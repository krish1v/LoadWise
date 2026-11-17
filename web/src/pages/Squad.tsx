import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp } from "lucide-react";
import { api, type DailyRow, type MetricKey, type SquadAthlete } from "../api";
import { fmt, fmtDate, METRICS, metricMeta } from "../format";
import { useOpenDay } from "../components/DayDrawer";
import { LoadStrip } from "../components/LoadStrip";
import { DateInput, ErrorNote, FlagCounts, Legend, Loading, PageHeader, Segmented, Swatch } from "../components/ui";

type SortKey = "label" | "last7" | "last28" | "sessions" | "flags";

function lastNDays(end: string, n: number): string[] {
  const [y, m, d] = end.split("-").map(Number);
  return Array.from({ length: n }, (_, i) => new Date(Date.UTC(y, m - 1, d - (n - 1 - i))).toISOString().slice(0, 10));
}

export function SquadPage() {
  const [refDate, setRefDate] = useState("");
  const summary = useQuery({ queryKey: ["summary", refDate], queryFn: () => api.summary(refDate || undefined), placeholderData: (p) => p });
  const daily = useQuery({ queryKey: ["daily", "all"], queryFn: () => api.daily() });
  const [metric, setMetric] = useState<MetricKey>("trimp");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "label", desc: false });
  const openDay = useOpenDay();

  const byAthlete = useMemo(() => {
    const m = new Map<string, Map<string, DailyRow>>();
    daily.data?.forEach((r) => {
      if (!m.has(r.athlete_id)) m.set(r.athlete_id, new Map());
      m.get(r.athlete_id)!.set(r.date, r);
    });
    return m;
  }, [daily.data]);

  if (summary.isLoading || daily.isLoading) return <Loading what="Loading squad" />;
  if (summary.error) return <ErrorNote error={summary.error} />;
  if (daily.error) return <ErrorNote error={daily.error} />;
  const { summary: s, squad } = summary.data!;
  const ref = squad.reference_date!;
  const days = lastNDays(ref, 28);
  const meta = metricMeta(metric);
  const max = Math.max(1, ...daily.data!.filter((r) => r.date >= days[0]).map((r) => r[metric].value ?? 0));

  const val = (a: SquadAthlete, k: SortKey): number | string => {
    if (k === "label") return a.label;
    if (k === "last7" || k === "last28") return a[k][metric].value ?? -1;
    if (k === "sessions") return a.sessions;
    return a.flags.error * 1000 + a.flags.warning;
  };
  const athletes = [...squad.athletes].sort((a, b) => {
    const x = val(a, sort.key), y = val(b, sort.key);
    const c = typeof x === "string" ? x.localeCompare(String(y), undefined, { numeric: true }) : (x as number) - (y as number);
    return sort.desc ? -c : c;
  });
  const th = (k: SortKey, label: string, right = true) => (
    <th className={`px-3 py-2 font-medium ${right ? "text-right" : "text-left"}`} aria-sort={sort.key === k ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => setSort({ key: k, desc: sort.key === k ? !sort.desc : k !== "label" })}>
        {label}{sort.key === k && (sort.desc ? <ArrowDown size={13} /> : <ArrowUp size={13} />)}
      </button>
    </th>
  );

  return (
    <>
      <PageHeader
        title="Squad"
        sub={<>{s.athletes} athletes, {s.daily_records.toLocaleString()} athlete-days from {s.session_records.toLocaleString()} sessions. {s.multi_session_days} days combine two or more sessions. Showing the 28 days up to {fmtDate(ref)}.</>}
        actions={<div className="flex flex-wrap items-end gap-3">
          <DateInput label="Window ends" value={refDate || ref} min={squad.first_date} max={squad.last_date} onChange={setRefDate} />
          <Segmented label="Metric" value={metric} onChange={setMetric} options={METRICS.map((m) => ({ value: m.key, label: m.short }))} />
        </div>}
      />
      <div className="mb-3">
        <Legend items={[
          { label: "Training", swatch: <Swatch color="var(--training)" /> },
          { label: "Game", swatch: <Swatch color="var(--game)" /> },
          { label: "Partial: some sessions lack this metric", swatch: <Swatch color="var(--serious)" hatch /> },
          { label: "No data recorded", swatch: <Swatch dashed /> },
        ]} />
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-[920px] text-sm">
          <thead className="border-b border-line text-ink-2">
            <tr>
              {th("label", "Athlete", false)}
              <th className="px-3 py-2 text-left font-medium">Daily {meta.noun}, last 28 days</th>
              {th("last7", `7-day ${meta.short}`)}
              {th("last28", `28-day ${meta.short}`)}
              {th("sessions", "Sessions")}
              {th("flags", "Issues")}
            </tr>
          </thead>
          <tbody>
            {athletes.map((a) => (
              <tr key={a.athlete_id} className="border-b border-line/70 last:border-0 hover:bg-surface-2/60">
                <td className="px-3 py-2">
                  <Link to={`/athlete/${a.athlete_id}`} className="font-semibold hover:underline">{a.label}</Link>
                  <div className="text-xs text-muted">{a.observed_days} days recorded</div>
                </td>
                <td className="px-3 py-1.5">
                  <LoadStrip days={days} rows={byAthlete.get(a.athlete_id) ?? new Map()} metric={metric} max={max}
                    label={`${a.label} daily ${meta.label}`} onDay={(d) => openDay(a.athlete_id, d)} />
                </td>
                <WindowCell w={a.last7[metric]} digits={meta.digits} />
                <WindowCell w={a.last28[metric]} digits={meta.digits} />
                <td className="px-3 py-2 text-right num">{a.sessions}<span className="text-muted"> ({a.games} games)</span></td>
                <td className="px-3 py-2 text-right"><FlagCounts counts={a.flags} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">{squad.window_note}</p>
    </>
  );
}

function WindowCell({ w, digits }: { w: SquadAthlete["last7"]["trimp"]; digits: number }) {
  return (
    <td className="px-3 py-2 text-right num">
      <div className="font-semibold">{fmt(w.value, digits)}</div>
      <div className="text-xs text-muted">
        {w.observed_days} days{w.incomplete_days > 0 && <span className="text-serious">, {w.incomplete_days} partial</span>}
      </div>
    </td>
  );
}
