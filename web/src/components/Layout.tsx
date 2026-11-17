import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Download, LineChart, ShieldCheck, Table2, Upload, Users } from "lucide-react";
import { api } from "../api";
import { fmtDate } from "../format";
import { UploadDialog } from "./UploadDialog";
import { Button, ErrorNote, Loading } from "./ui";

const NAV = [
  { to: "/", label: "Squad", icon: Users },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/daily", label: "Daily data", icon: Table2 },
  { to: "/quality", label: "Data quality", icon: ShieldCheck },
  { to: "/forecast", label: "Forecast", icon: LineChart },
];

export function Layout({ children }: { children: ReactNode }) {
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const [uploading, setUploading] = useState(false);
  const s = status.data;
  const hasData = !!s?.imports.length;
  const range = s?.summary?.date_range;

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <nav className="flex shrink-0 flex-col bg-nav text-nav-ink md:sticky md:top-0 md:h-screen md:w-52" aria-label="Main">
        <div className="px-4 pb-2 pt-4 md:pb-6">
          <p className="text-[22px] font-bold tracking-tight text-white">LoadWise</p>
          <p className="text-xs">Athlete workload monitoring</p>
        </div>
        <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-[15px] font-medium ${isActive ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-white"}`}
              >
                <Icon size={17} aria-hidden />{label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface px-4 py-2.5 md:px-8">
          <p className="text-sm text-ink-2">
            {hasData ? (
              <>
                <span className="font-semibold text-ink">{s!.imports.length} workbook{s!.imports.length > 1 ? "s" : ""}</span>
                {" "}· season {s!.season_start_year}–{String((s!.season_start_year ?? 0) + 1).slice(2)}
                {range?.first && <> · {fmtDate(range.first)} to {fmtDate(range.last)}</>}
              </>
            ) : "No data yet"}
          </p>
          <div className="flex gap-2">
            {hasData && (
              <>
                <a href="/api/export.csv" className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-surface-2 hover:text-ink"><Download size={15} />Daily CSV</a>
                <a href="/api/export.json" className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-surface-2 hover:text-ink"><Download size={15} />Full JSON</a>
              </>
            )}
            <Button variant="primary" onClick={() => setUploading(true)}><Upload size={15} />Add data</Button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8">
          {status.isLoading ? <Loading /> : status.error ? <ErrorNote error={status.error} /> :
            hasData ? children : <Welcome demo={!!s?.demo_available} year={s?.demo_season_year ?? 2025} onUpload={() => setUploading(true)} />}
        </main>
      </div>
      {uploading && <UploadDialog status={s} onClose={() => setUploading(false)} />}
    </div>
  );
}

function Welcome({ demo, year, onUpload }: { demo: boolean; year: number; onUpload: () => void }) {
  const qc = useQueryClient();
  const load = useMutation({ mutationFn: () => api.importDemo(year), onSuccess: () => qc.invalidateQueries() });
  return (
    <div className="mx-auto mt-16 max-w-xl text-center">
      <h1 className="text-3xl font-bold">Start with a workload export</h1>
      <p className="mt-2 text-ink-2">
        LoadWise reads the per-session Excel export, checks it, and combines each athlete’s sessions into one record per day.
        Histories build up as you add more files.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {demo && (
          <Button variant="primary" onClick={() => load.mutate()} disabled={load.isPending}>
            {load.isPending ? "Processing 1,260 sessions…" : `Load the demo season (${year}–${String(year + 1).slice(2)})`}
          </Button>
        )}
        <Button onClick={onUpload}><Upload size={15} />Upload a workbook</Button>
      </div>
      {load.error && <div className="mt-4"><ErrorNote error={load.error} /></div>}
    </div>
  );
}
