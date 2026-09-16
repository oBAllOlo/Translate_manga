"""WeebCentral chapter parser — HTTP scraping with HTMX headers."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin, urlparse

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
class WeebCentralParser(BaseParser):
    name = "weebcentral"
    domains = ["weebcentral.com"]

    def parse(self, url: str) -> tuple[str, list[PageImage]]:
        session = _get_session()
        response = session.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else "weebcentral-chapter"
        chapter_id = urlparse(url).path.rstrip("/").split("/")[-1]
        images_url = urljoin(url, f"/chapters/{chapter_id}/images")

        image_response = session.get(
            images_url,
            params={"is_prev": "False", "current_page": "1", "reading_style": "long_strip"},
            headers={"HX-Request": "true", "Referer": url},
            timeout=30,
        )
        image_response.raise_for_status()

        image_soup = BeautifulSoup(image_response.text, "html.parser")
        image_tags = image_soup.select("img[src]")
        pages: list[PageImage] = []
        for index, img in enumerate(image_tags, start=1):
            src = urljoin(url, img["src"])
            ext = Path(urlparse(src).path).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                ext = ".png"
            pages.append(PageImage(index, src, f"page-{index:03d}{ext}"))

        if not pages:
            raise RuntimeError("No page images found. The site may have changed or blocked the image endpoint.")

        return title, pages
