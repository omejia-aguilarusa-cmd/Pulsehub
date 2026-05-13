"""Estimating item and assembly editor dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from takeoff_pro.estimate import Assembly, AssemblyComponent, EstimateItem


class EstimateEditorDialog(QDialog):
    """Dialog for editing CSV-style items and simple assemblies."""

    def __init__(
        self,
        items: list[EstimateItem],
        assemblies: list[Assembly],
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the editor with existing estimating data."""
        super().__init__(parent)
        self.setWindowTitle("Estimating Library")
        self._items_table = QTableWidget(self)
        self._items_table.setColumnCount(4)
        self._items_table.setHorizontalHeaderLabels(["Item ID", "Description", "Unit", "Unit Cost"])
        self._assemblies_table = QTableWidget(self)
        self._assemblies_table.setColumnCount(5)
        self._assemblies_table.setHorizontalHeaderLabels(
            ["Assembly ID", "Name", "Takeoff Unit", "Item ID", "Qty / Unit"]
        )

        self._load_items(items)
        self._load_assemblies(assemblies)

        add_item_button = QPushButton("Add Item", self)
        add_item_button.clicked.connect(self._add_item_row)
        add_assembly_button = QPushButton("Add Assembly", self)
        add_assembly_button.clicked.connect(self._add_assembly_row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._items_table)
        layout.addWidget(add_item_button)
        layout.addWidget(self._assemblies_table)
        layout.addWidget(add_assembly_button)
        layout.addWidget(buttons)

    def items(self) -> list[EstimateItem]:
        """Return edited estimate items."""
        items: list[EstimateItem] = []
        for row in range(self._items_table.rowCount()):
            item_id = _cell_text(self._items_table, row, 0)
            if not item_id:
                continue
            items.append(
                EstimateItem(
                    item_id=item_id,
                    description=_cell_text(self._items_table, row, 1),
                    unit=_cell_text(self._items_table, row, 2) or "EA",
                    unit_cost=float(_cell_text(self._items_table, row, 3) or "0"),
                )
            )
        return items

    def assemblies(self) -> list[Assembly]:
        """Return edited assemblies."""
        assemblies: list[Assembly] = []
        for row in range(self._assemblies_table.rowCount()):
            assembly_id = _cell_text(self._assemblies_table, row, 0)
            item_id = _cell_text(self._assemblies_table, row, 3)
            if not assembly_id or not item_id:
                continue
            assemblies.append(
                Assembly(
                    assembly_id=assembly_id,
                    name=_cell_text(self._assemblies_table, row, 1),
                    takeoff_unit=_cell_text(self._assemblies_table, row, 2) or "EA",
                    components=[
                        AssemblyComponent(
                            item_id=item_id,
                            quantity_per_takeoff_unit=float(
                                _cell_text(self._assemblies_table, row, 4) or "0"
                            ),
                        )
                    ],
                )
            )
        return assemblies

    def _load_items(self, items: list[EstimateItem]) -> None:
        self._items_table.setRowCount(len(items))
        for row, item in enumerate(items):
            _set_row(
                self._items_table,
                row,
                [item.item_id, item.description, item.unit, f"{item.unit_cost:.4f}"],
            )

    def _load_assemblies(self, assemblies: list[Assembly]) -> None:
        self._assemblies_table.setRowCount(len(assemblies))
        for row, assembly in enumerate(assemblies):
            component = assembly.components[0] if assembly.components else None
            _set_row(
                self._assemblies_table,
                row,
                [
                    assembly.assembly_id,
                    assembly.name,
                    assembly.takeoff_unit,
                    component.item_id if component else "",
                    f"{component.quantity_per_takeoff_unit:.4f}" if component else "0",
                ],
            )

    def _add_item_row(self) -> None:
        row = self._items_table.rowCount()
        self._items_table.insertRow(row)
        _set_row(self._items_table, row, [f"ITEM-{row + 1}", "", "EA", "0"])

    def _add_assembly_row(self) -> None:
        row = self._assemblies_table.rowCount()
        self._assemblies_table.insertRow(row)
        _set_row(self._assemblies_table, row, [f"ASM-{row + 1}", "", "EA", "", "1"])


def _cell_text(table: QTableWidget, row: int, column: int) -> str:
    item = table.item(row, column)
    return item.text().strip() if item is not None else ""


def _set_row(table: QTableWidget, row: int, values: list[str]) -> None:
    for column, value in enumerate(values):
        table.setItem(row, column, QTableWidgetItem(value))
