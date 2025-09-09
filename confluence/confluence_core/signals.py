from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Dict, Any

from pydantic import BaseModel, Field


SignalType = Literal["signal", "heads_up", "exit"]
Style = Literal["day", "swing", "buy_hold"]
Market = Literal["equity", "crypto"]
Direction = Literal["long", "short"]
Confidence = Literal["low", "medium", "high"]


class Entry(BaseModel):
    primary: float
    alt: List[float] = Field(default_factory=list)


class Catalyst(BaseModel):
    when: str
    what: str
    verified_from: List[str]


class OrderTicket(BaseModel):
    robinhood_text: Optional[str] = None
    binance: Optional[Dict[str, Any]] = None


class StrictSignal(BaseModel):
    type: SignalType
    style: Style
    ticker: str
    market: Market
    direction: Direction
    entry: Entry
    stop: float
    targets: List[float]
    rr: float
    prob_success: float
    score: int
    why: List[str]
    catalysts: List[Catalyst] = Field(default_factory=list)
    regime: Literal["risk-on", "mixed", "risk-off"]
    order_ticket: OrderTicket
    citations: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    confidence: Confidence


__all__ = ["StrictSignal", "OrderTicket", "Entry", "Catalyst"]

