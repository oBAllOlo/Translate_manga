"""Job API endpoints."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter

from backend.app.models.database import get_db, get_all_jobs, insert_job
from backend.app.models.schemas import JobCreate, RangeJobCreate, JobResponse
from backend.app.services.job_runner import run_single_job, run_range_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs():
    db = await get_db()
    try:
        jobs = await get_all_jobs(db, limit=20)
        active = any(j.get("status") not in ("done", "error") for j in jobs)
        return {"jobs": jobs, "active": active}
    finally:
        await db.close()


@router.post("", status_code=201)
async def create_job(body: JobCreate):
    url = body.url.strip()
    if not url:
        return {"error": "url required"}, 400
    job_id = uuid.uuid4().hex[:8]
    db = await get_db()
    try:
        await insert_job(db, job_id, url)
    finally:
        await db.close()
    asyncio.create_task(run_single_job(job_id, url, body.chunk, body.concurrency))
    return {"id": job_id}


@router.post("/range", status_code=201)
async def create_range_job(body: RangeJobCreate):
    base_url = body.base_url.strip()
    if not base_url:
        return {"error": "base_url is required"}, 400
    if body.start > body.end:
        return {"error": f"start ({body.start}) > end ({body.end})"}, 400
    if body.start < 1:
        return {"error": "start must be >= 1"}, 400

    job_id = uuid.uuid4().hex[:8]
    db = await get_db()
    try:
        await insert_job(db, job_id, f"{base_url} [ch {body.start}-{body.end}]", is_range=True)
    finally:
        await db.close()
    asyncio.create_task(run_range_job(job_id, base_url, body.start, body.end, body.chunk, body.concurrency))
    return {"id": job_id}


@router.delete("")
@router.delete("/")
async def delete_completed_jobs():
    """Clear all completed or errored jobs."""
    db = await get_db()
    try:
        await db.execute("DELETE FROM jobs WHERE status IN ('done', 'error')")
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """Delete a single job by id."""
    db = await get_db()
    try:
        await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

