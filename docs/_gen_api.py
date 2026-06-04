#!/usr/bin/env python3
"""Generate the complete API reference (docs/reference/API.md) by introspecting
the public surface of the ``edof`` package (everything in ``edof.__all__``).

Run from the repository root:

    python docs/_gen_api.py

This keeps the API reference in lock-step with the code: signatures and
docstrings are read live, so the document never drifts from reality. Re-run it
whenever the public API changes.
"""
from __future__ import annotations

import inspect
import os
import sys

# Headless Qt so importing the package never tries to open a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Allow running from anywhere: put the repository root (parent of docs/) first.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import edof  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "reference", "API.md")

# Logical grouping for a readable table of contents.
GROUPS = [
    ("Document model", ["Document", "Page", "ResourceStore"]),
    ("Objects", ["EdofObject", "TextBox", "ImageBox", "Shape", "QRCode",
                 "Group", "Table", "TableCell", "CellBorder",
                 "SubDocumentBox", "SvgBox"]),
    ("Styles", ["TextStyle", "TextRun", "StrokeStyle", "FillStyle",
                "ShadowStyle", "Gradient", "LayerEffect"]),
    ("Variables", ["VariableStore", "VariableDef"]),
    ("Serialization", ["EdofSerializer"]),
    ("Geometry", ["Transform"]),
    ("Exceptions & warnings", [
        "EdofError", "EdofVersionError", "EdofResourceError", "EdofRenderError",
        "EdofVariableError", "EdofAPIError", "EdofValidationError",
        "EdofPrintError", "EdofNewerVersionWarning",
        "EdofMissingOptionalWarning", "EdofMissingFontWarning"]),
]

FUNCTION_GROUPS = [
    ("Convenience", ["new", "load", "import_pdf", "import_rtf", "import_docx", "export_docx"]),
    ("Tables", ["make_table"]),
    ("Rendering", ["render_page", "render_document"]),
    ("Bitmap export", ["export_page_bitmap", "export_all_pages",
                       "export_to_bytes"]),
    ("Geometry helpers", ["to_mm", "from_mm", "mm_to_px"]),
    ("Colour", ["as_color"]),
    ("Text metrics", ["measure_text_height"]),
]

# Symbols that exist in the API but are not yet complete. They are documented
# with a clear warning so nobody mistakes them for finished features.
EXPERIMENTAL = {"Table", "TableCell", "CellBorder", "make_table"}
_EXPERIMENTAL_NOTE = (
    "> **Experimental / TBD.** This is a work in progress and not yet "
    "complete. The API and behaviour may change; avoid relying on it in "
    "production.\n")


def _sig(obj) -> str:
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return "(...)"


def _doc(obj) -> str:
    d = inspect.getdoc(obj)
    return d.strip() if d else ""


def _anchor(name: str) -> str:
    return name.lower().replace(" ", "-").replace("&", "").replace("--", "-")


def _public_methods(cls):
    out = []
    for mname, m in inspect.getmembers(cls, predicate=inspect.isfunction):
        if mname.startswith("_"):
            continue
        out.append((mname, m))
    # Class/static methods are functions too in 3.x; also catch them.
    for mname, m in inspect.getmembers(cls):
        if mname.startswith("_") or any(mname == n for n, _ in out):
            continue
        if isinstance(inspect.getattr_static(cls, mname, None),
                      (staticmethod, classmethod)):
            real = getattr(cls, mname)
            out.append((mname, real))
    out.sort(key=lambda t: t[0])
    return out


def emit_class(w, name):
    cls = getattr(edof, name)
    w(f"### `{name}`\n")
    if name in EXPERIMENTAL:
        w(_EXPERIMENTAL_NOTE)
    ctor = _sig(cls)
    if ctor and ctor != "(...)":
        w(f"```python\n{name}{ctor}\n```\n")
    doc = _doc(cls)
    if doc:
        w(doc + "\n")
    meths = _public_methods(cls)
    if meths:
        w("\n**Methods**\n")
        for mname, m in meths:
            w(f"\n#### `{name}.{mname}{_sig(m)}`\n")
            md = _doc(m)
            if md:
                w(md + "\n")
    w("\n---\n")


def emit_function(w, name):
    fn = getattr(edof, name)
    w(f"### `{name}`\n")
    if name in EXPERIMENTAL:
        w(_EXPERIMENTAL_NOTE)
    sig = _sig(fn)
    if sig and sig != "(...)":
        w(f"```python\n{name}{sig}\n```\n")
    doc = _doc(fn)
    if doc:
        w(doc + "\n")
    w("\n---\n")


def emit_constants(w):
    w("## Constants\n")
    groups = {
        "Shape kinds": ["SHAPE_RECT", "SHAPE_ELLIPSE", "SHAPE_LINE",
                        "SHAPE_POLYGON", "SHAPE_ARROW", "SHAPE_PATH"],
        "Variable kinds": ["VAR_TEXT", "VAR_IMAGE", "VAR_NUMBER", "VAR_DATE",
                           "VAR_BOOL", "VAR_QR", "VAR_URL"],
        "Colour spaces": ["CS_RGB", "CS_RGBA", "CS_GRAY", "CS_BW", "CS_CMYK"],
        "Bit depths": ["BD_8", "BD_16"],
        "Version": ["__version__", "FORMAT_VERSION_STR"],
    }
    for title, names in groups.items():
        w(f"\n**{title}**\n\n")
        w("| Name | Value |\n|------|-------|\n")
        for n in names:
            v = getattr(edof, n, None)
            w(f"| `{n}` | `{v!r}` |\n")
    w("\n---\n")


def main():
    lines = []
    w = lambda s: lines.append(s)

    w("# API reference\n")
    w(f"_Generated from `edof` {edof.__version__} "
      f"(format {edof.FORMAT_VERSION_STR})._\n")
    w("\nThis page documents the complete public API exported by `import edof`. "
      "It is generated directly from the code with `docs/_gen_api.py`, so the "
      "signatures and descriptions match the installed version exactly.\n")

    # Table of contents
    w("\n## Contents\n")
    w("\n**Classes**\n")
    for title, names in GROUPS:
        present = [n for n in names if getattr(edof, n, None) is not None]
        if present:
            links = ", ".join(f"[`{n}`](#{_anchor(n)})" + (" _(TBD)_" if n in EXPERIMENTAL else "") for n in present)
            w(f"- {title}: {links}\n")
    w("\n**Functions**\n")
    for title, names in FUNCTION_GROUPS:
        present = [n for n in names if getattr(edof, n, None) is not None]
        if present:
            links = ", ".join(f"[`{n}`](#{_anchor(n)})" + (" _(TBD)_" if n in EXPERIMENTAL else "") for n in present)
            w(f"- {title}: {links}\n")
    w("- [Constants](#constants)\n")
    w("\n---\n")

    # Functions first (most-used entry points).
    w("\n## Functions\n")
    for title, names in FUNCTION_GROUPS:
        w(f"\n## {title}\n")
        for n in names:
            if getattr(edof, n, None) is not None:
                emit_function(w, n)

    # Classes.
    w("\n## Classes\n")
    for title, names in GROUPS:
        w(f"\n## {title}\n")
        for n in names:
            if getattr(edof, n, None) is not None:
                emit_class(w, n)

    emit_constants(w)

    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {OUT} ({len(text):,} bytes)")


if __name__ == "__main__":
    sys.exit(main())
