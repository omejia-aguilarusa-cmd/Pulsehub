"""Application entry point for Takeoff Pro desktop app."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env from the project root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv

        candidate = Path(__file__).resolve().parent.parent.parent / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=False)
    except ImportError:
        pass


def configure_logging() -> None:
    """Configure application-wide logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def create_application(argv: Sequence[str] | None = None) -> object:
    """Create and return the QApplication instance.

    Parameters
    ----------
    argv:
        Command-line arguments passed to Qt.  Defaults to ``sys.argv``.

    """
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        sys.exit(f"PyQt6 is required but could not be imported: {exc}")

    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("Takeoff Pro")
    app.setOrganizationName("Takeoff Pro")
    return app


def run(argv: Sequence[str] | None = None) -> int:
    """Start the desktop window and run the event loop.

    Returns the process exit code (0 on clean exit).
    """
    _load_dotenv()
    configure_logging()

    # Suppress Qt WebEngine sandbox warnings on Windows.
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

    app = create_application(argv)

    from takeoff_pro.ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    return app.exec()  # type: ignore[attr-defined,no-any-return]


def main() -> None:
    """Console script entry point."""
    sys.exit(run(sys.argv))
