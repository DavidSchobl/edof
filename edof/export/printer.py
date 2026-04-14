# edof/export/printer.py
"""
Cross-platform printing support.

Primary method: render pages to PNG temp files, then:
  • Windows: os.startfile(path, 'print')  – uses default app print dialog
  • macOS:   lpr command
  • Linux:   lpr / lp command

For GUI applications, prefer using QPrintPreviewDialog from edof_editor.py
which provides a proper print preview without any external dependencies.
"""
from __future__ import annotations
import io
import os
import platform
import subprocess
import tempfile
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from edof.format.document import Document


def list_printers() -> List[str]:
    """Return available printer names. Empty list if unavailable."""
    system = platform.system()
    try:
        if system == "Windows":
            try:
                import win32print
                return [p[2] for p in win32print.EnumPrinters(2)]
            except ImportError:
                pass
            # Fallback: use wmic
            out = subprocess.check_output(
                ["wmic", "printer", "get", "name"],
                text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            return [l.strip() for l in out.splitlines()
                    if l.strip() and l.strip() != "Name"]
        else:
            out = subprocess.check_output(["lpstat", "-p"], text=True, timeout=5)
            return [l.split()[1] for l in out.splitlines()
                    if l.startswith("printer")]
    except Exception:
        return []


def print_document(
    doc:      "Document",
    printer:  Optional[str] = None,
    pages:    Optional[List[int]] = None,
    dpi:      int = 150,
    copies:   int = 1,
) -> None:
    """
    Print selected pages (default: all) to the given printer.

    On Windows uses os.startfile('print') which opens the system print dialog.
    On macOS / Linux uses the lpr command.
    """
    from edof.engine.renderer import render_page
    from edof.exceptions import EdofPrintError

    page_indices = pages if pages is not None else list(range(len(doc.pages)))
    system = platform.system()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_files: List[str] = []

        for idx in page_indices:
            page = doc.pages[idx]
            try:
                img  = render_page(page, doc.resources, doc.variables, dpi=dpi)
                path = os.path.join(tmpdir, f"edof_print_{idx:04d}.png")
                img.save(path, format="PNG", dpi=(dpi, dpi))
                tmp_files.append(path)
            except Exception as e:
                raise EdofPrintError(f"Render failed for page {idx}: {e}") from e

        for _ in range(copies):
            for path in tmp_files:
                _send(path, printer, system)


def _send(path: str, printer: Optional[str], system: str) -> None:
    from edof.exceptions import EdofPrintError
    try:
        if system == "Windows":
            # os.startfile with 'print' verb opens the Windows print dialog
            # for the default associated application (e.g. Photos, Paint).
            # This is the most reliable method without pywin32.
            os.startfile(os.path.abspath(path), "print")
        elif system == "Darwin":
            cmd = ["lpr", path]
            if printer:
                cmd += ["-P", printer]
            subprocess.check_call(cmd, timeout=30)
        else:  # Linux / BSD
            # Try lpr first, then lp
            for cmd_name in ("lpr", "lp"):
                try:
                    cmd = [cmd_name, path]
                    if printer:
                        cmd += [("-P" if cmd_name == "lpr" else "-d"), printer]
                    subprocess.check_call(cmd, timeout=30)
                    return
                except FileNotFoundError:
                    continue
            raise EdofPrintError(
                "No print command found (lpr / lp). "
                "Install CUPS:  sudo apt install cups"
            )
    except EdofPrintError:
        raise
    except Exception as e:
        raise EdofPrintError(f"Print failed: {e}") from e
