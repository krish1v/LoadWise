"""Regenerate sample_output/ from the supplied workbook.

The season start year is set EXPLICITLY here (2025 = the 2025–26 season, as chosen
by the project owner). It is never inferred.

    python scripts/generate_sample_output.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from loadwise import Config, process_workbook  # noqa: E402

SEASON_START_YEAR = 2025
WORKBOOK = os.path.join(ROOT, "Data Set Georgia Tech_anonymized.xlsx")
OUT = os.path.join(ROOT, "sample_output")

if __name__ == "__main__":
    res = process_workbook(WORKBOOK, Config(season_start_year=SEASON_START_YEAR),
                           generated_at="sample (fixed timestamp for reproducibility)")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "loadwise_output.json"), "w", encoding="utf-8") as fh:
        fh.write(res.to_json(include_raw=False))
    with open(os.path.join(OUT, "loadwise_daily.csv"), "w", encoding="utf-8", newline="") as fh:
        fh.write(res.to_daily_csv())
    s = res.output["summary"]
    print(f"{s['session_records']} sessions, {s['athletes']} athletes, {s['daily_records']} daily records, "
          f"{s['date_range']['first']} -> {s['date_range']['last']}, flags {s['flags']}")
