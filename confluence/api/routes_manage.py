from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict

from confluence.config import load_settings


class ConfigUpdate(BaseModel):
    alerts: Dict[str, Any] | None = None
    risk: Dict[str, Any] | None = None


router = APIRouter()


@router.post("/config")
async def update_config(cfg: ConfigUpdate) -> dict:
    # In-memory update only for runtime; persist separately if needed
    s = load_settings()
    if cfg.alerts:
        for k, v in cfg.alerts.items():
            if hasattr(s.alerts, k):
                setattr(s.alerts, k, v)
    if cfg.risk and hasattr(s, "risk"):
        for k, v in cfg.risk.items():
            setattr(s, k, v)
    return {"status": "ok"}

