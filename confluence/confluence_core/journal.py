from __future__ import annotations

from confluence.db.session import AsyncSessionLocal
from confluence.journal import log_signal as _log_signal
from confluence.confluence_core.signals import StrictSignal
from confluence.models.signal import Signal, OrderTickets


def _map_strict_to_internal(s: StrictSignal) -> Signal:
    return Signal(
        id=f"strict-{s.ticker}-{s.timestamp}",
        symbol=s.ticker,
        asset_class=s.market,  # type: ignore
        side="long" if s.direction == "long" else "short",
        mode="day" if s.style == "day" else ("hold" if s.style == "buy_hold" else "swing"),
        entry=s.entry.primary,
        stop=s.stop,
        targets=s.targets,
        rr=s.rr,
        probability=s.prob_success,
        score=float(s.score),
        confidence=s.confidence,  # type: ignore
        verified_sources=[],
        rationale=", ".join(s.why),
        tickets=OrderTickets(
            robinhood_equities_text=s.order_ticket.robinhood_text,
            binance_rest_params=s.order_ticket.binance,
        ),
        metadata={"citations": s.citations, "regime": s.regime},
    )


async def log_strict_signal(s: StrictSignal) -> None:
    async with AsyncSessionLocal() as session:  # type: ignore
        await _log_signal(session, _map_strict_to_internal(s))


__all__ = ["log_strict_signal"]

