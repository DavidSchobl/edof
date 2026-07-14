"""Attribute registry — introspection layer for the 3D Batch mode.

The batch system needs a *uniform* way to ask any object "what can be set on
you, and how", independent of the attribute's concrete type. This module is
that single source of truth. It is pure backend: no Qt, no rendering, no
dependency on the editor. The batch model (4.3.2.0+) and the batch UI
(4.3.3.0+) consume it; nothing here knows they exist.

Design (per the roadmap's HORIZONTAL phasing): the *type* of a value is not a
set of separate code paths but ONE descriptor. A descriptor carries:

  * path     — dotted address of the attribute relative to the object
               (e.g. "text", "transform.width", "fill.color", "style.alignment")
  * label    — human label for a column header ("Text", "Width (mm)", ...)
  * kind     — value kind: 'text' | 'number' | 'color' | 'enum' | 'file_path'
  * choices  — allowed values for kind == 'enum' (else None)
  * priority — lower wins when two set attributes conflict; mirrors how EDOF
               itself resolves precedence (content beats geometry beats style).
               This is descriptive, NOT a new behaviour — the renderer is
               untouched; the batch layer uses it only to decide which of two
               mutually-exclusive columns to apply for a given row.
  * get(obj) — read the current value (used for demo defaults / preview)
  * set(obj, raw) — coerce a raw cell value to the attribute's real type and
               assign it; returns True on success, False if coercion failed
               (a bad cell is skipped, never raised — batch must not crash a
               render).

Because set() owns coercion, a consumer only ever does
``descriptor.set(obj, cell_text)`` regardless of kind — colour, number, enum
and path all flow through the same call. That is what lets the UI add smart
cell editors later as a pure presentation layer over an already-complete
model.

NOTE: this module only *describes and applies* attributes. It deliberately
does not read or write any .edof file and does not mutate anything until a
consumer calls ``set``. Object targeting by stable id / hierarchical path
(groups, sub-documents) is handled by the batch model, not here; this module
operates on an object instance the caller already resolved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

_log = logging.getLogger(__name__)


# ── priority bands (lower wins; matches EDOF's own precedence) ────────────────
PRIO_CONTENT = 10      # the object's primary payload (text, image path, qr data)
PRIO_GEOMETRY = 20     # transform: position, size, rotation
PRIO_STYLE = 30        # fills, strokes, fonts, alignment
PRIO_EFFECT = 40       # layer effects (added in a later phase)
# v4.3.5.17: the master 'All effects' switch must be applied LAST so it always
# wins -- otherwise Path-A effect creation (which turns the master on as a side
# effect) could override an explicit all_enabled=false in the same row. Lower
# priority number = applied later = wins on conflict.
PRIO_MASTER = 5


# ── value coercion helpers ───────────────────────────────────────────────────
def _coerce_number(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace(",", ".")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _coerce_color(raw: Any):
    """Accept '#rrggbb', '#rrggbbaa', 'r,g,b[,a]', or an (r,g,b[,a]) tuple.
    Returns an (r, g, b) or (r, g, b, a) int tuple, or None."""
    if raw is None:
        return None
    if isinstance(raw, (tuple, list)):
        try:
            vals = [int(round(float(c))) for c in raw]
        except (TypeError, ValueError):
            return None
        if len(vals) in (3, 4):
            return tuple(max(0, min(255, v)) for v in vals)
        return None
    s = str(raw).strip()
    if s == "":
        return None
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in h):
            comps = tuple(int(h[i:i + 2], 16) for i in range(0, len(h), 2))
            return comps
        return None
    parts = [p for p in s.replace(";", ",").split(",") if p.strip() != ""]
    try:
        vals = [max(0, min(255, int(round(float(p))))) for p in parts]
    except ValueError:
        return None
    if len(vals) in (3, 4):
        return tuple(vals)
    return None


def _coerce_str(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    return str(raw)


# ── descriptor ───────────────────────────────────────────────────────────────
@dataclass
class AttrDescriptor:
    path: str
    label: str
    kind: str                      # 'text'|'number'|'color'|'enum'|'file_path'
    priority: int
    _get: Callable[[Any], Any]
    _set: Callable[[Any, Any], bool]
    choices: Optional[List[str]] = None

    def get(self, obj: Any) -> Any:
        try:
            return self._get(obj)
        except Exception:
            _log.debug("attr get failed: %s", self.path, exc_info=True)
            return None

    def set(self, obj: Any, raw: Any) -> bool:
        """Coerce `raw` to the attribute's type and assign. Empty/None means
        'leave as-is' (batch semantics: an empty cell does not overwrite) and
        returns True without touching the object."""
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            return True
        try:
            return bool(self._set(obj, raw))
        except Exception:
            _log.debug("attr set failed: %s = %r", self.path, raw, exc_info=True)
            return False


# ── small builders for common attribute shapes ───────────────────────────────
def _attr_text(path, label, getter, setter, priority):
    def _s(o, raw):
        v = _coerce_str(raw)
        if v is None:
            return False
        setter(o, v)
        return True
    return AttrDescriptor(path, label, "text", priority, getter, _s)


def _attr_number(path, label, getter, setter, priority):
    def _s(o, raw):
        v = _coerce_number(raw)
        if v is None:
            return False
        setter(o, v)
        return True
    return AttrDescriptor(path, label, "number", priority, getter, _s)


def _attr_color(path, label, getter, setter, priority):
    def _s(o, raw):
        v = _coerce_color(raw)
        if v is None:
            return False
        setter(o, v)
        return True
    return AttrDescriptor(path, label, "color", priority, getter, _s)


def _attr_enum(path, label, choices, getter, setter, priority):
    cl = list(choices)

    def _s(o, raw):
        v = _coerce_str(raw)
        if v is None:
            return False
        v = v.strip()
        # case-insensitive match against the allowed set
        for c in cl:
            if v.lower() == c.lower():
                setter(o, c)
                return True
        return False
    return AttrDescriptor(path, label, "enum", priority, getter, _s, choices=cl)


def _attr_path(path, label, getter, setter, priority):
    def _s(o, raw):
        v = _coerce_str(raw)
        if v is None:
            return False
        setter(o, v)
        return True
    return AttrDescriptor(path, label, "file_path", priority, getter, _s)


# ── transform attributes (shared by every object) ────────────────────────────
def _transform_descriptors() -> List[AttrDescriptor]:
    def g(attr):
        return lambda o: getattr(o.transform, attr, None)

    def s(attr):
        def _set(o, v):
            setattr(o.transform, attr, v)
        return _set

    def s_dim(attr):
        """v4.3.5.34: setter for width/height that also scales a shape's local
        geometry (path_data / line points) proportionally, so resizing the box
        squashes/stretches the curve or line instead of cropping it (the bug:
        setting a curve's height cropped it, a line ignored height entirely).
        Mirrors the interactive resize behaviour."""
        def _set(o, v):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return False
            if v <= 0:
                return False
            old = getattr(o.transform, attr, None)
            setattr(o.transform, attr, v)
            if old is None or old <= 0:
                return True
            ratio = v / old
            if abs(ratio - 1.0) < 1e-9:
                return True
            from edof.format.objects import Shape, SHAPE_PATH, SHAPE_LINE
            if not isinstance(o, Shape):
                return True
            sx = ratio if attr == "width" else 1.0
            sy = ratio if attr == "height" else 1.0
            # PATH data are LOCAL (relative to transform.x/y -- the renderer adds
            # the transform), so scale them about the LOCAL origin (0,0), exactly
            # like the interactive resize. v4.3.5.36: the previous version scaled
            # about (transform.x, transform.y), which for local data pushed the
            # curve far off and it vanished.
            if o.shape_type == SHAPE_PATH and getattr(o, "path_data", None):
                new_data = []
                for cmd in o.path_data:
                    if not cmd:
                        new_data.append(cmd); continue
                    op = cmd[0]
                    if op in ("M", "L"):
                        new_data.append([op, cmd[1] * sx, cmd[2] * sy])
                    elif op == "C":
                        new_data.append([op, cmd[1] * sx, cmd[2] * sy,
                                         cmd[3] * sx, cmd[4] * sy,
                                         cmd[5] * sx, cmd[6] * sy])
                    elif op == "Q":
                        new_data.append([op, cmd[1] * sx, cmd[2] * sy,
                                         cmd[3] * sx, cmd[4] * sy])
                    else:
                        new_data.append(cmd)
                o.path_data = new_data
            # v4.3.5.48: LINE points are LOCAL now (like a path), so scale them
            # about the local origin (0,0).
            elif o.shape_type == SHAPE_LINE and getattr(o, "points", None):
                o.points = [[px * sx, py * sy] for (px, py) in o.points]
            return True
        return _set

    def s_pos(attr):
        """v4.3.5.48: setter for x/y. Line points are LOCAL now (the renderer
        adds the transform), like a path, so moving only changes the transform --
        no point translation needed."""
        def _set(o, v):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return False
            setattr(o.transform, attr, v)
            return True
        return _set

    def s_pos_delta(attr):
        """v4.3.5.36: INCREMENTAL x/y -- add/subtract from the current position
        (negative values move the other way). Reuses the absolute setter so a
        line's absolute points are translated too."""
        abs_set = s_pos(attr)
        def _set(o, v):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return False
            cur = getattr(o.transform, attr, 0.0) or 0.0
            return abs_set(o, cur + v)
        return _set

    return [
        _attr_number("transform.x", "X (mm)", g("x"), s_pos("x"), PRIO_GEOMETRY),
        _attr_number("transform.y", "Y (mm)", g("y"), s_pos("y"), PRIO_GEOMETRY),
        _attr_number("transform.x_offset", "X offset (+/- mm)",
                     lambda o: 0.0, s_pos_delta("x"), PRIO_GEOMETRY),
        _attr_number("transform.y_offset", "Y offset (+/- mm)",
                     lambda o: 0.0, s_pos_delta("y"), PRIO_GEOMETRY),
        _attr_number("transform.width", "Width (mm)", g("width"), s_dim("width"), PRIO_GEOMETRY),
        _attr_number("transform.height", "Height (mm)", g("height"), s_dim("height"), PRIO_GEOMETRY),
        _attr_number("transform.rotation", "Rotation (deg)", g("rotation"), s("rotation"), PRIO_GEOMETRY),
    ]


def _common_descriptors() -> List[AttrDescriptor]:
    """Attributes every EdofObject has (besides transform)."""
    return [
        _attr_number("opacity", "Opacity (0-1)",
                     lambda o: getattr(o, "opacity", 1.0),
                     lambda o, v: setattr(o, "opacity", max(0.0, min(1.0, v))),
                     PRIO_STYLE),
        # visibility is batchable (e.g. one row hides an object, another shows
        # it); 'locked' deliberately is NOT exposed -- it has no meaning per row
        _attr_enum("visible", "Visible",
                   ["true", "false"],
                   lambda o: "true" if getattr(o, "visible", True) else "false",
                   lambda o, v: setattr(o, "visible", str(v).lower() == "true"),
                   PRIO_STYLE),
    ]


# ── layer-effect attributes (per effect type) ────────────────────────────────
# For each effect type, the fields worth batching. Paths look like
# "effects.<type>.<field>"; the effect must already exist on the object (batch
# tweaks an existing effect, it does not create one). _kind picks the editor.
_EFFECT_FIELDS = {
    "drop_shadow": [
        ("color", "color", "Colour"),
        ("size", "number", "Blur (mm)"),
        ("distance", "number", "Distance (mm)"),
        ("direction", "number", "Angle (deg)"),
        ("spread", "number", "Spread"),
        ("opacity", "number", "Opacity"),
        ("enabled", "enum", "Enabled"),
    ],
    "inner_shadow": [
        ("color", "color", "Colour"),
        ("size", "number", "Blur (mm)"),
        ("distance", "number", "Distance (mm)"),
        ("direction", "number", "Angle (deg)"),
        ("opacity", "number", "Opacity"),
        ("enabled", "enum", "Enabled"),
    ],
    "outer_glow": [
        ("color", "color", "Colour"),
        ("size", "number", "Size (mm)"),
        ("spread", "number", "Spread"),
        ("opacity", "number", "Opacity"),
        ("enabled", "enum", "Enabled"),
    ],
    "inner_glow": [
        ("color", "color", "Colour"),
        ("size", "number", "Size (mm)"),
        ("spread", "number", "Spread"),
        ("opacity", "number", "Opacity"),
        ("enabled", "enum", "Enabled"),
    ],
    "stroke": [
        ("color", "color", "Colour"),
        ("size", "number", "Width (mm)"),
        ("stroke_position", "enum", "Position"),
        ("opacity", "number", "Opacity"),
        ("enabled", "enum", "Enabled"),
    ],
    "long_shadow": [
        ("color", "color", "Colour"),
        ("ls_length", "number", "Length (mm)"),
        ("ls_taper", "number", "Taper"),
        ("ls_light_angle", "number", "Light angle (deg)"),
        ("ls_blur_mode", "enum", "Blur mode"),
        ("ls_color_mode", "enum", "Colour mode"),
        ("enabled", "enum", "Enabled"),
    ],
    "chromatic_aberration": [
        ("ca_offset", "number", "Offset (mm)"),
        ("ca_angle", "number", "Angle (deg)"),
        ("ca_mode", "enum", "Mode"),
        ("enabled", "enum", "Enabled"),
    ],
    "halftone": [
        ("ht_dot", "number", "Dot size"),
        ("ht_angle", "number", "Angle (deg)"),
        ("ht_shape", "enum", "Shape"),
        ("ht_color_mode", "enum", "Colour mode"),
        ("ht_pattern_mode", "enum", "Pattern mode"),
        # ht_patterns (the base64 image cache) is NOT batchable directly --
        # batching raw base64 is meaningless and ties a row to an internal
        # backup. Pattern images are batched by FILE PATH instead (see the
        # synthesized ht_pattern_path / ht_pattern_path#N descriptors), which
        # load the PNG at apply time so the path is the source of truth.
        ("enabled", "enum", "Enabled"),
    ],
    "color_overlay": [
        ("color", "color", "Colour"),
        ("opacity", "number", "Opacity"),
        ("blend_mode", "enum", "Blend mode"),
        ("enabled", "enum", "Enabled"),
    ],
    "gradient_overlay": [
        ("gradient_start", "color", "Start colour"),
        ("gradient_end", "color", "End colour"),
        ("gradient_angle", "number", "Angle (deg)"),
        ("opacity", "number", "Opacity"),
        ("enabled", "enum", "Enabled"),
    ],
    "bevel": [
        ("bevel_kind", "enum", "Kind"),
        ("bevel_depth", "number", "Depth"),
        ("bevel_dir", "enum", "Direction"),
        ("soften", "number", "Soften"),
        ("enabled", "enum", "Enabled"),
    ],
    "light_sweep": [
        ("lsw_pos", "number", "Position"),
        ("lsw_width", "number", "Width"),
        ("lsw_angle", "number", "Angle (deg)"),
        ("enabled", "enum", "Enabled"),
    ],
    "texture_overlay": [
        ("texture_scale", "number", "Scale (%)"),
        ("texture_fit", "enum", "Fit"),
        ("opacity", "number", "Opacity"),
        ("enabled", "enum", "Enabled"),
    ],
}

# enum value sets for effect fields (case-insensitive on apply)
_EFFECT_ENUMS = {
    "enabled": ["true", "false"],
    "stroke_position": ["outside", "inside", "center"],
    "ls_blur_mode": ["solid", "constant", "linear", "custom"],
    "ls_color_mode": ["solid", "custom"],
    "ca_mode": ["linear", "radial"],
    "ht_shape": ["circle", "square", "diamond", "line"],
    "ht_color_mode": ["cmyk", "rgb", "mono"],
    "ht_pattern_mode": ["shape", "single", "per_channel"],
    "bevel_kind": ["outer", "inner", "emboss"],
    "bevel_dir": ["up", "down"],
    "blend_mode": ["normal", "multiply", "screen", "overlay", "darken",
                   "lighten", "color_dodge", "color_burn", "hard_light",
                   "soft_light", "difference", "exclusion"],
    "texture_fit": ["tile", "stretch", "fit", "fill"],
}


def _effect_field_descriptor(eff_type, field, kind, label, ordinal=0, eid=""):
    """Build a descriptor for one field of an effect of `eff_type` on the object.
    By default it targets the `ordinal`-th instance (ordinal 0 = first). If
    `eid` is given, it targets the effect with that stable id instead, so the
    binding survives reordering (positional ordinals would re-point). On write,
    if the object has no such effect yet, one is created (Path A, only for the
    positional first instance; an eid binding never fabricates). Several effects
    of the same type get ordinal paths ``effects.<type>#<N>.<field>``."""
    if ordinal <= 0:
        path = "effects.%s.%s" % (eff_type, field)
        disp_type = eff_type
    else:
        path = "effects.%s#%d.%s" % (eff_type, ordinal + 1, field)
        disp_type = "%s #%d" % (eff_type, ordinal + 1)

    def _find_effect(o, create=False):
        # eid binding takes precedence: find THE specific instance
        if eid:
            for e in (getattr(o, "effects", None) or []):
                if getattr(e, "eid", None) == eid:
                    return e
            return None     # an eid binding never fabricates an effect
        matches = [e for e in (getattr(o, "effects", None) or [])
                   if getattr(e, "type", None) == eff_type]
        if ordinal < len(matches):
            return matches[ordinal]
        if not create:
            return None
        # Path A: create instances on demand. To target ordinal N we must have
        # N+1 instances of this type, so we pad with default instances up to and
        # including N (you can't have a 2nd effect without a 1st). All created
        # instances use the same defaults the 'add effect' UI uses, disabled
        # until a row enables them.
        if not hasattr(o, "effects") or getattr(o, "effects") is None:
            try: o.effects = []
            except Exception: return None
        n_before = len(o.effects)
        created = None
        while len([e for e in o.effects
                   if getattr(e, "type", None) == eff_type]) <= ordinal:
            e = make_default_effect(eff_type)
            if e is None:
                return None
            o.effects.append(e)
            created = e
        # v4.3.5.30: path A no longer turns the master on when it creates the
        # first effect. Per request, the master is explicit only -- an
        # effects.all_enabled variable (or the master already on). Without this,
        # batching an effect onto an object that had none would silently enable
        # the master, so the effect showed even with no master variable (and
        # contradicted the panel's red warning).
        if created is not None:
            try:
                from edof.engine.debug_log import log as _dlog
                _dlog("registry.pathA_create_effect", eff_type=eff_type,
                      ordinal=ordinal, obj_id=str(getattr(o, "id", "?"))[:8],
                      n_effects_now=len(o.effects), master_set=False)
            except Exception: pass
        # return the ordinal-th instance now that it exists
        matches = [e for e in o.effects if getattr(e, "type", None) == eff_type]
        return matches[ordinal] if ordinal < len(matches) else None

    def _get(o):
        e = _find_effect(o)
        if e is None:
            # v4.3.5.16: 'is this effect enabled?' -> if the object doesn't have
            # the effect at all, the answer is a concrete "false" (not None), so
            # a newly-seeded batch cell gets a real value the user flips to true,
            # instead of an empty cell that misleadingly shows the first choice.
            if field == "enabled":
                return "false"
            return None
        v = getattr(e, field, None)
        if field == "enabled":
            return "true" if v else "false"
        return v

    _disp = "%s: %s" % (disp_type, label)

    if field == "enabled":
        def _set(o, raw):
            e = _find_effect(o, create=True)
            if e is None:
                return False
            e.enabled = str(raw).strip().lower() in ("true", "1", "yes", "on")
            # v4.3.5.28: we no longer auto-toggle the object's master 'All
            # effects' flag here. It surprised the user: after removing a master
            # variable, enabling a shadow still forced the master on, so effects
            # wouldn't hide. The master is now controlled only explicitly (an
            # effects.all_enabled variable, or the master being on already). Newly
            # added effects turn the master on at add time instead.
            return True
        return AttrDescriptor(path, _disp, "enum",
                              PRIO_EFFECT, _get, _set,
                              choices=["true", "false"])

    if kind == "color":
        def _set(o, raw):
            e = _find_effect(o, create=True)
            if e is None:
                return False
            c = _coerce_color(raw)
            if c is None:
                return False
            setattr(e, field, c)
            return True
        return AttrDescriptor(path, _disp, "color",
                              PRIO_EFFECT, _get, _set)

    if kind == "enum":
        choices = _EFFECT_ENUMS.get(field, [])

        def _set(o, raw):
            e = _find_effect(o, create=True)
            if e is None:
                return False
            v = _coerce_str(raw)
            if v is None:
                return False
            v = v.strip()
            for c in choices:
                if v.lower() == c.lower():
                    setattr(e, field, c)
                    return True
            return False
        return AttrDescriptor(path, _disp, "enum",
                              PRIO_EFFECT, _get, _set, choices=list(choices))

    if kind == "number":
        def _set(o, raw):
            e = _find_effect(o, create=True)
            if e is None:
                return False
            n = _coerce_number(raw)
            if n is None:
                return False
            setattr(e, field, n)
            return True
        return AttrDescriptor(path, _disp, "number",
                              PRIO_EFFECT, _get, _set)

    # text (e.g. ht_patterns)
    def _set(o, raw):
        e = _find_effect(o, create=True)
        if e is None:
            return False
        setattr(e, field, raw)
        return True
    return AttrDescriptor(path, _disp, "text",
                          PRIO_EFFECT, _get, _set)


def make_default_effect(eff_type):
    """Create a LayerEffect of `eff_type` with the SAME sensible defaults the
    'add effect' UI uses, not the bare dataclass defaults. This matters for
    Path A: an effect created on demand by a batch column must look like one the
    user would have added by hand (e.g. drop shadow at direction 315, not the
    dataclass's 135, which points the opposite way). Returns the effect disabled
    (enabled=False) -- the batch decides when to turn it on."""
    try:
        from edof import LayerEffect
    except Exception:
        return None
    e = LayerEffect(type=eff_type)
    if eff_type == 'drop_shadow':
        e.color = (0, 0, 0, 220); e.opacity = 0.7
        e.size = 2.0; e.distance = 2.0; e.direction = 315.0
        e.blend_mode = 'multiply'
    elif eff_type == 'inner_shadow':
        e.color = (0, 0, 0, 220); e.opacity = 0.7
        e.size = 2.0; e.distance = 2.0; e.direction = 315.0
        e.blend_mode = 'multiply'
    elif eff_type == 'outer_glow':
        e.color = (255, 255, 200, 255); e.opacity = 0.6
        e.size = 4.0; e.blend_mode = 'screen'
    elif eff_type == 'inner_glow':
        e.color = (255, 255, 200, 255); e.opacity = 0.6
        e.size = 4.0; e.blend_mode = 'screen'
    elif eff_type == 'bevel':
        e.color = (0, 0, 0, 200); e.color2 = (255, 255, 255, 255)
        e.size = 3.0; e.direction = 135.0; e.bevel_kind = 'inner'
    elif eff_type == 'stroke':
        e.color = (0, 0, 0, 255); e.size = 1.0
        e.stroke_position = 'outside'
    elif eff_type == 'color_overlay':
        e.color = (255, 0, 0, 255); e.opacity = 1.0
        e.blend_mode = 'normal'
    elif eff_type == 'gradient_overlay':
        e.gradient_start = (0, 0, 0, 255); e.gradient_end = (255, 255, 255, 255)
        e.gradient_angle = 90.0; e.opacity = 1.0
    elif eff_type == 'texture_overlay':
        e.opacity = 1.0; e.blend_mode = 'multiply'
    elif eff_type == 'long_shadow':
        e.color = (0, 0, 0, 180); e.direction = 315.0
        e.ls_length = 10.0; e.ls_fade = True; e.opacity = 0.7
        e.blend_mode = 'normal'
    elif eff_type == 'chromatic_aberration':
        e.ca_offset = 0.5; e.ca_angle = 0.0; e.opacity = 1.0
        e.blend_mode = 'normal'
    elif eff_type == 'halftone':
        e.color = (0, 0, 0, 255); e.ht_dot = 1.5
        e.ht_angle = 72.0; e.ht_shape = 'dot'; e.opacity = 1.0
        e.blend_mode = 'normal'
    elif eff_type == 'light_sweep':
        e.color2 = (255, 255, 255, 255); e.lsw_pos = 0.5
        e.lsw_width = 0.3; e.lsw_angle = 45.0; e.opacity = 0.6
        e.blend_mode = 'screen'
    try:
        e.enabled = False           # batch turns it on
    except Exception:
        pass
    return e


def all_effect_descriptors() -> List[AttrDescriptor]:
    """Every possible effect field for every effect type, regardless of whether
    any object currently has the effect. Used by the column 'add' tree so a
    user can batch an effect the object doesn't have yet (Path A)."""
    out = []
    for et, fields in _EFFECT_FIELDS.items():
        for field, kind, label in fields:
            out.append(_effect_field_descriptor(et, field, kind, label))
    return out


def effect_types() -> List[str]:
    """The effect type ids the registry knows how to batch."""
    return list(_EFFECT_FIELDS.keys())


def effect_fields(eff_type) -> List[AttrDescriptor]:
    """Descriptors for one effect type's fields (for the tree dialog)."""
    out = []
    for field, kind, label in _EFFECT_FIELDS.get(eff_type, []):
        out.append(_effect_field_descriptor(eff_type, field, kind, label))
    return out


def _ht_pattern_path_descriptor(ordinal=0):
    """A batchable FILE PATH for a halftone pattern image. Setting it loads the
    PNG from the path (Pillow, downscaled like the UI does) into the effect's
    ht_patterns[ordinal] slot. The path is the source of truth, so an imported
    file's pattern is set by path -- not by the internal base64 cache. ordinal 0
    is the first pattern (single mode / channel 1); higher ordinals address the
    per-channel patterns (#2 = channel 2, ...)."""
    if ordinal <= 0:
        path = "effects.halftone.ht_pattern_path"
        disp = "halftone: Pattern file"
    else:
        path = "effects.halftone.ht_pattern_path#%d" % (ordinal + 1)
        disp = "halftone #%d: Pattern file" % (ordinal + 1)

    def _find(o):
        for e in (getattr(o, "effects", None) or []):
            if getattr(e, "type", None) == "halftone":
                return e
        return None

    def _get(o):
        e = _find(o)
        if e is None:
            return None
        paths = getattr(e, "ht_pattern_paths", None) or []
        if ordinal < len(paths):
            return paths[ordinal]
        return ""

    def _file_to_b64(p):
        try:
            import base64, io
            from PIL import Image as _Img
            im = _Img.open(p).convert("RGBA")
            if max(im.size) > 512:
                r = 512.0 / max(im.size)
                im = im.resize((max(1, int(im.width * r)),
                                max(1, int(im.height * r))), _Img.LANCZOS)
            buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def _set(o, raw):
        e = _find(o)
        if e is None:
            d = find_descriptor(o, "effects.halftone.enabled")
            if d is not None:
                d.set(o, "false")     # creates a halftone effect via Path A
            e = _find(o)
        if e is None:
            return False
        p = _coerce_str(raw)
        if p is None:
            return False
        p = p.strip()
        paths = list(getattr(e, "ht_pattern_paths", None) or [])
        while len(paths) <= ordinal:
            paths.append("")
        paths[ordinal] = p
        try: e.ht_pattern_paths = paths
        except Exception: pass
        b64 = _file_to_b64(p) if p else ""
        if p and b64 is None:
            return False        # bad path / unreadable image
        pats = list(getattr(e, "ht_patterns", None) or [])
        while len(pats) <= ordinal:
            pats.append("")
        pats[ordinal] = b64 or ""
        try: e.ht_patterns = pats
        except Exception: pass
        if p and getattr(e, "ht_pattern_mode", "shape") == "shape":
            try: e.ht_pattern_mode = "single" if ordinal == 0 else "per_channel"
            except Exception: pass
        return True

    return AttrDescriptor(path, disp, "file_path", PRIO_EFFECT, _get, _set)


def _all_enabled_descriptor() -> AttrDescriptor:
    """The object-level master 'All effects' switch (effects.all_enabled). When
    false, no effect renders even if individual effects are enabled; the effects
    stay on the object. Batchable so a row can switch every effect on/off."""
    def _get(o):
        return "true" if getattr(o, "effects_enabled", True) else "false"

    def _set(o, raw):
        try:
            o.effects_enabled = str(raw).strip().lower() in ("true", "1", "yes", "on")
            try:
                from edof.engine.debug_log import log as _dlog
                _dlog("registry.all_enabled_set", raw=str(raw),
                      result=o.effects_enabled, obj_id=str(getattr(o, "id", "?"))[:8])
            except Exception: pass
            return True
        except Exception:
            return False
    return AttrDescriptor("effects.all_enabled", "All effects", "enum",
                          PRIO_MASTER, _get, _set, choices=["true", "false"])


def _effect_descriptors(obj) -> List[AttrDescriptor]:
    """Descriptors for the effects actually present on `obj`, plus the
    object-level master 'All effects' switch. With several effects of the same
    type, each instance gets its own ordinal-indexed descriptors (the first as
    ``effects.<type>.<field>``, the second as ``effects.<type>#2.<field>``, ...)
    so every instance can be batched independently, reflecting layer order."""
    out = [_all_enabled_descriptor()]
    per_type_count = {}
    for e in (getattr(obj, "effects", None) or []):
        et = getattr(e, "type", None)
        if et is None or et not in _EFFECT_FIELDS:
            continue
        ordinal = per_type_count.get(et, 0)
        per_type_count[et] = ordinal + 1
        for field, kind, label in _EFFECT_FIELDS[et]:
            out.append(_effect_field_descriptor(et, field, kind, label,
                                                ordinal=ordinal))
        # halftone: also expose pattern FILE PATH slots (the path is the source
        # of truth, loaded into the base64 cache at apply time). Offer the first
        # slot, plus per-channel slots when the colour mode uses channels.
        if et == "halftone" and ordinal == 0:
            n_slots = 4 if getattr(e, "ht_color_mode", "cmyk") == "cmyk" else 3
            if getattr(e, "ht_pattern_mode", "shape") in ("shape", "single"):
                n_slots = 1
            for k in range(n_slots):
                out.append(_ht_pattern_path_descriptor(ordinal=k))
    return out


# ── per-type attribute tables ────────────────────────────────────────────────
def _set_textbox_text(o, v):
    """Set a textbox's plain text AND keep the rich-text runs in sync, otherwise
    the renderer keeps showing the old runs and the change is invisible
    (v4.3.5.26). Formatting is preserved: the new text becomes a single run that
    inherits the first existing run's font/size/style (so a batched text keeps
    the look it had); paragraph breaks split into one run each."""
    v = "" if v is None else str(v)
    try:
        o.text = v
    except Exception:
        return
    runs = getattr(o, "runs", None)
    if runs is None:
        return
    # template formatting from the first run (if any)
    from edof.format.styles import TextRun
    proto = runs[0] if runs else None

    def _mk(seg):
        r = TextRun(text=seg)
        if proto is not None:
            for attr in ("font_family", "font_size", "bold", "italic",
                         "underline", "strikethrough", "color", "background",
                         "line_height", "letter_spacing"):
                try: setattr(r, attr, getattr(proto, attr, None))
                except Exception: pass
        return r

    # one run per paragraph, preserving the "\n" between them
    parts = v.split("\n")
    new_runs = []
    for i, seg in enumerate(parts):
        if i > 0:
            new_runs.append(_mk("\n"))
        if seg:
            new_runs.append(_mk(seg))
    try:
        o.runs = new_runs
    except Exception:
        pass


def _textbox_descriptors() -> List[AttrDescriptor]:
    d: List[AttrDescriptor] = []
    d.append(_attr_text("text", "Text",
                        lambda o: getattr(o, "text", ""),
                        _set_textbox_text,
                        PRIO_CONTENT))

    def sg(attr):
        return lambda o: getattr(o.style, attr, None)

    def ss(attr):
        def _set(o, v):
            setattr(o.style, attr, v)
        return _set

    d.append(_attr_color("style.color", "Text colour",
                         sg("color"), ss("color"), PRIO_STYLE))
    d.append(_attr_number("style.font_size", "Font size (mm)",
                          sg("font_size"), ss("font_size"), PRIO_STYLE))
    d.append(_attr_text("style.font_family", "Font family",
                        sg("font_family"), ss("font_family"), PRIO_STYLE))
    _ALIGN_CHOICES = ["left", "center", "right", "justify", "justify_full"]

    def _set_alignment(o, v):
        """Set horizontal alignment. Like text, run-level alignment wins in the
        layout engine, so setting only style.alignment can be invisible
        (v4.3.5.27). Push the value onto every run and clear the per-paragraph
        override map so a batched alignment (incl. justify) actually shows.
        Validates against the known choices (case-insensitive)."""
        v = _coerce_str(v)
        if v is None:
            return False
        vl = v.strip().lower()
        if vl not in _ALIGN_CHOICES:
            return False
        try:
            o.style.alignment = vl
        except Exception:
            return False
        for r in (getattr(o, "runs", None) or []):
            try: r.alignment = vl
            except Exception: pass
        try:
            if getattr(o, "paragraph_alignments", None):
                o.paragraph_alignments = {}
        except Exception: pass
        return True

    d.append(AttrDescriptor("style.alignment", "Align (horizontal)", "enum",
                            PRIO_STYLE, sg("alignment"), _set_alignment,
                            choices=list(_ALIGN_CHOICES)))
    d.append(_attr_enum("style.vertical_align", "Align (vertical)",
                        ["top", "middle", "bottom"],
                        sg("vertical_align"), ss("vertical_align"), PRIO_STYLE))
    # v4.3.5.29: justify distribution mode (how justified text spreads). Only
    # meaningful when alignment is justify/justify_full, but harmless otherwise.
    d.append(_attr_enum("style.justify_mode", "Justify mode",
                        ["space", "full"],
                        sg("justify_mode"), ss("justify_mode"), PRIO_STYLE))
    # v4.3.5.13: the rest of the text style that was missing from batch.
    d.append(_attr_enum("style.bold", "Bold", ["true", "false"],
                        lambda o: "true" if getattr(o.style, "bold", False) else "false",
                        lambda o, v: setattr(o.style, "bold",
                                             str(v).strip().lower() in ("true", "1", "yes", "on")),
                        PRIO_STYLE))
    d.append(_attr_enum("style.italic", "Italic", ["true", "false"],
                        lambda o: "true" if getattr(o.style, "italic", False) else "false",
                        lambda o, v: setattr(o.style, "italic",
                                             str(v).strip().lower() in ("true", "1", "yes", "on")),
                        PRIO_STYLE))
    d.append(_attr_enum("style.underline", "Underline", ["true", "false"],
                        lambda o: "true" if getattr(o.style, "underline", False) else "false",
                        lambda o, v: setattr(o.style, "underline",
                                             str(v).strip().lower() in ("true", "1", "yes", "on")),
                        PRIO_STYLE))
    d.append(_attr_enum("style.strikethrough", "Strikethrough", ["true", "false"],
                        lambda o: "true" if getattr(o.style, "strikethrough", False) else "false",
                        lambda o, v: setattr(o.style, "strikethrough",
                                             str(v).strip().lower() in ("true", "1", "yes", "on")),
                        PRIO_STYLE))
    d.append(_attr_number("style.line_height", "Line height (x)",
                          sg("line_height"), ss("line_height"), PRIO_STYLE))
    d.append(_attr_number("style.letter_spacing", "Letter spacing (mm)",
                          sg("letter_spacing"), ss("letter_spacing"), PRIO_STYLE))
    # auto-fit controls
    d.append(_attr_enum("style.auto_shrink", "Auto-shrink to fit", ["true", "false"],
                        lambda o: "true" if getattr(o.style, "auto_shrink", False) else "false",
                        lambda o, v: setattr(o.style, "auto_shrink",
                                             str(v).strip().lower() in ("true", "1", "yes", "on")),
                        PRIO_STYLE))
    d.append(_attr_enum("style.auto_fill", "Auto-fill to box", ["true", "false"],
                        lambda o: "true" if getattr(o.style, "auto_fill", False) else "false",
                        lambda o, v: setattr(o.style, "auto_fill",
                                             str(v).strip().lower() in ("true", "1", "yes", "on")),
                        PRIO_STYLE))
    d.append(_attr_number("style.min_font_size", "Min font size (mm)",
                          sg("min_font_size"), ss("min_font_size"), PRIO_STYLE))
    d.append(_attr_number("style.max_font_size", "Max font size (mm)",
                          sg("max_font_size"), ss("max_font_size"), PRIO_STYLE))
    d.append(_attr_enum("style.wrap", "Wrap text", ["true", "false"],
                        lambda o: "true" if getattr(o.style, "wrap", True) else "false",
                        lambda o, v: setattr(o.style, "wrap",
                                             str(v).strip().lower() in ("true", "1", "yes", "on")),
                        PRIO_STYLE))
    d.append(_attr_number("style.padding", "Padding (mm)",
                          sg("padding"), ss("padding"), PRIO_STYLE))
    return d


def _imagebox_descriptors() -> List[AttrDescriptor]:
    return [
        _attr_path("resource_id", "Image (file/resource)",
                   lambda o: getattr(o, "resource_id", None),
                   lambda o, v: setattr(o, "resource_id", v),
                   PRIO_CONTENT),
        _attr_enum("fit_mode", "Fit",
                   ["stretch", "contain", "cover", "fill"],
                   lambda o: getattr(o, "fit_mode", "stretch"),
                   lambda o, v: setattr(o, "fit_mode", v),
                   PRIO_STYLE),
        _attr_number("corner_radius", "Corner radius (mm)",
                     lambda o: getattr(o, "corner_radius", 0.0),
                     lambda o, v: setattr(o, "corner_radius", v),
                     PRIO_STYLE),
    ]


def _shape_descriptors(obj=None) -> List[AttrDescriptor]:
    def fg():
        return lambda o: getattr(o.fill, "color", None)

    def fsr():
        def _set(o, v):
            o.fill.color = v
        return _set

    def stg():
        return lambda o: getattr(o.stroke, "color", None)

    def stsr():
        def _set(o, v):
            o.stroke.color = v
        return _set

    out = [
        _attr_color("fill.color", "Fill colour", fg(), fsr(), PRIO_STYLE),
        _attr_color("stroke.color", "Stroke colour", stg(), stsr(), PRIO_STYLE),
        _attr_number("stroke.width", "Stroke width (mm)",
                     lambda o: getattr(o.stroke, "width", None),
                     lambda o, v: setattr(o.stroke, "width", v),
                     PRIO_STYLE),
    ]
    # corner_radius is only honoured by the renderer for rectangles; an ellipse
    # (and line/polygon/path/arrow) carry the field but ignore it, so it must
    # not appear in the picker for those shapes. Without an instance (the
    # type-only describe path) we cannot know the shape, so we include it; a
    # live object filters correctly.
    shape_type = getattr(obj, "shape_type", None) if obj is not None else None
    if shape_type is None or shape_type == "rect":
        out.append(_attr_number("corner_radius", "Corner radius (mm)",
                                lambda o: getattr(o, "corner_radius", 0.0),
                                lambda o, v: setattr(o, "corner_radius", v),
                                PRIO_STYLE))
    return out


def _qrcode_descriptors() -> List[AttrDescriptor]:
    return [
        _attr_text("data", "QR data",
                   lambda o: getattr(o, "data", ""),
                   lambda o, v: setattr(o, "data", v),
                   PRIO_CONTENT),
        _attr_enum("error_correction", "Error correction",
                   ["L", "M", "Q", "H"],
                   lambda o: getattr(o, "error_correction", "M"),
                   lambda o, v: setattr(o, "error_correction", v),
                   PRIO_STYLE),
        _attr_color("fg_color", "Foreground",
                    lambda o: getattr(o, "fg_color", (0, 0, 0)),
                    lambda o, v: setattr(o, "fg_color", v),
                    PRIO_STYLE),
        _attr_color("bg_color", "Background",
                    lambda o: getattr(o, "bg_color", (255, 255, 255)),
                    lambda o, v: setattr(o, "bg_color", v),
                    PRIO_STYLE),
    ]


def _subdocument_descriptors() -> List[AttrDescriptor]:
    return [
        _attr_path("source_path", "Sub-document (file)",
                   lambda o: getattr(o, "source_path", None),
                   lambda o, v: setattr(o, "source_path", v),
                   PRIO_CONTENT),
        _attr_number("page_index", "Page index",
                     lambda o: getattr(o, "page_index", 0),
                     lambda o, v: setattr(o, "page_index", int(round(v))),
                     PRIO_CONTENT),
        _attr_enum("fit_mode", "Fit",
                   ["stretch", "contain", "cover", "none"],
                   lambda o: getattr(o, "fit_mode", "contain"),
                   lambda o, v: setattr(o, "fit_mode", v),
                   PRIO_STYLE),
    ]


_TYPE_TABLE = {
    "textbox": _textbox_descriptors,
    "imagebox": _imagebox_descriptors,
    "shape": _shape_descriptors,
    "qrcode": _qrcode_descriptors,
    "subdocument": _subdocument_descriptors,
}


# ── public API ───────────────────────────────────────────────────────────────
def describe_object(obj: Any) -> List[AttrDescriptor]:
    """Return the batchable attribute descriptors for an object instance.

    Order: content first (so the most common target floats to the top of the
    'add column' picker), then geometry, then style. Object types without a
    specific table (e.g. group) still expose transform + common attributes.
    """
    otype = getattr(obj, "OBJECT_TYPE", "base")
    builder = _TYPE_TABLE.get(otype)
    if builder is None:
        specific = []
    elif otype == "shape":
        specific = builder(obj)            # shape needs the instance (corner_radius)
    else:
        specific = builder()
    out = (list(specific) + _transform_descriptors() + _common_descriptors()
           + _effect_descriptors(obj))     # effects present on this instance
    out.sort(key=lambda d: (d.priority, d.path))
    return out


def describe_type(otype: str) -> List[AttrDescriptor]:
    """Same as describe_object but keyed by OBJECT_TYPE string, for building
    the 'possible settings' export without a live instance. Getters/setters
    are still bound at call time against whatever object is passed later."""
    builder = _TYPE_TABLE.get(otype)
    if builder is None:
        specific = []
    elif otype == "shape":
        specific = builder(None)           # no instance -> include corner_radius
    else:
        specific = builder()
    out = list(specific) + _transform_descriptors() + _common_descriptors()
    out.sort(key=lambda d: (d.priority, d.path))
    return out


def effect_id_for_path(obj, path):
    """For an effect-field path (effects.<type>[#N].<field>), return the stable
    eid of the effect instance it currently resolves to on `obj`, or "" if the
    object doesn't have that instance. Used when creating a batch variable so it
    can bind to THIS effect (surviving reorder) instead of the position."""
    if not path.startswith("effects.") or path == "effects.all_enabled":
        return ""
    if path.startswith("effects.halftone.ht_pattern_path"):
        # halftone first instance only
        for e in (getattr(obj, "effects", None) or []):
            if getattr(e, "type", None) == "halftone":
                return getattr(e, "eid", "") or ""
        return ""
    parts = path.split(".")
    if len(parts) != 3:
        return ""
    seg = parts[1]
    if "#" in seg:
        base_t, _, num = seg.partition("#")
        try:
            ordinal = max(0, int(num) - 1)
        except ValueError:
            ordinal = 0
    else:
        base_t, ordinal = seg, 0
    matches = [e for e in (getattr(obj, "effects", None) or [])
               if getattr(e, "type", None) == base_t]
    if ordinal < len(matches):
        return getattr(matches[ordinal], "eid", "") or ""
    return ""


def find_descriptor_with_effect_id(obj, path, effect_id):
    """Like find_descriptor, but for an effect attribute path, bind the
    descriptor to the effect with stable id `effect_id` (rather than the
    positional ordinal in the path). Used when a batch column stores an
    effect_id so reordering effects doesn't re-point the variable. Falls back to
    the plain positional descriptor if effect_id is empty or the path isn't an
    effect-field path."""
    if not effect_id or not path.startswith("effects.") or path == "effects.all_enabled":
        return find_descriptor(obj, path)
    # parse effects.<type>[#N].<field> -> type + field (ordinal ignored: eid wins)
    parts = path.split(".")
    if len(parts) != 3:
        return find_descriptor(obj, path)
    eff_type = parts[1].split("#")[0]
    field = parts[2]
    spec = _EFFECT_FIELDS.get(eff_type)
    if not spec:
        # halftone pattern-path by id isn't supported; fall back
        return find_descriptor(obj, path)
    for f, kind, label in spec:
        if f == field:
            return _effect_field_descriptor(eff_type, field, kind, label,
                                            eid=effect_id)
    return find_descriptor(obj, path)


def find_descriptor(obj: Any, path: str) -> Optional[AttrDescriptor]:
    """Look up a single descriptor by its dotted path for the given object.

    For effect paths (``effects.<type>.<field>``) the descriptor is synthesized
    even when the object has no such effect yet, so a batch column can target an
    effect the base template doesn't have (Path A): applying a value then
    creates the effect (disabled by default)."""
    for d in describe_object(obj):
        if d.path == path:
            return d
    # halftone pattern file-path slots: effects.halftone.ht_pattern_path[#N]
    if path.startswith("effects.halftone.ht_pattern_path"):
        tail = path[len("effects.halftone.ht_pattern_path"):]
        ordinal = 0
        if tail.startswith("#"):
            try:
                ordinal = max(0, int(tail[1:]) - 1)
            except ValueError:
                ordinal = 0
        return _ht_pattern_path_descriptor(ordinal=ordinal)
    # Path A: effect path not present on the object -> build it on the fly
    if path.startswith("effects."):
        parts = path.split(".")
        if len(parts) == 3:
            _, eff_type, field = parts
            # an ordinal-indexed instance? effects.<type>#<N>.<field>
            ordinal = 0
            if "#" in eff_type:
                base, _, num = eff_type.partition("#")
                eff_type = base
                try:
                    ordinal = max(0, int(num) - 1)   # #2 -> ordinal 1
                except ValueError:
                    ordinal = 0
            spec = _EFFECT_FIELDS.get(eff_type)
            if spec:
                for f, kind, label in spec:
                    if f == field:
                        # for ordinal>0 this only resolves an existing instance
                        # (its setter won't create one); for ordinal 0 Path A
                        # creation still applies
                        return _effect_field_descriptor(eff_type, field, kind,
                                                        label, ordinal=ordinal)
    return None


def apply_value(obj: Any, path: str, raw: Any) -> bool:
    """Convenience: resolve `path` on `obj` and set `raw` through its
    descriptor (with full coercion). Returns False if the path is unknown or
    coercion failed; never raises."""
    d = find_descriptor(obj, path)
    if d is None:
        return False
    return d.set(obj, raw)


# ── v4.3.6.0: variable-text (text-run) descriptors ───────────────────────────
# A batch column can target a single styled RUN inside a TextBox, addressed by
# the run's stable rid. The descriptor finds the run by rid (never positional),
# so editing the surrounding text keeps the binding pointed at the same span.
_RUN_FIELDS = {
    "text":          ("text",   "Text"),
    "font_family":   ("text",   "Font"),
    "font_size":     ("number", "Font size (mm)"),
    "color":         ("color",  "Colour"),
    "background":    ("color",  "Highlight / marker"),
    "bold":          ("enum",   "Bold"),
    "italic":        ("enum",   "Italic"),
    "underline":     ("enum",   "Underline"),
    "strikethrough": ("enum",   "Strikethrough"),
}
_RUN_BOOL_FIELDS = ("bold", "italic", "underline", "strikethrough")
_RUN_ENUM_CHOICES = {f: ["true", "false"] for f in _RUN_BOOL_FIELDS}


def _run_field_descriptor(field, kind, label, rid, extra_run_ids=None):
    """Descriptor for one field of the text run with stable rid `rid` inside the
    object's runs. Found by rid, never positional. On write, if no run carries
    that rid nothing happens (we never fabricate a run -- the UI creates it).
    When the run's text changes, the parent TextBox.text is re-synced so plain
    -text consumers (search, export) stay correct.

    v4.4.0: extra_run_ids adds LINKED variables: writes fill every run whose
    rid is in the whole set; reads come from the primary rid."""
    path = "run.%s" % field
    _rid_set = {rid} | set(extra_run_ids or [])

    def _find_run(o):
        for r in (getattr(o, "runs", None) or []):
            if getattr(r, "rid", None) == rid:
                return r
        # primary rid absent on this object: any linked rid stands in
        for r in (getattr(o, "runs", None) or []):
            if getattr(r, "rid", None) in _rid_set:
                return r
        return None

    def _find_runs(o):
        # v4.3.6.21: a variable can occupy SEVERAL spans (runs) in one object --
        # same rid on each. v4.4.0: linked rids are included, each variable
        # keeps its identity, only the value is shared.
        return [r for r in (getattr(o, "runs", None) or [])
                if getattr(r, "rid", None) in _rid_set]

    def _get(o):
        r = _find_run(o)
        if r is None:
            return None
        v = getattr(r, field, None)
        if field in _RUN_BOOL_FIELDS:
            return "true" if v else "false"
        return v

    def _set(o, v):
        runs = _find_runs(o)
        if not runs:
            return False
        if field in _RUN_BOOL_FIELDS:
            v = str(v).strip().lower() in ("true", "1", "yes", "on")
        for r in runs:
            setattr(r, field, v)
        if field == "text":
            try:
                o.text = "".join(rr.text for rr in (getattr(o, "runs", None) or []))
            except Exception:
                pass
        return True

    if kind == "number":
        return _attr_number(path, label, _get, _set, PRIO_STYLE)
    if kind == "color":
        return _attr_color(path, label, _get, _set, PRIO_STYLE)
    if kind == "enum":
        return _attr_enum(path, label, _RUN_ENUM_CHOICES.get(field, ["true", "false"]),
                          _get, _set, PRIO_STYLE)
    # text (the run's content) is the object's primary payload for that span
    return _attr_text(path, label, _get, _set,
                      PRIO_CONTENT if field == "text" else PRIO_STYLE)


def find_descriptor_with_run_id(obj, path, run_id, extra_run_ids=None):
    """Like find_descriptor, but for a run attribute path ('run.<field>') bind
    the descriptor to the run with stable id `run_id`. Falls back to the plain
    lookup if run_id is empty or the path isn't a run-field path.

    v4.4.0: extra_run_ids extends the binding to LINKED variables: the value
    fills every run whose rid is run_id OR in extra_run_ids, while each of
    those variables keeps its own identity (rid + name + panel entry)."""
    if not run_id or not path.startswith("run."):
        return find_descriptor(obj, path)
    field = path.split(".", 1)[1]
    spec = _RUN_FIELDS.get(field)
    if not spec:
        return None
    kind, label = spec
    return _run_field_descriptor(field, kind, label, run_id,
                                 extra_run_ids=extra_run_ids)
