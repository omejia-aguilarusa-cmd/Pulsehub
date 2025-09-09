from __future__ import annotations

from pathlib import Path
from typing import Optional

import joblib
import numpy as np


class ProbabilityCalibrator:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._model = None
        if path.exists():
            try:
                self._model = joblib.load(path)
            except Exception:
                self._model = None

    def predict_proba(self, score: float) -> float:
        # Fallback: map score in [0, 2] roughly to probability
        if self._model is None:
            x = max(0.0, min(2.0, score))
            return 0.35 + 0.3 * (x / 2.0)
        return float(self._model.predict_proba(np.array([[score]]))[:, 1][0])


__all__ = ["ProbabilityCalibrator"]

