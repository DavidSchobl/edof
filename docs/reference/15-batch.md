# Reference: 3D Batch

The 3D Batch turns one document into many: **columns** bind cells to object
attributes, **rows** carry the values, and the export engine renders every
row to files. It replaces per-object variable bindings (the editor's 3D
Batch panels are a UI over exactly this model).

```python
from edof import Document
from edof.format.styles import TextRun
from edof.batch.model import build_ref, BatchRow
from edof.batch.generate import export_batch

doc = Document()
pg = doc.add_page()
tb = pg.add_textbox(10, 10, 100, 12, "Name")
tb.runs = [TextRun(text="Name", rid="r1", var_name="name")]

cfg = doc.batch
cfg.row_scope = "document"
col = cfg.add_column(build_ref(pg, tb), "run.text", "name", "text")
col.run_id = "r1"
cfg.rows.append(BatchRow(name="Praha", values={col.column_id: "Praha"}))
cfg.rows.append(BatchRow(name="Brno",  values={col.column_id: "Brno"}))

ok, written, errors = export_batch(doc, cfg, cfg.rows, "out",
                                   "[ROW_NUMBER:03]_[ROW_NAME]", "pdf",
                                   scope="all")
```

## Model (`edof.batch.model`)

| Piece | Meaning |
|---|---|
| `ObjectRef` | stable path to a target object (survives page reordering); `build_ref(page, obj)` creates one |
| `BatchColumn` | one bound attribute: `target` + dotted `attr_path`, `header`, value `kind` (text, number, color, enum, file_path, …) |
| `BatchColumn.run_id` | for text (run) variables: the span's `rid` — the column drives that span, not the whole textbox |
| `BatchColumn.extra_run_ids` | further variable rids **linked** to this column: one value drives several distinct spans (v4.4.0) |
| `BatchRow` | `values` = `{column_id: raw_value}`, optional `name`, `page_target` |
| `BatchConfig` | `row_scope` (`"page"`: a row fills one page; `"document"`: every page), `columns`, `rows`, `demo_rows` + `export_demo` |

Column headers are **unique by construction** (v4.4.0): unnamed columns
persist a systematic "textbox-1.text" style name, taken names are
auto-suffixed, and `BatchConfig.header_in_use` / `unique_header` /
`system_header` are the public helpers behind it.

`doc.batch` is the document's `BatchConfig` (created lazily, serialized with
the file). `apply_row_to_document(cfg, doc, row)` projects one row onto a
document: cells are coerced per column kind — a `file_path` cell
materialises the file into the resource store automatically.
`cfg.update_rows_from_csv(text)` imports rows, matching columns by header.

## Attribute registry (`edof.batch`)

The introspection layer behind the panels: `describe_object(obj)` /
`describe_type("textbox")` return uniform descriptors (dotted path, label,
kind, enum values, `get`/`set` with coercion) for every batchable attribute;
`find_descriptor(obj, path)` and `apply_value(obj, path, raw)` work with a
single one. Covered: textbox, imagebox, shape, qrcode, subdocument, plus
transform/opacity on everything, layer-effect fields
(`find_descriptor_with_effect_id`) and text-run spans
(`find_descriptor_with_run_id`, `extra_run_ids` aware).

## Export engine (`edof.batch.generate`)

`export_batch()` — scope (page/all), formats (png/jpg/svg/pdf/edof),
per-row vs single multipage output, sources modes, filename tags, image
compression and a cancellable progress callback are all documented in the
[Export reference](05-export.md#batch-export-v440).

## Filename tags (`render_filename`)

`[ROW_NUMBER]`, `[ROW_NUMBER:04]` (zero-padded), `[ROW_NAME]`, `[PAGE]`,
`[PAGE:02]`, `[{Header}]`, `[{Header:upper}]`, `[{Header:lower}]`; anything
else is literal text, the extension is appended automatically, name
collisions get `_2`, `_3`, …

## Editor

The **3D Batch** tab (right panel) manages columns and templates; the **3D
Batch (table)** dock edits rows like a spreadsheet, previews any row on the
canvas non-destructively, imports CSV and holds the **Generate…** button
(also in *File → Generate batch…*). Text variables are created from a
selection (`{ }` button), managed in the Objects panel (checkboxes, rename,
remove, change range, linking) — see the
[Variables reference](04-variables.md).
