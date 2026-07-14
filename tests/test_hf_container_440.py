"""v4.4.0: header/footer as a container of objects + hf batch variables.
Headless (offscreen where Qt is needed)."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from edof.format.document import Document
from edof.format.document_body import DocumentBody, Paragraph
from edof.format.document_boxes import DocumentTextBox
from edof.format.styles import TextRun
from edof.format.objects import TextBox, Shape
from edof.engine.document_paginate import (
    paginate_document, sync_hf_objects_all, writeback_hf_clone,
    find_document_header_on_page, find_document_footer_on_page,
    HF_HEADER_ID, HF_FOOTER_ID)


def _doc_mode_doc(text="hello world", header=True, footer=False):
    doc = Document()
    page = doc.add_page(width=210, height=297)
    doc.margins = (15.0, 15.0, 15.0, 15.0)
    doc.mode = "document"
    doc.body = DocumentBody()
    doc.body.page_margins_mm = (15.0, 15.0, 15.0, 15.0)
    doc.body.paragraphs = [Paragraph(runs=[TextRun(text=text)],
                                     style_id="Normal")]
    doc.body.header_enabled = header
    doc.body.footer_enabled = footer
    tb = DocumentTextBox()
    tb.transform.x = 15.0; tb.transform.y = 15.0
    tb.transform.width = 180.0; tb.transform.height = 267.0
    tb.style.padding = 0.0
    # paginate projects the box runs back to body.paragraphs, so the text
    # must live on the box
    tb.runs = [TextRun(text=text)]
    tb.text = text
    page.objects.append(tb)
    paginate_document(doc)
    return doc


_APP = None


def _ensure_app():
    """Keep a strong reference to the QApplication (a discarded instance is
    GC'd and every later QWidget constructor aborts)."""
    global _APP
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])


def _add_page_via_break(doc):
    """Force a second page by overflowing the body with a long text."""
    from edof.engine.document_paginate import find_document_body_on_page
    b = find_document_body_on_page(doc.pages[0])
    long_text = (b.text or "") + (" lorem ipsum dolor sit amet" * 900)
    b.runs = [TextRun(text=long_text)]
    b.text = long_text
    paginate_document(doc)
    assert len(doc.pages) >= 2
    return doc


def test_band_boxes_have_canonical_ids():
    doc = _doc_mode_doc(header=True, footer=True)
    h = find_document_header_on_page(doc.pages[0])
    f = find_document_footer_on_page(doc.pages[0])
    assert h is not None and h.id == HF_HEADER_ID
    assert f is not None and f.id == HF_FOOTER_ID


def test_canonical_id_migration_of_old_boxes():
    doc = _doc_mode_doc(header=True)
    h = find_document_header_on_page(doc.pages[0])
    h.id = "random_old_id_123"        # simulate a pre-4.4 file
    paginate_document(doc)
    h2 = find_document_header_on_page(doc.pages[0])
    assert h2.id == HF_HEADER_ID


def test_hf_container_clones_on_every_page():
    doc = _doc_mode_doc(header=True)
    _add_page_via_break(doc)
    logo = Shape("rectangle")
    logo.transform.x = 15; logo.transform.y = 3
    logo.transform.width = 20; logo.transform.height = 8
    doc.body.header_objects.append(logo)
    paginate_document(doc)
    for pg in doc.pages:
        clones = [o for o in pg.objects if o.id == logo.id]
        assert len(clones) == 1
        assert getattr(clones[0], "_hf_container", None) == "header"


def test_hf_container_template_removal_removes_clones():
    doc = _doc_mode_doc(header=True)
    _add_page_via_break(doc)
    logo = Shape("rectangle")
    doc.body.header_objects.append(logo)
    paginate_document(doc)
    assert any(o.id == logo.id for o in doc.pages[1].objects)
    doc.body.header_objects.remove(logo)
    paginate_document(doc)
    for pg in doc.pages:
        assert not any(o.id == logo.id for o in pg.objects)


def test_writeback_hf_clone_updates_template_and_pages():
    doc = _doc_mode_doc(header=True)
    _add_page_via_break(doc)
    tb = TextBox()
    tb.text = "U Lva"
    tb.runs = [TextRun(text="U Lva")]
    tb.transform.x = 100; tb.transform.y = 3
    tb.transform.width = 60; tb.transform.height = 8
    doc.body.header_objects.append(tb)
    paginate_document(doc)
    clone_p2 = next(o for o in doc.pages[1].objects if o.id == tb.id)
    clone_p2.transform.x = 42.0
    clone_p2.runs[0].text = "U Orla"
    clone_p2.text = "U Orla"
    assert writeback_hf_clone(doc, clone_p2)
    tmpl = doc.body.header_objects[0]
    assert tmpl.transform.x == 42.0 and tmpl.text == "U Orla"
    clone_p1 = next(o for o in doc.pages[0].objects if o.id == tb.id)
    assert clone_p1.transform.x == 42.0 and clone_p1.text == "U Orla"
    # non-clone object: no writeback
    other = Shape("rectangle")
    doc.pages[0].objects.append(other)
    assert not writeback_hf_clone(doc, other)


def test_hf_container_serialization_roundtrip():
    from edof.format.serializer import EdofSerializer
    doc = _doc_mode_doc(header=True, footer=True)
    logo = Shape("ellipse")
    logo.transform.x = 1; logo.transform.y = 2
    doc.body.header_objects.append(logo)
    note = TextBox(); note.text = "pata"; note.runs = [TextRun(text="pata")]
    doc.body.footer_objects.append(note)
    doc2 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(doc))
    assert len(doc2.body.header_objects) == 1
    assert doc2.body.header_objects[0].id == logo.id
    assert isinstance(doc2.body.footer_objects[0], TextBox)
    assert doc2.body.footer_objects[0].text == "pata"
    paginate_document(doc2)
    assert any(o.id == logo.id for o in doc2.pages[0].objects)


def test_hf_band_variable_rid_survives_pagination_and_batch_applies():
    from edof.batch.model import (ObjectRef, BatchRow, apply_row_to_document)
    doc = _doc_mode_doc(header=True)
    _add_page_via_break(doc)
    # variable span in the header TEMPLATE
    doc.body.header_runs = [
        TextRun(text="Menu: "),
        TextRun(text="U Lva", rid="ridhf0000001", var_name="restaurant")]
    paginate_document(doc)
    for pg in doc.pages:
        h = find_document_header_on_page(pg)
        assert any(getattr(r, "rid", None) == "ridhf0000001"
                   for r in h.runs), "rid must survive template resolution"
    # a column addressed by the canonical band id fills EVERY page
    cfg = doc.batch
    cfg.row_scope = "document"
    col = cfg.add_column(ObjectRef([HF_HEADER_ID]), "run.text",
                         "restaurant", "text")
    col.run_id = "ridhf0000001"
    row = BatchRow(values={col.column_id: "U Orla"})
    n = apply_row_to_document(cfg, doc, row)
    assert n >= 2
    for pg in doc.pages:
        h = find_document_header_on_page(pg)
        assert "U Orla" in (h.text or "")


def test_hf_template_mirror_on_clear_and_rename(qapp=None):
    pytest.importorskip("PyQt6")
    _ensure_app()
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = _doc_mode_doc(header=True)
    doc.body.header_runs = [
        TextRun(text="Menu: "),
        TextRun(text="U Lva", rid="ridhf0000002", var_name="restaurant")]
    paginate_document(doc)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    h = find_document_header_on_page(doc.pages[0])
    tpl.rename_run_variable([(h, "ridhf0000002")], "podnik")
    assert any(getattr(r, "var_name", None) == "podnik"
               for r in doc.body.header_runs), "rename must hit the template"
    tpl.remove_run_variable([(h, "ridhf0000002")])
    assert not any(getattr(r, "rid", None) == "ridhf0000002"
                   for r in doc.body.header_runs), "clear must hit the template"


def test_commit_hf_runs_from_inline_persists_rid():
    pytest.importorskip("PyQt6")
    _ensure_app()
    import edof._apps.editor as E
    doc = _doc_mode_doc(header=True)
    doc.body.header_runs = [TextRun(text="Menu: U Lva")]
    paginate_document(doc)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    h = find_document_header_on_page(doc.pages[0])
    cv._start_inline(h)
    assert getattr(cv, "_inline_hf_role", None) == "header"
    ied = cv._inline_widget
    ied._anchor = 6; ied._cursor = 11        # "U Lva"
    rid = ied.make_variable_from_selection("restaurant")
    assert rid
    ied.sync_to_tb_silent()
    assert cv._commit_hf_runs_from_inline()
    assert any(getattr(r, "rid", None) == rid
               for r in doc.body.header_runs), "rid must land on the template"
    # and it survives a repagination on every page
    paginate_document(doc)
    for pg in doc.pages:
        hh = find_document_header_on_page(pg)
        assert any(getattr(r, "rid", None) == rid for r in hh.runs)


def test_gc_keeps_hf_template_rids():
    pytest.importorskip("PyQt6")
    _ensure_app()
    import edof._apps.editor as E
    from edof.batch.model import ObjectRef
    doc = _doc_mode_doc(header=True)
    doc.body.header_runs = [
        TextRun(text="U Lva", rid="ridhf0000003", var_name="restaurant")]
    paginate_document(doc)
    cfg = doc.batch
    col = cfg.add_column(ObjectRef([HF_HEADER_ID]), "run.text",
                         "restaurant", "text")
    col.run_id = "ridhf0000003"
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv._sync_variable_entities()             # prime
    # toggle the band off: page clones vanish, template still has the rid
    doc.body.header_enabled = False
    paginate_document(doc)
    cv._sync_variable_entities()
    assert any(getattr(c, "run_id", "") == "ridhf0000003"
               for c in doc.batch.columns), "GC must not drop hf template rids"


def test_format_version_bumped_and_compat():
    import edof.version as V
    # 4.4.0 bumped the format to 4.3.0 (hf containers); 4.4.1 to 4.3.1
    # (links). This test pins the FLOOR, not the exact value.
    assert (V.FORMAT_MAJOR, V.FORMAT_MINOR) == (4, 3)
    from edof.version import compatibility
    assert compatibility("4.2.20") == "older"
    assert compatibility(V.FORMAT_VERSION_STR) == "ok"
