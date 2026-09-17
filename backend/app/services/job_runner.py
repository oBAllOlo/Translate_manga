"""Background job runner — orchestrates download, translate, PDF.

Key design (ADR-0003):
- Overlapping pipeline: download pages are enqueued into an asyncio.Queue as
  soon as each one finishes; translation starts immediately on the first
  available page rather than waiting for all downloads to complete.
- Shared HTTP session per chapter (single TCP/TLS handshake per host).
- Configurable Lens concurrency (default 8, range 2-12).
- Progress throttle: DB writes + WS broadcasts at most once every 1.5 s
  (first and last updates are always sent immediately).
- Error handling: Retry-then-Skip — download failures retry up to 3 times;
  if still failing the page is skipped so other pages continue translating.
- Range jobs apply the overlap within each chapter; chapters are still
  processed sequentially to avoid Lens rate-limiting.
- Job lifecycle states are preserved unchanged (queued → parsing →
  downloading → translating → done | error).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Any
from urllib.parse import urlparse as _urlparse

import aiosqlite

from backend.app.models.database import get_db, update_job, insert_job
from backend.app.ws.progress import manager
from core.models import (
    PageImage,
    slugify,
    write_json,
    read_json,
    IMAGE_EXTENSIONS,
    resolve_safe_chapter_dir,
)
from core.parsers import parse_source
from core.pdf import make_long_strip_pdf
from core.translate import LENS_CORE_DIR, save_data_url, lens_translate_work_dir

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "output"
PDF_ROOT = OUTPUT_ROOT / "pdfs"


# ---------------------------------------------------------------------------
# Progress throttle
# ---------------------------------------------------------------------------


class _ProgressThrottle:
    """Rate-limit DB writes + WS broadcasts to at most once per *interval* seconds.

    The first call and any call with ``force=True`` always go through immediately.
    The last update of a job should always be sent with ``force=True``.
    """

    def __init__(self, interval: float = 1.5) -> None:
        self._interval = interval
        self._last_sent: float = 0.0
        self._pending: dict[str, Any] = {}

    async def maybe_send(
        self,
        db: aiosqlite.Connection,
        job_id: str,
        *,
        force: bool = False,
        **fields,
    ) -> None:
        self._pending.update(fields)
        now = time.monotonic()
        if force or (now - self._last_sent) >= self._interval:
            await _update_and_broadcast(db, job_id, **self._pending)
            self._last_sent = now
            self._pending = {}


# ---------------------------------------------------------------------------
# WebSocket helpers
# ---------------------------------------------------------------------------


async def _broadcast_job(job_id: str, **data) -> None:
    """Broadcast a job update via WebSocket."""
    await manager.broadcast("job_update", {"job_id": job_id, **data})


async def _update_and_broadcast(db: aiosqlite.Connection, job_id: str, **fields) -> None:
    """Update job in DB and broadcast the change."""
    await update_job(db, job_id, **fields)
    await _broadcast_job(job_id, **fields)


# ---------------------------------------------------------------------------
# Active task registry
# ---------------------------------------------------------------------------

ACTIVE_TASKS: dict[str, asyncio.Task] = {}


def register_job_task(job_id: str, task: asyncio.Task) -> asyncio.Task:
    """Register an asyncio Task for a running job so it can be cancelled later."""
    ACTIVE_TASKS[job_id] = task

    def _on_done(t: asyncio.Task) -> None:
        if ACTIVE_TASKS.get(job_id) is t:
            ACTIVE_TASKS.pop(job_id, None)

    task.add_done_callback(_on_done)
    return task


async def cancel_job_task(job_id: str) -> bool:
    """Cancel a running job task by ID. Returns True if task was found and cancelled."""
    task = ACTIVE_TASKS.pop(job_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def cancel_all_job_tasks() -> int:
    """Cancel all running job tasks. Returns count of tasks cancelled."""
    count = 0
    for job_id, task in list(ACTIVE_TASKS.items()):
        if not task.done():
            task.cancel()
            count += 1
    ACTIVE_TASKS.clear()
    return count


# ---------------------------------------------------------------------------
# Download helper — sync, module-level, called from thread pool
# ---------------------------------------------------------------------------


def _download_one_page(session, page: PageImage, images_dir: Path) -> dict:
    """Download a single page with retry + fallback logic.

    Returns a dict with ``page``, ``url``, ``file`` on success,
    or ``page``, ``url``, ``error`` on failure.
    Thread-safe: uses a shared *session* whose connection pool handles
    concurrent requests safely.
    """
    target = images_dir / page.filename
    final_url = page.url

    if target.exists() and target.stat().st_size > 0:
        return {"page": page.page, "url": final_url, "file": str(target)}

    size = 0
    for attempt in range(3):
        try:
            size = _fetch_image(session, page.url, target)
        except Exception:
            size = 0

        if size == 0:
            md_fallback = _mangadex_fallback(page.url)
            if md_fallback:
                try:
                    if target.exists():
                        target.unlink()
                    size = _fetch_image(session, md_fallback, target)
                    if size > 0:
                        final_url = md_fallback
                except Exception:
                    pass

        if size == 0:
            sp_fallback = _unwrap_spoilerhat(page.url)
            if sp_fallback:
                try:
                    if target.exists():
                        target.unlink()
                    size = _fetch_image(session, sp_fallback, target)
                    if size > 0:
                        final_url = sp_fallback
                except Exception:
                    pass

        if size > 0:
            return {"page": page.page, "url": final_url, "file": str(target)}

        # Exponential backoff before next retry
        if attempt < 2:
            time.sleep(1.0 * (attempt + 1))

    # All attempts exhausted — clean up
    if target.exists():
        try:
            target.unlink()
        except OSError:
            pass
    return {"page": page.page, "url": page.url, "error": "Download failed after 3 attempts"}


# ---------------------------------------------------------------------------
# Overlapping pipeline helpers
# ---------------------------------------------------------------------------

_SENTINEL = object()  # marks end-of-download in the queue


async def _translate_consumer(
    queue: asyncio.Queue,
    work_dir: Path,
    *,
    concurrency: int = 8,
    lang: str = "th",
    max_retries: int = 2,
    on_progress: Callable[[int, int, int], Any] | None = None,
    total_pages: int = 0,
) -> list[dict]:
    """Consume download results from *queue* and translate via Google Lens.

    A translate task is dispatched immediately on each page arrival from the
    queue so translation runs concurrently with ongoing downloads.
    Skips pages that failed to download (``error`` key present).
    Returns list of translation result dicts sorted by page number.
    """
    if not LENS_CORE_DIR.exists():
        raise RuntimeError(f"Lens core folder not found: {LENS_CORE_DIR}")
    if str(LENS_CORE_DIR) not in sys.path:
        sys.path.insert(0, str(LENS_CORE_DIR))
    os.environ.setdefault("CHROME_IDLE_SECONDS", "120")

    try:
        from lens_images_core import translate_lens  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Could not import lens_images_core. Ensure vendor/lens_core exists."
        ) from exc

    logging.getLogger("lens_images_core").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    translated_dir = work_dir / "translated_images"
    translated_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[dict] = []
    done_count = 0
    fail_count = 0  # incremented per result — avoids O(n²) scan on every progress call

    async def _translate_one(dl_result: dict) -> dict:
        page_no = dl_result["page"]
        if "error" in dl_result:
            return {
                "page": page_no,
                "file": dl_result.get("file", ""),
                "thai": "",
                "translated_file": "",
                "error": dl_result["error"],
            }

        image_url = dl_result["url"]
        suffix = Path(_urlparse(image_url).path).suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            suffix = ".png"
        target = translated_dir / f"page-{page_no:03d}{suffix}"

        if target.exists():
            return {
                "page": page_no,
                "file": dl_result.get("file", ""),
                "source_url": image_url,
                "translated_file": str(target),
                "cached": True,
            }

        async with sem:
            last_error = ""
            for attempt in range(max_retries + 1):
                try:
                    response = await translate_lens(image_url, lang=lang)
                    image_data = response.get("image") or ""
                    if image_data.startswith("data:image/"):
                        save_data_url(image_data, target)
                    else:
                        raise RuntimeError("Lens returned no translated image")
                    return {
                        "page": page_no,
                        "file": dl_result.get("file", ""),
                        "source_url": image_url,
                        "thai": response.get("text", ""),
                        "translated_file": str(target),
                        "attempts": attempt + 1,
                    }
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt < max_retries:
                        await asyncio.sleep(3.0 * (attempt + 1))

            return {
                "page": page_no,
                "file": dl_result.get("file", ""),
                "source_url": image_url,
                "thai": "",
                "translated_file": "",
                "error": last_error,
                "attempts": max_retries + 1,
            }

    # Dispatch a translate task immediately on each page arrival (true overlap)
    results: list[dict] = []
    done_count = 0
    fail_count = 0
    running_tasks: set[asyncio.Task] = set()

    async def _handle_item(dl_result: dict) -> None:
        nonlocal done_count, fail_count
        res = await _translate_one(dl_result)
        results.append(res)
        done_count += 1
        if not res.get("translated_file"):
            fail_count += 1
        if on_progress is not None:
            cb = on_progress(done_count, total_pages or done_count, fail_count)
            if asyncio.iscoroutine(cb):
                await cb

    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        task = asyncio.create_task(_handle_item(item))
        running_tasks.add(task)
        task.add_done_callback(running_tasks.discard)

    if running_tasks:
        await asyncio.gather(*running_tasks)

    return sorted(results, key=lambda r: r.get("page", 0))


async def _run_overlapping_pipeline(
    pages: list[PageImage],
    work_dir: Path,
    chunk_size: int,
    pdf_path: Path | None,
    concurrency: int,
    source_url: str,
    title: str,
    on_first_translate: Callable | None = None,
    on_progress: Callable[[int, int, int], Any] | None = None,
    on_download: Callable[[int, int], Any] | None = None,
) -> tuple[int, int, Path]:
    """Full overlapping pipeline: download ↔ translate → PDF.

    Downloads run via ``loop.run_in_executor()`` which returns asyncio-compatible
    futures. ``asyncio.as_completed()`` on these futures yields between each
    completion, keeping the event loop free for translate tasks to run truly
    concurrently.

    Manifest is written once with the correct *source_url* and *title* after
    all downloads complete.
    Returns ``(ok_count, failed_count, pdf_path)``.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    manifest_rows: list[dict] = []
    images_dir = work_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    session = _get_session()

    async def _download_capture() -> None:
        """Submit pages to thread pool via asyncio futures; enqueue as they arrive.

        ``loop.run_in_executor()`` returns an ``asyncio.Future`` (not a
        ``concurrent.futures.Future``), so ``asyncio.as_completed()`` + ``await``
        correctly yields to the event loop between each completed download,
        allowing ``_translate_consumer`` tasks to run concurrently.
        """
        first_translate_signalled = False
        dl_count = 0
        total_dl = len(pages)
        with ThreadPoolExecutor(max_workers=8) as executor:
            async_futures = [
                loop.run_in_executor(executor, _download_one_page, session, page, images_dir)
                for page in pages
            ]
            for coro in asyncio.as_completed(async_futures):
                result = await coro  # yields to event loop — translate tasks can run here
                manifest_rows.append(result)
                dl_count += 1
                await queue.put(result)
                if not first_translate_signalled and on_first_translate:
                    first_translate_signalled = True
                    cb = on_first_translate()
                    if asyncio.iscoroutine(cb):
                        await cb
                if on_download:
                    cb = on_download(dl_count, total_dl)
                    if asyncio.iscoroutine(cb):
                        await cb
        await queue.put(_SENTINEL)

    # Producer + consumer run truly concurrently on the same event loop
    download_task = asyncio.create_task(_download_capture())
    translate_task = asyncio.create_task(
        _translate_consumer(
            queue, work_dir,
            concurrency=concurrency,
            on_progress=on_progress,
            total_pages=len(pages),
        )
    )
    await asyncio.gather(download_task, translate_task)
    results: list[dict] = translate_task.result()

    # Write manifest once with correct metadata (no double-write)
    successful_downloads = [r for r in manifest_rows if "error" not in r]
    write_json(
        work_dir / "manifest.json",
        {
            "source": source_url,
            "title": title,
            "page_count": len(successful_downloads),
            "pages": successful_downloads,
        },
    )

    # Write translation cache files
    failed_results = [r for r in results if not r.get("translated_file")]
    ok = len(results) - len(failed_results)
    write_json(work_dir / "lens_translations.json", results)
    if failed_results:
        write_json(work_dir / "lens_failed.json", [r["page"] for r in failed_results])
    elif (work_dir / "lens_failed.json").exists():
        (work_dir / "lens_failed.json").unlink()

    # Build PDF in thread pool (CPU-bound + I/O)
    PDF_ROOT.mkdir(parents=True, exist_ok=True)
    final_pdf = await loop.run_in_executor(
        None, make_long_strip_pdf, work_dir, pdf_path, True, chunk_size, 190
    )
    return ok, len(failed_results), final_pdf


# ---------------------------------------------------------------------------
# Public job runners
# ---------------------------------------------------------------------------


async def run_single_job(job_id: str, url: str, chunk_size: int, concurrency: int = 8) -> None:
    """Run a single chapter download + translate + PDF job (overlapping pipeline)."""
    db = await get_db()
    throttle = _ProgressThrottle(interval=1.5)
    try:
        await _update_and_broadcast(db, job_id, status="parsing", message="กำลังอ่าน URL")

        loop = asyncio.get_running_loop()
        title, pages = await loop.run_in_executor(None, parse_source, url)

        raw_slug = _urlparse(url).path.strip("/").split("/")[-1]
        chapter_slug = slugify(raw_slug) if raw_slug and raw_slug not in (".", "..") else slugify(title)
        work_dir = resolve_safe_chapter_dir(chapter_slug, OUTPUT_ROOT)
        work_dir.mkdir(parents=True, exist_ok=True)

        total_p = len(pages)
        dl_done = 0
        tr_done = 0
        tr_fails = 0
        translating_started = False

        await _update_and_broadcast(
            db, job_id,
            status="downloading",
            title=title,
            work_dir=str(work_dir),
            slug=work_dir.name,
            total_pages=total_p,
            downloaded=0,
            translated=0,
            message=f"ดาวน์โหลด {total_p} หน้า",
        )

        async def _update_single_progress(*, force: bool = False) -> None:
            if not translating_started:
                msg = f"ดาวน์โหลด {dl_done}/{total_p}"
                st = "downloading"
            elif dl_done < total_p:
                msg = f"แปล {tr_done}/{total_p} (ดาวน์โหลด {dl_done}/{total_p})"
                st = "translating"
            else:
                msg = f"แปล {tr_done}/{total_p}"
                st = "translating"

            await throttle.maybe_send(
                db, job_id, force=force,
                status=st,
                downloaded=dl_done,
                translated=tr_done,
                failed=tr_fails,
                total_pages=total_p,
                message=msg,
            )

        async def on_download(done: int, total: int) -> None:
            nonlocal dl_done
            dl_done = done
            await _update_single_progress()

        async def on_first_translate() -> None:
            nonlocal translating_started
            translating_started = True
            await _update_single_progress(force=True)

        async def on_progress(done: int, total: int, fails: int) -> None:
            nonlocal tr_done, tr_fails
            tr_done = done
            tr_fails = fails
            await _update_single_progress()

        ok, failed, pdf_path = await _run_overlapping_pipeline(
            pages, work_dir, chunk_size,
            PDF_ROOT / f"{chapter_slug}.pdf",
            concurrency,
            source_url=url,
            title=title,
            on_first_translate=on_first_translate,
            on_progress=on_progress,
            on_download=on_download,
        )

        rel_pdf = f"pdfs/{chapter_slug}.pdf" if (pdf_path and Path(pdf_path).exists()) else None
        await _update_and_broadcast(
            db, job_id,
            status="done",
            downloaded=total_p,
            translated=ok,
            failed=failed,
            pdf=rel_pdf,
            message="เสร็จแล้ว",
        )
        await manager.broadcast("chapter_changed", {"slug": chapter_slug})

    except asyncio.CancelledError:
        logger.info("Job %s was cancelled", job_id)
        await _update_and_broadcast(db, job_id, status="error", message="ยกเลิกการทำงานแล้ว (Cancelled)")
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        await _update_and_broadcast(db, job_id, status="error", message=f"{type(exc).__name__}: {exc}")
    finally:
        await db.close()


async def run_range_job(
    job_id: str, base_url: str, start: int, end: int, chunk_size: int, concurrency: int = 8
) -> None:
    """Run a chapter range job (overlapping within each chapter, sequential between)."""
    db = await get_db()
    throttle = _ProgressThrottle(interval=1.5)
    try:
        chapters = list(range(start, end + 1))
        base = base_url if base_url.endswith("-") else base_url.rstrip("/") + "/"
        await _update_and_broadcast(
            db, job_id,
            total_chapters=len(chapters),
            done_chapters=0,
            message=f"Range {start}-{end}",
        )
        failures: list[int] = []
        loop = asyncio.get_running_loop()

        for done_count, n in enumerate(chapters, start=1):  # O(1) — no list scan per iteration
            chapter_url = f"{base}chapter-{n}/"
            await _update_and_broadcast(
                db, job_id, status="parsing", message=f"Chapter {n}", current_chapter=n,
            )
            try:
                title, pages = await loop.run_in_executor(None, parse_source, chapter_url)
                raw_slug = _urlparse(chapter_url).path.strip("/").split("/")[-1]
                chapter_slug = slugify(raw_slug) if raw_slug and raw_slug not in (".", "..") else f"chapter-{n}"
                work_dir = resolve_safe_chapter_dir(chapter_slug, OUTPUT_ROOT)
                work_dir.mkdir(parents=True, exist_ok=True)

                total_p = len(pages)
                dl_done = 0
                tr_done = 0
                tr_fails = 0
                translating_started = False

                await _update_and_broadcast(
                    db, job_id,
                    status="downloading",
                    title=title,
                    total_pages=total_p,
                    downloaded=0,
                    translated=0,
                    work_dir=str(work_dir),
                    slug=work_dir.name,
                )

                async def _update_range_progress(*, _n: int = n, force: bool = False) -> None:
                    if not translating_started:
                        msg = f"ดาวน์โหลด Ch {_n} ({dl_done}/{total_p})"
                        st = "downloading"
                    elif dl_done < total_p:
                        msg = f"แปล Ch {_n} {tr_done}/{total_p} (ดาวน์โหลด {dl_done}/{total_p})"
                        st = "translating"
                    else:
                        msg = f"แปล Ch {_n} ({tr_done}/{total_p})"
                        st = "translating"

                    await throttle.maybe_send(
                        db, job_id, force=force,
                        status=st,
                        downloaded=dl_done,
                        translated=tr_done,
                        failed=tr_fails,
                        total_pages=total_p,
                        message=msg,
                    )

                async def on_range_download(done: int, total: int, _n: int = n) -> None:
                    nonlocal dl_done
                    dl_done = done
                    await _update_range_progress(_n=_n)

                async def on_first_translate_range(_n: int = n) -> None:
                    nonlocal translating_started
                    translating_started = True
                    await _update_range_progress(_n=_n, force=True)

                async def on_range_progress(
                    done: int, total: int, fails: int, _n: int = n
                ) -> None:
                    nonlocal tr_done, tr_fails
                    tr_done = done
                    tr_fails = fails
                    await _update_range_progress(_n=_n)

                ok, failed, pdf_path = await _run_overlapping_pipeline(
                    pages, work_dir, chunk_size,
                    PDF_ROOT / f"{chapter_slug}.pdf",
                    concurrency,
                    source_url=chapter_url,
                    title=title,
                    on_first_translate=on_first_translate_range,
                    on_progress=on_range_progress,
                    on_download=on_range_download,
                )
                await manager.broadcast("chapter_changed", {"slug": chapter_slug})

            except Exception as exc:
                failures.append(n)
                await _update_and_broadcast(db, job_id, message=f"Ch {n} failed: {exc}")

            await throttle.maybe_send(db, job_id, force=True, done_chapters=done_count)

        msg = f"Range เสร็จ. {len(chapters) - len(failures)}/{len(chapters)} สำเร็จ"
        if failures:
            msg += f" · failed: {failures}"
        await _update_and_broadcast(db, job_id, status="done", message=msg)

    except asyncio.CancelledError:
        logger.info("Range job %s was cancelled", job_id)
        await _update_and_broadcast(db, job_id, status="error", message="ยกเลิกการทำงานแล้ว (Cancelled)")
    except Exception as exc:
        logger.exception("Range job %s failed", job_id)
        await _update_and_broadcast(db, job_id, status="error", message=str(exc))
    finally:
        await db.close()


async def run_translate_job(
    job_id: str, chapter_slug: str, chunk_size: int = 8, concurrency: int = 8
) -> None:
    """Translate an existing downloaded chapter (no pipeline overlap needed)."""
    db = await get_db()
    throttle = _ProgressThrottle(interval=1.5)
    try:
        work_dir = resolve_safe_chapter_dir(chapter_slug, OUTPUT_ROOT)
        await _update_and_broadcast(db, job_id, status="translating", message=f"แปล {chapter_slug}")

        # Adapt two-arg on_progress signature from lens_translate_work_dir to throttle
        async def _compat_progress(done: int, total: int) -> None:
            await throttle.maybe_send(
                db, job_id,
                status="translating",
                translated=done,
                total_pages=total,
                message=f"แปล {chapter_slug} ({done}/{total})",
            )

        loop = asyncio.get_running_loop()
        PDF_ROOT.mkdir(parents=True, exist_ok=True)
        results = await lens_translate_work_dir(
            work_dir, lang="th", concurrency=concurrency, verbose=False,
            max_retries=2, on_progress=_compat_progress,
        )
        ok = sum(1 for r in results if r.get("translated_file"))
        failed = len(results) - ok
        final_pdf = await loop.run_in_executor(
            None, make_long_strip_pdf, work_dir, PDF_ROOT / f"{chapter_slug}.pdf", True, chunk_size, 190
        )
        rel_pdf = f"pdfs/{chapter_slug}.pdf" if final_pdf and Path(final_pdf).exists() else None
        await _update_and_broadcast(
            db, job_id, status="done", translated=ok, failed=failed,
            pdf=rel_pdf, message="เสร็จแล้ว",
        )
        await manager.broadcast("chapter_changed", {"slug": chapter_slug})
    except asyncio.CancelledError:
        logger.info("Translate job %s was cancelled", job_id)
        await _update_and_broadcast(db, job_id, status="error", message="ยกเลิกการทำงานแล้ว (Cancelled)")
    except Exception as exc:
        logger.exception("Translate job %s failed", job_id)
        await _update_and_broadcast(db, job_id, status="error", message=f"{type(exc).__name__}: {exc}")
    finally:
        await db.close()


async def run_retry_job(job_id: str, chapter_slug: str, failed_pages: list[int]) -> None:
    """Retry failed pages for an existing chapter."""
    db = await get_db()
    throttle = _ProgressThrottle(interval=1.5)
    try:
        work_dir = resolve_safe_chapter_dir(chapter_slug, OUTPUT_ROOT)
        await _update_and_broadcast(
            db, job_id, status="translating",
            translated=0, total_pages=len(failed_pages),
            message=f"Retry {len(failed_pages)} หน้า",
        )

        async def on_retry_progress(done: int, total: int) -> None:
            await throttle.maybe_send(
                db, job_id,
                status="translating",
                translated=done,
                total_pages=total,
                message=f"Retry ({done}/{total})",
            )

        results = await lens_translate_work_dir(
            work_dir, lang="th", force=True, concurrency=4,
            max_retries=3, only_pages=set(failed_pages),
            on_progress=on_retry_progress,
        )
        ok = sum(1 for r in results if r.get("translated_file"))
        await _update_and_broadcast(
            db, job_id, status="done", translated=ok, failed=len(results) - ok,
            message=f"Retry เสร็จ: {ok} สำเร็จ",
        )
        await manager.broadcast("chapter_changed", {"slug": chapter_slug})
    except asyncio.CancelledError:
        logger.info("Retry job %s was cancelled", job_id)
        await _update_and_broadcast(db, job_id, status="error", message="ยกเลิกการทำงานแล้ว (Cancelled)")
    except Exception as exc:
        logger.exception("Retry job %s failed", job_id)
        await _update_and_broadcast(db, job_id, status="error", message=str(exc))
    finally:
        await db.close()


async def run_refine_job(job_id: str, chapter_slug: str, force: bool = False) -> None:
    """Refine Thai translations in background using local Ollama TranslateGemma."""
    db = await get_db()
    throttle = _ProgressThrottle(interval=1.5)
    try:
        work_dir = resolve_safe_chapter_dir(chapter_slug, OUTPUT_ROOT)
        if not work_dir.exists():
            raise FileNotFoundError(f"Chapter directory {chapter_slug} not found")

        await _update_and_broadcast(
            db, job_id, status="refining", message=f"ขัดเกลาสำนวน AI: {chapter_slug}"
        )

        async def on_refine_progress(done: int, total: int) -> None:
            await throttle.maybe_send(
                db, job_id,
                status="refining",
                translated=done,
                total_pages=total,
                message=f"ขัดเกลาสำนวน AI ({done}/{total})",
            )

        from core.refine import refine_chapter_work_dir
        results = await refine_chapter_work_dir(
            work_dir,
            force=force,
            on_progress=on_refine_progress,
        )
        ok = sum(1 for r in results if not r.get("error"))
        failed = len(results) - ok
        await _update_and_broadcast(
            db, job_id,
            status="done",
            translated=ok,
            failed=failed,
            message=f"ขัดเกลาสำนวน AI เสร็จสิ้น ({ok}/{len(results)} หน้า)",
        )
        await manager.broadcast("chapter_changed", {"slug": chapter_slug})
    except asyncio.CancelledError:
        logger.info("Refine job %s was cancelled", job_id)
        await _update_and_broadcast(db, job_id, status="error", message="ยกเลิกการทำงานแล้ว (Cancelled)")
    except Exception as exc:
        logger.exception("Refine job %s failed", job_id)
        await _update_and_broadcast(db, job_id, status="error", message=f"{type(exc).__name__}: {exc}")
    finally:
        await db.close()

