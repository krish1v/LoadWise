"""LoadWise -- basketball workload ingestion, validation and daily aggregation.

This package is the *data layer* only. It is intentionally free of any UI,
optimization, injury-prediction, readiness or recommendation logic so that the
Athlete-State and optimization components being built by teammates can reuse it.

Public entry point: :func:`loadwise.pipeline.process_workbook`.
"""

from .config import Config, Thresholds, SCHEMA_VERSION
from .pipeline import process_workbook, ProcessResult, SeasonYearRequired

__all__ = [
    "Config",
    "Thresholds",
    "SCHEMA_VERSION",
    "process_workbook",
    "ProcessResult",
    "SeasonYearRequired",
]
