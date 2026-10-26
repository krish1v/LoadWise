# Unresolved Assumptions & Open Questions

This prototype deliberately flags — rather than silently resolves — anything it
cannot establish from the source. These need agreement with the S&C coach / team
before the downstream Athlete-State and ACWR modules rely on them.

## 1. Wellness scales (highest priority)

- The wellness columns (`Fatig - #`, `Sleep Qua - #`, `Sleep Ti - #`,
  `Sore - #`, `Stre - #`, `Wellness - Score`) have **unknown scale, direction
  and units**. Observed integers sit around 3–7 with a composite score ~24–31.
- We do **not** assume higher = better (or worse), and we do **not** assume
  `Sleep Ti - #` is sleep duration in hours.
- The supplied workbook has only **11 wellness rows for a single day (11/09)**,
  all for different athletes — far too sparse to infer a scale empirically.
- **Action:** confirm each field's scale, direction, and unit; confirm whether
  `Wellness - Score` is a sum of the components or an independent metric.

## 2. Average Movement Intensity semantics

- Preserved exactly as reported per session. We make **no claim** that it equals
  Movement Load ÷ duration, and we produce **no daily aggregate** for it because
  no aggregation method can currently be justified.
- An unweighted session mean is provided *for reference only*
  (`session_mean_unweighted`) and must not be treated as authoritative.
- **Action:** obtain the vendor definition; decide whether a duration-weighted
  daily value is appropriate, and document the formula if so.

## 3. Date interpretation

- Dates are text day/month with no year. Resolution **requires** an explicit
  season start year; the prototype is configured with **2025** (the 2025–26
  season: Sep–Dec 2025, Jan 2026). It never defaults to the current year.
- Rollover rule currently: months 9–12 → start year, months 1–8 → start year+1.
  This matches the observed Sep→Jan span but the exact season boundary month is
  an assumption.
- Resolved dates are cross-checked against the sequential `Day` study-index;
  disagreements are flagged (`DATE_DAYINDEX_CONFLICT`), **not** auto-corrected.
- **Action:** confirm the season start year and the rollover boundary; decide a
  policy if any date/day-index conflicts are reported for a future workbook.

## 4. Future ACWR methodology (separate module)

- Source-reported `ACWR`, `Acute Training Load` and `Chronic Training Load` are
  preserved **as source-reported fields only** — never recomputed here.
- LoadWise supplies clean, chronologically sorted daily histories per athlete,
  with **observed dates and explicit gaps** exposed. Unobserved dates are **not**
  assumed to be rest or zero load.
- Still to agree for the independent ACWR module:
  - Acute vs chronic **window definitions** (e.g. 7-day acute vs 28-day chronic;
    rolling vs EWMA).
  - **Missing-day policy** — are gaps treated as zero load, carried forward,
    ignored, or do they invalidate the window?
  - Which workload metric drives ACWR (TRIMP? Movement Load? both?).

## 5. Duplicate / overlap policy

- "Exact duplicate" = an identical copy across **all** source columns; one
  canonical record is kept and the rest excluded from totals (this also makes
  re-uploads idempotent).
- Same athlete + same date is explicitly **not** a duplicate — double practices
  and training+game days are legitimate and kept.
- Time-window overlap above `overlap_warn_fraction` (default 0.5) is flagged as a
  **possible** duplicate but kept **included** pending human review.
- **Action:** confirm the overlap threshold and whether any genuinely duplicated
  sessions exist in practice.

## 6. Screening thresholds

- Duration (1–300 min), HR (20–230 bpm), and workload-magnitude ceilings are
  conservative **screening** values that raise warnings only — they never
  reclassify a value as a hard error.
- **Action:** calibrate with the coach (e.g. realistic max game/practice length,
  player-specific HR maxima).

## 7. Observed data quirk (not an assumption, but flag for the team)

- In the supplied workbook, **Game records contain no Movement Load or
  High-Intensity value** (212 records each). Daily Movement Load / Efficiency on
  game-only days is therefore `missing`/`partial`, by design — not zero.
- **Action:** confirm whether this is expected (Movement Load unavailable for
  games) or a source-export gap to be fixed upstream.
