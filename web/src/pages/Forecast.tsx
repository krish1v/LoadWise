import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { Download } from "lucide-react";
import { api, baselineUrl } from "../api";
import { fmt, fmtDate, shortDate } from "../format";
import { ErrorNote, Legend, Loading, PageHeader, Panel, Select, useChartTheme } from "../components/ui";

const DEFAULT = [90, 90, 75, 0, 90, 60, 0];

export function ForecastPage() {
  const athletes = useQuery({ queryKey: ["athletes"], queryFn: api.athletes });
  const meta = useQuery({ queryKey: ["forecast-meta"], queryFn: api.forecastMeta, retry: false });
  const [athlete, setAthlete] = useState("");
  const [plan, setPlan] = useState<string[]>(DEFAULT.map(String));
  const minutes = plan.map((v) => Math.max(0, Number(v) || 0));
  const t = useChartTheme();

  useEffect(() => { if (!athlete && athletes.data?.length) setAthlete(athletes.data[0].athlete_id); }, [athletes.data, athlete]);
  const fc = useQuery({
    queryKey: ["forecast", athlete, minutes.join(",")],
    queryFn: () => api.forecast(athlete, minutes),
    enabled: !!athlete && !meta.error,
    placeholderData: (p) => p,
  });

  const option = useMemo(() => {
    const f = fc.data;
    if (!f) return null;
    const hist = f.observed_history;
    const cats = [...hist.map((h) => h.date), ...f.days.map((d) => d.date ?? `+${d.day_index}`)];
    return {
      textStyle: { fontFamily: t.font },
      grid: { left: 48, right: 16, top: 32, bottom: 36 },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: t.surface, borderColor: t.line,
        textStyle: { color: t.ink, fontFamily: t.font },
        formatter: (ps: { axisValue: string; seriesName: string; value: number | null }[]) => {
          const p = ps.find((x) => x.value !== null && x.value !== undefined);
          if (!p) return "";
          const h = hist.find((x) => x.date === p.axisValue);
          const d = f.days.find((x) => x.date === p.axisValue);
          return h ? `<b>${fmtDate(h.date, true)}</b><br/>Recorded training TRIMP: <b>${fmt(h.training_trimp)}</b><br/>${fmt(h.training_minutes)} min · ${fmt(h.trimp_per_min, 2)} per min`
            : d ? `<b>${d.date ? fmtDate(d.date, true) : `Day ${d.day_index}`}</b><br/>Predicted training TRIMP: <b>${fmt(d.predicted_trimp)}</b><br/>Planned ${fmt(d.planned_minutes)} min` : "";
        },
      },
      xAxis: { type: "category", data: cats, axisTick: { show: false }, axisLine: { lineStyle: { color: t.lineStrong } },
        axisLabel: { color: t.muted, formatter: (v: string) => (v.startsWith("+") ? v : shortDate(v)), interval: "auto" } },
      yAxis: { type: "value", name: "TRIMP", nameTextStyle: { color: t.muted }, splitNumber: 4, splitLine: { lineStyle: { color: t.line } }, axisLabel: { color: t.muted } },
      series: [
        { name: "Recorded", type: "bar", barMaxWidth: 12, stack: "x", itemStyle: { color: t.training, borderRadius: [3, 3, 0, 0] },
          data: [...hist.map((h) => h.training_trimp), ...f.days.map(() => null)] },
        { name: "Predicted", type: "bar", barMaxWidth: 12, stack: "x",
          itemStyle: { color: "transparent", borderColor: t.training, borderWidth: 1.5, borderType: "dashed", borderRadius: [3, 3, 0, 0] },
          data: [...hist.map(() => null), ...f.days.map((d) => d.predicted_trimp)],
          markLine: hist.length ? { silent: true, symbol: "none", lineStyle: { color: t.lineStrong, type: "solid" }, label: { show: false },
            data: [{ xAxis: cats[hist.length - 1] }] } : undefined },
      ],
    };
  }, [fc.data, t]);

  if (athletes.isLoading || meta.isLoading) return <Loading what="Loading model" />;
  if (meta.error) return <ErrorNote error={meta.error} />;
  const f = fc.data, v = meta.data!.validation;

  return (
    <>
      <PageHeader title="Training load forecast"
        sub="The prediction model built by the modelling team: expected TRIMP for planned training sessions, from each athlete’s recorded TRIMP per minute. Games, injury risk and readiness are out of scope." />
      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <Panel title="Planned week">
          <Select label="Athlete" value={athlete} onChange={setAthlete} className="mb-4 w-full">
            {athletes.data?.map((a) => <option key={a.athlete_id} value={a.athlete_id}>{a.label}</option>)}
          </Select>
          <p className="mb-2 text-sm text-ink-2">Planned training minutes per day, starting the day after the last recorded session. Use 0 for no training.</p>
          <ol className="space-y-1.5">
            {plan.map((p, i) => (
              <li key={i} className="flex items-center justify-between gap-2 text-sm">
                <label htmlFor={`plan-${i}`}>{f?.days[i]?.date ? fmtDate(f.days[i].date, true) : `Day ${i + 1}`}</label>
                <span className="flex items-center gap-1.5">
                  <input id={`plan-${i}`} value={p} inputMode="numeric" onChange={(e) => setPlan(plan.map((x, j) => (j === i ? e.target.value : x)))}
                    className="w-16 rounded-md border border-line-strong bg-surface px-2 py-1 text-right num" />
                  <span className="w-14 text-right text-ink-2 num">{f ? fmt(f.days[i]?.predicted_trimp) : "—"}</span>
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-1 text-right text-xs text-muted">minutes → predicted TRIMP</p>
          {f && (
            <div className="mt-4 border-t border-line pt-3">
              <p className="text-sm text-ink-2">Week total</p>
              <p className="text-3xl font-bold num">{fmt(f.horizon_total_trimp)} <span className="text-base font-medium text-ink-2">TRIMP</span></p>
            </div>
          )}
          <a href={athlete ? baselineUrl(athlete, minutes) : "#"} className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm font-semibold hover:bg-surface-2">
            <Download size={15} />Baseline for the optimizer (JSON)
          </a>
        </Panel>

        <div className="space-y-5">
          <Panel title="Recorded and predicted training TRIMP"
            aside={<Legend items={[
              { label: "Recorded training", swatch: <span aria-hidden className="inline-block h-3 w-3 rounded-[3px]" style={{ background: "var(--training)" }} /> },
              { label: "Predicted", swatch: <span aria-hidden className="inline-block h-3 w-3 rounded-[3px] border-[1.5px] border-dashed" style={{ borderColor: "var(--training)" }} /> },
            ]} />}>
            {fc.error ? <ErrorNote error={fc.error} /> : option ? <ReactECharts option={option} notMerge style={{ height: 300 }} /> : <Loading />}
            {f && (
              <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                <div><dt className="text-ink-2">Model rate</dt><dd className="text-lg font-semibold num">{fmt(f.model_trimp_per_min, 2)} <span className="text-sm font-normal text-ink-2">TRIMP/min</span></dd></div>
                <div><dt className="text-ink-2">Rate from this data</dt><dd className="text-lg font-semibold num">{fmt(f.observed_median_trimp_per_min, 2)} <span className="text-sm font-normal text-ink-2">median, training days</span></dd></div>
                <div><dt className="text-ink-2">Athlete in training data</dt><dd className="text-lg font-semibold">{f.known_athlete ? "Yes" : "No, squad average used"}</dd></div>
              </dl>
            )}
          </Panel>

          <Panel title="How accurate is it?">
            <table className="w-full max-w-lg text-sm num">
              <thead className="border-b border-line text-left text-ink-2">
                <tr><th className="py-1.5 font-medium">Method</th><th className="py-1.5 text-right font-medium">Mean abs. error</th><th className="py-1.5 text-right font-medium">RMSE</th><th className="py-1.5 text-right font-medium">Bias</th></tr>
              </thead>
              <tbody>
                {([["Model (ridge regression)", v.regression], ["Athlete’s own average rate", v.athlete_history], ["Squad average rate", v.pooled_history]] as const).map(([n, m]) => (
                  <tr key={n} className="border-b border-line/70"><td className="py-1.5">{n}</td><td className="py-1.5 text-right">{fmt(m.mae, 1)}</td><td className="py-1.5 text-right">{fmt(m.rmse, 1)}</td><td className="py-1.5 text-right">{fmt(m.bias, 1)}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 max-w-[75ch] text-sm text-ink-2">
              Errors are in TRIMP on {v.test_n} held-out sessions (trained on {v.train_n}). The test set is small, so treat the edge over the simpler methods as exploratory.
              Recorded duration stood in for planned duration during testing.
            </p>
          </Panel>
        </div>
      </div>
    </>
  );
}
