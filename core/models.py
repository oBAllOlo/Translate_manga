"""Shared data models and utility helpers."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class PageImage:
    """A single page image with its download URL."""
    page: int
    url: str
    filename: str


def slugify(value: str) -> str:
    """Convert a string to a URL-safe slug."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "chapter"


def read_json(path: Path, default):
    """Read a JSON file, returning *default* if it doesn't exist."""
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    """Write *data* as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_page_text(row: dict | None) -> str:
    """Safely extract Thai/translated text from a translation row."""
    if not isinstance(row, dict):
        return ""
    return str(row.get("thai") or row.get("text") or "").strip()


def resolve_safe_chapter_dir(name: str, root: Path) -> Path:
    """Safely resolve and validate a chapter directory path under root.

    Raises ValueError if the name contains invalid characters, is empty,
    or attempts directory traversal outside of root.
    """
    cleaned = (name or "").strip()
    if not cleaned or ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise ValueError(f"Invalid chapter identifier: {name!r}")
    target = (root / cleaned).resolve()
    root_resolved = root.resolve()
    try:
        is_safe = target != root_resolved and target.is_relative_to(root_resolved)
    except AttributeError:
        import os
        is_safe = target != root_resolved and str(target).startswith(str(root_resolved) + os.sep)
    if not is_safe:
        raise ValueError(f"Chapter path escapes output directory: {name!r}")
    return target


