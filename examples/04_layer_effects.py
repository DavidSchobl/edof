"""Layer effects showcase: long shadow modes, drop shadow, stroke, halftone.

The long shadow uses the per-point ray model: every silhouette point emits a
ray; colour / alpha / blur follow multi-stop gradients along the ray.
"""
from edof import Document, LayerEffect, export_page_bitmap

doc = Document()
page = doc.add_page(width=200, height=70)

# 1. classic: linear blur + fade
a = page.add_textbox(8, 18, 50, 30, "FLAT")
a.style.font_size = 12.0; a.style.bold = True; a.style.color = (250, 250, 250)
a.effects.append(LayerEffect(type="long_shadow", direction=25.0, ls_length=14.0,
                             ls_blur_mode="linear", size=3.0,
                             ls_alpha_mode="fade", color=(40, 40, 40, 255)))

# 2. constant blur softens backward over the leading edge too
b = page.add_textbox(72, 18, 50, 30, "SOFT")
b.style.font_size = 12.0; b.style.bold = True; b.style.color = (250, 250, 250)
b.effects.append(LayerEffect(type="long_shadow", direction=25.0, ls_length=14.0,
                             ls_blur_mode="constant", size=2.0,
                             ls_alpha_mode="solid", color=(30, 60, 120, 255)))

# 3. full custom gradients
c = page.add_textbox(138, 18, 54, 30, "RAY")
c.style.font_size = 12.0; c.style.bold = True; c.style.color = (250, 250, 250)
c.effects.append(LayerEffect(
    type="long_shadow", direction=25.0, ls_length=16.0,
    ls_blur_mode="custom",  ls_grad_blurs=[[0.0, 0.0], [0.6, 4.0], [1.0, 1.0]],
    ls_color_mode="custom", ls_grad_colors=[[0.0, 200, 30, 30],
                                            [0.5, 245, 200, 40],
                                            [1.0, 40, 60, 210]],
    ls_alpha_mode="custom", ls_grad_alphas=[[0.0, 1.0], [1.0, 0.55]]))

for tb in (a, b, c):
    tb.effects.append(LayerEffect(type="stroke", size=0.5, color=(20, 20, 20, 255)))

export_page_bitmap(doc, 0, "out/04_effects.png", dpi=200)
print("written: out/04_effects.png")
