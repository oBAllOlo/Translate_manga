"""Job API endpoints."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.app.models.database import get_db, get_all_jobs, insert_job
from backend.app.models.schemas import JobCreate, RangeJobCreate, JobResponse
from backend.app.services.job_runner import (
    run_single_job,
    run_range_job,
    register_job_task,
    cancel_job_task,
    cancel_all_job_tasks,
)
from backend.app.ws.progress import manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs():
    db = await get_db()
    try:
        jobs = await get_all_jobs(db, limit=50)
        active = any(j.get("status") not in ("done", "error") for j in jobs)
        return {"jobs": jobs, "active": active}
    finally:
        await db.close()


MAX_CHAPTER_RANGE = 50


@router.post("", status_code=201)
async def create_job(body: JobCreate):
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "url required")

    try:
        from core.parsers import get_parser
        get_parser(url)
    except Exception as exc:
        raise HTTPException(400, str(exc))

    job_id = uuid.uuid4().hex[:8]
    db = await get_db()
    try:
        await insert_job(db, job_id, url)
    finally:
        await db.close()
    task = asyncio.create_task(run_single_job(job_id, url, body.chunk, body.concurrency))
    register_job_task(job_id, task)
    return {"id": job_id}


@router.post("/range", status_code=201)
async def create_range_job(body: RangeJobCreate):
    base_url = body.base_url.strip()
    if not base_url:
        raise HTTPException(400, "base_url is required")
    if body.start > body.end:
        raise HTTPException(400, f"start ({body.start}) > end ({body.end})")
    if body.start < 1:
        raise HTTPException(400, "start must be >= 1")
    if (body.end - body.start + 1) > MAX_CHAPTER_RANGE:
        raise HTTPException(
            400,
            f"Range exceeds maximum limit of {MAX_CHAPTER_RANGE} chapters (requested {body.end - body.start + 1})"
        )

    try:
        from core.parsers import get_parser
        test_url = f"{base_url if base_url.endswith('-') else base_url.rstrip('/') + '/'}chapter-{body.start}/"
        get_parser(test_url)
    except Exception as exc:
        raise HTTPException(400, str(exc))

    job_id = uuid.uuid4().hex[:8]
    db = await get_db()
    try:
        await insert_job(db, job_id, f"{base_url} [ch {body.start}-{body.end}]", is_range=True)
    finally:
        await db.close()
    task = asyncio.create_task(run_range_job(job_id, base_url, body.start, body.end, body.chunk, body.concurrency))
    register_job_task(job_id, task)
    return {"id": job_id}


@router.post("/cancel-all")
async def cancel_all_jobs():
    """Cancel all running jobs."""
    count = await cancel_all_job_tasks()
    db = await get_db()
    try:
        await db.execute(
            "UPDATE jobs SET status = 'error', message = 'ยกเลิกการทำงานแล้ว (Cancelled)' WHERE status NOT IN ('done', 'error')"
        )
        await db.commit()
        await manager.broadcast("job_complete", {"message": "All active jobs cancelled"})
        return {"ok": True, "cancelled_count": count}
    finally:
        await db.close()


@router.post("/{job_id}/cancel")
async def cancel_single_job(job_id: str):
    """Cancel a single running job."""
    cancelled = await cancel_job_task(job_id)
    db = await get_db()
    try:
        await db.execute(
            "UPDATE jobs SET status = 'error', message = 'ยกเลิกการทำงานแล้ว (Cancelled)' WHERE id = ? AND status NOT IN ('done', 'error')",
            (job_id,),
        )
        await db.commit()
        await manager.broadcast("job_update", {"job_id": job_id, "status": "error", "message": "ยกเลิกการทำงานแล้ว (Cancelled)"})
        return {"ok": True, "cancelled": cancelled}
    finally:
        await db.close()


@router.delete("")
@router.delete("/")
async def delete_completed_jobs(all: bool = False):
    """Clear completed/errored jobs, or clear all jobs (including running) if all=True."""
    if all:
        await cancel_all_job_tasks()
        query = "DELETE FROM jobs"
    else:
        query = "DELETE FROM jobs WHERE status IN ('done', 'error')"
    db = await get_db()
    try:
        await db.execute(query)
        await db.commit()
        await manager.broadcast("job_complete", {"message": "Jobs cleared"})
        return {"ok": True}
    finally:
        await db.close()


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """Delete a single job by id, cancelling it first if running."""
    await cancel_job_task(job_id)
    db = await get_db()
    try:
        await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

