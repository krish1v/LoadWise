import { useMemo, useState } from "react";
import {
  createColumnHelper, flexRender, getCoreRowModel, getPaginationRowModel, getSortedRowModel,
  useReactTable, type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp } from "lucide-react";
import type { DailyRow, MetricBlock } from "../api";
import { fmt, fmtDate } from "../format";
import { useOpenDay } from "./DayDrawer";
import { Button, FlagCounts, MetricValue } from "./ui";

const h = createColumnHelper<DailyRow>();
const metricSort = (k: "trimp" | "movement_load" | "hit_min" | "duration_min") =>
  (a: { original: DailyRow }, b: { original: DailyRow }) => ((a.original[k] as MetricBlock).value ?? -1) - ((b.original[k] as MetricBlock).value ?? -1);

export function DailyTable({ rows, showAthlete = true, pageSize = 25 }: { rows: DailyRow[]; showAthlete?: boolean; pageSize?: number }) {
  const openDay = useOpenDay();
  const [sorting, setSorting] = useState<SortingState>([{ id: "date", desc: true }]);
  const columns = useMemo(() => [
    ...(showAthlete ? [h.accessor("athlete_label", { header: "Athlete", sortingFn: (a, b) => a.original.athlete_label.localeCompare(b.original.athlete_label, undefined, { numeric: true }) })] : []),
    h.accessor("date", { header: "Date", cell: (c) => <span className="whitespace-nowrap">{fmtDate(c.getValue(), true)}</span> }),
    h.accessor("session_count", {
      header: "Sessions",
      cell: (c) => { const t = c.row.original.sessions_by_type; return <span className="whitespace-nowrap">{c.getValue()} <span className="text-muted">({[t.training && `${t.training} T`, t.game && `${t.game} G`, t.other && `${t.other} other`].filter(Boolean).join(", ")})</span></span>; },
    }),
    h.accessor((r) => r.trimp.value, { id: "trimp", header: "TRIMP", sortingFn: metricSort("trimp"), cell: (c) => <MetricValue block={c.row.original.trimp} /> }),
    h.accessor((r) => r.movement_load.value, { id: "movement_load", header: "Move load", sortingFn: metricSort("movement_load"), cell: (c) => <MetricValue block={c.row.original.movement_load} /> }),
    h.accessor((r) => r.hit_min.value, { id: "hit_min", header: "HI min", sortingFn: metricSort("hit_min"), cell: (c) => <MetricValue block={c.row.original.hit_min} digits={1} /> }),
    h.accessor((r) => r.duration_min.value, { id: "duration_min", header: "Duration", sortingFn: metricSort("duration_min"), cell: (c) => <MetricValue block={c.row.original.duration_min} /> }),
    h.accessor((r) => r.training_trimp as number | null, { id: "training_trimp", header: "Training TRIMP", cell: (c) => <span className="num text-ink-2">{fmt(c.getValue())}</span> }),
    h.accessor((r) => r.game_trimp as number | null, { id: "game_trimp", header: "Game TRIMP", cell: (c) => <span className="num text-ink-2">{fmt(c.getValue())}</span> }),
    h.accessor("efficiency", { header: "Efficiency", cell: (c) => <span className="num" title={c.row.original.efficiency_reason ?? "Movement Load ÷ TRIMP"}>{fmt(c.getValue(), 2)}</span> }),
    h.accessor("trimp_per_min", { header: "TRIMP/min", cell: (c) => <span className="num" title={c.row.original.trimp_per_min_reason ?? ""}>{fmt(c.getValue(), 2)}</span> }),
    h.accessor((r) => r.gd_labels.join(", "), { id: "gd", header: "GD", cell: (c) => <span className={c.row.original.gd_conflict ? "text-serious" : ""}>{c.getValue() || "—"}</span> }),
    h.accessor((r) => r.flag_counts.error * 1000 + r.flag_counts.warning, { id: "issues", header: "Issues", cell: (c) => <FlagCounts counts={c.row.original.flag_counts} /> }),
  ], [showAthlete]);

  const table = useReactTable({
    data: rows, columns, state: { sorting }, onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });
  const left = new Set(["athlete_label", "date", "gd"]);

  return (
    <div className="rounded-lg border border-line bg-surface">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1000px] text-sm">
          <thead className="border-b border-line text-ink-2">
            {table.getHeaderGroups().map((g) => (
              <tr key={g.id}>
                {g.headers.map((hd) => (
                  <th key={hd.id} className={`px-3 py-2 font-medium ${left.has(hd.id) ? "text-left" : "text-right"}`}
                    aria-sort={hd.column.getIsSorted() ? (hd.column.getIsSorted() === "desc" ? "descending" : "ascending") : "none"}>
                    <button className="inline-flex items-center gap-1 whitespace-nowrap hover:text-ink" onClick={hd.column.getToggleSortingHandler()}>
                      {flexRender(hd.column.columnDef.header, hd.getContext())}
                      {hd.column.getIsSorted() === "asc" && <ArrowUp size={13} />}
                      {hd.column.getIsSorted() === "desc" && <ArrowDown size={13} />}
                    </button>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((r) => (
              <tr key={r.id} onClick={() => openDay(r.original.athlete_id, r.original.date)}
                className="cursor-pointer border-b border-line/70 last:border-0 hover:bg-surface-2/70"
                tabIndex={0} onKeyDown={(e) => e.key === "Enter" && openDay(r.original.athlete_id, r.original.date)}>
                {r.getVisibleCells().map((c) => (
                  <td key={c.id} className={`px-3 py-1.5 ${left.has(c.column.id) ? "text-left" : "text-right"} ${c.column.id === "athlete_label" ? "font-semibold" : ""}`}>
                    {flexRender(c.column.columnDef.cell, c.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && <tr><td className="px-3 py-8 text-center text-ink-2" colSpan={columns.length}>No athlete-days match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2 text-sm text-ink-2">
        <span className="num">{rows.length.toLocaleString()} athlete-days · click a row to see its sessions and source rows</span>
        <span className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>Previous</Button>
          <span className="num">Page {table.getState().pagination.pageIndex + 1} of {Math.max(1, table.getPageCount())}</span>
          <Button variant="ghost" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>Next</Button>
        </span>
      </footer>
    </div>
  );
}
