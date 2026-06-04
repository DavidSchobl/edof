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
    """v4.1.17: ALL length fields are in millimetres (mm), the canonical
    unit of EDOF. Typography users can interact with pt via the
    `font_size_pt` / `letter_spacing_pt` accessors below — but on-disk
    and in-memory the canonical unit is mm.

    Reference: 12 pt ≈ 4.233 mm; 1 pt = 25.4/72 mm.
    """
    font_family:     str            = "Arial"
    font_size:       float          = 4.233   # mm (= 12 pt)
    bold:            bool           = False
    italic:          bool           = False
    underline:       bool           = False
    strikethrough:   bool           = False
    color:           Color          = (0, 0, 0)
    background:      Optional[Color]= None
    letter_spacing:  float          = 0.0           # mm extra between glyphs
    line_height:     float          = 1.2           # unit-less multiplier
    alignment:       str            = "left"        # left|center|right|justify|justify_full
    justify_mode:    str            = "space"       # 'space' | 'full' (see text_layout)
    vertical_align:  str            = "top"         # top|middle|bottom
    auto_shrink:     bool           = False
    auto_fill:       bool           = False
    min_font_size:   float          = 1.411   # mm (= 4 pt)
    max_font_size:   float          = 70.555  # mm (= 200 pt)
    wrap:            bool           = True
    overflow_hidden: bool           = False
    padding:         float          = 1.0   # mm
    padding_top:     Optional[float] = None
    padding_right:   Optional[float] = None
    padding_bottom:  Optional[float] = None
    padding_left:    Optional[float] = None
    # v4.1.16.7: non-uniform glyph deformation
    glyph_scale_x:   float          = 1.0
    glyph_scale_y:   float          = 1.0

    # ── v4.1.17: pt accessors as convenience for typography users ────────────
    # The canonical unit is mm; these properties convert in/out of pt for
    # legacy code, app integrations (e.g. DOCX export), and humans who
    # think in points.
    @property
    def font_size_pt(self) -> float:
        return self.font_size * 72.0 / 25.4

    @font_size_pt.setter
    def font_size_pt(self, pt: float) -> None:
        self.font_size = float(pt) * 25.4 / 72.0

    # mm accessor is just an alias — for code that wants explicit naming
    @property
    def font_size_mm(self) -> float:
        return self.font_size

    @font_size_mm.setter
    def font_size_mm(self, mm: float) -> None:
        self.font_size = float(mm)

    @property
    def letter_spacing_pt(self) -> float:
        return self.letter_spacing * 72.0 / 25.4

    @letter_spacing_pt.setter
    def letter_spacing_pt(self, pt: float) -> None:
        self.letter_spacing = float(pt) * 25.4 / 72.0

    @property
    def letter_spacing_mm(self) -> float:
        return self.letter_spacing

    @letter_spacing_mm.setter
    def letter_spacing_mm(self, mm: float) -> None:
        self.letter_spacing = float(mm)

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
            "justify_mode":   self.justify_mode,
            "auto_shrink":    self.auto_shrink,
            "auto_fill":      self.auto_fill,
            "min_font_size":  self.min_font_size,
            "max_font_size":  self.max_font_size,
            "wrap":           self.wrap,
            "overflow_hidden":self.overflow_hidden,
            "padding":        self.padding,
            "padding_top":    self.padding_top,
            "padding_right":  self.padding_right,
            "padding_bottom": self.padding_bottom,
            "padding_left":   self.padding_left,
            "glyph_scale_x":  self.glyph_scale_x,
            "glyph_scale_y":  self.glyph_scale_y,
        }

    def get_padding(self):
        """v4.1.0: Return (top, right, bottom, left) in mm.
        Per-side fields override the uniform `padding` if set.
        """
        p = self.padding
        return (
            self.padding_top    if self.padding_top    is not None else p,
            self.padding_right  if self.padding_right  is not None else p,
            self.padding_bottom if self.padding_bottom is not None else p,
            self.padding_left   if self.padding_left   is not None else p,
        )

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
    """v4.1.17: width is in millimetres (mm), canonical EDOF unit.
    Use `width_pt` property for typography pt access (1 pt ≈ 0.353 mm)."""
    color: Color = (0, 0, 0)
    width: float = 0.353        # mm (= 1 pt)
    dash:  list  = field(default_factory=list)   # e.g. [6, 3]
    cap:   str   = "butt"       # butt|round|square
    join:  str   = "miter"      # miter|round|bevel

    @property
    def width_pt(self) -> float:
        return self.width * 72.0 / 25.4

    @width_pt.setter
    def width_pt(self, pt: float) -> None:
        self.width = float(pt) * 25.4 / 72.0

    @property
    def width_mm(self) -> float:
        return self.width

    @width_mm.setter
    def width_mm(self, mm: float) -> None:
        self.width = float(mm)

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

    v4.1.17: font_size is in millimetres (mm), the canonical EDOF unit.
    Use the `font_size_pt` property for typography-style pt values.

    Any field set to None inherits from the parent TextStyle.
    """
    text:           str                 = ""
    font_family:    Optional[str]       = None
    font_size:      Optional[float]     = None      # mm (None = inherit)
    bold:           Optional[bool]      = None
    italic:         Optional[bool]      = None
    underline:      Optional[bool]      = None
    strikethrough:  Optional[bool]      = None
    color:          Optional[Color]     = None
    background:     Optional[Color]     = None    # highlight color, RGBA
    # v4.1.23.33: per-run vertical line spacing (unit-less multiplier) and
    # horizontal letter spacing (mm of extra advance after each glyph).
    # None = inherit from the parent TextStyle. These make spacing a run
    # attribute like font size: a span of text keeps the spacing it was
    # typed with until a different value is set, and a line's height is the
    # max over the runs on it of (font_size * line_height).
    line_height:    Optional[float]     = None
    letter_spacing: Optional[float]     = None
    # v4.1.20.10: per-paragraph alignment. The layout engine reads this
    # for the paragraph containing each run — runs within a single
    # paragraph (= group separated by '\n') should all carry the same
    # value (the editor's set_alignment sets all runs in the current
    # paragraph together). None = inherit from parent TextStyle.alignment.
    alignment:      Optional[str]       = None    # 'left'|'center'|'right'|'justify'

    # v4.1.17: pt accessor (legacy / typography integration)
    @property
    def font_size_pt(self) -> Optional[float]:
        if self.font_size is None: return None
        return self.font_size * 72.0 / 25.4

    @font_size_pt.setter
    def font_size_pt(self, pt: Optional[float]) -> None:
        self.font_size = (float(pt) * 25.4 / 72.0) if pt is not None else None

    # mm alias for clarity
    @property
    def font_size_mm(self) -> Optional[float]:
        return self.font_size

    @font_size_mm.setter
    def font_size_mm(self, mm: Optional[float]) -> None:
        self.font_size = float(mm) if mm is not None else None

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
            "line_height":   self.line_height    if self.line_height    is not None else getattr(parent, 'line_height', 1.2),
            "letter_spacing": (self.letter_spacing if self.letter_spacing is not None else getattr(parent, 'letter_spacing', 0.0)) * scale,
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
        if self.line_height   is not None: d["line_height"]   = self.line_height
        if self.letter_spacing is not None: d["letter_spacing"] = self.letter_spacing
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TextRun":
        r = cls(text=d.get("text", ""))
        for k in ("font_family", "font_size", "bold", "italic",
                  "underline", "strikethrough", "line_height", "letter_spacing"):
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


# v4.1.0: Photoshop-style layer effects
@dataclass
class LayerEffect:
    """A Photoshop-style layer effect.

    type: one of 'drop_shadow', 'inner_shadow', 'outer_glow', 'inner_glow',
                 'bevel', 'stroke', 'color_overlay', 'gradient_overlay'
    """
    type: str = "drop_shadow"
    enabled: bool = True
    color: Color = (0, 0, 0, 200)
    color2: Color = (255, 255, 255, 200)   # for bevel highlight, gradient end
    blend_mode: str = "normal"
    blend_mode2: str = "normal"            # for bevel highlight blend
    opacity: float = 1.0                    # 0..1
    size: float = 2.0                       # mm — blur/glow radius, bevel size
    distance: float = 2.0                   # mm — shadow offset, used with direction
    direction: float = 135.0                # degrees, 0=right, 90=up, etc.
    # Stroke-specific
    stroke_position: str = "outside"        # outside | center | inside
    # Bevel-specific
    bevel_kind: str = "outer"               # outer | inner | smooth
    # Gradient-specific
    gradient_start: Color = (0, 0, 0, 255)
    gradient_end: Color = (255, 255, 255, 255)
    gradient_angle: float = 90.0
    # v4.1.1: Texture overlay
    texture_path:    Optional[str]   = None      # external file path
    texture_scale:   float           = 100.0     # %, relative to object size
    texture_data:    Optional[bytes] = None      # embedded bytes
    texture_fit:     str             = "tile"    # tile | fit | fill | stretch
    texture_anchor:  str             = "top-left"  # top-left | center

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "enabled": self.enabled,
            "color": _rgba_to_hex(self.color),
            "color2": _rgba_to_hex(self.color2),
            "blend_mode": self.blend_mode,
            "blend_mode2": self.blend_mode2,
            "opacity": self.opacity,
            "size": self.size,
            "distance": self.distance,
            "direction": self.direction,
            "stroke_position": self.stroke_position,
            "bevel_kind": self.bevel_kind,
            "gradient_start": _rgba_to_hex(self.gradient_start),
            "gradient_end": _rgba_to_hex(self.gradient_end),
            "gradient_angle": self.gradient_angle,
            "texture_path": self.texture_path,
            "texture_scale": self.texture_scale,
            "texture_fit": self.texture_fit,
            "texture_anchor": self.texture_anchor,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LayerEffect":
        obj = cls()
        color_keys = {"color", "color2", "gradient_start", "gradient_end"}
        for k, v in d.items():
            if k in color_keys and isinstance(v, str):
                v = _hex_to_rgba(v)
            if k == "texture_data": continue  # not serialized
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj
