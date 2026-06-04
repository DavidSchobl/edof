# edof – Easy Document Format

[![PyPI version](https://img.shields.io/pypi/v/edof.svg)](https://pypi.org/project/edof/)
[![Python](https://img.shields.io/pypi/pyversions/edof.svg)](https://pypi.org/project/edof/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build status](https://github.com/DavidSchobl/edof/actions/workflows/publish.yml/badge.svg)](https://github.com/DavidSchobl/edof/actions/workflows/publish.yml)
[![Downloads](https://static.pepy.tech/badge/edof)](https://pepy.tech/project/edof)
[![Sponsor](https://img.shields.io/badge/sponsor-%E2%9D%A4-ff69b4)](https://github.com/sponsors/DavidSchobl)

📚 **Documentation**: <https://davidschobl.github.io/edof/> &nbsp;|&nbsp;
💖 **Support development**: <https://github.com/sponsors/DavidSchobl>

A Python library and visual editor for programmatic document creation, template filling, and high-quality export. Documents are described in code or in a small ZIP-based file format, then rendered to PNG, JPEG, TIFF, BMP, PDF, RTF, or SVG. A PyQt6 desktop editor is included for visual editing with Photoshop-style layer effects, table cell editor, multi-blend compositing, and a path tool.

The library prioritizes a few specific things: vector PDF output without large native dependencies, rich-text and table rendering that survives high-DPI export, a template-filling workflow with typed variables, an optional encryption layer for documents that need it, and a rich visual editor that maps 1:1 to the API.

## How does it compare?

|                                           | edof | Photoshop | PDF (raw) | Inkscape | ReportLab | WeasyPrint | FPDF |
|-------------------------------------------|:----:|:---------:|:---------:|:--------:|:---------:|:----------:|:----:|
| **Open source / free**                    | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Pure Python (no native deps for core)** | ✅ | n/a | n/a | ❌ | ✅ | ❌ | ✅ |
| **Programmatic document creation**        | ✅ | ⚠️ | ❌ | ⚠️ | ✅ | ⚠️ | ✅ |
| **Visual editor included**                | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Vector PDF export**                     | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Raster export (PNG, JPEG, TIFF)**       | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **SVG export**                            | ✅ | ⚠️ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **RTF import / export**                   | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Templates with typed variables**        | ✅ | ❌ | ⚠️ | ❌ | ⚠️ | ⚠️ | ❌ |
| **Conditional visibility (visible_if)**   | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **AES-256 document encryption**           | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ | ❌ |
| **Permission tiers (fill/edit/admin)**    | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Layer effects (drop shadow, glow…)**    | ✅ | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| **15+ blend modes**                       | ✅ | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| **Tables with per-cell formatting**       | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **QR code generation**                    | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **PDF import (text + paths + images)**    | ✅ | ❌ | n/a | ✅ | ❌ | ❌ | ❌ |
| **Embedded sub-document references**      | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ | ❌ |
| **Custom font import**                    | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| **Photo retouching / drawing tools**      | ❌ | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| **Bitmap painting**                       | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Animation / video timeline**            | ❌ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |

Legend: ✅ first-class · ⚠️ partial / via extensions · ❌ not supported · n/a not applicable

**Note:** edof is a *layout & document* tool, not a paint or photo-retouching app. Pixel-level drawing/painting tools are not on the current roadmap. If there's strong demand they could be added in a future major release; right now edof focuses on giving you the most powerful possible vector-and-raster layout system that's still fully scriptable from Python.

## Install

```bash
pip install edof                # core only — Pillow + edof
pip install edof[crypto]        # + AES-256 document encryption
pip install edof[pdf]           # + PDF import (pymupdf), table detection (pdfplumber),
                                #   raster PDF fallback (reportlab)
pip install edof[qr]            # + QR code generation
pip install edof[pyqt6]         # + desktop editor
pip install edof[all]           # everything above
```

Console scripts: `edof-cli` (terminal tool), `edof-editor` (PyQt6 GUI editor), `edof-viewer` (lightweight read-only viewer).

## Quick start

```python
import edof
from edof import TextRun

doc  = edof.new(width=210, height=297, title="Certificate")
page = doc.add_page(dpi=300)

# Plain text
page.add_textbox(15, 30, 180, 12, "Awarded to").style.font_size = 14

# Rich text (mixed styles in a single line)
name = page.add_textbox(15, 50, 180, 25)
name.runs = [
    TextRun(text="Jan ", font_size=36),
    TextRun(text="Novák", font_size=36, bold=True, color=(150, 50, 0)),
]
name.style.alignment = "center"

doc.save("certificate.edof")
doc.export_pdf("certificate.pdf")        # vector PDF, no reportlab needed
doc.export_bitmap("certificate.png", dpi=300)
doc.export_svg("certificate.svg")
```

## Feature overview

### Document model

A `Document` contains pages; each `Page` contains objects. All measurements are in millimetres so layouts are resolution-independent.

**Object types** (`edof.format.objects`):

| Type | Purpose | Notable fields |
|---|---|---|
| `TextBox` | Single- or multi-line text with optional rich-text runs | `text`, `runs`, `style`, `padding`, `border`, `fill` |
| `ImageBox` | Embedded raster image | `resource_id`, `fit_mode` (contain/cover/fill/stretch) |
| `Shape` | Vector primitive | `shape_type` (rect/ellipse/line/polygon/arrow/path), `path_data`, `corner_radius`, `fill`, `stroke` |
| `QRCode` | QR code with selectable error correction | `data`, `error_correction`, `fg_color`, `bg_color`, `border_modules` |
| `Table` | Formatted table with per-cell styling | `cells`, `col_widths`, `row_heights`, `table_border` |
| `Group` | Container with optional clip | `children` |

Common fields on every object: `transform` (position/size/rotation/flip), `opacity`, `layer`, `visible`, `visible_if`, `blend_mode`, `lock_level`, `lock_text`, `lock_position`, `tags`, `shadow`, `effects` (v4.1.0+).

#### Transform fields

```python
obj.transform.x          # mm, X position (top-left)
obj.transform.y          # mm, Y position (top-left)
obj.transform.width      # mm, width  (use this name, not `w`)
obj.transform.height     # mm, height (use this name, not `h`)
obj.transform.rotation   # degrees, clockwise around the box center
obj.transform.flip_h     # bool
obj.transform.flip_v     # bool
```

#### Color formats

All color fields accept tuples in 0–255 range. Both RGB (3-tuple) and RGBA (4-tuple) are accepted; missing alpha defaults to 255 (opaque):

```python
obj.style.color    = (74, 144, 226)        # RGB → alpha 255 implied
obj.fill.color     = (245, 245, 248, 255)  # RGBA — explicit
obj.stroke.color   = (0, 0, 0, 200)        # RGBA — translucent black
shape.fill.color   = "#4a90e2"             # v4.1.0+: hex string accepted
```

When read back, colors come as tuples (`obj.style.color` returns `(74, 144, 226)`, `obj.fill.color` returns `(245, 245, 248, 255)`).

#### Padding

Currently `padding` is a single `float` (mm) applied uniformly on all four sides:

```python
tb.padding = 2.0          # 2 mm on all sides
```

A 4-side struct (`padding.left`, `padding.right`, etc.) is on the roadmap for v5.0. For now, if you need asymmetric padding, use a wider/taller textbox with `padding=0` and position content explicitly.

### Rich text

A `TextBox` can hold a list of `TextRun` segments instead of (or in addition to) plain text. Each run can override `font_family`, `font_size`, `bold`, `italic`, `underline`, `strikethrough`, `color`, and `background` (highlight). The layout engine packs runs into lines respecting these per-segment styles, and supports auto-shrink/auto-fill globally across all runs.

```python
tb.runs = [
    TextRun(text="Mixed: "),
    TextRun(text="bold ",   bold=True),
    TextRun(text="big ",    font_size=24),
    TextRun(text="and ",    color=(220, 0, 0)),
    TextRun(text="underlined", underline=True),
]
```

### Tables

`Table` is a separate object type (not a group of textboxes). Each `TableCell` carries its own `TextStyle` (or `runs[]`), `bg_color`, `padding`, and four independent `CellBorder` instances (top/right/bottom/left, each with its own color, width, and on/off). Column widths and row heights can be specified explicitly or auto-distributed. `colspan` and `rowspan` are supported.

```python
from edof import Table, TableCell, make_table

t = make_table([["Name", "Score"], ["Alice", "98"], ["Bob", "87"]],
               header=True, alternating=True)
page.add_object(t)
```

### Vector graphics

Shapes render as resolution-independent vectors in PDF and SVG output. The `path` shape type accepts either a list of SVG-style commands (`M`, `L`, `H`, `V`, `C`, `Q`, `Z`) or an SVG path string:

```python
from edof import Shape

# From SVG path string
sh = Shape.from_svg_path("M 10 10 L 50 10 C 70 30 90 30 110 10 Z")

# Direct command list
sh.path_data = [["M", 10, 10], ["L", 50, 10], ["C", 70, 30, 90, 30, 110, 10], ["Z"]]
```

Standard rectangles support corner radius. Ellipses, lines, polygons, and arrows are also vector primitives.

### Gradients

`FillStyle.gradient` accepts a `Gradient` with multiple stops, in linear or radial mode:

```python
from edof import Gradient

shape.fill.gradient = Gradient(
    type="linear", angle=45,
    stops=[(0.0, (255,   0,   0, 255)),
           (0.5, (255, 255,   0, 255)),
           (1.0, (  0,   0, 255, 255))],
)
shape.fill.color = None   # gradient takes precedence
```

### Variables and templates

Documents can define typed variables that get substituted at render time. Supported types: `text`, `number`, `date`, `bool`, `url`, `image`, `qr`. Object text uses `{name}` placeholders; `ImageBox` and `QRCode` can bind directly to a variable.

```python
doc.define_variable("recipient", required=True)
doc.define_variable("score",     type="number", default=0)

page.add_textbox(10, 10, 100, 12, "Awarded to {recipient}")

doc.fill_variables({"recipient": "Jan Novák", "score": 95})
doc.export_pdf("filled.pdf")
```

### Repeating sections

`page.repeat_objects(template_objs, data_list, gap=2.0)` duplicates a template for each row of a data list, substitutes `{column_name}` placeholders, and auto-paginates onto new pages when the page is full:

```python
header_tb = page.add_textbox(10, 10, 180, 8, "Sales Report")
row_tpl   = page.add_textbox(10, 20, 180, 6, "{name}: {amount} CZK")

page.objects.remove(row_tpl)   # we'll insert copies instead
new_pages = page.repeat_objects([row_tpl],
    [{"name": "Alice", "amount": 1500},
     {"name": "Bob",   "amount": 2300},
     # ... 200 more rows ...
    ], gap=1.0)
```

### Conditional visibility

`obj.visible_if` is a small expression evaluated at render time against the document's variables. Boolean operators, comparisons, arithmetic, and string equality are supported. No function calls, attribute access, or imports are allowed (safe AST evaluator).

```python
discount_label = page.add_textbox(10, 200, 180, 8, "DISCOUNT: -{discount} CZK")
discount_label.visible_if = "discount > 0"
```

### Blend modes

Per-object compositing modes: `normal`, `multiply`, `screen`, `darken`, `lighten`, `overlay`. Implemented for the Pillow renderer.

### Per-object locks (independent of encryption)

```python
heading.lock_level = "design"   # only design+ permission can modify
heading.lock_text  = True       # text is read-only even with admin (until cleared)
```

These flags work in plain documents too — they're a soft template-protection mechanism. The editor disables corresponding actions when an object is locked.

### Export formats

| Format | Method | Vector? | Notes |
|---|---|---|---|
| PNG / JPEG / TIFF / BMP | `doc.export_bitmap(path)` | raster | Configurable DPI, color space (RGB/RGBA/L/CMYK/1), bit depth (8/16) |
| PDF — vector (default) | `doc.export_pdf(path)` | yes | Pure-Python writer; searchable text; Standard 14 PDF fonts; WinAnsiEncoding incl. Czech diacritics |
| PDF — raster fallback | `doc.export_pdf(path, vector=False)` | no | Uses reportlab if installed; embeds rendered pages as images |
| SVG (per page) | `doc.export_svg(path, page=0)` | yes | `<text>` elements (searchable in browsers), gradients as `<linearGradient>/<radialGradient>`, images base64-embedded |
| Multi-page bitmaps | `doc.export_all_pages("page_{n}.png")` | raster | Filename pattern with `{n}` |

### PDF comparison

The vector PDF writer is a pure-Python implementation; it does not require reportlab. For a typical document, the resulting file is significantly smaller than rasterized output, and the text is selectable.

| Metric | Vector PDF | Raster PDF (reportlab) |
|---|---|---|
| Implementation | Pure Python (built-in) | reportlab — large native dep |
| Text | Vector ops (selectable, copyable) | Bitmap |
| File size (typical A4 page with text + shapes + table) | ~5 KB | ~80–135 KB |
| Czech / Latin-1 diacritics | WinAnsiEncoding mapping built-in | Depends on reportlab font setup |
| Resolution-dependent? | No | Yes — pick a DPI when exporting |
| Searchable in PDF readers | Yes | No |
| Copy-paste from PDF | Yes | No |

The integration test in this repo produces a vector PDF that is roughly 25× smaller than the equivalent raster PDF for the same A4 page. The exact ratio depends on content; pages dominated by photographic images will not see this kind of compression because raster image data is the limiting factor.

The vector writer currently supports the Standard 14 PDF fonts (Helvetica, Times, Courier with bold/italic) plus an alias mapping for common system fonts (Arial → Helvetica, Times New Roman → Times-Roman, etc.). TTF embedding for arbitrary fonts is not yet implemented in the vector writer; if you need a specific custom font in PDF output, use `vector=False` to fall back to the raster pipeline (which embeds the font via Pillow's text rendering).

### PDF import

`edof.import_pdf("file.pdf")` reads an existing PDF and produces an editable EDOF Document. It uses pymupdf for text/image/path extraction, reconstructs paragraph blocks via clustering (same font, similar X-alignment, vertical gap within line spacing), detects headings by font size relative to median, and extracts embedded fonts where possible.

```python
doc = edof.import_pdf("template.pdf",
                      detect_tables=True,        # uses pdfplumber if installed
                      merge_paragraphs=True,
                      heading_threshold=1.4,
                      indent_threshold_mm=3.0)
doc.save("template.edof")
```

This is best-effort and will not perfectly reconstruct every PDF. Common limitations:
- Subsetted fonts in the source PDF are remapped to the closest local full font where possible; if no match is found, the subset is embedded but adding new characters in that font is not possible.
- Type3 vector glyph fonts may not extract cleanly.
- Complex column layouts may need manual cleanup after import.

Migration warnings are appended to `doc.errors`.

### Legacy EDOF 2 import

EDOF 2 was an internal pre-release format that was never publicly distributed. EDOF 4 detects EDOF 2 archives automatically and migrates them on `edof.load(path)`. The migration handles the old ARGB color encoding, font weight ranges, the auto-shrink convention (`max_font_size_pt > font_point_size`), and embedded images. The migration is one-way; the result cannot be saved back to EDOF 2.

If the legacy archive used the old XOR-obfuscated password (which provided no real protection), the editor offers to upgrade to real AES-256 encryption.

### Save back to v3 format

```python
doc.export_3x("for_old_library.edof")
```

Produces a v3-compatible `.edof` with v4-only features flattened: `Table` becomes a Group, rich-text runs collapse to plain text, paths are sampled to polygons, gradients become a single average color, `visible_if` is evaluated once and baked into `.visible`. The original document is not modified.

### Encryption (optional, opt-in)

Documents are plain ZIP archives by default. When you call `doc.set_password(level, pwd)`, the document switches to encrypted mode on the next save. Requires `pip install edof[crypto]`.

**Algorithm:** AES-256-GCM for content, PBKDF2-SHA256 (600 000 iterations) for password-to-key derivation, 16-byte salt per slot, 12-byte nonce per ciphertext, 16-byte GCM tag for tamper detection.

**Permission levels** (hierarchical — higher implies all lower):

| Level | Allows |
|---|---|
| `view`   | Render, print, export. No modifications. |
| `fill`   | view + change variable values (template filling). |
| `edit`   | fill + change object `.text` and rich-text run text. |
| `design` | edit + change styles, fonts, colors, layout, structure (add/remove objects and pages). |
| `admin`  | design + manage passwords, recovery key, override per-object locks. |

Each level can have its own password. Whichever password the user types determines what they can do. A 24-character recovery key is generated automatically when the first password is set; it grants `admin` access and is shown exactly once.

**Encryption modes:**
- `full` — entire content + resources encrypted as a single AES-GCM blob inside the ZIP. The manifest reveals only that the file is encrypted, the KDF parameters, and the slot count. Title, page count, and all metadata are hidden.
- `partial` — only sensitive fields are encrypted (object text, rich-text runs, image data, QR data, table cell text, variable values). Structure remains visible: page count, page sizes, fonts, alignment, colors, layout, and the document title. Useful when you want to share a layout template publicly while keeping the actual content private. In partial mode, opening without a password gives a redacted view (`█` placeholder) where the layout is visible but the content is not.
- `none` — default; plain ZIP, no encryption.

```python
import edof
from edof.crypto import EDIT, DESIGN, ADMIN

doc = edof.new(title="Confidential")
page = doc.add_page()
page.add_textbox(10, 10, 100, 12, "TOP SECRET")

# Set up multi-level passwords (write down the recovery key!)
recovery = doc.set_password("admin", "ownerSecret")
doc.set_password("design", "designerPwd")
doc.set_password("edit",   "editorPwd")
doc.set_password("fill",   "templateFiller")
print("RECOVERY KEY:", recovery)        # 24 chars, shown once

doc.encryption_mode = "full"             # default after first password
doc.save("secret.edof")

# Loading
doc = edof.load("secret.edof", password="editorPwd")
print(doc.permission_level)              # Permission.EDIT
doc.can(DESIGN)                          # False
doc.require(EDIT)                        # OK
# doc.require(DESIGN)                    # raises PermissionError

# Recovery
doc = edof.load("secret.edof", recovery_key=recovery)   # → admin

# Rotation (no payload re-encryption — just rewraps the slot)
doc.change_password("edit", "editorPwd", "newEditorPwd")

# Removal (requires admin)
doc.remove_password("fill")
doc.clear_all_protection()               # → encryption_mode = "none"
```

**Per-object locks** add a finer-grained layer on top of doc-level encryption (and work without encryption too):

```python
heading.lock_level = "design"   # only design+ can modify, regardless of doc-level perms
heading.lock_text  = True       # text never editable until lock_text is cleared (admin-only)
```

**What encryption protects against**: reading content without the password; tampering with the encrypted bytes (GCM auth tag detects any modification); brute-forcing weak passwords (PBKDF2 with 600k iterations is intentionally slow).

**What it does not protect against**: a user with the password running their own decryption code (they have the password); side-channel attacks on the host running the library; loss of all passwords AND the recovery key — the document is then mathematically unrecoverable. Write down the recovery key.

## Recipes

### Headings with auto-computed height (no more silent text loss)

```python
# v4.1.0+: add_textbox_auto computes height from content and accepts style kwargs
heading = page.add_textbox_auto(
    20, 20, 170, "MY HEADING",
    font_size=24, bold=True, alignment="center",
)
# Read final height to position the next element
next_y = heading.transform.y + heading.transform.height + 5  # 5 mm gap
```

### Tables with explicit sizing

```python
# v4.1.0+: make_table accepts position + size and computes total height
tbl = edof.make_table(
    rows=[
        ["Product",    "Qty", "Price"],
        ["Widget",     "3",   "29.99"],
        ["Gadget",     "1",   "149.00"],
    ],
    header=True, alternating=True,
    x=20, y=next_y,
    col_widths=[100, 30, 40],   # mm; sum becomes table.transform.width
    row_heights=[10, 8, 8],     # mm; sum becomes table.transform.height
    # Or just: width=170 (auto-distribute equal column widths)
)
page.add_object(tbl)
print(f"Table ends at y = {tbl.transform.y + tbl.transform.height} mm")
```

### Colors — accepted formats

```python
import edof

tb.style.color   = (74, 144, 226)              # RGB tuple
tb.style.color   = (74, 144, 226, 200)         # RGBA tuple
tb.style.color   = edof.as_color("#4a90e2")    # hex via helper
tb.style.color   = edof.as_color("#4a90e2cc")  # 8-digit hex with alpha
```

### Per-side padding (v4.1.0+)

```python
tb.style.padding = 2.0           # uniform 2 mm on all sides
tb.style.padding_left  = 8.0     # override left only
tb.style.padding_right = 4.0     # override right only
# top/bottom fall back to padding=2.0
```



A PyQt6 desktop editor (`edof-editor`) ships with the library. It is a working editor, not a demo: it produces files that the API can load and round-trip without loss.

**Editing**
- Direct manipulation: select, move, resize, rotate, multi-select via Ctrl+click and lasso
- Properties panel adapts to the selected object type
- Object list panel with drag-to-reorder layers, eye/lock toggles
- 60-step undo/redo
- Snap-to-grid (Ctrl+G), magnetic alignment guides during drag
- Inline text editing with WYSIWYG sizing across zoom levels and Windows DPI scaling
- Find & Replace dialog (Ctrl+F) — regex and case-sensitive options
- Gradient editor with visual stop list

**Templates**
- File → New from Template…: Blank A4 portrait/landscape, Business Card, Certificate, Invoice with table

**File operations**
- File → Open: detects encrypted, EDOF 2, and EDOF 3 files automatically; prompts for password if needed
- File → Save / Save As / Save as v3 (downgrade)
- File → Import PDF: reconstructs editable document from a PDF
- File → Export PNG / Export SVG / Export PDF
- File → Batch from CSV: fill variables for each CSV row, export per-row PNG/PDF
- File → Print

**Document protection**
- Document → Unlock for editing… (Ctrl+Shift+L): password / recovery-key prompt; after unlock, a dialog lists exactly what the granted permission level can and cannot do
- Document → Protection…: full management UI for setting / changing / removing passwords, switching between full and partial encryption, and showing the recovery key
- Status bar continuously shows current protection state: 🔓 Plain / 🔒 Locked / 🔓 Unlocked: \<level\>
- Toolbar and menu actions are disabled when the current permission level forbids them; pressing a disabled-equivalent shortcut shows a clear "needs *level* password" dialog

**Other**
- Cursor position in mm in the status bar
- Page panel for multi-page docs
- Translatable UI: `editor_lang/en.json`; add `XX.json` for other languages

## Viewer

A lightweight read-only viewer (`edof-viewer`) ships alongside the editor (v4.1.1+). It is designed for the case where someone receives a `.edof` file and just wants to view, print, or convert it — without launching the full editor.

```bash
pip install 'edof[viewer]'
edof-viewer document.edof
```

**Features:** multi-page navigation (Page Up/Down, Ctrl+Home/End), zoom (Fit page Ctrl+0, Fit width Ctrl+1, Ctrl++/-), pan with middle-mouse drag, OS-level Print dialog, Export PDF, Export current page as PNG.

### File association

Register `.edof` files with `edof-viewer` so double-clicking opens the viewer (similar to PDF files):

```bash
edof-cli associate-files            # register
edof-cli associate-files --status   # check current status
edof-cli associate-files --remove   # unregister
```

This works on Windows (per-user, no admin needed) and Linux (writes desktop entry + MIME type). On macOS, full `.app` bundle association is planned for v5.0.

## Programmatic helpers

A few high-level convenience methods on `Page` make typical layouts shorter:

```python
page.add_card(x, y, w, h, title, body, accent_color)
page.add_metric(x, y, w, h, label, value, subtitle, value_color)
page.add_table(x, y, w, rows, header=True, alternating=True)
page.add_kv_list(x, y, w, items, key_width_frac=0.4)
page.add_textbox_auto(x, y, w, text, min_height=10, **style)   # height computed from content
```

Layout helpers (cursor-based composition):

```python
with page.row(y=10, gap=2, height=8) as r:
    r.add_textbox(80, "Name:")
    r.add_textbox(120, "{client_name}")

with page.column(x=15, gap=3, width=180) as c:
    c.add_textbox_auto("Long paragraph that grows to fit...")
    c.add_textbox(8, "Footer")
```

Standalone:

```python
height_mm = edof.measure_text_height("Some text", style, width_mm=100, dpi=300)
```

## CLI

```bash
edof-cli info template.edof              # metadata, variables, fonts used
edof-cli objects template.edof           # all objects with type and layer
edof-cli validate template.edof          # structural sanity check
edof-cli export template.edof out.png \
    --set name=Jan --set score=98        # fill variables and export
edof-cli batch template.edof data.csv \
    -o "out_{n}.png"                     # one file per CSV row
edof-cli import template.pdf -o template.edof
edof-cli convert legacy.edof -o new.edof  # EDOF 2 → 4
edof-cli export template.edof out.pdf --vector       # default
edof-cli export template.edof out.pdf --raster       # via reportlab
edof-cli export template.edof out.svg
```

## File format

`.edof` is a ZIP archive.

**Plain mode:**
```
template.edof
├── manifest.json     — version header, title, page count
├── document.json     — full document data
└── resources/<id>    — one file per embedded resource (images, fonts)
```

**Encrypted modes:**
```
template.edof
├── manifest.json           — version header + protection block (mode, KDF, slots)
├── encrypted_payload.bin   — AES-256-GCM ciphertext
├── document.json           — only in 'partial' mode (with sensitive fields redacted)
└── resources/<id>          — only in 'partial' mode (non-sensitive resources)
```

The manifest's `protection.slots` field contains, for each password level:
```json
{
  "permission": "edit",
  "kdf": "pbkdf2-sha256",
  "iterations": 600000,
  "salt":        "<base64, 16 bytes>",
  "wrapped_key": "<base64, 60 bytes — AES-GCM-encrypted content key>"
}
```

Format version is bumped to 4.0.1. Older 4.0.0 files load unchanged. Files saved by 4.0.1 that use no 4.0.1-only features are bit-compatible with 4.0.0 readers.

## Comparison with other libraries

This is intentionally narrow rather than promotional. Different libraries are good at different things; pick the one that matches your problem.

| | edof | reportlab | WeasyPrint | python-docx | Pillow alone |
|---|---|---|---|---|---|
| **Primary use case** | Templates, designed docs, editor | PDF generation from code | HTML/CSS → PDF | Word documents | Image processing |
| **Document model** | Page + objects with mm coords | Drawing primitives, callbacks | HTML/CSS | DOCX object model | n/a |
| **Built-in editor** | PyQt6 GUI (`edof-editor`) | No | No | No | No |
| **File format** | ZIP-based `.edof`, JSON inside | n/a (writes PDFs only) | n/a | DOCX | n/a |
| **Vector PDF output** | Built-in pure-Python writer | Yes (its primary purpose) | Yes (via Cairo) | No (requires conversion) | No |
| **Templating with typed variables** | Yes | Manually in your code | Via Jinja or similar | Manually | n/a |
| **Rich text with mixed styles in one line** | `TextRun` segments | Paragraph flowables | Yes (HTML inline) | Yes | n/a |
| **Tables with per-cell styling** | Yes | Yes | Yes | Yes | n/a |
| **PDF import / re-edit** | Best-effort via pymupdf | No | No | n/a | n/a |
| **AES document encryption** | Optional, with permission levels | No | No | DOCX has its own (different model) | n/a |
| **External dependencies (core)** | Pillow only | Several native libs | Cairo, Pango, large stack | lxml | None |

A non-exhaustive note on what other libraries do better: reportlab has the most mature PDF generation engine and the broadest feature coverage for printed output; WeasyPrint is the right answer if your content lives in HTML/CSS already; python-docx is the standard for Word interoperability; Pillow remains the right tool for image manipulation. edof is the right answer when you want documents with a consistent visual layout, type-checked variable filling, an editor your users can use, and an output format that survives high-DPI export — without requiring users to write CSS or learn ReportLab's flowables API.

## Side-by-side version installs

If you want to keep multiple edof versions on the same machine for testing or downgrade safety, use isolated virtualenvs:

```cmd
mkdir D:\apps\Edof_V401\edof-python
cd D:\apps\Edof_V401\edof-python
:: extract this version's source here
python -m venv .venv
.venv\Scripts\activate
pip install -e .[all]
deactivate
```

A small `.bat` makes switching painless:

```bat
@echo off
call D:\apps\Edof_V401\edof-python\.venv\Scripts\activate.bat
cd /d D:\apps\Edof_V401\edof-python
cmd /k prompt [edof v4.0.1] $P$G
```

Each version's venv is independent. Removing a version is `rmdir /s /q <folder>`; nothing else needs cleanup.

## Compatibility

- Python 3.9+
- All exports work with Pillow alone; everything else is optional
- Cross-platform (tested on Windows, Linux, macOS)

## Status and roadmap

Stable: document model, renderer, all export paths, variable system, editor, encryption, EDOF 2 / 3 / 4 round-trips, PDF import.

Known limitations:
- Vector PDF writer uses Standard 14 fonts only; arbitrary TTF embedding for vector mode is on the roadmap. For now, custom fonts work via the raster fallback (`vector=False`) or via Pillow during bitmap export.
- HMAC document signatures (separate from encryption) are not yet implemented.
- Per-page encryption (some pages encrypted, some not) is intentionally not supported — encryption is at the document level only.

## License

MIT. See `LICENSE`.
