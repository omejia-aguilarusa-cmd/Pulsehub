from __future__ import annotations

from pytestqt.qtbot import QtBot

from takeoff_pro.estimate import Assembly, AssemblyComponent, EstimateItem
from takeoff_pro.ui.estimate_dialog import EstimateEditorDialog
from takeoff_pro.ui.scale_dialog import ScaleCalibrationDialog


def test_estimate_editor_returns_items_and_assemblies(qtbot: QtBot) -> None:
    item = EstimateItem(item_id="PAINT", description="Paint", unit="GAL", unit_cost=35)
    assembly = Assembly(
        assembly_id="WALL",
        name="Wall",
        takeoff_unit="SF",
        components=[AssemblyComponent(item_id="PAINT", quantity_per_takeoff_unit=0.04)],
    )
    dialog = EstimateEditorDialog([item], [assembly])
    qtbot.addWidget(dialog)

    assert dialog.items() == [item]
    assert dialog.assemblies() == [assembly]

    dialog._add_item_row()
    dialog._add_assembly_row()

    assert len(dialog.items()) == 2
    assert len(dialog.assemblies()) == 1


def test_scale_dialog_returns_default_distance_and_unit(qtbot: QtBot) -> None:
    dialog = ScaleCalibrationDialog()
    qtbot.addWidget(dialog)

    assert dialog.distance() == 1.0
    assert dialog.unit() == "FT"
