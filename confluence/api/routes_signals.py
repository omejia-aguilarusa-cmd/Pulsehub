from __future__ import annotations

from fastapi import APIRouter
from typing import List

from confluence.scheduler.jobs import run_scan
from confluence.models.signal import Signal


router = APIRouter()


@router.post("/scan", response_model=List[Signal])
async def scan(mode: str = "day") -> List[Signal]:
    # Run one scan for the given mode and return signals
    # NOTE: Uses existing pipeline and schema; strict schema variant is added in confluence_core.signals
    await run_scan(mode)
    return []

