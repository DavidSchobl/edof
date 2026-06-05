"""edof Viewer — read-only viewer for .edof files.

A lightweight QMainWindow that opens an .edof file, renders pages, lets the
user navigate (next/prev/first/last), zoom (fit page / fit width / 100% /
custom), print, and export to PDF. Cannot edit objects — that is the
EdofEditor's job.

Designed to be the default association for .edof files on the user's OS so
that double-clicking a .edof file opens it for viewing (similar to how PDF
files open in a PDF viewer by default).

Entry point: edof-viewer [filepath]
"""
from __future__ import annotations

import os
import sys
from typing import Optional, List

try:
    from PyQt6.QtCore import Qt, QSize, QTimer
    from PyQt6.QtGui import (
        QPixmap, QImage, QAction, QKeySequence, QIcon, QPainter,
    )
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QToolBar, QStatusBar, QFileDialog, QMessageBox,
        QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
        QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QPushButton,
        QSizePolicy,
    )
    from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    # Allow the module to import without PyQt6 so non-GUI tooling (and the
    # test suite) can load it. The class below then subclasses a harmless
    # stand-in; main() refuses to run and prints an install hint instead.
    QMainWindow = object

import edof


# ─────────────────────────────────────────────────────────────────────────────
# Render thread (lightweight — just calls render_page)
# ─────────────────────────────────────────────────────────────────────────────

def _pil_to_qpixmap(pil_img):
    """Convert a PIL image to a QPixmap."""
    from io import BytesIO
    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    qimg = QImage()
    qimg.loadFromData(buf.getvalue(), "PNG")
    return QPixmap.fromImage(qimg)


# ─────────────────────────────────────────────────────────────────────────────
# Main Viewer Window
# ─────────────────────────────────────────────────────────────────────────────

VIEWER_QSS = """
QMainWindow, QWidget { background: #1e1e2e; color: #e0e0e8; font: 10pt 'Segoe UI'; }
QToolBar { background: #131320; border: none; padding: 4px; spacing: 2px; }
QToolButton { background: #2a2a3a; color: #e0e0e8; border: none; padding: 5px 10px;
              border-radius: 3px; font: 10pt 'Segoe UI'; min-width: 32px; min-height: 26px; }
QToolButton:hover { background: #4a4ada; }
QToolButton:disabled { color: #555; background: #1e1e2e; }
QStatusBar { background: #131320; color: #aaa; font: 9pt 'Segoe UI'; }
QMenuBar { background: #131320; color: #e0e0e8; }
QMenuBar::item:selected { background: #4a4ada; }
QMenu { background: #2a2a3a; color: #e0e0e8; border: 1px solid #444; }
QMenu::item:selected { background: #4a4ada; }
QGraphicsView { background: #2a2a3a; border: none; }
QPushButton { background: #2a2a3a; color: #e0e0e8; border: 1px solid #444;
              padding: 4px 10px; border-radius: 3px; min-height: 24px; }
QPushButton:hover { background: #4a4ada; border-color: #4a4ada; }
QComboBox, QSpinBox { background: #2a2a3a; color: #e0e0e8; border: 1px solid #444;
                       padding: 3px 5px; border-radius: 3px; min-height: 22px; }
QLabel { color: #ddd; }
"""


ZOOM_PRESETS = ["Fit page", "Fit width", "50%", "75%", "100%", "150%", "200%", "300%"]


class EdofViewer(QMainWindow):
    """Read-only viewer for .edof files."""

    def __init__(self, filepath: Optional[str] = None):
        super().__init__()
        self.setWindowTitle(f"EDOF Viewer {edof.__version__}")
        # v4.2.2: window / taskbar icon
        try:
            from edof._apps.assets import icon_path
            _ip = icon_path("edof-viewer.ico") or icon_path("edof-viewer.png")
            if _ip:
                self.setWindowIcon(QIcon(_ip))
        except Exception:
            pass
        self.resize(1100, 800)
        self.setStyleSheet(VIEWER_QSS)

        self._doc: Optional[edof.Document] = None
        self._filepath: Optional[str] = None
        self._page_idx = 0
        self._zoom_mode = "Fit page"   # one of ZOOM_PRESETS or "custom"
        self._zoom_factor = 1.0
        self._pixmap_item = None

        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._update_actions()

        # Render timer (debounced)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._do_render)

        if filepath and os.path.isfile(filepath):
            self.open_file(filepath)

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Central widget: a QGraphicsView showing the rendered page pixmap
        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene, self)
        self._view.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self._view.setBackgroundBrush(Qt.GlobalColor.darkGray)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setCentralWidget(self._view)

        self._status = QStatusBar()
        self._status_lbl = QLabel("No document loaded")
        self._status.addWidget(self._status_lbl)
        self.setStatusBar(self._status)

    def _build_menus(self):
        mb = self.menuBar()

        fm = mb.addMenu("&File")
        self._act_open = QAction("&Open…", self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.triggered.connect(self._on_open)
        fm.addAction(self._act_open)

        # v4.2.1: open the current document in the editor
        self._act_edit = QAction("Open in &Editor", self)
        self._act_edit.setShortcut(QKeySequence("Ctrl+E"))
        self._act_edit.triggered.connect(self._open_in_editor)
        fm.addAction(self._act_edit)

        self._act_export_pdf = QAction("Export as &PDF…", self)
        self._act_export_pdf.triggered.connect(self._on_export_pdf)
        fm.addAction(self._act_export_pdf)

        self._act_export_png = QAction("Export current page as PNG…", self)
        self._act_export_png.triggered.connect(self._on_export_png)
        fm.addAction(self._act_export_png)

        fm.addSeparator()
        self._act_print = QAction("&Print…", self)
        self._act_print.setShortcut(QKeySequence.StandardKey.Print)
        self._act_print.triggered.connect(self._on_print)
        fm.addAction(self._act_print)

        fm.addSeparator()
        self._act_quit = QAction("&Quit", self)
        self._act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self._act_quit.triggered.connect(self.close)
        fm.addAction(self._act_quit)

        # View menu
        vm = mb.addMenu("&View")
        self._act_first = QAction("First page", self)
        self._act_first.setShortcut("Ctrl+Home")
        self._act_first.triggered.connect(lambda: self._goto_page(0))
        vm.addAction(self._act_first)

        self._act_prev = QAction("Previous page", self)
        self._act_prev.setShortcut("PgUp")
        self._act_prev.triggered.connect(lambda: self._goto_page(self._page_idx - 1))
        vm.addAction(self._act_prev)

        self._act_next = QAction("Next page", self)
        self._act_next.setShortcut("PgDown")
        self._act_next.triggered.connect(lambda: self._goto_page(self._page_idx + 1))
        vm.addAction(self._act_next)

        self._act_last = QAction("Last page", self)
        self._act_last.setShortcut("Ctrl+End")
        self._act_last.triggered.connect(
            lambda: self._goto_page(len(self._doc.pages) - 1) if self._doc else None
        )
        vm.addAction(self._act_last)

        vm.addSeparator()
        self._act_zoom_in = QAction("Zoom in", self)
        self._act_zoom_in.setShortcut("Ctrl++")
        self._act_zoom_in.triggered.connect(lambda: self._zoom_step(1.25))
        vm.addAction(self._act_zoom_in)

        self._act_zoom_out = QAction("Zoom out", self)
        self._act_zoom_out.setShortcut("Ctrl+-")
        self._act_zoom_out.triggered.connect(lambda: self._zoom_step(0.8))
        vm.addAction(self._act_zoom_out)

        self._act_fit_page = QAction("Fit page", self)
        self._act_fit_page.setShortcut("Ctrl+0")
        self._act_fit_page.triggered.connect(lambda: self._set_zoom_mode("Fit page"))
        vm.addAction(self._act_fit_page)

        self._act_fit_width = QAction("Fit width", self)
        self._act_fit_width.setShortcut("Ctrl+1")
        self._act_fit_width.triggered.connect(lambda: self._set_zoom_mode("Fit width"))
        vm.addAction(self._act_fit_width)

        # Help menu
        hm = mb.addMenu("&Help")
        act_about = QAction("About edof Viewer…", self)
        act_about.triggered.connect(self._on_about)
        hm.addAction(act_about)

        act_associate = QAction("File association (.edof)…", self)
        act_associate.triggered.connect(self._on_associate)
        hm.addAction(act_associate)

        act_donate = QAction("💖 Support the developer…", self)
        act_donate.triggered.connect(self._on_donate)
        hm.addAction(act_donate)

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)

        tb.addAction(self._act_open)
        tb.addSeparator()
        tb.addAction(self._act_first)
        tb.addAction(self._act_prev)

        # Page indicator
        self._page_spin = QSpinBox()
        self._page_spin.setMinimum(1)
        self._page_spin.setMaximum(1)
        self._page_spin.setFixedWidth(60)
        self._page_spin.valueChanged.connect(lambda v: self._goto_page(v - 1))
        tb.addWidget(self._page_spin)
        self._page_total_lbl = QLabel(" / 1 ")
        tb.addWidget(self._page_total_lbl)

        tb.addAction(self._act_next)
        tb.addAction(self._act_last)
        tb.addSeparator()

        tb.addAction(self._act_zoom_out)
        # Zoom dropdown
        self._zoom_cb = QComboBox()
        self._zoom_cb.setEditable(False)
        self._zoom_cb.addItems(ZOOM_PRESETS)
        self._zoom_cb.setCurrentText("Fit page")
        self._zoom_cb.currentTextChanged.connect(self._on_zoom_changed)
        self._zoom_cb.setFixedWidth(90)
        tb.addWidget(self._zoom_cb)
        tb.addAction(self._act_zoom_in)

        tb.addSeparator()
        tb.addAction(self._act_print)
        tb.addAction(self._act_export_pdf)

    # ─────────────────────────────────────────────────────────────────────────
    # Document loading
    # ─────────────────────────────────────────────────────────────────────────

    def open_file(self, filepath: str):
        try:
            doc = edof.load(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Open failed",
                f"Could not open '{filepath}':\n\n{e}")
            return

        self._doc = doc
        self._filepath = filepath
        self._page_idx = 0
        self.setWindowTitle(f"{os.path.basename(filepath)} — EDOF Viewer {edof.__version__}")

        self._page_spin.blockSignals(True)
        self._page_spin.setMaximum(max(1, len(doc.pages)))
        self._page_spin.setValue(1)
        self._page_spin.blockSignals(False)
        self._page_total_lbl.setText(f" / {len(doc.pages)} ")

        self._update_actions()
        self._schedule_render()

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open .edof file", "",
            "EDOF Documents (*.edof);;All Files (*)"
        )
        if path:
            self.open_file(path)

    # ─────────────────────────────────────────────────────────────────────────
    # Navigation
    # ─────────────────────────────────────────────────────────────────────────

    def _goto_page(self, idx: int):
        if not self._doc: return
        idx = max(0, min(idx, len(self._doc.pages) - 1))
        if idx == self._page_idx and self._pixmap_item is not None:
            return
        self._page_idx = idx
        self._page_spin.blockSignals(True)
        self._page_spin.setValue(idx + 1)
        self._page_spin.blockSignals(False)
        self._update_actions()
        self._schedule_render()

    def _update_actions(self):
        has_doc = self._doc is not None
        has_pages = has_doc and len(self._doc.pages) > 0
        self._act_export_pdf.setEnabled(has_doc)
        self._act_export_png.setEnabled(has_pages)
        self._act_print.setEnabled(has_doc)

        if has_pages:
            n = len(self._doc.pages)
            at_first = self._page_idx <= 0
            at_last = self._page_idx >= n - 1
            self._act_first.setEnabled(not at_first)
            self._act_prev.setEnabled(not at_first)
            self._act_next.setEnabled(not at_last)
            self._act_last.setEnabled(not at_last)
        else:
            for a in (self._act_first, self._act_prev,
                       self._act_next, self._act_last):
                a.setEnabled(False)

    # ─────────────────────────────────────────────────────────────────────────
    # Zoom
    # ─────────────────────────────────────────────────────────────────────────

    def _on_zoom_changed(self, text):
        self._set_zoom_mode(text)

    def _set_zoom_mode(self, mode: str):
        self._zoom_mode = mode
        self._zoom_cb.blockSignals(True)
        idx = self._zoom_cb.findText(mode)
        if idx >= 0:
            self._zoom_cb.setCurrentIndex(idx)
        self._zoom_cb.blockSignals(False)

        # Convert preset to factor
        if mode == "Fit page" or mode == "Fit width":
            pass  # handled in _do_render
        elif mode.endswith("%"):
            try:
                self._zoom_factor = float(mode.rstrip("%")) / 100.0
            except ValueError:
                self._zoom_factor = 1.0
        self._schedule_render()

    def _zoom_step(self, factor: float):
        # Switch to custom percentage mode
        if self._zoom_mode in ("Fit page", "Fit width"):
            # Compute current effective factor from view transform
            self._zoom_factor = self._view.transform().m11() * 1.0
        new_f = self._zoom_factor * factor
        new_f = max(0.1, min(8.0, new_f))
        self._zoom_factor = new_f
        # Set custom percentage
        pct = f"{int(new_f * 100)}%"
        self._zoom_mode = pct
        self._zoom_cb.blockSignals(True)
        # Add to dropdown if not present
        if self._zoom_cb.findText(pct) < 0:
            self._zoom_cb.addItem(pct)
        self._zoom_cb.setCurrentText(pct)
        self._zoom_cb.blockSignals(False)
        self._schedule_render()

    # ─────────────────────────────────────────────────────────────────────────
    # Rendering
    # ─────────────────────────────────────────────────────────────────────────

    def _schedule_render(self):
        self._render_timer.start(50)

    def _do_render(self):
        if not self._doc or not self._doc.pages:
            self._scene.clear()
            self._pixmap_item = None
            self._status_lbl.setText("No document loaded")
            return
        page = self._doc.pages[self._page_idx]
        try:
            from edof.engine.renderer import render_page
            # Render at DPI suitable for current zoom (use 96 base; double for high zoom)
            zoom = self._zoom_factor if self._zoom_mode not in ("Fit page", "Fit width") else 1.0
            target_dpi = max(72, min(300, int(96 * max(1.0, zoom))))
            img = render_page(page, self._doc.resources,
                               self._doc.variables, dpi=target_dpi)
        except Exception as e:
            QMessageBox.critical(self, "Render error", str(e))
            return

        pixmap = _pil_to_qpixmap(img)
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        # Apply zoom
        self._view.resetTransform()
        if self._zoom_mode == "Fit page":
            self._view.fitInView(self._pixmap_item.boundingRect(),
                                  Qt.AspectRatioMode.KeepAspectRatio)
        elif self._zoom_mode == "Fit width":
            # Scale so pixmap width fits viewport width
            vw = self._view.viewport().width()
            pw = pixmap.width()
            if pw > 0:
                scale = vw / pw
                self._view.scale(scale, scale)
        else:
            # Custom factor — pixmap was rendered at target_dpi which is
            # 96 * zoom_factor. The view transform should be identity, so
            # the pixmap shows at exactly the requested zoom.
            pass

        # Update status
        n = len(self._doc.pages)
        self._status_lbl.setText(
            f"Page {self._page_idx+1} of {n}  •  "
            f"{page.width}×{page.height} mm  •  "
            f"{len(page.objects)} objects  •  zoom: {self._zoom_mode}"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom_mode in ("Fit page", "Fit width") and self._pixmap_item:
            self._do_render()

    # ─────────────────────────────────────────────────────────────────────────
    # Export & print
    # ─────────────────────────────────────────────────────────────────────────

    def _on_export_pdf(self):
        if not self._doc: return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as PDF",
            self._filepath.replace(".edof", ".pdf") if self._filepath else "document.pdf",
            "PDF Files (*.pdf)"
        )
        if not path: return
        try:
            self._doc.export_pdf(path)
            QMessageBox.information(self, "Export complete",
                f"Saved PDF to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_export_png(self):
        if not self._doc or not self._doc.pages: return
        page = self._doc.pages[self._page_idx]
        suggested = (self._filepath.replace(".edof", f"_page{self._page_idx+1}.png")
                     if self._filepath else "page.png")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export current page as PNG", suggested,
            "PNG Files (*.png);;JPEG Files (*.jpg)"
        )
        if not path: return
        try:
            self._doc.export_bitmap(path, page=self._page_idx, dpi=300)
            QMessageBox.information(self, "Export complete", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_print(self):
        if not self._doc: return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(os.path.basename(self._filepath) if self._filepath else "edof")
        dlg = QPrintDialog(printer, self)
        dlg.setOption(QPrintDialog.PrintDialogOption.PrintToFile, True)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return
        # Render each page to a pixmap and paint onto printer
        from edof.engine.renderer import render_page
        painter = QPainter(printer)
        try:
            for i, page in enumerate(self._doc.pages):
                if i > 0:
                    printer.newPage()
                target_dpi = printer.resolution()
                img = render_page(page, self._doc.resources, self._doc.variables, dpi=target_dpi)
                pixmap = _pil_to_qpixmap(img)
                rect = printer.pageRect(QPrinter.Unit.DevicePixel)
                # Scale pixmap to page (keep aspect)
                target = pixmap.scaled(int(rect.width()), int(rect.height()),
                                        Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap(int(rect.x()), int(rect.y()), target)
        finally:
            painter.end()

    # ─────────────────────────────────────────────────────────────────────────
    # Help & misc
    # ─────────────────────────────────────────────────────────────────────────

    def _on_about(self):
        QMessageBox.about(self, "About edof Viewer",
            f"<h2>edof Viewer {edof.__version__}</h2>"
            f"<p>A lightweight read-only viewer for <code>.edof</code> documents.</p>"
            f"<p>For editing, use <code>edof-editor</code> instead.</p>"
            f"<p><b>Documentation:</b> "
            f"<a href='https://davidschobl.github.io/edof/'>davidschobl.github.io/edof</a><br>"
            f"<b>Source:</b> "
            f"<a href='https://github.com/DavidSchobl/edof'>github.com/DavidSchobl/edof</a></p>"
            f"<p><b>Support development:</b> "
            f"<a href='https://ko-fi.com/davidschobl'>Ko-fi</a> &nbsp;|&nbsp; "
            f"<a href='https://github.com/sponsors/DavidSchobl'>GitHub Sponsors</a></p>"
            f"<p>License: MIT &nbsp;|&nbsp; © 2025 DavidSchobl</p>"
        )

    def _on_associate(self):
        try:
            from edof._apps._assoc_dialog import manage_association
        except Exception as e:
            QMessageBox.warning(self, "File association",
                                f"Could not load file association module: {e}")
            return
        manage_association(self)

    def _on_donate(self):
        try:
            import webbrowser
            webbrowser.open("https://ko-fi.com/davidschobl")
        except Exception:
            pass

    def _open_in_editor(self):
        """v4.2.1: launch edof-editor, opening the currently viewed file."""
        import shutil, subprocess
        from PyQt6.QtWidgets import QMessageBox
        exe = shutil.which("edof-editor")
        if exe:
            args = [exe]
        else:
            args = [sys.executable, "-m", "edof._apps.editor"]
        if self._filepath:
            args.append(self._filepath)
        try:
            subprocess.Popen(args, close_fds=True)
        except Exception as e:
            QMessageBox.warning(
                self, "Open in Editor",
                "Could not launch the editor.\n"
                "Make sure it is installed: pip install \"edof[all]\"\n\n"
                f"({e})")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Console entry point — `edof-viewer [filepath]`."""
    if not _HAS_QT:
        print("ERROR: PyQt6 is not installed.")
        print("Install with: pip install edof[viewer]")
        sys.exit(1)

    # v4.2.4: own taskbar identity so Windows shows the EDOF icon, not Python's.
    try:
        from edof._apps.assets import set_windows_app_id
        set_windows_app_id("DavidSchobl.EDOF.Viewer")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("EDOF Viewer")
    app.setApplicationVersion(edof.__version__)
    try:
        from edof._apps.assets import icon_path
        _ip = icon_path("edof-viewer.ico") or icon_path("edof-viewer.png")
        if _ip:
            app.setWindowIcon(QIcon(_ip))
    except Exception:
        pass

    # Optional file argument
    filepath = None
    args = sys.argv[1:]
    for a in args:
        if a.startswith("-"): continue
        if os.path.isfile(a):
            filepath = a
            break

    win = EdofViewer(filepath=filepath)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
