# edof/engine/renderer.py
"""v4.0: rich text, tables, vector paths, gradients, blend modes, conditional visibility."""
from __future__ import annotations
import io, os, math
import logging
import hashlib as _hashlib
import collections as _collections
from PIL import Image, ImageDraw, ImageChops
from edof.engine.color import convert_image
from edof.engine.transform import mm_to_px
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


def _make_page_canvas(page, w_px, h_px, dpi_r, show_transparency_checker):
    """Build the base page canvas (background only), shared by render_page and
    render_page_active so they are pixel-identical."""
    bg = _rgba(page.background, (255, 255, 255, 255))
    if bg[3] == 0:
        if show_transparency_checker:
            return _make_checker_canvas(w_px, h_px, dpi_r)
        return Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
    elif bg[3] < 255:
        if show_transparency_checker:
            checker = _make_checker_canvas(w_px, h_px, dpi_r)
            overlay = Image.new("RGBA", (w_px, h_px), bg[:4])
            return Image.alpha_composite(checker, overlay)
        return Image.new("RGBA", (w_px, h_px), bg[:4])
    return Image.new("RGBA", (w_px, h_px), bg[:4])


def render_page(page, resources, variables,
                dpi=None, color_space=None, bit_depth=None,
                show_transparency_checker=True, use_cache=False) -> Image.Image:
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
    canvas = _make_page_canvas(page, w_px, h_px, dpi_r, show_transparency_checker)
    res_fp = _res_fp(resources) if use_cache else None
    for obj in page.sorted_objects():
        if is_visible(obj, variables):
            if use_cache:
                _render_object_cached(obj, canvas, resources, variables, dpi_r, res_fp)
            else:
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


def render_page_active(page, resources, variables, active_id,
                       dpi=None, color_space=None, bit_depth=None,
                       show_transparency_checker=True, active_scale=1.0):
    """Fast re-render while a SINGLE object (active_id) is being edited.

    Caches the static background split into 'below' (page bg + every object
    under the active one) and 'above' (objects over it), keyed on a signature of
    every non-active object. Each call only re-renders the active object and
    composites it between the two cached layers, so dragging / tweaking one
    object on a dense page no longer re-renders the whole page every frame.

    Returns an RGBA-or-converted Image, or None when the fast path can't be used
    safely (active not on page, or an 'above' object uses a non-normal blend —
    flattening that group on transparency would not match a full render). The
    caller should fall back to render_page() on None.
    """
    dpi_r = dpi or page.dpi
    cs_r  = color_space or page.color_space
    bd_r  = bit_depth or page.bit_depth
    w_px  = max(1, int(mm_to_px(page.width,  dpi_r)))
    h_px  = max(1, int(mm_to_px(page.height, dpi_r)))
    size  = (w_px, h_px)

    objs = list(page.sorted_objects())
    act_idx = None
    for i, o in enumerate(objs):
        if getattr(o, 'id', None) == active_id:
            act_idx = i; break
    if act_idx is None:
        return None
    active = objs[act_idx]
    below  = objs[:act_idx]
    above  = objs[act_idx + 1:]

    # 'above' is flattened onto transparency then composited; only equivalent to
    # a full render when every above object uses normal blend.
    for o in above:
        if (getattr(o, 'blend_mode', 'normal') or 'normal') != 'normal':
            return None

    res_fp = _res_fp(resources)
    bg = _rgba(page.background, (255, 255, 255, 255))
    parts = [repr(bg), str(dpi_r), str(size), repr(_vars_fp(variables)),
             repr(res_fp), str(bool(show_transparency_checker)), str(act_idx)]
    for o in (below + above):
        parts.append(_obj_sig(o, variables, dpi_r, size, res_fp)
                     or repr(getattr(o, 'id', '?')))
    static_key = _hashlib.sha1('|'.join(parts).encode('utf-8', 'ignore')).hexdigest()

    ent = _ACTIVE_BG_CACHE.get(static_key)
    if ent is None:
        below_img = _make_page_canvas(page, w_px, h_px, dpi_r,
                                      show_transparency_checker)
        for o in below:
            if is_visible(o, variables):
                _render_object(o, below_img, resources, variables, dpi_r)
        above_img = Image.new("RGBA", size, (0, 0, 0, 0))
        for o in above:
            if is_visible(o, variables):
                _render_object(o, above_img, resources, variables, dpi_r)
        _ACTIVE_BG_CACHE.clear()   # keep only the current active context
        _ACTIVE_BG_CACHE[static_key] = (below_img, above_img)
        ent = _ACTIVE_BG_CACHE[static_key]
    below_img, above_img = ent

    result = below_img.copy()
    if is_visible(active, variables):
        _composite_active_cached(active, result, resources, variables,
                                 dpi_r, size, res_fp, active_scale)
    result.alpha_composite(above_img)

    if not show_transparency_checker and bg[3] < 255 and cs_r == "RGB":
        cs_r = "RGBA"
    out = convert_image(result, cs_r, bd_r)
    out.info["dpi"] = (dpi_r, dpi_r)
    return out


def render_document(doc, dpi=None, color_space=None, bit_depth=None):
    return [render_page(p, doc.resources, doc.variables, dpi, color_space, bit_depth)
            for p in doc.pages]


# ── Blend modes ──────────────────────────────────────────────────────────────

def _apply_blend(canvas, layer, pos, blend_mode):
    if blend_mode and blend_mode != "normal":
        _composite_with_blend(canvas, layer, pos, blend_mode)
    else:
        canvas.alpha_composite(layer, pos)


# ── Dispatcher ───────────────────────────────────────────────────────────────

_OBJ_CACHE = _collections.OrderedDict()
_OBJ_CACHE_CAP = 512

# v4.2.10.9: dirty-region cache for editing a single object. Holds the static
# background split around the active object: (below_img, above_img). Only one
# context is kept at a time (the current active object); a changed static set
# yields a new key and a rebuild.
_ACTIVE_BG_CACHE = _collections.OrderedDict()

# v4.2.10.10: translation cache for the active object itself. Keyed on the
# object's signature WITHOUT translation, so a pure move (only transform.x/y
# changes) is a cache hit: the rendered crop is re-composited at the new pixel
# offset instead of re-rendering the object (and its expensive effects). Keeps
# only the current active object.
_ACTIVE_OBJ_CACHE = _collections.OrderedDict()


def _alpha_composite_clipped(canvas, crop, px, py):
    """alpha_composite that tolerates a paste position partly off the top/left
    (alpha_composite itself requires a non-negative dest)."""
    cropx = -px if px < 0 else 0
    cropy = -py if py < 0 else 0
    if cropx >= crop.width or cropy >= crop.height:
        return
    if cropx or cropy:
        crop = crop.crop((cropx, cropy, crop.width, crop.height))
    if crop.width <= 0 or crop.height <= 0:
        return
    canvas.alpha_composite(crop, (max(0, px), max(0, py)))


def _obj_sig_no_translation(obj, variables, dpi, size, res_fp):
    """Signature of an object EXCLUDING its translation, so a pure move keeps the
    same key. Rotation / flip / size / content all remain in the key."""
    try:
        d = dict(obj.to_dict())
        tr = d.get('transform')
        if isinstance(tr, dict):
            tr = dict(tr); tr.pop('x', None); tr.pop('y', None)
            d['transform'] = tr
        raw = (repr(d) + repr(_vars_fp(variables))
               + str(dpi) + str(size) + repr(res_fp))
        return _hashlib.sha1(raw.encode('utf-8', 'ignore')).hexdigest()
    except Exception:
        return None


def _composite_active_cached(obj, canvas, resources, variables, dpi, size, res_fp,
                             active_scale=1.0):
    """Composite the active object, reusing its raster across pure moves. Only
    used for normal-blend objects (a non-normal blend must blend against the
    live backdrop); those render directly.

    When active_scale < 1 the active object is rendered at a reduced internal
    resolution and upscaled with NEAREST (so the dragged object pixelates for
    speed) while its POSITION stays full-dpi exact, so nothing shifts relative to
    the full-resolution static background.
    """
    blend = getattr(obj, 'blend_mode', 'normal') or 'normal'

    if active_scale < 0.999 and blend == 'normal':
        dl = max(24.0, dpi * active_scale)
        s = dl / dpi
        size_l = (max(1, int(round(size[0] * s))), max(1, int(round(size[1] * s))))
        sig = _obj_sig_no_translation(obj, variables, dl, size_l, res_fp)
        if sig is not None:
            tx = int(mm_to_px(obj.transform.x, dpi))   # full-dpi position (exact)
            ty = int(mm_to_px(obj.transform.y, dpi))
            ent = _ACTIVE_OBJ_CACHE.get(sig)
            if ent is not None:
                crop, base_pos, ref_tx, ref_ty = ent
                if crop is not None:
                    _alpha_composite_clipped(canvas, crop,
                                             base_pos[0] + (tx - ref_tx),
                                             base_pos[1] + (ty - ref_ty))
                return
            iso = Image.new("RGBA", size_l, (0, 0, 0, 0))
            _render_object(obj, iso, resources, variables, dl)
            bbox = iso.getbbox()
            _ACTIVE_OBJ_CACHE.clear()
            if bbox is None:
                _ACTIVE_OBJ_CACHE[sig] = (None, (0, 0), tx, ty)
                return
            crop_l = iso.crop(bbox)
            fw = max(1, int(round(crop_l.width / s)))
            fh = max(1, int(round(crop_l.height / s)))
            crop = crop_l.resize((fw, fh), Image.NEAREST)   # pixelate the preview
            pos = (int(round(bbox[0] / s)), int(round(bbox[1] / s)))
            _ACTIVE_OBJ_CACHE[sig] = (crop, pos, tx, ty)
            canvas.alpha_composite(crop, pos)
            return
        # sig unavailable -> fall through to a normal full-dpi render

    sig = (_obj_sig_no_translation(obj, variables, dpi, size, res_fp)
           if blend == 'normal' else None)
    if sig is None:
        _render_object(obj, canvas, resources, variables, dpi)
        return
    tx = int(mm_to_px(obj.transform.x, dpi))
    ty = int(mm_to_px(obj.transform.y, dpi))
    ent = _ACTIVE_OBJ_CACHE.get(sig)
    if ent is not None:
        crop, base_pos, ref_tx, ref_ty = ent
        if crop is not None:
            _alpha_composite_clipped(canvas, crop,
                                     base_pos[0] + (tx - ref_tx),
                                     base_pos[1] + (ty - ref_ty))
        return
    iso = Image.new("RGBA", size, (0, 0, 0, 0))
    _render_object(obj, iso, resources, variables, dpi)
    bbox = iso.getbbox()
    _ACTIVE_OBJ_CACHE.clear()   # keep only the current active object
    if bbox is None:
        _ACTIVE_OBJ_CACHE[sig] = (None, (0, 0), tx, ty)
    else:
        crop = iso.crop(bbox); pos = (bbox[0], bbox[1])
        _ACTIVE_OBJ_CACHE[sig] = (crop, pos, tx, ty)
        canvas.alpha_composite(crop, pos)


def clear_object_cache():
    """Drop all cached per-object rasters (call when resources change)."""
    _OBJ_CACHE.clear()
    _ACTIVE_BG_CACHE.clear()
    _ACTIVE_OBJ_CACHE.clear()


def _res_fp(resources):
    try:
        items = []
        for k, v in (resources or {}).items():
            sz = getattr(v, 'size', None)
            if sz is None:
                sz = len(v) if hasattr(v, '__len__') else id(v)
            items.append((str(k), str(sz)))
        return tuple(sorted(items))
    except Exception:
        return ()


def _vars_fp(variables):
    if variables is None:
        return ()
    if hasattr(variables, 'to_dict'):
        try:
            return tuple(sorted(variables.to_dict().items()))
        except Exception:
            pass
    if isinstance(variables, dict):
        try:
            return tuple(sorted(variables.items()))
        except Exception:
            pass
    try:
        return repr(variables)
    except Exception:
        return ()


def _obj_sig(obj, variables, dpi, size, res_fp):
    try:
        raw = (repr(obj.to_dict()) + repr(_vars_fp(variables))
               + str(dpi) + str(size) + repr(res_fp))
        return _hashlib.sha1(raw.encode('utf-8', 'ignore')).hexdigest()
    except Exception:
        return None


def _render_object_cached(obj, canvas, resources, variables, dpi, res_fp):
    """Pixel-identical wrapper around _render_object that reuses an isolated
    raster for unchanged objects. Only used for normal-blend objects (a
    non-normal blend blends against the objects beneath it, so it can't be
    rendered in isolation); those fall back to a direct render."""
    blend = getattr(obj, 'blend_mode', 'normal') or 'normal'
    sig = _obj_sig(obj, variables, dpi, canvas.size, res_fp) if blend == 'normal' else None
    if sig is None:
        _render_object(obj, canvas, resources, variables, dpi)
        return
    ent = _OBJ_CACHE.get(sig)
    if ent is not None:
        crop, pos = ent
        if crop is not None:
            canvas.alpha_composite(crop, pos)
        _OBJ_CACHE.move_to_end(sig)
        return
    iso = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    _render_object(obj, iso, resources, variables, dpi)
    bbox = iso.getbbox()
    if bbox is None:
        _OBJ_CACHE[sig] = (None, (0, 0))
    else:
        crop = iso.crop(bbox); pos = (bbox[0], bbox[1])
        _OBJ_CACHE[sig] = (crop, pos)
        canvas.alpha_composite(crop, pos)
    while len(_OBJ_CACHE) > _OBJ_CACHE_CAP:
        _OBJ_CACHE.popitem(last=False)


def _render_object(obj, canvas, resources, variables, dpi):
    # v4.1.0: Render layer effects efficiently using bbox-based buffers.
    effects_below = []
    effects_above = []
    if hasattr(obj, 'effects') and obj.effects:
        for e in obj.effects:
            if not e.enabled: continue
            if e.type in ('drop_shadow', 'outer_glow', 'long_shadow') or \
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
    # v4.2.7.13: render the body with NORMAL blending into the temp buffer. The
    # object's own blend mode is applied later, when the whole layer is put onto
    # the canvas — otherwise it would blend against the empty temp and be lost
    # (the "blending doesn't work for shapes/curves that have effects" bug).
    _obj_blend = getattr(obj, 'blend_mode', 'normal') or 'normal'
    _saved_blend = getattr(obj, 'blend_mode', 'normal')
    try:
        obj.blend_mode = 'normal'
        _render_object_dispatch(obj, temp, resources, variables, dpi)
    finally:
        obj.blend_mode = _saved_blend

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
        if e.type == 'long_shadow':
            # the long-shadow soft blur is a BOX (reach ~ size_px), not a 3-sigma
            # Gaussian, so it needs far less margin than the generic size*3 base.
            _bmax = float(e.size or 0.0)
            for _s in (getattr(e, 'ls_grad_blurs', []) or []):
                try:
                    _bmax = max(_bmax, float(_s[1]))
                except Exception:
                    pass
            em = (mm_to_px(abs(getattr(e, 'ls_length', 10.0)), dpi)
                  + mm_to_px(_bmax, dpi) * 1.3 + 10)
        elif e.type == 'chromatic_aberration':
            ca_off = max(abs(getattr(e, 'ca_offset', 0.5)),
                         abs(getattr(e, 'ca_r_offset', 0.0)),
                         abs(getattr(e, 'ca_g_offset', 0.0)),
                         abs(getattr(e, 'ca_b_offset', 0.0)))
            em = max(em, mm_to_px(ca_off, dpi) + 6)
            if getattr(e, 'ca_mode', 'linear') == 'radial':
                dmax = max(abs(getattr(e, 'ca_r_distort', 0.0)),
                           abs(getattr(e, 'ca_g_distort', 0.0)),
                           abs(getattr(e, 'ca_b_distort', 0.0))) / 100.0
                em = max(em, int((max(x1 - x0, y1 - y0) * 0.5 * dmax)) + 6)
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

    # v4.2.7.20: a halftone screen in "just patterns" mode (ht_keep_background
    # False) replaces the layer content — skip compositing the body so only the
    # screened dots show (the body is still available to the effect via obj_buf
    # for sampling). If keep_background is on, the body is drawn as usual.
    def _ht_bg(e):
        b = (getattr(e, 'ht_background', '') or '').lower()
        if not b:
            b = 'layer' if getattr(e, 'ht_keep_background', False) else 'native'
        return b
    _skip_body = any(
        getattr(e, 'enabled', True) and getattr(e, 'type', '') == 'halftone'
        and _ht_bg(e) != 'layer'
        for e in effects_above)

    # v4.1.1: Composite the actual object pixels at fill_opacity
    # v4.2.7.13: ...and with the object's blend mode (against the real canvas,
    # i.e. the background + any below-effects already drawn).
    fill_op = getattr(obj, 'fill_opacity', 1.0)
    if fill_op < 1.0:
        r, g, b, a = temp.split()
        a = a.point(lambda v, fo=fill_op: int(v * fo))
        body = Image.merge("RGBA", (r, g, b, a))
    else:
        body = temp
    if not _skip_body:
        _composite_with_blend(canvas, body, (0, 0), _obj_blend)

    # Apply effects-above (inner shadow, inner glow, color overlay, gradient)
    for e in effects_above:
        _apply_layer_effect_above(canvas, obj_buf, e, dpi, paste_pos)


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
        logging.getLogger(__name__).warning("render_subdocument: could not load sub-document: %s", e)
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


def _blur_L(img, radius_px):
    """v4.2.11.2: Gaussian-blur an 'L' matte on the GPU when GPU effects are
    enabled AND available, otherwise on the CPU (PIL). Per-call fallback: any
    GPU miss (unavailable, radius over budget, error) silently uses the CPU, so
    output is always produced and is visually identical (validated parity:
    mean diff ~0.35). This backs drop/inner shadow, outer/inner glow and the
    bevel soften, which all share this Gaussian."""
    from PIL import ImageFilter
    if radius_px is None or radius_px <= 0:
        return img
    try:
        from edof.engine import gpu as _gpu
        if _gpu.is_enabled():
            res = _gpu.gpu_gaussian_blur_L(img, radius_px)
            if res is not None:
                _gpu.blur_gpu_count += 1
                return res
            _gpu.blur_cpu_count += 1
    except Exception:
        pass
    return img.filter(ImageFilter.GaussianBlur(radius_px))


def _variable_box_blur(A, rmap):
    """4-pass per-pixel-radius box blur (the long-shadow variable blur core).

    Tries the GPU SAT-scan implementation when enabled, otherwise runs the CPU
    summed-area-table path. The CPU gather uses flat take() indices (about 1.9x
    faster than 2D fancy indexing, bit-identical output).
    """
    import numpy as _np
    H, W = A.shape
    try:
        from edof.engine import gpu as _gpu
        if _gpu.is_enabled():
            res = _gpu.gpu_variable_box_blur(A, rmap)
            if res is not None:
                _gpu.blur_gpu_count += 1
                return res
    except Exception:
        pass
    yy, xx = _np.mgrid[0:H, 0:W]
    y1b = _np.clip(yy - rmap, 0, H); y2b = _np.clip(yy + rmap + 1, 0, H)
    x1b = _np.clip(xx - rmap, 0, W); x2b = _np.clip(xx + rmap + 1, 0, W)
    area = ((y2b - y1b) * (x2b - x1b)).astype(_np.float32).ravel()
    Wp = W + 1
    i22 = (y2b * Wp + x2b).ravel(); i12 = (y1b * Wp + x2b).ravel()
    i21 = (y2b * Wp + x1b).ravel(); i11 = (y1b * Wp + x1b).ravel()
    out = A
    for _ in range(4):
        sat = _np.zeros((H + 1, W + 1), _np.float32)
        _np.cumsum(_np.cumsum(out, axis=0), axis=1, out=sat[1:, 1:])
        f = sat.ravel()
        out = ((f.take(i22) - f.take(i12) - f.take(i21) + f.take(i11))
               / area).reshape(H, W)
    return out


def _ls_slide_min_sym(A, r, axis=0):
    """min over the symmetric window [i-r, i+r] along `axis` (doubling shifts)."""
    import numpy as _np
    r = int(r)
    if r <= 0:
        return A.copy()
    out = A.copy()
    cov = 0
    step = 1
    while cov < r:
        d = min(step, r - cov)
        a = _np.empty_like(out)
        b = _np.empty_like(out)
        if axis == 0:
            a[:-d, :] = out[d:, :]; a[-d:, :] = out[-d:, :]
            b[d:, :] = out[:-d, :]; b[:d, :] = out[:d, :]
        else:
            a[:, :-d] = out[:, d:]; a[:, -d:] = out[:, -d:]
            b[:, d:] = out[:, :-d]; b[:, :d] = out[:, :d]
        out = _np.minimum(_np.minimum(out, a), b)
        cov += d; step = cov
    return out


def _ls_slide_max_x(A, w):
    """max over the trailing window [x-w+1, x] along X (doubling shifts)."""
    import numpy as _np
    if w <= 1:
        return A
    out = A.copy()
    cov = 1
    while cov < w:
        d = min(cov, w - cov)
        out[:, d:] = _np.maximum(out[:, d:], out[:, :-d])
        cov += d
    return out


def _ls_stops_interp(stops, t, default):
    """piecewise-linear lookup of [[t, v...], ...] stops at t (array)."""
    import numpy as _np
    if not stops:
        return None
    st = sorted((list(s) for s in stops), key=lambda s: s[0])
    xs = _np.array([s[0] for s in st], _np.float32)
    nvals = len(st[0]) - 1
    outs = []
    for k in range(nvals):
        ys = _np.array([s[1 + k] for s in st], _np.float32)
        outs.append(_np.interp(_np.clip(t, 0.0, 1.0), xs, ys).astype(_np.float32))
    return outs[0] if nvals == 1 else outs


def _long_shadow_matte(alpha, dxu, dyu, length_px,
                       color_stops, alpha_stops, blur_stops):
    """Long shadow: per-point rays, per-row exact (no taper -> 1D model).

    Every silhouette point emits a ray of length L along the throw; the source
    point's alpha scales its ray; the shadow is the max-union of all rays.
    With taper gone the union is exactly per-row in the rotated frame
    (throw = +X):  field(y, x) = max over d in [0, L] of R(y, x - d) * a(d/L).

    Stops (already resolved by the dispatcher, never empty):
      color_stops [[t, r, g, b], ...]   colour c(t), applied in page frame
      alpha_stops [[t, a01], ...]       alpha a(t) along each ray
      blur_stops  [[t, radius_px], ...] blur r(t), 0 keeps the contact sharp

    Fast paths: constant a(t) -> the field is ONE doubling smear (no segment
    loop); the GPU computes the EXACT max-convolution in a single kernel when
    enabled; the CPU fallback uses the youngest-ray term + a segment pass
    (windowed max-decomposition), allocation-free in the hot loop. The blur
    radius is FRACTIONAL: two integer-radius variable box blurs lerped per
    pixel, which removes the radius-quantisation rings ("checkerboard") the
    integer map produced. Everything stays float32 until the final compose."""
    import numpy as _np
    from PIL import ImageFilter
    W, H = alpha.size
    L = max(1, int(length_px))

    # ---- STAGE 1: project (rotate the throw to +X) --------------------------
    A_deg = math.degrees(math.atan2(dyu, dxu))
    if abs(((A_deg + 45.0) % 90.0) - 45.0) > 0.5:
        alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
    rot = alpha.rotate(A_deg, resample=Image.BILINEAR, expand=True, fillcolor=0)
    R = _np.asarray(rot, dtype=_np.float32)
    _full_shape = R.shape
    max_blur = max(float(s[1]) for s in blur_stops)
    _ys0, _xs0 = _np.where(R > 40.0)
    if len(_xs0):
        _mY = int(max_blur * 1.15) + 6
        x_lo = max(0, int(_xs0.min()) - int(max_blur * 1.15) - 6)
        x_hi = min(R.shape[1], int(_xs0.max()) + L + int(max_blur * 1.15) + 6)
        y_lo = max(0, int(_ys0.min()) - _mY)
        y_hi = min(R.shape[0], int(_ys0.max()) + _mY)
        R = _np.ascontiguousarray(R[y_lo:y_hi, x_lo:x_hi])
    else:
        x_lo = y_lo = 0
    rh, rw = R.shape
    objm = R > 40.0

    # ---- youngest-ray t (continuous, per row) --------------------------------
    colsr = _np.broadcast_to(_np.arange(rw, dtype=_np.float32), (rh, rw))
    idx = _np.where(objm, colsr, -1.0)
    last = _np.maximum.accumulate(idx, axis=1)
    dist = colsr - last
    dist[last < 0] = float(L + 1)
    dist[objm] = 0.0
    g = _np.clip(dist / float(L), 0.0, 1.0).astype(_np.float32)
    # the faint leading AA fringe (R in 2..40, upstream of any objm source)
    # SELF-emits at t = 0 -- it must not inherit the no-upstream sentinel
    # (t = 1), which gave the silhouette's leading rim the MAXIMUM blur
    # radius and painted a dark crescent / hard cut at the start.
    g = _np.where((R > 2.0) & (last < 0.0), 0.0, g).astype(_np.float32)

    # ---- STAGE 2: per-ray alpha field ----------------------------------------
    a_vals = _np.array([s[1] for s in alpha_stops], _np.float32)
    a_const = float(a_vals.max() - a_vals.min()) <= 1e-4

    def _smear_max(A0, span):
        out = A0.copy()
        cov = 1
        while cov < span:
            d = min(cov, span - cov)
            _np.maximum(out[:, d:], out[:, :-d], out=out[:, d:])
            cov += d
        return out

    field = None
    if not a_const:
        try:
            from edof.engine import gpu as _gpu
            if _gpu.is_enabled() and _gpu.gpu_available():
                lut = _ls_stops_interp(alpha_stops,
                                       _np.linspace(0.0, 1.0, 1024), 1.0)
                field = _gpu.gpu_long_shadow_field(R, L, lut)
        except Exception:
            field = None

    if field is None:
        # youngest-ray term: the value OF the nearest upstream emitter (not a
        # running max -- pairing the strongest upstream value with the nearest
        # distance overestimated behind semi-transparent emitters), times a(g).
        # This is a true single-ray contribution, so it never overestimates.
        if a_const:
            # constant a: the exact max-convolution is the plain smear (every
            # ray has the same weight, the strongest upstream emitter wins).
            field = _smear_max(R, L) * float(a_vals[0])
            field[g >= 1.0] = 0.0
        else:
            last_i = _np.clip(last, 0, rw - 1).astype(_np.int64)
            v_last = _np.take_along_axis(R, last_i, axis=1)
            v_last[last < 0] = 0.0
            a_of = _ls_stops_interp(alpha_stops, g, 1.0)
            field = v_last * a_of
            field[g >= 1.0] = 0.0
            # segment pass: secondary contributions the youngest ray misses
            # (strong old emitters through faint young ones, non-monotone
            # alpha). Allocation-free hot loop over a shared buffer.
            mono = bool(_np.all(_np.diff(_ls_stops_interp(
                alpha_stops, _np.linspace(0, 1, 65), 1.0)) <= 1e-6))
            N = 32 if mono else 64
            N = int(min(N, max(8, L)))
            w0 = max(1, int(math.ceil(L / float(N))))
            SM = _ls_slide_max_x(R, w0 + 1)
            ts = _np.linspace(0.0, 1.0, N + 1)
            a_s = _ls_stops_interp(alpha_stops,
                                   _np.linspace(0.0, 1.0, 4 * N + 1), 1.0)
            buf = _np.empty_like(R)
            for i in range(N):
                d0 = int(round(ts[i] * L))
                a_seg = float(a_s[4 * i: 4 * i + 5].max())
                if a_seg <= 0.002 or d0 >= rw:
                    continue
                nb = rw - d0
                _np.multiply(SM[:, :nb], a_seg, out=buf[:, :nb])
                _np.maximum(field[:, d0:], buf[:, :nb], out=field[:, d0:])

    # ---- STAGE 3: ONE variable blur (fractional radius) ----------------------
    A = field.astype(_np.float32, copy=False)
    if max_blur >= 0.5:
        # blur radius driver: youngest t inside the shadow. OUTSIDE (the soft
        # halo the blur itself creates) the driver must be LOCAL: each halo
        # pixel takes the t of the nearby shadow it belongs to, propagated
        # vertically out of the field over the blur reach, plus the row's own
        # g for the downstream end cap. (The previous driver was anchored to
        # the GLOBAL trailing object column, so any shadow cast before it --
        # e.g. one glyph's shadow passing beside another in text -- got a ZERO
        # outside radius: blurred inward, razor-sharp outward.) The root flank
        # stays sharp because the propagated t near the contact is ~0. Pixels
        # with no shadow within reach get t = 1; their gather windows are
        # empty, the SAT gather is O(1) per pixel, so it costs nothing.
        # Float de-stair smooth (no uint8 quantisation -> no radius rings).
        t_in = _np.where(A > 2.0, g, 2.0).astype(_np.float32)
        reach = int(math.ceil(max_blur)) + 2
        # propagate "the t of the NEAREST shadow", not "the smallest t in a
        # 2D window": (1) the perpendicular halo takes the LOCAL body t from
        # the Y-only pass -- a composed 2D window min pulled smaller t from
        # up to `reach` px upstream and visibly tightened the side halo;
        # (2) ONLY where the Y pass found nothing (sentinel) does the X pass
        # fill in: the BACKWARD halo past the leading edge (body t ~ 0 in the
        # same row -> radius = blur(0): constant/custom soften backward,
        # linear stays root-sharp) and the corners (the X pass reads the
        # already-filled perpendicular strips, so the halo wraps corners
        # roundly instead of leaving notches).
        tY = _ls_slide_min_sym(t_in, reach, axis=0)
        tX = _ls_slide_min_sym(tY, reach, axis=1)
        t_halo = _np.where(tY > 1.5, tX, tY)
        g_row = _np.where(last >= 0.0, g, 2.0).astype(_np.float32)
        tdist = _np.minimum(t_halo, g_row)
        tdist = _np.where(A > 2.0, g, tdist)
        # sentinel = no shadow within reach (e.g. UPSTREAM of the leading
        # edge): radius 0, NOT max -- clipping the sentinel to t = 1 gave
        # those pixels the maximum radius, which grew a spurious halo
        # BACKWARD past the silhouette's leading edge that the rotated-frame
        # crop box then cut into a hard diagonal line at the start.
        tdist = _np.where(tdist > 1.5, 0.0, tdist)
        tdist = _np.clip(tdist, 0.0, 1.0)
        tdist = _ls_gauss_f32(tdist, 0.8)
        rpx = _ls_stops_interp(blur_stops, tdist, 0.0)
        rq = _np.clip(rpx / 4.0, 0.0, max(1, min(rh, rw) // 2)).astype(_np.float32)
        r0 = _np.floor(rq).astype(_np.int64)
        frac = (rq - r0).astype(_np.float32)
        if int(r0.max()) >= 1 or float(frac.max()) > 0.01:
            b0 = _variable_box_blur(A, r0)
            b1 = _variable_box_blur(A, r0 + 1)
            out = b0 * (1.0 - frac) + b1 * frac
        else:
            out = A
    else:
        out = A

    # ---- STAGE 4: rotate back, trim bleed, colour ----------------------------
    def _unshear(arr2d):
        if arr2d.shape != _full_shape:
            full = _np.zeros(_full_shape, _np.float32)
            full[y_lo:y_lo + rh, x_lo:x_lo + rw] = arr2d
            arr2d = full
        im = Image.fromarray(_np.clip(arr2d, 0, 255).astype('uint8'), 'L').rotate(
            -A_deg, resample=Image.BILINEAR, expand=True, fillcolor=0)
        a = _np.asarray(im, dtype=_np.float32)
        bh2, bw2 = a.shape
        yy = max(0, (bh2 - H) // 2); xx = max(0, (bw2 - W) // 2)
        c = a[yy:yy + H, xx:xx + W]
        if c.shape != (H, W):
            cc = _np.zeros((H, W), _np.float32)
            ch, cw = min(H, c.shape[0]), min(W, c.shape[1]); cc[:ch, :cw] = c[:ch, :cw]; c = cc
        return c
    cov_p = _unshear(out)
    t_p = _unshear(_np.clip(g, 0.0, 1.0) * 255.0) / 255.0
    vmask = _unshear((out > 0.5).astype(_np.float32) * 255.0)
    cov_p = _np.where(vmask >= 128.0, cov_p, 0.0)

    t = _np.clip(t_p, 0.0, 1.0)
    cr, cg_, cb = _ls_stops_interp(color_stops, t, 0.0)
    rgb = _np.dstack([cr, cg_, cb])
    alpha_ch = _np.clip(cov_p, 0, 255)
    rgba = _np.dstack([_np.clip(rgb, 0, 255), alpha_ch]).astype('uint8')
    return Image.fromarray(rgba, 'RGBA')


def _ls_gauss_f32(arr01, sigma):
    """small separable float32 Gaussian on a 0..1 field (no 8-bit roundtrip)."""
    import numpy as _np
    rad = max(1, int(math.ceil(sigma * 2.5)))
    xs = _np.arange(-rad, rad + 1, dtype=_np.float32)
    k = _np.exp(-(xs * xs) / (2.0 * sigma * sigma))
    k /= k.sum()
    p = _np.pad(arr01, ((0, 0), (rad, rad)), mode='edge')
    h = _np.zeros_like(arr01)
    for i, kv in enumerate(k):
        h += kv * p[:, i:i + arr01.shape[1]]
    p = _np.pad(h, ((rad, rad), (0, 0)), mode='edge')
    v = _np.zeros_like(arr01)
    for i, kv in enumerate(k):
        v += kv * p[i:i + arr01.shape[0], :]
    return v

def _dilate_L(img, radius_px):
    """Grow an 'L' matte by ~radius_px (Photoshop Spread/Choke)."""
    from PIL import ImageFilter
    r = int(radius_px)
    if r <= 0:
        return img
    r = min(r, 75)  # cap kernel for performance
    return img.filter(ImageFilter.MaxFilter(r * 2 + 1))


def _box1d(a, r, axis):
    import numpy as np
    a = np.swapaxes(a, axis, -1)
    ap = np.pad(a, [(0, 0)] * (a.ndim - 1) + [(r, r)], mode='edge')
    C = np.cumsum(ap, axis=-1)
    C = np.concatenate([np.zeros(C.shape[:-1] + (1,), dtype=C.dtype), C], axis=-1)
    win = C[..., 2 * r + 1:] - C[..., :-(2 * r + 1)]
    return np.swapaxes(win / (2 * r + 1), axis, -1)


def _box_blur_np(a, r, passes=3):
    """Fast separable box blur (≈ Gaussian after a few passes), kept fully in
    float so the result has no 8-bit quantization stair-steps. Used for the
    bevel height map to avoid concentric contour-ring artifacts."""
    r = int(r)
    if r < 1:
        return a
    for _ in range(passes):
        a = _box1d(a, r, 1)
        a = _box1d(a, r, 0)
    return a


def _edt_1d(f1, INF):
    import numpy as np
    n = len(f1); d = np.empty(n); v = np.zeros(n, dtype=np.int64); z = np.empty(n + 1)
    k = 0; v[0] = 0; z[0] = -INF; z[1] = INF
    for q in range(1, n):
        denom = (2.0 * q - 2.0 * v[k])
        s = ((f1[q] + q * q) - (f1[v[k]] + v[k] * v[k])) / denom
        while s <= z[k]:
            k -= 1
            denom = (2.0 * q - 2.0 * v[k])
            s = ((f1[q] + q * q) - (f1[v[k]] + v[k] * v[k])) / denom
        k += 1; v[k] = q; z[k] = s; z[k + 1] = INF
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        d[q] = (q - v[k]) * (q - v[k]) + f1[v[k]]
    return d


def _edt(mask):
    """Euclidean distance (in px) from each True pixel to the nearest False
    pixel. Uses scipy when available, else a pure-numpy Felzenszwalb transform
    so EDOF has no hard scipy dependency."""
    import numpy as np
    try:
        from scipy import ndimage
        return ndimage.distance_transform_edt(mask)
    except Exception:
        H0, W0 = mask.shape
        scale = 1
        while (H0 // scale) * (W0 // scale) > 200000 and scale < 16:
            scale += 1
        if scale > 1:
            from PIL import Image as _I
            sm = _I.fromarray((mask.astype('uint8') * 255)).resize(
                (max(1, W0 // scale), max(1, H0 // scale)), _I.Resampling.NEAREST)
            small = np.asarray(sm) > 128
        else:
            small = mask
        INF = 1e20
        f = np.where(small, INF, 0.0)
        for j in range(f.shape[1]):
            f[:, j] = _edt_1d(f[:, j], INF)
        for i in range(f.shape[0]):
            f[i, :] = _edt_1d(f[i, :], INF)
        d = np.sqrt(f) * scale
        if scale > 1:
            from PIL import Image as _I
            d = np.asarray(_I.fromarray(d.astype('float32'), 'F').resize(
                (W0, H0), _I.Resampling.BILINEAR))
        return d


def _render_bevel_shaded(canvas, alpha, effect, dpi, px, py, bw, bh, outer):
    """Photoshop-style bevel: build a height ramp from the edge, derive surface
    normals, and light them (azimuth = direction, elevation = altitude) so the
    sloped bevel band gets a smooth highlight on the lit side and shadow on the
    other. Confined to the bevel band (the flat face stays untouched)."""
    import numpy as np
    from PIL import Image, ImageFilter
    import math as _m
    size_px = max(2, int(mm_to_px(effect.size, dpi)))
    tech = getattr(effect, 'bevel_technique', 'smooth') or 'smooth'
    depth = max(0.0, getattr(effect, 'bevel_depth', 100.0) / 100.0)
    bdir = getattr(effect, 'bevel_dir', 'up') or 'up'
    soften_px = mm_to_px(max(0.0, getattr(effect, 'soften', 0.0)), dpi)
    altitude = max(0.0, min(90.0, getattr(effect, 'altitude', 45.0)))
    hl_op = getattr(effect, 'highlight_opacity', 0.75)
    sh_op = getattr(effect, 'shadow_opacity', 0.75)
    op = effect.opacity
    a = np.asarray(alpha, dtype=np.float32) / 255.0
    # Height map from a distance transform: ramps 0 -> 1 over the bevel width and
    # then stays flat (plateau) in the interior, so the flat face has zero slope
    # and gets no shading (no concentric-ring banding). For an outer bevel the
    # ramp lives just outside the silhouette.
    if outer:
        dist = _edt(a <= 0.5)
    else:
        dist = _edt(a > 0.5)
    t = np.clip(dist / float(max(1, size_px)), 0.0, 1.0)
    if tech == 'chisel_hard':
        prof = t
    elif tech == 'chisel_soft':
        prof = np.clip(t * 1.15, 0.0, 1.0) ** 0.85
    else:  # smooth -> rounded profile
        prof = np.sin(t * (np.pi / 2.0))
    # light float smoothing of the plateau kink (small radius: no dome)
    H = _box_blur_np(prof.astype(np.float64), max(1, int(size_px * 0.18)), passes=2).astype(np.float32)
    gy, gx = np.gradient(H)
    amp = size_px * 1.6 * (0.4 + depth)
    if bdir == 'down':
        gx = -gx; gy = -gy
    nx = -gx * amp; ny = -gy * amp; nz = np.ones_like(H)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-6
    nx /= ln; ny /= ln; nz /= ln
    az = _m.radians(effect.direction); alt = _m.radians(altitude)
    lx = _m.cos(alt) * _m.cos(az); ly = -_m.cos(alt) * _m.sin(az); lz = _m.sin(alt)
    lam = nx * lx + ny * ly + nz * lz
    slope = np.sqrt(gx * gx + gy * gy)
    band = np.clip(slope * (size_px * 3.0), 0.0, 1.0)
    if outer:
        band = band * np.clip(1.0 - a, 0.0, 1.0)
    else:
        band = band * a
    hi = np.clip(lam, 0.0, 1.0) * band * (hl_op * op)
    sh = np.clip(-lam, 0.0, 1.0) * band * (sh_op * op)

    def _to_L(arr):
        im = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype('uint8'), 'L')
        if soften_px > 0:
            im = _blur_L(im, soften_px)
        return im
    c2 = effect.color2
    hl = Image.new("RGBA", (bw, bh), (c2[0], c2[1], c2[2], 0)); hl.putalpha(_to_L(hi))
    c1 = effect.color
    sh_img = Image.new("RGBA", (bw, bh), (c1[0], c1[1], c1[2], 0)); sh_img.putalpha(_to_L(sh))
    _composite_with_blend(canvas, sh_img, (px, py), getattr(effect, 'blend_mode', 'multiply') or 'multiply')
    _composite_with_blend(canvas, hl, (px, py), getattr(effect, 'blend_mode2', 'screen') or 'screen')


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
        s = max(0.0, min(1.0, getattr(effect, 'spread', 0.0)))
        size_px = max(0, mm_to_px(effect.size, dpi))
        expand_px = int(round(size_px * s))
        blur_px = max(0, size_px * (1.0 - s))
        # Translate the alpha (silhouette only) by (dx, dy)
        shadow_alpha = Image.new("L", (bw, bh), 0)
        shadow_alpha.paste(alpha, (dx, dy))
        if expand_px > 0:
            shadow_alpha = _dilate_L(shadow_alpha, expand_px)
        if blur_px > 0:
            shadow_alpha = _blur_L(shadow_alpha, blur_px)
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
        s = max(0.0, min(1.0, getattr(effect, 'spread', 0.0)))
        size_px = max(1, mm_to_px(effect.size, dpi))
        expand_px = int(round(size_px * s))
        blur_px = max(0, size_px * (1.0 - s))
        glow_alpha = _dilate_L(alpha, expand_px) if expand_px > 0 else alpha
        if blur_px > 0:
            glow_alpha = _blur_L(glow_alpha, blur_px)
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

    elif effect.type == 'long_shadow':
        # v4.2.11.57: three independent mode selectors, all resolved here into
        # stop lists for the per-point ray renderer. Taper and cast are GONE.
        #   BLUR  mode: solid | constant | linear | custom
        #   COLOR mode: solid | custom
        #   ALPHA mode: solid | fade | custom
        # Legacy documents (pre-.57) are derived: ls_mode 'soft' maps to its
        # ls_blur_mode (linear/constant), 'cast' to linear; ls_fade to the
        # alpha mode; ls_color_grad to a 2-stop colour gradient; ls_taper is
        # ignored (renders as 1.0, the straight ray).
        rad = math.radians(effect.direction)
        dxu = math.cos(rad); dyu = -math.sin(rad)
        length_px = max(1, int(mm_to_px(abs(getattr(effect, 'ls_length', 10.0)), dpi)))
        size_px = max(0.0, mm_to_px(effect.size, dpi))
        color = effect.color
        color2 = getattr(effect, 'color2', (0, 0, 0, 255)) or (0, 0, 0, 255)

        bm = (getattr(effect, 'ls_blur_mode', '') or '').strip().lower()
        if bm not in ('solid', 'constant', 'linear', 'custom'):
            lm = (getattr(effect, 'ls_mode', 'solid') or 'solid').lower()
            if lm == 'solid':
                bm = 'solid'
            elif lm == 'cast':
                bm = 'linear'
            else:                       # legacy 'soft'
                bm = 'constant' if bm == 'constant' else 'linear'
        am = (getattr(effect, 'ls_alpha_mode', '') or '').strip().lower()
        if am not in ('solid', 'fade', 'custom'):
            if getattr(effect, 'ls_grad_alphas', None):
                am = 'custom'
            else:
                am = 'fade' if bool(getattr(effect, 'ls_fade', True)) else 'solid'
        cm = (getattr(effect, 'ls_color_mode', '') or '').strip().lower()
        if cm not in ('solid', 'custom'):
            cm = 'custom' if (getattr(effect, 'ls_grad_colors', None)
                              or bool(getattr(effect, 'ls_color_grad', False))) else 'solid'

        # ---- resolve stops (never empty; customs fall back to defaults) ----
        if bm == 'solid':
            bstops = [[0.0, 0.0], [1.0, 0.0]]
        elif bm == 'constant':
            bstops = [[0.0, size_px], [1.0, size_px]]
        elif bm == 'linear':
            bstops = [[0.0, 0.0], [1.0, size_px]]
        else:
            raw = list(getattr(effect, 'ls_grad_blurs', []) or [])
            if not raw:
                raw = [[0.0, 0.0], [1.0, float(effect.size)]]
            bstops = [[float(s[0]), mm_to_px(max(0.0, float(s[1])), dpi)] for s in raw]
            if len(bstops) == 1:
                bstops.append([1.0, bstops[0][1]])
        if am == 'solid':
            astops = [[0.0, 1.0], [1.0, 1.0]]
        elif am == 'fade':
            astops = [[0.0, 1.0], [1.0, 0.0]]
        else:
            astops = [list(map(float, s)) for s in
                      (getattr(effect, 'ls_grad_alphas', []) or [])]
            if not astops:
                astops = [[0.0, 1.0], [1.0, 0.0]]
            if len(astops) == 1:
                astops.append([1.0, astops[0][1]])
        if cm == 'solid':
            cstops = [[0.0, float(color[0]), float(color[1]), float(color[2])],
                      [1.0, float(color[0]), float(color[1]), float(color[2])]]
        else:
            cstops = [list(map(float, s)) for s in
                      (getattr(effect, 'ls_grad_colors', []) or [])]
            if not cstops:
                cstops = [[0.0, float(color[0]), float(color[1]), float(color[2])],
                          [1.0, float(color2[0]), float(color2[1]), float(color2[2])]]
            if len(cstops) == 1:
                cstops.append([1.0] + list(cstops[0][1:]))
            # legacy ls_color_grad also carried the alpha pair; honour it when
            # the alpha mode is still legacy-derived
            if (not getattr(effect, 'ls_grad_colors', None)
                    and bool(getattr(effect, 'ls_color_grad', False))
                    and am == 'fade' and not getattr(effect, 'ls_grad_alphas', None)
                    and (getattr(effect, 'ls_alpha_mode', '') or '') == ''):
                a0 = (color[3] if len(color) > 3 else 255) / 255.0
                a1 = (color2[3] if len(color2) > 3 else 255) / 255.0
                astops = [[0.0, a0], [1.0, a1]]

        ls_layer = _long_shadow_matte(alpha, dxu, dyu, length_px,
                                      cstops, astops, bstops)
        if op_alpha != 255:
            a = ls_layer.getchannel("A").point(lambda v, oa=op_alpha: int(v * oa / 255))
            ls_layer.putalpha(a)
        _composite_with_blend(canvas, ls_layer, (px, py), effect.blend_mode)

    elif effect.type == 'bevel' and effect.bevel_kind == 'outer':
        _render_bevel_shaded(canvas, alpha, effect, dpi, px, py, bw, bh, outer=True)

def _ht_stencil(shape, size):
    """0..1 float stencil (size x size) for a halftone dot of the given shape."""
    import numpy as np
    size = max(1, int(size))
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    x = (xx - c) / max(1.0, c)
    y = (yy - c) / max(1.0, c)
    r = np.sqrt(x * x + y * y)
    aa = max(0.06, 2.0 / size)
    if shape in ('circle', 'dot'):
        m = np.clip((1.0 - r) / aa, 0, 1)
    elif shape == 'ring':
        m = np.minimum(np.clip((1.0 - r) / aa, 0, 1), np.clip((r - 0.55) / aa, 0, 1))
    elif shape == 'diamond':
        m = np.clip((1.0 - (np.abs(x) + np.abs(y))) / aa, 0, 1)
    elif shape == 'square':
        m = np.clip((1.0 - np.maximum(np.abs(x), np.abs(y))) / aa, 0, 1)
    elif shape == 'cross':
        th = 0.30
        m = np.maximum(np.clip((th - np.abs(x)) / aa, 0, 1),
                       np.clip((th - np.abs(y)) / aa, 0, 1))
    elif shape == 'line':
        m = np.clip((0.5 - np.abs(y)) / aa, 0, 1)
    elif shape == 'triangle':
        m = ((y <= 0.85) & (np.abs(x) <= (0.9 * (0.85 - y) / 1.7))).astype(np.float32)
    elif shape == 'hex':
        ax = np.abs(x); ay = np.abs(y)
        m = ((ax <= 0.85) & (ay <= 0.95) & (0.5 * ay + 0.866 * ax <= 0.82)).astype(np.float32)
    else:
        m = np.clip((1.0 - r) / aa, 0, 1)
    return m.astype(np.float32)


def _stamp_max(layer, arr, cx, cy):
    import numpy as np
    h, w = arr.shape
    x0 = int(round(cx - w / 2.0)); y0 = int(round(cy - h / 2.0))
    H, W = layer.shape
    ax0 = max(0, -x0); ay0 = max(0, -y0)
    bx0 = max(0, x0); by0 = max(0, y0)
    bx1 = min(W, x0 + w); by1 = min(H, y0 + h)
    if bx1 <= bx0 or by1 <= by0:
        return
    aw = bx1 - bx0; ah = by1 - by0
    sub = arr[ay0:ay0 + ah, ax0:ax0 + aw]
    tgt = layer[by0:by1, bx0:bx1]
    np.maximum(tgt, sub, out=tgt)


def _ht_pattern_stencil(b64):
    """Decode a base64 PNG into a float HxW stencil (its alpha, or luminance if
    the image has no usable alpha)."""
    import base64, io, numpy as np
    from PIL import Image
    try:
        raw = base64.b64decode(b64)
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None
    a = np.asarray(im.split()[-1], dtype=np.float32) / 255.0
    # The alpha only carries the shape if it actually varies. A fully
    # transparent OR a fully opaque (e.g. white-on-black) pattern has a flat
    # alpha and the shape lives in luminance instead, so fall back there.
    if float(a.max()) - float(a.min()) <= 0.004:
        a = np.asarray(im.convert("L"), dtype=np.float32) / 255.0
    return a


def _ht_make_buckets(src, maxd, K, R, is_shape):
    """K size buckets x R rotation variants of a dot stencil. src is a shape
    name (is_shape=True) or a float HxW pattern array."""
    import numpy as np
    from PIL import Image
    buckets = []
    for k in range(K):
        sz = max(1, int(round(maxd * (k + 1) / K)))
        if is_shape:
            base = _ht_stencil(src, sz)
        else:
            im = Image.fromarray((np.clip(src, 0, 1) * 255).astype('uint8'), 'L').resize((sz, sz), Image.LANCZOS)
            base = np.asarray(im, dtype=np.float32) / 255.0
        rots = [base]
        if R > 1:
            bim = Image.fromarray((np.clip(base, 0, 1) * 255).astype('uint8'), 'L')
            for rr in range(1, R):
                rim = bim.rotate(360.0 * rr / R, expand=True, resample=Image.BILINEAR)
                rots.append(np.asarray(rim, dtype=np.float32) / 255.0)
        buckets.append(rots)
    return buckets


def _ht_rot_idx(col, row, ci, R):
    if R <= 1:
        return 0
    h = ((col * 73856093) ^ (row * 19349663) ^ ((ci + 1) * 83492791)) & 0x7fffffff
    return h % R


def _ht_gpu_channel_layer(ci, vmap, buckets, cell, vy, hexgrid, n_rows, n_cols,
                          cos_r, sin_r, cx0, cy0, srad, K, maxd, rmode, bw, bh,
                          a_arr, csa, ox=0.0, oy=0.0, Rrot=1):
    """Vectorised grid geometry + EXACT per-cell value sampling (replicating
    the CPU loop's window .sum() expressions verbatim, v4.2.11.35: a cumsum-based
    sum has a different float32 rounding order, which could flip a dot one size
    bucket at exact .5 boundaries) + GPU instanced stamping. Returns the channel
    layer, or None to fall back.
    v4.2.11.50: covers ALL halftone cases. Custom patterns flow through the
    same buckets (only the gate excluded them); random rotation becomes K*Rrot
    atlas tiles with the variant picked by the CPU's exact _ht_rot_idx hash;
    decentralization is a constant per-channel (ox, oy) offset on the grid.
    Rotation variants are expand=True so the tile pitch is the LARGEST variant,
    not maxd."""
    import numpy as np
    from edof.engine import gpu as _gpu
    R = max(1, int(Rrot))
    T = K * R
    tile_sizes = np.zeros(T, dtype=np.int64)
    for k in range(K):
        for rr in range(R):
            tile_sizes[k * R + rr] = buckets[k][rr].shape[0]
    pitch = int(tile_sizes.max())
    if pitch <= 0:
        return None
    # memory guard: the f32 atlas upload should stay sane
    if pitch * pitch * T * 4 > 256 * 1024 * 1024:
        return None
    atlas = np.zeros((pitch, T * pitch), np.float32)
    for k in range(K):
        for rr in range(R):
            st = buckets[k][rr]; sz = st.shape[0]
            ti = k * R + rr
            atlas[0:sz, ti * pitch:ti * pitch + sz] = st
    rows = np.arange(-n_rows, n_rows + 1); cols = np.arange(-n_cols, n_cols + 1)
    RR, CC = np.meshgrid(rows, cols, indexing='ij')
    uy = RR * vy
    xoff = np.where(RR % 2 != 0, cell / 2.0, 0.0) if hexgrid else 0.0
    ux = CC * cell + xoff
    gx = ux * cos_r - uy * sin_r + cx0 + ox
    gy = ux * sin_r + uy * cos_r + cy0 + oy
    ix = gx.astype(np.int64); iy = gy.astype(np.int64)
    inb = (ix >= 0) & (ix < bw) & (iy >= 0) & (iy < bh)

    # exact CPU-order value sampling over candidate (in-bounds) cells
    cand = np.where(inb.ravel())[0]
    gxr = gx.ravel(); gyr = gy.ravel(); ixr = ix.ravel(); iyr = iy.ravel()
    rowr = RR.ravel(); colr = CC.ravel()
    inst_rows = []
    Km1 = K - 1
    for f in cand:
        iix = int(ixr[f]); iiy = int(iyr[f])
        y0 = iiy - srad if iiy - srad > 0 else 0
        y1 = iiy + srad + 1 if iiy + srad + 1 < bh else bh
        x0 = iix - srad if iix - srad > 0 else 0
        x1 = iix + srad + 1 if iix + srad + 1 < bw else bw
        a_reg = a_arr[y0:y1, x0:x1]
        asum = float(a_reg.sum())
        if asum <= 0.01:
            continue
        v_reg = vmap[y0:y1, x0:x1]
        val = float((v_reg * a_reg).sum() / asum)
        if rmode == 'size':
            scale = val; ad = 1.0
        else:
            scale = 1.0; ad = val
        if scale > 0.02:
            bk = min(K - 1, max(0, int(round(scale * Km1))))
            rr = _ht_rot_idx(int(colr[f]), int(rowr[f]), ci, R)
            ti = bk * R + rr
            sz = float(tile_sizes[ti])
            inst_rows.append((round(float(gxr[f]) - sz / 2.0),
                              round(float(gyr[f]) - sz / 2.0),
                              sz, float(ti), ad))
    inst = np.array(inst_rows, dtype=np.float32).reshape(-1, 5)
    return _gpu.gpu_halftone_stamp(atlas, pitch, T, bw, bh, inst)


def _render_halftone_mosaic(obj_buf, alpha, effect, dpi, bw, bh):
    """Per-channel shaped-dot / patterned halftone screen (the 'Maori mosaic'
    style). Optional custom pattern image(s) (1 / per-channel), random dot
    rotation, and the effect opacity all feed in. numpy + Pillow only."""
    import numpy as np
    import math as _m
    from PIL import Image
    src = np.asarray(obj_buf.convert("RGB"), dtype=np.float32)
    a_arr = np.asarray(alpha, dtype=np.float32) / 255.0
    cell = max(4.0, float(mm_to_px(abs(getattr(effect, 'ht_dot', 1.5)), dpi)))
    shape = getattr(effect, 'ht_shape', 'circle') or 'circle'
    mode = (getattr(effect, 'ht_color_mode', 'cmyk') or 'cmyk').lower()
    rmode = (getattr(effect, 'ht_render_mode', 'size') or 'size').lower()
    sizef = max(0.05, getattr(effect, 'ht_size_factor', 115.0) / 100.0)
    oscale = max(0.2, getattr(effect, 'ht_overlay_scale', 1.5))
    decent = max(0.0, getattr(effect, 'ht_decentralization', 0.0) / 100.0)
    angle_step = getattr(effect, 'ht_angle', 72.0)
    hexgrid = bool(getattr(effect, 'ht_hex', True))
    randrot = bool(getattr(effect, 'ht_random_rotate', False))
    clip = (getattr(effect, 'ht_clip', 'whole') or 'whole').lower()
    op = max(0.0, min(1.0, getattr(effect, 'opacity', 1.0)))

    Rc = src[..., 0]; Gc = src[..., 1]; Bc = src[..., 2]
    extra = bool(getattr(effect, 'ht_extra_channel', False))
    extra_col = (getattr(effect, 'ht_extra_color', 'auto') or 'auto').lower()
    if extra_col == 'auto':
        extra_col = 'black' if mode == 'rgb' else 'white'
    enabled = list(getattr(effect, 'ht_channels_enabled', []) or [])
    bright = np.maximum(np.maximum(Rc, Gc), Bc) / 255.0
    white_amt = np.minimum(np.minimum(Rc, Gc), Bc) / 255.0  # achromatic white floor
    dark_amt = 1.0 - bright                                  # darkness in all channels
    if mode == 'rgb':
        chans = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        vmaps = [Rc / 255.0, Gc / 255.0, Bc / 255.0]
        kinds = ['add', 'add', 'add']
    else:
        chans = [(0, 255, 255), (255, 0, 255), (255, 255, 0), (0, 0, 0)]
        rn = Rc / 255.0; gn = Gc / 255.0; bn = Bc / 255.0
        kk_ = 1.0 - bright
        denom = np.clip(1.0 - kk_, 1e-6, 1.0)
        vmaps = [np.clip((1.0 - rn - kk_) / denom, 0, 1),
                 np.clip((1.0 - gn - kk_) / denom, 0, 1),
                 np.clip((1.0 - bn - kk_) / denom, 0, 1),
                 np.clip(kk_, 0, 1)]
        kinds = ['mul', 'mul', 'mul', 'mul']
    if extra:
        if extra_col == 'black':
            chans.append((0, 0, 0)); vmaps.append(np.clip(dark_amt, 0, 1)); kinds.append('over')
        else:
            chans.append((255, 255, 255)); vmaps.append(np.clip(white_amt, 0, 1)); kinds.append('over')
    nchan = len(chans)

    diag = _m.hypot(bw, bh) / 2.0
    while ((2 * (diag / cell)) * (2 * (diag / cell))) > 200000 and cell < diag:
        cell *= 1.4

    K = 20
    Rrot = 8 if randrot else 1
    maxd = max(2, int(round(cell * oscale * sizef)))

    pat_arrs = [_ht_pattern_stencil(b) for b in (getattr(effect, 'ht_patterns', []) or [])]

    def _chan_src(ci):
        valid = [p for p in pat_arrs if p is not None]
        if not valid:
            return shape, True
        if len(pat_arrs) == 1:
            return (pat_arrs[0], False)
        if ci < len(pat_arrs) and pat_arrs[ci] is not None:
            return pat_arrs[ci], False
        return shape, True

    bucket_cache = {}
    chan_buckets = []
    for ci in range(nchan):
        s, is_shape = _chan_src(ci)
        key = ('shape:' + s) if is_shape else id(s)
        if key not in bucket_cache:
            bucket_cache[key] = _ht_make_buckets(s, maxd, K, Rrot, is_shape)
        chan_buckets.append(bucket_cache[key])

    if mode == 'rgb':
        out = np.zeros((bh, bw, 3), np.float32)
    else:
        out = np.full((bh, bw, 3), 255.0, np.float32)

    screen_angles = [0.0, 120.0, 240.0, 0.0]
    cover = np.zeros((bh, bw), np.float32)
    srad = max(1, int(round(cell / 4.0)))   # v4.2.10.12: per-cell sampling radius
    vy = (_m.sqrt(3) / 2.0) * cell if hexgrid else cell
    cx0, cy0 = bw / 2.0, bh / 2.0
    n_rows = int(diag / vy) + 2
    n_cols = int(diag / cell) + 2
    # v4.2.11.50: GPU fast path covers ALL cases now -- custom patterns,
    # random dot rotation and decentralization included (per-call CPU fallback
    # stays, as always).
    _use_gpu_ht = False; _csa = None
    try:
        from edof.engine import gpu as _gpu
        if _gpu.is_enabled() and _gpu.gpu_available():
            _use_gpu_ht = True   # exact per-cell sampling needs no precompute
    except Exception:
        _use_gpu_ht = False
    for ci, tint in enumerate(chans):
        if not (enabled[ci] if ci < len(enabled) else True):
            continue
        rot = _m.radians(angle_step * ci)
        cos_r = _m.cos(rot); sin_r = _m.sin(rot)
        vmap = vmaps[ci]
        oa = _m.radians(screen_angles[ci % 4]); off = decent * (cell / 2.0)
        ox = off * _m.cos(oa); oy = off * _m.sin(oa)
        buckets = chan_buckets[ci]
        layer = None
        if _use_gpu_ht:
            try:
                layer = _ht_gpu_channel_layer(ci, vmap, buckets, cell, vy, hexgrid,
                            n_rows, n_cols, cos_r, sin_r, cx0, cy0, srad, K, maxd,
                            rmode, bw, bh, a_arr, _csa,
                            ox=ox, oy=oy, Rrot=Rrot)
            except Exception:
                layer = None
        if layer is None:
            layer = np.zeros((bh, bw), np.float32)
            for row in range(-n_rows, n_rows + 1):
                uy = row * vy
                xoff = (cell / 2.0) if (hexgrid and (row % 2 != 0)) else 0.0
                for col in range(-n_cols, n_cols + 1):
                    ux = col * cell + xoff
                    gx = ux * cos_r - uy * sin_r + cx0 + ox
                    gy = ux * sin_r + uy * cos_r + cy0 + oy
                    ix = int(gx); iy = int(gy)
                    if 0 <= ix < bw and 0 <= iy < bh:
                        # sample the channel value by AVERAGING over the cell
                        # (radius ~ cell/4), alpha-weighted, like the reference
                        # mosaic generator.
                        y0 = iy - srad if iy - srad > 0 else 0
                        y1 = iy + srad + 1 if iy + srad + 1 < bh else bh
                        x0 = ix - srad if ix - srad > 0 else 0
                        x1 = ix + srad + 1 if ix + srad + 1 < bw else bw
                        a_reg = a_arr[y0:y1, x0:x1]
                        asum = float(a_reg.sum())
                        if asum > 0.01:
                            v_reg = vmap[y0:y1, x0:x1]
                            val = float((v_reg * a_reg).sum() / asum)
                        else:
                            val = 0.0
                        if asum <= 0.01:
                            continue
                        if rmode == 'size':
                            scale = val; ad = 1.0
                        else:
                            scale = 1.0; ad = val
                        if scale > 0.02:
                            bk = min(K - 1, max(0, int(round(scale * (K - 1)))))
                            rr = _ht_rot_idx(col, row, ci, Rrot)
                            st = buckets[bk][rr]
                            _stamp_max(layer, st * ad if ad != 1.0 else st, gx, gy)
        kind = kinds[ci]
        if kind == 'add':
            out[..., 0] += layer * tint[0]
            out[..., 1] += layer * tint[1]
            out[..., 2] += layer * tint[2]
        elif kind == 'mul':
            out[..., 0] *= (1.0 - layer * (1.0 - tint[0] / 255.0))
            out[..., 1] *= (1.0 - layer * (1.0 - tint[1] / 255.0))
            out[..., 2] *= (1.0 - layer * (1.0 - tint[2] / 255.0))
        else:  # 'over' — paint solid tint (extra white/black key channel)
            out[..., 0] = out[..., 0] * (1.0 - layer) + tint[0] * layer
            out[..., 1] = out[..., 1] * (1.0 - layer) + tint[1] * layer
            out[..., 2] = out[..., 2] * (1.0 - layer) + tint[2] * layer
        np.maximum(cover, layer, out=cover)
    out = np.clip(out, 0, 255).astype('uint8')
    # background mode decides the alpha: 'native' fills the whole silhouette
    # (RGB on its black base / CMYK on its white base — self-contained, faithful
    # regardless of document background); 'transparent'/'layer' keep only the dot
    # coverage so gaps show through.
    bg = (getattr(effect, 'ht_background', '') or '').lower()
    if not bg:
        bg = 'layer' if getattr(effect, 'ht_keep_background', False) else 'native'
    base = a_arr.copy() if bg == 'native' else cover
    if clip == 'hard':
        base = base * (a_arr > 0.5)
    elif clip == 'soft':
        base = base * a_arr
    out_a = np.clip(base * (255.0 * op), 0, 255).astype('uint8')
    rgba = np.dstack([out, out_a])
    return Image.fromarray(rgba, 'RGBA')


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
        s = max(0.0, min(1.0, getattr(effect, 'spread', 0.0)))
        size_px = max(0, mm_to_px(effect.size, dpi))
        expand_px = int(round(size_px * s))
        blur_px = max(0, size_px * (1.0 - s))
        # Inner shadow: invert alpha, offset, blur, mask back by original alpha
        inv = ImageChops.invert(alpha)
        shifted = Image.new("L", (bw, bh), 0); shifted.paste(inv, (dx, dy))
        if expand_px > 0:
            shifted = _dilate_L(shifted, expand_px)
        if blur_px > 0:
            shifted = _blur_L(shifted, blur_px)
        masked = ImageChops.multiply(shifted, alpha)
        if op_alpha != 255:
            masked = masked.point(lambda v, oa=op_alpha: int(v * oa / 255))
        c = effect.color
        layer = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        layer.putalpha(masked)
        _composite_with_blend(canvas, layer, (px, py), effect.blend_mode)

    elif effect.type == 'inner_glow':
        s = max(0.0, min(1.0, getattr(effect, 'spread', 0.0)))
        size_px = max(1, mm_to_px(effect.size, dpi))
        expand_px = int(round(size_px * s))
        blur_px = max(0, size_px * (1.0 - s))
        inv = ImageChops.invert(alpha)
        if expand_px > 0:
            inv = _dilate_L(inv, expand_px)
        blurred = _blur_L(inv, blur_px)
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

    elif effect.type == 'bevel' and effect.bevel_kind != 'outer':
        _render_bevel_shaded(canvas, alpha, effect, dpi, px, py, bw, bh, outer=False)

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

    elif effect.type == 'chromatic_aberration':
        # v4.2.7.12: rich per-channel chromatic aberration.
        # Each channel (R/G/B) is tinted by its own colour and either shifted by
        # its own offset/angle (linear) or scaled about the centre by its own
        # distortion % (radial — lens-like). The three layers add together.
        from PIL import ImageOps
        r, g, b, a = obj_buf.split()
        mode = getattr(effect, 'ca_mode', 'linear')
        cx = bw / 2.0; cy = bh / 2.0
        specs = [
            (r, getattr(effect, 'ca_r_color', (255, 0, 0, 255)),
             getattr(effect, 'ca_r_offset', 0.5), getattr(effect, 'ca_r_angle', 0.0),
             getattr(effect, 'ca_r_distort', 2.0)),
            (g, getattr(effect, 'ca_g_color', (0, 255, 0, 255)),
             getattr(effect, 'ca_g_offset', 0.0), getattr(effect, 'ca_g_angle', 0.0),
             getattr(effect, 'ca_g_distort', 0.0)),
            (b, getattr(effect, 'ca_b_color', (0, 0, 255, 255)),
             getattr(effect, 'ca_b_offset', 0.5), getattr(effect, 'ca_b_angle', 180.0),
             getattr(effect, 'ca_b_distort', -2.0)),
        ]
        # v4.2.11.5: GPU fast path (per-pixel shift/scale + tint in one shader).
        # Builds the same per-channel transforms as the CPU code below; on any
        # miss it falls through to the CPU path so output is identical.
        ca_done = False
        try:
            from edof.engine import gpu as _gpu
            if _gpu.is_enabled():
                gspecs = []
                for ch, col, off, ang, dist in specs:
                    if mode == 'radial':
                        s = 1.0 + (dist / 100.0)
                        if s <= 0.01: s = 0.01
                        gspecs.append((col, (0.0, 0.0), s))
                    else:
                        offpx = mm_to_px(abs(off), dpi)
                        rad = math.radians(ang)
                        dx = int(round(offpx * math.cos(rad)))
                        dy = int(round(-offpx * math.sin(rad)))
                        gspecs.append((col, (dx, dy), 1.0))
                ca_img = _gpu.gpu_chromatic_aberration(obj_buf, mode, gspecs)
                if ca_img is not None:
                    _gpu.blur_gpu_count += 1
                    if op_alpha != 255:
                        caa = ca_img.split()[3].point(lambda v, oa=op_alpha: int(v * oa / 255))
                        ca_img.putalpha(caa)
                    _composite_with_blend(canvas, ca_img, (px, py), effect.blend_mode)
                    ca_done = True
                else:
                    _gpu.blur_cpu_count += 1
        except Exception:
            ca_done = False
        if ca_done:
            return
        acc_rgb = Image.new("RGB", (bw, bh), (0, 0, 0))
        acc_a = Image.new("L", (bw, bh), 0)
        for ch, col, off, ang, dist in specs:
            tint = ImageOps.colorize(ch, (0, 0, 0), (int(col[0]), int(col[1]), int(col[2])))
            layer = tint.convert("RGBA"); layer.putalpha(a)
            placed = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            if mode == 'radial':
                s = 1.0 + (dist / 100.0)
                if s <= 0.01:
                    s = 0.01
                nw = max(1, int(round(bw * s))); nh = max(1, int(round(bh * s)))
                scaled = layer.resize((nw, nh))
                placed.paste(scaled, (int(round(cx - nw / 2.0)), int(round(cy - nh / 2.0))))
            else:
                offpx = mm_to_px(abs(off), dpi)
                rad = math.radians(ang)
                dx = int(round(offpx * math.cos(rad)))
                dy = int(round(-offpx * math.sin(rad)))
                placed.paste(layer, (dx, dy))
            lr, lg, lb, la = placed.split()
            acc_rgb = ImageChops.add(acc_rgb, Image.merge("RGB", (lr, lg, lb)))
            acc_a = ImageChops.lighter(acc_a, la)
        ca_img = acc_rgb.convert("RGBA"); ca_img.putalpha(acc_a)
        if op_alpha != 255:
            caa = ca_img.split()[3].point(lambda v, oa=op_alpha: int(v * oa / 255))
            ca_img.putalpha(caa)
        _composite_with_blend(canvas, ca_img, (px, py), effect.blend_mode)

    elif effect.type == 'halftone':
        # v4.2.7.18: per-channel shaped-dot halftone (RGB additive / CMYK
        # multiply), on rotated screens — the 'Maori mosaic' style.
        ht = _render_halftone_mosaic(obj_buf, alpha, effect, dpi, bw, bh)
        _composite_with_blend(canvas, ht, (px, py), effect.blend_mode)

    elif effect.type == 'light_sweep':
        # v4.2.7: glossy diagonal specular streak across the object.
        import numpy as np
        ang = math.radians(getattr(effect, 'lsw_angle', 45.0))
        ca_, sa_ = math.cos(ang), math.sin(ang)
        yy, xx = np.mgrid[0:bh, 0:bw].astype(np.float32)
        u = xx * ca_ + yy * sa_
        umin, umax = float(u.min()), float(u.max())
        un = (u - umin) / max(1.0, (umax - umin))
        pos = float(getattr(effect, 'lsw_pos', 0.5))
        width = max(0.01, float(getattr(effect, 'lsw_width', 0.3)))
        band = np.exp(-(((un - pos) / (width / 2.0)) ** 2))
        a_arr = np.asarray(alpha, dtype=np.float32) / 255.0
        out_a = (band * a_arr * (op_alpha / 255.0) * 255.0).astype('uint8')
        c = getattr(effect, 'color2', (255, 255, 255, 255))
        sweep = Image.new("RGBA", (bw, bh), (c[0], c[1], c[2], 0))
        sweep.putalpha(Image.fromarray(out_a, "L"))
        bm = effect.blend_mode if (effect.blend_mode and effect.blend_mode != 'normal') else 'screen'
        _composite_with_blend(canvas, sweep, (px, py), bm)


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

def _stroke_polyline(draw, poly, color, width):
    """v4.2.10.8: draw a thick polyline without cracks. PIL's line() renders
    each segment as a separate rectangle; without rounded joints a wide stroke
    over a flattened bezier shows gaps at every vertex. joint='curve' rounds the
    interior joints; round caps (small filled circles) close the two ends so a
    wide open stroke has clean, gap-free terminals."""
    if not poly or len(poly) < 2:
        return
    draw.line(poly, fill=color, width=width, joint='curve')
    if width >= 3:
        r = width / 2.0
        for (px, py) in (poly[0], poly[-1]):
            draw.ellipse([px - r, py - r, px + r, py + r], fill=color)


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


def _effective_corner_radii(obj, w, h, dpi):
    """Return ([tl,tr,br,bl] in px, all_equal). Empty corner_radii -> uniform."""
    rr = getattr(obj, 'corner_radii', None)
    if rr and len(rr) == 4:
        radii = [max(0.0, mm_to_px(float(x), dpi)) for x in rr]
    else:
        r = max(0.0, mm_to_px(float(getattr(obj, 'corner_radius', 0.0)), dpi))
        radii = [r, r, r, r]
    tl, tr, br, bl = radii

    def _sc(a, b, length):
        s = a + b
        if s > length and s > 0:
            f = length / s
            return a * f, b * f
        return a, b
    tl_t, tr_t = _sc(tl, tr, w)        # top edge
    bl_b, br_b = _sc(bl, br, w)        # bottom edge
    tl_l, bl_l = _sc(tl, bl, h)        # left edge
    tr_r, br_r = _sc(tr, br, h)        # right edge
    radii = [min(tl_t, tl_l), min(tr_t, tr_r), min(br_b, br_r), min(bl_b, bl_l)]
    all_equal = (max(radii) - min(radii)) < 0.01
    return radii, all_equal


def _rounded_corner_points(w, h, radii, samples=14, inset=0.0):
    """Closed polygon outline of a rectangle with per-corner radii [tl,tr,br,bl].

    `inset` shrinks the path inward on every side (used to keep a centered stroke
    of width 2*inset fully inside the object bounds instead of being clipped)."""
    tl, tr, br, bl = [max(0.0, r - inset) for r in radii]
    x0, y0, x1, y1 = inset, inset, w - inset, h - inset
    pts = []

    def arc(cx, cy, r, a0, a1):
        if r <= 0:
            pts.append((cx, cy)); return
        for i in range(samples + 1):
            a = math.radians(a0 + (a1 - a0) * i / samples)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    arc(x0 + tl, y0 + tl, tl, 180, 270)        # top-left
    arc(x1 - tr, y0 + tr, tr, 270, 360)        # top-right
    arc(x1 - br, y1 - br, br, 0, 90)           # bottom-right
    arc(x0 + bl, y1 - bl, bl, 90, 180)         # bottom-left
    return [(int(round(x)), int(round(y))) for x, y in pts]


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
        # v4.2.10.8: pad the buffer by half the stroke width (+ a small margin)
        # on every side. The path bbox (w_px/h_px) covers the centreline only;
        # a wide stroke is centred on the path edge and extends sw/2 beyond it,
        # so without padding the buffer edge clipped the stroke. Polys are
        # offset by PAD and the buffer is pasted back at -PAD.
        PAD = int(_math.ceil(sw / 2.0)) + 2
        buf_w = max(1, int(_math.ceil(w_px)) + 1 + 2 * PAD)
        buf_h = max(1, int(_math.ceil(h_px)) + 1 + 2 * PAD)
        buf = Image.new("RGBA", (buf_w, buf_h), (0,0,0,0))
        _pad_mm = PAD / mm_to_px(1.0, dpi)
        polys = _path_to_polygons(obj.path_data, dpi, _pad_mm, _pad_mm)
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
                _stroke_polyline(bd, poly, sc[:4], sw)
        else:
            for poly in polys:
                if len(poly) < 2: continue
                if fc and len(poly) >= 3: bd.polygon(poly, fill=fc[:4])
                _stroke_polyline(bd, poly, sc[:4], sw)
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
            _px = int(mm_to_px(t.x, dpi)) - PAD
            _py = int(mm_to_px(t.y, dpi)) - PAD
            # alpha_composite needs non-negative dest; crop the buffer if the
            # padded origin lands off the top/left edge of the canvas.
            _cropx = -_px if _px < 0 else 0
            _cropy = -_py if _py < 0 else 0
            if _cropx or _cropy:
                buf = buf.crop((_cropx, _cropy, buf.width, buf.height))
            canvas.alpha_composite(buf, (max(0, _px), max(0, _py)))
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
            radii, eq = _effective_corner_radii(obj, w_px, h_px, dpi)
            if eq:
                r = int(radii[0])
                if r > 0: md.rounded_rectangle([0,0,w_px,h_px], radius=r, fill=255)
                else:     md.rectangle([0,0,w_px,h_px], fill=255)
            else:
                md.polygon(_rounded_corner_points(w_px, h_px, radii), fill=255)
        elif st == SHAPE_ELLIPSE:
            md.ellipse([0,0,w_px,h_px], fill=255)
        else:
            md.rectangle([0,0,w_px,h_px], fill=255)
        gimg.putalpha(mask)
        tmp.alpha_composite(gimg)
        if st == SHAPE_RECT:
            radii, eq = _effective_corner_radii(obj, w_px, h_px, dpi)
            if eq:
                r = int(radii[0])
                if r > 0: td.rounded_rectangle([0,0,w_px,h_px], radius=r, outline=sc[:4], width=sw)
                else:     td.rectangle([0,0,w_px,h_px], outline=sc[:4], width=sw)
            else:
                p = _rounded_corner_points(w_px, h_px, radii, inset=sw/2.0)
                td.line(p + [p[0]], fill=sc[:4], width=sw, joint='curve')
        elif st == SHAPE_ELLIPSE:
            td.ellipse([0,0,w_px,h_px], outline=sc[:4], width=sw)
    else:
        if st == SHAPE_RECT:
            radii, eq = _effective_corner_radii(obj, w_px, h_px, dpi)
            if eq:
                r = int(radii[0])
                if r > 0: td.rounded_rectangle([0,0,w_px,h_px], radius=r, fill=fc[:4] if fc else None, outline=sc[:4], width=sw)
                else:     td.rectangle([0,0,w_px,h_px], fill=fc[:4] if fc else None, outline=sc[:4], width=sw)
            else:
                pf = _rounded_corner_points(w_px, h_px, radii)
                if fc: td.polygon(pf, fill=fc[:4])
                if sc and sw > 0:
                    ps = _rounded_corner_points(w_px, h_px, radii, inset=sw/2.0)
                    td.line(ps + [ps[0]], fill=sc[:4], width=sw, joint='curve')
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
