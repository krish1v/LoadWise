import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Upload, X } from "lucide-react";
import { api, type Preview, type Status } from "../api";
import { fmtDate } from "../format";
import { Button, ErrorNote } from "./ui";

type Source = { kind: "demo" } | { kind: "file"; file: File };

export function UploadDialog({ status, onClose }: { status: Status | undefined; onClose: () => void }) {
  const qc = useQueryClient();
  const storedYear = status?.season_start_year ?? null;
  const [source, setSource] = useState<Source | null>(null);
  const [year, setYear] = useState<string>(storedYear ? String(storedYear) : "");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const yearNum = /^\d{4}$/.test(year) ? Number(year) : null;

  const pv = useMutation({
    mutationFn: async () => {
      if (!source) throw new Error("Choose a file first.");
      return source.kind === "demo" ? api.previewDemo(yearNum) : api.previewFile(source.file, yearNum);
    },
    onSuccess: setPreview,
  });
  const run = useMutation({
    mutationFn: async () => {
      if (!source || yearNum === null) throw new Error("Set the season start year first.");
      return source.kind === "demo" ? api.importDemo(yearNum) : api.importFile(source.file, yearNum);
    },
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
  });

  // Re-preview whenever the file or year changes.
  useEffect(() => { if (source) pv.mutate(); }, [source, yearNum]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (f: File | undefined) => {
    if (!f) return;
    setSource({ kind: "file", file: f });
    setPreview(null);
  };
  const useDemo = () => {
    setSource({ kind: "demo" });
    if (!storedYear) setYear(String(status?.demo_season_year ?? 2025));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/30 p-4 sm:p-10" role="dialog" aria-modal="true" aria-labelledby="upload-title">
      <div className="w-full max-w-2xl rounded-xl border border-line bg-surface shadow-xl">
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 id="upload-title" className="text-xl font-bold">Add workload data</h2>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-ink-2 hover:bg-surface-2"><X size={20} /></button>
        </header>

        <div className="space-y-5 px-5 py-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]); }}
            className={`flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center ${dragging ? "border-training bg-training/5" : "border-line-strong"}`}
          >
            <FileSpreadsheet className="text-ink-2" size={28} aria-hidden />
            {source ? (
              <p className="font-semibold">{source.kind === "demo" ? "Demo: Georgia Tech anonymized workbook" : source.file.name}</p>
            ) : (
              <p className="text-ink-2">Drop the .xlsx export here</p>
            )}
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={() => input.current?.click()}><Upload size={15} />Choose file</Button>
              {status?.demo_available && <Button variant="ghost" onClick={useDemo}>Use the demo workbook</Button>}
            </div>
            <input ref={input} type="file" accept=".xlsx" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          </div>

          <div className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-semibold">Season start year</span>
              <input
                value={year}
                onChange={(e) => setYear(e.target.value.trim())}
                inputMode="numeric"
                placeholder="e.g. 2025"
                disabled={storedYear !== null}
                className="w-32 rounded-md border border-line-strong bg-surface px-2 py-1.5 text-ink num disabled:opacity-70"
              />
            </label>
            <p className="max-w-md text-sm text-ink-2">
              {storedYear !== null
                ? `Stored history uses the ${storedYear}–${String(storedYear + 1).slice(2)} season. Reset the history to change it.`
                : "Dates in the export have no year. Months from July onwards get this year; January to June get the next one."}
            </p>
          </div>

          {pv.error && <ErrorNote error={pv.error} />}
          {preview && <PreviewView p={preview} />}
          {run.error && <ErrorNote error={run.error} />}
        </div>

        <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!preview || preview.needs_season_year || yearNum === null || run.isPending}
            onClick={() => run.mutate()}
          >
            {run.isPending ? "Processing…" : "Process workbook"}
          </Button>
        </footer>
      </div>
    </div>
  );
}

function PreviewView({ p }: { p: Preview }) {
  return (
    <div className="space-y-4 rounded-lg bg-surface-2 p-4 text-sm">
      <div>
        <h3 className="mb-1 font-semibold">Sheets found</h3>
        <ul className="space-y-0.5">
          {p.sheets.map((s) => (
            <li key={s.role}>
              {s.present ? (
                <><span className="font-medium">{s.sheet}</span> ({s.role}): header on row <span className="num">{s.header_row}</span>, <span className="num">{s.records.toLocaleString()}</span> records, {s.columns} columns
                  {s.unavailable.length > 0 && s.role !== "wellness" && <span className="text-ink-2">. Not present: {s.unavailable.join(", ")}</span>}</>
              ) : (
                <span className="text-ink-2">{s.messages.join(" ")}</span>
              )}
            </li>
          ))}
        </ul>
      </div>
      {p.rollover.length > 0 && (
        <div>
          <h3 className="mb-1 font-semibold">How yearless dates will resolve</h3>
          {p.needs_season_year ? (
            <p className="font-medium text-serious">Enter the season start year to see the resolved dates.</p>
          ) : (
            <table className="text-sm num">
              <tbody>
                {p.rollover.map((r) => (
                  <tr key={r.month}>
                    <td className="pr-4">{r.month_name}</td>
                    <td className="pr-4 font-semibold">{r.resolved_year}</td>
                    <td className="pr-4 text-ink-2">{r.records} rows</td>
                    <td className="text-ink-2">e.g. “{r.example}”</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <div>
        <h3 className="mb-1 font-semibold">Sample rows</h3>
        <ul className="num">
          {p.date_samples.map((s) => (
            <li key={s.excel_row}>
              Row {s.excel_row}: “{String(s.raw)}” → {s.resolved.iso ? fmtDate(s.resolved.iso) : <span className="text-serious">{s.resolved.error?.replace(/_/g, " ")}</span>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
