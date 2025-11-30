from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QTransform, QBrush, QPen, QColor
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsEllipseItem


class VideoView(QGraphicsView):
    """Graphics-based video view with zoom and pan support."""
    
    annotation_requested = Signal(float, float)  # Emits video coordinates (x, y)

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

        # Annotation management
        self._annotations: list[dict] = []
        self._annotation_items: list[QGraphicsEllipseItem] = []
        self._annotation_mode: bool = False

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
            return
        
        # Handle annotation click
        if event.button() == Qt.LeftButton and not self._hand_enabled:
            x, y = self._map_to_video_coords(event.pos())
            if self._is_inside_video(x, y):
                self.annotation_requested.emit(x, y)
                event.accept()
                return
        
        super().mousePressEvent(event)

    def set_annotation_mode(self, enabled: bool) -> None:
        """Enable or disable annotation mode (clicking creates annotations)."""
        self._annotation_mode = enabled

    def set_annotations(self, annotations: list[dict]) -> None:
        """Update the visible annotations on the video."""
        # Clear existing annotation graphics
        for item in self._annotation_items:
            self._scene.removeItem(item)
        self._annotation_items.clear()
        
        self._annotations = annotations
        
        # Draw new annotations
        for annotation in annotations:
            if annotation.get("type") == "point":
                self._draw_point(annotation)

    def _draw_point(self, annotation: dict) -> None:
        """Draw a point annotation on the scene."""
        x = annotation.get("x", 0)
        y = annotation.get("y", 0)
        size = annotation.get("size", 3)
        color = annotation.get("color", QColor("yellow"))
        
        # Create ellipse centered at (0, 0) - position set via setPos
        half_size = size / 2
        ellipse = QGraphicsEllipseItem(-half_size, -half_size, size, size)
        ellipse.setBrush(QBrush(color))
        ellipse.setPen(QPen(Qt.NoPen))
        ellipse.setZValue(100)  # Above video
        
        # Position at video coordinates
        ellipse.setPos(x, y)
        
        # This flag makes the item ignore view transformations (zoom),
        # so it stays the same size on screen
        ellipse.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations, True)
        
        self._scene.addItem(ellipse)
        self._annotation_items.append(ellipse)

    def _map_to_video_coords(self, view_pos):
        """Convert view coordinates to video item coordinates."""
        scene_pos = self.mapToScene(view_pos)
        video_pos = self._video_item.mapFromScene(scene_pos)
        return video_pos.x(), video_pos.y()

    def _is_inside_video(self, x: float, y: float) -> bool:
        """Check if coordinates are within the video bounds."""
        rect = self._video_item.boundingRect()
        return rect.contains(x, y)

    def mouseReleaseEvent(self, event) -> None:
        if self._hand_enabled and event.button() == Qt.LeftButton:
            self.viewport().setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)
