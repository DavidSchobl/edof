"""edof file association — register .edof files with edof-viewer.

Provides cross-platform helpers to make double-clicking a .edof file in the
OS file manager open it in edof-viewer.

Windows: writes to HKEY_CURRENT_USER\\Software\\Classes (does NOT need admin).
Linux:  installs a .desktop file + MIME type.
macOS:  prints instructions (UTType registration via Info.plist requires a
        full .app bundle which is built only by the standalone installer).
"""
from __future__ import annotations

import os
import sys
import shutil
import subprocess
from pathlib import Path


def _find_viewer_executable():
    """Locate the edof-viewer command in PATH."""
    exe = shutil.which("edof-viewer")
    if exe:
        return exe
    # Fallback: try Python module invocation
    if sys.executable:
        return f'"{sys.executable}" -m edof._apps.viewer'
    raise RuntimeError(
        "Could not locate edof-viewer executable. "
        "Make sure edof[viewer] is installed: pip install 'edof[viewer]'"
    )


def _find_editor_executable():
    """Locate the edof-editor command in PATH (fallback to module invocation)."""
    exe = shutil.which("edof-editor")
    if exe:
        return exe
    if sys.executable:
        return f'"{sys.executable}" -m edof._apps.editor'
    raise RuntimeError(
        "Could not locate edof-editor executable. "
        "Make sure edof[editor] is installed: pip install 'edof[all]'"
    )


def _cmd_with_arg(exe: str) -> str:
    """Build a 'command' value: quote the exe (unless already quoted) + "%1"."""
    if exe.startswith('"') or exe.startswith("'"):
        return f'{exe} "%1"'
    return f'"{exe}" "%1"'


def current_association_status() -> str:
    """Return human-readable description of current .edof file association."""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ".edof") as k:
                cls, _ = winreg.QueryValueEx(k, "")
            if cls and cls.startswith("edof.Document"):
                # Our document type. With the v4.2.2 model the type has no
                # default opener, so check whether the open-with choices exist.
                return ("associated (EDOF icon set; Windows asks which app "
                        "to open with)")
            # Some other progid claims .edof
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                    f"{cls}\\shell\\open\\command") as k:
                    cmd, _ = winreg.QueryValueEx(k, "")
                return f"associated with another app: {cmd}"
            except OSError:
                return f"associated with: {cls}"
        except OSError:
            return "not associated"
    elif sys.platform.startswith("linux"):
        # Check xdg-mime
        try:
            r = subprocess.run(
                ["xdg-mime", "query", "default", "application/x-edof"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip():
                return f"associated with: {r.stdout.strip()}"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return "not associated"
    elif sys.platform == "darwin":
        return "macOS associations require .app bundle (not yet supported)"
    return "unknown platform"


def associate_edof_files():
    """Register .edof files with edof-viewer for the current user."""
    if sys.platform == "win32":
        return _associate_windows()
    if sys.platform.startswith("linux"):
        return _associate_linux()
    if sys.platform == "darwin":
        raise NotImplementedError(
            "macOS file association requires building edof-viewer as an .app "
            "bundle (planned for v5.0). For now, right-click a .edof file → "
            "Open With → Other → choose 'edof-viewer'."
        )
    raise NotImplementedError(f"Platform {sys.platform} not supported")


def unassociate_edof_files():
    """Remove the .edof file association for the current user."""
    if sys.platform == "win32":
        return _unassociate_windows()
    if sys.platform.startswith("linux"):
        return _unassociate_linux()
    raise NotImplementedError(f"Platform {sys.platform} not supported")


# ─────────────────────────────────────────────────────────────────────────────
# Windows
# ─────────────────────────────────────────────────────────────────────────────

def _associate_windows():
    """Register .edof in HKCU\\Software\\Classes (per-user, no admin needed).

    v4.2.2: the association does NOT force a default opener. `.edof` is mapped
    to a document *type* progid (icon + friendly name, no open command), and the
    Viewer and Editor are registered as the two "Open with" choices. The first
    time the user double-clicks a `.edof` file Windows asks which app to use, so
    the user picks their own default (and can change it any time). Files still
    show the document icon in Explorer.
    """
    import winreg

    classes = r"Software\Classes"
    progid_doc = "edof.Document"          # file type: icon + name, no opener
    progid_view = "edof.Document.Viewer"  # Open-with choice: Viewer
    progid_edit = "edof.Document.Editor"  # Open-with choice: Editor

    viewer = _find_viewer_executable()
    cmd_view = _cmd_with_arg(viewer)
    try:
        editor = _find_editor_executable()
        cmd_edit = _cmd_with_arg(editor)
    except RuntimeError:
        editor = None
        cmd_edit = None

    try:
        from edof._apps.assets import icon_path
    except Exception:
        icon_path = lambda *_a, **_k: None  # noqa: E731
    doc_icon = icon_path("edof-document.ico")
    view_icon = icon_path("edof-viewer.ico")
    edit_icon = icon_path("edof-editor.ico")

    def _set_default(path, value):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"{classes}\\{path}",
                                0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, value)

    # 1. .edof → the document TYPE progid (gives icon + name) and the open-with
    #    list. No "default opener" is set on the type, so Windows prompts the
    #    user to choose between the Viewer and the Editor.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"{classes}\\.edof",
                            0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, progid_doc)
        winreg.SetValueEx(k, "Content Type", 0, winreg.REG_SZ, "application/x-edof")
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                            f"{classes}\\.edof\\OpenWithProgids",
                            0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, progid_view, 0, winreg.REG_NONE, b"")
        if editor:
            winreg.SetValueEx(k, progid_edit, 0, winreg.REG_NONE, b"")

    # 2. Document type: friendly name + icon, deliberately NO shell\open\command.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"{classes}\\{progid_doc}",
                            0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "EDOF Document")
        winreg.SetValueEx(k, "FriendlyTypeName", 0, winreg.REG_SZ,
                          "Easy Document Format File")
    if doc_icon and os.path.isfile(doc_icon):
        _set_default(f"{progid_doc}\\DefaultIcon", f'"{doc_icon}",0')

    # 3. Viewer open-with choice (own name + icon + open command).
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"{classes}\\{progid_view}",
                            0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "EDOF Viewer")
    if view_icon and os.path.isfile(view_icon):
        _set_default(f"{progid_view}\\DefaultIcon", f'"{view_icon}",0')
    _set_default(f"{progid_view}\\shell\\open\\command", cmd_view)

    # 4. Editor open-with choice.
    if cmd_edit:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"{classes}\\{progid_edit}",
                                0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "EDOF Editor")
        if edit_icon and os.path.isfile(edit_icon):
            _set_default(f"{progid_edit}\\DefaultIcon", f'"{edit_icon}",0')
        _set_default(f"{progid_edit}\\shell\\open\\command", cmd_edit)

    # 5. Notify the shell that associations changed
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST,
                                             None, None)
    except Exception:
        pass

    if editor:
        return True, (".edof registered. Files now show the EDOF icon, and the "
                      "first time you open one Windows lets you choose the "
                      "Viewer or the Editor (no default is forced).")
    return True, (".edof registered with the Viewer as an open-with choice. "
                  "(Editor not found, so only the Viewer was registered.)")


def _unassociate_windows():
    import winreg
    classes = r"Software\Classes"
    for sub in [
        r".edof\OpenWithProgids",
        r".edof",
        # new (v4.2.2) keys
        r"edof.Document.Viewer\shell\open\command",
        r"edof.Document.Viewer\shell\open",
        r"edof.Document.Viewer\shell",
        r"edof.Document.Viewer\DefaultIcon",
        r"edof.Document.Viewer",
        r"edof.Document.Editor\shell\open\command",
        r"edof.Document.Editor\shell\open",
        r"edof.Document.Editor\shell",
        r"edof.Document.Editor\DefaultIcon",
        r"edof.Document.Editor",
        r"edof.Document\DefaultIcon",
        r"edof.Document",
        # old (<=4.2.1) keys, cleaned up for migration
        r"edof.Document.1\shell\edit\command",
        r"edof.Document.1\shell\edit",
        r"edof.Document.1\shell\open\command",
        r"edof.Document.1\shell\open",
        r"edof.Document.1\shell",
        r"edof.Document.1\DefaultIcon",
        r"edof.Document.1",
        r"edof.Document.Editor.1\shell\open\command",
        r"edof.Document.Editor.1\shell\open",
        r"edof.Document.Editor.1\shell",
        r"edof.Document.Editor.1\DefaultIcon",
        r"edof.Document.Editor.1",
    ]:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{classes}\\{sub}")
        except OSError:
            pass
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass
    return True, ".edof association removed."


# ─────────────────────────────────────────────────────────────────────────────
# Linux
# ─────────────────────────────────────────────────────────────────────────────

DESKTOP_ENTRY = """\
[Desktop Entry]
Type=Application
Name=EDOF Viewer
Comment=View EDOF documents
Exec={exec_cmd} %f
Terminal=false
MimeType=application/x-edof;
Categories=Office;Viewer;
"""

MIME_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-edof">
    <comment>EDOF Document</comment>
    <glob pattern="*.edof"/>
  </mime-type>
</mime-info>
"""


def _associate_linux():
    home = Path.home()
    apps_dir = home / ".local" / "share" / "applications"
    mime_dir = home / ".local" / "share" / "mime" / "packages"
    apps_dir.mkdir(parents=True, exist_ok=True)
    mime_dir.mkdir(parents=True, exist_ok=True)

    viewer = _find_viewer_executable()

    # 1. MIME type
    (mime_dir / "edof.xml").write_text(MIME_XML, encoding="utf-8")

    # 2. .desktop file
    desktop_path = apps_dir / "edof-viewer.desktop"
    desktop_path.write_text(
        DESKTOP_ENTRY.format(exec_cmd=viewer),
        encoding="utf-8",
    )
    desktop_path.chmod(0o755)

    # 3. Update database
    for cmd in (["update-mime-database", str(home / ".local" / "share" / "mime")],
                 ["update-desktop-database", str(apps_dir)],
                 ["xdg-mime", "default", "edof-viewer.desktop", "application/x-edof"]):
        try:
            subprocess.run(cmd, check=False, capture_output=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return True, ".edof associated with edof-viewer (Linux desktop entry installed)."


def _unassociate_linux():
    home = Path.home()
    for f in (home / ".local" / "share" / "applications" / "edof-viewer.desktop",
              home / ".local" / "share" / "mime" / "packages" / "edof.xml"):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass
    try:
        subprocess.run(
            ["update-mime-database", str(home / ".local" / "share" / "mime")],
            check=False, capture_output=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return True, ".edof association removed."


if __name__ == "__main__":
    # CLI invocation: `python -m edof._apps.file_assoc associate|unassociate|status`
    if len(sys.argv) < 2:
        print("usage: file_assoc.py [associate|unassociate|status]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "associate":
        associate_edof_files()
        print("OK: .edof files now associated with edof-viewer")
    elif cmd == "unassociate":
        unassociate_edof_files()
        print("OK: .edof file association removed")
    elif cmd == "status":
        print(current_association_status())
    else:
        print(f"unknown command: {cmd}")
        sys.exit(1)
