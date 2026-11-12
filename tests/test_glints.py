from datetime import date, datetime
import json
from pathlib import Path
import httpx

from scraper import (
    WIB,
    GlintsScraper,
    HttpClient,
    ROLES,
)

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=WIB)
FIXTURES = Path(__file__).parent / "fixtures"


def test_glints_parse_jobs():
    jobs = json.loads((FIXTURES / "glints_jobs.json").read_text(encoding="utf-8"))
    client = HttpClient(sleep=lambda _: None)
    scraper = GlintsScraper(client=client, days=14, now=NOW, use_playwright=False)
    postings = scraper.parse_jobs(jobs)
    client.close()

    assert len(postings) == 2
    first = postings[0]
    assert first.title == "System Analyst (Fresh Graduate)"
    assert first.company == "PT Glints Karya Indonesia"
    assert first.location == "Jakarta Selatan, DKI Jakarta"
    assert first.date_posted == date(2026, 11, 9)
    assert first.url == (
        "https://glints.com/id/opportunities/jobs/"
        "system-analyst-fresh-graduate/d4e5f6a7-1234-5678-9abc-def012345678"
    )
    assert first.experience_level == "1-3 yrs"
    assert first.platform == "Glints"

    second = postings[1]
    assert second.location == "Bandung, Jawa Barat"
    assert second.date_posted == date(2026, 11, 10)
    assert second.experience_level == "Entry/Fresh Graduate"


def test_glints_years_mapping():
    client = HttpClient(sleep=lambda _: None)
    scraper = GlintsScraper(client=client, days=14, now=NOW, use_playwright=False)
    assert scraper.format_years(0, 1, "System Analyst") == "Entry/Fresh Graduate"
    assert scraper.format_years(0, 0, "System Analyst") == "Entry/Fresh Graduate"
    assert scraper.format_years(3, 5, "System Analyst") == "3-5 yrs"
    assert scraper.format_years(None, None, "Junior System Analyst") == "Junior"
    assert scraper.format_years(None, None, "System Analyst") == "Not specified"
    client.close()


def test_glints_returns_empty_when_blocked_and_no_playwright():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    client = HttpClient(
        sleep=lambda _: None,
        transport=httpx.MockTransport(handler),
    )
    scraper = GlintsScraper(client=client, days=14, now=NOW, use_playwright=False)
    res = scraper.search("System Analyst", "Jakarta", ROLES["system_analyst"])
    assert res == []
    client.close()
