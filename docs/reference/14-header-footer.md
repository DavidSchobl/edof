# Reference: Header & Footer (document mode)

Document mode gives every page a shared **header band** and **footer band**,
plus (v4.4.0) full **containers of objects** that repeat on every page.

## Band text

The band text lives as template runs on the document body:

```python
from edof.format.styles import TextRun
from edof.format.document_body import DocumentBody

if doc.body is None:            # document mode: body drives pagination
    doc.body = DocumentBody()
doc.body.header_enabled = True
doc.body.header_runs = [TextRun(text="Menu — page {page_number}")]
doc.body.footer_enabled = True
doc.body.footer_runs = [TextRun(text="{page_number} / {page_count}")]
```

Tokens resolved per page: `{page_number}`, `{page_count}`,
`{page_number_left|center|right}`. `page_number_start` and the
odd/even template sets (`header_runs_even`, …) are honoured.

In the editor the band opens for editing on a **single click**; a `#▾`
toolbar menu inserts the page-number tokens. Band geometry is driven by page
setup (band height, margins) — bands are never dragged or resized as objects.

### Canonical ids

Every page's band box carries the same id: `hf_header` / `hf_footer`
(migrated automatically for older files at pagination). One batch
`ObjectRef(["hf_header"])` therefore addresses the band on **every** page.

### Batch variables in the band

Text variables work inside the band like anywhere else: make a selection in
the band editor a variable and its `rid` is persisted to the body template,
so it survives repagination, and a document-scope batch row fills the header
on every page at once. Remove / rename / merge / change-range all mirror
into the templates.

## Header & footer as containers of objects (v4.4.0)

Any object type (TextBox, ImageBox, Shape, …) can live in the band:

```python
from edof.format.objects import Shape

logo = Shape("rectangle")            # or any object
doc.body.header_objects.append(logo)
```

* Every page receives a **literal clone** with the **same id** as the
  template — rendering, selection, batch refs and variable rids work per
  page while the single source of truth stays on `doc.body`.
* **Editing any clone writes back** to the template and re-syncs every page.
* Editor: right-click an object in the Objects panel → **Move to header** /
  **Move to footer** / **Detach**. Container members carry a
  `▤ header` / `▤ footer` badge in the panel.
* Clones are derived state, rebuilt at each pagination; removing the
  template removes them everywhere.
* `{page_number}` tokens stay a *band-text* feature — container clones are
  literal copies (that keeps the clone → template write-back lossless).

## Storage (format 4.3.0)

| Key on `doc.body` | Meaning |
|---|---|
| `header_runs` / `footer_runs` (+`_even`) | band text templates |
| `header_style` / `footer_style` (+`_even`) | band box style (padding is always forced to 0) |
| `header_objects` / `footer_objects` | container templates (any object) |
| `header_height_mm` / `footer_height_mm`, `hf_odd_even`, `page_number_start` | geometry & numbering |

Old readers ignore the new keys; files without them load unchanged.
