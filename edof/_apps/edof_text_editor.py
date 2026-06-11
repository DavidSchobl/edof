# edof/_apps/edof_text_editor.py
"""
v4.1.16: Custom inline text editor for the EDOF editor.

KEY ARCHITECTURAL DECISION: this widget renders text using the SAME
PIL/freetype pipeline as the canvas/PDF/PNG renderer. There is no Qt
text rendering anywhere in the inline path. Consequence: the inline
editor and the rendered output are *pixel-perfect identical* by
construction.

Provides:
  • Rich text editing on TextRun list
  • Bold / Italic / Underline / Strikethrough toggles for current
    selection or future input
  • Horizontal alignment: left / center / right / justify (block text)
  • Vertical alignment: top / middle / bottom
  • Undo/Redo stack
  • Selection (click+drag, shift+arrows, Ctrl+A)
  • Clipboard with custom MIME type that preserves runs
  • IME support for Czech diacritics and other input methods
  • Overflow indicator (red border + arrow when text doesn't fit)
  • Word wrap with char-wrap fallback (delegated to text_layout)
  • Variable font sizes within one textbox (already supported by runs)

The widget is hosted in a QGraphicsProxyWidget by the editor, which
places it in the scene at the textbox's scene coordinates. The scene
transform handles zoom — this widget always works in scene-pixel units
(= the same pixel space the renderer uses).
"""
from __future__ import annotations
import copy, io
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QMimeData, pyqtSignal, QEvent
from PyQt6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QBrush, QKeyEvent,
    QMouseEvent, QInputMethodEvent, QFont, QFontMetrics, QGuiApplication,
)
from PyQt6.QtWidgets import QWidget, QApplication

from PIL import Image, ImageDraw

from edof.engine.text_layout import (
    Layout, layout_runs, render_layout_onto,
)
from edof.engine.transform import mm_to_px
from edof.format.styles import TextRun


_EDOF_RUNS_MIME = "application/x-edof-textruns"


# ── HTML clipboard → runs (v4.1.23.37) ──────────────────────────────────────
def _css_size_to_mm(val: str):
    """Parse a CSS font-size ('12pt', '16px', '1.2em' ignored) to mm."""
    try:
        v = val.strip().lower()
        if v.endswith('pt'):
            return float(v[:-2]) * 25.4 / 72.0
        if v.endswith('px'):
            return float(v[:-2]) / 96.0 * 25.4
        if v.endswith('mm'):
            return float(v[:-2])
        if v.endswith('%'):
            return None
        return float(v) / 96.0 * 25.4   # bare number → px
    except Exception:
        return None


def _css_color_to_rgba(val: str):
    try:
        v = val.strip().lower()
        if v.startswith('#'):
            h = v[1:]
            if len(h) == 3:
                h = ''.join(c * 2 for c in h)
            if len(h) >= 6:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
        if v.startswith('rgb'):
            nums = [int(float(x)) for x in v[v.find('(') + 1:v.find(')')].split(',')[:3]]
            if len(nums) == 3:
                return (nums[0], nums[1], nums[2], 255)
    except Exception:
        pass
    return None


def html_to_runs(html: str):
    """Convert clipboard HTML (from a browser, Google Sheets/Docs, Word, …)
    into a list of TextRun, preserving bold/italic/underline/strike, font
    family, font size (→mm), colour, letter spacing and line height. Block
    elements become '\\n'. Best-effort: unknown markup is ignored."""
    from html.parser import HTMLParser
    from edof.format.styles import TextRun

    BLOCK = {'p', 'div', 'br', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
             'blockquote', 'table'}
    SKIP = {'style', 'script', 'head', 'title'}
    VOID = {'meta', 'link', 'br', 'img', 'hr', 'input', 'base', 'col',
            'area', 'source', 'wbr', 'embed', 'param', 'track'}

    class _P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.runs = []
            self.stack = [{}]          # style frames
            self.skip_depth = 0
            self.list_stack = []       # nested ul/ol context

        def _cur(self):
            return self.stack[-1]

        def _style_from_attrs(self, tag, attrs):
            s = dict(self._cur())
            d = dict(attrs)
            if tag in ('b', 'strong'): s['bold'] = True
            if tag in ('i', 'em'):     s['italic'] = True
            if tag == 'u':             s['underline'] = True
            if tag in ('s', 'strike', 'del'): s['strike'] = True
            if tag == 'font':
                if d.get('color'):
                    c = _css_color_to_rgba(d['color']);  s['color'] = c or s.get('color')
                if d.get('face'): s['font_family'] = d['face']
            css = d.get('style', '')
            for decl in css.split(';'):
                if ':' not in decl: continue
                k, v = decl.split(':', 1); k = k.strip().lower(); v = v.strip()
                if k == 'font-weight':
                    s['bold'] = (v in ('bold', 'bolder') or (v.isdigit() and int(v) >= 600))
                elif k == 'font-style':
                    s['italic'] = v.startswith('italic') or v.startswith('oblique')
                elif k == 'text-decoration' or k == 'text-decoration-line':
                    if 'underline' in v: s['underline'] = True
                    if 'line-through' in v: s['strike'] = True
                elif k == 'font-size':
                    mm = _css_size_to_mm(v)
                    if mm: s['font_size'] = mm
                elif k == 'font-family':
                    s['font_family'] = v.split(',')[0].strip().strip('"\'')
                elif k == 'color':
                    c = _css_color_to_rgba(v)
                    if c: s['color'] = c
                elif k == 'letter-spacing':
                    mm = _css_size_to_mm(v)
                    if mm is not None: s['letter_spacing'] = mm
                elif k == 'line-height':
                    try:
                        if v.replace('.', '', 1).isdigit():
                            s['line_height'] = float(v)
                    except Exception: pass
            return s

        def handle_starttag(self, tag, attrs):
            if tag in SKIP:
                self.skip_depth += 1; return
            if self.skip_depth: return
            if tag in ('ul', 'ol'):
                self.list_stack.append({'type': tag, 'n': 0})
                self.stack.append(dict(self._cur()))
                return
            if tag == 'li':
                self.stack.append(self._style_from_attrs(tag, attrs))
                depth = max(0, len(self.list_stack) - 1)
                if self.runs and not (self.runs[-1].text or '').endswith('\n'):
                    self._emit('\n', self._cur())
                if self.list_stack and self.list_stack[-1]['type'] == 'ol':
                    self.list_stack[-1]['n'] += 1
                    marker = ('    ' * depth) + str(self.list_stack[-1]['n']) + '.  '
                else:
                    bl = ['•', '◦', '▪', '‣', '·']
                    marker = ('    ' * depth) + bl[min(depth, len(bl) - 1)] + '  '
                self._emit(marker, self._cur())
                return
            if tag in VOID:
                # void elements have no end tag — don't push a style frame
                # (it would never be popped and corrupt the stack), just
                # handle their side effect.
                if tag == 'br':
                    self._emit('\n', self._cur())
                return
            self.stack.append(self._style_from_attrs(tag, attrs))
            if tag == 'br':
                self._emit('\n', self._cur())
            elif tag in BLOCK and self.runs and not (self.runs[-1].text or '').endswith('\n'):
                self._emit('\n', self._cur())

        def handle_endtag(self, tag):
            if tag in SKIP:
                self.skip_depth = max(0, self.skip_depth - 1); return
            if self.skip_depth: return
            if tag in ('ul', 'ol'):
                if len(self.stack) > 1: self.stack.pop()
                if self.list_stack: self.list_stack.pop()
                return
            if len(self.stack) > 1:
                self.stack.pop()
            if tag in ('td', 'th'):
                self._emit('\t', self._cur())   # separate spreadsheet cells
            elif tag in BLOCK and tag != 'br':
                if self.runs and not (self.runs[-1].text or '').endswith('\n'):
                    self._emit('\n', self._cur())

        def handle_data(self, data):
            if self.skip_depth or not data:
                return
            # collapse internal whitespace (HTML semantics) but KEEP a single
            # leading/trailing space if the original had one, so inter-word
            # spacing across tag boundaries ("normal <b>bold</b>") survives.
            lead = ' ' if data[:1] in ' \t\r\n' else ''
            trail = ' ' if data[-1:] in ' \t\r\n' else ''
            core = ' '.join(data.split())
            txt = (lead + core + trail) if core else (lead or trail)
            if txt:
                self._emit(txt, self._cur())

        def _emit(self, text, s):
            r = TextRun(
                text=text,
                font_family=s.get('font_family'),
                font_size=s.get('font_size'),
                bold=s.get('bold'),
                italic=s.get('italic'),
                underline=s.get('underline'),
                strikethrough=s.get('strike'),
                color=s.get('color'),
                line_height=s.get('line_height'),
                letter_spacing=s.get('letter_spacing'),
            )
            self.runs.append(r)

    try:
        p = _P(); p.feed(html); p.close()
    except Exception:
        return []
    # drop a leading newline artifact
    runs = p.runs
    while runs and runs[0].text == '\n':
        runs.pop(0)
    return runs


def markdown_to_runs(md: str):
    """v4.1.23.38: convert Markdown text into formatted runs. Supports
    headings (#..######), **bold**, *italic* / _italic_, `code`, and
    bullet / numbered list lines (rendered with a • / number prefix as a
    stopgap until native list objects exist). Block structure → newlines."""
    import re
    from edof.format.styles import TextRun
    BODY_MM = 4.233           # 12 pt
    H_MM = {1: 8.0, 2: 6.8, 3: 5.8, 4: 5.0, 5: 4.6, 6: 4.3}
    out = []

    def emit_inline(text, base_bold=False, base_size=None):
        # split on **bold**, *italic*/_italic_, `code`
        i = 0
        tokens = re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_|`[^`]+`)', text)
        for tok in tokens:
            if not tok:
                continue
            bold = base_bold; italic = False; mono = None
            inner = tok
            if tok.startswith('**') and tok.endswith('**') and len(tok) >= 4:
                bold = True; inner = tok[2:-2]
            elif tok.startswith('*') and tok.endswith('*') and len(tok) >= 2:
                italic = True; inner = tok[1:-1]
            elif tok.startswith('_') and tok.endswith('_') and len(tok) >= 2:
                italic = True; inner = tok[1:-1]
            elif tok.startswith('`') and tok.endswith('`') and len(tok) >= 2:
                inner = tok[1:-1]; mono = 'Consolas'
            out.append(TextRun(text=inner,
                               font_size=base_size,
                               bold=(True if bold else None),
                               italic=(True if italic else None),
                               font_family=mono))

    def _depth(prefix):
        # tabs count as one level each; every 2 spaces = one level
        tabs = prefix.count('\t')
        spaces = len(prefix.replace('\t', ''))
        return tabs + spaces // 2

    _BULLETS = ['•', '◦', '▪', '‣', '·']
    lines = md.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    for li, line in enumerate(lines):
        h = re.match(r'^(#{1,6})\s+(.*)$', line)
        bullet = re.match(r'^([\t ]*)[-*+]\s+(.*)$', line)
        num = re.match(r'^([\t ]*)(\d+)\.\s+(.*)$', line)
        if h:
            lvl = len(h.group(1))
            emit_inline(h.group(2), base_bold=True, base_size=H_MM.get(lvl, 6.0))
        elif bullet:
            d = _depth(bullet.group(1))
            mark = _BULLETS[min(d, len(_BULLETS) - 1)]
            out.append(TextRun(text=('    ' * d) + mark + '  '))
            emit_inline(bullet.group(2))
        elif num:
            d = _depth(num.group(1))
            out.append(TextRun(text=('    ' * d) + num.group(2) + '.  '))
            emit_inline(num.group(3))
        else:
            emit_inline(line)
        if li < len(lines) - 1:
            out.append(TextRun(text='\n'))
    return out


# ── Undo entry ─────────────────────────────────────────────────────────────────

@dataclass
class _UndoEntry:
    runs:       list
    cursor:     int
    sel_anchor: Optional[int]
    label:      str = ""


def _clone_runs(runs):
    """Deep-copy a list of TextRun objects."""
    out = []
    for r in runs:
        # TextRun is a dataclass; copy via constructor
        try:
            kw = {f.name: getattr(r, f.name) for f in r.__dataclass_fields__.values()}
            out.append(type(r)(**kw))
        except Exception:
            out.append(copy.copy(r))
    return out


# ── Run manipulation helpers ──────────────────────────────────────────────────

def _runs_text(runs) -> str:
    return "".join((r.text or "") for r in runs)


def _runs_total_len(runs) -> int:
    return sum(len(r.text or "") for r in runs)


def _split_run_at(runs, run_idx: int, char_offset: int) -> int:
    """Split runs[run_idx] at the given char offset within that run.
    Returns the new run_idx for the right half."""
    r = runs[run_idx]
    if char_offset <= 0:
        return run_idx
    if char_offset >= len(r.text or ""):
        return run_idx + 1
    left_text  = r.text[:char_offset]
    right_text = r.text[char_offset:]
    r.text = left_text
    new = _clone_runs([r])[0]
    new.text = right_text
    runs.insert(run_idx + 1, new)
    return run_idx + 1


def _abs_to_run(runs, abs_idx: int) -> Tuple[int, int]:
    """Convert absolute char index to (run_idx, char_offset_within_run).

    For abs_idx == total_len, returns (last_run_idx, len(last_run.text))."""
    if not runs:
        return 0, 0
    acc = 0
    for i, r in enumerate(runs):
        L = len(r.text or "")
        if abs_idx < acc + L:
            return i, abs_idx - acc
        acc += L
    return len(runs) - 1, len(runs[-1].text or "")


def _scale_layout(layout, sx: float, sy: float):
    """Return a new Layout with all char coords scaled by (sx, sy).
    Used when rendering glyphs at natural size then resampling — the
    inline editor needs a scaled layout so hit-testing matches the
    deformed visual output."""
    import dataclasses, copy as _copy
    new = _copy.copy(layout)
    new.chars = []
    new.lines = []
    for c in layout.chars:
        nc = dataclasses.replace(
            c, x=c.x * sx, y=c.y * sy, w=c.w * sx,
            line_top=c.line_top * sy, line_h=c.line_h * sy,
            ascender=c.ascender * sy,
        )
        new.chars.append(nc)
    for ln in layout.lines:
        # rebuild ln.chars from already-scaled new.chars
        scaled_chars = [nc for nc in new.chars if nc.line_idx == ln.line_idx]
        nl = dataclasses.replace(
            ln, chars=scaled_chars,
            width=ln.width * sx, height=ln.height * sy,
            top=ln.top * sy, left=ln.left * sx,
            ascender=ln.ascender * sy,
        )
        new.lines.append(nl)
    new.total_w *= sx; new.total_h *= sy
    new.inner_x *= sx; new.inner_y *= sy
    new.inner_w *= sx; new.inner_h *= sy
    return new


def _normalize_runs(runs):
    """Merge adjacent runs with identical formatting, remove empties.

    v4.1.23.2: PURE — does not mutate the input list or its TextRun
    objects. Previously this function appended subsequent runs' text
    onto runs[0].text in place. Callers (notably sync_to_tb_silent)
    assigned the returned shorter list to tb.runs but left self._runs
    pointing at the original (now-mutated) list, so editor's _runs
    ended up with r0 holding the merged text AND r1..rN still holding
    their original fragments. Result: text_len doubled on every idle
    cycle, body.paragraphs grew unbounded, and paginate kept creating
    pages out of phantom content. Hard to find but devastating in
    practice — see the user-reported "1213 paragraphs / 21 pages"
    after ~85 Enter keystrokes."""
    if not runs:
        return runs
    out = []
    for r in runs:
        rt = r.text or ""
        if out:
            last = out[-1]
            same = all(getattr(last, attr, None) == getattr(r, attr, None)
                       for attr in ('font_family', 'font_size', 'bold', 'italic',
                                    'underline', 'color', 'background',
                                    'strikethrough', 'line_height', 'letter_spacing',
                                    'alignment'))
            if same:
                # Mutate the COPY in out, never the input.
                last.text = (last.text or "") + rt
                continue
        # Skip empties unless out is empty (preserve one run)
        if not rt and out:
            continue
        out.append(copy.deepcopy(r))
    # Ensure at least one run exists
    if not out:
        from edof.format.styles import TextRun
        out = [TextRun(text="")]
    return out


# ── The widget ─────────────────────────────────────────────────────────────────

class EdofTextEditor(QWidget):
    """Inline text editor for one TextBox, rendered via PIL."""

    committed = pyqtSignal(object)  # emits TextBox when Ctrl+Enter
    cancelled = pyqtSignal(object)  # emits TextBox when Esc
    # v4.1.20.1: emitted when user presses Ctrl+Shift+Enter — document-mode
    # canvas catches this to insert a new page and re-enter inline edit on
    # the new page's body. Normal Ctrl+Enter still commits to the current
    # textbox (so this is non-breaking for non-doc-mode users).
    new_page_requested = pyqtSignal(object)
    # v4.1.20.1: emitted when the inline editor's overflow state changes.
    # Doc-mode canvas uses this to show a hint about adding a new page.
    overflow_changed = pyqtSignal(bool)
    # v4.1.22.1: doc-mode signals for seamless multi-page editing.
    # backspace at cursor=0 → caller decides what "merge with previous" means
    # (navigate to previous page's body, optionally moving the content up).
    merge_with_previous_requested = pyqtSignal(object)
    # v4.1.23.20: Delete at cursor==len inside a doc body → caller pulls the
    # next page's content up (forward-delete across the page boundary), the
    # mirror image of merge_with_previous_requested.
    merge_with_next_requested = pyqtSignal(object)
    # ~1200 ms after the last keystroke while the editor is overflowing
    # and the textbox is a doc body — the canvas auto-commits so the
    # reflow engine can move the overflow to the next page automatically.
    idle_overflow_reached = pyqtSignal(object)
    # v4.1.22.2: emitted (debounced) whenever the caret moves or content
    # changes — the canvas listens so it can ensure the cursor remains
    # within the visible viewport (Word-style auto-scroll).
    cursor_changed = pyqtSignal()
    # v4.1.22.4: doc-body cursor navigation across pages.
    # navigate_above is emitted when the user presses Up/PgUp/Home(with no
    # earlier line available) and the cursor is already on the first line
    # of the body — the canvas hops to the previous page's body.
    navigate_above = pyqtSignal(object)
    # navigate_below is the same idea for Down/PgDown/End at the last line.
    navigate_below = pyqtSignal(object)

    def __init__(self, textbox, parent=None, *, dpi: float = 96.0,
                 page_bg: Optional[Tuple[int, int, int, int]] = None,
                 bg_snapshot=None, is_doc_body: bool = False):
        """v4.1.19.2: page_bg is the colour of the page beneath this textbox.
        Used as the inline editor's default background when the textbox has
        no fill of its own — so the editor doesn't look like a dark hole on
        a white page. Pass None when the textbox is overlaid on a transparent
        backdrop (e.g. embedded sub-document).

        v4.1.20.7: bg_snapshot is an optional QImage snapshot of the canvas
        pixmap at the textbox's location, used as the editor's opaque
        background. Sidesteps QGraphicsProxyWidget transparency bugs that
        plagued 4.1.17.x — 4.1.20.6 (yellow / dark cast under the widget).
        When provided, the editor paints this snapshot first, then text
        on top, producing a visually transparent result with zero
        reliance on Qt's transparency machinery.

        v4.1.22.1: is_doc_body marks this editor as the page-spanning
        body textbox in document mode. Behaviour differences:
          • No red overflow border (overflow flows to next page instead)
          • Idle-overflow auto-commit signal fires after ~1200 ms of no typing
          • Backspace at cursor=0 emits merge_with_previous_requested
          • The inline toolbar hides the commit/cancel ✓/✗ buttons (the
            body is never "cancelled" — Esc just ends the edit session)"""
        super().__init__(parent)
        self.tb = textbox
        self.dpi = float(dpi)
        # v4.1.19.2: remember the page background so we can use it as the
        # default fill behind text when the textbox itself has no fill set.
        self._page_bg = page_bg
        # v4.1.20.7: optional opaque QImage snapshot of canvas underneath
        self._bg_snapshot = bg_snapshot
        # v4.1.22.1: doc-body flag — alters overflow visual + emits flow signals
        self._is_doc_body = bool(is_doc_body)
        # v4.1.23.18: set True by the canvas when this page's body content
        # continues on the next page (a non-last page). When True the editor
        # suppresses the trailing virtual line so the caret cannot rest in
        # the bottom margin; the page boundary belongs to the next page.
        self._continues = False
        # v4.1.23.57: set True by _push_undo on any content/format edit; the
        # host reads it to mark the document modified (drives the save prompt).
        self._edited = False
        # v4.1.23.58: document-level body undo/redo hooks. For a doc body the
        # editor delegates undo/redo and edit-checkpoints to the host window so
        # the history spans pages (the per-editor stacks below only cover one
        # page and are lost on a page hop). Plain text boxes keep using the
        # local stacks. Set by the canvas in _start_inline for body editors.
        self._host_undo = None      # callable() -> document-level undo
        self._host_redo = None      # callable() -> document-level redo
        self._host_save = None      # callable() -> document-level Save (Ctrl+S)
        self._host_save_as = None   # callable() -> document-level Save As (Ctrl+Shift+S)
        self._on_body_edit = None   # callable() -> checkpoint before an edit burst
        # Idle-overflow auto-commit timer (doc body only)
        self._idle_overflow_timer = QTimer(self)
        self._idle_overflow_timer.setSingleShot(True)
        self._idle_overflow_timer.timeout.connect(self._on_idle_overflow)

        # If textbox has no runs, synthesize one from plain text
        if not textbox.runs:
            self._runs = [TextRun(
                text=textbox.text or "",
                font_family=textbox.style.font_family,
                font_size=textbox.style.font_size,
                bold=textbox.style.bold,
                italic=textbox.style.italic,
                color=textbox.style.color,
            )]
        else:
            self._runs = _clone_runs(textbox.runs)

        # Cursor state
        self._cursor: int = _runs_total_len(self._runs)
        self._anchor: Optional[int] = None    # selection anchor (None = no selection)
        # Format of the next typed character (cursor format)
        self._pending_format: Optional[dict] = None
        # v4.1.23.50: alignment to apply to the NEXT typed text. set_alignment
        # on an EMPTY paragraph can only record the choice in the (index-based,
        # shift-prone) map, not on a run — so typing afterwards rendered left
        # until a reflow re-split the runs. This carries the alignment onto the
        # runs as you type. Cleared on caret navigation / click like
        # _pending_format.
        self._pending_alignment: Optional[str] = None

        # Undo/Redo
        self._undo_stack: List[_UndoEntry] = []
        self._redo_stack: List[_UndoEntry] = []
        self._undo_limit = 1000

        # Blink
        self._cursor_visible = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(QApplication.cursorFlashTime() // 2 or 500)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start()

        # Cached layout
        self._layout: Optional[Layout] = None
        # Cached background pixmap (full-resolution PIL render)
        self._bg_pixmap: Optional[QPixmap] = None
        self._needs_render = True
        self._committing = False    # v4.1.16.2: re-entrancy guard

        # Widget setup
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        # v4.1.17.2: keep the widget transparent so when the textbox has no
        # fill, the canvas (and underlying subdoc / page background) shows
        # through correctly. Without WA_TranslucentBackground the dark Qt
        # palette colour painted itself behind any alpha-zero pixels.
        # v4.1.20.5: also set WA_NoSystemBackground and override the palette
        # so QGraphicsProxyWidget can't paint a fallback fill underneath the
        # widget during rendering.
        # v4.1.20.6: THE actual cause of the yellow cast was the global QSS
        # `QMainWindow,QWidget{ background:#1e1e2e }` rule — Qt's stylesheet
        # engine painted that dark purple under the widget *before* the
        # widget had a chance to paint its own transparent bg. Turning off
        # WA_StyledBackground tells the style engine to skip the bg pass
        # entirely for this widget, leaving only our own paintEvent in
        # control. Belt-and-braces: also override the QSS at instance level
        # with a class-specific selector so any inherited rules are bypassed.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAutoFillBackground(False)
        try:
            from PyQt6.QtGui import QPalette as _QP
            pal = self.palette()
            pal.setColor(self.backgroundRole(), Qt.GlobalColor.transparent)
            pal.setColor(_QP.ColorRole.Window, Qt.GlobalColor.transparent)
            pal.setColor(_QP.ColorRole.Base,   Qt.GlobalColor.transparent)
            self.setPalette(pal)
        except Exception:
            pass
        # v4.1.18.1: explicit per-widget stylesheet overrides the global QSS
        # `QWidget { background: #1e1e2e }` rule that would otherwise paint
        # a dark navy backdrop behind the rendered text. (Without this the
        # widget showed a coloured rectangle while editing — the famous
        # "tmavé/žluté pozadí" regression.)
        # v4.1.20.6: class-specific selector defeats global QSS inheritance.
        # Use rgba(0,0,0,0) which is unambiguously transparent.
        self.setStyleSheet(
            "EdofTextEditor{background:rgba(0,0,0,0);background-color:rgba(0,0,0,0);border:none;}"
        )
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.IBeamCursor)

        self._size_to_box()

    # ── Geometry ──────────────────────────────────────────────────────────────
    def _size_to_box(self):
        """Set widget size to the textbox dimensions in scene pixels."""
        w_px = max(1, int(round(mm_to_px(self.tb.transform.width,  self.dpi))))
        h_px = max(1, int(round(mm_to_px(self.tb.transform.height, self.dpi))))
        self.setFixedSize(w_px, h_px)

    # ── Public commit/cancel ──────────────────────────────────────────────────
    def commit_to_textbox(self):
        """Write back the edited runs to the original TextBox."""
        if self._committing:
            return
        self._committing = True
        runs = _normalize_runs(self._runs)
        # Keep a plain-text mirror
        self.tb.runs = runs
        self.tb.text = _runs_text(runs)
        self.committed.emit(self.tb)

    def sync_to_tb_silent(self):
        """v4.1.22.8: write current edited runs back to the parent textbox
        WITHOUT emitting the committed signal. Used by the canvas idle
        handler to make the body's data current before running balance —
        balance reads from tb.runs, so the editor's in-flight edits must
        be visible there. After balance modifies tb.runs (across pages),
        the canvas calls refresh_from_tb() to pull the new content back
        into the editor without tearing it down.

        v4.1.22.9: also signal that the editor's snapshot is now stale —
        the canvas will set _inline_snapshot=None so that a subsequent
        teardown doesn't roll the data back to the pre-edit state.

        v4.1.23.2: also REPLACE self._runs with the normalized list so
        the editor doesn't accumulate run fragments over time. Paginate
        splits content into many one-character TextRuns when emitting
        flat runs from paragraphs; each idle cycle's refresh_from_tb
        would pull those back into self._runs, and without this line
        they would never coalesce. The accompanying _normalize_runs
        fix ensures normalization itself doesn't mutate input runs."""
        runs = _normalize_runs(self._runs)
        self._runs = runs
        self.tb.runs = runs
        self.tb.text = _runs_text(runs)
        # The canvas owns _inline_snapshot, not the editor. The canvas's
        # idle handler clears it after calling this.

    def refresh_from_tb(self, new_cursor: Optional[int] = None):
        """v4.1.22.8: reload runs from the parent textbox after the canvas
        has modified it (typically due to a balance pass that pulled or
        pushed content). Cursor is clamped to the new content length;
        pass `new_cursor` to override (e.g. when the caret should jump to
        a specific position after backflow brought paragraphs in)."""
        try:
            from edof.engine.debug_log import log as _dlog
            _dlog("editor.refresh_from_tb",
                   new_cursor=new_cursor,
                   old_cursor=self._cursor,
                   tb_text=(self.tb.text or "")[:60])
        except Exception: pass
        from edof.format.styles import TextRun
        new_runs = [copy.deepcopy(r) for r in (self.tb.runs or [])]
        if not new_runs:
            new_runs = [TextRun(text="")]
        self._runs = new_runs
        total = _runs_total_len(self._runs)
        if new_cursor is not None:
            self._cursor = max(0, min(total, int(new_cursor)))
        else:
            self._cursor = max(0, min(total, self._cursor))
        self._anchor = None
        self._invalidate()

    def cancel(self):
        if self._committing:
            return
        self._committing = True
        self.cancelled.emit(self.tb)

    # ── Selection / cursor helpers ────────────────────────────────────────────
    def _has_selection(self) -> bool:
        return self._anchor is not None and self._anchor != self._cursor

    def _sel_range(self) -> Tuple[int, int]:
        # v4.1.16.2: don't use `or` because 0 is falsy in Python; that
        # bug made selections starting at index 0 collapse to (cursor, cursor).
        a = self._anchor if self._anchor is not None else self._cursor
        b = self._cursor
        return (min(a, b), max(a, b))

    def _clear_selection(self):
        self._anchor = None

    def _begin_selection_if_needed(self):
        if self._anchor is None:
            self._anchor = self._cursor

    # ── Edit operations ───────────────────────────────────────────────────────
    def _push_undo(self, label: str = ""):
        # v4.1.23.57: any undoable action means the body content/formatting was
        # edited. Record it so the host can mark the document modified even when
        # the edit does not restructure pagination (e.g. typing on a single
        # line). Without this, closing right after typing on the first line did
        # not prompt to save because _modified was never set.
        self._edited = True
        # v4.1.23.59: notify the host on EVERY body edit (including coalesced
        # keystrokes) so it can debounce-commit the burst as one step in the
        # unified document history. Done before the coalescing early-return so
        # fast continuous typing still registers.
        if getattr(self, '_is_doc_body', False):
            cb = getattr(self, '_on_body_edit', None)
            if cb:
                try: cb()
                except Exception: pass
        # v4.1.23.38: coalesce a run of single-character typing into ONE undo
        # step (Word-style) so Ctrl+Z doesn't crawl back letter by letter and
        # the history isn't exhausted by a paragraph of text. A new burst
        # starts after any non-"type" action.
        import time as _t
        now = _t.monotonic()
        if (label == "type" and self._undo_stack
                and self._undo_stack[-1].label == "type"
                and (now - getattr(self, '_last_undo_t', 0)) < 1.5):
            self._last_undo_t = now
            self._redo_stack.clear()
            return
        self._last_undo_t = now
        self._undo_stack.append(_UndoEntry(
            runs=_clone_runs(self._runs),
            cursor=self._cursor,
            sel_anchor=self._anchor,
            label=label,
        ))
        if len(self._undo_stack) > self._undo_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        # v4.1.23.58: doc body → document-level undo (spans pages).
        if getattr(self, '_is_doc_body', False) and self._host_undo is not None:
            try: self._host_undo(); return
            except Exception: pass
        if not self._undo_stack:
            return
        # Snapshot current state for redo
        self._redo_stack.append(_UndoEntry(
            runs=_clone_runs(self._runs),
            cursor=self._cursor, sel_anchor=self._anchor))
        e = self._undo_stack.pop()
        self._runs = _clone_runs(e.runs)
        self._cursor = e.cursor
        self._anchor = e.sel_anchor
        self._invalidate()

    def redo(self):
        # v4.1.23.58: doc body → document-level redo (spans pages).
        if getattr(self, '_is_doc_body', False) and self._host_redo is not None:
            try: self._host_redo(); return
            except Exception: pass
        if not self._redo_stack:
            return
        self._undo_stack.append(_UndoEntry(
            runs=_clone_runs(self._runs),
            cursor=self._cursor, sel_anchor=self._anchor))
        e = self._redo_stack.pop()
        self._runs = _clone_runs(e.runs)
        self._cursor = e.cursor
        self._anchor = e.sel_anchor
        self._invalidate()

    def _delete_range(self, start: int, end: int) -> None:
        """Delete chars in [start, end)."""
        if start >= end:
            return
        # v4.1.23.1-debug: log every delete
        try:
            from edof.engine.debug_log import log as _dlog
            full = "".join(r.text or "" for r in self._runs)
            _dlog("editor._delete_range",
                   start=start, end=end,
                   deleted=repr(full[start:end]),
                   cursor_before=self._cursor,
                   text_before_len=len(full))
        except Exception: pass
        # Split runs at boundaries, then drop runs fully inside
        # Find run_idx + offset for start and end
        # Easier approach: rebuild flat text + per-char run map, then re-bucket
        # by run identity.
        new_runs = []
        flat_text = []
        flat_fmt: List[int] = []
        abs_i = 0
        for r_idx, r in enumerate(self._runs):
            for ch in (r.text or ""):
                if not (start <= abs_i < end):
                    flat_text.append(ch)
                    flat_fmt.append(r_idx)
                abs_i += 1
        # Reassemble: group consecutive chars with same source run
        if not flat_text:
            # become single empty run, formatted by the run that was at start
            src = self._runs[min(len(self._runs)-1, max(0, _abs_to_run(self._runs, start)[0]))]
            new_run = _clone_runs([src])[0]
            new_run.text = ""
            self._runs = [new_run]
            return
        last_r = flat_fmt[0]
        buf = []
        for ch, r in zip(flat_text, flat_fmt):
            if r != last_r:
                src = self._runs[last_r]
                new = _clone_runs([src])[0]
                new.text = "".join(buf)
                new_runs.append(new)
                buf = []
                last_r = r
            buf.append(ch)
        if buf:
            src = self._runs[last_r]
            new = _clone_runs([src])[0]
            new.text = "".join(buf)
            new_runs.append(new)
        self._runs = new_runs

    def _insert_text(self, text: str) -> None:
        """Insert text at the cursor, applying _pending_format if set,
        otherwise inheriting format from the run at the cursor."""
        if not text:
            return
        # v4.1.23.1-debug: log the insertion
        try:
            from edof.engine.debug_log import log as _dlog
            _dlog("editor._insert_text",
                   text=repr(text),
                   cursor_before=self._cursor,
                   sel=self._has_selection(),
                   text_before_len=len("".join(r.text or "" for r in self._runs)))
        except Exception: pass
        # If there's a selection, delete it first
        if self._has_selection():
            a, b = self._sel_range()
            self._delete_range(a, b)
            self._cursor = a
            self._clear_selection()
        # Find insertion run
        r_idx, off = _abs_to_run(self._runs, self._cursor)
        if not self._runs:
            base = TextRun(text="", font_family="Arial", font_size=4.233)  # 12pt in mm
            self._runs.append(base)
        # If pending format differs from the run at cursor, split + insert new run
        base = self._runs[r_idx] if r_idx < len(self._runs) else self._runs[-1]
        base_fmt = self._fmt_dict_from_run(base)
        target_fmt = dict(self._pending_format) if self._pending_format else dict(base_fmt)
        # v4.1.23.50: a pending alignment (from set_alignment on an empty
        # paragraph) overrides so the typed run carries it.
        if self._pending_alignment is not None:
            target_fmt['alignment'] = self._pending_alignment
        if target_fmt == base_fmt:
            # Insert directly into base run
            base.text = (base.text or "")[:off] + text + (base.text or "")[off:]
        else:
            # Split base run, insert new run with target_fmt
            new_run = _clone_runs([base])[0]
            new_run.text = text
            for k, v in target_fmt.items():
                setattr(new_run, k, v)
            right_idx = _split_run_at(self._runs, r_idx, off)
            self._runs.insert(right_idx, new_run)
            # v4.1.23.33: do NOT clear _pending_format here. A set size/font/
            # spacing must persist for ALL subsequently typed characters until
            # the user changes it or moves the caret — previously it was
            # cleared after the first char, so only the first letter took the
            # new size and the rest fell back to the run at the caret. Pending
            # is cleared on caret navigation (click / arrows / Home / End).
        self._cursor += len(text)
        # v4.1.23.22: collapse any anchor after inserting. Previously the
        # anchor set by a click (anchor == cursor, so no visible selection)
        # was left behind; once the cursor advanced past it the editor
        # reported a 1-char selection, and the NEXT typed character replaced
        # the one just typed (e.g. "fc" became "c"). Clearing the anchor here
        # keeps the caret collapsed at the new position.
        self._anchor = None
        self._runs = _normalize_runs(self._runs)

    def _fmt_dict_from_run(self, run) -> dict:
        return {
            'font_family':   run.font_family,
            'font_size':     run.font_size,
            'bold':          bool(getattr(run, 'bold', False)),
            'italic':        bool(getattr(run, 'italic', False)),
            'underline':     bool(getattr(run, 'underline', False)),
            'strikethrough': bool(getattr(run, 'strikethrough', False)),
            'color':         run.color,
            'background':    getattr(run, 'background', None),
            'line_height':   getattr(run, 'line_height', None),
            'letter_spacing': getattr(run, 'letter_spacing', None),
            'alignment':     getattr(run, 'alignment', None),
        }

    def _apply_format_to_selection(self, **attrs):
        """Apply formatting attributes to the current selection or set as
        pending format for next insert if no selection.

        Implementation note (v4.1.16.2): we flatten the runs to per-char
        data, override format for the selection range, then rebuild runs.
        This avoids the index-drift bugs that came with split-based
        approaches when selection boundaries fell at run edges.
        """
        if not self._has_selection():
            # No selection — affect future characters. v4.1.23.33: accumulate
            # onto any existing pending format so setting several attributes in
            # a row (e.g. size then bold then spacing) keeps them all, instead
            # of each one resetting to the run's format and dropping the rest.
            if self._pending_format:
                cur_fmt = dict(self._pending_format)
            else:
                r_idx, off = _abs_to_run(self._runs, max(0, self._cursor - 1))
                base = self._runs[r_idx] if r_idx < len(self._runs) else (self._runs[-1] if self._runs else None)
                if base is None:
                    return
                cur_fmt = self._fmt_dict_from_run(base)
            cur_fmt.update(attrs)
            self._pending_format = cur_fmt
            return
        self._push_undo("format")
        a, b = self._sel_range()
        # Flatten to char list with source run formatting
        items = []  # list of (ch, src_run_idx, abs_idx)
        abs_i = 0
        for r_idx, r in enumerate(self._runs):
            for ch in (r.text or ""):
                items.append((ch, r_idx, abs_i))
                abs_i += 1
        # Walk and rebuild
        new_runs = []
        cur_fmt = None
        cur_buf = []
        for ch, src_r_idx, idx in items:
            src_run = self._runs[src_r_idx]
            fmt = self._fmt_dict_from_run(src_run)
            if a <= idx < b:
                fmt.update(attrs)
            if fmt != cur_fmt:
                if cur_buf:
                    new_runs.append(self._make_run("".join(cur_buf), cur_fmt))
                cur_buf = [ch]
                cur_fmt = fmt
            else:
                cur_buf.append(ch)
        if cur_buf:
            new_runs.append(self._make_run("".join(cur_buf), cur_fmt))
        if new_runs:
            self._runs = _normalize_runs(new_runs)

    def _make_run(self, text: str, fmt: dict):
        """Build a TextRun from a format dict."""
        return TextRun(
            text=text,
            font_family=fmt.get('font_family'),
            font_size=fmt.get('font_size'),
            bold=fmt.get('bold'),
            italic=fmt.get('italic'),
            underline=fmt.get('underline'),
            strikethrough=fmt.get('strikethrough'),
            color=fmt.get('color'),
            background=fmt.get('background'),
            line_height=fmt.get('line_height'),
            letter_spacing=fmt.get('letter_spacing'),
            alignment=fmt.get('alignment'),
        )

    def toggle_bold(self):
        sel = self._current_format_attr('bold')
        self._apply_format_to_selection(bold=not sel)
        self._invalidate()

    def toggle_italic(self):
        sel = self._current_format_attr('italic')
        self._apply_format_to_selection(italic=not sel)
        self._invalidate()

    def toggle_underline(self):
        sel = self._current_format_attr('underline')
        self._apply_format_to_selection(underline=not sel)
        self._invalidate()

    def toggle_strikethrough(self):
        sel = self._current_format_attr('strikethrough')
        self._apply_format_to_selection(strikethrough=not sel)
        self._invalidate()

    def set_alignment(self, align: str):
        """Set horizontal alignment for the paragraph containing the cursor
        (or all paragraphs covered by the current selection).

        v4.1.21: writes to TextBox.paragraph_alignments (per-paragraph map)
        rather than the textbox-level style. Paragraphs not in the map
        still inherit from style.alignment as the default. This lets the
        user mix alignments within one body in document mode (Word-style).

        align in {'left','center','right','justify','justify_full'}."""
        if align not in ('left', 'center', 'right', 'justify', 'justify_full'):
            return
        self._push_undo("align")
        # Compute paragraph index(es) affected
        text = _runs_text(self._runs)
        if self._has_selection():
            a, b = self._sel_range()
            a = max(0, min(len(text), a))
            b = max(0, min(len(text), b))
            if a > b: a, b = b, a
            start_para = text[:a].count('\n')
            end_para   = text[:b].count('\n')
            # v4.1.21.2: when the selection END is right after a '\n', the
            # cursor is conceptually at the start of the next paragraph but
            # the user's selection effectively ended at the newline itself —
            # they meant to align only up to and including the previous
            # paragraph. Without this adjustment, selecting a whole line
            # (Home → Shift+End → Shift+Down, or triple-click) extends the
            # alignment into the paragraph below as well.
            if b > a and b > 0 and text[b-1] == '\n':
                end_para = max(start_para, end_para - 1)
        else:
            start_para = text[:self._cursor].count('\n')
            end_para   = start_para
        # Ensure dict attribute exists on the textbox
        if not hasattr(self.tb, 'paragraph_alignments') or self.tb.paragraph_alignments is None:
            self.tb.paragraph_alignments = {}
        for idx in range(start_para, end_para + 1):
            self.tb.paragraph_alignments[str(idx)] = align
        # v4.1.23.35: ALSO stamp the alignment onto the RUNS of those
        # paragraphs. Runs survive the pagination round-trip and copy/paste,
        # so the layout can recover the alignment even after content reflows
        # across pages (the paragraph_alignments map is per-page-local and was
        # lost when per-page bodies were rebuilt). The layout prefers this
        # run-carried alignment over the map.
        try:
            paras = text.split('\n')
            offs = []; acc = 0
            for p in paras:
                offs.append(acc); acc += len(p) + 1
            if 0 <= start_para < len(offs) and end_para < len(offs):
                pa = offs[start_para]
                pb = offs[end_para] + len(paras[end_para])
                self._apply_attr_to_range(pa, pb, alignment=align)
        except Exception:
            pass
        # v4.1.21.1: do NOT update style.alignment here.
        # style.alignment is the DEFAULT for any paragraph not explicitly
        # listed in paragraph_alignments. Overwriting it when the user
        # aligns paragraph 0 would also re-align every other paragraph
        # that's still using the default, causing the "two lines change
        # when I meant one" bug.
        # v4.1.23.50: remember the choice so text typed right afterwards (even
        # into an empty paragraph that had no run to stamp) lands aligned.
        self._pending_alignment = align
        self._invalidate()

    def _apply_attr_to_range(self, a: int, b: int, **attrs):
        """v4.1.23.35: set run attributes on the character range [a, b),
        splitting/merging runs as needed (used for paragraph-level attributes
        like alignment that must be carried on the runs)."""
        if a >= b:
            return
        items = []
        for r_idx, r in enumerate(self._runs):
            for ch in (r.text or ""):
                items.append((ch, r_idx))
        new_runs = []; cur_fmt = None; cur_buf = []
        for idx, (ch, src_r_idx) in enumerate(items):
            fmt = self._fmt_dict_from_run(self._runs[src_r_idx])
            if a <= idx < b:
                fmt.update(attrs)
            if fmt != cur_fmt:
                if cur_buf:
                    new_runs.append(self._make_run("".join(cur_buf), cur_fmt))
                cur_buf = [ch]; cur_fmt = fmt
            else:
                cur_buf.append(ch)
        if cur_buf:
            new_runs.append(self._make_run("".join(cur_buf), cur_fmt))
        if new_runs:
            self._runs = _normalize_runs(new_runs)

    def set_vertical_alignment(self, valign: str):
        if valign not in ('top', 'middle', 'bottom'):
            return
        self._push_undo("valign")
        self.tb.style.vertical_align = valign
        self._invalidate()

    def set_font_family(self, family: str):
        self._apply_format_to_selection(font_family=family)
        self._invalidate()

    def set_font_size_mm(self, mm: float):
        """v4.1.17: primary font-size setter. mm is the canonical unit."""
        self._apply_format_to_selection(font_size=max(0.1, float(mm)))
        self._invalidate()

    def set_font_size_pt(self, pt: float):
        """Legacy/typography accessor — converts pt → mm internally."""
        mm = float(pt) * 25.4 / 72.0
        self.set_font_size_mm(mm)

    def set_line_height(self, mult: float):
        """v4.1.23.33: per-run line spacing multiplier (selection or pending)."""
        self._apply_format_to_selection(line_height=max(0.1, float(mult)))
        self._invalidate()

    def set_letter_spacing_mm(self, mm: float):
        """v4.1.23.33: per-run letter spacing in mm (selection or pending)."""
        self._apply_format_to_selection(letter_spacing=float(mm))
        self._invalidate()

    def set_color(self, rgba):
        self._apply_format_to_selection(color=rgba)
        self._invalidate()

    def set_background(self, rgba):
        """v4.1.23.38: per-run text background (highlight) colour. Pass None
        to clear the highlight."""
        self._apply_format_to_selection(background=rgba)
        self._invalidate()

    def _current_format_attr(self, attr: str):
        """Return the value of attr at the cursor / in the selection
        (or pending format)."""
        if self._pending_format and attr in self._pending_format:
            return self._pending_format[attr]
        if self._has_selection():
            a, b = self._sel_range()
            r_idx, _ = _abs_to_run(self._runs, a)
            r_b, _ = _abs_to_run(self._runs, max(a, b - 1))
            # Use first run's value as the "current" indicator
            return getattr(self._runs[r_idx], attr, None)
        r_idx, off = _abs_to_run(self._runs, max(0, self._cursor - 1))
        if r_idx < len(self._runs):
            return getattr(self._runs[r_idx], attr, None)
        return None

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _on_idle_overflow(self):
        """v4.1.22.7: fires periodically (150 ms after the last keystroke
        in a doc body, regardless of overflow). Always emit — the canvas
        decides whether commit+balance would change anything. This is
        what enables backflow: after the user deletes content on page 1,
        idle fires, canvas runs the balance pass which pulls forward
        from page 2."""
        if not getattr(self, '_is_doc_body', False):
            return
        try:
            from edof.engine.debug_log import log as _dlog
            _dlog("editor.idle_fired",
                   cursor=self._cursor,
                   text=("".join(r.text or "" for r in self._runs))[:80])
        except Exception: pass
        try: self.idle_overflow_reached.emit(self.tb)
        except Exception: pass

    def _invalidate(self):
        self._needs_render = True
        self._cursor_visible = True
        # v4.2.11.37: every Qt access below can hit a deleted C++ object when a
        # stale Python reference calls in after the widget was torn down (page
        # hop / repagination rebuilds the editor). A RuntimeError escaping a
        # slot aborts the whole app in PyQt6, so guard the Qt parts.
        try:
            self._blink_timer.stop()
            self._blink_timer.start()
            # v4.1.16.3: debounce repaint — PIL render is expensive; batch
            # rapid keystrokes by deferring update() ~20ms after the last
            # invalidation so we don't render 60+ times for a fast typist.
            if not hasattr(self, '_render_timer') or self._render_timer is None:
                self._render_timer = QTimer(self)
                self._render_timer.setSingleShot(True)
                self._render_timer.timeout.connect(self.update)
            self._render_timer.stop()
            self._render_timer.start(20)
            # Also issue an immediate cursor-only repaint so the cursor
            # follows keystrokes without 20ms lag (cursor draws on top of
            # the cached pixmap, doesn't need re-render).
            super().update()
        except RuntimeError:
            return   # underlying widget already destroyed -- nothing to paint
        # v4.1.22.2: tell the canvas the cursor may have moved
        try: self.cursor_changed.emit()
        except Exception: pass

    def _toggle_blink(self):
        self._cursor_visible = not self._cursor_visible
        # Cursor blink doesn't need a re-render of the PIL pixmap.
        try:
            super().update()
        except RuntimeError:
            pass

    def selectAll(self):
        """Select all text (compatibility with existing editor.py code)."""
        self._anchor = 0
        self._cursor = _runs_total_len(self._runs)
        self._invalidate()

    # ── Word navigation (v4.1.16.5) ──────────────────────────────────────────
    @staticmethod
    def _is_word_char(ch: str) -> bool:
        """A char counts as 'word' if it's alphanumeric or underscore."""
        return ch.isalnum() or ch == '_'

    def _word_left(self, idx: int) -> int:
        """Position of the previous word boundary (Ctrl+Left). Skips any
        whitespace immediately to the left, then any word chars."""
        text = _runs_text(self._runs)
        i = max(0, min(len(text), idx)) - 1
        # Skip non-word chars (whitespace, punctuation) backwards
        while i >= 0 and not self._is_word_char(text[i]):
            i -= 1
        # Then skip word chars backwards
        while i >= 0 and self._is_word_char(text[i]):
            i -= 1
        return i + 1

    def _word_right(self, idx: int) -> int:
        """Position of the next word boundary (Ctrl+Right)."""
        text = _runs_text(self._runs)
        n = len(text)
        i = max(0, min(n, idx))
        # Skip word chars forward
        while i < n and self._is_word_char(text[i]):
            i += 1
        # Then skip non-word chars forward
        while i < n and not self._is_word_char(text[i]):
            i += 1
        return i

    def _ensure_render(self):
        if not self._needs_render and self._bg_pixmap is not None:
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        try:
            # v4.1.19.2 / v4.1.20.4: choose the inline editor's background:
            #   1. textbox.fill.color, if set → explicit user choice
            #   2. fully transparent (0, 0, 0, 0) → otherwise
            # Previously the editor inherited the page background when the
            # textbox had no fill set. That looked fine for an isolated
            # textbox on a white page, but in document mode the body textbox
            # spans the whole page area — and an opaque page-bg paint covered
            # any other objects (shapes, images, tables) that the user
            # inserted underneath. Transparent-by-default lets the canvas's
            # already-rendered page+objects show through through the proxy.
            bg = (0, 0, 0, 0)
            fill_c = getattr(self.tb.fill, 'color', None) if hasattr(self.tb, 'fill') and self.tb.fill else None
            if fill_c and len(fill_c) >= 3:
                alpha = fill_c[3] if len(fill_c) >= 4 else 255
                bg = tuple(fill_c[:3]) + (int(alpha),)
            # v4.1.16.7: non-uniform glyph scaling — render text at natural
            # size, resize buffer non-uniformly. Same as canvas renderer.
            gsx = float(getattr(self.tb.style, 'glyph_scale_x', 1.0) or 1.0)
            gsy = float(getattr(self.tb.style, 'glyph_scale_y', 1.0) or 1.0)
            deform = abs(gsx - 1.0) > 0.005 or abs(gsy - 1.0) > 0.005
            # Auto-shrink scale (computed at NATURAL size)
            from edof.engine.text_engine import find_fitting_scale
            from edof.engine.transform import mm_to_px as _mtp
            from io import BytesIO
            # v4.1.23.9: compute padding EXACTLY like the canvas static
            # renderer (edof/engine/renderer.py) — float mm_to_px, with
            # int() applied only at the find_fitting_scale call. The old
            # code int()-cast the padding first (int(7.559)=7 instead of
            # 7.559), making the inline inner width ~2 px wider than the
            # canvas. That gave auto-fill a larger scale during editing,
            # so text looked slightly bigger and the last glyph wrapped
            # to a new line. Keeping the math identical fixes the drift.
            pad_mm = float(getattr(self.tb.style, 'padding', 1.0))
            pad_px = _mtp(pad_mm, self.dpi)

            # v4.1.23.9: the widget pixel size (w, h) is an INTEGER
            # (Qt requires int geometry, set via round(mm_to_px(...))).
            # But the canvas static renderer lays text out in the
            # UNROUNDED float box width (w_px = mm_to_px(t.width, dpi),
            # e.g. 680.31). Laying out in the rounded int (680.0) makes
            # the available line width ~0.3 px narrower, so a word/char
            # that fit on the canvas wraps to the next line in the
            # editor. Use the exact float box dims for layout + fit-scale
            # so wrapping matches the canvas pixel-for-pixel. The render
            # buffer stays at the int widget size (the sub-pixel glyph at
            # the right edge clips harmlessly, exactly as on the canvas).
            box_w_px = _mtp(self.tb.transform.width,  self.dpi)
            box_h_px = _mtp(self.tb.transform.height, self.dpi)

            if deform:
                nat_w = max(1, int(round(box_w_px / gsx)))
                nat_h = max(1, int(round(box_h_px / gsy)))
                inner_w_px = max(1, int(nat_w - 2 * pad_px))
                inner_h_px = max(1, int(nat_h - 2 * pad_px))
                scale = 1.0
                if getattr(self.tb.style, 'auto_shrink', False) or \
                   getattr(self.tb.style, 'auto_fill', False):
                    try:
                        scale = find_fitting_scale(
                            self._runs, self.tb.style, inner_w_px, inner_h_px,
                            dpi=self.dpi, wrap=self.tb.style.wrap,
                            shrink_only=self.tb.style.auto_shrink
                                        and not self.tb.style.auto_fill)
                    except Exception:
                        scale = 1.0
                # Render at natural size
                nat_img = Image.new("RGBA", (nat_w, nat_h), bg)
                nat_draw = ImageDraw.Draw(nat_img)
                pa = getattr(self.tb, 'paragraph_alignments', None) or {}
                layout = layout_runs(
                    self._runs, self.tb.style,
                    0.0, 0.0, float(nat_w), float(nat_h), self.dpi,
                    scale=scale, paragraph_alignments=pa,
                    add_trailing_virtual=not getattr(self, "_continues", False))
                render_layout_onto(nat_draw, layout, self._runs, self.tb.style,
                                   self.dpi, scale=scale)
                # Non-uniform resize
                img = nat_img.resize((w, h), Image.LANCZOS)
                # Layout for hit-testing must reflect the rendered space.
                # Use a scaled layout: multiply x by gsx, y by gsy.
                self._layout = _scale_layout(layout, gsx, gsy)
            else:
                img = Image.new("RGBA", (w, h), bg)
                draw = ImageDraw.Draw(img)
                inner_w_px = max(1, int(box_w_px - 2 * pad_px))
                inner_h_px = max(1, int(box_h_px - 2 * pad_px))
                scale = 1.0
                if getattr(self.tb.style, 'auto_shrink', False) or \
                   getattr(self.tb.style, 'auto_fill', False):
                    try:
                        scale = find_fitting_scale(
                            self._runs, self.tb.style, inner_w_px, inner_h_px,
                            dpi=self.dpi, wrap=self.tb.style.wrap,
                            shrink_only=self.tb.style.auto_shrink
                                        and not self.tb.style.auto_fill)
                    except Exception:
                        scale = 1.0
                layout = layout_runs(
                    self._runs, self.tb.style,
                    0.0, 0.0, box_w_px, box_h_px, self.dpi, scale=scale,
                    paragraph_alignments=getattr(self.tb, 'paragraph_alignments', None) or {},
                    add_trailing_virtual=not getattr(self, "_continues", False))
                self._layout = layout
                render_layout_onto(draw, layout, self._runs, self.tb.style,
                                   self.dpi, scale=scale)
            # Overflow indicator
            is_overflow = (self._layout is not None
                            and (self._layout.overflow_v or self._layout.overflow_h))
            # v4.1.22.1: in doc mode the body textbox flows overflow to the
            # next page automatically, so a red border would be misleading
            # — the user hasn't done anything wrong, it's just where the
            # page break naturally falls. Suppress for doc body.
            if is_overflow and not self._is_doc_body:
                draw2 = ImageDraw.Draw(img)
                for k in range(2):
                    draw2.rectangle([k, k, w - 1 - k, h - 1 - k],
                                   outline=(220, 50, 50, 255))
            # v4.1.20.1: emit overflow_changed when the state flips so the
            # canvas can show a hint ("Press Ctrl+Enter for new page" in
            # doc mode). Only emit on transitions to avoid spamming.
            prev_overflow = getattr(self, '_was_overflow', False)
            if is_overflow != prev_overflow:
                self._was_overflow = is_overflow
                try: self.overflow_changed.emit(is_overflow)
                except Exception: pass
            # v4.1.23.31: react to overflow IMMEDIATELY. Previously this
            # restarted an 80 ms timer on every render; while typing fast each
            # keystroke reset it, so the reflow never fired until the user
            # paused and several lines piled up BELOW the bottom margin (and
            # then jumped all at once). Now: while overflowing, fire as soon as
            # possible and do NOT keep pushing the deadline forward — start the
            # timer only if it is not already pending. The page break then
            # happens the moment a line crosses the margin, so no line is ever
            # left hanging below it. When NOT overflowing we keep a short
            # debounce so a delete can pull content back from the next page
            # once the user settles.
            if self._is_doc_body:
                try:
                    if is_overflow:
                        if not self._idle_overflow_timer.isActive():
                            self._idle_overflow_timer.start(0)
                    else:
                        self._idle_overflow_timer.start(120)
                except Exception: pass
            elif self._idle_overflow_timer.isActive():
                self._idle_overflow_timer.stop()
            # v4.1.19.1: convert PIL → QImage directly with explicit ARGB32
            # premultiplied format. Going through PNG encode/decode used to
            # work but on some Qt builds produced a yellow/dark cast around
            # antialiased glyphs because the loader picked a non-premultiplied
            # ARGB32 format and Qt compositing then treated the (255,255,255,0)
            # background pixels as visible. Direct conversion keeps alpha
            # semantics consistent end-to-end.
            try:
                raw = img.tobytes("raw", "RGBA")
                qimg = QImage(raw, img.width, img.height, img.width * 4,
                              QImage.Format.Format_RGBA8888).copy()
                # Use premultiplied internally for correct alpha composite
                qimg = qimg.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                self._bg_pixmap = QPixmap.fromImage(qimg)
            except Exception:
                # Fallback: PNG roundtrip (original path)
                buf = BytesIO()
                img.save(buf, "PNG")
                qimg = QImage()
                if qimg.loadFromData(buf.getvalue()):
                    self._bg_pixmap = QPixmap.fromImage(qimg)
                else:
                    self._bg_pixmap = None
            self._needs_render = False
        except Exception:
            import traceback, sys
            traceback.print_exc(file=sys.stderr)
            self._bg_pixmap = None
            self._layout = None
            self._needs_render = False

    def paintEvent(self, ev):
        try:
            self._ensure_render()
            p = QPainter(self)
            # v4.1.20.7: opaque snapshot first (replaces Qt transparency).
            # When the canvas pixmap snapshot is available, scale it to the
            # editor's current widget size and draw it as the bg. The text
            # bg pixmap (which still has transparent gaps where there's no
            # text) is then composited on top.
            if self._bg_snapshot is not None:
                try:
                    if (self._bg_snapshot.width() != self.width()
                        or self._bg_snapshot.height() != self.height()):
                        scaled = self._bg_snapshot.scaled(
                            self.width(), self.height(),
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                    else:
                        scaled = self._bg_snapshot
                    p.drawImage(0, 0, scaled)
                except Exception:
                    pass
            if self._bg_pixmap is not None:
                p.drawPixmap(0, 0, self._bg_pixmap)
            # v4.1.17.2: no fallback fill — the widget is WA_TranslucentBackground
            # so when the pixmap isn't ready yet (first paint), the underlying
            # canvas shows through. Previously we filled with opaque white which
            # caused dark/incorrect backdrop in subdocs and over coloured pages.
            # Selection overlay
            if self._has_selection() and self._layout is not None:
                a, b = self._sel_range()
                rects = self._layout.selection_rects(a, b)
                sel_color = QColor(0, 120, 212, 90)
                for x, y, w, h in rects:
                    p.fillRect(QRectF(x, y, max(2.0, w), h), sel_color)
            # Cursor
            if self.hasFocus() and self._cursor_visible and self._layout is not None:
                cx, cy, ch = self._layout.cursor_xy(self._cursor)
                # v4.1.23.7: when a pending format is set (user changed
                # the font size in the toolbar without a selection),
                # show the cursor at the pending size so the user sees
                # what they'll get before they type the first char.
                if self._pending_format and 'font_size' in self._pending_format:
                    try:
                        pending_fs = float(self._pending_format['font_size'])
                        # Match the layout's line-height calc: round(font_mm * dpi/25.4 * line_mult)
                        line_mult = float(
                            getattr(self.tb.style, 'line_height', 1.15) or 1.15)
                        pending_h = round(
                            pending_fs * self.dpi / 25.4 * line_mult)
                        # Keep the caret's BOTTOM on the current line's
                        # baseline and grow upward, so a larger pending
                        # size reads as "the next glyph will be this tall"
                        # without the caret jumping below the line.
                        if pending_h > ch:
                            cy = max(0.0, cy - (pending_h - ch))
                        ch = max(1, pending_h)
                    except Exception:
                        pass
                cur_color = self._current_format_attr('color') or (0, 0, 0)
                cur_qc = QColor(cur_color[0], cur_color[1], cur_color[2])
                cw = max(1.0, ch * 0.05)
                p.fillRect(QRectF(cx, cy, cw, ch), cur_qc)
            p.end()
        except Exception:
            import traceback, sys
            traceback.print_exc(file=sys.stderr)

    # ── Mouse ────────────────────────────────────────────────────────────────
    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(ev); return
        self._ensure_render()
        if self._layout is None:
            return
        idx = self._layout.hit_test(ev.position().x(), ev.position().y())
        if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._begin_selection_if_needed()
        else:
            self._clear_selection()
            self._anchor = idx
        self._cursor = idx
        # v4.1.23.20: remember where the press started + reset drag state so a
        # tiny pointer jitter during a plain click does not begin a (spurious)
        # selection that the next typed character would overwrite.
        self._press_pos = ev.position()
        self._drag_active = False
        # v4.1.23.38: a click places the caret at a new spot, which should
        # adopt the format THERE — drop any sticky pending format. (Setting a
        # size in the toolbar spinbox refocuses the editor without a click, so
        # that workflow is unaffected.)
        self._pending_format = None
        self._pending_alignment = None
        self._invalidate()
        self.setFocus()

    def mouseMoveEvent(self, ev: QMouseEvent):
        if not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        # v4.1.23.20: require a small movement before a drag-select begins, so
        # a click that wobbles by a pixel or two does not create a selection.
        if not getattr(self, '_drag_active', False):
            pp = getattr(self, '_press_pos', None)
            if pp is not None:
                dx = ev.position().x() - pp.x()
                dy = ev.position().y() - pp.y()
                if (dx * dx + dy * dy) < 16.0:   # ~4 px threshold
                    return
            self._drag_active = True
        self._ensure_render()
        if self._layout is None: return
        idx = self._layout.hit_test(ev.position().x(), ev.position().y())
        self._begin_selection_if_needed()
        self._cursor = idx
        self._invalidate()

    def mouseDoubleClickEvent(self, ev: QMouseEvent):
        # Select word
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self._ensure_render()
        if self._layout is None: return
        idx = self._layout.hit_test(ev.position().x(), ev.position().y())
        text = _runs_text(self._runs)
        a = idx
        while a > 0 and text[a - 1].isalnum():
            a -= 1
        b = idx
        while b < len(text) and text[b].isalnum():
            b += 1
        self._anchor = a; self._cursor = b
        self._invalidate()

    # ── Multi-level list editing (v4.1.23.47) ─────────────────────────────────
    _LIST_BULLETS = ['•', '◦', '▪', '‣', '·']

    def _list_para_bounds(self):
        """Flat (start, end) indices of the paragraph holding the caret, plus
        the full flat text. Paragraphs are split on '\\n'."""
        text = _runs_text(self._runs)
        start = text.rfind('\n', 0, self._cursor) + 1   # 0 if none
        nxt = text.find('\n', self._cursor)
        end = nxt if nxt != -1 else len(text)
        return start, end, text

    def _parse_list_line(self, line):
        """Return (kind, depth, marker, prefix_len) if the paragraph text is a
        list item, else None. kind is 'bullet' or 'number'; prefix_len counts
        the indent + marker + trailing gap so callers can slice off content."""
        import re
        m = re.match(r'^( *)([\u2022\u25e6\u25aa\u2023\u00b7])(  )', line)
        if m:
            return ('bullet', len(m.group(1)) // 4, m.group(2),
                    len(m.group(1)) + 1 + 2)
        m = re.match(r'^( *)(\d+)(\.  )', line)
        if m:
            return ('number', len(m.group(1)) // 4, m.group(2),
                    len(m.group(1)) + len(m.group(2)) + 3)
        return None

    def _make_list_prefix(self, kind, depth, num='1'):
        depth = max(0, depth)
        if kind == 'number':
            return ('    ' * depth) + str(num) + '.  '
        mark = self._LIST_BULLETS[min(depth, len(self._LIST_BULLETS) - 1)]
        return ('    ' * depth) + mark + '  '

    def _replace_list_prefix(self, para_start, old_len, new_prefix):
        """Swap a paragraph's leading list prefix, keeping the caret on the
        same content character it was on before."""
        old_cursor = self._cursor
        self._delete_range(para_start, para_start + old_len)
        self._cursor = para_start
        self._insert_text(new_prefix)
        delta = len(new_prefix) - old_len
        if old_cursor >= para_start + old_len:
            self._cursor = old_cursor + delta
        else:
            self._cursor = para_start + len(new_prefix)

    def _paragraph_starts_in_range(self, a, b):
        """Return ([paragraph start indices touched by a..b], full flat text)."""
        text = _runs_text(self._runs)
        start = text.rfind('\n', 0, a) + 1
        starts = [start]
        i = text.find('\n', start)
        while i != -1 and i < b:
            starts.append(i + 1)
            i = text.find('\n', i + 1)
        return starts, text

    # Public commands wired to toolbar buttons (v4.1.23.48)
    def toggle_bullet_list(self):
        self._toggle_list('bullet')

    def toggle_numbered_list(self):
        self._toggle_list('number')

    def list_indent(self):
        self._handle_list_indent(outdent=False)

    def list_outdent(self):
        self._handle_list_indent(outdent=True)

    def _toggle_list(self, kind):
        """Toggle bullet/numbered list on the current paragraph (or every
        paragraph in the selection). If they are already all this kind of list,
        the markers are removed; otherwise they are added/converted."""
        multi = self._has_selection()
        if multi:
            a, b = self._sel_range()
        else:
            a = b = self._cursor
        self._push_undo("list_toggle")
        starts, text = self._paragraph_starts_in_range(a, b)

        def line_of(start):
            nxt = text.find('\n', start)
            end = nxt if nxt != -1 else len(text)
            return text[start:end]

        infos = [(s, self._parse_list_line(line_of(s))) for s in starts]
        all_same = all((info and info[0] == kind) for _, info in infos)

        if not multi:
            s, info = infos[0]
            if all_same:
                self._replace_list_prefix(s, info[3], '')
            else:
                depth = info[1] if info else 0
                old_len = info[3] if info else 0
                new_prefix = self._make_list_prefix(kind, depth, num=1)
                self._replace_list_prefix(s, old_len, new_prefix)
            self._invalidate()
            return

        # Multi-paragraph: rebuild from the bottom up so earlier indices stay
        # valid while we edit.
        self._clear_selection()
        n = 1
        ops = []
        for s, info in infos:
            if all_same:
                ops.append((s, info[3], ''))
            else:
                depth = info[1] if info else 0
                old_len = info[3] if info else 0
                if kind == 'number':
                    pfx = self._make_list_prefix('number', depth, num=n); n += 1
                else:
                    pfx = self._make_list_prefix('bullet', depth)
                ops.append((s, old_len, pfx))
        for s, old_len, pfx in reversed(ops):
            self._delete_range(s, s + old_len)
            if pfx:
                self._cursor = s
                self._insert_text(pfx)
        self._cursor = max(0, min(_runs_total_len(self._runs), self._cursor))
        self._invalidate()

    def _handle_list_indent(self, outdent: bool) -> bool:
        """Tab / Shift+Tab on a list paragraph. Returns True if handled."""
        if self._has_selection():
            return False
        start, end, text = self._list_para_bounds()
        info = self._parse_list_line(text[start:end])
        if not info:
            return False
        kind, depth, marker, plen = info
        self._push_undo("list_outdent" if outdent else "list_indent")
        if outdent and depth <= 0:
            # already at the left margin → drop the marker entirely
            self._replace_list_prefix(start, plen, '')
        else:
            new_depth = depth - 1 if outdent else depth + 1
            new = self._make_list_prefix(kind, new_depth, num=marker)
            self._replace_list_prefix(start, plen, new)
        self._invalidate()
        return True

    def _handle_list_enter(self) -> bool:
        """Enter inside a list paragraph: continue the list, or end it when the
        current item is empty. Returns True if handled."""
        if self._has_selection():
            return False
        start, end, text = self._list_para_bounds()
        info = self._parse_list_line(text[start:end])
        if not info:
            return False
        kind, depth, marker, plen = info
        content = text[start + plen:end]
        # Empty item + caret in/after the prefix → terminate the list.
        if content.strip() == '' and self._cursor >= start + plen:
            self._push_undo("list_end")
            self._replace_list_prefix(start, plen, '')
            self._invalidate()
            return True
        self._push_undo("newline")
        if kind == 'number':
            try: nextnum = int(marker) + 1
            except ValueError: nextnum = 1
            new_prefix = self._make_list_prefix('number', depth, num=nextnum)
        else:
            new_prefix = self._make_list_prefix('bullet', depth)
        self._insert_text('\n' + new_prefix)
        self._invalidate()
        return True

    # ── Keys ──────────────────────────────────────────────────────────────────
    def event(self, ev):
        # v4.1.23.30: claim editing keys during ShortcutOverride so that
        # window-level QAction shortcuts do NOT swallow them before they reach
        # our keyPressEvent. The canvas has an object-delete QAction bound to
        # the bare "Delete" key; while editing text inside an inline body that
        # action was eating Delete, so forward-delete (and even deleting on the
        # current line) did nothing. Accepting the ShortcutOverride tells Qt to
        # deliver the key as a normal key press to this widget instead of
        # triggering the shortcut. Backspace already worked because it is not
        # bound as a shortcut; we include it (and the navigation/editing keys)
        # defensively in case more single-key shortcuts are added later.
        try:
            if ev.type() == QEvent.Type.ShortcutOverride:
                k = ev.key()
                mods = ev.modifiers()
                ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
                claim = {
                    Qt.Key.Key_Delete, Qt.Key.Key_Backspace,
                    Qt.Key.Key_Left, Qt.Key.Key_Right,
                    Qt.Key.Key_Up, Qt.Key.Key_Down,
                    Qt.Key.Key_Home, Qt.Key.Key_End,
                    Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                    Qt.Key.Key_Return, Qt.Key.Key_Enter,
                    Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
                }
                if k in claim and not ctrl:
                    ev.accept()
                    return True
                # v4.2.1: in the document body, claim Ctrl+S / Ctrl+Shift+S so
                # they reach our keyPressEvent (which forwards them to the
                # window's Save / Save As) instead of being swallowed or, for
                # Ctrl+Shift+S, triggering the editor's strikethrough action.
                if (getattr(self, '_is_doc_body', False)
                        and ctrl and k == Qt.Key.Key_S):
                    if (self._host_save is not None
                            or self._host_save_as is not None):
                        ev.accept()
                        return True
                # v4.1.23.38: also claim any Ctrl/Alt combo that maps to a
                # configured editor action (undo/redo/copy/paste/format/…) so a
                # window-level QAction (e.g. global Undo on Ctrl+Z) can't eat it
                # before our keyPressEvent dispatches it.
                try:
                    from edof._apps.shortcuts import event_combo
                    if not hasattr(self, '_combo_to_action'):
                        self._reload_shortcuts()
                    combo = event_combo(ev)
                    if combo and combo in getattr(self, '_combo_to_action', {}):
                        ev.accept()
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return super().event(ev)

    def keyPressEvent(self, ev: QKeyEvent):
        # v4.2.11.37: an exception escaping a key handler kills the whole app
        # in PyQt6 (qFatal). Catch, log, and keep the editor alive instead.
        try:
            return self._key_press_impl(ev)
        except Exception:
            import traceback as _tb
            _tb.print_exc()
            try:
                from edof.engine.debug_log import log as _dlog
                _dlog("edof_text_editor.keyPressEvent EXCEPTION",
                      err=_tb.format_exc()[-1500:])
            except Exception:
                pass
            return

    def _key_press_impl(self, ev: QKeyEvent):
        key = ev.key()
        mods = ev.modifiers()
        ctrl  = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        # v4.1.23.1-debug: log every keystroke with cursor state. Compact:
        # one line per key so we can read the whole session linearly.
        try:
            from edof.engine.debug_log import log as _dlog
            keytxt = ev.text() if ev.text() else ""
            _dlog("editor.key",
                   key=int(key),
                   ctrl=int(ctrl), shift=int(shift),
                   char=repr(keytxt) if keytxt else "",
                   cursor=self._cursor,
                   anchor=self._anchor,
                   text_len=len("".join(r.text or "" for r in self._runs)),
                   tail=("".join(r.text or "" for r in self._runs))[-25:])
        except Exception: pass

        # Navigation
        if key == Qt.Key.Key_Escape:
            self.cancel(); return
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            try:
                from edof.engine.debug_log import log as _dlog
                _dlog("editor.Enter",
                       ctrl=ctrl, is_doc_body=self._is_doc_body,
                       cursor=self._cursor,
                       text_before=("".join(r.text or "" for r in self._runs))[:80])
            except Exception: pass
            if ctrl:
                # Ctrl+Enter: in doc mode this is a HARD page break.
                # We insert a '\n' so the current paragraph is split at
                # the caret; the canvas handler then marks the resulting
                # post-break paragraph with page_break_before=True and
                # repaginates. In non-doc mode, just emit the signal —
                # the canvas commits the textbox.
                if self._is_doc_body:
                    self._push_undo("hard_page_break")
                    self._insert_text("\n")
                    self._invalidate()
                self.new_page_requested.emit(self.tb); return
            # v4.1.22.11: pre-emptive Enter REMOVED. With the Word-style
            # repaginate model, regular Enter just inserts '\n' and the
            # idle repaginate handler creates a new page automatically if
            # content overflows — no heuristic geometry check needed.
            # v4.1.23.47: multi-level list continuation. If the caret sits in a
            # bullet/numbered paragraph, Enter starts the next item (or ends the
            # list when the current item is empty) instead of a plain newline.
            if self._handle_list_enter():
                return
            self._push_undo("newline")
            self._insert_text("\n")
            self._invalidate(); return

        # v4.1.23.47: Tab / Shift+Tab manage list indentation.
        if key == Qt.Key.Key_Backtab or (key == Qt.Key.Key_Tab and shift):
            self._handle_list_indent(outdent=True)
            return
        if key == Qt.Key.Key_Tab and not ctrl:
            if self._handle_list_indent(outdent=False):
                return
            # Not in a list → insert a soft 4-space indent so Tab isn't dead.
            self._push_undo("type"); self._insert_text('    '); self._invalidate()
            return

        # v4.2.1: document-level Save / Save As take precedence inside the body
        # editor, before the configurable dispatch (which maps Ctrl+Shift+S to
        # strikethrough). Forward to the host window so the standard shortcuts
        # work while typing.
        if ctrl and key == Qt.Key.Key_S and getattr(self, '_is_doc_body', False):
            if shift and self._host_save_as is not None:
                self._host_save_as(); ev.accept(); return
            if not shift and self._host_save is not None:
                self._host_save(); ev.accept(); return

        # v4.1.23.37: configurable shortcuts (formatting / clipboard /
        # alignment). Resolved via the user-editable map; unmapped combos
        # (e.g. ctrl+arrow word navigation) fall through to the handlers below.
        if ctrl and self._dispatch_shortcut(ev):
            return

        # Selection setup
        def _move(new_idx: int):
            if shift:
                self._begin_selection_if_needed()
            else:
                self._clear_selection()
            self._cursor = max(0, min(_runs_total_len(self._runs), new_idx))
            # v4.1.23.38: a deliberate caret move adopts the format at the new
            # position — drop any sticky pending format. (Pending still
            # persists across continuous TYPING, which never calls _move.)
            self._pending_format = None
            self._pending_alignment = None
            self._invalidate()

        if key == Qt.Key.Key_Left:
            if ctrl:
                _move(self._word_left(self._cursor)); return
            _move(self._cursor - 1); return
        if key == Qt.Key.Key_Right:
            if ctrl:
                _move(self._word_right(self._cursor)); return
            _move(self._cursor + 1); return
        if key == Qt.Key.Key_Home:
            if ctrl:
                _move(0); return
            # Beginning of line
            self._ensure_render()
            if self._layout and self._layout.chars and self._cursor > 0:
                cur = max(0, self._cursor - 1)
                if cur < len(self._layout.chars):
                    line_idx = self._layout.chars[cur].line_idx
                    new = self._layout._line_start_index(line_idx)
                    _move(new); return
            _move(0); return
        if key == Qt.Key.Key_End:
            if ctrl:
                _move(_runs_total_len(self._runs)); return
            self._ensure_render()
            if self._layout and self._layout.chars:
                line_idx = self._layout.chars[min(len(self._layout.chars)-1, self._cursor)].line_idx
                # find last char in line
                end = self._cursor
                for c in self._layout.chars:
                    if c.line_idx == line_idx:
                        end = c.char_idx + 1
                _move(end); return
            _move(_runs_total_len(self._runs)); return
        if key == Qt.Key.Key_Up:
            self._ensure_render()
            if self._layout:
                cx, cy, ch = self._layout.cursor_xy(self._cursor)
                new = self._layout.hit_test(cx, cy - ch * 0.5)
                # v4.1.22.4: if Up didn't move the cursor, we're already on
                # the first line — for doc body, ask the canvas to hop to
                # the previous page's body.
                if new == self._cursor and self._is_doc_body:
                    try: self.navigate_above.emit(self.tb)
                    except Exception: pass
                    return
                _move(new); return
        if key == Qt.Key.Key_Down:
            self._ensure_render()
            if self._layout:
                cx, cy, ch = self._layout.cursor_xy(self._cursor)
                new = self._layout.hit_test(cx, cy + ch * 1.5)
                if new == self._cursor and self._is_doc_body:
                    try: self.navigate_below.emit(self.tb)
                    except Exception: pass
                    return
                _move(new); return
        if key == Qt.Key.Key_PageUp:
            self._ensure_render()
            if self._layout:
                cx, cy, ch = self._layout.cursor_xy(self._cursor)
                new = self._layout.hit_test(cx, cy - self.height() * 0.8)
                if new == self._cursor and self._is_doc_body:
                    try: self.navigate_above.emit(self.tb)
                    except Exception: pass
                    return
                _move(new); return
        if key == Qt.Key.Key_PageDown:
            self._ensure_render()
            if self._layout:
                cx, cy, ch = self._layout.cursor_xy(self._cursor)
                new = self._layout.hit_test(cx, cy + self.height() * 0.8)
                if new == self._cursor and self._is_doc_body:
                    try: self.navigate_below.emit(self.tb)
                    except Exception: pass
                    return
                _move(new); return

        # Editing
        if key == Qt.Key.Key_Backspace:
            # v4.1.22.1: Backspace at the very start of a doc body asks the
            # canvas to merge with the previous page's body (Word-style:
            # remove the page break, fuse content). If there's no selection
            # and the cursor is at 0, emit the request instead of doing a
            # local delete (which would be a no-op anyway).
            if (self._is_doc_body and not self._has_selection()
                and self._cursor == 0):
                try: self.merge_with_previous_requested.emit(self.tb)
                except Exception: pass
                return
            self._push_undo("delete")
            if self._has_selection():
                a, b = self._sel_range()
                self._delete_range(a, b); self._cursor = a; self._clear_selection()
            elif ctrl and self._cursor > 0:
                # v4.1.16.5: Ctrl+Backspace deletes previous word
                start = self._word_left(self._cursor)
                self._delete_range(start, self._cursor)
                self._cursor = start
            elif self._cursor > 0:
                self._delete_range(self._cursor - 1, self._cursor)
                self._cursor -= 1
            self._invalidate(); return
        if key == Qt.Key.Key_Delete:
            # v4.1.23.20: Delete at the very end of a doc body (no selection)
            # is a forward-delete across the page boundary: ask the canvas to
            # pull the next page's content up (mirror of Backspace-at-0).
            if (self._is_doc_body and not self._has_selection()
                and not ctrl
                and self._cursor >= _runs_total_len(self._runs)):
                try: self.merge_with_next_requested.emit(self.tb)
                except Exception: pass
                return
            self._push_undo("delete")
            if self._has_selection():
                a, b = self._sel_range()
                self._delete_range(a, b); self._cursor = a; self._clear_selection()
            elif ctrl:
                # v4.1.16.5: Ctrl+Delete deletes next word
                end = self._word_right(self._cursor)
                self._delete_range(self._cursor, end)
            else:
                self._delete_range(self._cursor, self._cursor + 1)
            self._invalidate(); return

        # Clipboard / undo / format / alignment shortcuts are handled by the
        # configurable dispatch earlier (v4.1.23.37). Ctrl+Y stays as a fixed
        # alternate redo (Windows convention) not exposed in the editable map.
        if ctrl and key == Qt.Key.Key_Y:
            self.redo(); return

        # Regular text input (ev.text() yields the typed character(s))
        if ev.text() and ev.text().isprintable():
            self._push_undo("type")
            self._insert_text(ev.text())
            self._invalidate(); return

        super().keyPressEvent(ev)

    # ── IME ──────────────────────────────────────────────────────────────────
    def inputMethodEvent(self, ev: QInputMethodEvent):
        commit = ev.commitString()
        if commit:
            self._push_undo("ime")
            self._insert_text(commit)
            self._invalidate()
        # Note: preedit (composition string) is not currently displayed
        # — IME usually shows it in its own popup. To display inline,
        # we'd need to render preedit text differently and not commit.
        ev.accept()

    def inputMethodQuery(self, query):
        try:
            # Return cursor position for IME
            if query == Qt.InputMethodQuery.ImCursorPosition:
                return self._cursor
            if query == Qt.InputMethodQuery.ImSurroundingText:
                return _runs_text(self._runs)
            if query == Qt.InputMethodQuery.ImCurrentSelection:
                if self._has_selection():
                    a, b = self._sel_range()
                    return _runs_text(self._runs)[a:b]
                return ""
            # PyQt6 removed ImMicroFocus; use ImCursorRectangle only
            if query == Qt.InputMethodQuery.ImCursorRectangle:
                self._ensure_render()
                if self._layout:
                    cx, cy, ch = self._layout.cursor_xy(self._cursor)
                    return QRect(int(cx), int(cy), 2, int(ch))
        except Exception:
            pass
        return super().inputMethodQuery(query)

    # ── Configurable shortcuts (v4.1.23.37) ───────────────────────────────────
    def _reload_shortcuts(self):
        """Load (or reload) the user's shortcut map and build a reverse
        combo→action index for keyPressEvent dispatch."""
        try:
            from edof._apps.shortcuts import load_shortcuts
            m = load_shortcuts()
        except Exception:
            m = {}
        self._combo_to_action = {v: k for k, v in m.items()}

    def _dispatch_shortcut(self, ev) -> bool:
        """Map a key event to a configured action and run it. Returns True if
        handled. Unmapped combos return False so other handlers can run."""
        try:
            from edof._apps.shortcuts import event_combo
        except Exception:
            return False
        if not hasattr(self, '_combo_to_action'):
            self._reload_shortcuts()
        combo = event_combo(ev)
        if not combo:
            return False
        action = self._combo_to_action.get(combo)
        if not action:
            return False
        actions = {
            'bold':          self.toggle_bold,
            'italic':        self.toggle_italic,
            'underline':     self.toggle_underline,
            'strikethrough': self.toggle_strikethrough,
            'copy':          self._copy,
            'copy_plain':    self._copy_plain,
            'cut':           self._cut,
            'paste':         self._paste,
            'paste_spacing': self._paste_line_spacing_only,
            'paste_markdown': self._paste_markdown,
            'select_all':    self._select_all,
            'undo':          self.undo,
            'redo':          self.redo,
            'align_left':    lambda: self.set_alignment('left'),
            'align_center':  lambda: self.set_alignment('center'),
            'align_right':   lambda: self.set_alignment('right'),
            'justify':       lambda: self.set_alignment('justify'),
            'justify_full':  lambda: self.set_alignment('justify_full'),
        }
        fn = actions.get(action)
        if fn is None:
            return False
        try:
            fn()
        except Exception:
            return False
        return True

    def _select_all(self):
        self._anchor = 0
        self._cursor = _runs_total_len(self._runs)
        self._invalidate()

    def _paste_markdown(self):
        """v4.1.23.38: Ctrl+Alt+V — interpret the clipboard's plain text as
        Markdown and insert it as formatted runs."""
        md = QGuiApplication.clipboard().mimeData()
        if md is None or not md.hasText():
            return
        txt = md.text()
        if not txt:
            return
        try:
            runs = markdown_to_runs(txt)
        except Exception:
            runs = None
        if not runs:
            self._insert_text(txt); self._invalidate(); return
        self._push_undo("paste")
        if self._has_selection():
            a, b = self._sel_range()
            self._delete_range(a, b)
            self._cursor = a; self._clear_selection()
        self._insert_runs(runs)
        self._invalidate()

    # ── Clipboard ────────────────────────────────────────────────────────────
    def _copy(self):
        if not self._has_selection():
            return
        a, b = self._sel_range()
        plain = _runs_text(self._runs)[a:b]
        # Serialize selected runs
        runs_blob = self._serialize_runs_range(a, b)
        md = QMimeData()
        md.setText(plain)
        md.setData(_EDOF_RUNS_MIME, runs_blob)
        QGuiApplication.clipboard().setMimeData(md)

    def _cut(self):
        if not self._has_selection():
            return
        self._push_undo("cut")
        self._copy()
        a, b = self._sel_range()
        self._delete_range(a, b)
        self._cursor = a; self._clear_selection()
        self._invalidate()

    def _paste(self):
        md = QGuiApplication.clipboard().mimeData()
        if md is None:
            return
        if md.hasFormat(_EDOF_RUNS_MIME):
            runs = self._deserialize_runs(md.data(_EDOF_RUNS_MIME).data())
            if runs:
                self._push_undo("paste")
                if self._has_selection():
                    a, b = self._sel_range()
                    self._delete_range(a, b)
                    self._cursor = a; self._clear_selection()
                self._insert_runs(runs)
                self._invalidate()
                return
        # v4.1.23.37: formatted HTML from a browser / Google Sheets / Docs /
        # Word — parse it into runs so font, size, bold/italic, colour and
        # spacing survive the paste.
        if md.hasHtml():
            try:
                runs = html_to_runs(md.html())
            except Exception:
                runs = []
            if runs and any((r.text or '').strip() for r in runs):
                self._push_undo("paste")
                if self._has_selection():
                    a, b = self._sel_range()
                    self._delete_range(a, b)
                    self._cursor = a; self._clear_selection()
                self._insert_runs(runs)
                self._invalidate()
                return
        # Fallback: plain text from clipboard
        if md.hasText():
            txt = md.text()
            if txt:
                self._push_undo("paste")
                self._insert_text(txt)
                self._invalidate()

    def _copy_plain(self):
        """v4.1.23.37: Ctrl+Shift+C — copy the selection as PLAIN text only
        (no EDOF run attributes). A subsequent paste inherits the caret's
        format instead of the copied formatting."""
        if not self._has_selection():
            return
        a, b = self._sel_range()
        plain = _runs_text(self._runs)[a:b]
        md = QMimeData()
        md.setText(plain)
        QGuiApplication.clipboard().setMimeData(md)

    def _paste_line_spacing_only(self):
        """v4.1.23.37: Ctrl+Shift+V — paste the clipboard text keeping ONLY the
        line spacing (and letter spacing) of the copied runs, dropping fonts,
        size, weight, colour etc. (those inherit from the caret / pending)."""
        md = QGuiApplication.clipboard().mimeData()
        if md is None:
            return
        runs = None
        if md.hasFormat(_EDOF_RUNS_MIME):
            runs = self._deserialize_runs(md.data(_EDOF_RUNS_MIME).data())
        elif md.hasHtml():
            try: runs = html_to_runs(md.html())
            except Exception: runs = None
        if runs:
            stripped = []
            for r in runs:
                stripped.append(TextRun(
                    text=r.text,
                    line_height=getattr(r, 'line_height', None),
                    letter_spacing=getattr(r, 'letter_spacing', None),
                ))
            self._push_undo("paste")
            if self._has_selection():
                a, b = self._sel_range()
                self._delete_range(a, b)
                self._cursor = a; self._clear_selection()
            self._insert_runs(stripped)
            self._invalidate()
            return
        # no run info → behave like plain paste
        if md.hasText() and md.text():
            self._push_undo("paste")
            self._insert_text(md.text())
            self._invalidate()

    def _paste_plain(self):
        """v4.1.23.22: paste clipboard text WITHOUT its original formatting —
        the inserted text inherits the format at the caret (or the pending
        format). Mapped to Ctrl+Shift+V."""
        md = QGuiApplication.clipboard().mimeData()
        if md is None:
            return
        txt = md.text() if md.hasText() else ""
        if not txt:
            return
        self._push_undo("paste")
        if self._has_selection():
            a, b = self._sel_range()
            self._delete_range(a, b)
            self._cursor = a; self._clear_selection()
        self._insert_text(txt)
        self._invalidate()

    def _serialize_runs_range(self, a: int, b: int) -> bytes:
        """Pickle-free serialization of run slice."""
        import json
        # Walk runs and extract slice
        out = []
        abs_i = 0
        for r in self._runs:
            L = len(r.text or "")
            if abs_i + L <= a or abs_i >= b:
                abs_i += L; continue
            s = max(0, a - abs_i); e = min(L, b - abs_i)
            txt = r.text[s:e]
            if not txt:
                abs_i += L; continue
            # v4.1.23.38: only emit attributes that are actually set on the run
            # so None (inherit) round-trips as inherit rather than being forced.
            d = {'text': txt}
            for k in ('font_family', 'font_size', 'bold', 'italic',
                      'underline', 'strikethrough', 'line_height',
                      'letter_spacing', 'alignment'):
                v = getattr(r, k, None)
                if v is not None:
                    d[k] = v
            # v4.2.11.48: KEEP SOURCE FORMATTING. Attributes the run inherits
            # from its box style (typical for header/footer bands, which have
            # their own base style) used to round-trip as "inherit" -- pasting
            # into a box with a different base style visibly changed the text.
            # Resolve the identity attributes from the source box style at copy
            # time so the pasted text looks like what was copied, anywhere.
            try:
                base = getattr(self.tb, 'style', None)
                if base is not None:
                    if 'font_family' not in d and getattr(base, 'font_family', None):
                        d['font_family'] = base.font_family
                    if 'font_size' not in d and getattr(base, 'font_size', None):
                        d['font_size'] = float(base.font_size)
                    if 'color' not in d and getattr(r, 'color', None) is None \
                            and getattr(base, 'color', None):
                        d['color'] = list(base.color)
            except Exception:
                pass
            if r.color is not None:
                d['color'] = list(r.color)
            if getattr(r, 'background', None) is not None:
                d['background'] = list(r.background)
            out.append(d)
            abs_i += L
        return json.dumps(out).encode("utf-8")

    def _deserialize_runs(self, data: bytes) -> List:
        import json
        try:
            items = json.loads(bytes(data).decode("utf-8"))
        except Exception:
            return []
        out = []
        for it in items:
            color = tuple(it['color']) if it.get('color') else None
            # v4.1.23.38: keep None = inherit. Previously a missing font_size
            # became 12 (read as 12 mm ≈ 34 pt → huge) and a missing
            # font_family became Arial, so pasting text that inherited its
            # size/font from the body came back oversized and re-fonted.
            fs = it.get('font_size', None)
            r = TextRun(
                text=it.get('text', ''),
                font_family=it.get('font_family', None),
                font_size=(float(fs) if fs is not None else None),
                bold=(bool(it['bold']) if 'bold' in it else None),
                italic=(bool(it['italic']) if 'italic' in it else None),
                underline=(bool(it['underline']) if 'underline' in it else None),
                color=color,
            )
            if 'strikethrough' in it and hasattr(r, 'strikethrough'):
                r.strikethrough = bool(it['strikethrough'])
            # v4.1.23.35: restore per-run spacing + alignment so Ctrl+C/Ctrl+V
            # carries font size, line spacing AND letter spacing (None = keep
            # inheriting from the body style).
            if it.get('line_height') is not None:
                r.line_height = float(it['line_height'])
            if it.get('letter_spacing') is not None:
                r.letter_spacing = float(it['letter_spacing'])
            if it.get('alignment') is not None:
                r.alignment = it['alignment']
            if it.get('background') is not None:
                r.background = tuple(it['background'])
            out.append(r)
        return out

    def _insert_runs(self, runs):
        """Insert a list of runs at the cursor."""
        if not runs:
            return
        # Find insertion run + offset
        r_idx, off = _abs_to_run(self._runs, self._cursor)
        # Split if mid-run
        right_idx = _split_run_at(self._runs, r_idx, off)
        for k, r in enumerate(runs):
            self._runs.insert(right_idx + k, _clone_runs([r])[0])
        added_len = sum(len(r.text or "") for r in runs)
        self._cursor += added_len
        self._runs = _normalize_runs(self._runs)
