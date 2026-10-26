"""Athlete-specific daily aggregation.

One daily record per resolved (athlete, date), combining all INCLUDED sessions.
Every additive metric carries explicit completeness (value, valid/expected
session counts, status). Derived ratios are computed only from complete, matched
inputs with a positive denominator -- never by averaging session ratios.
"""

from __future__ import annotations

import datetime as _dt
from typing import Dict, List, Optional

from . import schema

_EPS = 1e-9


def _aggregate_metric(sessions: List[dict], key: str) -> dict:
    """Sum one additive metric across sessions, tracking completeness."""
    expected = len(sessions)
    contributing = [s["normalized"].get(key) for s in sessions]
    valid = [v for v in contributing if v is not None]
    valid_count = len(valid)
    if valid_count == 0:
        value, status = None, "missing"
    elif valid_count == expected:
        value, status = sum(valid), "complete"
    else:
        value, status = sum(valid), "partial"
    return {
        "value": value,
        "valid_sessions": valid_count,
        "expected_sessions": expected,
        "completeness": status,
    }


def _bucket_sessions(sessions: List[dict], bucket: str) -> List[dict]:
    return [s for s in sessions if s["measurement_bucket"] == bucket]


def _metric_block(sessions: List[dict]) -> Dict[str, dict]:
    return {key: _aggregate_metric(sessions, key) for key in schema.ADDITIVE_METRICS}


def _reconciles(total: dict, parts: List[dict]) -> bool:
    tv = total["value"] or 0.0
    pv = sum((p["value"] or 0.0) for p in parts)
    return abs(tv - pv) <= _EPS * max(1.0, abs(tv))


def _derived_ratio(numer: dict, denom: dict, label: str) -> dict:
    """Compute numer/denom only when BOTH are complete and denom.value > 0."""
    if numer["completeness"] != "complete" or denom["completeness"] != "complete":
        return {"value": None, "reason": f"inputs not complete over the same included sessions "
                f"(numerator={numer['completeness']}, denominator={denom['completeness']})"}
    if denom["value"] is None or denom["value"] <= 0:
        return {"value": None, "reason": "denominator is zero or non-positive"}
    if numer["value"] is None:
        return {"value": None, "reason": "numerator unavailable"}
    return {"value": numer["value"] / denom["value"], "reason": None}


def build_daily_records(full_day_records: List[dict],
                        wellness_records: List[dict]) -> List[dict]:
    """Build the chronological per-athlete daily dataset."""
    # Group INCLUDED sessions by (athlete_id, date).
    groups: Dict[tuple, List[dict]] = {}
    for rec in full_day_records:
        if rec["status"] != "included":
            continue
        if rec["athlete_id"] is None or rec["date_resolved"] is None:
            continue
        groups.setdefault((rec["athlete_id"], rec["date_resolved"]), []).append(rec)

    # Index wellness by (athlete_id, date) -- keep ALL observations.
    wellness_by_key: Dict[tuple, List[dict]] = {}
    for w in wellness_records:
        if w["athlete_id"] is None or w["date_resolved"] is None:
            continue
        wellness_by_key.setdefault((w["athlete_id"], w["date_resolved"]), []).append(w)

    daily: List[dict] = []
    for (aid, date), sessions in groups.items():
        sessions.sort(key=lambda s: (s.get("start_fraction") is None, s.get("start_fraction") or 0,
                                     s["provenance"]["excel_row"]))
        label = sessions[0]["athlete_label"]

        total = _metric_block(sessions)
        training = _metric_block(_bucket_sessions(sessions, "training"))
        game = _metric_block(_bucket_sessions(sessions, "game"))
        other = _metric_block(_bucket_sessions(sessions, "other"))

        reconciliation = {
            key: _reconciles(total[key], [training[key], game[key], other[key]])
            for key in schema.ADDITIVE_METRICS
        }

        efficiency = _derived_ratio(total["movement_load"], total["trimp"], "efficiency")
        trimp_per_min = _derived_ratio(total["trimp"], total["duration_min"], "trimp_per_min")

        # Average movement intensity: preserve session values; NO daily aggregate.
        ami_sessions = [
            {"record_id": s["record_id"], "value": s["normalized"].get("avg_movement_intensity_source")}
            for s in sessions
        ]
        ami_values = [a["value"] for a in ami_sessions if a["value"] is not None]
        avg_movement_intensity = {
            "daily_value": None,
            "reason": "No justified aggregation method for Average Movement Intensity; "
                      "session values preserved instead.",
            "session_values": ami_sessions,
            "session_mean_unweighted": (sum(ami_values) / len(ami_values)) if ami_values else None,
        }

        # Source-reported per-session ratios, preserved separately from calculated ones.
        source_session_ratios = [
            {"record_id": s["record_id"],
             "trimp_per_min_source": s["normalized"].get("trimp_per_min_source"),
             "source_acwr": s["source"].get("source_acwr"),
             "source_acute_training_load": s["source"].get("source_acute_training_load"),
             "source_chronic_training_load": s["source"].get("source_chronic_training_load")}
            for s in sessions
        ]

        # Day index: keep only if all sessions agree.
        day_indices = {s["day_index"] for s in sessions if s["day_index"] is not None}
        if len(day_indices) == 1:
            day_index, day_index_note = next(iter(day_indices)), None
        elif len(day_indices) == 0:
            day_index, day_index_note = None, "no study-day index on contributing sessions"
        else:
            day_index, day_index_note = None, f"conflicting study-day indices: {sorted(day_indices)}"

        # GD labels / game context.
        gd_labels = sorted({s["gd"] for s in sessions if s["gd"] is not None})
        game_records = [s["record_id"] for s in sessions if s["measurement_bucket"] == "game"]
        schedule = {
            "gd_labels": gd_labels,
            "gd_conflict": len(gd_labels) > 1,
            "has_game": len(game_records) > 0,
            "game_record_ids": game_records,
            "note": "Observed GD/game context only; not a complete forward schedule.",
        }

        # Wellness observations for the day (all of them).
        wells = wellness_by_key.get((aid, date), [])
        wellness_obs = [
            {"record_id": w["record_id"], "scores": w["scores"], "date_raw": str(w["date_raw"])}
            for w in wells
        ]

        # Completeness metadata.
        any_partial = any(total[k]["completeness"] == "partial" for k in schema.ADDITIVE_METRICS)
        all_complete = all(total[k]["completeness"] == "complete" for k in schema.ADDITIVE_METRICS)
        flag_ids = sorted({fid for s in sessions for fid in s["flags"]})

        daily.append({
            "daily_id": f"{aid}:{date}",
            "athlete_id": aid,
            "athlete_label": label,
            "date": date,
            "day_index": day_index,
            "day_index_note": day_index_note,
            "included_session_count": len(sessions),
            "source_record_ids": [s["record_id"] for s in sessions],
            "totals": total,
            "breakdown": {"training": training, "game": game, "other": other},
            "breakdown_reconciles": reconciliation,
            "derived": {
                "efficiency_calculated": efficiency,
                "trimp_per_min_calculated": trimp_per_min,
                "avg_movement_intensity": avg_movement_intensity,
            },
            "source_session_ratios": source_session_ratios,
            "wellness_observations": wellness_obs,
            "schedule_context": schedule,
            "completeness": {
                "all_additive_complete": all_complete,
                "any_partial": any_partial,
            },
            "quality_flag_ids": flag_ids,
        })

    # Chronological order per athlete.
    daily.sort(key=lambda d: (d["athlete_id"], d["date"]))
    return daily


def build_athlete_history(daily_records: List[dict]) -> List[dict]:
    """Expose observed dates and gaps per athlete for a future ACWR module.

    We never fabricate rest days: absent calendar dates between observations are
    reported as explicit gaps so a downstream module can apply its own
    (still-to-be-agreed) missing-day policy.
    """
    by_athlete: Dict[str, List[dict]] = {}
    for d in daily_records:
        by_athlete.setdefault(d["athlete_id"], []).append(d)

    histories = []
    for aid, recs in sorted(by_athlete.items()):
        recs = sorted(recs, key=lambda r: r["date"])
        observed = [r["date"] for r in recs]
        gaps = []
        for prev, cur in zip(recs, recs[1:]):
            dp = _dt.date.fromisoformat(prev["date"])
            dc = _dt.date.fromisoformat(cur["date"])
            delta = (dc - dp).days
            if delta > 1:
                gaps.append({
                    "after_date": prev["date"],
                    "before_date": cur["date"],
                    "missing_days": delta - 1,
                    "note": "Unobserved dates -- NOT assumed to be rest or zero load.",
                })
        histories.append({
            "athlete_id": aid,
            "athlete_label": recs[0]["athlete_label"],
            "observed_dates": observed,
            "observed_day_count": len(observed),
            "first_date": observed[0] if observed else None,
            "last_date": observed[-1] if observed else None,
            "gaps": gaps,
        })
    return histories
