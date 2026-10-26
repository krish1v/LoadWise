"""Duplicate policy, idempotency, and export contract (criteria 7, 8, 9, 15)."""

from __future__ import annotations

import json

import pytest

from loadwise import Config, process_workbook
from loadwise.pipeline import apply_override
from conftest import row, tm


CFG = lambda: Config(season_start_year=2025)


def _daily(res, athlete="A001", date="2025-09-11"):
    return next((d for d in res.daily_records
                 if d["athlete_id"] == athlete and d["date"] == date), None)


# --- #7: exact duplicate preserved but counted once. ---
def test_exact_duplicate_preserved_counted_once(mk_workbook):
    r = row(**{"Start time (hh:min:sec)": tm(9, 0), "End time (hh:min:sec)": tm(10, 30),
               "Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
               "High intensity training (hh:mm:ss)": 0.0})
    res = process_workbook(mk_workbook([dict(r), dict(r)]), CFG())
    # Both records preserved.
    assert len(res.cleaned_records) == 2
    statuses = sorted(x["status"] for x in res.cleaned_records)
    assert statuses == ["excluded", "included"]
    # Daily total counts the metric once.
    d = _daily(res)
    assert d["included_session_count"] == 1
    assert d["totals"]["trimp"]["value"] == pytest.approx(30.0)
    assert any(f["rule_code"] == "EXACT_DUPLICATE" for f in res.quality_flags)


# --- #8: distinct same-day sessions remain included (not treated as duplicates). ---
def test_distinct_same_day_sessions_included(mk_workbook):
    fd = [
        row(**{"Start time (hh:min:sec)": tm(9, 0), "End time (hh:min:sec)": tm(10, 30),
               "Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
               "High intensity training (hh:mm:ss)": 0.0}),
        row(**{"Start time (hh:min:sec)": tm(17, 0), "End time (hh:min:sec)": tm(18, 30),
               "Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 25, "Movement load": 90,
               "High intensity training (hh:mm:ss)": 0.0}),
    ]
    res = process_workbook(mk_workbook(fd), CFG())
    assert all(x["status"] == "included" for x in res.cleaned_records)
    d = _daily(res)
    assert d["included_session_count"] == 2
    assert d["totals"]["trimp"]["value"] == pytest.approx(55.0)


def test_overlapping_sessions_flagged_but_included(mk_workbook):
    fd = [
        row(**{"Start time (hh:min:sec)": tm(9, 0), "End time (hh:min:sec)": tm(10, 30),
               "Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
               "High intensity training (hh:mm:ss)": 0.0}),
        row(**{"Start time (hh:min:sec)": tm(9, 15), "End time (hh:min:sec)": tm(10, 45),
               "Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 31, "Movement load": 101,
               "High intensity training (hh:mm:ss)": 0.0}),
    ]
    res = process_workbook(mk_workbook(fd), CFG())
    assert all(x["status"] == "included" for x in res.cleaned_records)
    assert any(f["rule_code"] == "POSSIBLE_DUPLICATE_OVERLAP" for f in res.quality_flags)


# --- #9: reprocessing the same input is idempotent. ---
def test_reprocessing_is_idempotent(mk_workbook):
    fd = [row(**{"Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
                 "High intensity training (hh:mm:ss)": 0.0})]
    path = mk_workbook(fd)
    a = process_workbook(path, CFG()).to_json()
    b = process_workbook(path, CFG()).to_json()
    assert a == b  # byte-identical (generated_at defaults to None)


# --- Manual include/exclude override recalculates daily outputs. ---
def test_manual_override_recalculates(mk_workbook):
    r = row(**{"Start time (hh:min:sec)": tm(9, 0), "End time (hh:min:sec)": tm(10, 30),
               "Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
               "High intensity training (hh:mm:ss)": 0.0})
    res = process_workbook(mk_workbook([dict(r), dict(r)]), CFG())
    excluded = next(x for x in res.cleaned_records if x["status"] == "excluded")
    apply_override(res, excluded["record_id"], "include", reason="confirmed distinct")
    d = _daily(res)
    assert d["included_session_count"] == 2
    assert d["totals"]["trimp"]["value"] == pytest.approx(60.0)


# --- #15: JSON serializes; daily totals trace back to source rows; CSV cols. ---
def test_json_serializes_and_is_safe(mk_workbook):
    fd = [row(**{"Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
                 "High intensity training (hh:mm:ss)": 0.0})]
    res = process_workbook(mk_workbook(fd), CFG())
    js = res.to_json()

    def _no_constants(c):
        raise ValueError(f"non-JSON constant present: {c}")

    # parse_constant fires only for NaN / Infinity / -Infinity tokens.
    parsed = json.loads(js, parse_constant=_no_constants)
    for key in ["schemaVersion", "importMetadata", "configuration", "athletes",
                "rawRecords", "cleanedRecords", "dailyRecords", "wellnessRecords",
                "scheduleContext", "qualityFlags", "summary"]:
        assert key in parsed


def test_daily_totals_trace_to_source_rows(mk_workbook):
    fd = [row(**{"Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
                 "High intensity training (hh:mm:ss)": 0.0})]
    res = process_workbook(mk_workbook(fd), CFG())
    d = res.daily_records[0]
    # Every contributing record id exists in cleanedRecords and maps to an Excel row.
    ids = {r["record_id"]: r for r in res.cleaned_records}
    for rid in d["source_record_ids"]:
        assert rid in ids
        assert ids[rid]["provenance"]["excel_row"] >= 2


def test_csv_has_completeness_columns(mk_workbook):
    fd = [row(**{"Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
                 "High intensity training (hh:mm:ss)": 0.0})]
    res = process_workbook(mk_workbook(fd), CFG())
    csv_text = res.to_daily_csv()
    header = csv_text.splitlines()[0]
    assert "trimp__completeness" in header
    assert "movement_load__completeness" in header
    assert "any_partial" in header


def test_json_without_raw_is_smaller(mk_workbook):
    fd = [row(**{"Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
                 "High intensity training (hh:mm:ss)": 0.0})]
    res = process_workbook(mk_workbook(fd), CFG())
    with_raw = res.to_json(include_raw=True)
    without = res.to_json(include_raw=False)
    assert len(without) < len(with_raw)
    assert json.loads(without)["rawRecords"]["omitted"] is True
