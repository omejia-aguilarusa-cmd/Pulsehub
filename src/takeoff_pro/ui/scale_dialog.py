"""Scale calibration dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QWidget,
)


class ScaleCalibrationDialog(QDialog):
    """Dialog for entering the real distance between two clicked points."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the dialog controls."""
        super().__init__(parent)
        self.setWindowTitle("Set Scale")
        self._distance_input = QDoubleSpinBox(self)
        self._distance_input.setRange(0.0001, 1_000_000)
        self._distance_input.setDecimals(4)
        self._distance_input.setValue(1.0)

        self._unit_input = QComboBox(self)
        self._unit_input.addItems(["FT", "IN", "M"])

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow("Distance", self._distance_input)
        layout.addRow("Units", self._unit_input)
        layout.addRow(buttons)

    def distance(self) -> float:
        """Return the entered real-world distance."""
        return float(self._distance_input.value())

    def unit(self) -> str:
        """Return the selected real-world unit."""
        return self._unit_input.currentText()
