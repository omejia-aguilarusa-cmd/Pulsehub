from __future__ import annotations

import asyncio
from typing import List, Dict, Any, Optional, Tuple

from loguru import logger

from confluence.config import load_settings
from confluence.data.providers.base import BaseMarketDataProvider
from confluence.data.providers.yahoo import YahooProvider
from confluence.data.providers.alphavantage import AlphaVantageProvider
from confluence.data.providers.binance_public import BinancePublicProvider


class Verifier:
    def __init__(self, providers: Optional[List[BaseMarketDataProvider]] = None) -> None:
        s = load_settings()
        if providers is None:
            providers = [
                YahooProvider(),
                AlphaVantageProvider(api_key=s.provider_keys.alphavantage_key),
                BinancePublicProvider(),
            ]
        # Filter out providers with missing API keys by probing quote(None)? we keep and let return None
        self.providers = providers
        self.min_sources = s.min_sources_required
        self.timeout = s.verify_timeout_seconds

    async def verify_quote(self, symbol: str) -> Tuple[Optional[float], List[str]]:
        tasks = [p.quote(symbol) for p in self.providers]
        results: List[Optional[Dict[str, Any]]] = []
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=False), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.debug("verify_quote timeout")

        prices: List[float] = []
        sources: List[str] = []
        for p, res in zip(self.providers, results or []):
            if res and (price := res.get("price")):
                prices.append(float(price))
                sources.append(p.name)
        if len(prices) >= self.min_sources:
            avg = sum(prices) / len(prices)
            return avg, sources
        return None, sources

    async def verify_news_and_earnings(self, symbol: str) -> Tuple[int, int, List[str]]:
        sources: List[str] = []
        news_count = 0
        earnings_hits = 0
        tasks_n = [p.news(symbol) for p in self.providers]
        tasks_e = [p.earnings(symbol) for p in self.providers]
        try:
            news_res, earn_res = await asyncio.wait_for(
                asyncio.gather(asyncio.gather(*tasks_n), asyncio.gather(*tasks_e)),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            return 0, 0, sources
        for p, items in zip(self.providers, news_res):
            if items:
                sources.append(p.name)
                news_count += len(items)
        for p, e in zip(self.providers, earn_res):
            if e:
                if p.name not in sources:
                    sources.append(p.name)
                earnings_hits += 1
        return news_count, earnings_hits, sources


__all__ = ["Verifier"]

