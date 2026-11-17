import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { ChevronLeft } from "lucide-react";
import { api, type MetricKey } from "../api";
import { fmt, fmtDate, METRICS, metricMeta, shortDate } from "../format";
import { useOpenDay } from "../components/DayDrawer";
import { DailyTable } from "../components/DailyTable";
import { ErrorNote, Legend, Loading, PageHeader, Panel, Segmented, Swatch, useChartTheme } from "../components/ui";

function dateRange(first: string, last: string): string[] {
  const out: string[] = [];
  const d = new Date(first + "T00:00:00Z"), end = new Date(last + "T00:00:00Z");
  while (d <= end) { out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }
  return out;
}

export function AthletePage() {
  const { id = "" } = useParams();
  const athletes = useQuery({ queryKey: ["athletes"], queryFn: api.athletes });
  const daily = useQuery({ queryKey: ["daily", id], queryFn: () => api.daily({ athlete: id }) });
  const [metric, setMetric] = useState<MetricKey>("trimp");
  const t = useChartTheme();
  const openDay = useOpenDay();
  const a = athletes.data?.find((x) => x.athlete_id === id);
  const meta = metricMeta(metric);

  const option = useMemo(() => {
    if (!a?.history.first_date || !daily.data) return null;
    const dates = dateRange(a.history.first_date, a.history.last_date!);
    const byDate = new Map(daily.data.map((r) => [r.date, r]));
    const decal = { symbol: "rect", symbolSize: 1, dashArrayX: [1, 0], dashArrayY: [2, 3], rotation: Math.PI / 4, color: "rgba(255,255,255,0.75)" };
    const series = (bucket: "training" | "game" | "other", color: string, name: string) => ({
      name, type: "bar", stack: "day", barMaxWidth: 10, barCategoryGap: "25%",
      itemStyle: { color, borderRadius: bucket === "training" ? [0, 0, 0, 0] : [3, 3, 0, 0], borderColor: t.surface, borderWidth: 0.5 },
      emphasis: { focus: "none" },
      data: dates.map((d) => {
        const r = byDate.get(d);
        const v = r ? (r[`${bucket}_${metric}`] as number | null) : null;
        if (v === null || v === undefined) return null;
        const partial = r![metric].completeness === "partial";
        return partial ? { value: v, itemStyle: { decal } } : v;
      }),
    });
    const gapAreas = a.history.gaps.map((g) => [{ xAxis: g.from }, { xAxis: g.to }]);
    return {
      textStyle: { fontFamily: t.font },
      aria: { enabled: true, decal: { show: false } },
      grid: { left: 48, right: 16, top: 32, bottom: 56 },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" },
        backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.ink, fontFamily: t.font },
        formatter: (ps: { axisValue: string }[]) => {
          const d = ps[0].axisValue, r = byDate.get(d);
          if (!r) return `<b>${fmtDate(d, true)}</b><br/>No data recorded (unobserved, not rest)`;
          const b = r[metric];
          const lines = [`<b>${fmtDate(d, true)}</b>`, `${meta.label}: <b>${fmt(b.value, meta.digits)}</b> ${meta.unit}`];
          if (r[`training_${metric}`] != null) lines.push(`Training: ${fmt(r[`training_${metric}`] as number, meta.digits)}`);
          if (r[`game_${metric}`] != null) lines.push(`Game: ${fmt(r[`game_${metric}`] as number, meta.digits)}`);
          if (b.completeness === "partial") lines.push(`<span style="color:${t.serious}">Partial: ${b.valid_sessions} of ${b.expected_sessions} sessions have this metric</span>`);
          if (b.completeness === "missing") lines.push(`Missing in every session (null, not zero)`);
          if (r.gd_labels.length) lines.push(`Game-day label: ${r.gd_labels.join(", ")}`);
          return lines.join("<br/>");
        },
      },
      xAxis: {
        type: "category", data: dates, axisTick: { show: false },
        axisLine: { lineStyle: { color: t.lineStrong } },
        axisLabel: { color: t.muted, formatter: (v: string) => shortDate(v), interval: Math.max(0, Math.floor(dates.length / 10)) },
      },
      yAxis: {
        type: "value", name: meta.unit, nameTextStyle: { color: t.muted }, splitNumber: 4,
        splitLine: { lineStyle: { color: t.line } }, axisLabel: { color: t.muted },
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 8, borderColor: t.line, textStyle: { color: t.muted }, fillerColor: "rgba(42,120,214,0.12)" }],
      series: [
        { ...series("training", t.training, "Training"), markArea: { silent: true, itemStyle: { color: t.line, opacity: 0.35 }, data: gapAreas } },
        series("other", t.other, "Other"),
        series("game", t.game, "Game"),
      ],
    };
  }, [a, daily.data, metric, t, meta]);

  if (athletes.isLoading || daily.isLoading) return <Loading what="Loading athlete" />;
  if (athletes.error || daily.error) return <ErrorNote error={athletes.error ?? daily.error} />;
  if (!a) return <ErrorNote error="Athlete not found." />;
  const h = a.history;

  return (
    <>
      <Link to="/" className="mb-2 inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink"><ChevronLeft size={15} />Squad</Link>
      <PageHeader
        title={a.label}
        sub={<>{h.observed_days} days with recorded sessions between {fmtDate(h.first_date)} and {fmtDate(h.last_date)}. {h.gaps.length} gaps ({h.gaps.reduce((s, g) => s + g.days, 0)} days) have no data; they are not counted as rest or zero load.</>}
        actions={<Segmented label="Metric" value={metric} onChange={setMetric} options={METRICS.map((m) => ({ value: m.key, label: m.short }))} />}
      />
      <Panel
        title={`Daily ${meta.noun} (${meta.unit})`}
        aside={<Legend items={[
          { label: "Training", swatch: <Swatch color="var(--training)" /> },
          { label: "Game", swatch: <Swatch color="var(--game)" /> },
          { label: "Partial day (striped bar)", swatch: <Swatch color="var(--training)" hatch /> },
          { label: "No data", swatch: <span aria-hidden className="inline-block h-3 w-3 rounded-[3px]" style={{ background: "var(--line)" }} /> },
        ]} />}
        className="mb-5"
      >
        {option && (
          <ReactECharts option={option} notMerge style={{ height: 320 }}
            onEvents={{ click: (p: { name: string }) => openDay(id, p.name) }} />
        )}
        <p className="mt-1 text-xs text-muted">Click a bar to see the sessions behind it. Scroll or drag the slider to zoom.</p>
      </Panel>
      <h2 className="mb-2 text-lg font-semibold">Daily records</h2>
      <DailyTable rows={daily.data!} showAthlete={false} pageSize={15} />
    </>
  );
}
