# edof/engine/text_layout.py
"""
v4.1.16: Unified text layout engine.

Provides a single source of truth for text layout used by BOTH:
  1. The canvas/PNG/PDF renderer (render_layout_onto)
  2. The inline text editor (hit-test, cursor positioning)

Justify (block) alignment is supported. Per-character positions are
recorded so the inline editor can hit-test clicks and position cursors
with no rendering-engine mismatch.

All sizes returned by this module are in canvas pixels at the given dpi
(= scene pixels = pixmap pixels). The inline editor converts to widget
coordinates by applying the same dpi-to-pixel conversion.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple

from edof.engine.text_engine import (
    load_font_safe, _run_to_font, _lw, _lh,
)
from edof.engine.transform import mm_to_px


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class CharBox:
    """One character's position in the laid-out text.

    coord units are canvas pixels (scene px) at the layout's dpi.
    """
    run_idx:    int    # index into runs list
    char_idx:   int    # absolute char index in the concatenated text
    char:       str    # the character itself
    x:          float  # left edge (pixels)
    y:          float  # top edge of the line containing the char
    w:          float  # advance width (pixels)
    line_idx:   int    # which logical line this char belongs to
    in_line_x:  float  # x position within the line (before alignment)
    line_top:   float  # y at line top
    line_h:     float  # line height
    ascender:   float  # baseline offset from line_top
    is_space:   bool   # whether this is whitespace
    is_newline: bool   # whether this is a forced newline (\n)


@dataclass
class LineInfo:
    line_idx:    int
    chars:       List[CharBox]
    width:       float       # natural width (no justify)
    height:      float
    ascender:    float
    top:         float       # y of line top after vertical alignment
    left:        float       # x of line start after horizontal alignment
    is_last:     bool        # true for the visually last line (no justify)


@dataclass
class Layout:
    """Complete laid-out text result."""
    lines:      List[LineInfo]
    chars:      List[CharBox] = field(default_factory=list)  # flat ordered list
    total_w:    float = 0.0
    total_h:    float = 0.0
    inner_x:    float = 0.0  # padding-adjusted x origin of text area
    inner_y:    float = 0.0
    inner_w:    float = 0.0
    inner_h:    float = 0.0
    overflow_v: bool  = False  # text taller than inner box
    overflow_h: bool  = False  # any line wider than inner box

    # ── Hit testing ────────────────────────────────────────────────────────────
    def hit_test(self, x: float, y: float) -> int:
        """Return the cursor index (0..len(text)) closest to (x,y).
        Coordinates are in scene/canvas pixels."""
        if not self.chars:
            return 0
        # Find the line whose vertical range contains y
        line = None
        for li in self.lines:
            if y < li.top + li.height:
                line = li
                break
        if line is None:
            line = self.lines[-1]
        # Within the line, find the char whose horizontal centre is closest
        # to x. Cursor goes BEFORE char if x < centre, AFTER if x >= centre.
        line_chars = line.chars
        if not line_chars:
            # empty line — cursor at line start
            return self._line_start_index(line.line_idx)
        for c in line_chars:
            cx = c.x + c.w * 0.5
            if x < cx:
                return c.char_idx
        # past the last visible char in the line
        # v4.1.21.3: when that last char is a newline (zero width, marks
        # the paragraph break), DON'T step over it — keep the cursor at
        # the newline's own index so it stays in the current paragraph.
        # Previously we returned last.char_idx + 1, which placed the cursor
        # at the START of the next paragraph when the user clicked at the
        # end of a line or anywhere on an empty middle paragraph (just a
        # bare \n line), making it impossible to put the cursor in the
        # empty paragraph itself.
        last = line_chars[-1]
        if last.is_newline:
            return last.char_idx
        return last.char_idx + 1

    def _line_start_index(self, line_idx: int) -> int:
        """Cursor index at start of the given line."""
        # Walk chars to find first char_idx in this line
        for c in self.chars:
            if c.line_idx == line_idx:
                return c.char_idx
        # past-the-end
        return len(self.chars)

    def cursor_xy(self, cursor_idx: int) -> Tuple[float, float, float]:
        """Return (x, y_top, height) for a cursor at the given index."""
        if not self.chars:
            # Empty document: place the caret using the (only) line's aligned
            # position, not the raw inner-left. v4.1.23.56: without this an
            # empty first paragraph set to center/right kept the caret hard
            # left until the user typed a character, because we ignored the
            # line's computed `left`. The line already carries the centered /
            # right-aligned origin, so honour it.
            if self.lines:
                ln = self.lines[0]
                return (ln.left, ln.top, ln.height)
            return (self.inner_x, self.inner_y, 12.0)
        # cursor_idx may be at end-of-text
        if cursor_idx >= len(self.chars):
            last = self.chars[-1]
            # If last char is a newline, cursor goes to next line start
            if last.is_newline:
                # find the line below
                next_line_idx = last.line_idx + 1
                # If there's a line, use its top
                if next_line_idx < len(self.lines):
                    li = self.lines[next_line_idx]
                    return (li.left, li.top, li.height)
                # Otherwise virtual line below the last
                li = self.lines[last.line_idx]
                return (li.left, li.top + li.height, li.height)
            return (last.x + last.w, last.line_top, last.line_h)
        c = self.chars[cursor_idx]
        return (c.x, c.line_top, c.line_h)

    def selection_rects(self, start: int, end: int) -> List[Tuple[float, float, float, float]]:
        """Return a list of (x, y, w, h) rects covering the selection."""
        if start == end or not self.chars:
            return []
        if start > end:
            start, end = end, start
        rects: List[Tuple[float, float, float, float]] = []
        # Iterate by line and accumulate
        current_line = -1
        seg_x = seg_y = seg_h = seg_w = 0.0
        for i in range(start, min(end, len(self.chars))):
            c = self.chars[i]
            if c.line_idx != current_line:
                if seg_w > 0:
                    rects.append((seg_x, seg_y, seg_w, seg_h))
                seg_x = c.x
                seg_y = c.line_top
                seg_h = c.line_h
                seg_w = c.w
                current_line = c.line_idx
            else:
                seg_w = (c.x + c.w) - seg_x
        if seg_w > 0:
            rects.append((seg_x, seg_y, seg_w, seg_h))
        return rects


# ── Layout function ────────────────────────────────────────────────────────────

def layout_runs(runs, parent_style,
                box_x_px: float, box_y_px: float,
                box_w_px: float, box_h_px: float,
                dpi: float, scale: float = 1.0,
                paragraph_alignments: dict = None,
                add_trailing_virtual: bool = True) -> Layout:
    """Produce a complete layout for the given runs inside the given box.

    v4.1.21: paragraph_alignments is an optional dict mapping paragraph
    index (as str) → alignment string. Paragraphs not in the dict fall
    back to parent_style.alignment. Paragraphs are counted from 0 and
    separated by '\\n' characters inside run text.

    v4.1.23.18: add_trailing_virtual — when False, a text that ends with
    '\\n' does NOT get the extra empty line below the final newline. This
    is used for a per-page editor whose content continues on the next page
    (a "continued" page): that empty line is just the page boundary and
    would otherwise sit in the bottom margin, where the caret must never
    rest. The last page of the flow keeps the trailing virtual (True).
    """
    paragraph_alignments = paragraph_alignments or {}
    # Padding (per-side if available)
    if hasattr(parent_style, 'get_padding'):
        pt_mm, pr_mm, pb_mm, pl_mm = parent_style.get_padding()
    else:
        pad_mm = getattr(parent_style, 'padding', 1.0)
        pt_mm = pr_mm = pb_mm = pl_mm = pad_mm
    pt = mm_to_px(pt_mm, dpi); pr = mm_to_px(pr_mm, dpi)
    pb = mm_to_px(pb_mm, dpi); pl = mm_to_px(pl_mm, dpi)

    inner_x = box_x_px + pl
    inner_y = box_y_px + pt
    inner_w = max(1.0, box_w_px - pl - pr)
    inner_h = max(1.0, box_h_px - pt - pb)

    default_align = getattr(parent_style, 'alignment', 'left') or 'left'
    valign    = getattr(parent_style, 'vertical_align', 'top') or 'top'
    do_wrap   = getattr(parent_style, 'wrap', True)
    line_mult = getattr(parent_style, 'line_height', 1.2)
    # v4.1.16.3: optional sub-mode for 'justify' alignment.
    justify_mode = getattr(parent_style, 'justify_mode', 'space') or 'space'
    if default_align == 'justify_full':
        default_align = 'justify'
        justify_mode = 'full'

    def alignment_for_para(idx: int) -> str:
        """v4.1.21: per-paragraph alignment. v4.1.23.35: run-derived alignment
        (carried on the runs) wins, then the paragraph_alignments map, then the
        style default."""
        raw = run_para_align.get(idx) or paragraph_alignments.get(str(idx))
        if raw == 'justify_full':
            return 'justify'   # justify_mode also gets bumped to 'full' below
        return raw or default_align

    # ── Step 1: tokenize all runs into a flat sequence of word/space/newline ──
    # v4.1.23.35: derive a paragraph→alignment map from the runs themselves so
    # alignment travels WITH the content (survives the pagination round-trip
    # and copy/paste), independent of the per-textbox paragraph_alignments map.
    # v4.1.23.49: assign each paragraph's alignment from the run that owns the
    # FIRST character of that paragraph (first-wins). The previous version only
    # registered the paragraph where a run STARTED, so a single run spanning a
    # newline ("Hello\nx" with alignment=center, which is exactly what you get
    # by pressing Enter on a centered line and typing) left the second
    # paragraph unaligned → it rendered left until pagination later split the
    # run per-paragraph. Walking characters fixes the live view while still
    # honouring an explicit different alignment on a following paragraph
    # (that text lives in its own run and wins for its own paragraph).
    run_para_align: dict = {}
    _para_idx = 0
    _need_para_start = True
    for _run in runs:
        _al = getattr(_run, 'alignment', None)
        for _ch in (_run.text or ""):
            if _need_para_start:
                if _al is not None and _para_idx not in run_para_align:
                    run_para_align[_para_idx] = _al
                _need_para_start = False
            if _ch == '\n':
                _para_idx += 1
                _need_para_start = True
    tokens: List[Tuple[int, str, str]] = []   # (run_idx, kind, text)
    abs_idx = 0
    char_run_map: List[Tuple[int, int]] = []  # for each abs_char_idx → (run_idx, char_in_run_idx)
    for r_idx, run in enumerate(runs):
        text = run.text or ""
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == '\n':
                tokens.append((r_idx, 'newline', '\n'))
                char_run_map.append((r_idx, i))
                i += 1
            elif ch == ' ' or ch == '\t':
                # group spaces
                j = i
                while j < len(text) and text[j] in (' ', '\t'):
                    char_run_map.append((r_idx, j))
                    j += 1
                tokens.append((r_idx, 'space', text[i:j]))
                i = j
            else:
                # word — non-space, non-newline
                j = i
                while j < len(text) and text[j] not in (' ', '\t', '\n'):
                    char_run_map.append((r_idx, j))
                    j += 1
                tokens.append((r_idx, 'word', text[i:j]))
                i = j

    # Helper: resolve a run + load font + measure
    cache: dict = {}
    def measure(r_idx: int, text: str):
        run = runs[r_idx]
        rs = run.resolve(parent_style, scale)
        key = (rs["font_family"], rs["bold"], rs["italic"], rs["font_size"])
        if key in cache:
            font, sz_px, asc = cache[key]
        else:
            font, sz_px = _run_to_font(rs, dpi)
            try: asc, _ = font.getmetrics()
            except Exception: asc = sz_px
            cache[key] = (font, sz_px, asc)
        w = _lw(font, text)
        # v4.1.23.33: per-run letter spacing — extra advance after each glyph
        # (mm → px). Added in measurement so wrapping, line width and per-char
        # positions all account for it consistently.
        ls = rs.get("letter_spacing", 0.0) or 0.0
        if ls:
            w += (ls * dpi / 25.4) * len(text)
        return rs, font, sz_px, asc, w

    # Per-character measurement (used inside words / spaces)
    def measure_char(r_idx: int, ch: str):
        rs, font, sz_px, asc, w = measure(r_idx, ch)
        return rs, font, sz_px, asc, w

    # ── Step 2: word-wrap with optional char-wrap fallback ───────────────────
    # A "line" is a list of dicts: {kind, r_idx, text, font, sz_px, asc, rs, width}
    raw_lines: List[List[dict]] = []
    cur: List[dict] = []
    cur_w = 0.0

    def line_break():
        nonlocal cur, cur_w
        raw_lines.append(cur)
        cur = []
        cur_w = 0.0

    overflow_h = False

    for r_idx, kind, txt in tokens:
        if kind == 'newline':
            # v4.1.23.29: carry the newline run's resolved metrics so an
            # EMPTY line (Enter with no text yet) takes the height of the
            # font that applies there, not the body default. This makes a
            # font-size / line-spacing change apply to pressed-Enter blank
            # lines, not only once the user starts typing.
            _nl_rs, _nlf, _nlsz, _nl_asc, _nlw = measure(r_idx, '')
            cur.append({'kind': 'newline', 'r_idx': r_idx, 'text': '\n',
                        'width': 0.0, 'rs': _nl_rs, 'asc': _nl_asc})
            line_break()
            continue
        rs, font, sz_px, asc, w = measure(r_idx, txt)
        seg = {'kind': kind, 'r_idx': r_idx, 'text': txt,
               'font': font, 'sz_px': sz_px, 'asc': asc, 'rs': rs,
               'width': w}
        if not do_wrap:
            cur.append(seg); cur_w += w
            continue
        if kind == 'space':
            if cur_w + w <= inner_w or not cur:
                cur.append(seg); cur_w += w
            else:
                # v4.1.23.40: keep the wrap-boundary space ON the current line
                # as a trailing space, then break. visible_end strips trailing
                # spaces from the width/justify math, so there is NO visual
                # change — but the space now gets a CharBox, which keeps each
                # CharBox.char_idx equal to the flat text index. Previously the
                # space was dropped silently; over a long document the missing
                # chars desynced char_idx from the text offset, so pagination
                # (which splits at a line's first_char) cut at the wrong place
                # and the per-page slice re-wrapped into one extra line → the
                # page overflowed the bottom margin.
                cur.append(seg)
                line_break()
            continue
        # word
        if cur_w + w <= inner_w:
            cur.append(seg); cur_w += w
        elif w > inner_w:
            # word longer than the line — char-wrap fallback
            overflow_h = True if w > inner_w else overflow_h
            for ch_i, ch in enumerate(txt):
                rs2, font2, sz2, asc2, w2 = measure_char(r_idx, ch)
                seg2 = {'kind': 'word', 'r_idx': r_idx, 'text': ch,
                        'font': font2, 'sz_px': sz2, 'asc': asc2, 'rs': rs2,
                        'width': w2}
                if cur_w + w2 > inner_w and cur:
                    line_break()
                cur.append(seg2); cur_w += w2
        else:
            line_break()
            cur.append(seg); cur_w += w
    if cur:
        raw_lines.append(cur)
    else:
        # v4.1.22.12: cur is empty after the main loop — usually because
        # the last token was a '\n'. The cursor should still have a
        # visual position on the implied empty line below that '\n'.
        # Append an empty raw_line for this trailing virtual line so the
        # cursor renders correctly AND so pagination knows there's a
        # blank line that may need to live on the next page.
        if add_trailing_virtual and raw_lines and any(
                seg.get('kind') == 'newline' for seg in raw_lines[-1]):
            raw_lines.append([])

    # Edge case: empty input
    if not raw_lines:
        raw_lines = [[]]

    # ── Step 3: per-line metrics ─────────────────────────────────────────────
    # Compute line_height and ascender for each line
    def default_font():
        rs = {"font_family": parent_style.font_family,
              "bold": parent_style.bold,
              "italic": parent_style.italic,
              "font_size": parent_style.font_size,
              "color": parent_style.color}
        return _run_to_font(rs, dpi)

    line_dims: List[Tuple[float, float, float]] = []  # (line_w, line_h, ascender)
    # v4.1.23.29/.33: track the font size AND line_height of the most recent
    # newline run so the trailing caret slot (an empty line with no segs at
    # all) inherits the size/spacing of the line that ended just above it.
    _last_nl_fs = parent_style.font_size
    _last_nl_lh = line_mult
    for line in raw_lines:
        line_w = sum(seg.get('width', 0.0) for seg in line)
        # v4.1.17.2: filter out newline segs (they carry no rs/asc metrics)
        meas_segs = [seg for seg in line if seg.get('kind') != 'newline' and 'rs' in seg]
        nl_segs = [seg for seg in line if seg.get('kind') == 'newline' and 'rs' in seg]
        if nl_segs:
            _last_nl_fs = max(seg['rs']["font_size"] for seg in nl_segs)
            _last_nl_lh = max(seg['rs'].get("line_height", line_mult) for seg in nl_segs)
        if meas_segs:
            asc = max(seg.get('asc', 0) for seg in meas_segs)
            # v4.1.23.18: EXACT float line height (mm geometry:
            # font_size_mm * dpi/25.4 * line_spacing) — no per-line pixel
            # rounding, so pagination and rendering agree at any size.
            # v4.1.23.33: the line_spacing is now PER RUN, so a line's height
            # is the max over its runs of (font_size * that run's line_height).
            # Mixed sizes/spacings on one line therefore size the line by the
            # tallest run, exactly as the user expects.
            lh = max(seg['rs']["font_size"] * dpi / 25.4
                     * seg['rs'].get("line_height", line_mult)
                     for seg in meas_segs)
        else:
            # v4.1.23.29: empty line. Use the size+spacing of the newline run
            # on this line if present (a blank line made by Enter), otherwise
            # the last newline values seen (the trailing caret slot after the
            # final '\n'), otherwise the parent style defaults. This way
            # pressing Enter at a set size/spacing keeps that size/spacing on
            # the new blank line instead of snapping back to the body default.
            if nl_segs:
                fs_mm = max(seg['rs']["font_size"] for seg in nl_segs)
                lh_mult = max(seg['rs'].get("line_height", line_mult) for seg in nl_segs)
                asc = max((seg.get('asc', 0) for seg in nl_segs), default=0.0)
            else:
                fs_mm = _last_nl_fs
                lh_mult = _last_nl_lh
                asc = 0.0
            if not asc:
                f, sz = default_font()
                try: asc, _ = f.getmetrics()
                except Exception: asc = sz
            lh = fs_mm * dpi / 25.4 * lh_mult
        line_dims.append((line_w, float(lh), float(asc)))

    total_h = sum(d[1] for d in line_dims)
    total_w = max((d[0] for d in line_dims), default=0.0)
    overflow_v = total_h > inner_h + 0.5
    overflow_h = overflow_h or (total_w > inner_w + 0.5)

    # ── Step 4: vertical alignment ───────────────────────────────────────────
    if   valign == 'middle': ty = inner_y + (inner_h - total_h) / 2.0
    elif valign == 'bottom': ty = inner_y + inner_h - total_h
    else:                     ty = inner_y

    # ── Step 5: build LineInfo + CharBox list with horizontal alignment ──────
    lines: List[LineInfo] = []
    chars_flat: List[CharBox] = []
    abs_char_idx = 0
    # v4.1.21: track current paragraph index. Paragraph 0 starts at first line;
    # each '\n' line ends the current paragraph and the next line begins a new
    # one. paragraph_alignments map provides per-paragraph alignment overrides.
    cur_para_idx = 0
    # v4.1.23.48: remember the effective alignment of the previous paragraph so
    # an EMPTY paragraph (the blank line you get by pressing Enter at the end of
    # a centered/right paragraph) can inherit it. Without this the caret on the
    # new empty line snapped to the left even though typed text lands centered.
    last_effective_align = default_align
    for line_idx, (line, (line_w, line_h, line_asc)) in enumerate(zip(raw_lines, line_dims)):
        is_last_visual = (line_idx == len(raw_lines) - 1)
        ends_with_newline = any(seg.get('kind') == 'newline' for seg in line)
        _line_empty = all(seg.get('kind') in ('space', 'newline') for seg in line)

        # Per-paragraph alignment. v4.1.23.35: run-derived alignment wins.
        raw_para_align = run_para_align.get(cur_para_idx) or paragraph_alignments.get(str(cur_para_idx))
        if raw_para_align == 'justify_full':
            alignment = 'justify'
            line_justify_mode = 'full'
        elif raw_para_align in ('left', 'center', 'right', 'justify'):
            alignment = raw_para_align
            line_justify_mode = justify_mode
        elif _line_empty and last_effective_align in ('center', 'right'):
            # Empty paragraph with no explicit alignment → inherit the previous
            # paragraph's alignment so the caret sits where text will appear.
            alignment = last_effective_align
            line_justify_mode = justify_mode
        else:
            alignment = default_align
            line_justify_mode = justify_mode
        last_effective_align = alignment

        # v4.1.16.3: count visual segments excluding TRAILING spaces.
        visible_end = len(line)
        while visible_end > 0 and line[visible_end - 1].get('kind') in ('space', 'newline'):
            visible_end -= 1
        natural_w = sum(seg.get('width', 0.0) for seg in line[:visible_end])

        # Determine layout strategy. v4.1.23.36: in FORCE mode ('justify_full')
        # also stretch the last line of a paragraph (and the very last line)
        # using automatic letter spacing — that is the "more forceful" justify.
        # The plain 'justify' mode leaves the last line natural, as usual.
        _force = (line_justify_mode == 'full')
        do_justify = (alignment == 'justify' and visible_end > 0
                      and (_force or (not is_last_visual and not ends_with_newline)))
        # Don't force-stretch a near-empty trailing line (a single short word
        # spread across the whole width looks broken).
        if (do_justify and _force and (is_last_visual or ends_with_newline)
                and natural_w < inner_w * 0.35):
            do_justify = False
        # Compute justify deltas
        extra_per_space = 0.0
        letter_spread = 0.0
        if do_justify:
            extra = max(0.0, inner_w - natural_w)
            n_spaces = sum(1 for seg in line[:visible_end] if seg.get('kind') == 'space')
            n_letters = sum(len(seg.get('text', ''))
                            for seg in line[:visible_end]
                            if seg.get('kind') == 'word')
            n_letter_slots = max(0, n_letters - 1)
            if line_justify_mode == 'full' and n_letter_slots > 0:
                # v4.1.23.38: FORCE justify is letter-spacing driven — it should
                # literally widen the gaps between letters, not blow up the
                # spaces between words. Put the bulk (85%) into letter spacing
                # and only a little (15%) into word spaces so words don't fuse.
                if n_spaces > 0:
                    extra_per_space = (extra * 0.15) / n_spaces
                    letter_spread   = (extra * 0.85) / n_letter_slots
                else:
                    letter_spread = extra / n_letter_slots
            else:
                if n_spaces > 0:
                    extra_per_space = extra / n_spaces

        # Horizontal origin
        if alignment == 'center':
            lx0 = inner_x + (inner_w - natural_w) / 2.0
        elif alignment == 'right':
            lx0 = inner_x + inner_w - natural_w
        else:  # left or justify
            lx0 = inner_x

        # Cursor at line origin
        lx = lx0
        line_chars: List[CharBox] = []
        # Track previous segment to know when to add letter_spread (only
        # between adjacent characters of the same word)
        emitted_count = 0
        prev_was_word_char = False
        for seg_pos, seg in enumerate(line):
            kind = seg.get('kind')
            text = seg.get('text', '')
            asc  = float(seg.get('asc', line_asc))
            is_visible_seg = seg_pos < visible_end
            if kind == 'newline':
                cb = CharBox(
                    run_idx=seg['r_idx'], char_idx=abs_char_idx, char='\n',
                    x=lx, y=ty, w=0.0,
                    line_idx=line_idx, in_line_x=lx - lx0,
                    line_top=ty, line_h=line_h, ascender=asc,
                    is_space=False, is_newline=True)
                line_chars.append(cb); chars_flat.append(cb)
                abs_char_idx += 1
                prev_was_word_char = False
                continue
            if kind == 'space':
                rs, _f, _s, _a, single_w = measure_char(seg['r_idx'], ' ')
                # Add justify extra only if this space is INSIDE the visible
                # part of the line.
                extra = extra_per_space if (is_visible_seg and do_justify) else 0.0
                for ch in text:
                    char_w = single_w + extra
                    cb = CharBox(
                        run_idx=seg['r_idx'], char_idx=abs_char_idx, char=ch,
                        x=lx, y=ty, w=char_w,
                        line_idx=line_idx, in_line_x=lx - lx0,
                        line_top=ty, line_h=line_h, ascender=asc,
                        is_space=True, is_newline=False)
                    line_chars.append(cb); chars_flat.append(cb)
                    lx += char_w
                    abs_char_idx += 1
                prev_was_word_char = False
                continue
            # word — each character with optional letter_spread
            for ch_i, ch in enumerate(text):
                _rs, _f, _s, _a, ch_w = measure_char(seg['r_idx'], ch)
                # Letter-spacing: add between consecutive word characters
                # within the visible part of the line
                spread = letter_spread if (do_justify and is_visible_seg
                                           and prev_was_word_char) else 0.0
                lx += spread
                cb = CharBox(
                    run_idx=seg['r_idx'], char_idx=abs_char_idx, char=ch,
                    x=lx, y=ty, w=ch_w,
                    line_idx=line_idx, in_line_x=lx - lx0,
                    line_top=ty, line_h=line_h, ascender=asc,
                    is_space=False, is_newline=False)
                line_chars.append(cb); chars_flat.append(cb)
                lx += ch_w
                abs_char_idx += 1
                prev_was_word_char = True

        lines.append(LineInfo(
            line_idx=line_idx, chars=line_chars,
            width=natural_w, height=line_h, ascender=line_asc,
            top=ty, left=lx0,
            is_last=is_last_visual,
        ))
        ty += line_h
        # v4.1.21: advance paragraph index when this line ended with a newline
        if ends_with_newline:
            cur_para_idx += 1

    return Layout(
        lines=lines, chars=chars_flat,
        total_w=total_w, total_h=total_h,
        inner_x=inner_x, inner_y=inner_y,
        inner_w=inner_w, inner_h=inner_h,
        overflow_v=overflow_v, overflow_h=overflow_h,
    )


# ── Rendering ──────────────────────────────────────────────────────────────────

_GLYPH_MASK_CACHE: dict = {}
_GLYPH_FAST = None   # None = not yet self-checked; True/False afterwards


def clear_glyph_cache():
    _GLYPH_MASK_CACHE.clear()


def _fast_char(draw, x, y, ch, font, color):
    """Replicate ImageDraw.text() for the plain case (no stroke, no embedded
    colour, no direction/features), reusing a cached FreeType mask. PIL's text()
    boils down to: coord=(int(x),int(y)); mask,off=font.getmask2(ch, fontmode,
    start=(frac(x),frac(y)), ...); draw_bitmap(coord+off, mask, ink). Only the
    expensive getmask2 (FreeType rasterisation) is cached; the final blend is
    PIL's own draw_bitmap, so the output is bit-identical by construction."""
    import math as _math
    mode = draw.fontmode
    ink, fill_ink = draw._getink(color)
    if ink is None:
        ink = fill_ink
    if ink is None:
        return
    cx, cy = int(x), int(y)
    fx = _math.modf(x)[0]; fy = _math.modf(y)[0]
    key = (id(font), ch, mode, ink, fx, fy)
    ent = _GLYPH_MASK_CACHE.get(key)
    if ent is None:
        mask, offset = font.getmask2(ch, mode, stroke_width=0,
                                     stroke_filled=True, anchor=None,
                                     ink=ink, start=(fx, fy))
        if len(_GLYPH_MASK_CACHE) > 60000:
            _GLYPH_MASK_CACHE.clear()
        ent = (font, mask, offset)        # strong font ref pins id(font)
        _GLYPH_MASK_CACHE[key] = ent
    _, mask, offset = ent
    draw.draw.draw_bitmap((cx + offset[0], cy + offset[1]), mask, ink)


def _glyph_fast_ok():
    """One-time self-check: render a probe string char-by-char via draw.text
    and via _fast_char at integer AND fractional positions on transparent,
    opaque and semi-transparent backgrounds. The fast path is enabled ONLY if
    every byte matches, so a different Pillow internals version can never
    change the rendering -- it just falls back to plain draw.text."""
    global _GLYPH_FAST
    if _GLYPH_FAST is not None:
        return _GLYPH_FAST
    try:
        from PIL import Image as _I, ImageDraw as _ID
        from edof.engine.text_engine import load_font_safe
        font = load_font_safe("Arial", False, False, 23, None)
        if font is None:
            _GLYPH_FAST = False
            return False
        probe = "Ayg9ěQ.;W"
        ok = True
        for bg in ((0, 0, 0, 0), (255, 255, 255, 255), (10, 200, 30, 128)):
            for x0, y0 in ((7, 5), (7.55, 5.3)):
                a = _I.new("RGBA", (220, 40), bg); da = _ID.Draw(a)
                b = _I.new("RGBA", (220, 40), bg); db = _ID.Draw(b)
                xa = x0
                for ch in probe:
                    da.text((xa, y0), ch, font=font, fill=(20, 40, 200))
                    xa += max(4, font.getbbox(ch)[2])
                xb = x0
                for ch in probe:
                    _fast_char(db, xb, y0, ch, font, (20, 40, 200))
                    xb += max(4, font.getbbox(ch)[2])
                if a.tobytes() != b.tobytes():
                    ok = False
        _GLYPH_FAST = ok
    except Exception:
        _GLYPH_FAST = False
    return _GLYPH_FAST


def render_layout_onto(draw, layout: Layout, runs, parent_style,
                       dpi: float, scale: float = 1.0,
                       clip_to_inner: bool = True) -> None:
    """Draw a previously-computed layout onto a PIL ImageDraw."""
    # v4.2.11.36: resolve each RUN once instead of once per character.
    # run.resolve + font lookup + colour unpacking were executed for every
    # glyph (thousands of times on a document page) although they only depend
    # on the run. The draw calls themselves are unchanged (bit-identical).
    _rcache = {}

    def _run_ctx(run_idx):
        ctx = _rcache.get(run_idx)
        if ctx is None:
            run = runs[run_idx] if 0 <= run_idx < len(runs) else None
            if run is None:
                ctx = None
            else:
                rs = run.resolve(parent_style, scale)
                font, _ = _run_to_font(rs, dpi)
                color = tuple(rs["color"][:3]) if rs["color"] else (0, 0, 0)
                bg = rs.get("background")
                sw = max(1, int(rs["font_size"] * dpi / 25.4) // 14)
                ctx = (rs, font, color, bg, sw)
            _rcache[run_idx] = ctx
        return ctx

    _fast = _glyph_fast_ok()
    for line in layout.lines:
        for c in line.chars:
            if c.is_newline:
                continue
            ctx = _run_ctx(c.run_idx)
            if ctx is None:
                continue
            rs, font, color, bg, sw = ctx
            # baseline draw position: line_top + (line_ascender - char_asc)
            draw_y = c.line_top + (line.ascender - c.ascender)
            # background highlight
            if bg and len(bg) >= 4 and bg[3] > 0:
                draw.rectangle([c.x, c.line_top, c.x + c.w, c.line_top + c.line_h], fill=bg)
            # draw char (cached FreeType mask when the self-check passed;
            # bit-identical -- otherwise plain draw.text)
            if _fast:
                try:
                    _fast_char(draw, c.x, draw_y, c.char, font, color)
                except Exception:
                    draw.text((c.x, draw_y), c.char, font=font, fill=color)
            else:
                draw.text((c.x, draw_y), c.char, font=font, fill=color)
            # underline / strikethrough per char
            if rs.get("underline"):
                uy = int(c.line_top + c.line_h * 0.92)
                draw.line([(c.x, uy), (c.x + c.w, uy)], fill=color, width=sw)
            if rs.get("strikethrough"):
                sy = int(c.line_top + c.line_h * 0.55)
                draw.line([(c.x, sy), (c.x + c.w, sy)], fill=color, width=sw)


# ── Convenience: layout from a TextBox object ─────────────────────────────────

def layout_textbox(obj, dpi: float, scale: float = 1.0) -> Layout:
    """Produce a Layout for a TextBox object's current state."""
    t = obj.transform
    box_x = mm_to_px(t.x, dpi)
    box_y = mm_to_px(t.y, dpi)
    box_w = mm_to_px(t.width,  dpi)
    box_h = mm_to_px(t.height, dpi)
    runs = obj.runs if obj.runs else [_synthetic_run(obj)]
    return layout_runs(runs, obj.style, box_x, box_y, box_w, box_h, dpi, scale)


def _synthetic_run(obj):
    """Build a single TextRun representing the plain text of a textbox."""
    from edof.format.styles import TextRun
    return TextRun(
        text=obj.text or "",
        font_family=obj.style.font_family,
        font_size=obj.style.font_size,
        bold=obj.style.bold,
        italic=obj.style.italic,
        underline=False,
        color=obj.style.color,
    )
