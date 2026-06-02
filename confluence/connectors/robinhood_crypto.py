from __future__ import annotations

"""
Compliance note:
- This adapter intentionally supports only Robinhood Crypto via official API keys.
- No equities endpoints are used. No username/password flows.
- If official API credentials are not provisioned, methods raise NotImplementedError.

As of writing, Robinhood does not provide a publicly accessible, self-serve retail API
for crypto order execution via API keys. When official credentials and endpoints are
available to you (e.g., partner access), set environment variables and implement the
requests in the placeholders below.
"""

from typing import Any, Dict

from loguru import logger


class RobinhoodCryptoClient:
    def __init__(self, api_key: str | None = None, api_secret: str | None = None) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        if not (self.api_key and self.api_secret):
            logger.warning("Robinhood Crypto disabled: no official API keys detected")

    def ensure_enabled(self) -> None:
        if not (self.api_key and self.api_secret):
            raise NotImplementedError(
                "Robinhood Crypto execution requires official API keys and endpoints."
            )

    async def place_order(self, **kwargs: Any) -> Dict[str, Any]:
        self.ensure_enabled()
        # Placeholder for official API request once available to you.
        raise NotImplementedError("Implement Robinhood Crypto order via official API only.")


__all__ = ["RobinhoodCryptoClient"]

