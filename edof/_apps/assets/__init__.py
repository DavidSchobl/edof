"""Bundled application assets (icons).

`icon_path(name)` returns the absolute on-disk path to a packaged icon, working
both from a source checkout and from an installed wheel. Kept Qt-free so it can
also be used by the file-association registration code.
"""
from __future__ import annotations

import os


def icon_path(name: str):
    """Return the absolute path to a bundled icon file, or None if missing.

    `name` is the file name, e.g. "edof-editor.ico" or "edof-document.png".
    """
    # Preferred: importlib.resources (works for installed packages).
    try:
        from importlib.resources import files
        p = files("edof._apps.assets.icons").joinpath(name)
        sp = str(p)
        if os.path.isfile(sp):
            return sp
    except Exception:
        pass
    # Fallback: relative to this file (source checkout).
    here = os.path.join(os.path.dirname(__file__), "icons", name)
    return here if os.path.isfile(here) else None


def app_icon_name(kind: str, ext: str = "ico") -> str:
    """Map a logical kind to an icon file name. kind in {editor,viewer,document}."""
    kind = kind if kind in ("editor", "viewer", "document") else "document"
    return f"edof-{kind}.{ext}"
