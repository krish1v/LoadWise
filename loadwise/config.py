"""Configuration, screening thresholds and the library's user-facing errors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

SCHEMA_VERSION = "1.0.0"


class LoadWiseInputError(Exception):
    """The input cannot be processed. `str(err)` is a user-facing, actionable message."""


class SeasonYearRequired(LoadWiseInputError):
    """Yearless day/month dates were found but no season start year was configured."""

    def __init__(self, sample: Optional[list] = None):
        self.sample = sample or []
        hint = f" (e.g. {', '.join(map(str, self.sample[:3]))})" if self.sample else ""
        super().__init__(
            "The workbook stores dates without a year" + hint + ". Set the season start "
            "year (e.g. 2025 for a 2025–26 season) so September–December resolve to that "
            "year and January onwards to the next. LoadWise never guesses the year."
        )


@dataclass(frozen=True)
class Thresholds:
    """Conservative screening limits. Breaching one produces a *warning*, not an error."""

    max_session_minutes: float = 300.0     # > 5 h for one recorded session is unusual
    min_session_minutes: float = 1.0       # < 1 min is probably an accidental recording
    hr_min_bpm: float = 30.0
    hr_max_bpm: float = 230.0
    hit_tolerance_minutes: float = 0.5     # HIT may exceed duration by this much (rounding)
    time_duration_tolerance_minutes: float = 2.0  # clock span vs duration column
    overlap_fraction: float = 0.5          # overlap share that marks a possible duplicate


@dataclass(frozen=True)
class Config:
    season_start_year: Optional[int] = None
    rollover_month: int = 7                # months >= this belong to season_start_year
    known_measurement_types: tuple = ("Training", "Game")
    thresholds: Thresholds = field(default_factory=Thresholds)

    def year_for_month(self, month: int) -> int:
        if self.season_start_year is None:
            raise SeasonYearRequired()
        return self.season_start_year if month >= self.rollover_month else self.season_start_year + 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["known_measurement_types"] = list(self.known_measurement_types)
        d["date_resolution"] = (
            "Yearless day/month dates: month >= rollover_month -> season_start_year, "
            "otherwise season_start_year + 1. Real Excel dates and serials are used as recorded "
            "(workbook epoch respected). No timezone conversion."
        )
        return d
