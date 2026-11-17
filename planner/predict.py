"""Load the fitted models and predict outcomes for supported recording durations.

Adapted from SamuelO12/createx-loadwise, prototype/prediction/predict.py (commit e5ec641).
Only the artifact location and the version-warning filter differ from the original.
"""
from functools import lru_cache
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd

ARTIFACTS = Path(__file__).parent / 'artifacts'
DURATION = 'actual_duration_min'
TARGETS = ['mip1', 'movement_load', 'training_trimp']
FEATURE_GROUPS = {
    'Previous MIP': ['last_mip1', 'days_since_mip1', 'mip1_mean_7d', 'mip1_mean_28d', 'mip1_days_7d', 'mip1_days_28d'],
    'Duration and frequency': ['last_recorded_duration_min', 'recorded_duration_mean_7d', 'training_days_7d', 'training_days_28d'],
    'Internal load': ['training_trimp_sum_7d', 'training_trimp_sum_28d'],
    'External load': ['movement_load_sum_7d', 'movement_load_days_7d'],
    'High HR exposure': ['high_hr_minutes_sum_7d', 'high_hr_days_7d'],
    'Competition history': ['reported_game_days_7d']
}
HISTORY_FEATURES = sum(FEATURE_GROUPS.values(), [])


def predict_values(model, features):
    values = np.asarray(model.predict(features), dtype=np.float64)
    if values.shape != (len(features),) or not np.isfinite(values).all():
        raise RuntimeError('A fitted model returned invalid predictions.')
    return np.maximum(0, values)


def supported_durations(fitting_data, athlete, durations):
    pooled_durations = fitting_data[DURATION].to_numpy()
    individual_durations = pooled_durations
    if athlete is not None:
        individual_durations = fitting_data.loc[
            fitting_data.athlete_id == athlete, DURATION].to_numpy()
    if len(individual_durations) == 0:
        return np.zeros(len(durations), dtype=bool)

    supported = []
    for duration in durations:
        within_range = individual_durations.min() <= duration <= individual_durations.max()
        pooled_count = np.sum(abs(pooled_durations - duration) <= 20)
        individual_count = np.sum(abs(individual_durations - duration) <= 20)
        supported.append(duration > 0 and within_range and pooled_count >= 10
                         and (athlete is None or individual_count >= 3))
    return np.array(supported, dtype=bool)


@lru_cache(maxsize=6)
def load_model(name):
    # The artifacts were saved with scikit-learn 1.8.0; tests check the reference result still holds.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Trying to unpickle estimator')
        return joblib.load(ARTIFACTS / 'models' / (name + '.joblib'))


def evaluate(history, durations, fitting_data, athlete):
    durations = np.asarray(durations, dtype=float)
    supported = supported_durations(fitting_data, athlete, durations)
    predictions = pd.DataFrame({DURATION: durations[supported]})
    if predictions.empty:
        return predictions

    # Pooled models use duration only, without an invented athlete history.
    personalized = athlete is not None
    features = HISTORY_FEATURES + [DURATION] if personalized else [DURATION]
    model_inputs = pd.DataFrame([history] * len(predictions)) if personalized else pd.DataFrame()
    model_inputs[DURATION] = predictions[DURATION]
    for target in TARGETS:
        model_name = target if personalized else target + '_duration_only'
        predictions[target] = predict_values(load_model(model_name), model_inputs[features])
    predictions['spline'] = predict_values(load_model('mip1_duration_only'), model_inputs[[DURATION]])
    return predictions
