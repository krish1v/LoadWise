import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { Download, Dumbbell, Moon, RotateCcw, Trophy, Zap } from "lucide-react";
import {
  api, PLANNING_FIELDS,
  type Activity, type PlanConfig, type PlanHistory, type PlanResult, type Planning, type PlanningKey,
} from "../api";
import { fmt, fmtDate, shortDate } from "../format";
import { Button, DateInput, ErrorNote, Legend, Loading, PageHeader, Panel, Segmented, Select, useChartTheme } from "../components/ui";

const ACTIVITY: Record<Activity, { label: string; icon: typeof Dumbbell; next: Activity }> = {
  training: { label: "Training", icon: Dumbbell, next: "game" },
  game: { label: "Game", icon: Trophy, next: "rest" },
  rest: { label: "Rest", icon: Moon, next: "training" },
};

const MINUTES: [PlanningKey, string][] = [
  ["original_team", "Planned team practice"],
  ["original_extra", "Planned individual work"],
  ["other_recorded", "Other monitored time"],
  ["team_min", "Team practice, min"],
  ["team_max", "Team practice, max"],
  ["extra_min", "Individual work, min"],
  ["extra_max", "Individual work, max"],
];
const LIMITS: [PlanningKey, string][] = [
  ["ml_limit", "Daily Movement Load limit"],
  ["trimp_limit", "Daily TRIMP limit"],
  ["ml_buffer", "Daily Movement Load buffer"],
  ["trimp_buffer", "Daily TRIMP buffer"],
  ["weekly_ml_limit", "Weekly Movement Load limit"],
  ["weekly_trimp_limit", "Weekly TRIMP limit"],
];
const TARGET_LABEL: Record<string, string> = { mip1: "MIP 1min", movement_load: "Movement Load", training_trimp: "TRIMP" };
const SPEC_LABEL: Record<string, string> = { joint: "History + duration", duration_only: "Duration only", history_reference: "28-day average (baseline)" };

type Draft = Record<PlanningKey, string>;
const toDraft = (p: Planning): Draft => Object.fromEntries(PLANNING_FIELDS.map((k) => [k, String(p[k])])) as Draft;

function parseDraft(d: Draft): Planning | string {
  const out = {} as Planning;
  for (const k of PLANNING_FIELDS) {
    const v = Number(d[k]);
    if (d[k].trim() === "" || !Number.isFinite(v) || v < 0) return `Enter a number of zero or more for every field (check “${[...MINUTES, ...LIMITS].find(([f]) => f === k)![1]}”).`;
    out[k] = v;
  }
  return out;
}

export function PlanPage() {
  const meta = useQuery({ queryKey: ["plan-meta"], queryFn: api.planMeta, retry: false });
  const [athlete, setAthlete] = useState("");
  const [start, setStart] = useState("");
  const [schedule, setSchedule] = useState<Activity[]>([]);
  const [objective, setObjective] = useState<PlanConfig["objective"]>("terminal");
  const [step, setStep] = useState<PlanConfig["step"]>(5);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [pooled, setPooled] = useState(false);
  const [pendingDemo, setPendingDemo] = useState<PlanConfig | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);

  useEffect(() => {
    const m = meta.data;
    if (!m || athlete) return;
    setSchedule(m.schedule);
    // /plan?demo=1 opens straight into the modelling team's reference example.
    if (m.demo && new URLSearchParams(window.location.search).get("demo") === "1") {
      setPendingDemo(m.demo); setAthlete(m.demo.athlete); setStart(m.demo.start);
      return;
    }
    setAthlete(m.roster[0]?.athlete_id ?? "");
    setStart(m.last_start ?? "");
  }, [meta.data, athlete]);

  const hist = useQuery({
    queryKey: ["plan-history", athlete, start],
    queryFn: () => api.planHistory(athlete, start),
    enabled: !!athlete && !!start,
    retry: false,
  });
  const run = useMutation({ mutationFn: api.planOptimize });

  // New athlete or start date: take the defaults the models suggest, unless the demo asked for its own inputs.
  useEffect(() => {
    const h = hist.data;
    if (!h) return;
    run.reset();
    if (pendingDemo && pendingDemo.athlete === h.athlete_id && pendingDemo.start === h.start) {
      setDraft(toDraft(pendingDemo.planning));
      setSchedule(pendingDemo.schedule);
      setObjective(pendingDemo.objective);
      setStep(pendingDemo.step);
      setPooled(false);
      setPendingDemo(null);
      run.mutate(pendingDemo);
      return;
    }
    setDraft(toDraft(h.planning));
    setPooled(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hist.data]);

  if (meta.isLoading) return <Loading what="Loading the planning models" />;
  if (meta.error) return <ErrorNote error={meta.error} />;
  const m = meta.data!;
  if (!m.roster.length) return <ErrorNote error="No training sessions are loaded, so there is nothing to plan from." />;
  const h = hist.data;

  const submit = () => {
    if (!draft || !h) return;
    const planning = parseDraft(draft);
    if (typeof planning === "string") { setInputError(planning); return; }
    setInputError(null);
    run.mutate({ athlete, start, planning, schedule, step, objective, allow_pooled: pooled, overrides: {} });
  };
  const loadDemo = () => {
    if (!m.demo) return;
    if (athlete === m.demo.athlete && start === m.demo.start) {
      setDraft(toDraft(m.demo.planning)); setSchedule(m.demo.schedule); setObjective(m.demo.objective); setStep(m.demo.step);
      run.mutate(m.demo);
    } else {
      setPendingDemo(m.demo); setAthlete(m.demo.athlete); setStart(m.demo.start);
    }
  };
  const resetInputs = () => { if (h) { setDraft(toDraft(h.planning)); setSchedule(m.schedule); setObjective("terminal"); setStep(5); run.reset(); } };

  return (
    <>
      <PageHeader
        title="Training plan"
        sub="Plan an athlete’s next seven days. From the athlete’s recent training history, LoadWise predicts MIP, Movement Load and TRIMP for each possible training duration, then picks the minutes for each day that best meet your goal within your workload limits."
        actions={m.demo && <Button onClick={loadDemo}><Zap size={15} />Run the reference example</Button>}
      />

      <div className="mb-5 flex flex-wrap items-end gap-x-5 gap-y-3 rounded-lg border border-line bg-surface px-4 py-3">
        <Select label="Athlete" value={athlete} onChange={(v) => { setAthlete(v); setPendingDemo(null); }} className="min-w-44">
          {m.roster.map((a) => <option key={a.athlete_id} value={a.athlete_id}>{a.label}</option>)}
        </Select>
        <DateInput label="First day of the plan" value={start} min={m.first_start ?? undefined} max={m.last_start ?? undefined}
          onChange={(v) => { if (v) { setStart(v); setPendingDemo(null); } }} />
        {h && <ModelMode h={h} fitting={m.fitting_period.last_date} />}
      </div>

      {hist.error ? <ErrorNote error={hist.error} /> : !h || !draft ? <Loading what="Reading training history" /> : (
        <div className="grid gap-5 xl:grid-cols-[400px_minmax(0,1fr)]">
          <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <Panel title="Week" aside={<button type="button" onClick={resetInputs} className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink"><RotateCcw size={14} />Reset</button>}>
              <p className="mb-2 text-sm text-ink-2">Select a day to change it: training, game or rest.</p>
              <ol className="grid grid-cols-7 gap-1">
                {schedule.map((kind, i) => {
                  const a = ACTIVITY[kind], Icon = a.icon, date = h.week_dates[i];
                  return (
                    <li key={i}>
                      <button type="button" aria-label={`${fmtDate(date, true)}: ${a.label}. Change`}
                        onClick={() => setSchedule(schedule.map((k, j) => (j === i ? a.next : k)))}
                        className={`flex w-full flex-col items-center gap-1 rounded-md border px-0.5 py-2 text-xs ${kind === "training" ? "border-training/60 bg-training/10" : kind === "game" ? "border-game/60 bg-game/10" : "border-line-strong bg-surface-2"}`}>
                        <span className="font-semibold">{fmtDate(date, true).split(" ")[0]}</span>
                        <span className="text-ink-2 num">{shortDate(date)}</span>
                        <Icon size={16} aria-hidden className={kind === "training" ? "text-training" : kind === "game" ? "text-game" : "text-muted"} />
                        <span>{a.label}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>
              <div className="mt-4 flex flex-wrap items-end gap-3">
                <div className="flex flex-col gap-0.5 text-xs text-ink-2">
                  Goal
                  <Segmented label="Goal" value={objective} onChange={setObjective}
                    options={[{ value: "terminal", label: "Best final day" }, { value: "cumulative", label: "Best whole week" }]} />
                </div>
                <Select label="Minute steps" value={String(step)} onChange={(v) => setStep(Number(v) as PlanConfig["step"])}>
                  <option value="1">1 minute</option><option value="5">5 minutes</option><option value="10">10 minutes</option>
                </Select>
              </div>
              <p className="mt-2 text-xs text-ink-2">
                {objective === "terminal" ? "Maximises predicted MIP on the last day, which must be a training day." : "Maximises predicted MIP summed over all training days."}
                {" "}Only training days are modelled; game and rest days carry no predictions.
              </p>
            </Panel>

            <Panel title="Minutes">
              <Fields fields={MINUTES} draft={draft} setDraft={setDraft} unit="min" />
              <p className="mt-2 text-xs text-ink-2">Predicted outcomes use the recorded duration: team practice + individual work + other monitored time.</p>
            </Panel>

            <Panel title="Workload limits">
              <Fields fields={LIMITS} draft={draft} setDraft={setDraft} />
              <p className="mt-2 text-xs text-ink-2">
                Suggested limits come from this athlete’s training days in the model data (daily: 90th percentile; weekly: 5 × 75th percentile).
                They are planning limits set by the coach, not safety thresholds.
              </p>
            </Panel>

            {!h.personalized && (
              <label className="flex items-start gap-2 rounded-lg border border-warning/60 bg-warning/10 px-3 py-2.5 text-sm">
                <input type="checkbox" checked={pooled} onChange={(e) => setPooled(e.target.checked)} className="mt-1" />
                <span>Use the squad models (duration only) for this athlete. They are not personalised. {h.reason}</span>
              </label>
            )}
            {inputError && <ErrorNote error={inputError} />}
            <Button type="submit" variant="primary" className="w-full py-2.5 text-[15px]" disabled={run.isPending || (!h.personalized && !pooled)}>
              <Zap size={16} />{run.isPending ? "Optimising the week…" : "Create the seven-day plan"}
            </Button>
          </form>

          <div className="min-w-0 space-y-5">
            {run.error ? <ErrorNote error={run.error} /> : run.data ? <PlanResultView r={run.data} label={h.label} />
              : run.isPending ? <Panel><Loading what="Predicting every candidate duration and solving the week" /></Panel>
              : <Panel><p className="py-6 text-center text-ink-2">Set the week and limits, then create the plan. Predictions appear here with the planned minutes for each day.</p></Panel>}
            <HistoryPanel h={h} />
          </div>
        </div>
      )}

      <ModelEvidencePanel />
    </>
  );
}

function ModelMode({ h, fitting }: { h: PlanHistory; fitting: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2 pb-1 text-sm">
      {h.personalized
        ? <span className="rounded-full bg-good/15 px-2.5 py-0.5 font-semibold text-ink">Personalised models</span>
        : <span className="rounded-full bg-warning/20 px-2.5 py-0.5 font-semibold text-ink">Squad models only</span>}
      <span className="text-ink-2">
        {h.personalized ? `${h.history.length} recorded training days before ${fmtDate(h.start)}` : h.reason}
      </span>
      {h.in_fitting_period && (
        <span className="text-ink-2">· Starts inside the models’ training period (to {fmtDate(fitting)}), so this replays data the models have seen.</span>
      )}
    </div>
  );
}

function Fields({ fields, draft, setDraft, unit }: { fields: [PlanningKey, string][]; draft: Draft; setDraft: (d: Draft) => void; unit?: string }) {
  return (
    <div className="grid grid-cols-2 gap-x-3 gap-y-2.5">
      {fields.map(([k, label]) => (
        <label key={k} className="flex flex-col gap-0.5 text-xs text-ink-2">
          {label}{unit ? ` (${unit})` : ""}
          <input inputMode="decimal" value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
            className="rounded-md border border-line-strong bg-surface px-2 py-1.5 text-right text-sm text-ink num" />
        </label>
      ))}
    </div>
  );
}

function PlanResultView({ r, label }: { r: PlanResult; label: string }) {
  const t = useChartTheme();
  const original = new Map(r.original.map((o) => [o.day, o]));
  const option = useMemo(() => ({
    animation: false,
    textStyle: { fontFamily: t.font },
    grid: { left: 44, right: 12, top: 28, bottom: 44 },
    tooltip: {
      trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.ink, fontFamily: t.font },
      formatter: (ps: { dataIndex: number }[]) => {
        const d = r.plan[ps[0].dataIndex];
        if (d.kind !== "training") return `<b>${fmtDate(d.date, true)}</b><br/>${ACTIVITY[d.kind].label}: not modelled`;
        const o = original.get(d.day);
        return `<b>${fmtDate(d.date, true)}</b><br/>Plan: ${fmt(d.duration)} min → MIP <b>${fmt(d.mip1, 2)}</b>`
          + (o ? `<br/>Your original: ${fmt(o.duration)} min → MIP ${fmt(o.mip1, 2)}` : "");
      },
    },
    xAxis: { type: "category", data: r.plan.map((d) => `${fmtDate(d.date, true).split(" ")[0]}\n${shortDate(d.date)}`),
      axisTick: { show: false }, axisLine: { lineStyle: { color: t.lineStrong } }, axisLabel: { color: t.muted, lineHeight: 14 } },
    yAxis: { type: "value", name: "Predicted MIP 1min", nameTextStyle: { color: t.muted, align: "left" }, splitNumber: 4,
      splitLine: { lineStyle: { color: t.line } }, axisLabel: { color: t.muted } },
    series: [
      { name: "Original plan", type: "bar", barMaxWidth: 16, barGap: "25%",
        itemStyle: { color: "transparent", borderColor: t.ink2, borderWidth: 1.5, borderType: "dashed", borderRadius: [3, 3, 0, 0] },
        data: r.plan.map((d) => (d.kind === "training" ? original.get(d.day)?.mip1 ?? null : null)) },
      { name: "Optimised plan", type: "bar", barMaxWidth: 16, itemStyle: { color: t.training, borderRadius: [3, 3, 0, 0] },
        data: r.plan.map((d) => (d.kind === "training" ? d.mip1 : null)) },
    ],
  }), [r, t]);  // eslint-disable-line react-hooks/exhaustive-deps

  const downloadCsv = () => {
    const cols = ["date", "kind", "team", "extra", "duration", "mip1", "movement_load", "training_trimp"] as const;
    const csv = [cols.join(","), ...r.plan.map((d) => cols.map((c) => d[c] ?? "").join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `loadwise_plan_${label.replace(/\W+/g, "_")}_${r.start}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <Panel title={`Plan for ${label}, ${fmtDate(r.plan[0].date)} to ${fmtDate(r.plan[6].date)}`}
      aside={<Button onClick={downloadCsv}><Download size={15} />CSV</Button>}>
      {r.pooled && <p className="mb-3 rounded-md bg-warning/10 px-3 py-2 text-sm">Squad models were used (not personalised): {r.reason}</p>}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Kpi label={r.objective === "terminal" ? "MIP on the last day" : "Total training-day MIP"}
          value={fmt(r.objective === "terminal" ? r.day7_mip : r.mip_sum, 2)} />
        <Kpi label="Total training-day MIP" value={fmt(r.mip_sum, 2)} hidden={r.objective !== "terminal"} />
        <Kpi label="Weekly Movement Load" value={fmt(r.weekly_ml)} note={`${fmt(r.ml_margin)} under the limit`} />
        <Kpi label="Weekly TRIMP" value={fmt(r.weekly_trimp)} note={`${fmt(r.trimp_margin)} under the limit`} />
      </dl>

      <div className="mt-4">
        <Legend items={[
          { label: "Original plan", swatch: <span aria-hidden className="inline-block h-3 w-3 rounded-[3px] border-[1.5px] border-dashed border-ink-2" /> },
          { label: "Optimised plan", swatch: <span aria-hidden className="inline-block h-3 w-3 rounded-[3px] bg-training" /> },
        ]} />
        <ReactECharts option={option} notMerge style={{ height: 240 }} />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-sm num">
          <thead className="border-b border-line text-left text-ink-2">
            <tr>
              <th className="py-1.5 font-medium">Day</th><th className="py-1.5 font-medium">Activity</th>
              <th className="py-1.5 text-right font-medium">Team (min)</th><th className="py-1.5 text-right font-medium">Individual (min)</th>
              <th className="py-1.5 text-right font-medium">Recorded (min)</th><th className="py-1.5 text-right font-medium">MIP 1min</th>
              <th className="py-1.5 text-right font-medium">Movement Load</th><th className="py-1.5 text-right font-medium">TRIMP</th>
            </tr>
          </thead>
          <tbody>
            {r.plan.map((d) => {
              const o = original.get(d.day), train = d.kind === "training";
              const was = (a: number | null | undefined, b: number | null | undefined, digits = 0) =>
                train && o && a !== b ? <span className="block text-xs text-muted">was {fmt(b, digits)}</span> : null;
              return (
                <tr key={d.day} className="border-b border-line/70 align-top">
                  <td className="py-1.5">{fmtDate(d.date, true).replace(/ \d{4}$/, "")}</td>
                  <td className="py-1.5">{ACTIVITY[d.kind].label}</td>
                  <td className="py-1.5 text-right">{train ? fmt(d.team) : "—"}{was(d.team, o?.team)}</td>
                  <td className="py-1.5 text-right">{train ? fmt(d.extra) : "—"}{was(d.extra, o?.extra)}</td>
                  <td className="py-1.5 text-right">{fmt(d.duration)}{was(d.duration, o?.duration)}</td>
                  <td className="py-1.5 text-right font-semibold">{fmt(d.mip1, 2)}{was(d.mip1, o?.mip1, 2)}</td>
                  <td className="py-1.5 text-right">{fmt(d.movement_load)}</td>
                  <td className="py-1.5 text-right">{fmt(d.training_trimp)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {r.alternative && (
        <p className="mt-3 text-sm text-ink-2">
          Cross-check with the duration-only spline model: its plan reaches {r.objective === "terminal" ? `last-day MIP ${fmt(r.alternative.day7_mip, 2)}` : `total MIP ${fmt(r.alternative.mip_sum, 2)}`},
          {" "}Movement Load {fmt(r.alternative.weekly_ml)}, TRIMP {fmt(r.alternative.weekly_trimp)}.
        </p>
      )}
      <p className="mt-2 max-w-[80ch] text-xs text-ink-2">{r.explanation} {r.limitation}</p>
    </Panel>
  );
}

function Kpi({ label, value, note, hidden }: { label: string; value: string; note?: string; hidden?: boolean }) {
  if (hidden) return null;
  return (
    <div>
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className="text-2xl font-bold num">{value}</dd>
      {note && <dd className="text-xs text-ink-2">{note}</dd>}
    </div>
  );
}

function HistoryPanel({ h }: { h: PlanHistory }) {
  const t = useChartTheme();
  const recent = h.history.slice(-30);
  const option = useMemo(() => ({
    textStyle: { fontFamily: t.font },
    grid: { left: 40, right: 12, top: 16, bottom: 28 },
    tooltip: {
      trigger: "axis", backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.ink, fontFamily: t.font },
      formatter: (ps: { dataIndex: number }[]) => {
        const d = recent[ps[0].dataIndex];
        return `<b>${fmtDate(d.date, true)}</b><br/>MIP 1min: <b>${fmt(d.mip1, 2)}</b><br/>Training: ${fmt(d.recorded_duration_min)} min · TRIMP ${fmt(d.training_trimp)} · Movement Load ${fmt(d.movement_load)}`;
      },
    },
    xAxis: { type: "category", data: recent.map((d) => shortDate(d.date)), axisTick: { show: false },
      axisLine: { lineStyle: { color: t.lineStrong } }, axisLabel: { color: t.muted } },
    yAxis: { type: "value", scale: true, splitNumber: 3, splitLine: { lineStyle: { color: t.line } }, axisLabel: { color: t.muted } },
    series: [{ name: "MIP 1min", type: "line", connectNulls: false, symbol: "circle", symbolSize: 8,
      itemStyle: { color: t.training, borderColor: t.surface, borderWidth: 2 }, lineStyle: { width: 2, color: t.training },
      data: recent.map((d) => d.mip1) }],
  }), [h, t]);  // eslint-disable-line react-hooks/exhaustive-deps

  const f = h.features;
  return (
    <Panel title="Recent history behind this plan">
      <p className="mb-1 text-sm text-ink-2">MIP 1min on the athlete’s last {recent.length} training days before the plan, with some of the history figures the predictions are based on. Days without training are skipped, not counted as zero.</p>
      {recent.length ? <ReactECharts option={option} notMerge style={{ height: 180 }} /> : <p className="py-4 text-ink-2">No training days before this date.</p>}
      {f && (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
          <Fact label="Last MIP 1min" value={`${fmt(f.last_mip1, 2)}`} note={`${fmt(f.days_since_mip1)} days before`} />
          <Fact label="MIP, 28-day mean" value={fmt(f.mip1_mean_28d, 2)} note={`${fmt(f.mip1_days_28d)} measured days`} />
          <Fact label="Training TRIMP, last 7 days" value={fmt(f.training_trimp_sum_7d)} note={`${fmt(f.training_days_7d)} training days`} />
          <Fact label="Games, last 7 days" value={fmt(f.reported_game_days_7d)} note={`Movement Load 7 days: ${fmt(f.movement_load_sum_7d)}`} />
        </dl>
      )}
    </Panel>
  );
}

function Fact({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-ink-2">{label}</dt>
      <dd className="text-lg font-semibold num">{value}</dd>
      {note && <dd className="text-xs text-ink-2">{note}</dd>}
    </div>
  );
}

function ModelEvidencePanel() {
  const ev = useQuery({ queryKey: ["plan-models"], queryFn: api.planModels });
  const [target, setTarget] = useState("mip1");
  const rows = useMemo(() => (ev.data?.comparison ?? []).filter((c) => c.target === target), [ev.data, target]);
  const imp = useMemo(() => (ev.data?.importance ?? []).filter((c) => c.target === target).sort((a, b) => b.mean_delta_rmse - a.mean_delta_rmse), [ev.data, target]);
  const maxImp = Math.max(...imp.map((i) => i.mean_delta_rmse), 1e-9);
  return (
    <Panel className="mt-5" title="How accurate are the models?"
      aside={<Segmented label="Prediction" value={target} onChange={setTarget}
        options={Object.entries(TARGET_LABEL).map(([value, label]) => ({ value, label }))} />}>
      {ev.error ? <ErrorNote error={ev.error} /> : !ev.data ? <Loading /> : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm num">
              <thead className="border-b border-line text-left text-ink-2">
                <tr><th className="py-1.5 font-medium">Inputs</th><th className="py-1.5 font-medium">Model</th>
                  <th className="py-1.5 text-right font-medium">Validation RMSE</th><th className="py-1.5 text-right font-medium">Test RMSE</th><th className="py-1.5 text-right font-medium">Test R²</th></tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.specification + c.model} className={`border-b border-line/70 ${c.selected ? "font-semibold" : "text-ink-2"}`}>
                    <td className="py-1.5">{SPEC_LABEL[c.specification] ?? c.specification}</td>
                    <td className="py-1.5">{c.model}{c.selected && <span className="ml-1.5 rounded bg-training/15 px-1.5 text-xs text-ink">used</span>}</td>
                    <td className="py-1.5 text-right">{fmt(c.val_rmse, 2)}</td><td className="py-1.5 text-right">{fmt(c.test_rmse, 2)}</td><td className="py-1.5 text-right">{fmt(c.test_r2, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-ink-2">
              Each model family was tuned on the training period and the one with the lowest validation error was kept (“used”).
              Test figures are from the held-out last weeks of the season ({rows[0]?.test_n ?? "—"} athlete-days). Lower RMSE is better.
            </p>
          </div>
          <div>
            <p className="mb-2 text-sm font-semibold">What drives the {TARGET_LABEL[target]} prediction</p>
            <ul className="space-y-1.5 text-sm">
              {imp.map((i) => (
                <li key={i.group}>
                  <div className="flex justify-between gap-2"><span>{i.group}</span><span className="text-ink-2 num">{i.mean_delta_rmse >= 0 ? "+" : ""}{fmt(i.mean_delta_rmse, Math.abs(i.mean_delta_rmse) < 1 ? 3 : 1)}</span></div>
                  <div className="mt-0.5 h-1.5 rounded-full bg-surface-2"><div className="h-1.5 rounded-full bg-training" style={{ width: `${Math.max(0, i.mean_delta_rmse) / maxImp * 100}%` }} /></div>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-ink-2">Increase in validation error when that group of inputs is shuffled. This shows what the model relies on, not cause and effect.</p>
          </div>
        </div>
      )}
    </Panel>
  );
}
