from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QTransform
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


class VideoView(QGraphicsView):
    """Graphics-based video view with zoom and pan support."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._video_item = QGraphicsVideoItem()
        self._scene.addItem(self._video_item)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        self._zoom = 1.0
        self._zoom_min = 0.2
        self._zoom_max = 8.0
        self._hand_enabled = False

        self.setDragMode(QGraphicsView.NoDrag)
        self.setAcceptDrops(True)

    @property
    def video_item(self) -> QGraphicsVideoItem:
        return self._video_item

    def reset_view(self) -> bool:
        """Fit the video in view and reset user zoom factor. Returns True if applied."""
        self._zoom = 1.0
        self.setTransform(QTransform())
        rect = self._video_item.boundingRect()
        if rect.isEmpty():
            return False
        self.fitInView(self._video_item, Qt.KeepAspectRatio)
        return True

    def set_hand_mode(self, enabled: bool) -> None:
        self._hand_enabled = enabled
        self.setDragMode(QGraphicsView.ScrollHandDrag if enabled else QGraphicsView.NoDrag)
        cursor = Qt.OpenHandCursor if enabled else Qt.ArrowCursor
        self.viewport().setCursor(cursor)

    def wheelEvent(self, event) -> None:
        angle = event.angleDelta().y()
        if angle == 0:
            event.ignore()
            return

        factor = 1.15 if angle > 0 else 1 / 1.15
        new_zoom = self._zoom * factor
        if new_zoom < self._zoom_min:
            factor = self._zoom_min / self._zoom
            self._zoom = self._zoom_min
        elif new_zoom > self._zoom_max:
            factor = self._zoom_max / self._zoom
            self._zoom = self._zoom_max
        else:
            self._zoom = new_zoom

        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event) -> None:
        if self._hand_enabled and event.button() == Qt.LeftButton:
            self.viewport().setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._hand_enabled and event.button() == Qt.LeftButton:
            self.viewport().setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)
