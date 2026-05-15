"""Graphics viewport for rendered plan pages."""

from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from uuid import uuid4

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from takeoff_pro.data.models import Measurement, MeasurementKind, Point


class PageViewport(QGraphicsView):
    """Interactive page viewport with zoom, pan, fit, and rotation controls."""

    # Emitted when the user presses a tool shortcut key (L/A/C).
    tool_activation_requested = pyqtSignal(object)  # MeasurementKind
    # Emitted when the user presses Escape to cancel the active tool.
    tool_cancelled = pyqtSignal()
    # Emitted when the user presses Enter to finish the active measurement.
    measurement_finish_requested = pyqtSignal()
    # Emitted when the user presses Delete to remove the last measurement.
    delete_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the viewport scene and interaction state."""
        super().__init__(parent)
        self.setObjectName("pageViewport")
        self._scene = QGraphicsScene(self)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._is_panning = False
        self._space_pressed = False
        self._last_pan_point = QPoint()
        self._rotation_degrees = 0
        self._fit_on_resize = False
        self._active_tool: MeasurementKind | None = None
        self._active_page_id: str | None = None
        self._pending_points: list[Point] = []
        self._calibration_points: list[Point] = []
        self._overlay_items: list[QGraphicsItem] = []
        self._measurement_created: Callable[[Measurement], None] | None = None
        self._calibration_completed: Callable[[list[Point]], None] | None = None

        self.setScene(self._scene)
        self.setBackgroundBrush(QColor("#f4f5f7"))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Reduce unnecessary painter state saves for better render performance.
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState)
        viewport_widget = self.viewport()
        if viewport_widget is not None:
            viewport_widget.installEventFilter(self)

    def set_image(self, image: QImage) -> None:
        """Display a rendered page image."""
        self._scene.clear()
        pixmap_item = self._scene.addPixmap(QPixmap.fromImage(image))
        if pixmap_item is None:
            msg = "Could not add rendered page to the scene."
            raise RuntimeError(msg)
        self._pixmap_item = pixmap_item
        self._scene.setSceneRect(pixmap_item.boundingRect())
        self._rotation_degrees = 0
        self._pending_points = []
        self._calibration_points = []
        self._overlay_items = []
        self.fit_to_window()

    def set_blank_page(self, width: int, height: int) -> None:
        """Display a blank page canvas."""
        image = QImage(width, height, QImage.Format.Format_RGB888)
        image.fill(QColor("white"))
        self.set_image(image)

    def set_placeholder(self, message: str) -> None:
        """Display a neutral placeholder message."""
        self._scene.clear()
        self._pixmap_item = None
        self._pending_points = []
        self._calibration_points = []
        self._overlay_items = []
        self.resetTransform()
        text_item = self._scene.addText(message)
        if text_item is None:
            msg = "Could not add placeholder text to the scene."
            raise RuntimeError(msg)
        text_item.setDefaultTextColor(QColor("#5f6673"))
        text_item.setPos(24, 24)
        self._scene.setSceneRect(0, 0, 800, 600)
        self._fit_on_resize = False

    def set_current_page_id(self, page_id: str | None) -> None:
        """Set the page that new measurements should attach to."""
        self._active_page_id = page_id
        self._pending_points = []

    def set_active_tool(self, kind: MeasurementKind | None) -> None:
        """Set the active drawing tool."""
        self._active_tool = kind
        self._pending_points = []
        if kind is None:
            self._clear_pending_items()

    def set_measurement_created_callback(
        self,
        callback: Callable[[Measurement], None] | None,
    ) -> None:
        """Set the callback invoked when a measurement is completed."""
        self._measurement_created = callback

    def start_calibration(self, callback: Callable[[list[Point]], None]) -> None:
        """Collect two clicked page points for scale calibration."""
        self._active_tool = None
        self._pending_points = []
        self._calibration_points = []
        self._calibration_completed = callback

    def add_tool_point(self, x: float, y: float) -> None:
        """Add a page-space point to the active drawing tool."""
        if self._active_tool is None:
            return
        self._append_pending_point(Point(x=x, y=y, point_type="Normal"))
        self._finish_if_tool_complete()

    def finish_active_measurement(self) -> None:
        """Finish the active polyline or polygon measurement."""
        minimum_points = 2 if self._active_tool == MeasurementKind.LENGTH else 3
        if (
            self._active_tool in {MeasurementKind.LENGTH, MeasurementKind.AREA}
            and len(self._pending_points) >= minimum_points
        ):
            self._finish_pending_measurement()

    def show_measurements(self, measurements: list[Measurement]) -> None:
        """Render measurement overlays for the current page."""
        self._clear_overlays()
        for measurement in measurements:
            self._draw_measurement(measurement)

    def fit_to_window(self) -> None:
        """Fit the current page to the viewport."""
        if self._pixmap_item is None:
            return
        self.resetTransform()
        self.rotate(self._rotation_degrees)
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._fit_on_resize = True

    def actual_size(self) -> None:
        """Show the current page at 100 percent scale."""
        if self._pixmap_item is None:
            return
        self.resetTransform()
        self.rotate(self._rotation_degrees)
        self._fit_on_resize = False

    def rotate_clockwise(self) -> None:
        """Rotate the viewport clockwise by 90 degrees."""
        if self._pixmap_item is None:
            return
        self._rotation_degrees = (self._rotation_degrees + 90) % 360
        if self._fit_on_resize:
            self.fit_to_window()
        else:
            self.resetTransform()
            self.rotate(self._rotation_degrees)

    def zoom_by(self, factor: float) -> None:
        """Scale the current view by a relative factor."""
        if self._pixmap_item is None:
            return
        self.scale(factor, factor)
        self._fit_on_resize = False

    def viewportEvent(self, event: QEvent | None) -> bool:
        """Route viewport mouse events into active takeoff tools."""
        if isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress and self._handle_drawing_press(event):
                return True
            if (
                event.type() == QEvent.Type.MouseButtonDblClick
                and self._handle_drawing_double_click(event)
            ):
                return True
        return super().viewportEvent(event)

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        """Handle mouse events delivered to the viewport child widget."""
        if watched is self.viewport() and isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress and self._handle_drawing_press(event):
                return True
            if (
                event.type() == QEvent.Type.MouseButtonDblClick
                and self._handle_drawing_double_click(event)
            ):
                return True
        return super().eventFilter(watched, event)

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:
        """Finish a polyline or area measurement on double-click."""
        if event is None:
            return
        if self._handle_drawing_double_click(event):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        """Zoom with Ctrl+wheel and preserve normal scrolling otherwise."""
        if event is None:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
            self.zoom_by(factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Start middle-button or space-drag panning."""
        if event is None:
            return
        if self._handle_drawing_press(event):
            event.accept()
            return
        is_middle_pan = event.button() == Qt.MouseButton.MiddleButton
        is_space_pan = self._space_pressed and event.button() == Qt.MouseButton.LeftButton
        if is_middle_pan or is_space_pan:
            self._is_panning = True
            self._last_pan_point = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        """Scroll the viewport while panning is active."""
        if event is None:
            return
        if self._is_panning:
            current_point = event.position().toPoint()
            delta = current_point - self._last_pan_point
            self._last_pan_point = current_point
            horizontal_bar = self.horizontalScrollBar()
            vertical_bar = self.verticalScrollBar()
            if horizontal_bar is not None:
                horizontal_bar.setValue(horizontal_bar.value() - delta.x())
            if vertical_bar is not None:
                vertical_bar.setValue(vertical_bar.value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        """Stop active panning."""
        if event is None:
            return
        if self._is_panning:
            self._is_panning = False
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if self._space_pressed else Qt.CursorShape.ArrowCursor
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Handle viewport keyboard shortcuts."""
        if event is None:
            return
        key = event.key()

        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return

        # Cancel active tool or pending measurement.
        if key == Qt.Key.Key_Escape and not event.isAutoRepeat():
            if self._pending_points or self._active_tool is not None or self._calibration_completed:
                self._pending_points = []
                self._calibration_points = []
                self._calibration_completed = None
                self._active_tool = None
                self._clear_pending_items()
                self.tool_cancelled.emit()
                event.accept()
                return

        # Finish current measurement.
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.isAutoRepeat():
            self.finish_active_measurement()
            self.measurement_finish_requested.emit()
            event.accept()
            return

        # Delete last measurement.
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not event.isAutoRepeat():
            self.delete_requested.emit()
            event.accept()
            return

        # Zoom in/out.
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal) and not event.isAutoRepeat():
            self.zoom_by(1.25)
            event.accept()
            return
        if key == Qt.Key.Key_Minus and not event.isAutoRepeat():
            self.zoom_by(1 / 1.25)
            event.accept()
            return

        # Tool shortcuts — emit to main window for state management.
        _TOOL_KEYS = {
            Qt.Key.Key_L: MeasurementKind.LENGTH,
            Qt.Key.Key_A: MeasurementKind.AREA,
            Qt.Key.Key_C: MeasurementKind.COUNT,
        }
        if key in _TOOL_KEYS and not event.isAutoRepeat():
            self.tool_activation_requested.emit(_TOOL_KEYS[key])
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent | None) -> None:
        """Clear spacebar panning state."""
        if event is None:
            return
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        """Keep fit-to-window pages fitted after resizing."""
        if event is None:
            return
        super().resizeEvent(event)
        if self._fit_on_resize:
            self.fit_to_window()

    def _handle_drawing_press(self, event: QMouseEvent) -> bool:
        if self._calibration_completed is not None and event.button() == Qt.MouseButton.LeftButton:
            self._handle_calibration_click(event)
            return True
        if self._active_tool is not None and event.button() == Qt.MouseButton.LeftButton:
            self._handle_tool_click(event)
            return True
        return False

    def _handle_drawing_double_click(self, event: QMouseEvent) -> bool:
        is_finish_click = (
            self._active_tool in {MeasurementKind.LENGTH, MeasurementKind.AREA}
            and event.button() == Qt.MouseButton.LeftButton
        )
        if not is_finish_click:
            return False
        scene_point = self.mapToScene(event.position().toPoint())
        self._append_pending_point_if_distinct(
            Point(x=scene_point.x(), y=scene_point.y(), point_type="Normal")
        )
        self.finish_active_measurement()
        return True

    def _handle_tool_click(self, event: QMouseEvent) -> None:
        scene_point = self.mapToScene(event.position().toPoint())
        self._append_pending_point(Point(x=scene_point.x(), y=scene_point.y(), point_type="Normal"))
        self._finish_if_tool_complete()

    def _handle_calibration_click(self, event: QMouseEvent) -> None:
        scene_point = self.mapToScene(event.position().toPoint())
        self._calibration_points.append(
            Point(x=scene_point.x(), y=scene_point.y(), point_type="Calibration")
        )
        if len(self._calibration_points) == 2:
            callback = self._calibration_completed
            points = list(self._calibration_points)
            self._calibration_completed = None
            self._calibration_points = []
            if callback is not None:
                callback(points)

    def _append_pending_point(self, point: Point) -> None:
        self._pending_points.append(point)
        self._draw_pending_points()

    def _append_pending_point_if_distinct(self, point: Point) -> None:
        if self._pending_points:
            last_point = self._pending_points[-1]
            if last_point.x == point.x and last_point.y == point.y:
                return
        self._append_pending_point(point)

    def _finish_if_tool_complete(self) -> None:
        if self._active_tool == MeasurementKind.COUNT:
            self._finish_pending_measurement()

    def _finish_pending_measurement(self) -> None:
        if self._active_tool is None or self._measurement_created is None:
            self._pending_points = []
            return
        measurement = Measurement(
            id=str(uuid4()),
            name=self._active_tool.value.title(),
            kind=self._active_tool,
            page_id=self._active_page_id,
            points=list(self._pending_points),
        )
        self._pending_points = []
        self._measurement_created(measurement)

    def _draw_pending_points(self) -> None:
        self._clear_pending_items()
        pending = Measurement(
            id="pending",
            name="Pending",
            kind=self._active_tool or MeasurementKind.UNKNOWN,
            page_id=self._active_page_id,
            points=list(self._pending_points),
        )
        self._draw_measurement(pending, pending=True)

    def _draw_measurement(self, measurement: Measurement, *, pending: bool = False) -> None:
        if measurement.page_id is not None and measurement.page_id != self._active_page_id:
            return
        points = measurement.points
        if not points:
            return
        color = QColor("#2563eb" if not pending else "#dc2626")
        pen = QPen(color, 2)
        brush = QBrush(QColor(37, 99, 235, 45))
        if measurement.kind == MeasurementKind.COUNT:
            for point in points:
                self._add_overlay_item(
                    self._scene.addEllipse(point.x - 5, point.y - 5, 10, 10, pen, QBrush(color)),
                    pending=pending,
                )
            return
        if measurement.kind == MeasurementKind.AREA and len(points) >= 3:
            polygon = QPolygonF([QPointF(point.x, point.y) for point in points])
            self._add_overlay_item(self._scene.addPolygon(polygon, pen, brush), pending=pending)
            return
        for start, end in pairwise(points):
            self._add_overlay_item(
                self._scene.addLine(start.x, start.y, end.x, end.y, pen),
                pending=pending,
            )
        for point in points:
            self._add_overlay_item(
                self._scene.addEllipse(point.x - 3, point.y - 3, 6, 6, pen, QBrush(color)),
                pending=pending,
            )

    def _add_overlay_item(self, item: QGraphicsItem | None, *, pending: bool) -> None:
        if item is not None:
            item.setData(0, "pending" if pending else "overlay")
            self._overlay_items.append(item)

    def _clear_overlays(self) -> None:
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items = []

    def _clear_pending_items(self) -> None:
        remaining_items: list[QGraphicsItem] = []
        for item in self._overlay_items:
            if item.data(0) == "pending":
                self._scene.removeItem(item)
            else:
                remaining_items.append(item)
        self._overlay_items = remaining_items
