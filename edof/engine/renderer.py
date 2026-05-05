# edof/engine/renderer.py
"""v4.0: rich text, tables, vector paths, gradients, blend modes, conditional visibility."""
from __future__ import annotations
import io, os, math
from typing import Optional, TYPE_CHECKING
from PIL import Image, ImageDraw, ImageChops
from edof.engine.color import convert_image
from edof.engine.transform import mm_to_px, rotate_point
from edof.engine.text_engine import render_text_onto, render_runs_onto, find_fitting_scale
from edof.format.objects import (EdofObject, TextBox, ImageBox, Shape,
                                  QRCode, Group, Table,
                                  SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE,
                                  SHAPE_POLYGON, SHAPE_ARROW, SHAPE_PATH)
from edof.utils.safe_eval import is_visible


def _rgba(c, default=(0, 0, 0, 255)) -> tuple:
    if c is None: return None
    t = tuple(int(v) for v in c)
    return (*t, 255) if len(t) == 3 else t[:4]


def render_page(page, resources, variables,
                dpi=None, color_space=None, bit_depth=None) -> Image.Image:
    dpi_r = dpi or page.dpi
    cs_r  = color_space or page.color_space
    bd_r  = bit_depth or page.bit_depth
    w_px  = max(1, int(mm_to_px(page.width,  dpi_r)))
    h_px  = max(1, int(mm_to_px(page.height, dpi_r)))
    bg    = _rgba(page.background, (255, 255, 255, 255))
    canvas = Image.new("RGBA", (w_px, h_px), bg[:4])
    for obj in page.sorted_objects():
        if is_visible(obj, variables):
            _render_object(obj, canvas, resources, variables, dpi_r)
    result = convert_image(canvas, cs_r, bd_r)
    result.info["dpi"] = (dpi_r, dpi_r)
    return result


def render_document(doc, dpi=None, color_space=None, bit_depth=None):
    return [render_page(p, doc.resources, doc.variables, dpi, color_space, bit_depth)
            for p in doc.pages]


# ── Blend modes ──────────────────────────────────────────────────────────────

def _composite_with_blend(canvas, layer, pos, blend):
    if blend in ("normal", "", None):
        canvas.alpha_composite(layer, pos); return
    x, y = pos; w, h = layer.size; cw, ch = canvas.size
    x0, y0 = max(0, x), max(0, y); x1, y1 = min(cw, x + w), min(ch, y + h)
    if x1 <= x0 or y1 <= y0: return
    bg = canvas.crop((x0, y0, x1, y1)).convert("RGBA")
    fg = layer.crop((x0 - x, y0 - y, x1 - x, y1 - y)).convert("RGBA")
    fr, fg_, fb, fa = fg.split(); br, bg_, bb, ba = bg.split()
    try:
        if   blend == "multiply": rc = (ImageChops.multiply(fr, br), ImageChops.multiply(fg_, bg_), ImageChops.multiply(fb, bb))
        elif blend == "screen":   rc = (ImageChops.screen(fr, br),   ImageChops.screen(fg_, bg_),   ImageChops.screen(fb, bb))
        elif blend == "darken":   rc = (ImageChops.darker(fr, br),   ImageChops.darker(fg_, bg_),   ImageChops.darker(fb, bb))
        elif blend == "lighten":  rc = (ImageChops.lighter(fr, br),  ImageChops.lighter(fg_, bg_),  ImageChops.lighter(fb, bb))
        else: canvas.alpha_composite(layer, pos); return
    except Exception:
        canvas.alpha_composite(layer, pos); return
    blended = Image.merge("RGBA", (*rc, fa))
    final = Image.alpha_composite(bg, blended)
    canvas.paste(final, (x0, y0))


def _apply_blend(canvas, layer, pos, blend_mode):
    if blend_mode and blend_mode != "normal":
        _composite_with_blend(canvas, layer, pos, blend_mode)
    else:
        canvas.alpha_composite(layer, pos)


# ── Dispatcher ───────────────────────────────────────────────────────────────

def _render_object(obj, canvas, resources, variables, dpi):
    if   isinstance(obj, TextBox):  _render_textbox(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, ImageBox): _render_imagebox(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, Table):    _render_table(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, Shape):    _render_shape(obj, canvas, dpi)
    elif isinstance(obj, QRCode):   _render_qrcode(obj, canvas, variables, dpi)
    elif isinstance(obj, Group):
        for child in obj.flatten():
            if is_visible(child, variables):
                _render_object(child, canvas, resources, variables, dpi)


# ── Gradient ─────────────────────────────────────────────────────────────────

def _render_gradient(w, h, gradient):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if not gradient or not gradient.stops: return img
    pixels = img.load()
    stops = sorted(gradient.stops, key=lambda s: s[0])

    def color_at(t):
        t = max(0.0, min(1.0, t))
        for i in range(len(stops) - 1):
            if stops[i][0] <= t <= stops[i+1][0]:
                t0, c0 = stops[i]; t1, c1 = stops[i+1]
                if t1 == t0: return tuple(int(v) for v in c1)
                f = (t - t0) / (t1 - t0)
                return tuple(int(c0[k] + (c1[k] - c0[k]) * f) for k in range(4))
        return tuple(int(v) for v in stops[-1][1])

    if gradient.type == "linear":
        ang = math.radians(gradient.angle)
        dx, dy = math.cos(ang), math.sin(ang)
        corners = [(0,0),(w,0),(0,h),(w,h)]
        projs = [px*dx + py*dy for px,py in corners]
        pmin, pmax = min(projs), max(projs)
        prange = pmax - pmin if pmax != pmin else 1.0
        for y in range(h):
            for x in range(w):
                pixels[x, y] = color_at((x*dx + y*dy - pmin) / prange)
    else:
        cx, cy = gradient.center[0]*w, gradient.center[1]*h
        max_r = gradient.radius * max(w, h)
        for y in range(h):
            for x in range(w):
                t = math.hypot(x-cx, y-cy) / max_r if max_r > 0 else 0
                pixels[x, y] = color_at(t)
    return img


# ── TextBox ──────────────────────────────────────────────────────────────────

def _render_textbox(obj, canvas, resources, variables, dpi):
    t = obj.transform
    x_px = mm_to_px(t.x, dpi); y_px = mm_to_px(t.y, dpi)
    w_px = mm_to_px(t.width, dpi); h_px = mm_to_px(t.height, dpi)
    if w_px < 1 or h_px < 1: return

    font_data = None
    if resources:
        for entry in resources.all_entries():
            if (entry.mime_type in ("font/ttf","font/otf","application/x-font-ttf","application/x-font-opentype")
                    and obj.style.font_family.lower() in entry.filename.lower()):
                font_data = entry.data; break

    tmp = Image.new("RGBA", (max(1, int(w_px)), max(1, int(h_px))), (0, 0, 0, 0))
    td  = ImageDraw.Draw(tmp, "RGBA")

    # Background
    if obj.fill.gradient:
        gimg = _render_gradient(int(w_px), int(h_px), obj.fill.gradient)
        tmp.alpha_composite(gimg)
    elif obj.fill.color:
        fd = _rgba(obj.fill.color)
        td.rectangle([0, 0, w_px, h_px], fill=(*fd[:3], int(obj.fill.opacity * fd[3])))

    if obj.border:
        bw = max(1, int(mm_to_px(obj.border.width / 72 * 25.4, dpi)))
        td.rectangle([0, 0, int(w_px) - 1, int(h_px) - 1],
                     outline=_rgba(obj.border.color)[:4], width=bw)

    # Text — runs override plain text if non-empty
    if obj.runs:
        pad_mm = getattr(obj.style, 'padding', 1.0)
        pad = mm_to_px(pad_mm, dpi)
        iw = max(1.0, w_px - 2 * pad); ih = max(1.0, h_px - 2 * pad)
        scale = 1.0
        if obj.style.auto_shrink or obj.style.auto_fill:
            scale = find_fitting_scale(obj.runs, obj.style, int(iw), int(ih),
                                        dpi=dpi, wrap=obj.style.wrap,
                                        shrink_only=obj.style.auto_shrink and not obj.style.auto_fill)
        render_runs_onto(td, obj.runs, obj.style, 0, 0, w_px, h_px, dpi, scale=scale)
    else:
        text = obj.get_resolved_text(variables)
        render_text_onto(td, text, obj.style, 0, 0, w_px, h_px, dpi, font_data)

    if obj.opacity < 1.0:
        r,g,b,a = tmp.split()
        a = a.point(lambda v: int(v * obj.opacity))
        tmp = Image.merge("RGBA", (r, g, b, a))
    if t.flip_h: tmp = tmp.transpose(Image.FLIP_LEFT_RIGHT)
    if t.flip_v: tmp = tmp.transpose(Image.FLIP_TOP_BOTTOM)
    if t.rotation % 360 != 0:
        tmp = tmp.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
        px = int(x_px + w_px/2 - tmp.width/2); py = int(y_px + h_px/2 - tmp.height/2)
    else:
        px, py = int(x_px), int(y_px)
    _apply_blend(canvas, tmp, (max(0, px), max(0, py)), getattr(obj, "blend_mode", "normal"))


# ── ImageBox ─────────────────────────────────────────────────────────────────

def _render_imagebox(obj, canvas, resources, variables, dpi):
    src = None
    if obj.variable and variables:
        val = variables.get(obj.variable)
        if val and isinstance(val, str):
            if os.path.isfile(val):
                try: src = Image.open(val).convert("RGBA")
                except Exception: pass
            elif val.startswith(("http://","https://")):
                try:
                    import urllib.request
                    with urllib.request.urlopen(val, timeout=3) as resp:
                        src = Image.open(io.BytesIO(resp.read())).convert("RGBA")
                except Exception: pass
    if src is None:
        if not obj.resource_id or obj.resource_id not in resources: return
        entry = resources.get(obj.resource_id)
        try: src = Image.open(io.BytesIO(entry.data)).convert("RGBA")
        except Exception: return

    t = obj.transform
    x_px = int(mm_to_px(t.x, dpi)); y_px = int(mm_to_px(t.y, dpi))
    w_px = int(mm_to_px(t.width, dpi)); h_px = int(mm_to_px(t.height, dpi))
    src = _apply_fit(src, w_px, h_px, obj.fit_mode)
    if t.flip_h: src = src.transpose(Image.FLIP_LEFT_RIGHT)
    if t.flip_v: src = src.transpose(Image.FLIP_TOP_BOTTOM)
    if t.rotation % 360 != 0:
        src = src.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
        x_px = int(x_px + w_px/2 - src.width/2); y_px = int(y_px + h_px/2 - src.height/2)
    if obj.opacity < 1.0:
        r,g,b,a = src.split()
        a = a.point(lambda v: int(v * obj.opacity))
        src = Image.merge("RGBA", (r, g, b, a))
    _apply_blend(canvas, src, (max(0, x_px), max(0, y_px)), getattr(obj, "blend_mode", "normal"))


def _apply_fit(src, w, h, mode):
    sw, sh = src.size
    if mode == "stretch": return src.resize((w, h), Image.LANCZOS)
    if mode in ("fill", "cover"):
        ratio = max(w/sw, h/sh); nw, nh = int(sw*ratio), int(sh*ratio)
        src = src.resize((nw, nh), Image.LANCZOS); l, t = (nw-w)//2, (nh-h)//2
        return src.crop((l, t, l+w, t+h))
    if mode == "contain":
        ratio = min(w/sw, h/sh); nw, nh = max(1, int(sw*ratio)), max(1, int(sh*ratio))
        res = src.resize((nw, nh), Image.LANCZOS)
        bg = Image.new("RGBA", (w, h), (0,0,0,0))
        bg.paste(res, ((w-nw)//2, (h-nh)//2), res); return bg
    bg = Image.new("RGBA", (w, h), (0,0,0,0)); bg.paste(src, (0,0), src); return bg


# ── Path / Shape ─────────────────────────────────────────────────────────────

def _de_casteljau(p0, p1, p2, p3, n=20):
    out = [p0]
    for i in range(1, n+1):
        t = i/n; u = 1-t
        x = u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0]
        y = u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
        out.append((x, y))
    return out

def _quad_bezier(p0, p1, p2, n=20):
    out = [p0]
    for i in range(1, n+1):
        t = i/n; u = 1-t
        out.append((u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0],
                    u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1]))
    return out

def _path_to_polygons(path_data, dpi, offset_x=0.0, offset_y=0.0):
    """Convert path commands to polylines.

    v4.0.3: offset_x/y allow rendering paths whose coordinates are local
    (relative to the object's transform.x/y). Default 0.0 keeps backward
    compatibility with absolute-coord paths from older documents.
    """
    polys, cur, cx, cy, sx, sy = [], [], 0.0, 0.0, 0.0, 0.0
    for cmd in path_data:
        if not cmd: continue
        op = cmd[0]
        if op == "M":
            if cur: polys.append(cur)
            cur = []; x, y = cmd[1] + offset_x, cmd[2] + offset_y
            cx, cy = x, y; sx, sy = x, y
            cur.append((mm_to_px(x, dpi), mm_to_px(y, dpi)))
        elif op == "L":
            x, y = cmd[1] + offset_x, cmd[2] + offset_y
            cur.append((mm_to_px(x, dpi), mm_to_px(y, dpi))); cx, cy = x, y
        elif op == "C":
            x1, y1, x2, y2, x, y = cmd[1:]
            x1 += offset_x; y1 += offset_y
            x2 += offset_x; y2 += offset_y
            x  += offset_x; y  += offset_y
            for px, py in _de_casteljau((cx,cy), (x1,y1), (x2,y2), (x,y))[1:]:
                cur.append((mm_to_px(px, dpi), mm_to_px(py, dpi)))
            cx, cy = x, y
        elif op == "Q":
            x1, y1, x, y = cmd[1:]
            x1 += offset_x; y1 += offset_y
            x  += offset_x; y  += offset_y
            for px, py in _quad_bezier((cx,cy), (x1,y1), (x,y))[1:]:
                cur.append((mm_to_px(px, dpi), mm_to_px(py, dpi)))
            cx, cy = x, y
        elif op == "Z":
            cur.append((mm_to_px(sx, dpi), mm_to_px(sy, dpi)))
            cx, cy = sx, sy
    if cur: polys.append(cur)
    return polys


def _render_shape(obj, canvas, dpi):
    t = obj.transform
    x0 = mm_to_px(t.x, dpi); y0 = mm_to_px(t.y, dpi)
    w_px = mm_to_px(t.width, dpi); h_px = mm_to_px(t.height, dpi)
    st = obj.shape_type

    if st == SHAPE_LINE and obj.points and len(obj.points) >= 2:
        sc = _rgba(obj.stroke.color, (0,0,0,255))
        sw = max(1, int(mm_to_px(obj.stroke.width / 72 * 25.4, dpi)))
        p1, p2 = obj.points[0], obj.points[1]
        cd = ImageDraw.Draw(canvas, "RGBA")
        cd.line([(mm_to_px(p1[0],dpi), mm_to_px(p1[1],dpi)),
                 (mm_to_px(p2[0],dpi), mm_to_px(p2[1],dpi))], fill=sc[:4], width=sw)
        return

    if st == SHAPE_PATH and obj.path_data:
        # v4.0.3: detect whether path_data is in local (relative to transform.x/y)
        # or absolute (legacy) coordinates. Local paths fit within transform width/height
        # starting from origin; absolute paths can be anywhere on the page.
        offset_x = offset_y = 0.0
        try:
            xs, ys = [], []
            for cmd in obj.path_data:
                op = cmd[0]
                if op in ("M", "L", "T"):
                    xs.append(cmd[1]); ys.append(cmd[2])
                elif op in ("C",):
                    xs.extend([cmd[1], cmd[3], cmd[5]])
                    ys.extend([cmd[2], cmd[4], cmd[6]])
                elif op == "Q":
                    xs.extend([cmd[1], cmd[3]])
                    ys.extend([cmd[2], cmd[4]])
            if xs:
                min_x, min_y = min(xs), min(ys)
                max_x, max_y = max(xs), max(ys)
                tol = 1.0  # mm
                if (min_x >= -tol and min_y >= -tol
                    and max_x <= t.width + tol and max_y <= t.height + tol):
                    # path coords are local — translate by transform.x/y
                    offset_x = t.x
                    offset_y = t.y
        except Exception:
            pass

        polys = _path_to_polygons(obj.path_data, dpi, offset_x, offset_y)
        cd = ImageDraw.Draw(canvas, "RGBA")
        sc = _rgba(obj.stroke.color, (0,0,0,255))
        sw = max(1, int(mm_to_px(obj.stroke.width / 72 * 25.4, dpi)))
        fc = _rgba(obj.fill.color)
        for poly in polys:
            if len(poly) < 2: continue
            if fc and len(poly) >= 3: cd.polygon(poly, fill=fc[:4])
            cd.line(poly, fill=sc[:4], width=sw)
        return

    tmp = Image.new("RGBA", (max(1, int(w_px)), max(1, int(h_px))), (0,0,0,0))
    td  = ImageDraw.Draw(tmp, "RGBA")
    fc  = _rgba(obj.fill.color)
    sc  = _rgba(obj.stroke.color, (0,0,0,255))
    sw  = max(1, int(mm_to_px(obj.stroke.width / 72 * 25.4, dpi)))

    if obj.fill.gradient:
        gimg = _render_gradient(int(w_px), int(h_px), obj.fill.gradient)
        mask = Image.new("L", (int(w_px), int(h_px)), 0)
        md = ImageDraw.Draw(mask)
        if st == SHAPE_RECT:
            r = int(mm_to_px(obj.corner_radius, dpi))
            if r > 0: md.rounded_rectangle([0,0,w_px,h_px], radius=r, fill=255)
            else:     md.rectangle([0,0,w_px,h_px], fill=255)
        elif st == SHAPE_ELLIPSE:
            md.ellipse([0,0,w_px,h_px], fill=255)
        else:
            md.rectangle([0,0,w_px,h_px], fill=255)
        gimg.putalpha(mask)
        tmp.alpha_composite(gimg)
        if st == SHAPE_RECT:
            r = int(mm_to_px(obj.corner_radius, dpi))
            if r > 0: td.rounded_rectangle([0,0,w_px,h_px], radius=r, outline=sc[:4], width=sw)
            else:     td.rectangle([0,0,w_px,h_px], outline=sc[:4], width=sw)
        elif st == SHAPE_ELLIPSE:
            td.ellipse([0,0,w_px,h_px], outline=sc[:4], width=sw)
    else:
        if st == SHAPE_RECT:
            r = int(mm_to_px(obj.corner_radius, dpi))
            if r > 0: td.rounded_rectangle([0,0,w_px,h_px], radius=r, fill=fc[:4] if fc else None, outline=sc[:4], width=sw)
            else:     td.rectangle([0,0,w_px,h_px], fill=fc[:4] if fc else None, outline=sc[:4], width=sw)
        elif st == SHAPE_ELLIPSE:
            td.ellipse([0,0,w_px,h_px], fill=fc[:4] if fc else None, outline=sc[:4], width=sw)
        elif st == SHAPE_LINE:
            td.line([0,0,w_px,h_px], fill=sc[:4] if sc else (0,0,0,255), width=sw)
        elif st in (SHAPE_POLYGON, SHAPE_ARROW):
            if obj.points:
                pts = [(mm_to_px(px,dpi), mm_to_px(py,dpi)) for px,py in obj.points]
                td.polygon(pts, fill=fc[:4] if fc else None, outline=sc[:4])

    if t.rotation % 360 != 0:
        tmp = tmp.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
    if obj.opacity < 1.0:
        r2,g2,b2,a2 = tmp.split()
        a2 = a2.point(lambda v: int(v * obj.opacity))
        tmp = Image.merge("RGBA", (r2,g2,b2,a2))
    px = int(x0 + w_px/2 - tmp.width/2) if t.rotation % 360 != 0 else int(x0)
    py = int(y0 + h_px/2 - tmp.height/2) if t.rotation % 360 != 0 else int(y0)
    _apply_blend(canvas, tmp, (max(0,px), max(0,py)), getattr(obj, "blend_mode", "normal"))


# ── QR Code ──────────────────────────────────────────────────────────────────

def _render_qrcode(obj, canvas, variables, dpi):
    try: import qrcode as qrlib
    except ImportError:
        from edof.exceptions import warn_missing
        warn_missing("QR code", "qr"); return

    data = obj.get_resolved_data(variables)
    if not data: return

    ec_map = {"L":qrlib.constants.ERROR_CORRECT_L,"M":qrlib.constants.ERROR_CORRECT_M,
              "Q":qrlib.constants.ERROR_CORRECT_Q,"H":qrlib.constants.ERROR_CORRECT_H}
    qr = qrlib.QRCode(error_correction=ec_map.get(obj.error_correction,
                      qrlib.constants.ERROR_CORRECT_M), border=obj.border_modules)
    qr.add_data(data); qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    fg = tuple(int(v) for v in obj.fg_color); bg = tuple(int(v) for v in obj.bg_color)
    fg_r,fg_g,fg_b = fg[:3]; fg_a = fg[3] if len(fg)==4 else 255
    bg_r,bg_g,bg_b = bg[:3]; bg_a = bg[3] if len(bg)==4 else 255
    pixels = qr_img.load()
    for x in range(qr_img.width):
        for y in range(qr_img.height):
            r,g,b,_ = pixels[x,y]
            pixels[x,y] = (fg_r,fg_g,fg_b,fg_a) if r < 128 else (bg_r,bg_g,bg_b,bg_a)

    t = obj.transform
    x_px = int(mm_to_px(t.x, dpi)); y_px = int(mm_to_px(t.y, dpi))
    w_px = int(mm_to_px(t.width, dpi)); h_px = int(mm_to_px(t.height, dpi))
    size = min(w_px, h_px)
    qr_img = qr_img.resize((size, size), Image.NEAREST)
    if t.rotation % 360 != 0:
        qr_img = qr_img.rotate(-t.rotation, expand=True)
        x_px = int(x_px + w_px/2 - qr_img.width/2); y_px = int(y_px + h_px/2 - qr_img.height/2)
    _apply_blend(canvas, qr_img, (max(0,x_px), max(0,y_px)), getattr(obj, "blend_mode", "normal"))


# ── Table ────────────────────────────────────────────────────────────────────

def _render_table(obj, canvas, resources, variables, dpi):
    t = obj.transform
    x0 = mm_to_px(t.x, dpi); y0 = mm_to_px(t.y, dpi)
    n_rows = obj.num_rows; n_cols = obj.num_cols
    if n_rows == 0 or n_cols == 0: return

    # Auto-distribute column widths and row heights
    col_w = list(obj.col_widths) + [0] * max(0, n_cols - len(obj.col_widths))
    explicit_w = sum(w for w in col_w if w > 0)
    auto_cols = sum(1 for w in col_w if w == 0)
    auto_w = (t.width - explicit_w) / auto_cols if auto_cols > 0 else 0
    col_w_px = [mm_to_px(w if w > 0 else auto_w, dpi) for w in col_w]

    row_h = list(obj.row_heights) + [0] * max(0, n_rows - len(obj.row_heights))
    explicit_h = sum(h for h in row_h if h > 0)
    auto_rows = sum(1 for h in row_h if h == 0)
    auto_h = (t.height - explicit_h) / auto_rows if auto_rows > 0 else 0
    row_h_px = [mm_to_px(h if h > 0 else auto_h, dpi) for h in row_h]

    x_offsets = [0]
    for w in col_w_px[:-1]: x_offsets.append(x_offsets[-1] + w)
    y_offsets = [0]
    for h in row_h_px[:-1]: y_offsets.append(y_offsets[-1] + h)

    cd = ImageDraw.Draw(canvas, "RGBA")

    # Backgrounds
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = obj.cells[ri][ci]
            cx = x0 + x_offsets[ci]; cy = y0 + y_offsets[ri]
            cw = sum(col_w_px[ci:ci + cell.colspan])
            ch = sum(row_h_px[ri:ri + cell.rowspan])
            bg = _rgba(cell.bg_color)
            if bg and bg[3] > 0:
                cd.rectangle([cx, cy, cx + cw, cy + ch], fill=bg)

    # Content
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = obj.cells[ri][ci]
            cx = x0 + x_offsets[ci]; cy = y0 + y_offsets[ri]
            cw = sum(col_w_px[ci:ci + cell.colspan])
            ch = sum(row_h_px[ri:ri + cell.rowspan])
            pad = mm_to_px(cell.padding, dpi)
            content_img = Image.new("RGBA", (max(1, int(cw)), max(1, int(ch))), (0,0,0,0))
            content_draw = ImageDraw.Draw(content_img, "RGBA")
            if cell.runs:
                render_runs_onto(content_draw, cell.runs, cell.style,
                                  pad, pad, cw - 2*pad, ch - 2*pad, dpi, scale=1.0)
            else:
                # Resolve {variable} placeholders in cell text
                cell_text = cell.text
                if variables and "{" in cell_text:
                    for name in variables.names():
                        v = variables.get(name)
                        if v is not None:
                            cell_text = cell_text.replace("{" + name + "}", str(v))
                render_text_onto(content_draw, cell_text, cell.style,
                                  pad, pad, cw - 2*pad, ch - 2*pad, dpi)
            canvas.alpha_composite(content_img, (int(cx), int(cy)))

    # Borders
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = obj.cells[ri][ci]
            cx = x0 + x_offsets[ci]; cy = y0 + y_offsets[ri]
            cw = sum(col_w_px[ci:ci + cell.colspan])
            ch = sum(row_h_px[ri:ri + cell.rowspan])
            for side, x1, y1, x2, y2 in [
                (cell.border_top,    cx,      cy,      cx + cw, cy),
                (cell.border_right,  cx + cw, cy,      cx + cw, cy + ch),
                (cell.border_bottom, cx,      cy + ch, cx + cw, cy + ch),
                (cell.border_left,   cx,      cy,      cx,      cy + ch),
            ]:
                if side.enabled:
                    bw = max(1, int(mm_to_px(side.width, dpi)))
                    cd.line([(x1, y1), (x2, y2)], fill=_rgba(side.color), width=bw)

    # Outer border
    if obj.table_border:
        bw = max(1, int(mm_to_px(obj.table_border.width / 72 * 25.4, dpi)))
        bc = _rgba(obj.table_border.color)
        total_w = mm_to_px(t.width, dpi); total_h = mm_to_px(t.height, dpi)
        cd.rectangle([x0, y0, x0 + total_w, y0 + total_h], outline=bc, width=bw)
