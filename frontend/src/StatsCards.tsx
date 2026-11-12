import React from "react";
import { Job } from "./types";

interface StatsCardsProps {
  jobs: Job[];
  source: "sheets" | "cache";
  sheetsConfigured: boolean;
}

const PORTAL_LIST = [
  { key: "linkedin", label: "LinkedIn" },
  { key: "jobstreet", label: "Jobstreet" },
  { key: "glints", label: "Glints" },
  { key: "kalibrr", label: "Kalibrr" },
  { key: "dealls", label: "Dealls" },
  { key: "tech in asia", label: "Tech in Asia" },
  { key: "indeed", label: "Indeed" },
];

export const StatsCards: React.FC<StatsCardsProps> = ({
  jobs,
  source,
  sheetsConfigured,
}) => {
  const total = jobs.length;
  const newCount = jobs.filter((j) => j.status === "New").length;
  const appliedCount = jobs.filter((j) =>
    ["Applied", "Interview"].includes(j.status)
  ).length;

  return (
    <section className="metrics-strip" aria-label="Ringkasan indeks lowongan">
      {/* 1. Total Active Jobs */}
      <div className="metric-cell">
        <p className="metric-title">Lowongan terjaring</p>
        <div className="metric-readout">
          <span className="metric-value">{total}</span>
          <span className="metric-unit">posisi ≤ 14 hari</span>
        </div>
        <p className="metric-caption">
          {sheetsConfigured
            ? `Sinkron 10 kolom Job_Tracker (${source})`
            : `Penyimpanan cache lokal (${source})`}
        </p>
      </div>

      {/* 2. Unprocessed / New */}
      <div className="metric-cell">
        <p className="metric-title">Belum ditindaklanjuti</p>
        <div className="metric-readout">
          <span className="metric-value metric-value--orange">{newCount}</span>
          <span className="metric-unit">status “New”</span>
        </div>
        <p className="metric-caption">
          Menunggu seleksi atau pengiriman lamaran.
        </p>
      </div>

      {/* 3. Active Applications */}
      <div className="metric-cell">
        <p className="metric-title">Lamaran berjalan</p>
        <div className="metric-readout">
          <span className="metric-value metric-value--sky">{appliedCount}</span>
          <span className="metric-unit">Applied &amp; Interview</span>
        </div>
        <p className="metric-caption">
          Perubahan status tersimpan langsung ke lembar kerja.
        </p>
      </div>

      {/* 4. Portal Distribution (7 Portals) */}
      <div className="metric-cell">
        <p className="metric-title">Distribusi 7 portal sumber</p>
        <dl className="portal-dl">
          {PORTAL_LIST.map((p) => {
            const count = jobs.filter(
              (j) => j.platform.toLowerCase() === p.key
            ).length;
            return (
              <div key={p.key} className="portal-dl__item">
                <dt>{p.label}</dt>
                <dd>{count}</dd>
              </div>
            );
          })}
        </dl>
        <p className="metric-caption">
          Deduplikasi otomatis berdasarkan URL kanonik.
        </p>
      </div>
    </section>
  );
};
