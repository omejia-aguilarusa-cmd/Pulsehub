from __future__ import annotations

from typing import Optional, List

import aiosmtplib
from email.message import EmailMessage


async def send_email(
    host: Optional[str],
    port: int,
    username: Optional[str],
    sender: Optional[str],
    to: List[str],
    subject: str,
    body: str,
    *,
    tls: bool = True,
    password: Optional[str] = None,
) -> bool:
    if not (host and sender and to):
        return False
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    if tls:
        client = aiosmtplib.SMTP(hostname=host, port=port, use_tls=False, start_tls=True)
    else:
        client = aiosmtplib.SMTP(hostname=host, port=port, use_tls=False)
    await client.connect()
    if username and password:
        await client.login(username, password)
    await client.send_message(msg)
    await client.quit()
    return True


__all__ = ["send_email"]
