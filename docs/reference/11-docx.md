# Reference: Word (.docx) import & export

_New in 4.2.0._

EDOF can read and write Microsoft Word `.docx` files for document-mode
documents (the continuous text flow used by the editor's document mode).

This is an **optional** feature backed by
[`python-docx`](https://python-docx.readthedocs.io/):

```bash
pip install edof[docx]
```

If the package is missing, the functions raise a clear `RuntimeError` instead
of failing obscurely.

The public entry points mirror the other importers:

| Function | Purpose | Returns |
|----------|---------|---------|
| `edof.export_docx(doc, path)` | Write a Document to `.docx` | `DocxReport` |
| `edof.import_docx(path)` | Read a `.docx` into a Document | `Document` (or `(Document, DocxReport)`) |

---

## Export

```python
import edof

doc = edof.load("contract.edof")
report = edof.export_docx(doc, "contract.docx")
print(report.paragraphs, "paragraphs written")
for warning in report.warnings:
    print("note:", warning)
```

What is written:

- Paragraphs and runs with **bold**, *italic*, underline and ~~strikethrough~~.
- Font family and font size.
- Run text colour.
- Paragraph alignment (left / center / right / justify).
- Page size and margins (taken from the EDOF page and document margins).
- Force-page-break-before-paragraph.
- Single-level bullet and numbered lists.
- **Line height matched exactly to EDOF.** EDOF computes a line's height as
  `font_size × line_height` (em-based). Word's "multiple" line-spacing rule
  instead multiplies the font's natural line height (~1.15 em for Arial),
  which comes out noticeably taller. To keep pagination aligned, the exporter
  writes an *exact* line height in points equal to EDOF's, so Word lays the
  text out at the same pitch and the page breaks line up with the editor.

If the document is not in document mode, the exporter falls back to gathering
text from the page's text boxes so something sensible is still produced.

---

## Import

```python
import edof

doc = edof.import_docx("letter.docx")
doc.save("letter.edof")
```

Imports create a fresh **document-mode** EDOF document (A4, 15 mm margins) and
lay the text out across pages. The following round-trips:

- Runs with bold / italic / underline / strikethrough.
- Font family and size, run colour.
- Paragraph alignment, page-break-before.
- Line spacing (Word "multiple" → EDOF multiplier; an exact spacing written by
  EDOF's own exporter is converted back to a multiplier).
- Space before / after a paragraph.
- Bullet and numbered lists (single level; nesting level is best-effort).

### Compatibility report

`import_docx` never silently drops content. Anything EDOF cannot represent yet
is detected and reported. Pass `return_report=True` to inspect it:

```python
doc, report = edof.import_docx("report.docx", return_report=True)

print("imported paragraphs:", report.paragraphs)
print("not supported:", report.unsupported)        # e.g. ['tables', 'images']

if not report.recommend_import:
    # Significant content (tables, images, drawings, …) would be lost.
    print("Not recommended:", report.recommend_reason)
else:
    doc.save("report.edof")
```

`DocxReport` fields:

| Field | Meaning |
|-------|---------|
| `paragraphs` | number of body paragraphs imported / exported |
| `warnings` | non-blocking notes (e.g. simplified lists) |
| `unsupported` | list of content types that could not be represented |
| `recommend_import` | `False` when significant content would be lost |
| `recommend_reason` | human-readable explanation for the recommendation |
| `summary()` | one-string summary of the above |

### Not supported yet

These are reported and skipped (never silently imported):

- **Major** (triggers "not recommended"): tables, images / drawings, text
  boxes, equations, embedded objects.
- **Minor** (imported text is fine, these are dropped): headers / footers,
  footnotes / endnotes, comments.

Other Word features not represented: multi-level list numbering definitions,
tab stops, style inheritance, sections / columns, fields, tracked changes.

The desktop editor exposes the same feature under **File → Import Word
(.docx)…** and **File → Export Word (.docx)…**, and shows the compatibility
report in a dialog before an import proceeds.

---

## Round-trip notes

Exporting then re-importing preserves the text and the formatting listed above.
Because EDOF and Word use different line-spacing models, an exact round-trip of
the *spacing multiplier* may differ by a hair (e.g. 1.15 vs 1.156) due to
point-rounding; the visual line height is preserved.
