# edof/gui/tkinter_canvas.py
"""
EdofTkCanvas – Tkinter canvas widget for EDOF document editing.

Features:
  • Page preview (Pillow → PhotoImage)
  • Click to select objects
  • Drag to MOVE selected object
  • 8 resize handles (corners + edges) – drag to RESIZE
  • Rotation handle (above top-center) – drag to ROTATE
  • Double-click TextBox → inline text editor overlay
  • Middle-mouse pan (relative, no jump)
  • Mouse-wheel zoom
  • Arrow-key nudge (0.5 mm)
  • Delete key removes selected object
  • on_select / on_change callbacks
"""
from __future__ import annotations
import math
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Tuple, TYPE_CHECKING

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

if TYPE_CHECKING:
    from edof.format.document import Document, Page
    from edof.format.objects  import EdofObject

# ── Handle geometry ───────────────────────────────────────────────────────────
# (rx, ry) = fraction of (width, height); values outside [0,1] = special
_HANDLES = {            # key  : (rx,  ry)
    'TL': (0,    0   ), 'TC': (0.5, 0   ), 'TR': (1,    0   ),
    'ML': (0,    0.5 ),                     'MR': (1,    0.5 ),
    'BL': (0,    1   ), 'BC': (0.5, 1   ), 'BR': (1,    1   ),
}
_ROT_OFFSET_PX = 30    # rotation handle: this many pixels above TC on-screen
_HANDLE_SZ     = 7     # half-size of handle square in pixels

_CURSORS = {
    'TL':'top_left_corner','TC':'top_side','TR':'top_right_corner',
    'ML':'left_side',                      'MR':'right_side',
    'BL':'bottom_left_corner','BC':'bottom_side','BR':'bottom_right_corner',
    'ROT':'exchange',
}


class EdofTkCanvas(tk.Canvas):
    """Tkinter Canvas widget for viewing and interactively editing an EDOF page."""

    def __init__(self, master, doc, page_index: int = 0,
                 zoom: float = 1.0, dpi: int = 96, **kw):
        if not _PIL_OK:
            raise ImportError("Pillow required: pip install Pillow")
        super().__init__(master, **kw)
        self._doc        = doc
        self._page_index = page_index
        self._zoom       = zoom
        self._dpi        = dpi
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._offset     = (0, 0)       # (ox, oy) canvas pixels

        # Selection & interaction
        self._selected:   Optional[str]   = None
        self._drag_mode:  Optional[str]   = None   # 'move'|'resize_XX'|'rotate'
        self._drag_start: Optional[tuple] = None   # (canvas_x, canvas_y)
        self._init_tf:    Optional[object]= None   # Transform copy at drag start

        # Pan
        self._pan_last:   Optional[tuple] = None

        # Inline text edit
        self._text_widget: Optional[tk.Text] = None
        self._text_obj_id: Optional[str]     = None

        # Callbacks
        self._on_select_cbs: List[Callable] = []
        self._on_change_cbs: List[Callable] = []

        self._setup_bindings()
        self.after_idle(self.render)

    # ── Bindings ──────────────────────────────────────────────────────────────

    def _setup_bindings(self):
        self.bind("<ButtonPress-1>",   self._on_lmb_down)
        self.bind("<B1-Motion>",       self._on_lmb_move)
        self.bind("<ButtonRelease-1>", self._on_lmb_up)
        self.bind("<Double-Button-1>", self._on_dbl_click)
        self.bind("<ButtonPress-2>",   self._on_pan_down)
        self.bind("<B2-Motion>",       self._on_pan_move)
        self.bind("<ButtonRelease-2>", self._on_pan_up)
        self.bind("<ButtonPress-3>",   self._on_pan_down)   # also right-drag pan
        self.bind("<B3-Motion>",       self._on_pan_move)
        self.bind("<ButtonRelease-3>", self._on_pan_up)
        self.bind("<MouseWheel>",      self._on_wheel)
        self.bind("<Button-4>",        lambda e: self._zoom_step(1.15))
        self.bind("<Button-5>",        lambda e: self._zoom_step(1/1.15))
        self.bind("<Left>",  lambda e: self._nudge(-0.5, 0))
        self.bind("<Right>", lambda e: self._nudge( 0.5, 0))
        self.bind("<Up>",    lambda e: self._nudge(0, -0.5))
        self.bind("<Down>",  lambda e: self._nudge(0,  0.5))
        self.bind("<Delete>",     self._on_delete)
        self.bind("<Escape>",     lambda e: self._cancel_text_edit())
        self.bind("<Configure>",  lambda e: self.render())
        self.bind("<Motion>",     self._on_mouse_motion)

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self):
        if not self._doc or not self._doc.pages:
            return
        try:
            from edof.engine.renderer import render_page
            page = self._doc.pages[self._page_index]
            img  = render_page(page, self._doc.resources,
                               self._doc.variables, dpi=self._dpi)
            w = max(1, int(img.width  * self._zoom))
            h = max(1, int(img.height * self._zoom))
            img = img.resize((w, h), Image.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            self._photo = ImageTk.PhotoImage(img)
            self.delete("all")
            cw = self.winfo_width()  or w
            ch = self.winfo_height() or h
            ox = max(0, (cw - w) // 2)
            oy = max(0, (ch - h) // 2)
            self._offset = (ox, oy)
            self.create_image(ox, oy, anchor="nw", image=self._photo, tags="page")
            if self._selected:
                self._draw_handles()
            # Reposition inline text widget if open
            if self._text_widget and self._text_obj_id:
                self._reposition_text_widget()
        except Exception as e:
            self.delete("all")
            self.create_text(10, 10, anchor="nw",
                             text=f"Render error:\n{e}", fill="red")

    def _draw_handles(self):
        page = self._doc.pages[self._page_index]
        obj  = page.get_object(self._selected)
        if not obj:
            return
        hpts = self._handle_canvas_positions(obj)
        if not hpts:
            return

        # Object bounding rect
        t     = obj.transform
        x0,y0 = self._mm_to_canvas(t.x, t.y)
        x1,y1 = self._mm_to_canvas(t.x+t.width, t.y+t.height)
        self.create_rectangle(x0, y0, x1, y1,
                              outline="#0078d4", width=2,
                              dash=(6,3), tags="handle")

        # Resize handles
        s = _HANDLE_SZ
        for key, (hx, hy) in hpts.items():
            if key == 'ROT':
                # Rotation handle: circle
                self.create_oval(hx-s, hy-s, hx+s, hy+s,
                                 fill="#ff6600", outline="white",
                                 width=2, tags="handle")
                # Tether line to TC
                if 'TC' in hpts:
                    tx, ty = hpts['TC']
                    self.create_line(tx, ty, hx, hy,
                                     fill="#0078d4", width=1,
                                     dash=(3,2), tags="handle")
            else:
                self.create_rectangle(hx-s, hy-s, hx+s, hy+s,
                                      fill="white", outline="#0078d4",
                                      width=2, tags="handle")

    def _handle_canvas_positions(self, obj) -> dict:
        """Return {key: (cx, cy)} for all handles of the selected object."""
        t = obj.transform
        hpts = {}
        for key, (rx, ry) in _HANDLES.items():
            mx = t.x + rx * t.width
            my = t.y + ry * t.height
            cx, cy = self._mm_to_canvas(mx, my)
            hpts[key] = (cx, cy)
        # Rotation handle: above TC
        if 'TC' in hpts:
            tx, ty = hpts['TC']
            hpts['ROT'] = (tx, ty - _ROT_OFFSET_PX)
        return hpts

    # ── Coordinate conversion ─────────────────────────────────────────────────

    def _mm_to_canvas(self, mx: float, my: float) -> Tuple[float, float]:
        from edof.engine.transform import mm_to_px
        ox, oy = self._offset
        return (ox + mm_to_px(mx, self._dpi) * self._zoom,
                oy + mm_to_px(my, self._dpi) * self._zoom)

    def _canvas_to_mm(self, cx: float, cy: float) -> Tuple[float, float]:
        from edof.engine.transform import px_to_mm
        ox, oy = self._offset
        return (px_to_mm((cx - ox) / self._zoom, self._dpi),
                px_to_mm((cy - oy) / self._zoom, self._dpi))

    # ── Hit testing ───────────────────────────────────────────────────────────

    def _hit_handle(self, cx: float, cy: float) -> Optional[str]:
        """Return handle key if (cx,cy) is on a handle of the selected object."""
        if not self._selected:
            return None
        page = self._doc.pages[self._page_index]
        obj  = page.get_object(self._selected)
        if not obj:
            return None
        hpts = self._handle_canvas_positions(obj)
        s    = _HANDLE_SZ + 3   # slightly larger hit target
        for key, (hx, hy) in hpts.items():
            if abs(cx - hx) <= s and abs(cy - hy) <= s:
                return key
        return None

    def _hit_object(self, cx: float, cy: float) -> Optional[str]:
        """Return id of topmost object at canvas position."""
        mx, my = self._canvas_to_mm(cx, cy)
        page   = self._doc.pages[self._page_index]
        for obj in reversed(page.sorted_objects()):
            if not obj.visible:
                continue
            t = obj.transform
            if t.x <= mx <= t.x + t.width and t.y <= my <= t.y + t.height:
                return obj.id
        return None

    # ── Mouse: left button ────────────────────────────────────────────────────

    def _on_lmb_down(self, event):
        self.focus_set()
        if self._text_widget:
            self._confirm_text_edit()
            return

        cx, cy = float(event.x), float(event.y)
        handle = self._hit_handle(cx, cy)

        if handle:
            # Start handle drag
            self._drag_mode  = f"resize_{handle}" if handle != 'ROT' else 'rotate'
            self._drag_start = (cx, cy)
            page  = self._doc.pages[self._page_index]
            obj   = page.get_object(self._selected)
            import copy
            self._init_tf = copy.copy(obj.transform) if obj else None
            return

        # Try to select an object
        hit = self._hit_object(cx, cy)
        if hit != self._selected:
            self._selected = hit
            for cb in self._on_select_cbs:
                cb(hit)
            self.render()

        if hit:
            self._drag_mode  = 'move'
            self._drag_start = (cx, cy)
            page  = self._doc.pages[self._page_index]
            obj   = page.get_object(hit)
            import copy
            self._init_tf = copy.copy(obj.transform) if obj else None
        else:
            self._drag_mode  = None
            self._drag_start = None
            self._init_tf    = None

    def _on_lmb_move(self, event):
        if not self._drag_mode or not self._drag_start or not self._selected:
            return
        cx, cy = float(event.x), float(event.y)
        dx_c   = cx - self._drag_start[0]
        dy_c   = cy - self._drag_start[1]

        from edof.engine.transform import px_to_mm
        dx_mm = px_to_mm(dx_c / self._zoom, self._dpi)
        dy_mm = px_to_mm(dy_c / self._zoom, self._dpi)

        page = self._doc.pages[self._page_index]
        obj  = page.get_object(self._selected)
        if not obj or not self._init_tf:
            return
        tf = self._init_tf

        if self._drag_mode == 'move':
            obj.transform.x = tf.x + dx_mm
            obj.transform.y = tf.y + dy_mm

        elif self._drag_mode == 'rotate':
            # Angle from object centre to current mouse
            cx_mm, cy_mm  = self._mm_to_canvas(tf.x + tf.width/2,
                                                tf.y + tf.height/2)
            angle = math.degrees(math.atan2(cy - cy_mm, cx - cx_mm)) + 90
            obj.transform.rotation = angle % 360

        else:
            # Resize handle
            handle = self._drag_mode.replace('resize_', '')
            MIN    = 2.0   # mm minimum size
            right  = tf.x + tf.width
            bottom = tf.y + tf.height

            if 'L' in handle:     # left edge moves, right fixed
                new_x = tf.x + dx_mm
                new_w = right - new_x
                if new_w >= MIN:
                    obj.transform.x     = new_x
                    obj.transform.width = new_w
            elif 'R' in handle:   # right edge moves, left fixed
                new_w = max(MIN, tf.width + dx_mm)
                obj.transform.width = new_w

            if 'T' in handle:     # top edge moves, bottom fixed
                new_y = tf.y + dy_mm
                new_h = bottom - new_y
                if new_h >= MIN:
                    obj.transform.y      = new_y
                    obj.transform.height = new_h
            elif 'B' in handle:   # bottom edge moves, top fixed
                new_h = max(MIN, tf.height + dy_mm)
                obj.transform.height = new_h

            # Edge-only handles: TC/BC → only Y; ML/MR → only X
            if handle == 'TC' or handle == 'BC':
                pass   # handled above
            if handle == 'ML' or handle == 'MR':
                pass   # handled above

        self.render()

    def _on_lmb_up(self, event):
        if self._drag_mode and self._drag_start:
            cx, cy = float(event.x), float(event.y)
            moved  = abs(cx - self._drag_start[0]) + abs(cy - self._drag_start[1]) > 2
            if moved:
                for cb in self._on_change_cbs:
                    cb()
        self._drag_mode  = None
        self._drag_start = None
        self._init_tf    = None

    # ── Double-click → inline text edit ───────────────────────────────────────

    def _on_dbl_click(self, event):
        hit = self._hit_object(float(event.x), float(event.y))
        if not hit:
            return
        page = self._doc.pages[self._page_index]
        obj  = page.get_object(hit)
        from edof.format.objects import TextBox
        if isinstance(obj, TextBox):
            self._start_text_edit(obj)

    def _start_text_edit(self, obj):
        self._cancel_text_edit()   # close any existing editor
        from edof.engine.transform import mm_to_px
        t     = obj.transform
        ox,oy = self._offset
        x_c   = ox + mm_to_px(t.x,      self._dpi) * self._zoom
        y_c   = oy + mm_to_px(t.y,      self._dpi) * self._zoom
        w_c   = max(60.0, mm_to_px(t.width,  self._dpi) * self._zoom)
        h_c   = max(24.0, mm_to_px(t.height, self._dpi) * self._zoom)

        fs = max(8, int(obj.style.font_size * self._zoom * self._dpi / 96))
        tw = tk.Text(self, wrap="word", relief="solid", borderwidth=2,
                     bg="#ffffee", fg="#000000",
                     font=("Arial", min(fs, 36)),
                     insertbackground="#000000")
        tw.insert("1.0", obj.text)
        tw.place(x=x_c, y=y_c, width=w_c, height=h_c)
        tw.focus_set()
        tw.mark_set("insert", "1.0")

        self._text_widget = tw
        self._text_obj_id = obj.id

        tw.bind("<Escape>",        lambda e: self._cancel_text_edit())
        tw.bind("<Control-Return>",lambda e: self._confirm_text_edit())
        # Ctrl+A select all
        tw.bind("<Control-a>",     lambda e: (tw.tag_add("sel","1.0","end"), "break"))

    def _reposition_text_widget(self):
        if not self._text_widget or not self._text_obj_id:
            return
        page = self._doc.pages[self._page_index]
        obj  = page.get_object(self._text_obj_id)
        if not obj:
            return
        from edof.engine.transform import mm_to_px
        t     = obj.transform
        ox,oy = self._offset
        x_c   = ox + mm_to_px(t.x,     self._dpi)*self._zoom
        y_c   = oy + mm_to_px(t.y,     self._dpi)*self._zoom
        w_c   = max(60.0, mm_to_px(t.width, self._dpi)*self._zoom)
        h_c   = max(24.0, mm_to_px(t.height,self._dpi)*self._zoom)
        self._text_widget.place(x=x_c, y=y_c, width=w_c, height=h_c)

    def _confirm_text_edit(self):
        if not self._text_widget or not self._text_obj_id:
            return
        text = self._text_widget.get("1.0", "end").rstrip("\n")
        page = self._doc.pages[self._page_index]
        obj  = page.get_object(self._text_obj_id)
        if obj:
            obj.text = text
        self._text_widget.destroy()
        self._text_widget = None
        self._text_obj_id = None
        self.render()
        for cb in self._on_change_cbs:
            cb()

    def _cancel_text_edit(self):
        if self._text_widget:
            self._text_widget.destroy()
            self._text_widget = None
            self._text_obj_id = None

    # ── Pan (middle / right mouse) ────────────────────────────────────────────

    def _on_pan_down(self, event):
        self._pan_last = (event.x, event.y)

    def _on_pan_move(self, event):
        if self._pan_last is None:
            return
        dx = event.x - self._pan_last[0]
        dy = event.y - self._pan_last[1]
        self._pan_last = (event.x, event.y)
        ox, oy = self._offset
        # Clamp so page doesn't fly off screen
        self._offset = (ox + dx, oy + dy)
        self.move("all", dx, dy)
        if self._selected:
            self._draw_handles()

    def _on_pan_up(self, event):
        self._pan_last = None

    # ── Wheel zoom ────────────────────────────────────────────────────────────

    def _on_wheel(self, event):
        self._zoom_step(1.15 if event.delta > 0 else 1/1.15)

    def _zoom_step(self, factor: float):
        self._zoom = max(0.05, min(8.0, self._zoom * factor))
        self.render()

    # ── Cursor feedback on hover ───────────────────────────────────────────────

    def _on_mouse_motion(self, event):
        if self._drag_mode:
            return
        cx, cy  = float(event.x), float(event.y)
        handle  = self._hit_handle(cx, cy)
        if handle:
            self.configure(cursor=_CURSORS.get(handle, "fleur"))
        elif self._hit_object(cx, cy):
            self.configure(cursor="fleur")
        else:
            self.configure(cursor="")

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def _nudge(self, dx: float, dy: float):
        if not self._selected:
            return
        page = self._doc.pages[self._page_index]
        obj  = page.get_object(self._selected)
        if obj:
            obj.transform.translate(dx, dy)
            self.render()
            for cb in self._on_change_cbs:
                cb()

    def _on_delete(self, event):
        if self._text_widget:
            return   # let Delete work in text widget
        if self._selected:
            page = self._doc.pages[self._page_index]
            page.remove_object(self._selected)
            self._selected = None
            self.render()
            for cb in self._on_select_cbs: cb(None)
            for cb in self._on_change_cbs: cb()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_document(self, doc, page_index: int = 0):
        self._doc        = doc
        self._page_index = page_index
        self._selected   = None
        self._cancel_text_edit()
        self.render()

    def set_page(self, index: int):
        self._page_index = index
        self._selected   = None
        self._cancel_text_edit()
        self.render()

    def get_selected(self) -> Optional[str]:
        return self._selected

    def set_selected(self, obj_id: Optional[str]):
        self._selected = obj_id
        self.render()

    def zoom_fit(self):
        if not self._doc or not self._doc.pages:
            return
        page = self._doc.pages[self._page_index]
        from edof.engine.transform import mm_to_px
        pw   = mm_to_px(page.width,  self._dpi)
        ph   = mm_to_px(page.height, self._dpi)
        cw   = self.winfo_width()  or 800
        ch   = self.winfo_height() or 600
        self._zoom = min(cw / pw, ch / ph) * 0.92
        self.render()

    def on_select(self, cb: Callable): self._on_select_cbs.append(cb)
    def on_change(self, cb: Callable): self._on_change_cbs.append(cb)

    @property
    def zoom(self) -> float: return self._zoom
    @zoom.setter
    def zoom(self, v: float):
        self._zoom = max(0.05, min(8.0, v))
        self.render()
