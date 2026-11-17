import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api, type Flag, type ReviewItem, type SessionRecord, type Severity } from "../api";
import { fmt, fmtDate, humanRule } from "../format";
import { Button, ErrorNote, Loading, PageHeader, Panel, Select, SeverityTag } from "../components/ui";

export function QualityPage() {
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const flags = useQuery({ queryKey: ["flags"], queryFn: api.flags });
  const [inspect, setInspect] = useState<string | null>(null);
  const s = status.data?.summary;

  if (status.isLoading || flags.isLoading) return <Loading what="Loading checks" />;
  if (flags.error) return <ErrorNote error={flags.error} />;

  return (
    <>
      <PageHeader title="Data quality" sub="What the checks found, what was left out of the totals, and why. Warnings flag values that look unusual; they still count unless you exclude them." />
      {s && (
        <dl className="mb-6 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
          {[
            ["Session records", s.session_records.toLocaleString()],
            ["Athletes", s.athletes],
            ["Resolved dates", s.resolved_dates],
            ["Errors", s.flags.error],
            ["Warnings", s.flags.warning],
            ["Excluded duplicates", s.excluded_exact_duplicates],
          ].map(([k, v]) => (
            <div key={k} className="bg-surface px-4 py-3">
              <dt className="text-sm text-ink-2">{k}</dt>
              <dd className="text-2xl font-bold num">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      <ReviewQueue onInspect={setInspect} />
      <IssueTable flags={flags.data!} onInspect={setInspect} />
      <Imports />
      {inspect && <Inspector id={inspect} onClose={() => setInspect(null)} />}
    </>
  );
}

function ReviewQueue({ onInspect }: { onInspect: (id: string) => void }) {
  const q = useQuery({ queryKey: ["review"], queryFn: api.review });
  const items = q.data ?? [];
  return (
    <Panel title="Duplicate review" className="mb-6"
      aside={<span className="text-sm text-ink-2">{items.length} session{items.length === 1 ? "" : "s"} to review</span>}>
      {q.isLoading ? <Loading /> : q.error ? <ErrorNote error={q.error} /> : items.length === 0 ? (
        <p className="text-ink-2">
          No exact copies or overlapping sessions were found. Several sessions for one athlete on the same day are normal
          (e.g. morning practice and an evening game) and are all counted.
        </p>
      ) : (
        <ul className="divide-y divide-line">{items.map((i) => <ReviewRow key={i.record_id} item={i} onInspect={onInspect} />)}</ul>
      )}
    </Panel>
  );
}

const KIND_TEXT = {
  exact_duplicate: "Exact copy of another row. Kept on file, not counted.",
  possible_duplicate: "Overlaps another session for the same athlete. Counted until you decide.",
  manual_override: "Decided manually.",
};

function ReviewRow({ item, onInspect }: { item: ReviewItem; onInspect: (id: string) => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState(item.override?.reason ?? "");
  const save = useMutation({
    mutationFn: (action: "include" | "exclude") => api.setOverride(item.record_id, action, reason),
    onSuccess: () => qc.invalidateQueries(),
  });
  const undo = useMutation({ mutationFn: () => api.clearOverride(item.record_id), onSuccess: () => qc.invalidateQueries() });
  const counted = item.status === "included";
  return (
    <li className="grid gap-3 py-3 lg:grid-cols-[1fr_auto]">
      <div>
        <p className="font-semibold">
          {item.athlete_label} · {fmtDate(item.date, true)} · {item.measurement_type} {item.start_time}–{item.end_time}
          <span className={`ml-2 text-sm font-medium ${counted ? "text-good" : "text-serious"}`}>{counted ? "Counted" : "Not counted"}</span>
        </p>
        <p className="text-sm text-ink-2">
          {KIND_TEXT[item.kind]} Row {item.excel_row} of {item.file}. TRIMP {fmt(item.metrics.trimp)}, Movement Load {fmt(item.metrics.movement_load)}, {fmt(item.metrics.duration_min)} min.
          {item.related.length > 0 && <> Related: {item.related.map((r) => <button key={r} className="ml-1 underline hover:text-ink" onClick={() => onInspect(r)}>{r.split(":")[1]}</button>)}</>}
        </p>
        {item.override && <p className="text-sm">Decision: <b>{item.override.action}</b> — “{item.override.reason}”</p>}
        {save.error && <ErrorNote error={save.error} />}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)"
          aria-label={`Reason for ${item.record_id}`} className="w-52 rounded-md border border-line-strong bg-surface px-2 py-1.5 text-sm" />
        <Button onClick={() => save.mutate("include")} disabled={!reason.trim() || save.isPending}>Count it</Button>
        <Button onClick={() => save.mutate("exclude")} disabled={!reason.trim() || save.isPending}>Leave it out</Button>
        {item.override && <Button variant="ghost" onClick={() => undo.mutate()}>Undo decision</Button>}
        <Button variant="ghost" onClick={() => onInspect(item.record_id)}>Inspect</Button>
      </div>
    </li>
  );
}

function IssueTable({ flags, onInspect }: { flags: Flag[]; onInspect: (id: string) => void }) {
  const [sev, setSev] = useState<"" | Severity>("");
  const [rule, setRule] = useState("");
  const [athlete, setAthlete] = useState("");
  const [limit, setLimit] = useState(50);
  const rules = useMemo(() => [...new Set(flags.map((f) => f.rule_code))].sort(), [flags]);
  const athletes = useMemo(() => [...new Map(flags.filter((f) => f.athlete_id).map((f) => [f.athlete_id!, f.athlete_label!])).entries()]
    .sort((a, b) => a[1].localeCompare(b[1], undefined, { numeric: true })), [flags]);
  const rows = flags.filter((f) => (!sev || f.severity === sev) && (!rule || f.rule_code === rule) && (!athlete || f.athlete_id === athlete));

  return (
    <Panel title="Issues" className="mb-6" pad={false}
      aside={<div className="flex flex-wrap gap-2">
        <Select label="Severity" value={sev} onChange={(v) => setSev(v as typeof sev)}>
          <option value="">All</option><option value="error">Errors</option><option value="warning">Warnings</option><option value="info">Info</option>
        </Select>
        <Select label="Check" value={rule} onChange={setRule}>
          <option value="">All checks</option>{rules.map((r) => <option key={r} value={r}>{humanRule(r)}</option>)}
        </Select>
        <Select label="Athlete" value={athlete} onChange={setAthlete}>
          <option value="">All athletes</option>{athletes.map(([id, l]) => <option key={id} value={id}>{l}</option>)}
        </Select>
      </div>}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="border-b border-line text-left text-ink-2">
            <tr>{["Severity", "Check", "Athlete", "Date", "Row", "Field", "What we found", "Effect on totals"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((f) => (
              <tr key={f.flag_id} className={`border-b border-line/70 align-top ${f.record_id ? "cursor-pointer hover:bg-surface-2/70" : ""}`}
                onClick={() => f.record_id && onInspect(f.record_id)} tabIndex={f.record_id ? 0 : undefined}
                onKeyDown={(e) => e.key === "Enter" && f.record_id && onInspect(f.record_id)}>
                <td className="px-3 py-2"><SeverityTag severity={f.severity} /></td>
                <td className="px-3 py-2 font-medium">{humanRule(f.rule_code)}</td>
                <td className="px-3 py-2 whitespace-nowrap">{f.athlete_label ?? "—"}</td>
                <td className="px-3 py-2 whitespace-nowrap">{f.date ? fmtDate(f.date) : "—"}</td>
                <td className="px-3 py-2 num">{f.excel_row ?? "—"}</td>
                <td className="px-3 py-2 text-ink-2">{f.field ?? "—"}</td>
                <td className="px-3 py-2 max-w-[40ch]">{f.explanation}</td>
                <td className="px-3 py-2 max-w-[36ch] text-ink-2">{f.aggregation_effect}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={8} className="px-3 py-8 text-center text-ink-2">No issues match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
      <footer className="flex items-center justify-between border-t border-line px-3 py-2 text-sm text-ink-2">
        <span className="num">Showing {Math.min(limit, rows.length)} of {rows.length}</span>
        {rows.length > limit && <Button variant="ghost" onClick={() => setLimit(limit + 100)}>Show more</Button>}
      </footer>
    </Panel>
  );
}

const FIELD_MAP: [string, string, (r: SessionRecord) => unknown][] = [
  ["athlete", "Athlete", (r) => `${r.athlete_label ?? "—"} (${r.athlete_id ?? "no ID"})`],
  ["date", "Date", (r) => r.date],
  ["study_day_index", "Study day", (r) => r.study_day_index],
  ["measurement_type", "Measurement type", (r) => r.measurement_type],
  ["gd", "GD", (r) => r.gd],
  ["start_time", "Start", (r) => r.start_time],
  ["end_time", "End", (r) => r.end_time],
  ["duration", "Duration (min)", (r) => r.metrics?.duration_min],
  ["hit", "High-intensity (min)", (r) => r.metrics?.hit_min],
  ["trimp", "TRIMP (index)", (r) => r.metrics?.trimp],
  ["movement_load", "Movement Load (AU)", (r) => r.metrics?.movement_load],
  ["trimp_per_min", "TRIMP/min (source)", (r) => r.source_ratios?.trimp_per_min],
  ["avg_movement_intensity", "Avg movement intensity (source)", (r) => r.source_ratios?.avg_movement_intensity],
  ["measurement_error", "Measurement error (%)", (r) => (r as unknown as { measurement_error_pct: number | null }).measurement_error_pct],
  ["hr_min", "Min HR (bpm)", (r) => r.heart_rate?.min_bpm],
  ["hr_avg", "Avg HR (bpm)", (r) => r.heart_rate?.avg_bpm],
  ["hr_peak", "Peak HR (bpm)", (r) => r.heart_rate?.peak_bpm],
  ["source_acwr", "ACWR (source-reported)", (r) => r.source_reported?.acwr],
];

const show = (v: unknown) => v === null || v === undefined ? <span className="text-muted">null</span>
  : typeof v === "number" ? <span className="num">{Number.isInteger(v) ? v : v.toFixed(4)}</span>
  : typeof v === "object" ? JSON.stringify(v) : String(v);

function Inspector({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["record", id], queryFn: () => api.record(id) });
  const r = q.data?.record;
  const isWellness = !!r?.values;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Record inspector">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative h-full w-full max-w-[640px] overflow-y-auto border-l border-line bg-page shadow-xl">
        <header className="sticky top-0 flex items-start justify-between border-b border-line bg-surface px-5 py-4">
          <div>
            <p className="text-sm text-ink-2">{r ? `${r.provenance.file}, sheet “${r.provenance.sheet}”, row ${r.provenance.excel_row}` : id}</p>
            <h2 className="text-xl font-bold">Original and normalized values</h2>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-ink-2 hover:bg-surface-2"><X size={20} /></button>
        </header>
        <div className="space-y-4 px-5 py-4">
          {q.isLoading && <Loading />}
          {q.error && <ErrorNote error={q.error} />}
          {r && (
            <>
              <p className="text-sm">Status: <b>{r.status}</b>{r.status_reason && <> ({r.status_reason.replace(/_/g, " ")})</>}</p>
              <table className="w-full text-sm">
                <thead className="border-b border-line text-left text-ink-2"><tr><th className="py-1.5 font-medium">Field</th><th className="py-1.5 font-medium">In the file</th><th className="py-1.5 font-medium">LoadWise value</th></tr></thead>
                <tbody>
                  {isWellness
                    ? Object.entries(r.values!).map(([k, v]) => (
                      <tr key={k} className="border-b border-line/70"><td className="py-1 text-ink-2">{k}</td><td className="py-1">{show(r.source_values[k])}</td><td className="py-1">{show(v)}</td></tr>))
                    : FIELD_MAP.map(([k, label, get]) => (
                      <tr key={k} className="border-b border-line/70">
                        <td className="py-1 text-ink-2">{label}</td>
                        <td className="py-1">{show(r.source_values[k])}</td>
                        <td className="py-1">{show(get(r))}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
              {q.data!.flags.length > 0 && (
                <ul className="space-y-1 text-sm">
                  {q.data!.flags.map((f) => <li key={f.flag_id} className="flex gap-2"><SeverityTag severity={f.severity} /><span><b>{humanRule(f.rule_code)}.</b> {f.explanation}</span></li>)}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Imports() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const [confirm, setConfirm] = useState(false);
  const reset = useMutation({ mutationFn: api.reset, onSuccess: () => qc.invalidateQueries() });
  return (
    <Panel title="Imported files">
      <ul className="mb-3 space-y-1 text-sm">
        {status.data?.imports.map((i) => (
          <li key={i.sha256}><b>{i.filename}</b> <span className="text-ink-2">· season {i.season_start_year} · added {fmtDate(i.uploaded_at.slice(0, 10))} · {(i.size_bytes / 1024 / 1024).toFixed(1)} MB · {i.sha256.slice(0, 12)}</span></li>
        ))}
      </ul>
      <p className="mb-3 text-sm text-ink-2">Adding the same file again changes nothing. Files that overlap are de-duplicated row by row.</p>
      {confirm ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm">Remove all imported files and review decisions?</span>
          <Button variant="danger" onClick={() => reset.mutate()}>Clear history</Button>
          <Button variant="ghost" onClick={() => setConfirm(false)}>Keep it</Button>
        </div>
      ) : <Button variant="danger" onClick={() => setConfirm(true)}>Clear history…</Button>}
    </Panel>
  );
}
