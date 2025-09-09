from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from typing import List

import pandas as pd
from loguru import logger

from confluence.models.signal import Signal, OrderTickets
from confluence.signals.technical import compute_indicators, simple_rules_row
from confluence.signals.scoring import Weights, blend_score
from confluence.signals.calibration import ProbabilityCalibrator
from pathlib import Path
from confluence.execution.orders import make_robinhood_equities_ticket, make_binance_limit
from confluence.data.verification import Verifier


async def generate_signals_for_symbol(
    symbol: str,
    asset_class: str,
    mode: str,
    df: pd.DataFrame,
    verifier: Verifier,
) -> List[Signal]:
    df_ind = compute_indicators(df)
    last = df_ind.iloc[-1].to_dict()
    rules = simple_rules_row(last)
    raw_score = float(rules["score"])  # 0..something

    # Blend score per mode weights
    weights = Weights(day=0.5, swing=0.3, hold=0.2)
    blended = blend_score(raw_score, mode, weights)

    # Calibrate to probability
    prob = ProbabilityCalibrator(path=Path("./prob.calib"))
    probability = prob.predict_proba(blended)

    # Entry/stop/targets via ATR
    price = float(last["close"])  # assume df prices in close
    atr = float(last.get("atr14", 0.0) or 0.0)
    entry = price
    stop = max(0.0, price - 1.5 * atr)
    targets = [price + k * atr for k in (1.0, 2.0, 3.0)]
    rr = (targets[0] - entry) / (entry - stop) if (entry - stop) > 0 else 0.0

    # Verify data from >=2 sources
    v_price, quote_sources = await verifier.verify_quote(symbol)
    news_count, earnings_hits, ne_sources = await verifier.verify_news_and_earnings(symbol)
    all_sources = sorted(set(quote_sources + ne_sources))
    quotes_ok = (v_price is not None) and (len(quote_sources) >= verifier.min_sources)
    info_ok = (news_count > 0 or earnings_hits > 0) and (len(ne_sources) >= verifier.min_sources)
    verified = quotes_ok and info_ok
    confidence = "high" if verified else "low"

    # If not verified, suppress signal emission by returning empty list
    if not verified:
        logger.info(f"Suppressed low-confidence signal for {symbol} ({mode}) — sources={all_sources}")
        return []

    sid = hashlib.sha256(f"{symbol}-{asset_class}-{mode}-{datetime.utcnow().isoformat()}".encode()).hexdigest()[0:12]
    rationale = f"trend={rules['rationale']} atr={atr:.2f} news={news_count} earnings_hits={earnings_hits}"

    tickets = OrderTickets(
        robinhood_equities_text=make_robinhood_equities_ticket(symbol, side="BUY", qty=1, limit_price=entry),
        binance_rest_params=make_binance_limit(symbol if asset_class == "crypto" else "", side="BUY", qty=1.0, price=entry) if asset_class == "crypto" else None,
    )

    signal = Signal(
        id=sid,
        symbol=symbol,
        asset_class=asset_class,  # type: ignore
        side="long",
        mode=mode,  # type: ignore
        entry=entry,
        stop=stop,
        targets=targets,
        rr=rr,
        probability=probability,
        score=blended,
        confidence=confidence,  # type: ignore
        verified_sources=all_sources,
        rationale=rationale,
        tickets=tickets,
        metadata={"v_price": v_price},
    )
    return [signal]


__all__ = ["generate_signals_for_symbol"]
