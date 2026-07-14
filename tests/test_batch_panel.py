"""UI-level tests for the 3D Batch panel (headless, offscreen)."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication
from edof import Document
from edof.batch import describe_object


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


@pytest.fixture
def panel_ctx(app):
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchPanel
    doc = Document()
    page = doc.add_page(width=100, height=60)
    tb = page.add_textbox(10, 10, 40, 15, "orig")
    sh = page.add_shape("rect", 50, 10, 30, 20)
    cv = E.EdofCanvas()
    cv.set_document(doc, 0)
    panel = EdofBatchPanel(cv)
    panel.set_document(doc)
    return doc, page, tb, sh, cv, panel


def _desc(obj, path):
    return [d for d in describe_object(obj) if d.path == path][0]


def test_panel_starts_empty(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    assert panel._table.rowCount() == 0
    # page scope, single-page fixture -> only "Name" (Page hidden until >1 page)
    assert panel._table.columnCount() == 1


def test_add_column_and_row(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "text"), "Name")
    assert col is not None
    assert col.header() == "Name"
    assert panel._table.columnCount() == 2     # Name + data (Page hidden, single page)
    # add_column_for_object now seeds one record so the variable does something
    assert panel._table.rowCount() == 1
    panel._on_add_row()
    assert panel._table.rowCount() == 2


def test_headers_show_page_column_in_page_scope(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "Name")
    hdrs = [panel._table.horizontalHeaderItem(i).text()
            for i in range(panel._table.columnCount())]
    assert hdrs[0] == "Name"
    assert "Page" not in hdrs            # single-page fixture
    assert "textbox" in hdrs[1] or "Name" in hdrs[1]


def test_document_scope_hides_page_column(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    doc.batch.row_scope = "document"
    panel.rebuild()
    panel.add_column_for_object(tb, _desc(tb, "text"), "Name")
    hdrs = [panel._table.horizontalHeaderItem(i).text()
            for i in range(panel._table.columnCount())]
    assert "Page" not in hdrs
    assert hdrs[0] == "Name"


def test_duplicate_name_highlight(panel_ctx):
    """v4.4.0: duplicate names can no longer exist. The second column with a
    taken name is auto-suffixed at creation, so the duplicate counter stays
    empty."""
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "Name")
    panel.add_column_for_object(sh, _desc(sh, "fill.color"), "Name")
    headers = sorted(c.header() for c in doc.batch.columns)
    assert headers == ["Name", "Name_2"], headers
    assert not doc.batch.duplicate_name_counts()


def test_prune_after_object_deletion(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "Name")
    panel.add_column_for_object(sh, _desc(sh, "fill.color"), "Colour")
    assert len(doc.batch.columns) == 2
    page.objects = [o for o in page.objects if o.id != sh.id]
    panel.prune_after_object_change()
    assert len(doc.batch.columns) == 1
    assert doc.batch.columns[0].header() == "Name"


def test_changed_signal_fires(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    fired = []
    panel.changed.connect(lambda: fired.append(1))
    panel.add_column_for_object(tb, _desc(tb, "text"), "Name")
    assert fired


def test_editor_has_batch_tab(app):
    import edof._apps.editor as E
    doc = Document()
    doc.add_page(width=100, height=60)
    ed = E.EdofEditor()
    ed.doc = doc
    ed._canvas.set_document(doc, 0)
    # right tab = Template panel; bottom dock = Table editor
    assert ed._batch_tpl is not None
    assert ed._batch_panel is not None
    assert ed._right_tabs.count() == 2
    assert ed._right_tabs.tabText(1) == "3D Batch"
    ed._show_batch_tab()
    assert ed._right_tabs.currentWidget() is ed._batch_tpl
    assert ed._batch_tpl._doc is doc


def test_cells_carry_kind_role(panel_ctx):
    from edof._apps.batch_panel import _KIND_ROLE
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "Text")
    panel.add_column_for_object(tb, _desc(tb, "style.alignment"), "Align")
    panel.add_column_for_object(sh, _desc(sh, "fill.color"), "Colour")
    panel._on_add_row()
    base = panel._n_lead()  # Name + Page lead columns
    kinds = [panel._table.item(0, base + i).data(_KIND_ROLE)
             for i in range(len(doc.batch.columns))]
    assert kinds == ["text", "enum", "color"]


def test_color_cell_gets_background(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(sh, _desc(sh, "fill.color"), "Colour")
    panel._on_add_row()
    doc.batch.rows[0].values[col.column_id] = "#00ff00"
    panel.rebuild()
    item = panel._table.item(0, panel._n_lead())   # first data column
    bg = item.background().color()
    assert (bg.red(), bg.green(), bg.blue()) == (0, 255, 0)


def test_enum_choices_available_to_delegate(panel_ctx):
    from edof.batch import find_descriptor
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "style.alignment"), "Align")
    obj = panel._first_object_for_column(col)
    assert obj is not None
    choices = find_descriptor(obj, "style.alignment").choices
    assert "center" in choices


def test_row_projects_to_canvas_without_mutating_document(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "text"), "Text")
    panel._on_add_row()
    doc.batch.rows[0].values[col.column_id] = "PREVIEW"
    panel._project_to_canvas(0)
    # the canvas now carries a non-destructive preview row
    assert cv._batch_preview_row is not None
    assert tb.text == "orig"      # live document untouched


def test_parse_color_helper():
    from edof._apps.batch_panel import _parse_color
    assert _parse_color("#00ff00").getRgb()[:3] == (0, 255, 0)
    assert _parse_color("255,0,0").getRgb()[:3] == (255, 0, 0)
    assert _parse_color("not a colour") is None
    assert _parse_color("") is None


def test_header_uses_type_ordinal_when_unnamed(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    tb2 = page.add_textbox(40, 0, 30, 15, "second")
    c1 = panel.add_column_for_object(tb, _desc(tb, "text"), "")
    c2 = panel.add_column_for_object(tb2, _desc(tb2, "text"), "")
    assert panel._column_label(c1) == "textbox-1.text"
    assert panel._column_label(c2) == "textbox-2.text"


def test_header_flattens_attr_dots(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    c = panel.add_column_for_object(sh, _desc(sh, "fill.color"), "")
    assert panel._column_label(c) == "shape-1.fill-color"


def test_named_variable_overrides_auto_header(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    c = panel.add_column_for_object(tb, _desc(tb, "text"), "")
    assert panel._column_label(c) == "textbox-1.text"
    c.var_name = "Křestní jméno"
    assert panel._column_label(c) == "Křestní jméno"


def test_unique_names_persist_systematic_labels(panel_ctx):
    """v4.4.0: unnamed columns store their systematic label as the real name,
    so headers are unique and survive as [{Header}] tags."""
    doc, page, tb, sh, cv, panel = panel_ctx
    tb2 = page.add_textbox(40, 0, 30, 15, "second")
    c1 = panel.add_column_for_object(tb, _desc(tb, "text"), "")
    c2 = panel.add_column_for_object(tb2, _desc(tb2, "text"), "")
    assert c1.var_name == "textbox-1.text"
    assert c2.var_name == "textbox-2.text"
    assert c1.header() != c2.header()



def test_tree_dialog_returns_checked_with_names(panel_ctx):
    from edof._apps.batch_panel import _AddColumnDialog
    from PyQt6.QtCore import Qt
    doc, page, tb, sh, cv, panel = panel_ctx
    dlg = _AddColumnDialog(tb)
    try:
        # check the first leaf under "Content" and name it via its line edit
        root = dlg._tree
        checked = 0
        for i in range(root.topLevelItemCount()):
            g = root.topLevelItem(i)
            if g.text(0) == "Content":
                for j in range(g.childCount()):
                    leaf = g.child(j)
                    leaf.setCheckState(0, Qt.CheckState.Checked)
                    path = leaf.data(0, dlg._DESC_ROLE)
                    if path in dlg._name_edits:
                        dlg._name_edits[path].setText("MyVar")
                    checked += 1
        dlg._accept()
        pairs = dlg.chosen_pairs()
        assert len(pairs) == checked
        assert any(name == "MyVar" for _d, name in pairs)
    finally:
        dlg.close()
        dlg.deleteLater()


def test_tree_dialog_offers_effects_not_on_object(panel_ctx):
    """v4.3.5.25: effects aren't all pre-listed; you add the one you want via
    '+ Add effect instance', which then appears and is batchable (Path A still
    applies the batched value, creating the effect at apply time)."""
    from edof._apps.batch_panel import _AddColumnDialog
    from PyQt6.QtCore import Qt
    doc, page, tb, sh, cv, panel = panel_ctx
    dlg = _AddColumnDialog(tb)
    root = dlg._tree
    fx = None
    for i in range(root.topLevelItemCount()):
        if root.topLevelItem(i).text(0) == "Layer Effects":
            fx = root.topLevelItem(i)
    assert fx is not None
    # only the master 'All effects' + a hint row until an effect is added
    assert fx.childCount() == 2
    dlg._add_instance("halftone")          # add the effect the object lacked
    fx = None
    for i in range(root.topLevelItemCount()):
        if root.topLevelItem(i).text(0) == "Layer Effects":
            fx = root.topLevelItem(i)
    ht = None
    for i in range(fx.childCount()):
        if fx.child(i).text(0).startswith("halftone"):
            ht = fx.child(i)
    assert ht is not None
    ht.child(0).setCheckState(0, Qt.CheckState.Checked)
    dlg._accept()
    paths = [d.path for d, _ in dlg.chosen_pairs()]
    assert any(p.startswith("effects.halftone.") for p in paths)


def test_color_cell_contrasting_text(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(sh, _desc(sh, "fill.color"), "")
    panel._on_add_row()
    base = panel._n_lead()
    idx = [i for i, c in enumerate(doc.batch.columns)
           if c.attr_path == "fill.color"][0]
    cases = {"#808080": (255, 255, 255),    # grey -> white text
             "#ffffff": (0, 0, 0),          # white -> black text
             "#000000": (255, 255, 255)}    # black -> white text
    for hexv, want_fg in cases.items():
        doc.batch.rows[0].values[col.column_id] = hexv
        panel.rebuild()
        it = panel._table.item(0, base + idx)
        fg = it.foreground().color()
        assert (fg.red(), fg.green(), fg.blue()) == want_fg


def test_rename_variable_via_header_handler(panel_ctx, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "text"), "")
    # page scope -> first data column is at section n_lead
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Příjmení", True)))
    panel._on_header_double_clicked(panel._n_lead())
    assert col.var_name == "Příjmení"
    assert panel._column_label(col) == "Příjmení"


def test_row_name_column_present_and_editable(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    panel._on_add_row()
    hdrs = [panel._table.horizontalHeaderItem(i).text()
            for i in range(panel._table.columnCount())]
    assert hdrs[0] == "Name"
    # write a row name into column 0
    panel._table.item(0, 0).setText("row-A")
    assert doc.batch.rows[0].name == "row-A"


def test_row_name_persists_roundtrip(panel_ctx):
    import tempfile, os
    from edof.format.serializer import EdofSerializer
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    panel._on_add_row()
    doc.batch.rows[0].name = "alpha"
    f = tempfile.mktemp(suffix=".edof")
    try:
        EdofSerializer().save(doc, f)
        d2 = EdofSerializer().load(f)
    finally:
        os.unlink(f)
    assert d2.batch.rows[0].name == "alpha"


def test_color_cell_paints_immediately_on_edit(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(sh, _desc(sh, "fill.color"), "")
    panel._on_add_row()
    cell = panel._table.item(0, panel._n_lead())
    cell.setText("#00ff00")                 # simulates dialog/manual entry
    bg = panel._table.item(0, panel._n_lead()).background().color()
    assert (bg.red(), bg.green(), bg.blue()) == (0, 255, 0)


def test_page_column_hidden_for_single_page(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx   # fixture has ONE page
    panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    panel._on_add_row()
    hdrs = [panel._table.horizontalHeaderItem(i).text()
            for i in range(panel._table.columnCount())]
    assert "Page" not in hdrs
    assert panel._n_lead() == 1


def test_page_column_appears_with_second_page(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    doc.add_page(width=100, height=60)
    panel.rebuild()
    hdrs = [panel._table.horizontalHeaderItem(i).text()
            for i in range(panel._table.columnCount())]
    assert "Page" in hdrs
    assert panel._n_lead() == 2


def _multi_page_ctx(app):
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchPanel
    from edof.batch.model import BatchRow
    doc = Document()
    p0 = doc.add_page(width=100, height=60)
    p1 = doc.add_page(width=100, height=60)
    t0 = p0.add_textbox(0, 0, 30, 15, "a")
    cv = E.EdofCanvas()
    cv.set_document(doc, 0)
    panel = EdofBatchPanel(cv)
    panel.set_document(doc)
    col = panel.add_column_for_object(t0, _desc(t0, "text"), "T")
    doc.batch.rows = [
        BatchRow(page_target=0, name="r0", values={col.column_id: "X0"}),
        BatchRow(page_target=1, name="r1", values={col.column_id: "X1"}),
        BatchRow(page_target=0, name="r2", values={col.column_id: "X2"}),
    ]
    panel.rebuild()
    return doc, cv, panel, col


def test_filter_show_all_lists_every_row(app):
    doc, cv, panel, col = _multi_page_ctx(app)
    panel._filter.setCurrentIndex(0)   # show all
    panel.rebuild()
    assert panel._table.rowCount() == 3


def test_filter_active_page_only(app):
    doc, cv, panel, col = _multi_page_ctx(app)
    panel._filter.setCurrentIndex(1)   # active page only, page 0
    panel.rebuild()
    names = [panel._table.item(r, 0).text() for r in range(panel._table.rowCount())]
    assert names == ["r0", "r2"]


def test_filter_follows_active_page(app):
    doc, cv, panel, col = _multi_page_ctx(app)
    panel._filter.setCurrentIndex(1)
    cv._page_idx = 1
    panel.notify_page_changed()
    names = [panel._table.item(r, 0).text() for r in range(panel._table.rowCount())]
    assert names == ["r1"]


def test_filtered_edit_hits_correct_model_row(app):
    doc, cv, panel, col = _multi_page_ctx(app)
    panel._filter.setCurrentIndex(1)
    cv._page_idx = 1
    panel.notify_page_changed()
    # the only visible row is model row 1 (r1)
    panel._table.item(0, panel._n_lead()).setText("CHANGED")
    assert doc.batch.rows[1].values.get(col.column_id) == "CHANGED"
    assert doc.batch.rows[0].values.get(col.column_id) == "X0"   # untouched


def test_filter_inactive_when_single_page(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx   # single page
    panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    panel.rebuild()
    # the filter cannot do anything with one page
    assert panel._row_filter_active() is False


def test_cell_edit_updates_canvas_projection(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "T"), "T") if False else \
          panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    panel._on_add_row()
    panel._table.setCurrentCell(0, 0)
    # edit the value; canvas projection refreshes without error, no mutation
    panel._table.item(0, panel._n_lead()).setText("LIVE")
    assert tb.text == "orig"      # live doc untouched


def test_page_scope_projection_switches_to_target_page(app):
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchPanel
    from edof.batch.model import BatchRow
    doc = Document()
    p0 = doc.add_page(width=80, height=50)
    p1 = doc.add_page(width=80, height=50)
    t0 = p0.add_textbox(5, 15, 70, 20, "a")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    panel = EdofBatchPanel(cv); panel.set_document(doc)
    col = panel.add_column_for_object(t0, _desc(t0, "text"), "T")
    doc.batch.rows = [BatchRow(page_target=1, values={col.column_id: "X"})]
    panel.rebuild()
    panel._table.setCurrentCell(0, 0)
    panel._project_to_canvas(0)
    # projecting a page-scope row switches the canvas to its target page
    assert cv._page_idx == 1
    assert cv._batch_preview_row is not None


def test_document_scope_projection(app):
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchPanel
    doc = Document()
    p0 = doc.add_page(width=80, height=50)
    p1 = doc.add_page(width=80, height=50)
    t0 = p0.add_textbox(5, 15, 70, 20, "a")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    panel = EdofBatchPanel(cv); panel.set_document(doc)
    doc.batch.row_scope = "document"
    col = panel.add_column_for_object(t0, _desc(t0, "text"), "T")
    panel.rebuild()
    panel._on_add_row()
    panel._table.setCurrentCell(0, 0)
    # document-scope row projects onto the canvas (page not forced)
    panel._project_to_canvas(0)
    assert cv._batch_preview_row is not None


def test_projection_survives_table_changes(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    panel._on_add_row()
    panel._table.setCurrentCell(0, 0)
    panel._project_to_canvas(0)
    # adding another row / removing a column triggers rebuild; must not raise
    panel._on_add_row()
    doc.batch.remove_column(col.column_id)
    panel.rebuild()
    assert tb.text == "orig"      # live doc still untouched




@pytest.fixture
def tpl_ctx(app):
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = Document()
    page = doc.add_page(width=100, height=60)
    tb = page.add_textbox(10, 10, 40, 15, "orig")
    sh = page.add_shape("rect", 50, 10, 30, 20)
    cv = E.EdofCanvas()
    cv.set_document(doc, 0)
    tpl = EdofBatchTemplatePanel(cv)
    tpl.set_document(doc)
    return doc, page, tb, sh, cv, tpl

def test_template_record_list(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    from edof.batch.model import build_ref
    doc.batch.add_column(build_ref(page, tb), "text", "Text", "text")
    tpl._new_record(); tpl._new_record()
    tpl.rebuild()
    assert tpl._rows.count() == 2


def test_template_form_fields_match_columns(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    from edof.batch.model import build_ref
    doc.batch.add_column(build_ref(page, tb), "text", "Text", "text")
    doc.batch.add_column(build_ref(page, sh), "fill.color", "Colour", "color")
    tpl._new_record()
    tpl.rebuild()
    tpl._rows.setCurrentRow(0)
    # Name + 2 variable blocks (single-page fixture -> no Page row)
    assert tpl._form.rowCount() == 3


def test_template_edit_writes_to_model(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    from edof.batch.model import build_ref
    col = doc.batch.add_column(build_ref(page, tb), "text", "Text", "text")
    tpl._new_record()
    tpl.rebuild()
    tpl._rows.setCurrentRow(0)
    tpl._set_val(col.column_id, "HELLO")
    assert doc.batch.rows[0].values.get(col.column_id) == "HELLO"
    assert tb.text == "orig"               # live doc untouched


def test_template_add_and_duplicate_record(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    from edof.batch.model import build_ref
    col = doc.batch.add_column(build_ref(page, tb), "text", "Text", "text")
    tpl._new_record()
    tpl._set_val(col.column_id, "A")
    tpl._dup_record()
    assert len(doc.batch.rows) == 2
    assert doc.batch.rows[1].values.get(col.column_id) == "A"   # deep-copied


def test_template_locked_record_not_editable(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    from edof.batch.model import build_ref
    col = doc.batch.add_column(build_ref(page, tb), "text", "Text", "text")
    tpl._new_record()
    doc.batch.rows[0].locked = True
    tpl.rebuild()
    tpl._rows.setCurrentRow(0)
    # editing a locked record is a no-op
    tpl._set_val(col.column_id, "NOPE")
    assert doc.batch.rows[0].values.get(col.column_id) in (None, "")


def test_demo_rows_separate_from_production(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    doc.batch.rows.clear()                    # drop the auto-seeded record
    panel._on_add_row()                       # production row
    doc.batch.rows[0].values[col.column_id] = "PROD"
    panel._rowset.setCurrentIndex(1)          # switch to demo
    assert panel._table.rowCount() == 0       # demo set empty
    panel._on_add_row()                       # demo row
    panel._table.item(0, panel._n_lead()).setText("DEMO")
    assert len(doc.batch.demo_rows) == 1
    assert len(doc.batch.rows) == 1           # production untouched
    assert doc.batch.demo_rows[0].values.get(col.column_id) == "DEMO"
    assert doc.batch.rows[0].values.get(col.column_id) == "PROD"


def test_export_demo_checkbox_sets_model(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    panel._chk_export_demo.setChecked(True)
    assert doc.batch.export_demo is True
    panel._chk_export_demo.setChecked(False)
    assert doc.batch.export_demo is False


def test_demo_rows_in_template_panel(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    from edof.batch.model import build_ref
    doc.batch.add_column(build_ref(page, tb), "text", "T", "text")
    tpl._rowset.setCurrentIndex(1)            # demo
    tpl._new_record()
    assert tpl._rows.count() == 1
    assert len(doc.batch.demo_rows) == 1


def test_demo_persists_roundtrip(panel_ctx):
    import tempfile, os
    from edof.format.serializer import EdofSerializer
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    panel._rowset.setCurrentIndex(1)
    panel._on_add_row()
    doc.batch.demo_rows[0].values[col.column_id] = "D"
    doc.batch.export_demo = True
    f = tempfile.mktemp(suffix=".edof")
    try:
        EdofSerializer().save(doc, f)
        d2 = EdofSerializer().load(f)
    finally:
        os.unlink(f)
    assert len(d2.batch.demo_rows) == 1
    assert d2.batch.demo_rows[0].values.get(col.column_id) == "D"
    assert d2.batch.export_demo is True


def test_duplicate_row(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    doc.batch.rows.clear()                    # drop the auto-seeded record
    panel._on_add_row()
    doc.batch.rows[0].values[col.column_id] = "A"
    doc.batch.rows[0].name = "one"
    panel.rebuild()
    panel._table.setCurrentCell(0, 0)
    panel._on_dup_row()
    assert len(doc.batch.rows) == 2
    assert doc.batch.rows[1].values.get(col.column_id) == "A"   # deep-copied
    assert doc.batch.rows[1].name == "one copy"                 # inserted after


def test_row_index_labels(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    doc.batch.rows.clear()                    # drop the auto-seeded record
    panel._on_add_row(); panel._on_add_row(); panel._on_add_row()
    labels = [panel._table.verticalHeaderItem(i).text()
              for i in range(panel._table.rowCount())]
    assert labels == ["1", "2", "3"]


def test_copy_paste_rows(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    doc.batch.rows.clear()                    # drop the auto-seeded record
    panel._on_add_row()
    doc.batch.rows[0].values[col.column_id] = "X"
    panel.rebuild()
    panel._table.setCurrentCell(0, 0)
    panel._copy_rows()
    assert len(panel._row_clipboard) == 1
    panel._paste_rows()
    assert len(doc.batch.rows) == 2
    assert doc.batch.rows[1].values.get(col.column_id) == "X"


def test_sort_by_number_column(panel_ctx):
    from edof.batch.model import BatchRow
    doc, page, tb, sh, cv, panel = panel_ctx
    col = panel.add_column_for_object(tb, _desc(tb, "transform.x"), "X")
    doc.batch.rows = [
        BatchRow(values={col.column_id: "30"}),
        BatchRow(values={col.column_id: "10"}),
        BatchRow(values={col.column_id: "20"}),
    ]
    panel.rebuild()
    sec = panel._n_lead()
    panel._on_header_clicked(sec)        # ascending
    vals = [r.values.get(col.column_id) for r in doc.batch.rows]
    assert vals == ["10", "20", "30"]
    panel._on_header_clicked(sec)        # descending
    vals = [r.values.get(col.column_id) for r in doc.batch.rows]
    assert vals == ["30", "20", "10"]


def test_sort_by_name(panel_ctx):
    from edof.batch.model import BatchRow
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    doc.batch.rows = [
        BatchRow(name="charlie"), BatchRow(name="alpha"), BatchRow(name="bravo"),
    ]
    panel.rebuild()
    panel._on_header_clicked(0)          # Name column
    names = [r.name for r in doc.batch.rows]
    assert names == ["alpha", "bravo", "charlie"]


def test_canvas_preview_toggle_clears(panel_ctx):
    doc, page, tb, sh, cv, panel = panel_ctx
    panel.add_column_for_object(tb, _desc(tb, "text"), "T")
    panel._on_add_row()
    panel._table.setCurrentCell(0, 0)
    panel._project_to_canvas(0)
    assert cv._batch_preview_row is not None
    # turning the projection off clears the canvas preview
    panel._canvas_preview_on = False
    cv.clear_batch_preview()
    assert cv._batch_preview_row is None


def test_remove_variable_requires_confirmation(tpl_ctx, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    doc, page, tb, sh, cv, tpl = tpl_ctx
    from edof.batch.model import build_ref
    col = doc.batch.add_column(build_ref(page, tb), "text", "T", "text")
    tpl._new_record()
    tpl.rebuild()
    # answering No keeps the variable
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    tpl._remove_variable(col)
    assert len(doc.batch.columns) == 1
    # answering Yes removes it
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    tpl._remove_variable(col)
    assert len(doc.batch.columns) == 0


def test_canvas_batch_preview_nondestructive(app):
    """The canvas projects a batch row without mutating the live document."""
    import edof._apps.editor as E
    from edof.batch.model import build_ref, BatchRow
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 15, 70, 20, "BASE")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    col = doc.batch.add_column(build_ref(p, tb), "text", "T", "text")
    row = BatchRow(page_target=0, values={col.column_id: "PROJECTED"})
    cv.set_batch_preview_row(row, page_idx=0)
    assert cv._batch_preview_row is row
    assert tb.text == "BASE"            # live doc untouched
    cv.clear_batch_preview()
    assert cv._batch_preview_row is None
    assert tb.text == "BASE"


def test_toggle_off_clears_canvas_projection(app):
    # lighter than spinning a full EdofEditor: a panel projects, then turning
    # its canvas-preview toggle off clears the projection
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    from edof.batch.model import build_ref, BatchRow
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 15, 70, 20, "BASE")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    col = doc.batch.add_column(build_ref(p, tb), "text", "T", "text")
    doc.batch.rows = [BatchRow(page_target=0, values={col.column_id: "X"})]
    tpl.rebuild()
    tpl._project_to_canvas(0)
    assert cv._batch_preview_row is not None
    tpl._on_toggle_canvas_preview(False)
    assert cv._batch_preview_row is None


# ── record mode ──────────────────────────────────────────────────────────────
def test_canvas_edit_mode_banner_state(app):
    import edof._apps.editor as E
    doc = Document()
    doc.add_page(width=80, height=50)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    assert cv._edit_mode == "classic"
    cv.set_edit_mode("batch")
    assert cv._edit_mode == "batch"
    cv.set_edit_mode("classic")
    assert cv._edit_mode == "classic"


def test_recording_creates_columns_from_canvas_edits(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    tpl.start_recording()
    assert tpl._recording
    assert len(doc.batch.rows) >= 1
    # edit on the "canvas" (mutate the live objects), then capture
    tb.text = "CHANGED"
    tb.transform.x = 22.0
    tpl.capture_canvas_edit()
    paths = {c.attr_path for c in doc.batch.columns}
    assert "text" in paths
    assert "transform.x" in paths
    col_text = [c for c in doc.batch.columns if c.attr_path == "text"][0]
    assert doc.batch.rows[0].values.get(col_text.column_id) == "CHANGED"


def test_stop_recording_restores_base_document(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    orig_text = tb.text
    orig_x = tb.transform.x
    tpl.start_recording()
    tb.text = "REC"
    tb.transform.x = 40.0
    tpl.capture_canvas_edit()
    col_text = [c for c in doc.batch.columns if c.attr_path == "text"][0]
    assert doc.batch.rows[0].values.get(col_text.column_id) == "REC"
    tpl.stop_recording()
    # live document restored to baseline
    assert tb.text == orig_text
    assert tb.transform.x == orig_x
    # but the record keeps the captured value
    assert doc.batch.rows[0].values.get(col_text.column_id) == "REC"


def test_cannot_record_into_locked_record(tpl_ctx, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    doc, page, tb, sh, cv, tpl = tpl_ctx
    tpl._new_record()
    doc.batch.rows[0].locked = True
    tpl.rebuild()
    tpl._cur = 0
    # the locked-record warning is modal; stub it so the test doesn't block
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    tpl.start_recording()
    assert not tpl._recording


# ── batch edit mode behaviour (v4.3.5.11) ────────────────────────────────────
def test_batch_edit_toggle_starts_recording(app, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    import edof._apps.editor as E
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    doc = Document()
    p = doc.add_page(width=80, height=50)
    p.add_textbox(5, 15, 70, 20, "x")
    ed = E.EdofEditor()
    ed.doc = doc
    ed._canvas.set_document(doc, 0)
    ed._act_batch_edit.setChecked(True)
    assert ed._canvas._edit_mode == "batch"
    assert ed._batch_tpl._recording
    ed._act_batch_edit.setChecked(False)
    assert ed._canvas._edit_mode == "classic"
    assert not ed._batch_tpl._recording


def test_insert_blocked_in_batch_edit(app, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    import edof._apps.editor as E
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    doc = Document()
    p = doc.add_page(width=80, height=50)
    p.add_textbox(5, 15, 70, 20, "x")
    ed = E.EdofEditor()
    ed.doc = doc
    ed._canvas.set_document(doc, 0)
    ed._act_batch_edit.setChecked(True)
    n0 = len(p.objects)
    ed._ins_shape("ellipse")       # must be refused in batch edit
    assert len(p.objects) == n0
    assert ed._batch_block() is True


def test_properties_edit_records_into_row(app, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    import edof._apps.editor as E
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    sh.fill.color = (0, 0, 0)
    ed = E.EdofEditor()
    ed.doc = doc
    ed._canvas.set_document(doc, 0)
    ed._canvas.set_sel_id(sh.id)
    ed._act_batch_edit.setChecked(True)
    # simulate a Properties edit (mutates the live object, then _on_chg)
    sh.fill.color = (255, 0, 0)
    ed._on_chg()
    cols = [c for c in doc.batch.columns if "fill" in c.attr_path]
    assert cols
    assert doc.batch.rows[0].values.get(cols[0].column_id) == "#ff0000"
    ed._act_batch_edit.setChecked(False)
    # template restored: live fill back to black
    assert sh.fill.color == (0, 0, 0)


# ── v4.3.5.11 polish ─────────────────────────────────────────────────────────
def test_undo_restores_removed_variable(app, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    import edof._apps.editor as E
    from edof.batch.model import build_ref, BatchRow
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 15, 70, 20, "x")
    ed = E.EdofEditor()
    ed.doc = doc
    ed._canvas.set_document(doc, 0)
    ed.history.clear(); ed.history.push(doc, None, "init")
    col = doc.batch.add_column(build_ref(p, tb), "text", "Var", "text")
    doc.batch.rows = [BatchRow(page_target=0, values={col.column_id: "A"})]
    ed.history.push(doc, None, "added")
    ed._batch_tpl.set_document(doc)
    # delete with confirmation auto-Yes
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    ed._batch_tpl._remove_variable(col)
    assert len(ed.doc.batch.columns) == 0
    ed._undo()
    assert len(ed.doc.batch.columns) == 1
    assert ed.doc.batch.columns[0].var_name == "Var"


def test_show_on_canvas_button_visual_state(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    b = tpl._btn_show_on_canvas
    assert b.isChecked()
    assert "Showing" in b.text()
    b.setChecked(False)
    assert b.text() == "Show selected on canvas"


def test_show_on_canvas_disabled_while_recording(tpl_ctx):
    doc, page, tb, sh, cv, tpl = tpl_ctx
    b = tpl._btn_show_on_canvas
    tpl.start_recording()
    assert not b.isEnabled()
    assert "recording" in b.text().lower()
    tpl.stop_recording()
    assert b.isEnabled()


def test_pick_color_standard_helper_exists():
    import edof._apps.batch_panel as BP
    assert hasattr(BP, "_pick_color_standard")
    # it resolves an initial colour from hex / tuple / None without raising
    # (we can't exec the modal dialog headless, just check the import path)
    from edof._apps.editor import EdofColorDialog
    assert hasattr(EdofColorDialog, "get_color")


def test_all_effects_master_in_tree_dialog(app):
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    dlg = _AddColumnDialog(sh)
    root = dlg._tree
    fx = None
    for i in range(root.topLevelItemCount()):
        if root.topLevelItem(i).text(0) == "Layer Effects":
            fx = root.topLevelItem(i)
    assert fx is not None
    # the master 'All effects' is the first leaf under Layer Effects
    labels = [fx.child(i).text(0) for i in range(fx.childCount())]
    assert any(l.startswith("All effects") for l in labels)


def test_master_switch_batches_through_row(app):
    import copy
    from edof import Document, LayerEffect
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    from edof.engine.renderer import render_page
    import numpy as np

    def redpx(d):
        a = np.asarray(render_page(d.pages[0], d.resources, d.variables,
                                   dpi=100).convert("RGB"))
        return int(((a[..., 0].astype(int) - a[..., 1]) > 80).sum())

    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 25, 18, 30, 14)
    sh.fill.color = (0, 0, 0)
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True,
                                  distance=4, color=(255, 0, 0, 255)))
    col = doc.batch.add_column(build_ref(p, sh), "effects.all_enabled",
                               "FX", "enum")
    off = copy.deepcopy(doc)
    apply_row_to_document(off.batch, off,
                          BatchRow(page_target=0, values={col.column_id: "false"}))
    assert redpx(off) == 0
    assert len(off.pages[0].objects[0].effects) == 1   # effect kept
    on = copy.deepcopy(doc)
    apply_row_to_document(on.batch, on,
                          BatchRow(page_target=0, values={col.column_id: "true"}))
    assert redpx(on) > 0


# ── v4.3.5.15 fixes from the log ─────────────────────────────────────────────
def test_record_effect_does_not_leak_to_template(tpl_ctx):
    """Bug: an effect added while recording stayed on the template after stop."""
    from edof import LayerEffect
    doc, page, tb, sh, cv, tpl = tpl_ctx
    assert len(sh.effects) == 0
    tpl.start_recording()
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True, distance=4))
    tpl.capture_canvas_edit()
    assert len(sh.effects) == 1            # present during recording
    tpl.stop_recording()
    assert len(sh.effects) == 0            # gone from the template after stop
    assert sh.effects_enabled is False     # master restored too


def test_record_captures_only_changed_effect_fields(tpl_ctx):
    """Bug: adding a default effect recorded all ~7 fields; should be just the
    ones that differ from the default (plus enabled)."""
    from edof.batch import make_default_effect
    doc, page, tb, sh, cv, tpl = tpl_ctx
    tpl.start_recording()
    e = make_default_effect("drop_shadow"); e.enabled = True
    sh.effects.append(e)
    tpl.capture_canvas_edit()
    paths = {c.attr_path for c in doc.batch.columns}
    assert paths == {"effects.drop_shadow.enabled"}     # only enabled captured


def test_record_captures_changed_field_too(tpl_ctx):
    from edof.batch import make_default_effect
    doc, page, tb, sh, cv, tpl = tpl_ctx
    tpl.start_recording()
    e = make_default_effect("drop_shadow"); e.enabled = True; e.distance = 9.0
    sh.effects.append(e)
    tpl.capture_canvas_edit()
    paths = {c.attr_path for c in doc.batch.columns}
    assert paths == {"effects.drop_shadow.enabled", "effects.drop_shadow.distance"}


def test_default_effects_enabled_is_false():
    from edof import Document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    assert sh.effects_enabled is False


def test_add_variable_seeds_record_and_value(panel_ctx):
    from edof.batch import find_descriptor
    doc, page, tb, sh, cv, panel = panel_ctx
    d = find_descriptor(sh, "transform.x")
    col = panel.add_column_for_object(sh, d, "X")
    # a record is auto-created and the new column pre-filled with the current value
    assert len(doc.batch.rows) == 1
    assert col.column_id in doc.batch.rows[0].values


def test_add_dialog_shows_existing_variables(app):
    from edof._apps.batch_panel import _AddColumnDialog, _existing_paths_for_object
    from edof import Document
    from edof.batch.model import build_ref
    from PyQt6.QtWidgets import QTreeWidgetItemIterator
    from PyQt6.QtCore import Qt
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    doc.batch.add_column(build_ref(p, sh), "effects.all_enabled", "All", "enum")
    existing = _existing_paths_for_object(doc.batch, sh, [p])
    assert "effects.all_enabled" in existing
    dlg = _AddColumnDialog(sh, None, existing_paths=existing)
    try:
        it = QTreeWidgetItemIterator(dlg._tree)
        found = False
        while it.value():
            item = it.value()
            if item.data(0, dlg._DESC_ROLE) == "effects.all_enabled":
                assert item.checkState(0) == Qt.CheckState.Checked
                assert not bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
                found = True
            it += 1
        assert found
    finally:
        dlg.close()
        dlg.deleteLater()


def test_record_captures_second_effect_of_same_type(tpl_ctx):
    """Adding a 2nd effect of the same type during recording captures it under
    an ordinal path, leaving the first (unchanged) instance alone."""
    from edof import LayerEffect
    from edof.batch import make_default_effect
    doc, page, tb, sh, cv, tpl = tpl_ctx
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True, distance=2))
    sh.effects_enabled = True
    tpl.start_recording()
    e2 = make_default_effect("drop_shadow"); e2.enabled = True; e2.distance = 9.0
    sh.effects.append(e2)
    tpl.capture_canvas_edit()
    paths = {c.attr_path for c in doc.batch.columns}
    assert "effects.drop_shadow#2.enabled" in paths
    assert "effects.drop_shadow#2.distance" in paths
    # first instance not captured (unchanged)
    assert "effects.drop_shadow.enabled" not in paths
    assert "effects.drop_shadow.distance" not in paths
    tpl.stop_recording()
    assert len(sh.effects) == 1            # 2nd belongs to the record


def test_tree_dialog_add_effect_instance(app):
    """v4.3.5.25: '+ Add effect instance' really adds a (disabled) effect to the
    object, so it shows in the tree as an instance and can be batched."""
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    from PyQt6.QtCore import Qt
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    dlg = _AddColumnDialog(sh, None)
    try:
        # the object has no drop_shadow -> not shown until added
        assert "effects.drop_shadow.enabled" not in dlg._items_by_path
        dlg._add_instance("drop_shadow")     # really adds it to the object
        assert len(sh.effects) == 1
        assert "effects.drop_shadow.enabled" in dlg._items_by_path
        dlg._add_instance("drop_shadow")     # a second instance
        assert len(sh.effects) == 2
        assert "effects.drop_shadow#2.enabled" in dlg._items_by_path
        dlg._items_by_path["effects.drop_shadow.enabled"].setCheckState(
            0, Qt.CheckState.Checked)
        dlg._items_by_path["effects.drop_shadow#2.enabled"].setCheckState(
            0, Qt.CheckState.Checked)
        dlg._name_edits["effects.drop_shadow#2.enabled"].setText("Second")
        dlg._accept()
        paths = {d.path: n for d, n in dlg.chosen_pairs()}
        assert "effects.drop_shadow.enabled" in paths
        assert paths.get("effects.drop_shadow#2.enabled") == "Second"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_tree_dialog_remembers_checks_across_instance_add(app):
    """Adding an instance rebuilds the tree but keeps prior checks/names."""
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document, LayerEffect
    from PyQt6.QtCore import Qt
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    sh.effects = [LayerEffect(type="drop_shadow")]      # one to start
    dlg = _AddColumnDialog(sh, None)
    try:
        dlg._items_by_path["effects.drop_shadow.enabled"].setCheckState(
            0, Qt.CheckState.Checked)
        dlg._name_edits["effects.drop_shadow.enabled"].setText("First")
        dlg._add_instance("drop_shadow")     # rebuild
        # the first check + name survived
        assert dlg._items_by_path["effects.drop_shadow.enabled"].checkState(0) \
            == Qt.CheckState.Checked
        assert dlg._name_edits["effects.drop_shadow.enabled"].text() == "First"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_header_uniqueness_helper():
    from edof._apps.batch_panel import _header_in_use
    from edof import Document
    from edof.batch.model import build_ref
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 5, 50, 15, "x")
    c = doc.batch.add_column(build_ref(p, tb), "text", "Title", "text")
    assert _header_in_use(doc.batch, "Title") is True
    assert _header_in_use(doc.batch, "title") is True          # case-insensitive
    assert _header_in_use(doc.batch, "Other") is False
    assert _header_in_use(doc.batch, "Title", exclude_col_id=c.column_id) is False
    assert _header_in_use(doc.batch, "") is False              # empty never conflicts


def test_dialog_rejects_duplicate_name(app, monkeypatch):
    from edof._apps import batch_panel as BP
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    from PyQt6.QtCore import Qt
    monkeypatch.setattr(BP.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 5, 50, 15, "x")
    dlg = _AddColumnDialog(tb, None, existing_names=["Taken"])
    try:
        dlg._items_by_path["text"].setCheckState(0, Qt.CheckState.Checked)
        dlg._name_edits["text"].setText("Taken")
        dlg._accept()
        assert dlg._result == []           # rejected, not accepted
        dlg._name_edits["text"].setText("Fresh")
        dlg._accept()
        assert any(n == "Fresh" for _d, n in dlg._result)
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_effects_collapsed_by_default(app):
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 5, 50, 15, "x")
    dlg = _AddColumnDialog(tb, None)
    try:
        for i in range(dlg._tree.topLevelItemCount()):
            g = dlg._tree.topLevelItem(i)
            if g.text(0) == "Layer Effects":
                assert g.isExpanded() is False
    finally:
        dlg.close()
        dlg.deleteLater()


def test_overlay_reflects_projected_geometry(app):
    """v4.3.5.20: while a batch row is projected, the selection overlay must use
    the PROJECTED object's geometry (e.g. a batched size), not the live one."""
    import edof._apps.editor as E
    from edof import Document
    from edof.batch.model import build_ref, BatchRow
    from edof.batch import find_descriptor
    doc = Document()
    p = doc.add_page(width=120, height=80)
    sh = p.add_shape("rect", 10, 10, 30, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0); cv.set_sel_id(sh.id)
    col = doc.batch.add_column(build_ref(p, sh), "transform.width", "W", "number")
    doc.batch.rows = [BatchRow(page_target=0, values={col.column_id: "60"})]
    cv.set_batch_preview_row(doc.batch.rows[0], page_idx=0)
    target = cv._overlay_target_for(sh)
    assert find_descriptor(target, "transform.width").get(target) == 60.0
    # live object unchanged
    assert find_descriptor(sh, "transform.width").get(sh) == 30.0


def test_start_recording_clears_projection(app):
    """v4.3.5.20: starting a record must drop any active canvas projection, so
    live edits (and the bounding box) show instead of the projected row."""
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    from edof import Document
    from edof.batch.model import build_ref, BatchRow
    doc = Document()
    p = doc.add_page(width=120, height=80)
    sh = p.add_shape("rect", 10, 10, 30, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0); cv.set_sel_id(sh.id)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    col = doc.batch.add_column(build_ref(p, sh), "transform.width", "W", "number")
    doc.batch.rows = [BatchRow(page_target=0, values={col.column_id: "60"})]
    cv.set_batch_preview_row(doc.batch.rows[0], page_idx=0)
    assert cv._batch_preview_row is not None
    tpl.start_recording()
    assert cv._batch_preview_row is None


# ── v4.3.5.22: 1-based page numbering, 0 = cross-page ────────────────────────
def test_page_display_helpers():
    from edof._apps.batch_panel import (_page_target_to_display,
                                         _display_to_page_target)
    assert _page_target_to_display(None) == "crosspage"
    assert _page_target_to_display(0) == "1"
    assert _page_target_to_display(1) == "2"
    assert _display_to_page_target("0") is None        # 0 -> cross-page
    assert _display_to_page_target("crosspage") is None
    assert _display_to_page_target("") is None
    assert _display_to_page_target("1") == 0
    assert _display_to_page_target("3") == 2


def test_crosspage_row_applies_to_all_pages():
    import copy
    from edof import Document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 5, 50, 15, "orig")
    # a second page that contains the SAME object id won't happen normally, but
    # multi-target lets one column drive objects on several pages
    p2 = doc.add_page(width=80, height=50)
    tb2 = p2.add_textbox(5, 5, 50, 15, "orig")
    col = doc.batch.add_column(build_ref(p, tb), "text", "T", "text")
    col.extra_targets = [build_ref(p2, tb2)]
    doc.batch.row_scope = "page"
    row = BatchRow(page_target=None, values={col.column_id: "X"})    # cross-page
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    assert d2.pages[0].objects[0].text == "X"
    assert d2.pages[1].objects[0].text == "X"


def test_specific_page_row_applies_to_that_page_only():
    import copy
    from edof import Document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 5, 50, 15, "orig")
    p2 = doc.add_page(width=80, height=50)
    tb2 = p2.add_textbox(5, 5, 50, 15, "orig")
    col = doc.batch.add_column(build_ref(p, tb), "text", "T", "text")
    col.extra_targets = [build_ref(p2, tb2)]
    doc.batch.row_scope = "page"
    # page_target=1 -> internal index 1 = the SECOND page (displayed as "2")
    row = BatchRow(page_target=1, values={col.column_id: "ONLY2"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    assert d2.pages[0].objects[0].text == "orig"
    assert d2.pages[1].objects[0].text == "ONLY2"


# ── v4.3.5.23: multi-target link/unlink dialog ───────────────────────────────
def test_link_dialog_lists_only_compatible(app):
    from edof._apps.batch_panel import _LinkObjectsDialog
    from edof import Document
    from edof.batch.model import build_ref
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb1 = p.add_textbox(5, 5, 50, 15, "A")
    tb2 = p.add_textbox(60, 5, 50, 15, "B")
    sh = p.add_shape("rect", 5, 30, 40, 20)        # no 'text' attribute
    col = doc.batch.add_column(build_ref(p, tb1), "text", "Text", "text")
    dlg = _LinkObjectsDialog(col, [p], None)
    try:
        # only the two textboxes are listed (shape has no 'text')
        assert len(dlg._rows) == 2
        # the current target (tb1) is pre-checked
        from PyQt6.QtCore import Qt
        checked = [r for (it, pi, r) in dlg._rows
                   if it.checkState(0) == Qt.CheckState.Checked]
        assert len(checked) == 1
    finally:
        dlg.close()
        dlg.deleteLater()


def test_link_dialog_accept_writes_targets(app):
    from edof._apps.batch_panel import _LinkObjectsDialog
    from edof import Document
    from edof.batch.model import build_ref
    from PyQt6.QtCore import Qt
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb1 = p.add_textbox(5, 5, 50, 15, "A")
    tb2 = p.add_textbox(60, 5, 50, 15, "B")
    col = doc.batch.add_column(build_ref(p, tb1), "text", "Text", "text")
    dlg = _LinkObjectsDialog(col, [p], None)
    try:
        for it, pi, ref in dlg._rows:
            it.setCheckState(0, Qt.CheckState.Checked)
        dlg._accept()
        assert len(col.all_targets()) == 2
    finally:
        dlg.close()
        dlg.deleteLater()


def test_link_dialog_end_to_end_multitarget(app):
    import copy
    from edof._apps.batch_panel import _LinkObjectsDialog
    from edof import Document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    from PyQt6.QtCore import Qt
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb1 = p.add_textbox(5, 5, 50, 15, "A")
    tb2 = p.add_textbox(60, 5, 50, 15, "B")
    col = doc.batch.add_column(build_ref(p, tb1), "text", "Text", "text")
    doc.batch.rows = [BatchRow(page_target=0, values={col.column_id: "X"})]
    dlg = _LinkObjectsDialog(col, [p], None)
    try:
        for it, pi, ref in dlg._rows:
            it.setCheckState(0, Qt.CheckState.Checked)
        dlg._accept()
    finally:
        dlg.close()
        dlg.deleteLater()
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, doc.batch.rows[0])
    assert d2.pages[0].objects[0].text == "X"
    assert d2.pages[0].objects[1].text == "X"


def test_link_dialog_empty_selection_rejected(app, monkeypatch):
    from edof._apps import batch_panel as BP
    from edof._apps.batch_panel import _LinkObjectsDialog
    from edof import Document
    from edof.batch.model import build_ref
    from PyQt6.QtCore import Qt
    monkeypatch.setattr(BP.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb1 = p.add_textbox(5, 5, 50, 15, "A")
    col = doc.batch.add_column(build_ref(p, tb1), "text", "Text", "text")
    dlg = _LinkObjectsDialog(col, [p], None)
    try:
        for it, pi, ref in dlg._rows:
            it.setCheckState(0, Qt.CheckState.Unchecked)
        before = len(col.all_targets())
        dlg._accept()                     # should warn, not change targets
        assert len(col.all_targets()) == before
    finally:
        dlg.close()
        dlg.deleteLater()


# ── v4.3.5.24: drag-reorder effects in the Add-variable tree ─────────────────
def test_reorder_list_shown_only_with_multiple_effects(app):
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document, LayerEffect
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    # zero effects -> reorder list empty
    dlg = _AddColumnDialog(sh, None)
    try:
        assert dlg._fx_reorder.count() == 0
    finally:
        dlg.close(); dlg.deleteLater()
    # one effect -> container visible (so it can be removed) but reorder moot
    sh.effects = [LayerEffect(type="drop_shadow")]
    dlg = _AddColumnDialog(sh, None)
    try:
        assert dlg._fx_reorder.count() == 1
        dlg.show(); app.processEvents()
        assert dlg._fx_reorder_cont.isVisible() is True
    finally:
        dlg.close(); dlg.deleteLater()
    # two effects -> list populated and visible
    sh.effects = [LayerEffect(type="drop_shadow"), LayerEffect(type="inner_glow")]
    dlg = _AddColumnDialog(sh, None)
    try:
        assert dlg._fx_reorder.count() == 2
        dlg.show(); app.processEvents()
        assert dlg._fx_reorder_cont.isVisible() is True
    finally:
        dlg.close(); dlg.deleteLater()


def test_reorder_writes_order_to_object(app):
    from PyQt6.QtWidgets import QListWidgetItem
    from PyQt6.QtCore import Qt
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document, LayerEffect
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    e1 = LayerEffect(type="drop_shadow")
    e2 = LayerEffect(type="inner_glow")
    e3 = LayerEffect(type="stroke")
    sh.effects = [e1, e2, e3]
    dlg = _AddColumnDialog(sh, None)
    try:
        lw = dlg._fx_reorder
        lw.clear()
        for eid in (e3.eid, e1.eid, e2.eid):
            it = QListWidgetItem("x"); it.setData(Qt.ItemDataRole.UserRole, eid)
            lw.addItem(it)
        dlg._on_fx_reordered()
        assert [e.eid for e in sh.effects] == [e3.eid, e1.eid, e2.eid]
        assert dlg._reordered is True
    finally:
        dlg.close(); dlg.deleteLater()


def test_reorder_keeps_eid_binding(app):
    """A variable bound by eid drives the same effect after a reorder done in
    the Add-variable dialog."""
    import copy
    from PyQt6.QtWidgets import QListWidgetItem
    from PyQt6.QtCore import Qt
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document, LayerEffect
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    from edof.batch import effect_id_for_path
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    sh.effects_enabled = True
    e1 = LayerEffect(type="drop_shadow", enabled=True, distance=2)
    e2 = LayerEffect(type="drop_shadow", enabled=True, distance=8)
    sh.effects = [e1, e2]
    col = doc.batch.add_column(build_ref(p, sh),
                               "effects.drop_shadow#2.distance", "D2", "number")
    col.effect_id = effect_id_for_path(sh, "effects.drop_shadow#2.distance")
    dlg = _AddColumnDialog(sh, None)
    try:
        lw = dlg._fx_reorder; lw.clear()
        for eid in (e2.eid, e1.eid):           # swap
            it = QListWidgetItem("x"); it.setData(Qt.ItemDataRole.UserRole, eid)
            lw.addItem(it)
        dlg._on_fx_reordered()
    finally:
        dlg.close(); dlg.deleteLater()
    row = BatchRow(page_target=0, values={col.column_id: "99"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    by_eid = {e.eid: e for e in d2.pages[0].objects[0].effects}
    assert by_eid[e2.eid].distance == 99.0     # still the right effect
    assert by_eid[e1.eid].distance == 2


# ── v4.3.5.25: dynamic effects in tree, reorder all, link refresh ────────────
def test_tree_starts_with_no_effect_slots(app):
    """The Add-variable tree no longer pre-lists every effect type; Layer
    Effects has just the master + a hint until effects are added."""
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    dlg = _AddColumnDialog(sh, None)
    try:
        # no positional effect slot exists yet
        assert "effects.drop_shadow.enabled" not in dlg._items_by_path
        assert "effects.bevel.enabled" not in dlg._items_by_path
    finally:
        dlg.close(); dlg.deleteLater()


def test_add_instance_adds_real_effect_to_object(app):
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    dlg = _AddColumnDialog(sh, None)
    try:
        assert len(sh.effects) == 0
        dlg._add_instance("bevel")
        assert len(sh.effects) == 1
        assert sh.effects[0].type == "bevel"
        assert sh.effects[0].enabled is False     # added disabled
        assert dlg._reordered is True
    finally:
        dlg.close(); dlg.deleteLater()


def test_reorder_lists_all_effect_types(app):
    """The reorder list shows effects of different types, not just identical."""
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document, LayerEffect
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    sh.effects = [LayerEffect(type="drop_shadow"),
                  LayerEffect(type="inner_glow"),
                  LayerEffect(type="stroke")]
    dlg = _AddColumnDialog(sh, None)
    try:
        assert dlg._fx_reorder.count() == 3
        labels = [dlg._fx_reorder.item(i).text() for i in range(3)]
        assert any("Drop shadow" in s for s in labels)
        assert any("Inner glow" in s for s in labels)
        assert any("Stroke" in s for s in labels)
    finally:
        dlg.close(); dlg.deleteLater()


def test_link_refreshes_preview(app, monkeypatch):
    """Linking more objects to a variable re-projects the current row so the
    new objects update immediately."""
    import edof._apps.editor as E
    from edof._apps import batch_panel as BP
    from edof._apps.batch_panel import EdofBatchTemplatePanel, _LinkObjectsDialog
    from edof import Document
    from edof.batch.model import build_ref
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb1 = p.add_textbox(5, 5, 50, 15, "A")
    tb2 = p.add_textbox(60, 5, 50, 15, "B")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    col = doc.batch.add_column(build_ref(p, tb1), "text", "T", "text")
    # auto-accept the link dialog with both objects checked
    calls = {"refresh": 0}
    orig = tpl._refresh_preview_current
    def _spy():
        calls["refresh"] += 1
        return orig()
    monkeypatch.setattr(tpl, "_refresh_preview_current", _spy)
    def fake_exec(self):
        for it, pi, ref in self._rows:
            from PyQt6.QtCore import Qt
            it.setCheckState(0, Qt.CheckState.Checked)
        self._accept()
        return BP.QDialog.DialogCode.Accepted
    monkeypatch.setattr(_LinkObjectsDialog, "exec", fake_exec)
    tpl._link_objects(col)
    assert len(col.all_targets()) == 2
    assert calls["refresh"] >= 1            # preview was refreshed


def test_add_instance_uses_sensible_defaults(app):
    """'+ Add effect instance' uses make_default_effect defaults, not bare
    dataclass ones (e.g. drop shadow direction 315, not 135)."""
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    dlg = _AddColumnDialog(sh, None)
    try:
        dlg._add_instance("drop_shadow")
        e = sh.effects[-1]
        assert e.direction == 315.0
        assert e.distance == 2.0
        assert e.enabled is False
    finally:
        dlg.close(); dlg.deleteLater()


def test_remove_selected_effect(app):
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document, LayerEffect
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    e1 = LayerEffect(type="drop_shadow")
    e2 = LayerEffect(type="inner_glow")
    sh.effects = [e1, e2]
    dlg = _AddColumnDialog(sh, None)
    try:
        dlg._fx_reorder.setCurrentRow(1)       # inner_glow
        dlg._remove_selected_effect()
        assert len(sh.effects) == 1
        assert sh.effects[0].type == "drop_shadow"
        assert dlg._reordered is True
    finally:
        dlg.close(); dlg.deleteLater()


def test_selected_objects_includes_multi(app):
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchPanel
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_textbox(5, 5, 50, 15, "A")
    b = p.add_textbox(60, 5, 50, 15, "B")
    c = p.add_textbox(5, 30, 50, 15, "C")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_sel_id(a.id); cv._multi_sel_ids = {b.id, c.id}
    tp = EdofBatchPanel(cv); tp.set_document(doc)
    objs = tp._selected_objects()
    assert len(objs) == 3
    assert objs[0] is a            # primary first


def test_multiselect_add_column_links_all(app):
    import copy
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchPanel
    from edof import Document
    from edof.batch import find_descriptor
    from edof.batch.model import BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_textbox(5, 5, 50, 15, "A")
    b = p.add_textbox(60, 5, 50, 15, "B")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_sel_id(a.id); cv._multi_sel_ids = {b.id}
    tp = EdofBatchPanel(cv); tp.set_document(doc)
    desc = find_descriptor(a, "text")
    extra = [o for o in tp._selected_objects() if o is not a]
    col = tp.add_column_for_object(a, desc, "T", extra_objs=extra)
    assert len(col.all_targets()) == 2
    doc.batch.rows = [BatchRow(page_target=0, values={col.column_id: "X"})]
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, doc.batch.rows[0])
    assert d2.pages[0].objects[0].text == "X"
    assert d2.pages[0].objects[1].text == "X"


def test_add_instance_does_not_touch_master(app):
    """v4.3.5.29: adding an effect via the dialog does NOT turn the master on.
    Per request, effects need an explicit 'effects enabled' (master) variable;
    the panel shows a red warning when it's missing."""
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    sh.effects_enabled = False
    dlg = _AddColumnDialog(sh, None)
    try:
        dlg._add_instance("drop_shadow")
        assert sh.effects_enabled is False     # master left alone
        assert len(sh.effects) == 1
    finally:
        dlg.close(); dlg.deleteLater()


def test_removing_master_variable_hides_effect(app):
    """The user's scenario: master + shadow on an object, then the master
    variable is removed -> the master returns to off (no auto-enable), so the
    effect hides; the shadow variable alone keeps the per-effect flag but the
    master gate is off."""
    import copy
    from edof import Document, LayerEffect
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    sh.effects = [LayerEffect(type="drop_shadow", enabled=False)]
    sh.effects_enabled = False
    c_shadow = doc.batch.add_column(build_ref(p, sh),
                                    "effects.drop_shadow.enabled", "S", "enum")
    # only the shadow variable applies (master variable removed from this object)
    row = BatchRow(page_target=0, values={c_shadow.column_id: "true"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    o = d2.pages[0].objects[0]
    assert o.effects[0].enabled is True
    assert o.effects_enabled is False      # master stays off -> effect hidden


def test_fx_warning_shows_without_master(app):
    """Red warning appears when an effect variable exists with no master
    variable and the master isn't already on; hidden once a master variable is
    added."""
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    from edof import Document, LayerEffect
    from edof.batch.model import build_ref
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    sh.effects = [LayerEffect(type="drop_shadow", enabled=False)]
    sh.effects_enabled = False
    cv = E.EdofCanvas(); cv.set_document(doc, 0); cv.set_sel_id(sh.id)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    tpl.show(); app.processEvents()
    try:
        doc.batch.add_column(build_ref(p, sh),
                             "effects.drop_shadow.enabled", "S", "enum")
        tpl.rebuild(); app.processEvents()
        assert tpl._fx_warn.isVisible() is True
        doc.batch.add_column(build_ref(p, sh), "effects.all_enabled", "M", "enum")
        tpl.rebuild(); app.processEvents()
        assert tpl._fx_warn.isVisible() is False
    finally:
        tpl.close(); tpl.deleteLater()


def test_justify_mode_in_registry():
    from edof import Document
    from edof.batch import find_descriptor
    doc = Document()
    p = doc.add_page(width=80, height=50)
    tb = p.add_textbox(5, 5, 50, 15, "x")
    d = find_descriptor(tb, "style.justify_mode")
    assert d is not None
    assert set(d.choices) == {"space", "full"}
    assert d.set(tb, "full") is True
    assert tb.style.justify_mode == "full"


# ── v4.3.5.31: multi-selection common-attribute tree ─────────────────────────
def test_multiselect_tree_shows_only_common(app):
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb = p.add_textbox(5, 5, 50, 15, "A")
    sh = p.add_shape("rect", 60, 5, 40, 15)        # no 'text'
    dlg = _AddColumnDialog(tb, None, extra_objs=[sh])
    try:
        paths = set(dlg._items_by_path.keys())
        assert "text" not in paths                 # not shared
        assert "transform.width" in paths          # shared geometry
        assert "(2 objects)" in dlg.windowTitle()
    finally:
        dlg.close(); dlg.deleteLater()


def test_multiselect_tree_drops_empty_bands(app):
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb = p.add_textbox(5, 5, 50, 15, "A")
    sh = p.add_shape("rect", 60, 5, 40, 15)
    dlg = _AddColumnDialog(tb, None, extra_objs=[sh])
    try:
        tops = [dlg._tree.topLevelItem(i).text(0)
                for i in range(dlg._tree.topLevelItemCount())]
        # Content band (text-only) should be gone; Geometry stays
        assert "Content" not in tops
        assert "Geometry" in tops
    finally:
        dlg.close(); dlg.deleteLater()


def test_single_selection_tree_unfiltered(app):
    """Without extra objects, the tree is the full single-object tree."""
    from edof._apps.batch_panel import _AddColumnDialog
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb = p.add_textbox(5, 5, 50, 15, "A")
    dlg = _AddColumnDialog(tb, None)
    try:
        assert "text" in dlg._items_by_path        # text present for a textbox
        assert "(objects)" not in dlg.windowTitle()
    finally:
        dlg.close(); dlg.deleteLater()


# ── v4.3.5.32: multi-select mirroring + table text filter ────────────────────
def test_object_list_extended_selection(app):
    import edof._apps.editor as E
    from PyQt6.QtWidgets import QListWidget
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    p.add_textbox(5, 5, 50, 15, "A")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    op = E.ObjectListPanel(cv)
    try:
        assert (op._list.selectionMode()
                == QListWidget.SelectionMode.ExtendedSelection)
        assert hasattr(op, "objectsSelected")
    finally:
        op.deleteLater(); app.processEvents()


def test_canvas_set_multi_selection(app):
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_textbox(5, 5, 50, 15, "A")
    b = p.add_textbox(60, 5, 50, 15, "B")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    assert cv._sel_id == a.id
    assert cv._multi_sel_ids == {b.id}
    assert len(cv.selected_objects()) == 2
    cv.set_multi_selection([])
    assert cv._sel_id is None
    assert cv._multi_sel_ids == set()
    cv.deleteLater(); app.processEvents()


def test_rectangle_select_bbox_intersect():
    """The marquee selects objects whose bbox intersects the rectangle."""
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 15)        # inside left
    b = p.add_shape("rect", 10, 40, 20, 15)        # inside left
    c = p.add_shape("rect", 90, 10, 20, 15)        # right, outside
    rx0, ry0, rx1, ry1 = 0, 0, 40, 70
    picked = [o.id for o in p.objects
              if o.transform.x < rx1 and o.transform.x + o.transform.width > rx0
              and o.transform.y < ry1 and o.transform.y + o.transform.height > ry0]
    assert a.id in picked
    assert b.id in picked
    assert c.id not in picked


def test_table_text_filter(app):
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchPanel
    from edof import Document
    from edof.batch import find_descriptor
    from edof.batch.model import BatchRow
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb = p.add_textbox(5, 5, 50, 15, "A")
    cv = E.EdofCanvas(); cv.set_document(doc, 0); cv.set_sel_id(tb.id)
    tp = EdofBatchPanel(cv); tp.set_document(doc)
    try:
        c1 = tp.add_column_for_object(tb, find_descriptor(tb, "text"), "Greeting")
        c2 = tp.add_column_for_object(tb, find_descriptor(tb, "transform.width"),
                                      "BoxWidth")
        doc.batch.rows = [
            BatchRow(page_target=0, name="r1",
                     values={c1.column_id: "Hello", c2.column_id: "50"}),
            BatchRow(page_target=0, name="r2",
                     values={c1.column_id: "Bye", c2.column_id: "99"}),
        ]
        tp.rebuild()

        def shown():
            return sum(1 for r in range(tp._table.rowCount())
                       if not tp._table.isRowHidden(r))
        assert shown() == 2                       # no filter
        tp._text_filter.setText("Hello")
        assert shown() == 1                       # value match
        tp._text_filter.setText("99")
        assert shown() == 1                       # value match (other row)
        tp._text_filter.setText("BoxWidth")
        assert shown() == 2                       # header match -> all rows
        tp._text_filter.setText("")
        assert shown() == 2                       # cleared
    finally:
        tp.deleteLater(); app.processEvents()


# ── v4.3.5.33: every variable gets an editor; filter by object name/type ─────
def test_all_descriptors_have_an_editor(app):
    """Every descriptor must produce a usable editor widget in the right panel
    (the fallthrough QLineEdit was lost in 4.3.5.29, breaking number/text)."""
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    from edof import Document
    from edof.batch import describe_object
    from edof.batch.model import build_ref, BatchRow
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb = p.add_textbox(5, 5, 50, 15, "A")
    cv = E.EdofCanvas(); cv.set_document(doc, 0); cv.set_sel_id(tb.id)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    try:
        bad = []
        for d in describe_object(tb):
            col = doc.batch.add_column(build_ref(p, tb), d.path,
                                       d.path.split(".")[-1], d.kind)
            row = BatchRow(page_target=0, values={col.column_id: "10"})
            field = tpl._make_field(col, row)
            if field is None:
                bad.append((d.path, d.kind))
            doc.batch.columns = [c for c in doc.batch.columns
                                 if c.column_id != col.column_id]
        assert bad == [], "descriptors with no editor: %r" % bad
    finally:
        cv.deleteLater(); app.processEvents()


def test_height_variable_is_editable(app):
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    from PyQt6.QtWidgets import QLineEdit
    from PyQt6.QtTest import QTest
    from edof import Document
    from edof.batch.model import build_ref, BatchRow
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb = p.add_textbox(5, 5, 50, 15, "A")
    cv = E.EdofCanvas(); cv.set_document(doc, 0); cv.set_sel_id(tb.id)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    try:
        hcol = doc.batch.add_column(build_ref(p, tb),
                                    "transform.height", "H", "number")
        doc.batch.rows = [BatchRow(page_target=0, values={hcol.column_id: "15"})]
        tpl._cur = 0
        f = tpl._make_field(hcol, doc.batch.rows[0])
        assert isinstance(f, QLineEdit)
        f.show(); app.processEvents()
        f.setText(""); QTest.keyClicks(f, "33"); app.processEvents()
        assert doc.batch.rows[0].values[hcol.column_id] == "33"
        f.close()
    finally:
        cv.deleteLater(); app.processEvents()


def test_filter_by_object_type(app):
    """The table filter matches an object's name/type even though the table
    never prints it (e.g. 'rectangle')."""
    import edof._apps.editor as E
    from edof._apps.batch_panel import EdofBatchPanel, _object_filter_text
    from edof import Document
    from edof.batch import find_descriptor
    from edof.batch.model import BatchRow
    doc = Document()
    p = doc.add_page(width=120, height=80)
    tb = p.add_textbox(5, 5, 50, 15, "Hello")
    sh = p.add_shape("rect", 60, 5, 40, 15)
    assert "rectangle" in _object_filter_text(sh)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    tp = EdofBatchPanel(cv); tp.set_document(doc)
    try:
        cv.set_sel_id(sh.id)
        c_sh = tp.add_column_for_object(sh, find_descriptor(sh, "transform.width"),
                                        "ShW")
        cv.set_sel_id(tb.id)
        c_tb = tp.add_column_for_object(tb, find_descriptor(tb, "text"), "Greeting")
        doc.batch.rows = [BatchRow(page_target=0, name="r1",
                                   values={c_sh.column_id: "40",
                                           c_tb.column_id: "Hi"})]
        tp.rebuild()

        def shown():
            return sum(1 for r in range(tp._table.rowCount())
                       if not tp._table.isRowHidden(r))
        tp._text_filter.setText("rectangle")
        assert shown() == 1                       # shape column matches -> rows
        tp._text_filter.setText("nope")
        assert shown() == 0
        tp._text_filter.setText("")
        assert shown() == 1
    finally:
        cv.deleteLater(); app.processEvents()


def test_object_list_rows_tall_enough(app):
    """v4.3.5.34: rows are at least 40px so the selection bar doesn't crowd the
    icon and text."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    p.add_textbox(5, 5, 50, 15, "A")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    op = E.ObjectListPanel(cv); op.refresh()
    try:
        assert op._list.item(0).sizeHint().height() >= 40
    finally:
        op.deleteLater(); app.processEvents()


def test_object_list_row_transparent_for_mouse(app):
    """The row widget passes clicks through to the list so Ctrl/Shift
    multi-selection works; its toggle buttons stay clickable."""
    import edof._apps.editor as E
    from PyQt6.QtWidgets import QPushButton
    from PyQt6.QtCore import Qt
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    p.add_textbox(5, 5, 50, 15, "A")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    op = E.ObjectListPanel(cv); op.refresh()
    try:
        rw = op._list.itemWidget(op._list.item(0))
        assert rw.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        btns = rw.findChildren(QPushButton)
        assert len(btns) >= 1
        # buttons must NOT be transparent (they need their own clicks)
        assert not btns[0].testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    finally:
        op.deleteLater(); app.processEvents()


# ── v4.3.5.35: multi-selection union box + projected preview geometry ────────
def test_selected_objects_projected_returns_all(app):
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 15)
    b = p.add_shape("rect", 60, 40, 20, 15)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    try:
        objs = cv._selected_objects_projected()
        assert len(objs) == 2
    finally:
        cv.deleteLater(); app.processEvents()


def test_union_box_uses_projected_geometry(app):
    """During a batch preview the multi-selection box reflects the projected
    geometry, not the template (the bug: template boxes during preview)."""
    import edof._apps.editor as E
    from edof import Document
    from edof.batch.model import build_ref, BatchRow
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 15)
    b = p.add_shape("rect", 60, 40, 20, 15)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    try:
        col = doc.batch.add_column(build_ref(p, a), "transform.width", "W", "number")
        row = BatchRow(page_target=0, values={col.column_id: "50"})
        cv.set_batch_preview_row(row)
        objs = cv._selected_objects_projected()
        widths = {round(o.transform.x): o.transform.width for o in objs}
        assert widths[10] == 50.0           # projected, not template 20
        assert widths[60] == 20.0           # untouched object
    finally:
        cv.deleteLater(); app.processEvents()


# ── v4.3.5.37: transform the whole multi-selection (resize + rotate) ─────────
def test_union_bbox_and_handles(app):
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    try:
        bb = cv._union_bbox_mm()
        assert bb == (10.0, 10.0, 70.0, 70.0)
        handles = cv._union_handles_px()
        assert handles is not None
        assert set(handles.keys()) >= {"TL", "TR", "BL", "BR", "ROT"}
    finally:
        cv.deleteLater(); app.processEvents()


def test_multi_resize_scales_about_anchor(app):
    import edof._apps.editor as E
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    try:
        cv._multi_bb0 = cv._union_bbox_mm()          # 10,10,70,70
        cv._multi_tf0 = {o.id: {"tf": copy.copy(o.transform)} for o in (a, b)}
        cv._drag_sp0 = QPointF(0, 0)
        # drag BR to double (union 60 -> 120, anchor TL 10,10)
        sp = QPointF(mm_to_px(130, cv._dpi), mm_to_px(130, cv._dpi))
        cv._apply_multi_transform("multi_resize_BR", sp, False, True)
        assert (a.transform.x, a.transform.y) == (10.0, 10.0)   # anchor fixed
        assert a.transform.width == 40.0                        # 2x
        assert (b.transform.x, b.transform.y) == (90.0, 90.0)
        assert b.transform.width == 40.0
    finally:
        cv.deleteLater(); app.processEvents()


def test_multi_rotate_about_center(app):
    import edof._apps.editor as E
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    try:
        cv._multi_bb0 = cv._union_bbox_mm()          # center 40,40
        cv._multi_tf0 = {o.id: {"tf": copy.copy(o.transform)} for o in (a, b)}
        cx, cy = 40, 40
        cv._drag_sp0 = QPointF(mm_to_px(cx + 10, cv._dpi), mm_to_px(cy, cv._dpi))
        sp = QPointF(mm_to_px(cx, cv._dpi), mm_to_px(cy + 10, cv._dpi))   # +90
        cv._apply_multi_transform("multi_rotate", sp, False, True)
        assert round(a.transform.rotation) == 90
        assert round(b.transform.rotation) == 90
        # a's center (20,20) rotates 90 about (40,40) -> (60,20)
        acx = a.transform.x + a.transform.width / 2
        acy = a.transform.y + a.transform.height / 2
        assert (round(acx), round(acy)) == (60, 20)
    finally:
        cv.deleteLater(); app.processEvents()


# ── v4.3.5.38: properties panel multi-edit + effects to selection ────────────
def test_props_multi_edit_width_and_opacity(app):
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 10, 20, 20)
    c = p.add_shape("rect", 90, 10, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id, c.id])
    pp = E.PropPanel(cv); pp.load(a)
    try:
        pp._atf("width", 40)                       # absolute to all
        assert a.transform.width == b.transform.width == c.transform.width == 40.0
        pp._aa("opacity", 0.3)                      # to all
        assert a.opacity == b.opacity == c.opacity == 0.3
    finally:
        cv.deleteLater(); app.processEvents()


def test_props_multi_edit_xy_is_delta(app):
    """X/Y edits move the whole selection by the same delta."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 10, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    pp = E.PropPanel(cv); pp.load(a)
    try:
        pp._atf("x", a.transform.x + 5)            # +5 to both
        assert a.transform.x == 15.0
        assert b.transform.x == 55.0
    finally:
        cv.deleteLater(); app.processEvents()


def test_apply_effects_to_selection(app):
    import edof._apps.editor as E
    from edof import Document, LayerEffect
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 10, 20, 20)
    a.effects = [LayerEffect(type="drop_shadow", enabled=True)]
    a.effects_enabled = True
    a.opacity = 0.7
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    pp = E.PropPanel(cv); pp.load(a)
    try:
        pp._apply_effects_to_selection()
        assert len(b.effects) == 1
        assert b.effects[0].type == "drop_shadow"
        assert b.effects_enabled is True           # master carried -> renders
        assert b.opacity == 0.7
    finally:
        cv.deleteLater(); app.processEvents()


def test_single_selection_props_unaffected(app):
    """With one object selected, edits apply only to it (no multi behavior)."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 10, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_sel_id(a.id)                            # single selection
    pp = E.PropPanel(cv); pp.load(a)
    try:
        pp._atf("width", 40)
        assert a.transform.width == 40.0
        assert b.transform.width == 20.0          # untouched
    finally:
        cv.deleteLater(); app.processEvents()


def test_union_handle_hit_no_attribute_error(app):
    """Regression (4.3.5.39): hovering / hit-testing the multi-selection box must
    not raise -- EdofCanvas has _zoom (a float), not the overlay's _view_zoom()."""
    import edof._apps.editor as E
    from PyQt6.QtCore import QPointF
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    try:
        handles = cv._union_handles_px()
        assert handles is not None
        # these are exactly the calls that raised in _update_cursor / mouseMove
        assert cv._hit_union_handle(QPointF(0, 0)) is None
        assert cv._hit_union_handle(handles["TL"]) == "TL"
        cv._update_cursor(QPointF(0, 0))           # must not raise
        cv._update_cursor(handles["BR"])           # must not raise
    finally:
        cv.deleteLater(); app.processEvents()


def test_multiselect_hides_single_overlay(app):
    """v4.3.5.40: a multi-selection shows only the union box; the primary
    object's single transform overlay is hidden (no lingering handle box)."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    try:
        cv.set_sel_id(a.id); cv._refresh_overlay()
        assert len(cv._overlay._handles) > 0          # single overlay shown
        cv.set_multi_selection([a.id, b.id]); cv._refresh_overlay()
        assert len(cv._overlay._handles) == 0         # hidden under union box
        # union box itself is still available
        assert cv._union_handles_px() is not None
    finally:
        cv.deleteLater(); app.processEvents()


def test_multi_resize_squashes_text_nonuniform(app):
    """v4.3.5.41: a non-uniform resize of a multi-selection scales a text box's
    glyph scale non-uniformly (squash/stretch the letters), not just the box."""
    import edof._apps.editor as E
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof.format.objects import TextBox
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=80)
    tb = p.add_textbox(10, 10, 40, 20, "Hello")
    r = p.add_shape("rect", 60, 10, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([tb.id, r.id])
    try:
        cv._multi_bb0 = cv._union_bbox_mm()        # 10,10,80,30 (width 70)
        cv._multi_tf0 = {}
        for o in (tb, r):
            snap = {"tf": copy.copy(o.transform)}
            if isinstance(o, TextBox):
                snap["gsx"] = 1.0; snap["gsy"] = 1.0
            cv._multi_tf0[o.id] = snap
        cv._drag_sp0 = QPointF(0, 0)
        # drag MR (right edge) to double width; anchor ML at x=10
        sp = QPointF(mm_to_px(10 + 140, cv._dpi), mm_to_px(20, cv._dpi))
        cv._apply_multi_transform("multi_resize_MR", sp, False, True)
        assert abs(tb.style.glyph_scale_x - 2.0) < 0.1   # stretched horizontally
        assert abs(tb.style.glyph_scale_y - 1.0) < 0.1   # height unchanged
    finally:
        cv.deleteLater(); app.processEvents()


def test_glyph_scale_renders_wider(app):
    """Sanity: glyph_scale_x actually widens the rendered text."""
    from edof import Document
    from edof.engine.renderer import _render_textbox
    from PIL import Image
    import numpy as np
    doc = Document()
    p = doc.add_page(width=200, height=80)
    tb = p.add_textbox(10, 10, 40, 20, "WWW")

    def width_px(o):
        c = Image.new("RGBA", (600, 400), (0, 0, 0, 0))
        _render_textbox(o, c, {}, {}, 96)
        a = np.array(c)[:, :, 3]
        xs = np.where(a > 0)[1]
        return (xs.max() - xs.min()) if len(xs) else 0

    w0 = width_px(tb)
    tb.style.glyph_scale_x = 2.0
    w1 = width_px(tb)
    assert w1 > w0 * 1.5


# ── v4.3.5.42: group / ungroup a selection ───────────────────────────────────
def test_group_and_ungroup(app):
    import edof._apps.editor as E
    from edof.format.objects import Group
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    c = p.add_shape("rect", 90, 10, 15, 15)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    try:
        cv.set_multi_selection([a.id, b.id])
        g = cv.group_selection()
        assert isinstance(g, Group)
        assert len(p.objects) == 2                 # group + c
        assert len(g.children) == 2
        # group bbox spans both children
        assert (round(g.transform.x), round(g.transform.y)) == (10, 10)
        assert (round(g.transform.width), round(g.transform.height)) == (60, 60)
        cv.set_sel_id(g.id)
        freed = cv.ungroup_selection()
        assert len(freed) == 2
        assert len(p.objects) == 3                 # dissolved back
    finally:
        cv.deleteLater(); app.processEvents()


def test_group_needs_two_objects(app):
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    try:
        cv.set_sel_id(a.id)
        assert cv.group_selection() is None        # one object -> no group
    finally:
        cv.deleteLater(); app.processEvents()


def test_group_move_translates_children(app):
    import edof._apps.editor as E
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    g = cv.group_selection()
    try:
        cv.set_sel_id(g.id)
        cv._drag_mode = "move"; cv._drag_sp0 = QPointF(0, 0)
        cv._drag_tf0 = copy.copy(g.transform)
        cv._drag_group0 = [(ch.transform.x, ch.transform.y) for ch in g.flatten()]
        cv._drag_pts0 = None; cv._multi_drag_tf0 = {}
        ax0, bx0 = a.transform.x, b.transform.x
        cv._apply_drag(QPointF(mm_to_px(20, cv._dpi), 0), False, False, False)
        assert abs(a.transform.x - (ax0 + 20)) < 0.5
        assert abs(b.transform.x - (bx0 + 20)) < 0.5
    finally:
        cv.deleteLater(); app.processEvents()


def test_objects_panel_shows_group_children(app):
    import edof._apps.editor as E
    from PyQt6.QtCore import Qt
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    g = cv.group_selection()
    op = E.ObjectListPanel(cv); op.refresh()
    try:
        # group + its two children listed
        assert op._list.count() == 3
        ids = [op._list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(op._list.count())]
        gi = ids.index(g.id)
        assert g.children[0].id in ids[gi + 1:]
        assert g.children[1].id in ids[gi + 1:]
    finally:
        op.deleteLater(); app.processEvents()


# ── v4.3.5.43: batch targets objects inside a group ──────────────────────────
def test_build_ref_into_group_is_multilevel():
    from edof import Document
    from edof.batch.model import build_ref, resolve_ref
    from edof.format.objects import Group
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    g = Group()
    p.remove_object(a.id); p.remove_object(b.id)
    g.add(a); g.add(b); p.add_object(g)
    ref = build_ref(p, a)
    assert ref is not None
    assert len(ref.path) == 2                       # [group, child]
    assert resolve_ref(p, ref) is a                 # resolves back to the child


def test_batch_applies_to_group_child():
    from edof import Document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    from edof.format.objects import Group
    import copy
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20); a.name = "A"
    b = p.add_shape("rect", 50, 50, 20, 20)
    g = Group()
    p.remove_object(a.id); p.remove_object(b.id)
    g.add(a); g.add(b); p.add_object(g)
    col = doc.batch.add_column(build_ref(p, a), "transform.width", "W", "number")
    row = BatchRow(page_target=0, values={col.column_id: "45"})
    dcopy = copy.deepcopy(doc)
    apply_row_to_document(dcopy.batch, dcopy, row)
    gp = dcopy.pages[0].objects[0]
    ap = next(c for c in gp.children if c.name == "A")
    assert ap.transform.width == 45.0               # batch reached into the group


def test_flatten_targets_includes_group_children():
    from edof import Document
    from edof._apps.batch_panel import _flatten_targets
    from edof.format.objects import Group
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20); a.name = "A"
    b = p.add_shape("rect", 50, 50, 20, 20); b.name = "B"
    c = p.add_shape("rect", 90, 10, 15, 15); c.name = "C"
    g = Group(); g.name = "G"
    p.remove_object(a.id); p.remove_object(b.id)
    g.add(a); g.add(b); p.add_object(g)
    names = {o.name for o in _flatten_targets(p)}
    assert {"A", "B", "C", "G"} <= names            # children, top-level, group


def test_find_obj_resolves_group_child(app):
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20); a.name = "A"
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    g = cv.group_selection()
    try:
        cv.set_sel_id(a.id)                          # select a child of the group
        sel = cv.selected_objects()
        assert sel and sel[0].name == "A"
        assert cv._find_obj(b.id) is b
    finally:
        cv.deleteLater(); app.processEvents()


# ── v4.3.5.44: single-select clears multi; group naming ──────────────────────
def test_set_sel_id_clears_multi(app):
    """Selecting one object drops a prior multi-selection (so batching a group
    targets only the group, not its children)."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20); a.name = "A"
    b = p.add_shape("rect", 50, 50, 20, 20); b.name = "B"
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    g = cv.group_selection()
    try:
        names = [o.name or "G" for o in cv.selected_objects()]
        assert names == ["G"]                       # only the group
        assert len(cv._multi_sel_ids) == 0
    finally:
        cv.deleteLater(); app.processEvents()


def test_next_group_name_fills_gap(app):
    import edof._apps.editor as E
    from edof.format.objects import Group
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    g1 = Group(); g1.name = "Group001"; p.add_object(g1)
    g3 = Group(); g3.name = "Group003"; p.add_object(g3)
    ed = E.EdofEditor.__new__(E.EdofEditor)
    ed._cp = lambda: p
    assert ed._next_group_name() == "Group002"      # fills the gap
    p.objects.clear()
    assert ed._next_group_name() == "Group001"      # none yet


# ── v4.3.5.45: multi-selection highlight in Objects panel ────────────────────
def test_select_many_highlights_all(app):
    import edof._apps.editor as E
    from PyQt6.QtCore import Qt
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    c = p.add_shape("rect", 90, 10, 15, 15)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    op = E.ObjectListPanel(cv); op.refresh()
    try:
        op.select_many([a.id, c.id], primary=a.id)
        sel = {op._list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(op._list.count()) if op._list.item(i).isSelected()}
        assert sel == {a.id, c.id}                   # both highlighted
        assert b.id not in sel
    finally:
        op.deleteLater(); app.processEvents()


def test_menu_style_has_item_padding(app):
    """Menu items get horizontal padding + min width so labels aren't clipped."""
    import edof._apps.editor as E
    line = [l for l in E.QSS.split("\n") if "QMenu::item" in l]
    assert line
    assert "padding" in line[0]
    assert "min-width" in line[0]


# ── v4.3.5.46: resize / rotate a group as a unit ─────────────────────────────
def _group_two(cv, p):
    a = p.add_shape("rect", 10, 10, 20, 20)
    b = p.add_shape("rect", 50, 50, 20, 20)
    cv.set_multi_selection([a.id, b.id])
    return a, b, cv.group_selection()


def test_group_resize_scales_children(app):
    import edof._apps.editor as E
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=120)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    a, b, g = _group_two(cv, p)
    try:
        cv.set_sel_id(g.id)
        cv._drag_mode = "resize_BR"; cv._drag_sp0 = QPointF(0, 0)
        cv._drag_tf0 = copy.copy(g.transform); cv._drag_anchor = (10, 10)
        cv._drag_group_tf0 = [(c.transform.x, c.transform.y, c.transform.width,
                               c.transform.height, 1.0, 1.0) for c in g.flatten()]
        cv._drag_group_pts0 = {}; cv._drag_group_path0 = {}
        cv._drag_group_crot0 = {id(c): 0.0 for c in g.flatten()}
        cv._drag_path_data0 = None; cv._drag_font_size0_style = None
        cv._drag_glyph_scale_x0 = 1.0; cv._drag_glyph_scale_y0 = 1.0
        cv._apply_drag(QPointF(mm_to_px(130, cv._dpi), mm_to_px(130, cv._dpi)),
                       False, False, False)
        assert (round(a.transform.x), round(a.transform.y)) == (10, 10)
        assert round(a.transform.width) == 40
        assert (round(b.transform.x), round(b.transform.y)) == (90, 90)
        assert round(b.transform.width) == 40
    finally:
        cv.deleteLater(); app.processEvents()


def test_group_rotate_sets_group_rotation(app):
    """v4.3.5.49: rotating a group sets the GROUP's transform rotation (the
    renderer rotates the whole group); children stay in local space, unrotated."""
    import edof._apps.editor as E
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=120)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    a, b, g = _group_two(cv, p)
    try:
        cv.set_sel_id(g.id)
        ax0, ay0 = a.transform.x, a.transform.y
        cv._drag_mode = "rotate"; cv._drag_sp0 = QPointF(0, 0)
        cv._drag_tf0 = copy.copy(g.transform)
        cv._drag_group_tf0 = [(c.transform.x, c.transform.y, c.transform.width,
                               c.transform.height, 1.0, 1.0) for c in g.flatten()]
        cv._drag_group_crot0 = {id(c): 0.0 for c in g.flatten()}
        cv._drag_group_rot0 = 0.0
        cx, cy = 40, 40
        sp = QPointF(mm_to_px(cx + 10, cv._dpi), mm_to_px(cy, cv._dpi))   # +90
        cv._apply_drag(sp, False, False, False)
        assert round(g.transform.rotation) == 90       # group carries rotation
        assert a.transform.rotation == 0               # child unrotated
        assert (a.transform.x, a.transform.y) == (ax0, ay0)   # child unmoved
    finally:
        cv.deleteLater(); app.processEvents()


def test_group_compute_bounds_keeps_rotation():
    """v4.3.5.49: the group keeps its own rotation (renderer rotates the whole
    group); compute_bounds only updates x/y/w/h from the local children."""
    from edof import Document
    from edof.format.objects import Group
    doc = Document()
    p = doc.add_page(width=200, height=120)
    a = p.add_shape("rect", 10, 10, 20, 20)
    g = Group(); g.transform.rotation = 90
    g.add(a)
    g.compute_bounds()
    assert g.transform.rotation == 90                  # rotation preserved
    assert (round(g.transform.width), round(g.transform.height)) == (20, 20)


# ── v4.3.5.47: line gets a transform box and scales on resize ────────────────
def test_line_overlay_has_box_and_endpoints(app):
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=120)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [(10, 10), (50, 30)]
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    try:
        cv._overlay.update_for(ln, cv._dpi)
        keys = set(cv._overlay._handles.keys())
        assert {"TL", "TR", "BR", "BL", "ROT"} <= keys   # full transform box
        assert {"P1", "P2"} <= keys                       # endpoints kept
    finally:
        cv.deleteLater(); app.processEvents()


def test_line_endpoint_hit_takes_priority(app):
    """A click on an endpoint edits the endpoint, not the box corner."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=120)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [(10, 10), (50, 30)]
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    try:
        cv._overlay.update_for(ln, cv._dpi)
        p1 = cv._overlay._handles["P1"]
        assert cv._overlay.hit_handle(p1) == "P1"        # endpoint wins
    finally:
        cv.deleteLater(); app.processEvents()


def test_line_resize_scales_points(app):
    """v4.3.5.48: line points are LOCAL; resizing scales them about (0,0)."""
    import edof._apps.editor as E
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=120)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [[0, 0], [40, 20]]                     # local
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_sel_id(ln.id)
    try:
        cv._drag_mode = "resize_BR"; cv._drag_sp0 = QPointF(0, 0)
        cv._drag_tf0 = copy.copy(ln.transform); cv._drag_anchor = (10, 10)
        cv._drag_path_data0 = None; cv._drag_line_pts0 = list(ln.points)
        cv._drag_font_size0_style = None
        cv._drag_glyph_scale_x0 = 1.0; cv._drag_glyph_scale_y0 = 1.0
        cv._drag_group_tf0 = None
        cv._apply_drag(QPointF(mm_to_px(90, cv._dpi), mm_to_px(50, cv._dpi)),
                       False, False, False)
        pts = [[round(x), round(y)] for x, y in ln.points]
        assert pts == [[0, 0], [80, 40]]              # local, scaled 2x about 0
    finally:
        cv.deleteLater(); app.processEvents()


def test_line_in_group_resizes(app):
    import edof._apps.editor as E
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=120)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [(10, 10), (50, 30)]
    r = p.add_shape("rect", 60, 60, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([ln.id, r.id])
    g = cv.group_selection()
    try:
        cv.set_sel_id(g.id)
        cv._drag_mode = "resize_BR"; cv._drag_sp0 = QPointF(0, 0)
        cv._drag_tf0 = copy.copy(g.transform); cv._drag_anchor = (10, 10)
        cv._drag_group_tf0 = [(c.transform.x, c.transform.y, c.transform.width,
                               c.transform.height, 1.0, 1.0) for c in g.flatten()]
        cv._drag_group_pts0 = {id(c): list(c.points) for c in g.flatten()
                               if getattr(c, "points", None)}
        cv._drag_group_path0 = {}
        cv._drag_group_crot0 = {id(c): 0.0 for c in g.flatten()}
        cv._drag_path_data0 = None; cv._drag_line_pts0 = None
        cv._drag_font_size0_style = None
        cv._drag_glyph_scale_x0 = 1.0; cv._drag_glyph_scale_y0 = 1.0
        bb = g.transform
        cv._apply_drag(QPointF(mm_to_px(10 + bb.width * 2, cv._dpi),
                               mm_to_px(10 + bb.height * 2, cv._dpi)),
                       False, False, False)
        assert ln.points[1][0] > 51                     # line endpoint moved out
    finally:
        cv.deleteLater(); app.processEvents()


def test_group_renders_rotated_as_unit(app):
    """v4.3.5.49: a rotated group renders as one rotated unit (buffer path), so
    its bbox swaps width/height about the center -- not an axis-aligned box."""
    from edof import Document
    from edof.format.objects import Group
    from edof.engine.renderer import _render_object_dispatch
    from PIL import Image
    import numpy as np
    doc = Document()
    p = doc.add_page(width=200, height=120)
    a = p.add_shape("rect", 10, 10, 60, 20); a.fill.color = (255, 0, 0, 255)
    b = p.add_shape("rect", 10, 40, 20, 20); b.fill.color = (0, 0, 255, 255)
    g = Group()
    p.remove_object(a.id); p.remove_object(b.id)
    g.add(a); g.add(b); p.add_object(g)
    g.compute_bounds()

    def bbox(o):
        c = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        _render_object_dispatch(o, c, {}, {}, 96)
        arr = np.array(c)[:, :, 3]
        ys, xs = np.where(arr > 0)
        f = 25.4 / 96
        return (xs.min() * f, ys.min() * f, xs.max() * f, ys.max() * f)

    x0, y0, x1, y1 = bbox(g)               # rotation 0: 60 wide, 50 tall
    w0, h0 = x1 - x0, y1 - y0
    g.transform.rotation = 90
    rx0, ry0, rx1, ry1 = bbox(g)
    rw, rh = rx1 - rx0, ry1 - ry0
    # rotated 90 -> width/height swap (within a few mm of buffer padding)
    assert abs(rw - h0) < 4 and abs(rh - w0) < 4


def test_group_rotation_preserved_on_compute_bounds(app):
    """After rotating then recomputing bounds (e.g. on release), the group keeps
    its rotation and the children stay unrotated."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=120)
    a = p.add_shape("rect", 10, 10, 40, 20)
    b = p.add_shape("rect", 10, 40, 40, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id])
    g = cv.group_selection()
    try:
        g.transform.rotation = 90
        g.compute_bounds()
        assert g.transform.rotation == 90
        assert a.transform.rotation == 0
    finally:
        cv.deleteLater(); app.processEvents()


# ── v4.3.5.50: effects on a group as a whole ─────────────────────────────────
def _px_count(o):
    from edof.engine.renderer import _render_object
    from PIL import Image
    import numpy as np
    c = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    _render_object(o, c, {}, {}, 96)
    return int((np.array(c)[:, :, 3] > 0).sum())


def _make_group(p):
    from edof.format.objects import Group
    a = p.add_shape("rect", 30, 30, 40, 40); a.fill.color = (255, 0, 0, 255)
    b = p.add_shape("rect", 80, 30, 40, 40); b.fill.color = (0, 0, 255, 255)
    g = Group()
    p.remove_object(a.id); p.remove_object(b.id)
    g.add(a); g.add(b); p.add_object(g); g.compute_bounds()
    return a, b, g


def test_effect_on_group_whole():
    """A drop shadow on the group applies to the whole group silhouette."""
    from edof import Document, LayerEffect
    doc = Document()
    p = doc.add_page(width=200, height=120)
    a, b, g = _make_group(p)
    base = _px_count(g)
    g.effects = [LayerEffect(type="drop_shadow", enabled=True, size=3, distance=5)]
    g.effects_enabled = True
    assert _px_count(g) > base                        # shadow added around group


def test_child_effect_inside_group():
    """A child's own effect still renders when it's inside a group."""
    from edof import Document, LayerEffect
    doc = Document()
    p = doc.add_page(width=200, height=120)
    a, b, g = _make_group(p)
    base = _px_count(g)
    a.effects = [LayerEffect(type="drop_shadow", enabled=True, size=3, distance=4)]
    a.effects_enabled = True
    assert _px_count(g) > base                        # child shadow shows


def test_nested_group_with_effect():
    """Effects survive nested groups (outer effect wraps the whole thing)."""
    from edof import Document, LayerEffect
    from edof.format.objects import Group
    doc = Document()
    p = doc.add_page(width=200, height=120)
    a = p.add_shape("rect", 30, 30, 30, 30); a.fill.color = (255, 0, 0, 255)
    b = p.add_shape("rect", 70, 30, 30, 30); b.fill.color = (0, 255, 0, 255)
    inner = Group()
    p.remove_object(a.id); p.remove_object(b.id)
    inner.add(a); inner.add(b); inner.compute_bounds()
    c = p.add_shape("rect", 30, 80, 30, 30); c.fill.color = (0, 0, 255, 255)
    outer = Group()
    p.remove_object(c.id)
    outer.add(inner); outer.add(c); p.add_object(outer); outer.compute_bounds()
    base = _px_count(outer)
    outer.effects = [LayerEffect(type="drop_shadow", enabled=True, size=3, distance=5)]
    outer.effects_enabled = True
    assert _px_count(outer) > base


# ── v4.3.5.51: group resize shears pre-rotated children, QR stays square ─────
def _resize_group_x2(cv, g):
    import copy
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    cv.set_sel_id(g.id)
    gb = g.transform; ax, ay = gb.x, gb.y
    cv._drag_mode = "resize_BR"; cv._drag_sp0 = QPointF(0, 0)
    cv._drag_tf0 = copy.copy(gb); cv._drag_anchor = (ax, ay)
    cv._drag_group_tf0 = [(c.transform.x, c.transform.y, c.transform.width,
                           c.transform.height, 1.0, 1.0) for c in g.flatten()]
    cv._drag_group_crot0 = {id(c): (c.transform.rotation or 0.0) for c in g.flatten()}
    cv._drag_group_cshear0 = {id(c): 0.0 for c in g.flatten()}
    cv._drag_group_pts0 = {}; cv._drag_group_path0 = {}
    cv._drag_path_data0 = None; cv._drag_line_pts0 = None
    cv._drag_font_size0_style = None
    cv._drag_glyph_scale_x0 = 1.0; cv._drag_glyph_scale_y0 = 1.0
    cv._apply_drag(QPointF(mm_to_px(ax + gb.width * 2, cv._dpi),
                           mm_to_px(ay + gb.height, cv._dpi)), False, False, False)


def test_group_resize_shears_rotated_rect(app):
    """A pre-rotated rect deforms (gains shear) when the group is stretched in x."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=300, height=200)
    sq = p.add_shape("rect", 50, 50, 40, 40); sq.transform.rotation = 45
    r = p.add_shape("rect", 150, 50, 40, 40)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([sq.id, r.id])
    g = cv.group_selection()
    try:
        _resize_group_x2(cv, g)
        assert abs(sq.transform.shear_x) > 0.01      # skewed
        assert sq.transform.rotation != 45           # rotation adjusted (RQ)
    finally:
        cv.deleteLater(); app.processEvents()


def test_group_resize_keeps_qr_square(app):
    """A pre-rotated QR stays square (no shear) when the group is stretched."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=300, height=200)
    qr = p.add_qrcode("test", 50, 50, 40); qr.transform.rotation = 30
    r = p.add_shape("rect", 150, 50, 40, 40)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([qr.id, r.id])
    g = cv.group_selection()
    try:
        _resize_group_x2(cv, g)
        assert qr.transform.shear_x == 0.0           # not skewed
        assert abs(qr.transform.width - qr.transform.height) < 0.1   # square
        assert abs(qr.transform.rotation - 30) < 0.1                 # rotation kept
    finally:
        cv.deleteLater(); app.processEvents()


# ── v4.3.5.52: resizing a ROTATED group keeps children grouped (no scatter) ──
def test_rotated_group_resize_keeps_layout(app):
    """A rotated group resized uniformly must scale child spacing proportionally
    and keep them compact -- previously they scattered because positions scaled
    in world axes instead of the group's rotated axes."""
    import edof._apps.editor as E
    import copy, math
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px
    from edof import Document
    doc = Document()
    p = doc.add_page(width=210, height=297)
    a = p.add_shape("rect", 50, 50, 15, 15)
    b = p.add_shape("rect", 50, 70, 15, 15)
    c = p.add_shape("rect", 50, 90, 15, 15)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id, c.id])
    g = cv.group_selection()

    def centers():
        return [(o.transform.x + o.transform.width / 2,
                 o.transform.y + o.transform.height / 2) for o in (a, b, c)]

    def dist(p, q):
        return math.hypot(p[0] - q[0], p[1] - q[1])

    try:
        cs0 = centers()
        d_ab0 = dist(cs0[0], cs0[1]); d_bc0 = dist(cs0[1], cs0[2])
        g.transform.rotation = 37
        cv.set_sel_id(g.id)
        gb = g.transform
        cv._drag_mode = "resize_BR"; cv._drag_sp0 = QPointF(0, 0)
        cv._drag_tf0 = copy.copy(gb)
        anchor = cv._compute_anchor(gb, "BR"); cv._drag_anchor = anchor
        cv._drag_group_tf0 = [(o.transform.x, o.transform.y, o.transform.width,
                               o.transform.height, 1.0, 1.0) for o in g.flatten()]
        cv._drag_group_crot0 = {id(o): 0.0 for o in g.flatten()}
        cv._drag_group_cshear0 = {id(o): 0.0 for o in g.flatten()}
        cv._drag_group_pts0 = {}; cv._drag_group_path0 = {}
        cv._drag_path_data0 = None; cv._drag_line_pts0 = None
        cv._drag_font_size0_style = None
        cv._drag_glyph_scale_x0 = 1.0; cv._drag_glyph_scale_y0 = 1.0
        acx, acy = anchor
        br = max(gb.corners, key=lambda pp: math.hypot(pp[0] - acx, pp[1] - acy))
        newbr = (acx + 2 * (br[0] - acx), acy + 2 * (br[1] - acy))
        cv._apply_drag(QPointF(mm_to_px(newbr[0], cv._dpi),
                               mm_to_px(newbr[1], cv._dpi)), True, False, False)
        cs1 = centers()
        d_ab1 = dist(cs1[0], cs1[1]); d_bc1 = dist(cs1[1], cs1[2])
        # spacing doubled (uniform 2x), both gaps equal -> still compact & even
        assert abs(d_ab1 / d_ab0 - 2.0) < 0.1
        assert abs(d_bc1 / d_bc0 - 2.0) < 0.1
    finally:
        cv.deleteLater(); app.processEvents()


# ── v4.3.5.53: halftone pattern file path shows in the batch tree ────────────
def test_pattern_file_in_batch_tree(app):
    """A halftone effect exposes its pattern FILE PATH in the add-column tree, so
    a custom pattern can be batched by path (it was missing before -- only the
    base64 cache existed, which isn't batchable)."""
    from edof import Document, LayerEffect
    import edof._apps.batch_panel as BP
    doc = Document()
    p = doc.add_page(width=100, height=100)
    r = p.add_shape("rect", 10, 10, 50, 50)
    r.effects = [LayerEffect(type="halftone", enabled=True,
                             ht_pattern_mode="single")]
    r.effects_enabled = True
    dlg = BP._AddColumnDialog(r, None, existing_paths=set())
    try:
        def walk(item):
            out = []
            for i in range(item.childCount()):
                ch = item.child(i)
                out.append(ch.text(0))
                out += walk(ch)
            return out
        tree = dlg._tree
        labels = []
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            labels.append(top.text(0)); labels += walk(top)
        assert any("pattern file" in t.lower() for t in labels)
        # and it's wired to the real descriptor path
        assert "effects.halftone.ht_pattern_path" in dlg._items_by_path
    finally:
        dlg.deleteLater(); app.processEvents()


def test_pattern_file_batch_roundtrip(app):
    """Setting the pattern path via batch loads a different pattern per value."""
    from edof import Document, LayerEffect
    from edof.batch import find_descriptor
    from PIL import Image
    import tempfile, os
    pf1 = tempfile.mktemp(suffix=".png")
    Image.new("RGBA", (16, 16), (0, 0, 0, 255)).save(pf1)
    pf2 = tempfile.mktemp(suffix=".png")
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for i in range(16):
        im.putpixel((i, i), (0, 0, 0, 255))
    im.save(pf2)
    try:
        doc = Document()
        p = doc.add_page(width=100, height=100)
        r = p.add_shape("rect", 10, 10, 50, 50)
        r.effects = [LayerEffect(type="halftone", enabled=True,
                                 ht_pattern_mode="single")]
        r.effects_enabled = True
        d = find_descriptor(r, "effects.halftone.ht_pattern_path")
        d.set(r, pf1); b1 = r.effects[0].ht_patterns[0]
        d.set(r, pf2); b2 = r.effects[0].ht_patterns[0]
        assert b1 and b2 and b1 != b2
        assert os.path.basename(r.effects[0].ht_pattern_paths[0]) == os.path.basename(pf2)
    finally:
        os.remove(pf1); os.remove(pf2)


# ── v4.3.5.56: CSV export/import buttons in the 3D Batch panel ───────────────
def test_batch_panel_has_csv_buttons(app):
    import edof._apps.editor as E
    import edof._apps.batch_panel as BP
    from edof import Document
    doc = Document()
    p = doc.add_page(width=100, height=100)
    p.add_shape("rect", 10, 10, 50, 50)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    panel = BP.EdofBatchPanel(cv); panel.set_document(doc)
    try:
        assert hasattr(panel, "_btn_export_csv")
        assert hasattr(panel, "_btn_import_csv")
        # meta file sits next to the clean csv
        assert panel._meta_path_for("/tmp/foo.csv").endswith("foo.meta.csv")
    finally:
        panel.deleteLater(); cv.deleteLater(); app.processEvents()


def test_batch_panel_csv_roundtrip_files(app, tmp_path):
    """Export writes clean + meta files; re-import restores the rows."""
    import edof._apps.editor as E
    import edof._apps.batch_panel as BP
    from edof import Document
    from edof.batch.model import BatchColumn, BatchRow, ObjectRef
    doc = Document()
    p = doc.add_page(width=100, height=100)
    p.add_shape("rect", 10, 10, 50, 50)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    panel = BP.EdofBatchPanel(cv); panel.set_document(doc)
    cfg = doc.batch
    cfg.columns = [BatchColumn(column_id="c1", target=ObjectRef.from_list([0]),
                               attr_path="transform.x", var_name="X", kind="number")]
    cfg.rows = [BatchRow(values={"c1": "10"}, name="a"),
                BatchRow(values={"c1": "20"}, name="b")]
    try:
        cp = tmp_path / "batch.csv"
        mp = tmp_path / "batch.meta.csv"
        cp.write_text(cfg.to_csv(), encoding="utf-8-sig")
        mp.write_text(cfg.to_meta_csv(), encoding="utf-8-sig")
        cfg.rows = []
        n = cfg.update_rows_from_csv(cp.read_bytes(), meta=mp.read_bytes())
        assert n == 2
        assert cfg.rows[0].name == "a" and cfg.rows[0].values["c1"] == "10"
    finally:
        panel.deleteLater(); cv.deleteLater(); app.processEvents()


# ── v4.3.5.58: batch generate dialog (filename pattern builder) ─────────────
def _gen_setup(app):
    import edof._apps.editor as E
    import edof._apps.batch_panel as BP
    from edof import Document
    from edof.batch.model import BatchColumn, BatchRow, ObjectRef
    doc = Document()
    p = doc.add_page(width=80, height=50)
    p.add_shape("rect", 5, 5, 30, 30)
    p.add_textbox(40, 5, 30, 30, "X")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    panel = BP.EdofBatchPanel(cv); panel.set_document(doc)
    cfg = doc.batch
    cfg.columns = [BatchColumn(column_id="c1", target=ObjectRef.from_list([1]),
                               attr_path="text", var_name="Name", kind="text")]
    cfg.rows = [BatchRow(values={"c1": "Alice"}, name="first"),
                BatchRow(values={"c1": "Bob"}, name="second")]
    return doc, cv, panel, cfg, BP


def test_generate_button_present(app):
    doc, cv, panel, cfg, BP = _gen_setup(app)
    try:
        assert hasattr(panel, "_btn_generate")
    finally:
        panel.deleteLater(); cv.deleteLater(); app.processEvents()


def test_filename_dialog_preview_and_step(app):
    doc, cv, panel, cfg, BP = _gen_setup(app)
    dlg = BP._FilenamePatternDialog(cfg, cfg.rows, panel)
    try:
        dlg._le_pat.setText("[ROW_NUMBER]_[ROW_NAME]")
        assert dlg._lbl_preview.text() == "1_first.png"
        dlg._step(1)
        assert dlg._lbl_preview.text() == "2_second.png"
        dlg._step(1)                       # wraps back to row 1
        assert dlg._lbl_preview.text() == "1_first.png"
    finally:
        dlg.deleteLater(); panel.deleteLater(); cv.deleteLater()
        app.processEvents()


def test_filename_dialog_insert_column(app):
    doc, cv, panel, cfg, BP = _gen_setup(app)
    dlg = BP._FilenamePatternDialog(cfg, cfg.rows, panel)
    try:
        dlg._le_pat.setText("")
        dlg._cb_col.setCurrentText("Name")
        dlg._insert_column()
        assert dlg._le_pat.text() == "[{Name}]"
        assert dlg._lbl_preview.text() == "Alice.png"
    finally:
        dlg.deleteLater(); panel.deleteLater(); cv.deleteLater()
        app.processEvents()


def test_filename_dialog_format_changes_ext(app):
    doc, cv, panel, cfg, BP = _gen_setup(app)
    dlg = BP._FilenamePatternDialog(cfg, cfg.rows, panel)
    try:
        dlg._le_pat.setText("[ROW_NAME]")
        dlg._cb_fmt.setCurrentText("pdf")
        assert dlg._lbl_preview.text() == "first.pdf"
    finally:
        dlg.deleteLater(); panel.deleteLater(); cv.deleteLater()
        app.processEvents()


# ── v4.3.5.60: variable binding UI removed from the properties panel ─────────
def test_properties_panel_has_no_variable_field(app):
    """The Variable binding field/button is gone from the properties panel
    (consolidated into the 3D Batch); le_var is kept hidden for compatibility."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=100, height=100)
    t = p.add_textbox(10, 10, 40, 20, "x")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    pp = E.PropPanel(cv)
    try:
        pp.load(t)
        # the field exists for back-compat but is not shown
        assert hasattr(pp, "le_var")
        assert not pp.le_var.isVisible()
        # _bind_var is now a no-op and must not bind anything
        pp.le_var.setText("should_not_bind")
        pp._bind_var()
        assert t.variable is None
        # loading an object that still has a variable must not crash
        t.variable = "legacy"
        pp.load(t)
    finally:
        pp.deleteLater(); cv.deleteLater(); app.processEvents()


# ── v4.3.5.61: old CSV-batch and Variables dialogs retired (redirect) ───────
def test_old_dialogs_redirect_to_batch(app, monkeypatch):
    """The retired Variables dialog and CSV-batch now redirect to the 3D Batch
    instead of defining doc variables / running the old per-row export."""
    import edof._apps.editor as E
    from edof import Document
    seen = []
    monkeypatch.setattr(E.QMessageBox, "information",
                        staticmethod(lambda *a, **k: seen.append(a[1] if len(a) > 1 else "")))
    doc = Document(); doc.add_page(width=100, height=100)
    ed = E.EdofEditor()
    try:
        ed.doc = doc
        assert hasattr(ed, "_open_batch_tab")
        ed._show_vars()
        assert seen and "Variables" in seen[-1]
        ed._batch_csv()
        assert "CSV" in seen[-1]
        # no doc variables were defined by the (now redirecting) dialog
        assert len(doc.variables.names()) == 0
        # the old dialog bodies are gone
        import inspect
        assert "DictReader" not in inspect.getsource(ed._batch_csv)
        assert "define_variable" not in inspect.getsource(ed._show_vars)
    finally:
        ed.deleteLater(); app.processEvents()


# ── v4.3.5.62: group child overlay + group effects panel ────────────────────
def test_child_overlay_carries_group_rotation(app):
    """A child of a rotated group gets its selection box rotated by the group, so
    it lands where the child is rendered (previously the box was axis-aligned in
    the child's local space and sat off to the side)."""
    import edof._apps.editor as E
    from edof.engine.transform import rotate_point, px_to_mm
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=200)
    a = p.add_shape("rect", 60, 60, 30, 30)
    b = p.add_shape("rect", 60, 110, 30, 30)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id]); g = cv.group_selection()
    try:
        g.transform.rotation = 40
        cv.set_sel_id(a.id)
        cv._refresh_overlay()
        poly = cv._overlay._poly
        box = [(px_to_mm(poly[i].x(), cv._dpi), px_to_mm(poly[i].y(), cv._dpi))
               for i in range(poly.count())]
        gt = g.transform; gcx = gt.x + gt.width / 2; gcy = gt.y + gt.height / 2
        at = a.transform
        corners = [(at.x, at.y), (at.x + at.width, at.y),
                   (at.x + at.width, at.y + at.height), (at.x, at.y + at.height)]
        rendered = [rotate_point(x, y, gcx, gcy, gt.rotation) for x, y in corners]
        for i in range(4):
            assert abs(box[i][0] - rendered[i][0]) < 1.0
            assert abs(box[i][1] - rendered[i][1]) < 1.0
    finally:
        cv.deleteLater(); app.processEvents()


def test_group_has_effects_panel(app):
    """Selecting a group shows the group panel (with a Layer Effects entry),
    not the empty panel."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=200)
    a = p.add_shape("rect", 50, 50, 30, 30)
    b = p.add_shape("rect", 50, 90, 30, 30)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id]); g = cv.group_selection()
    pp = E.PropPanel(cv)
    try:
        pp.load(g)
        assert pp._stack.currentIndex() == 9      # group page, not 0 (empty)
        assert hasattr(g, "effects")
    finally:
        pp.deleteLater(); cv.deleteLater(); app.processEvents()


# ── v4.3.5.63: rotated group resize keeps children inside the box ───────────
def test_rotated_group_resize_children_aligned(app):
    """Resizing a rotated group along its local axis scales children inside the
    box (axis-aligned in local space), keeping them aligned -- they used to
    scatter (positions drifted, perpendicular axis sheared)."""
    import edof._apps.editor as E
    import copy as cp, math
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px, rotate_point
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=200)
    a = p.add_shape("rect", 70, 70, 30, 25)
    b = p.add_shape("rect", 70, 105, 30, 25)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id]); g = cv.group_selection()

    def hw(tf, hx, hy):
        x = tf.x + hx * tf.width; y = tf.y + hy * tf.height
        cx = tf.x + tf.width / 2; cy = tf.y + tf.height / 2
        return rotate_point(x, y, cx, cy, tf.rotation)
    try:
        g.transform.rotation = 30
        W0 = g.transform.width
        mr = hw(g.transform, 1, 0.5)
        dx = 30 * math.cos(math.radians(30)); dy = 30 * math.sin(math.radians(30))
        gb = g.transform; cv.set_sel_id(g.id)
        cv._drag_mode = 'resize_MR'; cv._drag_sp0 = QPointF(0, 0)
        cv._drag_tf0 = cp.copy(gb)
        cv._drag_anchor = cv._compute_anchor(gb, 'MR')
        cv._drag_group_tf0 = [(c.transform.x, c.transform.y, c.transform.width,
                               c.transform.height, 1.0, 1.0) for c in g.flatten()]
        cv._drag_group_crot0 = {id(c): (c.transform.rotation or 0.0) for c in g.flatten()}
        cv._drag_group_cshear0 = {id(c): 0.0 for c in g.flatten()}
        cv._drag_group_pts0 = {}; cv._drag_group_path0 = {}
        cv._drag_path_data0 = None; cv._drag_line_pts0 = None
        cv._drag_font_size0_style = None
        cv._drag_glyph_scale_x0 = 1.0; cv._drag_glyph_scale_y0 = 1.0
        cv._apply_drag(QPointF(mm_to_px(mr[0] + dx, cv._dpi),
                               mm_to_px(mr[1] + dy, cv._dpi)), False, False, False)
        ca, cb = g.children[0], g.children[1]
        # children stay aligned (same local x), heights unchanged, widths scaled
        assert abs(ca.transform.x - cb.transform.x) < 0.5
        assert abs(ca.transform.height - 25) < 0.5 and abs(cb.transform.height - 25) < 0.5
        assert abs(ca.transform.width - 60) < 1.0   # sx = 2
    finally:
        cv.deleteLater(); app.processEvents()


def test_apply_to_all_hidden_for_single_selection(app):
    """The 'apply layer effects to all selected' button is hidden unless 2+
    objects are selected (it confused users on a single object/group)."""
    import edof._apps.editor as E
    from edof import Document
    doc = Document()
    p = doc.add_page(width=200, height=200)
    a = p.add_shape("rect", 30, 30, 40, 40)
    b = p.add_shape("rect", 90, 30, 40, 40)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    pp = E.PropPanel(cv)
    try:
        cv.set_multi_selection([a.id]); pp.load(a)
        assert all(btn.isHidden() for btn in pp._fx_apply_all_btns)
        cv.set_multi_selection([a.id, b.id]); pp.load(a)
        assert not any(btn.isHidden() for btn in pp._fx_apply_all_btns)
    finally:
        pp.deleteLater(); cv.deleteLater(); app.processEvents()


# ── v4.3.5.64: negative shear renders a parallelogram, not a triangle ────────
def test_negative_shear_is_parallelogram(app):
    """The shear offset sign bug collapsed a strongly negative shear into a
    triangle. A +s and -s shear must render mirror parallelograms of EQUAL area
    (a triangle would be ~half)."""
    import numpy as np
    from edof.engine.renderer import render_page
    from edof import Document

    def area(shx):
        doc = Document(); p = doc.add_page(width=200, height=150)
        a = p.add_shape("rect", 70, 50, 60, 50); a.fill.color = (220, 30, 30, 255)
        a.transform.shear_x = shx
        img = np.array(render_page(doc.pages[0], doc.resources, doc.variables,
                                   dpi=96).convert("RGBA"))
        return int(((img[:, :, 3] > 10) & (img[:, :, 0] > 100)).sum())

    pos = area(0.6); neg = area(-0.6)
    assert pos > 0 and neg > 0
    # equal within 5% (mirror parallelograms); a triangle would be ~50%
    assert abs(pos - neg) / max(pos, neg) < 0.05


def test_rotated_group_child_edit_keeps_others_still(app):
    """Editing one child of a ROTATED group must not move the others. The
    renderer rotates about the group BOX center (stable per-child), so the other
    children's visual centers stay put."""
    import edof._apps.editor as E
    import math
    from edof.engine.transform import rotate_point
    from edof import Document
    doc = Document(); p = doc.add_page(width=250, height=250)
    a = p.add_shape("rect", 50, 50, 20, 20)
    b = p.add_shape("rect", 90, 50, 20, 20)
    c = p.add_shape("rect", 130, 50, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id, c.id]); g = cv.group_selection()
    try:
        g.transform.rotation = 30

        def vis_center(ch):
            gt = g.transform; gcx = gt.x + gt.width / 2; gcy = gt.y + gt.height / 2
            ccx = ch.transform.x + ch.transform.width / 2
            ccy = ch.transform.y + ch.transform.height / 2
            return rotate_point(ccx, ccy, gcx, gcy, gt.rotation)
        b0 = vis_center(b); c0 = vis_center(c)
        a.transform.x += 15; a.transform.y += 15   # edit only child a
        b1 = vis_center(b); c1 = vis_center(c)
        assert abs(b1[0] - b0[0]) < 0.01 and abs(b1[1] - b0[1]) < 0.01
        assert abs(c1[0] - c0[0]) < 0.01 and abs(c1[1] - c0[1]) < 0.01
    finally:
        cv.deleteLater(); app.processEvents()


def test_nested_group_children_listed_in_panel(app):
    """A group nested inside a group must still list its own children in the
    Objects panel (they used to vanish below depth 1)."""
    import edof._apps.editor as E
    from PyQt6.QtCore import Qt
    from edof import Document
    doc = Document(); p = doc.add_page(width=200, height=200)
    a = p.add_shape("rect", 30, 30, 20, 20)
    b = p.add_shape("rect", 60, 30, 20, 20)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id]); g1 = cv.group_selection()
    c = p.add_shape("rect", 90, 30, 20, 20)
    cv.set_multi_selection([g1.id, c.id]); g2 = cv.group_selection()
    panel = E.ObjectListPanel(cv)
    try:
        panel.refresh()
        ids = {panel._list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(panel._list.count())}
        # the deeply nested leaves a and b must be present
        assert a.id in ids and b.id in ids
        assert g1.id in ids and g2.id in ids and c.id in ids
    finally:
        panel.deleteLater(); cv.deleteLater(); app.processEvents()


def test_rotated_group_renders_full_area(app):
    """A rotated group's child must render at ~full area (no square-buffer
    clipping). Regression guard for the 4.3.5.64->65 buffer rework."""
    import numpy as np
    from edof.engine.renderer import render_page
    from edof import Document
    import edof._apps.editor as E
    doc = Document(); p = doc.add_page(width=300, height=220)
    a = p.add_shape("rect", 80, 70, 70, 50); a.fill.color = (220, 30, 30, 255)
    b = p.add_shape("rect", 80, 130, 70, 25); b.fill.color = (40, 40, 40, 255)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id]); g = cv.group_selection()
    try:
        g.transform.rotation = 35
        img = np.array(render_page(doc.pages[0], doc.resources, doc.variables,
                                   dpi=96).convert("RGBA"))
        rm = (img[:, :, 0] > 150) & (img[:, :, 1] < 90) & (img[:, :, 3] > 10)
        f = (25.4 / 96) ** 2
        rendered = int(rm.sum()) * f
        expected = 70 * 50
        assert rendered / expected > 0.95   # within anti-aliasing tolerance
    finally:
        cv.deleteLater(); app.processEvents()


def test_compute_bounds_includes_shear(app):
    """A group box must fit sheared children (rotated rects that gained shear
    from a non-uniform resize). compute_bounds used to ignore shear, so the box
    over/under-shot the real extent."""
    import math
    from edof import Document
    import edof._apps.editor as E
    doc = Document(); p = doc.add_page(width=200, height=200)
    a = p.add_shape("rect", 70, 70, 40, 30); a.transform.rotation = 30
    b = p.add_shape("rect", 70, 110, 40, 30)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id]); g = cv.group_selection()
    try:
        # box without shear
        g.compute_bounds()
        w_no_shear = g.transform.width
        # add shear to the rotated child, recompute
        a.transform.shear_x = 0.6
        g.compute_bounds()
        w_shear = g.transform.width
        # shearing a rotated child changes its extent, so the box width changes
        assert abs(w_shear - w_no_shear) > 1.0
        # and the box must actually contain the sheared child's corners
        t = a.transform
        cx, cy = t.x + t.width / 2, t.y + t.height / 2
        rot = math.radians(t.rotation); shx = t.shear_x
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        gx0, gy0 = g.transform.x, g.transform.y
        gx1, gy1 = gx0 + g.transform.width, gy0 + g.transform.height
        for px, py in [(t.x, t.y), (t.x + t.width, t.y),
                       (t.x + t.width, t.y + t.height), (t.x, t.y + t.height)]:
            dx, dy = px - cx, py - cy
            dx = dx + shx * dy
            wx = cx + dx * cos_r - dy * sin_r
            wy = cy + dx * sin_r + dy * cos_r
            assert gx0 - 0.5 <= wx <= gx1 + 0.5
            assert gy0 - 0.5 <= wy <= gy1 + 0.5
    finally:
        cv.deleteLater(); app.processEvents()


def test_group_resize_back_and_forth_restores_child(app):
    """Resizing a group's side and back must restore a rotated child exactly.
    _shear_decompose ignored the child's existing shear, so the second
    (inverse) resize re-derived shear from rotation alone and collapsed it
    (shear jumped to ~-1.06). Composing with the prior shear makes diag(1/s)
    after diag(s) a true inverse."""
    import math
    from PyQt6.QtCore import QPointF
    from edof.engine.transform import mm_to_px, rotate_point
    from edof import Document
    import edof._apps.editor as E
    import copy as cp
    doc = Document(); p = doc.add_page(width=200, height=160)
    a = p.add_shape("rect", 50, 50, 40, 44); a.transform.rotation = 20
    b = p.add_shape("ellipse", 95, 55, 48, 40)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id]); g = cv.group_selection()

    def hw(tf, hx, hy):
        x = tf.x + hx * tf.width; y = tf.y + hy * tf.height
        cx = tf.x + tf.width / 2; cy = tf.y + tf.height / 2
        return rotate_point(x, y, cx, cy, tf.rotation)

    def start(g):
        gt = g.transform; cv.set_sel_id(g.id)
        cv._drag_mode = 'resize_MR'; cv._drag_sp0 = QPointF(0, 0)
        cv._drag_tf0 = cp.copy(gt); cv._drag_anchor = cv._compute_anchor(gt, 'MR')
        cv._drag_group_tf0 = [(c.transform.x, c.transform.y, c.transform.width,
                               c.transform.height, 1.0, 1.0) for c in g.flatten()]
        cv._drag_group_crot0 = {id(c): (c.transform.rotation or 0.0) for c in g.flatten()}
        cv._drag_group_cshear0 = {id(c): (getattr(c.transform, 'shear_x', 0.0) or 0.0)
                                  for c in g.flatten()}
        cv._drag_group_pts0 = {}; cv._drag_group_path0 = {}
        cv._drag_path_data0 = None; cv._drag_line_pts0 = None
        cv._drag_font_size0_style = None
        cv._drag_glyph_scale_x0 = 1.0; cv._drag_glyph_scale_y0 = 1.0
    try:
        r0 = a.transform.rotation; w0 = a.transform.width; h0 = a.transform.height
        start(g); mr = hw(g.transform, 1, 0.5)
        cv._apply_drag(QPointF(mm_to_px(mr[0] - 40, cv._dpi),
                               mm_to_px(mr[1], cv._dpi)), False, False, False)
        g.compute_bounds()
        assert abs(a.transform.shear_x) > 0.1   # drag 1 sheared it
        start(g); mr = hw(g.transform, 1, 0.5)
        cv._apply_drag(QPointF(mm_to_px(mr[0] + 40, cv._dpi),
                               mm_to_px(mr[1], cv._dpi)), False, False, False)
        g.compute_bounds()
        # back to the start: rotation, size and shear restored
        assert abs(a.transform.rotation - r0) < 0.5
        assert abs(a.transform.shear_x) < 0.02
        assert abs(a.transform.width - w0) < 0.5 and abs(a.transform.height - h0) < 0.5
    finally:
        cv.deleteLater(); app.processEvents()


def test_rotated_group_with_sheared_child_no_clip(app):
    """A rotated group whose child carries shear must not clip the child: the
    group buffer is sized from the child's SHEARED corners. Built from the u4
    repro (a cut-off rect corner)."""
    import numpy as np
    from edof.engine.renderer import render_page
    from edof import Document
    import edof._apps.editor as E
    doc = Document(); p = doc.add_page(width=200, height=160)
    a = p.add_shape("rect", 55, 55, 45, 45); a.fill.color = (90, 140, 240, 255)
    a.transform.rotation = 18; a.transform.shear_x = -0.75   # strong shear
    b = p.add_shape("rect", 55, 55, 45, 45); b.fill.color = (0, 0, 0, 0)
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv.set_multi_selection([a.id, b.id]); g = cv.group_selection()
    try:
        g.transform.rotation = 25   # rotated group -> buffer path
        img = np.array(render_page(doc.pages[0], doc.resources, doc.variables,
                                   dpi=96).convert("RGBA"))
        bm = (img[:, :, 2] > 180) & (img[:, :, 0] < 160) & (img[:, :, 1] > 100) & (img[:, :, 3] > 10)
        f = (25.4 / 96) ** 2
        total = int(bm.sum()) * f
        # parallelogram area = width*height (shear preserves area); not clipped
        expected = a.transform.width * a.transform.height
        assert total >= expected * 0.95
    finally:
        cv.deleteLater(); app.processEvents()


def test_variable_text_run_serialization(app):
    """A TextRun's variable binding (rid + var_name) round-trips through
    to_dict/from_dict; an ordinary run carries neither."""
    from edof.format.styles import TextRun
    plain = TextRun(text="hi")
    assert "rid" not in plain.to_dict() and "var_name" not in plain.to_dict()
    v = TextRun(text="World", rid="abc123", var_name="name")
    d = v.to_dict()
    assert d["rid"] == "abc123" and d["var_name"] == "name"
    r = TextRun.from_dict(d)
    assert r.rid == "abc123" and r.var_name == "name" and r.text == "World"


def test_variable_text_batch_substitutes_run(app):
    """A batch column targeting run.text on a stable rid replaces just that run
    and keeps TextBox.text in sync."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof.batch.model import BatchConfig, BatchRow, build_ref, apply_row_to_document
    doc = Document(); p = doc.add_page(width=120, height=40)
    tb = p.add_textbox(5, 5, 110, 25, "")
    tb.runs = [TextRun(text="Hello "),
               TextRun(text="World", rid="r1", var_name="name"),
               TextRun(text="!")]
    tb.text = "".join(r.text for r in tb.runs)
    cfg = BatchConfig()
    col = cfg.add_column(build_ref(p, tb), "run.text", "name", "text")
    col.run_id = "r1"
    row = BatchRow(); row.values[col.column_id] = "Alice"
    n = apply_row_to_document(cfg, doc, row)
    assert n == 1
    assert tb.runs[1].text == "Alice"
    assert tb.text == "Hello Alice!"
    # the binding finds the run by rid, not position: insert a run before it
    tb.runs.insert(0, TextRun(text=">> "))
    row2 = BatchRow(); row2.values[col.column_id] = "Bob"
    apply_row_to_document(cfg, doc, row2)
    assert tb.runs[2].text == "Bob"   # still the rid='r1' run


def test_variable_text_run_properties_batchable(app):
    """A run's style fields (font size) are batchable on the same rid."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof.batch.model import BatchConfig, BatchRow, build_ref, apply_row_to_document
    doc = Document(); p = doc.add_page(width=120, height=40)
    tb = p.add_textbox(5, 5, 110, 25, "")
    tb.runs = [TextRun(text="X", rid="r1", var_name="big")]
    cfg = BatchConfig()
    col = cfg.add_column(build_ref(p, tb), "run.font_size", "size", "number")
    col.run_id = "r1"
    row = BatchRow(); row.values[col.column_id] = "9.0"
    apply_row_to_document(cfg, doc, row)
    assert abs((tb.runs[0].font_size or 0) - 9.0) < 1e-6


def test_variable_run_survives_normalize(app):
    """A variable run must not be merged into an identically-formatted neighbour
    (its rid keeps it distinct), but two runs with the SAME rid do merge."""
    from edof.format.styles import TextRun
    from edof._apps.edof_text_editor import _normalize_runs
    runs = [TextRun(text="a "), TextRun(text="b", rid="r1", var_name="v"), TextRun(text=" c")]
    assert len(_normalize_runs(runs)) == 3
    same = [TextRun(text="a", rid="r1", var_name="v"), TextRun(text="b", rid="r1", var_name="v")]
    assert len(_normalize_runs(same)) == 1
    diff = [TextRun(text="a", rid="r1", var_name="v"), TextRun(text="b", rid="r2", var_name="w")]
    assert len(_normalize_runs(diff)) == 2


def test_show_variables_highlight(app):
    """With set_show_variables(True), a variable run renders a tint marker that
    a plain run doesn't; off, nothing extra is drawn."""
    import numpy as np
    from edof import Document
    from edof.format.styles import TextRun
    from edof.engine.renderer import render_page
    from edof.engine.text_engine import set_show_variables
    doc = Document(); p = doc.add_page(width=120, height=40)
    tb = p.add_textbox(5, 8, 110, 24, "")
    tb.runs = [TextRun(text="Hi "), TextRun(text="Name", rid="r1", var_name="n"),
               TextRun(text="!")]
    tb.text = "Hi Name!"

    def tint_px():
        img = np.array(render_page(p, doc.resources, doc.variables,
                                   dpi=96).convert("RGBA"))
        m = ((img[:, :, 2] > 180) & (img[:, :, 0] > 50) & (img[:, :, 0] < 150)
             & (img[:, :, 1] > 100) & (img[:, :, 1] < 200))
        return int(m.sum())
    try:
        set_show_variables(False)
        off = tint_px()
        set_show_variables(True)
        on = tint_px()
        assert off == 0
        assert on > 0
    finally:
        set_show_variables(False)


def test_run_descriptor_all_fields(app):
    """find_descriptor_with_run_id resolves every offered run attribute (text,
    font_size, colour, bold, italic) to the right run by rid."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof.batch import find_descriptor_with_run_id
    doc = Document(); p = doc.add_page(width=120, height=40)
    tb = p.add_textbox(5, 5, 110, 25, "")
    tb.runs = [TextRun(text="Hi"), TextRun(text="X", rid="r9", var_name="v",
                                           font_size=7.0, bold=True)]
    tb.text = "HiX"
    for field, expect in [("text", "X"), ("font_size", 7.0), ("bold", "true")]:
        d = find_descriptor_with_run_id(tb, "run.%s" % field, "r9")
        assert d is not None, field
        assert d.get(tb) == expect, (field, d.get(tb))
    # colour + italic descriptors exist too
    assert find_descriptor_with_run_id(tb, "run.color", "r9") is not None
    assert find_descriptor_with_run_id(tb, "run.italic", "r9") is not None
    # unknown rid -> descriptor still builds but reads None (no matching run)
    d = find_descriptor_with_run_id(tb, "run.text", "nope")
    assert d.get(tb) is None


def test_text_editor_read_only_blocks_typing(app):
    """With _read_only set, a printable keypress does not change the text; a
    navigation key still works."""
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import Qt, QEvent
    from edof.format.objects import TextBox
    from edof._apps.edof_text_editor import EdofTextEditor
    tb = TextBox(); tb.text = "abc"
    ed = EdofTextEditor(tb)
    try:
        ed._read_only = True
        before = "".join(r.text or "" for r in ed._runs)
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.NoModifier, "X")
        ed.keyPressEvent(ev)
        after = "".join(r.text or "" for r in ed._runs)
        assert before == after  # typing blocked
        # turning it off lets typing through
        ed._read_only = False
        ev2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.NoModifier, "X")
        ed.keyPressEvent(ev2)
        assert "".join(r.text or "" for r in ed._runs) != after
    finally:
        ed.deleteLater()
        app.processEvents()


def test_run_descriptor_extended_fields(app):
    """The extended run attributes (font, highlight/background, underline,
    strikethrough) all resolve and write to the right run by rid."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof.batch import find_descriptor_with_run_id, _RUN_FIELDS
    for f in ("font_family", "background", "underline", "strikethrough"):
        assert f in _RUN_FIELDS, f
    doc = Document(); p = doc.add_page(width=120, height=40)
    tb = p.add_textbox(5, 5, 110, 25, "")
    tb.runs = [TextRun(text="X", rid="r1", var_name="v")]
    tb.text = "X"
    # write a font + underline through the descriptors
    d_font = find_descriptor_with_run_id(tb, "run.font_family", "r1")
    d_font.set(tb, "Georgia")
    assert tb.runs[0].font_family == "Georgia"
    d_ul = find_descriptor_with_run_id(tb, "run.underline", "r1")
    d_ul.set(tb, "true")
    assert tb.runs[0].underline is True
    d_bg = find_descriptor_with_run_id(tb, "run.background", "r1")
    assert d_bg is not None


def test_load_dedupes_duplicate_run_columns(app):
    """Loading a doc with two columns on the same run_id+attr_path keeps one,
    so the variable isn't overwritten by a duplicate (the 'stuck variable' bug)."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof.format.serializer import EdofSerializer
    from edof.batch.model import BatchRow, build_ref, apply_row_to_document
    import tempfile, os, copy as _cp
    doc = Document(); p = doc.add_page(width=120, height=40)
    tb = p.add_textbox(5, 5, 110, 25, "")
    tb.runs = [TextRun(text="Ahoj "), TextRun(text="X", rid="rr", var_name="n")]
    tb.text = "Ahoj X"
    ref = build_ref(p, tb)
    # two run.text columns on the same rid (the duplicate-creation bug)
    c1 = doc.batch.add_column(ref, "run.text", "n", "text"); c1.run_id = "rr"
    c2 = doc.batch.add_column(ref, "run.text", "n", "text"); c2.run_id = "rr"
    r0 = BatchRow(); r0.values = {c1.column_id: "Davide", c2.column_id: "Katko"}
    r1 = BatchRow(); r1.values = {c1.column_id: "Tondo", c2.column_id: "Katko"}
    doc.batch.rows = [r0, r1]
    fd, path = tempfile.mkstemp(suffix=".edof"); os.close(fd)
    try:
        EdofSerializer().save(doc, path)
        d2 = EdofSerializer().load(path)
        # duplicate dropped
        run_text_cols = [c for c in d2.batch.columns if c.attr_path == "run.text"]
        assert len(run_text_cols) == 1
        # the variable now differs per row
        outs = []
        for i in range(2):
            rd = _cp.deepcopy(d2)
            apply_row_to_document(rd.batch, rd, rd.batch.rows[i])
            outs.append(rd.pages[0].objects[0].runs[1].text)
        assert outs[0] != outs[1]
    finally:
        os.unlink(path)


def test_preview_mirrors_into_inline_editor(app):
    """In document mode the inline editor holds its own runs; previewing a row
    must load the substituted runs into the editor (and restore on exit), else
    the body keeps showing the un-substituted text under the preview."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof.batch.model import BatchRow, build_ref
    from edof._apps.editor import EdofCanvas
    doc = Document(); p = doc.add_page(width=120, height=40)
    tb = p.add_textbox(5, 5, 110, 25, ""); tb.name = "document_body"
    tb.runs = [TextRun(text="Ahoj "), TextRun(text="X", rid="r1", var_name="n")]
    tb.text = "Ahoj X"
    ref = build_ref(p, tb)
    col = doc.batch.add_column(ref, "run.text", "n", "text"); col.run_id = "r1"
    r0 = BatchRow(); r0.values = {col.column_id: "Davide"}; doc.batch.rows.append(r0)

    class _Ed:
        def __init__(s, runs): s._runs = runs; s._read_only = False
        def _invalidate(s): pass
    class _C: pass
    c = _C()
    c._inline_widget = _Ed(tb.runs)
    c._inline_obj = tb
    c._doc = doc
    c._batch_preview_row = None
    c._batch_is_recording = False
    c._inline_live_runs = None
    c._apply_preview_to_inline = EdofCanvas._apply_preview_to_inline.__get__(c)

    assert c._inline_widget._runs[1].text == "X"
    c._batch_preview_row = r0
    c._apply_preview_to_inline()
    assert c._inline_widget._runs[1].text == "Davide"   # preview mirrored in
    c._batch_preview_row = None
    c._apply_preview_to_inline()
    assert c._inline_widget._runs[1].text == "X"          # live restored


def test_record_restore_restores_runs(app):
    """Stopping a recording must restore rich-text runs to the template, else a
    value recorded into a run stays on the base and an empty cell in another row
    inherits it instead of resetting to the template default."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    import copy as _cp
    base = Document(); bp = base.add_page(width=120, height=40)
    btb = bp.add_textbox(5, 5, 110, 25, ""); btb.name = "document_body"
    btb.runs = [TextRun(text="Ahoj "),
                TextRun(text="Jmeno", rid="r1", var_name="n", color=(0, 0, 0, 255))]
    btb.text = "Ahoj Jmeno"
    live = _cp.deepcopy(base)
    live.pages[0].objects[0].runs[1].color = (255, 0, 0, 255)
    live.pages[0].objects[0].runs[1].text = "Bob"

    class _CV:
        _page_idx = 0
        def _invalidate_page_cache(s, i): pass
        def _start_render(s): pass
    class _P: pass
    panel = _P(); panel._doc = live; panel._canvas = _CV()
    panel._restore_document_from = EdofBatchTemplatePanel._restore_document_from.__get__(panel)
    panel._restore_document_from(base)
    r = live.pages[0].objects[0].runs[1]
    assert r.color == (0, 0, 0, 255)
    assert r.text == "Jmeno"


def test_variable_runs_lists_dedups(app):
    """_variable_runs lists (rid, var_name) for variable runs, de-duped by rid,
    so the Objects panel shows one virtual object per variable."""
    from edof.format.styles import TextRun
    from edof.format.objects import TextBox
    from edof._apps.editor import _variable_runs
    tb = TextBox()
    tb.runs = [TextRun(text="a"),
               TextRun(text="b", rid="r1", var_name="x"),
               TextRun(text="c", rid="r2", var_name="y"),
               TextRun(text="d", rid="r1", var_name="x")]  # dup rid
    out = _variable_runs(tb)
    # v4.4.0: third element counts the SEPARATE spans of the rid ("x" lives on
    # two non-adjacent spans here, so the panel shows "x (×2)")
    assert out == [("r1", "x", 2), ("r2", "y", 1)]
    # a plain object with no variable runs -> empty
    tb2 = TextBox(); tb2.runs = [TextRun(text="plain")]
    assert _variable_runs(tb2) == []


def test_refresh_from_tb_keeps_selection(app):
    """A balance pass (refresh_from_tb) must keep the selection anchor, else any
    selection is wiped on every render while the body overflows -- which happens
    as soon as a header/footer shrinks the body box."""
    from edof.format.objects import TextBox
    from edof.format.styles import TextRun
    from edof._apps.edof_text_editor import EdofTextEditor
    tb = TextBox(); tb.text = "Ahoj svete jak se mas"
    tb.runs = [TextRun(text="Ahoj svete jak se mas")]
    ed = EdofTextEditor(tb)
    try:
        ed._anchor = 0; ed._cursor = 4
        assert ed._has_selection()
        ed.refresh_from_tb()
        assert ed._has_selection()           # selection survived
        assert ed._anchor == 0 and ed._cursor == 4
        # anchor is clamped if content shrank
        tb.runs = [TextRun(text="Hi")]; tb.text = "Hi"
        ed._anchor = 0; ed._cursor = 2
        ed.refresh_from_tb()
        assert ed._anchor is not None and ed._anchor <= 2
    finally:
        ed.deleteLater()
        app.processEvents()


def test_set_run_attr_across_multiple_variables(app):
    """v4.3.6.13: shared run-attribute editing toggles an attribute as a batch
    variable across several selected variable runs at once."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof._apps.editor import EdofCanvas
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = Document(); doc.mode = "document"
    p = doc.add_page(width=120, height=60)
    tb = p.add_textbox(5, 5, 110, 40, ""); tb.name = "document_body"
    tb.runs = [TextRun(text="A "), TextRun(text="X", rid="r1", var_name="x"),
               TextRun(text=" "), TextRun(text="Y", rid="r2", var_name="y")]
    tb.text = "A X Y"
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl._doc = doc
    try:
        targets = [(tb, "r1"), (tb, "r2")]
        assert tpl.run_attr_state(targets)["color"] == "none"
        tpl.set_run_attr(targets, "color", "color", True)
        assert tpl.run_attr_state(targets)["color"] == "all"
        cols = {(c.run_id, c.attr_path) for c in doc.batch.columns}
        assert ("r1", "run.color") in cols and ("r2", "run.color") in cols
        # partial -> 'some'
        tpl.set_run_attr([(tb, "r1")], "bold", "enum", True)
        assert tpl.run_attr_state(targets)["bold"] == "some"
        # remove
        tpl.set_run_attr(targets, "color", "color", False)
        assert tpl.run_attr_state(targets)["color"] == "none"
    finally:
        cv.deleteLater(); app.processEvents()


def test_virtual_variable_selection_sticks(app):
    """v4.4.0: variable multi-select lives in row CHECKBOXES, not the Qt
    selection. A refresh keeps the vrun item listed (non-selectable) and the
    checkbox state is restored from the canvas checked set."""
    from edof import Document
    from edof.format.styles import TextRun
    from edof._apps.editor import EdofCanvas, ObjectListPanel
    from PyQt6.QtCore import Qt
    doc = Document(); p = doc.add_page(width=120, height=40)
    tb = p.add_textbox(5, 5, 110, 25, ""); tb.name = "lbl"
    tb.runs = [TextRun(text="A "), TextRun(text="X", rid="r1", var_name="x")]
    tb.text = "A X"
    cv = EdofCanvas(); cv._doc = doc
    panel = ObjectListPanel(cv)
    try:
        vid = "vrun:%s:r1" % tb.id
        cv._active_var_focus = (tb.id, "r1")
        cv._selected_var_rids = {"r1"}
        cv._checked_var_vids = {vid}
        panel.refresh()
        items = [panel._list.item(i) for i in range(panel._list.count())]
        vitems = [it for it in items
                  if it.data(Qt.ItemDataRole.UserRole) == vid]
        assert len(vitems) == 1
        # vrun rows are excluded from the Qt selection model by design
        assert not (vitems[0].flags() & Qt.ItemFlag.ItemIsSelectable)
    finally:
        cv.deleteLater(); panel.deleteLater(); app.processEvents()


def test_shared_attr_targets_and_apply(app):
    """v4.3.6.14: variables selected in the panel are remembered as shared
    targets; applying an attribute (the dialog's effect) toggles it across all
    of them. (The dialog itself is UI; we exercise the underlying apply path.)"""
    from edof import Document
    from edof.format.styles import TextRun
    from edof._apps.editor import EdofCanvas
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = Document(); doc.mode = "document"
    p = doc.add_page(width=120, height=60)
    tb = p.add_textbox(5, 5, 110, 40, ""); tb.name = "document_body"
    tb.runs = [TextRun(text="A "), TextRun(text="X", rid="r1", var_name="x"),
               TextRun(text=" "), TextRun(text="Y", rid="r2", var_name="y")]
    tb.text = "A X Y"
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl._doc = doc
    try:
        tpl.set_shared_targets([(tb, "r1"), (tb, "r2")])
        assert len(tpl._shared_targets) == 2
        assert hasattr(tpl, "edit_shared_attrs_dialog")
        # the dialog's accept path calls set_run_attr; verify that applies to all
        tpl.set_run_attr(tpl._shared_targets, "color", "color", True)
        cols = {(c.run_id, c.attr_path) for c in doc.batch.columns}
        assert ("r1", "run.color") in cols and ("r2", "run.color") in cols
    finally:
        cv.deleteLater(); app.processEvents()


def test_rightclick_variable_uses_template_panel(app):
    """v4.3.6.15: the right-click / toolbar 'make variable' flow must hand off to
    the TEMPLATE panel, because only it has _add_text_variable (which syncs the
    rid to the textbox, turns the rainbow on, and refreshes the Objects panel).
    The wrapper panel lacks that method, so routing through it dropped the
    variable into the no-sync / no-refresh fallback -- the exact bug where a
    right-click variable neither coloured nor appeared in the Objects panel."""
    from edof._apps.batch_panel import EdofBatchPanel, EdofBatchTemplatePanel
    from edof._apps.editor import EdofCanvas
    cv = EdofCanvas()
    try:
        wrapper = EdofBatchPanel(cv)
        tpl = EdofBatchTemplatePanel(cv)
        # wrapper must NOT have it; template MUST
        assert not hasattr(wrapper, "_add_text_variable")
        assert hasattr(tpl, "_add_text_variable")
        # the fallback in _make_text_variable now syncs + refreshes; confirm the
        # editor exposes the pieces it relies on
        assert hasattr(cv, "objectChanged")
    finally:
        cv.deleteLater(); app.processEvents()


def test_run_variable_links_to_text_objects(app):
    """v4.3.6.16: a run-text variable can be linked to other text objects. The
    Link dialog lists text objects (not an empty list), and applying the value
    fills the linked object's whole text while the source span resolves via its
    rid."""
    import edof
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref, apply_row_to_document, BatchRow
    from edof._apps.batch_panel import _LinkObjectsDialog
    doc = edof.new(width=200, height=100)
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    o1 = p.add_textbox(5, 5, 90, 30, ""); o1.name = "src"
    o1.runs = [TextRun(text="R "), TextRun(text="XXX", rid="r1", var_name="rest")]
    o1.text = "R XXX"
    o2 = p.add_textbox(5, 50, 90, 30, "ph"); o2.name = "dst"; o2.text = "ph"
    o2.runs = [TextRun(text="ph")]
    cfg = doc.batch
    col = cfg.add_column(build_ref(p, o1), "run.text", "rest", "text"); col.run_id = "r1"
    # v4.3.6.20: dialog lists OTHER text objects, not the source span's own object
    dlg = _LinkObjectsDialog(col, list(doc.pages))
    try:
        labels = [it.text(0) for it, pi, ref in dlg._rows]
        assert any("dst" in l for l in labels)        # other object listed
        assert not any("src" in l for l in labels)    # source excluded
    finally:
        dlg.deleteLater(); app.processEvents()
    # link o2 and apply
    col.extra_targets = [build_ref(p, o2)]
    row = BatchRow(); row.values = {col.column_id: "Noma"}
    n = apply_row_to_document(cfg, doc, row)
    assert n == 2
    assert any(r.text == "Noma" for r in o1.runs)   # source span filled
    assert o2.text == "Noma"                          # linked object's text filled


def test_first_variable_after_new_doc_binds_panels(app):
    """v4.3.6.17: the batch panels used to rebind to a document only when their
    tab was opened, so the FIRST text variable made right after a new document
    hit a None doc (cfg None) and silently did nothing -- no column, no rainbow,
    nothing in the Objects panel. The documentChanged signal now rebinds them on
    every document swap, so the first variable works."""
    from PyQt6.QtWidgets import QDialog
    import edof
    from edof.format.document_body import DocumentBody, Paragraph
    from edof.format.document_boxes import DocumentTextBox
    from edof.format.styles import TextRun
    from edof.engine.document_paginate import find_document_body_on_page
    from edof._apps.editor import EdofEditor, _variable_runs
    _orig = QDialog.exec
    QDialog.exec = lambda self: QDialog.DialogCode.Accepted
    ed = EdofEditor()
    try:
        w, h = 210, 297
        doc = edof.new(width=w, height=h); doc.mode = "document"; doc.margins = (15, 15, 15, 15)
        if not doc.pages: doc.add_page(width=w, height=h)
        doc.body = DocumentBody(); doc.body.page_margins_mm = (15, 15, 15, 15)
        doc.body.paragraphs = [Paragraph(runs=[TextRun(text="")], style_id="Normal")]
        tb = DocumentTextBox(); tb.transform.x = 15; tb.transform.y = 15
        tb.transform.width = 180; tb.transform.height = 267
        tb.style.font_family = "Arial"; tb.style.font_size = 3.881; tb.style.padding = 0.0
        tb.text = "Ahoj svete"; tb.runs = [TextRun(text="Ahoj svete")]; tb.name = "document_body"
        doc.pages[0].objects.append(tb)
        ed.doc = doc; ed._canvas.set_document(doc)
        # signal must have rebound the panels WITHOUT opening the batch tab
        assert ed._batch_tpl._doc is doc
        pb = find_document_body_on_page(doc.pages[0])
        ed._canvas._start_inline(pb)
        ied = ed._canvas._inline_widget
        ied._anchor = 5; ied._cursor = 10
        ed._canvas._make_text_variable()
        app.processEvents()
        # the variable now exists, colours, and is listed
        pb2 = find_document_body_on_page(doc.pages[0])
        assert _variable_runs(pb2)
        assert any("vrun:" in str(ed._obj_panel._list.item(i).data(0x0100))
                   for i in range(ed._obj_panel._list.count())) or \
               any(c.attr_path == "run.text" for c in doc.batch.columns)
    finally:
        QDialog.exec = _orig
        ed.deleteLater(); app.processEvents()


def test_remove_run_variable_clears_rid_and_panel(app):
    """v4.3.6.18: removing a run variable must also strip rid/var_name from the
    runs, so its rainbow highlight and Objects-panel entry go away too (the
    column alone doesn't drive those)."""
    from PyQt6.QtWidgets import QMessageBox
    import edof
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref
    from edof._apps.editor import EdofCanvas, _variable_runs
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    _q = QMessageBox.question
    QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
    doc = edof.new(width=200, height=100)
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    o1 = p.add_textbox(5, 5, 90, 30, ""); o1.name = "src"
    o1.runs = [TextRun(text="R "), TextRun(text="X", rid="r1", var_name="v")]
    cfg = doc.batch
    col = cfg.add_column(build_ref(p, o1), "run.text", "v", "text"); col.run_id = "r1"
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    try:
        assert _variable_runs(o1) and len(cfg.columns) == 1
        tpl._remove_variable(col)
        app.processEvents()
        assert not _variable_runs(o1)        # rid stripped
        assert len(cfg.columns) == 0
    finally:
        QMessageBox.question = _q
        cv.deleteLater(); app.processEvents()


def test_run_variable_link_dialog_in_document_mode(app):
    """v4.3.6.20: in document mode the Link dialog excludes the source body
    (where the variable already lives -- linking onto itself is a no-op) and
    lists real OTHER objects instead."""
    import edof
    from edof.format.document_boxes import DocumentTextBox
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref
    from edof._apps.batch_panel import _LinkObjectsDialog
    doc = edof.new(width=200, height=200); doc.mode = "document"
    if not doc.pages: doc.add_page(width=200, height=200)
    p = doc.pages[0]
    db = DocumentTextBox(); db.name = "document_body"; db.text = "R XXX"
    db.runs = [TextRun(text="R "), TextRun(text="XXX", rid="r1", var_name="v")]
    p.objects.append(db)
    other = p.add_textbox(10, 100, 80, 20, "ph"); other.name = "other_box"
    cfg = doc.batch
    col = cfg.add_column(build_ref(p, db), "run.text", "v", "text"); col.run_id = "r1"
    dlg = _LinkObjectsDialog(col, list(doc.pages))
    try:
        names = [it.text(0) for it, pi, ref in dlg._rows]
        assert not any("document_body" in n for n in names)   # source excluded
        assert any("other_box" in n for n in names)           # real object listed
    finally:
        dlg.deleteLater(); app.processEvents()


def test_run_variable_field_editors(app):
    """v4.3.6.18: run font variable gets a font dropdown, run bool variable gets
    a true/false dropdown, and number/colour fields show the run's current value
    as placeholder."""
    from PyQt6.QtWidgets import QFontComboBox, QComboBox, QLineEdit
    import edof
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref, BatchRow
    from edof._apps.editor import EdofCanvas
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = edof.new(width=200, height=100)
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    o1 = p.add_textbox(5, 5, 90, 30, ""); o1.name = "src"
    o1.runs = [TextRun(text="X", rid="r1", var_name="v", font_size=14.0,
                       bold=False, color="#ff0000", font_family="Georgia")]
    cfg = doc.batch
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    row = BatchRow(); cfg.demo_rows = [row]
    try:
        def mk(attr, kind):
            c = cfg.add_column(build_ref(p, o1), attr, attr.split(".")[1], kind)
            c.run_id = "r1"
            return tpl._make_field(c, row)
        assert isinstance(mk("run.font_family", "text"), QFontComboBox)
        wb = mk("run.bold", "enum")
        assert isinstance(wb, QComboBox)
        assert {wb.itemText(i) for i in range(wb.count())} == {"true", "false"}
        ws = mk("run.font_size", "number")
        le = ws if isinstance(ws, QLineEdit) else ws.findChild(QLineEdit)
        assert le.placeholderText() == "14.0"
    finally:
        cv.deleteLater(); app.processEvents()


def test_make_variable_without_attribute(app):
    """v4.3.6.19: you can name a text span as a variable WITHOUT any attribute --
    a targetable entity with no batch column."""
    from PyQt6.QtWidgets import QDialog, QCheckBox
    import edof
    from edof.format.styles import TextRun
    from edof.format.document_boxes import DocumentTextBox
    from edof.engine.document_paginate import find_document_body_on_page
    from edof._apps.editor import EdofCanvas, _variable_runs
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    _e, _c = QDialog.exec, QCheckBox.isChecked
    QDialog.exec = lambda self: QDialog.DialogCode.Accepted
    QCheckBox.isChecked = lambda self: False   # no attributes ticked
    doc = edof.new(width=200, height=100); doc.mode = "document"
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    tb = DocumentTextBox(); tb.transform.x = 5; tb.transform.y = 5
    tb.transform.width = 180; tb.transform.height = 60
    tb.style.font_family = "Arial"; tb.style.font_size = 3.881; tb.style.padding = 0.0
    tb.text = "Ahoj svete"; tb.runs = [TextRun(text="Ahoj svete")]; tb.name = "document_body"
    p.objects.append(tb)
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    pb = find_document_body_on_page(p); cv._start_inline(pb); ied = cv._inline_widget
    ied._anchor = 5; ied._cursor = 10
    try:
        tpl._add_text_variable(ied)
        app.processEvents()
        pb2 = find_document_body_on_page(p)
        assert _variable_runs(pb2)            # entity created
        assert len(doc.batch.columns) == 0    # no column
    finally:
        QDialog.exec = _e; QCheckBox.isChecked = _c
        cv.deleteLater(); app.processEvents()


def test_remove_run_variable_entity(app):
    """v4.3.6.19: removing a variable entity clears its rid from the runs AND
    drops every column bound to it."""
    import edof
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref
    from edof._apps.editor import EdofCanvas, _variable_runs
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = edof.new(width=200, height=100)
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    o1 = p.add_textbox(5, 5, 90, 30, ""); o1.name = "src"
    o1.runs = [TextRun(text="R "), TextRun(text="X", rid="r1", var_name="v")]
    cfg = doc.batch
    cfg.add_column(build_ref(p, o1), "run.text", "v", "text").run_id = "r1"
    cfg.add_column(build_ref(p, o1), "run.color", "v_c", "color").run_id = "r1"
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    try:
        tpl.remove_run_variable([(o1, "r1")])
        app.processEvents()
        assert not _variable_runs(o1)
        assert len(cfg.columns) == 0
    finally:
        cv.deleteLater(); app.processEvents()


def test_rename_run_variable(app):
    """v4.3.6.20: renaming a variable updates var_name on runs and columns."""
    import edof
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref
    from edof._apps.editor import EdofCanvas, _variable_runs
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = edof.new(width=200, height=100)
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    o1 = p.add_textbox(5, 5, 90, 30, ""); o1.name = "src"
    o1.runs = [TextRun(text="R "), TextRun(text="X", rid="r1", var_name="inlinetext01")]
    cfg = doc.batch
    cfg.add_column(build_ref(p, o1), "run.text", "inlinetext01", "text").run_id = "r1"
    cfg.add_column(build_ref(p, o1), "run.color", "inlinetext01_color", "color").run_id = "r1"
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    try:
        tpl.rename_run_variable([(o1, "r1")], "restaurace")
        app.processEvents()
        assert _variable_runs(o1) == [("r1", "restaurace", 1)]
        assert sorted(c.var_name for c in cfg.columns) == ["restaurace", "restaurace_color"]
    finally:
        cv.deleteLater(); app.processEvents()


def test_no_attribute_variable_unique_names(app):
    """v4.3.6.20: two no-attribute variables get distinct default names (the
    name counter now also counts var_names on runs, not just columns)."""
    from PyQt6.QtWidgets import QDialog, QCheckBox
    import edof
    from edof.format.styles import TextRun
    from edof.format.document_boxes import DocumentTextBox
    from edof.engine.document_paginate import find_document_body_on_page
    from edof._apps.editor import EdofCanvas, _variable_runs
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    _e, _c = QDialog.exec, QCheckBox.isChecked
    QDialog.exec = lambda self: QDialog.DialogCode.Accepted
    QCheckBox.isChecked = lambda self: False
    doc = edof.new(width=200, height=100); doc.mode = "document"
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    tb = DocumentTextBox(); tb.transform.x = 5; tb.transform.y = 5
    tb.transform.width = 180; tb.transform.height = 60
    tb.style.font_family = "Arial"; tb.style.font_size = 3.881; tb.style.padding = 0.0
    tb.text = "Ahoj svete jak se mas"; tb.runs = [TextRun(text="Ahoj svete jak se mas")]
    tb.name = "document_body"
    p.objects.append(tb)
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    try:
        pb = find_document_body_on_page(p); cv._start_inline(pb); ied = cv._inline_widget
        ied._anchor = 5; ied._cursor = 10; tpl._add_text_variable(ied); app.processEvents()
        pb = find_document_body_on_page(p); cv._start_inline(pb); ied = cv._inline_widget
        ied._anchor = 11; ied._cursor = 14; tpl._add_text_variable(ied); app.processEvents()
        names = [vn for _r, vn, _n in _variable_runs(find_document_body_on_page(p))]
        assert len(names) == len(set(names)), names
    finally:
        QDialog.exec = _e; QCheckBox.isChecked = _c
        cv.deleteLater(); app.processEvents()


def test_link_dialog_excludes_source(app):
    """v4.3.6.20: the Link dialog lists OTHER objects, not the source where the
    variable already lives."""
    import edof
    from edof.format.styles import TextRun
    from edof.format.document_boxes import DocumentTextBox
    from edof.batch.model import build_ref
    from edof._apps.batch_panel import _LinkObjectsDialog
    doc = edof.new(width=200, height=200); doc.mode = "document"
    if not doc.pages: doc.add_page(width=200, height=200)
    p = doc.pages[0]
    body = DocumentTextBox(); body.name = "document_body"
    body.runs = [TextRun(text="Ahoj "), TextRun(text="Praha", rid="r1", var_name="mesto")]
    body.text = "Ahoj Praha"
    p.objects.append(body)
    p.add_textbox(10, 100, 80, 20, "placeholder").name = "box_mesto"
    cfg = doc.batch
    col = cfg.add_column(build_ref(p, body), "run.text", "mesto", "text"); col.run_id = "r1"
    dlg = _LinkObjectsDialog(col, [p])
    try:
        labels = [it.text(0) for (it, _pi, _ref) in dlg._rows]
        assert not any("document_body" in l for l in labels), labels
        assert any("box_mesto" in l for l in labels), labels
    finally:
        dlg.deleteLater(); app.processEvents()


def test_backspace_clears_phantom_selection(app):
    """v4.3.6.20: a click leaves anchor == cursor; backspace must not leave a
    phantom selection that the next edit would delete."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import Qt, QEvent
    from edof.format.objects import TextBox
    from edof.format.styles import TextRun
    from edof._apps.edof_text_editor import EdofTextEditor
    tb = TextBox(); tb.text = "Ahoj svete jak"; tb.runs = [TextRun(text="Ahoj svete jak")]
    ed = EdofTextEditor(tb)
    try:
        ed._clear_selection(); ed._anchor = 11; ed._cursor = 11   # simulate a click
        ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backspace,
                                   Qt.KeyboardModifier.NoModifier))
        assert not ed._has_selection()
    finally:
        ed.deleteLater(); app.processEvents()


def test_would_empty_variable(app):
    """v4.3.6.20: _would_empty_variable flags a variable's last character."""
    from edof.format.objects import TextBox
    from edof.format.styles import TextRun
    from edof._apps.edof_text_editor import EdofTextEditor
    tb = TextBox(); tb.text = "Ahoj X jak"
    tb.runs = [TextRun(text="Ahoj "), TextRun(text="X", rid="r1", var_name="v"),
               TextRun(text=" jak")]
    ed = EdofTextEditor(tb)
    try:
        assert ed._would_empty_variable(5) == "r1"   # the 'X'
        assert ed._would_empty_variable(0) is None    # plain text
    finally:
        ed.deleteLater(); app.processEvents()


def test_variable_fills_all_occurrences(app):
    """v4.3.6.21: a run-text column updates EVERY run carrying the rid, not just
    the first -- so the same variable on several spans all change together."""
    import edof
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref, apply_row_to_document, BatchRow
    doc = edof.new(width=200, height=100)
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    o = p.add_textbox(5, 5, 180, 60, ""); o.name = "body"
    o.runs = [TextRun(text="A "), TextRun(text="X", rid="r1", var_name="v"),
              TextRun(text=" B "), TextRun(text="X", rid="r1", var_name="v"),
              TextRun(text=" C "), TextRun(text="X", rid="r1", var_name="v")]
    o.text = "".join(r.text for r in o.runs)
    cfg = doc.batch
    col = cfg.add_column(build_ref(p, o), "run.text", "v", "text"); col.run_id = "r1"
    row = BatchRow(); row.values = {col.column_id: "Noma"}
    apply_row_to_document(cfg, doc, row)
    occ = [r.text for r in o.runs if getattr(r, "rid", None) == "r1"]
    assert occ == ["Noma", "Noma", "Noma"], occ


def test_add_selection_to_existing_variable(app, monkeypatch):
    """v4.3.6.21: 'Add to: <existing>' in the add-variable dialog gives the new
    span the existing variable's rid (no new column)."""
    from PyQt6.QtWidgets import QDialog, QCheckBox, QComboBox
    import edof
    from edof.format.styles import TextRun
    from edof.format.document_boxes import DocumentTextBox
    from edof.engine.document_paginate import find_document_body_on_page
    from edof._apps.editor import EdofCanvas
    from edof._apps.batch_panel import EdofBatchTemplatePanel
    doc = edof.new(width=200, height=100); doc.mode = "document"
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    tb = DocumentTextBox(); tb.transform.x = 5; tb.transform.y = 5
    tb.transform.width = 180; tb.transform.height = 60
    tb.style.font_family = "Arial"; tb.style.font_size = 3.881; tb.style.padding = 0.0
    tb.text = "Noma je super. Zkuste Noma."
    tb.runs = [TextRun(text="Noma je super. Zkuste Noma.")]; tb.name = "document_body"
    p.objects.append(tb)
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QCheckBox, "isChecked", lambda self: True)
    monkeypatch.setattr(QComboBox, "currentData", lambda self, role=0: None)
    try:
        pb = find_document_body_on_page(p); cv._start_inline(pb); ied = cv._inline_widget
        ied._anchor = 0; ied._cursor = 4
        tpl._add_text_variable(ied); app.processEvents()
        pb = find_document_body_on_page(p)
        rid0 = next(getattr(r, "rid", None) for r in pb.runs if getattr(r, "rid", None))
        cols_before = sum(1 for c in doc.batch.columns if c.run_id == rid0)
        monkeypatch.setattr(QComboBox, "currentData", lambda self, role=0: rid0)
        cv._start_inline(pb); ied = cv._inline_widget
        ied._anchor = 22; ied._cursor = 26
        tpl._add_text_variable(ied); app.processEvents()
        pb = find_document_body_on_page(p)
        cnt = sum(1 for r in pb.runs if getattr(r, "rid", None) == rid0)
        cols_after = sum(1 for c in doc.batch.columns if c.run_id == rid0)
        assert cnt == 2, cnt
        assert cols_after == cols_before
    finally:
        cv.deleteLater(); app.processEvents()


def test_merge_run_variables(app):
    """v4.3.6.21: folding one variable into another reassigns its runs to the
    primary rid and drops its column, so one column drives both spans."""
    import edof
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref, apply_row_to_document, BatchRow
    from edof._apps.batch_panel import _merge_run_variables_in_doc
    doc = edof.new(width=200, height=100)
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    o = p.add_textbox(5, 5, 180, 60, ""); o.name = "body"
    o.runs = [TextRun(text="A "), TextRun(text="David", rid="r1", var_name="v1"),
              TextRun(text=" B "), TextRun(text="David", rid="r2", var_name="v2")]
    o.text = "".join(r.text for r in o.runs)
    cfg = doc.batch
    c1 = cfg.add_column(build_ref(p, o), "run.text", "v1", "text"); c1.run_id = "r1"
    cfg.add_column(build_ref(p, o), "run.text", "v2", "text").run_id = "r2"
    assert _merge_run_variables_in_doc(doc, cfg, "r1", "v1", ["r2"])
    rids = [getattr(r, "rid", None) for r in o.runs if getattr(r, "rid", None)]
    assert rids == ["r1", "r1"]
    assert len(cfg.columns) == 1
    row = BatchRow(); row.values = {c1.column_id: "Katka"}
    apply_row_to_document(cfg, doc, row)
    assert [r.text for r in o.runs if getattr(r, "rid", None) == "r1"] == ["Katka", "Katka"]


def test_link_dialog_lists_other_variables(app):
    """v4.3.6.21: for a run variable the Link dialog lists OTHER run variables to
    fold in, and _accept collects them as merge rids."""
    from PyQt6.QtCore import Qt
    import edof
    from edof.format.styles import TextRun
    from edof.format.document_boxes import DocumentTextBox
    from edof.batch.model import build_ref
    from edof._apps.batch_panel import _LinkObjectsDialog
    doc = edof.new(width=200, height=200); doc.mode = "document"
    if not doc.pages: doc.add_page(width=200, height=200)
    p = doc.pages[0]
    body = DocumentTextBox(); body.name = "document_body"
    body.runs = [TextRun(text="A", rid="r1", var_name="v1"),
                 TextRun(text=" B ", ),
                 TextRun(text="C", rid="r2", var_name="v2")]
    body.text = "A B C"
    p.objects.append(body)
    cfg = doc.batch
    col = cfg.add_column(build_ref(p, body), "run.text", "v1", "text"); col.run_id = "r1"
    dlg = _LinkObjectsDialog(col, list(doc.pages))
    try:
        rids = [rid for (it, rid) in dlg._var_rows]
        assert "r2" in rids and "r1" not in rids   # other variable listed, not self
        for (it, rid) in dlg._var_rows:
            it.setCheckState(0, Qt.CheckState.Checked)
        dlg._accept()
        assert dlg._merge_rids == ["r2"]
    finally:
        dlg.deleteLater(); app.processEvents()


def test_merge_variables_with_inline_editor_active(app):
    """v4.3.6.23: merging variables must stick even when the body is being edited
    inline (its runs are a copy that the reflow syncs back to the page box)."""
    from PyQt6.QtCore import Qt
    import edof
    import edof._apps.batch_panel as BP
    from edof.format.styles import TextRun
    from edof.format.document_boxes import DocumentTextBox
    from edof.engine.document_paginate import find_document_body_on_page
    from edof._apps.editor import EdofCanvas
    from edof._apps.batch_panel import EdofBatchTemplatePanel, _LinkObjectsDialog
    doc = edof.new(width=200, height=100); doc.mode = "document"
    if not doc.pages: doc.add_page(width=200, height=100)
    p = doc.pages[0]
    tb = DocumentTextBox(); tb.transform.x = 5; tb.transform.y = 5
    tb.transform.width = 180; tb.transform.height = 60
    tb.style.font_family = "Arial"; tb.style.font_size = 3.881; tb.style.padding = 0.0
    tb.runs = [TextRun(text="Ahoj "), TextRun(text="David", rid="r1", var_name="v1"),
               TextRun(text=" a "), TextRun(text="David", rid="r2", var_name="v2")]
    tb.text = "".join(r.text for r in tb.runs); tb.name = "document_body"
    p.objects.append(tb)
    cfg = doc.batch
    from edof.batch.model import build_ref
    c1 = cfg.add_column(build_ref(p, tb), "run.text", "v1", "text"); c1.run_id = "r1"
    cfg.add_column(build_ref(p, tb), "run.text", "v2", "text").run_id = "r2"
    cv = EdofCanvas(); cv.set_document(doc)
    tpl = EdofBatchTemplatePanel(cv); tpl.set_document(doc)
    pb = find_document_body_on_page(p); cv._start_inline(pb)   # body IS being edited
    _orig = _LinkObjectsDialog.exec
    def fake(self):
        for (it, rid) in self._var_rows:
            it.setCheckState(0, Qt.CheckState.Checked)
        self._accept(); return BP.QDialog.DialogCode.Accepted
    _LinkObjectsDialog.exec = fake
    try:
        tpl._link_objects(c1)
        app.processEvents()
        pb2 = find_document_body_on_page(p)
        rids = set(getattr(r, "rid", None) for r in pb2.runs if getattr(r, "rid", None))
        # v4.4.0: LINK, not fold: both variables KEEP their rid and identity,
        # the redundant run.text column of v2 is dropped and v1's column
        # drives both spans via extra_run_ids.
        assert rids == {"r1", "r2"}, rids
        assert len(cfg.columns) == 1
        assert list(c1.extra_run_ids) == ["r2"]
        from edof.batch.model import BatchRow, apply_row_to_document
        row = BatchRow(page_target=0, values={c1.column_id: "Ahoj"})
        apply_row_to_document(cfg, doc, row)
        texts = {r.rid: r.text for r in pb2.runs if getattr(r, "rid", None)}
        assert texts == {"r1": "Ahoj", "r2": "Ahoj"}
    finally:
        _LinkObjectsDialog.exec = _orig
        cv.deleteLater(); app.processEvents()


def test_generate_dialog_single_output_modes(app):
    """v4.4.0: pdf/edof offer per-row vs single multipage output; single
    disables the per-row tag helpers; image formats hide the choice."""
    from edof._apps.batch_panel import _FilenamePatternDialog
    from edof.batch.model import BatchConfig, BatchRow
    cfg = BatchConfig()
    rows = [BatchRow(name="A"), BatchRow(name="B")]
    dlg = _FilenamePatternDialog(cfg, rows)
    dlg.show(); app.processEvents()
    try:
        # png: no output choice
        dlg._cb_fmt.setCurrentText("png"); app.processEvents()
        assert not dlg._rb_single.isVisible()
        # pdf: choice visible, defaults to per-row, tags enabled
        dlg._cb_fmt.setCurrentText("pdf"); app.processEvents()
        assert dlg._rb_single.isVisible() and dlg._rb_per_row.isChecked()
        assert all(w.isEnabled() for w in dlg._tag_buttons)
        # single: tags disabled, label switches, preview says one file
        dlg._rb_single.setChecked(True); app.processEvents()
        assert all(not w.isEnabled() for w in dlg._tag_buttons)
        assert dlg._lbl_pattern.text().startswith("Filename (one file)")
        assert "all 2 rows" in dlg._lbl_rowinfo.text()
        # accept carries the mode out
        dlg.out_dir = "/tmp"
        dlg._accept()
        assert dlg.output == "single" and dlg.fmt == "pdf"
        # back to png forces per_row again
        dlg2 = _FilenamePatternDialog(cfg, rows)
        dlg2.show(); app.processEvents()
        dlg2._cb_fmt.setCurrentText("edof"); app.processEvents()
        dlg2._rb_single.setChecked(True)
        dlg2._cb_fmt.setCurrentText("png"); app.processEvents()
        dlg2.out_dir = "/tmp"; dlg2._accept()
        assert dlg2.output == "per_row"
        dlg2.deleteLater()
    finally:
        dlg.deleteLater(); app.processEvents()


def test_editor_has_generate_batch_menu_slot():
    """v4.4.0: File menu 'Generate batch...' opens the panel's dialog without
    the batch dock ever being shown."""
    from edof._apps.editor import EdofEditor
    assert hasattr(EdofEditor, "_generate_batch")


def test_generate_dialog_image_compression(app):
    """v4.4.0: pdf/edof show the image-compression combo; accept carries the
    (format, quality) pair out; image formats hide it."""
    from edof._apps.batch_panel import _FilenamePatternDialog
    from edof.batch.model import BatchConfig, BatchRow
    cfg = BatchConfig()
    rows = [BatchRow(name="A")]
    dlg = _FilenamePatternDialog(cfg, rows)
    dlg.show(); app.processEvents()
    try:
        dlg._cb_fmt.setCurrentText("png"); app.processEvents()
        assert not dlg._cb_img.isVisible()
        dlg._cb_fmt.setCurrentText("edof"); app.processEvents()
        assert dlg._cb_img.isVisible()
        # pick "JPEG good (75 %)"
        for i in range(dlg._cb_img.count()):
            if dlg._cb_img.itemData(i) == ("jpeg", 75):
                dlg._cb_img.setCurrentIndex(i); break
        dlg.out_dir = "/tmp"; dlg._accept()
        assert dlg.image_format == "jpeg" and dlg.image_quality == 75
    finally:
        dlg.deleteLater(); app.processEvents()


def test_editor_has_save_optimized_slot():
    from edof._apps.editor import EdofEditor, _IMAGE_COMPRESS_CHOICES
    assert hasattr(EdofEditor, "_save_optimized")
    assert _IMAGE_COMPRESS_CHOICES[0][1][0] is None
    assert all(d[0] == "jpeg" for _l, d in _IMAGE_COMPRESS_CHOICES[1:])


def test_unique_column_names_model_level():
    """v4.4.0: BatchConfig.add_column never creates two columns with the same
    header; custom duplicates get _2 suffixes, unnamed collisions get a
    systematic name."""
    from edof.batch.model import BatchConfig, ObjectRef
    cfg = BatchConfig()
    ref = ObjectRef(["x"])
    c1 = cfg.add_column(ref, "run.text", "Name", "text")
    c2 = cfg.add_column(ref, "run.text", "Name", "text")
    c3 = cfg.add_column(ref, "run.text", "name", "text")   # case-insensitive
    assert c1.header() == "Name"
    assert c2.header() == "Name_2"
    assert c3.header() == "name_3"
    # unnamed columns: second collides on the attr-path fallback
    c4 = cfg.add_column(ref, "text", "", "text")
    c5 = cfg.add_column(ref, "text", "", "text")
    assert c4.header() == "text"
    assert c5.header() != "text"
    heads = [c.header().lower() for c in cfg.columns]
    assert len(heads) == len(set(heads))
    assert not cfg.duplicate_name_counts()


_KEEP_ALIVE_440 = []      # guards Qt objects from GC between these tests


def test_rename_run_variable_avoids_collision(tpl_ctx):
    """v4.4.0: renaming a variable to a name owned by ANOTHER column
    auto-suffixes instead of duplicating."""
    doc, page, tb, sh, cv, tpl = tpl_ctx
    _KEEP_ALIVE_440.append(tpl_ctx)
    from edof.format.styles import TextRun
    from edof.batch.model import build_ref
    tb.runs = [TextRun(text="Ahoj", rid="rA", var_name="varA")]
    cfg = doc.batch
    ca = cfg.add_column(build_ref(page, tb), "run.text", "varA", "text")
    ca.run_id = "rA"
    cb = cfg.add_column(build_ref(page, sh), "fill.color", "Taken", "color")
    tpl.rename_run_variable([(tb, "rA")], "Taken")
    assert ca.header() == "Taken_2"
    assert tb.runs[0].var_name == "Taken_2"
    assert cb.header() == "Taken"
