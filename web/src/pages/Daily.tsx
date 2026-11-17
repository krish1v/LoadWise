import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api } from "../api";
import { DailyTable } from "../components/DailyTable";
import { DateInput, ErrorNote, Loading, PageHeader, Select } from "../components/ui";

export function DailyPage() {
  const daily = useQuery({ queryKey: ["daily", "all"], queryFn: () => api.daily() });
  const athletes = useQuery({ queryKey: ["athletes"], queryFn: api.athletes });
  const [athlete, setAthlete] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [only, setOnly] = useState<"all" | "partial" | "multi" | "issues">("all");

  const rows = useMemo(() => (daily.data ?? []).filter((r) =>
    (!athlete || r.athlete_id === athlete) && (!from || r.date >= from) && (!to || r.date <= to) &&
    (only === "all" ||
      (only === "partial" && [r.trimp, r.movement_load, r.hit_min, r.duration_min].some((b) => b.completeness !== "complete")) ||
      (only === "multi" && r.session_count > 1) ||
      (only === "issues" && r.flag_counts.error + r.flag_counts.warning > 0))), [daily.data, athlete, from, to, only]);

  if (daily.isLoading) return <Loading what="Loading daily records" />;
  if (daily.error) return <ErrorNote error={daily.error} />;
  const all = daily.data!;
  const min = all.reduce((m, r) => (r.date < m ? r.date : m), all[0]?.date ?? "");
  const max = all.reduce((m, r) => (r.date > m ? r.date : m), "");

  return (
    <>
      <PageHeader
        title="Daily data"
        sub="One row per athlete per day. All sessions that day are summed, and a partial marker (e.g. 1/2) means only some sessions had that metric."
        actions={<>
          <a href="/api/export.csv" className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm font-semibold hover:bg-surface-2"><Download size={15} />Daily CSV</a>
          <a href="/api/export.json" className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm font-semibold hover:bg-surface-2"><Download size={15} />Full JSON</a>
        </>}
      />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Select label="Athlete" value={athlete} onChange={setAthlete}>
          <option value="">All athletes</option>
          {athletes.data?.map((a) => <option key={a.athlete_id} value={a.athlete_id}>{a.label}</option>)}
        </Select>
        <DateInput label="From" value={from} onChange={setFrom} min={min} max={max} />
        <DateInput label="To" value={to} onChange={setTo} min={min} max={max} />
        <Select label="Show" value={only} onChange={(v) => setOnly(v as typeof only)}>
          <option value="all">All days</option>
          <option value="partial">Days with partial or missing metrics</option>
          <option value="multi">Days with 2+ sessions</option>
          <option value="issues">Days with errors or warnings</option>
        </Select>
      </div>
      <DailyTable rows={rows} />
    </>
  );
}
