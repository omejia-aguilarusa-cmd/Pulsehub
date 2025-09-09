from __future__ import annotations

from typing import Optional, Dict, Any, List

import httpx
from loguru import logger


class AlphaVantageProvider:
    name = "alphavantage"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key

    async def quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self.api_key}
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("https://www.alphavantage.co/query", params=params)
            if r.status_code != 200:
                return None
            data = r.json().get("Global Quote", {})
            p = data.get("05. price")
            if not p:
                return None
            return {"symbol": symbol, "price": float(p), "ts": 0.0}

    async def news(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        # Alpha Vantage news API requires premium; skip
        return []

    async def earnings(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        params = {"function": "EARNINGS", "symbol": symbol, "apikey": self.api_key}
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("https://www.alphavantage.co/query", params=params)
            if r.status_code != 200:
                return None
            q = r.json().get("annualEarnings", [])
            if q:
                return {"symbol": symbol, "earnings_date": q[-1].get("fiscalDateEnding"), "provider": self.name}
        return None


__all__ = ["AlphaVantageProvider"]

