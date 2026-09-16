"""Image downloader — fetch manga page images to disk."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote
from urllib.parse import urlparse as _urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

from core.models import PageImage


def _get_session() -> requests.Session:
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
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=16, pool_maxsize=32)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _unwrap_spoilerhat(url: str) -> str | None:
    """Extract the real image URL from a spoilerhat.com proxy URL."""
    if "spoilerhat.com" not in url:
        return None
    qs = parse_qs(_urlparse(url).query)
    inner = qs.get("url", [None])[0]
    return unquote(inner) if inner else None


def _mangadex_fallback(url: str) -> str | None:
    """If url is from a mangadex at-home node (*.mangadex.network), return official uploads.mangadex.org URL."""
    if "mangadex.network" in url:
        parsed = _urlparse(url)
        return f"https://uploads.mangadex.org{parsed.path}"
    return None


def _fetch_image(session: requests.Session, url: str, target: Path, max_retries: int = 2) -> int:
    """Download a single image and return bytes written."""
    headers = {}
    if "mangafox.me" in url or "fanfox.net" in url:
        headers["Referer"] = "https://fanfox.net/"
    elif "mangadex" in url:
        headers["Referer"] = "https://mangadex.org/"
    elif "weebcentral" in url:
        headers["Referer"] = "https://weebcentral.com/"

    for attempt in range(1, max_retries + 1):
        try:
            with session.get(url, stream=True, timeout=45, headers=headers) as response:
                if response.status_code != 200:
                    # e.g. 404 on at-home node -> return 0 immediately so fallback is tried
                    return 0
                with target.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            handle.write(chunk)
            size = target.stat().st_size
            if size > 0:
                return size
        except Exception:
            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass
            if attempt < max_retries:
                time.sleep(0.5 * attempt)
    return 0


def download_images(
    pages: Iterable[PageImage],
    output_dir: Path,
    workers: int = 8,
    quiet: bool = False,
) -> list[dict]:
    """Download all *pages* into ``output_dir/images/`` and return manifest rows."""
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    page_list = list(pages)
    manifest_pages: list[dict | None] = [None] * len(page_list)

    def download_one(index: int, page: PageImage, session: requests.Session) -> tuple[int, dict]:
        target = images_dir / page.filename
        final_url = page.url
        if not target.exists() or target.stat().st_size == 0:
            size = 0

            # 1. Try primary URL
            try:
                size = _fetch_image(session, page.url, target)
            except Exception:
                size = 0

            # 2. Try MangaDex uploads fallback if primary URL is from an at-home node
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

            # 3. Try spoilerhat proxy unwrap if applicable
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

            # 4. If still failed, retry once with backoff
            if size == 0:
                time.sleep(1.0)
                try:
                    if target.exists():
                        target.unlink()
                    size = _fetch_image(session, final_url, target)
                except Exception:
                    pass

            if size == 0:
                if target.exists():
                    try:
                        target.unlink()
                    except OSError:
                        pass
                raise RuntimeError(f"Empty/failed download for page {page.page}: {page.url}")
        return index, {"page": page.page, "url": final_url, "file": str(target)}

    def _iter(iterable, **kw):
        if quiet:
            return iterable
        return tqdm(iterable, **kw)

    session = _get_session()
    if workers <= 1 or len(page_list) <= 1:
        for index, page in enumerate(_iter(page_list, desc="Downloading pages")):
            out_index, row = download_one(index, page, session)
            manifest_pages[out_index] = row
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(download_one, index, page, session) for index, page in enumerate(page_list)]
            for future in _iter(as_completed(futures), total=len(futures), desc=f"Downloading pages ({workers} workers)"):
                out_index, row = future.result()
                manifest_pages[out_index] = row

    return [row for row in manifest_pages if row is not None]
