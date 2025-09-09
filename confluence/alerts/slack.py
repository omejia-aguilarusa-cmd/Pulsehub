from __future__ import annotations

import json
from typing import Optional

import httpx
from loguru import logger


async def send_slack(webhook_url: Optional[str], text: str) -> bool:
    if not webhook_url:
        return False
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(webhook_url, content=json.dumps({"text": text}))
        if r.status_code != 200:
            logger.error(f"slack webhook error {r.status_code} {r.text}")
            return False
    return True


__all__ = ["send_slack"]

