from datetime import date, datetime
import pytest

import scraper
from scraper import (
    WIB,
    BaseScraper,
    HttpClient,
    JobPosting,
    ROLES,
    RoleConfig,
    main,
    run,
)

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=WIB)


class _BrokenScraper(BaseScraper):
    platform = "Broken"

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        raise RuntimeError("portal down")

    def collect(self, role: RoleConfig, locations: list[str] | None = None) -> list[JobPosting]:
        raise RuntimeError("portal down")


class _WorkingScraper(BaseScraper):
    platform = "Working"

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        return []

    def collect(self, role: RoleConfig, locations: list[str] | None = None) -> list[JobPosting]:
        return [
            JobPosting(
                title="System Analyst",
                company="PT A",
                location="Jakarta",
                platform="Working",
                url="https://id.jobstreet.com/id/job/1",
                date_posted=date(2026, 11, 10),
            ),
            JobPosting(
                title="Junior System Analyst",
                company="PT B",
                location="Bandung",
                platform="Working",
                url="https://id.jobstreet.com/id/job/2",
                date_posted=date(2026, 11, 11),
            ),
        ]


def test_run_continues_when_one_portal_raises():
    client = HttpClient(sleep=lambda _: None)
    s_bad = _BrokenScraper(client=client, days=14, now=NOW)
    s_ok = _WorkingScraper(client=client, days=14, now=NOW)

    transitions: list[tuple[str, str]] = []

    def on_status(portal: str, st: str) -> None:
        transitions.append((portal, st))

    postings, status = run([s_bad, s_ok], [ROLES["system_analyst"]], status_callback=on_status)
    client.close()

    assert len(postings) == 2
    assert status["Broken"].startswith("error")
    assert status["Working"] == "ok (2)"
    assert ("Broken", "pending") in transitions
    assert ("Broken", "scraping") in transitions
    assert ("Broken", "failed") in transitions
    assert ("Working", "pending") in transitions
    assert ("Working", "scraping") in transitions
    assert ("Working", "done") in transitions


def test_build_scrapers_supports_all_7_portals():
    client = HttpClient(sleep=lambda _: None)
    all_names = ["linkedin", "jobstreet", "glints", "kalibrr", "dealls", "techinasia", "indeed"]
    scrapers = scraper.build_scrapers(all_names, client=client, days=14, now=NOW, use_playwright=False)
    for sc in scrapers:
        sc.close()
    client.close()
    assert [s.platform for s in scrapers] == [
        "LinkedIn",
        "Jobstreet",
        "Glints",
        "Kalibrr",
        "Dealls",
        "Tech in Asia",
        "Indeed",
    ]


def test_main_dry_run_does_not_touch_sheets(monkeypatch: pytest.MonkeyPatch):
    def forbid_sheets(*args, **kwargs):
        raise AssertionError("SheetsSync.from_env must not be called in --dry-run")

    def fake_build_scrapers(names, client, days, now, use_playwright):
        return [_WorkingScraper(client=client, days=days, now=now)]

    monkeypatch.setattr(scraper.SheetsSync, "from_env", forbid_sheets)
    monkeypatch.setattr(scraper, "build_scrapers", fake_build_scrapers)

    code = main(["--dry-run", "--portals", "jobstreet", "--roles", "system_analyst"])
    assert code == 0


def test_main_missing_env_exits_2(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.delenv("SPREADSHEET_ID", raising=False)
    monkeypatch.setattr(scraper, "load_dotenv", lambda *a, **kw: False)

    code = main(["--portals", "jobstreet"])
    assert code == 2
