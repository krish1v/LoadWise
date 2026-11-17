"""Ingestion, identity, duplicates, idempotency, failures and export (criteria 6–9, 14, 15)."""

import datetime as dt
import json

import pytest

from loadwise import Config, LoadWiseInputError, process_workbook, preview_workbook
from loadwise.ingest import athlete_id
from conftest import FD_HEADERS, build_workbook, session, wellness

AM = dict(start=dt.time(9, 0), end=dt.time(10, 30))
PM = dict(start=dt.time(19, 0), end=dt.time(20, 30))


# 6. Wellness header below blank rows is detected (not hardcoded)
@pytest.mark.parametrize("header_row", [1, 7, 49])
def test_wellness_header_detected(cfg, header_row):
    res = process_workbook(build_workbook([session()], [wellness()], wellness_header_row=header_row), cfg)
    imp = res.output["importMetadata"]["imports"][0]
    assert imp["wellness"]["header_row"] == header_row
    assert imp["wellness"]["records"] == 1
    assert res.output["wellnessRecords"][0]["provenance"]["excel_row"] == header_row + 1


def test_identity_normalization_and_stability(cfg):
    assert athlete_id("  Player   01 ") == athlete_id("Player 01") == athlete_id("player 01")
    assert athlete_id("Player 01") != athlete_id("Player 10")          # no fuzzy merging
    rows = [session(athlete="Player 01", **AM), session(athlete=" Player  01", **PM)]
    res = process_workbook(build_workbook(rows, [wellness(athlete="Player 01")]), cfg)
    assert len(res.output["athletes"]) == 1
    a = res.output["athletes"][0]
    assert a["sheets"] == ["sessions", "wellness"]
    assert res.daily_records[0]["wellness"]          # same mapping for both sheets


def test_raw_and_provenance_preserved(cfg):
    res = process_workbook((("team.xlsx", build_workbook([session(), session(athlete="B")]))), cfg)
    rec = res.cleaned_records[1]
    assert rec["provenance"] == {"file": "team.xlsx", "sheet": "Full Day", "excel_row": 3}
    raw = next(r for r in res.output["rawRecords"] if r["record_id"] == rec["record_id"])
    assert raw["cells"]["Athlete name"] == "B"
    assert rec["source_values"]["date"] == "11/09"


# 7. Exact duplicate preserved but counted once
def test_exact_duplicate_counted_once(cfg):
    res = process_workbook(build_workbook([session(trimp=100), session(trimp=100)]), cfg)
    recs = res.cleaned_records
    assert len(recs) == 2
    assert recs[0]["status"] == "included" and recs[1]["status"] == "excluded"
    assert recs[1]["duplicate_of"] == recs[0]["record_id"]
    d = res.daily_records[0]
    assert d["totals"]["trimp"]["value"] == 100
    assert d["excluded_record_ids"] == [recs[1]["record_id"]]
    assert res.output["summary"]["excluded_exact_duplicates"] == 1


# 8. Distinct same-day sessions remain included
def test_distinct_same_day_sessions_included(cfg):
    res = process_workbook(build_workbook([session(**AM), session(**PM)]), cfg)
    assert all(r["status"] == "included" for r in res.cleaned_records)
    assert not any(f["rule_code"].endswith("DUPLICATE") for f in res.quality_flags)


def test_overlapping_sessions_warned_but_included(cfg):
    rows = [session(trimp=100, **AM), session(trimp=90, start=dt.time(9, 10), end=dt.time(10, 30))]
    res = process_workbook(build_workbook(rows), cfg)
    assert all(r["status"] == "included" for r in res.cleaned_records)
    assert sum(f["rule_code"] == "POSSIBLE_DUPLICATE_OVERLAP" for f in res.quality_flags) == 2
    assert res.daily_records[0]["totals"]["trimp"]["value"] == 190


def test_override_exclude_with_reason_recomputes(cfg):
    rows = [session(trimp=100, **AM), session(trimp=90, start=dt.time(9, 10), end=dt.time(10, 30))]
    res = process_workbook(build_workbook(rows), cfg)
    rid = res.cleaned_records[1]["record_id"]
    res2 = res.reprocess({rid: {"action": "exclude", "reason": "same session recorded twice"}})
    assert res2.daily_records[0]["totals"]["trimp"]["value"] == 100
    rec = res2.cleaned_records[1]
    assert rec["status"] == "excluded" and rec["override"]["reason"] == "same session recorded twice"
    # and it can be re-included
    res3 = res2.reprocess({rid: {"action": "include", "reason": "different drills"}})
    assert res3.daily_records[0]["totals"]["trimp"]["value"] == 190


# 9. Idempotent reprocessing / re-upload
def test_idempotent_reprocessing(cfg):
    wb = build_workbook([session(**AM), session(**PM), session(**PM)], [wellness()])
    a = process_workbook(wb, cfg, generated_at="t").to_json()
    b = process_workbook(wb, cfg, generated_at="t").to_json()
    assert a == b


def test_same_file_uploaded_twice_is_not_appended(cfg):
    wb = build_workbook([session()])
    once = process_workbook(wb, cfg, generated_at="t")
    twice = process_workbook([("a.xlsx", wb), ("a-copy.xlsx", wb)], cfg, generated_at="t")
    assert len(twice.cleaned_records) == 1
    assert twice.daily_records == once.daily_records


def test_overlapping_different_files_dedupe_across_imports(cfg):
    a = build_workbook([session(**AM)])
    b = build_workbook([session(**AM), session(**PM)], include_wellness=False)
    res = process_workbook([("a.xlsx", a), ("b.xlsx", b)], cfg)
    assert res.output["summary"]["excluded_exact_duplicates"] == 1
    assert res.daily_records[0]["session_count"] == 2


# 14. Graceful failures
def test_missing_optional_wellness_sheet(cfg):
    res = process_workbook(build_workbook([session()], include_wellness=False), cfg)
    assert res.daily_records and res.daily_records[0]["wellness"] == []
    assert any(f["rule_code"] == "OPTIONAL_SHEET_MISSING" for f in res.quality_flags)


def test_missing_required_sheet(cfg):
    with pytest.raises(LoadWiseInputError, match="Full Day"):
        process_workbook(build_workbook([session()], fd_sheet="Something else"), cfg)


def test_missing_required_columns(cfg):
    headers = [h for h in FD_HEADERS if h != "Athlete name"]
    with pytest.raises(LoadWiseInputError, match="Athlete name"):
        process_workbook(build_workbook([session()], fd_headers=headers), cfg)


def test_missing_optional_column_is_unavailable(cfg):
    headers = [h for h in FD_HEADERS if h != "Movement load"]
    res = process_workbook(build_workbook([session()], fd_headers=headers), cfg)
    assert res.daily_records[0]["totals"]["movement_load"]["completeness"] == "missing"
    assert any(f["rule_code"] == "COLUMN_UNAVAILABLE" for f in res.quality_flags)


@pytest.mark.parametrize("data,match", [(b"", "empty"), (b"not an excel file", "not a valid .xlsx"),
                                        (b"PK\x03\x04garbage", "not a valid|could not be opened")])
def test_malformed_and_empty_files(cfg, data, match):
    with pytest.raises(LoadWiseInputError, match=match):
        process_workbook(data, cfg)


def test_missing_athlete_row_stays_visible(cfg):
    res = process_workbook(build_workbook([session(athlete=None), session()]), cfg)
    rej = res.cleaned_records[0]
    assert rej["status"] == "rejected"
    assert rej["record_id"] not in res.daily_records[0]["source_record_ids"]
    assert any(f["rule_code"] == "MISSING_ATHLETE" and f["severity"] == "error" for f in res.quality_flags)


def test_preview_reports_need_for_year():
    p = preview_workbook(build_workbook([session(date="02/01")]), Config())
    assert p["needs_season_year"] is True
    assert p["rollover"][0]["resolved_year"] is None


# 15. JSON serializes and daily totals trace back to source rows
def test_json_contract_and_traceability(cfg):
    res = process_workbook(build_workbook([session(trimp=100, **AM), session(trimp=50, **PM),
                                           session(trimp=50, **PM)]), cfg)
    out = json.loads(res.to_json())
    for key in ("schemaVersion", "importMetadata", "configuration", "athletes", "rawRecords",
                "cleanedRecords", "dailyRecords", "wellnessRecords", "scheduleContext",
                "qualityFlags", "summary"):
        assert key in out
    by_id = {r["record_id"]: r for r in out["cleanedRecords"]}
    raw_ids = {r["record_id"] for r in out["rawRecords"]}
    for d in out["dailyRecords"]:
        total = sum(by_id[i]["metrics"]["trimp"] for i in d["source_record_ids"])
        assert total == d["totals"]["trimp"]["value"]
        for i in d["source_record_ids"] + d["excluded_record_ids"]:
            assert i in raw_ids and by_id[i]["provenance"]["excel_row"] >= 2
    assert "NaN" not in res.to_json() and "Infinity" not in res.to_json()


def test_daily_csv_has_completeness_columns(cfg):
    res = process_workbook(build_workbook([session(ml=None, **AM), session(**PM)]), cfg)
    lines = res.to_daily_csv().splitlines()
    header = lines[0].split(",")
    assert "movement_load_completeness" in header and "efficiency_null_reason" in header
    row = dict(zip(header, lines[1].split(",")))
    assert row["movement_load_completeness"] == "partial"
