"""Shared pytest fixtures: tiny synthetic workbook builders for edge cases."""

from __future__ import annotations

import datetime as _dt
import os

import openpyxl
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_WORKBOOK = os.path.join(REPO_ROOT, "Data Set Georgia Tech_anonymized.xlsx")

# The minimal Full Day header set the parser maps. Extra columns are allowed and
# preserved, but these are enough to exercise the core schema.
FULLDAY_HEADERS = [
    "Athlete name", "Measurement type", "Analysis period", "Date", "Day", "GD",
    "Start time (hh:min:sec)", "End time (hh:min:sec)", "Duration (hh:mm:ss)",
    "Measurement error (%)", "High intensity training (hh:mm:ss)",
    "TRIMP (Index)", "TRIMP/min (Index)", "Movement load",
    "Average movement intensity", "Average HR (bpm)", "Minimum HR (bpm)",
    "Peak HR (bpm)", "ACWR",
]

WELLNESS_HEADERS = [
    "Date", "Performed By", "Fatig - #", "Sleep Qua - #", "Sleep Ti - #",
    "Sore - #", "Stre - #", "Wellness - Score",
]


def _write_sheet(ws, headers, rows, header_row=1, duration_as_fraction=False):
    """Write a header row (at header_row) and data rows below it.

    Each row is a dict keyed by header name. Duration/time values:
      * duration columns accept a float (day-fraction) or a timedelta.
      * start/end time accept datetime.time.
    """
    for i, h in enumerate(headers, start=1):
        ws.cell(row=header_row, column=i, value=h)
    for j, row in enumerate(rows, start=header_row + 1):
        for i, h in enumerate(headers, start=1):
            if h in row:
                ws.cell(row=j, column=i, value=row[h])


def build_workbook(path, fullday_rows, wellness_rows=None, *,
                   fullday_header_row=1, wellness_header_row=1,
                   include_wellness=True, fullday_headers=None):
    """Create a synthetic .xlsx at ``path`` and return the path."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Full Day"
    _write_sheet(ws, fullday_headers or FULLDAY_HEADERS, fullday_rows,
                 header_row=fullday_header_row)
    if include_wellness:
        wsw = wb.create_sheet("Wellness")
        _write_sheet(wsw, WELLNESS_HEADERS, wellness_rows or [],
                     header_row=wellness_header_row)
    wb.save(path)
    return str(path)


@pytest.fixture
def mk_workbook(tmp_path):
    """Factory fixture returning build_workbook bound to a tmp file."""
    counter = {"n": 0}

    def _factory(fullday_rows, wellness_rows=None, **kwargs):
        counter["n"] += 1
        p = tmp_path / f"wb_{counter['n']}.xlsx"
        return build_workbook(str(p), fullday_rows, wellness_rows, **kwargs)

    return _factory


def row(**kwargs):
    """Convenience: a Full Day row dict with sensible defaults."""
    base = {
        "Athlete name": "Player 01",
        "Measurement type": "Training",
        "Analysis period": "Measurement",
        "Date": "11/09",
        "Day": 1,
    }
    base.update(kwargs)
    return base


def td(seconds):
    return _dt.timedelta(seconds=seconds)


def tm(h, m, s=0):
    return _dt.time(h, m, s)
