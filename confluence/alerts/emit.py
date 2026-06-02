from __future__ import annotations

from typing import List

from loguru import logger

from confluence.config import load_settings
from confluence.models.signal import Signal
from confluence.alerts.slack import send_slack
from confluence.alerts.telegram import send_telegram
from confluence.alerts.email import send_email
from confluence.secrets import get_secret
from confluence.db.session import AsyncSessionLocal
from confluence.journal import log_signal


def format_signal_text(s: Signal) -> str:
    tgt = ", ".join(f"{t:.2f}" for t in s.targets)
    return (
        f"{s.symbol} {s.side.upper()} [{s.mode}]\n"
        f"entry {s.entry:.4f} | stop {s.stop:.4f} | targets [{tgt}]\n"
        f"RR {s.rr:.2f} | p {s.probability:.2f} | score {s.score:.2f} | conf {s.confidence}\n"
        f"Sources: {', '.join(s.verified_sources)}\n"
        f"Rationale: {s.rationale}\n"
        f"RH ticket: {s.tickets.robinhood_equities_text or '-'}"
    )


async def emit_signal(s: Signal, recipients_email: List[str] | None = None) -> None:
    cfg = load_settings()
    text = format_signal_text(s)
    ok_slack = await send_slack(cfg.alerts.slack_webhook_url, text)
    ok_tg = await send_telegram(cfg.alerts.telegram_bot_token, cfg.alerts.telegram_chat_id, text)
    smtp_pass = get_secret("smtp_password", env=None)
    if recipients_email:
        await send_email(
            cfg.alerts.smtp_host,
            cfg.alerts.smtp_port,
            cfg.alerts.smtp_user,
            cfg.alerts.smtp_from,
            to=recipients_email,
            subject=f"Confluence signal {s.symbol} {s.mode}",
            body=text,
            tls=cfg.alerts.smtp_tls,
            password=smtp_pass,
        )
    logger.info(f"Alert sent slack={ok_slack} telegram={ok_tg}")
    # Persist signal
    async with AsyncSessionLocal() as session:  # type: ignore
        await log_signal(session, s)


__all__ = ["emit_signal", "format_signal_text"]
