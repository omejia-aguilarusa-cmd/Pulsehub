from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


class Schedules(BaseModel):
    # Cron-style schedules in America/New_York
    day: str = Field(default="*/5 9-16 * * 1-5")
    swing: str = Field(default="0 */30 9-16 * * 1-5")
    hold: str = Field(default="0 18 * * 1-5")


class Watchlists(BaseModel):
    equities: List[str] = Field(default_factory=list)
    crypto: List[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])


class ProviderKeys(BaseModel):
    alphavantage_key: Optional[str] = None
    polygon_key: Optional[str] = None
    finnhub_key: Optional[str] = None


class ExchangeKeys(BaseModel):
    binance_key: Optional[str] = None
    binance_secret: Optional[str] = None
    binanceus_key: Optional[str] = None
    binanceus_secret: Optional[str] = None
    # Robinhood Crypto: official API only; leave blank unless provided
    robinhood_crypto_key: Optional[str] = None
    robinhood_crypto_secret: Optional[str] = None


class Alerting(BaseModel):
    slack_webhook_url: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_tls: bool = True


class ConfluenceSettings(BaseSettings):
    model_config = SettingsConfigModel = SettingsConfigDict(env_prefix="CONFLUENCE_", env_file=CONFIG_DIR / ".env")

    # Logging
    log_level: str = Field(default="INFO")

    # Mode weights
    day_weight: float = 0.5
    swing_weight: float = 0.3
    hold_weight: float = 0.2

    schedules: Schedules = Field(default_factory=Schedules)
    watchlists: Watchlists = Field(default_factory=Watchlists)

    provider_keys: ProviderKeys = Field(default_factory=ProviderKeys)
    exchange_keys: ExchangeKeys = Field(default_factory=ExchangeKeys)
    alerts: Alerting = Field(default_factory=Alerting)

    database_url: str = Field(default="sqlite+aiosqlite:///./confluence.db")

    verify_timeout_seconds: float = 3.0
    min_sources_required: int = 2

    def apply_yaml(self, path: Path | None = None) -> None:
        cfg_path = path or (CONFIG_DIR / "config.yml")
        if cfg_path.exists():
            data = yaml.safe_load(cfg_path.read_text()) or {}
            for k, v in data.items():
                if hasattr(self, k):
                    setattr(self, k, v)


def load_settings() -> ConfluenceSettings:
    s = ConfluenceSettings()
    cfg = CONFIG_DIR / "config.yml"
    if cfg.exists():
        s.apply_yaml(cfg)
    return s


__all__ = ["ConfluenceSettings", "load_settings", "CONFIG_DIR"]

