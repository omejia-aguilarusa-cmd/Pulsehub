"""Graphics viewport for rendered plan pages."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import (
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QWidget


class PageViewport(QGraphicsView):
    """Interactive page viewport with zoom, pan, fit, and rotation controls."""

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

        self.setScene(self._scene)
        self.setBackgroundBrush(QColor("#f4f5f7"))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
        self.fit_to_window()

    def set_placeholder(self, message: str) -> None:
        """Display a neutral placeholder message."""
        self._scene.clear()
        self._pixmap_item = None
        self.resetTransform()
        text_item = self._scene.addText(message)
        if text_item is None:
            msg = "Could not add placeholder text to the scene."
            raise RuntimeError(msg)
        text_item.setDefaultTextColor(QColor("#5f6673"))
        text_item.setPos(24, 24)
        self._scene.setSceneRect(0, 0, 800, 600)
        self._fit_on_resize = False

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

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        """Zoom with Ctrl+wheel and preserve normal scrolling otherwise."""
        if event is None:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.zoom_by(factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Start middle-button or space-drag panning."""
        if event is None:
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
        """Track spacebar panning state."""
        if event is None:
            return
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
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
