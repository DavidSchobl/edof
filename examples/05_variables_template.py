"""Template with variables: define once, render many."""
from edof import Document, export_page_bitmap

doc = Document()
doc.variables.define("name", "string", default="World")
doc.variables.define("score", "number", default=0)

page = doc.add_page(width=120, height=60)
page.add_textbox(10, 12, 100, 14, "Certificate for {name}").style.font_size = 7.0
page.add_textbox(10, 32, 100, 12, "Score: {score} points").style.font_size = 5.0

for name, score in [("Alice", 97), ("Bob", 84)]:
    doc.variables.set("name", name)
    doc.variables.set("score", score)
    export_page_bitmap(doc, 0, f"out/05_cert_{name}.png", dpi=160)
    print(f"written: out/05_cert_{name}.png")
