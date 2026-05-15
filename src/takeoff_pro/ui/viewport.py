"""Graphics viewport for rendered plan pages.

GPU acceleration
----------------
The viewport attempts to use an OpenGL backend for QGraphicsView.  When
available, all zoom/pan and overlay compositing is handled by the GPU.  The
application falls back to software rendering transparently when
QtOpenGLWidgets is unavailable or the driver rejects the context.

Adaptive render quality
-----------------------
When the user zooms in beyond the quality of the base image a
``adaptive_render_needed`` signal is emitted after a short debounce.  The
main window handles this by rendering just the visible region at a higher
zoom and calling ``show_detail_image`` to overlay it on the scene.

Z-layer ordering (scene Z-values)
----------------------------------
  -1.0  base pixmap (thumbnail or full-quality page image)
   0.0  adaptive detail image (region rendered at current zoom + quality)
   1.0  measurement overlays (lines, polygons, count dots)
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from itertools import pairwise
from uuid import uuid4

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
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
    QLabel,
    QVBoxLayout,
    QWidget,
)

from takeoff_pro.data.models import Measurement, MeasurementKind, Point

LOGGER = logging.getLogger(__name__)

# ── OpenGL backend ────────────────────────────────────────────────────────────
# PyQt6 bundles QtOpenGLWidgets — no separate PyOpenGL install required.
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget as _QOpenGLWidget  # type: ignore[import]
    _OPENGL_AVAILABLE = True
except Exception:  # ImportError, or driver missing
    _QOpenGLWidget = None  # type: ignore[assignment,misc]
    _OPENGL_AVAILABLE = False

# ── Quality constants ─────────────────────────────────────────────────────────
# These must match _RENDER_QUALITY in page_renderer.py.
_BASE_QUALITY: float = 2.0          # quality used by render_page_to_image
_THUMB_QUALITY_MAX: float = 1.0     # max zoom used for thumbnails
_ADAPTIVE_HEADROOM: float = 0.75    # trigger upgrade when display_zoom > quality * headroom
_ADAPTIVE_DEBOUNCE_MS: int = 350    # ms to wait after last zoom before requesting upgrade
_MAX_ADAPTIVE_ZOOM: float = 8.0     # hard cap on region render zoom


class PageViewport(QGraphicsView):
    """Interactive page viewport with zoom, pan, fit, and rotation controls."""

    # ── Signals ───────────────────────────────────────────────────────────────
    tool_activation_requested = pyqtSignal(object)   # MeasurementKind
    tool_cancelled = pyqtSignal()
    measurement_finish_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    # Emitted after a debounce when the current display_zoom has moved far
    # enough beyond the base render quality to warrant a region re-render.
    # Payload: (display_zoom, visible_rect_in_scene_pts)
    adaptive_render_needed = pyqtSignal(float, QRectF)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the viewport scene and interaction state."""
        super().__init__(parent)
        self.setObjectName("pageViewport")
        self._scene = QGraphicsScene(self)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._detail_item: QGraphicsPixmapItem | None = None
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

        # Current base-image render quality (PDF points per logical pixel).
        self._render_quality: float = _BASE_QUALITY

        # Debounce timer for adaptive quality upgrades.
        self._quality_timer = QTimer(self)
        self._quality_timer.setSingleShot(True)
        self._quality_timer.timeout.connect(self._emit_adaptive_render_needed)

        # Perf overlay (built lazily, shown/hidden via toggle_perf_overlay).
        self._perf_overlay: _PerfOverlay | None = None
        self._gpu_enabled: bool = False

        self.setScene(self._scene)
        self.setBackgroundBrush(QColor("#f4f5f7"))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState)

        # GPU backend — must be set before the window is shown.
        self._try_enable_opengl()

        vp = self.viewport()
        if vp is not None:
            vp.installEventFilter(self)

    # ── GPU setup ─────────────────────────────────────────────────────────────

    def _try_enable_opengl(self) -> None:
        if not _OPENGL_AVAILABLE or _QOpenGLWidget is None:
            LOGGER.debug("OpenGL viewport unavailable — using software rendering.")
            return
        try:
            gl_widget = _QOpenGLWidget()
            self.setViewport(gl_widget)
            # FullViewportUpdate is required for OpenGL; Qt redraws the entire
            # viewport on each frame rather than individual dirty rects.
            self.setViewportUpdateMode(
                QGraphicsView.ViewportUpdateMode.FullViewportUpdate
            )
            self._gpu_enabled = True
            LOGGER.info("GPU viewport enabled (OpenGL/Qt RHI).")
        except Exception as exc:
            LOGGER.warning("OpenGL viewport setup failed: %s — using software.", exc)

    @property
    def gpu_enabled(self) -> bool:
        """True when the OpenGL viewport backend is active."""
        return self._gpu_enabled

    # ── Render-quality tracking ───────────────────────────────────────────────

    def set_render_quality(self, quality: float) -> None:
        """Record the quality (devicePixelRatio) of the currently displayed image."""
        self._render_quality = max(quality, 0.01)
        # Cancel any pending adaptive render — the quality just changed.
        self._quality_timer.stop()

    def show_detail_image(
        self, image: QImage, origin_x: float, origin_y: float
    ) -> None:
        """Overlay a high-quality region image at (origin_x, origin_y) in scene space.

        Replaces any previously displayed detail image.
        """
        if self._detail_item is not None:
            self._scene.removeItem(self._detail_item)
            self._detail_item = None

        pixmap = QPixmap.fromImage(image)
        item = self._scene.addPixmap(pixmap)
        if item is None:
            return
        item.setPos(origin_x, origin_y)
        item.setZValue(0.0)   # above base image (z=-1), below overlays (z=1)
        self._detail_item = item

    def clear_detail_image(self) -> None:
        """Remove the adaptive-quality detail overlay."""
        if self._detail_item is not None:
            self._scene.removeItem(self._detail_item)
            self._detail_item = None

    # ── Perf overlay ──────────────────────────────────────────────────────────

    def toggle_perf_overlay(self) -> bool:
        """Show or hide the performance overlay. Returns True when now visible."""
        if self._perf_overlay is None:
            self._perf_overlay = _PerfOverlay(self)
        if self._perf_overlay.isVisible():
            self._perf_overlay.hide()
            return False
        vp = self.viewport()
        if vp is not None:
            self._perf_overlay.move(vp.width() - self._perf_overlay.width() - 8, 8)
        self._perf_overlay.show()
        self._perf_overlay.raise_()
        return True

    def _update_perf_overlay(self) -> None:
        """Push current metrics to the overlay if it's visible."""
        if self._perf_overlay is None or not self._perf_overlay.isVisible():
            return
        self._perf_overlay.update_metrics(
            display_zoom=self.transform().m11(),
            render_quality=self._render_quality,
            gpu=self._gpu_enabled,
        )

    # ── Image management ──────────────────────────────────────────────────────

    def set_image(self, image: QImage) -> None:
        """Display a rendered page image as the base layer (z = -1)."""
        self._scene.clear()
        self._detail_item = None
        self._overlay_items = []
        pixmap_item = self._scene.addPixmap(QPixmap.fromImage(image))
        if pixmap_item is None:
            msg = "Could not add rendered page to the scene."
            raise RuntimeError(msg)
        pixmap_item.setZValue(-1.0)
        self._pixmap_item = pixmap_item
        self._scene.setSceneRect(pixmap_item.boundingRect())
        self._rotation_degrees = 0
        self._pending_points = []
        self._calibration_points = []
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
        self._detail_item = None
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

    # ── Tool management ───────────────────────────────────────────────────────

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

    # ── View controls ─────────────────────────────────────────────────────────

    def fit_to_window(self) -> None:
        """Fit the current page to the viewport."""
        if self._pixmap_item is None:
            return
        self.resetTransform()
        self.rotate(self._rotation_degrees)
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._fit_on_resize = True
        self._quality_timer.stop()

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
        self._on_zoom_changed()

    def visible_scene_rect(self) -> QRectF:
        """Return the visible portion of the scene in scene (PDF-point) coordinates."""
        vp = self.viewport()
        if vp is None:
            return QRectF()
        return self.mapToScene(vp.rect()).boundingRect()

    # ── Adaptive quality ──────────────────────────────────────────────────────

    def _on_zoom_changed(self) -> None:
        """Called whenever the viewport zoom changes; schedules quality check."""
        self._update_perf_overlay()
        display_zoom = self.transform().m11()
        # Only schedule if we're exceeding the current quality.
        if display_zoom > self._render_quality * _ADAPTIVE_HEADROOM:
            self._quality_timer.start(_ADAPTIVE_DEBOUNCE_MS)

    def _emit_adaptive_render_needed(self) -> None:
        """Emit signal after debounce if zoom still warrants a quality upgrade."""
        if self._pixmap_item is None:
            return
        display_zoom = self.transform().m11()
        if display_zoom <= self._render_quality * _ADAPTIVE_HEADROOM:
            return  # Zoom reduced since timer started — no longer needed.
        self.adaptive_render_needed.emit(
            min(display_zoom * 1.5, _MAX_ADAPTIVE_ZOOM),
            self.visible_scene_rect(),
        )

    # ── Event handlers ────────────────────────────────────────────────────────

    def viewportEvent(self, event: QEvent | None) -> bool:
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
        if event is None:
            return
        if self._handle_drawing_double_click(event):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        """Zoom with Ctrl+wheel; normal scroll otherwise."""
        if event is None:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
            self.zoom_by(factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
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
        if event is None:
            return
        if self._is_panning:
            current_point = event.position().toPoint()
            delta = current_point - self._last_pan_point
            self._last_pan_point = current_point
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            if hbar is not None:
                hbar.setValue(hbar.value() - delta.x())
            if vbar is not None:
                vbar.setValue(vbar.value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self._is_panning:
            self._is_panning = False
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if self._space_pressed
                else Qt.CursorShape.ArrowCursor
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

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.isAutoRepeat():
            self.finish_active_measurement()
            self.measurement_finish_requested.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not event.isAutoRepeat():
            self.delete_requested.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal) and not event.isAutoRepeat():
            self.zoom_by(1.25)
            event.accept()
            return

        if key == Qt.Key.Key_Minus and not event.isAutoRepeat():
            self.zoom_by(1 / 1.25)
            event.accept()
            return

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
        if event is None:
            return
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        if event is None:
            return
        super().resizeEvent(event)
        if self._fit_on_resize:
            self.fit_to_window()
        # Reposition perf overlay to stay at top-right.
        if self._perf_overlay is not None and self._perf_overlay.isVisible():
            vp = self.viewport()
            if vp is not None:
                self._perf_overlay.move(
                    vp.width() - self._perf_overlay.width() - 8, 8
                )

    # ── Drawing tool internals ────────────────────────────────────────────────

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
        self._append_pending_point(
            Point(x=scene_point.x(), y=scene_point.y(), point_type="Normal")
        )
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
        z = 1.0  # overlay layer — above both base and detail images

        if measurement.kind == MeasurementKind.COUNT:
            for point in points:
                item = self._scene.addEllipse(
                    point.x - 5, point.y - 5, 10, 10, pen, QBrush(color)
                )
                if item is not None:
                    item.setZValue(z)
                self._add_overlay_item(item, pending=pending)
            return

        if measurement.kind == MeasurementKind.AREA and len(points) >= 3:
            polygon = QPolygonF([QPointF(p.x, p.y) for p in points])
            item = self._scene.addPolygon(polygon, pen, brush)
            if item is not None:
                item.setZValue(z)
            self._add_overlay_item(item, pending=pending)
            return

        for start, end in pairwise(points):
            item = self._scene.addLine(start.x, start.y, end.x, end.y, pen)
            if item is not None:
                item.setZValue(z)
            self._add_overlay_item(item, pending=pending)
        for point in points:
            item = self._scene.addEllipse(
                point.x - 3, point.y - 3, 6, 6, pen, QBrush(color)
            )
            if item is not None:
                item.setZValue(z)
            self._add_overlay_item(item, pending=pending)

    def _add_overlay_item(self, item: QGraphicsItem | None, *, pending: bool) -> None:
        if item is not None:
            item.setData(0, "pending" if pending else "overlay")
            self._overlay_items.append(item)

    def _clear_overlays(self) -> None:
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items = []

    def _clear_pending_items(self) -> None:
        remaining: list[QGraphicsItem] = []
        for item in self._overlay_items:
            if item.data(0) == "pending":
                self._scene.removeItem(item)
            else:
                remaining.append(item)
        self._overlay_items = remaining


# ── Performance overlay widget ────────────────────────────────────────────────

class _PerfOverlay(QWidget):
    """Transparent on-screen widget showing real-time render metrics.

    Activated by Ctrl+Shift+P.  Mouse events pass through to the viewport.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(220)

        self.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 170);
                border-radius: 6px;
            }
            QLabel {
                color: #00ff88;
                font-family: Consolas, "Courier New", monospace;
                font-size: 11px;
                padding: 1px 0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._lines: dict[str, QLabel] = {}
        for key in ("backend", "display_zoom", "render_quality", "last_open",
                    "last_render", "last_convert", "last_region"):
            lbl = QLabel("—")
            layout.addWidget(lbl)
            self._lines[key] = lbl

        self.adjustSize()

    def update_metrics(
        self,
        display_zoom: float,
        render_quality: float,
        gpu: bool,
    ) -> None:
        from takeoff_pro.render.profiler import profiler as _p

        self._lines["backend"].setText(
            f"GPU: {'OpenGL ✓' if gpu else 'Software'}"
        )
        self._lines["display_zoom"].setText(f"Zoom: {display_zoom:.2f}×")
        self._lines["render_quality"].setText(f"Render Q: {render_quality:.1f}×")
        self._lines["last_open"].setText(
            f"PDF open: {_p.last_ms('pdf_open'):.0f} ms"
        )
        self._lines["last_render"].setText(
            f"Pixmap:  {_p.last_ms('pixmap_render'):.0f} ms"
        )
        self._lines["last_convert"].setText(
            f"Convert: {_p.last_ms('image_convert'):.0f} ms"
        )
        self._lines["last_region"].setText(
            f"Region:  {_p.last_ms('pixmap_render_region'):.0f} ms"
        )
        self.adjustSize()
