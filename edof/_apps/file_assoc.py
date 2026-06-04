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


def current_association_status() -> str:
    """Return human-readable description of current .edof file association."""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ".edof") as k:
                cls, _ = winreg.QueryValueEx(k, "")
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                 f"{cls}\\shell\\open\\command") as k:
                cmd, _ = winreg.QueryValueEx(k, "")
            return f"associated with: {cmd}"
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
    """Register .edof in HKCU\\Software\\Classes (per-user, no admin needed)."""
    import winreg

    viewer = _find_viewer_executable()
    # Build command line. Use double-quotes around the executable path.
    if viewer.startswith('"') or viewer.startswith("'"):
        cmd = f'{viewer} "%1"'
    else:
        cmd = f'"{viewer}" "%1"'

    progid = "edof.Document.1"
    classes = r"Software\Classes"

    # 1. .edof → progid
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                              f"{classes}\\.edof",
                              0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, progid)
        winreg.SetValueEx(k, "Content Type", 0, winreg.REG_SZ, "application/x-edof")

    # 2. progid metadata
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                              f"{classes}\\{progid}",
                              0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "EDOF Document")
        winreg.SetValueEx(k, "FriendlyTypeName", 0, winreg.REG_SZ,
                           "Easy Document Format File")

    # 3. progid\shell\open\command → "edof-viewer" "%1"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                              f"{classes}\\{progid}\\shell\\open\\command",
                              0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)

    # 4. DefaultIcon (use viewer exe as icon source if available)
    if "edof-viewer" in viewer and os.path.isfile(viewer.strip('"').split()[0]):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                  f"{classes}\\{progid}\\DefaultIcon",
                                  0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{viewer.strip(chr(34))}",0')

    # 5. Notify shell that associations changed
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST,
                                               None, None)
    except Exception:
        pass


def _unassociate_windows():
    import winreg
    classes = r"Software\Classes"
    for sub in [
        r".edof",
        r"edof.Document.1\shell\open\command",
        r"edof.Document.1\shell\open",
        r"edof.Document.1\shell",
        r"edof.Document.1\DefaultIcon",
        r"edof.Document.1",
    ]:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{classes}\\{sub}")
        except OSError:
            pass


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
