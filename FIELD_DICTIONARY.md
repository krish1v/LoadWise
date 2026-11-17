# LoadWise output contract and field dictionary (schema 1.0.0)

The JSON export is one object. A machine-readable summary of this file is embedded as `fieldDictionary`.

| Key | Contents |
|---|---|
| `schemaVersion` | `"1.0.0"` |
| `importMetadata` | Generator version, `generated_at` (injected by the caller), and per import: `import_id`, `sha256`, file name, sheets present, workbook date epoch (1900/1904), detected header rows, record counts, column mapping, messages |
| `configuration` | `season_start_year`, `rollover_month`, known measurement types, screening `thresholds`, the date-resolution rule, manual `overrides` (with reasons) |
| `fieldDictionary` | Units, nullability, provenance, statuses, completeness, ratio and duplicate policies |
| `athletes` | One per athlete: ID, display label, source label variants, sheets seen, counts, `history` |
| `rawRecords` | Every non-blank source row: `cells` exactly as read (header → value) and non-General `number_formats`. Immutable. |
| `cleanedRecords` | One normalized record per Full Day row (status `included` / `excluded` / `rejected`) |
| `dailyRecords` | One per athlete and resolved date with ≥1 included session |
| `wellnessRecords` | One normalized record per Wellness row |
| `scheduleContext` | Observed game-session dates, GD labels by date, team dates without data |
| `qualityFlags` | Structured validation flags |
| `summary` | Counts, flags by severity and rule, date range |

Values are JSON-safe: no NaN or Infinity, and dates are ISO strings. Ordering is deterministic: athletes by label, records by (import, Excel row), daily records by (athlete_id, date), flags by severity then record.

## Identity and provenance

| Field | Meaning |
|---|---|
| `athlete_id` | `ath-` + first 8 hex characters of SHA-1 of the normalized label, casefolded. The label is normalized by Unicode NFC, trimming and collapsing whitespace. The ID is deterministic and identical across uploads and across both sheets. There is **no fuzzy matching**: "Player 1" and "Player 01" are different athletes. |
| `athlete_label` | The cleaned display label. The original text stays in `source_values.athlete` and `athletes[].source_label_variants`. |
| `record_id` | `<first 12 hex of the file's SHA-256>:fd-<excel row>` for Full Day rows, and `…:wl-<row>` for Wellness rows. |
| `provenance` | `{file, sheet, excel_row}` on every raw, cleaned and wellness record. |

## Session record (`cleanedRecords[]`)

| Field | Unit / type | Nullable | Notes |
|---|---|---|---|
| `date` | `YYYY-MM-DD` | yes | Resolved local date. `date_method` is `day_month_plus_season_year`, `excel_date`, `excel_serial`, `day_month_year_text` or `iso_text`. When resolution fails, `date_error` gives the reason. |
| `study_day_index` | integer | yes | The source `Day` column. It is a sequential study-day index, **not a weekday**. |
| `measurement_type` / `session_bucket` | text / `training`·`game`·`other` | yes / no | Unknown types go to `other` and are flagged. |
| `gd` | text | yes | Source game-day label, e.g. `GD-1`. |
| `start_time`, `end_time` | `HH:MM:SS` | yes | Clock time as recorded. |
| `crosses_midnight`, `clock_span_min` | bool, minutes | – / yes | When end < start, the session is attributed to the start date. |
| `metrics.duration_min` | minutes | yes | Excel day fraction × 1440, `timedelta`, or `h:mm:ss` text. Full precision. |
| `metrics.hit_min` | minutes | yes | `High intensity training (hh:mm:ss)` |
| `metrics.trimp` | TRIMP index | yes | |
| `metrics.movement_load` | source-defined AU | yes | |
| `source_ratios.trimp_per_min` | TRIMP/min | yes | **Source-reported** session value; never averaged. |
| `source_ratios.avg_movement_intensity` | source-defined, unit unknown | yes | Preserved as reported. |
| `peak_intensity.{mip1, mip3}` | source-defined | yes | `Maximal Intensity Period MI 1min` / `3min`: the session's peak movement intensity over a 1- or 3-minute window. Negative values are nulled and flagged. |
| `measurement_error_pct` | percent points | yes | Percent-formatted cells are stored fractions × 100; `measurement_error_interpretation` says which rule applied. |
| `heart_rate.{min,avg,peak}_bpm` | bpm | yes | Screened only, never aggregated. |
| `source_reported.{acute_training_load, chronic_training_load, acwr}` | source units | yes | Reference only. **Not calculated or verified.** |
| `source_values` | – | – | The original value of every mapped column. |
| `status`, `status_reason` | – | – | `included`: counts. `excluded`: kept but not counted (`exact_duplicate` or `manual_override: <reason>`). `rejected`: no usable athlete or date. |
| `duplicate_of`, `possible_duplicate_of`, `override` | – | yes | Duplicate relationships and manual decisions. |
| `flag_ids` | list | – | Flags on this record. |

`null` means missing or unusable. `0` is a recorded zero. Neither is ever converted into the other. An invalid value nulls **only that metric**; the rest of the session still counts.

## Daily record (`dailyRecords[]`)

| Field | Meaning |
|---|---|
| `daily_id` | `<athlete_id>:<date>` |
| `athlete_id`, `athlete_label`, `date` | Athlete and resolved date |
| `study_day_index` | Set only when every session agrees and none conflicts with the date; otherwise `null` with `study_day_index_conflict: true` |
| `session_count`, `session_counts_by_type` | Included sessions (training / game / other) |
| `source_record_ids` | Included sessions, i.e. what the totals are built from |
| `excluded_record_ids` | Same athlete and date but not counted (copies, manual exclusions) |
| `totals.<metric>` | Metric block over all included sessions |
| `breakdown.{training,game,other}.<metric>` | The same blocks per session type |
| `reconciles.<metric>` | `true` when training + game + other equals the total, for both value and valid-session count |
| `derived.efficiency` | Total Movement Load / total TRIMP |
| `derived.trimp_per_min` | Total TRIMP / total duration (minutes) |
| `source_session_ratios` | Source-reported session TRIMP/min, kept separately |
| `peak_intensity.{mip1,mip3}` | Metric block whose `value` is the **max** over included sessions that recorded it (peaks are never summed), plus `by_bucket.{training,game,other}` blocks of the same shape |
| `avg_movement_intensity` | `session_values` are preserved. `daily_value` is always `null`, because no justified aggregation method exists. |
| `schedule` | `gd_labels` (all distinct), `gd_conflict`, `has_game_session` |
| `wellness` | **List** of same-day wellness observations, never summed, chosen between or zero-filled |
| `quality` | `incomplete_metrics`, `flag_ids`, `flag_counts` |

**Metric block:** `{value, valid_sessions, expected_sessions, completeness}`.

| completeness | meaning |
|---|---|
| `complete` | Every included session has the metric |
| `partial` | Some sessions have it; `value` is the sum of the known values only |
| `missing` | No session has it; `value` is `null` |
| `no_sessions` | The breakdown bucket has no sessions that day; `value` is `null` |

**Derived ratios** are calculated only when both inputs are `complete` over the same included sessions and the denominator is greater than 0. Otherwise the value is `null` and `reason` explains why. Session ratios are never averaged.

**Metrics:** `duration_min` (minutes), `trimp` (index), `movement_load` (AU), `hit_min` (minutes).

## History and schedule

- `athletes[].history`: `first_date`, `last_date`, `observed_days`, `observed_dates`, and `gaps` (`{from, to, days, status: "unobserved"}`). A gap is a day with no recorded session. It is **not** zero load and **not** a confirmed rest day. Rolling calculations must choose their own missing-day policy.
- `scheduleContext`: observed context only (game sessions and GD labels). It is not a complete or future schedule. `team_dates_without_data` lists days where nobody has data.

## Wellness record (`wellnessRecords[]`)

`values.{fatigue, sleep_quality, sleep_time, soreness, stress, wellness_score}` are stored exactly as recorded. **Scale, direction and units are unknown.** In particular, `sleep_time` (`Sleep Ti - #`) is *not* assumed to be hours.

## Quality flag (`qualityFlags[]`)

`{flag_id, rule_code, severity, record_id, field, sheet, excel_row, original_value, explanation, aggregation_effect}`. `flag_id` = `<record_id>/<RULE>/<field>`, which is stable across reprocessing.

| Rule | Severity | Effect |
|---|---|---|
| `MISSING_ATHLETE`, `MISSING_OR_INVALID_DATE` | error | Record `rejected`: visible, not aggregated |
| `NEGATIVE_METRIC`, `NEGATIVE_DURATION` | error | That metric nulled; others kept |
| `NON_NUMERIC_VALUE`, `NON_FINITE_VALUE` | warning (info for non-workload fields) | That value nulled |
| `MISSING_PRIMARY_METRIC`, `MISSING_DURATION` | warning | Daily metric becomes partial or missing |
| `METRIC_NOT_RECORDED_FOR_TYPE` | info | As above. Used when ≥90% of a measurement type in a file lacks the metric (e.g. no Movement Load for any Game), which is a property of the source rather than of the session. |
| `ZERO_DURATION`, `IMPLAUSIBLE_DURATION`, `HIT_EXCEEDS_DURATION`, `IMPLAUSIBLE_HR`, `HR_ORDER_INCONSISTENT`, `TIME_DURATION_MISMATCH` | warning | Included as recorded |
| `MIDNIGHT_CROSSING` | info | Attributed to the start date |
| `UNEXPECTED_MEASUREMENT_TYPE` | warning | Counted under `other` |
| `UNEXPECTED_ANALYSIS_PERIOD` | info | None |
| `DATE_DAYINDEX_CONFLICT`, `DATE_ORDER_ANOMALY` | warning | Aggregated on the resolved date; year not reassigned |
| `EXACT_DUPLICATE` | warning | Copy `excluded`; canonical = earliest (import, row) |
| `POSSIBLE_DUPLICATE_OVERLAP` | warning | Both stay included until reviewed |
| `GD_CONFLICT` | warning | All labels kept |
| `MANUAL_OVERRIDE`, `OVERRIDE_IGNORED` | info / warning | Decision applied, or not possible |
| `COLUMN_UNAVAILABLE`, `OPTIONAL_SHEET_MISSING`, `ATHLETE_LABEL_VARIANT` | info | Dataset-level notes |
| `WELLNESS_*` | warning / info | Wellness row rejected, unknown athlete, or several per day |

**Default screening thresholds** (configurable in `Thresholds`):
- session duration from 1 to 300 min
- HR from 30 to 230 bpm
- HIT may exceed duration by up to 0.5 min (rounding tolerance)
- clock span vs duration column tolerance of 2 min
- overlap ≥ 50% of the shorter session (or the same start time) marks a possible duplicate

## Daily CSV

One row per daily record. For each metric there are four columns: `<metric>`, `<metric>_completeness`, `<metric>_valid_sessions` and `<metric>_expected_sessions`. Then come the `training_*`, `game_*` and `other_*` values, `mip1_max`, `mip1_completeness`, `training_mip1_max`, `mip3_max`, `training_mip3_max`, `efficiency` and `trimp_per_min` with `*_null_reason`, `gd_labels` (`|`-separated), `gd_conflict`, `wellness_observations`, `flag_count`, `source_record_ids` and `excluded_record_ids`. Empty cell = null.
