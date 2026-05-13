from __future__ import annotations

from collections.abc import Sequence

import pytest
from pytestqt.qtbot import QtBot

from takeoff_pro import __version__
from takeoff_pro import app as app_module
from takeoff_pro.app import configure_logging, create_application
from takeoff_pro.ui.main_window import MainWindow


class _FakeApplication:
    """Test double for the Qt application event loop."""

    def exec(self) -> int:
        """Return a deterministic process status."""
        return 0


class _FakeWindow:
    """Test double for the main window."""

    def __init__(self) -> None:
        """Track whether the window was shown."""
        self.was_shown = False

    def show(self) -> None:
        """Record that startup requested a visible window."""
        self.was_shown = True


def test_phase0_placeholder_opens_main_window(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_logging()
    application = create_application([])
    window = MainWindow()
    qtbot.addWidget(window)

    assert __version__ == "0.1.0"
    assert application.applicationName() == "Takeoff Pro"
    assert window.windowTitle() == "Takeoff Pro"
    assert window.minimumWidth() == 900

    created_windows: list[_FakeWindow] = []

    def fake_create_application(argv: Sequence[str] | None = None) -> _FakeApplication:
        """Return a fake application for startup testing."""
        return _FakeApplication()

    def fake_main_window() -> _FakeWindow:
        """Return a fake window for startup testing."""
        created_window = _FakeWindow()
        created_windows.append(created_window)
        return created_window

    monkeypatch.setattr(app_module, "create_application", fake_create_application)
    monkeypatch.setattr(app_module, "MainWindow", fake_main_window)

    assert app_module.run(["takeoff-pro"]) == 0
    assert created_windows[0].was_shown

    def fake_run(argv: Sequence[str] | None = None) -> int:
        """Return a fake process status for console entry testing."""
        return 7

    monkeypatch.setattr(app_module, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        app_module.main()

    assert exc_info.value.code == 7
