# edof/gui/pyqt6_widget.py
"""
EdofQtWidget – a PyQt6 QWidget that renders and interacts with an EDOF page.
Requires: pip install edof[pyqt6]

Usage::

    from PyQt6.QtWidgets import QApplication
    import edof
    from edof.gui.pyqt6_widget import EdofQtWidget

    app    = QApplication([])
    doc    = edof.Document()
    page   = doc.add_page()
    page.add_textbox(10, 10, 100, 20, "Hello from PyQt6!")

    widget = EdofQtWidget(doc, page_index=0)
    widget.resize(800, 600)
    widget.show()
    app.exec()
"""

from __future__ import annotations
from typing import Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from edof.format.document import Document
    from edof.format.objects  import EdofObject


def _require_pyqt6():
    try:
        import PyQt6
    except ImportError:
        raise ImportError(
            "PyQt6 is required for EdofQtWidget. "
            "Install with:  pip install edof[pyqt6]"
        )


class EdofQtWidget:
    """
    PyQt6 widget for viewing / editing an EDOF document page.
    Import guard: PyQt6 is only imported when this class is instantiated.
    """

    def __new__(cls, *args, **kwargs):
        _require_pyqt6()
        return _build_widget(*args, **kwargs)


def _build_widget(doc: "Document",
                  page_index: int  = 0,
                  zoom:       float = 1.0,
                  dpi:        int   = 96,
                  parent=None):
    """
    Construct and return a QWidget instance.
    Called lazily so PyQt6 is only imported when explicitly used.
    """
    from PyQt6.QtWidgets import QWidget, QSizePolicy
    from PyQt6.QtCore    import Qt, QPoint
    from PyQt6.QtGui     import QPixmap, QPainter, QImage, QColor, QPen, QCursor

    from edof.engine.renderer  import render_page
    from edof.engine.transform import mm_to_px, px_to_mm
    from PIL import Image
    import io

    class _EdofWidget(QWidget):
        def __init__(self):
            super().__init__(parent)
            self._doc        = doc
            self._page_index = page_index
            self._zoom       = zoom
            self._dpi        = dpi
            self._selected:  Optional[str] = None
            self._offset     = QPoint(0, 0)
            self._drag_pos   = None
            self._on_select: List[Callable] = []
            self._on_change: List[Callable] = []
            self._pixmap:    Optional[QPixmap] = None

            self.setMinimumSize(200, 200)
            self.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Expanding)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.render_page()

        # ── Render ────────────────────────────────────────────────────────────

        def render_page(self):
            if not self._doc.pages:
                return
            try:
                page = self._doc.pages[self._page_index]
                img  = render_page(page, self._doc.resources,
                                   self._doc.variables, self._dpi)
                w = max(1, int(img.width  * self._zoom))
                h = max(1, int(img.height * self._zoom))
                img = img.resize((w, h), Image.LANCZOS).convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, "PNG")
                buf.seek(0)
                qimg = QImage.fromData(buf.read())
                self._pixmap = QPixmap.fromImage(qimg)
            except Exception as e:
                self._pixmap = None
                print(f"[edof] Render error: {e}")
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor("#888888"))
            if self._pixmap:
                cw, ch = self.width(), self.height()
                pw, ph = self._pixmap.width(), self._pixmap.height()
                ox = max(0, (cw - pw) // 2)
                oy = max(0, (ch - ph) // 2)
                self._offset = QPoint(ox, oy)
                painter.drawPixmap(ox, oy, self._pixmap)
                if self._selected:
                    self._draw_handles(painter, ox, oy)
            painter.end()

        def _draw_handles(self, painter, ox, oy):
            page = self._doc.pages[self._page_index]
            obj  = page.get_object(self._selected)
            if not obj:
                return
            t    = obj.transform
            x0   = ox + mm_to_px(t.x,           self._dpi) * self._zoom
            y0   = oy + mm_to_px(t.y,           self._dpi) * self._zoom
            x1   = ox + mm_to_px(t.x + t.width, self._dpi) * self._zoom
            y1   = oy + mm_to_px(t.y + t.height,self._dpi) * self._zoom
            pen  = QPen(QColor("#0078d4"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            from PyQt6.QtCore import QRectF
            painter.drawRect(QRectF(x0, y0, x1-x0, y1-y0))

        # ── Mouse events ──────────────────────────────────────────────────────

        def mousePressEvent(self, event):
            from PyQt6.QtCore import Qt
            if event.button() == Qt.MouseButton.LeftButton:
                self.setFocus()
                mx = event.position().x() - self._offset.x()
                my = event.position().y() - self._offset.y()
                mmx = px_to_mm(mx / self._zoom, self._dpi)
                mmy = px_to_mm(my / self._zoom, self._dpi)
                hit = self._hit_test(mmx, mmy)
                if hit != self._selected:
                    self._selected = hit
                    for cb in self._on_select:
                        cb(hit)
                self._drag_pos = event.position()
                self.update()

        def mouseMoveEvent(self, event):
            if self._selected and self._drag_pos is not None:
                dx_c = event.position().x() - self._drag_pos.x()
                dy_c = event.position().y() - self._drag_pos.y()
                from edof.engine.transform import px_to_mm
                dx_mm = px_to_mm(dx_c / self._zoom, self._dpi)
                dy_mm = px_to_mm(dy_c / self._zoom, self._dpi)
                page  = self._doc.pages[self._page_index]
                obj   = page.get_object(self._selected)
                if obj:
                    obj.transform.translate(dx_mm, dy_mm)
                self._drag_pos = event.position()
                self.render_page()

        def mouseReleaseEvent(self, event):
            if self._drag_pos:
                for cb in self._on_change:
                    cb()
            self._drag_pos = None

        def wheelEvent(self, event):
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom = min(8.0, self._zoom * 1.15)
            else:
                self._zoom = max(0.05, self._zoom / 1.15)
            self.render_page()

        def keyPressEvent(self, event):
            from PyQt6.QtCore import Qt
            key = event.key()
            nudge = 0.5
            if key == Qt.Key.Key_Left:  self._nudge(-nudge, 0)
            elif key == Qt.Key.Key_Right: self._nudge(nudge, 0)
            elif key == Qt.Key.Key_Up:   self._nudge(0, -nudge)
            elif key == Qt.Key.Key_Down: self._nudge(0, nudge)
            elif key == Qt.Key.Key_Delete:
                if self._selected:
                    self._doc.pages[self._page_index].remove_object(self._selected)
                    self._selected = None
                    self.render_page()
                    for cb in self._on_change:
                        cb()

        # ── Helpers ───────────────────────────────────────────────────────────

        def _hit_test(self, mmx: float, mmy: float) -> Optional[str]:
            page = self._doc.pages[self._page_index]
            for obj in reversed(page.sorted_objects()):
                if not obj.visible:
                    continue
                t = obj.transform
                if t.x <= mmx <= t.x+t.width and t.y <= mmy <= t.y+t.height:
                    return obj.id
            return None

        def _nudge(self, dx: float, dy: float) -> None:
            if not self._selected:
                return
            page = self._doc.pages[self._page_index]
            obj  = page.get_object(self._selected)
            if obj:
                obj.transform.translate(dx, dy)
            self.render_page()
            for cb in self._on_change:
                cb()

        # ── Public API ────────────────────────────────────────────────────────

        def set_document(self, doc, page_index: int = 0):
            self._doc        = doc
            self._page_index = page_index
            self._selected   = None
            self.render_page()

        def set_page(self, index: int):
            self._page_index = index
            self._selected   = None
            self.render_page()

        def on_select(self, cb: Callable):
            self._on_select.append(cb)

        def on_change(self, cb: Callable):
            self._on_change.append(cb)

        @property
        def zoom(self):
            return self._zoom

        @zoom.setter
        def zoom(self, v: float):
            self._zoom = max(0.05, min(8.0, v))
            self.render_page()

    return _EdofWidget()
