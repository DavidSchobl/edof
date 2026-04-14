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


# ── FillStyle ─────────────────────────────────────────────────────────────────

@dataclass
class FillStyle:
    color:   Optional[Color] = (255, 255, 255)
    opacity: float           = 1.0              # 0.0–1.0

    def to_dict(self) -> dict:
        return {
            "color":   _rgba_to_hex(self.color) if self.color else None,
            "opacity": self.opacity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FillStyle":
        obj = cls()
        c = d.get("color")
        obj.color   = _hex_to_rgba(c) if isinstance(c, str) and c else None
        obj.opacity = float(d.get("opacity", 1.0))
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
