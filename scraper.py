from __future__ import annotations

from abc import ABC, abstractmethod
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import random
import re
import sys
import threading
import time
from typing import Any, Callable
from urllib.parse import parse_qs, quote_plus, urlsplit

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
import gspread
import httpx

logger = logging.getLogger("lokerbang")

WIB = timezone(timedelta(hours=7))

ALL_PORTALS: tuple[str, ...] = (
    "linkedin",
    "jobstreet",
    "glints",
    "kalibrr",
    "dealls",
    "techinasia",
    "indeed",
)


@dataclass(frozen=True)
class RoleConfig:
    name: str
    queries: list[str]
    entry_only: bool
    title_patterns: list[re.Pattern[str]]


ROLES: dict[str, RoleConfig] = {
    "system_analyst": RoleConfig(
        name="System Analyst",
        queries=[
            "System Analyst",
            "Junior System Analyst",
            "IT Business Analyst",
            "Functional Analyst",
        ],
        entry_only=True,
        title_patterns=[
            re.compile(r"\bsystems?\s+analyst\b", re.IGNORECASE),
            re.compile(r"\banalis\s+sistem\b", re.IGNORECASE),
            re.compile(r"\bsystems?\s+analis\b", re.IGNORECASE),
            re.compile(r"\bit\s+business\s+analyst\b", re.IGNORECASE),
            re.compile(r"\bfunctional\s+analyst\b", re.IGNORECASE),
        ],
    ),
    "iot_engineer": RoleConfig(
        name="IoT Engineer",
        queries=[
            "IoT Engineer",
            "Internet of Things Engineer",
            "Embedded Engineer",
            "Automation & IoT",
        ],
        entry_only=True,
        title_patterns=[
            re.compile(r"\biot\b", re.IGNORECASE),
            re.compile(r"\binternet\s+of\s+things\b", re.IGNORECASE),
            re.compile(r"\bembedded\b.*\b(engineer|developer|iot|hardware|system)\b", re.IGNORECASE),
            re.compile(r"\bautomation\b.*\biot\b|\biot\b.*\bautomation\b", re.IGNORECASE),
            re.compile(
                r"\bhardware\b.*\b(iot|engineer|embedded)\b|\b(iot|embedded)\b.*\bhardware\b",
                re.IGNORECASE,
            ),
        ],
    ),
    "it_support": RoleConfig(
        name="IT Support",
        queries=[
            "IT Support",
            "IT Helpdesk",
            "Technical Support",
            "Desktop Support",
        ],
        entry_only=True,
        title_patterns=[
            re.compile(r"\bit\s+support\b", re.IGNORECASE),
            re.compile(r"\bit\s+help\s*desk\b|\bhelp\s*desk\b.*\bit\b", re.IGNORECASE),
            re.compile(r"\btechnical\s+support\b", re.IGNORECASE),
            re.compile(r"\bdesktop\s+support\b", re.IGNORECASE),
        ],
    ),
    "product_support": RoleConfig(
        name="Product Support",
        queries=[
            "Product Support",
            "Application Support",
            "SaaS Support",
            "Product Operations Support",
        ],
        entry_only=True,
        title_patterns=[
            re.compile(r"\bproduct\s+support\b", re.IGNORECASE),
            re.compile(r"\bapplication\s+support\b|\bapp\s+support\b", re.IGNORECASE),
            re.compile(r"\bsaas\s+support\b", re.IGNORECASE),
            re.compile(r"\bproduct\s+operations\s+support\b", re.IGNORECASE),
        ],
    ),
    "technical_writer": RoleConfig(
        name="Technical Writer",
        queries=[
            "Technical Writer",
            "Product Technical Writer",
            "IT Documentation Specialist",
            "Technical Content Writer",
        ],
        entry_only=True,
        title_patterns=[
            re.compile(r"\btechnical\s+writer\b", re.IGNORECASE),
            re.compile(r"\bproduct\s+technical\s+writer\b", re.IGNORECASE),
            re.compile(r"\bit\s+documentation\b|\bdocumentation\s+specialist\b", re.IGNORECASE),
            re.compile(r"\btechnical\s+content\s+writer\b", re.IGNORECASE),
        ],
    ),
}


def match_title(title: str | None, role: RoleConfig) -> bool:
    if not title:
        return False
    return any(p.search(title) for p in role.title_patterns)


def infer_role_category(title: str | None) -> str:
    if not title:
        return "System Analyst"
    for role in ROLES.values():
        if match_title(title, role):
            return role.name
    return "System Analyst"


@dataclass
class JobPosting:
    title: str
    company: str
    location: str
    platform: str
    url: str
    date_posted: date | None
    experience_level: str = "Not specified"
    role_category: str = ""

    def to_row(self, scraped_at: datetime) -> list[str]:
        ts = scraped_at.astimezone(WIB).strftime("%Y-%m-%d %H:%M:%S")
        posted = self.date_posted.isoformat() if self.date_posted else ""
        category = self.role_category.strip() or infer_role_category(self.title)
        return [
            ts,
            category,
            self.title.strip(),
            self.company.strip(),
            self.location.strip(),
            self.platform.strip(),
            posted,
            self.experience_level.strip() or "Not specified",
            self.url.strip(),
            "New",
        ]


_RELATIVE_RE = re.compile(
    r"(\d+)\+?\s*(minutes?|menit|hours?|jam|days?|hari|weeks?|minggu|months?|bulan)\b",
    re.IGNORECASE,
)
_TODAY_RE = re.compile(
    r"\b(just\s+now|baru\s+saja|today|hari\s+ini|active\s+today|baru\s+ditayangkan)\b",
    re.IGNORECASE,
)
_YESTERDAY_RE = re.compile(r"\b(yesterday|kemarin)\b", re.IGNORECASE)


def parse_relative_date(text: str | None, now: datetime) -> date | None:
    if not text or not text.strip():
        return None
    s = text.strip()
    today = now.astimezone(WIB).date()

    if _TODAY_RE.search(s):
        return today
    if _YESTERDAY_RE.search(s):
        return today - timedelta(days=1)

    m = _RELATIVE_RE.search(s)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith(("minute", "menit", "hour", "jam")):
            dt = now.astimezone(WIB) - timedelta(
                hours=amount if unit.startswith(("hour", "jam")) else 0,
                minutes=amount if unit.startswith(("minute", "menit")) else 0,
            )
            return dt.date()
        if unit.startswith(("day", "hari")):
            return today - timedelta(days=amount)
        if unit.startswith(("week", "minggu")):
            return today - timedelta(weeks=amount)
        if unit.startswith(("month", "bulan")):
            return (now.astimezone(WIB) - relativedelta(months=amount)).date()

    # Only fall back to dateutil if string looks like it contains digits (a date/timestamp)
    if not re.search(r"\d{4}|\d{1,2}[/-]\d{1,2}", s):
        return None
    try:
        dt = dateutil_parser.parse(s)
        if dt.tzinfo is not None:
            return dt.astimezone(WIB).date()
        return dt.date()
    except (ValueError, OverflowError, TypeError):
        return None


def is_within_days(d: date | None, now: datetime, days: int) -> bool:
    if d is None:
        return False
    today = now.astimezone(WIB).date()
    delta = (today - d).days
    return 0 <= delta <= days


_EXCLUDED_LOCATION_RE = re.compile(r"\b(cimahi|bandung\s+barat)\b", re.IGNORECASE)
_ALLOWED_LOCATION_RE = re.compile(
    r"\b(bandung|jakarta|tangerang|tangerang\s+selatan|tangsel|bsd|serpong|bekasi|cikarang|depok|bogor|jabodetabek)\b",
    re.IGNORECASE,
)


def match_location(loc: str | None) -> bool:
    if not loc:
        return False
    if _EXCLUDED_LOCATION_RE.search(loc):
        return False
    return bool(_ALLOWED_LOCATION_RE.search(loc))


_YEARS_RANGE_RE = re.compile(
    r"(\d+)\s*(?:-|–|to|sampai|s/d)\s*(\d+)\s*(?:years?|yrs?|tahun|thn)\b",
    re.IGNORECASE,
)
_YEARS_MIN_RE = re.compile(
    r"(?:min(?:imal|\.)?\s*|at\s+least\s*)?(\d+)\+?\s*(?:years?|yrs?|tahun|thn)\b",
    re.IGNORECASE,
)
_ENTRY_RE = re.compile(
    r"\b(fresh\s*grad(?:uate)?|entry[\s-]*level|lulusan\s+baru|intern(?:ship)?)\b",
    re.IGNORECASE,
)
_JUNIOR_RE = re.compile(r"\b(junior|jr\.?|associate|staff)\b", re.IGNORECASE)
_LEAD_RE = re.compile(
    r"\b(lead|leader|manager|mgr|head|director|principal|vp|chief|supervisor)\b",
    re.IGNORECASE,
)
_SENIOR_RE = re.compile(r"\b(senior|sr\.?|mid[\s-]*senior)\b", re.IGNORECASE)


def classify_experience(text: str | None) -> str:
    if not text or not text.strip():
        return "Not specified"
    s = text.strip()
    m_range = _YEARS_RANGE_RE.search(s)
    if m_range:
        return f"{int(m_range.group(1))}-{int(m_range.group(2))} yrs"
    m_min = _YEARS_MIN_RE.search(s)
    if m_min and ("+" in m_min.group(0) or int(m_min.group(1)) >= 3):
        return f"{int(m_min.group(1))}+ yrs"
    if _LEAD_RE.search(s):
        return "Lead/Manager"
    if _SENIOR_RE.search(s):
        return "Senior"
    if _ENTRY_RE.search(s):
        return "Entry/Fresh Graduate"
    if _JUNIOR_RE.search(s):
        return "Junior"
    if m_min:
        yrs = int(m_min.group(1))
        return "Entry/Fresh Graduate" if yrs <= 1 else f"{yrs}+ yrs"
    return "Not specified"


def passes_role_a_seniority(title: str, experience_level: str) -> bool:
    combined = f"{title} {experience_level}"
    if _LEAD_RE.search(combined) or _SENIOR_RE.search(combined):
        return False
    for m_range in _YEARS_RANGE_RE.finditer(combined):
        if int(m_range.group(1)) >= 3:
            return False
    stripped = _YEARS_RANGE_RE.sub("", combined)
    for m_min in _YEARS_MIN_RE.finditer(stripped):
        if int(m_min.group(1)) >= 3:
            return False
    return True


_LINKEDIN_ID_RE = re.compile(r"/jobs/view/(?:[^/?#]*?-)?(\d+)/?$")


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    path = parts.path.rstrip("/")
    if "linkedin.com" in host:
        m = _LINKEDIN_ID_RE.search(path)
        if m:
            return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
        return f"https://www.linkedin.com{path}"
    if "indeed.com" in host:
        qs = parse_qs(parts.query)
        jk = (qs.get("jk") or qs.get("vjk") or [""])[0].strip()
        if jk:
            return f"https://{host}/viewjob?jk={jk}"
    scheme = parts.scheme.lower() or "https"
    return f"{scheme}://{host}{path}"


class BlockedError(Exception):
    """Raised when the target site blocks the request (403 / WAF / Cloudflare)."""


USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
]

_BLOCK_HTML_RE = re.compile(
    r"(Glints\s*-\s*Firewall|cf-challenge|Just a moment\.\.\.|Attention Required!\s*\|\s*Cloudflare)",
    re.IGNORECASE,
)


class HttpClient:
    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_retries: int = 4,
        backoff_base: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep
        self._transport = transport
        self._first_request = True
        self._ua_index = random.randrange(len(USER_AGENTS))
        self._lock = threading.Lock()
        self._client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            transport=transport,
        )

    def _next_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        with self._lock:
            ua = USER_AGENTS[self._ua_index % len(USER_AGENTS)]
            self._ua_index += 1
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        }
        if extra:
            headers.update(extra)
        return headers

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        with self._lock:
            is_first = self._first_request
            self._first_request = False
        if not is_first and self.max_delay > 0:
            self._sleep(random.uniform(self.min_delay, self.max_delay))

        extra_headers = kwargs.pop("headers", None)
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 2):
            headers = self._next_headers(extra_headers)
            try:
                resp = self._client.request(method, url, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt > self.max_retries:
                    raise
                self._sleep((self.backoff_base ** attempt) + random.uniform(0.0, 1.0))
                continue

            if resp.status_code == 403 or _BLOCK_HTML_RE.search(resp.text[:2000]):
                raise BlockedError(f"Blocked ({resp.status_code}) on {url}")

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt > self.max_retries:
                    resp.raise_for_status()
                self._sleep((self.backoff_base ** attempt) + random.uniform(0.0, 1.0))
                continue

            resp.raise_for_status()
            return resp

        assert last_exc is not None
        raise last_exc

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self._client.close()


SEARCH_LOCATIONS: list[str] = ["Bandung", "Jakarta"]


class BaseScraper(ABC):
    platform: str = ""
    server_side_date_filter: bool = False

    def __init__(
        self,
        client: HttpClient,
        days: int = 14,
        now: datetime | None = None,
    ) -> None:
        self.client = client
        self.days = days
        self.now = now or datetime.now(WIB)

    @abstractmethod
    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        raise NotImplementedError

    def target_locations(self, locations: list[str]) -> list[str]:
        return locations

    def collect(self, role: RoleConfig, locations: list[str] | None = None) -> list[JobPosting]:
        locs = self.target_locations(locations or SEARCH_LOCATIONS)
        seen_urls: set[str] = set()
        results: list[JobPosting] = []

        for loc in locs:
            for query in role.queries:
                raw_items = self.search(query, loc, role)
                for item in raw_items:
                    norm_url = normalize_url(item.url)
                    if not norm_url or norm_url in seen_urls:
                        continue
                    if not match_title(item.title, role):
                        continue
                    if not match_location(item.location):
                        continue
                    if item.date_posted is not None:
                        if not is_within_days(item.date_posted, self.now, self.days):
                            continue
                    elif not self.server_side_date_filter:
                        continue
                    if role.entry_only and not passes_role_a_seniority(item.title, item.experience_level):
                        continue

                    item.url = norm_url
                    if not item.role_category:
                        item.role_category = role.name
                    seen_urls.add(norm_url)
                    results.append(item)

        return results

    def close(self) -> None:
        pass


class LinkedInScraper(BaseScraper):
    platform = "LinkedIn"
    server_side_date_filter = True
    ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    MAX_PAGES = 2

    _LOC_MAP = {
        "bandung": "Bandung, West Java, Indonesia",
        "jakarta": "Jakarta, Indonesia",
    }

    def target_locations(self, locations: list[str]) -> list[str]:
        return [self._LOC_MAP.get(loc.lower(), loc) for loc in locations]

    def parse_cards(self, html: str, entry_only: bool = False) -> list[JobPosting]:
        if not html or not html.strip():
            return []
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.base-search-card")
        postings: list[JobPosting] = []

        for card in cards:
            title_el = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle")
            loc_el = card.select_one("span.job-search-card__location")
            link_el = card.select_one("a.base-card__full-link[href]")
            time_el = card.select_one("time")

            if not (title_el and company_el and loc_el and link_el):
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True)
            location = loc_el.get_text(strip=True)
            raw_url = str(link_el.get("href", "")).strip()
            url = normalize_url(raw_url)

            date_str = ""
            if time_el:
                date_str = str(time_el.get("datetime") or time_el.get_text(strip=True))
            posted = parse_relative_date(date_str, self.now)

            exp = classify_experience(title)
            if exp == "Not specified" and entry_only:
                exp = "Entry/Junior (LinkedIn filter)"

            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    platform=self.platform,
                    url=url,
                    date_posted=posted,
                    experience_level=exp,
                )
            )
        return postings

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        seconds = self.days * 86400
        collected: list[JobPosting] = []

        for page in range(self.MAX_PAGES):
            params: dict[str, Any] = {
                "keywords": query,
                "location": location,
                "f_TPR": f"r{seconds}",
                "start": page * 25,
            }
            if role.entry_only:
                params["f_E"] = "1,2"

            resp = self.client.get(self.ENDPOINT, params=params)
            batch = self.parse_cards(resp.text, entry_only=role.entry_only)
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < 20:
                break

        return collected


class JobstreetScraper(BaseScraper):
    platform = "Jobstreet"
    server_side_date_filter = True
    ENDPOINT = "https://id.jobstreet.com/api/jobsearch/v5/search"
    MAX_PAGES = 2

    def target_locations(self, locations: list[str]) -> list[str]:
        mapped: list[str] = []
        for loc in locations:
            low = loc.lower()
            if low == "bandung":
                mapped.append("Bandung")
            elif low == "jakarta":
                mapped.extend(["Jakarta Raya", "Bekasi", "Tangerang", "Depok", "Bogor"])
            else:
                mapped.append(loc)
        return mapped

    def parse_results(self, data: dict[str, Any]) -> list[JobPosting]:
        items = data.get("data") or []
        postings: list[JobPosting] = []

        for item in items:
            job_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not (job_id and title):
                continue

            company = str(
                item.get("companyName")
                or (item.get("advertiser") or {}).get("description")
                or (item.get("employer") or {}).get("name")
                or "Unknown"
            ).strip()

            locs = item.get("locations") or []
            location = str(locs[0].get("label") if locs else "").strip()

            raw_date = str(item.get("listingDate") or item.get("listingDateDisplay") or "")
            posted = parse_relative_date(raw_date, self.now)

            teaser = str(item.get("teaser") or "")
            bullets = " ".join(item.get("bulletPoints") or [])
            exp = classify_experience(f"{title} {teaser} {bullets}")

            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    platform=self.platform,
                    url=f"https://id.jobstreet.com/id/job/{job_id}",
                    date_posted=posted,
                    experience_level=exp,
                )
            )
        return postings

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        collected: list[JobPosting] = []

        for page in range(1, self.MAX_PAGES + 1):
            params: dict[str, Any] = {
                "siteKey": "ID-Main",
                "sourcesystem": "houston",
                "keywords": query,
                "where": location,
                "daterange": self.days,
                "page": page,
                "pageSize": 30,
                "locale": "id-ID",
            }
            resp = self.client.get(self.ENDPOINT, params=params)
            data = resp.json()
            batch = self.parse_results(data)
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < 30:
                break

        return collected


class PlaywrightUnavailable(Exception):
    """Raised when playwright is not installed or Chromium cannot launch."""


_SLUG_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_NON_ALNUM_RE.sub("-", text.lower()).strip("-") or "job"


class GlintsScraper(BaseScraper):
    platform = "Glints"
    server_side_date_filter = False
    ENDPOINT = "https://glints.com/api/v2-alc/graphql?op=searchJobsV3"

    _GQL_QUERY = """
    query searchJobsV3($data: JobSearchConditionInput!) {
      searchJobsV3(data: $data) {
        jobsInPage {
          id
          title
          createdAt
          updatedAt
          company { name }
          city { name }
          location {
            formattedName
            parents { formattedName level }
          }
          minYearsOfExperience
          maxYearsOfExperience
        }
      }
    }
    """

    def __init__(
        self,
        client: HttpClient,
        days: int = 14,
        now: datetime | None = None,
        use_playwright: bool = True,
    ) -> None:
        super().__init__(client=client, days=days, now=now)
        self.use_playwright = use_playwright
        self._api_blocked = False
        self._pw_cm: Any = None
        self._browser: Any = None
        self._context: Any = None

    @staticmethod
    def format_years(min_yrs: int | None, max_yrs: int | None, title: str = "") -> str:
        if min_yrs is not None and max_yrs is not None:
            if min_yrs == 0 and max_yrs <= 1:
                return "Entry/Fresh Graduate"
            if min_yrs == 0 and max_yrs >= 20:
                return classify_experience(title)
            if max_yrs < min_yrs:
                return f"{min_yrs}+ yrs"
            return f"{min_yrs}-{max_yrs} yrs"
        if min_yrs is not None:
            if min_yrs <= 1:
                return "Entry/Fresh Graduate"
            return f"{min_yrs}+ yrs"
        return classify_experience(title)

    @staticmethod
    def _extract_location(job: dict[str, Any]) -> str:
        loc_obj = job.get("location") or {}
        city_obj = job.get("city") or {}
        formatted = str(loc_obj.get("formattedName") or "").strip()
        city_name = str(city_obj.get("name") or "").strip()
        parents = loc_obj.get("parents") or []

        parts: list[str] = []
        if formatted:
            parts.append(formatted)
        if city_name and city_name.lower() not in formatted.lower():
            parts.append(city_name)
        for p in parents:
            pname = str((p or {}).get("formattedName") or "").strip()
            if pname and pname.lower() != "indonesia" and all(pname.lower() not in x.lower() for x in parts):
                parts.append(pname)
        return ", ".join(parts)

    def parse_jobs(self, jobs: list[dict[str, Any]]) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for job in jobs or []:
            job_id = str(job.get("id") or "").strip()
            title = str(job.get("title") or "").strip()
            if not (job_id and title):
                continue

            company = str((job.get("company") or {}).get("name") or "Unknown").strip()
            location = self._extract_location(job)
            raw_date = str(job.get("updatedAt") or job.get("createdAt") or "")
            posted = parse_relative_date(raw_date, self.now)

            min_y = job.get("minYearsOfExperience")
            max_y = job.get("maxYearsOfExperience")
            exp = self.format_years(min_y, max_y, title)

            slug = _slugify(title)
            url = f"https://glints.com/id/opportunities/jobs/{slug}/{job_id}"
            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    platform=self.platform,
                    url=url,
                    date_posted=posted,
                    experience_level=exp,
                )
            )
        return postings

    def _search_via_api(self, query: str, location: str) -> list[JobPosting]:
        payload = {
            "operationName": "searchJobsV3",
            "variables": {
                "data": {
                    "SearchTerm": f"{query} {location}".strip(),
                    "CountryCode": "ID",
                    "includeExternalJobs": True,
                    "pageSize": 30,
                    "page": 1,
                    "lastUpdatedAtRange": "PAST_2_WEEKS",
                }
            },
            "query": self._GQL_QUERY,
        }
        resp = self.client.post(
            self.ENDPOINT,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://glints.com",
                "Referer": "https://glints.com/id/opportunities/jobs/explore",
            },
        )
        data = resp.json()
        jobs = ((data.get("data") or {}).get("searchJobsV3") or {}).get("jobsInPage") or []
        return self.parse_jobs(jobs)

    def _ensure_browser(self) -> Any:
        if self._context is not None:
            return self._context
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PlaywrightUnavailable("playwright is not installed") from exc

        try:
            self._pw_cm = sync_playwright().start()
            self._browser = self._pw_cm.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = self._browser.new_context(
                user_agent=USER_AGENTS[0],
                locale="id-ID",
            )
            self._context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            return self._context
        except Exception as exc:
            self.close()
            raise PlaywrightUnavailable(f"Failed to start Chromium: {exc}") from exc

    def _search_with_browser(self, query: str, location: str) -> list[JobPosting]:
        ctx = self._ensure_browser()
        page = ctx.new_page()
        captured_jobs: list[dict[str, Any]] = []

        def on_response(resp: Any) -> None:
            if "graphql" in resp.url and resp.status == 200:
                try:
                    body = resp.json()
                    block = (body.get("data") or {}).get("searchJobsV3") or (body.get("data") or {}).get("searchJobs")
                    if block and isinstance(block.get("jobsInPage"), list):
                        captured_jobs.extend(block["jobsInPage"])
                except Exception:
                    pass

        page.on("response", on_response)
        try:
            kw = quote_plus(f"{query} {location}".strip())
            explore_url = (
                f"https://glints.com/id/opportunities/jobs/explore"
                f"?keyword={kw}&country=ID&locationName=All+Cities%2FProvinces"
            )
            page.goto(explore_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            initial = page.evaluate(
                """() => {
                    try {
                        return window.__NEXT_DATA__.props.pageProps.initialJobs.jobsInPage || [];
                    } catch (e) {
                        return [];
                    }
                }"""
            )
            if isinstance(initial, list):
                captured_jobs.extend(initial)
        finally:
            page.close()

        return self.parse_jobs(captured_jobs)

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        if not self._api_blocked:
            try:
                return self._search_via_api(query, location)
            except BlockedError:
                self._api_blocked = True
                if not self.use_playwright:
                    logger.warning("Glints blocked HTTP request and Playwright fallback is disabled.")
                    return []
                logger.info("Glints HTTP blocked; falling back to Playwright for '%s' (%s)", query, location)

        if not self.use_playwright:
            return []
        try:
            return self._search_with_browser(query, location)
        except PlaywrightUnavailable as exc:
            logger.warning("Playwright unavailable for Glints: %s", exc)
            return []

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw_cm is not None:
            try:
                self._pw_cm.stop()
            except Exception:
                pass
            self._pw_cm = None


class KalibrrScraper(BaseScraper):
    platform = "Kalibrr"
    server_side_date_filter = False
    ENDPOINT = "https://www.kalibrr.com/kjs/job_board/search"

    def target_locations(self, locations: list[str]) -> list[str]:
        # Kalibrr public search API takes free-text `text` query and returns
        # structured `google_location.address_components`; querying once per
        # keyword avoids redundant duplicate pages while `collect()` filters
        # by `match_location`.
        return [locations[0]] if locations else [""]

    @staticmethod
    def _extract_location(item: dict[str, Any]) -> str:
        gloc = item.get("google_location") or {}
        comp = gloc.get("address_components") or {}
        parts = [
            str(comp.get("city") or "").strip(),
            str(comp.get("region") or "").strip(),
            str(comp.get("address_line_1") or "").strip(),
        ]
        cleaned = [p for p in parts if p]
        return ", ".join(cleaned)

    @staticmethod
    def _extract_experience(item: dict[str, Any], title: str) -> str:
        if item.get("is_open_to_fresh_grads"):
            return "Entry/Fresh Graduate"
        work_exp = item.get("work_experience")
        if isinstance(work_exp, int):
            if work_exp <= 12:
                return "Entry/Fresh Graduate"
            years = work_exp // 12 if work_exp >= 12 else work_exp
            if years <= 1:
                return "Entry/Fresh Graduate"
            if years == 2:
                return "1-2 yrs"
            return f"{years}+ yrs"
        return classify_experience(title)

    def parse_results(self, data: dict[str, Any]) -> list[JobPosting]:
        jobs = data.get("jobs") or []
        postings: list[JobPosting] = []

        for item in jobs:
            job_id = str(item.get("id") or "").strip()
            title = str(item.get("name") or item.get("title") or "").strip()
            if not (job_id and title):
                continue

            company_info = item.get("company_info") or item.get("company") or {}
            company = str(
                item.get("company_name")
                or company_info.get("name")
                or "Unknown"
            ).strip()
            company_code = str(company_info.get("code") or _slugify(company)).strip()
            slug = str(item.get("slug") or _slugify(title)).strip()

            location = self._extract_location(item)
            raw_date = str(item.get("activation_date") or item.get("created_at") or "")
            posted = parse_relative_date(raw_date, self.now)
            exp = self._extract_experience(item, title)

            url = f"https://www.kalibrr.com/c/{company_code}/jobs/{job_id}/{slug}"
            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    platform=self.platform,
                    url=url,
                    date_posted=posted,
                    experience_level=exp,
                )
            )

        return postings

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        params: dict[str, Any] = {
            "limit": 25,
            "offset": 0,
            "text": query,
        }
        resp = self.client.get(self.ENDPOINT, params=params)
        return self.parse_results(resp.json())


class DeallsScraper(BaseScraper):
    platform = "Dealls"
    server_side_date_filter = False
    API_ENDPOINT = "https://api.sejutacita.id/v1/explore-job/job"
    WEB_ENDPOINT = "https://dealls.com/loker"

    def target_locations(self, locations: list[str]) -> list[str]:
        return [locations[0]] if locations else [""]

    def parse_results(self, data: dict[str, Any]) -> list[JobPosting]:
        block = data.get("data") if isinstance(data.get("data"), dict) else data
        docs = (block or {}).get("docs") or []
        postings: list[JobPosting] = []

        for doc in docs:
            if not isinstance(doc, dict):
                continue
            slug = str(doc.get("slug") or "").strip()
            title = str(doc.get("role") or doc.get("title") or "").strip()
            if not (slug and title):
                continue

            comp_obj = doc.get("company") or {}
            company = str(
                comp_obj.get("name") if isinstance(comp_obj, dict) else comp_obj or "Unknown"
            ).strip()
            comp_slug = str(
                comp_obj.get("slug") if isinstance(comp_obj, dict) else ""
            ).strip()

            city_obj = doc.get("city") or {}
            city_name = str(
                city_obj.get("name") if isinstance(city_obj, dict) else city_obj or ""
            ).strip()
            loc_str = city_name or str(doc.get("location") or "").strip()

            raw_date = str(
                doc.get("publishedAt")
                or doc.get("createdAt")
                or doc.get("updatedAt")
                or ""
            )
            posted = parse_relative_date(raw_date, self.now)

            pref = doc.get("candidatePreference") or {}
            pref_exp = str(pref.get("experience") or "") if isinstance(pref, dict) else ""
            exp = classify_experience(f"{title} {pref_exp}")

            url = (
                f"https://dealls.com/loker/{slug}~{comp_slug}"
                if comp_slug
                else f"https://dealls.com/loker/{slug}"
            )
            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=loc_str,
                    platform=self.platform,
                    url=url,
                    date_posted=posted,
                    experience_level=exp,
                )
            )

        return postings

    def parse_next_data_html(self, html: str) -> list[JobPosting]:
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return []
        try:
            payload = json.loads(script.string)
            queries = (
                ((payload.get("props") or {}).get("pageProps") or {})
                .get("dehydratedState", {})
                .get("queries")
                or []
            )
            docs: list[dict[str, Any]] = []
            for q in queries:
                pages = ((q.get("state") or {}).get("data") or {}).get("pages") or []
                for p in pages:
                    if isinstance(p, dict) and isinstance(p.get("docs"), list):
                        docs.extend(p["docs"])
            return self.parse_results({"docs": docs})
        except Exception:
            return []

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        params: dict[str, Any] = {
            "search": query,
            "limit": 20,
            "page": 1,
            "status": "active",
            "published": "true",
        }
        try:
            resp = self.client.get(self.API_ENDPOINT, params=params)
            return self.parse_results(resp.json())
        except Exception:
            resp = self.client.get(self.WEB_ENDPOINT, params={"search": query})
            return self.parse_next_data_html(resp.text)


class TechInAsiaScraper(BaseScraper):
    platform = "Tech in Asia"
    server_side_date_filter = False
    ENDPOINT = "https://www.techinasia.com/api/2.0/job-postings"
    MAX_PAGES = 2

    def __init__(
        self,
        client: HttpClient,
        days: int = 14,
        now: datetime | None = None,
    ) -> None:
        super().__init__(client=client, days=days, now=now)
        self._cached_feed: list[JobPosting] | None = None

    def target_locations(self, locations: list[str]) -> list[str]:
        return [locations[0]] if locations else [""]

    def parse_results(self, data: dict[str, Any]) -> list[JobPosting]:
        items = data.get("data") or []
        postings: list[JobPosting] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not (job_id and title):
                continue

            comp_obj = item.get("company") or {}
            company = str(comp_obj.get("name") or "Unknown").strip()

            city_obj = item.get("city") or {}
            location = str(city_obj.get("name") or "").strip()

            raw_date = str(
                item.get("published_at")
                or item.get("created_at")
                or item.get("updated_at")
                or ""
            )
            posted = parse_relative_date(raw_date, self.now)

            exp_min = item.get("experience_min")
            exp_max = item.get("experience_max")
            exp = GlintsScraper.format_years(exp_min, exp_max, title)

            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    platform=self.platform,
                    url=f"https://www.techinasia.com/jobs/{job_id}",
                    date_posted=posted,
                    experience_level=exp,
                )
            )

        return postings

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        if self._cached_feed is not None:
            return list(self._cached_feed)

        collected: list[JobPosting] = []
        for page in range(1, self.MAX_PAGES + 1):
            params: dict[str, Any] = {
                "country_name[]": "Indonesia",
                "per_page": 50,
                "page": page,
            }
            resp = self.client.get(self.ENDPOINT, params=params)
            batch = self.parse_results(resp.json())
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < 50:
                break

        self._cached_feed = collected
        return list(collected)


class IndeedScraper(BaseScraper):
    platform = "Indeed"
    server_side_date_filter = True
    ENDPOINT = "https://id.indeed.com/jobs"

    def __init__(
        self,
        client: HttpClient,
        days: int = 14,
        now: datetime | None = None,
        use_playwright: bool = True,
    ) -> None:
        super().__init__(client=client, days=days, now=now)
        self.use_playwright = use_playwright
        self._http_blocked = False
        self._pw_cm: Any = None
        self._browser: Any = None
        self._context: Any = None

    def parse_mosaic_cards(self, cards: list[dict[str, Any]]) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for card in cards or []:
            if not isinstance(card, dict):
                continue
            jk = str(card.get("jobkey") or "").strip()
            title = str(card.get("title") or card.get("displayTitle") or "").strip()
            if not (jk and title):
                continue

            company = str(card.get("company") or "Unknown").strip()
            location = str(card.get("formattedLocation") or card.get("jobLocationCity") or "").strip()

            posted: date | None = None
            rel_str = str(card.get("formattedRelativeTime") or "").strip()
            if rel_str:
                posted = parse_relative_date(rel_str, self.now)
            if posted is None and isinstance(card.get("pubDate"), (int, float)):
                dt = datetime.fromtimestamp(float(card["pubDate"]) / 1000.0, tz=WIB)
                posted = dt.date()

            exp = classify_experience(title)
            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    platform=self.platform,
                    url=f"https://id.indeed.com/viewjob?jk={jk}",
                    date_posted=posted,
                    experience_level=exp,
                )
            )
        return postings

    def parse_html(self, html: str) -> list[JobPosting]:
        if not html:
            return []
        m = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});',
            html,
            re.DOTALL,
        )
        if m:
            try:
                blob = json.loads(m.group(1))
                results = (
                    ((blob.get("metaData") or {}).get("mosaicProviderJobCardsModel") or {}).get("results")
                    or []
                )
                if results:
                    return self.parse_mosaic_cards(results)
            except Exception:
                pass

        soup = BeautifulSoup(html, "html.parser")
        postings: list[JobPosting] = []
        for card in soup.select("div.job_seen_beacon, td.resultContent"):
            title_el = card.select_one("h2.jobTitle, a.jcs-JobTitle")
            link_el = card.select_one("a[data-jk], a.jcs-JobTitle[href]")
            comp_el = card.select_one("span[data-testid='company-name']")
            loc_el = card.select_one("div[data-testid='text-location']")
            date_el = card.select_one("span[data-testid='myJobsStateDate'], span.date")
            if not (title_el and link_el):
                continue

            title = title_el.get_text(strip=True)
            jk = str(link_el.get("data-jk") or "").strip()
            href = str(link_el.get("href") or "").strip()
            url = (
                f"https://id.indeed.com/viewjob?jk={jk}"
                if jk
                else normalize_url(f"https://id.indeed.com{href}" if href.startswith("/") else href)
            )
            company = comp_el.get_text(strip=True) if comp_el else "Unknown"
            location = loc_el.get_text(strip=True) if loc_el else ""
            posted = parse_relative_date(date_el.get_text(strip=True) if date_el else "", self.now)
            postings.append(
                JobPosting(
                    title=title,
                    company=company,
                    location=location,
                    platform=self.platform,
                    url=url,
                    date_posted=posted,
                    experience_level=classify_experience(title),
                )
            )
        return postings

    def _ensure_browser(self) -> Any:
        if self._context is not None:
            return self._context
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PlaywrightUnavailable("playwright is not installed") from exc

        try:
            self._pw_cm = sync_playwright().start()
            self._browser = self._pw_cm.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = self._browser.new_context(
                user_agent=USER_AGENTS[0],
                locale="id-ID",
            )
            self._context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            return self._context
        except Exception as exc:
            self.close()
            raise PlaywrightUnavailable(f"Failed to start Chromium: {exc}") from exc

    def _search_with_browser(self, query: str, location: str) -> list[JobPosting]:
        ctx = self._ensure_browser()
        page = ctx.new_page()
        try:
            url = (
                f"{self.ENDPOINT}?q={quote_plus(query)}"
                f"&l={quote_plus(location)}&fromage={self.days}"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2000)
            mosaic = page.evaluate(
                """() => {
                    try {
                        return window.mosaic.providerData["mosaic-provider-jobcards"]
                            .metaData.mosaicProviderJobCardsModel.results || [];
                    } catch (e) {
                        return [];
                    }
                }"""
            )
            if isinstance(mosaic, list) and mosaic:
                return self.parse_mosaic_cards(mosaic)
            return self.parse_html(page.content())
        finally:
            page.close()

    def search(self, query: str, location: str, role: RoleConfig) -> list[JobPosting]:
        if not self._http_blocked:
            try:
                resp = self.client.get(
                    self.ENDPOINT,
                    params={"q": query, "l": location, "fromage": self.days},
                )
                return self.parse_html(resp.text)
            except BlockedError:
                self._http_blocked = True
                if not self.use_playwright:
                    logger.warning("Indeed blocked HTTP request and Playwright fallback is disabled.")
                    return []
                logger.info("Indeed HTTP blocked; falling back to Playwright for '%s' (%s)", query, location)

        if not self.use_playwright:
            return []
        try:
            return self._search_with_browser(query, location)
        except PlaywrightUnavailable as exc:
            logger.warning("Playwright unavailable for Indeed: %s", exc)
            return []

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw_cm is not None:
            try:
                self._pw_cm.stop()
            except Exception:
                pass
            self._pw_cm = None


HEADER: list[str] = [
    "Timestamp_Scraped",
    "Role_Category",
    "Job_Title",
    "Company",
    "Location",
    "Platform",
    "Date_Posted",
    "Experience_Level",
    "Job_URL",
    "Status",
]


class SheetsSync:
    def __init__(self, spreadsheet: Any, sheet_name: str = "Job_Tracker") -> None:
        self.spreadsheet = spreadsheet
        self.sheet_name = sheet_name
        self.worksheet = self._ensure_worksheet()

    @classmethod
    def from_env(
        cls,
        service_account_file: str,
        spreadsheet_id: str,
        sheet_name: str = "Job_Tracker",
    ) -> "SheetsSync":
        gc = gspread.service_account(filename=service_account_file)
        sp = gc.open_by_key(spreadsheet_id)
        return cls(sp, sheet_name=sheet_name)

    def _ensure_worksheet(self) -> Any:
        try:
            ws = self.spreadsheet.worksheet(self.sheet_name)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=self.sheet_name, rows=1000, cols=len(HEADER))
            ws.append_row(HEADER, value_input_option="RAW")
            return ws

        rows = ws.get_all_values()
        if not rows or not any(cell.strip() for cell in rows[0]):
            ws.append_row(HEADER, value_input_option="RAW")
            return ws

        current_header = [cell.strip() for cell in rows[0]]
        if "Role_Category" not in current_header:
            self._migrate_worksheet_to_10_cols(ws, current_header, rows[1:])
        return ws

    def _migrate_worksheet_to_10_cols(
        self,
        ws: Any,
        old_header: list[str],
        data_rows: list[list[str]],
    ) -> None:
        col_map = {name: idx for idx, name in enumerate(old_header)}

        def _get(row: list[str], name: str, fallback: int) -> str:
            idx = col_map.get(name, fallback)
            return row[idx].strip() if idx < len(row) else ""

        migrated: list[list[str]] = [list(HEADER)]
        for r in data_rows:
            if not any(c.strip() for c in r):
                continue
            title = _get(r, "Job_Title", 1)
            role_cat = _get(r, "Role_Category", -1) if "Role_Category" in col_map else infer_role_category(title)
            migrated.append(
                [
                    _get(r, "Timestamp_Scraped", 0),
                    role_cat or infer_role_category(title),
                    title,
                    _get(r, "Company", 2),
                    _get(r, "Location", 3),
                    _get(r, "Platform", 4),
                    _get(r, "Date_Posted", 5),
                    _get(r, "Experience_Level", 6) or "Not specified",
                    _get(r, "Job_URL", 7),
                    _get(r, "Status", 8) or "New",
                ]
            )

        try:
            ws.resize(rows=max(1000, len(migrated) + 100), cols=len(HEADER))
        except Exception:
            pass
        ws.update(migrated, value_input_option="RAW")
        logger.info(
            "Migrated worksheet '%s' to 10-column schema (%d existing row(s) preserved).",
            self.sheet_name,
            len(migrated) - 1,
        )

    def existing_urls(self) -> set[str]:
        rows = self.worksheet.get_all_values()
        if not rows:
            return set()
        header = [c.strip() for c in rows[0]]
        try:
            url_idx = header.index("Job_URL")
        except ValueError:
            url_idx = 8

        seen: set[str] = set()
        for row in rows[1:]:
            if len(row) > url_idx and row[url_idx].strip():
                seen.add(normalize_url(row[url_idx]))
        return seen

    def sync(self, postings: list[JobPosting], scraped_at: datetime | None = None) -> int:
        ts = scraped_at or datetime.now(WIB)
        seen = self.existing_urls()
        new_rows: list[list[str]] = []

        for p in postings:
            norm = normalize_url(p.url)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            p.url = norm
            new_rows.append(p.to_row(ts))

        if not new_rows:
            return 0

        self.worksheet.append_rows(new_rows, value_input_option="RAW")
        return len(new_rows)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    root = logging.getLogger("lokerbang")
    root.setLevel(level)
    root.handlers.clear()

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = RotatingFileHandler(
        log_dir / "scraper.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root.addHandler(fh)


def build_scrapers(
    names: list[str],
    client: HttpClient,
    days: int,
    now: datetime,
    use_playwright: bool = True,
) -> list[BaseScraper]:
    scrapers: list[BaseScraper] = []
    for name in names:
        key = name.strip().lower()
        if key == "linkedin":
            scrapers.append(LinkedInScraper(client=client, days=days, now=now))
        elif key == "jobstreet":
            scrapers.append(JobstreetScraper(client=client, days=days, now=now))
        elif key == "glints":
            scrapers.append(
                GlintsScraper(
                    client=client,
                    days=days,
                    now=now,
                    use_playwright=use_playwright,
                )
            )
        elif key == "kalibrr":
            scrapers.append(KalibrrScraper(client=client, days=days, now=now))
        elif key == "dealls":
            scrapers.append(DeallsScraper(client=client, days=days, now=now))
        elif key in ("techinasia", "tech_in_asia"):
            scrapers.append(TechInAsiaScraper(client=client, days=days, now=now))
        elif key == "indeed":
            scrapers.append(
                IndeedScraper(
                    client=client,
                    days=days,
                    now=now,
                    use_playwright=use_playwright,
                )
            )
        else:
            raise ValueError(f"Unknown portal: {name}")
    return scrapers


def run(
    scrapers: list[BaseScraper],
    roles: list[RoleConfig],
    locations: list[str] | None = None,
    status_callback: Callable[[str, str], None] | None = None,
    max_workers: int = 7,
) -> tuple[list[JobPosting], dict[str, str]]:
    target_locs = locations or SEARCH_LOCATIONS
    status_lock = threading.Lock()
    status_by_portal: dict[str, str] = {}
    portal_postings: dict[str, list[JobPosting]] = {}

    def _notify(portal_name: str, state: str) -> None:
        if status_callback is not None:
            with status_lock:
                status_callback(portal_name, state)

    for sc in scrapers:
        _notify(sc.platform, "pending")

    def _scrape_one(sc: BaseScraper) -> tuple[str, list[JobPosting], str]:
        _notify(sc.platform, "scraping")
        collected: list[JobPosting] = []
        seen_local: set[str] = set()
        try:
            for role in roles:
                logger.info("[%s] Searching role '%s'...", sc.platform, role.name)
                found = sc.collect(role, target_locs)
                for item in found:
                    norm = normalize_url(item.url)
                    if not norm or norm in seen_local:
                        continue
                    seen_local.add(norm)
                    item.url = norm
                    if not item.role_category:
                        item.role_category = role.name
                    collected.append(item)
            _notify(sc.platform, "done")
            logger.info("[%s] Done: %d unique postings collected.", sc.platform, len(collected))
            return sc.platform, collected, f"ok ({len(collected)})"
        except Exception as exc:
            _notify(sc.platform, "failed")
            logger.exception("[%s] Portal failed: %s", sc.platform, exc)
            return sc.platform, [], f"error: {exc}"
        finally:
            try:
                sc.close()
            except Exception:
                pass

    if scrapers:
        workers = max(1, min(max_workers, len(scrapers)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_scrape_one, sc): sc.platform for sc in scrapers}
            for fut in as_completed(futures):
                platform_name, items, summary = fut.result()
                portal_postings[platform_name] = items
                status_by_portal[platform_name] = summary

    seen_urls: set[str] = set()
    all_postings: list[JobPosting] = []
    for sc in scrapers:
        for item in portal_postings.get(sc.platform, []):
            norm = normalize_url(item.url)
            if not norm or norm in seen_urls:
                continue
            seen_urls.add(norm)
            item.url = norm
            all_postings.append(item)

    return all_postings, status_by_portal


def _print_dry_run(postings: list[JobPosting], status_by_portal: dict[str, str]) -> None:
    print(f"\n=== DRY RUN RESULTS ({len(postings)} postings) ===")
    for p in postings:
        d_str = p.date_posted.isoformat() if p.date_posted else "N/A       "
        cat = (p.role_category or infer_role_category(p.title))[:18]
        print(
            f"[{p.platform:<12}] {d_str} | {cat:<18} | {p.title[:36]:<36} | "
            f"{p.company[:24]:<24} | {p.location[:24]:<24} | {p.experience_level}"
        )
    print("\nPortal summary:", status_by_portal)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scrape entry-level IT jobs across 7 portals into Google Sheets."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to Google Sheets.")
    parser.add_argument("--no-playwright", action="store_true", help="Disable Playwright fallback for Glints/Indeed.")
    parser.add_argument(
        "--portals",
        default=",".join(ALL_PORTALS),
        help=f"Comma-separated portals: {','.join(ALL_PORTALS)} (default: all)",
    )
    parser.add_argument(
        "--roles",
        default=",".join(ROLES.keys()),
        help=f"Comma-separated roles: {','.join(ROLES.keys())} (default: all)",
    )
    parser.add_argument("--days", type=int, default=14, help="Max posting age in days (default: 14).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args(argv)

    setup_logging(verbose=args.verbose)
    load_dotenv()

    portal_names = [p.strip().lower() for p in args.portals.split(",") if p.strip()]
    role_keys = [r.strip().lower() for r in args.roles.split(",") if r.strip()]

    invalid_portals = [p for p in portal_names if p not in set(ALL_PORTALS)]
    if invalid_portals:
        logger.error("Invalid portal(s): %s", ", ".join(invalid_portals))
        return 2

    invalid_roles = [r for r in role_keys if r not in ROLES]
    if invalid_roles:
        logger.error("Invalid role(s): %s", ", ".join(invalid_roles))
        return 2

    sa_file = os.getenv("SERVICE_ACCOUNT_FILE", "").strip()
    spreadsheet_id = os.getenv("SPREADSHEET_ID", "").strip()
    sheet_name = os.getenv("SHEET_NAME", "Job_Tracker").strip() or "Job_Tracker"

    if not args.dry_run and (not sa_file or not spreadsheet_id):
        logger.error(
            "Missing SERVICE_ACCOUNT_FILE or SPREADSHEET_ID in environment/.env. "
            "Use --dry-run to test without Google Sheets."
        )
        return 2

    now = datetime.now(WIB)
    client = HttpClient(min_delay=1.5, max_delay=3.5)
    try:
        scrapers = build_scrapers(
            portal_names,
            client=client,
            days=args.days,
            now=now,
            use_playwright=not args.no_playwright,
        )
        roles = [ROLES[k] for k in role_keys]
        postings, status_by_portal = run(scrapers, roles)
    finally:
        client.close()

    any_ok = any(v.startswith("ok") for v in status_by_portal.values())

    if args.dry_run:
        _print_dry_run(postings, status_by_portal)
        return 0 if any_ok else 1

    try:
        syncer = SheetsSync.from_env(
            service_account_file=sa_file,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
        )
        added = syncer.sync(postings, scraped_at=now)
        logger.info(
            "Google Sheets sync complete: %d new row(s) appended (out of %d scraped). Summary: %s",
            added,
            len(postings),
            status_by_portal,
        )
    except Exception as exc:
        logger.exception("Failed to sync to Google Sheets: %s", exc)
        return 1

    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
