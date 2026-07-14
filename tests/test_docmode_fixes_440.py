"""v4.4.0: document-mode bug round: preview commit protection, variable panel
occurrences + multi-select, hf single click, export without view marks."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication
from edof.format.document import Document
from edof.format.document_body import DocumentBody, Paragraph
from edof.format.document_boxes import DocumentTextBox
from edof.format.styles import TextRun
from edof.engine.document_paginate import (paginate_document,
                                           find_document_header_on_page)

_APP = None


def _ensure_app():
    global _APP
    _APP = QApplication.instance() or QApplication([])


def _doc_with_header_var():
    doc = Document()
    page = doc.add_page(width=210, height=297)
    doc.margins = (15.0,) * 4
    doc.mode = "document"
    doc.body = DocumentBody()
    doc.body.page_margins_mm = (15.0,) * 4
    doc.body.header_enabled = True
    doc.body.header_runs = [TextRun(text="Menu: "),
                            TextRun(text="U Lva", rid="ridh1",
                                    var_name="restaurant")]
    tb = DocumentTextBox()
    tb.transform.x = 15; tb.transform.y = 15
    tb.transform.width = 180; tb.transform.height = 267
    tb.style.padding = 0.0
    tb.runs = [TextRun(text="obsah")]; tb.text = "obsah"
    page.objects.append(tb)
    paginate_document(doc)
    return doc


def test_preview_mirror_never_commits_to_hf_template():
    """The cycle bug: with a batch row previewed, the inline hf editor shows
    MIRRORED substituted runs; a commit fired in that state must write the
    LIVE runs, not the preview values, into the template."""
    _ensure_app()
    import edof._apps.editor as E
    from edof.batch.model import ObjectRef, BatchRow
    from edof.engine.document_paginate import HF_HEADER_ID
    doc = _doc_with_header_var()
    cfg = doc.batch
    col = cfg.add_column(ObjectRef([HF_HEADER_ID]), "run.text",
                         "restaurant", "text")
    col.run_id = "ridh1"
    row = BatchRow(values={col.column_id: "U Orla"})

    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    h = find_document_header_on_page(doc.pages[0])
    cv._start_inline(h)
    assert cv._inline_hf_role == "header"
    # preview projects the row; the mirror swaps the editor runs
    cv.set_batch_preview_row(row, page_idx=0)
    ied = cv._inline_widget
    mirrored = "".join(r.text or "" for r in ied._runs)
    assert "U Orla" in mirrored, "mirror should show the row value"
    # clicking into the batch panel commits the editor
    cv._confirm_inline()
    tmpl_text = "".join(r.text or "" for r in doc.body.header_runs)
    assert "U Orla" not in tmpl_text, \
        "preview values must NEVER land in the header template"
    assert "U Lva" in tmpl_text


def test_variable_runs_span_occurrences():
    from edof._apps.editor import _variable_runs
    from edof.format.objects import TextBox
    tb = TextBox()
    tb.runs = [TextRun(text="a ", rid="r1", var_name="v1"),
               TextRun(text="mezera "),
               TextRun(text="b", rid="r1", var_name="v1"),
               TextRun(text=" c", rid="r2", var_name="v2")]
    out = _variable_runs(tb)
    assert out == [("r1", "v1", 2), ("r2", "v2", 1)]


def test_focus_text_variables_keeps_vid_list():
    _ensure_app()
    import edof._apps.editor as E
    doc = Document()
    page = doc.add_page(width=120, height=60)
    tb = page.add_textbox(10, 10, 100, 30, "aaa bbb")
    tb.runs = [TextRun(text="aaa", rid="r1", var_name="v1"),
               TextRun(text=" "),
               TextRun(text="bbb", rid="r2", var_name="v2")]
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    vids = ["vrun:%s:r1" % tb.id, "vrun:%s:r2" % tb.id]
    cv.focus_text_variables(vids)
    assert set(cv._selected_var_rids) == {"r1", "r2"}
    assert cv._selected_var_vids == vids
    # single focus narrows the list back to one
    cv.focus_text_variable(tb.id, "r1")
    assert cv._selected_var_vids == ["vrun:%s:r1" % tb.id]


def test_export_suppresses_view_marks(tmp_path):
    """Show Variables ON must not leak the rainbow into exports."""
    from edof.engine.text_engine import (set_show_variables, show_variables,
                                         set_focus_var_rids)
    from edof.export.bitmap import export_page_bitmap
    from PIL import Image
    doc = Document()
    page = doc.add_page(width=80, height=30)
    tb = page.add_textbox(5, 5, 70, 20, "VARTEXT")
    tb.runs = [TextRun(text="VARTEXT", rid="rx", var_name="vx",
                       font_size=8.0)]
    p_on = str(tmp_path / "on.png")
    p_off = str(tmp_path / "off.png")
    set_show_variables(False); set_focus_var_rids(None)
    export_page_bitmap(doc, 0, p_off, dpi=96)
    set_show_variables(True); set_focus_var_rids({"rx"})
    try:
        export_page_bitmap(doc, 0, p_on, dpi=96)
        assert show_variables() is True, "export must restore the toggle"
    finally:
        set_show_variables(False); set_focus_var_rids(None)
    a = Image.open(p_on).convert("RGB")
    b = Image.open(p_off).convert("RGB")
    import PIL.ImageChops as IC
    assert IC.difference(a, b).getbbox() is None, \
        "export with Show Variables ON must equal export with it OFF"


def test_single_click_enters_hf_band():
    _ensure_app()
    import edof._apps.editor as E
    from PyQt6.QtCore import QPointF, Qt, QEvent
    from PyQt6.QtGui import QMouseEvent
    doc = _doc_with_header_var()
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    h = find_document_header_on_page(doc.pages[0])
    from edof.engine.transform import mm_to_px
    t = h.transform
    x = mm_to_px(t.x + t.width / 2, cv._dpi)
    y = mm_to_px(t.y + t.height / 2, cv._dpi)
    vp = cv.mapFromScene(x, y)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress,
                     QPointF(float(vp.x()), float(vp.y())),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    assert cv._try_enter_hf_inline(ev) is True
    assert cv._inline_hf_role == "header"


# ── round 2 (David's feedback): linked variables, typing boundary, anchors ──

def test_linked_variables_keep_identity_and_share_value():
    """Linking B to A (extra_run_ids) fills both spans with one value while
    BOTH entities keep their rid, name and panel entry."""
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    from edof._apps.editor import _variable_runs
    from edof.format.objects import TextBox
    doc = Document()
    page = doc.add_page(width=120, height=60)
    tb = TextBox()
    tb.runs = [TextRun(text="U Lva", rid="ridA", var_name="nameA"),
               TextRun(text=" a "),
               TextRun(text="U Orla", rid="ridB", var_name="nameB")]
    tb.text = "U Lva a U Orla"
    tb.transform.x = 10; tb.transform.y = 10
    tb.transform.width = 100; tb.transform.height = 30
    page.objects.append(tb)
    cfg = doc.batch
    col = cfg.add_column(build_ref(page, tb), "run.text", "nameA", "text")
    col.run_id = "ridA"
    col.extra_run_ids = ["ridB"]
    row = BatchRow(page_target=0, values={col.column_id: "U Medveda"})
    apply_row_to_document(cfg, doc, row)
    ra = [r for r in tb.runs if r.rid == "ridA"][0]
    rb = [r for r in tb.runs if r.rid == "ridB"][0]
    assert ra.text == "U Medveda" and rb.text == "U Medveda"
    assert rb.var_name == "nameB", "linked variable keeps its name"
    vs = _variable_runs(tb)
    assert [(v[0], v[1]) for v in vs] == [("ridA", "nameA"),
                                          ("ridB", "nameB")], \
        "both entities must stay in the panel"
    # roundtrip keeps the link
    from edof.format.serializer import EdofSerializer
    doc2 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(doc))
    col2 = doc2.batch.columns[0]
    assert list(col2.extra_run_ids) == ["ridB"]


def test_typing_after_span_does_not_extend_it():
    _ensure_app()
    import edof._apps.editor as E
    doc = Document()
    page = doc.add_page(width=120, height=60)
    tb = page.add_textbox(10, 10, 100, 30, "abc VAR")
    tb.runs = [TextRun(text="abc "),
               TextRun(text="VAR", rid="r1", var_name="v1",
                       link="https://x.cz", anchor="a1")]
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv._start_inline(tb)
    ied = cv._inline_widget
    ied._cursor = len("abc VAR"); ied._anchor = None
    ied._insert_text(" dal")
    tail = [r for r in ied._runs if "dal" in (r.text or "")][0]
    assert tail.rid is None and tail.link is None and tail.anchor is None
    # typing INSIDE the span still belongs to it
    ied._cursor = len("abc V"); ied._anchor = None
    ied._insert_text("X")
    inside = [r for r in ied._runs if "X" in (r.text or "")][0]
    assert inside.rid == "r1"


def test_anchor_removal_and_show_anchors_render():
    _ensure_app()
    import edof._apps.editor as E
    from edof.engine.text_engine import (set_show_anchors, show_anchors,
                                         suppress_view_marks)
    from edof.engine.renderer import render_document, clear_object_cache
    doc = Document()
    page = doc.add_page(width=100, height=40)
    tb = page.add_textbox(5, 5, 90, 25, "CILTEXT")
    tb.runs = [TextRun(text="CILTEXT", anchor="anch_z", anchor_name="cil",
                       font_size=8.0)]
    # toggle ON changes render, OFF is default
    assert show_anchors() is False
    clear_object_cache()
    base = render_document(doc, dpi=96)[0].convert("RGB")
    set_show_anchors(True)
    clear_object_cache()
    marked = render_document(doc, dpi=96)[0].convert("RGB")
    import PIL.ImageChops as IC
    assert IC.difference(base, marked).getbbox() is not None
    # exports suppress the mark even while ON
    with suppress_view_marks():
        clear_object_cache()
        exported = render_document(doc, dpi=96)[0].convert("RGB")
    assert IC.difference(base, exported).getbbox() is None
    set_show_anchors(False)
    clear_object_cache()
    # removal via the editor API
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv._start_inline(tb)
    ied = cv._inline_widget
    ied._anchor = 0; ied._cursor = 7
    assert ied.selection_anchor() == "anch_z"
    assert ied.clear_anchor_in_selection() is True
    ied.sync_to_tb_silent()
    assert not any(getattr(r, "anchor", None) for r in tb.runs)


def test_var_checkbox_multiselect_state():
    _ensure_app()
    import edof._apps.editor as E
    doc = Document()
    page = doc.add_page(width=120, height=60)
    tb = page.add_textbox(10, 10, 100, 30, "aaa bbb")
    tb.runs = [TextRun(text="aaa", rid="r1", var_name="v1"),
               TextRun(text=" "),
               TextRun(text="bbb", rid="r2", var_name="v2")]
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    panel = E.ObjectListPanel(cv)
    panel.refresh()
    v1 = "vrun:%s:r1" % tb.id
    v2 = "vrun:%s:r2" % tb.id
    panel._on_var_checkbox(v1, True)
    panel._on_var_checkbox(v2, True)
    assert cv._checked_var_vids == {v1, v2}
    assert set(cv._selected_var_rids) == {"r1", "r2"}
    panel._on_var_checkbox(v1, False)
    assert cv._checked_var_vids == {v2}


def test_undo_caret_goes_to_undone_change_site():
    """Ctrl+Z places the caret at the site of the change being undone, not at
    the (unrelated) spot stored with the older snapshot."""
    _ensure_app()
    from edof._apps.editor import _UnifiedHistory
    doc = Document(); doc.add_page(width=100, height=50)
    h = _UnifiedHistory()
    h.push(doc, ("body", 5), "start")
    h.push(doc, ("body", 50), "edit far away")
    res = h.undo()
    assert res is not None
    _doc, ctx = res
    assert ctx == ("body", 50), "caret must follow the UNDONE change"
    # redo goes back to the reapplied change's site (unchanged behavior)
    res2 = h.redo()
    assert res2 is not None and res2[1] == ("body", 50)
    # object-op step (ctx None): fall back to the restored step's ctx
    h2 = _UnifiedHistory()
    h2.push(doc, ("body", 7), "text step")
    h2.push(doc, None, "object step")
    r3 = h2.undo()
    assert r3 is not None and r3[1] == ("body", 7)


def test_hf_band_click_via_press_release_sequence():
    """The single-click switch runs on RELEASE (deferred), so the press keeps
    its normal bookkeeping; body stays visible and typing lands in the band."""
    _ensure_app()
    import time
    import edof._apps.editor as E
    from PyQt6.QtCore import QPointF, Qt, QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    from edof.engine.document_paginate import find_document_body_on_page
    from edof.engine.transform import mm_to_px
    app = QApplication.instance()
    doc = _doc_with_header_var()
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.resize(900, 1000); cv.show()
    app.processEvents()
    body = find_document_body_on_page(doc.pages[0])
    cv._start_inline(body)
    app.processEvents()
    h = find_document_header_on_page(doc.pages[0])
    t = h.transform
    x = mm_to_px(t.x + t.width / 2, cv._dpi)
    y = mm_to_px(t.y + t.height / 2, cv._dpi)
    vp = cv.mapFromScene(x, y)
    pos = QPointF(float(vp.x()), float(vp.y()))
    pe = QMouseEvent(QEvent.Type.MouseButtonPress, pos,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    re = QMouseEvent(QEvent.Type.MouseButtonRelease, pos,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    cv.mousePressEvent(pe); app.processEvents()
    cv.mouseReleaseEvent(re); app.processEvents()
    t0 = time.time()
    while time.time() - t0 < 0.5:
        app.processEvents(); time.sleep(0.01)
    assert cv._inline_hf_role == "header"
    body2 = find_document_body_on_page(doc.pages[0])
    assert body2.visible, "body must not stay hidden after the switch"
    ied = cv._inline_widget
    ied._insert_text("Z")
    assert "Z" in "".join(r.text or "" for r in ied._runs)


def test_click_switching_body_header_body():
    """Refactor: ONE synchronous switch path. Header click enters the band,
    body click returns to body editing, template gets the committed text."""
    _ensure_app()
    import time
    import edof._apps.editor as E
    from PyQt6.QtCore import QPointF, Qt, QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    from edof.format.document_boxes import DocumentTextBox
    from edof.engine.document_paginate import find_document_body_on_page
    from edof.engine.transform import mm_to_px
    app = QApplication.instance()
    doc = _doc_with_header_var()
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.resize(900, 1000); cv.show()
    app.processEvents()
    body = find_document_body_on_page(doc.pages[0])
    cv._start_inline(body)
    app.processEvents()

    def click(x_mm, y_mm):
        x = mm_to_px(x_mm, cv._dpi); y = mm_to_px(y_mm, cv._dpi)
        vp = cv.mapFromScene(x, y)
        pos = QPointF(float(vp.x()), float(vp.y()))
        pe = QMouseEvent(QEvent.Type.MouseButtonPress, pos,
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        re = QMouseEvent(QEvent.Type.MouseButtonRelease, pos,
                         Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        cv.mousePressEvent(pe); app.processEvents()
        cv.mouseReleaseEvent(re); app.processEvents()
        t0 = time.time()
        while time.time() - t0 < 0.3:
            app.processEvents(); time.sleep(0.01)

    h = find_document_header_on_page(doc.pages[0])
    t = h.transform
    click(t.x + t.width / 2, t.y + t.height / 2)
    assert cv._inline_hf_role == "header"
    cv._inline_widget._insert_text("Q")
    # back into the body: header commits, BODY editing resumes
    click(100, 120)
    assert cv._inline_hf_role is None
    assert isinstance(cv._inline_obj, DocumentTextBox)
    assert "Q" in "".join(r.text or "" for r in doc.body.header_runs)
    # and once more into the band
    h2 = find_document_header_on_page(doc.pages[0])
    click(h2.transform.x + 5, h2.transform.y + h2.transform.height / 2)
    assert cv._inline_hf_role == "header"


def test_switch_takes_keyboard_focus_from_panels():
    """A consumed press skips Qt's focus-on-click; the switch must move the
    keyboard focus to the freshly opened editor even when it sat in a side
    panel (this is why typing into the header did nothing)."""
    _ensure_app()
    import time
    import edof._apps.editor as E
    from PyQt6.QtCore import QPointF, Qt, QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication, QLineEdit
    from edof.engine.document_paginate import find_document_body_on_page
    from edof.engine.transform import mm_to_px
    app = QApplication.instance()
    doc = _doc_with_header_var()
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.resize(900, 1000); cv.show()
    # a foreign widget holds the keyboard focus (like a batch panel field)
    stray = QLineEdit(); stray.show(); stray.setFocus()
    app.processEvents()
    body = find_document_body_on_page(doc.pages[0])
    cv._start_inline(body)
    app.processEvents()
    stray.setFocus(); app.processEvents()      # steal focus back
    h = find_document_header_on_page(doc.pages[0])
    t = h.transform
    x = mm_to_px(t.x + t.width / 2, cv._dpi)
    y = mm_to_px(t.y + t.height / 2, cv._dpi)
    vp = cv.mapFromScene(x, y)
    pos = QPointF(float(vp.x()), float(vp.y()))
    pe = QMouseEvent(QEvent.Type.MouseButtonPress, pos,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    re = QMouseEvent(QEvent.Type.MouseButtonRelease, pos,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    cv.mousePressEvent(pe); app.processEvents()
    cv.mouseReleaseEvent(re)
    t0 = time.time()
    while time.time() - t0 < 0.4:
        app.processEvents(); time.sleep(0.01)
    assert cv._inline_hf_role == "header"
    fw = app.focusWidget()
    assert fw is not stray, "focus must leave the side panel"
    assert fw is cv._inline_widget or fw is cv or fw is cv.viewport(), \
        ("focus must land in the editor chain, got %r" % fw)
    stray.deleteLater()


def test_preview_lock_releases_on_edit_intent():
    """THE 'can't type into the header' root cause: an active batch-row
    preview locks the template read-only and keystrokes were silently eaten.
    Clicking into a band now drops the preview, and typing into an already
    open read-only editor drops it too and processes the key."""
    _ensure_app()
    import time
    import edof._apps.editor as E
    from PyQt6.QtCore import QPointF, Qt, QEvent
    from PyQt6.QtGui import QMouseEvent, QKeyEvent
    from PyQt6.QtWidgets import QApplication
    from edof.batch.model import ObjectRef, BatchRow
    from edof.engine.document_paginate import HF_HEADER_ID
    from edof.engine.transform import mm_to_px
    app = QApplication.instance()
    doc = _doc_with_header_var()
    cfg = doc.batch
    col = cfg.add_column(ObjectRef([HF_HEADER_ID]), "run.text",
                         "restaurant", "text")
    col.run_id = "ridh1"
    row = BatchRow(values={col.column_id: "U Orla"})
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.resize(900, 1000); cv.show()
    app.processEvents()
    cv.set_batch_preview_row(row, page_idx=0)     # template lock ON
    assert cv._batch_template_locked()

    # 1) click into the header band: the switch drops the preview and the
    #    editor opens WRITABLE
    h = find_document_header_on_page(doc.pages[0])
    t = h.transform
    x = mm_to_px(t.x + t.width / 2, cv._dpi)
    y = mm_to_px(t.y + t.height / 2, cv._dpi)
    vp = cv.mapFromScene(x, y)
    pos = QPointF(float(vp.x()), float(vp.y()))
    pe = QMouseEvent(QEvent.Type.MouseButtonPress, pos,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    re = QMouseEvent(QEvent.Type.MouseButtonRelease, pos,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    cv.mousePressEvent(pe); app.processEvents()
    cv.mouseReleaseEvent(re)
    t0 = time.time()
    while time.time() - t0 < 0.4:
        app.processEvents(); time.sleep(0.01)
    assert cv._inline_hf_role == "header"
    assert cv._batch_preview_row is None, "preview must yield to editing"
    ied = cv._inline_widget
    assert not getattr(ied, "_read_only", False)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_W,
                   Qt.KeyboardModifier.NoModifier, "W")
    ied.keyPressEvent(ev)
    assert "W" in "".join(r.text or "" for r in ied._runs), \
        "typing must work right after the click"

    # 2) already open READ-ONLY editor: a keystroke drops the preview and is
    #    processed (not silently eaten)
    cv.set_batch_preview_row(row, page_idx=0)
    app.processEvents()
    assert getattr(cv._inline_widget, "_read_only", False)
    ied2 = cv._inline_widget
    ev2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Q,
                    Qt.KeyboardModifier.NoModifier, "Q")
    ied2.keyPressEvent(ev2)
    assert cv._batch_preview_row is None
    assert "Q" in "".join(r.text or "" for r in ied2._runs)


def test_hf_band_overlay_never_covers_content():
    """THE 'typing invisible' root cause: the band decoration paints in
    drawForeground (OVER the scene, over the band's text and the open
    editor). An opaque fill there hid everything. The band interior must
    stay untouched (no fill), and while the band is being edited the
    decoration is skipped entirely."""
    _ensure_app()
    import edof._apps.editor as E
    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtCore import QRectF
    from edof.engine.transform import mm_to_px
    doc = _doc_with_header_var()          # header has text -> no hint label
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.resize(900, 1000); cv.show()
    h = find_document_header_on_page(doc.pages[0])
    t = h.transform
    bx = mm_to_px(t.x, cv._dpi); by = mm_to_px(t.y, cv._dpi)
    bw = mm_to_px(t.width, cv._dpi); bh = mm_to_px(t.height, cv._dpi)

    def paint_over_red():
        img = QImage(1400, 1400, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 0, 0))
        p = QPainter(img)
        try:
            cv.drawForeground(p, QRectF(0, 0, 1400, 1400))
        finally:
            p.end()
        return img

    # 1) not editing: interior must remain RED (outline may touch the edge)
    img = paint_over_red()
    cx = int(bx + bw / 2); cy = int(by + bh / 2)
    c = img.pixelColor(cx, cy)
    assert (c.red(), c.green(), c.blue()) == (255, 0, 0), \
        "band interior must not be filled (it paints OVER the content)"

    # 2) editing this band: decoration skipped entirely, even the outline
    cv._inline_id = h.id
    img2 = paint_over_red()
    edge = img2.pixelColor(int(bx) + 1, int(by) + 1)
    assert (edge.red(), edge.green(), edge.blue()) == (255, 0, 0), \
        "no band decoration may paint while the band is being edited"
    cv._inline_id = None


def test_repagination_settles_with_hf_style_padding():
    """The batch-panel flicker: a stored header/footer template style with
    non-zero padding re-armed an endless zero -> restore -> zero cycle, so
    EVERY repagination reported changed=True while a band was enabled. A
    second paginate with no real edits must report changed=False."""
    from edof.engine.document_paginate import paginate_document
    doc = _doc_with_header_var()
    # poison the stored band style the way old documents have it
    h = find_document_header_on_page(doc.pages[0])
    sd = h.style.to_dict()
    sd["padding"] = 1.0
    doc.body.header_style = sd
    paginate_document(doc)              # may report changed (style applied)
    r2 = paginate_document(doc)
    assert r2["changed"] is False, \
        "no-op repagination must settle even with a padded band style"
    r3 = paginate_document(doc)
    assert r3["changed"] is False
