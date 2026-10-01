"""
Interactive Video Frame Preview and Bounding Box Editor.
Allows visual inspection, drag-and-drop relocation, and handle-based resizing
of the watermark bounding box with live coordinate feedback.
"""
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QFont, QImage, QMouseEvent, QPainter, QPaintEvent,
    QPen, QPixmap
)
from PySide6.QtWidgets import QWidget


class PreviewWidget(QWidget):
    box_changed = Signal(int, int, int, int)  # x, y, w, h in video coordinates

    HANDLE_SIZE = 8  # screen pixels for resize handles

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)

        self._pixmap: Optional[QPixmap] = None
        self._video_w: int = 1920
        self._video_h: int = 1080

        # Box in original video coordinate space
        self._box_x: int = 0
        self._box_y: int = 0
        self._box_w: int = 100
        self._box_h: int = 100
        self._has_box: bool = False

        # Interaction state
        self._drag_mode: Optional[str] = None  # 'move', 'tl', 'tr', 'bl', 'br'
        self._drag_start_pos: QPoint = QPoint()
        self._orig_box: Tuple[int, int, int, int] = (0, 0, 0, 0)

    def set_frame_image(self, image_path: Path, video_w: int, video_h: int):
        self._video_w = max(1, video_w)
        self._video_h = max(1, video_h)
        self._pixmap = QPixmap(str(image_path))
        self.update()

    def set_box(self, x: int, y: int, w: int, h: int):
        self._box_x = max(0, min(self._video_w - 10, int(x)))
        self._box_y = max(0, min(self._video_h - 10, int(y)))
        self._box_w = max(8, min(self._video_w - self._box_x, int(w)))
        self._box_h = max(8, min(self._video_h - self._box_y, int(h)))
        self._has_box = True
        self.update()
        self.box_changed.emit(self._box_x, self._box_y, self._box_w, self._box_h)

    def get_box(self) -> Tuple[int, int, int, int]:
        return (self._box_x, self._box_y, self._box_w, self._box_h)

    def clear(self):
        self._pixmap = None
        self._has_box = False
        self.update()

    def _get_draw_rect(self) -> QRect:
        """Calculate image rect centered in widget maintaining aspect ratio."""
        if not self._pixmap or self._pixmap.isNull():
            return QRect()

        w_space = self.width() - 20
        h_space = self.height() - 20
        if w_space <= 0 or h_space <= 0:
            return QRect()

        scaled_size = self._pixmap.size().scaled(QSize(w_space, h_space), Qt.KeepAspectRatio)
        x = (self.width() - scaled_size.width()) // 2
        y = (self.height() - scaled_size.height()) // 2
        return QRect(x, y, scaled_size.width(), scaled_size.height())

    def _video_to_screen_rect(self, d_rect: QRect) -> QRect:
        if self._video_w <= 0 or self._video_h <= 0 or d_rect.isEmpty():
            return QRect()
        scale_x = d_rect.width() / self._video_w
        scale_y = d_rect.height() / self._video_h

        sx = d_rect.x() + int(self._box_x * scale_x)
        sy = d_rect.y() + int(self._box_y * scale_y)
        sw = max(6, int(self._box_w * scale_x))
        sh = max(6, int(self._box_h * scale_y))
        return QRect(sx, sy, sw, sh)

    def _screen_to_video_coords(self, pt: QPoint, d_rect: QRect) -> Tuple[int, int]:
        if d_rect.width() <= 0 or d_rect.height() <= 0:
            return (0, 0)
        scale_x = self._video_w / d_rect.width()
        scale_y = self._video_h / d_rect.height()

        vx = int((pt.x() - d_rect.x()) * scale_x)
        vy = int((pt.y() - d_rect.y()) * scale_y)
        return (max(0, min(self._video_w, vx)), max(0, min(self._video_h, vy)))

    def _get_handles(self, s_rect: QRect) -> dict:
        sz = self.HANDLE_SIZE
        hs = sz // 2
        return {
            "tl": QRect(s_rect.left() - hs, s_rect.top() - hs, sz, sz),
            "tr": QRect(s_rect.right() - hs, s_rect.top() - hs, sz, sz),
            "bl": QRect(s_rect.left() - hs, s_rect.bottom() - hs, sz, sz),
            "br": QRect(s_rect.right() - hs, s_rect.bottom() - hs, sz, sz),
        }

    def mousePressEvent(self, event: QMouseEvent):
        if not self._has_box or event.button() != Qt.LeftButton:
            return

        d_rect = self._get_draw_rect()
        if d_rect.isEmpty():
            return

        s_rect = self._video_to_screen_rect(d_rect)
        handles = self._get_handles(s_rect)

        pos = event.pos()
        self._drag_start_pos = pos
        self._orig_box = (self._box_x, self._box_y, self._box_w, self._box_h)

        # Check handles first
        for name, h_rect in handles.items():
            if h_rect.contains(pos):
                self._drag_mode = name
                return

        # Check if inside box
        if s_rect.contains(pos):
            self._drag_mode = "move"
            self.setCursor(Qt.SizeAllCursor)
            return

        self._drag_mode = None

    def mouseMoveEvent(self, event: QMouseEvent):
        d_rect = self._get_draw_rect()
        if d_rect.isEmpty() or not self._has_box:
            return

        pos = event.pos()

        # Update cursor when hovering
        if self._drag_mode is None:
            s_rect = self._video_to_screen_rect(d_rect)
            handles = self._get_handles(s_rect)
            if handles["tl"].contains(pos) or handles["br"].contains(pos):
                self.setCursor(Qt.SizeFDiagCursor)
            elif handles["tr"].contains(pos) or handles["bl"].contains(pos):
                self.setCursor(Qt.SizeBDiagCursor)
            elif s_rect.contains(pos):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return

        # Handle active drag
        dx_screen = pos.x() - self._drag_start_pos.x()
        dy_screen = pos.y() - self._drag_start_pos.y()

        scale_x = self._video_w / d_rect.width()
        scale_y = self._video_h / d_rect.height()
        dx_vid = int(dx_screen * scale_x)
        dy_vid = int(dy_screen * scale_y)

        ox, oy, ow, oh = self._orig_box

        if self._drag_mode == "move":
            new_x = max(0, min(self._video_w - ow, ox + dx_vid))
            new_y = max(0, min(self._video_h - oh, oy + dy_vid))
            self._box_x = new_x
            self._box_y = new_y
        elif self._drag_mode == "tl":
            new_x = min(ox + ow - 16, max(0, ox + dx_vid))
            new_y = min(oy + oh - 16, max(0, oy + dy_vid))
            self._box_w = (ox + ow) - new_x
            self._box_h = (oy + oh) - new_y
            self._box_x = new_x
            self._box_y = new_y
        elif self._drag_mode == "tr":
            new_y = min(oy + oh - 16, max(0, oy + dy_vid))
            self._box_w = max(16, min(self._video_w - ox, ow + dx_vid))
            self._box_h = (oy + oh) - new_y
            self._box_y = new_y
        elif self._drag_mode == "bl":
            new_x = min(ox + ow - 16, max(0, ox + dx_vid))
            self._box_w = (ox + ow) - new_x
            self._box_h = max(16, min(self._video_h - oy, oh + dy_vid))
            self._box_x = new_x
        elif self._drag_mode == "br":
            self._box_w = max(16, min(self._video_w - ox, ow + dx_vid))
            self._box_h = max(16, min(self._video_h - oy, oh + dy_vid))

        self.update()
        self.box_changed.emit(self._box_x, self._box_y, self._box_w, self._box_h)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_mode = None
        self.setCursor(Qt.ArrowCursor)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw dark canvas background
        painter.fillRect(self.rect(), QColor("#10141c"))

        d_rect = self._get_draw_rect()
        if not self._pixmap or self._pixmap.isNull() or d_rect.isEmpty():
            # Placeholder text
            painter.setPen(QColor("#484f58"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "No video loaded\nDrop a video or click 'Select Video'")
            return

        # Draw scaled frame
        painter.drawPixmap(d_rect, self._pixmap)

        if not self._has_box:
            return

        # Draw Watermark Box
        s_rect = self._video_to_screen_rect(d_rect)

        # Semi-transparent red highlight
        painter.fillRect(s_rect, QColor(255, 68, 68, 65))

        # Box border
        pen = QPen(QColor("#ff3333"), 2, Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRect(s_rect)

        # Corner handles
        handles = self._get_handles(s_rect)
        for h_rect in handles.values():
            painter.fillRect(h_rect, QColor("#ffffff"))
            painter.setPen(QPen(QColor("#ff3333"), 1.5))
            painter.drawRect(h_rect)

        # Dimension tooltip badge
        label = f"({self._box_x}, {self._box_y}) {self._box_w}x{self._box_h}"
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        badge_w = 140
        badge_h = 20
        bx = max(s_rect.left(), min(self.width() - badge_w - 5, s_rect.left()))
        by = max(5, s_rect.top() - badge_h - 4)
        badge_rect = QRect(bx, by, badge_w, badge_h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 190))
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge_rect, Qt.AlignCenter, label)
