"""Manga Bubble Cleaner & Inpainter.

Eliminates dirty cleaning artifacts, ghost text, and harsh rectangular bounding boxes
from translated manga pages by leveraging OpenCV inpainting and intelligent foreground blending.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple, Optional

import cv2
import numpy as np

LOGGER = logging.getLogger("manga.cleaner")


def load_image(path: Path | str) -> np.ndarray:
    """Load an image using cv2 with utf-8 / unicode path safety on Windows."""
    path_str = str(path)
    # Using cv2.imdecode to handle arbitrary Windows paths safely
    data = np.fromfile(path_str, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not load image from: {path_str}")
    return img


def save_image(img: np.ndarray, path: Path | str) -> None:
    """Save an image using cv2 with unicode path safety on Windows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower() or ".png"
    success, enc = cv2.imencode(suffix, img)
    if not success:
        raise ValueError(f"Failed to encode image to {suffix}")
    enc.tofile(str(path))


def create_diff_mask(
    original: np.ndarray,
    lens: np.ndarray,
    diff_thresh: int = 15,
    dilate_px: int = 7,
) -> np.ndarray:
    """Generate a binary mask identifying speech bubbles and modified regions.
    
    Compares the original raw manga page with the Google Lens rendered image.
    Any pixel modification (white boxes, replaced text) is captured, thresholded,
    and dilated to envelop edge halos and ghost text.
    """
    # Ensure same dimensions
    if original.shape[:2] != lens.shape[:2]:
        lens = cv2.resize(lens, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_AREA)

    # Color difference
    diff = cv2.absdiff(original, lens)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

    # Threshold to isolate altered areas
    _, thresh = cv2.threshold(diff_gray, diff_thresh, 255, cv2.THRESH_BINARY)

    # Morphological closing to fill small gaps inside text and boxes
    close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, close_k)

    # Dilate outward to cover ghosting, text strokes, and bounding box fringes
    if dilate_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px, dilate_px))
        mask = cv2.dilate(closed, kernel, iterations=1)
    else:
        mask = closed

    return mask


def inpaint_bubble_background(
    original: np.ndarray,
    mask: np.ndarray,
    radius: int = 7,
    method: str = "telea",
) -> np.ndarray:
    """Inpaint the original image using the mask to cleanly restore bubble backgrounds.
    
    This erases original Japanese/English characters using surrounding speech bubble
    colors/gradients, leaving zero ghost text or rectangular patches.
    """
    flag = cv2.INPAINT_TELEA if method.lower() == "telea" else cv2.INPAINT_NS
    cleaned = cv2.inpaint(original, mask, inpaintRadius=radius, flags=flag)
    return cleaned


def extract_text_foreground(
    lens: np.ndarray,
    mask: np.ndarray,
    dark_thresh: int = 180,
) -> Tuple[np.ndarray, np.ndarray]:
    """Extract only the sharp, translated text foreground from the Lens image.
    
    Returns:
        (text_rgb, alpha_channel)
    Where alpha is 1.0 on dark text strokes and 0.0 on the white bounding box background.
    """
    lens_gray = cv2.cvtColor(lens, cv2.COLOR_BGR2GRAY)

    # Only inspect within regions where Lens changed the image
    in_box = mask > 0

    # Text is dark strokes inside the modified region
    # Any white patch pixel (usually > 200) has near-zero alpha
    alpha = np.zeros(lens_gray.shape, dtype=np.float32)

    # Smooth linear gradient from dark_thresh down to 50
    # Pixels darker than dark_thresh get scaled alpha
    dark_mask = (lens_gray < dark_thresh) & in_box
    alpha[dark_mask] = (dark_thresh - lens_gray[dark_mask].astype(np.float32)) / float(dark_thresh)
    alpha = np.clip(alpha * 1.3, 0.0, 1.0)  # Boost text contrast slightly

    # Smooth the edges of the font strokes for crisp anti-aliasing
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)

    return lens, alpha


def blend_cleaned_page(
    original: np.ndarray,
    lens: np.ndarray,
    diff_thresh: int = 15,
    dilate_px: int = 7,
    inpaint_radius: int = 7,
) -> np.ndarray:
    """End-to-end composite:
    1. Inpaint original image to eliminate ghost text and restore clean bubble background.
    2. Extract crisp translated text from Lens image without any white bounding box.
    3. Seamlessly blend translated text onto the restored bubble background.
    """
    if original.shape[:2] != lens.shape[:2]:
        lens = cv2.resize(lens, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_AREA)

    # 1. Mask modified areas (speech bubbles / text)
    mask = create_diff_mask(original, lens, diff_thresh=diff_thresh, dilate_px=dilate_px)

    if cv2.countNonZero(mask) == 0:
        # No differences found, return original or lens
        return original.copy()

    # 2. Inpaint the original background to erase original text & create clean canvas
    clean_bg = inpaint_bubble_background(original, mask, radius=inpaint_radius)

    # 3. Extract translated foreground text with anti-aliasing alpha
    text_rgb, alpha = extract_text_foreground(lens, mask)

    # 4. Alpha composite text onto clean background: result = text * alpha + bg * (1 - alpha)
    alpha_3d = np.repeat(alpha[:, :, np.newaxis], 3, axis=2)
    composite = (text_rgb.astype(np.float32) * alpha_3d + clean_bg.astype(np.float32) * (1.0 - alpha_3d))
    composite = np.clip(composite, 0, 255).astype(np.uint8)

    return composite


def clean_page_file(
    original_path: Path | str,
    lens_path: Path | str,
    output_path: Path | str | None = None,
) -> Path:
    """Read original and lens images, apply bubble inpainting and clean blend, and save."""
    orig_p = Path(original_path)
    lens_p = Path(lens_path)
    out_p = Path(output_path) if output_path else lens_p

    orig_img = load_image(orig_p)
    lens_img = load_image(lens_p)

    cleaned = blend_cleaned_page(orig_img, lens_img)
    save_image(cleaned, out_p)
    LOGGER.info(f"Cleaned page saved to: {out_p}")
    return out_p
