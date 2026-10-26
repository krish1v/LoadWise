# LoadWise Field Dictionary

Field-level documentation for the output contract: units, nullability,
provenance and completeness semantics. A machine-readable copy of the core
entries ships inside every JSON export under the `fieldDictionary` key
(`loadwise/schema.py::FIELD_DICTIONARY`).

Conventions used throughout:

- **`null`** = missing or unusable. A **valid `0`** is *not* null and is preserved.
- No `NaN` / `Infinity` / raw date objects ever appear in the JSON.
- All IDs are stable; all collections are deterministically ordered.

---

## Identity & provenance

| Field | Unit | Nullable | Meaning |
|---|---|---|---|
| `athlete_id` | — | no | Deterministic LoadWise id (`A001`…). Stable across uploads (append-only when a prior identity map is fed back). Same mapping for both sheets. Never produced by fuzzy matching. |
| `athlete_label` | — | no | Original display label, whitespace-trimmed / internal-whitespace-collapsed. |
| `athlete_label_raw` | — | yes | The verbatim source label. |
| `provenance.file` / `.sheet` / `.excel_row` | — | no | Immutable source location of every record. |
| `record_id` | — | no | `fd-<excelrow>` (Full Day) or `wl-<excelrow>` (Wellness). |

## Dates & schedule

| Field | Unit | Nullable | Meaning |
|---|---|---|---|
| `date_raw` | — | yes | Verbatim source date (e.g. the string `"11/09"`), never mutated. |
| `date_resolved` | date `YYYY-MM-DD` | yes | Resolved using the configured season start year. `null` if missing/unresolvable (→ record rejected from aggregation but kept visible). |
| `day_index` | study-day ordinal | yes | From the source `Day` column. **A sequential study-day index, not a weekday.** On a daily record, present only if all contributing sessions agree. |
| `gd` / `schedule_context.gd_labels` | — | yes | Source Game-Day labels (`GD`, `GD-1`, `GD+1`, …). **Observed context, not a complete forward schedule.** Conflicting same-day labels set `gd_conflict=true`. |
| `scheduleContext.athletes[].gaps` | days | — | Unobserved calendar gaps between observed dates. **Not** assumed to be rest or zero load. |

## Durations & times

| Field | Unit | Nullable | Meaning |
|---|---|---|---|
| `duration_min` | minutes | yes | Session/day duration. Excel day-fractions ×1440 (so `0.0625` → `90.0`); `hh:mm:ss`/`timedelta`/`time` parsed. Full precision kept; rounded only for display. |
| `high_intensity_min` | minutes | yes | High-intensity training time, same conversion. |
| `start_time` / `end_time` | clock `HH:MM:SS` | yes | Local wall-clock; **no timezone conversion is applied**. |
| `crosses_midnight` | bool | no | True when `end_time < start_time` (handled explicitly; ambiguous cases flagged). |

## Workload metrics (additive — summed per day)

| Field | Unit | Nullable | Meaning |
|---|---|---|---|
| `trimp` | index (dimensionless) | yes | Training Impulse. |
| `movement_load` | arbitrary units (source-defined) | yes | Movement Load. No physical unit claimed. |
| `high_intensity_min` | minutes | yes | (see above) — also an additive daily total. |
| `duration_min` | minutes | yes | (see above) — also an additive daily total. |

Each additive metric appears on a daily record as a **completeness block**:

```json
{ "value": 118.4, "valid_sessions": 2, "expected_sessions": 2, "completeness": "complete" }
```

- `completeness = "complete"` — every included session contributed the metric.
- `completeness = "partial"` — some did; `value` is the sum of the known ones.
- `completeness = "missing"` — none did; `value` is `null` (never `0`).

Training / game / other subtotals exist for each additive metric and **reconcile
to the overall total** (`breakdown_reconciles`).

## Source-preserved, non-recalculated fields

| Field | Unit | Nullable | Meaning |
|---|---|---|---|
| `avg_movement_intensity_source` | source-defined (unverified) | yes | Average Movement Intensity exactly as reported. **Not** assumed to equal Movement Load ÷ duration. No daily aggregate is produced (`derived.avg_movement_intensity.daily_value = null`); session values are preserved. |
| `trimp_per_min_source` | index/min | yes | Source TRIMP/min, kept separate from the calculated daily value. |
| `source_acwr` | ratio (source-reported) | yes | **Source ACWR — not independently calculated.** |
| `source_acute_training_load` / `source_chronic_training_load` | source-reported | yes | Preserved as-is for reference. |
| `measurement_error_pct` / `*_pct_hrmax` | percentage points | yes | Converted from the stored fraction using cell format + column context (not a blanket rule). `percent_notes` records which rule fired. |

## Derived metrics (calculated independently of the source)

| Field | Unit | Nullable | Rule |
|---|---|---|---|
| `derived.efficiency_calculated.value` | ratio (ML units per TRIMP) | yes | ΣMovementLoad ÷ ΣTRIMP. Computed **only** when both totals are `complete` over the same included sessions **and** ΣTRIMP > 0; otherwise `null` with a `reason`. |
| `derived.trimp_per_min_calculated.value` | index/min | yes | ΣTRIMP ÷ Σduration(min). Same completeness + positive-denominator rule. |

Session ratios are **never averaged** to form a daily ratio.

## Wellness (same-day observations)

| Field | Unit | Nullable | Meaning |
|---|---|---|---|
| `wellness_observations[].scores.{fatigue, sleep_quality, sleep_time, soreness, stress, wellness_score}` | **source-defined — scale/direction/unit UNKNOWN** | yes | Joined by athlete + resolved date. **Multiple same-day observations are all kept** (never summed or silently reduced to one). Missing wellness is `null`, never `0`. In particular `sleep_time` is **not** assumed to be hours. |

## Record status & flags

| Field | Values | Meaning |
|---|---|---|
| `status` | `included` / `excluded` / `rejected` | `included` enters daily totals; `excluded` is a duplicate or manual exclusion (kept, out of totals); `rejected` lacks a usable athlete/date (kept visible, cannot aggregate). |
| `status_reason` | string / null | Why the status was set (e.g. `exact_duplicate`, `missing_athlete`, `manual_override:include (reason)`). |
| `duplicate_of` | record_id / null | The canonical record this is an exact copy of. |
| `override` | `{action, reason}` / null | Manual include/exclude decision with its reason. |
| `qualityFlags[]` | — | `{flag_id, rule_code, severity (error/warning/info), record_id, field, sheet, excel_row, original_value, explanation, effect}`. |
