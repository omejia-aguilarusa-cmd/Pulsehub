from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel


OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "STOP_LOSS", "TAKE_PROFIT", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"]


class BinanceOrderParams(BaseModel):
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: float
    price: Optional[float] = None
    timeInForce: Optional[str] = None
    stopPrice: Optional[float] = None
    recvWindow: int = 5000


__all__ = ["BinanceOrderParams"]

