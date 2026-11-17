import type { MetricKey } from "./api";

// `noun` is the in-sentence form ("daily movement load", "daily TRIMP").
export const METRICS: { key: MetricKey; label: string; noun: string; short: string; unit: string; digits: number }[] = [
  { key: "trimp", label: "TRIMP", noun: "TRIMP", short: "TRIMP", unit: "index", digits: 0 },
  { key: "movement_load", label: "Movement Load", noun: "movement load", short: "Move load", unit: "AU", digits: 0 },
  { key: "hit_min", label: "High-intensity minutes", noun: "high-intensity minutes", short: "HI min", unit: "min", digits: 1 },
  { key: "duration_min", label: "Duration", noun: "duration", short: "Duration", unit: "min", digits: 0 },
];
export const metricMeta = (k: MetricKey) => METRICS.find((m) => m.key === k)!;

// Round only for display; values stay full-precision in the data.
export function fmt(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function fmtDate(iso: string | null | undefined, withDay = false): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  const wd = DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${withDay ? wd + " " : ""}${d} ${MONTHS[m - 1]} ${y}`;
}

export const shortDate = (iso: string) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}`;
};

export const humanRule = (code: string) =>
  code.toLowerCase().replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
