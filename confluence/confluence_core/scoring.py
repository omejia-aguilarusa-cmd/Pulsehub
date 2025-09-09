from __future__ import annotations

from typing import Dict


def score_day(f: Dict[str, float]) -> int:
    # Trend 20, Level 25, Trigger 25, RVOL 15, Volatility 10, Catalyst −10
    s = 0.0
    s += min(20.0, max(0.0, 20.0 * f.get("trend", 0.0)))
    s += min(25.0, max(0.0, 25.0 * f.get("level", 0.0)))
    s += min(25.0, max(0.0, 25.0 * f.get("trigger", 0.0)))
    s += min(15.0, max(0.0, 15.0 * f.get("rvol", 0.0)))
    s += min(10.0, max(0.0, 10.0 * f.get("volatility", 0.0)))
    s -= min(10.0, max(0.0, 10.0 * f.get("catalyst_risk", 0.0)))
    return int(round(s))


def score_swing(f: Dict[str, float]) -> int:
    s = 0.0
    s += min(25.0, 25.0 * f.get("htf_trend", 0.0))
    s += min(25.0, 25.0 * f.get("base", 0.0))
    s += min(20.0, 20.0 * f.get("break_retest", 0.0))
    s += min(15.0, 15.0 * f.get("fundamentals", 0.0))
    s -= min(10.0, 10.0 * f.get("catalyst_risk", 0.0))
    s += min(15.0, 15.0 * f.get("rr", 0.0))
    return int(round(s))


def score_hold(f: Dict[str, float]) -> int:
    s = 0.0
    s += min(25.0, 25.0 * f.get("quality", 0.0))
    s += min(20.0, 20.0 * f.get("earnings_durability", 0.0))
    s += min(15.0, 15.0 * f.get("balance_sheet", 0.0))
    s += min(20.0, 20.0 * f.get("valuation", 0.0))
    s += min(10.0, 10.0 * f.get("tailwinds", 0.0))
    s += min(10.0, 10.0 * f.get("dd_profile", 0.0))
    return int(round(s))


__all__ = ["score_day", "score_swing", "score_hold"]

