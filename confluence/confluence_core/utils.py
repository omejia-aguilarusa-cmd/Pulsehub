from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def now_et_iso() -> str:
    return datetime.now(tz=ZoneInfo("America/New_York")).isoformat()


__all__ = ["now_et_iso"]

