# Sample output

Generated from `Data Set Georgia Tech_anonymized.xlsx` with the season start year **explicitly set to 2025** (the 2025–26 season):

```bash
python scripts/generate_sample_output.py
```

- `loadwise_output.json`: the full output contract (schema 1.0.0). The raw cell dump is replaced by a count to keep the file small; every cleaned record still carries `source_values` and its Excel row. Use `result.to_json()` or `/api/export.json` for the version that includes the raw dump.
- `loadwise_daily.csv`: one row per athlete-day, with completeness columns.

Result:
- **Records:** 1,260 session records, 15 athletes, 1,116 athlete-days (142 of them with two or more sessions).
- **Dates:** 11 Sep 2025 to 9 Jan 2026. The Wellness header was detected on row 49 (11 records).
- **Flags:** 0 errors, 111 warnings and 316 info.
  - The info flags are the Movement Load and High-Intensity values that the export never records for its 158 game sessions.
  - The warnings are 54 training sessions without those metrics, 2 sessions whose times and duration disagree, and 1 unusually low heart rate.
- **Duplicates:** none found.

The `generated_at` timestamp is fixed, so regenerating gives byte-identical files.
