"""Stable, versioned JSON output contract and the flattened daily CSV."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
from typing import List, Optional

FIELD_DICTIONARY = {
    "units": {
        "duration_min": "minutes (from Excel day fractions x 1440, timedelta, or h:mm:ss text)",
        "hit_min": "minutes of 'High intensity training (hh:mm:ss)'",
        "trimp": "TRIMP index (source-defined, dimensionless)",
        "movement_load": "source-defined arbitrary units (AU)",
        "avg_movement_intensity": "source-defined; unit and vendor formula not established",
        "efficiency": "Movement Load AU per TRIMP index point (daily, calculated)",
        "trimp_per_min": "TRIMP index per minute (daily, calculated); session values are source-reported",
        "measurement_error_pct": "percent points, interpreted from cell format and column header",
        "heart_rate": "beats per minute",
        "dates": "ISO 8601 calendar date YYYY-MM-DD, local date as recorded (no timezone shift)",
        "wellness": "unknown scale, direction and unit; stored exactly as recorded",
    },
    "nullability": "null = missing or unusable. 0 = a recorded zero. Never interchangeable. "
                   "No value is filled with zero.",
    "provenance": "Every raw, cleaned and wellness record has provenance {file, sheet, excel_row}; "
                  "record_id = <first 12 hex of file SHA-256>:<fd|wl>-<excel row>.",
    "record_status": {
        "included": "counts towards daily totals",
        "excluded": "kept but not counted (exact_duplicate or manual_override)",
        "rejected": "no usable athlete or date; visible but cannot be aggregated",
    },
    "completeness": {
        "complete": "every included session of the day has the metric",
        "partial": "some sessions have it; value is the sum of the known values only",
        "missing": "no session has it; value is null",
        "no_sessions": "breakdown bucket has no sessions that day; value is null",
    },
    "metric_block": "{value, valid_sessions, expected_sessions, completeness}",
    "derived_ratios": "efficiency = total Movement Load / total TRIMP; trimp_per_min = total TRIMP / "
                      "total duration. Only when both inputs are complete over the same sessions and "
                      "the denominator > 0; otherwise value null with a reason. Session ratios are "
                      "never averaged.",
    "source_reported": "acute_training_load, chronic_training_load and acwr are copied from the "
                       "source system for reference only. They are NOT recalculated or validated.",
    "history": "athletes[].history lists observed dates and gaps. Gaps are unobserved, not rest or zero.",
    "duplicates": "Exact duplicates (all source cells identical) keep the first record as canonical; "
                  "copies are excluded with duplicate_of. Possible duplicates (overlapping or same-start "
                  "sessions) stay included with a warning until reviewed.",
}

DAILY_CSV_COLUMNS = [
    "athlete_id", "athlete_label", "date", "study_day_index", "session_count",
    "training_sessions", "game_sessions", "other_sessions",
]
_METRICS = ("duration_min", "trimp", "movement_load", "hit_min")


def sanitize(obj):
    """Recursively make a structure JSON-safe (NaN/Inf -> null, dates -> ISO strings, sets -> lists)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items() if not str(k).startswith("_tmp")}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, set):
        return [sanitize(v) for v in sorted(obj, key=str)]
    if isinstance(obj, (dt.datetime, dt.date, dt.time)):
        return obj.isoformat()
    if isinstance(obj, dt.timedelta):
        return {"timedelta_seconds": obj.total_seconds()}
    return obj


def to_json(output: dict, indent: Optional[int] = 2, include_raw: bool = True) -> str:
    out = output
    if not include_raw:
        out = dict(output)
        out["rawRecords"] = {"omitted": True, "count": len(output["rawRecords"]),
                             "note": "Raw cell dump omitted; see cleanedRecords[].source_values."}
    return json.dumps(sanitize(out), indent=indent, ensure_ascii=False, allow_nan=False)


def daily_to_csv(daily: List[dict]) -> str:
    cols = list(DAILY_CSV_COLUMNS)
    for m in _METRICS:
        cols += [m, f"{m}_completeness", f"{m}_valid_sessions", f"{m}_expected_sessions"]
    for b in ("training", "game", "other"):
        cols += [f"{b}_{m}" for m in _METRICS]
    cols += ["efficiency", "efficiency_null_reason", "trimp_per_min", "trimp_per_min_null_reason",
             "gd_labels", "gd_conflict", "wellness_observations", "flag_count", "source_record_ids",
             "excluded_record_ids"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for d in daily:
        row = {
            "athlete_id": d["athlete_id"], "athlete_label": d["athlete_label"], "date": d["date"],
            "study_day_index": d["study_day_index"], "session_count": d["session_count"],
            "training_sessions": d["session_counts_by_type"]["training"],
            "game_sessions": d["session_counts_by_type"]["game"],
            "other_sessions": d["session_counts_by_type"]["other"],
        }
        for m in _METRICS:
            t = d["totals"][m]
            row.update({m: t["value"], f"{m}_completeness": t["completeness"],
                        f"{m}_valid_sessions": t["valid_sessions"],
                        f"{m}_expected_sessions": t["expected_sessions"]})
            for b in ("training", "game", "other"):
                row[f"{b}_{m}"] = d["breakdown"][b][m]["value"]
        for r in ("efficiency", "trimp_per_min"):
            row[r] = d["derived"][r]["value"]
            row[f"{r}_null_reason"] = d["derived"][r]["reason"]
        row.update({
            "gd_labels": "|".join(d["schedule"]["gd_labels"]),
            "gd_conflict": d["schedule"]["gd_conflict"],
            "wellness_observations": len(d["wellness"]),
            "flag_count": len(d["quality"]["flag_ids"]),
            "source_record_ids": "|".join(d["source_record_ids"]),
            "excluded_record_ids": "|".join(d["excluded_record_ids"]),
        })
        w.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buf.getvalue()
