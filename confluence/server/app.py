from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from confluence.models.signal import Signal


app = FastAPI(title="Confluence", version="0.1.0")


class Health(BaseModel):
    status: str


@app.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok")


@app.post("/webhook/signal", response_model=Signal)
async def ingest_signal(signal: Signal) -> Signal:
    # Accept externally generated signals (signed webhooks can be added)
    return signal


__all__ = ["app"]

