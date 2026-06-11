"""Minimal edof document: one page, styled text, PNG + PDF export."""
from edof import Document, export_page_bitmap
from edof.export.pdf import export_pdf

doc = Document()
page = doc.add_page(width=120, height=80)          # mm

title = page.add_textbox(10, 10, 100, 16, "Hello, edof!")
title.style.font_size = 9.0                        # mm
title.style.bold = True
title.style.color = (30, 60, 160)

body = page.add_textbox(10, 32, 100, 36,
                        "Documents are described in code, then rendered "
                        "to PNG, JPEG, TIFF, BMP, PDF, or SVG.")
body.style.font_size = 4.0

export_page_bitmap(doc, 0, "out/01_hello.png", dpi=200)
export_pdf(doc, "out/01_hello.pdf")
print("written: out/01_hello.png, out/01_hello.pdf")
