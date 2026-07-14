"""Tests for the 3D Batch data model + .edof persistence (edof.batch.model)."""
import tempfile, os
import pytest
from edof import Document
from edof.format.serializer import EdofSerializer
from edof.batch.model import (BatchConfig, BatchColumn, BatchRow, ObjectRef,
                              build_ref, resolve_ref, find_ref_on_pages,
                              apply_row_to_document)


def _doc():
    d = Document()
    return d, d.add_page(width=100, height=60)


# ── object refs ──────────────────────────────────────────────────────────────
def test_build_and_resolve_toplevel_ref():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    ref = build_ref(pg, tb)
    assert ref is not None
    assert len(ref.path) == 1
    assert resolve_ref(pg, ref) is tb


def test_build_ref_into_group():
    d, pg = _doc()
    g = pg.add_group()
    inner = pg.add_textbox(0, 0, 30, 15, "inner")
    g.add(inner)
    pg.objects = [o for o in pg.objects if o.id != inner.id]   # now only in group
    ref = build_ref(pg, inner)
    assert ref is not None and len(ref.path) == 2
    assert resolve_ref(pg, ref) is inner


def test_resolve_missing_ref_returns_none():
    d, pg = _doc()
    assert resolve_ref(pg, ObjectRef(["nonexistent"])) is None
    assert resolve_ref(pg, ObjectRef([])) is None


def test_find_ref_on_pages():
    d = Document()
    p1 = d.add_page(width=100, height=60)
    p2 = d.add_page(width=100, height=60)
    t2 = p2.add_textbox(0, 0, 30, 15, "x")
    ref = build_ref(p2, t2)
    assert find_ref_on_pages([p1, p2], ref) == 1


# ── columns / rows ───────────────────────────────────────────────────────────
def test_add_remove_column():
    d, pg = _doc()
    tb = pg.add_textbox(0, 0, 30, 15, "x")
    cfg = BatchConfig()
    col = cfg.add_column(build_ref(pg, tb), "text", "Name", "text")
    assert len(cfg.columns) == 1
    assert cfg.column(col.column_id) is col
    assert cfg.remove_column(col.column_id) is True
    assert cfg.columns == []


def test_remove_column_also_clears_row_values():
    d, pg = _doc()
    tb = pg.add_textbox(0, 0, 30, 15, "x")
    cfg = BatchConfig()
    col = cfg.add_column(build_ref(pg, tb), "text", "Name", "text")
    cfg.rows.append(BatchRow(page_target=0, values={col.column_id: "v"}))
    cfg.remove_column(col.column_id)
    assert cfg.rows[0].values == {}


def test_header_falls_back_to_attr_path():
    col = BatchColumn("c1", ObjectRef(["x"]), "text", var_name="")
    assert col.header() == "text"
    col.var_name = "Příjmení"
    assert col.header() == "Příjmení"


def test_duplicate_name_counts():
    d, pg = _doc()
    a = pg.add_textbox(0, 0, 30, 15, "a")
    b = pg.add_textbox(40, 0, 30, 15, "b")
    cfg = BatchConfig()
    c1 = cfg.add_column(build_ref(pg, a), "text", "Name", "text")
    c2 = cfg.add_column(build_ref(pg, b), "text", "Name", "text")
    # v4.4.0: duplicates are impossible now, the second column is suffixed
    # at creation, so the duplicate counter stays empty by construction
    assert (c1.header(), c2.header()) == ("Name", "Name_2")
    assert cfg.duplicate_name_counts() == {}
    # forcing a duplicate behind the API's back is still detected
    c2.var_name = "Name"
    assert cfg.duplicate_name_counts() == {"Name": 2}


# ── applying rows ────────────────────────────────────────────────────────────
def test_apply_row_page_scope():
    d, pg = _doc()
    tb = pg.add_textbox(0, 0, 40, 15, "orig")
    cfg = d.batch
    col = cfg.add_column(build_ref(pg, tb), "text", "Name", "text")
    row = BatchRow(page_target=0, values={col.column_id: "Karel"})
    assert apply_row_to_document(cfg, d, row) == 1
    assert tb.text == "Karel"


def test_page_scope_skips_other_pages_objects():
    d = Document()
    pa = d.add_page(width=100, height=60)
    pb = d.add_page(width=100, height=60)
    ta = pa.add_textbox(0, 0, 40, 15, "aa")
    tb = pb.add_textbox(0, 0, 40, 15, "bb")
    cfg = d.batch
    ca = cfg.add_column(build_ref(pa, ta), "text", "A", "text")
    cb = cfg.add_column(build_ref(pb, tb), "text", "B", "text")
    row = BatchRow(page_target=0,
                   values={ca.column_id: "AA2", cb.column_id: "BB2"})
    assert apply_row_to_document(cfg, d, row) == 1   # only the page-0 column
    assert ta.text == "AA2"
    assert tb.text == "bb"                            # untouched


def test_apply_row_document_scope():
    d = Document()
    p1 = d.add_page(width=100, height=60)
    p2 = d.add_page(width=100, height=60)
    t1 = p1.add_textbox(0, 0, 40, 15, "a")
    t2 = p2.add_textbox(0, 0, 40, 15, "b")
    cfg = d.batch
    cfg.row_scope = "document"
    c1 = cfg.add_column(build_ref(p1, t1), "text", "T1", "text")
    c2 = cfg.add_column(build_ref(p2, t2), "text", "T2", "text")
    row = BatchRow(values={c1.column_id: "X", c2.column_id: "Y"})
    assert apply_row_to_document(cfg, d, row) == 2
    assert t1.text == "X" and t2.text == "Y"


def test_empty_cell_does_not_apply():
    d, pg = _doc()
    tb = pg.add_textbox(0, 0, 40, 15, "keep")
    cfg = d.batch
    col = cfg.add_column(build_ref(pg, tb), "text", "Name", "text")
    row = BatchRow(page_target=0, values={col.column_id: ""})
    assert apply_row_to_document(cfg, d, row) == 0
    assert tb.text == "keep"


# ── pruning / orphans ────────────────────────────────────────────────────────
def test_prune_dead_columns():
    d, pg = _doc()
    x = pg.add_textbox(0, 0, 30, 15, "x")
    cfg = d.batch
    cfg.add_column(build_ref(pg, x), "text", "X", "text")
    pg.objects = []                       # delete the object
    removed = cfg.prune_dead_columns(d.pages)
    assert len(removed) == 1
    assert cfg.columns == []


def test_orphan_columns_not_removed():
    d, pg = _doc()
    x = pg.add_textbox(0, 0, 30, 15, "x")
    cfg = d.batch
    cfg.add_column(build_ref(pg, x), "text", "X", "text")
    pg.objects = []
    orphans = cfg.orphan_columns(d.pages)
    assert len(orphans) == 1
    assert len(cfg.columns) == 1          # still present, just flagged


# ── serialization / persistence ──────────────────────────────────────────────
def test_config_roundtrip_dict():
    cfg = BatchConfig(row_scope="document", export_demo=True)
    cfg.columns.append(BatchColumn("c1", ObjectRef(["a", "b"]), "fill.color",
                                   "Colour", "color"))
    cfg.rows.append(BatchRow(page_target=2, values={"c1": "#ff0000"}))
    cfg.demo_rows.append(BatchRow(values={"c1": "#00ff00"}))
    cfg2 = BatchConfig.from_dict(cfg.to_dict())
    assert cfg2.row_scope == "document"
    assert cfg2.export_demo is True
    assert cfg2.columns[0].target.to_list() == ["a", "b"]
    assert cfg2.columns[0].attr_path == "fill.color"
    assert cfg2.rows[0].page_target == 2
    assert cfg2.rows[0].values == {"c1": "#ff0000"}
    assert cfg2.demo_rows[0].values == {"c1": "#00ff00"}


def test_empty_config_not_serialized_in_document():
    d, pg = _doc()
    assert d.to_dict().get("batch") is None
    _ = d.batch                            # touch but leave empty
    assert d.to_dict().get("batch") is None


def test_document_edof_roundtrip_with_batch():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "orig")
    sh = pg.add_shape("rect", 50, 10, 30, 20)
    cfg = d.batch
    c1 = cfg.add_column(build_ref(pg, tb), "text", "Name", "text")
    c2 = cfg.add_column(build_ref(pg, sh), "fill.color", "Colour", "color")
    cfg.rows.append(BatchRow(page_target=0,
                             values={c1.column_id: "Karel",
                                     c2.column_id: "#00ff00"}))
    f = tempfile.mktemp(suffix=".edof")
    try:
        EdofSerializer().save(d, f)
        d2 = EdofSerializer().load(f)
    finally:
        os.unlink(f)
    b2 = d2.batch
    assert len(b2.columns) == 2
    assert len(b2.rows) == 1
    assert b2.columns[0].header() == "Name"
    # refs still resolve on the loaded document
    assert resolve_ref(d2.pages[0], b2.columns[0].target) is not None


def test_old_document_without_batch_key_loads():
    d, pg = _doc()
    dd = d.to_dict()
    dd.pop("batch", None)                  # simulate a pre-4.3.2.0 file
    d2 = Document.from_dict(dd)
    assert d2._batch is None
    assert d2.batch.is_empty()             # property still works


def test_column_multi_target_applies_to_all():
    """v4.3.5.13: one column can drive several objects (extra_targets)."""
    import copy
    from edof import Document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=120, height=50)
    tb1 = p.add_textbox(5, 5, 50, 15, "A")
    tb2 = p.add_textbox(60, 5, 50, 15, "B")
    col = doc.batch.add_column(build_ref(p, tb1), "text", "Text", "text")
    col.extra_targets = [build_ref(p, tb2)]
    row = BatchRow(page_target=0, values={col.column_id: "SHARED"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    assert d2.pages[0].objects[0].text == "SHARED"
    assert d2.pages[0].objects[1].text == "SHARED"


def test_column_multi_target_serialization():
    import copy
    from edof import Document
    from edof.batch.model import build_ref, BatchColumn
    from edof.format.serializer import EdofSerializer
    doc = Document()
    p = doc.add_page(width=120, height=50)
    tb1 = p.add_textbox(5, 5, 50, 15, "A")
    tb2 = p.add_textbox(60, 5, 50, 15, "B")
    col = doc.batch.add_column(build_ref(p, tb1), "text", "T", "text")
    col.extra_targets = [build_ref(p, tb2)]
    d2 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(doc))
    c2 = d2.batch.columns[0]
    assert len(c2.extra_targets) == 1
    assert len(c2.all_targets()) == 2


# ── v4.3.5.59: legacy variables migrate into the 3D Batch ───────────────────
def test_variable_binding_migrates_to_batch():
    from edof import Document
    from edof.batch.model import migrate_variables_to_batch
    doc = Document()
    p = doc.add_page(width=100, height=100)
    doc.define_variable("name", type="text"); doc.set_variable("name", "Alice")
    tb = p.add_textbox(10, 10, 40, 20, "x"); tb.variable = "name"
    n = migrate_variables_to_batch(doc)
    assert n == 1
    assert tb.variable is None                      # binding cleared
    assert len(doc.batch.columns) == 1
    col = doc.batch.columns[0]
    assert col.header() == "name" and col.attr_path == "text"
    assert len(doc.batch.rows) == 1
    assert doc.batch.rows[0].values[col.column_id] == "Alice"


def test_variable_migration_is_idempotent():
    from edof import Document
    from edof.batch.model import migrate_variables_to_batch
    doc = Document()
    p = doc.add_page(width=100, height=100)
    doc.define_variable("v", type="text"); doc.set_variable("v", "x")
    tb = p.add_textbox(10, 10, 40, 20, "x"); tb.variable = "v"
    assert migrate_variables_to_batch(doc) == 1
    # second run does nothing and doesn't duplicate the column
    assert migrate_variables_to_batch(doc) == 0
    assert len(doc.batch.columns) == 1


def test_variable_migration_on_load():
    """Saving with a variable binding and re-loading migrates transparently."""
    from edof import Document
    import tempfile, os
    doc = Document()
    p = doc.add_page(width=100, height=100)
    doc.define_variable("name", type="text"); doc.set_variable("name", "Karel")
    tb = p.add_textbox(10, 10, 40, 20, "x"); tb.variable = "name"
    f = tempfile.mktemp(suffix=".edof")
    try:
        doc.save(f)
        d2 = Document.load(f)
        assert d2.pages[0].objects[0].variable is None
        assert len(d2.batch.columns) == 1
        assert d2.batch.columns[0].header() == "name"
    finally:
        os.remove(f)


def test_migration_no_variables_leaves_batch_absent():
    """A file with no variable bindings doesn't get a batch created by migration."""
    from edof import Document
    from edof.batch.model import migrate_variables_to_batch
    doc = Document()
    p = doc.add_page(width=100, height=100)
    p.add_textbox(10, 10, 40, 20, "plain")
    assert migrate_variables_to_batch(doc) == 0
    assert doc._batch is None                       # not lazily created
