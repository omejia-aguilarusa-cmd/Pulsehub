from __future__ import annotations

from typing import List


def robinhood_equity_text(
    symbol: str,
    side: str,
    qty: float,
    entry: float,
    stop: float | None = None,
    targets: List[float] | None = None,
    tif: str = "DAY",
) -> str:
    parts = [f"{side.upper()} {qty:g} {symbol} @ {entry:.2f} LMT"]
    if stop is not None:
        parts.append(f"STP {stop:.2f}")
    if targets:
        parts.append("TGT " + "/".join(f"{t:.2f}" for t in targets))
    parts.append(f"TIF:{tif}")
    return ", ".join(parts)


__all__ = ["robinhood_equity_text"]

