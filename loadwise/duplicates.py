"""Duplicate detection and canonicalization.

Policy (spec section 4):
  * Same athlete + date alone is NOT a duplicate.
  * Every original record is preserved.
  * Exact copies: keep one canonical record, exclude the rest from totals, and
    record the relationship. (This is what makes re-uploading idempotent.)
  * Distinct *possible* duplicates / overlaps stay INCLUDED with a visible
    warning until a human reviews them.
"""

from __future__ import annotations

import hashlib
import json
from typing import List, Optional

from .ingest import RawRecord
from .normalize import _jsonable_source
from .validate import FlagCollector


def _row_fingerprint(raw: RawRecord) -> str:
    """Stable hash of ALL source cell values (order-independent by header)."""
    payload = {h: _jsonable_source(v) for h, v in raw.cells.items()}
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def mark_exact_duplicates(records: List[dict], raw_by_id: dict, fc: FlagCollector) -> None:
    """Detect exact-duplicate full-day rows; keep the first, exclude the rest."""
    groups: dict = {}
    for rec in records:
        raw = raw_by_id.get(rec["record_id"])
        if raw is None:
            continue
        fp = _row_fingerprint(raw)
        groups.setdefault(fp, []).append(rec)

    for fp, group in groups.items():
        if len(group) < 2:
            continue
        # Canonical = lowest Excel row (deterministic).
        group.sort(key=lambda r: r["provenance"]["excel_row"])
        canonical = group[0]
        for dup in group[1:]:
            dup["duplicate_of"] = canonical["record_id"]
            flag = fc.add(rule_code="EXACT_DUPLICATE", severity="warning",
                record_id=dup["record_id"], field=None,
                sheet=dup["provenance"]["sheet"], excel_row=dup["provenance"]["excel_row"],
                original_value=canonical["record_id"],
                explanation=f"Exact copy of record {canonical['record_id']} "
                            f"(Excel row {canonical['provenance']['excel_row']}).",
                effect="Excluded from totals by default; one canonical copy retained.")
            dup["flags"].append(flag["flag_id"])
            # Only exclude if it was otherwise going to be included.
            if dup["status"] == "included":
                dup["status"] = "excluded"
                dup["status_reason"] = "exact_duplicate"


def _overlap_fraction(a: dict, b: dict) -> Optional[float]:
    """Fraction of the shorter session's time window that overlaps the other."""
    sa, ea = a.get("start_fraction"), a.get("end_fraction")
    sb, eb = b.get("start_fraction"), b.get("end_fraction")
    if None in (sa, ea, sb, eb):
        return None
    # Ignore midnight-crossing sessions here (handled/flagged elsewhere).
    if ea < sa or eb < sb:
        return None
    lo = max(sa, sb)
    hi = min(ea, eb)
    overlap = max(0.0, hi - lo)
    shorter = min(ea - sa, eb - sb)
    if shorter <= 0:
        return None
    return overlap / shorter


def flag_possible_duplicates(records: List[dict], fc: FlagCollector,
                             overlap_fraction: float = 0.5) -> None:
    """Flag same-athlete/same-day sessions that overlap in time (stay included)."""
    by_key: dict = {}
    for rec in records:
        if rec["status"] not in ("included",):
            continue
        if rec["athlete_id"] is None or rec["date_resolved"] is None:
            continue
        by_key.setdefault((rec["athlete_id"], rec["date_resolved"]), []).append(rec)

    for (aid, date), group in by_key.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                frac = _overlap_fraction(group[i], group[j])
                if frac is not None and frac >= overlap_fraction:
                    a, b = group[i], group[j]
                    flag = fc.add(rule_code="POSSIBLE_DUPLICATE_OVERLAP", severity="warning",
                        record_id=b["record_id"], field="start_time/end_time",
                        sheet=b["provenance"]["sheet"], excel_row=b["provenance"]["excel_row"],
                        original_value={"overlap_fraction": round(frac, 3),
                                        "other_record": a["record_id"]},
                        explanation=f"Session time window overlaps {a['record_id']} by "
                                    f"{frac*100:.0f}% for athlete {aid} on {date}.",
                        effect="Both sessions remain INCLUDED pending review (distinct by default).")
                    b["flags"].append(flag["flag_id"])
                    a["flags"].append(flag["flag_id"])
