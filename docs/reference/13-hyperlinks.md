# Reference: Hyperlinks

v4.4.0. A link is a **run format**, like bold or italic: any span of text can
carry one. Two kinds exist:

* **External** — `http://…`, `https://…` or `mailto:…`. A bare domain
  (`example.com/menu`) is normalized to `https://`.
* **In-document** — written as `#<anchor_id>`, pointing at a **link target**
  (an *anchor*): a named span marked elsewhere in the document. Following it
  jumps to the target's page and selects the span.

```python
from edof import Document
from edof.format.styles import TextRun

doc = Document()
p1 = doc.add_page(); p2 = doc.add_page()
tb = p1.add_textbox(10, 10, 100, 12, "")
tb.runs = [
    TextRun(text="Visit the site", link="https://example.com"),
    TextRun(text=" or jump to the "),
    TextRun(text="glossary", link="#anch_glossary"),
]
tgt = p2.add_textbox(10, 10, 100, 12, "")
tgt.runs = [TextRun(text="Glossary", anchor="anch_glossary",
                    anchor_name="Glossary")]
```

## Data model

| Field | On | Meaning |
|---|---|---|
| `link` | `TextRun` | External URL or `#<anchor_id>`; `None` = plain text |
| `anchor` | `TextRun` | Stable target id (like a `rid`, survives editing around it) |
| `anchor_name` | `TextRun` | Human name shown in pickers |
| `link_style` | `Document` | Document-wide link appearance (below) |

All fields are optional format keys (format 4.3.0); old readers ignore them.

## Appearance: the document link style

Links render with the document link style unless a run overrides
`color` / `underline` explicitly — that is how one specific link is
re-styled by normal formatting.

```python
doc.link_style = {
    "color":       (17, 85, 204, 255),   # base colour (default: blue)
    "underline":   True,
    "hover_color": (11, 57, 158, 255),   # editor hover tint
}
```

`None` (the default) uses the built-in blue-underlined style. In the editor:
**Document → Link style…** edits it for every link at once.

## Editor & viewer behaviour

* **Create / edit:** select text, then the 🔗 toolbar button, **Ctrl+K**, or
  the right-click menu. The dialog offers an external URL or a picker of
  existing targets; *Remove link* lives in the same dialog and menu.
* **Mark a target:** select the target text, then the ⚓ toolbar button or
  right-click → *Mark as link target*. The button toggles — on an existing
  target it offers removal.
* **Follow:** **Ctrl+click** (Word-style) — inside the inline text editor
  *and* directly on the canvas, in both basic and document mode. Hovering
  tints the link with the hover colour; holding Ctrl shows the hand cursor.
* **Viewer:** a plain click follows links (panning still works).
* **View → Show Link Targets** marks anchor spans with a translucent
  red→blue gradient. Default **off**; never exported.

## Validation (security)

Link targets are validated everywhere — on creation, on follow and on
export — against a whitelist: `http`, `https`, `mailto` and `#anchor`.
`javascript:`, `file:`, `data:` and free text are refused;
`set_link_on_selection()` returns `False` for them. A link stored in an
untrusted file cannot smuggle a dangerous scheme, because following
re-validates. See `edof.utils.links.validate_link`.

## Export

* **PDF** — every link span emits a `/Link` annotation: external targets as
  `/A /URI` actions, in-document targets as `/Dest [page /Fit]` resolved to
  the target's page. Adjacent same-link words on a line merge into one
  clickable rectangle.
* **SVG** — link runs are wrapped in `<a href … xlink:href …>` (external
  links open in a new tab).
* **Bitmap** — links render with their colour/underline only (no regions).

Unsafe or dead targets are silently skipped by the exporters.
