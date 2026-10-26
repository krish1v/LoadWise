"""Identity assignment and ingestion/structure handling (criteria 6, 14)."""

from __future__ import annotations

import openpyxl
import pytest

from loadwise import Config, process_workbook
from loadwise.identity import IdentityMap, normalize_label
from loadwise import ingest
from loadwise.pipeline import SeasonYearRequired
from conftest import row, WELLNESS_HEADERS


# --- Identity: deterministic, stable, no fuzzy merge. ---
def test_identity_deterministic_and_trimmed():
    idm = IdentityMap()
    idm.register_all([normalize_label(x) for x in ["  Player 02 ", "Player 01", "Player  01"]])
    # "Player  01" collapses internal whitespace to match "Player 01".
    assert idm.get("Player 01") == "A001"
    assert idm.get("Player 02") == "A002"
    assert idm.get(normalize_label("Player  01")) == "A001"


def test_identity_stable_across_uploads_append_only():
    first = IdentityMap()
    first.register_all(["Player 01", "Player 02"])
    seed = first.as_dict()
    # A later upload introduces a new athlete; existing ids must not change.
    second = IdentityMap(seed)
    second.register_all(["Player 01", "Player 02", "Player 03"])
    assert second.get("Player 01") == "A001"
    assert second.get("Player 02") == "A002"
    assert second.get("Player 03") == "A003"


def test_identity_no_fuzzy_merge_of_distinct_labels():
    idm = IdentityMap()
    idm.register_all(["Player 01", "Player 10"])
    assert idm.get("Player 01") != idm.get("Player 10")


# --- #6: Wellness header below blank rows is detected. ---
def test_wellness_header_below_blank_rows_detected(mk_workbook):
    fd = [row(**{"Duration (hh:mm:ss)": 0.0625, "TRIMP (Index)": 30, "Movement load": 100,
                 "High intensity training (hh:mm:ss)": 0.0})]
    well = [{"Date": "11/09", "Performed By": "Player 01", "Fatig - #": 5,
             "Sleep Qua - #": 6, "Sleep Ti - #": 7, "Sore - #": 4, "Stre - #": 5,
             "Wellness - Score": 27}]
    path = mk_workbook(fd, well, wellness_header_row=49)  # mimic the real workbook
    sheets = ingest.ingest_workbook(path)
    assert sheets["wellness"].present
    assert sheets["wellness"].header_row == 49
    assert len(sheets["wellness"].records) == 1


# --- #14: graceful handling of structural problems. ---
def test_missing_optional_wellness_sheet_is_not_fatal(mk_workbook):
    fd = [row(**{"TRIMP (Index)": 30, "Movement load": 100})]
    path = mk_workbook(fd, include_wellness=False)
    sheets = ingest.ingest_workbook(path)
    assert sheets["wellness"].present is False
    # Pipeline still runs with zero wellness records.
    res = process_workbook(path, Config(season_start_year=2025))
    assert res.wellness_records == []


def test_invalid_required_structure_raises(mk_workbook):
    # Full Day sheet present but without recognizable headers.
    bad = [{"Foo": 1, "Bar": 2}]
    path = mk_workbook(bad, fullday_headers=["Foo", "Bar", "Baz"])
    with pytest.raises(ingest.SheetStructureError):
        ingest.ingest_workbook(path)


def test_malformed_file_raises_ingest_error(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"this is not a real xlsx file")
    with pytest.raises(ingest.IngestError):
        ingest.ingest_workbook(str(p))


def test_empty_file_raises_ingest_error(tmp_path):
    p = tmp_path / "empty.xlsx"
    p.write_bytes(b"")
    with pytest.raises(ingest.IngestError):
        ingest.ingest_workbook(str(p))


def test_missing_season_year_raises_actionable(mk_workbook):
    fd = [row(**{"TRIMP (Index)": 30, "Movement load": 100})]
    path = mk_workbook(fd)
    with pytest.raises(SeasonYearRequired) as ei:
        process_workbook(path, Config(season_start_year=None))
    assert "season start year" in str(ei.value).lower()
