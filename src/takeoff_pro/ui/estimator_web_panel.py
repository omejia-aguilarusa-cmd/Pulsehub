"""Embedded web workspace host for the production Takeoff UI."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except ImportError:  # pragma: no cover - import guard for systems without WebEngine
    _HAS_WEBENGINE = False

LOGGER = logging.getLogger(__name__)

if getattr(sys, "frozen", False):
    _ASSETS_DIR = Path(getattr(sys, "_MEIPASS", "")) / "takeoff_pro" / "ui" / "assets"
else:
    _ASSETS_DIR = Path(__file__).parent / "assets"

_UI_HTML = _ASSETS_DIR / "estimator_ui.html"


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(value or "")
    except (ValueError, TypeError):
        return default


def _resolve_api_key(provider: str) -> str:
    """Return the correct API key for the given provider name.

    Provider-specific env vars take priority so the frontend receives the
    right credential without requiring the user to duplicate it into AI_API_KEY.
    """
    if provider == "openai":
        return (
            os.getenv("OPENAI_API_KEY", "").strip()
            or os.getenv("AI_API_KEY", "").strip()
        )
    if provider == "anthropic":
        return (
            os.getenv("ANTHROPIC_API_KEY", "").strip()
            or os.getenv("AI_API_KEY", "").strip()
        )
    if provider == "deepseek":
        return (
            os.getenv("DEEPSEEK_API_KEY", "").strip()
            or os.getenv("AI_API_KEY", "").strip()
        )
    # lmstudio and unknown providers
    return os.getenv("AI_API_KEY", "lm-studio-local").strip() or "lm-studio-local"


def _build_ai_config_script() -> str:
    """Return a <script> tag injecting AI provider config from environment variables.

    OAuth / ChatGPT sign-in is not supported by the OpenAI API for desktop
    applications.  The OpenAI API requires an API key.  This limitation is
    documented here so the abstraction can be upgraded if OpenAI adds an
    OAuth-compatible path for desktop runtimes in the future.
    """
    provider = os.getenv("AI_PROVIDER", "").strip()
    deepseek_key_configured = bool(
        os.getenv("DEEPSEEK_API_KEY", "").strip()
        or (provider == "deepseek" and os.getenv("AI_API_KEY", "").strip())
    )
    # baseUrl must point to the correct endpoint for the active provider.
    # For DeepSeek, always use the DeepSeek API regardless of AI_BASE_URL.
    deepseek_base = "https://api.deepseek.com/v1"
    base_url = (
        deepseek_base
        if provider == "deepseek"
        else os.getenv("AI_BASE_URL", "http://127.0.0.1:1234/v1").strip()
    )
    config = {
        "provider": provider,
        "baseUrl": base_url,
        "apiKey": _resolve_api_key(provider),
        "chatModel": os.getenv("AI_CHAT_MODEL", "").strip(),
        "takeoffModel": os.getenv("AI_TAKEOFF_MODEL", "").strip(),
        "supportsVision": os.getenv("AI_SUPPORTS_VISION", "").strip().lower()
        in ("true", "1", "yes"),
        "maxTokens": _safe_int(os.getenv("AI_MAX_TOKENS"), 4096),
        # Provider cascade: OpenAI → DeepSeek (backup) → LM Studio
        "deepseekKeyConfigured": deepseek_key_configured,
        "deepseekBaseUrl": "https://api.deepseek.com/v1",
        "deepseekModel": os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
        # OAuth limitation notice surfaced in the settings UI.
        "oauthAvailable": False,
        "oauthNote": (
            "OpenAI Codex OAuth / ChatGPT sign-in is not available for "
            "desktop applications via the OpenAI API. An API key is required. "
            "Configure OPENAI_API_KEY in your .env file. "
            "DeepSeek is available as an automatic backup — configure "
            "DEEPSEEK_API_KEY in your .env file or enter it in Settings."
        ),
    }
    return f"<script>window.TAKEOFF_AI_CONFIG = {json.dumps(config)};</script>"


class EstimatorWebPanel(QWidget):
    """Full-height web workspace without any duplicated native shell UI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the embedded web workspace."""
        super().__init__(parent)
        self._view: QWebEngineView | None = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        load_error = self._load_error()
        if load_error:
            self._show_fallback(layout, load_error)
            return

        try:
            self._view = QWebEngineView(self)
            settings = self._view.settings()
            if settings is None:
                self._show_fallback(layout, "Workspace browser settings are unavailable.")
                return
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                True,
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                True,
            )
            html = _UI_HTML.read_bytes().decode("utf-8")
            html = html.replace("<head>", f"<head>{_build_ai_config_script()}", 1)
            self._view.setContent(
                html.encode("utf-8"),
                "text/html; charset=utf-8",
                QUrl.fromLocalFile(str(_UI_HTML)),
            )
            layout.addWidget(self._view)
        except Exception as exc:
            LOGGER.exception("Could not load workspace UI")
            self._show_fallback(layout, str(exc))

    def _load_error(self) -> str | None:
        """Return a user-facing setup error before creating the browser view."""
        if not _HAS_WEBENGINE:
            return "PyQt6-WebEngine is not available."
        if not _UI_HTML.exists():
            return f"Workspace HTML not found: {_UI_HTML}"
        return None

    def _show_fallback(self, layout: QVBoxLayout, detail: str) -> None:
        """Render a readable fallback when the embedded workspace cannot load."""
        fallback = QLabel(
            f"The Takeoff workspace could not be loaded. {detail}",
            self,
        )
        fallback.setWordWrap(True)
        layout.addWidget(fallback)
