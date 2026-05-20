"""Swappable AI provider adapters for server-side/local Python calls."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class AiProviderError(RuntimeError):
    """Raised when an AI provider call fails."""


class AiProviderNotConfiguredError(AiProviderError):
    """Raised when no configured provider is available."""

    def __init__(self, detail: str = "AI provider API key is not configured.") -> None:
        """Initialize with a safe user-facing detail."""
        super().__init__(detail)


class AiVisionProvider(Protocol):
    """Protocol implemented by vision-capable takeoff providers."""

    @property
    def name(self) -> str:
        """Return the provider name."""

    @property
    def model(self) -> str:
        """Return the model name."""

    def is_configured(self) -> bool:
        """Return whether required credentials are available."""

    def run_vision_json(self, *, prompt: str, image_paths: list[Path]) -> str:
        """Return strict JSON text for a prompt and page images."""


@dataclass(frozen=True)
class OpenAiVisionProvider:
    """OpenAI vision adapter using environment variables."""

    api_key: str | None = None
    model: str = "gpt-4.1-mini"
    name: str = "openai"

    def is_configured(self) -> bool:
        """Return whether the OpenAI API key is configured."""
        return bool(self.api_key or os.getenv("OPENAI_API_KEY"))

    def run_vision_json(self, *, prompt: str, image_paths: list[Path]) -> str:
        """Call OpenAI Responses API and return model text."""
        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise AiProviderNotConfiguredError()
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        content.extend(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{_read_base64(path)}",
            }
            for path in image_paths
        )
        body: dict[str, Any] = {
            "model": self.model,
            "input": [{"role": "user", "content": content}],
            "text": {"format": {"type": "json_object"}},
        }
        data = _post_json("https://api.openai.com/v1/responses", api_key, body)
        return _extract_openai_text(data)


@dataclass(frozen=True)
class AnthropicVisionProvider:
    """Anthropic vision adapter using environment variables."""

    api_key: str | None = None
    model: str = "claude-3-5-sonnet-latest"
    name: str = "anthropic"

    def is_configured(self) -> bool:
        """Return whether the Anthropic API key is configured."""
        return bool(self.api_key or os.getenv("ANTHROPIC_API_KEY"))

    def run_vision_json(self, *, prompt: str, image_paths: list[Path]) -> str:
        """Call Anthropic Messages API and return model text."""
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AiProviderNotConfiguredError()
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": _read_base64(path),
                },
            }
            for path in image_paths
        ]
        content.append({"type": "text", "text": prompt})
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 6000,
            "messages": [{"role": "user", "content": content}],
        }
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            api_key,
            body,
            extra_headers={"anthropic-version": "2023-06-01"},
        )
        return _extract_anthropic_text(data)


def provider_from_env() -> AiVisionProvider:
    """Return the configured AI provider selected by environment variables."""
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
    model = os.getenv("AI_TAKEOFF_MODEL", "").strip()
    if provider == "anthropic":
        return AnthropicVisionProvider(model=model or "claude-3-5-sonnet-latest")
    if provider == "openai":
        return OpenAiVisionProvider(model=model or "gpt-4.1-mini")
    raise AiProviderNotConfiguredError()


def _read_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _post_json(
    url: str,
    api_key: str,
    body: dict[str, Any],
    *,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {api_key}",
        **(extra_headers or {}),
    }
    if "anthropic.com" in url:
        headers.pop("authorization", None)
        headers["x-api-key"] = api_key
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        msg = f"AI provider request failed: {exc}"
        raise AiProviderError(msg) from exc
    value = json.loads(payload)
    if not isinstance(value, dict):
        msg = "AI provider returned a non-object response."
        raise AiProviderError(msg)
    return value


def _extract_openai_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text
    for output in data.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return str(content["text"])
    msg = "OpenAI response did not include output text."
    raise AiProviderError(msg)


def _extract_anthropic_text(data: dict[str, Any]) -> str:
    for item in data.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                return text
    msg = "Anthropic response did not include text content."
    raise AiProviderError(msg)
