"""Structured quality flags, duplicate handling and manual include/exclude overrides.

Every flag: flag_id, rule_code, severity (error|warning|info), record_id, field,
sheet, excel_row, original_value, explanation, aggregation_effect.
Flag IDs are derived from (record, rule, field) so they are stable across reprocessing.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations
from typing import Dict, List, Optional

from .config import Config
from .normalize import PRIMARY_METRICS, _jsonable

SEVERITIES = ("error", "warning", "info")

METRIC_LABELS = {
    "duration_min": "Duration", "trimp": "TRIMP", "movement_load": "Movement Load",
    "hit_min": "High-intensity time",
}
METRIC_SOURCE_KEY = {"duration_min": "duration", "hit_min": "hit", "trimp": "trimp",
                     "movement_load": "movement_load"}


class FlagCollector:
    def __init__(self):
        self._flags: Dict[str, dict] = {}

    def add(self, rule_code: str, severity: str, explanation: str, effect: str,
            record: Optional[dict] = None, field: Optional[str] = None, original_value=None) -> dict:
        assert severity in SEVERITIES
        rid = record["record_id"] if record else None
        fid = f"{rid or 'dataset'}/{rule_code}" + (f"/{field}" if field else "")
        flag = {
            "flag_id": fid,
            "rule_code": rule_code,
            "severity": severity,
            "record_id": rid,
            "field": field,
            "sheet": record["provenance"]["sheet"] if record else None,
            "excel_row": record["provenance"]["excel_row"] if record else None,
            "original_value": _jsonable(original_value),
            "explanation": explanation,
            "aggregation_effect": effect,
        }
        if fid not in self._flags:
            self._flags[fid] = flag
            if record is not None:
                record["flag_ids"].append(fid)
        return self._flags[fid]

    @property
    def flags(self) -> List[dict]:
        order = {s: i for i, s in enumerate(SEVERITIES)}
        return sorted(self._flags.values(),
                      key=lambda f: (order[f["severity"]], f["sheet"] or "", f["record_id"] or "",
                                     f["rule_code"], f["field"] or ""))


def _reject(rec: dict, reason: str):
    rec["status"] = "rejected"
    rec["status_reason"] = reason


# ---------------------------------------------------------------- sessions --

def _systematic_missing(records: List[dict]) -> Dict[tuple, tuple]:
    """(measurement type, metric) pairs where the source essentially never records the metric.

    e.g. this export has no Movement Load for any Game session. That is a property of the
    source, not a per-session data problem, so it is reported as info rather than a warning.
    """
    totals: Counter = Counter()
    missing: Counter = Counter()
    for r in records:
        for key in PRIMARY_METRICS:
            totals[(r["measurement_type"], key)] += 1
            if r["parse_problems"].get(key) == "missing":
                missing[(r["measurement_type"], key)] += 1
    return {k: (missing[k], n) for k, n in totals.items() if n >= 5 and missing[k] / n >= 0.9}


def validate_sessions(records: List[dict], config: Config, fc: FlagCollector) -> None:
    t = config.thresholds
    systematic = _systematic_missing(records)
    for rec in records:
        src = rec["source_values"]
        if rec["athlete_id"] is None:
            fc.add("MISSING_ATHLETE", "error", "No athlete name in this row, so it cannot be "
                   "assigned to anyone.", "Record kept for review but excluded from daily aggregation.",
                   rec, "athlete", src.get("athlete"))
            _reject(rec, "missing_athlete")
        if rec["date"] is None:
            reason = rec["date_error"] or "missing_date"
            fc.add("MISSING_OR_INVALID_DATE", "error",
                   f"The date could not be resolved ({reason.replace('_', ' ')}).",
                   "Record kept for review but excluded from daily aggregation.",
                   rec, "date", src.get("date"))
            if rec["status"] != "rejected":
                _reject(rec, reason)

        if rec["session_bucket"] == "other":
            fc.add("UNEXPECTED_MEASUREMENT_TYPE", "warning",
                   f"Measurement type {rec['measurement_type']!r} is not one of "
                   f"{', '.join(config.known_measurement_types)}.",
                   "Included in daily totals under the 'other/unknown' breakdown.",
                   rec, "measurement_type", src.get("measurement_type"))
        if rec["analysis_period"] not in (None, "Measurement"):
            fc.add("UNEXPECTED_ANALYSIS_PERIOD", "info",
                   f"Analysis period is {rec['analysis_period']!r} rather than 'Measurement'.",
                   "No effect; recorded for review.", rec, "analysis_period", src.get("analysis_period"))

        m = rec["metrics"]
        for key in PRIMARY_METRICS:
            prob = rec["parse_problems"].get(key)
            label = METRIC_LABELS[key]
            orig = src.get(METRIC_SOURCE_KEY[key])
            if prob == "column_unavailable":
                continue                        # reported once at dataset level
            if prob == "missing" and (rec["measurement_type"], key) in systematic:
                miss, n = systematic[(rec["measurement_type"], key)]
                fc.add("METRIC_NOT_RECORDED_FOR_TYPE", "info",
                       f"{label} is empty for {miss} of {n} '{rec['measurement_type']}' sessions in this "
                       "file, so the source system does not appear to record it for this session type.",
                       f"{label} is unknown (null, not zero) for this session; daily {label} is marked "
                       "partial or missing. Other metrics of the session still count.", rec, key, orig)
            elif prob == "missing":
                code = "MISSING_DURATION" if key == "duration_min" else "MISSING_PRIMARY_METRIC"
                fc.add(code, "warning", f"{label} is empty for this session.",
                       f"{label} is unknown for this session; daily {label} is marked partial or "
                       "missing. Other metrics of the session still count.", rec, key, orig)
            elif prob in ("non_numeric", "non_finite"):
                fc.add("NON_NUMERIC_VALUE" if prob == "non_numeric" else "NON_FINITE_VALUE", "warning",
                       f"{label} value {orig!r} is not a usable number.",
                       f"Treated as missing (null) for {label} only; other metrics still count.",
                       rec, key, orig)
            elif m[key] is not None and m[key] < 0:
                code = "NEGATIVE_DURATION" if key == "duration_min" else "NEGATIVE_METRIC"
                fc.add(code, "error", f"{label} is negative ({m[key]:.2f}), which is impossible.",
                       f"Treated as missing (null) for {label} only; other metrics still count.",
                       rec, key, orig)
                m[key] = None
                rec["parse_problems"][key] = "negative"

        dur = m["duration_min"]
        if dur is not None:
            if dur == 0:
                fc.add("ZERO_DURATION", "warning", "Session duration is zero.",
                       "Zero is kept as recorded; TRIMP per minute cannot use it as a denominator.",
                       rec, "duration_min", src.get("duration"))
            elif dur < t.min_session_minutes or dur > t.max_session_minutes:
                fc.add("IMPLAUSIBLE_DURATION", "warning",
                       f"Duration {dur:.1f} min is outside the screening range "
                       f"{t.min_session_minutes:g}–{t.max_session_minutes:g} min. Plausible but unusual.",
                       "Included as recorded; please review.", rec, "duration_min", src.get("duration"))
        hit = m["hit_min"]
        if hit is not None and dur is not None and hit > dur + t.hit_tolerance_minutes:
            fc.add("HIT_EXCEEDS_DURATION", "warning",
                   f"High-intensity time ({hit:.1f} min) exceeds session duration ({dur:.1f} min) "
                   f"by more than the {t.hit_tolerance_minutes:g}-min rounding tolerance.",
                   "Both values included as recorded; please review.", rec, "hit_min", src.get("hit"))

        hr = rec["heart_rate"]
        for k, v in hr.items():
            if v is not None and not (t.hr_min_bpm <= v <= t.hr_max_bpm):
                fc.add("IMPLAUSIBLE_HR", "warning",
                       f"Heart rate {k.replace('_bpm', '')} = {v:g} bpm is outside the screening "
                       f"range {t.hr_min_bpm:g}–{t.hr_max_bpm:g} bpm.",
                       "Heart rate is not aggregated; workload metrics unaffected.", rec, k, v)
        lo, avg, pk = hr["min_bpm"], hr["avg_bpm"], hr["peak_bpm"]
        vals = [v for v in (lo, avg, pk) if v is not None]
        if len(vals) >= 2 and vals != sorted(vals):
            fc.add("HR_ORDER_INCONSISTENT", "warning",
                   f"Expected minimum ≤ average ≤ peak heart rate, got {lo} / {avg} / {pk}.",
                   "Heart rate is not aggregated; workload metrics unaffected.", rec, "heart_rate",
                   {"min": lo, "avg": avg, "peak": pk})
        for k in ("hr_avg", "hr_min", "hr_peak", "trimp_per_min", "avg_movement_intensity",
                  "source_acwr", "source_acute_load", "source_chronic_load"):
            prob = rec["parse_problems"].get(k)
            if prob:
                fc.add("NON_NUMERIC_VALUE", "info", f"{k} value {src.get(k)!r} is not a usable number.",
                       "Treated as missing (null); daily workload totals unaffected.", rec, k, src.get(k))

        if rec["crosses_midnight"]:
            fc.add("MIDNIGHT_CROSSING", "info",
                   f"Session starts {rec['start_time']} and ends {rec['end_time']} (after midnight).",
                   "Whole session attributed to the start date.", rec, "end_time", src.get("end_time"))
        span = rec["clock_span_min"]
        if span is not None and dur is not None and abs(span - dur) > t.time_duration_tolerance_minutes:
            fc.add("TIME_DURATION_MISMATCH", "warning",
                   f"Start/end times span {span:.1f} min but the duration column says {dur:.1f} min"
                   + (" (possibly an ambiguous midnight crossing)." if rec["crosses_midnight"] else "."),
                   "Duration column is used for totals; please review.", rec, "duration_min",
                   {"start": rec["start_time"], "end": rec["end_time"], "duration": src.get("duration")})


def check_dates(records: List[dict], fc: FlagCollector) -> None:
    """Cross-check resolved dates against the study-day index and chronological source order."""
    usable = [r for r in records if r["date"] and r["study_day_index"] is not None]
    by_index: Dict[object, Counter] = defaultdict(Counter)
    for r in usable:
        by_index[r["study_day_index"]][r["date"]] += 1
    majority = {i: c.most_common(1)[0][0] for i, c in by_index.items()}
    for r in usable:
        if r["date"] != majority[r["study_day_index"]]:
            r["study_day_consistent"] = False
            fc.add("DATE_DAYINDEX_CONFLICT", "warning",
                   f"Study day {r['study_day_index']} maps to {majority[r['study_day_index']]} in most "
                   f"rows, but this row resolves to {r['date']}.",
                   "Record still aggregated on its own resolved date; study-day index left blank "
                   "on that daily record.", r, "date", r["source_values"].get("date"))
    # Increasing study-day index must not go back in time.
    pairs = sorted(majority.items(), key=lambda kv: kv[0])
    for (i1, d1), (i2, d2) in zip(pairs, pairs[1:]):
        if d2 < d1:
            for r in usable:
                if r["study_day_index"] == i2:
                    r["study_day_consistent"] = False
                    fc.add("DATE_DAYINDEX_CONFLICT", "warning",
                           f"Study day {i2} resolves to {d2}, earlier than study day {i1} ({d1}). "
                           "Check the season year / rollover month.",
                           "Record still aggregated on its resolved date; please review.",
                           r, "date", r["source_values"].get("date"))
    # Source-order evidence: in a chronologically ordered sheet, big backward jumps are suspicious.
    for imp in sorted({r["import_id"] for r in records}):
        seq = [r for r in records if r["import_id"] == imp and r["date"]]
        steps = list(zip(seq, seq[1:]))
        if len(steps) < 10:
            continue
        backwards = [(a, b) for a, b in steps if b["date"] < a["date"]]
        if len(backwards) / len(steps) > 0.1:
            continue                                   # sheet is not chronological; no evidence
        for a, b in backwards:
            gap = (_d(a["date"]) - _d(b["date"])).days
            if gap > 31:
                fc.add("DATE_ORDER_ANOMALY", "warning",
                       f"The sheet is otherwise chronological, but this row ({b['date']}) is {gap} days "
                       f"earlier than the row above ({a['date']}). The year may be wrong.",
                       "Record aggregated on its resolved date; please review the year.",
                       b, "date", b["source_values"].get("date"))


def _d(iso: str):
    import datetime as dt
    return dt.date.fromisoformat(iso)


def check_gd_conflicts(records: List[dict], fc: FlagCollector) -> None:
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for r in records:
        if r["status"] == "included":
            groups[(r["athlete_id"], r["date"])].append(r)
    for (_, date), recs in sorted(groups.items()):
        labels = sorted({r["gd"] for r in recs if r["gd"]})
        if len(labels) > 1:
            for r in recs:
                fc.add("GD_CONFLICT", "warning",
                       f"Sessions on {date} carry different game-day labels: {', '.join(labels)}.",
                       "All labels kept on the daily record with gd_conflict = true.", r, "gd", r["gd"])


# -------------------------------------------------------------- duplicates --

def _fingerprint(rec: dict, raw_cells: dict) -> str:
    payload = json.dumps({k: _jsonable(v) for k, v in sorted(raw_cells.items())},
                         sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()


def mark_exact_duplicates(records: List[dict], raw_cells: Dict[str, dict], fc: FlagCollector) -> None:
    """Identical source rows: keep the first as canonical, exclude the copies (kept, not deleted)."""
    first: Dict[str, dict] = {}
    for rec in records:                        # records are in (import order, excel row) order
        fp = _fingerprint(rec, raw_cells[rec["record_id"]])
        rec["fingerprint"] = fp
        if fp not in first:
            first[fp] = rec
            continue
        canon = first[fp]
        rec["duplicate_of"] = canon["record_id"]
        canon.setdefault("duplicate_copies", []).append(rec["record_id"])
        where = (f"row {canon['provenance']['excel_row']}" if canon["import_id"] == rec["import_id"]
                 else f"row {canon['provenance']['excel_row']} of {canon['provenance']['file']}")
        fc.add("EXACT_DUPLICATE", "warning",
               f"Every source value is identical to {where} ({canon['record_id']}).",
               "Preserved but excluded from totals so the session counts once.", rec, None,
               {"duplicate_of": canon["record_id"]})
        if rec["status"] == "included":
            rec["status"] = "excluded"
            rec["status_reason"] = "exact_duplicate"


def _interval(r: dict):
    from .normalize import clock_minutes
    s = r["start_time"]
    if s is None or r["clock_span_min"] is None:
        return None
    start = clock_minutes(s)
    return start, start + r["clock_span_min"]


def flag_possible_duplicates(records: List[dict], config: Config, fc: FlagCollector) -> None:
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for r in records:
        if r["status"] == "included":
            groups[(r["athlete_id"], r["date"])].append(r)
    for _, recs in sorted(groups.items()):
        for a, b in combinations(recs, 2):
            ia, ib = _interval(a), _interval(b)
            if ia is None or ib is None:
                continue
            overlap = min(ia[1], ib[1]) - max(ia[0], ib[0])
            shortest = min(ia[1] - ia[0], ib[1] - ib[0])
            same_start = a["start_time"] == b["start_time"]
            if same_start or (shortest > 0 and overlap / shortest >= config.thresholds.overlap_fraction):
                why = ("start at the same time" if same_start
                       else f"overlap by {overlap:.0f} min ({overlap / shortest:.0%} of the shorter one)")
                for x, y in ((a, b), (b, a)):
                    x.setdefault("possible_duplicate_of", []).append(y["record_id"])
                    fc.add("POSSIBLE_DUPLICATE_OVERLAP", "warning",
                           f"This session and {y['record_id']} (row {y['provenance']['excel_row']}) "
                           f"{why} but are not identical.",
                           "Both stay included until reviewed; exclude one in duplicate review if it "
                           "is the same session recorded twice.", x, "start_time",
                           {"start": x["start_time"], "end": x["end_time"]})


def apply_overrides(records: List[dict], overrides: Dict[str, dict], fc: FlagCollector) -> None:
    by_id = {r["record_id"]: r for r in records}
    for rid in sorted(overrides):
        ov = overrides[rid]
        rec = by_id.get(rid)
        if rec is None:
            continue
        if rec["status"] == "rejected":
            fc.add("OVERRIDE_IGNORED", "warning",
                   "This record has no usable athlete or date, so it cannot be included.",
                   "Override ignored.", rec, None, ov)
            continue
        rec["override"] = {"action": ov["action"], "reason": ov.get("reason", "")}
        rec["status"] = "included" if ov["action"] == "include" else "excluded"
        rec["status_reason"] = f"manual_override: {ov.get('reason', '')}".strip()
        fc.add("MANUAL_OVERRIDE", "info",
               f"Manually {ov['action']}d. Reason: {ov.get('reason') or '(none given)'}",
               f"Record {'included in' if ov['action'] == 'include' else 'excluded from'} daily totals.",
               rec, None, ov)


# ---------------------------------------------------------------- wellness --

def validate_wellness(records: List[dict], known_athletes: set, fc: FlagCollector) -> None:
    for rec in records:
        if rec["athlete_id"] is None:
            fc.add("WELLNESS_MISSING_ATHLETE", "warning", "Wellness row has no athlete name.",
                   "Kept for review; not joined to any daily record.", rec, "athlete",
                   rec["source_values"].get("athlete"))
            _reject(rec, "missing_athlete")
        if rec["date"] is None:
            fc.add("WELLNESS_INVALID_DATE", "warning",
                   f"Wellness date could not be resolved ({rec['date_error']}).",
                   "Kept for review; not joined to any daily record.", rec, "date",
                   rec["source_values"].get("date"))
            if rec["status"] != "rejected":
                _reject(rec, rec["date_error"] or "missing_date")
        for k, prob in rec["parse_problems"].items():
            fc.add("NON_NUMERIC_VALUE", "info", f"Wellness {k} value is not a usable number.",
                   "Stored as null; never filled with zero.", rec, k, rec["source_values"].get(k))
        if rec["athlete_id"] and rec["athlete_id"] not in known_athletes:
            fc.add("WELLNESS_UNKNOWN_ATHLETE", "info",
                   f"{rec['athlete_label']!r} has wellness data but no workload sessions.",
                   "Wellness kept; no daily workload record to attach it to.", rec, "athlete",
                   rec["source_values"].get("athlete"))
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for rec in records:
        if rec["status"] == "included":
            groups[(rec["athlete_id"], rec["date"])].append(rec)
    for recs in groups.values():
        if len(recs) > 1:
            for rec in recs:
                fc.add("WELLNESS_MULTIPLE_SAME_DAY", "info",
                       f"{len(recs)} wellness observations for this athlete on {rec['date']}.",
                       "All observations kept on the daily record; none summed or dropped.", rec)
