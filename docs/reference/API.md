# API reference

_Generated from `edof` 4.2.4 (format 4.2.0)._


This page documents the complete public API exported by `import edof`. It is generated directly from the code with `docs/_gen_api.py`, so the signatures and descriptions match the installed version exactly.


## Contents


**Classes**

- Document model: [`Document`](#document), [`Page`](#page), [`ResourceStore`](#resourcestore)

- Objects: [`EdofObject`](#edofobject), [`TextBox`](#textbox), [`ImageBox`](#imagebox), [`Shape`](#shape), [`QRCode`](#qrcode), [`Group`](#group), [`Table`](#table) _(TBD)_, [`TableCell`](#tablecell) _(TBD)_, [`CellBorder`](#cellborder) _(TBD)_, [`SubDocumentBox`](#subdocumentbox), [`SvgBox`](#svgbox)

- Styles: [`TextStyle`](#textstyle), [`TextRun`](#textrun), [`StrokeStyle`](#strokestyle), [`FillStyle`](#fillstyle), [`ShadowStyle`](#shadowstyle), [`Gradient`](#gradient), [`LayerEffect`](#layereffect)

- Variables: [`VariableStore`](#variablestore), [`VariableDef`](#variabledef)

- Serialization: [`EdofSerializer`](#edofserializer)

- Geometry: [`Transform`](#transform)

- Exceptions & warnings: [`EdofError`](#edoferror), [`EdofVersionError`](#edofversionerror), [`EdofResourceError`](#edofresourceerror), [`EdofRenderError`](#edofrendererror), [`EdofVariableError`](#edofvariableerror), [`EdofAPIError`](#edofapierror), [`EdofValidationError`](#edofvalidationerror), [`EdofPrintError`](#edofprinterror), [`EdofNewerVersionWarning`](#edofnewerversionwarning), [`EdofMissingOptionalWarning`](#edofmissingoptionalwarning), [`EdofMissingFontWarning`](#edofmissingfontwarning)


**Functions**

- Convenience: [`new`](#new), [`load`](#load), [`import_pdf`](#import_pdf), [`import_rtf`](#import_rtf), [`import_docx`](#import_docx), [`export_docx`](#export_docx)

- Tables: [`make_table`](#make_table) _(TBD)_

- Rendering: [`render_page`](#render_page), [`render_document`](#render_document)

- Bitmap export: [`export_page_bitmap`](#export_page_bitmap), [`export_all_pages`](#export_all_pages), [`export_to_bytes`](#export_to_bytes)

- Geometry helpers: [`to_mm`](#to_mm), [`from_mm`](#from_mm), [`mm_to_px`](#mm_to_px)

- Colour: [`as_color`](#as_color)

- Text metrics: [`measure_text_height`](#measure_text_height)

- [Constants](#constants)


---


## Functions


## Convenience

### `new`

```python
new(width: float = 210.0, height: float = 297.0, **kwargs) -> edof.format.document.Document
```

Create a new blank Document.

Args:
    width, height: page size in millimetres (default A4 portrait).
    **kwargs: forwarded to ``Document`` (e.g. ``default_dpi``, ``title``).

Example:
    >>> import edof
    >>> doc = edof.new(210, 297, title="Hello", dpi=300)
    >>> page = doc.add_page()
    >>> page.add_textbox(15, 15, 180, 12, "Hello world!")
    >>> doc.save("hello.edof")


---

### `load`

```python
load(path: str, password: str = None, recovery_key: str = None) -> edof.format.document.Document
```

Load an .edof file and return a Document.

Automatically detects:
  - Legacy EDOF 2 archives (best-effort, one-way migration)
  - Encrypted EDOF 4 archives (requires password= or recovery_key=)
Migration warnings appear in doc.errors.


---

### `import_pdf`

```python
import_pdf(path: str, **kwargs) -> edof.format.document.Document
```

Import a PDF as an editable EDOF Document.

Requires pymupdf (`pip install edof[pdf]`).

Options:
    detect_tables       (bool, default False) — heuristic table detection (needs pdfplumber)
    merge_paragraphs    (bool, default True)  — cluster spans into paragraphs
    heading_threshold   (float, default 1.4)  — font_size > median × X → heading
    indent_threshold_mm (float, default 3.0)  — first-line indent detection
    extract_paths       (bool, default True)  — convert vector paths (v4.0.3)
    extract_images      (bool, default True)  — extract embedded raster images (v4.0.3)

Example:
    >>> doc = edof.import_pdf("report.pdf", detect_tables=True)
    >>> doc.save("report.edof")


---

### `import_rtf`

```python
import_rtf(path: str) -> edof.format.document.Document
```

Import an RTF file as an editable EDOF Document.

Each non-empty paragraph becomes a TextBox stacked vertically; runs
preserve bold/italic/underline/size/color. Tables, images, lists, and
other complex RTF features are not supported.

Example:
    >>> doc = edof.import_rtf("letter.rtf")


---

### `import_docx`

```python
import_docx(path: str, return_report: bool = False)
```

Import a Word (.docx) file as a document-mode EDOF Document.

Requires python-docx (`pip install edof[docx]`).

The body text flow is imported with bold / italic / underline /
strikethrough, font family and size, run colour, paragraph alignment,
line spacing, space before/after, page breaks and simple lists.
Unsupported content (tables, images, drawings, text boxes, equations,
embedded objects, and — minor — headers/footers, footnotes, comments) is
NOT imported; it is detected and described in the returned report.

Args:
    path: path to the .docx file.
    return_report: when True, return ``(Document, DocxReport)`` so you can
        inspect ``report.unsupported`` / ``report.recommend_import`` /
        ``report.recommend_reason``; when False (default), return just the
        Document, matching ``import_pdf`` / ``import_rtf``.

Example:
    >>> doc, report = edof.import_docx("contract.docx", return_report=True)
    >>> if not report.recommend_import:
    ...     print("Heads up:", report.recommend_reason)
    >>> doc.save("contract.edof")


---

### `export_docx`

```python
export_docx(doc: edof.format.document.Document, path: str)
```

Export a document-mode EDOF Document to a Word (.docx) file.

Requires python-docx (`pip install edof[docx]`).

Writes the body text flow with run formatting (bold / italic / underline /
strikethrough, font, size, colour), paragraph alignment, page size and
margins, page breaks, simple lists, and a line height matched exactly to
EDOF's so pagination in Word lines up with the editor.

Returns a ``DocxReport`` (``report.paragraphs``, ``report.warnings``).

Example:
    >>> doc = edof.load("contract.edof")
    >>> report = edof.export_docx(doc, "contract.docx")
    >>> print(report.paragraphs, "paragraphs written")


---


## Tables

### `make_table`

> **Experimental / TBD.** This is a work in progress and not yet complete. The API and behaviour may change; avoid relying on it in production.

```python
make_table(rows: 'List[List[str]]', header: 'bool' = True, header_bg=(83, 74, 183, 255), header_color=(255, 255, 255), alt_bg=(245, 245, 252, 255), alternating: 'bool' = True, x: 'Optional[float]' = None, y: 'Optional[float]' = None, width: 'Optional[float]' = None, col_widths: 'Optional[List[float]]' = None, row_heights: 'Optional[List[float]]' = None, row_height: 'float' = 8.0, header_height: 'Optional[float]' = None) -> 'Table'
```

Quick helper to build a Table from list-of-lists.

accept x, y, width, col_widths, row_heights — Transform is set
accordingly and Table.transform.height is computed from row_heights so
callers can immediately read tbl.transform.y + tbl.transform.height for
the next vertical position.

Examples:
    # Auto-distribute columns across width=120mm, default row height 8mm
    tbl = edof.make_table(rows, header=True, x=20, y=20, width=120)

    # Explicit column widths and row heights
    tbl = edof.make_table(rows, x=20, y=20,
                           col_widths=[60, 30, 30],
                           row_heights=[10, 8, 8, 8])


---


## Rendering

### `render_page`

```python
render_page(page, resources, variables, dpi=None, color_space=None, bit_depth=None, show_transparency_checker=True) -> 'Image.Image'
```

Render a page to an RGBA image.

``show_transparency_checker`` controls whether transparent or
partially-transparent page backgrounds are filled with a checkerboard
pattern. Default True (user-facing render — Photoshop-like). Set to
False when rendering pages that will be composited into a larger
canvas (embedded sub-document, export with real alpha).


---

### `render_document`

```python
render_document(doc, dpi=None, color_space=None, bit_depth=None)
```


---


## Bitmap export

### `export_page_bitmap`

```python
export_page_bitmap(doc: "'Document'", page_index: 'int' = 0, path: 'str' = 'output.png', dpi: 'Optional[int]' = None, color_space: 'Optional[str]' = None, bit_depth: 'Optional[int]' = None, format: 'str' = 'PNG', jpeg_quality: 'int' = 95) -> 'None'
```

Render one page and save it to a file.


---

### `export_all_pages`

```python
export_all_pages(doc: "'Document'", path_pattern: 'str' = 'page_{n}.png', dpi: 'Optional[int]' = None, color_space: 'Optional[str]' = None, bit_depth: 'Optional[int]' = None, format: 'str' = 'PNG', jpeg_quality: 'int' = 95) -> 'List[str]'
```

Render every page.
``path_pattern`` may contain ``{n}`` (0-based index) and ``{page}`` (1-based).
Returns list of written paths.


---

### `export_to_bytes`

```python
export_to_bytes(doc: "'Document'", page_index: 'int' = 0, format: 'str' = 'PNG', dpi: 'Optional[int]' = None, color_space: 'Optional[str]' = None, bit_depth: 'Optional[int]' = None, jpeg_quality: 'int' = 95) -> 'bytes'
```

Render one page and return raw image bytes.


---


## Geometry helpers

### `to_mm`

```python
to_mm(value: 'float', unit: 'str' = 'mm') -> 'float'
```


---

### `from_mm`

```python
from_mm(value: 'float', unit: 'str' = 'mm') -> 'float'
```


---

### `mm_to_px`

```python
mm_to_px(mm: 'float', dpi: 'float') -> 'float'
```


---


## Colour

### `as_color`

```python
as_color(value) -> 'Color'
```

Accept hex string, tuple, or list → normalised Color tuple.


---


## Text metrics

### `measure_text_height`

```python
measure_text_height(text: 'str', style: 'TextStyle', width_mm: 'float', dpi: 'float' = 96, font_data: 'Optional[bytes]' = None) -> 'float'
```

Height in mm needed to render text at given style inside width_mm.


---


## Classes


## Document model

### `Document`

```python
Document(width: 'float' = 210.0, height: 'float' = 297.0, dpi: 'int' = 300, color_space: 'str' = 'RGB', bit_depth: 'int' = 8, title: 'str' = '', author: 'str' = '', description: 'str' = '') -> 'None'
```

Root object for an EDOF document.

Usage::

    doc = edof.Document(width=210, height=297)
    page = doc.add_page()
    tb = page.add_textbox(10, 10, 100, 20, "Hello!")
    doc.save("hello.edof")


**Methods**


#### `Document.add_page(self, width: 'Optional[float]' = None, height: 'Optional[float]' = None, dpi: 'Optional[int]' = None, color_space: 'Optional[str]' = None, bit_depth: 'Optional[int]' = None, background: 'tuple' = (255, 255, 255)) -> 'Page'`


#### `Document.add_resource(self, data: 'bytes', filename: 'str', mime_type: 'str' = 'application/octet-stream') -> 'str'`


#### `Document.add_resource_from_file(self, path: 'str') -> 'str'`


#### `Document.can(self, required) -> 'bool'`

Test whether the current session has at least the required permission.


#### `Document.change_password(self, level: 'str', old_password: 'str', new_password: 'str') -> 'None'`

Rotate a password. Knowing the old password is sufficient.


#### `Document.clear_all_protection(self) -> 'None'`

Remove all encryption and passwords. Requires ADMIN permission.


#### `Document.clear_errors(self) -> 'None'`


#### `Document.consume_recovery_key(self) -> 'Optional[str]'`

Get and clear the pending recovery key.


#### `Document.define_variable(self, name: 'str', **kwargs) -> 'None'`


#### `Document.duplicate_page(self, index: 'int') -> 'Page'`


#### `Document.export_3x(self, path: 'str') -> 'None'`

Save a downgraded copy of the document as a v3.x .edof file.

Best-effort lossy conversion:
  - Tables → Groups of TextBoxes + line shapes
  - TextBox.runs[] → flattened to plain text (formatting lost)
  - Path shapes → polygon shapes (Beziers sampled)
  - Gradients → average color of stops
  - visible_if → evaluated and baked into .visible
  - blend_mode → reset to 'normal'

The output can be opened by edof 3.x. Use this when you need to
share an EDOF document with someone running the older library.
The original (in-memory) document is not modified.


#### `Document.export_all_pages(self, path_pattern: 'str' = 'page_{n}.png', dpi: 'Optional[int]' = None, color_space: 'Optional[str]' = None, bit_depth: 'Optional[int]' = None, format: 'str' = 'PNG', jpeg_quality: 'int' = 95) -> 'List[str]'`

Export every page to a separate file.

path_pattern can contain {n} (0-based) and {page} (1-based). E.g.
"out/page_{n}.png" or "doc-page-{page}.jpg".

Returns list of written file paths.


#### `Document.export_bitmap(self, path: 'str', page: 'int' = 0, dpi: 'Optional[int]' = None, color_space: 'Optional[str]' = None, bit_depth: 'Optional[int]' = None, format: 'str' = 'PNG') -> 'None'`


#### `Document.export_pdf(self, path: 'str', vector: 'bool' = True, dpi: 'Optional[int]' = None) -> 'None'`

Export to PDF.

vector=True (default) uses the built-in pure-Python vector PDF writer
(searchable text, small files, no reportlab dependency).
vector=False falls back to raster mode via reportlab.


#### `Document.export_rtf(self, path: 'str') -> 'None'`

Export the document as RTF (Rich Text Format).

Best-effort, paragraph-by-paragraph conversion. Each TextBox becomes
a paragraph; runs preserve bold/italic/underline/size/color.
Tables, images, shapes, and complex layout are NOT exported.

Use this for round-tripping with Word and other RTF editors when the
content is primarily text.


#### `Document.export_svg(self, path: 'str', page: 'int' = 0) -> 'None'`

Export a single page as SVG.


#### `Document.fill_variables(self, mapping: 'Dict[str, Any]') -> 'None'`

Batch fill – ``doc.fill_variables({"name": "Jan", "date": "2025"})``


#### `Document.from_dict(d: 'dict', resource_data: 'Dict[str, bytes]' = None) -> "'Document'"`


#### `Document.get_page(self, index: 'int') -> 'Page'`


#### `Document.load(path: 'str', password: 'str' = None, recovery_key: 'str' = None) -> "'Document'"`


#### `Document.lock(self) -> 'None'`

Forget the cached content key for this session.


#### `Document.move_page(self, from_index: 'int', to_index: 'int') -> 'None'`


#### `Document.print_document(self, printer: 'Optional[str]' = None, pages: 'Optional[List[int]]' = None) -> 'None'`


#### `Document.remove_page(self, index: 'int') -> 'None'`


#### `Document.remove_password(self, level: 'str') -> 'None'`

Remove a password slot. Requires ADMIN permission.


#### `Document.require(self, required) -> 'None'`

Raise PermissionError if the current session lacks the permission.


#### `Document.save(self, path: 'str') -> 'None'`


#### `Document.set_password(self, level: 'str', password: 'str') -> 'Optional[str]'`

Set or replace the password for a permission level.

level: 'fill' | 'edit' | 'design' | 'admin'

Returns a recovery key string if this is the first password being set
on the document; otherwise None. **Save the recovery key immediately
and securely** — it cannot be retrieved later if you lose all passwords.

After this call the document switches to encryption_mode='full'.
Use doc.encryption_mode = 'partial' if you want partial encryption.

Multi-level usage:
    rk = doc.set_password('admin',  'master')   # returns recovery key
    doc.set_password('fill',   'klienti')        # returns None
    doc.set_password('edit',   'korektura')      # returns None


#### `Document.set_variable(self, name: 'str', value: 'Any') -> 'None'`


#### `Document.to_dict(self) -> 'dict'`


#### `Document.unlock(self, password: 'str' = None, recovery_key: 'str' = None) -> "'Permission'"`

Unlock an encrypted document with a password or recovery key.

Returns the granted Permission. Raises EdofWrongPassword on failure.


#### `Document.validate(self) -> 'List[str]'`

Return list of validation issues (empty = valid).


---

### `Page`

```python
Page(id: 'str' = <factory>, index: 'int' = 0, width: 'float' = 210.0, height: 'float' = 297.0, dpi: 'int' = 300, color_space: 'str' = 'RGB', bit_depth: 'int' = 8, background: 'tuple' = (255, 255, 255), objects: 'List[EdofObject]' = <factory>) -> None
```

A single page in an EDOF document.


**Methods**


#### `Page.add_card(self, x: 'float', y: 'float', w: 'float', h: 'float', title: 'str' = '', body: 'str' = '', accent_color: 'tuple' = (83, 74, 183, 255), bg_color: 'tuple' = (255, 255, 255, 255), border_color: 'tuple' = (220, 220, 230, 255), title_font_size: 'float' = 4.939, body_font_size: 'float' = 3.528, unit: 'str' = 'mm') -> 'Group'`

Card widget: rounded background + accent header + title + body text.


#### `Page.add_group(self) -> 'Group'`


#### `Page.add_image(self, resource_id: 'str', x: 'float' = 0, y: 'float' = 0, width: 'float' = 50, height: 'float' = 50, unit: 'str' = 'mm', fit_mode: 'str' = 'contain') -> 'ImageBox'`


#### `Page.add_kv_list(self, x: 'float', y: 'float', w: 'float', items: 'list', row_height: 'float' = 7.0, key_width_frac: 'float' = 0.4, key_color: 'tuple' = (100, 100, 130), value_color: 'tuple' = (20, 20, 40), font_size: 'float' = 3.175, unit: 'str' = 'mm') -> 'Group'`

Key-value definition list widget.


#### `Page.add_metric(self, x: 'float', y: 'float', w: 'float', h: 'float', label: 'str' = 'Metric', value: 'str' = '0', subtitle: 'str' = '', value_color: 'tuple' = (83, 74, 183, 255), unit: 'str' = 'mm') -> 'Group'`

Metric widget: large value + label + optional subtitle.


#### `Page.add_object(self, obj: 'EdofObject') -> 'EdofObject'`


#### `Page.add_qrcode(self, data: 'str', x: 'float' = 0, y: 'float' = 0, size: 'float' = 30, unit: 'str' = 'mm', error_correction: 'str' = 'M') -> 'QRCode'`


#### `Page.add_shape(self, shape_type: 'str' = 'rect', x: 'float' = 0, y: 'float' = 0, width: 'float' = 50, height: 'float' = 30, unit: 'str' = 'mm') -> 'Shape'`


#### `Page.add_table(self, x: 'float', y: 'float', w: 'float', rows: 'list', header: 'bool' = True, row_height: 'float' = 8.0, alternating: 'bool' = True, header_color: 'tuple' = (83, 74, 183, 255), alt_color: 'tuple' = (245, 245, 252, 255), border_color: 'tuple' = (200, 200, 215, 255), font_size: 'float' = 3.175, unit: 'str' = 'mm') -> 'Group'`

Simple table widget.


#### `Page.add_textbox(self, x: 'float' = 0, y: 'float' = 0, width: 'float' = 80, height: 'float' = 20, text: 'str' = '', unit: 'str' = 'mm', **style_kwargs) -> 'TextBox'`


#### `Page.add_textbox_auto(self, x: 'float', y: 'float', w: 'float', text: 'str' = '', min_height: 'float' = 6.0, unit: 'str' = 'mm', **style_kwargs) -> 'TextBox'`

Add a TextBox whose height is computed automatically from the text content.
Returns the TextBox; its transform.height is set to the measured value.
The caller can read tb.transform.y + tb.transform.height to get next_y.


#### `Page.column(self, x: 'float', gap: 'float' = 2.0, width: 'float' = 40.0, unit: 'str' = 'mm') -> "'_ColumnContext'"`

Return a column layout context that auto-positions objects top-to-bottom.


#### `Page.duplicate(self) -> "'Page'"`


#### `Page.from_dict(d: 'dict') -> "'Page'"`


#### `Page.get_by_name(self, name: 'str') -> 'List[EdofObject]'`


#### `Page.get_by_tag(self, tag: 'str') -> 'List[EdofObject]'`


#### `Page.get_object(self, obj_id: 'str') -> 'Optional[EdofObject]'`


#### `Page.remove_object(self, obj_id: 'str') -> 'bool'`


#### `Page.repeat_objects(self, template_objs, data_list, gap: 'float' = 2.0, y_start: 'Optional[float]' = None, y_end: 'Optional[float]' = None, new_page_callback=None) -> "List['Page']"`

Duplicate template objects for each row in data_list.

For each row in data_list (a list of dicts), the template_objs are
deep-copied, their {column_name} placeholders in text/runs are
substituted with row values, and the copies are translated downward
by (block_height + gap).

When the bottom of the next block would exceed y_end (defaults to
page.height - 10mm), a new page is created (sharing the same width,
height, dpi, color_space, bit_depth) and content continues there.

new_page_callback(new_page) lets the caller add headers/footers to
each generated page.

Returns the list of pages created (the original page is index 0;
any additional pages are appended).


#### `Page.row(self, y: 'float', gap: 'float' = 2.0, height: 'float' = 10.0, unit: 'str' = 'mm') -> "'_RowContext'"`

Return a row layout context that auto-positions objects left-to-right.


#### `Page.sorted_objects(self) -> 'List[EdofObject]'`

Return objects sorted by layer (ascending = bottom to top).


#### `Page.to_dict(self) -> 'dict'`


---

### `ResourceStore`

```python
ResourceStore() -> 'None'
```

Holds all embedded resources (fonts, images, …) for a Document.


**Methods**


#### `ResourceStore.add(self, data: 'bytes', filename: 'str', mime_type: 'str' = 'application/octet-stream', metadata: 'Optional[Dict]' = None) -> 'str'`

Add raw bytes, return the new resource_id.


#### `ResourceStore.add_from_file(self, path: 'str', mime_type: 'Optional[str]' = None) -> 'str'`

Add a file from disk, return the new resource_id.


#### `ResourceStore.all_entries(self) -> 'Iterator[ResourceEntry]'`


#### `ResourceStore.from_index(index: 'dict', data_lookup: 'Dict[str, bytes]') -> "'ResourceStore'"`


#### `ResourceStore.get(self, resource_id: 'str') -> 'Optional[ResourceEntry]'`


#### `ResourceStore.index_dict(self) -> 'dict'`

Serialise metadata index (not the raw bytes).


#### `ResourceStore.remove(self, resource_id: 'str') -> 'bool'`


---


## Objects

### `EdofObject`

```python
EdofObject(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False) -> None
```

EdofObject(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False)


**Methods**


#### `EdofObject.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `EdofObject.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `EdofObject.copy(self) -> "'EdofObject'"`


#### `EdofObject.flip_h(self) -> "'EdofObject'"`


#### `EdofObject.flip_v(self) -> "'EdofObject'"`


#### `EdofObject.from_dict(d: 'dict') -> "'EdofObject'"`


#### `EdofObject.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `EdofObject.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `EdofObject.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `EdofObject.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `EdofObject.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `EdofObject.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `EdofObject.to_dict(self) -> 'dict'`


---

### `TextBox`

```python
TextBox(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, text: 'str' = '', style: 'TextStyle' = <factory>, runs: "List['TextRun']" = <factory>, padding: 'float' = 2.0, padding_left: 'Optional[float]' = None, padding_right: 'Optional[float]' = None, padding_top: 'Optional[float]' = None, padding_bot: 'Optional[float]' = None, border: 'Optional[StrokeStyle]' = None, fill: 'FillStyle' = <factory>, paragraph_alignments: 'Dict[str, str]' = <factory>) -> None
```

TextBox(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, text: 'str' = '', style: 'TextStyle' = <factory>, runs: "List['TextRun']" = <factory>, padding: 'float' = 2.0, padding_left: 'Optional[float]' = None, padding_right: 'Optional[float]' = None, padding_top: 'Optional[float]' = None, padding_bot: 'Optional[float]' = None, border: 'Optional[StrokeStyle]' = None, fill: 'FillStyle' = <factory>, paragraph_alignments: 'Dict[str, str]' = <factory>)


**Methods**


#### `TextBox.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `TextBox.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `TextBox.copy(self) -> "'EdofObject'"`


#### `TextBox.flip_h(self) -> "'EdofObject'"`


#### `TextBox.flip_v(self) -> "'EdofObject'"`


#### `TextBox.from_dict(d: 'dict') -> "'EdofObject'"`


#### `TextBox.get_resolved_text(self, var_store=None) -> 'str'`

Return text after variable substitution.

Two substitution mechanisms:
  1. If `obj.variable` is set, the value of that variable replaces the text entirely.
  2. Otherwise, `{name}` placeholders inside `obj.text` are substituted with
     corresponding variable values.

bug fix — placeholder substitution now actually happens at render time.
Previously {name} placeholders were only resolved by repeat_objects(), but
plain rendering left them as literals.


#### `TextBox.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `TextBox.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `TextBox.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `TextBox.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `TextBox.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `TextBox.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `TextBox.to_dict(self) -> 'dict'`


---

### `ImageBox`

```python
ImageBox(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, resource_id: 'Optional[str]' = None, fit_mode: 'str' = 'stretch', border: 'Optional[StrokeStyle]' = None, corner_radius: 'float' = 0.0) -> None
```

ImageBox(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, resource_id: 'Optional[str]' = None, fit_mode: 'str' = 'stretch', border: 'Optional[StrokeStyle]' = None, corner_radius: 'float' = 0.0)


**Methods**


#### `ImageBox.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `ImageBox.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `ImageBox.copy(self) -> "'EdofObject'"`


#### `ImageBox.flip_h(self) -> "'EdofObject'"`


#### `ImageBox.flip_v(self) -> "'EdofObject'"`


#### `ImageBox.from_dict(d: 'dict') -> "'EdofObject'"`


#### `ImageBox.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `ImageBox.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `ImageBox.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `ImageBox.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `ImageBox.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `ImageBox.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `ImageBox.to_dict(self) -> 'dict'`


---

### `Shape`

```python
Shape(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, shape_type: 'str' = 'rect', fill: 'FillStyle' = <factory>, stroke: 'StrokeStyle' = <factory>, corner_radius: 'float' = 0.0, points: 'List[Any]' = <factory>, path_data: 'List[Any]' = <factory>, path_point_types: 'List[str]' = <factory>) -> None
```

Shape(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, shape_type: 'str' = 'rect', fill: 'FillStyle' = <factory>, stroke: 'StrokeStyle' = <factory>, corner_radius: 'float' = 0.0, points: 'List[Any]' = <factory>, path_data: 'List[Any]' = <factory>, path_point_types: 'List[str]' = <factory>)


**Methods**


#### `Shape.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `Shape.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `Shape.copy(self) -> "'EdofObject'"`


#### `Shape.flip_h(self) -> "'EdofObject'"`


#### `Shape.flip_v(self) -> "'EdofObject'"`


#### `Shape.from_dict(d: 'dict') -> "'EdofObject'"`


#### `Shape.from_svg_path(d_attr: 'str') -> "'Shape'"`

Create a Shape with shape_type='path' from an SVG path 'd' string.

Supports M, L, H, V, C, Q, Z (absolute and relative).
Coordinates are in mm, relative to the shape's transform origin.


#### `Shape.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `Shape.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `Shape.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `Shape.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `Shape.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `Shape.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `Shape.to_dict(self) -> 'dict'`


#### `Shape.to_svg_path_d(self) -> 'str'`

Serialize self.path_data back to SVG 'd' attribute string.
Uses absolute coordinates only.


---

### `QRCode`

```python
QRCode(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, data: 'str' = '', error_correction: 'str' = 'M', border_modules: 'int' = 4, fg_color: 'tuple' = (0, 0, 0), bg_color: 'tuple' = (255, 255, 255)) -> None
```

QRCode(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, data: 'str' = '', error_correction: 'str' = 'M', border_modules: 'int' = 4, fg_color: 'tuple' = (0, 0, 0), bg_color: 'tuple' = (255, 255, 255))


**Methods**


#### `QRCode.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `QRCode.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `QRCode.copy(self) -> "'EdofObject'"`


#### `QRCode.flip_h(self) -> "'EdofObject'"`


#### `QRCode.flip_v(self) -> "'EdofObject'"`


#### `QRCode.from_dict(d: 'dict') -> "'EdofObject'"`


#### `QRCode.get_resolved_data(self, var_store=None) -> 'str'`


#### `QRCode.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `QRCode.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `QRCode.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `QRCode.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `QRCode.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `QRCode.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `QRCode.to_dict(self) -> 'dict'`


---

### `Group`

```python
Group(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, children: 'List[EdofObject]' = <factory>) -> None
```

Group(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, children: 'List[EdofObject]' = <factory>)


**Methods**


#### `Group.add(self, obj: 'EdofObject') -> 'EdofObject'`


#### `Group.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `Group.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `Group.copy(self) -> "'EdofObject'"`


#### `Group.flatten(self) -> 'List[EdofObject]'`


#### `Group.flip_h(self) -> "'EdofObject'"`


#### `Group.flip_v(self) -> "'EdofObject'"`


#### `Group.from_dict(d: 'dict') -> "'EdofObject'"`


#### `Group.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `Group.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `Group.remove_by_id(self, obj_id: 'str') -> 'bool'`


#### `Group.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `Group.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `Group.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `Group.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `Group.to_dict(self) -> 'dict'`


---

### `Table`

> **Experimental / TBD.** This is a work in progress and not yet complete. The API and behaviour may change; avoid relying on it in production.

```python
Table(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, cells: 'List[List[Any]]' = <factory>, row_heights: 'List[float]' = <factory>, col_widths: 'List[float]' = <factory>, table_border: 'Optional[StrokeStyle]' = None) -> None
```

Formatted table with per-cell styling.

cells is a 2D grid: cells[row_index][col_index].
Set row_heights or col_widths to 0 to auto-distribute.


**Methods**


#### `Table.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `Table.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `Table.copy(self) -> "'EdofObject'"`


#### `Table.flip_h(self) -> "'EdofObject'"`


#### `Table.flip_v(self) -> "'EdofObject'"`


#### `Table.from_dict(d: 'dict') -> "'EdofObject'"`


#### `Table.get_cell(self, row: 'int', col: 'int') -> 'Optional[TableCell]'`


#### `Table.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `Table.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `Table.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `Table.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `Table.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `Table.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `Table.set_cell(self, row: 'int', col: 'int', cell: 'TableCell') -> 'None'`


#### `Table.to_dict(self) -> 'dict'`


---

### `TableCell`

> **Experimental / TBD.** This is a work in progress and not yet complete. The API and behaviour may change; avoid relying on it in production.

```python
TableCell(text: 'str' = '', runs: 'List[Any]' = <factory>, style: 'TextStyle' = <factory>, bg_color: 'tuple' = (255, 255, 255, 0), padding: 'float' = 1.5, border_top: 'CellBorder' = <factory>, border_right: 'CellBorder' = <factory>, border_bottom: 'CellBorder' = <factory>, border_left: 'CellBorder' = <factory>, colspan: 'int' = 1, rowspan: 'int' = 1) -> None
```

A single cell in a Table. Supports rich text via runs.


**Methods**


#### `TableCell.from_dict(d: 'dict') -> "'TableCell'"`


#### `TableCell.to_dict(self) -> 'dict'`


---

### `CellBorder`

> **Experimental / TBD.** This is a work in progress and not yet complete. The API and behaviour may change; avoid relying on it in production.

```python
CellBorder(color: 'tuple' = (180, 180, 180, 255), width: 'float' = 0.3, enabled: 'bool' = True) -> None
```

Per-side border of a TableCell.


**Methods**


#### `CellBorder.from_dict(d: 'dict') -> "'CellBorder'"`


#### `CellBorder.to_dict(self) -> 'dict'`


---

### `SubDocumentBox`

```python
SubDocumentBox(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, resource_id: 'Optional[str]' = None, source_path: 'Optional[str]' = None, page_index: 'int' = 0, fit_mode: 'str' = 'contain') -> None
```

A box that embeds another EDOF document (or a reference to one).

Two storage modes:
- resource_id: the embedded document is stored in doc.resources[resource_id] as bytes
- source_path: an external path to a .edof file (loaded at render time)

page_index: which page of the sub-document to embed
fit_mode: contain | cover | stretch | none


**Methods**


#### `SubDocumentBox.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `SubDocumentBox.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `SubDocumentBox.copy(self) -> "'EdofObject'"`


#### `SubDocumentBox.flip_h(self) -> "'EdofObject'"`


#### `SubDocumentBox.flip_v(self) -> "'EdofObject'"`


#### `SubDocumentBox.from_dict(d: 'dict') -> "'EdofObject'"`


#### `SubDocumentBox.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `SubDocumentBox.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `SubDocumentBox.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `SubDocumentBox.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `SubDocumentBox.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `SubDocumentBox.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `SubDocumentBox.to_dict(self) -> 'dict'`


---

### `SvgBox`

```python
SvgBox(id: 'str' = <factory>, name: 'str' = '', variable: 'Optional[str]' = None, transform: 'Transform' = <factory>, locked: 'bool' = False, visible: 'bool' = True, layer: 'int' = 0, tags: 'List[str]' = <factory>, shadow: 'ShadowStyle' = <factory>, opacity: 'float' = 1.0, fill_opacity: 'float' = 1.0, effects: "List['LayerEffect']" = <factory>, visible_if: 'str' = '', blend_mode: 'str' = 'normal', lock_level: 'str' = '', lock_text: 'bool' = False, lock_position: 'bool' = False, svg_xml: 'str' = '', fit_mode: 'str' = 'contain', border: 'Optional[StrokeStyle]' = None, corner_radius: 'float' = 0.0) -> None
```

An SVG file embedded as a rastered image. Stores the original
SVG XML inline so loading/saving is lossless. In the editor, double-click
offers to convert to native EDOF path shapes for editing — at that point
the SvgBox is replaced by Shape objects and the SVG is discarded.


**Methods**


#### `SvgBox.can_modify(self, doc) -> 'bool'`

Return True if this object can be modified given doc's current
session permission. Honors per-object lock_level.


#### `SvgBox.can_modify_text(self, doc) -> 'bool'`

Return True if this object's text/runs can be modified.


#### `SvgBox.copy(self) -> "'EdofObject'"`


#### `SvgBox.flip_h(self) -> "'EdofObject'"`


#### `SvgBox.flip_v(self) -> "'EdofObject'"`


#### `SvgBox.from_dict(d: 'dict') -> "'EdofObject'"`


#### `SvgBox.move(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `SvgBox.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'EdofObject'"`


#### `SvgBox.resize(self, w: 'float', h: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'EdofObject'"`


#### `SvgBox.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'EdofObject'"`


#### `SvgBox.rotate(self, angle: 'float') -> "'EdofObject'"`


#### `SvgBox.rotate_to(self, angle: 'float') -> "'EdofObject'"`


#### `SvgBox.to_dict(self) -> 'dict'`


---


## Styles

### `TextStyle`

```python
TextStyle(font_family: 'str' = 'Arial', font_size: 'float' = 4.233, bold: 'bool' = False, italic: 'bool' = False, underline: 'bool' = False, strikethrough: 'bool' = False, color: 'Color' = (0, 0, 0), background: 'Optional[Color]' = None, letter_spacing: 'float' = 0.0, line_height: 'float' = 1.2, alignment: 'str' = 'left', justify_mode: 'str' = 'space', vertical_align: 'str' = 'top', auto_shrink: 'bool' = False, auto_fill: 'bool' = False, min_font_size: 'float' = 1.411, max_font_size: 'float' = 70.555, wrap: 'bool' = True, overflow_hidden: 'bool' = False, padding: 'float' = 1.0, padding_top: 'Optional[float]' = None, padding_right: 'Optional[float]' = None, padding_bottom: 'Optional[float]' = None, padding_left: 'Optional[float]' = None, glyph_scale_x: 'float' = 1.0, glyph_scale_y: 'float' = 1.0) -> None
```

ALL length fields are in millimetres (mm), the canonical
unit of EDOF. Typography users can interact with pt via the
`font_size_pt` / `letter_spacing_pt` accessors below — but on-disk
and in-memory the canonical unit is mm.

Reference: 12 pt ≈ 4.233 mm; 1 pt = 25.4/72 mm.


**Methods**


#### `TextStyle.copy(self) -> "'TextStyle'"`


#### `TextStyle.from_dict(d: 'dict') -> "'TextStyle'"`


#### `TextStyle.get_padding(self)`

Return (top, right, bottom, left) in mm.
Per-side fields override the uniform `padding` if set.


#### `TextStyle.to_dict(self) -> 'dict'`


---

### `TextRun`

```python
TextRun(text: 'str' = '', font_family: 'Optional[str]' = None, font_size: 'Optional[float]' = None, bold: 'Optional[bool]' = None, italic: 'Optional[bool]' = None, underline: 'Optional[bool]' = None, strikethrough: 'Optional[bool]' = None, color: 'Optional[Color]' = None, background: 'Optional[Color]' = None, line_height: 'Optional[float]' = None, letter_spacing: 'Optional[float]' = None, alignment: 'Optional[str]' = None) -> None
```

A styled segment of text within a TextBox.runs list. v4.0 feature.

font_size is in millimetres (mm), the canonical EDOF unit.
Use the `font_size_pt` property for typography-style pt values.

Any field set to None inherits from the parent TextStyle.


**Methods**


#### `TextRun.from_dict(d: 'dict') -> "'TextRun'"`


#### `TextRun.resolve(self, parent: "'TextStyle'", scale: 'float' = 1.0) -> 'dict'`

Return effective style dict for rendering this run.
scale multiplies font_size for auto-shrink/fill.


#### `TextRun.to_dict(self) -> 'dict'`


---

### `StrokeStyle`

```python
StrokeStyle(color: 'Color' = (0, 0, 0), width: 'float' = 0.353, dash: 'list' = <factory>, cap: 'str' = 'butt', join: 'str' = 'miter') -> None
```

width is in millimetres (mm), canonical EDOF unit.
Use `width_pt` property for typography pt access (1 pt ≈ 0.353 mm).


**Methods**


#### `StrokeStyle.from_dict(d: 'dict') -> "'StrokeStyle'"`


#### `StrokeStyle.to_dict(self) -> 'dict'`


---

### `FillStyle`

```python
FillStyle(color: 'Optional[Color]' = (255, 255, 255), opacity: 'float' = 1.0, gradient: 'Optional[Gradient]' = None) -> None
```

FillStyle(color: 'Optional[Color]' = (255, 255, 255), opacity: 'float' = 1.0, gradient: 'Optional[Gradient]' = None)


**Methods**


#### `FillStyle.from_dict(d: 'dict') -> "'FillStyle'"`


#### `FillStyle.to_dict(self) -> 'dict'`


---

### `ShadowStyle`

```python
ShadowStyle(enabled: 'bool' = False, color: 'Color' = (0, 0, 0, 128), offset_x: 'float' = 2.0, offset_y: 'float' = 2.0, blur: 'float' = 4.0) -> None
```

ShadowStyle(enabled: 'bool' = False, color: 'Color' = (0, 0, 0, 128), offset_x: 'float' = 2.0, offset_y: 'float' = 2.0, blur: 'float' = 4.0)


**Methods**


#### `ShadowStyle.from_dict(d: 'dict') -> "'ShadowStyle'"`


#### `ShadowStyle.to_dict(self) -> 'dict'`


---

### `Gradient`

```python
Gradient(type: 'str' = 'linear', angle: 'float' = 0.0, center: 'tuple' = (0.5, 0.5), radius: 'float' = 0.5, stops: 'list' = <factory>) -> None
```

Multi-stop gradient for FillStyle. v4.0 feature.


**Methods**


#### `Gradient.from_dict(d: 'dict') -> "'Gradient'"`


#### `Gradient.to_dict(self) -> 'dict'`


---

### `LayerEffect`

```python
LayerEffect(type: 'str' = 'drop_shadow', enabled: 'bool' = True, color: 'Color' = (0, 0, 0, 200), color2: 'Color' = (255, 255, 255, 200), blend_mode: 'str' = 'normal', blend_mode2: 'str' = 'normal', opacity: 'float' = 1.0, size: 'float' = 2.0, distance: 'float' = 2.0, direction: 'float' = 135.0, stroke_position: 'str' = 'outside', bevel_kind: 'str' = 'outer', gradient_start: 'Color' = (0, 0, 0, 255), gradient_end: 'Color' = (255, 255, 255, 255), gradient_angle: 'float' = 90.0, texture_path: 'Optional[str]' = None, texture_scale: 'float' = 100.0, texture_data: 'Optional[bytes]' = None, texture_fit: 'str' = 'tile', texture_anchor: 'str' = 'top-left') -> None
```

A Photoshop-style layer effect.

type: one of 'drop_shadow', 'inner_shadow', 'outer_glow', 'inner_glow',
             'bevel', 'stroke', 'color_overlay', 'gradient_overlay'


**Methods**


#### `LayerEffect.from_dict(d: 'dict') -> "'LayerEffect'"`


#### `LayerEffect.to_dict(self) -> 'dict'`


---


## Variables

### `VariableStore`

```python
VariableStore() -> 'None'
```

Holds all VariableDefs and their current values for one Document.


**Methods**


#### `VariableStore.all_values(self) -> 'Dict[str, Any]'`


#### `VariableStore.define(self, name: 'str', type: 'str' = 'text', default: 'Any' = '', description: 'str' = '', required: 'bool' = False, choices=None) -> 'VariableDef'`


#### `VariableStore.fill(self, mapping: 'Dict[str, Any]') -> 'None'`

Batch fill – set multiple variables at once.


#### `VariableStore.from_dict(d: 'dict') -> "'VariableStore'"`


#### `VariableStore.get(self, name: 'str', fallback: 'Any' = None) -> 'Any'`


#### `VariableStore.get_def(self, name: 'str') -> 'Optional[VariableDef]'`


#### `VariableStore.missing_required(self) -> 'List[str]'`


#### `VariableStore.names(self) -> 'List[str]'`


#### `VariableStore.reset_all(self) -> 'None'`


#### `VariableStore.set(self, name: 'str', value: 'Any') -> 'None'`


#### `VariableStore.to_dict(self) -> 'dict'`


#### `VariableStore.undefine(self, name: 'str') -> 'None'`


---

### `VariableDef`

```python
VariableDef(name: 'str', type: 'str' = 'text', default: 'Any' = '', description: 'str' = '', required: 'bool' = False, choices: 'Optional[List]' = None) -> None
```

VariableDef(name: 'str', type: 'str' = 'text', default: 'Any' = '', description: 'str' = '', required: 'bool' = False, choices: 'Optional[List]' = None)


**Methods**


#### `VariableDef.from_dict(d: 'dict') -> "'VariableDef'"`


#### `VariableDef.to_dict(self) -> 'dict'`


#### `VariableDef.validate(self, value: 'Any') -> 'bool'`


---


## Serialization

### `EdofSerializer`

```python
EdofSerializer()
```


**Methods**


#### `EdofSerializer.from_bytes(data: 'bytes', password: 'Optional[str]' = None, recovery_key: 'Optional[str]' = None) -> "'Document'"`


#### `EdofSerializer.load(path: 'str', password: 'Optional[str]' = None, recovery_key: 'Optional[str]' = None) -> "'Document'"`


#### `EdofSerializer.peek(path: 'str') -> 'dict'`

Return the manifest without loading or decrypting the document.


#### `EdofSerializer.read_preview(path: 'str') -> 'Optional[bytes]'`

Return PNG thumbnail bytes embedded in an .edof file, or
None if no preview is present (older files / encrypted full mode).


#### `EdofSerializer.save(doc: "'Document'", path: 'str') -> 'None'`


#### `EdofSerializer.to_bytes(doc: "'Document'") -> 'bytes'`


---


## Geometry

### `Transform`

```python
Transform(x: 'float' = 0.0, y: 'float' = 0.0, width: 'float' = 50.0, height: 'float' = 30.0, rotation: 'float' = 0.0, flip_h: 'bool' = False, flip_v: 'bool' = False) -> None
```

Represents the full spatial state of a document object.

``x``, ``y``  – top-left corner position in mm (before rotation)
``width``      – mm
``height``     – mm
``rotation``   – clockwise degrees around the bounding-box centre
``flip_h``     – horizontal flip (applied before rotation)
``flip_v``     – vertical flip (applied before rotation)


**Methods**


#### `Transform.center_on(self, cx: 'float', cy: 'float', unit: 'str' = 'mm') -> "'Transform'"`

Position so the object's centre is at (cx, cy).


#### `Transform.copy(self) -> "'Transform'"`


#### `Transform.flip_horizontal(self) -> "'Transform'"`


#### `Transform.flip_vertical(self) -> "'Transform'"`


#### `Transform.from_dict(d: 'dict') -> "'Transform'"`


#### `Transform.move_to(self, x: 'float', y: 'float', unit: 'str' = 'mm') -> "'Transform'"`


#### `Transform.resize_free(self, new_width: 'float', new_height: 'float', unit: 'str' = 'mm', anchor: 'str' = 'top-left') -> "'Transform'"`

Set absolute width and height; anchor = 'top-left' | 'center'.


#### `Transform.resize_to_fit(self, max_w: 'float', max_h: 'float', unit: 'str' = 'mm') -> "'Transform'"`

Uniformly scale so the object fits within (max_w × max_h).


#### `Transform.resize_uniform(self, factor: 'float', anchor: 'str' = 'center') -> "'Transform'"`

Scale width and height by the same factor.


#### `Transform.rotate(self, angle_deg: 'float') -> "'Transform'"`

Add angle_deg (clockwise) to current rotation.


#### `Transform.rotate_around(self, pivot_x: 'float', pivot_y: 'float', angle_deg: 'float', unit: 'str' = 'mm') -> "'Transform'"`

Rotate the entire object around an arbitrary point.


#### `Transform.rotate_to(self, angle_deg: 'float') -> "'Transform'"`

Set absolute rotation.


#### `Transform.set_height_keep_ratio(self, new_height: 'float', unit: 'str' = 'mm') -> "'Transform'"`


#### `Transform.set_width_keep_ratio(self, new_width: 'float', unit: 'str' = 'mm') -> "'Transform'"`


#### `Transform.to_dict(self) -> 'dict'`


#### `Transform.translate(self, dx: 'float', dy: 'float', unit: 'str' = 'mm') -> "'Transform'"`


---


## Exceptions & warnings

### `EdofError`

Base exception – catch this to handle any edof error.


---

### `EdofVersionError`

File format version is completely incompatible with this library.


---

### `EdofResourceError`

A resource (font, image, …) cannot be found or loaded.


---

### `EdofRenderError`

Error during rendering or export.


---

### `EdofVariableError`

Variable undefined, wrong type, or invalid value.


---

### `EdofAPIError`

Invalid API command name or parameters.


---

### `EdofValidationError`

Document or object fails structural validation.


---

### `EdofPrintError`

Printing failed or no printer available.


---

### `EdofNewerVersionWarning`

File was saved by a newer version of edof.
The document may render incorrectly; update the library.


---

### `EdofMissingOptionalWarning`

An optional feature (PDF export, QR, PyQt6) is unavailable.


---

### `EdofMissingFontWarning`

Emitted when a requested font family is not found on this system
and a fallback font is used instead.


---

## Constants


**Shape kinds**


| Name | Value |
|------|-------|

| `SHAPE_RECT` | `'rect'` |

| `SHAPE_ELLIPSE` | `'ellipse'` |

| `SHAPE_LINE` | `'line'` |

| `SHAPE_POLYGON` | `'polygon'` |

| `SHAPE_ARROW` | `'arrow'` |

| `SHAPE_PATH` | `'path'` |


**Variable kinds**


| Name | Value |
|------|-------|

| `VAR_TEXT` | `'text'` |

| `VAR_IMAGE` | `'image'` |

| `VAR_NUMBER` | `'number'` |

| `VAR_DATE` | `'date'` |

| `VAR_BOOL` | `'bool'` |

| `VAR_QR` | `'qr'` |

| `VAR_URL` | `'url'` |


**Colour spaces**


| Name | Value |
|------|-------|

| `CS_RGB` | `'RGB'` |

| `CS_RGBA` | `'RGBA'` |

| `CS_GRAY` | `'L'` |

| `CS_BW` | `'1'` |

| `CS_CMYK` | `'CMYK'` |


**Bit depths**


| Name | Value |
|------|-------|

| `BD_8` | `8` |

| `BD_16` | `16` |


**Version**


| Name | Value |
|------|-------|

| `__version__` | `'4.2.4'` |

| `FORMAT_VERSION_STR` | `'4.2.0'` |


---

