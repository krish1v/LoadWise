"""Integration smoke test against the supplied workbook (criterion-wide).

Skips automatically if the real workbook is not present, so the suite still runs
anywhere. The season year used here is the one configured for this project.
"""

from __future__ import annotations

import json
import os

import pytest

from loadwise import Config, process_workbook
from conftest import REAL_WORKBOOK

pytestmark = pytest.mark.skipif(not os.path.exists(REAL_WORKBOOK),
                                reason="supplied workbook not present")

SEASON_YEAR = 2025  # 2025-26 season, as configured for this project


@pytest.fixture(scope="module")
def result():
    return process_workbook(REAL_WORKBOOK, Config(season_start_year=SEASON_YEAR))


def test_record_and_athlete_counts(result):
    s = result.output["summary"]
    assert s["full_day_records"] == 1260
    assert s["athletes"] == 15
    assert s["wellness_records"] == 11


def test_date_range_resolves_sep_to_jan(result):
    s = result.output["summary"]
    assert s["date_range"]["first"] == "2025-09-11"
    assert s["date_range"]["last"] == "2026-01-09"


def test_multi_session_days_collapse(result):
    multi = [d for d in result.daily_records if d["included_session_count"] > 1]
    assert len(multi) == 142  # observed training+game / double-practice days


def test_all_breakdowns_reconcile(result):
    for d in result.daily_records:
        assert all(d["breakdown_reconciles"].values()), d["daily_id"]


def test_game_records_have_no_movement_load_surface_as_partial(result):
    # Game-only days should have movement_load missing/partial, not fabricated 0.
    game_only = [d for d in result.daily_records
                 if d["schedule_context"]["has_game"]
                 and d["breakdown"]["training"]["trimp"]["expected_sessions"] == 0]
    assert game_only, "expected at least one game-only day"
    assert any(d["totals"]["movement_load"]["completeness"] in ("missing", "partial")
               for d in game_only)


def test_output_is_strict_json(result):
    js = result.to_json()
    parsed = json.loads(js)
    assert parsed["schemaVersion"]
    assert len(parsed["dailyRecords"]) == len(result.daily_records)


def test_real_workbook_idempotent():
    a = process_workbook(REAL_WORKBOOK, Config(season_start_year=SEASON_YEAR)).to_json()
    b = process_workbook(REAL_WORKBOOK, Config(season_start_year=SEASON_YEAR)).to_json()
    assert a == b
