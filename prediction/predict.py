"""Share the application's feature contract and prediction checks with training"""
from pathlib import Path
from planner.predict import (DURATION, TARGETS, HISTORY_FEATURES, FEATURE_GROUPS,predict_values, supported_durations)

RESULTS = Path(__file__).resolve().parent / 'reproduced_results'
