"""Synthetic workbook builder. Every fixture is small and explicitly labelled synthetic."""

from __future__ import annotations

import datetime as dt
import io
import os
import sys

import openpyxl
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from loadwise import Config  # noqa: E402

REAL_WORKBOOK = os.path.join(ROOT, "Data Set Georgia Tech_anonymized.xlsx")

FD_HEADERS = ["Athlete name", "Measurement type", "Analysis period", "Date", "Day", "GD",
              "Start time (hh:min:sec)", "End time (hh:min:sec)", "Duration (hh:mm:ss)",
              "Measurement error (%)", "High intensity training (hh:mm:ss)", "TRIMP (Index)",
              "TRIMP/min (Index)", "Movement load", "Average movement intensity",
              "Average HR (bpm)", "Minimum HR (bpm)", "Peak HR (bpm)",
              "Acute Training Load", "Chronic Training Load", "ACWR",
              "Maximal Intensity Period MI 1min", "Maximal Intensity Period MI 3min"]
MIP1, MIP3 = "Maximal Intensity Period MI 1min", "Maximal Intensity Period MI 3min"
WL_HEADERS = ["Date", "Performed By", "Fatig - #", "Sleep Qua - #", "Sleep Ti - #", "Sore - #",
              "Stre - #", "Wellness - Score"]


def session(athlete="Player A", mtype="Training", date="11/09", day=1, gd=None,
            start=dt.time(9, 0), end=dt.time(10, 30), duration=0.0625, hit=dt.timedelta(minutes=5),
            trimp=100.0, ml=200.0, **extra):
    row = {"Athlete name": athlete, "Measurement type": mtype, "Analysis period": "Measurement",
           "Date": date, "Day": day, "GD": gd, "Start time (hh:min:sec)": start,
           "End time (hh:min:sec)": end, "Duration (hh:mm:ss)": duration,
           "Measurement error (%)": 0.02, "High intensity training (hh:mm:ss)": hit,
           "TRIMP (Index)": trimp, "TRIMP/min (Index)": 1.1, "Movement load": ml,
           "Average movement intensity": 0.9, "Average HR (bpm)": 120, "Minimum HR (bpm)": 60,
           "Peak HR (bpm)": 180, "Acute Training Load": 700, "Chronic Training Load": 800,
           "ACWR": 0.875, MIP1: 6.0, MIP3: 5.0}
    row.update(extra)
    return row


def wellness(athlete="Player A", date="11/09", score=25):
    return {"Date": date, "Performed By": athlete, "Fatig - #": 5, "Sleep Qua - #": 5,
            "Sleep Ti - #": 6, "Sore - #": 4, "Stre - #": 5, "Wellness - Score": score}


def build_workbook(sessions=None, wellness_rows=None, wellness_header_row=49, fd_headers=None,
                   include_wellness=True, epoch1904=False, fd_sheet="Full Day") -> bytes:
    wb = openpyxl.Workbook()
    if epoch1904:
        wb.epoch = openpyxl.utils.datetime.CALENDAR_MAC_1904
    ws = wb.active
    ws.title = fd_sheet
    headers = fd_headers or FD_HEADERS
    ws.append(headers)
    for s in sessions or []:
        ws.append([s.get(h) for h in headers])
        r = ws.max_row
        for col, h in enumerate(headers, 1):
            if h == "Measurement error (%)":
                ws.cell(r, col).number_format = "0.00 %"
            if h == "Duration (hh:mm:ss)":
                ws.cell(r, col).number_format = "[hh]:mm:ss"
    if include_wellness:
        wl = wb.create_sheet("Wellness")
        for c, h in enumerate(WL_HEADERS, 1):
            wl.cell(wellness_header_row, c, h)
        for i, w in enumerate(wellness_rows or [], 1):
            for c, h in enumerate(WL_HEADERS, 1):
                wl.cell(wellness_header_row + i, c, w.get(h))
        wl.cell(wellness_header_row + len(wellness_rows or []) + 5, 1).number_format = "0.00"  # blank tail
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def cfg():
    return Config(season_start_year=2025)
