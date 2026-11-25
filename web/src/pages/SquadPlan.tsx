import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, Navigate, useLocation } from "react-router-dom";
import { Download, Users, Zap } from "lucide-react";
import {
  api,
  type Activity,
  type SquadAthleteDefaults,
  type SquadAthleteInput,
  type SquadConfig,
  type SquadDayInput,
  type SquadDefaults,
  type SquadResult,
  type WorkloadLimits,
} from "../api";
import { fmt, fmtDate } from "../format";
import { Button, DateInput, ErrorNote, Loading, PageHeader, Panel, Select } from "../components/ui";

const LIMIT_FIELDS: [keyof WorkloadLimits, string][] = [
  ["trimp_limit", "Daily TRIMP limit"],
  ["ml_limit", "Daily Movement Load limit"],
  ["weekly_trimp_limit", "Weekly TRIMP limit"],
  ["weekly_ml_limit", "Weekly Movement Load limit"],
  ["trimp_buffer", "Daily TRIMP buffer"],
  ["ml_buffer", "Daily Movement Load buffer"],
];

interface NumberFieldProps {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  optional?: boolean;
  max?: number;
  whole?: boolean;
}

function NumberField({
  label,
  value,
  onChange,
  optional = false,
  max,
  whole = false,
}: NumberFieldProps) {
  function changeValue(text: string) {
    if (text === "") {
      onChange(optional ? null : NaN);
      return;
    }
    onChange(Number(text));
  }

  const displayedValue = value !== null && Number.isFinite(value) ? value : "";
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs text-ink-2">
      {label}
      <input
        type="number"
        min="0"
        max={max}
        step={whole ? 1 : "any"}
        required={!optional}
        value={displayedValue}
        placeholder={optional ? "No limit" : "Required"}
        onChange={(event) => changeValue(event.target.value)}
        className="w-full rounded-md border border-line-strong bg-surface px-2 py-1.5 text-right text-sm text-ink num"
      />
    </label>
  );
}

export function SquadPlanPage() {
  const location = useLocation();
  const meta = useQuery({ queryKey: ["plan-meta"], queryFn: api.planMeta, retry: false });
  const [chosenStart, setChosenStart] = useState("");
  const start = chosenStart || meta.data?.last_start || "";
  const defaults = useQuery({
    queryKey: ["squad-defaults", start],
    queryFn: () => api.squadDefaults(start),
    enabled: !!start,
    retry: false,
  });
  const oldLink = new URLSearchParams(location.search);
  if (oldLink.has("feedback") || oldLink.has("demo")) {
    return <Navigate to={`/plan/individual${location.search}`} replace />;
  }
  if (meta.isLoading) return <Loading what="Loading the squad planner" />;
  if (meta.error) return <ErrorNote error={meta.error} />;
  if (!meta.data?.roster.length)
    return <ErrorNote error="Load training data before planning the squad’s week." />;

  return (
    <>
      <PageHeader
        title="Squad training plan"
        sub="Set team practices once. Choose each athlete’s individual-training availability and workload limits, then build the squad’s seven-day plan."
        actions={
          <Link className="text-sm font-semibold underline" to="/plan/individual">
            Individual planner & saved feedback
          </Link>
        }
      />
      <div className="mb-5">
        <DateInput
          label="Week starts"
          value={start}
          min={meta.data.first_start ?? undefined}
          max={meta.data.last_start ?? undefined}
          onChange={setChosenStart}
        />
      </div>
      {defaults.error && <ErrorNote error={defaults.error} />}
      {!defaults.error && !defaults.data && <Loading what="Reading athlete histories" />}
      {!defaults.error && defaults.data && <SquadForm key={start} defaults={defaults.data} />}
    </>
  );
}

interface AthleteDraft extends SquadAthleteDefaults {
  selected: boolean;
}

function SquadForm({ defaults }: { defaults: SquadDefaults }) {
  const [days, setDays] = useState(defaults.days);
  const [athletes, setAthletes] = useState<AthleteDraft[]>(
    defaults.athletes.map((athlete) => ({ ...athlete, selected: true })),
  );
  const [objective, setObjective] = useState<SquadConfig["objective"]>("terminal");
  const [step, setStep] = useState<SquadConfig["step"]>(5);
  const run = useMutation({ mutationFn: api.squadOptimize });
  const selected = athletes.filter((athlete) => athlete.selected);
  const needsPermission = selected.some((athlete) => athlete.reason && !athlete.allow_pooled);
  const invalidFinalDay = objective === "terminal" && days[6].kind !== "training";

  function updateDay(index: number, changes: Partial<SquadDayInput>) {
    const updated = [...days];
    updated[index] = { ...updated[index], ...changes };
    setDays(updated);
    run.reset();
  }

  function updateAthlete(index: number, changes: Partial<AthleteDraft>) {
    const updated = [...athletes];
    updated[index] = { ...updated[index], ...changes };
    setAthletes(updated);
    run.reset();
  }

  function changeActivity(index: number, kind: Activity) {
    const team = kind === "training" ? 90 : 0;
    updateDay(index, { kind, team });
  }

  function selectAll(selected: boolean) {
    setAthletes(athletes.map((athlete) => ({ ...athlete, selected })));
    run.reset();
  }

  function changeAvailability(athleteIndex: number, dayIndex: number, minutes: number) {
    const availability = [...athletes[athleteIndex].availability];
    availability[dayIndex] = minutes;
    updateAthlete(athleteIndex, { availability });
  }

  function changeLimit(athleteIndex: number, name: keyof WorkloadLimits, value: number) {
    const limits = { ...athletes[athleteIndex].limits, [name]: value };
    updateAthlete(athleteIndex, { limits });
  }

  function changeObjective(value: string) {
    setObjective(value as SquadConfig["objective"]);
    run.reset();
  }

  function changeStep(value: string) {
    setStep(Number(value) as SquadConfig["step"]);
    run.reset();
  }

  function submit() {
    const inputs: SquadAthleteInput[] = [];
    for (const athlete of selected) {
      inputs.push({
        athlete: athlete.athlete,
        availability: athlete.availability,
        limits: athlete.limits,
        other_recorded: athlete.other_recorded,
        allow_pooled: athlete.allow_pooled,
      });
    }
    run.mutate({ start: defaults.start, days, objective, step, athletes: inputs });
  }

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <fieldset disabled={run.isPending} className="min-w-0 space-y-5">
          <Panel title="1. Fixed team schedule">
            <p className="mb-4 text-sm text-ink-2">
              Every selected athlete attends these team-practice minutes. Only individual work can
              change. Game and rest days receive no training assignment.
            </p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
              {days.map((day, i) => (
                <div key={i} className="space-y-3 rounded-md border border-line bg-surface-2 p-3">
                  <p className="font-semibold">
                    Day {i + 1}
                    <span className="block text-xs font-normal text-ink-2">
                      {fmtDate(defaults.week_dates[i], true)}
                    </span>
                  </p>
                  <Select
                    label={`Day ${i + 1} activity`}
                    value={day.kind}
                    onChange={(value) => changeActivity(i, value as Activity)}
                  >
                    <option value="training">Training</option>
                    <option value="game">Game</option>
                    <option value="rest">Rest</option>
                  </Select>
                  {day.kind === "training" ? (
                    <>
                      <NumberField
                        label="Fixed team min"
                        whole
                        max={1440}
                        value={day.team}
                        onChange={(value) => updateDay(i, { team: value! })}
                      />
                      <NumberField
                        label="Shared individual min cap"
                        optional
                        value={day.individual_limit}
                        onChange={(value) => updateDay(i, { individual_limit: value })}
                      />
                    </>
                  ) : (
                    <p className="text-xs text-ink-2">Training not modeled</p>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-ink-2">
              The optional shared cap limits the sum of all athletes’ individual minutes that day. Leave
              it blank when coaching capacity is unrestricted. Overlapping sessions need a separate
              scheduling model.
            </p>
          </Panel>

          <Panel
            title={`2. Athlete inputs · ${selected.length} selected`}
            aside={
              <div className="flex gap-3 text-sm">
                <button type="button" className="underline" onClick={() => selectAll(true)}>
                  Select all
                </button>
                <button type="button" className="underline" onClick={() => selectAll(false)}>
                  Clear
                </button>
              </div>
            }
          >
            <p className="mb-3 text-sm text-ink-2">
              Enter the maximum individual-training minutes available each day. LoadWise chooses between
              zero and that maximum. Workload limits stay separate for every athlete.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-ink-2">
                  <tr>
                    <th className="py-2 pr-4">Athlete</th>
                    {days.map((day, i) => (
                      <th key={i} className="min-w-20 px-1 py-2">
                        Day {i + 1}
                        <span className="block font-normal">{day.kind}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {athletes.map((athlete, i) => (
                    <tr key={athlete.athlete} className="border-t border-line">
                      <td className="py-3 pr-4">
                        <label className="flex items-center gap-2 whitespace-nowrap font-semibold">
                          <input
                            type="checkbox"
                            checked={athlete.selected}
                            onChange={(e) => updateAthlete(i, { selected: e.target.checked })}
                          />
                          {athlete.label}
                        </label>
                        <span className="text-xs text-ink-2">
                          {athlete.reason ? "Duration-only model needed" : "History + duration model"}
                        </span>
                      </td>
                      {days.map((day, d) => (
                        <td key={d} className="px-1 py-2">
                          {day.kind === "training" ? (
                            <fieldset disabled={!athlete.selected}>
                              <NumberField
                                label={`${athlete.label}, Day ${d + 1} max min`}
                                whole
                                max={1440}
                                value={athlete.availability[d]}
                                onChange={(value) => changeAvailability(i, d, value!)}
                              />
                            </fieldset>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details className="mt-4 border-t border-line pt-3" open={needsPermission || undefined}>
              <summary className="cursor-pointer font-semibold">
                Athlete workload limits & model settings
              </summary>
              <p className="my-3 text-xs text-ink-2">
                Defaults use historical percentiles: daily 90th percentile and weekly 5 × 75th
                percentile. Review them for this week; these are planning limits. Other monitored minutes
                are fixed per training day and are included in recorded duration.
              </p>
              <div className="grid gap-3 lg:grid-cols-2">
                {athletes.map(
                  (athlete, i) =>
                    athlete.selected && (
                      <fieldset
                        key={athlete.athlete}
                        className="min-w-0 rounded-md border border-line p-3"
                      >
                        <legend className="px-1 font-semibold">{athlete.label}</legend>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                          {LIMIT_FIELDS.map(([key, label]) => (
                            <NumberField
                              key={key}
                              label={label}
                              value={athlete.limits[key]}
                              onChange={(value) => changeLimit(i, key, value!)}
                            />
                          ))}
                          <NumberField
                            label="Other monitored min/day"
                            whole
                            max={1440}
                            value={athlete.other_recorded}
                            onChange={(value) => updateAthlete(i, { other_recorded: value! })}
                          />
                        </div>
                        {athlete.reason && (
                          <label className="mt-3 flex items-start gap-2 text-sm text-ink-2">
                            <input
                              className="mt-1"
                              type="checkbox"
                              checked={athlete.allow_pooled}
                              onChange={(e) => updateAthlete(i, { allow_pooled: e.target.checked })}
                            />
                            <span>
                              Allow duration-only predictions for this athlete. {athlete.reason}
                            </span>
                          </label>
                        )}
                      </fieldset>
                    ),
                )}
              </div>
            </details>
          </Panel>

          <Panel title="3. Team objective">
            <div className="flex flex-wrap items-end gap-4">
              <Select
                label="Maximize equal-weight squad MIP"
                value={objective}
                onChange={changeObjective}
              >
                <option value="terminal">Final training day (Day 7)</option>
                <option value="cumulative">Sum across the week’s training days</option>
              </Select>
              <Select label="Minute steps" value={String(step)} onChange={changeStep}>
                <option value="1">1 minute</option>
                <option value="5">5 minutes</option>
                <option value="10">10 minutes</option>
              </Select>
              <Button
                type="submit"
                variant="primary"
                disabled={!selected.length || needsPermission || invalidFinalDay}
              >
                <Zap size={16} />
                {run.isPending ? "Planning the squad…" : `Create ${selected.length} athlete plans`}
              </Button>
            </div>
            <p className="mt-3 text-sm text-ink-2">
              Each selected athlete has equal weight. The solver maximizes their combined predicted MIP;
              the team score shows the average per athlete. History stays fixed for all seven days.
            </p>
            {invalidFinalDay && (
              <p className="mt-2 text-sm text-critical">
                Set Day 7 to training or choose the whole-week objective.
              </p>
            )}
            {needsPermission && (
              <p className="mt-2 text-sm text-critical">
                Review duration-only model settings above, or deselect those athletes.
              </p>
            )}
            {defaults.in_fitting_period && (
              <p className="mt-2 text-xs text-ink-2">
                This week starts inside the models’ fitting period, so this is a replay using models
                fitted on that period.
              </p>
            )}
          </Panel>
        </fieldset>
      </form>
      {run.error && <ErrorNote error={run.error} />}
      {run.isPending && (
        <Loading what="Predicting candidate durations and solving all athlete plans together" />
      )}
      {run.data && <SquadResults result={run.data} />}
    </div>
  );
}

function downloadPlan(result: SquadResult) {
  const rows: (string | number | null)[][] = [
    [
      "athlete",
      "date",
      "activity",
      "team_minutes",
      "individual_minutes",
      "recorded_minutes",
      "mip1",
      "movement_load",
      "trimp",
    ],
  ];
  for (const athlete of result.athletes) {
    for (const day of athlete.summary.plan) {
      rows.push([
        athlete.athlete,
        day.date,
        day.kind,
        day.team,
        day.extra,
        day.duration,
        day.mip1,
        day.movement_load,
        day.training_trimp,
      ]);
    }
  }
  const csvRows = [];
  for (const row of rows) {
    const values = [];
    for (const value of row) {
      const text = String(value ?? "").replace(/"/g, '""');
      values.push(`"${text}"`);
    }
    csvRows.push(values.join(","));
  }
  const csv = csvRows.join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `loadwise_squad_${result.start}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

function SquadResults({ result }: { result: SquadResult }) {
  const finalDay = result.objective === "terminal";
  return (
    <div className="space-y-5">
      <Panel
        title="Squad plan"
        aside={
          <Button type="button" onClick={() => downloadPlan(result)}>
            <Download size={15} />
            All athlete plans · CSV
          </Button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-4">
          <div>
            <p className="text-xs text-ink-2">Selected athletes</p>
            <p className="text-3xl font-bold num">{result.athlete_count}</p>
          </div>
          <div>
            <p className="text-xs text-ink-2">
              {finalDay ? "Day 7 MIP · squad average" : "Weekly MIP sum · average per athlete"}
            </p>
            <p className="text-3xl font-bold num">{fmt(result.score.average, 2)}</p>
          </div>
          <div>
            <p className="text-xs text-ink-2">Team-only baseline · same objective</p>
            <p className="text-3xl font-bold num">{fmt(result.baseline.average, 2)}</p>
          </div>
          <div>
            <p className="text-xs text-ink-2">Change from team-only baseline</p>
            <p className="text-3xl font-bold num">
              {result.improvement !== null && result.improvement > 0 ? "+" : ""}
              {fmt(result.improvement, 2)}
            </p>
          </div>
        </div>
        <p className="mt-4 text-sm text-ink-2">{result.explanation}</p>
        {!result.baseline.feasible && (
          <p className="mt-2 text-sm text-ink-2">
            The team-only baseline is outside the model’s supported range or exceeds at least one
            athlete’s workload limits. Check the athlete details below before comparing scores.
          </p>
        )}
      </Panel>

      <Panel title="Individual training assignments · minutes" pad={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-ink-2">
              <tr>
                <th className="px-4 py-3">Athlete</th>
                {result.days.map((day) => (
                  <th key={day.day} className="px-3 py-3 text-right">
                    Day {day.day}
                    <span className="block font-normal">{fmtDate(day.date, true)}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-line bg-surface-2 font-semibold">
                <td className="px-4 py-3">Fixed team practice</td>
                {result.days.map((day) => (
                  <td key={day.day} className="px-3 py-3 text-right num">
                    {day.kind === "training" ? day.team : day.kind}
                  </td>
                ))}
              </tr>
              {result.athletes.map((athlete) => (
                <tr key={athlete.athlete_id} className="border-t border-line">
                  <td className="px-4 py-3 font-semibold">
                    {athlete.athlete}
                    {athlete.pooled && (
                      <span className="block text-xs font-normal text-ink-2">Duration-only</span>
                    )}
                  </td>
                  {athlete.summary.plan.map((day) => (
                    <td key={day.day} className="px-3 py-3 text-right num">
                      {day.kind === "training" ? day.extra : "—"}
                    </td>
                  ))}
                </tr>
              ))}
              <tr className="border-t border-line bg-surface-2 font-semibold">
                <td className="px-4 py-3">Total individual work</td>
                {result.days.map((day) => (
                  <td key={day.day} className="px-3 py-3 text-right num">
                    {day.kind === "training" ? day.individual_minutes : "—"}
                    {day.kind === "training" && day.individual_limit !== null && (
                      <span className="block text-xs font-normal text-ink-2">
                        cap {day.individual_limit}
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Team MIP by training day" pad={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-ink-2">
              <tr>
                <th className="px-4 py-2">Date</th>
                <th className="px-4 py-2">Activity</th>
                <th className="px-4 py-2 text-right">Squad average MIP</th>
                <th className="px-4 py-2 text-right">Sum of athlete MIP</th>
              </tr>
            </thead>
            <tbody>
              {result.days.map((day) => (
                <tr key={day.day} className="border-t border-line">
                  <td className="px-4 py-2">{fmtDate(day.date, true)}</td>
                  <td className="px-4 py-2 capitalize">{day.kind}</td>
                  <td className="px-4 py-2 text-right num">{fmt(day.mip_average, 2)}</td>
                  <td className="px-4 py-2 text-right num">{fmt(day.mip_total, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel
        title={
          <span className="flex items-center gap-2">
            <Users size={16} />
            Individual seven-day plans
          </span>
        }
      >
        <div className="space-y-3">
          {result.athletes.map((athlete) => (
            <details key={athlete.athlete_id} className="rounded-md border border-line p-3">
              <summary className="cursor-pointer font-semibold">
                {athlete.athlete} · {finalDay ? "Day 7 MIP" : "Weekly MIP sum"}{" "}
                {fmt(finalDay ? athlete.summary.day7_mip : athlete.summary.mip_sum, 2)}
              </summary>
              {athlete.pooled && (
                <p className="mt-2 text-xs text-ink-2">Duration-only predictions. {athlete.reason}</p>
              )}
              {athlete.baseline.reason && (
                <p className="mt-2 text-xs text-ink-2">Baseline: {athlete.baseline.reason}</p>
              )}
              <div className="mt-3 overflow-x-auto">
                <table className="w-full whitespace-nowrap text-sm">
                  <thead className="text-left text-xs text-ink-2">
                    <tr>
                      {[
                        "Date",
                        "Activity",
                        "Team min",
                        "Individual min",
                        "Recorded min",
                        "MIP",
                        "Movement Load",
                        "TRIMP",
                      ].map((label) => (
                        <th key={label} className="px-2 py-2">
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {athlete.summary.plan.map((day) => (
                      <tr key={day.day} className="border-t border-line">
                        <td className="px-2 py-2">{fmtDate(day.date, true)}</td>
                        <td className="px-2 py-2 capitalize">{day.kind}</td>
                        <td className="px-2 py-2 num">
                          {fmt(day.kind === "training" ? day.team : null)}
                        </td>
                        <td className="px-2 py-2 num">
                          {fmt(day.kind === "training" ? day.extra : null)}
                        </td>
                        <td className="px-2 py-2 num">{fmt(day.duration)}</td>
                        <td className="px-2 py-2 num">{fmt(day.mip1, 2)}</td>
                        <td className="px-2 py-2 num">{fmt(day.movement_load)}</td>
                        <td className="px-2 py-2 num">{fmt(day.training_trimp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs text-ink-2">
                Weekly predicted TRIMP {fmt(athlete.summary.weekly_trimp)} · remaining budget{" "}
                {fmt(athlete.summary.trimp_margin)}. Movement Load {fmt(athlete.summary.weekly_ml)} ·
                remaining budget {fmt(athlete.summary.ml_margin)}. Remaining budgets include the
                specified buffers.
              </p>
            </details>
          ))}
        </div>
        <p className="mt-4 text-xs text-ink-2">{result.limitation}</p>
      </Panel>
    </div>
  );
}
