"""Excel ingestion with header detection and full provenance.

Raw source records are immutable: we read every cell of every column verbatim
(typed value + number format) and attach file / sheet / Excel-row provenance.
Header positions and data-row counts are *detected*, never hardcoded, so the
Wellness header living on row 49 above blank rows is handled automatically.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

import openpyxl

from . import schema


class IngestError(Exception):
    """Raised when a workbook cannot be read at all (malformed / empty file)."""


class SheetStructureError(Exception):
    """Raised when a *required* sheet is present but its structure is unusable."""


@dataclass
class RawRecord:
    record_id: str
    file: str
    sheet: str
    excel_row: int
    cells: Dict[str, object]           # header -> typed source value (immutable)
    formats: Dict[str, Optional[str]]  # header -> Excel number format


@dataclass
class SheetIngest:
    name: str
    present: bool
    header_row: Optional[int]
    headers: List[str]
    records: List[RawRecord] = field(default_factory=list)
    note: Optional[str] = None


def _open_workbook(source: Union[str, bytes, io.BytesIO]):
    try:
        if isinstance(source, (bytes, bytearray)):
            return openpyxl.load_workbook(io.BytesIO(source), data_only=True, read_only=False)
        if hasattr(source, "read"):
            return openpyxl.load_workbook(source, data_only=True, read_only=False)
        if not os.path.exists(source):
            raise IngestError(f"File not found: {source}")
        if os.path.getsize(source) == 0:
            raise IngestError("File is empty (0 bytes).")
        return openpyxl.load_workbook(source, data_only=True, read_only=False)
    except IngestError:
        raise
    except Exception as e:  # malformed / not an xlsx / corrupt
        raise IngestError(f"Could not open workbook: {e}") from e


def _find_sheet(wb, name: str):
    """Case-insensitive, trimmed sheet lookup."""
    target = name.strip().lower()
    for ws in wb.worksheets:
        if ws.title.strip().lower() == target:
            return ws
    return None


def _detect_header_in_rows(rows: list, markers: List[str], max_scan: int = 60) -> Optional[int]:
    """Return the 0-based index into ``rows`` of the header row (>=2 markers)."""
    marker_set = {m.strip().lower() for m in markers}
    best_i, best_hits = None, 0
    for i, rowcells in enumerate(rows[:max_scan]):
        vals = {str(c.value).strip().lower() for c in rowcells if c.value is not None}
        hits = len(marker_set & vals)
        if hits > best_hits:
            best_hits, best_i = hits, i
    return best_i if best_hits >= 2 else None


def _row_cells_blank(rowcells) -> bool:
    for c in rowcells:
        v = c.value
        if v is not None and not (isinstance(v, str) and v.strip() == ""):
            return False
    return True


def _ingest_sheet(wb, sheet_name: str, markers: List[str], id_prefix: str,
                  file_label: str, required: bool) -> SheetIngest:
    ws = _find_sheet(wb, sheet_name)
    if ws is None:
        return SheetIngest(name=sheet_name, present=False, header_row=None, headers=[],
                           note="sheet_not_found")

    # One pass over the sheet. iter_rows yields Cell objects (value + number_format)
    # in fixed-width, row-aligned tuples -- far faster than random ws.cell() access.
    rows = list(ws.iter_rows())
    header_i = _detect_header_in_rows(rows, markers)
    if header_i is None:
        msg = f"Could not locate a header row in sheet {sheet_name!r} (looked for {markers})."
        if required:
            raise SheetStructureError(msg)
        return SheetIngest(name=sheet_name, present=True, header_row=None, headers=[], note=msg)

    header_excel_row = header_i + 1  # iter_rows[0] == Excel row 1
    headers: List[str] = []
    col_pos: List[int] = []
    for pos, cell in enumerate(rows[header_i]):
        v = cell.value
        if v is None or str(v).strip() == "":
            continue
        headers.append(str(v).strip())
        col_pos.append(pos)

    records: List[RawRecord] = []
    for offset, rowcells in enumerate(rows[header_i + 1:], start=1):
        if _row_cells_blank(rowcells):
            continue  # skip blank/trailing rows anywhere in the data region
        excel_row = header_excel_row + offset
        cells: Dict[str, object] = {}
        formats: Dict[str, Optional[str]] = {}
        for header, pos in zip(headers, col_pos):
            cell = rowcells[pos] if pos < len(rowcells) else None
            cells[header] = cell.value if cell is not None else None
            formats[header] = cell.number_format if cell is not None else None
        records.append(RawRecord(
            record_id=f"{id_prefix}-{excel_row:05d}",
            file=file_label, sheet=ws.title, excel_row=excel_row,
            cells=cells, formats=formats,
        ))

    return SheetIngest(name=ws.title, present=True, header_row=header_excel_row,
                       headers=headers, records=records)


def ingest_workbook(source: Union[str, bytes, io.BytesIO],
                    file_label: Optional[str] = None) -> Dict[str, SheetIngest]:
    """Read the workbook and return {'full_day': SheetIngest, 'wellness': SheetIngest}.

    'Full Day' is a required sheet; 'Wellness' is optional. Malformed/empty files
    raise IngestError; a present-but-unusable required sheet raises
    SheetStructureError. Both carry actionable messages.
    """
    if file_label is None:
        file_label = source if isinstance(source, str) else "<uploaded>"
    wb = _open_workbook(source)
    if not wb.worksheets:
        raise IngestError("Workbook contains no worksheets.")

    full_day = _ingest_sheet(wb, "Full Day", schema.FULLDAY_HEADER_MARKERS,
                             id_prefix="fd", file_label=file_label, required=True)
    wellness = _ingest_sheet(wb, "Wellness", schema.WELLNESS_HEADER_MARKERS,
                             id_prefix="wl", file_label=file_label, required=False)
    return {"full_day": full_day, "wellness": wellness}


def detect_sheets_preview(source: Union[str, bytes, io.BytesIO],
                          file_label: Optional[str] = None) -> dict:
    """Lightweight preview of sheets/headers for the Upload view (no normalization)."""
    ing = ingest_workbook(source, file_label=file_label)
    out = {}
    for key, si in ing.items():
        out[key] = {
            "sheet_name": si.name,
            "present": si.present,
            "header_row": si.header_row,
            "headers": si.headers,
            "record_count": len(si.records),
            "note": si.note,
        }
    return out
