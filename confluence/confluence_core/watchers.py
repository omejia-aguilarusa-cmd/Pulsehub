from __future__ import annotations

from typing import List
import pandas as pd
from datetime import datetime
import numpy as np


async def dummy_ohlcv(n: int = 240) -> pd.DataFrame:
    idx = pd.date_range(end=datetime.utcnow(), periods=n, freq="1min")
    base = 100 + np.cumsum(np.random.randn(n))
    return pd.DataFrame(
        {
            "open": base + 0.1 * np.random.randn(n),
            "high": base + np.abs(np.random.randn(n)),
            "low": base - np.abs(np.random.randn(n)),
            "close": base + 0.1 * np.random.randn(n),
            "volume": np.random.rand(n) * 1000,
        },
        index=idx,
    )


async def watch_symbols(symbols: List[str]) -> dict:
    # Placeholder; provide OHLCV per symbol
    data = {}
    for s in symbols:
        data[s] = await dummy_ohlcv()
    return data


__all__ = ["watch_symbols"]

