"""MangaBlaze chapter parser — Selenium headless Chrome."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from core.models import IMAGE_EXTENSIONS, PageImage
from core.parsers.base import BaseParser, register


@register
class MangaBlazeParser(BaseParser):
    name = "mangablaze"
    domains = ["mangablaze.com"]

    def parse(self, url: str) -> tuple[str, list[PageImage]]:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        opts = ChromeOptions()
        for arg in "--headless=new --disable-gpu --no-sandbox --disable-dev-shm-usage --window-size=1920,1080".split():
            opts.add_argument(arg)
        opts.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )

        driver = webdriver.Chrome(options=opts)
        try:
            driver.get(url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".reading-content img, img.wp-manga-chapter-img"))
            )

            title = driver.title.strip() or "mangablaze-chapter"

            # Try JS preloaded array first
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
        for index, img_url in enumerate(image_urls, start=1):
            ext = Path(urlparse(img_url).path).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                ext = ".jpg"
            pages.append(PageImage(index, img_url, f"page-{index:03d}{ext}"))

        return title, pages
