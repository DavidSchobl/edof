"""Shared .edof file-association dialog.

The user chooses *here* (inside the EDOF app) which app opens .edof files on
double-click; the choice is then registered with the OS. Used by both the
editor and the viewer so the experience is identical.
"""
from __future__ import annotations


def manage_association(parent=None):
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
        QPushButton, QMessageBox, QFrame,
    )
    from edof._apps.file_assoc import (
        associate_edof_files, unassociate_edof_files, current_association_status,
    )

    status = current_association_status()
    is_assoc = "associated" in status.lower() and "not " not in status.lower()
    editor_default = "editor" in status.lower()

    dlg = QDialog(parent)
    dlg.setWindowTitle("File association (.edof)")
    dlg.setMinimumWidth(420)
    v = QVBoxLayout(dlg)

    v.addWidget(QLabel(f"<b>Current status:</b> {status}"))
    info = QLabel(
        "Choose which app opens a <code>.edof</code> file when you double-click "
        "it. You decide here, inside EDOF; the other app stays available via "
        "right-click \u2192 Open With. Files show the EDOF icon either way."
    )
    info.setWordWrap(True)
    v.addWidget(info)

    rb_view = QRadioButton("Open with EDOF Viewer (read-only)")
    rb_edit = QRadioButton("Open with EDOF Editor")
    grp = QButtonGroup(dlg)
    grp.addButton(rb_view)
    grp.addButton(rb_edit)
    (rb_edit if editor_default else rb_view).setChecked(True)
    v.addWidget(rb_view)
    v.addWidget(rb_edit)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    v.addWidget(line)

    row = QHBoxLayout()
    btn_reg = QPushButton("Register / Update")
    btn_rm = QPushButton("Remove association")
    btn_rm.setEnabled(is_assoc)
    btn_close = QPushButton("Close")
    row.addWidget(btn_reg)
    row.addWidget(btn_rm)
    row.addStretch(1)
    row.addWidget(btn_close)
    v.addLayout(row)

    note = QLabel(
        "<small>On Windows this is per-user (no admin needed); you may need to "
        "log out and back in for the Explorer icon to refresh.</small>"
    )
    note.setWordWrap(True)
    v.addWidget(note)

    def _do_register():
        app = "editor" if rb_edit.isChecked() else "viewer"
        try:
            ok, msg = associate_edof_files(default_app=app)
            (QMessageBox.information if ok else QMessageBox.warning)(
                dlg, "File association", msg)
            if ok:
                dlg.accept()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(dlg, "File association", str(e))

    def _do_remove():
        try:
            ok, msg = unassociate_edof_files()
            (QMessageBox.information if ok else QMessageBox.warning)(
                dlg, "File association", msg)
            if ok:
                dlg.accept()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(dlg, "File association", str(e))

    btn_reg.clicked.connect(_do_register)
    btn_rm.clicked.connect(_do_remove)
    btn_close.clicked.connect(dlg.reject)
    dlg.exec()
