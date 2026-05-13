"""Application bootstrap for Takeoff Pro."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from PyQt6.QtWidgets import QApplication

from takeoff_pro.ui.main_window import MainWindow

LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure the application logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create or return the active Qt application."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        if isinstance(existing_app, QApplication):
            existing_app.setApplicationName("Takeoff Pro")
            existing_app.setOrganizationName("Takeoff Pro Contributors")
            return existing_app
        msg = "An incompatible Qt application instance is already running."
        raise RuntimeError(msg)

    args = list(argv) if argv is not None else sys.argv
    app = QApplication(args)
    app.setApplicationName("Takeoff Pro")
    app.setOrganizationName("Takeoff Pro Contributors")
    return app


def run(argv: Sequence[str] | None = None) -> int:
    """Run the desktop application event loop."""
    configure_logging()
    LOGGER.info("Starting Takeoff Pro")
    app = create_application(argv)
    window = MainWindow()
    window.show()
    return app.exec()


def main() -> None:
    """Run Takeoff Pro as a console script."""
    raise SystemExit(run())
