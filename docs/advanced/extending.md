# Extending edof

If the built-in object types don't cover a use case, you have two options:

1. **Compose existing types** into reusable patterns (functions or classes that build groups of standard objects)
2. **Subclass `EdofObject`** for genuinely new object types that need custom rendering

Option 1 is much easier and covers most needs. Option 2 requires touching the renderer and serializer.

---

## Option 1: Composition (recommended)

Most "new objects" can be built from existing types:

### A barcode object

`Shape` with `path` type can render any vector shape. To build a barcode:

```python
import edof
from edof import Shape

def make_barcode(data, width_mm=40, height_mm=10):
    """Generate a Code 39 barcode as a Shape."""
    # Code 39 character widths (1=narrow, 2=wide), pattern of 9 elements:
    # bar-space-bar-space-bar-space-bar-space-bar
    code39 = {
        '0': 'NwNwwNwNN', '1': 'wNNwNNNNw', '2': 'NNwwNNNNw', '3': 'wNwwNNNNN',
        # ... etc.
    }
    # ...
    # Build path data
    path_data = []
    x = 0
    for char in data:
        pattern = code39[char]
        for i, w in enumerate(pattern):
            if i % 2 == 0:  # bar
                bar_w = 0.4 if w == 'N' else 1.2
                path_data.append(["M", x, 0])
                path_data.append(["L", x + bar_w, 0])
                path_data.append(["L", x + bar_w, height_mm])
                path_data.append(["L", x, height_mm])
                path_data.append(["Z"])
            else:  # space
                bar_w = 0.4 if w == 'N' else 1.2
            x += bar_w + 0.1   # inter-element gap

    sh = Shape(shape_type="path")
    sh.path_data = path_data
    sh.transform.width = x
    sh.transform.height = height_mm
    sh.fill.color = (0, 0, 0, 255)
    return sh

barcode = make_barcode("HELLO123", width_mm=40, height_mm=10)
barcode.transform.x = 15
barcode.transform.y = 100
page.add_object(barcode)
```

### A signature box

```python
def add_signature_box(page, x, y, w, h=15, label="Signature"):
    """Build a signature line + label as a group."""
    from edof import Group, Shape

    g = Group()
    g.transform.x = x
    g.transform.y = y
    g.transform.width = w
    g.transform.height = h

    # Signature line
    line = Shape(shape_type="line")
    line.transform.x = 0
    line.transform.y = h - 4
    line.transform.width = w
    line.points = [[0, 0], [w, 0]]
    line.stroke.color = (50, 50, 50, 255)
    line.stroke.width = 0.3
    g.children.append(line)

    # Label below
    tb = page.add_textbox(0, h - 3, w, 4, label)
    tb.style.font_size = 8
    tb.style.alignment = "center"
    tb.style.color = (100, 100, 100)
    page.objects.remove(tb)
    g.children.append(tb)

    page.add_object(g)
    return g

add_signature_box(page, 20, 250, 80, label="Director")
add_signature_box(page, 110, 250, 80, label="Date")
```

### A multi-line bullet list

```python
def add_bullet_list(page, x, y, w, items, font_size=10, bullet="•"):
    """Add a bulleted list as a group of textboxes."""
    items_list = list(items)
    line_height = font_size * 0.4   # rough mm conversion

    for i, item in enumerate(items_list):
        # Bullet
        b = page.add_textbox(x, y + i * line_height, 5, line_height, bullet)
        b.style.font_size = font_size
        b.style.alignment = "right"
        # Text
        t = page.add_textbox(x + 5, y + i * line_height, w - 5, line_height, item)
        t.style.font_size = font_size
        t.style.wrap = False

    return y + len(items_list) * line_height   # return next y

next_y = add_bullet_list(page, 15, 100, 180, [
    "First item",
    "Second item",
    "Third with longer text",
])
print(f"List ended at y={next_y}")
```

These compositions are just functions. They produce standard edof objects, so they save/load through the regular file format without any custom handling.

---

## Option 2: Custom object types

If you genuinely need a new persistable type that doesn't fit existing primitives, you can subclass `EdofObject`. This is **advanced** — it requires touching the renderer, serializer, and editor (if you want UI support).

### Step 1: Define the class

```python
# my_extension.py
from dataclasses import dataclass, field
from edof.format.objects import EdofObject

@dataclass
class StarShape(EdofObject):
    """N-pointed star shape."""
    OBJECT_TYPE = "star"   # serialized type tag

    points: int = 5
    inner_ratio: float = 0.5
    fill_color: tuple = (255, 200, 0, 255)
    stroke_color: tuple = (200, 100, 0, 255)
    stroke_width: float = 0.5

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["points"] = self.points
        d["inner_ratio"] = self.inner_ratio
        d["fill_color"] = list(self.fill_color)
        d["stroke_color"] = list(self.stroke_color)
        d["stroke_width"] = self.stroke_width
        return d

    @classmethod
    def from_dict(cls, d: dict):
        obj = cls()
        # Restore base fields
        EdofObject._populate_from_dict(obj, d)
        # Custom fields
        obj.points = int(d.get("points", 5))
        obj.inner_ratio = float(d.get("inner_ratio", 0.5))
        obj.fill_color = tuple(d.get("fill_color", (255, 200, 0, 255)))
        obj.stroke_color = tuple(d.get("stroke_color", (200, 100, 0, 255)))
        obj.stroke_width = float(d.get("stroke_width", 0.5))
        return obj
```

### Step 2: Register the type

```python
from edof.format.objects import register_object_type

register_object_type("star", StarShape)
```

This lets the deserializer know what class to instantiate when it sees `"type": "star"` in a saved document.

### Step 3: Render it

The renderer needs to know how to draw the new type. There are two ways:

**Way A: Convert to existing primitives at render time.**

If your custom type is fundamentally a `Shape` with extra metadata, you can write a "to_primitive" method that converts it to a standard `Shape` whenever the renderer asks:

```python
def to_render_primitive(self):
    """Return an equivalent edof.Shape for rendering."""
    import math
    from edof import Shape

    cx = self.transform.x + self.transform.width / 2
    cy = self.transform.y + self.transform.height / 2
    R = min(self.transform.width, self.transform.height) / 2
    r = R * self.inner_ratio

    # Build star path
    path_data = []
    for i in range(self.points * 2):
        angle = -math.pi / 2 + i * math.pi / self.points
        radius = R if i % 2 == 0 else r
        px = math.cos(angle) * radius + (R if i == 0 else 0)
        py = math.sin(angle) * radius + R
        if i == 0:
            path_data.append(["M", px, py])
        else:
            path_data.append(["L", px, py])
    path_data.append(["Z"])

    sh = Shape(shape_type="path")
    sh.transform = self.transform
    sh.path_data = path_data
    sh.fill.color = self.fill_color
    sh.stroke.color = self.stroke_color
    sh.stroke.width = self.stroke_width
    return sh
```

Then patch the renderer (or write a wrapper) to call `to_render_primitive()` for unknown types.

**Way B: Hook into the renderer.**

The renderer in `edof.engine.renderer` has a dispatch table. You'd need to add a case for your new type and write the actual Pillow drawing code. This is more involved — see the source of existing object renderers (`_render_textbox`, `_render_shape`, etc.) for examples.

### Step 4: Use it

```python
from my_extension import StarShape, register_my_types
register_my_types()

import edof
doc = edof.new()
page = doc.add_page()
star = StarShape()
star.transform.x = 50
star.transform.y = 50
star.transform.width = 30
star.transform.height = 30
star.points = 6
page.add_object(star)

doc.save("with_star.edof")
```

When loaded back, the file will deserialize the star (assuming the loading process has registered the type).

### Caveats

- **Portability:** files containing custom types only load correctly in environments that have your extension code. Sharing such files with vanilla edof users will result in errors or skipped objects.
- **Forward compatibility:** if you publish files with custom types, future edof versions may add a built-in type with the same name. Use a unique prefix (e.g., `mycompany_star`) to avoid collisions.
- **Editor support:** the GUI editor doesn't know about your custom types. Objects of unknown types are skipped or shown as placeholders.

---

## Custom serialization

Sometimes you don't need a new object type, just a custom way to encode one.

### Adding extra metadata to existing objects

Use the `tags` field for free-form labels, or define your own custom field via subclassing as shown above.

For loose metadata that shouldn't affect rendering, the `name` and `tags` fields are conventional:

```python
tb = page.add_textbox(15, 15, 180, 12, "Hello")
tb.name = "greeting"
tb.tags = ["headline", "translatable", "lang:en"]

# Later:
greetings = page.get_by_name("greeting")
translatable = page.get_by_tag("translatable")
```

These fields are preserved across save/load automatically.

### External post-processing

If you want to add features that don't fit the file format (e.g., comments, version history, change tracking), keep them in a separate file and link by document ID:

```python
import json

# Build the doc
doc = edof.new(title="Project Brief")
# ...
doc.save("brief.edof")

# Sidecar metadata
meta = {
    "doc_id": doc.id,
    "comments": [...],
    "approval_history": [...],
}
with open("brief.meta.json", "w") as f:
    json.dump(meta, f)
```

This way, your sidecar data travels with the document but doesn't pollute the format.

---

## Plugins for the editor (advanced)

The editor (`edof._apps.editor`) is a single PyQt6 file. To add menu items, custom dialogs, or new tools:

1. Fork the source
2. Add your code as a method of `EdofEditor`
3. Register the action in `_build_ui()` or one of the menu builders
4. Run via `python -m edof._apps.editor` instead of the installed `edof-editor` script

There's no formal plugin API as of 4.0.1 — extending the editor means modifying its source. A plugin system might come in future versions.

---

## When to suggest features upstream

If you're building something useful that others might want, consider opening an issue or PR on the [edof GitHub repository](https://github.com/DavidSchobl/edof) before going down the custom-type route. Examples of features that might be welcome upstream:

- New object types that solve general problems (charts, diagrams, complex shapes)
- New export formats
- Standard import formats
- Editor improvements

Custom domain-specific extensions (your-company-specific business logic) are better kept as separate packages or downstream forks.
