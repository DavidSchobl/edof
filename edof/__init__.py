# edof/__init__.py
"""
from __future__ import annotations
edof – Easy Document Format
================================
Programmatic document creation, template filling, and export.

v4.1.17: **mm is the canonical unit for everything length-related**
(font_size, padding, stroke widths, positions, dimensions). The
`*_pt` accessors (font_size_pt, etc.) are provided for typography
users who think in points.

Quick start::

    import edof

    doc  = edof.Document(title="Hello")
    page = doc.add_page()
    tb   = page.add_textbox(10, 10, 120, 20, "Hello, World!")
    tb.style.font_size  = 4.233        # mm (≈ 12 pt)
    # — or equivalently via pt accessor —
    tb.style.font_size_pt = 12
    tb.style.auto_shrink = True
    doc.save("hello.edof")
    doc.export_bitmap("hello.png", dpi=300)
"""

from edof.version    import __version__, FORMAT_VERSION_STR  # noqa: F401
from edof.exceptions import EdofMissingFontWarning  # noqa: F401
from edof.exceptions import (                                 # noqa: F401
    EdofError, EdofVersionError, EdofResourceError,
    EdofRenderError, EdofVariableError, EdofAPIError,
    EdofValidationError, EdofPrintError,
    EdofNewerVersionWarning, EdofMissingOptionalWarning,
)

from edof.format.document  import Document, Page, ResourceStore   # noqa: F401
from edof.format.objects   import (                               # noqa: F401
    EdofObject, TextBox, ImageBox, Shape, QRCode, Group,
    Table, TableCell, CellBorder,
    SubDocumentBox, SvgBox,
    SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE, SHAPE_POLYGON, SHAPE_ARROW, SHAPE_PATH,
    make_table,
)
from edof.format.styles    import TextStyle, StrokeStyle, FillStyle, ShadowStyle, TextRun, Gradient, LayerEffect, as_color  # noqa: F401
from edof.format.variables import VariableStore, VariableDef      # noqa: F401
from edof.format.variables import (                               # noqa: F401
    VAR_TEXT, VAR_IMAGE, VAR_NUMBER, VAR_DATE, VAR_BOOL, VAR_QR, VAR_URL,
)
from edof.format.serializer import EdofSerializer                 # noqa: F401
from edof.format.document   import (                              # noqa: F401
    CS_RGB, CS_RGBA, CS_GRAY, CS_BW, CS_CMYK, BD_8, BD_16,
)
from edof.engine.transform  import Transform, to_mm, from_mm, mm_to_px  # noqa: F401
from edof.engine.renderer   import render_page, render_document    # noqa: F401
from edof.engine.text_engine import measure_text_height             # noqa: F401
from edof.export.bitmap     import (                               # noqa: F401
    export_page_bitmap, export_all_pages, export_to_bytes,
)

# ── Convenience aliases ───────────────────────────────────────────────────────

def load(path: str, password: str = None,
          recovery_key: str = None) -> Document:
    """Load an .edof file and return a Document.

    v4.0.1: Automatically detects:
      - Legacy EDOF 2 archives (best-effort, one-way migration)
      - Encrypted EDOF 4 archives (requires password= or recovery_key=)
    Migration warnings appear in doc.errors.
    """
    from edof.utils.legacy_v2 import is_v2_archive, load_v2
    if is_v2_archive(path):
        return load_v2(path)
    return Document.load(path, password=password, recovery_key=recovery_key)


def new(width: float = 210.0, height: float = 297.0, **kwargs) -> Document:
    """Create a new blank Document.

    Args:
        width, height: page size in millimetres (default A4 portrait).
        **kwargs: forwarded to ``Document`` (e.g. ``default_dpi``, ``title``).

    Example:
        >>> import edof
        >>> doc = edof.new(210, 297, title="Hello", dpi=300)
        >>> page = doc.pages[0]
        >>> doc.save("hello.edof")
    """
    return Document(width=width, height=height, **kwargs)


def import_pdf(path: str, **kwargs) -> Document:
    """v4.0: Import a PDF as an editable EDOF Document.

    Requires pymupdf (`pip install edof[pdf]`).

    Options:
        detect_tables       (bool, default False) — heuristic table detection (needs pdfplumber)
        merge_paragraphs    (bool, default True)  — cluster spans into paragraphs
        heading_threshold   (float, default 1.4)  — font_size > median × X → heading
        indent_threshold_mm (float, default 3.0)  — first-line indent detection
        extract_paths       (bool, default True)  — convert vector paths (v4.0.3)
        extract_images      (bool, default True)  — extract embedded raster images (v4.0.3)

    Example:
        >>> doc = edof.import_pdf("report.pdf", detect_tables=True)
        >>> doc.save("report.edof")
    """
    from edof.utils.pdf_import import import_pdf as _import_pdf
    return _import_pdf(path, **kwargs)


def import_rtf(path: str) -> Document:
    """v4.0.3: Import an RTF file as an editable EDOF Document.

    Each non-empty paragraph becomes a TextBox stacked vertically; runs
    preserve bold/italic/underline/size/color. Tables, images, lists, and
    other complex RTF features are not supported.

    Example:
        >>> doc = edof.import_rtf("letter.rtf")
    """
    from edof.utils.rtf import import_rtf as _import_rtf
    return _import_rtf(path)


def import_docx(path: str, return_report: bool = False):
    """v4.2.0: Import a Word (.docx) file as a document-mode EDOF Document.

    Requires python-docx (`pip install edof[docx]`).

    The body text flow is imported with bold / italic / underline /
    strikethrough, font family and size, run colour, paragraph alignment,
    line spacing, space before/after, page breaks and simple lists.
    Unsupported content (tables, images, drawings, text boxes, equations,
    embedded objects, and — minor — headers/footers, footnotes, comments) is
    NOT imported; it is detected and described in the returned report.

    Args:
        path: path to the .docx file.
        return_report: when True, return ``(Document, DocxReport)`` so you can
            inspect ``report.unsupported`` / ``report.recommend_import`` /
            ``report.recommend_reason``; when False (default), return just the
            Document, matching ``import_pdf`` / ``import_rtf``.

    Example:
        >>> doc, report = edof.import_docx("contract.docx", return_report=True)
        >>> if not report.recommend_import:
        ...     print("Heads up:", report.recommend_reason)
        >>> doc.save("contract.edof")
    """
    from edof.interop.docx_io import import_docx as _imp
    doc, report = _imp(path)
    return (doc, report) if return_report else doc


def export_docx(doc: Document, path: str):
    """v4.2.0: Export a document-mode EDOF Document to a Word (.docx) file.

    Requires python-docx (`pip install edof[docx]`).

    Writes the body text flow with run formatting (bold / italic / underline /
    strikethrough, font, size, colour), paragraph alignment, page size and
    margins, page breaks, simple lists, and a line height matched exactly to
    EDOF's so pagination in Word lines up with the editor.

    Returns a ``DocxReport`` (``report.paragraphs``, ``report.warnings``).

    Example:
        >>> doc = edof.load("contract.edof")
        >>> report = edof.export_docx(doc, "contract.docx")
        >>> print(report.paragraphs, "paragraphs written")
    """
    from edof.interop.docx_io import export_docx as _exp
    return _exp(doc, path)


__all__ = [
    # Core
    "Document", "Page", "ResourceStore",
    # Objects
    "EdofObject", "TextBox", "ImageBox", "Shape", "QRCode", "Group",
    "Table", "TableCell", "CellBorder", "make_table",
    "SubDocumentBox", "SvgBox",
    "SHAPE_RECT", "SHAPE_ELLIPSE", "SHAPE_LINE", "SHAPE_POLYGON",
    "SHAPE_ARROW", "SHAPE_PATH",
    # Styles
    "TextStyle", "StrokeStyle", "FillStyle", "ShadowStyle", "TextRun", "Gradient",
    "LayerEffect", "as_color",
    # Variables
    "VariableStore", "VariableDef",
    "VAR_TEXT", "VAR_IMAGE", "VAR_NUMBER", "VAR_DATE", "VAR_BOOL", "VAR_QR", "VAR_URL",
    # Serializer
    "EdofSerializer",
    # Color-space / bit-depth constants
    "CS_RGB", "CS_RGBA", "CS_GRAY", "CS_BW", "CS_CMYK", "BD_8", "BD_16",
    # Transform
    "Transform", "to_mm", "from_mm", "mm_to_px",
    # Render
    "render_page", "render_document",
    # Export helpers
    "export_page_bitmap", "export_all_pages", "export_to_bytes",
    # Convenience
    "load", "new", "import_pdf", "import_rtf", "import_docx", "export_docx",
    # Version
    "__version__", "FORMAT_VERSION_STR",
    # Exceptions
    "EdofError", "EdofVersionError", "EdofResourceError",
    "EdofRenderError", "EdofVariableError", "EdofAPIError",
    "EdofValidationError", "EdofPrintError",
    "EdofNewerVersionWarning", "EdofMissingOptionalWarning", "EdofMissingFontWarning",
    # Text helpers
    "measure_text_height",
]
