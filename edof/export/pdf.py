# edof/export/pdf.py
"""
Export EDOF document to PDF via reportlab (optional dependency).
Install with:  pip install edof[pdf]
"""

from __future__ import annotations
import io
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from edof.format.document import Document


def export_pdf(doc: "Document", path: str,
               dpi: Optional[int] = None) -> None:
    """
    Render every page to a bitmap and bundle into a PDF.
    Requires ``reportlab``:  pip install edof[pdf]
    """
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.units import mm
    except ImportError:
        from edof.exceptions import warn_missing, EdofError
        warn_missing("PDF export", "pdf")
        raise EdofError(
            "reportlab is required for PDF export. "
            "Install with:  pip install edof[pdf]"
        )

    from edof.engine.renderer import render_page

    # Use the first page's size for the PDF canvas; pages can differ.
    first = doc.pages[0]
    pdf   = rl_canvas.Canvas(
        path,
        pagesize=(first.width * mm, first.height * mm),
    )
    pdf.setTitle(doc.title or "EDOF Document")
    pdf.setAuthor(doc.author or "")
    pdf.setSubject(doc.description or "")

    for page in doc.pages:
        img = render_page(page, doc.resources, doc.variables,
                          dpi or page.dpi)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        w_mm, h_mm = page.width, page.height
        pdf.setPageSize((w_mm * mm, h_mm * mm))
        pdf.drawImage(
            ImageReader(buf),
            0, 0,
            width=w_mm * mm, height=h_mm * mm,
            preserveAspectRatio=False,
        )
        pdf.showPage()

    pdf.save()
