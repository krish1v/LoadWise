import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api, type DailyDetail, type SessionRecord, type RawRecord } from "../api";
import { fmt, fmtDate, humanRule, METRICS } from "../format";
import { ErrorNote, Loading, MetricValue, SeverityTag } from "./ui";

type Target = { athlete: string; date: string } | null;
const Ctx = createContext<(athlete: string, date: string) => void>(() => {});
export const useOpenDay = () => useContext(Ctx);

export function DayDrawerProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<Target>(null);
  return (
    <Ctx.Provider value={(athlete, date) => setTarget({ athlete, date })}>
      {children}
      {target && <DayDrawer target={target} onClose={() => setTarget(null)} />}
    </Ctx.Provider>
  );
}

function DayDrawer({ target, onClose }: { target: NonNullable<Target>; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const q = useQuery({ queryKey: ["day", target.athlete, target.date], queryFn: () => api.dailyDetail(target.athlete, target.date), retry: false });
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Day detail">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div ref={ref} tabIndex={-1} className="relative flex h-full w-full max-w-[720px] flex-col overflow-hidden border-l border-line bg-page shadow-xl outline-none">
        <header className="flex items-start justify-between gap-3 border-b border-line bg-surface px-5 py-4">
          <div>
            <p className="text-sm text-ink-2">{q.data?.daily.athlete_label ?? "Athlete"}</p>
            <h2 className="text-2xl font-bold">{fmtDate(target.date, true)}</h2>
          </div>
          <button onClick={onClose} className="rounded p-1 text-ink-2 hover:bg-surface-2" aria-label="Close"><X size={20} /></button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {q.isLoading && <Loading what="Loading sessions" />}
          {q.error && <ErrorNote error={q.error} />}
          {q.data && <DayBody d={q.data} />}
        </div>
      </div>
    </div>
  );
}

function DayBody({ d }: { d: DailyDetail }) {
  const day = d.daily;
  return (
    <div className="space-y-6">
      <section>
        <table className="w-full text-sm">
          <thead className="text-left text-ink-2">
            <tr className="border-b border-line">
              <th className="py-1.5 font-medium">Metric</th>
              <th className="py-1.5 text-right font-medium">Day total</th>
              <th className="py-1.5 text-right font-medium">Training</th>
              <th className="py-1.5 text-right font-medium">Game</th>
              <th className="py-1.5 text-right font-medium">Other</th>
            </tr>
          </thead>
          <tbody>
            {METRICS.map((m) => (
              <tr key={m.key} className="border-b border-line/70">
                <td className="py-1.5">{m.label} <span className="text-muted">({m.unit})</span></td>
                <td className="py-1.5 text-right font-semibold"><MetricValue block={day.totals[m.key]} digits={m.digits} /></td>
                {(["training", "game", "other"] as const).map((b) => (
                  <td key={b} className="py-1.5 text-right text-ink-2"><MetricValue block={day.breakdown[b][m.key]} digits={m.digits} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
          <Ratio label="Efficiency (Movement Load ÷ TRIMP)" r={day.derived.efficiency} digits={2} />
          <Ratio label="TRIMP per minute" r={day.derived.trimp_per_min} digits={2} />
        </dl>
        <p className="mt-2 text-sm text-ink-2">
          Study day {day.study_day_index ?? "—"}
          {day.schedule.gd_labels.length > 0 && <> · Game-day label {day.schedule.gd_labels.join(", ")}</>}
          {day.schedule.gd_conflict && <span className="text-serious"> (conflicting labels)</span>}
        </p>
      </section>

      <section>
        <h3 className="mb-2 text-lg font-semibold">Sessions and source rows</h3>
        <ul className="space-y-3">
          {d.sessions.map((s) => <SessionCard key={s.record_id} s={s} flags={d.flags.filter((f) => f.record_id === s.record_id)} />)}
        </ul>
      </section>

      <section>
        <h3 className="mb-2 text-lg font-semibold">Wellness</h3>
        {day.wellness.length === 0 ? (
          <p className="text-sm text-ink-2">No wellness observation recorded for this day.</p>
        ) : (
          <>
            <table className="w-full text-sm num">
              <thead className="text-left text-ink-2">
                <tr className="border-b border-line">
                  <th className="py-1 font-medium">Row</th>
                  {["Fatigue", "Sleep quality", "Sleep Ti", "Soreness", "Stress", "Score"].map((h) => <th key={h} className="py-1 text-right font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {day.wellness.map((w) => (
                  <tr key={w.record_id} className="border-b border-line/70">
                    <td className="py-1">{w.excel_row}</td>
                    {["fatigue", "sleep_quality", "sleep_time", "soreness", "stress", "wellness_score"].map((k) => (
                      <td key={k} className="py-1 text-right">{fmt(w[k] as number | null, 0)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs text-muted">Shown as recorded. The scale, direction and units of these fields are not known.</p>
          </>
        )}
      </section>
    </div>
  );
}

function Ratio({ label, r, digits }: { label: string; r: { value: number | null; reason: string | null }; digits: number }) {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2">
      <dt className="text-ink-2">{label}</dt>
      <dd className="text-xl font-semibold num">{fmt(r.value, digits)}</dd>
      {r.reason && <dd className="text-xs text-muted">Not calculated: {r.reason}.</dd>}
    </div>
  );
}

const BUCKET_COLOR = { training: "var(--training)", game: "var(--game)", other: "var(--other)" };

function SessionCard({ s, flags }: { s: SessionRecord & { raw: RawRecord | null }; flags: DailyDetail["flags"] }) {
  const [open, setOpen] = useState(false);
  const excluded = s.status !== "included";
  return (
    <li className={`rounded-lg border bg-surface ${excluded ? "border-dashed border-line-strong opacity-80" : "border-line"}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-3 pt-2.5">
        <p className="font-semibold">
          <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full" style={{ background: BUCKET_COLOR[s.session_bucket] }} aria-hidden />
          {s.measurement_type ?? "Unknown type"} · {s.start_time ?? "?"}–{s.end_time ?? "?"}
          {s.crosses_midnight && <span className="ml-1 text-sm text-ink-2">(crosses midnight)</span>}
        </p>
        <p className="text-sm text-ink-2">
          {s.provenance.file}, sheet “{s.provenance.sheet}”, row <span className="num font-semibold text-ink">{s.provenance.excel_row}</span>
        </p>
      </div>
      {excluded && (
        <p className="px-3 text-sm font-medium text-serious">
          Not counted: {s.status_reason?.replace(/_/g, " ")}{s.duplicate_of ? ` (copy of ${s.duplicate_of})` : ""}
        </p>
      )}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 px-3 py-2 text-sm sm:grid-cols-4">
        {METRICS.map((m) => (
          <div key={m.key}>
            <dt className="text-ink-2">{m.short}</dt>
            <dd className="num font-semibold">{s.metrics[m.key] === null ? <span className="text-muted">— missing</span> : fmt(s.metrics[m.key], m.digits === 0 ? 1 : 2)}</dd>
          </div>
        ))}
        <div><dt className="text-ink-2">TRIMP/min (source)</dt><dd className="num">{fmt(s.source_ratios.trimp_per_min, 2)}</dd></div>
        <div><dt className="text-ink-2">Avg movement intensity</dt><dd className="num">{fmt(s.source_ratios.avg_movement_intensity, 2)}</dd></div>
        <div><dt className="text-ink-2">HR min / avg / peak</dt><dd className="num">{fmt(s.heart_rate.min_bpm)} / {fmt(s.heart_rate.avg_bpm)} / {fmt(s.heart_rate.peak_bpm)}</dd></div>
        <div><dt className="text-ink-2">ACWR (source-reported)</dt><dd className="num">{fmt(s.source_reported.acwr, 2)}</dd></div>
      </dl>
      {flags.length > 0 && (
        <ul className="space-y-1 border-t border-line px-3 py-2 text-sm">
          {flags.map((f) => (
            <li key={f.flag_id} className="flex gap-2">
              <SeverityTag severity={f.severity} />
              <span><span className="font-medium">{humanRule(f.rule_code)}.</span> {f.explanation} <span className="text-ink-2">{f.aggregation_effect}</span></span>
            </li>
          ))}
        </ul>
      )}
      <button onClick={() => setOpen(!open)} className="w-full border-t border-line px-3 py-1.5 text-left text-sm text-ink-2 hover:bg-surface-2" aria-expanded={open}>
        {open ? "Hide" : "Show"} original cell values
      </button>
      {open && s.raw && (
        <div className="max-h-72 overflow-auto border-t border-line px-3 py-2">
          <table className="w-full text-xs">
            <tbody>
              {Object.entries(s.raw.cells).filter(([, v]) => v !== null).map(([k, v]) => (
                <tr key={k} className="border-b border-line/60">
                  <td className="py-0.5 pr-3 text-ink-2">{k}</td>
                  <td className="py-0.5 num">{typeof v === "object" ? JSON.stringify(v) : String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </li>
  );
}
