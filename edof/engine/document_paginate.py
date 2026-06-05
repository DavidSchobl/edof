# edof/engine/document_paginate.py
"""v4.1.23: Clean document-mode pagination.

Replaces edof.engine.textbox_flow.repaginate_doc and all its helpers.

Core principle: doc.body.paragraphs is the canonical content. Pages are
PURE VIEWPORTS regenerated from that content on every change. Each page
is built from the same template:
  1. DocumentTextBox (always) — body content slice for this page,
     auto-positioned inside the section margins.
  2. DocumentHeaderBox (if doc.body.header_enabled) — header template
     with variables resolved for this page.
  3. DocumentFooterBox (if doc.body.footer_enabled) — footer template
     symmetric to the header.
  4. Any user-placed overlays (images, shapes, free text boxes) are
     preserved on their original page.

The four pagination rules (page_break_before, keep_lines, keep_next,
widow/orphan) are applied in a post-process pass over a paragraph-aware
line walk. Per-paragraph space_before_mm / space_after_mm are honoured.

External API:
  paginate_document(doc, focus_page=None, focus_cursor=None) -> dict
    Returns:
      changed         bool   — anything actually changed
      pages_count     int    — final page count
      cursor_page     int|None
      cursor_offset   int|None — char offset within that page's body
"""
from __future__ import annotations

import copy as _copy
from typing import Any, Dict, List, Optional, Tuple

from edof.format.styles import TextRun
from edof.format.document_body import DocumentBody, Paragraph
from edof.format.document_boxes import (
    DocumentTextBox, DocumentHeaderBox, DocumentFooterBox,
    is_document_box, is_document_body, is_document_header, is_document_footer,
    resolve_template_runs,
)
from edof.format.objects import TextBox
from edof.engine.transform import mm_to_px


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────

def runs_text(runs) -> str:
    """Plain text content of a run list."""
    return "".join((r.text or "") for r in (runs or []))


def split_runs_at_char(runs, idx: int) -> Tuple[List[TextRun], List[TextRun]]:
    """Split a list of runs at character index `idx`. Returns (left, right).
    Style on the run that gets split is duplicated to both halves."""
    if idx <= 0: return ([], [_copy.deepcopy(r) for r in (runs or [])])
    left: List[TextRun] = []
    right: List[TextRun] = []
    pos = 0
    consumed = False
    for r in (runs or []):
        rt = r.text or ""
        rlen = len(rt)
        if consumed:
            right.append(_copy.deepcopy(r))
            continue
        if pos + rlen <= idx:
            left.append(_copy.deepcopy(r))
            pos += rlen
            if pos == idx:
                consumed = True
            continue
        # idx falls inside this run
        local = idx - pos
        l_run = _copy.deepcopy(r); l_run.text = rt[:local]; left.append(l_run)
        r_run = _copy.deepcopy(r); r_run.text = rt[local:]; right.append(r_run)
        consumed = True
    return (left, right)


def find_document_body_on_page(page) -> Optional[DocumentTextBox]:
    """First DocumentTextBox on a page, or None."""
    for o in page.objects:
        if isinstance(o, DocumentTextBox):
            return o
    # Legacy fallback: look for a TextBox named "document_body" (pre-4.1.23)
    for o in page.objects:
        if isinstance(o, TextBox) and (getattr(o, 'name', '') or '') in (
                'document_body', 'doc_body') or (getattr(o, 'name', '') or '').startswith('doc_body'):
            return o
    return None


def find_document_header_on_page(page) -> Optional[DocumentHeaderBox]:
    for o in page.objects:
        if isinstance(o, DocumentHeaderBox):
            return o
    return None


def find_document_footer_on_page(page) -> Optional[DocumentFooterBox]:
    for o in page.objects:
        if isinstance(o, DocumentFooterBox):
            return o
    return None


def _split_runs_at_newlines(runs) -> List[List[TextRun]]:
    """Split runs into per-paragraph run lists at every '\\n'. The '\\n'
    chars themselves are dropped — each returned list is one paragraph's
    runs without paragraph terminators."""
    paragraphs: List[List[TextRun]] = []
    cur: List[TextRun] = []
    for r in (runs or []):
        text = r.text or ""
        if '\n' not in text:
            if text:
                cur.append(_copy.deepcopy(r))
            continue
        parts = text.split('\n')
        for j, part in enumerate(parts):
            if part:
                new_r = _copy.deepcopy(r); new_r.text = part
                cur.append(new_r)
            if j < len(parts) - 1:
                # v4.1.23.32: closing a paragraph here. If it has no text
                # runs (an EMPTY line made by Enter), keep a zero-width run
                # carrying THIS run's format so the empty line's font size
                # (and therefore its height) is preserved through the
                # paragraph round-trip. Without this the empty line fell back
                # to the body default size in pagination while the editor
                # rendered it at the typed size, so pagination thought more
                # lines fit and let text run below the bottom margin.
                if not cur:
                    empty_r = _copy.deepcopy(r); empty_r.text = ''
                    cur.append(empty_r)
                paragraphs.append(cur); cur = []
    paragraphs.append(cur)
    return paragraphs


def _runs_from_paragraphs(paragraphs, start_idx: int, end_idx: int) -> List[TextRun]:
    """Build a flat runs list for paragraphs[start_idx:end_idx], joining
    paragraphs with single '\\n' separators."""
    out: List[TextRun] = []
    end_idx = min(end_idx, len(paragraphs))
    for i in range(start_idx, end_idx):
        p = paragraphs[i]
        if i > start_idx:
            # v4.1.23.32: the separator '\n' terminates the PREVIOUS paragraph
            # and (for an empty paragraph) is the only glyph on that line, so
            # it must carry that paragraph's font size — otherwise an empty
            # line is measured at the body default size and pagination
            # underestimates its height, letting content spill below the
            # bottom margin. Copy the font metrics from the previous
            # paragraph's last run (its placeholder run for empty lines).
            sep = TextRun(text='\n')
            prev_runs = (paragraphs[i - 1].runs or [])
            if prev_runs:
                src = prev_runs[-1]
                try:
                    sep.font_size = src.font_size
                    sep.font_family = src.font_family
                    sep.bold = getattr(src, 'bold', False)
                    sep.italic = getattr(src, 'italic', False)
                    sep.line_height = getattr(src, 'line_height', None)
                    sep.letter_spacing = getattr(src, 'letter_spacing', None)
                except Exception:
                    pass
            out.append(sep)
        for r in (p.runs or []):
            out.append(_copy.deepcopy(r))
    return out


def _sync_body_from_textboxes(doc) -> None:
    """Project every page's DocumentTextBox.runs back into doc.body.paragraphs.

    The editor mutates the per-page DocumentTextBox during typing; before
    we re-paginate from body.paragraphs (the canonical store), we have
    to fold those edits back in. Preserves paragraph properties by index
    (lossy when paragraphs are inserted/removed in the middle, fine for
    caret-position edits)."""
    if doc is None or getattr(doc, 'body', None) is None:
        return
    all_runs: List[TextRun] = []
    # v4.1.23.52: paragraph indices (in the rebuilt body) that begin on a hard
    # page break, and whether pagination has run at all (so we know the flags
    # are trustworthy). Used to re-apply page_break_before authoritatively,
    # because inserting the separator below shifts indices and the old
    # index-based property copy would otherwise put the break on the wrong
    # paragraph.
    hard_break_para_indices = set()
    have_hb_info = False
    for pg in doc.pages:
        tb = find_document_body_on_page(pg)
        if tb is None: continue
        if hasattr(tb, '_hard_break_before'):
            have_hb_info = True
        runs_in = list(tb.runs or [])
        # Legacy bodies (from v4.1.22 and earlier) may have tb.text set
        # but no runs at all. Treat the plain text as a single run so
        # the content survives migration.
        if not runs_in and (tb.text or ""):
            runs_in = [TextRun(text=tb.text)]
        is_empty = not runs_text(runs_in)
        # This page begins a NEW paragraph due to a hard page break.
        # Concatenation normally adds no separator (each slice is an exact cut
        # of one flow), which is right for SOFT breaks. But if the user
        # appended text to the previous page's last paragraph, that page no
        # longer ends in '\n' and direct concatenation would fuse the two
        # separate paragraphs. Re-insert the '\n' that the hard break implies.
        #
        # v4.1.23.55: this MUST run even when the page body is EMPTY (a fresh
        # Ctrl+Enter break the user has not typed into yet). Otherwise the empty
        # page is skipped, its hard-break index is never recorded, and the
        # authoritative pass below clears page_break_before — so on the next
        # repagination the empty page collapses back and the break is lost.
        if getattr(tb, '_hard_break_before', False):
            prev_text = runs_text(all_runs)
            if prev_text and not prev_text.endswith('\n'):
                all_runs.append(TextRun(text='\n'))
            hard_break_para_indices.add(runs_text(all_runs).count('\n'))
        if is_empty:
            continue
        all_runs.extend(_copy.deepcopy(r) for r in runs_in)

    para_runs = _split_runs_at_newlines(all_runs)
    old_paragraphs = doc.body.paragraphs or []
    new_paragraphs: List[Paragraph] = []

    def _runs_align(runs):
        # v4.2.1: the editor stamps the chosen alignment onto the runs of a
        # paragraph (set_alignment). Promote that onto Paragraph.alignment so
        # it is the durable, canonical home: it survives serialization and is
        # read by the renderer, the .docx exporter and style resolution. Without
        # this the alignment lived only on the runs / the page-local map and was
        # lost on save and on export.
        for _r in runs:
            a = getattr(_r, 'alignment', None)
            if a:
                return a
        return None

    for i, runs in enumerate(para_runs):
        run_al = _runs_align(runs)
        if i < len(old_paragraphs):
            old = old_paragraphs[i]
            new_p = Paragraph(
                runs=runs,
                style_id=old.style_id,
                alignment=(run_al if run_al is not None else old.alignment),
                line_height=old.line_height,
                space_before_mm=old.space_before_mm,
                space_after_mm=old.space_after_mm,
                indent_first_mm=old.indent_first_mm,
                indent_left_mm=old.indent_left_mm,
                indent_right_mm=old.indent_right_mm,
                list_level=old.list_level,
                list_kind=old.list_kind,
                keep_next=old.keep_next,
                keep_lines=old.keep_lines,
                page_break_before=old.page_break_before,
                widow_orphan_control=old.widow_orphan_control,
            )
        else:
            new_p = Paragraph(runs=runs, alignment=run_al)
        new_paragraphs.append(new_p)
    # v4.1.23.52: once pagination has run, the page bodies' hard-break flags are
    # the authoritative source of truth for page_break_before. Re-apply it so a
    # break never drifts onto a neighbouring paragraph after an edit across the
    # boundary. (Skipped on a fresh load before any pagination, where the
    # index-preserved flags are all we have.)
    if have_hb_info:
        for idx, p in enumerate(new_paragraphs):
            p.page_break_before = (idx in hard_break_para_indices)
    doc.body.paragraphs = new_paragraphs


# ────────────────────────────────────────────────────────────────────────
# Geometry
# ────────────────────────────────────────────────────────────────────────

def _section_geometry(doc):
    """Return (page_w_mm, page_h_mm, top_m, right_m, bottom_m, left_m,
                header_h_mm, footer_h_mm) for the document's single section."""
    pw = float(doc.default_width)
    ph = float(doc.default_height)
    body = doc.body
    top, right, bottom, left = body.page_margins_mm
    header_h = float(body.header_height_mm) if body.header_enabled else 0.0
    footer_h = float(body.footer_height_mm) if body.footer_enabled else 0.0
    return (pw, ph, float(top), float(right), float(bottom), float(left),
             header_h, footer_h)


def _body_rect_mm(doc) -> Tuple[float, float, float, float]:
    """Return (x, y, w, h) of the body region in mm."""
    pw, ph, top, right, bottom, left, header_h, footer_h = _section_geometry(doc)
    bx = left
    by = top + header_h
    bw = max(20.0, pw - left - right)
    bh = max(20.0, ph - top - bottom - header_h - footer_h)
    return (bx, by, bw, bh)


def _header_rect_mm(doc) -> Tuple[float, float, float, float]:
    pw, ph, top, right, bottom, left, header_h, footer_h = _section_geometry(doc)
    return (left, top, max(20.0, pw - left - right), max(1.0, header_h))


def _footer_rect_mm(doc) -> Tuple[float, float, float, float]:
    pw, ph, top, right, bottom, left, header_h, footer_h = _section_geometry(doc)
    return (left, ph - bottom - footer_h,
             max(20.0, pw - left - right), max(1.0, footer_h))


def _make_body_textbox(doc, ref_style=None) -> DocumentTextBox:
    """Construct a DocumentTextBox sized to the section's body rect."""
    bx, by, bw, bh = _body_rect_mm(doc)
    tb = DocumentTextBox()
    tb.transform.x = bx; tb.transform.y = by
    tb.transform.width = bw; tb.transform.height = bh
    if ref_style is not None:
        try: tb.style = _copy.deepcopy(ref_style)
        except Exception: pass
    tb.style.auto_fill = False
    tb.fill.color = None
    return tb


def _make_header_textbox(doc, ref_style=None) -> DocumentHeaderBox:
    bx, by, bw, bh = _header_rect_mm(doc)
    tb = DocumentHeaderBox()
    tb.transform.x = bx; tb.transform.y = by
    tb.transform.width = bw; tb.transform.height = bh
    if ref_style is not None:
        try: tb.style = _copy.deepcopy(ref_style)
        except Exception: pass
    tb.style.auto_fill = False
    tb.fill.color = None
    tb.style.font_size = 3.0    # smaller default for header
    return tb


def _make_footer_textbox(doc, ref_style=None) -> DocumentFooterBox:
    bx, by, bw, bh = _footer_rect_mm(doc)
    tb = DocumentFooterBox()
    tb.transform.x = bx; tb.transform.y = by
    tb.transform.width = bw; tb.transform.height = bh
    if ref_style is not None:
        try: tb.style = _copy.deepcopy(ref_style)
        except Exception: pass
    tb.style.auto_fill = False
    tb.fill.color = None
    tb.style.font_size = 3.0
    return tb


def sync_geometry_to_section(doc) -> bool:
    """Resize every body/header/footer box to match doc.body's margin +
    header_height + footer_height settings. Returns True if anything
    changed. Call this after the user edits margins or toggles header/footer
    visibility."""
    if doc is None or getattr(doc, 'body', None) is None: return False
    changed = False
    bx, by, bw, bh = _body_rect_mm(doc)
    for pg in doc.pages:
        tb = find_document_body_on_page(pg)
        if tb is not None:
            if (tb.transform.x != bx or tb.transform.y != by
                or tb.transform.width != bw or tb.transform.height != bh):
                tb.transform.x = bx; tb.transform.y = by
                tb.transform.width = bw; tb.transform.height = bh
                changed = True
    if doc.body.header_enabled:
        hx, hy, hw, hh = _header_rect_mm(doc)
        for pg in doc.pages:
            hb = find_document_header_on_page(pg)
            if hb is not None:
                if (hb.transform.x != hx or hb.transform.y != hy
                    or hb.transform.width != hw or hb.transform.height != hh):
                    hb.transform.x = hx; hb.transform.y = hy
                    hb.transform.width = hw; hb.transform.height = hh
                    changed = True
    if doc.body.footer_enabled:
        fx, fy, fw, fh = _footer_rect_mm(doc)
        for pg in doc.pages:
            fb = find_document_footer_on_page(pg)
            if fb is not None:
                if (fb.transform.x != fx or fb.transform.y != fy
                    or fb.transform.width != fw or fb.transform.height != fh):
                    fb.transform.x = fx; fb.transform.y = fy
                    fb.transform.width = fw; fb.transform.height = fh
                    changed = True
    return changed


# ────────────────────────────────────────────────────────────────────────
# Migration
# ────────────────────────────────────────────────────────────────────────

def migrate_legacy_doc_boxes(doc) -> bool:
    """Convert plain TextBox objects with name='document_body' (v4.1.22.x
    and earlier) to DocumentTextBox subclass. Returns True if anything
    was migrated. Safe to call on any document — non-doc-mode is no-op."""
    if doc is None or getattr(doc, 'mode', '') != 'document': return False
    changed = False
    for pg in doc.pages:
        new_objects = []
        for obj in pg.objects:
            if (isinstance(obj, TextBox)
                and not isinstance(obj, (DocumentTextBox, DocumentHeaderBox, DocumentFooterBox))
                and ((obj.name or '') in ('document_body', 'doc_body')
                     or (obj.name or '').startswith('doc_body'))):
                # Upgrade to DocumentTextBox
                new_tb = DocumentTextBox()
                # Copy every field that exists on both classes
                for fld in ('id', 'transform', 'text', 'style', 'runs',
                              'padding', 'padding_left', 'padding_right',
                              'padding_top', 'padding_bot', 'border', 'fill',
                              'paragraph_alignments', 'name', 'variable',
                              'note', 'visible', 'locked', 'rotation',
                              'opacity', 'z_index'):
                    if hasattr(obj, fld):
                        try:
                            setattr(new_tb, fld, getattr(obj, fld))
                        except Exception:
                            pass
                new_objects.append(new_tb)
                changed = True
            else:
                new_objects.append(obj)
        pg.objects = new_objects

    # v4.1.23.9: document bodies must have zero internal padding — the
    # page margins already provide the visual inset, and any extra
    # padding both reduces line capacity and (because each line.height is
    # rounded up) lets the last line bleed past the box's outer edge into
    # the bottom margin. Force padding to 0 on every body/header/footer.
    for pg in doc.pages:
        for obj in pg.objects:
            if isinstance(obj, (DocumentTextBox, DocumentHeaderBox, DocumentFooterBox)):
                st = getattr(obj, 'style', None)
                if st is not None:
                    for pad_attr in ('padding', 'padding_top', 'padding_bot',
                                      'padding_left', 'padding_right'):
                        if getattr(st, pad_attr, 0):
                            try:
                                setattr(st, pad_attr, 0.0)
                                changed = True
                            except Exception:
                                pass
    return changed


# ────────────────────────────────────────────────────────────────────────
# Main paginate
# ────────────────────────────────────────────────────────────────────────

def paginate_document(doc,
                       focus_page: Optional[int] = None,
                       focus_cursor: Optional[int] = None,
                       dpi: Optional[float] = None,
                       boundary_to_focus_page: bool = False,
                       skip_sync: bool = False,
                       ) -> Dict[str, Any]:
    """Rebuild doc.pages from doc.body.paragraphs.

    Steps:
      1. Migrate legacy boxes if any (one-shot).
      2. Project current DocumentTextBox runs back to body.paragraphs.
      3. Compute body rect, layout body content across pages.
      4. For each chunk, ensure a page exists with a DocumentTextBox
         holding the right slice. Header/footer boxes added/removed
         per body.{header,footer}_enabled.
      5. Prune trailing pages with no body content AND no user overlays
         (so user images, shapes, free text boxes are never destroyed).
      6. Map the caret through to (cursor_page, cursor_offset).
    """
    from edof.engine.text_layout import layout_runs

    result = {
        'changed': False, 'pages_count': 0,
        'cursor_page': None, 'cursor_offset': None,
    }
    if doc is None or getattr(doc, 'mode', '') != 'document':
        return result
    if getattr(doc, 'body', None) is None:
        return result

    # v4.1.23.1-debug: log entry with snapshot of every page's tb content.
    try:
        from edof.engine.debug_log import log as _dlog
        snap_parts = []
        for i, pg in enumerate(doc.pages):
            b = find_document_body_on_page(pg)
            if b is None:
                snap_parts.append(f"p{i}=<no body>")
            else:
                txt = b.text or ""
                snap_parts.append(f"p{i}_len={len(txt)}_tail={txt[-15:]!r}")
        _dlog("paginate.entry",
               focus_page=focus_page, focus_cursor=focus_cursor,
               pages=len(doc.pages),
               body_paras=len(doc.body.paragraphs or []),
               snapshot=" | ".join(snap_parts))
    except Exception: pass

    # Step 1: migrate legacy boxes
    if migrate_legacy_doc_boxes(doc):
        result['changed'] = True

    # Step 2: sync per-page edits → body.paragraphs
    # v4.1.23.53: skip when the caller already synced AND set canonical
    # paragraph flags (e.g. a Ctrl+Enter hard break sets page_break_before on
    # doc.body just before calling us). Re-running the sync here would rebuild
    # the paragraphs from the page bodies and wipe that just-set flag, which
    # made Ctrl+Enter stop creating a page.
    if not skip_sync:
        _sync_body_from_textboxes(doc)
    paragraphs = doc.body.paragraphs or []

    # Step 3: layout body content
    bx, by, bw, bh = _body_rect_mm(doc)
    # v4.1.23.42: pagination MUST run at the SAME dpi the result will be
    # rendered at. Text width is measured by the font engine in integer
    # pixels, so word-wrap boundaries (and thus line counts) shift slightly
    # between e.g. 96 and 150 dpi. If pagination uses 96 but the on-screen
    # inline editor renders at the screen dpi (often 150), a page that
    # "fits" during pagination wraps one line longer when drawn → the last
    # line spills past the bottom margin. The caller passes its render dpi.
    if dpi is None:
        dpi = float(getattr(doc, 'preferred_dpi', 96.0) or 96.0)
    else:
        dpi = float(dpi)
    w_px = mm_to_px(bw, dpi)
    h_px = mm_to_px(bh, dpi)

    # Reference body style: take from first existing body, or default
    ref_body = None
    for pg in doc.pages:
        b = find_document_body_on_page(pg)
        if b is not None:
            ref_body = b; break
    ref_style = ref_body.style if ref_body is not None else None
    body_style = ref_style or _copy.deepcopy(doc.pages[0].objects[0].style) \
                  if doc.pages and doc.pages[0].objects \
                  and isinstance(doc.pages[0].objects[0], TextBox) else None
    if body_style is None:
        from edof.format.styles import TextStyle
        body_style = TextStyle()
        body_style.font_family = "Arial"
        body_style.font_size = 3.881
        body_style.line_height = 1.15
        body_style.padding = 0.0

    pt_mm = getattr(body_style, 'padding_top', None) or body_style.padding or 0
    pb_mm = getattr(body_style, 'padding_bot', None) or body_style.padding or 0
    pt_px = mm_to_px(pt_mm, dpi)
    pb_px = mm_to_px(pb_mm, dpi)
    inner_h = max(1.0, h_px - pt_px - pb_px)

    # Caret as a global character index over the entire body flow.
    global_cursor: Optional[int] = None
    if focus_page is not None and focus_cursor is not None:
        prefix = 0
        for i, pg in enumerate(doc.pages):
            tb = find_document_body_on_page(pg)
            if tb is None: continue
            if i == focus_page:
                global_cursor = prefix + int(focus_cursor)
                break
            tx = runs_text(tb.runs or [])
            prefix += len(tx)
            # v4.1.23.11: NO cross-page implicit '\n' adjustment. Since
            # 4.1.23.10 the body flow is the direct concatenation of each
            # page's slice (sync inserts no separators), so the global
            # offset of a position on a later page is simply the sum of
            # the prior slices' lengths plus the local offset. The old
            # "+1 when a page doesn't end in \n" overcounted by one and
            # mis-placed the caret after edits on page 2+.

    # Build the flat run stream and layout at infinite height.
    all_runs = _runs_from_paragraphs(paragraphs, 0, len(paragraphs))
    flat = runs_text(all_runs)
    pa = getattr(ref_body, 'paragraph_alignments', None) if ref_body else {}
    pa = pa or {}
    HUGE_H = 1e7
    layout = layout_runs(all_runs, body_style, 0, 0, w_px, HUGE_H, dpi,
                          paragraph_alignments=pa)

    # Compute paragraph char ranges in flat
    para_start: List[int] = []
    running = 0
    for i, p in enumerate(paragraphs):
        para_start.append(running)
        running += len(p.plain_text())
        if i < len(paragraphs) - 1:
            running += 1

    # Build per-line info
    line_info: List[Dict[str, Any]] = []
    flat_pos = 0
    if layout.lines:
        cur_para_for_line = 0
        for li, line in enumerate(layout.lines):
            if line.chars:
                first_idx = line.chars[0].char_idx
                last_idx = max(c.char_idx for c in line.chars)
                flat_pos = last_idx + 1
            else:
                first_idx = flat_pos
                last_idx = flat_pos - 1
            while (cur_para_for_line + 1 < len(para_start)
                    and para_start[cur_para_for_line + 1] <= first_idx):
                cur_para_for_line += 1
            is_first = (cur_para_for_line < len(paragraphs)
                          and first_idx == para_start[cur_para_for_line])
            line_info.append({
                'first_char': first_idx,
                'last_char':  last_idx,
                'height':     float(line.height),
                'para_idx':   cur_para_for_line,
                'is_first_of_para': is_first,
                'is_last_of_para':  False,
                'is_trailing_virtual': (not line.chars
                                          and li == len(layout.lines) - 1),
            })
        for i in range(len(line_info)):
            if i + 1 < len(line_info):
                line_info[i]['is_last_of_para'] = (
                    line_info[i + 1]['para_idx'] > line_info[i]['para_idx'])
            else:
                line_info[i]['is_last_of_para'] = True
        # Per-line needed height including space_before/after
        for info in line_info:
            para = paragraphs[info['para_idx']] if info['para_idx'] < len(paragraphs) else None
            extra = 0.0
            if para is not None:
                if info['is_first_of_para'] and para.space_before_mm:
                    extra += mm_to_px(para.space_before_mm, dpi)
                if info['is_last_of_para'] and para.space_after_mm:
                    extra += mm_to_px(para.space_after_mm, dpi)
            info['needed_h'] = info['height'] + extra

    # v4.1.23.9: overflow tolerance. With document-body padding forced
    # v4.1.23.18: strict Word-like fit. A line belongs to this page only
    # when it fits ENTIRELY inside the body, i.e. its bottom edge
    # (used_h + this line's own height) is within inner_h. Each line
    # contributes its OWN height (needed_h, derived from that line's font
    # size and line spacing), so mixed font sizes paginate correctly and
    # NO line ever dips below the bottom margin, regardless of font size.
    # A small epsilon absorbs float-rounding noise.
    overflow_tolerance = 0.5

    # Tentative line walk → line_chunks
    line_chunks: List[Tuple[int, int]] = []
    if not line_info:
        line_chunks = [(0, 0)]
    else:
        chunk_start_li = 0
        used_h = 0.0
        for li, info in enumerate(line_info):
            para = paragraphs[info['para_idx']] if info['para_idx'] < len(paragraphs) else None
            forced = (info['is_first_of_para']
                       and para is not None
                       and para.page_break_before
                       and li > chunk_start_li)
            cursor_here = (global_cursor is not None
                            and global_cursor == info['first_char'])
            needed = info['needed_h']
            # Overflow when this line's BOTTOM (used_h + its own height)
            # exceeds the body. This keeps the whole line inside the text
            # area at any font size.
            overflows = (used_h + needed > inner_h + overflow_tolerance
                          and li > chunk_start_li)
            if forced:
                line_chunks.append((chunk_start_li, li))
                chunk_start_li = li
                used_h = needed
            elif overflows:
                # --- v4.1.23.15/.30: plain Word-like STRICT pagination. ---
                #
                # A line either fits on the current page (its bottom edge is
                # within the body) or the WHOLE line flows to the next page.
                # No line is ever kept past the bottom margin. The caret simply
                # follows its line to whichever page that line lands on, and the
                # editor view follows the caret (idle hop). This is fully
                # deterministic: page breaks depend only on content, not on
                # where the caret is, so there is no oscillation, no run of
                # lines hanging below the margin, and no block of lines that
                # appears to vanish when a break finally happens.
                #
                # v4.1.23.28/.29 had a "caret tail dip" that kept the caret's
                # line (and its wrapped paragraph tail) on the current page to
                # avoid a forward jump while typing. It caused worse problems:
                # a long paragraph stayed many lines below the margin and then
                # jumped all at once, and the boundary line hopped between
                # pages as the caret moved. Removed in favor of strict breaks.
                #
                # The one exception is a TRAILING VIRTUAL line (the caret's
                # empty landing slot after the final '\n') with NO caret on it:
                # that happens only for a loaded/blurred document, where making
                # a new page just to hold an invisible empty slot would be a
                # spurious extra page. In that case we drop it. When the caret
                # IS on it (editing at the very bottom), it breaks normally so
                # the caret moves to line 1 of the next page, like pressing
                # Enter at the bottom of a full page in Word.
                if info['is_trailing_virtual'] and not cursor_here:
                    break
                line_chunks.append((chunk_start_li, li))
                chunk_start_li = li
                used_h = needed
            else:
                used_h += needed
        line_chunks.append((chunk_start_li, len(line_info)))

        # Post-process: keep_lines, keep_next, widow/orphan. All are now
        # capacity-aware: a line/paragraph is only pushed to the next page when
        # that page still has room. Without this guard the widow/orphan pass
        # grew pages past their height (every pasted paragraph had the control
        # on), the capacity guard below then re-split them, and the leftovers
        # landed on near-empty 1-2 line pages.
        _apply_keep_lines(line_chunks, line_info, paragraphs,
                          inner_h, overflow_tolerance)
        _apply_keep_next(line_chunks, line_info, paragraphs,
                         inner_h, overflow_tolerance)
        _apply_widow_orphan(line_chunks, line_info, paragraphs,
                            inner_h, overflow_tolerance)
        # v4.1.23.40: FINAL capacity guard. keep_next / widow-orphan move lines
        # onto the following page to avoid orphans/widows, but they did not
        # check that the following page still fits — so a page could end up
        # with more lines than its height allows and text spilled past the
        # bottom margin (and got clipped on export/print). Re-split any chunk
        # that now exceeds the body height, pushing the overflow forward. This
        # guarantees no line ever sits below the margin, overriding the
        # widow/orphan reflow only where the two would conflict.
        line_chunks = _enforce_capacity(
            line_chunks, line_info, inner_h, overflow_tolerance)

    # Convert line_chunks → char chunks
    chunks: List[Tuple[int, int]] = []
    for s, e in line_chunks:
        if s >= e:
            pos = line_info[s]['first_char'] if s < len(line_info) else len(flat)
            chunks.append((pos, pos))
            continue
        sc = line_info[s]['first_char']
        if e < len(line_info):
            ec = line_info[e]['first_char']
        else:
            ec = len(flat)
        chunks.append((sc, ec))

    # v4.1.23.5: when the user just deleted at the start of a non-first page
    # so the content now fits on the previous page, the natural chunk count
    # drops by one and the cursor would suddenly hop back. To keep the UX
    # smooth, append an empty trailing chunk for the focus page so it stays
    # alive (empty) and the cursor stays put. Only triggers in the precise
    # boundary case: focus_page is exactly one past the last content chunk
    # AND the focus cursor is at offset 0 of the (now empty) page. A second
    # backspace will then merge the empty page back to the previous one.
    if (focus_page is not None
            and focus_cursor is not None
            and focus_page == len(chunks)
            and int(focus_cursor) == 0
            and len(chunks) > 0):
        end_pos = chunks[-1][1]
        chunks.append((end_pos, end_pos))

    needed_pages = max(1, len(chunks))
    # v4.1.23.52: record, per chunk/page, whether it STARTS at a hard page
    # break (a paragraph with page_break_before). _sync_body_from_textboxes
    # needs this so that, when the user appends text to the end of the page
    # BEFORE a hard break (which removes that page's trailing newline), it can
    # re-insert the paragraph separator instead of fusing the text onto the
    # next page's break paragraph.
    chunk_hard_break: List[bool] = []
    for ci, (s, e) in enumerate(line_chunks):
        hb = False
        if ci > 0 and s < len(line_info):
            info_s = line_info[s]
            p_idx = info_s.get('para_idx', -1)
            if (info_s.get('is_first_of_para')
                    and 0 <= p_idx < len(paragraphs)
                    and paragraphs[p_idx].page_break_before):
                hb = True
        chunk_hard_break.append(hb)
    cp = doc.pages[0] if doc.pages else None
    while len(doc.pages) < needed_pages:
        if cp is None:
            cp = doc.add_page()
            result['changed'] = True
        else:
            new_pg = doc.add_page(cp.width, cp.height)
            new_pg.background = tuple(getattr(cp, 'background', (255, 255, 255, 255)))
            result['changed'] = True

    # Step 4: write each page's body + header/footer
    cursor_page = None
    cursor_offset = None
    for i, (start, end) in enumerate(chunks):
        pg = doc.pages[i]
        body = find_document_body_on_page(pg)
        if body is None:
            body = _make_body_textbox(doc, ref_style=body_style)
            body.name = f"document_body"
            pg.objects.append(body)
            result['changed'] = True
        else:
            # Make sure geometry matches current section settings
            if (body.transform.x != bx or body.transform.y != by
                or body.transform.width != bw or body.transform.height != bh):
                body.transform.x = bx; body.transform.y = by
                body.transform.width = bw; body.transform.height = bh
                result['changed'] = True

        # Build slice
        if start == 0 and end == len(flat):
            slice_runs = [_copy.deepcopy(r) for r in all_runs]
        else:
            _, after_start = split_runs_at_char(all_runs, start)
            seg_len = end - start
            after_len = len(runs_text(after_start))
            if seg_len >= after_len:
                slice_runs = after_start
            else:
                slice_runs, _ = split_runs_at_char(after_start, seg_len)
        slice_text = runs_text(slice_runs)

        if (body.text or "") != slice_text:
            body.runs = slice_runs
            body.text = slice_text
            result['changed'] = True
        else:
            body.runs = slice_runs

        # v4.1.23.52: tag whether this page begins a brand-new paragraph due to
        # a hard page break, so the body-sync can keep it separate from the
        # previous page even after the user edits across the boundary.
        try:
            body._hard_break_before = bool(chunk_hard_break[i]) if i < len(chunk_hard_break) else False
        except Exception:
            pass
        # v4.1.23.54: tag whether this body continues onto a later page. The
        # static renderer uses it to suppress the trailing virtual caret line
        # (the empty slot a text ending in '\n' would otherwise show), which on
        # a CONTINUING page sat in the bottom margin and looked like overflow.
        try:
            body._continues = (i < len(chunks) - 1)
        except Exception:
            pass

        # Map global cursor to this page
        if global_cursor is not None and cursor_page is None:
            is_last = (i == len(chunks) - 1)
            # v4.1.23.50/.51: a caret EXACTLY on a page boundary normally falls
            # onto the NEXT page. For ordinary typing/Enter we want it to stay
            # on the page being edited (so pressing Enter at the end of a page,
            # especially before a hard break, does not teleport to the next
            # page). But a HARD page break (Ctrl+Enter) explicitly wants to
            # ADVANCE to the new page, so that path leaves this flag off.
            on_focus_boundary = (boundary_to_focus_page
                                  and global_cursor == end
                                  and focus_page is not None
                                  and i == int(focus_page))
            # v4.1.23.55: but only KEEP the caret on the focus page when that
            # page still has room for the caret's line. If the page is full
            # (the line the caret sits on was pushed to the next page by
            # overflow), staying would drop the caret below the bottom margin —
            # the exact "cursor under the margin while typing" bug. In that
            # case fall through so the caret advances to the next page where
            # its line actually lives. A page with room (e.g. a short page just
            # before a hard break) still keeps the caret, so Enter there does
            # not teleport away.
            if on_focus_boundary and i < len(line_chunks):
                s_li, e_li = line_chunks[i]
                if e_li > s_li:
                    used_h_here = _chunk_height(line_info, s_li, e_li)
                    last_h = line_info[e_li - 1].get(
                        'needed_h', line_info[e_li - 1].get('height', 0.0))
                    if used_h_here + last_h > inner_h + overflow_tolerance:
                        on_focus_boundary = False
            in_range = (start <= global_cursor < end) or (
                is_last and global_cursor == end) or on_focus_boundary
            if in_range:
                off = global_cursor - start
                if off < 0: off = 0
                if off > len(slice_text): off = len(slice_text)
                cursor_page = i
                cursor_offset = off

        # Header / footer for this page
        _ensure_header_footer(doc, pg, i, needed_pages, ref_style=body_style)

    # Clear bodies on pages beyond needed
    for i in range(needed_pages, len(doc.pages)):
        body = find_document_body_on_page(doc.pages[i])
        if body is not None and (body.runs or body.text):
            body.runs = []
            body.text = ""
            result['changed'] = True

    # Fallback cursor placement. Normally cursor_page is resolved during
    # the slice loop; if not (e.g. focus_page was stale / out of range
    # after content shrank), clamp it to a valid page so the caller never
    # gets a None cursor_page.
    if focus_page is not None and cursor_page is None:
        clamped = max(0, min(int(focus_page), len(doc.pages) - 1))
        cursor_page = clamped
        cursor_offset = 0

    # Step 5: prune trailing empty pages (preserve overlays & focus)
    while len(doc.pages) > max(needed_pages, 1):
        idx = len(doc.pages) - 1
        if focus_page == idx or cursor_page == idx:
            break
        pg = doc.pages[idx]
        body = find_document_body_on_page(pg)
        header = find_document_header_on_page(pg)
        footer = find_document_footer_on_page(pg)
        # Count overlays = anything that isn't a doc-mode box
        overlays = [o for o in pg.objects
                     if o is not body and o is not header and o is not footer]
        if overlays:
            break
        if body is not None and runs_text(body.runs or []):
            break
        doc.pages.pop()
        result['changed'] = True

    result['pages_count']    = len(doc.pages)
    result['cursor_page']    = cursor_page
    result['cursor_offset']  = cursor_offset

    # v4.1.23.1-debug: paginate exit snapshot
    try:
        from edof.engine.debug_log import log as _dlog
        snap_parts = []
        for i, pg in enumerate(doc.pages):
            b = find_document_body_on_page(pg)
            if b is not None:
                txt = b.text or ""
                snap_parts.append(f"p{i}_len={len(txt)}_tail={txt[-15:]!r}")
        _dlog("paginate.exit",
               changed=result['changed'],
               pages=result['pages_count'],
               cursor_page=cursor_page,
               cursor_offset=cursor_offset,
               snapshot=" | ".join(snap_parts))
    except Exception: pass

    return result


def _ensure_header_footer(doc, pg, page_idx: int, page_count: int,
                            ref_style=None) -> None:
    """For one page: add/remove the DocumentHeaderBox / DocumentFooterBox
    according to doc.body.header_enabled / footer_enabled, and fill in
    their runs with variables resolved for this page index."""
    body = doc.body
    # Header
    existing_h = find_document_header_on_page(pg)
    if body.header_enabled:
        if existing_h is None:
            existing_h = _make_header_textbox(doc, ref_style=ref_style)
            pg.objects.insert(0, existing_h)
        else:
            # Ensure geometry up to date
            hx, hy, hw, hh = _header_rect_mm(doc)
            existing_h.transform.x = hx; existing_h.transform.y = hy
            existing_h.transform.width = hw; existing_h.transform.height = hh
        resolved = resolve_template_runs(body.header_runs,
                                            page_idx, page_count)
        existing_h.runs = resolved
        existing_h.text = runs_text(resolved)
    elif existing_h is not None:
        pg.objects.remove(existing_h)

    # Footer
    existing_f = find_document_footer_on_page(pg)
    if body.footer_enabled:
        if existing_f is None:
            existing_f = _make_footer_textbox(doc, ref_style=ref_style)
            pg.objects.append(existing_f)
        else:
            fx, fy, fw, fh = _footer_rect_mm(doc)
            existing_f.transform.x = fx; existing_f.transform.y = fy
            existing_f.transform.width = fw; existing_f.transform.height = fh
        resolved = resolve_template_runs(body.footer_runs,
                                            page_idx, page_count)
        existing_f.runs = resolved
        existing_f.text = runs_text(resolved)
    elif existing_f is not None:
        pg.objects.remove(existing_f)


# ────────────────────────────────────────────────────────────────────────
# Pagination rules (post-process passes)
# ────────────────────────────────────────────────────────────────────────

def _enforce_capacity(line_chunks, line_info, inner_h, tol):
    """v4.1.23.40: ensure no chunk's lines exceed the page body height.
    Walks each chunk; if the accumulated line heights pass inner_h, the chunk
    is cut there and the remaining lines become a new following chunk. Runs as
    the LAST pagination step so the no-overflow guarantee always holds, even
    after keep_next / widow-orphan have pushed lines around."""
    queue = [c for c in line_chunks if c[1] > c[0]]
    if not queue:
        return list(line_chunks)
    result = []
    queue = list(queue)
    while queue:
        s, e = queue.pop(0)
        used = 0.0
        cut = e
        for li in range(s, e):
            h = line_info[li].get('needed_h', line_info[li].get('height', 0.0))
            if used + h > inner_h + tol and li > s:
                cut = li
                break
            used += h
        result.append((s, cut))
        if cut < e:
            queue.insert(0, (cut, e))
    return result


def _chunk_height(line_info, s, e):
    return sum(line_info[i].get('needed_h', line_info[i].get('height', 0.0))
               for i in range(s, e))


def _apply_keep_lines(line_chunks, line_info, paragraphs, inner_h, tol):
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False; guard += 1
        for ci in range(len(line_chunks) - 1):
            s, e = line_chunks[ci]
            if e <= s: continue
            last_li = e - 1
            if line_info[last_li]['is_last_of_para']: continue
            pi = line_info[last_li]['para_idx']
            para = paragraphs[pi] if pi < len(paragraphs) else None
            if para is None or not para.keep_lines: continue
            first_li = last_li
            while first_li > s and line_info[first_li - 1]['para_idx'] == pi:
                first_li -= 1
            if first_li <= s: continue
            ns, ne = line_chunks[ci + 1]
            # capacity: the moved tail must fit on the next page
            if (_chunk_height(line_info, ns, ne)
                    + _chunk_height(line_info, first_li, e) > inner_h + tol):
                continue
            line_chunks[ci] = (s, first_li)
            line_chunks[ci + 1] = (first_li, ne)
            changed = True
            break


def _apply_keep_next(line_chunks, line_info, paragraphs, inner_h, tol):
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False; guard += 1
        for ci in range(len(line_chunks) - 1):
            s, e = line_chunks[ci]
            if e <= s: continue
            last_li = e - 1
            if not line_info[last_li]['is_last_of_para']: continue
            pi = line_info[last_li]['para_idx']
            para = paragraphs[pi] if pi < len(paragraphs) else None
            if para is None or not para.keep_next: continue
            ns, ne = line_chunks[ci + 1]
            if ne <= ns: continue
            if line_info[ns]['para_idx'] != pi + 1: continue
            first_li_n = last_li
            while first_li_n > s and line_info[first_li_n - 1]['para_idx'] == pi:
                first_li_n -= 1
            if first_li_n <= s: continue
            if (_chunk_height(line_info, ns, ne)
                    + _chunk_height(line_info, first_li_n, e) > inner_h + tol):
                continue
            line_chunks[ci]     = (s, first_li_n)
            line_chunks[ci + 1] = (first_li_n, ne)
            changed = True
            break


def _apply_widow_orphan(line_chunks, line_info, paragraphs, inner_h, tol):
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False; guard += 1
        for ci in range(len(line_chunks) - 1):
            s, e = line_chunks[ci]
            ns, ne = line_chunks[ci + 1]
            if e <= s or ne <= ns: continue
            last_li = e - 1
            if line_info[last_li]['is_last_of_para']: continue
            pi = line_info[last_li]['para_idx']
            para = paragraphs[pi] if pi < len(paragraphs) else None
            if para is None or not para.widow_orphan_control: continue
            lines_here = 0
            i = last_li
            while i >= s and line_info[i]['para_idx'] == pi:
                lines_here += 1; i -= 1
            lines_next = 0
            j = ns
            while j < ne and line_info[j]['para_idx'] == pi:
                lines_next += 1; j += 1
            want = (lines_here == 1 and lines_next >= 2) or \
                   (lines_next == 1 and lines_here >= 2)
            if not want:
                continue
            # capacity: pushing the last line to the next page must not
            # overflow it — otherwise the fix would be worse than the widow.
            moved_h = line_info[e - 1].get(
                'needed_h', line_info[e - 1].get('height', 0.0))
            if _chunk_height(line_info, ns, ne) + moved_h > inner_h + tol:
                continue
            line_chunks[ci]     = (s, e - 1)
            line_chunks[ci + 1] = (e - 1, ne)
            changed = True; break
