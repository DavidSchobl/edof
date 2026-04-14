# Changelog

All notable changes to **edof** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) · Versioning: [SemVer](https://semver.org/)

---

## [3.0.1] – 2025-04-14

### Added
- `edof-editor` and `edof-cli` console scripts — available directly in PATH after `pip install edof[all]`
- Scripts moved inside the package (`edof/_apps/`) so they install correctly with pip
- `edof/editor_lang/en.json` moved inside the package — add `XX.json` to translate the editor to any language

### Fixed

**Printing**
- Print preview rendered blank pages — `pr.width()` / `pr.height()` return zero in `QPrintPreviewDialog`; fixed by using `painter.viewport()` for the drawable area
- `QPrinter.PageSize.A4` does not exist in PyQt6 — replaced with `QPageSize(QPageSize.PageSizeId.A4)`
- `QImageIOHandler: Rejecting image` (256 MB limit) — switched from BMP/PNG file encoding to raw PIL bytes (`img.tobytes()`) passed directly to `QImage` constructor, bypassing Qt's image allocation limit entirely
- Print preview renders at ≤ 150 dpi regardless of printer resolution — avoids out-of-memory on high-DPI printers

**Inline text editor**
- Keyboard input did nothing — `QGraphicsProxyWidget` event routing is unreliable; replaced with `QPlainTextEdit` as a direct child of the viewport widget
- Clicking inside the editor confirmed and closed it — click detection now checks viewport geometry before confirming
- Text appeared much smaller in editor than on canvas — font size formula corrected to `font_pt × RDPI × zoom / logical_dpi` which matches rendered output at all zoom levels and Windows DPI scaling settings (100 %, 125 %, 150 %)

**Auto-shrink / auto-fill**
- `find_fitting_size` loaded fonts at `int(pt)` pixels instead of `int(pt × dpi / 72)` pixels — measurements were inconsistent with actual rendering, causing wrong font size convergence
- Auto-fill could produce text that visually overflowed the box despite the function returning "fits"

**Canvas interaction**
- Rotation handle moved in the wrong direction — sign error in position formula (`−sin` → `+sin`)
- Resizing a rotated object caused it to drift — anchor (opposite corner/edge) now stays fixed in world space; mouse delta is projected onto the object's local axes
- Middle-mouse pan jumped on first move — now uses scroll bar delta relative to `pan_start`
- Toolbar and menu items missing — semicolon on `if key: ...; addAction()` made `addAction` conditional on the shortcut being set; all actions without a shortcut were silently dropped
- Cursor did not update correctly over empty canvas / locked objects / resize handles
- Layer ordering was `layer ± 1` — replaced with proper swap logic; Bring to Front / Send to Back move to absolute max/min

**Variables & objects**
- Setting a variable cleared the text box content — `get_resolved_text()` now falls back to `obj.text` when the variable value is empty, preserving the template placeholder text in the editor
- Hidden objects (`visible = False`) disappeared completely and could not be selected — ghost outlines (dashed red border) are now drawn for hidden objects and hit testing includes them

**Double-click actions**
- Double-click on `QRCode` now opens an inline data/URL editor overlay
- Double-click on `ImageBox` now opens a file picker to replace the source image

**QR codes**
- Non-black `fg_color` values produced invisible QR codes — fixed by always rendering in B&W and then colorising pixel-by-pixel; luminance detection (`r < 128`) now correctly identifies dark vs light pixels regardless of colour

---

## [3.0.0] – 2025-01-01

Initial public release.

### Library

**Document model**
- `Document`, `Page`, `ResourceStore`
- Object types: `TextBox`, `ImageBox`, `Shape` (rect / ellipse / polygon / arrow), `Line` (two explicit points in mm), `QRCode`, `Group`
- Common properties on every object: `id`, `name`, `variable`, `layer`, `locked`, `visible`, `editable`, `tags`, `opacity`, `shadow`
- `TextStyle` — font family, size, bold, italic, underline, strikethrough, color, background, letter spacing, line height, alignment (H + V), word wrap, overflow
- `auto_shrink` — `font_size` is the maximum; text shrinks to fit; never enlarges
- `auto_fill` — finds the largest font size that fills the box (grows and shrinks)
- `StrokeStyle`, `FillStyle`, `ShadowStyle` — full RGBA support
- `Transform` — position and size in mm, clockwise rotation in degrees, flip H/V; full chain API

**Variable / template system**
- `VariableStore` with type validation: `text`, `number`, `date`, `image`, `qr`, `url`, `bool`
- `doc.fill_variables({"name": "Jan"})` for batch fill
- `ImageBox` variable — value is a local file path or HTTP URL loaded at render time
- Non-destructive: unset variable falls back to `obj.text`

**Rendering**
- Pillow RGBA compositor; color spaces: RGB, RGBA, L, 1, CMYK; bit depths: 8 and 16
- Configurable DPI per page
- Rotation applied to the entire object surface (fill + border + text as one unit)

**Text engine**
- System font discovery on Windows, macOS and Linux
- Bold / italic variant resolution, font cache
- `list_system_fonts()`, text wrap, multi-line, vertical alignment

**File format (`.edof`)**
- ZIP archive: `manifest.json` + `document.json` + `resources/<uuid>`
- `EdofSerializer` — `save`, `load`, `to_bytes`, `from_bytes`, `peek`
- Forward and backward compatibility with non-fatal warnings

**Export & print**
- Bitmap: PNG, JPEG, TIFF, BMP; all-pages pattern; in-memory bytes
- PDF via reportlab (`pip install edof[pdf]`)
- Print: `os.startfile` (Windows), `lpr` / `lp` (macOS / Linux)

**QR codes**
- `pip install edof[qr]`; error correction L/M/Q/H; RGBA colors
- Standalone helpers in `edof.utils.qr`

**Command API**
- `edof.api.commands.execute(doc, {"cmd": "…"})` — string-based dispatch
- `CommandHistory` — snapshot-based undo/redo

**GUI widgets**
- `EdofTkCanvas` — Tkinter widget
- `EdofQtWidget` — PyQt6 QGraphicsView widget

### Applications

**EDOF Editor** (`edof-editor`) — requires `pip install edof[all]`
- Full desktop document editor built on PyQt6
- Canvas with selection, move, resize, rotation, zoom, pan
- Inline text editing, type-aware property panel, object list, page list
- Export PNG / JPEG / TIFF / PDF, print via system dialog, 60-step undo/redo

**EDOF CLI** (`edof-cli`)
- `info`, `objects`, `validate`, `export` sub-commands
- `--set key=value`, `--json-vars`, `--all-pages`, `--dpi`, `--format`, `--color-space`

---

> Versions 1.x and 2.x were internal development iterations not publicly released.
