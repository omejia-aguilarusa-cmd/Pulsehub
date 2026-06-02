from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


DEFAULT_PATH = Path("confluence/config.yaml")


class CoreConfig:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data

    @classmethod
    def load(cls, path: Path | None = None) -> "CoreConfig":
        p = path or DEFAULT_PATH
        raw = yaml.safe_load(p.read_text()) if p.exists() else {}
        return cls(raw)

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node


__all__ = ["CoreConfig", "DEFAULT_PATH"]

