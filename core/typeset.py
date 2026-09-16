"""Manga Thai Typesetting Engine.

Handles Thai word segmentation, natural line wrapping, and proper font rendering
for manga speech bubbles without vowel stacking or clipped text.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

LOGGER = logging.getLogger("manga.typeset")

# Windows standard Thai-supporting fonts
DEFAULT_WINDOWS_FONTS = [
    r"C:\Windows\Fonts\LeelawUI.ttf",       # Leelawadee UI
    r"C:\Windows\Fonts\leelawad.ttf",      # Leelawadee
    r"C:\Windows\Fonts\tahoma.ttf",        # Tahoma
    r"C:\Windows\Fonts\angsana.ttc",       # Angsana New
    r"C:\Windows\Fonts\cordia.ttc",        # Cordia New
]


def get_thai_font(size: int = 24, font_path: Optional[str] = None) -> ImageFont.FreeTypeFont:
    """Load an optimal Thai-compatible TrueType font."""
    if font_path and Path(font_path).exists():
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            pass

    for candidate in DEFAULT_WINDOWS_FONTS:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                continue

    # Fallback to PIL default font
    return ImageFont.load_default()


def tokenize_thai(text: str) -> List[str]:
    """Segment Thai text into natural word tokens using pythainlp or fallback."""
    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(text, engine="newmm")
        return [t for t in tokens if t]
    except Exception:
        # Fallback: break by whitespace or single characters
        return text.split()


def wrap_thai_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> List[str]:
    """Wrap Thai text into lines that fit within max_width using syllabic/word boundaries."""
    paragraphs = text.split("\n")
    lines: List[str] = []

    for para in paragraphs:
        tokens = tokenize_thai(para)
        current_line = ""

        for token in tokens:
            test_line = current_line + token
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]

            if line_w <= max_width or not current_line:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = token

        if current_line:
            lines.append(current_line)

    return lines


def render_thai_text_box(
    img: Image.Image,
    text: str,
    box: Tuple[int, int, int, int],  # (x1, y1, x2, y2)
    font_size: Optional[int] = None,
    color: str = "#000000",
    stroke_width: int = 1,
    stroke_color: str = "#FFFFFF",
) -> Image.Image:
    """Render wrapped and centered Thai text inside a bounding box on the image."""
    x1, y1, x2, y2 = box
    box_w = max(10, x2 - x1)
    box_h = max(10, y2 - y1)

    draw = ImageDraw.Draw(img)

    # Determine suitable font size if not fixed
    if not font_size:
        # Heuristic font size based on box dimensions and text length
        text_len = max(1, len(text.replace("\n", "")))
        est_area_per_char = (box_w * box_h) / text_len
        base_size = int(est_area_per_char ** 0.5 * 0.9)
        font_size = max(14, min(36, base_size))

    font = get_thai_font(size=font_size)
    lines = wrap_thai_text(text, font, box_w, draw)

    if not lines:
        return img

    # Calculate total text block height
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    line_spacing = 4
    total_h = sum(line_heights) + (len(lines) - 1) * line_spacing

    # Center vertically inside the box
    start_y = y1 + max(0, (box_h - total_h) // 2)

    current_y = start_y
    for i, line in enumerate(lines):
        w = line_widths[i]
        # Center horizontally inside the box
        line_x = x1 + max(0, (box_w - w) // 2)

        draw.text(
            (line_x, current_y),
            line,
            font=font,
            fill=color,
            stroke_width=stroke_width,
            stroke_color=stroke_color,
        )
        current_y += line_heights[i] + line_spacing

    return img
