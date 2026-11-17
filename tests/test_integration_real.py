"""Smoke test on the supplied workbook (skipped if it is not present)."""

import json
import os

import pytest

from loadwise import Config, process_workbook
from conftest import REAL_WORKBOOK

pytestmark = pytest.mark.skipif(not os.path.exists(REAL_WORKBOOK), reason="real workbook not present")


@pytest.fixture(scope="module")
def result():
    return process_workbook(REAL_WORKBOOK, Config(season_start_year=2025), generated_at="test")


def test_structure_detected(result):
    imp = result.output["importMetadata"]["imports"][0]
    assert imp["full_day"]["header_row"] == 1 and imp["full_day"]["records"] == 1260
    assert imp["wellness"]["header_row"] == 49 and imp["wellness"]["records"] == 11


def test_counts_and_dates(result):
    s = result.output["summary"]
    assert s["session_records"] == 1260 and s["athletes"] == 15
    assert s["date_range"] == {"first": "2025-09-11", "last": "2026-01-09"}
    assert s["flags"]["error"] == 0


def test_types_and_game_metrics_never_zero_filled(result):
    types = {r["measurement_type"] for r in result.cleaned_records}
    assert types == {"Training", "Game"}
    games = [r for r in result.cleaned_records if r["measurement_type"] == "Game"]
    assert any(r["metrics"]["movement_load"] is None for r in games)
    for d in result.daily_records:
        assert all(d["reconciles"].values())
        if d["totals"]["movement_load"]["completeness"] == "missing":
            assert d["totals"]["movement_load"]["value"] is None


def test_source_acwr_preserved_not_calculated(result):
    rec = result.cleaned_records[0]
    assert rec["source_reported"]["acwr"] is not None
    assert "not calculated" in rec["source_reported"]["_note"]
    assert not any("acwr" in k.lower() for k in result.daily_records[0])


def test_json_serializes(result):
    assert json.loads(result.to_json(include_raw=False))["schemaVersion"] == "1.0.0"
