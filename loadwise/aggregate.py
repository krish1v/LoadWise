"""Athlete-specific daily aggregation with explicit completeness, plus history and schedule context.

Rules (see FIELD_DICTIONARY.md):
- Additive metrics are summed independently over *included* sessions.
- Every metric block reports value, valid_sessions, expected_sessions and completeness:
  complete (all sessions have it) | partial (some do; value is the known sum) |
  missing (none do; value null) | no_sessions (breakdown bucket has no sessions; value null).
- Derived ratios are computed only from complete inputs over the same sessions with a
  positive denominator. Session ratios are never averaged.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Dict, List, Optional

from .normalize import PEAK_METRICS, PRIMARY_METRICS

BUCKETS = ("training", "game", "other")


def metric_block(sessions: List[dict], key: str) -> dict:
    vals = [s["metrics"][key] for s in sessions]
    valid = [v for v in vals if v is not None]
    if not sessions:
        status = "no_sessions"
    elif len(valid) == len(sessions):
        status = "complete"
    elif valid:
        status = "partial"
    else:
        status = "missing"
    return {"value": sum(valid) if valid else None, "valid_sessions": len(valid),
            "expected_sessions": len(sessions), "completeness": status}


def peak_block(sessions: List[dict], key: str) -> dict:
    """Daily peak of a per-session peak metric: max over sessions that recorded it."""
    vals = [s["peak_intensity"][key] for s in sessions]
    valid = [v for v in vals if v is not None]
    block = metric_block([{"metrics": {key: v}} for v in vals], key)
    block["value"] = max(valid) if valid else None
    return block


def _peaks(recs: List[dict]) -> Dict[str, dict]:
    return {k: {**peak_block(recs, k),
                "by_bucket": {b: peak_block([r for r in recs if r["session_bucket"] == b], k)
                              for b in BUCKETS}}
            for k in PEAK_METRICS}


def _blocks(sessions: List[dict]) -> Dict[str, dict]:
    return {k: metric_block(sessions, k) for k in PRIMARY_METRICS}


def derived_ratio(numer: dict, denom: dict, numer_name: str, denom_name: str) -> dict:
    if numer["completeness"] != "complete" or denom["completeness"] != "complete":
        return {"value": None, "reason": f"{numer_name} and {denom_name} are not both complete over "
                                         "the same included sessions"}
    if denom["value"] is None or denom["value"] <= 0:
        return {"value": None, "reason": f"{denom_name} total is zero or negative"}
    return {"value": numer["value"] / denom["value"], "reason": None}


def _reconciles(total: dict, parts: List[dict]) -> bool:
    known = [p["value"] for p in parts if p["value"] is not None]
    t = total["value"]
    if t is None:
        return not known
    return abs(sum(known) - t) <= 1e-9 * max(1.0, abs(t)) and \
        sum(p["valid_sessions"] for p in parts) == total["valid_sessions"]


def build_daily_records(sessions: List[dict], wellness: List[dict]) -> List[dict]:
    included: Dict[tuple, List[dict]] = defaultdict(list)
    excluded: Dict[tuple, List[str]] = defaultdict(list)
    for s in sessions:
        if s["athlete_id"] is None or s["date"] is None:
            continue
        key = (s["athlete_id"], s["date"])
        (included[key].append(s) if s["status"] == "included" else excluded[key].append(s["record_id"]))
    well: Dict[tuple, List[dict]] = defaultdict(list)
    for w in wellness:
        if w["status"] == "included":
            well[(w["athlete_id"], w["date"])].append(w)

    daily = []
    for (aid, date), recs in sorted(included.items()):
        recs = sorted(recs, key=lambda r: (r["start_time"] or "", r["record_id"]))
        totals = _blocks(recs)
        breakdown = {b: _blocks([r for r in recs if r["session_bucket"] == b]) for b in BUCKETS}
        breakdown_counts = {b: sum(r["session_bucket"] == b for r in recs) for b in BUCKETS}
        indices = {r["study_day_index"] for r in recs
                   if r["study_day_index"] is not None and r.get("study_day_consistent", True)}
        all_indices = {r["study_day_index"] for r in recs if r["study_day_index"] is not None}
        gd_labels = sorted({r["gd"] for r in recs if r["gd"]})
        flag_ids = sorted({f for r in recs for f in r["flag_ids"]})
        partial = [k for k, b in totals.items() if b["completeness"] != "complete"]
        daily.append({
            "daily_id": f"{aid}:{date}",
            "athlete_id": aid,
            "athlete_label": recs[0]["athlete_label"],
            "date": date,
            "study_day_index": next(iter(indices)) if len(indices) == 1 and len(all_indices) == 1 else None,
            "study_day_index_conflict": len(all_indices) > 1 or len(indices) != len(all_indices),
            "session_count": len(recs),
            "session_counts_by_type": breakdown_counts,
            "source_record_ids": [r["record_id"] for r in recs],
            "excluded_record_ids": sorted(excluded.get((aid, date), [])),
            "totals": totals,
            "breakdown": breakdown,
            "reconciles": {k: _reconciles(totals[k], [breakdown[b][k] for b in BUCKETS])
                           for k in PRIMARY_METRICS},
            "peak_intensity": _peaks(recs),
            "derived": {
                "efficiency": derived_ratio(totals["movement_load"], totals["trimp"],
                                            "Movement Load", "TRIMP"),
                "trimp_per_min": derived_ratio(totals["trimp"], totals["duration_min"],
                                               "TRIMP", "duration"),
            },
            "source_session_ratios": [
                {"record_id": r["record_id"], "trimp_per_min": r["source_ratios"]["trimp_per_min"]}
                for r in recs],
            "avg_movement_intensity": {
                "session_values": [{"record_id": r["record_id"],
                                    "value": r["source_ratios"]["avg_movement_intensity"]} for r in recs],
                "daily_value": None,
                "reason": "No documented aggregation method for this source-defined metric; "
                          "session values are preserved instead.",
            },
            "schedule": {
                "gd_labels": gd_labels,
                "gd_conflict": len(gd_labels) > 1,
                "has_game_session": breakdown_counts["game"] > 0,
            },
            "wellness": [{"record_id": w["record_id"], "excel_row": w["provenance"]["excel_row"],
                          **w["values"]} for w in sorted(well.get((aid, date), []),
                                                         key=lambda w: w["record_id"])],
            "quality": {
                "incomplete_metrics": partial,
                "flag_ids": flag_ids,
            },
        })
    return daily


def _gaps(dates: List[str]) -> List[dict]:
    gaps = []
    ds = [dt.date.fromisoformat(d) for d in dates]
    for a, b in zip(ds, ds[1:]):
        if (b - a).days > 1:
            gaps.append({"from": (a + dt.timedelta(days=1)).isoformat(),
                         "to": (b - dt.timedelta(days=1)).isoformat(),
                         "days": (b - a).days - 1, "status": "unobserved"})
    return gaps


def build_athletes(sessions: List[dict], wellness: List[dict], daily: List[dict]) -> List[dict]:
    info: Dict[str, dict] = {}
    for rec, sheet in [(s, "sessions") for s in sessions] + [(w, "wellness") for w in wellness]:
        aid = rec["athlete_id"]
        if aid is None:
            continue
        a = info.setdefault(aid, {"athlete_id": aid, "labels": set(), "raw_labels": set(),
                                  "sheets": set(), "session_records": 0, "wellness_records": 0})
        a["labels"].add(rec["athlete_label"])
        a["raw_labels"].add(str(rec["source_values"].get("athlete")))
        a["sheets"].add(sheet)
        a["session_records" if sheet == "sessions" else "wellness_records"] += 1
    by_athlete: Dict[str, List[str]] = defaultdict(list)
    for d in daily:
        by_athlete[d["athlete_id"]].append(d["date"])
    out = []
    for aid, a in info.items():
        dates = sorted(by_athlete.get(aid, []))
        out.append({
            "athlete_id": aid,
            "label": sorted(a["labels"])[0],
            "source_label_variants": sorted(a["raw_labels"]),
            "sheets": sorted(a["sheets"]),
            "session_records": a["session_records"],
            "wellness_records": a["wellness_records"],
            "history": {
                "first_date": dates[0] if dates else None,
                "last_date": dates[-1] if dates else None,
                "observed_days": len(dates),
                "observed_dates": dates,
                "gaps": _gaps(dates),
                "gap_policy": "Gaps are days with no recorded session. They are NOT zero load and "
                              "NOT confirmed rest days; downstream rolling metrics must choose a policy.",
            },
        })
    return sorted(out, key=lambda a: (a["label"].casefold(), a["athlete_id"]))


def build_schedule_context(sessions: List[dict]) -> dict:
    inc = [s for s in sessions if s["status"] == "included"]
    dates = sorted({s["date"] for s in inc})
    game_dates: Dict[str, set] = defaultdict(set)
    gd_by_date: Dict[str, set] = defaultdict(set)
    for s in inc:
        if s["session_bucket"] == "game":
            game_dates[s["date"]].add(s["athlete_id"])
        if s["gd"]:
            gd_by_date[s["date"]].add(s["gd"])
    no_data = []
    if dates:
        d, end = dt.date.fromisoformat(dates[0]), dt.date.fromisoformat(dates[-1])
        observed = set(dates)
        while d <= end:
            if d.isoformat() not in observed:
                no_data.append(d.isoformat())
            d += dt.timedelta(days=1)
    return {
        "note": "Observed context only: derived from recorded game sessions and GD labels. This is "
                "not a complete or future schedule. Dates without data are unobserved, not confirmed rest.",
        "observed_range": {"first": dates[0] if dates else None, "last": dates[-1] if dates else None},
        "game_session_dates": [{"date": d, "athletes_with_game_session": len(a)}
                               for d, a in sorted(game_dates.items())],
        "gd_labels_by_date": {d: sorted(v) for d, v in sorted(gd_by_date.items())},
        "team_dates_without_data": no_data,
    }
