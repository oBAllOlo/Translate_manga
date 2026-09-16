"""IsekaiNonbiri chapter parser — HTTP scraping."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

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
class IsekaiNonbiriParser(BaseParser):
    name = "isekainonbiri"
    domains = ["isekainonbirinouka.com"]

    def parse(self, url: str) -> tuple[str, list[PageImage]]:
        session = _get_session()
        response = session.get(url, timeout=30, headers={"Referer": url})
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
        for index, img_url in enumerate(image_urls, start=1):
            path = urlparse(img_url).path
            ext = Path(path).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                mime_match = re.search(r"[?&]mime=([a-zA-Z0-9]+)", img_url)
                ext = f".{mime_match.group(1).lower()}" if mime_match else ".jpg"
            pages.append(PageImage(index, img_url, f"page-{index:03d}{ext}"))

        return title, pages
