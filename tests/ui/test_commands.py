from __future__ import annotations

from PyQt6.QtGui import QUndoStack

from takeoff_pro.data.models import Measurement, MeasurementKind, Point, TakeoffSection
from takeoff_pro.ui.commands import AddMeasurementCommand


def test_add_measurement_command_redo_and_undo() -> None:
    changed = 0
    section = TakeoffSection(id="section", name="Length", kind=MeasurementKind.LENGTH)
    measurement = Measurement(
        id="measurement",
        name="Length",
        kind=MeasurementKind.LENGTH,
        points=[Point(x=0, y=0), Point(x=1, y=0)],
    )

    def on_changed() -> None:
        nonlocal changed
        changed += 1

    stack = QUndoStack()
    stack.push(AddMeasurementCommand(section, measurement, on_changed))

    assert section.measurements == [measurement]
    stack.undo()
    assert section.measurements == []
    stack.redo()
    assert section.measurements == [measurement]
    assert changed == 3
