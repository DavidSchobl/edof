# edof/engine/text_engine.py
"""
Text layout engine.
KEY FIX: find_fitting_size now receives dpi and correctly converts pt → px.
"""
from __future__ import annotations
import io, os, platform
from typing import Optional, Tuple
from PIL import ImageDraw, ImageFont
from edof.engine.transform import mm_to_px
from edof.format.styles import TextStyle

# ── Font discovery ─────────────────────────────────────────────────────────────

def _font_dirs() -> list:
    s = platform.system()
    if s == "Windows":
        return [r"C:\Windows\Fonts",
                os.path.join(os.environ.get("LOCALAPPDATA",""), r"Microsoft\Windows\Fonts")]
    if s == "Darwin":
        return ["/Library/Fonts","/System/Library/Fonts",
                os.path.expanduser("~/Library/Fonts")]
    return ["/usr/share/fonts","/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts")]

_FONT_DB: Optional[dict] = None

def _scan_fonts() -> dict:
    result: dict = {}
    for d in _font_dirs():
        if not os.path.isdir(d): continue
        for root, _, files in os.walk(d):
            for fname in files:
                if not fname.lower().endswith(('.ttf','.otf')): continue
                path = os.path.join(root, fname)
                try:
                    f = ImageFont.truetype(path, 10)
                    family, style = f.getname()
                    family = family.strip()
                except Exception: continue
                key = family.lower()
                if key not in result:
                    result[key] = {'_display': family}
                sl = style.lower()
                if 'bold' in sl and ('italic' in sl or 'oblique' in sl):
                    result[key]['bolditalic'] = path
                elif 'bold' in sl:
                    result[key]['bold'] = path
                elif 'italic' in sl or 'oblique' in sl:
                    result[key]['italic'] = path
                else:
                    result[key].setdefault('regular', path)
    return result

def _get_db() -> dict:
    global _FONT_DB
    if _FONT_DB is None: _FONT_DB = _scan_fonts()
    return _FONT_DB

def invalidate_font_cache():
    global _FONT_DB, _FONT_CACHE
    _FONT_DB = None; _FONT_CACHE.clear()

def list_system_fonts() -> list:
    return sorted(v.get('_display', k) for k,v in _get_db().items())

def get_font_path(family: str, bold: bool=False, italic: bool=False) -> Optional[str]:
    db = _get_db(); key = family.lower()
    entry = db.get(key)
    if not entry:
        for k,v in db.items():
            if key in k or k in key: entry=v; break
    if not entry: return None
    if bold and italic:
        return entry.get('bolditalic') or entry.get('bold') or entry.get('italic') or entry.get('regular')
    if bold:   return entry.get('bold') or entry.get('bolditalic') or entry.get('regular')
    if italic: return entry.get('italic') or entry.get('bolditalic') or entry.get('regular')
    return entry.get('regular') or next((v for k,v in entry.items() if k!='_display'), None)

# ── Font loading ───────────────────────────────────────────────────────────────

_FONT_CACHE: dict = {}

def load_font(family: str, bold: bool, italic: bool, size_px: int,
              font_data: Optional[bytes]=None) -> Optional[ImageFont.FreeTypeFont]:
    ckey = (family, bold, italic, size_px, hash(font_data) if font_data else None)
    if ckey in _FONT_CACHE: return _FONT_CACHE[ckey]
    font = None
    if font_data:
        try: font = ImageFont.truetype(io.BytesIO(font_data), size=size_px)
        except Exception: pass
    if font is None:
        path = get_font_path(family, bold, italic)
        if path:
            try: font = ImageFont.truetype(path, size=size_px)
            except Exception: pass
    if font is None:
        try: font = ImageFont.truetype(family, size=size_px)
        except Exception: pass
    if font is not None: _FONT_CACHE[ckey] = font
    return font

def load_font_safe(family, bold, italic, size_px, font_data=None):
    f = load_font(family, bold, italic, size_px, font_data)
    return f if f is not None else ImageFont.load_default()

# ── Measurement ───────────────────────────────────────────────────────────────

def _lh(font, mult: float) -> int:
    try: asc, desc = font.getmetrics(); h = asc + abs(desc)
    except Exception:
        try: h = font.size
        except Exception: h = 12
    return max(1, int(h * mult))

def _lw(font, text: str) -> int:
    if not text: return 0
    try: bb = font.getbbox(text); return max(0, bb[2]-bb[0])
    except Exception: pass
    try: return int(font.getlength(text))
    except Exception: return len(text)*7

def wrap_lines(text: str, font, max_w: Optional[int]) -> list:
    raw = text.replace('\r\n','\n').replace('\r','\n').split('\n')
    if max_w is None: return raw
    out = []
    for line in raw:
        if not line: out.append(''); continue
        words, cur = line.split(' '), ''
        for word in words:
            test = (cur+' '+word).strip()
            if _lw(font, test) <= max_w: cur = test
            else:
                if cur: out.append(cur)
                while word and _lw(font, word) > max_w:
                    for i in range(len(word), 0, -1):
                        if _lw(font, word[:i]) <= max_w:
                            out.append(word[:i]); word=word[i:]; break
                    else: out.append(word); word=''; break
                cur = word
        if cur: out.append(cur)
    return out

def _fits(text: str, font, max_w: int, max_h: int, lh_mult: float, wrap: bool) -> bool:
    lines = wrap_lines(text, font, max_w if wrap else None)
    lh    = _lh(font, lh_mult)
    w     = max((_lw(font, l) for l in lines), default=0)
    h     = lh * len(lines)
    return w <= max_w and h <= max_h

# ── Auto-shrink / Auto-fill ────────────────────────────────────────────────────

def find_fitting_size(text: str,
                      max_w_px: int, max_h_px: int,
                      style: TextStyle,
                      dpi: float = 96,           # ← REQUIRED for correct pt→px
                      font_data: Optional[bytes] = None,
                      wrap: bool = True,
                      shrink_only: bool = True) -> float:
    """
    Binary-search for the best font size in pt.

    shrink_only=True  (auto_shrink):  upper bound = style.font_size (never enlarges)
    shrink_only=False (auto_fill):    upper bound = style.max_font_size (fills box)

    KEY FIX: font is loaded at  int(pt * dpi / 72)  pixels so measurement
             is consistent with the actual render output.
    """
    if not text:
        return style.font_size

    def _pt_to_px(pt: float) -> int:
        return max(1, int(pt * dpi / 72.0))

    # Verify a FreeType font is available
    if load_font(style.font_family, style.bold, style.italic,
                 _pt_to_px(12), font_data) is None:
        return style.font_size

    lo = max(1.0, style.min_font_size)
    hi = style.font_size if shrink_only else style.max_font_size

    # For auto_shrink: if text already fits at current size, return unchanged
    if shrink_only:
        probe = load_font(style.font_family, style.bold, style.italic,
                          _pt_to_px(hi), font_data)
        if probe and _fits(text, probe, max_w_px, max_h_px, style.line_height, wrap):
            return hi

    best = lo
    for _ in range(28):                  # 28 iterations → <0.001pt accuracy
        mid   = (lo + hi) / 2.0
        sz_px = _pt_to_px(mid)           # ← correct pt→px conversion
        f     = load_font(style.font_family, style.bold, style.italic,
                          sz_px, font_data)
        if f is None: break
        if _fits(text, f, max_w_px, max_h_px, style.line_height, wrap):
            best = mid; lo = mid
        else:
            hi   = mid
        if hi - lo < 0.02: break

    return best

# ── Rendering ─────────────────────────────────────────────────────────────────

def render_text_onto(draw, text: str, style: TextStyle,
                     x_px: float, y_px: float, w_px: float, h_px: float,
                     dpi: float, font_data: Optional[bytes] = None) -> None:
    if not text: return
    pad = mm_to_px(2.0, dpi)
    ix = x_px+pad; iy = y_px+pad
    iw = max(1.0, w_px-2*pad); ih = max(1.0, h_px-2*pad)

    if style.auto_fill:
        fs_pt = find_fitting_size(text, int(iw), int(ih), style,
                                   dpi=dpi, font_data=font_data,
                                   wrap=style.wrap, shrink_only=False)
    elif style.auto_shrink:
        fs_pt = find_fitting_size(text, int(iw), int(ih), style,
                                   dpi=dpi, font_data=font_data,
                                   wrap=style.wrap, shrink_only=True)
    else:
        fs_pt = style.font_size

    sz_px = max(1, int(fs_pt * dpi / 72.0))
    font  = load_font_safe(style.font_family, style.bold, style.italic,
                            sz_px, font_data)
    lines = wrap_lines(text, font, int(iw) if style.wrap else None)
    lh    = _lh(font, style.line_height)
    total = lh * len(lines)

    if   style.vertical_align == 'middle': ty = iy + (ih-total)/2.0
    elif style.vertical_align == 'bottom': ty = iy + ih - total
    else:                                  ty = iy

    fill = tuple(style.color[:3])
    sw   = max(1, sz_px // 14)
    for line in lines:
        lw = _lw(font, line)
        if   style.alignment == 'center': lx = ix + (iw-lw)/2.0
        elif style.alignment == 'right':  lx = ix + iw - lw
        else:                             lx = ix
        if style.overflow_hidden and ty + lh > y_px + h_px + 1: break
        draw.text((lx, ty), line, font=font, fill=fill)
        if style.underline:
            draw.line([(lx,int(ty+lh*0.9)),(lx+lw,int(ty+lh*0.9))], fill=fill, width=sw)
        if style.strikethrough:
            draw.line([(lx,int(ty+lh*0.55)),(lx+lw,int(ty+lh*0.55))], fill=fill, width=sw)
        ty += lh
