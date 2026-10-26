# Sample output

Generated from `Data Set Georgia Tech_anonymized.xlsx` with
`Config(season_start_year=2025)` (the configured 2025–26 season).

Regenerate with:

```bash
python -c "from loadwise import Config, process_workbook; r=process_workbook('Data Set Georgia Tech_anonymized.xlsx', Config(season_start_year=2025), generated_at='2026-10-18T00:00:00'); open('sample_output/loadwise_output.json','w',encoding='utf-8').write(r.to_json(include_raw=False)); open('sample_output/loadwise_daily.csv','w',encoding='utf-8',newline='').write(r.to_daily_csv())"
```

## Files

- **`loadwise_output.json`** — the full versioned output contract. The large
  per-cell `rawRecords` dump is omitted here for readability
  (`to_json(include_raw=False)` replaces it with counts); pass
  `include_raw=True` to embed all 1,260 × 100 source cells. Traceability is
  unaffected: every daily total still traces through `source_record_ids` →
  `cleanedRecords` → `provenance.excel_row`.
- **`loadwise_daily.csv`** — flattened daily dataset with completeness columns.

## What this sample shows

- 1,260 Full-Day records → **1,116 daily records** across **15 athletes**,
  spanning **2025-09-11 → 2026-01-09**.
- **142** athlete-days combine more than one session (training+game and
  double-practice days).
- **424 warnings**, all `MISSING_PRIMARY_METRIC`: Game records (and some
  trainings) carry no Movement Load / High-Intensity in the source, so **80**
  daily records are `partial` — surfaced explicitly, never zero-filled.
- **0 errors, 0 rejected records, 0 exact duplicates** in this workbook.
