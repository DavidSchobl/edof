# Troubleshooting

Common issues and how to solve them.

## Installation

### `pip install edof[all]` fails

Most likely one of the optional extras (PyQt6, pymupdf, reportlab, cryptography) doesn't have a wheel for your Python version. Install with a smaller subset and add extras one by one to find the culprit:

```bash
pip install edof
pip install edof[crypto]
pip install edof[qr]
pip install edof[pdf]
pip install edof[pyqt6]
```

The one that fails is the one to investigate. Search for the error message in the failing package's GitHub issues.

If a wheel doesn't exist, you may need:
- A C compiler installed (Visual Studio Build Tools on Windows; `gcc` on Linux; Xcode CLI tools on macOS)
- A Python version with a wheel — try a slightly older Python (3.12 instead of 3.13, etc.)

### `edof-editor` not found in PATH

This means either:
- The `[pyqt6]` extra wasn't installed → `pip install edof[pyqt6]`
- The Python `Scripts/` directory isn't in PATH

Check where the script lives:

```bash
# Windows
where edof-editor

# Linux/macOS
which edof-editor
```

If not found:

```python
import sys, os
print(os.path.dirname(sys.executable))   # Python install directory
# Then find: <that>/Scripts/edof-editor.exe (Windows) or <that>/bin/edof-editor (Linux/macOS)
```

Add the appropriate Scripts/bin directory to PATH (Environment Variables on Windows; `~/.bashrc` on Linux).

### `ImportError: cryptography` when using encryption

```bash
pip install edof[crypto]
# or directly:
pip install cryptography>=42
```

### `ImportError: pymupdf` when calling `import_pdf`

```bash
pip install edof[pdf]
```

---

## Runtime issues

### `EdofPasswordRequired` when loading

The file is encrypted and needs a password:

```python
doc = edof.load("secret.edof", password="...")
```

Or with the recovery key:

```python
doc = edof.load("secret.edof", recovery_key="ABCD-EFGH-...")
```

If you don't have either, the file is unrecoverable.

### `EdofWrongPassword`

Check:
- Caps Lock and keyboard layout
- Trailing/leading whitespace (passwords are case-sensitive and exact)
- Are you using the password for the right level? (Try each known password.)

For recovery keys, dashes and case are ignored. `7K3F-9XQM-2N8P` and `7K3F9XQM2N8P` work the same.

### `EdofVersionError` when loading

The file was saved by a newer edof version, or the file is corrupt.

Check the version:

```python
from edof.format.serializer import EdofSerializer
manifest = EdofSerializer.peek("file.edof")
print(manifest.get("edof_version"))
```

If the version is `4.0.x` and you have `4.0.0`, upgrade:

```bash
pip install --upgrade edof
```

If the file shows no version (raw extraction shows no `manifest.json`), it might be:
- A corrupt ZIP — try `unzip -t file.edof` to verify integrity
- An EDOF 2 archive (no manifest, just `data.json`) — should auto-migrate; if not, file a bug
- Not actually an `.edof` file — check with `file file.edof` (Linux/macOS) or look at the first 4 bytes; ZIP starts with `PK\x03\x04`

### `EdofValidationError`

You called `doc.validate()` and it found issues. The exception has a list of problem strings:

```python
issues = doc.validate()
for i in issues:
    print(f"  - {i}")
```

Common issues and fixes:

| Issue | Fix |
|---|---|
| "Required variable X has no value" | Call `doc.set_variable("X", value)` before exporting |
| "Object Y references resource Z which doesn't exist" | The resource was deleted but objects still reference it. Either re-add the resource or update the object's `resource_id` |
| "Duplicate object ID" | Two objects have the same UUID. Re-create one of them with `obj.id = new_uuid()` |
| "Object positioned entirely off-page" | Check `obj.transform.x/y` — likely negative or beyond page size |

`validate()` doesn't fix issues — it just reports them. Always check after building documents programmatically.

### Czech / Polish / German diacritics don't render

The vector PDF writer uses WinAnsiEncoding which covers Czech, Polish, German, etc. fine. If diacritics are missing:

- **Vector PDF:** edof might be falling back to Helvetica which has full WinAnsi support; verify by inspecting the PDF in a viewer
- **Raster PDF / PNG:** Pillow uses the system fonts. Make sure DejaVu Sans, Arial, or a similar Unicode-capable font is installed

If a specific Unicode character doesn't render, the font you specified doesn't have that glyph. Try a different font (DejaVu Sans is the safest default) or use raster output mode.

### Custom font in PDF doesn't work

The vector PDF writer only supports the **Standard 14 PDF fonts** (Helvetica, Times, Courier with bold/italic variants). Other fonts are mapped to the closest match.

For custom fonts in PDF, use raster mode:

```python
doc.export_pdf("output.pdf", vector=False)
```

This goes through Pillow which can render any installed TTF.

### "Image variable doesn't update"

If `ib.variable = "logo"` and you change `doc.set_variable("logo", new_path)`, but the rendered output doesn't show the new image:

- **Check the value type.** Image variables accept either a resource_id (string already in `doc.resources`) or a file path (string pointing to disk). If you pass a resource_id that doesn't exist, the variable is silently ignored.
- **Cache:** if you're rendering in a tight loop, edof internally caches loaded images. Restart the process if behavior is suspicious during testing.

```python
# Verify the variable was set
print(doc.variables.get("logo"))
# Verify the file exists
import os
print(os.path.exists(doc.variables.get("logo")))
```

### "Repeating section overflows the page weirdly"

`page.repeat_objects()` calculates total height based on the bounding box of the template objects + `gap`. If your template has an unusual layout (nested groups, overlapping elements), the height may be misjudged.

Workaround: explicitly set a height on the template:

```python
# Template with explicit height
group_template = some_group_with_known_size
group_template.transform.height = 25.0   # mm

# Now repeat_objects knows exactly how much space each repetition needs
```

### "Editor crashes on startup"

Run from a terminal to see error output:

```bash
edof-editor
```

If you see PyQt errors:
- Check PyQt6 version: `pip show PyQt6`
- Update: `pip install --upgrade PyQt6`
- On Linux, you may need `qt6-base-dev` system packages

If you see edof errors:
- Try opening with no file: `edof-editor` (no arguments)
- Try with the API instead of the editor: `python -c "import edof; print(edof.__version__)"`

### "Editor opens but is blank/black"

Often a graphics driver issue:
- On Linux, try `QT_QPA_PLATFORM=xcb edof-editor`
- On Windows, update your graphics drivers
- On Wayland, sometimes setting `QT_QPA_PLATFORM=wayland` or `xcb` helps

### "Inserted object appears in wrong position"

Coordinates are in **mm**, with `(0, 0)` at top-left. Y increases downward. If your object appears upside down or off-page:

- Are you using pixels by mistake? Convert: `mm = pixels * 25.4 / dpi`
- Are you using bottom-left coords (mathematical convention)? Flip: `y_top = page.height - y_bottom - height`

### "PDF export is much smaller / larger than expected"

**Smaller than expected** — make sure you're exporting in the right mode:
```python
doc.export_pdf("out.pdf")              # vector — typically 5-10 KB per page
doc.export_pdf("out.pdf", vector=False) # raster — typically 80-200 KB per page
```

**Larger than expected** — usually photographic images. Check your resources:
```python
total = 0
for rid, info in doc.resources.list().items():
    print(f"  {rid}: {info['filename']} {info['size']:,} bytes")
    total += info['size']
print(f"Total resources: {total:,} bytes")
```

If image sizes are large, downscale them before adding (Pillow can do this in 5 lines).

### "Variables in placeholder text not substituted"

Check:

```python
print(doc.variables.values())   # what's currently set?
print(doc.variables.names())     # what's defined?
```

If the variable is defined but not set, the placeholder remains as `{name}` and a warning is added to `doc.errors`.

If you typed `{recipient}` but defined `recipient_name`, the names don't match — placeholders are exact.

### `EdofMissingFontWarning` in `doc.errors`

A font was requested but not found. Check:

```python
from edof.engine.text_engine import discovered_fonts
print(discovered_fonts())
```

Either install the font or pick a different one.

The render still happens with a fallback font (DejaVu Sans) — it's just a warning.

---

## Performance

### "Rendering is slow"

Rough times on modern hardware:
- Simple A4 page at 300 DPI bitmap: 50-200 ms
- A4 page with table + 100 textboxes at 300 DPI: 500 ms - 2 s
- Vector PDF: 30-100 ms per page
- Raster PDF: similar to bitmap export at the chosen DPI

If you're seeing 5+ seconds per page:
- Check DPI — 600+ is overkill for most uses
- Check images — large embedded images take time to scale
- Check fonts — first font use loads/scans system fonts (subsequent uses are fast)

### "Large batch is slow"

See [cookbook/batch-pdf.md](../cookbook/batch-pdf.md) for performance tips. Key ones:
- Load template once, fill many times
- Don't re-add resources per render
- Use multiprocessing for true parallelism

### "Memory usage grows over time during a long batch"

Possible causes:
- Pillow image cache (rare in normal use)
- Pickled state in subprocesses

Mitigation:
```python
# Periodically restart the worker process
if i % 1000 == 0:
    # ... persist state, restart from clean slate
```

In practice, memory stays stable for batches of thousands of documents.

---

## File corruption

### "File won't open, says invalid ZIP"

Try standard ZIP recovery tools:
```bash
zip -F broken.edof --out fixed.edof
```

If the ZIP is structurally OK but `manifest.json` is corrupt:
- Extract and inspect: `unzip broken.edof manifest.json`
- Hand-edit the JSON if needed
- Re-zip back: `zip fixed.edof manifest.json document.json resources/*`

For encrypted files, manifest corruption usually means the file is unrecoverable. The `protection.slots` data is critical — without it, no password can unlock the document.

### "Document loads but content looks scrambled"

Could be:
- Mixed format versions (file claims v4 but has v3 fields). `doc.errors` should have warnings.
- Custom object types that the loading environment doesn't know about → unknown objects are silently dropped or shown as placeholders. See [advanced/extending.md](extending.md).
- A bug in edof. File an issue with the file attached if possible.

---

## Reporting bugs

If you've ruled out the issues above:

1. Try the latest version: `pip install --upgrade edof`
2. Reproduce with a minimal example (smallest doc that triggers the issue)
3. Capture:
   - edof version: `python -c "import edof; print(edof.__version__)"`
   - Python version: `python --version`
   - OS and version
   - The minimal example code
   - Full traceback if there's an exception
4. Open an issue at `https://github.com/DavidSchobl/edof/issues`

If the bug involves a specific file, include it (or a redacted/synthetic version that reproduces the issue).

---

## Where to get help

- This documentation in the `docs/` directory
- The `examples/` directory in the repo (if present)
- GitHub Issues: `https://github.com/DavidSchobl/edof/issues`
- For security issues (encryption bugs, key handling): contact the maintainer privately first
