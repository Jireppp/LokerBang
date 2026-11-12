from datetime import date, datetime
import json
from pathlib import Path

from scraper import (
    WIB,
    BaseScraper,
    DeallsScraper,
    HttpClient,
    IndeedScraper,
    JobPosting,
    JobstreetScraper,
    KalibrrScraper,
    LinkedInScraper,
    ROLES,
    RoleConfig,
    TechInAsiaScraper,
)

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=WIB)
FIXTURES = Path(__file__).parent / "fixtures"


def test_linkedin_parse_cards():
    html = (FIXTURES / "linkedin_search.html").read_text(encoding="utf-8")
    client = HttpClient(sleep=lambda _: None)
    scraper = LinkedInScraper(client=client, days=14, now=NOW)
    postings = scraper.parse_cards(html, entry_only=True)
    client.close()

    assert len(postings) == 2
    first = postings[0]
    assert first.title == "System Analyst"
    assert first.company == "PT Elnusa Tbk"
    assert first.location == "Jakarta, Indonesia"
    assert first.date_posted == date(2026, 11, 5)
    assert first.url == "https://www.linkedin.com/jobs/view/4487719677"
    assert first.platform == "LinkedIn"
    assert first.experience_level == "Entry/Junior (LinkedIn filter)"


def test_jobstreet_parse_results():
    data = json.loads((FIXTURES / "jobstreet_search.json").read_text(encoding="utf-8"))
    client = HttpClient(sleep=lambda _: None)
    scraper = JobstreetScraper(client=client, days=14, now=NOW)
    postings = scraper.parse_results(data)
    client.close()

    assert len(postings) == 2
    first = postings[0]
    assert first.title == "System Analyst & Design"
    assert first.company == "Nutech Integrasi"
    assert first.location == "Jakarta Selatan, Jakarta Raya"
    assert first.date_posted == date(2026, 11, 5)
    assert first.url == "https://id.jobstreet.com/id/job/95720018"
    assert first.platform == "Jobstreet"

    second = postings[1]
    assert second.company == "PT IoT Nusantara"
    assert second.date_posted == date(2026, 11, 10)
    assert second.experience_level == "Entry/Fresh Graduate"


class _StubScraper(BaseScraper):
    platform = "Stub"

    def __init__(self, items: list[JobPosting], server_filter: bool = True) -> None:
        client = HttpClient(sleep=lambda _: None)
        super().__init__(client=client, days=14, now=NOW)
        self._items = items
        self.server_side_date_filter = server_filter

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        return list(self._items)


def test_collect_filters_and_dedups():
    items = [
        # Valid
        JobPosting(
            title="Junior System Analyst",
            company="PT A",
            location="Jakarta Selatan",
            platform="Stub",
            url="https://id.linkedin.com/jobs/view/system-analyst-111?refId=x",
            date_posted=date(2026, 11, 10),
            experience_level="Junior",
        ),
        # Duplicate URL variant
        JobPosting(
            title="Junior System Analyst",
            company="PT A",
            location="Jakarta Selatan",
            platform="Stub",
            url="https://www.linkedin.com/jobs/view/111?trackingId=y",
            date_posted=date(2026, 11, 10),
            experience_level="Junior",
        ),
        # Excluded location (Surabaya)
        JobPosting(
            title="System Analyst",
            company="PT B",
            location="Surabaya, Jawa Timur",
            platform="Stub",
            url="https://www.linkedin.com/jobs/view/222",
            date_posted=date(2026, 11, 10),
        ),
        # Excluded > 14 days old
        JobPosting(
            title="System Analyst",
            company="PT C",
            location="Bandung",
            platform="Stub",
            url="https://www.linkedin.com/jobs/view/333",
            date_posted=date(2026, 10, 15),
        ),
        # Excluded Senior for Role A
        JobPosting(
            title="Senior System Analyst",
            company="PT D",
            location="Jakarta",
            platform="Stub",
            url="https://www.linkedin.com/jobs/view/444",
            date_posted=date(2026, 11, 10),
        ),
        # Excluded unrelated title
        JobPosting(
            title="Marketing Executive",
            company="PT E",
            location="Jakarta",
            platform="Stub",
            url="https://www.linkedin.com/jobs/view/555",
            date_posted=date(2026, 11, 10),
        ),
    ]
    scraper = _StubScraper(items, server_filter=True)
    result = scraper.collect(ROLES["system_analyst"], ["Jakarta"])
    scraper.client.close()

    assert len(result) == 1
    assert result[0].url == "https://www.linkedin.com/jobs/view/111"
    assert result[0].role_category == "System Analyst"


def test_kalibrr_parse_results():
    payload = {
        "jobs": [
            {
                "id": 275629,
                "name": "Junior System Analyst",
                "slug": "junior-system-analyst",
                "company_name": "PT Metrodata Electronics, Tbk",
                "company_info": {"code": "metrodata", "name": "PT Metrodata Electronics, Tbk"},
                "google_location": {
                    "address_components": {
                        "city": "Jakarta Barat",
                        "region": "DKI Jakarta",
                    }
                },
                "activation_date": "2026-11-10T04:15:45.408010+00:00",
                "is_open_to_fresh_grads": True,
                "work_experience": 1,
            }
        ]
    }
    client = HttpClient(sleep=lambda _: None)
    sc = KalibrrScraper(client=client, days=14, now=NOW)
    postings = sc.parse_results(payload)
    client.close()

    assert len(postings) == 1
    p = postings[0]
    assert p.title == "Junior System Analyst"
    assert p.company == "PT Metrodata Electronics, Tbk"
    assert "Jakarta Barat" in p.location
    assert p.platform == "Kalibrr"
    assert p.date_posted == date(2026, 11, 10)
    assert p.url == "https://www.kalibrr.com/c/metrodata/jobs/275629/junior-system-analyst"
    assert p.experience_level == "Entry/Fresh Graduate"


def test_dealls_parse_results():
    payload = {
        "data": {
            "docs": [
                {
                    "id": "6abb92e844cad40012300054",
                    "slug": "system-analyst-38",
                    "role": "System Analyst",
                    "company": {"name": "AMIT Global Solutions", "slug": "amit-global-solutions"},
                    "city": {"name": "Jakarta Selatan"},
                    "publishedAt": "2026-11-08T10:28:56.880Z",
                    "candidatePreference": {"experience": "0-2 years"},
                }
            ]
        }
    }
    client = HttpClient(sleep=lambda _: None)
    sc = DeallsScraper(client=client, days=14, now=NOW)
    postings = sc.parse_results(payload)
    client.close()

    assert len(postings) == 1
    p = postings[0]
    assert p.title == "System Analyst"
    assert p.company == "AMIT Global Solutions"
    assert p.location == "Jakarta Selatan"
    assert p.platform == "Dealls"
    assert p.date_posted == date(2026, 11, 8)
    assert p.url == "https://dealls.com/loker/system-analyst-38~amit-global-solutions"


def test_techinasia_parse_results():
    payload = {
        "data": [
            {
                "id": "708c2d26-7300-45f0-bb8d-79ece8d4151c",
                "title": "Technical Writer",
                "company": {"name": "Kumparan"},
                "city": {"name": "Jakarta"},
                "published_at": "2026-11-11 04:51:44",
                "experience_min": 0,
                "experience_max": 2,
            }
        ]
    }
    client = HttpClient(sleep=lambda _: None)
    sc = TechInAsiaScraper(client=client, days=14, now=NOW)
    postings = sc.parse_results(payload)
    client.close()

    assert len(postings) == 1
    p = postings[0]
    assert p.title == "Technical Writer"
    assert p.company == "Kumparan"
    assert p.location == "Jakarta"
    assert p.platform == "Tech in Asia"
    assert p.date_posted == date(2026, 11, 11)
    assert p.url == "https://www.techinasia.com/jobs/708c2d26-7300-45f0-bb8d-79ece8d4151c"
    assert p.experience_level == "0-2 yrs"


def test_indeed_parse_mosaic_cards():
    cards = [
        {
            "jobkey": "e933db10b1ec15d8",
            "title": "IT Support Specialist",
            "company": "HW Group",
            "formattedLocation": "Jakarta",
            "formattedRelativeTime": "2 hari yang lalu",
            "pubDate": 1794204000000,
        }
    ]
    client = HttpClient(sleep=lambda _: None)
    sc = IndeedScraper(client=client, days=14, now=NOW, use_playwright=False)
    postings = sc.parse_mosaic_cards(cards)
    client.close()

    assert len(postings) == 1
    p = postings[0]
    assert p.title == "IT Support Specialist"
    assert p.company == "HW Group"
    assert p.location == "Jakarta"
    assert p.platform == "Indeed"
    assert p.date_posted == date(2026, 11, 10)
    assert p.url == "https://id.indeed.com/viewjob?jk=e933db10b1ec15d8"


def test_collect_keeps_undated_only_with_server_filter():
    undated = JobPosting(
        title="IoT Engineer",
        company="PT A",
        location="Bekasi",
        platform="Stub",
        url="https://id.jobstreet.com/id/job/999",
        date_posted=None,
    )
    s_true = _StubScraper([undated], server_filter=True)
    assert len(s_true.collect(ROLES["iot_engineer"], ["Jakarta"])) == 1
    s_true.client.close()

    s_false = _StubScraper([undated], server_filter=False)
    assert len(s_false.collect(ROLES["iot_engineer"], ["Jakarta"])) == 0
    s_false.client.close()
