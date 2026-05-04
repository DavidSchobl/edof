# Reference: Desktop Editor

`edof-editor` is a PyQt6 GUI for visual editing. Requires `pip install edof[pyqt6]`.

Launch:
```bash
edof-editor                   # open with empty document
edof-editor template.edof     # open a specific file
```

The editor produces files that round-trip through the API without loss.

---

## Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  Menu Bar (File, Edit, Insert, Page, Document, View, Help)           │
├──────────────────────────────────────────────────────────────────────┤
│  Toolbar (New, Open, Save, Insert*, Undo/Redo, Zoom, Layer ops)      │
├────────┬───────────────────────────────────────────────────┬─────────┤
│ Pages  │                                                   │         │
│ panel  │                                                   │ Props   │
│        │           Canvas (the page being edited)          │ panel   │
│ Object │                                                   │         │
│ list   │                                                   │ Variab- │
│        │                                                   │ les     │
├────────┴───────────────────────────────────────────────────┴─────────┤
│  Status bar (cursor pos, zoom, protection state, messages)           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Menus

### File

| Item | Shortcut | What it does |
|---|---|---|
| New | Ctrl+N | Create empty document |
| New from Template… | — | Choose a starter template (Blank A4 P/L, Business Card, Certificate, Invoice with Table) |
| Open… | Ctrl+O | Open an `.edof` file (auto-detects encrypted) |
| Import PDF… | — | Reconstruct an editable document from a PDF (best-effort) |
| Save | Ctrl+S | Save to current file |
| Save As… | Ctrl+Shift+S | Choose a new file |
| Save as v3 (downgrade)… | — | Lossy export to v3 format |
| Export PNG… | — | Current page as PNG |
| Export All Pages… | — | Every page as separate PNGs |
| Export PDF… | — | Whole document to PDF |
| Export SVG… | — | Current page as SVG |
| Batch from CSV… | — | Fill variables from each CSV row, export per-row PNGs/PDFs |
| Print… | Ctrl+P | Send to printer |
| Quit | Ctrl+Q | Close (prompts to save changes) |

### Edit

| Item | Shortcut | What it does |
|---|---|---|
| Undo | Ctrl+Z | Step back in history (60 levels) |
| Redo | Ctrl+Y | Step forward |
| Duplicate | Ctrl+D | Copy selected object, offset by 8mm |
| Delete | Delete | Remove selected object(s) |
| Find & Replace… | Ctrl+F | Search across all TextBoxes (regex / case-sensitive options) |
| Gradient Editor… | — | Visual stop editor for the selected object's gradient |

### Insert

Insert specific object types. All inserts respect permission levels — users without `design` permission see a "needs design password" dialog.

| Item | Shortcut | What it does |
|---|---|---|
| Text Box | T | Insert text box at default size |
| Image… | I | Choose an image file, embed and place |
| Rectangle | R | Insert rectangle |
| Ellipse | E | Insert ellipse |
| Line | L | Insert line |
| QR Code | Q | Insert QR code with default URL |

Most inserts can also be done via the toolbar.

### Page

| Item | What it does |
|---|---|
| Add Page | Append new page to document |
| Duplicate Page | Copy current page |
| Delete Page | Remove current page (prompts if it's the only page) |
| Page Settings… | Edit width, height, DPI, color space, background |

### Document

| Item | Shortcut | What it does |
|---|---|---|
| Variables… | — | Manage typed variables (define, edit, set values) |
| Doc Info… | — | Title, author, description, document ID |
| Validate | — | Check for missing required variables, invalid references, etc. |
| Unlock for editing… | Ctrl+Shift+L | Prompt for password (when document is encrypted) |
| Protection… | — | Manage encryption: set/change/remove passwords, switch encryption mode, clear all protection |
| Re-lock (forget password) | — | Forget the cached content key |

### View

| Item | Shortcut | What it does |
|---|---|---|
| Zoom In | Ctrl+= | Zoom 25% larger |
| Zoom Out | Ctrl+- | Zoom 25% smaller |
| Fit Page | Ctrl+0 | Fit page to canvas |
| Snap to Grid | Ctrl+G | Toggle 5mm grid snapping. Affects move, resize, and rotation (rotation snaps to 15°). Hold **Alt** to bypass for one operation. |
| Show Alignment Guides | — | Toggle magnetic snap to other objects' edges |

### Help

About dialog, version info, link to documentation.

---

## Canvas interactions

### Selection

- **Single click** on an object → select it
- **Click empty space** → deselect
- **Ctrl+click** on object → toggle add/remove from multi-selection
- **Drag-select** on empty space → lasso multi-select (in selection mode)

### Manipulation

- **Drag selected object** → move (snaps to grid if Ctrl+G is on)
- **Drag corner handle** → resize (preserves aspect ratio with Shift)
- **Drag rotation handle** (above the object) → rotate
- **Hold Alt while dragging** → bypass grid snap for one operation
- **Arrow keys** with selection → nudge by 1mm (Shift+Arrow = 10mm)
- **Delete / Backspace** → remove selected
- **Ctrl+D** → duplicate
- **Middle-mouse drag** → pan canvas
- **Mouse wheel** → zoom (toward cursor position)

### Group dragging

When multiple objects are selected, dragging any of them moves all of them together (preserving relative positions).

### Edit text inline

**Double-click a TextBox** → enter inline edit mode. Type to change content. Click outside or press Esc to commit.

The inline editor uses WYSIWYG sizing — text shows at the same size as final rendering, regardless of zoom level.

### Rotation handle

When an object is selected, a small handle appears above it. Drag this handle to rotate. Hold Shift to constrain to 15° increments.

### Resize anchors

Eight handles around the bounding box (corners + midpoints). Drag to resize. The opposite corner stays fixed (e.g. dragging top-left keeps bottom-right in place).

---

## Properties panel

Right-side dock. Adapts to the selected object type:

### TextBox properties

- Text content (multiline editor; supports `{variable}` placeholders)
- Font family (dropdown of installed fonts)
- Font size (numeric field)
- Bold / Italic / Underline / Strikethrough (toggles)
- Text color (color picker)
- Alignment (left/center/right/justify)
- Vertical alignment (top/middle/bottom)
- Wrap, auto-shrink, auto-fill (toggles)
- Padding
- Background color
- Border style and color
- Variable binding (dropdown of defined variables)

### ImageBox properties

- Resource (re-pick image from disk)
- Fit mode (contain/cover/fill/stretch)
- H-align, V-align
- Variable binding

### Shape properties

- Shape type (rect/ellipse/line/polygon/arrow/path)
- Fill color OR gradient (with Gradient Editor button)
- Stroke color, width, dash pattern
- Corner radius (rectangle only)

### QRCode properties

- Data (or variable binding)
- Error correction (L/M/Q/H)
- Foreground, background colors

### Table properties

- Number of rows / columns
- Column widths (per column)
- Cell-level styling: select cell → bg color, padding, borders, runs
- Add/remove rows/columns

### Common properties (for any selection)

- Position X, Y (mm)
- Size W, H (mm)
- Rotation (degrees)
- Layer (z-order)
- Opacity (0-100%)
- Visible (toggle)
- Visible if (expression)
- Lock level (none/fill/edit/design/admin)
- Lock text (toggle)
- Tags (free-form list)

---

## Pages panel

Left-side dock showing all pages as thumbnails.

- Click a page → switch to it
- Right-click → menu (duplicate, delete, page settings)
- Drag to reorder

---

## Object list panel

Below pages panel. Shows all objects on the current page in layer order (top item = topmost).

- Click an object → select it on canvas
- Drag to reorder layers
- Eye toggle: show/hide
- Lock toggle: prevent editing (UI lock — separate from `lock_level`)

---

## Variables panel

Right side, below properties. Lists all defined variables and their current values.

- Click value to edit inline
- Add new variable button
- Delete button per variable
- Type / required indicators

---

## Status bar

Bottom of window, always visible. Shows:

- **Cursor position** in mm (live during mouse move on canvas)
- **Zoom level** (percentage)
- **Protection state**:
  - 🔓 Plain document — full edit access
  - 🔒 Document is locked — view only
  - 🔓 Unlocked: \<level name\>
- **Most recent action message** (e.g. "Saved: template.edof", "Imported 4 pages from PDF")

---

## Encryption workflow

### Opening an encrypted file

1. **File → Open…** → choose the encrypted `.edof`
2. The editor detects encryption and shows a password prompt:

   ```
   ┌─ Encrypted Document ──────────────┐
   │  This document is encrypted.       │
   │  Enter a password or recovery key: │
   │                                    │
   │  ( ) Password                      │
   │  ( ) Recovery key                  │
   │                                    │
   │  [____________________]            │
   │                                    │
   │              [ Open ]  [ Cancel ]  │
   └────────────────────────────────────┘
   ```

3. After successful unlock, a dialog shows what your level allows:

   ```
   ┌─ Unlocked ────────────────────────────────┐
   │ Unlocked at level: Edit text              │
   │                                            │
   │ ✓ You CAN:                                │
   │   • Everything in Fill                    │
   │   • Change text content of objects        │
   │   • Change rich-text run contents         │
   │                                            │
   │ ✗ You CANNOT:                             │
   │   • Change fonts, colors, sizes           │
   │   • Move, resize, rotate objects          │
   │   • Add or remove objects                 │
   │   • Manage passwords                      │
   │                                            │
   │                              [ OK ]        │
   └────────────────────────────────────────────┘
   ```

4. Three wrong attempts close the prompt. Use **File → Open** to try again.

### Setting up encryption

**Document → Protection…** opens the management dialog:

```
┌─ Document Protection ──────────────────────────┐
│ Status: 🔓 Plain (no encryption)              │
│ Add a password below to enable encryption.    │
│                                                │
│ Set / change passwords:                       │
│   fill   (empty):      [____________________] │
│   edit   (empty):      [____________________] │
│   design (empty):      [____________________] │
│   admin  (empty):      [____________________] │
│                                                │
│ Levels: fill=template, edit=text,             │
│ design=full edit, admin=manage protection.    │
│                                                │
│ [ Remove all protection ]   [ Apply ] [Cancel]│
└────────────────────────────────────────────────┘
```

After clicking Apply on first password setup, a **recovery key dialog** appears:

```
┌─ Recovery Key — SAVE THIS NOW ────────────┐
│ ⚠ Save this recovery key NOW              │
│                                            │
│ If you lose all your passwords, this is   │
│ the only way to recover the document.     │
│ It will not be shown again. Store it in   │
│ a password manager or print it to paper.  │
│                                            │
│ ┌────────────────────────────────────────┐│
│ │ 7K3F-9XQM-2N8P-VR4A-HT6L-Z5BJ          ││
│ └────────────────────────────────────────┘│
│                                            │
│ [ Copy to clipboard ]  [I have saved this]│
└────────────────────────────────────────────┘
```

The "I have saved this key" button confirms before closing — if you click it without copying first, it asks again.

### Permission-aware UI

When the current session lacks permission for an action:

- **Toolbar buttons and menu items** for that action are disabled (greyed out)
- Pressing a keyboard shortcut for a disabled action shows a clear dialog:

   ```
   ┌─ Permission required ────────────────────┐
   │ This action (Add TextBox) requires        │
   │ permission level:                         │
   │    Design or higher                       │
   │                                            │
   │ You are currently at:                     │
   │    Edit text                              │
   │                                            │
   │ Use Document → Unlock for editing… to    │
   │ enter a higher-level password.            │
   │                                            │
   │                              [ OK ]        │
   └────────────────────────────────────────────┘
   ```

- **Per-object locks** are also enforced — you can't drag an object whose `lock_level` exceeds your current permission, or edit text on an object with `lock_text=True`.

---

## Keyboard shortcuts summary

| Shortcut | Action |
|---|---|
| Ctrl+N | New |
| Ctrl+O | Open |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| Ctrl+Q | Quit |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |
| Ctrl+D | Duplicate |
| Delete | Delete selection |
| Ctrl+F | Find & Replace |
| Ctrl+G | Toggle snap to grid |
| Ctrl+= / Ctrl++ | Zoom in |
| Ctrl+- | Zoom out |
| Ctrl+0 | Fit page |
| Ctrl+P | Print |
| Ctrl+Shift+L | Unlock for editing |
| T | Insert text box |
| I | Insert image |
| R | Insert rectangle |
| E | Insert ellipse |
| L | Insert line |
| Q | Insert QR code |
| Arrow keys | Nudge selection by 1mm |
| Shift+Arrow | Nudge by 10mm |
| Esc | Cancel current operation / exit text edit |

---

## Localization

The editor's UI strings live in JSON files in `edof/editor_lang/`:

- `en.json` — English (default, always present)
- Add `XX.json` for other languages (`cs.json`, `de.json`, etc.)

Set the language environment variable before launching:

```bash
EDOF_LANG=cs edof-editor
```

If a key is missing in the chosen language file, the editor falls back to English.

---

## Settings persistence

The editor remembers across sessions (via Qt's `QSettings`):
- Window geometry (size and position)
- Snap-to-grid on/off
- Show alignment guides on/off
- Recent files list (up to 10)

Settings are stored in standard system locations:
- **Windows**: registry under `HKEY_CURRENT_USER\Software\edof\editor`
- **Linux**: `~/.config/edof/editor.conf`
- **macOS**: `~/Library/Preferences/edof.editor.plist`

Delete to reset all preferences.

---

## Troubleshooting

**Editor doesn't start, no error:** Check the console output — sometimes PyQt6 errors go to stderr without appearing in a dialog. Run `edof-editor` from a terminal to see them.

**Editor crashes on a specific file:** Try the API to load it:

```python
import edof
doc = edof.load("problem.edof")
print(doc.errors)
```

If the API loads it cleanly but the editor crashes, file a bug. If the API errors too, the file is likely corrupt.

**Fonts don't appear in dropdown:** edof discovers fonts at startup. If you install a font while the editor is running, restart to pick it up.

**Slow performance with large documents:** Lower the canvas DPI in View settings (default 96). Re-rendering is the expensive part; the document data itself is fast.

**Password dialog keeps rejecting correct password:** Check Caps Lock and keyboard layout. The recovery key field is case-insensitive and ignores dashes; the password field is case-sensitive.
