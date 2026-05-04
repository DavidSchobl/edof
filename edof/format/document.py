# edof/format/document.py
"""
Document and Page – the top-level EDOF 3.0 data model.
"""

from __future__ import annotations
import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from edof.format.objects    import (EdofObject, TextBox, ImageBox,
                                     Shape, QRCode, Group, _new_id)
from edof.format.styles     import FillStyle, TextStyle, StrokeStyle
from edof.format.variables  import VariableStore
from edof.engine.transform  import Transform, to_mm

# ── Color-space / bit-depth constants ─────────────────────────────────────────

CS_RGB  = "RGB"
CS_RGBA = "RGBA"
CS_GRAY = "L"
CS_BW   = "1"
CS_CMYK = "CMYK"

BD_8  = 8
BD_16 = 16


# ── Resource store ─────────────────────────────────────────────────────────────

@dataclass
class ResourceEntry:
    resource_id: str
    filename:    str
    mime_type:   str
    data:        bytes
    metadata:    Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "resource_id": self.resource_id,
            "filename":    self.filename,
            "mime_type":   self.mime_type,
            "metadata":    self.metadata,
            # raw data is stored separately in the .edof zip archive
        }


class ResourceStore:
    """Holds all embedded resources (fonts, images, …) for a Document."""

    def __init__(self) -> None:
        self._store: Dict[str, ResourceEntry] = {}

    # ── Adding ────────────────────────────────────────────────────────────────

    def add(self, data: bytes, filename: str,
            mime_type: str = "application/octet-stream",
            metadata: Optional[Dict] = None) -> str:
        """Add raw bytes, return the new resource_id."""
        rid = _new_id()
        self._store[rid] = ResourceEntry(
            resource_id=rid, filename=filename,
            mime_type=mime_type, data=data,
            metadata=metadata or {},
        )
        return rid

    def add_from_file(self, path: str,
                      mime_type: Optional[str] = None) -> str:
        """Add a file from disk, return the new resource_id."""
        import mimetypes, os
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(path)
            mime_type = mime_type or "application/octet-stream"
        with open(path, "rb") as fh:
            data = fh.read()
        import os
        return self.add(data, os.path.basename(path), mime_type)

    # ── Access ────────────────────────────────────────────────────────────────

    def get(self, resource_id: str) -> Optional[ResourceEntry]:
        return self._store.get(resource_id)

    def remove(self, resource_id: str) -> bool:
        return bool(self._store.pop(resource_id, None))

    def all_entries(self) -> Iterator[ResourceEntry]:
        yield from self._store.values()

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, resource_id: str) -> bool:
        return resource_id in self._store

    # ── Serialization ─────────────────────────────────────────────────────────

    def index_dict(self) -> dict:
        """Serialise metadata index (not the raw bytes)."""
        return {rid: entry.to_dict() for rid, entry in self._store.items()}

    @classmethod
    def from_index(cls, index: dict,
                   data_lookup: Dict[str, bytes]) -> "ResourceStore":
        store = cls()
        for rid, meta in index.items():
            store._store[rid] = ResourceEntry(
                resource_id = rid,
                filename    = meta.get("filename", ""),
                mime_type   = meta.get("mime_type", "application/octet-stream"),
                data        = data_lookup.get(rid, b""),
                metadata    = meta.get("metadata", {}),
            )
        return store


# ── Page ──────────────────────────────────────────────────────────────────────

@dataclass
class Page:
    """A single page in an EDOF document."""

    id:          str     = field(default_factory=_new_id)
    index:       int     = 0
    width:       float   = 210.0    # mm  (A4 default)
    height:      float   = 297.0    # mm
    dpi:         int     = 300
    color_space: str     = CS_RGB
    bit_depth:   int     = BD_8
    background:  tuple   = (255, 255, 255)
    objects:     List[EdofObject] = field(default_factory=list)

    # ── Object management ─────────────────────────────────────────────────────

    def add_object(self, obj: EdofObject) -> EdofObject:
        obj.layer = len(self.objects)
        self.objects.append(obj)
        return obj

    def add_textbox(
        self,
        x: float = 0, y: float = 0,
        width: float = 80, height: float = 20,
        text: str = "",
        unit: str = "mm",
        **style_kwargs,
    ) -> TextBox:
        tb = TextBox(text=text)
        tb.transform = Transform(
            x=to_mm(x, unit), y=to_mm(y, unit),
            width=to_mm(width, unit), height=to_mm(height, unit),
        )
        for k, v in style_kwargs.items():
            if hasattr(tb.style, k):
                setattr(tb.style, k, v)
        return self.add_object(tb)  # type: ignore[return-value]

    def add_image(
        self,
        resource_id: str,
        x: float = 0, y: float = 0,
        width: float = 50, height: float = 50,
        unit: str = "mm",
        fit_mode: str = "contain",
    ) -> ImageBox:
        ib = ImageBox(resource_id=resource_id, fit_mode=fit_mode)
        ib.transform = Transform(
            x=to_mm(x, unit), y=to_mm(y, unit),
            width=to_mm(width, unit), height=to_mm(height, unit),
        )
        return self.add_object(ib)  # type: ignore[return-value]

    def add_shape(
        self,
        shape_type: str = "rect",
        x: float = 0, y: float = 0,
        width: float = 50, height: float = 30,
        unit: str = "mm",
    ) -> Shape:
        sh = Shape(shape_type=shape_type)
        sh.transform = Transform(
            x=to_mm(x, unit), y=to_mm(y, unit),
            width=to_mm(width, unit), height=to_mm(height, unit),
        )
        return self.add_object(sh)  # type: ignore[return-value]

    def add_qrcode(
        self,
        data: str,
        x: float = 0, y: float = 0,
        size: float = 30,
        unit: str = "mm",
        error_correction: str = "M",
    ) -> QRCode:
        qr = QRCode(data=data, error_correction=error_correction)
        s  = to_mm(size, unit)
        qr.transform = Transform(
            x=to_mm(x, unit), y=to_mm(y, unit),
            width=s, height=s,
        )
        return self.add_object(qr)  # type: ignore[return-value]


    def add_group(self) -> Group:
        g = Group()
        return self.add_object(g)  # type: ignore[return-value]

    # ══════════════════════════════════════════════════════════════════════════
    # v4.0: Repeating sections (templating)
    # ══════════════════════════════════════════════════════════════════════════

    def repeat_objects(self, template_objs, data_list,
                       gap: float = 2.0,
                       y_start: Optional[float] = None,
                       y_end: Optional[float] = None,
                       new_page_callback=None) -> List["Page"]:
        """v4.0: Duplicate template objects for each row in data_list.

        For each row in data_list (a list of dicts), the template_objs are
        deep-copied, their {column_name} placeholders in text/runs are
        substituted with row values, and the copies are translated downward
        by (block_height + gap).

        When the bottom of the next block would exceed y_end (defaults to
        page.height - 10mm), a new page is created (sharing the same width,
        height, dpi, color_space, bit_depth) and content continues there.

        new_page_callback(new_page) lets the caller add headers/footers to
        each generated page.

        Returns the list of pages created (the original page is index 0;
        any additional pages are appended).
        """
        import copy
        if not template_objs or not data_list: return [self]

        # Compute bbox of template
        ys = [o.transform.y for o in template_objs]
        ye = [o.transform.y + o.transform.height for o in template_objs]
        block_top    = min(ys)
        block_bottom = max(ye)
        block_height = block_bottom - block_top

        if y_start is None: y_start = block_top
        if y_end   is None: y_end   = self.height - 10.0

        pages = [self]
        cur_page = self
        cur_y    = y_start

        for row in data_list:
            # Check if next block fits
            if cur_y + block_height > y_end:
                # Create new page
                new_page = Page(
                    width=self.width, height=self.height,
                    dpi=self.dpi, color_space=self.color_space,
                    bit_depth=self.bit_depth,
                    background=self.background,
                )
                new_page.index = (cur_page.index or 0) + 1
                pages.append(new_page)
                cur_page = new_page
                cur_y    = y_start
                if new_page_callback:
                    new_page_callback(new_page)

            # Copy template objects with substitution
            for tpl in template_objs:
                obj = copy.deepcopy(tpl)
                obj.id = _new_id()
                obj.transform.y = cur_y + (tpl.transform.y - block_top)
                _substitute_row(obj, row)
                cur_page.add_object(obj)

            cur_y += block_height + gap

        return pages


    # ══════════════════════════════════════════════════════════════════════════
    # Helper widgets (item 4)  – high-level composite objects
    # ══════════════════════════════════════════════════════════════════════════

    def add_card(
        self,
        x: float, y: float, w: float, h: float,
        title: str = "",
        body: str = "",
        accent_color: tuple = (83, 74, 183, 255),
        bg_color: tuple = (255, 255, 255, 255),
        border_color: tuple = (220, 220, 230, 255),
        title_font_size: float = 14,
        body_font_size: float = 10,
        unit: str = "mm",
    ) -> Group:
        """Card widget: rounded background + accent header + title + body text."""
        x, y, w, h = to_mm(x,unit), to_mm(y,unit), to_mm(w,unit), to_mm(h,unit)
        g = Group()
        # Background
        bg = Shape(shape_type="rect")
        bg.transform = Transform(x=x, y=y, width=w, height=h)
        bg.fill.color = bg_color; bg.stroke.color = border_color; bg.stroke.width = 0.5
        bg.corner_radius = 2.0
        g.children.append(bg)
        # Accent bar
        bar_h = max(6.0, title_font_size * 0.7)
        bar = Shape(shape_type="rect")
        bar.transform = Transform(x=x, y=y, width=w, height=bar_h)
        bar.fill.color = accent_color; bar.stroke.color = accent_color
        g.children.append(bar)
        # Title
        if title:
            tb = TextBox(text=title)
            tb.transform = Transform(x=x+2, y=y, width=w-4, height=bar_h)
            tb.style.font_size = title_font_size; tb.style.bold = True
            tb.style.color = (255, 255, 255); tb.style.vertical_align = "middle"
            tb.style.auto_shrink = True; tb.style.padding = 0.5
            g.children.append(tb)
        # Body
        if body:
            tb2 = TextBox(text=body)
            tb2.transform = Transform(x=x+2, y=y+bar_h+1, width=w-4, height=h-bar_h-2)
            tb2.style.font_size = body_font_size; tb2.style.wrap = True
            tb2.style.overflow_hidden = True; tb2.style.padding = 0.5
            g.children.append(tb2)
        return self.add_object(g)  # type: ignore[return-value]

    def add_metric(
        self,
        x: float, y: float, w: float, h: float,
        label: str = "Metric",
        value: str = "0",
        subtitle: str = "",
        value_color: tuple = (83, 74, 183, 255),
        unit: str = "mm",
    ) -> Group:
        """Metric widget: large value + label + optional subtitle."""
        x, y, w, h = to_mm(x,unit), to_mm(y,unit), to_mm(w,unit), to_mm(h,unit)
        g = Group()
        # Value
        val_h = h * 0.55
        tv = TextBox(text=value)
        tv.transform = Transform(x=x, y=y, width=w, height=val_h)
        tv.style.auto_fill = True; tv.style.alignment = "center"
        tv.style.vertical_align = "bottom"; tv.style.bold = True
        tv.style.color = value_color[:3] if len(value_color)>=3 else (83,74,183)
        tv.style.padding = 0.5
        g.children.append(tv)
        # Label
        tl = TextBox(text=label)
        tl.transform = Transform(x=x, y=y+val_h, width=w, height=h*0.25)
        tl.style.font_size = 9; tl.style.alignment = "center"
        tl.style.color = (100, 100, 120); tl.style.padding = 0.5
        g.children.append(tl)
        # Subtitle
        if subtitle:
            ts = TextBox(text=subtitle)
            ts.transform = Transform(x=x, y=y+val_h+h*0.25, width=w, height=h*0.2)
            ts.style.font_size = 8; ts.style.alignment = "center"
            ts.style.color = (160, 160, 180); ts.style.padding = 0.5
            g.children.append(ts)
        return self.add_object(g)  # type: ignore[return-value]

    def add_table(
        self,
        x: float, y: float, w: float,
        rows: list,
        header: bool = True,
        row_height: float = 8.0,
        alternating: bool = True,
        header_color: tuple = (83, 74, 183, 255),
        alt_color: tuple = (245, 245, 252, 255),
        border_color: tuple = (200, 200, 215, 255),
        font_size: float = 9.0,
        unit: str = "mm",
    ) -> Group:
        """Simple table widget."""
        x, y, w = to_mm(x,unit), to_mm(y,unit), to_mm(w,unit)
        rh = to_mm(row_height, unit)
        g  = Group()
        if not rows: return self.add_object(g)  # type: ignore[return-value]
        n_cols = len(rows[0])
        col_w  = w / n_cols

        for ri, row in enumerate(rows):
            is_header = (ri == 0 and header)
            row_y     = y + ri * rh
            # Row background
            bg = Shape(shape_type="rect")
            bg.transform = Transform(x=x, y=row_y, width=w, height=rh)
            if is_header:
                bg.fill.color = header_color
            elif alternating and ri % 2 == 0:
                bg.fill.color = alt_color
            else:
                bg.fill.color = (255, 255, 255, 255)
            bg.stroke.color = border_color; bg.stroke.width = 0.3
            g.children.append(bg)
            # Cells
            for ci, cell in enumerate(row):
                tb = TextBox(text=str(cell))
                tb.transform = Transform(x=x+ci*col_w, y=row_y, width=col_w, height=rh)
                tb.style.font_size = font_size; tb.style.padding = 1.0
                tb.style.vertical_align = "middle"; tb.style.auto_shrink = True
                if is_header:
                    tb.style.bold = True; tb.style.color = (255, 255, 255)
                else:
                    tb.style.color = (40, 40, 60)
                g.children.append(tb)

        return self.add_object(g)  # type: ignore[return-value]

    def add_kv_list(
        self,
        x: float, y: float, w: float,
        items: list,
        row_height: float = 7.0,
        key_width_frac: float = 0.4,
        key_color: tuple = (100, 100, 130),
        value_color: tuple = (20, 20, 40),
        font_size: float = 9.0,
        unit: str = "mm",
    ) -> Group:
        """Key-value definition list widget."""
        x, y, w = to_mm(x,unit), to_mm(y,unit), to_mm(w,unit)
        rh = to_mm(row_height, unit)
        g  = Group()
        kw = w * key_width_frac; vw = w - kw

        for ri, item in enumerate(items):
            key = str(item[0]) if len(item) >= 1 else ""
            val = str(item[1]) if len(item) >= 2 else ""
            row_y = y + ri * rh
            # Key
            tk = TextBox(text=key)
            tk.transform = Transform(x=x, y=row_y, width=kw, height=rh)
            tk.style.font_size = font_size; tk.style.bold = True
            tk.style.color = key_color; tk.style.vertical_align = "middle"
            tk.style.padding = 0.5; tk.style.auto_shrink = True
            g.children.append(tk)
            # Value
            tv = TextBox(text=val)
            tv.transform = Transform(x=x+kw, y=row_y, width=vw, height=rh)
            tv.style.font_size = font_size; tv.style.color = value_color
            tv.style.vertical_align = "middle"; tv.style.padding = 0.5
            tv.style.auto_shrink = True
            g.children.append(tv)

        return self.add_object(g)  # type: ignore[return-value]

    # ══════════════════════════════════════════════════════════════════════════
    # Layout helpers (item 5)
    # ══════════════════════════════════════════════════════════════════════════

    def row(self, y: float, gap: float = 2.0,
            height: float = 10.0, unit: str = "mm") -> "_RowContext":
        """Return a row layout context that auto-positions objects left-to-right."""
        return _RowContext(self, to_mm(0, unit), to_mm(y, unit),
                           to_mm(gap, unit), to_mm(height, unit))

    def column(self, x: float, gap: float = 2.0,
               width: float = 40.0, unit: str = "mm") -> "_ColumnContext":
        """Return a column layout context that auto-positions objects top-to-bottom."""
        return _ColumnContext(self, to_mm(x, unit), to_mm(0, unit),
                              to_mm(gap, unit), to_mm(width, unit))

    # ══════════════════════════════════════════════════════════════════════════
    # Auto-height textbox (item 6)
    # ══════════════════════════════════════════════════════════════════════════

    def add_textbox_auto(
        self,
        x: float, y: float, w: float,
        text: str = "",
        min_height: float = 6.0,
        unit: str = "mm",
        **style_kwargs,
    ) -> TextBox:
        """
        Add a TextBox whose height is computed automatically from the text content.
        Returns the TextBox; its transform.height is set to the measured value.
        The caller can read tb.transform.y + tb.transform.height to get next_y.
        """
        from edof.engine.text_engine import measure_text_height
        from edof.format.styles import TextStyle

        x_mm = to_mm(x, unit); y_mm = to_mm(y, unit)
        w_mm = to_mm(w, unit); min_h = to_mm(min_height, unit)

        # Build a temporary style to measure height
        tmp_style = TextStyle()
        for k, v in style_kwargs.items():
            if hasattr(tmp_style, k):
                setattr(tmp_style, k, v)

        h_mm = max(min_h, measure_text_height(text, tmp_style, w_mm))

        tb = TextBox(text=text)
        tb.transform = Transform(x=x_mm, y=y_mm, width=w_mm, height=h_mm)
        for k, v in style_kwargs.items():
            if hasattr(tb.style, k):
                setattr(tb.style, k, v)
        return self.add_object(tb)  # type: ignore[return-value]

    def remove_object(self, obj_id: str) -> bool:
        before = len(self.objects)
        self.objects = [o for o in self.objects if o.id != obj_id]
        return len(self.objects) < before

    def get_object(self, obj_id: str) -> Optional[EdofObject]:
        return next((o for o in self.objects if o.id == obj_id), None)

    def get_by_name(self, name: str) -> List[EdofObject]:
        return [o for o in self.objects if o.name == name]

    def get_by_tag(self, tag: str) -> List[EdofObject]:
        return [o for o in self.objects if tag in o.tags]

    def sorted_objects(self) -> List[EdofObject]:
        """Return objects sorted by layer (ascending = bottom to top)."""
        return sorted(self.objects, key=lambda o: o.layer)

    def duplicate(self) -> "Page":
        p       = copy.deepcopy(self)
        p.id    = _new_id()
        p.index = self.index + 1
        # Give each object a fresh id
        for obj in p.objects:
            obj.id = _new_id()
        return p

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        from edof.format.styles import _rgba_to_hex
        return {
            "id":          self.id,
            "index":       self.index,
            "width":       self.width,
            "height":      self.height,
            "dpi":         self.dpi,
            "color_space": self.color_space,
            "bit_depth":   self.bit_depth,
            "background":  _rgba_to_hex(self.background),
            "objects":     [o.to_dict() for o in self.objects],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Page":
        from edof.format.styles import _hex_to_rgba
        bg_raw = d.get("background", "#ffffff")
        bg     = _hex_to_rgba(bg_raw) if isinstance(bg_raw, str) else tuple(bg_raw)
        p = cls(
            id          = d.get("id",          _new_id()),
            index       = int(d.get("index",       0)),
            width       = float(d.get("width",   210.0)),
            height      = float(d.get("height",  297.0)),
            dpi         = int(d.get("dpi",         300)),
            color_space = d.get("color_space",  CS_RGB),
            bit_depth   = int(d.get("bit_depth",     8)),
            background  = bg,
        )
        p.objects = [EdofObject.from_dict(o) for o in d.get("objects", [])]
        return p


# ── Document ──────────────────────────────────────────────────────────────────

class Document:
    """
    Root object for an EDOF document.

    Usage::

        doc = edof.Document(width=210, height=297)
        page = doc.add_page()
        tb = page.add_textbox(10, 10, 100, 20, "Hello!")
        doc.save("hello.edof")
    """

    def __init__(
        self,
        width:        float = 210.0,   # mm
        height:       float = 297.0,   # mm
        dpi:          int   = 300,
        color_space:  str   = CS_RGB,
        bit_depth:    int   = BD_8,
        title:        str   = "",
        author:       str   = "",
        description:  str   = "",
    ) -> None:
        self.id           = _new_id()
        self.title        = title
        self.author       = author
        self.description  = description
        self.created      = datetime.now(timezone.utc).isoformat()
        self.modified     = self.created
        self.default_width       = width
        self.default_height      = height
        self.default_dpi         = dpi
        self.default_color_space = color_space
        self.default_bit_depth   = bit_depth
        self.pages:     List[Page]     = []
        self.variables: VariableStore  = VariableStore()
        self.resources: ResourceStore  = ResourceStore()
        self._error_state: List[str]   = []   # non-fatal warnings / errors
        # v4.0.1: encryption + permissions
        from edof.crypto.document_protection import DocumentProtection
        self._protection = DocumentProtection()

    # ── Error state ───────────────────────────────────────────────────────────

    def _push_error(self, msg: str) -> None:
        self._error_state.append(msg)

    @property
    def errors(self) -> List[str]:
        return list(self._error_state)

    def clear_errors(self) -> None:
        self._error_state.clear()

    # ── Pages ─────────────────────────────────────────────────────────────────

    def add_page(
        self,
        width:        Optional[float] = None,
        height:       Optional[float] = None,
        dpi:          Optional[int]   = None,
        color_space:  Optional[str]   = None,
        bit_depth:    Optional[int]   = None,
        background:   tuple           = (255, 255, 255),
    ) -> Page:
        page = Page(
            index       = len(self.pages),
            width       = width       or self.default_width,
            height      = height      or self.default_height,
            dpi         = dpi         or self.default_dpi,
            color_space = color_space or self.default_color_space,
            bit_depth   = bit_depth   or self.default_bit_depth,
            background  = background,
        )
        self.pages.append(page)
        return page

    def get_page(self, index: int) -> Page:
        return self.pages[index]

    def remove_page(self, index: int) -> None:
        self.pages.pop(index)
        for i, p in enumerate(self.pages):
            p.index = i

    def move_page(self, from_index: int, to_index: int) -> None:
        page = self.pages.pop(from_index)
        self.pages.insert(to_index, page)
        for i, p in enumerate(self.pages):
            p.index = i

    def duplicate_page(self, index: int) -> Page:
        new_page = self.pages[index].duplicate()
        self.pages.insert(index + 1, new_page)
        for i, p in enumerate(self.pages):
            p.index = i
        return new_page

    # ── Variables ─────────────────────────────────────────────────────────────

    def define_variable(self, name: str, **kwargs) -> None:
        self.variables.define(name, **kwargs)

    def set_variable(self, name: str, value: Any) -> None:
        self.variables.set(name, value)

    def fill_variables(self, mapping: Dict[str, Any]) -> None:
        """Batch fill – ``doc.fill_variables({"name": "Jan", "date": "2025"})``"""
        self.variables.fill(mapping)

    # ── Resources ─────────────────────────────────────────────────────────────

    def add_resource(self, data: bytes, filename: str,
                     mime_type: str = "application/octet-stream") -> str:
        return self.resources.add(data, filename, mime_type)

    def add_resource_from_file(self, path: str) -> str:
        return self.resources.add_from_file(path)

    # ── Save / Load ───────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        from edof.format.serializer import EdofSerializer
        EdofSerializer.save(self, path)
        self.modified = datetime.now(timezone.utc).isoformat()

    @classmethod
    def load(cls, path: str, password: str = None,
              recovery_key: str = None) -> "Document":
        from edof.format.serializer import EdofSerializer
        return EdofSerializer.load(path, password=password,
                                    recovery_key=recovery_key)

    # ── Export helpers ─────────────────────────────────────────────────────────

    def export_bitmap(
        self,
        path:         str,
        page:         int  = 0,
        dpi:          Optional[int] = None,
        color_space:  Optional[str] = None,
        bit_depth:    Optional[int] = None,
        format:       str  = "PNG",
    ) -> None:
        from edof.export.bitmap import export_page_bitmap
        export_page_bitmap(
            self, page_index=page, path=path,
            dpi=dpi, color_space=color_space,
            bit_depth=bit_depth, format=format,
        )

    def export_pdf(self, path: str, vector: bool = True,
                    dpi: Optional[int] = None) -> None:
        """v4.0: Export to PDF.

        vector=True (default) uses the built-in pure-Python vector PDF writer
        (searchable text, small files, no reportlab dependency).
        vector=False falls back to raster mode via reportlab.
        """
        from edof.export.pdf import export_pdf
        export_pdf(self, path, vector=vector, dpi=dpi)

    def export_svg(self, path: str, page: int = 0) -> None:
        """v4.0: Export a single page as SVG."""
        from edof.export.svg import export_svg
        export_svg(self, path, page=page)

    # ══════════════════════════════════════════════════════════════════════════
    # v4.0.1: Encryption & permission control
    # ══════════════════════════════════════════════════════════════════════════

    @property
    def encryption_mode(self) -> str:
        """One of 'none', 'partial', 'full'. Set via save() or set_password()."""
        return self._protection.mode

    @encryption_mode.setter
    def encryption_mode(self, mode: str) -> None:
        if mode not in ("none", "partial", "full"):
            raise ValueError(f"Mode must be 'none', 'partial' or 'full', got {mode!r}")
        if mode != "none" and self._protection.mode == "none":
            # Switching from plain → encrypted requires at least one password
            if not self._protection.has_password("admin") and not self._protection.slots:
                raise PermissionError(
                    "Cannot enable encryption: no passwords have been set. "
                    "Call doc.set_password('admin', '...') first."
                )
        self._protection.mode = mode

    @property
    def is_encrypted(self) -> bool:
        return self._protection.is_encrypted

    @property
    def is_locked(self) -> bool:
        """True if the document is encrypted and not yet unlocked."""
        return self._protection.is_encrypted and not self._protection.is_unlocked

    @property
    def permission_level(self) -> "Permission":
        from edof.crypto import Permission
        return self._protection.permission

    @property
    def password_levels(self) -> List[str]:
        """Levels that have passwords set (e.g. ['fill', 'admin'])."""
        return self._protection.password_levels

    def can(self, required) -> bool:
        """Test whether the current session has at least the required permission."""
        return self._protection.can(required)

    def require(self, required) -> None:
        """Raise PermissionError if the current session lacks the permission."""
        self._protection.require(required)

    def set_password(self, level: str, password: str) -> Optional[str]:
        """Set or replace the password for a permission level.

        level: 'fill' | 'edit' | 'design' | 'admin'

        Returns a recovery key string if this is the first password being set
        on the document; otherwise None. **Save the recovery key immediately
        and securely** — it cannot be retrieved later if you lose all passwords.

        After this call the document switches to encryption_mode='full'.
        Use doc.encryption_mode = 'partial' if you want partial encryption.

        Multi-level usage:
            rk = doc.set_password('admin',  'master')   # returns recovery key
            doc.set_password('fill',   'klienti')        # returns None
            doc.set_password('edit',   'korektura')      # returns None
        """
        return self._protection.set_password(level, password)

    def remove_password(self, level: str) -> None:
        """Remove a password slot. Requires ADMIN permission."""
        self._protection.remove_password(level)

    def change_password(self, level: str, old_password: str,
                         new_password: str) -> None:
        """Rotate a password. Knowing the old password is sufficient."""
        self._protection.change_password(level, old_password, new_password)

    def clear_all_protection(self) -> None:
        """Remove all encryption and passwords. Requires ADMIN permission."""
        self._protection.clear_all_passwords()

    def unlock(self, password: str = None,
                recovery_key: str = None) -> "Permission":
        """Unlock an encrypted document with a password or recovery key.

        Returns the granted Permission. Raises EdofWrongPassword on failure.
        """
        if not self._protection.is_encrypted:
            from edof.crypto import ADMIN
            return ADMIN
        if recovery_key:
            return self._protection.unlock_with_recovery_key(recovery_key)
        if password is not None:
            return self._protection.unlock_with_password(password)
        from edof.crypto import EdofPasswordRequired
        raise EdofPasswordRequired("Document is encrypted; provide password or recovery_key")

    def lock(self) -> None:
        """Forget the cached content key for this session."""
        self._protection.lock()

    @property
    def recovery_key(self) -> Optional[str]:
        """Pending recovery key (returned once after first set_password())."""
        return self._protection._pending_recovery_key

    def consume_recovery_key(self) -> Optional[str]:
        """Get and clear the pending recovery key."""
        return self._protection.take_pending_recovery_key()

    def export_3x(self, path: str) -> None:
        """v4.0.1: Save a downgraded copy of the document as a v3.x .edof file.

        Best-effort lossy conversion:
          - Tables → Groups of TextBoxes + line shapes
          - TextBox.runs[] → flattened to plain text (formatting lost)
          - Path shapes → polygon shapes (Beziers sampled)
          - Gradients → average color of stops
          - visible_if → evaluated and baked into .visible
          - blend_mode → reset to 'normal'

        The output can be opened by edof 3.x. Use this when you need to
        share an EDOF document with someone running the older library.
        The original (in-memory) document is not modified.
        """
        from edof.export.legacy_v3 import export_3x
        export_3x(self, path)

    def print_document(self, printer: Optional[str] = None,
                       pages: Optional[List[int]] = None) -> None:
        from edof.export.printer import print_document
        print_document(self, printer=printer, pages=pages)

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> List[str]:
        """Return list of validation issues (empty = valid)."""
        issues: List[str] = []
        if not self.pages:
            issues.append("Document has no pages.")
        for i, page in enumerate(self.pages):
            for obj in page.objects:
                if obj.variable and obj.variable not in self.variables.names():
                    issues.append(
                        f"Page {i}: object '{obj.id}' references "
                        f"undefined variable '{obj.variable}'."
                    )
                if hasattr(obj, "resource_id") and obj.resource_id:
                    if obj.resource_id not in self.resources:
                        issues.append(
                            f"Page {i}: object '{obj.id}' references "
                            f"missing resource '{obj.resource_id}'."
                        )
        missing = self.variables.missing_required()
        if missing:
            issues.append(f"Required variables not set: {missing}")
        return issues

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        from edof.version import FORMAT_VERSION_STR
        return {
            "edof_version":   FORMAT_VERSION_STR,
            "id":             self.id,
            "title":          self.title,
            "author":         self.author,
            "description":    self.description,
            "created":        self.created,
            "modified":       self.modified,
            "defaults": {
                "width":       self.default_width,
                "height":      self.default_height,
                "dpi":         self.default_dpi,
                "color_space": self.default_color_space,
                "bit_depth":   self.default_bit_depth,
            },
            "pages":     [p.to_dict() for p in self.pages],
            "variables": self.variables.to_dict(),
            "resources": self.resources.index_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict,
                  resource_data: Dict[str, bytes] = None) -> "Document":
        defs = d.get("defaults", {})
        doc  = cls(
            width       = float(defs.get("width",        210.0)),
            height      = float(defs.get("height",       297.0)),
            dpi         = int(  defs.get("dpi",            300)),
            color_space =       defs.get("color_space",  CS_RGB),
            bit_depth   = int(  defs.get("bit_depth",        8)),
            title       =       d.get("title",              ""),
            author      =       d.get("author",             ""),
            description =       d.get("description",        ""),
        )
        doc.id       = d.get("id",       _new_id())
        doc.created  = d.get("created",  doc.created)
        doc.modified = d.get("modified", doc.modified)
        doc.pages    = [Page.from_dict(pd) for pd in d.get("pages", [])]
        doc.variables = VariableStore.from_dict(d.get("variables", {}))
        doc.resources = ResourceStore.from_index(
            d.get("resources", {}),
            resource_data or {},
        )
        return doc

    def __repr__(self) -> str:
        return (
            f"<Document title={self.title!r} pages={len(self.pages)} "
            f"vars={len(self.variables.names())} "
            f"resources={len(self.resources)}>"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Layout context helpers (item 5)
# ══════════════════════════════════════════════════════════════════════════════

class _RowContext:
    """Auto-positions objects left-to-right on a horizontal row."""

    def __init__(self, page: Page, start_x: float, y: float,
                 gap: float, default_height: float):
        self._page    = page
        self._x       = start_x
        self._y       = y
        self._gap     = gap
        self._dh      = default_height

    @property
    def next_x(self) -> float:
        return self._x

    @property
    def y(self) -> float:
        return self._y

    def add_textbox(self, width: float, text: str = "",
                    height: Optional[float] = None, **style_kwargs):
        h  = height if height is not None else self._dh
        tb = self._page.add_textbox(self._x, self._y, width, h, text, **style_kwargs)
        self._x += width + self._gap
        return tb

    def add_image(self, resource_id, width: float, height: Optional[float] = None,
                  fit_mode: str = "contain"):
        h  = height if height is not None else self._dh
        ib = self._page.add_image(resource_id, self._x, self._y, width, h, fit_mode=fit_mode)
        self._x += width + self._gap
        return ib

    def add_shape(self, shape_type: str = "rect", width: float = 10,
                  height: Optional[float] = None):
        h  = height if height is not None else self._dh
        sh = self._page.add_shape(shape_type, self._x, self._y, width, h)
        self._x += width + self._gap
        return sh

    def skip(self, width: float):
        """Advance cursor without adding an object."""
        self._x += width + self._gap


class _ColumnContext:
    """Auto-positions objects top-to-bottom in a column."""

    def __init__(self, page: Page, x: float, start_y: float,
                 gap: float, default_width: float):
        self._page = page
        self._x    = x
        self._y    = start_y
        self._gap  = gap
        self._dw   = default_width

    @property
    def next_y(self) -> float:
        return self._y

    @property
    def x(self) -> float:
        return self._x

    def add_textbox(self, height: float, text: str = "",
                    width: Optional[float] = None, **style_kwargs):
        w  = width if width is not None else self._dw
        tb = self._page.add_textbox(self._x, self._y, w, height, text, **style_kwargs)
        self._y += height + self._gap
        return tb

    def add_textbox_auto(self, text: str = "", width: Optional[float] = None,
                         min_height: float = 6.0, **style_kwargs):
        w  = width if width is not None else self._dw
        tb = self._page.add_textbox_auto(self._x, self._y, w, text,
                                          min_height=min_height, **style_kwargs)
        self._y += tb.transform.height + self._gap
        return tb

    def add_image(self, resource_id, height: float, width: Optional[float] = None,
                  fit_mode: str = "contain"):
        w  = width if width is not None else self._dw
        ib = self._page.add_image(resource_id, self._x, self._y, w, height, fit_mode=fit_mode)
        self._y += height + self._gap
        return ib

    def add_shape(self, shape_type: str = "rect", height: float = 5,
                  width: Optional[float] = None):
        w  = width if width is not None else self._dw
        sh = self._page.add_shape(shape_type, self._x, self._y, w, height)
        self._y += height + self._gap
        return sh

    def skip(self, height: float):
        """Advance cursor without adding an object."""
        self._y += height + self._gap


# ══════════════════════════════════════════════════════════════════════════════
#  v4.0: Variable substitution helper for repeat_objects
# ══════════════════════════════════════════════════════════════════════════════

def _substitute_row(obj, row: dict) -> None:
    """Replace {col_name} placeholders in obj.text, obj.runs, qrcode.data, etc."""
    from edof.format.objects import TextBox, QRCode, Group, Table

    def _sub(s: str) -> str:
        if not s or "{" not in s: return s
        for k, v in row.items():
            s = s.replace("{" + str(k) + "}", str(v) if v is not None else "")
        return s

    if isinstance(obj, TextBox):
        obj.text = _sub(obj.text)
        for run in obj.runs:
            run.text = _sub(run.text)
    elif isinstance(obj, QRCode):
        obj.data = _sub(obj.data)
    elif isinstance(obj, Table):
        for row_cells in obj.cells:
            for cell in row_cells:
                cell.text = _sub(cell.text)
                for run in cell.runs:
                    run.text = _sub(run.text)
    elif isinstance(obj, Group):
        for child in obj.children:
            _substitute_row(child, row)
