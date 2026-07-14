# Reference: Export

edof can render documents to several output formats: PDF (vector or raster), bitmap (PNG/JPEG/TIFF/BMP), and SVG.

## PDF export

### `doc.export_pdf(path, vector=True, **kwargs)`

Export the entire document to a PDF.

**Parameters:**
- `path: str` — output PDF path
- `vector: bool` — `True` (default) uses the built-in pure-Python vector PDF writer; `False` falls back to raster PDF via `reportlab` (requires `pip install edof[pdf]`)

**Vector mode (default):**
- Pure Python, no external dependencies
- Vector text (selectable, copyable, searchable in PDF readers)
- Vector shapes (resolution-independent)
- Significantly smaller files than raster
- WinAnsiEncoding for Latin-1 characters including Czech diacritics
- Standard 14 PDF fonts (Helvetica / Times / Courier with bold and italic variants)

**Raster mode (`vector=False`):**
- Requires `reportlab` and `Pillow`
- Each page is rendered to a bitmap, then embedded in the PDF
- File size is much larger (depends on DPI and content)
- Text is NOT selectable (it's part of the image)
- Supports any TTF font (since it goes through Pillow)
- Useful when you need a custom font or when the vector writer can't handle a feature

### Vector PDF font handling

The vector writer maps font families to the Standard 14 PDF fonts:

| Family | Maps to |
|---|---|
| `Helvetica`, `Arial`, `sans-serif` | Helvetica (with bold / italic variants) |
| `Times New Roman`, `Times`, `serif` | Times-Roman |
| `Courier`, `monospace` | Courier |

Any other font family falls back to Helvetica with a warning logged to `doc.errors`.

If you need a specific TTF in PDF output, use raster mode:

```python
doc.export_pdf("output.pdf", vector=False)
```

### File size comparison

For an A4 page with text, shapes, and a table:

| Mode | Typical size |
|---|---|
| `vector=True` | 5–10 KB |
| `vector=False` at 300 DPI | 80–135 KB |
| `vector=False` at 600 DPI | 250–400 KB |

These ratios depend heavily on content. Pages dominated by photographic images don't compress with vector mode (the bottleneck is the image data, which is the same either way).

### Example

```python
doc.export_pdf("output.pdf")                       # vector
doc.export_pdf("output_raster.pdf", vector=False)  # raster fallback
```

---

## Bitmap export

### `doc.export_bitmap(path, page=0, dpi=300, format=None, color_space=None, bit_depth=8)`

Export a single page to an image file.

**Parameters:**
- `path: str` — output file path
- `page: int` — 0-based page index (default: 0, the first page)
- `dpi: int` — dots per inch (default: 300)
- `format: str` — image format: `"PNG"`, `"JPEG"`, `"TIFF"`, `"BMP"`, etc. If `None`, auto-detected from path extension.
- `color_space: str` — override page's `color_space` field (`"RGB"`, `"RGBA"`, `"L"`, `"1"`, `"CMYK"`)
- `bit_depth: int` — `8` (default) or `16`

**Returns:** the filepath written.

```python
doc.export_bitmap("output.png", dpi=300)
doc.export_bitmap("output.jpg", dpi=150, format="JPEG")
doc.export_bitmap("page2.png", page=1, dpi=600)
doc.export_bitmap("grayscale.png", color_space="L")
```

### Resolution

Pixel dimensions = `(width_mm / 25.4) * dpi`. So an A4 page (210 × 297 mm) at 300 DPI is 2480 × 3508 pixels.

### Format auto-detection

If `format=None`, the format is taken from the file extension:
- `.png` → PNG
- `.jpg` / `.jpeg` → JPEG
- `.tif` / `.tiff` → TIFF
- `.bmp` → BMP
- `.gif` → GIF

### Standalone function

`edof.export_page_bitmap(doc, page_index, path, **kwargs)` is the same operation but as a standalone function. Useful when you want to export a page in a function-style pipeline:

```python
from edof import export_page_bitmap

export_page_bitmap(doc, page_index=0, path="page1.png", dpi=300)
```

---

## Multi-page bitmap export

### `edof.export_all_pages(doc, path_pattern, **kwargs)`

Export every page to a separate file, using a path pattern with `{n}` (or `{page}`) placeholder.

```python
from edof import export_all_pages

paths = export_all_pages(doc, "out/page_{n}.png", dpi=300)
print(paths)
# ['out/page_1.png', 'out/page_2.png', 'out/page_3.png', ...]
```

The placeholder is replaced with the 1-based page number (so `page_1.png`, not `page_0.png`). Returns the list of written paths.

`{page}` is an alias for `{n}` for compatibility.

---

## SVG export

### `doc.export_svg(path, page=0)`

Export a single page to SVG.

**Parameters:**
- `path: str` — output `.svg` path
- `page: int` — 0-based page index (default: 0)

```python
doc.export_svg("output.svg")           # first page
doc.export_svg("page3.svg", page=2)
```

### SVG output features

- Text rendered as `<text>` elements (selectable in browsers, searchable, accessible)
- Shapes rendered as native SVG primitives (`<rect>`, `<ellipse>`, `<line>`, `<polygon>`, `<path>`)
- Gradients exported as `<linearGradient>` / `<radialGradient>` definitions
- Images base64-embedded inline (the SVG is self-contained, no external files)
- QR codes rendered as inline SVG paths

The SVG output is suitable for web embedding, vector editing in Inkscape / Illustrator, and conversion via other tools.

### Limitations

- Drop shadows and blend modes have limited SVG filter support
- Custom path-rendering effects from the bitmap renderer don't carry over

---

## Bytes export (no file)

### `edof.export_to_bytes(doc, format="png", page=0, **kwargs) → bytes`

Render to bytes without writing to disk. Useful for sending to a network, embedding in a database, or piping through other tools.

```python
from edof import export_to_bytes

png_bytes = export_to_bytes(doc, page_index=0, format="PNG", dpi=300)
jpg_bytes = export_to_bytes(doc, format="JPEG", jpeg_quality=85)

# Send to API
import requests
requests.post("https://api.example.com/upload", files={"file": png_bytes})
```

---

## Render functions (low-level)

For advanced use, you can render directly to Pillow `Image` objects:

### `edof.render_page(doc, page_index=0, dpi=300, ...) → PIL.Image`

Render one page to a Pillow `Image`. Useful for further processing (cropping, filtering, compositing).

```python
from edof import render_page
from PIL import Image

img = render_page(doc.pages[0], doc.resources, doc.variables, dpi=300)
img.thumbnail((200, 200))             # resize
img.save("thumbnail.png")
```

### `edof.render_document(doc, dpi=300, ...) → list[PIL.Image]`

Render every page, return a list of Images.

```python
from edof import render_document

images = render_document(doc, dpi=150)
for i, img in enumerate(images):
    img.save(f"thumb_{i}.png")
```

---

## Printing

### `doc.print_document(printer_name=None, copies=1, dpi=None)`

Send the document to a system printer. Requires `pip install edof[pyqt6]`.

**Parameters:**
- `printer_name: str | None` — name of the printer; `None` uses the default
- `copies: int` — number of copies (default: 1)
- `dpi: int | None` — print resolution; `None` uses the printer's native (capped at 300)

```python
doc.print_document()                                 # default printer
doc.print_document(printer_name="HP LaserJet", copies=3)
```

To list available printers programmatically (PyQt6):

```python
from PyQt6.QtPrintSupport import QPrinterInfo
for info in QPrinterInfo.availablePrinters():
    print(info.printerName())
```

---

## Export and encryption

When a document is encrypted (`encryption_mode != "none"`), exporting works as follows:

- **Plain export** (PDF, PNG, SVG) is **always allowed** regardless of permission level — the user can render what they're allowed to see.
- The exported file itself is **never encrypted** — encryption is a property of the `.edof` file format, not the rendered output.
- If the document is **locked** (encrypted but not yet unlocked), export fails with an exception. Unlock first.

```python
doc = edof.load("secret.edof", password="myPass")
doc.export_pdf("output.pdf")   # works
doc.export_bitmap("output.png")  # works

doc.lock()
doc.export_pdf("output2.pdf")   # raises — content key forgotten
```

---

## Performance tips

- **Vector PDF is faster than raster PDF.** Less computation, smaller output.
- **Higher DPI dramatically increases bitmap render time.** 300 DPI = standard print quality; 150 DPI suffices for screen viewing.
- **`render_document()` reuses font / resource caches** across pages — exporting all pages at once is faster than calling `render_page()` in a loop.
- **For large documents with many template repetitions**, build the document once, then export multiple variations:

```python
doc = edof.load("template.edof")

for record in customer_data:
    doc.fill_variables(record)
    doc.export_pdf(f"out/customer_{record['id']}.pdf")
```

---

## Batch export (v4.4.0)

`edof.batch.generate.export_batch()` renders every batch row to files; the
editor's **Generate…** dialog is a front-end for it.

```python
from edof.batch.generate import export_batch

ok, written, errors = export_batch(
    doc, doc.batch, doc.batch.rows, out_dir,
    pattern="[ROW_NUMBER:03]_[ROW_NAME]",
    fmt="pdf",             # png | jpg | svg | pdf | edof
    scope="all",           # "page" (page_idx) or "all"
    page_idx=0,
    sources="integrate",   # edof only: "integrate" | "external"
    output="per_row",      # pdf/edof: "per_row" | "single"
    progress=None,         # progress(done, total) -> False cancels
    dpi=300)
```

| fmt | scope="page" | scope="all" |
|---|---|---|
| png / jpg / svg | one file per row | one file per row **per page** (`[PAGE]` token, auto-appended as `_p[PAGE]` when missing) |
| pdf | single-page PDF | multipage PDF |
| edof | single-page document | whole document |

**Output shape (pdf / edof).** `output="per_row"` writes one file per row
with tag-based names. `output="single"` writes **one multipage file**: every
row's page(s) appended in row order, the pattern used once as a plain
filename. The single `.edof` is *baked*: fixed pages with the values filled
in, no document body and no batch config, so it reopens exactly as
generated. `progress(done, total)` is called between rows; returning `False`
cancels (files already written stay, an error entry says `Cancelled`).

**Source modes (edof):**

* `"integrate"` — one self-contained `.edof`: file-path images are
  materialised into the resource store (apply does that automatically) and
  the used fonts are embedded.
* `"external"` — the row's document is written next to a `sources/` folder
  holding the referenced files, objects point at the *relative* path, and
  the pair ships as `<name>.zip` — an **editable bundle**. `Document.load`
  resolves relative resource paths against the `.edof` location, so the
  unpacked bundle renders from any working directory.

**Filename tags** (case-insensitive, collisions de-duplicated):
`[ROW_NUMBER]`, `[ROW_NUMBER:04]`, `[ROW_NAME]`, `[PAGE]`, `[PAGE:02]`,
`[{Header}]`, `[{Header:upper}]`, `[{Header:lower}]`.

## Image compression (v4.4.0)

Photo-heavy documents (large PNG sources) can be shrunk by re-encoding the
embedded images, either into the saved `.edof` or into an exported PDF.

```python
n, before, after = doc.recompress_images("jpeg", 75)  # or ("png", 100)
doc.save("small.edof")

doc.export_pdf("small.pdf", image_format="jpeg", image_quality=60)
```

`recompress_images` re-encodes every image resource: `"png"` is lossless,
`"jpeg"` is lossy at the given quality (1-100). Images with real
transparency always stay lossless PNG (JPEG has no alpha), a resource is
only replaced when the re-encoded bytes are smaller, and non-image
resources (fonts) are untouched. Returns `(n_changed, bytes_before,
bytes_after)`.

In PDF export, `image_format="jpeg"` embeds images as DCT (JPEG) streams at
`image_quality`; an image's alpha channel survives as a lossless `/SMask`
over the JPEG base. Editor UI: the **Export PDF** dialog and the batch
**Generate** dialog have an *Images* choice (Lossless, JPEG 90/75/60/40 %),
and **File → Save optimized copy…** saves a re-encoded copy of the open
document (the original stays untouched) and reports the MB saved.

`export_batch(..., image_format="jpeg", image_quality=75)` applies the same
re-encoding to the pdf and edof outputs, per row and single-file alike.

## Font embedding (v4.4.0)

```python
doc.save("file.edof", embed_fonts=True)   # or: n = doc.embed_used_fonts()
```

Embeds the font files for every family+weight combination the document's
text actually uses (pages, runs, tables, header/footer templates and
containers). Idempotent — already-embedded families are skipped. Embedded
fonts resolve **weight-aware** by the real family name from each font
file's name table (`"Nunito Sans"` matches `NunitoSans-Bold.ttf` for bold
runs), in every text path including rich-text runs.

> Editor view aids (the variable rainbow, focus highlights, link-target
> marks) are **never** included in any export.
