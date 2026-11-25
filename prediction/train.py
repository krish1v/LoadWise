"""Fit the seven model families and choose winner by validation RMSE"""
import json
import argparse
import platform
import importlib.metadata
from pathlib import Path
import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, SplineTransformer
from data.prepare_data import PROCESSED, load_data
from .models import linear, ridge, lasso, spline, svr, knn, random_forest
from .predict import RESULTS, DURATION, TARGETS, HISTORY_FEATURES, predict_values
from .analysis import (calculate_metrics, feature_importance, historical_predictions, joint_response,)

MODEL_FAMILIES = [linear, ridge, lasso, spline, svr, knn, random_forest]

def build_model(model_name, parameters, estimator, features):
    steps = [('impute', SimpleImputer(strategy='median'))]
    if model_name == 'Spline Ridge':
        steps.append(('spline', SplineTransformer(n_knots=parameters['n_knots'], degree=3, knots='uniform', include_bias=False, extrapolation='constant')))
    if model_name != 'Random Forest':
        steps.append(('scale', StandardScaler()))
    if model_name in ['Lasso', 'RBF SVR']:
        estimator = TransformedTargetRegressor(regressor=estimator, transformer=StandardScaler())
    preprocessing = ColumnTransformer([('numeric', Pipeline(steps), features)])
    return Pipeline([('preprocess', preprocessing), ('model', estimator)])

def select_family_model(family, training, validation, features, target_column):
    best = None
    for name, parameters, estimator in family.configurations():
        model = build_model(name, parameters, estimator, features)
        model.fit(training[features], training[target_column])
        predictions = predict_values(model, validation[features])
        metrics = calculate_metrics(validation[target_column], predictions)
        if best is None or metrics['rmse'] < best['metrics']['rmse']:
            best = {'name': name, 'parameters': parameters, 'model': model, 'metrics': metrics}
    return best

def comparison_row(target, specification, model_name, selected, parameters, validation_metrics, test_metrics):
    row = {'target': target, 'specification': specification, 'model': model_name, 'selected': selected, 'parameters': json.dumps(parameters, sort_keys=True)}
    for name, value in validation_metrics.items():
        row['val_' + name] = value
    for name, value in test_metrics.items():
        row['test_' + name] = value
    return row

def compare_families(training, validation, test, target, specification, features, output):
    target_column = 'target_' + target
    winners = []
    for family in MODEL_FAMILIES:
        winners.append(select_family_model(family, training, validation, features, target_column))
    selected = min(winners, key=lambda candidate: candidate['metrics']['rmse'])

    fitting_data = pd.concat([training, validation])
    comparisons = []
    for winner in winners:
        fitted = clone(winner['model'])
        fitted.fit(fitting_data[features], fitting_data[target_column])
        predictions = predict_values(fitted, test[features])
        test_metrics = calculate_metrics(test[target_column], predictions)
        is_selected = winner is selected
        comparisons.append(comparison_row(target, specification, winner['name'], is_selected, winner['parameters'], winner['metrics'], test_metrics))
        if is_selected:
            suffix = '' if specification == 'joint' else '_duration_only'
            model_path = output / 'models' / (target + suffix + '.joblib')
            joblib.dump(fitted, model_path, compress=3)

    print(target, specification, selected['name'], round(selected['metrics']['rmse'], 3), flush=True)
    importance = []
    if specification == 'joint':
        importance = feature_importance(selected, validation, features, target)
    return comparisons, importance

def historical_reference(daily, training, validation, test, target):
    fitting_data = pd.concat([training, validation])
    target_column = 'target_' + target
    validation_predictions = historical_predictions(daily, validation, training, target)
    test_predictions = historical_predictions(daily, test, fitting_data, target)
    return comparison_row(target, 'history_reference', 'Historical 28d mean', False, {}, calculate_metrics(validation[target_column], validation_predictions), calculate_metrics(test[target_column], test_predictions))

def train_models(output=RESULTS, processed=PROCESSED):
    daily, data, _ = load_data(processed)
    required = ['actual_duration_min'] + ['target_' + t for t in TARGETS]
    if data[required].isna().any().any():
        raise ValueError('Training data contains missing durations or targets. Define and document an exclusion rule before fitting.')
    training = data[data.split == 'train']
    validation = data[data.split == 'validation']
    test = data[data.split == 'test']
    if any(frame.empty for frame in (training, validation, test)):
        raise ValueError('Training, validation and test splits must all contain rows.')
    if not (training.day.max() < validation.day.min() and validation.day.max() < test.day.min()):
        raise ValueError('The splits must be chronological and non-overlapping.')
    output = Path(output)
    (output / 'models').mkdir(parents=True, exist_ok=True)

    comparisons = []
    importance = []
    specifications = [('joint', HISTORY_FEATURES + [DURATION]), ('duration_only', [DURATION])]
    for target in TARGETS:
        for specification, features in specifications:
            model_rows, importance_rows = compare_families(training, validation, test, target, specification, features, output)
            comparisons.extend(model_rows)
            importance.extend(importance_rows)
        comparisons.append(historical_reference(daily, training, validation, test, target))

    pd.DataFrame(comparisons).to_csv(output / 'model_comparison.csv', index=False)
    pd.DataFrame(importance).to_csv(output / 'validation_importance.csv', index=False)
    responses = joint_response(pd.concat([training, validation]), test, output)
    responses.to_csv(output / 'joint_response.csv', index=False)
    columns = ['athlete_id', 'day', 'date_label', 'split', 'target_mip1', 'target_movement_load', 'target_training_trimp', DURATION]
    pd.concat([training, validation])[columns].to_csv(
        output / 'fitting_reference.csv', index=False)
    metadata = {
        'python': platform.python_version(),
        'packages': {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scikit-learn', 'scipy', 'joblib', 'openpyxl']},
        'split_rows': data.groupby('split').size().to_dict(),
        'features': {'joint': HISTORY_FEATURES + [DURATION], 'duration_only': [DURATION]},
        'selection': 'Lowest validation RMSE; refit on train plus validation before test scoring.'}
    (output / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return output

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', type=Path, default=RESULTS)
    parser.add_argument('--data-dir', type=Path, default=PROCESSED)
    args = parser.parse_args()
    train_models(args.output, args.data_dir)
