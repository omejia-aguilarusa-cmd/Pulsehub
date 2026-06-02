from __future__ import annotations

from typing import Optional, Dict, Any

from confluence.data.providers.yahoo import YahooProvider


class QuotesYahoo:
    def __init__(self) -> None:
        self.p = YahooProvider()

    async def quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        return await self.p.quote(symbol)


__all__ = ["QuotesYahoo"]

