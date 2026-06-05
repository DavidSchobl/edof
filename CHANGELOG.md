# Changelog

All notable changes to **edof** are documented here.
Format: Keep a Changelog (https://keepachangelog.com/en/1.0.0/)
Versioning: SemVer (https://semver.org/)

================================================================================

## [4.2.3] - 2026-06-05

### Changed
- **You now choose the default opener inside EDOF, not in the OS dialog.** The
  "File association (.edof)" dialog (in both the Editor and the Viewer) lets you
  pick whether double-clicking a `.edof` file opens the **Viewer** or the
  **Editor**, and registers that choice as the default. The other app stays
  available via right-click → Open With, and files keep the EDOF icon. The same
  choice is available on the command line: `edof-cli associate-files --app
  editor` (or `--app viewer`, the default). In 4.2.2 the OS prompted you to pick
  on first open; now the choice is made in the app.

================================================================================

## [4.2.2] - 2026-06-05

Bug-fix release with application/document icons.

### Fixed
- **Centre (and other) paragraph alignment is no longer lost on save or on
  Word export.** `TextRun` now serializes its `alignment`, and the body sync
  promotes run-carried alignment onto `Paragraph.alignment`, so the chosen
  alignment survives the `.edof` round-trip and is picked up by `export_docx`.
- **Ctrl+S / Ctrl+Shift+S now work while typing in the body editor.** They are
  routed to the window's Save / Save As; previously Ctrl+S did nothing inside
  the inline editor and Ctrl+Shift+S toggled strikethrough instead of Save As.
- **File association no longer errors with "cannot unpack NoneType".** The
  associate / unassociate functions now return `(ok, message)`.
- Removed an unsupported `outline` property from the stylesheet that caused
  repeated "Could not parse stylesheet of object ..." console warnings.

### Added
- **Icons.** The Editor and Viewer windows now use their own icons, `.edof`
  files show a document icon in Explorer, and the Viewer / Editor appear with
  their own icons under "Open with". Icons ship inside the package
  (`edof/_apps/assets/icons/`, `.ico` + `.png` + `.icns` for Windows / Linux /
  macOS).
- **File association** that registers the Viewer and the Editor as open-with
  choices and gives `.edof` files the EDOF icon. The Viewer gained a
  register / remove toggle and **File → Open in Editor (Ctrl+E)**.

================================================================================

## [4.2.1] - 2026-06-04

Follow-up to 4.2.0 (which was already published to PyPI, where versions are
immutable, so these ship in a new version).

### Fixed
- `edof._apps.viewer` now imports without PyQt6 installed (it falls back to a
  harmless base class and `main()` prints an install hint), so the CI test
  suite passes on the lean `[dev,qr]` install instead of erroring on import.

### Added
- Ko-fi funding links (`https://ko-fi.com/davidschobl`): `.github/FUNDING.yml`,
  the `Funding` project URL, the README, and the in-app "Support the
  developer" action and About dialogs (alongside GitHub Sponsors).

### Packaging
- `deploy-edof.bat` / `deploy-edof.sh` default the deploy clone to a directory
  next to the script (the unzipped package) instead of a hard-coded developer
  path.

================================================================================

## [4.2.0] - 2026-06-04

First public release since 4.0.3. It folds in a long line of editor and
format work developed in between, so the highlights below cover everything
new since 4.0.3.

### Added
- **Word (.docx) import and export** (optional, needs `python-docx`:
  `pip install edof[docx]`). New top-level API `edof.export_docx(doc, path)`
  and `edof.import_docx(path, return_report=False)`, plus **File → Import /
  Export Word (.docx)…** in the desktop editor.
  - Export writes the document body flow: runs with bold / italic / underline
    / strikethrough, font family and size, run colour, paragraph alignment,
    page size and margins, page-break-before, single-level lists, and a line
    height matched **exactly** to EDOF's so Word paginates the same way the
    editor does.
  - Import builds a document-mode file and produces a compatibility report.
    It never silently drops content: tables, images, drawings, text boxes,
    equations and embedded objects are detected and the user is advised
    against importing when such content is significant; headers/footers,
    footnotes and comments are reported as dropped. See
    `docs/reference/11-docx.md`.
- **Unified document-wide undo/redo.** A single timeline now covers both
  body-text editing and object operations (move / add / delete / style).
  Body edits coalesce into one step per typing burst and are flushed before
  any undo/redo or object change, so Ctrl+Z/Ctrl+Y behave consistently
  everywhere and never split between two histories.
- **Document mode** maturity: continuous multi-page text flow with automatic
  pagination, hard page breaks (Ctrl+Enter), per-paragraph keep/break
  controls, and per-run/paragraph line spacing.
- Complete generated **API reference** (`docs/reference/API.md`) and a
  MkDocs-Material documentation site published to GitHub Pages.
- **Read-only Viewer** (`edof-viewer`) and OS-level **file associations** for
  `.edof` (open by double-click; register from the editor, the viewer, or
  `edof-cli associate-files`).
- **Document mode**: a continuous, multi-page text flow you can edit like a
  word processor, alongside the free-form object canvas.
- **Layer effects** (Photoshop-style), **per-side padding** on text boxes, and
  a **bezier path tool**.
- **Table editor UI** (tables remain experimental / a work in progress).

### Changed
- **Debug logging is now opt-in.** It is disabled by default and only writes a
  log when `EDOF_DEBUG=1` is set or it is enabled programmatically;
  `EDOF_DEBUG_PATH` overrides the location. Releases no longer create
  `edof_debug.log` in the home directory during normal use.
- Line-height model on export uses an exact point value (not Word's "multiple"
  rule), eliminating the ~15 % taller spacing that pushed extra lines onto
  later pages.

### Fixed
- Pagination: hard page breaks and empty break-pages survive re-pagination;
  the caret no longer drops below the bottom margin while typing at the end of
  a full page; the empty-document caret respects paragraph alignment;
  continuing pages no longer render a spurious trailing cursor line.
- Close / New / Open now prompt to save unsaved body edits, including edits
  made on a single line that previously failed to mark the document modified.
- New documents no longer capture the editor's placeholder hint into undo
  history, so undoing to the very start leaves a clean empty document.

### Packaging
- Clean release tree (no build/debug helpers or caches); restored the
  `.github/workflows/publish.yml` Trusted-Publishing (OIDC) workflow; added a
  `Funding` project URL and a `.gitignore`.

================================================================================

## [4.0.3] - 2026-05-04

The "editor catches up with the API" release. Substantial editor improvements,
PDF import bug fixes, RTF import/export, and a long list of polish.
No format changes — files saved by 4.0.3 are wire-compatible with 4.0.2.

================================================================================
FIXED — PDF import: vector paths had wrong bounding box
================================================================================

Previously, vector paths (lines, curves, rectangles) imported from PDF were
created with a transform spanning the entire page, while the path coordinates
themselves were absolute. The renderer worked, but the editor couldn't select
or move them — the bounding box covered the whole page.

In 4.0.3:
- `_extract_paths()` now computes the actual bbox of each path
- Path coordinates are stored as local (relative to transform.x/y)
- The renderer auto-detects local vs absolute coords for backward compatibility
  with documents created before this fix

Also added new flags to `import_pdf()`:
- `extract_paths` (default True): convert PDF vector paths to Shape objects
- `extract_images` (default True): extract embedded raster images

These flags were promised in the 4.0.2 docs but were not actually wired up.

================================================================================
FIXED — Image scale X breaks position
================================================================================

When resizing an ImageBox by dragging an edge handle (only one axis), the
opposite anchor was not held fixed, causing the image to "jump" sideways. The
resize now correctly keeps the opposite corner / edge as the anchor regardless
of which handle you drag.

================================================================================
FIXED — Subpixel text rendering disappears at low zoom
================================================================================

When zoomed below 100%, thin text strokes on the canvas would render at
sub-pixel widths and disappear into anti-aliasing — the text became unreadable.

In 4.0.3, the editor canvas renders at higher DPI when zoomed out (up to 2×)
and downscales with LANCZOS, so thin strokes survive. This affects only the
canvas preview; export quality is unchanged.

================================================================================
CHANGED — Modifier semantics for resize/rotation/move
================================================================================

The editor's modifier behaviors were inconsistent and didn't match user
expectations. Revised in 4.0.3:

- **Ctrl** while dragging — bypass ALL snapping (grid, alignment guides, margins).
  This is the primary "give me precise control" modifier.
- **Alt** while dragging — bypass snapping (legacy alias for Ctrl, kept for
  compatibility).
- **Shift on resize** — toggles uniform/non-uniform scale:
  - For ImageBox: default is uniform (preserve aspect ratio); Shift toggles
    to non-uniform.
  - For other objects: default is non-uniform; Shift forces uniform.
- **Shift on rotation** — snap to 15° increments.

This means typical workflows do the right thing automatically:
- Drag image corner → preserves aspect ratio
- Drag image corner with Shift → free distortion if you really want it
- Drag rectangle corner → free resize
- Drag rectangle corner with Shift → preserve aspect ratio

================================================================================
ADDED — Page margins (per-document) with snap support
================================================================================

Documents now have an optional `doc.margins` field — a 4-tuple of
(top, right, bottom, left) in mm. Margins are saved/loaded with the document.

In the editor:
- View menu → "Use Page Margins (snap)" toggle
- View menu → "Set Margins…" dialog
- When enabled, dragged objects snap their edges to the margin lines

Margins are editor-only — they're not enforced at render or export.

================================================================================
ADDED — Editor: Insert Table dialog
================================================================================

Tables existed in the API since 4.0.0 but had no UI to create them. Insert
Table dialog now offers:
- Rows × columns
- Width × height in mm
- Optional header (first row in bold + accent color)
- Optional alternating row colors

================================================================================
ADDED — Editor: Path drawing tool
================================================================================

A new toolbar button (✎) puts the canvas in path-drawing mode:
- Click adds a point
- Double-click or Enter finishes the path
- Esc cancels
- Snap-to-grid is honored if enabled

The result is a `Shape(shape_type="path")` with proper local coordinates and
correct bounding box.

================================================================================
ADDED — Editor: Object panel rename, drag-and-drop, context menu
================================================================================

The left-side object list panel was bare-bones. Now:

- **F2** or **double-click** an item to rename the object inline
- **Drag** items up/down to reorder layers (front-to-back ordering)
- **Right-click** an item for: Rename, Bring to Front, Bring Forward,
  Send Backward, Send to Back, Show/Hide, Lock/Unlock, Duplicate, Delete

Also fixed a dark-theme rendering bug where alternating row colors were too
bright; the panel now uses a quieter selected-state highlight.

================================================================================
ADDED — Editor: Properties panel — Advanced section
================================================================================

A new "Advanced" group on the right-side properties panel exposes API-level
features that previously had no UI:

- **Show if** (`visible_if` expression) — conditional visibility
- **Lock level** dropdown (none / fill / edit / design / admin) — for
  permission-aware editing of encrypted templates
- **Lock text** checkbox — prevents changes to text content even when the
  object itself is editable
- **Blend mode** dropdown (normal / multiply / screen / darken / lighten / overlay)
- **Shape type** changer — convert rect ↔ ellipse ↔ polygon ↔ path on the fly
- **Drop shadow** — toggle + offset X/Y + blur

================================================================================
ADDED — Editor: Help → Keyboard Shortcuts dialog
================================================================================

F1 now opens a comprehensive reference dialog covering File, Edit, View,
Insert, Document, Selection, Modifier keys (with the new v4.0.3 semantics),
Object panel actions, and the Path tool.

Help → About also added.

================================================================================
ADDED — Editor: PDF Export dialog with Vector / Raster choice
================================================================================

The PDF export menu item now opens a dialog explaining the trade-off:
- **Vector PDF** (default): pure-Python writer, smaller files, selectable text,
  limited to Standard 14 PDF fonts
- **Raster PDF**: rendered as bitmap, larger files, no text selection,
  supports any TTF font, requires reportlab

Plus a DPI control for raster mode.

================================================================================
ADDED — Editor: Resizable docks + persistence
================================================================================

The left and right panels were previously fixed-width. Now:
- Both docks are user-resizable
- Both are dockable (movable, can detach to floating)
- Geometry, snap-to-grid state, alignment guides state, margin state, and
  full window/dock layout persist across sessions (via `QSettings`)
- View menu → "Reset Panel Layout" to restore defaults

================================================================================
ADDED — Editor: Toolbar tooltips
================================================================================

Every toolbar button now has a descriptive tooltip + status-bar message +
keyboard shortcut hint. Previously hovering "💾" gave no explanation; now it
shows "Save (Ctrl+S)".

================================================================================
ADDED — RTF import / export
================================================================================

A new utility module (`edof.utils.rtf`) provides best-effort interop with
Rich Text Format documents:

- `edof.import_rtf(path)` reads an RTF file into an EDOF Document. Each
  non-empty paragraph becomes a TextBox; runs preserve bold/italic/underline/
  size/color. Tables, images, lists, fields are not supported.
- `doc.export_rtf(path)` writes an EDOF document as flat RTF — paragraphs in
  vertical order, runs with formatting. Other object types (shapes, images,
  tables) are not exported.

In the editor:
- File → Import RTF…
- File → Export RTF…

================================================================================
DOCUMENTATION
================================================================================

- Documentation site at https://davidschobl.github.io/edof/ updated for 4.0.3
- Editor reference page (`docs/reference/08-editor.md`) updated with
  v4.0.3 modifier semantics, margins, panel persistence
- New "Path tool" section in editor docs

================================================================================
TESTS
================================================================================

138/138 tests passing (vs 112 in 4.0.2):
- 36 v3.1 (legacy)
- 36 v4.0
- 21 v4.0.1
- 19 v4.0.2
- 26 v4.0.3 (new)

================================================================================

## [4.0.2] - 2026-05-04

Polish, bug fixes, and CLI completeness release. No format changes — files saved by 4.0.2 are bit-identical to 4.0.1 when no 4.0.2-only behaviors are exercised.

================================================================================
FIXED — Variable `{name}` placeholder substitution at render time
================================================================================

Previously, `{name}` placeholders inside `obj.text` were only substituted by `repeat_objects()`. Direct rendering (`doc.export_pdf()`, `doc.export_bitmap()`, `doc.export_svg()`) left placeholders as literal text. Documentation and examples in 4.0.1 promised this worked — now it actually does.

Behaviour:
- `obj.text = "Hello {name}!"` with `doc.set_variable("name", "Alice")` now renders as "Hello Alice!".
- Multiple placeholders supported: `"{greeting} {name}"`.
- Undefined variable names stay as literal `{name}` (graceful fallback, no exception).
- Table cell substitution (which already worked) is unchanged.
- The previous mechanism of binding a textbox to a single variable via `obj.variable = "name"` continues to work and takes priority.

================================================================================
FIXED — Editor: snap-to-grid during resize and rotation
================================================================================

When **Snap to Grid** (Ctrl+G) was enabled in 4.0.1, snapping only applied while moving objects. Resize handles (non-uniform scale corner / edge dragging) and rotation handles ignored the setting.

In 4.0.2:
- **Resize**: when grid snap is active and the object is non-rotated, the mouse position is snapped to the 5mm grid before computing the new size, so resize ends on grid increments. Rotated objects skip this (snapping along rotated axes is unintuitive). Hold **Alt** to bypass.
- **Rotation**: when grid snap is active, rotation now snaps to 15° increments by default (the same behaviour you previously got only by holding Shift). Hold **Alt** to bypass.

================================================================================
ADDED — Editor settings persistence (Windows / Linux / macOS)
================================================================================

The editor now uses `QSettings` to remember preferences across sessions:

- Window geometry (size + position)
- Snap-to-grid on/off
- Show alignment guides on/off
- Recent files list (up to 10)

Settings live in standard system locations (registry on Windows, `~/.config/edof/editor.conf` on Linux, `~/Library/Preferences/edof.plist` on macOS). Delete to reset.

================================================================================
ADDED — Validate enhancements
================================================================================

`doc.validate()` now also reports:
- **Duplicate object IDs** anywhere in the document (recursing into groups). Useful when programmatically copying objects without resetting `obj.id`.
- **Objects positioned entirely off-page** (i.e. their bounding box has no overlap with the page). Partially-off objects (overlapping the edge) are NOT flagged — that's a deliberate design choice (e.g. bleed marks).

These join the existing checks for missing-resource references, undefined variable references, and unset required variables. The function still returns an empty list when the document is fully valid.

================================================================================
ADDED — CLI: 6 new subcommands + password support on existing ones
================================================================================

The CLI now exposes the rest of the public API. New subcommands:

- `edof-cli batch <template> <csv> -o <pattern>` — generate one output file per CSV row, auto-filling variables. Supports `{n}`, `{column}` in output pattern; `--start`, `--limit`, `--continue-on-error`. Accepts PDF/PNG/JPEG/SVG output formats.
- `edof-cli import <pdf> -o <edof>` — convert a PDF to an editable .edof (best-effort PDF reconstruction, requires `[pdf]` extra). `--no-tables`, `--no-images`, `--no-paths`, `--heading-threshold` flags.
- `edof-cli convert <input> -o <output>` — migrate any legacy archive to current v4 format.
- `edof-cli to-v3 <input> -o <output>` — save as v3-compatible (lossy: tables flatten, runs collapse, paths sample, gradients average).
- `edof-cli set-password <input> --level admin --password <pwd>` — manage encryption from the command line. Supports `--remove`, `--clear-all`, `--current-password`, `--recovery-key`. Recovery key is shown once on first password.
- `edof-cli unlock-render <encrypted> <out.pdf> --password <pwd>` — decrypt + render in one step. The decrypted document is never written to disk.

Existing commands (`info`, `objects`, `validate`, `export`) gained:
- `--password` / `--recovery-key` flags for working with encrypted templates.
- `--vector` / `--raster` flags on PDF export.
- SVG output support on `export` (auto-detected from `.svg` extension or via `--format svg`).

`info` on an encrypted file without a password now shows public manifest data (encryption mode, permission levels, KDF parameters) instead of failing.

Exit codes are now consistent with the documentation:
- `0` success
- `1` usage error
- `2` file not found
- `3` encryption error (wrong password / missing crypto extra)
- `4` validation failure
- `5` unknown internal error

================================================================================
DOCUMENTATION
================================================================================

Comprehensive documentation added under `docs/`. Covers every public symbol with signatures, examples, and conventions. Hosted on GitHub Pages at https://davidschobl.github.io/edof/ (after the deploy below). Includes:

- Installation, quick start, and conventions
- Full API reference (Document, Page, all object types, styles, variables, export, import, encryption, editor, CLI, helpers)
- Five cookbook recipes (certificate, invoice, batch PDF, encrypted template, PDF import)
- Advanced topics (file format internals, extending, troubleshooting)

`pyproject.toml` now declares `[project.urls]` (Documentation, Repository, Changelog, Issues), which appear on the PyPI project page.

The README badges and content link to the documentation site.

================================================================================

## [4.0.1] - 2026-05-04

Maintenance + protection release. Adds AES-256 encryption, multi-level password protection, real (not XOR) document security, plus editor enhancements.

================================================================================
ADDED — Encryption & multi-level password protection
================================================================================

This is the headline feature for 4.0.1.

By default, documents remain plain (no encryption, no friction — same as 4.0.0). When an admin password is set, the document switches to encrypted mode on the next save. Encryption requires the optional `cryptography` extra: `pip install edof[crypto]`.

**Cryptography**
- AES-256-GCM authenticated encryption for content
- PBKDF2-SHA256 key derivation with 600,000 iterations
- 16-byte random salt per slot, 12-byte random nonce per ciphertext
- GCM authentication tag detects tampering on load
- Real protection: no XOR, no obfuscation theatre

**Permission levels (hierarchical)**
- `view`   — render, print, export. No modifications.
- `fill`   — view + change variable values (template filling). No structural / textual edits.
- `edit`   — fill + change object .text content (and rich-text run text segments).
- `design` — edit + change styles, layout, add / remove objects and pages.
- `admin`  — design + manage passwords, recovery keys, lock_level overrides.

Higher levels imply all lower levels.

**Multi-slot key wrapping**
- Each password independently wraps the same 32-byte content key.
- Setting an `admin` password also generates a 24-character alphanumeric recovery key.
- The recovery key is shown exactly once at first password setup; it cannot be retrieved later.
- Recovery key always grants ADMIN; designed for owner self-recovery.
- Changing one password does not re-encrypt the bulk payload (just rewraps that one slot).

**Encryption modes**
- `full`    — entire document content (and resources) encrypted as a single AES blob inside the ZIP. Manifest leaks only KDF parameters and slot count. Title, page count, all metadata are hidden.
- `partial` — only sensitive content fields encrypted (text content, rich-text runs, image data, QR data, table cell text). Structure (positions, sizes, fonts, alignment, page count, title) remains visible. Useful for "design template" sharing where layout is public but content is private.
- `none`    — current 4.0 behaviour, plain ZIP, no encryption.

In partial mode without a password, the document loads with redacted content (a placeholder character `█` replaces text). The user can see the layout and structure but no content. With a password, the full content is decrypted and accessible.

**Per-object locks (independent of doc-level encryption)**
- `obj.lock_level = "design"` — modifying this object requires at least the named permission, regardless of the user's general permission level.
- `obj.lock_text = True` — hard text lock; even ADMIN cannot edit `.text` or `.runs` until clearing this flag (which itself requires ADMIN).
- `obj.can_modify(doc) -> bool` — programmatic check.
- `obj.can_modify_text(doc) -> bool` — also honors `lock_text`.

**Document API**
```python
rk = doc.set_password("admin", "mySecret123")
doc.set_password("design", "designerPwd")
doc.set_password("edit",   "editorPwd")
doc.set_password("fill",   "templateFiller")

doc.encryption_mode = "partial"   # or "full" (default after first password)
doc.save("template.edof")

doc = edof.load("template.edof", password="editorPwd")
print(doc.permission_level)   # Permission.EDIT
doc.can(edof.crypto.DESIGN)   # False
doc.require(edof.crypto.EDIT) # OK, no exception

doc.change_password("edit", "old", "new")   # rotate without re-encrypting payload
doc.remove_password("fill")                 # requires ADMIN
doc.clear_all_protection()                  # requires ADMIN

doc = edof.load("template.edof", recovery_key="ABCD-EFGH-...")  # recovers as ADMIN
```

**Editor UI**
- File → Open: detects encrypted files automatically and prompts for password / recovery key. Three-strikes-and-out; Cancel on any prompt aborts the open.
- Document → Unlock for editing… (Ctrl+Shift+L): shows password prompt when an encrypted document was opened with insufficient privileges, then displays a dialog listing exactly what the granted level can and cannot do.
- Document → Protection… : full management UI for setting / changing / removing passwords and switching between full and partial encryption modes. Confirmation dialog before plain → encrypted upgrade.
- Document → Re-lock: forgets the cached content key for the session.
- Status bar shows protection state at all times: 🔓 Plain / 🔒 Locked / 🔓 Unlocked: <level>.
- Permission-aware action gating: pressing a button (Add TextBox, Delete, Duplicate, etc.) without sufficient permission shows a clear dialog explaining what level is needed.
- Canvas drag respects `obj.can_modify()`; locked objects cannot be moved.
- Recovery key dialog uses fixed-width font, clipboard copy button, "I have saved this key" confirmation gate.

**EDOF 2 → 4 password upgrade flow**
- When opening a legacy EDOF 2 archive that had an XOR-obfuscated password, the editor offers to set up real AES-256 encryption with a clear explanation of why the old password was insecure.

================================================================================
ADDED — Editor improvements (carry-over completed in 4.0.1)
================================================================================

- Snap-to-grid: View → Snap to Grid (Ctrl+G), 5 mm grid, hold Alt to bypass.
- Alignment guides: View → Show Alignment Guides; magnetic snap to other objects' edges and centers during drag, threshold 1.5 mm.
- Multi-select: Ctrl+click adds / removes from selection; group drag moves all selected objects together; group delete removes them all.
- Cursor position in mm in the status bar (live during mouse move).
- Find & Replace dialog (Ctrl+F): searches all TextBoxes on all pages, with case-sensitive and regex options.
- Gradient Editor dialog: visual stop list, add/remove/recolor stops, switch between linear and radial.
- Template gallery (File → New from Template…): Blank A4 P/L, Business Card, Certificate, Invoice with Table.
- File → Save as v3 (downgrade)…: produces a v3-compatible .edof with all v4-only features flattened.
- File → Import PDF…
- File → Export SVG…

================================================================================
ADDED — `doc.export_3x(path)` API
================================================================================

Programmatic API for downgrading a v4 document to v3 format.

Best-effort lossy conversion:
- Tables flattened to a Group of TextBoxes plus line shapes for borders.
- Rich-text runs collapsed to plain `obj.text` (formatting lost).
- Path shapes rasterised to polygon shapes (Beziers sampled at 12 segments per curve).
- Gradients replaced with the average color of their stops.
- `visible_if` evaluated once at export time and baked into `.visible`.
- `blend_mode` reset to `"normal"`.

The original document is not mutated; a deep copy is made first. Manifest in the output explicitly says `format_version: 3.1.0` so v3 readers don't show a "newer version" warning.

```python
doc.export_3x("for_v3_users.edof")
```

================================================================================
ADDED — Real EDOF 2 import (`edof/utils/legacy_v2.py`)
================================================================================

Replaces the placeholder scaffolding from 4.0.0 with a complete migration path based on the actual EDOF 2 schema (versions ≤ 2.2):

- ZIP with `data.json` at root (no manifest).
- Float `version` field (e.g. `2.2`).
- ARGB hex colors `#AARRGGBB` correctly converted to v4 RGB tuples (alpha dropped, RGB preserved — alpha is not part of TextStyle.color in v4).
- `font_weight ≥ 600` → `bold = True`.
- `max_font_size_pt > font_point_size` → `auto_shrink = True`, `font_size = max`.
- `h_align` / `v_align` mapped to v4 `alignment` / `vertical_align`.
- Embedded images extracted from the `images/` directory and added as v4 resources with detected MIME type.
- `z_value` → `layer` (preserves stacking order).
- `allow_non_uniform_scale` → `fit_mode = "stretch"` or `"contain"`.
- `edit_mode` other than "all" → informational warning in `doc.errors`.
- `edit_password_xor` → ignored, with explicit warning that XOR provided no real security; editor offers to set up real AES encryption.

Auto-detection: `edof.load(path)` checks for v2 markers (`data.json` at root, version < 3.0, no `manifest.json`) and routes to the legacy loader transparently.

================================================================================
ADDED — Optional dependency
================================================================================

```toml
[project.optional-dependencies]
crypto = ["cryptography>=42.0"]
all    = [..., "cryptography>=42.0"]
```

Encryption is opt-in. Without `cryptography` installed, all plain-mode functionality continues to work; only `set_password()` and friends raise `EdofCryptoUnavailable` with installation instructions.

================================================================================
FILE FORMAT
================================================================================

- Format version bumped to 4.0.1.
- New optional `protection` block in the manifest:
```json
{
  "protection": {
    "mode": "full" | "partial",
    "format": "edof-aes-256-gcm-v1",
    "slots": [
      {"permission": "fill", "kdf": "pbkdf2-sha256", "iterations": 600000,
       "salt": "<base64>", "wrapped_key": "<base64>"},
      ...
    ]
  }
}
```
- New file inside encrypted archives: `encrypted_payload.bin` (AES-GCM ciphertext: 12 B nonce || 16 B GCM tag || ciphertext).
- 4.0.0 files load unchanged (mode defaults to "none").
- Plain 4.0.1 files are bit-identical to 4.0.0 format.

================================================================================
SECURITY MODEL
================================================================================

What encryption protects against:
- Reading content without a password
- Detection of any tampering with the ciphertext
- Brute-forcing weak passwords (PBKDF2 with 600k iterations is intentionally slow)

What it does NOT protect against:
- A user with sufficient access running their own decryption code (they have the password)
- Side-channel attacks on the host (memory dumps, keyloggers, etc.)
- Loss of all passwords AND the recovery key — the document is mathematically unrecoverable
- A malicious EDOF library — verify the source

Recovery key is treated as an additional ADMIN-level slot keyed by the recovery string. If you lose it, the only way to regenerate one is to remove all passwords and re-protect the document (which requires the admin password).

================================================================================
FIXED
================================================================================

- `EdofSerializer` now reads `FORMAT_VERSION_STR` dynamically through the version module, so `export_3x()` can override it for the duration of a single save without leaking into other operations.
- Editor `_gradient_editor` method properly registered (it was lost during 4.0.0 development).

================================================================================



Major release: rich text, vector graphics, custom PDF writer, PDF import, formatted tables, and legacy EDOF 2 read support.
This is a major version bump because the renderer, PDF subsystem, and Shape model received fundamental architectural changes. File-format compatibility is preserved - 3.x files load with automatic migration, and EDOF 2 files (legacy unreleased format) are now also readable in best-effort mode.

================================================================================
ADDED - Rich text & formatting
================================================================================

Rich text runs in TextBox
- New TextRun dataclass: text segment with its own font_family, font_size, bold, italic, underline, strikethrough, color, background
- TextBox.runs: list[TextRun] - when non-empty, replaces plain text + style rendering
- Run-based layout engine: per-run measurement, wrap across run boundaries, mixed font sizes on the same line
- Auto-shrink / auto-fill with runs: global scale factor s found by binary search and applied to all font_size values, preserving relative size ratios between runs
- Per-run underline, strikethrough, background highlight rendering with correct horizontal extents
- Backwards compatible: runs == [] keeps the original plain-text behaviour

Formatted tables
- New Table object type (separate from Group)
- TableCell with full styling: own TextStyle or runs[] for rich text, bg_color (RGBA), per-side border (top/right/bottom/left) with own color and width, padding, colspan, rowspan
- Per-row and per-column custom widths/heights; auto-distribution if not specified
- Cell content clipped at cell boundary
- Editor: click to select cell, double-click to edit, right-click for cell formatting menu

================================================================================
ADDED - Vector graphics
================================================================================

Bezier path Shape
- New shape type "path" - arbitrary vector path with line segments and Bezier curves
- Shape.path_data: list[PathCommand] - SVG-style commands: M (moveto), L (lineto), C (cubic Bezier), Q (quadratic Bezier), Z (close)
- Pixel-correct rendering via Pillow ImageDraw.line() for segments + de Casteljau subdivision for curves
- Direct SVG path string parsing: Shape.from_svg_path("M 10 10 L 50 50 C ...")

Linear and radial gradients
- FillStyle.gradient - replaces solid fill with multi-stop gradient
- Linear: gradient_type="linear" with gradient_angle (deg) and gradient_stops=[(offset, rgba), ...]
- Radial: gradient_type="radial" with gradient_center=(cx, cy) and gradient_radius
- Renderer creates per-object gradient mask; full RGBA interpolation between stops

Path-based stroke styling
- StrokeStyle.dash_pattern - list of mm values, e.g. [3, 2] for dashed line
- StrokeStyle.cap - "butt", "round", "square"
- StrokeStyle.join - "miter", "round", "bevel"

Blend modes
- obj.blend_mode - "normal", "multiply", "screen", "overlay", "darken", "lighten"
- Compositing via Pillow with custom pixel ops

================================================================================
ADDED - Custom vector PDF writer
================================================================================

Pure-Python PDF 1.7 writer (no reportlab dependency)
- Native implementation of cross-reference table, object catalog, page tree, content streams
- Standard 14 PDF fonts (Helvetica, Times, Courier with bold/italic) - zero embedding for these
- TTF embedding for custom fonts (Type0/CID font + ToUnicode CMap + cidset)
- System font name mapping (Arial -> Helvetica, Times New Roman -> Times-Roman, ...)
- WinAnsiEncoding for Latin-1 incl. Czech diacritics; UTF-16BE for CID fonts
- Vector text - searchable, copyable, selectable in PDF readers
- Vector shapes (rect, ellipse, line, polygon, Bezier path)
- Linear / radial gradient as PDF shading patterns
- Images as XObject with FlateDecode (PNG-style) or DCTDecode (JPEG passthrough)
- Multi-page support with shared resources
- PDF metadata (title, author, subject, keywords, creator) via Info dictionary
- Vector PDFs typically 5-15x smaller than rasterised PDFs
- Default mode is vector; raster fallback: doc.export_pdf(path, vector=False)

================================================================================
ADDED - PDF -> EDOF import
================================================================================

edof.import_pdf(path) -> Document

Bidirectional PDF support - open existing PDFs as editable EDOF documents.

Text reconstruction
- Per-page text spans extracted via pymupdf with bbox, font, size, color, bold/italic flags
- Block clustering algorithm detects formatted text blocks:
    * Same font + size (5% tolerance) -> grouped together
    * Vertical gap <= font_size x 1.5 -> same paragraph
    * Similar X-alignment (left, center, justified) -> same column
    * Line-spacing tolerance - variable line gaps within a paragraph are merged when consistent
    * Indented paragraphs detected by first-line offset relative to subsequent lines
    * Hanging indents for bulleted lists detected separately
- Heading detection: spans with significantly larger font size than median -> standalone TextBox marked as heading
- List detection: spans starting with bullet/dash/number prefixes -> list item TextBoxes with proper indent
- Mixed inline formatting within a block -> produces a rich-text TextBox with runs[]

Font handling
- Standard 14 PDF fonts -> mapped via the alias system, no embedding needed
- Fully embedded TrueType/OpenType -> font bytes extracted directly into .edof resources
- Subsetted fonts ("AAAAAA+Arial" prefix), most common case:
    * First tries to find the full font locally via the alias system -> uses local copy (full editing capability)
    * If not found, embeds the subset anyway -> existing text renders correctly, but adding new characters to that font will warn in doc.errors
    * Both cases logged in doc.errors with the substitution decision
- Type3 fonts (vector glyphs) -> individual glyphs converted to Shape path objects when extractable; otherwise replaced with the closest local font and logged
- CID fonts (Asian scripts) -> handled transparently by pymupdf, embedded as full TTFs

Image extraction
- Embedded raster images extracted with original encoding (PNG / JPEG)
- Pixel position and clip preserved
- One ImageBox per detected image

Vector graphics
- PDF stroked/filled paths converted to Shape objects with "path" type
- Color and stroke properties preserved
- Bezier curves preserved as C commands (no rasterization)

Tables (heuristic)
- Optional pdfplumber dependency: detects tabular grids from horizontal/vertical lines + clustered text spans
- Detected tables become Table objects with TableCells preserving cell content and basic styling
- When detection is uncertain, falls back to individual TextBoxes (logged in doc.errors)

API:
    doc = edof.import_pdf("template.pdf",
                          detect_tables=True,
                          merge_paragraphs=True,
                          heading_threshold=1.4)   # font_size > median * 1.4

CLI:
    edof-cli import template.pdf -o template.edof --detect-tables

Editor: File -> Import PDF...

================================================================================
ADDED - Legacy EDOF 2 read support
================================================================================

EDOF 2 was an internal pre-release format that was never publicly distributed. It had architectural problems that led to the redesign in EDOF 3. To support users who have legacy EDOF 2 archives, the loader now performs a best-effort migration.

- edof.load(path) auto-detects the file format (EDOF 4, EDOF 3, or EDOF 2)
- EDOF 2 files identified by manifest version field or legacy structure markers
- Best-effort migration:
    * Object types mapped to EDOF 4 equivalents where possible
    * Style properties translated (legacy enum values -> string constants)
    * Embedded resources preserved
    * Variable system mapped to new VariableStore (legacy unstructured names normalised)
- Migration warnings recorded in doc.errors (does not abort)
- One-way conversion only: EDOF 2 -> EDOF 4. The output cannot be saved back to EDOF 2.
- CLI: edof-cli convert legacy.edof -o new.edof
- After conversion, save as a current EDOF file: doc.save("new.edof")

================================================================================
ADDED - SVG export
================================================================================

- doc.export_svg(path, page=0) - one SVG file per page
- Text rendered as <text> elements (searchable in browsers, indexable, copyable)
- Shapes as native SVG: <rect>, <ellipse>, <line>, <polygon>, <path> (with full Bezier)
- Gradients rendered as <linearGradient> / <radialGradient> definitions
- Images embedded as base64 data URIs (PNG / JPEG)
- Custom fonts embedded via @font-face with data URI

================================================================================
ADDED - Templating
================================================================================

Conditional visibility
- obj.visible_if = "score > 90" - Python-style expression evaluated against document variables at render time
- Safe evaluator: literals, comparisons (<, <=, ==, !=, >=, >), arithmetic, and/or/not, in/not in; no function calls, no imports, no attribute access
- Syntax errors recorded in doc.errors without aborting render
- Editor displays a small (i) badge on objects with conditions

Repeating sections
- page.repeat_objects(template_objs, data_list, gap=2.0) - duplicates a group of objects for each row of data_list
- Variable substitution per row: {column_name} placeholders inside text, runs[].text, qrcode.data, imagebox.variable are replaced with row values
- Auto-pagination: when a row would overflow the page, a new page is created automatically with the same dimensions
- Page-level header/footer objects can be marked repeat_on_pages=True so they appear on every generated page

================================================================================
ADDED - High-level API helpers
================================================================================

Configurable text padding
- TextStyle.padding (mm) - default 1 mm (was hardcoded 2 mm); set to 0 for edge-to-edge text
- Small textboxes (< 6 mm tall) are now usable

Font fallback & cross-platform aliases
- load_font_safe() emits EdofMissingFontWarning instead of silently using a bitmap fallback
- Fallback chain: DejaVu Sans -> Liberation Sans -> FreeSans
- Cross-platform aliases for Arial, Helvetica, Times New Roman, Courier New, Calibri, Cambria, Verdana, Tahoma, Trebuchet MS, Georgia, Segoe UI, Comic Sans MS, Impact

High-level widgets
- page.add_card(x, y, w, h, title, body, accent_color) - accent header + title + body
- page.add_metric(x, y, w, h, label, value, subtitle, value_color) - large-value tile
- page.add_table(x, y, w, rows, header, alternating, row_height) - quick table (now uses new Table object internally)
- page.add_kv_list(x, y, w, items, key_width_frac) - key-value list

Layout helpers
- page.row(y, gap, height) -> _RowContext with add_textbox, add_image, add_shape, skip, next_x
- page.column(x, gap, width) -> _ColumnContext with add_textbox, add_textbox_auto, add_image, add_shape, skip, next_y

Auto-height textbox
- page.add_textbox_auto(x, y, w, text, min_height, **style) - height computed from content
- edof.measure_text_height(text, style, width_mm, dpi) - standalone helper

================================================================================
ADDED - Editor
================================================================================

Existing 3.x features retained
- edof-editor and edof-cli console scripts
- edof/editor_lang/en.json for translations (add XX.json for other languages)
- Async rendering, type-aware property panel, object list panel
- Inline text editor with WYSIWYG sizing across all zoom levels and Windows DPI scaling
- Double-click QR / Image actions
- 60-step undo/redo

New in 4.0
- Rich text inline editor: double-click a TextBox with runs opens a formatting toolbar (bold, italic, underline, color, font, size) for selected text
- Cell editor for Table objects: click cell to select, double-click to edit content, right-click for cell formatting
- Path drawing tool: draw arbitrary Bezier paths; convert any shape to path for editing
- Cursor position in mm in status bar (live update during mouse move)
- Find & Replace dialog (Ctrl+F): searches all TextBoxes on all pages, optional case-sensitive, regex, whole-word
- Snap-to-grid: toggleable grid snap during drag, configurable spacing
- Alignment guides: magnetic alignment to other objects' edges/centres while dragging
- Multi-select: Ctrl+click adds to selection, lasso drag-rectangle, group move + batch property edit
- Template gallery: File -> New from Template (invoice, certificate, business card, A4 label sheet)
- CSV batch export: File -> Batch Fill from CSV...
- Import PDF: File -> Import PDF...
- Convert legacy EDOF 2: File -> Open... auto-detects and converts on load
- Gradient editor: visual stop editor for fill gradients
- Layer panel: dedicated dock with drag-to-reorder, eye/lock toggles per object

Print preview fixes (carried from 3.x)
- Raw PIL bytes via QImage constructor -> bypasses Qt 256 MB image allocation limit
- painter.viewport() for correct page rect (was blank pages)
- QPageSize(QPageSize.PageSizeId.A4) (PyQt6-correct API)
- Preview renders at <= 150 dpi regardless of printer DPI

================================================================================
ADDED - CLI
================================================================================

- edof-cli info template.edof - metadata, variables, editable fields, fonts used
- edof-cli objects template.edof - all objects with layer, type, variable
- edof-cli validate template.edof - structural validation
- edof-cli export template.edof out.png --set name=Jan - fill and export
- edof-cli batch template.edof data.csv -o "out_{n}.png" - CSV batch export
- edof-cli import template.pdf -o template.edof - PDF -> EDOF
- edof-cli convert legacy.edof -o template.edof - EDOF 2 -> EDOF 4 conversion
- --vector / --raster flag for PDF export
- --svg for SVG export
- --all-pages, --dpi, --format, --color-space overrides

================================================================================
FIXED - carried from 3.x development
================================================================================

- Inline text editor keyboard input (replaced QGraphicsProxyWidget with QPlainTextEdit viewport child)
- Inline text editor font size = font_pt x RDPI x zoom / logical_dpi (correct WYSIWYG at all zoom + Windows DPI scaling)
- Auto-shrink / auto-fill DPI conversion (pt -> px = pt x dpi / 72)
- Rotation handle direction sign error
- Rotated object resize keeps anchor fixed
- Middle-mouse pan (scroll bar delta)
- Toolbar/menu items missing (semicolon bug if key: ...; addAction())
- Layer ordering proper swap
- QR codes with non-black colors (B&W render then colorise)
- get_resolved_text falls back to obj.text for empty variable values
- Hidden objects show as ghost outline, still selectable

================================================================================
CHANGED - breaking
================================================================================

- doc.export_pdf() defaults to vector mode (was raster); doc.export_pdf(path, vector=False) for raster fallback
- Internal add_table helper produces a Table object (was a Group of TextBoxes); existing .edof files with the old layout still load via auto-migration
- Shape.path_data field added - old Shape instances without this field load with path_data = [] (no behaviour change)
- TextStyle.padding default 1.0 mm (was hardcoded 2.0 mm in renderer)
- FillStyle.gradient field added - old FillStyle instances load with gradient = None (no behaviour change)

================================================================================
CHANGED - non-breaking
================================================================================

- reportlab is no longer a hard requirement - only used as fallback if vector=False is requested with reportlab installed
- pymupdf added to edof[pdf] extras for the new PDF writer and PDF importer
- pdfplumber added to edof[pdf] extras as optional table-detection helper

================================================================================
FILE FORMAT
================================================================================

- Format version bumped to 4.0.0
- Forward compat: 3.x files load and migrate automatically; new 4.x fields default to neutral values that preserve existing rendering
- Legacy EDOF 2 read support: best-effort migration on load (one-way; output is always 4.x)
- Backward compat for 3.x consumers: 4.x files using only 3.x features can be downgraded with doc.export_3x() (best-effort: rich-text runs collapsed to plain text, paths rasterised to bitmap shapes, tables flattened to groups)

================================================================================
REMOVED
================================================================================

- Old raster-only pdf.py writer (replaced by vector writer with raster fallback)

================================================================================
MIGRATION GUIDE (3.x -> 4.x)
================================================================================

- All 3.x scripts continue to work without changes
- doc.export_pdf("out.pdf") now produces vector PDF; if you specifically need raster (e.g., for compatibility with old PDF/A profiles), pass vector=False
- If you used add_table and relied on iterating its child TextBoxes, switch to Table.cells instead
- New rich-text features are opt-in; plain TextBox.text continues to work
- Legacy EDOF 2 files: loading works automatically. To convert in bulk:
      for f in glob("legacy/*.edof"):
          doc = edof.load(f)
          doc.save(f.replace("legacy/", "converted/"))

================================================================================
================================================================================

## [3.0.2] - 2025-04-15

### Fixed
- attestations: false in CI workflow to fix failed PyPI publish via GitHub Actions

================================================================================

## [3.0.1] - 2025-04-14

### Added
- edof-editor and edof-cli console scripts
- editor_lang/en.json for editor i18n

### Fixed
- Print preview blank pages, Qt 256 MB image limit, QPrinter.PageSize API
- Inline text editor keyboard input and WYSIWYG font sizing
- Auto-shrink / auto-fill DPI conversion
- Rotation handle direction, rotated resize anchor, middle-mouse pan
- Toolbar items missing (semicolon bug)
- Layer ordering swap logic
- QR codes with non-black colors
- Variable binding clearing text
- Hidden objects unselectable

================================================================================

## [3.0.0] - 2025-01-01

Initial public release.

- Document model: TextBox, ImageBox, Shape, Line, QRCode, Group
- Variable/template system with type validation and batch fill
- Pillow RGBA renderer; RGB/RGBA/L/1/CMYK; 8/16-bit
- .edof ZIP format with embedded assets
- Export: PNG/JPEG/TIFF/BMP/PDF; CLI tool; PyQt6 desktop editor
- Command API with undo/redo

================================================================================

Note: Versions 1.x were internal iterations not publicly released.
EDOF 2 was a separate pre-release format with architectural problems that led to the redesign in EDOF 3. EDOF 2 archives can be read by EDOF 4+ in best-effort mode but cannot be written back to.
