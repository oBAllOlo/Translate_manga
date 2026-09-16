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
    target = (OUTPUT_ROOT / filepath).resolve()
    # Security: ensure the resolved path is still under OUTPUT_ROOT
    if not str(target).startswith(str(OUTPUT_ROOT.resolve())):
        return Response(status_code=403)
    if not target.exists() or not target.is_file():
        return Response(status_code=404)
    return FileResponse(target)
