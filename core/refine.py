"""LLM Refine — Polish Thai manga translations using local Ollama TranslateGemma."""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import os
from pathlib import Path
from typing import Callable, Any

import httpx

from core.models import read_json, write_json

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "translategemma:12b"

MANGA_REFINE_SYSTEM_PROMPT = (
    "คุณเป็นนักแปลมังงะมืออาชีพ ได้รับข้อความภาษาไทยที่แปลจากมังงะโดย Google Lens\n"
    "กรุณาปรับสำนวนให้เป็นธรรมชาติ เหมาะกับบทสนทนาของตัวละคร ใช้ภาษาพูดที่เหมาะสม\n"
    "ห้ามเพิ่มหรือลดเนื้อหา แค่ปรับสำนวนให้อ่านลื่นขึ้น ตอบกลับเฉพาะข้อความที่ปรับแล้วเท่านั้น"
)


class OllamaError(RuntimeError):
    """Base exception for Ollama LLM errors."""
    pass


class OllamaConnectionError(OllamaError):
    """Raised when the Ollama server is unreachable."""
    pass


class OllamaModelError(OllamaError):
    """Raised when the requested model is not found on the Ollama server."""
    pass


def get_ollama_config(
    base_url: str | None = None,
    model: str | None = None,
) -> tuple[str, str]:
    """Resolve base URL and model from parameters or environment variables."""
    resolved_base = (
        base_url
        or os.environ.get("OLLAMA_BASE_URL")
        or DEFAULT_OLLAMA_BASE_URL
    ).rstrip("/")
    resolved_model = (
        model
        or os.environ.get("OLLAMA_MODEL")
        or DEFAULT_OLLAMA_MODEL
    )
    return resolved_base, resolved_model


async def check_ollama_health(
    base_url: str | None = None,
    model: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Verify Ollama server is reachable and the required model is available."""
    url, target_model = get_ollama_config(base_url, model)
    endpoint = f"{url}/api/tags"

    async def _check(c: httpx.AsyncClient):
        try:
            resp = await c.get(endpoint, timeout=10.0)
            if resp.status_code != 200:
                raise OllamaConnectionError(
                    f"Ollama server returned status {resp.status_code} at {endpoint}"
                )
            data = resp.json()
            models_list = data.get("models") or []
            installed_names = [m.get("name", "") for m in models_list if isinstance(m, dict)]

            # Check exact match or base match (e.g. translategemma:12b or translategemma)
            has_model = False
            for name in installed_names:
                if name == target_model:
                    has_model = True
                    break
                if name.split(":")[0] == target_model.split(":")[0]:
                    has_model = True
                    break

            if not has_model:
                raise OllamaModelError(
                    f"Model '{target_model}' not found in Ollama. "
                    f"Available models: {installed_names}. "
                    f"Please run 'ollama pull {target_model}'."
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama server at {url}. "
                f"Make sure Ollama is running ('ollama serve')."
            ) from exc

    if client is not None:
        await _check(client)
    else:
        async with httpx.AsyncClient() as c:
            await _check(c)


async def refine_single_text(
    text: str,
    base_url: str | None = None,
    model: str | None = None,
    client: httpx.AsyncClient | None = None,
    system_prompt: str = MANGA_REFINE_SYSTEM_PROMPT,
) -> str:
    """Send Thai text to Ollama chat endpoint and return polished Thai text."""
    if not text or not text.strip():
        return ""

    url, target_model = get_ollama_config(base_url, model)
    endpoint = f"{url}/api/chat"
    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "stream": False,
    }

    async def _post(c: httpx.AsyncClient) -> str:
        resp = await c.post(endpoint, json=payload, timeout=60.0)
        if resp.status_code != 200:
            raise OllamaError(f"Ollama chat error {resp.status_code}: {resp.text}")
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        return content.strip()

    if client is not None:
        return await _post(client)
    else:
        async with httpx.AsyncClient() as c:
            return await _post(c)


async def refine_chapter_work_dir(
    work_dir: Path,
    force: bool = False,
    only_pages: set[int] | None = None,
    on_progress: Callable[[int, int], Any] | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Refine Thai translations in work_dir sequentially and save to llm_refined.json."""
    url, target_model = get_ollama_config(base_url, model)

    lens_file = work_dir / "lens_translations.json"
    if not lens_file.exists():
        raise RuntimeError(f"lens_translations.json not found in {work_dir}")

    lens_rows = read_json(lens_file, [])
    if not lens_rows:
        return []

    # Map lens rows by page number
    lens_by_page: dict[int, dict] = {}
    for r in lens_rows:
        if isinstance(r, dict) and "page" in r:
            try:
                lens_by_page[int(r["page"])] = r
            except (ValueError, TypeError):
                pass

    if only_pages is not None:
        target_pages = sorted([p for p in lens_by_page.keys() if p in only_pages])
    else:
        target_pages = sorted(lens_by_page.keys())

    refined_file = work_dir / "llm_refined.json"
    existing_refined = read_json(refined_file, [])
    refined_by_page: dict[int, dict] = {}
    for r in existing_refined:
        if isinstance(r, dict) and "page" in r:
            try:
                refined_by_page[int(r["page"])] = r
            except (ValueError, TypeError):
                pass

    # Fail fast: check Ollama health before doing any work
    async with httpx.AsyncClient() as client:
        await check_ollama_health(url, target_model, client=client)

        results: list[dict] = []
        total_target = len(target_pages)
        completed_count = 0

        for page_no in target_pages:
            lens_entry = lens_by_page.get(page_no, {})
            original_text = lens_entry.get("thai") or lens_entry.get("text") or ""

            # Check cache
            cached_entry = refined_by_page.get(page_no)
            if cached_entry and not force and cached_entry.get("refined_text") is not None and not cached_entry.get("error"):
                res_dict = {
                    "page": page_no,
                    "original_text": cached_entry.get("original_text", original_text),
                    "refined_text": cached_entry.get("refined_text", ""),
                    "model": cached_entry.get("model", target_model),
                    "timestamp": cached_entry.get("timestamp", datetime.now().isoformat()),
                    "cached": True,
                }
                results.append(res_dict)
                refined_by_page[page_no] = res_dict
            else:
                # Refine with Ollama
                refined_text = ""
                error_msg: str | None = None
                if original_text.strip():
                    try:
                        refined_text = await refine_single_text(
                            original_text, url, target_model, client=client
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to refine page {page_no}: {exc}")
                        error_msg = f"{type(exc).__name__}: {exc}"

                res_dict = {
                    "page": page_no,
                    "original_text": original_text,
                    "refined_text": refined_text if not error_msg else (cached_entry.get("refined_text", "") if cached_entry else ""),
                    "model": target_model,
                    "timestamp": datetime.now().isoformat(),
                    "cached": False,
                }
                if error_msg:
                    res_dict["error"] = error_msg

                results.append(res_dict)
                refined_by_page[page_no] = res_dict

            completed_count += 1
            if on_progress is not None:
                try:
                    cb = on_progress(completed_count, total_target)
                    if asyncio.iscoroutine(cb):
                        await cb
                except Exception:
                    pass

        # Save merged results back to llm_refined.json
        sorted_all = [refined_by_page[p] for p in sorted(refined_by_page.keys())]
        write_json(refined_file, sorted_all)

    return results


async def refine_single_page(
    work_dir: Path,
    page_no: int,
    force: bool = False,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    """Refine a single page and update llm_refined.json."""
    results = await refine_chapter_work_dir(
        work_dir=work_dir,
        force=force,
        only_pages={page_no},
        base_url=base_url,
        model=model,
    )
    if results:
        return results[0]
    return {"page": page_no, "original_text": "", "refined_text": "", "cached": False}
