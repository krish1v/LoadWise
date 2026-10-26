"""Unit normalization helpers.

Durations -> minutes; percentages interpreted via cell formatting + column
context; numeric coercion that preserves valid zeros and uses None for missing.
No timezone math is ever applied (we only ever touch local wall-clock values).
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from typing import Optional, Tuple


def is_missing(value) -> bool:
    """True for values that should become null (None, blank, NaN)."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def to_float(value) -> Optional[float]:
    """Coerce to a finite float. Preserves 0.0; returns None for missing/invalid.

    Non-finite values (inf/-inf/nan) return None so they can be flagged and kept
    out of JSON (which has no Infinity).
    """
    if is_missing(value):
        return None
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        try:
            f = float(s)
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


_HHMMSS = re.compile(r"^\s*(\d+):([0-5]?\d):([0-5]?\d)(?:\.\d+)?\s*$")
_HHMM = re.compile(r"^\s*(\d+):([0-5]?\d)\s*$")


def duration_to_minutes(value, number_format: Optional[str] = None) -> Optional[float]:
    """Convert a duration cell to minutes at full precision.

    Handles every representation the workbook (or a synthetic fixture) can use:
      * ``datetime.timedelta``                  -> total_seconds / 60
      * ``datetime.time``                       -> h*60 + m + s/60 (clock as elapsed)
      * numeric Excel day-fraction (e.g. 0.0625)-> x 1440  (0.0625 -> 90.0)
      * ``"hh:mm:ss"`` / ``"hh:mm"`` strings    -> parsed
    Returns None for missing/unparseable values.
    """
    if is_missing(value):
        return None
    if isinstance(value, _dt.timedelta):
        return value.total_seconds() / 60.0
    if isinstance(value, _dt.time):
        return value.hour * 60.0 + value.minute + value.second / 60.0 + value.microsecond / 60_000_000.0
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if not math.isfinite(f):
            return None
        # Excel stores durations as a fraction of a day.
        return f * 1440.0
    if isinstance(value, str):
        s = value.strip()
        m = _HHMMSS.match(s)
        if m:
            h, mi, se = (int(g) for g in m.groups())
            return h * 60.0 + mi + se / 60.0
        m = _HHMM.match(s)
        if m:
            h, mi = (int(g) for g in m.groups())
            return h * 60.0 + mi
        f = to_float(s)
        return f * 1440.0 if f is not None else None
    return None


def time_to_fraction(value) -> Optional[float]:
    """Return a clock time as a fraction of a day in [0,1), else None.

    Used for same-day overlap arithmetic between sessions.
    """
    if is_missing(value):
        return None
    if isinstance(value, _dt.time):
        return (value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1e6) / 86400.0
    if isinstance(value, _dt.datetime):
        t = value.time()
        return (t.hour * 3600 + t.minute * 60 + t.second) / 86400.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        f = float(value)
        if math.isfinite(f):
            return f - math.floor(f)  # keep only the time-of-day fraction
    if isinstance(value, str):
        m = _HHMMSS.match(value) or _HHMM.match(value)
        if m:
            g = [int(x) for x in m.groups()]
            h, mi = g[0], g[1]
            se = g[2] if len(g) > 2 else 0
            return (h * 3600 + mi * 60 + se) / 86400.0
    return None


def time_to_str(value) -> Optional[str]:
    """Render a clock time as 'HH:MM:SS' for JSON, else None."""
    frac = time_to_fraction(value)
    if frac is None:
        return None
    total = int(round(frac * 86400)) % 86400
    h, rem = divmod(total, 3600)
    mi, se = divmod(rem, 60)
    return f"{h:02d}:{mi:02d}:{se:02d}"


def percent_from_cell(value, number_format: Optional[str], header: str) -> Tuple[Optional[float], str]:
    """Interpret a percentage cell into percentage points.

    Uses the cell's number format first, then column context -- never a single
    blanket rule. Returns (percent_points, interpretation_note).
    """
    f = to_float(value)
    if f is None:
        return None, "missing"
    fmt = (number_format or "").lower()
    if "%" in fmt:
        # Stored as a fraction (Excel multiplies by 100 for display).
        return f * 100.0, "fraction_format_x100"
    # No percent format: rely on column context + magnitude.
    if "(%)" in (header or "") and -1.5 <= f <= 1.5:
        # Looks like a stored fraction even without % formatting.
        return f * 100.0, "context_fraction_x100"
    # Otherwise assume the number is already in percentage points.
    return f, "assumed_percentage_points"
