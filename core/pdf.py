"""PDF generation — long-strip and per-page layouts."""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import PageBreak, SimpleDocTemplate

from core.models import IMAGE_EXTENSIONS


def image_files_from_folder(folder: Path) -> list[Path]:
    """Return sorted image files from *folder*."""
    files = [path for path in folder.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(files, key=lambda path: path.name)


def _fit_image_size(image_path: Path, max_width: float, max_height: float) -> tuple[float, float]:
    """Scale an image to fit within *max_width* × *max_height*."""
    with Image.open(image_path) as image:
        width, height = image.size
    scale = min(max_width / width, max_height / height)
    return width * scale, height * scale


def make_image_pdf(
    work_dir: Path,
    output_pdf: Path | None = None,
    translated: bool = True,
) -> Path:
    """Generate a one-image-per-page A4 PDF."""
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
    """Generate a long-strip PDF where multiple images stack vertically."""
    image_dir = work_dir / ("translated_images" if translated else "images")
    files = image_files_from_folder(image_dir)
    if not files:
        raise RuntimeError(f"No images found in {image_dir}")

    output_pdf = output_pdf or (work_dir / ("lens-translated-long.pdf" if translated else "images-long.pdf"))
    margin = 6 * mm
    target_width = width_mm * mm
    page_width = target_width + margin * 2

    # Pre-cache all image dimensions in a single I/O pass to avoid reading each
    # file twice (once for chunk sizing, once during draw).
    image_sizes: dict[Path, tuple[int, int]] = {}
    for image_path in files:
        with Image.open(image_path) as img:
            image_sizes[image_path] = img.size

    if max_page_height_mm > 0:
        max_height_pt = max_page_height_mm * mm
        chunks: list[list[Path]] = []
        current: list[Path] = []
        current_h = margin * 2
        for image_path in files:
            w, h = image_sizes[image_path]
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
            width, height = image_sizes[image_path]
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

