"""Units, date resolution and standardized (normalized) records.

Every normalized record keeps the source values next to the normalized ones and
carries file/sheet/Excel-row provenance. `None` means missing or unusable; zero
is a valid value and is never turned into None (or vice versa).
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Dict, List, Optional, Tuple

from openpyxl.utils.datetime import from_excel

from .config import Config
from .ingest import (FULL_DAY_COLUMNS, WELLNESS_COLUMNS, RawRecord, SheetResult, athlete_id,
                     normalize_label)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ------------------------------------------------------------------- units --


def is_missing(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "") or (
        isinstance(v, float) and math.isnan(v))


_NUM_RE = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?$")


def to_number(v) -> Tuple[Optional[float], Optional[str]]:
    """-> (value, problem). problem ∈ {None, 'missing', 'non_numeric', 'non_finite'}."""
    if is_missing(v):
        return None, "missing"
    if isinstance(v, bool):
        return None, "non_numeric"
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str) and _NUM_RE.match(v.strip()):
        f = float(v.strip().replace(",", "."))
    elif isinstance(v, str) and v.strip().lower() in ("inf", "-inf", "infinity", "nan"):
        return None, "non_finite"
    else:
        return None, "non_numeric"
    if not math.isfinite(f):
        return None, "non_finite"
    return f, None


_DUR_RE = re.compile(r"^(-)?(\d+):(\d{1,2})(?::(\d{1,2}(?:\.\d+)?))?$")


def duration_to_minutes(v) -> Tuple[Optional[float], Optional[str]]:
    """Excel day fraction (x1440), timedelta, time, or 'h:mm[:ss]' string -> minutes."""
    if is_missing(v):
        return None, "missing"
    if isinstance(v, dt.timedelta):
        return v.total_seconds() / 60.0, None
    if isinstance(v, dt.time):
        return v.hour * 60 + v.minute + (v.second + v.microsecond / 1e6) / 60.0, None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if not math.isfinite(float(v)):
            return None, "non_finite"
        return float(v) * 1440.0, None
    if isinstance(v, str):
        m = _DUR_RE.match(v.strip())
        if m:
            sign = -1 if m.group(1) else 1
            h, mi = int(m.group(2)), int(m.group(3))
            s = float(m.group(4)) if m.group(4) else 0.0
            return sign * (h * 60 + mi + s / 60.0), None
        num, prob = to_number(v)
        if num is not None:
            return num * 1440.0, None
        return None, prob or "non_numeric"
    return None, "non_numeric"


def clock_minutes(v) -> Optional[float]:
    """Time-of-day -> minutes after midnight (None if not a recognisable clock time)."""
    if isinstance(v, dt.datetime):
        v = v.time()
    if isinstance(v, dt.time):
        return v.hour * 60 + v.minute + v.second / 60.0
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < 1:
        return float(v) * 1440.0
    if isinstance(v, str):
        m = _DUR_RE.match(v.strip())
        if m and not m.group(1) and int(m.group(2)) < 24:
            return int(m.group(2)) * 60 + int(m.group(3)) + (float(m.group(4) or 0) / 60.0)
    return None


def clock_str(v) -> Optional[str]:
    m = clock_minutes(v)
    if m is None:
        return None
    secs = int(round(m * 60))
    return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"


def percent(v, number_format: str, header: str) -> Tuple[Optional[float], str]:
    """Interpret a percentage using the cell format and column context -> percent points."""
    num, _ = to_number(v)
    if num is None:
        return None, "missing_or_invalid"
    if "%" in (number_format or ""):
        return num * 100.0, "cell_formatted_as_percent: stored fraction x 100"
    if "%" in header:
        return num, "header_says_percent_cell_not_percent_formatted: stored value used as percent"
    return num, "no_percent_context: stored value used as is"


# ------------------------------------------------------------------- dates --

_DM_RE = re.compile(r"^(\d{1,2})[./-](\d{1,2})\.?$")
_DMY_RE = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$")
_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")


def is_yearless(v) -> bool:
    return isinstance(v, str) and bool(_DM_RE.match(v.strip()))


def resolve_date(v, config: Config, epoch=None) -> Dict[str, Optional[str]]:
    """-> {iso, method, error}. Never invents a year (requires config.season_start_year)."""
    out = {"iso": None, "method": None, "error": None}
    if is_missing(v):
        out["error"] = "missing_date"
        return out
    try:
        if isinstance(v, dt.datetime):
            out.update(iso=v.date().isoformat(), method="excel_date")
        elif isinstance(v, dt.date):
            out.update(iso=v.isoformat(), method="excel_date")
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            d = from_excel(v, epoch) if epoch is not None else from_excel(v)
            out.update(iso=(d.date() if isinstance(d, dt.datetime) else d).isoformat(),
                       method="excel_serial")
        elif isinstance(v, str):
            s = v.strip()
            if m := _DM_RE.match(s):
                day, month = int(m.group(1)), int(m.group(2))
                if config.season_start_year is None:
                    out["error"] = "season_year_required"
                    return out
                year = config.year_for_month(month) if 1 <= month <= 12 else 0
                out.update(iso=dt.date(year, month, day).isoformat(), method="day_month_plus_season_year")
            elif m := _DMY_RE.match(s):
                out.update(iso=dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat(),
                           method="day_month_year_text")
            elif m := _ISO_RE.match(s):
                out.update(iso=dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat(),
                           method="iso_text")
            else:
                out["error"] = "unparseable_date"
        else:
            out["error"] = "unparseable_date"
    except (ValueError, OverflowError):
        out.update(iso=None, method=None, error="invalid_calendar_date")
    return out


def rollover_preview(raw_dates: List[object], config: Config) -> List[dict]:
    """Per month (in season order): which year a yearless day/month date will get."""
    counts: Dict[int, List[str]] = {}
    for v in raw_dates:
        if is_yearless(v):
            month = int(_DM_RE.match(v.strip()).group(2))
            if 1 <= month <= 12:
                counts.setdefault(month, []).append(v.strip())
    rows = []
    for month in sorted(counts, key=lambda m: (m < config.rollover_month, m)):
        vals = counts[month]
        rows.append({
            "month": month, "month_name": MONTHS[month - 1], "records": len(vals),
            "example": vals[0],
            "resolved_year": (config.year_for_month(month) if config.season_start_year else None),
        })
    return rows


# -------------------------------------------------------- normalized records --

PRIMARY_METRICS = ("duration_min", "trimp", "movement_load", "hit_min")


def _bucket(mtype: Optional[str], config: Config) -> str:
    if mtype is None:
        return "other"
    for known in config.known_measurement_types:
        if mtype.strip().casefold() == known.casefold():
            return known.casefold()
    return "other"


def _jsonable(v):
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return {"timedelta_seconds": v.total_seconds()}
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    return v


def _get(rec: RawRecord, mapping: dict, key: str):
    h = mapping.get(key)
    return (rec.cells.get(h), rec.formats.get(h, "General"), h) if h else (None, "General", None)


def normalize_session(rec: RawRecord, mapping: dict, config: Config, epoch) -> dict:
    g = lambda k: _get(rec, mapping, k)[0]
    problems: Dict[str, str] = {}
    label_raw = g("athlete")
    label = normalize_label(label_raw)
    date = resolve_date(g("date"), config, epoch)
    mtype = normalize_label(g("measurement_type"))

    metrics: Dict[str, Optional[float]] = {}
    for key, src in (("duration_min", "duration"), ("hit_min", "hit")):
        if mapping.get(src) is None:
            metrics[key] = None
            problems[key] = "column_unavailable"
            continue
        val, prob = duration_to_minutes(g(src))
        metrics[key] = val
        if prob:
            problems[key] = prob
    for key in ("trimp", "movement_load"):
        if mapping.get(key) is None:
            metrics[key] = None
            problems[key] = "column_unavailable"
            continue
        val, prob = to_number(g(key))
        metrics[key] = val
        if prob:
            problems[key] = prob

    def num(key):
        val, prob = to_number(g(key))
        if prob and prob != "missing":
            problems[key] = prob
        return val

    start_raw, end_raw = g("start_time"), g("end_time")
    s_min, e_min = clock_minutes(start_raw), clock_minutes(end_raw)
    crosses = s_min is not None and e_min is not None and e_min < s_min
    span = None if s_min is None or e_min is None else (e_min - s_min + (1440 if crosses else 0))

    err_v, err_fmt, err_h = _get(rec, mapping, "measurement_error")
    err_pct, err_interp = percent(err_v, err_fmt, err_h or "%")

    study_day, _ = to_number(g("study_day_index"))
    source_values = {}
    for key, header in mapping.items():
        if header is not None:
            source_values[key] = _jsonable(rec.cells.get(header))

    return {
        "record_id": rec.record_id,
        "import_id": rec.import_id,
        "provenance": {"file": rec.file, "sheet": rec.sheet, "excel_row": rec.excel_row},
        "athlete_id": athlete_id(label),
        "athlete_label": label,
        "date": date["iso"],
        "date_method": date["method"],
        "date_error": date["error"],
        "study_day_index": int(study_day) if study_day is not None and study_day == int(study_day) else study_day,
        "measurement_type": mtype,
        "session_bucket": _bucket(mtype, config),
        "analysis_period": normalize_label(g("analysis_period")),
        "gd": normalize_label(g("gd")),
        "start_time": clock_str(start_raw),
        "end_time": clock_str(end_raw),
        "crosses_midnight": crosses,
        "clock_span_min": span,
        "metrics": metrics,
        "source_ratios": {
            "trimp_per_min": num("trimp_per_min"),
            "avg_movement_intensity": num("avg_movement_intensity"),
        },
        "measurement_error_pct": err_pct,
        "measurement_error_interpretation": err_interp,
        "heart_rate": {"avg_bpm": num("hr_avg"), "min_bpm": num("hr_min"), "peak_bpm": num("hr_peak")},
        "source_reported": {
            "acute_training_load": num("source_acute_load"),
            "chronic_training_load": num("source_chronic_load"),
            "acwr": num("source_acwr"),
            "_note": "As reported by the source system; not calculated or verified by LoadWise.",
        },
        "source_values": source_values,
        "parse_problems": problems,
        "status": "included",
        "status_reason": None,
        "duplicate_of": None,
        "override": None,
        "flag_ids": [],
    }


WELLNESS_FIELDS = ("fatigue", "sleep_quality", "sleep_time", "soreness", "stress", "wellness_score")


def normalize_wellness(rec: RawRecord, mapping: dict, config: Config, epoch) -> dict:
    g = lambda k: _get(rec, mapping, k)[0]
    label = normalize_label(g("athlete"))
    date = resolve_date(g("date"), config, epoch)
    values, problems = {}, {}
    for key in WELLNESS_FIELDS:
        if mapping.get(key) is None:
            values[key] = None
            continue
        val, prob = to_number(g(key))
        values[key] = val
        if prob and prob != "missing":
            problems[key] = prob
    return {
        "record_id": rec.record_id,
        "import_id": rec.import_id,
        "provenance": {"file": rec.file, "sheet": rec.sheet, "excel_row": rec.excel_row},
        "athlete_id": athlete_id(label),
        "athlete_label": label,
        "date": date["iso"],
        "date_method": date["method"],
        "date_error": date["error"],
        "values": values,
        "values_note": "Source scale, direction and units unknown; values are as recorded.",
        "source_values": {k: _jsonable(rec.cells.get(h)) for k, h in mapping.items() if h},
        "parse_problems": problems,
        "status": "included",
        "status_reason": None,
        "flag_ids": [],
    }


def normalize_sheet(sheet: SheetResult, kind: str, config: Config, epoch) -> List[dict]:
    fn = normalize_session if kind == "session" else normalize_wellness
    return [fn(r, sheet.mapping, config, epoch) for r in sheet.records]


__all__ = ["duration_to_minutes", "percent", "resolve_date", "rollover_preview", "to_number",
           "normalize_sheet", "PRIMARY_METRICS", "WELLNESS_FIELDS", "FULL_DAY_COLUMNS",
           "WELLNESS_COLUMNS", "is_yearless", "clock_str"]
