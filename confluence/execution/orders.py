from __future__ import annotations

from typing import Dict, Any

from confluence.models.order import BinanceOrderParams


def make_robinhood_equities_ticket(symbol: str, *, side: str, qty: int, limit_price: float) -> str:
    # Text-only, for user to copy into Robinhood equities UI manually.
    side_u = side.upper()
    return f"{side_u} {qty} {symbol} LIMIT @ {limit_price:.2f} GTC"


def make_binance_limit(symbol: str, *, side: str, qty: float, price: float) -> Dict[str, Any]:
    params = BinanceOrderParams(
        symbol=symbol,
        side=side.upper(),
        type="LIMIT",
        quantity=qty,
        price=price,
        timeInForce="GTC",
    ).model_dump(exclude_none=True)
    return params


__all__ = ["make_robinhood_equities_ticket", "make_binance_limit"]

