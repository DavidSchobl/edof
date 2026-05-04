# Cookbook: Import a PDF, edit, re-export

> Requires `pip install edof[pdf]`

A common workflow: you have an existing PDF (a form, an old invoice template, a brochure) that you want to modify. PDFs are normally hard to edit, but edof can reconstruct most PDFs into editable documents.

## Important caveats first

PDF reconstruction is **best-effort**. Don't expect a pixel-perfect match. The cleaner the source PDF, the better the result.

What works well:
- Single-column or two-column text documents
- Basic invoices and forms
- Simple letterheads
- Documents with embedded standard fonts

What works poorly:
- Scanned documents (text is part of the image, not extractable)
- Type3 vector glyph fonts (some glyphs may not extract)
- Complex multi-column magazine layouts
- PDFs with subsetted custom fonts (limited substitution available)
- Documents with extensive use of clipping or transparency groups

For mission-critical templates, consider rebuilding from scratch in edof rather than importing.

## Step 1: Import

```python
import edof

doc = edof.import_pdf("old_template.pdf")

# See what was extracted
for i, page in enumerate(doc.pages):
    print(f"Page {i+1}: {len(page.objects)} objects, "
          f"{page.width:.1f} x {page.height:.1f} mm")

# Check for warnings
if doc.errors:
    print("\nImport warnings:")
    for err in doc.errors:
        print(f"  - {err}")
```

Typical import takes a few seconds for a multi-page document.

## Step 2: Inspect what was imported

```python
page = doc.pages[0]

for obj in page.objects:
    print(f"  {type(obj).__name__:<10}  pos=({obj.transform.x:.1f}, {obj.transform.y:.1f})  "
          f"size={obj.transform.width:.1f}x{obj.transform.height:.1f}", end="")
    if hasattr(obj, 'text') and obj.text:
        print(f"  text={obj.text[:40]!r}")
    elif hasattr(obj, 'shape_type'):
        print(f"  shape={obj.shape_type}")
    else:
        print()
```

Use the editor to visually inspect:

```python
doc.save("imported.edof")
# Then run: edof-editor imported.edof
```

## Step 3: Clean up

Imported documents often need manual cleanup:

```python
# Find and merge fragmented text (PDFs often split paragraphs into many small textboxes)
def merge_fragmented_text(page, vertical_threshold=2.0, horizontal_threshold=5.0):
    """Merge adjacent textboxes with same font into single textboxes."""
    from edof import TextBox

    textboxes = sorted(
        [o for o in page.objects if isinstance(o, TextBox)],
        key=lambda t: (t.transform.y, t.transform.x)
    )

    merged = []
    skip = set()
    for i, tb in enumerate(textboxes):
        if id(tb) in skip:
            continue
        # Find compatible neighbors
        for j in range(i + 1, len(textboxes)):
            other = textboxes[j]
            if id(other) in skip:
                continue
            # Check if other is on next line, with similar X
            same_x = abs(tb.transform.x - other.transform.x) < horizontal_threshold
            below = (other.transform.y - tb.transform.y - tb.transform.height) < vertical_threshold
            same_font = (tb.style.font_family == other.style.font_family and
                         abs(tb.style.font_size - other.style.font_size) < 0.5)
            if same_x and below and same_font:
                tb.text = tb.text + "\n" + other.text
                tb.transform.height += other.transform.height
                skip.add(id(other))
            else:
                break

        merged.append(tb)

    # Replace page objects
    page.objects = [o for o in page.objects if not isinstance(o, TextBox) or id(o) in [id(m) for m in merged] or id(o) in skip]
    # Actually simpler: rebuild
    page.objects = merged + [o for o in page.objects if not isinstance(o, TextBox)]


merge_fragmented_text(doc.pages[0])
```

(This is illustrative — for production use, add unit tests and refine the matching heuristics for your specific PDF style.)

## Step 4: Add variables for templating

The big payoff: convert hardcoded text in the imported PDF into a real template.

```python
page = doc.pages[0]

# Find textboxes with specific content and convert them to variables
for obj in page.objects:
    if isinstance(obj, edof.TextBox):
        if "John Doe" in obj.text:
            obj.text = obj.text.replace("John Doe", "{customer_name}")
        elif "$1,500" in obj.text:
            obj.text = obj.text.replace("$1,500", "${amount}")
        elif "March 15, 2024" in obj.text:
            obj.text = obj.text.replace("March 15, 2024", "{date}")

# Define the variables
doc.define_variable("customer_name", required=True, label="Customer name")
doc.define_variable("amount", type="number", default=0)
doc.define_variable("date", type="date", required=True)

doc.save("template_from_pdf.edof")
```

You now have a reusable template based on the imported PDF.

## Step 5: Adjust styling

Imported PDFs often have idiosyncratic styling. Clean it up in code:

```python
# Standardize font sizes (round to half-points)
for page in doc.pages:
    for obj in page.objects:
        if isinstance(obj, edof.TextBox):
            obj.style.font_size = round(obj.style.font_size * 2) / 2

# Use a consistent font family
for page in doc.pages:
    for obj in page.objects:
        if isinstance(obj, edof.TextBox):
            if obj.style.font_size > 14:
                obj.style.font_family = "Helvetica"   # heading
            else:
                obj.style.font_family = "Helvetica"   # body
```

## Step 6: Re-export

```python
# Save as edof template
doc.save("template_v4.edof")

# Re-export to PDF (now in vector mode!)
doc.export_pdf("re-exported.pdf")
```

The re-exported PDF will be:
- A vector PDF (smaller, searchable)
- Resolution-independent
- Editable in edof going forward

## Common issues and fixes

### "Imported document has too many tiny textboxes"

PDFs often store each line of text as a separate object. Use the merge function above, or use the editor to visually select and combine them.

### "Fonts look different from original"

The vector PDF writer uses Standard 14 fonts. If the original used a custom font that wasn't extractable, edof falls back to Helvetica/Times. To preserve the original look:

1. Identify the font in the source PDF (open in a PDF reader, "Document Properties → Fonts")
2. Install that font on your system if you don't have it
3. Re-export with raster mode: `doc.export_pdf("output.pdf", vector=False)`

This uses Pillow which can render any installed TTF.

### "Tables came out as a mess of textboxes"

Auto table detection isn't perfect. Two fixes:
- Pass `detect_tables=True` to `import_pdf` if you didn't (it's the default if `pdfplumber` is installed)
- Manually rebuild the table:

```python
# Find the textboxes that should be a table
candidates = [o for o in page.objects if some_criteria(o)]
# Remove them
for c in candidates:
    page.objects.remove(c)
# Build a real Table
from edof import Table, TableCell
t = Table()
t.cells = [...]   # populate from the texts you extracted
page.add_object(t)
```

### "Some text is missing from the import"

A few possibilities:
- The text was an embedded image (pdfminer/pymupdf can't extract it). Check with: `[o for o in page.objects if isinstance(o, edof.ImageBox)]`
- The text was rendered using a Type3 vector font without unicode mapping. Run the import with `--verbose` flag (or check `doc.errors`) to see warnings.
- The text is rendered as path data (vector outlines). edof imports these as Shape objects, but they're not editable as text.

### "Imported document is bigger than expected"

The PDF importer extracts every embedded image at full resolution. For documents with high-res photos, the resulting `.edof` can be large. Mitigations:
- Resize images after import:

```python
from PIL import Image
import io

for page in doc.pages:
    for obj in page.objects:
        if isinstance(obj, edof.ImageBox):
            data = doc.resources.get(obj.resource_id)
            img = Image.open(io.BytesIO(data))
            if img.width > 2000:
                img.thumbnail((2000, 2000))
                buf = io.BytesIO()
                img.save(buf, "PNG")
                doc.resources.replace(obj.resource_id, buf.getvalue())
```

(`doc.resources.replace` exists for this purpose.)

## End-to-end script

```python
import edof
import sys

if len(sys.argv) < 3:
    print("Usage: pdf-to-template.py input.pdf output.edof")
    sys.exit(1)

input_pdf, output_edof = sys.argv[1], sys.argv[2]

print(f"Importing {input_pdf}...")
doc = edof.import_pdf(input_pdf)
print(f"  {len(doc.pages)} pages, {sum(len(p.objects) for p in doc.pages)} objects")

if doc.errors:
    print("Warnings:")
    for err in doc.errors[:5]:
        print(f"  - {err}")

# Clean up: remove tiny textboxes (often artifacts)
for page in doc.pages:
    page.objects = [
        o for o in page.objects
        if not (isinstance(o, edof.TextBox) and (o.transform.width < 2 or o.transform.height < 1))
    ]

# Save
doc.save(output_edof)
print(f"Saved: {output_edof}")
print(f"Open in editor: edof-editor {output_edof}")
```
