# Cookbook: Flat-design poster with layer effects

Build a small event poster that leans on layer effects: a long-shadow headline with multi-stop gradients, a halftone photo treatment, and a chromatic-aberration accent. Everything renders identically to PNG and PDF.

## Result

A 148×105 mm (A6 landscape) poster: a bold headline throwing a coloured ray shadow, a halftoned circle as the graphic element, and a subtitle with a subtle RGB split.

## The headline: long shadow with gradient stops

The long shadow is a per-point ray model: every silhouette point emits a ray of length `ls_length` along `direction`. Colour, alpha, and blur are each a function of the ray's own progression `t` in 0–1, controlled by three independent modes.

```python
from edof import Document, LayerEffect, export_page_bitmap
from edof.export.pdf import export_pdf

doc = Document()
page = doc.add_page(width=148, height=105)
page.background = (245, 242, 235, 255)

headline = page.add_textbox(10, 18, 128, 30, "SYNTHWAVE")
headline.style.font_size = 13.0
headline.style.bold = True
headline.style.color = (250, 250, 250)

headline.effects.append(LayerEffect(
    type="long_shadow",
    direction=205.0,            # down-right
    ls_length=18.0,             # mm
    # blur: sharp at the contact, peaks mid-ray, tightens at the tip
    ls_blur_mode="custom",
    ls_grad_blurs=[[0.0, 0.0], [0.55, 3.5], [1.0, 0.8]],
    # colour: hot orange to deep violet along the ray
    ls_color_mode="custom",
    ls_grad_colors=[[0.0, 235, 90, 40], [0.55, 200, 40, 120], [1.0, 60, 25, 110]],
    # alpha: hold strength, then release
    ls_alpha_mode="custom",
    ls_grad_alphas=[[0.0, 1.0], [0.7, 0.85], [1.0, 0.0]],
))
headline.effects.append(LayerEffect(type="stroke", size=0.45,
                                    color=(35, 20, 50, 255)))
```

Mode cheat-sheet: `ls_blur_mode="solid"` keeps the whole shadow razor sharp; `"constant"` blurs uniformly (and softens backward over the leading edge — physically right for a constant kernel); `"linear"` is the classic sharp-contact, soft-tip look using just `size`; `"custom"` takes the stop list above. The same Solid / Custom split applies to colour, and Solid / Fade / Custom to alpha.

## The graphic: a halftoned disc

```python
disc = page.add_shape("ellipse", 96, 48, 42, 42)
disc.fill.color = (40, 90, 160)
disc.effects.append(LayerEffect(
    type="halftone",
    ht_dot=1.1,                 # cell size in mm
    ht_angle=18.0,
    ht_shape="circle",
    ht_color_mode="mono",
    ht_hex=True,                # hexagonal grid
))
```

## The subtitle: chromatic aberration accent

```python
sub = page.add_textbox(10, 56, 80, 14, "city lights / 21 June")
sub.style.font_size = 5.0
sub.style.color = (40, 35, 60)
sub.effects.append(LayerEffect(type="chromatic_aberration",
                               ca_mode="linear", ca_offset=0.25, ca_angle=0.0))
```

## Export

```python
export_page_bitmap(doc, 0, "poster.png", dpi=300)
export_pdf(doc, "poster.pdf")
```

## Variations

- **Sharper retro look:** `ls_blur_mode="solid"`, `ls_alpha_mode="solid"` — the classic hard flat-design shadow.
- **Soft neon:** add `LayerEffect(type="outer_glow", size=2.5, color=(255, 80, 180, 200))` under the headline.
- **GPU:** with `moderngl` installed, the ray field, the variable blur, halftone, and chromatic aberration all run on the GPU; check `from edof.engine.gpu import gpu_status; print(gpu_status())`.

The complete runnable script (three shadow styles side by side) is [examples/04_layer_effects.py](../../examples/04_layer_effects.py); the full field reference is [reference/12-effects.md](../reference/12-effects.md).
