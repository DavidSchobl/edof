# Installation

## Basic installation

```bash
pip install edof
```

This installs the core library, which includes all features that depend only on Pillow (rendering, vector PDF export, all object types, variables, plain `.edof` save/load). Pillow is installed automatically.

## Optional extras

edof has several optional features bundled in extras. Pick what you need:

```bash
pip install edof[pdf]      # PDF import + raster PDF fallback
pip install edof[qr]       # QR code generation
pip install edof[crypto]   # AES-256 document encryption
pip install edof[pyqt6]    # Desktop editor
pip install edof[all]      # Everything above
```

You can combine them:

```bash
pip install edof[crypto,pyqt6]
```

### What each extra adds

**`[pdf]`** — installs `pymupdf` (for `import_pdf`), `pdfplumber` (for table detection during import), and `reportlab` (for raster PDF fallback when `vector=False`). Without this extra, `doc.export_pdf()` works fine in vector mode (the default), but `import_pdf()` and `export_pdf(vector=False)` are unavailable.

**`[qr]`** — installs `qrcode[pil]` for rendering QR code objects. Without this extra, `QRCode` objects render as a placeholder rectangle with a warning.

**`[crypto]`** — installs `cryptography>=42` for AES-256-GCM document encryption. Without this extra, `doc.set_password()` and related methods raise `EdofCryptoUnavailable`. Plain (unencrypted) documents work without `cryptography` installed.

**`[pyqt6]`** — installs `PyQt6` and provides the `edof-editor` console script. The editor is optional; the library is fully usable from code without a GUI.

**`[all]`** — equivalent to `[pdf,qr,crypto,pyqt6]`. Recommended for desktop development unless you need to keep the install minimal.

## After installation

The `edof-cli` and `edof-editor` scripts are installed automatically. To verify:

```bash
edof-cli --version
edof-cli info --help
```

If you installed `[pyqt6]`:

```bash
edof-editor
```

## Side-by-side version installs

If you need multiple edof versions for testing (or to compare one release against an older one without uninstalling the old one), use isolated virtualenvs.

**Windows:**

```cmd
mkdir D:\apps\Edof_V401
cd D:\apps\Edof_V401
python -m venv .venv
.venv\Scripts\activate
pip install edof[all]==4.2.2
deactivate
```

A small batch script makes switching painless. Save as `D:\apps\bin\edof401.bat`:

```bat
@echo off
call D:\apps\Edof_V401\.venv\Scripts\activate.bat
cmd /k prompt [edof v4.2.2] $P$G
```

Then `edof401` in any cmd window puts you in that version's environment.

**Linux / macOS:**

```bash
mkdir -p ~/apps/edof-401
cd ~/apps/edof-401
python -m venv .venv
source .venv/bin/activate
pip install edof[all]==4.2.2
deactivate
```

Add to `~/.zshrc` or similar:

```bash
alias edof401='source ~/apps/edof-401/.venv/bin/activate'
```

Each version's venv is independent. Removing a version is just deleting its folder.

## Compatibility

- **Python:** 3.9 or newer
- **Operating systems:** Windows, Linux, macOS — all features work cross-platform
- **Pillow:** any version >= 9.0
- **Cryptography:** any version >= 42 (when using the `[crypto]` extra)
- **PyQt6:** any version >= 6.6 (when using the `[pyqt6]` extra)

## Troubleshooting installation

**`pip install edof[all]` fails on a specific extra:** Some heavy extras (`pymupdf`, `PyQt6`) sometimes lag on the latest Python release. If you're on Python 3.13 or newer and one of them fails, install with a smaller subset:

```bash
pip install edof
pip install edof[crypto]
pip install edof[qr]
# Then add the others one by one to identify which one fails
```

**`edof-editor` not found after install:** This means the `[pyqt6]` extra wasn't included, or your shell hasn't picked up the new entry point. Try:

```bash
pip install --upgrade edof[pyqt6]
which edof-editor    # Linux/macOS
where edof-editor    # Windows
```

If the script exists but you can't run it from cmd, your `Scripts` directory might not be in PATH. On Windows, the path is usually:

```
C:\Users\<you>\AppData\Local\Programs\Python\Python312\Scripts\
```

Add it to PATH in your environment variables, or run the editor with full path:

```cmd
"C:\Users\YourName\AppData\Local\Programs\Python\Python312\Scripts\edof-editor.exe"
```

**`ImportError: cryptography` when using encryption:** Run `pip install edof[crypto]` or `pip install cryptography>=42`.

**`ImportError: pymupdf` when calling `import_pdf`:** Run `pip install edof[pdf]` or `pip install pymupdf`.
