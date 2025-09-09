from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List

import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from confluence.config import load_settings
from confluence.data.verification import Verifier
from confluence.signals.generator import generate_signals_for_symbol
from confluence.alerts.emit import emit_signal


async def fetch_dummy_ohlcv(symbol: str, n: int = 120) -> pd.DataFrame:
    # Placeholder fetcher: in production, use exchange/historical APIs
    import numpy as np

    idx = pd.date_range(end=datetime.utcnow(), periods=n, freq="1min")
    base = 100 + np.cumsum(np.random.randn(n))
    high = base + np.random.rand(n)
    low = base - np.random.rand(n)
    close = base + 0.5 * np.random.randn(n)
    open_ = base + 0.5 * np.random.randn(n)
    volume = np.random.rand(n) * 100
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


async def run_scan(mode: str) -> None:
    settings = load_settings()
    verifier = Verifier()
    watch = settings.watchlists.crypto if mode in ("day", "swing") else settings.watchlists.equities
    signals_all: List = []
    for sym in watch:
        df = await fetch_dummy_ohlcv(sym)
        asset_class = "crypto" if sym.upper().endswith("USDT") else "equity"
        sigs = await generate_signals_for_symbol(sym, asset_class, mode, df, verifier)
        signals_all.extend(sigs)
    for s in signals_all:
        logger.info(f"Signal {s.symbol} {s.mode} p={s.probability:.2f} rr={s.rr:.2f} verified={s.confidence}")
        await emit_signal(s)


def start_scheduler() -> AsyncIOScheduler:
    s = load_settings()
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.add_job(lambda: asyncio.create_task(run_scan("day")), CronTrigger.from_crontab(s.schedules.day))
    scheduler.add_job(lambda: asyncio.create_task(run_scan("swing")), CronTrigger.from_crontab(s.schedules.swing))
    scheduler.add_job(lambda: asyncio.create_task(run_scan("hold")), CronTrigger.from_crontab(s.schedules.hold))
    scheduler.start()
    logger.info("Scheduler started")
    return scheduler


__all__ = ["start_scheduler", "run_scan"]
