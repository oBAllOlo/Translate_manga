"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.app.models.database import init_db
from backend.app.routers import jobs, chapters, files
from backend.app.ws.progress import manager

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path(__file__).resolve().parent.parent.parent / "output"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    OUTPUT_ROOT.mkdir(exist_ok=True)
    await init_db()
    logger.info("Manga Translate API ready")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Manga Translate API",
    description="แปลมังงะอังกฤษเป็นไทยด้วย Google Lens",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow Vite dev server (localhost:5173) and any local origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(jobs.router)
app.include_router(chapters.router)
app.include_router(files.router)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Frontend SPA static serving (when built)
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Exclude API, WS, and Output paths
        if full_path.startswith(("api", "ws", "output")):
            return {"detail": "Not found"}
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"detail": "Frontend not built"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
