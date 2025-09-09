from __future__ import annotations

from typing import List, Dict, Any, Optional
import httpx


class NewsGeneric:
    def __init__(self, api_key: Optional[str]) -> None:
        self.key = api_key

    async def news(self, query: str, limit: int = 4) -> List[Dict[str, Any]]:
        if not self.key:
            return []
        url = "https://newsapi.org/v2/everything"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, params={"q": query, "pageSize": limit, "apiKey": self.key})
            if r.status_code != 200:
                return []
            out: List[Dict[str, Any]] = []
            for a in r.json().get("articles", [])[:limit]:
                out.append({"title": a.get("title"), "url": a.get("url"), "publishedAt": a.get("publishedAt")})
            return out


__all__ = ["NewsGeneric"]

