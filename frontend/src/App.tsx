import React, { useEffect, useRef, useState } from "react";
import {
  fetchJobs,
  fetchScrapeStatus,
  triggerScrape,
  updateJobStatus,
} from "./api";
import { Job, JobStatus, PortalRunState } from "./types";
import { StatsCards } from "./StatsCards";
import { ScraperControls } from "./ScraperControls";
import { JobTable } from "./JobTable";

export const App: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [source, setSource] = useState<"sheets" | "cache">("cache");
  const [sheetsConfigured, setSheetsConfigured] = useState<boolean>(false);
  const [isLoadingJobs, setIsLoadingJobs] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const [selectedRoles, setSelectedRoles] = useState<string[]>([
    "system_analyst",
    "iot_engineer",
    "it_support",
    "product_support",
    "technical_writer",
  ]);
  const [selectedLocations, setSelectedLocations] = useState<string[]>([
    "Bandung",
    "Jakarta",
  ]);
  const [selectedPortals, setSelectedPortals] = useState<string[]>([
    "linkedin",
    "jobstreet",
    "glints",
    "kalibrr",
    "dealls",
    "techinasia",
    "indeed",
  ]);

  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<string>("Siap");
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [portalStatus, setPortalStatus] = useState<
    Record<string, PortalRunState>
  >({});
  const [lastTelemetryText, setLastTelemetryText] = useState<string>(
    "Menunggu perintah penarikan atau pembaruan lembar kerja."
  );

  const pollIntervalRef = useRef<number | null>(null);
  const timerIntervalRef = useRef<number | null>(null);

  const loadData = async (refreshSheets = false) => {
    if (refreshSheets) {
      setIsRefreshing(true);
    } else {
      setIsLoadingJobs(true);
    }
    try {
      const data = await fetchJobs(refreshSheets);
      setJobs(data.jobs);
      setSource(data.source);
      setSheetsConfigured(data.sheets_configured);
      const latestStamp = data.jobs[0]?.timestamp_scraped;
      if (refreshSheets) {
        setLastTelemetryText(
          `Sinkronisasi selesai (${data.count} baris dimuat dari ${
            data.source === "sheets" ? "Google Sheets" : "cache lokal"
          }).`
        );
      } else if (latestStamp) {
        setLastTelemetryText(
          `Tangkapan terakhir tercatat pada ${latestStamp} WIB (${data.count} posisi aktif).`
        );
      } else {
        setLastTelemetryText(
          "Belum ada rekaman lowongan. Jalankan penarikan untuk mengisi Job_Tracker."
        );
      }
    } catch (err: any) {
      setLastTelemetryText(
        `Gagal memuat daftar lowongan: ${err.message || "Periksa koneksi server API pada port 8000."}`
      );
    } finally {
      setIsLoadingJobs(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, []);

  const handleToggle = (
    list: string[],
    setList: React.Dispatch<React.SetStateAction<string[]>>,
    item: string
  ) => {
    if (list.includes(item)) {
      if (list.length > 1) {
        setList(list.filter((x) => x !== item));
      }
    } else {
      setList([...list, item]);
    }
  };

  const startPolling = () => {
    setIsRunning(true);
    setElapsedSeconds(0);

    timerIntervalRef.current = window.setInterval(() => {
      setElapsedSeconds((sec) => sec + 1);
    }, 1000);

    pollIntervalRef.current = window.setInterval(async () => {
      try {
        const st = await fetchScrapeStatus();
        setCurrentStep(st.current_step);
        if (st.portal_status) {
          setPortalStatus(st.portal_status);
        }
        if (!st.is_running) {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
          setIsRunning(false);

          const newCount = st.last_result?.new_jobs_count ?? 0;
          const totalScraped = st.last_result?.total_scraped ?? 0;
          const finishedAt = st.finished_at
            ? `${st.finished_at} WIB`
            : "baru saja";
          setLastTelemetryText(
            `Penarikan selesai pada ${finishedAt}: ${newCount} lowongan baru ditambahkan dari ${totalScraped} hasil pindaian.`
          );
          await loadData(false);
        }
      } catch {
        // Polling continues until backend responds
      }
    }, 1500);
  };

  const handleRunScraper = async () => {
    if (isRunning) return;
    try {
      const initialMap: Record<string, PortalRunState> = {};
      for (const p of selectedPortals) {
        initialMap[p] = "pending";
      }
      setPortalStatus(initialMap);
      await triggerScrape({
        roles: selectedRoles,
        locations: selectedLocations,
        portals: selectedPortals,
        days: 14,
      });
      startPolling();
    } catch (err: any) {
      setLastTelemetryText(
        `Gagal memulai penarikan: ${err.message || "Periksa koneksi backend FastAPI."}`
      );
    }
  };

  const handleStatusChange = async (url: string, newStatus: JobStatus) => {
    const res = await updateJobStatus(url, newStatus);
    setJobs((prev) =>
      prev.map((j) => (j.url === url ? { ...j, status: res.job.status } : j))
    );
    setLastTelemetryText(
      `Status untuk “${res.job.title}” (${res.job.company}) disimpan sebagai ${newStatus}.`
    );
  };

  return (
    <div className="app-shell">
      {/* Top Instrument Bar */}
      <header className="app-header">
        <div className="container app-header__inner">
          <div className="app-brand">
            <a
              href="/"
              aria-label="Beranda LokerBang"
              className="app-wordmark"
            >
              LokerBang
            </a>
            <span className="app-brand__sep" aria-hidden="true">
              /
            </span>
            <h1 className="app-brand__sub" style={{ margin: 0 }}>
              Pemantauan 5 kategori role IT pada 7 portal kerja
            </h1>
          </div>

          <div className="app-telemetry-meta">
            <span className="signal-readout">
              <span
                className={`pin ${sheetsConfigured ? "pin--sky" : ""}`}
                aria-hidden="true"
              />
              <span>
                {sheetsConfigured
                  ? "Lembar kerja: Job_Tracker (10 kolom)"
                  : "Penyimpanan: Cache lokal"}
              </span>
            </span>

            <span className="signal-readout measure">
              <span
                className={`pin ${isRunning ? "pin--orange" : "pin--ink"}`}
                aria-hidden="true"
              />
              <span>
                {isRunning
                  ? `Menarik data (${elapsedSeconds}s WIB)`
                  : "Status mesin: Siap (WIB)"}
              </span>
            </span>
          </div>
        </div>
      </header>

      {/* Main Telemetry Workspace */}
      <main className="container app-main">
        {/* Corner-Ticked Command Well */}
        <ScraperControls
          selectedRoles={selectedRoles}
          onToggleRole={(r) => handleToggle(selectedRoles, setSelectedRoles, r)}
          selectedLocations={selectedLocations}
          onToggleLocation={(l) =>
            handleToggle(selectedLocations, setSelectedLocations, l)
          }
          selectedPortals={selectedPortals}
          onTogglePortal={(p) =>
            handleToggle(selectedPortals, setSelectedPortals, p)
          }
          portalStatus={portalStatus}
          isRunning={isRunning}
          elapsedSeconds={elapsedSeconds}
          currentStep={currentStep}
          lastTelemetryText={lastTelemetryText}
          onRunScraper={handleRunScraper}
          onRefreshSheets={() => loadData(true)}
          isRefreshing={isRefreshing}
        />

        {/* Hairline-Parted Measurements Strip */}
        <StatsCards
          jobs={jobs}
          source={source}
          sheetsConfigured={sheetsConfigured}
        />

        {/* Full-Width Ruled Job Ledger */}
        <JobTable
          jobs={jobs}
          isLoading={isLoadingJobs}
          onStatusChange={handleStatusChange}
        />
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <div className="container app-footer__inner">
          <span>
            LokerBang: Bandung Raya &amp; Jabodetabek (LinkedIn, Jobstreet,
            Glints, Kalibrr, Dealls, Tech in Asia, Indeed)
          </span>
          <span className="measure">
            Sinkronisasi dua arah: Job_Tracker &amp; jobs_cache.json (WIB UTC+7)
          </span>
        </div>
      </footer>
    </div>
  );
};
