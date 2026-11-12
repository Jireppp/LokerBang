from __future__ import annotations

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scraper import (  # noqa: E402
    ALL_PORTALS,
    HEADER,
    ROLES,
    SEARCH_LOCATIONS,
    WIB,
    HttpClient,
    JobPosting,
    SheetsSync,
    build_scrapers,
    infer_role_category,
    normalize_url,
    run as run_scrapers,
    setup_logging,
)

load_dotenv(ROOT_DIR / ".env")
setup_logging(verbose=False)
logger = logging.getLogger("lokerbang.api")

CACHE_FILE = Path(__file__).resolve().parent / "jobs_cache.json"
VALID_STATUSES = {"New", "Saved", "Applied", "Interview", "Rejected"}

PORTAL_KEY_MAP: dict[str, str] = {
    "linkedin": "linkedin",
    "jobstreet": "jobstreet",
    "glints": "glints",
    "kalibrr": "kalibrr",
    "dealls": "dealls",
    "tech in asia": "techinasia",
    "techinasia": "techinasia",
    "indeed": "indeed",
}

app = FastAPI(
    title="LokerBang Telemetry API Bridge",
    version="2.0.0",
    description="FastAPI bridge for LokerBang 7-portal parallel job scraper and Google Sheets tracker.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    roles: list[str] = Field(default_factory=lambda: list(ROLES.keys()))
    locations: list[str] = Field(default_factory=lambda: ["Bandung", "Jakarta"])
    portals: list[str] = Field(default_factory=lambda: list(ALL_PORTALS))
    days: int = Field(default=14, ge=1, le=60)
    async_mode: bool = Field(default=False)


class StatusUpdateRequest(BaseModel):
    url: str
    status: str


_scrape_lock = threading.Lock()
_scrape_state: dict[str, Any] = {
    "is_running": False,
    "current_step": "Idle",
    "started_at": None,
    "finished_at": None,
    "portal_status": {},
    "last_result": None,
}


def _normalize_job_record(job: dict[str, Any]) -> dict[str, str]:
    title = str(job.get("title") or "").strip()
    role_cat = str(job.get("role_category") or "").strip() or infer_role_category(title)
    return {
        "timestamp_scraped": str(job.get("timestamp_scraped") or "").strip(),
        "role_category": role_cat,
        "title": title,
        "company": str(job.get("company") or "").strip(),
        "location": str(job.get("location") or "").strip(),
        "platform": str(job.get("platform") or "").strip(),
        "date_posted": str(job.get("date_posted") or "").strip(),
        "experience_level": str(job.get("experience_level") or "Not specified").strip() or "Not specified",
        "url": normalize_url(str(job.get("url") or "")),
        "status": str(job.get("status") or "New").strip() or "New",
    }


def _load_cache() -> list[dict[str, str]]:
    if not CACHE_FILE.exists():
        return []
    try:
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        items: list[dict[str, Any]] = []
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict) and isinstance(raw.get("jobs"), list):
            items = raw["jobs"]
        else:
            return []

        needs_migration = any("role_category" not in j or not j.get("role_category") for j in items if isinstance(j, dict))
        normalized = [_normalize_job_record(j) for j in items if isinstance(j, dict) and j.get("url")]
        if needs_migration and normalized:
            _save_cache(normalized)
        return normalized
    except Exception as exc:
        logger.warning("Failed to read cache file %s: %s", CACHE_FILE, exc)
    return []


def _save_cache(jobs: list[dict[str, str]]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S"),
        "schema_columns": HEADER,
        "jobs": [_normalize_job_record(j) for j in jobs if j.get("url")],
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _sheets_credentials() -> tuple[str, str, str] | None:
    load_dotenv(ROOT_DIR / ".env", override=True)
    sa_file = os.getenv("SERVICE_ACCOUNT_FILE", "").strip()
    spreadsheet_id = os.getenv("SPREADSHEET_ID", "").strip()
    sheet_name = os.getenv("SHEET_NAME", "Job_Tracker").strip() or "Job_Tracker"
    if not sa_file or not spreadsheet_id or "PASTE" in spreadsheet_id:
        return None
    sa_path = Path(sa_file)
    if not sa_path.is_absolute():
        sa_path = ROOT_DIR / sa_path
    if not sa_path.exists():
        return None
    return str(sa_path), spreadsheet_id, sheet_name


def _try_load_from_sheets() -> list[dict[str, str]] | None:
    creds = _sheets_credentials()
    if not creds:
        return None
    sa_path, spreadsheet_id, sheet_name = creds
    try:
        syncer = SheetsSync.from_env(sa_path, spreadsheet_id, sheet_name)
        rows = syncer.worksheet.get_all_values()
        if not rows or len(rows) < 2:
            return []
        header = [h.strip() for h in rows[0]]
        col_map = {name: idx for idx, name in enumerate(header)}

        def _cell(row: list[str], col_name: str, fallback_idx: int) -> str:
            idx = col_map.get(col_name, fallback_idx)
            return row[idx].strip() if 0 <= idx < len(row) else ""

        jobs: list[dict[str, str]] = []
        for r in rows[1:]:
            if not any(c.strip() for c in r):
                continue
            url = _cell(r, "Job_URL", 8)
            if not url:
                continue
            title = _cell(r, "Job_Title", 2)
            role_cat = _cell(r, "Role_Category", 1) or infer_role_category(title)
            jobs.append(
                {
                    "timestamp_scraped": _cell(r, "Timestamp_Scraped", 0),
                    "role_category": role_cat,
                    "title": title,
                    "company": _cell(r, "Company", 3),
                    "location": _cell(r, "Location", 4),
                    "platform": _cell(r, "Platform", 5),
                    "date_posted": _cell(r, "Date_Posted", 6),
                    "experience_level": _cell(r, "Experience_Level", 7) or "Not specified",
                    "url": normalize_url(url),
                    "status": _cell(r, "Status", 9) or "New",
                }
            )
        return jobs
    except Exception as exc:
        logger.warning("Could not load jobs from Google Sheets: %s", exc)
        return None


def _try_sync_to_sheets(postings: list[JobPosting]) -> int:
    creds = _sheets_credentials()
    if not creds or not postings:
        return 0
    sa_path, spreadsheet_id, sheet_name = creds
    try:
        syncer = SheetsSync.from_env(sa_path, spreadsheet_id, sheet_name)
        return syncer.sync(postings, scraped_at=datetime.now(WIB))
    except Exception as exc:
        logger.warning("Could not sync new jobs to Google Sheets: %s", exc)
        return 0


def _try_update_sheet_status(target_url: str, new_status: str) -> bool:
    creds = _sheets_credentials()
    if not creds:
        return False
    sa_path, spreadsheet_id, sheet_name = creds
    norm_target = normalize_url(target_url)
    try:
        syncer = SheetsSync.from_env(sa_path, spreadsheet_id, sheet_name)
        rows = syncer.worksheet.get_all_values()
        if not rows:
            return False
        header = [h.strip() for h in rows[0]]
        url_idx = header.index("Job_URL") if "Job_URL" in header else 8
        status_idx = header.index("Status") if "Status" in header else 9

        for row_num, r in enumerate(rows[1:], start=2):
            if len(r) > url_idx and normalize_url(r[url_idx]) == norm_target:
                syncer.worksheet.update_cell(row_num, status_idx + 1, new_status)
                return True
    except Exception as exc:
        logger.warning("Failed to update status in Google Sheets: %s", exc)
    return False


def _posting_to_dict(p: JobPosting, scraped_at: datetime) -> dict[str, str]:
    row = p.to_row(scraped_at)
    return {
        "timestamp_scraped": row[0],
        "role_category": row[1],
        "title": row[2],
        "company": row[3],
        "location": row[4],
        "platform": row[5],
        "date_posted": row[6],
        "experience_level": row[7],
        "url": normalize_url(row[8]),
        "status": row[9],
    }


def _run_scraper_pipeline(
    role_keys: list[str],
    locations: list[str],
    portal_names: list[str],
    days: int = 14,
) -> tuple[list[JobPosting], dict[str, str]]:
    now = datetime.now(WIB)
    client = HttpClient(min_delay=1.5, max_delay=3.0)
    portal_status_map: dict[str, str] = {p.lower(): "pending" for p in portal_names}
    _scrape_state["portal_status"] = dict(portal_status_map)

    def _on_portal_status(platform_label: str, state: str) -> None:
        key = PORTAL_KEY_MAP.get(platform_label.lower(), platform_label.lower())
        portal_status_map[key] = state
        _scrape_state["portal_status"] = dict(portal_status_map)
        active = [k for k, v in portal_status_map.items() if v == "scraping"]
        done = [k for k, v in portal_status_map.items() if v == "done"]
        if active:
            _scrape_state["current_step"] = (
                f"Scraping paralel ({len(done)}/{len(portal_status_map)} selesai): "
                f"aktif {', '.join(active)}..."
            )

    try:
        scrapers = build_scrapers(
            portal_names,
            client=client,
            days=days,
            now=now,
            use_playwright=True,
        )
        roles = [ROLES[k] for k in role_keys if k in ROLES]
        target_locs = locations or SEARCH_LOCATIONS
        return run_scrapers(
            scrapers=scrapers,
            roles=roles,
            locations=target_locs,
            status_callback=_on_portal_status,
            max_workers=7,
        )
    finally:
        client.close()


def _execute_scrape_job(req: ScrapeRequest) -> dict[str, Any]:
    started_ts = time.time()
    now = datetime.now(WIB)
    _scrape_state["is_running"] = True
    _scrape_state["started_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    _scrape_state["finished_at"] = None
    _scrape_state["portal_status"] = {p.lower(): "pending" for p in req.portals}
    _scrape_state["current_step"] = (
        f"Initializing parallel scraper for {', '.join(req.portals)}..."
    )

    try:
        postings, portal_summary = _run_scraper_pipeline(
            role_keys=req.roles,
            locations=req.locations,
            portal_names=req.portals,
            days=req.days,
        )

        _scrape_state["current_step"] = "Syncing results to cache & Google Sheets..."
        existing_jobs = _load_cache()
        if not existing_jobs:
            sheet_jobs = _try_load_from_sheets()
            if sheet_jobs is not None:
                existing_jobs = sheet_jobs

        seen_urls = {normalize_url(j.get("url", "")) for j in existing_jobs if j.get("url")}
        new_dicts: list[dict[str, str]] = []
        new_postings: list[JobPosting] = []

        for p in postings:
            norm = normalize_url(p.url)
            if not norm or norm in seen_urls:
                continue
            seen_urls.add(norm)
            p.url = norm
            new_postings.append(p)
            new_dicts.append(_posting_to_dict(p, now))

        merged = new_dicts + existing_jobs
        _save_cache(merged)
        sheets_added = _try_sync_to_sheets(new_postings)

        elapsed = round(time.time() - started_ts, 1)
        result = {
            "status": "completed",
            "new_jobs_count": len(new_dicts),
            "sheets_synced_count": sheets_added,
            "total_scraped": len(postings),
            "total_in_tracker": len(merged),
            "portal_summary": portal_summary,
            "portal_status": dict(_scrape_state.get("portal_status", {})),
            "elapsed_seconds": elapsed,
            "finished_at": datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S"),
        }
        _scrape_state["last_result"] = result
        _scrape_state["current_step"] = f"Completed ({len(new_dicts)} new jobs)"
        return result
    except Exception as exc:
        logger.exception("Scrape job failed: %s", exc)
        err_res = {
            "status": "error",
            "message": str(exc),
            "new_jobs_count": 0,
            "total_scraped": 0,
            "portal_status": dict(_scrape_state.get("portal_status", {})),
        }
        _scrape_state["last_result"] = err_res
        _scrape_state["current_step"] = f"Error: {exc}"
        return err_res
    finally:
        _scrape_state["is_running"] = False
        _scrape_state["finished_at"] = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")
        if _scrape_lock.locked():
            _scrape_lock.release()


@app.get("/api/health")
def health_check() -> dict[str, Any]:
    creds = _sheets_credentials()
    return {
        "status": "ok",
        "sheets_configured": creds is not None,
        "header_columns": HEADER,
        "supported_roles": {k: v.queries for k, v in ROLES.items()},
        "supported_portals": list(ALL_PORTALS),
    }


@app.get("/api/jobs")
def get_jobs(refresh_sheets: bool = Query(default=False)) -> dict[str, Any]:
    cached = _load_cache()
    source = "cache"

    if refresh_sheets or not cached:
        sheet_jobs = _try_load_from_sheets()
        if sheet_jobs is not None:
            if cached:
                by_url = {normalize_url(j["url"]): j for j in cached if j.get("url")}
                for sj in sheet_jobs:
                    by_url[normalize_url(sj["url"])] = sj
                cached = list(by_url.values())
            else:
                cached = sheet_jobs
            _save_cache(cached)
            source = "sheets"

    cached_sorted = sorted(
        cached,
        key=lambda j: (j.get("date_posted") or "", j.get("timestamp_scraped") or ""),
        reverse=True,
    )
    return {
        "jobs": cached_sorted,
        "count": len(cached_sorted),
        "source": source,
        "sheets_configured": _sheets_credentials() is not None,
    }


@app.get("/api/scrape/status")
def get_scrape_status() -> dict[str, Any]:
    return dict(_scrape_state)


@app.post("/api/scrape")
def trigger_scrape(req: ScrapeRequest) -> dict[str, Any]:
    valid_roles = [r for r in req.roles if r in ROLES]
    if not valid_roles:
        raise HTTPException(status_code=400, detail="Pilih minimal 1 target role yang valid.")
    valid_portals = [p.lower() for p in req.portals if p.lower() in set(ALL_PORTALS)]
    if not valid_portals:
        raise HTTPException(status_code=400, detail="Pilih minimal 1 portal yang valid.")
    req.roles = valid_roles
    req.portals = valid_portals

    if not _scrape_lock.acquire(blocking=False):
        return {
            "status": "already_running",
            "message": _scrape_state.get("current_step", "Scraper sedang berjalan."),
            "portal_status": dict(_scrape_state.get("portal_status", {})),
            "new_jobs_count": 0,
        }

    _scrape_state["portal_status"] = {p: "pending" for p in valid_portals}

    if req.async_mode:
        thread = threading.Thread(target=_execute_scrape_job, args=(req,), daemon=True)
        thread.start()
        return {
            "status": "started",
            "message": "Scraper paralel dijalankan di background.",
            "portal_status": dict(_scrape_state["portal_status"]),
            "new_jobs_count": 0,
        }

    return _execute_scrape_job(req)


@app.patch("/api/jobs/status")
def update_job_status(req: StatusUpdateRequest) -> dict[str, Any]:
    new_status = req.status.strip()
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Status tidak valid. Gunakan salah satu dari: {', '.join(sorted(VALID_STATUSES))}",
        )

    target_norm = normalize_url(req.url)
    if not target_norm:
        raise HTTPException(status_code=400, detail="Job URL wajib diisi.")

    jobs = _load_cache()
    updated_job: dict[str, str] | None = None
    for job in jobs:
        if normalize_url(job.get("url", "")) == target_norm:
            job["status"] = new_status
            updated_job = job
            break

    if updated_job is None:
        raise HTTPException(status_code=404, detail="Lowongan tidak ditemukan di cache.")

    _save_cache(jobs)
    synced_to_sheet = _try_update_sheet_status(target_norm, new_status)

    return {
        "status": "ok",
        "job": updated_job,
        "synced_to_sheets": synced_to_sheet,
    }
