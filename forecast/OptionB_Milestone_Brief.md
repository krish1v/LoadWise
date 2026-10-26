# LoadWise — Prediction module (Option B): October milestone

## Engineering question
Given an athlete's historical training workload and a **planned monitored session duration**, can we predict their upcoming **session TRIMP** more accurately than a pooled team-history estimate?

This supports the practitioner need identified by Marc at Bamberg: compare a player with **their own historical workload**, while acknowledging individual responses and limited staff time. It does **not** predict injuries, readiness, high-speed running, or improved athletic capacity.

## Simple implemented algorithm

**One Ridge regression**, not a model tournament. First compute each athlete's historical median TRIMP/min from prior training sessions. The inputs are (1) that athlete's historical TRIMP/min and (2) athlete identity. The model predicts a TRIMP/min intensity, which is multiplied by the planned session duration:

`predicted session TRIMP = planned duration (min) × max(0, learned TRIMP/min)`.

The predicted intensity is calibrated by Ridge regression (L2 regularization, alpha 10) using historical outcomes. All rate calculations for training observations are based on *earlier* sessions; for test records, athlete history is frozen at the training cutoff. New athletes fall back to the global median rate. We exclude game recordings, zero-TRIMP records, and ambiguous overlapping athlete-days.

## Proper out-of-sample comparison

- **1,102** original training records; **964** eligible after screening.
- **914** chronologically earlier observations for model fitting (94.8%).
- **50** chronologically later observations, all on or after ordinal day 116, reserved for testing (5.2%).
- We compare the model with (a) a pooled-history TRIMP-per-minute prediction and (b) a prior-athlete median TRIMP-per-minute prediction. These are comparison rules, not additional ML models.

| Method | Held-out MAE (TRIMP) | Held-out RMSE (TRIMP) |
|---|---:|---:|
| Pooled history | 26.62 | 40.42 |
| Athlete history | 25.14 | 38.82 |
| **Athlete-informed Ridge regression** | **24.26** | **37.40** |

The regression reduces average absolute error by **8.9%** versus pooled history and **3.5%** versus the athlete-history reference for the 50 evaluated sessions. The model also underpredicts actual TRIMP by **10.08 TRIMP on average**, meaning forecasts should not be interpreted as conservative workload limits.

**Cold-start limitation:** One record in the final holdout belongs to an athlete not seen during training, and its absolute error is about 167 TRIMP. On the remaining 49 observations for previously observed athletes, model MAE is approximately 21.34 TRIMP. This subset is a *diagnostic*, not a replacement for the full 50-observation headline result.

**Missing context:** All 50 final test records lack a game-day-relative (GD) classification. The demo therefore presents comparable-day historical rates as supporting context, but does not misleadingly use GD as a validated predictor.

## What the coach actually sees

1. Select a player and enter the planned monitored-session duration for each upcoming day.
2. See each day's predicted training TRIMP and a seven-day forecast total.
3. See their historical median TRIMP/min and, when available, comparable-day historical intensity.
4. Export one standardized JSON object that can later feed the optimizer's **expected baseline workload** input.

The UI deliberately does *not* claim to adjust an athlete's wellness, predict injury, or infer the incremental effect of substituting high-intensity drills within a practice. Those require different observations or assumptions. Training and game loads are not interchangeable.

## Presentation 2 sequence (about 90 seconds)

1. **Problem (15 s):** Coaches have fragmented histories; Marc relies on individual and comparable-day references.
2. **Method (20 s):** Show 95/5 chronological split and one athlete-informed regression.
3. **Evidence (20 s):** Show held-out MAE comparisons and actual-versus-predicted plot. Explain the observed errors honestly.
4. **Live mockup (25 s):** Select an athlete, modify planned session minutes, watch the seven-day workload forecast update, download JSON.
5. **Future (10 s):** Explain how forecasted workload informs optimization constraints while Mantas's future outcome data may inform a *separate* performance-response model.

## Scientific limitations and next work

- Historical **actual duration** stands in for planned duration in retrospective testing; actual prospective accuracy is unmeasured.
- The same 50-observation holdout was consulted during model refinement: treat the reported advantage as **exploratory**, not a fully untouched confirmatory test. Validate on new later sessions and/or a predefined future holdout.
- Small test sample, distribution shift, one unseen athlete, and absent game-relative-day labels.
- TRIMP is a heart-rate-derived **workload exposure**, not a performance capacity or physical improvement metric; Firstbeat high-intensity heart-rate-zone minutes are not HSR distance.
- There is no evidence yet that these predictions improve downstream *optimization decisions*. We will evaluate the planning impact separately rather than claiming it now.
- Marc's private anonymized material is for academic use only: don't redistribute source records, individualized outputs, or derived athlete histories without permission.

## Files

- `LoadWise_OptionB_Demo.html` — **ready-to-open, fully interactive browser mockup** (no installation; uses regression-calibrated athlete workload rates).
- `loadwise_predict.py` — reproduces data cleaning, regression fitting, 95/5 testing, evaluation and saved model.
- `loadwise_demo.py` — optional minimal Streamlit coach-facing functional mockup.
- `validation_charts.png` — predicted-versus-actual scatter and error comparison.
- `heldout_predictions.csv` — all 50 predicted-versus-observed training sessions, for private internal analysis.
- `results.json`, `loadwise_model.joblib` — model summary and locally saved trained predictor.

**Demo (no setup):** Open `LoadWise_OptionB_Demo.html` in a browser. Select an athlete, change daily duration inputs, inspect workload forecasts and historical reference context, and export JSON.

**Retrain on original Excel (optional):** Install `artifact_tool numpy scikit-learn matplotlib joblib`; then run `python loadwise_predict.py --input "PATH_TO_PRIVATE_WORKBOOK.xlsx"`. The demo HTML is a snapshot of the model trained on the current dataset; regenerating the regression model does not automatically rebuild the HTML.

**Privacy:** The HTML and learned model contain information derived from private academic-use data, so only share with authorized project members. The original workbook is not included.
