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
                                  QRCode, Group, Table, SubDocumentBox, SvgBox,
                                  SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE,
                                  SHAPE_POLYGON, SHAPE_ARROW, SHAPE_PATH)
from edof.utils.safe_eval import is_visible


def _rgba(c, default=(0, 0, 0, 255)) -> tuple:
    if c is None: return None
    t = tuple(int(v) for v in c)
    return (*t, 255) if len(t) == 3 else t[:4]


def render_page(page, resources, variables,
                dpi=None, color_space=None, bit_depth=None,
                show_transparency_checker=True) -> Image.Image:
    """Render a page to an RGBA image.

    v4.1.8: ``show_transparency_checker`` controls whether transparent or
    partially-transparent page backgrounds are filled with a checkerboard
    pattern. Default True (user-facing render — Photoshop-like). Set to
    False when rendering pages that will be composited into a larger
    canvas (embedded sub-document, export with real alpha).
    """
    dpi_r = dpi or page.dpi
    cs_r  = color_space or page.color_space
    bd_r  = bit_depth or page.bit_depth
    w_px  = max(1, int(mm_to_px(page.width,  dpi_r)))
    h_px  = max(1, int(mm_to_px(page.height, dpi_r)))
    bg    = _rgba(page.background, (255, 255, 255, 255))
    # v4.1.3/4.1.8: transparent / partial-transparent background
    if bg[3] == 0:
        if show_transparency_checker:
            canvas = _make_checker_canvas(w_px, h_px, dpi_r)
        else:
            # Pure transparent — used when this page will be composited elsewhere
            canvas = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
    elif bg[3] < 255:
        if show_transparency_checker:
            checker = _make_checker_canvas(w_px, h_px, dpi_r)
            overlay = Image.new("RGBA", (w_px, h_px), bg[:4])
            canvas = Image.alpha_composite(checker, overlay)
        else:
            canvas = Image.new("RGBA", (w_px, h_px), bg[:4])
    else:
        canvas = Image.new("RGBA", (w_px, h_px), bg[:4])
    for obj in page.sorted_objects():
        if is_visible(obj, variables):
            _render_object(obj, canvas, resources, variables, dpi_r)
    # v4.1.8: if bg is transparent and caller wants real alpha, force RGBA
    # mode (otherwise convert_image to "RGB" would strip the alpha)
    if not show_transparency_checker and bg[3] < 255 and cs_r == "RGB":
        cs_r = "RGBA"
    result = convert_image(canvas, cs_r, bd_r)
    result.info["dpi"] = (dpi_r, dpi_r)
    return result


def _make_checker_canvas(w_px, h_px, dpi):
    """v4.1.3: Create an RGBA canvas filled with a transparency checker pattern."""
    # Checker square size: ~3mm
    sq = max(8, int(mm_to_px(3, dpi)))
    canvas = Image.new("RGBA", (w_px, h_px), (220, 220, 220, 255))
    cd = ImageDraw.Draw(canvas)
    for y in range(0, h_px, sq):
        for x in range(0, w_px, sq):
            if ((x // sq) + (y // sq)) % 2 == 0:
                cd.rectangle([x, y, x + sq, y + sq], fill=(180, 180, 180, 255))
    return canvas


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
        # ── Basic chops ──────────────────────────────────────────────────────
        if   blend == "multiply": rc = (ImageChops.multiply(fr, br), ImageChops.multiply(fg_, bg_), ImageChops.multiply(fb, bb))
        elif blend == "screen":   rc = (ImageChops.screen(fr, br),   ImageChops.screen(fg_, bg_),   ImageChops.screen(fb, bb))
        elif blend == "darken":   rc = (ImageChops.darker(fr, br),   ImageChops.darker(fg_, bg_),   ImageChops.darker(fb, bb))
        elif blend == "lighten":  rc = (ImageChops.lighter(fr, br),  ImageChops.lighter(fg_, bg_),  ImageChops.lighter(fb, bb))
        elif blend == "difference":
            rc = (ImageChops.difference(fr, br), ImageChops.difference(fg_, bg_), ImageChops.difference(fb, bb))
        elif blend == "exclusion":
            # B + F - 2*B*F/255
            import numpy as np
            B = np.array(bg, dtype=np.float32)
            F = np.array(fg, dtype=np.float32)
            out = B + F - 2 * B * F / 255.0
            out = np.clip(out, 0, 255).astype(np.uint8)
            blended = Image.fromarray(out, "RGBA")
            blended.putalpha(fa)
            final = Image.alpha_composite(bg, blended)
            canvas.paste(final, (x0, y0))
            return
        # ── Numpy-based composite for advanced modes ────────────────────────
        elif blend in ("overlay", "color_dodge", "color_burn", "hard_light",
                        "soft_light", "hue", "saturation", "color", "luminosity"):
            import numpy as np
            B = np.array(bg, dtype=np.float32)[..., :3] / 255.0
            F = np.array(fg, dtype=np.float32)[..., :3] / 255.0
            FA = np.array(fg, dtype=np.float32)[..., 3:4] / 255.0
            if   blend == "overlay":
                out = np.where(B < 0.5, 2 * B * F, 1 - 2 * (1 - B) * (1 - F))
            elif blend == "color_dodge":
                out = np.where(F >= 1.0, 1.0, np.minimum(1.0, B / np.maximum(1 - F, 1e-6)))
            elif blend == "color_burn":
                out = np.where(F <= 0.0, 0.0, 1 - np.minimum(1.0, (1 - B) / np.maximum(F, 1e-6)))
            elif blend == "hard_light":
                out = np.where(F < 0.5, 2 * F * B, 1 - 2 * (1 - F) * (1 - B))
            elif blend == "soft_light":
                # Pegtop's formula
                out = (1 - 2 * F) * B * B + 2 * F * B
            elif blend in ("hue", "saturation", "color", "luminosity"):
                # Convert to HSL
                from colorsys import rgb_to_hls, hls_to_rgb
                H, W = B.shape[:2]
                # Vectorized HLS conversion
                def rgb_to_hls_arr(arr):
                    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
                    mx = np.max(arr, axis=-1)
                    mn = np.min(arr, axis=-1)
                    L = (mx + mn) / 2
                    diff = mx - mn
                    S = np.where(L < 0.5, diff / np.maximum(mx + mn, 1e-9),
                                  diff / np.maximum(2 - mx - mn, 1e-9))
                    S = np.where(diff < 1e-9, 0, S)
                    Hh = np.zeros_like(L)
                    Hh = np.where(np.logical_and(diff > 1e-9, mx == r),
                                   (g - b) / np.maximum(diff, 1e-9), Hh)
                    Hh = np.where(np.logical_and(diff > 1e-9, mx == g),
                                   2 + (b - r) / np.maximum(diff, 1e-9), Hh)
                    Hh = np.where(np.logical_and(diff > 1e-9, mx == b),
                                   4 + (r - g) / np.maximum(diff, 1e-9), Hh)
                    Hh = (Hh / 6.0) % 1.0
                    return Hh, L, S
                def hls_to_rgb_arr(H_, L_, S_):
                    def hue_to_rgb(p, q, t):
                        t = t % 1.0
                        return np.where(t < 1/6, p + (q - p) * 6 * t,
                                np.where(t < 1/2, q,
                                  np.where(t < 2/3, p + (q - p) * (2/3 - t) * 6, p)))
                    q = np.where(L_ < 0.5, L_ * (1 + S_), L_ + S_ - L_ * S_)
                    p = 2 * L_ - q
                    r = hue_to_rgb(p, q, H_ + 1/3)
                    g = hue_to_rgb(p, q, H_)
                    b = hue_to_rgb(p, q, H_ - 1/3)
                    return np.stack([r, g, b], axis=-1)
                bH, bL, bS = rgb_to_hls_arr(B)
                fH, fL, fS = rgb_to_hls_arr(F)
                if   blend == "hue":        out = hls_to_rgb_arr(fH, bL, bS)
                elif blend == "saturation": out = hls_to_rgb_arr(bH, bL, fS)
                elif blend == "color":      out = hls_to_rgb_arr(fH, bL, fS)
                else:                       out = hls_to_rgb_arr(bH, fL, bS)  # luminosity
            out = np.clip(out * 255, 0, 255).astype(np.uint8)
            blended_rgb = out
            # Composite via alpha
            B_full = np.array(bg, dtype=np.float32)
            FA_flat = FA.squeeze(-1)
            final_arr = B_full.copy()
            final_arr[..., :3] = (1 - FA_flat[..., None]) * B_full[..., :3] + FA_flat[..., None] * blended_rgb
            final_arr[..., 3] = np.maximum(B_full[..., 3], FA_flat * 255)
            final = Image.fromarray(np.clip(final_arr, 0, 255).astype(np.uint8), "RGBA")
            canvas.paste(final, (x0, y0))
            return
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
    # v4.1.0: Render layer effects efficiently using bbox-based buffers.
    effects_below = []
    effects_above = []
    if hasattr(obj, 'effects') and obj.effects:
        for e in obj.effects:
            if not e.enabled: continue
            if e.type in ('drop_shadow', 'outer_glow') or \
               (e.type == 'stroke' and getattr(e, 'stroke_position', 'outside') == 'outside') or \
               (e.type == 'bevel' and getattr(e, 'bevel_kind', 'outer') == 'outer'):
                effects_below.append(e)
            else:
                effects_above.append(e)

    if not effects_below and not effects_above:
        # Fast path: no effects
        _render_object_dispatch(obj, canvas, resources, variables, dpi)
        return

    # ── Render the object onto a full-size temp canvas first ─────────────────
    from PIL import Image
    temp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    _render_object_dispatch(obj, temp, resources, variables, dpi)

    # Compute the actual object bbox from alpha (where the object pixels are)
    bbox = temp.getbbox()
    if bbox is None:
        # Object rendered nothing visible — bail out
        return
    x0, y0, x1, y1 = bbox

    # Compute the largest margin needed by any effect (in pixels)
    margin_px = 20
    for e in effects_below + effects_above:
        em = mm_to_px(e.size, dpi) * 3 + mm_to_px(abs(getattr(e, 'distance', 0)), dpi)
        margin_px = max(margin_px, int(em + 10))

    # Crop a working buffer around the object plus margin
    bx0 = max(0, x0 - margin_px)
    by0 = max(0, y0 - margin_px)
    bx1 = min(canvas.size[0], x1 + margin_px)
    by1 = min(canvas.size[1], y1 + margin_px)
    if bx1 <= bx0 or by1 <= by0:
        canvas.alpha_composite(temp)
        return
    obj_buf = temp.crop((bx0, by0, bx1, by1))
    paste_pos = (bx0, by0)

    # Apply effects-below (drop shadow, outer glow, stroke, etc) — at full
    # alpha (independent of fill_opacity, like Photoshop)
    for e in effects_below:
        _apply_layer_effect_below(canvas, obj_buf, e, dpi, paste_pos)

    # v4.1.1: Composite the actual object pixels at fill_opacity
    fill_op = getattr(obj, 'fill_opacity', 1.0)
    if fill_op < 1.0:
        # Scale the alpha channel of `temp` by fill_opacity
        r, g, b, a = temp.split()
        a = a.point(lambda v, fo=fill_op: int(v * fo))
        temp_with_fillop = Image.merge("RGBA", (r, g, b, a))
        canvas.alpha_composite(temp_with_fillop)
    else:
        canvas.alpha_composite(temp)

    # Apply effects-above (inner shadow, inner glow, color overlay, gradient)
    for e in effects_above:
        _apply_layer_effect_above(canvas, obj_buf, e, dpi, paste_pos)


def _render_object_raw(obj, canvas, resources, variables, dpi, offset=(0,0)):
    """Backward-compatible alias for _render_object_dispatch."""
    _render_object_dispatch(obj, canvas, resources, variables, dpi)


def _render_object_dispatch(obj, canvas, resources, variables, dpi):
    if   isinstance(obj, TextBox):  _render_textbox(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, ImageBox): _render_imagebox(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, SvgBox):   _render_svgbox(obj, canvas, dpi)
    elif isinstance(obj, Table):    _render_table(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, Shape):    _render_shape(obj, canvas, dpi)
    elif isinstance(obj, QRCode):   _render_qrcode(obj, canvas, variables, dpi)
    elif isinstance(obj, SubDocumentBox):
        _render_subdocument(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, Group):
        for child in obj.flatten():
            if is_visible(child, variables):
                _render_object_dispatch(child, canvas, resources, variables, dpi)


def _render_svgbox(obj, canvas, dpi):
    """v4.1.13: Rasterize the SVG XML via QSvgRenderer and alpha-composite
    onto the canvas at the object's transform.x/y position with width/height.
    """
    from PIL import Image
    if not obj.svg_xml: return
    t = obj.transform
    w_px = max(1, int(mm_to_px(t.width, dpi)))
    h_px = max(1, int(mm_to_px(t.height, dpi)))
    try:
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtGui import QImage, QPainter
        from PyQt6.QtCore import QByteArray, QRectF
    except ImportError:
        return   # PyQt6.QtSvg not available — skip silently
    try:
        renderer = QSvgRenderer(QByteArray(obj.svg_xml.encode("utf-8")))
        if not renderer.isValid():
            return
        qimg = QImage(w_px, h_px, QImage.Format.Format_ARGB32)
        qimg.fill(0)
        p = QPainter(qimg)
        renderer.render(p, QRectF(0, 0, w_px, h_px))
        p.end()
        # Convert QImage to PIL
        ptr = qimg.constBits()
        ptr.setsize(qimg.sizeInBytes())
        # Qt's ARGB32 is BGRA in memory on little-endian
        pil_img = Image.frombuffer("RGBA", (w_px, h_px), bytes(ptr),
                                    "raw", "BGRA", 0, 1)
    except Exception:
        return
    # Apply transforms
    if t.flip_h: pil_img = pil_img.transpose(Image.FLIP_LEFT_RIGHT)
    if t.flip_v: pil_img = pil_img.transpose(Image.FLIP_TOP_BOTTOM)
    if t.rotation % 360 != 0:
        pil_img = pil_img.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
        cx_px = int(mm_to_px(t.x + t.width/2, dpi))
        cy_px = int(mm_to_px(t.y + t.height/2, dpi))
        paste_x = cx_px - pil_img.width // 2
        paste_y = cy_px - pil_img.height // 2
        canvas.alpha_composite(pil_img, (max(0, paste_x), max(0, paste_y)))
    else:
        canvas.alpha_composite(pil_img,
            (max(0, int(mm_to_px(t.x, dpi))),
             max(0, int(mm_to_px(t.y, dpi)))))


def _render_subdocument(obj, canvas, resources, variables, dpi):
    """Render an embedded sub-document onto the canvas."""
    from PIL import Image
    sub_doc = None
    # Try to load the sub-document
    try:
        if obj.resource_id and obj.resource_id in resources:
            entry = resources.get(obj.resource_id)
            if entry:
                data = entry.data
                from edof.format.serializer import EdofSerializer
                import tempfile, os as _os
                with tempfile.NamedTemporaryFile(suffix=".edof", delete=False) as f:
                    f.write(data); tmp_path = f.name
                try:
                    sub_doc = EdofSerializer().load(tmp_path)
                finally:
                    try: _os.unlink(tmp_path)
                    except Exception: pass
        elif obj.source_path:
            from edof.format.serializer import EdofSerializer
            sub_doc = EdofSerializer().load(obj.source_path)
    except Exception as e:
        print(f"[render_subdocument] Could not load sub-document: {e}")
        return

    if not sub_doc or not sub_doc.pages:
        return

    page_idx = max(0, min(obj.page_index, len(sub_doc.pages) - 1))
    sub_page = sub_doc.pages[page_idx]
    # v4.1.8: render the embedded page with show_transparency_checker=False
    # so transparent backgrounds remain truly transparent in the parent
    # (otherwise the child's editor-only checker pattern would be visible).
    sub_img = render_page(sub_page, sub_doc.resources, sub_doc.variables,
                            dpi=dpi, show_transparency_checker=False).convert("RGBA")

    # Place it in the bounding box defined by obj.transform
    t = obj.transform
    x_px = int(mm_to_px(t.x, dpi)); y_px = int(mm_to_px(t.y, dpi))
    w_px = int(mm_to_px(t.width, dpi)); h_px = int(mm_to_px(t.height, dpi))
    if w_px <= 0 or h_px <= 0:
        return

    # v4.1.9: build the fitted sub-doc image into a (w_px, h_px) tmp buffer,
    # then rotate the whole thing as a single block (so rotation rotates the
    # entire child rendering — natural behavior for a nested document).
    fit = obj.fit_mode or "contain"
    src_w, src_h = sub_img.size
    bbox_buf = Image.new("RGBA", (max(1, w_px), max(1, h_px)), (0, 0, 0, 0))
    if fit == "stretch":
        out = sub_img.resize((w_px, h_px), Image.Resampling.LANCZOS)
        bbox_buf.alpha_composite(out, (0, 0))
    elif fit == "contain":
        ratio = min(w_px / src_w, h_px / src_h)
        new_w = max(1, int(src_w * ratio))
        new_h = max(1, int(src_h * ratio))
        scaled = sub_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        ox = (w_px - new_w) // 2
        oy = (h_px - new_h) // 2
        bbox_buf.alpha_composite(scaled, (max(0, ox), max(0, oy)))
    elif fit == "cover":
        ratio = max(w_px / src_w, h_px / src_h)
        new_w = max(1, int(src_w * ratio))
        new_h = max(1, int(src_h * ratio))
        scaled = sub_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        ox = (new_w - w_px) // 2
        oy = (new_h - h_px) // 2
        cropped = scaled.crop((ox, oy, ox + w_px, oy + h_px))
        bbox_buf.alpha_composite(cropped, (0, 0))
    else:  # "none" — paste at top-left of bbox, no scaling, possibly clipped
        bbox_buf.alpha_composite(sub_img.crop((0, 0,
                                                  min(src_w, w_px),
                                                  min(src_h, h_px))),
                                    (0, 0))
    # Apply rotation if any
    if t.rotation % 360 != 0:
        rotated = bbox_buf.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
        cx = x_px + w_px // 2
        cy = y_px + h_px // 2
        paste_x = cx - rotated.width // 2
        paste_y = cy - rotated.height // 2
        canvas.alpha_composite(rotated, (max(0, paste_x), max(0, paste_y)))
    else:
        canvas.alpha_composite(bbox_buf, (max(0, x_px), max(0, y_px)))


def _apply_layer_effect_below(canvas, obj_buf, effect, dpi, paste_pos):
    """Apply effects that go BEHIND the object: drop shadow, outer glow,
    outside stroke, outer bevel.

    obj_buf: small RGBA buffer containing just the object silhouette
    paste_pos: (x, y) in pixels — where obj_buf was cropped from a full-size temp
    """
    from PIL import Image, ImageFilter, ImageChops
    import math
    _, _, _, alpha = obj_buf.split()
    px, py = paste_pos
    bw, bh = obj_buf.size

    op_alpha = max(0, min(255, int(255 * effect.opacity)))

    if effect.type == 'drop_shadow':
        rad = math.radians(effect.direction)
        dx = int(mm_to_px(effect.distance, dpi) * math.cos(rad))
        dy = -int(mm_to_px(effect.distance, dpi) * math.sin(rad))
        blur_px = max(0, mm_to_px(effect.size, dpi))
        # Translate the alpha (silhouette only) by (dx, dy)
        shadow_alpha = Image.new("L", (bw, bh), 0)
        shadow_alpha.paste(alpha, (dx, dy))
        if blur_px > 0:
            shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(blur_px))
        # Scale by opacity
        if op_alpha != 255:
            shadow_alpha = shadow_alpha.point(lambda v, oa=op_alpha: int(v * oa / 255))
        # Build colored layer with that alpha
        c = effect.color
        shadow = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        shadow.putalpha(shadow_alpha)
        # Composite onto canvas at paste_pos using effect's blend mode
        _composite_with_blend(canvas, shadow, (px, py), effect.blend_mode)

    elif effect.type == 'outer_glow':
        blur_px = max(1, mm_to_px(effect.size, dpi))
        glow_alpha = alpha.filter(ImageFilter.GaussianBlur(blur_px))
        if op_alpha != 255:
            glow_alpha = glow_alpha.point(lambda v, oa=op_alpha: int(v * oa / 255))
        c = effect.color
        glow = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        glow.putalpha(glow_alpha)
        _composite_with_blend(canvas, glow, (px, py), effect.blend_mode)

    elif effect.type == 'stroke' and effect.stroke_position == 'outside':
        size_px = max(1, int(mm_to_px(effect.size, dpi)))
        # Dilate alpha
        kernel = size_px * 2 + 1
        dilated = alpha.filter(ImageFilter.MaxFilter(kernel))
        # Subtract original to get outer ring
        ring = ImageChops.subtract(dilated, alpha)
        if op_alpha != 255:
            ring = ring.point(lambda v, oa=op_alpha: int(v * oa / 255))
        c = effect.color
        stroke_layer = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        stroke_layer.putalpha(ring)
        _composite_with_blend(canvas, stroke_layer, (px, py), effect.blend_mode)

    elif effect.type == 'bevel' and effect.bevel_kind == 'outer':
        # Outer bevel: shadow opposite of light direction, highlight on light side
        size_px = max(1, int(mm_to_px(effect.size, dpi)))
        rad = math.radians(effect.direction)
        dx_h = int(size_px * 0.7 * math.cos(rad))
        dy_h = -int(size_px * 0.7 * math.sin(rad))
        # Highlight (light side, offset outward in light direction)
        c2 = effect.color2
        hl_a = Image.new("L", (bw, bh), 0); hl_a.paste(alpha, (dx_h, dy_h))
        hl_a = hl_a.filter(ImageFilter.GaussianBlur(size_px))
        # Subtract object silhouette so it's only outside
        hl_a = ImageChops.subtract(hl_a, alpha)
        hl = Image.new("RGBA", (bw, bh), (c2[0], c2[1], c2[2], 0))
        hl.putalpha(hl_a)
        # Shadow (opposite side)
        c1 = effect.color
        sh_a = Image.new("L", (bw, bh), 0); sh_a.paste(alpha, (-dx_h, -dy_h))
        sh_a = sh_a.filter(ImageFilter.GaussianBlur(size_px))
        sh_a = ImageChops.subtract(sh_a, alpha)
        sh = Image.new("RGBA", (bw, bh), (c1[0], c1[1], c1[2], 0))
        sh.putalpha(sh_a)
        _composite_with_blend(canvas, sh, (px, py), 'multiply')
        _composite_with_blend(canvas, hl, (px, py), 'screen')


def _apply_layer_effect_above(canvas, obj_buf, effect, dpi, paste_pos):
    """Apply effects that go ON TOP of the object."""
    from PIL import Image, ImageFilter, ImageChops
    import math
    _, _, _, alpha = obj_buf.split()
    px, py = paste_pos
    bw, bh = obj_buf.size
    op_alpha = max(0, min(255, int(255 * effect.opacity)))

    if effect.type == 'inner_shadow':
        rad = math.radians(effect.direction)
        dx = int(mm_to_px(effect.distance, dpi) * math.cos(rad))
        dy = -int(mm_to_px(effect.distance, dpi) * math.sin(rad))
        blur_px = max(0, mm_to_px(effect.size, dpi))
        # Inner shadow: invert alpha, offset, blur, mask back by original alpha
        inv = ImageChops.invert(alpha)
        shifted = Image.new("L", (bw, bh), 0); shifted.paste(inv, (dx, dy))
        if blur_px > 0:
            shifted = shifted.filter(ImageFilter.GaussianBlur(blur_px))
        masked = ImageChops.multiply(shifted, alpha)
        if op_alpha != 255:
            masked = masked.point(lambda v, oa=op_alpha: int(v * oa / 255))
        c = effect.color
        layer = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        layer.putalpha(masked)
        _composite_with_blend(canvas, layer, (px, py), effect.blend_mode)

    elif effect.type == 'inner_glow':
        blur_px = max(1, mm_to_px(effect.size, dpi))
        inv = ImageChops.invert(alpha)
        blurred = inv.filter(ImageFilter.GaussianBlur(blur_px))
        masked = ImageChops.multiply(blurred, alpha)
        if op_alpha != 255:
            masked = masked.point(lambda v, oa=op_alpha: int(v * oa / 255))
        c = effect.color
        layer = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        layer.putalpha(masked)
        _composite_with_blend(canvas, layer, (px, py), effect.blend_mode)

    elif effect.type == 'stroke' and effect.stroke_position in ('center', 'inside'):
        size_px = max(1, int(mm_to_px(effect.size, dpi)))
        kernel = size_px * 2 + 1
        if effect.stroke_position == 'center':
            # Half outside half inside
            dilated = alpha.filter(ImageFilter.MaxFilter(kernel))
            eroded  = alpha.filter(ImageFilter.MinFilter(kernel))
            ring = ImageChops.subtract(dilated, eroded)
        else:  # inside
            eroded = alpha.filter(ImageFilter.MinFilter(kernel))
            ring = ImageChops.subtract(alpha, eroded)
        if op_alpha != 255:
            ring = ring.point(lambda v, oa=op_alpha: int(v * oa / 255))
        c = effect.color
        layer = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        layer.putalpha(ring)
        _composite_with_blend(canvas, layer, (px, py), effect.blend_mode)

    elif effect.type == 'bevel' and effect.bevel_kind in ('inner', 'emboss'):
        # v4.1.1: Inner bevel — apply highlight/shadow gradient across the
        # whole inner face (not just edge). Computes a "depth map" by blurring
        # the eroded silhouette, then offsetting in light direction.
        size_px = max(2, int(mm_to_px(effect.size, dpi)))
        rad = math.radians(effect.direction)
        dx_h = int(size_px * math.cos(rad))
        dy_h = -int(size_px * math.sin(rad))
        # Create a depth gradient: blurred alpha (gives soft edges)
        depth = alpha.filter(ImageFilter.GaussianBlur(size_px))
        # Highlight is "lighter where shifted toward light"
        # Shadow is "darker where shifted away from light"
        hl_a = Image.new("L", (bw, bh), 0); hl_a.paste(depth, (dx_h, dy_h))
        hl_a = ImageChops.multiply(hl_a, alpha)  # only inside silhouette
        # Subtract the original depth to get only the parts that are
        # "more lit" by the shift (positive lighting)
        hl_a = ImageChops.subtract(hl_a, depth)
        sh_a = Image.new("L", (bw, bh), 0); sh_a.paste(depth, (-dx_h, -dy_h))
        sh_a = ImageChops.multiply(sh_a, alpha)
        sh_a = ImageChops.subtract(sh_a, depth)
        # Apply opacity scaling to both
        op = effect.opacity
        if op != 1.0:
            hl_a = hl_a.point(lambda v, oo=op: int(v * oo))
            sh_a = sh_a.point(lambda v, oo=op: int(v * oo))
        c2 = effect.color2  # highlight
        hl = Image.new("RGBA", (bw, bh), (c2[0], c2[1], c2[2], 0))
        hl.putalpha(hl_a)
        c1 = effect.color   # shadow
        sh = Image.new("RGBA", (bw, bh), (c1[0], c1[1], c1[2], 0))
        sh.putalpha(sh_a)
        # Blend modes per side
        bm_shadow = getattr(effect, 'blend_mode', 'multiply') or 'multiply'
        bm_hl     = getattr(effect, 'blend_mode2', 'screen') or 'screen'
        _composite_with_blend(canvas, sh, (px, py), bm_shadow)
        _composite_with_blend(canvas, hl, (px, py), bm_hl)

    elif effect.type == 'color_overlay':
        c = effect.color
        layer = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        if op_alpha != 255:
            scaled_alpha = alpha.point(lambda v, oa=op_alpha: int(v * oa / 255))
        else:
            scaled_alpha = alpha
        layer.putalpha(scaled_alpha)
        _composite_with_blend(canvas, layer, (px, py), effect.blend_mode)

    elif effect.type == 'gradient_overlay':
        # Build a linear gradient at given angle, then mask by alpha
        grad_img = _build_linear_gradient(bw, bh, effect.gradient_start,
                                            effect.gradient_end, effect.gradient_angle)
        # Mask by silhouette
        if op_alpha != 255:
            scaled_alpha = alpha.point(lambda v, oa=op_alpha: int(v * oa / 255))
        else:
            scaled_alpha = alpha
        grad_img.putalpha(scaled_alpha)
        _composite_with_blend(canvas, grad_img, (px, py), effect.blend_mode)

    elif effect.type == 'texture_overlay':
        # Load texture
        tex = None
        try:
            if effect.texture_path:
                tex = Image.open(effect.texture_path).convert("RGBA")
            elif effect.texture_data:
                from io import BytesIO
                tex = Image.open(BytesIO(effect.texture_data)).convert("RGBA")
        except Exception:
            tex = None
        if tex is None:
            return
        # v4.1.1: scale is relative to OBJECT size, not zoom (so the texture
        # looks the same regardless of canvas zoom). fit_mode controls layout.
        scale = (effect.texture_scale or 100) / 100.0
        fit_mode = getattr(effect, 'texture_fit', 'tile') or 'tile'
        anchor   = getattr(effect, 'texture_anchor', 'top-left') or 'top-left'
        if fit_mode == 'stretch':
            tiled = tex.resize((bw, bh), Image.LANCZOS)
        elif fit_mode == 'fit':
            # Aspect-preserve fit inside object
            ratio = min(bw / tex.width, bh / tex.height) * scale
            new_w = max(1, int(tex.width * ratio))
            new_h = max(1, int(tex.height * ratio))
            scaled = tex.resize((new_w, new_h), Image.LANCZOS)
            tiled = Image.new("RGBA", (bw, bh), (0,0,0,0))
            if anchor == 'center':
                tiled.paste(scaled, ((bw - new_w) // 2, (bh - new_h) // 2))
            else:
                tiled.paste(scaled, (0, 0))
        elif fit_mode == 'fill':
            # Aspect-preserve cover (overflow)
            ratio = max(bw / tex.width, bh / tex.height) * scale
            new_w = max(1, int(tex.width * ratio))
            new_h = max(1, int(tex.height * ratio))
            scaled = tex.resize((new_w, new_h), Image.LANCZOS)
            tiled = Image.new("RGBA", (bw, bh), (0,0,0,0))
            if anchor == 'center':
                tiled.paste(scaled, (-(new_w - bw) // 2, -(new_h - bh) // 2))
            else:
                tiled.paste(scaled, (0, 0))
        else:  # tile
            new_w = max(1, int(tex.width * scale))
            new_h = max(1, int(tex.height * scale))
            scaled = tex.resize((new_w, new_h), Image.LANCZOS)
            tiled = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            offset_x = (bw - new_w) // 2 if anchor == 'center' else 0
            offset_y = (bh - new_h) // 2 if anchor == 'center' else 0
            # Wrap: start before 0 if needed
            start_x = offset_x % new_w - new_w
            start_y = offset_y % new_h - new_h
            for ty in range(start_y, bh, new_h):
                for tx in range(start_x, bw, new_w):
                    tiled.paste(scaled, (tx, ty))
        # Combine alpha
        if op_alpha != 255:
            scaled_alpha = alpha.point(lambda v, oa=op_alpha: int(v * oa / 255))
        else:
            scaled_alpha = alpha
        _, _, _, tex_alpha = tiled.split()
        combined_alpha = ImageChops.multiply(tex_alpha, scaled_alpha)
        tiled.putalpha(combined_alpha)
        _composite_with_blend(canvas, tiled, (px, py), effect.blend_mode)


def _build_linear_gradient(w, h, c_start, c_end, angle_deg):
    """Generate an RGBA image with a linear gradient from c_start to c_end at angle_deg.

    Uses NumPy if available for speed, otherwise PIL with a fast path.
    """
    from PIL import Image
    import math
    try:
        import numpy as np
        ang = math.radians(angle_deg)
        cos_a, sin_a = math.cos(ang), -math.sin(ang)
        # t at center is 0.5, increasing in light direction
        x = np.arange(w).reshape(1, w) - w / 2
        y = np.arange(h).reshape(h, 1) - h / 2
        max_d = max(w, h) / 2
        t = (x * cos_a + y * sin_a) / (max_d * 2) + 0.5
        t = np.clip(t, 0, 1)
        r = (c_start[0] * (1 - t) + c_end[0] * t).astype(np.uint8)
        g = (c_start[1] * (1 - t) + c_end[1] * t).astype(np.uint8)
        b = (c_start[2] * (1 - t) + c_end[2] * t).astype(np.uint8)
        a = np.full_like(r, 255)
        arr = np.stack([r, g, b, a], axis=-1)
        return Image.fromarray(arr, mode='RGBA')
    except ImportError:
        # PIL fallback - slow but works
        ang = math.radians(angle_deg)
        cos_a, sin_a = math.cos(ang), -math.sin(ang)
        max_d = max(w, h) / 2
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        # Build per-row using horizontal fill where possible
        cs = c_start; ce = c_end
        for y in range(h):
            for x in range(w):
                t = ((x - w/2) * cos_a + (y - h/2) * sin_a) / (max_d * 2) + 0.5
                t = max(0, min(1, t))
                r = int(cs[0] * (1-t) + ce[0] * t)
                g = int(cs[1] * (1-t) + ce[1] * t)
                b = int(cs[2] * (1-t) + ce[2] * t)
                img.putpixel((x, y), (r, g, b, 255))
        return img


def _composite_with_blend(canvas, layer, pos, blend_mode):
    """Composite `layer` onto `canvas` at `pos` using a blend mode.

    For 'normal', uses alpha_composite. For other modes, blends RGB while
    respecting layer alpha.
    """
    from PIL import Image
    px, py = pos
    if blend_mode == 'normal' or blend_mode is None:
        canvas.alpha_composite(layer, (max(0, px), max(0, py)))
        return
    # Crop region of canvas
    bw, bh = layer.size
    cw, ch = canvas.size
    # Source region of layer to use
    src_x0 = max(0, -px); src_y0 = max(0, -py)
    src_x1 = min(bw, cw - px); src_y1 = min(bh, ch - py)
    if src_x1 <= src_x0 or src_y1 <= src_y0: return
    dst_x0 = max(0, px); dst_y0 = max(0, py)
    layer_crop = layer.crop((src_x0, src_y0, src_x1, src_y1))
    canvas_crop = canvas.crop((dst_x0, dst_y0, dst_x0 + (src_x1 - src_x0),
                                dst_y0 + (src_y1 - src_y0)))
    blended = _apply_blend_mode_internal(canvas_crop, layer_crop, blend_mode)
    canvas.paste(blended, (dst_x0, dst_y0))


def _apply_blend_mode_internal(base, top, mode):
    """Blend two RGBA images using the given mode. Returns an RGBA image."""
    from PIL import Image, ImageChops
    try:
        import numpy as np
        b = np.asarray(base.convert("RGBA"), dtype=np.float32)
        t = np.asarray(top.convert("RGBA"), dtype=np.float32)
        ba = b[..., 3:4] / 255.0
        ta = t[..., 3:4] / 255.0
        br = b[..., :3] / 255.0
        tr = t[..., :3] / 255.0
        if mode == 'multiply':
            blend = br * tr
        elif mode == 'screen':
            blend = 1 - (1 - br) * (1 - tr)
        elif mode == 'overlay':
            blend = np.where(br < 0.5, 2 * br * tr, 1 - 2 * (1 - br) * (1 - tr))
        elif mode == 'darken':
            blend = np.minimum(br, tr)
        elif mode == 'lighten':
            blend = np.maximum(br, tr)
        elif mode == 'color_dodge':
            blend = np.where(tr >= 1, 1, np.minimum(1, br / np.maximum(1e-6, 1 - tr)))
        elif mode == 'color_burn':
            blend = np.where(tr <= 0, 0, 1 - np.minimum(1, (1 - br) / np.maximum(1e-6, tr)))
        elif mode == 'hard_light':
            blend = np.where(tr < 0.5, 2 * br * tr, 1 - 2 * (1 - br) * (1 - tr))
        elif mode == 'soft_light':
            blend = np.where(tr < 0.5,
                              br - (1 - 2 * tr) * br * (1 - br),
                              br + (2 * tr - 1) * (np.where(br < 0.25, ((16 * br - 12) * br + 4) * br, np.sqrt(br)) - br))
        elif mode == 'difference':
            blend = np.abs(br - tr)
        elif mode == 'exclusion':
            blend = br + tr - 2 * br * tr
        else:  # normal fallback
            blend = tr
        blend = np.clip(blend, 0, 1)
        # Out alpha = ba + ta*(1-ba)
        out_a = ba + ta * (1 - ba)
        # Out color = (blend * ta * (1 - ba) + br * ba * (1 - ta) + blend * ba * ta) / out_a
        # Simplified standard Porter-Duff over with blend:
        out_rgb = (blend * ta + br * (1 - ta))
        out = np.concatenate([out_rgb, out_a], axis=-1)
        out = (np.clip(out, 0, 1) * 255).astype(np.uint8)
        return Image.fromarray(out, mode='RGBA')
    except Exception:
        # Fallback to alpha composite if numpy not available
        result = base.copy()
        result.alpha_composite(top)
        return result


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
        bw = max(1, int(mm_to_px(obj.border.width, dpi)))
        td.rectangle([0, 0, int(w_px) - 1, int(h_px) - 1],
                     outline=_rgba(obj.border.color)[:4], width=bw)

    # Text — synthesize a single run from plain text if obj.runs is empty,
    # so the unified runs+deformation path handles everything.
    text_runs = obj.runs
    if not text_runs:
        text = obj.get_resolved_text(variables)
        if text:
            from edof.format.styles import TextRun as _TR
            text_runs = [_TR(text=text)]
    if text_runs:
        # v4.1.16.7: non-uniform glyph scaling support. Render the text
        # at "natural" size (current_size / glyph_scale) into a buffer,
        # then resize the buffer non-uniformly back to actual box size.
        # This produces real letter-stretching, not just font-size change.
        gsx = float(getattr(obj.style, 'glyph_scale_x', 1.0) or 1.0)
        gsy = float(getattr(obj.style, 'glyph_scale_y', 1.0) or 1.0)
        if abs(gsx - 1.0) > 0.005 or abs(gsy - 1.0) > 0.005:
            nat_w = max(1, int(round(w_px / gsx)))
            nat_h = max(1, int(round(h_px / gsy)))
            text_buf = Image.new("RGBA", (nat_w, nat_h), (0, 0, 0, 0))
            text_td  = ImageDraw.Draw(text_buf)
            pad_mm = getattr(obj.style, 'padding', 1.0)
            pad = mm_to_px(pad_mm, dpi)
            iw = max(1.0, nat_w - 2 * pad); ih = max(1.0, nat_h - 2 * pad)
            scale = 1.0
            if obj.style.auto_shrink or obj.style.auto_fill:
                scale = find_fitting_scale(text_runs, obj.style, int(iw), int(ih),
                                            dpi=dpi, wrap=obj.style.wrap,
                                            shrink_only=obj.style.auto_shrink and not obj.style.auto_fill)
            from edof.engine.text_layout import layout_runs as _lay, render_layout_onto as _draw
            pa = getattr(obj, 'paragraph_alignments', None) or {}
            lay = _lay(text_runs, obj.style, 0.0, 0.0, float(nat_w), float(nat_h),
                       dpi, scale=scale, paragraph_alignments=pa,
                       add_trailing_virtual=not getattr(obj, '_continues', False))
            _draw(text_td, lay, text_runs, obj.style, dpi, scale=scale)
            text_buf = text_buf.resize((int(w_px), int(h_px)), Image.LANCZOS)
            tmp.paste(text_buf, (0, 0), text_buf)
            # Emit overflow warning if applicable
            if (lay.overflow_v and not obj.style.auto_shrink
                and not obj.style.auto_fill):
                import warnings as _w
                _w.warn(
                    f"Text overflows textbox at {obj.style.font_size:.2f}mm. "
                    f"Set style.auto_shrink=True to fit, or increase box height.",
                    RuntimeWarning, stacklevel=3)
        else:
            pad_mm = getattr(obj.style, 'padding', 1.0)
            pad = mm_to_px(pad_mm, dpi)
            iw = max(1.0, w_px - 2 * pad); ih = max(1.0, h_px - 2 * pad)
            scale = 1.0
            if obj.style.auto_shrink or obj.style.auto_fill:
                scale = find_fitting_scale(text_runs, obj.style, int(iw), int(ih),
                                            dpi=dpi, wrap=obj.style.wrap,
                                            shrink_only=obj.style.auto_shrink and not obj.style.auto_fill)
            from edof.engine.text_layout import layout_runs as _lay, render_layout_onto as _draw
            pa = getattr(obj, 'paragraph_alignments', None) or {}
            lay = _lay(text_runs, obj.style, 0.0, 0.0, float(w_px), float(h_px),
                       dpi, scale=scale, paragraph_alignments=pa,
                       add_trailing_virtual=not getattr(obj, '_continues', False))
            _draw(td, lay, text_runs, obj.style, dpi, scale=scale)
            if (lay.overflow_v and not obj.style.auto_shrink
                and not obj.style.auto_fill):
                import warnings as _w
                _w.warn(
                    f"Text overflows textbox at {obj.style.font_size:.2f}mm. "
                    f"Set style.auto_shrink=True to fit, or increase box height.",
                    RuntimeWarning, stacklevel=3)

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
        sw = max(1, int(mm_to_px(obj.stroke.width, dpi)))
        p1, p2 = obj.points[0], obj.points[1]
        # v4.1.9/4.1.10: route through tmp buffer when rotation or flip is set
        if t.rotation % 360 != 0 or t.flip_h or t.flip_v:
            # Compute the bbox containing both endpoints in mm
            xmin = min(p1[0], p2[0]); ymin = min(p1[1], p2[1])
            xmax = max(p1[0], p2[0]); ymax = max(p1[1], p2[1])
            bw_mm = max(0.1, xmax - xmin)
            bh_mm = max(0.1, ymax - ymin)
            buf_w = max(1, int(mm_to_px(bw_mm, dpi)) + sw * 2)
            buf_h = max(1, int(mm_to_px(bh_mm, dpi)) + sw * 2)
            buf = Image.new("RGBA", (buf_w, buf_h), (0,0,0,0))
            bd = ImageDraw.Draw(buf, "RGBA")
            lp1 = (int(mm_to_px(p1[0]-xmin, dpi)) + sw,
                   int(mm_to_px(p1[1]-ymin, dpi)) + sw)
            lp2 = (int(mm_to_px(p2[0]-xmin, dpi)) + sw,
                   int(mm_to_px(p2[1]-ymin, dpi)) + sw)
            bd.line([lp1, lp2], fill=sc[:4], width=sw)
            # v4.1.10: flip before rotation
            if t.flip_h: buf = buf.transpose(Image.FLIP_LEFT_RIGHT)
            if t.flip_v: buf = buf.transpose(Image.FLIP_TOP_BOTTOM)
            if t.rotation % 360 != 0:
                rotated = buf.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
            else:
                rotated = buf
            cx_px = int(mm_to_px((xmin + xmax) / 2, dpi))
            cy_px = int(mm_to_px((ymin + ymax) / 2, dpi))
            paste_x = cx_px - rotated.width // 2
            paste_y = cy_px - rotated.height // 2
            canvas.alpha_composite(rotated, (max(0, paste_x), max(0, paste_y)))
            return
        # No rotation or flip: draw directly (faster)
        cd = ImageDraw.Draw(canvas, "RGBA")
        cd.line([(mm_to_px(p1[0],dpi), mm_to_px(p1[1],dpi)),
                 (mm_to_px(p2[0],dpi), mm_to_px(p2[1],dpi))], fill=sc[:4], width=sw)
        return

    if st == SHAPE_PATH and obj.path_data:
        sc = _rgba(obj.stroke.color, (0,0,0,255))
        sw = max(1, int(mm_to_px(obj.stroke.width, dpi)))
        fc = _rgba(obj.fill.color)
        # v4.1.11: fill ONLY for closed paths (ends with ['Z']). Open paths
        # render only stroke — filling an open shape doesn't have a unique
        # geometric interpretation, so we skip it.
        is_closed = (obj.path_data[-1] and obj.path_data[-1][0] == 'Z')
        if not is_closed:
            fc = None
        # v4.1.10.1: ALWAYS render path into a tmp buffer + alpha_composite
        # onto canvas. Drawing semi-transparent fills directly with
        # ImageDraw.polygon(fill=RGBA) does NOT alpha-blend — it overwrites
        # pixels (effectively losing the alpha after RGB conversion).
        # v4.1.10.4: ceil + 1px right/bottom padding so anti-aliased stroke
        # and floor-rounded path coords don't clip the last column/row.
        import math as _math
        buf_w = max(1, int(_math.ceil(w_px)) + 1)
        buf_h = max(1, int(_math.ceil(h_px)) + 1)
        buf = Image.new("RGBA", (buf_w, buf_h), (0,0,0,0))
        polys = _path_to_polygons(obj.path_data, dpi, 0.0, 0.0)
        bd = ImageDraw.Draw(buf, "RGBA")
        # v4.1.15: gradient support for closed paths
        if is_closed and obj.fill.gradient is not None:
            # Build a polygon-shaped mask, then composite gradient through it
            mask = Image.new("L", (buf_w, buf_h), 0)
            md = ImageDraw.Draw(mask)
            for poly in polys:
                if len(poly) >= 3:
                    md.polygon(poly, fill=255)
            gimg = _render_gradient(buf_w, buf_h, obj.fill.gradient)
            # Apply object's fill_opacity uniformly to the mask
            fop = float(getattr(obj.fill, 'opacity', 1.0))
            if fop < 1.0:
                mask = mask.point(lambda v, _f=fop: int(v * _f))
            gimg.putalpha(ImageChops.multiply(gimg.split()[3], mask))
            buf.alpha_composite(gimg)
            # Then draw stroke ON TOP of the gradient fill
            for poly in polys:
                if len(poly) < 2: continue
                bd.line(poly, fill=sc[:4], width=sw)
        else:
            for poly in polys:
                if len(poly) < 2: continue
                if fc and len(poly) >= 3: bd.polygon(poly, fill=fc[:4])
                bd.line(poly, fill=sc[:4], width=sw)
        # Apply flip/rotation if any
        if t.flip_h: buf = buf.transpose(Image.FLIP_LEFT_RIGHT)
        if t.flip_v: buf = buf.transpose(Image.FLIP_TOP_BOTTOM)
        if t.rotation % 360 != 0:
            buf = buf.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
            cx_px = int(mm_to_px(t.x + t.width/2, dpi))
            cy_px = int(mm_to_px(t.y + t.height/2, dpi))
            paste_x = cx_px - buf.width // 2
            paste_y = cy_px - buf.height // 2
            canvas.alpha_composite(buf, (max(0, paste_x), max(0, paste_y)))
        else:
            canvas.alpha_composite(buf,
                (max(0, int(mm_to_px(t.x, dpi))),
                 max(0, int(mm_to_px(t.y, dpi)))))
        return

    tmp = Image.new("RGBA", (max(1, int(w_px)), max(1, int(h_px))), (0,0,0,0))
    td  = ImageDraw.Draw(tmp, "RGBA")
    fc  = _rgba(obj.fill.color)
    sc  = _rgba(obj.stroke.color, (0,0,0,255))
    sw  = max(1, int(mm_to_px(obj.stroke.width, dpi)))

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

    # v4.1.10: apply flip before rotation (consistent with text/image handling)
    if t.flip_h: tmp = tmp.transpose(Image.FLIP_LEFT_RIGHT)
    if t.flip_v: tmp = tmp.transpose(Image.FLIP_TOP_BOTTOM)
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
    n_rows = obj.num_rows; n_cols = obj.num_cols
    if n_rows == 0 or n_cols == 0: return

    # Auto-distribute column widths and row heights
    col_w = list(obj.col_widths) + [0] * max(0, n_cols - len(obj.col_widths))
    explicit_w = sum(w for w in col_w if w > 0)
    auto_cols = sum(1 for w in col_w if w == 0)
    auto_w = (t.width - explicit_w) / auto_cols if auto_cols > 0 else 0
    # v4.1.1: if all widths are explicit but their sum != transform.width,
    # scale them proportionally so that resizing the table actually rescales
    # all columns instead of overflowing the bounding box.
    if auto_cols == 0 and explicit_w > 0 and abs(explicit_w - t.width) > 0.01:
        scale = t.width / explicit_w
        col_w = [w * scale for w in col_w]
    col_w_px = [mm_to_px(w if w > 0 else auto_w, dpi) for w in col_w]

    row_h = list(obj.row_heights) + [0] * max(0, n_rows - len(obj.row_heights))
    explicit_h = sum(h for h in row_h if h > 0)
    auto_rows = sum(1 for h in row_h if h == 0)
    auto_h = (t.height - explicit_h) / auto_rows if auto_rows > 0 else 0
    if auto_rows == 0 and explicit_h > 0 and abs(explicit_h - t.height) > 0.01:
        scale = t.height / explicit_h
        row_h = [h * scale for h in row_h]
    row_h_px = [mm_to_px(h if h > 0 else auto_h, dpi) for h in row_h]

    # v4.1.1: support rotation by rendering to a tmp image and rotating
    needs_rotation = abs(t.rotation) > 0.01
    if needs_rotation:
        tw_px = mm_to_px(t.width, dpi); th_px = mm_to_px(t.height, dpi)
        from PIL import Image as _PI
        tmp_canvas = _PI.new("RGBA", (max(1, int(tw_px)), max(1, int(th_px))), (0,0,0,0))
        x0 = 0; y0 = 0
        target_canvas = tmp_canvas
    else:
        x0 = mm_to_px(t.x, dpi); y0 = mm_to_px(t.y, dpi)
        target_canvas = canvas

    x_offsets = [0]
    for w in col_w_px[:-1]: x_offsets.append(x_offsets[-1] + w)
    y_offsets = [0]
    for h in row_h_px[:-1]: y_offsets.append(y_offsets[-1] + h)

    cd = ImageDraw.Draw(target_canvas, "RGBA")

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
            target_canvas.alpha_composite(content_img, (int(cx), int(cy)))

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
        bw = max(1, int(mm_to_px(obj.table_border.width, dpi)))
        bc = _rgba(obj.table_border.color)
        total_w = mm_to_px(t.width, dpi); total_h = mm_to_px(t.height, dpi)
        cd.rectangle([x0, y0, x0 + total_w, y0 + total_h], outline=bc, width=bw)

    # v4.1.1: if we rendered into a tmp_canvas due to rotation, rotate now
    if needs_rotation:
        from PIL import Image as _PI
        rotated = tmp_canvas.rotate(-t.rotation, resample=_PI.BICUBIC, expand=True)
        # Paste with center alignment
        tw_px = mm_to_px(t.width, dpi); th_px = mm_to_px(t.height, dpi)
        cx = mm_to_px(t.x + t.width/2, dpi); cy = mm_to_px(t.y + t.height/2, dpi)
        px = int(cx - rotated.width / 2); py = int(cy - rotated.height / 2)
        canvas.alpha_composite(rotated, (max(0, px), max(0, py)))
