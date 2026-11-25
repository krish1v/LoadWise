"""Summarize prediction errors and inspect how fitted models behave"""
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .predict import (DURATION, HISTORY_FEATURES, FEATURE_GROUPS, predict_values, supported_durations,)

def calculate_metrics(actual, predicted):
    return {
        'mae': float(mean_absolute_error(actual, predicted)),
        'rmse': float(np.sqrt(mean_squared_error(actual, predicted))),
        'r2': float(r2_score(actual, predicted)),
        'n': len(actual)}

def feature_importance(selected, validation, features, target):
    # Shuffle one feature group at a time and record the change in RMSE
    rng = np.random.default_rng(42)
    groups = {'Current recorded duration': [DURATION], **FEATURE_GROUPS}
    target_column = 'target_' + target
    baseline_rmse = selected['metrics']['rmse']
    results = []

    for group, columns in groups.items():
        changes = []
        for _ in range(30):
            shuffled = validation[features].copy()
            order = rng.permutation(len(validation))
            shuffled[columns] = shuffled[columns].to_numpy()[order]
            predictions = predict_values(selected['model'], shuffled)
            rmse = calculate_metrics(validation[target_column], predictions)['rmse']
            changes.append(rmse - baseline_rmse)
        results.append({'target': target, 'model': selected['name'], 'group': group, 'mean_delta_rmse': np.mean(changes), 'sd_delta_rmse': np.std(changes)})
    return results

def historical_predictions(daily, observations, reference, target):
    predictions = []
    for observation in observations.itertuples():
        past = daily[(daily.athlete_id == observation.athlete_id) & (daily.day < observation.day)]
        recent_mean = past.loc[past.day >= observation.day - 28, target].mean()
        earlier_values = past[target].dropna()
        if pd.notna(recent_mean):
            prediction = recent_mean
        elif len(earlier_values):
            prediction = earlier_values.iloc[-1]
        else:
            prediction = reference['target_' + target].median()
        predictions.append(prediction)
    return predictions

def joint_response(fitting_data, test, output):
    # Compare 120 and 180 minutes while holding each athlete history fixed
    model = joblib.load(output / 'models/mip1.joblib')
    supported = []
    for row in test.itertuples():
        supported.append(supported_durations(fitting_data, row.athlete_id, [120, 180]).all())
    states = test.loc[supported].copy()
    for duration in [120, 180]:
        model_inputs = states[HISTORY_FEATURES].copy()
        model_inputs[DURATION] = duration
        states[f'mip_{duration}'] = predict_values(model, model_inputs)

    contrasts = []
    for feature in ['all', 'training_trimp_sum_7d', 'movement_load_sum_7d', 'mip1_mean_7d']:
        groups = [('all', states)]
        if feature != 'all':
            lower, upper = fitting_data[feature].quantile([1/3, 2/3])
            groups = [
                ('lower', states[states[feature] <= lower]),
                ('middle', states[(states[feature] > lower) & (states[feature] <= upper)]),
                ('higher', states[states[feature] > upper])]
        for group, histories in groups:
            mean_120 = histories.mip_120.mean()
            mean_180 = histories.mip_180.mean()
            contrasts.append({
                'feature': feature, 'group': group, 'n': len(histories),
                'mean_low': mean_120, 'mean_high': mean_180,
                'mean_delta': mean_180 - mean_120})

    return pd.DataFrame(contrasts)

