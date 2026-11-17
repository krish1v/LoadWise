# LoadWise

Athlete workload monitoring prototype (university project, Bamberg Baskets context).

This repository holds the **data layer** and the **web UI** built around it:

- `loadwise/`: a pure-Python library. It reads the per-session Excel export, standardizes and validates it, and produces **one record per athlete per day**, with explicit completeness and full provenance. It is model-independent: no optimization, injury prediction, readiness or recommendations.
- `api/`: a small FastAPI service. It stores uploads in SQLite so athlete histories build up over time.
- `web/`: a React app with squad overview, athlete timelines, a season calendar heatmap, daily data, data quality review and the training-load forecast.

> **ACWR scope.** Source-reported ACWR, Acute Training Load and Chronic Training Load are preserved **as source-reported fields only**. They are never recalculated or treated as validated. LoadWise provides clean daily histories (observed dates plus explicit gaps) for a **future, separate ACWR module**. Its window definitions and missing-day policy still need agreement (see `ASSUMPTIONS.md`).

## Setup

Requires Python 3.10+ and Node 18+.

```bash
pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
```

## Run

```bash
uvicorn api.main:app            # http://localhost:8000  (API + built UI)
```

- **First start:** if the store is empty, the bundled demo workbook is imported automatically with season start year **2025**, so the UI opens with data. Set `LOADWISE_AUTOLOAD_DEMO=0` to disable this.
- **Database:** history lives in `data/loadwise.db`. Override the location with `LOADWISE_DB=...`.
- **Front-end development:** run `uvicorn api.main:app --reload` and `cd web && npm run dev` (http://localhost:5173 proxies `/api`).

### Using the UI

| View | What it is for |
|---|---|
| **Add data** (top bar) | Drag in an `.xlsx` (or use the demo) and set the season start year. Review the detected sheets, header rows and how yearless dates resolve, then click **Process workbook**. Re-adding a file already stored changes nothing. |
| **Squad** | Every athlete with a 28-day daily load strip (training blue, game orange, partial hatched, no data dashed), 7/28-day sums and issue counts. Move the window with *Window ends*. |
| **Athlete** | The full-season daily timeline (training/game stacked, gaps shaded, partial days striped) and the athlete's daily table. Click any bar or row to open the drill-down. |
| **Calendar** | Squad × date heatmap for one metric, with game days marked. |
| **Daily data** | Filter by athlete, date range, partial days, multi-session days or days with issues. Download the daily CSV or the full JSON. |
| **Data quality** | Counts (records, athletes, resolved dates, errors, warnings, excluded duplicates), the duplicate review queue (count it / leave it out, with a required reason; totals recalculate), the filterable issue table, a side-by-side original-vs-normalized record inspector, and the imported files with *Clear history*. |
| **Forecast** | The teammate's Option B model: planned training minutes in, predicted training TRIMP out, drawn on top of recorded history. Shows its validation figures and exports the `expected_baseline_workload` JSON for the optimizer. |

The **drill-down drawer** (from any chart, table row or calendar cell) shows one athlete-day:
- totals and training/game/other splits, each with coverage
- calculated Efficiency and TRIMP/min, or the reason they are null
- every contributing session, with file, sheet and Excel row, its flags and the original cell values
- excluded copies
- same-day wellness observations

## Use the library directly

```python
from loadwise import Config, process_workbook, preview_workbook

result = process_workbook("Data Set Georgia Tech_anonymized.xlsx", Config(season_start_year=2025))
result.daily_records            # one dict per athlete-day
result.quality_flags            # structured flags
result.to_json()                # versioned JSON contract (see FIELD_DICTIONARY.md)
result.to_json(include_raw=False)
result.to_daily_csv()           # flat daily table with completeness columns

# manual duplicate decisions (reason required in the UI/API); only the fast steps re-run
result = result.reprocess({"<record_id>": {"action": "exclude", "reason": "recorded twice"}})

# several files at once (identical files are read once; identical rows count once)
process_workbook([("a.xlsx", bytes_a), ("b.xlsx", bytes_b)], Config(season_start_year=2025))
```

- A missing season year raises `SeasonYearRequired`, which carries an actionable message. LoadWise never guesses a year.
- Unusable input raises `LoadWiseInputError` with a user-facing message. That covers empty files, non-xlsx files, a missing `Full Day` sheet and missing athlete/date columns.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | imports, season year, summary |
| POST | `/api/preview`, GET `/api/preview/demo` | sheets, header rows, date samples, rollover table (nothing stored) |
| POST | `/api/imports` (multipart `file`, `season_start_year`), `/api/imports/demo` | validate, store, recompute |
| DELETE | `/api/imports/{sha256}`, `/api/store` | remove one file / clear history |
| GET | `/api/summary?ref=YYYY-MM-DD` | summary + squad overview + schedule context |
| GET | `/api/athletes`, `/api/daily?athlete=&date_from=&date_to=` | athletes with histories; daily rows |
| GET | `/api/daily/{athlete_id}/{date}` | drill-down: daily record, sessions + raw cells, flags |
| GET | `/api/calendar?metric=trimp` | athlete × date matrix (null = unobserved) |
| GET | `/api/flags`, `/api/records/{record_id}`, `/api/review` | issues, record inspector, duplicate queue |
| POST/DELETE | `/api/overrides` | include/exclude with reason; clear |
| GET | `/api/export.json?include_raw=`, `/api/export.csv` | downloads |
| GET | `/api/forecast/meta`, `/api/forecast/{athlete_id}?minutes=90,60,…`, `…/baseline.json` | prediction layer |

Interactive docs: http://localhost:8000/docs

## Tests

```bash
pytest -q                  # 72 tests, ~45 s
cd web && npm run build    # includes the TypeScript type-check
```

- **Synthetic fixtures** (built in `tests/conftest.py`) cover every acceptance criterion: same-day sessions, splits that reconcile, `0.0625` → 90 min, the Dec→Jan rollover, the missing-year request, the Wellness header below blank rows, exact and possible duplicates, idempotency, missing vs zero, partial coverage, isolation of invalid fields, ratio rules, graceful failures, and JSON traceability.
- **Real-workbook test:** `tests/test_integration_real.py` smoke-tests the supplied workbook.
- **API test:** `tests/test_api.py` drives the API and store, including the re-upload no-op, overrides, exports and the forecast.

## Layout

```
loadwise/   config · ingest · normalize · validate · aggregate · export · pipeline · store · forecast
api/        main.py (FastAPI)
web/        Vite + React + TypeScript (Tailwind, TanStack Query/Table, ECharts)
scripts/    generate_sample_output.py
sample_output/   JSON + daily CSV from the real workbook (season year 2025, set explicitly)
forecast/   the teammate's trained model, validation results and brief
```

The pipeline is a pure function of (file bytes, config, overrides). The SQLite store keeps only those inputs and recomputes from them, so every number in the UI can be reproduced from the files.

See `FIELD_DICTIONARY.md` for the output contract and `ASSUMPTIONS.md` for open questions.
