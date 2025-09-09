from __future__ import annotations

from typing import Optional, Dict, Any, List

import httpx


BINANCE_PUBLIC = "https://api.binance.com"


class BinancePublicProvider:
    name = "binance_public"

    async def quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        url = f"{BINANCE_PUBLIC}/api/v3/ticker/price"
        params = {"symbol": symbol}
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return None
            d = r.json()
            return {"symbol": symbol, "price": float(d["price"]), "ts": 0.0}

    async def news(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        return []

    async def earnings(self, symbol: str) -> Optional[Dict[str, Any]]:
        return None


__all__ = ["BinancePublicProvider"]

