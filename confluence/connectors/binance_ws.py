from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import websockets


BINANCE_WS = "wss://stream.binance.com:9443/ws"
BINANCEUS_WS = "wss://stream.binance.us:9443/ws"


async def trades_stream(symbol: str, *, us: bool = False) -> AsyncIterator[dict]:
    # Symbol must be lowercase for stream
    stream = f"{symbol.lower()}@trade"
    url = f"{BINANCEUS_WS if us else BINANCE_WS}/{stream}"
    async with websockets.connect(url, ping_interval=15, ping_timeout=20) as ws:
        while True:
            msg = await ws.recv()
            yield json.loads(msg)


__all__ = ["trades_stream"]

