"""MangaDex chapter parser — uses the public MangaDex API."""
from __future__ import annotations

import re
from pathlib import Path

import requests

from core.models import IMAGE_EXTENSIONS, PageImage
from core.parsers.base import BaseParser, register


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
    return session


@register
class MangaDexParser(BaseParser):
    name = "mangadex"
    domains = ["mangadex.org"]

    def parse(self, url: str) -> tuple[str, list[PageImage]]:
        match = re.search(r"/chapter/([a-f0-9-]{36})", url)
        if not match:
            raise ValueError(f"Could not extract chapter UUID from URL: {url}")
        chapter_id = match.group(1)

        session = _get_session()

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
            img_url = f"{base_url}/data/{chapter_hash}/{filename}"
            ext = Path(filename).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                ext = ".png"
            pages.append(PageImage(index, img_url, f"page-{index:03d}{ext}"))

        if not pages:
            raise RuntimeError("No page images found from MangaDex API.")

        return title, pages
