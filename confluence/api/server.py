from __future__ import annotations

from fastapi import FastAPI

from confluence.api.routes_signals import router as signals_router
from confluence.api.routes_manage import router as manage_router


app = FastAPI(title="Confluence", version="0.1.0")

app.include_router(signals_router, prefix="/signals", tags=["signals"])
app.include_router(manage_router, prefix="/manage", tags=["manage"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

