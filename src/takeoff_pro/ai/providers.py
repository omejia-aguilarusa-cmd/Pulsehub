"""Swappable AI provider adapters for server-side/local Python calls."""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)

# Model-name substrings that reliably indicate vision/multimodal capability.
_VISION_KEYWORDS: frozenset[str] = frozenset(
    {
        "vision",
        "vl",
        "llava",
        "pixtral",
        "bakllava",
        "cogvlm",
        "internvl",
        "phi-vision",
        "molmo",
        "minicpm-v",
        "qvq",
        "smolvlm",
        "gemma3",
        "magistral",
    }
)


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
        LOGGER.info("AI provider: openai model=%s", self.model)
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
        LOGGER.info("AI provider: anthropic model=%s", self.model)
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            api_key,
            body,
            extra_headers={"anthropic-version": "2023-06-01"},
        )
        return _extract_anthropic_text(data)


@dataclass(frozen=True)
class LmStudioVisionProvider:
    """LM Studio local provider using the OpenAI-compatible API.

    LM Studio requires no external API key.  Set ``AI_BASE_URL`` to the
    address shown in the LM Studio "Local Server" panel (default
    ``http://127.0.0.1:1234/v1``) and optionally set ``AI_TAKEOFF_MODEL``
    to the exact model ID reported by ``GET /v1/models``.  If no model ID
    is set the first model returned by the server is used automatically.
    """

    base_url: str = "http://127.0.0.1:1234/v1"
    api_key: str = "lm-studio-local"
    model: str = ""
    name: str = "lmstudio"

    def is_configured(self) -> bool:
        """Return True — LM Studio needs no external key; base URL is enough."""
        return bool(self.base_url.strip())

    def run_vision_json(self, *, prompt: str, image_paths: list[Path]) -> str:
        """Call LM Studio chat/completions and return the model text as JSON."""
        model = self.model.strip() or self._resolve_model()
        content: list[dict[str, Any]] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{_read_base64(p)}"},
            }
            for p in image_paths
        ]
        content.append({"type": "text", "text": prompt})
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "max_tokens": 6000,
        }
        url = self.base_url.rstrip("/") + "/chat/completions"
        LOGGER.info("AI provider: lmstudio model=%s", model)
        try:
            data = _post_json(url, self.api_key, body)
        except AiProviderError as exc:
            raw = str(exc)
            if any(kw in raw for kw in ("Connection refused", "timed out", "unreachable")):
                msg = (
                    f"LM Studio is not reachable at {self.base_url}. "
                    "Start LM Studio and enable the Local Server."
                )
                raise AiProviderError(msg) from exc
            raise
        return _extract_chat_completions_text(data)

    def _resolve_model(self) -> str:
        """Auto-select the first model loaded in LM Studio."""
        models = _list_lmstudio_models(self.base_url, self.api_key)
        if models is None:
            msg = (
                f"LM Studio is not reachable at {self.base_url}. "
                "Start LM Studio and enable the Local Server."
            )
            raise AiProviderError(msg)
        if not models:
            msg = (
                "LM Studio is reachable, but no model is loaded. "
                "Load a model in LM Studio and try again."
            )
            raise AiProviderError(msg)
        LOGGER.info("LM Studio: auto-selected model=%s", models[0])
        return models[0]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@dataclass
class AiHealthResult:
    """Result of an AI provider health check."""

    configured: bool = False
    provider: str = "none"
    base_url_reachable: bool = False
    models: list[str] = field(default_factory=list)
    takeoff_model: str = ""
    chat_model: str = ""
    supports_vision: str = "unknown"  # "unknown" | "true" | "false"
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "configured": self.configured,
            "provider": self.provider,
            "baseUrlReachable": self.base_url_reachable,
            "models": self.models,
            "takeoffModel": self.takeoff_model,
            "chatModel": self.chat_model,
            "supportsVision": self.supports_vision,
            "warnings": self.warnings,
        }


def check_ai_health() -> AiHealthResult:
    """Return a health-check snapshot for the currently configured AI provider.

    Safe to call at any time; never raises — errors are captured in
    ``AiHealthResult.warnings``.
    """
    result = AiHealthResult()
    provider_name = os.getenv("AI_PROVIDER", "openai").strip().lower()
    result.provider = provider_name
    result.takeoff_model = os.getenv("AI_TAKEOFF_MODEL", "").strip()
    result.chat_model = os.getenv("AI_CHAT_MODEL", "").strip()

    if provider_name == "lmstudio":
        base_url = os.getenv("AI_BASE_URL", "http://127.0.0.1:1234/v1").strip()
        api_key = os.getenv("AI_API_KEY", "lm-studio-local").strip() or "lm-studio-local"
        models = _list_lmstudio_models(base_url, api_key)
        result.base_url_reachable = models is not None
        result.models = models if models is not None else []
        # configured=True when the base URL is reachable; model availability is
        # communicated separately via warnings so the caller can distinguish the
        # two states ("LM Studio unreachable" vs "running but no model loaded").
        result.configured = result.base_url_reachable
        if not result.base_url_reachable:
            result.warnings.append(
                f"LM Studio is not reachable at {base_url}. "
                "Start LM Studio and enable the Local Server."
            )
        elif not result.models:
            result.warnings.append(
                "LM Studio is reachable, but no model is loaded. "
                "Load a model in LM Studio and try again."
            )
        else:
            active = result.takeoff_model or result.models[0]
            result.supports_vision = _detect_vision_support(active)
            if result.supports_vision == "false":
                result.warnings.append(
                    "Text chat is available, but image-based scope detection "
                    "requires a vision model. Load a model with vision support "
                    "(e.g. LLaVA, Qwen-VL, Pixtral)."
                )

    elif provider_name == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        result.configured = bool(key)
        result.base_url_reachable = True
        result.supports_vision = "true"
        if not key:
            result.warnings.append("ANTHROPIC_API_KEY is not set.")

    elif provider_name == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        result.configured = bool(key)
        result.base_url_reachable = True
        result.supports_vision = "true"
        if not key:
            result.warnings.append("OPENAI_API_KEY is not set.")

    else:
        result.warnings.append(
            f"Unknown AI_PROVIDER '{provider_name}'. "
            "Valid values: lmstudio, openai, anthropic."
        )

    return result


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


def provider_from_env() -> AiVisionProvider:
    """Return the configured AI provider selected by environment variables."""
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
    model = os.getenv("AI_TAKEOFF_MODEL", "").strip()

    if provider == "anthropic":
        return AnthropicVisionProvider(model=model or "claude-3-5-sonnet-latest")

    if provider == "openai":
        return OpenAiVisionProvider(model=model or "gpt-4.1-mini")

    if provider == "lmstudio":
        base_url = os.getenv("AI_BASE_URL", "http://127.0.0.1:1234/v1").strip()
        api_key = os.getenv("AI_API_KEY", "lm-studio-local").strip() or "lm-studio-local"
        if not base_url:
            msg = (
                "AI_PROVIDER=lmstudio requires AI_BASE_URL "
                "(e.g. AI_BASE_URL=http://127.0.0.1:1234/v1)."
            )
            raise AiProviderNotConfiguredError(msg)
        LOGGER.info(
            "AI provider selected: lmstudio base_url=%s model=%s",
            base_url,
            model or "(auto)",
        )
        return LmStudioVisionProvider(base_url=base_url, api_key=api_key, model=model)

    msg = f"Unknown AI_PROVIDER '{provider}'. Valid values: lmstudio, openai, anthropic."
    raise AiProviderNotConfiguredError(msg)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _detect_vision_support(model_name: str) -> str:
    """Return 'true', 'false', or 'unknown' based on model name heuristics."""
    lower = model_name.lower()
    if any(kw in lower for kw in _VISION_KEYWORDS):
        return "true"
    # Without stronger signals, don't assume text-only — return unknown so the
    # app doesn't falsely block a vision-capable model with an unfamiliar name.
    return "unknown"


def _list_lmstudio_models(base_url: str, api_key: str) -> list[str] | None:
    """Return model IDs from LM Studio ``GET /models``, or ``None`` if unreachable."""
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data: Any = json.loads(resp.read().decode("utf-8"))
        return [
            str(m["id"])
            for m in data.get("data", [])
            if isinstance(m, dict) and "id" in m
        ]
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
        return None


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
    except urllib.error.HTTPError as exc:
        # Surface the upstream error message from the response body when possible.
        try:
            error_body: Any = json.loads(exc.read().decode("utf-8"))
            upstream = error_body.get("error", {}).get("message", "")
        except Exception:  # exc.read() can fail in many ways
            upstream = ""
        detail = upstream or str(exc)
        msg = f"AI provider request failed: {detail}"
        raise AiProviderError(msg) from exc
    except urllib.error.URLError as exc:
        msg = f"AI provider request failed: {exc}"
        raise AiProviderError(msg) from exc
    value: Any = json.loads(payload)
    if not isinstance(value, dict):
        msg = "AI provider returned a non-object response."
        raise AiProviderError(msg)
    return value


def _extract_chat_completions_text(data: dict[str, Any]) -> str:
    """Extract content from an OpenAI-style chat completions response."""
    for choice in data.get("choices", []):
        if not isinstance(choice, dict):
            continue
        msg_obj = choice.get("message", {})
        if isinstance(msg_obj, dict):
            text = msg_obj.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
    msg = "Chat completions response did not include content."
    raise AiProviderError(msg)


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
