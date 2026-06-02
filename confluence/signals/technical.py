from __future__ import annotations

import pandas as pd
import pandas_ta as ta
from typing import Dict, Any


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # df has columns: open, high, low, close, volume; index is datetime
    df = df.copy()
    df["rsi"] = ta.rsi(df["close"], length=14)
    df["ema20"] = ta.ema(df["close"], length=20)
    df["ema50"] = ta.ema(df["close"], length=50)
    df["atr14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df["macd"] = macd["MACD_12_26_9"]
    df["macd_signal"] = macd["MACDs_12_26_9"]
    df["macd_hist"] = macd["MACDh_12_26_9"]
    bb = ta.bbands(df["close"], length=20, std=2)
    df["bb_upper"] = bb["BBU_20_2.0"]
    df["bb_lower"] = bb["BBL_20_2.0"]
    return df


def simple_rules_row(row: Dict[str, Any]) -> Dict[str, float]:
    score = 0.0
    rationale = []
    if row["close"] > row["ema20"] > row["ema50"]:
        score += 1.0
        rationale.append("trend_up")
    if row["macd_hist"] > 0:
        score += 0.5
        rationale.append("macd_bullish")
    if row["rsi"] < 30:
        score += 0.3
        rationale.append("rsi_oversold_rebound")
    return {"score": score, "rationale": ",".join(rationale)}


__all__ = ["compute_indicators", "simple_rules_row"]

