import React from "react";
import { PortalRunState } from "./types";

interface ScraperControlsProps {
  selectedRoles: string[];
  onToggleRole: (role: string) => void;
  selectedLocations: string[];
  onToggleLocation: (loc: string) => void;
  selectedPortals: string[];
  onTogglePortal: (portal: string) => void;
  portalStatus: Record<string, PortalRunState>;
  isRunning: boolean;
  elapsedSeconds: number;
  currentStep: string;
  lastTelemetryText: string;
  onRunScraper: () => void;
  onRefreshSheets: () => void;
  isRefreshing: boolean;
}

export const ROLE_OPTIONS = [
  { id: "system_analyst", label: "System Analyst" },
  { id: "iot_engineer", label: "IoT Engineer" },
  { id: "it_support", label: "IT Support" },
  { id: "product_support", label: "Product Support" },
  { id: "technical_writer", label: "Technical Writer" },
];

export const LOCATION_OPTIONS = [
  { id: "Bandung", label: "Bandung" },
  { id: "Jakarta", label: "Jakarta Raya" },
];

export const PORTAL_OPTIONS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "jobstreet", label: "Jobstreet" },
  { id: "glints", label: "Glints" },
  { id: "kalibrr", label: "Kalibrr" },
  { id: "dealls", label: "Dealls" },
  { id: "techinasia", label: "Tech in Asia" },
  { id: "indeed", label: "Indeed" },
];

function getPortalPinModifier(
  active: boolean,
  runState?: PortalRunState
): string {
  if (runState === "scraping") return "pin--orange";
  if (runState === "done") return "pin--sky";
  if (runState === "failed") return "pin--ink";
  return active ? "pin--orange" : "";
}

export const ScraperControls: React.FC<ScraperControlsProps> = ({
  selectedRoles,
  onToggleRole,
  selectedLocations,
  onToggleLocation,
  selectedPortals,
  onTogglePortal,
  portalStatus,
  isRunning,
  elapsedSeconds,
  currentStep,
  lastTelemetryText,
  onRunScraper,
  onRefreshSheets,
  isRefreshing,
}) => {
  return (
    <section className="well ticks" aria-label="Parameter penarikan lowongan">
      <div className="command-grid">
        {/* Target Roles (5 Categories) */}
        <fieldset className="command-group command-group--roles">
          <legend className="field-label">Kategori role target (5)</legend>
          <div className="toggle-row">
            {ROLE_OPTIONS.map((role) => {
              const active = selectedRoles.includes(role.id);
              return (
                <button
                  key={role.id}
                  type="button"
                  disabled={isRunning}
                  aria-pressed={active}
                  onClick={() => onToggleRole(role.id)}
                  className="toggle-chip"
                >
                  <span
                    className={`pin ${active ? "pin--orange" : ""}`}
                    aria-hidden="true"
                  />
                  <span>{role.label}</span>
                </button>
              );
            })}
          </div>
        </fieldset>

        {/* Target Locations */}
        <fieldset className="command-group">
          <legend className="field-label">Wilayah pantau</legend>
          <div className="toggle-row">
            {LOCATION_OPTIONS.map((loc) => {
              const active = selectedLocations.includes(loc.id);
              return (
                <button
                  key={loc.id}
                  type="button"
                  disabled={isRunning}
                  aria-pressed={active}
                  onClick={() => onToggleLocation(loc.id)}
                  className="toggle-chip"
                >
                  <span
                    className={`pin ${active ? "pin--orange" : ""}`}
                    aria-hidden="true"
                  />
                  <span>{loc.label}</span>
                </button>
              );
            })}
          </div>
        </fieldset>

        {/* Source Portals (7 Portals) */}
        <fieldset className="command-group command-group--portals">
          <legend className="field-label">Sumber portal paralel (7)</legend>
          <div className="toggle-row">
            {PORTAL_OPTIONS.map((portal) => {
              const active = selectedPortals.includes(portal.id);
              const st = portalStatus[portal.id];
              return (
                <button
                  key={portal.id}
                  type="button"
                  disabled={isRunning}
                  aria-pressed={active}
                  onClick={() => onTogglePortal(portal.id)}
                  className="toggle-chip"
                  title={st ? `${portal.label}: ${st}` : portal.label}
                >
                  <span
                    className={`pin ${getPortalPinModifier(active, st)}`}
                    aria-hidden="true"
                  />
                  <span>{portal.label}</span>
                  {st && (
                    <span className="measure level-inline">[{st}]</span>
                  )}
                </button>
              );
            })}
          </div>
        </fieldset>

        {/* Execution Controls */}
        <div className="command-actions">
          <button
            type="button"
            disabled={isRunning || isRefreshing}
            onClick={onRefreshSheets}
            className="btn"
          >
            <span>{isRefreshing ? "Menyinkronkan…" : "Sinkronkan"}</span>
          </button>

          <button
            type="button"
            disabled={
              isRunning ||
              selectedRoles.length === 0 ||
              selectedLocations.length === 0 ||
              selectedPortals.length === 0
            }
            onClick={onRunScraper}
            className="btn btn--primary"
          >
            {isRunning ? (
              <span className="measure">Menarik ({elapsedSeconds}s WIB)</span>
            ) : (
              <span>Tarik lowongan</span>
            )}
          </button>
        </div>
      </div>

      {/* Persistent Telemetry Log Line */}
      <div className="telemetry-bar" role="status" aria-live="polite">
        <div className="telemetry-bar__status">
          <span
            className={`pin ${isRunning ? "pin--orange" : "pin--sky"}`}
            aria-hidden="true"
          />
          <span>
            {isRunning
              ? currentStep || "Menjalankan antrean paralel pada 7 portal…"
              : lastTelemetryText}
          </span>
        </div>
        <span className="measure">
          {isRunning
            ? `Durasi berjalan: ${elapsedSeconds}s WIB`
            : "Jendela usia: ≤ 14 hari (WIB UTC+7)"}
        </span>
      </div>
    </section>
  );
};
