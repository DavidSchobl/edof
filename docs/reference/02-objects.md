# Reference: Objects

Every object that can appear on a page inherits from `EdofObject`. There are six concrete types: `TextBox`, `ImageBox`, `Shape`, `QRCode`, `Table`, `Group`.

## Common fields (on every object)

These fields are available on **all** object types via inheritance from `EdofObject`.

### Identity

- `id: str` — UUID, generated automatically. Used for `page.get_object()`, lookups, and references between objects.
- `name: str` — optional human-readable name. Useful for `page.get_by_name()`.
- `tags: list[str]` — optional list of free-form tags. Useful for `page.get_by_tag()` and conditional logic.

### Position & transform

- `transform: Transform` — combined position, size, rotation, flip. See [reference/03-styles.md](03-styles.md#transform).
  - `transform.x`, `transform.y` — top-left in mm
  - `transform.width`, `transform.height` — in mm
  - `transform.rotation` — in degrees, clockwise
  - `transform.flip_h`, `transform.flip_v` — booleans

Shortcut helpers exist on the object directly:

- `obj.move(dx, dy)` — translate by delta
- `obj.move_to(x, y)` — set absolute position
- `obj.resize(w, h)` — set size
- `obj.rotate(degrees)` — add to rotation
- `obj.center()` — centerpoint as `(cx, cy)` tuple

### Layering & visibility

- `layer: int` — stacking order. Higher = front. Set automatically when adding objects (incremental); can be overridden.
- `visible: bool` — global show/hide
- `visible_if: str` — small Python-style expression evaluated against `doc.variables` at render time (see below)
- `opacity: float` — 0.0 to 1.0
- `blend_mode: str` — one of `"normal"`, `"multiply"`, `"screen"`, `"darken"`, `"lighten"`, `"overlay"`. Implemented in the Pillow renderer.

### Conditional visibility (`visible_if`)

Set `obj.visible_if` to an expression evaluated as a boolean. Variables are resolved from `doc.variables`. The expression supports:

- Boolean operators: `and`, `or`, `not`
- Comparisons: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Arithmetic: `+`, `-`, `*`, `/`
- Numeric and string literals
- Variable names

Not allowed: function calls, attribute access, imports, comprehensions. The evaluator is a safe AST whitelist.

```python
discount_label = page.add_textbox(10, 200, 180, 8, "DISCOUNT: -{discount} CZK")
discount_label.visible_if = "discount > 0"

vip_badge = page.add_textbox(160, 10, 40, 8, "VIP")
vip_badge.visible_if = "tier == 'gold' or score >= 90"
```

### Locking (template protection)

- `locked: bool` — UI-level lock; the editor refuses to move/edit a locked object
- `lock_level: str` — `""`, `"fill"`, `"edit"`, `"design"`, or `"admin"`. Modifying this object requires at least the named permission level.
- `lock_text: bool` — hard text lock; `.text` and `.runs` cannot be changed even by `admin` until `lock_text` is set back to `False`. Clearing `lock_text` itself requires `admin`.

Helper methods:

- `obj.can_modify(doc) → bool`
- `obj.can_modify_text(doc) → bool`

These respect both per-object locks and document-level encryption permissions. See [reference/07-encryption.md](07-encryption.md).

### Effects

- `shadow: ShadowStyle | None` — drop shadow. See [reference/03-styles.md](03-styles.md#shadowstyle).

### Other

- `OBJECT_TYPE: str` (class attribute) — the type tag in serialized form (`"textbox"`, `"imagebox"`, etc.)
- `obj.copy()` — return a deep copy with a new ID
- `obj.to_dict()` — JSON-serializable dict
- `EdofObject.from_dict(d)` (classmethod) — reconstruct from dict

---

## TextBox

Renders text within a rectangular frame.

### Basic usage

```python
tb = page.add_textbox(x=15, y=15, w=180, h=12, text="Hello world")
tb.style.font_family = "Helvetica"
tb.style.font_size   = 14
tb.style.bold        = True
tb.style.color       = (50, 80, 160)
tb.style.alignment   = "center"
```

### Fields specific to TextBox

- `text: str` — plain text content. Supports `\n` for line breaks. Supports `{variable}` placeholders.
- `runs: list[TextRun]` — optional rich-text segments. When non-empty, takes priority over `text`. See below.
- `style: TextStyle` — text styling. See [reference/03-styles.md](03-styles.md#textstyle).
- `padding: tuple[float, ...]` — `(top, right, bottom, left)` in mm. Can be a single float for uniform.
- `border: BorderStyle | None` — frame border around the text box
- `fill: FillStyle | None` — background color or gradient
- `variable: str` — if set, the textbox displays the value of this variable directly (overrides `text`)

### Rich text via `TextRun`

```python
from edof import TextRun

tb = page.add_textbox(15, 30, 180, 18)
tb.runs = [
    TextRun(text="Awarded to "),
    TextRun(text="Jan ",     font_size=24),
    TextRun(text="Novák",    font_size=24, bold=True, color=(150, 50, 0)),
    TextRun(text=" for excellence", italic=True),
]
```

`TextRun` fields:
- `text: str`
- `font_family: str | None`
- `font_size: float | None`
- `bold, italic, underline, strikethrough: bool | None`
- `color: tuple | None` — RGB or RGBA
- `background: tuple | None` — highlight color

`None` means "inherit from the textbox's `style`". Fields are merged at render time.

### Auto-sizing

Set in `tb.style`:
- `auto_shrink: bool` — reduces font size until text fits within the box
- `auto_fill: bool` — increases font size until text fills the box
- `wrap: bool` — soft-wrap on whitespace (default: `True`)

These are mutually exclusive; setting both is undefined behavior.

### Variable placeholder syntax

Plain text and run text both support `{variable_name}` substitutions. At render time, placeholders are replaced with the variable's current value.

```python
doc.define_variable("client", default="Customer")
page.add_textbox(15, 15, 180, 8, "Hello {client}, welcome.")
```

If a variable is undefined, the placeholder is left as-is and a warning goes to `doc.errors`.

---

## ImageBox

Renders an embedded raster image.

```python
img_id = doc.add_resource_from_file("logo.png")
ib = page.add_image(img_id, x=15, y=15, w=40, h=40)
ib.fit_mode = "contain"
```

### Fields

- `resource_id: str` — ID of the resource (returned by `doc.add_resource()`)
- `fit_mode: str` — how to fit the image in the box:
  - `"contain"` — preserve aspect, letterbox if needed (default)
  - `"cover"` — preserve aspect, crop to fill
  - `"fill"` — preserve aspect, fit short side, crop overflow (alias for cover with center anchor)
  - `"stretch"` — distort to fill exactly
- `align_h: str` — `"left"`, `"center"`, `"right"` — anchor when image doesn't fill horizontally
- `align_v: str` — `"top"`, `"middle"`, `"bottom"`
- `variable: str` — if set, swaps the image at render time. The variable should be of type `image` and contain a resource_id or path.

### Loading from variable

```python
doc.define_variable("logo", type="image")
ib.variable = "logo"

# At render:
doc.set_variable("logo", "/path/to/customer_logo.png")
doc.export_pdf("output.pdf")
```

When the variable is set to a path, edof loads it as a fresh resource (no permanent storage in the document).

---

## Shape

Vector primitive. Supports six subtypes via the `shape_type` field:

```python
from edof import (Shape, SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE,
                   SHAPE_POLYGON, SHAPE_ARROW, SHAPE_PATH)
```

(Or use string literals: `"rect"`, `"ellipse"`, etc.)

### Common Shape fields

- `shape_type: str` — see above
- `fill: FillStyle | None` — color or gradient
- `stroke: StrokeStyle | None` — outline
- `corner_radius: float` — for rectangles only

### Type-specific fields

#### `"rect"` and `"ellipse"`
Use the `transform` for size and position. No additional fields. Set `corner_radius > 0` for rounded corners on rectangles.

```python
rect = page.add_shape("rect", 15, 15, 180, 30)
rect.fill.color = (240, 240, 240, 255)
rect.corner_radius = 5

ellipse = page.add_shape("ellipse", 15, 50, 50, 50)
ellipse.fill.color = (255, 200, 100, 255)
```

#### `"line"`
Has `points: list[[x, y]]` — list of `[x, y]` pairs. For a single line, use exactly 2 points. The points are in **local coordinates relative to the transform's `(x, y)`**, in mm.

```python
line = page.add_shape("line", 15, 100, 180, 0)
line.points = [[0, 0], [180, 0]]
line.stroke.color = (0, 0, 0, 255)
line.stroke.width = 0.5
```

#### `"polygon"`
Like `"line"` but closed. The renderer connects the last point back to the first.

```python
poly = page.add_shape("polygon", 100, 100, 60, 60)
poly.points = [[30, 0], [60, 60], [0, 60]]   # triangle
poly.fill.color = (200, 50, 50, 255)
```

#### `"arrow"`
A line with an arrowhead. `points` defines start and end. `stroke.width` controls thickness; arrowhead size scales with width.

```python
arrow = page.add_shape("arrow", 15, 150, 100, 20)
arrow.points = [[0, 10], [100, 10]]
arrow.stroke.color = (50, 50, 50, 255)
arrow.stroke.width = 1.5
```

#### `"path"`
SVG-style Bezier path. Has `path_data: list` containing command tuples.

Commands supported:
- `["M", x, y]` — move to
- `["L", x, y]` — line to
- `["H", x]` — horizontal line to
- `["V", y]` — vertical line to
- `["C", x1, y1, x2, y2, x, y]` — cubic Bezier
- `["Q", x1, y1, x, y]` — quadratic Bezier
- `["Z"]` — close path

```python
sh = Shape(shape_type="path")
sh.transform.x = 50
sh.transform.y = 100
sh.path_data = [
    ["M", 0, 0],
    ["L", 50, 0],
    ["C", 70, 20, 80, 20, 100, 0],   # Bezier curve
    ["Z"],
]
sh.fill.color = (100, 200, 100, 255)
page.add_object(sh)
```

#### `Shape.from_svg_path(d: str) → Shape` (classmethod)

Parse an SVG-style path string into a `path` shape:

```python
heart = Shape.from_svg_path(
    "M 50 10 C 40 0 0 0 0 30 C 0 60 50 90 50 90 "
    "C 50 90 100 60 100 30 C 100 0 60 0 50 10 Z"
)
heart.transform.x = 75
heart.transform.y = 100
heart.fill.color = (220, 50, 50, 255)
page.add_object(heart)
```

Supported SVG commands: `M m L l H h V v C c S s Q q T t A Z z`.

---

## QRCode

QR code rendered from a data string. Requires `pip install edof[qr]`.

```python
qr = page.add_qrcode(x=170, y=15, w=25, h=25, data="https://example.com")
qr.error_correction = "M"
```

### Fields

- `data: str` — text or URL to encode (UTF-8)
- `error_correction: str` — `"L"` (7%), `"M"` (15%), `"Q"` (25%), `"H"` (30%) recovery levels
- `fg_color: tuple` — foreground RGBA (default: black)
- `bg_color: tuple` — background RGBA (default: white)
- `border_modules: int` — quiet zone width in QR module units (default: 4)
- `variable: str` — if set, the QR encodes the variable's value at render time

```python
doc.define_variable("verify_url", type="url")
qr.variable = "verify_url"
doc.set_variable("verify_url", "https://example.com/verify/abc123")
```

Without `[qr]`, QR objects render as a placeholder rectangle with a warning logged to `doc.errors`.

---

## Table

Multi-cell formatted table.

```python
from edof import Table, TableCell

t = Table()
t.transform.x = 15
t.transform.y = 50
t.transform.width  = 180
t.transform.height = 60
t.col_widths = [80, 25, 30, 45]   # in mm; 0 = auto-distribute remaining
t.row_heights = [10, 0, 0, 0]     # 0 = auto-distribute

t.cells = [
    [TableCell(text="Item"),    TableCell(text="Qty"), TableCell(text="Price"), TableCell(text="Total")],
    [TableCell(text="Widget"),  TableCell(text="3"),   TableCell(text="100"),   TableCell(text="300")],
    [TableCell(text="Gadget"),  TableCell(text="1"),   TableCell(text="250"),   TableCell(text="250")],
]
# Style header row
for c in t.cells[0]:
    c.bg_color = (50, 80, 160, 255)
    c.style.color = (255, 255, 255)
    c.style.bold = True

page.add_object(t)
```

### Fields

- `cells: list[list[TableCell]]` — 2D matrix of cells
- `col_widths: list[float]` — widths per column in mm; `0` means "auto-distribute"
- `row_heights: list[float]` — heights per row; `0` means "auto-distribute"
- `table_border: BorderStyle | None` — outer border around the entire table
- `cell_padding: tuple` — default cell padding `(t, r, b, l)` in mm

`num_rows` and `num_cols` are read-only properties derived from `cells`.

### TableCell

Each cell is independently styled.

- `text: str` — plain text content
- `runs: list[TextRun]` — rich text (overrides `text`)
- `style: TextStyle` — text styling
- `bg_color: tuple` — RGBA background
- `padding: tuple` — overrides table-level `cell_padding`
- `colspan: int` — span this cell over multiple columns (default: 1)
- `rowspan: int` — span this cell over multiple rows (default: 1)
- `border_top, border_right, border_bottom, border_left: CellBorder` — independent borders per side. Each `CellBorder` has `enabled`, `color`, `width`, `style` (`"solid"`, `"dashed"`, `"dotted"`).

### `make_table()` helper

```python
from edof import make_table

t = make_table(
    [["Name", "Score"],
     ["Alice", 98],
     ["Bob", 87]],
    header=True,         # first row is styled as header
    alternating=True,    # zebra-stripe data rows
    style="default",     # presets: "default", "modern", "minimal"
)
```

Returns a `Table` configured with reasonable defaults. Adjust further in code.

---

## Group

A container that holds child objects and applies transformations / clipping uniformly.

```python
from edof import Group

g = Group()
g.transform.x = 50
g.transform.y = 50
g.children = [
    page.add_textbox(0, 0, 100, 12, "Header"),
    page.add_shape("line", 0, 14, 100, 0),
]
# Move them out of page.objects and into the group
for child in g.children:
    page.objects.remove(child)
page.add_object(g)
```

### Fields

- `children: list[EdofObject]` — child objects
- `clip: bool` — if `True`, children are clipped to the group's transform bounds

Coordinates of children are interpreted **relative to the group's transform** (not absolute page coordinates). Rotating the group rotates all children together; resizing scales them.

`Group.copy()` deep-copies all children with new IDs. `Group.duplicate()` (alias).

---

## Object equality and copying

All objects are dataclasses underneath, but equality is identity-based (each object has a unique ID). Use `obj.copy()` for a deep copy with a new ID:

```python
template = page.add_textbox(10, 10, 100, 12, "Template")
template.style.bold = True

# Make 5 copies, each shifted down
for i in range(1, 6):
    new = template.copy()
    new.transform.y = 10 + i * 15
    new.text = f"Row {i}"
    page.add_object(new)
```
