# edof – Easy Document Format 3.0

[![PyPI version](https://img.shields.io/pypi/v/edof.svg)](https://pypi.org/project/edof/)
[![Python](https://img.shields.io/pypi/pyversions/edof.svg)](https://pypi.org/project/edof/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**edof** is a Python library for programmatic document creation, template filling,
and high-quality export. Documents are stored as `.edof` files – a versioned ZIP
archive containing a JSON document structure and all embedded resources.

---

## Installation

```bash
# Core (Pillow only)
pip install edof

# With PDF export
pip install edof[pdf]

# With QR code generation
pip install edof[qr]

# With PyQt6 GUI widget
pip install edof[pyqt6]

# Everything
pip install edof[all]

# For development
pip install edof[dev]
```

---

## Quick Start

```python
import edof

# Create a document (A4, 300 DPI, RGB)
doc = edof.new(width=210, height=297, title="My Doc", author="Jan")

# Add a page
page = doc.add_page(dpi=300, color_space="RGB")

# Add a text box with auto-shrink
tb = page.add_textbox(x=10, y=10, width=190, height=30,
                       text="This text shrinks to fit!")
tb.style.font_size   = 48
tb.style.auto_shrink = True
tb.style.alignment   = "center"

# Add an image
rid = doc.add_resource_from_file("photo.jpg")
page.add_image(rid, x=10, y=50, width=80, height=60, fit_mode="contain")

# Add a QR code
page.add_qrcode("https://example.com", x=100, y=50, size=40)

# Add a shape
sh = page.add_shape("rect", x=10, y=120, width=190, height=1)
sh.fill.color = (0, 0, 0)

# Save
doc.save("document.edof")

# Export bitmap
doc.export_bitmap("output.png", page=0, dpi=300, color_space="RGB")

# Export PDF (requires pip install edof[pdf])
doc.export_pdf("output.pdf")
```

---

## Named Variables (Template / Batch Fill)

```python
doc = edof.new()
page = doc.add_page()

# Define variables
doc.define_variable("recipient", type="text", default="World",
                    description="Recipient name")
doc.define_variable("date",      type="date")

# Bind objects to variables
tb = page.add_textbox(10, 10, 100, 20, "")
tb.variable = "recipient"

# Fill at render time
doc.fill_variables({"recipient": "Jan Novák", "date": "2025-06-01"})
doc.export_bitmap("output.png")

# Batch fill loop
for name in ["Alice", "Bob", "Carol"]:
    doc.fill_variables({"recipient": name})
    doc.export_bitmap(f"cert_{name}.png")
```

---

## Object Manipulation

```python
obj = page.add_textbox(0, 0, 50, 20, "Hello")

# Move
obj.move(10, 5)                        # translate by dx, dy
obj.move_to(20, 30)                    # absolute position

# Resize
obj.resize_uniform(1.5)               # scale both axes by factor
obj.resize(100, 40)                   # free resize (mm)
obj.resize(100, 40, anchor="center")  # resize keeping center fixed

# Rotate around center
obj.rotate(45)                         # add 45°
obj.rotate_to(90)                      # set absolute

# Flip
obj.flip_h()
obj.flip_v()

# Transform chaining
obj.move_to(10, 10).resize(80, 30).rotate(15)
```

---

## Color Spaces & Bit Depth

```python
# Page-level settings
page = doc.add_page(color_space="L",  bit_depth=8)   # grayscale
page = doc.add_page(color_space="1")                  # black & white
page = doc.add_page(color_space="RGBA", bit_depth=16) # 16-bit with alpha

# Export with override
doc.export_bitmap("bw.png",    color_space="1")
doc.export_bitmap("gray.tiff", color_space="L",  format="TIFF")
doc.export_bitmap("hdr.tiff",  color_space="RGB", bit_depth=16, format="TIFF")
```

---

## QR Codes

```python
# Static QR
page.add_qrcode("https://example.com", x=10, y=10, size=40,
                error_correction="H")   # L / M / Q / H

# Variable-bound QR (changes with fill_variables)
qr = page.add_qrcode("", x=10, y=60, size=30)
qr.variable = "url"
doc.define_variable("url", type="qr")
doc.set_variable("url", "https://mysite.com/user/42")

# Generate standalone QR image
from edof.utils.qr import generate_qr_bytes
png_bytes = generate_qr_bytes("Hello!", size_px=512)
```

---

## GUI Widgets

### Tkinter

```python
import tkinter as tk
import edof
from edof.gui.tkinter_canvas import EdofTkCanvas

root   = tk.Tk()
doc    = edof.load("document.edof")
canvas = EdofTkCanvas(root, doc, page_index=0, zoom=1.0, dpi=96,
                       width=800, height=600)
canvas.pack(fill="both", expand=True)

# Callbacks
canvas.on_select(lambda obj_id: print("Selected:", obj_id))
canvas.on_change(lambda: print("Document changed"))

# Zoom control
canvas.zoom = 1.5
canvas.zoom_fit()

root.mainloop()
```

### PyQt6

```python
from PyQt6.QtWidgets import QApplication
import edof
from edof.gui.pyqt6_widget import EdofQtWidget

app    = QApplication([])
doc    = edof.load("document.edof")
widget = EdofQtWidget(doc, page_index=0, zoom=1.0)
widget.resize(900, 700)
widget.show()
app.exec()
```

---

## Command API

```python
import edof
from edof.api.commands import execute, CommandHistory

doc = edof.new()
doc.add_page()

# Execute commands
obj_id = execute(doc, {"cmd": "add_textbox", "page": 0,
                        "x": 10, "y": 10, "width": 80, "height": 20,
                        "text": "Hello API"})

execute(doc, {"cmd": "set_style", "object_id": obj_id, "page": 0,
               "style": {"font_size": 24, "auto_shrink": True}})

execute(doc, {"cmd": "export_bitmap", "page": 0, "path": "out.png",
               "dpi": 300, "format": "PNG"})

# Undo / redo
history = CommandHistory(max_undo=50)
history.push(doc, "initial")
# … make changes …
doc = history.undo(doc)   # returns restored Document or None
doc = history.redo(doc)
```

---

## Version Compatibility

```python
import warnings
from edof.exceptions import EdofNewerVersionWarning

# Older files are loaded and migrated automatically (no action needed).

# Newer files: a EdofNewerVersionWarning is emitted (never blocks execution).
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    doc = edof.load("newer_format.edof")
    if w:
        print("Notice:", w[0].message)

# Check error state (non-fatal notices from the load)
print(doc.errors)
```

---

## EDOF Editor

A full desktop editor ships with the library:

```bash
python edof_editor.py
python edof_editor.py myfile.edof
```

Features: canvas with zoom/pan, object selection and drag-move, property panel,
text/image/shape/QR insertion, variables dialog, undo/redo, PNG/PDF export.

---

## File Format

`.edof` files are ZIP archives:

```
document.edof (ZIP)
├── manifest.json       ← version header, quick metadata
├── document.json       ← full document tree (JSON)
└── resources/
    ├── <uuid>          ← embedded image / font blobs
    └── …
```

---

## Running Tests

```bash
pip install edof[dev]
pytest
pytest --cov=edof --cov-report=html
```

---

## Publishing to PyPI

```bash
pip install build twine
python -m build
twine upload dist/*
```

---

## License

MIT – see [LICENSE](LICENSE).
