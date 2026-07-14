"""v4.3.6.28: text-variable lifecycle sync, one-step undo, change range,
focus highlight, gradient stop alpha. Headless (offscreen)."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication
from edof import Document


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _mk_canvas_with_var(app):
    """Canvas + textbox with a variable span, inline editor OPEN (so the
    editor holds a live COPY of the runs)."""
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = Document()
    page = doc.add_page(width=120, height=60)
    tb = page.add_textbox(10, 10, 90, 20, "Restaurace U Lva")
    cv = E.EdofCanvas()
    cv.set_document(doc, 0)
    cv._start_inline(tb)
    ied = cv._inline_widget
    assert ied is not None
    # select "U Lva" (offset 11..16) and make it a variable
    ied._anchor = 11
    ied._cursor = 16
    rid = ied.make_variable_from_selection("restaurant")
    assert rid
    ied.sync_to_tb_silent()
    tpl = EdofBatchTemplatePanel(cv)
    tpl.set_document(doc)
    return doc, page, tb, cv, ied, tpl, rid


def _runs_with_rid(obj, rid):
    return [r for r in (getattr(obj, "runs", None) or [])
            if getattr(r, "rid", None) == rid]


def test_remove_variable_clears_inline_copy(app):
    doc, page, tb, cv, ied, tpl, rid = _mk_canvas_with_var(app)
    assert _runs_with_rid(tb, rid)
    tpl.remove_run_variable([(tb, rid)])
    # page object clean
    assert not _runs_with_rid(tb, rid)
    # the OPEN inline editor's copy must be clean too, or the next reflow
    # resurrects the variable from the stale copy
    assert not [r for r in ied._runs if getattr(r, "rid", None) == rid]


def test_rename_variable_updates_inline_copy(app):
    doc, page, tb, cv, ied, tpl, rid = _mk_canvas_with_var(app)
    tpl.rename_run_variable([(tb, rid)], "podnik")
    names = {getattr(r, "var_name", None) for r in _runs_with_rid(tb, rid)}
    assert names == {"podnik"}
    inames = {getattr(r, "var_name", None) for r in ied._runs
              if getattr(r, "rid", None) == rid}
    assert inames == {"podnik"}


def test_change_range_moves_rid_and_keeps_columns(app):
    doc, page, tb, cv, ied, tpl, rid = _mk_canvas_with_var(app)
    # bind a column to the rid so we can check it survives
    from edof.batch.model import build_ref
    ref = build_ref(page, tb)
    col = doc.batch.add_column(ref, "run.text", "restaurant", "text")
    col.run_id = rid
    # new range: "Restaurace" (0..10)
    ied._anchor = 0
    ied._cursor = 10
    tpl.change_run_variable_range(tb, rid)
    spans = _runs_with_rid(tb, rid)
    assert spans and "".join(r.text for r in spans) == "Restaurace"
    # old span lost the rid
    for r in tb.runs:
        if "U Lva" in (r.text or ""):
            assert getattr(r, "rid", None) != rid
    # the column is still bound to the same rid
    assert any(getattr(c, "run_id", "") == rid for c in doc.batch.columns)
    # name survived
    assert {getattr(r, "var_name", None) for r in spans} == {"restaurant"}


def test_orphan_gc_rebuilds_batch_panels(app):
    doc, page, tb, cv, ied, tpl, rid = _mk_canvas_with_var(app)
    from edof.batch.model import build_ref
    ref = build_ref(page, tb)
    col = doc.batch.add_column(ref, "run.text", "restaurant", "text")
    col.run_id = rid

    class _MW:                                  # canvas.parent() stand-in
        pass
    mw = _MW()
    rebuilds = []
    tpl.rebuild()                               # prime
    orig = tpl.rebuild
    tpl.rebuild = lambda: (rebuilds.append(1), orig())
    mw._batch_tpl = tpl
    cv.parent = lambda: mw
    # prime the change detector, then delete the variable's runs entirely
    cv._sync_variable_entities()
    for r in list(tb.runs):
        if getattr(r, "rid", None) == rid:
            tb.runs.remove(r)
    tb.text = "".join(r.text or "" for r in tb.runs)
    cv._sync_variable_entities()
    # column bound to the vanished rid is gone AND the panel was rebuilt
    assert not any(getattr(c, "run_id", "") == rid for c in doc.batch.columns)
    assert rebuilds


def test_remove_variable_single_undo_step(app):
    """remove -> ONE Ctrl+Z restores the variable (no dead presses)."""
    import edof._apps.editor as E
    doc, page, tb, cv, ied, tpl, rid = _mk_canvas_with_var(app)

    class _History:
        def __init__(self): self.stack = []
        def push(self, doc, ctx=None, desc=""):
            from edof.format.serializer import EdofSerializer
            self.stack.append((EdofSerializer.to_bytes(doc), desc))

    class _Ed:
        def __init__(self, doc):
            self.doc = doc
            self.history = _History()
            self._modified = False
        def _commit_pending_body(self): pass
        def _commit_pending_obj(self): pass
        def _upd_title(self): pass
        def push_history(self, desc="Batch edit"):
            self.history.push(self.doc, None, desc)

    ed = _Ed(doc)
    tpl._editor = ed
    tpl.remove_run_variable([(tb, rid)])
    # exactly ONE labelled step for the op (the begin flush pushes nothing)
    descs = [d for (_b, d) in ed.history.stack]
    assert descs == ["Remove variable"]


def test_focus_var_rids_render_marks_span(app):
    """set_focus_var_rids highlights the span at render even when the global
    Show Variables toggle is off."""
    from edof.engine.text_engine import set_focus_var_rids, set_show_variables
    from edof.engine.renderer import render_document, clear_object_cache
    doc = Document()
    page = doc.add_page(width=100, height=40)
    tb = page.add_textbox(5, 5, 90, 25, "plain VARIED tail")
    # make "VARIED" a variable run manually
    from edof.format.styles import TextRun
    tb.runs = [TextRun(text="plain "),
               TextRun(text="VARIED", rid="ridfocus0001", var_name="v"),
               TextRun(text=" tail")]
    set_show_variables(False)
    set_focus_var_rids(None)
    clear_object_cache()
    base = render_document(doc, dpi=96)[0]
    set_focus_var_rids({"ridfocus0001"})
    clear_object_cache()
    marked = render_document(doc, dpi=96)[0]
    set_focus_var_rids(None)
    clear_object_cache()
    import PIL.ImageChops as IC
    diff = IC.difference(base.convert("RGB"), marked.convert("RGB"))
    assert diff.getbbox() is not None       # rainbow mark changed pixels


def test_gradient_stop_alpha_applies_on_rect_shape(app):
    """v4.3.6.28: gradient stops with alpha 255 -> 0 must fade the fill (the
    rect/ellipse branch used to overwrite the gradient alpha with the mask)."""
    from edof.format.styles import Gradient
    from edof.engine.renderer import render_document
    doc = Document()
    page = doc.add_page(width=100, height=50)
    sh = page.add_shape("rectangle", x=10, y=10, width=80, height=30)
    sh.fill.type = "gradient"
    sh.fill.gradient = Gradient(type="linear", angle=0,
                                stops=[(0.0, (255, 0, 0, 255)),
                                       (1.0, (255, 0, 0, 0))])
    img = render_document(doc, dpi=96)[0].convert("RGB")
    w, h = img.size
    left = img.getpixel((int(w * 0.15), h // 2))
    right = img.getpixel((int(w * 0.85), h // 2))
    assert left[1] < 60                     # nearly opaque red
    assert right[1] > 200                   # faded to the white page
