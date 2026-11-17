# Planner artifacts

Copied from [SamuelO12/createx-loadwise](https://github.com/SamuelO12/createx-loadwise), commit `e5ec641`:

| File | Source |
|---|---|
| `models/*.joblib` | `prototype/prediction/results/models/`, saved with scikit-learn 1.8.0 |
| `model_comparison.csv`, `validation_importance.csv` | `prototype/prediction/results/` |
| `fitting_reference.csv` | `prototype/data/processed/modeling_data.csv`, train and validation rows (study days 1–95), joined with each day's recorded duration from `athlete_training_days.csv` |

`fitting_reference.csv` is what the models were trained on. The planner uses it to check which durations an athlete has history for and to suggest workload limits. It is not the live data: athlete histories come from LoadWise.
