"""Save to .edof, load back, re-export: the file format round-trip."""
from edof import Document, LayerEffect, export_page_bitmap
from edof.format.serializer import EdofSerializer

doc = Document()
page = doc.add_page(width=100, height=60)
tb = page.add_textbox(10, 18, 80, 24, "Round trip")
tb.style.font_size = 9.0
tb.effects.append(LayerEffect(type="long_shadow", ls_length=8.0,
                              direction=30.0, ls_blur_mode="linear", size=2.0))

EdofSerializer().save(doc, "out/06_roundtrip.edof")
doc2 = EdofSerializer().load("out/06_roundtrip.edof")
export_page_bitmap(doc2, 0, "out/06_roundtrip.png", dpi=160)
print("written: out/06_roundtrip.edof, out/06_roundtrip.png")
