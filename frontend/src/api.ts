import { Job, JobsResponse, ScrapePayload, ScrapeStatus } from "./types";

const API_BASE = "";

export async function fetchJobs(refreshSheets = false): Promise<JobsResponse> {
  const url = refreshSheets ? `${API_BASE}/api/jobs?refresh_sheets=true` : `${API_BASE}/api/jobs`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Gagal memuat lowongan: ${res.statusText}`);
  }
  return res.json();
}

export async function triggerScrape(payload: ScrapePayload): Promise<{ status: string; message?: string }> {
  const res = await fetch(`${API_BASE}/api/scrape`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, async_mode: true }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Gagal memulai scraping.");
  }
  return res.json();
}

export async function fetchScrapeStatus(): Promise<ScrapeStatus> {
  const res = await fetch(`${API_BASE}/api/scrape/status`);
  if (!res.ok) {
    throw new Error("Gagal memeriksa status scraper.");
  }
  return res.json();
}

export async function updateJobStatus(url: string, status: string): Promise<{ status: string; job: Job }> {
  const res = await fetch(`${API_BASE}/api/jobs/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, status }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Gagal memperbarui status lowongan.");
  }
  return res.json();
}
