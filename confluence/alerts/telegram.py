from __future__ import annotations

from typing import Optional
import httpx


async def send_telegram(bot_token: Optional[str], chat_id: Optional[str], text: str) -> bool:
    if not (bot_token and chat_id):
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
        return r.status_code == 200


__all__ = ["send_telegram"]

