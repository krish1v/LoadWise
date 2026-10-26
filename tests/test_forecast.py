"""Tests for the Option B forecast bridge (loadwise.forecast).

Auto-skips if the model artifact or scikit-learn/joblib are unavailable, so the
core data-layer suite still runs anywhere.
"""

from __future__ import annotations

import json
import os

import pytest

from loadwise.forecast import MODEL_PATH

pytestmark = pytest.mark.skipif(not os.path.exists(MODEL_PATH),
                                reason="forecast model artifact not present")

try:
    import joblib  # noqa: F401
    import sklearn  # noqa: F401
    _ML = True
except ImportError:
    _ML = False

pytestmark = [pytestmark, pytest.mark.skipif(not _ML, reason="scikit-learn/joblib not installed")]


@pytest.fixture(scope="module")
def fc():
    from loadwise.forecast import Forecaster
    return Forecaster()


def test_known_and_coldstart_athletes(fc):
    assert fc.is_known("Player 01")
    assert not fc.is_known("Player 99")  # unseen -> cold start


def test_prediction_scales_linearly_with_minutes(fc):
    one = fc.predict_session("Player 01", 60)
    two = fc.predict_session("Player 01", 120)
    assert one > 0
    assert two == pytest.approx(2 * one, rel=1e-6)  # TRIMP = rate x minutes


def test_zero_minutes_predicts_zero(fc):
    assert fc.predict_session("Player 01", 0) == 0.0


def test_coldstart_uses_global_rate(fc):
    rate_unseen = fc.historical_rate("Player 99")
    assert rate_unseen == pytest.approx(fc.global_rate)


def test_forecast_totals_and_structure(fc):
    out = fc.forecast("Player 02", [90, 0, 75])
    assert len(out["days"]) == 3
    assert out["days"][1]["predicted_trimp"] == 0.0
    assert out["horizon_total_trimp"] == pytest.approx(
        sum(d["predicted_trimp"] for d in out["days"]), abs=0.1)
    assert out["known_athlete"] is True


def test_baseline_export_is_json_safe_and_shaped(fc):
    exp = fc.baseline_export("Player 03", [90, 90], start_date="2026-01-12")
    s = json.dumps(exp)  # must serialize
    assert exp["kind"] == "expected_baseline_workload"
    assert exp["metric"] == "training_trimp"
    assert len(exp["daily_baseline"]) == 2
    assert exp["daily_baseline"][0]["day_offset"] == 0
    assert "caveats" in exp and exp["caveats"]
    json.loads(s, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))  # no NaN/Inf
