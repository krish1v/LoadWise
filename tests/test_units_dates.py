"""Units and date-resolution edge cases (acceptance criteria 3, 4, 5, 10)."""

from __future__ import annotations

import datetime as _dt

import pytest

from loadwise import Config
from loadwise.dates import resolve_date, rollover_preview
from loadwise import units


# --- #3: Excel duration fraction 0.0625 -> 90 minutes. ---
def test_duration_fraction_0_0625_is_90_minutes():
    assert units.duration_to_minutes(0.0625) == 90.0


def test_duration_handles_timedelta_time_and_string():
    assert units.duration_to_minutes(_dt.timedelta(seconds=11560)) == pytest.approx(192.6667, abs=1e-3)
    assert units.duration_to_minutes(_dt.time(1, 30, 0)) == 90.0
    assert units.duration_to_minutes("01:30:00") == 90.0
    assert units.duration_to_minutes("01:30") == 90.0
    assert units.duration_to_minutes(None) is None
    assert units.duration_to_minutes("") is None


# --- #10: missing is distinct from a valid zero. ---
def test_zero_preserved_missing_is_none():
    assert units.to_float(0) == 0.0
    assert units.to_float(0.0) == 0.0
    assert units.to_float(None) is None
    assert units.to_float("") is None
    assert units.to_float(float("nan")) is None
    assert units.to_float(float("inf")) is None
    assert units.duration_to_minutes(0.0) == 0.0  # valid zero duration, not missing


def test_percent_interpretation_uses_format_then_context():
    # Stored fraction with % format -> percentage points.
    v, note = units.percent_from_cell(0.0213, "0.00\\ %", "Measurement error (%)")
    assert v == pytest.approx(2.13, abs=1e-6)
    assert note == "fraction_format_x100"
    # No % format but (%) header + small magnitude -> treated as fraction.
    v, note = units.percent_from_cell(0.42, "General", "Average %HRmax (%)")
    assert v == pytest.approx(42.0)
    assert note == "context_fraction_x100"
    # No % format, large magnitude -> already percentage points.
    v, note = units.percent_from_cell(42.0, "General", "Something (%)")
    assert v == 42.0
    assert note == "assumed_percentage_points"


# --- #4: day/month resolution incl. Dec->Jan rollover with configured year. ---
def test_day_month_rollover_with_season_year():
    cfg = Config(season_start_year=2025)
    assert resolve_date("11/09", cfg).iso == "2025-09-11"   # September -> start year
    assert resolve_date("31/12", cfg).iso == "2025-12-31"   # December -> start year
    assert resolve_date("09/01", cfg).iso == "2026-01-09"   # January -> rolls over
    assert resolve_date("01/08", cfg).iso == "2026-08-01"   # Aug -> next year side


def test_rollover_preview_shows_mapping():
    cfg = Config(season_start_year=2025)
    prev = rollover_preview(cfg)
    by_month = {p["month"]: p["year"] for p in prev}
    assert by_month[9] == 2025 and by_month[12] == 2025
    assert by_month[1] == 2026
    # Preview is empty when year unknown (nothing invented).
    assert rollover_preview(Config(season_start_year=None)) == []


# --- #5: missing year config -> actionable, not an invented year. ---
def test_missing_year_does_not_invent():
    cfg = Config(season_start_year=None)
    r = resolve_date("11/09", cfg)
    assert r.resolved is None
    assert r.error == "season_year_not_configured"


def test_unparseable_and_invalid_dates():
    cfg = Config(season_start_year=2025)
    assert resolve_date("not-a-date", cfg).error.startswith("unparseable_date")
    assert resolve_date("45/09", cfg).error.startswith("invalid_day")
    assert resolve_date("11/13", cfg).error.startswith("invalid_month")
    assert resolve_date(None, cfg).error == "missing_date"
