from __future__ import annotations

import hmac
import hashlib
import time
from typing import Dict, Any, Optional

import httpx
from aiolimiter import AsyncLimiter
from loguru import logger


BINANCE_BASE = "https://api.binance.com"
BINANCEUS_BASE = "https://api.binance.us"


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, *, us: bool = False) -> None:
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.base = BINANCEUS_BASE if us else BINANCE_BASE
        # Basic rate-limit awareness: 1200 weight/min default; budget tokens
        self.limiter = AsyncLimiter(max_rate=240, time_period=60)

    async def _signed(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        async with self.limiter:
            ts = int(time.time() * 1000)
            q = params.copy() if params else {}
            q.update({"timestamp": ts})
            query = "&".join([f"{k}={q[k]}" for k in sorted(q.keys())])
            sig = hmac.new(self.api_secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
            q["signature"] = sig
            headers = {"X-MBX-APIKEY": self.api_key}
            async with httpx.AsyncClient(base_url=self.base, timeout=10.0) as client:
                r = await client.request(method, path, params=q, headers=headers)
                if r.status_code != 200:
                    logger.error(f"binance error {r.status_code} {r.text}")
                    raise httpx.HTTPStatusError("Binance error", request=r.request, response=r)
                # Optional: read used weight header
                used = r.headers.get("X-MBX-USED-WEIGHT-1M")
                if used:
                    logger.debug(f"binance used-weight-1m={used}")
                return r.json()

    async def account(self) -> Dict[str, Any]:
        return await self._signed("GET", "/api/v3/account")

    async def order(self, **kwargs: Any) -> Dict[str, Any]:
        return await self._signed("POST", "/api/v3/order", params=kwargs)

    async def cancel_order(self, symbol: str, orderId: int) -> Dict[str, Any]:
        return await self._signed("DELETE", "/api/v3/order", params={"symbol": symbol, "orderId": orderId})


__all__ = ["BinanceClient"]

