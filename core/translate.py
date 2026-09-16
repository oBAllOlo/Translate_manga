"""Google Lens translation — translate manga page images via Chrome CDP."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Any
from urllib.parse import urlparse

from tqdm import tqdm

from core.models import IMAGE_EXTENSIONS, read_json, write_json

# Resolve the vendored lens_images_core path.
VENDOR_LENS_DIR = Path(__file__).resolve().parent.parent / "vendor" / "lens_core"

# Fallback to the old nested path if vendor/ hasn't been set up yet.
_OLD_LENS_DIR = (
    Path(__file__).resolve().parent.parent
    / "Translate-image-manga-In-Page-main"
    / "Translate-image-manga-In-Page-main"
)

LENS_CORE_DIR = VENDOR_LENS_DIR if VENDOR_LENS_DIR.exists() else _OLD_LENS_DIR


def save_data_url(data_url: str, target: Path) -> None:
    """Decode a ``data:image/…`` URL and write it to *target*."""
    if not data_url.startswith("data:image/"):
        raise ValueError("Expected a data:image URL")
    _, payload = data_url.split(",", 1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(payload))


async def lens_translate_work_dir(
    work_dir: Path,
    lang: str = "th",
    limit: int | None = None,
    force: bool = False,
    concurrency: int = 4,
    verbose: bool = False,
    max_retries: int = 2,
    retry_delay: float = 3.0,
    only_pages: set[int] | None = None,
    on_progress: Callable[[int, int], Any] | None = None,
) -> list[dict]:
    """Translate every page in *work_dir* via Google Lens and return results."""
    if not LENS_CORE_DIR.exists():
        raise RuntimeError(f"Lens core folder not found: {LENS_CORE_DIR}")
    if str(LENS_CORE_DIR) not in sys.path:
        sys.path.insert(0, str(LENS_CORE_DIR))
    os.environ.setdefault("CHROME_IDLE_SECONDS", "120")

    try:
        from lens_images_core import translate_lens  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Could not import lens_images_core. Ensure the folder "
            "`vendor/lens_core` (or legacy path) exists and dependencies are installed."
        ) from exc

    if not verbose:
        logging.getLogger("lens_images_core").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    manifest = read_json(work_dir / "manifest.json", {})
    pages = manifest.get("pages") or []
    if not pages:
        raise RuntimeError(f"No manifest pages found at {work_dir / 'manifest.json'}")
    if only_pages is not None:
        pages = [p for p in pages if int(p.get("page", 0)) in only_pages]
    if limit:
        pages = pages[:limit]

    translated_dir = work_dir / "translated_images"
    previous_rows = read_json(work_dir / "lens_translations.json", [])
    previous_by_page = {
        int(row["page"]): row
        for row in previous_rows
        if isinstance(row, dict) and str(row.get("page", "")).isdigit()
    }
    results: list[dict | None] = [None] * len(pages)
    sem = asyncio.Semaphore(max(1, concurrency))

    async def translate_one(index: int, row: dict) -> tuple[int, dict]:
        page_no = int(row["page"])
        image_url = row.get("url") or row.get("source")
        if not image_url or not str(image_url).startswith(("http://", "https://")):
            return index, {
                "page": page_no,
                "file": row.get("file", ""),
                "thai": "",
                "translated_file": "",
                "error": "Google Lens batch needs an HTTP image URL in manifest.json",
            }

        suffix = Path(urlparse(image_url).path).suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            suffix = ".png"
        target = translated_dir / f"page-{page_no:03d}{suffix}"

        if target.exists() and not force:
            cached = previous_by_page.get(page_no, {})
            return index, {
                **cached,
                **{
                    "page": page_no,
                    "file": row.get("file", ""),
                    "source_url": image_url,
                    "translated_file": str(target),
                    "cached": True,
                },
            }

        async with sem:
            last_error: str = ""
            for attempt in range(max_retries + 1):
                try:
                    response = await translate_lens(image_url, lang=lang)
                    image_data = response.get("image") or ""
                    if image_data.startswith("data:image/"):
                        save_data_url(image_data, target)
                        orig_file = Path(row.get("file", ""))
                        if orig_file.exists():
                            try:
                                from core.cleaner import clean_page_file
                                clean_page_file(orig_file, target, target)
                            except Exception as clean_err:
                                logging.getLogger("core.translate").warning(
                                    f"Auto-clean failed for page {page_no}: {clean_err}"
                                )
                    else:
                        raise RuntimeError("Lens returned no translated image")
                    return index, {
                        "page": page_no,
                        "file": row.get("file", ""),
                        "source_url": image_url,
                        "thai": response.get("text", ""),
                        "translated_file": str(target),
                        "loc": response.get("loc", ""),
                        "json_url": response.get("json_url", ""),
                        "attempts": attempt + 1,
                    }
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt < max_retries:
                        await asyncio.sleep(retry_delay * (attempt + 1))
            return index, {
                "page": page_no,
                "file": row.get("file", ""),
                "source_url": image_url,
                "thai": "",
                "translated_file": "",
                "error": last_error,
                "attempts": max_retries + 1,
            }

    completed_count = 0
    tasks = [asyncio.create_task(translate_one(index, row)) for index, row in enumerate(pages)]
    for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"Google Lens translate ({concurrency} workers)"):
        index, row = await task
        results[index] = row
        completed_count += 1
        if on_progress is not None:
            try:
                cb_res = on_progress(completed_count, len(pages))
                if asyncio.iscoroutine(cb_res):
                    await cb_res
            except Exception:
                pass

    final_results = [row for row in results if row is not None]
    if only_pages is not None:
        existing = {int(r["page"]): r for r in read_json(work_dir / "lens_translations.json", []) if isinstance(r, dict)}
        for row in final_results:
            existing[int(row["page"])] = row
        merged = [existing[k] for k in sorted(existing.keys())]
        write_json(work_dir / "lens_translations.json", merged)
    else:
        write_json(work_dir / "lens_translations.json", final_results)
    failed = [r for r in final_results if not r.get("translated_file")]
    if failed:
        write_json(work_dir / "lens_failed.json", [r["page"] for r in failed])
    elif (work_dir / "lens_failed.json").exists():
        (work_dir / "lens_failed.json").unlink()
    return final_results
