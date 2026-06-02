from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal, Dict, Any

from pydantic import BaseModel, Field


Confidence = Literal["high", "low"]
Mode = Literal["day", "swing", "hold"]
AssetClass = Literal["equity", "crypto"]
Side = Literal["long", "short"]


class OrderTickets(BaseModel):
    robinhood_equities_text: Optional[str] = None
    binance_rest_params: Optional[Dict[str, Any]] = None


class Signal(BaseModel):
    id: str
    t: datetime = Field(default_factory=datetime.utcnow)
    symbol: str
    asset_class: AssetClass
    side: Side
    mode: Mode

    entry: float
    stop: float
    targets: List[float]
    rr: float
    probability: float
    score: float
    confidence: Confidence
    verified_sources: List[str] = Field(default_factory=list)

    rationale: str

    tickets: OrderTickets
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["Signal", "OrderTickets", "Mode", "AssetClass", "Side"]

