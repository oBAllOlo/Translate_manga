from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import re
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import PageBreak, SimpleDocTemplate
from tqdm import tqdm


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
LENS_CORE_DIR = Path(__file__).resolve().parent / "Translate-image-manga-In-Page-main" / "Translate-image-manga-In-Page-main"


@dataclass
class PageImage:
    page: int
    url: str
    filename: str


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "chapter"


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }
    )
    return session


def parse_mangadex_images(chapter_url: str) -> tuple[str, list[PageImage]]:
    match = re.search(r"/chapter/([a-f0-9-]{36})", chapter_url)
    if not match:
        raise ValueError(f"Could not extract chapter UUID from URL: {chapter_url}")
    chapter_id = match.group(1)

    session = get_session()

    chapter_resp = session.get(
        f"https://api.mangadex.org/chapter/{chapter_id}",
        params={"includes[]": "manga"},
        timeout=30,
    )
    chapter_resp.raise_for_status()
    chapter_data = chapter_resp.json().get("data", {})
    attributes = chapter_data.get("attributes", {})
    chapter_num = attributes.get("chapter") or ""

    title = f"mangadex-chapter-{chapter_num}" if chapter_num else "mangadex-chapter"
    for rel in chapter_data.get("relationships", []):
        if rel.get("type") == "manga":
            manga_title = (rel.get("attributes") or {}).get("title", {})
            title_str = manga_title.get("en") or next(iter(manga_title.values()), "")
            if title_str:
                title = f"{title_str} Ch.{chapter_num}" if chapter_num else title_str
            break

    athome_resp = session.get(
        f"https://api.mangadex.org/at-home/server/{chapter_id}",
        timeout=30,
    )
    athome_resp.raise_for_status()
    athome_data = athome_resp.json()

    base_url = athome_data["baseUrl"]
    chapter_hash = athome_data["chapter"]["hash"]
    filenames = athome_data["chapter"]["data"]

    pages: list[PageImage] = []
    for index, filename in enumerate(filenames, start=1):
        url = f"{base_url}/data/{chapter_hash}/{filename}"
        ext = Path(filename).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = ".png"
        pages.append(PageImage(index, url, f"page-{index:03d}{ext}"))

    if not pages:
        raise RuntimeError("No page images found from MangaDex API.")

    return title, pages


def parse_mangablaze_images(chapter_url: str) -> tuple[str, list[PageImage]]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    opts = ChromeOptions()
    for arg in "--headless=new --disable-gpu --no-sandbox --disable-dev-shm-usage --window-size=1920,1080".split():
        opts.add_argument(arg)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(chapter_url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".reading-content img, img.wp-manga-chapter-img"))
        )

        title = driver.title.strip() or "mangablaze-chapter"

        # try JS preloaded array first
        image_urls: list[str] = []
        try:
            image_urls = driver.execute_script("return window.chapter_preloaded_images || [];")
        except Exception:
            pass

        if not image_urls:
            imgs = driver.find_elements(By.CSS_SELECTOR, ".reading-content img, img.wp-manga-chapter-img")
            for img in imgs:
                src = img.get_attribute("data-src") or img.get_attribute("src") or ""
                src = src.strip()
                if src and not src.startswith("data:"):
                    image_urls.append(src)
    finally:
        driver.quit()

    if not image_urls:
        raise RuntimeError("No page images found on MangaBlaze page. The site structure may have changed.")

    pages: list[PageImage] = []
    for index, url in enumerate(image_urls, start=1):
        ext = Path(urlparse(url).path).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = ".jpg"
        pages.append(PageImage(index, url, f"page-{index:03d}{ext}"))

    return title, pages


def parse_weebcentral_images(chapter_url: str) -> tuple[str, list[PageImage]]:
    session = get_session()
    response = session.get(chapter_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "weebcentral-chapter"
    chapter_id = urlparse(chapter_url).path.rstrip("/").split("/")[-1]
    images_url = urljoin(chapter_url, f"/chapters/{chapter_id}/images")

    image_response = session.get(
        images_url,
        params={"is_prev": "False", "current_page": "1", "reading_style": "long_strip"},
        headers={"HX-Request": "true", "Referer": chapter_url},
        timeout=30,
    )
    image_response.raise_for_status()

    image_soup = BeautifulSoup(image_response.text, "html.parser")
    image_tags = image_soup.select("img[src]")
    pages: list[PageImage] = []
    for index, img in enumerate(image_tags, start=1):
        src = urljoin(chapter_url, img["src"])
        ext = Path(urlparse(src).path).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = ".png"
        pages.append(PageImage(index, src, f"page-{index:03d}{ext}"))

    if not pages:
        raise RuntimeError("No page images found. The site may have changed or blocked the image endpoint.")

    return title, pages


def parse_isekainonbiri_images(chapter_url: str) -> tuple[str, list[PageImage]]:
    session = get_session()
    response = session.get(chapter_url, timeout=30, headers={"Referer": chapter_url})
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "isekainonbiri-chapter"

    container = soup.select_one("div.reading-content")
    if container is None:
        raise RuntimeError("Reader container .reading-content not found. The site structure may have changed.")

    image_urls: list[str] = []
    for img in container.select("img"):
        src = (
            img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("srcset", "").split(",")[0].strip().split(" ")[0]
            or img.get("src")
            or ""
        ).strip()
        if src and not src.startswith("data:"):
            image_urls.append(src)

    if not image_urls:
        raise RuntimeError("No page images found on isekainonbirinouka page. The site structure may have changed.")

    pages: list[PageImage] = []
    for index, url in enumerate(image_urls, start=1):
        path = urlparse(url).path
        ext = Path(path).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            mime_match = re.search(r"[?&]mime=([a-zA-Z0-9]+)", url)
            ext = f".{mime_match.group(1).lower()}" if mime_match else ".jpg"
        pages.append(PageImage(index, url, f"page-{index:03d}{ext}"))

    return title, pages


def _unwrap_spoilerhat(url: str) -> str | None:
    if "spoilerhat.com" not in url:
        return None
    from urllib.parse import parse_qs, urlparse as _urlparse, unquote
    qs = parse_qs(_urlparse(url).query)
    inner = qs.get("url", [None])[0]
    return unquote(inner) if inner else None


def _fetch_image(session: requests.Session, url: str, target: Path) -> int:
    headers = {}
    if "mangafox.me" in url or "fanfox.net" in url:
        headers["Referer"] = "https://fanfox.net/"
    with session.get(url, stream=True, timeout=60, headers=headers) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    handle.write(chunk)
    return target.stat().st_size


def download_images(pages: Iterable[PageImage], output_dir: Path, workers: int = 8, quiet: bool = False) -> list[dict]:
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    page_list = list(pages)
    manifest_pages = [None] * len(page_list)

    def download_one(index: int, page: PageImage) -> tuple[int, dict]:
        target = images_dir / page.filename
        final_url = page.url
        if not target.exists() or target.stat().st_size == 0:
            session = get_session()
            size = 0
            try:
                size = _fetch_image(session, page.url, target)
            except Exception:
                size = 0
            if size == 0:
                fallback = _unwrap_spoilerhat(page.url)
                if fallback:
                    try:
                        if target.exists():
                            target.unlink()
                        size = _fetch_image(session, fallback, target)
                        if size > 0:
                            final_url = fallback
                    except Exception:
                        pass
            if size == 0:
                if target.exists():
                    target.unlink()
                raise RuntimeError(f"Empty/failed download for page {page.page}: {page.url}")
        return index, {"page": page.page, "url": final_url, "file": str(target)}

    def _iter(iterable, **kw):
        if quiet:
            return iterable
        return tqdm(iterable, **kw)

    if workers <= 1 or len(page_list) <= 1:
        for index, page in enumerate(_iter(page_list, desc="Downloading pages")):
            out_index, row = download_one(index, page)
            manifest_pages[out_index] = row
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(download_one, index, page) for index, page in enumerate(page_list)]
            for future in _iter(as_completed(futures), total=len(futures), desc=f"Downloading pages ({workers} workers)"):
                out_index, row = future.result()
                manifest_pages[out_index] = row

    return [row for row in manifest_pages if row is not None]


def save_data_url(data_url: str, target: Path) -> None:
    if not data_url.startswith("data:image/"):
        raise ValueError("Expected a data:image URL")
    _, payload = data_url.split(",", 1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(payload))


def image_files_from_folder(folder: Path) -> list[Path]:
    files = [path for path in folder.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(files, key=lambda path: path.name)


def _fit_image_size(image_path: Path, max_width: float, max_height: float) -> tuple[float, float]:
    with Image.open(image_path) as image:
        width, height = image.size
    scale = min(max_width / width, max_height / height)
    return width * scale, height * scale


def make_image_pdf(work_dir: Path, output_pdf: Path | None = None, translated: bool = True) -> Path:
    image_dir = work_dir / ("translated_images" if translated else "images")
    files = image_files_from_folder(image_dir)
    if not files:
        raise RuntimeError(f"No images found in {image_dir}")

    output_pdf = output_pdf or (work_dir / ("lens-translated.pdf" if translated else "images.pdf"))
    page_width, page_height = A4
    margin = 8 * mm
    max_width = page_width - margin * 2
    max_height = page_height - margin * 2

    doc = SimpleDocTemplate(
        str(output_pdf), pagesize=A4,
        rightMargin=margin, leftMargin=margin, topMargin=margin, bottomMargin=margin,
    )
    story = []
    for index, image_path in enumerate(files):
        width, height = _fit_image_size(image_path, max_width, max_height)
        story.append(PdfImage(str(image_path), width=width, height=height))
        if index != len(files) - 1:
            story.append(PageBreak())
    doc.build(story)
    return output_pdf


def make_long_strip_pdf(
    work_dir: Path,
    output_pdf: Path | None = None,
    translated: bool = True,
    chunk_size: int = 8,
    width_mm: float = 190,
    max_page_height_mm: float = 0,
) -> Path:
    image_dir = work_dir / ("translated_images" if translated else "images")
    files = image_files_from_folder(image_dir)
    if not files:
        raise RuntimeError(f"No images found in {image_dir}")

    output_pdf = output_pdf or (work_dir / ("lens-translated-long.pdf" if translated else "images-long.pdf"))
    margin = 6 * mm
    target_width = width_mm * mm
    page_width = target_width + margin * 2

    if max_page_height_mm > 0:
        max_height_pt = max_page_height_mm * mm
        chunks: list[list[Path]] = []
        current: list[Path] = []
        current_h = margin * 2
        for image_path in files:
            with Image.open(image_path) as image:
                w, h = image.size
            scaled_h = h * (target_width / w)
            if current and current_h + scaled_h > max_height_pt:
                chunks.append(current)
                current = []
                current_h = margin * 2
            current.append(image_path)
            current_h += scaled_h
        if current:
            chunks.append(current)
    else:
        chunks = [files] if chunk_size <= 0 else [files[i : i + chunk_size] for i in range(0, len(files), chunk_size)]

    pdf = canvas.Canvas(str(output_pdf))
    for chunk in chunks:
        scaled_sizes = []
        page_height = margin * 2
        for image_path in chunk:
            with Image.open(image_path) as image:
                width, height = image.size
            scale = target_width / width
            draw_width = target_width
            draw_height = height * scale
            scaled_sizes.append((image_path, draw_width, draw_height))
            page_height += draw_height

        pdf.setPageSize((page_width, page_height))
        y = page_height - margin
        for image_path, draw_width, draw_height in scaled_sizes:
            y -= draw_height
            pdf.drawImage(str(image_path), margin, y, width=draw_width, height=draw_height, preserveAspectRatio=True)
        pdf.showPage()

    pdf.save()
    return output_pdf


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
) -> list[dict]:
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
            "`Translate-image-manga-In-Page-main` exists and dependencies are installed."
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
                                logging.getLogger("manga_translate").warning(
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

    tasks = [asyncio.create_task(translate_one(index, row)) for index, row in enumerate(pages)]
    for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"Google Lens translate ({concurrency} workers)"):
        index, row = await task
        results[index] = row

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


def command_go(args) -> None:
    """Download + Google Lens translate + long-strip PDF (single command)."""
    if "mangadex.org" in args.url:
        title, pages = parse_mangadex_images(args.url)
    elif "mangablaze.com" in args.url:
        title, pages = parse_mangablaze_images(args.url)
    elif "isekainonbirinouka.com" in args.url:
        title, pages = parse_isekainonbiri_images(args.url)
    else:
        title, pages = parse_weebcentral_images(args.url)

    work_dir = Path(args.output or Path("output") / slugify(title))
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_pages = download_images(pages, work_dir, workers=args.download_workers)
    write_json(
        work_dir / "manifest.json",
        {"source": args.url, "title": title, "page_count": len(manifest_pages), "pages": manifest_pages},
    )
    print(f"Saved {len(manifest_pages)} images to {work_dir / 'images'}")

    results = asyncio.run(
        lens_translate_work_dir(
            work_dir, lang=args.lang, concurrency=args.lens_workers,
            verbose=args.verbose, max_retries=args.max_retries,
        )
    )
    ok = sum(1 for r in results if r.get("translated_file"))
    print(f"Lens: {ok}/{len(results)} translated.")
    output_pdf = make_long_strip_pdf(
        work_dir, None, translated=True, chunk_size=args.chunk_size, width_mm=args.width_mm
    )
    print(f"PDF: {output_pdf}")


def command_from_url(args) -> None:
    if "mangadex.org" in args.url:
        title, pages = parse_mangadex_images(args.url)
    elif "mangablaze.com" in args.url:
        title, pages = parse_mangablaze_images(args.url)
    elif "isekainonbirinouka.com" in args.url:
        title, pages = parse_isekainonbiri_images(args.url)
    else:
        title, pages = parse_weebcentral_images(args.url)
    work_dir = Path(args.output or Path("output") / slugify(title))
    work_dir.mkdir(parents=True, exist_ok=True)

    manifest_pages = download_images(pages, work_dir, workers=args.download_workers)
    write_json(
        work_dir / "manifest.json",
        {"source": args.url, "title": title, "page_count": len(manifest_pages), "pages": manifest_pages},
    )
    print(f"Saved {len(manifest_pages)} images to {work_dir / 'images'}")

    if args.lens_long_pdf:
        results = asyncio.run(
            lens_translate_work_dir(
                work_dir,
                lang=args.lang,
                limit=args.limit,
                force=args.force_lens,
                concurrency=args.lens_workers,
                verbose=args.verbose,
            )
        )
        ok = sum(1 for row in results if row.get("translated_file"))
        failed = len(results) - ok
        print(f"Lens translated {ok} page(s), failed {failed}. Metadata: {work_dir / 'lens_translations.json'}")
        output_pdf = make_long_strip_pdf(
            work_dir,
            Path(args.long_output) if args.long_output else None,
            translated=True,
            chunk_size=args.chunk_size,
            width_mm=args.width_mm,
        )
        print(f"Long PDF written to {output_pdf}")


def command_chapter_range(args) -> None:
    import queue
    import threading

    raw_base = args.base_url
    if raw_base.endswith("-"):
        base_url = raw_base
    else:
        base_url = raw_base.rstrip("/") + "/"
    failed_chapters: list[int] = []

    def parse_for(base: str, url: str):
        if "mangadex.org" in base:
            return parse_mangadex_images(url)
        if "mangablaze.com" in base:
            return parse_mangablaze_images(url)
        if "isekainonbirinouka.com" in base:
            return parse_isekainonbiri_images(url)
        return parse_weebcentral_images(url)

    ready: "queue.Queue[object]" = queue.Queue(maxsize=2)
    SENTINEL = object()

    def producer():
        for n in range(args.start, args.end + 1):
            chapter_url = f"{base_url}chapter-{n}/"
            try:
                title, pages = parse_for(base_url, chapter_url)
                chapter_slug = urlparse(chapter_url).path.strip("/").split("/")[-1] or f"chapter-{n}"
                if args.output_prefix:
                    work_dir = Path(f"{args.output_prefix}_{n}")
                else:
                    work_dir = Path("output") / chapter_slug
                work_dir.mkdir(parents=True, exist_ok=True)
                manifest_pages = download_images(pages, work_dir, workers=8, quiet=True)
                write_json(
                    work_dir / "manifest.json",
                    {"source": chapter_url, "title": title, "page_count": len(manifest_pages), "pages": manifest_pages},
                )
                ready.put({
                    "n": n, "url": chapter_url, "title": title,
                    "work_dir": work_dir, "chapter_slug": chapter_slug,
                    "downloaded": len(manifest_pages),
                })
            except Exception as exc:
                ready.put({"n": n, "url": chapter_url, "error": exc})
        ready.put(SENTINEL)

    producer_thread = threading.Thread(target=producer, daemon=True)
    producer_thread.start()

    bar = "─" * 60
    total = args.end - args.start + 1
    processed = 0

    while True:
        item = ready.get()
        if item is SENTINEL:
            break
        n = item["n"]
        processed += 1
        print(f"\n┌{bar}")
        print(f"│ 📖 Chapter {n}  ({processed}/{total})")
        print(f"│ {item['url']}")
        print(f"└{bar}")

        if "error" in item:
            print(f"  ❌ Parse/download failed: {item['error']}")
            failed_chapters.append(n)
            continue

        work_dir = item["work_dir"]
        chapter_slug = item["chapter_slug"]
        print(f"  📥 Downloaded {item['downloaded']} pages → {work_dir.name}/images")

        if args.lens_long_pdf:
            try:
                results = asyncio.run(
                    lens_translate_work_dir(
                        work_dir,
                        lang=args.lang,
                        force=False,
                        concurrency=4,
                        verbose=False,
                    )
                )
                ok = sum(1 for row in results if row.get("translated_file"))
                failed_pages = [int(r["page"]) for r in results if not r.get("translated_file")]

                if failed_pages:
                    print(f"  ⚠️  Lens: {ok}/{len(results)} OK · failed pages {failed_pages} → retrying...")
                    retry_results = asyncio.run(
                        lens_translate_work_dir(
                            work_dir,
                            lang=args.lang,
                            force=True,
                            concurrency=4,
                            verbose=False,
                            max_retries=3,
                            only_pages=set(failed_pages),
                        )
                    )
                    retry_ok = sum(1 for r in retry_results if r.get("translated_file"))
                    still_failed = [int(r["page"]) for r in retry_results if not r.get("translated_file")]
                    print(f"  🔁 Retry: {retry_ok}/{len(retry_results)} recovered" + (f" · still failing: {still_failed}" if still_failed else ""))
                    if still_failed:
                        failed_chapters.append(n)
                        continue
                else:
                    print(f"  ✅ Lens translated {ok}/{len(results)} pages")

                pdf_dir = Path("output") / "pdfs"
                pdf_dir.mkdir(parents=True, exist_ok=True)
                output_pdf = make_long_strip_pdf(
                    work_dir,
                    pdf_dir / f"{chapter_slug}.pdf",
                    translated=True,
                    chunk_size=args.chunk_size,
                    width_mm=args.width_mm,
                )
                print(f"  📄 PDF → {output_pdf}")
            except Exception as exc:
                print(f"  ❌ Lens/PDF failed: {exc}")
                failed_chapters.append(n)

    producer_thread.join(timeout=5)

    print(f"\n{'═' * 60}")
    ok_count = total - len(failed_chapters)
    print(f"  Done. {ok_count}/{total} chapters succeeded.")
    if failed_chapters:
        print(f"  ⚠️  Failed chapters: {failed_chapters}")
        print(f"  💡 Tip: run `lens-retry output/<chapter-slug>` to retry those")
    print(f"{'═' * 60}")


def process_single_url(
    url: str,
    output_dir: Path | None,
    lens_long_pdf: bool,
    lang: str,
    chunk_size: int,
    width_mm: float,
    lens_workers: int,
    download_workers: int,
    max_retries: int,
    verbose: bool,
) -> Path:
    if "mangadex.org" in url:
        title, pages = parse_mangadex_images(url)
    elif "mangablaze.com" in url:
        title, pages = parse_mangablaze_images(url)
    elif "isekainonbirinouka.com" in url:
        title, pages = parse_isekainonbiri_images(url)
    else:
        title, pages = parse_weebcentral_images(url)
    work_dir = output_dir or (Path("output") / slugify(title))
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_pages = download_images(pages, work_dir, workers=download_workers)
    write_json(
        work_dir / "manifest.json",
        {"source": url, "title": title, "page_count": len(manifest_pages), "pages": manifest_pages},
    )
    if lens_long_pdf:
        results = asyncio.run(
            lens_translate_work_dir(
                work_dir,
                lang=lang,
                concurrency=lens_workers,
                verbose=verbose,
                max_retries=max_retries,
            )
        )
        ok = sum(1 for row in results if row.get("translated_file"))
        failed = len(results) - ok
        print(f"  Lens translated {ok} page(s), failed {failed}.")
        make_long_strip_pdf(work_dir, None, translated=True, chunk_size=chunk_size, width_mm=width_mm)
    return work_dir


def command_batch(args) -> None:
    urls: list[str] = []
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    urls.extend(args.urls or [])
    if not urls:
        raise RuntimeError("No URLs provided. Pass --file <path> or extra positional URLs.")

    print(f"Batch processing {len(urls)} URL(s)")
    failures: list[tuple[str, str]] = []
    for index, url in enumerate(urls, start=1):
        print(f"\n[{index}/{len(urls)}] {url}")
        try:
            process_single_url(
                url=url,
                output_dir=None,
                lens_long_pdf=args.lens_long_pdf,
                lang=args.lang,
                chunk_size=args.chunk_size,
                width_mm=args.width_mm,
                lens_workers=args.lens_workers,
                download_workers=args.download_workers,
                max_retries=args.max_retries,
                verbose=args.verbose,
            )
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            failures.append((url, str(exc)))

    print(f"\nDone. {len(urls) - len(failures)} succeeded, {len(failures)} failed.")
    if failures:
        for url, err in failures:
            print(f"  FAIL {url}: {err}")


def command_lens(args) -> None:
    work_dir = Path(args.work_dir)
    results = asyncio.run(
        lens_translate_work_dir(
            work_dir,
            lang=args.lang,
            limit=args.limit,
            force=args.force,
            concurrency=args.workers,
            verbose=args.verbose,
            max_retries=args.max_retries,
        )
    )
    ok = sum(1 for row in results if row.get("translated_file"))
    failed = len(results) - ok
    print(f"Lens translated {ok} page(s), failed {failed}. Metadata: {work_dir / 'lens_translations.json'}")
    if args.make_pdf:
        output_pdf = make_image_pdf(work_dir, Path(args.output) if args.output else None, translated=True)
        print(f"PDF written to {output_pdf}")
    if args.make_long_pdf:
        output_pdf = make_long_strip_pdf(
            work_dir,
            Path(args.long_output) if args.long_output else None,
            translated=True,
            chunk_size=args.chunk_size,
            width_mm=args.width_mm,
        )
        print(f"Long PDF written to {output_pdf}")


def command_lens_retry(args) -> None:
    work_dir = Path(args.work_dir)
    failed_path = work_dir / "lens_failed.json"
    failed_pages = read_json(failed_path, [])
    if not failed_pages:
        print("No failed pages to retry.")
        return
    print(f"Retrying {len(failed_pages)} failed page(s): {failed_pages}")
    results = asyncio.run(
        lens_translate_work_dir(
            work_dir,
            lang=args.lang,
            force=True,
            concurrency=args.workers,
            verbose=args.verbose,
            max_retries=args.max_retries,
            only_pages=set(int(p) for p in failed_pages),
        )
    )
    ok = sum(1 for row in results if row.get("translated_file"))
    failed = len(results) - ok
    print(f"Retry: {ok} succeeded, {failed} still failing.")


def command_make_image_pdf(args) -> None:
    output_pdf = make_image_pdf(
        Path(args.work_dir),
        Path(args.output) if args.output else None,
        translated=not args.original,
    )
    print(f"PDF written to {output_pdf}")


def command_make_long_pdf(args) -> None:
    output_pdf = make_long_strip_pdf(
        Path(args.work_dir),
        Path(args.output) if args.output else None,
        translated=not args.original,
        chunk_size=args.chunk_size,
        width_mm=args.width_mm,
        max_page_height_mm=getattr(args, "max_page_height_mm", 0),
    )
    print(f"Long PDF written to {output_pdf}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download manga pages, translate to Thai via Google Lens, and build a reading PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            r"""
            Examples:
              python manga_translate.py go "https://mangadex.org/chapter/..."
              python manga_translate.py from-url "https://weebcentral.com/chapters/..." --lens-long-pdf
              python manga_translate.py chapter-range "https://mangablaze.com/manga/<slug>/" 1 5 --lens-long-pdf
              python manga_translate.py batch --file urls.txt --lens-long-pdf
              python manga_translate.py lens ".\output\chapter-id" --make-long-pdf
              python manga_translate.py lens-retry ".\output\chapter-id"
              python manga_translate.py make-long-pdf ".\output\chapter-id" --max-page-height-mm 800
            """
        ),
    )
    subparsers = parser.add_subparsers(required=True)

    from_url = subparsers.add_parser("from-url")
    from_url.add_argument("url")
    from_url.add_argument("--output")
    from_url.add_argument("--lens-long-pdf", action="store_true")
    from_url.add_argument("--lang", default="th")
    from_url.add_argument("--force-lens", action="store_true")
    from_url.add_argument("--lens-workers", type=int, default=4)
    from_url.add_argument("--download-workers", type=int, default=8)
    from_url.add_argument("--chunk-size", type=int, default=8)
    from_url.add_argument("--width-mm", type=float, default=190)
    from_url.add_argument("--long-output")
    from_url.add_argument("--verbose", action="store_true")
    from_url.add_argument("--limit", type=int)
    from_url.set_defaults(func=command_from_url)

    chapter_range = subparsers.add_parser("chapter-range", help="Download and translate a range of chapters")
    chapter_range.add_argument("base_url", help="Base manga URL e.g. https://mangablaze.com/manga/wistoria-wand-and-sword/")
    chapter_range.add_argument("start", type=int, help="First chapter number")
    chapter_range.add_argument("end", type=int, help="Last chapter number (inclusive)")
    chapter_range.add_argument("--output-prefix", default=None, help="Output folder prefix, e.g. .\\output\\chapter (default: output/chapter)")
    chapter_range.add_argument("--lens-long-pdf", action="store_true")
    chapter_range.add_argument("--lang", default="th")
    chapter_range.add_argument("--chunk-size", type=int, default=8)
    chapter_range.add_argument("--width-mm", type=float, default=190)
    chapter_range.set_defaults(func=command_chapter_range)

    go = subparsers.add_parser("go", help="Download a chapter + Lens translate + build long PDF (one shot)")
    go.add_argument("url")
    go.add_argument("--output")
    go.add_argument("--lang", default="th")
    go.add_argument("--download-workers", type=int, default=8)
    go.add_argument("--lens-workers", type=int, default=4)
    go.add_argument("--max-retries", type=int, default=2)
    go.add_argument("--chunk-size", type=int, default=8)
    go.add_argument("--width-mm", type=float, default=190)
    go.add_argument("--verbose", action="store_true")
    go.set_defaults(func=command_go)

    batch = subparsers.add_parser("batch", help="Process many chapter URLs (from --file or args)")
    batch.add_argument("urls", nargs="*", help="One or more chapter URLs")
    batch.add_argument("--file", help="Path to a text file with one URL per line (# for comments)")
    batch.add_argument("--lens-long-pdf", action="store_true")
    batch.add_argument("--lang", default="th")
    batch.add_argument("--chunk-size", type=int, default=8)
    batch.add_argument("--width-mm", type=float, default=190)
    batch.add_argument("--lens-workers", type=int, default=4)
    batch.add_argument("--download-workers", type=int, default=8)
    batch.add_argument("--max-retries", type=int, default=2)
    batch.add_argument("--verbose", action="store_true")
    batch.set_defaults(func=command_batch)

    lens = subparsers.add_parser("lens")
    lens.add_argument("work_dir")
    lens.add_argument("--lang", default="th")
    lens.add_argument("--limit", type=int)
    lens.add_argument("--force", action="store_true")
    lens.add_argument("--workers", type=int, default=4)
    lens.add_argument("--verbose", action="store_true")
    lens.add_argument("--make-pdf", action="store_true")
    lens.add_argument("--make-long-pdf", action="store_true")
    lens.add_argument("--chunk-size", type=int, default=8)
    lens.add_argument("--width-mm", type=float, default=190)
    lens.add_argument("--output")
    lens.add_argument("--long-output")
    lens.add_argument("--max-retries", type=int, default=2)
    lens.set_defaults(func=command_lens)

    lens_retry = subparsers.add_parser("lens-retry", help="Retry pages listed in lens_failed.json")
    lens_retry.add_argument("work_dir")
    lens_retry.add_argument("--lang", default="th")
    lens_retry.add_argument("--workers", type=int, default=4)
    lens_retry.add_argument("--max-retries", type=int, default=3)
    lens_retry.add_argument("--verbose", action="store_true")
    lens_retry.set_defaults(func=command_lens_retry)

    image_pdf = subparsers.add_parser("make-image-pdf")
    image_pdf.add_argument("work_dir")
    image_pdf.add_argument("--output")
    image_pdf.add_argument("--original", action="store_true")
    image_pdf.set_defaults(func=command_make_image_pdf)

    long_pdf = subparsers.add_parser("make-long-pdf")
    long_pdf.add_argument("work_dir")
    long_pdf.add_argument("--output")
    long_pdf.add_argument("--original", action="store_true")
    long_pdf.add_argument("--chunk-size", type=int, default=8)
    long_pdf.add_argument("--width-mm", type=float, default=190)
    long_pdf.add_argument("--max-page-height-mm", type=float, default=0,
                         help="If >0, auto-pack images until reaching this page height instead of fixed chunk-size")
    long_pdf.set_defaults(func=command_make_long_pdf)

    return parser


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
