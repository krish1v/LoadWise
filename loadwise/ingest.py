"""Read an .xlsx workbook into immutable raw records with full provenance.

Header rows are *detected* (by looking for marker columns), never hardcoded, so
the Wellness header on row 49 below blank rows is found automatically.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

import openpyxl

from .config import LoadWiseInputError

Source = Union[str, bytes]

# canonical key -> source header, per sheet. "required" columns must exist.
FULL_DAY_COLUMNS = {
    "athlete": "Athlete name",
    "measurement_type": "Measurement type",
    "analysis_period": "Analysis period",
    "date": "Date",
    "study_day_index": "Day",
    "gd": "GD",
    "start_time": "Start time (hh:min:sec)",
    "end_time": "End time (hh:min:sec)",
    "duration": "Duration (hh:mm:ss)",
    "measurement_error": "Measurement error (%)",
    "hit": "High intensity training (hh:mm:ss)",
    "trimp": "TRIMP (Index)",
    "trimp_per_min": "TRIMP/min (Index)",
    "movement_load": "Movement load",
    "avg_movement_intensity": "Average movement intensity",
    "hr_avg": "Average HR (bpm)",
    "hr_min": "Minimum HR (bpm)",
    "hr_peak": "Peak HR (bpm)",
    "source_acute_load": "Acute Training Load",
    "source_chronic_load": "Chronic Training Load",
    "source_acwr": "ACWR",
}
FULL_DAY_REQUIRED = ("athlete", "date")

WELLNESS_COLUMNS = {
    "date": "Date",
    "athlete": "Performed By",
    "fatigue": "Fatig - #",
    "sleep_quality": "Sleep Qua - #",
    "sleep_time": "Sleep Ti - #",
    "soreness": "Sore - #",
    "stress": "Stre - #",
    "wellness_score": "Wellness - Score",
}
WELLNESS_REQUIRED = ("athlete", "date")

FULL_DAY_SHEET = "Full Day"
WELLNESS_SHEET = "Wellness"
HEADER_SCAN_ROWS = 200


def _norm_header(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().casefold()


# ---------------------------------------------------------------- identity --

def normalize_label(raw) -> Optional[str]:
    """Harmless formatting cleanup only: Unicode NFC, trim, collapse whitespace."""
    if raw is None:
        return None
    s = re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(raw))).strip()
    return s or None


def athlete_id(label: Optional[str]) -> Optional[str]:
    """Deterministic, upload-independent ID. Case-insensitive; no fuzzy matching."""
    norm = normalize_label(label)
    if norm is None:
        return None
    return "ath-" + hashlib.sha1(norm.casefold().encode("utf-8")).hexdigest()[:8]


# ------------------------------------------------------------------ models --

@dataclass(frozen=True)
class RawRecord:
    record_id: str
    import_id: str
    file: str
    sheet: str
    excel_row: int
    cells: Dict[str, object]      # header -> value exactly as openpyxl read it
    formats: Dict[str, str]       # header -> Excel number format


@dataclass
class SheetResult:
    name: str
    present: bool
    header_row: Optional[int] = None
    headers: List[str] = field(default_factory=list)
    mapping: Dict[str, Optional[str]] = field(default_factory=dict)   # key -> header or None
    records: List[RawRecord] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)


@dataclass
class WorkbookIngest:
    import_id: str
    sha256: str
    file: str
    epoch: str
    sheet_names: List[str]
    full_day: SheetResult
    wellness: SheetResult
    workbook_epoch: object = None


# ------------------------------------------------------------------ reading --

def _read_bytes(source: Source) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    try:
        with open(source, "rb") as fh:
            return fh.read()
    except OSError as e:
        raise LoadWiseInputError(f"Could not read the file: {e}") from e


def _open(data: bytes):
    if not data:
        raise LoadWiseInputError("The uploaded file is empty. Choose an .xlsx export from the source system.")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise LoadWiseInputError(
            "This file is not a valid .xlsx workbook (old .xls, CSV or a corrupted file?). "
            "Re-export it from Excel as .xlsx and upload again.")
    try:
        return openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise LoadWiseInputError(f"The workbook could not be opened ({type(e).__name__}). "
                                 "Re-save it in Excel as .xlsx and try again.") from e


def _find_sheet(wb, wanted: str):
    for name in wb.sheetnames:
        if _norm_header(name) == _norm_header(wanted):
            return wb[name]
    return None


def _read_sheet(ws, wanted: str, columns: dict, required: tuple, prefix: str,
                import_id: str, file: str) -> SheetResult:
    res = SheetResult(name=ws.title, present=True)
    markers = {_norm_header(columns[k]) for k in required}
    rows = ws.iter_rows()
    header_cells = None
    for scanned, row in enumerate(rows, 1):
        values = {_norm_header(c.value) for c in row if c.value is not None}
        if markers <= values:
            header_cells = row
            break
        if scanned >= HEADER_SCAN_ROWS:
            break
    if header_cells is None:
        res.messages.append(
            f"Sheet '{ws.title}': no header row containing "
            f"{', '.join(repr(columns[k]) for k in required)} was found in the first "
            f"{HEADER_SCAN_ROWS} rows.")
        return res

    res.header_row = next(c.row for c in header_cells if getattr(c, "row", None))
    headers: List[Optional[str]] = []
    seen: Dict[str, int] = {}
    for c in header_cells:
        if c.value is None or str(c.value).strip() == "":
            headers.append(None)
            continue
        h = str(c.value).strip()
        if h in seen:                       # keep duplicate headers distinguishable
            seen[h] += 1
            h = f"{h} ({seen[h]})"
        else:
            seen[h] = 1
        headers.append(h)
    res.headers = [h for h in headers if h]
    by_norm = {_norm_header(h): h for h in res.headers}
    res.mapping = {k: by_norm.get(_norm_header(v)) for k, v in columns.items()}

    for row in rows:
        cells = {h: None for h in res.headers}
        formats = {h: "General" for h in res.headers}
        excel_row = None
        for h, c in zip(headers, row):
            if excel_row is None and getattr(c, "row", None):
                excel_row = c.row
            if h is None:
                continue
            v = c.value
            if isinstance(v, str) and v.strip() == "":
                v = None
            cells[h] = v
            formats[h] = getattr(c, "number_format", "General") or "General"
        if excel_row is None or all(v is None for v in cells.values()):
            continue          # trailing / interleaved blank rows
        res.records.append(RawRecord(
            record_id=f"{import_id}:{prefix}-{excel_row}", import_id=import_id, file=file,
            sheet=ws.title, excel_row=excel_row, cells=cells, formats=formats))
    return res


def ingest_workbook(source: Source, filename: Optional[str] = None) -> WorkbookIngest:
    """Read the workbook. Raises LoadWiseInputError for unusable input."""
    data = _read_bytes(source)
    file = filename or (source if isinstance(source, str) else "upload.xlsx")
    file = re.split(r"[\\/]", str(file))[-1]
    sha = hashlib.sha256(data).hexdigest()
    import_id = sha[:12]
    wb = _open(data)
    try:
        fd_ws = _find_sheet(wb, FULL_DAY_SHEET)
        if fd_ws is None:
            raise LoadWiseInputError(
                f"Required sheet '{FULL_DAY_SHEET}' was not found (sheets present: "
                f"{', '.join(wb.sheetnames) or 'none'}). Export the per-measurement "
                f"'{FULL_DAY_SHEET}' report from the source system.")
        full_day = _read_sheet(fd_ws, FULL_DAY_SHEET, FULL_DAY_COLUMNS, FULL_DAY_REQUIRED,
                               "fd", import_id, file)
        if full_day.header_row is None:
            raise LoadWiseInputError(
                full_day.messages[0] + " These columns are required to identify athletes and dates.")
        missing_opt = [FULL_DAY_COLUMNS[k] for k, h in full_day.mapping.items() if h is None]
        if missing_opt:
            full_day.messages.append("Optional columns not present (reported as unavailable): "
                                     + ", ".join(missing_opt))

        wl_ws = _find_sheet(wb, WELLNESS_SHEET)
        if wl_ws is None:
            wellness = SheetResult(name=WELLNESS_SHEET, present=False, messages=[
                f"Optional sheet '{WELLNESS_SHEET}' not found; daily records will have no wellness observations."])
        else:
            wellness = _read_sheet(wl_ws, WELLNESS_SHEET, WELLNESS_COLUMNS, WELLNESS_REQUIRED,
                                   "wl", import_id, file)
            if wellness.header_row is None:
                wellness.present = False
                wellness.messages.append("Wellness data was skipped; the workload data is unaffected.")
        return WorkbookIngest(import_id=import_id, sha256=sha, file=file,
                              epoch=wb.epoch.date().isoformat(), sheet_names=list(wb.sheetnames),
                              full_day=full_day, wellness=wellness, workbook_epoch=wb.epoch)
    finally:
        wb.close()
