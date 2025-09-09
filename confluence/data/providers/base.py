from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional, List, Dict, Any


class Quote(Protocol):
    symbol: str
    price: float
    ts: float


class BaseMarketDataProvider(Protocol):
    name: str

    async def quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        ...

    async def news(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        ...

    async def earnings(self, symbol: str) -> Optional[Dict[str, Any]]:
        ...


__all__ = ["BaseMarketDataProvider"]

