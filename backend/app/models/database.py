"""SQLite database setup using aiosqlite."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "manga.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    title       TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',
    message     TEXT,
    progress    TEXT DEFAULT '{}',
    is_range    INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
"""


async def get_db() -> aiosqlite.Connection:
    """Open (or create) the SQLite database and return a connection."""
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute(_CREATE_SQL)
    await db.commit()
    return db


async def init_db() -> None:
    """Ensure the database and tables exist."""
    db = await get_db()
    await db.close()


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------


async def insert_job(db: aiosqlite.Connection, job_id: str, url: str, is_range: bool = False) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    await db.execute(
        "INSERT INTO jobs (id, url, status, is_range, created_at) VALUES (?, ?, 'queued', ?, ?)",
        (job_id, url, int(is_range), now),
    )
    await db.commit()


async def update_job(db: aiosqlite.Connection, job_id: str, **fields) -> None:
    fields["updated_at"] = datetime.now().isoformat(timespec="seconds")

    # Merge non-standard fields into the JSON 'progress' column
    standard_cols = {"url", "title", "status", "message", "is_range", "updated_at"}
    progress_fields = {k: v for k, v in fields.items() if k not in standard_cols}
    col_fields = {k: v for k, v in fields.items() if k in standard_cols}

    if progress_fields:
        row = await db.execute_fetchall("SELECT progress FROM jobs WHERE id = ?", (job_id,))
        if row:
            existing = json.loads(row[0][0] or "{}")
            existing.update(progress_fields)
            col_fields["progress"] = json.dumps(existing)

    if col_fields:
        set_clause = ", ".join(f"{k} = ?" for k in col_fields)
        values = list(col_fields.values()) + [job_id]
        await db.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
        await db.commit()


async def get_all_jobs(db: aiosqlite.Connection, limit: int = 20) -> list[dict]:
    rows = await db.execute_fetchall(
        "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    result = []
    for row in rows:
        d = dict(row)
        progress = json.loads(d.pop("progress", "{}") or "{}")
        d.update(progress)
        d["is_range"] = bool(d.get("is_range"))
        result.append(d)
    return result
