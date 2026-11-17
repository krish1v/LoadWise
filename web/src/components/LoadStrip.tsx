import type { DailyRow, MetricKey } from "../api";
import { fmt, fmtDate, metricMeta } from "../format";

/**
 * One athlete's daily load as a strip of thin bars: training (blue) under game (orange).
 * Partial days carry a hatched cap; unobserved days are a dashed tick, never a zero bar.
 */
export function LoadStrip({ days, rows, metric, max, height = 34, onDay, label }:
  { days: string[]; rows: Map<string, DailyRow>; metric: MetricKey; max: number; height?: number;
    onDay?: (date: string) => void; label: string }) {
  const bw = 7, gap = 2, w = days.length * (bw + gap) - gap;
  const scale = (v: number) => (max > 0 ? Math.max(1.5, (v / max) * (height - 4)) : 0);
  const m = metricMeta(metric);
  return (
    <svg width={w} height={height} viewBox={`0 0 ${w} ${height}`} role="group" aria-label={label} className="block overflow-visible">
      <defs>
        <pattern id="hatch-p" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="4" height="4" fill="var(--surface)" />
          <line x1="0" y1="0" x2="0" y2="4" stroke="var(--serious)" strokeWidth="2" />
        </pattern>
      </defs>
      <line x1={0} x2={w} y1={height - 0.5} y2={height - 0.5} stroke="var(--line)" />
      {days.map((date, i) => {
        const x = i * (bw + gap);
        const r = rows.get(date);
        if (!r) {
          return (
            <g key={date}>
              <title>{fmtDate(date, true)}: no data recorded (unobserved, not rest)</title>
              <line x1={x + 1} x2={x + bw - 1} y1={height - 2} y2={height - 2} stroke="var(--line-strong)" strokeDasharray="2 1.5" />
            </g>
          );
        }
        const block = r[metric];
        const tr = (r[`training_${metric}`] as number | null) ?? 0;
        const gm = (r[`game_${metric}`] as number | null) ?? 0;
        const ot = (r[`other_${metric}`] as number | null) ?? 0;
        const hT = scale(tr + ot), hG = gm > 0 ? scale(gm) : 0;
        const total = hT + hG + (hT && hG ? 1 : 0);
        const partial = block.completeness === "partial";
        const tip = `${fmtDate(date, true)}: ${m.label} ${fmt(block.value, m.digits)}${partial ? ` (partial, ${block.valid_sessions}/${block.expected_sessions} sessions)` : block.completeness === "missing" ? " (missing in all sessions)" : ""}`;
        return (
          <g key={date} onClick={() => onDay?.(date)} className={onDay ? "cursor-pointer" : ""}
            tabIndex={onDay ? 0 : undefined} role={onDay ? "button" : undefined} aria-label={tip}
            onKeyDown={(e) => { if (onDay && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onDay(date); } }}>
            <title>{tip}</title>
            <rect x={x - 1} y={0} width={bw + 2} height={height} fill="transparent" />
            {block.value === null ? (
              <rect x={x} y={height - 6} width={bw} height={5} fill="url(#hatch-p)" rx={1} />
            ) : (
              <>
                {hT > 0 && <rect x={x} y={height - hT} width={bw} height={hT} rx={1.5} fill={ot && !tr ? "var(--other)" : "var(--training)"} />}
                {hG > 0 && <rect x={x} y={height - hT - (hT ? 1 : 0) - hG} width={bw} height={hG} rx={1.5} fill="var(--game)" />}
                {partial && <rect x={x} y={height - total - 4} width={bw} height={3} fill="url(#hatch-p)" />}
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
