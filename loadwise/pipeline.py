"""End-to-end orchestration: ingest -> normalize -> validate -> dedupe ->
aggregate -> export. This is the single reusable entry point for both the
Streamlit UI and other applications.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Optional, Union

from . import aggregate, duplicates, export, ingest, normalize, validate
from .config import SCHEMA_VERSION, Config
from .dates import rollover_preview, check_day_index_consistency
from .identity import IdentityMap
from .validate import FlagCollector


class SeasonYearRequired(Exception):
    """Raised when processing is attempted without a configured season start year.

    Carries an actionable, user-facing message. We never invent a year.
    """

    def __init__(self, sample_months=None):
        self.sample_months = sample_months or []
        msg = ("A season start year is required to resolve the workbook's day/month "
               "dates (which run September into January). Set Config.season_start_year "
               "to the calendar year the September records belong to. LoadWise will not "
               "default to the current year or guess.")
        super().__init__(msg)


@dataclass
class ProcessResult:
    """Everything a caller needs, in memory, plus the JSON-safe output object."""
    config: Config
    idmap: IdentityMap
    cleaned_records: List[dict]
    wellness_records: List[dict]
    daily_records: List[dict]
    athlete_history: List[dict]
    quality_flags: List[dict]
    rollover_preview: list
    day_index_issues: list
    output: dict
    raw_full_day: list = field(default_factory=list)
    raw_wellness: list = field(default_factory=list)

    def to_json(self, indent: Optional[int] = 2, include_raw: bool = True) -> str:
        return export.to_json(self.output, indent=indent, include_raw=include_raw)

    def to_daily_csv(self) -> str:
        return export.daily_to_csv(self.daily_records)


def _recompute_daily(result: ProcessResult) -> None:
    """Rebuild daily records + history + output after status overrides change."""
    result.daily_records = aggregate.build_daily_records(result.cleaned_records,
                                                         result.wellness_records)
    result.athlete_history = aggregate.build_athlete_history(result.daily_records)
    result.output = export.build_output(
        config=result.config, idmap=result.idmap,
        raw_full_day=result.raw_full_day, raw_wellness=result.raw_wellness,
        cleaned_records=result.cleaned_records, daily_records=result.daily_records,
        wellness_records=result.wellness_records, athlete_history=result.athlete_history,
        quality_flags=result.quality_flags, import_metadata=result.output["importMetadata"],
        rollover_preview=result.rollover_preview, day_index_issues=result.day_index_issues,
    )


def apply_override(result: ProcessResult, record_id: str, action: str,
                   reason: str = "") -> ProcessResult:
    """Apply a manual include/exclude override to one record and recompute.

    action: 'include' or 'exclude'. The decision + reason are recorded on the
    record and the affected daily outputs are recalculated.
    """
    if action not in ("include", "exclude"):
        raise ValueError("action must be 'include' or 'exclude'")
    for rec in result.cleaned_records:
        if rec["record_id"] == record_id:
            if rec["status"] == "rejected":
                raise ValueError("Cannot override a rejected record (no usable athlete/date).")
            rec["override"] = {"action": action, "reason": reason}
            rec["status"] = "included" if action == "include" else "excluded"
            rec["status_reason"] = f"manual_override:{action}" + (f" ({reason})" if reason else "")
            break
    else:
        raise KeyError(f"record_id not found: {record_id}")
    _recompute_daily(result)
    return result


def process_workbook(source: Union[str, bytes, io.BytesIO],
                     config: Config,
                     *,
                     file_label: Optional[str] = None,
                     existing_identity: Optional[dict] = None,
                     generated_at: Optional[str] = None) -> ProcessResult:
    """Run the full pipeline and return a ProcessResult.

    ``generated_at`` is injected (not read from the clock) so output is
    deterministic/idempotent in tests; the UI passes a real timestamp.
    Raises SeasonYearRequired if config.season_start_year is None.
    """
    if config.season_start_year is None:
        raise SeasonYearRequired()

    # 1. Ingest (raw, immutable, with provenance).
    sheets = ingest.ingest_workbook(source, file_label=file_label)
    full_day_si = sheets["full_day"]
    wellness_si = sheets["wellness"]

    # 2. Identity map (shared across both sheets, stable across uploads).
    idmap = IdentityMap(existing_identity)
    idmap.register_all(normalize.collect_labels(full_day_si, wellness_si))

    # 3. Normalize.
    cleaned = [normalize.normalize_full_day(r, config, idmap) for r in full_day_si.records]
    wellness = ([normalize.normalize_wellness(r, config, idmap) for r in wellness_si.records]
                if wellness_si.present else [])

    # 4. Validate.
    fc = FlagCollector()
    validate.validate_full_day(cleaned, config, fc)
    if wellness:
        validate.validate_wellness(wellness, config, fc)

    # 5. Duplicate handling.
    raw_by_id = {r.record_id: r for r in full_day_si.records}
    duplicates.mark_exact_duplicates(cleaned, raw_by_id, fc)
    duplicates.flag_possible_duplicates(cleaned, fc, config.overlap_warn_fraction)

    # 6. Aggregate.
    daily = aggregate.build_daily_records(cleaned, wellness)
    history = aggregate.build_athlete_history(daily)

    # Date/day-index issues for the configuration block.
    import datetime as _dt
    resolved_rows = [
        {"record_id": r["record_id"], "excel_row": r["provenance"]["excel_row"],
         "date": _dt.date.fromisoformat(r["date_resolved"]), "day_index": r["day_index"]}
        for r in cleaned if r["date_resolved"] and r["day_index"] is not None
    ]
    day_index_issues = check_day_index_consistency(resolved_rows)

    import_metadata = {
        "schemaVersion": SCHEMA_VERSION,
        "source_file": file_label or (source if isinstance(source, str) else "<uploaded>"),
        "generated_at": generated_at,  # None => deterministic; UI injects real time
        "full_day_sheet": {"name": full_day_si.name, "header_row": full_day_si.header_row,
                            "detected_records": len(full_day_si.records)},
        "wellness_sheet": {"name": wellness_si.name, "present": wellness_si.present,
                           "header_row": wellness_si.header_row,
                           "detected_records": len(wellness_si.records), "note": wellness_si.note},
        "identity_map": idmap.as_dict(),
    }

    output = export.build_output(
        config=config, idmap=idmap,
        raw_full_day=full_day_si.records, raw_wellness=wellness_si.records,
        cleaned_records=cleaned, daily_records=daily, wellness_records=wellness,
        athlete_history=history, quality_flags=fc.flags,
        import_metadata=import_metadata,
        rollover_preview=rollover_preview(config), day_index_issues=day_index_issues,
    )

    return ProcessResult(
        config=config, idmap=idmap, cleaned_records=cleaned, wellness_records=wellness,
        daily_records=daily, athlete_history=history, quality_flags=fc.flags,
        rollover_preview=rollover_preview(config), day_index_issues=day_index_issues,
        output=output, raw_full_day=full_day_si.records, raw_wellness=wellness_si.records,
    )
