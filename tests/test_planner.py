"""Training planner: LoadWise daily records -> the modelling team's model inputs."""

import datetime as dt

import pytest

from conftest import MIP1, build_workbook, session
from loadwise import process_workbook

pytest.importorskip("sklearn")
pytest.importorskip("scipy")

from planner import PlanningContext  # noqa: E402
from planner.features import history_features, training_days  # noqa: E402


def _days(n_days, athlete="Player 01", start=dt.date(2025, 11, 1), **kw):
    rows = []
    for i in range(n_days):
        d = start + dt.timedelta(days=i)
        rows.append(session(athlete=athlete, date=d.strftime("%d/%m"), day=i + 1, **kw))
    return rows


def test_mip_is_daily_max_over_training_and_sums_need_complete_days(cfg):
    rows = [
        session(date="11/09", start=dt.time(9), end=dt.time(10, 30), **{MIP1: 6.5}),
        session(date="11/09", start=dt.time(16), end=dt.time(17, 30), ml=None, **{MIP1: 7.25}),
        session(date="11/09", mtype="Game", start=dt.time(19), end=dt.time(21), ml=None, **{MIP1: 9.0}),
    ]
    res = process_workbook(build_workbook(rows), cfg)
    day = res.daily_records[0]
    assert day["peak_intensity"]["mip1"]["value"] == 9.0                       # all sessions
    assert day["peak_intensity"]["mip1"]["by_bucket"]["training"]["value"] == 7.25
    frame, games = training_days(res.daily_records)
    row = frame.iloc[0]
    assert row.mip1 == 7.25                               # game peak not used
    assert row.training_trimp == 200.0                    # both training sessions recorded TRIMP
    assert row.movement_load != row.movement_load         # NaN: one training session lacks ML
    assert row.recorded_duration_min == pytest.approx(180)
    assert games == {("Player A", dt.date(2025, 9, 11).toordinal())}


def test_history_features_use_calendar_days(cfg):
    res = process_workbook(build_workbook(_days(5)), cfg)
    frame, games = training_days(res.daily_records)
    past = frame.astype(object).where(frame.notna(), None).to_dict("records")
    start = dt.date(2025, 11, 10).toordinal()
    f = history_features(past, games, "Player 01", start)
    assert f["days_since_mip1"] == 5 and f["training_days_7d"] == 3 and f["training_days_28d"] == 5
    assert f["training_trimp_sum_28d"] == 500.0


def test_short_history_falls_back_to_pooled_models(cfg):
    res = process_workbook(build_workbook(_days(2)), cfg)
    ctx = PlanningContext(res.daily_records)
    _, reason, _, history = ctx.defaults("Player 01", ctx.last_day)
    assert reason.startswith("Fewer than three") and history is None


def test_unknown_athlete_is_pooled_not_matched(cfg):
    # 'Player 99' is not in the models' training data: no fuzzy matching, pooled fallback.
    res = process_workbook(build_workbook(_days(6, athlete="Player 99")), cfg)
    ctx = PlanningContext(res.daily_records)
    _, reason, _, _ = ctx.defaults("Player 99", ctx.last_day)
    assert "not in the model training data" in reason


def test_planning_start_must_be_in_range(cfg):
    res = process_workbook(build_workbook(_days(4)), cfg)
    ctx = PlanningContext(res.daily_records)
    with pytest.raises(ValueError, match="between"):
        ctx.start_day("2030-01-01")
