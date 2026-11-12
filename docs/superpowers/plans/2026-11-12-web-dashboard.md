# LokerBang Web Dashboard & FastAPI Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide an interactive Modern SaaS Telemetry Web Dashboard (React + TypeScript + Tailwind) and lightweight FastAPI bridge (`backend/api.py`) allowing 1-click scraping execution, live telemetry status polling, KPI stats, search/filtering with table/card views, and inline application status updates synced to both `backend/jobs_cache.json` and Google Sheets.

**Architecture:**
- `backend/api.py`: FastAPI server running on port 8000 with CORS, background thread scraper execution with lock & live progress state, `/api/jobs` with dual-storage (Google Sheets + local `backend/jobs_cache.json` cache fallback), `/api/scrape` with status polling `/api/scrape/status`, and `/api/jobs/status` PATCH endpoint updating status in both cache and Google Sheet.
- `frontend/`: Vite + React + TypeScript + Tailwind CSS dashboard styled under Hallmark "Rim" modern-minimal telemetry theme (dark slate/warm black, Geist Mono tabular telemetry, high contrast, clean badges, crisp cards/table).
- Zero breaking changes to existing `scraper.py` and `tests/`.

## Tasks

- [ ] **Task 1: Backend API Bridge (`backend/api.py`) & Tests**
  - Create `backend/api.py` with endpoints:
    - `GET /api/health`
    - `GET /api/jobs` (returns `{ jobs: list, source: "sheets" | "cache", updated_at: str }`)
    - `POST /api/scrape` (body `{ roles: list[str], locations: list[str], portals: list[str] }`, launches background thread, returns `{ started: true, message: str }`)
    - `GET /api/scrape/status` (returns `{ is_running: bool, current_step: str, started_at: str | None, elapsed_seconds: int, last_result: dict | None }`)
    - `PATCH /api/jobs/status` (body `{ url: str, status: str }`, updates cache + Google Sheets column if connected, returns updated job)
  - Unit tests in `tests/test_api.py` using `fastapi.testclient.TestClient`.

- [ ] **Task 2: Frontend Setup (Vite + React + TypeScript + Tailwind + Lucide)**
  - Scaffold `frontend/` directory with `package.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `postcss.config.js`, `index.html`.
  - Install dependencies (`lucide-react`, `tailwindcss`, `clsx`, `tailwind-merge`).

- [ ] **Task 3: Frontend Data Types & API Client (`frontend/src/types.ts` & `frontend/src/api.ts`)**
  - TypeScript interfaces matching backend response (`Job`, `ScrapePayload`, `ScrapeStatus`, `KpiStats`).
  - Helper functions for fetch, polling, and status mutation with error handling.

- [ ] **Task 4: Hallmark Theme Tokens & Components**
  - `frontend/src/index.css`: Hallmark Rim theme tokens (`--color-paper`, `--color-ink`, `--color-accent`, Geist/Switzer font setup).
  - `StatsCards.tsx`: 4 KPI telemetry cards (Total Jobs, Portal breakdown: LinkedIn/Jobstreet/Glints, New Jobs count, Active Target Locations).
  - `ScraperControls.tsx`: Multi-select pills/toggles for Roles, Locations, Portals, plus "Run Scraper Now" with real-time running timer & progress text.
  - `JobTable.tsx`: Search bar, portal/location/status filter tabs, Table View / Card Grid View switcher, portal badges (LinkedIn blue, Jobstreet magenta, Glints amber), relative date highlights (<3 days green tag), interactive status dropdown, and "Apply / Buka Portal" external link button.
  - `App.tsx`: Layout composition, auto-refresh after scraping completes, toast notifications.

- [ ] **Task 5: Verification & End-to-End Smoke Test**
  - Run backend unit tests (`pytest tests/test_api.py`).
  - Build frontend with `npm run build` to ensure 0 TypeScript / bundle errors.
  - Test backend API endpoints live with Python TestClient / requests.
  - Update `README.md` with instructions to run both services simultaneously.
