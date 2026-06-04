# edof/format/svg_io.py
"""v4.1.13: SVG import/export utilities.

Two main functions:
  - svg_to_shapes(xml, box_x_mm, box_y_mm, box_w_mm, box_h_mm)
      Parse an SVG and return a list of native EDOF Shape (path) objects,
      sized and positioned within the given mm box.
  - shapes_to_svg(shapes, page_w_mm, page_h_mm)
      Serialize EDOF Shape (path) objects to an SVG XML string.

Only path shapes are exported. Other shape types (rect, ellipse, line, etc.)
are converted to equivalent SVG primitives where reasonable.

The parser supports paths via <path d="...">, plus simple primitives <rect>,
<circle>, <ellipse>, <line>, <polyline>, <polygon>. It does NOT understand
<g> transforms, gradients, masks, filters, or text. Use SvgBox (raster
display) for fidelity-preserving import of complex SVGs.
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from typing import List

from edof.format.objects import Shape, SHAPE_PATH, _parse_svg_path
from edof.format.styles import FillStyle, StrokeStyle


SVG_NS = "{http://www.w3.org/2000/svg}"


def _strip_ns(tag: str) -> str:
    """Remove SVG namespace prefix from a tag name."""
    if tag.startswith(SVG_NS):
        return tag[len(SVG_NS):]
    if tag.startswith("{"):
        end = tag.find("}")
        if end != -1: return tag[end + 1:]
    return tag


def _parse_length(s: str | None, default: float = 0.0) -> float:
    """Parse an SVG length string. Strips px/mm suffixes; falls back to float."""
    if s is None: return default
    s = s.strip()
    if not s: return default
    # Strip common units
    for suf in ("px", "pt", "mm", "cm", "in", "em", "%"):
        if s.endswith(suf):
            s = s[:-len(suf)]; break
    try:
        return float(s)
    except ValueError:
        return default


def _parse_color(s: str | None) -> tuple | None:
    """Parse SVG fill/stroke color. Returns (r,g,b,a) tuple or None for 'none'."""
    if s is None: return None
    s = s.strip().lower()
    if s in ("none", "transparent"): return None
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            r = int(h[0]*2, 16); g = int(h[1]*2, 16); b = int(h[2]*2, 16)
            return (r, g, b, 255)
        if len(h) == 6:
            r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
            return (r, g, b, 255)
    if s.startswith("rgb"):
        m = re.findall(r"\d+", s)
        if len(m) >= 3:
            return (int(m[0]), int(m[1]), int(m[2]), 255)
    # Named colors — basic set
    named = {
        "black": (0,0,0,255), "white": (255,255,255,255),
        "red": (255,0,0,255), "green": (0,128,0,255), "blue": (0,0,255,255),
        "yellow": (255,255,0,255), "cyan": (0,255,255,255),
        "magenta": (255,0,255,255), "gray": (128,128,128,255),
        "grey": (128,128,128,255), "orange": (255,165,0,255),
    }
    if s in named: return named[s]
    return (0, 0, 0, 255)   # fallback: opaque black


def _parse_style_attr(style: str) -> dict:
    """Parse SVG style="key:value; ..." into a dict."""
    out = {}
    for part in style.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _get_attr(elem, name, default=None):
    """Get attribute, checking inline first then 'style'."""
    v = elem.get(name)
    if v is not None: return v
    style = elem.get("style")
    if style:
        sd = _parse_style_attr(style)
        if name in sd: return sd[name]
    return default


def _path_data_bbox(path_data):
    """Compute the bbox of a path_data list (in its own coord system)."""
    xs = []; ys = []
    for cmd in path_data:
        if not cmd: continue
        op = cmd[0]
        if op == "M" or op == "L":
            xs.append(cmd[1]); ys.append(cmd[2])
        elif op == "C":
            xs.append(cmd[1]); ys.append(cmd[2])
            xs.append(cmd[3]); ys.append(cmd[4])
            xs.append(cmd[5]); ys.append(cmd[6])
        elif op == "Q":
            xs.append(cmd[1]); ys.append(cmd[2])
            xs.append(cmd[3]); ys.append(cmd[4])
    if not xs:
        return (0, 0, 1, 1)
    return (min(xs), min(ys), max(xs), max(ys))


def _shift_path_data(path_data, dx, dy):
    """Shift all coords in path_data by (dx, dy)."""
    for cmd in path_data:
        if not cmd: continue
        op = cmd[0]
        if op == "M" or op == "L":
            cmd[1] += dx; cmd[2] += dy
        elif op == "C":
            cmd[1] += dx; cmd[2] += dy
            cmd[3] += dx; cmd[4] += dy
            cmd[5] += dx; cmd[6] += dy
        elif op == "Q":
            cmd[1] += dx; cmd[2] += dy
            cmd[3] += dx; cmd[4] += dy


def _scale_path_data(path_data, sx, sy):
    """Scale all coords in path_data by (sx, sy)."""
    for cmd in path_data:
        if not cmd: continue
        op = cmd[0]
        if op == "M" or op == "L":
            cmd[1] *= sx; cmd[2] *= sy
        elif op == "C":
            cmd[1] *= sx; cmd[2] *= sy
            cmd[3] *= sx; cmd[4] *= sy
            cmd[5] *= sx; cmd[6] *= sy
        elif op == "Q":
            cmd[1] *= sx; cmd[2] *= sy
            cmd[3] *= sx; cmd[4] *= sy


def _primitive_to_path_data(elem) -> list | None:
    """Convert a <rect>, <circle>, <ellipse>, <line>, <polyline>, <polygon>
    element to an equivalent path_data list. Returns None for unknown tags."""
    tag = _strip_ns(elem.tag)
    if tag == "rect":
        x = _parse_length(elem.get("x"), 0)
        y = _parse_length(elem.get("y"), 0)
        w = _parse_length(elem.get("width"), 0)
        h = _parse_length(elem.get("height"), 0)
        return [
            ["M", x, y], ["L", x+w, y], ["L", x+w, y+h], ["L", x, y+h], ["Z"]
        ]
    if tag in ("circle", "ellipse"):
        cx = _parse_length(elem.get("cx"), 0)
        cy = _parse_length(elem.get("cy"), 0)
        if tag == "circle":
            rx = ry = _parse_length(elem.get("r"), 0)
        else:
            rx = _parse_length(elem.get("rx"), 0)
            ry = _parse_length(elem.get("ry"), 0)
        # Approximate with 4 cubic Beziers (k = 0.5522847498)
        k = 0.5522847498
        return [
            ["M", cx - rx, cy],
            ["C", cx - rx, cy - ry*k,  cx - rx*k, cy - ry,  cx, cy - ry],
            ["C", cx + rx*k, cy - ry,  cx + rx, cy - ry*k,  cx + rx, cy],
            ["C", cx + rx, cy + ry*k,  cx + rx*k, cy + ry,  cx, cy + ry],
            ["C", cx - rx*k, cy + ry,  cx - rx, cy + ry*k,  cx - rx, cy],
            ["Z"],
        ]
    if tag == "line":
        x1 = _parse_length(elem.get("x1"), 0)
        y1 = _parse_length(elem.get("y1"), 0)
        x2 = _parse_length(elem.get("x2"), 0)
        y2 = _parse_length(elem.get("y2"), 0)
        return [["M", x1, y1], ["L", x2, y2]]
    if tag in ("polyline", "polygon"):
        pts_str = elem.get("points", "")
        nums = [float(t) for t in re.findall(r"-?\d*\.?\d+(?:[eE][+-]?\d+)?", pts_str)]
        if len(nums) < 4: return None
        out = [["M", nums[0], nums[1]]]
        for i in range(2, len(nums) - 1, 2):
            out.append(["L", nums[i], nums[i+1]])
        if tag == "polygon":
            out.append(["Z"])
        return out
    return None


def svg_to_shapes(xml: str, box_x_mm: float, box_y_mm: float,
                    box_w_mm: float, box_h_mm: float) -> List[Shape]:
    """Parse an SVG and return EDOF Shape (path) objects scaled to fit the
    given mm box. SVG <path>, <rect>, <circle>, <ellipse>, <line>,
    <polyline>, <polygon> are extracted as paths. Other elements (text,
    embedded images, gradients) are ignored — use SvgBox raster for those.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []

    # Get viewBox or width/height for scale
    vb = (root.get("viewBox") or "").split()
    if len(vb) == 4:
        vx, vy, vw, vh = (float(t) for t in vb)
    else:
        vw = _parse_length(root.get("width"), 100)
        vh = _parse_length(root.get("height"), 100)
        vx = 0; vy = 0
    if vw <= 0 or vh <= 0:
        vw = vh = 100

    sx = box_w_mm / vw
    sy = box_h_mm / vh

    shapes = []
    for elem in root.iter():
        tag = _strip_ns(elem.tag)
        path_data = None
        if tag == "path":
            d = elem.get("d", "")
            if d: path_data = _parse_svg_path(d)
        else:
            path_data = _primitive_to_path_data(elem)
        if not path_data: continue

        # Shift by viewBox origin
        if vx != 0 or vy != 0:
            _shift_path_data(path_data, -vx, -vy)
        # Scale to mm
        _scale_path_data(path_data, sx, sy)

        # Normalize: shift so path bbox starts at (0,0); shape transform
        # carries the offset within the larger box.
        mnx, mny, mxx, mxy = _path_data_bbox(path_data)
        _shift_path_data(path_data, -mnx, -mny)

        sh = Shape(shape_type=SHAPE_PATH)
        sh.path_data = path_data
        sh.transform.x = box_x_mm + mnx
        sh.transform.y = box_y_mm + mny
        sh.transform.width = max(1.0, mxx - mnx)
        sh.transform.height = max(1.0, mxy - mny)

        # Parse fill, stroke
        fill_c = _parse_color(_get_attr(elem, "fill", "black" if tag != "path" else "black"))
        stroke_c = _parse_color(_get_attr(elem, "stroke"))
        sw = _parse_length(_get_attr(elem, "stroke-width"), 1) * min(sx, sy)
        if fill_c is None:
            sh.fill.color = None
        else:
            sh.fill.color = fill_c
        if stroke_c is not None:
            sh.stroke.color = stroke_c
            # Convert mm to pt (72/25.4)
            sh.stroke.width = max(0.5, sw * 72 / 25.4)
        else:
            sh.stroke.width = 0   # no stroke
            sh.stroke.color = (0, 0, 0, 0)

        # Path point types: default 'smooth' for C, 'corner' for L/M
        sh.path_point_types = []
        for cmd in path_data:
            if cmd and cmd[0] in ("C", "Q"):
                sh.path_point_types.append("smooth")
            else:
                sh.path_point_types.append("corner")

        shapes.append(sh)

    return shapes


def shapes_to_svg(shapes: List[Shape], page_w_mm: float, page_h_mm: float) -> str:
    """Serialize EDOF path shapes to an SVG XML string. Coords are in mm
    (viewBox 0 0 W H, width/height in mm units)."""
    parts = []
    parts.append(f'<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                  f'viewBox="0 0 {page_w_mm:.4f} {page_h_mm:.4f}" '
                  f'width="{page_w_mm:.4f}mm" height="{page_h_mm:.4f}mm">')
    for sh in shapes:
        if not hasattr(sh, "path_data") or not sh.path_data:
            continue
        if getattr(sh, "shape_type", None) != "path":
            continue
        # Build d string with absolute coords offset by transform.x/y
        d_parts = []
        ox = sh.transform.x; oy = sh.transform.y
        for cmd in sh.path_data:
            if not cmd: continue
            op = cmd[0]
            if op == "M":
                d_parts.append(f"M{ox+cmd[1]:.4f} {oy+cmd[2]:.4f}")
            elif op == "L":
                d_parts.append(f"L{ox+cmd[1]:.4f} {oy+cmd[2]:.4f}")
            elif op == "C":
                d_parts.append(f"C{ox+cmd[1]:.4f} {oy+cmd[2]:.4f} "
                                f"{ox+cmd[3]:.4f} {oy+cmd[4]:.4f} "
                                f"{ox+cmd[5]:.4f} {oy+cmd[6]:.4f}")
            elif op == "Q":
                d_parts.append(f"Q{ox+cmd[1]:.4f} {oy+cmd[2]:.4f} "
                                f"{ox+cmd[3]:.4f} {oy+cmd[4]:.4f}")
            elif op == "Z":
                d_parts.append("Z")
        d_str = " ".join(d_parts)
        # Fill/stroke styles
        fill = "none"
        if sh.fill and sh.fill.color:
            r, g, b, a = sh.fill.color
            fill = f"rgb({r},{g},{b})"
        stroke = "none"
        sw_pt = 0
        if sh.stroke and sh.stroke.color and sh.stroke.color[3] > 0:
            r, g, b, a = sh.stroke.color
            stroke = f"rgb({r},{g},{b})"
            # pt → mm: 25.4/72
            sw_pt = (sh.stroke.width or 1) * 25.4 / 72.0
        parts.append(f'  <path d="{d_str}" fill="{fill}" stroke="{stroke}" '
                      f'stroke-width="{sw_pt:.4f}"/>')
    parts.append('</svg>')
    return "\n".join(parts)
