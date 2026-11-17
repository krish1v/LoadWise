"""End-to-end orchestration: ingest -> normalize -> validate -> aggregate -> export.

`process_workbook` is a pure function of (file bytes, config, overrides): the same
inputs always give byte-identical JSON (pass `generated_at` to pin the timestamp).
Reading the workbook is the slow part, so a `ProcessResult` keeps its ingests and
`result.reprocess(overrides)` re-runs only the fast steps.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple, Union

from . import __version__
from .aggregate import build_athletes, build_daily_records, build_schedule_context
from .config import SCHEMA_VERSION, Config, LoadWiseInputError, SeasonYearRequired
from .export import FIELD_DICTIONARY, daily_to_csv, sanitize, to_json
from .ingest import (FULL_DAY_COLUMNS, WorkbookIngest, ingest_workbook)
from .normalize import _jsonable, is_yearless, normalize_sheet, resolve_date, rollover_preview
from .validate import (FlagCollector, apply_overrides, check_dates, check_gd_conflicts,
                       flag_possible_duplicates, mark_exact_duplicates, validate_sessions,
                       validate_wellness)

SourceLike = Union[str, bytes, Tuple[str, bytes]]


def _as_list(sources) -> List[SourceLike]:
    if isinstance(sources, (str, bytes, tuple)):
        return [sources]
    return list(sources)


def ingest_all(sources: Union[SourceLike, Iterable[SourceLike]]) -> List[WorkbookIngest]:
    """Read every workbook once; identical files (same SHA-256) are read only once."""
    out, seen = [], set()
    for src in _as_list(sources):
        name, data = (src if isinstance(src, tuple) else (None, src))
        ing = ingest_workbook(data, filename=name)
        if ing.sha256 not in seen:
            seen.add(ing.sha256)
            out.append(ing)
    return out


def _yearless_samples(ingests: List[WorkbookIngest]) -> List[str]:
    samples = []
    for ing in ingests:
        for sheet in (ing.full_day, ing.wellness):
            h = sheet.mapping.get("date")
            for r in sheet.records:
                v = r.cells.get(h) if h else None
                if is_yearless(v):
                    samples.append(v.strip())
                    if len(samples) >= 3:
                        return samples
    return samples


@dataclass
class ProcessResult:
    output: dict
    ingests: List[WorkbookIngest] = field(repr=False)
    config: Config = field(repr=False)
    overrides: Dict[str, dict] = field(default_factory=dict, repr=False)
    generated_at: Optional[str] = None

    @property
    def daily_records(self) -> List[dict]:
        return self.output["dailyRecords"]

    @property
    def cleaned_records(self) -> List[dict]:
        return self.output["cleanedRecords"]

    @property
    def quality_flags(self) -> List[dict]:
        return self.output["qualityFlags"]

    def to_json(self, indent: Optional[int] = 2, include_raw: bool = True) -> str:
        return to_json(self.output, indent=indent, include_raw=include_raw)

    def to_daily_csv(self) -> str:
        return daily_to_csv(self.daily_records)

    def reprocess(self, overrides: Optional[Dict[str, dict]] = None) -> "ProcessResult":
        return build(self.ingests, self.config, overrides if overrides is not None else self.overrides,
                     generated_at=self.generated_at)


def process_workbook(sources, config: Config, overrides: Optional[Dict[str, dict]] = None,
                     generated_at: Optional[str] = None) -> ProcessResult:
    """Process one workbook (path, bytes or (filename, bytes)) or a list of them.

    Raises SeasonYearRequired if yearless dates exist and config.season_start_year is None,
    and LoadWiseInputError for unusable files (empty, not .xlsx, missing required sheet/columns).
    """
    return build(ingest_all(sources), config, overrides or {}, generated_at=generated_at)


def build(ingests: List[WorkbookIngest], config: Config, overrides: Dict[str, dict],
          generated_at: Optional[str] = None) -> ProcessResult:
    if not ingests:
        raise LoadWiseInputError("No workbook to process.")
    if config.season_start_year is None:
        samples = _yearless_samples(ingests)
        if samples:
            raise SeasonYearRequired(samples)
    for rid, ov in (overrides or {}).items():
        if ov.get("action") not in ("include", "exclude"):
            raise LoadWiseInputError(f"Override for {rid} must be 'include' or 'exclude'.")

    fc = FlagCollector()
    sessions, wellness, raw_cells, raw_out = [], [], {}, []
    for ing in ingests:
        epoch = ing.workbook_epoch
        s = normalize_sheet(ing.full_day, "session", config, epoch)
        for rec in s:
            rec["study_day_consistent"] = True
        validate_sessions(s, config, fc)
        check_dates(s, fc)
        sessions += s
        wellness += normalize_sheet(ing.wellness, "wellness", config, epoch)
        for sheet in (ing.full_day, ing.wellness):
            for r in sheet.records:
                raw_cells[r.record_id] = r.cells
                raw_out.append({
                    "record_id": r.record_id, "import_id": r.import_id, "file": r.file,
                    "sheet": r.sheet, "excel_row": r.excel_row,
                    "cells": {k: _jsonable(v) for k, v in r.cells.items()},
                    "number_formats": {k: f for k, f in r.formats.items() if f != "General"},
                })
        unavailable = [FULL_DAY_COLUMNS[k] for k, h in ing.full_day.mapping.items() if h is None]
        if unavailable:
            fc.add(f"COLUMN_UNAVAILABLE", "info",
                   f"{ing.file}: optional columns not present: {', '.join(unavailable)}.",
                   "Those fields are null (unavailable) for every session of this file.")
        if not ing.wellness.present:
            fc.add("OPTIONAL_SHEET_MISSING", "info",
                   f"{ing.file}: " + " ".join(ing.wellness.messages),
                   "Daily records from this file have no wellness observations.")

    mark_exact_duplicates(sessions, raw_cells, fc)
    flag_possible_duplicates(sessions, config, fc)
    apply_overrides(sessions, overrides or {}, fc)
    check_gd_conflicts(sessions, fc)
    validate_wellness(wellness, {s["athlete_id"] for s in sessions if s["athlete_id"]}, fc)

    daily = build_daily_records(sessions, wellness)
    athletes = build_athletes(sessions, wellness, daily)
    for a in athletes:
        if len({v.strip().casefold() for v in a["source_label_variants"]}) < len(a["source_label_variants"]):
            fc.add("ATHLETE_LABEL_VARIANT", "info",
                   f"Labels {a['source_label_variants']} differ only in spacing/case and were treated "
                   f"as one athlete ({a['athlete_id']}).", "Sessions combined under one athlete ID.")
    flags = fc.flags
    sev_by_id = {f["flag_id"]: f["severity"] for f in flags}
    for d in daily:
        c = Counter(sev_by_id[f] for f in d["quality"]["flag_ids"] if f in sev_by_id)
        d["quality"]["flag_counts"] = {s: c.get(s, 0) for s in ("error", "warning", "info")}

    status = Counter(s["status"] for s in sessions)
    sev = Counter(f["severity"] for f in flags)
    output = {
        "schemaVersion": SCHEMA_VERSION,
        "importMetadata": {
            "generator": f"loadwise {__version__}",
            "generated_at": generated_at,
            "imports": [{
                "import_id": ing.import_id, "sha256": ing.sha256, "file": ing.file,
                "sheets_present": ing.sheet_names, "workbook_date_epoch": ing.epoch,
                "full_day": {"sheet": ing.full_day.name, "header_row": ing.full_day.header_row,
                             "records": len(ing.full_day.records),
                             "column_mapping": ing.full_day.mapping,
                             "messages": ing.full_day.messages},
                "wellness": {"sheet": ing.wellness.name, "present": ing.wellness.present,
                             "header_row": ing.wellness.header_row,
                             "records": len(ing.wellness.records),
                             "column_mapping": ing.wellness.mapping,
                             "messages": ing.wellness.messages},
            } for ing in ingests],
        },
        "configuration": {**config.to_dict(), "overrides": {k: overrides[k] for k in sorted(overrides)}},
        "fieldDictionary": FIELD_DICTIONARY,
        "athletes": athletes,
        "rawRecords": raw_out,
        "cleanedRecords": sessions,
        "dailyRecords": daily,
        "wellnessRecords": wellness,
        "scheduleContext": build_schedule_context(sessions),
        "qualityFlags": flags,
        "summary": {
            "imports": len(ingests),
            "session_records": len(sessions),
            "sessions_included": status.get("included", 0),
            "sessions_excluded": status.get("excluded", 0),
            "sessions_rejected": status.get("rejected", 0),
            "excluded_exact_duplicates": sum(s["status_reason"] == "exact_duplicate" for s in sessions),
            "possible_duplicate_sessions": sum(bool(s.get("possible_duplicate_of")) for s in sessions),
            "wellness_records": len(wellness),
            "athletes": len(athletes),
            "resolved_dates": len({s["date"] for s in sessions if s["date"]}),
            "daily_records": len(daily),
            "daily_records_with_incomplete_metrics": sum(bool(d["quality"]["incomplete_metrics"])
                                                         for d in daily),
            "multi_session_days": sum(d["session_count"] > 1 for d in daily),
            "flags": {s: sev.get(s, 0) for s in ("error", "warning", "info")},
            "flags_by_rule": dict(sorted(Counter(f["rule_code"] for f in flags).items())),
            "date_range": {"first": min((d["date"] for d in daily), default=None),
                           "last": max((d["date"] for d in daily), default=None)},
        },
    }
    return ProcessResult(output=sanitize(output), ingests=ingests, config=config,
                         overrides=dict(overrides or {}), generated_at=generated_at)


def preview_workbook(source: SourceLike, config: Config) -> dict:
    """Cheap pre-processing review: sheets, detected headers, date samples, rollover table.

    Never raises for a missing season year; reports `needs_season_year` instead.
    """
    return preview_ingest(ingest_all(source)[0], config)


def preview_ingest(ing: WorkbookIngest, config: Config) -> dict:
    """Same as preview_workbook, for an already-read workbook."""
    h = ing.full_day.mapping.get("date")
    raw_dates = [r.cells.get(h) for r in ing.full_day.records] if h else []
    sample_idx = sorted(set(list(range(min(3, len(raw_dates)))) +
                            list(range(max(0, len(raw_dates) - 3), len(raw_dates)))))
    needs_year = any(is_yearless(v) for v in raw_dates) and config.season_start_year is None
    return sanitize({
        "file": ing.file, "sha256": ing.sha256, "sheets_present": ing.sheet_names,
        "workbook_date_epoch": ing.epoch,
        "sheets": [{
            "role": role, "sheet": s.name, "present": s.present, "header_row": s.header_row,
            "records": len(s.records), "columns": len(s.headers),
            "mapped": {k: v for k, v in s.mapping.items() if v},
            "unavailable": [k for k, v in s.mapping.items() if v is None],
            "messages": s.messages,
        } for role, s in (("workload sessions", ing.full_day), ("wellness", ing.wellness))],
        "needs_season_year": needs_year,
        "date_samples": [{"excel_row": ing.full_day.records[i].excel_row, "raw": _jsonable(raw_dates[i]),
                          "resolved": resolve_date(raw_dates[i], config, ing.workbook_epoch)}
                         for i in sample_idx],
        "rollover": rollover_preview(raw_dates, config),
    })


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
