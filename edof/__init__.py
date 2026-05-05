# edof/__init__.py
"""
from __future__ import annotations
edof – Easy Document Format 3.0
================================
Programmatic document creation, template filling, and export.

Quick start::

    import edof

    doc  = edof.Document(title="Hello")
    page = doc.add_page()
    tb   = page.add_textbox(10, 10, 120, 20, "Hello, World!")
    tb.style.font_size  = 36
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
    SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE, SHAPE_POLYGON, SHAPE_ARROW, SHAPE_PATH,
    make_table,
)
from edof.format.styles    import TextStyle, StrokeStyle, FillStyle, ShadowStyle, TextRun, Gradient  # noqa: F401
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
    """Create a new blank Document."""
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
    """
    from edof.utils.pdf_import import import_pdf as _import_pdf
    return _import_pdf(path, **kwargs)


def import_rtf(path: str) -> Document:
    """v4.0.3: Import an RTF file as an editable EDOF Document.

    Each non-empty paragraph becomes a TextBox stacked vertically; runs
    preserve bold/italic/underline/size/color. Tables, images, lists, and
    other complex RTF features are not supported.
    """
    from edof.utils.rtf import import_rtf as _import_rtf
    return _import_rtf(path)


__all__ = [
    # Core
    "Document", "Page", "ResourceStore",
    # Objects
    "EdofObject", "TextBox", "ImageBox", "Shape", "QRCode", "Group",
    "Table", "TableCell", "CellBorder", "make_table",
    "SHAPE_RECT", "SHAPE_ELLIPSE", "SHAPE_LINE", "SHAPE_POLYGON",
    "SHAPE_ARROW", "SHAPE_PATH",
    # Styles
    "TextStyle", "StrokeStyle", "FillStyle", "ShadowStyle", "TextRun", "Gradient",
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
    "load", "new", "import_pdf", "import_rtf",
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
