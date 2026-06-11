#!/usr/bin/env python3
"""
EDOF Editor – PyQt6
Requires: pip install PyQt6 Pillow edof
"""
import sys, os, math, copy, io as _io, json, threading

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
        QGraphicsItem, QGraphicsPixmapItem, QGraphicsProxyWidget,
        QWidget, QDockWidget, QListWidget, QListWidgetItem, QAbstractItemView,
        QTabWidget, QFormLayout, QLabel, QLineEdit, QTextEdit, QPlainTextEdit,
        QCheckBox, QComboBox, QPushButton,
        QDoubleSpinBox as _QDoubleSpinBox, QSpinBox as _QSpinBox,
        QStyleOptionSpinBox, QStyle, QStyleFactory,
        QToolBar, QStatusBar, QMenu, QScrollArea,
        QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
        QFileDialog, QMessageBox, QInputDialog, QColorDialog,
        QDialog, QDialogButtonBox, QStackedWidget,
        QRadioButton, QButtonGroup, QSplitter, QSizePolicy, QSlider,
    )
    from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, QSize, pyqtSignal, QObject, QSettings
    from PyQt6.QtGui import (
        QAction, QPainter, QPen, QBrush, QColor, QPixmap, QImage,
        QPolygonF, QFont, QTransform, QCursor, QKeySequence, QPalette, QIcon,
    )
except ImportError:
    print("PyQt6 required:  pip install PyQt6"); sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
#  v4.1.14: Custom spinbox subclasses with reliably-drawn arrow triangles
#
#  Why we paint arrows ourselves:
#    - Pure QSS arrow images render unreliably across Qt versions and
#      OS/theme combinations (especially on dark themes — the default
#      black triangles disappear on dark backgrounds).
#    - Applying Fusion style per-spinbox draws the triangles correctly
#      but completely overrides our QSS button colors and hover states.
#    - Painting the triangles ourselves on top of QSS-styled buttons
#      gives us both: nice dark-theme button backgrounds with hover
#      AND crisp anti-aliased white arrows that always render.
# ─────────────────────────────────────────────────────────────────────────────

_SPIN_ARROW_COLOR = QColor("#e0e0e0")     # bright enough on dark + on hover
_SPIN_ARROW_DISABLED = QColor("#666666")  # dimmed when widget disabled

def _draw_spin_arrows(widget):
    """Draw up/down triangle arrows inside the two button subrects of a
    QSpinBox/QDoubleSpinBox. Called from paintEvent of our subclasses
    AFTER super().paintEvent() so the buttons' background/hover/pressed
    states from QSS render normally, and our triangles sit on top."""
    opt = QStyleOptionSpinBox()
    widget.initStyleOption(opt)
    style = widget.style()
    up_rect = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                     QStyle.SubControl.SC_SpinBoxUp, widget)
    down_rect = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                       QStyle.SubControl.SC_SpinBoxDown, widget)
    p = QPainter(widget)
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        color = _SPIN_ARROW_COLOR if widget.isEnabled() else _SPIN_ARROW_DISABLED
        p.setBrush(QBrush(color))
        # Triangle half-width and half-height (small, fits 16×13 button)
        hw, hh = 3.5, 2.5
        # Up arrow — apex up, base down, centered in up_rect
        cx, cy = up_rect.center().x() + 0.5, up_rect.center().y() + 0.5
        p.drawPolygon(QPolygonF([
            QPointF(cx - hw, cy + hh),
            QPointF(cx + hw, cy + hh),
            QPointF(cx,      cy - hh),
        ]))
        # Down arrow — apex down, base up, centered in down_rect
        cx, cy = down_rect.center().x() + 0.5, down_rect.center().y() + 0.5
        p.drawPolygon(QPolygonF([
            QPointF(cx - hw, cy - hh),
            QPointF(cx + hw, cy - hh),
            QPointF(cx,      cy + hh),
        ]))
    finally:
        p.end()


class QDoubleSpinBox(_QDoubleSpinBox):
    """v4.1.14: QDoubleSpinBox with custom-painted arrow triangles."""
    def paintEvent(self, event):
        super().paintEvent(event)
        _draw_spin_arrows(self)


class FocusKeepingSpinBox(QDoubleSpinBox):
    """v4.1.23.20: a size spinbox whose up/down arrow buttons change the
    value WITHOUT stealing keyboard focus from the document editor. Only a
    click directly on the number field grabs focus (so the user can type a
    value). Set ._editor_ref to the widget (or canvas) that should keep focus.
    v4.1.23.25: detect the button column by geometry as well, deselect the
    number, and refocus the editor so the caret keeps blinking in the doc."""
    def _refocus_ref(self):
        ref = getattr(self, '_editor_ref', None)
        if ref is None: return
        try:
            if hasattr(ref, '_refocus_inline'):
                ref._refocus_inline()
            else:
                ref.setFocus()
        except Exception: pass

    def mousePressEvent(self, ev):
        try:
            pt = ev.position().toPoint()
            opt = QStyleOptionSpinBox(); self.initStyleOption(opt)
            style = self.style()
            up = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                       QStyle.SubControl.SC_SpinBoxUp, self)
            down = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                         QStyle.SubControl.SC_SpinBoxDown, self)
            on_up = up.contains(pt)
            on_down = down.contains(pt)
            # Geometry fallback: anything in the right-hand button column
            # counts as a step (top half = up, bottom half = down). This
            # covers styles where the hit rects are slightly off.
            if not (on_up or on_down):
                btn_left = min(up.left(), down.left())
                if btn_left > 0 and pt.x() >= btn_left:
                    if pt.y() < self.rect().center().y(): on_up = True
                    else: on_down = True
            if on_up or on_down:
                if on_up: self.stepUp()
                else: self.stepDown()
                try: self.lineEdit().deselect()
                except Exception: pass
                try: self.clearFocus()
                except Exception: pass
                ev.accept()
                self._refocus_ref()
                return
        except Exception:
            pass
        # Click on the number field → normal behaviour (focus + edit)
        super().mousePressEvent(ev)


class QSpinBox(_QSpinBox):
    """v4.1.14: QSpinBox with custom-painted arrow triangles."""
    def paintEvent(self, event):
        super().paintEvent(event)
        _draw_spin_arrows(self)

try:
    import edof
    from edof.engine.text_engine import list_system_fonts, invalidate_font_cache
    from edof.engine.transform   import mm_to_px, px_to_mm, rotate_point
    from edof.api.commands       import CommandHistory
    from PIL import Image
except ImportError as e:
    _a = QApplication(sys.argv)
    QMessageBox.critical(None,"Import error",f"{e}\n\npip install edof[all]")
    sys.exit(1)

# ── Language ───────────────────────────────────────────────────────────────────

class LangManager:
    def __init__(self, lang="en"):
        self._d: dict = {}
        self.load(lang)

    def load(self, lang: str):
        p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "editor_lang", f"{lang}.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                self._d = json.load(f)

    def t(self, key: str, **kw) -> str:
        s = self._d.get(key, key)
        return s.format(**kw) if kw else s

_L = LangManager("en")
t  = _L.t   # short alias

# ── Theme ──────────────────────────────────────────────────────────────────────
CBKG="$3d3d52"; ACC="#0078d4"; ACC2="#ff6600"
PBG="#1e1e2e"; PBG2="#252535"; PBG3="#2a2a3e"
FG="#e0e0f0"; FGD="#7070a0"
HSIZE=6; ROT_DIST=28; MIN_MM=2.0; RDPI=96

QSS=f"""
QMainWindow,QWidget{{background:{PBG};color:{FG};font:10pt 'Segoe UI'}}
QMenuBar{{background:#131320;color:{FG};font:10pt 'Segoe UI'}} QMenuBar::item:selected{{background:{ACC}}}
QMenu{{background:{PBG2};color:{FG};border:1px solid #444;font:10pt 'Segoe UI'}} QMenu::item:selected{{background:{ACC}}}
QToolBar{{background:#131320;border:none;padding:2px}}
QToolButton{{background:{PBG2};color:{FG};border:none;padding:4px 10px;border-radius:3px;
  font-family:'Segoe UI','Segoe UI Symbol','Arial Unicode MS','DejaVu Sans';font-size:10pt}}
QToolButton:hover{{background:{ACC}}}
QDockWidget::title{{background:#131320;padding:5px;font-weight:bold;color:{FGD};font-size:10pt}}
QTabWidget::pane{{border:none;background:{PBG}}}
QTabBar::tab{{background:{PBG2};color:{FGD};padding:5px 12px;border:none;font-size:10pt}}
QTabBar::tab:selected{{background:{PBG};color:{FG};border-top:2px solid {ACC}}}
QLabel{{font:10pt 'Segoe UI'}}
QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox,QTextEdit,QPlainTextEdit{{
  background:{PBG3};color:{FG};border:1px solid #3a3a5a;border-radius:3px;padding:3px 5px;font:10pt 'Segoe UI';min-height:24px}}
QLineEdit:focus,QDoubleSpinBox:focus,QSpinBox:focus,QPlainTextEdit:focus{{border:1px solid {ACC}}}
/* v4.1.2/4.1.9/4.1.9.1/4.1.10.1/4.1.14: SpinBox arrow buttons.
   QSS sets the button rectangles' background/hover/pressed colors only.
   The actual triangle arrows are painted on top by our custom
   QDoubleSpinBox / QSpinBox subclasses (see top of editor.py) so they
   render reliably on any Qt version, OS, and dark/light theme. */
QSpinBox,QDoubleSpinBox{{padding-right:18px}}
QSpinBox::up-button,QDoubleSpinBox::up-button{{
  subcontrol-origin:border;subcontrol-position:top right;
  width:16px;height:13px;background:#3a3a5a;border-left:1px solid #555;border-bottom:1px solid #555;border-top-right-radius:3px}}
QSpinBox::down-button,QDoubleSpinBox::down-button{{
  subcontrol-origin:border;subcontrol-position:bottom right;
  width:16px;height:13px;background:#3a3a5a;border-left:1px solid #555;border-bottom-right-radius:3px}}
QSpinBox::up-button:hover,QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover,QDoubleSpinBox::down-button:hover{{background:{ACC}}}
QSpinBox::up-button:pressed,QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed,QDoubleSpinBox::down-button:pressed{{background:#5a5a7a}}
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow,
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow{{
  /* Suppress Qt's default arrow rendering — we paint our own. */
  width:0;height:0;image:none}}
QPushButton{{background:#333355;color:{FG};border:none;padding:5px 12px;border-radius:3px;min-height:24px;
  font-family:'Segoe UI','Segoe UI Symbol','Arial Unicode MS','DejaVu Sans';font-size:10pt}}
QPushButton:hover{{background:{ACC}}}
QPushButton#acc{{background:{ACC};color:white;font-weight:bold}}
QPushButton#danger{{background:#883333;color:white}}
QCheckBox,QRadioButton{{color:{FG};spacing:6px;font:10pt 'Segoe UI'}}
QCheckBox::indicator,QRadioButton::indicator{{width:16px;height:16px;background:{PBG3};border:1px solid #555;border-radius:3px}}
QCheckBox::indicator:checked{{background:{ACC};border-color:{ACC}}}
QRadioButton::indicator{{border-radius:8px}} QRadioButton::indicator:checked{{background:{ACC};border-color:{ACC}}}
QComboBox::drop-down{{border:none;width:18px}}
QComboBox QAbstractItemView{{background:{PBG2};color:{FG};selection-background-color:{ACC};font:10pt 'Segoe UI'}}
QListWidget{{background:#1a1a2e;color:{FG};border:none;font:10pt 'Segoe UI'}}
QListWidget::item{{padding:4px 6px}}
QListWidget::item:selected{{background:{ACC}}}
QTableWidget{{background:#1a1a2e;color:{FG};gridline-color:#444;font:10pt 'Segoe UI'}}
QTableWidget::item:selected{{background:{ACC}}}
QHeaderView::section{{background:{PBG2};color:{FG};padding:4px;border:none;font:10pt 'Segoe UI'}}
QScrollBar:vertical{{background:{PBG};width:10px}} QScrollBar::handle:vertical{{background:#444;border-radius:5px;min-height:25px}}
QScrollBar:horizontal{{background:{PBG};height:10px}} QScrollBar::handle:horizontal{{background:#444;border-radius:5px;min-width:25px}}
QGroupBox{{border:1px solid #333;border-radius:4px;margin-top:10px;padding-top:8px;color:{FGD};font:bold 10pt 'Segoe UI'}}
QGroupBox::title{{subcontrol-origin:margin;padding:0 6px}}
QStatusBar{{background:#131320;color:{FGD};font:9pt 'Segoe UI'}}
QSlider::groove:horizontal{{background:{PBG3};height:5px;border-radius:2px}}
QSlider::handle:horizontal{{background:{ACC};width:16px;height:16px;border-radius:8px;margin:-5px 0}}
QTextBrowser{{font:10pt 'Segoe UI';background:{PBG};color:{FG}}}
"""
A4W,A4H=210.0,297.0

# ── Color utilities ────────────────────────────────────────────────────────────

def _to_qc(c) -> QColor:
    if not c: return QColor(0,0,0,255)
    t=tuple(int(v) for v in c)
    return QColor(t[0],t[1],t[2],t[3] if len(t)>=4 else 255)

def _cswatch(c) -> str:
    q=_to_qc(c)
    return f"background:rgba({q.red()},{q.green()},{q.blue()},{q.alpha()});border:1px solid #777;border-radius:3px"


# ═══════════════════════════════════════════════════════════════════════════════
#  Custom Color Dialog with hex + alpha slider
# ═══════════════════════════════════════════════════════════════════════════════

class _SVField(QWidget):
    """Saturation (x) / Value (y) square for the current hue."""
    picked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(210, 170)
        self._h = 0.0; self._s = 1.0; self._v = 1.0
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_hsv(self, h, s, v):
        self._h = h; self._s = s; self._v = v; self.update()

    def paintEvent(self, e):
        from PyQt6.QtGui import QLinearGradient
        p = QPainter(self); r = self.rect()
        hue = QColor.fromHsvF(max(0.0, min(0.99999, self._h)), 1.0, 1.0)
        g1 = QLinearGradient(float(r.left()), float(r.top()), float(r.right()), float(r.top()))
        g1.setColorAt(0.0, QColor(255, 255, 255)); g1.setColorAt(1.0, hue)
        p.fillRect(r, QBrush(g1))
        g2 = QLinearGradient(float(r.left()), float(r.top()), float(r.left()), float(r.bottom()))
        g2.setColorAt(0.0, QColor(0, 0, 0, 0)); g2.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(r, QBrush(g2))
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        x = self._s * r.width(); y = (1.0 - self._v) * r.height()
        p.setPen(QPen(QColor(0, 0, 0), 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x, y), 5.5, 5.5)
        p.setPen(QPen(QColor(255, 255, 255), 1)); p.drawEllipse(QPointF(x, y), 6.5, 6.5)

    def _emit(self, pos):
        w = max(1, self.width()); h = max(1, self.height())
        self._s = min(1.0, max(0.0, pos.x() / w))
        self._v = min(1.0, max(0.0, 1.0 - pos.y() / h))
        self.update(); self.picked.emit(self._s, self._v)

    def mousePressEvent(self, e): self._emit(e.position())
    def mouseMoveEvent(self, e):
        if e.buttons(): self._emit(e.position())


class _HueBar(QWidget):
    picked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(20); self.setMinimumHeight(170); self._h = 0.0

    def set_hue(self, h): self._h = h; self.update()

    def paintEvent(self, e):
        from PyQt6.QtGui import QLinearGradient
        p = QPainter(self); r = self.rect()
        g = QLinearGradient(float(r.left()), float(r.top()), float(r.left()), float(r.bottom()))
        for i in range(7):
            g.setColorAt(i / 6.0, QColor.fromHsvF((i / 6.0) % 1.0, 1.0, 1.0))
        p.fillRect(r, QBrush(g))
        y = int(self._h * r.height())
        p.setPen(QPen(QColor(0, 0, 0), 3)); p.drawLine(0, y, r.width(), y)
        p.setPen(QPen(QColor(255, 255, 255), 1)); p.drawLine(0, y, r.width(), y)

    def _emit(self, pos):
        self._h = min(0.99999, max(0.0, pos.y() / max(1, self.height())))
        self.update(); self.picked.emit(self._h)

    def mousePressEvent(self, e): self._emit(e.position())
    def mouseMoveEvent(self, e):
        if e.buttons(): self._emit(e.position())


class _AlphaBar(QWidget):
    picked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(20); self.setMinimumHeight(170); self._a = 255; self._rgb = (0, 0, 0)

    def set_color(self, r, g, b, a): self._rgb = (r, g, b); self._a = a; self.update()

    def paintEvent(self, e):
        from PyQt6.QtGui import QLinearGradient
        p = QPainter(self); r = self.rect(); sz = 6
        for yy in range(0, r.height(), sz):
            for xx in range(0, r.width(), sz):
                c = QColor(205, 205, 210) if ((xx // sz + yy // sz) % 2 == 0) else QColor(150, 150, 158)
                p.fillRect(xx, yy, sz, sz, c)
        rr, gg, bb = self._rgb
        g = QLinearGradient(float(r.left()), float(r.top()), float(r.left()), float(r.bottom()))
        g.setColorAt(0.0, QColor(rr, gg, bb, 255)); g.setColorAt(1.0, QColor(rr, gg, bb, 0))
        p.fillRect(r, QBrush(g))
        y = int((1.0 - self._a / 255.0) * r.height())
        p.setPen(QPen(QColor(0, 0, 0), 3)); p.drawLine(0, y, r.width(), y)
        p.setPen(QPen(QColor(255, 255, 255), 1)); p.drawLine(0, y, r.width(), y)

    def _emit(self, pos):
        self._a = int(round((1.0 - min(1.0, max(0.0, pos.y() / max(1, self.height())))) * 255))
        self.update(); self.picked.emit(self._a)

    def mousePressEvent(self, e): self._emit(e.position())
    def mouseMoveEvent(self, e):
        if e.buttons(): self._emit(e.position())


class _EyedropOverlay(QDialog):
    """Fullscreen modal screenshot overlay: move to preview (loupe + swatch),
    left-click to sample, right-click / Esc to cancel."""

    def __init__(self):
        super().__init__(None)
        from PyQt6.QtWidgets import QApplication
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.BypassWindowManagerHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        scr = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self._scr = scr
        self._shot = scr.grabWindow(0)
        self._img = self._shot.toImage()
        self._dpr = self._shot.devicePixelRatio() or 1.0
        self._rgb = None
        self._pos = None        # last logical cursor pos within overlay
        self._cur = (0, 0, 0)
        self.setGeometry(scr.geometry())
        self.setMouseTracking(True)
        cur = _custom_cursor('eyedropper')
        self.setCursor(cur if cur is not None else QCursor(Qt.CursorShape.CrossCursor))

    def showEvent(self, e):
        super().showEvent(e)
        self.activateWindow(); self.raise_()
        cur = _custom_cursor('eyedropper')
        self.grabMouse(cur if cur is not None else QCursor(Qt.CursorShape.CrossCursor))

    def _devpt(self, lx, ly):
        ox = self._scr.geometry().x(); oy = self._scr.geometry().y()
        x = int((lx - ox) * self._dpr); y = int((ly - oy) * self._dpr)
        return (max(0, min(self._img.width() - 1, x)),
                max(0, min(self._img.height() - 1, y)))

    def _sample(self, gx, gy):
        x, y = self._devpt(gx, gy)
        return self._img.pixelColor(x, y)

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._shot)
        if self._pos is None:
            return
        from PyQt6.QtCore import QRect
        lx, ly = self._pos.x(), self._pos.y()
        dx, dy = self._devpt(lx, ly)
        # loupe: zoom an N×N device-pixel region around the cursor
        N = 13; Z = 9; side = N * Z
        src = self._img.copy(QRect(dx - N // 2, dy - N // 2, N, N))
        loupe = src.scaled(side, side, Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.FastTransformation)
        ox = lx + 22; oy = ly + 22
        if ox + side + 14 > self.width():
            ox = lx - side - 22
        if oy + side + 40 > self.height():
            oy = ly - side - 40
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(ox - 2, oy - 2, side + 4, side + 4, QColor(20, 20, 24))
        p.drawImage(ox, oy, loupe)
        # centre pixel marker
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawRect(ox + (N // 2) * Z, oy + (N // 2) * Z, Z, Z)
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.drawRect(ox - 1, oy - 1, side + 2, side + 2)
        # swatch + hex below the loupe
        r, g, b = self._cur
        p.fillRect(ox, oy + side + 2, side, 22, QColor(r, g, b))
        p.fillRect(ox, oy + side + 24, side, 16, QColor(20, 20, 24))
        p.setPen(QColor(235, 235, 240))
        p.drawText(QRect(ox, oy + side + 24, side, 16), Qt.AlignmentFlag.AlignCenter,
                   "#%02X%02X%02X" % (r, g, b))

    def mouseMoveEvent(self, e):
        gp = e.globalPosition().toPoint()
        self._pos = self.mapFromGlobal(gp)
        c = self._sample(gp.x(), gp.y())
        self._cur = (c.red(), c.green(), c.blue())
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.releaseMouse(); self.reject(); return
        c = self._sample(e.globalPosition().toPoint().x(), e.globalPosition().toPoint().y())
        self._rgb = (c.red(), c.green(), c.blue())
        self.releaseMouse(); self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.releaseMouse(); self.reject()


class EdofColorDialog(QDialog):
    """Photoshop-style colour picker: SV square + hue strip (+ alpha strip) with
    HSB / RGB / hex fields, all kept in sync."""

    def __init__(self, initial=(0, 0, 0, 255), parent=None, alpha=True):
        super().__init__(parent)
        from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGridLayout,
                                     QLabel, QSpinBox, QLineEdit)
        import colorsys
        self.setWindowTitle("Color"); self.setStyleSheet(QSS)
        self.setMinimumWidth(340)
        self._alpha_enabled = alpha
        c = list(initial[:4]) if len(initial) >= 4 else [*initial[:3], 255]
        self._color = c
        self._on_change = None
        h, s, v = colorsys.rgb_to_hsv(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)
        self._h, self._s, self._v = h, s, v
        self._upd = False

        vb = QVBoxLayout(self); vb.setContentsMargins(12, 12, 12, 12); vb.setSpacing(8)

        top = QHBoxLayout(); top.setSpacing(8)
        self._sv = _SVField(); self._sv.set_hsv(h, s, v)
        self._hb = _HueBar(); self._hb.set_hue(h)
        top.addWidget(self._sv, 1); top.addWidget(self._hb)
        if alpha:
            self._ab = _AlphaBar(); self._ab.set_color(c[0], c[1], c[2], c[3])
            top.addWidget(self._ab)
        else:
            self._ab = None
        vb.addLayout(top)

        # new / current swatches
        sw = QHBoxLayout(); sw.setSpacing(0)
        self._new_sw = QLabel(); self._new_sw.setFixedHeight(24)
        self._cur_sw = QLabel(); self._cur_sw.setFixedHeight(24)
        self._cur_sw.setStyleSheet(
            f"background:rgba({c[0]},{c[1]},{c[2]},{c[3]/255.0});border:1px solid #777;")
        sw.addWidget(self._new_sw); sw.addWidget(self._cur_sw)
        vb.addLayout(sw)

        def _spinbox(mx):
            sp = QSpinBox(); sp.setRange(0, mx)
            sp.setMinimumWidth(84); sp.setMinimumHeight(24)
            sp.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
            return sp
        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(5)
        self._spH = _spinbox(360); self._spS = _spinbox(100); self._spB = _spinbox(100)
        self._spR = _spinbox(255); self._spG = _spinbox(255); self._spBl = _spinbox(255)
        grid.addWidget(QLabel("H"), 0, 0); grid.addWidget(self._spH, 0, 1)
        grid.addWidget(QLabel("S"), 1, 0); grid.addWidget(self._spS, 1, 1)
        grid.addWidget(QLabel("B"), 2, 0); grid.addWidget(self._spB, 2, 1)
        grid.addWidget(QLabel("R"), 0, 2); grid.addWidget(self._spR, 0, 3)
        grid.addWidget(QLabel("G"), 1, 2); grid.addWidget(self._spG, 1, 3)
        grid.addWidget(QLabel("B "), 2, 2); grid.addWidget(self._spBl, 2, 3)
        grid.addWidget(QLabel("#"), 3, 0)
        self._hex = QLineEdit(); self._hex.setMaxLength(9); self._hex.setMinimumWidth(110)
        grid.addWidget(self._hex, 3, 1)
        if alpha:
            self._spA = _spinbox(255)
            grid.addWidget(QLabel("A"), 3, 2); grid.addWidget(self._spA, 3, 3)
        else:
            self._spA = None
        grid.setColumnStretch(1, 1); grid.setColumnStretch(3, 1)
        vb.addLayout(grid)

        from PyQt6.QtWidgets import QPushButton as _QPB
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        self._btn_eye = _QPB("🖉 Pick from screen")
        self._btn_eye.setToolTip("Eyedropper: click anywhere on screen to sample a colour")
        self._btn_eye.clicked.connect(self._eyedrop)
        bb.addButton(self._btn_eye, QDialogButtonBox.ButtonRole.ActionRole)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        vb.addWidget(bb)

        # wiring
        self._sv.picked.connect(self._on_sv)
        self._hb.picked.connect(self._on_hue)
        if self._ab: self._ab.picked.connect(self._on_alpha)
        self._spH.valueChanged.connect(self._on_hsb)
        self._spS.valueChanged.connect(self._on_hsb)
        self._spB.valueChanged.connect(self._on_hsb)
        self._spR.valueChanged.connect(self._on_rgb)
        self._spG.valueChanged.connect(self._on_rgb)
        self._spBl.valueChanged.connect(self._on_rgb)
        if self._spA: self._spA.valueChanged.connect(self._on_alpha_spin)
        self._hex.editingFinished.connect(self._on_hex)
        self._apply()

    def _on_sv(self, s, v):
        self._s, self._v = s, v; self._apply()

    def _on_hue(self, h):
        self._h = h; self._apply()

    def _on_alpha(self, a):
        self._color[3] = a; self._apply()

    def _on_alpha_spin(self, a):
        if self._upd: return
        self._color[3] = a; self._apply()

    def _on_hsb(self, _=0):
        if self._upd: return
        self._h = self._spH.value() / 360.0
        self._s = self._spS.value() / 100.0
        self._v = self._spB.value() / 100.0
        self._apply()

    def _on_rgb(self, _=0):
        if self._upd: return
        import colorsys
        r = self._spR.value() / 255.0; g = self._spG.value() / 255.0; b = self._spBl.value() / 255.0
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r, g, b)
        self._apply()

    def _on_hex(self):
        h = self._hex.text().strip().lstrip("#")
        try:
            if len(h) == 6:
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16); a = self._color[3]
            elif len(h) == 8:
                r, g, b, a = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
            else:
                return
        except ValueError:
            return
        import colorsys
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        self._color[3] = a
        self._apply()

    def _apply(self):
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(self._h, self._s, self._v)
        R, G, B = int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
        A = self._color[3]
        self._color = [R, G, B, A]
        self._upd = True
        self._sv.set_hsv(self._h, self._s, self._v)
        self._hb.set_hue(self._h)
        if self._ab: self._ab.set_color(R, G, B, A)
        self._new_sw.setStyleSheet(
            f"background:rgba({R},{G},{B},{A/255.0});border:1px solid #777;")
        self._spH.setValue(int(round(self._h * 360)))
        self._spS.setValue(int(round(self._s * 100)))
        self._spB.setValue(int(round(self._v * 100)))
        self._spR.setValue(R); self._spG.setValue(G); self._spBl.setValue(B)
        if self._spA: self._spA.setValue(A)
        if self._alpha_enabled:
            self._hex.setText("#%02x%02x%02x%02x" % (R, G, B, A))
        else:
            self._hex.setText("#%02x%02x%02x" % (R, G, B))
        self._upd = False
        if self._on_change:
            try:
                self._on_change(tuple(self._color))
            except Exception:
                pass

    def _eyedrop(self):
        ov = _EyedropOverlay()
        if ov.exec() == QDialog.DialogCode.Accepted and ov._rgb:
            self._on_eyedrop(*ov._rgb)

    def _on_eyedrop(self, r, g, b):
        import colorsys
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        self._apply()

    def color(self) -> tuple:
        return tuple(self._color)

    @staticmethod
    def get_color(parent, initial=(0, 0, 0, 255), alpha=True, on_change=None):
        dlg = EdofColorDialog(initial, parent, alpha)
        dlg._on_change = on_change
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.color()
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Async render signal helper
# ═══════════════════════════════════════════════════════════════════════════════

class _RenderSignals(QObject):
    done = pyqtSignal(bytes, int)   # (png_bytes, render_id)

_render_signals = _RenderSignals()
_render_id = 0


# ═══════════════════════════════════════════════════════════════════════════════
#  SelectionOverlay
# ═══════════════════════════════════════════════════════════════════════════════

# ── v4.2.7.2: custom tool cursors (loaded from bundled cursors.json) ──────────
_CURSOR_CACHE = {}


def _zoom_cursor():
    """A plain magnifier cursor (no +/- sign) used while Alt is held over the
    page, to signal that the wheel will zoom."""
    c = _CURSOR_CACHE.get('zoom_plain')
    if c is not None:
        return c
    try:
        s = 28
        pm = QPixmap(s, s); pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy, r = 11, 11, 8
        # lens (white halo + dark ring so it shows on any background)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255), 3)); p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
        p.setPen(QPen(QColor(30, 30, 30), 1.6)); p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
        # handle
        hx0, hy0, hx1, hy1 = int(cx + r * 0.7), int(cy + r * 0.7), 25, 25
        p.setPen(QPen(QColor(255, 255, 255), 4)); p.drawLine(hx0, hy0, hx1, hy1)
        p.setPen(QPen(QColor(30, 30, 30), 2)); p.drawLine(hx0, hy0, hx1, hy1)
        p.end()
        c = QCursor(pm, cx, cy)
    except Exception:
        c = QCursor(Qt.CursorShape.CrossCursor)
    _CURSOR_CACHE['zoom_plain'] = c
    return c
_CURSOR_SHEET = None

def _load_cursor_sheet():
    global _CURSOR_SHEET
    if _CURSOR_SHEET is not None:
        return _CURSOR_SHEET
    _CURSOR_SHEET = {}
    try:
        import json as _json
        from edof._apps.assets import cursor_path
        p = cursor_path("cursors.json")
        if p:
            with open(p, encoding="utf-8") as fh:
                for c in _json.load(fh).get("cursors", []):
                    _CURSOR_SHEET[c.get("name")] = c
    except Exception:
        pass
    return _CURSOR_SHEET

def _custom_cursor(name):
    """Return a QCursor built from the bundled PNG + hotspot, or None."""
    if name in _CURSOR_CACHE:
        return _CURSOR_CACHE[name]
    qc = None
    try:
        from edof._apps.assets import cursor_path
        sheet = _load_cursor_sheet()
        meta = sheet.get(name, {})
        fname = meta.get("file", "cur-%s.png" % name)
        path = cursor_path(fname)
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                hs = meta.get("hotspot") or [pm.width() // 2, pm.height() // 2]
                hx, hy = int(hs[0]), int(hs[1])
                target = 24                              # 32px art renders too big
                if pm.width() > target:
                    f = target / float(pm.width())
                    pm = pm.scaled(target, max(1, int(round(pm.height() * f))),
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                    hx = int(round(hx * f)); hy = int(round(hy * f))
                qc = QCursor(pm, hx, hy)
    except Exception:
        qc = None
    _CURSOR_CACHE[name] = qc
    return qc

def tcur(name, fallback=Qt.CursorShape.ArrowCursor):
    """Custom QCursor for `name`, falling back to a Qt cursor shape."""
    return _custom_cursor(name) or QCursor(fallback)


_UICON_CACHE = {}

def _ht_file_to_b64(path):
    """Load an image file and return it as a base64 PNG string (or None)."""
    import base64, io
    from PIL import Image as _Img
    try:
        im = _Img.open(path).convert("RGBA")
        buf = io.BytesIO(); im.save(buf, 'PNG')
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _ht_b64_pixmap(b64, size=30):
    """QPixmap thumbnail for a base64 PNG pattern (or None)."""
    import base64
    if not b64:
        return None
    try:
        raw = base64.b64decode(b64)
        pm = QPixmap()
        if pm.loadFromData(raw) and not pm.isNull():
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    return None


def _menu_icon_style(menu, px):
    """Enlarge QMenu action icons. QMenu has no setIconSize in Qt6, so we attach
    a QProxyStyle overriding PM_SmallIconSize. The no-arg QProxyStyle wraps the
    application default style WITHOUT taking ownership (passing a concrete style
    would transfer ownership of the shared app style and crash on teardown). The
    style is parented to the menu so its lifetime is tied to it; setStyle does
    not take ownership."""
    from PyQt6.QtWidgets import QProxyStyle, QStyle

    class _IconStyle(QProxyStyle):
        def pixelMetric(self, metric, option=None, widget=None):
            if metric == QStyle.PixelMetric.PM_SmallIconSize:
                return px
            return super().pixelMetric(metric, option, widget)

    st = _IconStyle()
    st.setParent(menu)
    return st


def _ht_lib_get():
    from PyQt6.QtCore import QSettings
    v = QSettings("EDOF", "editor").value("halftone/pattern_library", [])
    return [x for x in (v or []) if isinstance(x, str) and x]


def _ht_lib_add(b64):
    from PyQt6.QtCore import QSettings
    if not b64:
        return
    s = QSettings("EDOF", "editor")
    lst = [x for x in (s.value("halftone/pattern_library", []) or []) if isinstance(x, str) and x]
    if b64 in lst:
        lst.remove(b64)
    lst.insert(0, b64)
    s.setValue("halftone/pattern_library", lst[:24])


def uicon(name, tint=None):
    """QIcon for a bundled UI icon ('save', 'rect', ...), keeping the original
    (colour) artwork. `tint` can recolour it via SourceIn if ever needed.
    Returns a (possibly null) QIcon."""
    key = (name, tint)
    if key in _UICON_CACHE:
        return _UICON_CACHE[key]
    ic = QIcon()
    try:
        from edof._apps.assets import ui_icon_path
        p = ui_icon_path("ic-%s.png" % name)
        if p:
            pm = QPixmap(p)
            if not pm.isNull():
                if tint is not None:
                    tinted = QPixmap(pm.size())
                    tinted.fill(Qt.GlobalColor.transparent)
                    pt = QPainter(tinted)
                    pt.drawPixmap(0, 0, pm)
                    pt.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                    pt.fillRect(tinted.rect(), QColor(*tint))
                    pt.end()
                    pm = tinted
                ic = QIcon(pm)
    except Exception:
        ic = QIcon()
    _UICON_CACHE[key] = ic
    return ic


def _key_name(k):
    """Human-readable Qt key name for debug logs."""
    try:
        return Qt.Key(k).name
    except Exception:
        return str(k)


def _mods_str(m):
    """Human-readable keyboard-modifier string for debug logs."""
    try:
        M = Qt.KeyboardModifier
        out = []
        if m & M.ControlModifier: out.append('Ctrl')
        if m & M.ShiftModifier:   out.append('Shift')
        if m & M.AltModifier:     out.append('Alt')
        if m & M.MetaModifier:    out.append('Meta')
        return '+'.join(out) or 'none'
    except Exception:
        return '?'


class SelectionOverlay(QGraphicsItem):
    _ANCHOR={'TL':(1,1),'TC':(.5,1),'TR':(0,1),'ML':(1,.5),'MR':(0,.5),
             'BL':(1,0),'BC':(.5,0),'BR':(0,0)}
    _SIGN={'TL':(-1,-1),'TC':(0,-1),'TR':(1,-1),'ML':(-1,0),'MR':(1,0),
           'BL':(-1,1),'BC':(0,1),'BR':(1,1)}
    _CUR={'TL':Qt.CursorShape.SizeFDiagCursor,'TC':Qt.CursorShape.SizeVerCursor,
          'TR':Qt.CursorShape.SizeBDiagCursor,'ML':Qt.CursorShape.SizeHorCursor,
          'MR':Qt.CursorShape.SizeHorCursor,'BL':Qt.CursorShape.SizeBDiagCursor,
          'BC':Qt.CursorShape.SizeVerCursor,'BR':Qt.CursorShape.SizeFDiagCursor,
          'ROT':Qt.CursorShape.CrossCursor,'P1':Qt.CursorShape.CrossCursor,
          'P2':Qt.CursorShape.CrossCursor}

    def __init__(self):
        super().__init__(); self.setZValue(9999)
        self._handles={}; self._poly=QPolygonF(); self._tc_pt=QPointF()
        self._is_line=False; self._lp1=QPointF(); self._lp2=QPointF()

    def _view_zoom(self):
        """Current view zoom (scene->viewport scale). Handles are sized in
        scene units, so dividing by this keeps them a constant on-screen size
        at any zoom. HiDPI is handled by Qt rendering the vectors at the
        display's device pixel ratio."""
        try:
            vs = self.scene().views()
            if vs:
                z = vs[0].transform().m11()
                if z > 1e-6:
                    return float(z)
        except Exception:
            pass
        return 1.0

    def update_for(self, obj, dpi):
        self._handles.clear(); self._is_line=False
        if obj is None: self.prepareGeometryChange(); return

        # v4.1.20.9: document-body textbox is a fixed page-spanning region —
        # not a user-shaped object. Hide all resize / rotate handles for it
        # so the only interaction is inline edit. The selection rectangle
        # is still drawn (dashed border, no handles) so it's clear the
        # textbox is selected.
        is_doc_body = False
        try:
            name = getattr(obj, 'name', '') or ''
            if name in ('document_body', 'doc_body') or name.startswith('doc_body'):
                is_doc_body = True
        except Exception:
            pass

        from edof.format.objects import Shape, SHAPE_LINE
        if isinstance(obj,Shape) and obj.shape_type==SHAPE_LINE and obj.points and len(obj.points)>=2:
            self._is_line=True
            p1,p2=obj.points[0],obj.points[1]
            self._lp1=QPointF(mm_to_px(p1[0],dpi),mm_to_px(p1[1],dpi))
            self._lp2=QPointF(mm_to_px(p2[0],dpi),mm_to_px(p2[1],dpi))
            self._handles={'P1':self._lp1,'P2':self._lp2}
            self.prepareGeometryChange(); return

        t=obj.transform; cx=t.x+t.width/2; cy=t.y+t.height/2
        def rs(mx,my):
            rx,ry=rotate_point(mx,my,cx,cy,t.rotation)
            return QPointF(mm_to_px(rx,dpi),mm_to_px(ry,dpi))
        if is_doc_body:
            # Only outline polygon, no handles
            pts4 = [(t.x,t.y),(t.x+t.width,t.y),(t.x+t.width,t.y+t.height),(t.x,t.y+t.height)]
            self._poly = QPolygonF([rs(*p) for p in pts4])
            # Mark as "body" so paint can draw outline-only.
            self._handles = {'_body_outline': QPointF(0,0)}
            self._tc_pt = rs(t.x+t.width/2, t.y)
            self.prepareGeometryChange(); return

        pts={'TL':(t.x,t.y),'TC':(t.x+t.width/2,t.y),'TR':(t.x+t.width,t.y),
             'ML':(t.x,t.y+t.height/2),'MR':(t.x+t.width,t.y+t.height/2),
             'BL':(t.x,t.y+t.height),'BC':(t.x+t.width/2,t.y+t.height),
             'BR':(t.x+t.width,t.y+t.height)}
        for k,(mx,my) in pts.items(): self._handles[k]=rs(mx,my)
        rad=math.radians(t.rotation); tc=self._handles['TC']
        rdist=ROT_DIST/self._view_zoom()   # constant on-screen rotate distance
        self._handles['ROT']=QPointF(tc.x()+rdist*math.sin(rad),
                                      tc.y()-rdist*math.cos(rad))
        self._tc_pt=tc
        self._poly=QPolygonF([rs(*pts['TL']),rs(*pts['TR']),rs(*pts['BR']),rs(*pts['BL'])])
        self.prepareGeometryChange()

    def hit_handle(self, sp):
        HIT=(HSIZE+6)/self._view_zoom()
        for k,pt in self._handles.items():
            if abs(sp.x()-pt.x())<=HIT and abs(sp.y()-pt.y())<=HIT: return k
        return None

    _CUR_NAME={'TL':'resize_nwse','TC':'resize_ns','TR':'resize_nesw',
               'ML':'resize_ew','MR':'resize_ew','BL':'resize_nesw',
               'BC':'resize_ns','BR':'resize_nwse','ROT':'rotate',
               'P1':'tangent','P2':'tangent'}
    def cursor_for(self, h): return tcur(self._CUR_NAME.get(h,''), self._CUR.get(h,Qt.CursorShape.ArrowCursor))
    def boundingRect(self): return QRectF(-9999,-9999,19998,19998)

    def paint(self, p, opt, widget):
        if not self._handles: return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z = self._view_zoom()
        hs = HSIZE / z                      # handle half-size, constant on screen
        def _pen(color, w, style=Qt.PenStyle.SolidLine, dash=None):
            pen = QPen(QColor(color), float(w), style)
            pen.setCosmetic(True)           # width/dash in screen px, HiDPI-aware
            if dash is not None: pen.setDashPattern(dash)
            return pen
        if self._is_line:
            p.setPen(_pen(ACC, 2, Qt.PenStyle.DashLine)); p.drawLine(self._lp1,self._lp2)
            for pt in (self._lp1,self._lp2):
                r=QRectF(pt.x()-hs,pt.y()-hs,hs*2,hs*2)
                p.setPen(_pen(ACC, 2)); p.setBrush(QBrush(QColor("white"))); p.drawEllipse(r)
            return
        # v4.1.20.9: document-body outline mode — dashed bbox only, no handles
        if '_body_outline' in self._handles:
            p.setPen(_pen(ACC, 1.5, Qt.PenStyle.DashLine, [4, 3]))
            p.setBrush(Qt.BrushStyle.NoBrush); p.drawPolygon(self._poly)
            return
        p.setPen(_pen(ACC, 2, Qt.PenStyle.DashLine, [5, 3]))
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawPolygon(self._poly)
        rot=self._handles.get('ROT')
        if rot:
            p.setPen(_pen(ACC, 1, Qt.PenStyle.DotLine)); p.drawLine(self._tc_pt,rot)
        for k,pt in self._handles.items():
            r=QRectF(pt.x()-hs,pt.y()-hs,hs*2,hs*2)
            if k=='ROT':
                p.setPen(_pen("white", 2)); p.setBrush(QBrush(QColor(ACC2))); p.drawEllipse(r)
            else:
                p.setPen(_pen(ACC, 2)); p.setBrush(QBrush(QColor("white"))); p.drawRect(r)


# ═══════════════════════════════════════════════════════════════════════════════
#  EdofCanvas  –  QGraphicsView
# ═══════════════════════════════════════════════════════════════════════════════

class _GradientStopsBar(QWidget):
    """Photoshop-style multi-stop gradient editor over t in [0, 1].

    mode 'color': each stop is [t, r, g, b] (double-click a stop = colour
    dialog). mode 'scalar': each stop is [t, v] with v in [0, vmax]
    (double-click = numeric input). Interactions: drag a stop to move it,
    double-click empty space to add a stop (interpolated value), right-click a
    stop to delete it. An empty stop list means 'legacy behaviour' and renders
    as a dashed outline; the small x button clears back to it."""
    changed = pyqtSignal()

    def __init__(self, mode='color', vmax=1.0, suffix='', parent=None):
        super().__init__(parent)
        self._mode = mode; self._vmax = float(vmax); self._suffix = suffix
        self._stops = []          # sorted [t, ...] rows
        self._drag = -1
        self.setMinimumSize(190, 30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Double-click: add / edit stop. Drag: move. Right-click: delete.\n"
                        "Empty = legacy controls (fade / colour / blur mode).")

    # -- data ----------------------------------------------------------------
    def stops(self):
        return [list(s) for s in self._stops]

    def setStops(self, stops):
        self._stops = sorted(([float(x) for x in s] for s in (stops or [])),
                             key=lambda s: s[0])
        self.update()

    def _interp_at(self, t):
        if not self._stops:
            if self._mode == 'color':
                return [0.0, 0.0, 0.0]
            return [self._vmax if self._mode == 'scalar' else 1.0]
        st = self._stops
        if t <= st[0][0]:
            return list(st[0][1:])
        if t >= st[-1][0]:
            return list(st[-1][1:])
        for i in range(len(st) - 1):
            a, b = st[i], st[i + 1]
            if a[0] <= t <= b[0]:
                f = 0.0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
                return [a[1 + k] + (b[1 + k] - a[1 + k]) * f
                        for k in range(len(a) - 1)]
        return list(st[-1][1:])

    # -- geometry ------------------------------------------------------------
    def _bar_rect(self):
        from PyQt6.QtCore import QRect
        return QRect(8, 4, max(40, self.width() - 16), self.height() - 16)

    def _t_at(self, x):
        r = self._bar_rect()
        return max(0.0, min(1.0, (x - r.left()) / max(1.0, float(r.width()))))

    def _x_of(self, t):
        r = self._bar_rect()
        return int(r.left() + t * r.width())

    def _hit(self, pos):
        for i, s in enumerate(self._stops):
            if abs(pos.x() - self._x_of(s[0])) <= 6:
                return i
        return -1

    # -- painting ------------------------------------------------------------
    def paintEvent(self, ev):
        from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QPen, QPolygonF
        from PyQt6.QtCore import QPointF
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._bar_rect()
        if not self._stops:
            pen = QPen(QColor(150, 150, 150)); pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 3, 3)
            p.setPen(QColor(140, 140, 140))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "legacy (click to add stops)")
            p.end(); return
        grad = QLinearGradient(r.left(), 0, r.right(), 0)
        n = 32
        for i in range(n + 1):
            t = i / n
            v = self._interp_at(t)
            if self._mode == 'color':
                col = QColor(int(v[0]), int(v[1]), int(v[2]))
            else:
                g8 = int(255 * (1.0 - max(0.0, min(1.0, v[0] / max(1e-6, self._vmax)))))
                col = QColor(g8, g8, g8)
            grad.setColorAt(t, col)
        p.setPen(QPen(QColor(90, 90, 90))); p.setBrush(grad)
        p.drawRoundedRect(r, 3, 3)
        for i, s in enumerate(self._stops):
            x = self._x_of(s[0]); y = r.bottom() + 1
            tri = QPolygonF([QPointF(x, y), QPointF(x - 5, y + 8), QPointF(x + 5, y + 8)])
            if self._mode == 'color':
                fill = QColor(int(s[1]), int(s[2]), int(s[3]))
            else:
                g8 = int(255 * (1.0 - max(0.0, min(1.0, s[1] / max(1e-6, self._vmax)))))
                fill = QColor(g8, g8, g8)
            p.setBrush(fill)
            p.setPen(QPen(QColor(30, 30, 30) if i != self._drag else QColor(0, 120, 255), 1.4))
            p.drawPolygon(tri)
        p.end()

    # -- interaction ---------------------------------------------------------
    def mousePressEvent(self, ev):
        i = self._hit(ev.position().toPoint())
        if ev.button() == Qt.MouseButton.RightButton:
            if i >= 0:
                del self._stops[i]
                self._drag = -1; self.update(); self.changed.emit()
            return
        self._drag = i
        self.update()

    def mouseMoveEvent(self, ev):
        if self._drag >= 0:
            t = self._t_at(ev.position().x())
            self._stops[self._drag][0] = t
            self._stops.sort(key=lambda s: s[0])
            self._drag = next(idx for idx, s in enumerate(self._stops)
                              if abs(s[0] - t) < 1e-9)
            self.update(); self.changed.emit()

    def mouseReleaseEvent(self, ev):
        self._drag = -1; self.update()

    def mouseDoubleClickEvent(self, ev):
        i = self._hit(ev.position().toPoint())
        t = self._t_at(ev.position().x())
        if i < 0:
            self._stops.append([t] + self._interp_at(t))
            self._stops.sort(key=lambda s: s[0])
            i = next(idx for idx, s in enumerate(self._stops)
                     if abs(s[0] - t) < 1e-9)
        s = self._stops[i]
        if self._mode == 'color':
            init = (int(s[1]), int(s[2]), int(s[3]), 255)
            rgb = None
            try:
                dlg = EdofColorDialog(init, self, alpha=False)
                if dlg.exec():
                    rgb = dlg.color()[:3]
            except Exception:
                rgb = None
            if rgb is None:
                from PyQt6.QtWidgets import QColorDialog
                from PyQt6.QtGui import QColor as _QC
                col = QColorDialog.getColor(_QC(*init[:3]), self)
                if col.isValid():
                    rgb = (col.red(), col.green(), col.blue())
            if rgb is not None:
                s[1], s[2], s[3] = float(rgb[0]), float(rgb[1]), float(rgb[2])
        else:
            from PyQt6.QtWidgets import QInputDialog
            v, ok = QInputDialog.getDouble(self, "Stop value",
                                           f"Value at {int(s[0]*100)}%{self._suffix}:",
                                           float(s[1]), 0.0, self._vmax, 2)
            if ok:
                s[1] = float(v)
        self.update(); self.changed.emit()


class _MmField(QWidget):
    """A slider + number box for a (mm) value, with a user-adjustable maximum
    so there is no hard cap. Exposes value()/setValue() and a valueChanged
    signal, so it is a drop-in replacement for a QDoubleSpinBox."""
    valueChanged = pyqtSignal(float)

    def __init__(self, value=0.0, maximum=100.0, decimals=2, suffix=' mm',
                 minimum=0.0, parent=None):
        super().__init__(parent)
        self._guard = False
        self._dec = decimals
        self._scale = 10 ** decimals
        self._min = float(minimum)
        h = QHBoxLayout(self); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        self._sld = QSlider(Qt.Orientation.Horizontal); self._sld.setMinimumWidth(110)
        self._spin = _QDoubleSpinBox(); self._spin.setDecimals(decimals); self._spin.setSuffix(suffix)
        self._spin.setFixedWidth(94)
        self._spin.setSingleStep(0.1 if suffix.strip() == 'mm' else 1.0)
        self._maxspin = _QDoubleSpinBox(); self._maxspin.setDecimals(0)
        self._maxspin.setRange(1, 100000); self._maxspin.setFixedWidth(72)
        self._maxspin.setPrefix("≤ ")
        self._maxspin.setToolTip("Maximum — raise to go past the default cap")
        self._apply_max(max(float(maximum), float(value), self._min + 1.0))
        self.setValue(float(value))
        h.addWidget(self._sld, 1); h.addWidget(self._spin); h.addWidget(self._maxspin)
        self._sld.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)
        self._maxspin.valueChanged.connect(self._on_maxchange)

    def _apply_max(self, mx):
        mx = float(mx)
        self._maxspin.blockSignals(True); self._maxspin.setValue(mx); self._maxspin.blockSignals(False)
        self._spin.setRange(self._min, mx)
        self._sld.blockSignals(True)
        self._sld.setRange(int(self._min * self._scale), int(mx * self._scale))
        self._sld.blockSignals(False)

    def _on_maxchange(self, mx):
        cur = self._spin.value()
        self._apply_max(max(float(mx), self._min + 1.0))
        self.setValue(min(cur, float(mx)))

    def _on_slider(self, iv):
        if self._guard:
            return
        self._guard = True
        v = iv / self._scale
        self._spin.setValue(v)
        self._guard = False
        self.valueChanged.emit(v)

    def _on_spin(self, v):
        if self._guard:
            return
        self._guard = True
        self._sld.setValue(int(round(v * self._scale)))
        self._guard = False
        self.valueChanged.emit(v)

    def value(self):
        return self._spin.value()

    def setValue(self, v):
        self._guard = True
        self._spin.setValue(float(v))
        self._sld.setValue(int(round(float(v) * self._scale)))
        self._guard = False


class EdofCanvas(QGraphicsView):
    objectSelected=pyqtSignal(object)
    objectChanged=pyqtSignal()
    # v4.1.22.13: emitted whenever _page_idx changes so the main window
    # can keep the side panel's selected row in sync. This covers cases
    # where the canvas moves between pages on its own (cursor hop during
    # idle repaginate, _do_new_page, merge_with_previous, etc.) — without
    # this signal the page list lagged behind the actual canvas state.
    pageChanged=pyqtSignal(int)
    zoomChanged=pyqtSignal(float)   # emitted whenever the view zoom changes

    def __init__(self, parent=None):
        super().__init__(parent)
        # v4.1.18: Hi-DPI screen detection — pick a canvas DPI that gives
        # crisp 1:1 rendering on the user's actual screen. Falls back to
        # 96 (RDPI) when screen info is unavailable (offscreen tests).
        try:
            from PyQt6.QtGui import QGuiApplication
            scr = QGuiApplication.primaryScreen()
            ld = float(scr.logicalDotsPerInch()) if scr else RDPI
            # Cap at 192 dpi — render cost grows quadratically with DPI
            screen_dpi = max(72.0, min(192.0, ld))
        except Exception:
            screen_dpi = float(RDPI)
        self._doc=None; self._page_idx=0; self._dpi=screen_dpi; self._zoom=1.0
        # Remember screen DPI separately so doc.preferred_dpi can override
        self._screen_dpi = screen_dpi
        self._sel_id=None
        # v4.0.1: multi-select and snap-to-grid
        self._multi_sel_ids=set()       # set of additional selected object ids
        self._snap_to_grid=False
        self._snap_size_mm=5.0
        self._show_align_guides=True
        self._align_guide_lines=[]      # transient overlay lines during drag
        # v4.0.3: per-document margins (top, right, bottom, left in mm) + toggle
        self._margins_enabled=False
        self._margins=(15.0, 15.0, 15.0, 15.0)
        # v4.0.3: path drawing tool state
        self._path_drawing=False
        self._path_points=[]            # accumulated points: (x, y, kind) where kind in ('L','C')
        self._path_close=False          # v4.1.0: close path on finish
        self._path_drag_origin=None     # v4.1.0: track drag for bezier control points
        # v4.1.15: rectangle draw mode (e.g. textbox draw-by-drag)
        self._rect_draw_kind = None     # None | "textbox" (extendable to "rect"/"ellipse")
        self._rect_draw_start = None    # scene-space QPointF where drag started
        self._rect_draw_preview = None  # QGraphicsRectItem showing the preview rectangle
        self._rect_draw_callback = None # called with (x_mm,y_mm,w_mm,h_mm) on release
        # v4.1.0/4.1.5/4.1.10: path point edit mode
        self._path_edit_obj_id = None
        self._path_edit_handles = []
        self._path_edit_decorations = []   # v4.1.5: dashed control lines (not draggable)
        self._path_drag_handle = None
        self._path_drag_start = None
        self._path_selected_anchors = set()  # v4.1.10: indexes of selected anchors
        self._lasso_start=None          # start point for lasso selection
        self._lasso_rect_item=None
        self._drag_mode=None; self._drag_sp0=None; self._drag_tf0=None; self._drag_anchor=None
        self._pan_start=None; self._pan_scroll0=None
        self._preview_item=None; self._ghost_items=[]
        # Inline editor (v4.1.15.7: QGraphicsProxyWidget in scene)
        self._inline_widget=None; self._inline_id=None; self._inline_obj=None
        self._inline_border_frame=None
        self._inline_proxy=None

        scene=QGraphicsScene(self); self.setScene(scene)
        self.setBackgroundBrush(QBrush(QColor("#3d3d52")))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag); self.setMouseTracking(True)
        # v4.2.10.11: load toggleable render optimizations (see _load_render_opts).
        self._load_render_opts()
        # v4.1.1: GPU acceleration via QOpenGLWidget viewport (when available).
        # v4.2.10.11: now behind the gl_viewport setting (default on).
        # Falls back to default raster viewport if Qt OpenGL is missing.
        if self._opt_gl_viewport:
            self._apply_gl_viewport(True)

        self._page_item=QGraphicsPixmapItem(); scene.addItem(self._page_item)
        # v4.1.0: ensure smooth pixmap scaling on the page item itself, not just the view
        self._page_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._overlay=SelectionOverlay(); scene.addItem(self._overlay)

        # Async render support
        self._render_id=0; self._render_pending=False
        self._rtimer=QTimer(); self._rtimer.setSingleShot(True)
        self._rtimer.timeout.connect(self._start_render)
        _render_signals.done.connect(self._on_render_done)
        # v4.1.23.21: page pixmap cache for flicker-free, fast page switching.
        # On a page change we show the cached pixmap immediately (no blank /
        # stale frame) and refresh it in the background; neighbouring pages
        # are pre-rendered so the next switch is instant too.
        self._page_px_cache = {}     # pg_idx -> QPixmap
        self._rid_info = {}          # render id -> (pg_idx, display:bool)
        self._prerender_timer = QTimer(); self._prerender_timer.setSingleShot(True)
        self._prerender_timer.timeout.connect(self._prerender_neighbors)
        # v4.1.23.26: format carried across a page transition so continued
        # typing on the new page keeps the size/attributes the caret had,
        # instead of falling back to the body's default size.
        self._carry_pending = None

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)

    # ── Document setup ────────────────────────────────────────────────────────

    def set_document(self,doc,page_idx=0):
        try:
            from edof.engine.debug_log import log as _dlog
            _dlog("canvas.set_document",
                   page=page_idx,
                   pages_total=len(doc.pages) if doc else 0)
        except Exception: pass
        # v4.1.23.21: a different document invalidates the whole pixmap cache.
        if doc is not getattr(self, '_doc', None):
            # v4.2.11.49: the ribbon is present from startup for EVERY
            # document: rebuild a disabled skeleton for the new document so the
            # band is reserved up front and the page never shifts when text
            # editing begins.
            try:
                from PyQt6.QtCore import QTimer as _QT
                _QT.singleShot(0, self._ensure_ribbon_skeleton)
            except Exception:
                pass
            try: self._page_px_cache.clear()
            except Exception: pass
            try:
                from edof.engine.renderer import clear_object_cache
                clear_object_cache()
            except Exception: pass
        self._doc=doc; self._page_idx=page_idx; self._sel_id=None
        # v4.1.18: pick the rendering DPI for the canvas — for print-targeted
        # docs (default_dpi >= 200) the canvas renders at higher resolution
        # so text and shapes are crisp. For screen docs we keep the screen
        # DPI we detected at startup. The zoom level is separate and lets
        # the user scale the on-screen view independently.
        # v4.1.18.1: also consider the current page's dpi override.
        if doc is not None:
            doc_dpi = getattr(doc, 'default_dpi', None) or 0
            page_dpi = 0
            try:
                cur_pg = doc.pages[page_idx] if 0 <= page_idx < len(doc.pages) else None
                if cur_pg: page_dpi = getattr(cur_pg, 'dpi', 0) or 0
            except Exception:
                pass
            target = max(int(doc_dpi), int(page_dpi))
            if target >= 150:
                # Print-targeted: render at half target DPI on the canvas
                # (keeps text legible without quadratic render cost)
                self._dpi = max(self._screen_dpi, min(192.0, float(target) / 2.0))
            else:
                self._dpi = self._screen_dpi
        # v4.1.20.2: commit-not-cancel (see set_page comment)
        if self._inline_widget is not None:
            self._skip_sticky_reentry = True
            try: self._inline_widget.commit_to_textbox()
            except Exception: self._after_inline_commit()
        self._overlay.update_for(None,self._dpi)
        # v4.1.23.21: instant flicker-free hop using the cached pixmap.
        try:
            cached = self._page_px_cache.get(page_idx)
            if cached is not None:
                cpx, cscale = cached if isinstance(cached, tuple) else (cached, 1.0)
                self._apply_page_pixmap(cpx, cscale)
        except Exception: pass
        self._start_render(); self.objectSelected.emit(None)
        try: self.pageChanged.emit(page_idx)
        except Exception: pass

    def set_page(self,idx,move_cursor=True):
        prev_idx = self._page_idx
        try:
            from edof.engine.debug_log import log as _dlog
            _dlog("canvas.set_page", prev=prev_idx, new=idx,
                   total_pages=len(self._doc.pages) if self._doc else 0)
        except Exception: pass
        self._page_idx=idx; self._sel_id=None
        # v4.1.20.2: commit (not cancel) any active inline edit before
        # switching pages — cancel rolls back via snapshot and the user
        # would lose anything they just typed. Suppress sticky reentry so
        # we don't get yanked back into the body of the old page after
        # commit completes.
        if self._inline_widget is not None:
            self._skip_sticky_reentry = True
            try: self._inline_widget.commit_to_textbox()
            except Exception: self._after_inline_commit()
        self._overlay.update_for(None,self._dpi)
        # v4.1.23.21: show the cached pixmap for the target page instantly so
        # the switch is flicker-free; the background render then refreshes it.
        cached = self._page_px_cache.get(idx)
        if cached is not None:
            try:
                cpx, cscale = cached if isinstance(cached, tuple) else (cached, 1.0)
                self._apply_page_pixmap(cpx, cscale)
            except Exception: pass
        self._start_render(); self.objectSelected.emit(None)
        # v4.1.23.21: Ctrl+click on a page only VIEWS it — the caret is left
        # where it was, so the user can glance at another page without losing
        # their editing position. A plain click moves the caret onto the page.
        if (move_cursor
            and self._doc is not None
            and getattr(self._doc, 'mode', '') == 'document'
            and 0 <= idx < len(self._doc.pages)):
            new_pg = self._doc.pages[idx]
            body = None
            for obj in new_pg.objects:
                name = getattr(obj, 'name', '') or ''
                if name in ('document_body', 'doc_body') or name.startswith('doc_body'):
                    body = obj; break
            if body is not None:
                from PyQt6.QtCore import QTimer as _IFT
                def _enter(b=body):
                    self.set_sel_id(b.id)
                    self._start_inline(b)
                    # v4.1.23.21: land the caret at the START of the freshly
                    # selected page. Defaulting to the end would put it on the
                    # page boundary (which maps to the next page) and make the
                    # view jump onward — exactly the "clicking a page sends me
                    # back" bug.
                    if self._inline_widget is not None:
                        try:
                            self._inline_widget._cursor = 0
                            self._inline_widget._anchor = None
                            self._inline_widget._invalidate()
                        except Exception: pass
                _IFT.singleShot(80, _enter)
        # v4.1.22.13: tell the main window the active page changed so the
        # left panel highlights the right row.
        if prev_idx != idx:
            try: self.pageChanged.emit(idx)
            except Exception: pass

    def schedule_render(self,ms=80):
        # v4.1.15.1: Don't reset the timer if it's already pending to fire
        # sooner than `ms`. Without this, rapidly-repeated schedule_render
        # calls during drag (every mouse-move) keep pushing the deadline
        # forward and the render never actually runs until release.
        if self._rtimer.isActive() and self._rtimer.remainingTime() <= ms:
            return
        self._rtimer.start(ms)

    def schedule_render_interactive(self, ms=30):
        """v4.2.10.0: live-preview render used while a value is being tuned
        (effect sliders, opacity, etc.). Renders low-res for responsiveness,
        then a full-quality render once edits settle (~0.35s idle)."""
        self._interacting = True
        self.schedule_render(ms)
        try:
            if getattr(self, '_interact_idle', None) is None:
                self._interact_idle = QTimer(); self._interact_idle.setSingleShot(True)
                self._interact_idle.timeout.connect(self._finish_interaction)
            self._interact_idle.start(350)
        except Exception:
            pass

    def _finish_interaction(self):
        self._interacting = False
        self.schedule_render(0)

    # ── Async rendering ───────────────────────────────────────────────────────

    def _start_render(self):
        if not self._doc or not self._doc.pages: return
        self._render_page_async(self._page_idx, display=True)
        # Pre-render neighbours a moment later so quick page switches are
        # instant and flicker-free.
        try: self._prerender_timer.start(120)
        except Exception: pass

    def _load_render_opts(self):
        """v4.2.10.11: load toggleable render optimizations from QSettings.
        All default ON. These gate the interactive render path; the idle
        full-quality render and export are unaffected by cache/dirty-region
        flags (they always produce exact output)."""
        from PyQt6.QtCore import QSettings
        s = QSettings("edof", "editor")
        def _b(key, default=True):
            return bool(s.value("render/" + key, default, type=bool))
        self._opt_object_cache       = _b("object_cache")
        self._opt_dirty_region       = _b("dirty_region")
        self._opt_adaptive_dpi       = _b("adaptive_dpi")
        self._opt_supersample        = _b("supersample")
        self._opt_lowres_interaction = _b("lowres_interaction")
        self._opt_gl_viewport        = _b("gl_viewport")
        # v4.2.11.2: GPU effects (shader blur for shadow/glow). Default OFF until
        # the user opts in; the renderer falls back to CPU whenever GPU is off or
        # unavailable, so this only ever accelerates, never changes output.
        self._opt_gpu_effects        = _b("gpu_effects", False)
        try:
            from edof.engine import gpu as _gpu
            _gpu.set_enabled(self._opt_gpu_effects)
        except Exception:
            pass

    def set_render_opt(self, key, value):
        """Set one optimization flag live + persist it. gl_viewport is applied
        immediately by swapping the viewport."""
        from PyQt6.QtCore import QSettings
        QSettings("edof", "editor").setValue("render/" + key, bool(value))
        setattr(self, "_opt_" + key, bool(value))
        if key == "gl_viewport":
            self._apply_gl_viewport(bool(value))
        if key == "gpu_effects":
            try:
                from edof.engine import gpu as _gpu
                _gpu.set_enabled(bool(value))
            except Exception:
                pass
        self.schedule_render(0)

    def _apply_gl_viewport(self, enabled):
        """Swap the QGraphicsView viewport between a QOpenGLWidget (GPU blits for
        pan/zoom) and the default raster viewport. Safe to call at runtime."""
        try:
            from PyQt6.QtWidgets import QGraphicsView as _QGV
            if enabled:
                from PyQt6.QtOpenGLWidgets import QOpenGLWidget
                from PyQt6.QtGui import QSurfaceFormat
                fmt = QSurfaceFormat(); fmt.setSamples(4)  # 4x MSAA
                gl = QOpenGLWidget(); gl.setFormat(fmt)
                self.setViewport(gl)
                self.setViewportUpdateMode(_QGV.ViewportUpdateMode.FullViewportUpdate)
            else:
                from PyQt6.QtWidgets import QWidget
                self.setViewport(QWidget())
                self.setViewportUpdateMode(_QGV.ViewportUpdateMode.MinimalViewportUpdate)
        except Exception:
            pass  # No OpenGL available — keep whatever viewport we have

    def _render_page_async(self, pg_idx, display=True):
        if not self._doc or not self._doc.pages: return
        if not (0 <= pg_idx < len(self._doc.pages)): return
        # v4.2.9.1/.2: adaptive render DPI — match the effective on-screen
        # resolution (base_dpi * zoom). Zoom in -> render higher (crisp); zoom
        # out -> render lower (cheaper, identical on-screen sharpness since the
        # screen can't show more pixels than it has). The pixmap is then scaled
        # onto the base-DPI scene, so scene coords / hit-testing never move.
        # Rendering at the object's full DPI when shown small would just waste
        # pixels the screen can't display, so we target the screen resolution.
        base_dpi = int(self._dpi)
        zoom = float(getattr(self, '_zoom', 1.0) or 1.0)
        # v4.2.9.3: also honour the display's device pixel ratio (HiDPI / OS
        # scaling), otherwise the OS upscales a logical-resolution pixmap and it
        # looks soft on retina / 125-150% screens.
        try:
            eff_dpr = float(self.devicePixelRatioF() or 1.0)
        except Exception:
            eff_dpr = 1.0
        eff_dpr = max(1.0, min(eff_dpr, 4.0))
        if not getattr(self, '_opt_adaptive_dpi', True):
            eff_dpr = 1.0   # optimization off -> plain base-DPI render
        if not getattr(self, '_opt_adaptive_dpi', True):
            factor = 1.0
        elif zoom > 1.25:
            factor = min(zoom, 3.0)
        elif zoom < 0.8:
            # v4.2.9.9: supersample when zoomed out so fine detail (halftone
            # dots, thin strokes, small text) downscales smoothly instead of
            # aliasing / moiring. Render above the bare screen-matched DPI, up
            # to the base DPI (Qt then minifies it = anti-aliasing). For extreme
            # zoom-out we still scale below base to keep big pages cheap.
            SS = 2.0 if getattr(self, '_opt_supersample', True) else 1.0
            factor = min(1.0, max(zoom * SS, 0.2))
        else:
            factor = 1.0
        raw = max(48.0 * eff_dpr, min(base_dpi * 3.0 * eff_dpr, base_dpi * factor * eff_dpr))
        if factor == 1.0 and eff_dpr == 1.0:
            render_dpi = base_dpi          # exact at ~100% on a 1x display
        else:
            # quantise to 24-DPI steps to limit per-object cache churn on zoom
            render_dpi = max(24, int(round(raw / 24.0)) * 24)
        try:
            pg0 = self._doc.pages[pg_idx]
            wpx = mm_to_px(pg0.width, render_dpi); hpx = mm_to_px(pg0.height, render_dpi)
            CAP = 28_000_000
            if wpx * hpx > CAP and wpx * hpx > 0:
                import math as _m2
                render_dpi = max(24, int(render_dpi * _m2.sqrt(CAP / (wpx * hpx))))
        except Exception:
            render_dpi = base_dpi
        # v4.2.11.52: WYSIWYG halftone. The dot lattice is decided at the render
        # DPI, so zooming out (which lowers render DPI) re-samples it and makes
        # dots pop in and out between zoom levels. Pin a minimum render DPI when
        # the page carries a halftone effect, so the lattice is computed at a
        # stable resolution and the pixmap is merely scaled onto the scene; the
        # dot count then stays identical at every zoom. Floor = the DPI at which
        # the cell spacing is >= 24 px (the lattice has converged by there); the
        # densest dot on the page (smallest ht_dot) drives it. Capped at 600 and
        # re-checked against the memory cap so big pages stay bounded.
        try:
            _pg_ht = self._doc.pages[pg_idx]
            _ht_dots = [abs(float(getattr(fx, 'ht_dot', 1.5)) or 1.5)
                        for _o in (getattr(_pg_ht, 'objects', None) or [])
                        for fx in (getattr(_o, 'effects', None) or [])
                        if getattr(fx, 'type', '') == 'halftone'
                        and getattr(fx, 'enabled', False)]
            if _ht_dots:
                _ht_floor = int(min(24.0 * 25.4 / max(0.05, min(_ht_dots)), 600.0))
                if render_dpi < _ht_floor:
                    render_dpi = _ht_floor
                    _wpx = mm_to_px(_pg_ht.width, render_dpi)
                    _hpx = mm_to_px(_pg_ht.height, render_dpi)
                    if _wpx * _hpx > 28_000_000 and _wpx * _hpx > 0:
                        import math as _m3
                        render_dpi = max(24, int(render_dpi * _m3.sqrt(28_000_000 / (_wpx * _hpx))))
        except Exception:
            pass
        # v4.2.9.8 / v4.2.11.31: while actively dragging/resizing an object the
        # page re-renders every mouse-move, which lags for heavy objects (images,
        # halftone, blur). Keep the page (and every STATIC element) at full DPI so
        # nothing shifts, and render only the dragged object at reduced resolution
        # (pixelated, via render_page_active active_scale). Only when there is no
        # single active object (whole-page re-render) do we fall back to the old
        # low-DPI page preview for responsiveness.
        interacting = bool(getattr(self, '_interacting', False))
        lowres = bool(getattr(self, '_opt_lowres_interaction', True))
        use_cache = bool(getattr(self, '_opt_object_cache', True))
        active_id = None
        if (interacting and display
                and getattr(self, '_opt_dirty_region', True)):
            active_id = (getattr(self, '_path_edit_obj_id', None)
                         or getattr(self, '_sel_id', None))
        active_scale = 1.0
        if interacting and lowres:
            if active_id is not None:
                active_scale = 0.6           # only the dragged object pixelates
            else:
                render_dpi = max(48, min(render_dpi, int(base_dpi * 0.6)))
        scale = (base_dpi / float(render_dpi)) if render_dpi else 1.0
        self._render_id += 1; rid = self._render_id
        self._rid_info[rid] = (pg_idx, display, scale)
        dpi = render_dpi
        doc = self._doc
        def task():
            try:
                from edof.engine.renderer import render_page, render_page_active
                pg = doc.pages[pg_idx]
                img = None
                if active_id is not None:
                    img = render_page_active(pg, doc.resources, doc.variables,
                                             active_id, dpi=dpi,
                                             active_scale=active_scale)
                if img is None:
                    img = render_page(pg, doc.resources, doc.variables,
                                      dpi=dpi, use_cache=use_cache)
                img = img.convert("RGB")
                buf = _io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
                _render_signals.done.emit(buf.read(), rid)
            except Exception as e:
                print(f"[render] {e}")
        threading.Thread(target=task, daemon=True).start()

    def _prerender_neighbors(self):
        """v4.1.23.21: render the previous and next pages off-screen into the
        pixmap cache so switching to them is instant."""
        if not self._doc or not self._doc.pages: return
        for nidx in (self._page_idx - 1, self._page_idx + 1):
            if 0 <= nidx < len(self._doc.pages) and nidx not in self._page_px_cache:
                self._render_page_async(nidx, display=False)

    def _invalidate_page_cache(self, idx=None):
        """Drop cached page pixmaps. idx=None clears everything (use after
        structural changes like add/remove page or repagination)."""
        try:
            if idx is None:
                self._page_px_cache.clear()
            else:
                self._page_px_cache.pop(idx, None)
        except Exception: pass

    def _reflow_current_body(self):
        """v4.1.23.26/.27: force a repagination + re-render of the active doc
        body (used after a line-spacing change, which alters line heights).
        Reuses the idle repaginate path for page breaks, then ALWAYS re-lays
        the inline editor and re-renders the page pixmap — even when the page
        count did not change — so the new line spacing is immediately visible.
        The line-height math itself is untouched."""
        try:
            obj = getattr(self, '_inline_obj', None)
            ed = getattr(self, '_inline_widget', None)
            # 1. repaginate (handles the case where taller lines push content
            # onto a new page / shorter lines pull it back)
            if obj is not None and self._is_document_body(obj):
                try: self._on_idle_overflow_reached(obj)
                except Exception: pass
            # 2. re-lay the inline editor with the new style
            ed = getattr(self, '_inline_widget', None)   # may have been rebuilt
            if ed is not None:
                try:
                    ed._invalidate()
                    ed._ensure_render()
                except Exception: pass
            # 3. drop the cached page pixmaps and re-render so the page behind
            # the editor shows the new spacing too
            self._invalidate_page_cache()
            self.schedule_render(0)
        except Exception:
            import traceback as _tb; _tb.print_exc()

    def _capture_carry(self):
        """v4.1.23.26: snapshot the effective format (size + attributes) at
        the caret of the current doc-body editor, so it can be re-applied as
        the pending format on the page we are about to switch to. This keeps
        the user's current size/attrs when typing continues on the new page
        instead of reverting to the body default."""
        try:
            ed = getattr(self, '_inline_widget', None)
            if ed is None or not self._is_document_body(getattr(self, '_inline_obj', None)):
                self._carry_pending = None
                return
            fmt = {}
            for attr in ('font_size', 'font_family', 'bold', 'italic',
                         'underline', 'strikethrough', 'color',
                         'line_height', 'letter_spacing'):
                v = ed._current_format_attr(attr)
                if v is not None:
                    fmt[attr] = v
            self._carry_pending = fmt or None
        except Exception:
            self._carry_pending = None

    def _refocus_inline(self):
        """v4.1.23.22/.26: return keyboard focus to the active inline editor.
        The editor is a QGraphicsProxyWidget in this view's scene, so three
        things must hold for keystrokes to reach it: the QGraphicsView itself
        must hold focus (a sibling widget like the size spinbox steals it),
        the proxy must be the scene's focus item, and the embedded widget must
        have widget focus. We also restart the caret blink so it stays
        visible."""
        try:
            proxy = getattr(self, '_inline_proxy', None)
            ed = getattr(self, '_inline_widget', None)
            # 1. the view must own focus (spinbox/buttons are viewport siblings)
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            # 2. proxy = scene focus item
            if proxy is not None and proxy.scene() is not None:
                proxy.setFocus(Qt.FocusReason.OtherFocusReason)
            # 3. embedded widget focus + visible caret
            if ed is not None:
                ed.setFocus(Qt.FocusReason.OtherFocusReason)
                try: ed._invalidate()
                except Exception: pass
        except Exception: pass

    def _apply_page_pixmap(self, px, scale):
        """Place a rendered page pixmap so it occupies the base-DPI scene rect.
        When the page was rendered at a higher DPI (crisp zoom-in), scale < 1
        maps the high-res pixmap back onto the base-DPI scene so overlays and
        hit-testing stay in base-DPI coordinates."""
        self._page_item.setPixmap(px)
        try: self._page_item.setScale(scale)
        except Exception: pass
        self._page_item.setPos(0, 0)
        self.scene().setSceneRect(QRectF(0, 0, px.width() * scale, px.height() * scale))

    def _on_render_done(self, data: bytes, rid: int):
        info = self._rid_info.pop(rid, None)
        px = QPixmap(); px.loadFromData(data)
        if info is not None and len(info) >= 3:
            pg_idx, display, scale = info[0], info[1], info[2]
        else:
            pg_idx, display, scale = (self._page_idx, True, 1.0)
        try: self._page_px_cache[pg_idx] = (px, scale)
        except Exception: pass
        # Background pre-renders only fill the cache — don't touch the view.
        if not display:
            return
        if rid != self._render_id and pg_idx != self._page_idx:
            return   # stale display render for a page we already left
        self._apply_page_pixmap(px, scale)
        self._refresh_overlay(); self._update_ghosts()
        self._reposition_inline()

    # ── Ghost items for invisible objects ─────────────────────────────────────

    def _update_ghosts(self):
        for item in self._ghost_items: self.scene().removeItem(item)
        self._ghost_items.clear()
        if not self._doc or not self._doc.pages: return
        pen=QPen(QColor(200,80,80,160),1,Qt.PenStyle.DashLine)
        brs=QBrush(QColor(200,80,80,20))
        for obj in self._doc.pages[self._page_idx].objects:
            if not obj.visible:
                t=obj.transform
                x=mm_to_px(t.x,self._dpi); y=mm_to_px(t.y,self._dpi)
                w=mm_to_px(t.width,self._dpi); h=mm_to_px(t.height,self._dpi)
                item=self.scene().addRect(QRectF(0,0,w,h),pen,brs)
                item.setPos(x,y); item.setTransformOriginPoint(w/2,h/2)
                item.setRotation(t.rotation); item.setZValue(50)
                self._ghost_items.append(item)

    def _refresh_overlay(self):
        # v4.1.12: hide the selection bbox overlay while editing path
        # anchors. The bbox corner handles can sit on top of anchor handles
        # (e.g. M at (0,0) coincides with bbox top-left), visually
        # confusing the user.
        if getattr(self, '_path_edit_obj_id', None):
            self._overlay.update_for(None, self._dpi)
            return
        sel = self._sel_obj()
        # v4.2.11.42: header/footer (and the body) are geometry-locked document
        # furniture, not free objects. Never show their transform box/handles
        # even if selected via the Objects list -- their size/position is driven
        # by page setup, so dragging an edge makes no sense.
        try:
            from edof.format.document_boxes import (
                DocumentHeaderBox, DocumentFooterBox)
            if isinstance(sel, (DocumentHeaderBox, DocumentFooterBox)) or \
               self._is_document_body(sel):
                self._overlay.update_for(None, self._dpi)
                return
        except Exception:
            pass
        self._overlay.update_for(sel, self._dpi)

    # v4.1.0: grid as semi-transparent dots + visible margins
    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if not self._doc or not self._doc.pages: return
        if self._page_idx >= len(self._doc.pages): return
        page = self._doc.pages[self._page_idx]
        page_w_px = mm_to_px(page.width, self._dpi)
        page_h_px = mm_to_px(page.height, self._dpi)
        # v4.2.10.3: keep grid/margins/guides a constant on-screen size at any
        # zoom (cosmetic pens for lines/dashes; dots via a cosmetic-width point).
        z = self.transform().m11()
        if z <= 1e-6: z = 1.0

        # Draw grid as semi-transparent dots
        if self._snap_to_grid:
            grid_mm = self._snap_size_mm
            grid_px = mm_to_px(grid_mm, self._dpi)
            if grid_px * z > 6:  # don't draw if too dense on screen
                painter.save()
                pen = QPen(QColor(120, 140, 200, 120), 2.2)
                pen.setCosmetic(True); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                x = 0.0
                while x <= page_w_px:
                    y = 0.0
                    while y <= page_h_px:
                        painter.drawPoint(QPointF(x, y))
                        y += grid_px
                    x += grid_px
                painter.restore()

        # Draw page margins as light dashed cyan lines
        if self._margins_enabled and self._margins:
            top, right, bottom, left = self._margins
            painter.save()
            pen = QPen(QColor(80, 160, 220, 160), 1.2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True); pen.setDashPattern([4, 4])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            tl_x = mm_to_px(left, self._dpi)
            tl_y = mm_to_px(top, self._dpi)
            br_x = page_w_px - mm_to_px(right, self._dpi)
            br_y = page_h_px - mm_to_px(bottom, self._dpi)
            painter.drawRect(QRectF(tl_x, tl_y, br_x - tl_x, br_y - tl_y))
            painter.restore()

        # v4.2.11.43: header/footer guide bands. An enabled but empty band has
        # no text and no fill, so there was nothing to see or aim at -- you
        # could not tell where to double-click to edit it (or to insert page
        # numbers). Draw a faint tinted band with a dashed outline, plus a hint
        # while it is empty. Document mode only. The band is exactly the box the
        # double-click hit-test targets.
        try:
            body = getattr(self._doc, 'body', None)
            if body is not None and getattr(self._doc, 'mode', '') == 'document':
                from edof.engine.document_paginate import (
                    find_document_header_on_page as _fh,
                    find_document_footer_on_page as _ff)
                bands = []
                if getattr(body, 'header_enabled', False):
                    hb = _fh(page)
                    if hb is not None:
                        bands.append((hb, "Header"))
                if getattr(body, 'footer_enabled', False):
                    fb = _ff(page)
                    if fb is not None:
                        bands.append((fb, "Footer"))
                for box, label in bands:
                    # v4.2.11.44: draw the band at the box's ACTUAL geometry
                    # (it sits inside the top/bottom margin at box.transform.y,
                    # NOT at the page edge). The previous version computed its
                    # own y from the page edge, so the visible band did not line
                    # up with the box the double-click targets -- it looked like
                    # a band at the page boundary that could not be clicked.
                    t = box.transform
                    bx = mm_to_px(t.x, self._dpi); by = mm_to_px(t.y, self._dpi)
                    bw = mm_to_px(t.width, self._dpi); bh = mm_to_px(t.height, self._dpi)
                    empty = not ((box.text or '').strip())
                    painter.save()
                    pen = QPen(QColor(90, 150, 210, 150), 1.0, Qt.PenStyle.DashLine)
                    pen.setCosmetic(True); pen.setDashPattern([3, 3])
                    painter.setPen(pen)
                    painter.setBrush(QColor(120, 160, 220, 26))
                    painter.drawRect(QRectF(bx, by, bw, bh))
                    if empty:
                        painter.setPen(QColor(90, 120, 170, 210))
                        f = painter.font(); f.setPointSizeF(max(6.0, 9.0 / z)); painter.setFont(f)
                        painter.drawText(
                            QRectF(bx + 6, by, bw - 12, bh),
                            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                            f"{label} (double-click to edit)")
                    painter.restore()
        except Exception:
            pass
        if self._align_guide_lines:
            painter.save()
            pen = QPen(QColor(255, 100, 200, 200), 1.2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for line in self._align_guide_lines:
                # line is (orientation, position_px) where orientation is 'h' or 'v'
                if isinstance(line, tuple) and len(line) == 2:
                    orient, pos = line
                    if orient == 'h':
                        painter.drawLine(QPointF(0, pos), QPointF(page_w_px, pos))
                    else:
                        painter.drawLine(QPointF(pos, 0), QPointF(pos, page_h_px))
            painter.restore()

    # ── Coordinates ───────────────────────────────────────────────────────────

    def _sp(self,event): return self.mapToScene(event.position().toPoint())
    def _to_mm(self,sp): return px_to_mm(sp.x(),self._dpi),px_to_mm(sp.y(),self._dpi)

    # ── Inline text editor (viewport overlay – reliable event handling) ────────

    def _start_inline(self, obj):
        """v4.1.16: Replaced QTextEdit with custom EdofTextEditor widget.
        The new editor renders text via the SAME PIL/freetype pipeline as
        the canvas renderer, guaranteeing pixel-perfect WYSIWYG. The widget
        is placed in the scene via QGraphicsProxyWidget so it scales with
        the view's zoom transform automatically."""
        try:
            from edof.engine.debug_log import log as _dlog
            _dlog("canvas._start_inline",
                   obj_name=getattr(obj, 'name', '?'),
                   page=self._page_idx,
                   tb_text=(obj.text or "")[:60] if hasattr(obj, 'text') else "")
        except Exception: pass
        from edof._apps.edof_text_editor import EdofTextEditor
        from PyQt6.QtWidgets import QGraphicsProxyWidget
        self._cancel_inline()
        t   = obj.transform
        dpi = float(self._dpi)

        self._inline_was_visible = obj.visible
        obj.visible = False
        # Snapshot for cancel revert
        try:
            import copy as _copy
            self._inline_snapshot = {
                'text':       obj.text,
                'runs':       _copy.deepcopy(getattr(obj, 'runs', [])),
                'font_size':  obj.style.font_size,
                'width':      obj.transform.width,
                'height':     obj.transform.height,
                'alignment':       obj.style.alignment,
                'vertical_align':  obj.style.vertical_align,
                # v4.1.21: snapshot per-paragraph alignment overrides too
                'paragraph_alignments': _copy.deepcopy(
                    getattr(obj, 'paragraph_alignments', {}) or {}),
            }
        except Exception:
            self._inline_snapshot = None
        self.schedule_render(0)

        # Scene coordinates (= pixmap pixels = renderer pixel space)
        scene_x = mm_to_px(t.x, dpi)
        scene_y = mm_to_px(t.y, dpi)
        scene_w = max(1.0, mm_to_px(t.width,  dpi))
        scene_h = max(1.0, mm_to_px(t.height, dpi))

        # Create the editor widget
        # v4.1.19.2: pass current page background so the inline editor uses
        # it as the default backdrop (rather than the scene's dark navy
        # colour) when the textbox has no fill of its own.
        # v4.1.20.7: ALSO pass a snapshot of the canvas pixmap at this
        # textbox's location. This snapshot becomes the editor's opaque
        # background, sidestepping every QGraphicsProxyWidget transparency
        # bug we've tried to work around in 4.1.17.x → 4.1.20.6 (Qt's
        # stylesheet engine paints a dark fill under the widget despite
        # WA_TranslucentBackground / WA_StyledBackground / palette overrides
        # / etc.). By making the editor visually identical to what's
        # underneath, the "yellow" cast simply cannot occur — there is no
        # transparency involved.
        cur_pg = self._cur_page()
        page_bg = None
        if cur_pg is not None:
            pb = getattr(cur_pg, 'background', None)
            if pb and len(pb) >= 3:
                page_bg = tuple(pb)
        # v4.1.20.7: render a FRESH snapshot of the page minus the body
        # textbox. We use the renderer directly (sync) so the snapshot is
        # always up-to-date, and we exclude the body from it so there's no
        # ghost of the old body text underneath the editor when the user
        # types something shorter than before.
        snapshot_qimg = None
        try:
            from edof.engine.renderer import render_page
            from PIL import Image
            # obj is already visible=False, so render_page skips it
            snapshot_pil = render_page(
                cur_pg, self._doc.resources, self._doc.variables,
                dpi=dpi, show_transparency_checker=False)
            # Crop to textbox bounds in pixel coords
            sx = int(round(scene_x)); sy = int(round(scene_y))
            sw = int(round(scene_w)); sh = int(round(scene_h))
            sx2 = sx + sw; sy2 = sy + sh
            # Clamp to image bounds
            iw, ih = snapshot_pil.size
            sx_c = max(0, min(sx, iw)); sy_c = max(0, min(sy, ih))
            sx2_c = max(sx_c, min(sx2, iw)); sy2_c = max(sy_c, min(sy2, ih))
            if sx2_c > sx_c and sy2_c > sy_c:
                snap_crop = snapshot_pil.crop((sx_c, sy_c, sx2_c, sy2_c))
                # Pad if textbox extends outside the rendered page
                if (sx2_c - sx_c) != sw or (sy2_c - sy_c) != sh:
                    full = Image.new("RGBA", (sw, sh),
                                       (page_bg[:3] + (255,)) if page_bg else (255, 255, 255, 255))
                    paste_x = max(0, sx_c - sx)
                    paste_y = max(0, sy_c - sy)
                    full.paste(snap_crop, (paste_x, paste_y))
                    snapshot_pil_crop = full
                else:
                    snapshot_pil_crop = snap_crop
                # Convert to QImage via raw bytes
                snapshot_pil_crop = snapshot_pil_crop.convert("RGBA")
                from PyQt6.QtGui import QImage as _QI
                raw = snapshot_pil_crop.tobytes("raw", "RGBA")
                snapshot_qimg = _QI(raw, snapshot_pil_crop.width,
                                       snapshot_pil_crop.height,
                                       snapshot_pil_crop.width * 4,
                                       _QI.Format.Format_RGBA8888).copy()
        except Exception:
            import traceback as _tb; _tb.print_exc()
            snapshot_qimg = None
        is_body = self._is_document_body(obj)
        # v4.2.11.41: header/footer boxes display per-page RESOLVED runs
        # (with {page_number} already turned into "1"). When the user edits one
        # we want them to see and edit the TEMPLATE (the raw {page_number}
        # token), which lives on doc.body.header_runs / footer_runs. Swap the
        # template in before constructing the editor and remember the role so
        # the commit writes back to the right place.
        self._inline_hf_role = None
        self._inline_hf_even = False
        try:
            from edof.format.document_boxes import (
                DocumentHeaderBox, DocumentFooterBox)
            from edof.format.styles import TextRun as _TR
            body = getattr(self._doc, 'body', None)
            if body is not None and isinstance(
                    obj, (DocumentHeaderBox, DocumentFooterBox)):
                role = 'header' if isinstance(obj, DocumentHeaderBox) else 'footer'
                self._inline_hf_role = role
                # v4.2.11.46: pick the template SET for this page's parity so
                # editing on an even page edits the even template (when the
                # odd/even option is on), and apply the persisted band style so
                # vertical align etc. shows correctly while editing.
                start = int(getattr(body, 'page_number_start', 1) or 1)
                page_number = self._page_idx + start
                use_even = bool(getattr(body, 'hf_odd_even', False)) and (page_number % 2 == 0)
                self._inline_hf_even = use_even
                suff = '_even' if use_even else ''
                tmpl = list(getattr(body, f'{role}_runs{suff}', []) or [])
                obj.runs = tmpl or [_TR(text="")]
                obj.text = "".join(r.text or "" for r in obj.runs)
                sd = getattr(body, f'{role}_style{suff}', None)
                if sd:
                    try:
                        from edof.format.styles import TextStyle as _TS
                        obj.style = _TS.from_dict(dict(sd))
                    except Exception:
                        pass
        except Exception:
            self._inline_hf_role = None
        ed = EdofTextEditor(obj, dpi=dpi, page_bg=page_bg,
                              bg_snapshot=snapshot_qimg,
                              is_doc_body=is_body)
        # v4.1.23.18: mark the editor "continued" when this doc body is on a
        # page that is NOT the last page carrying the body — its content
        # flows onto the next page. The editor then suppresses the trailing
        # virtual line so the caret cannot land on the empty boundary line
        # that would sit in the bottom margin. The last body page keeps it.
        if is_body and self._doc is not None:
            try:
                from edof.engine.document_paginate import (
                    find_document_body_on_page as _find_body)
                cidx = None
                for _i, _pg in enumerate(self._doc.pages):
                    if obj in _pg.objects:
                        cidx = _i; break
                continues = False
                if cidx is not None:
                    for _pg in self._doc.pages[cidx + 1:]:
                        if _find_body(_pg) is not None:
                            continues = True; break
                ed._continues = continues
            except Exception:
                ed._continues = False
        # v4.1.23.58: for the document body, route the editor's undo/redo and
        # edit-burst checkpoints to the host window's document-level body
        # history, so Ctrl+Z spans pages. Plain text boxes keep their local
        # per-editor undo (host hooks left as None).
        if is_body:
            mw = self.parent()
            if mw is not None and hasattr(mw, '_on_body_touched'):
                ed._host_undo = mw._undo
                ed._host_redo = mw._redo
                ed._on_body_edit = mw._on_body_touched
                # v4.2.1: route Ctrl+S / Ctrl+Shift+S to the window's save so
                # they work while the caret is inside the body text editor
                # (previously Ctrl+S did nothing and Ctrl+Shift+S toggled
                # strikethrough instead of Save As).
                if hasattr(mw, '_save'):
                    ed._host_save = mw._save
                if hasattr(mw, '_save_as'):
                    ed._host_save_as = mw._save_as
        # v4.1.16.4: signals trigger UI cleanup AFTER editor has written
        # data back. Editor.py drives commit/cancel directly; signals are
        # for after-the-fact cleanup only — no recursion possible.
        ed.committed.connect(lambda _tb: self._after_inline_commit())
        ed.cancelled.connect(lambda _tb: self._after_inline_cancel())
        # v4.1.20.1: Ctrl+Enter routing — in doc mode inserts new page,
        # otherwise commits the textbox (preserves legacy behaviour).
        ed.new_page_requested.connect(lambda _tb: self._on_new_page_requested(_tb))
        ed.overflow_changed.connect(lambda v: self._on_inline_overflow(v, obj))
        # v4.1.22.1: doc-body specific flow signals
        ed.merge_with_previous_requested.connect(
            lambda _tb: self._on_merge_with_previous(_tb))
        ed.merge_with_next_requested.connect(
            lambda _tb: self._on_merge_with_next(_tb))
        ed.idle_overflow_reached.connect(
            lambda _tb: self._on_idle_overflow_reached(_tb))
        ed.cursor_changed.connect(self._scroll_to_cursor)
        # v4.1.22.4: arrow-up/-down past body edges hops to prev/next page
        ed.navigate_above.connect(lambda _tb: self._on_navigate_above(_tb))
        ed.navigate_below.connect(lambda _tb: self._on_navigate_below(_tb))

        # Wrap in proxy and insert into scene
        proxy = QGraphicsProxyWidget()
        proxy.setWidget(ed)
        # v4.1.18.1: keep the proxy itself transparent (some Qt versions paint
        # a fill behind embedded widgets even when the widget is translucent)
        proxy.setAutoFillBackground(False)
        proxy.setPos(scene_x, scene_y)
        proxy.setZValue(10000)
        # v4.1.16.5: apply textbox rotation so inline editor edits the
        # textbox in its rotated orientation. Rotation centre = widget
        # centre (matches how the renderer rotates).
        rotation = float(getattr(t, 'rotation', 0.0) or 0.0)
        if abs(rotation) > 0.01:
            proxy.setTransformOriginPoint(scene_w / 2.0, scene_h / 2.0)
            proxy.setRotation(rotation)
        self.scene().addItem(proxy)
        # v4.1.20.3: robust focus setup — proxy needs to be focusable AND
        # set as scene focus item, the embedded widget then receives keyboard
        # input. Previously a single ed.setFocus() sometimes lost the first
        # keystroke because Qt's focus chain hadn't fully wired up before the
        # first key event arrived. Calling setFocus on both proxy & widget
        # and deferring via QTimer.singleShot(0, …) lets the event loop
        # settle before keystrokes start flowing in.
        proxy.setFlag(proxy.GraphicsItemFlag.ItemIsFocusable, True)
        proxy.setFocus()
        ed.setFocus()
        from PyQt6.QtCore import QTimer as _IFT
        def _reassert_focus():
            try:
                if proxy.scene() is not None:
                    proxy.setFocus()
                if ed is not None:
                    ed.setFocus()
                    ed.activateWindow()
            except Exception: pass
        _IFT.singleShot(0, _reassert_focus)
        self._inline_widget = ed
        self._inline_proxy  = proxy
        self._inline_id     = obj.id
        self._inline_obj    = obj
        # v4.1.23.26: if we just flowed onto this page, adopt the format the
        # caret had on the previous page so continued typing keeps the size
        # and attributes instead of dropping to the body default.
        if self._is_document_body(obj) and getattr(self, '_carry_pending', None):
            try: ed._pending_format = dict(self._carry_pending)
            except Exception: pass
        self._carry_pending = None
        # Dashed accent border in the scene (also scales with zoom)
        border_pen = QPen(QColor(ACC), 1.5, Qt.PenStyle.DashLine)
        border_rect = self.scene().addRect(
            QRectF(scene_x, scene_y, scene_w, scene_h),
            border_pen, QBrush(Qt.BrushStyle.NoBrush))
        border_rect.setZValue(9999)
        if abs(rotation) > 0.01:
            # Rotate border around the same centre as proxy
            border_rect.setTransformOriginPoint(
                scene_x + scene_w / 2.0, scene_y + scene_h / 2.0)
            border_rect.setRotation(rotation)
        self._inline_border_frame = border_rect

        # Floating formatting toolbar above the editor (stays in viewport
        # so it's always readable at any zoom). v4.2.11.49: construction lives
        # in _build_text_ribbon so a disabled skeleton can be shown at startup.
        self._build_text_ribbon(ed, obj, is_body)


    def _build_text_ribbon(self, ed, obj, is_body):
        """Build (or rebuild in place) the persistent text ribbon, binding its
        controls to the given editor instance. Also used with a hidden dummy
        editor to show a disabled skeleton ribbon from startup
        (v4.2.11.49)."""
                # v4.2.11.47: PERSISTENT ribbon. Destroying and recreating the toolbar
        # on every session (and every sticky commit cycle in document mode)
        # made it blink and flipped the reserved viewport band -- the page
        # visibly jumped. The container is now created ONCE and kept visible;
        # each session only rebuilds its contents in place (the buttons bind to
        # the current editor instance). Ending a session merely disables the
        # controls; the band and the page never move.
        toolbar = getattr(self, '_text_ribbon', None)
        if toolbar is None:
            toolbar = QWidget(self)   # parent = view frame: occupies the
            # reserved top margin band instead of the scrollable page area.
            toolbar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            toolbar.setStyleSheet("background:#2b2b2b;border:1px solid #555;border-radius:3px;")
            self._text_ribbon = toolbar
        else:
            old = toolbar.layout()
            if old is not None:
                while old.count():
                    it = old.takeAt(0)
                    w_ = it.widget()
                    if w_ is not None:
                        w_.deleteLater()
                    else:
                        lay = it.layout()
                        if lay is not None:
                            while lay.count():
                                it2 = lay.takeAt(0)
                                if it2.widget() is not None:
                                    it2.widget().deleteLater()
                # detach the old layout so a fresh one can be installed
                _tmp = QWidget(); _tmp.setLayout(old); _tmp.deleteLater()
        toolbar.setEnabled(True)
        # v4.2.11.39: the toolbar content can exceed one row's width (the
        # design-mode editor adds Apply/Cancel on top of everything else), and
        # a fixed-width single row silently pushed the trailing controls --
        # including the size / line-spacing / letter-spacing spinboxes -- past
        # the right edge. The outer layout is vertical now; the content is
        # packed into ONE row when it fits the viewport and wraps into TWO
        # rows when it does not.
        tb_layout = QVBoxLayout(toolbar)
        tb_layout.setContentsMargins(4, 2, 4, 2); tb_layout.setSpacing(2)

        def _btn(text, tip, callback, fixed_w=32, icon=None):
            b = QPushButton(text); b.setToolTip(tip)
            b.setFixedHeight(30); b.setFixedWidth(fixed_w)
            b.setStyleSheet("font:bold 11pt 'Segoe UI';color:white;background:#444;border:1px solid #666;border-radius:3px;")
            # v4.1.16.2: NoFocus so clicking a toolbar button doesn't
            # steal focus from the editor (which would clear the selection
            # and make format toggles act on nothing).
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if icon:
                _ic = uicon(icon)
                if not _ic.isNull():
                    b.setText(""); b.setIcon(_ic); b.setIconSize(QSize(18, 18))
            b.clicked.connect(callback)
            return b

        # Format toggles
        btn_b = _btn("B",   "Bold (Ctrl+B)",         ed.toggle_bold, icon="bold")
        btn_i = _btn("I",   "Italic (Ctrl+I)",       ed.toggle_italic, icon="italic")
        btn_i.setStyleSheet(btn_i.styleSheet().replace("font:bold", "font:italic bold"))
        btn_u = _btn("U",   "Underline (Ctrl+U)",    ed.toggle_underline, icon="underline")
        btn_u.setStyleSheet(btn_u.styleSheet() + "QPushButton{text-decoration:underline}")
        btn_s = _btn("S",   "Strikethrough",         ed.toggle_strikethrough, icon="strike")
        btn_s.setStyleSheet(btn_s.styleSheet() + "QPushButton{text-decoration:line-through}")
        # v4.1.23.38: text colour + highlight (line/background) colour.
        from PyQt6.QtWidgets import QColorDialog as _QCD
        from PyQt6.QtGui import QColor as _QColor
        def _pick_text_color():
            cur = ed._current_format_attr('color') or (0, 0, 0)
            c = _QCD.getColor(_QColor(cur[0], cur[1], cur[2]), self,
                              "Text colour")
            if c.isValid():
                ed.set_color((c.red(), c.green(), c.blue(), 255))
                self._reflow_current_body()
            self._refocus_inline()
        def _pick_hl_color():
            cur = ed._current_format_attr('background')
            init = _QColor(cur[0], cur[1], cur[2]) if cur else _QColor(255, 255, 0)
            dlg = _QCD(init, self); dlg.setWindowTitle("Highlight colour")
            dlg.setOption(_QCD.ColorDialogOption.ShowAlphaChannel, True)
            # offer a quick "no highlight" via the custom button row
            if dlg.exec():
                c = dlg.currentColor()
                ed.set_background((c.red(), c.green(), c.blue(), c.alpha()))
                self._reflow_current_body()
            self._refocus_inline()
        def _clear_hl():
            ed.set_background(None); self._reflow_current_body(); self._refocus_inline()
        btn_color = _btn("A", "Text colour", _pick_text_color)
        btn_color.setStyleSheet(btn_color.styleSheet().replace(
            "color:white", "color:#ff5555"))
        btn_hl = _btn("ab", "Highlight colour", _pick_hl_color)
        btn_hl.setStyleSheet(btn_hl.styleSheet() + "QPushButton{background:#5a5a2d}")
        btn_hl_clear = _btn("a̶", "Clear highlight", _clear_hl)
        # v4.2.11.41: page-number token menu, shown only while editing a header
        # or footer. Inserts {page_number} (and variants) at the caret; the
        # paginator resolves the token per page at render time.
        btn_pgnum = None
        if getattr(self, '_inline_hf_role', None) in ('header', 'footer'):
            from PyQt6.QtWidgets import QMenu as _QMenu
            def _ins(tok):
                def _do():
                    try:
                        ed._insert_text(tok); ed._invalidate()
                    except Exception: pass
                    self._refocus_inline()
                return _do
            pg_menu = _QMenu(self)
            pg_menu.addAction("Page number  (1)", _ins("{page_number}"))
            pg_menu.addAction("Page X of Y  (1 / N)",
                              _ins("{page_number} / {page_count}"))
            pg_menu.addAction("Total pages  (N)", _ins("{page_count}"))
            pg_menu.addSeparator()
            pg_menu.addAction("Number, left-aligned",   _ins("{page_number_left}"))
            pg_menu.addAction("Number, centered",       _ins("{page_number_center}"))
            pg_menu.addAction("Number, right-aligned",  _ins("{page_number_right}"))
            btn_pgnum = _btn("#▾", "Insert page number", lambda: None, fixed_w=40)
            btn_pgnum.setMenu(pg_menu)
        # v4.1.16.3: Font size spinbox — applies to current selection.
        # v4.1.17: now in mm (canonical EDOF unit).
        sp_size = FocusKeepingSpinBox()
        sp_size._editor_ref = self   # canvas — has _refocus_inline()
        sp_size.setRange(0.3, 350.0)
        sp_size.setSingleStep(0.1)
        sp_size.setDecimals(2)
        sp_size.setSuffix(" mm")
        sp_size.setMinimumWidth(110); sp_size.setMaximumWidth(140)
        sp_size.setMinimumHeight(30); sp_size.setMaximumHeight(30)
        sp_size.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        sp_size.setAlignment(Qt.AlignmentFlag.AlignRight)
        sp_size.setStyleSheet("""
            QDoubleSpinBox {
                background:#3a3a4a;
                color:white;
                border:1px solid #666;
                border-radius:3px;
                padding:2px 4px;
                font:bold 10pt 'Segoe UI';
                selection-background-color:#0078d4;
            }
        """)
        try:
            sp_size.setValue(float(obj.style.font_size))   # already mm
        except Exception:
            sp_size.setValue(4.233)   # 12pt default
        def _on_size_changed(v):
            try: ed.set_font_size_mm(float(v))
            except Exception: pass
        sp_size.valueChanged.connect(_on_size_changed)

        # v4.1.23.26: font-family selector.
        cb_font = QComboBox()
        cb_font.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        cb_font.setMinimumWidth(140); cb_font.setMaximumWidth(200)
        cb_font.setFixedHeight(30)
        cb_font.setStyleSheet("""
            QComboBox{background:#3a3a4a;color:white;border:1px solid #666;
                      border-radius:3px;padding:2px 6px;font:bold 10pt 'Segoe UI';}
            QComboBox QAbstractItemView{background:#2a2a35;color:white;
                      selection-background-color:#0a84ff;}
        """)
        try:
            from edof.engine.text_engine import list_system_fonts
            _fonts = list_system_fonts() or []
        except Exception:
            _fonts = []
        if not _fonts:
            _fonts = ["Arial", "Times New Roman", "Courier New"]
        cb_font.addItems(_fonts)
        try:
            cur_fam = obj.style.font_family
            ix = cb_font.findText(cur_fam, Qt.MatchFlag.MatchFixedString)
            if ix >= 0: cb_font.setCurrentIndex(ix)
        except Exception: pass
        def _on_font_changed(name):
            try:
                ed.set_font_family(str(name))
            except Exception: pass
            self._refocus_inline()
        cb_font.activated.connect(lambda _i: _on_font_changed(cb_font.currentText()))

        # v4.1.23.27: line-spacing spinbox. Sets the body style's line_height
        # multiplier (the SAME value the layout/pagination already use);
        # default 1.15 unchanged. Arrows step without stealing focus.
        sp_ls = FocusKeepingSpinBox()
        sp_ls._editor_ref = self
        sp_ls.setRange(0.5, 5.0)
        sp_ls.setSingleStep(0.05)
        sp_ls.setDecimals(2)
        sp_ls.setPrefix("⇕ ")
        sp_ls.setFixedHeight(30); sp_ls.setMinimumWidth(96); sp_ls.setMaximumWidth(110)
        sp_ls.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        sp_ls.setAlignment(Qt.AlignmentFlag.AlignRight)
        sp_ls.setToolTip("Line spacing (multiplier)")
        sp_ls.setStyleSheet(sp_size.styleSheet())
        try:
            sp_ls.setValue(float(getattr(obj.style, 'line_height', 1.15) or 1.15))
        except Exception:
            sp_ls.setValue(1.15)
        def _on_ls_changed(v):
            # v4.1.23.33: per-RUN line spacing (applies to selection or as a
            # sticky pending value for the next typed text), NOT the whole
            # body. The editor reflows so the new spacing is visible at once.
            try:
                ed.set_line_height(float(v))
                self._reflow_current_body()
            except Exception:
                import traceback as _tb; _tb.print_exc()
            self._refocus_inline()
        sp_ls.valueChanged.connect(_on_ls_changed)

        # v4.1.23.33: per-run LETTER SPACING (mm of extra advance after each
        # glyph). Applies to the selection or as a sticky pending value.
        sp_letsp = FocusKeepingSpinBox()
        sp_letsp._editor_ref = self
        sp_letsp.setRange(-2.0, 10.0)
        sp_letsp.setSingleStep(0.1)
        sp_letsp.setDecimals(2)
        sp_letsp.setPrefix("⇿ ")
        sp_letsp.setSuffix(" mm")
        sp_letsp.setFixedHeight(30); sp_letsp.setMinimumWidth(104); sp_letsp.setMaximumWidth(120)
        sp_letsp.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        sp_letsp.setAlignment(Qt.AlignmentFlag.AlignRight)
        sp_letsp.setToolTip("Letter spacing (mm)")
        sp_letsp.setStyleSheet(sp_size.styleSheet())
        try:
            sp_letsp.setValue(float(getattr(obj.style, 'letter_spacing', 0.0) or 0.0))
        except Exception:
            sp_letsp.setValue(0.0)
        def _on_letsp_changed(v):
            try:
                ed.set_letter_spacing_mm(float(v))
                self._reflow_current_body()
            except Exception:
                import traceback as _tb; _tb.print_exc()
            self._refocus_inline()
        sp_letsp.valueChanged.connect(_on_letsp_changed)

        # v4.1.23.25: keep the toolbar in sync with the format at the caret.
        # As the caret moves (or selection changes) the size spinbox shows the
        # caret's size and the B/I/U/S buttons light up for active attributes.
        _fmt_btns = [(btn_b, 'bold'), (btn_i, 'italic'),
                     (btn_u, 'underline'), (btn_s, 'strikethrough')]
        _fmt_base = {id(b): b.styleSheet() for b, _ in _fmt_btns}
        # v4.1.23.35: populated after the alignment buttons are created below;
        # the _sync_fmt closure reads it at call time.
        _align_btns = []
        def _sync_fmt():
            try:
                sz = ed._current_format_attr('font_size')
                if sz:
                    sp_size.blockSignals(True)
                    sp_size.setValue(float(sz))
                    sp_size.blockSignals(False)
                fam = ed._current_format_attr('font_family')
                if fam:
                    ix = cb_font.findText(str(fam), Qt.MatchFlag.MatchFixedString)
                    if ix >= 0 and ix != cb_font.currentIndex():
                        cb_font.blockSignals(True)
                        cb_font.setCurrentIndex(ix)
                        cb_font.blockSignals(False)
                try:
                    lh = ed._current_format_attr('line_height')
                    if lh is None:
                        lh = float(getattr(obj.style, 'line_height', 1.15) or 1.15)
                    lh = float(lh)
                    if abs(sp_ls.value() - lh) > 1e-6:
                        sp_ls.blockSignals(True); sp_ls.setValue(lh); sp_ls.blockSignals(False)
                except Exception: pass
                try:
                    ls = ed._current_format_attr('letter_spacing')
                    if ls is None:
                        ls = float(getattr(obj.style, 'letter_spacing', 0.0) or 0.0)
                    ls = float(ls)
                    if abs(sp_letsp.value() - ls) > 1e-6:
                        sp_letsp.blockSignals(True); sp_letsp.setValue(ls); sp_letsp.blockSignals(False)
                except Exception: pass
                for b, attr in _fmt_btns:
                    active = bool(ed._current_format_attr(attr))
                    base = _fmt_base.get(id(b), b.styleSheet())
                    b.setStyleSheet(base.replace('#444', '#0a84ff')
                                    if active else base)
                # v4.1.23.35: highlight the active alignment button so the
                # user can see which alignment (incl. justify) is on.
                try:
                    cur_al = ed._current_format_attr('alignment')
                    if not cur_al:
                        cur_al = (getattr(obj, 'paragraph_alignments', {}) or {}).get(
                            str((''.join(r.text or '' for r in ed._runs))[:ed._cursor].count('\n')))
                    cur_al = cur_al or (getattr(obj.style, 'alignment', 'left') or 'left')
                    for b, av in _align_btns:
                        on = (cur_al == av)
                        base = _fmt_base.get(id(b), b.styleSheet())
                        b.setStyleSheet(base.replace('#444', '#0a84ff') if on else base)
                except Exception: pass
                # v4.1.23.38: reflect the caret's text + highlight colour on
                # the colour buttons so the user can see what's set.
                try:
                    tc = ed._current_format_attr('color') or (0, 0, 0)
                    btn_color.setStyleSheet(
                        "font:bold 11pt 'Segoe UI';background:#444;"
                        "border:1px solid #666;border-radius:3px;"
                        "color:rgb(%d,%d,%d);border-bottom:3px solid rgb(%d,%d,%d);"
                        % (tc[0], tc[1], tc[2], tc[0], tc[1], tc[2]))
                    bgc = ed._current_format_attr('background')
                    if bgc:
                        btn_hl.setStyleSheet(
                            "font:bold 11pt 'Segoe UI';color:white;"
                            "border:1px solid #666;border-radius:3px;"
                            "background:rgb(%d,%d,%d);" % (bgc[0], bgc[1], bgc[2]))
                    else:
                        btn_hl.setStyleSheet(
                            "font:bold 11pt 'Segoe UI';color:white;"
                            "border:1px solid #666;border-radius:3px;background:#5a5a2d;")
                except Exception: pass
            except Exception: pass
        ed.cursor_changed.connect(_sync_fmt)
        for _b, _ in _fmt_btns:
            _b.clicked.connect(_sync_fmt)
        self._sync_fmt_toolbar = _sync_fmt
        # reflect the caret's starting format once the runs are loaded
        from PyQt6.QtCore import QTimer as _SFT
        _SFT.singleShot(0, _sync_fmt)
        # Alignment. v4.1.23.36: append U+FE0E (text-presentation selector) so
        # Windows renders these as normal text glyphs instead of blowing them
        # up into large colour EMOJI (the "huge justify icons" bug). Two
        # justify modes: weak = spread spaces on full lines only; force =
        # also stretch with automatic letter spacing.
        _TP = "\uFE0E"
        btn_al  = _btn("⯇"+_TP,  "Align left (Ctrl+L)",   lambda: ed.set_alignment('left'), icon="align-left")
        btn_ac  = _btn("≡"+_TP,  "Align center (Ctrl+E)", lambda: ed.set_alignment('center'), icon="align-center")
        btn_ar  = _btn("⯈"+_TP,  "Align right (Ctrl+R)",  lambda: ed.set_alignment('right'), icon="align-right")
        btn_aj  = _btn("≣"+_TP,  "Justify – spread spaces, full lines only (Ctrl+J)",
                       lambda: ed.set_alignment('justify'))
        btn_ajf = _btn("≣!"+_TP, "Force justify – stretch with automatic letter spacing",
                       lambda: ed.set_alignment('justify_full'), fixed_w=40)
        # v4.1.23.35: register alignment buttons for active-state highlighting.
        _align_btns.extend([(btn_al, 'left'), (btn_ac, 'center'),
                            (btn_ar, 'right'), (btn_aj, 'justify'),
                            (btn_ajf, 'justify_full')])
        for _b, _ in _align_btns:
            _fmt_base[id(_b)] = _b.styleSheet()
            _b.clicked.connect(_sync_fmt)
        # Vertical alignment
        btn_vt = _btn("⤒"+_TP,  "Align top",     lambda: ed.set_vertical_alignment('top'))
        btn_vm = _btn("↕"+_TP,  "Align middle",  lambda: ed.set_vertical_alignment('middle'))
        btn_vb = _btn("⤓"+_TP,  "Align bottom",  lambda: ed.set_vertical_alignment('bottom'))
        # v4.1.23.48: list controls — toggle bullet / numbered list and change
        # the indent level. These create the markers (•/◦/▪ or 1./2./…) that
        # Tab/Shift+Tab and Enter then manage interactively.
        def _ed_then_reflow(fn):
            def _go():
                fn(); self._reflow_current_body(); self._refocus_inline()
            return _go
        btn_ul = _btn("•≣"+_TP, "Bullet list",      _ed_then_reflow(ed.toggle_bullet_list), fixed_w=40)
        btn_ol = _btn("1≣"+_TP, "Numbered list",    _ed_then_reflow(ed.toggle_numbered_list), fixed_w=40)
        btn_ind = _btn("⇥"+_TP, "Indent list item (Tab)",        _ed_then_reflow(ed.list_indent))
        btn_ded = _btn("⇤"+_TP, "Outdent list item (Shift+Tab)", _ed_then_reflow(ed.list_outdent))
        # Confirm / cancel
        btn_ok     = _btn("✓"+_TP, "Apply (Ctrl+Enter)", self._confirm_inline)
        btn_ok.setStyleSheet(btn_ok.styleSheet().replace("background:#444", "background:#2d6e2d"))
        btn_cancel = _btn("✕"+_TP, "Cancel (Esc)",       self._cancel_inline)
        btn_cancel.setStyleSheet(btn_cancel.styleSheet().replace("background:#444", "background:#6e2d2d"))

        # Content groups in display order. v4.1.22.1: the doc-mode body has no
        # Apply/Cancel (the body is permanent; Esc still ends the session).
        row1_items = [btn_b, btn_i, btn_u, btn_s,
                      btn_color, btn_hl, btn_hl_clear]
        if btn_pgnum is not None:
            row1_items.append(btn_pgnum)
        row1_items += [cb_font, sp_size, sp_ls, sp_letsp]
        row2_items = [btn_al, btn_ac, btn_ar, btn_aj, btn_ajf,
                      btn_ul, btn_ol, btn_ind, btn_ded,
                      btn_vt, btn_vm, btn_vb]
        tail_items = [] if is_body else [btn_ok, btn_cancel]
        if is_body:
            btn_ok.hide(); btn_cancel.hide()

        # v4.2.7.4: pin to the TOP of the viewport (Word-style ribbon).
        vp = self.viewport()
        tb_w = max(740, self.width() - 8)

        def _need_w(ws):
            return sum(max(w.sizeHint().width(), w.minimumWidth())
                       for w in ws) + 3 * (len(ws) + 1) + 8

        # v4.2.11.47: the row decision must be IDENTICAL for every session
        # (body / header / design textbox), otherwise the ribbon height would
        # flip 40<->76 between sessions and the band would jump. Sessions
        # differ by up to ~96px of optional buttons (#▾ page-number menu,
        # Apply/Cancel), so always include that allowance in the estimate.
        one_row = (_need_w(row1_items + row2_items + tail_items) + 96) <= tb_w
        rows = ([row1_items + row2_items] if one_row
                else [row1_items, row2_items])
        for ri, items in enumerate(rows):
            rl = QHBoxLayout(); rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(3)
            for wdg in items:
                rl.addWidget(wdg)
            rl.addStretch()
            if ri == len(rows) - 1:
                for wdg in tail_items:
                    rl.addWidget(wdg)
            tb_layout.addLayout(rl)
        tb_h = 40 if one_row else 76
        toolbar.setFixedHeight(tb_h)
        toolbar.setGeometry(4, 4, tb_w, tb_h)
        toolbar.show()
        self._inline_toolbar = toolbar
        # v4.2.11.42: reserve the toolbar band as a viewport margin so the
        # scrollable canvas area starts BELOW it. centerOn / Fit then operate on
        # the area under the ribbon (the scene rect is exactly the page and
        # offered no scroll room to shift it down, so the page used to be
        # centered in the full viewport and tucked under the ribbon).
        try:
            self.setViewportMargins(0, tb_h + 8, 0, 0)
        except Exception:
            pass
        return toolbar

    def _ensure_ribbon_skeleton(self):
        """v4.2.11.49: show the text ribbon from startup (disabled) instead of
        having it pop in -- and shift the page -- on the first text edit. Built
        against a hidden dummy editor; the controls are disabled so the dummy
        bindings can never fire, and the first real session rebuilds the
        contents in place."""
        try:
            from edof.format.objects import TextBox as _TB
            from edof._apps.edof_text_editor import EdofTextEditor as _ETE
            dummy_tb = _TB()
            dummy_ed = _ETE(dummy_tb, dpi=float(self._dpi),
                            page_bg=(255, 255, 255, 255),
                            bg_snapshot=None, is_doc_body=True)
            dummy_ed.hide()
            for _tn in ('_blink_timer', '_render_timer'):
                _t = getattr(dummy_ed, _tn, None)
                if _t is not None:
                    try: _t.stop()
                    except Exception: pass
            prev_role = getattr(self, '_inline_hf_role', None)
            self._inline_hf_role = None     # no #▾ button in the skeleton
            self._build_text_ribbon(dummy_ed, dummy_tb, is_body=True)
            self._inline_hf_role = prev_role
            self._ribbon_dummy_ed = dummy_ed   # keep closures alive
            self._inline_toolbar = None        # no active session
            rb = getattr(self, '_text_ribbon', None)
            if rb is not None:
                rb.setEnabled(False)
                rb.show()
        except Exception:
            import traceback as _tb; _tb.print_exc()

    def _textbox_to_html(self, obj):
        """v4.1.0: Convert TextBox runs to HTML for QTextEdit display."""
        if not hasattr(obj, 'runs') or not obj.runs:
            # Plain fallback
            from html import escape
            return f"<span>{escape(obj.text)}</span>"
        from html import escape
        parts = []
        for run in obj.runs:
            txt = escape(run.text or "").replace("\n", "<br>")
            style_parts = []
            if run.bold:      style_parts.append("font-weight:bold")
            if run.italic:    style_parts.append("font-style:italic")
            if run.underline: style_parts.append("text-decoration:underline")
            if run.font_size: style_parts.append(f"font-size:{run.font_size:.2f}mm")
            if run.font_family: style_parts.append(f"font-family:'{run.font_family}'")
            if run.color and len(run.color) >= 3:
                style_parts.append(f"color:#{run.color[0]:02x}{run.color[1]:02x}{run.color[2]:02x}")
            if style_parts:
                parts.append(f'<span style="{";".join(style_parts)}">{txt}</span>')
            else:
                parts.append(txt)
        return "".join(parts)

    def _html_to_runs(self, html):
        """v4.1.0: Parse QTextEdit HTML output into TextRun list."""
        from edof.format.styles import TextRun
        from PyQt6.QtGui import QTextDocument, QTextCursor
        doc = QTextDocument()
        doc.setHtml(html)
        runs = []
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        while not cursor.atEnd():
            block = cursor.block()
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid() and fragment.length() > 0:
                    text = fragment.text()
                    fmt = fragment.charFormat()
                    f = fmt.font()
                    color_qc = fmt.foreground().color()
                    color = (color_qc.red(), color_qc.green(), color_qc.blue())
                    run = TextRun(
                        text=text,
                        bold=f.bold(),
                        italic=f.italic(),
                        underline=f.underline(),
                        font_family=f.family(),
                        font_size=f.pointSize() if f.pointSize() > 0 else 12.0,
                        color=color,
                    )
                    runs.append(run)
                it += 1
            # Add newline between blocks
            if cursor.movePosition(QTextCursor.MoveOperation.NextBlock):
                if runs:
                    runs[-1].text += "\n"
            else:
                break
        return runs

    def _reposition_inline(self):
        """v4.1.15.7: With QGraphicsProxyWidget the editor lives IN the
        scene and gets its position/size in scene coords. Toolbar stays
        in the viewport. We update both. v4.1.16.5: also handles rotation."""
        if not self._inline_widget or not self._inline_obj: return
        t   = self._inline_obj.transform
        dpi = float(self._dpi)
        scene_x = mm_to_px(t.x, dpi)
        scene_y = mm_to_px(t.y, dpi)
        scene_w = max(1.0, mm_to_px(t.width,  dpi))
        scene_h = max(1.0, mm_to_px(t.height, dpi))
        rotation = float(getattr(t, 'rotation', 0.0) or 0.0)
        if getattr(self, '_inline_proxy', None):
            self._inline_proxy.setPos(scene_x, scene_y)
            self._inline_widget.setFixedSize(int(round(scene_w)), int(round(scene_h)))
            self._inline_proxy.setTransformOriginPoint(scene_w / 2.0, scene_h / 2.0)
            self._inline_proxy.setRotation(rotation)
        if getattr(self, '_inline_border_frame', None):
            try:
                self._inline_border_frame.setRect(
                    QRectF(scene_x, scene_y, scene_w, scene_h))
                self._inline_border_frame.setTransformOriginPoint(
                    scene_x + scene_w / 2.0, scene_y + scene_h / 2.0)
                self._inline_border_frame.setRotation(rotation)
            except Exception: pass
        # Toolbar — use sceneBoundingRect so it follows rotated proxy bbox.
        # v4.1.20.2: in document mode the toolbar pins to the top of the
        # canvas viewport (Word-style ribbon), regardless of where the
        # textbox sits. Floating-near-textbox is the default for free-form
        # design mode but feels wrong for a long flowing document.
        rb = getattr(self, '_text_ribbon', None)
        if rb is not None and rb.isVisible():
            # v4.2.7.4: always pin to the top of the viewport.
            # v4.2.11.47: the ribbon is persistent; keep its current height
            # (1 or 2 rows) and only reflow its width to the view.
            try:
                tb_w = max(740, self.width() - 8)
                cur_h = rb.height() or 40
                rb.setGeometry(4, 4, tb_w, cur_h)
            except Exception:
                pass

    def _confirm_inline(self):
        """v4.1.16.4: drive commit by asking the editor widget to write
        its runs back to the textbox; the widget then emits `committed`
        which triggers cleanup. NOT recursive."""
        if not self._inline_widget or not self._inline_id: return
        pg = self._cur_page()
        obj = pg.get_object(self._inline_id) if pg else None
        # Restore visibility BEFORE commit so user sees correct state
        if obj is not None and hasattr(self, '_inline_was_visible'):
            obj.visible = self._inline_was_visible
        try:
            if hasattr(self._inline_widget, 'commit_to_textbox'):
                # This call writes obj.runs+text and emits `committed`
                # which is wired to _after_inline_commit (cleanup).
                self._inline_widget.commit_to_textbox()
            else:
                # No widget commit method — just clean up
                self._after_inline_commit()
        except Exception:
            import traceback; traceback.print_exc()
            self._after_inline_commit()

    def _after_inline_commit(self):
        """Called after EdofTextEditor.commit_to_textbox writes its data.
        Just cleans up UI and triggers re-render — does NOT restore from
        snapshot (changes are committed).

        v4.1.20: in document mode, if the just-committed textbox was the
        document body (sticky edit), automatically re-enter inline edit
        on it so the user can keep typing without double-clicking.
        v4.1.20.1: sticky re-entry is suppressed when _skip_sticky_reentry
        is set (used by toolbar insert actions so the user can place a new
        object on the canvas instead of being yanked back into the body)."""
        # Capture before cleanup which obj was being edited
        committed_obj = getattr(self, '_inline_obj', None)
        skip_sticky = getattr(self, '_skip_sticky_reentry', False)
        was_doc_body = self._is_document_body(committed_obj)
        # v4.2.11.41: if a header/footer was being edited, persist its runs back
        # to the shared template on doc.body and repaginate so every page picks
        # up the change (with per-page variables re-resolved).
        hf_role = getattr(self, '_inline_hf_role', None)
        hf_even = bool(getattr(self, '_inline_hf_even', False))
        self._inline_hf_role = None
        self._inline_hf_even = False
        if hf_role and committed_obj is not None and self._doc is not None:
            self._skip_sticky_reentry = False   # early return below skips the
            # normal reset at the end of this method; don't leak the flag.
            try:
                body = self._doc.body
                runs = list(getattr(committed_obj, 'runs', []) or [])
                suff = '_even' if hf_even else ''
                setattr(body, f'{hf_role}_runs{suff}', runs)
                # v4.2.11.46: persist the band's box-level style (vertical
                # align, default font, ...) so it survives repagination and
                # applies on every page of this parity.
                try:
                    sd = committed_obj.style.to_dict()
                    setattr(body, f'{hf_role}_style{suff}', sd)
                except Exception:
                    pass
                # v4.2.11.46: keep the view where the user left it -- the
                # repagination + refresh below used to reset scroll and make
                # the page jump around.
                _hsb = self.horizontalScrollBar().value()
                _vsb = self.verticalScrollBar().value()
                self._inline_snapshot = None
                self._cancel_inline()
                from edof.engine.document_paginate import paginate_document
                paginate_document(self._doc, dpi=self._dpi)
                mw = self.parent()
                if mw is not None and hasattr(mw, '_refresh_pages'):
                    try: mw._refresh_pages()
                    except Exception: pass
                if mw is not None and hasattr(mw, '_mark_modified'):
                    try: mw._mark_modified()
                    except Exception: pass
                self._invalidate_page_cache()
                self.schedule_render(0)
                try:
                    self.horizontalScrollBar().setValue(_hsb)
                    self.verticalScrollBar().setValue(_vsb)
                except Exception:
                    pass
                return
            except Exception:
                import traceback as _tb; _tb.print_exc()
                return
        # v4.1.23.26: snapshot the caret format BEFORE teardown so an
        # overflow hop can carry it to the next page (set only if we actually
        # hop below).
        _pre_carry = None
        if was_doc_body:
            ed0 = getattr(self, '_inline_widget', None)
            if ed0 is not None:
                try:
                    _pre_carry = {}
                    for _a in ('font_size','font_family','bold','italic',
                               'underline','strikethrough','color',
                               'line_height','letter_spacing'):
                        _v = ed0._current_format_attr(_a)
                        if _v is not None: _pre_carry[_a] = _v
                    _pre_carry = _pre_carry or None
                except Exception: _pre_carry = None

        self._inline_snapshot = None      # commit succeeded — clear snapshot
        self._cancel_inline()              # cleanup (no rollback since snap is None)

        # v4.1.22: doc-mode auto-overflow flow. After commit, if the just-
        # edited body overflows, push the overflowing paragraphs to the
        # next page's body (creating the page if needed). User-visible
        # effect: typing past the page boundary "flows" into a new page.
        reflowed_target = None
        if was_doc_body and committed_obj is not None:
            try:
                # v4.1.22.1: compute the page index containing the
                # committed object — not self._page_idx, which may have
                # already advanced if commit was triggered by a navigation.
                src_page_idx = None
                for i, _pg in enumerate(self._doc.pages):
                    if committed_obj in _pg.objects:
                        src_page_idx = i; break
                if src_page_idx is None:
                    src_page_idx = self._page_idx
                cursor_at_commit = getattr(self, '_pending_reflow_cursor', None)
                self._pending_reflow_cursor = None
                from edof.engine.document_paginate import paginate_document
                # v4.1.23: Clean document paginate. Treats the doc body as a
                # single paragraph flow (doc.body.paragraphs) and re-flows
                # pages from scratch.
                rp = paginate_document(self._doc,
                                        focus_page=src_page_idx,
                                        focus_cursor=cursor_at_commit,
                                        dpi=self._dpi)
                if rp.get('changed'):
                    reflowed_target = {
                        'reflowed': True,
                        'final_cursor_page_idx': rp.get('cursor_page'),
                        'final_cursor_offset_in_body': rp.get('cursor_offset'),
                        'new_page_idx': rp.get('cursor_page'),
                        'next_body_id': None,
                        'created_page': True,
                    }
                    mw = self.parent()
                    if mw is not None and hasattr(mw, '_refresh_pages'):
                        try: mw._refresh_pages()
                        except Exception: pass
                    if mw is not None and hasattr(mw, '_mark_modified'):
                        try: mw._mark_modified()
                        except Exception: pass
                if self._page_idx >= len(self._doc.pages):
                    self._page_idx = max(0, len(self._doc.pages) - 1)
            except Exception:
                import traceback as _tb; _tb.print_exc()

        self.objectChanged.emit()
        self.schedule_render(0)

        # Sticky-edit in document mode (unless an insert action is in flight)
        if was_doc_body and committed_obj is not None and not skip_sticky:
            from PyQt6.QtCore import QTimer
            if reflowed_target is not None:
                # After reflow, jump to the next page's body so the cursor
                # follows the text that just flowed there.
                new_idx = reflowed_target['new_page_idx']
                next_body_id = reflowed_target['next_body_id']
                # v4.1.23.26: carry the caret format to the page we flow onto.
                self._carry_pending = _pre_carry
                if reflowed_target.get('created_page'):
                    # Notify main window to refresh page list
                    mw = self.parent()
                    if mw is not None and hasattr(mw, '_refresh_pages'):
                        try: mw._refresh_pages()
                        except Exception: pass
                    if mw is not None and hasattr(mw, '_mark_modified'):
                        try: mw._mark_modified()
                        except Exception: pass
                def _hop_to_next():
                    # v4.1.22.2: prefer the final cursor target if reflow
                    # tracked it (covers the case where the user typed at
                    # the end of a large body that cascades over several
                    # new pages — caret follows to the LAST page rather
                    # than getting stranded on the first overflow page).
                    target_page_idx = reflowed_target.get('final_cursor_page_idx')
                    target_cursor_off = reflowed_target.get('final_cursor_offset_in_body')
                    if target_page_idx is None:
                        target_page_idx = reflowed_target['new_page_idx']
                    try: self.set_document(self._doc, target_page_idx)
                    except Exception: pass
                    pg = self._cur_page()
                    if pg is None: return
                    tb = None
                    # Try to use the body at target page
                    for o in pg.objects:
                        name = getattr(o, 'name', '') or ''
                        if name in ('document_body','doc_body') or name.startswith('doc_body'):
                            tb = o; break
                    if tb is not None:
                        self.set_sel_id(tb.id)
                        self._start_inline(tb)
                        if (target_cursor_off is not None
                            and self._inline_widget is not None):
                            try:
                                self._inline_widget._cursor = int(target_cursor_off)
                                self._inline_widget._anchor = None
                                self._inline_widget._invalidate()
                                self._scroll_to_cursor()
                            except Exception: pass
                QTimer.singleShot(60, _hop_to_next)
            else:
                QTimer.singleShot(50, lambda obj=committed_obj: self._start_inline(obj))
        # v4.1.23.44: finished editing an INSERTED object (not the body) in
        # document mode, and not because the user clicked another object
        # (skip_sticky set in that case) → return focus to the document body
        # so the user keeps writing where they left off. This is the
        # "ending an object edit drops you back into the document" behaviour.
        elif (not was_doc_body and committed_obj is not None and not skip_sticky
              and self._doc is not None
              and getattr(self._doc, 'mode', '') == 'document'):
            from PyQt6.QtCore import QTimer
            def _reenter_body():
                pg = self._cur_page()
                if pg is None: return
                for o in pg.objects:
                    if self._is_document_body(o):
                        self.set_sel_id(o.id); self._start_inline(o); break
            QTimer.singleShot(50, _reenter_body)
        # Always clear the flag after one commit
        self._skip_sticky_reentry = False

    def _is_document_body(self, obj) -> bool:
        """v4.1.23: True iff `obj` is a DocumentTextBox (or, for legacy
        files not yet migrated, a TextBox named 'document_body'). The
        isinstance path is the canonical test; the name fallback is just
        defensive for documents loaded before migration ran."""
        if obj is None: return False
        try:
            from edof.format.document_boxes import DocumentTextBox
            if isinstance(obj, DocumentTextBox):
                return True
        except Exception:
            pass
        doc = getattr(self, '_doc', None)
        if doc is None or getattr(doc, 'mode', '') != 'document':
            return False
        from edof.format.objects import TextBox as _TB
        if not isinstance(obj, _TB):
            return False
        name = getattr(obj, 'name', '') or ''
        return name in ('document_body', 'doc_body') or name.startswith('doc_body')

    def _on_inline_overflow(self, is_overflow: bool, tb):
        """v4.1.20.1: Originally showed a status hint suggesting the user
        press Ctrl+Enter to start a new page. v4.1.22.2: now that overflow
        triggers auto-flow (with cascading), the hint is misleading and
        also cycled noisily (blinking) as the cascade unfolded — so it's
        suppressed for doc-body textboxes. Other textboxes still get no
        hint either; the red border on the editor already signals the
        problem clearly enough for the design-mode case."""
        return

    def _on_new_page_requested(self, tb):
        # v4.2.11.37: any exception escaping this slot aborts the whole app
        # (PyQt6 qFatal) -- reproduced exactly that on Ctrl+Enter. Run the page
        # break inside a guard; on failure log it and leave the editor alive.
        try:
            return self._do_new_page_requested(tb)
        except Exception:
            import traceback as _tb_mod
            _tb_mod.print_exc()
            try:
                from edof.engine.debug_log import log as _dlog
                _dlog("canvas._on_new_page_requested EXCEPTION",
                      err=_tb_mod.format_exc()[-1500:])
            except Exception:
                pass
            try:
                self.schedule_render(0)
            except Exception:
                pass
            return

    def _do_new_page_requested(self, tb):
        """v4.1.22.14: Ctrl+Enter handling.

        In document mode (body textbox): WORD-STYLE HARD PAGE BREAK.
        The editor already inserted a '\\n' at the caret to split the
        current paragraph; this handler:
          1. syncs the editor → tb,
          2. projects all TextBoxes back into doc.body.paragraphs,
          3. marks the paragraph CONTAINING the caret as
             page_break_before=True (= the newly-created post-break para),
          4. repaginates — the rule pushes that paragraph to a fresh page,
          5. hops the editor to the new page.

        For non-doc-mode: just commit (legacy behaviour)."""
        if not self._is_document_body(tb):
            if self._inline_widget is not None:
                try: self._inline_widget.commit_to_textbox()
                except Exception: self._after_inline_commit()
            return
        if self._inline_widget is None:
            return

        from edof.engine.document_paginate import (
            _sync_body_from_textboxes, paginate_document,
            find_document_body_on_page, runs_text)

        # 1. Sync the editor's current state (with the just-inserted \n)
        # to its TextBox runs.
        try:
            self._inline_widget.sync_to_tb_silent()
            self._inline_snapshot = None
        except Exception:
            return

        # Cursor offset in the current body, AFTER the inserted \n.
        cursor_in_tb = int(getattr(self._inline_widget, '_cursor', 0))

        # 2. Project page TextBoxes → doc.body.paragraphs.
        _sync_body_from_textboxes(self._doc)

        cur_idx = None
        for i, pg in enumerate(self._doc.pages):
            if tb in pg.objects:
                cur_idx = i; break
        if cur_idx is None:
            return

        # 3. Compute global char offset of caret, then map to paragraph.
        global_offset = 0
        for i, pg in enumerate(self._doc.pages):
            t_obj = find_document_body_on_page(pg)
            if t_obj is None: continue
            if i == cur_idx:
                global_offset += cursor_in_tb
                break
            tx = runs_text(t_obj.runs or [])
            global_offset += len(tx)
            if tx and not tx.endswith('\n'):
                global_offset += 1

        paragraphs = (self._doc.body.paragraphs
                       if self._doc.body else [])
        running = 0
        target_para_idx = 0
        for i, p in enumerate(paragraphs):
            plen = len(p.plain_text())
            if global_offset <= running + plen:
                target_para_idx = i
                break
            running += plen + 1
            target_para_idx = i + 1 if i + 1 < len(paragraphs) else i

        # 4. Mark the target paragraph as page_break_before.
        if 0 <= target_para_idx < len(paragraphs):
            paragraphs[target_para_idx].page_break_before = True

        # 5. Paginate with the caret as focus.
        rp = paginate_document(self._doc,
                                focus_page=cur_idx,
                                focus_cursor=cursor_in_tb,
                                dpi=self._dpi,
                                skip_sync=True)

        # 6. Notify main window and hop the editor.
        mw = self.parent()
        if mw is not None and hasattr(mw, '_refresh_pages'):
            try: mw._refresh_pages()
            except Exception: pass
        if mw is not None and hasattr(mw, '_mark_modified'):
            try: mw._mark_modified()
            except Exception: pass

        final_page = rp.get('cursor_page')
        final_off  = rp.get('cursor_offset')
        if final_page is None: final_page = cur_idx
        if final_off  is None: final_off  = cursor_in_tb
        if final_page >= len(self._doc.pages):
            final_page = len(self._doc.pages) - 1

        # If caret stays on same page, refresh in place; else hop.
        if (final_page == cur_idx
            and cur_idx < len(self._doc.pages)
            and tb in self._doc.pages[cur_idx].objects):
            try:
                self._inline_widget.refresh_from_tb(final_off)
                self.schedule_render(0)
                self._scroll_to_cursor()
            except Exception:
                import traceback as _tb_mod; _tb_mod.print_exc()
            return

        # Hop path
        target_page_idx = final_page
        target_body = find_document_body_on_page(self._doc.pages[target_page_idx])
        if target_body is None: return

        from PyQt6.QtCore import QTimer
        self._skip_sticky_reentry = True
        try: self._cancel_inline()
        except Exception: pass

        def _hop():
            try: self.set_document(self._doc, target_page_idx)
            except Exception: pass
            self.set_sel_id(target_body.id)
            self._start_inline(target_body)
            if self._inline_widget is not None and final_off is not None:
                try:
                    self._inline_widget._cursor = max(0, int(final_off))
                    self._inline_widget._anchor = None
                    self._inline_widget._invalidate()
                    self._scroll_to_cursor()
                    # v4.1.23.5: editor._invalidate defers layout rebuild
                    # via a 20ms render timer, so the synchronous scroll
                    # above reads a stale (or empty) layout. Schedule a
                    # second scroll after layout settles.
                    QTimer.singleShot(60, self._scroll_to_cursor)
                except Exception: pass
        QTimer.singleShot(40, _hop)

    def _scroll_to_cursor(self):
        """v4.1.22.2: ensure the inline editor's caret is visible in the
        viewport — auto-scroll the canvas if the user typed past the
        bottom (or top) of the visible area, Word-style.

        v4.1.22.3: clamp the target Y to the textbox's bottom edge. The
        reflow engine will move overflowing text onto the next page
        shortly; scrolling below the body would briefly expose dead canvas
        area beneath the page and make the caret appear stranded."""
        ed = getattr(self, '_inline_widget', None)
        proxy = getattr(self, '_inline_proxy', None)
        if ed is None or proxy is None:
            return
        try:
            # v4.1.23.20: make sure the layout exists before we look for the
            # caret line. When this is called right after hopping to another
            # page the freshly-created editor may not have rendered yet, so
            # _layout would be None and we'd silently skip scrolling — which
            # is exactly why arrowing up to the previous page used to leave
            # the view at the page top instead of following the caret down.
            try: ed._ensure_render()
            except Exception: pass
            layout = getattr(ed, '_layout', None)
            cursor = int(getattr(ed, '_cursor', 0))
            if layout is None: return
            target_line = None
            for ln in layout.lines:
                for c in ln.chars:
                    if c.char_idx >= cursor:
                        target_line = ln; break
                if target_line is not None: break
            if target_line is None and layout.lines:
                target_line = layout.lines[-1]
            if target_line is None: return
            line_top = target_line.top
            line_h   = target_line.height
            sp = proxy.scenePos()
            cy_scene_top    = sp.y() + line_top
            cy_scene_bottom = sp.y() + line_top + line_h
            # Clamp to body's bottom edge in scene coords so we never
            # scroll below the page (overflow lines are handled by reflow,
            # not by exposing them).
            try:
                obj = getattr(self, '_inline_obj', None)
                if obj is not None:
                    body_bot = sp.y() + ed.height()
                    if cy_scene_bottom > body_bot:
                        cy_scene_bottom = body_bot
            except Exception: pass
            from PyQt6.QtCore import QPointF
            vp_rect = self.viewport().rect()
            top_left  = self.mapToScene(vp_rect.topLeft())
            bot_right = self.mapToScene(vp_rect.bottomRight())
            margin = max(20.0, line_h * 1.5)
            scroll_to_y = None
            if cy_scene_bottom > bot_right.y() - margin:
                scroll_to_y = cy_scene_bottom - (bot_right.y() - top_left.y()) * 0.7
            elif cy_scene_top < top_left.y() + margin:
                scroll_to_y = cy_scene_top - margin
            if scroll_to_y is not None:
                center_x = (top_left.x() + bot_right.x()) / 2.0
                target_y = scroll_to_y + (bot_right.y() - top_left.y()) / 2.0
                self.centerOn(QPointF(center_x, target_y))
        except Exception:
            pass

    def _on_idle_overflow_reached(self, tb):
        """v4.1.23: idle timer fired in a doc body. Run the clean
        paginate_document pass from edof.engine.document_paginate and:
          • If caret stayed on the same page: refresh editor in place.
          • If caret moved pages: tear down + hop + restart inline.
        """
        try:
            from edof.engine.debug_log import log as _dlog
        except Exception:
            _dlog = lambda *a, **k: None
        if not self._is_document_body(tb):
            _dlog("canvas.idle.skip", reason="not doc body")
            return
        if self._inline_widget is None:
            _dlog("canvas.idle.skip", reason="no inline widget")
            return
        try:
            from edof.engine.document_paginate import (
                paginate_document, find_document_body_on_page)
        except Exception:
            return

        cur_idx = None
        for i, pg in enumerate(self._doc.pages):
            if tb in pg.objects:
                cur_idx = i; break
        if cur_idx is None:
            _dlog("canvas.idle.skip", reason="tb not in any page")
            return

        cursor_before = int(getattr(self._inline_widget, '_cursor', 0))
        _dlog("canvas.idle.entry",
               page=cur_idx, cursor=cursor_before,
               tb_text=(tb.text or "")[:80])

        # 1. Sync editor → tb
        try:
            self._inline_widget.sync_to_tb_silent()
            self._inline_snapshot = None
        except Exception:
            return
        # v4.1.23.26: grab the caret format now (editor still alive) so an
        # overflow hop below can carry it to the next page.
        _idle_carry = None
        try:
            _ied = self._inline_widget
            if _ied is not None:
                _idle_carry = {}
                for _a in ('font_size','font_family','bold','italic',
                           'underline','strikethrough','color',
                           'line_height','letter_spacing'):
                    _v = _ied._current_format_attr(_a)
                    if _v is not None: _idle_carry[_a] = _v
                _idle_carry = _idle_carry or None
        except Exception: _idle_carry = None

        # 2. Paginate
        rp = paginate_document(self._doc,
                                focus_page=cur_idx,
                                focus_cursor=cursor_before,
                                dpi=self._dpi,
                                boundary_to_focus_page=True)
        _dlog("canvas.idle.repaginate",
               changed=rp.get('changed'),
               pages=rp.get('pages_count'),
               cursor_page=rp.get('cursor_page'),
               cursor_offset=rp.get('cursor_offset'))
        _changed = rp.get('changed')
        # v4.1.23.57: mark the document modified whenever the inline body editor
        # reports an edit, even if pagination did not restructure (e.g. typing
        # on a single line). This must happen BEFORE the early return below, or
        # editing one line never sets _modified and closing did not prompt to
        # save.
        try:
            iw = getattr(self, '_inline_widget', None)
            if iw is not None and getattr(iw, '_edited', False):
                mw = self.parent()
                if mw is not None and hasattr(mw, '_mark_modified'):
                    try: mw._mark_modified()
                    except Exception: pass
                iw._edited = False
        except Exception:
            pass
        # v4.1.23.21: only react when pagination actually changed the
        # document. The 4.1.23.18 "hop on boundary even if unchanged" rule
        # caused a snap-back: opening a full page placed the caret at its
        # end (== the page boundary, which maps to the next page), and this
        # idle pass then yanked the view straight back to the next page.
        # Boundary fall-through is handled by the navigation/merge handlers,
        # not here.
        if not _changed:
            return

        if _changed:
            mw = self.parent()
            if mw is not None and hasattr(mw, '_refresh_pages'):
                try: mw._refresh_pages()
                except Exception: pass
            if mw is not None and hasattr(mw, '_mark_modified'):
                try: mw._mark_modified()
                except Exception: pass

        final_page = rp.get('cursor_page')
        final_off  = rp.get('cursor_offset')
        if final_page is None: final_page = cur_idx
        if final_off  is None: final_off  = cursor_before
        if final_page >= len(self._doc.pages):
            final_page = len(self._doc.pages) - 1

        # In-place refresh path
        if (final_page == cur_idx and cur_idx < len(self._doc.pages)
            and tb in self._doc.pages[cur_idx].objects):
            _dlog("canvas.idle.inplace_refresh", final_off=final_off)
            try:
                self._inline_widget.refresh_from_tb(final_off)
                self.schedule_render(0)
                self._scroll_to_cursor()
            except Exception:
                import traceback as _tb; _tb.print_exc()
            return

        # Hop to another page
        _dlog("canvas.idle.hop", from_page=cur_idx, to_page=final_page,
               final_off=final_off)
        target_page_idx = final_page
        target_body = find_document_body_on_page(self._doc.pages[target_page_idx])
        if target_body is None: return
        # v4.1.23.26: carry caret format onto the page we flow to.
        self._carry_pending = _idle_carry

        from PyQt6.QtCore import QTimer
        self._skip_sticky_reentry = True
        try: self._cancel_inline()
        except Exception: pass

        def _hop():
            try: self.set_document(self._doc, target_page_idx)
            except Exception: pass
            self.set_sel_id(target_body.id)
            self._start_inline(target_body)
            if self._inline_widget is not None and final_off is not None:
                try:
                    self._inline_widget._cursor = max(0, int(final_off))
                    self._inline_widget._anchor = None
                    self._inline_widget._invalidate()
                    self._scroll_to_cursor()
                    # v4.1.23.5: editor._invalidate defers layout rebuild
                    # via a 20ms render timer, so the synchronous scroll
                    # above reads a stale (or empty) layout. Schedule a
                    # second scroll after layout settles.
                    QTimer.singleShot(60, self._scroll_to_cursor)
                except Exception: pass
        QTimer.singleShot(40, _hop)

    def _on_merge_with_previous(self, tb):
        """v4.1.22.1: backspace at cursor=0 inside a doc body. Find the
        previous page's body, commit current edit, then either:
          • If current body has content: append it to previous body's runs
            and remove the (now empty) current page.
          • If current body is empty: just remove the current page.
        After merge, switch to previous page and re-enter inline edit with
        cursor at the merge boundary."""
        if not self._is_document_body(tb): return
        doc = self._doc
        if doc is None: return
        # Locate current page
        cur_idx = None
        for i, pg in enumerate(doc.pages):
            if tb in pg.objects:
                cur_idx = i; break
        if cur_idx is None or cur_idx <= 0:
            return    # no previous page
        prev_pg = doc.pages[cur_idx - 1]
        prev_body = None
        for o in prev_pg.objects:
            name = getattr(o, 'name', '') or ''
            if name in ('document_body','doc_body') or name.startswith('doc_body'):
                prev_body = o; break
        if prev_body is None: return

        # Commit current edit so its runs are written back to tb
        self._skip_sticky_reentry = True
        if self._inline_widget is not None:
            try: self._inline_widget.commit_to_textbox()
            except Exception: self._after_inline_commit()

        # v4.1.23.8: Backspace at the start of a non-first page should
        # delete the previous '\n' (= the implicit paragraph break that
        # caused the page split), Word-style. Previously we just
        # concatenated prev + cur content, which meant the total char
        # count was unchanged — paginate then re-split the merged body
        # into the same two pages, leaving the user back where they
        # started (and worse, the editor's stale _runs from the merged
        # state would get sync'd back on the next idle, doubling the
        # page 1 content).
        from edof.engine.document_paginate import runs_text
        cur_runs = list(tb.runs or [])
        prev_runs = list(prev_body.runs or [])
        cur_text = runs_text(cur_runs)
        prev_text = runs_text(prev_runs)

        # Strip the trailing '\n' from prev_runs (it WAS the page break
        # terminator). After this, the two run lists join naturally.
        stripped = False
        if prev_text.endswith('\n'):
            while prev_runs and not (prev_runs[-1].text or ""):
                prev_runs.pop()
            if prev_runs:
                last = prev_runs[-1]
                if last.text == '\n':
                    prev_runs.pop()
                elif last.text and last.text.endswith('\n'):
                    last.text = last.text[:-1]
                stripped = True

        # Join: prev (now without trailing '\n') + cur
        prev_runs.extend(cur_runs)
        prev_body.runs = prev_runs
        prev_body.text = runs_text(prev_runs)

        # Cursor target = end of (stripped) prev_text. If we stripped a
        # '\n', the cursor lands at the position where it used to be,
        # which is now one char earlier.
        merge_cursor = len(prev_text) - (1 if stripped else 0)
        if merge_cursor < 0: merge_cursor = 0

        # Remove current page from doc
        try: doc.pages.pop(cur_idx)
        except Exception: pass
        mw = self.parent() if self.parent() else None
        if mw is not None and hasattr(mw, '_refresh_pages'):
            try: mw._refresh_pages()
            except Exception: pass
        if mw is not None and hasattr(mw, '_mark_modified'):
            try: mw._mark_modified()
            except Exception: pass
        # Switch canvas to previous page
        new_idx = cur_idx - 1
        from PyQt6.QtCore import QTimer
        def _hop_back():
            # v4.1.23.8: paginate FIRST so prev_body's tb is re-sliced
            # to its final content. THEN start_inline so the editor
            # reads the correct (post-paginate) runs into _runs. The
            # old order (start_inline → paginate) meant the editor
            # opened with the pre-paginate merged content, then the
            # next idle's sync_to_tb wrote that stale content back to
            # the tb, doubling the page-1 content on every backspace
            # cycle.
            from edof.engine.document_paginate import (
                paginate_document, find_document_body_on_page)
            rp = {}
            try:
                rp = paginate_document(doc, focus_page=new_idx,
                                        focus_cursor=merge_cursor, dpi=self._dpi) or {}
            except Exception: pass
            # Honor paginate's cursor placement — after the strip+merge,
            # the merged flow may re-split differently, so the caret's
            # final page/offset is whatever paginate computed (usually
            # new_idx, but be robust if content reflowed).
            target_page = rp.get('cursor_page', new_idx)
            target_off  = rp.get('cursor_offset', merge_cursor)
            if target_off is None:
                target_off = merge_cursor
            if target_page is None or target_page >= len(doc.pages):
                target_page = min(new_idx, max(0, len(doc.pages) - 1))
            target_body = None
            try:
                target_body = find_document_body_on_page(doc.pages[target_page])
            except Exception: pass
            if target_body is None:
                target_body = prev_body
            try: self.set_document(doc, target_page)
            except Exception: pass
            self.set_sel_id(target_body.id)
            self._start_inline(target_body)
            # Position cursor at the paginate-computed offset (clamped)
            if self._inline_widget is not None:
                try:
                    page_len = len(target_body.text or "")
                    self._inline_widget._cursor = max(0, min(int(target_off), page_len))
                    self._inline_widget._anchor = None
                    self._inline_widget._invalidate()
                except Exception: pass
            self.schedule_render(0)
        QTimer.singleShot(60, _hop_back)


    def _on_merge_with_next(self, tb):
        """v4.1.23.20: Delete at cursor==len inside a doc body. Forward-delete
        across the page boundary: pull the next page's content up into this
        body, removing exactly ONE character (the one to the right of the
        caret in the unified flow), Word-style. Mirror of
        _on_merge_with_previous. The caret stays put at the boundary."""
        if not self._is_document_body(tb): return
        doc = self._doc
        if doc is None: return
        from edof.engine.document_paginate import (
            paginate_document, find_document_body_on_page, runs_text)
        # Locate current page + the next page's body
        cur_idx = None
        for i, pg in enumerate(doc.pages):
            if tb in pg.objects:
                cur_idx = i; break
        if cur_idx is None or cur_idx >= len(doc.pages) - 1:
            return    # no next page → nothing to pull
        next_body = find_document_body_on_page(doc.pages[cur_idx + 1])
        if next_body is None: return

        # Commit current edit so tb.runs is current
        self._skip_sticky_reentry = True
        if self._inline_widget is not None:
            try: self._inline_widget.commit_to_textbox()
            except Exception: self._after_inline_commit()

        cur_runs = list(tb.runs or [])
        next_runs = list(next_body.runs or [])
        cur_text = runs_text(cur_runs)
        next_text = runs_text(next_runs)
        merge_cursor = len(cur_text)   # caret stays at the boundary

        # Forward-delete removes the single character to the right of the
        # caret = the FIRST character of the next page's content. If the
        # next body is empty we simply absorb the (empty) page.
        if next_text:
            for r in next_runs:
                if r.text:
                    r.text = r.text[1:]
                    break

        # Join cur + (next minus its first char) into the current body
        cur_runs.extend(next_runs)
        tb.runs = cur_runs
        tb.text = runs_text(cur_runs)

        # Drop the now-absorbed next page
        try: doc.pages.pop(cur_idx + 1)
        except Exception: pass
        mw = self.parent() if self.parent() else None
        if mw is not None and hasattr(mw, '_refresh_pages'):
            try: mw._refresh_pages()
            except Exception: pass
        if mw is not None and hasattr(mw, '_mark_modified'):
            try: mw._mark_modified()
            except Exception: pass

        from PyQt6.QtCore import QTimer
        def _stay():
            rp = {}
            try:
                rp = paginate_document(doc, focus_page=cur_idx,
                                        focus_cursor=merge_cursor, dpi=self._dpi) or {}
            except Exception: pass
            target_page = rp.get('cursor_page', cur_idx)
            target_off  = rp.get('cursor_offset', merge_cursor)
            if target_off is None: target_off = merge_cursor
            if target_page is None or target_page >= len(doc.pages):
                target_page = min(cur_idx, max(0, len(doc.pages) - 1))
            target_body = None
            try:
                target_body = find_document_body_on_page(doc.pages[target_page])
            except Exception: pass
            if target_body is None:
                target_body = tb
            try: self.set_document(doc, target_page)
            except Exception: pass
            self.set_sel_id(target_body.id)
            self._start_inline(target_body)
            if self._inline_widget is not None:
                try:
                    page_len = len(target_body.text or "")
                    self._inline_widget._cursor = max(0, min(int(target_off), page_len))
                    self._inline_widget._anchor = None
                    self._inline_widget._invalidate()
                except Exception: pass
            self.schedule_render(0)
        QTimer.singleShot(60, _stay)


    def _on_navigate_above(self, tb):
        """v4.1.22.4: Up/PgUp pressed while caret is on the first line of
        a doc body — hop to the previous page's body and place caret on
        its LAST line, Word-style."""
        if not self._is_document_body(tb): return
        doc = self._doc
        if doc is None: return
        cur_idx = None
        for i, pg in enumerate(doc.pages):
            if tb in pg.objects:
                cur_idx = i; break
        if cur_idx is None or cur_idx <= 0:
            return
        prev_pg = doc.pages[cur_idx - 1]
        prev_body = None
        for o in prev_pg.objects:
            name = getattr(o, 'name', '') or ''
            if name in ('document_body','doc_body') or name.startswith('doc_body'):
                prev_body = o; break
        if prev_body is None: return
        # Commit current edit so caret state on this body is saved
        self._skip_sticky_reentry = True
        if self._inline_widget is not None:
            try: self._inline_widget.commit_to_textbox()
            except Exception: self._after_inline_commit()
        # Cursor target = the previous body's LAST VISIBLE line. The
        # previous page is never the last page (we came from a later one),
        # so its text ends with the page-boundary '\n' whose empty line is
        # suppressed in the editor. Landing at len() would put the caret on
        # that boundary (which belongs to this page, not the previous one),
        # so target the position just before the final '\n' — the last line
        # actually drawn inside the previous page's body.
        prev_text = getattr(prev_body, 'text', '') or ''
        if prev_text.endswith('\n'):
            target_offset = len(prev_text) - 1
        else:
            target_offset = len(prev_text)
        from PyQt6.QtCore import QTimer
        def _hop_up():
            try: self.set_document(doc, cur_idx - 1)
            except Exception: pass
            self.set_sel_id(prev_body.id)
            self._start_inline(prev_body)
            if self._inline_widget is not None:
                try:
                    self._inline_widget._cursor = target_offset
                    self._inline_widget._anchor = None
                    self._inline_widget._invalidate()
                    self._scroll_to_cursor()
                    # v4.1.23.20: scene position of the freshly placed page
                    # may settle a tick later — scroll again so the caret on
                    # the previous page's LAST line is brought into view
                    # (not the page top).
                    QTimer.singleShot(80, self._scroll_to_cursor)
                except Exception: pass
        QTimer.singleShot(60, _hop_up)

    def _on_navigate_below(self, tb):
        """v4.1.22.4: Down/PgDown pressed while caret is on the last line
        of a doc body — hop to the next page's body and place caret on
        its FIRST line."""
        if not self._is_document_body(tb): return
        doc = self._doc
        if doc is None: return
        cur_idx = None
        for i, pg in enumerate(doc.pages):
            if tb in pg.objects:
                cur_idx = i; break
        if cur_idx is None: return
        if cur_idx + 1 >= len(doc.pages):
            return
        next_pg = doc.pages[cur_idx + 1]
        next_body = None
        for o in next_pg.objects:
            name = getattr(o, 'name', '') or ''
            if name in ('document_body','doc_body') or name.startswith('doc_body'):
                next_body = o; break
        if next_body is None: return
        self._skip_sticky_reentry = True
        if self._inline_widget is not None:
            try: self._inline_widget.commit_to_textbox()
            except Exception: self._after_inline_commit()
        from PyQt6.QtCore import QTimer
        def _hop_down():
            try: self.set_document(doc, cur_idx + 1)
            except Exception: pass
            self.set_sel_id(next_body.id)
            self._start_inline(next_body)
            if self._inline_widget is not None:
                try:
                    self._inline_widget._cursor = 0
                    self._inline_widget._anchor = None
                    self._inline_widget._invalidate()
                    self._scroll_to_cursor()
                except Exception: pass
        QTimer.singleShot(60, _hop_down)


    def _after_inline_cancel(self):
        """Called when user presses Esc — rolls back to snapshot then
        cleans up."""
        # Leave snapshot intact; _cancel_inline will restore from it
        self._cancel_inline()
        self.objectChanged.emit()
        self.schedule_render(0)

    def _cancel_inline(self):
        # v4.1.1/4.1.7: restore visibility AND text snapshot so cancelling
        # leaves the textbox exactly as it was before edit.
        obj = getattr(self, '_inline_obj', None)
        if obj is not None and hasattr(self, '_inline_was_visible'):
            obj.visible = self._inline_was_visible
        snap = getattr(self, '_inline_snapshot', None)
        if obj is not None and snap is not None:
            try:
                obj.text = snap['text']
                obj.runs = snap['runs']
                obj.style.font_size = snap['font_size']
                obj.transform.width  = snap['width']
                obj.transform.height = snap['height']
                if 'alignment' in snap:
                    obj.style.alignment = snap['alignment']
                if 'vertical_align' in snap:
                    obj.style.vertical_align = snap['vertical_align']
                # v4.1.21: restore per-paragraph alignments on cancel
                if 'paragraph_alignments' in snap:
                    obj.paragraph_alignments = dict(snap['paragraph_alignments'] or {})
            except Exception:
                pass
        self._inline_snapshot = None
        if getattr(self, '_inline_toolbar', None):
            # v4.2.11.47: the ribbon is persistent -- ending a session only
            # DISABLES its controls. It stays visible and the reserved band
            # stays put, so the page never jumps on commit/cancel/sticky
            # cycles. It is hidden only when the document is replaced
            # (set_document).
            try:
                self._inline_toolbar.setEnabled(False)
            except Exception: pass
            self._inline_toolbar = None
        # v4.1.15.7: remove scene-based dashed border rect
        if getattr(self, '_inline_border_frame', None):
            try:
                self.scene().removeItem(self._inline_border_frame)
            except Exception: pass
            self._inline_border_frame = None
        # v4.1.16.2: clean up widget+proxy WITHOUT double-delete.
        # QGraphicsProxyWidget OWNS the wrapped widget. We:
        #   1. Detach the widget from the proxy (proxy.setWidget(None))
        #   2. Remove proxy from scene
        #   3. deleteLater on BOTH widget and proxy in that order
        # to ensure neither is referenced before its destruction.
        proxy = getattr(self, '_inline_proxy', None)
        widget = getattr(self, '_inline_widget', None)
        self._inline_proxy = None
        self._inline_widget = None
        if proxy is not None:
            try:
                proxy.setWidget(None)   # detach widget from proxy
            except Exception: pass
            try:
                self.scene().removeItem(proxy)
            except Exception: pass
            # Defer deletion until after the current event has processed
            try:
                QTimer.singleShot(0, lambda p=proxy: (
                    p.deleteLater() if p is not None else None))
            except Exception: pass
        if widget is not None:
            try:
                # v4.2.11.37: stop the widget's own timers (render debounce,
                # cursor blink) BEFORE the deferred delete so a queued timeout
                # can't land on a half-destroyed widget.
                for _tn in ('_render_timer', '_blink_timer'):
                    _t = getattr(widget, _tn, None)
                    if _t is not None:
                        try: _t.stop()
                        except Exception: pass
                widget.hide()
                widget.setParent(None)
                QTimer.singleShot(0, lambda w=widget: (
                    w.deleteLater() if w is not None else None))
            except Exception: pass
        self._inline_id = None
        self._inline_obj = None
        self.schedule_render(0)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self,event):
        btn=event.button()
        # v4.1.22.3: middle button always starts pan, regardless of any
        # other interaction mode (inline edit, path edit, rect-draw). This
        # is the standard "press wheel to pan" UX users expect.
        if btn == Qt.MouseButton.MiddleButton:
            self._pan_start = event.pos()
            self._pan_scroll0 = (self.horizontalScrollBar().value(),
                                   self.verticalScrollBar().value())
            self.viewport().setCursor(tcur('hand_grab', Qt.CursorShape.ClosedHandCursor))
            event.accept(); return
        # v4.1.16.4: when inline edit is active and user clicks outside
        # both the editor (proxy widget) AND the toolbar, auto-commit.
        # This is more reliable than the previous focusOutEvent approach
        # which had race conditions with the toolbar children.
        if self._inline_widget is not None:
            click_in_proxy = False
            click_in_toolbar = False
            hit_other_obj = False
            try:
                sp = self.mapToScene(event.pos())
                if self._inline_proxy is not None:
                    click_in_proxy = self._inline_proxy.sceneBoundingRect().contains(sp)
            except Exception: pass
            try:
                if self._inline_toolbar is not None and self._inline_toolbar.isVisible():
                    click_in_toolbar = self._inline_toolbar.geometry().contains(event.pos())
            except Exception: pass
            # v4.1.20.8: in doc mode the body textbox spans the whole page
            # area, so click_in_proxy is true everywhere — blocking the user
            # from selecting other inserted objects (shapes/images) under
            # the body. Check whether the click point hits a non-body object
            # at higher layer; if it does, commit and let normal selection
            # handling pick it.
            if (click_in_proxy and self._doc is not None
                and getattr(self._doc, 'mode', '') == 'document'):
                try:
                    pg = self._cur_page()
                    if pg is not None:
                        sp = self.mapToScene(event.pos())
                        from edof.engine.transform import px_to_mm
                        click_x_mm = px_to_mm(sp.x(), self._dpi)
                        click_y_mm = px_to_mm(sp.y(), self._dpi)
                        for o in reversed(pg.sorted_objects()):
                            if o.id == self._inline_id: continue
                            name = getattr(o, 'name', '') or ''
                            if (name in ('document_body', 'doc_body')
                                or name.startswith('doc_body')):
                                continue
                            t = o.transform
                            ox, oy = t.x, t.y
                            ow, oh = t.width or 0, t.height or 0
                            if (ox <= click_x_mm <= ox + ow and
                                oy <= click_y_mm <= oy + oh):
                                hit_other_obj = True; break
                except Exception:
                    pass
            if (not click_in_proxy and not click_in_toolbar) or hit_other_obj:
                # Click is outside the editor / on a different object →
                # commit changes and let normal handling continue.
                self._skip_sticky_reentry = True
                self._confirm_inline()
                # Fall through to normal handling so the click can select
                # another object or start a new action.
            else:
                # Inside editor or toolbar — forward, scene routes to proxy
                super().mousePressEvent(event); return
        # v4.1.1: hand tool — left button starts panning
        if btn==Qt.MouseButton.LeftButton and getattr(self, '_hand_tool', False):
            self._pan_start=event.pos()
            self._pan_scroll0=(self.horizontalScrollBar().value(),
                               self.verticalScrollBar().value())
            self.viewport().setCursor(tcur('hand_grab', Qt.CursorShape.ClosedHandCursor))
            event.accept(); return
        if btn==Qt.MouseButton.MiddleButton:
            self._pan_start=event.pos()
            self._pan_scroll0=(self.horizontalScrollBar().value(),
                               self.verticalScrollBar().value())
            self.viewport().setCursor(tcur('hand_grab', Qt.CursorShape.ClosedHandCursor))
            event.accept(); return

        # v4.1.0/4.1.1/4.1.5/4.1.10: path edit mode — pick up a handle if clicked
        # _sp() already returns scene-space coords; do NOT mapToScene again.
        if btn == Qt.MouseButton.LeftButton and getattr(self, '_path_edit_obj_id', None):
            sp = self._sp(event)
            hit = None
            # v4.1.11.1: iterate in REVERSE so the most-recently-drawn handle
            # (visually on top in z-order) wins ties when handles overlap.
            for h in reversed(self._path_edit_handles):
                if h.data(0) is None: continue
                rect = h.sceneBoundingRect()
                grown = rect.adjusted(-2, -2, 2, 2)
                if grown.contains(sp):
                    hit = h; break
            if hit is not None:
                # v4.1.10/4.1.10.2: update selection set when clicking an ENDPOINT
                # (control point clicks don't change anchor selection)
                ci = hit.data(0); kind = hit.data(2)
                ctrl_held = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                # v4.1.11: Ctrl+click on anchor → grab the tangent_out (creating
                # it if needed). Lets the user drag a tangent directly off an
                # anchor for fast corner→bezier conversion.
                if kind == 'endpoint' and ctrl_held:
                    page = self._cur_page()
                    obj = page.get_object(self._path_edit_obj_id) if page else None
                    if obj:
                        # Determine anchor index (ci IS the cmd index = anchor index)
                        ai = ci
                        cur_type = self._anchor_type(obj, ai)
                        # Convert corner/auto to smooth so tangents are visible
                        if cur_type == "corner" or cur_type == "auto":
                            self._set_point_type(obj, ai, "smooth")
                        # Refresh handles so the tangent_out handle exists
                        self._refresh_path_edit_handles()
                        # Find the tangent_out handle and grab it
                        tout_storage = self._tangent_out_storage(obj, ai)
                        if tout_storage is not None:
                            t_cmd, tx_idx, ty_idx = tout_storage
                            t_ci = obj.path_data.index(t_cmd)
                            for h2 in self._path_edit_handles:
                                if (h2.data(0) == t_ci and h2.data(1) == tx_idx
                                    and h2.data(2) == 'cp'):
                                    self._path_drag_handle = h2; self._path_drag_start = None
                                    self._dbg('edit.grabTangentFromAnchor', ai=ai,
                                              t_ci=t_ci, tx_idx=tx_idx)
                                    event.accept(); return
                if kind == 'endpoint':
                    shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    if shift:
                        if ci in self._path_selected_anchors:
                            self._path_selected_anchors.discard(ci)
                        else:
                            self._path_selected_anchors.add(ci)
                    else:
                        if ci not in self._path_selected_anchors:
                            self._path_selected_anchors = {ci}
                    self._dbg('edit.selectAnchor', ci=ci, shift=shift,
                              selected=sorted(self._path_selected_anchors))
                    self._refresh_path_edit_handles()
                self._path_drag_handle = hit; self._path_drag_start = None
                self._dbg('edit.grabHandle', ci=hit.data(0), pi=hit.data(1),
                          kind=hit.data(2))
                event.accept(); return
            # v4.1.8: shift+click empty segment = insert new point at click position
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._dbg('edit.insertPointAtClick', sp=(round(sp.x(),1), round(sp.y(),1)))
                self._insert_path_point_at_click(sp)
                event.accept(); return
            # v4.1.10: click on empty area in path edit mode = clear anchor selection
            if self._path_selected_anchors:
                self._dbg('edit.clearSelection',
                          was=sorted(self._path_selected_anchors))
                self._path_selected_anchors = set()
                self._refresh_path_edit_handles()

        if btn==Qt.MouseButton.LeftButton:
            # v4.1.15: rectangle draw mode (e.g. for new textbox by drag).
            if self._rect_draw_kind is not None:
                sp = self._sp(event)
                self._rect_draw_start = sp
                # v4.2.10.1: preview matches the shape kind (ellipse shows an
                # ellipse, line/arrow show a segment) instead of always a rect.
                from PyQt6.QtWidgets import (QGraphicsRectItem,
                                             QGraphicsEllipseItem, QGraphicsLineItem)
                k = self._rect_draw_kind
                _pen = QPen(QColor(120, 180, 255, 255), 1, Qt.PenStyle.DashLine)
                _brush = QBrush(QColor(120, 180, 255, 40))
                if k == "ellipse":
                    it = QGraphicsEllipseItem(QRectF(sp.x(), sp.y(), 0, 0))
                    it.setPen(_pen); it.setBrush(_brush)
                elif k in ("line", "arrow"):
                    it = QGraphicsLineItem(sp.x(), sp.y(), sp.x(), sp.y())
                    it.setPen(QPen(QColor(120, 180, 255, 255), 2, Qt.PenStyle.DashLine))
                else:
                    it = QGraphicsRectItem(QRectF(sp.x(), sp.y(), 0, 0))
                    it.setPen(_pen); it.setBrush(_brush)
                it.setZValue(9500)
                self._rect_draw_preview = it
                self.scene().addItem(it)
                event.accept(); return

            # v4.0.3/4.1.0: path drawing tool — intercept clicks
            if getattr(self, '_path_drawing', False):
                sp=self._sp(event); mx,my=self._to_mm(sp)
                if self._snap_to_grid:
                    s=self._snap_size_mm
                    mx=round(mx/s)*s; my=round(my/s)*s
                # v4.1.0: if click is near the first point and we have >= 3 points,
                # close the path
                if len(self._path_points) >= 3:
                    fx, fy = self._path_points[0][:2]
                    threshold_mm = 3.0
                    if abs(mx - fx) < threshold_mm and abs(my - fy) < threshold_mm:
                        self._dbg('draw.closeClick', mx=round(mx,2), my=round(my,2),
                                  first=(round(fx,2), round(fy,2)))
                        self._path_close = True
                        self._finish_path_drawing()
                        event.accept(); return
                # v4.1.0/4.1.1: Pen tool — click for corner, click+drag for curve
                # Initial entry: store as "L" but remember press position so
                # mouse-move can convert to curve point on drag.
                self._path_drag_origin = (mx, my)
                self._path_press_idx = len(self._path_points)
                self._path_points.append((mx, my, 'L'))
                self._dbg('draw.addPoint', idx=self._path_press_idx,
                          mx=round(mx,2), my=round(my,2), snap=self._snap_to_grid)
                self._draw_path_preview()
                event.accept(); return

            # If inline editor active and click is NOT on it → confirm
            if self._inline_widget:
                vp_pos=event.position().toPoint()
                if not self._inline_widget.geometry().contains(vp_pos):
                    self._confirm_inline()
                else:
                    super().mousePressEvent(event); return

            sp=self._sp(event); handle=self._overlay.hit_handle(sp)
            if handle:
                obj=self._sel_obj()
                if (obj and not obj.locked and not getattr(obj, 'lock_position', False)
                        and not (getattr(self._doc, 'mode', '') == 'document'
                                 and self._is_document_body(obj))):
                    mode='rotate' if handle=='ROT' else f'resize_{handle}'
                    if handle in ('P1','P2'): mode=f'line_{handle}'
                    self._drag_mode=mode; self._drag_sp0=sp
                    self._drag_tf0=copy.copy(obj.transform)
                    self._drag_anchor=(self._compute_anchor(obj.transform,handle)
                                       if handle not in ('ROT','P1','P2') else None)
                    # v4.1.7: snapshot path_data for proportional path scaling on resize
                    from edof.format.objects import Shape, SHAPE_PATH
                    if (isinstance(obj, Shape) and obj.shape_type == SHAPE_PATH
                        and obj.path_data):
                        self._drag_path_data0 = copy.deepcopy(obj.path_data)
                    else:
                        self._drag_path_data0 = None
                    # v4.1.16.5: snapshot font sizes so Shift/Ctrl resize
                    # can scale fonts proportionally without drift.
                    # v4.1.16.7: also snapshot glyph_scale_x/y for the
                    # "Shift = deform" mode.
                    from edof.format.objects import TextBox as _TB
                    if isinstance(obj, _TB):
                        self._drag_font_size0_style = obj.style.font_size
                        self._drag_font_sizes0_runs = [
                            r.font_size for r in (obj.runs or [])]
                        self._drag_glyph_scale_x0 = float(
                            getattr(obj.style, 'glyph_scale_x', 1.0) or 1.0)
                        self._drag_glyph_scale_y0 = float(
                            getattr(obj.style, 'glyph_scale_y', 1.0) or 1.0)
                    else:
                        self._drag_font_size0_style = None
                        self._drag_font_sizes0_runs = None
                        self._drag_glyph_scale_x0 = 1.0
                        self._drag_glyph_scale_y0 = 1.0
                return
            hit=self._hit_obj(sp)
            # v4.1.17.1: if user has a selected object and clicked inside its
            # rotated bounding box, prefer the selection over a topmost
            # object that happens to be drawn over it. Without this guard,
            # clicking on the selected object while another layer overlaps
            # would steal the drag to that other layer.
            if hit and self._sel_id and hit != self._sel_id and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                sel_obj = self._find_obj(self._sel_id)
                if sel_obj is not None:
                    mx, my = self._to_mm(sp)
                    t = sel_obj.transform
                    cx, cy = t.x + t.width/2, t.y + t.height/2
                    lx, ly = rotate_point(mx, my, cx, cy, -t.rotation)
                    if t.x <= lx <= t.x + t.width and t.y <= ly <= t.y + t.height:
                        # Click is inside the selected object — keep it as drag target
                        hit = self._sel_id
            ctrl=bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier)
            # v4.0.1: Ctrl+click toggles addition to multi-select set
            if ctrl and hit:
                if hit==self._sel_id:
                    # Demote primary; promote first multi to primary
                    if self._multi_sel_ids:
                        self._sel_id=next(iter(self._multi_sel_ids))
                        self._multi_sel_ids.discard(self._sel_id)
                    else:
                        self._sel_id=None
                elif hit in self._multi_sel_ids:
                    self._multi_sel_ids.discard(hit)
                else:
                    if self._sel_id and self._sel_id!=hit:
                        self._multi_sel_ids.add(self._sel_id)
                    self._sel_id=hit
                self._refresh_overlay()
                self.objectSelected.emit(self._sel_obj())
                self._drag_mode=None
                super().mousePressEvent(event); return

            if hit!=self._sel_id:
                # v4.1.10.1: leaving the path edit subject → exit edit mode
                if (getattr(self, '_path_edit_obj_id', None) is not None
                    and self._path_edit_obj_id != hit):
                    self._exit_path_edit_mode()
                self._sel_id=hit
                if not ctrl: self._multi_sel_ids.clear()
                self._refresh_overlay()
                self.objectSelected.emit(self._sel_obj())
            if hit:
                obj=self._sel_obj()
                # v4.0.1: respect doc permissions and per-object lock_level
                # v4.1.0: respect lock_position too
                can_drag = (obj and not obj.locked
                            and not getattr(obj, 'lock_position', False)
                            and not (getattr(self._doc, 'mode', '') == 'document'
                                     and self._is_document_body(obj))
                            and (not self._doc or obj.can_modify(self._doc)))
                if can_drag:
                    self._drag_mode='move'; self._drag_sp0=sp
                    self._drag_tf0=copy.copy(obj.transform)
                    # Capture starting transforms of all multi-selected objects
                    self._multi_drag_tf0={}
                    for mid in self._multi_sel_ids:
                        mobj=self._find_obj(mid)
                        if mobj and not mobj.locked and not getattr(mobj, 'lock_position', False):
                            self._multi_drag_tf0[mid]=copy.copy(mobj.transform)
            else:
                self._drag_mode=None; self._multi_sel_ids.clear()
                # v4.0.1: start lasso selection on empty click
                self._lasso_start=sp
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        # v4.1.16.3: forward to scene/proxy widget when inline edit is active
        if self._inline_widget is not None and self._pan_start is None:
            super().mouseMoveEvent(event); return
        # v4.2.9.8: flag active object manipulation so the page renders at a
        # lower DPI for responsiveness (full quality restored on release).
        self._interacting = bool(getattr(self, '_drag_mode', None)
                                 or getattr(self, '_path_drag_handle', None)
                                 or getattr(self, '_path_drag_origin', None))
        if self._pan_start is not None:
            d=event.pos()-self._pan_start
            self.horizontalScrollBar().setValue(self._pan_scroll0[0]-d.x())
            self.verticalScrollBar().setValue(self._pan_scroll0[1]-d.y())
            event.accept(); return
        sp=self._sp(event)

        # v4.1.15: rectangle draw — live-update preview while button held
        if (self._rect_draw_kind is not None
            and self._rect_draw_start is not None
            and self._rect_draw_preview is not None):
            x0, y0 = self._rect_draw_start.x(), self._rect_draw_start.y()
            x1, y1 = sp.x(), sp.y()
            if self._rect_draw_kind in ("line", "arrow"):
                self._rect_draw_preview.setLine(x0, y0, x1, y1)
            else:
                rx = min(x0, x1); ry = min(y0, y1)
                rw = abs(x1 - x0); rh = abs(y1 - y0)
                self._rect_draw_preview.setRect(rx, ry, rw, rh)
            event.accept(); return

        # v4.1.1: pen tool — drag during press converts last point to curve
        if (getattr(self, '_path_drawing', False)
            and getattr(self, '_path_drag_origin', None) is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and self._path_points):
            ox, oy = self._path_drag_origin
            mx, my = self._to_mm(sp)
            dist = ((mx - ox) ** 2 + (my - oy) ** 2) ** 0.5
            if dist > 1.0:  # > 1mm of drag = curve
                idx = self._path_press_idx
                if idx is not None and idx < len(self._path_points):
                    # Replace 'L' with 'C' (curve point) carrying outgoing handle.
                    # v4.1.1 fix: points may be 3-tuple (L) or 5-tuple (C).
                    p = self._path_points[idx]
                    px_pt, py_pt = p[0], p[1]
                    self._path_points[idx] = (px_pt, py_pt, 'C', mx, my)
                    self._dbg('draw.dragToCurve', idx=idx, dist=round(dist,2),
                              handle=(round(mx,2), round(my,2)))
                    self._draw_path_preview()
            event.accept(); return

        # v4.1.0: path edit handle drag
        if getattr(self, '_path_drag_handle', None) is not None:
            page = self._cur_page()
            obj = page.get_object(self._path_edit_obj_id) if page else None
            if obj and obj.path_data:
                ci = self._path_drag_handle.data(0)
                pi = self._path_drag_handle.data(1)
                kind = self._path_drag_handle.data(2)  # 'endpoint' or 'cp'
                # v4.1.5: defensive — if data wasn't set (e.g. user grabbed
                # a decoration item by accident), bail out cleanly
                if ci is None or pi is None:
                    self._path_drag_handle = None
                    event.accept(); return
                # Convert mouse position to mm (relative to obj)
                # v4.1.10.2: if the object has rotation, un-rotate the world
                # coord before subtracting transform.x/y so the path_data
                # stays in unrotated local coords (the renderer applies
                # rotation back at draw time)
                mx, my = self._to_mm(sp)
                rot_deg = obj.transform.rotation or 0.0
                if abs(rot_deg) > 0.01:
                    cx_mm = obj.transform.x + obj.transform.width / 2.0
                    cy_mm = obj.transform.y + obj.transform.height / 2.0
                    mx, my = rotate_point(mx, my, cx_mm, cy_mm, -rot_deg)
                local_x = mx - obj.transform.x
                local_y = my - obj.transform.y
                # Mutate path_data
                if ci >= len(obj.path_data):
                    self._path_drag_handle = None
                    event.accept(); return
                cmd = obj.path_data[ci]
                if not cmd or pi + 1 >= len(cmd):
                    self._path_drag_handle = None
                    event.accept(); return
                # v4.2.6.0: Photoshop-style live modifiers (read DURING drag),
                # for both anchor and tangent handles:
                #   (none)      = snap to grid (if grid snap is on)
                #   Ctrl        = no snapping
                #   Shift       = constrain to 0/45/90 deg from the drag start
                #   Ctrl+Shift  = constrain, no snapping
                _mods = event.modifiers()
                _ctrl = bool(_mods & Qt.KeyboardModifier.ControlModifier)
                _shift = bool(_mods & Qt.KeyboardModifier.ShiftModifier)
                if getattr(self, '_path_drag_start', None) is None:
                    self._path_drag_start = (cmd[pi], cmd[pi+1])
                if _shift:
                    _sx, _sy = self._path_drag_start
                    _ddx = local_x - _sx; _ddy = local_y - _sy
                    if _ddx or _ddy:
                        _ang = math.atan2(_ddy, _ddx)
                        _step = math.pi / 4.0
                        _ang = round(_ang / _step) * _step
                        _dist = math.hypot(_ddx, _ddy)
                        local_x = _sx + _dist * math.cos(_ang)
                        local_y = _sy + _dist * math.sin(_ang)
                if (not _ctrl) and getattr(self, '_snap_to_grid', False) and abs(rot_deg) < 0.01:
                    _s = self._snap_size_mm
                    if _s and _s > 0:
                        _cx = local_x + obj.transform.x
                        _cy = local_y + obj.transform.y
                        _cx = round(_cx / _s) * _s
                        _cy = round(_cy / _s) * _s
                        local_x = _cx - obj.transform.x
                        local_y = _cy - obj.transform.y
                old_x, old_y = cmd[pi], cmd[pi+1]
                cmd[pi] = local_x
                cmd[pi+1] = local_y
                self._dbg('edit.dragHandle', ci=ci, pi=pi, kind=kind,
                          old=(round(old_x,2), round(old_y,2)),
                          new=(round(local_x,2), round(local_y,2)),
                          ctrl=_ctrl, shift=_shift, rot=round(rot_deg,1))
                # v4.1.10.1: if this endpoint is in the multi-selection, move
                # the other selected anchors by the same delta (group drag).
                # v4.2.6.0: group drag — move every OTHER selected anchor by the
                # same delta, INCLUDING its tangent handles, so multi-point moves
                # keep the curve shape (the dragged anchor itself is handled by
                # the per-anchor logic below).
                if (kind == 'endpoint'
                    and ci in self._path_selected_anchors
                    and len(self._path_selected_anchors) > 1):
                    dx_g = local_x - old_x; dy_g = local_y - old_y
                    if dx_g or dy_g:
                        for _ai in range(self._anchor_count(obj)):
                            _aci = self._anchor_cmd_index(obj, _ai)
                            if _aci == ci:
                                continue
                            if _aci not in self._path_selected_anchors:
                                continue
                            self._translate_anchor(obj, _ai, dx_g, dy_g)
                # v4.1.12.6: anchor-centric CP drag with proper smooth mirror.
                # Old code only handled middle anchors; M of closed path was
                # broken because its tangent_in lives in wrap-cmd.cp2 (not
                # cmd[ai].cp2 for ai=0). Use the same storage helpers as
                # _set_point_type so mirror works uniformly.
                if kind == 'cp':
                    ptypes = getattr(obj, 'path_point_types', []) or []
                    # Determine which anchor OWNS this CP, and whether it's
                    # the IN (cp2) or OUT (cp1) tangent side.
                    ai_owner = None; side = None
                    if cmd[0] == 'C':
                        wci = self._wrap_cmd_index(obj)
                        n_anch = self._anchor_count(obj)
                        if pi == 3:
                            # cp2 → tangent_in. Owner = anchor at ci, unless
                            # ci is wrap-cmd (then owner = anchor 0 / M).
                            if self._is_closed_path(obj) and wci == ci:
                                ai_owner = 0
                            else:
                                ai_owner = ci
                            side = 'in'
                        elif pi == 1:
                            # cp1 → tangent_out. Owner = anchor at ci-1, unless
                            # ci is wrap-cmd (then owner = last user anchor).
                            if self._is_closed_path(obj) and wci == ci:
                                ai_owner = n_anch - 1
                            else:
                                ai_owner = ci - 1
                            side = 'out'
                    if ai_owner is not None and 0 <= ai_owner < self._anchor_count(obj):
                        own_ci = self._anchor_cmd_index(obj, ai_owner)
                        anchor_ptype = ptypes[own_ci] if own_ci < len(ptypes) else "smooth"
                        if anchor_ptype == "smooth":
                            ap = self._anchor_pos(obj, ai_owner)
                            if ap is not None:
                                aax, aay = ap
                                # This CP's current value
                                this_x, this_y = cmd[pi], cmd[pi + 1]
                                # Mirror through anchor
                                opp_x = 2 * aax - this_x
                                opp_y = 2 * aay - this_y
                                # Write to opposite-side storage
                                if side == 'in':
                                    self._set_tangent_out(obj, ai_owner, opp_x, opp_y)
                                else:
                                    self._set_tangent_in(obj, ai_owner, opp_x, opp_y)
                # v4.1.10/4.1.10.1: respect point type when dragging an endpoint
                if kind == 'endpoint':
                    ptypes = getattr(obj, 'path_point_types', [])
                    ptype = ptypes[ci] if ci < len(ptypes) else "smooth"
                    if cmd[0] == 'C' and pi == 5:
                        if ptype == "corner":
                            pass  # CPs stay where they are
                        elif ptype in ("smooth", "asymmetric"):
                            # Move this C's cp2 + next C's cp1 by same delta
                            dx = local_x - old_x; dy = local_y - old_y
                            cmd[3] += dx; cmd[4] += dy
                            if ci + 1 < len(obj.path_data):
                                nxt = obj.path_data[ci + 1]
                                if nxt and nxt[0] == 'C':
                                    nxt[1] += dx; nxt[2] += dy
                        elif ptype == "auto":
                            # Recompute CPs from neighbors
                            self._convert_point_to_smooth(obj, ci)
                    if cmd[0] == 'M' and pi == 1:
                        # v4.1.10.1/4.1.10.4: M (start point) always carries
                        # the next segment's cp1 along. For a closed path,
                        # also move the LAST segment's cp2 (the incoming
                        # tangent at M, coming from the wrap-around) so the
                        # closure stays smooth.
                        dx = local_x - old_x; dy = local_y - old_y
                        if ci + 1 < len(obj.path_data):
                            nxt = obj.path_data[ci + 1]
                            if nxt and nxt[0] == 'C':
                                nxt[1] += dx; nxt[2] += dy
                        # Closed-path wrap: only sync the wrap-cmd, and ONLY if
                        # path_data[-2] is genuinely the wrap-cmd. M has already
                        # been moved at this point, so match the wrap endpoint to
                        # M's OLD position (the wrap still points there).
                        # v4.2.10.8 FIX: without this guard, a closed path that
                        # lacks a wrap-cmd (straight-Z closure) would have its
                        # LAST user anchor overwritten with M's position when M
                        # was dragged, making that anchor vanish onto M.
                        is_closed = (obj.path_data and obj.path_data[-1]
                                     and obj.path_data[-1][0] == "Z")
                        if is_closed and len(obj.path_data) >= 3:
                            last_drawn = obj.path_data[-2]
                            is_wrap = (last_drawn and last_drawn[0] == 'C'
                                       and len(last_drawn) >= 7
                                       and abs(last_drawn[5] - old_x) <= 0.1
                                       and abs(last_drawn[6] - old_y) <= 0.1)
                            if is_wrap:
                                # Move its cp2 (and endpoint, which IS M for a
                                # closed path, so it must track M's new pos)
                                last_drawn[3] += dx; last_drawn[4] += dy
                                last_drawn[5] = cmd[1]
                                last_drawn[6] = cmd[2]
                # v4.1.10.4: after the drag, recompute tangents on any
                # neighboring 'auto' anchor so the curve through it follows
                # the new geometry (auto = always derived from neighbors).
                if kind == 'endpoint':
                    ptypes_now = getattr(obj, 'path_point_types', [])
                    for nci in (ci - 1, ci, ci + 1):
                        if 0 <= nci < len(ptypes_now):
                            if ptypes_now[nci] == "auto" and nci > 0:
                                # _convert_point_to_smooth recomputes CPs from
                                # neighbors. Safe to call repeatedly.
                                self._convert_point_to_smooth(obj, nci)
                # v4.1.10.2: live-normalize bbox and refresh the selection
                # overlay so the user can see the curve extents while
                # dragging anchors / control points beyond the original
                # bounding box. _normalize_path_bbox shifts path_data and
                # transform.x/y by equal-and-opposite amounts, so the path
                # stays visually at the same place (mouse cursor stays on
                # the dragged handle).
                self._normalize_path_bbox(obj)
                self._refresh_path_edit_handles()
                self._refresh_overlay()
                # v4.1.3: live render (was 50ms debounce → noticeable lag)
                self.schedule_render(0)
            event.accept(); return
        # v4.0: cursor position in mm in status bar
        try:
            mw = self.window()
            if hasattr(mw, "_status") and self._doc:
                page = self._doc.pages[self._page_idx] if self._page_idx < len(self._doc.pages) else None
                if page:
                    mm_x = sp.x() / max(1, self._render_size.width())  * page.width
                    mm_y = sp.y() / max(1, self._render_size.height()) * page.height
                    mw._status.showMessage(f"X: {mm_x:.1f} mm   Y: {mm_y:.1f} mm")
        except Exception:
            pass
        if self._drag_mode and self._drag_sp0:
            mods=event.modifiers()
            shift=bool(mods&Qt.KeyboardModifier.ShiftModifier)
            alt  =bool(mods&Qt.KeyboardModifier.AltModifier)
            ctrl =bool(mods&Qt.KeyboardModifier.ControlModifier)
            self._apply_drag(sp,shift,alt,ctrl)
            # v4.1.7: live-refresh path edit handles if active
            if getattr(self, '_path_edit_obj_id', None):
                self._refresh_path_edit_handles()
        else: self._update_cursor(sp)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        # v4.1.16.3: forward to editor when inline active
        if self._inline_widget is not None and self._pan_start is None:
            super().mouseReleaseEvent(event); return
        # v4.2.9.8: interaction ended -> next render is full quality
        self._interacting = False
        # v4.1.1: hand tool release
        if getattr(self, '_hand_tool', False) and event.button() == Qt.MouseButton.LeftButton:
            self._pan_start=None; self._pan_scroll0=None
            self.viewport().setCursor(tcur('hand', Qt.CursorShape.OpenHandCursor))
            event.accept(); return
        if event.button()==Qt.MouseButton.MiddleButton:
            self._pan_start=None; self._pan_scroll0=None
            self.viewport().setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept(); return

        # v4.1.15: rectangle draw — finalize
        if (event.button() == Qt.MouseButton.LeftButton
            and self._rect_draw_kind is not None
            and self._rect_draw_start is not None):
            sp = self._sp(event)
            x0, y0 = self._rect_draw_start.x(), self._rect_draw_start.y()
            x1, y1 = sp.x(), sp.y()
            kind = self._rect_draw_kind
            cb = self._rect_draw_callback
            if kind in ("line", "arrow"):
                # v4.2.10.1: signed endpoints preserve the drawn direction, and
                # axis-aligned lines (zero-width/height bbox) are allowed.
                sx, sy = self._to_mm(QPointF(x0, y0))
                ex, ey = self._to_mm(QPointF(x1, y1))
                if self._snap_to_grid:
                    s = self._snap_size_mm
                    sx = round(sx/s)*s; sy = round(sy/s)*s
                    ex = round(ex/s)*s; ey = round(ey/s)*s
                self._cancel_rect_draw()
                import math as _ml
                if _ml.hypot(ex - sx, ey - sy) >= 2.0 and cb is not None:
                    cb(sx, sy, ex - sx, ey - sy)   # start + signed deltas
                event.accept(); return
            # rect / ellipse / textbox / polygon / ... : bounding-box geometry
            rx = min(x0, x1); ry = min(y0, y1)
            rw = abs(x1 - x0); rh = abs(y1 - y0)
            x_mm, y_mm = self._to_mm(QPointF(rx, ry))
            w_mm = rw / mm_to_px(1.0, self._dpi)
            h_mm = rh / mm_to_px(1.0, self._dpi)
            if self._snap_to_grid:
                s = self._snap_size_mm
                x_mm = round(x_mm/s)*s; y_mm = round(y_mm/s)*s
                w_mm = max(s, round(w_mm/s)*s); h_mm = max(s, round(h_mm/s)*s)
            self._cancel_rect_draw()
            if w_mm >= 5.0 and h_mm >= 5.0 and cb is not None:
                cb(x_mm, y_mm, w_mm, h_mm)
            event.accept(); return

        # v4.1.1: clear pen-tool drag origin
        if getattr(self, '_path_drawing', False):
            self._path_drag_origin = None
            self._path_press_idx = None
        # v4.1.0/4.1.3/4.1.9.1: release path edit handle
        if getattr(self, '_path_drag_handle', None) is not None:
            self._dbg('edit.releaseHandle', ci=self._path_drag_handle.data(0),
                      pi=self._path_drag_handle.data(1), kind=self._path_drag_handle.data(2))
            self._path_drag_handle = None; self._path_drag_start = None
            # v4.1.9.1: after dragging an anchor or CP, recompute the bbox to
            # encompass the entire curve (including overshoot from control
            # points). Previously the bbox was based on transform.x/y/w/h
            # only, so dragged-out CPs ended up outside the selection box.
            page = self._cur_page()
            obj = page.get_object(self._path_edit_obj_id) if page else None
            if obj and obj.path_data:
                self._normalize_path_bbox(obj)
            self._refresh_path_edit_handles()
            self._refresh_overlay()
            self.schedule_render(0)
            self.objectChanged.emit()
            event.accept(); return
        if self._drag_mode:
            if self._preview_item:
                self.scene().removeItem(self._preview_item); self._preview_item=None
            self._start_render()
            if self._drag_mode: self.objectChanged.emit()
            # v4.1.7: if path edit mode is on for the dragged object,
            # refresh its edit handles so they follow the new position/size.
            if getattr(self, '_path_edit_obj_id', None):
                self._refresh_path_edit_handles()
        self._drag_mode=None; self._drag_sp0=None; self._drag_tf0=None; self._drag_anchor=None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """v4.1.7: right-click on a path edit anchor → menu to change point type."""
        if not getattr(self, '_path_edit_obj_id', None):
            super().contextMenuEvent(event); return
        sp = self.mapToScene(event.pos())
        # Find which handle was clicked
        target = None
        for h in self._path_edit_handles:
            if h.data(0) is None: continue
            rect = h.sceneBoundingRect().adjusted(-3, -3, 3, 3)
            if rect.contains(sp):
                target = h; break
        if not target:
            super().contextMenuEvent(event); return
        ci = target.data(0); pi = target.data(1); kind = target.data(2)
        if kind != 'endpoint':
            super().contextMenuEvent(event); return
        page = self._cur_page()
        obj = page.get_object(self._path_edit_obj_id) if page else None
        if not obj or not obj.path_data: return
        cmd = obj.path_data[ci]
        # v4.1.10: ensure path_point_types initialized
        if (not hasattr(obj, 'path_point_types')
            or len(obj.path_point_types) != len(obj.path_data)):
            ptypes = []
            for c in obj.path_data:
                if not c: ptypes.append("corner"); continue
                op = c[0]
                ptypes.append("smooth" if op in ("C", "Q") else "corner")
            obj.path_point_types = ptypes
        current_type = obj.path_point_types[ci] if ci < len(obj.path_point_types) else "corner"
        # Build menu — 4 point types + Delete
        menu = QMenu(self)
        act_corner = menu.addAction("▢  Corner (no tangents)")
        act_smooth = menu.addAction("◆  Smooth (symmetric tangents)")
        act_asym   = menu.addAction("○  Asymmetric (independent tangents)")
        act_auto   = menu.addAction("▽  Auto (recomputed from neighbors)")
        for a, t in [(act_corner, "corner"), (act_smooth, "smooth"),
                       (act_asym, "asymmetric"), (act_auto, "auto")]:
            a.setCheckable(True)
            a.setChecked(t == current_type)
        menu.addSeparator()
        act_delete = menu.addAction("Delete point")
        chosen = menu.exec(event.globalPos())
        if chosen == act_corner:
            self._set_point_type(obj, ci, "corner")
        elif chosen == act_smooth:
            self._set_point_type(obj, ci, "smooth")
        elif chosen == act_asym:
            self._set_point_type(obj, ci, "asymmetric")
        elif chosen == act_auto:
            self._set_point_type(obj, ci, "auto")
        elif chosen == act_delete:
            self._delete_path_point(obj, ci)
        self._refresh_path_edit_handles()
        self.schedule_render(0)
        self.objectChanged.emit()

    def _ensure_wrap_cmd(self, obj):
        """v4.1.11.1: Old-format closed paths (path_data = [M, L|C..., Z])
        don't have an explicit wrap-cmd that owns tangent_in of M and
        tangent_out of the last anchor. When the user wants to change the
        type of M or the last anchor in a way that needs visible tangents,
        we materialize a wrap-cmd by inserting a straight L from last
        anchor back to M, just before Z."""
        if not self._is_closed_path(obj): return False
        if self._wrap_cmd_index(obj) is not None: return False
        m = obj.path_data[0]
        if not m or m[0] != 'M': return False
        z_idx = len(obj.path_data) - 1
        last_drawn_idx = z_idx - 1
        if last_drawn_idx < 1: return False
        # Insert L wrap-cmd ending at M
        obj.path_data.insert(z_idx, ['L', m[1], m[2]])
        ptypes = getattr(obj, 'path_point_types', []) or []
        if z_idx <= len(ptypes):
            ptypes.insert(z_idx, 'corner')
        return True

    def _ensure_anchor_is_curve(self, obj, ai):
        """v4.1.11: ensure the cmd for anchor ai is a 'C' (cubic bezier).
        If it's L or Q, promote to C with collapsed tangents (cp1=prev_anchor,
        cp2=anchor). For ai==0 (M), there's nothing to promote — return.
        The wrap-cmd of a closed path may also need promotion when modifying
        tangent_in of anchor 0."""
        if ai <= 0: return
        ci = self._anchor_cmd_index(obj, ai)
        if ci < 0 or ci >= len(obj.path_data): return
        cmd = obj.path_data[ci]
        if not cmd or cmd[0] == 'C': return
        # Get previous anchor and this anchor positions
        prev_pos = self._anchor_pos(obj, ai - 1)
        this_pos = self._anchor_pos(obj, ai)
        if not prev_pos or not this_pos: return
        # Collapsed tangents: cp1 at prev, cp2 at this
        obj.path_data[ci] = ['C', prev_pos[0], prev_pos[1],
                                    this_pos[0], this_pos[1],
                                    this_pos[0], this_pos[1]]

    def _ensure_outgoing_is_curve(self, obj, ai):
        """Ensure the cmd carrying tangent_out(ai) is 'C'."""
        n = self._anchor_count(obj)
        if n == 0: return
        if self._is_closed_path(obj) and ai == n - 1:
            # v4.1.11.1: materialize wrap-cmd if missing
            self._ensure_wrap_cmd(obj)
            wci = self._wrap_cmd_index(obj)
            if wci is None: return
            wcmd = obj.path_data[wci]
            if not wcmd or wcmd[0] == 'C': return
            this_pos = self._anchor_pos(obj, ai)
            m_pos = self._anchor_pos(obj, 0)
            if not this_pos or not m_pos: return
            obj.path_data[wci] = ['C', this_pos[0], this_pos[1],
                                          m_pos[0], m_pos[1],
                                          m_pos[0], m_pos[1]]
        else:
            self._ensure_anchor_is_curve(obj, ai + 1)

    def _ensure_incoming_is_curve(self, obj, ai):
        """Ensure the cmd carrying tangent_in(ai) is 'C'."""
        if ai == 0 and self._is_closed_path(obj):
            # v4.1.11.1: materialize wrap-cmd if missing (old-format path)
            self._ensure_wrap_cmd(obj)
            wci = self._wrap_cmd_index(obj)
            if wci is None: return
            wcmd = obj.path_data[wci]
            if not wcmd or wcmd[0] == 'C': return
            last_pos = self._anchor_pos(obj, self._anchor_count(obj) - 1)
            m_pos = self._anchor_pos(obj, 0)
            if not last_pos or not m_pos: return
            obj.path_data[wci] = ['C', last_pos[0], last_pos[1],
                                          m_pos[0], m_pos[1],
                                          m_pos[0], m_pos[1]]
        else:
            self._ensure_anchor_is_curve(obj, ai)

    def _set_point_type(self, obj, ai, new_type):
        """v4.1.11: Anchor-centric type change. Updates BOTH tangent_in and
        tangent_out per the transition table, then immediately normalizes
        bbox and refreshes UI so changes apply on-the-spot.

        `ai` is the anchor INDEX (not cmd index). For backward compat with
        callers that still pass a cmd index, we accept either — they're
        equal for the first anchor_count cmds (M and L/C anchors).
        """
        import math as _math

        # Initialize ptypes if needed
        ptypes = self._ensure_ptypes_initialized(obj)
        ci = self._anchor_cmd_index(obj, ai)
        if ci < 0 or ci >= len(ptypes): return
        old_type = ptypes[ci]
        ptypes[ci] = new_type

        # Snapshot anchor pos and neighbors (for tangent computation)
        a_pos = self._anchor_pos(obj, ai)
        if a_pos is None:
            self._normalize_path_bbox(obj)
            return
        ax, ay = a_pos
        prev_pos = self._neighbor_anchor_pos(obj, ai, -1)
        next_pos = self._neighbor_anchor_pos(obj, ai, +1)

        # ── *→corner: adjacent segments become straight L (true sharp corner) ─
        if new_type == "corner":
            # v4.1.12.5: corner means STRAIGHT segments on both sides of A.
            # We demote the incoming cmd (cmd[ai]) and outgoing cmd
            # (cmd[ai+1] or wrap-cmd for closed-path-last) to L. This loses
            # the neighbor anchors' tangent_out / tangent_in for THESE
            # specific segments — but that's the whole point of "corner":
            # no curve adjacent to it.
            # The neighbors' tangents on their OTHER sides are unaffected.

            # Incoming: cmd[ci_in] becomes L ending at A.
            ci_in = self._anchor_cmd_index(obj, ai)
            if 0 <= ci_in < len(obj.path_data):
                cmd_in = obj.path_data[ci_in]
                if cmd_in and cmd_in[0] == 'C':
                    obj.path_data[ci_in] = ['L', ax, ay]

            # For ai == 0 of closed path: the incoming cmd is the wrap-cmd.
            if ai == 0 and self._is_closed_path(obj):
                wci = self._wrap_cmd_index(obj)
                if wci is not None and obj.path_data[wci][0] == 'C':
                    # Wrap-cmd ends at M position; demote to L ending at M
                    m = obj.path_data[0]
                    obj.path_data[wci] = ['L', m[1], m[2]]

            # Outgoing: cmd[ai+1] becomes L ending at next anchor.
            n_cnt = self._anchor_count(obj)
            if self._is_closed_path(obj) and ai == n_cnt - 1:
                # Last anchor of closed path: outgoing is wrap-cmd
                wci = self._wrap_cmd_index(obj)
                if wci is not None and obj.path_data[wci][0] == 'C':
                    m = obj.path_data[0]
                    obj.path_data[wci] = ['L', m[1], m[2]]
            else:
                ci_out = ai + 1
                if 0 <= ci_out < len(obj.path_data):
                    cmd_out = obj.path_data[ci_out]
                    if cmd_out and cmd_out[0] == 'C':
                        # Preserve endpoint, demote to L
                        ex, ey = cmd_out[5], cmd_out[6]
                        obj.path_data[ci_out] = ['L', ex, ey]

            # Also if AI's cmd itself isn't already L and both sides corner, ensure L
            if (ai > 0 and ci < len(obj.path_data)
                and obj.path_data[ci] and obj.path_data[ci][0] == 'C'):
                obj.path_data[ci] = ['L', ax, ay]

            self._normalize_path_bbox(obj)
            self._refresh_path_edit_handles()
            self._refresh_overlay()
            self.schedule_render(0)
            self.objectChanged.emit()
            return

        # v4.1.12.4: SMOOTH (= continuous) always makes tangents collinear
        # around the anchor (mirror). If at least one tangent already exists,
        # average their direction and preserve magnitudes (legacy
        # asym→smooth behavior, now used always). If BOTH are collapsed
        # (corner→smooth), fall through to quadratic-formula init.
        def _at_anchor(p):
            if p is None: return True
            return _math.hypot(p[0]-ax, p[1]-ay) < 0.1
        if new_type == "smooth":
            cur_in = self._anchor_tangent_in(obj, ai)
            cur_out = self._anchor_tangent_out(obj, ai)
            in_at = _at_anchor(cur_in) if cur_in is not None else True
            out_at = _at_anchor(cur_out) if cur_out is not None else True
            if not (in_at and out_at):
                # At least one tangent is non-collapsed: collinearize
                if cur_in is None or in_at:
                    # Only out exists → mirror it
                    if cur_out is not None:
                        # Ensure incoming cmd is C so we can store
                        self._ensure_incoming_is_curve(obj, ai)
                        self._set_tangent_in(obj, ai,
                                              2 * ax - cur_out[0],
                                              2 * ay - cur_out[1])
                elif cur_out is None or out_at:
                    # Only in exists → mirror it
                    if cur_in is not None:
                        self._ensure_outgoing_is_curve(obj, ai)
                        self._set_tangent_out(obj, ai,
                                               2 * ax - cur_in[0],
                                               2 * ay - cur_in[1])
                else:
                    # Both exist: average direction, preserve magnitudes
                    in_mag = _math.hypot(cur_in[0]-ax, cur_in[1]-ay) or 1.0
                    out_mag = _math.hypot(cur_out[0]-ax, cur_out[1]-ay) or 1.0
                    back = (ax - cur_in[0], ay - cur_in[1])
                    forw = (cur_out[0] - ax, cur_out[1] - ay)
                    avg_x = back[0] + forw[0]
                    avg_y = back[1] + forw[1]
                    avg_mag = _math.hypot(avg_x, avg_y)
                    if avg_mag < 0.001:
                        # Tangents point opposite each other (rare); use
                        # incoming direction
                        in_d = _math.hypot(*back) or 1.0
                        ux = back[0] / in_d; uy = back[1] / in_d
                    else:
                        ux = avg_x / avg_mag; uy = avg_y / avg_mag
                    self._set_tangent_in(obj, ai, ax - ux*in_mag, ay - uy*in_mag)
                    self._set_tangent_out(obj, ai, ax + ux*out_mag, ay + uy*out_mag)
                # Done with smooth
                self._normalize_path_bbox(obj)
                self._refresh_path_edit_handles()
                self._refresh_overlay()
                self.schedule_render(0)
                self.objectChanged.emit()
                return

        # ── Promote to C if needed (so we have tangent storage) ──────────────
        self._ensure_incoming_is_curve(obj, ai)
        self._ensure_outgoing_is_curve(obj, ai)

        # Get current tangent state
        cur_in  = self._anchor_tangent_in(obj, ai)
        cur_out = self._anchor_tangent_out(obj, ai)
        in_collapsed = _at_anchor(cur_in)
        out_collapsed = _at_anchor(cur_out)

        # If transitioning FROM corner, compute fresh tangents per new_type
        if old_type == "corner":
            in_collapsed = True
            out_collapsed = True
        # v4.1.11.1: auto type ALWAYS recomputes tangents (it's by definition
        # neighbor-derived, not user-set). This way switching to auto
        # immediately rebuilds the curve through the anchor.
        if new_type == "auto":
            in_collapsed = True
            out_collapsed = True

        if in_collapsed or out_collapsed:
            # Need to compute initial tangent geometry
            # v4.1.12.1: asymmetric does NOT auto-position tangents anymore.
            # Per user spec, asym transitions must preserve the existing
            # curve shape — moving tangents away from the anchor would
            # change the curve. User can Ctrl+drag the anchor to pull
            # tangents out manually.
            if new_type == "asymmetric":
                pass   # leave tangents wherever they are
            else:
                # v4.1.11.1: smooth/auto use the QUADRATIC Bezier method.
                # P1 = 2*Pc - (P0+P2)/2 makes the quadratic curve pass through
                # Pc at t=0.5. Converting to cubic gives the tangent direction
                # (P2-P0) and magnitude |P2-P0|/6 on each side, symmetric
                # around Pc. This matches the "auto-smooth" curve users expect.
                if prev_pos is not None and next_pos is not None:
                    dx = next_pos[0] - prev_pos[0]
                    dy = next_pos[1] - prev_pos[1]
                    chord_mag = _math.hypot(dx, dy)
                    if chord_mag > 0.001:
                        # tangent_in  = Pc - (P2-P0)/6
                        # tangent_out = Pc + (P2-P0)/6
                        mag6 = chord_mag / 6.0
                        # Tiny minimum (1mm) so handles are clickable even
                        # for very close-spaced anchors; doesn't override
                        # the quadratic formula for normal-sized chords.
                        if mag6 < 1.0: mag6 = 1.0
                        ux = dx / chord_mag; uy = dy / chord_mag
                        if in_collapsed:
                            self._set_tangent_in(obj, ai, ax - ux*mag6, ay - uy*mag6)
                        if out_collapsed:
                            self._set_tangent_out(obj, ai, ax + ux*mag6, ay + uy*mag6)
                    else:
                        # P0 == P2 (e.g. 2-anchor closed loop with M neighboring
                        # itself). Use perpendicular-to-(M-A1) so tangents point
                        # off the chord.
                        if next_pos is not None:
                            dx2 = next_pos[0] - ax; dy2 = next_pos[1] - ay
                            d2 = _math.hypot(dx2, dy2) or 1.0
                            # Perpendicular CCW
                            perp_x = -dy2 / d2; perp_y = dx2 / d2
                            mag = max(5.0, d2 / 2.0)
                            if in_collapsed:
                                self._set_tangent_in(obj, ai, ax + perp_x * mag,
                                                              ay + perp_y * mag)
                            if out_collapsed:
                                self._set_tangent_out(obj, ai, ax - perp_x * mag,
                                                               ay - perp_y * mag)
                elif prev_pos is not None:
                    # End of open path
                    dx = ax - prev_pos[0]; dy = ay - prev_pos[1]
                    d = _math.hypot(dx, dy) or 1.0
                    mag = max(5.0, d / 3.0)
                    if in_collapsed:
                        self._set_tangent_in(obj, ai, ax - dx/d*mag, ay - dy/d*mag)
                elif next_pos is not None:
                    # Start of open path
                    dx = next_pos[0] - ax; dy = next_pos[1] - ay
                    d = _math.hypot(dx, dy) or 1.0
                    mag = max(5.0, d / 3.0)
                    if out_collapsed:
                        self._set_tangent_out(obj, ai, ax + dx/d*mag, ay + dy/d*mag)

        # ── asymmetric → smooth: handled at top by SMOOTH-always branch ──

        # smooth / auto / asym → other type: tangents preserved (no change)

        self._normalize_path_bbox(obj)
        self._refresh_path_edit_handles()
        self._refresh_overlay()
        self.schedule_render(0)
        self.objectChanged.emit()

    def _insert_path_point_at_click(self, sp):
        self._dbg('insertPoint.enter', sp=(round(sp.x(),1), round(sp.y(),1)))
        """v4.1.8/4.1.10.1: Insert a new anchor point on the path at the click
        location. For straight L segments: split into two L. For bezier C
        segments: use de Casteljau subdivision so the curve shape is preserved
        — the new anchor and the surrounding control points keep the original
        path visually identical, but the user can now drag the new anchor.
        """
        page = self._cur_page()
        obj = page.get_object(self._path_edit_obj_id) if page else None
        if not obj or not obj.path_data: return
        click_mx, click_my = self._to_mm(sp)
        local_x = click_mx - obj.transform.x
        local_y = click_my - obj.transform.y

        # Iterate segments, find closest one + parameter t
        best = None  # (distance, ci, t)
        prev_x, prev_y = 0.0, 0.0
        for ci, cmd in enumerate(obj.path_data):
            if not cmd: continue
            op = cmd[0]
            if op == "M":
                prev_x, prev_y = cmd[1], cmd[2]
                continue
            if op == "Z":
                m = obj.path_data[0]
                end_x, end_y = m[1], m[2]
                seg_type = "L"; ctrl = None
            elif op == "L":
                end_x, end_y = cmd[1], cmd[2]
                seg_type = "L"; ctrl = None
            elif op == "C":
                end_x, end_y = cmd[5], cmd[6]
                seg_type = "C"
                ctrl = (cmd[1], cmd[2], cmd[3], cmd[4])
            elif op == "Q":
                end_x, end_y = cmd[3], cmd[4]
                seg_type = "Q"
                ctrl = (cmd[1], cmd[2])
            else:
                continue
            best_seg_dist = float('inf')
            best_t = 0.5
            samples = 32
            for s in range(samples + 1):
                t = s / samples
                if seg_type == "L":
                    px = prev_x + (end_x - prev_x) * t
                    py = prev_y + (end_y - prev_y) * t
                elif seg_type == "C":
                    cx1, cy1, cx2, cy2 = ctrl
                    u = 1 - t
                    px = u**3*prev_x + 3*u*u*t*cx1 + 3*u*t*t*cx2 + t**3*end_x
                    py = u**3*prev_y + 3*u*u*t*cy1 + 3*u*t*t*cy2 + t**3*end_y
                elif seg_type == "Q":
                    cx, cy = ctrl
                    u = 1 - t
                    px = u*u*prev_x + 2*u*t*cx + t*t*end_x
                    py = u*u*prev_y + 2*u*t*cy + t*t*end_y
                d = (px - local_x) ** 2 + (py - local_y) ** 2
                if d < best_seg_dist:
                    best_seg_dist = d
                    best_t = t
            if best is None or best_seg_dist < best[0]:
                best = (best_seg_dist, ci, best_t, seg_type, ctrl,
                        prev_x, prev_y, end_x, end_y)
            prev_x, prev_y = end_x, end_y

        if best is None: return
        d, ci, t_split, seg_type, ctrl, p0x, p0y, p3x, p3y = best
        # Tolerance: only insert if within ~5mm
        if d > 25.0:
            return

        old_cmd = obj.path_data[ci]
        if seg_type == "L" or old_cmd[0] == "Z":
            # Straight line — split into two L commands at the click point,
            # then convert the new anchor to a smooth bezier with visible
            # tangents (v4.1.10.3: previously stayed as a corner which was
            # hard for the user to convert into a curve afterwards).
            ix = p0x + (p3x - p0x) * t_split
            iy = p0y + (p3y - p0y) * t_split
            new_cmd = ["L", ix, iy]
            obj.path_data.insert(ci, new_cmd)
            if hasattr(obj, 'path_point_types') and obj.path_point_types:
                obj.path_point_types.insert(ci, "smooth")
            else:
                # Initialize the whole list now (covers older docs)
                ptypes = []
                for c in obj.path_data:
                    if not c: ptypes.append("corner"); continue
                    ptypes.append("smooth" if c[0] in ("C", "Q") else "corner")
                obj.path_point_types = ptypes
                obj.path_point_types[ci] = "smooth"
            # Promote L to C with visible tangents
            self._convert_point_to_smooth(obj, ci)
        elif seg_type == "C":
            # De Casteljau split — preserves the original curve shape
            cx1, cy1, cx2, cy2 = ctrl
            T = t_split; U = 1 - T
            # Q points (first level)
            q0x = U * p0x + T * cx1; q0y = U * p0y + T * cy1
            q1x = U * cx1 + T * cx2; q1y = U * cy1 + T * cy2
            q2x = U * cx2 + T * p3x; q2y = U * cy2 + T * p3y
            # R points (second level)
            r0x = U * q0x + T * q1x; r0y = U * q0y + T * q1y
            r1x = U * q1x + T * q2x; r1y = U * q1y + T * q2y
            # Split point (third level)
            mx_ = U * r0x + T * r1x; my_ = U * r0y + T * r1y
            # Replace original C with two C commands
            first_c  = ["C", q0x, q0y, r0x, r0y, mx_, my_]
            second_c = ["C", r1x, r1y, q2x, q2y, p3x, p3y]
            obj.path_data[ci] = first_c
            obj.path_data.insert(ci + 1, second_c)
            if hasattr(obj, 'path_point_types') and obj.path_point_types:
                # The new anchor between the two C's is smooth (it inherits
                # from the original curve's tangents which we just split).
                obj.path_point_types.insert(ci, "smooth")
        elif seg_type == "Q":
            # Quadratic split via de Casteljau
            cx, cy = ctrl
            T = t_split; U = 1 - T
            q0x = U * p0x + T * cx;  q0y = U * p0y + T * cy
            q1x = U * cx  + T * p3x; q1y = U * cy  + T * p3y
            mx_ = U * q0x + T * q1x; my_ = U * q0y + T * q1y
            first_q  = ["Q", q0x, q0y, mx_, my_]
            second_q = ["Q", q1x, q1y, p3x, p3y]
            obj.path_data[ci] = first_q
            obj.path_data.insert(ci + 1, second_q)
            if hasattr(obj, 'path_point_types') and obj.path_point_types:
                obj.path_point_types.insert(ci, "smooth")

        self._refresh_path_edit_handles()
        self.schedule_render(0)
        self.objectChanged.emit()

    def _convert_point_to_sharp(self, obj, ci):
        """Convert the endpoint at command index ci to a sharp (corner) point.
        For C commands: replace with L pointing to the same end coordinates.
        For Q commands: replace with L. M and L are already sharp."""
        cmd = obj.path_data[ci]
        if not cmd: return
        if cmd[0] == 'C':
            obj.path_data[ci] = ['L', cmd[5], cmd[6]]
        elif cmd[0] == 'Q':
            obj.path_data[ci] = ['L', cmd[3], cmd[4]]

    def _circle_tangent(self, p0, p1, p2):
        """v4.1.10.5: unit tangent vector at p1 of the circle through p0, p1, p2.
        Used by auto-smooth for visually natural curves. Falls back to chord
        direction (p2-p0) when the three points are collinear (infinite circle).
        Sign chosen so the tangent points 'forward' (from p0 toward p2)."""
        import math as _math
        x0, y0 = p0; x1, y1 = p1; x2, y2 = p2
        mx01, my01 = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        mx12, my12 = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        dx01, dy01 = x1 - x0, y1 - y0
        dx12, dy12 = x2 - x1, y2 - y1
        px01, py01 = dy01, -dx01   # perpendicular to p0-p1
        px12, py12 = dy12, -dx12   # perpendicular to p1-p2
        denom = px01 * py12 - py01 * px12
        if abs(denom) < 1e-9:
            # Collinear — fall back to chord direction
            cx_v = x2 - x0; cy_v = y2 - y0
            mag = _math.hypot(cx_v, cy_v) or 1.0
            return (cx_v / mag, cy_v / mag)
        t = ((mx12 - mx01) * py12 - (my12 - my01) * px12) / denom
        cx = mx01 + t * px01
        cy = my01 + t * py01
        # Tangent perpendicular to radius (p1 - center)
        rx, ry = x1 - cx, y1 - cy
        tx, ty = -ry, rx
        # Choose sign so tangent points along (p2 - p0)
        forward = (x2 - x0) * tx + (y2 - y0) * ty
        if forward < 0:
            tx, ty = -tx, -ty
        mag = _math.hypot(tx, ty) or 1.0
        return (tx / mag, ty / mag)

    def _convert_point_to_smooth(self, obj, ci):
        """v4.1.12: Set THIS anchor's tangents (cp2 of cmd[ci] + cp1 of
        cmd[ci+1]) using the quadratic Bezier method.

        DOES NOT TOUCH cp1 of cmd[ci] — that's the PREVIOUS anchor's
        tangent_out and is owned by ai-1, not ai. (Fixes 4.1.11.1 bug
        where setting smooth on one anchor moved its predecessor's
        tangent.)
        """
        if ci <= 0 or ci >= len(obj.path_data): return
        cmd = obj.path_data[ci]
        if not cmd: return
        if cmd[0] == 'L':
            ex, ey = cmd[1], cmd[2]
        elif cmd[0] == 'C':
            ex, ey = cmd[5], cmd[6]
        elif cmd[0] == 'Q':
            ex, ey = cmd[3], cmd[4]
        else:
            return
        prev_x, prev_y = self._prev_path_point(obj.path_data, ci)
        next_x, next_y = self._next_path_point(obj.path_data, ci)
        # Promote L/Q to C with collapsed cp1 (carries forward whatever the
        # previous anchor's tangent_out should be; the previous anchor owns
        # that cp1 and may set it independently — we set it to the segment
        # midpoint as a sensible default for collapsed/corner prev anchors).
        if cmd[0] != 'C':
            # Initial cp1 = prev_pos (collapsed). If prev anchor had a
            # tangent_out, it stays where it was (we'd need to migrate from
            # the previous Q or L, but those have no tangent state).
            obj.path_data[ci] = ['C', prev_x, prev_y, ex, ey, ex, ey]
            cmd = obj.path_data[ci]
        # Now compute THIS anchor's tangent_in (cp2) and tangent_out
        # (cp1 of next cmd) using the quadratic-Bezier method.
        import math as _math
        dx = next_x - prev_x; dy = next_y - prev_y
        chord_mag = _math.hypot(dx, dy)
        if chord_mag > 0.001:
            mag = chord_mag / 6.0
            if mag < 1.0: mag = 1.0
            ux = dx / chord_mag; uy = dy / chord_mag
            tx = ux * mag; ty = uy * mag
        else:
            tx = 1.0; ty = 0.0
        # cp2 = this anchor's tangent_in (incoming, points BACKWARD)
        cmd[3] = ex - tx; cmd[4] = ey - ty
        # cp1 of NEXT cmd = this anchor's tangent_out (outgoing)
        if (ci + 1 < len(obj.path_data) and obj.path_data[ci + 1]
            and obj.path_data[ci + 1][0] == 'C'):
            obj.path_data[ci + 1][1] = ex + tx
            obj.path_data[ci + 1][2] = ey + ty
        """Convert the endpoint at command index ci to a smooth bezier point.
        Generates symmetrical tangents based on neighbors.

        v4.1.8: closed-path aware — for the last point before Z, next is M
        (wrapping). For the first L/C in a closed path, prev wraps to the
        point before Z. This makes 'smooth' actually flow through the seam.
        """
        if ci == 0: return  # M cannot be a curve
        cmd = obj.path_data[ci]
        if not cmd: return
        # Determine endpoint coords
        if cmd[0] == 'L':
            ex, ey = cmd[1], cmd[2]
        elif cmd[0] == 'C':
            ex, ey = cmd[5], cmd[6]
        elif cmd[0] == 'Q':
            ex, ey = cmd[3], cmd[4]
        else:
            return
        # v4.1.8: detect closed path (last command is Z)
        is_closed = (obj.path_data and obj.path_data[-1]
                     and obj.path_data[-1][0] == "Z")
        last_drawn = len(obj.path_data) - (2 if is_closed else 1)  # index of last L/C/Q

        # Previous endpoint
        prev_x, prev_y = self._prev_path_point(obj.path_data, ci)
        # v4.1.8: if first drawn point in closed path, prev wraps to last
        if ci == 1 and is_closed and last_drawn >= 1:
            wrap = obj.path_data[last_drawn]
            if wrap:
                if wrap[0] == 'L': prev_x, prev_y = wrap[1], wrap[2]
                elif wrap[0] == 'C': prev_x, prev_y = wrap[5], wrap[6]
                elif wrap[0] == 'Q': prev_x, prev_y = wrap[3], wrap[4]

        # Next endpoint (for tangent direction)
        next_x, next_y = ex, ey
        next_ci = ci + 1
        if next_ci < len(obj.path_data):
            nxt = obj.path_data[next_ci]
            # Skip Z when looking for next
            if nxt and nxt[0] == 'Z':
                next_ci = None  # signal need to wrap
            elif nxt:
                if nxt[0] == 'L': next_x, next_y = nxt[1], nxt[2]
                elif nxt[0] == 'C': next_x, next_y = nxt[5], nxt[6]
                elif nxt[0] == 'Q': next_x, next_y = nxt[3], nxt[4]
        else:
            next_ci = None

        # v4.1.8: if no next (last drawn point in closed path), wrap to M
        if next_ci is None and is_closed and ci == last_drawn:
            m = obj.path_data[0]
            if m and m[0] == "M":
                next_x, next_y = m[1], m[2]

        # v4.1.10.5/4.1.11.1: use the QUADRATIC Bezier method —
        # P1 = 2*Pc - (P0+P2)/2 makes the quadratic pass through Pc at t=0.5,
        # which corresponds to a cubic with tangent direction (P2-P0) and
        # tangent magnitude |P2-P0|/6 on each side, symmetric.
        import math as _math
        dx = next_x - prev_x; dy = next_y - prev_y
        chord_mag = _math.hypot(dx, dy)
        if chord_mag > 0.001:
            mag = chord_mag / 6.0
            if mag < 1.0: mag = 1.0
            ux = dx / chord_mag; uy = dy / chord_mag
            tx = ux * mag; ty = uy * mag
        else:
            tx = 1.0; ty = 0.0
        # cp1 = previous endpoint + half-chord direction
        cp1x = prev_x + (ex - prev_x) / 3.0
        cp1y = prev_y + (ey - prev_y) / 3.0
        # cp2 = endpoint − tangent (incoming tangent at this anchor)
        cp2x = ex - tx; cp2y = ey - ty
        obj.path_data[ci] = ['C', cp1x, cp1y, cp2x, cp2y, ex, ey]
        # Update next cmd's cp1 (outgoing tangent at this anchor)
        if (ci + 1 < len(obj.path_data) and obj.path_data[ci + 1]
            and obj.path_data[ci + 1][0] == 'C'):
            obj.path_data[ci + 1][1] = ex + tx
            obj.path_data[ci + 1][2] = ey + ty

    def _path_connect_selected(self):
        """v4.1.11: Connect (merge) two selected anchors. Cases:
          - First + Last anchors of an OPEN path → close the path (smoothly
            merge into a single anchor at midpoint).
          - Any 2 adjacent anchors → merge into one anchor at midpoint,
            preserving tangent_in of first and tangent_out of second.

        Selection of non-adjacent anchors is rejected.
        """
        import math as _math
        page = self._cur_page()
        obj = page.get_object(self._path_edit_obj_id) if page else None
        if not obj or not obj.path_data:
            self._dbg('connect.abort', reason='no_obj_or_data'); return
        selected = sorted(self._path_selected_anchors or set())
        self._dbg('connect.enter', selected=selected, ncmds=len(obj.path_data))
        if len(selected) != 2:
            return
        n = self._anchor_count(obj)
        a_ci, b_ci = selected[0], selected[1]
        # Check adjacency. Open path: |b - a| == 1. Closed path: also (0, n-1).
        is_adjacent = (b_ci - a_ci == 1)
        is_wrap_pair = (self._is_closed_path(obj)
                        and a_ci == 0 and b_ci == n - 1)
        # SPECIAL: open path, first + last selected → close
        is_close_op = (not self._is_closed_path(obj)
                       and a_ci == 0 and b_ci == n - 1
                       and n >= 3)
        if not (is_adjacent or is_wrap_pair or is_close_op):
            return  # silently ignore — TODO: status bar message

        if is_close_op:
            # CLOSE the open path: merge last anchor's pos into M, append
            # a wrap-cmd that carries last's tangent_out as cp1 and M's
            # tangent_out (anchor 1's tangent_in via cmd[1].cp2 mirror) as
            # cp2. Drop last cmd.
            self._ensure_ptypes_initialized(obj)
            ptypes = obj.path_point_types
            last_pos = self._anchor_pos(obj, n - 1)
            m_pos = self._anchor_pos(obj, 0)
            if last_pos is None or m_pos is None: return
            mid = ((last_pos[0] + m_pos[0]) / 2.0,
                    (last_pos[1] + m_pos[1]) / 2.0)
            # Move M to midpoint
            obj.path_data[0][1] = mid[0]
            obj.path_data[0][2] = mid[1]
            # Get tangents we want to keep:
            #   - new anchor's tangent_in = LAST anchor's tangent_in
            #   - new anchor's tangent_out = path_data[1].cp1 (anchor 0's
            #     original outgoing); we keep this unchanged
            last_in_pos = self._anchor_tangent_in(obj, n - 1)
            last_out_pos = self._anchor_tangent_out(obj, n - 1)
            # Drop last cmd
            last_ci = self._anchor_cmd_index(obj, n - 1)
            del obj.path_data[last_ci]
            if last_ci < len(ptypes):
                del ptypes[last_ci]
            # Build wrap-cmd that closes back to (new) M position.
            # cp1 of wrap = where last_out_pos was (or last anchor's pos)
            # cp2 of wrap = where last_in_pos was
            cp1_w = last_out_pos if last_out_pos else last_pos
            cp2_w = last_in_pos  if last_in_pos  else last_pos
            obj.path_data.append(['C',
                cp1_w[0], cp1_w[1],
                cp2_w[0], cp2_w[1],
                mid[0], mid[1]])
            ptypes.append('smooth')
            obj.path_data.append(['Z'])
            ptypes.append('corner')
            # M's anchor type stays as-is (default corner)
            self._path_selected_anchors = {0}
        elif is_wrap_pair:
            # Closed path, 0 + (n-1) selected → this would "open" via merge,
            # but probably user meant disconnect. For now, ignore.
            return
        else:
            # Adjacent merge: anchors a and b=a+1
            self._ensure_ptypes_initialized(obj)
            ptypes = obj.path_point_types
            pos_a = self._anchor_pos(obj, a_ci)
            pos_b = self._anchor_pos(obj, b_ci)
            if pos_a is None or pos_b is None: return
            mid = ((pos_a[0] + pos_b[0]) / 2.0,
                    (pos_a[1] + pos_b[1]) / 2.0)
            # Keep: tangent_in of a, tangent_out of b
            tin_a = self._anchor_tangent_in(obj, a_ci)
            tout_b = self._anchor_tangent_out(obj, b_ci)
            # The merged anchor will live at cmd index a_ci; its endpoint = mid
            cmd_a = obj.path_data[a_ci]
            # We want cmd_a (the merged anchor cmd) to be C with:
            #   cp1 unchanged (anchor a's incoming side, was set by previous anchor's outgoing)
            #   cp2 = tin_a (a's incoming tangent, preserved)
            #   endpoint = mid
            if cmd_a[0] == 'M':
                obj.path_data[a_ci] = ['M', mid[0], mid[1]]
            elif cmd_a[0] == 'L':
                obj.path_data[a_ci] = ['L', mid[0], mid[1]]
            elif cmd_a[0] == 'C':
                if tin_a is not None:
                    cmd_a[3] = tin_a[0]; cmd_a[4] = tin_a[1]
                cmd_a[5] = mid[0]; cmd_a[6] = mid[1]
            # Now anchor b's outgoing (cmd[b+1].cp1) should become anchor a's outgoing
            if tout_b is not None:
                # Find the cmd that holds b's tangent_out
                tout_storage = self._tangent_out_storage(obj, b_ci)
                if tout_storage is not None:
                    out_cmd, ix, iy = tout_storage
                    # That cmd's cp1 = tout_b (already is). We want to keep that
                    # value AFTER deleting cmd[b_ci]. Index shifts down by 1.
                    pass
            # Delete cmd at b_ci (the second anchor)
            del obj.path_data[b_ci]
            if b_ci < len(ptypes):
                del ptypes[b_ci]
            self._path_selected_anchors = {a_ci}

        self._normalize_path_bbox(obj)
        self._refresh_path_edit_handles()
        self._refresh_overlay()
        self.schedule_render(0)
        self.objectChanged.emit()

    def _path_disconnect_selected(self):
        """v4.1.11/4.1.12: Disconnect one selected anchor.

        Cases:
          - Anchor 0 (M) of CLOSED path → OPEN: remove the wrap-cmd (last
            drawn cmd) + Z. Path becomes open with the same anchors.
          - Last anchor (n-1) of CLOSED path → OPEN: remove wrap + Z too
            (same effect, the closure happens between last and M either way).
          - Any other anchor on CLOSED path → SPLIT: add a 2nd anchor 5mm
            away. Path stays closed.
          - Any anchor on OPEN path → SPLIT: same, path stays open.
        """
        import math as _math
        page = self._cur_page()
        obj = page.get_object(self._path_edit_obj_id) if page else None
        if not obj or not obj.path_data:
            self._dbg('disconnect.abort', reason='no_obj_or_data'); return
        selected = list(self._path_selected_anchors or set())
        self._dbg('disconnect.enter', selected=sorted(selected), ncmds=len(obj.path_data))
        if len(selected) != 1: return
        ci = selected[0]
        n = self._anchor_count(obj)
        self._ensure_ptypes_initialized(obj)
        ptypes = obj.path_point_types

        # v4.1.12.2/4.1.12.3: Disconnect on a CLOSED path always opens it.
        # The selected anchor is "broken into two" — one staying at the
        # path's START (M, takes tangent_out), the other at the path's END
        # (last anchor, takes tangent_in). Both sit at the same position,
        # 5mm apart so they're individually grabbable. User can drag either
        # one separately, or select both and Connect to rejoin.
        if self._is_closed_path(obj):
            # First, capture the selected anchor's POSITION and its
            # tangent_in (from wrap-cmd's cp2, if it exists) — that becomes
            # the new END anchor's incoming tangent.
            sel_pos = self._anchor_pos(obj, ci)
            sel_tangent_in = self._anchor_tangent_in(obj, ci)
            sel_tangent_out = self._anchor_tangent_out(obj, ci)
            wci = self._wrap_cmd_index(obj)
            # Get wrap-cmd's cp2 (= tangent_in of M = tangent_in of anchor 0)
            wrap_cp2 = None
            if wci is not None:
                wcmd = obj.path_data[wci]
                if wcmd and wcmd[0] == 'C':
                    wrap_cp2 = (wcmd[3], wcmd[4])
            # Strip Z + wrap-cmd
            if obj.path_data[-1][0] == 'Z':
                del obj.path_data[-1]
                if len(ptypes) > len(obj.path_data): del ptypes[-1]
            if wci is not None and 0 <= wci < len(obj.path_data):
                del obj.path_data[wci]
                if wci < len(ptypes): del ptypes[wci]

            # Step: rotate path so ci becomes index 0 (M).
            if ci != 0:
                if obj.path_data and obj.path_data[0][0] == 'M':
                    om = obj.path_data[0]
                    obj.path_data[0] = ['L', om[1], om[2]]
                ci_cmd = obj.path_data[ci]
                if ci_cmd[0] == 'L':
                    obj.path_data[ci] = ['M', ci_cmd[1], ci_cmd[2]]
                elif ci_cmd[0] == 'C':
                    obj.path_data[ci] = ['M', ci_cmd[5], ci_cmd[6]]
                obj.path_data[:] = obj.path_data[ci:] + obj.path_data[:ci]
                ptypes[:] = ptypes[ci:] + ptypes[:ci]

            # Now ci is 0. Append an L cmd at end with SAME pos as M, so the
            # path has TWO anchors at that location (start and end of the
            # now-open path). User can drag either independently.
            m_cmd = obj.path_data[0]
            m_pos = (m_cmd[1], m_cmd[2])
            # Offset the END anchor 5mm so they're not on top of each other.
            # Use a sensible direction: opposite of M's outgoing tangent
            # (or just (-5, 0) fallback).
            import math as _math
            offset = None
            tout_now = self._anchor_tangent_out(obj, 0)   # outgoing of new M
            if tout_now is not None:
                dx = tout_now[0] - m_pos[0]; dy = tout_now[1] - m_pos[1]
                d = _math.hypot(dx, dy)
                if d > 0.1:
                    offset = (-dx / d * 5.0, -dy / d * 5.0)   # backwards
            if offset is None:
                offset = (-5.0, 0.0)
            end_pos = (m_pos[0] + offset[0], m_pos[1] + offset[1])
            # If selection had an explicit tangent_in (wrap-C had cp2 at
            # specific location), we'd like the new end's cp2 to reflect
            # that. But since the cmd is L (corner) by default, no cp2.
            # User can upgrade end to bezier with Ctrl+drag or type menu.
            obj.path_data.append(['L', end_pos[0], end_pos[1]])
            ptypes.append('corner')

            self._path_selected_anchors = {0}
        else:
            # SPLIT the anchor into two (open path or already-opened)
            pos = self._anchor_pos(obj, ci)
            if pos is None: return
            tout = self._anchor_tangent_out(obj, ci)
            # Offset for second anchor: 5mm along tangent_out, fallback chain
            offset = None
            if tout is not None:
                dx = tout[0] - pos[0]; dy = tout[1] - pos[1]
                d = _math.hypot(dx, dy)
                if d > 0.1:
                    offset = (dx / d * 5.0, dy / d * 5.0)
            if offset is None:
                nxt = self._neighbor_anchor_pos(obj, ci, +1)
                if nxt is not None:
                    dx = nxt[0] - pos[0]; dy = nxt[1] - pos[1]
                    d = _math.hypot(dx, dy)
                    if d > 0.1:
                        offset = (dx / d * 5.0, dy / d * 5.0)
            if offset is None:
                offset = (5.0, 0.0)
            second_pos = (pos[0] + offset[0], pos[1] + offset[1])
            obj.path_data.insert(ci + 1, ['L', second_pos[0], second_pos[1]])
            ptypes.insert(ci + 1, 'corner')
            self._path_selected_anchors = {ci + 1}

        self._normalize_path_bbox(obj)
        self._refresh_path_edit_handles()
        self._refresh_overlay()
        self.schedule_render(0)
        self.objectChanged.emit()

    def _delete_path_point(self, obj, ci):
        """Remove the point at command index ci. Don't allow removing M."""
        if ci == 0: return  # cannot remove the M
        if len(obj.path_data) <= 2: return
        del obj.path_data[ci]

    def mouseDoubleClickEvent(self,event):
        # v4.0.3: double-click finishes path drawing
        if getattr(self, '_path_drawing', False):
            self._finish_path_drawing()
            event.accept(); return
        # v4.2.11.45: in document mode the body sits in near-permanent sticky
        # inline edit, so the `not self._inline_widget` guard below made it
        # impossible to double-click INTO a header/footer -- the event was
        # silently swallowed while the body editor was open (i.e. almost
        # always). If a double-click lands on a header/footer box while some
        # inline session is active, commit that session and switch the editor
        # to the band.
        if event.button()==Qt.MouseButton.LeftButton and self._inline_widget:
            try:
                sp=self._sp(event); hit=self._hit_obj(sp, allow_hf=True)
                cur_id=getattr(self._inline_obj, 'id', None)
                tgt=self._find_obj(hit) if (hit and hit != cur_id) else None
                from edof.format.document_boxes import (
                    DocumentHeaderBox, DocumentFooterBox)
                if tgt is not None and isinstance(
                        tgt, (DocumentHeaderBox, DocumentFooterBox)):
                    # v4.2.11.46: keep the viewport stable during the switch:
                    # don't flip the reserved toolbar margin off/on (84->0->84
                    # shifted the whole page = visible jump) and restore the
                    # scroll position afterwards.
                    self._inline_switching = True
                    _hsb = self.horizontalScrollBar().value()
                    _vsb = self.verticalScrollBar().value()
                    self._skip_sticky_reentry = True
                    try:
                        ed = self._inline_widget
                        if ed is not None:
                            ed.commit_to_textbox()
                    except Exception:
                        pass
                    if self._inline_widget is not None:
                        self._cancel_inline()
                    self._skip_sticky_reentry = False
                    # The commit may have repaginated and replaced the box
                    # instance -- re-resolve it on the current page.
                    fresh = self._find_obj(tgt.id) or tgt
                    self._sel_id = fresh.id
                    self._start_inline(fresh)
                    self._inline_switching = False
                    try:
                        self.horizontalScrollBar().setValue(_hsb)
                        self.verticalScrollBar().setValue(_vsb)
                    except Exception:
                        pass
                    event.accept(); return
            except Exception:
                import traceback as _tb; _tb.print_exc()
        if event.button()==Qt.MouseButton.LeftButton and not self._inline_widget:
            sp=self._sp(event); hit=self._hit_obj(sp, allow_hf=True)
            if hit:
                self._sel_id=hit; obj=self._sel_obj()
                if   isinstance(obj, edof.TextBox):  self._start_inline(obj)
                elif isinstance(obj, edof.QRCode):   self._edit_qr_inline(obj)
                elif isinstance(obj, edof.ImageBox): self._edit_image_inline(obj)
                # v4.1.2: double-click on embedded sub-document opens it in a new window
                elif isinstance(obj, edof.SubDocumentBox):
                    mw = self._main_window()
                    if mw and hasattr(mw, '_open_subdoc_in_tab'):
                        mw._open_subdoc_in_tab(obj)
                # v4.1.13: double-click on SvgBox offers conversion to native shapes
                elif isinstance(obj, edof.SvgBox):
                    from PyQt6.QtWidgets import QMessageBox as _QMB
                    res = _QMB.question(
                        self, "Convert SVG",
                        "Convert this SVG to native EDOF path shapes for editing?\n\n"
                        "Yes:   Shapes will be extracted; the original SVG is discarded.\n"
                        "No:    Keep as raster-displayed SVG (saved losslessly).",
                        _QMB.StandardButton.Yes | _QMB.StandardButton.No,
                        _QMB.StandardButton.No)
                    if res == _QMB.StandardButton.Yes:
                        mw = self._main_window()
                        if mw and hasattr(mw, '_convert_svgbox_to_shapes'):
                            mw._convert_svgbox_to_shapes(obj)
                    event.accept(); return
                # v4.1.10.2: double-click on Shape(path) enters path edit mode
                elif (isinstance(obj, edof.Shape)
                      and obj.shape_type == 'path' and obj.path_data):
                    self._path_edit_obj_id = obj.id
                    self._path_selected_anchors = set()
                    self._refresh_path_edit_handles()
                    self.schedule_render(0)
        super().mouseDoubleClickEvent(event)

    def _edit_qr_inline(self, obj):
        """Double-click QR → quick edit of data/URL in a small overlay."""
        self._cancel_inline()
        t    = obj.transform
        dpi  = self._dpi; zoom = self._zoom
        scene_tl = QPointF(mm_to_px(t.x, dpi), mm_to_px(t.y, dpi))
        vp_tl    = self.mapFromScene(scene_tl)
        w_vp = int(max(120, mm_to_px(t.width,  dpi) * zoom))

        ed = QLineEdit(self.viewport())
        ed.setText(obj.data)
        ed.setGeometry(vp_tl.x(), vp_tl.y(), w_vp, 28)
        ed.setStyleSheet(
            f"background:#ffffdd;color:#000;border:2px solid {ACC};"
            f"padding:2px;font-size:10pt;border-radius:0px")
        ed.setPlaceholderText("QR data / URL…")
        ed.show(); ed.setFocus(); ed.selectAll()

        self._inline_widget = ed
        self._inline_id     = obj.id
        self._inline_obj    = obj

        def on_change(text):
            obj.data = text
            self.schedule_render(300)
            self.objectChanged.emit()
        ed.textChanged.connect(on_change)

        def key_handler(event, _orig=ed.keyPressEvent):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                               Qt.Key.Key_Escape):
                self._confirm_inline(); return
            _orig(event)
        ed.keyPressEvent = key_handler

        def focus_out(event, _orig=ed.focusOutEvent):
            _orig(event); QTimer.singleShot(80, self._confirm_inline)
        ed.focusOutEvent = focus_out

    def _edit_image_inline(self, obj):
        """Double-click ImageBox → open file picker to replace source."""
        from PyQt6.QtWidgets import QFileDialog
        p, _ = QFileDialog.getOpenFileName(
            self, "Replace Image Source", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp);;All (*.*)")
        if p and self._doc:
            rid = self._doc.add_resource_from_file(p)
            obj.resource_id = rid
            # Clear variable binding if set (explicit file takes precedence)
            self.schedule_render()
            self.objectChanged.emit()

    def wheelEvent(self,event):
        # v4.1.22.3: refined scroll controls
        #   plain wheel    → scroll vertically (typical reading direction)
        #   Shift + wheel  → scroll horizontally
        #   Alt + wheel    → zoom (also Ctrl, for users who expect either)
        #   Ctrl + wheel   → zoom (legacy / common convention)
        mods = event.modifiers()
        dy = event.angleDelta().y()
        dx = event.angleDelta().x()
        zoom_mod = bool(mods & (Qt.KeyboardModifier.AltModifier
                                | Qt.KeyboardModifier.ControlModifier))
        horiz_mod = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if zoom_mod:
            # v4.1.22.11: on Linux/X11, Alt+VerticalWheel is sometimes
            # delivered with the delta on the horizontal axis instead.
            # Use whichever axis has a non-zero delta to decide zoom in
            # vs zoom out. Without this, holding Alt always read dy=0
            # and the comparison `dy > 0` was False → zoom-out only.
            delta = dy if dy else dx
            f = 1.15 if delta > 0 else 1/1.15
            self._set_zoom(self._zoom * f)
            event.accept(); return
        # Pan via scroll bars (steps of ~3 lines per notch)
        step = 120  # one wheel notch = 120 units
        h_bar = self.horizontalScrollBar()
        v_bar = self.verticalScrollBar()
        scroll_unit = max(20, v_bar.singleStep() * 4)
        if horiz_mod:
            # When Shift held, vertical wheel delta drives horizontal scroll.
            # Also honour any natural horizontal delta from touchpads.
            delta = -(dy if dy else dx) / step * scroll_unit
            h_bar.setValue(int(h_bar.value() + delta))
        else:
            # Vertical scroll. Some touchpads send dx for horizontal — keep
            # vertical wheel as the primary axis.
            delta = -dy / step * scroll_unit
            # v4.1.23.47: Word-like continuous feel without a full stacked
            # layout — when already at the top/bottom of the current page and
            # the wheel keeps going that way, flip to the adjacent page and
            # land the view at the matching edge. move_cursor=False so the
            # caret and focus stay put (scrolling must never steal focus).
            at_bottom = v_bar.value() >= v_bar.maximum() - 1
            at_top = v_bar.value() <= v_bar.minimum() + 1
            doc_ok = (self._doc is not None and len(self._doc.pages) > 1)
            if doc_ok and dy < 0 and at_bottom \
                    and self._page_idx < len(self._doc.pages) - 1:
                self.set_page(self._page_idx + 1, move_cursor=False)
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().minimum())
                event.accept(); return
            if doc_ok and dy > 0 and at_top and self._page_idx > 0:
                self.set_page(self._page_idx - 1, move_cursor=False)
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().maximum())
                event.accept(); return
            v_bar.setValue(int(v_bar.value() + delta))
            if dx:
                h_delta = -dx / step * scroll_unit
                h_bar.setValue(int(h_bar.value() + h_delta))
        event.accept()

    def _dbg(self, tag, **extra):
        """Detailed, opt-in debug for curve creation/editing + key handling.
        No-op unless EDOF_DEBUG is enabled. Always records the current mode and
        path state so the log shows context for every event."""
        try:
            from edof.engine.debug_log import is_enabled, log as _dlog
            if not is_enabled():
                return
        except Exception:
            return
        try:
            st = {
                'mode': ('draw' if getattr(self, '_path_drawing', False)
                         else 'pathedit' if getattr(self, '_path_edit_obj_id', None)
                         else 'rectdraw' if getattr(self, '_rect_draw_kind', None)
                         else 'normal'),
                'sel': getattr(self, '_sel_id', None),
                'edit_id': getattr(self, '_path_edit_obj_id', None),
                'npts': len(getattr(self, '_path_points', []) or []),
                'drag_h': getattr(self, '_path_drag_handle', None) is not None,
                'drag_o': getattr(self, '_path_drag_origin', None) is not None,
            }
            st.update(extra)
            _dlog('curve.' + tag, **st)
        except Exception:
            pass

    def keyPressEvent(self,event):
        self._dbg('keyPress', key=_key_name(event.key()), text=event.text(),
                  mods=_mods_str(event.modifiers()), rep=event.isAutoRepeat())
        # v4.2.9.7: Alt held over the page -> show the magnifier cursor (the
        # wheel will zoom). Doesn't consume the event (Alt stays a modifier).
        if event.key() == Qt.Key.Key_Alt and not getattr(self, '_alt_zoom_on', False):
            self._alt_zoom_on = True
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.setOverrideCursor(_zoom_cursor())
            except Exception: pass
        # v4.1.16.3: if inline edit is active, ALL key events go to the
        # editor widget (arrow keys, delete, etc). Without this guard the
        # canvas would nudge the textbox object while the user is trying
        # to navigate the cursor or delete text.
        if self._inline_widget is not None:
            self._dbg('key.toInline', key=_key_name(event.key()))
            super().keyPressEvent(event); return
        # v4.1.15: rect draw — Esc cancels
        if self._rect_draw_kind is not None and event.key() == Qt.Key.Key_Escape:
            self._dbg('key.rectDrawEsc')
            self._cancel_rect_draw()
            event.accept(); return
        # v4.0.3: path drawing tool keyboard handling
        if getattr(self, '_path_drawing', False):
            key=event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._dbg('key.finishDraw')
                self._finish_path_drawing()
                event.accept(); return
            elif key == Qt.Key.Key_Escape:
                self._dbg('key.cancelDraw')
                self._cancel_path_drawing()
                event.accept(); return
            elif key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                # undo last placed point while drawing (if supported below)
                self._dbg('key.drawBackspace')
        # v4.1.11: in path edit mode, C = Connect / D = Disconnect / Esc = exit
        if getattr(self, '_path_edit_obj_id', None):
            key = event.key()
            if key == Qt.Key.Key_C and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._dbg('key.connect')
                self._path_connect_selected()
                event.accept(); return
            if key == Qt.Key.Key_D and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._dbg('key.disconnect')
                self._path_disconnect_selected()
                event.accept(); return
            if key == Qt.Key.Key_Escape:
                self._dbg('key.exitPathEdit')
                self._exit_path_edit_mode()
                self.schedule_render(0)
                event.accept(); return
        obj=self._sel_obj()
        if not obj or obj.locked: super().keyPressEvent(event); return
        # v4.1.15: F2 or Enter on a selected TextBox starts inline edit
        if (isinstance(obj, edof.TextBox)
            and event.key() in (Qt.Key.Key_F2, Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not self._inline_widget):
            self._start_inline(obj)
            event.accept(); return
        d=0.5; key=event.key()
        if   key==Qt.Key.Key_Left:  obj.transform.translate(-d,0)
        elif key==Qt.Key.Key_Right: obj.transform.translate(d,0)
        elif key==Qt.Key.Key_Up:    obj.transform.translate(0,-d)
        elif key==Qt.Key.Key_Down:  obj.transform.translate(0,d)
        elif key in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace): self._do_delete(); return
        else: super().keyPressEvent(event); return
        self._refresh_overlay(); self.objectChanged.emit(); self.schedule_render(60)

    # ── Drag ──────────────────────────────────────────────────────────────────

    def _compute_anchor(self,tf,handle):
        afx,afy=SelectionOverlay._ANCHOR.get(handle,(0,0))
        ax=tf.x+afx*tf.width; ay=tf.y+afy*tf.height
        cx=tf.x+tf.width/2; cy=tf.y+tf.height/2
        return rotate_point(ax,ay,cx,cy,tf.rotation)

    def _snap_to_neighbors(self, obj, x, y, w, h, threshold_mm=1.5):
        """v4.0.1: Snap object's edges and center to nearby objects' edges/centers.
        Returns (snapped_x, snapped_y, snapped_flag).
        """
        pg=self._cur_page()
        if not pg: return x, y, False
        # Candidate snap lines from other objects (excluding self & multi-sel)
        excluded={obj.id} | self._multi_sel_ids
        x_lines=[]; y_lines=[]
        for o in pg.objects:
            if o.id in excluded: continue
            if not getattr(o,'visible',True): continue
            t=o.transform
            x_lines.extend([t.x, t.x + t.width, t.x + t.width/2])
            y_lines.extend([t.y, t.y + t.height, t.y + t.height/2])
        # Page edges
        x_lines.extend([0, pg.width, pg.width/2])
        y_lines.extend([0, pg.height, pg.height/2])
        # Object's own snap candidates: left, right, center
        my_x_pts=[(x, 'L'), (x + w, 'R'), (x + w/2, 'C')]
        my_y_pts=[(y, 'T'), (y + h, 'B'), (y + h/2, 'C')]
        snap_x=x; snap_y=y; snapped=False
        best_dx=threshold_mm
        for mx, _ in my_x_pts:
            for tx in x_lines:
                d=abs(mx - tx)
                if d < best_dx:
                    best_dx=d
                    snap_x=x + (tx - mx); snapped=True
        best_dy=threshold_mm
        for my, _ in my_y_pts:
            for ty in y_lines:
                d=abs(my - ty)
                if d < best_dy:
                    best_dy=d
                    snap_y=y + (ty - my); snapped=True
        return snap_x, snap_y, snapped

    def _apply_drag(self,sp,shift,alt,ctrl=False):
        """v4.0.3: refactored drag logic.

        Modifier semantics (revised):
          - Ctrl  → bypass ALL snapping (grid + alignment guides + margins)
          - Alt   → bypass snapping (legacy alias for Ctrl, kept for compatibility)
          - Shift on RESIZE → toggle uniform/non-uniform scale.
                             Default for ImageBox is uniform (preserve aspect ratio);
                             Shift toggles to non-uniform. For other objects, default
                             is non-uniform (legacy); Shift forces uniform.
          - Shift on ROTATE → snap to 15° increments (same as before).
        """
        obj=self._sel_obj()
        if not obj: return
        tf=self._drag_tf0
        from edof.format.objects import ImageBox
        no_snap = alt or ctrl   # v4.0.3: Ctrl is the new "bypass snap"

        if self._drag_mode=='move':
            dx=px_to_mm(sp.x()-self._drag_sp0.x(),self._dpi)
            dy=px_to_mm(sp.y()-self._drag_sp0.y(),self._dpi)
            new_x=tf.x+dx; new_y=tf.y+dy
            # Snap to grid
            if self._snap_to_grid and not no_snap:
                s=self._snap_size_mm
                new_x=round(new_x/s)*s
                new_y=round(new_y/s)*s
            # Snap to margins (v4.0.3)
            if not no_snap:
                new_x, new_y = self._snap_to_margins(
                    obj, new_x, new_y, tf.width, tf.height)
            # Alignment guides — snap to other objects' edges/centers
            if self._show_align_guides and not no_snap:
                new_x, new_y, snapped = self._snap_to_neighbors(
                    obj, new_x, new_y, tf.width, tf.height)
            obj.transform.x=new_x; obj.transform.y=new_y
            # Move multi-selected objects together
            applied_dx=new_x-tf.x; applied_dy=new_y-tf.y
            for mid, mtf0 in getattr(self, '_multi_drag_tf0', {}).items():
                mobj=self._find_obj(mid)
                if mobj:
                    mobj.transform.x=mtf0.x+applied_dx
                    mobj.transform.y=mtf0.y+applied_dy

        elif self._drag_mode=='rotate':
            cx_s=mm_to_px(tf.x+tf.width/2,self._dpi)
            cy_s=mm_to_px(tf.y+tf.height/2,self._dpi)
            angle=math.degrees(math.atan2(sp.y()-cy_s,sp.x()-cx_s))+90
            if shift and not no_snap:
                angle=round(angle/15)*15
            elif self._snap_to_grid and not no_snap:
                angle=round(angle/15)*15
            obj.transform.rotation=angle%360

        elif self._drag_mode.startswith('line_'):
            ptk=self._drag_mode.split('_')[1]; mx,my=self._to_mm(sp)
            if self._snap_to_grid and not no_snap:
                s=self._snap_size_mm
                mx=round(mx/s)*s; my=round(my/s)*s
            idx=0 if ptk=='P1' else 1
            pts=list(obj.points); pts[idx]=[mx,my]; obj.points=pts
            x1,y1=pts[0]; x2,y2=pts[1]
            obj.transform.x=min(x1,x2); obj.transform.y=min(y1,y2)
            obj.transform.width=max(abs(x2-x1),MIN_MM); obj.transform.height=max(abs(y2-y1),MIN_MM)

        else:
            # Resize
            handle=self._drag_mode.replace('resize_','')
            sw,sh=SelectionOverlay._SIGN.get(handle,(1,1))
            cos_r=math.cos(math.radians(tf.rotation)); sin_r=math.sin(math.radians(tf.rotation))
            ax,ay=self._drag_anchor; mx,my=self._to_mm(sp)
            # Snap mouse to grid for non-rotated objects
            if self._snap_to_grid and not no_snap and abs(tf.rotation) < 0.01:
                s=self._snap_size_mm
                mx=round(mx/s)*s
                my=round(my/s)*s
            vx,vy=mx-ax,my-ay

            # v4.0.3: Decide aspect-ratio behavior
            # Default for ImageBox = uniform (preserve aspect ratio)
            # Shift toggles to non-uniform.
            # For other objects, default = non-uniform; Shift forces uniform.
            # v4.1.16.6: TextBox — drag rohu vždy mění rozměry pole. SHIFT
            # navíc DEFORMUJE TEXT: font_size se škáluje proporčně podle
            # plochy boxu (geometric mean sx,sy). Žádné Ctrl rozlišení.
            from edof.format.objects import TextBox as _TB
            is_image = isinstance(obj, ImageBox)
            is_textbox = isinstance(obj, _TB)
            if is_image:
                uniform = not shift
            elif is_textbox:
                # TextBox: always non-uniform dimensions (text reflows).
                # Shift is handled below by also scaling font.
                uniform = False
            else:
                # Other: non-uniform unless Shift
                uniform = shift

            # Compute new dimensions in local axes
            new_w_raw = sw*(vx*cos_r+vy*sin_r) if sw else tf.width
            new_h_raw = sh*(vx*(-sin_r)+vy*cos_r) if sh else tf.height

            if uniform and sw and sh and tf.width > 0 and tf.height > 0:
                # Preserve aspect ratio: pick whichever scale is bigger and apply both
                aspect = tf.height / tf.width
                # Choose dominant axis based on which the user moved further
                if abs(new_w_raw - tf.width) >= abs(new_h_raw - tf.height):
                    new_w = max(MIN_MM, new_w_raw)
                    new_h = max(MIN_MM, new_w * aspect)
                else:
                    new_h = max(MIN_MM, new_h_raw)
                    new_w = max(MIN_MM, new_h / aspect)
            elif uniform and (not sw or not sh):
                # Edge handle on uniform mode: only one axis active, leave the other alone
                new_w = max(MIN_MM, new_w_raw) if sw else tf.width
                new_h = max(MIN_MM, new_h_raw) if sh else tf.height
            else:
                new_w = max(MIN_MM, new_w_raw) if sw else tf.width
                new_h = max(MIN_MM, new_h_raw) if sh else tf.height

            # v4.1.7: For Shape with path_data, scale local path coordinates
            # proportionally so resizing the bbox actually resizes the curve
            # (same behavior as Photoshop / Illustrator).
            from edof.format.objects import Shape, SHAPE_PATH
            if (isinstance(obj, Shape) and obj.shape_type == SHAPE_PATH
                and obj.path_data and tf.width > 0 and tf.height > 0):
                sx = new_w / tf.width
                sy = new_h / tf.height
                if abs(sx - 1.0) > 0.001 or abs(sy - 1.0) > 0.001:
                    # Use the original path_data captured at drag start, scaled
                    # to current dimensions — avoids drift across many small mouseMoves.
                    base = getattr(self, '_drag_path_data0', None)
                    if base is not None:
                        new_data = []
                        for cmd in base:
                            if not cmd: new_data.append(cmd); continue
                            op = cmd[0]
                            if op == "M" or op == "L":
                                new_data.append([op, cmd[1] * sx, cmd[2] * sy])
                            elif op == "C":
                                new_data.append([op,
                                    cmd[1] * sx, cmd[2] * sy,
                                    cmd[3] * sx, cmd[4] * sy,
                                    cmd[5] * sx, cmd[6] * sy])
                            elif op == "Q":
                                new_data.append([op,
                                    cmd[1] * sx, cmd[2] * sy,
                                    cmd[3] * sx, cmd[4] * sy])
                            else:
                                new_data.append(cmd)
                        obj.path_data = new_data

            # v4.1.16.7: TextBox font deformation — Shift only.
            # Instead of multiplying font_size (which scales uniformly),
            # we update glyph_scale_x/y. The renderer then renders the
            # text at natural size and resamples non-uniformly — true
            # letter stretching, not just font scaling.
            if is_textbox and shift:
                f_gsx0 = getattr(self, '_drag_glyph_scale_x0', 1.0)
                f_gsy0 = getattr(self, '_drag_glyph_scale_y0', 1.0)
                if tf.width > 0 and tf.height > 0:
                    sx = new_w / tf.width
                    sy = new_h / tf.height
                    obj.style.glyph_scale_x = max(0.05, f_gsx0 * sx)
                    obj.style.glyph_scale_y = max(0.05, f_gsy0 * sy)
            # v4.0.3 fix: keep the OPPOSITE corner fixed (the anchor).
            # Previous logic computed new_cx/cy from sw/sh signs and resulted
            # in image jumping when only one axis was scaled.
            new_cx = ax + sw*new_w/2*cos_r + sh*new_h/2*(-sin_r)
            new_cy = ay + sw*new_w/2*sin_r + sh*new_h/2*cos_r
            obj.transform.x = new_cx - new_w/2
            obj.transform.y = new_cy - new_h/2
            obj.transform.width = new_w
            obj.transform.height = new_h

        self._refresh_overlay(); self._show_preview(obj)
        # v4.1.15.1: realtime canvas re-render during drag (not just preview).
        # Throttled at ~50ms via schedule_render's pending-deadline check.
        self.schedule_render(50)
        # If we're in inline edit on this object, reposition the inline widget
        # so its geometry tracks the live drag.
        if self._inline_widget is not None and self._inline_id == obj.id:
            self._reposition_inline()

    def _snap_to_margins(self, obj, new_x, new_y, w, h):
        """v4.0.3: snap to document-level margins if enabled."""
        if not getattr(self, '_margins_enabled', False):
            return new_x, new_y
        if self._doc is None or not self._doc.pages:
            return new_x, new_y
        page_idx = getattr(self, '_page_idx', 0)
        if page_idx >= len(self._doc.pages):
            return new_x, new_y
        page = self._doc.pages[page_idx]
        m = getattr(self, '_margins', None)
        if not m:
            return new_x, new_y
        top, right, bottom, left = m
        threshold = 2.0  # mm
        page_w = page.width
        page_h = page.height
        # left edge
        if abs(new_x - left) < threshold:
            new_x = left
        # right edge of object
        if abs(new_x + w - (page_w - right)) < threshold:
            new_x = page_w - right - w
        # top edge
        if abs(new_y - top) < threshold:
            new_y = top
        # bottom edge
        if abs(new_y + h - (page_h - bottom)) < threshold:
            new_y = page_h - bottom - h
        return new_x, new_y

    # ── v4.0.3: Path drawing helpers ──────────────────────────────────────────
    def _draw_path_preview(self):
        """Draw temporary lines/curves connecting collected path points,
        with visible bezier handles."""
        for item in getattr(self, '_path_preview_items', []):
            try: self.scene().removeItem(item)
            except Exception: pass
        self._path_preview_items=[]
        if len(self._path_points) < 1: return
        # v4.2.10.8: size preview dots/handles in SCREEN pixels (divide by zoom)
        # and use cosmetic pens, matching edit-mode handles. Previously they were
        # fixed scene-px radii, so they grew/shrank with zoom during drawing.
        _z = max(0.05, float(getattr(self, '_zoom', 1.0) or 1.0))
        pen=QPen(QColor(120,180,255,200),2,Qt.PenStyle.SolidLine); pen.setCosmetic(True)
        handle_pen = QPen(QColor(255, 200, 80, 200), 1, Qt.PenStyle.DashLine); handle_pen.setCosmetic(True)
        cp_brush = QBrush(QColor(255, 220, 100, 200))
        # First point larger and orange to indicate "click to close"
        for i,p in enumerate(self._path_points):
            mx, my = p[0], p[1]
            x=mm_to_px(mx, self._dpi); y=mm_to_px(my, self._dpi)
            r = (5 if i == 0 and len(self._path_points) >= 3 else 3) / _z
            color = QColor(220, 130, 80) if i == 0 and len(self._path_points) >= 3 else QColor(120,180,255)
            _dot_pen = QPen(color, 1.5); _dot_pen.setCosmetic(True)
            dot=self.scene().addEllipse(x-r, y-r, 2*r, 2*r,
                                          _dot_pen,
                                          QBrush(color))
            dot.setZValue(9000)
            self._path_preview_items.append(dot)
            # v4.1.3: if this is a 'C' point, draw the handle (line to control + dot)
            if p[2] == 'C' and len(p) >= 5:
                hx, hy = p[3], p[4]
                hxp = mm_to_px(hx, self._dpi); hyp = mm_to_px(hy, self._dpi)
                line = self.scene().addLine(x, y, hxp, hyp, handle_pen)
                line.setZValue(9000)
                self._path_preview_items.append(line)
                _cr = 3 / _z
                _cp_pen = QPen(QColor(255, 200, 80, 255), 1); _cp_pen.setCosmetic(True)
                cp_dot = self.scene().addEllipse(hxp - _cr, hyp - _cr, 2*_cr, 2*_cr,
                                                    _cp_pen,
                                                    cp_brush)
                cp_dot.setZValue(9000)
                self._path_preview_items.append(cp_dot)

        # Connect with lines or bezier curves between consecutive points
        if len(self._path_points) >= 2:
            from PyQt6.QtGui import QPainterPath
            from PyQt6.QtWidgets import QGraphicsPathItem
            for i in range(1, len(self._path_points)):
                p1=self._path_points[i-1]; p2=self._path_points[i]
                # Determine if this segment is a curve (either point has handle)
                p1_curve = p1[2] == 'C' and len(p1) >= 5
                p2_curve = p2[2] == 'C' and len(p2) >= 5
                if p1_curve or p2_curve:
                    pp = QPainterPath()
                    pp.moveTo(mm_to_px(p1[0], self._dpi), mm_to_px(p1[1], self._dpi))
                    # cp1 = p1's outgoing handle (or p1 itself)
                    if p1_curve:
                        cp1x, cp1y = p1[3], p1[4]
                    else:
                        cp1x, cp1y = p1[0], p1[1]
                    # cp2 = mirror of p2's handle around p2 (smooth curve)
                    if p2_curve:
                        cp2x = 2 * p2[0] - p2[3]
                        cp2y = 2 * p2[1] - p2[4]
                    else:
                        cp2x, cp2y = p2[0], p2[1]
                    pp.cubicTo(
                        mm_to_px(cp1x, self._dpi), mm_to_px(cp1y, self._dpi),
                        mm_to_px(cp2x, self._dpi), mm_to_px(cp2y, self._dpi),
                        mm_to_px(p2[0], self._dpi), mm_to_px(p2[1], self._dpi))
                    item = QGraphicsPathItem(pp); item.setPen(pen)
                    self.scene().addItem(item)
                    item.setZValue(9000)
                    self._path_preview_items.append(item)
                else:
                    line=self.scene().addLine(
                        mm_to_px(p1[0],self._dpi), mm_to_px(p1[1],self._dpi),
                        mm_to_px(p2[0],self._dpi), mm_to_px(p2[1],self._dpi), pen)
                    line.setZValue(9000)
                    self._path_preview_items.append(line)

    def _finish_path_drawing(self):
        """Convert collected points into a Shape(path) object.

        Points may be:
        - (x, y, 'L')                         — corner / line-to
        - (x, y, 'C', handle_x, handle_y)     — smooth curve point with outgoing handle
        """
        pts=list(self._path_points or [])
        close = getattr(self, '_path_close', False)
        self._dbg('finishDraw.enter', npts=len(pts), close=close,
                  types=[p[2] for p in pts])
        self._cancel_path_drawing()
        if len(pts) < 2:
            self._dbg('finishDraw.abort', reason='too_few_points', npts=len(pts))
            return
        # v4.1.11: when closing, the user typically clicked on (near) the
        # first point. We don't want to duplicate that anchor — instead the
        # last clicked point IS removed, and a wrap-cmd is appended after
        # the last unique anchor that ends back at M's position. The Z
        # terminator follows. Outcome: anchor 0 is the only "first" point,
        # last anchor is whatever was clicked second-to-last, then a
        # closing curve segment goes back to anchor 0.
        if close and len(pts) >= 3:
            # Check if last point is essentially at first point (within 2mm)
            d_close = ((pts[-1][0] - pts[0][0])**2 +
                        (pts[-1][1] - pts[0][1])**2) ** 0.5
            if d_close < 2.0:
                pts = pts[:-1]   # drop duplicate; wrap-cmd will close
        # Compute bbox over all coords (including handles)
        xs=[]; ys=[]
        for p in pts:
            xs.append(p[0]); ys.append(p[1])
            if p[2] == 'C' and len(p) >= 5:
                xs.append(p[3]); ys.append(p[4])
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w=max(1.0, max_x - min_x); h=max(1.0, max_y - min_y)

        # Build path_data with cubic Beziers where points have handles
        path_data = []
        for i, p in enumerate(pts):
            mx, my = p[0] - min_x, p[1] - min_y
            if i == 0:
                path_data.append(["M", mx, my])
                continue
            prev = pts[i-1]
            cur  = pts[i]
            # Determine if this segment should be a curve
            prev_has_handle = prev[2] == 'C' and len(prev) >= 5
            cur_has_handle  = cur[2]  == 'C' and len(cur)  >= 5
            if prev_has_handle or cur_has_handle:
                # Build cubic Bezier control points
                # cp1 = previous's outgoing handle (or copy of prev point if no handle)
                if prev_has_handle:
                    cp1x = prev[3] - min_x; cp1y = prev[4] - min_y
                else:
                    cp1x = prev[0] - min_x; cp1y = prev[1] - min_y
                # cp2 = mirror of current's outgoing handle around current point
                # (gives smooth incoming tangent matching outgoing)
                if cur_has_handle:
                    cp2x = (2 * cur[0] - cur[3]) - min_x
                    cp2y = (2 * cur[1] - cur[4]) - min_y
                else:
                    cp2x = mx; cp2y = my
                path_data.append(["C", cp1x, cp1y, cp2x, cp2y, mx, my])
            else:
                path_data.append(["L", mx, my])
        if close:
            # v4.1.12.1: emit a wrap-cmd that closes the path back to M.
            # v4.2.10.8 FIX: the wrap-cmd's ENDPOINT must equal M's local
            # position so _wrap_cmd_index() recognizes it and hides it from the
            # anchor list. Previously it was hardcoded (0.0, 0.0); whenever M
            # was not at the bbox origin (almost always) the wrap was mistaken
            # for a real extra anchor (phantom point) and the closure did not
            # connect as a curve. Also emit when EITHER end is curved (was: both),
            # falling back to the anchor position for a corner end.
            last_has_handle = (pts and pts[-1][2] == 'C' and len(pts[-1]) >= 5)
            first_has_handle = (pts and pts[0][2] == 'C' and len(pts[0]) >= 5)
            m_x = pts[0][0] - min_x; m_y = pts[0][1] - min_y
            if last_has_handle or first_has_handle:
                last_pt = pts[-1]; first_pt = pts[0]
                # cp1 = last anchor's OUTGOING tangent (its stored handle, used
                # directly like every other segment's cp1); corner -> anchor.
                if last_has_handle:
                    cp1x_w = last_pt[3] - min_x; cp1y_w = last_pt[4] - min_y
                else:
                    cp1x_w = last_pt[0] - min_x; cp1y_w = last_pt[1] - min_y
                # cp2 = first anchor's INCOMING tangent (mirror of its stored
                # outgoing handle); corner -> anchor.
                if first_has_handle:
                    cp2x_w = (2 * first_pt[0] - first_pt[3]) - min_x
                    cp2y_w = (2 * first_pt[1] - first_pt[4]) - min_y
                else:
                    cp2x_w = first_pt[0] - min_x; cp2y_w = first_pt[1] - min_y
                path_data.append(["C", cp1x_w, cp1y_w, cp2x_w, cp2y_w, m_x, m_y])
            path_data.append(["Z"])
        from edof.format.objects import Shape, SHAPE_PATH
        sh=Shape(shape_type=SHAPE_PATH)
        sh.path_data=path_data
        sh.transform.x=min_x; sh.transform.y=min_y
        sh.transform.width=w; sh.transform.height=h
        # v4.1.0: closed path → default fill, open path → outline only
        if close:
            sh.fill.color=(180,200,230,128)
        else:
            sh.fill.color=None
        sh.stroke.color=(50,50,50,255)
        sh.stroke.width=0.5
        # Add to page
        win=self._main_window()
        if win:
            page=win._cp()
            if page:
                page.add_object(sh)
                win._auto_name(sh, "curve")   # v4.1.10
                # v4.1.10.3: re-normalize the bbox using sampled curve points
                # so the rendered curve is never clipped by an undersized
                # transform.width/height (was computed only from anchor+CP
                # corners, which can be narrower than the actual curve)
                self._normalize_path_bbox(sh)
                self.set_sel_id(sh.id)
                self.schedule_render()
                win._push("Add Path")
                self._dbg('finishDraw.created', id=sh.id, ncmds=len(path_data),
                          close=close, bbox=(round(min_x,1), round(min_y,1),
                                             round(w,1), round(h,1)))
            else:
                self._dbg('finishDraw.abort', reason='no_page')
        else:
            self._dbg('finishDraw.abort', reason='no_window')

    def _cancel_path_drawing(self):
        """Exit path-drawing mode and clean up preview."""
        self._dbg('cancelDraw', npts=len(getattr(self,'_path_points',[]) or []))
        self._path_drawing=False
        self._path_points=[]
        self._path_close=False
        for item in getattr(self, '_path_preview_items', []):
            try: self.scene().removeItem(item)
            except Exception: pass
        try:
            self.viewport().setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        except Exception: pass

    # v4.1.15: ── Rectangle draw mode ────────────────────────────────────────
    def start_rect_draw(self, kind, callback):
        """Enter rectangle-draw mode. The user drags a rectangle on the
        canvas; on release, `callback(x_mm, y_mm, w_mm, h_mm)` is invoked.
        Drags smaller than 5mm × 5mm are treated as a cancel."""
        # Exit any other drawing mode first
        if self._path_drawing: self._cancel_path_drawing()
        self._rect_draw_kind = kind
        self._rect_draw_callback = callback
        self._rect_draw_start = None
        try:
            self.viewport().setCursor(tcur('crosshair', Qt.CursorShape.CrossCursor))
        except Exception: pass

    def _cancel_rect_draw(self):
        """Exit rectangle-draw mode and clean up preview."""
        if self._rect_draw_preview is not None:
            try: self.scene().removeItem(self._rect_draw_preview)
            except Exception: pass
        self._rect_draw_kind = None
        self._rect_draw_start = None
        self._rect_draw_preview = None
        self._rect_draw_callback = None
        try:
            self.viewport().setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        except Exception: pass

    # v4.1.0: Path point edit mode — drag handles to reshape an existing path
    def _enter_path_edit_mode(self, obj):
        """Show drag handles for each point of a Shape with shape_type='path'."""
        from edof.format.objects import SHAPE_PATH
        self._dbg('enterEdit', id=getattr(obj,'id',None), stype=getattr(obj,'shape_type',None), ncmds=len(getattr(obj,'path_data',[]) or []))
        if obj.shape_type != SHAPE_PATH or not obj.path_data:
            self._dbg('enterEdit.abort', reason='not_a_path_or_empty')
            return
        self._exit_path_edit_mode()
        self._path_edit_obj_id = obj.id
        self._path_edit_handles = []
        self._refresh_path_edit_handles()

    def _refresh_path_edit_handles(self):
        # v4.1.5: cleanly separate draggable handles from decoration lines.
        # Previously, decoration dashed lines were also added to
        # _path_edit_handles, so clicking near a line set _path_drag_handle
        # to a line item with no setData(0/1) → next mouseMove crashed
        # with `obj.path_data[None]` TypeError.
        # Remove old handles and decoration lines
        for h in getattr(self, '_path_edit_handles', []):
            try: self.scene().removeItem(h)
            except Exception: pass
        for h in getattr(self, '_path_edit_decorations', []):
            try: self.scene().removeItem(h)
            except Exception: pass
        self._path_edit_handles = []
        self._path_edit_decorations = []
        oid = getattr(self, '_path_edit_obj_id', None)
        if not oid: return
        page = self._cur_page()
        if not page: return
        obj = page.get_object(oid)
        if not obj or not obj.path_data: return
        self._dbg('refreshHandles', id=oid, ncmds=len(obj.path_data),
                  selected=sorted(getattr(self, '_path_selected_anchors', set()) or set()),
                  rot=round(obj.transform.rotation or 0.0, 1))
        # v4.1.3: render endpoint handles + bezier control handles + control lines
        ox = obj.transform.x; oy = obj.transform.y
        # v4.1.10.2: handles must rotate along with the rendered path so they
        # sit on the curve regardless of object rotation. Compute rotation
        # center (bbox center) and apply rotate_point() per handle.
        rot_deg = obj.transform.rotation or 0.0
        rot_active = abs(rot_deg) > 0.01
        cx_mm = obj.transform.x + obj.transform.width / 2.0
        cy_mm = obj.transform.y + obj.transform.height / 2.0
        def _to_canvas_mm(local_x_mm, local_y_mm):
            """Convert object-local mm coord to canvas mm coord (applies rotation)."""
            wx = ox + local_x_mm; wy = oy + local_y_mm
            if rot_active:
                wx, wy = rotate_point(wx, wy, cx_mm, cy_mm, rot_deg)
            return wx, wy

        # v4.1.11: ensure path_point_types is initialized (helper does it)
        ptypes = self._ensure_ptypes_initialized(obj)

        # v4.1.11: iterate ANCHORS, not cmds. Each anchor draws:
        #   - its anchor handle (square/diamond/circle/triangle per type)
        #   - tangent_in handle (if exists AND anchor type shows CPs)
        #   - tangent_out handle (if exists AND anchor type shows CPs)
        #   - decoration dashed lines from anchor to each visible tangent
        VISIBLE_TYPES = ("smooth", "asymmetric")
        n_anchors = self._anchor_count(obj)
        line_pen = QPen(QColor(120, 180, 255, 200), 1, Qt.PenStyle.DashLine)

        # First pass: decoration lines (tangents → anchor)
        for ai in range(n_anchors):
            ap = self._anchor_pos(obj, ai)
            if ap is None: continue
            atype = ptypes[self._anchor_cmd_index(obj, ai)] if self._anchor_cmd_index(obj, ai) < len(ptypes) else "smooth"
            if atype not in VISIBLE_TYPES: continue
            ax_l, ay_l = ap
            aw = _to_canvas_mm(ax_l, ay_l)
            ax_px = (mm_to_px(aw[0], self._dpi), mm_to_px(aw[1], self._dpi))
            tin = self._anchor_tangent_in(obj, ai)
            if tin is not None:
                tw = _to_canvas_mm(tin[0], tin[1])
                tpx = (mm_to_px(tw[0], self._dpi), mm_to_px(tw[1], self._dpi))
                l = self.scene().addLine(ax_px[0], ax_px[1], tpx[0], tpx[1], line_pen)
                l.setZValue(9999)
                self._path_edit_decorations.append(l)
            tout = self._anchor_tangent_out(obj, ai)
            if tout is not None:
                tw = _to_canvas_mm(tout[0], tout[1])
                tpx = (mm_to_px(tw[0], self._dpi), mm_to_px(tw[1], self._dpi))
                l = self.scene().addLine(ax_px[0], ax_px[1], tpx[0], tpx[1], line_pen)
                l.setZValue(9999)
                self._path_edit_decorations.append(l)

        # v4.1.10: persistent anchor selection (set of cmd indices)
        selected = getattr(self, '_path_selected_anchors', set()) or set()

        # Handle styles
        endpoint_pen_unsel   = QPen(QColor(255, 200, 80, 255), 2)
        endpoint_brush_unsel = QBrush(QColor(255, 255, 255, 255))
        endpoint_pen_sel     = QPen(QColor(0, 200, 255, 255), 2)
        endpoint_brush_sel   = QBrush(QColor(120, 230, 255, 255))
        cp_pen   = QPen(QColor(80, 150, 255, 255), 2)
        cp_brush = QBrush(QColor(180, 220, 255, 255))
        # v4.2.6.0: keep handle outlines crisp (constant 1-2 px) at any zoom,
        # and size the handle shapes in SCREEN pixels by dividing by the zoom
        # so they neither grow nor pixelate when zooming in.
        for _p in (endpoint_pen_unsel, endpoint_pen_sel, cp_pen, line_pen):
            _p.setCosmetic(True)
        _z = max(0.05, float(getattr(self, '_zoom', 1.0) or 1.0))

        # Second pass: anchor handles + tangent handles
        handles_def = []
        for ai in range(n_anchors):
            ap = self._anchor_pos(obj, ai)
            if ap is None: continue
            ci = self._anchor_cmd_index(obj, ai)
            cmd = obj.path_data[ci]
            atype = ptypes[ci] if ci < len(ptypes) else "smooth"
            # Anchor endpoint
            if cmd[0] == 'M' or cmd[0] == 'L':
                handles_def.append((ci, 1, 'endpoint', ap[0], ap[1]))
            elif cmd[0] == 'C':
                handles_def.append((ci, 5, 'endpoint', ap[0], ap[1]))
            elif cmd[0] == 'Q':
                handles_def.append((ci, 3, 'endpoint', ap[0], ap[1]))
            # Tangent handles only if this anchor's type allows
            if atype in VISIBLE_TYPES:
                tin_s = self._tangent_in_storage(obj, ai)
                if tin_s is not None:
                    tcmd, ix, iy = tin_s
                    tcmd_index = obj.path_data.index(tcmd)
                    handles_def.append((tcmd_index, ix, 'cp', tcmd[ix], tcmd[iy]))
                tout_s = self._tangent_out_storage(obj, ai)
                if tout_s is not None:
                    tcmd, ix, iy = tout_s
                    tcmd_index = obj.path_data.index(tcmd)
                    handles_def.append((tcmd_index, ix, 'cp', tcmd[ix], tcmd[iy]))

        for (ci, pi, kind, x_mm, y_mm) in handles_def:
            # v4.1.10.2: use _to_canvas_mm so handles rotate with the object
            wx, wy = _to_canvas_mm(x_mm, y_mm)
            x_px = mm_to_px(wx, self._dpi)
            y_px = mm_to_px(wy, self._dpi)
            if kind == 'endpoint':
                is_sel = ci in selected
                pen = endpoint_pen_sel if is_sel else endpoint_pen_unsel
                brush = endpoint_brush_sel if is_sel else endpoint_brush_unsel
                # v4.1.10: shape varies by point type
                ptype = ptypes[ci] if ci < len(ptypes) else "corner"
                r = 6.0 / _z
                if ptype == "corner":
                    # Square
                    handle = self.scene().addRect(
                        x_px - r, y_px - r, 2*r, 2*r, pen, brush)
                elif ptype == "smooth":
                    # Diamond (square rotated 45°) — use polygon
                    poly = QPolygonF([
                        QPointF(x_px, y_px - r),
                        QPointF(x_px + r, y_px),
                        QPointF(x_px, y_px + r),
                        QPointF(x_px - r, y_px),
                    ])
                    handle = self.scene().addPolygon(poly, pen, brush)
                elif ptype == "asymmetric":
                    # Circle
                    handle = self.scene().addEllipse(
                        x_px - r, y_px - r, 2*r, 2*r, pen, brush)
                else:  # "auto"
                    # Triangle (downward)
                    poly = QPolygonF([
                        QPointF(x_px - r, y_px - r),
                        QPointF(x_px + r, y_px - r),
                        QPointF(x_px, y_px + r),
                    ])
                    handle = self.scene().addPolygon(poly, pen, brush)
            else:
                r = 5.0 / _z
                handle = self.scene().addEllipse(
                    x_px - r, y_px - r, 2*r, 2*r,
                    cp_pen, cp_brush)
            handle.setZValue(10000)
            handle.setData(0, ci)
            handle.setData(1, pi)
            handle.setData(2, kind)
            self._path_edit_handles.append(handle)

    def _translate_anchor(self, obj, ai, dx, dy):
        """v4.2.6.0: move an anchor's endpoint AND both its tangent handles by
        (dx, dy) in object-local mm, so a group drag keeps the curve shape."""
        ci = self._anchor_cmd_index(obj, ai)
        if ci is None or ci >= len(obj.path_data):
            return
        cmd = obj.path_data[ci]
        if not cmd:
            return
        op = cmd[0]
        if op in ('M', 'L') and len(cmd) >= 3:
            cmd[1] += dx; cmd[2] += dy
        elif op == 'C' and len(cmd) >= 7:
            cmd[5] += dx; cmd[6] += dy
        elif op == 'Q' and len(cmd) >= 5:
            cmd[3] += dx; cmd[4] += dy
        for storage in (self._tangent_in_storage(obj, ai),
                        self._tangent_out_storage(obj, ai)):
            if storage:
                t, ix, iy = storage
                if ix < len(t) and iy < len(t):
                    t[ix] += dx; t[iy] += dy

    # ── v4.1.11: anchor-centric helpers ─────────────────────────────────────
    #
    # path_data is SVG-style: ['M', x, y], ['L', x, y], ['C', cp1x, cp1y,
    # cp2x, cp2y, x, y], optionally terminated by ['Z']. An ANCHOR in the
    # editor is one user-manipulable point. For OPEN paths, anchor count
    # equals the number of M/L/C/Q cmds. For CLOSED paths (path_data ends
    # with ['Z']) the LAST drawn cmd has endpoint == M.endpoint — it serves
    # as the wrap-around back to M. We hide that duplicate from the user:
    # closed-path anchor count = (cmds count) - 1.
    #
    # Tangent ownership per anchor ai:
    #   tangent_out(ai) = next cmd's cp1  (if C)
    #   tangent_in(ai)  = this cmd's cp2  (if C); for ai==0 in closed paths
    #                      it's the wrap cmd's cp2
    # These are the actual editable handles; the path_data layout is just
    # the on-disk encoding.

    def _is_closed_path(self, obj) -> bool:
        return bool(obj and obj.path_data and obj.path_data[-1]
                    and obj.path_data[-1][0] == 'Z')

    def _drawn_cmds(self, obj):
        """Return only drawn cmds (M/L/C/Q), excluding Z."""
        if not obj or not obj.path_data: return []
        return [c for c in obj.path_data if c and c[0] != 'Z']

    def _anchor_count(self, obj) -> int:
        """Number of user-visible anchors. Closed paths with an explicit
        wrap-cmd (endpoint == M) hide that wrap from the user; old-format
        closed paths that just have a `Z` after the last anchor don't have
        a wrap-cmd, so all drawn cmds are real anchors."""
        n = len(self._drawn_cmds(obj))
        if self._is_closed_path(obj) and self._wrap_cmd_index(obj) is not None:
            return n - 1
        return n

    def _anchor_cmd_index(self, obj, ai: int) -> int:
        """Convert anchor index → path_data index. The 'wrap' cmd in a
        closed path is at index (anchor_count) which is its own cmd, not
        an anchor."""
        return ai   # M/L/C are at positions 0..N-1 in path_data

    def _wrap_cmd_index(self, obj):
        """For closed paths, return the index of the wrap-cmd (the duplicate
        whose endpoint equals M and which carries tangent_in(0) as its cp2).
        Returns None for open paths AND for closed paths whose last drawn
        cmd is NOT a wrap-duplicate (older documents that closed via a
        straight Z without an explicit wrap-cmd)."""
        if not self._is_closed_path(obj): return None
        wci = len(obj.path_data) - 2
        if wci < 1: return None
        wcmd = obj.path_data[wci]
        if not wcmd: return None
        m = obj.path_data[0]
        if not m or m[0] != 'M': return None
        op = wcmd[0]
        if op == 'L': end = (wcmd[1], wcmd[2])
        elif op == 'C': end = (wcmd[5], wcmd[6])
        elif op == 'Q': end = (wcmd[3], wcmd[4])
        else: return None
        # Wrap-cmd's endpoint must coincide with M (within 0.1mm)
        if abs(end[0] - m[1]) > 0.1 or abs(end[1] - m[2]) > 0.1:
            return None
        return wci

    def _anchor_pos(self, obj, ai: int):
        """Return (x_mm, y_mm) of anchor ai (in local coords)."""
        ci = self._anchor_cmd_index(obj, ai)
        if ci < 0 or ci >= len(obj.path_data): return None
        cmd = obj.path_data[ci]
        if not cmd: return None
        op = cmd[0]
        if op == 'M' or op == 'L': return (cmd[1], cmd[2])
        if op == 'C': return (cmd[5], cmd[6])
        if op == 'Q': return (cmd[3], cmd[4])
        return None

    def _anchor_type(self, obj, ai: int) -> str:
        """Get anchor type. Defaults to 'smooth' for C cmds, 'corner' for L."""
        ci = self._anchor_cmd_index(obj, ai)
        ptypes = getattr(obj, 'path_point_types', []) or []
        if ci < len(ptypes):
            return ptypes[ci]
        if ci < len(obj.path_data):
            cmd = obj.path_data[ci]
            if cmd and cmd[0] in ('C', 'Q'): return 'smooth'
        return 'corner'

    def _ensure_ptypes_initialized(self, obj):
        """Make sure path_point_types is parallel to path_data."""
        n = len(obj.path_data)
        ptypes = getattr(obj, 'path_point_types', []) or []
        if len(ptypes) == n: return ptypes
        new_pt = []
        for i, cmd in enumerate(obj.path_data):
            if i < len(ptypes):
                new_pt.append(ptypes[i]); continue
            if not cmd: new_pt.append('corner'); continue
            if cmd[0] in ('C', 'Q'): new_pt.append('smooth')
            else: new_pt.append('corner')
        obj.path_point_types = new_pt
        return new_pt

    def _tangent_in_storage(self, obj, ai: int):
        """Return (cmd, idx_x, idx_y) where the cp coords for tangent_in(ai)
        are stored, or None if this anchor has no incoming tangent (e.g.
        first anchor of an open path)."""
        if ai == 0:
            if self._is_closed_path(obj):
                wci = self._wrap_cmd_index(obj)
                if wci is not None and obj.path_data[wci][0] == 'C':
                    return (obj.path_data[wci], 3, 4)
            return None
        ci = self._anchor_cmd_index(obj, ai)
        if 0 <= ci < len(obj.path_data):
            cmd = obj.path_data[ci]
            if cmd and cmd[0] == 'C':
                return (cmd, 3, 4)
        return None

    def _tangent_out_storage(self, obj, ai: int):
        """Return (cmd, idx_x, idx_y) for tangent_out(ai), or None."""
        # tangent_out(ai) is in cmd at index ai+1. For closed path the
        # wrap-cmd is at index N-1 (= last drawn cmd) — anchor 0 wraps to
        # itself, so anchor (count-1)'s outgoing tangent is at wrap_cmd.cp1
        n_drawn = len(self._drawn_cmds(obj))
        if self._is_closed_path(obj):
            # closed: anchor (count-1) is last user-visible anchor, its
            # outgoing cmd is wrap_cmd at index (count). That wrap cmd
            # comes after the last user-anchor in path_data.
            if ai == self._anchor_count(obj) - 1:
                # Outgoing tangent = wrap cmd's cp1
                wci = self._wrap_cmd_index(obj)
                if wci is not None and obj.path_data[wci][0] == 'C':
                    return (obj.path_data[wci], 1, 2)
                return None
        # For all other anchors, tangent_out is in path_data[ai+1] (cp1)
        next_ci = ai + 1
        if 0 <= next_ci < len(obj.path_data):
            cmd = obj.path_data[next_ci]
            if cmd and cmd[0] == 'C':
                return (cmd, 1, 2)
        return None

    def _anchor_tangent_in(self, obj, ai):
        s = self._tangent_in_storage(obj, ai)
        if s is None: return None
        cmd, ix, iy = s
        return (cmd[ix], cmd[iy])

    def _anchor_tangent_out(self, obj, ai):
        s = self._tangent_out_storage(obj, ai)
        if s is None: return None
        cmd, ix, iy = s
        return (cmd[ix], cmd[iy])

    def _set_tangent_in(self, obj, ai, x, y):
        s = self._tangent_in_storage(obj, ai)
        if s is None: return
        cmd, ix, iy = s
        cmd[ix] = x; cmd[iy] = y

    def _set_tangent_out(self, obj, ai, x, y):
        s = self._tangent_out_storage(obj, ai)
        if s is None: return
        cmd, ix, iy = s
        cmd[ix] = x; cmd[iy] = y

    def _neighbor_anchor_pos(self, obj, ai, direction):
        """Get neighbor anchor pos in given direction (-1=prev, +1=next)."""
        n = self._anchor_count(obj)
        if n == 0: return None
        if self._is_closed_path(obj):
            nai = (ai + direction) % n
        else:
            nai = ai + direction
            if nai < 0 or nai >= n: return None
        return self._anchor_pos(obj, nai)

    def _normalize_path_bbox(self, obj):
        """v4.1.9.1/4.1.10.2: Recompute the object's transform to a tight
        bounding box that follows the *evaluated* path (sampled bezier
        curve), not the anchor-and-tangent coordinates.

        For straight L segments the endpoints are exact extremes. For C/Q
        segments we sample along the bezier so the bbox actually hugs the
        drawn curve. Net visual effect: the path stays at the same place,
        the bbox just resizes to fit.
        """
        if not obj or not obj.path_data:
            return
        # Sample resolution for bezier extremes (32 = sub-pixel accuracy at
        # any reasonable zoom; not visible noise)
        SAMPLES = 32

        xs, ys = [], []
        prev_x, prev_y = 0.0, 0.0
        for cmd in obj.path_data:
            if not cmd: continue
            op = cmd[0]
            if op == "M":
                xs.append(cmd[1]); ys.append(cmd[2])
                prev_x, prev_y = cmd[1], cmd[2]
            elif op == "L":
                xs.append(cmd[1]); ys.append(cmd[2])
                prev_x, prev_y = cmd[1], cmd[2]
            elif op == "C":
                cx1, cy1, cx2, cy2, ex, ey = cmd[1:7]
                # Sample the curve to find actual extremes
                for s in range(SAMPLES + 1):
                    t = s / SAMPLES
                    u = 1 - t
                    bx = u**3*prev_x + 3*u*u*t*cx1 + 3*u*t*t*cx2 + t**3*ex
                    by = u**3*prev_y + 3*u*u*t*cy1 + 3*u*t*t*cy2 + t**3*ey
                    xs.append(bx); ys.append(by)
                prev_x, prev_y = ex, ey
            elif op == "Q":
                cx, cy, ex, ey = cmd[1:5]
                for s in range(SAMPLES + 1):
                    t = s / SAMPLES
                    u = 1 - t
                    bx = u*u*prev_x + 2*u*t*cx + t*t*ex
                    by = u*u*prev_y + 2*u*t*cy + t*t*ey
                    xs.append(bx); ys.append(by)
                prev_x, prev_y = ex, ey
            # Z doesn't move the pen
        if not xs or not ys:
            return
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        # If the points don't start at (0, 0), shift them so they do, and
        # compensate by moving transform.x/y accordingly.
        if abs(min_x) > 0.01 or abs(min_y) > 0.01:
            for cmd in obj.path_data:
                if not cmd: continue
                op = cmd[0]
                if op == "M" or op == "L":
                    cmd[1] -= min_x; cmd[2] -= min_y
                elif op == "C":
                    cmd[1] -= min_x; cmd[2] -= min_y
                    cmd[3] -= min_x; cmd[4] -= min_y
                    cmd[5] -= min_x; cmd[6] -= min_y
                elif op == "Q":
                    cmd[1] -= min_x; cmd[2] -= min_y
                    cmd[3] -= min_x; cmd[4] -= min_y
            obj.transform.x += min_x
            obj.transform.y += min_y
        new_w = max(0.1, max_x - min_x)
        new_h = max(0.1, max_y - min_y)
        obj.transform.width = new_w
        obj.transform.height = new_h

    def _prev_path_point(self, path_data, ci):
        """Return the (x,y) of the path endpoint immediately before cmd at index ci."""
        if ci == 0: return (0.0, 0.0)
        for j in range(ci - 1, -1, -1):
            cmd = path_data[j]
            if not cmd: continue
            op = cmd[0]
            if op == "M" or op == "L":
                return (cmd[1], cmd[2])
            if op == "C":
                return (cmd[5], cmd[6])
            if op == "Q":
                return (cmd[3], cmd[4])
        return (0.0, 0.0)

    def _next_path_point(self, path_data, ci):
        """v4.1.12: Return the (x,y) of the path endpoint of the next drawn
        cmd (after ci). Skips Z. Falls back to this cmd's own endpoint if no
        next cmd exists."""
        for j in range(ci + 1, len(path_data)):
            cmd = path_data[j]
            if not cmd: continue
            op = cmd[0]
            if op == "Z": continue
            if op == "M" or op == "L":
                return (cmd[1], cmd[2])
            if op == "C":
                return (cmd[5], cmd[6])
            if op == "Q":
                return (cmd[3], cmd[4])
        # Fall back to this cmd's own endpoint
        cmd = path_data[ci] if 0 <= ci < len(path_data) else None
        if cmd:
            op = cmd[0]
            if op == "M" or op == "L": return (cmd[1], cmd[2])
            if op == "C": return (cmd[5], cmd[6])
            if op == "Q": return (cmd[3], cmd[4])
        return (0.0, 0.0)

    def _exit_path_edit_mode(self):
        self._dbg('exitEdit', id=getattr(self,'_path_edit_obj_id',None))
        for h in getattr(self, '_path_edit_handles', []):
            try: self.scene().removeItem(h)
            except Exception: pass
        for h in getattr(self, '_path_edit_decorations', []):
            try: self.scene().removeItem(h)
            except Exception: pass
        self._path_edit_handles = []
        self._path_edit_decorations = []
        self._path_edit_obj_id = None
        self._path_drag_handle = None
        self._path_preview_items=[]
        try: self.unsetCursor()
        except Exception: pass

    def _main_window(self):
        """Find the parent EdofEditor window (for _push, etc.)."""
        w=self.parent()
        while w is not None and not isinstance(w, QMainWindow):
            w=w.parent()
        return w

    def _show_preview(self,obj):
        from edof.format.objects import Shape,SHAPE_LINE
        if isinstance(obj,Shape) and obj.shape_type==SHAPE_LINE: return
        t=obj.transform
        x=mm_to_px(t.x,self._dpi); y=mm_to_px(t.y,self._dpi)
        w=mm_to_px(t.width,self._dpi); h=mm_to_px(t.height,self._dpi)
        pen=QPen(QColor(255,255,255,100),1,Qt.PenStyle.DotLine)
        brs=QBrush(QColor(255,255,255,15))
        if self._preview_item is None:
            self._preview_item=self.scene().addRect(QRectF(0,0,w,h),pen,brs)
            self._preview_item.setZValue(8000)
        else: self._preview_item.setRect(QRectF(0,0,w,h))
        self._preview_item.setPos(x,y)
        self._preview_item.setTransformOriginPoint(w/2,h/2)
        self._preview_item.setRotation(t.rotation)

    # ── Cursor ────────────────────────────────────────────────────────────────

    def _resize_cursor(self, handle, rot):
        """Pick a resize cursor that matches the handle's on-screen orientation,
        accounting for the object's rotation."""
        if handle == 'ROT':
            return tcur('rotate', Qt.CursorShape.CrossCursor)
        base = {'ML':0,'MR':0,'TC':90,'BC':90,'TL':135,'BR':135,'TR':45,'BL':45}.get(handle)
        if base is None:
            return tcur('move', Qt.CursorShape.SizeAllCursor)
        ang = (base + (rot or 0.0)) % 180.0
        buckets = ((0,'resize_ew',Qt.CursorShape.SizeHorCursor),
                   (45,'resize_nesw',Qt.CursorShape.SizeBDiagCursor),
                   (90,'resize_ns',Qt.CursorShape.SizeVerCursor),
                   (135,'resize_nwse',Qt.CursorShape.SizeFDiagCursor))
        best = min(buckets, key=lambda b: min(abs(ang-b[0]), 180-abs(ang-b[0])))
        return tcur(best[1], best[2])

    def _update_cursor(self,sp):
        from PyQt6.QtWidgets import QApplication
        # v4.2.7.2: rectangle drawing
        if self._rect_draw_kind is not None:
            self.viewport().setCursor(tcur('crosshair', Qt.CursorShape.CrossCursor)); return
        # pen drawing — near the first point (with >=3 pts) shows the close cursor
        if getattr(self, '_path_drawing', False):
            name = 'pen'
            try:
                if len(self._path_points) >= 3:
                    mx, my = self._to_mm(sp)
                    fx, fy = self._path_points[0][:2]
                    if abs(mx-fx) < 3.0 and abs(my-fy) < 3.0:
                        name = 'pen_close'
            except Exception:
                pass
            self.viewport().setCursor(tcur(name, Qt.CursorShape.CrossCursor)); return
        if getattr(self, '_hand_tool', False):
            self.viewport().setCursor(tcur('hand', Qt.CursorShape.OpenHandCursor)); return
        # path point editing — tangent / anchor / add / remove
        if getattr(self, '_path_edit_obj_id', None):
            mods = QApplication.keyboardModifiers()
            hit = None
            for h in reversed(self._path_edit_handles):
                if h.data(0) is None: continue
                if h.sceneBoundingRect().adjusted(-2,-2,2,2).contains(sp):
                    hit = h; break
            if hit is not None:
                if hit.data(2) == 'endpoint':
                    if mods & Qt.KeyboardModifier.AltModifier:
                        self.viewport().setCursor(tcur('remove_point', Qt.CursorShape.PointingHandCursor))
                    elif mods & Qt.KeyboardModifier.ControlModifier:
                        self.viewport().setCursor(tcur('tangent', Qt.CursorShape.CrossCursor))
                    else:
                        self.viewport().setCursor(tcur('move', Qt.CursorShape.SizeAllCursor))
                else:
                    self.viewport().setCursor(tcur('tangent', Qt.CursorShape.CrossCursor))
            else:
                self.viewport().setCursor(tcur('add_point', Qt.CursorShape.CrossCursor))
            return
        handle=self._overlay.hit_handle(sp)
        if handle:
            obj=self._sel_obj()
            rot=getattr(obj.transform,'rotation',0.0) if obj else 0.0
            self.viewport().setCursor(self._resize_cursor(handle, rot))
        elif self._hit_obj(sp):
            obj=self._sel_obj()
            if obj and obj.locked:
                self.viewport().setCursor(tcur('not_allowed', Qt.CursorShape.ForbiddenCursor))
            else:
                self.viewport().setCursor(tcur('move', Qt.CursorShape.SizeAllCursor))
        else: self.viewport().setCursor(tcur('move', Qt.CursorShape.ArrowCursor))

    # ── Hit test ──────────────────────────────────────────────────────────────

    def _hit_obj(self,sp,allow_hf=False):
        if not self._doc or not self._doc.pages: return None
        pg=self._doc.pages[self._page_idx]; mx,my=self._to_mm(sp)
        doc_mode = getattr(self._doc, 'mode', '') == 'document'
        try:
            from edof.format.document_boxes import (
                DocumentHeaderBox, DocumentFooterBox)
        except Exception:
            DocumentHeaderBox = DocumentFooterBox = ()
        for obj in reversed(pg.sorted_objects()):
            # v4.1.23.43: the document body is edited inline and must NEVER be
            # picked / dragged as an object via a canvas click. It spans the
            # whole page, so without this it would swallow every click (you
            # could drag the page body and could not select inserted boxes
            # sitting over it). It still appears in the Objects list so its
            # z-order can be changed there.
            if doc_mode and self._is_document_body(obj):
                continue
            # v4.2.11.42: header/footer boxes are NOT free-form objects. Their
            # geometry is driven by page setup (margins / band height), so they
            # must never show selection handles or be dragged/resized. They are
            # editable by DOUBLE-CLICK only, which passes allow_hf=True.
            if (not allow_hf) and isinstance(obj, (DocumentHeaderBox, DocumentFooterBox)):
                continue
            t=obj.transform; cx,cy=t.x+t.width/2,t.y+t.height/2
            lx,ly=rotate_point(mx,my,cx,cy,-t.rotation)
            if t.x<=lx<=t.x+t.width and t.y<=ly<=t.y+t.height: return obj.id
        return None

    # ── Context menu ──────────────────────────────────────────────────────────

    def _ctx_menu(self,vpos):
        sp=self.mapToScene(vpos)
        # v4.1.10.1: if in path edit mode and right-clicked on an anchor,
        # show point-type menu instead of object context menu
        if getattr(self, '_path_edit_obj_id', None):
            target = None
            for h in self._path_edit_handles:
                if h.data(0) is None: continue
                rect = h.sceneBoundingRect().adjusted(-3, -3, 3, 3)
                if rect.contains(sp):
                    target = h; break
            if target is not None and target.data(2) == 'endpoint':
                ci = target.data(0)
                page = self._cur_page()
                obj = page.get_object(self._path_edit_obj_id) if page else None
                if obj and obj.path_data:
                    # Ensure path_point_types is initialized
                    if (not hasattr(obj, 'path_point_types')
                        or len(obj.path_point_types) != len(obj.path_data)):
                        ptypes = []
                        for c in obj.path_data:
                            if not c: ptypes.append("corner"); continue
                            ptypes.append("smooth" if c[0] in ("C", "Q") else "corner")
                        obj.path_point_types = ptypes
                    current_type = obj.path_point_types[ci] if ci < len(obj.path_point_types) else "corner"
                    menu = QMenu(self)
                    act_corner = menu.addAction("Corner (no tangents)")
                    act_smooth = menu.addAction("Smooth (symmetric tangents)")
                    act_asym   = menu.addAction("Asymmetric (independent tangents)")
                    act_auto   = menu.addAction("Auto (recomputed from neighbors)")
                    for a, ttype in [(act_corner, "corner"), (act_smooth, "smooth"),
                                       (act_asym, "asymmetric"), (act_auto, "auto")]:
                        a.setCheckable(True)
                        a.setChecked(ttype == current_type)
                    menu.addSeparator()
                    act_connect = menu.addAction("Connect anchors (C)")
                    act_connect.setEnabled(len(self._path_selected_anchors) == 2)
                    act_disconnect = menu.addAction("Disconnect anchor (D)")
                    act_disconnect.setEnabled(len(self._path_selected_anchors) == 1)
                    menu.addSeparator()
                    act_delete = menu.addAction("Delete point")
                    chosen = menu.exec(self.viewport().mapToGlobal(vpos))
                    if   chosen == act_corner: self._set_point_type(obj, ci, "corner")
                    elif chosen == act_smooth: self._set_point_type(obj, ci, "smooth")
                    elif chosen == act_asym:   self._set_point_type(obj, ci, "asymmetric")
                    elif chosen == act_auto:   self._set_point_type(obj, ci, "auto")
                    elif chosen == act_connect:    self._path_connect_selected()
                    elif chosen == act_disconnect: self._path_disconnect_selected()
                    elif chosen == act_delete: self._delete_path_point(obj, ci)
                    self._refresh_path_edit_handles()
                    self.schedule_render(0)
                    self.objectChanged.emit()
                    return

        hit=self._hit_obj(sp)
        if hit and hit!=self._sel_id:
            self._sel_id=hit; self._refresh_overlay()
            self.objectSelected.emit(self._sel_obj())
        menu=QMenu(self); obj=self._sel_obj()
        if obj:
            lock_lbl=t('ctx_unlock') if obj.locked else t('ctx_lock')
            menu.addAction(lock_lbl,self._toggle_lock)
            if isinstance(obj,edof.TextBox):
                menu.addAction(t('ctx_edit_inline'),lambda:self._start_inline(obj))
            vis_lbl=t('ctx_show') if not obj.visible else t('ctx_hide')
            menu.addAction(vis_lbl,self._toggle_visible)
            menu.addSeparator()
            menu.addAction(t('ctx_dup'),self.objectChanged.emit)
            menu.addAction(t('ctx_del'),self._do_delete)
            menu.addSeparator()
            menu.addAction(t('layer_front'),  lambda:self._layer_op('front'))
            menu.addAction(t('layer_up'),     lambda:self._layer_op('up'))
            menu.addAction(t('layer_down'),   lambda:self._layer_op('down'))
            menu.addAction(t('layer_back'),   lambda:self._layer_op('back'))
            menu.addSeparator()
            menu.addAction(t('ctx_flip_h'),lambda:(obj.transform.flip_horizontal(),
                           self.schedule_render(),self.objectChanged.emit()))
            menu.addAction(t('ctx_flip_v'),lambda:(obj.transform.flip_vertical(),
                           self.schedule_render(),self.objectChanged.emit()))
            menu.addSeparator()
            fxm = menu.addMenu("Layer Effects")
            fxm.addAction("Copy Effects", lambda o=obj: _copy_layer_effects(o))
            _pa = fxm.addAction("Paste Effects", lambda o=obj: (
                _paste_layer_effects(o), self.schedule_render(0), self.objectChanged.emit()))
            _pa.setEnabled(_has_fx_clipboard())
            _ca = fxm.addAction("Clear Effects", lambda o=obj: (
                _clear_layer_effects(o), self.schedule_render(0), self.objectChanged.emit()))
            _ca.setEnabled(bool(getattr(obj, 'effects', None)))
        menu.exec(self.viewport().mapToGlobal(vpos))

    def _toggle_lock(self):
        obj=self._sel_obj()
        if obj: obj.locked=not obj.locked; self.objectChanged.emit(); self.schedule_render()

    def _toggle_visible(self):
        obj=self._sel_obj()
        if obj: obj.visible=not obj.visible; self.objectChanged.emit(); self._start_render()

    def _do_delete(self):
        pg=self._cur_page()
        if not pg: return
        # v4.0.1: delete all multi-selected objects too
        ids_to_delete=[]
        if self._sel_id: ids_to_delete.append(self._sel_id)
        ids_to_delete.extend(self._multi_sel_ids)
        if not ids_to_delete: return
        for oid in ids_to_delete:
            pg.remove_object(oid)
        self._sel_id=None; self._multi_sel_ids.clear()
        self._overlay.update_for(None,self._dpi)
        self.objectSelected.emit(None); self.objectChanged.emit(); self.schedule_render()

    def _layer_op(self, op: str):
        """Layer ordering: front/back/up/down with proper swap logic."""
        obj=self._sel_obj(); pg=self._cur_page()
        if not obj or not pg: return
        sorted_objs=pg.sorted_objects()  # sorted by .layer asc
        layers=[o.layer for o in sorted_objs]
        idx=next((i for i,o in enumerate(sorted_objs) if o.id==obj.id),None)
        if idx is None: return

        if op=='front':
            mx=max(layers); obj.layer=mx+1
        elif op=='back':
            for o in pg.objects:
                if o.id!=obj.id: o.layer+=1
            obj.layer=0
        elif op=='up' and idx<len(sorted_objs)-1:
            above=sorted_objs[idx+1]
            obj.layer,above.layer=above.layer,obj.layer
        elif op=='down' and idx>0:
            below=sorted_objs[idx-1]
            obj.layer,below.layer=below.layer,obj.layer

        # v4.1.10: also notify object change so the right-panel Order label
        # and the Objects panel both update right away
        self.schedule_render()
        self.objectChanged.emit()
        # Re-emit selection so PropPanel reloads its layer label
        try:
            self.objectSelected.emit(self._sel_obj())
        except Exception: pass

    # ── Zoom / Fit ────────────────────────────────────────────────────────────

    def _restore_alt_cursor(self):
        if getattr(self, '_alt_zoom_on', False):
            self._alt_zoom_on = False
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.restoreOverrideCursor()
            except Exception: pass

    def keyReleaseEvent(self, event):
        if not event.isAutoRepeat():
            self._dbg('keyRelease', key=_key_name(event.key()),
                      mods=_mods_str(event.modifiers()))
        if event.key() == Qt.Key.Key_Alt:
            self._restore_alt_cursor()
        super().keyReleaseEvent(event)

    def enterEvent(self, event):
        # re-apply the magnifier if Alt is still held when the pointer returns
        try:
            from PyQt6.QtWidgets import QApplication
            if (QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier) \
               and not getattr(self, '_alt_zoom_on', False):
                self._alt_zoom_on = True
                QApplication.setOverrideCursor(_zoom_cursor())
        except Exception: pass
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._restore_alt_cursor()
        super().leaveEvent(event)

    def focusOutEvent(self, event):
        self._restore_alt_cursor()
        super().focusOutEvent(event)

    def _zoom_bounds(self):
        """(min, max) zoom. Max = 10 screen px per document px (== 1000% in the
        status bar), where pixel edges show crisp. Min = half the fit-to-window
        zoom (page fills ~half the viewport)."""
        if not self._doc or not self._doc.pages:
            return (0.05, 8.0)
        base = float(self._dpi or 96)
        try:
            pg = self._doc.pages[self._page_idx]
            docdpi = float(getattr(pg, 'dpi', 0) or getattr(self._doc, 'default_dpi', 0) or 96)
        except Exception:
            docdpi = 96.0
        if docdpi <= 0:
            docdpi = 96.0
        max_z = 10.0 * docdpi / base
        try:
            pg = self._doc.pages[self._page_idx]
            pw = mm_to_px(pg.width, base); ph = mm_to_px(pg.height, base)
            vw = max(50, self.viewport().width()); vh = max(50, self.viewport().height())
            min_z = (min(vw / pw, vh / ph) * 0.95) / 2.0
        except Exception:
            min_z = 0.05
        if min_z <= 0:
            min_z = 0.02
        if min_z >= max_z:
            min_z = max_z * 0.05
        return (min_z, max_z)

    def _set_zoom(self,z):
        old_zoom=self._zoom
        mn, mx = self._zoom_bounds()
        self._zoom=max(mn, min(mx, z))
        self.setTransform(QTransform().scale(self._zoom,self._zoom))
        # v4.2.9.7: once we're upscaling the rendered pixmap (zoom beyond the
        # render-DPI factor cap of 3x), switch to nearest-neighbour so pixel
        # edges look crisp/blocky instead of blurry.
        try:
            mode = (Qt.TransformationMode.FastTransformation if self._zoom > 3.0
                    else Qt.TransformationMode.SmoothTransformation)
            self._page_item.setTransformationMode(mode)
        except Exception: pass
        self._refresh_overlay(); self._reposition_inline()
        # v4.2.6.0: rebuild path-edit handles so their screen size stays
        # constant (they are sized by 1/zoom).
        if getattr(self, '_path_edit_obj_id', None):
            self._refresh_path_edit_handles()
        # v4.1.15.7: inline editor is a QGraphicsProxyWidget in the scene,
        # so the view transform scales it automatically — no manual rescale.
        # v4.1.0: re-render at higher DPI when zoomed in for crisp display
        if abs(self._zoom - old_zoom) > 0.001:
            # Throttle: only re-render on meaningful zoom changes
            if hasattr(self, '_zoom_timer'):
                self._zoom_timer.stop()
            else:
                self._zoom_timer = QTimer()
                self._zoom_timer.setSingleShot(True)
                self._zoom_timer.timeout.connect(self._start_render)
            self._zoom_timer.start(150)
        self.viewport().update()
        try: self.zoomChanged.emit(self._zoom)
        except Exception: pass

    def zoom_fit(self):
        if not self._doc or not self._doc.pages: return
        pg=self._doc.pages[self._page_idx]
        pw=mm_to_px(pg.width,self._dpi); ph=mm_to_px(pg.height,self._dpi)
        # v4.2.11.42: the inline toolbar band is reserved via setViewportMargins,
        # so viewport().width()/height() already exclude it -- Fit uses the
        # usable area and centers the page within it (the page top lands below
        # the ribbon).
        vw=max(100,self.viewport().width())
        vh=max(100,self.viewport().height())
        self._set_zoom(min(vw/pw,vh/ph)*0.95)
        self.centerOn(pw/2, ph/2)

    @property
    def zoom(self): return self._zoom
    @zoom.setter
    def zoom(self,v): self._set_zoom(v)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cur_page(self):
        if not self._doc or not self._doc.pages: return None
        return self._doc.pages[self._page_idx] if self._page_idx<len(self._doc.pages) else None

    def _sel_obj(self):
        pg=self._cur_page()
        return pg.get_object(self._sel_id) if pg and self._sel_id else None

    def _find_obj(self, oid):
        """v4.0.1: helper for multi-select."""
        pg=self._cur_page()
        return pg.get_object(oid) if pg and oid else None

    def selected_objects(self):
        """v4.0.1: return list of all selected objects (primary + multi)."""
        out=[]
        primary=self._sel_obj()
        if primary: out.append(primary)
        for oid in self._multi_sel_ids:
            o=self._find_obj(oid)
            if o: out.append(o)
        return out

    def get_sel_id(self): return self._sel_id
    def set_sel_id(self,oid):
        # v4.1.7: if leaving path edit mode (selected something else, or nothing)
        # exit it cleanly so handles disappear
        if (getattr(self, '_path_edit_obj_id', None) is not None
            and self._path_edit_obj_id != oid):
            self._exit_path_edit_mode()
        self._sel_id=oid; self._refresh_overlay()
        self.objectSelected.emit(self._sel_obj())


# ═══════════════════════════════════════════════════════════════════════════════
#  Object List Panel
# ═══════════════════════════════════════════════════════════════════════════════

# v4.1.10: per-type icons for the Objects panel. Shape gets sub-type
# resolution (rect/ellipse/path/line/polygon/arrow) via _icon_for_obj().
_TYPE_ICONS = {
    'textbox':     'T',
    'imagebox':    '🖼',
    'shape':       '⬜',     # fallback; refined per shape_type below
    'qrcode':      '▢',
    'group':       '⊞',
    'table':       '⊞',
    'subdocument': '📄',
    'base':        '·',
}
_SHAPE_SUBTYPE_ICONS = {
    'rect':    '⬜',
    'ellipse': '⭕',
    'line':    '─',
    'path':    '✎',
    'polygon': '◆',
    'arrow':   '➤',
}

_TYPE_ICON_NAMES = {
    'textbox': 'text', 'imagebox': 'image', 'qrcode': 'qr',
    'group': 'group', 'table': 'table',
}
_SHAPE_ICON_NAMES = {
    'rect': 'rect', 'ellipse': 'ellipse', 'line': 'line', 'path': 'pen',
    'polygon': 'polygon', 'arrow': 'arrow',
}


def _obj_icon_name(obj):
    """UI-icon asset name for an object type (or None to fall back to a glyph)."""
    t = getattr(obj, 'OBJECT_TYPE', 'base')
    if t == 'shape':
        return _SHAPE_ICON_NAMES.get(getattr(obj, 'shape_type', None))
    return _TYPE_ICON_NAMES.get(t)


# --- Layer-effects clipboard (Copy / Paste / Clear layer style) --------------
_FX_CLIPBOARD = None


def _copy_layer_effects(obj):
    """Copy an object's full layer style (effects + blending) to the clipboard."""
    global _FX_CLIPBOARD
    if obj is None:
        return False
    _FX_CLIPBOARD = {
        'effects': [e.to_dict() for e in (getattr(obj, 'effects', None) or [])],
        'blend_mode': getattr(obj, 'blend_mode', 'normal'),
        'opacity': getattr(obj, 'opacity', 1.0),
        'fill_opacity': getattr(obj, 'fill_opacity', 1.0),
    }
    return True


def _paste_layer_effects(obj):
    """Apply the clipboard layer style to an object (replaces its effects)."""
    if obj is None or _FX_CLIPBOARD is None:
        return False
    from edof.format.styles import LayerEffect
    obj.effects = [LayerEffect.from_dict(d) for d in _FX_CLIPBOARD['effects']]
    obj.blend_mode = _FX_CLIPBOARD['blend_mode']
    obj.opacity = _FX_CLIPBOARD['opacity']
    obj.fill_opacity = _FX_CLIPBOARD['fill_opacity']
    return True


def _clear_layer_effects(obj):
    """Remove all layer effects from an object (blending left untouched)."""
    if obj is None:
        return False
    obj.effects = []
    return True


def _has_fx_clipboard():
    return _FX_CLIPBOARD is not None


def _icon_for_obj(obj) -> str:
    """v4.1.10: pick the most informative icon for an object."""
    t = getattr(obj, 'OBJECT_TYPE', 'base')
    if t == 'shape':
        st = getattr(obj, 'shape_type', None)
        return _SHAPE_SUBTYPE_ICONS.get(st, _TYPE_ICONS['shape'])
    return _TYPE_ICONS.get(t, '·')

class ObjectListPanel(QWidget):
    objectSelected=pyqtSignal(str)   # object id

    def __init__(self,canvas,parent=None):
        super().__init__(parent); self._canvas=canvas
        vb=QVBoxLayout(self); vb.setContentsMargins(4,4,4,4); vb.setSpacing(4)
        self._list=QListWidget()
        # v4.0.3: dark-theme friendly styling — no alternating rows (the default
        # zebra was bright and hard to read on dark theme)
        self._list.setAlternatingRowColors(False)
        self._list.setStyleSheet(
            "QListWidget{background:#1c1c2a;color:#e6e6f0;border:1px solid #2a2a3c;}"
            "QListWidget::item{padding:4px;}"
            "QListWidget::item:selected{background:#3050a0;color:white;}"
            "QListWidget::item:hover{background:#2a3050;}"
        )
        # v4.0.3: drag-and-drop to reorder layers
        self._list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        # v4.0.3: F2 / double-click rename, right-click menu
        self._list.setEditTriggers(
            QListWidget.EditTrigger.EditKeyPressed |
            QListWidget.EditTrigger.DoubleClicked
        )
        self._list.itemChanged.connect(self._on_item_renamed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.currentItemChanged.connect(self._on_item_changed)
        # v4.1.17.1: click on the visibility / lock toggles at the right edge
        # of each row to toggle the property. Detected via mousePressEvent.
        self._list.mousePressEvent = self._on_list_mouse_press
        self._suppress_rename_signal=False
        vb.addWidget(self._list)

    def _on_list_mouse_press(self, event):
        # v4.1.19.10: position-based toggle detection removed — visibility
        # and lock now have real QPushButton widgets via setItemWidget which
        # handle clicks directly. This handler just defers to the default
        # selection behaviour.
        QListWidget.mousePressEvent(self._list, event)

    def refresh(self):
        self._list.blockSignals(True)
        self._suppress_rename_signal=True
        self._list.clear()
        pg=self._canvas._cur_page()
        if not pg: self._list.blockSignals(False); self._suppress_rename_signal=False; return
        sel=self._canvas.get_sel_id()
        for obj in reversed(pg.sorted_objects()):
            # v4.1.19.11: full custom row widget — icon + editable name +
            # variable tag + toggle buttons. setItemWidget hides the item's
            # own text rendering, so all visible content has to live in this
            # widget. The list item still carries the object id for selection
            # / context menu / drag-drop reorder.
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, obj.id)
            row = self._make_row_widget(obj)
            # Match Qt's row sizing to the widget so it doesn't get clipped
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            if obj.id==sel: self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._suppress_rename_signal=False

    def _make_row_widget(self, obj):
        """v4.1.19.11: Build the full row widget shown in the Objects panel.
        Contains: icon, editable name (double-click to rename), variable tag
        if present, and clickable visibility + lock toggle buttons docked on
        the right edge."""
        from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QPushButton,
                                       QLabel, QLineEdit, QStackedLayout)
        canvas = self._canvas
        panel = self
        row = QWidget()
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        # v4.1.23.45: transparent row background so the QListWidget item's
        # ":selected" highlight (the blue bar) shows across the WHOLE row,
        # not just a thin outline.
        row.setStyleSheet("background:transparent;")
        # v4.1.19.12: explicit minimum height so the QLineEdit's bottom edge
        # doesn't get clipped. The global QSS sets QLineEdit min-height 24px
        # + padding 3+3px = ~30px needed; we go 32px for safety margin.
        row.setMinimumHeight(32)
        h = QHBoxLayout(row); h.setContentsMargins(6, 4, 4, 4); h.setSpacing(4)

        icon = _icon_for_obj(obj)
        name = obj.name or obj.id[:12] + "…"

        # Icon label — real bundled PNG when available, glyph fallback otherwise
        ico_lbl = QLabel()
        ico_lbl.setStyleSheet("background:transparent;color:#cccccc;font-size:11pt;")
        _icn = uicon(_obj_icon_name(obj)) if _obj_icon_name(obj) else None
        if _icn is not None and not _icn.isNull():
            ico_lbl.setPixmap(_icn.pixmap(16, 16))
        else:
            ico_lbl.setText(icon)
        ico_lbl.setFixedWidth(20)
        # v4.1.23.45: let clicks fall through to the list so the item gets
        # selected (and a drag can start) no matter where on the row you click.
        ico_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        h.addWidget(ico_lbl)

        # Editable name — QLineEdit that looks like a label until focused
        name_edit = QLineEdit(name)
        name_edit.setStyleSheet(
            "QLineEdit{background:transparent;border:none;color:#e6e6f0;"
            "font-size:10pt;padding:0 2px;}"
            "QLineEdit:focus{background:#252535;border:1px solid #0078d4;"
            "border-radius:2px;}"
        )
        name_edit.setReadOnly(True)
        # Strip ability to grab focus on click — only F2 / double-click enables editing
        name_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # v4.1.23.45: when read-only the name field must NOT eat the click —
        # otherwise single clicks on the (wide) name area landed in the line
        # edit instead of selecting the row, which is why selecting felt
        # unreliable. Let clicks fall through to the list; re-enable real
        # mouse handling only while renaming.
        name_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        def _enable_edit():
            name_edit.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            name_edit.setReadOnly(False)
            name_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            name_edit.setFocus()
            name_edit.selectAll()
        def _commit_name():
            new = name_edit.text().strip()
            if new and new != obj.name:
                obj.name = new
                canvas.objectChanged.emit()
            name_edit.setReadOnly(True)
            name_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            name_edit.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        name_edit.editingFinished.connect(_commit_name)
        # Double-click anywhere on the row to enter rename mode
        def _on_mouse_double(ev):
            _enable_edit()
            ev.accept()
        row.mouseDoubleClickEvent = _on_mouse_double
        # Single click selects the item (route through list)
        h.addWidget(name_edit, 1)

        # Variable tag if present
        if obj.variable:
            var_lbl = QLabel(f"[{obj.variable}]")
            var_lbl.setStyleSheet("background:transparent;color:#7070a0;font-size:9pt;")
            var_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            h.addWidget(var_lbl)

        # Toggle buttons
        def _mk_btn(symbol_fn, tooltip_fn, toggle_fn, icon_fn=None):
            from PyQt6.QtCore import QSize
            btn = QPushButton()
            ic = uicon(icon_fn(obj)) if icon_fn else None
            if ic is not None and not ic.isNull():
                btn.setIcon(ic); btn.setIconSize(QSize(15, 15))
            else:
                btn.setText(symbol_fn(obj))
            btn.setFixedSize(22, 22)
            btn.setToolTip(tooltip_fn(obj))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(
                "QPushButton{background:transparent;border:none;"
                "color:#cccccc;font-size:11pt;padding:0;}"
                "QPushButton:hover{background:#3a3a5a;border-radius:3px;}"
            )
            def on_click():
                toggle_fn(obj)
                canvas.objectChanged.emit()
                canvas.schedule_render()
                panel.refresh()
            btn.clicked.connect(on_click)
            return btn

        vis_btn = _mk_btn(
            lambda o: "👁" if o.visible else "🚫",
            lambda o: ("Hide layer" if o.visible else "Show layer"),
            lambda o: setattr(o, 'visible', not o.visible),
            icon_fn=lambda o: 'visible' if o.visible else 'hidden',
        )
        lock_btn = _mk_btn(
            lambda o: "🔒" if o.locked else "🔓",
            lambda o: ("Unlock layer" if o.locked else "Lock layer"),
            lambda o: setattr(o, 'locked', not o.locked),
            icon_fn=lambda o: 'lock' if o.locked else 'unlock',
        )
        h.addWidget(vis_btn)
        h.addWidget(lock_btn)
        return row

    def _on_item_changed(self,item):
        if self._suppress_rename_signal: return
        if item:
            oid=item.data(Qt.ItemDataRole.UserRole)
            if oid: self.objectSelected.emit(oid)

    def _on_item_renamed(self, item):
        """v4.0.3: F2/dblclick rename committed. v4.1.19.10: simplified since
        the item text no longer contains toggle emojis."""
        if self._suppress_rename_signal: return
        oid=item.data(Qt.ItemDataRole.UserRole)
        if not oid: return
        new_text=item.text()
        clean=new_text.strip()
        # Drop leading icon (single character + space)
        if len(clean) >= 2 and clean[1] == ' ':
            clean = clean[2:]
        # Drop trailing [variable] tag
        if "[" in clean and "]" in clean:
            clean = clean[:clean.rfind("[")].strip()
        clean = clean.strip()
        # Don't accept empty
        if not clean.strip():
            self.refresh(); return
        # Update the object
        pg=self._canvas._cur_page()
        if pg:
            obj=pg.get_object(oid)
            if obj:
                obj.name=clean.strip()
                self._canvas.objectChanged.emit()
                self.refresh()

    def _on_rows_moved(self, parent_idx, start, end, dest_parent, dest_row):
        """v4.0.3: drag-and-drop to reorder layers.

        The list is rendered in reverse layer order (top item = front-most layer).
        Dragging an item up should bring it to front; dragging down should send
        to back. We rebuild layer values from the new visual order.
        """
        pg=self._canvas._cur_page()
        if not pg: return
        # Collect new order from the list (top-to-bottom = front-to-back)
        new_order_top_to_bottom=[]
        for i in range(self._list.count()):
            oid=self._list.item(i).data(Qt.ItemDataRole.UserRole)
            obj=pg.get_object(oid)
            if obj: new_order_top_to_bottom.append(obj)
        # Reverse to get back-to-front order, then assign sequential layer values
        for new_layer, obj in enumerate(reversed(new_order_top_to_bottom)):
            obj.layer = new_layer
        self._canvas.objectChanged.emit()
        self._canvas.schedule_render()

    def _on_context_menu(self, pos):
        """v4.0.3: right-click context menu on the object list."""
        item=self._list.itemAt(pos)
        if not item: return
        oid=item.data(Qt.ItemDataRole.UserRole)
        if not oid: return
        pg=self._canvas._cur_page()
        if not pg: return
        obj=pg.get_object(oid)
        if not obj: return

        menu=QMenu(self)
        ren_act=menu.addAction("Rename… (F2)")
        ren_act.triggered.connect(lambda: self._list.editItem(item))
        menu.addSeparator()
        # Find main window for layer ops
        main=self._canvas
        while main is not None and not isinstance(main, QMainWindow):
            main=main.parent()

        if main:
            menu.addAction("Bring to Front",
                           lambda: (self._set_sel(oid), main._layer_op('front')))
            menu.addAction("Bring Forward",
                           lambda: (self._set_sel(oid), main._layer_op('up')))
            menu.addAction("Send Backward",
                           lambda: (self._set_sel(oid), main._layer_op('down')))
            menu.addAction("Send to Back",
                           lambda: (self._set_sel(oid), main._layer_op('back')))
            menu.addSeparator()

        vis_lbl="Show" if not obj.visible else "Hide"
        def _toggle_vis():
            obj.visible = not obj.visible
            self._canvas.objectChanged.emit(); self._canvas.schedule_render()
            self.refresh()
        menu.addAction(vis_lbl, _toggle_vis)

        lck_lbl="Unlock" if obj.locked else "Lock"
        def _toggle_lock():
            obj.locked = not obj.locked
            self._canvas.objectChanged.emit(); self._canvas.schedule_render()
            self.refresh()
        menu.addAction(lck_lbl, _toggle_lock)
        menu.addSeparator()

        if main:
            menu.addAction("Duplicate", lambda: (self._set_sel(oid), main._dup_obj()))
            menu.addAction("Delete",    lambda: (self._set_sel(oid), main._del_obj()))

        menu.addSeparator()
        fxm = menu.addMenu("Layer Effects")
        fxm.addAction("Copy Effects", lambda: _copy_layer_effects(obj))

        def _fx_paste():
            _paste_layer_effects(obj)
            self._canvas.objectChanged.emit(); self._canvas.schedule_render(); self.refresh()
        pa = fxm.addAction("Paste Effects", _fx_paste); pa.setEnabled(_has_fx_clipboard())

        def _fx_clear():
            _clear_layer_effects(obj)
            self._canvas.objectChanged.emit(); self._canvas.schedule_render(); self.refresh()
        ca = fxm.addAction("Clear Effects", _fx_clear); ca.setEnabled(bool(getattr(obj, 'effects', None)))

        menu.exec(self._list.mapToGlobal(pos))

    def _set_sel(self, oid):
        self._canvas.set_sel_id(oid)
        self.objectSelected.emit(oid)

    def select(self,obj_id):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole)==obj_id:
                self._list.setCurrentRow(i); break
        self._list.blockSignals(False)


# ═══════════════════════════════════════════════════════════════════════════════
#  Collapsible group box  (v4.1.9)
# ═══════════════════════════════════════════════════════════════════════════════

class EdofCollapsibleGroup(QWidget):
    """A group box whose body can be collapsed by clicking the header.

    Photoshop / Inkscape pattern: ▼ Title (expanded) → ▶ Title (collapsed).
    State can be saved/restored via :py:meth:`setCollapsed` /
    :py:meth:`isCollapsed`, so the editor can persist it in QSettings.
    """
    toggled = pyqtSignal(bool)  # emits True when collapsed

    def __init__(self, title: str, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._collapsed = collapsed
        self._title = title

        # Header — clickable label with arrow + text
        self._header = QPushButton()
        self._header.setStyleSheet(
            "QPushButton{background:transparent;color:#a0a0c0;border:none;"
            "text-align:left;padding:4px 6px;font:bold 10pt 'Segoe UI';}"
            "QPushButton:hover{color:#ffffff;background:#2a2a3a;border-radius:3px;}")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        self._update_header()

        # Body container — holds the actual content widgets
        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 4, 8, 8)
        self._body_layout.setSpacing(4)

        # Outer layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header)
        outer.addWidget(self._body)

        self._body.setVisible(not collapsed)

    def addWidget(self, w):
        """Add a widget to the collapsible body."""
        self._body_layout.addWidget(w)

    def addLayout(self, l):
        """Add a layout to the collapsible body."""
        self._body_layout.addLayout(l)

    def setCollapsed(self, collapsed: bool):
        if collapsed == self._collapsed: return
        self._collapsed = collapsed
        self._body.setVisible(not collapsed)
        self._update_header()
        self.toggled.emit(collapsed)

    def isCollapsed(self) -> bool:
        return self._collapsed

    def _toggle(self):
        self.setCollapsed(not self._collapsed)

    def _update_header(self):
        arrow = "▶" if self._collapsed else "▼"
        self._header.setText(f"{arrow}  {self._title}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Property Panel
# ═══════════════════════════════════════════════════════════════════════════════

class PropPanel(QWidget):
    changed=pyqtSignal()

    def __init__(self,canvas,parent=None):
        super().__init__(parent); self._canvas=canvas
        self._obj=None; self._loading=False
        self._lt=QTimer(); self._lt.setSingleShot(True); self._lt.setInterval(150)
        self._lt.timeout.connect(self._live_text)
        self._qt=QTimer(); self._qt.setSingleShot(True); self._qt.setInterval(150)
        self._qt.timeout.connect(self._live_qr)
        self._setup()

    def _dspin(self,lo=-99999,hi=99999,dec=2,step=0.1,suffix=""):
        # v4.1.14: arrows now painted by our QDoubleSpinBox subclass at the
        # top of this file, so no Fusion-style hack is needed here.
        # v4.2.5: default to 0.01 mm precision (dec=2) and a 0.1 mm arrow step
        # (was 0.5) so mm fields no longer jump by half a millimetre.
        s=QDoubleSpinBox(); s.setRange(lo,hi); s.setDecimals(dec); s.setSingleStep(step)
        if suffix: s.setSuffix(suffix)
        return s

    # --- Layer-effects copy / paste / clear -----------------------------
    def _copy_effects(self):
        _copy_layer_effects(self._obj)

    def _paste_effects(self):
        if self._obj is not None and _paste_layer_effects(self._obj):
            try:
                self._canvas.schedule_render(0)
            except Exception:
                pass
            self.changed.emit()

    def _clear_effects(self):
        if self._obj is not None and _clear_layer_effects(self._obj):
            try:
                self._canvas.schedule_render(0)
            except Exception:
                pass
            self.changed.emit()

    def _fx_actions_row(self, fx_btn):
        """v4.2.11.4: Layer Effects button on its OWN row, with Copy / Paste /
        Clear layer-effect buttons on a SEPARATE row below it. Returns a single
        container so every object-type panel lays it out the same way."""
        from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                     QPushButton)
        from PyQt6.QtCore import QSize
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(4)
        v.addWidget(fx_btn)                      # row 1: the Layer Effects button

        row = QWidget(); h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)

        def _mk(icon_name, glyph, tip, cb):
            b = QPushButton(); b.setFixedSize(28, 26); b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            ic = uicon(icon_name)
            if ic is not None and not ic.isNull():
                b.setIcon(ic); b.setIconSize(QSize(15, 15))
            else:
                b.setText(glyph)
            b.setStyleSheet("QPushButton{background:#2f2f44;border:none;border-radius:4px;}"
                            "QPushButton:hover{background:#3a3a5a;}")
            b.clicked.connect(cb)
            return b
        h.addWidget(_mk('duplicate', '⧉', 'Copy layer effects', self._copy_effects))
        h.addWidget(_mk('fx', '⊕', 'Paste layer effects', self._paste_effects))
        h.addWidget(_mk('delete', '✕', 'Clear layer effects', self._clear_effects))
        h.addStretch(1)                          # row 2: copy / paste / clear
        v.addWidget(row)
        return container

    def _setup(self):
        """v4.1.3: Refactored properties panel.

        Structure (top to bottom):
          1. Transform (X/Y/W/H/Rot/Layer/Scale/Flip)  — purely geometric
          2. Type-specific panel (TextBox / Image / Shape / Table / SubDoc / QR / Line)
          3. Visibility & Locking — visible_if, lock_level, lock flags
          4. Object metadata — name, variable binding

        Removed (vs v4.1.2):
          - Opacity & Blend mode — now exclusively in Layer Effects dialog
          - Shape type combo — now only inside the Shape-specific panel,
            never shown for Text / Image / SubDoc / QR / etc.
          - Drop shadow controls — already removed in v4.1.1
        """
        from PyQt6.QtWidgets import QGroupBox, QFrame
        vb=QVBoxLayout(self); vb.setContentsMargins(6,6,6,6); vb.setSpacing(6)

        # ── 1. Transform (geometry only) ────────────────────────────────
        g_tf=QGroupBox(t('tab_transform'))
        fl=QFormLayout(g_tf); fl.setSpacing(4); fl.setContentsMargins(8,10,8,6)
        fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        # v4.1.7/4.1.9: spinboxes have a sensible minimum and stretch to fill
        # remaining space — no hard maximum cap that crops in narrow panels.
        self.sp_x=self._dspin(suffix=" mm"); self.sp_x.setMinimumWidth(50)
        self.sp_y=self._dspin(suffix=" mm"); self.sp_y.setMinimumWidth(50)
        self.sp_w=self._dspin(lo=0.1, suffix=" mm"); self.sp_w.setMinimumWidth(50)
        self.sp_h=self._dspin(lo=0.1, suffix=" mm"); self.sp_h.setMinimumWidth(50)
        self.sp_rot=self._dspin(lo=0,hi=360,step=1,dec=1,suffix="°")
        self.sp_rot.setMinimumWidth(50)

        # v4.1.7: Position + Size in one tight 2-column grid using QGridLayout
        # so that X|Y and W|H always line up cleanly.
        from PyQt6.QtWidgets import QGridLayout
        gridw = QWidget(); grid = QGridLayout(gridw)
        grid.setContentsMargins(0,0,0,0); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(4)
        lbl_x = QLabel("X"); lbl_x.setFixedWidth(14)
        lbl_y = QLabel("Y"); lbl_y.setFixedWidth(14)
        lbl_w = QLabel("W"); lbl_w.setFixedWidth(14)
        lbl_h = QLabel("H"); lbl_h.setFixedWidth(14)
        grid.addWidget(lbl_x, 0, 0); grid.addWidget(self.sp_x, 0, 1)
        grid.addWidget(lbl_y, 0, 2); grid.addWidget(self.sp_y, 0, 3)
        grid.addWidget(lbl_w, 1, 0); grid.addWidget(self.sp_w, 1, 1)
        grid.addWidget(lbl_h, 1, 2); grid.addWidget(self.sp_h, 1, 3)
        grid.setColumnStretch(1, 1); grid.setColumnStretch(3, 1)
        fl.addRow("Pos / Size:", gridw)
        # Rotation
        fl.addRow("Rotation:", self.sp_rot)

        for sp,key in [(self.sp_x,'x'),(self.sp_y,'y'),
                       (self.sp_w,'width'),(self.sp_h,'height'),
                       (self.sp_rot,'rotation')]:
            sp.editingFinished.connect(lambda k=key,s=sp: self._atf(k,s.value()))

        # v4.1.9.1: Layer index is read-only info — order is changed via the
        # ▲▲ ▲ ▼ ▼▼ buttons that reposition the object in the page's list.
        # The old spinbox was editable but mutating `obj.layer` had no effect
        # on rendering order (which is determined by list position).
        self.lbl_layer = QLabel("—")
        self.lbl_layer.setStyleSheet(
            "QLabel{color:#c0c0e0;background:#2a2a3a;border:1px solid #3a3a5a;"
            "border-radius:3px;padding:3px 6px;min-height:18px;font:10pt 'Segoe UI';}")
        self.lbl_layer.setMinimumWidth(60)
        self.lbl_layer.setToolTip(
            "Stacking order in the page (1 = back, N = front). "
            "Use the arrow buttons to reorder.")
        ly_w=QWidget(); hly=QHBoxLayout(ly_w); hly.setContentsMargins(0,0,0,0); hly.setSpacing(2)
        hly.addWidget(self.lbl_layer)
        # v4.1.10/4.1.10.1: Unicode geometric shapes with explicit font
        # fallback to Segoe UI Symbol on Windows for reliable rendering.
        BTN_FONT = "font:bold 11pt 'Segoe UI Symbol','Arial Unicode MS','DejaVu Sans';"
        for lbl,op,tip in [("⤒",'front','Bring to front'),
                             ("▲", 'up','Bring forward'),
                             ("▼", 'down','Send backward'),
                             ("⤓",'back','Send to back')]:
            b=QPushButton(lbl); b.setFixedWidth(32); b.setFixedHeight(24)
            b.setToolTip(tip)
            b.setStyleSheet(BTN_FONT + "padding:0;")
            _icn = uicon('layer-%s' % op)
            if _icn is not None and not _icn.isNull():
                from PyQt6.QtCore import QSize
                b.setText(""); b.setIcon(_icn); b.setIconSize(QSize(15, 15))
            b.clicked.connect(lambda _,o=op:self._canvas._layer_op(o))
            hly.addWidget(b)
        hly.addStretch()
        fl.addRow("Order:", ly_w)

        # Scale and Flip — one compact row
        sf_w=QWidget(); hsf=QHBoxLayout(sf_w); hsf.setContentsMargins(0,0,0,0); hsf.setSpacing(4)
        self.sp_scale=self._dspin(lo=0.01,hi=100,dec=2); self.sp_scale.setValue(1.5)
        self.sp_scale.setMinimumWidth(50)
        bs=QPushButton("Scale ×"); bs.setFixedHeight(24); bs.setMaximumWidth(70)
        bs.clicked.connect(self._apply_scale)
        # v4.1.10.3: same symbol-font + zero-padding pattern as the layer
        # arrows, since the default button QSS shrinks the glyph
        BTN_SYM_FONT = "font:bold 11pt 'Segoe UI Symbol','Arial Unicode MS','DejaVu Sans';padding:0;"
        bfh=QPushButton("⟷"); bfh.setFixedWidth(28); bfh.setFixedHeight(24)
        bfh.setStyleSheet(BTN_SYM_FONT)
        bfv=QPushButton("⇕"); bfv.setFixedWidth(28); bfv.setFixedHeight(24)
        bfv.setStyleSheet(BTN_SYM_FONT)
        bfh.setToolTip("Flip horizontal"); bfv.setToolTip("Flip vertical")
        bfh.clicked.connect(lambda:self._flip('h')); bfv.clicked.connect(lambda:self._flip('v'))
        hsf.addWidget(self.sp_scale); hsf.addWidget(bs); hsf.addStretch(); hsf.addWidget(bfh); hsf.addWidget(bfv)
        fl.addRow("Scale:", sf_w)
        vb.addWidget(g_tf)

        # ── 2. Type-specific panel ──────────────────────────────────────
        self._stack=QStackedWidget()
        vb.addWidget(self._stack,0)
        def _resize_stack_to_current():
            cur = self._stack.currentWidget()
            if cur:
                h = cur.sizeHint().height()
                self._stack.setMaximumHeight(max(80, h + 10))
        self._stack.currentChanged.connect(lambda _: _resize_stack_to_current())
        self._stack.addWidget(self._mk_empty())   # 0
        self._stack.addWidget(self._mk_tb())       # 1 TextBox
        self._stack.addWidget(self._mk_img())      # 2 ImageBox
        self._stack.addWidget(self._mk_shape())    # 3 Shape
        self._stack.addWidget(self._mk_qr())       # 4 QRCode
        self._stack.addWidget(self._mk_line())     # 5 Line
        self._stack.addWidget(self._mk_table())    # 6 Table
        self._stack.addWidget(self._mk_subdoc())   # 7 SubDocumentBox
        self._stack.addWidget(self._mk_pagesetup()) # 8 Document page setup (doc body)

        # ── 3. Visibility & Locking ─────────────────────────────────────
        g_lock=QGroupBox("Visibility & Locking")
        fa=QFormLayout(g_lock); fa.setSpacing(4); fa.setContentsMargins(8,10,8,6)
        fa.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # v4.1.4: explicit visible / locked / editable flags (were lost in
        # 4.1.3 panel refactor, causing AttributeError crashes on selection)
        self.cb_visible = QCheckBox("Visible")
        self.cb_visible.setToolTip("Hide this object on the page (uncheck to render invisible)")
        self.cb_visible.toggled.connect(lambda v: self._aa('visible', v))
        fa.addRow("", self.cb_visible)

        self.cb_locked = QCheckBox("Locked (cannot be edited at all)")
        self.cb_locked.toggled.connect(lambda v: self._aa('locked', v))
        fa.addRow("", self.cb_locked)

        self.cb_editable = QCheckBox("Allow content edit when filling form")
        self.cb_editable.setToolTip("Used by template fill workflows")
        self.cb_editable.toggled.connect(lambda v: self._aa('editable', v))
        fa.addRow("", self.cb_editable)

        self.le_visible_if=QLineEdit()
        self.le_visible_if.setPlaceholderText("e.g. amount > 0  or  tier == 'gold'")
        self.le_visible_if.setToolTip(
            "Optional Python expression. Object is rendered only when "
            "this evaluates true given current variable values.")
        self.le_visible_if.editingFinished.connect(
            lambda: self._aa('visible_if', self.le_visible_if.text().strip()))
        fa.addRow("Show if:", self.le_visible_if)

        self.cb_lock_level=QComboBox()
        self.cb_lock_level.addItems(["(none)", "fill", "edit", "design", "admin"])
        self.cb_lock_level.setToolTip(
            "Permission level required to modify this object.\n"
            "(none) — anyone can edit\n"
            "fill — only fillable fields editable\n"
            "edit — content editable, not styling\n"
            "design — full editing permitted\n"
            "admin — only admins can change anything")
        self.cb_lock_level.currentTextChanged.connect(self._on_lock_level)
        fa.addRow("Lock level:", self.cb_lock_level)

        self.cb_lock_text=QCheckBox("Lock text content (for templates)")
        self.cb_lock_text.toggled.connect(lambda v: self._aa('lock_text', v))
        fa.addRow("", self.cb_lock_text)

        self.cb_lock_position=QCheckBox("Lock position && size (content still editable)")
        self.cb_lock_position.toggled.connect(lambda v: self._aa('lock_position', v))
        fa.addRow("", self.cb_lock_position)
        # v4.1.9: wrap Visibility & Locking in a collapsible (default collapsed
        # so the panel is short when user just wants to set position/size)
        coll_lock = EdofCollapsibleGroup("Visibility & Locking", collapsed=True)
        # The inner QGroupBox keeps the visual frame but is hidden inside collapsible
        g_lock.setTitle("")  # avoid duplicate title since collapsible has its own
        g_lock.setStyleSheet("QGroupBox{border:none;margin-top:0;padding-top:0;}")
        coll_lock.addWidget(g_lock)
        vb.addWidget(coll_lock)
        self._g_lock = g_lock     # inner widget (form)
        self._coll_lock = coll_lock   # the wrapper

        # ── 4. Object metadata ──────────────────────────────────────────
        g_o=QGroupBox(t('tab_object')); fo=QFormLayout(g_o)
        fo.setSpacing(4); fo.setContentsMargins(8,10,8,6)
        fo.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.le_name=QLineEdit(); self.le_name.setPlaceholderText("Editor label")
        self.le_name.editingFinished.connect(lambda:self._aa('name',self.le_name.text()))
        fo.addRow(t('prop_name'),self.le_name)
        self.le_var=QLineEdit(); self.le_var.setPlaceholderText("variable_name")
        bv=QPushButton(t('btn_bind')); bv.setFixedWidth(60); bv.clicked.connect(self._bind_var)
        rv=QWidget(); hbv=QHBoxLayout(rv); hbv.setContentsMargins(0,0,0,0); hbv.setSpacing(4)
        hbv.addWidget(self.le_var); hbv.addWidget(bv)
        fo.addRow(t('prop_variable'), rv)
        # v4.1.4: tags (comma-separated)
        self.le_tags=QLineEdit(); self.le_tags.setPlaceholderText("tag1, tag2, …")
        self.le_tags.setToolTip("Free-form labels for grouping / filtering objects in scripts")
        self.le_tags.editingFinished.connect(self._apply_tags)
        fo.addRow("Tags:", self.le_tags)
        # ID/type info (read-only)
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet(f"color:{FGD}; font:9pt 'Segoe UI'; padding:2px;")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fo.addRow("", self.lbl_info)
        # v4.1.9: wrap Object metadata in collapsible (default collapsed)
        coll_obj = EdofCollapsibleGroup(t('tab_object'), collapsed=True)
        g_o.setTitle("")
        g_o.setStyleSheet("QGroupBox{border:none;margin-top:0;padding-top:0;}")
        coll_obj.addWidget(g_o)
        vb.addWidget(coll_obj)
        self._g_obj = g_o
        self._coll_obj = coll_obj
        # v4.1.7: also keep Transform group ref
        self._g_tf = g_tf

        # v4.1.9: persist collapsed state across sessions
        try:
            settings = QSettings("Edof", "EdofEditor")
            v_collapsed = settings.value("propPanel/lockCollapsed", True, type=bool)
            o_collapsed = settings.value("propPanel/objCollapsed", True, type=bool)
            coll_lock.setCollapsed(v_collapsed)
            coll_obj.setCollapsed(o_collapsed)
            coll_lock.toggled.connect(
                lambda c: settings.setValue("propPanel/lockCollapsed", c))
            coll_obj.toggled.connect(
                lambda c: settings.setValue("propPanel/objCollapsed", c))
        except Exception: pass

        vb.addStretch(1)

        # v4.1.7: initial state — nothing selected, hide Lock & Object groups
        self._coll_lock.setVisible(False)
        self._coll_obj.setVisible(False)
        self._g_tf.setVisible(False)

    def _mk_empty(self):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(8,12,8,12)
        lbl = QLabel("<i style='color:#7070a0'>Click an object on the page to edit its properties.</i>")
        lbl.setWordWrap(True)
        l.addWidget(lbl); l.addStretch()
        return w

    def _mk_pagesetup(self):
        """v4.2.11.41: document page setup, shown when the doc body is selected
        (the body itself has no meaningful per-object properties). Margins +
        page size + header/footer enable & height, applied to doc.body and the
        document, then repaginated."""
        from PyQt6.QtWidgets import QGroupBox
        w = QWidget(); vb = QVBoxLayout(w)
        vb.setContentsMargins(6, 4, 6, 4); vb.setSpacing(5)

        intro = QLabel("Document page setup. Applies to the whole document.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#8a8aa0;font:9pt 'Segoe UI';padding:2px;")
        vb.addWidget(intro)

        # Page size
        gsz = QGroupBox("Page size"); fsz = QFormLayout(gsz)
        fsz.setContentsMargins(8, 8, 8, 6); fsz.setSpacing(4)
        self.cb_ps_preset = QComboBox()
        self._ps_presets = [
            ("A4 portrait", 210.0, 297.0), ("A4 landscape", 297.0, 210.0),
            ("A5 portrait", 148.0, 210.0), ("A5 landscape", 210.0, 148.0),
            ("A3 portrait", 297.0, 420.0), ("A3 landscape", 420.0, 297.0),
            ("Letter portrait", 215.9, 279.4), ("Letter landscape", 279.4, 215.9),
            ("Custom", None, None),
        ]
        for nm, _ww, _hh in self._ps_presets:
            self.cb_ps_preset.addItem(nm)
        self.cb_ps_preset.currentIndexChanged.connect(self._on_ps_preset)
        fsz.addRow("Preset:", self.cb_ps_preset)
        self.sp_ps_w = self._dspin(lo=10, hi=2000, dec=1, step=1, suffix=" mm")
        self.sp_ps_h = self._dspin(lo=10, hi=2000, dec=1, step=1, suffix=" mm")
        self.sp_ps_w.editingFinished.connect(self._apply_pagesetup)
        self.sp_ps_h.editingFinished.connect(self._apply_pagesetup)
        fsz.addRow("Width:", self.sp_ps_w)
        fsz.addRow("Height:", self.sp_ps_h)
        vb.addWidget(gsz)

        # Margins
        gm = QGroupBox("Margins"); fm = QFormLayout(gm)
        fm.setContentsMargins(8, 8, 8, 6); fm.setSpacing(4)
        self.sp_mt = self._dspin(lo=0, hi=200, dec=1, step=1, suffix=" mm")
        self.sp_mr = self._dspin(lo=0, hi=200, dec=1, step=1, suffix=" mm")
        self.sp_mb = self._dspin(lo=0, hi=200, dec=1, step=1, suffix=" mm")
        self.sp_ml = self._dspin(lo=0, hi=200, dec=1, step=1, suffix=" mm")
        for sp in (self.sp_mt, self.sp_mr, self.sp_mb, self.sp_ml):
            sp.editingFinished.connect(self._apply_pagesetup)
        fm.addRow("Top:", self.sp_mt); fm.addRow("Right:", self.sp_mr)
        fm.addRow("Bottom:", self.sp_mb); fm.addRow("Left:", self.sp_ml)
        vb.addWidget(gm)

        # Header / footer
        ghf = QGroupBox("Header & footer"); fhf = QFormLayout(ghf)
        fhf.setContentsMargins(8, 8, 8, 6); fhf.setSpacing(4)
        self.cb_hdr_on = QCheckBox("Enable header")
        self.cb_hdr_on.toggled.connect(self._apply_pagesetup)
        fhf.addRow("", self.cb_hdr_on)
        self.sp_hdr_h = self._dspin(lo=3, hi=100, dec=1, step=1, suffix=" mm")
        self.sp_hdr_h.editingFinished.connect(self._apply_pagesetup)
        fhf.addRow("Header height:", self.sp_hdr_h)
        self.cb_ftr_on = QCheckBox("Enable footer")
        self.cb_ftr_on.toggled.connect(self._apply_pagesetup)
        fhf.addRow("", self.cb_ftr_on)
        self.sp_ftr_h = self._dspin(lo=3, hi=100, dec=1, step=1, suffix=" mm")
        self.sp_ftr_h.editingFinished.connect(self._apply_pagesetup)
        fhf.addRow("Footer height:", self.sp_ftr_h)
        # v4.2.11.46: page numbering start + odd/even template sets
        self.sp_pn_start = QSpinBox(); self.sp_pn_start.setRange(1, 9999)
        self.sp_pn_start.setValue(1)
        self.sp_pn_start.editingFinished.connect(self._apply_pagesetup)
        fhf.addRow("First page number:", self.sp_pn_start)
        self.cb_odd_even = QCheckBox("Different odd && even pages")
        self.cb_odd_even.setToolTip(
            "Pages with an even page number use their own header/footer.\n"
            "Edit them by double-clicking the band on an even page.")
        self.cb_odd_even.toggled.connect(self._apply_pagesetup)
        fhf.addRow("", self.cb_odd_even)
        # v4.2.11.48: text fitting for the bands. Stored in the persisted band
        # style (header_style/footer_style), applied on every page.
        self.cb_hdr_shrink = QCheckBox("Header: auto-shrink text")
        self.cb_hdr_fill   = QCheckBox("Header: auto-fill (grow to fit)")
        self.cb_ftr_shrink = QCheckBox("Footer: auto-shrink text")
        self.cb_ftr_fill   = QCheckBox("Footer: auto-fill (grow to fit)")
        for cb in (self.cb_hdr_shrink, self.cb_hdr_fill,
                   self.cb_ftr_shrink, self.cb_ftr_fill):
            cb.toggled.connect(self._apply_pagesetup)
            fhf.addRow("", cb)
        hint = QLabel("Double-click the header/footer band on the page to edit "
                      "its text. Use the #▾ button there to insert page numbers.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a8aa0;font:8pt 'Segoe UI';padding:2px;")
        vb.addWidget(ghf); vb.addWidget(hint)
        vb.addStretch()
        return w

    def _on_ps_preset(self, idx):
        if self._loading:
            return
        if 0 <= idx < len(self._ps_presets):
            _nm, ww, hh = self._ps_presets[idx]
            if ww is not None:
                self.sp_ps_w.blockSignals(True); self.sp_ps_h.blockSignals(True)
                self.sp_ps_w.setValue(ww); self.sp_ps_h.setValue(hh)
                self.sp_ps_w.blockSignals(False); self.sp_ps_h.blockSignals(False)
        self._apply_pagesetup()

    def _load_pagesetup(self, obj):
        doc = getattr(self._canvas, '_doc', None)
        if doc is None:
            return
        body = getattr(doc, 'body', None)
        self._loading = True
        try:
            pg = self._canvas._cur_page()
            pw = float(getattr(pg, 'width', 210.0)) if pg else 210.0
            ph = float(getattr(pg, 'height', 297.0)) if pg else 297.0
            self.sp_ps_w.setValue(pw); self.sp_ps_h.setValue(ph)
            # match a preset if dimensions line up, else Custom
            sel = len(self._ps_presets) - 1
            for i, (_nm, ww, hh) in enumerate(self._ps_presets):
                if ww is not None and abs(ww - pw) < 0.5 and abs(hh - ph) < 0.5:
                    sel = i; break
            self.cb_ps_preset.setCurrentIndex(sel)
            # margins: prefer body.page_margins_mm, else doc.margins
            m = None
            if body is not None and getattr(body, 'page_margins_mm', None):
                m = body.page_margins_mm
            elif getattr(doc, 'margins', None):
                m = doc.margins
            if m and len(m) == 4:
                self.sp_mt.setValue(float(m[0])); self.sp_mr.setValue(float(m[1]))
                self.sp_mb.setValue(float(m[2])); self.sp_ml.setValue(float(m[3]))
            if body is not None:
                self.cb_hdr_on.setChecked(bool(getattr(body, 'header_enabled', False)))
                self.cb_ftr_on.setChecked(bool(getattr(body, 'footer_enabled', False)))
                self.sp_hdr_h.setValue(float(getattr(body, 'header_height_mm', 12.0)))
                self.sp_ftr_h.setValue(float(getattr(body, 'footer_height_mm', 12.0)))
                self.sp_pn_start.setValue(int(getattr(body, 'page_number_start', 1) or 1))
                self.cb_odd_even.setChecked(bool(getattr(body, 'hf_odd_even', False)))
                hs = getattr(body, 'header_style', None) or {}
                fs = getattr(body, 'footer_style', None) or {}
                self.cb_hdr_shrink.setChecked(bool(hs.get('auto_shrink')))
                self.cb_hdr_fill.setChecked(bool(hs.get('auto_fill')))
                self.cb_ftr_shrink.setChecked(bool(fs.get('auto_shrink')))
                self.cb_ftr_fill.setChecked(bool(fs.get('auto_fill')))
        finally:
            self._loading = False

    def _apply_pagesetup(self):
        if self._loading:
            return
        doc = getattr(self._canvas, '_doc', None)
        if doc is None:
            return
        body = getattr(doc, 'body', None)
        pw = float(self.sp_ps_w.value()); ph = float(self.sp_ps_h.value())
        margins = (float(self.sp_mt.value()), float(self.sp_mr.value()),
                   float(self.sp_mb.value()), float(self.sp_ml.value()))
        try:
            for pg in doc.pages:
                pg.width = pw; pg.height = ph
            doc.margins = margins
            if body is not None:
                body.page_margins_mm = margins
                body.header_enabled = bool(self.cb_hdr_on.isChecked())
                body.footer_enabled = bool(self.cb_ftr_on.isChecked())
                body.header_height_mm = float(self.sp_hdr_h.value())
                body.footer_height_mm = float(self.sp_ftr_h.value())
                body.page_number_start = int(self.sp_pn_start.value())
                body.hf_odd_even = bool(self.cb_odd_even.isChecked())
                # v4.2.11.48: merge text-fitting flags into the persisted band
                # styles. If a band has no stored style yet, seed it from the
                # band box currently on the page (or engine defaults) so a
                # later from_dict doesn't reset its other attributes.
                def _hf_seed(role):
                    sd = getattr(body, f'{role}_style', None)
                    if sd:
                        return dict(sd)
                    try:
                        from edof.engine.document_paginate import (
                            find_document_header_on_page as _ffh,
                            find_document_footer_on_page as _fff)
                        pg2 = self._canvas._cur_page()
                        box = (_ffh(pg2) if role == 'header' else _fff(pg2)) if pg2 else None
                        if box is not None:
                            return box.style.to_dict()
                    except Exception:
                        pass
                    from edof.format.styles import TextStyle as _TS
                    return _TS().to_dict()
                for role, shr, fil in (
                        ('header', self.cb_hdr_shrink, self.cb_hdr_fill),
                        ('footer', self.cb_ftr_shrink, self.cb_ftr_fill)):
                    sd = _hf_seed(role)
                    sd['auto_shrink'] = bool(shr.isChecked())
                    sd['auto_fill'] = bool(fil.isChecked())
                    setattr(body, f'{role}_style', sd)
                    if body.hf_odd_even:
                        se = getattr(body, f'{role}_style_even', None)
                        se = dict(se) if se else dict(sd)
                        se['auto_shrink'] = bool(shr.isChecked())
                        se['auto_fill'] = bool(fil.isChecked())
                        setattr(body, f'{role}_style_even', se)
            self._canvas._margins = margins
            self._canvas._margins_enabled = True
            from edof.engine.document_paginate import paginate_document
            paginate_document(doc, dpi=self._canvas._dpi)
            mw = self._canvas.parent()
            if mw is not None and hasattr(mw, '_refresh_pages'):
                try: mw._refresh_pages()
                except Exception: pass
            if mw is not None and hasattr(mw, '_mark_modified'):
                try: mw._mark_modified()
                except Exception: pass
            try: self._canvas._invalidate_page_cache()
            except Exception: pass
            self._canvas.schedule_render(0)
            self._canvas.viewport().update()
        except Exception:
            import traceback as _tb; _tb.print_exc()

    def _mk_tb(self):
        from PyQt6.QtWidgets import QGroupBox
        w=QWidget(); vb=QVBoxLayout(w); vb.setContentsMargins(6,4,6,4); vb.setSpacing(5)
        g1=QGroupBox("Content"); fl1=QFormLayout(g1); fl1.setContentsMargins(8,8,8,6)
        self.te_text=QTextEdit(); self.te_text.setFixedHeight(80)
        self.te_text.textChanged.connect(lambda:self._lt.start())
        fl1.addRow(self.te_text); vb.addWidget(g1)

        g2=QGroupBox(t('tab_style')); fl2=QFormLayout(g2); fl2.setSpacing(4); fl2.setContentsMargins(8,8,8,6)
        self.cb_font=QComboBox(); self.cb_font.setEditable(True)
        # v4.1.0: handle font selection — itemData is the clean name without badge
        def _on_font_change(text):
            if self._loading: return
            # If user picked from dropdown, use itemData (clean name)
            idx = self.cb_font.currentIndex()
            real_name = self.cb_font.itemData(idx) if idx >= 0 else None
            if not real_name:
                # User typed manually — strip any badge prefix/suffix
                real_name = text.replace("✓ ", "").split("  (PDF-safe)")[0].strip()
            self._as('font_family', real_name, str)
        self.cb_font.currentTextChanged.connect(_on_font_change)
        fl2.addRow(t('prop_font'),self.cb_font)
        # v4.1.17: font_size in mm (canonical). Range 0.1–500mm gives 0.28–1417pt
        self.sp_fsize=self._dspin(lo=0.1,hi=500,dec=2,step=0.5,suffix=" mm")
        self.sp_fsize.editingFinished.connect(lambda:self._as('font_size',self.sp_fsize.value(),float))
        fl2.addRow(t('prop_size'),self.sp_fsize)
        rc=QWidget(); hbc=QHBoxLayout(rc); hbc.setContentsMargins(0,0,0,0)
        self.btn_color=QPushButton(); self.btn_color.setFixedSize(36,22)
        self.btn_color.clicked.connect(self._pick_text_color)
        hbc.addWidget(self.btn_color); hbc.addStretch(); fl2.addRow(t('prop_color'),rc)
        self.cb_align=QComboBox(); self.cb_align.addItems(["left","center","right","justify"])
        self.cb_align.currentTextChanged.connect(lambda v:self._as('alignment',v,str))
        fl2.addRow(t('prop_align_h'),self.cb_align)
        self.cb_valign=QComboBox(); self.cb_valign.addItems(["top","middle","bottom"])
        self.cb_valign.currentTextChanged.connect(lambda v:self._as('vertical_align',v,str))
        fl2.addRow(t('prop_align_v'),self.cb_valign)
        self.sp_lh=self._dspin(lo=0.5,hi=5,dec=2,step=0.05)
        self.sp_lh.editingFinished.connect(lambda:self._as('line_height',self.sp_lh.value(),float))
        fl2.addRow(t('prop_line_height'),self.sp_lh)
        for attr,lbl in [('bold','Bold'),('italic','Italic'),('underline','Underline'),
                         ('strikethrough','Strikethrough'),('wrap','Wrap'),('overflow_hidden','Hide overflow')]:
            cb=QCheckBox(lbl); cb.toggled.connect(lambda v,a=attr:self._as(a,v,bool))
            setattr(self,f'cb_{attr}',cb); fl2.addRow("",cb)
        vb.addWidget(g2)

        g3=QGroupBox("Sizing"); fb=QVBoxLayout(g3); fb.setContentsMargins(8,8,8,6)
        self._sz_bg=QButtonGroup(self)
        self.rb_fixed=QRadioButton(t('sizing_fixed'))
        self.rb_shrink=QRadioButton(t('sizing_shrink'))
        self.rb_fill=QRadioButton(t('sizing_fill'))
        for rb in (self.rb_fixed,self.rb_shrink,self.rb_fill):
            self._sz_bg.addButton(rb); fb.addWidget(rb); rb.toggled.connect(self._apply_sizing)
        # v4.1.17: min/max font_size in mm. Default upper is 500mm, but
        # there's a "no limit" checkbox to allow unbounded auto-fill.
        self.sp_minfs=self._dspin(lo=0.1,hi=500,dec=2,step=0.5,suffix=" mm")
        self.sp_minfs.editingFinished.connect(lambda:self._as('min_font_size',self.sp_minfs.value(),float))
        rm=QWidget(); hm=QHBoxLayout(rm); hm.setContentsMargins(0,0,0,0)
        hm.addWidget(QLabel(t('prop_min_size'))); hm.addWidget(self.sp_minfs)
        fb.addWidget(rm)
        # Max font size + ∞ checkbox
        self.sp_maxfs=self._dspin(lo=0.1,hi=10000,dec=2,step=1.0,suffix=" mm")
        self.sp_maxfs.editingFinished.connect(lambda:self._as('max_font_size',self.sp_maxfs.value(),float))
        self.cb_maxfs_inf=QCheckBox("∞ (no limit)")
        def _toggle_inf(checked):
            # When checked, set max to a huge effective value; remember previous
            if checked:
                self._prev_maxfs = self.sp_maxfs.value()
                self.sp_maxfs.setEnabled(False)
                self._as('max_font_size', 1e6, float)   # effectively unlimited
            else:
                self.sp_maxfs.setEnabled(True)
                val = getattr(self, '_prev_maxfs', 70.555)
                self.sp_maxfs.setValue(val)
                self._as('max_font_size', val, float)
        self.cb_maxfs_inf.toggled.connect(_toggle_inf)
        rmax=QWidget(); hmax=QHBoxLayout(rmax); hmax.setContentsMargins(0,0,0,0)
        hmax.addWidget(QLabel(t('prop_max_size'))); hmax.addWidget(self.sp_maxfs)
        hmax.addWidget(self.cb_maxfs_inf)
        fb.addWidget(rmax)
        vb.addWidget(g3)
        btn_uf=QPushButton(t('btn_upload_font')); btn_uf.clicked.connect(self._upload_font)
        vb.addWidget(btn_uf)
        # v4.1.3: Layer Effects in every type panel
        btn_fx_tb = QPushButton("✨ Layer Effects…")
        btn_fx_tb.setStyleSheet("font:bold 10pt 'Segoe UI';background:#3a3a5a;padding:6px;")
        btn_fx_tb.clicked.connect(self._open_layer_effects_dialog)
        fx_container_tb = self._fx_actions_row(btn_fx_tb)
        vb.addWidget(fx_container_tb)
        self._btn_fx_tb = fx_container_tb      # v4.1.23.37: toggled off for doc body
        # v4.1.23.37: shown instead of effects when the document body is selected
        self._lbl_body_note = QLabel("Document body — special text effects are "
                                     "applied to inserted text boxes, not the page body.")
        self._lbl_body_note.setWordWrap(True)
        self._lbl_body_note.setStyleSheet("color:#8a8aa0;font:9pt 'Segoe UI';padding:4px;")
        self._lbl_body_note.setVisible(False)
        vb.addWidget(self._lbl_body_note)
        vb.addStretch(); return w

    def _mk_img(self):
        w=QWidget(); fl=QFormLayout(w); fl.setContentsMargins(8,8,8,6)
        self.cb_fit=QComboBox(); self.cb_fit.addItems(["contain","cover","fill","stretch","none"])
        self.cb_fit.currentTextChanged.connect(lambda v:self._aa('fit_mode',v))
        fl.addRow(t('prop_fit_mode'),self.cb_fit)
        fl.addRow("",QLabel("<small style='color:#7070a0'>Variable = file path or URL for dynamic image</small>"))
        btn_rep=QPushButton(t('btn_replace')); btn_rep.clicked.connect(self._replace_image)
        fl.addRow("",btn_rep)
        # v4.1.1: Layer Effects button (gives access to blend mode + opacity + effects)
        btn_fx = QPushButton("✨ Layer Effects… (blend mode, effects)")
        btn_fx.setStyleSheet("font:bold 10pt 'Segoe UI';background:#3a3a5a;padding:6px;")
        btn_fx.clicked.connect(self._open_layer_effects_dialog)
        fl.addRow("", self._fx_actions_row(btn_fx))
        return w

    def _mk_shape(self):
        w=QWidget(); fl=QFormLayout(w); fl.setContentsMargins(8,8,8,6); fl.setSpacing(6)
        fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # v4.1.3: Shape type combo moved here from "Advanced" — only shown
        # for Shape objects (not text, image, etc.)
        self.cb_shape_type = QComboBox()
        self.cb_shape_type.addItems(["rect", "ellipse", "line", "polygon", "arrow", "path"])
        self.cb_shape_type.setToolTip(
            "Switching to 'path' converts the shape to editable path data.\\n"
            "Switching from 'path' to a built-in shape replaces curve detail "
            "with the bounding box (irreversible).")
        self.cb_shape_type.currentTextChanged.connect(self._on_shape_type)
        fl.addRow("Type:", self.cb_shape_type)

        rf=QWidget(); hf=QHBoxLayout(rf); hf.setContentsMargins(0,0,0,0); hf.setSpacing(4)
        self.btn_fill=QPushButton(); self.btn_fill.setFixedSize(40,24)
        self.btn_fill.setToolTip("Fill color (click to choose, with alpha)")
        self.btn_fill.clicked.connect(self._pick_fill)
        self.lbl_fill_a=QLabel("100%"); self.lbl_fill_a.setFixedWidth(40)
        hf.addWidget(self.btn_fill); hf.addWidget(self.lbl_fill_a); hf.addStretch()
        fl.addRow(t('prop_fill'),rf)

        rs=QWidget(); hs=QHBoxLayout(rs); hs.setContentsMargins(0,0,0,0); hs.setSpacing(4)
        self.btn_stroke=QPushButton(); self.btn_stroke.setFixedSize(40,24)
        self.btn_stroke.clicked.connect(self._pick_stroke)
        self.sp_sw=self._dspin(lo=0.01,hi=20,dec=2,step=0.1,suffix=" mm"); self.sp_sw.setFixedWidth(90)
        self.sp_sw.editingFinished.connect(self._apply_stroke_w)
        hs.addWidget(self.btn_stroke); hs.addWidget(self.sp_sw); hs.addStretch()
        fl.addRow(t('prop_stroke'),rs)

        self.sp_cr=self._dspin(lo=0,hi=200,dec=2,suffix=" mm")
        self.sp_cr.editingFinished.connect(self._apply_corner_uniform)
        fl.addRow("Corner radius:",self.sp_cr)
        # v4.2.7.1: per-corner radii [TL, TR, BR, BL] — two rows (top / bottom)
        rcr=QWidget(); gcr=QGridLayout(rcr); gcr.setContentsMargins(0,0,0,0)
        gcr.setHorizontalSpacing(4); gcr.setVerticalSpacing(2)
        self.sp_cr_tl=self._dspin(lo=0,hi=200,dec=2); self.sp_cr_tl.setFixedWidth(64)
        self.sp_cr_tr=self._dspin(lo=0,hi=200,dec=2); self.sp_cr_tr.setFixedWidth(64)
        self.sp_cr_br=self._dspin(lo=0,hi=200,dec=2); self.sp_cr_br.setFixedWidth(64)
        self.sp_cr_bl=self._dspin(lo=0,hi=200,dec=2); self.sp_cr_bl.setFixedWidth(64)
        for s in (self.sp_cr_tl,self.sp_cr_tr,self.sp_cr_br,self.sp_cr_bl):
            s.editingFinished.connect(self._apply_corner_each)
        gcr.addWidget(QLabel("TL"),0,0); gcr.addWidget(self.sp_cr_tl,0,1)
        gcr.addWidget(QLabel("TR"),0,2); gcr.addWidget(self.sp_cr_tr,0,3)
        gcr.addWidget(QLabel("BL"),1,0); gcr.addWidget(self.sp_cr_bl,1,1)
        gcr.addWidget(QLabel("BR"),1,2); gcr.addWidget(self.sp_cr_br,1,3)
        gcr.setColumnStretch(4,1)
        fl.addRow("Corners (mm):",rcr)

        # Path-only controls
        rp=QWidget(); hp=QHBoxLayout(rp); hp.setContentsMargins(0,0,0,0); hp.setSpacing(4)
        btn_smooth = QPushButton("⌒ Smooth")
        btn_smooth.setToolTip("Convert path to smooth Bezier curves (Catmull-Rom)")
        btn_smooth.clicked.connect(self._smooth_path)
        btn_sharp = QPushButton("∠ Sharp")
        btn_sharp.setToolTip("Convert path back to straight lines")
        btn_sharp.clicked.connect(self._sharpen_path)
        hp.addWidget(btn_smooth); hp.addWidget(btn_sharp); hp.addStretch()
        fl.addRow("Path:", rp)

        btn_edit = QPushButton("✎ Edit Path Points")
        btn_edit.setStyleSheet("background:#2a4a3a;padding:6px;font-weight:bold;")
        btn_edit.setToolTip("Drag points and bezier handles to reshape the path. "
                              "Yellow squares = anchor points. Blue circles = bezier handles. "
                              "Right-click an anchor to switch to Sharp / Smooth or delete it. "
                              "Shift+click an empty segment to insert a new point.")
        btn_edit.clicked.connect(self._toggle_path_edit)
        fl.addRow("", btn_edit)

        # v4.1.12: removed "Close / Open path" button. Closing/opening is now
        # done via Connect (C key, 2 selected anchors) / Disconnect (D key,
        # 1 selected anchor). Single conceptual operator instead of two
        # overlapping buttons.

        # v4.1.3: Layer Effects button in EVERY type panel for consistency
        btn_fx = QPushButton("✨ Layer Effects…")
        btn_fx.setStyleSheet("font:bold 10pt 'Segoe UI';background:#3a3a5a;padding:6px;")
        btn_fx.setToolTip("Drop shadow, glow, bevel, stroke, overlays, blend mode, opacity")
        btn_fx.clicked.connect(self._open_layer_effects_dialog)
        fl.addRow("", self._fx_actions_row(btn_fx))
        return w

    def _smooth_path(self):
        """v4.1.0/4.1.1: Convert straight-line path to smooth cubic-Bezier curve.

        v4.1.1 fix: after smoothing, recompute path bbox (which may be larger
        due to bezier control points overshooting) and adjust the object's
        transform so the visible result stays in place and selection handles
        remain accurate.
        """
        from edof.format.objects import SHAPE_PATH
        if not self._obj or getattr(self._obj, 'shape_type', None) != SHAPE_PATH:
            return
        if not self._obj.path_data:
            return
        # Extract just the points
        points = []
        is_closed = False
        for cmd in self._obj.path_data:
            if not cmd: continue
            op = cmd[0]
            if op in ("M", "L"):
                points.append((cmd[1], cmd[2]))
            elif op == "C":
                points.append((cmd[5], cmd[6]))
            elif op == "Q":
                points.append((cmd[3], cmd[4]))
            elif op == "Z":
                is_closed = True
        if len(points) < 2: return
        # Catmull-Rom to cubic Bezier conversion
        new_data = [["M", points[0][0], points[0][1]]]
        n = len(points)
        tension = 0.5
        for i in range(n - 1):
            p0 = points[i-1] if i > 0 else (points[-2] if is_closed else points[i])
            p1 = points[i]
            p2 = points[i+1]
            p3 = points[i+2] if i+2 < n else (points[1] if is_closed else points[i+1])
            cx1 = p1[0] + (p2[0] - p0[0]) * tension / 3.0
            cy1 = p1[1] + (p2[1] - p0[1]) * tension / 3.0
            cx2 = p2[0] - (p3[0] - p1[0]) * tension / 3.0
            cy2 = p2[1] - (p3[1] - p1[1]) * tension / 3.0
            new_data.append(["C", cx1, cy1, cx2, cy2, p2[0], p2[1]])
        if is_closed:
            new_data.append(["Z"])
        self._obj.path_data = new_data
        # v4.1.1: fix transform so smooth path stays in place visually
        self._normalize_path_transform(self._obj)
        self._canvas.schedule_render(); self.changed.emit()

    def _normalize_path_transform(self, obj):
        """v4.1.1: Compute path bbox, shift path_data to local origin (0,0),
        and shift transform.x/y by the same amount so the visible position
        is unchanged. Update transform.width/height to match the new bbox."""
        if not obj.path_data: return
        # Find min/max across all points (including bezier control points)
        xs, ys = [], []
        for cmd in obj.path_data:
            if not cmd: continue
            op = cmd[0]
            if op == "M" or op == "L":
                xs.append(cmd[1]); ys.append(cmd[2])
            elif op == "C":
                # Include control points so bbox encloses curve overshoot
                xs.extend([cmd[1], cmd[3], cmd[5]])
                ys.extend([cmd[2], cmd[4], cmd[6]])
            elif op == "Q":
                xs.extend([cmd[1], cmd[3]])
                ys.extend([cmd[2], cmd[4]])
        if not xs or not ys: return
        min_x = min(xs); min_y = min(ys)
        max_x = max(xs); max_y = max(ys)
        # Shift everything so min becomes (0,0)
        if min_x != 0 or min_y != 0:
            new_data = []
            for cmd in obj.path_data:
                if not cmd: new_data.append(cmd); continue
                op = cmd[0]
                if op == "M" or op == "L":
                    new_data.append([op, cmd[1] - min_x, cmd[2] - min_y])
                elif op == "C":
                    new_data.append([op,
                        cmd[1] - min_x, cmd[2] - min_y,
                        cmd[3] - min_x, cmd[4] - min_y,
                        cmd[5] - min_x, cmd[6] - min_y])
                elif op == "Q":
                    new_data.append([op,
                        cmd[1] - min_x, cmd[2] - min_y,
                        cmd[3] - min_x, cmd[4] - min_y])
                else:
                    new_data.append(cmd)
            obj.path_data = new_data
            obj.transform.x += min_x
            obj.transform.y += min_y
        obj.transform.width = max(1.0, max_x - min_x)
        obj.transform.height = max(1.0, max_y - min_y)

    def _sharpen_path(self):
        """v4.1.0: Convert path with curves back to straight line segments."""
        from edof.format.objects import SHAPE_PATH
        if not self._obj or getattr(self._obj, 'shape_type', None) != SHAPE_PATH:
            return
        if not self._obj.path_data:
            return
        new_data = []
        is_closed = False
        first = True
        for cmd in self._obj.path_data:
            if not cmd: continue
            op = cmd[0]
            if op == "M":
                new_data.append(["M", cmd[1], cmd[2]])
                first = False
            elif op == "L":
                new_data.append(cmd)
            elif op == "C":
                # Take the endpoint only as a line segment
                new_data.append(["L", cmd[5], cmd[6]])
            elif op == "Q":
                new_data.append(["L", cmd[3], cmd[4]])
            elif op == "Z":
                new_data.append(["Z"])
        self._obj.path_data = new_data
        self._normalize_path_transform(self._obj)
        self._canvas.schedule_render(); self.changed.emit()

    def _toggle_path_close(self):
        """v4.1.8: Add or remove the Z (close) command on the path."""
        from edof.format.objects import Shape, SHAPE_PATH
        if not self._obj or not isinstance(self._obj, Shape): return
        if self._obj.shape_type != SHAPE_PATH: return
        if not self._obj.path_data: return
        is_closed = (self._obj.path_data[-1]
                     and self._obj.path_data[-1][0] == "Z")
        if is_closed:
            # Open the path — remove the Z
            self._obj.path_data = [c for c in self._obj.path_data if not (c and c[0] == "Z")]
        else:
            # Close the path — append Z
            self._obj.path_data.append(["Z"])
        self._canvas.schedule_render(0)
        self._canvas._refresh_path_edit_handles()
        self.changed.emit()

    def _toggle_path_edit(self):
        """v4.1.0: Enter/exit path point edit mode on the canvas."""
        from edof.format.objects import SHAPE_PATH
        if not self._obj or getattr(self._obj, 'shape_type', None) != SHAPE_PATH:
            return
        # Toggle the canvas's path edit mode
        if getattr(self._canvas, '_path_edit_obj_id', None) == self._obj.id:
            self._canvas._exit_path_edit_mode()
        else:
            self._canvas._enter_path_edit_mode(self._obj)

    def _mk_qr(self):
        w=QWidget(); fl=QFormLayout(w); fl.setContentsMargins(8,8,8,6); fl.setSpacing(5)
        self.le_qr=QLineEdit(); self.le_qr.setPlaceholderText("URL or data…")
        self.le_qr.textChanged.connect(lambda:self._qt.start())
        fl.addRow(t('prop_qr_data'),self.le_qr)
        self.cb_ec=QComboBox(); self.cb_ec.addItems(["L","M","Q","H"]); self.cb_ec.setCurrentText("M")
        self.cb_ec.currentTextChanged.connect(lambda v:self._aa('error_correction',v))
        fl.addRow(t('prop_qr_ec'),self.cb_ec)
        for attr,lbl_key in [('fg_color','prop_qr_fg'),('bg_color','prop_qr_bg')]:
            row=QWidget(); hb=QHBoxLayout(row); hb.setContentsMargins(0,0,0,0)
            btn=QPushButton(); btn.setFixedSize(36,22)
            btn.clicked.connect(lambda _,a=attr:self._pick_qr_color(a))
            lbl_a=QLabel("100%"); lbl_a.setFixedWidth(36)
            setattr(self,f'btn_qr_{attr}',btn); setattr(self,f'lbl_qr_{attr}_a',lbl_a)
            hb.addWidget(btn); hb.addWidget(lbl_a); hb.addStretch()
            fl.addRow(t(lbl_key),row)
        self.sp_qr_brd=QSpinBox(); self.sp_qr_brd.setRange(0,20); self.sp_qr_brd.setValue(4)
        self.sp_qr_brd.editingFinished.connect(lambda:self._aa('border_modules',self.sp_qr_brd.value()))
        fl.addRow(t('prop_qr_border'),self.sp_qr_brd)
        # v4.2.7.1: QR codes support layer effects too (respect alpha)
        btn_fx=QPushButton("✨ Layer Effects…")
        btn_fx.clicked.connect(self._open_layer_effects_dialog)
        fl.addRow(self._fx_actions_row(btn_fx)); return w

    def _mk_line(self):
        w=QWidget(); fl=QFormLayout(w); fl.setContentsMargins(8,8,8,6); fl.setSpacing(5)
        self.sp_lx1=self._dspin(); self.sp_ly1=self._dspin()
        self.sp_lx2=self._dspin(); self.sp_ly2=self._dspin()
        for lbl,sp,i,c in [(t('prop_x1'),self.sp_lx1,0,'x'),(t('prop_y1'),self.sp_ly1,0,'y'),
                           (t('prop_x2'),self.sp_lx2,1,'x'),(t('prop_y2'),self.sp_ly2,1,'y')]:
            sp.editingFinished.connect(lambda ii=i,cc=c,s=sp:self._apply_line_pt(ii,cc,s.value()))
            fl.addRow(lbl,sp)
        rl=QWidget(); hl=QHBoxLayout(rl); hl.setContentsMargins(0,0,0,0)
        self.btn_lstroke=QPushButton(); self.btn_lstroke.setFixedSize(36,22)
        self.btn_lstroke.clicked.connect(self._pick_line_stroke)
        self.sp_lsw=self._dspin(lo=0.01,hi=20,dec=2,step=0.1,suffix=" mm"); self.sp_lsw.setFixedWidth(80)
        self.sp_lsw.editingFinished.connect(lambda:self._apply_line_sw())
        hl.addWidget(self.btn_lstroke); hl.addWidget(self.sp_lsw); hl.addStretch()
        fl.addRow(t('prop_stroke'),rl)
        # v4.2.7.1: lines support layer effects too
        btn_fx=QPushButton("✨ Layer Effects…")
        btn_fx.clicked.connect(self._open_layer_effects_dialog)
        fl.addRow(self._fx_actions_row(btn_fx)); return w

    def _mk_table(self):
        """v4.1.0/4.1.1: Table editing UI panel."""
        w = QWidget(); fl = QFormLayout(w); fl.setContentsMargins(8, 8, 8, 6); fl.setSpacing(6)

        # Open cell editor (the main interface for editing cells)
        btn_edit = QPushButton("✎ Edit Cells…")
        btn_edit.setStyleSheet("font:bold 11pt 'Segoe UI';background:#3a3a5a;padding:6px;")
        btn_edit.setToolTip("Open the cell editor to edit cell text, colors, borders, alignment")
        btn_edit.clicked.connect(self._open_table_cell_editor)
        fl.addRow("", btn_edit)

        # ── Outer border ────────────────────────────────────────────────
        # Single combined row: [☑ Outer border] [color] [width spin]
        ob_row = QWidget(); ob_h = QHBoxLayout(ob_row); ob_h.setContentsMargins(0,0,0,0); ob_h.setSpacing(6)
        self.cb_table_border = QCheckBox("Outer border")
        self.cb_table_border.toggled.connect(self._on_table_border_toggle)
        self.btn_table_border_color = QPushButton(); self.btn_table_border_color.setFixedSize(28, 22)
        self.btn_table_border_color.setToolTip("Border color")
        self.btn_table_border_color.clicked.connect(self._pick_table_border_color)
        self.sp_table_border_w = self._dspin(lo=0.1, hi=20, dec=2, step=0.1, suffix=" mm")
        self.sp_table_border_w.setFixedWidth(80)
        self.sp_table_border_w.setToolTip("Border width")
        self.sp_table_border_w.editingFinished.connect(self._on_table_border_change)
        ob_h.addWidget(self.cb_table_border)
        ob_h.addWidget(self.btn_table_border_color)
        ob_h.addWidget(self.sp_table_border_w)
        ob_h.addStretch()
        fl.addRow("", ob_row)

        # ── Structure: row/column ops in one neat row ──────────────────
        rrc = QWidget(); hrc = QHBoxLayout(rrc); hrc.setContentsMargins(0,0,0,0); hrc.setSpacing(4)
        for label, tip, action in [
            ("+ Row", "Add row at the bottom", "add_row"),
            ("− Row", "Remove last row", "del_row"),
            ("+ Col", "Add column at the right", "add_col"),
            ("− Col", "Remove last column", "del_col"),
        ]:
            btn = QPushButton(label); btn.setFixedHeight(24); btn.setMinimumWidth(56)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _, a=action: self._table_struct_op(a))
            hrc.addWidget(btn)
        hrc.addStretch()
        fl.addRow("Rows / cols:", rrc)

        # Layer effects entry point
        btn_fx = QPushButton("✨ Layer Effects…")
        btn_fx.setStyleSheet("font:bold 10pt 'Segoe UI';background:#3a3a5a;padding:6px;")
        btn_fx.clicked.connect(self._open_layer_effects_dialog)
        fl.addRow("", self._fx_actions_row(btn_fx))

        return w

    def _on_table_border_toggle(self, on):
        if self._loading or not isinstance(self._obj, edof.Table): return
        if on:
            from edof.format.styles import StrokeStyle
            if not self._obj.table_border:
                self._obj.table_border = StrokeStyle()
            self._obj.table_border.color = (50, 50, 50, 255)
            self._obj.table_border.width = 0.5
        else:
            self._obj.table_border = None
        self._canvas.schedule_render(); self.changed.emit()

    def _pick_table_border_color(self):
        if self._loading or not isinstance(self._obj, edof.Table): return
        if not self._obj.table_border:
            from edof.format.styles import StrokeStyle
            self._obj.table_border = StrokeStyle()
        from PyQt6.QtWidgets import QColorDialog
        cur = self._obj.table_border.color
        qc = QColorDialog.getColor(QColor(cur[0], cur[1], cur[2]), self, "Border color")
        if qc.isValid():
            self._obj.table_border.color = (qc.red(), qc.green(), qc.blue(), 255)
            self.btn_table_border_color.setStyleSheet(f"background:{qc.name()};")
            self._canvas.schedule_render(); self.changed.emit()

    def _on_table_border_change(self):
        if self._loading or not isinstance(self._obj, edof.Table): return
        if self._obj.table_border:
            self._obj.table_border.width = self.sp_table_border_w.value()
            self._canvas.schedule_render(); self.changed.emit()

    def _table_struct_op(self, op):
        if self._loading or not isinstance(self._obj, edof.Table): return
        from edof.format.objects import TableCell
        t = self._obj
        if op == "add_row":
            ncols = len(t.cells[0]) if t.cells else 1
            t.cells.append([TableCell() for _ in range(ncols)])
            t.row_heights.append(0.0)
        elif op == "del_row" and len(t.cells) > 1:
            t.cells.pop()
            if t.row_heights: t.row_heights.pop()
        elif op == "add_col":
            for row in t.cells:
                row.append(TableCell())
            t.col_widths.append(0.0)
        elif op == "del_col" and t.cells and len(t.cells[0]) > 1:
            for row in t.cells:
                row.pop()
            if t.col_widths: t.col_widths.pop()
        self._canvas.schedule_render(); self.changed.emit()

    def _open_table_cell_editor(self):
        """v4.1.0: Open dialog to edit table cells (text, colors, borders, alignment)."""
        if not isinstance(self._obj, edof.Table): return
        tbl = self._obj
        from PyQt6.QtWidgets import (QTableWidget, QTableWidgetItem, QHeaderView,
                                       QAbstractItemView, QColorDialog as _QColorDialog)
        dlg = QDialog(self); dlg.setWindowTitle("Cell Editor")
        dlg.setStyleSheet(QSS); dlg.resize(900, 600)
        v = QVBoxLayout(dlg)

        # Top toolbar
        tb = QWidget(); tbh = QHBoxLayout(tb); tbh.setContentsMargins(0,0,0,0)
        lbl_info = QLabel("Click a cell to select. Use the buttons to edit colors, alignment, borders.")
        tbh.addWidget(lbl_info); tbh.addStretch()
        v.addWidget(tb)

        # Table widget for visual editing
        nrows = max(1, tbl.num_rows); ncols = max(1, tbl.num_cols)
        tw = QTableWidget(nrows, ncols)
        tw.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Populate
        for r in range(nrows):
            for c in range(ncols):
                if r < len(tbl.cells) and c < len(tbl.cells[r]):
                    cell = tbl.cells[r][c]
                    item = QTableWidgetItem(cell.text)
                    bg = cell.bg_color
                    if bg[3] > 0:
                        item.setBackground(QColor(bg[0], bg[1], bg[2], bg[3]))
                    fg = cell.style.color
                    if fg and len(fg) >= 3:
                        item.setForeground(QColor(fg[0], fg[1], fg[2]))
                    if cell.style.bold:
                        f = item.font(); f.setBold(True); item.setFont(f)
                    tw.setItem(r, c, item)
        v.addWidget(tw, 1)

        # Bottom — actions
        btn_row = QWidget(); brh = QHBoxLayout(btn_row); brh.setContentsMargins(0,0,0,0)
        btn_bg = QPushButton("Cell Background…")
        btn_fg = QPushButton("Text Color…")
        btn_bold = QPushButton("Bold")
        btn_italic = QPushButton("Italic")
        btn_align_l = QPushButton("⇤")
        btn_align_c = QPushButton("⇎")
        btn_align_r = QPushButton("⇥")
        btn_clr_borders = QPushButton("Border Color…")
        sp_border_w = QDoubleSpinBox(); sp_border_w.setRange(0, 20); sp_border_w.setSuffix(" mm"); sp_border_w.setValue(0.3); sp_border_w.setFixedWidth(80)
        for w_ in [btn_bg, btn_fg, btn_bold, btn_italic, btn_align_l, btn_align_c, btn_align_r,
                    QLabel("Border:"), btn_clr_borders, sp_border_w]:
            brh.addWidget(w_)
        brh.addStretch()
        v.addWidget(btn_row)

        def _selected_cells():
            ranges = tw.selectedRanges()
            if not ranges:
                # Use current cell only
                if tw.currentRow() >= 0 and tw.currentColumn() >= 0:
                    yield tw.currentRow(), tw.currentColumn()
                return
            for rng in ranges:
                for r in range(rng.topRow(), rng.bottomRow() + 1):
                    for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                        yield r, c

        def _pick_bg():
            qc = _QColorDialog.getColor(QColor(255,255,255), dlg, "Cell background", QColorDialog.ColorDialogOption.ShowAlphaChannel)
            if not qc.isValid(): return
            color = (qc.red(), qc.green(), qc.blue(), qc.alpha())
            for r, c in _selected_cells():
                if r < len(tbl.cells) and c < len(tbl.cells[r]):
                    tbl.cells[r][c].bg_color = color
                    item = tw.item(r, c)
                    if item: item.setBackground(qc)
        btn_bg.clicked.connect(_pick_bg)

        def _pick_fg():
            qc = _QColorDialog.getColor(QColor(0,0,0), dlg, "Text color")
            if not qc.isValid(): return
            for r, c in _selected_cells():
                if r < len(tbl.cells) and c < len(tbl.cells[r]):
                    tbl.cells[r][c].style.color = (qc.red(), qc.green(), qc.blue())
                    item = tw.item(r, c)
                    if item: item.setForeground(qc)
        btn_fg.clicked.connect(_pick_fg)

        def _toggle_bold():
            for r, c in _selected_cells():
                if r < len(tbl.cells) and c < len(tbl.cells[r]):
                    cell = tbl.cells[r][c]
                    cell.style.bold = not cell.style.bold
                    item = tw.item(r, c)
                    if item:
                        f = item.font(); f.setBold(cell.style.bold); item.setFont(f)
        btn_bold.clicked.connect(_toggle_bold)

        def _toggle_italic():
            for r, c in _selected_cells():
                if r < len(tbl.cells) and c < len(tbl.cells[r]):
                    cell = tbl.cells[r][c]
                    cell.style.italic = not cell.style.italic
                    item = tw.item(r, c)
                    if item:
                        f = item.font(); f.setItalic(cell.style.italic); item.setFont(f)
        btn_italic.clicked.connect(_toggle_italic)

        def _set_align(a):
            for r, c in _selected_cells():
                if r < len(tbl.cells) and c < len(tbl.cells[r]):
                    tbl.cells[r][c].style.alignment = a
        btn_align_l.clicked.connect(lambda: _set_align("left"))
        btn_align_c.clicked.connect(lambda: _set_align("center"))
        btn_align_r.clicked.connect(lambda: _set_align("right"))

        def _set_borders():
            qc = _QColorDialog.getColor(QColor(50,50,50), dlg, "Border color")
            if not qc.isValid(): return
            color = (qc.red(), qc.green(), qc.blue(), 255)
            width = sp_border_w.value()
            for r, c in _selected_cells():
                if r < len(tbl.cells) and c < len(tbl.cells[r]):
                    cell = tbl.cells[r][c]
                    for side in ('border_top','border_right','border_bottom','border_left'):
                        b = getattr(cell, side)
                        b.color = color
                        b.width = width
                        b.enabled = True
        btn_clr_borders.clicked.connect(_set_borders)

        # Sync text from QTableWidget back to model on cell change
        def _on_item_change(item):
            r, c = item.row(), item.column()
            if r < len(tbl.cells) and c < len(tbl.cells[r]):
                tbl.cells[r][c].text = item.text()
        tw.itemChanged.connect(_on_item_change)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject); bb.accepted.connect(dlg.accept)
        for b in bb.buttons():
            b.clicked.connect(dlg.accept)
        v.addWidget(bb)

        dlg.exec()
        self._canvas.schedule_render(); self.changed.emit()

    def _load_table(self, obj):
        """v4.1.0: Populate table panel from object."""
        self._loading = True
        try:
            border = getattr(obj, 'table_border', None)
            self.cb_table_border.setChecked(border is not None)
            if border:
                c = border.color
                self.btn_table_border_color.setStyleSheet(
                    f"background:#{c[0]:02x}{c[1]:02x}{c[2]:02x};")
                self.sp_table_border_w.setValue(border.width)
            else:
                self.btn_table_border_color.setStyleSheet("background:#ccc;")
                self.sp_table_border_w.setValue(0.5)
        finally:
            self._loading = False

    # ── v4.1.2: SubDocumentBox properties panel ─────────────────────────────
    def _mk_subdoc(self):
        """v4.1.2/4.1.7: Properties panel for embedded sub-document with
        explicit Embedded vs External mode toggle."""
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup
        w = QWidget(); fl = QFormLayout(w); fl.setContentsMargins(8, 8, 8, 6); fl.setSpacing(6)
        fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        fl.addRow(QLabel("<b>Embedded EDOF document</b>"))

        # v4.1.7: Mode toggle — Embedded vs External
        self._sd_bg = QButtonGroup(w)
        self.rb_subdoc_embedded = QRadioButton("Embedded (saved inside this .edof)")
        self.rb_subdoc_embedded.setToolTip(
            "The sub-document is stored as bytes inside this .edof file. "
            "Self-contained, easy to share, no external dependency.")
        self.rb_subdoc_external = QRadioButton("External file (link by path)")
        self.rb_subdoc_external.setToolTip(
            "The sub-document is a separate .edof file on disk. "
            "Auto-reloads when the linked file changes externally.")
        self._sd_bg.addButton(self.rb_subdoc_embedded)
        self._sd_bg.addButton(self.rb_subdoc_external)
        self.rb_subdoc_embedded.toggled.connect(self._subdoc_mode_changed)
        fl.addRow("Mode:", self.rb_subdoc_embedded)
        fl.addRow("", self.rb_subdoc_external)

        # Source display (path or "embedded as resource")
        self.le_subdoc_path = QLineEdit()
        self.le_subdoc_path.setPlaceholderText("(no source loaded yet)")
        self.le_subdoc_path.setReadOnly(True)
        fl.addRow("Source:", self.le_subdoc_path)

        # Action buttons — split across two rows for narrow panels
        rrow1 = QWidget(); rh1 = QHBoxLayout(rrow1); rh1.setContentsMargins(0,0,0,0); rh1.setSpacing(4)
        btn_load = QPushButton("Load .edof…")
        btn_load.setToolTip("Load an .edof file (mode determines whether it's embedded or linked)")
        btn_load.clicked.connect(self._subdoc_load_file)
        btn_open = QPushButton("📂 Edit")
        btn_open.setToolTip("Open the sub-document for editing in a new window")
        btn_open.clicked.connect(self._subdoc_open_in_tab)
        rh1.addWidget(btn_load); rh1.addWidget(btn_open); rh1.addStretch()
        fl.addRow("", rrow1)

        rrow2 = QWidget(); rh2 = QHBoxLayout(rrow2); rh2.setContentsMargins(0,0,0,0); rh2.setSpacing(4)
        btn_extract = QPushButton("Embedded → External")
        btn_extract.setToolTip("Save embedded bytes to an external .edof file and switch to External mode")
        btn_extract.clicked.connect(self._subdoc_extract)
        btn_inline = QPushButton("External → Embedded")
        btn_inline.setToolTip("Read external file bytes and save them inside this document")
        btn_inline.clicked.connect(self._subdoc_inline)
        rh2.addWidget(btn_extract); rh2.addWidget(btn_inline); rh2.addStretch()
        fl.addRow("", rrow2)

        self.cb_subdoc_fit = QComboBox()
        self.cb_subdoc_fit.addItems(["contain", "cover", "stretch", "none"])
        self.cb_subdoc_fit.currentTextChanged.connect(
            lambda v: self._aa('fit_mode', v) if not self._loading else None)
        fl.addRow("Fit:", self.cb_subdoc_fit)

        self.sp_subdoc_page = QSpinBox(); self.sp_subdoc_page.setRange(0, 999)
        self.sp_subdoc_page.setMinimumWidth(60)
        self.sp_subdoc_page.valueChanged.connect(
            lambda v: self._aa('page_index', v) if not self._loading else None)
        fl.addRow("Page index:", self.sp_subdoc_page)

        self.lbl_subdoc_status = QLabel(""); self.lbl_subdoc_status.setStyleSheet(f"color:{FGD};")
        self.lbl_subdoc_status.setWordWrap(True)
        fl.addRow("", self.lbl_subdoc_status)

        # Layer effects
        btn_fx = QPushButton("✨ Layer Effects…")
        btn_fx.setStyleSheet("font:bold 10pt 'Segoe UI';background:#3a3a5a;padding:6px;")
        btn_fx.clicked.connect(self._open_layer_effects_dialog)
        fl.addRow("", self._fx_actions_row(btn_fx))

        return w

    def _subdoc_mode_changed(self, embedded_checked):
        """User toggled the Embedded/External radio buttons."""
        if self._loading or not isinstance(self._obj, edof.SubDocumentBox):
            return
        # We only switch mode if the user actively chose. The actual switch
        # requires data: if going Embedded → External we need to extract the
        # bytes; External → Embedded we need to read the file. Buttons handle
        # that. Here we just hint to the user via status text.
        if embedded_checked and self._obj.source_path and not self._obj.resource_id:
            self.lbl_subdoc_status.setText(
                "<small>Click 'External → Embedded' to load the file's bytes "
                "into this document.</small>")
        elif not embedded_checked and self._obj.resource_id and not self._obj.source_path:
            self.lbl_subdoc_status.setText(
                "<small>Click 'Embedded → External' to extract the bytes to "
                "an external file.</small>")

    def _subdoc_inline(self):
        """v4.1.7: Read an external source_path file's bytes and embed them."""
        if not isinstance(self._obj, edof.SubDocumentBox): return
        if not self._obj.source_path or not os.path.isfile(self._obj.source_path):
            QMessageBox.information(self, "Inline",
                "No external file linked, or the file no longer exists on disk.")
            return
        mw = self._main_window()
        if not mw or not mw.doc: return
        try:
            with open(self._obj.source_path, "rb") as f:
                data = f.read()
            rid = mw.doc.resources.add(data,
                                          filename=os.path.basename(self._obj.source_path),
                                          mime_type="application/x-edof")
            self._obj.resource_id = rid
            self._obj.source_path = None
            self._load_subdoc(self._obj)
            self._canvas.schedule_render(); self.changed.emit()
            QMessageBox.information(self, "Inline",
                "External file embedded into this document.")
        except Exception as e:
            QMessageBox.warning(self, "Inline failed", f"Error: {e}")

    def _load_subdoc(self, obj):
        """Populate subdoc panel from object."""
        self._loading = True
        try:
            # v4.1.9: elide middle for very long paths so narrow panels
            # show "C:/path/.../file.edof" instead of cutting off the end
            def _elide_mid(s: str, max_len: int = 36) -> str:
                if len(s) <= max_len:
                    return s
                keep = (max_len - 1) // 2
                return s[:keep] + "…" + s[-keep:]

            if obj.source_path:
                self.le_subdoc_path.setText(_elide_mid(obj.source_path))
                self.le_subdoc_path.setToolTip(obj.source_path)
                status = f"<small>External file. Watching for changes on disk.</small>"
                self.rb_subdoc_external.setChecked(True)
            elif obj.resource_id:
                short = obj.resource_id[:8] if len(obj.resource_id) > 12 else obj.resource_id
                self.le_subdoc_path.setText(f"(embedded resource: {short}…)")
                self.le_subdoc_path.setToolTip(f"Full resource id: {obj.resource_id}")
                status = "<small>Embedded inside this document — fully self-contained.</small>"
                self.rb_subdoc_embedded.setChecked(True)
            else:
                self.le_subdoc_path.setText("")
                self.le_subdoc_path.setToolTip("")
                status = "<small><i>No source yet — choose Mode and click Load .edof… or open this in a new window to create.</i></small>"
                self.rb_subdoc_embedded.setChecked(True)
            self.cb_subdoc_fit.setCurrentText(obj.fit_mode)
            self.sp_subdoc_page.setValue(obj.page_index)
            self.lbl_subdoc_status.setText(status)
        finally:
            self._loading = False

    def _subdoc_load_file(self):
        """Load an .edof file. Mode (embedded vs external) follows the radio."""
        if not isinstance(self._obj, edof.SubDocumentBox): return
        fn, _ = QFileDialog.getOpenFileName(self, "Load .edof file",
                                              "", "EDOF documents (*.edof)")
        if not fn: return
        try:
            mw = self._main_window()
            if not mw or not mw.doc: return
            if self.rb_subdoc_external.isChecked():
                # External link — store path
                self._obj.source_path = fn
                self._obj.resource_id = None
            else:
                # Embedded — store bytes
                with open(fn, "rb") as f:
                    data = f.read()
                rid = mw.doc.resources.add(data,
                                              filename=os.path.basename(fn),
                                              mime_type="application/x-edof")
                self._obj.resource_id = rid
                self._obj.source_path = None
            self._load_subdoc(self._obj)
            self._canvas.schedule_render(); self.changed.emit()
            # Refresh main window's file watcher for new external paths
            if hasattr(mw, '_refresh_subdoc_watcher'):
                mw._refresh_subdoc_watcher()
        except Exception as e:
            QMessageBox.warning(self, "Load failed", f"Could not load file:\n{e}")

    def _subdoc_open_in_tab(self):
        """v4.1.2: Open the embedded document in a new editor tab."""
        if not isinstance(self._obj, edof.SubDocumentBox): return
        mw = self._main_window()
        if not mw: return
        # Delegate to main window's tab manager
        mw._open_subdoc_in_tab(self._obj)

    def _subdoc_extract(self):
        """Save embedded bytes to external file and switch to source_path mode."""
        if not isinstance(self._obj, edof.SubDocumentBox): return
        if not self._obj.resource_id:
            QMessageBox.information(self, "Extract", "Already external (or no resource loaded).")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save embedded .edof to file",
                                              "embedded.edof", "EDOF documents (*.edof)")
        if not fn: return
        mw = self._main_window()
        if not mw or not mw.doc: return
        try:
            entry = mw.doc.resources.get(self._obj.resource_id)
            if not entry: return
            with open(fn, "wb") as f:
                f.write(entry.data)
            # Switch to external mode
            self._obj.source_path = fn
            self._obj.resource_id = None
            self._load_subdoc(self._obj)
            QMessageBox.information(self, "Extract",
                                      f"Extracted to {fn}. Now linked externally.")
        except Exception as e:
            QMessageBox.warning(self, "Extract failed", f"Error: {e}")

    # ── Load ─────────────────────────────────────────────────────────────────

    def load(self,obj):
        self._loading=True; self._obj=obj
        try:
            if obj is None:
                # v4.1.7/4.1.9: hide everything except the empty-state hint
                self._g_tf.setVisible(False)
                self._coll_lock.setVisible(False)
                self._coll_obj.setVisible(False)
                self._stack.setCurrentIndex(0)
                return
            # v4.1.7/4.1.9: show the groups now that we have a selection
            self._g_tf.setVisible(True)
            self._coll_lock.setVisible(True)
            self._coll_obj.setVisible(True)
            t_=obj.transform
            self.sp_x.setValue(round(t_.x,3)); self.sp_y.setValue(round(t_.y,3))
            self.sp_w.setValue(round(t_.width,3)); self.sp_h.setValue(round(t_.height,3))
            self.sp_rot.setValue(round(t_.rotation,2))
            # v4.1.9.1/4.1.10: stacking order display — show position among
            # siblings sorted by .layer (which IS the actual stacking key)
            try:
                page = self._canvas._cur_page()
                if page and obj in page.objects:
                    s = page.sorted_objects()
                    idx = s.index(obj) + 1  # 1-based, bottom=1
                    total = len(s)
                    self.lbl_layer.setText(f"{idx} / {total}")
                else:
                    self.lbl_layer.setText("—")
            except Exception:
                self.lbl_layer.setText("—")
            self.le_name.setText(obj.name or ""); self.le_var.setText(obj.variable or "")
            self.le_tags.setText(", ".join(obj.tags))
            self.cb_locked.setChecked(obj.locked)
            self.cb_editable.setChecked(getattr(obj,'editable',True))
            self.cb_visible.setChecked(obj.visible)
            self.lbl_info.setText(f"ID: {obj.id[:24]}…  Type: {obj.OBJECT_TYPE}")

            # v4.0.3/4.1.3: load visibility & locking fields
            self.le_visible_if.blockSignals(True)
            self.le_visible_if.setText(getattr(obj, 'visible_if', '') or '')
            self.le_visible_if.blockSignals(False)
            ll = getattr(obj, 'lock_level', '') or ''
            self.cb_lock_level.blockSignals(True)
            idx = max(0, ["", "fill", "edit", "design", "admin"].index(ll)) if ll in ("","fill","edit","design","admin") else 0
            self.cb_lock_level.setCurrentIndex(idx)
            self.cb_lock_level.blockSignals(False)
            self.cb_lock_text.blockSignals(True)
            self.cb_lock_text.setChecked(bool(getattr(obj, 'lock_text', False)))
            self.cb_lock_text.blockSignals(False)
            self.cb_lock_position.blockSignals(True)
            self.cb_lock_position.setChecked(bool(getattr(obj, 'lock_position', False)))
            self.cb_lock_position.blockSignals(False)
            # v4.1.3: blend_mode + opacity loaded only inside Layer Effects dialog
            # (was duplicated in Advanced section)

            from edof.format.objects import Shape,SHAPE_LINE
            if self._canvas._is_document_body(obj):
                # v4.2.11.41: the body has no useful per-object properties;
                # show document page setup (margins / size / header-footer).
                self._load_pagesetup(obj); self._stack.setCurrentIndex(8)
            elif isinstance(obj,edof.TextBox):     self._load_tb(obj); self._stack.setCurrentIndex(1)
            elif isinstance(obj,edof.ImageBox):    self._load_img(obj); self._stack.setCurrentIndex(2)
            elif isinstance(obj, edof.Table):      self._load_table(obj); self._stack.setCurrentIndex(6)
            elif isinstance(obj, edof.SubDocumentBox):
                self._load_subdoc(obj); self._stack.setCurrentIndex(7)
            elif isinstance(obj,Shape) and obj.shape_type==SHAPE_LINE:
                self._load_line(obj); self._stack.setCurrentIndex(5)
            elif isinstance(obj,Shape):            self._load_shape(obj); self._stack.setCurrentIndex(3)
            elif isinstance(obj,edof.QRCode):      self._load_qr(obj); self._stack.setCurrentIndex(4)
            elif hasattr(edof, 'SvgBox') and isinstance(obj, edof.SvgBox):
                # v4.1.17.1: SvgBox uses the image panel for opacity, blend_mode,
                # layer effects. ImageBox-specific fields (resource picker)
                # remain inert when no image is attached.
                self._load_img(obj); self._stack.setCurrentIndex(2)
            else:                                  self._stack.setCurrentIndex(0)
            # v4.1.23.37: the document BODY is not a place for per-object text
            # effects (those belong to inserted text boxes). When it's selected
            # hide the Layer Effects button and show an explanatory note.
            try:
                is_body = False
                try:
                    is_body = bool(self._canvas._is_document_body(obj))
                except Exception:
                    is_body = (getattr(obj, 'name', '') == 'document_body')
                if hasattr(self, '_btn_fx_tb'):
                    self._btn_fx_tb.setVisible(not is_body)
                if hasattr(self, '_lbl_body_note'):
                    self._lbl_body_note.setVisible(is_body)
            except Exception:
                pass
        finally: self._loading=False

    def _load_tb(self,obj):
        s=obj.style
        self.te_text.blockSignals(True); self.te_text.setPlainText(obj.text); self.te_text.blockSignals(False)
        self.cb_font.blockSignals(True); self.cb_font.setCurrentText(s.font_family); self.cb_font.blockSignals(False)
        self.sp_fsize.setValue(round(s.font_size,2)); self.sp_minfs.setValue(round(s.min_font_size,2))
        # v4.1.17: max_font_size + ∞ checkbox
        is_inf = s.max_font_size > 9999
        self.cb_maxfs_inf.blockSignals(True); self.cb_maxfs_inf.setChecked(is_inf); self.cb_maxfs_inf.blockSignals(False)
        self.sp_maxfs.setEnabled(not is_inf)
        if not is_inf:
            self.sp_maxfs.setValue(round(s.max_font_size, 2))
        self.sp_lh.setValue(round(s.line_height,2))
        self.cb_align.setCurrentText(s.alignment); self.cb_valign.setCurrentText(s.vertical_align)
        self.btn_color.setStyleSheet(_cswatch((*s.color[:3],255)))
        for attr in ('bold','italic','underline','strikethrough','wrap','overflow_hidden'):
            getattr(self,f'cb_{attr}').blockSignals(True)
            getattr(self,f'cb_{attr}').setChecked(getattr(s,attr,False))
            getattr(self,f'cb_{attr}').blockSignals(False)
        self.rb_fixed.blockSignals(True); self.rb_shrink.blockSignals(True); self.rb_fill.blockSignals(True)
        if s.auto_fill: self.rb_fill.setChecked(True)
        elif s.auto_shrink: self.rb_shrink.setChecked(True)
        else: self.rb_fixed.setChecked(True)
        for rb in (self.rb_fixed,self.rb_shrink,self.rb_fill): rb.blockSignals(False)

    def _load_img(self,obj):
        self.cb_fit.blockSignals(True); self.cb_fit.setCurrentText(getattr(obj,'fit_mode','contain'))
        self.cb_fit.blockSignals(False)

    def _load_shape(self,obj):
        # v4.1.3: shape_type combo (moved from Advanced)
        self.cb_shape_type.blockSignals(True)
        self.cb_shape_type.setCurrentText(obj.shape_type)
        self.cb_shape_type.blockSignals(False)
        self.btn_fill.setStyleSheet(_cswatch(obj.fill.color or (200,200,200,255)))
        c=obj.fill.color; a=int(c[3]/255*100) if c and len(c)==4 else 100
        self.lbl_fill_a.setText(f"{a}%")
        self.btn_stroke.setStyleSheet(_cswatch(obj.stroke.color or (0,0,0,255)))
        self.sp_sw.setValue(getattr(obj.stroke,'width',1)); self.sp_cr.setValue(getattr(obj,'corner_radius',0))
        _rr=getattr(obj,'corner_radii',[]) or []
        if len(_rr)==4: _cv=_rr
        else: _cv=[getattr(obj,'corner_radius',0)]*4
        for _s,_val in zip((self.sp_cr_tl,self.sp_cr_tr,self.sp_cr_br,self.sp_cr_bl),_cv):
            _s.blockSignals(True); _s.setValue(_val); _s.blockSignals(False)

    def _load_qr(self,obj):
        self.le_qr.blockSignals(True); self.le_qr.setText(obj.data); self.le_qr.blockSignals(False)
        self.cb_ec.setCurrentText(obj.error_correction); self.sp_qr_brd.setValue(obj.border_modules)
        for attr in ('fg_color','bg_color'):
            c=getattr(obj,attr,(0,0,0,255))
            getattr(self,f'btn_qr_{attr}').setStyleSheet(_cswatch(c))
            a=int(c[3]/255*100) if len(c)==4 else 100
            getattr(self,f'lbl_qr_{attr}_a').setText(f"{a}%")

    def _load_line(self,obj):
        pts=obj.points if obj.points and len(obj.points)>=2 else [[0,0],[50,50]]
        self.sp_lx1.setValue(pts[0][0]); self.sp_ly1.setValue(pts[0][1])
        self.sp_lx2.setValue(pts[1][0]); self.sp_ly2.setValue(pts[1][1])
        self.btn_lstroke.setStyleSheet(_cswatch(obj.stroke.color or (0,0,0,255)))
        self.sp_lsw.setValue(getattr(obj.stroke,'width',1))

    # ── Apply ─────────────────────────────────────────────────────────────────

    def _atf(self,key,val):
        if self._loading or not self._obj: return
        setattr(self._obj.transform,key,val)
        self._canvas._refresh_overlay(); self._canvas.schedule_render(); self.changed.emit()

    def _aa(self,key,val):
        if self._loading or not self._obj: return
        setattr(self._obj,key,val); self._canvas.schedule_render(); self.changed.emit()

    def _aa_obj(self,key,val):
        if self._loading or not self._obj: return
        setattr(self._obj,key,val); self._canvas.schedule_render(); self.changed.emit()

    def _apply_corner_uniform(self):
        # master spin -> all corners equal (uniform); clears per-corner override
        if self._loading or not self._obj: return
        v=self.sp_cr.value()
        self._obj.corner_radius=v
        self._obj.corner_radii=[]
        for s in (self.sp_cr_tl,self.sp_cr_tr,self.sp_cr_br,self.sp_cr_bl):
            s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        self._canvas.schedule_render(); self.changed.emit()

    def _apply_corner_each(self):
        # per-corner spins -> corner_radii [TL,TR,BR,BL]
        if self._loading or not self._obj: return
        self._obj.corner_radii=[self.sp_cr_tl.value(),self.sp_cr_tr.value(),
                                self.sp_cr_br.value(),self.sp_cr_bl.value()]
        self._canvas.schedule_render(); self.changed.emit()

    def _as(self,key,val,typ):
        if self._loading or not isinstance(self._obj,edof.TextBox): return
        try: setattr(self._obj.style,key,typ(val))
        except Exception: return
        # v4.1.19.8: if the inline editor is currently editing THIS textbox,
        # invalidate its cached pixmap so style changes (auto_fill,
        # max_font_size, font_size, etc.) take effect immediately rather
        # than waiting until edit mode exits.
        try:
            inl = getattr(self._canvas, '_inline_widget', None)
            inl_obj = getattr(self._canvas, '_inline_obj', None)
            if inl is not None and inl_obj is self._obj:
                inl._invalidate()
        except Exception:
            pass
        self._canvas.schedule_render(); self.changed.emit()

    def _apply_scale(self):
        if not self._obj: return
        self._obj.transform.resize_uniform(self.sp_scale.value())
        self.load(self._obj); self._canvas._refresh_overlay()
        self._canvas.schedule_render(); self.changed.emit()

    def _flip(self,axis):
        if not self._obj: return
        if axis=='h': self._obj.transform.flip_horizontal()
        else:         self._obj.transform.flip_vertical()
        self._canvas.schedule_render(); self.changed.emit()

    # v4.0.3: advanced property handlers
    def _on_lock_level(self, txt):
        if self._loading or not self._obj: return
        val = "" if txt == "(none)" else txt
        self._obj.lock_level = val
        self.changed.emit()

    def _on_shape_type(self, txt):
        if self._loading or not self._obj: return
        from edof.format.objects import Shape, SHAPE_PATH
        if not isinstance(self._obj, Shape): return
        old = self._obj.shape_type
        if old == txt: return
        # v4.1.1: meaningful conversions only
        # - rect/ellipse/polygon/arrow → path: convert to path_data so renderer keeps drawing
        # - path → rect/ellipse: keep bbox, drop curve detail (warn)
        # - line cannot convert (different data layout)
        if txt == 'path' and old != 'path':
            self._obj.path_data = self._convert_shape_to_path_data(self._obj, old)
        elif old == 'path' and txt != 'path':
            ret = QMessageBox.question(self, "Convert shape",
                f"Converting from path to {txt} will discard the curve detail "
                f"and use the bounding box. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                # Revert combo
                self.cb_shape_type.blockSignals(True)
                self.cb_shape_type.setCurrentText(old)
                self.cb_shape_type.blockSignals(False)
                return
            self._obj.path_data = []
        self._obj.shape_type = txt
        self._canvas.schedule_render(); self.changed.emit()

    def _convert_shape_to_path_data(self, obj, src_type):
        """v4.1.1: Convert a built-in shape to path_data so it renders as a path.

        Coordinates are local (relative to obj.transform.x/y), bounded by
        obj.transform.width × obj.transform.height.
        """
        w = obj.transform.width; h = obj.transform.height
        if src_type == 'rect':
            return [
                ["M", 0, 0],
                ["L", w, 0],
                ["L", w, h],
                ["L", 0, h],
                ["Z"],
            ]
        elif src_type == 'ellipse':
            # Approximate ellipse with 4 cubic Bezier curves (kappa = 0.5522847498)
            k = 0.5522847498 * (w / 2)
            ky = 0.5522847498 * (h / 2)
            cx, cy = w / 2, h / 2
            return [
                ["M", cx, 0],
                ["C", cx + k, 0, w, cy - ky, w, cy],
                ["C", w, cy + ky, cx + k, h, cx, h],
                ["C", cx - k, h, 0, cy + ky, 0, cy],
                ["C", 0, cy - ky, cx - k, 0, cx, 0],
                ["Z"],
            ]
        elif src_type == 'arrow':
            # Simple arrow shape: shaft + arrowhead in the bbox
            head_w = min(w * 0.3, h * 0.5)
            shaft_h = h * 0.3
            return [
                ["M", 0, h / 2 - shaft_h / 2],
                ["L", w - head_w, h / 2 - shaft_h / 2],
                ["L", w - head_w, 0],
                ["L", w, h / 2],
                ["L", w - head_w, h],
                ["L", w - head_w, h / 2 + shaft_h / 2],
                ["L", 0, h / 2 + shaft_h / 2],
                ["Z"],
            ]
        elif src_type == 'polygon':
            # Use existing polygon points if any, else default triangle
            pts = getattr(obj, 'polygon_points', None)
            if pts and len(pts) >= 2:
                pd = [["M", pts[0][0], pts[0][1]]]
                for p in pts[1:]:
                    pd.append(["L", p[0], p[1]])
                pd.append(["Z"])
                return pd
            return [
                ["M", w / 2, 0],
                ["L", w, h],
                ["L", 0, h],
                ["Z"],
            ]
        # Fallback: rect
        return [["M", 0, 0], ["L", w, 0], ["L", w, h], ["L", 0, h], ["Z"]]

    # v4.1.1: Layer effects dialog (Photoshop-style)
    # ─────────────────────────────────────────────────────────────────────
    # v4.1.1: Layer Effects dialog — Photoshop-style with per-effect params
    # ─────────────────────────────────────────────────────────────────────
    def _open_layer_effects_dialog(self):
        if not self._obj:
            return
        from copy import deepcopy
        from edof.format.styles import LayerEffect
        from PyQt6.QtWidgets import (QListWidget, QListWidgetItem, QStackedWidget,
                                       QGroupBox, QSplitter, QSlider, QFrame)

        # Snapshot for cancel
        original_effects = deepcopy(self._obj.effects)
        original_blend = getattr(self._obj, 'blend_mode', 'normal')
        original_opacity = getattr(self._obj, 'opacity', 1.0)

        # Effect types in order; first one is Blending Options (special)
        EFFECT_LIST = [
            ('blending',         '⚙ Blending Options'),
            ('drop_shadow',      'Drop Shadow'),
            ('inner_shadow',     'Inner Shadow'),
            ('outer_glow',       'Outer Glow'),
            ('inner_glow',       'Inner Glow'),
            ('bevel',            'Bevel & Emboss'),
            ('stroke',           'Stroke'),
            ('color_overlay',    'Color Overlay'),
            ('gradient_overlay', 'Gradient Overlay'),
            ('texture_overlay',  'Texture Overlay'),
            ('long_shadow',          'Long Shadow'),
            ('chromatic_aberration', 'Chromatic Aberration'),
            ('halftone',             'Halftone'),
            ('light_sweep',          'Light Sweep'),
        ]
        BLEND_MODES = [
            'normal','multiply','screen','overlay','darken','lighten',
            'color_dodge','color_burn','hard_light','soft_light',
            'difference','exclusion','hue','saturation','color','luminosity',
        ]

        # v4.2.7.9: instance model — effects are a list of instances (so the
        # same type can appear more than once, be duplicated and reordered).
        DISPLAY = {
            'drop_shadow': 'Drop Shadow', 'inner_shadow': 'Inner Shadow',
            'outer_glow': 'Outer Glow', 'inner_glow': 'Inner Glow',
            'bevel': 'Bevel & Emboss', 'stroke': 'Stroke',
            'color_overlay': 'Color Overlay', 'gradient_overlay': 'Gradient Overlay',
            'texture_overlay': 'Texture Overlay', 'long_shadow': 'Long Shadow',
            'chromatic_aberration': 'Chromatic Aberration', 'halftone': 'Halftone',
            'light_sweep': 'Light Sweep',
        }
        ADD_TYPES = [et for et, _ in EFFECT_LIST if et != 'blending']

        def _make_default(et):
            e = LayerEffect(type=et, enabled=True)
            if et == 'drop_shadow':
                e.color = (0, 0, 0, 220); e.opacity = 0.7
                e.size = 2.0; e.distance = 2.0; e.direction = 315.0
                e.blend_mode = 'multiply'
            elif et == 'inner_shadow':
                e.color = (0, 0, 0, 220); e.opacity = 0.7
                e.size = 2.0; e.distance = 2.0; e.direction = 315.0
                e.blend_mode = 'multiply'
            elif et == 'outer_glow':
                e.color = (255, 255, 200, 255); e.opacity = 0.6
                e.size = 4.0; e.blend_mode = 'screen'
            elif et == 'inner_glow':
                e.color = (255, 255, 200, 255); e.opacity = 0.6
                e.size = 4.0; e.blend_mode = 'screen'
            elif et == 'bevel':
                e.color = (0, 0, 0, 200); e.color2 = (255, 255, 255, 255)
                e.size = 3.0; e.direction = 135.0; e.bevel_kind = 'inner'
            elif et == 'stroke':
                e.color = (0, 0, 0, 255); e.size = 1.0
                e.stroke_position = 'outside'
            elif et == 'color_overlay':
                e.color = (255, 0, 0, 255); e.opacity = 1.0
                e.blend_mode = 'normal'
            elif et == 'gradient_overlay':
                e.gradient_start = (0, 0, 0, 255); e.gradient_end = (255, 255, 255, 255)
                e.gradient_angle = 90.0; e.opacity = 1.0
            elif et == 'texture_overlay':
                e.opacity = 1.0; e.blend_mode = 'multiply'
            elif et == 'long_shadow':
                e.color = (0, 0, 0, 180); e.direction = 315.0
                e.ls_length = 10.0; e.ls_fade = True; e.opacity = 0.7
                e.blend_mode = 'normal'
            elif et == 'chromatic_aberration':
                e.ca_offset = 0.5; e.ca_angle = 0.0; e.opacity = 1.0
                e.blend_mode = 'normal'
            elif et == 'halftone':
                e.color = (0, 0, 0, 255); e.ht_dot = 1.5
                e.ht_angle = 72.0; e.ht_shape = 'dot'; e.opacity = 1.0
                e.blend_mode = 'normal'
            elif et == 'light_sweep':
                e.color2 = (255, 255, 255, 255); e.lsw_pos = 0.5
                e.lsw_width = 0.3; e.lsw_angle = 45.0; e.opacity = 0.6
                e.blend_mode = 'screen'
            return e

        # working: key -> LayerEffect; order: [key,...] render order
        working = {}
        order = []
        _key_counter = [0]
        def _new_key(et):
            _key_counter[0] += 1
            return f"{et}#{_key_counter[0]}"
        for _e in self._obj.effects:
            _k = _new_key(_e.type); working[_k] = deepcopy(_e); order.append(_k)

        dlg = QDialog(self); dlg.setWindowTitle("Layer Style")
        # v4.2.7.6: modern, clearer styling for the effects dialog
        dlg.setStyleSheet(QSS + """
            QDialog { background:#15161a; }
            QListWidget { background:#1b1d23; border:1px solid #2a2d36; border-radius:8px;
                          padding:4px; outline:0; }
            QListWidget::item { padding:7px 10px; border-radius:6px; margin:1px 2px; color:#cfd2da; }
            QListWidget::item:hover { background:#23262f; }
            QListWidget::item:selected { background:#2a6cf0; color:#ffffff; }
            QGroupBox { border:1px solid #2a2d36; border-radius:8px; margin-top:14px;
                        padding:10px 12px 12px 12px; background:#1b1d23; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 4px; color:#9aa0ad; }
            QScrollArea { border:0; background:transparent; }
            QSlider::groove:horizontal { height:4px; background:#2a2d36; border-radius:2px; }
            QSlider::handle:horizontal { width:14px; background:#2a6cf0; border-radius:7px; margin:-6px 0; }
            QSlider::sub-page:horizontal { background:#2a6cf0; border-radius:2px; }
        """)
        dlg.resize(820, 640)
        v = QVBoxLayout(dlg); v.setSpacing(8); v.setContentsMargins(10, 10, 10, 10)

        # Top header: master enable
        hdr = QHBoxLayout()
        cb_master = QCheckBox("Effects enabled")
        cb_master.setStyleSheet("font-weight:bold;")
        cb_master.setChecked(any(e.enabled for e in self._obj.effects))
        hdr.addWidget(cb_master)
        hdr.addStretch()
        v.addLayout(hdr)

        # Splitter: left list, right stack
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle{background:#444;}")

        # Left: effects list (instances) with checkboxes + drag-to-reorder
        from PyQt6.QtWidgets import QAbstractItemView
        list_w = QListWidget()
        list_w.setMinimumWidth(200)
        list_w.setMaximumWidth(250)
        list_w.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        list_w.setDefaultDropAction(Qt.DropAction.MoveAction)
        UR = Qt.ItemDataRole.UserRole
        item_by_key = {}
        _rebuilding = [False]

        def _label_for(key):
            t = working[key].type
            base = DISPLAY.get(t, t)
            same = [k for k in order if working[k].type == t]
            return f"{base} {same.index(key)+1}" if len(same) > 1 else base

        def _mk_item(key):
            it = QListWidgetItem(_label_for(key)); it.setData(UR, key)
            it.setFlags((it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        & ~Qt.ItemFlag.ItemIsDropEnabled)
            it.setCheckState(Qt.CheckState.Checked if working[key].enabled
                             else Qt.CheckState.Unchecked)
            return it

        def _blend_item():
            it = QListWidgetItem("⚙ Blending Options"); it.setData(UR, '__blend__')
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            return it

        def _rebuild_list(keep_key=None):
            _rebuilding[0] = True
            list_w.blockSignals(True)
            if keep_key is None:
                ci = list_w.currentItem()
                keep_key = ci.data(UR) if ci else '__blend__'
            list_w.clear(); item_by_key.clear()
            list_w.addItem(_blend_item())
            for k in order:
                it = _mk_item(k); item_by_key[k] = it; list_w.addItem(it)
            target = 0
            for r in range(list_w.count()):
                if list_w.item(r).data(UR) == keep_key:
                    target = r; break
            list_w.setCurrentRow(target)
            list_w.blockSignals(False)
            _rebuilding[0] = False
        splitter.addWidget(list_w)

        # Right: stack of parameter widgets (built lazily per instance)
        stack = QStackedWidget()
        param_widgets = {}

        # Helper builders
        def _color_btn(initial_color):
            btn = QPushButton(); btn.setFixedSize(40, 24)
            btn.setStyleSheet(
                f"background:#{initial_color[0]:02x}{initial_color[1]:02x}{initial_color[2]:02x};"
                "border:1px solid #888;border-radius:3px;")
            return btn

        def _blend_combo(initial='normal'):
            cb = QComboBox(); cb.addItems(BLEND_MODES); cb.setCurrentText(initial)
            return cb

        def _slider_pct(initial=100):
            s = QSlider(Qt.Orientation.Horizontal); s.setRange(0, 100); s.setValue(int(initial))
            s.setMinimumWidth(160)
            return s

        def _spin(lo, hi, val, suffix='', dec=2):
            sp = QDoubleSpinBox(); sp.setRange(lo, hi); sp.setValue(val); sp.setDecimals(dec); sp.setSuffix(suffix)
            # v4.2.5: mm fields step by 0.1 mm (was 1.0); angles/percent keep 1.
            sp.setSingleStep(0.1 if suffix.strip() == 'mm' else 1.0)
            sp.setFixedWidth(110)
            return sp

        def _mm(val, mx=100.0, lo=0.0, dec=2, suffix=' mm'):
            # v4.2.7.10: mm fields are slider + number + adjustable max (no cap)
            return _MmField(value=val, maximum=mx, decimals=dec, suffix=suffix, minimum=lo)

        def _live():
            # Apply current instance list to obj (enabled, in order)
            new_effects = [deepcopy(working[k]) for k in order
                           if working[k].enabled and cb_master.isChecked()]
            self._obj.effects = new_effects
            self._canvas.schedule_render_interactive(30)

        # ── Page 0: Blending Options ─────────────────────────────────────────
        w_blend = QWidget(); fl_blend = QFormLayout(w_blend); fl_blend.setSpacing(10)
        fl_blend.setContentsMargins(20, 20, 20, 20)
        title_blend = QLabel("<h3>Blending Options</h3>"); fl_blend.addRow(title_blend)
        cb_blend_mode = _blend_combo(original_blend)
        sl_opacity = _slider_pct(int(original_opacity * 100))
        lbl_op_val = QLabel(f"{int(original_opacity*100)}%"); lbl_op_val.setFixedWidth(40)
        op_row = QWidget(); op_h = QHBoxLayout(op_row); op_h.setContentsMargins(0,0,0,0)
        op_h.addWidget(sl_opacity); op_h.addWidget(lbl_op_val)
        # v4.1.1: fill opacity (Photoshop) — affects only object pixels, not effects
        original_fill_op = getattr(self._obj, 'fill_opacity', original_opacity)
        sl_fill = _slider_pct(int(original_fill_op * 100))
        lbl_fill_val = QLabel(f"{int(original_fill_op*100)}%"); lbl_fill_val.setFixedWidth(40)
        fill_row = QWidget(); fill_h = QHBoxLayout(fill_row); fill_h.setContentsMargins(0,0,0,0)
        fill_h.addWidget(sl_fill); fill_h.addWidget(lbl_fill_val)
        fl_blend.addRow("Blend mode:", cb_blend_mode)
        fl_blend.addRow("Opacity:", op_row)
        fl_blend.addRow("Fill opacity:", fill_row)
        info = QLabel("<small><b>Opacity</b> affects entire layer (object + effects).<br>"
                       "<b>Fill opacity</b> affects only the object pixels — drop shadow, "
                       "glow, stroke, etc. remain at full strength.</small>")
        info.setWordWrap(True); info.setStyleSheet(f"color:{FGD};")
        fl_blend.addRow("", info)

        def _on_blend_change():
            self._obj.blend_mode = cb_blend_mode.currentText()
            self._canvas.schedule_render_interactive(30)
        def _on_opacity_change(v):
            self._obj.opacity = v / 100.0
            lbl_op_val.setText(f"{v}%")
            self._canvas.schedule_render_interactive(30)
        def _on_fill_change(v):
            self._obj.fill_opacity = v / 100.0
            lbl_fill_val.setText(f"{v}%")
            self._canvas.schedule_render_interactive(30)
        cb_blend_mode.currentTextChanged.connect(lambda _: _on_blend_change())
        sl_opacity.valueChanged.connect(_on_opacity_change)
        sl_fill.valueChanged.connect(_on_fill_change)

        # ── Build a parameter widget for each effect type ─────────────────────
        def _enable_in_list(et):
            # 'et' is now an instance key
            working[et].enabled = True
            it = item_by_key.get(et)
            if it is not None and it.checkState() != Qt.CheckState.Checked:
                it.setCheckState(Qt.CheckState.Checked)

        def _build_shadow_page(et, is_inner):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(8); fl.setContentsMargins(20, 20, 20, 20)
            title = QLabel(f"<h3>{'Inner' if is_inner else 'Drop'} Shadow</h3>")
            fl.addRow(title)
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); op_h = QHBoxLayout(op_row); op_h.setContentsMargins(0,0,0,0)
            op_h.addWidget(sl_op); op_h.addWidget(lbl_op)
            btn_c = _color_btn(working[et].color)
            sp_dir = _spin(0, 360, working[et].direction, '°', 0)
            sp_dist = _mm(working[et].distance, 100)
            sp_size = _mm(working[et].size, 100)

            fl.addRow("Blend mode:", cb_bm)
            fl.addRow("Opacity:", op_row)
            fl.addRow("Color:", btn_c)
            fl.addRow("Angle:", sp_dir)
            fl.addRow("Distance:", sp_dist)
            sl_spread = _slider_pct(int(working[et].spread * 100))
            lbl_sp = QLabel(f"{int(working[et].spread*100)}%"); lbl_sp.setFixedWidth(40)
            sp_row = QWidget(); sph = QHBoxLayout(sp_row); sph.setContentsMargins(0,0,0,0)
            sph.addWidget(sl_spread); sph.addWidget(lbl_sp)
            fl.addRow("Size (blur):", sp_size)
            fl.addRow("Choke:" if is_inner else "Spread:", sp_row)

            def _commit():
                working[et].blend_mode = cb_bm.currentText()
                working[et].opacity = sl_op.value() / 100.0
                working[et].direction = sp_dir.value()
                working[et].distance = sp_dist.value()
                working[et].size = sp_size.value()
                working[et].spread = sl_spread.value() / 100.0
                _enable_in_list(et); _live()
            def _on_sp(v):
                lbl_sp.setText(f"{v}%"); _commit()
            def _on_op(v):
                lbl_op.setText(f"{v}%"); _commit()
            def _pick_c():
                from PyQt6.QtWidgets import QColorDialog
                c = working[et].color
                _orig_c = working[et].color
                def _prev_c(col):
                    working[et].color = col; _live()
                new_c = EdofColorDialog.get_color(dlg, c if len(c)>=4 else (*c[:3],255), alpha=True, on_change=_prev_c)
                if new_c is not None:
                    working[et].color = new_c
                    hex_rgb = f"#{new_c[0]:02x}{new_c[1]:02x}{new_c[2]:02x}"
                    btn_c.setStyleSheet(f"background:{hex_rgb};border:1px solid #888;border-radius:3px;")
                    _enable_in_list(et); _live()
                else:
                    working[et].color = _orig_c; _live()
            cb_bm.currentTextChanged.connect(lambda _: _commit())
            sl_op.valueChanged.connect(_on_op)
            sp_dir.valueChanged.connect(lambda _: _commit())
            sp_dist.valueChanged.connect(lambda _: _commit())
            sp_size.valueChanged.connect(lambda _: _commit())
            sl_spread.valueChanged.connect(_on_sp)
            btn_c.clicked.connect(_pick_c)
            return w

        def _build_glow_page(et, is_inner):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(8); fl.setContentsMargins(20, 20, 20, 20)
            title = QLabel(f"<h3>{'Inner' if is_inner else 'Outer'} Glow</h3>")
            fl.addRow(title)
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); op_h = QHBoxLayout(op_row); op_h.setContentsMargins(0,0,0,0)
            op_h.addWidget(sl_op); op_h.addWidget(lbl_op)
            btn_c = _color_btn(working[et].color)
            sp_size = _mm(working[et].size, 100)

            fl.addRow("Blend mode:", cb_bm)
            fl.addRow("Opacity:", op_row)
            fl.addRow("Color:", btn_c)
            sl_spread = _slider_pct(int(working[et].spread * 100))
            lbl_sp = QLabel(f"{int(working[et].spread*100)}%"); lbl_sp.setFixedWidth(40)
            sp_row = QWidget(); sph = QHBoxLayout(sp_row); sph.setContentsMargins(0,0,0,0)
            sph.addWidget(sl_spread); sph.addWidget(lbl_sp)
            fl.addRow("Size:", sp_size)
            fl.addRow("Choke:" if is_inner else "Spread:", sp_row)

            def _commit():
                working[et].blend_mode = cb_bm.currentText()
                working[et].opacity = sl_op.value() / 100.0
                working[et].size = sp_size.value()
                working[et].spread = sl_spread.value() / 100.0
                _enable_in_list(et); _live()
            def _on_sp(v):
                lbl_sp.setText(f"{v}%"); _commit()
            def _on_op(v):
                lbl_op.setText(f"{v}%"); _commit()
            def _pick_c():
                from PyQt6.QtWidgets import QColorDialog
                c = working[et].color
                _orig_c = working[et].color
                def _prev_c(col):
                    working[et].color = col; _live()
                new_c = EdofColorDialog.get_color(dlg, c if len(c)>=4 else (*c[:3],255), alpha=True, on_change=_prev_c)
                if new_c is not None:
                    working[et].color = new_c
                    hex_rgb = f"#{new_c[0]:02x}{new_c[1]:02x}{new_c[2]:02x}"
                    btn_c.setStyleSheet(f"background:{hex_rgb};border:1px solid #888;border-radius:3px;")
                    _enable_in_list(et); _live()
                else:
                    working[et].color = _orig_c; _live()
            cb_bm.currentTextChanged.connect(lambda _: _commit())
            sl_op.valueChanged.connect(_on_op)
            sp_size.valueChanged.connect(lambda _: _commit())
            sl_spread.valueChanged.connect(_on_sp)
            btn_c.clicked.connect(_pick_c)
            return w

        def _build_bevel_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(7); fl.setContentsMargins(20, 14, 20, 14)
            fl.addRow(QLabel("<h3>Bevel & Emboss</h3>"))
            cb_kind = QComboBox(); cb_kind.addItems(['inner', 'outer', 'emboss', 'smooth'])
            cb_kind.setCurrentText(working[et].bevel_kind)
            cb_tech = QComboBox(); cb_tech.addItems(['smooth', 'chisel_hard', 'chisel_soft'])
            cb_tech.setCurrentText(getattr(working[et], 'bevel_technique', 'smooth') or 'smooth')
            cb_dir = QComboBox(); cb_dir.addItems(['up', 'down'])
            cb_dir.setCurrentText(getattr(working[et], 'bevel_dir', 'up') or 'up')
            sp_size = _mm(working[et].size, 50)
            sp_soft = _mm(getattr(working[et], 'soften', 0.0), 30)
            def _vslider(lo, hi, val, suffix=''):
                sl = QSlider(Qt.Orientation.Horizontal); sl.setRange(lo, hi)
                sl.setValue(int(val)); sl.setMinimumWidth(150)
                lb = QLabel(f"{int(val)}{suffix}"); lb.setFixedWidth(52)
                row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0,0,0,0)
                h.addWidget(sl); h.addWidget(lb)
                return sl, lb, row
            sl_depth, lbl_depth, depth_row = _vslider(0, 1000, getattr(working[et], 'bevel_depth', 100.0), '%')
            sl_dir, lbl_dir, dir_row = _vslider(0, 360, working[et].direction, '°')
            sl_alt, lbl_alt, alt_row = _vslider(0, 90, getattr(working[et], 'altitude', 45.0), '°')

            def _op_row(val):
                sl = _slider_pct(int(val * 100)); lb = QLabel(f"{int(val*100)}%"); lb.setFixedWidth(40)
                row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0,0,0,0); h.addWidget(sl); h.addWidget(lb)
                return sl, lb, row
            sl_op, lbl_op, op_row = _op_row(working[et].opacity)
            sl_hi, lbl_hi, hiop_row = _op_row(getattr(working[et], 'highlight_opacity', 0.75))
            sl_shd, lbl_shd, shop_row = _op_row(getattr(working[et], 'shadow_opacity', 0.75))

            btn_hi = _color_btn(working[et].color2)
            cb_hi_blend = _blend_combo(getattr(working[et], 'blend_mode2', 'screen') or 'screen')
            hi_row = QWidget(); hh = QHBoxLayout(hi_row); hh.setContentsMargins(0,0,0,0); hh.setSpacing(4)
            hh.addWidget(btn_hi); hh.addWidget(cb_hi_blend); hh.addStretch()
            btn_sh = _color_btn(working[et].color)
            cb_sh_blend = _blend_combo(getattr(working[et], 'blend_mode', 'multiply') or 'multiply')
            sh_row = QWidget(); sh2 = QHBoxLayout(sh_row); sh2.setContentsMargins(0,0,0,0); sh2.setSpacing(4)
            sh2.addWidget(btn_sh); sh2.addWidget(cb_sh_blend); sh2.addStretch()

            fl.addRow("Style:", cb_kind)
            fl.addRow("Technique:", cb_tech)
            fl.addRow("Size (face depth):", sp_size)
            fl.addRow("Depth:", depth_row)
            fl.addRow("Direction:", cb_dir)
            fl.addRow("Light angle:", dir_row)
            fl.addRow("Altitude:", alt_row)
            fl.addRow("Soften:", sp_soft)
            fl.addRow("Opacity:", op_row)
            fl.addRow("Highlight:", hi_row)
            fl.addRow("Highlight opacity:", hiop_row)
            fl.addRow("Shadow:", sh_row)
            fl.addRow("Shadow opacity:", shop_row)

            def _commit():
                working[et].bevel_kind = cb_kind.currentText()
                working[et].bevel_technique = cb_tech.currentText()
                working[et].bevel_dir = cb_dir.currentText()
                working[et].size = sp_size.value()
                working[et].bevel_depth = sl_depth.value()
                working[et].soften = sp_soft.value()
                working[et].direction = sl_dir.value()
                working[et].altitude = sl_alt.value()
                working[et].opacity = sl_op.value() / 100.0
                working[et].highlight_opacity = sl_hi.value() / 100.0
                working[et].shadow_opacity = sl_shd.value() / 100.0
                working[et].blend_mode = cb_sh_blend.currentText()
                working[et].blend_mode2 = cb_hi_blend.currentText()
                _enable_in_list(et); _live()
            def _on_op(v): lbl_op.setText(f"{v}%"); _commit()
            def _on_hi(v): lbl_hi.setText(f"{v}%"); _commit()
            def _on_shd(v): lbl_shd.setText(f"{v}%"); _commit()
            def _pick(target_attr, btn):
                c = getattr(working[et], target_attr)
                _orig_b = getattr(working[et], target_attr)
                def _prev_b(col):
                    setattr(working[et], target_attr, col); _live()
                new_c = EdofColorDialog.get_color(dlg, c if len(c)>=4 else (*c[:3],255), alpha=True, on_change=_prev_b)
                if new_c is not None:
                    setattr(working[et], target_attr, new_c)
                    btn.setStyleSheet(f"background:#{new_c[0]:02x}{new_c[1]:02x}{new_c[2]:02x};border:1px solid #888;border-radius:3px;")
                    _enable_in_list(et); _live()
                else:
                    setattr(working[et], target_attr, _orig_b); _live()
            for c in (cb_kind, cb_tech, cb_dir, cb_hi_blend, cb_sh_blend):
                c.currentTextChanged.connect(lambda _: _commit())
            for s in (sp_size, sp_soft):
                s.valueChanged.connect(lambda _: _commit())
            sl_depth.valueChanged.connect(lambda v: (lbl_depth.setText(f"{v}%"), _commit()))
            sl_dir.valueChanged.connect(lambda v: (lbl_dir.setText(f"{v}°"), _commit()))
            sl_alt.valueChanged.connect(lambda v: (lbl_alt.setText(f"{v}°"), _commit()))
            sl_op.valueChanged.connect(_on_op)
            sl_hi.valueChanged.connect(_on_hi)
            sl_shd.valueChanged.connect(_on_shd)
            btn_hi.clicked.connect(lambda: _pick('color2', btn_hi))
            btn_sh.clicked.connect(lambda: _pick('color', btn_sh))
            return w

        def _build_stroke_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(8); fl.setContentsMargins(20, 20, 20, 20)
            fl.addRow(QLabel("<h3>Stroke</h3>"))
            sp_size = _mm(working[et].size, 20)
            cb_pos = QComboBox(); cb_pos.addItems(['outside','center','inside']); cb_pos.setCurrentText(working[et].stroke_position)
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); op_h = QHBoxLayout(op_row); op_h.setContentsMargins(0,0,0,0)
            op_h.addWidget(sl_op); op_h.addWidget(lbl_op)
            btn_c = _color_btn(working[et].color)
            fl.addRow("Size:", sp_size)
            fl.addRow("Position:", cb_pos)
            fl.addRow("Blend mode:", cb_bm)
            fl.addRow("Opacity:", op_row)
            fl.addRow("Color:", btn_c)
            def _commit():
                working[et].size = sp_size.value()
                working[et].stroke_position = cb_pos.currentText()
                working[et].blend_mode = cb_bm.currentText()
                working[et].opacity = sl_op.value() / 100.0
                _enable_in_list(et); _live()
            def _on_op(v):
                lbl_op.setText(f"{v}%"); _commit()
            def _pick():
                from PyQt6.QtWidgets import QColorDialog
                c = working[et].color
                _orig_c = working[et].color
                def _prev_c(col):
                    working[et].color = col; _live()
                new_c = EdofColorDialog.get_color(dlg, c if len(c)>=4 else (*c[:3],255), alpha=True, on_change=_prev_c)
                if new_c is not None:
                    working[et].color = new_c
                    hex_rgb = f"#{new_c[0]:02x}{new_c[1]:02x}{new_c[2]:02x}"
                    btn_c.setStyleSheet(f"background:{hex_rgb};border:1px solid #888;border-radius:3px;")
                    _enable_in_list(et); _live()
                else:
                    working[et].color = _orig_c; _live()
            sp_size.valueChanged.connect(lambda _: _commit())
            cb_pos.currentTextChanged.connect(lambda _: _commit())
            cb_bm.currentTextChanged.connect(lambda _: _commit())
            sl_op.valueChanged.connect(_on_op)
            btn_c.clicked.connect(_pick)
            return w

        def _build_color_overlay_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(8); fl.setContentsMargins(20, 20, 20, 20)
            fl.addRow(QLabel("<h3>Color Overlay</h3>"))
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); op_h = QHBoxLayout(op_row); op_h.setContentsMargins(0,0,0,0)
            op_h.addWidget(sl_op); op_h.addWidget(lbl_op)
            btn_c = _color_btn(working[et].color)
            fl.addRow("Blend mode:", cb_bm)
            fl.addRow("Opacity:", op_row)
            fl.addRow("Color:", btn_c)
            def _commit():
                working[et].blend_mode = cb_bm.currentText()
                working[et].opacity = sl_op.value() / 100.0
                _enable_in_list(et); _live()
            def _on_op(v):
                lbl_op.setText(f"{v}%"); _commit()
            def _pick():
                from PyQt6.QtWidgets import QColorDialog
                c = working[et].color
                _orig_c = working[et].color
                def _prev_c(col):
                    working[et].color = col; _live()
                new_c = EdofColorDialog.get_color(dlg, c if len(c)>=4 else (*c[:3],255), alpha=True, on_change=_prev_c)
                if new_c is not None:
                    working[et].color = new_c
                    hex_rgb = f"#{new_c[0]:02x}{new_c[1]:02x}{new_c[2]:02x}"
                    btn_c.setStyleSheet(f"background:{hex_rgb};border:1px solid #888;border-radius:3px;")
                    _enable_in_list(et); _live()
                else:
                    working[et].color = _orig_c; _live()
            cb_bm.currentTextChanged.connect(lambda _: _commit())
            sl_op.valueChanged.connect(_on_op)
            btn_c.clicked.connect(_pick)
            return w

        def _build_gradient_overlay_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(8); fl.setContentsMargins(20, 20, 20, 20)
            fl.addRow(QLabel("<h3>Gradient Overlay</h3>"))
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); op_h = QHBoxLayout(op_row); op_h.setContentsMargins(0,0,0,0)
            op_h.addWidget(sl_op); op_h.addWidget(lbl_op)
            btn_c1 = _color_btn(working[et].gradient_start)
            btn_c2 = _color_btn(working[et].gradient_end)
            sp_ang = _spin(0, 360, working[et].gradient_angle, '°', 0)
            fl.addRow("Blend mode:", cb_bm)
            fl.addRow("Opacity:", op_row)
            fl.addRow("Start color:", btn_c1)
            fl.addRow("End color:", btn_c2)
            fl.addRow("Angle:", sp_ang)
            def _commit():
                working[et].blend_mode = cb_bm.currentText()
                working[et].opacity = sl_op.value() / 100.0
                working[et].gradient_angle = sp_ang.value()
                _enable_in_list(et); _live()
            def _on_op(v):
                lbl_op.setText(f"{v}%"); _commit()
            def _pick(attr, btn):
                from PyQt6.QtWidgets import QColorDialog
                c = getattr(working[et], attr)
                _orig_g = getattr(working[et], attr)
                def _prev_g(col):
                    setattr(working[et], attr, col); _live()
                new_c = EdofColorDialog.get_color(dlg, c if len(c)>=4 else (*c[:3],255), alpha=True, on_change=_prev_g)
                if new_c is not None:
                    setattr(working[et], attr, new_c)
                    hex_rgb = f"#{new_c[0]:02x}{new_c[1]:02x}{new_c[2]:02x}"
                    btn.setStyleSheet(f"background:{hex_rgb};border:1px solid #888;border-radius:3px;")
                    _enable_in_list(et); _live()
                else:
                    setattr(working[et], attr, _orig_g); _live()
            cb_bm.currentTextChanged.connect(lambda _: _commit())
            sl_op.valueChanged.connect(_on_op)
            sp_ang.valueChanged.connect(lambda _: _commit())
            btn_c1.clicked.connect(lambda: _pick('gradient_start', btn_c1))
            btn_c2.clicked.connect(lambda: _pick('gradient_end', btn_c2))
            return w

        def _build_texture_overlay_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(8); fl.setContentsMargins(20, 20, 20, 20)
            fl.addRow(QLabel("<h3>Texture Overlay</h3>"))
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); op_h = QHBoxLayout(op_row); op_h.setContentsMargins(0,0,0,0)
            op_h.addWidget(sl_op); op_h.addWidget(lbl_op)
            btn_load = QPushButton("Load Texture Image…")
            lbl_status = QLabel("(no texture loaded)" if not getattr(working[et], 'texture_path', None) else f"Loaded: {os.path.basename(working[et].texture_path)}")
            sp_scale = _spin(10, 500, getattr(working[et], 'texture_scale', 100.0) or 100.0, '%', 0)
            # v4.1.1: fit mode + anchor
            cb_fit = QComboBox(); cb_fit.addItems(['tile','fit','fill','stretch'])
            cb_fit.setCurrentText(getattr(working[et], 'texture_fit', 'tile') or 'tile')
            cb_fit.setToolTip("tile=repeat at scale  •  fit=letterbox inside  •  fill=cover (overflow)  •  stretch=ignore aspect")
            cb_anchor = QComboBox(); cb_anchor.addItems(['top-left','center'])
            cb_anchor.setCurrentText(getattr(working[et], 'texture_anchor', 'top-left') or 'top-left')
            fl.addRow("Texture:", btn_load)
            fl.addRow("", lbl_status)
            fl.addRow("Blend mode:", cb_bm)
            fl.addRow("Opacity:", op_row)
            fl.addRow("Fit:", cb_fit)
            fl.addRow("Anchor:", cb_anchor)
            fl.addRow("Scale:", sp_scale)
            info = QLabel("<small>Scale is relative to <b>object size</b>, "
                           "independent of canvas zoom — texture stays the same size on the page.</small>")
            info.setWordWrap(True); info.setStyleSheet(f"color:{FGD};")
            fl.addRow("", info)
            def _commit():
                working[et].blend_mode = cb_bm.currentText()
                working[et].opacity = sl_op.value() / 100.0
                working[et].texture_scale = sp_scale.value()
                working[et].texture_fit = cb_fit.currentText()
                working[et].texture_anchor = cb_anchor.currentText()
                _enable_in_list(et); _live()
            def _on_op(v):
                lbl_op.setText(f"{v}%"); _commit()
            def _load():
                fn, _ = QFileDialog.getOpenFileName(dlg, "Load texture",
                                                      "", "Images (*.png *.jpg *.jpeg *.bmp *.tiff)")
                if fn:
                    working[et].texture_path = fn
                    lbl_status.setText(f"Loaded: {os.path.basename(fn)}")
                    _enable_in_list(et); _live()
            cb_bm.currentTextChanged.connect(lambda _: _commit())
            sl_op.valueChanged.connect(_on_op)
            sp_scale.valueChanged.connect(lambda _: _commit())
            cb_fit.currentTextChanged.connect(lambda _: _commit())
            cb_anchor.currentTextChanged.connect(lambda _: _commit())
            btn_load.clicked.connect(_load)
            return w

        def _color_commit_helper(et, btn_c, attr='color'):
            _orig = getattr(working[et], attr)
            def _prev(col):
                setattr(working[et], attr, col); _live()
            new_c = EdofColorDialog.get_color(
                dlg, getattr(working[et], attr) if len(getattr(working[et], attr)) >= 4
                else (*getattr(working[et], attr)[:3], 255), alpha=True, on_change=_prev)
            if new_c is not None:
                setattr(working[et], attr, new_c)
                btn_c.setStyleSheet(f"background:#{new_c[0]:02x}{new_c[1]:02x}{new_c[2]:02x};border:1px solid #888;border-radius:3px;")
                _enable_in_list(et); _live()
            else:
                setattr(working[et], attr, _orig); _live()

        def _build_long_shadow_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(8); fl.setContentsMargins(20, 20, 20, 20)
            fl.addRow(QLabel("<h3>Long Shadow</h3>"))
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); oh = QHBoxLayout(op_row); oh.setContentsMargins(0,0,0,0); oh.addWidget(sl_op); oh.addWidget(lbl_op)
            sp_dir = _spin(0, 360, working[et].direction, '°', 0)
            sp_len = _mm(working[et].ls_length, 200)

            def _grad_row(bar):
                row = QWidget(); hh = QHBoxLayout(row); hh.setContentsMargins(0, 0, 0, 0)
                hh.addWidget(bar, 1)
                bx = QPushButton("×"); bx.setFixedWidth(22)
                bx.setToolTip("Reset stops to default")
                hh.addWidget(bx)
                return row, bx

            # ---- BLUR: Solid | Constant | Linear | Custom -------------------
            _bm0 = (getattr(working[et], 'ls_blur_mode', '') or '').lower()
            if _bm0 not in ('solid', 'constant', 'linear', 'custom'):
                _lm = (getattr(working[et], 'ls_mode', 'solid') or 'solid').lower()
                if _lm == 'solid':
                    _bm0 = 'solid'
                elif _lm == 'cast':
                    _bm0 = 'linear'
                else:
                    _bm0 = 'constant' if _bm0 == 'constant' else 'linear'
            cb_blur = QComboBox(); cb_blur.addItems(['Solid', 'Constant', 'Linear', 'Custom'])
            cb_blur.setCurrentText(_bm0.capitalize())
            sp_size = _mm(working[et].size, 50)
            gb_blur = _GradientStopsBar('scalar', vmax=25.0, suffix=' mm')
            _bs = getattr(working[et], 'ls_grad_blurs', []) or []
            gb_blur.setStops(_bs if _bs else [[0.0, 0.0], [1.0, max(0.5, float(working[et].size or 2.0))]])
            row_b, bx_b = _grad_row(gb_blur)
            lab_size = QLabel("Blur amount:")
            lab_gb = QLabel("Blur gradient (mm):")
            fl.addRow("Blend mode:", cb_bm); fl.addRow("Opacity:", op_row)
            fl.addRow("Angle:", sp_dir); fl.addRow("Length:", sp_len)
            fl.addRow("Mode:", cb_blur)
            fl.addRow(lab_size, sp_size)
            fl.addRow(lab_gb, row_b)

            # ---- COLOR: Solid | Custom --------------------------------------
            _cm0 = (getattr(working[et], 'ls_color_mode', '') or '').lower()
            if _cm0 not in ('solid', 'custom'):
                _cm0 = 'custom' if ((getattr(working[et], 'ls_grad_colors', []) or [])
                                    or bool(getattr(working[et], 'ls_color_grad', False))) else 'solid'
            cb_color = QComboBox(); cb_color.addItems(['Solid', 'Custom'])
            cb_color.setCurrentText(_cm0.capitalize())
            btn_c = _color_btn(working[et].color)
            gb_color = _GradientStopsBar('color')
            _cs = getattr(working[et], 'ls_grad_colors', []) or []
            if not _cs:
                _c0 = list(working[et].color[:3])
                _c1 = list((getattr(working[et], 'color2', None) or (0, 0, 0, 255))[:3])
                _cs = [[0.0] + [float(v) for v in _c0], [1.0] + [float(v) for v in _c1]]
            gb_color.setStops(_cs)
            row_c, bx_c = _grad_row(gb_color)
            lab_col = QLabel("Color:")
            lab_gc = QLabel("Color gradient:")
            fl.addRow("Color mode:", cb_color)
            fl.addRow(lab_col, btn_c)
            fl.addRow(lab_gc, row_c)

            # ---- ALPHA: Solid | Fade | Custom -------------------------------
            _am0 = (getattr(working[et], 'ls_alpha_mode', '') or '').lower()
            if _am0 not in ('solid', 'fade', 'custom'):
                if getattr(working[et], 'ls_grad_alphas', []) or []:
                    _am0 = 'custom'
                else:
                    _am0 = 'fade' if bool(getattr(working[et], 'ls_fade', True)) else 'solid'
            cb_alpha = QComboBox(); cb_alpha.addItems(['Solid', 'Fade', 'Custom'])
            cb_alpha.setCurrentText(_am0.capitalize())
            gb_alpha = _GradientStopsBar('scalar', vmax=1.0)
            _as = getattr(working[et], 'ls_grad_alphas', []) or []
            gb_alpha.setStops(_as if _as else [[0.0, 1.0], [1.0, 0.0]])
            row_a, bx_a = _grad_row(gb_alpha)
            lab_ga = QLabel("Alpha gradient:")
            fl.addRow("Alpha mode:", cb_alpha)
            fl.addRow(lab_ga, row_a)

            def _sync_vis():
                bm = cb_blur.currentText().lower()
                lab_size.setVisible(bm in ('constant', 'linear'))
                sp_size.setVisible(bm in ('constant', 'linear'))
                lab_size.setText("Blur amount:" if bm == 'constant' else "End blur:")
                lab_gb.setVisible(bm == 'custom'); row_b.setVisible(bm == 'custom')
                cm = cb_color.currentText().lower()
                lab_col.setVisible(cm == 'solid'); btn_c.setVisible(cm == 'solid')
                lab_gc.setVisible(cm == 'custom'); row_c.setVisible(cm == 'custom')
                am = cb_alpha.currentText().lower()
                lab_ga.setVisible(am == 'custom'); row_a.setVisible(am == 'custom')
            _sync_vis()

            def _commit():
                working[et].blend_mode = cb_bm.currentText(); working[et].opacity = sl_op.value()/100.0
                working[et].direction = sp_dir.value(); working[et].ls_length = sp_len.value()
                bm = cb_blur.currentText().lower()
                working[et].ls_blur_mode = bm
                working[et].ls_mode = 'solid' if bm == 'solid' else 'soft'   # legacy readers
                working[et].size = sp_size.value()
                if bm == 'custom':
                    working[et].ls_grad_blurs = gb_blur.stops()
                cm = cb_color.currentText().lower()
                working[et].ls_color_mode = cm
                working[et].ls_color_grad = False                            # legacy readers: solid colour
                if cm == 'custom':
                    working[et].ls_grad_colors = gb_color.stops()
                am = cb_alpha.currentText().lower()
                working[et].ls_alpha_mode = am
                working[et].ls_fade = (am == 'fade')                         # legacy readers
                if am == 'custom':
                    working[et].ls_grad_alphas = gb_alpha.stops()
                _sync_vis(); _enable_in_list(et); _live()
            def _on_op(v): lbl_op.setText(f"{v}%"); _commit()
            cb_bm.currentTextChanged.connect(lambda _: _commit()); sl_op.valueChanged.connect(_on_op)
            sp_dir.valueChanged.connect(lambda _: _commit()); sp_len.valueChanged.connect(lambda _: _commit())
            cb_blur.currentTextChanged.connect(lambda _: _commit())
            cb_color.currentTextChanged.connect(lambda _: _commit())
            cb_alpha.currentTextChanged.connect(lambda _: _commit())
            sp_size.valueChanged.connect(lambda _: _commit())
            for gb in (gb_color, gb_alpha, gb_blur):
                gb.changed.connect(_commit)
            bx_b.clicked.connect(lambda: (gb_blur.setStops([[0.0, 0.0], [1.0, max(0.5, float(sp_size.value() or 2.0))]]), _commit()))
            bx_c.clicked.connect(lambda: (gb_color.setStops([[0.0] + [float(v) for v in working[et].color[:3]], [1.0, 0.0, 0.0, 0.0]]), _commit()))
            bx_a.clicked.connect(lambda: (gb_alpha.setStops([[0.0, 1.0], [1.0, 0.0]]), _commit()))
            btn_c.clicked.connect(lambda: _color_commit_helper(et, btn_c, 'color'))
            return w

        def _build_chromatic_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(7); fl.setContentsMargins(20, 16, 20, 16)
            fl.addRow(QLabel("<h3>Chromatic Aberration</h3>"))
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); oh = QHBoxLayout(op_row); oh.setContentsMargins(0,0,0,0); oh.addWidget(sl_op); oh.addWidget(lbl_op)
            cb_mode = QComboBox(); cb_mode.addItems(['linear', 'radial'])
            cb_mode.setCurrentText(getattr(working[et], 'ca_mode', 'linear') or 'linear')
            fl.addRow("Opacity:", op_row)
            fl.addRow("Mode:", cb_mode)

            # per-channel widgets: color, offset (mm), angle, distort (%)
            chans = [('R', 'ca_r_color', 'ca_r_offset', 'ca_r_angle', 'ca_r_distort'),
                     ('G', 'ca_g_color', 'ca_g_offset', 'ca_g_angle', 'ca_g_distort'),
                     ('B', 'ca_b_color', 'ca_b_offset', 'ca_b_angle', 'ca_b_distort')]
            ch_widgets = {}
            for name, ck, ok, ak, dk in chans:
                fl.addRow(QLabel(f"<b>{name} channel</b>"))
                btn_c = _color_btn(getattr(working[et], ck))
                sp_off = _mm(getattr(working[et], ok), 20)
                sp_ang = _spin(0, 360, getattr(working[et], ak), '°', 0)
                sp_dist = _spin(-50, 50, getattr(working[et], dk), ' %', 1)
                fl.addRow("  Colour:", btn_c)
                fl.addRow("  Offset:", sp_off)
                fl.addRow("  Angle:", sp_ang)
                fl.addRow("  Radial distort:", sp_dist)
                ch_widgets[name] = (btn_c, sp_off, sp_ang, sp_dist, ck, ok, ak, dk)

            def _sync_mode():
                radial = (cb_mode.currentText() == 'radial')
                for name, (btn_c, sp_off, sp_ang, sp_dist, ck, ok, ak, dk) in ch_widgets.items():
                    sp_off.setEnabled(not radial); sp_ang.setEnabled(not radial)
                    sp_dist.setEnabled(radial)
            _sync_mode()

            def _commit():
                working[et].opacity = sl_op.value()/100.0
                working[et].ca_mode = cb_mode.currentText()
                for name, (btn_c, sp_off, sp_ang, sp_dist, ck, ok, ak, dk) in ch_widgets.items():
                    setattr(working[et], ok, sp_off.value())
                    setattr(working[et], ak, sp_ang.value())
                    setattr(working[et], dk, sp_dist.value())
                _sync_mode(); _enable_in_list(et); _live()
            def _on_op(v): lbl_op.setText(f"{v}%"); _commit()
            sl_op.valueChanged.connect(_on_op)
            cb_mode.currentTextChanged.connect(lambda _: _commit())
            for name, (btn_c, sp_off, sp_ang, sp_dist, ck, ok, ak, dk) in ch_widgets.items():
                sp_off.valueChanged.connect(lambda _: _commit())
                sp_ang.valueChanged.connect(lambda _: _commit())
                sp_dist.valueChanged.connect(lambda _: _commit())
                btn_c.clicked.connect(lambda _=False, b=btn_c, k=ck: _color_commit_helper(et, b, k))
            return w

        def _build_halftone_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(7); fl.setContentsMargins(20, 14, 20, 14)
            fl.addRow(QLabel("<h3>Halftone (mosaic screen)</h3>"))
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); oh = QHBoxLayout(op_row); oh.setContentsMargins(0,0,0,0); oh.addWidget(sl_op); oh.addWidget(lbl_op)
            cb_cmode = QComboBox(); cb_cmode.addItems(['cmyk', 'rgb'])
            cb_cmode.setCurrentText(getattr(working[et], 'ht_color_mode', 'cmyk') or 'cmyk')
            cb_rmode = QComboBox(); cb_rmode.addItems(['size', 'transparency'])
            cb_rmode.setCurrentText(getattr(working[et], 'ht_render_mode', 'size') or 'size')
            cb_shape = QComboBox()
            cb_shape.addItems(['circle', 'diamond', 'square', 'ring', 'cross', 'line', 'triangle', 'hex'])
            _shp = working[et].ht_shape if working[et].ht_shape in (
                'circle', 'diamond', 'square', 'ring', 'cross', 'line', 'triangle', 'hex') else 'circle'
            cb_shape.setCurrentText(_shp)
            sp_dot = _mm(working[et].ht_dot, 20, lo=0.3)
            sp_ang = _spin(0, 180, working[et].ht_angle, '°', 0)
            sp_sf = _spin(1, 1000, getattr(working[et], 'ht_size_factor', 115.0), ' %', 0)
            sp_ov = _spin(0.2, 4.0, getattr(working[et], 'ht_overlay_scale', 1.5), '×', 2)
            sp_dc = _spin(0, 100, getattr(working[et], 'ht_decentralization', 0.0), ' %', 0)
            chk_hex = QCheckBox("Hex grid"); chk_hex.setChecked(bool(getattr(working[et], 'ht_hex', True)))
            fl.addRow("Blend mode:", cb_bm); fl.addRow("Opacity:", op_row)
            fl.addRow("Color mode:", cb_cmode)
            fl.addRow("Dot driven by:", cb_rmode)
            fl.addRow("Dot shape:", cb_shape)
            fl.addRow("Cell size:", sp_dot)
            fl.addRow("Screen angle step:", sp_ang)
            fl.addRow("Dot scale:", sp_sf)
            fl.addRow("Max dot vs cell:", sp_ov)
            fl.addRow("Decentralization:", sp_dc)
            fl.addRow("", chk_hex)
            chk_rand = QCheckBox("Random dot rotation")
            chk_rand.setChecked(bool(getattr(working[et], 'ht_random_rotate', False)))
            fl.addRow("", chk_rand)

            cb_bg = QComboBox()
            cb_bg.addItem("Transparent (dots only)", "transparent")
            cb_bg.addItem("Native (RGB=black / CMYK=white)", "native")
            cb_bg.addItem("Layer content", "layer")
            _bgv = getattr(working[et], 'ht_background', '') or (
                'layer' if getattr(working[et], 'ht_keep_background', False) else 'native')
            _bgi = cb_bg.findData(_bgv); cb_bg.setCurrentIndex(_bgi if _bgi >= 0 else 0)
            fl.addRow("Background:", cb_bg)

            chk_extra = QCheckBox("Extra key channel (RGB+black / CMYK+white)")
            chk_extra.setChecked(bool(getattr(working[et], "ht_extra_channel", False)))
            fl.addRow("", chk_extra)
            cb_extra = QComboBox()
            cb_extra.addItem("Auto (black for RGB, white for CMYK)", "auto")
            cb_extra.addItem("White", "white")
            cb_extra.addItem("Black", "black")
            _exv = getattr(working[et], 'ht_extra_color', 'auto') or 'auto'
            _exi = cb_extra.findData(_exv); cb_extra.setCurrentIndex(_exi if _exi >= 0 else 0)
            fl.addRow("Extra ink:", cb_extra)

            # per-channel enable (R G B [+key]  /  C M Y K [+key])
            _ce = list(getattr(working[et], 'ht_channels_enabled', []) or [True] * 5)
            while len(_ce) < 5:
                _ce.append(True)
            chk_ch = []
            ch_row = QWidget(); ch_h = QHBoxLayout(ch_row); ch_h.setContentsMargins(0, 0, 0, 0); ch_h.setSpacing(8)
            for i in range(5):
                cb = QCheckBox(); cb.setChecked(bool(_ce[i])); cb.setFixedWidth(40)
                chk_ch.append(cb); ch_h.addWidget(cb)
            ch_h.addStretch()
            lbl_ch = QLabel("Channels:")
            fl.addRow(lbl_ch, ch_row)

            def _relabel_channels():
                names = (['R', 'G', 'B'] if cb_cmode.currentText() == 'rgb' else ['C', 'M', 'Y', 'K'])
                if chk_extra.isChecked():
                    names = names + ['K2' if cb_cmode.currentText() == 'rgb' else 'W']
                for i, cb in enumerate(chk_ch):
                    if i < len(names):
                        cb.setText(names[i]); cb.setVisible(True)
                    else:
                        cb.setVisible(False)
            _relabel_channels()

            cb_clip = QComboBox()
            cb_clip.addItem("Whole dots (no clip)", "whole")
            cb_clip.addItem("Hard (clip to source)", "hard")
            cb_clip.addItem("Soft (feather to source)", "soft")
            _cl = getattr(working[et], 'ht_clip', 'whole') or 'whole'
            _cli = cb_clip.findData(_cl); cb_clip.setCurrentIndex(_cli if _cli >= 0 else 0)
            fl.addRow("Edge clip:", cb_clip)

            # Custom pattern images (fallback to the built-in shape when missing)
            # --- Patterns: mode + per-channel thumbnail slots --------------
            def _chan_names():
                nm = (['R', 'G', 'B'] if cb_cmode.currentText() == 'rgb' else ['C', 'M', 'Y', 'K'])
                if chk_extra.isChecked():
                    nm = nm + ['K2' if cb_cmode.currentText() == 'rgb' else 'W']
                return nm

            def _pats():
                return list(getattr(working[et], 'ht_patterns', []) or [])

            cb_pmode = QComboBox()
            cb_pmode.addItem("Built-in shape", "shape")
            cb_pmode.addItem("One image (all channels)", "single")
            cb_pmode.addItem("Per channel (individual)", "per_channel")
            _pm0 = getattr(working[et], 'ht_pattern_mode', 'shape') or 'shape'
            _pmi = cb_pmode.findData(_pm0); cb_pmode.setCurrentIndex(_pmi if _pmi >= 0 else 0)
            fl.addRow("Pattern mode:", cb_pmode)

            pat_strip = QWidget(); pat_h = QHBoxLayout(pat_strip)
            pat_h.setContentsMargins(0, 0, 0, 0); pat_h.setSpacing(4)
            _thumb_btns = []
            for i in range(5):
                b = QPushButton(); b.setFixedSize(34, 34)
                b.setStyleSheet("QPushButton{background:#26263a;border:1px solid #44445e;border-radius:5px;}"
                                "QPushButton:hover{border-color:#6a6aa0;}")
                pat_h.addWidget(b); _thumb_btns.append(b)
            pat_h.addStretch()
            fl.addRow("Patterns:", pat_strip)

            def _nslots():
                md = cb_pmode.currentData()
                return 0 if md == 'shape' else (1 if md == 'single' else len(_chan_names()))

            def _refresh_thumbs():
                md = cb_pmode.currentData(); names = _chan_names(); pats = _pats()
                ns = _nslots()
                pat_strip.setVisible(md != 'shape')
                for i, b in enumerate(_thumb_btns):
                    if i < ns:
                        b.setVisible(True)
                        lab = "all" if md == 'single' else (names[i] if i < len(names) else str(i + 1))
                        b.setToolTip(f"{lab} pattern — click to load / library / clear")
                        b64 = pats[i] if i < len(pats) else ""
                        pm = _ht_b64_pixmap(b64, 28) if b64 else None
                        if pm is not None:
                            from PyQt6.QtGui import QIcon as _QIcon
                            from PyQt6.QtCore import QSize as _QSize
                            b.setIcon(_QIcon(pm)); b.setIconSize(_QSize(28, 28)); b.setText("")
                        else:
                            b.setIcon(QIcon()); b.setText(lab)
                    else:
                        b.setVisible(False)

            def _set_pat(idx, b64):
                md = cb_pmode.currentData()
                if md == 'single':
                    working[et].ht_patterns = [b64 or ""]
                else:
                    pats = _pats(); n = len(_chan_names())
                    while len(pats) < n:
                        pats.append("")
                    pats[idx] = b64 or ""
                    working[et].ht_patterns = pats
                if b64:
                    _ht_lib_add(b64)
                _refresh_thumbs(); _commit()

            def _on_pmode():
                md = cb_pmode.currentData()
                cur = _pats()
                if md == 'shape':
                    working[et].ht_patterns = []
                elif md == 'single':
                    first = next((p for p in cur if p), "")
                    working[et].ht_patterns = [first]
                else:  # per_channel
                    n = len(_chan_names())
                    if len(cur) == 1 and cur[0]:
                        working[et].ht_patterns = [cur[0]] * n
                    else:
                        while len(cur) < n:
                            cur.append("")
                        working[et].ht_patterns = cur
                working[et].ht_pattern_mode = md
                _refresh_thumbs(); _commit()

            def _thumb_menu(idx):
                from PyQt6.QtWidgets import QMenu, QFileDialog
                from PyQt6.QtGui import QIcon as _QIcon
                m = QMenu(dlg)
                def _load():
                    f, _f = QFileDialog.getOpenFileName(
                        dlg, "Choose pattern image", "",
                        "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
                    if f:
                        b64 = _ht_file_to_b64(f)
                        if b64:
                            _set_pat(idx, b64)
                m.addAction("Load image…", _load)
                lib = _ht_lib_get()
                if lib:
                    sub = m.addMenu("From library"); sub.setStyle(_menu_icon_style(sub, 28))
                    for b64 in lib:
                        pm = _ht_b64_pixmap(b64, 28); act = sub.addAction("")
                        if pm is not None:
                            act.setIcon(_QIcon(pm))
                        act.triggered.connect(lambda _=False, bb=b64: _set_pat(idx, bb))
                cur = _pats()
                if idx < len(cur) and cur[idx]:
                    m.addAction("Clear", lambda: _set_pat(idx, ""))
                m.exec(_thumb_btns[idx].mapToGlobal(_thumb_btns[idx].rect().bottomLeft()))

            for i, b in enumerate(_thumb_btns):
                b.clicked.connect(lambda _=False, ix=i: _thumb_menu(ix))
            cb_pmode.currentIndexChanged.connect(lambda _: _on_pmode())
            _refresh_thumbs()

            def _commit():
                working[et].blend_mode = cb_bm.currentText(); working[et].opacity = sl_op.value()/100.0
                working[et].ht_color_mode = cb_cmode.currentText()
                working[et].ht_render_mode = cb_rmode.currentText()
                working[et].ht_shape = cb_shape.currentText()
                working[et].ht_dot = sp_dot.value(); working[et].ht_angle = sp_ang.value()
                working[et].ht_size_factor = sp_sf.value()
                working[et].ht_overlay_scale = sp_ov.value()
                working[et].ht_decentralization = sp_dc.value()
                working[et].ht_hex = chk_hex.isChecked()
                working[et].ht_random_rotate = chk_rand.isChecked()
                working[et].ht_background = cb_bg.currentData()
                working[et].ht_keep_background = (cb_bg.currentData() == 'layer')
                working[et].ht_extra_channel = chk_extra.isChecked()
                working[et].ht_extra_color = cb_extra.currentData()
                working[et].ht_channels_enabled = [cb.isChecked() for cb in chk_ch]
                working[et].ht_clip = cb_clip.currentData()
                _enable_in_list(et); _live()
            def _on_op(v): lbl_op.setText(f"{v}%"); _commit()
            cb_bm.currentTextChanged.connect(lambda _: _commit()); sl_op.valueChanged.connect(_on_op)
            for c in (cb_cmode, cb_rmode, cb_shape):
                c.currentTextChanged.connect(lambda _: _commit())
            for s in (sp_dot, sp_ang, sp_sf, sp_ov, sp_dc):
                s.valueChanged.connect(lambda _: _commit())
            chk_hex.toggled.connect(lambda _: _commit())
            chk_rand.toggled.connect(lambda _: _commit())
            cb_bg.currentIndexChanged.connect(lambda _: _commit())
            chk_extra.toggled.connect(lambda _: (_relabel_channels(), _refresh_thumbs(), _commit()))
            cb_extra.currentIndexChanged.connect(lambda _: _commit())
            for cb in chk_ch:
                cb.toggled.connect(lambda _: _commit())
            cb_clip.currentIndexChanged.connect(lambda _: _commit())
            cb_cmode.currentTextChanged.connect(lambda _: (_relabel_channels(), _refresh_thumbs()))
            return w

        def _build_light_sweep_page(et):
            w = QWidget(); fl = QFormLayout(w); fl.setSpacing(8); fl.setContentsMargins(20, 20, 20, 20)
            fl.addRow(QLabel("<h3>Light Sweep</h3>"))
            cb_bm = _blend_combo(working[et].blend_mode)
            sl_op = _slider_pct(int(working[et].opacity * 100))
            lbl_op = QLabel(f"{int(working[et].opacity*100)}%"); lbl_op.setFixedWidth(40)
            op_row = QWidget(); oh = QHBoxLayout(op_row); oh.setContentsMargins(0,0,0,0); oh.addWidget(sl_op); oh.addWidget(lbl_op)
            btn_c = _color_btn(working[et].color2)
            sp_pos = _spin(0, 1, working[et].lsw_pos, '', 2)
            sp_wid = _spin(0.05, 1, working[et].lsw_width, '', 2)
            sp_ang = _spin(0, 360, working[et].lsw_angle, '°', 0)
            fl.addRow("Blend mode:", cb_bm); fl.addRow("Opacity:", op_row); fl.addRow("Light color:", btn_c)
            fl.addRow("Position (0-1):", sp_pos); fl.addRow("Width (0-1):", sp_wid); fl.addRow("Angle:", sp_ang)
            def _commit():
                working[et].blend_mode = cb_bm.currentText(); working[et].opacity = sl_op.value()/100.0
                working[et].lsw_pos = sp_pos.value(); working[et].lsw_width = sp_wid.value()
                working[et].lsw_angle = sp_ang.value(); _enable_in_list(et); _live()
            def _on_op(v): lbl_op.setText(f"{v}%"); _commit()
            cb_bm.currentTextChanged.connect(lambda _: _commit()); sl_op.valueChanged.connect(_on_op)
            sp_pos.valueChanged.connect(lambda _: _commit()); sp_wid.valueChanged.connect(lambda _: _commit())
            sp_ang.valueChanged.connect(lambda _: _commit())
            btn_c.clicked.connect(lambda: _color_commit_helper(et, btn_c, 'color2'))
            return w

        # ── dispatch: build the parameter panel for a given instance key ──────
        def _build_for(key):
            t = working[key].type
            if t == 'drop_shadow':   return _build_shadow_page(key, is_inner=False)
            if t == 'inner_shadow':  return _build_shadow_page(key, is_inner=True)
            if t == 'outer_glow':    return _build_glow_page(key, is_inner=False)
            if t == 'inner_glow':    return _build_glow_page(key, is_inner=True)
            if t == 'bevel':         return _build_bevel_page(key)
            if t == 'stroke':        return _build_stroke_page(key)
            if t == 'color_overlay': return _build_color_overlay_page(key)
            if t == 'gradient_overlay': return _build_gradient_overlay_page(key)
            if t == 'texture_overlay':  return _build_texture_overlay_page(key)
            if t == 'long_shadow':   return _build_long_shadow_page(key)
            if t == 'chromatic_aberration': return _build_chromatic_page(key)
            if t == 'halftone':      return _build_halftone_page(key)
            if t == 'light_sweep':   return _build_light_sweep_page(key)
            return QWidget()

        stack.addWidget(w_blend)
        param_widgets['__blend__'] = w_blend

        def _show(key):
            if key == '__blend__':
                stack.setCurrentWidget(w_blend); return
            if key not in param_widgets:
                pg = _build_for(key); param_widgets[key] = pg; stack.addWidget(pg)
            stack.setCurrentWidget(param_widgets[key])

        splitter.addWidget(stack)
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        v.addWidget(splitter, 1)

        def _cur_key():
            it = list_w.currentItem()
            return it.data(UR) if it else None

        def _on_select():
            k = _cur_key()
            if k is not None:
                _show(k)
        list_w.currentRowChanged.connect(lambda _: _on_select())

        def _on_check(item):
            if _rebuilding[0]: return
            k = item.data(UR)
            if k == '__blend__': return
            working[k].enabled = (item.checkState() == Qt.CheckState.Checked)
            _live()
        list_w.itemChanged.connect(_on_check)

        def _on_rows_moved(*_a):
            if _rebuilding[0]: return
            keys = [list_w.item(r).data(UR) for r in range(list_w.count())]
            order[:] = [k for k in keys if k != '__blend__']
            # keep Blending Options pinned at the top
            if list_w.count() == 0 or list_w.item(0).data(UR) != '__blend__':
                _rebuild_list(keep_key=_cur_key())
            else:
                # labels (ordinal suffixes) may have changed
                for k in order:
                    it = item_by_key.get(k)
                    if it is not None: it.setText(_label_for(k))
            _live()
        list_w.model().rowsMoved.connect(_on_rows_moved)

        cb_master.toggled.connect(lambda _: _live())

        # ── Add / Duplicate / Remove ─────────────────────────────────────────
        from PyQt6.QtWidgets import QMenu
        btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ Add"); btn_dup = QPushButton("⧉ Duplicate")
        btn_del = QPushButton("－ Remove")
        for b in (btn_add, btn_dup, btn_del):
            b.setFixedHeight(28); b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_dup)
        btn_row.addWidget(btn_del); btn_row.addStretch()
        v.addLayout(btn_row)

        def _add_effect(et2):
            k = _new_key(et2); working[k] = _make_default(et2); order.append(k)
            _rebuild_list(keep_key=k); _show(k); _live()
        def _add_menu():
            m = QMenu(dlg)
            for et2 in ADD_TYPES:
                act = m.addAction(DISPLAY.get(et2, et2))
                act.triggered.connect(lambda _=False, t=et2: _add_effect(t))
            m.exec(btn_add.mapToGlobal(btn_add.rect().bottomLeft()))
        def _duplicate():
            k = _cur_key()
            if not k or k == '__blend__': return
            nk = _new_key(working[k].type); working[nk] = deepcopy(working[k])
            order.insert(order.index(k) + 1, nk)
            _rebuild_list(keep_key=nk); _show(nk); _live()
        def _remove():
            k = _cur_key()
            if not k or k == '__blend__': return
            i = order.index(k); order.remove(k)
            pw = param_widgets.pop(k, None)
            if pw is not None:
                stack.removeWidget(pw); pw.deleteLater()
            working.pop(k, None)
            nxt = order[i] if i < len(order) else (order[i-1] if order else '__blend__')
            _rebuild_list(keep_key=nxt); _show(nxt); _live()
        btn_add.clicked.connect(_add_menu)
        btn_dup.clicked.connect(_duplicate)
        btn_del.clicked.connect(_remove)

        # OK / Cancel
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)

        _rebuild_list(keep_key='__blend__')
        _show('__blend__')
        # test/debug hooks
        self._fx_dlg_list = list_w
        self._fx_dlg_order = order
        self._fx_dlg_working = working
        self._fx_dlg_ops = {'add': _add_effect, 'dup': _duplicate,
                            'rm': _remove, 'cur': _cur_key, 'reorder': _on_rows_moved}

        result = dlg.exec()
        if result != QDialog.DialogCode.Accepted:
            self._obj.effects = original_effects
            self._obj.blend_mode = original_blend
            self._obj.opacity = original_opacity
            # v4.2.10.14: cancel restores the pre-dialog state, which is identical
            # to the current history top — suppress recording so Ctrl+Z isn't left
            # with a dead no-op step.
            try:
                mw = self._canvas._main_window()
                if mw is not None: mw._arm_history_suppression()
            except Exception:
                pass
            self._canvas.schedule_render(); self.changed.emit()
            return
        # Commit final state (enabled instances, in order)
        self._obj.effects = [deepcopy(working[k]) for k in order
                             if working[k].enabled and cb_master.isChecked()]
        self._canvas.schedule_render(); self.changed.emit()


    def _live_text(self):
        if self._loading or not isinstance(self._obj,edof.TextBox): return
        self._obj.text=self.te_text.toPlainText()
        self._canvas.schedule_render(80); self.changed.emit()

    def _live_qr(self):
        if self._loading or not isinstance(self._obj,edof.QRCode): return
        self._obj.data=self.le_qr.text(); self._canvas.schedule_render(80); self.changed.emit()

    def _apply_sizing(self):
        if self._loading or not isinstance(self._obj,edof.TextBox): return
        self._obj.style.auto_shrink=self.rb_shrink.isChecked()
        self._obj.style.auto_fill=self.rb_fill.isChecked()
        # v4.1.19.8: refresh inline editor immediately when sizing mode toggles
        try:
            inl = getattr(self._canvas, '_inline_widget', None)
            inl_obj = getattr(self._canvas, '_inline_obj', None)
            if inl is not None and inl_obj is self._obj:
                inl._invalidate()
        except Exception:
            pass
        self._canvas.schedule_render(); self.changed.emit()

    def _apply_tags(self):
        if self._loading or not self._obj: return
        self._obj.tags=[t.strip() for t in self.le_tags.text().split(',') if t.strip()]
        self.changed.emit()

    def _apply_line_pt(self,idx,coord,val):
        if self._loading or not self._obj: return
        pts=list(self._obj.points) if self._obj.points else [[0,0],[50,50]]
        while len(pts)<=idx: pts.append([0,0])
        pts[idx]=list(pts[idx]); pts[idx][0 if coord=='x' else 1]=val
        self._obj.points=pts
        x1,y1=pts[0]; x2,y2=pts[1]
        self._obj.transform.x=min(x1,x2); self._obj.transform.y=min(y1,y2)
        self._obj.transform.width=max(abs(x2-x1),MIN_MM); self._obj.transform.height=max(abs(y2-y1),MIN_MM)
        self._canvas._refresh_overlay(); self._canvas.schedule_render(); self.changed.emit()

    def _apply_stroke_w(self):
        if not self._obj: return
        self._obj.stroke.width=self.sp_sw.value(); self._canvas.schedule_render(); self.changed.emit()

    def _apply_line_sw(self):
        if not self._obj: return
        self._obj.stroke.width=self.sp_lsw.value(); self._canvas.schedule_render(); self.changed.emit()

    def _bind_var(self):
        if not self._obj: return
        name=self.le_var.text().strip(); self._obj.variable=name or None
        doc=self._canvas._doc
        if doc and name and name not in doc.variables.names(): doc.define_variable(name)
        self._canvas.schedule_render(); self.changed.emit()

    def _pick_text_color(self):
        if not isinstance(self._obj,edof.TextBox): return
        orig=tuple(self._obj.style.color)
        def _prev(col):
            self._obj.style.color=col[:3]; self._canvas.schedule_render()
        c=EdofColorDialog.get_color(self,(*self._obj.style.color[:3],255),alpha=False,on_change=_prev)
        if c:
            self._obj.style.color=c[:3]; self.btn_color.setStyleSheet(_cswatch(c))
            self._canvas.schedule_render(); self.changed.emit()
        else:
            self._obj.style.color=orig; self._canvas.schedule_render()

    def _pick_fill(self):
        if not hasattr(self._obj,'fill'): return
        orig=self._obj.fill.color
        def _prev(col):
            self._obj.fill.color=col; self._canvas.schedule_render()
        c=EdofColorDialog.get_color(self,self._obj.fill.color or (200,200,200,255),alpha=True,on_change=_prev)
        if c:
            self._obj.fill.color=c; self.btn_fill.setStyleSheet(_cswatch(c))
            self.lbl_fill_a.setText(f"{int(c[3]/255*100)}%"); self._canvas.schedule_render(); self.changed.emit()
        else:
            self._obj.fill.color=orig; self._canvas.schedule_render()

    def _pick_stroke(self):
        if not hasattr(self._obj,'stroke'): return
        orig=self._obj.stroke.color
        def _prev(col):
            self._obj.stroke.color=col; self._canvas.schedule_render()
        c=EdofColorDialog.get_color(self,self._obj.stroke.color or (0,0,0,255),alpha=True,on_change=_prev)
        if c:
            self._obj.stroke.color=c; self.btn_stroke.setStyleSheet(_cswatch(c))
            self._canvas.schedule_render(); self.changed.emit()
        else:
            self._obj.stroke.color=orig; self._canvas.schedule_render()

    def _pick_line_stroke(self):
        if not hasattr(self._obj,'stroke'): return
        orig=self._obj.stroke.color
        def _prev(col):
            self._obj.stroke.color=col; self._canvas.schedule_render()
        c=EdofColorDialog.get_color(self,self._obj.stroke.color or (0,0,0,255),alpha=True,on_change=_prev)
        if c:
            self._obj.stroke.color=c; self.btn_lstroke.setStyleSheet(_cswatch(c))
            self._canvas.schedule_render(); self.changed.emit()
        else:
            self._obj.stroke.color=orig; self._canvas.schedule_render()

    def _pick_qr_color(self,attr):
        if not isinstance(self._obj,edof.QRCode): return
        orig=getattr(self._obj,attr,(0,0,0,255))
        def _prev(col):
            setattr(self._obj,attr,col); self._canvas.schedule_render()
        c=EdofColorDialog.get_color(self,getattr(self._obj,attr,(0,0,0,255)),alpha=True,on_change=_prev)
        if c:
            setattr(self._obj,attr,c)
            getattr(self,f'btn_qr_{attr}').setStyleSheet(_cswatch(c))
            getattr(self,f'lbl_qr_{attr}_a').setText(f"{int(c[3]/255*100)}%")
            self._canvas.schedule_render(); self.changed.emit()
        else:
            setattr(self._obj,attr,orig); self._canvas.schedule_render()

    def _upload_font(self):
        p,_=QFileDialog.getOpenFileName(self,"Upload font","","Fonts (*.ttf *.otf)")
        if not p or not self._canvas._doc: return
        try:
            from PIL import ImageFont as _IF
            f=_IF.truetype(p,10); fname=f.getname()[0]
            self._canvas._doc.add_resource_from_file(p)
            invalidate_font_cache(); fonts=list_system_fonts()
            self.cb_font.clear(); self.cb_font.addItems(fonts); self.cb_font.setCurrentText(fname)
        except Exception as e: QMessageBox.critical(self,"Error",str(e))

    def _replace_image(self):
        if not isinstance(self._obj,edof.ImageBox): return
        doc=self._canvas._doc
        if not doc: return
        p,_=QFileDialog.getOpenFileName(self,"Image","","Images (*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp)")
        if p:
            rid=doc.add_resource_from_file(p); self._obj.resource_id=rid
            self._canvas.schedule_render(); self.changed.emit()

    def set_font_list(self, fonts):
        """v4.1.0: shows fonts with PDF-safe badges.
        Fonts that are part of the Standard 14 PDF base fonts get a (PDF) suffix.
        """
        self._loading = True; cur = self.cb_font.currentText()
        # Standard 14 PDF base fonts (and their common system aliases)
        PDF_SAFE_NAMES = {
            "helvetica", "arial",
            "times new roman", "times", "times-roman", "liberation serif",
            "courier", "courier new", "liberation mono",
            "symbol", "zapfdingbats", "zapf dingbats",
        }
        self.cb_font.clear()
        # Always include Standard 14 at the top, marked
        std14 = ["Helvetica", "Times New Roman", "Courier New"]
        seen = set()
        for f in std14:
            self.cb_font.addItem(f"✓ {f}  (PDF-safe)", f)
            seen.add(f.lower())
        # Add separator
        self.cb_font.insertSeparator(self.cb_font.count())
        # Add system fonts
        for f in sorted(fonts):
            if f.lower() in seen: continue
            label = f
            if f.lower() in PDF_SAFE_NAMES:
                label = f"✓ {f}  (PDF-safe)"
            self.cb_font.addItem(label, f)
        # Restore previous selection
        if cur:
            for i in range(self.cb_font.count()):
                data = self.cb_font.itemData(i)
                if data == cur or self.cb_font.itemText(i) == cur:
                    self.cb_font.setCurrentIndex(i); break
        self._loading = False


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════

class _UnifiedHistory:
    """v4.1.23.59: a SINGLE undo/redo timeline for the whole document — both
    body text edits and object operations (move/add/delete/style…). Each entry
    is a full-document snapshot (serialized, like the old object history) plus a
    caret context so a body-text step can reopen the inline editor where it was.

    Pointer model: the top of the stack is always the current committed state
    (object ops snapshot immediately; the body burst is flushed to a step before
    every undo/redo and before every object op). undo()/redo() move the pointer
    and return (restored_doc, caret_ctx)."""

    def __init__(self, max_steps: int = 80) -> None:
        self._stack = []      # list of (snapshot_bytes, caret_ctx, desc)
        self._ptr = -1
        self._max = max_steps

    def _snap(self, doc) -> bytes:
        from edof.format.serializer import EdofSerializer
        return EdofSerializer.to_bytes(doc)

    def _restore(self, data: bytes):
        from edof.format.serializer import EdofSerializer
        return EdofSerializer.from_bytes(data)

    def push(self, doc, caret_ctx=None, desc: str = "") -> None:
        self._stack = self._stack[:self._ptr + 1]
        self._stack.append((self._snap(doc), caret_ctx, desc))
        if len(self._stack) > self._max:
            self._stack.pop(0)
        self._ptr = len(self._stack) - 1

    def undo(self):
        if self._ptr <= 0:
            return None
        self._ptr -= 1
        data, ctx, _desc = self._stack[self._ptr]
        return (self._restore(data), ctx)

    def redo(self):
        if self._ptr >= len(self._stack) - 1:
            return None
        self._ptr += 1
        data, ctx, _desc = self._stack[self._ptr]
        return (self._restore(data), ctx)

    def can_undo(self) -> bool:
        return self._ptr > 0

    def can_redo(self) -> bool:
        return self._ptr < len(self._stack) - 1

    def clear(self) -> None:
        self._stack.clear()
        self._ptr = -1


class EdofEditor(QMainWindow):
    def __init__(self,filepath=None):
        super().__init__()
        self.doc=None; self.filepath=None
        # v4.1.23.59: ONE unified undo/redo timeline for body text AND objects.
        self.history=_UnifiedHistory(max_steps=80); self._modified=False
        # Body edits coalesce into one history step per typing burst: any edit
        # (re)starts a short debounce; when it settles the burst is pushed.
        # undo/redo and object ops flush a pending burst first so ordering is
        # exact. _body_pending guards whether there is an uncommitted burst.
        self._body_pending = False
        self._body_commit_timer = QTimer(self)
        self._body_commit_timer.setSingleShot(True)
        self._body_commit_timer.timeout.connect(self._commit_pending_body)
        self._body_commit_delay = 700  # ms
        # v4.2.10.13: object edits (move/resize/rotate/style via canvas drag or
        # the property panel) coalesce into one history step per burst, mirroring
        # the body-text model. Previously these went through _on_chg which only
        # set the modified flag and never pushed history, so undo/redo did
        # nothing for them in BASIC (free-design) mode. _suppress_obj_history
        # guards programmatic doc swaps (New/Open/undo-restore) so they don't
        # record spurious steps.
        self._obj_pending = False
        self._suppress_obj_history = False
        self._obj_commit_timer = QTimer(self)
        self._obj_commit_timer.setSingleShot(True)
        self._obj_commit_timer.timeout.connect(self._commit_pending_obj)
        self._obj_commit_delay = 450  # ms
        # v4.0.2: persistent settings + recent files
        self._settings = QSettings("edof", "editor")
        self._recent_files = self._settings.value("recent_files", []) or []
        if isinstance(self._recent_files, str):
            self._recent_files = [self._recent_files]
        self._build_ui(); self.setStyleSheet(QSS)
        # v4.1.10.1: apply Fusion style to all spinboxes so up/down arrows
        # actually render as solid triangles (Qt default arrows + custom QSS
        # buttons combine badly across versions; Fusion paints reliably).
        try:
            from PyQt6.QtWidgets import QStyleFactory, QAbstractSpinBox
            fusion = QStyleFactory.create("Fusion")
            if fusion is not None:
                def _apply_fusion(widget):
                    for child in widget.findChildren(QAbstractSpinBox):
                        try: child.setStyle(fusion)
                        except Exception: pass
                _apply_fusion(self)
                # Apply to any spinboxes created later too (subdoc/table dialogs)
                self._fusion_style = fusion
        except Exception: pass

        # v4.1.10.3/4.1.10.4/4.1.10.5: copy the exact stylesheet that the
        # Layer order buttons use (those render glyphs correctly per user
        # report). The `font:` shorthand with a quoted primary symbol family
        # *plus* small padding lets Qt actually render Unicode symbols. We
        # preserve existing stylesheet rules by appending.
        try:
            from PyQt6.QtWidgets import QPushButton, QToolButton
            SYM_FONT_RULE = (
                "font:bold 11pt 'Segoe UI Symbol','Arial Unicode MS','DejaVu Sans';"
                "padding:2px;"
            )
            def _patch_button_font(btn):
                label = btn.text() or ""
                if not any(ord(c) > 127 for c in label):
                    return
                existing = btn.styleSheet() or ""
                if "Segoe UI Symbol" in existing:
                    return
                btn.setStyleSheet(existing + SYM_FONT_RULE)
            for btn in self.findChildren(QPushButton):
                _patch_button_font(btn)
            for btn in self.findChildren(QToolButton):
                _patch_button_font(btn)
        except Exception: pass
        self.setWindowTitle(f"{t('app_title')} {edof.__version__}")
        # v4.2.2: window / taskbar icon
        try:
            from edof._apps.assets import icon_path
            _ip = icon_path("edof-editor.ico") or icon_path("edof-editor.png")
            if _ip:
                self.setWindowIcon(QIcon(_ip))
        except Exception:
            pass
        # v4.0.2/4.1.9.1: restore window geometry, default to maximized on first run
        geom = self._settings.value("geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        else:
            self.resize(1440, 880)
            # First run: open maximized so the user sees a full workspace
            QTimer.singleShot(0, self.showMaximized)
        # v4.0.3: restore dock layout (window state) — happens after build_ui
        ws = self._settings.value("windowState")
        if ws is not None:
            QTimer.singleShot(50, lambda: self.restoreState(ws))
        # v4.0.2/4.0.3: restore canvas preferences
        self._canvas._snap_to_grid = bool(self._settings.value("snap_to_grid", False, type=bool))
        self._canvas._show_align_guides = bool(self._settings.value("show_align_guides", True, type=bool))
        self._canvas._margins_enabled = bool(self._settings.value("margins_enabled", False, type=bool))
        # v4.1.10.2: restore grid size (mm)
        try:
            saved_size = float(self._settings.value("snap_size_mm", 5.0))
            if 0.01 <= saved_size <= 100.0:
                self._canvas._snap_size_mm = saved_size
        except (TypeError, ValueError): pass
        self._sync_view_actions()
        QTimer.singleShot(300,self._load_fonts)
        if filepath and os.path.isfile(filepath):
            self._open_file(filepath)
        else:
            # v4.1.5: show welcome screen instead of silently creating a doc
            QTimer.singleShot(0, self._show_welcome_screen)

        # v4.1.2: child editor windows for embedded sub-documents + file watcher
        self._child_editors = []          # list of EdofEditor child windows
        self._parent_editor = None        # if this editor is a child, points to parent
        self._parent_subdoc = None        # the SubDocumentBox in parent that this represents
        self._parent_temp_file = None     # temp file path used for embedded subdoc roundtrip
        try:
            from PyQt6.QtCore import QFileSystemWatcher
            self._fs_watcher = QFileSystemWatcher(self)
            self._fs_watcher.fileChanged.connect(self._on_external_subdoc_changed)
        except Exception:
            self._fs_watcher = None
        # Refresh watcher whenever the document changes
        QTimer.singleShot(500, self._refresh_subdoc_watcher)

    def closeEvent(self, ev):
        # v4.1.8: if this is a child window (embedded subdoc edit), notify
        # parent so it removes us from _child_editors (allows dedup to work
        # correctly on re-open)
        parent = getattr(self, '_parent_editor', None)
        if parent and hasattr(parent, '_child_editors'):
            try:
                if self in parent._child_editors:
                    parent._child_editors.remove(self)
            except Exception:
                pass
        # v4.1.2: warn if there are unsaved child subdoc windows
        if hasattr(self, '_child_editors') and self._child_editors:
            unsaved = [c for c in self._child_editors if getattr(c, '_modified', False)]
            if unsaved:
                ret = QMessageBox.question(
                    self, "Unsaved sub-documents",
                    f"{len(unsaved)} embedded document(s) have unsaved changes "
                    f"that will be lost when this window closes. Close anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if ret != QMessageBox.StandardButton.Yes:
                    ev.ignore(); return
        # Close all child editors
        if hasattr(self, '_child_editors'):
            for child in list(self._child_editors):
                try: child.close()
                except Exception: pass
        # v4.0.2/4.0.3: persist preferences across sessions
        try:
            self._settings.setValue("geometry", self.saveGeometry())
            self._settings.setValue("windowState", self.saveState())
            self._settings.setValue("snap_to_grid", bool(self._canvas._snap_to_grid))
            self._settings.setValue("show_align_guides", bool(self._canvas._show_align_guides))
            self._settings.setValue("margins_enabled", bool(self._canvas._margins_enabled))
            self._settings.setValue("recent_files", list(self._recent_files)[:10])
        except Exception:
            pass
        super().closeEvent(ev)

    def _add_recent(self, path):
        """v4.0.2: track recently opened files.
        v4.1.13.1: persist immediately so crash-recovery still shows recents."""
        if not path: return
        try:
            path = os.path.abspath(path)
        except Exception:
            return
        try: self._recent_files.remove(path)
        except ValueError: pass
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:10]
        # Persist now (cheap; avoids losing recents on crash)
        try:
            self._settings.setValue("recent_files", list(self._recent_files))
            self._settings.sync()
        except Exception:
            pass

    def _sync_view_actions(self):
        """v4.0.2/4.0.3: keep View menu checkboxes in sync with state."""
        if hasattr(self, "_act_snap_grid") and self._act_snap_grid is not None:
            self._act_snap_grid.setChecked(self._canvas._snap_to_grid)
        if hasattr(self, "_act_align_guides") and self._act_align_guides is not None:
            self._act_align_guides.setChecked(self._canvas._show_align_guides)
        if hasattr(self, "_act_margins") and self._act_margins is not None:
            self._act_margins.setChecked(self._canvas._margins_enabled)

    def _build_ui(self):
        self._canvas=EdofCanvas(self)
        self._canvas.objectSelected.connect(self._on_sel)
        self._canvas.objectChanged.connect(self._on_chg)
        # v4.1.22.13: keep the left panel's selected row in sync with the
        # actual current page on the canvas, including when the canvas
        # moves between pages on its own (cursor hop during repaginate,
        # _do_new_page after Ctrl+Enter, merge-with-previous backspace).
        self._canvas.pageChanged.connect(self._on_canvas_page_changed)
        self._canvas.zoomChanged.connect(self._on_zoom_changed)
        self.setCentralWidget(self._canvas)

        # Left: pages + objects (tabbed)
        left_tabs=QTabWidget()
        # Page list
        self._pg_list=QListWidget(); self._pg_list.setAlternatingRowColors(True)
        self._pg_list.currentRowChanged.connect(self._on_pg_sel)
        pl=QWidget(); pv=QVBoxLayout(pl); pv.setContentsMargins(4,4,4,4); pv.setSpacing(4)
        pv.addWidget(self._pg_list,1)
        ph=QHBoxLayout(); ba=QPushButton("+ Add"); ba.clicked.connect(self._add_page)
        bd=QPushButton("× Del"); bd.setObjectName("danger"); bd.clicked.connect(self._del_page)
        ph.addWidget(ba); ph.addWidget(bd); pv.addLayout(ph)
        left_tabs.addTab(pl,t('panel_pages'))
        # Object list
        self._obj_panel=ObjectListPanel(self._canvas)
        self._obj_panel.objectSelected.connect(self._on_obj_select)
        left_tabs.addTab(self._obj_panel,t('panel_objects'))
        ld=QDockWidget("",self); ld.setWidget(left_tabs)
        # v4.0.3: dock is movable + resizable (was Fixed)
        ld.setObjectName("LeftDock")
        ld.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                       QDockWidget.DockWidgetFeature.DockWidgetClosable)
        ld.setMinimumWidth(140)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,ld)
        self._left_dock = ld
        # v4.1.20: default left panel width increased by ~25% (175 → 220) so
        # object names and toggle buttons fit comfortably without scrolling.
        QTimer.singleShot(0, lambda: self.resizeDocks([ld], [220], Qt.Orientation.Horizontal))

        # Right: properties (scrollable)
        self._props=PropPanel(self._canvas); self._props.changed.connect(self._on_chg)
        scroll=QScrollArea(); scroll.setWidget(self._props); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # v4.1.9: ensure panel is never narrower than the spinboxes can fit
        scroll.setMinimumWidth(260)
        self._props.setMinimumWidth(240)
        rd=QDockWidget(t('panel_properties'),self); rd.setWidget(scroll)
        rd.setObjectName("RightDock")
        rd.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                       QDockWidget.DockWidgetFeature.DockWidgetClosable)
        rd.setMinimumWidth(240)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,rd)
        self._right_dock = rd
        QTimer.singleShot(0, lambda: self.resizeDocks([rd], [320], Qt.Orientation.Horizontal))

        self._lbl_zoom=QLabel("100%")
        # v4.1.18: status bar DPI indicator
        self._lbl_dpi = QLabel("—")
        self._lbl_dpi.setToolTip("Document target DPI (used for PDF/PNG export)")
        self._status=QStatusBar(); self.setStatusBar(self._status)
        self._status.addPermanentWidget(self._lbl_dpi)
        self._status.addPermanentWidget(self._lbl_zoom)
        self._build_toolbar(); self._build_menu()

    def _build_toolbar(self):
        tb=self.addToolBar("Main"); tb.setMovable(False); tb.setIconSize(QSize(16,16))
        # v4.2.11.33: shortcuts used to be registered on BOTH the toolbar and the
        # menu action (Ctrl+S, Ctrl+N, Ctrl+O, Ctrl+Z, ...). Qt treats a key
        # bound to two actions as AMBIGUOUS and fires neither, so those
        # shortcuts silently did nothing. Now there is a single registry: menu
        # actions register first (menus display the key natively), toolbar
        # actions only show the key in the tooltip and register afterwards only
        # if the key is still free.
        self._sc_reg = {}
        self._tb_deferred_sc = []
        def a(lbl, slot, key=None, tip=None, icon=None):
            ac=QAction(lbl,self); ac.triggered.connect(slot)
            if icon:
                _ic=uicon(icon)
                if not _ic.isNull(): ac.setIcon(_ic)
            if key:
                self._tb_deferred_sc.append((ac, key))
                if tip:
                    ac.setToolTip(f"{tip}  ({key})")
                    ac.setStatusTip(tip)
                else:
                    ac.setToolTip(key); ac.setStatusTip(key)
            elif tip:
                ac.setToolTip(tip); ac.setStatusTip(tip)
            tb.addAction(ac)
            return ac
        # v4.1.19: explicit Select / Hand tool buttons as a checkable group
        # so the active mode is visually obvious in the toolbar.
        def add_tool(lbl, slot, key=None, tip=None, icon=None):
            ac = QAction(lbl, self); ac.setCheckable(True)
            ac.triggered.connect(slot)
            if icon:
                _ic=uicon(icon)
                if not _ic.isNull(): ac.setIcon(_ic)
            if key:
                self._tb_deferred_sc.append((ac, key))
                ac.setToolTip(f"{tip}  ({key})" if tip else key)
                ac.setStatusTip(tip or key)
            elif tip:
                ac.setToolTip(tip); ac.setStatusTip(tip)
            tb.addAction(ac); return ac
        # v4.0.3: every toolbar button now has a descriptive tooltip
        # v4.2.7.3: custom UI icons (fall back to the emoji/text label if missing)
        a("📄", self._new_doc,                "Ctrl+N",  "New document", icon="new")
        a("📂", self._open_dlg,               "Ctrl+O",  "Open .edof file", icon="open")
        a("💾", self._save,                   "Ctrl+S",  "Save", icon="save")
        tb.addSeparator()
        a("↩",  self._undo,                   "Ctrl+Z",  "Undo", icon="undo")
        a("↪",  self._redo,                   "Ctrl+Y",  "Redo", icon="redo")
        tb.addSeparator()
        # v4.1.19: tool mode selectors (cursor / hand) — exclusive group.
        # v4.1.19.3: no single-letter shortcuts (V/H) — they were stealing
        # typed characters away from the inline text editor. The buttons
        # are clearly visible in the toolbar and clickable directly.
        self._act_select_tool = add_tool("↖", lambda: self._set_tool_mode("select"),
                                            None, "Select tool — click and drag to select/move objects", icon="select")
        self._act_hand_tool   = add_tool("✋", lambda: self._set_tool_mode("hand"),
                                            None, "Hand tool — drag the canvas to pan", icon="hand")
        self._act_select_tool.setChecked(True)   # default
        tb.addSeparator()
        a("T",  self._ins_textbox,             tip="Insert text box", icon="text")
        a("🖼", self._ins_image,                tip="Insert image", icon="image")
        a("⬜", lambda:self._ins_shape("rect"),    tip="Insert rectangle", icon="rect")
        a("⬭", lambda:self._ins_shape("ellipse"), tip="Insert ellipse", icon="ellipse")
        a("╱",  self._ins_line,                tip="Insert line", icon="line")
        a("⬛", self._ins_qr,                   tip="Insert QR code", icon="qr")
        # v4.0.3: new insert tools
        a("⊞",  self._ins_table,               tip="Insert table…", icon="table")
        a("📄", self._ins_subdoc,              tip="Insert embedded EDOF sub-document (v4.1.2)", icon="subdoc")
        a("✎",  self._ins_path,                tip="Pen tool — click=corner, click+drag=curve handle (Esc to cancel)", icon="pen")
        a("⟨S⟩", self._ins_svg,                tip="Import SVG (raster display; double-click to convert)", icon="svg")
        tb.addSeparator()
        a("🔍+",lambda:self._zoom_step(1.25),  "Ctrl+=", "Zoom in", icon="zoom-in")
        a("🔍-",lambda:self._zoom_step(1/1.25),"Ctrl+-", "Zoom out", icon="zoom-out")
        a("Fit",self._zoom_fit,                "Ctrl+0", "Fit page to window", icon="fit")
        tb.addSeparator()
        a("⧉",  self._dup_obj,                 "Ctrl+D", "Duplicate selected object", icon="duplicate")
        a("🗑", self._del_obj,                 "Delete", "Delete selected object", icon="delete")
        tb.addSeparator()
        a("PNG",self._export_png,              tip="Export current page as PNG", icon="export")
        a("PDF",self._export_pdf,              tip="Export document as PDF…", icon="pdf")
        a("📊 CSV",self._batch_csv,            tip="Batch generate from CSV", icon="csv")

        # v4.1.20: paragraph-style dropdown for document mode. Shown always
        # but only relevant when the current doc has mode == 'document' and
        # the user is editing the body. Applying a style writes preset
        # font_size + bold + alignment into the textbox style and the
        # currently selected runs (or all runs if no selection).
        from PyQt6.QtWidgets import QComboBox
        tb.addSeparator()
        self._cb_para_style = QComboBox()
        self._cb_para_style.setMinimumWidth(110)
        self._cb_para_style.setToolTip(
            "Paragraph style preset (Word-like). Applies to the body text "
            "in document mode."
        )
        # Built-in style presets from document_body.default_paragraph_styles
        for label in ("Normal", "Title", "Heading 1", "Heading 2",
                        "Heading 3", "Quote", "Code"):
            self._cb_para_style.addItem(label)
        self._cb_para_style.currentTextChanged.connect(self._apply_para_style)
        tb.addWidget(self._cb_para_style)

    def _apply_para_style(self, style_label: str):
        """v4.1.20: apply a paragraph style preset to the body textbox.

        Maps Word-style names to TextStyle + run defaults. Currently writes
        the style to the parent textbox style (whole-textbox scope). Per-
        paragraph selection scope is deferred to 4.1.21 when document_flow
        is wired into the canvas renderer."""
        if not self.doc: return
        # Find target object: prefer body, fall back to current selection
        target = None
        if getattr(self.doc, 'mode', '') == 'document':
            for page in self.doc.pages:
                for obj in page.objects:
                    if getattr(obj, 'name', '') in ('document_body', 'doc_body'):
                        target = obj
                        break
                if target: break
        if target is None:
            sel_id = self._canvas.get_sel_id() if hasattr(self, '_canvas') else None
            if sel_id:
                target = self._canvas._cur_page().get_object(sel_id) if self._canvas._cur_page() else None
        if target is None or not isinstance(target, edof.TextBox): return
        # Style preset map (mm font sizes)
        presets = {
            "Normal":    dict(font_size=3.881, bold=False, italic=False, alignment="left",  line_height=1.15),
            "Title":     dict(font_size=10.583, bold=True,  italic=False, alignment="center", line_height=1.20),
            "Heading 1": dict(font_size=7.408,  bold=True,  italic=False, alignment="left",  line_height=1.20),
            "Heading 2": dict(font_size=5.644,  bold=True,  italic=False, alignment="left",  line_height=1.20),
            "Heading 3": dict(font_size=4.586,  bold=True,  italic=False, alignment="left",  line_height=1.20),
            "Quote":     dict(font_size=3.881, bold=False, italic=True,  alignment="left",  line_height=1.30),
            "Code":      dict(font_size=3.528, bold=False, italic=False, alignment="left",  line_height=1.10),
        }
        preset = presets.get(style_label)
        if not preset: return
        for k, v in preset.items():
            setattr(target.style, k, v)
        # Also push into runs (so newly typed text uses the style)
        if hasattr(target, 'runs') and target.runs:
            for run in target.runs:
                run.bold   = preset.get('bold')
                run.italic = preset.get('italic')
                run.font_size = preset.get('font_size')
        # Refresh inline editor if it's active
        try:
            inl = getattr(self._canvas, '_inline_widget', None)
            inl_obj = getattr(self._canvas, '_inline_obj', None)
            if inl is not None and inl_obj is target:
                inl._invalidate()
        except Exception:
            pass
        self._canvas.schedule_render()
        self._mark_modified()

    def _reg_sc(self, ac, key):
        """Register a shortcut exactly once window-wide. A key bound to two
        QActions is ambiguous in Qt and fires NEITHER, so duplicates are
        silently skipped (the duplicate keeps its tooltip/menu text only)."""
        try:
            ks = QKeySequence(key); s = ks.toString()
            if not s or s in self._sc_reg:
                return False
            self._sc_reg[s] = ac
            ac.setShortcut(ks)
            return True
        except Exception:
            return False

    def _build_menu(self):
        mb=self.menuBar()
        def m(tk): return mb.addMenu(t(tk))
        def a(mn,tk,slot,key=None,sep=False):
            if sep: mn.addSeparator(); return
            ac=QAction(t(tk),self); ac.triggered.connect(slot)
            if key: self._reg_sc(ac, key)
            mn.addAction(ac)
        fm=m('menu_file')
        a(fm,'new',self._new_doc,"Ctrl+N"); a(fm,'open',self._open_dlg,"Ctrl+O")
        # v4.0.1: New from template
        new_tpl_act=QAction("New from Template…",self)
        new_tpl_act.triggered.connect(self._new_from_template)
        fm.addAction(new_tpl_act)
        # v4.0.1: Import PDF
        imp_act=QAction("Import PDF…",self)
        imp_act.triggered.connect(self._import_pdf)
        fm.addAction(imp_act)
        # v4.0.3: Import RTF
        imp_rtf=QAction("Import RTF…",self)
        imp_rtf.triggered.connect(self._import_rtf)
        fm.addAction(imp_rtf)
        # v4.1.24.0: Import Word (.docx)
        imp_docx=QAction("Import Word (.docx)…",self)
        imp_docx.triggered.connect(self._import_docx)
        fm.addAction(imp_docx)
        # v4.1.0: Import custom font (.ttf, .otf)
        imp_font=QAction("Import Font…",self)
        imp_font.triggered.connect(self._import_font)
        fm.addAction(imp_font)
        a(fm,sep=True,tk="",slot=None)
        a(fm,'save',self._save,"Ctrl+S"); a(fm,'save_as',self._save_as,"Ctrl+Shift+S")
        # v4.0.1: Save as v3 (downgrade)
        save_3x_act=QAction("Save as v3 (downgrade)…",self)
        save_3x_act.triggered.connect(self._save_as_v3)
        fm.addAction(save_3x_act)
        a(fm,sep=True,tk="",slot=None)
        a(fm,'export_png',self._export_png); a(fm,'export_all',self._export_all)
        a(fm,'export_pdf',self._export_pdf)
        # v4.0.1: SVG export
        svg_act=QAction("Export SVG…",self)
        svg_act.triggered.connect(self._export_svg)
        fm.addAction(svg_act)
        # v4.0.3: Export RTF
        rtf_act=QAction("Export RTF…",self)
        rtf_act.triggered.connect(self._export_rtf)
        fm.addAction(rtf_act)
        # v4.1.24.0: Export Word (.docx)
        docx_act=QAction("Export Word (.docx)…",self)
        docx_act.triggered.connect(self._export_docx)
        fm.addAction(docx_act)
        a(fm,'batch_csv',self._batch_csv)
        # v4.1.17.1: CSV template generator — emit a blank CSV with columns
        # matching the document's variable names (only objects that have a
        # variable attached, deduped).
        csvtpl_act = QAction("Generate CSV Template…", self)
        csvtpl_act.triggered.connect(self._gen_csv_template)
        fm.addAction(csvtpl_act)
        a(fm,sep=True,tk="",slot=None)
        a(fm,'print',self._print); a(fm,sep=True,tk="",slot=None); a(fm,'quit',self.close,"Ctrl+Q")
        em=m('menu_edit')
        a(em,'undo',self._undo,"Ctrl+Z"); a(em,'redo',self._redo,"Ctrl+Y")
        a(em,sep=True,tk="",slot=None); a(em,'duplicate',self._dup_obj,"Ctrl+D"); a(em,'delete',self._del_obj,"Delete")
        a(em,sep=True,tk="",slot=None)
        a(em,'find_replace',self._find_replace,"Ctrl+F")
        # v4.0.1: gradient editor
        grad_act=QAction("Gradient Editor…",self)
        grad_act.triggered.connect(self._gradient_editor)
        em.addAction(grad_act)
        im=m('menu_insert')
        a(im,'text_box',self._ins_textbox); a(im,'image',self._ins_image)
        a(im,'rectangle',lambda:self._ins_shape("rect")); a(im,'ellipse',lambda:self._ins_shape("ellipse"))
        a(im,'line',self._ins_line); a(im,'qr_code',self._ins_qr)
        # v4.1.3: Add missing items
        a(im,sep=True,tk="",slot=None)
        path_act = QAction("Pen tool (path)…", self)
        # v4.1.19.3: no single-letter shortcut — was stealing "p" away from
        # text input in inline editor.
        path_act.triggered.connect(self._ins_path)
        im.addAction(path_act)
        table_act = QAction("Table…", self)
        table_act.triggered.connect(self._ins_table)
        im.addAction(table_act)
        subdoc_act = QAction("Embedded EDOF sub-document…", self)
        subdoc_act.triggered.connect(self._ins_subdoc)
        im.addAction(subdoc_act)
        pm=m('menu_page')
        a(pm,'add_page',self._add_page); a(pm,'dup_page',self._dup_page)
        a(pm,'del_page',self._del_page); a(pm,sep=True,tk="",slot=None); a(pm,'page_settings',self._page_settings)
        dm=m('menu_document')
        a(dm,'variables',self._show_vars); a(dm,'doc_info',self._doc_info); a(dm,'validate',self._validate)
        # v4.0.1: encryption / protection
        a(dm,sep=True,tk="",slot=None)
        unlock_act=QAction("Unlock for editing…",self)
        self._reg_sc(unlock_act, "Ctrl+Shift+L")
        unlock_act.triggered.connect(self._show_unlock_dialog)
        dm.addAction(unlock_act)
        protect_act=QAction("Protection…",self)
        protect_act.triggered.connect(self._show_protection_dialog)
        dm.addAction(protect_act)
        relock_act=QAction("Re-lock (forget password)",self)
        relock_act.triggered.connect(self._relock_doc)
        dm.addAction(relock_act)
        vm=m('menu_view')
        a(vm,'zoom_in',lambda:self._zoom_step(1.25),"Ctrl+=")
        a(vm,'zoom_out',lambda:self._zoom_step(1/1.25),"Ctrl+-")
        a(vm,'fit_page',self._zoom_fit,"Ctrl+0")
        a(vm,sep=True,tk="",slot=None)
        # v4.0.1: snap-to-grid toggle
        snap_act=QAction("Snap to Grid",self)
        snap_act.setCheckable(True); self._reg_sc(snap_act, "Ctrl+G")
        def _toggle_snap(chk):
            self._canvas._snap_to_grid = chk
            self._canvas.viewport().update()  # v4.1.0: redraw grid dots
        snap_act.triggered.connect(_toggle_snap)
        vm.addAction(snap_act)
        self._act_snap_grid = snap_act   # v4.0.2: keep reference for state sync
        # v4.1.10.2: Grid size dialog (mm, 2 decimals)
        grid_size_act = QAction("Grid Size…", self)
        grid_size_act.triggered.connect(self._set_grid_size_dlg)
        vm.addAction(grid_size_act)
        # v4.0.1: alignment guides toggle
        align_act=QAction("Show Alignment Guides",self)
        align_act.setCheckable(True); align_act.setChecked(True)
        def _toggle_align(chk):
            self._canvas._show_align_guides = chk
            self._canvas.viewport().update()
        align_act.triggered.connect(_toggle_align)
        vm.addAction(align_act)
        self._act_align_guides = align_act   # v4.0.2

        # v4.0.3: margin snap toggle + setup
        margin_act=QAction("Use Page Margins (snap)", self)
        margin_act.setCheckable(True)
        margin_act.triggered.connect(self._toggle_margins)
        vm.addAction(margin_act)
        self._act_margins = margin_act
        margin_set_act=QAction("Set Margins…", self)
        margin_set_act.triggered.connect(self._set_margins_dlg)
        vm.addAction(margin_set_act)

        vm.addSeparator()
        # v4.2.10.11: render performance / optimization toggles
        perf_act = QAction("Performance / optimizations…", self)
        perf_act.triggered.connect(self._open_perf_settings)
        vm.addAction(perf_act)
        # v4.0.3: reset panels
        reset_panels_act=QAction("Reset Panel Layout", self)
        reset_panels_act.triggered.connect(self._reset_panels)
        vm.addAction(reset_panels_act)

        # v4.0.3 / v4.1.0: Help menu
        hm=mb.addMenu("&Help")
        sk_act=QAction("Keyboard Shortcuts…", self)
        self._reg_sc(sk_act, "F1")
        sk_act.triggered.connect(self._show_shortcuts)
        hm.addAction(sk_act)
        # v4.1.23.37: editable shortcut customization
        cust_sk_act=QAction("Customize Shortcuts…", self)
        cust_sk_act.triggered.connect(self._edit_shortcuts)
        hm.addAction(cust_sk_act)
        # v4.1.0: full help guide (multi-page)
        guide_act=QAction("Help Guide…", self)
        self._reg_sc(guide_act, "F2")
        guide_act.triggered.connect(self._show_help_guide)
        hm.addAction(guide_act)
        hm.addSeparator()
        # v4.1.0: donate
        # v4.1.1: file association management
        assoc_act = QAction("File association (.edof)…", self)
        assoc_act.triggered.connect(self._open_file_assoc_dialog)
        hm.addAction(assoc_act)
        hm.addSeparator()
        donate_act=QAction("💖 Support the developer…", self)
        donate_act.triggered.connect(self._open_donate)
        hm.addAction(donate_act)
        hm.addSeparator()
        # v4.2.10.7: in-app debug logging toggle, independent of how the editor
        # was launched (file association / shortcut / entry point). Removes all
        # dependence on EDOF_DEBUG env / launcher batch quoting.
        try:
            from edof.engine.debug_log import is_enabled as _dbg_on
            _dbg_state = bool(_dbg_on())
        except Exception:
            _dbg_state = False
        self._dbg_log_act = QAction("Debug log (curves/keys)", self)
        self._dbg_log_act.setCheckable(True)
        self._dbg_log_act.setChecked(_dbg_state)
        self._dbg_log_act.triggered.connect(self._toggle_debug_log)
        hm.addAction(self._dbg_log_act)
        open_log_act = QAction("Open debug log location…", self)
        open_log_act.triggered.connect(self._open_debug_log_location)
        hm.addAction(open_log_act)
        hm.addSeparator()
        about_act=QAction("About edof…", self)
        about_act.triggered.connect(self._show_about)
        hm.addAction(about_act)
        # v4.2.11.33: register toolbar shortcuts LAST -- only keys the menu did
        # not claim get bound here, so no key is ever ambiguous (= dead).
        for _ac, _key in getattr(self, '_tb_deferred_sc', []):
            self._reg_sc(_ac, _key)

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _debug_log_path(self):
        """Resolve where the debug log lives: EDOF_DEBUG_PATH if set, else the
        debug_log module default (user home / edof_debug.log)."""
        import os as _os
        try:
            from edof.engine.debug_log import current_path as _cp
            return _os.path.abspath(_cp())
        except Exception:
            return _os.path.abspath(
                _os.environ.get("EDOF_DEBUG_PATH")
                or _os.path.join(_os.path.expanduser("~"), "edof_debug.log"))

    def _toggle_debug_log(self, checked):
        """v4.2.10.7: enable/disable detailed curve+key logging from the menu,
        regardless of how the editor was launched. On enable, the log file is
        created immediately and its exact path is shown."""
        from PyQt6.QtWidgets import QMessageBox
        import os as _os
        try:
            from edof.engine import debug_log as _dl
        except Exception as e:
            QMessageBox.warning(self, "Debug log", f"Debug log unavailable: {e}")
            return
        if checked:
            # honour an explicit EDOF_DEBUG_PATH; otherwise use the module default
            path = _os.environ.get("EDOF_DEBUG_PATH") or None
            _dl.enable(path)   # writes a LOG.ENABLED line, creating the file
            _dl.log("editor.startup", version=edof.__version__,
                    log_path=_dl.current_path(), source="menu")
            real = self._debug_log_path()
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("Debug log enabled")
            box.setText("Detailed curve / key logging is ON.\n\n"
                        "Draw and edit with the pen tool, then close the editor "
                        "and send this file:")
            box.setInformativeText(real)
            open_btn = box.addButton("Open folder", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Ok)
            box.exec()
            if box.clickedButton() is open_btn:
                self._open_debug_log_location()
        else:
            _dl.log("editor.debug.disabled")
            _dl.disable()
            QMessageBox.information(self, "Debug log",
                                    "Debug logging turned off.")

    def _open_debug_log_location(self):
        """Open the folder that contains the debug log (creating the file first
        if logging is on but nothing has been written yet)."""
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        import os as _os
        path = self._debug_log_path()
        folder = _os.path.dirname(path) or "."
        exists = _os.path.exists(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        msg = f"Debug log path:\n{path}\n\n"
        msg += ("File exists." if exists else
                "File not created yet. Enable 'Debug log (curves/keys)' in the "
                "Help menu, then draw with the pen tool.")
        QMessageBox.information(self, "Debug log location", msg)

    def _on_sel(self,obj):
        self._props.load(obj)
        self._obj_panel.refresh()
        if obj: self._obj_panel.select(obj.id)
        # v4.1.20.5: in document mode, when nothing is selected (e.g. user
        # clicked empty page area or finished interacting with a just-placed
        # object), automatically resume inline edit on the body textbox so
        # the cursor returns there rather than disappearing into nowhere.
        # v4.1.20.9: track the pending auto-return timer so a follow-up
        # selection (e.g. user clicks an object right after deselect) can
        # cancel it — without this the body would yank back into edit
        # 120 ms after the user picked something else.
        pending = getattr(self, '_auto_return_timer', None)
        if pending is not None:
            try: pending.stop()
            except Exception: pass
            self._auto_return_timer = None
        if (obj is None and self.doc is not None
            and getattr(self.doc, 'mode', '') == 'document'
            and self._canvas._inline_widget is None):
            cur_pg = self._canvas._cur_page()
            if cur_pg is not None:
                body = None
                for o in cur_pg.objects:
                    name = getattr(o, 'name', '') or ''
                    if name in ('document_body', 'doc_body') or name.startswith('doc_body'):
                        body = o; break
                if body is not None:
                    from PyQt6.QtCore import QTimer
                    timer = QTimer(self)
                    timer.setSingleShot(True)
                    def _do_return(b=body, t=timer):
                        # Only fire if still nothing selected and no inline
                        # widget appeared in the meantime
                        if (self._canvas.get_sel_id() is None
                            and self._canvas._inline_widget is None):
                            self._canvas.set_sel_id(b.id)
                            self._canvas._start_inline(b)
                        self._auto_return_timer = None
                    timer.timeout.connect(_do_return)
                    timer.start(120)
                    self._auto_return_timer = timer

    def _on_chg(self):
        self._modified=True; self._upd_title()
        self._obj_panel.refresh()
        # v4.2.10.13: record this object edit as a coalesced history step.
        if self.doc is not None and not self._suppress_obj_history:
            self._obj_pending = True
            self._obj_commit_timer.start(self._obj_commit_delay)

    def _commit_pending_obj(self):
        """Flush a coalesced object-edit burst into one history step."""
        self._obj_commit_timer.stop()
        if not self._obj_pending or self.doc is None:
            self._obj_pending = False
            return
        self._obj_pending = False
        # Body burst (if any) must land before this object step for correct order.
        self._commit_pending_body()
        self.history.push(self.doc, None, "Edit")
        self._modified = True; self._upd_title()

    def _arm_history_suppression(self):
        """v4.2.10.13: after a programmatic doc load/reset, swallow the refresh
        signals (objectChanged/changed) so they don't record a spurious history
        step. Cleared on the next event-loop turn once signals have drained."""
        from PyQt6.QtCore import QTimer
        self._suppress_obj_history = True
        self._obj_pending = False
        try: self._obj_commit_timer.stop()
        except Exception: pass
        QTimer.singleShot(0, lambda: setattr(self, '_suppress_obj_history', False))

    def _on_pg_sel(self,idx):
        if self.doc and 0<=idx<len(self.doc.pages):
            # v4.1.23.24: every page-list click switches AND moves the caret
            # onto the page (caret at its start). The earlier Ctrl="view only,
            # don't move caret" variant left the caret with no active editor,
            # which could strand it outside the margin — not worth reopening
            # the margin edge cases, so it's removed.
            self._canvas.set_page(idx)

    def _on_canvas_page_changed(self, idx: int):
        """v4.1.22.13: keep the left page list selection in sync with the
        canvas. Block signals so we don't loop back into _on_pg_sel which
        would call set_page again."""
        try:
            from edof.engine.debug_log import log as _dlog
            _dlog("mw.canvas_page_changed",
                   idx=idx,
                   list_count=self._pg_list.count() if hasattr(self, '_pg_list') else -1,
                   list_current=self._pg_list.currentRow() if hasattr(self, '_pg_list') else -1)
        except Exception: pass
        if not hasattr(self, '_pg_list'): return
        if 0 <= idx < self._pg_list.count():
            self._pg_list.blockSignals(True)
            try:
                self._pg_list.setCurrentRow(idx)
            finally:
                self._pg_list.blockSignals(False)
        try: self._upd_title()   # refresh DPI/mm/px status for the new page
        except Exception: pass

    def _on_obj_select(self,oid):
        # v4.1.20.8: when Objects panel selects an object in document mode
        # that is NOT the inline-edit target (typically a shape/image the
        # user inserted and wants to manipulate), commit the active body
        # edit and suppress sticky-reentry. Without this the inline editor
        # stays open with body focus, blocking interaction with the picked
        # object.
        canvas = self._canvas
        if (canvas._inline_widget is not None
            and canvas._inline_id != oid
            and self.doc is not None
            and getattr(self.doc, 'mode', '') == 'document'):
            canvas._skip_sticky_reentry = True
            try: canvas._inline_widget.commit_to_textbox()
            except Exception: canvas._after_inline_commit()
        canvas.set_sel_id(oid)

    # ── Document ──────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────
    # v4.1.5: Welcome / Start screen
    # ─────────────────────────────────────────────────────────────────────
    def _show_welcome_screen(self):
        """Display a welcome overlay with a big New Document button and
        recent files list. Hidden as soon as the user creates or opens a doc."""
        if getattr(self, '_welcome_widget', None):
            try: self._welcome_widget.show(); self._welcome_widget.raise_(); return
            except Exception: pass

        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        w = QWidget(self)
        w.setAutoFillBackground(True)
        w.setStyleSheet(f"QWidget#welcome_root {{background:{PBG};}}")
        w.setObjectName("welcome_root")
        outer = QHBoxLayout(w); outer.setContentsMargins(40, 40, 40, 40); outer.setSpacing(40)

        # Left side: huge "New Document" button
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0,0,0,0); lv.setSpacing(16)
        title = QLabel(f"edof <small>{edof.__version__}</small>")
        title.setStyleSheet(f"font:bold 28pt 'Segoe UI';color:{FG};")
        sub = QLabel("Easy Document Format — design, fill, export")
        sub.setStyleSheet(f"font:12pt 'Segoe UI';color:{FGD};")
        lv.addWidget(title); lv.addWidget(sub); lv.addSpacing(20)

        btn_new = QPushButton("📄  New Document")
        btn_new.setFixedHeight(80); btn_new.setMinimumWidth(280)
        btn_new.setStyleSheet(
            f"QPushButton{{background:{ACC};color:white;font:bold 18pt 'Segoe UI';"
            "border:none;border-radius:6px;padding:14px;}}"
            f"QPushButton:hover{{background:#5a5acc;}}")
        btn_new.clicked.connect(self._welcome_new)
        lv.addWidget(btn_new)

        btn_open = QPushButton("📂  Open Document…")
        btn_open.setFixedHeight(50); btn_open.setMinimumWidth(280)
        btn_open.setStyleSheet(
            "QPushButton{background:#2a2a3a;color:#ddd;font:12pt 'Segoe UI';"
            "border:1px solid #555;border-radius:5px;padding:10px;}"
            "QPushButton:hover{background:#3a3a4a;}")
        btn_open.clicked.connect(self._welcome_open)
        lv.addWidget(btn_open)
        lv.addStretch()

        outer.addWidget(left, 1)

        # Right side: recent files
        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(0,0,0,0); rv.setSpacing(8)
        recent_title = QLabel("Recent files")
        recent_title.setStyleSheet(f"font:bold 13pt 'Segoe UI';color:{FG};")
        rv.addWidget(recent_title)

        recent_list = QListWidget()
        recent_list.setStyleSheet(
            f"QListWidget{{background:{PBG2};color:{FG};border:1px solid #444;"
            "border-radius:5px;font:11pt 'Segoe UI';padding:4px;}}"
            f"QListWidget::item{{padding:8px 10px;border-bottom:1px solid #333;}}"
            f"QListWidget::item:hover{{background:#3a3a5a;}}"
            f"QListWidget::item:selected{{background:{ACC};color:white;}}")
        # Populate with recent files (defensive: filter to existing files only)
        any_recent = False
        for path in (self._recent_files or []):
            if not path or not os.path.isfile(path): continue
            it = QListWidgetItem(f"{os.path.basename(path)}\n  {os.path.dirname(path)}")
            it.setData(Qt.ItemDataRole.UserRole, path)
            recent_list.addItem(it); any_recent = True
        if not any_recent:
            it = QListWidgetItem("(no recent files yet)")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            recent_list.addItem(it)
        recent_list.itemDoubleClicked.connect(
            lambda item: self._welcome_open_recent(item))
        rv.addWidget(recent_list, 1)

        outer.addWidget(right, 1)

        # Place over central widget
        cw = self.centralWidget()
        if cw is None:
            self.setCentralWidget(w)
            self._welcome_widget = w
            return
        # v4.1.13.1: parent + cover full central widget area. Force a
        # geometry update both immediately AND on next event loop tick so
        # the rectangle stretches properly even before window is shown.
        w.setParent(cw)
        w.setGeometry(cw.rect())
        w.show(); w.raise_()
        self._welcome_widget = w
        # Geometry keep-in-sync via resize hook
        old_resize = cw.resizeEvent
        def _new_resize(ev):
            if old_resize: old_resize(ev)
            if self._welcome_widget:
                self._welcome_widget.setGeometry(0, 0, cw.width(), cw.height())
        cw.resizeEvent = _new_resize
        # Defer one more resize for after the main window has been shown
        from PyQt6.QtCore import QTimer as _QT
        _QT.singleShot(0, lambda: self._welcome_widget
                       and self._welcome_widget.setGeometry(cw.rect()))
        _QT.singleShot(50, lambda: self._welcome_widget
                       and self._welcome_widget.setGeometry(cw.rect()))

    def _close_welcome(self):
        if getattr(self, '_welcome_widget', None):
            try:
                self._welcome_widget.hide()
                self._welcome_widget.deleteLater()
            except Exception: pass
            self._welcome_widget = None

    def _welcome_new(self):
        self._close_welcome()
        self._new_doc()

    def _welcome_open(self):
        self._close_welcome()
        self._open_dlg()

    def _welcome_open_recent(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path: return
        self._close_welcome()
        if os.path.isfile(path):
            self._open_file(path)

    def _new_doc(self):
        if not self._confirm(): return
        # v4.1.0: dialog with paper / video sizes + modes
        from PyQt6.QtWidgets import QGroupBox, QListWidget, QListWidgetItem, QRadioButton
        dlg=QDialog(self); dlg.setWindowTitle("New Document"); dlg.setStyleSheet(QSS)
        dlg.resize(480, 480)
        v=QVBoxLayout(dlg)

        # Mode selection
        mode_grp=QGroupBox("Mode")
        mv=QVBoxLayout(mode_grp)
        rb_empty=QRadioButton("Empty document — fixed-position objects (default)")
        rb_empty.setChecked(True)
        rb_doc=QRadioButton("Document — auto margins (15mm), word-style flow editing")
        mv.addWidget(rb_empty); mv.addWidget(rb_doc)
        v.addWidget(mode_grp)

        # Preset selection
        pres_grp=QGroupBox("Size (a preset just fills the W / H / DPI fields below)")
        pl=QVBoxLayout(pres_grp)
        list_presets=QListWidget()
        # Paper sizes
        paper=[
            ("A0  (841 × 1189 mm, portrait)",  841.0, 1189.0),
            ("A1  (594 × 841 mm,  portrait)",  594.0, 841.0),
            ("A2  (420 × 594 mm,  portrait)",  420.0, 594.0),
            ("A3  (297 × 420 mm,  portrait)",  297.0, 420.0),
            ("A4  (210 × 297 mm,  portrait)",  210.0, 297.0),
            ("A4  (297 × 210 mm,  landscape)", 297.0, 210.0),
            ("A5  (148 × 210 mm,  portrait)",  148.0, 210.0),
            ("A6  (105 × 148 mm,  portrait)",  105.0, 148.0),
            ("US Letter (216 × 279 mm)",       215.9, 279.4),
            ("US Letter (279 × 216 mm, landscape)", 279.4, 215.9),
            ("US Legal (216 × 356 mm)",        215.9, 355.6),
            ("Tabloid (279 × 432 mm)",         279.4, 431.8),
            ("Business card (85 × 55 mm)",     85.0,  55.0),
            ("Postcard (148 × 105 mm)",        148.0, 105.0),
        ]
        # Video sizes — convert px @ 72 dpi to mm
        # 1 inch = 25.4 mm; 1 px @ 72 dpi = 25.4/72 mm
        px_to_mm = 25.4 / 72.0
        video=[
            ("HD 1280 × 720 (720p)",                1280 * px_to_mm,  720 * px_to_mm),
            ("Full HD 1920 × 1080 (1080p)",         1920 * px_to_mm, 1080 * px_to_mm),
            ("4K UHD 3840 × 2160",                  3840 * px_to_mm, 2160 * px_to_mm),
            ("Cinema 4K 4096 × 2160",               4096 * px_to_mm, 2160 * px_to_mm),
            ("8K UHD 7680 × 4320",                  7680 * px_to_mm, 4320 * px_to_mm),
            ("Square 1080 × 1080 (Instagram)",      1080 * px_to_mm, 1080 * px_to_mm),
            ("Story 1080 × 1920 (Instagram/TikTok)",1080 * px_to_mm, 1920 * px_to_mm),
            ("YouTube thumbnail 1280 × 720",        1280 * px_to_mm,  720 * px_to_mm),
            ("Twitter post 1200 × 675",             1200 * px_to_mm,  675 * px_to_mm),
        ]

        # Group headers
        hdr1=QListWidgetItem("── Paper ──"); hdr1.setFlags(Qt.ItemFlag.NoItemFlags); list_presets.addItem(hdr1)
        for name, w, h in paper:
            it=QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, ("paper", w, h))
            list_presets.addItem(it)
        hdr2=QListWidgetItem("── Video / Screen ──"); hdr2.setFlags(Qt.ItemFlag.NoItemFlags); list_presets.addItem(hdr2)
        for name, w, h in video:
            it=QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, ("video", w, h))
            list_presets.addItem(it)
        hdr3=QListWidgetItem("── Custom ──"); hdr3.setFlags(Qt.ItemFlag.NoItemFlags); list_presets.addItem(hdr3)
        custom_it=QListWidgetItem("Custom size…")
        custom_it.setData(Qt.ItemDataRole.UserRole, ("custom", None, None))
        list_presets.addItem(custom_it)
        # Default: A4 portrait
        list_presets.setCurrentRow(5)
        pl.addWidget(list_presets)
        v.addWidget(pres_grp)

        # Custom size inputs (shown when "Custom size" picked)
        cust_w=QWidget(); hcw=QHBoxLayout(cust_w); hcw.setContentsMargins(8,0,0,0)
        sp_cw=QDoubleSpinBox(); sp_cw.setRange(1, 5000); sp_cw.setValue(210); sp_cw.setSuffix(" mm")
        sp_ch=QDoubleSpinBox(); sp_ch.setRange(1, 5000); sp_ch.setValue(297); sp_ch.setSuffix(" mm")
        sp_dpi=QSpinBox(); sp_dpi.setRange(1, 9600); sp_dpi.setValue(300); sp_dpi.setSuffix(" DPI")
        sp_dpi.setToolTip("Custom DPI is respected: once you change it, picking a "
                          "preset will not overwrite it.")
        hcw.addWidget(QLabel("W:")); hcw.addWidget(sp_cw)
        hcw.addWidget(QLabel("H:")); hcw.addWidget(sp_ch)
        hcw.addWidget(QLabel("DPI:")); hcw.addWidget(sp_dpi)
        v.addWidget(cust_w)

        # v4.2.5: presets just PREFILL these fields; the document is always
        # created from the W/H/DPI fields below, so whatever the user types
        # wins (previously a preset row overrode the typed values). The DPI is
        # only suggested by a preset until the user sets their own value, then
        # it is left untouched so a custom DPI sticks.
        _dpi_touched = [False]
        _prog = [False]
        def _on_dpi_changed(_v):
            if not _prog[0]:
                _dpi_touched[0] = True
        sp_dpi.valueChanged.connect(_on_dpi_changed)

        def _prefill_from_preset(cur, _prev=None):
            if cur is None:
                return
            data = cur.data(Qt.ItemDataRole.UserRole)
            if not data:
                return
            kind, pw, ph = data
            if kind == "custom":
                return  # keep whatever the user has typed
            _prog[0] = True
            sp_cw.setValue(round(float(pw), 2))
            sp_ch.setValue(round(float(ph), 2))
            if not _dpi_touched[0]:
                sp_dpi.setValue(300 if kind == "paper" else 72)
            _prog[0] = False
        list_presets.currentItemChanged.connect(_prefill_from_preset)
        _prefill_from_preset(list_presets.currentItem())

        # v4.1.3: Background option
        from PyQt6.QtWidgets import QGroupBox as _QGB
        bg_grp = _QGB("Background")
        bgv = QHBoxLayout(bg_grp); bgv.setContentsMargins(10, 10, 10, 10); bgv.setSpacing(8)
        rb_bg_white = QRadioButton("White")
        rb_bg_white.setChecked(True)
        rb_bg_transp = QRadioButton("Transparent")
        rb_bg_transp.setToolTip("Transparent renders as a checkerboard in the editor")
        rb_bg_custom = QRadioButton("Custom…")
        custom_color = [255, 255, 255, 255]
        btn_bg_pick = QPushButton(); btn_bg_pick.setFixedSize(36, 22)
        btn_bg_pick.setStyleSheet("background:#ffffff;border:1px solid #888;border-radius:3px;")
        def _pick_custom():
            new_c = EdofColorDialog.get_color(dlg, tuple(custom_color), alpha=True)
            if new_c is not None:
                custom_color[0]=new_c[0]; custom_color[1]=new_c[1]
                custom_color[2]=new_c[2]; custom_color[3]=new_c[3]
                btn_bg_pick.setStyleSheet(
                    f"background:#{new_c[0]:02x}{new_c[1]:02x}{new_c[2]:02x};"
                    "border:1px solid #888;border-radius:3px;")
                rb_bg_custom.setChecked(True)
        btn_bg_pick.clicked.connect(_pick_custom)
        bgv.addWidget(rb_bg_white); bgv.addWidget(rb_bg_transp)
        bgv.addWidget(rb_bg_custom); bgv.addWidget(btn_bg_pick); bgv.addStretch()
        v.addWidget(bg_grp)

        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); v.addWidget(bb)
        if dlg.exec()!=QDialog.DialogCode.Accepted: return

        # Resolve size — ALWAYS from the W/H/DPI fields (presets only prefill
        # them), so the user's typed values are never silently overridden.
        item = list_presets.currentItem()
        w = sp_cw.value(); h = sp_ch.value()
        dpi = sp_dpi.value()
        if w <= 0 or h <= 0:
            return

        title = "Untitled"
        new_doc = edof.new(width=w, height=h, title=title, dpi=dpi)
        page = new_doc.add_page()

        # v4.1.3: apply background choice
        if rb_bg_transp.isChecked():
            page.background = (255, 255, 255, 0)
        elif rb_bg_custom.isChecked():
            page.background = tuple(custom_color)
        else:
            page.background = (255, 255, 255, 255)

        # Document mode: enable margins + create initial flow content
        if rb_doc.isChecked():
            new_doc.margins = (15.0, 15.0, 15.0, 15.0)
            new_doc.mode = "document"   # v4.1.0
            self._canvas._margins = new_doc.margins
            self._canvas._margins_enabled = True
            if hasattr(self, '_act_margins'):
                self._act_margins.setChecked(True)
            # v4.1.19.1: also create the DocumentBody scaffold + a margin-
            # spanning textbox on the first page so the user can start typing
            # immediately. The textbox lives on the page (design-mode style)
            # and acts as the "writing area" — until 4.1.20 makes the
            # DocumentBody flow path fully editable, this gives the document
            # template the writeable region the user expects.
            from edof.format.document_body import DocumentBody, Paragraph
            from edof.format.document_boxes import DocumentTextBox
            from edof.format.styles import TextRun
            new_doc.body = DocumentBody()
            new_doc.body.page_margins_mm = (15.0, 15.0, 15.0, 15.0)
            new_doc.body.paragraphs = [
                Paragraph(runs=[TextRun(text="")], style_id="Normal")
            ]
            # v4.1.23: use DocumentTextBox directly (no legacy migration
            # needed). It carries the same fields as a TextBox plus the
            # isinstance discriminator the editor / paginator use.
            top, right, bottom, left = new_doc.body.page_margins_mm
            tb = DocumentTextBox()
            tb.transform.x = left; tb.transform.y = top
            tb.transform.width  = max(20.0, w - left - right)
            tb.transform.height = max(20.0, h - top - bottom)
            tb.style.font_family = "Arial"
            tb.style.font_size = 3.881
            tb.style.alignment = "left"
            tb.style.vertical_align = "top"
            tb.style.line_height = 1.15
            tb.style.padding = 0.0   # v4.1.23.9: doc bodies have no internal padding
            tb.style.wrap = True
            tb.style.auto_shrink = False
            tb.style.auto_fill = False
            tb.fill.color = None
            # v4.1.23.60: start the body EMPTY. Previously a placeholder string
            # ("Start typing your document…") was stored here and only cleared
            # AFTER the initial history snapshot was taken, so undoing all the
            # way back to the start restored that placeholder as real text.
            tb.text = ""
            tb.runs = [TextRun(text="")]
            tb.name = "document_body"
            page.objects.append(tb)
            self._auto_name(tb, "doc_body")
        else:
            new_doc.mode = "empty"

        self.doc = new_doc; self.filepath = None; self._modified = False
        self.history.clear(); self.history.push(self.doc, None, "New"); self._arm_history_suppression()
        # v4.1.19.2: explicit cleanup before showing new doc — cancel any
        # active inline edit, clear selection, drop welcome screen. Without
        # this New could appear to do nothing if a leftover inline editor
        # or welcome overlay was sitting on top of the canvas.
        try: self._canvas._cancel_inline()
        except Exception: pass
        try: self._canvas.set_sel_id(None)
        except Exception: pass
        if hasattr(self, '_welcome_widget') and self._welcome_widget:
            self._close_welcome()
        self._canvas.set_document(self.doc, 0)
        self._refresh_pages(); self._upd_title()
        self._canvas.schedule_render(0)
        # v4.2.9.6: fit the page to the window on New as well (deferred so the
        # viewport has its final size).
        from PyQt6.QtCore import QTimer as _FitT2
        _FitT2.singleShot(0, self._zoom_fit)
        _FitT2.singleShot(80, self._zoom_fit)

        # v4.1.19.2: in document mode, auto-start inline editing on the
        # body textbox so the user can type immediately without having to
        # double-click. Deferred via singleShot so the canvas has finished
        # rendering and the textbox object has a valid id and proxy slot.
        if new_doc.mode == "document":
            doc_body_tb = None
            if new_doc.pages and new_doc.pages[0].objects:
                doc_body_tb = new_doc.pages[0].objects[0]
            if doc_body_tb is not None:
                # Select first, then start inline editing
                self._canvas.set_sel_id(doc_body_tb.id)
                # Clear placeholder text so user starts in blank document
                if doc_body_tb.text == "Start typing your document…":
                    doc_body_tb.text = ""
                    if hasattr(doc_body_tb, 'runs') and doc_body_tb.runs:
                        for r in doc_body_tb.runs:
                            if r.text == "Start typing your document…":
                                r.text = ""
                QTimer.singleShot(150, lambda tb=doc_body_tb:
                                       self._canvas._start_inline(tb))

    def _open_dlg(self):
        p,_=QFileDialog.getOpenFileName(
            self, t('open'), "",
            "EDOF and PDFs with EDOF source (*.edof *.pdf);;EDOF (*.edof);;PDF (*.pdf);;All (*.*)"
        )
        if p: self._open_file(p)

    def _try_extract_edof_from_pdf(self, pdf_path: str):
        """v4.1.17.4: Scan a PDF for embedded files with .edof extension and
        extract the first match to a temp file. Returns the temp path or None.

        Uses a minimal byte-level parse — no PDF library dependency required.
        """
        import re, zlib, tempfile
        try:
            with open(pdf_path, "rb") as f:
                data = f.read()
        except Exception:
            return None
        # Find Filespec dicts containing a .edof filename
        # Filespecs look like: << /Type /Filespec /F (name.edof) ... /EF << /F N 0 R >> >>
        for m in re.finditer(rb"/Type\s*/Filespec[^>]+?/F\s*\(([^)]+)\)[^>]*?/EF\s*<<\s*/F\s*(\d+)\s+\d+\s+R",
                              data, re.DOTALL):
            fname = m.group(1).decode("latin-1", errors="replace")
            if not fname.lower().endswith(".edof"):
                continue
            ef_num = int(m.group(2))
            # Find the EmbeddedFile stream object
            obj_pattern = re.compile(
                rb"\b" + str(ef_num).encode() + rb"\s+0\s+obj\s*<<(.*?)>>\s*stream\n(.*?)\nendstream",
                re.DOTALL
            )
            om = obj_pattern.search(data)
            if not om: continue
            header = om.group(1)
            payload = om.group(2)
            if b"/Filter" in header and b"FlateDecode" in header:
                try:
                    payload = zlib.decompress(payload)
                except Exception:
                    return None
            # Write to temp and return path
            tmp = tempfile.mktemp(suffix=".edof",
                                    prefix=fname.replace(".edof", "_") + "_")
            with open(tmp, "wb") as f: f.write(payload)
            QMessageBox.information(self, "EDOF source found",
                f"This PDF contains an embedded EDOF source:\n  {fname}\n\n"
                f"Opening the embedded copy for editing. Save will write a new "
                f"file; the PDF itself remains unchanged.")
            return tmp
        return None

    def _open_file(self, path):
        # v4.1.17.4: if user picks a PDF, try to extract the embedded .edof
        # source attachment. If found, load that instead. Otherwise message.
        if path.lower().endswith('.pdf'):
            extracted = self._try_extract_edof_from_pdf(path)
            if extracted:
                path = extracted   # continue loading the extracted .edof
            else:
                QMessageBox.information(self, "Open PDF",
                    "This PDF doesn't contain an embedded EDOF source.\n\n"
                    "You can only open .edof files (or PDFs exported from "
                    "EDOF with 'Embed source' enabled).")
                return
        # v4.1.5: close welcome screen if open
        if hasattr(self, '_welcome_widget') and self._welcome_widget:
            self._close_welcome()
        # v4.0.1: Handle encrypted files (peek manifest, prompt for password)
        try:
            from edof.format.serializer import EdofSerializer
            from edof.crypto import EdofPasswordRequired, EdofWrongPassword
            from edof.utils.legacy_v2 import is_v2_archive

            password = None
            recovery_key = None
            had_xor_password = False

            # Check for legacy EDOF 2 with XOR password
            if is_v2_archive(path):
                try:
                    import zipfile, json
                    with zipfile.ZipFile(path) as zf:
                        v2_data = json.loads(zf.read("data.json"))
                        if v2_data.get("edit_password_xor"):
                            had_xor_password = True
                except Exception: pass

            # Peek manifest to check encryption
            else:
                try:
                    manifest = EdofSerializer.peek(path)
                    if manifest.get("protection", {}).get("mode") in ("partial", "full"):
                        password, recovery_key = self._prompt_for_password()
                        if password is None and recovery_key is None:
                            return  # user cancelled
                except Exception: pass

            # Load (with retries on wrong password)
            attempts = 0
            while True:
                attempts += 1
                try:
                    self.doc = edof.load(path, password=password,
                                           recovery_key=recovery_key)
                    break
                except EdofPasswordRequired:
                    password, recovery_key = self._prompt_for_password()
                    if password is None and recovery_key is None: return
                except EdofWrongPassword:
                    if attempts > 3:
                        QMessageBox.warning(self, "Failed",
                            "Three wrong attempts. Please open the file again.")
                        return
                    QMessageBox.warning(self, "Wrong password",
                        "The password or recovery key did not match. Try again.")
                    password, recovery_key = self._prompt_for_password()
                    if password is None and recovery_key is None: return

            self.filepath = path; self._modified = False
            self.history.clear(); self.history.push(self.doc, None, "Opened"); self._arm_history_suppression()
            self._canvas.set_document(self.doc, 0)
            self._refresh_pages(); self._upd_title()
            # v4.2.9.5: fit the page to the window on open (deferred so the
            # viewport has its final size before we measure it).
            from PyQt6.QtCore import QTimer as _FitT
            _FitT.singleShot(0, self._zoom_fit)
            _FitT.singleShot(80, self._zoom_fit)

            # Offer to upgrade XOR-protected v2 to real encryption
            if had_xor_password:
                self._offer_v2_upgrade()

            if self.doc.errors:
                QMessageBox.information(self, "Notice", "\n".join(self.doc.errors))
            self._update_protection_status()
            self._status.showMessage(t('status_opened', name=os.path.basename(path)))
            self._add_recent(path)   # v4.0.2
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _prompt_for_password(self):
        """Show a password prompt; returns (password, recovery_key) or (None, None) on cancel."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                     QLineEdit, QPushButton, QRadioButton,
                                     QButtonGroup)
        dlg = QDialog(self); dlg.setWindowTitle("Encrypted Document")
        dlg.setStyleSheet(QSS); dlg.resize(420, 220)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("<b>This document is encrypted.</b>"))
        v.addWidget(QLabel("Enter a password or recovery key to open it:"))

        rb_pwd = QRadioButton("Password"); rb_rk = QRadioButton("Recovery key")
        rb_pwd.setChecked(True)
        bg = QButtonGroup(dlg); bg.addButton(rb_pwd); bg.addButton(rb_rk)
        h = QHBoxLayout(); h.addWidget(rb_pwd); h.addWidget(rb_rk); v.addLayout(h)

        edit = QLineEdit(); edit.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(edit)

        def _toggle():
            if rb_rk.isChecked():
                edit.setEchoMode(QLineEdit.EchoMode.Normal)
                edit.setPlaceholderText("XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
            else:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
                edit.setPlaceholderText("")
            edit.clear()
        rb_pwd.toggled.connect(_toggle); rb_rk.toggled.connect(_toggle)

        bb = QHBoxLayout()
        ok = QPushButton("Open"); cancel = QPushButton("Cancel")
        bb.addStretch(); bb.addWidget(ok); bb.addWidget(cancel); v.addLayout(bb)

        result = [None, None]
        def do_ok():
            if rb_rk.isChecked():
                result[1] = edit.text().strip()
            else:
                result[0] = edit.text()
            dlg.accept()
        ok.clicked.connect(do_ok)
        edit.returnPressed.connect(do_ok)
        cancel.clicked.connect(dlg.reject)
        edit.setFocus()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result[0], result[1]
        return None, None

    def _offer_v2_upgrade(self):
        """After loading a legacy v2 archive that had XOR password, offer real AES."""
        msg = (
            "This document was loaded from a legacy EDOF 2 archive that had "
            "an XOR-obfuscated password.\n\n"
            "XOR provides no real protection — the password could be trivially "
            "recovered by anyone with the file.\n\n"
            "Would you like to set up real AES-256 encryption now?")
        r = QMessageBox.question(self, "Upgrade protection?", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self._show_protection_dialog()

    def _save(self):
        if not self.doc: return
        if self.filepath:
            try:
                self.doc.save(self.filepath); self._modified=False; self._upd_title()
                self._status.showMessage(t('status_saved',name=os.path.basename(self.filepath)))
                # v4.1.2: notify parent if this is a child sub-document window
                cb = getattr(self, '_on_save_callback', None)
                if cb:
                    try: cb()
                    except Exception: pass
                # v4.1.2: refresh fs watcher in case new SubDocumentBoxes were added
                self._refresh_subdoc_watcher()
            except Exception as e: QMessageBox.critical(self,"Error",str(e))
        else: self._save_as()

    def _save_as(self):
        if not self.doc: return
        p,_=QFileDialog.getSaveFileName(self,t('save_as'),"","EDOF (*.edof)")
        if p: self.filepath=p; self._save()

    def _confirm(self):
        # v4.1.23.56: flush an OPEN inline body editor first, so the user's most
        # recent keystrokes (which may not have hit the 120 ms idle sync yet)
        # are written into the document before we decide whether it is dirty.
        # Without this, closing right after typing dropped the last line(s) AND
        # the save prompt never appeared because _modified was still False.
        try:
            iw = getattr(self._canvas, '_inline_widget', None)
            if iw is not None and self.doc is not None:
                from edof.engine.document_paginate import (
                    _sync_body_from_textboxes, runs_text)
                _tb = getattr(iw, 'tb', None)
                _before = runs_text(_tb.runs) if _tb is not None else None
                try: iw.sync_to_tb_silent()
                except Exception: pass
                _after = runs_text(_tb.runs) if _tb is not None else None
                try: _sync_body_from_textboxes(self.doc)
                except Exception: pass
                # The body counts as modified if the flush changed the textbox
                # OR the editor recorded any edit that hasn't been folded into
                # _modified yet (e.g. typing on a single line, where pagination
                # never restructured and the idle marker may not have run).
                if _before != _after or getattr(iw, '_edited', False):
                    self._modified = True
        except Exception:
            pass
        if not self._modified:
            return True
        # Save / Don't Save / Cancel. Cancel aborts the close (or New/Open).
        _b = QMessageBox.StandardButton
        r = QMessageBox.question(
            self, t('dlg_unsaved'), t('dlg_save_changes'),
            _b.Save | _b.Discard | _b.Cancel, _b.Save)
        if r == _b.Cancel:
            return False
        if r == _b.Save:
            self._save()
            # Proceed only if the save actually went through. If the user
            # cancelled the Save As dialog (no filepath), _modified is still
            # set, so we abort rather than silently lose the document.
            return not self._modified
        return True  # Discard: proceed without saving

    def _upd_title(self):
        ti=(self.doc.title or "Untitled") if self.doc else "—"
        f=os.path.basename(self.filepath) if self.filepath else "Unsaved"
        self.setWindowTitle(f"{t('app_title')} {edof.__version__} — {ti} [{f}]{'•' if self._modified else ''}")
        # v4.2.9.4: show meaningful document info, not the internal (now
        # dynamic) canvas render DPI: page DPI, size in mm, size in pixels.
        if hasattr(self, '_lbl_dpi'):
            if self.doc and self.doc.pages:
                idx = int(getattr(self._canvas, '_page_idx', 0) or 0)
                if not (0 <= idx < len(self.doc.pages)):
                    idx = 0
                pg = self.doc.pages[idx]
                pdpi = int(getattr(pg, 'dpi', 0) or getattr(self.doc, 'default_dpi', 0) or 96)
                wmm = float(getattr(pg, 'width', 0) or 0)
                hmm = float(getattr(pg, 'height', 0) or 0)
                try:
                    wpx = int(round(mm_to_px(wmm, pdpi)))
                    hpx = int(round(mm_to_px(hmm, pdpi)))
                except Exception:
                    wpx = hpx = 0
                _gpu_badge = ""
                try:
                    from edof.engine import gpu as _gpu
                    if _gpu.is_enabled() and _gpu.gpu_available():
                        _gpu_badge = " · GPU"
                except Exception:
                    pass
                self._lbl_dpi.setText(f"{pdpi} DPI · {wmm:g}×{hmm:g} mm · {wpx}×{hpx} px{_gpu_badge}")
                self._lbl_dpi.setToolTip(
                    "Document resolution and page size (export DPI, millimetres, "
                    "and pixels at that DPI). On-screen sharpness is automatic "
                    "(zoom- and display-aware) and independent of this.")
            else:
                self._lbl_dpi.setText("—")
        try: self._on_zoom_changed()
        except Exception: pass

    def _push(self,d):
        if not self.doc: return
        # v4.1.23.59: commit any pending body burst FIRST so this object change
        # lands as the next, separate step in the one shared timeline.
        self._commit_pending_body()
        # v4.2.10.13: an explicit op (add/delete/duplicate/...) supersedes any
        # in-flight object-edit burst — its emit IS that burst — so cancel the
        # pending step to avoid recording a duplicate snapshot of the same state.
        self._obj_pending = False
        if hasattr(self, '_obj_commit_timer'):
            self._obj_commit_timer.stop()
        self.history.push(self.doc, None, d); self._modified=True; self._upd_title()

    def _mark_modified(self):
        """v4.1.7: simple helper to set the modified flag and update title."""
        self._modified = True
        self._upd_title()

    def _commit_inline_for_insert(self):
        """v4.1.20.1: Commit any active inline edit before triggering an
        insert action (textbox/image/shape/table/etc.). In document mode
        this also sets _skip_sticky_reentry so the user isn't yanked back
        into the body after commit — they need the canvas to be free so
        they can place the new object. Returns silently if no inline edit
        is active."""
        try:
            if getattr(self._canvas, '_inline_widget', None) is not None:
                self._canvas._skip_sticky_reentry = True
                self._canvas._confirm_inline()
        except Exception:
            pass

    def _check_perm(self, required: str, action_label: str = "edit") -> bool:
        """v4.0.1: Verify the doc grants `required` permission for an action.

        Shows a dialog if denied. Returns True if allowed.
        """
        if not self.doc: return False
        if not self.doc.is_encrypted:
            return True   # plain doc → always allowed
        if self.doc.can(required):
            return True
        from edof.crypto import describe_permission
        d = describe_permission(required)
        cur = describe_permission(self.doc.permission_level)
        QMessageBox.information(self, "Permission required",
            f"This action ({action_label}) requires permission level:\n"
            f"   {d['label']} or higher\n\n"
            f"You are currently at:\n"
            f"   {cur['label']}\n\n"
            f"Use Document → Unlock for editing… to enter a higher-level password.")
        return False

    def _undo(self):
        if not self.doc: return
        # Flush an uncommitted body burst as its own step so it can be undone.
        self._commit_pending_body()
        # v4.2.10.13: flush an in-flight object-edit burst too, so the latest
        # move/resize/style is a committed step before we step back.
        self._commit_pending_obj()
        res = self.history.undo()
        if res is not None:
            doc, ctx = res
            self._apply_history_state(doc, ctx)

    def _redo(self):
        if not self.doc: return
        self._commit_pending_body()
        self._commit_pending_obj()
        res = self.history.redo()
        if res is not None:
            doc, ctx = res
            self._apply_history_state(doc, ctx)

    # ── v4.1.23.59: unified history helpers (body + objects) ──────────────────
    def _body_global_cursor(self):
        """Global caret offset of the active inline body editor over the whole
        body flow, or None if no body editor is open."""
        try:
            iw = getattr(self._canvas, '_inline_widget', None)
            if iw is None or not getattr(iw, '_is_doc_body', False):
                return None
            from edof.engine.document_paginate import (
                find_document_body_on_page, runs_text)
            tb = getattr(iw, 'tb', None)
            prefix = 0
            for pg in self.doc.pages:
                b = find_document_body_on_page(pg)
                if b is None:
                    continue
                if b is tb:
                    return prefix + int(getattr(iw, '_cursor', 0))
                prefix += len(runs_text(b.runs or []))
        except Exception:
            pass
        return None

    def _body_sync_active(self):
        """Flush the active inline body editor into doc.body so a snapshot taken
        right after reflects the very latest keystrokes."""
        try:
            iw = getattr(self._canvas, '_inline_widget', None)
            if iw is not None and getattr(iw, '_is_doc_body', False):
                try: iw.sync_to_tb_silent()
                except Exception: pass
                from edof.engine.document_paginate import _sync_body_from_textboxes
                _sync_body_from_textboxes(self.doc)
        except Exception:
            pass

    def _on_body_touched(self):
        """Called by the inline body editor on every content edit. Marks a burst
        pending and (re)arms the debounce that commits it as one history step."""
        self._body_pending = True
        try:
            self._body_commit_timer.stop()
            self._body_commit_timer.start(self._body_commit_delay)
        except Exception:
            pass

    def _commit_pending_body(self):
        """Push the current body state as a single undo step (one per burst)."""
        try: self._body_commit_timer.stop()
        except Exception: pass
        if not self._body_pending or self.doc is None:
            self._body_pending = False
            return
        self._body_sync_active()
        gc = self._body_global_cursor()
        self.history.push(self.doc, ('body', gc), "Edit text")
        self._body_pending = False
        self._modified = True; self._upd_title()

    def _global_to_page_offset(self, doc, gc):
        """Map a global body caret offset to (page_index, in_page_offset) using
        the page body slices of the given (already paginated) document."""
        from edof.engine.document_paginate import (
            find_document_body_on_page, runs_text)
        prefix = 0
        last = 0
        for i, pg in enumerate(doc.pages):
            b = find_document_body_on_page(pg)
            if b is None:
                continue
            ln = len(runs_text(b.runs or []))
            last = i
            if gc <= prefix + ln:
                return i, gc - prefix
            prefix += ln
        return last, max(0, gc - prefix)

    def _apply_history_state(self, doc, ctx):
        """Restore a snapshot from the unified history. Replaces the live doc,
        refreshes the view, and — for a body-text step — reopens the inline
        editor at the saved caret. For an object step, stays in object mode."""
        from PyQt6.QtCore import QTimer
        # v4.2.10.13: restoring a snapshot mutates the doc and refreshes panels,
        # which fires objectChanged/changed. Suppress object-history recording so
        # the restore itself does not push a spurious step. Cleared on the next
        # event loop turn, after the refresh signals have drained.
        self._suppress_obj_history = True
        self._obj_pending = False
        try: self._obj_commit_timer.stop()
        except Exception: pass
        QTimer.singleShot(0, lambda: setattr(self, '_suppress_obj_history', False))
        self.doc = doc
        # The current inline editor points at the OLD document; tear it down and
        # skip the sticky auto-reentry so our explicit handling wins.
        try:
            self._canvas._skip_sticky_reentry = True
            self._canvas._cancel_inline()
        except Exception:
            pass
        kind = ctx[0] if ctx else None
        self._modified = True
        if kind == 'body':
            gc = ctx[1] if (ctx and ctx[1] is not None) else 0
            cp, co = self._global_to_page_offset(self.doc, int(gc))
            if cp >= len(self.doc.pages): cp = len(self.doc.pages) - 1
            self._refresh_pages()
            from edof.engine.document_paginate import find_document_body_on_page

            def _reopen():
                try:
                    self._canvas.set_document(self.doc, cp)
                    body = find_document_body_on_page(self.doc.pages[cp])
                    if body is not None:
                        self._canvas.set_sel_id(body.id)
                        self._canvas._start_inline(body)
                        iw = getattr(self._canvas, '_inline_widget', None)
                        if iw is not None:
                            _tot = sum(len(r.text or "") for r in (iw._runs or []))
                            iw._cursor = max(0, min(int(co), _tot))
                            iw._anchor = None
                            iw._edited = False
                            iw._invalidate()
                            try: self._canvas._scroll_to_cursor()
                            except Exception: pass
                            QTimer.singleShot(60, self._canvas._scroll_to_cursor)
                except Exception:
                    import traceback as _tb; _tb.print_exc()
            QTimer.singleShot(40, _reopen)
        else:
            # Object-level step: just show the restored document.
            try:
                self._canvas.set_document(
                    self.doc, min(self._cpi(), len(self.doc.pages) - 1))
            except Exception:
                pass
            self._refresh_pages()
        self._upd_title()

    # ── Insert ────────────────────────────────────────────────────────────────
    def _cp(self):
        if not self.doc or not self.doc.pages: return None
        i=self._cpi(); return self.doc.pages[i] if i<len(self.doc.pages) else None
    def _cpi(self): return max(0,self._pg_list.currentRow())

    def _auto_name(self, obj, prefix: str):
        """v4.1.10: Assign a stable auto-incrementing name like 'curve_01',
        'text_03', etc. Counts existing objects with the same prefix on the
        page and picks the next index.

        Only applied if the object doesn't already have a user-provided name.
        """
        if obj.name:
            return
        page = self._cp()
        if not page: return
        # Find existing names with matching prefix
        max_idx = 0
        import re
        pat = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
        for o in page.objects:
            if not o.name: continue
            m = pat.match(o.name)
            if m:
                try: max_idx = max(max_idx, int(m.group(1)))
                except ValueError: pass
        obj.name = f"{prefix}_{max_idx + 1:02d}"

    def _ins_textbox(self):
        """v4.1.15: Click menu → draw rectangle on canvas → textbox is
        created at the dragged rectangle, then immediately enters inline
        edit mode with the default placeholder text selected so the user
        starts typing right away. Esc cancels. Drags below 5×5mm are
        ignored (clicked accidentally)."""
        if not self._check_perm("design", "Add TextBox"): return
        self._commit_inline_for_insert()
        pg=self._cp()
        if not pg: return
        self._status.showMessage("Drag a rectangle on the canvas to place the text box. Esc to cancel.")
        def _create(x_mm, y_mm, w_mm, h_mm):
            from edof.units import pt_to_mm as _ptmm
            tb=pg.add_textbox(x_mm, y_mm, w_mm, h_mm, "Text")
            tb.style.font_size = _ptmm(18)   # v4.1.17: mm canonical (18pt = 6.35mm)
            self._auto_name(tb, "text")
            self._canvas.set_sel_id(tb.id); self._canvas.schedule_render(); self._push("Add TextBox")
            self._status.showMessage(f"Added text box ({w_mm:.0f}×{h_mm:.0f}mm) — start typing")
            # v4.1.15: auto-enter inline edit so user can type immediately
            from PyQt6.QtCore import QTimer as _IET
            def _enter_edit():
                self._canvas._start_inline(tb)
                # Select all so the first keystroke replaces the placeholder
                ed = self._canvas._inline_widget
                if ed is not None and hasattr(ed, 'selectAll'):
                    try: ed.selectAll()
                    except Exception: pass
            _IET.singleShot(0, _enter_edit)
        self._canvas.start_rect_draw("textbox", _create)

    def _ins_image(self):
        if not self._check_perm("design", "Add Image"): return
        self._commit_inline_for_insert()
        pg=self._cp()
        if not pg: return
        p,_=QFileDialog.getOpenFileName(self,t('image'),"","Images (*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp);;All (*.*)")
        if not p: return
        try:
            rid=self.doc.add_resource_from_file(p); ib=pg.add_image(rid,10,10,80,80)
            # Use the source filename (without extension) as the name
            import os as _os
            base = _os.path.splitext(_os.path.basename(p))[0]
            ib.name = base or "image"
            # If duplicate name on this page, fall back to auto-naming
            if any(o.name == ib.name and o.id != ib.id for o in pg.objects):
                ib.name = ""
                self._auto_name(ib, "image")
            self._canvas.set_sel_id(ib.id); self._canvas.schedule_render(); self._push("Add Image")
        except Exception as e: QMessageBox.critical(self,"Error",str(e))

    def _ins_svg(self):
        """v4.1.13: Import an SVG file as an SvgBox (raster display).
        User can double-click the box to convert into editable EDOF shapes."""
        if not self._check_perm("design", "Add SVG"): return
        self._commit_inline_for_insert()
        pg = self._cp()
        if not pg: return
        p, _ = QFileDialog.getOpenFileName(self, "Import SVG", "",
                                              "SVG files (*.svg);;All (*.*)")
        if not p: return
        try:
            with open(p, "r", encoding="utf-8") as f:
                xml = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read SVG: {e}")
            return
        # Determine intrinsic size from SVG viewBox/width/height
        from edof.format.svg_io import _parse_length
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            QMessageBox.critical(self, "Error", f"Invalid SVG: {e}")
            return
        vb = (root.get("viewBox") or "").split()
        if len(vb) == 4:
            vw = float(vb[2]); vh = float(vb[3])
        else:
            vw = _parse_length(root.get("width"), 100)
            vh = _parse_length(root.get("height"), 100)
        if vw <= 0: vw = 100
        if vh <= 0: vh = 100
        # Default placement: 100mm wide, preserve aspect
        target_w = min(100.0, vw if vw > 10 else 100.0)
        target_h = target_w * vh / vw
        from edof.format.objects import SvgBox
        sv = SvgBox()
        sv.svg_xml = xml
        sv.transform.x = 10; sv.transform.y = 10
        sv.transform.width = target_w
        sv.transform.height = target_h
        pg.objects.append(sv)
        import os as _os
        base = _os.path.splitext(_os.path.basename(p))[0]
        sv.name = base or "svg"
        if any(o.name == sv.name and o.id != sv.id for o in pg.objects):
            sv.name = ""
            self._auto_name(sv, "svg")
        self._canvas.set_sel_id(sv.id)
        self._canvas.schedule_render()
        self._push("Import SVG")

    def _convert_svgbox_to_shapes(self, obj):
        """v4.1.13: Replace an SvgBox with native EDOF Shape objects parsed
        from its SVG XML. Discards the original XML."""
        pg = self._cp()
        if not pg or not obj or not getattr(obj, 'svg_xml', None): return
        from edof.format.svg_io import svg_to_shapes
        shapes = svg_to_shapes(obj.svg_xml,
                                obj.transform.x, obj.transform.y,
                                obj.transform.width, obj.transform.height)
        if not shapes:
            QMessageBox.information(self, "Convert SVG",
                "No convertible path elements found in this SVG. "
                "Conversion supports <path>, <rect>, <circle>, <ellipse>, "
                "<line>, <polyline>, <polygon>.")
            return
        # Remove the SvgBox and add the shapes
        idx = None
        for i, o in enumerate(pg.objects):
            if o.id == obj.id: idx = i; break
        if idx is None: return
        pg.objects.pop(idx)
        for sh in shapes:
            self._auto_name(sh, "curve")
            pg.objects.append(sh)
        self._canvas.schedule_render()
        self._push("Convert SVG to shapes")

    def _export_svg_v4_1_13(self):
        """v4.1.13 lightweight SVG export — paths only. Kept for reference;
        use the main _export_svg which delegates to doc.export_svg for full
        support (text, images, gradients, etc.)."""
        pg = self._cp()
        if not pg: return
        p, _ = QFileDialog.getSaveFileName(self, "Export SVG (paths only)", "",
                                              "SVG files (*.svg);;All (*.*)")
        if not p: return
        if not p.lower().endswith(".svg"): p += ".svg"
        from edof.format.svg_io import shapes_to_svg
        shapes = [o for o in pg.objects
                    if getattr(o, 'shape_type', None) == 'path']
        if not shapes:
            QMessageBox.information(self, "Export SVG",
                "Current page has no path shapes to export.")
            return
        xml = shapes_to_svg(shapes, pg.width, pg.height)
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(xml)
            self.statusBar().showMessage(f"Exported {len(shapes)} path(s) to {p}", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Write failed: {e}")

    def _ins_shape(self,stype):
        if not self._check_perm("design", f"Add {stype}"): return
        self._commit_inline_for_insert()
        pg=self._cp()
        if not pg: return
        # v4.1.17.1: Drag-to-draw instead of dropping at fixed position
        def _create(x_mm, y_mm, w_mm, h_mm):
            sh=pg.add_shape(stype, x_mm, y_mm, w_mm, h_mm)
            sh.fill.color=(100,149,237,255); sh.stroke.color=(50,80,180,255)
            prefix_map = {"rect": "rect", "ellipse": "ellipse",
                           "polygon": "polygon", "arrow": "arrow",
                           "line": "line", "path": "curve"}
            self._auto_name(sh, prefix_map.get(stype, "shape"))
            self._canvas.set_sel_id(sh.id); self._canvas.schedule_render()
            self._push(f"Add {stype}")
        self._canvas.start_rect_draw(stype, _create)

    def _ins_line(self):
        self._commit_inline_for_insert()
        pg=self._cp()
        if not pg: return
        # v4.1.17.1: drag-to-draw line
        # v4.2.10.1: receives start (x_mm,y_mm) + SIGNED deltas (w_mm,h_mm)
        def _create(x_mm, y_mm, w_mm, h_mm):
            ex, ey = x_mm + w_mm, y_mm + h_mm
            sh=pg.add_shape("line", min(x_mm, ex), min(y_mm, ey),
                            max(0.1, abs(w_mm)), max(0.1, abs(h_mm)))
            sh.stroke.color=(40,40,40,255); sh.stroke.width=0.7; sh.fill.color=None
            # Endpoints in absolute page mm, preserving the drawn direction
            sh.points=[[x_mm, y_mm], [ex, ey]]
            self._auto_name(sh, "line")
            self._canvas.set_sel_id(sh.id); self._canvas.schedule_render()
            self._push("Add Line")
        self._canvas.start_rect_draw("line", _create)

    def _ins_qr(self):
        self._commit_inline_for_insert()
        pg=self._cp()
        if not pg: return
        data,ok=QInputDialog.getText(self,t('dlg_qr_title'),t('dlg_qr_prompt'))
        if not ok or not data: return
        qr=pg.add_qrcode(data,30,30,50); self._auto_name(qr, "qr")
        self._canvas.set_sel_id(qr.id)
        self._canvas.schedule_render(); self._push("Add QR")

    # v4.1.2: Insert embedded SubDocumentBox
    def _ins_subdoc(self):
        if not self._check_perm("design", "Insert sub-document"): return
        self._commit_inline_for_insert()
        pg = self._cp()
        if not pg: return
        ret = QMessageBox.question(self, "Insert sub-document",
            "Embed an existing .edof file?\n\n"
            "Yes — Choose a file to embed now\n"
            "No — Insert empty placeholder (link a file later)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel)
        if ret == QMessageBox.StandardButton.Cancel: return
        embed_path = None
        if ret == QMessageBox.StandardButton.Yes:
            fn, _ = QFileDialog.getOpenFileName(self, "Choose .edof to embed",
                                                  "", "EDOF documents (*.edof)")
            if fn:
                embed_path = fn
        # v4.1.17.1: drag-to-draw subdoc bbox
        def _create(x_mm, y_mm, w_mm, h_mm):
            sub = edof.SubDocumentBox()
            sub.transform.x = x_mm; sub.transform.y = y_mm
            sub.transform.width = w_mm; sub.transform.height = h_mm
            if embed_path:
                try:
                    with open(embed_path, "rb") as f: data = f.read()
                    rid = self.doc.resources.add(data,
                                                    filename=os.path.basename(embed_path),
                                                    mime_type="application/x-edof")
                    sub.resource_id = rid
                except Exception as e:
                    QMessageBox.warning(self, "Insert sub-document",
                                          f"Could not load file:\n{e}")
            pg.add_object(sub)
            self._auto_name(sub, "subdoc")
            self._canvas.set_sel_id(sub.id)
            self._canvas.schedule_render()
            self._push("Insert sub-document")
            self._refresh_subdoc_watcher()
        self._canvas.start_rect_draw("subdoc", _create)

    # v4.0.3: Insert Table
    def _ins_table(self):
        if not self._check_perm("design", "Insert table"): return
        self._commit_inline_for_insert()
        pg=self._cp()
        if not pg: return
        dlg=QDialog(self); dlg.setWindowTitle("Insert Table"); dlg.setStyleSheet(QSS)
        v=QVBoxLayout(dlg)
        form=QFormLayout()
        sp_r=QSpinBox(); sp_r.setRange(1, 100); sp_r.setValue(3)
        sp_c=QSpinBox(); sp_c.setRange(1, 20); sp_c.setValue(3)
        sp_w=QDoubleSpinBox(); sp_w.setRange(20, 500); sp_w.setValue(100); sp_w.setSuffix(" mm")
        sp_h=QDoubleSpinBox(); sp_h.setRange(10, 500); sp_h.setValue(40);  sp_h.setSuffix(" mm")
        cb_hdr=QCheckBox("First row is header (bold + accent)"); cb_hdr.setChecked(True)
        cb_zb=QCheckBox("Alternating row colors"); cb_zb.setChecked(False)
        form.addRow("Rows:", sp_r); form.addRow("Columns:", sp_c)
        form.addRow("Width:", sp_w); form.addRow("Height:", sp_h)
        form.addRow(cb_hdr); form.addRow(cb_zb)
        v.addLayout(form)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); v.addWidget(bb)
        if dlg.exec()!=QDialog.DialogCode.Accepted: return

        rows = sp_r.value(); cols = sp_c.value()
        from edof.format.objects import Table, TableCell
        # Use make_table helper for nicer defaults
        from edof import make_table
        sample = [[f"Col {c+1}" if cb_hdr.isChecked() and r==0 else "" for c in range(cols)]
                   for r in range(rows)]
        t_obj = make_table(sample, header=cb_hdr.isChecked(), alternating=cb_zb.isChecked())
        t_obj.transform.x = 20; t_obj.transform.y = 20
        t_obj.transform.width = sp_w.value(); t_obj.transform.height = sp_h.value()
        pg.add_object(t_obj)
        self._auto_name(t_obj, "table")
        self._canvas.set_sel_id(t_obj.id); self._canvas.schedule_render()
        self._push("Add Table")

    # v4.0.3: Path tool — collects clicks until double-click / Enter
    def _set_tool_mode(self, mode: str):
        """v4.1.19: set the active canvas tool mode and update toolbar
        button states so the active tool is visually obvious.

        mode in: 'select' (default cursor), 'hand' (pan)
        """
        # Update canvas internal flags
        is_hand = (mode == 'hand')
        self._canvas._hand_tool = is_hand
        if is_hand:
            self._canvas.viewport().setCursor(tcur('hand', Qt.CursorShape.OpenHandCursor))
            self._status.showMessage("Hand tool ON — drag to pan. Press V or click ↖ to return.")
        else:
            self._canvas.viewport().setCursor(tcur('move', Qt.CursorShape.ArrowCursor))
            self._status.showMessage("Select tool ON — click to select, drag to move.")
        # Sync toolbar button checked states
        if hasattr(self, '_act_select_tool'):
            self._act_select_tool.setChecked(not is_hand)
        if hasattr(self, '_act_hand_tool'):
            self._act_hand_tool.setChecked(is_hand)

    def _toggle_hand_tool(self):
        """v4.1.1: Hand tool — pan the canvas without selecting.
        v4.1.19: route through unified tool mode setter so toolbar state stays
        in sync (still kept for backward-compatible keyboard shortcut callers)."""
        cur = getattr(self._canvas, '_hand_tool', False)
        self._set_tool_mode('select' if cur else 'hand')

    def _ins_path(self):
        if not self._check_perm("design", "Draw path"): return
        self._commit_inline_for_insert()
        pg=self._cp()
        if not pg: return
        # Switch canvas into path-drawing mode; mouse clicks accumulate points
        self._canvas._path_drawing = True
        self._canvas._path_points = []
        self._status.showMessage(
            "Pen tool: click=corner, click+drag=curve handle, click first point or Enter to close, Esc to cancel.")
        self._canvas.viewport().setCursor(tcur('pen', Qt.CursorShape.CrossCursor))

    def _dup_obj(self):
        if not self._check_perm("design", "Duplicate object"): return
        pg=self._cp(); sid=self._canvas.get_sel_id()
        if not pg or not sid: return
        obj=pg.get_object(sid)
        if not obj: return
        new=obj.copy(); new.transform.translate(8,8); pg.add_object(new)
        self._canvas.set_sel_id(new.id); self._canvas.schedule_render(); self._push("Duplicate")

    def _del_obj(self):
        if not self._check_perm("design", "Delete object"): return
        self._canvas._do_delete(); self._push("Delete")

    # ── Pages ─────────────────────────────────────────────────────────────────
    def _add_page(self):
        if not self.doc: return
        self.doc.add_page(); self._refresh_pages()
        self._canvas.set_page(len(self.doc.pages)-1); self._push("Add page")

    def _dup_page(self):
        if not self.doc: return
        self.doc.duplicate_page(self._cpi()); self._refresh_pages(); self._push("Dup page")

    def _del_page(self):
        if not self.doc or len(self.doc.pages)<=1:
            QMessageBox.information(self,"Info",t('info_only_page')); return
        idx=self._cpi(); self.doc.remove_page(idx); self._refresh_pages()
        self._canvas.set_page(min(idx,len(self.doc.pages)-1)); self._push("Del page")

    def _refresh_pages(self):
        # v4.1.23.21: pages were added/removed or content reflowed — drop the
        # canvas page-pixmap cache so stale thumbnails aren't shown on switch.
        try: self._canvas._invalidate_page_cache()
        except Exception: pass
        self._pg_list.blockSignals(True); cur=self._pg_list.currentRow(); self._pg_list.clear()
        if self.doc:
            for i,p in enumerate(self.doc.pages):
                self._pg_list.addItem(f"  Page {i+1}  {int(p.width)}×{int(p.height)}")
        n=self._pg_list.count()
        if n>0: self._pg_list.setCurrentRow(max(0,min(cur,n-1)))
        self._pg_list.blockSignals(False)
        self._obj_panel.refresh()

    # ── Zoom ──────────────────────────────────────────────────────────────────
    def _zoom_pct(self):
        """Displayed zoom %, where 100% == 1 document pixel : 1 screen pixel.
        Internally the canvas zoom is relative to its (dynamic) render DPI, so we
        rescale by base_dpi / document_dpi for a meaningful figure."""
        cz = float(getattr(self._canvas, 'zoom', 1.0) or 1.0)
        base = float(getattr(self._canvas, '_dpi', 96) or 96)
        docdpi = 96.0
        try:
            if self.doc and self.doc.pages:
                idx = int(getattr(self._canvas, '_page_idx', 0) or 0)
                if not (0 <= idx < len(self.doc.pages)):
                    idx = 0
                pg = self.doc.pages[idx]
                docdpi = float(getattr(pg, 'dpi', 0) or getattr(self.doc, 'default_dpi', 0) or 96)
        except Exception:
            docdpi = 96.0
        if docdpi <= 0:
            docdpi = 96.0
        return cz * base / docdpi * 100.0

    def _on_zoom_changed(self, *_):
        try: self._lbl_zoom.setText(f"{int(round(self._zoom_pct()))}%")
        except Exception: pass

    def _zoom_step(self,f):
        self._canvas.zoom=self._canvas.zoom*f; self._on_zoom_changed()
    def _zoom_fit(self):
        self._canvas.zoom_fit(); self._on_zoom_changed()

    # ── Export / Print ────────────────────────────────────────────────────────
    # ── v4.0.3: View menu helpers ─────────────────────────────────────────────
    def _toggle_margins(self, on):
        self._canvas._margins_enabled = bool(on)
        # If enabling and doc has saved margins, use them; otherwise default
        if self.doc and self.doc.margins:
            self._canvas._margins = tuple(self.doc.margins)
        self._canvas.viewport().update()   # v4.1.0: redraw margin lines
        self._canvas.schedule_render()

    def _set_grid_size_dlg(self):
        """v4.1.10.2: Set snap grid size (mm, 2-decimal precision)."""
        cur = getattr(self._canvas, '_snap_size_mm', 5.0)
        dlg = QDialog(self); dlg.setWindowTitle("Grid Size"); dlg.setStyleSheet(QSS)
        v = QVBoxLayout(dlg)
        form = QFormLayout()
        sp = QDoubleSpinBox()
        sp.setRange(0.01, 100.0)
        sp.setDecimals(2)
        sp.setSingleStep(0.5)
        sp.setSuffix(" mm")
        sp.setValue(round(cur, 2))
        # Apply Fusion style so arrows render
        try:
            from PyQt6.QtWidgets import QStyleFactory
            fs = QStyleFactory.create("Fusion")
            if fs: sp.setStyle(fs)
        except Exception: pass
        form.addRow("Grid spacing:", sp)
        v.addLayout(form)
        hint = QLabel("Affects: snap-to-grid for object move/resize and grid dots.\n"
                      "Use Ctrl+G or View → Snap to Grid to enable snapping.")
        hint.setStyleSheet("color:#888;font:9pt 'Segoe UI';")
        v.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_val = max(0.01, sp.value())
        self._canvas._snap_size_mm = new_val
        # Persist to QSettings so it survives restarts
        try:
            self._settings.setValue("snap_size_mm", new_val)
        except Exception: pass
        self._canvas.viewport().update()

    def _set_margins_dlg(self):
        if not self.doc:
            QMessageBox.information(self, "No document", "Open a document first.")
            return
        cur = self.doc.margins or (15.0, 15.0, 15.0, 15.0)
        dlg=QDialog(self); dlg.setWindowTitle("Page Margins"); dlg.setStyleSheet(QSS)
        v=QVBoxLayout(dlg)
        info=QLabel("Margins are used as snap targets in the editor. "
                    "They are not enforced at export.")
        info.setWordWrap(True); v.addWidget(info)
        form=QFormLayout()
        sps={}
        for label, val in (("Top:",cur[0]),("Right:",cur[1]),("Bottom:",cur[2]),("Left:",cur[3])):
            sp=QDoubleSpinBox(); sp.setRange(0,200); sp.setSuffix(" mm"); sp.setValue(val)
            form.addRow(label, sp)
            sps[label]=sp
        v.addLayout(form)
        cb_enable=QCheckBox("Enable margin snapping")
        cb_enable.setChecked(self._canvas._margins_enabled)
        v.addWidget(cb_enable)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); v.addWidget(bb)
        if dlg.exec()!=QDialog.DialogCode.Accepted: return
        margins=(sps["Top:"].value(), sps["Right:"].value(),
                  sps["Bottom:"].value(), sps["Left:"].value())
        self.doc.margins = margins
        self._canvas._margins = margins
        self._canvas._margins_enabled = cb_enable.isChecked()
        if hasattr(self, '_act_margins'):
            self._act_margins.setChecked(cb_enable.isChecked())
        # v4.1.23: In document mode, margins are not just a snap hint — they
        # define the body box geometry on each page. Push to body, resize
        # every body / header / footer textbox to match, then paginate so
        # content re-flows.
        if self.doc.mode == "document" and self.doc.body is not None:
            self.doc.body.page_margins_mm = margins
            try:
                from edof.engine.document_paginate import (
                    sync_geometry_to_section, paginate_document)
                sync_geometry_to_section(self.doc)
                if self._canvas._inline_widget is not None:
                    try: self._canvas._inline_widget.commit_to_textbox()
                    except Exception: pass
                paginate_document(self.doc, dpi=self._canvas._dpi)
                self._refresh_pages()
            except Exception:
                import traceback; traceback.print_exc()
        self._modified=True; self._upd_title()
        self._canvas.schedule_render()

    @staticmethod
    def _format_gpu_selftest(res):
        """v4.2.11.34: build the self-test report from ALL metrics the engine
        returns (the old dialog hardcoded blur + CA, so the loft / halftone /
        variable-blur parity results added in 4.2.11.28-.32 never showed up).
        Unknown future *_diff keys are listed too, so this can't go stale."""
        lines = [res.get('status', ''), ""]
        shown = set()

        def sec(title, mkey, xkey, scale255=True, note=None):
            if mkey not in res:
                return
            shown.add(mkey); shown.add(xkey)
            fmt = "{:.3f}" if scale255 else "{:.5f}"
            lines.append(title + ":")
            lines.append("   mean difference: " + fmt.format(res[mkey]))
            if xkey in res:
                lines.append("   max  difference: " + ("{:.1f}" if scale255 else "{:.5f}").format(res[xkey]))
            if note:
                lines.append("   " + note)
            lines.append("")

        sec(f"Gaussian blur, radius {res.get('radius', 0):g}px",
            'mean_diff', 'max_diff',
            note="(tiny diff expected: GPU sums weights in a different order)")
        sec("Chromatic aberration", 'ca_mean_diff', 'ca_max_diff')
        sec("Long-shadow loft sweep - coverage",
            'loft_cov_mean_diff', 'loft_cov_max_diff')
        sec("Long-shadow loft sweep - distance map (0..1 scale)",
            'loft_tmap_mean_diff', 'loft_tmap_max_diff', scale255=False)
        sec("Halftone dot stamping", 'ht_mean_diff', 'ht_max_diff')
        sec("Variable box blur (long shadow)", 'vb_mean_diff', 'vb_max_diff',
            note="(tiny diff expected: sequential cumsum vs parallel scan)")

        # errors from individual sections
        for k in sorted(res):
            if k.endswith('_error'):
                lines.append(f"{k[:-6]} section FAILED: {res[k]}")
                lines.append("")
                shown.add(k)
        # future-proof: any *_diff key not covered above still gets printed
        extra = [k for k in sorted(res)
                 if k.endswith('_diff') and k not in shown]
        for k in extra:
            lines.append(f"{k}: {res[k]:.5f}")
        if extra:
            lines.append("")

        lines.append("(differences on the 0-255 scale unless noted; lower is "
                      f"better; 0 = exact parity. Images saved to:\n{res.get('out_dir', '?')})")
        return "\n".join(lines)

    def _run_gpu_selftest(self):
        """v4.2.11.0: run the CPU-vs-GPU blur parity self-test and report the
        result (status + mean/max pixel difference), opening the folder with the
        cpu/gpu/diff images so the GPU shader can be validated on real hardware.
        v4.2.11.34: reports ALL parity sections (blur, CA, loft, halftone,
        variable blur), not just the first two."""
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        from edof.engine import gpu as _gpu
        try:
            res = _gpu.selftest(size=512, radius=8.0)
        except Exception as e:
            QMessageBox.warning(self, "GPU self-test", f"Self-test failed:\n{e}")
            return
        if not res.get("available"):
            QMessageBox.information(
                self, "GPU self-test",
                "GPU is not available, so the GPU path stays disabled and "
                "everything renders on the CPU.\n\n" + res.get("status", "") +
                "\n\nTo enable it, install the optional dependency:\n"
                "    pip install moderngl")
            return
        if res.get("error"):
            QMessageBox.warning(self, "GPU self-test",
                                res["status"] + "\n\n" + res["error"])
            return
        msg = self._format_gpu_selftest(res)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("GPU self-test")
        box.setText("CPU vs GPU parity")
        box.setInformativeText(msg)
        open_btn = box.addButton("Open images", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(res["out_dir"]))

    def _open_perf_settings(self):
        """v4.2.10.11: dialog to toggle render optimizations on/off. Changes
        apply live and persist via QSettings. The idle full-quality render and
        export always use the exact path, so these only affect interactive
        smoothness, not final output."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QCheckBox, QLabel,
                                     QDialogButtonBox, QFrame)
        cv = self._canvas
        dlg = QDialog(self); dlg.setWindowTitle("Performance / optimizations")
        lay = QVBoxLayout(dlg)
        intro = QLabel("These affect interactive smoothness only. The idle "
                       "full-quality render and all exports are unaffected.")
        intro.setWordWrap(True); lay.addWidget(intro)

        # (settings key, label, tooltip)
        opts = [
            ("object_cache", "Per-object raster cache",
             "Reuse unchanged objects' rasters. Big win on dense pages."),
            ("dirty_region", "Dirty-region (active object only)",
             "While editing one object, re-render only that object over a "
             "cached background of the rest."),
            ("adaptive_dpi", "Adaptive render DPI (zoom + HiDPI)",
             "Render at the on-screen resolution: crisper when zoomed in, "
             "cheaper when zoomed out / on HiDPI screens."),
            ("supersample", "Supersample when zoomed out",
             "Render fine detail above screen resolution and minify = "
             "anti-aliasing (smoother halftone / thin lines when far out)."),
            ("lowres_interaction", "Low-res preview while dragging",
             "Render at reduced DPI during drag / resize for responsiveness, "
             "full quality on release."),
            ("gl_viewport", "GPU viewport (OpenGL)",
             "Use a QOpenGLWidget viewport for GPU-accelerated pan/zoom blits. "
             "Does not change rasterization. Toggle off if you see a black "
             "viewport or artifacts on your GPU/driver."),
        ]
        boxes = {}
        for key, label, tip in opts:
            cb = QCheckBox(label)
            cb.setChecked(bool(getattr(cv, "_opt_" + key, True)))
            cb.setToolTip(tip)
            sub = QLabel(tip); sub.setWordWrap(True)
            sub.setStyleSheet("color: gray; margin-left: 22px; font-size: 11px;")
            cb.toggled.connect(lambda v, k=key: cv.set_render_opt(k, v))
            lay.addWidget(cb); lay.addWidget(sub)
            boxes[key] = cb

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); lay.addWidget(line)
        note = QLabel("Tip: turning everything off gives the simplest, most "
                      "predictable render path (slowest, but a good baseline "
                      "for comparison).")
        note.setWordWrap(True); note.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(note)

        # v4.2.11.0: GPU (experimental) — Build 5 groundwork. The GPU path is not
        # wired into the live renderer yet; this runs a CPU-vs-GPU parity
        # self-test so the blur shader can be validated on real hardware first.
        line2 = QFrame(); line2.setFrameShape(QFrame.Shape.HLine); lay.addWidget(line2)
        from edof.engine import gpu as _gpu
        gpu_title = QLabel("<b>GPU acceleration (experimental)</b>")
        lay.addWidget(gpu_title)
        gpu_stat = QLabel(_gpu.gpu_status()); gpu_stat.setWordWrap(True)
        gpu_stat.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(gpu_stat)
        gpu_cb = QCheckBox("Use GPU for effect blur (shadow / glow / bevel)")
        gpu_cb.setChecked(bool(getattr(cv, "_opt_gpu_effects", False)))
        gpu_cb.setEnabled(_gpu.gpu_available())
        gpu_cb.setToolTip("Run the Gaussian blur behind drop/inner shadow, "
                          "outer/inner glow and bevel-soften on the GPU. Falls "
                          "back to CPU per-effect on any miss. Output matches the "
                          "CPU within ~0.35/255 mean. Export stays on CPU.")
        gpu_cb.toggled.connect(lambda v: cv.set_render_opt("gpu_effects", v))
        lay.addWidget(gpu_cb)
        if not _gpu.gpu_available():
            hint = QLabel("Enable by installing the optional dependency: "
                          "pip install moderngl")
            hint.setWordWrap(True); hint.setStyleSheet("color: gray; font-size: 11px;")
            lay.addWidget(hint)
        from PyQt6.QtWidgets import QPushButton as _QPB
        gpu_btn = _QPB("Run GPU self-test…")
        gpu_btn.clicked.connect(self._run_gpu_selftest)
        lay.addWidget(gpu_btn)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.accept); bb.accepted.connect(dlg.accept)
        lay.addWidget(bb)
        dlg.resize(440, dlg.sizeHint().height())
        dlg.exec()

    def _reset_panels(self):
        """Reset all dock widget sizes/positions to defaults."""
        # Resize the main window first
        self.resize(1440, 880)
        # Try to restore default state — if we have a saved baseline, use it;
        # otherwise just reset specific dock geometry
        for dock_name in ("_left_dock", "_right_dock", "_pages_dock"):
            d = getattr(self, dock_name, None)
            if d is None: continue
            d.setVisible(True)
            d.setFloating(False)
        # Re-apply default sizes by minimum-size hint
        if hasattr(self, "_settings"):
            self._settings.remove("geometry")
            self._settings.remove("windowState")
        QMessageBox.information(self, "Panels reset",
            "Panel layout reset. Restart editor for full effect.")

    def _edit_shortcuts(self):
        """v4.1.23.37: editable text-editor keyboard shortcuts. Saved to the
        user config and applied to any open inline editor immediately."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
            QTableWidget, QTableWidgetItem, QPushButton, QKeySequenceEdit,
            QLabel, QHeaderView)
        from PyQt6.QtGui import QKeySequence
        try:
            from edof._apps.shortcuts import (DEFAULT_SHORTCUTS, load_shortcuts,
                                              save_shortcuts)
        except Exception:
            return
        cur = load_shortcuts()
        dlg = QDialog(self); dlg.setWindowTitle("Customize Shortcuts")
        dlg.setStyleSheet(QSS); dlg.resize(520, 560)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Text editor shortcuts. Click a cell and press the "
                           "desired key combination."))
        tbl = QTableWidget(len(DEFAULT_SHORTCUTS), 2)
        tbl.setHorizontalHeaderLabels(["Action", "Shortcut"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tbl.verticalHeader().setVisible(False)
        editors = {}
        for row, (aid, (label, _def)) in enumerate(DEFAULT_SHORTCUTS.items()):
            it = QTableWidgetItem(label)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tbl.setItem(row, 0, it)
            kse = QKeySequenceEdit()
            try:
                kse.setKeySequence(QKeySequence(cur.get(aid, _def).replace('+', '+')))
            except Exception:
                pass
            editors[aid] = kse
            tbl.setCellWidget(row, 1, kse)
        v.addWidget(tbl)
        row = QHBoxLayout()
        btn_reset = QPushButton("Reset to defaults")
        btn_cancel = QPushButton("Cancel")
        btn_save = QPushButton("Save")
        row.addWidget(btn_reset); row.addStretch()
        row.addWidget(btn_cancel); row.addWidget(btn_save)
        v.addLayout(row)

        def _reset():
            for aid, (label, dflt) in DEFAULT_SHORTCUTS.items():
                try: editors[aid].setKeySequence(QKeySequence(dflt))
                except Exception: pass
        def _save():
            mapping = {}
            for aid, kse in editors.items():
                seq = kse.keySequence().toString().lower()
                mapping[aid] = seq or DEFAULT_SHORTCUTS[aid][1]
            save_shortcuts(mapping)
            # apply to a live inline editor if open
            try:
                ed = getattr(self, '_inline_widget', None)
                if ed is not None and hasattr(ed, '_reload_shortcuts'):
                    ed._reload_shortcuts()
            except Exception:
                pass
            dlg.accept()
        btn_reset.clicked.connect(_reset)
        btn_cancel.clicked.connect(dlg.reject)
        btn_save.clicked.connect(_save)
        dlg.exec()

    def _show_shortcuts(self):
        """v4.0.3: keyboard shortcuts reference dialog."""
        dlg=QDialog(self); dlg.setWindowTitle("Keyboard Shortcuts"); dlg.setStyleSheet(QSS)
        dlg.resize(560, 600)
        v=QVBoxLayout(dlg)
        from PyQt6.QtWidgets import QTextBrowser
        tb=QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setHtml("""
        <h2>EDOF Editor — Keyboard Shortcuts</h2>

        <h3>File</h3>
        <table cellpadding="3">
        <tr><td><b>Ctrl+N</b></td><td>New document</td></tr>
        <tr><td><b>Ctrl+O</b></td><td>Open .edof file</td></tr>
        <tr><td><b>Ctrl+S</b></td><td>Save</td></tr>
        <tr><td><b>Ctrl+Shift+S</b></td><td>Save As…</td></tr>
        <tr><td><b>Ctrl+P</b></td><td>Print…</td></tr>
        <tr><td><b>Ctrl+Q</b></td><td>Quit</td></tr>
        </table>

        <h3>Edit</h3>
        <table cellpadding="3">
        <tr><td><b>Ctrl+Z</b></td><td>Undo</td></tr>
        <tr><td><b>Ctrl+Y</b></td><td>Redo</td></tr>
        <tr><td><b>Ctrl+D</b></td><td>Duplicate selection</td></tr>
        <tr><td><b>Delete</b></td><td>Delete selection</td></tr>
        <tr><td><b>Ctrl+F</b></td><td>Find &amp; Replace</td></tr>
        </table>

        <h3>View</h3>
        <table cellpadding="3">
        <tr><td><b>Ctrl+=</b></td><td>Zoom in</td></tr>
        <tr><td><b>Ctrl+-</b></td><td>Zoom out</td></tr>
        <tr><td><b>Ctrl+0</b></td><td>Fit page to window</td></tr>
        <tr><td><b>Ctrl+G</b></td><td>Toggle snap to grid</td></tr>
        </table>

        <h3>Insert</h3>
        <table cellpadding="3">
        <tr><td><b>T</b></td><td>Text box</td></tr>
        <tr><td><b>I</b></td><td>Image</td></tr>
        <tr><td><b>R</b></td><td>Rectangle</td></tr>
        <tr><td><b>E</b></td><td>Ellipse</td></tr>
        <tr><td><b>L</b></td><td>Line</td></tr>
        <tr><td><b>Q</b></td><td>QR code</td></tr>
        </table>

        <h3>Document</h3>
        <table cellpadding="3">
        <tr><td><b>Ctrl+Shift+L</b></td><td>Unlock for editing (encrypted docs)</td></tr>
        </table>

        <h3>Selection / dragging</h3>
        <table cellpadding="3">
        <tr><td><b>Click</b></td><td>Select object</td></tr>
        <tr><td><b>Ctrl+click</b></td><td>Add/remove from multi-select</td></tr>
        <tr><td><b>Drag empty area</b></td><td>Lasso multi-select</td></tr>
        <tr><td><b>Drag object</b></td><td>Move (snaps to grid + alignment guides + margins)</td></tr>
        <tr><td><b>Drag corner handle</b></td><td>Resize</td></tr>
        <tr><td><b>Drag rotate handle</b></td><td>Rotate</td></tr>
        <tr><td><b>Drag middle-mouse</b></td><td>Pan canvas</td></tr>
        <tr><td><b>Mouse wheel</b></td><td>Zoom toward cursor</td></tr>
        <tr><td><b>Double-click textbox</b></td><td>Edit text inline</td></tr>
        <tr><td><b>Arrow keys</b></td><td>Nudge selection by 0.5 mm</td></tr>
        </table>

        <h3>Modifier keys (v4.0.3 revised)</h3>
        <table cellpadding="3">
        <tr><td><b>Shift</b> while resizing</td>
            <td><b>For images:</b> toggle to non-uniform scale (default is uniform).<br>
                <b>For shapes/text:</b> force uniform scale (preserve aspect ratio).</td></tr>
        <tr><td><b>Shift</b> while rotating</td>
            <td>Snap to 15° increments</td></tr>
        <tr><td><b>Ctrl</b> while dragging</td>
            <td>Bypass all snapping (grid, alignment guides, margins)</td></tr>
        <tr><td><b>Alt</b> while dragging</td>
            <td>Bypass snapping (legacy alias for Ctrl)</td></tr>
        </table>

        <h3>Object panel (left side)</h3>
        <table cellpadding="3">
        <tr><td><b>F2</b> on selected item</td><td>Rename object</td></tr>
        <tr><td><b>Double-click item</b></td><td>Rename object</td></tr>
        <tr><td><b>Right-click item</b></td><td>Layer / lock / hide / duplicate / delete menu</td></tr>
        <tr><td><b>Drag item</b></td><td>Reorder layers</td></tr>
        </table>

        <h3>Path drawing tool (✎)</h3>
        <table cellpadding="3">
        <tr><td><b>Click</b></td><td>Add point</td></tr>
        <tr><td><b>Double-click</b> or <b>Enter</b></td><td>Finish path</td></tr>
        <tr><td><b>Esc</b></td><td>Cancel</td></tr>
        </table>

        <p>For more info see the
        <a href="https://davidschobl.github.io/edof/">documentation</a>.</p>
        """)
        v.addWidget(tb)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject); bb.accepted.connect(dlg.accept)
        bb.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()

    def _open_file_assoc_dialog(self):
        """Manage the .edof file association (choose app in-app, register/remove)."""
        try:
            from edof._apps._assoc_dialog import manage_association
        except Exception as e:
            QMessageBox.warning(self, "File association",
                                  f"Could not load file association module: {e}")
            return
        manage_association(self)

    # ─────────────────────────────────────────────────────────────────────
    # v4.1.2: Multi-window support for embedded sub-documents
    # ─────────────────────────────────────────────────────────────────────

    def _open_subdoc_in_tab(self, subdoc):
        """v4.1.2/4.1.3/4.1.8: Open the embedded/linked sub-document in a new
        editor window. Dedup: if a window is already open for this subdoc, just
        raise it to front instead of opening another.

        - If subdoc.source_path is set → open that external file directly.
        - If subdoc.resource_id is set (embedded) → extract bytes to temp,
          open it. Save propagates back via _on_save_callback.
        - If neither is set → ask if user wants to create a new empty
          embedded document or load an existing file.
        """
        import edof
        if not isinstance(subdoc, edof.SubDocumentBox):
            return

        # v4.1.8: deduplication — if a child window for this subdoc is already
        # open, just bring it forward. Prevents the "double-click opens
        # endless windows" problem.
        for existing in list(self._child_editors):
            try:
                if (getattr(existing, '_parent_subdoc', None) is subdoc
                    and existing.isVisible()):
                    existing.raise_(); existing.activateWindow()
                    return
                # Clean up stale references (window already closed)
                if not existing.isVisible():
                    self._child_editors.remove(existing)
            except Exception:
                pass

        # Case 1: external source_path
        if subdoc.source_path and os.path.isfile(subdoc.source_path):
            child = EdofEditor(filepath=subdoc.source_path)
            child._parent_editor = self
            child._parent_subdoc = subdoc
            child.show()
            self._child_editors.append(child)
            return
        # Case 2: embedded resource
        if subdoc.resource_id and self.doc:
            entry = self.doc.resources.get(subdoc.resource_id)
            if not entry:
                QMessageBox.warning(self, "Open sub-document",
                                       "Embedded resource not found.")
                return
            self._launch_child_for_embedded(subdoc, entry.data, entry.filename or "subdoc.edof")
            return
        # Case 3: empty SubDoc — offer to create or load
        ret = QMessageBox.question(self, "Empty sub-document",
            "This embed has no source loaded yet. What would you like to do?\n\n"
            "Yes — Create a new blank embedded document and open it for editing\n"
            "No  — Load an existing .edof file to embed",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel)
        if ret == QMessageBox.StandardButton.Cancel: return
        if ret == QMessageBox.StandardButton.No:
            fn, _ = QFileDialog.getOpenFileName(self, "Choose .edof to embed",
                                                  "", "EDOF documents (*.edof)")
            if not fn: return
            try:
                with open(fn, "rb") as f:
                    data = f.read()
                rid = self.doc.resources.add(data,
                                                filename=os.path.basename(fn),
                                                mime_type="application/x-edof")
                subdoc.resource_id = rid
                self._mark_modified()
                self._canvas.schedule_render()
                # Now open it
                self._launch_child_for_embedded(subdoc, data, os.path.basename(fn))
            except Exception as e:
                QMessageBox.warning(self, "Load failed", f"Could not load file:\n{e}")
            return
        # Yes — create a new empty embedded document
        try:
            # v4.1.9.1: child page inherits the placeholder's bounding box
            # dimensions (so resizing the placeholder doesn't change the
            # content — they start matched). Background defaults to
            # transparent so the placeholder is visually empty until filled.
            w_mm = max(10.0, subdoc.transform.width or 100.0)
            h_mm = max(10.0, subdoc.transform.height or 100.0)
            new_doc = edof.new(width=w_mm, height=h_mm, title="Embedded")
            new_page = new_doc.add_page()
            new_page.background = (255, 255, 255, 0)   # transparent
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix="edof_subdoc_")
            tmp_path = os.path.join(tmp_dir, "embedded.edof")
            new_doc.save(tmp_path)
            with open(tmp_path, "rb") as f:
                data = f.read()
            rid = self.doc.resources.add(data,
                                            filename="embedded.edof",
                                            mime_type="application/x-edof")
            subdoc.resource_id = rid
            try: self._mark_modified()
            except Exception: pass
            self._canvas.schedule_render()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            QMessageBox.warning(self, "Create failed",
                f"Could not create empty embedded document:\n\n{e}\n\n{tb}")
            return
        # Open the freshly created file in a child window
        self._launch_child_for_embedded(subdoc, data, "embedded.edof",
                                          existing_temp_path=tmp_path)

    def _launch_child_for_embedded(self, subdoc, data, filename, existing_temp_path=None):
        """v4.1.3: Helper to open an embedded sub-document in a child editor window."""
        import tempfile
        if existing_temp_path:
            tmp_path = existing_temp_path
        else:
            tmp_dir = tempfile.mkdtemp(prefix="edof_subdoc_")
            tmp_path = os.path.join(tmp_dir, filename)
            try:
                with open(tmp_path, "wb") as f:
                    f.write(data)
            except Exception as e:
                QMessageBox.warning(self, "Open sub-document",
                                       f"Could not extract embedded bytes:\n{e}")
                return
        child = EdofEditor(filepath=tmp_path)
        child._parent_editor = self
        child._parent_subdoc = subdoc
        child._parent_temp_file = tmp_path
        child.setWindowTitle(f"[Embedded] {child.windowTitle()}")
        # v4.1.3: faster save propagation — direct callback
        child._on_save_callback = lambda: self._on_child_subdoc_saved(child)
        child.show()
        child.raise_()
        child.activateWindow()
        self._child_editors.append(child)

    def _on_child_subdoc_saved(self, child):
        """v4.1.2/4.1.3: child window saved → update parent's embedded resource immediately."""
        if child not in self._child_editors:
            return
        if not child._parent_temp_file or not child._parent_subdoc:
            return
        try:
            with open(child._parent_temp_file, "rb") as f:
                new_data = f.read()
        except Exception:
            return
        # Update parent's resource bytes
        rid = child._parent_subdoc.resource_id
        if rid and self.doc:
            entry = self.doc.resources.get(rid)
            if entry:
                entry.data = new_data
                self._mark_modified()
                # v4.1.3: aggressive invalidation for instant visual update
                try:
                    self._canvas._render_id += 1
                except Exception: pass
                self._canvas.schedule_render(0)
                # Force a second render shortly after to ensure pixmap settles
                QTimer.singleShot(80, lambda: self._canvas.schedule_render(0))
                # Bring parent to front so user sees the update
                self.raise_()
                self._status.showMessage(
                    f"Embedded sub-document updated from child window.", 3000)

    def _refresh_subdoc_watcher(self):
        """v4.1.2: Update QFileSystemWatcher to track external SubDocumentBox source paths."""
        if not self._fs_watcher or not self.doc:
            return
        try:
            current = list(self._fs_watcher.files())
            if current:
                self._fs_watcher.removePaths(current)
        except Exception:
            pass
        paths = set()
        import edof
        for page in self.doc.pages:
            for obj in page.objects:
                if isinstance(obj, edof.SubDocumentBox) and obj.source_path:
                    if os.path.isfile(obj.source_path):
                        paths.add(obj.source_path)
        if paths:
            try:
                self._fs_watcher.addPaths(list(paths))
            except Exception:
                pass

    def _on_external_subdoc_changed(self, path):
        """v4.1.2: An external .edof referenced by a SubDocumentBox changed.

        QFileSystemWatcher fires once and may need re-add (some editors
        write atomically by replacing the file).
        """
        # Re-add path to keep watching after atomic replace
        try:
            QTimer.singleShot(200, lambda: self._fs_watcher.addPath(path))
        except Exception:
            pass
        # Just trigger a re-render — renderer reads source_path each time
        self._status.showMessage(f"Embedded document changed on disk: "
                                   f"{os.path.basename(path)} — reloading.", 3000)
        self._canvas.schedule_render(100)

    def _open_donate(self):
        """v4.1.0: Open the donate page (Ko-fi) in the user's browser."""
        try:
            import webbrowser
            webbrowser.open("https://ko-fi.com/davidschobl")
        except Exception as e:
            QMessageBox.information(self, "Support",
                f"To support the developer, visit:\n"
                f"https://ko-fi.com/davidschobl\n"
                f"https://github.com/sponsors/DavidSchobl\n\n({e})")

    def _show_about(self):
        # v4.1.0: more comprehensive about + donate link
        QMessageBox.about(self, "About edof",
            f"<h2>edof — Easy Document Format</h2>"
            f"<p><b>Editor version:</b> {edof.__version__}<br>"
            f"<b>Format version:</b> edof {edof.FORMAT_VERSION_STR}</p>"
            f"<p>A Python library and visual editor for programmatic document "
            f"creation, template filling, and high-quality export. "
            f"Combines the precision of programmatic generation with a "
            f"rich visual editor.</p>"
            f"<h3>Capabilities</h3>"
            f"<ul>"
            f"<li><b>Format:</b> ZIP-based <code>.edof</code> with full save/load fidelity</li>"
            f"<li><b>Objects:</b> TextBox (rich text), ImageBox, Shape (rect, ellipse, "
            f"line, polygon, arrow, path), QRCode, Table, Group, SubDocumentBox</li>"
            f"<li><b>Editor:</b> visual canvas, drag/resize, layer panel, properties, "
            f"path tool, snap-to-grid, alignment guides, page margins, cell editor for tables</li>"
            f"<li><b>Effects:</b> 16 blend modes, drop shadow, inner shadow, outer/inner "
            f"glow, bevel, stroke, color/gradient overlay (Photoshop-style)</li>"
            f"<li><b>Variables:</b> typed (text, number, date, bool, image, QR, URL), "
            f"<code>{{name}}</code>-style placeholders, conditional visibility</li>"
            f"<li><b>Encryption:</b> AES-256 with permission tiers (fill/edit/design/admin)</li>"
            f"<li><b>Import:</b> PDF (text, vector paths, images), RTF (paragraphs + runs), "
            f"v2/v3 legacy formats</li>"
            f"<li><b>Export:</b> Vector PDF (Standard 14 fonts, no deps), Raster PDF "
            f"(any font, requires reportlab), PNG/JPEG/TIFF, SVG, RTF</li>"
            f"<li><b>CLI:</b> render, export, import, batch, set-password, unlock-render, "
            f"to-v3, convert</li>"
            f"</ul>"
            f"<p><b>Documentation:</b> "
            f"<a href='https://davidschobl.github.io/edof/'>davidschobl.github.io/edof</a><br>"
            f"<b>Source:</b> "
            f"<a href='https://github.com/DavidSchobl/edof'>github.com/DavidSchobl/edof</a><br>"
            f"<b>PyPI:</b> "
            f"<a href='https://pypi.org/project/edof/'>pypi.org/project/edof</a></p>"
            f"<h3>Support the developer</h3>"
            f"<p>If edof saves you time and you'd like to support its development, "
            f"you can donate any amount via "
            f"<a href='https://ko-fi.com/davidschobl'>Ko-fi</a> or "
            f"<a href='https://github.com/sponsors/DavidSchobl'>GitHub Sponsors</a>. "
            f"Every contribution helps keep edof maintained and free.</p>"
            f"<p>License: MIT &nbsp;|&nbsp; © 2025 DavidSchobl</p>")

    def _show_help_guide(self):
        """v4.1.0: Multi-page help guide with table of contents."""
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QStackedWidget, QSplitter
        dlg = QDialog(self); dlg.setWindowTitle("EDOF Help Guide"); dlg.setStyleSheet(QSS)
        dlg.resize(900, 660)
        v = QVBoxLayout(dlg)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        toc = QListWidget(); toc.setMaximumWidth(220)
        stack = QStackedWidget()

        PAGES = [
            ("Getting Started", """
<h2>Getting Started</h2>
<p>Welcome to <b>EDOF Editor</b> — a visual editor for the Easy Document Format.</p>
<h3>Your first document</h3>
<ol>
<li><b>File → New</b> (Ctrl+N) — choose a paper or video size, plus a mode:
    <ul>
    <li><b>Empty</b>: free-form layout, fixed-position objects (default)</li>
    <li><b>Document</b>: word-style with auto margins for flowing content</li>
    </ul></li>
<li><b>Add objects</b> from the toolbar: text, image, shapes, table, QR code, path</li>
<li><b>Drag</b> to position, <b>handles</b> to resize, properties panel on the right
    for fine-tuning</li>
<li><b>Save</b> with Ctrl+S — outputs an <code>.edof</code> file (ZIP-based)</li>
<li><b>Export</b> via File → Export PDF (vector or raster) or PNG/JPEG/TIFF</li>
</ol>
<h3>What is EDOF?</h3>
<p>EDOF (Easy Document Format) is both a <b>file format</b> (.edof) and a
<b>Python library</b>. The visual editor is one of three ways to create documents:</p>
<ul>
<li>From Python code: <code>edof.new(...)</code>, <code>page.add_textbox(...)</code></li>
<li>From the command line: <code>edof-cli</code></li>
<li>Visually in this editor</li>
</ul>
<p>All three produce the same .edof files, fully interoperable.</p>
"""),
            ("Tools & Toolbar", """
<h2>Tools & Toolbar</h2>
<p>The toolbar provides quick access to common operations:</p>
<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;'>
<tr><th>Icon</th><th>Tool</th><th>Shortcut</th></tr>
<tr><td>📄</td><td>New document</td><td>Ctrl+N</td></tr>
<tr><td>📂</td><td>Open</td><td>Ctrl+O</td></tr>
<tr><td>💾</td><td>Save</td><td>Ctrl+S</td></tr>
<tr><td>↩️</td><td>Undo</td><td>Ctrl+Z</td></tr>
<tr><td>↪️</td><td>Redo</td><td>Ctrl+Y</td></tr>
<tr><td>T</td><td>Insert text box</td><td>—</td></tr>
<tr><td>🖼</td><td>Insert image (file picker)</td><td>—</td></tr>
<tr><td>▭</td><td>Insert rectangle</td><td>—</td></tr>
<tr><td>⬭</td><td>Insert ellipse</td><td>—</td></tr>
<tr><td>⊞</td><td>Insert table (rows × cols dialog)</td><td>—</td></tr>
<tr><td>QR</td><td>Insert QR code</td><td>—</td></tr>
<tr><td>✎</td><td>Path tool — click to add points, double-click to finish, click first point to close</td><td>—</td></tr>
<tr><td>🔍+/-</td><td>Zoom</td><td>Ctrl+= / Ctrl+-</td></tr>
</table>
<h3>Path Tool</h3>
<p>The path tool creates vector shapes by clicking points:</p>
<ul>
<li><b>Click</b> to add a point</li>
<li>When ≥3 points exist, the first point becomes orange — <b>click it</b> to close the shape (creates a filled polygon)</li>
<li><b>Double-click</b> or press <b>Enter</b> to finish as an open path</li>
<li><b>Esc</b> to cancel</li>
</ul>
"""),
            ("Layer Effects", """
<h2>Layer Effects</h2>
<p>EDOF Editor includes Photoshop-style layer effects available on every object.
Open them via the <b>Layer Effects…</b> button in the Advanced section of the
properties panel.</p>
<h3>Available effects</h3>
<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;'>
<tr><th>Effect</th><th>What it does</th></tr>
<tr><td>Drop Shadow</td><td>Cast shadow behind the object. Configurable color, blend, opacity, size, distance, direction.</td></tr>
<tr><td>Inner Shadow</td><td>Shadow inside the object's bounds — gives an inset/recessed look.</td></tr>
<tr><td>Outer Glow</td><td>Soft luminous halo around the object's silhouette.</td></tr>
<tr><td>Inner Glow</td><td>Glow inward from the object's edges.</td></tr>
<tr><td>Bevel & Emboss</td><td>3D-looking bevel with light/dark colors and a 3D direction wheel (uses <b>Color</b> for shadow side, <b>Color 2</b> for highlight side).</td></tr>
<tr><td>Stroke</td><td>Outline around the object. Outside / Center / Inside positioning.</td></tr>
<tr><td>Color Overlay</td><td>Solid color tint across the object's silhouette.</td></tr>
<tr><td>Gradient Overlay</td><td>Linear gradient with configurable angle, start/end colors.</td></tr>
</table>
<h3>Stacking</h3>
<p>Effects stack in this order: drop shadow → outer glow → outside stroke → outer bevel
→ <b>object</b> → inner shadow → inner glow → color overlay → gradient overlay → inside stroke.</p>
"""),
            ("Variables & Templates", """
<h2>Variables & Templates</h2>
<p>EDOF documents support <b>typed variables</b> for templates. Define them
in the Variables panel, reference them from object properties.</p>
<h3>Variable types</h3>
<ul>
<li><b>text</b>, <b>number</b>, <b>date</b>, <b>bool</b></li>
<li><b>image</b> — variable image content for ImageBox</li>
<li><b>qr</b>, <b>url</b> — QR-code data</li>
</ul>
<h3>Usage</h3>
<ol>
<li>Define a variable (e.g. <code>customer_name</code>)</li>
<li>Bind it to an object via the properties panel <b>Variable</b> field, OR</li>
<li>Use placeholder syntax: <code>Hello {customer_name}!</code></li>
<li>Use <b>Show if</b> for conditional visibility: <code>amount &gt; 1000</code></li>
</ol>
<h3>Filling templates from code</h3>
<pre>
import edof
doc = edof.load("invoice_template.edof")
doc.variables.set("customer_name", "Alice")
doc.variables.set("amount", 1500)
doc.export_pdf("invoice.pdf")
</pre>
"""),
            ("Encryption & Permissions", """
<h2>Encryption & Permissions</h2>
<p>EDOF documents can be encrypted with AES-256 and have <b>permission tiers</b>:</p>
<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;'>
<tr><th>Level</th><th>Can do</th></tr>
<tr><td>view</td><td>Read-only — open and render, no edits</td></tr>
<tr><td>fill</td><td>Fill in variable values only</td></tr>
<tr><td>edit</td><td>Edit object content (text, images), not structure</td></tr>
<tr><td>design</td><td>Add/remove/reorder objects</td></tr>
<tr><td>admin</td><td>All permissions including encryption changes</td></tr>
</table>
<p>Use <b>Document → Encryption…</b> to set passwords, or via the CLI:</p>
<pre>
edof-cli set-password input.edof --level edit --password secret
edof-cli unlock-render protected.edof --password secret -o out.pdf
</pre>
"""),
            ("Keyboard Shortcuts", """
<h2>Keyboard Shortcuts</h2>
<p>Press <b>F1</b> for the dedicated keyboard shortcuts dialog with a complete reference.</p>
<h3>Most common</h3>
<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;'>
<tr><th>Action</th><th>Shortcut</th></tr>
<tr><td>New / Open / Save</td><td>Ctrl+N / Ctrl+O / Ctrl+S</td></tr>
<tr><td>Undo / Redo</td><td>Ctrl+Z / Ctrl+Y</td></tr>
<tr><td>Copy / Cut / Paste / Duplicate</td><td>Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+D</td></tr>
<tr><td>Delete</td><td>Del</td></tr>
<tr><td>Zoom in / out / fit</td><td>Ctrl+= / Ctrl+- / Ctrl+0</td></tr>
<tr><td>Snap to grid</td><td>Ctrl+G</td></tr>
<tr><td>Bypass snap</td><td>Hold Ctrl while dragging</td></tr>
<tr><td>Uniform scale (ImageBox: free distortion)</td><td>Hold Shift while dragging handle</td></tr>
<tr><td>Snap rotation to 15°</td><td>Hold Shift while rotating</td></tr>
<tr><td>Bold / Italic / Underline (in text edit)</td><td>Ctrl+B / Ctrl+I / Ctrl+U</td></tr>
</table>
"""),
            ("Tips & Tricks", """
<h2>Tips & Tricks</h2>
<ul>
<li><b>Live preview while typing:</b> Click into a text box to start editing; a floating toolbar appears with bold/italic/underline/font/size/color. The canvas re-renders as you type.</li>
<li><b>Object panel:</b> drag items up/down to reorder layers; F2 to rename; right-click for context menu</li>
<li><b>Margins as snap targets:</b> View → Use Page Margins; drag near margin lines to snap edge of object</li>
<li><b>PDF-safe fonts:</b> The font dropdown marks Standard 14 PDF fonts with ✓ — pick those if you'll export Vector PDF</li>
<li><b>Custom fonts:</b> File → Import Font…; the font is registered for the session and embedded in doc.resources</li>
<li><b>Sub-documents:</b> Use <code>SubDocumentBox</code> in code (or via API) to embed another .edof inside this one — useful for headers/footers/letterheads</li>
<li><b>Templates:</b> File → Templates includes business card, certificate, invoice — use as starting points</li>
</ul>
"""),
            ("Programmatic API", """
<h2>Programmatic API</h2>
<p>Everything in the editor maps directly to Python API calls. Use the editor
to design templates, then fill them programmatically:</p>
<pre>
import edof

# Create
doc = edof.new(width=210, height=297, title="Invoice")
page = doc.add_page()
tb = page.add_textbox(20, 20, 170, 10, "Hello {name}!")
tb.style.font_size = 5.644
tb.style.bold = True

# Variables
doc.variables.add(edof.VariableDef("name", edof.VAR_TEXT, default="World"))
doc.variables.set("name", "Alice")

# Layer effects (Photoshop-style)
tb.effects.append(edof.LayerEffect(
    type="drop_shadow",
    enabled=True,
    color=(0,0,0,180),
    size=2.0,
    distance=2.0,
    direction=135.0,
))

# Save / Export
doc.save("hello.edof")
doc.export_pdf("hello.pdf")
</pre>
<p>See <a href='https://davidschobl.github.io/edof/'>full API docs</a> for
all object types, styles, encryption, etc.</p>
"""),
            ("Tables — Programmatic", """
<h2>Tables — Programmatic Access</h2>
<p>Tables are 2D grids of cells with rich per-cell formatting. The editor's
Cell Editor handles most editing, but for templates and bulk operations,
the API gives you full control.</p>
<h3>Creating a table</h3>
<pre>
import edof
doc = edof.new(width=210, height=297)
page = doc.add_page()

# Quick way: from rows of strings (with optional header)
tbl = edof.make_table(
    rows=[
        ["Name", "Price", "Qty"],
        ["Apple", "10", "3"],
        ["Bread", "25", "2"],
    ],
    header=True,            # first row gets bold header style
    alternating=True,       # alternate row backgrounds
    col_widths=[60, 30, 30],   # mm; 0 = auto
    row_heights=[10, 8, 8],    # mm; 0 = auto
)
tbl.transform.x = 20; tbl.transform.y = 20
tbl.transform.width = 120; tbl.transform.height = 26
page.add_object(tbl)
</pre>
<h3>Accessing cells</h3>
<pre>
# tbl.cells is a 2D list: cells[row_index][col_index]
cell = tbl.cells[1][0]      # Row 1 (Apple), col 0 (Name)
print(cell.text)             # "Apple"

# Modify text
cell.text = "Granny Smith"

# Modify style
cell.style.bold = True
cell.style.color = (180, 0, 0)        # RGB red
cell.style.alignment = "right"

# Background color (RGBA)
cell.bg_color = (255, 255, 200, 255)   # light yellow

# Per-side borders
cell.border_top.color = (50, 50, 50, 255)
cell.border_top.width = 0.5            # mm
cell.border_top.enabled = True

cell.border_left.enabled = False       # hide left border
</pre>
<h3>Adding rows/columns programmatically</h3>
<pre>
from edof.format.objects import TableCell

# Add a row at the end
new_row = [TableCell(text=str(v)) for v in ["Cherry", "30", "5"]]
tbl.cells.append(new_row)
tbl.row_heights.append(8)

# Insert a column at index 1
for r, row in enumerate(tbl.cells):
    row.insert(1, TableCell(text=f"Item {r}"))
tbl.col_widths.insert(1, 25)
</pre>
<h3>Iterating</h3>
<pre>
for r_idx, row in enumerate(tbl.cells):
    for c_idx, cell in enumerate(row):
        # Process every cell
        if r_idx == 0:  # header row
            cell.style.bold = True
            cell.bg_color = (200, 200, 220, 255)
</pre>
<h3>Outer table border</h3>
<pre>
from edof.format.styles import StrokeStyle
tbl.table_border = StrokeStyle(
    color=(0, 0, 0, 255),
    width=0.8,           # mm
)
</pre>
<h3>Coming in v5.0</h3>
<p>Future versions will add formula support: <code>=SUM(B2:B5)</code>,
<code>=A1*0.21</code>, etc. For now, compute values in your code before
populating the cells.</p>
""")
        ]

        for title_, _html in PAGES:
            it = QListWidgetItem(title_)
            toc.addItem(it)
            from PyQt6.QtWidgets import QTextBrowser
            tb = QTextBrowser()
            tb.setHtml(_html)
            tb.setOpenExternalLinks(True)
            stack.addWidget(tb)
        toc.currentRowChanged.connect(stack.setCurrentIndex)
        toc.setCurrentRow(0)

        splitter.addWidget(toc)
        splitter.addWidget(stack)
        splitter.setSizes([220, 680])
        v.addWidget(splitter, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject); bb.accepted.connect(dlg.accept)
        # The Close button in PyQt has the role 'Reject'
        for b in bb.buttons():
            b.clicked.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()

    def _export_png(self):
        if not self.doc or not self.doc.pages: return
        # v4.1.18: DPI selector dialog before file picker
        dlg = QDialog(self); dlg.setWindowTitle("Export bitmap"); dlg.setStyleSheet(QSS)
        dlg.resize(380, 200)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Resolution (DPI):"))
        from PyQt6.QtWidgets import QComboBox
        cb_dpi = QComboBox()
        for label, val in [("Screen (96)", 96), ("Web (150)", 150),
                            ("Print (300)", 300), ("High-res (600)", 600)]:
            cb_dpi.addItem(label, val)
        # Pick a reasonable default for the document
        pref = getattr(self.doc, 'default_dpi', 300) or 300
        if pref >= 600: cb_dpi.setCurrentIndex(3)
        elif pref >= 300: cb_dpi.setCurrentIndex(2)
        elif pref >= 150: cb_dpi.setCurrentIndex(1)
        else: cb_dpi.setCurrentIndex(0)
        v.addWidget(cb_dpi)
        v.addWidget(QLabel("Custom DPI:"))
        sp_custom = QSpinBox(); sp_custom.setRange(36, 1200); sp_custom.setValue(cb_dpi.currentData())
        sp_custom.setSuffix(" DPI")
        v.addWidget(sp_custom)
        cb_dpi.currentIndexChanged.connect(lambda i: sp_custom.setValue(cb_dpi.currentData()))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        target_dpi = sp_custom.value()
        p,_=QFileDialog.getSaveFileName(self,t('export_png'),"","PNG (*.png);;JPEG (*.jpg);;TIFF (*.tiff)")
        if not p: return
        _rv = self._render_flush(dpi=target_dpi)
        try:
            fmt=os.path.splitext(p)[1].upper().lstrip(".")
            self.doc.export_bitmap(p,page=self._cpi(),dpi=target_dpi,format=fmt or "PNG")
            self._status.showMessage(t('status_saved',name=os.path.basename(p)))
        except Exception as e: QMessageBox.critical(self,"Error",str(e))
        finally: self._render_restore(_rv)

    def _export_all(self):
        if not self.doc: return
        d=QFileDialog.getExistingDirectory(self,t('export_all'))
        if not d: return
        _rv = self._render_flush(dpi=300)
        try:
            from edof.export.bitmap import export_all_pages
            ps=export_all_pages(self.doc,os.path.join(d,"page_{page}.png"),dpi=300)
            QMessageBox.information(self,"Done",f"Exported {len(ps)} page(s)")
        except Exception as e: QMessageBox.critical(self,"Error",str(e))
        finally: self._render_restore(_rv)

    def _export_pdf(self):
        if not self.doc: return
        # v4.0.3: dialog with vector/raster choice
        # v4.1.18: add Embed source checkbox + DPI selector for raster mode
        dlg=QDialog(self); dlg.setWindowTitle("Export PDF"); dlg.setStyleSheet(QSS)
        dlg.resize(440, 320)
        v=QVBoxLayout(dlg)

        info=QLabel(
            "<b>Vector PDF</b> (default): pure-Python writer. Smaller files, "
            "selectable text. Limited to Standard 14 PDF fonts (Helvetica, "
            "Times, Courier with bold/italic). Pages containing layer effects "
            "are auto-rasterized at 300 DPI for fidelity.<br><br>"
            "<b>Raster PDF</b>: rendered as bitmap at given DPI. Larger files, "
            "no text selection, but supports any TTF font. Requires reportlab."
        )
        info.setWordWrap(True)
        v.addWidget(info)

        from PyQt6.QtWidgets import QRadioButton, QButtonGroup, QCheckBox
        rb_vec=QRadioButton("Vector PDF (recommended)"); rb_vec.setChecked(True)
        rb_ras=QRadioButton("Raster PDF (custom fonts, larger files)")
        v.addWidget(rb_vec); v.addWidget(rb_ras)

        dpi_row=QWidget(); hb=QHBoxLayout(dpi_row); hb.setContentsMargins(20,0,0,0)
        sp_dpi=QSpinBox(); sp_dpi.setRange(72, 600); sp_dpi.setValue(300)
        sp_dpi.setSuffix(" DPI"); sp_dpi.setEnabled(False)
        rb_ras.toggled.connect(sp_dpi.setEnabled)
        hb.addWidget(QLabel("Raster resolution:")); hb.addWidget(sp_dpi); hb.addStretch()
        v.addWidget(dpi_row)

        # v4.1.18: Embed source checkbox
        cb_embed = QCheckBox("Embed EDOF source so the PDF can be re-edited "
                              "(recipient needs the EDOF editor)")
        cb_embed.setChecked(True)
        v.addWidget(cb_embed)

        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); v.addWidget(bb)
        if dlg.exec()!=QDialog.DialogCode.Accepted: return

        p,_=QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF (*.pdf)")
        if not p: return
        if not p.lower().endswith(".pdf"): p += ".pdf"
        vector = rb_vec.isChecked()
        embed = cb_embed.isChecked()
        raster_dpi = sp_dpi.value() if not vector else None
        _rv = self._render_flush(dpi=raster_dpi)
        try:
            self.doc.export_pdf(p, vector=vector, dpi=raster_dpi, embed_source=embed)
            mode = "vector" if vector else "raster"
            embed_msg = " (with EDOF source)" if embed else ""
            self._status.showMessage(f"Saved {mode} PDF{embed_msg}: {os.path.basename(p)}")
        except ImportError:
            QMessageBox.critical(self,"PDF Error",
                "Raster PDF requires reportlab.\npip install edof[pdf]")
        except Exception as e:
            QMessageBox.critical(self,"PDF Error", str(e))
        finally:
            self._render_restore(_rv)

    def _gen_csv_template(self):
        """v4.1.17.1: Generate a blank CSV template whose columns are the
        variable names attached to objects in this document. Useful for
        preparing the CSV used by 'Batch CSV → exports'.

        Only objects with a non-empty `obj.variable` contribute a column.
        Duplicates are deduped. A single blank data row is added so the
        spreadsheet editor opens with an editable row visible."""
        if not self.doc: return
        # Walk all pages and gather variable names (deduped, in stable order)
        seen = []
        for page in self.doc.pages:
            for obj in page.flatten() if hasattr(page, 'flatten') else page.objects:
                vname = getattr(obj, 'variable', None)
                if vname and vname not in seen:
                    seen.append(vname)
            # Some Page implementations don't have flatten — fallback
            for obj in getattr(page, 'objects', []):
                vname = getattr(obj, 'variable', None)
                if vname and vname not in seen:
                    seen.append(vname)
                # Walk groups recursively
                children = getattr(obj, 'children', None)
                if children:
                    stack = list(children)
                    while stack:
                        c = stack.pop()
                        vn = getattr(c, 'variable', None)
                        if vn and vn not in seen:
                            seen.append(vn)
                        sub = getattr(c, 'children', None)
                        if sub: stack.extend(sub)
        if not seen:
            QMessageBox.information(self, "No variables",
                "No objects in this document are bound to a variable.\n\n"
                "Select a textbox and set its 'Variable' field in the "
                "properties panel to make it template-fillable.")
            return
        # Ask where to save
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV template", "template.csv", "CSV (*.csv);;All (*.*)")
        if not out_path: return
        if not out_path.lower().endswith('.csv'):
            out_path = out_path + '.csv'
        import csv
        try:
            with open(out_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(seen)            # header row with variable names
                w.writerow(['' for _ in seen])   # one blank data row
            QMessageBox.information(self, "CSV template",
                f"Wrote {len(seen)} column(s) to:\n{out_path}\n\n"
                f"Columns: {', '.join(seen)}")
        except Exception as e:
            QMessageBox.critical(self, "CSV template", f"Could not write file:\n{e}")

    def _batch_csv(self):
        """Item 26: CSV import for batch fill → export per row."""
        if not self.doc: return
        csv_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV file", "", "CSV (*.csv);;All (*.*)")
        if not csv_path: return
        out_dir = QFileDialog.getExistingDirectory(self, "Output folder for exports")
        if not out_dir: return

        # Detect variables in template
        var_names = self.doc.variables.names()
        if not var_names:
            QMessageBox.warning(self, "No variables",
                "This template has no variables defined.\n"
                "Bind objects to variables first.")
            return

        import csv
        try:
            with open(csv_path, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows   = list(reader)
                headers= reader.fieldnames or []
        except Exception as e:
            QMessageBox.critical(self, "CSV Error", str(e)); return

        if not rows:
            QMessageBox.information(self, "Empty", "CSV has no data rows."); return

        # Show mapping dialog
        dlg = QDialog(self); dlg.setWindowTitle("CSV → Variables mapping")
        dlg.setStyleSheet(QSS); dlg.resize(480, 320)
        vb = QVBoxLayout(dlg); vb.setContentsMargins(12,12,12,12)
        vb.addWidget(QLabel(f"CSV has {len(rows)} rows. Map CSV columns to template variables:"))

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner  = QWidget(); fl = QFormLayout(inner); scroll.setWidget(inner)
        vb.addWidget(scroll, 1)

        combos = {}
        for var in var_names:
            cb = QComboBox(); cb.addItem("(skip)")
            cb.addItems(headers)
            # Auto-match by name
            if var in headers: cb.setCurrentText(var)
            elif var.lower() in [h.lower() for h in headers]:
                cb.setCurrentText(next(h for h in headers if h.lower()==var.lower()))
            fl.addRow(f"Variable:  {var}", cb)
            combos[var] = cb

        # Filename pattern
        le_pat = QLineEdit("{n:04d}.png"); le_pat.setPlaceholderText("{n}.png or {col_name}.png")
        vb.addWidget(QLabel("Output filename pattern  (use {n} for row number, {column_name} for column value):"))
        vb.addWidget(le_pat)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); vb.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted: return

        mapping  = {var: cb.currentText() for var,cb in combos.items() if cb.currentText() != "(skip)"}
        pattern  = le_pat.text().strip() or "{n:04d}.png"
        ok_count = 0; errors = []

        for n, row in enumerate(rows, 1):
            try:
                fill = {var: row.get(col, "") for var, col in mapping.items()}
                self.doc.fill_variables(fill)
                # Build filename
                fname = pattern
                try:
                    fname = pattern.format(n=n, **{k: v for k,v in row.items()
                                                    if k and k.isidentifier()})
                except Exception:
                    fname = f"{n:04d}.png"
                out_path = os.path.join(out_dir, fname)
                ext      = os.path.splitext(out_path)[1].lower().lstrip(".")
                fmt      = ext.upper() if ext in ("png","jpg","jpeg","tiff","bmp") else "PNG"
                self.doc.export_bitmap(out_path, page=self._cpi(), dpi=300, format=fmt)
                ok_count += 1
            except Exception as e:
                errors.append(f"Row {n}: {e}")

        msg = f"Exported {ok_count}/{len(rows)} rows to:\n{out_dir}"
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors[:5])
        QMessageBox.information(self, "Batch export done", msg)
        self._status.showMessage(f"Batch export: {ok_count}/{len(rows)} rows")

    def _render_flush(self, dpi=None):
        """v4.1.23.38: prepare the document for off-screen rendering
        (print / export). In document mode the body text boxes are kept
        visible=False while inline-editing (the editor draws instead), so a
        plain render_page would output blank pages. Flush the live edit into
        the body and make every document body visible. Returns a restore list.

        v4.1.23.42: also RE-PAGINATE at the render dpi. The live pagination
        runs at the screen dpi; if the export/print renders at a different dpi,
        word-wrap can shift by a line and the bottom line spills past the
        margin. Paginating at the exact render dpi keeps them in lock-step."""
        restore = []
        try:
            ed = getattr(self, '_inline_widget', None)
            if ed is not None:
                try: ed.sync_to_tb_silent()
                except Exception: pass
        except Exception:
            pass
        try:
            from edof.engine.document_paginate import paginate_document
            paginate_document(self.doc, focus_page=self._cpi(),
                              focus_cursor=None,
                              dpi=float(dpi) if dpi else self._canvas._dpi)
        except Exception:
            pass
        try:
            for pg in (self.doc.pages if self.doc else []):
                for obj in list(getattr(pg, 'objects', [])):
                    if (getattr(obj, 'name', '') == 'document_body'
                            and not getattr(obj, 'visible', True)):
                        restore.append((obj, obj.visible))
                        obj.visible = True
        except Exception:
            pass
        return restore

    def _render_restore(self, restore):
        for obj, vis in (restore or []):
            try: obj.visible = vis
            except Exception: pass
        # v4.1.23.42: the export re-paginated at the render dpi; restore the
        # on-screen pagination at the screen dpi so the editor view matches.
        try:
            from edof.engine.document_paginate import paginate_document
            paginate_document(self.doc, focus_page=self._cpi(),
                              focus_cursor=None, dpi=self._canvas._dpi)
        except Exception:
            pass

    def _print(self):
        if not self.doc or not self.doc.pages: return
        _restore_vis = self._render_flush()
        try:
            from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
            from PyQt6.QtCore import QRectF
            from PyQt6.QtGui import QPainter, QImage

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            # set A4 via QPageSize (correct PyQt6 API)
            from PyQt6.QtGui import QPageSize
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))

            preview = QPrintPreviewDialog(printer, self)
            preview.setWindowTitle("Print Preview – EDOF Editor")
            preview.resize(900, 700)

            def paint_pages(pr: QPrinter):
                """
                Called by QPrintPreviewDialog for each repaint.
                Uses raw PIL bytes → QImage to bypass Qt's 256 MB image limit.
                Renders at max 150 dpi for preview (fast), full dpi for actual print.
                """
                try:
                    from edof.engine.renderer import render_page
                    from PyQt6.QtCore import Qt as _Qt

                    painter = QPainter(pr)
                    if not painter.isActive():
                        return

                    vp = painter.viewport()

                    # Cap DPI: preview uses screen-appropriate resolution,
                    # actual print uses the selected printer DPI (capped at 300).
                    raw_dpi = int(pr.resolution())
                    dpi     = min(raw_dpi, 150)   # never render > 150 dpi for preview

                    _raw_refs = []  # keep raw bytes alive while QImage uses them

                    for i, pg_idx in enumerate(range(len(self.doc.pages))):
                        if i > 0:
                            pr.newPage()
                            vp = painter.viewport()

                        pg  = self.doc.pages[pg_idx]
                        img = render_page(pg, self.doc.resources,
                                          self.doc.variables, dpi=dpi)
                        img = img.convert("RGB")

                        # PIL → raw bytes → QImage
                        # This bypasses Qt's QImageIOHandler allocation limit
                        # completely (no file-format reader involved).
                        raw = img.tobytes()          # RGB bytes
                        _raw_refs.append(raw)        # prevent GC
                        stride = img.width * 3       # bytes per row
                        qimg   = QImage(
                            raw, img.width, img.height,
                            stride, QImage.Format.Format_RGB888,
                        )

                        if qimg.isNull():
                            continue

                        # Scale to fit viewport keeping aspect ratio
                        scaled = qimg.scaled(
                            vp.width(), vp.height(),
                            _Qt.AspectRatioMode.KeepAspectRatio,
                            _Qt.TransformationMode.SmoothTransformation,
                        )
                        # Centre on printable area
                        ox = (vp.width()  - scaled.width())  // 2
                        oy = (vp.height() - scaled.height()) // 2
                        painter.drawImage(ox, oy, scaled)

                    painter.end()
                except Exception as e:
                    import traceback; traceback.print_exc()

            preview.paintRequested.connect(paint_pages)
            preview.exec()
            self._status.showMessage(t('status_print'))
            # v4.1.23.38: restore body visibility (inline edit continues)
            self._render_restore(_restore_vis)
        except ImportError:
            # QtPrintSupport not available – fall back to library method
            try:
                self.doc.print_document()
                self._status.showMessage(t('status_print'))
            except Exception as e:
                QMessageBox.critical(self, "Print Error",
                    f"Printing failed:\n{e}\n\n"
                    f"Install QtPrintSupport or export to PDF and print manually.")
        except Exception as e:
            QMessageBox.critical(self, "Print Error", str(e))

    # ── Dialogs ───────────────────────────────────────────────────────────────
    def _page_settings(self):
        pg=self._cp()
        if not pg: return
        dlg=QDialog(self); dlg.setWindowTitle(t('dlg_page_settings')); dlg.setStyleSheet(QSS)
        dlg.setMinimumWidth(420)
        fl=QFormLayout(dlg); fl.setContentsMargins(16,16,16,16); fl.setSpacing(8)
        sw=QDoubleSpinBox(); sw.setRange(1,9999); sw.setValue(pg.width); sw.setSuffix(" mm")
        sh=QDoubleSpinBox(); sh.setRange(1,9999); sh.setValue(pg.height); sh.setSuffix(" mm")
        sd=QSpinBox(); sd.setRange(72,1200); sd.setValue(pg.dpi); sd.setSuffix(" DPI")
        sd.setToolTip("Export resolution for PDF/PNG. Display quality on screen is "
                       "automatic (zoom-aware) and not affected by this setting.")
        cs=QComboBox(); cs.addItems(["RGB","RGBA","L","1","CMYK"]); cs.setCurrentText(pg.color_space)
        bd=QComboBox(); bd.addItems(["8","16"]); bd.setCurrentText(str(pg.bit_depth))

        # v4.1.3: Page background color picker with alpha
        cur_bg = pg.background
        if isinstance(cur_bg, (tuple, list)):
            if len(cur_bg) >= 4:
                bg_init = tuple(cur_bg)
            else:
                bg_init = (cur_bg[0], cur_bg[1], cur_bg[2], 255)
        else:
            bg_init = (255, 255, 255, 255)
        bg_state = list(bg_init)

        bg_row = QWidget(); hb_bg = QHBoxLayout(bg_row); hb_bg.setContentsMargins(0,0,0,0); hb_bg.setSpacing(6)
        btn_bg = QPushButton(); btn_bg.setFixedSize(40, 24)
        def _refresh_bg_btn():
            r,g,b,a = bg_state
            if a == 0:
                # Transparent indicator: checker-like style
                btn_bg.setStyleSheet(
                    "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                    "stop:0 #d0d0d0, stop:0.5 #f0f0f0, stop:1 #d0d0d0);"
                    "border:1px solid #888;border-radius:3px;")
                btn_bg.setText("⊘"); btn_bg.setToolTip("Transparent")
            else:
                btn_bg.setStyleSheet(
                    f"background:#{r:02x}{g:02x}{b:02x};"
                    "border:1px solid #888;border-radius:3px;")
                btn_bg.setText(""); btn_bg.setToolTip(f"RGBA({r},{g},{b},{a})")
        _refresh_bg_btn()
        def _pick_bg():
            def _prev(col):
                pg.background = tuple(col)
                try: self._canvas.schedule_render()
                except Exception: pass
            new_c = EdofColorDialog.get_color(dlg, tuple(bg_state), alpha=True, on_change=_prev)
            if new_c is not None:
                bg_state[0]=new_c[0]; bg_state[1]=new_c[1]
                bg_state[2]=new_c[2]; bg_state[3]=new_c[3]
                _refresh_bg_btn()
            # reconcile live preview back to the committed state (revert if cancelled)
            pg.background = tuple(bg_state)
            try: self._canvas.schedule_render()
            except Exception: pass
        btn_bg.clicked.connect(_pick_bg)
        # Quick presets
        btn_white = QPushButton("White"); btn_white.setFixedHeight(24)
        btn_white.clicked.connect(lambda: (bg_state.__setitem__(0,255), bg_state.__setitem__(1,255),
                                              bg_state.__setitem__(2,255), bg_state.__setitem__(3,255),
                                              _refresh_bg_btn()))
        btn_transp = QPushButton("Transparent"); btn_transp.setFixedHeight(24)
        btn_transp.setToolTip("Transparent background — shown as checkerboard in editor; "
                                "blank in PNG/PDF export with alpha support")
        btn_transp.clicked.connect(lambda: (bg_state.__setitem__(3,0), _refresh_bg_btn()))
        hb_bg.addWidget(btn_bg); hb_bg.addWidget(btn_white); hb_bg.addWidget(btn_transp); hb_bg.addStretch()

        # Info label
        info=QLabel("<small>DPI is the resolution used when exporting to PDF or PNG. "
                    "On-screen preview is rendered at zoom-aware DPI automatically — "
                    "it always looks crisp regardless of this setting.<br><br>"
                    "Transparent background renders as a checkerboard in the editor "
                    "and as transparency in PNG export.</small>")
        info.setWordWrap(True); info.setStyleSheet(f"color:{FGD};")
        fl.addRow(t('lbl_width'),sw); fl.addRow(t('lbl_height'),sh); fl.addRow(t('lbl_dpi'),sd)
        fl.addRow(t('prop_color_space'),cs); fl.addRow(t('lbl_bit_depth'),bd)
        fl.addRow("Background:", bg_row)
        fl.addRow("", info)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); fl.addRow(bb)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            old_dpi = pg.dpi
            old_bg = tuple(bg_init)
            pg.width=sw.value(); pg.height=sh.value(); pg.dpi=sd.value()
            pg.color_space=cs.currentText(); pg.bit_depth=int(bd.currentText())
            pg.background = tuple(bg_state)
            self._modified = True
            # v4.1.1/4.1.3: aggressive cache clear and re-render
            try:
                self._canvas._render_id += 1
                # Clear any pixmap cache so DPI/bg changes are visible
                if hasattr(self._canvas, '_page_item') and self._canvas._page_item:
                    self._canvas._page_item.setPixmap(self._canvas._page_item.pixmap())
            except Exception: pass
            self._refresh_pages()
            self._canvas.set_document(self.doc, self._cpi())
            # Two renders to ensure the change visibly takes effect
            self._canvas.schedule_render(0)
            QTimer.singleShot(50, lambda: self._canvas.schedule_render(0))
            if old_dpi != pg.dpi:
                self._status.showMessage(
                    f"Page DPI changed: {old_dpi} → {pg.dpi}  (export DPI; "
                    f"on-screen preview is zoom-aware)", 5000)
            elif old_bg != pg.background:
                self._status.showMessage("Page background updated.", 3000)
            else:
                self._status.showMessage("Page settings updated.", 3000)
        else:
            # dialog cancelled: undo any live background preview
            if pg.background != tuple(bg_init):
                pg.background = tuple(bg_init)
                try: self._canvas.schedule_render()
                except Exception: pass

    def _show_vars(self):
        if not self.doc: return
        dlg=QDialog(self); dlg.setWindowTitle(t('dlg_variables')); dlg.resize(520,380)
        dlg.setStyleSheet(QSS); vb=QVBoxLayout(dlg); vb.setContentsMargins(12,12,12,12)
        vb.addWidget(QLabel("Variables for templates / batch fill:"))
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        inner=QWidget(); fl=QFormLayout(inner); fl.setSpacing(5); scroll.setWidget(inner)
        vb.addWidget(scroll,1); entries=[]
        for name in self.doc.variables.names():
            le=QLineEdit(str(self.doc.variables.get(name) or ""))
            fl.addRow(name,le); entries.append((name,le))
        ar=QWidget(); hb=QHBoxLayout(ar); hb.setContentsMargins(0,0,0,0)
        le_new=QLineEdit(); le_new.setPlaceholderText("variable_name")
        cb_t=QComboBox(); cb_t.addItems(["text","number","date","image","qr","url","bool"])
        btn_a=QPushButton("Add"); hb.addWidget(le_new); hb.addWidget(cb_t); hb.addWidget(btn_a)
        vb.addWidget(ar)
        def do_add():
            n=le_new.text().strip()
            if n: self.doc.define_variable(n,type=cb_t.currentText())
            dlg.close(); self._show_vars()
        btn_a.clicked.connect(do_add)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        def apply():
            for name,le in entries:
                try: self.doc.set_variable(name,le.text())
                except Exception: pass
            self._canvas.schedule_render(); self._push("Update vars"); dlg.accept()
        bb.accepted.connect(apply); bb.rejected.connect(dlg.reject); vb.addWidget(bb); dlg.exec()

    def _doc_info(self):
        if not self.doc: return
        dlg=QDialog(self); dlg.setWindowTitle(t('dlg_doc_info')); dlg.setStyleSheet(QSS)
        fl=QFormLayout(dlg); fl.setContentsMargins(16,16,16,16)
        lt=QLineEdit(self.doc.title); la=QLineEdit(self.doc.author); ld=QLineEdit(self.doc.description)
        fl.addRow("Title",lt); fl.addRow("Author",la); fl.addRow("Description",ld)
        cs=QComboBox(); cs.addItems(["RGB","RGBA","L","1","CMYK"]); cs.setCurrentText(self.doc.default_color_space)
        bd=QComboBox(); bd.addItems(["8","16"]); bd.setCurrentText(str(self.doc.default_bit_depth))
        # v4.1.18: document target DPI — affects new pages' inherited DPI and
        # the canvas rendering quality. Higher = crisper print output, larger
        # canvas buffers. Stored as Document.default_dpi.
        dpi = QSpinBox(); dpi.setRange(72, 1200); dpi.setSuffix(" DPI")
        dpi.setValue(getattr(self.doc, 'default_dpi', 300) or 300)
        dpi.setToolTip("Target resolution for export. New pages inherit this. "
                         "On-screen rendering scales to the screen automatically.")
        fl.addRow("Target DPI", dpi)
        fl.addRow(t('lbl_default_cs'),cs); fl.addRow(t('lbl_bit_depth'),bd)
        info=QLabel(f"Created: {self.doc.created[:19]}\nModified: {self.doc.modified[:19]}\n"
                    f"ID: {self.doc.id[:24]}…\nPages: {len(self.doc.pages)}  v{edof.FORMAT_VERSION_STR}")
        info.setStyleSheet(f"color:{FGD};font-family:Consolas;font-size:8pt"); fl.addRow(info)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        def apply():
            self.doc.title=lt.text(); self.doc.author=la.text(); self.doc.description=ld.text()
            self.doc.default_color_space=cs.currentText(); self.doc.default_bit_depth=int(bd.currentText())
            new_dpi = dpi.value()
            dpi_changed = (getattr(self.doc, 'default_dpi', None) != new_dpi)
            self.doc.default_dpi = new_dpi
            # v4.1.18.1: when DPI changes, ask whether to propagate the new
            # value to every existing page (Page.dpi is what the renderer
            # actually reads). Without this the canvas / export keeps using
            # the old per-page DPI and the change appears to do nothing.
            if dpi_changed:
                ret = QMessageBox.question(
                    self, "Apply DPI to all pages?",
                    f"Set every existing page's DPI to {new_dpi} too?\n\n"
                    f"Yes — every page now exports at {new_dpi} DPI and the "
                    f"canvas re-renders at the new resolution.\n"
                    f"No — only new pages will use {new_dpi} DPI; existing "
                    f"pages keep their current value.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes)
                if ret == QMessageBox.StandardButton.Yes:
                    for page in self.doc.pages:
                        page.dpi = new_dpi
                # Force canvas to re-pick rendering DPI
                self._canvas.set_document(self.doc, self._cpi())
                self._mark_modified()
            self._upd_title(); dlg.accept()
        bb.accepted.connect(apply); bb.rejected.connect(dlg.reject); fl.addRow(bb); dlg.exec()

    def _find_replace(self):
        """v4.0: Find & Replace across all pages."""
        if not self.doc: return
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                     QLineEdit, QPushButton, QCheckBox, QLabel)
        dlg = QDialog(self); dlg.setWindowTitle("Find & Replace")
        dlg.setStyleSheet(QSS); dlg.resize(420, 200)
        v = QVBoxLayout(dlg)
        find_edit    = QLineEdit(); find_edit.setPlaceholderText("Find...")
        replace_edit = QLineEdit(); replace_edit.setPlaceholderText("Replace with...")
        case_cb  = QCheckBox("Match case")
        regex_cb = QCheckBox("Regex")
        v.addWidget(QLabel("Find:")); v.addWidget(find_edit)
        v.addWidget(QLabel("Replace:")); v.addWidget(replace_edit)
        h = QHBoxLayout(); h.addWidget(case_cb); h.addWidget(regex_cb); v.addLayout(h)
        result_lbl = QLabel(""); v.addWidget(result_lbl)
        btn_h = QHBoxLayout()
        btn_find  = QPushButton("Find All")
        btn_repl  = QPushButton("Replace All")
        btn_close = QPushButton("Close")
        btn_h.addWidget(btn_find); btn_h.addWidget(btn_repl); btn_h.addWidget(btn_close)
        v.addLayout(btn_h)

        def _iter_textboxes():
            from edof.format.objects import TextBox, Group, Table
            def _walk(objs):
                for o in objs:
                    if isinstance(o, TextBox): yield o
                    elif isinstance(o, Group):
                        yield from _walk(o.children)
                    elif isinstance(o, Table):
                        # Table cells aren't TextBoxes, but they have text
                        pass
            for p in self.doc.pages:
                yield from _walk(p.objects)

        def _do_find():
            import re
            q = find_edit.text()
            if not q: return
            count = 0
            try:
                if regex_cb.isChecked():
                    flags = 0 if case_cb.isChecked() else re.IGNORECASE
                    pat = re.compile(q, flags)
                    for tb in _iter_textboxes():
                        if pat.search(tb.text): count += 1
                else:
                    if case_cb.isChecked():
                        for tb in _iter_textboxes():
                            if q in tb.text: count += 1
                    else:
                        ql = q.lower()
                        for tb in _iter_textboxes():
                            if ql in tb.text.lower(): count += 1
            except re.error as e:
                result_lbl.setText(f"Regex error: {e}"); return
            result_lbl.setText(f"Found in {count} text box(es)")

        def _do_replace():
            import re
            q = find_edit.text()
            r = replace_edit.text()
            if not q: return
            count = 0
            try:
                if regex_cb.isChecked():
                    flags = 0 if case_cb.isChecked() else re.IGNORECASE
                    pat = re.compile(q, flags)
                    for tb in _iter_textboxes():
                        new, n = pat.subn(r, tb.text)
                        if n: tb.text = new; count += n
                else:
                    for tb in _iter_textboxes():
                        if case_cb.isChecked():
                            if q in tb.text:
                                tb.text = tb.text.replace(q, r); count += 1
                        else:
                            # Case-insensitive replace
                            import re as _re
                            new, n = _re.subn(_re.escape(q), r, tb.text, flags=_re.IGNORECASE)
                            if n: tb.text = new; count += n
            except re.error as e:
                result_lbl.setText(f"Regex error: {e}"); return
            result_lbl.setText(f"Replaced {count} occurrence(s)")
            self._render_canvas()

        btn_find.clicked.connect(_do_find)
        btn_repl.clicked.connect(_do_replace)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec()

    def _validate(self):
        if not self.doc: return
        issues=self.doc.validate()
        if issues: QMessageBox.warning(self,t('dlg_validate'),"\n".join(f"• {i}" for i in issues))
        else: QMessageBox.information(self,t('dlg_validate'),"✓ Document is valid.")

    # ══════════════════════════════════════════════════════════════════════════
    # v4.0.1: Protection / Encryption dialogs
    # ══════════════════════════════════════════════════════════════════════════

    def _show_unlock_dialog(self):
        """Prompt for password to unlock an encrypted document."""
        if not self.doc: return
        if not self.doc.is_encrypted:
            QMessageBox.information(self, "Unlock",
                "This document is not encrypted. No password needed.\n\n"
                "You have full edit access (Administrator level).")
            return

        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                     QLineEdit, QPushButton, QRadioButton,
                                     QButtonGroup, QFrame)
        from edof.crypto import EdofWrongPassword

        dlg = QDialog(self); dlg.setWindowTitle("Unlock Document")
        dlg.setStyleSheet(QSS); dlg.resize(440, 280)
        v = QVBoxLayout(dlg)

        v.addWidget(QLabel("<b>This document is encrypted.</b>"))
        info = QLabel(
            f"Available password levels:\n  • " +
            "\n  • ".join(self.doc.password_levels) +
            "\n\nEach password grants a different level of editing access.")
        info.setWordWrap(True)
        v.addWidget(info)

        v.addWidget(QFrame())  # separator

        # Toggle: password vs recovery key
        rb_pwd = QRadioButton("Use password")
        rb_rk  = QRadioButton("Use recovery key")
        rb_pwd.setChecked(True)
        bg = QButtonGroup(dlg); bg.addButton(rb_pwd); bg.addButton(rb_rk)
        v.addWidget(rb_pwd); v.addWidget(rb_rk)

        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText("Password")
        v.addWidget(edit)

        def _toggle_mode():
            if rb_rk.isChecked():
                edit.setEchoMode(QLineEdit.EchoMode.Normal)
                edit.setPlaceholderText("XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
            else:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
                edit.setPlaceholderText("Password")
            edit.clear()
        rb_pwd.toggled.connect(_toggle_mode)
        rb_rk.toggled.connect(_toggle_mode)

        result_lbl = QLabel(""); result_lbl.setStyleSheet("color: #c14;")
        v.addWidget(result_lbl)

        bb = QHBoxLayout()
        ok_btn = QPushButton("Unlock"); cancel_btn = QPushButton("Cancel")
        bb.addStretch(); bb.addWidget(ok_btn); bb.addWidget(cancel_btn)
        v.addLayout(bb)

        def try_unlock():
            try:
                if rb_rk.isChecked():
                    perm = self.doc.unlock(recovery_key=edit.text().strip())
                else:
                    perm = self.doc.unlock(password=edit.text())
                # Reload UI with full content
                self._canvas.set_document(self.doc, self._canvas._page_idx)
                self._obj_panel.set_document(self.doc)
                self._update_protection_status()
                QMessageBox.information(self, "Unlocked",
                    self._format_permission_dialog(perm))
                dlg.accept()
            except EdofWrongPassword:
                result_lbl.setText("Wrong password / recovery key")
                edit.clear()
            except Exception as e:
                result_lbl.setText(f"Error: {e}")

        ok_btn.clicked.connect(try_unlock)
        edit.returnPressed.connect(try_unlock)
        cancel_btn.clicked.connect(dlg.reject)
        edit.setFocus()
        dlg.exec()

    def _format_permission_dialog(self, perm) -> str:
        """Format a 'what you can / can't do' message after unlock."""
        from edof.crypto import describe_permission
        d = describe_permission(perm)
        msg = f"Unlocked at level: {d['label']}\n\n"
        msg += "✓ You CAN:\n"
        for a in d["allowed"]: msg += f"   • {a}\n"
        if d["denied"]:
            msg += "\n✗ You CANNOT:\n"
            for a in d["denied"]: msg += f"   • {a}\n"
        return msg

    def _relock_doc(self):
        if not self.doc or not self.doc.is_encrypted: return
        self.doc.lock()
        self._canvas.set_document(self.doc, self._canvas._page_idx)
        self._update_protection_status()

    def _update_protection_status(self):
        """Update toolbar/status bar to reflect current permission level."""
        if not self.doc: return
        if not self.doc.is_encrypted:
            self._status.showMessage("🔓 Plain document — full edit access")
            return
        if self.doc.is_locked:
            self._status.showMessage("🔒 Document is locked — view only")
        else:
            from edof.crypto import describe_permission
            d = describe_permission(self.doc.permission_level)
            self._status.showMessage(f"🔓 Unlocked: {d['label']} "
                                      f"({self.doc.permission_level.to_string()})")

    def _show_protection_dialog(self):
        """Manage encryption mode and passwords."""
        if not self.doc: return
        if not self.doc.can("admin") and self.doc.is_encrypted:
            QMessageBox.warning(self, "Permission required",
                "Managing protection requires the Administrator password.\n\n"
                "Use Document → Unlock for editing… first.")
            return

        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                     QFormLayout, QLabel, QLineEdit, QPushButton,
                                     QComboBox, QGroupBox, QFrame)

        dlg = QDialog(self); dlg.setWindowTitle("Document Protection")
        dlg.setStyleSheet(QSS); dlg.resize(540, 540)
        v = QVBoxLayout(dlg)

        # Status block
        if self.doc.is_encrypted:
            status_html = (f"<b>Status:</b> 🔒 Encrypted ({self.doc.encryption_mode})<br>"
                           f"<b>Passwords set:</b> {', '.join(self.doc.password_levels) or '(none)'}")
        else:
            status_html = ("<b>Status:</b> 🔓 Plain (no encryption)<br>"
                           "<i>Add a password below to enable encryption.</i>")
        status_lbl = QLabel(status_html); status_lbl.setWordWrap(True)
        v.addWidget(status_lbl)
        v.addWidget(QFrame())

        # Encryption mode (if encrypted)
        if self.doc.is_encrypted:
            mode_box = QGroupBox("Encryption mode")
            mb = QFormLayout(mode_box)
            mode_cb = QComboBox(); mode_cb.addItems(["full", "partial"])
            mode_cb.setCurrentText(self.doc.encryption_mode)
            mb.addRow("Mode:", mode_cb)
            mode_help = QLabel(
                "<i><b>full</b>: nothing is visible without a password.<br>"
                "<b>partial</b>: layout & structure visible, but text content is encrypted.</i>")
            mode_help.setWordWrap(True)
            mb.addRow(mode_help)
            v.addWidget(mode_box)
        else:
            mode_cb = None

        # Password slots
        pwd_box = QGroupBox("Set / change passwords")
        pwd_layout = QFormLayout(pwd_box)
        pwd_inputs = {}
        for level in ("fill", "edit", "design", "admin"):
            le = QLineEdit()
            le.setEchoMode(QLineEdit.EchoMode.Password)
            le.setPlaceholderText("Leave empty to keep / unset")
            pwd_inputs[level] = le
            existing = "✓ set" if level in self.doc.password_levels else "(empty)"
            pwd_layout.addRow(f"{level} ({existing}):", le)
        v.addWidget(pwd_box)

        # Help
        v.addWidget(QLabel(
            "<i>Levels:  fill=template, edit=text, design=full edit, admin=manage protection.</i>"))

        # Recovery key section
        if self.doc.is_encrypted:
            rk_lbl = QLabel("<i>Recovery key was shown when you set the first password. "
                            "If you lost it and want a new one, remove all passwords first.</i>")
            rk_lbl.setWordWrap(True)
            v.addWidget(rk_lbl)

        # Action buttons
        bb = QHBoxLayout()
        clear_btn = QPushButton("Remove all protection")
        clear_btn.setEnabled(self.doc.is_encrypted)
        ok_btn = QPushButton("Apply"); cancel_btn = QPushButton("Cancel")
        bb.addWidget(clear_btn); bb.addStretch()
        bb.addWidget(ok_btn); bb.addWidget(cancel_btn)
        v.addLayout(bb)

        def _apply():
            try:
                # Track if this is the first protection being applied (to show recovery key)
                first_setup = (not self.doc.is_encrypted)

                # Set passwords
                new_pwds = {lv: le.text() for lv, le in pwd_inputs.items() if le.text()}
                if not new_pwds and not self.doc.is_encrypted:
                    QMessageBox.information(self, "No change",
                        "No passwords entered; document remains unprotected.")
                    return

                # Confirm if upgrading plain → encrypted
                if first_setup and new_pwds:
                    confirm = QMessageBox.question(self, "Enable encryption?",
                        "This will encrypt the document with AES-256.\n\n"
                        "WRITE DOWN your passwords AND the recovery key that "
                        "will be shown — without them the document is "
                        "permanently inaccessible.\n\nContinue?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if confirm != QMessageBox.StandardButton.Yes:
                        return

                recovery_key = None
                for level, pwd in new_pwds.items():
                    rk = self.doc.set_password(level, pwd)
                    if rk: recovery_key = rk

                # Set mode
                if mode_cb:
                    self.doc.encryption_mode = mode_cb.currentText()

                # Show recovery key if generated
                if recovery_key:
                    self._show_recovery_key_dialog(recovery_key)

                self._update_protection_status()
                self._push("Protection")
                dlg.accept()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

        def _clear_all():
            confirm = QMessageBox.question(self, "Remove all protection?",
                "This will remove all passwords and decrypt the document.\n\n"
                "After saving, the file will be readable by anyone.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    self.doc.clear_all_protection()
                    self._update_protection_status()
                    self._push("Clear protection")
                    dlg.accept()
                except Exception as e:
                    QMessageBox.warning(self, "Error", str(e))

        ok_btn.clicked.connect(_apply)
        clear_btn.clicked.connect(_clear_all)
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec()

    def _show_recovery_key_dialog(self, recovery_key: str):
        """Show the recovery key with strong emphasis on saving it."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                     QLineEdit, QPushButton, QApplication)
        dlg = QDialog(self); dlg.setWindowTitle("Recovery Key — SAVE THIS NOW")
        dlg.setStyleSheet(QSS); dlg.resize(520, 280)
        v = QVBoxLayout(dlg)

        warn = QLabel(
            "<h3 style='color:#c14;'>⚠ Save this recovery key NOW</h3>"
            "<p>If you lose all your passwords, this is the <b>only</b> way "
            "to recover the document. It will <b>not</b> be shown again. "
            "Store it in a password manager or print it to paper.</p>")
        warn.setWordWrap(True)
        v.addWidget(warn)

        key_edit = QLineEdit(recovery_key)
        key_edit.setReadOnly(True)
        key_edit.setStyleSheet(
            "font-family: 'Courier New', monospace; font-size: 16pt; "
            "background: #f8f8f0; padding: 8px;")
        v.addWidget(key_edit)

        bb = QHBoxLayout()
        copy_btn = QPushButton("Copy to clipboard")
        ok_btn = QPushButton("I have saved this key")
        bb.addWidget(copy_btn); bb.addStretch(); bb.addWidget(ok_btn)
        v.addLayout(bb)

        confirmed = [False]
        def do_copy():
            QApplication.clipboard().setText(recovery_key)
            copy_btn.setText("Copied ✓"); confirmed[0] = True
        def do_ok():
            if not confirmed[0]:
                r = QMessageBox.question(dlg, "Confirm",
                    "Have you really copied / written down the recovery key?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if r != QMessageBox.StandardButton.Yes: return
            dlg.accept()
        copy_btn.clicked.connect(do_copy)
        ok_btn.clicked.connect(do_ok)
        dlg.exec()

    # ══════════════════════════════════════════════════════════════════════════
    # v4.0.1: New file actions
    # ══════════════════════════════════════════════════════════════════════════

    def _save_as_v3(self):
        """Save as a v3-compatible .edof file (lossy downgrade)."""
        if not self.doc: return
        path,_=QFileDialog.getSaveFileName(self, "Save as v3 (downgrade)",
            "", "EDOF v3 files (*.edof)")
        if not path: return
        if not path.lower().endswith(".edof"): path+=".edof"
        try:
            self.doc.export_3x(path)
            QMessageBox.information(self, "Saved as v3",
                f"Document downgraded and saved to:\n{path}\n\n"
                f"Note: Tables, rich text, paths, gradients, and conditional\n"
                f"visibility have been flattened. The original document is\n"
                f"unchanged.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save as v3:\n{e}")

    def _import_pdf(self):
        """Import a PDF as an editable EDOF document."""
        if not self._confirm(): return
        path,_=QFileDialog.getOpenFileName(self, "Import PDF",
            "", "PDF files (*.pdf)")
        if not path: return
        try:
            new_doc=edof.import_pdf(path, detect_tables=True)
            self.doc=new_doc; self.filepath=None
            self._canvas.set_document(new_doc, 0)
            self._obj_panel.set_document(new_doc)
            self.setWindowTitle(f"edof editor — Imported from {os.path.basename(path)}")
            self._push("Import PDF")
            n_errors=len(new_doc.errors)
            msg=f"Imported {sum(len(p.objects) for p in new_doc.pages)} objects from PDF."
            if n_errors:
                msg+=f"\n\n{n_errors} migration warning(s):\n"
                msg+="\n".join(f"• {e}" for e in new_doc.errors[:5])
            QMessageBox.information(self, "Import successful", msg)
        except Exception as e:
            QMessageBox.warning(self, "Import error", f"Could not import PDF:\n{e}")

    # v4.0.3: RTF import/export handlers
    def _import_rtf(self):
        if not self._confirm(): return
        path,_=QFileDialog.getOpenFileName(self, "Import RTF",
            "", "RTF files (*.rtf)")
        if not path: return
        try:
            new_doc=edof.import_rtf(path)
            self.doc=new_doc; self.filepath=None
            self._canvas.set_document(new_doc, 0)
            self._obj_panel.set_document(new_doc)
            self.setWindowTitle(f"edof editor — Imported from {os.path.basename(path)}")
            self._push("Import RTF")
            QMessageBox.information(self, "Import successful",
                f"Imported {sum(len(p.objects) for p in new_doc.pages)} text "
                f"box(es) from RTF.")
        except Exception as e:
            QMessageBox.warning(self, "Import error", f"Could not import RTF:\n{e}")

    def _import_font(self):
        """v4.1.0: Embed a custom .ttf/.otf font into the document.
        The font bytes are stored as a resource and registered in QFontDatabase
        for the active editor session (not persisted across sessions).
        """
        if not self.doc:
            QMessageBox.information(self, "No document", "Open or create a document first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import Font",
            "", "TrueType / OpenType fonts (*.ttf *.otf);;All (*.*)")
        if not path: return
        try:
            # Read the font file
            with open(path, "rb") as f:
                font_bytes = f.read()
            # Register with QFontDatabase for current session
            from PyQt6.QtGui import QFontDatabase
            font_id = QFontDatabase.addApplicationFontFromData(font_bytes)
            if font_id < 0:
                QMessageBox.warning(self, "Import error",
                    "Qt could not load the font file. The file may be corrupted "
                    "or use an unsupported format.")
                return
            families = QFontDatabase.applicationFontFamilies(font_id)
            if not families:
                QMessageBox.warning(self, "Import error",
                    "Font registered but no font families found.")
                return
            family_name = families[0]
            # Embed as resource so it travels with the document
            try:
                # add returns auto-id; we'll use add to register with proper bytes
                self.doc.resources.add(font_bytes,
                    filename=os.path.basename(path),
                    mime_type="font/ttf" if path.lower().endswith(".ttf") else "font/otf")
            except Exception:
                pass
            self._modified = True; self._upd_title()
            # Refresh font dropdown
            self._load_fonts()
            QMessageBox.information(self, "Font imported",
                f"Imported '{family_name}' from {os.path.basename(path)}.\n\n"
                f"You can now select it in the Font dropdown.\n"
                f"Note: This font is NOT one of the Standard 14 PDF fonts, so "
                f"vector PDF export may fall back to Helvetica. Use Raster PDF "
                f"export to preserve the custom font.")
        except Exception as e:
            QMessageBox.warning(self, "Import error", f"Could not import font:\n{e}")

    def _export_rtf(self):
        if not self.doc: return
        path,_=QFileDialog.getSaveFileName(self, "Export RTF",
            "", "RTF files (*.rtf)")
        if not path: return
        if not path.lower().endswith(".rtf"): path+=".rtf"
        try:
            self.doc.export_rtf(path)
            self._status.showMessage(f"RTF saved: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not export RTF:\n{e}")

    def _export_docx(self):
        """v4.1.24.0: export the document-mode body flow to a .docx file."""
        if not self.doc: return
        # Flush any in-progress body edit so the export reflects the latest text.
        try: self._commit_pending_body()
        except Exception: pass
        try: self._body_sync_active()
        except Exception: pass
        path,_=QFileDialog.getSaveFileName(self, "Export Word (.docx)",
            "", "Word documents (*.docx)")
        if not path: return
        if not path.lower().endswith(".docx"): path+=".docx"
        try:
            from edof.interop import docx_io
            rep = docx_io.export_docx(self.doc, path)
            self._status.showMessage(f"DOCX saved: {os.path.basename(path)}")
            msg = (f"Exported {rep.paragraphs} paragraph(s) to "
                   f"{os.path.basename(path)}.")
            if rep.warnings:
                msg += "\n\nNotes:\n" + "\n".join("• " + w for w in rep.warnings)
            QMessageBox.information(self, "Export successful", msg)
        except RuntimeError as e:
            QMessageBox.warning(self, "DOCX support missing", str(e))
        except Exception as e:
            QMessageBox.warning(self, "Export error", f"Could not export DOCX:\n{e}")

    def _import_docx(self):
        """v4.1.24.0: import a .docx into a new document-mode EDOF document.

        Unsupported content (tables, images, …) is not imported; when it is
        significant the user is warned and advised against importing, but may
        still proceed to bring in the plain text."""
        if not self._confirm(): return
        path,_=QFileDialog.getOpenFileName(self, "Import Word (.docx)",
            "", "Word documents (*.docx)")
        if not path: return
        try:
            from edof.interop import docx_io
            new_doc, rep = docx_io.import_docx(path)
        except RuntimeError as e:
            QMessageBox.warning(self, "DOCX support missing", str(e)); return
        except Exception as e:
            QMessageBox.warning(self, "Import error",
                f"Could not read DOCX:\n{e}"); return
        # Compatibility gate.
        if not rep.recommend_import:
            ret = QMessageBox.question(self, "Not fully EDOF-compatible",
                rep.recommend_reason + "\n\nImport the text anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                return
        elif rep.unsupported:
            QMessageBox.information(self, "Some content dropped",
                rep.recommend_reason or rep.summary())
        # Adopt the imported document (fresh, unsaved).
        self.doc = new_doc; self.filepath = None; self._modified = True
        self.history.clear(); self.history.push(self.doc, None, "Import DOCX"); self._arm_history_suppression()
        self._canvas.set_document(self.doc, 0)
        self._refresh_pages(); self._upd_title()
        self._status.showMessage(
            f"Imported {rep.paragraphs} paragraph(s) from {os.path.basename(path)}")

    def _export_svg(self):
        """Export current page as SVG.
        v4.1.13.6: Cleaned up — removed orphaned gradient editor code that
        was accidentally inlined into this function and ran after every
        export, opening a hidden gradient dialog that wiped fill.color
        when accepted."""
        if not self.doc: return
        path,_=QFileDialog.getSaveFileName(self, "Export SVG",
            "", "SVG files (*.svg)")
        if not path: return
        if not path.lower().endswith(".svg"): path+=".svg"
        try:
            self.doc.export_svg(path, page=self._canvas._page_idx)
            self._status.showMessage(f"SVG saved: {os.path.basename(path)}")
            self._canvas.schedule_render(0)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not export SVG:\n{e}")

    # ── v4.0.1: Template gallery ──────────────────────────────────────────────

    def _gradient_editor(self):
        """Open visual gradient editor for the selected object."""
        if not self._check_perm("design", "Gradient editor"): return
        obj=self._canvas._sel_obj()
        if not obj or not hasattr(obj,'fill'):
            QMessageBox.information(self,"Gradient Editor",
                "Select a shape or text box first.")
            return
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                                     QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
                                     QListWidget, QListWidgetItem, QColorDialog, QLabel)
        from edof.format.styles import Gradient
        dlg=QDialog(self); dlg.setWindowTitle("Gradient Editor")
        dlg.setStyleSheet(QSS); dlg.resize(420, 380)
        v=QVBoxLayout(dlg)

        g=obj.fill.gradient or Gradient(type="linear", angle=0,
            stops=[(0.0,(255,255,255,255)), (1.0,(0,0,0,255))])

        f=QFormLayout()
        type_cb=QComboBox(); type_cb.addItems(["linear","radial"])
        type_cb.setCurrentText(g.type); f.addRow("Type:", type_cb)
        angle_sb=QDoubleSpinBox(); angle_sb.setRange(0,360); angle_sb.setValue(g.angle)
        f.addRow("Angle (linear, deg):", angle_sb)
        radius_sb=QDoubleSpinBox(); radius_sb.setRange(0.05, 2.0); radius_sb.setSingleStep(0.05)
        radius_sb.setValue(g.radius); f.addRow("Radius (radial, 0–1):", radius_sb)
        v.addLayout(f)

        v.addWidget(QLabel("Color stops (drag to reorder, double-click to recolor):"))
        stops_lw=QListWidget()
        for off, col in g.stops:
            it=QListWidgetItem(f"@ {off:.2f}  rgb={col[:3]} a={col[3] if len(col)>=4 else 255}")
            it.setData(Qt.ItemDataRole.UserRole,(off,col))
            stops_lw.addItem(it)
        v.addWidget(stops_lw)

        def edit_stop(item):
            off,col=item.data(Qt.ItemDataRole.UserRole)
            qcol=QColorDialog.getColor(QColor(*col[:3]),self,"Stop color")
            if qcol.isValid():
                new=(qcol.red(),qcol.green(),qcol.blue(), col[3] if len(col)>=4 else 255)
                item.setText(f"@ {off:.2f}  rgb={new[:3]} a={new[3]}")
                item.setData(Qt.ItemDataRole.UserRole,(off,new))
        stops_lw.itemDoubleClicked.connect(edit_stop)

        bh=QHBoxLayout()
        add_b=QPushButton("+ Stop"); del_b=QPushButton("− Stop")
        bh.addWidget(add_b); bh.addWidget(del_b); v.addLayout(bh)
        def add_stop():
            it=QListWidgetItem("@ 0.50  rgb=(128, 128, 128) a=255")
            it.setData(Qt.ItemDataRole.UserRole,(0.5,(128,128,128,255)))
            stops_lw.addItem(it)
        def del_stop():
            for it in stops_lw.selectedItems(): stops_lw.takeItem(stops_lw.row(it))
        add_b.clicked.connect(add_stop); del_b.clicked.connect(del_stop)

        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                            QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(bb)
        def apply():
            stops=[]
            for i in range(stops_lw.count()):
                stops.append(stops_lw.item(i).data(Qt.ItemDataRole.UserRole))
            new_g=Gradient(type=type_cb.currentText(), angle=angle_sb.value(),
                            radius=radius_sb.value(), stops=stops)
            obj.fill.gradient=new_g; obj.fill.color=None
            self._canvas.schedule_render(); self._push("Gradient")
            dlg.accept()
        bb.accepted.connect(apply); bb.rejected.connect(dlg.reject)
        dlg.exec()

    def _new_from_template(self):
        """Create a new document from a built-in template."""
        from PyQt6.QtWidgets import QInputDialog
        templates={
            "Blank A4 Portrait":           lambda: edof.new(width=210, height=297),
            "Blank A4 Landscape":          lambda: edof.new(width=297, height=210),
            "Business Card (85×55)":       _tpl_business_card,
            "Certificate (A4 Landscape)":  _tpl_certificate,
            "Invoice (A4)":                _tpl_invoice,
        }
        name, ok = QInputDialog.getItem(self, "New from Template",
            "Select a template:", list(templates.keys()), 0, False)
        if not ok: return
        if not self._confirm(): return
        new_doc=templates[name]()
        if not new_doc.pages: new_doc.add_page()
        self.doc=new_doc; self.filepath=None
        self._canvas.set_document(new_doc, 0)
        self._obj_panel.set_document(new_doc)
        self.setWindowTitle(f"edof editor — {name}")
        self._push("New from template")

    def _load_fonts(self):
        try:
            fonts=list_system_fonts()
            if not fonts: fonts=["Arial","Times New Roman","Courier New","Helvetica"]
            self._props.set_font_list(fonts)
            self._status.showMessage(t('status_fonts',n=len(fonts)))
        except Exception: pass

    def closeEvent(self,event):
        if self._confirm(): event.accept()
        else: event.ignore()


# ══════════════════════════════════════════════════════════════════════════════
#  v4.0.1  Built-in templates
# ══════════════════════════════════════════════════════════════════════════════

def _tpl_business_card():
    """Standard 85×55mm business card."""
    from edof.format.styles import TextRun
    doc=edof.new(width=85, height=55, title="Business Card")
    page=doc.add_page(dpi=300)
    name=page.add_textbox(5, 10, 75, 8, "Your Name")
    name.style.font_size=4.939; name.style.bold=True; name.style.alignment="left"
    title=page.add_textbox(5, 18, 75, 5, "Title / Position")
    title.style.font_size=3.175; title.style.italic=True; title.style.color=(120,120,120)
    page.add_textbox(5, 30, 75, 4, "phone@example.com").style.font_size=2.822
    page.add_textbox(5, 35, 75, 4, "+420 000 000 000").style.font_size=2.822
    page.add_textbox(5, 40, 75, 4, "www.example.com").style.font_size=2.822
    return doc

def _tpl_certificate():
    """A4 landscape certificate template."""
    from edof.format.styles import TextRun
    doc=edof.new(width=297, height=210, title="Certificate")
    page=doc.add_page(dpi=300)
    # Outer border
    border=page.add_shape("rect", 10, 10, 277, 190)
    border.fill.color=None; border.stroke.color=(50,50,100,255); border.stroke.width=2
    # Header
    hdr=page.add_textbox(20, 30, 257, 20, "CERTIFICATE OF ACHIEVEMENT")
    hdr.style.font_size=11.289; hdr.style.bold=True; hdr.style.alignment="center"
    hdr.style.color=(50,50,100)
    # Subtitle
    sub=page.add_textbox(20, 60, 257, 10, "is hereby presented to")
    sub.style.font_size=4.939; sub.style.italic=True; sub.style.alignment="center"
    sub.style.color=(120,120,120)
    # Recipient (variable)
    rec=page.add_textbox(20, 80, 257, 25, "Recipient Name")
    rec.style.font_size=12.700; rec.style.bold=True; rec.style.alignment="center"
    rec.variable="recipient"
    # Description
    desc=page.add_textbox(20, 120, 257, 20,
        "for outstanding achievement and dedication.")
    desc.style.font_size=4.939; desc.style.alignment="center"
    desc.style.wrap=True
    # Date
    page.add_textbox(20, 160, 100, 10, "Date").style.font_size=3.528
    page.add_textbox(180, 160, 100, 10, "Signature").style.font_size=3.528
    doc.define_variable("recipient", required=True)
    return doc

def _tpl_invoice():
    """A4 invoice template with table."""
    from edof.format.objects import Table, TableCell
    doc=edof.new(width=210, height=297, title="Invoice")
    page=doc.add_page(dpi=300)
    # Header
    hdr=page.add_textbox(15, 15, 100, 12, "INVOICE")
    hdr.style.font_size=9.878; hdr.style.bold=True; hdr.style.color=(50,80,160)
    # Number
    num=page.add_textbox(120, 15, 75, 6, "#{invoice_number}")
    num.style.font_size=4.233; num.style.alignment="right"
    # Date
    dt=page.add_textbox(120, 22, 75, 5, "Date: {date}")
    dt.style.font_size=3.528; dt.style.alignment="right"
    # From / To
    page.add_textbox(15, 40, 90, 6, "From:").style.bold=True
    page.add_textbox(15, 47, 90, 25, "Your Company\nStreet 123\n100 00 City").style.font_size=3.528
    page.add_textbox(110, 40, 85, 6, "Bill to:").style.bold=True
    page.add_textbox(110, 47, 85, 25, "{client_name}\n{client_address}").style.font_size=3.528
    # Items table
    tbl=Table()
    tbl.transform.x=15; tbl.transform.y=85; tbl.transform.width=180; tbl.transform.height=80
    tbl.col_widths=[80, 25, 30, 45]
    tbl.cells=[
        [TableCell(text="Description"), TableCell(text="Qty"),
         TableCell(text="Unit Price"), TableCell(text="Total")],
        [TableCell(text="Item 1"), TableCell(text="1"),
         TableCell(text="0.00"), TableCell(text="0.00")],
        [TableCell(text="Item 2"), TableCell(text="1"),
         TableCell(text="0.00"), TableCell(text="0.00")],
        [TableCell(text="Item 3"), TableCell(text="1"),
         TableCell(text="0.00"), TableCell(text="0.00")],
    ]
    for c in tbl.cells[0]:
        c.bg_color=(50,80,160,255); c.style.color=(255,255,255); c.style.bold=True
    page.add_object(tbl)
    # Total
    total=page.add_textbox(110, 175, 85, 8, "TOTAL: {total} CZK")
    total.style.font_size=4.939; total.style.bold=True; total.style.alignment="right"
    # Footer
    foot=page.add_textbox(15, 270, 180, 8, "Thank you for your business.")
    foot.style.font_size=3.175; foot.style.italic=True; foot.style.alignment="center"
    foot.style.color=(120,120,120)
    # Variables
    doc.define_variable("invoice_number", default="2026-001")
    doc.define_variable("date", default="2026-01-01")
    doc.define_variable("client_name", default="Client Name")
    doc.define_variable("client_address", default="Client Address")
    doc.define_variable("total", default="0.00")
    return doc


def main():
    # v4.2.4: own taskbar identity so Windows shows the EDOF icon, not Python's.
    try:
        from edof._apps.assets import set_windows_app_id
        set_windows_app_id("DavidSchobl.EDOF.Editor")
    except Exception:
        pass

    # Remove Qt image allocation limit (default 256 MB blocks large print jobs)
    try:
        from PyQt6.QtGui import QImageReader
        QImageReader.setAllocationLimit(0)   # 0 = unlimited
    except Exception:
        pass

    # v4.1.23.46: surface startup/runtime crashes. The Windows launcher uses
    # pythonw (no console), so an uncaught exception during startup just made
    # the window silently fail to appear ("úvodní okno se nenačte"). Write the
    # full traceback to the debug log AND show it in a dialog so the cause is
    # visible instead of a blank failure.
    import traceback as _tb

    def _log_crash(text):
        try:
            import os as _os
            path = _os.environ.get("EDOF_DEBUG_PATH") or _os.path.join(
                _os.path.expanduser("~"), "edof_debug.log")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n==== EDOF CRASH ====\n" + text + "\n")
        except Exception:
            pass

    def _excepthook(exc_type, exc, tb):
        text = "".join(_tb.format_exception(exc_type, exc, tb))
        _log_crash(text)
        try:
            from PyQt6.QtWidgets import QMessageBox
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("EDOF — error")
            box.setText("EDOF hit an error.")
            box.setDetailedText(text)
            box.exec()
        except Exception:
            pass
    sys.excepthook = _excepthook

    # v4.2.10.6: guaranteed startup line. The moment the editor launches with
    # EDOF_DEBUG enabled, create the log file immediately with a header showing
    # the resolved path, so the file appears even before any curve/key event.
    # This gives instant confirmation that logging is on and where it lives.
    try:
        from edof.engine.debug_log import is_enabled as _dbg_on, log as _dlog, current_path as _dbg_path
        if _dbg_on():
            _dlog("editor.startup", version=edof.__version__, log_path=_dbg_path())
    except Exception:
        pass

    app=QApplication(sys.argv); app.setApplicationName("EDOF Editor")
    app.setApplicationVersion(edof.__version__)
    try:
        from edof._apps.assets import icon_path
        _ip = icon_path("edof-editor.ico") or icon_path("edof-editor.png")
        if _ip:
            app.setWindowIcon(QIcon(_ip))
    except Exception:
        pass
    try:
        win=EdofEditor(sys.argv[1] if len(sys.argv)>1 else None)
        win.show()
    except Exception:
        _excepthook(*sys.exc_info())
        sys.exit(1)
    sys.exit(app.exec())

if __name__=="__main__": main()
