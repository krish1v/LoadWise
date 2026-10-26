"""Aggregation + validation behavior (criteria 1, 2, 11, 12, 13)."""

from __future__ import annotations

import pytest

from loadwise import Config, process_workbook
from conftest import row


CFG = lambda: Config(season_start_year=2025)


def _daily(res, athlete="A001", date="2025-09-11"):
    for d in res.daily_records:
        if d["athlete_id"] == athlete and d["date"] == date:
            return d
    return None


# --- #1: two sessions same athlete+day -> one daily record, correct totals. ---
def test_two_sessions_one_day_combined():
    fd = [
        row(**{"Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
               "High intensity training (hh:mm:ss)": 0.00347222222}),  # ~5 min
        row(**{"Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 20, "Movement load": 50,
               "High intensity training (hh:mm:ss)": 0.0}),
    ]
    import tempfile, os
    from conftest import build_workbook
    p = os.path.join(tempfile.mkdtemp(), "x.xlsx")
    build_workbook(p, fd, [])
    res = process_workbook(p, CFG())
    dailies = [d for d in res.daily_records if d["athlete_id"] == "A001"]
    assert len(dailies) == 1
    d = dailies[0]
    assert d["included_session_count"] == 2
    assert d["totals"]["trimp"]["value"] == pytest.approx(50.0)
    assert d["totals"]["movement_load"]["value"] == pytest.approx(150.0)
    assert d["totals"]["duration_min"]["value"] == pytest.approx(180.0)  # 90 + 90
    assert d["totals"]["trimp"]["completeness"] == "complete"


# --- #2: training/game/other breakdown reconciles to totals. ---
def test_training_game_split_reconciles(mk_workbook):
    fd = [
        row(**{"Measurement type": "Training", "Duration (hh:mm:ss)": 0.0625,
               "TRIMP (Index)": 30, "Movement load": 100,
               "High intensity training (hh:mm:ss)": 0.0}),
        row(**{"Measurement type": "Game", "Duration (hh:mm:ss)": 0.0625,
               "TRIMP (Index)": 40, "Movement load": 80,
               "High intensity training (hh:mm:ss)": 0.0}),
    ]
    res = process_workbook(mk_workbook(fd), CFG())
    d = _daily(res)
    assert d["totals"]["trimp"]["value"] == pytest.approx(70.0)
    assert d["breakdown"]["training"]["trimp"]["value"] == pytest.approx(30.0)
    assert d["breakdown"]["game"]["trimp"]["value"] == pytest.approx(40.0)
    assert all(d["breakdown_reconciles"].values())


# --- #11: partial sums report coverage; all-missing returns null. ---
def test_partial_and_all_missing_metrics(mk_workbook):
    fd = [
        # Session A has movement_load; session B does not -> partial sum.
        row(**{"Date": "12/09", "Day": 2, "TRIMP (Index)": 30, "Movement load": 100,
               "Duration (hh:mm:ss)": 0.0625, "High intensity training (hh:mm:ss)": 0.0}),
        row(**{"Date": "12/09", "Day": 2, "TRIMP (Index)": 20,
               "Duration (hh:mm:ss)": 0.0625, "High intensity training (hh:mm:ss)": 0.0}),
    ]
    res = process_workbook(mk_workbook(fd), CFG())
    d = _daily(res, date="2025-09-12")
    ml = d["totals"]["movement_load"]
    assert ml["value"] == pytest.approx(100.0)       # known part retained
    assert ml["completeness"] == "partial"
    assert ml["valid_sessions"] == 1 and ml["expected_sessions"] == 2
    # TRIMP present on both -> complete.
    assert d["totals"]["trimp"]["completeness"] == "complete"


def test_all_missing_metric_returns_null(mk_workbook):
    fd = [row(**{"TRIMP (Index)": 30, "Duration (hh:mm:ss)": 0.0625,
                 "High intensity training (hh:mm:ss)": 0.0})]  # no movement load
    res = process_workbook(mk_workbook(fd), CFG())
    d = _daily(res)
    assert d["totals"]["movement_load"]["value"] is None
    assert d["totals"]["movement_load"]["completeness"] == "missing"


# --- #12: an invalid field does not erase unrelated valid metrics. ---
def test_invalid_field_does_not_erase_others(mk_workbook):
    fd = [row(**{"TRIMP (Index)": 30, "Movement load": -50,  # invalid negative
                 "Duration (hh:mm:ss)": 0.0625, "High intensity training (hh:mm:ss)": 0.0})]
    res = process_workbook(mk_workbook(fd), CFG())
    rec = res.cleaned_records[0]
    assert rec["normalized"]["movement_load"] is None       # offending metric nulled
    assert rec["normalized"]["trimp"] == pytest.approx(30.0)  # valid metric kept
    assert rec["status"] == "included"                       # session not discarded
    codes = {f["rule_code"] for f in res.quality_flags}
    assert "NEGATIVE_METRIC" in codes


# --- #13: ratios use matching complete inputs; zero denominator is safe. ---
def test_efficiency_and_trimp_per_min_complete(mk_workbook):
    fd = [row(**{"TRIMP (Index)": 30, "Movement load": 150, "Duration (hh:mm:ss)": 0.0625,
                 "High intensity training (hh:mm:ss)": 0.0})]
    res = process_workbook(mk_workbook(fd), CFG())
    d = _daily(res)
    assert d["derived"]["efficiency_calculated"]["value"] == pytest.approx(150 / 30)
    assert d["derived"]["trimp_per_min_calculated"]["value"] == pytest.approx(30 / 90)


def test_zero_denominator_returns_null_with_reason(mk_workbook):
    fd = [row(**{"TRIMP (Index)": 0, "Movement load": 150, "Duration (hh:mm:ss)": 0.0625,
                 "High intensity training (hh:mm:ss)": 0.0})]
    res = process_workbook(mk_workbook(fd), CFG())
    d = _daily(res)
    eff = d["derived"]["efficiency_calculated"]
    assert eff["value"] is None and "denominator" in eff["reason"]


def test_ratio_null_when_inputs_not_complete(mk_workbook):
    # Movement load missing on one of two sessions -> efficiency not computed.
    fd = [
        row(**{"TRIMP (Index)": 30, "Movement load": 150, "Duration (hh:mm:ss)": 0.0625,
               "High intensity training (hh:mm:ss)": 0.0}),
        row(**{"TRIMP (Index)": 30, "Duration (hh:mm:ss)": 0.0625,
               "High intensity training (hh:mm:ss)": 0.0}),
    ]
    res = process_workbook(mk_workbook(fd), CFG())
    d = _daily(res)
    assert d["derived"]["efficiency_calculated"]["value"] is None
    assert "not complete" in d["derived"]["efficiency_calculated"]["reason"]


def test_avg_movement_intensity_has_no_daily_aggregate(mk_workbook):
    fd = [row(**{"TRIMP (Index)": 30, "Movement load": 150, "Average movement intensity": 0.9,
                 "Duration (hh:mm:ss)": 0.0625, "High intensity training (hh:mm:ss)": 0.0})]
    res = process_workbook(mk_workbook(fd), CFG())
    d = _daily(res)
    ami = d["derived"]["avg_movement_intensity"]
    assert ami["daily_value"] is None
    assert ami["session_values"][0]["value"] == pytest.approx(0.9)
