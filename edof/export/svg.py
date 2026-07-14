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
    from edof.format.objects import (TextBox, ImageBox, Shape, QRCode, Group, Table, SvgBox)
    if isinstance(obj, Group):
        from edof.utils.safe_eval import is_visible
        out = []
        for child in obj.flatten():
            if is_visible(child, ctx["doc"].variables):
                out.extend(_emit(child, ctx))
        # v4.3.5.54: a rotated group wraps its children in a rotation about the
        # group center (children are in the group's local, un-rotated space).
        return _wrap_transform(obj, out)
    if isinstance(obj, TextBox):  inner = _emit_textbox(obj, ctx)
    elif isinstance(obj, ImageBox): inner = _emit_imagebox(obj, ctx)
    elif isinstance(obj, SvgBox):   inner = _emit_svgbox(obj, ctx)
    elif isinstance(obj, Shape):    inner = _emit_shape(obj, ctx)
    elif isinstance(obj, QRCode):   inner = _emit_qrcode(obj, ctx)
    elif isinstance(obj, Table):    inner = _emit_table(obj, ctx)
    else: return []
    # v4.3.5.54: apply the object's rotation and shear (previously ignored on
    # export) as an SVG transform about the object's center.
    return _wrap_transform(obj, inner)


def _wrap_transform(obj, inner):
    """v4.3.5.54: wrap an object's SVG output in a <g> that applies its rotation
    and horizontal shear about the object's center, matching the renderer
    (local -> shear -> rotate). No-op when there's no rotation/shear/flip."""
    t = obj.transform
    rot = getattr(t, "rotation", 0) or 0
    shx = getattr(t, "shear_x", 0.0) or 0.0
    fh = getattr(t, "flip_h", False)
    fv = getattr(t, "flip_v", False)
    if rot % 360 == 0 and not shx and not fh and not fv:
        return inner
    cx = t.x + t.width / 2.0
    cy = t.y + t.height / 2.0
    # SVG transforms apply right-to-left: move to center, rotate, shear, flip,
    # move back -- so a local point is flipped, sheared, then rotated (== render).
    parts = [f"translate({cx},{cy})"]
    if rot % 360 != 0:
        parts.append(f"rotate({rot})")
    if shx:
        parts.append(f"matrix(1,0,{shx},1,0,0)")     # x' = x + shx*y
    if fh or fv:
        parts.append(f"scale({-1 if fh else 1},{-1 if fv else 1})")
    parts.append(f"translate({-cx},{-cy})")
    g_open = '<g transform="' + " ".join(parts) + '">'
    return [g_open] + list(inner) + ["</g>"]


def _emit_svgbox(obj, ctx):
    """v4.1.13: Embed an SvgBox's original SVG XML as a nested <g> with
    appropriate transforms. We strip the outer <svg> tag to inline the
    contents into the parent <svg>."""
    import re as _re
    t = obj.transform
    xml = obj.svg_xml or ""
    if not xml: return []
    # Extract inner content between <svg ...> and </svg>
    m = _re.search(r"<svg\b[^>]*>(.*)</svg>", xml, _re.DOTALL | _re.IGNORECASE)
    if not m: return []
    inner = m.group(1)
    # Extract viewBox / width / height from the outer svg
    head_m = _re.search(r"<svg\b([^>]*)>", xml, _re.IGNORECASE)
    head = head_m.group(1) if head_m else ""
    vb_m = _re.search(r'viewBox="([^"]+)"', head)
    if vb_m:
        try:
            vx, vy, vw, vh = (float(x) for x in vb_m.group(1).split())
        except Exception:
            vx, vy, vw, vh = 0, 0, 100, 100
    else:
        vx, vy, vw, vh = 0, 0, 100, 100
    if vw <= 0: vw = 100
    if vh <= 0: vh = 100
    sx = t.width / vw
    sy = t.height / vh
    return [
        f'<g transform="translate({t.x},{t.y}) scale({sx},{sy}) '
        f'translate({-vx},{-vy})">',
        inner,
        '</g>',
    ]


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

        # v4.1.17: obj.style.font_size is now in mm directly
        font_size_mm = obj.style.font_size
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
                f'font-size="{font_size_mm}mm" '
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
    # v4.1.17: parent.font_size is now mm
    line_h_mm = parent.font_size * parent.line_height
    base_y = y_mm + parent.font_size * 0.8

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
                f'font-size="{rs["font_size"]}mm" '
                f'font-weight="{weight}" font-style="{style}"'
                f'{deco_attr} '
                f'fill="{_color(color)}">{_xml.escape(run.text)}</tspan>')
        # v4.4.0: a link run becomes a clickable <a> (SVG allows <a> inside
        # <text>). Only whitelisted targets are emitted; in-document anchors
        # become fragment refs (viewers may ignore them, harmless).
        _lnk = getattr(run, "link", None)
        if _lnk:
            from edof.utils.links import validate_link
            _safe = validate_link(_lnk)
            if _safe is not None:
                _href = _xml.escape(_safe, {'"': "&quot;"})
                _tgt = "" if _safe.startswith("#") else ' target="_blank"'
                span = (f'<a href="{_href}" xlink:href="{_href}"{_tgt}>'
                        f'{span}</a>')
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
            # v4.3.5.48: line points are LOCAL -> add the transform origin
            p1, p2 = obj.points[0], obj.points[1]
            x1, y1 = p1[0] + t.x, p1[1] + t.y
            x2, y2 = p2[0] + t.x, p2[1] + t.y
            out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
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
            # v4.1.13.2: path_data is in LOCAL coords (relative to
            # transform.x/y). For correct SVG positioning, we need to
            # shift by (t.x, t.y) so the path appears at the same place
            # in the exported SVG.
            d = _path_to_svg_d(obj.path_data, dx=t.x, dy=t.y)
            out.append(f'<path d="{d}" '
                       f'fill="{fill_attr}" stroke="{stroke_str}" stroke-width="{sw}" />')
    return out


def _path_to_svg_d(path_data, dx=0.0, dy=0.0):
    """v4.1.13.2: optionally shift all coords by (dx, dy) on output."""
    parts = []
    for cmd in path_data:
        if not cmd: continue
        op = cmd[0]
        if op in ("M", "L"):
            parts.append(f"{op}{cmd[1]+dx} {cmd[2]+dy}")
        elif op == "C":
            parts.append(f"C{cmd[1]+dx} {cmd[2]+dy} "
                          f"{cmd[3]+dx} {cmd[4]+dy} "
                          f"{cmd[5]+dx} {cmd[6]+dy}")
        elif op == "Q":
            parts.append(f"Q{cmd[1]+dx} {cmd[2]+dy} "
                          f"{cmd[3]+dx} {cmd[4]+dy}")
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
    # v4.4.0 (BUG #10 regression): resource_id may be a FILE PATH (that is
    # how a batch fills an image column). The raster renderer resolved paths
    # since 4.3.6.27, but the SVG/PDF exports still required a resource-store
    # key, so batch-filled images silently vanished from exports.
    data = None
    mime = "image/png"
    if obj.resource_id and obj.resource_id in ctx["doc"].resources:
        entry = ctx["doc"].resources.get(obj.resource_id)
        if not entry: return []
        data = entry.data
        mime = entry.mime_type or "image/png"
    else:
        import os as _os
        rid = obj.resource_id
        if rid and isinstance(rid, str) and _os.path.isfile(rid):
            try:
                with open(rid, "rb") as _f:
                    data = _f.read()
                _ext = _os.path.splitext(rid)[1].lower().lstrip(".")
                mime = ("image/jpeg" if _ext in ("jpg", "jpeg")
                        else "image/%s" % (_ext or "png"))
            except Exception:
                return []
    if data is None:
        return []
    b64  = base64.b64encode(data).decode("ascii")
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
    # v4.4.0 perf: precompute the {variable} replacement pairs once per table
    _var_repl = None
    try:
        _vars = ctx["doc"].variables
        if _vars:
            _var_repl = [("{" + n + "}", str(_vars.get(n)))
                         for n in _vars.names() if _vars.get(n) is not None]
    except Exception:
        _var_repl = None
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
            if _var_repl and "{" in cell_text:
                for k, v in _var_repl:
                    if k in cell_text:
                        cell_text = cell_text.replace(k, v)
            if cell_text:
                font_size_mm = cell.style.font_size  # v4.1.17: already mm
                ty = cy + ch/2 + font_size_mm * 0.35
                tx = cx + cw/2
                out.append(
                    f'<text x="{tx}" y="{ty}" text-anchor="middle" '
                    f'font-family="{_xml.escape(cell.style.font_family)}" '
                    f'font-size="{font_size_mm}mm" '
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
