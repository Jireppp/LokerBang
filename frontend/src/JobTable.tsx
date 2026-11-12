import React, { useMemo, useState } from "react";
import { Job, JobStatus } from "./types";

interface JobTableProps {
  jobs: Job[];
  isLoading: boolean;
  onStatusChange: (url: string, newStatus: JobStatus) => Promise<void>;
  onResetFilters?: () => void;
}

const STATUS_OPTIONS: JobStatus[] = [
  "New",
  "Saved",
  "Applied",
  "Interview",
  "Rejected",
];

const ROLE_CATEGORIES = [
  "System Analyst",
  "IoT Engineer",
  "IT Support",
  "Product Support",
  "Technical Writer",
];

const PORTAL_NAMES = [
  "LinkedIn",
  "Jobstreet",
  "Glints",
  "Kalibrr",
  "Dealls",
  "Tech in Asia",
  "Indeed",
];

function getStatusSelectModifier(status: JobStatus): string {
  if (status === "New") {
    return "status-select--new";
  }
  if (status === "Applied" || status === "Interview") {
    return "status-select--active";
  }
  return "";
}

function getDaysAgoInfo(dateStr: string): { label: string; isFresh: boolean } {
  if (!dateStr) {
    return { label: "Tidak tercatat", isFresh: false };
  }
  const posted = new Date(`${dateStr}T00:00:00+07:00`);
  if (Number.isNaN(posted.getTime())) {
    return { label: `${dateStr} WIB`, isFresh: false };
  }
  const now = new Date();
  const diffDays = Math.max(
    0,
    Math.floor((now.getTime() - posted.getTime()) / (1000 * 60 * 60 * 24))
  );
  if (diffDays === 0) {
    return { label: `${dateStr} (0h WIB)`, isFresh: true };
  }
  if (diffDays <= 3) {
    return { label: `${dateStr} (${diffDays}h WIB)`, isFresh: true };
  }
  return { label: `${dateStr} (${diffDays}h WIB)`, isFresh: false };
}

export const JobTable: React.FC<JobTableProps> = ({
  jobs,
  isLoading,
  onStatusChange,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("All");
  const [portalFilter, setPortalFilter] = useState<string>("All");
  const [locationFilter, setLocationFilter] = useState<string>("All");
  const [statusFilter, setStatusFilter] = useState<string>("All");
  const [viewMode, setViewMode] = useState<"table" | "grid">("table");
  const [updatingUrl, setUpdatingUrl] = useState<string | null>(null);

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      if (
        roleFilter !== "All" &&
        (job.role_category || "System Analyst").toLowerCase() !==
          roleFilter.toLowerCase()
      ) {
        return false;
      }
      if (
        portalFilter !== "All" &&
        job.platform.toLowerCase() !== portalFilter.toLowerCase()
      ) {
        return false;
      }
      if (statusFilter !== "All" && job.status !== statusFilter) {
        return false;
      }
      if (locationFilter !== "All") {
        const locLower = job.location.toLowerCase();
        if (locationFilter === "Bandung" && !locLower.includes("bandung")) {
          return false;
        }
        if (locationFilter === "Jakarta" && locLower.includes("bandung")) {
          return false;
        }
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = job.title.toLowerCase().includes(q);
        const matchCompany = job.company.toLowerCase().includes(q);
        const matchLoc = job.location.toLowerCase().includes(q);
        const matchRole = (job.role_category || "").toLowerCase().includes(q);
        if (!matchTitle && !matchCompany && !matchLoc && !matchRole) {
          return false;
        }
      }
      return true;
    });
  }, [jobs, roleFilter, portalFilter, statusFilter, locationFilter, searchQuery]);

  const handleSelectStatus = async (url: string, nextStatus: JobStatus) => {
    setUpdatingUrl(url);
    try {
      await onStatusChange(url, nextStatus);
    } finally {
      setUpdatingUrl(null);
    }
  };

  const clearFilters = () => {
    setSearchQuery("");
    setRoleFilter("All");
    setPortalFilter("All");
    setLocationFilter("All");
    setStatusFilter("All");
  };

  return (
    <section className="ledger-section" aria-labelledby="ledger-heading">
      {/* Section Header */}
      <div className="ledger-head">
        <h2 id="ledger-heading" className="ledger-title">
          Daftar lowongan aktif
        </h2>
        <p className="measure">
          Menampilkan {filteredJobs.length} dari {jobs.length} posisi (WIB UTC+7)
        </p>
      </div>

      {/* Filter & View Bar */}
      <div className="filter-grid">
        <div className="filter-field filter-field--search">
          <label htmlFor="filter-search" className="field-label">
            Pencarian kata kunci
          </label>
          <input
            id="filter-search"
            name="q"
            type="search"
            autoComplete="off"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="PT Elnusa, System Analyst, Bandung"
            className="input"
          />
          <span className="field-helper">
            Menyaring judul posisi, kategori, perusahaan, atau kota.
          </span>
        </div>

        <div className="filter-field">
          <label htmlFor="filter-role" className="field-label">
            Kategori role
          </label>
          <select
            id="filter-role"
            name="role_category"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="select"
          >
            <option value="All">Semua role (5)</option>
            {ROLE_CATEGORIES.map((rc) => (
              <option key={rc} value={rc}>
                {rc}
              </option>
            ))}
          </select>
          <span className="field-helper">5 kategori role target.</span>
        </div>

        <div className="filter-field">
          <label htmlFor="filter-portal" className="field-label">
            Portal sumber
          </label>
          <select
            id="filter-portal"
            name="portal"
            value={portalFilter}
            onChange={(e) => setPortalFilter(e.target.value)}
            className="select"
          >
            <option value="All">Semua portal (7)</option>
            {PORTAL_NAMES.map((pn) => (
              <option key={pn} value={pn}>
                {pn}
              </option>
            ))}
          </select>
          <span className="field-helper">7 portal kerja terhubung.</span>
        </div>

        <div className="filter-field">
          <label htmlFor="filter-location" className="field-label">
            Wilayah kerja
          </label>
          <select
            id="filter-location"
            name="location"
            value={locationFilter}
            onChange={(e) => setLocationFilter(e.target.value)}
            className="select"
          >
            <option value="All">Semua wilayah</option>
            <option value="Bandung">Bandung</option>
            <option value="Jakarta">Jakarta &amp; Bodetabek</option>
          </select>
          <span className="field-helper">Bandung Raya atau Jabodetabek.</span>
        </div>

        <div className="filter-field">
          <label htmlFor="filter-status" className="field-label">
            Status lamaran
          </label>
          <select
            id="filter-status"
            name="status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="select"
          >
            <option value="All">Semua status</option>
            {STATUS_OPTIONS.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>
          <span className="field-helper">Tahap proses lamaran saat ini.</span>
        </div>

        <div className="filter-field filter-field--view">
          <span className="field-label">Susunan tampilan</span>
          <div className="segmented" role="group" aria-label="Susunan tampilan">
            <button
              type="button"
              aria-pressed={viewMode === "table"}
              onClick={() => setViewMode("table")}
              className="toggle-chip"
            >
              Tabel
            </button>
            <button
              type="button"
              aria-pressed={viewMode === "grid"}
              onClick={() => setViewMode("grid")}
              className="toggle-chip"
            >
              Kartu
            </button>
          </div>
          <span className="field-helper">Baris penuh atau kartu indeks.</span>
        </div>
      </div>

      {/* Loading / Empty / Table / Grid */}
      {isLoading ? (
        <div className="skeleton-stack" aria-busy="true" aria-label="Memuat daftar lowongan">
          {[1, 2, 3, 4, 5].map((n) => (
            <div key={n} className="skeleton-row" />
          ))}
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="empty-well">
          <p className="job-title">
            Tidak ada baris lowongan yang cocok dengan saringan saat ini.
          </p>
          <p className="job-company">
            Longgarkan kata kunci pencarian di atas atau jalankan penarikan data baru dari portal.
          </p>
          <button type="button" onClick={clearFilters} className="btn">
            Atur ulang saringan
          </button>
        </div>
      ) : viewMode === "table" ? (
        <div className="table-wrap">
          <table className="ledger-table">
            <thead>
              <tr>
                <th scope="col">Posisi &amp; perusahaan</th>
                <th scope="col">Kategori role</th>
                <th scope="col">Wilayah</th>
                <th scope="col">Portal &amp; tingkat</th>
                <th scope="col">Tanggal tayang</th>
                <th scope="col">Status lamaran</th>
                <th scope="col">Tautan</th>
              </tr>
            </thead>
            <tbody>
              {filteredJobs.map((job) => {
                const dateInfo = getDaysAgoInfo(job.date_posted);
                const isNew = job.status === "New";
                return (
                  <tr key={job.url}>
                    <td>
                      <div className="job-primary">
                        <span
                          className={`pin ${isNew ? "pin--orange" : "pin--ink"}`}
                          aria-hidden="true"
                        />
                        <div>
                          <div className="job-title">{job.title}</div>
                          <div className="job-company">{job.company}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="portal-tag">
                        {job.role_category || "System Analyst"}
                      </span>
                    </td>
                    <td>{job.location}</td>
                    <td>
                      <span className="portal-tag">{job.platform}</span>
                      <span className="level-sub">{job.experience_level}</span>
                    </td>
                    <td
                      className={`date-cell ${
                        dateInfo.isFresh ? "date-fresh" : ""
                      }`}
                    >
                      {dateInfo.label}
                    </td>
                    <td>
                      <select
                        name={`status-${job.url}`}
                        aria-label={`Status lamaran untuk ${job.title} di ${job.company}`}
                        disabled={updatingUrl === job.url}
                        value={job.status}
                        onChange={(e) =>
                          handleSelectStatus(
                            job.url,
                            e.target.value as JobStatus
                          )
                        }
                        className={`status-select ${getStatusSelectModifier(
                          job.status
                        )}`}
                      >
                        {STATUS_OPTIONS.map((st) => (
                          <option key={st} value={st}>
                            {st}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <a
                        href={job.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ledger-link"
                      >
                        <span>Buka lowongan</span>
                        <span aria-hidden="true">↗</span>
                      </a>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="specimen-grid">
          {filteredJobs.map((job) => {
            const dateInfo = getDaysAgoInfo(job.date_posted);
            const isNew = job.status === "New";
            return (
              <article key={job.url} className="specimen-card">
                <div>
                  <div className="job-primary">
                    <span
                      className={`pin ${isNew ? "pin--orange" : "pin--ink"}`}
                      aria-hidden="true"
                    />
                    <h3 className="job-title">{job.title}</h3>
                  </div>

                  <dl className="specimen-dl">
                    <dt>Kategori</dt>
                    <dd>{job.role_category || "System Analyst"}</dd>
                    <dt>Perusahaan</dt>
                    <dd>{job.company}</dd>
                    <dt>Wilayah</dt>
                    <dd>{job.location}</dd>
                    <dt>Portal</dt>
                    <dd>{job.platform}</dd>
                    <dt>Tingkat</dt>
                    <dd>{job.experience_level}</dd>
                    <dt>Tayang</dt>
                    <dd
                      className={`date-cell ${
                        dateInfo.isFresh ? "date-fresh" : ""
                      }`}
                    >
                      {dateInfo.label}
                    </dd>
                  </dl>
                </div>

                <div className="specimen-card__foot">
                  <select
                    name={`grid-status-${job.url}`}
                    aria-label={`Status lamaran untuk ${job.title} di ${job.company}`}
                    disabled={updatingUrl === job.url}
                    value={job.status}
                    onChange={(e) =>
                      handleSelectStatus(job.url, e.target.value as JobStatus)
                    }
                    className={`status-select ${getStatusSelectModifier(
                      job.status
                    )}`}
                  >
                    {STATUS_OPTIONS.map((st) => (
                      <option key={st} value={st}>
                        {st}
                      </option>
                    ))}
                  </select>

                  <a
                    href={job.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ledger-link"
                  >
                    <span>Buka lowongan</span>
                    <span aria-hidden="true">↗</span>
                  </a>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
};
