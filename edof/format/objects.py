# edof/format/objects.py
"""
All document-object types for EDOF 3.0.

Every object carries:
  id        – UUID
  name      – human label (used in editor)
  variable  – name of a VariableDef this object is bound to
  transform – Transform (position, size, rotation, flips)
  locked    – cannot be selected in an editor
  visible   – toggle render visibility
  layer     – z-order (higher = on top)
  tags      – arbitrary string labels
  shadow    – drop shadow
  opacity   – 0.0–1.0
"""

from __future__ import annotations
import copy
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

from edof.engine.transform import Transform
from edof.format.styles import (
    TextStyle, StrokeStyle, FillStyle, ShadowStyle,
)


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Base ──────────────────────────────────────────────────────────────────────

@dataclass
class EdofObject:
    OBJECT_TYPE: str = field(default="base", init=False, repr=False)

    id:        str               = field(default_factory=_new_id)
    name:      str               = ""
    variable:  Optional[str]     = None
    transform: Transform         = field(default_factory=Transform)
    locked:    bool              = False
    visible:   bool              = True
    layer:     int               = 0
    tags:      List[str]         = field(default_factory=list)
    shadow:    ShadowStyle       = field(default_factory=ShadowStyle)
    opacity:   float             = 1.0
    # v4.0: conditional visibility — Python-style boolean expression
    # evaluated against doc.variables. Empty = always visible (uses .visible flag).
    visible_if: str              = ""
    # v4.0: blend mode for compositing this object onto the canvas
    # one of: "normal", "multiply", "screen", "overlay", "darken", "lighten"
    blend_mode: str              = "normal"
    # v4.0.1: per-object permission lock — modifying this object requires
    # at least this permission level. Empty = no per-object lock.
    # Values: "" | "fill" | "edit" | "design" | "admin"
    lock_level: str              = ""
    # v4.0.1: hard text lock. Even with sufficient permission, .text and
    # .runs cannot be modified until lock_text is set False, which requires
    # ADMIN permission. Useful for "this header must never change".
    lock_text:  bool             = False

    # ── Transform shortcuts ────────────────────────────────────────────────────

    def move(self, dx: float, dy: float, unit: str = "mm") -> "EdofObject":
        self.transform.translate(dx, dy, unit); return self

    def move_to(self, x: float, y: float, unit: str = "mm") -> "EdofObject":
        self.transform.move_to(x, y, unit); return self

    def rotate(self, angle: float) -> "EdofObject":
        self.transform.rotate(angle); return self

    def rotate_to(self, angle: float) -> "EdofObject":
        self.transform.rotate_to(angle); return self

    def resize_uniform(self, factor: float,
                       anchor: str = "center") -> "EdofObject":
        self.transform.resize_uniform(factor, anchor); return self

    def resize(self, w: float, h: float, unit: str = "mm",
               anchor: str = "top-left") -> "EdofObject":
        self.transform.resize_free(w, h, unit, anchor); return self

    def flip_h(self) -> "EdofObject":
        self.transform.flip_horizontal(); return self

    def flip_v(self) -> "EdofObject":
        self.transform.flip_vertical(); return self

    # ── Serialization ──────────────────────────────────────────────────────────

    def _base_dict(self) -> dict:
        return {
            "type":      self.OBJECT_TYPE,
            "id":        self.id,
            "name":      self.name,
            "variable":  self.variable,
            "transform": self.transform.to_dict(),
            "locked":    self.locked,
            "visible":   self.visible,
            "layer":     self.layer,
            "tags":      self.tags,
            "shadow":    self.shadow.to_dict(),
            "opacity":   self.opacity,
            "editable":  getattr(self, "editable", True),
            "visible_if": self.visible_if,    # v4.0
            "blend_mode": self.blend_mode,    # v4.0
            "lock_level": self.lock_level,    # v4.0.1
            "lock_text":  self.lock_text,     # v4.0.1
        }

    def to_dict(self) -> dict:
        return self._base_dict()

    @staticmethod
    def from_dict(d: dict) -> "EdofObject":
        _cls_map = {
            "textbox":  TextBox,
            "imagebox": ImageBox,
            "shape":    Shape,
            "qrcode":   QRCode,
            "group":    Group,
            "table":    Table,    # v4.0
        }
        cls = _cls_map.get(d.get("type", ""), EdofObject)
        return cls._from_dict(d)

    @classmethod
    def _from_dict(cls, d: dict) -> "EdofObject":
        obj           = cls.__new__(cls)
        obj.id        = d.get("id",       _new_id())
        obj.name      = d.get("name",     "")
        obj.variable  = d.get("variable")
        obj.transform = Transform.from_dict(d.get("transform", {}))
        obj.locked    = bool(d.get("locked",  False))
        obj.visible   = bool(d.get("visible", True))
        obj.layer     = int(d.get("layer",    0))
        obj.tags      = list(d.get("tags",    []))
        obj.shadow    = ShadowStyle.from_dict(d.get("shadow", {}))
        obj.opacity   = float(d.get("opacity", 1.0))
        obj.editable  = bool(d.get("editable", True))
        obj.visible_if = d.get("visible_if", "") or ""    # v4.0
        obj.blend_mode = d.get("blend_mode", "normal")    # v4.0
        obj.lock_level = d.get("lock_level", "") or ""    # v4.0.1
        obj.lock_text  = bool(d.get("lock_text", False))  # v4.0.1
        return obj

    def copy(self) -> "EdofObject":
        c    = copy.deepcopy(self)
        c.id = _new_id()
        return c

    def __post_init__(self) -> None:
        # Allow subclasses to set OBJECT_TYPE as a plain class attribute
        pass

    # ── v4.0.1: Permission gate helpers ───────────────────────────────────────

    def can_modify(self, doc) -> bool:
        """Return True if this object can be modified given doc's current
        session permission. Honors per-object lock_level.
        """
        if not getattr(doc, "_protection", None):
            return True
        # Plain doc with no protection → always editable
        if not doc.is_encrypted and not self.lock_level:
            return True
        # If object has its own lock_level, that's the gate
        if self.lock_level:
            from edof.crypto.permissions import Permission, can
            try:
                return can(doc.permission_level,
                           Permission.from_string(self.lock_level))
            except ValueError:
                return True   # malformed lock_level — fail open
        # No per-object lock; rely on doc-level "edit" permission
        from edof.crypto import EDIT
        return doc.can(EDIT)

    def can_modify_text(self, doc) -> bool:
        """Return True if this object's text/runs can be modified."""
        if self.lock_text:
            return False
        return self.can_modify(doc)


# ── TextBox ───────────────────────────────────────────────────────────────────

@dataclass
class TextBox(EdofObject):
    text:          str                = ""
    style:         TextStyle          = field(default_factory=TextStyle)
    runs:          List["TextRun"]    = field(default_factory=list)   # v4.0: rich text
    padding:       float              = 2.0         # mm, all sides
    padding_left:  Optional[float]    = None
    padding_right: Optional[float]    = None
    padding_top:   Optional[float]    = None
    padding_bot:   Optional[float]    = None
    border:        Optional[StrokeStyle] = None
    fill:          FillStyle          = field(
                       default_factory=lambda: FillStyle(color=None))

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "textbox")

    def get_resolved_text(self, var_store=None) -> str:
        """
        Return text after variable substitution.

        Two substitution mechanisms:
          1. If `obj.variable` is set, the value of that variable replaces the text entirely.
          2. Otherwise, `{name}` placeholders inside `obj.text` are substituted with
             corresponding variable values.

        v4.0.2: bug fix — placeholder substitution now actually happens at render time.
        Previously {name} placeholders were only resolved by repeat_objects(), but
        plain rendering left them as literals.
        """
        if self.variable and var_store:
            val = var_store.get(self.variable)
            if val is not None and str(val) != "":
                return str(val)
        # v4.0.2: substitute {name} placeholders in the static text
        text = self.text
        if var_store and "{" in text:
            try:
                # Build a fresh dict with stringified values; missing vars stay as
                # literal "{name}" via a custom mapping.
                class _SafeDict(dict):
                    def __missing__(self, key):
                        return "{" + key + "}"
                vals = _SafeDict()
                for n in var_store.names():
                    v = var_store.get(n)
                    vals[n] = "" if v is None else str(v)
                text = text.format_map(vals)
            except (KeyError, IndexError, ValueError):
                pass  # leave text alone on any formatting error
        return text

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "text":          self.text,
            "style":         self.style.to_dict(),
            "runs":          [r.to_dict() for r in self.runs] if self.runs else [],
            "padding":       self.padding,
            "padding_left":  self.padding_left,
            "padding_right": self.padding_right,
            "padding_top":   self.padding_top,
            "padding_bot":   self.padding_bot,
            "border":        self.border.to_dict() if self.border else None,
            "fill":          self.fill.to_dict(),
        })
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "TextBox":
        base: TextBox = EdofObject._from_dict.__func__(cls, d)
        base.text          = d.get("text", "")
        base.style         = TextStyle.from_dict(d.get("style", {}))
        from edof.format.styles import TextRun
        base.runs          = [TextRun.from_dict(r) for r in d.get("runs", [])]
        base.padding       = float(d.get("padding", 2.0))
        base.padding_left  = d.get("padding_left")
        base.padding_right = d.get("padding_right")
        base.padding_top   = d.get("padding_top")
        base.padding_bot   = d.get("padding_bot")
        bd = d.get("border")
        base.border        = StrokeStyle.from_dict(bd) if bd else None
        base.fill          = FillStyle.from_dict(d.get("fill", {"color": None}))
        object.__setattr__(base, "OBJECT_TYPE", "textbox")
        return base


# ── ImageBox ──────────────────────────────────────────────────────────────────

@dataclass
class ImageBox(EdofObject):
    resource_id:   Optional[str]      = None
    fit_mode:      str                = "stretch"   # contain|cover|fill|stretch|none (v4.0.3 default changed)
    border:        Optional[StrokeStyle] = None
    corner_radius: float              = 0.0         # mm

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "imagebox")

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "resource_id":   self.resource_id,
            "fit_mode":      self.fit_mode,
            "border":        self.border.to_dict() if self.border else None,
            "corner_radius": self.corner_radius,
        })
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "ImageBox":
        base: ImageBox = EdofObject._from_dict.__func__(cls, d)
        base.resource_id   = d.get("resource_id")
        base.fit_mode      = d.get("fit_mode", "stretch")
        bd = d.get("border")
        base.border        = StrokeStyle.from_dict(bd) if bd else None
        base.corner_radius = float(d.get("corner_radius", 0.0))
        object.__setattr__(base, "OBJECT_TYPE", "imagebox")
        return base


# ── Shape ─────────────────────────────────────────────────────────────────────

SHAPE_RECT    = "rect"
SHAPE_ELLIPSE = "ellipse"
SHAPE_LINE    = "line"
SHAPE_POLYGON = "polygon"
SHAPE_ARROW   = "arrow"
SHAPE_PATH    = "path"     # v4.0: SVG-style Bezier path


@dataclass
class Shape(EdofObject):
    shape_type:    str         = SHAPE_RECT
    fill:          FillStyle   = field(default_factory=FillStyle)
    stroke:        StrokeStyle = field(default_factory=StrokeStyle)
    corner_radius: float       = 0.0
    # Relative points for POLYGON / LINE (mm, relative to transform origin)
    points:        List[Any]   = field(default_factory=list)
    # v4.0: SVG-style path data when shape_type == SHAPE_PATH
    # Format: [["M", 10.0, 20.0], ["L", 30.0, 40.0], ["C", x1, y1, x2, y2, x, y], ["Z"]]
    path_data:     List[Any]   = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "shape")

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "shape_type":    self.shape_type,
            "fill":          self.fill.to_dict(),
            "stroke":        self.stroke.to_dict(),
            "corner_radius": self.corner_radius,
            "points":        self.points,
            "path_data":     self.path_data,
        })
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "Shape":
        base: Shape = EdofObject._from_dict.__func__(cls, d)
        base.shape_type    = d.get("shape_type", SHAPE_RECT)
        base.fill          = FillStyle.from_dict(d.get("fill", {}))
        base.stroke        = StrokeStyle.from_dict(d.get("stroke", {}))
        base.corner_radius = float(d.get("corner_radius", 0.0))
        base.points        = list(d.get("points", []))
        base.path_data     = list(d.get("path_data", []))
        object.__setattr__(base, "OBJECT_TYPE", "shape")
        return base

    @classmethod
    def from_svg_path(cls, d_attr: str) -> "Shape":
        """v4.0: Create a Shape with shape_type='path' from an SVG path 'd' string.

        Supports M, L, H, V, C, Q, Z (absolute and relative).
        Coordinates are in mm, relative to the shape's transform origin.
        """
        sh = cls(shape_type=SHAPE_PATH)
        sh.path_data = _parse_svg_path(d_attr)
        return sh


# ── SVG path parser ───────────────────────────────────────────────────────────

def _parse_svg_path(d: str) -> list:
    """Parse SVG path 'd' attribute into a list of [cmd, *args] commands.
    Output uses absolute coordinates only.
    """
    import re
    tokens = re.findall(r"[MmLlHhVvCcQqZz]|-?\d*\.?\d+(?:[eE][+-]?\d+)?", d)
    out, i, cur_x, cur_y, start_x, start_y = [], 0, 0.0, 0.0, 0.0, 0.0
    last_cmd = None
    while i < len(tokens):
        tok = tokens[i]
        if tok in "MmLlHhVvCcQqZz":
            cmd = tok; i += 1
        else:
            cmd = last_cmd or "L"
        rel = cmd.islower()
        c = cmd.upper()
        try:
            if c == "M":
                x = float(tokens[i]); y = float(tokens[i+1]); i += 2
                if rel: x += cur_x; y += cur_y
                out.append(["M", x, y])
                cur_x, cur_y = x, y
                start_x, start_y = x, y
                last_cmd = "L" if rel else "L"   # subsequent coords as L
            elif c == "L":
                x = float(tokens[i]); y = float(tokens[i+1]); i += 2
                if rel: x += cur_x; y += cur_y
                out.append(["L", x, y])
                cur_x, cur_y = x, y; last_cmd = cmd
            elif c == "H":
                x = float(tokens[i]); i += 1
                if rel: x += cur_x
                out.append(["L", x, cur_y]); cur_x = x; last_cmd = cmd
            elif c == "V":
                y = float(tokens[i]); i += 1
                if rel: y += cur_y
                out.append(["L", cur_x, y]); cur_y = y; last_cmd = cmd
            elif c == "C":
                x1 = float(tokens[i]);   y1 = float(tokens[i+1])
                x2 = float(tokens[i+2]); y2 = float(tokens[i+3])
                x  = float(tokens[i+4]); y  = float(tokens[i+5]); i += 6
                if rel:
                    x1 += cur_x; y1 += cur_y; x2 += cur_x; y2 += cur_y
                    x += cur_x; y += cur_y
                out.append(["C", x1, y1, x2, y2, x, y])
                cur_x, cur_y = x, y; last_cmd = cmd
            elif c == "Q":
                x1 = float(tokens[i]); y1 = float(tokens[i+1])
                x  = float(tokens[i+2]); y = float(tokens[i+3]); i += 4
                if rel:
                    x1 += cur_x; y1 += cur_y; x += cur_x; y += cur_y
                out.append(["Q", x1, y1, x, y])
                cur_x, cur_y = x, y; last_cmd = cmd
            elif c == "Z":
                out.append(["Z"])
                cur_x, cur_y = start_x, start_y
                last_cmd = cmd
            else:
                i += 1
        except (IndexError, ValueError):
            break
    return out


# ── QRCode ────────────────────────────────────────────────────────────────────

@dataclass
class QRCode(EdofObject):
    data:             str   = ""
    error_correction: str   = "M"               # L|M|Q|H
    border_modules:   int   = 4                 # quiet-zone width in modules
    fg_color:         tuple = (0, 0, 0)
    bg_color:         tuple = (255, 255, 255)

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "qrcode")

    def get_resolved_data(self, var_store=None) -> str:
        if self.variable and var_store:
            val = var_store.get(self.variable)
            if val is not None:
                return str(val)
        return self.data

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "data":             self.data,
            "error_correction": self.error_correction,
            "border_modules":   self.border_modules,
            "fg_color":         list(self.fg_color),
            "bg_color":         list(self.bg_color),
        })
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "QRCode":
        base: QRCode = EdofObject._from_dict.__func__(cls, d)
        base.data             = d.get("data", "")
        base.error_correction = d.get("error_correction", "M")
        base.border_modules   = int(d.get("border_modules", 4))
        base.fg_color         = tuple(d.get("fg_color", [0, 0, 0]))
        base.bg_color         = tuple(d.get("bg_color", [255, 255, 255]))
        object.__setattr__(base, "OBJECT_TYPE", "qrcode")
        return base


# ── Group ─────────────────────────────────────────────────────────────────────

@dataclass
class Group(EdofObject):
    children: List[EdofObject] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "group")

    def add(self, obj: EdofObject) -> EdofObject:
        self.children.append(obj)
        return obj

    def remove_by_id(self, obj_id: str) -> bool:
        before = len(self.children)
        self.children = [o for o in self.children if o.id != obj_id]
        return len(self.children) < before

    def flatten(self) -> List[EdofObject]:
        out: List[EdofObject] = []
        for child in self.children:
            if isinstance(child, Group):
                out.extend(child.flatten())
            else:
                out.append(child)
        return out

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "Group":
        base: Group = EdofObject._from_dict.__func__(cls, d)
        base.children = [EdofObject.from_dict(c) for c in d.get("children", [])]
        object.__setattr__(base, "OBJECT_TYPE", "group")
        return base


# ══════════════════════════════════════════════════════════════════════════════
#  v4.0  Table  —  formatted table with per-cell styling
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CellBorder:
    """Per-side border of a TableCell."""
    color: tuple = (180, 180, 180, 255)
    width: float = 0.3            # mm
    enabled: bool = True

    def to_dict(self) -> dict:
        from edof.format.styles import _rgba_to_hex
        return {"color": _rgba_to_hex(self.color),
                "width": self.width, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> "CellBorder":
        from edof.format.styles import _hex_to_rgba
        b = cls()
        c = d.get("color")
        if isinstance(c, str): b.color = _hex_to_rgba(c)
        elif c is not None:    b.color = tuple(c)
        b.width   = float(d.get("width", 0.3))
        b.enabled = bool(d.get("enabled", True))
        return b


@dataclass
class TableCell:
    """A single cell in a Table. Supports rich text via runs."""
    text:      str            = ""
    runs:      List[Any]      = field(default_factory=list)   # List[TextRun]
    style:     TextStyle      = field(default_factory=TextStyle)
    bg_color:  tuple          = (255, 255, 255, 0)            # RGBA, alpha=0 = transparent
    padding:   float          = 1.5                           # mm
    border_top:    CellBorder = field(default_factory=CellBorder)
    border_right:  CellBorder = field(default_factory=CellBorder)
    border_bottom: CellBorder = field(default_factory=CellBorder)
    border_left:   CellBorder = field(default_factory=CellBorder)
    colspan:   int            = 1
    rowspan:   int            = 1

    def to_dict(self) -> dict:
        from edof.format.styles import _rgba_to_hex
        return {
            "text":          self.text,
            "runs":          [r.to_dict() for r in self.runs],
            "style":         self.style.to_dict(),
            "bg_color":      _rgba_to_hex(self.bg_color),
            "padding":       self.padding,
            "border_top":    self.border_top.to_dict(),
            "border_right":  self.border_right.to_dict(),
            "border_bottom": self.border_bottom.to_dict(),
            "border_left":   self.border_left.to_dict(),
            "colspan":       self.colspan,
            "rowspan":       self.rowspan,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TableCell":
        from edof.format.styles import TextStyle, TextRun, _hex_to_rgba
        c = cls()
        c.text     = d.get("text", "")
        c.runs     = [TextRun.from_dict(r) for r in d.get("runs", [])]
        c.style    = TextStyle.from_dict(d.get("style", {}))
        bg = d.get("bg_color")
        c.bg_color = _hex_to_rgba(bg) if isinstance(bg, str) else tuple(bg) if bg else (255,255,255,0)
        c.padding  = float(d.get("padding", 1.5))
        c.border_top    = CellBorder.from_dict(d.get("border_top", {}))
        c.border_right  = CellBorder.from_dict(d.get("border_right", {}))
        c.border_bottom = CellBorder.from_dict(d.get("border_bottom", {}))
        c.border_left   = CellBorder.from_dict(d.get("border_left", {}))
        c.colspan = int(d.get("colspan", 1))
        c.rowspan = int(d.get("rowspan", 1))
        return c


@dataclass
class Table(EdofObject):
    """v4.0: Formatted table with per-cell styling.

    cells is a 2D grid: cells[row_index][col_index].
    Set row_heights or col_widths to 0 to auto-distribute.
    """
    cells:        List[List[Any]] = field(default_factory=list)   # List[List[TableCell]]
    row_heights:  List[float]     = field(default_factory=list)   # mm; 0 = auto
    col_widths:   List[float]     = field(default_factory=list)   # mm; 0 = auto
    table_border: Optional[StrokeStyle] = None    # outer border around whole table

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "table")

    @property
    def num_rows(self) -> int: return len(self.cells)
    @property
    def num_cols(self) -> int: return len(self.cells[0]) if self.cells else 0

    def get_cell(self, row: int, col: int) -> Optional[TableCell]:
        if 0 <= row < self.num_rows and 0 <= col < self.num_cols:
            return self.cells[row][col]
        return None

    def set_cell(self, row: int, col: int, cell: TableCell) -> None:
        if 0 <= row < self.num_rows and 0 <= col < self.num_cols:
            self.cells[row][col] = cell

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "cells":        [[c.to_dict() for c in row] for row in self.cells],
            "row_heights":  self.row_heights,
            "col_widths":   self.col_widths,
            "table_border": self.table_border.to_dict() if self.table_border else None,
        })
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "Table":
        base: Table = EdofObject._from_dict.__func__(cls, d)
        base.cells       = [[TableCell.from_dict(c) for c in row]
                             for row in d.get("cells", [])]
        base.row_heights = list(d.get("row_heights", []))
        base.col_widths  = list(d.get("col_widths", []))
        tb = d.get("table_border")
        base.table_border = StrokeStyle.from_dict(tb) if tb else None
        object.__setattr__(base, "OBJECT_TYPE", "table")
        return base


# Helper: build a table with simple row data
def make_table(rows: List[List[str]],
               header: bool = True,
               header_bg=(83, 74, 183, 255),
               header_color=(255, 255, 255),
               alt_bg=(245, 245, 252, 255),
               alternating: bool = True) -> Table:
    """Quick helper to build a Table from list-of-lists."""
    t = Table()
    n_cols = max(len(r) for r in rows) if rows else 0
    for ri, row in enumerate(rows):
        cells = []
        for ci in range(n_cols):
            cell = TableCell(text=str(row[ci]) if ci < len(row) else "")
            if header and ri == 0:
                cell.bg_color = header_bg
                cell.style.color = header_color[:3]
                cell.style.bold = True
            elif alternating and ri % 2 == 0:
                cell.bg_color = alt_bg
            cells.append(cell)
        t.cells.append(cells)
    return t
