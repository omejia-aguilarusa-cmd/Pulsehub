from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from confluence.models.signal import Signal
from confluence.db.models import SignalLog


async def log_signal(session: AsyncSession, s: Signal) -> None:
    obj = SignalLog(
        signal_id=s.id,
        symbol=s.symbol,
        asset_class=s.asset_class,
        side=s.side,
        mode=s.mode,
        entry=s.entry,
        stop=s.stop,
        probability=s.probability,
        score=s.score,
        rr=s.rr,
        confidence=s.confidence,
        sources={"verified_sources": s.verified_sources},
    )
    session.add(obj)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"failed to log signal: {e}")


__all__ = ["log_signal"]

