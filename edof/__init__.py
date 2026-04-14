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
from edof.exceptions import (                                 # noqa: F401
    EdofError, EdofVersionError, EdofResourceError,
    EdofRenderError, EdofVariableError, EdofAPIError,
    EdofValidationError, EdofPrintError,
    EdofNewerVersionWarning, EdofMissingOptionalWarning,
)

from edof.format.document  import Document, Page, ResourceStore   # noqa: F401
from edof.format.objects   import (                               # noqa: F401
    EdofObject, TextBox, ImageBox, Shape, QRCode, Group,
    SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE, SHAPE_POLYGON, SHAPE_ARROW,
)
from edof.format.styles    import TextStyle, StrokeStyle, FillStyle, ShadowStyle  # noqa: F401
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
from edof.export.bitmap     import (                               # noqa: F401
    export_page_bitmap, export_all_pages, export_to_bytes,
)

# ── Convenience aliases ───────────────────────────────────────────────────────

def load(path: str) -> Document:
    """Load an .edof file and return a Document."""
    return Document.load(path)


def new(width: float = 210.0, height: float = 297.0, **kwargs) -> Document:
    """Create a new blank Document."""
    return Document(width=width, height=height, **kwargs)


__all__ = [
    # Core
    "Document", "Page", "ResourceStore",
    # Objects
    "EdofObject", "TextBox", "ImageBox", "Shape", "QRCode", "Group",
    "SHAPE_RECT", "SHAPE_ELLIPSE", "SHAPE_LINE", "SHAPE_POLYGON", "SHAPE_ARROW",
    # Styles
    "TextStyle", "StrokeStyle", "FillStyle", "ShadowStyle",
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
    "load", "new",
    # Version
    "__version__", "FORMAT_VERSION_STR",
    # Exceptions
    "EdofError", "EdofVersionError", "EdofResourceError",
    "EdofRenderError", "EdofVariableError", "EdofAPIError",
    "EdofValidationError", "EdofPrintError",
    "EdofNewerVersionWarning", "EdofMissingOptionalWarning",
]
