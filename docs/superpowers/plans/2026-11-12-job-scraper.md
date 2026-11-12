# LokerBang Job Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command scrapes ≤14-day-old System Analyst (entry) and IoT Engineer jobs in Bandung/Jakarta/Bodetabek from LinkedIn, Jobstreet ID, and Glints ID, and appends only new rows to the `Job_Tracker` Google Sheet.

**Architecture:** Single `scraper.py`. Layers are pure helpers (date, location, role, URL), then `HttpClient` (httpx + UA rotation + delay + backoff), then three `BaseScraper` subclasses returning `JobPosting`, then `SheetsSync` (dedup + one `append_rows`), then the `main()` CLI. Pure logic is unit-tested with pytest using saved HTML/JSON fixtures. Network and Sheets are mocked in tests and checked live with `--dry-run`.

**Tech Stack:** Python 3.10+ (machine has 3.13), httpx 0.28, beautifulsoup4, python-dateutil, gspread 6, google-auth, python-dotenv, playwright (Glints only), pytest.

**Spec:** `docs/superpowers/specs/2026-11-12-job-scraper-design.md`

## Global Constraints

- Sheet name `Job_Tracker`. Header exactly: `Timestamp_Scraped, Job_Title, Company, Location, Platform, Date_Posted, Experience_Level, Job_URL, Status`.
- `Status` default `"New"`. Existing rows are never modified.
- Writes use one `worksheet.append_rows(rows, value_input_option="RAW")` per run.
- `Date_Posted` = `YYYY-MM-DD`. `Timestamp_Scraped` = `YYYY-MM-DD HH:MM:SS` in Asia/Jakarta (UTC+7, a fixed offset so no tzdata dependency on Windows).
- Delay between requests: `random.uniform(2, 5)` seconds. Retry on 429/5xx/network errors with exponential backoff `base=2s`, `max_retries=4`, plus jitter.
- `.env` keys: `SERVICE_ACCOUNT_FILE`, `SPREADSHEET_ID` (optional `SHEET_NAME`, default `Job_Tracker`).
- Platform labels: `LinkedIn`, `Jobstreet`, `Glints`.
- Not a git repo, so commit steps are skipped. Each task ends with green tests instead.

## Review Focus

1. **Portal schema drift or block mid-run:** that portal logs an error and returns `[]`, other portals still run, and the summary shows the failure. Test: `test_run_continues_when_one_portal_raises` (Task 6).
2. **Indonesian relative dates** ("2 jam yang lalu", "1 minggu yang lalu", "kemarin", "30+ hari yang lalu") parse correctly or return `None`, never raise. Test: `test_parse_relative_date_id_phrases` (Task 1).
3. **Same job via tracking-param URL variants** (`?position=1&refId=...`, `?trackingId=`) is normalized so it is not appended twice. Test: `test_normalize_url_strips_tracking` (Task 1), `test_sync_skips_existing_normalized_url` (Task 5).
4. **Empty sheet / sheet missing / header-only sheet:** creates the sheet or header and dedups against nothing without crashing. Test: `test_sync_creates_worksheet_and_header` (Task 5).
5. **Senior titles leaking into Role A** ("Senior System Analyst", "Lead", "Manager", "5 tahun"): dropped, while "Not specified" is kept. Test: `test_role_a_seniority_filter` (Task 1).

---

### Task 1: Scaffolding + pure helpers

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt` (`-r requirements.txt` + `pytest`), `.env.example`, `.gitignore` (`.env`, `*.json` creds, `logs/`, `__pycache__/`), `scraper.py` (helpers section), `tests/test_helpers.py`

**Interfaces — Produces (in `scraper.py`):**
- `WIB = timezone(timedelta(hours=7))`
- `@dataclass JobPosting(title: str, company: str, location: str, platform: str, url: str, date_posted: date | None, experience_level: str = "Not specified")` with `to_row(scraped_at: datetime) -> list[str]` (9 columns in header order, `Status="New"`, date `""` when None)
- `ROLES: dict[str, RoleConfig]` keys `"system_analyst"`, `"iot_engineer"`. `RoleConfig(name, queries: list[str], entry_only: bool, title_patterns: list[re.Pattern])`
- `parse_relative_date(text: str, now: datetime) -> date | None`: EN + ID relative phrases, ISO strings via `dateutil.parser`
- `is_within_days(d: date | None, now: datetime, days: int) -> bool` (None → False)
- `match_location(loc: str) -> bool`: case-insensitive match on bandung, jakarta, tangerang, tangerang selatan, bsd, serpong, bekasi, cikarang, depok, bogor. Explicitly rejects `cimahi` and `bandung barat`.
- `match_title(title: str, role: RoleConfig) -> bool`
- `classify_experience(text: str) -> str`: returns `"Entry/Fresh Graduate"`, `"Junior"`, `"Senior"`, `"Lead/Manager"`, `"Mid"`, a `"N-M yrs"` string, or `"Not specified"`
- `passes_role_a_seniority(title: str, experience_level: str) -> bool`: drops Senior / Lead/Manager / min years ≥ 3
- `normalize_url(url: str) -> str`: lowercase host, strip query + fragment for LinkedIn (`/jobs/view/<slug>-<id>` → `https://www.linkedin.com/jobs/view/<id>`), keep the path only for Jobstreet/Glints

- [ ] **Step 1: Write failing tests** in `tests/test_helpers.py`, with `now = datetime(2026,11,12,10,0,tzinfo=WIB)`:
  - `test_parse_relative_date_en`: "3 days ago"→2026-11-09, "2 hours ago"→2026-11-12, "1 week ago"→2026-11-05, "2026-11-05"→2026-11-05
  - `test_parse_relative_date_id_phrases`: "6 hari yang lalu"→11-06, "2 jam yang lalu"→11-12, "1 minggu yang lalu"→11-05, "kemarin"→11-11, "30+ hari yang lalu"→10-13, "garbage"→None
  - `test_is_within_days`: 11-05 True, 10-28 True (exactly 14), 10-27 False, None False
  - `test_match_location`: True for "Jakarta Selatan, Jakarta Raya", "Bekasi, Jawa Barat", "Kota Bandung", "Tangerang Selatan", "Cikarang"; False for "Cimahi", "Bandung Barat", "Surabaya", "Indonesia"
  - `test_match_title`: SA role True for "Junior System Analyst", "Analis Sistem", "Systems Analyst"; False for "Business Analyst". IoT role True for "IoT Engineer", "Internet of Things Engineer", "Hardware & IoT Engineer", "Embedded Hardware Engineer"; False for "Hardware Sales"
  - `test_role_a_seniority_filter`: ("Senior System Analyst","Not specified")→False, ("System Analyst Lead","Not specified")→False, ("System Analyst","3-5 yrs")→False, ("System Analyst","Not specified")→True, ("Junior System Analyst","Junior")→True, ("System Analyst","0-2 yrs")→True
  - `test_classify_experience`: "Fresh Graduate"→"Entry/Fresh Graduate", "Entry level"→"Entry/Fresh Graduate", "Associate"→"Junior", "Mid-Senior level"→"Senior", "Director"→"Lead/Manager", "1-3 tahun"→"1-3 yrs", ""→"Not specified"
  - `test_normalize_url_strips_tracking`: `https://id.linkedin.com/jobs/view/system-analyst-at-pt-elnusa-tbk-4487719677?position=1&refId=x` → `https://www.linkedin.com/jobs/view/4487719677`; `https://id.jobstreet.com/id/job/95720018?type=standard#x` → `https://id.jobstreet.com/id/job/95720018`
  - `test_job_posting_to_row`: 9 items, `[0]=="2026-11-12 10:00:00"`, `[5]=="2026-11-05"`, `[8]=="New"`; with `date_posted=None`, `[5]==""`
- [ ] **Step 2:** `pip install -r requirements-dev.txt`, then `pytest tests/test_helpers.py -v` → FAIL (ImportError)
- [ ] **Step 3:** Implement the helpers in `scraper.py`. Relative dates: regex `(\d+)\+?\s*(minute|menit|hour|jam|day|hari|week|minggu|month|bulan)` → `relativedelta`, plus special cases "just now/baru saja/today/hari ini"→today and "yesterday/kemarin"→−1 day. Fall back to `dateutil.parser.parse` in try/except → None.
- [ ] **Step 4:** `pytest tests/test_helpers.py -v` → all PASS

### Task 2: HttpClient (UA rotation, delay, backoff)

**Files:** Modify `scraper.py`. Test `tests/test_http.py`

**Interfaces — Produces:**
- `class BlockedError(Exception)`
- `class HttpClient(min_delay=2.0, max_delay=5.0, max_retries=4, backoff_base=2.0, sleep=time.sleep)` with methods `get(url, **kw) -> httpx.Response`, `post(url, **kw) -> httpx.Response`, and `close()`. It rotates through ≥5 desktop UAs (Chrome/Edge/Firefox on Win/Mac) and sends `Accept-Language: id-ID,id;q=0.9,en;q=0.8`. It sleeps a random delay before every request except the first. It raises `BlockedError` on 403, or on 200 HTML containing "Firewall" / "cf-challenge" / "Just a moment". It retries on 429/5xx/`httpx.TransportError` with sleep `backoff_base**attempt + uniform(0,1)` and raises after `max_retries`.

- [ ] **Step 1: Failing tests** using `httpx.MockTransport` and an injected recording `sleep`:
  - `test_retries_then_succeeds`: responses 503, 429, then 200 → 200 returned and 2 backoff sleeps recorded, with values ≥2 and ≥4
  - `test_raises_after_max_retries`: always 500 → `httpx.HTTPStatusError`
  - `test_403_raises_blocked`, `test_firewall_html_raises_blocked`
  - `test_delay_between_requests_in_range`: second call records a sleep between 2 and 5
  - `test_user_agent_rotates`: over 10 calls, more than 1 distinct UA is seen
- [ ] **Step 2:** `pytest tests/test_http.py -v` → FAIL
- [ ] **Step 3:** Implement. The constructor also accepts `transport: httpx.BaseTransport | None` for tests. Timeout is 20 s and `follow_redirects=True`.
- [ ] **Step 4:** `pytest tests/test_http.py -v` → PASS

### Task 3: LinkedInScraper + JobstreetScraper

**Files:** Modify `scraper.py`. Test `tests/test_scrapers.py`. Fixtures `tests/fixtures/linkedin_search.html`, `tests/fixtures/jobstreet_search.json` (captured live during this task, trimmed to 2–3 jobs)

**Interfaces:**
- Consumes: `HttpClient`, `JobPosting`, `RoleConfig`, the Task 1 helpers
- Produces: `class BaseScraper(ABC)` with `platform: str`, `__init__(client: HttpClient, days: int, now: datetime)`, abstract `search(query: str, location: str, role: RoleConfig) -> list[JobPosting]`, and concrete `collect(role: RoleConfig, locations: list[str]) -> list[JobPosting]`. `collect` loops queries × locations, applies the common filters (`match_title`, `match_location`, date rule, Role A seniority), and dedups by `normalize_url`.
- Date rule inside `collect`: keep when `is_within_days(...)`, or when `date_posted is None and self.server_side_date_filter`. LinkedIn and Jobstreet set `server_side_date_filter = True`.
- `LinkedInScraper.parse_cards(html: str) -> list[JobPosting]` and `JobstreetScraper.parse_results(data: dict) -> list[JobPosting]` are pure and tested with the fixtures.
- Search locations per scraper: `SEARCH_LOCATIONS = ["Bandung", "Jakarta"]`. LinkedIn uses `"Bandung, West Java, Indonesia"` and `"Jakarta, Indonesia"` (the Jakarta search covers Bodetabek). Jobstreet uses `where="Bandung"` and `where="Jakarta Raya"`, plus extra `where` values `"Bekasi"`, `"Tangerang"`, `"Depok"`, `"Bogor"`.

LinkedIn: GET `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search` with params `keywords, location, f_TPR=r{days*86400}, start` (0, 25, 50…, at most 4 pages, stop on an empty page), plus `f_E=1,2` when `role.entry_only`. Card selectors: `div.base-search-card`, title `h3.base-search-card__title`, company `h4.base-search-card__subtitle`, location `span.job-search-card__location`, date `time[datetime]` (`datetime` attribute, falling back to text), URL `a.base-card__full-link[href]`. `experience_level`: `"Entry/Junior (LinkedIn filter)"` when entry_only, else `classify_experience(title)`.

Jobstreet: GET `https://id.jobstreet.com/api/jobsearch/v5/search` with params `siteKey=ID-Main, sourcesystem=houston, keywords, where, daterange=days, page, pageSize=30, locale=id-ID` (at most 3 pages, stop when `data` is empty). Field mapping: `title`, `companyName` (falling back to `advertiser.description`), `locations[0].label`, `listingDate` (ISO; fall back to parsing `listingDateDisplay`), URL `https://id.jobstreet.com/id/job/{id}`, `experience_level = classify_experience(title + " " + teaser)`. If the API fails, the scraper raises (no HTML fallback). The spec's HTML fallback is dropped (YAGNI), because the live check showed the API returning 200.

- [ ] **Step 1:** Capture fixtures with a one-off httpx call and save them trimmed
- [ ] **Step 2: Failing tests:**
  - `test_linkedin_parse_cards`: from the fixture, the first posting has title "System Analyst", company "PT Elnusa Tbk", location "Jakarta, Indonesia", date 2026-11-05, URL normalized to `https://www.linkedin.com/jobs/view/4487719677`
  - `test_jobstreet_parse_results`: first posting has title "System Analyst & Design", company "Nutech Integrasi", location "Jakarta Selatan, Jakarta Raya", date 2026-11-05, URL `https://id.jobstreet.com/id/job/95720018`
  - `test_collect_filters_and_dedups`: a stub scraper returning [valid, duplicate URL variant, Surabaya, 20-day-old, "Senior System Analyst"] → 1 result
  - `test_collect_keeps_undated_only_with_server_filter`
- [ ] **Step 3:** `pytest tests/test_scrapers.py -v` → FAIL
- [ ] **Step 4:** Implement
- [ ] **Step 5:** `pytest tests -v` → PASS

### Task 4: GlintsScraper (API attempt → Playwright fallback)

**Files:** Modify `scraper.py`. Test `tests/test_glints.py`. Fixture `tests/fixtures/glints_jobs.json`

**Interfaces:**
- Produces: `GlintsScraper(BaseScraper)` with `platform="Glints"`, `server_side_date_filter=False`, `__init__(..., use_playwright: bool = True)`, pure `parse_jobs(jobs: list[dict]) -> list[JobPosting]`
- `class PlaywrightUnavailable(Exception)`

Flow per `search`: first POST the GraphQL `searchJobsV3` to `https://glints.com/api/v2/graphql?op=searchJobsV3` through `HttpClient`. On `BlockedError` with `use_playwright`, call `_search_with_browser`. Otherwise log a warning and return `[]`. `_search_with_browser` does a lazy `from playwright.sync_api import sync_playwright` (ImportError → `PlaywrightUnavailable` → warning, return `[]`). It launches one headless Chromium per run (reused across searches, closed in `close()`), with a realistic UA, `locale="id-ID"`, `--disable-blink-features=AutomationControlled`, and an init script that hides `navigator.webdriver`. It opens `https://glints.com/id/opportunities/jobs/explore?keyword={q}&country=ID&locationName={loc}&lastUpdated=PAST_2_WEEKS`, captures the `searchJobsV3` GraphQL response via `page.on("response")`, and falls back to `__NEXT_DATA__` JSON. Verify the live behavior during this task and adjust the capture method to what works.

Field mapping (as in the GraphQL job object): `title`, `company.name`, location = `city.name` or `location.formattedName`, date = `updatedAt` or `createdAt` (ISO), URL `https://glints.com/id/opportunities/jobs/{slugify(title)}/{id}`, `experience_level` from `minYearsOfExperience`/`maxYearsOfExperience`: (0, ≤1) → "Entry/Fresh Graduate", else `"{min}-{max} yrs"`, missing → "Not specified".

- [ ] **Step 1: Failing tests:** `test_glints_parse_jobs` (fixture → title, company, location, date, URL, "1-3 yrs"), `test_glints_years_mapping` (0/1 → Entry; 3/5 → "3-5 yrs"; None → Not specified), `test_glints_returns_empty_when_blocked_and_no_playwright` (MockTransport 403, `use_playwright=False` → `[]`, no raise)
- [ ] **Step 2:** Run → FAIL
- [ ] **Step 3:** Implement. Run `playwright install chromium` if it is not already installed.
- [ ] **Step 4:** `pytest tests -v` → PASS
- [ ] **Step 5:** Live smoke test: `python -c "..."` calling `GlintsScraper(...).collect(ROLES['iot_engineer'], ['Jakarta'])` prints ≥0 results without exception. Record what worked.

### Task 5: SheetsSync

**Files:** Modify `scraper.py`. Test `tests/test_sheets.py`

**Interfaces:**
- Produces: `HEADER: list[str]` (exact Global Constraints order). `class SheetsSync(spreadsheet)` with `@classmethod from_env(service_account_file: str, spreadsheet_id: str, sheet_name: str = "Job_Tracker") -> SheetsSync` (uses `gspread.service_account(filename=...)` + `open_by_key`), `existing_urls() -> set[str]` (finds the `Job_URL` column by header name and normalizes each value), and `sync(postings: list[JobPosting], scraped_at: datetime) -> int` (returns the number appended; makes zero calls to `append_rows` when there is nothing new).
- Worksheet handling: get by title. On `gspread.WorksheetNotFound`, call `add_worksheet(title, rows=1000, cols=9)` and then `append_row(HEADER)`. If the sheet exists but row 1 is empty, write the header.

- [ ] **Step 1: Failing tests** with a `FakeSpreadsheet`/`FakeWorksheet` (in-memory rows, records calls):
  - `test_sync_creates_worksheet_and_header`: missing sheet → created and row 1 == HEADER
  - `test_sync_skips_existing_normalized_url`: the sheet holds the LinkedIn URL with tracking params, the posting has the clean URL → 0 appended, `append_rows` not called
  - `test_sync_appends_in_single_batch`: 3 new postings → exactly 1 `append_rows` call with 3 rows and `value_input_option="RAW"`
  - `test_sync_does_not_touch_existing_rows`: an existing row with Status "Applied" is unchanged afterwards
- [ ] **Step 2:** Run → FAIL
- [ ] **Step 3:** Implement
- [ ] **Step 4:** `pytest tests -v` → PASS

### Task 6: CLI orchestration, logging, README

**Files:** Modify `scraper.py`. Create `README.md`. Test `tests/test_main.py`

**Interfaces:**
- Produces: `run(scrapers: list[BaseScraper], roles: list[RoleConfig]) -> tuple[list[JobPosting], dict[str, str]]` (all postings deduped by normalized URL, plus a per-platform status of `"ok (N)"` or `"error: <msg>"`), and `main(argv: list[str] | None = None) -> int`.
- CLI args: `--dry-run`, `--no-playwright`, `--portals` (choices `linkedin,jobstreet,glints`, comma list, default all), `--roles` (`system_analyst,iot_engineer`, default both), `--days` (int, default 14), `-v/--verbose`.
- Logging: console + `logs/scraper.log` (RotatingFileHandler, 1 MB × 3). Format `%(asctime)s %(levelname)s [%(name)s] %(message)s`.
- `.env` is loaded via `load_dotenv()`. A missing `SERVICE_ACCOUNT_FILE`/`SPREADSHEET_ID` without `--dry-run` → log an error and exit code 2. Dry-run prints a table (platform, date, title, company, location) and the count.
- Exit code 0 when at least one portal succeeded, 1 when all failed.

README.md content (Indonesian): what the tool does; setup (`pip install -r requirements.txt`, `playwright install chromium`, copy `.env.example`→`.env`); the Service Account guide (create a GCP project → enable Google Sheets API + Google Drive API → create a Service Account → Keys → JSON → save it in the project folder → open the JSON and copy `client_email` → share the spreadsheet with that email as Editor → copy the spreadsheet ID from the URL `/d/<ID>/edit`); usage examples; a scheduling note for Windows Task Scheduler.

- [ ] **Step 1: Failing tests:**
  - `test_run_continues_when_one_portal_raises`: stub A raises RuntimeError, stub B returns 2 → 2 postings, status A starts with "error", B == "ok (2)"
  - `test_main_dry_run_does_not_touch_sheets` (monkeypatch `SheetsSync.from_env` to raise if called; stub scrapers via monkeypatched `build_scrapers`) → exit 0
  - `test_main_missing_env_exits_2`
- [ ] **Step 2:** Run → FAIL
- [ ] **Step 3:** Implement `build_scrapers(names: list[str], client: HttpClient, days: int, now: datetime, use_playwright: bool) -> list[BaseScraper]`, `run`, `main`, and `if __name__ == "__main__": sys.exit(main())`. Write README.md.
- [ ] **Step 4:** `pytest tests -v` → all PASS
- [ ] **Step 5:** Live check: `python scraper.py --dry-run` → finishes, prints results from LinkedIn and Jobstreet (Glints: results or a clear warning), exit 0, and `logs/scraper.log` is created.
