import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertOctagon, AlertTriangle, Info } from "lucide-react";
import type { Completeness, MetricBlock, Severity } from "../api";
import { cssVar, fmt } from "../format";

type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-ink text-surface hover:opacity-90",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-surface-2",
  ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
  danger: "bg-surface text-critical border border-line-strong hover:bg-surface-2",
};

export function Button({ variant = "secondary", className = "", ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...p}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
    />
  );
}

export function Panel({ title, aside, children, className = "", pad = true }:
  { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`rounded-lg border border-line bg-surface ${className}`}>
      {(title || aside) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {aside}
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[28px] font-bold leading-tight tracking-tight">{title}</h1>
        {sub && <p className="mt-0.5 max-w-[72ch] text-ink-2">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const SEV: Record<Severity, { icon: typeof Info; color: string; label: string }> = {
  error: { icon: AlertOctagon, color: "text-critical", label: "Error" },
  warning: { icon: AlertTriangle, color: "text-[#b07800] dark:text-warning", label: "Warning" },
  info: { icon: Info, color: "text-ink-2", label: "Info" },
};

/** Status colour never carries meaning alone: icon + label always. */
export function SeverityTag({ severity, count }: { severity: Severity; count?: number }) {
  const s = SEV[severity];
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-sm font-medium ${s.color}`}>
      <Icon size={14} aria-hidden />
      {count !== undefined ? <span className="num">{count}</span> : null}
      <span className={count !== undefined ? "sr-only" : ""}>{s.label}{count !== undefined && count !== 1 ? "s" : ""}</span>
    </span>
  );
}

export function FlagCounts({ counts }: { counts: Record<Severity, number> }) {
  const shown = (["error", "warning"] as Severity[]).filter((s) => counts[s] > 0);
  if (!shown.length) return <span className="text-sm text-muted">None</span>;
  return <span className="inline-flex gap-2">{shown.map((s) => <SeverityTag key={s} severity={s} count={counts[s]} />)}</span>;
}

const COMPLETENESS_TEXT: Record<Completeness, string> = {
  complete: "Complete",
  partial: "Partial",
  missing: "Missing",
  no_sessions: "No sessions",
};

/** A daily metric value with its coverage. Partial values carry a hatched marker and "2/3". */
export function MetricValue({ block, digits = 0 }: { block: MetricBlock; digits?: number }) {
  const { completeness: c, value, valid_sessions: v, expected_sessions: e } = block;
  const title = c === "partial"
    ? `Partial: known sum from ${v} of ${e} sessions`
    : c === "missing" ? `Missing in all ${e} sessions (null, not zero)` : COMPLETENESS_TEXT[c];
  return (
    <span className="inline-flex items-center justify-end gap-1.5 num" title={title}>
      {c === "partial" && (
        <span className="inline-flex items-center gap-1 rounded-sm px-1 text-[11px] font-semibold text-serious" aria-label={title}>
          <span className="hatch inline-block h-2.5 w-2.5 rounded-[2px] text-serious" aria-hidden />
          {v}/{e}
        </span>
      )}
      <span className={c === "missing" || c === "no_sessions" ? "text-muted" : ""}>{fmt(value, digits)}</span>
    </span>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }:
  { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line-strong bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded px-2.5 py-1 text-sm font-medium ${value === o.value ? "bg-ink text-surface" : "text-ink-2 hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, children, label, className = "" }:
  { value: string; onChange: (v: string) => void; children: ReactNode; label: string; className?: string }) {
  return (
    <label className={`inline-flex flex-col gap-0.5 text-xs text-ink-2 ${className}`}>
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-line-strong bg-surface px-2 py-1.5 text-sm text-ink"
      >
        {children}
      </select>
    </label>
  );
}

export function DateInput({ value, onChange, label, min, max }:
  { value: string; onChange: (v: string) => void; label: string; min?: string; max?: string }) {
  return (
    <label className="inline-flex flex-col gap-0.5 text-xs text-ink-2">
      {label}
      <input type="date" value={value} min={min} max={max} onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-ink" />
    </label>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="py-10 text-center text-ink-2" role="status">{what}…</p>;
}

export function ErrorNote({ error }: { error: unknown }) {
  return (
    <p role="alert" className="rounded-md border border-critical/40 bg-critical/5 px-3 py-2 text-sm text-critical">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}

export function Legend({ items }: { items: { label: string; swatch: ReactNode }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-2">
      {items.map((i) => (
        <li key={i.label} className="inline-flex items-center gap-1.5">{i.swatch}{i.label}</li>
      ))}
    </ul>
  );
}

export const Swatch = ({ color, hatch = false, dashed = false }: { color?: string; hatch?: boolean; dashed?: boolean }) => (
  <span
    aria-hidden
    className={`inline-block h-3 w-3 rounded-[3px] ${hatch ? "hatch" : ""} ${dashed ? "unobserved" : ""}`}
    style={hatch ? { color } : dashed ? undefined : { background: color }}
  />
);

/** Chart colours read from CSS tokens so light/dark both come from the validated steps. */
export function useChartTheme() {
  const read = () => ({
    training: cssVar("--training"), game: cssVar("--game"), other: cssVar("--other"),
    ink: cssVar("--ink"), ink2: cssVar("--ink-2"), muted: cssVar("--muted"),
    line: cssVar("--line"), lineStrong: cssVar("--line-strong"), surface: cssVar("--surface"),
    serious: cssVar("--serious"), font: "Barlow Semi Condensed, system-ui, sans-serif",
    dark: window.matchMedia("(prefers-color-scheme: dark)").matches,
  });
  const [t, setT] = useState(read);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setT(read());
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return t;
}
