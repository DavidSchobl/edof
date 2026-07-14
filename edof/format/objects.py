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
from typing import Any, List, Optional, Dict

from edof.engine.transform import Transform
from edof.format.styles import (
    TextStyle, StrokeStyle, BorderStyle, FillStyle, ShadowStyle,
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
    # v4.1.1: Photoshop-style fill opacity — affects the object pixels but
    # NOT layer effects (drop shadow, glow, stroke etc still render at full
    # alpha). When equal to opacity, behaves like a single opacity field.
    fill_opacity: float          = 1.0
    # v4.1.0: Photoshop-style layer effects (list of LayerEffect)
    effects:   List["LayerEffect"] = field(default_factory=list)
    # v4.3.5.12: master "All effects" switch. When False, NO layer effect on
    # this object renders, regardless of each effect's own 'enabled' flag -- but
    # the effects stay on the object (so they aren't lost and can be batched).
    # Exposed as the batchable attribute effects.all_enabled.
    # v4.3.5.15: defaults to False (effects off) -- adding an effect via the UI
    # turns it on. An object with no effects has nothing to show, so off is the
    # natural default; the user can switch it off explicitly to hide effects.
    effects_enabled: bool        = False
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
    # v4.1.0: position lock — object cannot be moved/resized via the editor
    # but its content (text, colors, effects) is still editable.
    lock_position: bool          = False

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
            "fill_opacity": self.fill_opacity,
            "editable":  getattr(self, "editable", True),
            "visible_if": self.visible_if,    # v4.0
            "blend_mode": self.blend_mode,    # v4.0
            "lock_level": self.lock_level,    # v4.0.1
            "lock_text":  self.lock_text,     # v4.0.1
            "lock_position": self.lock_position,   # v4.1.0
            "effects":   [e.to_dict() for e in self.effects],   # v4.1.0
            "effects_enabled": self.effects_enabled,   # v4.3.5.12
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
            "subdocument": SubDocumentBox,   # v4.1.0
            "svgbox":   SvgBox,   # v4.1.13
        }
        # v4.1.23: document-mode subclasses. Imported lazily to avoid a
        # circular import at module load time.
        try:
            from edof.format.document_boxes import (
                DocumentTextBox, DocumentHeaderBox, DocumentFooterBox)
            _cls_map["document_textbox"] = DocumentTextBox
            _cls_map["document_header"]  = DocumentHeaderBox
            _cls_map["document_footer"]  = DocumentFooterBox
        except Exception:
            pass
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
        obj.fill_opacity = float(d.get("fill_opacity", obj.opacity))  # v4.1.1
        obj.editable  = bool(d.get("editable", True))
        obj.visible_if = d.get("visible_if", "") or ""    # v4.0
        obj.blend_mode = d.get("blend_mode", "normal")    # v4.0
        obj.lock_level = d.get("lock_level", "") or ""    # v4.0.1
        obj.lock_text  = bool(d.get("lock_text", False))  # v4.0.1
        obj.lock_position = bool(d.get("lock_position", False))  # v4.1.0
        # v4.1.0: layer effects
        from edof.format.styles import LayerEffect
        obj.effects = [LayerEffect.from_dict(e) for e in d.get("effects", [])]
        # v4.3.5.15: effects_enabled defaults to False for new objects, but an
        # older file (saved before this key existed) that HAS effects expected
        # them to render -- so when the key is absent and effects are present,
        # fall back to True for backwards compatibility.
        if "effects_enabled" in d:
            obj.effects_enabled = bool(d.get("effects_enabled"))
        else:
            obj.effects_enabled = bool(obj.effects)   # legacy: on iff it has effects
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
    # v4.1.21: per-paragraph alignment overrides. Maps paragraph index
    # (counted from 0, where paragraph break = "\n" inside runs) → one of
    # 'left' | 'center' | 'right' | 'justify' | 'justify_full'. Paragraphs
    # without an entry fall back to `style.alignment`. Keyed by stringified
    # int for JSON friendliness.
    paragraph_alignments: Dict[str, str] = field(default_factory=dict)

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
            "fill":           self.fill.to_dict(),
            # v4.1.21: per-paragraph alignment overrides
            "paragraph_alignments": dict(self.paragraph_alignments) if self.paragraph_alignments else {},
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
        base.border        = (BorderStyle.from_dict(bd) if isinstance(bd, dict) and bd.get("kind") == "border" else StrokeStyle.from_dict(bd)) if bd else None
        base.fill          = FillStyle.from_dict(d.get("fill", {"color": None}))
        # v4.1.21: per-paragraph alignment overrides — normalise keys to str
        pa = d.get("paragraph_alignments") or {}
        base.paragraph_alignments = {str(k): str(v) for k, v in pa.items()}
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
        base.border        = (BorderStyle.from_dict(bd) if isinstance(bd, dict) and bd.get("kind") == "border" else StrokeStyle.from_dict(bd)) if bd else None
        base.corner_radius = float(d.get("corner_radius", 0.0))
        object.__setattr__(base, "OBJECT_TYPE", "imagebox")
        return base


# ── SvgBox (v4.1.13) ──────────────────────────────────────────────────────────

@dataclass
class SvgBox(EdofObject):
    """v4.1.13: An SVG file embedded as a rastered image. Stores the original
    SVG XML inline so loading/saving is lossless. In the editor, double-click
    offers to convert to native EDOF path shapes for editing — at that point
    the SvgBox is replaced by Shape objects and the SVG is discarded."""
    svg_xml:       str                = ""
    fit_mode:      str                = "contain"   # contain|stretch|none
    border:        Optional[StrokeStyle] = None
    corner_radius: float              = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "svgbox")

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "svg_xml":       self.svg_xml,
            "fit_mode":      self.fit_mode,
            "border":        self.border.to_dict() if self.border else None,
            "corner_radius": self.corner_radius,
        })
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "SvgBox":
        base: SvgBox = EdofObject._from_dict.__func__(cls, d)
        base.svg_xml       = d.get("svg_xml", "")
        base.fit_mode      = d.get("fit_mode", "contain")
        bd = d.get("border")
        base.border        = (BorderStyle.from_dict(bd) if isinstance(bd, dict) and bd.get("kind") == "border" else StrokeStyle.from_dict(bd)) if bd else None
        base.corner_radius = float(d.get("corner_radius", 0.0))
        object.__setattr__(base, "OBJECT_TYPE", "svgbox")
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
    # v4.2.7.1: per-corner radii [top-left, top-right, bottom-right, bottom-left]
    # in mm. Empty list = use uniform corner_radius for all four corners.
    corner_radii:  List[float] = field(default_factory=list)
    points:        List[Any]   = field(default_factory=list)
    # v4.0: SVG-style path data when shape_type == SHAPE_PATH
    # Format: [["M", 10.0, 20.0], ["L", 30.0, 40.0], ["C", x1, y1, x2, y2, x, y], ["Z"]]
    path_data:     List[Any]   = field(default_factory=list)
    # v4.1.10: per-anchor type. Parallel to path_data indices (same length).
    # Valid values: "corner" | "smooth" | "asymmetric" | "auto".
    # Affects drag behavior: corner = independent CPs, smooth = symmetric CPs,
    # asymmetric = independent (both moveable but separately), auto = CPs
    # recomputed from neighbors on each move.
    path_point_types: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "shape")

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "shape_type":    self.shape_type,
            "fill":          self.fill.to_dict(),
            "stroke":        self.stroke.to_dict(),
            "corner_radius": self.corner_radius,
            "corner_radii":  self.corner_radii,
            "points":        self.points,
            "path_data":     self.path_data,
            "path_point_types": self.path_point_types,
            # v4.3.5.48: marks that line points are stored LOCAL (relative to
            # transform), so load doesn't migrate them again.
            "_local_points": True,
        })
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "Shape":
        base: Shape = EdofObject._from_dict.__func__(cls, d)
        base.shape_type    = d.get("shape_type", SHAPE_RECT)
        base.fill          = FillStyle.from_dict(d.get("fill", {}))
        base.stroke        = StrokeStyle.from_dict(d.get("stroke", {}))
        base.corner_radius = float(d.get("corner_radius", 0.0))
        base.corner_radii  = [float(x) for x in d.get("corner_radii", [])]
        base.points        = list(d.get("points", []))
        base.path_data     = list(d.get("path_data", []))
        base.path_point_types = list(d.get("path_point_types", []))
        object.__setattr__(base, "OBJECT_TYPE", "shape")
        # v4.3.5.48: lines now store LOCAL points (relative to transform.x/y),
        # like paths, so move/resize/rotate/group/batch work through the
        # transform. Files saved before this stored ABSOLUTE points (no
        # "_local_points" flag) -> subtract the transform origin once so they
        # render in the same spot and become local going forward.
        if base.shape_type == SHAPE_LINE and len(base.points) >= 2 \
                and not d.get("_local_points", False):
            tx, ty = base.transform.x, base.transform.y
            base.points = [[p[0] - tx, p[1] - ty] for p in base.points]
        return base

    def normalize_line(self):
        """v4.3.5.48: keep a line's invariant — points are LOCAL (relative to
        transform.x/y) and the transform IS their bounding box. Call after the
        endpoints change (create / endpoint drag) so the box and points stay in
        sync, exactly like a path. World position is preserved."""
        if self.shape_type != SHAPE_LINE or len(self.points) < 2:
            return
        # current world coords of the endpoints
        wx = [p[0] + self.transform.x for p in self.points]
        wy = [p[1] + self.transform.y for p in self.points]
        minx, miny = min(wx), min(wy)
        maxx, maxy = max(wx), max(wy)
        self.transform.x = minx
        self.transform.y = miny
        self.transform.width = max(0.1, maxx - minx)
        self.transform.height = max(0.1, maxy - miny)
        # re-express points local to the new origin
        self.points = [[wxi - minx, wyi - miny] for wxi, wyi in zip(wx, wy)]

    @classmethod
    def from_svg_path(cls, d_attr: str) -> "Shape":
        """v4.0: Create a Shape with shape_type='path' from an SVG path 'd' string.

        Supports M, L, H, V, C, Q, Z (absolute and relative).

        v4.3.6.25: the transform is now derived from the path's own bounding box
        and the path is re-origined to a local (0,0), so an absolutely-positioned
        path (e.g. a heart drawn around 100,100) renders where its coordinates
        say instead of being clipped to the default 50x30 box. The visual result
        is identical whether you feed absolute or local coordinates.
        """
        sh = cls(shape_type=SHAPE_PATH)
        pd = _parse_svg_path(d_attr)
        xs, ys = [], []
        for cmd in pd:
            if not cmd:
                continue
            coords = cmd[1:]                     # (x,y) pairs for M/L/C/Q; none for Z
            for k in range(0, len(coords) - 1, 2):
                xs.append(float(coords[k])); ys.append(float(coords[k + 1]))
        if xs and ys:
            minx, miny = min(xs), min(ys)
            maxx, maxy = max(xs), max(ys)
            sh.transform.x = float(minx)
            sh.transform.y = float(miny)
            sh.transform.width = max(0.001, float(maxx - minx))
            sh.transform.height = max(0.001, float(maxy - miny))
            if abs(minx) > 1e-9 or abs(miny) > 1e-9:
                shifted = []
                for cmd in pd:
                    if not cmd:
                        shifted.append(cmd); continue
                    op = cmd[0]; coords = list(cmd[1:])
                    for k in range(0, len(coords) - 1, 2):
                        coords[k] = coords[k] - minx
                        coords[k + 1] = coords[k + 1] - miny
                    shifted.append([op] + coords)
                pd = shifted
        sh.path_data = pd
        return sh

    def to_svg_path_d(self) -> str:
        """v4.1.13: Serialize self.path_data back to SVG 'd' attribute string.
        Uses absolute coordinates only."""
        if not self.path_data: return ""
        parts = []
        for cmd in self.path_data:
            if not cmd: continue
            op = cmd[0]
            if op == "M":
                parts.append(f"M{cmd[1]:.4f} {cmd[2]:.4f}")
            elif op == "L":
                parts.append(f"L{cmd[1]:.4f} {cmd[2]:.4f}")
            elif op == "C":
                parts.append(f"C{cmd[1]:.4f} {cmd[2]:.4f} {cmd[3]:.4f} {cmd[4]:.4f} {cmd[5]:.4f} {cmd[6]:.4f}")
            elif op == "Q":
                parts.append(f"Q{cmd[1]:.4f} {cmd[2]:.4f} {cmd[3]:.4f} {cmd[4]:.4f}")
            elif op == "Z":
                parts.append("Z")
        return " ".join(parts)


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
        # v4.3.5.64: optional fixed rotation pivot in mm (world coords). The
        # renderer rotates the whole group about this point. When None the pivot
        # falls back to the center of the children's bbox -- but that center
        # moves whenever a child is edited, which makes the OTHER children appear
        # to "dance". Pinning the pivot when the group is rotated keeps the other
        # children visually still during per-child edits. Stored only when set.
        if not hasattr(self, "rotation_pivot"):
            object.__setattr__(self, "rotation_pivot", None)

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

    def compute_bounds(self):
        """v4.3.5.42: axis-aligned (x,y,w,h) bounding box in mm of all children,
        accounting for child rotation AND shear. Also stored on self.transform so
        the group has a meaningful box for selection/handles. v4.3.5.66: shear was
        ignored, so the box didn't fit sheared children (e.g. rotated rects that
        gained shear from a non-uniform group resize); each corner is now sheared
        about the child center before rotation, matching the renderer."""
        import math as _m
        xs, ys = [], []
        for o in self.flatten():
            t = getattr(o, "transform", None)
            if t is None:
                continue
            cx, cy = t.x + t.width / 2.0, t.y + t.height / 2.0
            rot = _m.radians(getattr(t, "rotation", 0) or 0)
            shx = getattr(t, "shear_x", 0.0) or 0.0
            cos_r, sin_r = _m.cos(rot), _m.sin(rot)
            for (px, py) in [(t.x, t.y), (t.x + t.width, t.y),
                             (t.x + t.width, t.y + t.height), (t.x, t.y + t.height)]:
                dx, dy = px - cx, py - cy
                # shear about the center (x += shear_x*y), then rotation -- the
                # same order the renderer applies, so the box matches the pixels.
                dx = dx + shx * dy
                rx = cx + dx * cos_r - dy * sin_r
                ry = cy + dx * sin_r + dy * cos_r
                xs.append(rx); ys.append(ry)
        if not xs:
            return (self.transform.x, self.transform.y,
                    self.transform.width, self.transform.height)
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        self.transform.x = x0; self.transform.y = y0
        self.transform.width = max(0.1, x1 - x0)
        self.transform.height = max(0.1, y1 - y0)
        # v4.3.5.49: the group's box is the bbox of its children in their LOCAL
        # (un-rotated) space; the group's own transform.rotation is kept (the
        # renderer rotates the whole group). Don't reset it.
        return (x0, y0, x1 - x0, y1 - y0)

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["children"] = [c.to_dict() for c in self.children]
        piv = getattr(self, "rotation_pivot", None)
        if piv is not None:
            d["rotation_pivot"] = [float(piv[0]), float(piv[1])]
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "Group":
        base: Group = EdofObject._from_dict.__func__(cls, d)
        base.children = [EdofObject.from_dict(c) for c in d.get("children", [])]
        object.__setattr__(base, "OBJECT_TYPE", "group")
        piv = d.get("rotation_pivot", None)
        if piv is not None and len(piv) == 2:
            object.__setattr__(base, "rotation_pivot", (float(piv[0]), float(piv[1])))
        else:
            object.__setattr__(base, "rotation_pivot", None)
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
               alternating: bool = True,
               # v4.1.0: position/size convenience
               x: Optional[float] = None,
               y: Optional[float] = None,
               width: Optional[float] = None,
               col_widths: Optional[List[float]] = None,
               row_heights: Optional[List[float]] = None,
               row_height: float = 8.0,
               header_height: Optional[float] = None) -> Table:
    """Quick helper to build a Table from list-of-lists.

    v4.1.0: accept x, y, width, col_widths, row_heights — Transform is set
    accordingly and Table.transform.height is computed from row_heights so
    callers can immediately read tbl.transform.y + tbl.transform.height for
    the next vertical position.

    Examples:
        # Auto-distribute columns across width=120mm, default row height 8mm
        tbl = edof.make_table(rows, header=True, x=20, y=20, width=120)

        # Explicit column widths and row heights
        tbl = edof.make_table(rows, x=20, y=20,
                               col_widths=[60, 30, 30],
                               row_heights=[10, 8, 8, 8])
    """
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

    # v4.1.0: position + sizing convenience
    if col_widths is not None:
        t.col_widths = list(col_widths)
        total_w = sum(col_widths)
    elif width is not None and n_cols > 0:
        per_col = width / n_cols
        t.col_widths = [per_col] * n_cols
        total_w = width
    else:
        total_w = 0  # auto-distribute later

    if row_heights is not None:
        t.row_heights = list(row_heights)
        total_h = sum(row_heights)
    else:
        n_rows = len(rows)
        rh = []
        for i in range(n_rows):
            if i == 0 and header and header_height is not None:
                rh.append(header_height)
            else:
                rh.append(row_height)
        t.row_heights = rh
        total_h = sum(rh)

    if x is not None: t.transform.x = x
    if y is not None: t.transform.y = y
    if total_w > 0:   t.transform.width = total_w
    if total_h > 0:   t.transform.height = total_h
    return t


# ── v4.1.0: SubDocumentBox — embed another EDOF document inside this one ─────

@dataclass
class SubDocumentBox(EdofObject):
    """A box that embeds another EDOF document (or a reference to one).

    Two storage modes:
    - resource_id: the embedded document is stored in doc.resources[resource_id] as bytes
    - source_path: an external path to a .edof file (loaded at render time)

    page_index: which page of the sub-document to embed
    fit_mode: contain | cover | stretch | none
    """
    resource_id:  Optional[str] = None
    source_path:  Optional[str] = None
    page_index:   int           = 0
    fit_mode:     str           = "contain"

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "subdocument")

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({
            "resource_id": self.resource_id,
            "source_path": self.source_path,
            "page_index":  self.page_index,
            "fit_mode":    self.fit_mode,
        })
        return d

    @classmethod
    def _from_dict(cls, d: dict) -> "SubDocumentBox":
        base: SubDocumentBox = EdofObject._from_dict.__func__(cls, d)
        base.resource_id = d.get("resource_id")
        base.source_path = d.get("source_path")
        base.page_index  = int(d.get("page_index", 0))
        base.fit_mode    = d.get("fit_mode", "contain")
        object.__setattr__(base, "OBJECT_TYPE", "subdocument")
        return base
