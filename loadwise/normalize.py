"""Standardize raw records into normalized records.

Normalization preserves every source value alongside its normalized counterpart,
keeps full numeric precision, uses null (None) for missing/unusable values, and
preserves valid zeros. Raw records are never mutated.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from . import schema, units
from .config import Config
from .dates import resolve_date
from .identity import IdentityMap, normalize_label
from .ingest import RawRecord, SheetIngest


def _bucket(measurement_type: Optional[str], known: tuple) -> str:
    if measurement_type is None:
        return "other"
    mt = measurement_type.strip().lower()
    if mt == "training":
        return "training"
    if mt == "game":
        return "game"
    return "other"


def collect_labels(full_day: SheetIngest, wellness: SheetIngest) -> List[str]:
    """All normalized athlete labels seen in either sheet (for identity assignment)."""
    labels = set()
    for rec in full_day.records:
        lbl = normalize_label(rec.cells.get("Athlete name"))
        if lbl:
            labels.add(lbl)
    if wellness.present:
        for rec in wellness.records:
            lbl = normalize_label(rec.cells.get("Performed By"))
            if lbl:
                labels.add(lbl)
    return sorted(labels)


def normalize_full_day(rec: RawRecord, config: Config, idmap: IdentityMap) -> dict:
    cells = rec.cells
    formats = rec.formats

    raw_label = cells.get("Athlete name")
    norm_label = normalize_label(raw_label)
    athlete_id = idmap.get(norm_label)

    mtype_raw = cells.get("Measurement type")
    mtype = str(mtype_raw).strip() if mtype_raw is not None else None

    dres = resolve_date(cells.get("Date"), config)

    out: dict = {
        "record_id": rec.record_id,
        "provenance": {"file": rec.file, "sheet": rec.sheet, "excel_row": rec.excel_row},
        "athlete_id": athlete_id,
        "athlete_label": norm_label,
        "athlete_label_raw": raw_label,
        "measurement_type": mtype,
        "measurement_type_raw": mtype_raw,
        "measurement_bucket": _bucket(mtype, config.known_measurement_types),
        "analysis_period": (str(cells.get("Analysis period")).strip()
                            if cells.get("Analysis period") is not None else None),
        "date_raw": cells.get("Date"),
        "date_resolved": dres.iso,
        "date_error": dres.error,
        "day_index": units.to_float(cells.get("Day")),
        "gd": (str(cells.get("GD")).strip() if cells.get("GD") is not None else None),
    }
    # day_index should be an int when integral.
    if out["day_index"] is not None and float(out["day_index"]).is_integer():
        out["day_index"] = int(out["day_index"])

    # Times (clock) + midnight crossing.
    start_v, end_v = cells.get("Start time (hh:min:sec)"), cells.get("End time (hh:min:sec)")
    sf, ef = units.time_to_fraction(start_v), units.time_to_fraction(end_v)
    out["start_time"] = units.time_to_str(start_v)
    out["end_time"] = units.time_to_str(end_v)
    out["start_fraction"] = sf
    out["end_fraction"] = ef
    out["crosses_midnight"] = bool(sf is not None and ef is not None and ef < sf)

    normalized: Dict[str, Optional[float]] = {}
    source: Dict[str, object] = {}

    # Duration-typed -> minutes.
    for header, key in schema.FULLDAY_DURATION_COLS.items():
        v = cells.get(header)
        normalized[key] = units.duration_to_minutes(v, formats.get(header))
        source[key + "_raw"] = _jsonable_source(v)

    # Numeric metrics.
    for header, key in schema.FULLDAY_NUMERIC_COLS.items():
        v = cells.get(header)
        normalized[key] = units.to_float(v)
        source[key + "_raw"] = _jsonable_source(v)

    # Percentages (format/context aware).
    percent_notes = {}
    for header, key in schema.FULLDAY_PERCENT_COLS.items():
        v = cells.get(header)
        pct, note = units.percent_from_cell(v, formats.get(header), header)
        normalized[key] = pct
        percent_notes[key] = note
        source[key + "_raw"] = _jsonable_source(v)

    # Source-reported (never treated as independently calculated).
    for header, key in schema.FULLDAY_SOURCE_REPORTED.items():
        v = cells.get(header)
        source[key] = _jsonable_source(v)

    out["normalized"] = normalized
    out["source"] = source
    out["percent_notes"] = percent_notes
    out["status"] = "included"      # may be downgraded by validation/duplicates
    out["status_reason"] = None
    out["duplicate_of"] = None
    out["override"] = None          # {"action": "include"|"exclude", "reason": str}
    out["flags"] = []               # flag ids attached later
    return out


def normalize_wellness(rec: RawRecord, config: Config, idmap: IdentityMap) -> dict:
    cells = rec.cells
    raw_label = cells.get("Performed By")
    norm_label = normalize_label(raw_label)
    athlete_id = idmap.get(norm_label)
    dres = resolve_date(cells.get("Date"), config)

    scores = {}
    for header, key in schema.WELLNESS_SCORE_COLS.items():
        scores[key] = units.to_float(cells.get(header))

    return {
        "record_id": rec.record_id,
        "provenance": {"file": rec.file, "sheet": rec.sheet, "excel_row": rec.excel_row},
        "athlete_id": athlete_id,
        "athlete_label": norm_label,
        "athlete_label_raw": raw_label,
        "date_raw": cells.get("Date"),
        "date_resolved": dres.iso,
        "date_error": dres.error,
        "scores": scores,
        "status": "included",
        "flags": [],
    }


def _jsonable_source(v):
    """Preserve a source value in a JSON-safe form (used inside 'source')."""
    import datetime as _dt
    if v is None:
        return None
    if isinstance(v, _dt.timedelta):
        return {"kind": "duration", "seconds": v.total_seconds()}
    if isinstance(v, _dt.time):
        return {"kind": "time", "text": units.time_to_str(v)}
    if isinstance(v, _dt.datetime):
        return {"kind": "datetime", "iso": v.isoformat()}
    if isinstance(v, _dt.date):
        return {"kind": "date", "iso": v.isoformat()}
    if isinstance(v, float):
        import math
        return v if math.isfinite(v) else None
    if isinstance(v, (int, str, bool)):
        return v
    return str(v)
