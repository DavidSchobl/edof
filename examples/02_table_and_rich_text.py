"""A line-item table plus rich text (mixed runs in one text box)."""
from edof import Document, TextRun, export_page_bitmap

doc = Document()
page = doc.add_page(width=140, height=100)

rich = page.add_textbox(10, 8, 120, 14, "")
rich.runs = [
    TextRun(text="Invoice ", bold=True),
    TextRun(text="#2026-0042 ", color=(160, 30, 30)),
    TextRun(text="(draft)", italic=True),
]
rich.style.font_size = 6.0

rows = [["Item", "Qty", "Price"],
        ["Long shadow render", "3", "900"],
        ["Halftone pass", "1", "450"],
        ["GPU time", "2", "120"]]
page.add_table(10, 28, 120, rows, header=True)

export_page_bitmap(doc, 0, "out/02_table.png", dpi=200)
print("written: out/02_table.png")
