import { useEffect, useMemo, useState, type ReactNode } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, PencilLine, XCircle } from "lucide-react";
import {
  api, type Activity, type Decision, type EditedDay, type EvaluatedPlan, type FeedbackIn, type FeedbackRecord,
  type PlanConfig, type PlanDay, type PlanResult,
} from "../api";
import { ACTIVITY } from "../activity";
import { fmt, fmtDate } from "../format";
import { Button, ErrorNote, Panel } from "./ui";

type Mode = "choose" | "accept" | "reject" | "modify";

const SCALES = {
  accept: {
    question: "How good is this plan?",
    low: "Acceptable, but needs improvement",
    high: "Excellent — I would definitely use this",
    direction: "Higher means a better plan.",
  },
  reject: {
    question: "How strongly do you reject this plan?",
    low: "Not quite suitable — minor changes needed",
    high: "Completely unsuitable — I would never use this",
    direction: "Higher means a stronger rejection.",
  },
} as const;

const BADGE: Record<Decision, { label: string; icon: typeof CheckCircle2; cls: string }> = {
  accepted: { label: "Accepted", icon: CheckCircle2, cls: "bg-good/15 text-ink" },
  rejected: { label: "Rejected", icon: XCircle, cls: "bg-critical/10 text-critical" },
  modified: { label: "Modified and accepted", icon: PencilLine, cls: "bg-training/15 text-ink" },
};

export function DecisionBadge({ decision, size = "sm" }: { decision: Decision; size?: "sm" | "lg" }) {
  const b = BADGE[decision], Icon = b.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${b.cls} ${size === "lg" ? "px-3 py-1 text-base" : "px-2.5 py-0.5 text-sm"}`}>
      <Icon size={size === "lg" ? 18 : 14} aria-hidden />{b.label}
    </span>
  );
}

/** The rating always travels with its own scale: the two scales point in opposite directions. */
export function ratingText(r: Pick<FeedbackRecord, "rating" | "rating_scale">): string | null {
  if (r.rating == null || !r.rating_scale) return null;
  return r.rating_scale === "acceptance"
    ? `${r.rating}/5 on the acceptance scale (5 = excellent)`
    : `${r.rating}/5 on the rejection scale (5 = completely unsuitable)`;
}

export const fmtWhen = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

const dayName = (iso: string) => fmtDate(iso, true).replace(/ \d{4}$/, "");

function describeDay(d: { kind: Activity; team: number | null; extra: number | null }) {
  return d.kind === "training" ? `Training, ${fmt(d.team)} + ${fmt(d.extra)} min` : ACTIVITY[d.kind].label;
}

const textareaCls = "w-full rounded-md border border-line-strong bg-surface px-2.5 py-2 text-sm text-ink";

function Comment({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="mt-4 flex flex-col gap-1 text-sm text-ink-2">
      <span>{label} <span className="text-muted">(optional)</span></span>
      <textarea rows={3} maxLength={2000} value={value} onChange={(e) => onChange(e.target.value)} className={textareaCls} />
    </label>
  );
}

// ------------------------------------------------------------------ entry --

export function PlanFeedback({ config, proposal, saved, onSaved }: {
  config: PlanConfig; proposal: PlanResult; saved: FeedbackRecord | null; onSaved: (r: FeedbackRecord) => void;
}) {
  const [mode, setMode] = useState<Mode>("choose");
  const save = useMutation({ mutationFn: api.planFeedbackCreate, onSuccess: onSaved });
  // A new proposal starts a fresh decision.
  useEffect(() => { setMode("choose"); save.reset(); }, [proposal]); // eslint-disable-line react-hooks/exhaustive-deps

  if (saved) return <Outcome rec={saved} />;
  const submit = (body: Omit<FeedbackIn, "config" | "proposal">) => save.mutate({ config, proposal, ...body });
  const back = () => { setMode("choose"); save.reset(); };

  return (
    <Panel title="Coach decision" aside={mode !== "choose" && <Button variant="ghost" onClick={back}>Back to options</Button>}>
      {mode === "choose" && <Chooser onPick={setMode} />}
      {(mode === "accept" || mode === "reject") && (
        <RateForm tone={mode} pending={save.isPending}
          onSubmit={(rating, comment) => submit({ decision: mode === "accept" ? "accepted" : "rejected", rating, comment })} />
      )}
      {mode === "modify" && (
        <ModifyEditor config={config} proposal={proposal} pending={save.isPending}
          onSubmit={(days, comment) => submit({ decision: "modified", modified: { days }, comment })} />
      )}
      {save.error && <div className="mt-3"><ErrorNote error={save.error} /></div>}
    </Panel>
  );
}

function Chooser({ onPick }: { onPick: (m: Mode) => void }) {
  const options: { mode: Mode; icon: typeof CheckCircle2; title: string; note: string; cls: string }[] = [
    { mode: "accept", icon: CheckCircle2, title: "Accept", note: "Use the plan as proposed", cls: "hover:border-good text-good" },
    { mode: "modify", icon: PencilLine, title: "Modify", note: "Adjust days, then use it", cls: "hover:border-training text-training" },
    { mode: "reject", icon: XCircle, title: "Reject", note: "Don’t use this plan", cls: "hover:border-critical text-critical" },
  ];
  return (
    <>
      <p className="mb-3 text-sm text-ink-2">Would you use this plan? Your decision is saved for evaluating the models later. It does not change the models.</p>
      <div className="grid gap-2 sm:grid-cols-3">
        {options.map((o) => (
          <button key={o.mode} type="button" onClick={() => onPick(o.mode)}
            className={`group flex items-center gap-3 rounded-lg border border-line-strong bg-surface px-3.5 py-3 text-left transition-colors hover:bg-surface-2 ${o.cls}`}>
            <o.icon size={22} aria-hidden />
            <span>
              <span className="block text-[15px] font-semibold text-ink">{o.title}</span>
              <span className="block text-xs text-ink-2">{o.note}</span>
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

// ------------------------------------------------------- accept / reject --

function RatingScale({ tone, value, onChange }: { tone: "accept" | "reject"; value: number | null; onChange: (n: number) => void }) {
  const s = SCALES[tone];
  const sel = tone === "accept" ? "border-good bg-good/15 text-ink" : "border-critical bg-critical/10 text-critical";
  return (
    <fieldset>
      <legend className="text-[17px] font-semibold">{s.question}</legend>
      <p className="text-sm text-ink-2">Rate from 1 to 5. {s.direction}</p>
      <div role="radiogroup" aria-label={s.question} className="mt-2.5 grid max-w-lg grid-cols-5 gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" role="radio" aria-checked={value === n} onClick={() => onChange(n)}
            aria-label={`${n}${n === 1 ? `: ${s.low}` : n === 5 ? `: ${s.high}` : ""}`}
            className={`rounded-md border py-2 text-lg font-bold num transition-colors ${value === n ? sel : "border-line-strong bg-surface hover:bg-surface-2"}`}>
            {n}
          </button>
        ))}
      </div>
      <div className="mt-1.5 flex max-w-lg justify-between gap-6 text-xs text-ink-2">
        <span><b className="text-ink">1</b> = {s.low}</span>
        <span className="text-right"><b className="text-ink">5</b> = {s.high}</span>
      </div>
    </fieldset>
  );
}

function RateForm({ tone, pending, onSubmit }: { tone: "accept" | "reject"; pending: boolean; onSubmit: (rating: number, comment: string) => void }) {
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [confirming, setConfirming] = useState(false);
  const accept = tone === "accept";
  return (
    <div className={`border-l-4 pl-4 ${accept ? "border-good" : "border-critical"}`}>
      <p className={`mb-3 inline-flex items-center gap-1.5 text-sm font-semibold ${accept ? "text-good" : "text-critical"}`}>
        {accept ? <CheckCircle2 size={16} aria-hidden /> : <XCircle size={16} aria-hidden />}
        {accept ? "Accepting the plan" : "Rejecting the plan"}
      </p>
      <RatingScale tone={tone} value={rating} onChange={(n) => { setRating(n); setConfirming(false); }} />
      <Comment value={comment} onChange={setComment} label={accept ? "Comment" : "Why are you rejecting it?"} />
      {!confirming ? (
        <Button variant="primary" className="mt-4" disabled={rating == null} onClick={() => setConfirming(true)}>Continue</Button>
      ) : (
        <div className="mt-4 rounded-md border border-line-strong bg-surface-2 px-3.5 py-3">
          <p className="text-sm">
            {accept ? "Accept" : "Reject"} this plan with <b>{ratingText({ rating, rating_scale: accept ? "acceptance" : "rejection" })}</b>?
          </p>
          <div className="mt-2.5 flex gap-2">
            <Button variant={accept ? "primary" : "danger"} disabled={pending} onClick={() => onSubmit(rating!, comment)}>
              {pending ? "Saving…" : accept ? "Confirm acceptance" : "Confirm rejection"}
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)} disabled={pending}>Back</Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- modify --

type Row = { kind: Activity; team: string; extra: string };
const WHOLE = /^\d+$/;

function toEdited(rows: Row[]): EditedDay[] | string {
  const out: EditedDay[] = [];
  for (const [i, r] of rows.entries()) {
    if (r.kind !== "training") { out.push({ day: i + 1, kind: r.kind, team: 0, extra: 0 }); continue; }
    if (!WHOLE.test(r.team.trim()) || !WHOLE.test(r.extra.trim()) || Number(r.team) > 1440 || Number(r.extra) > 1440)
      return `Day ${i + 1}: enter whole minutes from 0 to 1440.`;
    out.push({ day: i + 1, kind: "training", team: Number(r.team), extra: Number(r.extra) });
  }
  return out;
}

const sameDay = (a: EditedDay, p: PlanDay) =>
  a.kind === p.kind && (a.kind !== "training" || (a.team === p.team && a.extra === p.extra));

function ModifyEditor({ config, proposal, pending, onSubmit }: {
  config: PlanConfig; proposal: PlanResult; pending: boolean; onSubmit: (days: EditedDay[], comment: string) => void;
}) {
  const initial = useMemo<Row[]>(() => proposal.plan.map((d) => ({ kind: d.kind, team: String(d.team ?? 0), extra: String(d.extra ?? 0) })), [proposal]);
  const [rows, setRows] = useState<Row[]>(initial);
  const [stage, setStage] = useState<"edit" | "review">("edit");
  const [comment, setComment] = useState("");

  const parsed = toEdited(rows);
  const key = typeof parsed === "string" ? null : JSON.stringify(parsed);
  const [debounced, setDebounced] = useState(key);
  useEffect(() => { const t = setTimeout(() => setDebounced(key), 350); return () => clearTimeout(t); }, [key]);
  const ev = useQuery({
    queryKey: ["plan-evaluate", config.athlete, config.start, debounced],
    queryFn: () => api.planEvaluate(config, JSON.parse(debounced!)),
    enabled: debounced != null, placeholderData: keepPreviousData, retry: false,
  });
  const updating = key !== debounced || ev.isFetching;
  const changed = typeof parsed === "string" ? [] : parsed.filter((d, i) => !sameDay(d, proposal.plan[i]));

  const setRow = (i: number, patch: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const setKind = (i: number, kind: Activity) => {
    // A day switched to training starts from the coach's planned minutes.
    if (kind === "training" && rows[i].kind !== "training") {
      const p = proposal.plan[i].kind === "training" ? proposal.plan[i] : null;
      setRow(i, { kind, team: String(p?.team ?? config.planning.original_team), extra: String(p?.extra ?? config.planning.original_extra) });
    } else setRow(i, { kind });
  };

  if (stage === "review" && typeof parsed !== "string") {
    return (
      <ReviewChanges proposal={proposal} edited={parsed} ev={ev.data} evError={ev.error} updating={updating}
        comment={comment} setComment={setComment} pending={pending}
        onBack={() => setStage("edit")} onSave={() => onSubmit(parsed, comment)} />
    );
  }

  const other = config.planning.other_recorded;
  return (
    <div>
      <p className="mb-3 text-sm text-ink-2">
        Change any day’s activity or minutes. Predictions update as you edit, using the same models (nothing is re-optimised).
        Recorded time adds {fmt(other)} min of other monitored time on training days.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm num">
          <thead className="border-b border-line text-left text-ink-2">
            <tr>
              <th className="py-1.5 font-medium">Day</th><th className="py-1.5 font-medium">Activity</th>
              <th className="py-1.5 text-right font-medium">Team (min)</th><th className="py-1.5 text-right font-medium">Individual (min)</th>
              <th className="py-1.5 text-right font-medium">Recorded</th><th className="py-1.5 text-right font-medium">MIP 1min</th>
              <th className="py-1.5 text-right font-medium">Movement Load</th><th className="py-1.5 text-right font-medium">TRIMP</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const p = proposal.plan[i], e = ev.data?.plan[i], train = r.kind === "training";
              const dirty = typeof parsed !== "string" && !sameDay(parsed[i], p);
              const field = (k: "team" | "extra") => {
                const changedField = train && (p.kind !== "training" || r[k] !== String(p[k]));
                return (
                  <input aria-label={`${dayName(p.date)} ${k === "team" ? "team" : "individual"} minutes`} inputMode="numeric" disabled={!train}
                    value={train ? r[k] : "—"} onChange={(ev) => setRow(i, { [k]: ev.target.value })}
                    className={`w-20 rounded-md border bg-surface px-2 py-1 text-right text-sm text-ink num disabled:opacity-40 ${changedField ? "border-training ring-1 ring-training/40" : "border-line-strong"}`} />
                );
              };
              const was = (v: number | null | undefined, o: number | null | undefined, digits = 0) =>
                dirty && fmt(v, digits) !== fmt(o, digits) ? <span className="block text-xs text-muted">was {fmt(o, digits)}</span> : null;
              return (
                <tr key={i} className={`border-b border-line/70 align-top ${dirty ? "bg-training/5" : ""}`}>
                  <td className="py-1.5 pr-2">
                    {dayName(p.date)}
                    {dirty && <span className="ml-1.5 rounded bg-training/15 px-1 text-[11px] font-semibold">edited</span>}
                  </td>
                  <td className="py-1.5 pr-2">
                    <select aria-label={`${dayName(p.date)} activity`} value={r.kind} onChange={(ev) => setKind(i, ev.target.value as Activity)}
                      className={`rounded-md border bg-surface px-2 py-1 text-sm text-ink ${r.kind !== p.kind ? "border-training ring-1 ring-training/40" : "border-line-strong"}`}>
                      {(Object.keys(ACTIVITY) as Activity[]).map((k) => <option key={k} value={k}>{ACTIVITY[k].label}</option>)}
                    </select>
                  </td>
                  <td className="py-1.5 text-right">{field("team")}</td>
                  <td className="py-1.5 text-right">{field("extra")}</td>
                  <td className="py-1.5 text-right">{train && WHOLE.test(r.team) && WHOLE.test(r.extra) ? fmt(Number(r.team) + Number(r.extra) + other) : "—"}</td>
                  <td className="py-1.5 text-right font-semibold">
                    {e && e.kind === "training" && e.supported === false ? <span className="text-xs font-normal text-[#b07800] dark:text-warning">No prediction</span> : fmt(e?.mip1, 2)}
                    {was(e?.mip1, p.mip1, 2)}
                  </td>
                  <td className="py-1.5 text-right">{fmt(e?.movement_load)}{was(e?.movement_load, p.movement_load)}</td>
                  <td className="py-1.5 text-right">{fmt(e?.training_trimp)}{was(e?.training_trimp, p.training_trimp)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {typeof parsed === "string" ? <div className="mt-3"><ErrorNote error={parsed} /></div>
        : ev.error ? <div className="mt-3"><ErrorNote error={ev.error} /></div>
        : ev.data && <WeekSummary ev={ev.data} proposal={proposal} config={config} updating={updating} />}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={typeof parsed === "string" || !changed.length} onClick={() => setStage("review")}>
          Review changes <ArrowRight size={15} />
        </Button>
        <Button variant="ghost" disabled={!changed.length} onClick={() => setRows(initial)}>Undo all edits</Button>
        <span className="text-sm text-ink-2">
          {changed.length ? `${changed.length} day${changed.length > 1 ? "s" : ""} changed` : "No changes yet. To use the plan as it is, choose Accept."}
        </span>
      </div>
    </div>
  );
}

function Warnings({ ev }: { ev: EvaluatedPlan }) {
  if (!ev.warnings.length) return null;
  return (
    <ul className="mt-2.5 flex flex-wrap gap-1.5">
      {ev.warnings.map((w) => (
        <li key={w.code + w.day} className="inline-flex items-center gap-1 rounded-full bg-warning/20 px-2.5 py-0.5 text-xs text-ink">
          <AlertTriangle size={12} aria-hidden className="text-[#b07800] dark:text-warning" />{w.message}
        </li>
      ))}
    </ul>
  );
}

function WeekSummary({ ev, proposal, config, updating }: { ev: EvaluatedPlan; proposal: PlanResult; config: PlanConfig; updating: boolean }) {
  const lim = config.planning;
  return (
    <div className={`mt-3 rounded-md bg-surface-2 px-3.5 py-3 transition-opacity ${updating ? "opacity-60" : ""}`}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <Stat label="MIP on the last day" value={fmt(ev.day7_mip, 2)} was={fmt(proposal.day7_mip, 2)} />
        <Stat label="Total training-day MIP" value={fmt(ev.mip_sum, 2)} was={fmt(proposal.mip_sum, 2)} />
        <Stat label="Weekly Movement Load" value={`${fmt(ev.weekly_ml)} / ${fmt(lim.weekly_ml_limit)}`} was={fmt(proposal.weekly_ml)} warn={ev.ml_margin < 0} />
        <Stat label="Weekly TRIMP" value={`${fmt(ev.weekly_trimp)} / ${fmt(lim.weekly_trimp_limit)}`} was={fmt(proposal.weekly_trimp)} warn={ev.trimp_margin < 0} />
      </dl>
      <Warnings ev={ev} />
      <p className="mt-2 text-xs text-ink-2">
        {updating ? "Updating predictions…" : "Limit checks are shown as warnings only. You can still save the plan."}
      </p>
    </div>
  );
}

function Stat({ label, value, was, warn }: { label: string; value: string; was?: string; warn?: boolean }) {
  return (
    <div>
      <dt className="text-ink-2">{label}</dt>
      <dd className={`text-lg font-semibold num ${warn ? "text-[#b07800] dark:text-warning" : ""}`}>{value}</dd>
      {was !== undefined && <dd className="text-xs text-muted num">proposed {was}</dd>}
    </div>
  );
}

function ReviewChanges({ proposal, edited, ev, evError, updating, comment, setComment, pending, onBack, onSave }: {
  proposal: PlanResult; edited: EditedDay[]; ev: EvaluatedPlan | undefined; evError: unknown; updating: boolean;
  comment: string; setComment: (v: string) => void; pending: boolean; onBack: () => void; onSave: () => void;
}) {
  const changed = edited.map((d, i) => ({ d, p: proposal.plan[i], e: ev?.plan[i] })).filter(({ d, p }) => !sameDay(d, p));
  return (
    <div>
      <p className="text-[17px] font-semibold">Review your changes</p>
      <p className="mb-3 text-sm text-ink-2">The original proposal is kept alongside your version.</p>
      <ul className="divide-y divide-line rounded-md border border-line">
        {changed.map(({ d, p, e }) => (
          <li key={d.day} className="grid gap-1 px-3.5 py-2.5 text-sm sm:grid-cols-[150px_minmax(0,1fr)]">
            <span className="font-semibold">{dayName(p.date)}</span>
            <span className="flex flex-wrap items-center gap-x-2 num">
              <span className="text-ink-2 line-through decoration-muted">{describeDay(p)}</span>
              <ArrowRight size={14} aria-hidden className="text-muted" />
              <span className="font-semibold">{describeDay(d)}</span>
              {(p.mip1 != null || e?.mip1 != null) && <span className="text-xs text-ink-2">· MIP {fmt(p.mip1, 2)} → {fmt(e?.mip1, 2)}</span>}
            </span>
          </li>
        ))}
      </ul>
      {evError ? <div className="mt-3"><ErrorNote error={evError} /></div> : ev && (
        <div className="mt-3 text-sm">
          <p className="num">
            Week: Movement Load {fmt(proposal.weekly_ml)} → <b>{fmt(ev.weekly_ml)}</b>, TRIMP {fmt(proposal.weekly_trimp)} → <b>{fmt(ev.weekly_trimp)}</b>,
            {" "}last-day MIP {fmt(proposal.day7_mip, 2)} → <b>{fmt(ev.day7_mip, 2)}</b>.
          </p>
          <Warnings ev={ev} />
        </div>
      )}
      <Comment value={comment} onChange={setComment} label="What did you change, and why?" />
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="primary" disabled={pending || updating || !!evError} onClick={onSave}>
          <PencilLine size={15} />{pending ? "Saving…" : "Save as “Modified and accepted”"}
        </Button>
        <Button variant="ghost" onClick={onBack} disabled={pending}>Keep editing</Button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------- outcome --

function Outcome({ rec }: { rec: FeedbackRecord }) {
  const rating = ratingText(rec);
  const accent = rec.decision === "accepted" ? "border-good" : rec.decision === "rejected" ? "border-critical" : "border-training";
  const heading = rec.decision === "accepted" ? "You accepted this plan."
    : rec.decision === "rejected" ? "You rejected this plan." : "You modified and accepted this plan.";
  return (
    <Panel title="Coach decision" aside={<span className="text-sm text-ink-2">Saved {fmtWhen(rec.created_at)}</span>}>
      <div className={`border-l-4 pl-4 ${accent}`}>
        <div className="flex flex-wrap items-center gap-3">
          <DecisionBadge decision={rec.decision} size="lg" />
          <span className="text-[15px] font-semibold">{heading}</span>
        </div>
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_minmax(0,1fr)]">
          {rating && <Row label="Rating">{rating}</Row>}
          <Row label="Comment">{rec.comment ? <span className="whitespace-pre-wrap">{rec.comment}</span> : <span className="text-muted">No comment</span>}</Row>
          <Row label="Plan">{rec.athlete_label}, {fmtDate(rec.proposal.plan[0].date)} to {fmtDate(rec.proposal.plan[6].date)}</Row>
        </dl>
      </div>
      {rec.modified && <Comparison rec={rec} />}
      <p className="mt-3 text-xs text-ink-2">Stored for evaluating the models later. The models are not retrained or changed.</p>
    </Panel>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <><dt className="text-ink-2">{label}</dt><dd>{children}</dd></>;
}

function Comparison({ rec }: { rec: FeedbackRecord }) {
  const ev = rec.modified!.evaluation;
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[620px] text-sm num">
        <thead className="border-b border-line text-left text-ink-2">
          <tr>
            <th className="py-1.5 font-medium">Day</th><th className="py-1.5 font-medium">Proposed</th>
            <th className="py-1.5 font-medium">Coach’s plan</th><th className="py-1.5 text-right font-medium">MIP 1min</th>
            <th className="py-1.5 text-right font-medium">Movement Load</th><th className="py-1.5 text-right font-medium">TRIMP</th>
          </tr>
        </thead>
        <tbody>
          {ev.plan.map((d, i) => {
            const p = rec.proposal.plan[i], dirty = !sameDay(d, p);
            const pair = (a: number | null, b: number | null, digits = 0) =>
              dirty ? <><span className="text-muted">{fmt(b, digits)} → </span>{fmt(a, digits)}</> : fmt(a, digits);
            return (
              <tr key={d.day} className={`border-b border-line/70 ${dirty ? "bg-training/5" : ""}`}>
                <td className="py-1.5">{dayName(d.date)}</td>
                <td className={`py-1.5 ${dirty ? "text-ink-2" : ""}`}>{describeDay(p)}</td>
                <td className={`py-1.5 ${dirty ? "font-semibold" : "text-ink-2"}`}>{dirty ? describeDay(d) : "Unchanged"}</td>
                <td className="py-1.5 text-right">{pair(d.mip1, p.mip1, 2)}</td>
                <td className="py-1.5 text-right">{pair(d.movement_load, p.movement_load)}</td>
                <td className="py-1.5 text-right">{pair(d.training_trimp, p.training_trimp)}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot className="text-ink-2">
          <tr>
            <td className="pt-2" colSpan={3}>Week total</td>
            <td className="pt-2 text-right">{fmt(rec.proposal.mip_sum, 2)} → <b className="text-ink">{fmt(ev.mip_sum, 2)}</b></td>
            <td className="pt-2 text-right">{fmt(rec.proposal.weekly_ml)} → <b className="text-ink">{fmt(ev.weekly_ml)}</b></td>
            <td className="pt-2 text-right">{fmt(rec.proposal.weekly_trimp)} → <b className="text-ink">{fmt(ev.weekly_trimp)}</b></td>
          </tr>
        </tfoot>
      </table>
      {ev.warnings.length > 0 && <Warnings ev={ev} />}
    </div>
  );
}

// ------------------------------------------------------------------- log --

export function FeedbackLog({ athleteId, label, activeId, onOpen }: {
  athleteId: string; label: string; activeId: number | null; onOpen: (r: FeedbackRecord) => void;
}) {
  const q = useQuery({ queryKey: ["plan-feedback-list", athleteId], queryFn: () => api.planFeedbackList(athleteId), enabled: !!athleteId });
  return (
    <Panel title={`Coach feedback for ${label}`} pad={false}>
      {q.error ? <div className="p-4"><ErrorNote error={q.error} /></div>
        : !q.data ? <p className="p-4 text-sm text-ink-2">Loading…</p>
        : !q.data.length ? <p className="p-4 text-sm text-ink-2">No decisions saved yet. Create a plan, then accept, modify or reject it.</p>
        : (
          <ul className="divide-y divide-line">
            {q.data.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => onOpen(r)} aria-current={r.id === activeId}
                  className={`grid w-full gap-1 px-4 py-2.5 text-left text-sm hover:bg-surface-2 sm:grid-cols-[190px_170px_minmax(0,1fr)] sm:items-center ${r.id === activeId ? "bg-surface-2" : ""}`}>
                  <span><DecisionBadge decision={r.decision} /></span>
                  <span className="num">
                    Week of {fmtDate(r.start)}
                    <span className="block text-xs text-ink-2">{fmtWhen(r.created_at)}</span>
                  </span>
                  <span className="min-w-0">
                    {r.rating != null && <span className="block text-ink-2">{ratingText(r)}</span>}
                    <span className="block truncate text-ink-2">{r.comment ?? <span className="text-muted">No comment</span>}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
    </Panel>
  );
}
