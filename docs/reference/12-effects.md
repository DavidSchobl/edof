# Reference: Layer effects

Photoshop-style, non-destructive effects attached to any object (text box, shape, image, table). Effects live in the object's `effects` list as `LayerEffect` instances; each can be toggled with `enabled`. All sizes and distances are in **millimetres** (the canonical edof unit), all angles in **degrees**.

```python
from edof import Document, LayerEffect

doc = Document()
page = doc.add_page(width=120, height=80)
tb = page.add_textbox(10, 25, 100, 30, "BADGE")
tb.style.font_size = 16.0
tb.effects.append(LayerEffect(type="long_shadow", ls_length=12.0,
                              direction=20.0, color=(40, 40, 40, 255)))
```

Rendering order: `drop_shadow`, `outer_glow`, `long_shadow`, outside `stroke` and outer `bevel` are composited **below** the object; everything else renders **above/into** it. Several effects of the same type can be stacked; they apply in list order.

Common fields on every effect:

| Field | Type | Meaning |
|---|---|---|
| `type` | str | One of the effect types below |
| `enabled` | bool | Toggle without removing the effect |
| `opacity` | float 0–1 | Effect layer opacity |
| `blend_mode` | str | Photoshop blend mode (`normal`, `multiply`, `screen`, `overlay`, ...) |
| `color` | Color | Primary effect colour `(r, g, b)` or `(r, g, b, a)` |
| `size` | float mm | Primary size/radius (meaning depends on type) |

---

## drop_shadow

Classic soft shadow below the object.

| Field | Meaning |
|---|---|
| `distance` (mm) | Offset along `direction` |
| `direction` (°) | Light/throw angle |
| `size` (mm) | Blur radius |
| `spread` (0–100) | Hardens the core before blurring |

```python
obj.effects.append(LayerEffect(type="drop_shadow",
                               distance=2.5, direction=135.0,
                               size=3.0, color=(0, 0, 0, 180)))
```

`inner_shadow` takes the same fields and renders inside the object's silhouette.

## outer_glow / inner_glow

Soft halo outside (or inside) the silhouette. `size` is the glow radius, `color` the glow colour, `spread` hardens the core.

## long_shadow

The flat-design "infinite shadow": every point of the silhouette emits a ray of length `ls_length` along `direction`; the shadow is the union of all rays. The source pixel's alpha scales its whole ray, so semi-transparent edges and PNG alpha behave naturally. Along each ray, colour, alpha, and blur are functions of the ray's own progression *t* ∈ [0, 1].

Three independent mode selectors:

**Blur mode — `ls_blur_mode`**

| Value | Behaviour | Controls used |
|---|---|---|
| `solid` | Razor-sharp shadow | — |
| `constant` | Same blur everywhere (also softens backward over the leading edge) | `size` (mm) |
| `linear` | Sharp at the contact, blur grows to `size` at the tip | `size` (mm) |
| `custom` | Multi-stop blur curve | `ls_grad_blurs` |

**Colour mode — `ls_color_mode`**

| Value | Behaviour | Controls used |
|---|---|---|
| `solid` | One colour | `color` |
| `custom` | Multi-stop colour gradient along the ray | `ls_grad_colors` |

**Alpha mode — `ls_alpha_mode`**

| Value | Behaviour | Controls used |
|---|---|---|
| `solid` | Full strength to the tip | — |
| `fade` | Linear fade to zero | — |
| `custom` | Multi-stop alpha curve (may be non-monotone) | `ls_grad_alphas` |

Gradient stops are lists of `[t, value...]` rows, linearly interpolated:

```python
LayerEffect(type="long_shadow", direction=25.0, ls_length=15.0,
            ls_blur_mode="custom",  ls_grad_blurs=[[0.0, 0.0], [0.6, 4.5], [1.0, 1.0]],
            ls_color_mode="custom", ls_grad_colors=[[0.0, 200, 30, 30],
                                                    [0.5, 245, 200, 40],
                                                    [1.0, 40, 60, 210]],
            ls_alpha_mode="custom", ls_grad_alphas=[[0.0, 1.0], [1.0, 0.55]])
```

- `ls_grad_colors`: `[t, r, g, b]`
- `ls_grad_alphas`: `[t, a]` with `a` in 0–1
- `ls_grad_blurs`: `[t, radius_mm]`

Notes:

- With non-monotone alpha curves the union semantics apply: over a thick body, older interior rays can dominate where the curve dips; a thin stroke shows the full curve.
- Documents written before format 4.2.19 carry the legacy controls (`ls_fade`, `ls_color_grad`, `ls_mode`); they are derived automatically and render unchanged. Leave `ls_alpha_mode` / `ls_color_mode` empty to keep legacy derivation.
- The ray field and the variable blur both run on the GPU when available (see `edof.engine.gpu.gpu_status()`); the CPU fallback is a close approximation and exact in the dominant regime.

## stroke

Outline around the silhouette. `size` is the width (mm), `stroke_position` is `outside`, `inside`, or `center`.

## color_overlay / gradient_overlay / texture_overlay

Fill the object's silhouette with a flat colour, a two-colour gradient (`gradient_start`, `gradient_end`, `gradient_angle`), or an image texture (`texture_path` or embedded `texture_data`, with `texture_scale`, `texture_fit` = `tile`/`fit`/`stretch`, `texture_anchor`).

## bevel

Emboss/chisel lighting. `bevel_kind` = `outer`/`inner`, `bevel_technique` = `smooth`/`chisel`, `bevel_depth` (%), `bevel_dir` = `up`/`down`, `size` (mm), `soften` (mm), `altitude` (°), `highlight_opacity`, `shadow_opacity`.

## chromatic_aberration

RGB channel separation. Global controls: `ca_offset` (mm), `ca_angle` (°), `ca_mode` = `linear` (uniform shift) or `radial` (lens-style, grows from the centre with per-channel `ca_*_distort`). Per-channel overrides: `ca_r_offset`/`ca_r_angle` and friends, plus custom channel colours `ca_r_color`, `ca_g_color`, `ca_b_color`. GPU-accelerated.

## halftone

Print-style halftone rasterization of the object. Key fields: `ht_dot` (cell size, mm), `ht_angle` (°), `ht_shape` (`circle`, `square`, `diamond`, `cross`, `ring`, ...), `ht_color_mode` (`cmyk`, `rgb`, `mono`), `ht_render_mode` (`size` = classic dot growth, `opacity`), `ht_hex` (hexagonal grid), plus pattern stamps via `ht_pattern_mode`/`ht_patterns`. GPU-accelerated with exact CPU parity.

## light_sweep

A diagonal highlight band across the object: `lsw_pos` (0–1 position), `lsw_width` (0–1), `lsw_angle` (°), `color`.

---

## Serialization

Effects round-trip through `.edof` files as plain dictionaries inside the object's `effects` array. Unknown fields are ignored on load, so newer files degrade gracefully in older readers. See [Advanced: file format](../advanced/file-format.md).
