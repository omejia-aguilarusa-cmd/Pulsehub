from __future__ import annotations

from typing import Any, Dict

from confluence.connectors.binance import BinanceClient as _BinanceClient


class BinanceClient(_BinanceClient):
    def __init__(self, api_key: str, api_secret: str, *, base: str = "binance_us") -> None:
        super().__init__(api_key, api_secret, us=(base == "binance_us"))


__all__ = ["BinanceClient"]

