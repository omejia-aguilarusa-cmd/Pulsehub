from __future__ import annotations

from typing import Optional, Dict, Any
import httpx


class QuotesPolygon:
    def __init__(self, api_key: str | None) -> None:
        self.key = api_key

    async def quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.key:
            return None
        url = f"https://api.polygon.io/v2/last/nbbo/{symbol}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, params={"apiKey": self.key})
            if r.status_code != 200:
                return None
            d = r.json()
            p = d.get("results", {}).get("p") or d.get("results", {}).get("askPrice")
            if not p:
                return None
            return {"symbol": symbol, "price": float(p), "ts": 0.0}


__all__ = ["QuotesPolygon"]

