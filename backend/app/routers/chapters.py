"""Chapter API endpoints — list, detail, translate, retry, delete."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.app.models.database import get_db, insert_job
from backend.app.models.schemas import (
    ChapterSummary, ChapterDetail, SeriesGroup, PageInfo,
    TouchupRequest, RecleanRequest,
)
from backend.app.services.job_runner import (
    OUTPUT_ROOT, PDF_ROOT,
    run_translate_job, run_retry_job,
)
from core.models import IMAGE_EXTENSIONS, read_json

router = APIRouter(prefix="/api/chapters", tags=["chapters"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_chapter(path: Path) -> dict:
    """Scan a single chapter directory and return summary info."""
    name = path.name
    manifest = read_json(path / "manifest.json", {})

    pdfs: list[str] = []
    try:
        for entry in os.scandir(path):
            if entry.is_file() and entry.name.lower().endswith(".pdf"):
                pdfs.append(entry.name)
    except OSError:
        pass
    pdfs.sort()
    external_pdf = PDF_ROOT / f"{name}.pdf"
    if external_pdf.exists():
        pdfs.append(f"pdfs/{external_pdf.name}")

    def _first_image(folder: Path) -> str | None:
        try:
            best = None
            for entry in os.scandir(folder):
                if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_EXTENSIONS:
                    if best is None or entry.name < best:
                        best = entry.name
            return best
        except OSError:
            return None

    def _count_images(folder: Path) -> int:
        try:
            return sum(1 for e in os.scandir(folder) if e.is_file() and Path(e.name).suffix.lower() in IMAGE_EXTENSIONS)
        except OSError:
            return 0

    thumb, thumb_kind = None, "none"
    tr_first = _first_image(path / "translated_images")
    if tr_first:
        thumb, thumb_kind = f"translated_images/{tr_first}", "translated"
    else:
        im_first = _first_image(path / "images")
        if im_first:
            thumb, thumb_kind = f"images/{im_first}", "original"

    # Extract series title from manga title (clean prefixes like Chapter 145 | and site suffixes)
    raw_title = manifest.get("title", name)
    clean_title = re.sub(r"^(?:Chapter|Ch\.?)\s*\d+\s*\|\s*", "", raw_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r"\s*\|\s*(?:Weeb\s*Central|MangaDex|MangaBlaze).*$", "", clean_title, flags=re.IGNORECASE).strip()
    series_title = re.sub(r"\s*Ch\.?\s*\d+.*$", "", clean_title).strip() or clean_title or raw_title

    return {
        "name": name,
        "title": raw_title,
        "page_count": manifest.get("page_count"),
        "translated_count": _count_images(path / "translated_images"),
        "pdfs": pdfs,
        "thumb": thumb,
        "thumb_kind": thumb_kind,
        "has_failed": (path / "lens_failed.json").exists(),
        "mtime": path.stat().st_mtime,
        "series_title": series_title,
    }


def _list_chapter_dirs() -> list[Path]:
    """Return all chapter directories under OUTPUT_ROOT."""
    if not OUTPUT_ROOT.exists():
        return []
    try:
        pdf_root_resolved = PDF_ROOT.resolve()
    except OSError:
        pdf_root_resolved = None

    dirs: list[Path] = []
    for path in OUTPUT_ROOT.iterdir():
        if not path.is_dir():
            continue
        try:
            if pdf_root_resolved is not None and path.resolve() == pdf_root_resolved:
                continue
        except OSError:
            pass
        dirs.append(path)
    return dirs


def _get_all_chapters() -> list[dict]:
    """Scan all chapter directories and return summaries."""
    dirs = _list_chapter_dirs()
    if not dirs:
        return []
    with ThreadPoolExecutor(max_workers=min(16, len(dirs))) as pool:
        rows = list(pool.map(_scan_chapter, dirs))
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows


def _group_by_series(chapters: list[dict]) -> list[dict]:
    """Group chapters by series title."""
    series_map: dict[str, list[dict]] = {}
    for ch in chapters:
        key = ch.get("series_title") or ch.get("title") or ch["name"]
        series_map.setdefault(key, []).append(ch)

    result = []
    for series_title, chs in series_map.items():
        chs.sort(key=lambda c: c["mtime"], reverse=True)
        result.append({
            "series_title": series_title,
            "chapters": chs,
            "chapter_count": len(chs),
            "thumb": chs[0].get("thumb"),
            "thumb_name": chs[0].get("name"),
        })
    result.sort(key=lambda s: max(c["mtime"] for c in s["chapters"]), reverse=True)
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_chapters():
    loop = asyncio.get_event_loop()
    chapters = await loop.run_in_executor(None, _get_all_chapters)
    series = _group_by_series(chapters)
    return {"chapters": chapters, "series": series}


@router.get("/{name}")
async def get_chapter(name: str):
    target = OUTPUT_ROOT / name
    if not target.exists():
        # Case-insensitive check
        found = None
        if OUTPUT_ROOT.exists():
            for p in OUTPUT_ROOT.iterdir():
                if p.is_dir() and p.name.lower() == name.lower():
                    found = p
                    break
        if found:
            target = found
        else:
            raise HTTPException(404, f"Chapter '{name}' not found on disk")

    manifest = read_json(target / "manifest.json", {})
    translations = read_json(target / "lens_translations.json", [])
    translated_by_page = {
        int(r["page"]): r for r in translations if isinstance(r, dict)
    }

    pages: list[dict] = []
    for p in manifest.get("pages", []):
        page_no = int(p.get("page", 0))
        tr = translated_by_page.get(page_no, {})

        raw_file = p.get("file") or ""
        raw_tr = tr.get("translated_file") or ""
        orig_filename = Path(raw_file).name if raw_file else f"page-{page_no:03d}.jpg"
        tr_filename = Path(raw_tr).name if raw_tr else (orig_filename if tr.get("translated_file") else None)

        pages.append({
            "page": page_no,
            "file": f"{target.name}/images/{orig_filename}",
            "url": p.get("url"),
            "translated_file": f"{target.name}/translated_images/{tr_filename}" if tr_filename else None,
            "has_translation": bool(tr.get("translated_file")),
        })

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _scan_chapter, target)

    return {
        "name": target.name,
        "title": manifest.get("title", target.name),
        "source": manifest.get("source"),
        "page_count": manifest.get("page_count"),
        "translated_count": info["translated_count"],
        "pages": pages,
        "pdfs": info["pdfs"],
        "has_failed": info["has_failed"],
    }


@router.post("/{name}/translate")
async def translate_chapter(name: str):
    target = OUTPUT_ROOT / name
    if not target.exists():
        raise HTTPException(404, "Chapter not found")

    job_id = uuid.uuid4().hex[:8]
    db = await get_db()
    try:
        await insert_job(db, job_id, f"translate: {name}")
    finally:
        await db.close()

    asyncio.create_task(run_translate_job(job_id, name))
    return {"job_id": job_id}


@router.post("/{name}/retry")
async def retry_chapter(name: str):
    target = OUTPUT_ROOT / name
    if not target.exists():
        raise HTTPException(404, "Chapter not found")

    failed = read_json(target / "lens_failed.json", [])
    if not failed:
        raise HTTPException(400, "No failed pages to retry")

    job_id = uuid.uuid4().hex[:8]
    db = await get_db()
    try:
        await insert_job(db, job_id, f"retry: {name}")
    finally:
        await db.close()

    asyncio.create_task(run_retry_job(job_id, name, [int(p) for p in failed]))
    return {"job_id": job_id}


def _safe_rmtree(path: Path):
    """Safely remove a directory tree on Windows handling readonly/permission locks."""
    def _onerror(func, p, exc_info):
        try:
            os.chmod(p, 0o777)
            func(p)
        except Exception:
            pass

    if path.exists() and path.is_dir():
        shutil.rmtree(path, onerror=_onerror)


@router.delete("/{name}")
async def delete_chapter(name: str):
    target = OUTPUT_ROOT / name
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Chapter not found")
    if target.resolve().parent != OUTPUT_ROOT.resolve():
        raise HTTPException(400, "Invalid path")
    _safe_rmtree(target)
    external_pdf = PDF_ROOT / f"{name}.pdf"
    if external_pdf.exists():
        try:
            external_pdf.unlink()
        except OSError:
            pass

    # Clean up corresponding job in DB so Dashboard doesn't show ghost job
    db = await get_db()
    try:
        await db.execute("DELETE FROM jobs WHERE url LIKE ? OR progress LIKE ?", (f"%{name}%", f"%{name}%"))
        await db.commit()
    finally:
        await db.close()

    return {"deleted": name}


@router.delete("")
@router.delete("/")
async def delete_all_chapters():
    deleted = []
    try:
        pdf_root_resolved = PDF_ROOT.resolve()
    except OSError:
        pdf_root_resolved = None

    for path in list(OUTPUT_ROOT.iterdir()):
        if not path.is_dir():
            continue
        try:
            if pdf_root_resolved is not None and path.resolve() == pdf_root_resolved:
                continue
        except OSError:
            pass
        try:
            _safe_rmtree(path)
            deleted.append(path.name)
        except Exception:
            pass

    if PDF_ROOT.exists():
        for pdf_file in list(PDF_ROOT.glob("*.pdf")):
            try:
                pdf_file.unlink()
            except OSError:
                pass

    # Also clean up completed and errored jobs from DB
    db = await get_db()
    try:
        await db.execute("DELETE FROM jobs WHERE status IN ('done', 'error')")
        await db.commit()
    finally:
        await db.close()

    return {"deleted": deleted, "count": len(deleted)}


@router.post("/{name}/pages/{page_no}/touchup")
async def touchup_chapter_page(name: str, page_no: int, payload: TouchupRequest):
    """Save manual inpainting or typesetting edits from reader touch-up studio."""
    import base64
    target = OUTPUT_ROOT / name
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Chapter not found")

    translated_dir = target / "translated_images"
    translated_dir.mkdir(parents=True, exist_ok=True)
    out_file = translated_dir / f"page-{page_no:03d}.png"

    data_url = payload.image_data
    if not data_url.startswith("data:image/"):
        raise HTTPException(400, "Invalid image format; expected data:image/...")

    try:
        _, encoded = data_url.split(",", 1)
        raw_bytes = base64.b64decode(encoded)
        out_file.write_bytes(raw_bytes)
    except Exception as exc:
        raise HTTPException(400, f"Failed to decode and save image: {exc}")

    return {"success": True, "page": page_no, "file": str(out_file)}


@router.post("/{name}/pages/{page_no}/reclean")
async def reclean_chapter_page(name: str, page_no: int, req: RecleanRequest = RecleanRequest()):
    """Re-run the automated bubble cleaner & inpainter on a specific page."""
    target = OUTPUT_ROOT / name
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Chapter not found")

    images_dir = target / "images"
    translated_dir = target / "translated_images"

    orig_file = None
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        cand = images_dir / f"page-{page_no:03d}{ext}"
        if cand.exists():
            orig_file = cand
            break

    if not orig_file:
        raise HTTPException(404, f"Original image for page {page_no} not found")

    trans_file = None
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        cand = translated_dir / f"page-{page_no:03d}{ext}"
        if cand.exists():
            trans_file = cand
            break

    if not trans_file:
        raise HTTPException(404, f"Translated image for page {page_no} not found")

    try:
        from core.cleaner import clean_page_file
        clean_page_file(
            orig_file,
            trans_file,
            trans_file,
        )
    except Exception as exc:
        raise HTTPException(500, f"Recleaning failed: {exc}")

    return {"success": True, "page": page_no, "file": str(trans_file)}

