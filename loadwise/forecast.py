"""Bridge to the Option B prediction layer (athlete-aware Ridge regression).

This connects the LoadWise *data layer* to the teammate-built workload
**prediction** module. It loads the trained model artifact
(`forecast/loadwise_model.joblib`) and exposes a small, UI-agnostic API:

    predicted session TRIMP = planned duration (min) x max(0, learned TRIMP/min)

The learned TRIMP/min comes from one Ridge regression over
(athlete historical TRIMP/min, athlete identity). Unseen athletes fall back to
the global median rate (cold start). We do **not** re-train here -- we consume
the saved artifact exactly as produced by `loadwise_predict.py`.

Scope (per the milestone brief): this predicts an upcoming *training* session's
TRIMP only. It does NOT predict injuries, readiness, wellness, high-speed
running, or game load, and training/game loads are not interchangeable.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Optional

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "forecast", "loadwise_model.joblib")


class ForecastUnavailable(Exception):
    """Raised when the model artifact or its dependencies cannot be loaded."""


@lru_cache(maxsize=1)
def load_model(path: str = MODEL_PATH) -> dict:
    """Load and cache the trained model bundle.

    Returns the dict saved by loadwise_predict.py:
    {model, players, rates, global_rate, gd_rates, results}.
    """
    if not os.path.exists(path):
        raise ForecastUnavailable(f"Model artifact not found at {path}. "
                                  "Copy loadwise_model.joblib into the forecast/ folder.")
    try:
        import warnings
        import joblib  # local import so the data layer has no hard ML dependency
        # The saved Ridge pipeline is a simple linear model; a scikit-learn
        # minor-version bump only emits a cosmetic InconsistentVersionWarning
        # (predictions are unaffected). Silence it so the console stays clean.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*version.*", category=UserWarning)
            try:
                from sklearn.exceptions import InconsistentVersionWarning
                warnings.simplefilter("ignore", InconsistentVersionWarning)
            except Exception:
                pass
            return joblib.load(path)
    except ImportError as e:
        raise ForecastUnavailable(
            "scikit-learn / joblib are required for the forecast layer "
            "(`pip install scikit-learn joblib`).") from e
    except Exception as e:  # pragma: no cover - corrupt artifact
        raise ForecastUnavailable(f"Could not load the model: {e}") from e


def _features(player: str, past_rate: float, players: List[str]) -> List[float]:
    """Exactly mirror loadwise_predict.features(): rate + identity one-hot."""
    return [past_rate] + [int(player == p) for p in players[:-1]]


class Forecaster:
    """Thin, deterministic wrapper around the saved prediction model."""

    def __init__(self, bundle: Optional[dict] = None):
        self.bundle = bundle or load_model()
        self.model = self.bundle["model"]
        self.players: List[str] = list(self.bundle["players"])
        self.rates: Dict[str, float] = dict(self.bundle["rates"])
        self.global_rate: float = float(self.bundle["global_rate"])
        self.gd_rates: Dict[str, Dict[str, float]] = dict(self.bundle.get("gd_rates", {}))
        self.results: dict = dict(self.bundle.get("results", {}))

    # -- identity -----------------------------------------------------------
    def known_athletes(self) -> List[str]:
        return list(self.players)

    def is_known(self, athlete_label: str) -> bool:
        return athlete_label in self.rates

    # -- rates / predictions ------------------------------------------------
    def historical_rate(self, athlete_label: str) -> float:
        """Frozen (training-cutoff) historical median TRIMP/min for the athlete."""
        return self.rates.get(athlete_label, self.global_rate)

    def predicted_rate(self, athlete_label: str) -> float:
        """Model-calibrated TRIMP/min (always >= 0)."""
        past = self.historical_rate(athlete_label)
        import numpy as np
        feats = _features(athlete_label, past, self.players)
        return float(np.maximum(0.0, self.model.predict([feats])[0]))

    def predict_session(self, athlete_label: str, planned_minutes: float) -> float:
        """Predicted TRIMP for one planned training session."""
        return self.predicted_rate(athlete_label) * max(0.0, float(planned_minutes))

    def forecast(self, athlete_label: str, planned_minutes: List[float]) -> dict:
        """Multi-day forecast for one athlete.

        Returns per-day predictions plus the horizon total, the rates used, and
        cold-start / provenance context.
        """
        rate = self.predicted_rate(athlete_label)
        days = [{
            "day_index": i + 1,
            "planned_minutes": round(float(m), 1),
            "predicted_trimp": round(rate * max(0.0, float(m)), 1),
        } for i, m in enumerate(planned_minutes)]
        return {
            "athlete_label": athlete_label,
            "known_athlete": self.is_known(athlete_label),
            "historical_trimp_per_min": round(self.historical_rate(athlete_label), 4),
            "model_trimp_per_min": round(rate, 4),
            "global_fallback_rate": round(self.global_rate, 4),
            "days": days,
            "horizon_total_trimp": round(sum(d["predicted_trimp"] for d in days), 1),
            "comparable_day_rates": {k: round(v, 4)
                                     for k, v in self.gd_rates.get(athlete_label, {}).items()},
        }

    def baseline_export(self, athlete_label: str, planned_minutes: List[float],
                        start_date: Optional[str] = None) -> dict:
        """Standardized JSON for the optimizer's 'expected baseline workload' input.

        This is the hand-off contract between the prediction layer and the
        future optimization layer: a per-day expected training TRIMP baseline.
        """
        fc = self.forecast(athlete_label, planned_minutes)
        return {
            "schemaVersion": "forecast-1.0.0",
            "kind": "expected_baseline_workload",
            "metric": "training_trimp",
            "athlete_label": athlete_label,
            "known_athlete": fc["known_athlete"],
            "model": {
                "type": "athlete_informed_ridge_regression",
                "trimp_per_min": fc["model_trimp_per_min"],
                "historical_trimp_per_min": fc["historical_trimp_per_min"],
                "cold_start_fallback_used": not fc["known_athlete"],
            },
            "start_date": start_date,
            "daily_baseline": [
                {"day_offset": d["day_index"] - 1,
                 "planned_minutes": d["planned_minutes"],
                 "expected_training_trimp": d["predicted_trimp"]}
                for d in fc["days"]
            ],
            "horizon_total_trimp": fc["horizon_total_trimp"],
            "validation": self.results,
            "caveats": [
                "Predicts TRAINING session TRIMP only; not games, injury, readiness, or HSR.",
                "Historical actual duration proxied for planned duration in validation.",
                "Small holdout (50), one unseen athlete, no game-relative-day labels at test.",
                "Treat the reported accuracy advantage as exploratory, not confirmatory.",
            ],
        }
