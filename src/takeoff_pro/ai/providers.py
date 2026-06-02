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
        "gemma4",
        "gemma-4",
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
            if "404" in raw:
                msg = (
                    f"Wrong endpoint: {url} returned 404. "
                    "Ensure AI_BASE_URL ends with /v1 (e.g. http://127.0.0.1:1234/v1)."
                )
                raise AiProviderError(msg) from exc
            if "503" in raw or "model not loaded" in raw.lower():
                msg = (
                    f"LM Studio returned 503 — model '{model}' may not be loaded. "
                    "Load the model in LM Studio and try again."
                )
                raise AiProviderError(msg) from exc
            if "422" in raw or "unsupported" in raw.lower():
                msg = (
                    f"LM Studio rejected the request ({raw}). "
                    "Check that the model supports vision/multimodal input."
                )
                raise AiProviderError(msg) from exc
            raise
        try:
            return _extract_chat_completions_text(data)
        except AiProviderError as exc:
            msg = (
                f"Response parse failed: {exc}. "
                "The model may have returned non-JSON or an unexpected structure."
            )
            raise AiProviderError(msg) from exc

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
    """Return a cascade health-check snapshot.

    Always reports the fixed priority order:
      1. OpenAI Codex (primary — mandatory)
      2. DeepSeek     (backup — only if OpenAI fails)
      3. LM Studio    (last resort)

    Safe to call at any time; never raises.
    """
    result = AiHealthResult()
    result.provider = "cascade: deepseek → openai → lmstudio"
    result.takeoff_model = os.getenv("AI_TAKEOFF_MODEL", "").strip()
    result.chat_model = os.getenv("AI_CHAT_MODEL", "").strip()

    # --- DeepSeek (primary) -------------------------------------------------
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if deepseek_key:
        result.configured = True
        result.base_url_reachable = True
        result.supports_vision = "false"
        result.models.append("deepseek:deepseek-chat (primary — ready)")
        result.warnings.append(
            "DeepSeek does not support image input on its public API.  "
            "PDF text extraction is used in place of page images."
        )
    else:
        result.warnings.append(
            "DEEPSEEK_API_KEY is not set — DeepSeek is the primary provider.  "
            "Add it to your .env file."
        )

    # --- OpenAI (secondary) -------------------------------------------------
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key:
        result.configured = True
        result.supports_vision = "true"
        result.models.append("openai:gpt-4.1-mini (secondary — ready)")
    else:
        result.warnings.append(
            "OPENAI_API_KEY is not set — OpenAI is inactive.  "
            "Add it to your .env file to enable it as a secondary provider."
        )

    # --- LM Studio (last resort) --------------------------------------------
    base_url = os.getenv("AI_BASE_URL", "http://127.0.0.1:1234/v1").strip()
    lm_api_key = os.getenv("AI_API_KEY", "lm-studio-local").strip() or "lm-studio-local"
    lm_models = _list_lmstudio_models(base_url, lm_api_key)
    if lm_models is not None:
        result.base_url_reachable = True
        if lm_models:
            result.configured = True
            result.models.append(f"lmstudio:{lm_models[0]} (last resort — ready)")
        else:
            result.warnings.append(
                "LM Studio is reachable but no model is loaded — "
                "load a model in LM Studio if you want local fallback."
            )
    else:
        result.warnings.append(
            f"LM Studio is not reachable at {base_url} — "
            "this is normal if you do not run LM Studio locally."
        )

    if not result.configured:
        result.warnings.append(
            "No AI provider is configured.  "
            "Set OPENAI_API_KEY (primary) and/or DEEPSEEK_API_KEY (backup) in your .env file."
        )

    return result


# ---------------------------------------------------------------------------
# DeepSeek provider (backup when OpenAI / Codex is unavailable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeepSeekProvider:
    """DeepSeek API adapter — OpenAI-compatible, used as automatic backup.

    DeepSeek's public API (``api.deepseek.com``) is OpenAI-compatible and
    accepts the same ``/v1/chat/completions`` format.  It does not currently
    support image/vision input; when image paths are supplied they are ignored
    and only the text prompt is sent.  Set ``AI_PROVIDER=deepseek`` and
    ``DEEPSEEK_API_KEY`` (or ``AI_API_KEY``) in your ``.env`` file.
    """

    api_key: str | None = None
    model: str = "deepseek-chat"
    name: str = "deepseek"

    def is_configured(self) -> bool:
        """Return whether a DeepSeek API key is available."""
        return bool(self.api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("AI_API_KEY"))

    def run_vision_json(self, *, prompt: str, image_paths: list[Path]) -> str:  # noqa: ARG002
        """Call DeepSeek chat completions and return JSON text.

        Image paths are accepted for interface compatibility but not forwarded
        because DeepSeek does not currently support image input on its public
        API.  The text prompt is sent alone; callers should include OCR or
        page-text extracts in the prompt when image analysis is required.
        """
        api_key = self.api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("AI_API_KEY")
        if not api_key:
            raise AiProviderNotConfiguredError(
                "DeepSeek API key is not configured.  Set DEEPSEEK_API_KEY in your .env file "
                "or enter the key in Settings → AI provider → API key override."
            )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": 6000,
        }
        url = "https://api.deepseek.com/chat/completions"
        LOGGER.info("AI provider: deepseek model=%s", self.model)
        try:
            data = _post_json(url, api_key, body)
        except AiProviderError as exc:
            raw = str(exc)
            if "401" in raw:
                raise AiProviderError(
                    "DeepSeek API key rejected (HTTP 401).  Verify DEEPSEEK_API_KEY in your "
                    ".env file or update it in Settings → AI provider."
                ) from exc
            if "402" in raw:
                raise AiProviderError(
                    "DeepSeek account balance is insufficient (HTTP 402).  "
                    "Top up at platform.deepseek.com."
                ) from exc
            if "429" in raw:
                raise AiProviderError(
                    "DeepSeek rate limit reached (HTTP 429).  "
                    "Wait before retrying."
                ) from exc
            raise
        return _extract_chat_completions_text(data)


# ---------------------------------------------------------------------------
# OAuth provider placeholder
# ---------------------------------------------------------------------------

# NOTE: OpenAI Codex OAuth / ChatGPT sign-in is NOT supported by the OpenAI
# API for desktop (non-web) applications.  The OpenAI API only supports API
# key authentication.  "ChatGPT sign-in" OAuth is specific to ChatGPT plugin
# web flows and cannot be used to call the OpenAI Responses/Chat Completions
# API from a PyQt6 desktop runtime.
#
# This placeholder class documents the intended interface so that if OpenAI
# ever provides an OAuth-compatible path for desktop runtimes, the concrete
# implementation can be added here without changing any call sites.


@dataclass(frozen=True)
class OpenAiOAuthProvider:
    """Placeholder for future OpenAI OAuth / ChatGPT sign-in authentication.

    This class documents the intended interface.  It is *not yet functional*
    because the OpenAI API does not support OAuth-based authentication for
    desktop applications.  Set ``AI_PROVIDER=openai`` and provide
    ``OPENAI_API_KEY`` as an environment variable until an OAuth path becomes
    available.
    """

    model: str = "gpt-4o"
    name: str = "openai_oauth"

    def is_configured(self) -> bool:
        """Return False — OAuth is not yet available for this runtime."""
        return False

    def run_vision_json(self, *, prompt: str, image_paths: list[Path]) -> str:
        """Raise an informative error — OAuth is not yet implemented."""
        msg = (
            "OpenAI OAuth / ChatGPT sign-in is not supported for desktop "
            "applications.  Set AI_PROVIDER=openai and configure "
            "OPENAI_API_KEY in your .env file to use the OpenAI API."
        )
        raise AiProviderNotConfiguredError(msg)


# ---------------------------------------------------------------------------
# Cascading provider (OpenAI → DeepSeek → LM Studio)
# ---------------------------------------------------------------------------


@dataclass
class CascadingProvider:
    """Tries providers in priority order; falls back automatically on failure.

    Priority is fixed:
      1. OpenAI Codex (primary — mandatory)
      2. DeepSeek      (automatic backup — only if OpenAI fails)
      3. LM Studio     (last resort — local, no key required)

    A provider is skipped at attempt time only when it explicitly has no
    credential (``is_configured()`` returns False).  An API error from a
    configured provider causes fallback to the next tier so transient
    failures or rate limits do not break the run.
    """

    providers: list[AiVisionProvider]

    @property
    def name(self) -> str:
        """Return the name of the first ready provider."""
        for p in self.providers:
            if p.is_configured():
                return p.name
        return "none"

    @property
    def model(self) -> str:
        """Return the model of the first ready provider."""
        for p in self.providers:
            if p.is_configured():
                return p.model
        return ""

    def is_configured(self) -> bool:
        """Return True when at least one provider is ready."""
        return any(p.is_configured() for p in self.providers)

    def run_vision_json(self, *, prompt: str, image_paths: list[Path]) -> str:
        """Try each provider in order; fall back on any failure."""
        last_error: Exception | None = None
        for provider in self.providers:
            if not provider.is_configured():
                LOGGER.debug("Cascade: skipping %s — not configured.", provider.name)
                continue
            try:
                LOGGER.info("Cascade: attempting provider=%s", provider.name)
                result = provider.run_vision_json(prompt=prompt, image_paths=image_paths)
                LOGGER.info("Cascade: succeeded with provider=%s", provider.name)
                return result
            except AiProviderNotConfiguredError as exc:
                LOGGER.warning("Cascade: %s not configured — %s", provider.name, exc)
                last_error = exc
            except AiProviderError as exc:
                LOGGER.warning(
                    "Cascade: %s failed (%s) — falling back to next provider.",
                    provider.name,
                    exc,
                )
                last_error = exc
        if last_error is not None:
            raise AiProviderError(
                f"All configured providers failed.  Last error: {last_error}"
            ) from last_error
        raise AiProviderNotConfiguredError(
            "No AI provider is configured.  "
            "Set OPENAI_API_KEY in your .env file (primary) or "
            "DEEPSEEK_API_KEY as a backup.  "
            "LM Studio will be used as a last resort when running locally."
        )


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


def provider_from_env() -> AiVisionProvider:
    """Return a CascadingProvider with DeepSeek as the primary provider.

    Priority:
      1. DeepSeek   — primary.  Requires DEEPSEEK_API_KEY.
      2. OpenAI     — secondary.  Activates automatically when OPENAI_API_KEY is added.
      3. LM Studio  — last resort.  Local, no key required.
    """
    model = os.getenv("AI_TAKEOFF_MODEL", "").strip()

    # --- 1. DeepSeek (primary) ----------------------------------------------
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    deepseek_provider: AiVisionProvider = DeepSeekProvider(
        api_key=deepseek_key or None,
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat",
    )

    # --- 2. OpenAI (secondary — activates when key is added) ---------------
    openai_provider: AiVisionProvider = OpenAiVisionProvider(
        model=model or "gpt-4.1-mini"
    )

    # --- 3. LM Studio (last resort — local) --------------------------------
    lm_base_url = os.getenv("AI_BASE_URL", "http://127.0.0.1:1234/v1").strip()
    lm_api_key = os.getenv("AI_API_KEY", "lm-studio-local").strip() or "lm-studio-local"
    lmstudio_provider: AiVisionProvider = LmStudioVisionProvider(
        base_url=lm_base_url,
        api_key=lm_api_key,
        model=model,
    )

    cascade = CascadingProvider(
        providers=[deepseek_provider, openai_provider, lmstudio_provider]
    )
    LOGGER.info(
        "AI cascade built: deepseek(configured=%s) → openai(configured=%s) → lmstudio",
        deepseek_provider.is_configured(),
        openai_provider.is_configured(),
    )
    return cascade


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
    try:
        value: Any = json.loads(payload)
    except json.JSONDecodeError as exc:
        snippet = payload[:200]
        msg = f"AI provider returned non-JSON response: {snippet!r}"
        raise AiProviderError(msg) from exc
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
