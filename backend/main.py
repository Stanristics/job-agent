"""
FastAPI backend for the Job Agent dashboard.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import sqlite3
import json
import logging
import asyncio
import os
from datetime import datetime

from database import get_conn, init_db
from scrapers import run_all_scrapers, fetch_description
from ai_agent import process_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Job Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve frontend static files ────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_dashboard():
    index = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Job Agent API running"}

# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()
    logger.info("Job Agent API started.")

# ── Helpers ────────────────────────────────────────────────────────────────────
def get_settings() -> dict:
    conn = get_conn()
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return {r['key']: r['value'] for r in rows}

def row_to_dict(row) -> dict:
    d = dict(row)
    if d.get('match_reason'):
        try:
            d['match_reason'] = json.loads(d['match_reason'])
        except:
            pass
    return d

# ── Jobs endpoints ─────────────────────────────────────────────────────────────
@app.get("/jobs")
def get_jobs(status: Optional[str] = None, min_score: Optional[int] = None):
    conn = get_conn()
    query = 'SELECT * FROM jobs WHERE 1=1'
    params = []
    if status:
        query += ' AND status = ?'
        params.append(status)
    if min_score is not None:
        query += ' AND match_score >= ?'
        params.append(min_score)
    query += ' ORDER BY match_score DESC, created_at DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]

@app.get("/jobs/{job_id}")
def get_job(job_id: int):
    conn = get_conn()
    row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return row_to_dict(row)

class JobUpdate(BaseModel):
    status: Optional[str] = None
    cover_letter: Optional[str] = None

@app.patch("/jobs/{job_id}")
def update_job(job_id: int, update: JobUpdate):
    conn = get_conn()
    if update.status:
        conn.execute('UPDATE jobs SET status = ? WHERE id = ?', (update.status, job_id))
    if update.cover_letter is not None:
        conn.execute('UPDATE jobs SET cover_letter = ? WHERE id = ?', (update.cover_letter, job_id))
    conn.commit()
    conn.close()
    return {"success": True}

@app.delete("/jobs/{job_id}")
def delete_job(job_id: int):
    conn = get_conn()
    conn.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
    conn.commit()
    conn.close()
    return {"success": True}

# ── Stats ──────────────────────────────────────────────────────────────────────
@app.get("/stats")
def get_stats():
    conn = get_conn()
    total     = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
    pending   = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
    approved  = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='approved'").fetchone()[0]
    rejected  = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='rejected'").fetchone()[0]
    submitted = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='submitted'").fetchone()[0]
    avg_score = conn.execute('SELECT AVG(match_score) FROM jobs').fetchone()[0]
    conn.close()
    return {
        'total': total, 'pending': pending, 'approved': approved,
        'rejected': rejected, 'submitted': submitted,
        'avg_score': round(avg_score or 0, 1)
    }

# ── Search trigger ─────────────────────────────────────────────────────────────
search_running = False

@app.post("/search")
async def trigger_search(background_tasks: BackgroundTasks):
    global search_running
    if search_running:
        return {"message": "Search already running"}
    background_tasks.add_task(run_search)
    return {"message": "Search started"}

async def run_search():
    global search_running
    search_running = True
    try:
        settings = get_settings()
        titles   = [t.strip() for t in settings.get('job_titles', 'Data Scientist').split(',')]
        logger.info(f"Starting search for: {titles} across Germany")
        jobs = await asyncio.to_thread(run_all_scrapers, titles, 'Germany')
        conn = get_conn()
        new_count = 0
        for job in jobs:
            exists = conn.execute('SELECT id FROM jobs WHERE url = ?', (job['url'],)).fetchone()
            if exists:
                continue
            job['description'] = await asyncio.to_thread(fetch_description, job['url'], job['source'])
            job = await asyncio.to_thread(process_job, job, settings)
            conn.execute('''
                INSERT OR IGNORE INTO jobs
                  (title, company, location, source, url, description,
                   salary, posted_date, match_score, match_reason, cover_letter, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                job['title'], job['company'], job['location'], job['source'],
                job['url'], job['description'], job['salary'], job['posted_date'],
                job['match_score'], job['match_reason'], job['cover_letter'], 'pending'
            ))
            conn.commit()
            new_count += 1
        conn.close()
        logger.info(f"Search complete. {new_count} new jobs added.")
    except Exception as e:
        logger.error(f"Search error: {e}")
    finally:
        search_running = False

@app.get("/search/status")
def search_status():
    return {"running": search_running}

# ── Settings ───────────────────────────────────────────────────────────────────
@app.get("/settings")
def get_all_settings():
    return get_settings()

class SettingsUpdate(BaseModel):
    key: str
    value: str

@app.post("/settings")
def update_setting(update: SettingsUpdate):
    conn = get_conn()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                 (update.key, update.value))
    conn.commit()
    conn.close()
    return {"success": True}

# ── Submit application ─────────────────────────────────────────────────────────
@app.post("/jobs/{job_id}/submit")
def submit_application(job_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET status='submitted', submitted_at=datetime('now') WHERE id=?",
        (job_id,)
    )
    conn.commit()
    conn.close()
    return {"success": True}

# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)


# ── Send application email ─────────────────────────────────────────────────────
class EmailRequest(BaseModel):
    to_email: str
    job_id: int

@app.post("/jobs/{job_id}/send-email")
def send_email(job_id: int, req: EmailRequest):
    conn = get_conn()
    row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    job      = row_to_dict(row)
    settings = get_settings()
    cv_path  = settings.get('cv_path', '')

    from ai_agent import send_application_email
    result = send_application_email(req.to_email, job, job['cover_letter'], cv_path, settings)

    if result['success']:
        # Mark as submitted
        conn = get_conn()
        conn.execute(
            "UPDATE jobs SET status='submitted', submitted_at=datetime('now') WHERE id=?",
            (job_id,)
        )
        conn.commit()
        conn.close()

    return result


# ── Platform detection (for dashboard badge) ────────────────────────────────────
@app.get("/jobs/{job_id}/detect-platform")
def detect_platform(job_id: int):
    """Detect which application system (LinkedIn/Greenhouse/Workday/Lever/email) this job uses."""
    conn = get_conn()
    row = conn.execute('SELECT url FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    url_lower = row['url'].lower()
    if 'linkedin.com' in url_lower:
        platform = 'linkedin'
    elif 'greenhouse.io' in url_lower:
        platform = 'greenhouse'
    elif 'myworkdayjobs.com' in url_lower or 'workday.com' in url_lower:
        platform = 'workday'
    elif 'lever.co' in url_lower:
        platform = 'lever'
    elif 'indeed.com' in url_lower:
        platform = 'indeed'
    else:
        platform = 'unknown'

    # Form-based platforms need the local form filler; others use email
    needs_form_filler = platform in ('linkedin', 'greenhouse', 'workday', 'lever')

    return {"platform": platform, "needs_form_filler": needs_form_filler}

# NOTE: Actual form-filling does NOT run here on Render.
# Render has no display, so there's nothing for Stanley to review before submitting.
# Form-filling runs locally via local_form_filler.py on Stanley's Mac instead —
# that script pulls approved jobs from this API and opens a real visible browser.
