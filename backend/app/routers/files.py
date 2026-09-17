"""Static file serving for images and PDFs."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

OUTPUT_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "output"

router = APIRouter(tags=["files"])


@router.get("/output/{filepath:path}")
async def serve_output(filepath: str):
    """Serve files from the output directory."""
    output_root = OUTPUT_ROOT.resolve()
    target = (OUTPUT_ROOT / filepath).resolve()
    # Security: ensure the resolved path is strictly contained under OUTPUT_ROOT
    try:
        if not target.is_relative_to(output_root):
            return Response(status_code=403)
    except AttributeError:
        import os
        if not str(target).startswith(str(output_root) + os.sep):
            return Response(status_code=403)
    if not target.exists() or not target.is_file():
        return Response(status_code=404)
    return FileResponse(target)
