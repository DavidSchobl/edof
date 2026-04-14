# edof/engine/transform.py
"""
2-D spatial transform for document objects.
Internal unit: millimetres (mm).
Rotation: degrees, clockwise, pivot = bounding-box centre.
"""

from __future__ import annotations
import copy
import math
from dataclasses import dataclass
from typing import Tuple

Point = Tuple[float, float]

# ── Unit conversion ────────────────────────────────────────────────────────────

_TO_MM: dict[str, float] = {
    "mm":   1.0,
    "cm":   10.0,
    "inch": 25.4,
    "in":   25.4,
    "pt":   25.4 / 72.0,
    "px":   25.4 / 96.0,   # at 96 dpi (screen default)
}


def to_mm(value: float, unit: str = "mm") -> float:
    return value * _TO_MM.get(unit, 1.0)


def from_mm(value: float, unit: str = "mm") -> float:
    return value / _TO_MM.get(unit, 1.0)


def mm_to_px(mm: float, dpi: float) -> float:
    return mm * dpi / 25.4


def px_to_mm(px: float, dpi: float) -> float:
    return px * 25.4 / dpi


# ── Point geometry ─────────────────────────────────────────────────────────────

def rotate_point(px: float, py: float,
                 cx: float, cy: float,
                 angle_deg: float) -> Point:
    """Rotate (px, py) clockwise around (cx, cy) by angle_deg."""
    r = math.radians(angle_deg)
    cos_a, sin_a = math.cos(r), math.sin(r)
    dx, dy = px - cx, py - cy
    return (cx + dx * cos_a - dy * sin_a,
            cy + dx * sin_a + dy * cos_a)


# ── Transform ──────────────────────────────────────────────────────────────────

@dataclass
class Transform:
    """
    Represents the full spatial state of a document object.

    ``x``, ``y``  – top-left corner position in mm (before rotation)
    ``width``      – mm
    ``height``     – mm
    ``rotation``   – clockwise degrees around the bounding-box centre
    ``flip_h``     – horizontal flip (applied before rotation)
    ``flip_v``     – vertical flip (applied before rotation)
    """
    x:        float = 0.0
    y:        float = 0.0
    width:    float = 50.0
    height:   float = 30.0
    rotation: float = 0.0
    flip_h:   bool  = False
    flip_v:   bool  = False

    # ── Computed geometry ──────────────────────────────────────────────────────

    @property
    def center(self) -> Point:
        return self.x + self.width / 2.0, self.y + self.height / 2.0

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def corners(self) -> list[Point]:
        """Four corners after rotation."""
        cx, cy = self.center
        raw: list[Point] = [
            (self.x,              self.y),
            (self.x + self.width, self.y),
            (self.x + self.width, self.y + self.height),
            (self.x,              self.y + self.height),
        ]
        return [rotate_point(px, py, cx, cy, self.rotation) for px, py in raw]

    @property
    def bounding_box(self) -> tuple[float, float, float, float]:
        """Axis-aligned bounding box (x, y, w, h) after rotation."""
        pts = self.corners
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = min(xs), min(ys)
        return x0, y0, max(xs) - x0, max(ys) - y0

    # ── Movement ───────────────────────────────────────────────────────────────

    def translate(self, dx: float, dy: float, unit: str = "mm") -> "Transform":
        self.x += to_mm(dx, unit)
        self.y += to_mm(dy, unit)
        return self

    def move_to(self, x: float, y: float, unit: str = "mm") -> "Transform":
        self.x = to_mm(x, unit)
        self.y = to_mm(y, unit)
        return self

    def center_on(self, cx: float, cy: float, unit: str = "mm") -> "Transform":
        """Position so the object's centre is at (cx, cy)."""
        cx_mm = to_mm(cx, unit)
        cy_mm = to_mm(cy, unit)
        self.x = cx_mm - self.width  / 2.0
        self.y = cy_mm - self.height / 2.0
        return self

    # ── Resize ─────────────────────────────────────────────────────────────────

    def resize_uniform(self, factor: float,
                       anchor: str = "center") -> "Transform":
        """Scale width and height by the same factor."""
        cx, cy = self.center
        self.width  *= factor
        self.height *= factor
        if anchor == "center":
            self.x = cx - self.width  / 2.0
            self.y = cy - self.height / 2.0
        return self

    def resize_free(self, new_width: float, new_height: float,
                    unit: str = "mm",
                    anchor: str = "top-left") -> "Transform":
        """Set absolute width and height; anchor = 'top-left' | 'center'."""
        cx, cy = self.center
        self.width  = to_mm(new_width,  unit)
        self.height = to_mm(new_height, unit)
        if anchor == "center":
            self.x = cx - self.width  / 2.0
            self.y = cy - self.height / 2.0
        return self

    def resize_to_fit(self, max_w: float, max_h: float,
                      unit: str = "mm") -> "Transform":
        """Uniformly scale so the object fits within (max_w × max_h)."""
        mw = to_mm(max_w, unit)
        mh = to_mm(max_h, unit)
        scale = min(mw / self.width, mh / self.height)
        return self.resize_uniform(scale)

    def set_width_keep_ratio(self, new_width: float,
                             unit: str = "mm") -> "Transform":
        nw = to_mm(new_width, unit)
        ratio = nw / self.width
        self.width  = nw
        self.height *= ratio
        return self

    def set_height_keep_ratio(self, new_height: float,
                              unit: str = "mm") -> "Transform":
        nh = to_mm(new_height, unit)
        ratio = nh / self.height
        self.height = nh
        self.width  *= ratio
        return self

    # ── Rotation ───────────────────────────────────────────────────────────────

    def rotate(self, angle_deg: float) -> "Transform":
        """Add angle_deg (clockwise) to current rotation."""
        self.rotation = (self.rotation + angle_deg) % 360.0
        return self

    def rotate_to(self, angle_deg: float) -> "Transform":
        """Set absolute rotation."""
        self.rotation = angle_deg % 360.0
        return self

    def rotate_around(self, pivot_x: float, pivot_y: float,
                      angle_deg: float,
                      unit: str = "mm") -> "Transform":
        """Rotate the entire object around an arbitrary point."""
        px = to_mm(pivot_x, unit)
        py = to_mm(pivot_y, unit)
        new_tl = rotate_point(self.x, self.y, px, py, angle_deg)
        self.x = new_tl[0]
        self.y = new_tl[1]
        self.rotation = (self.rotation + angle_deg) % 360.0
        return self

    # ── Flip ───────────────────────────────────────────────────────────────────

    def flip_horizontal(self) -> "Transform":
        self.flip_h = not self.flip_h
        return self

    def flip_vertical(self) -> "Transform":
        self.flip_v = not self.flip_v
        return self

    # ── Serialization ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
            "rotation": self.rotation,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transform":
        return cls(
            x        = float(d.get("x",         0.0)),
            y        = float(d.get("y",         0.0)),
            width    = float(d.get("width",    50.0)),
            height   = float(d.get("height",   30.0)),
            rotation = float(d.get("rotation",  0.0)),
            flip_h   = bool( d.get("flip_h",  False)),
            flip_v   = bool( d.get("flip_v",  False)),
        )

    def copy(self) -> "Transform":
        return copy.deepcopy(self)
