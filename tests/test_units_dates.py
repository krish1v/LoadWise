"""Units and dates (acceptance criteria 3, 4, 5) — synthetic fixtures."""

import datetime as dt

import pytest

from loadwise import Config, SeasonYearRequired, process_workbook
from loadwise.normalize import duration_to_minutes, percent, resolve_date, rollover_preview, to_number
from conftest import build_workbook, session


# --- 3. Excel duration 0.0625 -> 90 minutes --------------------------------
def test_excel_fraction_is_90_minutes():
    assert duration_to_minutes(0.0625) == (90.0, None)


@pytest.mark.parametrize("value,expected", [
    (dt.timedelta(hours=1, minutes=30), 90.0),
    ("1:30:00", 90.0),
    ("01:30", 90.0),
    (dt.time(1, 30), 90.0),
    (0, 0.0),
])
def test_duration_formats(value, expected):
    assert duration_to_minutes(value)[0] == pytest.approx(expected)


def test_duration_keeps_full_precision():
    assert duration_to_minutes(dt.timedelta(seconds=11560))[0] == pytest.approx(192.6666666666)


def test_duration_unusable_values_are_null():
    assert duration_to_minutes(None) == (None, "missing")
    assert duration_to_minutes("abc") == (None, "non_numeric")


def test_duration_through_pipeline_is_90(cfg):
    res = process_workbook(build_workbook([session(duration=0.0625)]), cfg)
    assert res.cleaned_records[0]["metrics"]["duration_min"] == pytest.approx(90.0)


def test_numbers_and_zero():
    assert to_number(0) == (0.0, None)
    assert to_number("12,5") == (12.5, None)
    assert to_number(float("nan"))[0] is None
    assert to_number(float("inf")) == (None, "non_finite")
    assert to_number("n/a") == (None, "non_numeric")


def test_percent_uses_format_and_header_context():
    assert percent(0.0214, "0.00 %", "Measurement error (%)")[0] == pytest.approx(2.14)
    # header says %, but cell is not %-formatted and already holds percent points
    assert percent(21.76, "0", "Heart Rate Recovery (%) 30s")[0] == pytest.approx(21.76)


# --- 4. Day/month dates and the Dec -> Jan rollover --------------------------
def test_rollover_uses_supplied_season_year():
    c = Config(season_start_year=2025)
    assert resolve_date("11/09", c)["iso"] == "2025-09-11"
    assert resolve_date("31/12", c)["iso"] == "2025-12-31"
    assert resolve_date("01/01", c)["iso"] == "2026-01-01"
    assert resolve_date("09/01", c)["iso"] == "2026-01-09"


def test_rollover_preview_lists_years_in_season_order():
    rows = rollover_preview(["11/09", "05/12", "02/01"], Config(season_start_year=2025))
    assert [(r["month_name"], r["resolved_year"]) for r in rows] == [
        ("Sep", 2025), ("Dec", 2025), ("Jan", 2026)]


def test_rollover_through_pipeline(cfg):
    wb = build_workbook([session(date="31/12", day=1), session(date="01/01", day=2,
                                                                start=dt.time(9), end=dt.time(10))])
    dates = [r["date"] for r in process_workbook(wb, cfg).cleaned_records]
    assert dates == ["2025-12-31", "2026-01-01"]


def test_invalid_calendar_date_is_rejected_not_guessed(cfg):
    res = process_workbook(build_workbook([session(date="31/02")]), cfg)
    rec = res.cleaned_records[0]
    assert rec["date"] is None and rec["status"] == "rejected"
    assert any(f["rule_code"] == "MISSING_OR_INVALID_DATE" for f in res.quality_flags)


def test_real_dates_and_1904_serials():
    c = Config()   # no year needed for real dates
    assert resolve_date(dt.datetime(2025, 10, 3, 23, 30), c)["iso"] == "2025-10-03"  # no tz shift
    from openpyxl.utils.datetime import CALENDAR_MAC_1904, CALENDAR_WINDOWS_1900
    assert resolve_date(45000, c, CALENDAR_WINDOWS_1900)["iso"] == "2023-03-15"
    assert resolve_date(45000 - 1462, c, CALENDAR_MAC_1904)["iso"] == "2023-03-15"


# --- 5. Missing year -> actionable request, never an invented year -----------
def test_missing_year_raises_actionable_error():
    with pytest.raises(SeasonYearRequired) as e:
        process_workbook(build_workbook([session()]), Config())
    assert "season start year" in str(e.value)
    assert str(dt.date.today().year) not in str(e.value)


def test_date_dayindex_conflict_is_flagged(cfg):
    rows = [session(date="11/09", day=1), session(athlete="Player B", date="12/09", day=1)]
    res = process_workbook(build_workbook(rows), cfg)
    assert any(f["rule_code"] == "DATE_DAYINDEX_CONFLICT" for f in res.quality_flags)


def test_midnight_crossing_is_flagged_and_attributed_to_start_date(cfg):
    res = process_workbook(build_workbook([session(start=dt.time(23, 0), end=dt.time(0, 30))]), cfg)
    rec = res.cleaned_records[0]
    assert rec["crosses_midnight"] and rec["clock_span_min"] == pytest.approx(90)
    assert rec["date"] == "2025-09-11"
    assert any(f["rule_code"] == "MIDNIGHT_CROSSING" for f in res.quality_flags)
