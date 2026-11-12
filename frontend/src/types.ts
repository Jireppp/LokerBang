export type JobPlatform =
  | "LinkedIn"
  | "Jobstreet"
  | "Glints"
  | "Kalibrr"
  | "Dealls"
  | "Tech in Asia"
  | "Indeed"
  | string;

export type JobStatus = "New" | "Saved" | "Applied" | "Interview" | "Rejected";

export type PortalRunState = "pending" | "scraping" | "done" | "failed";

export interface Job {
  timestamp_scraped: string;
  role_category: string;
  title: string;
  company: string;
  location: string;
  platform: JobPlatform;
  date_posted: string;
  experience_level: string;
  url: string;
  status: JobStatus;
}

export interface JobsResponse {
  jobs: Job[];
  count: number;
  source: "sheets" | "cache";
  sheets_configured: boolean;
}

export interface ScrapePayload {
  roles: string[];
  locations: string[];
  portals: string[];
  days?: number;
  async_mode?: boolean;
}

export interface ScrapeStatus {
  is_running: boolean;
  current_step: string;
  started_at: string | null;
  finished_at: string | null;
  portal_status?: Record<string, PortalRunState>;
  last_result: {
    status?: string;
    new_jobs_count?: number;
    sheets_synced_count?: number;
    total_scraped?: number;
    total_in_tracker?: number;
    portal_summary?: Record<string, string>;
    portal_status?: Record<string, PortalRunState>;
    elapsed_seconds?: number;
    message?: string;
  } | null;
}
