# Reference: Import

edof can read three things from outside its own format: PDF documents (best-effort reconstruction), legacy EDOF 2 archives, and EDOF 3 archives.

## PDF import

### `edof.import_pdf(path, **options) → Document`

Parse a PDF file and return an editable `Document`. Requires `pip install edof[pdf]` (which pulls in `pymupdf` for the parsing engine, `pdfplumber` for table detection, and `reportlab` for the raster fallback).

```python
import edof
doc = edof.import_pdf("input.pdf")
doc.save("editable.edof")
```

### Parameters

- `path: str` — path to the PDF
- `detect_tables: bool` — use `pdfplumber` to detect tables (default: `True` if installed)
- `merge_paragraphs: bool` — group adjacent text fragments with same font into paragraphs (default: `True`)
- `heading_threshold: float` — multiplier above median font size to mark text as a heading (default: `1.4` — text >40% larger than median is a heading)
- `indent_threshold_mm: float` — minimum X-offset to consider a new column (default: `3.0`)
- `extract_images: bool` — extract embedded raster images as resources (default: `True`)
- `extract_paths: bool` — convert vector paths to `Shape` objects (default: `True`)

### How it works

1. **Page extraction.** Page sizes and orientations are read from the PDF.
2. **Text extraction.** `pymupdf` extracts text spans with position, font, size, color.
3. **Block clustering.** Adjacent spans with the same font, similar X position, and close vertical spacing are merged into paragraphs / textboxes.
4. **Heading detection.** Spans larger than `heading_threshold * median_font_size` are tagged as headings.
5. **Table detection** (if `pdfplumber` available). Bounding boxes are merged into `Table` objects with cell text from `pymupdf`.
6. **Image extraction.** Embedded raster images become `ImageBox` objects with the original image data added as resources.
7. **Path extraction.** Vector paths become `Shape` objects (rect, line, polygon, or path).
8. **Font handling.** Embedded fonts are extracted where possible; otherwise mapped to the closest local font.

### Limitations

- Subsetted fonts in source PDFs are remapped; you can't add new characters in that font.
- Type3 vector glyph fonts may not extract cleanly.
- Complex multi-column layouts may need manual cleanup after import.
- Very dense pages may produce many small textboxes that need merging.
- Forms (AcroForm fields) are not parsed; PDF annotations are dropped.

Migration warnings appear in `doc.errors`:

```python
doc = edof.import_pdf("scanned.pdf")
for err in doc.errors:
    print(err)
# 'Page 3: 12 spans skipped (font subset 5xK0HM not extractable)'
# 'Page 5: image dimensions exceed 10000px, downscaled'
```

### When PDF import doesn't work

If the result is a mess (jumbled text, missing content), consider:

- The PDF is image-based (scanned). Text is part of an image, not extractable as text. You'd need OCR first.
- The PDF uses Type3 fonts or embedded subsets without unicode tables. Some text may be unreadable.
- The PDF is encrypted. Decrypt first with another tool.

For document templates, the recommended workflow is to **build the template natively in edof** rather than trying to import an existing PDF — the round-trip is rarely lossless.

---

## Legacy EDOF 2 import

EDOF 2 was an internal pre-release format never publicly distributed. It used:
- A single `data.json` file at the archive root (no separate manifest)
- Float `version` field (`2.2` etc.)
- ARGB hex colors (`#AARRGGBB` — alpha first)
- Only two object types: `text` and `image`
- XOR-obfuscated password (which provided no real security)

When you call `edof.load(path)` on an EDOF 2 archive, edof auto-detects it and migrates to EDOF 4 format on the fly:

```python
doc = edof.load("legacy_v2.edof")
print(doc.errors)
# ['Loaded legacy EDOF 2.2 archive — best-effort migration to v4. ...']
```

### What's migrated

| EDOF 2 | EDOF 4 |
|---|---|
| `EdofTextItem` | `TextBox` |
| `EdofImageItem` | `ImageBox` |
| ARGB hex color | RGB tuple (alpha → object opacity) |
| `font_weight ≥ 600` | `style.bold = True` |
| `max_font_size_pt > font_point_size` | `style.auto_shrink = True`, `font_size = max` |
| `h_align` / `v_align` | `style.alignment` / `style.vertical_align` |
| `images/*` in archive | `doc.resources` entries |
| `z_value` | `obj.layer` |
| `allow_non_uniform_scale: False` | `fit_mode = "contain"` |
| `allow_non_uniform_scale: True` | `fit_mode = "stretch"` |

### What's lost

- `edit_mode` (NONE / TEXT_ONLY / TEXT_FONT / ALL) — informational warning is logged, no equivalent in v4. Use `obj.lock_level` / `lock_text` or document-level encryption for similar effect.
- `edit_password_xor` — completely ignored (XOR is not real security). The editor offers to set up real AES-256 encryption when opening such files.

The migration is **one-way**. The result is a regular EDOF 4 document; `doc.save()` writes it as v4. There's no way to write back to EDOF 2 format.

### Detection logic

`edof.utils.legacy_v2.is_v2_archive(path)` returns `True` if the file looks like EDOF 2:
- Contains a top-level `data.json` (and not `manifest.json`)
- The JSON has `version` field as a number < 3.0, **or**
- Pages have `page_width_mm` field, **or**
- First item's `type` is `"text"` or `"image"`

---

## EDOF 3 archives

EDOF 4 reads EDOF 3 archives natively. The format change between 3 and 4 was additive (new optional features), so any v3 file loads cleanly as v4. Some new v4 fields are added with default values during load.

```python
doc = edof.load("template_v3.edof")
print(doc.errors)
# Possibly empty, or with notes about upgrades from v3 fields
```

If you need to **export back to v3 format** (e.g. for an environment running the older library), use:

```python
doc.export_3x("backwards_compatible.edof")
```

This is a lossy operation — see [reference/05-export.md](05-export.md) and [reference/01-document.md](01-document.md#docexport_3xpath) for what's flattened.

---

## Format version detection

If you want to inspect a file's version without loading it:

```python
from edof.format.serializer import EdofSerializer

manifest = EdofSerializer.peek("unknown.edof")
print(manifest.get("edof_version"))   # e.g. "4.2.0" or "3.0.0"
```

`peek()` reads only the manifest, not the document content. It works on encrypted files too — you'll see the protection block but no actual content.

For very old EDOF 2 archives that have no manifest, `peek()` will fail. Use `is_v2_archive()` first:

```python
from edof.utils.legacy_v2 import is_v2_archive

if is_v2_archive("ancient.edof"):
    print("EDOF 2 — will be migrated on load")
else:
    manifest = EdofSerializer.peek("ancient.edof")
    print(f"Version: {manifest.get('edof_version')}")
```
