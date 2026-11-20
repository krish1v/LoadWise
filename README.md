# LoadWise

Athlete workload optimization prototype. It turns raw per-session Excel exports into clean daily athlete histories, predicts training load, and plans each athlete's week.

## What's inside

| Folder | What it does |
|---|---|
| `loadwise/` | **Data layer.** Reads the Excel export, validates it and builds one record per athlete per day, with completeness and provenance. Contains no models. |
| `planner/` | **Models and optimizer.** The modelling team's prediction models (MIP 1min, Movement Load, TRIMP) and weekly optimizer ([SamuelO12/createx-loadwise](https://github.com/SamuelO12/createx-loadwise), commit `e5ec641`). They read LoadWise daily records as input. |
| `api/` | **Backend.** FastAPI service that stores uploads in SQLite and serves the data, the planner and coach feedback. |
| `web/` | **Frontend.** React app: squad overview, athlete timelines, calendar heatmap, daily data, data quality review and the training planner. |

> **ACWR.** Source-reported ACWR and acute/chronic load are kept only as source fields. They are never recalculated or validated (see `ASSUMPTIONS.md`).

## Quick start

Requires Python 3.10+ and Node 18+.

```bash
pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
uvicorn api.main:app        # http://localhost:8000
```

On first start the bundled demo workbook (season 2025) is imported automatically, so the app opens with data.

| Setting | Default |
|---|---|
| `LOADWISE_DB` | `data/loadwise.db` |
| `LOADWISE_AUTOLOAD_DEMO` | `1` (set `0` to start empty) |

For frontend development, run `uvicorn api.main:app --reload` and `cd web && npm run dev` (http://localhost:5173).

## Using the app

- **Add data**: upload an `.xlsx`, check the preview (sheets, headers, date resolution) and process it. Re-uploading the same file changes nothing.
- **Squad / Athlete / Calendar / Daily data**: browse daily loads. Click any bar, row or cell to see the athlete-day in detail, down to the original Excel cells.
- **Data quality**: review issues and possible duplicates (include or exclude, with a reason), and manage imported files.
- **Training plan**: pick an athlete and a week, set training, game or rest for each day plus limits, and generate a plan with predicted MIP, Movement Load and TRIMP. Coaches can accept, reject or modify the plan. A modified week is re-scored with the same models, and the feedback is saved. **Run the reference example** (or `/plan?demo=1`) reproduces the modelling team's reference week.

## API

Interactive docs are at http://localhost:8000/docs. Main groups:

- **Data**: `/api/imports`, `/api/preview`, `/api/summary`, `/api/athletes`, `/api/daily`, `/api/calendar`
- **Quality**: `/api/flags`, `/api/records/{id}`, `/api/review`, `/api/overrides`
- **Export**: `/api/export.json`, `/api/export.csv`
- **Planner**: `/api/plan/meta`, `/api/plan/history`, `/api/plan/optimize`, `/api/plan/evaluate`, `/api/plan/models`
- **Feedback**: `/api/plan/feedback` (GET list / POST), `/api/plan/feedback/{id}`

## Use the library directly

```python
from loadwise import Config, process_workbook

result = process_workbook("Data Set Georgia Tech_anonymized.xlsx", Config(season_start_year=2025))
result.daily_records     # one dict per athlete-day
result.quality_flags     # structured issues
result.to_json()         # full output (see FIELD_DICTIONARY.md)
result.to_daily_csv()    # flat daily table
```

LoadWise never guesses a season year: if it's missing, it raises `SeasonYearRequired`.

## Tests

```bash
pytest -q                  # 78 tests
cd web && npm run build    # includes the TypeScript type-check
```

The tests cover the data pipeline (synthetic fixtures and the real workbook), the API and store, and the planner. The planner tests check that LoadWise data reproduces the modelling team's reference result.

## Further reading

- `FIELD_DICTIONARY.md`: output fields and JSON contract
- `ASSUMPTIONS.md`: open questions and decisions
- `planner/artifacts/README.md`: fitted models and evaluation tables
- `sample_output/`: example JSON and CSV from the real workbook
