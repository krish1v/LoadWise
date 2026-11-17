"""Training planner built on the modelling team's prediction models and optimizer.

Source: SamuelO12/createx-loadwise, prototype/ (commit e5ec641). The fitted models, their
fitting reference and evaluation tables are vendored under planner/artifacts/.

This package is deliberately separate from `loadwise`, the model-independent data layer:
it only *reads* LoadWise daily records (see planner.features) and never changes them.
"""
import math

import numpy as np
import pandas as pd

from .predict import ARTIFACTS, TARGETS
from .recommend import recommend
from .scenarios import FITTING_PERIOD, REFERENCE_DEMO, SCHEDULE, PlanningContext

__all__ = ['PlanningContext', 'recommend', 'REFERENCE_DEMO', 'SCHEDULE', 'FITTING_PERIOD',
           'model_evidence', 'jsonable', 'TARGETS']


def jsonable(value):
    """Convert numpy/pandas values to plain JSON types (NaN -> None)."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def model_evidence():
    """Model comparison and grouped feature importance from the team's evaluation."""
    comparison = pd.read_csv(ARTIFACTS / 'model_comparison.csv')
    importance = pd.read_csv(ARTIFACTS / 'validation_importance.csv')
    return jsonable({'comparison': comparison.to_dict('records'),
                     'importance': importance.to_dict('records')})
