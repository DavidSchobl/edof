# edof/engine/textbox_flow.py
"""
v4.1.22: Lightweight overflow-to-next-page flow for document mode.

This is NOT the full DocumentBody flow engine (that's a longer-term piece
in edof/engine/document_flow.py). Instead, this module provides the
minimum tooling to make doc-mode body textboxes behave like a Word
document: when a body overflows its page, the overflowing paragraphs
move to the next page's body automatically.

Public helpers:
    runs_text(runs)                       → str
    split_runs_at_paragraph(runs, idx)    → (head_runs, tail_runs)
    find_overflow_paragraph(runs, style,
                              w_px, h_px, dpi,
                              paragraph_alignments)
                                          → int | None
    auto_reflow_body(doc, page_idx, body) → reflow result dict

The reflow result is informational and used by the editor to decide
whether to switch pages / re-enter inline edit.
"""
from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any
import copy as _copy

from edof.format.styles import TextRun


def runs_text(runs: List["TextRun"]) -> str:
    """Concatenate run texts into a single flat string."""
    return "".join(r.text for r in (runs or []))


def _strip_trailing_newline_runs(runs: List["TextRun"]) -> List["TextRun"]:
    """v4.1.22.5: return a copy of `runs` with one trailing '\\n' removed
    from the very last run that has any text. Used by the auto-reflow
    when the user pressed Enter at the bottom of a full page — the
    trailing '\\n' belongs logically to the next page, not the one being
    completed."""
    out = [_copy.deepcopy(r) for r in (runs or [])]
    for i in range(len(out) - 1, -1, -1):
        if out[i].text:
            if out[i].text.endswith('\n'):
                out[i].text = out[i].text[:-1]
                if not out[i].text:
                    out.pop(i)
            break
    return out


def split_runs_at_paragraph(runs: List["TextRun"],
                             paragraph_idx: int
                             ) -> Tuple[List["TextRun"], List["TextRun"]]:
    """Split runs into two lists at the START of paragraph `paragraph_idx`.

    Paragraph 0 begins at offset 0; subsequent paragraphs begin right after
    each '\\n' character. The split keeps the '\\n' separator on the HEAD
    side (which is the standard behaviour — '\\n' terminates a paragraph).

    Returns (head_runs, tail_runs). Either may be empty.
    """
    if not runs:
        return [], []
    if paragraph_idx <= 0:
        return [], [_copy.deepcopy(r) for r in runs]

    # Find character offset of the start of paragraph_idx
    # = the position right after the (paragraph_idx-1)-th '\n'
    flat = runs_text(runs)
    if paragraph_idx > flat.count('\n'):
        # Asking for paragraph beyond the end → nothing to split off
        return [_copy.deepcopy(r) for r in runs], []
    # Walk to the paragraph_idx-th '\n'
    nl_seen = 0
    split_offset = len(flat)
    for i, ch in enumerate(flat):
        if ch == '\n':
            nl_seen += 1
            if nl_seen == paragraph_idx:
                split_offset = i + 1   # right after this \n
                break

    # Split runs at character offset
    head: List[TextRun] = []
    tail: List[TextRun] = []
    cur_offset = 0
    for r in runs:
        rt = r.text or ""
        r_start = cur_offset
        r_end = cur_offset + len(rt)
        if r_end <= split_offset:
            head.append(_copy.deepcopy(r))
        elif r_start >= split_offset:
            tail.append(_copy.deepcopy(r))
        else:
            # Run straddles the split — break into two
            inside = split_offset - r_start
            r_head = _copy.deepcopy(r); r_head.text = rt[:inside]
            r_tail = _copy.deepcopy(r); r_tail.text = rt[inside:]
            if r_head.text: head.append(r_head)
            if r_tail.text: tail.append(r_tail)
        cur_offset = r_end
    return head, tail


def split_runs_at_char(runs: List["TextRun"],
                        char_offset: int
                        ) -> Tuple[List["TextRun"], List["TextRun"]]:
    """v4.1.22.6: split runs at an arbitrary character offset (not
    necessarily a paragraph boundary). Used by mid-paragraph reflow when
    a single overlong paragraph wraps beyond the page — we split at the
    visual line boundary inside that paragraph."""
    if not runs:
        return [], []
    flat = runs_text(runs)
    char_offset = max(0, min(len(flat), char_offset))
    if char_offset == 0:
        return [], [_copy.deepcopy(r) for r in runs]
    if char_offset >= len(flat):
        return [_copy.deepcopy(r) for r in runs], []
    head: List[TextRun] = []
    tail: List[TextRun] = []
    cur_offset = 0
    for r in runs:
        rt = r.text or ""
        r_start = cur_offset
        r_end = cur_offset + len(rt)
        if r_end <= char_offset:
            head.append(_copy.deepcopy(r))
        elif r_start >= char_offset:
            tail.append(_copy.deepcopy(r))
        else:
            inside = char_offset - r_start
            r_head = _copy.deepcopy(r); r_head.text = rt[:inside]
            r_tail = _copy.deepcopy(r); r_tail.text = rt[inside:]
            if r_head.text: head.append(r_head)
            if r_tail.text: tail.append(r_tail)
        cur_offset = r_end
    return head, tail


def find_overflow_char_idx(runs: List["TextRun"],
                              parent_style,
                              box_w_px: float,
                              box_h_px: float,
                              dpi: float,
                              paragraph_alignments: Optional[Dict[str, str]] = None
                              ) -> Optional[int]:
    """v4.1.22.6: return the character index where the first overflowing
    visual line BEGINS (or None if content fits). This is the right
    split point even when the overflow is inside a single paragraph (in
    which case `find_overflow_paragraph` would return 0 and reflow would
    be stuck)."""
    from edof.engine.text_layout import layout_runs
    paragraph_alignments = paragraph_alignments or {}
    layout = layout_runs(
        runs, parent_style,
        0.0, 0.0, float(box_w_px), float(box_h_px), dpi,
        paragraph_alignments=paragraph_alignments)
    if not getattr(layout, 'overflow_v', False):
        return None
    inner_h = layout.inner_h
    for line in layout.lines:
        if line.top + line.height > inner_h + 0.5:
            if line.chars:
                return line.chars[0].char_idx
            for c in getattr(layout, 'chars', []):
                if c.line_idx == line.line_idx:
                    return c.char_idx
            return len(runs_text(runs))
    return None


def find_overflow_paragraph(runs: List["TextRun"],
                              parent_style,
                              box_w_px: float,
                              box_h_px: float,
                              dpi: float,
                              paragraph_alignments: Optional[Dict[str, str]] = None
                              ) -> Optional[int]:
    """Return the paragraph index of the first paragraph that does not fit
    entirely inside (box_w_px × box_h_px) at the given DPI, or None if the
    content fits.

    Implementation: layout the runs at the natural box size and find the
    first line whose vertical extent (top + height) exceeds inner_h.
    Convert that line's first-character offset to a paragraph index by
    counting '\\n' chars before it.
    """
    from edof.engine.text_layout import layout_runs
    paragraph_alignments = paragraph_alignments or {}
    layout = layout_runs(
        runs, parent_style,
        0.0, 0.0, float(box_w_px), float(box_h_px), dpi,
        paragraph_alignments=paragraph_alignments)
    if not getattr(layout, 'overflow_v', False):
        return None
    inner_h = layout.inner_h
    # Build flat text for paragraph index lookup
    flat = runs_text(runs)
    for line in layout.lines:
        if line.top + line.height > inner_h + 0.5:
            # First char in this line — find its char_idx
            if line.chars:
                first_idx = line.chars[0].char_idx
            else:
                # Empty line — walk chars to find one with matching line_idx
                first_idx = None
                for c in getattr(layout, 'chars', []):
                    if c.line_idx == line.line_idx:
                        first_idx = c.char_idx; break
                if first_idx is None:
                    first_idx = len(flat)
            para = flat[:first_idx].count('\n')
            return para
    return None


def auto_reflow_body(doc, page_idx: int, body,
                     cursor_offset: Optional[int] = None
                     ) -> Dict[str, Any]:
    """Reflow body's overflowing paragraphs to the next page's body.

    v4.1.22.2: cascading — if the next page's body still overflows after
    receiving the tail, recurse and split it again, creating as many
    pages as needed in a single call. This prevents the "blinking
    status / one-page-per-second" UX users saw in 4.1.22.

    v4.1.22.2: if `cursor_offset` is provided (an int char-offset inside
    `body.runs` BEFORE the reflow), the function tracks where the cursor
    ends up after all splits and returns `final_cursor_page_idx` +
    `final_cursor_offset_in_body` so the caller can re-position the
    user's caret on the correct page.

    Returns a dict:
        {
            'reflowed': bool,
            'split_at_paragraph': int | None,        # first split (info)
            'pages_added': int,                       # cumulative
            'pages_touched': list[int],               # all destination pages
            'new_page_idx': int | None,               # where the FIRST tail
                                                       # landed
            'next_body_id':  str | None,              # FIRST tail's body
            'created_page':  bool,                    # any new page made
            'final_cursor_page_idx': int | None,      # where cursor wound up
            'final_cursor_offset_in_body': int | None,
        }
    """
    from edof.engine.transform import mm_to_px
    from edof.format.objects import TextBox

    result = {
        'reflowed': False, 'split_at_paragraph': None,
        'pages_added': 0, 'pages_touched': [],
        'new_page_idx': None, 'next_body_id': None,
        'created_page': False,
        'final_cursor_page_idx': None,
        'final_cursor_offset_in_body': None,
    }
    if doc is None or body is None or not getattr(body, 'runs', None):
        return result

    dpi = float(getattr(doc, 'preferred_dpi', 96.0) or 96.0)

    # Track cursor through cascade
    cur_page_idx = page_idx
    cur_body = body
    cur_cursor_offset = cursor_offset
    first_iteration = True

    while True:
        w_px = mm_to_px(cur_body.transform.width,  dpi)
        h_px = mm_to_px(cur_body.transform.height, dpi)
        pa = getattr(cur_body, 'paragraph_alignments', None) or {}
        overflow_para = find_overflow_paragraph(
            cur_body.runs, cur_body.style, w_px, h_px, dpi, pa)
        if overflow_para is None:
            # No overflow — done
            if cur_cursor_offset is not None and result['final_cursor_page_idx'] is None:
                result['final_cursor_page_idx'] = cur_page_idx
                result['final_cursor_offset_in_body'] = cur_cursor_offset
            break

        empty_tail_new_page = False
        mid_paragraph_split = False
        head: Optional[List["TextRun"]] = None
        tail: Optional[List["TextRun"]] = None

        if overflow_para > 0:
            head, tail = split_runs_at_paragraph(cur_body.runs, overflow_para)
            if not tail:
                cur_text_full = runs_text(cur_body.runs)
                if cur_text_full.endswith('\n'):
                    # v4.1.22.5 empty-tail-new-page handling
                    head = _strip_trailing_newline_runs(head)
                    empty_tail_new_page = True
                    cur_cursor_offset = 0
                else:
                    break    # unsplittable
        else:
            # v4.1.22.6: overflow is inside paragraph 0 (or any single
            # paragraph that wraps beyond the page). Fall back to a mid-
            # paragraph split at the first overflowing visual line. The
            # paragraph effectively becomes two — the boundary is implicit
            # (no '\n' inserted), so reflow can keep moving the tail to
            # following pages until everything fits.
            split_char = find_overflow_char_idx(
                cur_body.runs, cur_body.style, w_px, h_px, dpi, pa)
            if split_char is None or split_char <= 0:
                break    # nothing to do
            head, tail = split_runs_at_char(cur_body.runs, split_char)
            if not tail:
                break
            mid_paragraph_split = True

        head_text_len = len(runs_text(head))

        # Where does cursor land relative to head/tail?
        cursor_in_tail = None
        cursor_stays_here = False
        if empty_tail_new_page:
            # Special: trailing-\n overflow → caret always hops to next page
            cursor_in_tail = 0
        elif cur_cursor_offset is not None:
            if cur_cursor_offset <= head_text_len:
                cursor_stays_here = True   # cursor is in head → stays in this body
            else:
                cursor_in_tail = cur_cursor_offset - head_text_len

        # Write head back to cur_body
        cur_body.runs = head
        cur_body.text = runs_text(head)

        # Find / create next page body
        next_idx = cur_page_idx + 1
        created_here = False
        if next_idx >= len(doc.pages):
            cp = doc.pages[cur_page_idx]
            new_pg = doc.add_page(cp.width, cp.height)
            new_pg.background = tuple(getattr(cp, 'background', (255,255,255,255)))
            created_here = True
        new_pg = doc.pages[next_idx]

        next_body = None
        for o in new_pg.objects:
            name = getattr(o, 'name', '') or ''
            if isinstance(o, TextBox) and (
                name in ('document_body', 'doc_body') or name.startswith('doc_body')):
                next_body = o; break
        if next_body is None:
            # v4.1.22.10: mirror the dimensions of the body we just split
            # from. Previously this read doc.body.page_margins_mm whose
            # default (25.4mm = 1") doesn't match the user's actual body
            # (e.g. 10mm), causing cascaded pages to have wrong-sized
            # bodies and fit fewer paragraphs.
            tb = TextBox()
            tb.transform.x      = cur_body.transform.x
            tb.transform.y      = cur_body.transform.y
            tb.transform.width  = cur_body.transform.width
            tb.transform.height = cur_body.transform.height
            try: tb.style = _copy.deepcopy(cur_body.style)
            except Exception: pass
            tb.style.auto_fill = False
            tb.fill.color = None
            tb.name = f"doc_body_p{next_idx + 1}"
            new_pg.objects.append(tb)
            next_body = tb

        # Prepend tail to next_body (v4.1.22.5: but only when there IS
        # tail content — empty_tail_new_page case just hops the caret to
        # the next body without modifying it)
        if not empty_tail_new_page:
            existing = next_body.runs or []
            tail_text = runs_text(tail)
            if tail_text and not tail_text.endswith('\n') and existing and runs_text(existing):
                sep = TextRun(text='\n')
                tail = tail + [sep]
            next_body.runs = tail + existing
            next_body.text = runs_text(next_body.runs)
        else:
            # caret will sit at offset 0 of next body, no content moved
            cursor_in_tail = 0

        # Record info
        result['reflowed'] = True
        if first_iteration:
            result['split_at_paragraph'] = overflow_para
            result['new_page_idx'] = next_idx
            result['next_body_id'] = next_body.id
            first_iteration = False
        if created_here:
            result['pages_added'] += 1
            result['created_page'] = True
        result['pages_touched'].append(next_idx)

        # Resolve cursor if it stays on this page
        if cursor_stays_here and result['final_cursor_page_idx'] is None:
            result['final_cursor_page_idx'] = cur_page_idx
            result['final_cursor_offset_in_body'] = cur_cursor_offset

        # Continue cascade on the next body
        cur_page_idx = next_idx
        cur_body = next_body
        cur_cursor_offset = cursor_in_tail
        # Loop continues; if next_body fits → break

    # If we exited without resolving the cursor (e.g. cursor was in tail of
    # the FINAL split body and that body fits), it's on cur_page_idx.
    if (cursor_offset is not None
        and result['final_cursor_page_idx'] is None):
        result['final_cursor_page_idx'] = cur_page_idx
        result['final_cursor_offset_in_body'] = cur_cursor_offset
    return result


def prune_empty_trailing_pages(doc, keep_page_idx: Optional[int] = None) -> int:
    """v4.1.22.1: After a backflow/delete leaves the last page(s) empty,
    remove any trailing doc-mode pages whose only meaningful content is
    an empty document body. Returns the number of pages removed.

    Stops at the first page from the end whose body has text content OR
    whose objects list contains anything other than its doc_body.

    v4.1.22.9: if `keep_page_idx` is given, never remove that page —
    typically the page the user is actively editing (just created via
    pre-emptive Enter and not yet typed into). Without this guard, the
    idle balance pass would prune the fresh page the moment it's
    created, before the user has a chance to type anything.
    """
    from edof.format.objects import TextBox
    if doc is None or not getattr(doc, 'pages', None):
        return 0
    if getattr(doc, 'mode', '') != 'document':
        return 0
    removed = 0
    while len(doc.pages) > 1:
        last_idx = len(doc.pages) - 1
        if keep_page_idx is not None and last_idx == keep_page_idx:
            break    # user is here — leave the page alone
        pg = doc.pages[-1]
        body = None
        non_body_count = 0
        for o in pg.objects:
            name = getattr(o, 'name', '') or ''
            if isinstance(o, TextBox) and (
                name in ('document_body','doc_body') or name.startswith('doc_body')):
                if body is None:
                    body = o
                else:
                    non_body_count += 1
            else:
                non_body_count += 1
        if body is None:
            break
        if non_body_count > 0:
            break
        if runs_text(body.runs or []):
            break
        doc.pages.pop()
        removed += 1
    return removed


def _find_body_on_page(page) -> Optional["TextBox"]:
    from edof.format.objects import TextBox
    for o in page.objects:
        name = getattr(o, 'name', '') or ''
        if isinstance(o, TextBox) and (
            name in ('document_body', 'doc_body') or name.startswith('doc_body')):
            return o
    return None


def pull_paragraphs_from_next(doc, page_idx: int,
                                 body,
                                 next_cursor_offset: Optional[int] = None
                                 ) -> Dict[str, Any]:
    """v4.1.22.7: backflow — when `body` has unused vertical room and the
    next page's body has content, move whole paragraphs forward from the
    next body into this one until adding another would overflow.

    v4.1.22.10: track the caret precisely. If `next_cursor_offset` is
    given (= caret was on the NEXT page at that offset), the return dict
    contains either:
      • 'cursor_landed_in_current': X  (caret migrated INTO this body at
        offset X), OR
      • 'cursor_stays_in_next': X  (caret still on next page, offset X)
    Exactly one of those is set; both omitted means no pull happened.
    'chars_moved_from_next' = how many chars total left the next body.
    """
    from edof.engine.transform import mm_to_px
    from edof.format.styles import TextRun
    info: Dict[str, Any] = {
        'chars_moved_from_next': 0,
        'cursor_landed_in_current': None,
        'cursor_stays_in_next': None,
    }
    if doc is None or body is None: return info
    if page_idx + 1 >= len(doc.pages): return info
    next_pg = doc.pages[page_idx + 1]
    next_body = _find_body_on_page(next_pg)
    if next_body is None: return info
    next_runs = next_body.runs or []
    if not runs_text(next_runs):
        # nothing to pull, but caret may still be on next page at offset 0
        if next_cursor_offset is not None:
            info['cursor_stays_in_next'] = next_cursor_offset
        return info

    dpi = float(getattr(doc, 'preferred_dpi', 96.0) or 96.0)
    w_px = mm_to_px(body.transform.width,  dpi)
    h_px = mm_to_px(body.transform.height, dpi)
    pa = getattr(body, 'paragraph_alignments', None) or {}

    chars_moved = 0
    while True:
        nf = runs_text(next_runs)
        if not nf: break
        nl_idx = nf.find('\n')
        if nl_idx == -1:
            head_para_runs = [_copy.deepcopy(r) for r in next_runs]
            rest_runs = []
            first_para_len = len(nf)
            includes_terminator = False
        else:
            head_para_runs, rest_runs = split_runs_at_paragraph(next_runs, 1)
            first_para_len = nl_idx + 1
            includes_terminator = True

        cur_text = runs_text(body.runs or [])
        candidate = [_copy.deepcopy(r) for r in (body.runs or [])]
        sep_added = 0
        if cur_text and not cur_text.endswith('\n'):
            candidate.append(TextRun(text='\n'))
            sep_added = 1
        candidate.extend(head_para_runs)

        ov = find_overflow_paragraph(candidate, body.style,
                                       w_px, h_px, dpi, pa)
        if ov is not None:
            break    # can't fit, stop

        # ── Cursor tracking: BEFORE we commit the pull, record where the
        # caret would land if it was within this paragraph. ──
        if next_cursor_offset is not None and info['cursor_landed_in_current'] is None:
            # The chars about to leave next-body: first_para_len. If the
            # caret's offset in next is <= first_para_len, it lands in
            # CURRENT body at position: len(cur_text_pre_pull) + sep_added + offset.
            if next_cursor_offset <= first_para_len:
                # When offset == first_para_len AND includes_terminator,
                # the caret was right after the '\n'  → it's actually at
                # the START of the next paragraph. Treat as "still in next"
                # in that boundary case so the next iteration picks it up.
                if (next_cursor_offset == first_para_len
                    and includes_terminator):
                    next_cursor_offset = 0   # at start of remaining next
                else:
                    new_pos = len(cur_text) + sep_added + next_cursor_offset
                    info['cursor_landed_in_current'] = new_pos
                    next_cursor_offset = None    # consumed

        # Accept the pull
        body.runs = candidate
        body.text = runs_text(candidate)
        next_runs = rest_runs
        chars_moved += first_para_len
        if next_cursor_offset is not None:
            next_cursor_offset = max(0, next_cursor_offset - first_para_len)
        if not includes_terminator:
            break

    next_body.runs = next_runs
    next_body.text = runs_text(next_runs)
    info['chars_moved_from_next'] = chars_moved
    if next_cursor_offset is not None and info['cursor_landed_in_current'] is None:
        info['cursor_stays_in_next'] = next_cursor_offset
    return info


def balance_doc_bodies(doc,
                        anchor_page_idx: Optional[int] = None,
                        anchor_body=None,
                        cursor_offset: Optional[int] = None
                        ) -> Dict[str, Any]:
    """v4.1.22.7: top-level balance pass across all doc-body pages.

    Phase 1 (forward): for every page starting at index 0, run
    auto_reflow_body to push overflow forward. Cascades naturally if a
    body overflows after receiving content.

    Phase 2 (backward): for every page starting at index 0, run
    pull_paragraphs_from_next to fill any leftover capacity from the
    next page's content.

    Phase 3: prune trailing empty pages.

    Track the user's caret if (`anchor_body`, `cursor_offset`) is given:
    if the anchor body's content moved during balance, the returned
    final_cursor_* fields tell the caller where to put the caret.
    """
    result = {
        'final_cursor_page_idx': None,
        'final_cursor_offset_in_body': None,
        'changed': False,
    }
    if doc is None: return result
    if getattr(doc, 'mode', '') != 'document': return result

    # PHASE 1 — forward push from every body
    # Track cursor through. For non-anchor bodies, cursor_offset = None.
    new_anchor_page = anchor_page_idx
    new_anchor_offset = cursor_offset
    for i in range(len(doc.pages)):
        body = _find_body_on_page(doc.pages[i])
        if body is None: continue
        co = new_anchor_offset if i == new_anchor_page else None
        r = auto_reflow_body(doc, i, body, cursor_offset=co)
        if r.get('reflowed'):
            result['changed'] = True
        if i == new_anchor_page and r.get('reflowed'):
            tgt_page = r.get('final_cursor_page_idx')
            tgt_off  = r.get('final_cursor_offset_in_body')
            if tgt_page is not None:
                new_anchor_page = tgt_page
                new_anchor_offset = tgt_off

    # PHASE 2 — backward pull from every body
    for i in range(len(doc.pages)):
        body = _find_body_on_page(doc.pages[i])
        if body is None: continue
        # If caret is on the next page, pass its offset for tracking
        next_cur = None
        if (new_anchor_page is not None
            and new_anchor_page == i + 1
            and new_anchor_offset is not None):
            next_cur = new_anchor_offset
        info = pull_paragraphs_from_next(doc, i, body, next_cursor_offset=next_cur)
        if info['chars_moved_from_next'] > 0:
            result['changed'] = True
        # Update anchor based on where the caret landed
        if next_cur is not None:
            if info['cursor_landed_in_current'] is not None:
                new_anchor_page = i
                new_anchor_offset = info['cursor_landed_in_current']
            elif info['cursor_stays_in_next'] is not None:
                # caret still on page i+1 but at reduced offset
                new_anchor_offset = info['cursor_stays_in_next']

    # PHASE 3 — prune (but protect the anchor's page if it's currently
    # the trailing one — typical when pre-emptive Enter just created it)
    keep_idx = new_anchor_page if new_anchor_page is not None else anchor_page_idx
    pruned = prune_empty_trailing_pages(doc, keep_page_idx=keep_idx)
    if pruned:
        result['changed'] = True
        if new_anchor_page is not None and new_anchor_page >= len(doc.pages):
            new_anchor_page = max(0, len(doc.pages) - 1)

    result['final_cursor_page_idx'] = new_anchor_page
    result['final_cursor_offset_in_body'] = new_anchor_offset
    return result


# ════════════════════════════════════════════════════════════════════════
# v4.1.22.13: Word-style pagination — body.paragraphs is the SOURCE
# ════════════════════════════════════════════════════════════════════════
#
# Architectural shift from v4.1.22.11:
#
# The data model is now Word-aligned. `doc.body.paragraphs` is the
# canonical store; each page's body TextBox is a viewport that just
# displays a slice of the master paragraph list. The editor still hooks
# into a page TextBox for editing UX, but every repaginate cycle:
#
#   1. Reads the current TextBox runs and projects them BACK into
#      `doc.body.paragraphs` (preserving paragraph properties where the
#      paragraph index still makes sense).
#   2. Walks `doc.body.paragraphs` with proper pagination rules:
#        • page_break_before   — force a fresh page before this paragraph
#        • keep_next           — don't separate from the next paragraph
#        • keep_lines          — don't split a paragraph between pages
#        • widow_orphan        — protect against 1-line orphans/widows
#      while respecting per-paragraph `space_before_mm` / `space_after_mm`
#      so the visual rhythm is correct.
#   3. Writes back each page's body TextBox with its paragraph slice
#      (the viewport refresh).
#   4. Maps the caret's (page, char_offset) through the rewrite so the
#      editor lands on the same logical character.
#
# Pages that hold non-body objects (images, shapes) are always preserved.
# Trailing empty pages without other content are pruned unless they're
# the focus page (= where the user is actively editing).
# ────────────────────────────────────────────────────────────────────

def _split_runs_at_newlines(runs: List["TextRun"]) -> List[List["TextRun"]]:
    """Split a list of runs into paragraph-sized run lists at every '\\n'.
    The '\\n' chars themselves are dropped — each returned list is one
    paragraph's content without paragraph terminators."""
    paragraphs: List[List["TextRun"]] = []
    cur: List["TextRun"] = []
    for r in (runs or []):
        text = r.text or ""
        if '\n' not in text:
            if text or r is not None:
                cur.append(_copy.deepcopy(r))
            continue
        parts = text.split('\n')
        for j, part in enumerate(parts):
            if part:
                new_r = _copy.deepcopy(r)
                new_r.text = part
                cur.append(new_r)
            if j < len(parts) - 1:
                # paragraph boundary — close current and start fresh
                paragraphs.append(cur)
                cur = []
    paragraphs.append(cur)   # final paragraph (may be empty)
    return paragraphs


def _runs_from_paragraphs(paragraphs, start_idx: int, end_idx: int
                            ) -> List["TextRun"]:
    """Build a flat runs list for paragraphs[start_idx:end_idx], joining
    paragraphs with single '\\n' separators. End_idx is exclusive."""
    out: List["TextRun"] = []
    end_idx = min(end_idx, len(paragraphs))
    for i in range(start_idx, end_idx):
        p = paragraphs[i]
        if i > start_idx:
            out.append(TextRun(text='\n'))
        for r in (p.runs or []):
            out.append(_copy.deepcopy(r))
    return out


def _sync_textboxes_to_body(doc) -> None:
    """Project current page-body TextBox runs back into doc.body.paragraphs.

    This is what makes `doc.body.paragraphs` the canonical store: the
    editor mutates TextBox runs during typing, and on every repaginate
    cycle those mutations are folded back into the master paragraph list
    BEFORE we re-paginate from it. Existing paragraph properties
    (alignment, spacing, keep rules) are preserved positionally — i.e.
    paragraph N in the new list inherits properties from paragraph N in
    the old list. This is a lossy heuristic when paragraphs are
    inserted/removed in the middle, but it's enough for the common case
    of edits at the caret.
    """
    from edof.format.document_body import DocumentBody, Paragraph
    if doc is None: return
    if getattr(doc, 'body', None) is None:
        doc.body = DocumentBody()

    # Collect runs from every body textbox in page order
    all_runs: List["TextRun"] = []
    for pg in doc.pages:
        tb = _find_body_on_page(pg)
        if tb is None: continue
        runs_in = tb.runs or []
        if not runs_text(runs_in): continue
        cur_text = runs_text(all_runs)
        if cur_text and not cur_text.endswith('\n'):
            all_runs.append(TextRun(text='\n'))
        all_runs.extend(_copy.deepcopy(r) for r in runs_in)

    # Split into paragraph-sized run lists
    para_runs = _split_runs_at_newlines(all_runs)

    # Build new paragraph list, preserving properties from old (positional)
    old_paragraphs = doc.body.paragraphs or []
    new_paragraphs: List[Paragraph] = []
    for i, runs in enumerate(para_runs):
        if i < len(old_paragraphs):
            old = old_paragraphs[i]
            new_p = Paragraph(
                runs=runs,
                style_id=old.style_id,
                alignment=old.alignment,
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
            new_p = Paragraph(runs=runs)
        new_paragraphs.append(new_p)
    doc.body.paragraphs = new_paragraphs


def sync_body_geometry_to_margins(doc) -> bool:
    """v4.1.22.13: align every page's body TextBox to the margins stored
    on doc.body.page_margins_mm.

    Call this AFTER mutating page_margins_mm (or after editing the page
    size) and BEFORE repaginate_doc, so the freshly-sized bodies feed
    the right inner_h into pagination. Returns True if any geometry
    actually changed."""
    if doc is None or getattr(doc, 'body', None) is None: return False
    if not doc.pages: return False
    try:
        top, right, bottom, left = doc.body.page_margins_mm
    except Exception:
        return False
    changed = False
    for pg in doc.pages:
        body = _find_body_on_page(pg)
        if body is None: continue
        new_x = float(left); new_y = float(top)
        new_w = max(20.0, float(pg.width)  - float(left) - float(right))
        new_h = max(20.0, float(pg.height) - float(top)  - float(bottom))
        if (body.transform.x != new_x or body.transform.y != new_y
            or body.transform.width  != new_w
            or body.transform.height != new_h):
            body.transform.x = new_x
            body.transform.y = new_y
            body.transform.width  = new_w
            body.transform.height = new_h
            changed = True
    return changed


def repaginate_doc(doc,
                   focus_page_idx: Optional[int] = None,
                   focus_cursor_offset: Optional[int] = None
                   ) -> Dict[str, Any]:
    """Word-style pagination — re-flow doc.body.paragraphs across pages.

    Steps:
      1. Sync textboxes → body.paragraphs (canonical store).
      2. Compute body geometry (from doc.body.page_margins_mm + page size,
         or fall back to the first existing body's transform).
      3. Walk paragraphs with pagination rules, build page ranges as
         (start_para, end_para, intra_first_line, intra_last_line) for
         partial paragraph splits.
      4. For each page range, build the runs slice and assign to that
         page's body TextBox (creating pages as needed).
      5. Prune trailing pages without content / non-body objects, unless
         the focus page is on them.
      6. Map (focus_page, focus_cursor_offset) → (cursor_page,
         cursor_offset) through the rebuild.

    NOTE: For backwards compatibility, the current pass implements a
    line-level pagination that respects per-paragraph spacing and the
    `page_break_before` rule. `keep_next`, `keep_lines`, and full
    widow/orphan handling are scheduled for a follow-up build — the
    fields are already on the model so callers can set them today.
    """
    from edof.engine.text_layout import layout_runs
    from edof.engine.transform import mm_to_px
    from edof.format.objects import TextBox

    result = {
        'pages_count': 0,
        'cursor_page': None,
        'cursor_offset': None,
        'changed': False,
    }
    if doc is None or getattr(doc, 'mode', '') != 'document':
        return result
    if not doc.pages:
        return result

    # ── Step 1: project textbox edits back into body.paragraphs ──
    _sync_textboxes_to_body(doc)
    paragraphs = doc.body.paragraphs if doc.body else []

    # ── Step 2: compute body geometry from existing first body ──
    ref_body = None
    for pg in doc.pages:
        b = _find_body_on_page(pg)
        if b is not None:
            ref_body = b; break
    if ref_body is None:
        # No body anywhere — nothing to do
        result['pages_count'] = len(doc.pages)
        return result

    body_x = ref_body.transform.x
    body_y = ref_body.transform.y
    body_w = ref_body.transform.width
    body_h = ref_body.transform.height
    body_style = ref_body.style
    dpi = float(getattr(doc, 'preferred_dpi', 96.0) or 96.0)
    w_px = mm_to_px(body_w, dpi)
    h_px = mm_to_px(body_h, dpi)
    pad_default = getattr(body_style, 'padding', 1.0) or 1.0
    pt = getattr(body_style, 'padding_top', None)
    pb = getattr(body_style, 'padding_bot', None)
    pt_px = mm_to_px(pt if pt is not None else pad_default, dpi)
    pb_px = mm_to_px(pb if pb is not None else pad_default, dpi)
    inner_h = max(1.0, h_px - pt_px - pb_px)

    # Determine global cursor (paragraph idx, offset within paragraph)
    # from the (focus_page_idx, focus_cursor_offset) which refer to the
    # CURRENT TextBox state, but we just rebuilt body.paragraphs. The
    # safest mapping is via the flat global char index.
    global_cursor: Optional[int] = None
    if focus_page_idx is not None and focus_cursor_offset is not None:
        prefix_len = 0
        for i, pg in enumerate(doc.pages):
            tb = _find_body_on_page(pg)
            if tb is None: continue
            if i == focus_page_idx:
                global_cursor = prefix_len + int(focus_cursor_offset)
                break
            text = runs_text(tb.runs or [])
            prefix_len += len(text)
            if text and not text.endswith('\n'):
                prefix_len += 1   # implicit \n between page bodies

    # ── Step 3: build a single flat run stream from body.paragraphs ──
    # so the layout engine can give us the line list
    all_runs = _runs_from_paragraphs(paragraphs, 0, len(paragraphs))
    flat = runs_text(all_runs)

    # Lay out at infinite height to enumerate every line in the document
    pa = getattr(ref_body, 'paragraph_alignments', None) or {}
    HUGE_H = 1e7
    layout = layout_runs(all_runs, body_style, 0, 0, w_px, HUGE_H, dpi,
                         paragraph_alignments=pa)

    # ── Step 4: build per-line info + walk into tentative chunks,
    # then apply paragraph-level rules (keep_lines, keep_next,
    # widow/orphan) as post-process passes. ──
    chunks: List[Tuple[int, int]] = []
    if not layout.lines:
        chunks.append((0, len(flat)))
    else:
        # 4a. Compute paragraph char ranges in `flat`
        para_start: List[int] = []
        running = 0
        for i, p in enumerate(paragraphs):
            para_start.append(running)
            running += len(p.plain_text())
            if i < len(paragraphs) - 1:
                running += 1    # the joining '\n'

        # 4b. Build per-line info: position, height, paragraph membership.
        line_info: List[Dict[str, Any]] = []
        flat_pos = 0
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
            is_first_of_para = (
                cur_para_for_line < len(paragraphs)
                and first_idx == para_start[cur_para_for_line])
            line_info.append({
                'first_char': first_idx,
                'last_char':  last_idx,
                'height':     float(line.height),
                'para_idx':   cur_para_for_line,
                'is_first_of_para': is_first_of_para,
                'is_last_of_para':  False,    # filled in below
                'is_trailing_virtual': (not line.chars
                                         and li == len(layout.lines) - 1),
            })

        # Determine is_last_of_para via lookahead
        for i in range(len(line_info)):
            if i + 1 < len(line_info):
                line_info[i]['is_last_of_para'] = (
                    line_info[i + 1]['para_idx'] > line_info[i]['para_idx'])
            else:
                line_info[i]['is_last_of_para'] = True

        # Compute needed height per line (with space_before / space_after)
        for li, info in enumerate(line_info):
            para = paragraphs[info['para_idx']] if info['para_idx'] < len(paragraphs) else None
            extra = 0.0
            if para is not None:
                if info['is_first_of_para'] and para.space_before_mm:
                    extra += mm_to_px(para.space_before_mm, dpi)
                if info['is_last_of_para'] and para.space_after_mm:
                    extra += mm_to_px(para.space_after_mm, dpi)
            info['needed_h'] = info['height'] + extra

        # 4c. Tentative chunk walk (line indices)
        line_chunks: List[Tuple[int, int]] = []     # (start_line, end_line_excl)
        chunk_start_li = 0
        used_h = 0.0
        for li, info in enumerate(line_info):
            para = paragraphs[info['para_idx']] if info['para_idx'] < len(paragraphs) else None
            # Forced break before paragraph?
            forced_break = (info['is_first_of_para']
                              and para is not None
                              and para.page_break_before
                              and li > chunk_start_li)
            cursor_is_here = (global_cursor is not None
                                and global_cursor == info['first_char'])
            needed = info['needed_h']
            overflows = (used_h + needed > inner_h + 0.5
                          and li > chunk_start_li)

            if forced_break:
                line_chunks.append((chunk_start_li, li))
                chunk_start_li = li
                used_h = needed
            elif overflows:
                # Trailing-virtual line that nobody points the caret at
                # → don't create an orphan page just for it
                if info['is_trailing_virtual'] and not cursor_is_here:
                    break
                line_chunks.append((chunk_start_li, li))
                chunk_start_li = li
                used_h = needed
            else:
                used_h += needed
        line_chunks.append((chunk_start_li, len(line_info)))

        # 4d. Post-process passes for paragraph-level rules.
        # Each pass may cause cascading effects, so we loop until stable.
        def _para_at_line(li_idx: int) -> int:
            if 0 <= li_idx < len(line_info):
                return line_info[li_idx]['para_idx']
            return -1

        def _first_line_of_para(para_idx: int, after_li: int) -> int:
            """First line index of paragraph `para_idx`, scanning forward
            from `after_li`. Returns len(line_info) if not found."""
            i = max(0, after_li)
            while i < len(line_info):
                if line_info[i]['para_idx'] == para_idx and line_info[i]['is_first_of_para']:
                    return i
                if line_info[i]['para_idx'] > para_idx:
                    break
                i += 1
            return i

        # ── (i) keep_lines: don't split a paragraph across pages ──
        keep_lines_changed = True
        guard = 0
        while keep_lines_changed and guard < 50:
            keep_lines_changed = False
            guard += 1
            for ci in range(len(line_chunks) - 1):
                s, e = line_chunks[ci]
                if e <= s: continue
                last_li = e - 1
                if line_info[last_li]['is_last_of_para']: continue
                para_idx = line_info[last_li]['para_idx']
                para = paragraphs[para_idx] if para_idx < len(paragraphs) else None
                if para is None or not para.keep_lines: continue
                # Move all lines of this paragraph from chunk ci to ci+1.
                # Find the first line of this paragraph in chunk ci.
                first_li = last_li
                while first_li > s and line_info[first_li - 1]['para_idx'] == para_idx:
                    first_li -= 1
                if first_li <= s:
                    # The whole chunk is just this paragraph — can't push
                    # without making chunk empty. Skip (paragraph won't fit
                    # on any single page; we have to allow the split).
                    continue
                line_chunks[ci] = (s, first_li)
                ns, ne = line_chunks[ci + 1]
                line_chunks[ci + 1] = (first_li, ne)
                keep_lines_changed = True
                break

        # ── (ii) keep_next: paragraph N keeps with N+1 ──
        keep_next_changed = True
        guard = 0
        while keep_next_changed and guard < 50:
            keep_next_changed = False
            guard += 1
            for ci in range(len(line_chunks) - 1):
                s, e = line_chunks[ci]
                if e <= s: continue
                last_li = e - 1
                if not line_info[last_li]['is_last_of_para']: continue
                last_para_idx = line_info[last_li]['para_idx']
                last_para = paragraphs[last_para_idx] if last_para_idx < len(paragraphs) else None
                if last_para is None or not last_para.keep_next: continue
                # Where does paragraph N+1 start? Must be in chunk ci+1
                # for keep_next to be violated.
                ns, ne = line_chunks[ci + 1]
                if ne <= ns: continue
                if line_info[ns]['para_idx'] != last_para_idx + 1: continue
                # Move paragraph N entirely to chunk ci+1
                first_li_of_n = last_li
                while first_li_of_n > s and line_info[first_li_of_n - 1]['para_idx'] == last_para_idx:
                    first_li_of_n -= 1
                if first_li_of_n <= s:
                    # Whole chunk is paragraph N — can't push without
                    # emptying. Skip.
                    continue
                line_chunks[ci]     = (s, first_li_of_n)
                line_chunks[ci + 1] = (first_li_of_n, ne)
                keep_next_changed = True
                break

        # ── (iii) widow/orphan control ──
        # Orphan = single line of a paragraph alone at end of a page.
        # Widow  = single line of a paragraph alone at top of a page.
        wo_changed = True
        guard = 0
        while wo_changed and guard < 50:
            wo_changed = False
            guard += 1
            for ci in range(len(line_chunks) - 1):
                s, e = line_chunks[ci]
                ns, ne = line_chunks[ci + 1]
                if e <= s or ne <= ns: continue
                last_li = e - 1
                if line_info[last_li]['is_last_of_para']: continue
                para_idx = line_info[last_li]['para_idx']
                para = paragraphs[para_idx] if para_idx < len(paragraphs) else None
                if para is None or not para.widow_orphan_control: continue
                # Count lines of this paragraph in chunk ci
                lines_here = 0
                i = last_li
                while i >= s and line_info[i]['para_idx'] == para_idx:
                    lines_here += 1
                    i -= 1
                # Count lines of this paragraph in chunk ci+1
                lines_next = 0
                j = ns
                while j < ne and line_info[j]['para_idx'] == para_idx:
                    lines_next += 1
                    j += 1
                # Orphan: single line at end of ci, rest in ci+1
                # Widow:  single line at start of ci+1, rest in ci
                if lines_here == 1 and lines_next >= 2:
                    # Push that single line to next chunk
                    line_chunks[ci]     = (s, e - 1)
                    line_chunks[ci + 1] = (e - 1, ne)
                    wo_changed = True
                    break
                if lines_next == 1 and lines_here >= 2:
                    # Pull one more line into next chunk so it has 2
                    line_chunks[ci]     = (s, e - 1)
                    line_chunks[ci + 1] = (e - 1, ne)
                    wo_changed = True
                    break

        # 4e. Convert line_chunks back to char chunks
        for s, e in line_chunks:
            if s >= e:
                pos = (line_info[s]['first_char']
                        if s < len(line_info) else len(flat))
                chunks.append((pos, pos))
                continue
            start_char = line_info[s]['first_char']
            if e < len(line_info):
                end_char = line_info[e]['first_char']
            else:
                end_char = len(flat)
            chunks.append((start_char, end_char))

    needed = max(1, len(chunks))

    # ── Step 5: ensure we have enough pages ──
    while len(doc.pages) < needed:
        cp = doc.pages[0]
        new_pg = doc.add_page(cp.width, cp.height)
        new_pg.background = tuple(getattr(cp, 'background', (255, 255, 255, 255)))
        result['changed'] = True

    # ── Step 6: write each page's body TextBox from the chunk ──
    cursor_page = None
    cursor_offset = None
    for i, (start, end) in enumerate(chunks):
        pg = doc.pages[i]
        body = _find_body_on_page(pg)
        if body is None:
            body = TextBox()
            body.transform.x      = body_x
            body.transform.y      = body_y
            body.transform.width  = body_w
            body.transform.height = body_h
            try: body.style = _copy.deepcopy(body_style)
            except Exception: pass
            body.style.auto_fill = False
            body.fill.color = None
            body.name = f"doc_body_p{i+1}"
            pg.objects.append(body)
            result['changed'] = True
        # Slice all_runs at [start:end]
        if start == 0 and end == len(flat):
            slice_runs = [_copy.deepcopy(r) for r in all_runs]
        else:
            _, after_start = split_runs_at_char(all_runs, start)
            seg_len = end - start
            if seg_len >= len(runs_text(after_start)):
                slice_runs = after_start
            else:
                slice_runs, _ = split_runs_at_char(after_start, seg_len)
        slice_text = runs_text(slice_runs)
        # v4.1.22.16: REMOVED the "strip leading \\n" logic that used to
        # live here. It was meant to clean up an artifact where a chunk
        # boundary fell exactly at a paragraph-separator '\\n', but in
        # practice my walk never produces such boundaries — chunks split
        # at LINE boundaries, which are always at the start of a line
        # (i.e. just AFTER the previous line's terminator). The strip
        # ended up eating legitimate content: pressing Enter on an empty
        # doc inserts a single '\\n', the entire chunk became that '\\n',
        # the strip removed it, body became empty. Each idle cycle ate
        # one '\\n'. That matched the "self-erasing rows" / "repetitive
        # automatic edits" symptoms the user reported.
        prev_text = body.text or ""
        if prev_text != slice_text:
            body.runs = slice_runs
            body.text = slice_text
            result['changed'] = True
        else:
            body.runs = slice_runs

        # Map global cursor to this page if within range
        if global_cursor is not None and cursor_page is None:
            is_last_chunk = (i == len(chunks) - 1)
            in_range = (start <= global_cursor < end) or (
                is_last_chunk and global_cursor == end)
            if in_range:
                off = global_cursor - start
                if off < 0: off = 0
                if off > len(slice_text): off = len(slice_text)
                cursor_page = i
                cursor_offset = off

    # ── Step 7: clear bodies on pages beyond `needed` ──
    for i in range(needed, len(doc.pages)):
        body = _find_body_on_page(doc.pages[i])
        if body is not None and (body.runs or body.text):
            body.runs = []
            body.text = ""
            result['changed'] = True

    # Fallback cursor placement
    if focus_page_idx is not None and cursor_page is None:
        # Maybe the focus body was empty and global_cursor wasn't set
        if focus_page_idx < len(doc.pages):
            cursor_page = focus_page_idx
            cursor_offset = 0

    if global_cursor is not None and cursor_page is None and chunks:
        last_body = _find_body_on_page(doc.pages[len(chunks)-1])
        cursor_page = len(chunks) - 1
        cursor_offset = len(last_body.text or "") if last_body else 0

    # ── Step 8: prune trailing pages without content / non-body objects ──
    while len(doc.pages) > max(needed, 1):
        idx = len(doc.pages) - 1
        if focus_page_idx == idx or cursor_page == idx:
            break
        pg = doc.pages[idx]
        body = _find_body_on_page(pg)
        non_body_count = sum(1 for o in pg.objects if o is not body)
        if non_body_count > 0:
            break
        if body is not None and runs_text(body.runs or []):
            break
        doc.pages.pop()
        result['changed'] = True

    result['pages_count'] = len(doc.pages)
    result['cursor_page'] = cursor_page
    result['cursor_offset'] = cursor_offset
    return result

