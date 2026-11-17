# Unresolved assumptions and open questions

These need agreement with the coach or the teammates. Each item says what LoadWise does today.

## Dates
- **Season year.** The export stores `dd/mm` with no year. LoadWise requires `season_start_year` and never infers it. The sample output and the demo use **2025** (2025–26 season), chosen explicitly by the project owner. Months from July (`rollover_month = 7`) get the start year; January to June get the next year. In the supplied workbook this means Sep–Dec 2025 and Jan 2026. Is July the right cut-over for this club's season?
- **Checks that are evidence only.** The study-day index (`Day`) and the chronological row order are used as supporting evidence: a conflict is flagged and the year is never reassigned. In the supplied workbook every study-day index maps to exactly one date.
- **Midnight crossings.** A session whose end time is earlier than its start time is attributed entirely to its **start date**. Splitting load across two days was not attempted.
- **Two sessions where times and duration disagree** (Excel rows 829 and 937) are flagged. The duration column is used for totals.

## Wellness
- The scale, range, direction (is higher better?) and units of `Fatig - #`, `Sleep Qua - #`, `Sleep Ti - #`, `Sore - #`, `Stre - #` and `Wellness - Score` are **unknown**. Values are stored as recorded and never rescaled, inverted or summed. `Sleep Ti - #` is **not** treated as hours of sleep.
- The supplied workbook has only 11 wellness rows, all from one day.

## Workload metrics
- **Average Movement Intensity:** its unit and vendor formula are not established. Session values are preserved. No daily aggregate is produced, and LoadWise does not assume it equals Movement Load ÷ duration.
- **Movement Load** is treated as source-defined arbitrary units and **TRIMP** as a source index. Neither vendor formula is reproduced.
- **Game sessions** in the supplied export have no Movement Load or High-Intensity values (158 games). Those daily metrics are therefore partial or missing on game days, never zero. This is flagged as info (`METRIC_NOT_RECORDED_FOR_TYPE`), because it is a property of the export. Should game Movement Load come from another source?
- **Screening thresholds** (duration 1–300 min, HR 30–230 bpm, etc.) are conservative placeholders, not physiological limits. A minimum HR of 29 bpm (row 366) is flagged as unusual, not as an error.

## Duplicates and multiple files
- An **exact duplicate** means every source cell is identical. A **possible duplicate** means the same athlete and date, with sessions that overlap by ≥ 50% or start at the same time. Same athlete and same date alone is never treated as a duplicate.
- When several files are stored, identical rows across files are counted once (the earliest import wins). A changed re-export of the same sessions with different values would show up as possible duplicates, not be merged silently. A "replace this file" workflow may be needed later.
- All stored files must share one season start year. Starting another season requires clearing the history.

## ACWR and rolling metrics (future module)
- Source ACWR, Acute Training Load and Chronic Training Load are preserved for reference only. They are **not recalculated**, and LoadWise does not know the source's window lengths or method.
- A separate ACWR module must still agree on:
  - which load metric to use (TRIMP? Movement Load? both?)
  - acute and chronic window lengths, and rolling-average vs EWMA
  - the **missing-day policy**: days without data are exposed as unobserved gaps, not zeros, and the module must decide whether a gap is rest, unknown, or imputed
  - how to treat partial days (e.g. game days without Movement Load)
- The squad view's 7/28-day sums are display only. They sum the known values over observed days and are not ACWR.

## Training planner (modelling team's models)
- `planner/` runs the modelling team's fitted models and optimizer unchanged (SamuelO12/createx-loadwise, `prototype/`, commit `e5ec641`). Only the data source changed: the models' inputs are built from LoadWise daily records instead of the team's own workbook reader. On the supplied workbook both produce the same 1,049 training days and 158 game days, and the team's reference plan is reproduced exactly.
- **Rules carried over from the team** (they differ from LoadWise's own daily totals):
  - only training sessions feed the models; game sessions only count towards "games in the last 7 days"
  - a day's Movement Load, TRIMP, duration or high-intensity minutes is treated as unknown unless **every** training session that day recorded it (LoadWise itself reports a partial sum with coverage)
  - MIP 1min is the day's highest training-session value
- **Fitted period.** The models were fitted on 11 Sep to 14 Dec 2025 (study days 1–95) and tested on the following weeks. A plan starting on or before 14 Dec 2025 replays data the models have seen; the UI says so.
- **Athletes the models have not seen** (or with fewer than three measured MIP days, or none in the last 28 days) can only use the squad-level duration-only models, after the coach confirms it. Athletes are matched to the models by exact label (`Player 01`); there is no fuzzy matching.
- **Version.** The model files were saved with scikit-learn 1.8.0. With 1.9.1 the reference result still matches to 1e-6, which the tests check.
- **Scope.** The planner predicts next-day training outcomes and picks training minutes within coach-set limits. Games and rest are not modelled, history is held fixed through the week, and suggested limits come from percentiles of the training data. It is not an injury, readiness or safety prediction. The earlier Option B TRIMP forecast was replaced by these models.
