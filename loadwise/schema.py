"""Column mapping and the field dictionary (the output contract documentation).

The parser never hardcodes row counts or header positions -- it finds headers by
name using the aliases below, so the supplied workbook's quirks (Wellness header
on row 49, trailing blank rows) are handled by *detection*, not constants.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Full Day sheet: header name -> internal normalized key.
# Only the mapped columns enter the core schema; ALL original columns are still
# preserved verbatim in rawRecords.
# ---------------------------------------------------------------------------

# Identity / context columns.
FULLDAY_CONTEXT = {
    "Athlete name": "athlete_label",
    "Measurement type": "measurement_type",
    "Analysis period": "analysis_period",
    "Date": "date_raw",
    "Day": "day_index",
    "GD": "gd",
    "Start time (hh:min:sec)": "start_time",
    "End time (hh:min:sec)": "end_time",
}

# Duration-typed columns (Excel day-fraction / timedelta / "hh:mm:ss") -> minutes.
FULLDAY_DURATION_COLS = {
    "Duration (hh:mm:ss)": "duration_min",
    "High intensity training (hh:mm:ss)": "high_intensity_min",
}

# Plain numeric workload metrics.
FULLDAY_NUMERIC_COLS = {
    "TRIMP (Index)": "trimp",
    "TRIMP/min (Index)": "trimp_per_min_source",
    "Movement load": "movement_load",
    "Average movement intensity": "avg_movement_intensity_source",
    "Average HR (bpm)": "avg_hr",
    "Minimum HR (bpm)": "min_hr",
    "Peak HR (bpm)": "peak_hr",
}

# Percentage columns: stored as a fraction (format "0.00 %") -> percent points.
FULLDAY_PERCENT_COLS = {
    "Measurement error (%)": "measurement_error_pct",
    "Average %HRmax (%)": "avg_pct_hrmax",
    "Minimum %HRmax (%)": "min_pct_hrmax",
    "Peak %HRmax (%)": "peak_pct_hrmax",
}

# Source-reported fields that must be preserved *as source-reported* and never
# treated as independently calculated by LoadWise (see spec section 1).
FULLDAY_SOURCE_REPORTED = {
    "Acute Training Load": "source_acute_training_load",
    "Chronic Training Load": "source_chronic_training_load",
    "ACWR": "source_acwr",
    "Training Status": "source_training_status",
}

# Additive metrics that are summed across sessions in daily aggregation.
ADDITIVE_METRICS = ["duration_min", "high_intensity_min", "trimp", "movement_load"]

# Primary metrics whose absence raises a "missing primary metric" flag.
PRIMARY_METRICS = ["trimp", "movement_load", "high_intensity_min"]

# Metrics that must be numeric, finite and non-negative.
NONNEGATIVE_METRICS = [
    "duration_min", "high_intensity_min", "trimp", "trimp_per_min_source",
    "movement_load", "avg_movement_intensity_source",
]

# ---------------------------------------------------------------------------
# Wellness sheet.
# ---------------------------------------------------------------------------
WELLNESS_CONTEXT = {
    "Date": "date_raw",
    "Performed By": "athlete_label",
}
WELLNESS_SCORE_COLS = {
    "Fatig - #": "fatigue",
    "Sleep Qua - #": "sleep_quality",
    "Sleep Ti - #": "sleep_time",
    "Sore - #": "soreness",
    "Stre - #": "stress",
    "Wellness - Score": "wellness_score",
}

# Columns used to locate a header row during detection (any of these present).
FULLDAY_HEADER_MARKERS = ["Athlete name", "Measurement type", "Date"]
WELLNESS_HEADER_MARKERS = ["Performed By", "Wellness - Score", "Fatig - #"]


# ---------------------------------------------------------------------------
# Field dictionary -- the machine-readable output contract. Shipped inside the
# JSON export so downstream teammates never have to guess units or semantics.
# ---------------------------------------------------------------------------
FIELD_DICTIONARY = {
    "athlete_id": {
        "unit": None,
        "nullable": False,
        "description": "Deterministic LoadWise athlete identifier (stable across uploads).",
    },
    "athlete_label": {
        "unit": None,
        "nullable": False,
        "description": "Original athlete display label from the source, whitespace-trimmed.",
    },
    "date_resolved": {
        "unit": "date (YYYY-MM-DD)",
        "nullable": True,
        "description": "Day/month source date resolved to a full date using the configured "
                       "season start year. null when the date is missing/unresolvable.",
    },
    "date_raw": {
        "unit": None,
        "nullable": True,
        "description": "Verbatim source date value (preserved, never mutated).",
    },
    "day_index": {
        "unit": "study-day ordinal",
        "nullable": True,
        "description": "Sequential study-day index from the source 'Day' column. NOT a weekday.",
    },
    "duration_min": {
        "unit": "minutes",
        "nullable": True,
        "description": "Session/day duration in minutes. Excel day-fractions are x1440; "
                       "'hh:mm:ss' durations are parsed. Full precision kept internally.",
    },
    "high_intensity_min": {
        "unit": "minutes",
        "nullable": True,
        "description": "High-intensity training time in minutes (from the 'High intensity "
                       "training' duration column).",
    },
    "trimp": {
        "unit": "index (dimensionless)",
        "nullable": True,
        "description": "Training Impulse, a dimensionless index. Additive across sessions.",
    },
    "movement_load": {
        "unit": "arbitrary units (source-defined)",
        "nullable": True,
        "description": "Movement Load in source-defined arbitrary units. Additive across sessions.",
    },
    "avg_movement_intensity_source": {
        "unit": "source-defined (unverified)",
        "nullable": True,
        "description": "Average Movement Intensity exactly as reported by the source. LoadWise "
                       "makes NO claim that this equals Movement Load / duration, and does not "
                       "produce a daily aggregate for it.",
    },
    "trimp_per_min_source": {
        "unit": "index per minute",
        "nullable": True,
        "description": "Source-reported TRIMP/min. Preserved separately from the LoadWise-"
                       "calculated daily TRIMP-per-minute.",
    },
    "efficiency_calculated": {
        "unit": "ratio (movement load units per TRIMP index)",
        "nullable": True,
        "description": "LoadWise daily Efficiency = total Movement Load / total TRIMP. Computed "
                       "only when both inputs are complete over the same included sessions and "
                       "TRIMP > 0; otherwise null with a reason.",
    },
    "trimp_per_min_calculated": {
        "unit": "index per minute",
        "nullable": True,
        "description": "LoadWise daily TRIMP/min = total TRIMP / total duration (minutes). "
                       "Computed only when both inputs are complete and duration > 0.",
    },
    "source_acwr": {
        "unit": "ratio (source-reported)",
        "nullable": True,
        "description": "ACWR exactly as reported by the source system. NOT independently "
                       "calculated by LoadWise. A separate ACWR module (window + missing-day "
                       "policy still to be agreed) will compute an independent value later.",
    },
    "measurement_error_pct": {
        "unit": "percent (percentage points)",
        "nullable": True,
        "description": "Measurement error. Stored in the source as a fraction (format '0.00 %'); "
                       "converted to percentage points here.",
    },
    "completeness": {
        "unit": None,
        "nullable": False,
        "description": "Per-metric completeness: 'complete' (all included sessions contributed), "
                       "'partial' (some contributed), or 'missing' (none did -> value is null).",
    },
    "wellness_scores": {
        "unit": "source-defined (scale/direction UNKNOWN)",
        "nullable": True,
        "description": "Same-day wellness observations. Scale, direction and units are NOT "
                       "assumed -- in particular 'sleep_time' is NOT assumed to be hours.",
    },
    "gd": {
        "unit": None,
        "nullable": True,
        "description": "Source Game-Day context label (e.g. GD, GD-1, GD+1). Observed context, "
                       "not a complete forward schedule.",
    },
}
