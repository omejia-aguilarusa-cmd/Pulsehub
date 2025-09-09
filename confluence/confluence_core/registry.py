from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List

from confluence.data.providers.yahoo import YahooProvider
from confluence.data.providers.alphavantage import AlphaVantageProvider


@dataclass
class ProviderSpec:
    name: str
    params: Dict[str, Any]


def parse_spec(item: str) -> ProviderSpec:
    # Example: "polygon?api_key=${POLYGON_KEY}"
    if "?" not in item:
        return ProviderSpec(name=item, params={})
    name, query = item.split("?", 1)
    params: Dict[str, Any] = {}
    for kv in query.split("&"):
        if not kv:
            continue
        k, v = kv.split("=", 1)
        if v.startswith("${") and v.endswith("}"):
            env_name = v[2:-1]
            params[k] = os.getenv(env_name)
        else:
            params[k] = v
    return ProviderSpec(name=name, params=params)


def build_providers(specs: List[str]):
    providers = []
    for s in specs:
        sp = parse_spec(s)
        if sp.name == "yahoo":
            providers.append(YahooProvider())
        elif sp.name == "alphavantage":
            providers.append(AlphaVantageProvider(api_key=sp.params.get("api_key")))
        # Placeholders for polygon/iex/newsapi etc. to be added in datafeeds
    return providers


__all__ = ["build_providers", "parse_spec", "ProviderSpec"]

