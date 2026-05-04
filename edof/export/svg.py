# edof/export/svg.py
"""
v4.0: SVG export.

Renders one EDOF page as an SVG file:
  - Text as <text> elements (searchable, copyable)
  - Shapes as <rect>, <ellipse>, <line>, <polygon>, <path>
  - Gradients as <linearGradient> / <radialGradient>
  - Images embedded as base64 data URIs
"""
from __future__ import annotations
import base64
import io
import math
import xml.sax.saxutils as _xml
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edof.format.document import Document


def export_svg(doc, path: str, page: int = 0) -> None:
    """Export a single page to an SVG file."""
    from edof.utils.safe_eval import is_visible

    p = doc.pages[page]
    parts = []
    parts.append(_svg_header(p.width, p.height, doc.title))

    # Background
    bg = p.background
    if bg and tuple(bg[:3]) != (255, 255, 255):
        parts.append(f'<rect width="{p.width}" height="{p.height}" '
                     f'fill="{_color(bg)}" />')

    # Defs (gradients, images) collected during emit
    defs = []
    body = []
    ctx = {"doc": doc, "defs": defs, "_id": 0}

    for obj in p.sorted_objects():
        if not is_visible(obj, doc.variables):
            continue
        body.extend(_emit(obj, ctx))

    if defs:
        parts.append("<defs>")
        parts.extend(defs)
        parts.append("</defs>")
    parts.extend(body)
    parts.append("</svg>")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def _svg_header(w_mm, h_mm, title=""):
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w_mm}mm" height="{h_mm}mm" '
        f'viewBox="0 0 {w_mm} {h_mm}">\n'
        f'<title>{_xml.escape(title or "EDOF Document")}</title>'
    )


def _color(c):
    if c is None: return "none"
    if len(c) >= 4 and c[3] < 255:
        return f"rgba({int(c[0])},{int(c[1])},{int(c[2])},{c[3]/255:.3f})"
    return f"rgb({int(c[0])},{int(c[1])},{int(c[2])})"


def _emit(obj, ctx):
    from edof.format.objects import (TextBox, ImageBox, Shape, QRCode, Group, Table)
    if isinstance(obj, TextBox):  return _emit_textbox(obj, ctx)
    if isinstance(obj, ImageBox): return _emit_imagebox(obj, ctx)
    if isinstance(obj, Shape):    return _emit_shape(obj, ctx)
    if isinstance(obj, QRCode):   return _emit_qrcode(obj, ctx)
    if isinstance(obj, Table):    return _emit_table(obj, ctx)
    if isinstance(obj, Group):
        from edof.utils.safe_eval import is_visible
        out = []
        for child in obj.flatten():
            if is_visible(child, ctx["doc"].variables):
                out.extend(_emit(child, ctx))
        return out
    return []


def _emit_textbox(obj, ctx):
    t = obj.transform
    pad = getattr(obj.style, "padding", 1.0)
    out = []

    if obj.fill and obj.fill.color:
        c = obj.fill.color
        if len(c) < 4 or c[3] > 0:
            out.append(f'<rect x="{t.x}" y="{t.y}" width="{t.width}" '
                       f'height="{t.height}" fill="{_color(c)}" />')

    if obj.border:
        out.append(f'<rect x="{t.x}" y="{t.y}" width="{t.width}" '
                   f'height="{t.height}" fill="none" '
                   f'stroke="{_color(obj.border.color)}" '
                   f'stroke-width="{obj.border.width / 72 * 25.4}" />')

    if obj.runs:
        out.extend(_emit_runs(obj, t.x + pad, t.y + pad,
                               t.width - 2*pad, t.height - 2*pad))
    else:
        text = obj.get_resolved_text(ctx["doc"].variables)
        if not text: return out

        font_w = "bold" if obj.style.bold else "normal"
        font_s = "italic" if obj.style.italic else "normal"
        deco   = []
        if obj.style.underline:     deco.append("underline")
        if obj.style.strikethrough: deco.append("line-through")

        # Approximate vertical alignment
        font_size_mm = obj.style.font_size / 72 * 25.4
        if   obj.style.vertical_align == "middle": y_text = t.y + t.height/2 + font_size_mm * 0.35
        elif obj.style.vertical_align == "bottom": y_text = t.y + t.height - pad
        else:                                       y_text = t.y + pad + font_size_mm * 0.8

        anchor = {"left": "start", "center": "middle", "right": "end"}.get(obj.style.alignment, "start")
        if   anchor == "middle": x_text = t.x + t.width / 2
        elif anchor == "end":    x_text = t.x + t.width - pad
        else:                     x_text = t.x + pad

        deco_attr = f' text-decoration="{" ".join(deco)}"' if deco else ""
        # Split lines
        for i, line in enumerate(text.replace("\r\n","\n").split("\n")):
            if not line: continue
            line_y = y_text + i * font_size_mm * obj.style.line_height
            out.append(
                f'<text x="{x_text}" y="{line_y}" '
                f'font-family="{_xml.escape(obj.style.font_family)}" '
                f'font-size="{obj.style.font_size}pt" '
                f'font-weight="{font_w}" font-style="{font_s}"'
                f'{deco_attr} '
                f'fill="{_color(obj.style.color)}" '
                f'text-anchor="{anchor}">{_xml.escape(line)}</text>'
            )
    return out


def _emit_runs(obj, x_mm, y_mm, w_mm, h_mm):
    """Emit rich-text runs as <tspan> elements within a <text>."""
    out = []
    parent = obj.style
    # Approximate baseline
    line_h_mm = parent.font_size / 72 * 25.4 * parent.line_height
    base_y = y_mm + parent.font_size / 72 * 25.4 * 0.8

    # Build single <text> element with multiple <tspan>s
    spans = []
    for run in obj.runs:
        rs = run.resolve(parent, scale=1.0)
        weight = "bold" if rs["bold"] else "normal"
        style  = "italic" if rs["italic"] else "normal"
        deco   = []
        if rs.get("underline"): deco.append("underline")
        if rs.get("strikethrough"): deco.append("line-through")
        deco_attr = f' text-decoration="{" ".join(deco)}"' if deco else ""
        color = rs["color"] if rs["color"] else (0, 0, 0)
        span = (f'<tspan font-family="{_xml.escape(rs["font_family"])}" '
                f'font-size="{rs["font_size"]}pt" '
                f'font-weight="{weight}" font-style="{style}"'
                f'{deco_attr} '
                f'fill="{_color(color)}">{_xml.escape(run.text)}</tspan>')
        spans.append(span)

    out.append(f'<text x="{x_mm}" y="{base_y}">{"".join(spans)}</text>')
    return out


def _emit_shape(obj, ctx):
    from edof.format.objects import (
        SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE, SHAPE_POLYGON, SHAPE_PATH,
    )
    t = obj.transform
    fill   = obj.fill.color
    stroke = obj.stroke.color
    sw     = obj.stroke.width / 72 * 25.4

    fill_attr = "none"
    if obj.fill.gradient:
        ctx["_id"] += 1
        gid = f"grad{ctx['_id']}"
        ctx["defs"].append(_emit_gradient_def(obj.fill.gradient, gid))
        fill_attr = f"url(#{gid})"
    elif fill:
        fill_attr = _color(fill)

    stroke_str = _color(stroke) if stroke else "none"

    out = []
    if obj.shape_type == SHAPE_RECT:
        rx = obj.corner_radius
        out.append(
            f'<rect x="{t.x}" y="{t.y}" width="{t.width}" height="{t.height}" '
            f'rx="{rx}" ry="{rx}" '
            f'fill="{fill_attr}" stroke="{stroke_str}" stroke-width="{sw}" />'
        )
    elif obj.shape_type == SHAPE_ELLIPSE:
        out.append(
            f'<ellipse cx="{t.x + t.width/2}" cy="{t.y + t.height/2}" '
            f'rx="{t.width/2}" ry="{t.height/2}" '
            f'fill="{fill_attr}" stroke="{stroke_str}" stroke-width="{sw}" />'
        )
    elif obj.shape_type == SHAPE_LINE:
        if obj.points and len(obj.points) >= 2:
            p1, p2 = obj.points[0], obj.points[1]
            out.append(f'<line x1="{p1[0]}" y1="{p1[1]}" x2="{p2[0]}" y2="{p2[1]}" '
                       f'stroke="{stroke_str}" stroke-width="{sw}" />')
        else:
            out.append(f'<line x1="{t.x}" y1="{t.y}" x2="{t.x + t.width}" y2="{t.y + t.height}" '
                       f'stroke="{stroke_str}" stroke-width="{sw}" />')
    elif obj.shape_type == SHAPE_POLYGON:
        if obj.points:
            pts = " ".join(f"{x},{y}" for x, y in obj.points)
            out.append(f'<polygon points="{pts}" '
                       f'fill="{fill_attr}" stroke="{stroke_str}" stroke-width="{sw}" />')
    elif obj.shape_type == SHAPE_PATH:
        if obj.path_data:
            d = _path_to_svg_d(obj.path_data)
            out.append(f'<path d="{d}" '
                       f'fill="{fill_attr}" stroke="{stroke_str}" stroke-width="{sw}" />')
    return out


def _path_to_svg_d(path_data):
    parts = []
    for cmd in path_data:
        if not cmd: continue
        op = cmd[0]
        if op in ("M", "L"):
            parts.append(f"{op}{cmd[1]} {cmd[2]}")
        elif op == "C":
            parts.append(f"C{cmd[1]} {cmd[2]} {cmd[3]} {cmd[4]} {cmd[5]} {cmd[6]}")
        elif op == "Q":
            parts.append(f"Q{cmd[1]} {cmd[2]} {cmd[3]} {cmd[4]}")
        elif op == "Z":
            parts.append("Z")
    return " ".join(parts)


def _emit_gradient_def(gradient, gid):
    stops = "\n".join(
        f'  <stop offset="{off}" stop-color="{_color(c)}" />'
        for off, c in sorted(gradient.stops, key=lambda s: s[0])
    )
    if gradient.type == "linear":
        ang = math.radians(gradient.angle)
        x2 = math.cos(ang); y2 = math.sin(ang)
        return (f'<linearGradient id="{gid}" gradientUnits="objectBoundingBox" '
                f'x1="0" y1="0" x2="{x2}" y2="{y2}">\n{stops}\n</linearGradient>')
    else:
        cx, cy = gradient.center
        return (f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{gradient.radius}">\n'
                f'{stops}\n</radialGradient>')


def _emit_imagebox(obj, ctx):
    if not obj.resource_id or obj.resource_id not in ctx["doc"].resources:
        return []
    entry = ctx["doc"].resources.get(obj.resource_id)
    if not entry: return []
    mime = entry.mime_type or "image/png"
    b64  = base64.b64encode(entry.data).decode("ascii")
    t    = obj.transform
    return [
        f'<image x="{t.x}" y="{t.y}" width="{t.width}" height="{t.height}" '
        f'xlink:href="data:{mime};base64,{b64}" />'
    ]


def _emit_qrcode(obj, ctx):
    """Render QR as PNG and embed."""
    try:
        import qrcode as qrlib
    except ImportError:
        return []
    from PIL import Image

    data = obj.get_resolved_data(ctx["doc"].variables)
    if not data: return []

    ec = {"L": qrlib.constants.ERROR_CORRECT_L, "M": qrlib.constants.ERROR_CORRECT_M,
          "Q": qrlib.constants.ERROR_CORRECT_Q, "H": qrlib.constants.ERROR_CORRECT_H}
    qr = qrlib.QRCode(error_correction=ec.get(obj.error_correction, ec["M"]),
                       border=obj.border_modules)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    if obj.fg_color[:3] != (0,0,0) or obj.bg_color[:3] != (255,255,255):
        pixels = img.load(); fg = obj.fg_color[:3]; bg = obj.bg_color[:3]
        for x in range(img.width):
            for y in range(img.height):
                r, _, _ = pixels[x, y]
                pixels[x, y] = fg if r < 128 else bg

    buf = io.BytesIO(); img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    t = obj.transform
    size = min(t.width, t.height)
    return [f'<image x="{t.x}" y="{t.y}" width="{size}" height="{size}" '
            f'xlink:href="data:image/png;base64,{b64}" />']


def _emit_table(obj, ctx):
    t = obj.transform
    n_rows = obj.num_rows; n_cols = obj.num_cols
    if n_rows == 0 or n_cols == 0: return []

    col_w = list(obj.col_widths) + [0] * max(0, n_cols - len(obj.col_widths))
    explicit_w = sum(w for w in col_w if w > 0)
    auto_cols = sum(1 for w in col_w if w == 0)
    auto_w = (t.width - explicit_w) / auto_cols if auto_cols > 0 else 0
    col_w_mm = [w if w > 0 else auto_w for w in col_w]

    row_h = list(obj.row_heights) + [0] * max(0, n_rows - len(obj.row_heights))
    explicit_h = sum(h for h in row_h if h > 0)
    auto_rows = sum(1 for h in row_h if h == 0)
    auto_h = (t.height - explicit_h) / auto_rows if auto_rows > 0 else 0
    row_h_mm = [h if h > 0 else auto_h for h in row_h]

    x_off = [0]
    for w in col_w_mm[:-1]: x_off.append(x_off[-1] + w)
    y_off = [0]
    for h in row_h_mm[:-1]: y_off.append(y_off[-1] + h)

    out = []
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = obj.cells[ri][ci]
            cx = t.x + x_off[ci]; cy = t.y + y_off[ri]
            cw = sum(col_w_mm[ci:ci + cell.colspan])
            ch = sum(row_h_mm[ri:ri + cell.rowspan])
            bg = cell.bg_color
            if bg and len(bg) >= 4 and bg[3] > 0:
                out.append(f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" '
                           f'fill="{_color(bg)}" />')
            cell_text = cell.text
            if ctx["doc"].variables and "{" in cell_text:
                for name in ctx["doc"].variables.names():
                    v = ctx["doc"].variables.get(name)
                    if v is not None:
                        cell_text = cell_text.replace("{" + name + "}", str(v))
            if cell_text:
                font_size_mm = cell.style.font_size / 72 * 25.4
                ty = cy + ch/2 + font_size_mm * 0.35
                tx = cx + cw/2
                out.append(
                    f'<text x="{tx}" y="{ty}" text-anchor="middle" '
                    f'font-family="{_xml.escape(cell.style.font_family)}" '
                    f'font-size="{cell.style.font_size}pt" '
                    f'font-weight="{"bold" if cell.style.bold else "normal"}" '
                    f'fill="{_color(cell.style.color)}">{_xml.escape(cell_text)}</text>'
                )
            # Borders
            for side, x1, y1, x2, y2 in [
                (cell.border_top,    cx,    cy,    cx+cw, cy),
                (cell.border_right,  cx+cw, cy,    cx+cw, cy+ch),
                (cell.border_bottom, cx,    cy+ch, cx+cw, cy+ch),
                (cell.border_left,   cx,    cy,    cx,    cy+ch),
            ]:
                if side.enabled:
                    out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                               f'stroke="{_color(side.color)}" '
                               f'stroke-width="{side.width}" />')
    return out
