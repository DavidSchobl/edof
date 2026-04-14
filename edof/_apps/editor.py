#!/usr/bin/env python3
"""
EDOF Editor 3.0 – PyQt6
Requires: pip install PyQt6 Pillow edof
"""
import sys, os, math, copy, io as _io, json, threading

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
        QGraphicsItem, QGraphicsPixmapItem, QGraphicsProxyWidget,
        QWidget, QDockWidget, QListWidget, QListWidgetItem, QAbstractItemView,
        QTabWidget, QFormLayout, QLabel, QLineEdit, QTextEdit, QPlainTextEdit,
        QCheckBox, QComboBox, QPushButton, QDoubleSpinBox, QSpinBox,
        QToolBar, QStatusBar, QMenu, QScrollArea,
        QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
        QFileDialog, QMessageBox, QInputDialog, QColorDialog,
        QDialog, QDialogButtonBox, QStackedWidget,
        QRadioButton, QButtonGroup, QSplitter, QSizePolicy, QSlider,
    )
    from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, QSize, pyqtSignal, QObject
    from PyQt6.QtGui import (
        QAction, QPainter, QPen, QBrush, QColor, QPixmap, QImage,
        QPolygonF, QFont, QTransform, QCursor, QKeySequence,
    )
except ImportError:
    print("PyQt6 required:  pip install PyQt6"); sys.exit(1)

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
QMainWindow,QWidget{{background:{PBG};color:{FG};font:9pt 'Segoe UI'}}
QMenuBar{{background:#131320;color:{FG}}} QMenuBar::item:selected{{background:{ACC}}}
QMenu{{background:{PBG2};color:{FG};border:1px solid #444}} QMenu::item:selected{{background:{ACC}}}
QToolBar{{background:#131320;border:none;padding:2px}}
QToolButton{{background:{PBG2};color:{FG};border:none;padding:3px 8px;border-radius:3px}}
QToolButton:hover{{background:{ACC}}}
QDockWidget::title{{background:#131320;padding:4px;font-weight:bold;color:{FGD}}}
QTabWidget::pane{{border:none;background:{PBG}}}
QTabBar::tab{{background:{PBG2};color:{FGD};padding:4px 10px;border:none}}
QTabBar::tab:selected{{background:{PBG};color:{FG};border-top:2px solid {ACC}}}
QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox,QTextEdit,QPlainTextEdit{{
  background:{PBG3};color:{FG};border:1px solid #3a3a5a;border-radius:3px;padding:1px 4px}}
QLineEdit:focus,QDoubleSpinBox:focus,QSpinBox:focus,QPlainTextEdit:focus{{border:1px solid {ACC}}}
QPushButton{{background:#333355;color:{FG};border:none;padding:3px 10px;border-radius:3px;min-height:22px}}
QPushButton:hover{{background:{ACC}}}
QPushButton#acc{{background:{ACC};color:white;font-weight:bold}}
QPushButton#danger{{background:#883333;color:white}}
QCheckBox,QRadioButton{{color:{FG};spacing:5px}}
QCheckBox::indicator,QRadioButton::indicator{{width:14px;height:14px;background:{PBG3};border:1px solid #555;border-radius:3px}}
QCheckBox::indicator:checked{{background:{ACC};border-color:{ACC}}}
QRadioButton::indicator{{border-radius:7px}} QRadioButton::indicator:checked{{background:{ACC};border-color:{ACC}}}
QComboBox::drop-down{{border:none;width:16px}}
QComboBox QAbstractItemView{{background:{PBG2};color:{FG};selection-background-color:{ACC}}}
QListWidget{{background:#1a1a2e;color:{FG};border:none;outline:none}}
QListWidget::item:selected{{background:{ACC}}}
QScrollBar:vertical{{background:{PBG};width:8px}} QScrollBar::handle:vertical{{background:#444;border-radius:4px;min-height:20px}}
QGroupBox{{border:1px solid #333;border-radius:4px;margin-top:8px;padding-top:6px;color:{FGD}}}
QGroupBox::title{{subcontrol-origin:margin;padding:0 4px}}
QStatusBar{{background:#131320;color:{FGD};font-size:8pt}}
QSlider::groove:horizontal{{background:{PBG3};height:4px;border-radius:2px}}
QSlider::handle:horizontal{{background:{ACC};width:14px;height:14px;border-radius:7px;margin:-5px 0}}
"""
A4W,A4H=210.0,297.0

# ── Color utilities ────────────────────────────────────────────────────────────

def _to_qc(c) -> QColor:
    if not c: return QColor(0,0,0,255)
    t=tuple(int(v) for v in c)
    return QColor(t[0],t[1],t[2],t[3] if len(t)>=4 else 255)

def _from_qc(c: QColor) -> tuple:
    return (c.red(),c.green(),c.blue(),c.alpha())

def _cswatch(c) -> str:
    q=_to_qc(c)
    return f"background:rgba({q.red()},{q.green()},{q.blue()},{q.alpha()});border:1px solid #777;border-radius:3px"


# ═══════════════════════════════════════════════════════════════════════════════
#  Custom Color Dialog with hex + alpha slider
# ═══════════════════════════════════════════════════════════════════════════════

class EdofColorDialog(QDialog):
    def __init__(self, initial=(0,0,0,255), parent=None, alpha=True):
        super().__init__(parent)
        self.setWindowTitle("Color"); self.setStyleSheet(QSS)
        self.setFixedSize(280, 300 if alpha else 240)
        self._alpha_enabled = alpha
        self._color = list(initial[:4]) if len(initial)>=4 else [*initial[:3],255]

        vb=QVBoxLayout(self); vb.setContentsMargins(12,12,12,12); vb.setSpacing(8)

        # Preview swatch
        self._swatch=QLabel(); self._swatch.setFixedHeight(32)
        self._swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vb.addWidget(self._swatch)

        # Hex input
        hrow=QWidget(); hb=QHBoxLayout(hrow); hb.setContentsMargins(0,0,0,0)
        hb.addWidget(QLabel("Hex:"))
        self._hex=QLineEdit(); self._hex.setMaxLength(9); self._hex.setFixedWidth(90)
        self._hex.editingFinished.connect(self._from_hex)
        hb.addWidget(self._hex); hb.addStretch()
        vb.addWidget(hrow)

        # RGBA sliders
        self._sliders={}; self._labels={}
        channels=[("R","color_r",0),("G","color_g",1),("B","color_b",2)]
        if alpha: channels.append(("A","color_a",3))
        for name,key,idx in channels:
            row=QWidget(); rb=QHBoxLayout(row); rb.setContentsMargins(0,0,0,0)
            rb.addWidget(QLabel(t(key)).setMinimumWidth(12) or QLabel(t(key)))
            sl=QSlider(Qt.Orientation.Horizontal); sl.setRange(0,255); sl.setValue(self._color[idx])
            lbl=QLabel(str(self._color[idx])); lbl.setFixedWidth(30)
            sl.valueChanged.connect(lambda v,i=idx,l=lbl: self._on_slider(i,v,l))
            rb.addWidget(sl); rb.addWidget(lbl)
            row.setLayout(rb); vb.addWidget(row)
            self._sliders[idx]=sl; self._labels[idx]=lbl

        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|
                            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        vb.addWidget(bb)
        self._update_display()

    def _on_slider(self, idx, v, lbl):
        self._color[idx]=v; lbl.setText(str(v)); self._update_display()

    def _update_display(self):
        r,g,b,a=self._color
        self._swatch.setStyleSheet(
            f"background:rgba({r},{g},{b},{a});border:1px solid #777;border-radius:4px")
        hex8="#%02x%02x%02x%02x"%(r,g,b,a)
        self._hex.blockSignals(True); self._hex.setText(hex8); self._hex.blockSignals(False)

    def _from_hex(self):
        h=self._hex.text().strip().lstrip("#")
        try:
            if len(h)==6:   r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16); a=255
            elif len(h)==8: r,g,b,a=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16),int(h[6:8],16)
            else: return
            self._color=[r,g,b,a]
            for idx,v in [(0,r),(1,g),(2,b),(3,a)]:
                if idx in self._sliders:
                    self._sliders[idx].blockSignals(True)
                    self._sliders[idx].setValue(v)
                    self._labels[idx].setText(str(v))
                    self._sliders[idx].blockSignals(False)
            self._update_display()
        except Exception: pass

    def color(self) -> tuple:
        return tuple(self._color)

    @staticmethod
    def get_color(parent, initial=(0,0,0,255), alpha=True):
        dlg=EdofColorDialog(initial, parent, alpha)
        if dlg.exec()==QDialog.DialogCode.Accepted:
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

    def update_for(self, obj, dpi):
        self._handles.clear(); self._is_line=False
        if obj is None: self.prepareGeometryChange(); return

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
        pts={'TL':(t.x,t.y),'TC':(t.x+t.width/2,t.y),'TR':(t.x+t.width,t.y),
             'ML':(t.x,t.y+t.height/2),'MR':(t.x+t.width,t.y+t.height/2),
             'BL':(t.x,t.y+t.height),'BC':(t.x+t.width/2,t.y+t.height),
             'BR':(t.x+t.width,t.y+t.height)}
        for k,(mx,my) in pts.items(): self._handles[k]=rs(mx,my)
        rad=math.radians(t.rotation); tc=self._handles['TC']
        self._handles['ROT']=QPointF(tc.x()+ROT_DIST*math.sin(rad),
                                      tc.y()-ROT_DIST*math.cos(rad))
        self._tc_pt=tc
        self._poly=QPolygonF([rs(*pts['TL']),rs(*pts['TR']),rs(*pts['BR']),rs(*pts['BL'])])
        self.prepareGeometryChange()

    def hit_handle(self, sp):
        HIT=HSIZE+6
        for k,pt in self._handles.items():
            if abs(sp.x()-pt.x())<=HIT and abs(sp.y()-pt.y())<=HIT: return k
        return None

    def cursor_for(self, h): return self._CUR.get(h,Qt.CursorShape.ArrowCursor)
    def boundingRect(self): return QRectF(-9999,-9999,19998,19998)

    def paint(self, p, opt, widget):
        if not self._handles: return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._is_line:
            p.setPen(QPen(QColor(ACC),2,Qt.PenStyle.DashLine)); p.drawLine(self._lp1,self._lp2)
            for pt in (self._lp1,self._lp2):
                r=QRectF(pt.x()-HSIZE,pt.y()-HSIZE,HSIZE*2,HSIZE*2)
                p.setPen(QPen(QColor(ACC),2)); p.setBrush(QBrush(QColor("white"))); p.drawEllipse(r)
            return
        pen=QPen(QColor(ACC),2,Qt.PenStyle.DashLine); pen.setDashPattern([5,3])
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPolygon(self._poly)
        rot=self._handles.get('ROT')
        if rot:
            p.setPen(QPen(QColor(ACC),1,Qt.PenStyle.DotLine)); p.drawLine(self._tc_pt,rot)
        for k,pt in self._handles.items():
            r=QRectF(pt.x()-HSIZE,pt.y()-HSIZE,HSIZE*2,HSIZE*2)
            if k=='ROT':
                p.setPen(QPen(QColor("white"),2)); p.setBrush(QBrush(QColor(ACC2))); p.drawEllipse(r)
            else:
                p.setPen(QPen(QColor(ACC),2)); p.setBrush(QBrush(QColor("white"))); p.drawRect(r)


# ═══════════════════════════════════════════════════════════════════════════════
#  EdofCanvas  –  QGraphicsView
# ═══════════════════════════════════════════════════════════════════════════════

class EdofCanvas(QGraphicsView):
    objectSelected=pyqtSignal(object)
    objectChanged=pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc=None; self._page_idx=0; self._dpi=float(RDPI); self._zoom=1.0
        self._sel_id=None
        self._drag_mode=None; self._drag_sp0=None; self._drag_tf0=None; self._drag_anchor=None
        self._pan_start=None; self._pan_scroll0=None
        self._preview_item=None; self._ghost_items=[]
        # Inline editor (key fix: no QGraphicsProxyWidget, use viewport overlay)
        self._inline_widget=None; self._inline_id=None; self._inline_obj=None

        scene=QGraphicsScene(self); self.setScene(scene)
        self.setBackgroundBrush(QBrush(QColor("#3d3d52")))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag); self.setMouseTracking(True)

        self._page_item=QGraphicsPixmapItem(); scene.addItem(self._page_item)
        self._overlay=SelectionOverlay(); scene.addItem(self._overlay)

        # Async render support
        self._render_id=0; self._render_pending=False
        self._rtimer=QTimer(); self._rtimer.setSingleShot(True)
        self._rtimer.timeout.connect(self._start_render)
        _render_signals.done.connect(self._on_render_done)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)

    # ── Document setup ────────────────────────────────────────────────────────

    def set_document(self,doc,page_idx=0):
        self._doc=doc; self._page_idx=page_idx; self._sel_id=None
        self._cancel_inline(); self._overlay.update_for(None,self._dpi)
        self._start_render(); self.objectSelected.emit(None)

    def set_page(self,idx):
        self._page_idx=idx; self._sel_id=None
        self._cancel_inline(); self._overlay.update_for(None,self._dpi)
        self._start_render(); self.objectSelected.emit(None)

    def schedule_render(self,ms=120):
        self._rtimer.start(ms)

    # ── Async rendering ───────────────────────────────────────────────────────

    def _start_render(self):
        if not self._doc or not self._doc.pages: return
        self._render_id+=1; rid=self._render_id
        pg_idx=self._page_idx; dpi=int(self._dpi)
        # Snapshot references (not deep copy for perf)
        doc=self._doc

        def task():
            try:
                from edof.engine.renderer import render_page
                pg=doc.pages[pg_idx]
                img=render_page(pg,doc.resources,doc.variables,dpi=dpi).convert("RGB")
                buf=_io.BytesIO(); img.save(buf,"PNG"); buf.seek(0)
                _render_signals.done.emit(buf.read(), rid)
            except Exception as e: print(f"[render] {e}")

        threading.Thread(target=task,daemon=True).start()

    def _on_render_done(self, data: bytes, rid: int):
        if rid != self._render_id: return   # stale render, discard
        px=QPixmap(); px.loadFromData(data)
        self._page_item.setPixmap(px); self._page_item.setPos(0,0)
        self.scene().setSceneRect(QRectF(0,0,px.width(),px.height()))
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
        self._overlay.update_for(self._sel_obj(),self._dpi)

    # ── Coordinates ───────────────────────────────────────────────────────────

    def _sp(self,event): return self.mapToScene(event.position().toPoint())
    def _to_mm(self,sp): return px_to_mm(sp.x(),self._dpi),px_to_mm(sp.y(),self._dpi)

    # ── Inline text editor (viewport overlay – reliable event handling) ────────

    def _start_inline(self, obj):
        self._cancel_inline()
        t    = obj.transform
        dpi  = self._dpi; zoom = self._zoom

        # Viewport position of the object's top-left corner
        scene_tl = QPointF(mm_to_px(t.x, dpi), mm_to_px(t.y, dpi))
        vp_tl    = self.mapFromScene(scene_tl)

        # Width/height in viewport pixels
        w_vp = int(max(60, mm_to_px(t.width,  dpi) * zoom))
        h_vp = int(max(24, mm_to_px(t.height, dpi) * zoom))

        # Create QPlainTextEdit as direct child of the viewport
        ed = QPlainTextEdit(self.viewport())
        ed.setPlainText(obj.text)
        ed.setGeometry(vp_tl.x(), vp_tl.y(), w_vp, h_vp)

        # WYSIWYG font size: match what is rendered on canvas.
        # Rendered text height on screen = font_pt * RDPI/72 * zoom  (viewport px)
        # Widget font pt = rendered_px * 72 / logical_dpi
        try:
            from PyQt6.QtWidgets import QApplication as _QApp
            ldpi = (_QApp.primaryScreen().logicalDotsPerInch()
                    if _QApp.primaryScreen() else 96.0)
        except Exception:
            ldpi = 96.0
        fs_widget = max(6.0, obj.style.font_size * RDPI * zoom / ldpi)
        ed.setFont(QFont(obj.style.font_family, int(fs_widget)))
        ed.setStyleSheet(
            f"background:rgba(255,255,220,230);color:#000000;"
            f"border:2px solid {ACC};padding:2px;border-radius:0px")
        ed.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ed.show(); ed.setFocus()
        # Position cursor at end
        cur=ed.textCursor(); cur.movePosition(cur.MoveOperation.End); ed.setTextCursor(cur)

        self._inline_widget = ed
        self._inline_id     = obj.id
        self._inline_obj    = obj

        # NOTE: do NOT use selectAll() – it causes the first click to deselect
        # Live update while typing
        def on_change():
            obj.text = ed.toPlainText()
            self.schedule_render(300)
            self.objectChanged.emit()
        ed.textChanged.connect(on_change)

        # Escape / Ctrl+Enter
        def key_handler(event, _orig=ed.keyPressEvent):
            if event.key()==Qt.Key.Key_Escape: self._cancel_inline(); return
            if (event.key()==Qt.Key.Key_Return and
                    event.modifiers()&Qt.KeyboardModifier.ControlModifier):
                self._confirm_inline(); return
            _orig(event)
        ed.keyPressEvent = key_handler

        # Confirm on focus loss
        def focus_out(event, _orig=ed.focusOutEvent):
            _orig(event); QTimer.singleShot(100, self._confirm_inline)
        ed.focusOutEvent = focus_out

    def _reposition_inline(self):
        if not self._inline_widget or not self._inline_obj: return
        t   = self._inline_obj.transform
        dpi = self._dpi; zoom = self._zoom
        scene_tl=QPointF(mm_to_px(t.x,dpi),mm_to_px(t.y,dpi))
        vp_tl=self.mapFromScene(scene_tl)
        w_vp=int(max(60,mm_to_px(t.width,dpi)*zoom))
        h_vp=int(max(24,mm_to_px(t.height,dpi)*zoom))
        self._inline_widget.setGeometry(vp_tl.x(),vp_tl.y(),w_vp,h_vp)

    def _confirm_inline(self):
        if not self._inline_widget or not self._inline_id: return
        pg=self._cur_page(); obj=pg.get_object(self._inline_id) if pg else None
        if obj: obj.text=self._inline_widget.toPlainText()
        self._cancel_inline()
        self.objectChanged.emit(); self.schedule_render()

    def _cancel_inline(self):
        if self._inline_widget:
            self._inline_widget.hide()
            try: self._inline_widget.deleteLater()
            except Exception: pass
            self._inline_widget=None; self._inline_id=None; self._inline_obj=None

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self,event):
        btn=event.button()
        if btn==Qt.MouseButton.MiddleButton:
            self._pan_start=event.pos()
            self._pan_scroll0=(self.horizontalScrollBar().value(),
                               self.verticalScrollBar().value())
            self.viewport().setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept(); return

        if btn==Qt.MouseButton.LeftButton:
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
                if obj and not obj.locked:
                    mode='rotate' if handle=='ROT' else f'resize_{handle}'
                    if handle in ('P1','P2'): mode=f'line_{handle}'
                    self._drag_mode=mode; self._drag_sp0=sp
                    self._drag_tf0=copy.copy(obj.transform)
                    self._drag_anchor=(self._compute_anchor(obj.transform,handle)
                                       if handle not in ('ROT','P1','P2') else None)
                return
            hit=self._hit_obj(sp)
            if hit!=self._sel_id:
                self._sel_id=hit; self._refresh_overlay()
                self.objectSelected.emit(self._sel_obj())
            if hit:
                obj=self._sel_obj()
                if obj and not obj.locked:
                    self._drag_mode='move'; self._drag_sp0=sp
                    self._drag_tf0=copy.copy(obj.transform)
            else: self._drag_mode=None
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._pan_start is not None:
            d=event.pos()-self._pan_start
            self.horizontalScrollBar().setValue(self._pan_scroll0[0]-d.x())
            self.verticalScrollBar().setValue(self._pan_scroll0[1]-d.y())
            event.accept(); return
        sp=self._sp(event)
        if self._drag_mode and self._drag_sp0:
            mods=event.modifiers()
            shift=bool(mods&Qt.KeyboardModifier.ShiftModifier)
            alt  =bool(mods&Qt.KeyboardModifier.AltModifier)
            self._apply_drag(sp,shift,alt)
        else: self._update_cursor(sp)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:
            self._pan_start=None; self._pan_scroll0=None
            self.viewport().setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept(); return
        if self._drag_mode:
            if self._preview_item:
                self.scene().removeItem(self._preview_item); self._preview_item=None
            self._start_render()
            if self._drag_mode: self.objectChanged.emit()
        self._drag_mode=None; self._drag_sp0=None; self._drag_tf0=None; self._drag_anchor=None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and not self._inline_widget:
            sp=self._sp(event); hit=self._hit_obj(sp)
            if hit:
                self._sel_id=hit; obj=self._sel_obj()
                if   isinstance(obj, edof.TextBox):  self._start_inline(obj)
                elif isinstance(obj, edof.QRCode):   self._edit_qr_inline(obj)
                elif isinstance(obj, edof.ImageBox): self._edit_image_inline(obj)
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
        f=1.15 if event.angleDelta().y()>0 else 1/1.15
        self._set_zoom(self._zoom*f); event.accept()

    def keyPressEvent(self,event):
        obj=self._sel_obj()
        if not obj or obj.locked: super().keyPressEvent(event); return
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

    def _apply_drag(self,sp,shift,alt):
        obj=self._sel_obj();
        if not obj: return
        tf=self._drag_tf0

        if self._drag_mode=='move':
            dx=px_to_mm(sp.x()-self._drag_sp0.x(),self._dpi)
            dy=px_to_mm(sp.y()-self._drag_sp0.y(),self._dpi)
            obj.transform.x=tf.x+dx; obj.transform.y=tf.y+dy

        elif self._drag_mode=='rotate':
            cx_s=mm_to_px(tf.x+tf.width/2,self._dpi)
            cy_s=mm_to_px(tf.y+tf.height/2,self._dpi)
            angle=math.degrees(math.atan2(sp.y()-cy_s,sp.x()-cx_s))+90
            if shift and not alt:
                angle=round(angle/15)*15   # snap 15° on Shift
            # Alt or no modifier = free rotation (no snap)
            obj.transform.rotation=angle%360

        elif self._drag_mode.startswith('line_'):
            ptk=self._drag_mode.split('_')[1]; mx,my=self._to_mm(sp)
            idx=0 if ptk=='P1' else 1
            pts=list(obj.points); pts[idx]=[mx,my]; obj.points=pts
            x1,y1=pts[0]; x2,y2=pts[1]
            obj.transform.x=min(x1,x2); obj.transform.y=min(y1,y2)
            obj.transform.width=max(abs(x2-x1),MIN_MM); obj.transform.height=max(abs(y2-y1),MIN_MM)

        else:
            handle=self._drag_mode.replace('resize_','')
            sw,sh=SelectionOverlay._SIGN.get(handle,(1,1))
            cos_r=math.cos(math.radians(tf.rotation)); sin_r=math.sin(math.radians(tf.rotation))
            ax,ay=self._drag_anchor; mx,my=self._to_mm(sp)
            vx,vy=mx-ax,my-ay
            new_w=max(MIN_MM,sw*(vx*cos_r+vy*sin_r))    if sw else tf.width
            new_h=max(MIN_MM,sh*(vx*(-sin_r)+vy*cos_r)) if sh else tf.height
            new_cx=ax+sw*new_w/2*cos_r+sh*new_h/2*(-sin_r)
            new_cy=ay+sw*new_w/2*sin_r+sh*new_h/2*cos_r
            obj.transform.x=new_cx-new_w/2; obj.transform.y=new_cy-new_h/2
            obj.transform.width=new_w; obj.transform.height=new_h

        self._refresh_overlay(); self._show_preview(obj)

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

    def _update_cursor(self,sp):
        handle=self._overlay.hit_handle(sp)
        if handle: self.viewport().setCursor(QCursor(self._overlay.cursor_for(handle)))
        elif self._hit_obj(sp):
            obj=self._sel_obj()
            cur=(Qt.CursorShape.ForbiddenCursor if (obj and obj.locked)
                 else Qt.CursorShape.SizeAllCursor)
            self.viewport().setCursor(QCursor(cur))
        else: self.viewport().setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    # ── Hit test ──────────────────────────────────────────────────────────────

    def _hit_obj(self,sp):
        if not self._doc or not self._doc.pages: return None
        pg=self._doc.pages[self._page_idx]; mx,my=self._to_mm(sp)
        for obj in reversed(pg.sorted_objects()):
            t=obj.transform; cx,cy=t.x+t.width/2,t.y+t.height/2
            lx,ly=rotate_point(mx,my,cx,cy,-t.rotation)
            if t.x<=lx<=t.x+t.width and t.y<=ly<=t.y+t.height: return obj.id
        return None

    # ── Context menu ──────────────────────────────────────────────────────────

    def _ctx_menu(self,vpos):
        sp=self.mapToScene(vpos); hit=self._hit_obj(sp)
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
        menu.exec(self.viewport().mapToGlobal(vpos))

    def _toggle_lock(self):
        obj=self._sel_obj()
        if obj: obj.locked=not obj.locked; self.objectChanged.emit(); self.schedule_render()

    def _toggle_visible(self):
        obj=self._sel_obj()
        if obj: obj.visible=not obj.visible; self.objectChanged.emit(); self._start_render()

    def _do_delete(self):
        pg=self._cur_page()
        if pg and self._sel_id:
            pg.remove_object(self._sel_id); self._sel_id=None
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

        self.schedule_render(); self.objectChanged.emit()

    # ── Zoom / Fit ────────────────────────────────────────────────────────────

    def _set_zoom(self,z):
        self._zoom=max(0.05,min(8.0,z))
        self.setTransform(QTransform().scale(self._zoom,self._zoom))
        self._refresh_overlay(); self._reposition_inline()

    def zoom_fit(self):
        if not self._doc or not self._doc.pages: return
        pg=self._doc.pages[self._page_idx]
        pw=mm_to_px(pg.width,self._dpi); ph=mm_to_px(pg.height,self._dpi)
        vw=max(100,self.viewport().width()); vh=max(100,self.viewport().height())
        self._set_zoom(min(vw/pw,vh/ph)*0.95); self.centerOn(pw/2,ph/2)

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

    def get_sel_id(self): return self._sel_id
    def set_sel_id(self,oid):
        self._sel_id=oid; self._refresh_overlay()
        self.objectSelected.emit(self._sel_obj())


# ═══════════════════════════════════════════════════════════════════════════════
#  Object List Panel
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_ICONS={'textbox':'T','imagebox':'🖼','shape':'⬜','qrcode':'⬛','group':'⊞','base':'?'}

class ObjectListPanel(QWidget):
    objectSelected=pyqtSignal(str)   # object id

    def __init__(self,canvas,parent=None):
        super().__init__(parent); self._canvas=canvas
        vb=QVBoxLayout(self); vb.setContentsMargins(4,4,4,4); vb.setSpacing(4)
        self._list=QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentItemChanged.connect(self._on_item_changed)
        vb.addWidget(self._list)

    def refresh(self):
        self._list.blockSignals(True); self._list.clear()
        pg=self._canvas._cur_page()
        if not pg: self._list.blockSignals(False); return
        sel=self._canvas.get_sel_id()
        for obj in reversed(pg.sorted_objects()):
            icon=_TYPE_ICONS.get(obj.OBJECT_TYPE,'?')
            name=obj.name or obj.id[:12]+'…'
            var= f"  [{obj.variable}]" if obj.variable else ""
            vis= "" if obj.visible else " 🚫"
            lck= " 🔒" if obj.locked else ""
            item=QListWidgetItem(f"{icon} {name}{var}{vis}{lck}")
            item.setData(Qt.ItemDataRole.UserRole,obj.id)
            self._list.addItem(item)
            if obj.id==sel: self._list.setCurrentItem(item)
        self._list.blockSignals(False)

    def _on_item_changed(self,item):
        if item:
            oid=item.data(Qt.ItemDataRole.UserRole)
            if oid: self.objectSelected.emit(oid)

    def select(self,obj_id):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole)==obj_id:
                self._list.setCurrentRow(i); break
        self._list.blockSignals(False)


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

    def _dspin(self,lo=-99999,hi=99999,dec=2,step=0.5,suffix=""):
        s=QDoubleSpinBox(); s.setRange(lo,hi); s.setDecimals(dec); s.setSingleStep(step)
        if suffix: s.setSuffix(suffix)
        return s

    def _setup(self):
        from PyQt6.QtWidgets import QGroupBox
        vb=QVBoxLayout(self); vb.setContentsMargins(4,4,4,4); vb.setSpacing(4)

        # Transform
        g_tf=QGroupBox(t('tab_transform')); fl=QFormLayout(g_tf); fl.setSpacing(4); fl.setContentsMargins(8,8,8,6)
        self.sp_x=self._dspin(); self.sp_y=self._dspin()
        self.sp_w=self._dspin(lo=0.1); self.sp_h=self._dspin(lo=0.1)
        self.sp_rot=self._dspin(lo=0,hi=360,step=1,dec=1)
        self.sp_opa=self._dspin(lo=0,hi=100,dec=0,step=5,suffix="%")
        self.sp_lay=QSpinBox(); self.sp_lay.setRange(0,9999)
        for lbl,sp,key in [(t('prop_x'),self.sp_x,'x'),(t('prop_y'),self.sp_y,'y'),
                           (t('prop_w'),self.sp_w,'width'),(t('prop_h'),self.sp_h,'height'),
                           (t('prop_rot'),self.sp_rot,'rotation')]:
            sp.editingFinished.connect(lambda k=key,s=sp: self._atf(k,s.value())); fl.addRow(lbl,sp)
        self.sp_opa.editingFinished.connect(lambda:self._aa('opacity',self.sp_opa.value()/100.0))
        self.sp_lay.editingFinished.connect(lambda:self._aa('layer',self.sp_lay.value()))
        fl.addRow(t('prop_opacity'),self.sp_opa); fl.addRow(t('prop_layer'),self.sp_lay)
        # Scale + Flip
        rs=QWidget(); hbs=QHBoxLayout(rs); hbs.setContentsMargins(0,0,0,0)
        self.sp_scale=self._dspin(lo=0.01,hi=100,dec=2); self.sp_scale.setValue(1.5)
        bs=QPushButton(t('btn_scale')); bs.clicked.connect(self._apply_scale)
        hbs.addWidget(self.sp_scale); hbs.addWidget(bs); fl.addRow("",rs)
        rf=QWidget(); hbf=QHBoxLayout(rf); hbf.setContentsMargins(0,0,0,0)
        bfh=QPushButton(t('btn_flip_h')); bfv=QPushButton(t('btn_flip_v'))
        bfh.clicked.connect(lambda:self._flip('h')); bfv.clicked.connect(lambda:self._flip('v'))
        hbf.addWidget(bfh); hbf.addWidget(bfv); fl.addRow("",rf)
        # Layer buttons
        rl=QWidget(); hbl=QHBoxLayout(rl); hbl.setContentsMargins(0,0,0,0)
        for lbl,op in [("▲▲",'front'),("▲",'up'),("▼",'down'),("▼▼",'back')]:
            b=QPushButton(lbl); b.setFixedWidth(32)
            b.clicked.connect(lambda _,o=op:self._canvas._layer_op(o))
            hbl.addWidget(b)
        hbl.addStretch(); fl.addRow("Layers",rl)
        vb.addWidget(g_tf)

        # Type-specific
        self._stack=QStackedWidget(); vb.addWidget(self._stack,1)
        self._stack.addWidget(self._mk_empty())   # 0
        self._stack.addWidget(self._mk_tb())       # 1 TextBox
        self._stack.addWidget(self._mk_img())      # 2 ImageBox
        self._stack.addWidget(self._mk_shape())    # 3 Shape
        self._stack.addWidget(self._mk_qr())       # 4 QRCode
        self._stack.addWidget(self._mk_line())     # 5 Line

        # Object meta
        g_o=QGroupBox(t('tab_object')); fo=QFormLayout(g_o); fo.setSpacing(4); fo.setContentsMargins(8,8,8,6)
        self.le_name=QLineEdit(); self.le_name.setPlaceholderText("Editor label")
        self.le_name.editingFinished.connect(lambda:self._aa('name',self.le_name.text()))
        fo.addRow(t('prop_name'),self.le_name)
        self.le_var=QLineEdit(); self.le_var.setPlaceholderText("variable_name")
        bv=QPushButton(t('btn_bind')); bv.setFixedWidth(44); bv.clicked.connect(self._bind_var)
        rv=QWidget(); hbv=QHBoxLayout(rv); hbv.setContentsMargins(0,0,0,0)
        hbv.addWidget(self.le_var); hbv.addWidget(bv); fo.addRow(t('prop_variable'),rv)
        fo.addRow("",QLabel(f"<small style='color:{FGD}'>{t('var_hint')}</small>"))
        self.le_tags=QLineEdit(); self.le_tags.setPlaceholderText("tag1, tag2")
        self.le_tags.editingFinished.connect(self._apply_tags)
        fo.addRow(t('prop_tags'),self.le_tags)
        self.cb_locked=QCheckBox(t('prop_locked'))
        self.cb_editable=QCheckBox(t('prop_editable'))
        self.cb_visible=QCheckBox(t('prop_visible'))
        self.cb_locked.toggled.connect(lambda v:self._aa('locked',v))
        self.cb_editable.toggled.connect(lambda v:self._aa('editable',v))
        self.cb_visible.toggled.connect(lambda v:self._aa('visible',v))
        fo.addRow("",self.cb_locked); fo.addRow("",self.cb_editable); fo.addRow("",self.cb_visible)
        self.lbl_info=QLabel(); self.lbl_info.setStyleSheet(f"color:{FGD};font-size:8pt")
        self.lbl_info.setWordWrap(True); fo.addRow("",self.lbl_info)
        vb.addWidget(g_o)

    # ── Type-specific panels ──────────────────────────────────────────────────

    def _mk_empty(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(QLabel(t('no_selection'))); l.addStretch(); return w

    def _mk_tb(self):
        from PyQt6.QtWidgets import QGroupBox
        w=QWidget(); vb=QVBoxLayout(w); vb.setContentsMargins(6,4,6,4); vb.setSpacing(5)
        g1=QGroupBox("Content"); fl1=QFormLayout(g1); fl1.setContentsMargins(8,8,8,6)
        self.te_text=QTextEdit(); self.te_text.setFixedHeight(80)
        self.te_text.textChanged.connect(lambda:self._lt.start())
        fl1.addRow(self.te_text); vb.addWidget(g1)

        g2=QGroupBox(t('tab_style')); fl2=QFormLayout(g2); fl2.setSpacing(4); fl2.setContentsMargins(8,8,8,6)
        self.cb_font=QComboBox(); self.cb_font.setEditable(True)
        self.cb_font.currentTextChanged.connect(lambda v:self._as('font_family',v,str))
        fl2.addRow(t('prop_font'),self.cb_font)
        self.sp_fsize=self._dspin(lo=1,hi=500,dec=1)
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
        self.sp_minfs=self._dspin(lo=1,hi=200,dec=1)
        self.sp_minfs.editingFinished.connect(lambda:self._as('min_font_size',self.sp_minfs.value(),float))
        rm=QWidget(); hm=QHBoxLayout(rm); hm.setContentsMargins(0,0,0,0)
        hm.addWidget(QLabel(t('prop_min_size'))); hm.addWidget(self.sp_minfs)
        fb.addWidget(rm); vb.addWidget(g3)
        btn_uf=QPushButton(t('btn_upload_font')); btn_uf.clicked.connect(self._upload_font)
        vb.addWidget(btn_uf); vb.addStretch(); return w

    def _mk_img(self):
        w=QWidget(); fl=QFormLayout(w); fl.setContentsMargins(8,8,8,6)
        self.cb_fit=QComboBox(); self.cb_fit.addItems(["contain","cover","fill","stretch","none"])
        self.cb_fit.currentTextChanged.connect(lambda v:self._aa('fit_mode',v))
        fl.addRow(t('prop_fit_mode'),self.cb_fit)
        fl.addRow("",QLabel("<small style='color:#7070a0'>Variable = file path or URL for dynamic image</small>"))
        btn_rep=QPushButton(t('btn_replace')); btn_rep.clicked.connect(self._replace_image)
        fl.addRow("",btn_rep); return w

    def _mk_shape(self):
        w=QWidget(); fl=QFormLayout(w); fl.setContentsMargins(8,8,8,6); fl.setSpacing(5)
        rf=QWidget(); hf=QHBoxLayout(rf); hf.setContentsMargins(0,0,0,0)
        self.btn_fill=QPushButton(); self.btn_fill.setFixedSize(36,22)
        self.btn_fill.clicked.connect(self._pick_fill)
        self.lbl_fill_a=QLabel("100%"); self.lbl_fill_a.setFixedWidth(36)
        hf.addWidget(self.btn_fill); hf.addWidget(self.lbl_fill_a); hf.addStretch()
        fl.addRow(t('prop_fill'),rf)
        rs=QWidget(); hs=QHBoxLayout(rs); hs.setContentsMargins(0,0,0,0)
        self.btn_stroke=QPushButton(); self.btn_stroke.setFixedSize(36,22)
        self.btn_stroke.clicked.connect(self._pick_stroke)
        self.sp_sw=self._dspin(lo=0.1,hi=100,dec=1,step=0.5,suffix=" pt"); self.sp_sw.setFixedWidth(80)
        self.sp_sw.editingFinished.connect(self._apply_stroke_w)
        hs.addWidget(self.btn_stroke); hs.addWidget(self.sp_sw); hs.addStretch()
        fl.addRow(t('prop_stroke'),rs)
        self.sp_cr=self._dspin(lo=0,hi=200,dec=1,suffix=" mm")
        self.sp_cr.editingFinished.connect(lambda:self._aa_obj('corner_radius',self.sp_cr.value()))
        fl.addRow("Corner radius",self.sp_cr)
        return w

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
        fl.addRow(t('prop_qr_border'),self.sp_qr_brd); return w

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
        self.sp_lsw=self._dspin(lo=0.1,hi=100,dec=1,step=0.5,suffix=" pt"); self.sp_lsw.setFixedWidth(80)
        self.sp_lsw.editingFinished.connect(lambda:self._apply_line_sw())
        hl.addWidget(self.btn_lstroke); hl.addWidget(self.sp_lsw); hl.addStretch()
        fl.addRow(t('prop_stroke'),rl); return w

    # ── Load ─────────────────────────────────────────────────────────────────

    def load(self,obj):
        self._loading=True; self._obj=obj
        try:
            if obj is None: self._stack.setCurrentIndex(0); return
            t_=obj.transform
            self.sp_x.setValue(round(t_.x,3)); self.sp_y.setValue(round(t_.y,3))
            self.sp_w.setValue(round(t_.width,3)); self.sp_h.setValue(round(t_.height,3))
            self.sp_rot.setValue(round(t_.rotation,2))
            self.sp_opa.setValue(round(obj.opacity*100,0)); self.sp_lay.setValue(obj.layer)
            self.le_name.setText(obj.name or ""); self.le_var.setText(obj.variable or "")
            self.le_tags.setText(", ".join(obj.tags))
            self.cb_locked.setChecked(obj.locked)
            self.cb_editable.setChecked(getattr(obj,'editable',True))
            self.cb_visible.setChecked(obj.visible)
            self.lbl_info.setText(f"ID: {obj.id[:24]}…  Type: {obj.OBJECT_TYPE}")

            from edof.format.objects import Shape,SHAPE_LINE
            if isinstance(obj,edof.TextBox):       self._load_tb(obj); self._stack.setCurrentIndex(1)
            elif isinstance(obj,edof.ImageBox):    self._load_img(obj); self._stack.setCurrentIndex(2)
            elif isinstance(obj,Shape) and obj.shape_type==SHAPE_LINE:
                self._load_line(obj); self._stack.setCurrentIndex(5)
            elif isinstance(obj,Shape):            self._load_shape(obj); self._stack.setCurrentIndex(3)
            elif isinstance(obj,edof.QRCode):      self._load_qr(obj); self._stack.setCurrentIndex(4)
            else:                                  self._stack.setCurrentIndex(0)
        finally: self._loading=False

    def _load_tb(self,obj):
        s=obj.style
        self.te_text.blockSignals(True); self.te_text.setPlainText(obj.text); self.te_text.blockSignals(False)
        self.cb_font.blockSignals(True); self.cb_font.setCurrentText(s.font_family); self.cb_font.blockSignals(False)
        self.sp_fsize.setValue(round(s.font_size,1)); self.sp_minfs.setValue(round(s.min_font_size,1))
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
        self.btn_fill.setStyleSheet(_cswatch(obj.fill.color or (200,200,200,255)))
        c=obj.fill.color; a=int(c[3]/255*100) if c and len(c)==4 else 100
        self.lbl_fill_a.setText(f"{a}%")
        self.btn_stroke.setStyleSheet(_cswatch(obj.stroke.color or (0,0,0,255)))
        self.sp_sw.setValue(getattr(obj.stroke,'width',1)); self.sp_cr.setValue(getattr(obj,'corner_radius',0))

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

    def _as(self,key,val,typ):
        if self._loading or not isinstance(self._obj,edof.TextBox): return
        try: setattr(self._obj.style,key,typ(val))
        except Exception: return
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
        c=EdofColorDialog.get_color(self,(*self._obj.style.color[:3],255),alpha=False)
        if c:
            self._obj.style.color=c[:3]; self.btn_color.setStyleSheet(_cswatch(c))
            self._canvas.schedule_render(); self.changed.emit()

    def _pick_fill(self):
        if not hasattr(self._obj,'fill'): return
        c=EdofColorDialog.get_color(self,self._obj.fill.color or (200,200,200,255),alpha=True)
        if c:
            self._obj.fill.color=c; self.btn_fill.setStyleSheet(_cswatch(c))
            self.lbl_fill_a.setText(f"{int(c[3]/255*100)}%"); self._canvas.schedule_render(); self.changed.emit()

    def _pick_stroke(self):
        if not hasattr(self._obj,'stroke'): return
        c=EdofColorDialog.get_color(self,self._obj.stroke.color or (0,0,0,255),alpha=True)
        if c:
            self._obj.stroke.color=c; self.btn_stroke.setStyleSheet(_cswatch(c))
            self._canvas.schedule_render(); self.changed.emit()

    def _pick_line_stroke(self):
        if not hasattr(self._obj,'stroke'): return
        c=EdofColorDialog.get_color(self,self._obj.stroke.color or (0,0,0,255),alpha=True)
        if c:
            self._obj.stroke.color=c; self.btn_lstroke.setStyleSheet(_cswatch(c))
            self._canvas.schedule_render(); self.changed.emit()

    def _pick_qr_color(self,attr):
        if not isinstance(self._obj,edof.QRCode): return
        c=EdofColorDialog.get_color(self,getattr(self._obj,attr,(0,0,0,255)),alpha=True)
        if c:
            setattr(self._obj,attr,c)
            getattr(self,f'btn_qr_{attr}').setStyleSheet(_cswatch(c))
            getattr(self,f'lbl_qr_{attr}_a').setText(f"{int(c[3]/255*100)}%")
            self._canvas.schedule_render(); self.changed.emit()

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

    def set_font_list(self,fonts):
        self._loading=True; cur=self.cb_font.currentText()
        self.cb_font.clear(); self.cb_font.addItems(fonts); self.cb_font.setCurrentText(cur)
        self._loading=False


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════

class EdofEditor(QMainWindow):
    def __init__(self,filepath=None):
        super().__init__()
        self.doc=None; self.filepath=None
        self.history=CommandHistory(max_undo=60); self._modified=False
        self._build_ui(); self.setStyleSheet(QSS)
        self.setWindowTitle(t('app_title')); self.resize(1440,880)
        QTimer.singleShot(300,self._load_fonts)
        if filepath and os.path.isfile(filepath): self._open_file(filepath)
        else: self._new_doc()

    def _build_ui(self):
        self._canvas=EdofCanvas(self)
        self._canvas.objectSelected.connect(self._on_sel)
        self._canvas.objectChanged.connect(self._on_chg)
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
        ld.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        ld.setFixedWidth(175); self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,ld)

        # Right: properties (scrollable)
        self._props=PropPanel(self._canvas); self._props.changed.connect(self._on_chg)
        scroll=QScrollArea(); scroll.setWidget(self._props); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rd=QDockWidget(t('panel_properties'),self); rd.setWidget(scroll)
        rd.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        rd.setFixedWidth(310); self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,rd)

        self._lbl_zoom=QLabel("100%")
        self._status=QStatusBar(); self.setStatusBar(self._status)
        self._status.addPermanentWidget(self._lbl_zoom)
        self._build_toolbar(); self._build_menu()

    def _build_toolbar(self):
        tb=self.addToolBar("Main"); tb.setMovable(False); tb.setIconSize(QSize(14,14))
        def a(lbl,slot,key=None):
            ac=QAction(lbl,self); ac.triggered.connect(slot)
            if key: ac.setShortcut(QKeySequence(key))
            tb.addAction(ac)
        a("📄",self._new_doc,"Ctrl+N"); a("📂",self._open_dlg,"Ctrl+O"); a("💾",self._save,"Ctrl+S")
        tb.addSeparator()
        a("↩",self._undo,"Ctrl+Z"); a("↪",self._redo,"Ctrl+Y"); tb.addSeparator()
        a("T",self._ins_textbox); a("🖼",self._ins_image)
        a("⬜",lambda:self._ins_shape("rect")); a("⬭",lambda:self._ins_shape("ellipse"))
        a("╱",self._ins_line); a("⬛",self._ins_qr); tb.addSeparator()
        a("🔍+",lambda:self._zoom_step(1.25),"Ctrl+="); a("🔍-",lambda:self._zoom_step(1/1.25),"Ctrl+-")
        a("Fit",self._zoom_fit,"Ctrl+0"); tb.addSeparator()
        a("⧉",self._dup_obj,"Ctrl+D"); a("🗑",self._del_obj,"Delete"); tb.addSeparator()
        a("PNG",self._export_png); a("PDF",self._export_pdf)

    def _build_menu(self):
        mb=self.menuBar()
        def m(tk): return mb.addMenu(t(tk))
        def a(mn,tk,slot,key=None,sep=False):
            if sep: mn.addSeparator(); return
            ac=QAction(t(tk),self); ac.triggered.connect(slot)
            if key: ac.setShortcut(QKeySequence(key))
            mn.addAction(ac)
        fm=m('menu_file')
        a(fm,'new',self._new_doc,"Ctrl+N"); a(fm,'open',self._open_dlg,"Ctrl+O")
        a(fm,sep=True,tk="",slot=None)
        a(fm,'save',self._save,"Ctrl+S"); a(fm,'save_as',self._save_as,"Ctrl+Shift+S")
        a(fm,sep=True,tk="",slot=None)
        a(fm,'export_png',self._export_png); a(fm,'export_all',self._export_all)
        a(fm,'export_pdf',self._export_pdf); a(fm,sep=True,tk="",slot=None)
        a(fm,'print',self._print); a(fm,sep=True,tk="",slot=None); a(fm,'quit',self.close,"Ctrl+Q")
        em=m('menu_edit')
        a(em,'undo',self._undo,"Ctrl+Z"); a(em,'redo',self._redo,"Ctrl+Y")
        a(em,sep=True,tk="",slot=None); a(em,'duplicate',self._dup_obj,"Ctrl+D"); a(em,'delete',self._del_obj,"Delete")
        im=m('menu_insert')
        a(im,'text_box',self._ins_textbox); a(im,'image',self._ins_image)
        a(im,'rectangle',lambda:self._ins_shape("rect")); a(im,'ellipse',lambda:self._ins_shape("ellipse"))
        a(im,'line',self._ins_line); a(im,'qr_code',self._ins_qr)
        pm=m('menu_page')
        a(pm,'add_page',self._add_page); a(pm,'dup_page',self._dup_page)
        a(pm,'del_page',self._del_page); a(pm,sep=True,tk="",slot=None); a(pm,'page_settings',self._page_settings)
        dm=m('menu_document')
        a(dm,'variables',self._show_vars); a(dm,'doc_info',self._doc_info); a(dm,'validate',self._validate)
        vm=m('menu_view')
        a(vm,'zoom_in',lambda:self._zoom_step(1.25),"Ctrl+=")
        a(vm,'zoom_out',lambda:self._zoom_step(1/1.25),"Ctrl+-")
        a(vm,'fit_page',self._zoom_fit,"Ctrl+0")

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_sel(self,obj):
        self._props.load(obj)
        self._obj_panel.refresh()
        if obj: self._obj_panel.select(obj.id)

    def _on_chg(self):
        self._modified=True; self._upd_title()
        self._obj_panel.refresh()

    def _on_pg_sel(self,idx):
        if self.doc and 0<=idx<len(self.doc.pages): self._canvas.set_page(idx)

    def _on_obj_select(self,oid):
        self._canvas.set_sel_id(oid)

    # ── Document ──────────────────────────────────────────────────────────────
    def _new_doc(self):
        if not self._confirm(): return
        self.doc=edof.new(width=A4W,height=A4H,title="Untitled"); self.filepath=None; self._modified=False
        self.doc.add_page(); self.history.clear(); self.history.push(self.doc,"New")
        self._canvas.set_document(self.doc,0); self._refresh_pages(); self._upd_title()

    def _open_dlg(self):
        p,_=QFileDialog.getOpenFileName(self,t('open'),"","EDOF (*.edof);;All (*.*)")
        if p: self._open_file(p)

    def _open_file(self,path):
        try:
            self.doc=edof.load(path); self.filepath=path; self._modified=False
            self.history.clear(); self.history.push(self.doc,"Opened")
            self._canvas.set_document(self.doc,0); self._refresh_pages(); self._upd_title()
            if self.doc.errors: QMessageBox.warning(self,"Notice","\n".join(self.doc.errors))
            self._status.showMessage(t('status_opened',name=os.path.basename(path)))
        except Exception as e: QMessageBox.critical(self,"Error",str(e))

    def _save(self):
        if not self.doc: return
        if self.filepath:
            try:
                self.doc.save(self.filepath); self._modified=False; self._upd_title()
                self._status.showMessage(t('status_saved',name=os.path.basename(self.filepath)))
            except Exception as e: QMessageBox.critical(self,"Error",str(e))
        else: self._save_as()

    def _save_as(self):
        if not self.doc: return
        p,_=QFileDialog.getSaveFileName(self,t('save_as'),"","EDOF (*.edof)")
        if p: self.filepath=p; self._save()

    def _confirm(self):
        if self._modified:
            r=QMessageBox.question(self,t('dlg_unsaved'),t('dlg_discard'),
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
            return r==QMessageBox.StandardButton.Yes
        return True

    def _upd_title(self):
        ti=(self.doc.title or "Untitled") if self.doc else "—"
        f=os.path.basename(self.filepath) if self.filepath else "Unsaved"
        self.setWindowTitle(f"{t('app_title')} — {ti} [{f}]{'•' if self._modified else ''}")

    def _push(self,d):
        if self.doc: self.history.push(self.doc,d); self._modified=True; self._upd_title()

    def _undo(self):
        if not self.doc: return
        r=self.history.undo(self.doc)
        if r:
            self.doc=r; self._canvas.set_document(self.doc,min(self._cpi(),len(self.doc.pages)-1))
            self._refresh_pages()

    def _redo(self):
        if not self.doc: return
        r=self.history.redo(self.doc)
        if r:
            self.doc=r; self._canvas.set_document(self.doc,min(self._cpi(),len(self.doc.pages)-1))
            self._refresh_pages()

    # ── Insert ────────────────────────────────────────────────────────────────
    def _cp(self):
        if not self.doc or not self.doc.pages: return None
        i=self._cpi(); return self.doc.pages[i] if i<len(self.doc.pages) else None
    def _cpi(self): return max(0,self._pg_list.currentRow())

    def _ins_textbox(self):
        pg=self._cp()
        if not pg: return
        tb=pg.add_textbox(20,20,100,25,"Text"); tb.style.font_size=18
        self._canvas.set_sel_id(tb.id); self._canvas.schedule_render(); self._push("Add TextBox")

    def _ins_image(self):
        pg=self._cp()
        if not pg: return
        p,_=QFileDialog.getOpenFileName(self,t('image'),"","Images (*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp);;All (*.*)")
        if not p: return
        try:
            rid=self.doc.add_resource_from_file(p); ib=pg.add_image(rid,10,10,80,80)
            self._canvas.set_sel_id(ib.id); self._canvas.schedule_render(); self._push("Add Image")
        except Exception as e: QMessageBox.critical(self,"Error",str(e))

    def _ins_shape(self,stype):
        pg=self._cp()
        if not pg: return
        sh=pg.add_shape(stype,30,30,70,45); sh.fill.color=(100,149,237,255); sh.stroke.color=(50,80,180,255)
        self._canvas.set_sel_id(sh.id); self._canvas.schedule_render(); self._push(f"Add {stype}")

    def _ins_line(self):
        pg=self._cp()
        if not pg: return
        sh=pg.add_shape("line",0,0,1,1); sh.stroke.color=(40,40,40,255); sh.stroke.width=2; sh.fill.color=None
        sh.points=[[20.0,60.0],[100.0,100.0]]
        sh.transform.x=20; sh.transform.y=60; sh.transform.width=80; sh.transform.height=40
        self._canvas.set_sel_id(sh.id); self._canvas.schedule_render(); self._push("Add Line")

    def _ins_qr(self):
        pg=self._cp()
        if not pg: return
        data,ok=QInputDialog.getText(self,t('dlg_qr_title'),t('dlg_qr_prompt'))
        if not ok or not data: return
        qr=pg.add_qrcode(data,30,30,50); self._canvas.set_sel_id(qr.id)
        self._canvas.schedule_render(); self._push("Add QR")

    def _dup_obj(self):
        pg=self._cp(); sid=self._canvas.get_sel_id()
        if not pg or not sid: return
        obj=pg.get_object(sid)
        if not obj: return
        new=obj.copy(); new.transform.translate(8,8); pg.add_object(new)
        self._canvas.set_sel_id(new.id); self._canvas.schedule_render(); self._push("Duplicate")

    def _del_obj(self): self._canvas._do_delete(); self._push("Delete")

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
        self._pg_list.blockSignals(True); cur=self._pg_list.currentRow(); self._pg_list.clear()
        if self.doc:
            for i,p in enumerate(self.doc.pages):
                self._pg_list.addItem(f"  Page {i+1}  {int(p.width)}×{int(p.height)}")
        n=self._pg_list.count()
        if n>0: self._pg_list.setCurrentRow(max(0,min(cur,n-1)))
        self._pg_list.blockSignals(False)
        self._obj_panel.refresh()

    # ── Zoom ──────────────────────────────────────────────────────────────────
    def _zoom_step(self,f):
        self._canvas.zoom=self._canvas.zoom*f; self._lbl_zoom.setText(f"{int(self._canvas.zoom*100)}%")
    def _zoom_fit(self):
        self._canvas.zoom_fit(); self._lbl_zoom.setText(f"{int(self._canvas.zoom*100)}%")

    # ── Export / Print ────────────────────────────────────────────────────────
    def _export_png(self):
        if not self.doc or not self.doc.pages: return
        p,_=QFileDialog.getSaveFileName(self,t('export_png'),"","PNG (*.png);;JPEG (*.jpg);;TIFF (*.tiff)")
        if not p: return
        try:
            fmt=os.path.splitext(p)[1].upper().lstrip(".")
            self.doc.export_bitmap(p,page=self._cpi(),dpi=300,format=fmt or "PNG")
            self._status.showMessage(t('status_saved',name=os.path.basename(p)))
        except Exception as e: QMessageBox.critical(self,"Error",str(e))

    def _export_all(self):
        if not self.doc: return
        d=QFileDialog.getExistingDirectory(self,t('export_all'))
        if not d: return
        try:
            from edof.export.bitmap import export_all_pages
            ps=export_all_pages(self.doc,os.path.join(d,"page_{page}.png"),dpi=300)
            QMessageBox.information(self,"Done",f"Exported {len(ps)} page(s)")
        except Exception as e: QMessageBox.critical(self,"Error",str(e))

    def _export_pdf(self):
        if not self.doc: return
        p,_=QFileDialog.getSaveFileName(self,t('export_pdf'),"","PDF (*.pdf)")
        if not p: return
        try: self.doc.export_pdf(p)
        except Exception as e: QMessageBox.critical(self,"PDF Error",f"pip install edof[pdf]\n\n{e}")

    def _print(self):
        if not self.doc or not self.doc.pages: return
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
        fl=QFormLayout(dlg); fl.setContentsMargins(16,16,16,16)
        sw=QDoubleSpinBox(); sw.setRange(1,9999); sw.setValue(pg.width)
        sh=QDoubleSpinBox(); sh.setRange(1,9999); sh.setValue(pg.height)
        sd=QSpinBox(); sd.setRange(72,1200); sd.setValue(pg.dpi)
        cs=QComboBox(); cs.addItems(["RGB","RGBA","L","1","CMYK"]); cs.setCurrentText(pg.color_space)
        bd=QComboBox(); bd.addItems(["8","16"]); bd.setCurrentText(str(pg.bit_depth))
        fl.addRow(t('lbl_width'),sw); fl.addRow(t('lbl_height'),sh); fl.addRow(t('lbl_dpi'),sd)
        fl.addRow(t('prop_color_space'),cs); fl.addRow(t('lbl_bit_depth'),bd)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); fl.addRow(bb)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            pg.width=sw.value(); pg.height=sh.value(); pg.dpi=sd.value()
            pg.color_space=cs.currentText(); pg.bit_depth=int(bd.currentText())
            self._refresh_pages(); self._canvas.schedule_render()

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
        fl.addRow(t('lbl_default_cs'),cs); fl.addRow(t('lbl_bit_depth'),bd)
        info=QLabel(f"Created: {self.doc.created[:19]}\nModified: {self.doc.modified[:19]}\n"
                    f"ID: {self.doc.id[:24]}…\nPages: {len(self.doc.pages)}  v{edof.FORMAT_VERSION_STR}")
        info.setStyleSheet(f"color:{FGD};font-family:Consolas;font-size:8pt"); fl.addRow(info)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        def apply():
            self.doc.title=lt.text(); self.doc.author=la.text(); self.doc.description=ld.text()
            self.doc.default_color_space=cs.currentText(); self.doc.default_bit_depth=int(bd.currentText())
            self._upd_title(); dlg.accept()
        bb.accepted.connect(apply); bb.rejected.connect(dlg.reject); fl.addRow(bb); dlg.exec()

    def _validate(self):
        if not self.doc: return
        issues=self.doc.validate()
        if issues: QMessageBox.warning(self,t('dlg_validate'),"\n".join(f"• {i}" for i in issues))
        else: QMessageBox.information(self,t('dlg_validate'),"✓ Document is valid.")

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


def main():
    # Remove Qt image allocation limit (default 256 MB blocks large print jobs)
    try:
        from PyQt6.QtGui import QImageReader
        QImageReader.setAllocationLimit(0)   # 0 = unlimited
    except Exception:
        pass
    app=QApplication(sys.argv); app.setApplicationName("EDOF Editor")
    app.setApplicationVersion(edof.__version__)
    win=EdofEditor(sys.argv[1] if len(sys.argv)>1 else None)
    win.show(); sys.exit(app.exec())

if __name__=="__main__": main()
