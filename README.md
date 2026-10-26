# LoadWise — Workload Ingestion & Daily Aggregation (Prototype)

LoadWise is the **data layer** of a basketball workload-monitoring prototype
(university project, Bamberg Baskets context). It ingests a Polar/"Full Day"
Excel export, standardizes it, validates it, and produces an **athlete-specific
daily dataset** plus a stable, versioned JSON/CSV output contract.

This layer is intentionally **model-independent**: it does **no** optimization,
injury prediction, readiness scoring, or training recommendations. Teammates
building the Athlete-State and optimization components consume its output.

> **Scope note on ACWR / workload estimates:** source-reported ACWR, Acute
> Training Load and Chronic Training Load are preserved **as source-reported
> fields only** — they are *not* treated as independently calculated. LoadWise
> provides clean historical daily data (observed dates + explicit gaps) for a
> **future, separate ACWR module** whose window definitions and missing-day
> policy still need to be agreed (see `ASSUMPTIONS.md`).

---

## 1. Setup

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

## 2. Run the UI

```bash
streamlit run app/streamlit_app.py
```

The app **auto-loads the bundled example workbook on startup** (season year
2025) — no clicks needed. The sidebar switches the data source (example dataset
or an uploaded `.xlsx`), sets the season start year, and exposes the screening
thresholds; changing any of these reprocesses automatically.

Four tabs:

- **Overview & import** — headline metrics, the inferred Sep→Jan year rollover
  to review, the detected sheets/headers (with the Wellness header found on row
  49), and any date / study-day conflicts.
- **Validation** — counts (records, athletes, dates, errors, warnings, excluded
  duplicates), a filterable issue table, side-by-side source-vs-normalized
  inspection, and include/exclude duplicate controls that recalculate the
  affected daily outputs.
- **Daily dataset** — filter by athlete and date range; a table emphasizing
  TRIMP, Movement Load, High-Intensity minutes, duration and training/game
  splits with visible partial-data indicators; drill-down into the contributing
  sessions and source rows; download the JSON and daily CSV.
- **Forecast** — the Option B **prediction layer** wired in (see below).

Theme is set in `.streamlit/config.toml`.

## Forecast layer (Option B prediction model)

The teammate-built workload prediction module is connected through
`loadwise/forecast.py`, which loads the trained artifact in `forecast/`
(`loadwise_model.joblib`) and exposes a small, UI-agnostic API:

```python
from loadwise.forecast import Forecaster
fc = Forecaster()
fc.forecast("Player 01", [90, 90, 75, 0, 90, 60, 0])   # 7-day training-TRIMP forecast
fc.baseline_export("Player 01", [90, 90])              # JSON hand-off to the optimizer
```

It is one athlete-aware Ridge regression:
`predicted session TRIMP = planned duration (min) × max(0, learned TRIMP/min)`,
where the rate is learned from (athlete historical TRIMP/min, athlete identity).
Unseen athletes fall back to the global median rate (cold start). The model is
**consumed as-is**, not re-trained here. The Forecast tab shows the held-out
validation metrics (Ridge vs. athlete-history vs. pooled baselines), the
validation chart, comparable game-day history (context only), and a **download
of the standardized `expected_baseline_workload` JSON** — the contract this
layer passes to the future optimization layer. The tab also shows LoadWise's
*own* observed median training TRIMP/min next to the model's, making the
data-layer → prediction-layer link explicit.

Scope: it predicts upcoming **training** TRIMP only — not games, injuries,
readiness, or high-speed running. See `forecast/OptionB_Milestone_Brief.md` for
the method, honest limitations, and the exploratory (not confirmatory) framing
of its accuracy advantage.

## 3. Use it as a library

The entire pipeline is reusable without the UI:

```python
from loadwise import Config, process_workbook

result = process_workbook(
    "Data Set Georgia Tech_anonymized.xlsx",
    Config(season_start_year=2025),         # REQUIRED: never guessed
)

result.output          # JSON-safe dict (the full output contract)
result.daily_records   # list of per-athlete/day records
result.quality_flags   # structured validation flags
result.to_json()                 # versioned JSON string
result.to_json(include_raw=False)  # lighter JSON (raw dump replaced by counts)
result.to_daily_csv()            # flattened daily CSV (with completeness columns)
```

A missing season year raises `loadwise.SeasonYearRequired` with an actionable
message instead of inventing a year.

## 4. Run the tests

```bash
pytest -q
```

Small synthetic fixtures exercise every edge case (criteria 1–15 in the brief);
an integration smoke test runs the supplied workbook (auto-skips if absent).

---

## Architecture

Processing logic is fully separated from the UI so other apps can reuse it.

```
loadwise/
  config.py       Config + conservative, overridable screening Thresholds
  schema.py       column↔key mapping + the machine-readable FIELD_DICTIONARY
  identity.py     deterministic, stable, non-fuzzy athlete-id assignment
  units.py        duration→minutes, format/context-aware percentages, safe floats
  dates.py        yearless day/month → YYYY-MM-DD with reviewable rollover
  ingest.py       openpyxl read, header DETECTION, raw records + provenance
  normalize.py    standardize into normalized records (source preserved)
  validate.py     structured, severity-tagged quality flags
  duplicates.py   exact-duplicate canonicalization + overlap detection
  aggregate.py    athlete/day aggregation with explicit completeness + history
  export.py       JSON-safe output contract + flattened daily CSV
  pipeline.py     end-to-end orchestration + manual include/exclude override
app/streamlit_app.py   thin 3-view UI (presentation only)
tests/                 synthetic-fixture unit tests + real-workbook integration
sample_output/         sample JSON + CSV generated from the real workbook (year=2025)
```

### Key guarantees

- **Raw records are immutable** and retain file / sheet / Excel-row provenance.
- **Header positions and row counts are detected, never hardcoded** (so the
  Wellness header on row 49 above blank rows is found automatically).
- **`null` means missing/unusable; valid zeros are preserved.**
- **Determinism / idempotency:** stable IDs + deterministic ordering mean
  reprocessing the same file yields byte-identical JSON (the import timestamp is
  injected by the caller, not read from the clock).
- **Completeness is explicit:** every additive daily metric reports
  `{value, valid_sessions, expected_sessions, completeness}` where completeness
  is `complete` / `partial` / `missing`.
- **Derived ratios** (Efficiency = ΣMovementLoad/ΣTRIMP, TRIMP/min =
  ΣTRIMP/Σduration) are computed **only** from complete, matched inputs with a
  positive denominator — session ratios are never averaged. Source-reported
  ratios are kept separately.

See `FIELD_DICTIONARY.md` for field-level units, nullability and semantics, and
`ASSUMPTIONS.md` for unresolved questions.

## Output contract (JSON)

Top-level keys: `schemaVersion`, `importMetadata`, `configuration`,
`fieldDictionary`, `athletes`, `rawRecords`, `cleanedRecords`, `dailyRecords`,
`wellnessRecords`, `scheduleContext`, `qualityFlags`, `summary`.

Rejected and excluded records are retained with their status and reasons; every
daily total is traceable through `source_record_ids` → `cleanedRecords` →
`provenance.excel_row`, plus the duplicate decision that produced it.

## Observed facts about the supplied workbook

- `Full Day`: 1,260 measurement rows, 15 anonymized athletes; `Measurement type`
  ∈ {Training, Game}; `Analysis period` = Measurement throughout.
- Dates are **text** day/month (`11/09`), running `2025-09-11` → `2026-01-09`
  under season year 2025.
- **Game records carry no Movement Load or High-Intensity value** (158 games +
  54 trainings → 212 each are missing). LoadWise surfaces these as
  `MISSING_PRIMARY_METRIC` warnings and as `partial`/`missing` daily totals —
  it never fabricates a zero.
- `Wellness`: header on Excel row 49, 11 records, trailing blank rows.
