from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QTransform, QBrush, QPen, QColor
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
)


class VideoView(QGraphicsView):
    """Graphics-based video view with zoom and pan support."""
    
    annotation_requested = Signal(float, float)  # Emits video coordinates (x, y) for point
    line_completed = Signal(float, float, float, float)  # Emits (x1, y1, x2, y2) for line
    angle_completed = Signal(float, float, float, float, float, float)  # Emits (x1, y1, x2, y2, x3, y3)
    angle_preview_changed = Signal(float)  # Emits current angle in degrees during drawing

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
        self._annotation_items: list = []  # Can hold ellipses, lines, etc.
        self._annotation_mode: bool = False
        
        # Current tool mode
        self._current_tool: str = "selection"  # "selection", "hand", "point", "line", "angle", etc.
        
        # Line drawing state
        self._line_start_point: QPointF | None = None
        self._line_preview_item: QGraphicsLineItem | None = None
        self._line_is_dragging: bool = False
        self._line_guide_enabled: bool = False
        self._line_preview_color: QColor = QColor("yellow")
        self._line_preview_width: int = 2
        
        # Angle drawing state
        self._angle_points: list[QPointF] = []  # Stores p1, p2, then p3
        self._angle_preview_lines: list[QGraphicsLineItem] = []  # Preview lines
        self._angle_preview_color: QColor = QColor("yellow")
        self._angle_preview_width: int = 2
        self._shift_pressed: bool = False

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

    def set_current_tool(self, tool: str) -> None:
        """Set the current tool and cancel any in-progress drawing."""
        if self._current_tool != tool:
            self._cancel_line_drawing()
            self._cancel_angle_drawing()
        self._current_tool = tool

    def set_line_guide_enabled(self, enabled: bool) -> None:
        """Enable or disable line guide preview."""
        self._line_guide_enabled = enabled

    def set_line_preview_style(self, color: QColor, width: int) -> None:
        """Set the style for line preview."""
        self._line_preview_color = color
        self._line_preview_width = width

    def set_angle_preview_style(self, color: QColor, width: int) -> None:
        """Set the style for angle preview."""
        self._angle_preview_color = color
        self._angle_preview_width = width

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Shift:
            self._shift_pressed = True
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key_Shift:
            self._shift_pressed = False
        super().keyReleaseEvent(event)

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
            
            # Point tool
            if self._current_tool == "point":
                if self._is_inside_video(x, y):
                    self.annotation_requested.emit(x, y)
                    event.accept()
                    return
            
            # Line tool
            elif self._current_tool == "line":
                if self._line_start_point is None:
                    # First click - start the line (must be inside video)
                    if self._is_inside_video(x, y):
                        self._line_start_point = QPointF(x, y)
                        self._line_is_dragging = True
                        event.accept()
                        return
                else:
                    # Second click - complete the line
                    x, y = self._clamp_to_video_bounds(x, y)
                    self.line_completed.emit(
                        self._line_start_point.x(),
                        self._line_start_point.y(),
                        x,
                        y
                    )
                    self._cancel_line_drawing()
                    event.accept()
                    return
            
            # Angle tool
            elif self._current_tool == "angle":
                x, y = self._clamp_to_video_bounds(x, y)
                
                if len(self._angle_points) == 0:
                    # First click - p1 (must be inside video)
                    if self._is_inside_video(x, y):
                        self._angle_points.append(QPointF(x, y))
                        event.accept()
                        return
                elif len(self._angle_points) == 1:
                    # Second click - p2
                    self._angle_points.append(QPointF(x, y))
                    event.accept()
                    return
                elif len(self._angle_points) == 2:
                    # Third click - p3, complete the angle
                    p1 = self._angle_points[0]
                    p2 = self._angle_points[1]
                    
                    # Apply perpendicular constraint if shift is pressed
                    if self._shift_pressed:
                        x, y = self._project_to_perpendicular(p1, p2, x, y)
                    
                    x, y = self._clamp_to_video_bounds(x, y)
                    
                    self.angle_completed.emit(
                        p1.x(), p1.y(),
                        p2.x(), p2.y(),
                        x, y
                    )
                    self._cancel_angle_drawing()
                    event.accept()
                    return
        
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        x, y = self._map_to_video_coords(event.pos())
        
        # Update line preview if drawing
        if self._current_tool == "line" and self._line_start_point is not None:
            if self._line_guide_enabled or self._line_is_dragging:
                x, y = self._clamp_to_video_bounds(x, y)
                self._update_line_preview(x, y)
        
        # Update angle preview if drawing
        elif self._current_tool == "angle" and len(self._angle_points) > 0:
            # Apply perpendicular constraint if shift is pressed and we have 2 points
            if self._shift_pressed and len(self._angle_points) == 2:
                p1 = self._angle_points[0]
                p2 = self._angle_points[1]
                x, y = self._project_to_perpendicular(p1, p2, x, y)
            
            x, y = self._clamp_to_video_bounds(x, y)
            self._update_angle_preview(x, y)
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._hand_enabled and event.button() == Qt.LeftButton:
            self.viewport().setCursor(Qt.OpenHandCursor)
            super().mouseReleaseEvent(event)
            return
        
        # Handle line tool release
        if event.button() == Qt.LeftButton and self._current_tool == "line":
            if self._line_start_point is not None and self._line_is_dragging:
                x, y = self._map_to_video_coords(event.pos())
                x, y = self._clamp_to_video_bounds(x, y)
                
                start = self._line_start_point
                distance = abs(x - start.x()) + abs(y - start.y())
                
                if distance > 5:
                    # User dragged enough → create line immediately
                    self.line_completed.emit(start.x(), start.y(), x, y)
                    self._cancel_line_drawing()
                else:
                    # User clicked without dragging → switch to click-click mode
                    self._line_is_dragging = False
                    if not self._line_guide_enabled and self._line_preview_item is not None:
                        self._scene.removeItem(self._line_preview_item)
                        self._line_preview_item = None
                
                event.accept()
                return
        
        super().mouseReleaseEvent(event)

    def _project_to_perpendicular(self, p1: QPointF, p2: QPointF, x: float, y: float) -> tuple[float, float]:
        """Project point (x, y) onto the line perpendicular to p1-p2 passing through p2."""
        # Direction vector of p1-p2
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        
        # Handle degenerate case (p1 == p2)
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return x, y
        
        # Perpendicular direction (rotate 90 degrees)
        perp_dx = -dy
        perp_dy = dx
        
        # Normalize perpendicular vector
        length = math.sqrt(perp_dx * perp_dx + perp_dy * perp_dy)
        perp_dx /= length
        perp_dy /= length
        
        # Vector from p2 to cursor
        vx = x - p2.x()
        vy = y - p2.y()
        
        # Project onto perpendicular direction
        dot = vx * perp_dx + vy * perp_dy
        
        # Return projected point
        return p2.x() + dot * perp_dx, p2.y() + dot * perp_dy

    def _update_angle_preview(self, end_x: float, end_y: float) -> None:
        """Update the angle preview lines."""
        # Clear existing preview lines
        for item in self._angle_preview_lines:
            self._scene.removeItem(item)
        self._angle_preview_lines.clear()
        
        if len(self._angle_points) == 0:
            return
        
        pen = QPen(self._angle_preview_color)
        pen.setWidth(self._angle_preview_width)
        pen.setCosmetic(True)
        
        if len(self._angle_points) == 1:
            # Drawing first line (p1 to cursor)
            p1 = self._angle_points[0]
            line = QGraphicsLineItem(p1.x(), p1.y(), end_x, end_y)
            line.setPen(pen)
            line.setZValue(101)
            self._scene.addItem(line)
            self._angle_preview_lines.append(line)
        
        elif len(self._angle_points) == 2:
            # Drawing second line (p2 to cursor), also show first line
            p1 = self._angle_points[0]
            p2 = self._angle_points[1]
            
            # First line (p1 to p2)
            line1 = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            line1.setPen(pen)
            line1.setZValue(101)
            self._scene.addItem(line1)
            self._angle_preview_lines.append(line1)
            
            # Second line (p2 to cursor/p3)
            line2 = QGraphicsLineItem(p2.x(), p2.y(), end_x, end_y)
            line2.setPen(pen)
            line2.setZValue(101)
            self._scene.addItem(line2)
            self._angle_preview_lines.append(line2)
            
            # Calculate and emit angle
            angle = self._calculate_angle(p1, p2, QPointF(end_x, end_y))
            self.angle_preview_changed.emit(angle)

    def _calculate_angle(self, p1: QPointF, p2: QPointF, p3: QPointF) -> float:
        """Calculate the angle at p2 formed by p1-p2-p3, always returning < 180 degrees."""
        # Vectors from p2 to p1 and from p2 to p3
        v1x = p1.x() - p2.x()
        v1y = p1.y() - p2.y()
        v2x = p3.x() - p2.x()
        v2y = p3.y() - p2.y()
        
        # Calculate magnitudes
        mag1 = math.sqrt(v1x * v1x + v1y * v1y)
        mag2 = math.sqrt(v2x * v2x + v2y * v2y)
        
        if mag1 < 0.001 or mag2 < 0.001:
            return 0.0
        
        # Calculate dot product and angle
        dot = v1x * v2x + v1y * v2y
        cos_angle = dot / (mag1 * mag2)
        
        # Clamp to avoid numerical errors
        cos_angle = max(-1.0, min(1.0, cos_angle))
        
        angle_rad = math.acos(cos_angle)
        angle_deg = math.degrees(angle_rad)
        
        # Ensure angle is always < 180
        if angle_deg > 180:
            angle_deg = 360 - angle_deg
        
        return angle_deg

    def _cancel_angle_drawing(self) -> None:
        """Cancel any in-progress angle drawing."""
        self._angle_points.clear()
        for item in self._angle_preview_lines:
            self._scene.removeItem(item)
        self._angle_preview_lines.clear()
        # Emit 0 to clear the angle display
        self.angle_preview_changed.emit(-1)  # -1 signals "no angle being drawn"

    def _update_line_preview(self, end_x: float, end_y: float) -> None:
        """Update or create the line preview."""
        if self._line_start_point is None:
            return
        
        start = self._line_start_point
        
        if self._line_preview_item is None:
            self._line_preview_item = QGraphicsLineItem()
            pen = QPen(self._line_preview_color)
            pen.setWidth(self._line_preview_width)
            pen.setCosmetic(True)
            self._line_preview_item.setPen(pen)
            self._line_preview_item.setZValue(101)
            self._scene.addItem(self._line_preview_item)
        
        self._line_preview_item.setLine(start.x(), start.y(), end_x, end_y)

    def _cancel_line_drawing(self) -> None:
        """Cancel any in-progress line drawing."""
        self._line_start_point = None
        self._line_is_dragging = False
        if self._line_preview_item is not None:
            self._scene.removeItem(self._line_preview_item)
            self._line_preview_item = None

    def _clamp_to_video_bounds(self, x: float, y: float) -> tuple[float, float]:
        """Clamp coordinates to video bounds."""
        rect = self._video_item.boundingRect()
        x = max(rect.left(), min(rect.right(), x))
        y = max(rect.top(), min(rect.bottom(), y))
        return x, y

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
            ann_type = annotation.get("type")
            if ann_type == "point":
                self._draw_point(annotation)
            elif ann_type == "line":
                self._draw_line(annotation)
            elif ann_type == "angle":
                self._draw_angle(annotation)

    def _draw_point(self, annotation: dict) -> None:
        """Draw a point annotation on the scene."""
        x = annotation.get("x", 0)
        y = annotation.get("y", 0)
        size = annotation.get("size", 3)
        color = annotation.get("color", QColor("yellow"))
        
        half_size = size / 2
        ellipse = QGraphicsEllipseItem(-half_size, -half_size, size, size)
        ellipse.setBrush(QBrush(color))
        ellipse.setPen(QPen(Qt.NoPen))
        ellipse.setZValue(100)
        ellipse.setPos(x, y)
        ellipse.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations, True)
        
        self._scene.addItem(ellipse)
        self._annotation_items.append(ellipse)

    def _draw_line(self, annotation: dict) -> None:
        """Draw a line annotation on the scene."""
        x1 = annotation.get("x1", 0)
        y1 = annotation.get("y1", 0)
        x2 = annotation.get("x2", 0)
        y2 = annotation.get("y2", 0)
        width = annotation.get("width", 2)
        color = annotation.get("color", QColor("yellow"))
        
        line = QGraphicsLineItem(x1, y1, x2, y2)
        pen = QPen(color)
        pen.setWidth(width)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(100)
        
        self._scene.addItem(line)
        self._annotation_items.append(line)

    def _draw_angle(self, annotation: dict) -> None:
        """Draw an angle annotation on the scene (two lines)."""
        x1 = annotation.get("x1", 0)
        y1 = annotation.get("y1", 0)
        x2 = annotation.get("x2", 0)
        y2 = annotation.get("y2", 0)
        x3 = annotation.get("x3", 0)
        y3 = annotation.get("y3", 0)
        width = annotation.get("width", 2)
        color = annotation.get("color", QColor("yellow"))
        
        pen = QPen(color)
        pen.setWidth(width)
        pen.setCosmetic(True)
        
        # Line from p1 to p2
        line1 = QGraphicsLineItem(x1, y1, x2, y2)
        line1.setPen(pen)
        line1.setZValue(100)
        self._scene.addItem(line1)
        self._annotation_items.append(line1)
        
        # Line from p2 to p3
        line2 = QGraphicsLineItem(x2, y2, x3, y3)
        line2.setPen(pen)
        line2.setZValue(100)
        self._scene.addItem(line2)
        self._annotation_items.append(line2)

    def _map_to_video_coords(self, view_pos):
        """Convert view coordinates to video item coordinates."""
        scene_pos = self.mapToScene(view_pos)
        video_pos = self._video_item.mapFromScene(scene_pos)
        return video_pos.x(), video_pos.y()

    def _is_inside_video(self, x: float, y: float) -> bool:
        """Check if coordinates are within the video bounds."""
        rect = self._video_item.boundingRect()
        return rect.contains(x, y)