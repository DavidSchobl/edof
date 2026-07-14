"""Tests for the 3D Batch attribute registry (edof.batch)."""
import pytest
from edof import Document
from edof.batch import (describe_object, describe_type, find_descriptor,
                        apply_value, AttrDescriptor,
                        PRIO_CONTENT, PRIO_GEOMETRY, PRIO_STYLE)


def _doc():
    d = Document()
    return d, d.add_page(width=100, height=60)


def test_textbox_has_content_and_transform():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    paths = {x.path for x in describe_object(tb)}
    assert "text" in paths
    assert "transform.width" in paths
    assert "style.color" in paths
    assert "style.alignment" in paths


def test_content_sorts_before_geometry_and_style():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    descs = describe_object(tb)
    # the master 'All effects' switch sorts first now (PRIO_MASTER is the lowest
    # priority value); content (text) is the first non-master descriptor.
    non_master = [x for x in descs if x.path != "effects.all_enabled"]
    assert non_master[0].path == "text"
    assert non_master[0].priority == PRIO_CONTENT
    prios = [x.priority for x in descs]
    assert prios == sorted(prios)


def test_apply_text():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    assert apply_value(tb, "text", "Karel") is True
    assert tb.text == "Karel"


def test_apply_number_accepts_comma_decimal():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    assert apply_value(tb, "transform.width", "95,5") is True
    assert tb.transform.width == 95.5


def test_apply_color_hex_and_csv():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    assert apply_value(tb, "style.color", "#ff0000") is True
    assert tb.style.color == (255, 0, 0)
    assert apply_value(tb, "style.color", "0,128,255") is True
    assert tb.style.color == (0, 128, 255)


def test_apply_color_rgba_hex():
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 30, 20)
    assert apply_value(sh, "fill.color", "#01020304") is True
    assert sh.fill.color == (1, 2, 3, 4)


def test_apply_enum_case_insensitive():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    assert apply_value(tb, "style.alignment", "CENTER") is True
    assert tb.style.alignment == "center"


def test_enum_rejects_unknown_value():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    assert apply_value(tb, "style.alignment", "diagonal") is False
    assert tb.style.alignment == "left"   # unchanged


def test_empty_cell_does_not_overwrite():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "keep")
    assert apply_value(tb, "text", "") is True      # success...
    assert tb.text == "keep"                         # ...but unchanged
    assert apply_value(tb, "text", "   ") is True
    assert tb.text == "keep"


def test_unknown_path_returns_false():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    assert apply_value(tb, "no.such.attr", "x") is False


def test_bad_number_returns_false_and_keeps_value():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    before = tb.transform.width
    assert apply_value(tb, "transform.width", "not a number") is False
    assert tb.transform.width == before


def test_descriptor_get_reads_current_value():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "Hi")
    desc = find_descriptor(tb, "transform.width")
    assert desc.get(tb) == 40.0


def test_describe_type_without_instance():
    descs = describe_type("imagebox")
    paths = {x.path for x in descs}
    assert "resource_id" in paths
    assert "fit_mode" in paths
    fit = [x for x in descs if x.path == "fit_mode"][0]
    assert fit.kind == "enum"
    assert "contain" in fit.choices


def test_shape_set_changes_render():
    import numpy as np
    from edof.engine.renderer import render_page
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 30, 20)
    assert apply_value(sh, "fill.color", "#00ff00") is True
    arr = np.asarray(render_page(pg, d.resources, d.variables, dpi=80))
    reg = arr[40:90, 30:130]
    green = (reg[..., 1].astype(int) - reg[..., 0] > 80) & \
            (reg[..., 1].astype(int) - reg[..., 2] > 80)
    assert int(green.sum()) > 0


def test_all_object_types_describe_without_error():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    sh = pg.add_shape("rect", 10, 10, 30, 20)
    for obj in (tb, sh):
        for desc in describe_object(obj):
            assert isinstance(desc, AttrDescriptor)
            assert desc.kind in ("text", "number", "color", "enum", "file_path")
            desc.get(obj)   # must not raise


def test_rect_has_corner_radius_but_ellipse_does_not():
    d, pg = _doc()
    rect = pg.add_shape("rect", 0, 0, 30, 20)
    ell = pg.add_shape("ellipse", 40, 0, 30, 20)
    line = pg.add_shape("line", 0, 30, 30, 5)
    assert "corner_radius" in {x.path for x in describe_object(rect)}
    assert "corner_radius" not in {x.path for x in describe_object(ell)}
    assert "corner_radius" not in {x.path for x in describe_object(line)}


def test_effects_not_offered_without_effect():
    # v4.3.5.12: the master 'effects.all_enabled' switch IS always offered, but
    # no per-effect field (effects.<type>.<field>) is offered without the effect
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    paths = {x.path for x in describe_object(tb)}
    assert "effects.all_enabled" in paths
    per_effect = [p for p in paths
                  if p.startswith("effects.") and p != "effects.all_enabled"]
    assert per_effect == []


def test_effect_attributes_offered_when_present():
    from edof import LayerEffect
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    tb.effects.append(LayerEffect(type="drop_shadow", size=3.0, distance=2.0))
    paths = {x.path for x in describe_object(tb)}
    assert "effects.drop_shadow.distance" in paths
    assert "effects.drop_shadow.color" in paths
    assert "effects.drop_shadow.enabled" in paths


def test_apply_effect_field():
    from edof import LayerEffect
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    tb.effects.append(LayerEffect(type="drop_shadow", size=3.0, distance=2.0))
    assert apply_value(tb, "effects.drop_shadow.distance", "7") is True
    assert tb.effects[0].distance == 7.0
    assert apply_value(tb, "effects.drop_shadow.color", "#ff0000") is True
    assert tb.effects[0].color == (255, 0, 0)
    assert apply_value(tb, "effects.drop_shadow.enabled", "false") is True
    assert tb.effects[0].enabled is False


def test_apply_halftone_pattern_field():
    from edof import LayerEffect
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    tb.effects.append(LayerEffect(type="halftone", ht_dot=1.5,
                                  ht_pattern_mode="single", ht_patterns=["a"]))
    assert apply_value(tb, "effects.halftone.ht_dot", "2.5") is True
    assert tb.effects[0].ht_dot == 2.5
    assert apply_value(tb, "effects.halftone.ht_shape", "square") is True
    assert tb.effects[0].ht_shape == "square"


def test_visible_batchable_locked_not():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    paths = {x.path for x in describe_object(tb)}
    assert "visible" in paths
    assert "locked" not in paths
    assert apply_value(tb, "visible", "false") is True
    assert tb.visible is False


def test_ca_black_object_produces_colour_fringes():
    """Regression: chromatic aberration on a pure-black object must split into
    colour fringes, not render a flat black blob."""
    import numpy as np
    from edof import LayerEffect
    from edof.engine.renderer import render_page
    d, pg = _doc()
    sh = pg.add_shape("rect", 25, 18, 30, 14)
    sh.fill.color = (0, 0, 0)
    sh.effects_enabled = True            # master on (default is now off)
    sh.effects.append(LayerEffect(type="chromatic_aberration", ca_offset=2.0,
                                  ca_r_offset=2.0, ca_b_offset=2.0,
                                  ca_r_angle=0, ca_b_angle=180))
    a = np.asarray(render_page(pg, d.resources, d.variables, dpi=100).convert("RGB"))
    r = a[..., 0].astype(int); g = a[..., 1].astype(int); b = a[..., 2].astype(int)
    colorful = (np.abs(r - g) > 40) | (np.abs(r - b) > 40) | (np.abs(g - b) > 40)
    assert int(colorful.sum()) > 100      # real colour fringes exist


def test_path_a_creates_effect_when_missing():
    """Applying an effect field to an object without that effect creates it,
    disabled by default (Path A)."""
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    assert len(tb.effects) == 0
    assert apply_value(tb, "effects.drop_shadow.distance", "5") is True
    assert len(tb.effects) == 1
    assert tb.effects[0].type == "drop_shadow"
    assert tb.effects[0].enabled is False     # default off
    assert tb.effects[0].distance == 5.0
    # enabling works
    assert apply_value(tb, "effects.drop_shadow.enabled", "true") is True
    assert tb.effects[0].enabled is True


def test_all_effect_descriptors_cover_every_type():
    from edof.batch import all_effect_descriptors, effect_types
    descs = all_effect_descriptors()
    types_in = {d.path.split(".")[1] for d in descs}
    assert types_in == set(effect_types())
    assert len(effect_types()) == 13


def test_find_descriptor_synthesizes_effect_path():
    from edof.batch import find_descriptor
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    # no halftone on the object, but the descriptor is still resolvable
    desc = find_descriptor(tb, "effects.halftone.ht_dot")
    assert desc is not None
    assert desc.kind == "number"


def test_path_a_effect_uses_ui_defaults_not_dataclass():
    """Regression: an effect created via Path A must use the same defaults as
    the 'add effect' UI (e.g. drop shadow direction 315, not the dataclass 135
    which points the opposite way)."""
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    assert apply_value(tb, "effects.drop_shadow.enabled", "true") is True
    e = tb.effects[0]
    assert e.direction == 315.0           # not the dataclass default of 135
    assert e.color == (0, 0, 0, 220)
    assert e.blend_mode == "multiply"


def test_make_default_effect_matches_for_all_types():
    from edof.batch import make_default_effect, effect_types
    for et in effect_types():
        e = make_default_effect(et)
        assert e is not None
        assert e.type == et
        assert e.enabled is False         # Path A default: off until enabled


def test_textbox_has_autofit_and_style_attrs():
    """v4.3.5.13: the text style attributes that were missing from batch."""
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    paths = {x.path for x in describe_object(tb)}
    for p in ("style.bold", "style.italic", "style.underline",
              "style.strikethrough", "style.line_height", "style.letter_spacing",
              "style.auto_shrink", "style.auto_fill", "style.min_font_size",
              "style.max_font_size", "style.wrap", "style.padding"):
        assert p in paths, p


def test_textbox_new_attrs_apply():
    d, pg = _doc()
    tb = pg.add_textbox(10, 10, 40, 15, "x")
    assert apply_value(tb, "style.bold", "true") is True
    assert tb.style.bold is True
    assert apply_value(tb, "style.auto_shrink", "true") is True
    assert tb.style.auto_shrink is True
    assert apply_value(tb, "style.line_height", "1.5") is True
    assert abs(tb.style.line_height - 1.5) < 1e-6


# ── v4.3.5.16: seed value + multiple effects of the same type ────────────────
def test_effect_enabled_get_is_false_when_effect_absent():
    """Seed bug: enabled descriptor must return a concrete 'false' (not None)
    when the object has no such effect, so a seeded cell isn't a misleading
    empty that shows the first enum choice."""
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    desc = find_descriptor(sh, "effects.drop_shadow.enabled")
    assert desc.get(sh) == "false"


def test_effect_enabled_get_reflects_template_when_present():
    from edof import LayerEffect
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True))
    desc = find_descriptor(sh, "effects.drop_shadow.enabled")
    assert desc.get(sh) == "true"


def test_multiple_same_type_effects_have_ordinal_paths():
    from edof import LayerEffect
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True, distance=2))
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True, distance=8))
    paths = {x.path for x in describe_object(sh)}
    assert "effects.drop_shadow.enabled" in paths
    assert "effects.drop_shadow#2.enabled" in paths
    assert "effects.drop_shadow.distance" in paths
    assert "effects.drop_shadow#2.distance" in paths


def test_ordinal_descriptor_targets_correct_instance():
    from edof import LayerEffect
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True, distance=2))
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True, distance=8))
    assert find_descriptor(sh, "effects.drop_shadow.distance").get(sh) == 2
    assert find_descriptor(sh, "effects.drop_shadow#2.distance").get(sh) == 8


def test_ordinal_batch_applies_independently():
    import copy
    from edof import Document, LayerEffect
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 25, 18, 30, 14)
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True, distance=2))
    sh.effects.append(LayerEffect(type="drop_shadow", enabled=True, distance=8))
    sh.effects_enabled = True
    col = doc.batch.add_column(build_ref(p, sh), "effects.drop_shadow#2.enabled", "S2", "enum")
    row = BatchRow(page_target=0, values={col.column_id: "false"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    o = d2.pages[0].objects[0]
    assert o.effects[0].enabled is True     # first untouched
    assert o.effects[1].enabled is False    # second toggled off


def test_ordinal_path_a_pads_instances():
    """v4.3.5.17: setting a #2 path on an object that lacks the 2nd instance
    pads with default instances up to that ordinal (you can't have a 2nd effect
    without a 1st), so a recorded 2nd effect can be toggled back on. Reading
    (get) must NOT fabricate anything."""
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    desc = find_descriptor(sh, "effects.drop_shadow#2.enabled")
    # reading does not create
    assert desc.get(sh) == "false"
    assert len(sh.effects) == 0
    # setting pads up to the 2nd instance and enables it
    ok = desc.set(sh, "true")
    assert ok is True
    assert len(sh.effects) == 2
    assert sh.effects[1].enabled is True


def test_master_off_overrides_path_a_enabled():
    """all_enabled=false must win over a same-row effect.enabled=true that
    creates the effect via Path A (the master applies last, lowest priority)."""
    import copy
    from edof import Document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    from edof.engine.renderer import render_page
    import numpy as np
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 25, 18, 30, 14)
    sh.fill.color = (0, 0, 0)
    base = int((np.asarray(render_page(p, doc.resources, doc.variables, dpi=100)
                           .convert("RGB")).sum(axis=2) < 600).sum())
    c_all = doc.batch.add_column(build_ref(p, sh), "effects.all_enabled", "All", "enum")
    c_sh = doc.batch.add_column(build_ref(p, sh), "effects.drop_shadow.enabled", "Sh", "enum")
    row = BatchRow(page_target=0, values={c_all.column_id: "false", c_sh.column_id: "true"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    o = d2.pages[0].objects[0]
    assert o.effects_enabled is False           # master wins
    px = int((np.asarray(render_page(d2.pages[0], d2.resources, d2.variables, dpi=100)
                         .convert("RGB")).sum(axis=2) < 600).sum())
    assert px == base                           # shadow hidden by master


def test_path_a_does_not_touch_master_when_object_has_effects():
    """v4.3.5.28: enabling an effect via the registry does NOT force the master
    on (the master is explicit). An explicit effects.all_enabled in the same row
    controls the master and applies last."""
    import copy
    from edof import LayerEffect
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    sh.effects.append(LayerEffect(type="glow", enabled=True))
    sh.effects_enabled = False
    desc = find_descriptor(sh, "effects.drop_shadow.enabled")
    desc.set(sh, "true")
    assert sh.effects_enabled is False     # master left alone
    # an explicit all_enabled drives the master
    d2, pg2 = _doc()
    sh2 = pg2.add_shape("rect", 10, 10, 40, 30)
    sh2.effects.append(LayerEffect(type="drop_shadow", enabled=False))
    sh2.effects_enabled = False
    c_en = d2.batch.add_column(build_ref(pg2, sh2),
                               "effects.drop_shadow.enabled", "E", "enum")
    c_all = d2.batch.add_column(build_ref(pg2, sh2),
                                "effects.all_enabled", "M", "enum")
    row = BatchRow(page_target=0, values={c_en.column_id: "true",
                                          c_all.column_id: "true"})
    dd = copy.deepcopy(d2)
    apply_row_to_document(dd.batch, dd, row)
    o = dd.pages[0].objects[0]
    assert o.effects[0].enabled is True
    assert o.effects_enabled is True       # all_enabled=true drives master


# ── v4.3.5.20: halftone pattern by file path ─────────────────────────────────
def test_halftone_pattern_path_loads_file(tmp_path):
    from PIL import Image
    pat = tmp_path / "pat.png"
    Image.new("RGBA", (16, 16), (0, 128, 255, 255)).save(pat)
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    desc = find_descriptor(sh, "effects.halftone.ht_pattern_path")
    assert desc is not None
    assert desc.kind == "file_path"
    assert desc.set(sh, str(pat)) is True
    e = [x for x in sh.effects if x.type == "halftone"][0]
    assert e.ht_pattern_paths and e.ht_pattern_paths[0] == str(pat)
    assert e.ht_patterns and e.ht_patterns[0]      # base64 loaded
    assert desc.get(sh) == str(pat)                # path is readable back


def test_halftone_pattern_path_bad_file_fails():
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    desc = find_descriptor(sh, "effects.halftone.ht_pattern_path")
    assert desc.set(sh, "/no/such/file.png") is False


def test_halftone_raw_patterns_not_batchable():
    """The base64 cache must not be a batchable field anymore."""
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    from edof import LayerEffect
    sh.effects.append(LayerEffect(type="halftone"))
    paths = {x.path for x in describe_object(sh)}
    assert "effects.halftone.ht_patterns" not in paths
    # but mode and the pattern-file path are
    assert "effects.halftone.ht_pattern_mode" in paths
    assert "effects.halftone.ht_pattern_path" in paths


def test_halftone_pattern_paths_serialize():
    from edof import Document, LayerEffect
    from edof.format.serializer import EdofSerializer
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    e = LayerEffect(type="halftone")
    e.ht_pattern_paths = ["/a/b.png", "/c/d.png"]
    sh.effects.append(e)
    d2 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(doc))
    e2 = d2.pages[0].objects[0].effects[0]
    assert e2.ht_pattern_paths == ["/a/b.png", "/c/d.png"]


# ── v4.3.5.21: stable effect identity (eid) ──────────────────────────────────
def test_effects_get_stable_eid():
    from edof import LayerEffect
    e1 = LayerEffect(type="drop_shadow")
    e2 = LayerEffect(type="drop_shadow")
    assert e1.eid and e2.eid and e1.eid != e2.eid


def test_eid_survives_serialization():
    from edof import Document, LayerEffect
    from edof.format.serializer import EdofSerializer
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    e = LayerEffect(type="drop_shadow")
    sh.effects.append(e)
    d2 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(doc))
    assert d2.pages[0].objects[0].effects[0].eid == e.eid


def test_effect_id_for_path_resolves_instance():
    from edof import LayerEffect
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    e1 = LayerEffect(type="drop_shadow", distance=2)
    e2 = LayerEffect(type="drop_shadow", distance=8)
    sh.effects = [e1, e2]
    from edof.batch import effect_id_for_path
    assert effect_id_for_path(sh, "effects.drop_shadow.enabled") == e1.eid
    assert effect_id_for_path(sh, "effects.drop_shadow#2.enabled") == e2.eid
    # an instance the object doesn't have -> empty
    assert effect_id_for_path(sh, "effects.drop_shadow#3.enabled") == ""


def test_eid_binding_survives_reorder():
    """A column bound by effect_id stays on the SAME effect after a reorder,
    unlike a positional ordinal path."""
    import copy
    from edof import Document, LayerEffect
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    e1 = LayerEffect(type="drop_shadow", enabled=True, distance=2)
    e2 = LayerEffect(type="drop_shadow", enabled=True, distance=8)
    sh.effects = [e1, e2]
    sh.effects_enabled = True
    col = doc.batch.add_column(build_ref(p, sh),
                               "effects.drop_shadow#2.enabled", "S2", "enum")
    col.effect_id = e2.eid
    row = BatchRow(page_target=0, values={col.column_id: "false"})
    # reorder: e2 now first
    doc.pages[0].objects[0].effects = [e2, e1]
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    o = d2.pages[0].objects[0]
    by_eid = {e.eid: e for e in o.effects}
    assert by_eid[e2.eid].enabled is False     # still the right effect
    assert by_eid[e1.eid].enabled is True


def test_column_effect_id_serializes():
    from edof import Document, LayerEffect
    from edof.format.serializer import EdofSerializer
    from edof.batch.model import build_ref
    doc = Document()
    p = doc.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    e = LayerEffect(type="drop_shadow")
    sh.effects.append(e)
    col = doc.batch.add_column(build_ref(p, sh),
                               "effects.drop_shadow.enabled", "S", "enum")
    col.effect_id = e.eid
    d2 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(doc))
    assert d2.batch.columns[0].effect_id == e.eid


# ── v4.3.5.26: text updates runs, enabling effect turns on master ────────────
def test_text_set_updates_runs():
    """Setting a textbox's text via batch updates the rich-text runs too, so the
    change is actually visible (preserving the first run's formatting)."""
    from edof.format.styles import TextRun
    d, pg = _doc()
    tb = pg.add_textbox(5, 5, 50, 15, "Original")
    tb.runs = [TextRun(text="Original", bold=True, font_size=5.0,
                       font_family="Arial")]
    desc = find_descriptor(tb, "text")
    assert desc.set(tb, "Changed") is True
    assert tb.text == "Changed"
    assert tb.runs and tb.runs[0].text == "Changed"
    assert tb.runs[0].bold is True          # formatting preserved
    assert tb.runs[0].font_size == 5.0
    assert tb.runs[0].font_family == "Arial"


def test_text_set_multiline_runs():
    from edof.format.styles import TextRun
    d, pg = _doc()
    tb = pg.add_textbox(5, 5, 50, 15, "x")
    tb.runs = [TextRun(text="x")]
    find_descriptor(tb, "text").set(tb, "Line1\nLine2")
    texts = [r.text for r in tb.runs]
    assert "Line1" in texts and "Line2" in texts and "\n" in texts


def test_enabling_effect_does_not_touch_master():
    """v4.3.5.28: enabling an effect no longer auto-toggles the master (that
    surprised the user). The master is controlled explicitly only."""
    from edof import LayerEffect
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    sh.effects = [LayerEffect(type="drop_shadow", enabled=False)]
    sh.effects_enabled = False
    find_descriptor(sh, "effects.drop_shadow.enabled").set(sh, "true")
    assert sh.effects[0].enabled is True
    assert sh.effects_enabled is False     # master left alone


def test_disabling_effect_leaves_master():
    """enabled=false doesn't force the master off (other effects may need it)."""
    from edof import LayerEffect
    d, pg = _doc()
    sh = pg.add_shape("rect", 10, 10, 40, 30)
    sh.effects = [LayerEffect(type="drop_shadow", enabled=True)]
    sh.effects_enabled = True
    find_descriptor(sh, "effects.drop_shadow.enabled").set(sh, "false")
    assert sh.effects[0].enabled is False
    assert sh.effects_enabled is True       # left on


# ── v4.3.5.27: multi-target effect fix, justify on runs ──────────────────────
def test_eid_binding_falls_back_for_other_targets():
    """A column bound by eid (primary) applies to other linked objects too,
    falling back to the positional descriptor where the eid doesn't match."""
    import copy
    from edof import Document, LayerEffect
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    from edof.batch import effect_id_for_path
    doc = Document()
    p = doc.add_page(width=120, height=80)
    sh1 = p.add_shape("rect", 10, 10, 40, 30)
    sh2 = p.add_shape("rect", 60, 10, 40, 30)
    sh1.effects = [LayerEffect(type="drop_shadow", enabled=False)]
    sh2.effects = [LayerEffect(type="drop_shadow", enabled=False)]
    col = doc.batch.add_column(build_ref(p, sh1),
                               "effects.drop_shadow.enabled", "S", "enum")
    col.effect_id = effect_id_for_path(sh1, "effects.drop_shadow.enabled")
    col.extra_targets = [build_ref(p, sh2)]
    # master variable on both so the effect renders (master is explicit now)
    cm = doc.batch.add_column(build_ref(p, sh1), "effects.all_enabled", "M", "enum")
    cm.extra_targets = [build_ref(p, sh2)]
    row = BatchRow(page_target=0, values={col.column_id: "true",
                                          cm.column_id: "true"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    o1 = d2.pages[0].objects[0]
    o2 = d2.pages[0].objects[1]
    assert o1.effects[0].enabled is True       # primary (eid match)
    assert o2.effects[0].enabled is True       # other target (positional)
    assert o1.effects_enabled is True
    assert o2.effects_enabled is True


def test_alignment_justify_applies_to_runs():
    from edof.format.styles import TextRun
    d, pg = _doc()
    tb = pg.add_textbox(5, 5, 50, 15, "Text")
    tb.runs = [TextRun(text="Text", alignment="left")]
    desc = find_descriptor(tb, "style.alignment")
    assert "justify" in desc.choices
    assert desc.set(tb, "justify") is True
    assert tb.style.alignment == "justify"
    assert tb.runs[0].alignment == "justify"   # pushed to runs


def test_path_a_does_not_enable_master():
    """v4.3.5.30: creating an effect via Path A on an object with no effects no
    longer turns the master on -- the master is explicit only, so the effect
    stays hidden until an all_enabled variable enables it (consistent with the
    panel's warning)."""
    import copy
    from edof import Document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    sh = p.add_shape("rect", 60, 10, 40, 30)      # no effects
    sh.effects_enabled = False
    col = doc.batch.add_column(build_ref(p, sh),
                               "effects.drop_shadow.enabled", "S", "enum")
    row = BatchRow(page_target=0, values={col.column_id: "true"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    o = d2.pages[0].objects[0]
    assert len(o.effects) == 1                    # effect created (Path A)
    assert o.effects[0].enabled is True
    assert o.effects_enabled is False             # but master NOT auto-enabled


def test_path_a_with_master_variable_shows():
    """With an all_enabled variable set true, the Path A effect renders."""
    import copy
    from edof import Document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    sh = p.add_shape("rect", 60, 10, 40, 30)
    sh.effects_enabled = False
    c_s = doc.batch.add_column(build_ref(p, sh),
                               "effects.drop_shadow.enabled", "S", "enum")
    c_m = doc.batch.add_column(build_ref(p, sh), "effects.all_enabled", "M", "enum")
    row = BatchRow(page_target=0, values={c_s.column_id: "true",
                                          c_m.column_id: "true"})
    d2 = copy.deepcopy(doc)
    apply_row_to_document(d2.batch, d2, row)
    o = d2.pages[0].objects[0]
    assert o.effects_enabled is True
    assert o.effects[0].enabled is True


# ── v4.3.5.34: dimension setters scale shape geometry; QR opacity ────────────
def test_height_scales_line_points():
    """v4.3.5.48: line points are LOCAL (0-based), scaled about (0,0) like a
    path -- so the local endpoint's y doubles when height doubles."""
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [[0, 0], [40, 20]]                            # local
    find_descriptor(ln, "transform.height").set(ln, "40")     # 20 -> 40, sy=2
    assert ln.points[1][1] == 40.0                            # 20 -> 40 about 0
    assert ln.points[0] == [0.0, 0.0]                         # local origin fixed
    assert ln.transform.height == 40.0


def test_height_scales_path_data():
    """v4.3.5.36: path data are LOCAL, scaled about (0,0) like interactive
    resize -- so all y's double when height doubles."""
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    cv = p.add_shape("path", 10, 10, 40, 20)
    cv.path_data = [["M", 0, 0], ["C", 10, 0, 20, 20, 40, 20]]
    find_descriptor(cv, "transform.height").set(cv, "40")     # 20 -> 40, sy=2
    # all y's scale about 0: 0 stays, 20 -> 40
    assert cv.path_data[1] == ["C", 10.0, 0.0, 20.0, 40.0, 40.0, 40.0]


def test_width_scales_path_data():
    """Local path data scale about (0,0) when width changes."""
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    cv = p.add_shape("path", 10, 10, 40, 20)
    cv.path_data = [["M", 0, 10], ["L", 40, 10]]
    find_descriptor(cv, "transform.width").set(cv, "80")      # 40 -> 80, sx=2
    # x at 40 -> 80 (about 0)
    assert cv.path_data[1] == ["L", 80.0, 10.0]


def test_dimension_setter_leaves_rect_alone():
    """A rect has no local geometry, so only its transform changes."""
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    r = p.add_shape("rect", 10, 10, 40, 20)
    assert find_descriptor(r, "transform.height").set(r, "40") is True
    assert r.transform.height == 40.0


def test_qr_opacity_renders():
    """QR opacity used to be ignored entirely; it now scales the QR alpha."""
    import importlib.util
    if importlib.util.find_spec("qrcode") is None:
        import pytest
        pytest.skip("qrcode not installed")
    from edof import Document
    from edof.engine.renderer import _render_qrcode
    from PIL import Image
    import numpy as np
    doc = Document()
    p = doc.add_page(width=60, height=60)
    qr = p.add_qrcode("test", 10, 10, 30, 30)
    out = {}
    for op in (1.0, 0.5):
        qr.opacity = op
        canvas = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        _render_qrcode(qr, canvas, {}, 96)
        a = np.array(canvas)[:, :, 3]
        nz = a[a > 0]
        out[op] = int(nz.max()) if len(nz) else 0
    assert out[1.0] == 255
    assert out[0.5] <= 130                          # ~127


# ── v4.3.5.36: line move/scale, path scale fix, absolute/incremental x/y ─────
def test_height_does_not_vanish_curve():
    """Regression: scaling a curve's height must keep it on-canvas (the previous
    version scaled about transform.x/y, pushing local path data off so it
    vanished)."""
    from edof import Document
    from edof.engine.renderer import _render_shape
    from PIL import Image
    import numpy as np
    doc = Document()
    p = doc.add_page(width=120, height=80)
    cv = p.add_shape("path", 10, 10, 40, 20)
    cv.path_data = [["M", 0, 0], ["L", 20, 20], ["L", 40, 0]]
    cv.stroke.width = 1
    find_descriptor(cv, "transform.height").set(cv, "40")
    canvas = Image.new("RGBA", (600, 400), (0, 0, 0, 0))
    _render_shape(cv, canvas, 96)
    a = np.array(canvas)[:, :, 3]
    assert (a > 0).any()                       # not vanished


def test_x_moves_line_via_transform():
    """v4.3.5.48: line points are LOCAL now (renderer adds the transform), so
    setting x only changes the transform -- points stay local and unchanged."""
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [[0, 0], [40, 20]]
    find_descriptor(ln, "transform.x").set(ln, "40")
    assert ln.transform.x == 40.0
    assert ln.points == [[0, 0], [40, 20]]               # unchanged (local)


def test_y_moves_line_via_transform():
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [[0, 0], [40, 20]]
    find_descriptor(ln, "transform.y").set(ln, "25")
    assert ln.transform.y == 25.0
    assert ln.points == [[0, 0], [40, 20]]               # unchanged (local)


def test_x_offset_incremental():
    """Incremental x adds/subtracts from the current position (negatives allowed).
    v4.3.5.48: a line's local points are unchanged; only the transform shifts."""
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [[0, 0], [40, 20]]
    d = find_descriptor(ln, "transform.x_offset")
    assert d is not None
    d.set(ln, "-5")                                       # move left by 5
    assert ln.transform.x == 5.0
    assert ln.points == [[0, 0], [40, 20]]               # unchanged (local)


def test_y_offset_incremental_on_rect():
    """Incremental y on a plain rect just shifts the transform."""
    from edof import Document
    doc = Document()
    p = doc.add_page(width=120, height=80)
    r = p.add_shape("rect", 10, 10, 40, 20)
    find_descriptor(r, "transform.y_offset").set(r, "7")
    assert r.transform.y == 17.0
    find_descriptor(r, "transform.y_offset").set(r, "-2")
    assert r.transform.y == 15.0


def test_offset_descriptors_exist_in_tree():
    from edof import Document
    from edof.batch import describe_object
    doc = Document()
    p = doc.add_page(width=120, height=80)
    r = p.add_shape("rect", 10, 10, 40, 20)
    paths = {d.path for d in describe_object(r)}
    assert "transform.x_offset" in paths
    assert "transform.y_offset" in paths
    assert "transform.x" in paths              # absolute still there


# ── v4.3.5.48: line points are local (like a path) ───────────────────────────
def test_line_migration_absolute_to_local():
    """Old files stored absolute line points (no _local_points flag) -> load
    subtracts the transform origin so they become local and render the same."""
    from edof.format.objects import Shape
    old = {"type": "shape", "shape_type": "line",
           "transform": {"x": 10, "y": 10, "width": 40, "height": 20},
           "points": [[10, 10], [50, 30]], "stroke": {"width": 1}}
    ln = Shape.from_dict(old)
    assert ln.points == [[0.0, 0.0], [40.0, 20.0]]     # now local
    assert ln.transform.x == 10.0 and ln.transform.y == 10.0


def test_line_local_points_not_remigrated():
    """A file already storing local points (with the flag) is not migrated."""
    from edof.format.objects import Shape
    new = {"type": "shape", "shape_type": "line",
           "transform": {"x": 10, "y": 10, "width": 40, "height": 20},
           "points": [[0, 0], [40, 20]], "_local_points": True,
           "stroke": {"width": 1}}
    ln = Shape.from_dict(new)
    assert ln.points == [[0, 0], [40, 20]]
    assert ln.to_dict().get("_local_points") is True


def test_normalize_line_rebases_box():
    """normalize_line keeps the invariant: transform = bbox of points, points
    re-based to 0, world position preserved."""
    from edof.format.objects import Shape, SHAPE_LINE
    ln = Shape(shape_type=SHAPE_LINE)
    ln.transform.x = 10; ln.transform.y = 10
    ln.points = [[5, 5], [60, 40]]                     # local, off-origin
    ln.normalize_line()
    # world bbox was (15,15)-(70,50)
    assert (ln.transform.x, ln.transform.y) == (15.0, 15.0)
    assert (ln.transform.width, ln.transform.height) == (55.0, 35.0)
    assert ln.points == [[0.0, 0.0], [55.0, 35.0]]


def test_line_render_adds_transform():
    """The renderer places a local line by adding the transform origin (so it
    moves with the transform, like a path)."""
    from edof import Document
    from edof.engine.renderer import _render_shape
    from PIL import Image
    import numpy as np
    doc = Document()
    p = doc.add_page(width=200, height=120)
    ln = p.add_shape("line", 10, 10, 40, 20)
    ln.points = [[0, 0], [40, 20]]
    ln.stroke.width = 1

    def bbox(o):
        c = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        _render_shape(o, c, 96)
        a = np.array(c)[:, :, 3]
        ys, xs = np.where(a > 0)
        f = 25.4 / 96
        return (round(xs.min() * f), round(ys.min() * f),
                round(xs.max() * f), round(ys.max() * f))

    assert bbox(ln) == (10, 10, 50, 30)                # transform + local
    ln.transform.x = 60
    assert bbox(ln) == (60, 10, 100, 30)               # moved with transform


# ── v4.3.5.51: shear (skew) for pre-rotated children in a group/selection ────
def test_transform_shear_serialization():
    from edof.engine.transform import Transform
    t = Transform(x=10, y=10, width=40, height=40, rotation=30, shear_x=-0.5)
    d = t.to_dict()
    assert d.get("shear_x") == -0.5
    assert Transform.from_dict(d).shear_x == -0.5
    # zero shear is not emitted
    assert "shear_x" not in Transform(x=0, y=0).to_dict()


def test_shear_decompose_matches_matrix():
    """The RQ decomposition reproduces diag(sx,sy)*R(theta) on the box corners."""
    import math
    from edof._apps.editor import _shear_decompose
    sx, sy, theta, w0, h0 = 2.0, 1.0, 45.0, 40.0, 40.0
    rot, w, h, shx = _shear_decompose(sx, sy, theta, w0, h0)

    def model(lx, ly):
        px = lx * w; py = ly * h
        px = px + shx * py
        ph = math.radians(rot)
        return (px * math.cos(ph) - py * math.sin(ph),
                px * math.sin(ph) + py * math.cos(ph))

    def truth(lx, ly):
        px = lx * w0; py = ly * h0
        th = math.radians(theta)
        rx = px * math.cos(th) - py * math.sin(th)
        ry = px * math.sin(th) + py * math.cos(th)
        return (sx * rx, sy * ry)

    for lx, ly in [(0.5, 0.5), (-0.5, 0.5), (0.5, -0.5), (-0.5, -0.5)]:
        mx, my = model(lx, ly)
        tx, ty = truth(lx, ly)
        assert abs(mx - tx) < 0.05 and abs(my - ty) < 0.05


def test_shear_renders_parallelogram():
    """A sheared rect renders wider (the skew turns the box into a parallelogram)."""
    from edof import Document
    from edof.engine.renderer import _render_object_dispatch
    from PIL import Image
    import numpy as np
    doc = Document()
    p = doc.add_page(width=200, height=120)
    r = p.add_shape("rect", 40, 40, 40, 40); r.fill.color = (255, 0, 0, 255)

    def width_px(o):
        c = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        _render_object_dispatch(o, c, {}, {}, 96)
        a = np.array(c)[:, :, 3]
        xs = np.where(a.any(axis=0))[0]
        return xs.max() - xs.min()

    w0 = width_px(r)
    r.transform.shear_x = 0.5
    assert width_px(r) > w0 + 30        # widened by the skew


# ── v4.3.5.54: SVG/PDF export applies rotation and shear ─────────────────────
def test_svg_export_applies_rotation():
    """SVG export now wraps a rotated object in a rotation transform (it used to
    ignore rotation entirely)."""
    from edof import Document
    from edof.export.svg import export_svg
    import tempfile, os
    doc = Document()
    p = doc.add_page(width=100, height=100)
    r = p.add_shape("rect", 30, 30, 40, 20)
    r.transform.rotation = 30
    sf = tempfile.mktemp(suffix=".svg")
    try:
        export_svg(doc, sf)
        svg = open(sf).read()
        assert "rotate(30" in svg
        assert "<g transform=" in svg
    finally:
        os.remove(sf)


def test_svg_export_applies_shear():
    """SVG export emits the shear as a matrix transform."""
    from edof import Document
    from edof.export.svg import export_svg
    import tempfile, os
    doc = Document()
    p = doc.add_page(width=100, height=100)
    r = p.add_shape("rect", 30, 30, 40, 20)
    r.transform.shear_x = -0.5
    sf = tempfile.mktemp(suffix=".svg")
    try:
        export_svg(doc, sf)
        svg = open(sf).read()
        assert "matrix(1,0,-0.5,1,0,0)" in svg
    finally:
        os.remove(sf)


def test_svg_no_transform_when_plain():
    """A plain (unrotated, unsheared) object has no transform wrapper."""
    from edof import Document
    from edof.export.svg import export_svg
    import tempfile, os
    doc = Document()
    p = doc.add_page(width=100, height=100)
    p.add_shape("rect", 30, 30, 40, 20)
    sf = tempfile.mktemp(suffix=".svg")
    try:
        export_svg(doc, sf)
        svg = open(sf).read()
        assert "<g transform=" not in svg
    finally:
        os.remove(sf)


def test_pdf_writer_has_shear():
    """The PDF writer exposes shear_at (used by export for sheared objects)."""
    from edof.export.pdf_writer import PdfPage
    assert hasattr(PdfPage, "shear_at")


# ── v4.3.5.55: 3D Batch CSV export/import (clean csv + meta csv) ─────────────
def _mk_cfg():
    from edof.batch.model import BatchConfig, BatchColumn, BatchRow, ObjectRef
    cfg = BatchConfig()
    cfg.columns = [
        BatchColumn(column_id="col_a", target=ObjectRef.from_list([0]),
                    attr_path="text", var_name="Name", kind="text"),
        BatchColumn(column_id="col_b", target=ObjectRef.from_list([1]),
                    attr_path="transform.x", var_name="PosX", kind="number"),
    ]
    cfg.rows = [BatchRow(values={"col_a": "Alice", "col_b": "10"}, name="r1"),
                BatchRow(values={"col_a": "Bob", "col_b": "20"}, name="r2")]
    return cfg


def test_csv_clean_has_no_meta():
    """The clean CSV is just name + headers + values, no meta line."""
    cfg = _mk_cfg()
    clean = cfg.to_csv()
    first = clean.splitlines()[0]
    assert first.startswith("name,")
    assert "#edof-batch" not in clean       # meta is a separate file
    assert "Alice" in clean and "Bob" in clean


def test_csv_meta_maps_headers():
    """The meta CSV maps each header to its column_id."""
    cfg = _mk_cfg()
    meta = cfg.to_meta_csv()
    assert "header,column_id" in meta.splitlines()[0]
    assert "col_a" in meta and "col_b" in meta


def test_csv_roundtrip_with_meta():
    from edof.batch.model import BatchConfig
    cfg = _mk_cfg()
    clean = cfg.to_csv(); meta = cfg.to_meta_csv()
    cfg2 = BatchConfig(); cfg2.columns = cfg.columns
    n = cfg2.update_rows_from_csv(clean, meta=meta)
    assert n == 2
    assert cfg2.rows[0].values == cfg.rows[0].values
    assert cfg2.rows[0].name == "r1"


def test_csv_import_without_meta_matches_by_header():
    cfg = _mk_cfg(); cfg.rows = []
    n = cfg.update_rows_from_csv("name,Name\nKarel,Novak\n")
    assert n == 1
    assert cfg.rows[0].name == "Karel"
    assert cfg.rows[0].values["col_a"] == "Novak"


def test_csv_import_autodetects_cp1250():
    cfg = _mk_cfg(); cfg.rows = []
    data = "name,Name\n\u017dlu\u0165ou\u010dk\u00fd,test\n".encode("cp1250")
    n = cfg.update_rows_from_csv(data)
    assert n == 1
    assert cfg.rows[0].name == "\u017dlu\u0165ou\u010dk\u00fd"


def test_csv_import_strips_bom():
    cfg = _mk_cfg(); cfg.rows = []
    data = "\ufeffname,Name\nTest,Val\n".encode("utf-8")
    n = cfg.update_rows_from_csv(data)
    assert n == 1 and cfg.rows[0].name == "Test"


def test_csv_import_ignores_unknown_columns():
    cfg = _mk_cfg(); cfg.rows = []
    cfg.update_rows_from_csv("name,Name,Bogus\nA,B,C\n")
    assert cfg.rows[0].values == {"col_a": "B"}     # Bogus dropped


# ── v4.3.5.57: export filename token templates ──────────────────────────────
def _fn_cfg():
    from edof.batch.model import BatchConfig, BatchColumn, ObjectRef
    cfg = BatchConfig()
    cfg.columns = [
        BatchColumn(column_id="c1", target=ObjectRef.from_list([0]),
                    attr_path="text", var_name="Name", kind="text"),
        BatchColumn(column_id="c2", target=ObjectRef.from_list([1]),
                    attr_path="text", var_name="City", kind="text"),
    ]
    return cfg


def test_filename_basic_tokens():
    from edof.batch.model import render_filename, BatchRow
    cfg = _fn_cfg()
    row = BatchRow(values={"c1": "Alice", "c2": "Brno"}, name="card")
    assert render_filename("[ROW_NUMBER]_[ROW_NAME]-[{Name}]", 7, row, cfg) == \
        "7_card-Alice.png"


def test_filename_padding_and_ext():
    from edof.batch.model import render_filename, BatchRow
    cfg = _fn_cfg()
    row = BatchRow(values={"c1": "Alice", "c2": "Brno"}, name="card")
    assert render_filename("[ROW_NUMBER:04]_[{Name}].pdf", 7, row, cfg) == \
        "0007_Alice.pdf"


def test_filename_case_modifiers():
    from edof.batch.model import render_filename, BatchRow
    cfg = _fn_cfg()
    row = BatchRow(values={"c1": "Alice", "c2": "Brno"}, name="card")
    assert render_filename("[{Name:upper}]-[{City:lower}]", 1, row, cfg) == \
        "ALICE-brno.png"


def test_filename_sanitizes_path_chars():
    from edof.batch.model import render_filename, BatchRow
    cfg = _fn_cfg()
    row = BatchRow(values={"c1": "A/B", "c2": "C:D"}, name="x")
    out = render_filename("[{Name}]_[{City}]", 1, row, cfg)
    assert "/" not in out and ":" not in out


def test_filename_blank_name_and_unknown_token():
    from edof.batch.model import render_filename, BatchRow
    cfg = _fn_cfg()
    row = BatchRow(values={"c1": "Bob"}, name="")
    assert render_filename("[ROW_NAME]_[ROW_NUMBER]", 3, row, cfg) == "row_3.png"
    # unknown token keeps its text, drops the brackets
    assert render_filename("[BOGUS]_[ROW_NUMBER]", 1, row, cfg) == "BOGUS_1.png"


def test_filename_default_when_empty():
    from edof.batch.model import render_filename, BatchRow
    cfg = _fn_cfg()
    row = BatchRow(values={"c1": "Bob"}, name="n")
    # empty template falls back to a padded row number
    assert render_filename("", 5, row, cfg) == "0005.png"
