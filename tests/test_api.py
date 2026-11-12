from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from backend import api


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache_file = tmp_path / "jobs_cache.json"
    monkeypatch.setattr(api, "CACHE_FILE", cache_file)
    monkeypatch.setattr(api, "_try_load_from_sheets", lambda: None)
    monkeypatch.setattr(api, "_try_update_sheet_status", lambda url, status: False)
    monkeypatch.setattr(api, "_try_sync_to_sheets", lambda postings: 0)
    return cache_file


def test_get_jobs_empty_cache():
    client = TestClient(api.app)
    res = client.get("/api/jobs")
    assert res.status_code == 200
    body = res.json()
    assert body["jobs"] == []
    assert body["source"] == "cache"


def test_patch_job_status_updates_cache():
    sample = [
        {
            "timestamp_scraped": "2026-11-12 10:00:00",
            "title": "System Analyst",
            "company": "PT Elnusa Tbk",
            "location": "Jakarta, Indonesia",
            "platform": "LinkedIn",
            "date_posted": "2026-11-05",
            "experience_level": "Entry/Fresh Graduate",
            "url": "https://www.linkedin.com/jobs/view/4487719677",
            "status": "New",
        }
    ]
    api._save_cache(sample)

    client = TestClient(api.app)
    res = client.patch(
        "/api/jobs/status",
        json={
            "url": "https://www.linkedin.com/jobs/view/4487719677",
            "status": "Applied",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["job"]["status"] == "Applied"

    after = client.get("/api/jobs").json()["jobs"]
    assert after[0]["status"] == "Applied"


def test_post_scrape_runs_and_adds_new_jobs(monkeypatch: pytest.MonkeyPatch):
    from datetime import date
    from scraper import JobPosting

    def fake_execute_scrape(role_keys, locations, portal_names, days=14):
        api._scrape_state["portal_status"] = {p: "done" for p in portal_names}
        return (
            [
                JobPosting(
                    title="IoT Engineer",
                    company="PT Sensor Bandung",
                    location="Bandung, Jawa Barat",
                    platform="Kalibrr",
                    url="https://www.kalibrr.com/c/sensor/jobs/123/iot-engineer",
                    date_posted=date(2026, 11, 10),
                    experience_level="Entry/Fresh Graduate",
                    role_category="IoT Engineer",
                )
            ],
            {"Kalibrr": "ok (1)"},
        )

    monkeypatch.setattr(api, "_run_scraper_pipeline", fake_execute_scrape)

    client = TestClient(api.app)
    res = client.post(
        "/api/scrape",
        json={
            "roles": ["iot_engineer", "technical_writer"],
            "locations": ["Bandung"],
            "portals": ["kalibrr", "dealls", "techinasia", "indeed"],
            "async_mode": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["new_jobs_count"] == 1
    assert data["total_scraped"] == 1
    assert data["portal_status"]["kalibrr"] == "done"

    jobs = client.get("/api/jobs").json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["title"] == "IoT Engineer"
    assert jobs[0]["role_category"] == "IoT Engineer"
    assert jobs[0]["status"] == "New"
