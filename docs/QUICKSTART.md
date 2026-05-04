# Quick start

A 10-minute tour covering the most useful features. After this, you'll know enough to build real templates.

## Hello world

```python
import edof

doc  = edof.new(width=210, height=297, title="My first document")
page = doc.add_page(dpi=300)
page.add_textbox(15, 15, 180, 12, "Hello world!")

doc.save("hello.edof")
doc.export_pdf("hello.pdf")
doc.export_bitmap("hello.png", dpi=300)
```

`edof.new()` creates a blank document. `width` and `height` are in **millimetres**. `add_page()` adds an A4 page (or a page of any size you specified). `add_textbox()` places a text frame at coordinates `(x, y)` of given `(width, height)`.

The `(0, 0)` origin is the top-left corner. Y increases downward.

## Styling text

`add_textbox()` returns a `TextBox` object whose `.style` controls appearance:

```python
tb = page.add_textbox(15, 30, 180, 18, "Big bold heading")
tb.style.font_family = "Helvetica"
tb.style.font_size   = 24
tb.style.bold        = True
tb.style.color       = (50, 80, 160)      # RGB tuple
tb.style.alignment   = "center"           # "left" | "center" | "right" | "justify"
```

For mixed styles within one line, use `runs`:

```python
from edof import TextRun

tb = page.add_textbox(15, 60, 180, 12)
tb.runs = [
    TextRun(text="Awarded to "),
    TextRun(text="Jan Novák", bold=True, color=(150, 50, 0)),
    TextRun(text=" for excellence", italic=True),
]
```

Multiple runs are laid out as one continuous line, respecting per-run formatting.

## Auto-shrink and auto-fill

When text might overflow the box, set `auto_shrink=True` (shrink to fit) or `auto_fill=True` (grow to fill):

```python
tb = page.add_textbox(15, 80, 90, 30, "Some long heading that might be too wide")
tb.style.font_size  = 36
tb.style.auto_shrink = True   # will reduce font size until it fits
```

## Variables and templates

A document can declare typed variables, which are substituted into text using `{name}` placeholders:

```python
doc.define_variable("recipient", required=True)
doc.define_variable("score",     type="number", default=0)

page.add_textbox(15, 100, 180, 12, "Awarded to {recipient}")
page.add_textbox(15, 115, 180, 12, "Score: {score}")

doc.fill_variables({
    "recipient": "Jan Novák",
    "score":     95,
})
doc.export_pdf("certificate.pdf")
```

Variables can be required (loading errors if missing), have defaults, or be optional. See [reference/04-variables.md](reference/04-variables.md) for all variable types (text, number, date, bool, url, image, qr).

## Images

```python
# Add an image to the document's resource store
img_id = doc.add_resource_from_file("logo.png")

# Place it on the page
ib = page.add_image(img_id, x=15, y=140, w=40, h=40)
ib.fit_mode = "contain"   # "contain" | "cover" | "fill" | "stretch"
```

## Shapes

```python
# Rectangle with rounded corners
rect = page.add_shape("rect", 15, 200, 180, 30)
rect.fill.color   = (240, 240, 240, 255)
rect.stroke.color = (100, 100, 100, 255)
rect.stroke.width = 0.5
rect.corner_radius = 3

# Line
line = page.add_shape("line", 15, 240, 180, 0)
line.points = [[0, 0], [180, 0]]
line.stroke.color = (0, 0, 0, 255)
line.stroke.width = 0.3

# Bezier path from SVG path string
from edof import Shape
heart = Shape.from_svg_path("M 50 10 C 40 0 0 0 0 30 C 0 60 50 90 50 90 C 50 90 100 60 100 30 C 100 0 60 0 50 10 Z")
page.add_object(heart)
```

Shape types: `"rect"`, `"ellipse"`, `"line"`, `"polygon"`, `"arrow"`, `"path"`.

## Tables

```python
from edof import make_table

t = make_table(
    [["Item", "Qty", "Price"],
     ["Widget", "3", "100"],
     ["Gadget", "1", "250"]],
    header=True,
    alternating=True,
)
t.transform.x = 15
t.transform.y = 250
t.transform.width  = 180
t.transform.height = 30
page.add_object(t)
```

## QR codes

```python
qr = page.add_qrcode(x=170, y=15, w=25, h=25, data="https://example.com")
qr.error_correction = "M"   # "L" | "M" | "Q" | "H"
```

Requires `pip install edof[qr]`.

## Loading and saving

```python
doc.save("template.edof")               # native format (ZIP)
doc.export_pdf("output.pdf")            # vector PDF (default)
doc.export_pdf("output.pdf", vector=False)   # raster PDF (needs reportlab)
doc.export_bitmap("output.png", dpi=300)
doc.export_svg("output.svg", page=0)

# Load it back
doc = edof.load("template.edof")
```

## Encryption (optional)

Requires `pip install edof[crypto]`. By default, documents are plain ZIP files. To encrypt:

```python
doc = edof.new(title="Confidential")
page = doc.add_page()
page.add_textbox(10, 10, 100, 12, "TOP SECRET")

# Set up multi-level passwords
recovery_key = doc.set_password("admin",  "ownerSecret")
doc.set_password("design", "designerPwd")
doc.set_password("edit",   "editorPwd")
doc.set_password("fill",   "templateFiller")
print("RECOVERY KEY:", recovery_key)   # 24-character key, shown only once

doc.save("secret.edof")

# Loading
doc = edof.load("secret.edof", password="editorPwd")
print(doc.permission_level)            # Permission.EDIT
```

The four levels (`fill < edit < design < admin`) grant different amounts of editing access. See [reference/07-encryption.md](reference/07-encryption.md).

## What's next

You now know enough to build real documents. Some directions to explore:

- The complete object reference in [reference/02-objects.md](reference/02-objects.md)
- All variable types and template features in [reference/04-variables.md](reference/04-variables.md)
- Cookbook recipes in [cookbook/](cookbook/) for full working examples
- Helper methods like `page.add_card()`, `page.add_metric()` in [reference/10-helpers.md](reference/10-helpers.md) — they save a lot of typing for common layouts
