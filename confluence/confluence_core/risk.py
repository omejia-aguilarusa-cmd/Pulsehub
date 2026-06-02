from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 0.5
    max_daily_drawdown_pct: float = 2.0
    max_positions_day: int = 5


def position_size(equity: float, risk_pct: float, entry: float, stop: float) -> float:
    risk_amount = equity * (risk_pct / 100.0)
    risk_per_unit = max(1e-9, abs(entry - stop))
    return max(0.0, risk_amount / risk_per_unit)


__all__ = ["RiskConfig", "position_size"]

