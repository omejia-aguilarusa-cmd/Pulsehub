from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Mode = Literal["day", "swing", "hold"]


@dataclass
class Weights:
    day: float
    swing: float
    hold: float


def blend_score(raw_score: float, mode: Mode, weights: Weights) -> float:
    if mode == "day":
        return raw_score * weights.day
    if mode == "swing":
        return raw_score * weights.swing
    return raw_score * weights.hold


__all__ = ["Weights", "blend_score"]

