from __future__ import annotations

import asyncio
import logging
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template_string, request, send_from_directory

from manga_translate import (
    IMAGE_EXTENSIONS,
    download_images,
    lens_translate_work_dir,
    make_long_strip_pdf,
    parse_isekainonbiri_images,
    parse_mangablaze_images,
    parse_mangadex_images,
    parse_weebcentral_images,
    read_json,
    slugify,
    write_json,
)


class _QuietFilter(logging.Filter):
    QUIET_PATHS = ("/api/state",)

    def filter(self, record):
        msg = record.getMessage()
        return not any(p in msg for p in self.QUIET_PATHS)


logging.getLogger("werkzeug").addFilter(_QuietFilter())
app = Flask(__name__)
OUTPUT_ROOT = Path("output")
PDF_ROOT = OUTPUT_ROOT / "pdfs"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def parse_source(url: str):
    if "mangadex.org" in url:
        return parse_mangadex_images(url)
    if "mangablaze.com" in url:
        return parse_mangablaze_images(url)
    if "isekainonbirinouka.com" in url:
        return parse_isekainonbiri_images(url)
    return parse_weebcentral_images(url)


def update_job(job_id: str, **changes) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(changes)
            JOBS[job_id]["updated"] = datetime.now().isoformat(timespec="seconds")


def lens_translate_and_pdf(job_id: str, work_dir: Path, chunk_size: int, pdf_path: Path | None = None) -> None:
    update_job(job_id, status="translating", message="Google Lens translating")
    results = asyncio.run(
        lens_translate_work_dir(work_dir, lang="th", concurrency=4, verbose=False, max_retries=2)
    )
    ok = sum(1 for r in results if r.get("translated_file"))
    failed = len(results) - ok
    update_job(job_id, translated=ok, failed=failed, message="Building PDF")
    pdf_path = make_long_strip_pdf(work_dir, pdf_path, translated=True, chunk_size=chunk_size, width_mm=190)
    update_job(job_id, pdf=str(pdf_path))


def run_job(job_id: str, url: str, chunk_size: int) -> None:
    try:
        update_job(job_id, status="parsing", message="Parsing chapter URL")
        title, pages = parse_source(url)
        from urllib.parse import urlparse as _urlparse
        chapter_slug = _urlparse(url).path.strip("/").split("/")[-1] or slugify(title)
        work_dir = OUTPUT_ROOT / chapter_slug
        work_dir.mkdir(parents=True, exist_ok=True)
        update_job(job_id, status="downloading", title=title, work_dir=str(work_dir),
                   slug=work_dir.name, total_pages=len(pages),
                   message=f"Downloading {len(pages)} pages")
        manifest_pages = download_images(pages, work_dir, workers=8)
        write_json(work_dir / "manifest.json",
                   {"source": url, "title": title,
                    "page_count": len(manifest_pages), "pages": manifest_pages})
        update_job(job_id, downloaded=len(manifest_pages))
        PDF_ROOT.mkdir(parents=True, exist_ok=True)
        lens_translate_and_pdf(job_id, work_dir, chunk_size, PDF_ROOT / f"{chapter_slug}.pdf")
        update_job(job_id, status="done", message="Finished")
    except Exception as exc:
        update_job(job_id, status="error", message=f"{type(exc).__name__}: {exc}")


def run_range_job(job_id: str, base_url: str, start: int, end: int, chunk_size: int) -> None:
    chapters = list(range(start, end + 1))
    base = base_url if base_url.endswith("-") else base_url.rstrip("/") + "/"
    update_job(job_id, total_chapters=len(chapters), done_chapters=0, message=f"Range {start}-{end}")
    failures: list[int] = []
    for n in chapters:
        chapter_url = f"{base}chapter-{n}/"
        update_job(job_id, status="parsing", message=f"Chapter {n}", current_chapter=n)
        try:
            title, pages = parse_source(chapter_url)
            from urllib.parse import urlparse as _urlparse
            chapter_slug = _urlparse(chapter_url).path.strip("/").split("/")[-1] or f"chapter-{n}"
            work_dir = OUTPUT_ROOT / chapter_slug
            work_dir.mkdir(parents=True, exist_ok=True)
            update_job(job_id, status="downloading", title=title, total_pages=len(pages),
                       work_dir=str(work_dir), slug=work_dir.name)
            manifest_pages = download_images(pages, work_dir, workers=8)
            write_json(work_dir / "manifest.json",
                       {"source": chapter_url, "title": title,
                        "page_count": len(manifest_pages), "pages": manifest_pages})
            update_job(job_id, downloaded=len(manifest_pages))
            PDF_ROOT.mkdir(parents=True, exist_ok=True)
            lens_translate_and_pdf(job_id, work_dir, chunk_size, PDF_ROOT / f"{chapter_slug}.pdf")
        except Exception as exc:
            failures.append(n)
            update_job(job_id, message=f"Ch {n} failed: {exc}")
        with JOBS_LOCK:
            JOBS[job_id]["done_chapters"] = JOBS[job_id].get("done_chapters", 0) + 1

    msg = f"Range done. {len(chapters) - len(failures)}/{len(chapters)} OK"
    if failures:
        msg += f" · failed: {failures}"
    update_job(job_id, status="done", message=msg)


INDEX_HTML = """<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manga Translate</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Thai:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0a0c12;
  --bg-grad: radial-gradient(ellipse 80% 60% at 50% -20%, rgba(124,92,255,.15), transparent 70%),
             radial-gradient(ellipse 60% 50% at 100% 100%, rgba(34,197,94,.08), transparent 60%),
             #0a0c12;
  --panel: rgba(26, 29, 36, .7);
  --panel-solid: #1a1d24;
  --panel-2: #232733;
  --panel-3: #2d3140;
  --text: #e7e9ee;
  --muted: #8b94a7;
  --muted-2: #5d6478;
  --accent: #8b6dff;
  --accent-2: #b794ff;
  --accent-glow: rgba(139, 109, 255, .35);
  --ok: #22c55e;
  --warn: #f59e0b;
  --err: #ef4444;
  --border: rgba(255,255,255,.08);
  --border-strong: rgba(255,255,255,.16);
  --shadow: 0 8px 32px rgba(0,0,0,.4), 0 2px 6px rgba(0,0,0,.3);
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: 'Inter', 'Noto Sans Thai', system-ui, sans-serif;
  background: var(--bg-grad);
  background-attachment: fixed;
  color: var(--text);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

/* ----------- layout ----------- */
.container { max-width: 1280px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }
.hero {
  display: flex; justify-content: space-between; align-items: flex-end;
  margin-bottom: 2rem; gap: 1rem; flex-wrap: wrap;
}
.brand { display: flex; align-items: center; gap: .8rem; }
.brand-icon {
  width: 48px; height: 48px; border-radius: 12px;
  background: linear-gradient(135deg, #8b6dff, #5b8def);
  display: flex; align-items: center; justify-content: center;
  font-size: 1.5rem; box-shadow: 0 4px 16px var(--accent-glow);
}
.brand h1 {
  margin: 0; font-size: 1.6rem; font-weight: 700;
  background: linear-gradient(135deg, #fff, #b794ff);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.brand-sub { font-size: .8rem; color: var(--muted); margin-top: .15rem; }
.tag {
  display: inline-flex; align-items: center; gap: .35rem;
  background: rgba(34,197,94,.12); color: var(--ok);
  padding: .35rem .7rem; border-radius: 999px; font-size: .75rem; font-weight: 500;
  border: 1px solid rgba(34,197,94,.25);
}
.tag::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--ok);
  box-shadow: 0 0 8px var(--ok);
}

/* ----------- cards ----------- */
.card {
  background: var(--panel);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 1.3rem 1.4rem;
  margin-bottom: 1rem;
  box-shadow: var(--shadow);
  transition: border-color .2s;
}
.card:hover { border-color: var(--border-strong); }
.card-header { display: flex; align-items: center; gap: .6rem; margin-bottom: 1rem; }
.card h2 {
  margin: 0; font-size: .8rem; color: var(--muted);
  font-weight: 600; text-transform: uppercase; letter-spacing: .08em;
}
.card-icon {
  width: 28px; height: 28px; border-radius: 7px;
  background: rgba(139,109,255,.12); color: var(--accent);
  display: flex; align-items: center; justify-content: center; font-size: .9rem;
}

/* ----------- forms ----------- */
.form-row { display: flex; gap: .6rem; flex-wrap: wrap; align-items: stretch; }
input[type=text], input[type=number] {
  padding: .7rem .9rem; background: var(--panel-solid); color: var(--text);
  border: 1px solid var(--border); border-radius: 9px; font-size: .95rem;
  font-family: inherit; transition: all .15s;
}
input[type=text] { flex: 1; min-width: 220px; }
input:hover { border-color: var(--border-strong); }
input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
input::placeholder { color: var(--muted-2); }

.btn {
  padding: .7rem 1.4rem;
  background: linear-gradient(135deg, var(--accent), #6e51e6);
  color: white; border: none; border-radius: 9px; cursor: pointer;
  font-size: .95rem; font-weight: 600; font-family: inherit;
  box-shadow: 0 4px 14px var(--accent-glow);
  transition: transform .1s, box-shadow .2s, filter .15s;
  display: inline-flex; align-items: center; gap: .4rem;
}
.btn:hover { filter: brightness(1.1); box-shadow: 0 6px 18px var(--accent-glow); }
.btn:active { transform: translateY(1px); }
.btn-ghost {
  background: transparent; color: var(--muted); border: 1px solid var(--border-strong);
  box-shadow: none;
}
.btn-ghost:hover { color: var(--text); background: var(--panel-2); border-color: var(--accent); }
.btn-sm {
  padding: .35rem .75rem;
  font-size: .8rem;
  border-radius: 7px;
}
.btn-danger {
  background: rgba(239, 68, 68, .12);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, .3);
  box-shadow: none;
}
.btn-danger:hover {
  background: rgba(239, 68, 68, .22);
  border-color: #ef4444;
  color: #fff;
  box-shadow: 0 2px 10px rgba(239, 68, 68, .25);
}
.form-hint { font-size: .8rem; color: var(--muted); margin-top: .6rem; }
.form-hint code { background: var(--panel-2); padding: .1rem .4rem; border-radius: 4px; color: var(--accent-2); font-size: .85em; }
.site-links { display: inline-flex; flex-wrap: wrap; align-items: center; gap: .45rem; }
.site-link {
  display: inline-flex; align-items: center; gap: .3rem;
  background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
  padding: .28rem .65rem; border-radius: 7px; font-size: .8rem;
  text-decoration: none; font-weight: 500; transition: all .15s;
}
.site-link:hover {
  background: rgba(139,109,255,.14); border-color: var(--accent); color: var(--accent-2);
  transform: translateY(-1px);
}
.site-link .icon { font-size: .75rem; opacity: .7; }

/* ----------- jobs ----------- */
.jobs { display: flex; flex-direction: column; gap: .65rem; }
.job {
  background: var(--panel-solid); border: 1px solid var(--border); border-radius: 10px;
  padding: .9rem 1.1rem; display: flex; align-items: center; gap: 1rem;
  transition: all .2s; position: relative; overflow: hidden;
}
.job:hover { border-color: var(--border-strong); }
.job::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--accent); opacity: 0; transition: opacity .2s;
}
.job:hover::before { opacity: 1; }
.job-info { flex: 1; min-width: 0; }
.job-title { font-weight: 600; font-size: .95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-meta { font-size: .8rem; color: var(--muted); margin-top: .25rem; }

.status-pill {
  padding: .2rem .65rem; border-radius: 999px; font-size: .65rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .05em; white-space: nowrap;
  border: 1px solid currentColor;
}
.status-queued, .status-parsing { background: rgba(245,158,11,.12); color: var(--warn); border-color: rgba(245,158,11,.4); }
.status-downloading, .status-translating { background: rgba(139,109,255,.12); color: var(--accent-2); border-color: rgba(139,109,255,.4); }
.status-done { background: rgba(34,197,94,.12); color: var(--ok); border-color: rgba(34,197,94,.4); }
.status-error { background: rgba(239,68,68,.12); color: var(--err); border-color: rgba(239,68,68,.4); }

.progress { height: 5px; background: rgba(255,255,255,.05); border-radius: 999px; overflow: hidden; margin-top: .55rem; }
.progress-bar {
  height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  transition: width .4s ease-out; position: relative;
}
.progress-bar::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.3), transparent);
  animation: shimmer 1.8s infinite;
}
.status-done .progress-bar::after, .status-error .progress-bar::after { display: none; }
@keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }

/* ----------- chapters ----------- */
.chapters-header { display: flex; gap: .6rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; }
.search-box {
  flex: 1; min-width: 200px; max-width: 320px;
  position: relative;
}
.search-box input {
  width: 100%; padding-left: 2.2rem;
}
.search-box::before {
  content: '🔍'; position: absolute; left: .75rem; top: 50%; transform: translateY(-50%);
  font-size: .9rem; opacity: .6;
}
.chapter-count { font-size: .8rem; color: var(--muted); }
.filter-select {
  background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
  border-radius: 8px; padding: .5rem .7rem; font-size: .85rem; font-family: inherit;
  cursor: pointer; outline: none; transition: border-color .15s;
}
.filter-select:hover, .filter-select:focus { border-color: var(--accent); }

.chapters { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 1rem; }
.chapter {
  background: var(--panel-solid); border: 1px solid var(--border); border-radius: 12px;
  overflow: hidden; transition: all .25s cubic-bezier(.4,0,.2,1);
  display: flex; flex-direction: column;
}
.chapter:hover {
  transform: translateY(-4px);
  border-color: var(--accent);
  box-shadow: 0 12px 32px rgba(0,0,0,.4), 0 0 0 1px var(--accent-glow);
}
.chapter-thumb {
  aspect-ratio: 3/4; background: #000; overflow: hidden; position: relative;
}
.chapter-thumb img {
  width: 100%; height: 100%; object-fit: cover;
  transition: transform .4s, filter .25s;
}
.chapter:hover .chapter-thumb img { transform: scale(1.05); }
.chapter-thumb::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(to top, rgba(0,0,0,.75) 0%, rgba(0,0,0,0) 35%);
  pointer-events: none;
}
.thumb-badge {
  position: absolute; top: 8px; right: 8px;
  padding: .25rem .55rem; border-radius: 6px;
  font-size: .65rem; font-weight: 700; letter-spacing: .03em;
  backdrop-filter: blur(6px); z-index: 2;
  border: 1px solid rgba(255,255,255,.2);
}
.thumb-badge.ok { background: rgba(34,197,94,.85); color: white; }
.thumb-badge.warn { background: rgba(245,158,11,.85); color: #111; }
.chapter-info { padding: .7rem .85rem .5rem; flex: 1; }
.chapter-name {
  font-size: .9rem; font-weight: 600;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; line-height: 1.3;
}
.chapter-meta { font-size: .72rem; color: var(--muted); margin-top: .35rem; display: flex; gap: .5rem; align-items: center; }
.chapter-meta::before { content: '📄'; font-size: .8rem; }
.chapter-actions { display: flex; gap: .35rem; padding: .6rem .85rem .85rem; }
.chapter-actions a, .chapter-actions button {
  font-size: .75rem; padding: .4rem .55rem; flex: 1; text-align: center;
  background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
  border-radius: 6px; cursor: pointer; text-decoration: none; font-weight: 500;
  font-family: inherit; transition: all .15s;
}
.chapter-actions a:hover, .chapter-actions button:hover {
  border-color: var(--accent); color: var(--accent-2); background: rgba(139,109,255,.08);
}
.chapter-actions .danger:hover { border-color: var(--err); color: var(--err); background: rgba(239,68,68,.08); }

/* ----------- empty states ----------- */
.empty-state {
  color: var(--muted); text-align: center; padding: 3rem 1rem; font-size: .95rem;
  display: flex; flex-direction: column; align-items: center; gap: .6rem;
}
.empty-icon { font-size: 2.5rem; opacity: .35; }

/* ----------- toast ----------- */
.toast {
  position: fixed; bottom: 1.5rem; right: 1.5rem;
  background: var(--panel-solid); border: 1px solid var(--border-strong);
  padding: .8rem 1.2rem; border-radius: 10px;
  opacity: 0; transform: translateY(20px);
  transition: opacity .25s, transform .25s; pointer-events: none;
  box-shadow: var(--shadow); font-size: .9rem; font-weight: 500;
  z-index: 1000; max-width: 360px;
}
.toast.show { opacity: 1; transform: translateY(0); }
.toast.toast-err { border-color: var(--err); color: var(--err); }
.toast.toast-ok { border-color: var(--ok); color: var(--ok); }

/* ----------- responsive ----------- */
@media (max-width: 640px) {
  .container { padding: 1.2rem 1rem 2.5rem; }
  .brand h1 { font-size: 1.3rem; }
  .form-row { flex-direction: column; }
  .form-row input[type=number] { flex: 1 !important; }
  .chapters { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: .7rem; }
}
</style>
</head>
<body>
<div class="container">
  <div class="hero">
    <div class="brand">
      <div class="brand-icon">📚</div>
      <div>
        <h1>Manga Translate</h1>
        <div class="brand-sub">แปลมังงะอังกฤษเป็นไทยด้วย Google Lens</div>
      </div>
    </div>
    <span class="tag">Google Lens Overlay</span>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-icon">✨</div>
      <h2>ตอนเดียว</h2>
    </div>
    <form id="form">
      <div class="form-row">
        <input type="text" name="url" placeholder="วาง URL ตอนมังงะ — MangaDex / WeebCentral" required autocomplete="off">
        <input type="number" name="chunk" value="8" min="0" title="chunk-size (หน้าต่อ PDF page)" style="flex:0 0 90px">
        <button type="submit" class="btn">เริ่ม →</button>
      </div>
      <div class="form-hint" style="display:flex; align-items:center; flex-wrap:wrap; gap:.5rem; margin-top:.7rem;">
        <span style="font-size:.82rem; color:var(--muted);">🌐 เว็บหลักที่เปิดใช้งานได้ปกติ:</span>
        <div class="site-links">
          <a href="https://mangadex.org/" target="_blank" rel="noreferrer" class="site-link">MangaDex <span class="icon">↗</span></a>
          <a href="https://weebcentral.com/" target="_blank" rel="noreferrer" class="site-link">WeebCentral <span class="icon">↗</span></a>
        </div>
      </div>
    </form>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-icon">📦</div>
      <h2>หลายตอน (Chapter Range)</h2>
    </div>
    <form id="range-form">
      <div class="form-row">
        <input type="text" name="base_url" placeholder="Base URL เช่น https://mangablaze.com/manga/<slug>/" required autocomplete="off" style="flex:3">
        <input type="number" name="start" placeholder="เริ่ม" required min="1" style="flex:0 0 90px">
        <input type="number" name="end" placeholder="จบ" required min="1" style="flex:0 0 90px">
        <button type="submit" class="btn">เริ่ม →</button>
      </div>
      <div class="form-hint" style="display:flex; align-items:center; flex-wrap:wrap; gap:.5rem; margin-top:.7rem;">
        <span style="font-size:.82rem; color:var(--muted);">🌐 เว็บที่รองรับ:</span>
        <div class="site-links">
          <a href="https://mangablaze.com/" target="_blank" rel="noreferrer" class="site-link">MangaBlaze <span class="icon">↗</span></a>
        </div>
        <span style="font-size:.78rem; color:var(--muted-2); margin-left:.2rem;">(ระบบจะต่อท้ายเป็น <code>chapter-N/</code> ให้อัตโนมัติ)</span>
      </div>
    </form>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-icon">⚡</div>
      <h2>งานปัจจุบัน</h2>
    </div>
    <div class="jobs" id="jobs"></div>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-icon">📚</div>
      <h2>คลังตอน</h2>
      <div style="flex:1"></div>
      <span class="chapter-count" id="chapter-count"></span>
      <button class="btn btn-sm btn-danger" id="btn-delete-all" onclick="deleteAllChapters()" style="display:none;">🗑 ลบทั้งหมด</button>
    </div>
    <div class="chapters-header">
      <div class="search-box">
        <input type="text" id="search" placeholder="ค้นหาตอน..." autocomplete="off">
      </div>
      <select id="filter-status" class="filter-select">
        <option value="all">ทั้งหมด</option>
        <option value="has_pdf">มี PDF</option>
        <option value="no_pdf">ยังไม่มี PDF</option>
        <option value="not_translated">ยังไม่แปล</option>
        <option value="has_failed">มีหน้าที่ fail</option>
      </select>
      <select id="filter-sort" class="filter-select">
        <option value="newest">ใหม่สุด</option>
        <option value="oldest">เก่าสุด</option>
        <option value="chapter_asc">ตอน ↑</option>
        <option value="chapter_desc">ตอน ↓</option>
        <option value="name">ชื่อ A-Z</option>
      </select>
    </div>
    <div class="chapters" id="chapters"></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const STATUS_TH = { queued:'รอคิว', parsing:'อ่าน URL', downloading:'ดาวน์โหลด', translating:'กำลังแปล', done:'เสร็จ', error:'ผิดพลาด' };

function showToast(msg, kind){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (kind==='err' ? ' toast-err' : kind==='ok' ? ' toast-ok' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 2600);
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function pdfUrl(p){return '/output/'+p.replace(/\\\\/g,'/').replace(/^output\\//,'');}

function calcProgress(j){
  if(j.status==='done'||j.status==='error')return 100;
  if(j.status==='translating'&&j.translated&&j.total_pages)return 60+(j.translated/j.total_pages)*40;
  if(j.status==='downloading'&&j.downloaded&&j.total_pages)return 10+(j.downloaded/j.total_pages)*50;
  if(j.status==='parsing')return 5;
  return 0;
}

let pollTimer = null;
async function refresh() {
  try {
    const state = await (await fetch('/api/state')).json();
    const jobs = state.jobs || [];
    const chapters = state.chapters || [];
    document.getElementById('jobs').innerHTML = jobs.length ? jobs.map(j => {
      const pct = calcProgress(j);
      const sub = [
        j.downloaded ? `↓ ${j.downloaded}/${j.total_pages||'?'}` : '',
        j.translated !== undefined ? `✓ ${j.translated}` : '',
        j.failed ? `✗ ${j.failed}` : '',
        j.message || '',
      ].filter(Boolean).join(' · ');
      const link = j.pdf ? `<a class="btn btn-ghost" href="${pdfUrl(j.pdf)}" target="_blank">เปิด PDF</a>` : '';
      return `<div class="job">
        <div class="job-info">
          <div class="job-title">${escapeHtml(j.title || j.url)}</div>
          <div class="job-meta">${escapeHtml(sub)}</div>
          <div class="progress"><div class="progress-bar" style="width:${pct}%"></div></div>
        </div>
        <span class="status-pill status-${j.status}">${STATUS_TH[j.status]||j.status}</span>
        ${link}
      </div>`;
    }).join('') : '<div class="empty-state"><div class="empty-icon">💤</div>ยังไม่มีงาน — วาง URL ด้านบนเพื่อเริ่ม</div>';

    window._chapters = chapters;
    renderChapters();

    const nextDelay = state.active ? 2000 : 8000;
    clearTimeout(pollTimer);
    pollTimer = setTimeout(refresh, nextDelay);
  } catch (e) {
    console.error(e);
    clearTimeout(pollTimer);
    pollTimer = setTimeout(refresh, 5000);
  }
}

function chapterNum(c) {
  const m = (c.name||'').match(/chapter-(\\d+(?:[-.]\\d+)?)/i);
  return m ? parseFloat(m[1].replace('-', '.')) : Infinity;
}

function renderChapters() {
  const all = window._chapters || [];
  const q = (document.getElementById('search').value || '').trim().toLowerCase();
  const status = document.getElementById('filter-status').value;
  const sort = document.getElementById('filter-sort').value;

  let filtered = q
    ? all.filter(c => (c.title||'').toLowerCase().includes(q) || (c.name||'').toLowerCase().includes(q))
    : all.slice();

  filtered = filtered.filter(c => {
    if (status === 'has_pdf') return c.pdfs.length > 0;
    if (status === 'no_pdf') return c.pdfs.length === 0;
    if (status === 'not_translated') return !c.translated_count;
    if (status === 'has_failed') return c.has_failed;
    return true;
  });

  if (sort === 'oldest') filtered.sort((a,b) => (a.mtime||0) - (b.mtime||0));
  else if (sort === 'chapter_asc') filtered.sort((a,b) => chapterNum(a) - chapterNum(b));
  else if (sort === 'chapter_desc') filtered.sort((a,b) => chapterNum(b) - chapterNum(a));
  else if (sort === 'name') filtered.sort((a,b) => (a.name||'').localeCompare(b.name||''));
  // 'newest' is the default order from server (mtime desc) — no sort needed

  const el = document.getElementById('chapters');
  const delAllBtn = document.getElementById('btn-delete-all');
  if (delAllBtn) {
    delAllBtn.style.display = all.length ? 'inline-flex' : 'none';
  }
  document.getElementById('chapter-count').textContent =
    all.length ? `${filtered.length}/${all.length} ตอน` : '';
  if (!filtered.length) {
    el.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <div class="empty-icon">${all.length ? '🔍' : '📥'}</div>
      ${all.length ? 'ไม่พบตอนที่ตรงกับคำค้นหา' : 'ยังไม่มีตอน — เริ่มงานใหม่ด้านบน'}
    </div>`;
    return;
  }
  el.innerHTML = filtered.map(c => {
    const badge = c.thumb_kind === 'translated'
      ? '<span class="thumb-badge ok">TH</span>'
      : (c.thumb_kind === 'original' ? '<span class="thumb-badge warn">EN</span>' : '');
    return `<div class="chapter">
      <div class="chapter-thumb">
        ${c.thumb ? `<img loading="lazy" src="/output/${encodeURI(c.name)}/${c.thumb}">` : ''}
        ${badge}
      </div>
      <div class="chapter-info">
        <div class="chapter-name" title="${escapeHtml(c.name)}">${escapeHtml(c.title || c.name)}</div>
        <div class="chapter-meta">${c.translated_count||0}/${c.page_count||'?'} แปล · ${c.pdfs.length} PDF</div>
      </div>
      <div class="chapter-actions">
        ${c.pdfs.length ? `<a href="/output/${encodeURI(c.name)}/${encodeURI(c.pdfs[0])}" target="_blank">📖 อ่าน</a>` : `<button onclick="translateChapter('${c.name}')">แปล</button>`}
        ${c.has_failed ? `<button onclick="retry('${c.name}')">retry</button>` : ''}
        <button class="danger" onclick="del('${c.name}')">ลบ</button>
      </div>
    </div>`;
  }).join('');
}

document.getElementById('search').addEventListener('input', renderChapters);
document.getElementById('filter-status').addEventListener('change', renderChapters);
document.getElementById('filter-sort').addEventListener('change', renderChapters);

async function translateChapter(name){
  if(!confirm(`แปล "${name}" ด้วย Google Lens?`))return;
  const r = await fetch(`/api/chapters/${encodeURIComponent(name)}/translate`, {method:'POST'});
  const body = await r.json().catch(()=>({}));
  if(r.ok) showToast('✓ เริ่มแปลแล้ว','ok'); else showToast('ERROR: '+(body.error||r.status),'err');
  refresh();
}
async function retry(name){
  if(!confirm(`Retry หน้าที่ Lens fail ใน "${name}"?`))return;
  const r = await fetch(`/api/chapters/${encodeURIComponent(name)}/retry`,{method:'POST'});
  if(r.ok) showToast('✓ Retry queued','ok'); else showToast('Retry failed','err');
  refresh();
}
async function del(name){
  if(!confirm(`ลบ "${name}"?`))return;
  const r = await fetch(`/api/chapters/${encodeURIComponent(name)}`,{method:'DELETE'});
  if(r.ok) showToast('🗑 ลบแล้ว','ok'); else showToast('ลบไม่สำเร็จ','err');
  refresh();
}
async function deleteAllChapters(){
  const all = window._chapters || [];
  if(!all.length){
    showToast('ไม่มีตอนในคลังให้ลบ','err');
    return;
  }
  if(!confirm(`⚠️ คุณแน่ใจหรือไม่ว่าต้องการลบทั้งหมด ${all.length} ตอนในคลัง?\n(โฟลเดอร์ภาพและ PDF ทั้งหมดจะถูกลบถาวร)`)) return;
  try {
    const r = await fetch('/api/chapters', {method:'DELETE'});
    const body = await r.json().catch(()=>({}));
    if(r.ok){
      showToast(`🗑 ลบทั้งหมด ${body.count || all.length} ตอนเรียบร้อย`,'ok');
    } else {
      showToast('ลบไม่สำเร็จ: '+(body.error||r.status),'err');
    }
  } catch(e) {
    showToast('เกิดข้อผิดพลาดในการลบ','err');
  }
  refresh();
}

document.getElementById('form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch('/api/jobs', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({url: fd.get('url'), chunk: parseInt(fd.get('chunk')||'8')}),
  });
  const body = await r.json().catch(()=>({}));
  if(r.ok){ showToast('✓ เริ่มงานแล้ว','ok'); e.target.url.value=''; }
  else showToast('ERROR: '+(body.error||r.status),'err');
  refresh();
});

document.getElementById('range-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const mainFd = new FormData(document.getElementById('form'));
  const payload = {
    base_url: (fd.get('base_url')||'').trim(),
    start: parseInt(fd.get('start')), end: parseInt(fd.get('end')),
    chunk: parseInt(mainFd.get('chunk')||'8'),
  };
  const r = await fetch('/api/range', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const body = await r.json().catch(()=>({}));
  if(r.ok){ showToast('✓ เริ่ม Range แล้ว','ok'); e.target.reset(); }
  else { console.error(body); showToast('ERROR: '+(body.error||r.status),'err'); }
  refresh();
});

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refresh();
  else clearTimeout(pollTimer);
});
refresh();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/api/state")
def api_state():
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda r: r.get("created", ""), reverse=True)[:20]
    active = any(j.get("status") not in ("done", "error") for j in jobs)
    return jsonify({"jobs": jobs, "chapters": _list_chapters(), "active": active})


_CHAPTERS_CACHE: dict = {"sig": None, "rows": []}


def _scan_chapter(path: Path) -> dict:
    import os
    name = path.name
    manifest = read_json(path / "manifest.json", {})

    pdfs: list[str] = []
    try:
        for entry in os.scandir(path):
            if entry.is_file() and entry.name.lower().endswith(".pdf"):
                pdfs.append(entry.name)
    except OSError:
        pass
    pdfs.sort()
    external_pdf = PDF_ROOT / f"{name}.pdf"
    if external_pdf.exists():
        pdfs.append(f"../pdfs/{external_pdf.name}")

    def _first_image(folder: Path) -> str | None:
        try:
            best = None
            for entry in os.scandir(folder):
                if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_EXTENSIONS:
                    if best is None or entry.name < best:
                        best = entry.name
            return best
        except OSError:
            return None

    def _count_images(folder: Path) -> int:
        try:
            return sum(1 for e in os.scandir(folder) if e.is_file() and Path(e.name).suffix.lower() in IMAGE_EXTENSIONS)
        except OSError:
            return 0

    thumb, thumb_kind = None, "none"
    tr_first = _first_image(path / "translated_images")
    if tr_first:
        thumb, thumb_kind = f"translated_images/{tr_first}", "translated"
    else:
        im_first = _first_image(path / "images")
        if im_first:
            thumb, thumb_kind = f"images/{im_first}", "original"

    return {
        "name": name,
        "title": manifest.get("title", name),
        "page_count": manifest.get("page_count"),
        "translated_count": _count_images(path / "translated_images"),
        "pdfs": pdfs, "thumb": thumb, "thumb_kind": thumb_kind,
        "has_failed": (path / "lens_failed.json").exists(),
        "mtime": path.stat().st_mtime,
    }


def _list_chapters():
    from concurrent.futures import ThreadPoolExecutor

    if not OUTPUT_ROOT.exists():
        return []

    try:
        pdf_root_resolved = PDF_ROOT.resolve()
    except OSError:
        pdf_root_resolved = None

    dirs: list[Path] = []
    for path in OUTPUT_ROOT.iterdir():
        if not path.is_dir():
            continue
        try:
            if pdf_root_resolved is not None and path.resolve() == pdf_root_resolved:
                continue
        except OSError:
            pass
        dirs.append(path)

    sig = tuple(sorted((p.name, p.stat().st_mtime) for p in dirs))
    if _CHAPTERS_CACHE["sig"] == sig and _CHAPTERS_CACHE["rows"]:
        return _CHAPTERS_CACHE["rows"]

    if dirs:
        with ThreadPoolExecutor(max_workers=min(16, len(dirs))) as pool:
            rows = list(pool.map(_scan_chapter, dirs))
    else:
        rows = []
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    _CHAPTERS_CACHE["sig"] = sig
    _CHAPTERS_CACHE["rows"] = rows
    return rows


@app.route("/api/jobs", methods=["POST"])
def api_create_job():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    job_id = uuid.uuid4().hex[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "url": url, "status": "queued",
            "created": datetime.now().isoformat(timespec="seconds"),
        }
    threading.Thread(target=run_job, args=(job_id, url, int(data.get("chunk", 8))), daemon=True).start()
    return jsonify({"id": job_id}), 201


@app.route("/api/range", methods=["POST"])
def api_range():
    data = request.get_json(force=True) or {}
    base_url = (data.get("base_url") or "").strip()
    if not base_url:
        return jsonify({"error": "base_url is required"}), 400
    try:
        start, end = int(data.get("start")), int(data.get("end"))
    except (TypeError, ValueError):
        return jsonify({"error": f"start/end must be integers (got {data.get('start')!r}, {data.get('end')!r})"}), 400
    if start > end:
        return jsonify({"error": f"start ({start}) > end ({end})"}), 400
    if start < 1:
        return jsonify({"error": "start must be >= 1"}), 400
    job_id = uuid.uuid4().hex[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "url": f"{base_url} [ch {start}-{end}]",
            "title": f"Chapter range {start}-{end}", "status": "queued",
            "created": datetime.now().isoformat(timespec="seconds"), "is_range": True,
        }
    threading.Thread(target=run_range_job, args=(job_id, base_url, start, end, int(data.get("chunk", 8))), daemon=True).start()
    return jsonify({"id": job_id}), 201


@app.route("/api/chapters/<name>/translate", methods=["POST"])
def api_translate_existing(name: str):
    target = OUTPUT_ROOT / name
    if not target.exists():
        abort(404)
    manifest = read_json(target / "manifest.json", {})
    job_id = uuid.uuid4().hex[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "url": f"translate: {name}",
            "title": manifest.get("title", name), "status": "translating",
            "total_pages": manifest.get("page_count"),
            "created": datetime.now().isoformat(timespec="seconds"),
            "message": f"Translating {name}",
        }

    def do_translate():
        try:
            lens_translate_and_pdf(job_id, target, 8)
            update_job(job_id, status="done", message="Done")
        except Exception as exc:
            update_job(job_id, status="error", message=str(exc))

    threading.Thread(target=do_translate, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/chapters/<name>/retry", methods=["POST"])
def api_retry(name: str):
    target = OUTPUT_ROOT / name
    if not target.exists():
        abort(404)
    failed = read_json(target / "lens_failed.json", [])
    if not failed:
        return jsonify({"error": "no failed pages"}), 400
    job_id = uuid.uuid4().hex[:8]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "url": f"retry: {name}", "title": f"Retry {name}",
            "status": "translating", "total_pages": len(failed),
            "created": datetime.now().isoformat(timespec="seconds"),
            "message": f"Retrying {len(failed)} pages",
        }

    def do_retry():
        try:
            results = asyncio.run(lens_translate_work_dir(
                target, lang="th", force=True, concurrency=4,
                max_retries=3, only_pages=set(int(p) for p in failed),
            ))
            ok = sum(1 for r in results if r.get("translated_file"))
            update_job(job_id, status="done", translated=ok, failed=len(results) - ok,
                       message=f"Retry done: {ok} succeeded")
        except Exception as exc:
            update_job(job_id, status="error", message=str(exc))

    threading.Thread(target=do_retry, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/chapters/<name>", methods=["DELETE"])
def api_delete(name: str):
    target = OUTPUT_ROOT / name
    if not target.exists() or not target.is_dir():
        abort(404)
    if target.resolve().parent != OUTPUT_ROOT.resolve():
        abort(400)
    shutil.rmtree(target)
    external_pdf = PDF_ROOT / f"{name}.pdf"
    if external_pdf.exists():
        try:
            external_pdf.unlink()
        except OSError:
            pass
    _CHAPTERS_CACHE["sig"] = None
    _CHAPTERS_CACHE["rows"] = []
    return jsonify({"deleted": name})


@app.route("/api/chapters", methods=["DELETE"])
def api_delete_all():
    deleted = []
    try:
        pdf_root_resolved = PDF_ROOT.resolve()
    except OSError:
        pdf_root_resolved = None

    for path in list(OUTPUT_ROOT.iterdir()):
        if not path.is_dir():
            continue
        try:
            if pdf_root_resolved is not None and path.resolve() == pdf_root_resolved:
                continue
        except OSError:
            pass
        try:
            shutil.rmtree(path)
            deleted.append(path.name)
        except Exception as e:
            logging.error("Failed to delete %s: %s", path.name, e)

    if PDF_ROOT.exists():
        for pdf_file in list(PDF_ROOT.glob("*.pdf")):
            try:
                pdf_file.unlink()
            except OSError:
                pass

    _CHAPTERS_CACHE["sig"] = None
    _CHAPTERS_CACHE["rows"] = []
    return jsonify({"deleted": deleted, "count": len(deleted)})


@app.route("/output/<path:filename>")
def serve_output(filename: str):
    return send_from_directory(OUTPUT_ROOT.resolve(), filename)


if __name__ == "__main__":
    OUTPUT_ROOT.mkdir(exist_ok=True)
    print("Manga Translate Web → http://127.0.0.1:5000  (auto-reload on file change)")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=True,
            extra_files=["manga_translate.py"])
