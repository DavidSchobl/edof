# edof/format/styles.py
"""
Style dataclasses: TextStyle, StrokeStyle, FillStyle, ShadowStyle.
Colours are stored as (R,G,B) or (R,G,B,A) tuples, values 0-255.
"""

from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Optional, Tuple

Color = Tuple[int, ...]


# ── Colour helpers ────────────────────────────────────────────────────────────

def _hex_to_rgba(h: str) -> Color:
    h = h.lstrip("#")
    if len(h) == 6:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    if len(h) == 8:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
    raise ValueError(f"Invalid colour hex: {h!r}")


def _rgba_to_hex(c: Color) -> str:
    return "#" + "".join(f"{v:02x}" for v in c)


def as_color(value) -> Color:
    """Accept hex string, tuple, or list → normalised Color tuple."""
    if isinstance(value, str):
        return _hex_to_rgba(value)
    return tuple(int(v) for v in value)


# ── TextStyle ─────────────────────────────────────────────────────────────────

@dataclass
class TextStyle:
    font_family:     str            = "Arial"
    font_size:       float          = 12.0          # pt
    bold:            bool           = False
    italic:          bool           = False
    underline:       bool           = False
    strikethrough:   bool           = False
    color:           Color          = (0, 0, 0)
    background:      Optional[Color]= None
    letter_spacing:  float          = 0.0           # pt extra between glyphs
    line_height:     float          = 1.2           # multiplier of font_size
    alignment:       str            = "left"        # left|center|right|justify
    vertical_align:  str            = "top"         # top|middle|bottom
    # Auto-shrink: reduce font_size until text fits the box
    auto_shrink:     bool           = False
    auto_fill:       bool           = False   # grows AND shrinks to fill the box
    min_font_size:   float          = 4.0
    max_font_size:   float          = 200.0
    wrap:            bool           = True
    overflow_hidden: bool           = True
    padding:         float          = 1.0   # mm – space between box edge and text

    def to_dict(self) -> dict:
        return {
            "font_family":    self.font_family,
            "font_size":      self.font_size,
            "bold":           self.bold,
            "italic":         self.italic,
            "underline":      self.underline,
            "strikethrough":  self.strikethrough,
            "color":          _rgba_to_hex(self.color),
            "background":     _rgba_to_hex(self.background) if self.background else None,
            "letter_spacing": self.letter_spacing,
            "line_height":    self.line_height,
            "alignment":      self.alignment,
            "vertical_align": self.vertical_align,
            "auto_shrink":    self.auto_shrink,
            "auto_fill":      self.auto_fill,
            "min_font_size":  self.min_font_size,
            "max_font_size":  self.max_font_size,
            "wrap":           self.wrap,
            "overflow_hidden":self.overflow_hidden,
            "padding":        self.padding,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TextStyle":
        obj = cls()
        for k, v in d.items():
            if k in ("color", "background") and isinstance(v, str) and v:
                v = _hex_to_rgba(v)
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj

    def copy(self) -> "TextStyle":
        return copy.deepcopy(self)


# ── StrokeStyle ───────────────────────────────────────────────────────────────

@dataclass
class StrokeStyle:
    color: Color = (0, 0, 0)
    width: float = 1.0          # pt
    dash:  list  = field(default_factory=list)   # e.g. [6, 3]
    cap:   str   = "butt"       # butt|round|square
    join:  str   = "miter"      # miter|round|bevel

    def to_dict(self) -> dict:
        return {
            "color": _rgba_to_hex(self.color),
            "width": self.width,
            "dash":  self.dash,
            "cap":   self.cap,
            "join":  self.join,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StrokeStyle":
        obj = cls()
        for k, v in d.items():
            if k == "color" and isinstance(v, str):
                v = _hex_to_rgba(v)
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj



# ── Gradient (v4.0) ───────────────────────────────────────────────────────────

@dataclass
class Gradient:
    """Multi-stop gradient for FillStyle. v4.0 feature."""
    type:   str   = "linear"     # "linear" | "radial"
    angle:  float = 0.0          # degrees, for linear (0=left-to-right)
    center: tuple = (0.5, 0.5)   # normalized (0-1), for radial
    radius: float = 0.5          # normalized, for radial
    stops:  list  = field(default_factory=list)
    # stops format: [(offset_0_to_1, (r,g,b,a)), ...]

    def to_dict(self) -> dict:
        return {
            "type":   self.type,
            "angle":  self.angle,
            "center": list(self.center),
            "radius": self.radius,
            "stops":  [[off, _rgba_to_hex(c)] for off, c in self.stops],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Gradient":
        g = cls()
        g.type   = d.get("type", "linear")
        g.angle  = float(d.get("angle", 0))
        g.center = tuple(d.get("center", (0.5, 0.5)))
        g.radius = float(d.get("radius", 0.5))
        g.stops  = [(float(off), _hex_to_rgba(c) if isinstance(c, str) else c)
                    for off, c in d.get("stops", [])]
        return g


# ── TextRun (v4.0 rich text) ──────────────────────────────────────────────────

@dataclass
class TextRun:
    """A styled segment of text within a TextBox.runs list. v4.0 feature.

    Any field set to None inherits from the parent TextStyle.
    """
    text:           str                 = ""
    font_family:    Optional[str]       = None
    font_size:      Optional[float]     = None
    bold:           Optional[bool]      = None
    italic:         Optional[bool]      = None
    underline:      Optional[bool]      = None
    strikethrough:  Optional[bool]      = None
    color:          Optional[Color]     = None
    background:     Optional[Color]     = None    # highlight color, RGBA

    def resolve(self, parent: "TextStyle", scale: float = 1.0) -> dict:
        """Return effective style dict for rendering this run.
        scale multiplies font_size for auto-shrink/fill."""
        return {
            "font_family":   self.font_family    or parent.font_family,
            "font_size":     (self.font_size if self.font_size is not None else parent.font_size) * scale,
            "bold":          self.bold           if self.bold          is not None else parent.bold,
            "italic":        self.italic         if self.italic        is not None else parent.italic,
            "underline":     self.underline      if self.underline     is not None else parent.underline,
            "strikethrough": self.strikethrough  if self.strikethrough is not None else parent.strikethrough,
            "color":         self.color          if self.color         is not None else parent.color,
            "background":    self.background,    # None means transparent
        }

    def to_dict(self) -> dict:
        d = {"text": self.text}
        if self.font_family   is not None: d["font_family"]   = self.font_family
        if self.font_size     is not None: d["font_size"]     = self.font_size
        if self.bold          is not None: d["bold"]          = self.bold
        if self.italic        is not None: d["italic"]        = self.italic
        if self.underline     is not None: d["underline"]     = self.underline
        if self.strikethrough is not None: d["strikethrough"] = self.strikethrough
        if self.color         is not None: d["color"]         = _rgba_to_hex(self.color)
        if self.background    is not None: d["background"]    = _rgba_to_hex(self.background)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TextRun":
        r = cls(text=d.get("text", ""))
        for k in ("font_family", "font_size", "bold", "italic",
                  "underline", "strikethrough"):
            if k in d: setattr(r, k, d[k])
        for k in ("color", "background"):
            if k in d:
                v = d[k]
                setattr(r, k, _hex_to_rgba(v) if isinstance(v, str) else v)
        return r


# ── FillStyle ─────────────────────────────────────────────────────────────────

@dataclass
class FillStyle:
    color:    Optional[Color]    = (255, 255, 255)
    opacity:  float              = 1.0              # 0.0–1.0
    gradient: Optional[Gradient] = None              # v4.0: if set, takes precedence over color

    def to_dict(self) -> dict:
        d = {
            "color":   _rgba_to_hex(self.color) if self.color else None,
            "opacity": self.opacity,
        }
        if self.gradient is not None:
            d["gradient"] = self.gradient.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FillStyle":
        obj = cls()
        c = d.get("color")
        obj.color   = _hex_to_rgba(c) if isinstance(c, str) and c else None
        obj.opacity = float(d.get("opacity", 1.0))
        g = d.get("gradient")
        if isinstance(g, dict):
            obj.gradient = Gradient.from_dict(g)
        return obj


# ── ShadowStyle ───────────────────────────────────────────────────────────────

@dataclass
class ShadowStyle:
    enabled:  bool  = False
    color:    Color = (0, 0, 0, 128)
    offset_x: float = 2.0       # mm
    offset_y: float = 2.0       # mm
    blur:     float = 4.0       # mm

    def to_dict(self) -> dict:
        return {
            "enabled":  self.enabled,
            "color":    _rgba_to_hex(self.color),
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "blur":     self.blur,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ShadowStyle":
        obj = cls()
        for k, v in d.items():
            if k == "color" and isinstance(v, str):
                v = _hex_to_rgba(v)
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj
