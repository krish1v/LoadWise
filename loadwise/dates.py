"""Date resolution for yearless day/month source dates.

The workbook stores dates as text like ``11/09`` (day/month) with no year,
running September into January. Resolution requires an explicitly configured
season start year -- we NEVER default to the current year and NEVER silently
invent one. We also expose the inferred month->year rollover for human review
and flag ordering inconsistencies rather than guessing.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import List, Optional, Tuple

from .config import Config

_DM = re.compile(r"^\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*$")


class DateResolution:
    """Result of resolving one raw date value."""

    __slots__ = ("raw", "resolved", "day", "month", "year", "error")

    def __init__(self, raw, resolved=None, day=None, month=None, year=None, error=None):
        self.raw = raw
        self.resolved = resolved  # datetime.date or None
        self.day = day
        self.month = month
        self.year = year
        self.error = error  # str reason or None

    @property
    def iso(self) -> Optional[str]:
        return self.resolved.isoformat() if self.resolved else None


def parse_day_month(raw) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Parse a raw date into (day, month, error).

    Accepts the workbook's text 'd/m', and also real date/datetime objects and
    Excel serials already converted by openpyxl.
    """
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, None, "missing_date"
    if isinstance(raw, _dt.datetime):
        return raw.day, raw.month, None
    if isinstance(raw, _dt.date):
        return raw.day, raw.month, None
    s = str(raw).strip()
    m = _DM.match(s)
    if not m:
        return None, None, f"unparseable_date:{s!r}"
    day, month = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12):
        return None, None, f"invalid_month:{month}"
    if not (1 <= day <= 31):
        return None, None, f"invalid_day:{day}"
    return day, month, None


def resolve_date(raw, config: Config) -> DateResolution:
    """Resolve one raw day/month value using the configured season year."""
    day, month, err = parse_day_month(raw)
    if err:
        return DateResolution(raw, error=err)
    # Real date/datetime already carries a year -> trust it.
    if isinstance(raw, _dt.date) and not isinstance(raw, _dt.datetime):
        return DateResolution(raw, resolved=raw, day=day, month=month, year=raw.year)
    if isinstance(raw, _dt.datetime):
        d = raw.date()
        return DateResolution(raw, resolved=d, day=day, month=month, year=d.year)
    year = config.rollover_year(month)
    if year is None:
        return DateResolution(raw, day=day, month=month, error="season_year_not_configured")
    try:
        d = _dt.date(year, month, day)
    except ValueError as e:
        return DateResolution(raw, day=day, month=month, year=year, error=f"invalid_date:{e}")
    return DateResolution(raw, resolved=d, day=day, month=month, year=year)


def rollover_preview(config: Config) -> List[dict]:
    """Return the month->year mapping implied by the config, for human review.

    Lists the season's months in chronological order (Sep..Dec of the start
    year, then Jan..Aug of the next year) so the user can confirm the rollover
    before processing.
    """
    if config.season_start_year is None:
        return []
    order = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
    names = ["", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]
    out = []
    for mo in order:
        yr = config.rollover_year(mo)
        out.append({"month": mo, "month_name": names[mo], "year": yr,
                    "in_start_year": mo in config.start_year_months})
    return out


def check_day_index_consistency(resolved_rows: List[dict]) -> List[dict]:
    """Flag records whose resolved date ordering disagrees with the study-day index.

    ``resolved_rows`` is a list of dicts with keys: record_id, date (date|None),
    day_index (int|None), excel_row. We check that, across records, a larger
    study-day index corresponds to a non-earlier calendar date. Inconsistencies
    are returned (we flag, we do not silently re-assign years).
    """
    usable = [r for r in resolved_rows if r.get("date") is not None and r.get("day_index") is not None]
    # Reference mapping: for each day_index, the set of dates seen.
    by_index = {}
    for r in usable:
        by_index.setdefault(r["day_index"], set()).add(r["date"])

    issues: List[dict] = []
    # 1) A single study-day index mapping to multiple distinct calendar dates.
    for idx, dates in by_index.items():
        if len(dates) > 1:
            for r in usable:
                if r["day_index"] == idx:
                    issues.append({
                        "record_id": r["record_id"],
                        "excel_row": r.get("excel_row"),
                        "reason": "day_index_maps_to_multiple_dates",
                        "day_index": idx,
                        "dates": sorted(d.isoformat() for d in dates),
                    })
    # 2) Monotonicity: sort by day_index, dates should be non-decreasing.
    ordered = sorted(((idx, min(ds)) for idx, ds in by_index.items()), key=lambda t: t[0])
    prev_idx, prev_date = None, None
    for idx, d in ordered:
        if prev_date is not None and d < prev_date:
            issues.append({
                "record_id": None,
                "excel_row": None,
                "reason": "date_decreases_as_day_index_increases",
                "day_index": idx,
                "date": d.isoformat(),
                "previous_day_index": prev_idx,
                "previous_date": prev_date.isoformat(),
            })
        prev_idx, prev_date = idx, d
    return issues
