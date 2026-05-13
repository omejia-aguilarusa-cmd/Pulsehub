"""Undoable commands for takeoff editing."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtGui import QUndoCommand

from takeoff_pro.data.models import Measurement, TakeoffSection


class AddMeasurementCommand(QUndoCommand):
    """Undoable command that adds a measurement to a section."""

    def __init__(
        self,
        section: TakeoffSection,
        measurement: Measurement,
        on_changed: Callable[[], None],
    ) -> None:
        """Initialize the command."""
        super().__init__(f"Add {measurement.kind.value} measurement")
        self._section = section
        self._measurement = measurement
        self._on_changed = on_changed

    def redo(self) -> None:
        """Add the measurement."""
        if not any(existing.id == self._measurement.id for existing in self._section.measurements):
            self._section.measurements.append(self._measurement)
        self._on_changed()

    def undo(self) -> None:
        """Remove the measurement."""
        self._section.measurements = [
            existing
            for existing in self._section.measurements
            if existing.id != self._measurement.id
        ]
        self._on_changed()
