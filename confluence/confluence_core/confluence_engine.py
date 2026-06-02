from __future__ import annotations

from typing import List
from math import isfinite

from confluence.confluence_core.signals import StrictSignal, Entry, OrderTicket
from confluence.confluence_core.scoring import score_day, score_swing, score_hold
from confluence.confluence_core.config import CoreConfig
from confluence.execution.orders import make_robinhood_equities_ticket, make_binance_limit


def _gate(score: int, rr: float, prob: float, cfg: CoreConfig) -> bool:
    return (
        score >= cfg.get("alerts", "min_confluence_score", default=70)
        and rr >= cfg.get("alerts", "min_rr", default=2.0)
        and prob >= cfg.get("alerts", "min_prob", default=0.55)
    )


def make_strict_signal(
    ticker: str,
    market: str,
    style: str,
    entry: float,
    stop: float,
    targets: List[float],
    why: List[str],
    rr: float,
    prob_success: float,
    score_inputs: dict,
    citations: List[str] | None = None,
) -> StrictSignal | None:
    cfg = CoreConfig.load()
    if style == "day":
        score = score_day(score_inputs)
    elif style == "swing":
        score = score_swing(score_inputs)
    else:
        score = score_hold(score_inputs)

    if not _gate(score, rr, prob_success, cfg):
        return None

    direction = "long" if entry >= stop else "short"
    rh_ticket = make_robinhood_equities_ticket(ticker, side="BUY" if direction == "long" else "SELL", qty=1, limit_price=entry) if market == "equity" else None
    binance_ticket = make_binance_limit(ticker, side="BUY" if direction == "long" else "SELL", qty=1.0, price=entry) if market == "crypto" else None

    return StrictSignal(
        type="signal",
        style=style,  # type: ignore
        ticker=ticker,
        market=market,  # type: ignore
        direction=direction,  # type: ignore
        entry=Entry(primary=entry, alt=[]),
        stop=stop,
        targets=targets,
        rr=rr if isfinite(rr) else 0.0,
        prob_success=prob_success,
        score=score,
        why=why,
        catalysts=[],
        regime="mixed",
        order_ticket=OrderTicket(robinhood_text=rh_ticket, binance=binance_ticket),
        citations=citations or [],
        confidence="high",
    )


__all__ = ["make_strict_signal"]

