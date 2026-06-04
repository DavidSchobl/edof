# edof/engine/document_flow.py
"""
v4.1.19: Flow layout engine for document-mode documents.

Takes a `DocumentBody` (paragraphs + styles + margins) and a page size,
returns a list of `FlowPage` objects each with `lines` (a list of laid-out
line records) ready for the renderer. The engine handles:

  • Cascading paragraph styles + direct overrides
  • Per-paragraph spacing (before / after) and indentation
  • Word wrap at run boundaries (with hyphenation-style line breaks)
  • Page packing — overflow paragraphs flow to the next page
  • Bullet / numbered list prefixes
  • Header / footer paragraphs on every page

It does NOT handle:

  • Inline images / tables (paragraph "type" stays text-only in this revision)
  • Floating objects (anchored to fixed coords) — those still belong to design mode
  • Widows / orphans control — added in 4.1.20 when we have multi-line metrics

Output unit is mm. Caller (renderer) converts mm → px at draw time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

from edof.format.document_body import DocumentBody, Paragraph, resolve_paragraph_style
from edof.format.styles import TextRun, TextStyle


@dataclass
class FlowLineSegment:
    """One segment of a laid-out line — a run's worth of text or part of it."""
    text:     str
    rs:       dict          # resolved run style (font_family, font_size, bold, ...)
    width_mm: float

@dataclass
class FlowLine:
    """A single line of text within a paragraph after wrap."""
    segments: List[FlowLineSegment] = field(default_factory=list)
    width_mm: float = 0.0
    height_mm: float = 0.0      # max ascent+descent across line × line_height
    ascender_mm: float = 0.0

@dataclass
class FlowParagraphRender:
    """A single paragraph after layout, anchored to a page top-left in mm."""
    paragraph: Paragraph
    style:     dict             # resolved style dict
    x_mm:      float
    y_mm:      float
    width_mm:  float            # paragraph block width (excluding indents)
    lines:     List[FlowLine] = field(default_factory=list)
    list_prefix: str = ""        # e.g. "• " or "3. "

@dataclass
class FlowPage:
    """One rendered page of flow content."""
    page_w_mm: float
    page_h_mm: float
    inner_x_mm: float     # content area top-left
    inner_y_mm: float
    inner_w_mm: float
    inner_h_mm: float
    paragraphs: List[FlowParagraphRender] = field(default_factory=list)
    header: Optional[FlowParagraphRender] = None
    footer: Optional[FlowParagraphRender] = None


def _measure_run_text(rs: dict, text: str) -> float:
    """Approximate width of text in mm at given run style.

    Uses a quick estimation based on character width = 0.55 × font_size mm.
    For exact metrics we'd load the font here — this is a pragmatic
    first-pass that the renderer can refine at draw time without
    affecting line wrap decisions noticeably."""
    fs_mm = float(rs.get("font_size", 3.881))
    bold  = bool(rs.get("bold", False))
    # Bold ≈ 7% wider; monospace fonts wider; rough averages.
    char_w = fs_mm * (0.58 if bold else 0.55)
    if any(c in (rs.get("font_family", "") or "").lower() for c in ("courier", "mono")):
        char_w = fs_mm * 0.60
    return char_w * len(text)


def _split_runs_to_tokens(p: Paragraph,
                           parent_style: TextStyle) -> List[Tuple[dict, str, bool]]:
    """Tokenise paragraph runs into (rs, text, is_space) triples ready for
    line-fitting. Words and spaces are separate tokens; explicit \\n in text
    is currently treated as a soft break (single newline)."""
    out: List[Tuple[dict, str, bool]] = []
    for run in p.runs:
        rs = run.resolve(parent_style, scale=1.0)
        text = run.text or ""
        if not text: continue
        # Split keeping whitespace as separate tokens
        i = 0
        while i < len(text):
            ch = text[i]
            if ch.isspace():
                # Run of whitespace
                j = i
                while j < len(text) and text[j].isspace():
                    j += 1
                out.append((rs, text[i:j], True))
                i = j
            else:
                j = i
                while j < len(text) and not text[j].isspace():
                    j += 1
                out.append((rs, text[i:j], False))
                i = j
    return out


def _wrap_paragraph(p: Paragraph, styles_dict, max_width_mm: float
                     ) -> Tuple[List[FlowLine], dict, float]:
    """Wrap a paragraph's runs into FlowLines that fit max_width_mm.
    Returns (lines, resolved_style, total_height_mm).
    Inter-paragraph spacing is added by the page-packer."""
    resolved = resolve_paragraph_style(p, styles_dict)
    # Build a synthetic TextStyle to use TextRun.resolve()
    parent = TextStyle(
        font_family   = resolved["font_family"],
        font_size     = resolved["font_size"],
        bold          = resolved["bold"],
        italic        = resolved["italic"],
        color         = resolved["color"],
        line_height   = resolved["line_height"],
        alignment     = resolved["alignment"],
    )
    tokens = _split_runs_to_tokens(p, parent)
    if not tokens:
        # Empty paragraph — emit single blank line for spacing
        line = FlowLine(
            height_mm   = resolved["font_size"] * resolved["line_height"],
            ascender_mm = resolved["font_size"] * 0.8,
        )
        return [line], resolved, line.height_mm
    lines: List[FlowLine] = []
    cur = FlowLine()
    cur_w = 0.0

    def close_line():
        nonlocal cur, cur_w
        if cur.segments:
            # Compute line metrics
            max_fs = max(seg.rs.get("font_size", 3.881) for seg in cur.segments)
            cur.height_mm = max_fs * resolved["line_height"]
            cur.ascender_mm = max_fs * 0.8
            cur.width_mm = cur_w
            lines.append(cur)
        cur = FlowLine(); cur_w = 0.0

    for rs, text, is_space in tokens:
        w = _measure_run_text(rs, text)
        if cur_w + w > max_width_mm and cur.segments and not is_space:
            close_line()
        elif is_space and cur_w + w > max_width_mm and cur.segments:
            close_line()
            continue   # drop leading space on new line
        cur.segments.append(FlowLineSegment(text=text, rs=rs, width_mm=w))
        cur_w += w
    close_line()

    if not lines:
        # Safety: ensure at least one line
        lines.append(FlowLine(
            height_mm=resolved["font_size"] * resolved["line_height"],
            ascender_mm=resolved["font_size"] * 0.8,
        ))
    total_h = sum(ln.height_mm for ln in lines)
    return lines, resolved, total_h


def _list_prefix(p: Paragraph, counters: Dict[int, int]) -> str:
    """Compute the bullet / numbered prefix string for a paragraph.
    counters maps list_level → next number to use, mutated in place."""
    if p.list_kind == "bullet":
        marks = ["•", "◦", "▪"]
        lvl = max(0, min(2, p.list_level or 0))
        return f"{marks[lvl]} "
    if p.list_kind == "number":
        lvl = max(0, min(2, p.list_level or 0))
        counters[lvl] = counters.get(lvl, 0) + 1
        # Reset deeper levels when a higher level increments
        for deeper in list(counters.keys()):
            if deeper > lvl: counters[deeper] = 0
        return f"{counters[lvl]}. "
    return ""


def layout_document(body: DocumentBody,
                     page_w_mm: float, page_h_mm: float
                     ) -> List[FlowPage]:
    """Top-level layout pass. Returns a list of FlowPage records.

    The renderer then walks each FlowPage and draws paragraphs starting at
    (paragraph.x_mm, paragraph.y_mm), one line at a time using the segment
    list. No mutation of `body` happens here — it is pure layout."""
    top, right, bottom, left = body.page_margins_mm
    inner_x = left
    inner_y = top
    inner_w = max(1.0, page_w_mm - left - right)
    inner_h = max(1.0, page_h_mm - top - bottom)
    pages: List[FlowPage] = []

    # ── Helper to start a new page ──
    def new_page() -> FlowPage:
        pg = FlowPage(
            page_w_mm=page_w_mm, page_h_mm=page_h_mm,
            inner_x_mm=inner_x, inner_y_mm=inner_y,
            inner_w_mm=inner_w, inner_h_mm=inner_h,
        )
        # Header
        if body.header:
            h_lines, h_resolved, h_height = _wrap_paragraph(
                body.header, body.styles, inner_w)
            pg.header = FlowParagraphRender(
                paragraph=body.header, style=h_resolved,
                x_mm=inner_x, y_mm=max(2.0, top - h_height - 2.0),
                width_mm=inner_w, lines=h_lines,
            )
        # Footer
        if body.footer:
            f_lines, f_resolved, f_height = _wrap_paragraph(
                body.footer, body.styles, inner_w)
            pg.footer = FlowParagraphRender(
                paragraph=body.footer, style=f_resolved,
                x_mm=inner_x, y_mm=page_h_mm - bottom + 2.0,
                width_mm=inner_w, lines=f_lines,
            )
        pages.append(pg)
        return pg

    pg = new_page()
    cur_y = inner_y
    list_counters: Dict[int, int] = {}

    for paragraph in body.paragraphs:
        # Apply indent_left/right for content width (first-line indent is
        # an offset on the first line specifically; we compute available width
        # as full inner width minus left/right indents)
        resolved = resolve_paragraph_style(paragraph, body.styles)
        left_ind  = float(resolved.get("indent_left_mm")  or 0.0)
        right_ind = float(resolved.get("indent_right_mm") or 0.0)
        first_ind = float(resolved.get("indent_first_mm") or 0.0)
        space_before = float(resolved.get("space_before_mm") or 0.0)
        space_after  = float(resolved.get("space_after_mm")  or 0.0)
        prefix = _list_prefix(paragraph, list_counters)
        if prefix:
            # Reserve space for prefix (treated as part of first-line indent)
            first_ind += 6.0       # rough; renderer handles exact

        # Apply space-before (suppressed at very top of a page)
        add_space = space_before if cur_y > inner_y + 0.1 else 0.0
        cur_y += add_space

        # Effective content width
        content_w = max(1.0, inner_w - left_ind - right_ind)
        lines, _, total_h = _wrap_paragraph(paragraph, body.styles, content_w)

        # Does it fit on current page?
        if cur_y + total_h > inner_y + inner_h and lines:
            # Try splitting: keep as many lines as possible on this page,
            # rest moves to next page (paragraph break across pages)
            remaining = list(lines)
            while remaining:
                fit_lines = []
                fit_h = 0.0
                while remaining and cur_y + fit_h + remaining[0].height_mm <= inner_y + inner_h:
                    fit_lines.append(remaining.pop(0))
                    fit_h += fit_lines[-1].height_mm
                if fit_lines:
                    block = FlowParagraphRender(
                        paragraph=paragraph, style=resolved,
                        x_mm=inner_x + left_ind, y_mm=cur_y,
                        width_mm=content_w, lines=fit_lines,
                        list_prefix=prefix,
                    )
                    pg.paragraphs.append(block)
                    cur_y += fit_h
                if remaining:
                    pg = new_page(); cur_y = inner_y
                    prefix = ""   # list prefix only on first part
        else:
            block = FlowParagraphRender(
                paragraph=paragraph, style=resolved,
                x_mm=inner_x + left_ind, y_mm=cur_y,
                width_mm=content_w, lines=lines, list_prefix=prefix,
            )
            pg.paragraphs.append(block)
            cur_y += total_h

        # Apply space-after
        cur_y += space_after

        # If now past page bottom, start a new page on next paragraph
        if cur_y >= inner_y + inner_h:
            pg = new_page(); cur_y = inner_y

    return pages
