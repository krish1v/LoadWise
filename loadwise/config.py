"""Configuration for the LoadWise data layer.

Every threshold here is a *screening* threshold: crossing it produces a warning,
not a confirmed error. Values are deliberately conservative and all are
overridable by the caller / UI. Nothing in this module invents data.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

# Bumped whenever the shape of the exported JSON output contract changes.
SCHEMA_VERSION = "1.0.0"


@dataclass
class Thresholds:
    """Configurable, conservative plausibility-screening thresholds.

    These never reclassify a value as a hard error on their own -- they only
    raise warnings so a human can review plausible-but-unusual measurements.
    """

    # Session duration screening (minutes).
    min_duration_min: float = 1.0
    max_duration_min: float = 300.0

    # Heart-rate screening (bpm). Basketball players can briefly exceed 200.
    hr_min_bpm: float = 20.0
    hr_max_bpm: float = 230.0

    # Workload magnitude screening (arbitrary / index units).
    max_trimp: float = 1500.0
    max_movement_load: float = 100_000.0
    max_trimp_per_min: float = 20.0

    # Rounding tolerance when checking "high-intensity minutes <= duration".
    # Durations are stored at second resolution; 1 minute of slack absorbs
    # rounding without masking genuine inconsistencies.
    hit_tolerance_min: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Config:
    """Top-level processing configuration.

    season_start_year is the calendar year that the *September* records belong
    to. January records roll over to season_start_year + 1. It is intentionally
    Optional and has no default: the pipeline refuses to invent a year.
    """

    season_start_year: Optional[int] = None

    # Months (1-12) whose records belong to ``season_start_year``. Every other
    # month rolls over to ``season_start_year + 1``. The supplied workbook runs
    # Sep->Jan, so Sep-Dec stay in the start year and Jan-Aug roll over.
    start_year_months: tuple = (9, 10, 11, 12)

    thresholds: Thresholds = field(default_factory=Thresholds)

    # Measurement types we understand. Anything else is kept but flagged and
    # bucketed as "other" in aggregation.
    known_measurement_types: tuple = ("Training", "Game")

    # Analysis-period value(s) we expect for individual measurements.
    expected_analysis_periods: tuple = ("Measurement",)

    # When True, exact-duplicate copies are excluded from totals by default
    # (one canonical record is retained). Distinct possible duplicates are
    # always kept included until a human reviews them.
    exclude_exact_duplicates: bool = True

    # Overlap fraction (0..1) of two same-athlete/same-day sessions' time
    # windows above which they are flagged as a *possible* duplicate/overlap.
    overlap_warn_fraction: float = 0.5

    def rollover_year(self, month: int) -> Optional[int]:
        """Return the resolved calendar year for a given month, or None."""
        if self.season_start_year is None:
            return None
        return self.season_start_year if month in self.start_year_months else self.season_start_year + 1

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict already recursed into Thresholds; make tuples JSON-friendly.
        d["start_year_months"] = list(self.start_year_months)
        d["known_measurement_types"] = list(self.known_measurement_types)
        d["expected_analysis_periods"] = list(self.expected_analysis_periods)
        return d
