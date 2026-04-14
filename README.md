# edof – Easy Document Format 3.0

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%20|%203.10%20|%203.11%20|%203.12%20|%203.13-blue)](https://pypi.org/project/edof/)
[![Tests](https://github.com/DavidSchobl/edof/actions/workflows/publish.yml/badge.svg)](https://github.com/DavidSchobl/edof/actions)
[![PyPI](https://img.shields.io/badge/PyPI-coming%20soon-lightgrey)](https://pypi.org/project/edof/)

**edof** is a Python library for programmatic document creation, template filling and high-quality export.  
Documents are stored as `.edof` files – a versioned ZIP archive with a JSON document tree and all embedded resources (fonts, images).

```python
import edof

doc  = edof.new(width=210, height=297, title="My Certificate")
page = doc.add_page(dpi=300)

tb = page.add_textbox(10, 20, 190, 30, "")
tb.variable       = "recipient"       # bound to a template variable
tb.style.font_size   = 48
tb.style.auto_shrink = True           # shrinks if text doesn't fit, never enlarges
tb.style.alignment   = "center"

doc.define_variable("recipient", required=True)
doc.fill_variables({"recipient": "Jan Novák"})
doc.save("certificate.edof")
doc.export_bitmap("certificate.png", dpi=300)
```

---

## Installation

```bash
# Core library (Pillow only)
pip install edof

# With PDF export
pip install edof[pdf]

# With QR code generation
pip install edof[qr]

# With PyQt6 editor / widget
pip install edof[pyqt6]

# Everything
pip install edof[all]

# Development
pip install edof[dev]
```

**Python 3.9 – 3.13** supported.

---

## Quick Start

### Create a document

```python
import edof

doc  = edof.new(width=210, height=297)   # A4 in mm, 300 dpi default
page = doc.add_page()

# Text box
tb = page.add_textbox(x=10, y=10, width=190, height=30, text="Hello!")
tb.style.font_size  = 36
tb.style.alignment  = "center"
tb.style.bold       = True

# Image
rid = doc.add_resource_from_file("logo.png")
page.add_image(rid, x=10, y=50, width=80, height=50, fit_mode="contain")

# Shape
sh = page.add_shape("rect", x=10, y=110, width=190, height=1)
sh.fill.color = (0, 0, 0, 255)

# QR code  (requires pip install edof[qr])
page.add_qrcode("https://github.com/DavidSchobl/edof", x=160, y=120, size=30)

doc.save("doc.edof")
doc.export_bitmap("doc.png", dpi=300)   # PNG
doc.export_pdf("doc.pdf")               # PDF (requires edof[pdf])
```

---

## Templates & Batch Fill

Objects can be bound to named **variables**. At render time the variable value replaces the object's content.

```python
doc = edof.new()
page = doc.add_page()

# Define variables with types and defaults
doc.define_variable("name",  type="text",   default="—",          required=True)
doc.define_variable("score", type="number", default="0")
doc.define_variable("logo",  type="image",  default="default.png") # file path or URL

# Bind objects to variables
tb_name = page.add_textbox(10, 10, 100, 20, "")
tb_name.variable      = "name"
tb_name.style.auto_shrink = True    # font shrinks if name is long

img = page.add_image(None, 150, 10, 40, 40)
img.variable = "logo"               # value = file path or HTTP URL

# Fill once
doc.fill_variables({"name": "Alice", "score": "98", "logo": "alice.png"})
doc.export_bitmap("alice.png")

# Batch loop
for row in [("Bob", "87", "bob.png"), ("Carol", "95", "carol.png")]:
    doc.fill_variables({"name": row[0], "score": row[1], "logo": row[2]})
    doc.export_bitmap(f"{row[0]}.png")
```

### Missing variables are non-destructive
If a variable has no value set, the object shows its `obj.text` fallback — useful for previewing a template in the editor without filling all fields first.

---

## Object Types

### TextBox

```python
tb = page.add_textbox(x, y, width, height, text="")

# Sizing modes (mutually exclusive):
tb.style.auto_shrink = True     # font_size = maximum; shrinks to fit; never enlarges
tb.style.auto_fill   = True     # fills the box (grows and shrinks up to max_font_size)
# both False = fixed font size

tb.style.font_family   = "Arial"
tb.style.font_size     = 18.0       # pt
tb.style.min_font_size = 4.0        # floor for auto-shrink/fill
tb.style.max_font_size = 200.0      # ceiling for auto-fill
tb.style.bold          = True
tb.style.italic        = True
tb.style.underline     = True
tb.style.strikethrough = True
tb.style.color         = (0, 0, 0)      # RGB
tb.style.alignment     = "center"       # left|center|right|justify
tb.style.vertical_align= "middle"       # top|middle|bottom
tb.style.line_height   = 1.2
tb.style.wrap          = True
tb.style.overflow_hidden = True
```

### ImageBox

```python
img = page.add_image(resource_id, x, y, width, height,
                     fit_mode="contain")   # contain|cover|fill|stretch|none
# fit_mode="contain" – letterboxed, preserves aspect ratio
# fit_mode="cover"   – cropped, fills the box
# fit_mode="fill"    – alias for cover
# fit_mode="stretch" – distorts to fill exactly

rid = doc.add_resource_from_file("photo.jpg")
# or: rid = doc.add_resource(bytes_data, "photo.jpg", "image/jpeg")
```

### Shape

```python
sh = page.add_shape("rect", x, y, width, height)
# Types: "rect" | "ellipse" | "polygon" | "arrow"

sh.fill.color          = (100, 149, 237, 255)   # RGBA
sh.stroke.color        = (50, 80, 180, 255)
sh.stroke.width        = 1.5    # pt
sh.corner_radius       = 4.0    # mm (for rect)
```

### Line

```python
sh = page.add_shape("line", 0, 0, 1, 1)
sh.points = [[x1_mm, y1_mm], [x2_mm, y2_mm]]  # two absolute page coordinates
sh.stroke.color = (0, 0, 0, 255)
sh.stroke.width = 2.0   # pt
```

### QR Code

```python
qr = page.add_qrcode(data="https://example.com", x=10, y=10,
                     size=40, error_correction="M")
# error_correction: "L" | "M" | "Q" | "H"
qr.fg_color = (0, 0, 0, 255)        # RGBA – any color works
qr.bg_color = (255, 255, 255, 255)
qr.variable = "url"   # dynamic data from variable
```

---

## Transform API

Every object supports a full transform chain:

```python
obj.move_to(20, 30)                    # absolute position (mm)
obj.move(10, 5)                        # relative translate
obj.rotate_to(45)                      # absolute rotation (°, clockwise)
obj.rotate(15)                         # add 15° to current rotation
obj.resize_uniform(1.5)               # scale both axes, keep centre
obj.resize(100, 40)                   # set absolute width × height (mm)
obj.resize(100, 40, anchor="center")  # resize keeping centre fixed
obj.flip_h()
obj.flip_v()

# Chainable
obj.move_to(10, 10).resize(80, 30).rotate_to(15)
```

---

## Color Spaces & Bit Depth

```python
page = doc.add_page(color_space="L",  bit_depth=8)   # grayscale
page = doc.add_page(color_space="1")                  # black & white
page = doc.add_page(color_space="RGB", bit_depth=16)  # 16-bit

# Override on export
doc.export_bitmap("gray.tiff", color_space="L",  format="TIFF")
doc.export_bitmap("bw.png",    color_space="1")
```

Supported values: `"RGB"`, `"RGBA"`, `"L"` (grayscale), `"1"` (B&W), `"CMYK"`.

---

## File Format

`.edof` is a plain ZIP archive — inspectable with any ZIP tool:

```
document.edof
├── manifest.json        ← version header, quick metadata
├── document.json        ← full document tree (no binary blobs)
└── resources/
    ├── <uuid>           ← embedded image / font (raw bytes)
    └── …
```

### Version compatibility

| File version vs library | Behaviour |
|---|---|
| Same | Full compatibility |
| File older | Loaded and migrated automatically, non-fatal notice in `doc.errors` |
| File newer | `EdofNewerVersionWarning` emitted; content loaded best-effort |
| File too old (major < 1) | `EdofVersionError` raised |

```python
import warnings
from edof.exceptions import EdofNewerVersionWarning

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    doc = edof.load("newer.edof")

print(doc.errors)      # non-fatal notices from load
```

---

## Command API

```python
from edof.api.commands import execute, CommandHistory

doc = edof.new(); doc.add_page()

oid = execute(doc, {"cmd": "add_textbox", "page": 0,
                    "x": 10, "y": 10, "width": 80, "height": 20,
                    "text": "Hello API"})

execute(doc, {"cmd": "set_style", "object_id": oid, "page": 0,
              "style": {"font_size": 24, "auto_shrink": True}})

execute(doc, {"cmd": "export_bitmap", "page": 0,
              "path": "out.png", "dpi": 300})

# Undo / redo
history = CommandHistory(max_undo=50)
history.push(doc, "initial state")
# … make changes …
doc = history.undo(doc)   # returns restored Document or None
doc = history.redo(doc)
```

Available commands: `add_page`, `remove_page`, `add_textbox`, `add_image`, `add_shape`, `add_qrcode`, `remove_object`, `set_text`, `set_variable`, `fill_variables`, `move_object`, `resize_object`, `rotate_object`, `set_style`, `set_visibility`, `set_layer`, `export_bitmap`, `export_pdf`, `save`, `validate`.

---

## EDOF Editor

A full desktop document editor ships with the repository:

```bash
pip install edof[pyqt6]   # or edof[all]
edof-editor               # open editor
edof-editor myfile.edof   # open file directly
```

**Canvas features:**
- 8 resize handles (corners + edges) with correct rotated-object resize
- Rotation handle — **Shift** = snap to 15°, **Alt** = free rotation
- Double-click `TextBox` → WYSIWYG inline text editor (font size matches canvas zoom)
- Double-click `QRCode` → inline data/URL editor
- Double-click `ImageBox` → file picker to replace the source
- Ghost outlines for hidden objects — still selectable
- Middle-mouse pan · Scroll-wheel zoom

**Property panel** — type-aware:

| Object | Properties shown |
|---|---|
| TextBox | Content (live update), font, size, color + alpha, alignment, sizing mode radio buttons |
| ImageBox | Fit mode, replace image |
| Shape | Fill color + alpha, stroke color + alpha + width, corner radius |
| Line | X1/Y1/X2/Y2 endpoints, stroke |
| QRCode | Data/URL (live update), error correction, FG/BG color + alpha |

**Other editor features:**
- Object list panel (layer order, type, name, variable, visibility, lock)
- Custom RGBA color dialog (`#RRGGBBAA` hex + sliders)
- Layer ordering: bring to front / forward / backward / send to back
- Variables dialog with live re-render on apply
- Print preview (`QPrintPreviewDialog`) with correct page rendering
- Export PNG / JPEG / TIFF / PDF
- 60-step undo/redo
- Internationalisation — add `editor_lang/XX.json` for any language (base: `en.json`)

---

## EDOF CLI

Fill templates and export from the command line without opening the editor:

```bash
# Inspect a template
edof-cli info      template.edof
edof-cli objects   template.edof
edof-cli validate  template.edof

# Export with variables
edof-cli export template.edof output.png \
    --set name="Jan Novák" \
    --set date="2025-01-01" \
    --dpi 300

# JSON variables
edof-cli export template.edof output.png \
    --json-vars '{"name":"Jan","score":"98"}'

# All pages  (use {page} or {n} in filename)
edof-cli export template.edof page_{page}.png --all-pages

# PDF
edof-cli export template.edof output.pdf
```

| Flag | Short | Description |
|---|---|---|
| `--set KEY=VALUE` | `-s` | Set one variable (repeatable) |
| `--json-vars JSON` | `-j` | Set multiple variables as JSON |
| `--page N` | `-p` | Page index (0-based, default 0) |
| `--all-pages` | `-A` | Export all pages |
| `--format` | `-f` | `png` `jpg` `tiff` `bmp` `pdf` |
| `--dpi N` | `-d` | Resolution (default 300) |
| `--color-space` | `-c` | `RGB` `RGBA` `L` `1` `CMYK` |

---




## License

MIT – see [LICENSE](LICENSE).

---

## Links

- **PyPI:** https://pypi.org/project/edof/
- **GitHub:** https://github.com/DavidSchobl/edof
- **Issues:** https://github.com/DavidSchobl/edof/issues
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
