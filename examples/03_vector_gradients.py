"""Vector shapes and gradient fills."""
from edof import Document, Gradient, export_page_bitmap

doc = Document()
page = doc.add_page(width=120, height=80)

rect = page.add_shape("rect", 10, 10, 45, 28)
rect.fill.gradient = Gradient(type="linear", angle=35.0,
                              stops=[(0.0, (255, 120, 40, 255)),
                                     (1.0, (160, 30, 160, 255))])
rect.stroke.width = 0.6
rect.stroke.color = (60, 20, 60)

ell = page.add_shape("ellipse", 65, 10, 45, 28)
ell.fill.color = (40, 140, 220)
ell.fill.opacity = 0.85

rad = page.add_shape("rect", 10, 46, 100, 26)
rad.fill.gradient = Gradient(type="radial", center=(0.5, 0.5), radius=0.7,
                             stops=[(0.0, (255, 240, 200, 255)),
                                    (1.0, (40, 90, 60, 255))])

export_page_bitmap(doc, 0, "out/03_vector.png", dpi=200)
print("written: out/03_vector.png")
