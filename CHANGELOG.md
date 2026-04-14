# Changelog

All notable changes to **edof** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) · Versioning: [SemVer](https://semver.org/)

---

## [3.0.0] – 2025-01-01

Initial public release.

### Library

#### Document model
- `Document`, `Page`, `ResourceStore` – root structure
- Object types: `TextBox`, `ImageBox`, `Shape` (rect/ellipse/polygon/arrow), `Line` (two absolute points), `QRCode`, `Group`
- Common object properties: `id`, `name`, `variable`, `layer`, `locked`, `visible`, `editable`, `tags`, `opacity`, `shadow`
- `TextStyle` – font, size, bold/italic/underline/strikethrough, color, alignment (H+V), line height, word wrap, overflow
- `auto_shrink` – shrinks font to fit the box, never enlarges (font_size = maximum)
- `auto_fill` – fills the box by finding the largest fitting font size (grows + shrinks)
- `StrokeStyle`, `FillStyle`, `ShadowStyle` – RGBA color support throughout
- `Transform` – position/size in mm, clockwise rotation in °, flip H/V; full chain API

#### Variable / template system
- `VariableStore` – named placeholders with type validation (`text`, `number`, `date`, `image`, `qr`, `url`, `bool`)
- `doc.fill_variables({"name": "Jan"})` – batch fill for template rendering
- `ImageBox` variable – value can be a file path or HTTP URL loaded at render time
- Fallback: if variable is unset/empty, `obj.text` is displayed (non-destructive in editor)

#### Rendering
- Pillow RGBA compositor; color spaces: RGB, RGBA, L, 1, CMYK; bit depths: 8 and 16
- Configurable DPI per page
- Correct `pt → px` DPI conversion throughout (font sizing, auto-shrink/fill)
- Rotation applies to the entire object surface (fill + border + text as one unit)
- QR colorization: generates B&W first, colorizes pixel-by-pixel → all fg/bg colors work

#### File format (`.edof`)
- ZIP archive: `manifest.json` + `document.json` + `resources/<uuid>` (embedded fonts, images)
- `EdofSerializer` – `save`, `load`, `to_bytes`, `from_bytes`, `peek`
- Forward compat: newer file → `EdofNewerVersionWarning` (non-fatal, execution continues)
- Backward compat: older files migrated automatically via `edof.utils.compat`

#### Export & print
- Bitmap: PNG, JPEG, TIFF, BMP; all pages with `{page}` pattern; in-memory bytes
- PDF via reportlab (`pip install edof[pdf]`)
- Print: `QPrintPreviewDialog` (PyQt6), `os.startfile` (Windows), `lpr`/`lp` (macOS/Linux)

#### Text engine
- System font discovery on Windows / macOS / Linux via `font.getname()` metadata
- Bold/italic variant resolution, font cache, `list_system_fonts()`
- Text wrap, multi-line, vertical alignment, underline, strikethrough

#### QR codes
- `edof[qr]` optional dep; error correction L/M/Q/H; RGBA colors
- Standalone helpers: `edof.utils.qr.generate_qr_image()`, `generate_qr_bytes()`

#### Command API & undo/redo
- `edof.api.commands.execute(doc, {"cmd": "...", ...})` – string-based dispatch
- `CommandHistory` – snapshot-based undo/redo stack

#### GUI
- `EdofTkCanvas` – Tkinter canvas widget
- `EdofQtWidget` – PyQt6 QGraphicsView widget

### Applications

#### EDOF Editor (`edof_editor.py`) — requires PyQt6
- Async rendering (background thread, UI never blocks)
- Resize handles (8 directions) + rotation handle; rotated object resize keeps anchor fixed
- Shift = snap rotation to 15°, Alt = free rotation
- Inline text editing (double-click): WYSIWYG font size matches canvas zoom and screen DPI
- Double-click QR → inline data/URL editor; double-click Image → file picker
- Ghost outlines for hidden objects (still selectable)
- Type-aware property panel: TextBox / ImageBox / Shape / Line / QRCode each has own controls
- Custom color dialog: hex `#RRGGBBAA`, RGBA sliders, live swatch
- Object list panel, page list panel, layer ordering (front/back/up/down)
- Print preview via `QPrintPreviewDialog`, renders at ≤150 dpi using raw PIL bytes (bypasses Qt 256 MB limit)
- Internationalisation via `editor_lang/XX.json`

#### EDOF CLI (`edof_cli.py`)
- `info`, `objects`, `validate`, `export` sub-commands
- `--set key=value`, `--json-vars '{...}'`, `--all-pages`, `--dpi`, `--format`, `--color-space`

---

## Unreleased

Nothing yet.

---

> Versions 1.x and 2.x were internal development iterations and were never publicly released.
