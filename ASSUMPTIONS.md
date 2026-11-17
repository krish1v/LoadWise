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

## Forecast layer
- The Forecast view consumes the modelling team's trained artifact (`forecast/loadwise_model.joblib`) as-is. It predicts **training** TRIMP from planned minutes only, not games, injury or readiness.
- Forecast days start the day after the athlete's last recorded session. Athletes missing from the model's training data (e.g. Player 15) fall back to the squad rate.
- Its accuracy figures come from a 50-session holdout and should be treated as exploratory.
