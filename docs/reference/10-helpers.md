# Reference: Helpers

Convenience methods for common composition patterns. These save a lot of typing for typical layouts.

---

## High-level page helpers

### `page.add_card(x, y, w, h, title, body, accent_color=None) → Group`

A title + body block in a styled rectangle.

```python
card = page.add_card(
    x=15, y=15, w=180, h=60,
    title="Summary",
    body="Quarterly revenue increased by 15%, driven primarily by enterprise contracts.",
    accent_color=(50, 80, 160),
)
```

Returns a `Group` containing:
- A background `Shape` (rect with rounded corners, light fill)
- An accent line (left edge, in `accent_color`)
- A title `TextBox` (bold)
- A body `TextBox` (auto-wrapped)

You can manipulate the returned group like any object.

### `page.add_metric(x, y, w, h, label, value, subtitle="", value_color=None) → Group`

A "stat card" with a big number and small label.

```python
m = page.add_metric(
    x=15, y=80, w=80, h=40,
    label="Total Revenue",
    value="1,520,000 CZK",
    subtitle="+15% YoY",
    value_color=(50, 130, 80),   # green for positive
)
```

Returns a `Group` containing:
- The label (small, top, gray)
- The value (large, center, optional color)
- The subtitle (small, bottom, gray)

Useful for dashboards.

### `page.add_table(x, y, w, rows, header=True, alternating=True, style="default") → Table`

Quick table from a list-of-lists with reasonable defaults.

```python
t = page.add_table(
    x=15, y=130, w=180,
    rows=[
        ["Name", "Score", "Grade"],
        ["Alice", 98, "A"],
        ["Bob", 87, "B"],
        ["Carol", 92, "A-"],
    ],
    header=True,           # first row is bold + colored
    alternating=True,      # zebra stripes on data rows
    style="default",       # "default" | "modern" | "minimal"
)
```

Internally calls `make_table()` with these settings, then sets the table's `transform.x/y` from the parameters. Width is fixed; height is auto.

Style presets:
- `"default"` — moderate borders, blue header
- `"modern"` — minimal borders, no header background
- `"minimal"` — only header underline, no other borders

### `page.add_kv_list(x, y, w, items, key_width_frac=0.4) → Group`

Two-column "key: value" list.

```python
kv = page.add_kv_list(
    x=15, y=150, w=180,
    items=[
        ("Customer", "ACME s.r.o."),
        ("Order ID", "2026-04-12"),
        ("Status",   "Shipped"),
    ],
    key_width_frac=0.3,    # keys take 30% of width
)
```

Returns a `Group` of TextBoxes laid out as a two-column grid. Keys are bold; values are regular.

### `page.add_textbox_auto(x, y, w, text, min_height=10, **style) → TextBox`

Like `add_textbox()`, but the height is computed from the content. Useful when you don't know in advance how tall the text will be.

```python
tb = page.add_textbox_auto(
    x=15, y=15, w=180,
    text="Some long paragraph that may take 1 to 5 lines depending on its length...",
    min_height=10,
    font_size=11,
    line_height=1.4,
)
```

`**style` keyword args are applied to `tb.style` (e.g. `font_size=14`, `bold=True`, `color=(...)`, `alignment="center"`).

The height is computed by calling `measure_text_height()` (see below).

---

## Layout context managers

These let you compose objects fluently in rows and columns.

### `with page.row(y, gap=2.0, height=8.0) as r:`

Compose horizontally on a single line.

```python
with page.row(y=20, gap=2, height=10) as r:
    r.add_textbox(80, "Name:")           # 80mm wide
    r.add_textbox(120, "{client_name}")  # 120mm wide
```

Inside the `with`:
- `r.add_textbox(width, text, **style)` — add textbox
- `r.add_image(width, resource_id, **kwargs)` — add image
- `r.add_shape(width, shape_type, **kwargs)` — add shape
- `r.x` (read-only) — current x position; use to compute remaining width

The cursor advances by `width + gap` after each item. Items are aligned to `y` and have height `height`.

### `with page.column(x, gap=3.0, width=180.0) as c:`

Compose vertically.

```python
with page.column(x=15, gap=3, width=180) as c:
    c.add_textbox_auto("Long paragraph...")
    c.add_textbox(8, "Footer note")
    c.add_shape(0.5, "line")
```

Inside the `with`:
- `c.add_textbox(height, text, **style)` — fixed-height textbox
- `c.add_textbox_auto(text, min_height=10, **style)` — auto-height textbox
- `c.add_image(height, resource_id, **kwargs)`
- `c.add_shape(height, shape_type, **kwargs)`
- `c.y` (read-only) — current y position

---

## Standalone helpers

### `edof.make_table(rows, header=True, alternating=True, style="default") → Table`

Build a `Table` object without placing it on a page. Manipulate further if needed:

```python
from edof import make_table

t = make_table([["A", "B"], ["1", "2"]], header=True)
t.transform.x = 10
t.transform.y = 50
t.transform.width = 100
page.add_object(t)
```

### `edof.measure_text_height(text, style, width_mm, dpi=300, line_height=None) → float`

Calculate the height (in mm) needed to fit the given text in a frame of the given width with the given style.

```python
from edof import measure_text_height
from edof.format.styles import TextStyle

style = TextStyle(font_family="Helvetica", font_size=11, wrap=True)
height = measure_text_height(
    "Some text that needs to wrap. " * 10,
    style,
    width_mm=180,
    dpi=300,
)
print(f"Needs {height:.1f}mm")
```

Used internally by `add_textbox_auto()` and `add_card()`. Useful directly when you need to plan layouts in advance.

### `edof.mm_to_px(mm, dpi=300) → int`

Convert mm to pixels at given DPI.

```python
edof.mm_to_px(15.0, dpi=300)   # 177
```

### `edof.to_mm(px, dpi=300) → float`

Inverse: pixels to mm.

```python
edof.to_mm(177, dpi=300)   # 14.99...
```

### `edof.from_mm(mm, dpi=300) → int`

Alias of `mm_to_px`.

---

## Recipe: combining helpers for a real layout

```python
import edof

doc = edof.new(width=210, height=297, title="Customer Report")
page = doc.add_page(dpi=300)

# Heading
heading = page.add_textbox(15, 15, 180, 12, "Q4 2026 Customer Report")
heading.style.font_size = 18
heading.style.bold = True

# KV summary block
page.add_kv_list(15, 35, 180, [
    ("Customer",      "{customer_name}"),
    ("Period",        "Q4 2026"),
    ("Account Mgr",   "{manager_name}"),
])

# Three metric tiles in a row
with page.row(y=75, gap=5, height=40) as r:
    r.add_metric_widget(60, "Revenue", "1,520,000 CZK", "+15%", value_color=(50,130,80))
    r.add_metric_widget(60, "Orders",  "147",            "+8%",  value_color=(50,130,80))
    r.add_metric_widget(60, "Active",  "92%",            "−2%",  value_color=(180,80,50))

# (Note: row context manager doesn't have add_metric_widget — that's pseudocode for the example.
#  The actual approach is to add_metric on the page directly with the X positions you want.)

# Detail table
page.add_table(
    x=15, y=130, w=180,
    rows=[["Date", "Description", "Amount"]] + [
        [r['date'], r['desc'], r['amount']] for r in records
    ],
    header=True,
    alternating=True,
)

# Footer
page.add_textbox_auto(
    x=15, y=270, w=180,
    text="Prepared by: {manager_name} on {date}",
    font_size=8,
    color=(120, 120, 120),
)

doc.define_variable("customer_name", required=True)
doc.define_variable("manager_name", required=True)
doc.define_variable("date", type="date")

doc.save("template.edof")
```
