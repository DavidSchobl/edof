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
        return obj

    def copy(self) -> "EdofObject":
        c    = copy.deepcopy(self)
        c.id = _new_id()
        return c

    def __post_init__(self) -> None:
        # Allow subclasses to set OBJECT_TYPE as a plain class attribute
        pass


# ── TextBox ───────────────────────────────────────────────────────────────────

@dataclass
class TextBox(EdofObject):
    text:          str                = ""
    style:         TextStyle          = field(default_factory=TextStyle)
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
        Falls back to obj.text if the variable is not set or empty,
        so the editor always shows meaningful content.
        """
        if self.variable and var_store:
            val = var_store.get(self.variable)
            if val is not None and str(val) != "":
                return str(val)
        return self.text

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "text":          self.text,
            "style":         self.style.to_dict(),
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
    fit_mode:      str                = "contain"   # contain|cover|fill|stretch|none
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
        base.fit_mode      = d.get("fit_mode", "contain")
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


@dataclass
class Shape(EdofObject):
    shape_type:    str         = SHAPE_RECT
    fill:          FillStyle   = field(default_factory=FillStyle)
    stroke:        StrokeStyle = field(default_factory=StrokeStyle)
    corner_radius: float       = 0.0
    # Relative points for POLYGON / LINE (mm, relative to transform origin)
    points:        List[Any]   = field(default_factory=list)

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
        object.__setattr__(base, "OBJECT_TYPE", "shape")
        return base


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
