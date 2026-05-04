# Reference: Document & Page

## Module-level functions

### `edof.new(width=210.0, height=297.0, title="", author="", description="") → Document`

Create a new empty `Document` with one default A4 page.

**Parameters:**
- `width` — page width in mm (default: 210, A4 portrait)
- `height` — page height in mm (default: 297, A4 portrait)
- `title` — document title (saved to manifest, shown in editor)
- `author` — author name
- `description` — short description

```python
doc = edof.new(width=210, height=297, title="My Document", author="Jan Novák")
```

The document starts with one blank page already added. To start with no pages, do `doc.pages.clear()` after creation.

---

### `edof.load(path, password=None, recovery_key=None) → Document`

Load an `.edof` file. Auto-detects:
- Plain EDOF 4 archives (loaded as-is)
- Encrypted EDOF 4 archives (requires `password` or `recovery_key`)
- Legacy EDOF 2 archives (auto-migrated; result cannot be saved back to v2)
- Legacy EDOF 3 archives (loaded normally; v3 features mapped where possible)

**Parameters:**
- `path` — path to `.edof` file
- `password` — password for encrypted documents (try this first)
- `recovery_key` — 24-character recovery key, used as fallback

**Returns:** `Document`

**Raises:**
- `EdofPasswordRequired` — file is encrypted but no password supplied
- `EdofWrongPassword` — wrong password / recovery key
- `EdofVersionError` — file is too new to read or corrupt

```python
doc = edof.load("template.edof")                       # plain
doc = edof.load("secret.edof", password="myPass")
doc = edof.load("secret.edof", recovery_key="ABCD-EFGH-...")
```

For encrypted documents, `doc.permission_level` after loading reflects the level granted by the password used.

---

## Class: `Document`

The root container. Holds pages, variables, embedded resources, and protection state.

### Attributes

- `id: str` — UUID, generated automatically
- `title: str`
- `author: str`
- `description: str`
- `pages: list[Page]` — direct list, can be manipulated
- `variables: VariableStore` — variable definitions and values
- `resources: ResourceStore` — embedded binary resources (images, fonts)
- `errors: list[str]` — non-fatal warnings from load/migration; read-only

### Persistence

#### `doc.save(path)`

Save to an `.edof` file. The file is a ZIP archive; if encryption is enabled, the structure depends on `encryption_mode`. See [advanced/file-format.md](../advanced/file-format.md).

```python
doc.save("output.edof")
```

#### `doc.to_dict() → dict`

Return a JSON-serializable dictionary of the document. Used internally by the serializer; useful for inspection or custom serialization.

#### `Document.from_dict(d, resources=None) → Document` (classmethod)

Reconstruct a document from a dictionary, optionally with a `{resource_id: bytes}` map.

#### `Document.load(path, password=None, recovery_key=None) → Document` (classmethod)

Same as `edof.load()`. Both call the underlying `EdofSerializer.load()`.

### Pages

#### `doc.add_page(width=None, height=None, dpi=300) → Page`

Append a new page. If `width` and `height` are omitted, the new page inherits the size of the last page (or the document defaults if there are no pages yet).

```python
page = doc.add_page(width=148, height=210, dpi=300)   # A5 page
```

#### `doc.get_page(index) → Page`

Get a page by 0-based index. Raises `IndexError` if out of range.

#### `doc.remove_page(index)`

Remove a page by index.

#### `doc.duplicate_page(index) → Page`

Insert a deep copy of the page at `index` immediately after it. Returns the new page.

#### `doc.move_page(from_index, to_index)`

Move a page within the document.

### Variables

See [reference/04-variables.md](04-variables.md) for the variable system in depth.

#### `doc.define_variable(name, type="text", default=None, required=False, label="", help="", choices=None, max_length=None)`

Declare a variable.

#### `doc.set_variable(name, value)`

Set a variable's current value.

#### `doc.fill_variables(values: dict)`

Set multiple variables at once.

### Resources

#### `doc.add_resource(data: bytes, filename: str, mime_type: str) → str`

Add a binary resource. Returns the new resource ID.

```python
with open("logo.png", "rb") as f:
    img_id = doc.add_resource(f.read(), "logo.png", "image/png")
```

#### `doc.add_resource_from_file(path) → str`

Convenience: load a file from disk and add it. Auto-detects MIME type from the extension.

```python
img_id = doc.add_resource_from_file("logo.png")
```

### Validation

#### `doc.validate() → list[str]`

Run structural sanity checks. Returns a list of issue strings; an empty list means the document is valid. Examples of issues detected: required variables not set, references to nonexistent resource IDs, duplicate object IDs, objects positioned entirely off-page.

```python
issues = doc.validate()
if issues:
    print("Document has problems:")
    for i in issues: print(f"  - {i}")
```

### Export

See [reference/05-export.md](05-export.md) for full export options.

#### `doc.export_pdf(path, vector=True, **kwargs)`

Export to PDF. By default, uses the built-in vector writer. Pass `vector=False` to use the raster fallback (requires `reportlab`).

#### `doc.export_bitmap(path, page=0, dpi=300, format=None, color_space=None, bit_depth=8)`

Export one page to a raster image.

#### `doc.export_svg(path, page=0)`

Export one page to SVG.

#### `doc.export_3x(path)`

Save a v3-compatible copy of the document. Lossy: tables flatten to groups, rich text collapses, paths sample to polygons, gradients average to a single color.

### Encryption

See [reference/07-encryption.md](07-encryption.md) for the full encryption system.

#### `doc.set_password(level, password) → str | None`

Set or replace the password for a permission level. Returns a 24-character recovery key if this is the first password (otherwise `None`).

#### `doc.remove_password(level)`

Remove a password slot. Requires `admin` permission.

#### `doc.change_password(level, old_password, new_password)`

Rotate a password without re-encrypting the payload.

#### `doc.unlock(password=None, recovery_key=None) → Permission`

Unlock an encrypted document.

#### `doc.lock()`

Forget the cached content key. Subsequent operations on encrypted content will fail until re-unlocked.

#### `doc.can(required) → bool`

Check whether the current session has the required permission.

#### `doc.require(required)`

Raise `PermissionError` if the current session lacks the permission.

#### `doc.clear_all_protection()`

Remove all encryption and passwords. Requires `admin` permission.

### Properties (encryption-related, read-only)

- `doc.encryption_mode: str` — `"none"`, `"partial"`, or `"full"`. Setter is allowed for changing modes when at least one password is set.
- `doc.is_encrypted: bool`
- `doc.is_locked: bool` — `True` if encrypted and not unlocked
- `doc.permission_level: Permission`
- `doc.password_levels: list[str]`
- `doc.recovery_key: str | None` — pending recovery key (returned once after `set_password`)

### Errors

- `doc.errors: list[str]` (read-only) — accumulated warnings from operations like load (e.g. legacy migration notes, missing resources)
- `doc.clear_errors()` — clear the list

### Print

#### `doc.print_document(printer_name=None, copies=1, dpi=None)`

Send the document to a system printer. Requires `[pyqt6]`. If `printer_name` is `None`, the default system printer is used. `dpi=None` uses the printer's native resolution (capped at 300 to avoid huge data).

---

## Class: `Page`

A single page of the document. Pages contain objects.

### Attributes

- `id: str` — UUID
- `width: float` — in mm
- `height: float` — in mm
- `dpi: int` — used for raster export
- `color_space: str` — one of `CS_RGB`, `CS_RGBA`, `CS_GRAY`, `CS_BW`, `CS_CMYK`
- `bit_depth: int` — `BD_8` or `BD_16`
- `background: tuple` — RGBA tuple, e.g. `(255, 255, 255, 255)` for white
- `objects: list[EdofObject]` — direct list of page contents
- `index: int` (read-only) — position within the document

### Adding objects

#### `page.add_textbox(x, y, w, h, text="") → TextBox`

Quick way to add a text box. See [reference/02-objects.md](02-objects.md) for the full TextBox API.

#### `page.add_image(resource_id, x, y, w, h) → ImageBox`

Add an image referencing a previously-uploaded resource.

#### `page.add_shape(shape_type, x, y, w, h) → Shape`

Add a shape. `shape_type` is one of `"rect"`, `"ellipse"`, `"line"`, `"polygon"`, `"arrow"`, `"path"`.

#### `page.add_qrcode(x, y, w, h, data="") → QRCode`

Add a QR code object.

#### `page.add_table() → Table`

Add an empty table. Configure its `cells`, `col_widths`, etc. afterward.

#### `page.add_group() → Group`

Add a group container; populate its `children`.

#### `page.add_object(obj) → EdofObject`

Add a pre-built object (e.g. one constructed manually or copied).

```python
new_tb = my_template_textbox.copy()
page.add_object(new_tb)
```

### High-level helpers

These are convenience methods that build pre-styled compositions. See [reference/10-helpers.md](10-helpers.md) for full details.

- `page.add_card(x, y, w, h, title, body, accent_color)` — title + body in a styled box
- `page.add_metric(x, y, w, h, label, value, subtitle="", value_color=None)` — number/metric block
- `page.add_table(x, y, w, rows, header=True, alternating=True)` — quick table from list-of-lists data
- `page.add_kv_list(x, y, w, items, key_width_frac=0.4)` — two-column key:value list
- `page.add_textbox_auto(x, y, w, text, min_height=10, **style)` — text box whose height is computed from content

### Layout helpers (cursor-based composition)

#### `page.row(y, gap=2.0, height=8.0) → RowContext`

Context manager for composing horizontally:

```python
with page.row(y=20, gap=2, height=10) as r:
    r.add_textbox(80, "Name:")        # 80 mm wide
    r.add_textbox(120, "{name}")
```

#### `page.column(x, gap=3.0, width=180.0) → ColumnContext`

Context manager for composing vertically:

```python
with page.column(x=15, gap=3, width=180) as c:
    c.add_textbox_auto("Long paragraph that grows to fit...")
    c.add_textbox(8, "Footer note")
```

### Querying objects

#### `page.get_object(obj_id) → EdofObject | None`

Find an object by its ID (recursively searches groups).

#### `page.get_by_name(name) → list[EdofObject]`

Return all objects whose `name` field matches.

#### `page.get_by_tag(tag) → list[EdofObject]`

Return all objects whose `tags` list contains the tag.

#### `page.sorted_objects() → list[EdofObject]`

Return objects sorted by `layer` ascending (back-to-front render order). The `objects` list itself is not auto-sorted; use this when you need traversal order.

### Removing objects

#### `page.remove_object(obj_id) → bool`

Remove an object by ID. Returns `True` if found and removed.

### Repeating sections (template generation)

#### `page.repeat_objects(template, data, gap=2.0) → list[Page]`

Duplicate a list of template objects for each row of data, substituting `{column_name}` placeholders. Auto-paginates onto new pages when the current page is full. Returns a list of any new pages that were added.

```python
header_tb = page.add_textbox(10, 10, 180, 8, "Sales Report")
header_tb.style.bold = True

# Build a template row (don't add it permanently to the page yet)
row_tpl = page.add_textbox(10, 20, 180, 6, "{name}: {amount} CZK")
page.objects.remove(row_tpl)

new_pages = page.repeat_objects([row_tpl],
    [{"name": "Alice", "amount": 1500},
     {"name": "Bob",   "amount": 2300},
     # ... 200 more rows ...
    ], gap=1.0)

print(f"Added {len(new_pages)} extra pages")
```

The placeholder substitution happens against the data dict. Variables defined on the document are also expanded if present.

### Page operations

#### `page.duplicate() → Page`

Return a deep copy with a new ID. Does **not** add the copy to the document; you have to do that explicitly.

#### `page.to_dict() → dict`

Serialize the page (used by serializer).

#### `Page.from_dict(d) → Page` (classmethod)

Reconstruct a page from a dict.

---

## Module: `edof.format.serializer`

Low-level save/load. You generally don't need to call these directly — `doc.save()` and `edof.load()` use them under the hood. Useful for reading an `.edof` file's manifest without fully loading it:

### `EdofSerializer.peek(path) → dict`

Return the manifest dictionary without loading or decrypting the document. Works on encrypted documents too — you'll see the protection block and slot info, but no content.

```python
from edof.format.serializer import EdofSerializer

manifest = EdofSerializer.peek("doc.edof")
print(f"Title: {manifest.get('title')}")
print(f"Pages: {manifest.get('pages')}")
print(f"Encrypted: {manifest.get('protection') is not None}")
```

### `EdofSerializer.save(doc, path)` (staticmethod)

Same as `doc.save(path)`.

### `EdofSerializer.load(path, password=None, recovery_key=None) → Document` (staticmethod)

Same as `edof.load(path, password, recovery_key)`.

### `EdofSerializer.from_bytes(data, password=None, recovery_key=None) → Document` (staticmethod)

Load from raw bytes (e.g. when the `.edof` data comes from a network or database, not from a file).

### `EdofSerializer.to_bytes(doc) → bytes` (staticmethod)

Serialize to raw bytes without writing to disk.

```python
data = EdofSerializer.to_bytes(doc)
# Now you can store `data` in a database, send it over network, etc.

# Later:
from edof.format.serializer import EdofSerializer
doc = EdofSerializer.from_bytes(data)
```
