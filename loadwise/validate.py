"""Validation rules producing structured, severity-tagged quality flags.

Design principles (spec section 4):
  * Flags are structured: id, rule code, severity, provenance, original value,
    plain-language explanation, and the effect on aggregation.
  * Thresholds are conservative + configurable; plausible-but-unusual values are
    warnings, never confirmed errors.
  * A missing/invalid single metric nulls *only that metric* -- never the whole
    session's other valid metrics.
  * Records lacking a usable athlete/date are *rejected* (kept out of daily
    aggregation) but remain fully visible.
"""

from __future__ import annotations

from typing import List, Optional

from . import schema
from .config import Config
from .dates import check_day_index_consistency


class FlagCollector:
    """Accumulates flags with deterministic sequential IDs."""

    def __init__(self):
        self._flags: List[dict] = []

    def add(self, *, rule_code: str, severity: str, record_id: Optional[str],
            field: Optional[str], sheet: Optional[str], excel_row: Optional[int],
            original_value, explanation: str, effect: str) -> dict:
        flag = {
            "flag_id": f"F{len(self._flags) + 1:05d}",
            "rule_code": rule_code,
            "severity": severity,
            "record_id": record_id,
            "field": field,
            "sheet": sheet,
            "excel_row": excel_row,
            "original_value": _safe(original_value),
            "explanation": explanation,
            "effect": effect,
        }
        self._flags.append(flag)
        return flag

    @property
    def flags(self) -> List[dict]:
        return self._flags


def _safe(v):
    import datetime as _dt
    import math
    if isinstance(v, _dt.timedelta):
        return f"{v.total_seconds()}s"
    if isinstance(v, (_dt.time, _dt.date, _dt.datetime)):
        return v.isoformat()
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    return v


def _attach(rec: dict, flag: dict):
    rec["flags"].append(flag["flag_id"])


def validate_full_day(records: List[dict], config: Config, fc: FlagCollector) -> None:
    """Validate normalized Full-Day records in place (sets status, appends flags)."""
    th = config.thresholds
    for rec in records:
        prov = rec["provenance"]
        sheet, row, rid = prov["sheet"], prov["excel_row"], rec["record_id"]
        norm = rec["normalized"]

        # --- Identity / date: rejection-worthy. ---
        if rec["athlete_id"] is None:
            _attach(rec, fc.add(rule_code="MISSING_ATHLETE", severity="error",
                record_id=rid, field="athlete_label", sheet=sheet, excel_row=row,
                original_value=rec["athlete_label_raw"],
                explanation="Record has no usable athlete identifier.",
                effect="Rejected: cannot enter daily aggregation (still visible)."))
            rec["status"] = "rejected"
            rec["status_reason"] = "missing_athlete"

        if rec["date_resolved"] is None:
            reason = rec.get("date_error") or "missing_date"
            sev = "error"
            _attach(rec, fc.add(rule_code="MISSING_OR_INVALID_DATE", severity=sev,
                record_id=rid, field="date_raw", sheet=sheet, excel_row=row,
                original_value=rec["date_raw"],
                explanation=f"Date could not be resolved ({reason}).",
                effect="Rejected: cannot enter daily aggregation (still visible)."))
            if rec["status"] != "rejected":
                rec["status"] = "rejected"
                rec["status_reason"] = reason

        # --- Measurement type / analysis period. ---
        if rec["measurement_bucket"] == "other":
            _attach(rec, fc.add(rule_code="UNEXPECTED_MEASUREMENT_TYPE", severity="warning",
                record_id=rid, field="measurement_type", sheet=sheet, excel_row=row,
                original_value=rec["measurement_type_raw"],
                explanation="Measurement type is not 'Training' or 'Game'.",
                effect="Counted under the 'other/unknown' daily breakdown."))
        if (rec["analysis_period"] is not None
                and rec["analysis_period"] not in config.expected_analysis_periods):
            _attach(rec, fc.add(rule_code="UNEXPECTED_ANALYSIS_PERIOD", severity="info",
                record_id=rid, field="analysis_period", sheet=sheet, excel_row=row,
                original_value=rec["analysis_period"],
                explanation="Analysis period differs from the expected 'Measurement'.",
                effect="No effect on aggregation; informational."))

        # --- Workload numeric validity (null only the offending metric). ---
        for key in schema.NONNEGATIVE_METRICS:
            v = norm.get(key)
            raw_present = rec["source"].get(key + "_raw") is not None
            if v is None and raw_present:
                _attach(rec, fc.add(rule_code="NON_NUMERIC_METRIC", severity="warning",
                    record_id=rid, field=key, sheet=sheet, excel_row=row,
                    original_value=rec["source"].get(key + "_raw"),
                    explanation=f"'{key}' is present but not a finite number.",
                    effect="This metric treated as missing; other metrics unaffected."))
            elif v is not None and v < 0:
                _attach(rec, fc.add(rule_code="NEGATIVE_METRIC", severity="error",
                    record_id=rid, field=key, sheet=sheet, excel_row=row,
                    original_value=v,
                    explanation=f"'{key}' is negative ({v:.4g}), which is invalid.",
                    effect="This metric nulled for aggregation; other metrics unaffected."))
                norm[key] = None  # drop just this metric

        # --- Missing primary metrics. ---
        for key in schema.PRIMARY_METRICS:
            if norm.get(key) is None:
                _attach(rec, fc.add(rule_code="MISSING_PRIMARY_METRIC", severity="warning",
                    record_id=rid, field=key, sheet=sheet, excel_row=row,
                    original_value=None,
                    explanation=f"Primary metric '{key}' is missing for this session.",
                    effect="Daily total for this metric becomes partial (or null if all miss)."))

        # --- Duration checks. ---
        dur = norm.get("duration_min")
        if dur is None:
            _attach(rec, fc.add(rule_code="MISSING_DURATION", severity="warning",
                record_id=rid, field="duration_min", sheet=sheet, excel_row=row,
                original_value=rec["source"].get("duration_min_raw"),
                explanation="Session duration is missing.",
                effect="Duration-based ratios for the day may be unavailable."))
        elif dur == 0:
            _attach(rec, fc.add(rule_code="ZERO_DURATION", severity="warning",
                record_id=rid, field="duration_min", sheet=sheet, excel_row=row,
                original_value=0,
                explanation="Session duration is zero.",
                effect="Zero preserved; excluded as a positive denominator for ratios."))
        elif dur < 0:
            _attach(rec, fc.add(rule_code="NEGATIVE_DURATION", severity="error",
                record_id=rid, field="duration_min", sheet=sheet, excel_row=row,
                original_value=dur,
                explanation="Session duration is negative.",
                effect="Duration nulled for aggregation."))
            norm["duration_min"] = None
            dur = None
        elif not (th.min_duration_min <= dur <= th.max_duration_min):
            _attach(rec, fc.add(rule_code="IMPLAUSIBLE_DURATION", severity="warning",
                record_id=rid, field="duration_min", sheet=sheet, excel_row=row,
                original_value=round(dur, 4),
                explanation=f"Duration {dur:.1f} min is outside the screening range "
                            f"[{th.min_duration_min}, {th.max_duration_min}] min.",
                effect="Value retained; flagged for review."))

        # --- High-intensity minutes vs duration (with rounding tolerance). ---
        hit = norm.get("high_intensity_min")
        if hit is not None and dur is not None and hit > dur + th.hit_tolerance_min:
            _attach(rec, fc.add(rule_code="HIT_EXCEEDS_DURATION", severity="warning",
                record_id=rid, field="high_intensity_min", sheet=sheet, excel_row=row,
                original_value=round(hit, 4),
                explanation=f"High-intensity minutes ({hit:.1f}) exceed session duration "
                            f"({dur:.1f}) beyond the {th.hit_tolerance_min} min tolerance.",
                effect="Both values retained; flagged for review."))

        # --- TRIMP/min source magnitude screen. ---
        tpm = norm.get("trimp_per_min_source")
        if tpm is not None and tpm > th.max_trimp_per_min:
            _attach(rec, fc.add(rule_code="IMPLAUSIBLE_TRIMP_PER_MIN", severity="warning",
                record_id=rid, field="trimp_per_min_source", sheet=sheet, excel_row=row,
                original_value=round(tpm, 4),
                explanation=f"Source TRIMP/min {tpm:.2f} exceeds screening max {th.max_trimp_per_min}.",
                effect="Value retained; flagged for review."))

        # --- Workload magnitude screens. ---
        if norm.get("trimp") is not None and norm["trimp"] > th.max_trimp:
            _attach(rec, fc.add(rule_code="IMPLAUSIBLE_TRIMP", severity="warning",
                record_id=rid, field="trimp", sheet=sheet, excel_row=row,
                original_value=round(norm["trimp"], 4),
                explanation=f"TRIMP {norm['trimp']:.1f} exceeds screening max {th.max_trimp}.",
                effect="Value retained; flagged for review."))
        if norm.get("movement_load") is not None and norm["movement_load"] > th.max_movement_load:
            _attach(rec, fc.add(rule_code="IMPLAUSIBLE_MOVEMENT_LOAD", severity="warning",
                record_id=rid, field="movement_load", sheet=sheet, excel_row=row,
                original_value=round(norm["movement_load"], 4),
                explanation=f"Movement Load {norm['movement_load']:.1f} exceeds screening max "
                            f"{th.max_movement_load}.",
                effect="Value retained; flagged for review."))

        # --- Heart-rate plausibility + ordering. ---
        avg_hr, min_hr, peak_hr = norm.get("avg_hr"), norm.get("min_hr"), norm.get("peak_hr")
        for key, val in (("avg_hr", avg_hr), ("min_hr", min_hr), ("peak_hr", peak_hr)):
            if val is not None and not (th.hr_min_bpm <= val <= th.hr_max_bpm):
                _attach(rec, fc.add(rule_code="IMPLAUSIBLE_HR", severity="warning",
                    record_id=rid, field=key, sheet=sheet, excel_row=row,
                    original_value=round(val, 2),
                    explanation=f"{key} {val:.0f} bpm outside screening range "
                                f"[{th.hr_min_bpm}, {th.hr_max_bpm}] bpm.",
                    effect="HR metric retained; flagged for review (not a workload metric)."))
        hrs = [h for h in (min_hr, avg_hr, peak_hr) if h is not None]
        if len(hrs) >= 2:
            ok = (min_hr is None or avg_hr is None or min_hr <= avg_hr) and \
                 (avg_hr is None or peak_hr is None or avg_hr <= peak_hr) and \
                 (min_hr is None or peak_hr is None or min_hr <= peak_hr)
            if not ok:
                _attach(rec, fc.add(rule_code="HR_ORDER_INCONSISTENT", severity="warning",
                    record_id=rid, field="min/avg/peak_hr", sheet=sheet, excel_row=row,
                    original_value={"min": min_hr, "avg": avg_hr, "peak": peak_hr},
                    explanation="Heart rates violate min <= avg <= peak.",
                    effect="HR metrics retained; flagged for review."))

    # --- Cross-record: date vs study-day index consistency. ---
    resolved_rows = []
    index_lookup = {}
    for rec in records:
        if rec["date_resolved"] is not None and rec["day_index"] is not None:
            import datetime as _dt
            d = _dt.date.fromisoformat(rec["date_resolved"])
            resolved_rows.append({"record_id": rec["record_id"], "excel_row": rec["provenance"]["excel_row"],
                                  "date": d, "day_index": rec["day_index"]})
            index_lookup.setdefault(rec["record_id"], rec)
    for issue in check_day_index_consistency(resolved_rows):
        fc.add(rule_code="DATE_DAYINDEX_CONFLICT", severity="warning",
               record_id=issue.get("record_id"), field="day_index/date",
               sheet="Full Day", excel_row=issue.get("excel_row"),
               original_value={k: v for k, v in issue.items() if k not in ("record_id", "excel_row", "reason")},
               explanation=f"Study-day index and resolved date disagree ({issue['reason']}).",
               effect="Dates flagged for review; not silently re-assigned.")


def validate_wellness(records: List[dict], config: Config, fc: FlagCollector) -> None:
    for rec in records:
        prov = rec["provenance"]
        sheet, row, rid = prov["sheet"], prov["excel_row"], rec["record_id"]
        if rec["athlete_id"] is None:
            _attach(rec, fc.add(rule_code="WELLNESS_MISSING_ATHLETE", severity="warning",
                record_id=rid, field="athlete_label", sheet=sheet, excel_row=row,
                original_value=rec["athlete_label_raw"],
                explanation="Wellness record has no usable athlete identifier.",
                effect="Cannot be joined to a daily record."))
            rec["status"] = "unjoinable"
        if rec["date_resolved"] is None:
            _attach(rec, fc.add(rule_code="WELLNESS_MISSING_DATE", severity="warning",
                record_id=rid, field="date_raw", sheet=sheet, excel_row=row,
                original_value=rec["date_raw"],
                explanation="Wellness record date could not be resolved.",
                effect="Cannot be joined to a daily record."))
            rec["status"] = "unjoinable"
