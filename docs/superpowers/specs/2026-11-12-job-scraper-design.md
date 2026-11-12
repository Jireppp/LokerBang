# LokerBang — Job Scraper → Google Sheets (Design)

Date: 2026-11-12

## Intent
A personal job-hunting tool. One command scrapes fresh job postings (≤ 14 days old)
from LinkedIn, Jobstreet ID, and Glints ID for two target roles in Bandung & Jakarta,
and appends only *new* postings to a Google Sheet (`Job_Tracker`) the user uses as an
application tracker. Run manually on a Windows laptop now; must be schedulable later
(Task Scheduler / GitHub Actions / VPS) without code changes.

## Goals
- Role A: "System Analyst" — entry level only (fresh graduate / junior / 0–2 yrs).
- Role B: "IoT Engineer" / "Internet of Things Engineer" / "Hardware & IoT" — any level.
- Locations: Bandung (Jawa Barat), Jakarta (DKI Jakarta) + Bodetabek (see decisions).
- Time window: posted ≤ 14 days before run time; older postings dropped.
- Sheet `Job_Tracker` with header
  `[Timestamp_Scraped, Job_Title, Company, Location, Platform, Date_Posted, Experience_Level, Job_URL, Status]`.
- Dedup on `Job_URL` against existing sheet rows; single `append_rows` batch call.
- Anti-ban: random 2–5 s sleep between requests, exponential backoff retry, UA rotation.
- Config via `.env` (`SERVICE_ACCOUNT_FILE`, `SPREADSHEET_ID`).

## Non-goals
- No login / personal cookies for any portal.
- No full job description scraping, no detail pages unless needed for date/level.
- No database, no UI, no notifications (may come later).

## Anti-goals (failure even if it "works")
- Overwriting or reordering rows the user edited (esp. `Status`).
- Duplicate rows for the same job.
- One portal failing kills the whole run.
- Burning Sheets API quota with per-row writes.

## Constraints
- Python 3.10+, Windows-friendly (no bash-only tooling).
- Deps: `httpx`, `python-dateutil`, `gspread`, `google-auth`, `python-dotenv`,
  optional `playwright` (fallback only).
- Deliverables: `requirements.txt`, `.env.example`, `scraper.py`, setup guide (README).

## Approaches considered
- **A. Single class-based `scraper.py`, httpx-first, Playwright fallback** — CHOSEN.
  Fast/light, matches requested single-file format, light for future scheduling.
- B. Playwright for everything — most block-resistant, but 5–10× slower and
  ~150 MB Chromium; heavy for CI scheduling.
- C. Multi-module package — cleaner at scale, but user asked for one `scraper.py`;
  A's class split makes later extraction trivial.

## Design (decided)
- `JobPosting` dataclass = common output schema of every scraper.
- `HttpClient`: httpx wrapper with UA rotation, realistic headers, random 2–5 s delay,
  exponential backoff (retry on 429/5xx/network errors), detects block (403/Cloudflare).
- `BaseScraper` (abstract `search(query, location) -> list[JobPosting]`) with
  `LinkedInScraper`, `JobstreetScraper`, `GlintsScraper`.
  - LinkedIn: guest endpoint `jobs-guest/jobs/api/seeMoreJobPostings/search`,
    `f_TPR=r1209600` (14 d), `f_E=1,2` for Role A, pagination via `start`, parse HTML cards.
  - Jobstreet: internal JSON search API with `daterange=14` / `createdAt=14d`;
    HTML parse as fallback.
  - Glints: public GraphQL search; Playwright fallback when blocked (Cloudflare).
- `PlaywrightFallback`: lazily imported; if missing, log warning and skip that portal.
- Post-filters applied uniformly: date ≤ 14 d, location matches Bandung/Jakarta/Bodetabek,
  Role A seniority filter (keep entry/junior/0–2 yrs; drop senior/lead/manager/≥3 yrs),
  title relevance to keywords. Relative dates ("3 days ago", "2 jam lalu", "1 minggu
  yang lalu") parsed via dateutil + regex for EN & ID phrases.
- In-run dedup by normalized URL (strip tracking query params).
- `SheetsSync`: opens spreadsheet by ID, creates `Job_Tracker` with header if missing,
  reads `Job_URL` column once, appends only new rows via one `append_rows`
  (`value_input_option="RAW"`). `Status` defaults to `"New"`; existing rows never touched.
- CLI: `--dry-run` (print, no Sheets write), `--no-playwright`, `--portals` subset,
  `--days` (default 14). Logging to console + `logs/scraper.log`. Non-interactive.
- Per-portal try/except: a failing portal is logged and skipped; summary at end.

## Decisions from review (user)
- Role A postings with no stated seniority are KEPT, `Experience_Level = "Not specified"`.
  No detail-page requests for level.
- Locations: Bandung, Jakarta, and Bodetabek (Tangerang, Tangerang Selatan, BSD,
  Bekasi, Cikarang, Depok, Bogor). NOT Cimahi/Bandung Barat, NOT remote/"Indonesia"-only.
- User never deletes rows; they change `Status`. Dedup against current `Job_URL`
  column only — no seen-history store.

## Decisions from review (builder's calls — user may override)
- Cross-portal duplicates (same job on LinkedIn + Jobstreet) are kept as separate rows:
  different URLs, and seeing where a job is posted is useful.
- Dates written as plain ISO strings with `value_input_option="RAW"` (locale-proof,
  sorts correctly): `Date_Posted = YYYY-MM-DD`, `Timestamp_Scraped = YYYY-MM-DD HH:MM:SS`
  in WIB (Asia/Jakarta, UTC+7).
- Unparseable/missing date: keep only if the portal already enforced the 14-day filter
  server-side (LinkedIn `f_TPR`, Jobstreet `daterange`); `Date_Posted` left empty.
  Otherwise drop.
- Role A title match: "system analyst", "systems analyst", "analis sistem",
  "IT system analyst", "system analis". Excludes pure "Business Analyst".
- Role B title match: "iot", "internet of things", "hardware" + ("iot"|"engineer"|"embedded").

## Left to the builder
- Exact GraphQL query/operation shape for Glints and current Jobstreet API params
  (verify against live site at build time).
- HTML selectors for LinkedIn cards.
- Pagination depth caps (sensible default, e.g. ≤ 5 pages / query).
