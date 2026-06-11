# Reference: Styles & Transform

All visual properties of objects come from a small set of style classes: `TextStyle`, `FillStyle`, `StrokeStyle`, `Gradient`, `ShadowStyle`, `CellBorder`, `BorderStyle`, plus the geometric `Transform`.

## Color format

Throughout edof, colors are tuples of integers in the range `0–255`:

```python
red       = (255, 0, 0)              # RGB — alpha defaults to 255
red_solid = (255, 0, 0, 255)         # RGBA — equivalent
red_50pct = (255, 0, 0, 128)         # RGBA with 50% alpha
```

Functions and styles accept both 3-tuples (RGB) and 4-tuples (RGBA). 3-tuples implicitly use full opacity.

`None` as a color means "no color" (transparent). For fills, `None` lets the gradient take over if set.

---

## TextStyle

Defaults for text rendering inside a `TextBox` or `TableCell`.

```python
tb.style.font_family   = "Helvetica"
tb.style.font_size     = 12.0           # in points (pt)
tb.style.bold          = False
tb.style.italic        = False
tb.style.underline     = False
tb.style.strikethrough = False
tb.style.color         = (0, 0, 0)      # RGB
tb.style.alignment     = "left"         # "left" | "center" | "right" | "justify"
tb.style.vertical_align = "top"         # "top" | "middle" | "bottom"
tb.style.line_height   = 1.2            # multiplier of font_size
tb.style.letter_spacing = 0.0           # in pt
tb.style.wrap          = True           # soft-wrap on whitespace
tb.style.auto_shrink   = False          # shrink font to fit box
tb.style.auto_fill     = False          # grow font to fill box
tb.style.background    = None           # text-frame background; usually use FillStyle.color instead
```

### Fonts

By default, edof tries fonts in this priority:
1. The exact `font_family` you specified (system font lookup via Pillow)
2. Common aliases (`Arial → DejaVu Sans` on Linux, etc.)
3. The fallback embedded with Pillow (DejaVu Sans)

For PDF vector export, only the Standard 14 PDF fonts work in vector mode (Helvetica / Times / Courier with bold and italic variants). Other fonts are mapped to the closest match. To use a custom font in PDF, fall back to raster mode: `doc.export_pdf(path, vector=False)` — this uses Pillow which can render any installed TTF.

To list which fonts edof discovered on the current system:

```python
import edof
from edof.engine.text_engine import discovered_fonts
print(discovered_fonts())
```

---

## FillStyle

Solid color or gradient fill for shapes and text-box backgrounds.

```python
from edof import FillStyle, Gradient

# Solid color
shape.fill = FillStyle(color=(100, 149, 237, 255))

# Gradient
shape.fill = FillStyle(gradient=Gradient(
    type="linear", angle=0,
    stops=[(0.0, (255, 0, 0, 255)),
           (1.0, (0, 0, 255, 255))]
))

# Or set them on the existing fill
shape.fill.color    = None    # disable solid color
shape.fill.gradient = my_gradient
```

### Fields

- `color: tuple | None` — RGB or RGBA. If `gradient` is also set, `gradient` wins.
- `gradient: Gradient | None` — see below

---

## Gradient

Linear or radial gradient with multiple color stops.

```python
from edof import Gradient

g = Gradient(
    type="linear",        # "linear" | "radial"
    angle=45,             # for linear: degrees, 0 = left-to-right
    radius=0.5,           # for radial: radius as fraction of the bounding box
    stops=[
        (0.0, (255,   0,   0, 255)),  # red at start
        (0.5, (255, 255,   0, 255)),  # yellow in middle
        (1.0, (  0,   0, 255, 255)),  # blue at end
    ],
)
```

### Fields

- `type: str` — `"linear"` or `"radial"`
- `angle: float` — degrees, only used for linear gradients. `0` = left-to-right; `90` = top-to-bottom; `45` = top-left to bottom-right
- `radius: float` — fraction of the bounding box, only for radial. `0.5` = inscribed circle; `1.0` = encompasses corners
- `stops: list[tuple[float, tuple[int, int, int, int]]]` — list of `(offset, color)` pairs. Offset is `0.0` to `1.0`. Stops are sorted at render.

The renderer interpolates colors between consecutive stops in linear or radial space. For best results, ensure the first stop is at offset `0.0` and the last at `1.0`.

---

## StrokeStyle

Outline / stroke for shapes.

```python
from edof import StrokeStyle

shape.stroke = StrokeStyle(
    color = (0, 0, 0, 255),
    width = 0.5,            # in mm
    dash  = "solid",        # "solid" | "dashed" | "dotted"
    cap   = "round",        # "butt" | "round" | "square"
    join  = "round",        # "miter" | "round" | "bevel"
)
```

### Fields

- `color: tuple | None` — RGB or RGBA. `None` (or `(0, 0, 0, 0)`) = no stroke.
- `width: float` — line width in **mm** (gets converted to pixels at render time)
- `dash: str` — `"solid"`, `"dashed"`, `"dotted"`
- `cap: str` — line endpoint shape
- `join: str` — corner shape between segments

---

## ShadowStyle

Drop shadow for any object.

```python
from edof import ShadowStyle

obj.shadow = ShadowStyle(
    offset_x = 1.0,         # mm; positive = right
    offset_y = 1.0,         # mm; positive = down
    blur     = 2.0,         # mm
    color    = (0, 0, 0, 80),  # 80/255 = ~31% opacity
)
```

### Fields

- `offset_x, offset_y: float` — shift in mm
- `blur: float` — Gaussian blur radius in mm
- `color: tuple` — shadow color (typically with reduced alpha)

Set `obj.shadow = None` (the default) for no shadow.

---

## CellBorder

Per-side border on a `TableCell`. Each cell has four independent borders: `border_top`, `border_right`, `border_bottom`, `border_left`.

```python
from edof import CellBorder

cell.border_top = CellBorder(
    enabled = True,
    color   = (50, 50, 50, 255),
    width   = 0.3,           # mm
    style   = "solid",       # "solid" | "dashed" | "dotted"
)
```

### Fields

- `enabled: bool` — must be `True` for border to render
- `color: tuple` — RGB or RGBA
- `width: float` — in mm
- `style: str` — line pattern

---

## BorderStyle

Border around an entire `TextBox` or `Table`. Same fields as `CellBorder` but applies to the object as a whole rather than per-side.

```python
tb.border = BorderStyle(
    enabled = True,
    color   = (200, 200, 200, 255),
    width   = 0.2,
    style   = "solid",
    radius  = 2.0,           # rounded corners in mm
)
```

---

## Transform

Position, size, rotation, and flip — all combined.

Every object has a `transform` attribute. You usually access individual fields rather than the whole object:

```python
obj.transform.x      = 50.0
obj.transform.y      = 100.0
obj.transform.width  = 80.0
obj.transform.height = 30.0
obj.transform.rotation = 15.0      # degrees, clockwise
obj.transform.flip_h = False       # mirror horizontally
obj.transform.flip_v = False       # mirror vertically
```

### Coordinate system

- Origin `(0, 0)` is the **top-left** corner of the page.
- X increases to the right.
- Y increases **downward** (like screen coordinates, opposite from typical mathematical convention).
- All values are in **mm**.

### Convenience methods on Transform

```python
obj.transform.translate(dx, dy)        # add to x, y
obj.transform.move_to(x, y)            # set x, y absolutely
obj.transform.center()                 # returns (cx, cy) tuple
obj.transform.center_on(cx, cy)        # set position by center point
obj.transform.scale(sx, sy=None)       # multiply width/height
obj.transform.rotate_to(angle)         # set rotation absolutely
obj.transform.rotate_by(delta)         # add to rotation
obj.transform.bbox()                   # returns (x1, y1, x2, y2) — top-left and bottom-right
```

### Same-named shortcuts on the object itself

For convenience, common operations on the transform are exposed on the object:

```python
obj.move(dx, dy)                       # → obj.transform.translate(dx, dy)
obj.move_to(x, y)                      # → obj.transform.move_to(x, y)
obj.resize(w, h)                       # set transform.width and transform.height
obj.rotate(degrees)                    # → obj.transform.rotate_by(degrees)
obj.center()                           # → obj.transform.center()
```

---

## Unit conversion

If you need to convert between mm and pixels (e.g. for direct Pillow operations):

```python
from edof import mm_to_px, from_mm, to_mm

px = mm_to_px(15.0, dpi=300)   # 15 mm at 300 DPI = 177.165 px
mm = to_mm(177, dpi=300)       # round-trip back

# from_mm() is alias of mm_to_px
```

Calculations:
- `1 mm = (dpi / 25.4) px`
- A4 portrait at 300 DPI = `2480 × 3508` px

---

## Color space and bit depth (page-level)

These are not styles per object — they're set on the `Page`:

```python
from edof import CS_RGB, CS_RGBA, CS_GRAY, CS_BW, CS_CMYK, BD_8, BD_16

page.color_space = CS_RGB    # "RGB"
page.bit_depth   = BD_8      # 8

# Grayscale page (e.g. for one-color print)
page.color_space = CS_GRAY   # "L"
```

Constants:
- `CS_RGB = "RGB"` — 3-channel color (default)
- `CS_RGBA = "RGBA"` — 4-channel with alpha
- `CS_GRAY = "L"` — single channel grayscale
- `CS_BW = "1"` — 1-bit black and white
- `CS_CMYK = "CMYK"` — 4-channel print
- `BD_8 = 8` — 8 bits per channel (default)
- `BD_16 = 16` — 16 bits per channel (high precision)

These are passed through to Pillow at export time. Most users stick with the defaults.

## LayerEffect

Photoshop-style layer effects (`drop_shadow`, `long_shadow`, `stroke`, `bevel`, `halftone`, `chromatic_aberration`, ...) live on the object's `effects` list, not inside the style objects above. They have their own reference page: [12 — Layer effects](12-effects.md).
