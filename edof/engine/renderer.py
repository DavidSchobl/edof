# edof/engine/renderer.py
"""
Page renderer.
Fixes:
  • QR: always renders in B&W then colorizes → all fg/bg colors work correctly
  • ImageBox: honours variable binding → variable value can be a file path
  • RGBA color tuples supported everywhere
"""
from __future__ import annotations
import io, os, math
from typing import Optional, TYPE_CHECKING
from PIL import Image, ImageDraw, ImageOps
from edof.engine.color import convert_image
from edof.engine.transform import mm_to_px, rotate_point
from edof.engine.text_engine import render_text_onto
from edof.format.objects import (EdofObject, TextBox, ImageBox, Shape,
                                  QRCode, Group,
                                  SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE,
                                  SHAPE_POLYGON, SHAPE_ARROW)
if TYPE_CHECKING:
    from edof.format.document import Document, Page, ResourceStore
    from edof.format.variables import VariableStore


def _rgba(c, default=(0, 0, 0, 255)) -> tuple:
    if c is None: return None
    t = tuple(int(v) for v in c)
    return (*t, 255) if len(t) == 3 else t[:4]


def render_page(page, resources, variables,
                dpi=None, color_space=None, bit_depth=None) -> Image.Image:
    dpi_r = dpi or page.dpi
    cs_r  = color_space or page.color_space
    bd_r  = bit_depth  or page.bit_depth
    w_px  = max(1, int(mm_to_px(page.width,  dpi_r)))
    h_px  = max(1, int(mm_to_px(page.height, dpi_r)))
    bg    = _rgba(page.background, (255, 255, 255, 255))
    canvas = Image.new("RGBA", (w_px, h_px), bg[:4])
    for obj in page.sorted_objects():
        if obj.visible:
            _render_object(obj, canvas, resources, variables, dpi_r)
    result = convert_image(canvas, cs_r, bd_r)
    result.info["dpi"] = (dpi_r, dpi_r)
    return result


def render_document(doc, dpi=None, color_space=None, bit_depth=None):
    return [render_page(p, doc.resources, doc.variables, dpi, color_space, bit_depth)
            for p in doc.pages]


def _render_object(obj, canvas, resources, variables, dpi):
    if   isinstance(obj, TextBox):  _render_textbox(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, ImageBox): _render_imagebox(obj, canvas, resources, variables, dpi)
    elif isinstance(obj, Shape):    _render_shape(obj, canvas, dpi)
    elif isinstance(obj, QRCode):   _render_qrcode(obj, canvas, variables, dpi)
    elif isinstance(obj, Group):
        for child in obj.flatten():
            if child.visible:
                _render_object(child, canvas, resources, variables, dpi)


# ── TextBox ───────────────────────────────────────────────────────────────────

def _render_textbox(obj, canvas, resources, variables, dpi):
    t = obj.transform
    x_px = mm_to_px(t.x, dpi); y_px = mm_to_px(t.y, dpi)
    w_px = mm_to_px(t.width, dpi); h_px = mm_to_px(t.height, dpi)
    if w_px < 1 or h_px < 1: return

    font_data: Optional[bytes] = None
    if resources:
        for entry in resources.all_entries():
            if (entry.mime_type in ("font/ttf","font/otf",
                                    "application/x-font-ttf","application/x-font-opentype")
                    and obj.style.font_family.lower() in entry.filename.lower()):
                font_data = entry.data; break

    text = obj.get_resolved_text(variables)
    tmp  = Image.new("RGBA", (max(1,int(w_px)), max(1,int(h_px))), (0,0,0,0))
    td   = ImageDraw.Draw(tmp, "RGBA")

    if obj.fill.color:
        fd = _rgba(obj.fill.color)
        td.rectangle([0,0,w_px,h_px], fill=(*fd[:3], int(obj.fill.opacity*fd[3])))

    if obj.border:
        bw = max(1, int(mm_to_px(obj.border.width/72*25.4, dpi)))
        td.rectangle([0,0,int(w_px)-1,int(h_px)-1],
                     outline=_rgba(obj.border.color)[:4], width=bw)

    render_text_onto(td, text, obj.style, 0, 0, w_px, h_px, dpi, font_data)

    if obj.opacity < 1.0:
        r,g,b,a = tmp.split()
        a = a.point(lambda v: int(v*obj.opacity))
        tmp = Image.merge("RGBA",(r,g,b,a))
    if t.flip_h: tmp = tmp.transpose(Image.FLIP_LEFT_RIGHT)
    if t.flip_v: tmp = tmp.transpose(Image.FLIP_TOP_BOTTOM)
    if t.rotation % 360 != 0:
        tmp = tmp.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
        px = int(x_px+w_px/2-tmp.width/2); py = int(y_px+h_px/2-tmp.height/2)
    else:
        px, py = int(x_px), int(y_px)
    canvas.alpha_composite(tmp, (max(0,px), max(0,py)))


# ── ImageBox ──────────────────────────────────────────────────────────────────

def _render_imagebox(obj, canvas, resources, variables, dpi):
    # Support variable binding for image path
    src: Optional[Image.Image] = None

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

    t    = obj.transform
    x_px = int(mm_to_px(t.x,      dpi)); y_px = int(mm_to_px(t.y,     dpi))
    w_px = int(mm_to_px(t.width,  dpi)); h_px = int(mm_to_px(t.height, dpi))

    src = _apply_fit(src, w_px, h_px, obj.fit_mode)
    if t.flip_h: src = src.transpose(Image.FLIP_LEFT_RIGHT)
    if t.flip_v: src = src.transpose(Image.FLIP_TOP_BOTTOM)
    if t.rotation % 360 != 0:
        src = src.rotate(-t.rotation, expand=True, resample=Image.BICUBIC)
        x_px = int(x_px+w_px/2-src.width/2); y_px = int(y_px+h_px/2-src.height/2)
    if obj.opacity < 1.0:
        r,g,b,a = src.split()
        a = a.point(lambda v: int(v*obj.opacity))
        src = Image.merge("RGBA",(r,g,b,a))
    canvas.alpha_composite(src, (max(0,x_px), max(0,y_px)))


def _apply_fit(src, w, h, mode):
    sw, sh = src.size
    if mode == "stretch": return src.resize((w,h), Image.LANCZOS)
    if mode in ("fill","cover"):
        ratio=max(w/sw,h/sh); nw,nh=int(sw*ratio),int(sh*ratio)
        src=src.resize((nw,nh),Image.LANCZOS); l,t=(nw-w)//2,(nh-h)//2
        return src.crop((l,t,l+w,t+h))
    if mode == "contain":
        ratio=min(w/sw,h/sh); nw,nh=max(1,int(sw*ratio)),max(1,int(sh*ratio))
        res=src.resize((nw,nh),Image.LANCZOS)
        bg=Image.new("RGBA",(w,h),(0,0,0,0)); bg.paste(res,((w-nw)//2,(h-nh)//2),res)
        return bg
    bg=Image.new("RGBA",(w,h),(0,0,0,0)); bg.paste(src,(0,0),src); return bg


# ── Shape ─────────────────────────────────────────────────────────────────────

def _render_shape(obj, canvas, dpi):
    t    = obj.transform
    x0   = mm_to_px(t.x,       dpi); y0  = mm_to_px(t.y,       dpi)
    w_px = mm_to_px(t.width,   dpi); h_px= mm_to_px(t.height,  dpi)
    st   = obj.shape_type

    # Line with explicit points (absolute page mm coords)
    if st == SHAPE_LINE and obj.points and len(obj.points) >= 2:
        sc = _rgba(obj.stroke.color, (0,0,0,255))
        sw = max(1, int(mm_to_px(obj.stroke.width/72*25.4, dpi)))
        p1, p2 = obj.points[0], obj.points[1]
        cd = ImageDraw.Draw(canvas, "RGBA")
        cd.line([(mm_to_px(p1[0],dpi), mm_to_px(p1[1],dpi)),
                 (mm_to_px(p2[0],dpi), mm_to_px(p2[1],dpi))],
                fill=sc[:4], width=sw)
        return

    tmp = Image.new("RGBA",(max(1,int(w_px)),max(1,int(h_px))),(0,0,0,0))
    td  = ImageDraw.Draw(tmp,"RGBA")
    fc  = _rgba(obj.fill.color)
    sc  = _rgba(obj.stroke.color, (0,0,0,255))
    sw  = max(1, int(mm_to_px(obj.stroke.width/72*25.4, dpi)))

    if st == SHAPE_RECT:
        r = int(mm_to_px(obj.corner_radius, dpi))
        if r>0: td.rounded_rectangle([0,0,w_px,h_px],radius=r,fill=fc[:4] if fc else None,outline=sc[:4],width=sw)
        else:   td.rectangle([0,0,w_px,h_px],fill=fc[:4] if fc else None,outline=sc[:4],width=sw)
    elif st == SHAPE_ELLIPSE:
        td.ellipse([0,0,w_px,h_px],fill=fc[:4] if fc else None,outline=sc[:4],width=sw)
    elif st == SHAPE_LINE:
        td.line([0,0,w_px,h_px],fill=sc[:4] if sc else (0,0,0,255),width=sw)
    elif st in (SHAPE_POLYGON, SHAPE_ARROW):
        if obj.points:
            pts=[(mm_to_px(px,dpi),mm_to_px(py,dpi)) for px,py in obj.points]
            td.polygon(pts,fill=fc[:4] if fc else None,outline=sc[:4])

    if t.rotation%360!=0:
        tmp=tmp.rotate(-t.rotation,expand=True,resample=Image.BICUBIC)
    if obj.opacity<1.0:
        r2,g2,b2,a2=tmp.split(); a2=a2.point(lambda v:int(v*obj.opacity))
        tmp=Image.merge("RGBA",(r2,g2,b2,a2))
    px=int(x0+w_px/2-tmp.width/2) if t.rotation%360!=0 else int(x0)
    py=int(y0+h_px/2-tmp.height/2) if t.rotation%360!=0 else int(y0)
    canvas.alpha_composite(tmp,(max(0,px),max(0,py)))


# ── QR Code ───────────────────────────────────────────────────────────────────

def _render_qrcode(obj, canvas, variables, dpi):
    try: import qrcode as qrlib
    except ImportError:
        from edof.exceptions import warn_missing
        warn_missing("QR code","qr"); return

    data = obj.get_resolved_data(variables)
    if not data: return

    ec_map={"L":qrlib.constants.ERROR_CORRECT_L,"M":qrlib.constants.ERROR_CORRECT_M,
             "Q":qrlib.constants.ERROR_CORRECT_Q,"H":qrlib.constants.ERROR_CORRECT_H}
    qr=qrlib.QRCode(error_correction=ec_map.get(obj.error_correction,
                    qrlib.constants.ERROR_CORRECT_M), border=obj.border_modules)
    qr.add_data(data); qr.make(fit=True)

    # Always render B&W first, then colorize manually
    # This correctly handles any fg/bg color (including non-black)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    fg = tuple(int(v) for v in obj.fg_color)
    bg = tuple(int(v) for v in obj.bg_color)
    fg_r,fg_g,fg_b = fg[:3]; fg_a = fg[3] if len(fg)==4 else 255
    bg_r,bg_g,bg_b = bg[:3]; bg_a = bg[3] if len(bg)==4 else 255

    pixels = qr_img.load()
    w, h   = qr_img.size
    for x in range(w):
        for y in range(h):
            r,g,b,_ = pixels[x,y]
            if r < 128:   # dark pixel = QR module = foreground
                pixels[x,y] = (fg_r, fg_g, fg_b, fg_a)
            else:         # light pixel = background
                pixels[x,y] = (bg_r, bg_g, bg_b, bg_a)

    t    = obj.transform
    x_px = int(mm_to_px(t.x,      dpi)); y_px = int(mm_to_px(t.y,      dpi))
    w_px = int(mm_to_px(t.width,  dpi)); h_px = int(mm_to_px(t.height, dpi))
    size = min(w_px, h_px)
    qr_img = qr_img.resize((size,size), Image.NEAREST)

    if t.rotation%360!=0:
        qr_img=qr_img.rotate(-t.rotation,expand=True)
        x_px=int(x_px+w_px/2-qr_img.width/2); y_px=int(y_px+h_px/2-qr_img.height/2)
    canvas.alpha_composite(qr_img,(max(0,x_px),max(0,y_px)))
