# edof/format/document_body.py
"""
v4.1.19: Document Mode data structures.

When `Document.mode == "document"`, the document is treated as a flow-based
word-style document with a `body` attribute holding paragraphs, paragraph
styles, and page-level chrome (headers, footers, margins). Pages are still
generated for rendering, but their objects[] are computed automatically by
the flow layout engine (`edof.engine.document_flow`) rather than placed
manually by the user.

Coexists with the "empty" (free-form canvas) mode. A document is one mode
or the other — switching modes is intentional and discards the model state
of the other.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from edof.format.styles import TextRun, TextStyle


# ──────────────────────────────────────────────────────────────────────────────
#  Paragraph styles
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ParagraphStyle:
    """A named paragraph style. Maps to docx style definitions on export.

    Fields default to None to express "inherit from parent style".
    The root style ('Normal') is the only one that should have concrete
    defaults — all others cascade through their parent_id chain.
    """
    id:              str
    name:            str
    parent_id:       Optional[str]  = None
    font_family:     Optional[str]  = None
    font_size:       Optional[float] = None     # mm (canonical)
    bold:            Optional[bool]  = None
    italic:          Optional[bool]  = None
    color:           Optional[Tuple[int, int, int]] = None
    alignment:       Optional[str]   = None     # "left"|"center"|"right"|"justify"
    line_height:     Optional[float] = None     # multiplier
    space_before_mm: Optional[float] = None
    space_after_mm:  Optional[float] = None
    indent_first_mm: Optional[float] = None
    indent_left_mm:  Optional[float] = None
    indent_right_mm: Optional[float] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in {
            "id":              self.id,
            "name":            self.name,
            "parent_id":       self.parent_id,
            "font_family":     self.font_family,
            "font_size":       self.font_size,
            "bold":            self.bold,
            "italic":          self.italic,
            "color":           list(self.color) if self.color else None,
            "alignment":       self.alignment,
            "line_height":     self.line_height,
            "space_before_mm": self.space_before_mm,
            "space_after_mm":  self.space_after_mm,
            "indent_first_mm": self.indent_first_mm,
            "indent_left_mm":  self.indent_left_mm,
            "indent_right_mm": self.indent_right_mm,
        }.items() if v is not None or k == "id" or k == "name"}

    @classmethod
    def from_dict(cls, d: dict) -> "ParagraphStyle":
        kw = dict(d)
        if "color" in kw and kw["color"] is not None:
            kw["color"] = tuple(kw["color"])
        return cls(**kw)


def default_paragraph_styles() -> Dict[str, ParagraphStyle]:
    """Return the built-in style set: Normal, Heading 1-3, Title, Quote, Code."""
    return {
        "Normal": ParagraphStyle(
            id="Normal", name="Normal",
            font_family="Arial", font_size=3.881,         # 11pt
            bold=False, italic=False, color=(0, 0, 0),
            alignment="left", line_height=1.15,
            space_before_mm=0.0, space_after_mm=2.5,
            indent_first_mm=0.0, indent_left_mm=0.0, indent_right_mm=0.0,
        ),
        "Title": ParagraphStyle(
            id="Title", name="Title", parent_id="Normal",
            font_size=10.583,                              # 30pt
            bold=True, alignment="center",
            space_before_mm=0.0, space_after_mm=6.0,
        ),
        "Heading1": ParagraphStyle(
            id="Heading1", name="Heading 1", parent_id="Normal",
            font_size=7.408,                               # 21pt
            bold=True,
            space_before_mm=4.0, space_after_mm=2.0,
        ),
        "Heading2": ParagraphStyle(
            id="Heading2", name="Heading 2", parent_id="Normal",
            font_size=5.644,                               # 16pt
            bold=True,
            space_before_mm=3.0, space_after_mm=1.5,
        ),
        "Heading3": ParagraphStyle(
            id="Heading3", name="Heading 3", parent_id="Normal",
            font_size=4.586,                               # 13pt
            bold=True, italic=False,
            space_before_mm=2.5, space_after_mm=1.0,
        ),
        "Quote": ParagraphStyle(
            id="Quote", name="Quote", parent_id="Normal",
            italic=True, color=(80, 80, 80),
            indent_left_mm=10.0, indent_right_mm=10.0,
            space_before_mm=2.0, space_after_mm=2.0,
        ),
        "Code": ParagraphStyle(
            id="Code", name="Code", parent_id="Normal",
            font_family="Courier New", font_size=3.528,    # 10pt
            color=(40, 40, 40),
            indent_left_mm=5.0, line_height=1.1,
            space_before_mm=1.0, space_after_mm=1.0,
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
#  Paragraph
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Paragraph:
    """One paragraph in document-mode flow. Carries runs and direct
    formatting overrides on top of its referenced ParagraphStyle."""
    runs:            List[TextRun]   = field(default_factory=list)
    style_id:        str             = "Normal"
    # Direct overrides (None = use style)
    alignment:       Optional[str]    = None
    line_height:     Optional[float]  = None
    space_before_mm: Optional[float]  = None
    space_after_mm:  Optional[float]  = None
    indent_first_mm: Optional[float]  = None
    indent_left_mm:  Optional[float]  = None
    indent_right_mm: Optional[float]  = None
    # List/numbering (None = no list)
    list_level:      Optional[int]   = None       # 0,1,2
    list_kind:       str             = "none"     # "none"|"bullet"|"number"
    # v4.1.22.13: Word-style pagination control. Defaults match Word's
    # defaults so existing documents behave identically.
    keep_next:           bool = False      # don't separate from next paragraph
    keep_lines:          bool = False      # don't split paragraph across pages
    page_break_before:   bool = False      # force a new page before this paragraph
    widow_orphan_control: bool = True      # require ≥2 lines on each side of split

    def plain_text(self) -> str:
        return "".join(r.text or "" for r in self.runs)

    def to_dict(self) -> dict:
        return {k: v for k, v in {
            "runs":            [r.to_dict() for r in self.runs],
            "style_id":        self.style_id,
            "alignment":       self.alignment,
            "line_height":     self.line_height,
            "space_before_mm": self.space_before_mm,
            "space_after_mm":  self.space_after_mm,
            "indent_first_mm": self.indent_first_mm,
            "indent_left_mm":  self.indent_left_mm,
            "indent_right_mm": self.indent_right_mm,
            "list_level":      self.list_level,
            "list_kind":       self.list_kind,
            "keep_next":           self.keep_next or None,
            "keep_lines":          self.keep_lines or None,
            "page_break_before":   self.page_break_before or None,
            # widow_orphan_control defaults to True — only serialize when False
            "widow_orphan_control": (False if not self.widow_orphan_control else None),
        }.items() if v is not None or k == "runs"}

    @classmethod
    def from_dict(cls, d: dict) -> "Paragraph":
        kw = dict(d)
        if "runs" in kw:
            kw["runs"] = [TextRun.from_dict(r) for r in kw["runs"]]
        else:
            kw["runs"] = []
        # Boolean fields with safe defaults
        for bf, default in (("keep_next", False), ("keep_lines", False),
                              ("page_break_before", False),
                              ("widow_orphan_control", True)):
            if bf in kw and kw[bf] is None:
                kw[bf] = default
        return cls(**kw)


# ──────────────────────────────────────────────────────────────────────────────
#  Resolution: cascade ParagraphStyle through parent chain + apply overrides
# ──────────────────────────────────────────────────────────────────────────────

def resolve_paragraph_style(p: Paragraph,
                              styles: Dict[str, ParagraphStyle]) -> dict:
    """Walk the style's parent_id chain back to "Normal", merge non-None
    fields, then apply Paragraph's direct overrides. Returns a flat dict
    of resolved values (font_family, font_size, alignment, ... etc.).

    Missing inherited values fall back to TextStyle defaults (4.233 mm = 12pt).
    """
    base = {
        "font_family":     "Arial",
        "font_size":       3.881,        # 11pt mm
        "bold":            False,
        "italic":          False,
        "color":           (0, 0, 0),
        "alignment":       "left",
        "line_height":     1.15,
        "space_before_mm": 0.0,
        "space_after_mm":  2.5,
        "indent_first_mm": 0.0,
        "indent_left_mm":  0.0,
        "indent_right_mm": 0.0,
    }
    chain: List[ParagraphStyle] = []
    cur_id = p.style_id
    seen = set()
    while cur_id and cur_id not in seen:
        seen.add(cur_id)
        st = styles.get(cur_id)
        if not st: break
        chain.append(st)
        cur_id = st.parent_id
    # Walk from root (last in chain) → leaf
    for st in reversed(chain):
        for k in base.keys():
            v = getattr(st, k, None)
            if v is not None:
                base[k] = v
    # Apply paragraph direct overrides
    for k in ("alignment", "line_height", "space_before_mm", "space_after_mm",
              "indent_first_mm", "indent_left_mm", "indent_right_mm"):
        v = getattr(p, k, None)
        if v is not None:
            base[k] = v
    return base


# ──────────────────────────────────────────────────────────────────────────────
#  DocumentBody
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DocumentBody:
    """Top-level container when Document.mode == 'document'.

    page_margins_mm: (top, right, bottom, left) — section margins.
    page_size_mm:    (width, height) — section page size.
    header/footer:   shared content displayed on every page, with template
                     variables ({page_number}, {page_count}, ...) resolved
                     per page. Disabled by default; enable via
                     header_enabled / footer_enabled.
    """
    paragraphs:      List[Paragraph]              = field(default_factory=list)
    styles:          Dict[str, ParagraphStyle]    = field(default_factory=default_paragraph_styles)
    page_margins_mm: Tuple[float, float, float, float] = (25.4, 25.4, 25.4, 25.4)

    # v4.1.23: shared header/footer template runs, applied to every page
    # via DocumentHeaderBox / DocumentFooterBox at paginate time.
    header_enabled:   bool                      = False
    header_runs:      List["TextRun"]           = field(default_factory=list)
    header_height_mm: float                     = 12.0
    footer_enabled:   bool                      = False
    footer_runs:      List["TextRun"]           = field(default_factory=list)
    footer_height_mm: float                     = 12.0

    # Deprecated paragraph-style header/footer — kept for backward compat
    # with files saved by v4.1.22.x and earlier. New code reads/writes
    # *_runs above.
    header:          Optional[Paragraph]          = None
    footer:          Optional[Paragraph]          = None

    def to_dict(self) -> dict:
        return {
            "paragraphs":       [p.to_dict() for p in self.paragraphs],
            "styles":           {sid: s.to_dict() for sid, s in self.styles.items()},
            "page_margins_mm":  list(self.page_margins_mm),
            "header_enabled":   self.header_enabled,
            "header_runs":      [r.to_dict() for r in (self.header_runs or [])],
            "header_height_mm": self.header_height_mm,
            "footer_enabled":   self.footer_enabled,
            "footer_runs":      [r.to_dict() for r in (self.footer_runs or [])],
            "footer_height_mm": self.footer_height_mm,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentBody":
        # Styles
        st_dicts = d.get("styles", {})
        if st_dicts:
            styles = {sid: ParagraphStyle.from_dict(sd) for sid, sd in st_dicts.items()}
        else:
            styles = default_paragraph_styles()
        # Paragraphs
        paragraphs = [Paragraph.from_dict(pd) for pd in d.get("paragraphs", [])]
        # Margins
        m = d.get("page_margins_mm", (25.4, 25.4, 25.4, 25.4))
        margins = tuple(float(v) for v in m)
        # Header/footer (new template-runs API)
        header_enabled = bool(d.get("header_enabled", False))
        header_runs = [TextRun.from_dict(rd) for rd in d.get("header_runs", [])]
        header_height_mm = float(d.get("header_height_mm", 12.0))
        footer_enabled = bool(d.get("footer_enabled", False))
        footer_runs = [TextRun.from_dict(rd) for rd in d.get("footer_runs", [])]
        footer_height_mm = float(d.get("footer_height_mm", 12.0))
        return cls(
            paragraphs=paragraphs,
            styles=styles,
            page_margins_mm=margins,
            header_enabled=header_enabled,
            header_runs=header_runs,
            header_height_mm=header_height_mm,
            footer_enabled=footer_enabled,
            footer_runs=footer_runs,
            footer_height_mm=footer_height_mm,
        )
