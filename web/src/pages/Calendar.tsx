import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type MetricKey } from "../api";
import { fmt, fmtDate, METRICS, metricMeta } from "../format";
import { useOpenDay } from "../components/DayDrawer";
import { ErrorNote, Legend, Loading, PageHeader, Segmented, Swatch, useChartTheme } from "../components/ui";

// Sequential blue ramp from the validated palette; one hue for magnitude. Low values recede
// toward the surface, so the ramp runs light->dark on a light page and dark->light on a dark one.
const RAMP_LIGHT = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
const RAMP_DARK = [...RAMP_LIGHT].reverse();
const CELL_W = 9, CELL_H = 20, GAP = 1.5, LABEL_W = 92, TOP = 26;

export function CalendarPage() {
  const [metric, setMetric] = useState<MetricKey>("trimp");
  const q = useQuery({ queryKey: ["calendar", metric], queryFn: () => api.calendar(metric) });
  const openDay = useOpenDay();
  const meta = metricMeta(metric);
  const RAMP = useChartTheme().dark ? RAMP_DARK : RAMP_LIGHT;

  const bins = useMemo(() => {
    const vals = (q.data?.athletes.flatMap((a) => a.cells.map((c) => c?.value)).filter((v): v is number => v !== null && v !== undefined && v > 0) ?? []).sort((a, b) => a - b);
    if (!vals.length) return [];
    return RAMP.slice(1).map((_, i) => vals[Math.floor(((i + 1) / RAMP.length) * (vals.length - 1))]);
  }, [q.data, RAMP]);
  const color = (v: number) => RAMP[bins.findIndex((b) => v <= b) === -1 ? RAMP.length - 1 : bins.findIndex((b) => v <= b)];

  if (q.isLoading) return <Loading what="Loading calendar" />;
  if (q.error) return <ErrorNote error={q.error} />;
  const { dates, athletes } = q.data!;
  const w = LABEL_W + dates.length * (CELL_W + GAP);
  const h = TOP + athletes.length * (CELL_H + GAP);
  const monthStarts = dates.map((d, i) => ({ d, i })).filter(({ d, i }) => i === 0 || d.endsWith("-01"));

  return (
    <>
      <PageHeader
        title="Season calendar"
        sub={`Every athlete’s daily ${meta.noun} from ${fmtDate(dates[0])} to ${fmtDate(dates[dates.length - 1])}. Stronger colour means more load. Click a day for its sessions.`}
        actions={<Segmented label="Metric" value={metric} onChange={setMetric} options={METRICS.map((m) => ({ value: m.key, label: m.short }))} />}
      />
      <div className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-center gap-2 text-sm text-ink-2">
          <span>Lower</span>
          <span className="flex">{RAMP.map((c) => <span key={c} className="h-3 w-5" style={{ background: c }} aria-hidden />)}</span>
          <span>Higher {meta.unit}</span>
        </div>
        <Legend items={[
          { label: "Game that day", swatch: <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: "var(--game)" }} /> },
          { label: "Partial", swatch: <Swatch color="var(--serious)" hatch /> },
          { label: "Metric missing", swatch: <span aria-hidden className="hatch inline-block h-3 w-3 rounded-[3px] text-muted" /> },
          { label: "No data recorded", swatch: <Swatch dashed /> },
        ]} />
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-surface p-3">
        <svg width={w} height={h} role="grid" aria-label={`Calendar heatmap of daily ${meta.label}`} style={{ fontFamily: "inherit" }}>
          <defs>
            <pattern id="cal-hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="4" stroke="var(--serious)" strokeWidth="1.6" />
            </pattern>
            <pattern id="cal-missing" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="4" stroke="var(--muted)" strokeWidth="1.2" />
            </pattern>
          </defs>
          {monthStarts.map(({ d, i }) => (
            <g key={d}>
              <text x={LABEL_W + i * (CELL_W + GAP)} y={12} fontSize={12} fill="var(--ink-2)">{fmtDate(d).replace(/^\d+ /, "")}</text>
              <line x1={LABEL_W + i * (CELL_W + GAP) - 1} x2={LABEL_W + i * (CELL_W + GAP) - 1} y1={16} y2={h} stroke="var(--line-strong)" />
            </g>
          ))}
          {athletes.map((a, r) => {
            const y = TOP + r * (CELL_H + GAP);
            return (
              <g key={a.athlete_id} role="row">
                <Link to={`/athlete/${a.athlete_id}`}>
                  <text x={0} y={y + CELL_H / 2 + 4} fontSize={13} fill="var(--ink)" className="hover:underline">{a.label}</text>
                </Link>
                {a.cells.map((c, i) => {
                  const x = LABEL_W + i * (CELL_W + GAP);
                  const d = dates[i];
                  if (!c) return (
                    <rect key={d} x={x + 0.5} y={y + 0.5} width={CELL_W - 1} height={CELL_H - 1} rx={1.5} fill="none"
                      stroke="var(--line)" strokeDasharray="2 1.5"><title>{a.label}, {fmtDate(d, true)}: no data recorded</title></rect>
                  );
                  const tip = `${a.label}, ${fmtDate(d, true)}: ${meta.label} ${fmt(c.value, meta.digits)}${c.completeness === "partial" ? " (partial)" : c.completeness === "missing" ? " (missing in all sessions)" : ""}${c.has_game ? ", game day" : ""}`;
                  return (
                    <g key={d} role="gridcell" tabIndex={0} aria-label={tip} className="cursor-pointer"
                      onClick={() => openDay(a.athlete_id, d)}
                      onKeyDown={(e) => { if (e.key === "Enter") openDay(a.athlete_id, d); }}>
                      <title>{tip}</title>
                      <rect x={x} y={y} width={CELL_W} height={CELL_H} rx={1.5}
                        fill={c.value === null ? "url(#cal-missing)" : c.value === 0 ? "var(--surface-2)" : color(c.value)} />
                      {c.completeness === "partial" && <rect x={x} y={y} width={CELL_W} height={6} fill="url(#cal-hatch)" />}
                      {c.has_game && <circle cx={x + CELL_W / 2} cy={y + CELL_H - 4} r={2.2} fill="var(--game)" stroke="var(--surface)" strokeWidth={1} />}
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="mt-2 text-xs text-muted">Colour bands are equal-count bins of the observed values. Dashed cells are days with no recorded session; they are not rest days or zero load.</p>
    </>
  );
}
