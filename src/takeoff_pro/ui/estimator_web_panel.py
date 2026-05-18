"""Embedded web workspace host for the production Takeoff UI."""

from __future__ import annotations

import logging
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
            self._view.setContent(
                _UI_HTML.read_bytes(),
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
