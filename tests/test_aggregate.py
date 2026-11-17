"""Daily aggregation (criteria 1, 2, 10, 11, 12, 13) — synthetic fixtures."""

import datetime as dt

import pytest

from loadwise import process_workbook
from conftest import build_workbook, session, wellness

AM = dict(start=dt.time(9, 0), end=dt.time(10, 30))
PM = dict(start=dt.time(19, 0), end=dt.time(20, 30))


def _day(res, idx=0):
    return res.daily_records[idx]


# 1. Two sessions on one day -> one record with correct totals
def test_two_sessions_one_daily_record(cfg):
    res = process_workbook(build_workbook([session(trimp=100, ml=200, **AM),
                                           session(trimp=150, ml=300, **PM)]), cfg)
    assert len(res.daily_records) == 1
    d = _day(res)
    assert d["session_count"] == 2
    assert d["totals"]["trimp"]["value"] == 250
    assert d["totals"]["movement_load"]["value"] == 500
    assert d["totals"]["duration_min"]["value"] == pytest.approx(180)
    assert d["totals"]["hit_min"]["value"] == pytest.approx(10)
    assert len(d["source_record_ids"]) == 2


# 2. Training/game splits reconcile with totals
def test_training_game_split_reconciles(cfg):
    res = process_workbook(build_workbook([session(trimp=100, **AM),
                                           session(mtype="Game", trimp=300, gd="GD", **PM)]), cfg)
    d = _day(res)
    assert d["breakdown"]["training"]["trimp"]["value"] == 100
    assert d["breakdown"]["game"]["trimp"]["value"] == 300
    assert d["breakdown"]["other"]["trimp"]["completeness"] == "no_sessions"
    assert all(d["reconciles"].values())
    assert d["schedule"]["has_game_session"] and d["schedule"]["gd_labels"] == ["GD"]


def test_unknown_type_goes_to_other_and_still_reconciles(cfg):
    res = process_workbook(build_workbook([session(**AM), session(mtype="Recovery", **PM)]), cfg)
    d = _day(res)
    assert d["breakdown"]["other"]["trimp"]["value"] == 100
    assert all(d["reconciles"].values())
    assert any(f["rule_code"] == "UNEXPECTED_MEASUREMENT_TYPE" for f in res.quality_flags)


# 10. Missing stays distinct from a valid zero
def test_zero_is_not_missing(cfg):
    res = process_workbook(build_workbook([session(ml=0, hit=None)]), cfg)
    t = _day(res)["totals"]
    assert t["movement_load"]["value"] == 0 and t["movement_load"]["completeness"] == "complete"
    assert t["hit_min"]["value"] is None and t["hit_min"]["completeness"] == "missing"


# 11. Partial sums report coverage; all-missing -> null
def test_partial_and_all_missing(cfg):
    res = process_workbook(build_workbook([session(ml=200, hit=None, **AM),
                                           session(mtype="Game", ml=None, hit=None, **PM)]), cfg)
    t = _day(res)["totals"]
    assert t["movement_load"] == {"value": 200, "valid_sessions": 1, "expected_sessions": 2,
                                  "completeness": "partial"}
    assert t["hit_min"]["value"] is None and t["hit_min"]["completeness"] == "missing"
    assert "movement_load" in _day(res)["quality"]["incomplete_metrics"]


# 12. An invalid field does not erase unrelated valid metrics
def test_invalid_trimp_keeps_movement_load(cfg):
    res = process_workbook(build_workbook([session(trimp="error", ml=321)]), cfg)
    rec = res.cleaned_records[0]
    assert rec["status"] == "included"
    assert rec["metrics"]["trimp"] is None and rec["metrics"]["movement_load"] == 321
    assert _day(res)["totals"]["movement_load"]["value"] == 321
    assert any(f["rule_code"] == "NON_NUMERIC_VALUE" and f["field"] == "trimp"
               for f in res.quality_flags)


def test_negative_metric_nulled_and_flagged_as_error(cfg):
    res = process_workbook(build_workbook([session(trimp=-5, ml=50)]), cfg)
    assert res.cleaned_records[0]["metrics"]["trimp"] is None
    assert res.cleaned_records[0]["metrics"]["movement_load"] == 50
    assert any(f["rule_code"] == "NEGATIVE_METRIC" and f["severity"] == "error"
               for f in res.quality_flags)


# 13. Ratios use matching complete inputs and handle zero denominators
def test_ratios_from_complete_totals_not_averaged(cfg):
    res = process_workbook(build_workbook([session(trimp=100, ml=300, duration=0.0625, **AM),
                                           session(trimp=50, ml=50, duration=1 / 48, **PM)]), cfg)
    der = _day(res)["derived"]
    assert der["efficiency"]["value"] == pytest.approx(350 / 150)     # not mean(3.0, 1.0) = 2.0
    assert der["trimp_per_min"]["value"] == pytest.approx(150 / 120)


def test_ratio_null_when_inputs_partial(cfg):
    res = process_workbook(build_workbook([session(ml=200, **AM), session(ml=None, **PM)]), cfg)
    eff = _day(res)["derived"]["efficiency"]
    assert eff["value"] is None and "not both complete" in eff["reason"]


def test_ratio_zero_denominator(cfg):
    res = process_workbook(build_workbook([session(trimp=0, ml=10, duration=0)]), cfg)
    der = _day(res)["derived"]
    assert der["efficiency"]["value"] is None and "zero" in der["efficiency"]["reason"]
    assert der["trimp_per_min"]["value"] is None


def test_avg_movement_intensity_not_aggregated(cfg):
    res = process_workbook(build_workbook([session(**AM), session(**PM)]), cfg)
    ami = _day(res)["avg_movement_intensity"]
    assert ami["daily_value"] is None and len(ami["session_values"]) == 2


def test_wellness_joined_and_multiple_kept(cfg):
    res = process_workbook(build_workbook([session()], [wellness(score=20), wellness(score=22)]), cfg)
    w = _day(res)["wellness"]
    assert [x["wellness_score"] for x in w] == [20, 22]
    assert any(f["rule_code"] == "WELLNESS_MULTIPLE_SAME_DAY" for f in res.quality_flags)


def test_history_gaps_are_unobserved_not_zero(cfg):
    res = process_workbook(build_workbook([session(date="11/09", day=1), session(date="15/09", day=5)]), cfg)
    hist = res.output["athletes"][0]["history"]
    assert hist["observed_dates"] == ["2025-09-11", "2025-09-15"]
    assert hist["gaps"] == [{"from": "2025-09-12", "to": "2025-09-14", "days": 3, "status": "unobserved"}]
    assert len(res.daily_records) == 2   # no zero-filled days


def test_gd_conflict_flagged(cfg):
    res = process_workbook(build_workbook([session(gd="GD-1", **AM), session(gd="GD", **PM)]), cfg)
    assert _day(res)["schedule"]["gd_conflict"]
    assert any(f["rule_code"] == "GD_CONFLICT" for f in res.quality_flags)


def test_hit_exceeds_duration_and_hr_checks(cfg):
    res = process_workbook(build_workbook([session(duration=1 / 1440 * 10, hit=dt.timedelta(minutes=20),
                                                   **{"Minimum HR (bpm)": 190, "Peak HR (bpm)": 250})]), cfg)
    codes = {f["rule_code"] for f in res.quality_flags}
    assert {"HIT_EXCEEDS_DURATION", "HR_ORDER_INCONSISTENT", "IMPLAUSIBLE_HR"} <= codes
    assert all(f["severity"] == "warning" for f in res.quality_flags
               if f["rule_code"] in ("HIT_EXCEEDS_DURATION", "IMPLAUSIBLE_HR"))


def test_structurally_unrecorded_metric_is_info_not_warning(cfg):
    games = [session(athlete=f"P{i}", mtype="Game", ml=None, hit=None) for i in range(6)]
    res = process_workbook(build_workbook(games + [session(athlete="Q", ml=None)]), cfg)
    by = {(f["rule_code"], f["severity"]) for f in res.quality_flags}
    assert ("METRIC_NOT_RECORDED_FOR_TYPE", "info") in by
    assert ("MISSING_PRIMARY_METRIC", "warning") in by        # the lone training gap stays a warning
    games_days = [d for d in res.daily_records if d["athlete_label"] != "Q"]
    assert all(d["totals"]["movement_load"]["value"] is None for d in games_days)
