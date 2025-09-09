from __future__ import annotations

import time
from typing import Optional, Dict, Any, List

import httpx
from loguru import logger


BASE_URL = "https://query2.finance.yahoo.com"


class YahooProvider:
    name = "yahoo"

    async def quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        url = f"{BASE_URL}/v7/finance/quote"
        params = {"symbols": symbol}
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                logger.debug(f"yahoo quote {symbol} status={r.status_code}")
                return None
            data = r.json().get("quoteResponse", {}).get("result", [])
            if not data:
                return None
            q = data[0]
            price = q.get("regularMarketPrice")
            ts = q.get("regularMarketTime") or int(time.time())
            if price is None:
                return None
            return {"symbol": symbol, "price": float(price), "ts": float(ts)}

    async def news(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        # Use Yahoo finance RSS-like endpoint
        url = f"{BASE_URL}/v1/finance/search"
        params = {"q": symbol}
        items: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return items
            for it in r.json().get("news", [])[:limit]:
                items.append({
                    "title": it.get("title"),
                    "link": it.get("link"),
                    "publisher": it.get("publisher"),
                    "provider": self.name,
                })
        return items

    async def earnings(self, symbol: str) -> Optional[Dict[str, Any]]:
        # Yahoo calendar for earnings
        url = f"{BASE_URL}/v10/finance/quoteSummary/{symbol}"
        params = {"modules": "calendarEvents"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return None
            d = r.json().get("quoteSummary", {}).get("result", [{}])[0]
            cal = (d or {}).get("calendarEvents", {})
            e = cal.get("earnings", {}).get("earningsDate", [])
            if e:
                # Use first date
                dt = e[0].get("fmt") or e[0].get("raw")
                return {"symbol": symbol, "earnings_date": dt, "provider": self.name}
        return None


__all__ = ["YahooProvider"]

