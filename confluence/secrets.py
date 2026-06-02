from __future__ import annotations

import os
from typing import Optional

import keyring


def get_secret(name: str, env: Optional[str] = None, *, service: str = "confluence") -> Optional[str]:
    # Prefer OS keyring; fall back to env var
    v = keyring.get_password(service, name)
    if v:
        return v
    if env and env in os.environ:
        return os.environ.get(env)
    return None


__all__ = ["get_secret"]

