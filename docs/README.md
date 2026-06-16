# edof Documentation

Reference documentation for the **edof** Python library — a tool for programmatic document creation, template filling, and high-quality export. Documents are described in code or in a small ZIP-based file format, then rendered to PNG, JPEG, TIFF, BMP, PDF, or SVG.

This documentation covers every public function, class, and method, plus practical recipes for common tasks.

## Where to start

If you have never used edof, read in this order:

1. [Installation](INSTALL.md) — how to install edof and which optional features need extra packages
2. [Quick start](QUICKSTART.md) — a 10-minute tour covering the 80% most useful features
3. [Reference: Document & Page](reference/01-document.md) — the basic document model

If you have a specific task in mind, jump straight to:

- [Cookbook: Generate certificates from CSV](cookbook/certificate.md)
- [Cookbook: Build an invoice template](cookbook/invoice.md)
- [Cookbook: Batch generate PDFs from data](cookbook/batch-pdf.md)
- [Cookbook: Encrypted templates with multi-level passwords](cookbook/encrypted-template.md)
- [Cookbook: Import a PDF, edit, and re-export](cookbook/pdf-import-edit.md)
- [Cookbook: Flat-design poster with layer effects](cookbook/effects-poster.md)

Runnable end-to-end scripts live in [`examples/`](../examples/README.md).

## Reference

Complete API reference, organized by topic:

| Topic | What's inside |
|---|---|
| [01 — Document & Page](reference/01-document.md) | `edof.new`, `Document`, `Page`, persistence, validation |
| [02 — Objects](reference/02-objects.md) | `TextBox`, `ImageBox`, `Shape`, `QRCode`, `Table`, `Group`, common fields |
| [03 — Styles](reference/03-styles.md) | `TextStyle`, `FillStyle`, `StrokeStyle`, `Gradient`, `ShadowStyle`, `CellBorder`, `Transform` |
| [04 — Variables & Templates](reference/04-variables.md) | Variable types, `define_variable`, `fill_variables`, placeholders, `repeat_objects` |
| [05 — Export](reference/05-export.md) | PDF (vector / raster), bitmap formats, SVG, multi-page, printing |
| [06 — Import](reference/06-import.md) | `import_pdf`, EDOF 2 legacy import, version migration |
| [07 — Encryption](reference/07-encryption.md) | Passwords, permission levels, `set_password`, `unlock`, recovery keys, per-object locks |
| [08 — Editor](reference/08-editor.md) | The PyQt6 desktop editor — features, shortcuts, dialogs |
| [09 — CLI](reference/09-cli.md) | `edof-cli` and all its subcommands |
| [10 — Helpers](reference/10-helpers.md) | `add_card`, `add_metric`, `add_kv_list`, `row()`, `column()`, `make_table`, `measure_text_height` |
| [11 — DOCX interop](reference/11-docx.md) | Word import / export — `import_docx`, `export_docx`, mapping and limitations |
| [12 — Layer effects](reference/12-effects.md) | `LayerEffect` — shadows, glows, stroke, overlays, bevel, chromatic aberration, halftone, long shadow with gradient stops |

## Advanced

| Topic | What's inside |
|---|---|
| [.edof file format](advanced/file-format.md) | ZIP layout, JSON schema, manifest format, encrypted archive structure |
| [Extending edof](advanced/extending.md) | Adding custom object types, custom serialization |
| [Troubleshooting](advanced/troubleshooting.md) | Common issues and how to fix them |

## Conventions used in this documentation

**Measurements** — All sizes and positions are in millimetres (`mm`) unless stated otherwise. Object opacity is `0.0`–`1.0`. Colors are RGB or RGBA tuples in `0`–`255` range, e.g. `(50, 80, 160, 255)`.

**Coordinate system** — `(0, 0)` is the top-left corner of the page. X increases rightward, Y increases downward.

**Code examples** — Examples that need only the core library (`pip install edof`) are unmarked. Examples requiring an optional extra are tagged like:

> Requires `pip install edof[crypto]`

## Version

This documentation is for **edof 4.3.0.4**.
