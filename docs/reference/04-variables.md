# Reference: Variables & Templates

The variable system turns documents into reusable templates. Variables are typed, can have defaults, and are substituted into text via `{name}` placeholders or bound directly to images and QR codes.

## Defining a variable

```python
doc.define_variable(
    name="recipient",
    type="text",
    default=None,
    required=True,
    label="Recipient name",      # human-readable label (used in editor / CLI)
    help="Person being awarded the certificate",
    choices=None,                # for "text" type: list of allowed values
    max_length=None,             # for "text" type: maximum string length
)
```

### Variable types

| Type constant | String | Purpose |
|---|---|---|
| `VAR_TEXT`   | `"text"`   | String value |
| `VAR_NUMBER` | `"number"` | Integer or float |
| `VAR_DATE`   | `"date"`   | Date string (ISO 8601: `YYYY-MM-DD`) |
| `VAR_BOOL`   | `"bool"`   | True / False |
| `VAR_URL`    | `"url"`    | URL string (validated as a URL on set) |
| `VAR_IMAGE`  | `"image"`  | Resource ID or file path |
| `VAR_QR`     | `"qr"`     | Text/URL to encode as QR (used by QRCode objects) |

You can use the constants or the strings interchangeably:

```python
from edof import VAR_NUMBER

doc.define_variable("score", type=VAR_NUMBER, default=0)
doc.define_variable("score", type="number", default=0)   # equivalent
```

### Optional fields

- `required: bool` — if `True`, `doc.validate()` fails when the variable has no value
- `default` — value used when no explicit value is set
- `label: str` — display label for editor / CLI prompts
- `help: str` — descriptive text
- `choices: list` — restrict text values to this list (becomes a dropdown in the editor)
- `max_length: int` — for text variables; trims at this length

---

## Setting variable values

```python
doc.set_variable("recipient", "Jan Novák")
doc.set_variable("score", 95)

# Bulk
doc.fill_variables({
    "recipient": "Jan Novák",
    "score":     95,
    "date":      "2026-05-04",
})
```

`fill_variables()` is a wrapper that calls `set_variable()` repeatedly.

Type checking is enforced — setting a non-numeric value on a `number` variable raises `EdofVariableError`. Same for invalid dates, malformed URLs, etc.

---

## Using variables in text

The `{variable_name}` syntax substitutes at render time:

```python
doc.define_variable("name")
doc.define_variable("amount", type="number")

page.add_textbox(15, 15, 180, 8, "Hello {name}, you owe {amount} CZK.")

doc.set_variable("name", "Alice")
doc.set_variable("amount", 1500)
doc.export_pdf("invoice.pdf")
```

The result reads "Hello Alice, you owe 1500 CZK."

### Number formatting

By default, numbers render as Python's `str(value)`. To format more carefully (currency, decimals, etc.), pre-format the string in code before setting the variable:

```python
doc.set_variable("amount", f"{1500.50:,.2f}")   # "1,500.50"
```

Or define the variable as `text` instead of `number`.

### Date formatting

Dates render in ISO format by default. For custom formatting, do it in code:

```python
import datetime
date = datetime.date.today()
doc.set_variable("today", date.strftime("%d. %B %Y"))   # "4. May 2026"
```

---

## Binding objects to variables directly

Some object types support a `variable` attribute that overrides their content at render time.

### TextBox bound to a variable

```python
doc.define_variable("title", default="Untitled")

tb = page.add_textbox(15, 15, 180, 12, "")
tb.variable = "title"
# tb.text is ignored at render — value of "title" is used instead
```

This is equivalent to `tb.text = "{title}"`, but the binding is explicit and the editor shows it differently in the UI.

### ImageBox bound to a variable

```python
doc.define_variable("logo", type="image")

ib = page.add_image(default_logo_id, x=15, y=15, w=40, h=40)
ib.variable = "logo"

# Now at render time, "logo" can be a resource ID OR a path to a file:
doc.set_variable("logo", "/path/to/customer_logo.png")
doc.export_pdf("output.pdf")

# Or another resource ID already in the document:
new_id = doc.add_resource_from_file("alternate.png")
doc.set_variable("logo", new_id)
```

### QRCode bound to a variable

```python
doc.define_variable("verify_url", type="url")

qr = page.add_qrcode(160, 15, 30, 30, data="https://default.com")
qr.variable = "verify_url"

doc.set_variable("verify_url", "https://verify.example.com/abc123")
```

---

## VariableStore (low-level access)

`doc.variables` is a `VariableStore` instance. Most users don't interact with it directly, but it has these methods:

```python
store = doc.variables

store.names()                  # list of all variable names
store.exists("score")          # bool
store.get("score")             # current value (or default if not set)
store.get_definition("score")  # VariableDef object
store.set("score", 42)         # same as doc.set_variable
store.unset("score")           # remove value (falls back to default)
store.values()                 # dict of all current values
```

### VariableDef

The metadata about a variable (separate from its current value):

```python
defn = doc.variables.get_definition("score")
print(defn.name, defn.type, defn.default, defn.required)
```

Fields: `name`, `type`, `default`, `required`, `label`, `help`, `choices`, `max_length`.

---

## Repeating sections

`page.repeat_objects()` is the powerful template feature: it duplicates a set of "template" objects for each row of a data list and auto-paginates onto new pages.

```python
# Build a header that goes on every page
header = page.add_textbox(15, 10, 180, 8, "Sales Report")
header.style.bold = True

# Build a template row
row_tpl = page.add_textbox(15, 25, 180, 8, "{name}: {amount} CZK")
row_tpl.style.font_size = 10

# Important: remove the template from the page before repeating it
page.objects.remove(row_tpl)

# Generate one row per data entry; repeat_objects creates new pages as needed
new_pages = page.repeat_objects(
    template=[row_tpl],
    data=[
        {"name": "Alice", "amount": 1500},
        {"name": "Bob",   "amount": 2300},
        {"name": "Carol", "amount": 1850},
        # ... 200 more ...
    ],
    gap=2.0,                    # vertical spacing in mm between repeated rows
)

print(f"Added {len(new_pages)} extra pages.")
```

### Parameters

- `template: list[EdofObject]` — the objects to repeat. They can use `{column_name}` placeholders that match keys of the data dicts.
- `data: list[dict]` — list of records. Each record's keys are the placeholders.
- `gap: float` — vertical space in mm between repetitions (default: 2.0)

### How it works

1. The template is "snapshotted" — relative positions of objects are preserved.
2. For each row in `data`:
   - All template objects are deep-copied
   - `{column}` placeholders are replaced with `row[column]`
   - The copies are added to the current page, shifted vertically
3. When the next repetition would overflow the page, a new page is added (with the same dimensions) and rendering continues there.
4. The new pages are returned so you can add page-specific elements (page numbers, etc.).

### Multi-object templates

```python
header = page.add_textbox(15, 0, 100, 6, "{name}")
header.style.bold = True
header.style.font_size = 10

body = page.add_textbox(15, 6, 180, 12, "{description}")
body.style.font_size = 8

shape = page.add_shape("line", 15, 18, 180, 0)
shape.points = [[0, 0], [180, 0]]

# Remove the template objects from the page
page.objects.remove(header)
page.objects.remove(body)
page.objects.remove(shape)

# Repeat them as a unit
page.repeat_objects(
    template=[header, body, shape],
    data=[
        {"name": "Section 1", "description": "Some description text."},
        {"name": "Section 2", "description": "More description."},
        # ...
    ],
    gap=4.0,
)
```

### Adding page-specific elements after repeat

```python
new_pages = page.repeat_objects(template=[row_tpl], data=data, gap=1.0)

# Add a page number to every page
for i, p in enumerate([page] + new_pages):
    pn = p.add_textbox(95, 285, 20, 6, f"Page {i+1}")
    pn.style.font_size = 8
    pn.style.alignment = "center"
```

---

## Validation

`doc.validate()` checks (among other things) that all `required=True` variables have values:

```python
doc.define_variable("recipient", required=True)
issues = doc.validate()
print(issues)
# ['Required variable "recipient" has no value']

doc.set_variable("recipient", "Alice")
issues = doc.validate()
print(issues)
# []
```

`fill_variables()` does NOT auto-validate; call `validate()` explicitly to check.

---

## Variable expressions in `visible_if`

`obj.visible_if` is a small expression evaluated against `doc.variables` at render time:

```python
discount_label = page.add_textbox(15, 200, 180, 8, "DISCOUNT: -{discount} CZK")
discount_label.visible_if = "discount > 0"

vip_section = page.add_group()
vip_section.visible_if = "tier == 'gold' or score >= 90"
```

See [reference/02-objects.md](02-objects.md#conditional-visibility-visible_if) for the full expression syntax.
