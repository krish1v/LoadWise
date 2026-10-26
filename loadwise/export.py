"""Build the stable, versioned JSON output contract and a flattened daily CSV.

JSON is strictly serializable: no NaN / Infinity, no raw dates/times/timedeltas,
stable IDs and deterministic ordering throughout.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import math
from typing import List, Optional

from .config import SCHEMA_VERSION, Config
from .normalize import _jsonable_source
from .schema import ADDITIVE_METRICS, FIELD_DICTIONARY


def sanitize(obj):
    """Recursively convert a structure into strictly JSON-safe values."""
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, _dt.date):
        return obj.isoformat()
    if isinstance(obj, _dt.time):
        return obj.isoformat()
    if isinstance(obj, _dt.timedelta):
        return {"kind": "duration", "seconds": obj.total_seconds()}
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return str(obj)


def _raw_to_jsonable(raw) -> dict:
    return {
        "record_id": raw.record_id,
        "file": raw.file,
        "sheet": raw.sheet,
        "excel_row": raw.excel_row,
        "cells": {h: _jsonable_source(v) for h, v in raw.cells.items()},
        "formats": dict(raw.formats),
    }


def build_output(*, config: Config, idmap, raw_full_day, raw_wellness,
                 cleaned_records: List[dict], daily_records: List[dict],
                 wellness_records: List[dict], athlete_history: List[dict],
                 quality_flags: List[dict], import_metadata: dict,
                 rollover_preview: list, day_index_issues: list) -> dict:
    """Assemble the full output object (already JSON-safe)."""
    severities = {"error": 0, "warning": 0, "info": 0}
    for f in quality_flags:
        severities[f["severity"]] = severities.get(f["severity"], 0) + 1

    statuses = {"included": 0, "excluded": 0, "rejected": 0, "other": 0}
    for r in cleaned_records:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1

    resolved_dates = sorted({r["date_resolved"] for r in cleaned_records if r["date_resolved"]})

    summary = {
        "full_day_records": len(cleaned_records),
        "wellness_records": len(wellness_records),
        "athletes": len(idmap.athletes()),
        "resolved_dates": len(resolved_dates),
        "date_range": {"first": resolved_dates[0] if resolved_dates else None,
                       "last": resolved_dates[-1] if resolved_dates else None},
        "daily_records": len(daily_records),
        "record_status_counts": statuses,
        "excluded_duplicates": sum(1 for r in cleaned_records
                                   if r["status"] == "excluded" and r["status_reason"] == "exact_duplicate"),
        "flag_severity_counts": severities,
        "partial_daily_records": sum(1 for d in daily_records if d["completeness"]["any_partial"]),
    }

    output = {
        "schemaVersion": SCHEMA_VERSION,
        "importMetadata": import_metadata,
        "configuration": {
            **config.to_dict(),
            "rollover_preview": rollover_preview,
            "day_index_issues": day_index_issues,
            "aggregation_policies": {
                "additive_metrics_summed_independently": ADDITIVE_METRICS,
                "derived_ratios": "computed only from complete, matched inputs with positive denominator; "
                                  "session ratios are never averaged",
                "average_movement_intensity": "session values preserved; no daily aggregate produced",
                "source_reported_fields": "ACWR/ATL/CTL preserved as source-reported, not recalculated",
                "duplicates": "exact copies excluded from totals (one canonical kept); "
                              "possible overlaps kept included until reviewed",
                "missing_vs_zero": "null = missing/unusable; valid zeros preserved",
            },
        },
        "fieldDictionary": FIELD_DICTIONARY,
        "athletes": idmap.athletes(),
        "rawRecords": {
            "fullDay": [_raw_to_jsonable(r) for r in raw_full_day],
            "wellness": [_raw_to_jsonable(r) for r in raw_wellness],
        },
        "cleanedRecords": cleaned_records,
        "dailyRecords": daily_records,
        "wellnessRecords": wellness_records,
        "scheduleContext": {
            "note": "Per-athlete observed dates and gaps for a future, separate ACWR module. "
                    "Gaps are NOT assumed to be rest/zero-load. Window definitions and "
                    "missing-day policy still require agreement.",
            "athletes": athlete_history,
        },
        "qualityFlags": quality_flags,
        "summary": summary,
    }
    return sanitize(output)


def to_json(output: dict, *, indent: Optional[int] = 2, include_raw: bool = True) -> str:
    """Serialize deterministically. allow_nan=False guarantees JSON-safety.

    include_raw=False replaces the (large) rawRecords arrays with counts, for
    lighter downloads; traceability via record IDs in cleanedRecords is kept.
    """
    if not include_raw:
        rr = output.get("rawRecords", {})
        output = {**output, "rawRecords": {
            "fullDay": [], "wellness": [],
            "omitted": True,
            "fullDay_count": len(rr.get("fullDay", [])),
            "wellness_count": len(rr.get("wellness", [])),
        }}
    return json.dumps(output, indent=indent, ensure_ascii=False,
                      allow_nan=False, sort_keys=False)


def daily_to_csv(daily_records: List[dict]) -> str:
    """Flatten daily records to CSV, including completeness columns."""
    fieldnames = [
        "daily_id", "athlete_id", "athlete_label", "date", "day_index",
        "included_session_count",
    ]
    for m in ADDITIVE_METRICS:
        fieldnames += [m, f"{m}__completeness", f"{m}__valid_sessions", f"{m}__expected_sessions"]
    for bucket in ("training", "game", "other"):
        for m in ADDITIVE_METRICS:
            fieldnames.append(f"{bucket}__{m}")
    fieldnames += [
        "efficiency_calculated", "efficiency_reason",
        "trimp_per_min_calculated", "trimp_per_min_reason",
        "avg_movement_intensity_daily",
        "has_game", "gd_labels", "wellness_observation_count",
        "quality_flag_count", "any_partial", "source_record_ids",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for d in daily_records:
        row = {
            "daily_id": d["daily_id"],
            "athlete_id": d["athlete_id"],
            "athlete_label": d["athlete_label"],
            "date": d["date"],
            "day_index": d["day_index"],
            "included_session_count": d["included_session_count"],
            "efficiency_calculated": d["derived"]["efficiency_calculated"]["value"],
            "efficiency_reason": d["derived"]["efficiency_calculated"]["reason"],
            "trimp_per_min_calculated": d["derived"]["trimp_per_min_calculated"]["value"],
            "trimp_per_min_reason": d["derived"]["trimp_per_min_calculated"]["reason"],
            "avg_movement_intensity_daily": d["derived"]["avg_movement_intensity"]["daily_value"],
            "has_game": d["schedule_context"]["has_game"],
            "gd_labels": "|".join(d["schedule_context"]["gd_labels"]),
            "wellness_observation_count": len(d["wellness_observations"]),
            "quality_flag_count": len(d["quality_flag_ids"]),
            "any_partial": d["completeness"]["any_partial"],
            "source_record_ids": "|".join(d["source_record_ids"]),
        }
        for m in ADDITIVE_METRICS:
            block = d["totals"][m]
            row[m] = block["value"]
            row[f"{m}__completeness"] = block["completeness"]
            row[f"{m}__valid_sessions"] = block["valid_sessions"]
            row[f"{m}__expected_sessions"] = block["expected_sessions"]
        for bucket in ("training", "game", "other"):
            for m in ADDITIVE_METRICS:
                row[f"{bucket}__{m}"] = d["breakdown"][bucket][m]["value"]
        writer.writerow(row)
    return buf.getvalue()
