# edof/format/document_boxes.py
"""v4.1.23: Document-mode text box classes.

Three subclasses of TextBox, distinguished by their role on a page in
a document-mode file:

  • DocumentTextBox    — the body content viewport on each page.
                         Auto-sized to the section's margins. The
                         canonical content lives on Document.body.paragraphs;
                         this box just displays a slice of that flow.

  • DocumentHeaderBox  — the optional header on each page.
                         Content is SHARED across pages (lives on
                         Document.body.header_runs). May contain
                         template variables like {page_number} and
                         {page_count} which are resolved per-page at
                         render time.

  • DocumentFooterBox  — the optional footer. Symmetric to the header.

These classes don't add new fields beyond the regular TextBox; they
exist as a discriminator so the editor and paginator can tell them
apart by isinstance() instead of by string-matching the `name` field.
That was the source of many cross-cutting bugs in 4.1.22.x — every
piece of code had to remember to do the same string check.

Serialization uses the OBJECT_TYPE string set in __post_init__. On
load, the format reader looks at obj_type and dispatches to the right
class. Old files saved as a plain TextBox with name="document_body"
are migrated to DocumentTextBox in the document loader (see Document.from_dict).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from edof.format.objects import TextBox


@dataclass
class DocumentTextBox(TextBox):
    """Body viewport on a single page of a document-mode file."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "document_textbox")
        if not self.name:
            self.name = "document_body"

    @property
    def doc_role(self) -> str:
        return "body"


@dataclass
class DocumentHeaderBox(TextBox):
    """Header viewport on a single page. Content is shared across pages
    via Document.body.header_runs; this box's `runs` field is set by
    the paginator at render time with variables resolved."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "document_header")
        if not self.name:
            self.name = "document_header"

    @property
    def doc_role(self) -> str:
        return "header"


@dataclass
class DocumentFooterBox(TextBox):
    """Footer viewport on a single page. Symmetric to DocumentHeaderBox."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "OBJECT_TYPE", "document_footer")
        if not self.name:
            self.name = "document_footer"

    @property
    def doc_role(self) -> str:
        return "footer"


def is_document_box(obj) -> bool:
    """True if obj is any of the three document-mode box subclasses."""
    return isinstance(obj, (DocumentTextBox, DocumentHeaderBox, DocumentFooterBox))


def is_document_body(obj) -> bool:
    return isinstance(obj, DocumentTextBox)


def is_document_header(obj) -> bool:
    return isinstance(obj, DocumentHeaderBox)


def is_document_footer(obj) -> bool:
    return isinstance(obj, DocumentFooterBox)


def resolve_template_vars(text: str, page_idx: int, page_count: int,
                            extra: Optional[dict] = None) -> str:
    """Resolve {page_number}, {page_count}, etc. in a template string.

    page_idx is 0-based; {page_number} is 1-based for display.

    Defined variables:
      {page_number}        1, 2, 3, ...
      {page_count}         total pages
      {page_number_left}   page_number aligned visually left (= "1   ")
      {page_number_right}  page_number aligned visually right (= "   1")
      {page_number_center} page_number centered

    Any other {name} is preserved as-is so users can mix custom variables
    in via the document's variable store later.
    """
    page_number = page_idx + 1
    page_number_str = str(page_number)
    page_count_str = str(page_count)
    # Width for visual alignment: width of the largest page number
    w = max(len(str(page_count)), 1)
    repl = {
        "page_number":        page_number_str,
        "page_count":         page_count_str,
        "page_number_left":   page_number_str.ljust(w),
        "page_number_right":  page_number_str.rjust(w),
        "page_number_center": page_number_str.center(w),
    }
    if extra: repl.update({k: str(v) for k, v in extra.items()})

    # Walk the string token-by-token. Unknown {name} preserved.
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == '{':
            j = text.find('}', i + 1)
            if j > i:
                name = text[i + 1:j]
                if name in repl:
                    out.append(repl[name])
                    i = j + 1
                    continue
        out.append(text[i])
        i += 1
    return "".join(out)


def resolve_template_runs(runs, page_idx: int, page_count: int,
                            extra: Optional[dict] = None):
    """Apply resolve_template_vars to each run's text, returning new runs.
    Original runs are not mutated."""
    import copy as _copy
    out = []
    for r in (runs or []):
        new_r = _copy.deepcopy(r)
        if new_r.text:
            new_r.text = resolve_template_vars(
                new_r.text, page_idx, page_count, extra)
        out.append(new_r)
    return out
