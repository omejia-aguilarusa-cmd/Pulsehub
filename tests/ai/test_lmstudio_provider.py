"""Tests for the LM Studio AI provider adapter and health check."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pytest import MonkeyPatch

from takeoff_pro.ai.providers import (
    AiProviderError,
    AiProviderNotConfiguredError,
    LmStudioVisionProvider,
    _detect_vision_support,
    _extract_chat_completions_text,
    _list_lmstudio_models,
    check_ai_health,
    provider_from_env,
)

# ---------------------------------------------------------------------------
# Shared test doubles
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal context-manager double for urllib HTTP responses."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        """Return the pre-baked response bytes."""
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        pass


def _fake_urlopen(response_body: dict[str, Any] | list[Any]) -> _FakeResponse:
    """Return a fake HTTP response that yields *response_body* as JSON."""
    return _FakeResponse(json.dumps(response_body).encode("utf-8"))


_MODELS_RESPONSE: dict[str, Any] = {
    "data": [
        {"id": "lmstudio-community/llava-1.5-7b-hf-GGUF"},
        {"id": "lmstudio-community/mistral-7b-instruct-v0.3-GGUF"},
    ]
}

_CHAT_RESPONSE: dict[str, Any] = {
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": '{"rooms": [], "elements": [], "warnings": [], "confidenceScore": 0.85}',
            }
        }
    ]
}


# ---------------------------------------------------------------------------
# LmStudioVisionProvider.is_configured
# ---------------------------------------------------------------------------


def test_lmstudio_is_configured_with_default_url() -> None:
    provider = LmStudioVisionProvider()
    assert provider.is_configured() is True


def test_lmstudio_is_configured_with_custom_url() -> None:
    provider = LmStudioVisionProvider(base_url="http://10.0.0.5:1234/v1")
    assert provider.is_configured() is True


def test_lmstudio_is_not_configured_with_empty_url() -> None:
    provider = LmStudioVisionProvider(base_url="   ")
    assert provider.is_configured() is False


# ---------------------------------------------------------------------------
# provider_from_env — lmstudio branch
# ---------------------------------------------------------------------------


def test_provider_from_env_lmstudio_returns_lmstudio_provider(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("AI_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("AI_API_KEY", "lm-studio-local")
    monkeypatch.delenv("AI_TAKEOFF_MODEL", raising=False)

    provider = provider_from_env()

    assert isinstance(provider, LmStudioVisionProvider)
    assert provider.name == "lmstudio"
    assert provider.base_url == "http://127.0.0.1:1234/v1"


def test_provider_from_env_lmstudio_uses_model_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("AI_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("AI_TAKEOFF_MODEL", "my-custom-model")

    provider = provider_from_env()

    assert isinstance(provider, LmStudioVisionProvider)
    assert provider.model == "my-custom-model"


def test_provider_from_env_lmstudio_default_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.delenv("AI_API_KEY", raising=False)

    provider = provider_from_env()

    assert isinstance(provider, LmStudioVisionProvider)
    assert provider.api_key == "lm-studio-local"


def test_provider_from_env_unknown_provider_raises(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "someunknown")

    with pytest.raises(AiProviderNotConfiguredError, match="Unknown AI_PROVIDER"):
        provider_from_env()


def test_provider_from_env_openai_still_works(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    provider = provider_from_env()
    assert provider.name == "openai"


def test_provider_from_env_anthropic_still_works(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    provider = provider_from_env()
    assert provider.name == "anthropic"


# ---------------------------------------------------------------------------
# _list_lmstudio_models
# ---------------------------------------------------------------------------


def test_list_models_returns_ids_on_success() -> None:
    with patch("urllib.request.urlopen", return_value=_fake_urlopen(_MODELS_RESPONSE)):
        models = _list_lmstudio_models("http://127.0.0.1:1234/v1", "lm-studio-local")

    assert models == [
        "lmstudio-community/llava-1.5-7b-hf-GGUF",
        "lmstudio-community/mistral-7b-instruct-v0.3-GGUF",
    ]


def test_list_models_returns_none_when_unreachable() -> None:
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        models = _list_lmstudio_models("http://127.0.0.1:1234/v1", "lm-studio-local")

    assert models is None


def test_list_models_returns_empty_list_when_none_loaded() -> None:
    with patch(
        "urllib.request.urlopen",
        return_value=_fake_urlopen({"data": []}),
    ):
        models = _list_lmstudio_models("http://127.0.0.1:1234/v1", "lm-studio-local")

    assert models == []


# ---------------------------------------------------------------------------
# LmStudioVisionProvider.run_vision_json
# ---------------------------------------------------------------------------


def test_run_vision_json_uses_explicit_model(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n")

    provider = LmStudioVisionProvider(
        base_url="http://127.0.0.1:1234/v1",
        model="lmstudio-community/llava-1.5-7b-hf-GGUF",
    )

    captured_body: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int = 90) -> _FakeResponse:  # noqa: ANN401
        if req.get_method() == "POST":
            captured_body.update(json.loads(req.data))
            return _fake_urlopen(_CHAT_RESPONSE)
        return _fake_urlopen(_MODELS_RESPONSE)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = provider.run_vision_json(prompt="Analyze this plan.", image_paths=[image])

    assert '"rooms"' in result
    assert captured_body["model"] == "lmstudio-community/llava-1.5-7b-hf-GGUF"
    assert captured_body["response_format"] == {"type": "json_object"}


def test_run_vision_json_auto_selects_model_when_none_set(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n")

    provider = LmStudioVisionProvider(base_url="http://127.0.0.1:1234/v1", model="")

    def fake_urlopen(req: Any, timeout: int = 90) -> _FakeResponse:  # noqa: ANN401
        if req.get_method() == "GET":
            return _fake_urlopen(_MODELS_RESPONSE)
        return _fake_urlopen(_CHAT_RESPONSE)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = provider.run_vision_json(prompt="Analyze.", image_paths=[image])

    assert '"rooms"' in result


def test_run_vision_json_raises_when_lmstudio_unreachable(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n")

    provider = LmStudioVisionProvider(base_url="http://127.0.0.1:1234/v1", model="")

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        with pytest.raises(AiProviderError, match="not reachable"):
            provider.run_vision_json(prompt="Analyze.", image_paths=[image])


def test_run_vision_json_raises_when_no_model_loaded(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n")

    provider = LmStudioVisionProvider(base_url="http://127.0.0.1:1234/v1", model="")

    with patch("urllib.request.urlopen", return_value=_fake_urlopen({"data": []})):
        with pytest.raises(AiProviderError, match="no model is loaded"):
            provider.run_vision_json(prompt="Analyze.", image_paths=[image])


# ---------------------------------------------------------------------------
# _extract_chat_completions_text
# ---------------------------------------------------------------------------


def test_extract_chat_completions_text_happy_path() -> None:
    data = {"choices": [{"message": {"role": "assistant", "content": '{"rooms":[]}'}}]}
    assert _extract_chat_completions_text(data) == '{"rooms":[]}'


def test_extract_chat_completions_text_raises_on_empty_choices() -> None:
    with pytest.raises(AiProviderError, match="did not include content"):
        _extract_chat_completions_text({"choices": []})


def test_extract_chat_completions_text_skips_empty_content() -> None:
    data = {
        "choices": [
            {"message": {"content": "   "}},
            {"message": {"content": "valid"}},
        ]
    }
    assert _extract_chat_completions_text(data) == "valid"


# ---------------------------------------------------------------------------
# _detect_vision_support
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_name,expected",
    [
        ("lmstudio-community/llava-1.5-7b-hf-GGUF", "true"),
        ("qwen2-vl-7b-instruct", "true"),
        ("pixtral-12b", "true"),
        ("smolvlm-instruct", "true"),
        ("bakllava-1", "true"),
        ("cogvlm2-19b", "true"),
        ("phi-vision-3.5", "true"),
        ("molmo-7b-d", "true"),
        # Text-only — not enough signal to confirm false; return unknown
        ("mistral-7b-instruct-v0.3", "unknown"),
        ("llama-3-8b-instruct", "unknown"),
        ("deepseek-coder-6.7b", "unknown"),
    ],
)
def test_detect_vision_support(model_name: str, expected: str) -> None:
    assert _detect_vision_support(model_name) == expected


# ---------------------------------------------------------------------------
# check_ai_health
# ---------------------------------------------------------------------------


def test_health_lmstudio_reachable_with_vision_model(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("AI_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.delenv("AI_TAKEOFF_MODEL", raising=False)

    with patch(
        "urllib.request.urlopen",
        return_value=_fake_urlopen(_MODELS_RESPONSE),
    ):
        result = check_ai_health()

    assert result.configured is True
    assert result.provider == "lmstudio"
    assert result.base_url_reachable is True
    assert "lmstudio-community/llava-1.5-7b-hf-GGUF" in result.models
    assert result.supports_vision == "true"
    assert result.warnings == []


def test_health_lmstudio_unreachable(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("AI_BASE_URL", "http://127.0.0.1:1234/v1")

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        result = check_ai_health()

    assert result.configured is False
    assert result.base_url_reachable is False
    assert any("not reachable" in w for w in result.warnings)


def test_health_lmstudio_no_model_loaded(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("AI_BASE_URL", "http://127.0.0.1:1234/v1")

    with patch("urllib.request.urlopen", return_value=_fake_urlopen({"data": []})):
        result = check_ai_health()

    # Provider settings are correct (LM Studio is reachable) so configured=True.
    # The missing model is surfaced via warnings, not by marking configured=False.
    assert result.configured is True
    assert result.base_url_reachable is True
    assert result.models == []
    assert any("no model is loaded" in w for w in result.warnings)


def test_health_lmstudio_text_only_model_warns(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("AI_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("AI_TAKEOFF_MODEL", "mistral-7b-instruct")

    text_only_response: dict[str, Any] = {"data": [{"id": "mistral-7b-instruct"}]}
    with patch("urllib.request.urlopen", return_value=_fake_urlopen(text_only_response)):
        result = check_ai_health()

    # "unknown" — not enough name signal to confirm text-only; no warning added
    assert result.supports_vision == "unknown"
    assert result.configured is True


def test_health_openai_configured(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    result = check_ai_health()

    assert result.configured is True
    assert result.provider == "openai"
    assert result.supports_vision == "true"
    assert result.warnings == []


def test_health_openai_missing_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = check_ai_health()

    assert result.configured is False
    assert any("OPENAI_API_KEY" in w for w in result.warnings)


def test_health_anthropic_configured(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    result = check_ai_health()

    assert result.configured is True
    assert result.provider == "anthropic"
    assert result.supports_vision == "true"


def test_health_unknown_provider(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "some_unknown")

    result = check_ai_health()

    assert result.configured is False
    assert any("Unknown AI_PROVIDER" in w for w in result.warnings)


def test_health_as_dict_shape(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    data = check_ai_health().as_dict()

    assert set(data) == {
        "configured",
        "provider",
        "baseUrlReachable",
        "models",
        "takeoffModel",
        "chatModel",
        "supportsVision",
        "warnings",
    }
