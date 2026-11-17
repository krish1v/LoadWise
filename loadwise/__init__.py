"""LoadWise data layer: Excel ingestion, validation and athlete-specific daily aggregation.

Model-independent: no optimization, injury prediction, readiness or recommendations,
and no recalculated ACWR (source ACWR is preserved as source-reported only).
"""

__version__ = "1.0.0"

from .config import Config, LoadWiseInputError, SeasonYearRequired, Thresholds  # noqa: E402
from .pipeline import ProcessResult, preview_workbook, process_workbook  # noqa: E402

__all__ = ["Config", "Thresholds", "LoadWiseInputError", "SeasonYearRequired",
           "process_workbook", "preview_workbook", "ProcessResult", "__version__"]
