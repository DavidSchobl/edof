# edof/engine/text_engine.py
"""
Text layout engine.

v3.1.0:
  • Item 1: padding reads style.padding mm (default 1 mm, was hardcoded 2 mm)
  • Item 2: load_font_safe falls back to DejaVu/Liberation, emits EdofMissingFontWarning
  • Item 3: cross-platform font aliases (Arial→Liberation Sans, Helvetica→FreeSans …)
  • measure_text_height() helper for auto-height textbox (item 6)
"""
from __future__ import annotations
import io, os, platform, warnings
from typing import Optional
from PIL import ImageFont
from edof.engine.transform import mm_to_px
from edof.format.styles import TextStyle

# v4.3.6.1: when on, runs that are batch variables (var_name set) are drawn with
# a tinted background + dotted underline so you can see which spans are variable.
# A view-only aid toggled from the canvas; off for normal rendering and export.
_SHOW_VARIABLES = False


def set_show_variables(on: bool) -> None:
    global _SHOW_VARIABLES
    _SHOW_VARIABLES = bool(on)


def show_variables() -> bool:
    return _SHOW_VARIABLES


# v4.3.6.28: rids to highlight regardless of the Show Variables toggle. Set by
# the UI when a batch table column or a panel variable is focused, so the page
# render (and the batch preview) marks the exact span that value drives.
_FOCUS_VAR_RIDS = None


def set_focus_var_rids(rids) -> None:
    global _FOCUS_VAR_RIDS
    _FOCUS_VAR_RIDS = set(rids) if rids else None


def focus_var_rids():
    return _FOCUS_VAR_RIDS


# v4.4.0: when on, runs that are LINK TARGETS (anchor set) are marked with a
# translucent red -> blue gradient under the span. View-only aid, default OFF,
# toggled from the View menu; exports suppress it like the variable rainbow.
_SHOW_ANCHORS = False


def set_show_anchors(on: bool) -> None:
    global _SHOW_ANCHORS
    _SHOW_ANCHORS = bool(on)


def show_anchors() -> bool:
    return _SHOW_ANCHORS


def _draw_anchor_gradient(draw, x0, y0, x1, y1, alpha=70):
    """Translucent horizontal red -> blue gradient under an anchor span."""
    w = max(1, int(x1 - x0))
    for i in range(w):
        t = i / max(1, w - 1)
        r = int(220 * (1 - t) + 40 * t)
        b = int(40 * (1 - t) + 220 * t)
        draw.line([(x0 + i, y0), (x0 + i, y1)], fill=(r, 30, b, alpha))


class suppress_view_marks:
    """v4.4.0: context manager that turns OFF the view-only text marks (the
    variable rainbow + the focus highlight) for the duration of an EXPORT and
    restores them after. Exports must never bake editor aids into output."""

    def __enter__(self):
        global _SHOW_VARIABLES, _FOCUS_VAR_RIDS, _SHOW_ANCHORS
        self._sv = _SHOW_VARIABLES
        self._fv = _FOCUS_VAR_RIDS
        self._sa = _SHOW_ANCHORS
        _SHOW_VARIABLES = False
        _FOCUS_VAR_RIDS = None
        _SHOW_ANCHORS = False
        return self

    def __exit__(self, *exc):
        global _SHOW_VARIABLES, _FOCUS_VAR_RIDS, _SHOW_ANCHORS
        _SHOW_VARIABLES = self._sv
        _FOCUS_VAR_RIDS = self._fv
        _SHOW_ANCHORS = self._sa
        return False


# v4.3.6.4: variable-text marker is a rainbow gradient drawn UNDER the span, a
# full hue sweep every `grain_mm` (default 3.5mm). The hue is keyed to absolute
# x so the band flows continuously across glyphs (and across runs on a line).
import colorsys as _colorsys


def _draw_var_rainbow(draw, x0, y0, x1, y1, dpi, grain_mm=8.0, alpha=64):
    """Fill [x0,y0,x1,y1] with a DIAGONAL rainbow, one full hue cycle per
    grain_mm (default 8mm), at ~25% opacity. Hue is keyed to (x+y) so the bands
    run at 45 degrees and line up continuously across adjacent spans."""
    period = max(2.0, mm_to_px(grain_mm, dpi))
    x0i, y0i = int(x0), int(y0)
    x1i, y1i = int(round(x1)), int(round(y1))
    if x1i <= x0i or y1i <= y0i:
        return
    step = max(1, int(period / 24))     # ~24 diagonal bands per full rainbow
    d = x0i + y0i
    d_max = x1i + y1i
    while d < d_max:
        hue = ((d / period) % 1.0)
        r, g, b = _colorsys.hsv_to_rgb(hue, 0.85, 1.0)
        col = (int(r * 255), int(g * 255), int(b * 255), alpha)
        # iso-hue line x+y=d, clipped to the rectangle
        xa = max(x0i, d - y1i)
        xb = min(x1i, d - y0i)
        if xa <= xb:
            draw.line([(xa, d - xa), (xb, d - xb)], fill=col, width=step + 1)
        d += step

# ── Cross-platform aliases ────────────────────────────────────────────────────
_FONT_ALIASES: dict[str, list[str]] = {
    "arial":           ["Liberation Sans", "FreeSans", "DejaVu Sans"],
    "helvetica":       ["Liberation Sans", "FreeSans", "DejaVu Sans"],
    "helvetica neue":  ["Liberation Sans", "FreeSans", "DejaVu Sans"],
    "times new roman": ["Liberation Serif", "FreeSerif", "DejaVu Serif"],
    "times":           ["Liberation Serif", "FreeSerif", "DejaVu Serif"],
    "courier new":     ["Liberation Mono", "FreeMono", "DejaVu Sans Mono"],
    "courier":         ["Liberation Mono", "FreeMono", "DejaVu Sans Mono"],
    "georgia":         ["DejaVu Serif", "FreeSerif", "Liberation Serif"],
    "verdana":         ["DejaVu Sans", "Liberation Sans", "FreeSans"],
    "tahoma":          ["DejaVu Sans", "Liberation Sans", "FreeSans"],
    "trebuchet ms":    ["DejaVu Sans", "Liberation Sans"],
    "calibri":         ["Carlito", "Liberation Sans", "DejaVu Sans"],
    "cambria":         ["Caladea", "DejaVu Serif", "Liberation Serif"],
    "segoe ui":        ["DejaVu Sans", "Liberation Sans", "FreeSans"],
    "comic sans ms":   ["DejaVu Sans", "Liberation Sans"],
    "impact":          ["DejaVu Sans", "Liberation Sans"],
}
_FALLBACK_FAMILIES = [
    "DejaVu Sans", "Liberation Sans", "FreeSans",
    "DejaVu Serif", "Liberation Serif",
    "DejaVu Sans Mono", "Liberation Mono",
]

# ── Font discovery ─────────────────────────────────────────────────────────────

def _font_dirs() -> list:
    s = platform.system()
    if s == "Windows":
        return [r"C:\Windows\Fonts",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Windows\Fonts")]
    if s == "Darwin":
        return ["/Library/Fonts", "/System/Library/Fonts",
                os.path.expanduser("~/Library/Fonts")]
    return ["/usr/share/fonts", "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts")]

_FONT_DB: Optional[dict] = None

def _scan_fonts() -> dict:
    result: dict = {}
    for d in _font_dirs():
        if not os.path.isdir(d): continue
        for root, _, files in os.walk(d):
            for fname in files:
                if not fname.lower().endswith(('.ttf', '.otf')): continue
                path = os.path.join(root, fname)
                try:
                    f = ImageFont.truetype(path, 10)
                    family, style = f.getname()
                    family = family.strip()
                except Exception:
                    continue
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
    if _FONT_DB is None:
        _FONT_DB = _scan_fonts()
    return _FONT_DB

def invalidate_font_cache():
    global _FONT_DB, _FONT_CACHE
    _FONT_DB = None
    _FONT_CACHE.clear()
    _LW_CACHE.clear()
    _ASC_CACHE.clear()
    try:
        from edof.engine.text_layout import clear_glyph_cache
        clear_glyph_cache()
    except Exception:
        pass

def list_system_fonts() -> list:
    return sorted(v.get('_display', k) for k, v in _get_db().items())

def get_font_path(family: str, bold: bool = False, italic: bool = False) -> Optional[str]:
    db = _get_db()

    def _lookup(fam: str) -> Optional[str]:
        key   = fam.lower()
        entry = db.get(key)
        if not entry:
            for k, v in db.items():
                if key in k or k in key:
                    entry = v; break
        if not entry: return None
        if bold and italic:
            return (entry.get('bolditalic') or entry.get('bold')
                    or entry.get('italic') or entry.get('regular'))
        if bold:   return entry.get('bold') or entry.get('bolditalic') or entry.get('regular')
        if italic: return entry.get('italic') or entry.get('bolditalic') or entry.get('regular')
        return entry.get('regular') or next((v for k, v in entry.items() if k != '_display'), None)

    path = _lookup(family)
    if path: return path
    for alias in _FONT_ALIASES.get(family.lower(), []):
        path = _lookup(alias)
        if path: return path
    for fb in _FALLBACK_FAMILIES:
        path = _lookup(fb)
        if path: return path
    return None

# ── Embedded (resource) fonts, v4.4.0 ────────────────────────────────────────
# BUG #11: embedded fonts used to be matched by a FILENAME SUBSTRING in one
# code path only (plain textboxes), so "Nunito Sans" never matched
# "NunitoSans-Regular.ttf" and rich-text runs never saw embedded fonts at
# all. This registry reads the REAL family + style from the font file's name
# table (PIL getname), keyed by a normalized family name, weight-aware.
# Installed from a document's resources (render entry points call
# register_resource_fonts); load_font consults it before the system lookup,
# so every text path gets embedded fonts.

_EMBED_FONTS: dict = {}          # norm_family -> {"regular"/"bold"/"italic"/"bolditalic": bytes}
_EMBED_SRC_KEY = None            # cache key of the registered resource set

_FONT_MIMES = ("font/ttf", "font/otf", "application/x-font-ttf",
               "application/x-font-opentype", "font/sfnt", "font/woff",
               "application/font-sfnt")


def _norm_family(name: str) -> str:
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


def register_resource_fonts(resources) -> None:
    """Install a document's embedded fonts. Cheap when unchanged (keyed by
    the set of font resource ids). Pass None to clear."""
    global _EMBED_FONTS, _EMBED_SRC_KEY
    if resources is None:
        _EMBED_FONTS = {}
        _EMBED_SRC_KEY = None
        return
    try:
        entries = [e for e in resources.all_entries()
                   if (e.mime_type or "") in _FONT_MIMES
                   or (e.filename or "").lower().endswith((".ttf", ".otf"))]
    except Exception:
        return
    key = tuple(sorted(getattr(e, "resource_id", "") for e in entries))
    if key == _EMBED_SRC_KEY:
        return
    fonts: dict = {}
    for e in entries:
        try:
            f = ImageFont.truetype(io.BytesIO(e.data), size=16)
            fam, sub = f.getname()
        except Exception:
            # unreadable name table: fall back to the filename stem
            stem = (e.filename or "").rsplit(".", 1)[0]
            fam, sub = stem, ""
        sub_l = (sub or "").lower()
        stem_l = (e.filename or "").lower()
        bold = ("bold" in sub_l) or ("bold" in stem_l)
        italic = ("italic" in sub_l or "oblique" in sub_l
                  or "italic" in stem_l or "oblique" in stem_l)
        slot = ("bolditalic" if bold and italic
                else "bold" if bold else "italic" if italic else "regular")
        fkey = _norm_family(fam)
        fonts.setdefault(fkey, {})[slot] = e.data
        # a filename-derived alias helps when the name table family differs
        # from what the document references
        stem_key = _norm_family((e.filename or "").rsplit(".", 1)[0])
        if stem_key and stem_key != fkey:
            fonts.setdefault(stem_key, {}).setdefault(slot, e.data)
    _EMBED_FONTS = fonts
    _EMBED_SRC_KEY = key


def embedded_font_bytes(family: str, bold: bool, italic: bool):
    """Bytes of the best embedded match for family+weight, or None.
    Exact style first, then graceful degradation to regular."""
    if not _EMBED_FONTS:
        return None
    fk = _norm_family(family)
    entry = _EMBED_FONTS.get(fk)
    if entry is None:
        # allow the document family to be a PREFIX of the registered one
        # ("Nunito Sans" vs "Nunito Sans 10pt") and vice versa
        for k, v in _EMBED_FONTS.items():
            if fk and (k.startswith(fk) or fk.startswith(k)):
                entry = v
                break
    if entry is None:
        return None
    if bold and italic:
        return (entry.get("bolditalic") or entry.get("bold")
                or entry.get("italic") or entry.get("regular"))
    if bold:
        return entry.get("bold") or entry.get("regular")
    if italic:
        return entry.get("italic") or entry.get("regular")
    return entry.get("regular") or next(iter(entry.values()), None)


# ── Font loading ───────────────────────────────────────────────────────────────

_FONT_CACHE: dict = {}

def load_font(family: str, bold: bool, italic: bool, size_px: int,
              font_data: Optional[bytes] = None) -> Optional[ImageFont.FreeTypeFont]:
    # v4.4.0: the embedded-font registry participates in resolution, so the
    # cache key must change when a different document's fonts are installed
    ckey = (family, bold, italic, size_px,
            hash(font_data) if font_data else None, _EMBED_SRC_KEY)
    if ckey in _FONT_CACHE: return _FONT_CACHE[ckey]
    font = None
    if font_data:
        try: font = ImageFont.truetype(io.BytesIO(font_data), size=size_px)
        except Exception: pass
    if font is None:
        # v4.4.0: embedded (resource) fonts, weight-aware, ALL text paths
        _ed = embedded_font_bytes(family, bold, italic)
        if _ed:
            try: font = ImageFont.truetype(io.BytesIO(_ed), size=size_px)
            except Exception: pass
    if font is None:
        path = get_font_path(family, bold, italic)
        if path:
            try: font = ImageFont.truetype(path, size=size_px)
            except Exception: pass
    if font is None:
        try: font = ImageFont.truetype(family, size=size_px)
        except Exception: pass
    if font is not None:
        _FONT_CACHE[ckey] = font
    return font

def load_font_safe(family: str, bold: bool, italic: bool, size_px: int,
                   font_data: Optional[bytes] = None) -> ImageFont.ImageFont:
    font = load_font(family, bold, italic, size_px, font_data)
    if font is not None: return font
    # Warn (item 2)
    try:
        from edof.exceptions import EdofMissingFontWarning
        warnings.warn(
            f"Font '{family}' not found. Using system fallback.",
            EdofMissingFontWarning, stacklevel=4)
    except ImportError:
        pass
    for fb in _FALLBACK_FAMILIES:
        font = load_font(fb, bold, italic, size_px)
        if font is not None: return font
    return ImageFont.load_default()

# ── Measurement ───────────────────────────────────────────────────────────────

def _lh(font, mult: float) -> int:
    try: asc, desc = font.getmetrics(); h = asc + abs(desc)
    except Exception:
        try: h = font.size
        except Exception: h = 12
    return max(1, int(h * mult))

_LW_CACHE: dict = {}      # (id(font), text) -> (font_ref, width)
_ASC_CACHE: dict = {}     # id(font) -> (font_ref, ascender)


def _lw(font, text: str) -> int:
    if not text: return 0
    # v4.2.11.33: measurement cache. getbbox is a pure function of
    # (font, text) and dominates layout cost on long documents (every word is
    # re-measured on every keystroke / fitting-scale probe / repagination).
    # Keeping a strong ref to the font in the value pins id(font) for the
    # cache's lifetime, so keys can never alias after a GC.
    key = (id(font), text)
    hit = _LW_CACHE.get(key)
    if hit is not None:
        return hit[1]
    # v4.3.6.24: measure the width the TEXT ACTUALLY OCCUPIES when drawn from the
    # pen origin. The old code used getbbox[2]-getbbox[0], which subtracts the
    # first glyph's LEFT side bearing -- but draw.text() starts at the pen, so
    # the rightmost pixel lands at getbbox[2], not getbbox[2]-getbbox[0]. For
    # fonts with a noticeable left bearing this UNDER-measured the line, so wrap
    # let a line through that then overflowed the box on render (the tail of the
    # line got clipped). Use max(advance, visual-right-edge): the advance is what
    # layout consumes, the visual right edge catches glyphs that overshoot it.
    adv = 0
    try:
        adv = int(round(font.getlength(text)))
    except Exception:
        adv = 0
    vis = 0
    try:
        bb = font.getbbox(text)
        vis = max(0, bb[2])
    except Exception:
        vis = 0
    w = max(adv, vis)
    if w <= 0:
        w = len(text) * 7
    if len(_LW_CACHE) > 400000:
        _LW_CACHE.clear()
    _LW_CACHE[key] = (font, w)
    return w


def _font_ascender(font, fallback: int) -> int:
    key = id(font)
    hit = _ASC_CACHE.get(key)
    if hit is not None:
        return hit[1]
    try: asc, _ = font.getmetrics()
    except Exception: asc = fallback
    if len(_ASC_CACHE) > 20000:
        _ASC_CACHE.clear()
    _ASC_CACHE[key] = (font, asc)
    return asc

def wrap_lines(text: str, font, max_w: Optional[int]) -> list:
    raw = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if max_w is None: return raw
    out = []
    for line in raw:
        if not line: out.append(''); continue
        words, cur = line.split(' '), ''
        for word in words:
            test = (cur + ' ' + word).strip()
            if _lw(font, test) <= max_w:
                cur = test
            else:
                if cur: out.append(cur)
                while word and _lw(font, word) > max_w:
                    for i in range(len(word), 0, -1):
                        if _lw(font, word[:i]) <= max_w:
                            out.append(word[:i]); word = word[i:]; break
                    else: out.append(word); word = ''; break
                cur = word
        if cur: out.append(cur)
    return out

def _fits(text: str, font, max_w: int, max_h: int, lh_mult: float, wrap: bool) -> bool:
    lines = wrap_lines(text, font, max_w if wrap else None)
    lh    = _lh(font, lh_mult)
    w     = max((_lw(font, l) for l in lines), default=0)
    h     = lh * len(lines)
    return w <= max_w and h <= max_h

# ── find_fitting_size ─────────────────────────────────────────────────────────

def find_fitting_size(text: str, max_w_px: int, max_h_px: int,
                      style: TextStyle, dpi: float = 96,
                      font_data: Optional[bytes] = None,
                      wrap: bool = True, shrink_only: bool = True) -> float:
    if not text: return style.font_size

    # v4.1.17: font_size is in mm now; convert mm → px for font loading
    def _mm_px(mm): return max(1, int(mm * dpi / 25.4))

    if load_font(style.font_family, style.bold, style.italic, _mm_px(4.233), font_data) is None:
        return style.font_size

    lo = max(0.1, style.min_font_size)
    # v4.1.19.6: cap binary-search upper bound for font growth.
    # Three cases for auto_fill (shrink_only=False):
    #   1. User checked "∞ no limit" → max_font_size = 1e6. Loading a font at
    #      1e6 mm fails (PIL can't rasterise glyphs that huge), so search
    #      aborted and returned min_font_size. Fix: use container-based cap.
    #   2. User set an explicit cap (e.g. 50 mm) → respect it strictly.
    #   3. Default 70.555 mm (~200 pt) on a fresh textbox → respect it.
    # Final hi is also clamped at 1000 mm (= 2834 pt) so font loading
    # always succeeds (font rasteriser limits).
    if shrink_only:
        hi = style.font_size
    else:
        container_h_mm = max_h_px * 25.4 / dpi if dpi else 100.0
        container_w_mm = max_w_px * 25.4 / dpi if dpi else 100.0
        container_cap = max(container_h_mm, container_w_mm) * 1.5
        if style.max_font_size >= 9999 or abs(style.max_font_size - 70.555) < 1e-6:
            # "∞ no limit" → grow until the container is full.
            # v4.3.0.1: the untouched legacy DEFAULT (70.555 mm = 200 pt) is
            # treated the same way — auto_fill means "fill the box", and the
            # silent default cap made it stop short in any box taller than
            # ~95 mm. An explicitly set different cap is still respected.
            hi = min(container_cap, 1000.0)
        else:
            # Explicit cap → respect it (clamp to font-loader hard limit)
            hi = min(float(style.max_font_size), 1000.0)

    if shrink_only:
        probe = load_font(style.font_family, style.bold, style.italic, _mm_px(hi), font_data)
        if probe and _fits(text, probe, max_w_px, max_h_px, style.line_height, wrap):
            return hi

    best = lo
    for _ in range(28):
        mid = (lo + hi) / 2.0
        f   = load_font(style.font_family, style.bold, style.italic, _mm_px(mid), font_data)
        if f is None: break
        if _fits(text, f, max_w_px, max_h_px, style.line_height, wrap):
            best = mid; lo = mid
        else:
            hi = mid
        if hi - lo < 0.005: break
    # v4.1.19.9: safety margin (see find_fitting_scale comment) — avoids
    # the last character being pushed to a new line by rounding mismatch
    # between fit check and final layout.
    return best * 0.995

# ── Auto-height helper (item 6) ───────────────────────────────────────────────

def measure_text_height(text: str, style: TextStyle, width_mm: float,
                        dpi: float = 96,
                        font_data: Optional[bytes] = None) -> float:
    """Height in mm needed to render text at given style inside width_mm."""
    # v4.1.0: per-side padding
    if hasattr(style, 'get_padding'):
        pt_mm, pr_mm, pb_mm, pl_mm = style.get_padding()
    else:
        pad_mm = getattr(style, 'padding', 1.0)
        pt_mm = pr_mm = pb_mm = pl_mm = pad_mm
    iw_px  = max(1, int(mm_to_px(max(0, width_mm - pl_mm - pr_mm), dpi)))
    sz_px  = max(1, int(style.font_size * dpi / 25.4))
    font   = load_font_safe(style.font_family, style.bold, style.italic, sz_px, font_data)
    lines  = wrap_lines(text, font, iw_px if style.wrap else None) if text else ['']
    lh_px  = _lh(font, style.line_height)
    total  = lh_px * len(lines) + mm_to_px(pt_mm + pb_mm, dpi)
    return total / (dpi / 25.4)

# ── Rendering ─────────────────────────────────────────────────────────────────

def render_text_onto(draw, text: str, style: TextStyle,
                     x_px: float, y_px: float, w_px: float, h_px: float,
                     dpi: float, font_data: Optional[bytes] = None) -> None:
    if not text: return

    # v4.1.0: per-side padding (item 4 from user feedback)
    if hasattr(style, 'get_padding'):
        pt_mm, pr_mm, pb_mm, pl_mm = style.get_padding()
    else:
        pad_mm = getattr(style, 'padding', 1.0)
        pt_mm = pr_mm = pb_mm = pl_mm = pad_mm
    pt = mm_to_px(pt_mm, dpi); pr = mm_to_px(pr_mm, dpi)
    pb = mm_to_px(pb_mm, dpi); pl = mm_to_px(pl_mm, dpi)
    ix = x_px + pl; iy = y_px + pt
    iw = max(1.0, w_px - pl - pr); ih = max(1.0, h_px - pt - pb)

    if style.auto_fill:
        fs_mm = find_fitting_size(text, int(iw), int(ih), style,
                                   dpi=dpi, font_data=font_data,
                                   wrap=style.wrap, shrink_only=False)
    elif style.auto_shrink:
        fs_mm = find_fitting_size(text, int(iw), int(ih), style,
                                   dpi=dpi, font_data=font_data,
                                   wrap=style.wrap, shrink_only=True)
    else:
        fs_mm = style.font_size

    # v4.1.17: font_size is in mm; convert to px via mm × dpi / 25.4
    sz_px = max(1, int(fs_mm * dpi / 25.4))
    font  = load_font_safe(style.font_family, style.bold, style.italic, sz_px, font_data)
    lines = wrap_lines(text, font, int(iw) if style.wrap else None)
    lh    = _lh(font, style.line_height)
    total = lh * len(lines)

    # v4.1.0: warn (once per box) if text doesn't fit and auto_shrink is off
    if total > ih and not style.auto_shrink and not style.auto_fill:
        import warnings
        warnings.warn(
            f"Text overflows textbox: {len(lines)} line(s) at {fs_mm:.2f}mm need "
            f"{total:.0f}px but box has only {ih:.0f}px inner height. "
            f"Set style.auto_shrink=True to fit, or increase box height. "
            f"Set style.overflow_hidden=True to clip.",
            RuntimeWarning, stacklevel=3
        )

    if   style.vertical_align == 'middle': ty = iy + (ih - total) / 2.0
    elif style.vertical_align == 'bottom': ty = iy + ih - total
    else:                                  ty = iy

    fill = tuple(style.color[:3])
    sw   = max(1, sz_px // 14)
    for line in lines:
        lw = _lw(font, line)
        if   style.alignment == 'center': lx = ix + (iw - lw) / 2.0
        elif style.alignment == 'right':  lx = ix + iw - lw
        else:                             lx = ix
        if style.overflow_hidden and ty + lh > y_px + h_px + 1: break
        draw.text((lx, ty), line, font=font, fill=fill)
        if style.underline:
            draw.line([(lx, int(ty+lh*0.9)), (lx+lw, int(ty+lh*0.9))], fill=fill, width=sw)
        if style.strikethrough:
            draw.line([(lx, int(ty+lh*0.55)), (lx+lw, int(ty+lh*0.55))], fill=fill, width=sw)
        ty += lh


# ══════════════════════════════════════════════════════════════════════════════
#  v4.0  Run-based rich text layout
# ══════════════════════════════════════════════════════════════════════════════

def _run_to_font(run_style: dict, dpi: float):
    """Load a font for a resolved run style dict."""
    sz_px = max(1, int(run_style["font_size"] * dpi / 25.4))
    return load_font_safe(run_style["font_family"], run_style["bold"],
                          run_style["italic"], sz_px), sz_px


def _layout_runs(runs, parent_style, max_w_px: int, dpi: float,
                 wrap: bool = True, scale: float = 1.0) -> tuple:
    """
    Lay out a list of TextRuns into lines. Returns:
      (lines, total_height_px, total_width_px)
    where each line is a list of (run, segment_text, width_px, font, ascender_px).
    """
    # Step 1: build a flat list of (run, char) entries, splitting at spaces and explicit \n
    word_seq = []   # list of (run, word, is_newline)
    for run in runs:
        text = run.text
        # Split keeping newlines
        i = 0
        while i < len(text):
            if text[i] == '\n':
                word_seq.append((run, '\n', True))
                i += 1
            else:
                # Read a run of non-newline chars
                j = i
                while j < len(text) and text[j] != '\n':
                    j += 1
                # Split by spaces but keep them attached
                segment = text[i:j]
                # Tokenize: words + spaces between
                k = 0
                while k < len(segment):
                    if segment[k] == ' ':
                        # Run of spaces
                        m = k
                        while m < len(segment) and segment[m] == ' ':
                            m += 1
                        word_seq.append((run, segment[k:m], False))
                        k = m
                    else:
                        m = k
                        while m < len(segment) and segment[m] != ' ':
                            m += 1
                        word_seq.append((run, segment[k:m], False))
                        k = m
                i = j

    # Step 2: pack words into lines respecting max_w_px
    lines = []          # list of [(run, text, width, font, ascender), ...]
    cur_line = []
    cur_w    = 0

    def _measure(run, text):
        rs   = run.resolve(parent_style, scale)
        font, sz_px = _run_to_font(rs, dpi)
        asc = _font_ascender(font, sz_px)
        w = _lw(font, text)
        return rs, font, sz_px, asc, w

    for run, word, is_nl in word_seq:
        if is_nl:
            lines.append(cur_line); cur_line = []; cur_w = 0
            continue
        rs, font, sz_px, asc, w = _measure(run, word)
        if wrap and cur_w + w > max_w_px and cur_line:
            lines.append(cur_line); cur_line = []; cur_w = 0
            # Skip leading spaces on new line
            if word.strip() == "":
                continue
        cur_line.append((run, word, w, font, asc, rs))
        cur_w += w
    if cur_line:
        lines.append(cur_line)

    # Step 3: compute line heights (max ascender + descender per line)
    line_metrics = []
    for line in lines:
        max_asc = max((seg[4] for seg in line), default=10)
        max_lh  = max((int(seg[5]["font_size"] * dpi / 25.4 * parent_style.line_height)
                       for seg in line), default=int(parent_style.font_size * dpi / 25.4 * parent_style.line_height))
        line_metrics.append((max_asc, max_lh))

    total_h = sum(lh for _, lh in line_metrics)
    total_w = max((sum(seg[2] for seg in line) for line in lines), default=0)

    return lines, total_h, total_w, line_metrics


def _runs_fit(runs, parent_style, max_w_px: int, max_h_px: int,
              dpi: float, wrap: bool, scale: float) -> bool:
    # v4.3.6.25: measure with the SAME layout the renderer uses (layout_runs),
    # not the private _layout_runs -- the two tokenised text into segments
    # differently, so their summed line widths disagreed by a few px. The fit
    # said "fits", the render wrapped a hair wider and clipped the last word.
    # layout_runs takes BOX dimensions and subtracts padding internally, so add
    # the padding back onto the inner max_w/max_h we were handed here.
    from edof.engine.text_layout import layout_runs as _layout_runs_render
    if hasattr(parent_style, 'get_padding'):
        pt_mm, pr_mm, pb_mm, pl_mm = parent_style.get_padding()
    else:
        _pad = getattr(parent_style, 'padding', 1.0)
        pt_mm = pr_mm = pb_mm = pl_mm = _pad
    pw = mm_to_px(pl_mm, dpi) + mm_to_px(pr_mm, dpi)
    ph = mm_to_px(pt_mm, dpi) + mm_to_px(pb_mm, dpi)
    lay = _layout_runs_render(runs, parent_style, 0.0, 0.0,
                              float(max_w_px) + pw, float(max_h_px) + ph,
                              dpi, scale=scale)
    return lay.total_w <= max_w_px + 0.5 and lay.total_h <= max_h_px + 0.5


def find_fitting_scale(runs, parent_style, max_w_px: int, max_h_px: int,
                       dpi: float = 96, wrap: bool = True,
                       shrink_only: bool = True) -> float:
    """v4.0: For runs, find a global scale factor that fits the box.
    Preserves relative font_size ratios between runs.

    v4.1.19.7: when growing (shrink_only=False, i.e. auto_fill), the upper
    bound for the scale is derived from style.max_font_size (or the
    container's own dimensions when the user enabled "∞ no limit"
    via max_font_size = 1e6). Previously hi was hard-coded to 5.0,
    which capped text at 5× the natural font size regardless of the
    user's settings — making both the max_font_size spinbox and the
    ∞ checkbox effectively non-functional for the runs render path.
    """
    if not runs:
        return 1.0

    if shrink_only:
        if _runs_fit(runs, parent_style, max_w_px, max_h_px, dpi, wrap, 1.0):
            return 1.0
        lo, hi = 0.05, 1.0
    else:
        base_fs = max(0.1, float(parent_style.font_size))
        container_h_mm = max_h_px * 25.4 / dpi if dpi else 100.0
        container_w_mm = max_w_px * 25.4 / dpi if dpi else 100.0
        container_cap_mm = max(container_h_mm, container_w_mm) * 1.5
        # Three cases:
        #   1. ∞ no limit (max ≥ 9999 mm sentinel) → grow up to container
        #   2. Explicit user cap                   → respect it
        #   3. Default 70.555 mm                    → respect it (legacy)
        # Hard absolute cap at 1000 mm so font rasterisation always succeeds.
        if (parent_style.max_font_size >= 9999
                or abs(parent_style.max_font_size - 70.555) < 1e-6):
            # v4.3.0.1: untouched legacy default = no cap (see find_fitting_size)
            hi_mm = min(container_cap_mm, 1000.0)
        else:
            hi_mm = min(float(parent_style.max_font_size), 1000.0)
        hi = max(1.0, hi_mm / base_fs)
        lo = 0.05

    best = lo
    for _ in range(28):
        mid = (lo + hi) / 2.0
        if _runs_fit(runs, parent_style, max_w_px, max_h_px, dpi, wrap, mid):
            best = mid; lo = mid
        else:
            hi = mid
        if hi - lo < 0.005: break
    # v4.1.19.9: tiny safety margin — the fit check and final layout use
    # slightly different rounding paths (PIL font metrics quantise to int
    # pixel widths in places). Without a margin the "just fits" result can
    # push the last character onto a new line in the actual rendered output.
    # 0.5% shrink keeps the size visually identical but eliminates the edge.
    return best * 0.995


def render_runs_onto(draw, runs, parent_style,
                     x_px: float, y_px: float, w_px: float, h_px: float,
                     dpi: float, scale: float = 1.0) -> None:
    """v4.0: Render a list of TextRuns into a box."""
    if not runs:
        return

    pad_mm = getattr(parent_style, 'padding', 1.0)
    pad    = mm_to_px(pad_mm, dpi)
    ix = x_px + pad; iy = y_px + pad
    iw = max(1.0, w_px - 2 * pad); ih = max(1.0, h_px - 2 * pad)

    lines, total_h, total_w, line_metrics = _layout_runs(
        runs, parent_style, int(iw), dpi, wrap=parent_style.wrap, scale=scale)

    # Vertical alignment
    if   parent_style.vertical_align == 'middle': ty = iy + (ih - total_h) / 2.0
    elif parent_style.vertical_align == 'bottom': ty = iy + ih - total_h
    else:                                          ty = iy

    for line, (max_asc, lh) in zip(lines, line_metrics):
        line_w = sum(seg[2] for seg in line)
        # Horizontal alignment
        if   parent_style.alignment == 'center': lx = ix + (iw - line_w) / 2.0
        elif parent_style.alignment == 'right':  lx = ix + iw - line_w
        else:                                     lx = ix

        # Render each segment
        for run, text, w, font, asc, rs in line:
            color = tuple(rs["color"][:3]) if rs["color"] else (0, 0, 0)
            bg    = rs.get("background")
            # Background highlight
            if bg and len(bg) >= 4 and bg[3] > 0:
                draw.rectangle([lx, ty, lx + w, ty + lh], fill=bg)
            # v4.3.6.1: variable-text marker (view-only). A run that is a batch
            # variable gets a faint tint + dotted underline when the toggle is on.
            if _SHOW_VARIABLES and getattr(run, "var_name", None):
                _draw_var_rainbow(draw, lx, ty, lx + w, ty + lh, dpi)
            # Baseline alignment: draw at baseline, accounting for ascender
            draw_y = ty + (max_asc - asc)
            draw.text((lx, draw_y), text, font=font, fill=color)
            sw = max(1, int(rs["font_size"] * dpi / 25.4) // 14)
            if rs.get("underline"):
                uy = int(ty + lh * 0.92)
                draw.line([(lx, uy), (lx + w, uy)], fill=color, width=sw)
            if rs.get("strikethrough"):
                sy = int(ty + lh * 0.55)
                draw.line([(lx, sy), (lx + w, sy)], fill=color, width=sw)
            lx += w
        ty += lh
