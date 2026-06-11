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


def _sub_asset_path(subpkg: str, subdir: str, name: str):
    try:
        from importlib.resources import files
        p = files("edof._apps.assets." + subpkg).joinpath(name)
        sp = str(p)
        if os.path.isfile(sp):
            return sp
    except Exception:
        pass
    here = os.path.join(os.path.dirname(__file__), subdir, name)
    return here if os.path.isfile(here) else None


def cursor_path(name: str):
    """Absolute path to a bundled cursor asset (e.g. 'cur-pen.png' or
    'cursors.json'), or None."""
    return _sub_asset_path("cursors", "cursors", name)


def ui_icon_path(name: str):
    """Absolute path to a bundled UI icon asset (e.g. 'ic-save.png' or
    'icons.json'), or None."""
    return _sub_asset_path("ui_icons", "ui_icons", name)


def app_icon_name(kind: str, ext: str = "ico") -> str:
    """Map a logical kind to an icon file name. kind in {editor,viewer,document}."""
    kind = kind if kind in ("editor", "viewer", "document") else "document"
    return f"edof-{kind}.{ext}"


def set_windows_app_id(app_id: str) -> None:
    """Give this process its own Windows taskbar identity.

    Without this, a GUI launched under python/pythonw is grouped under the host
    interpreter and the taskbar shows the interpreter's icon instead of the
    app's window icon. Must be called early, before any window is shown. No-op
    off Windows.
    """
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
    except Exception:
        pass
