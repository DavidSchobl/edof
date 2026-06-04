"""Tests for v4.1.0 features:
- LayerEffect dataclass
- effects field on EdofObject (save/load)
- SubDocumentBox object type (save/load)
- Document.mode field
- Many blend modes work
"""
import os
import tempfile
import pytest

import edof
from edof.format.styles import LayerEffect


# ─────────────────────────────────────────────────────────────────────────────
# LayerEffect
# ─────────────────────────────────────────────────────────────────────────────

def test_layer_effect_default():
    e = LayerEffect()
    assert e.type == "drop_shadow"
    assert e.enabled is True
    assert e.opacity == 1.0
    assert e.size == 2.0
    assert e.direction == 135.0


def test_layer_effect_to_dict_from_dict():
    e = LayerEffect(
        type="outer_glow",
        enabled=True,
        color=(255, 0, 0, 200),
        size=5.0,
        opacity=0.7,
        direction=90.0,
    )
    d = e.to_dict()
    assert d["type"] == "outer_glow"
    assert d["size"] == 5.0
    e2 = LayerEffect.from_dict(d)
    assert e2.type == "outer_glow"
    assert e2.size == 5.0
    assert e2.opacity == 0.7
    assert e2.color[:3] == (255, 0, 0)


def test_layer_effect_all_types():
    for t in ['drop_shadow', 'inner_shadow', 'outer_glow', 'inner_glow',
               'bevel', 'stroke', 'color_overlay', 'gradient_overlay']:
        e = LayerEffect(type=t)
        d = e.to_dict()
        e2 = LayerEffect.from_dict(d)
        assert e2.type == t


# ─────────────────────────────────────────────────────────────────────────────
# Effects field on EdofObject
# ─────────────────────────────────────────────────────────────────────────────

def test_object_has_effects_field():
    doc = edof.new(width=100, height=100)
    page = doc.add_page()
    tb = page.add_textbox(10, 10, 80, 20, "Hello")
    assert hasattr(tb, "effects")
    assert tb.effects == []


def test_object_effects_save_load():
    doc = edof.new(width=100, height=100)
    page = doc.add_page()
    tb = page.add_textbox(10, 10, 80, 20, "Hello")
    tb.effects.append(LayerEffect(type="drop_shadow", size=3.0, color=(0,0,255,200)))
    tb.effects.append(LayerEffect(type="stroke", size=1.0, color=(255,0,0,255)))

    with tempfile.NamedTemporaryFile(suffix=".edof", delete=False) as f:
        path = f.name
    try:
        doc.save(path)
        doc2 = edof.load(path)
        page2 = doc2.pages[0]
        tb2 = page2.objects[0]
        assert len(tb2.effects) == 2
        assert tb2.effects[0].type == "drop_shadow"
        assert tb2.effects[0].size == 3.0
        assert tb2.effects[1].type == "stroke"
    finally:
        os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# Document.mode
# ─────────────────────────────────────────────────────────────────────────────

def test_doc_mode_default():
    doc = edof.new(width=100, height=100)
    assert doc.mode == "empty"


def test_doc_mode_save_load():
    doc = edof.new(width=100, height=100)
    doc.mode = "document"
    doc.add_page()
    with tempfile.NamedTemporaryFile(suffix=".edof", delete=False) as f:
        path = f.name
    try:
        doc.save(path)
        doc2 = edof.load(path)
        assert doc2.mode == "document"
    finally:
        os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# SubDocumentBox
# ─────────────────────────────────────────────────────────────────────────────

def test_subdocument_box_create():
    sub = edof.SubDocumentBox()
    assert sub.OBJECT_TYPE == "subdocument"
    assert sub.fit_mode == "contain"
    assert sub.page_index == 0


def test_subdocument_box_save_load():
    doc = edof.new(width=200, height=200)
    page = doc.add_page()
    sub = edof.SubDocumentBox()
    sub.transform.x = 10; sub.transform.y = 10
    sub.transform.width = 80; sub.transform.height = 80
    sub.source_path = "/tmp/some_other.edof"
    sub.fit_mode = "cover"
    sub.page_index = 2
    page.add_object(sub)

    with tempfile.NamedTemporaryFile(suffix=".edof", delete=False) as f:
        path = f.name
    try:
        doc.save(path)
        doc2 = edof.load(path)
        sub2 = doc2.pages[0].objects[0]
        assert isinstance(sub2, edof.SubDocumentBox)
        assert sub2.fit_mode == "cover"
        assert sub2.page_index == 2
        assert sub2.source_path == "/tmp/some_other.edof"
    finally:
        os.unlink(path)


def test_subdocument_box_resource_embedded():
    """Test embedding a sub-document into resources."""
    sub_doc = edof.new(width=50, height=50, title="Sub")
    sub_doc.add_page().add_textbox(5, 5, 40, 10, "I'm embedded!")
    with tempfile.NamedTemporaryFile(suffix=".edof", delete=False) as f:
        sub_path = f.name
    try:
        sub_doc.save(sub_path)
        with open(sub_path, "rb") as f:
            sub_bytes = f.read()

        # Main doc with embedded sub-doc
        doc = edof.new(width=200, height=200)
        page = doc.add_page()
        # Add resource via proper API
        rid = doc.resources.add(sub_bytes,
                                  filename="embedded.edof",
                                  mime_type="application/x-edof")
        # SubDocumentBox referencing resource
        sub_box = edof.SubDocumentBox()
        sub_box.transform.x = 10; sub_box.transform.y = 10
        sub_box.transform.width = 50; sub_box.transform.height = 50
        sub_box.resource_id = rid
        page.add_object(sub_box)

        # Save and reload
        with tempfile.NamedTemporaryFile(suffix=".edof", delete=False) as f:
            main_path = f.name
        try:
            doc.save(main_path)
            doc2 = edof.load(main_path)
            assert rid in doc2.resources
            sub_box2 = doc2.pages[0].objects[0]
            assert isinstance(sub_box2, edof.SubDocumentBox)
            assert sub_box2.resource_id == rid
        finally:
            os.unlink(main_path)
    finally:
        os.unlink(sub_path)


# ─────────────────────────────────────────────────────────────────────────────
# Blend modes — render doesn't crash with new modes
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode", [
    "normal", "multiply", "screen", "overlay", "darken", "lighten",
    "color_dodge", "color_burn", "hard_light", "soft_light",
    "difference", "exclusion", "hue", "saturation", "color", "luminosity",
])
def test_blend_modes_render(mode):
    """All v4.1.0 blend modes render without crashing."""
    from edof.engine.renderer import render_page
    doc = edof.new(width=50, height=50)
    page = doc.add_page()
    sh2 = page.add_shape("ellipse", 5, 5, 40, 40)
    sh2.fill.color = (50, 200, 100, 200)

    sh = page.add_shape("rect", 10, 10, 30, 30)
    sh.fill.color = (255, 100, 50, 200)
    sh.blend_mode = mode

    img = render_page(page, doc.resources, doc.variables, dpi=72)
    assert img is not None
    assert img.size[0] > 0


# ─────────────────────────────────────────────────────────────────────────────
# Layer effects render
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("effect_type", [
    "drop_shadow", "outer_glow", "stroke", "color_overlay",
    "inner_shadow", "inner_glow",
])
def test_layer_effects_render(effect_type):
    """Layer effects render without crashing."""
    from edof.engine.renderer import render_page
    doc = edof.new(width=50, height=50)
    page = doc.add_page()
    sh = page.add_shape("rect", 10, 10, 30, 30)
    sh.fill.color = (255, 100, 50, 255)
    sh.effects.append(LayerEffect(type=effect_type, size=2.0))

    img = render_page(page, doc.resources, doc.variables, dpi=72)
    assert img is not None


def test_pdf_no_duplicate_text_layer():
    """v4.1.0 CRITICAL: PDF text layer must not contain duplicate emissions.

    Reported by user @4.0.3: each text() / shape() call appended ALL previous
    content cumulatively, causing N(N+1)/2 emissions instead of N. For 50
    textboxes that meant 1275 entries instead of 50, blowing up file size and
    breaking text extraction / search / accessibility.
    """
    import tempfile, os, zlib, re
    doc = edof.new(width=210, height=297, title="No Dup")
    page = doc.add_page()
    n = 25
    for i in range(n):
        page.add_textbox(20, 10 + i * 9, 170, 7, f"unique_marker_{i}")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        doc.export_pdf(path)
        size = os.path.getsize(path)
        # File should be reasonable. Bug previously made this ~50KB+ for 25 boxes.
        assert size < 10_000, f"PDF size {size} suggests duplication bug"

        # Decompress all flate streams and count Tj ops
        with open(path, 'rb') as f:
            content = f.read()
        total_tj = 0
        # Find all "stream\n...\nendstream" pairs
        for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", content, re.DOTALL):
            blob = m.group(1)
            try:
                decompressed = zlib.decompress(blob)
                total_tj += decompressed.count(b" Tj\n")
            except Exception:
                # Not a flate stream
                total_tj += blob.count(b" Tj\n")
        assert total_tj == n, f"Expected {n} Tj ops, got {total_tj} (duplication bug?)"
    finally:
        try: os.unlink(path)
        except Exception: pass


def test_pdf_textbox_with_runs_no_duplicates():
    """Same as above but with rich-text runs."""
    import tempfile, os, zlib, re
    from edof.format.styles import TextRun
    doc = edof.new(width=210, height=297)
    page = doc.add_page()
    tb = page.add_textbox(20, 20, 170, 100, "")
    for i in range(10):
        tb.runs.append(TextRun(text=f"word{i} ", bold=(i % 2 == 0),
                                 italic=(i % 3 == 0), font_size=3.528 + i))
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        doc.export_pdf(path)
        with open(path, 'rb') as f:
            content = f.read()
        total_tj = 0
        for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", content, re.DOTALL):
            blob = m.group(1)
            try:
                decompressed = zlib.decompress(blob)
                total_tj += decompressed.count(b" Tj\n")
            except Exception:
                total_tj += blob.count(b" Tj\n")
        # 10 runs of "wordN " → tokenized as 20 (word + space).
        # Without bug fix this would have been 1+2+...+20 = 210
        assert total_tj <= 25, f"Too many Tj ops ({total_tj}) — duplication?"
    finally:
        try: os.unlink(path)
        except Exception: pass


def test_overflow_hidden_default_false():
    """v4.1.0: text should render even when slightly larger than box.

    Previously overflow_hidden=True default caused silent text loss when
    the line was even 0.5px taller than the box. Reported by user @4.0.3.
    """
    from edof.format.styles import TextStyle
    s = TextStyle()
    assert s.overflow_hidden is False, \
        "overflow_hidden default must be False to prevent silent text loss"


def test_overflow_warning_emitted():
    """When text overflows and auto_shrink is off, a warning is emitted."""
    import warnings
    doc = edof.new(width=210, height=297)
    page = doc.add_page()
    tb = page.add_textbox(20, 20, 170, 8, "BIG HEADING")  # box too short
    tb.style.font_size = 8.467   # mm (= 24pt) — line height 10mm > box 8mm
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            doc.export_bitmap(path, page=0, dpi=96)
            messages = [str(warning.message) for warning in w]
            assert any("overflow" in m.lower() for m in messages), \
                f"Expected overflow warning, got: {messages}"
    finally:
        try: os.unlink(path)
        except Exception: pass


def test_padding_per_side():
    """v4.1.0: TextStyle supports per-side padding via padding_top/_right/etc."""
    from edof.format.styles import TextStyle
    s = TextStyle()
    s.padding = 2.0
    s.padding_left = 8.0
    pt, pr, pb, pl = s.get_padding()
    assert pt == 2.0
    assert pr == 2.0
    assert pb == 2.0
    assert pl == 8.0  # overridden


def test_make_table_with_position():
    """v4.1.0: make_table accepts x/y/col_widths/row_heights."""
    tbl = edof.make_table(
        rows=[["a", "b"], ["c", "d"]],
        x=10, y=20,
        col_widths=[30, 40],
        row_heights=[8, 6],
    )
    assert tbl.transform.x == 10
    assert tbl.transform.y == 20
    assert tbl.transform.width == 70
    assert tbl.transform.height == 14


def test_export_all_pages_bound_method():
    """v4.1.0: Document.export_all_pages exists as a bound method."""
    import tempfile, os
    doc = edof.new(width=100, height=100)
    doc.add_page()
    doc.add_page()
    tmpdir = tempfile.mkdtemp()
    try:
        pattern = os.path.join(tmpdir, "page_{n}.png")
        paths = doc.export_all_pages(pattern, dpi=72)
        assert len(paths) == 2
        for p in paths:
            assert os.path.exists(p)
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_as_color_exported():
    """v4.1.0: edof.as_color is exported for hex-string color input."""
    assert hasattr(edof, 'as_color')
    c = edof.as_color("#4a90e2")
    assert c == (0x4a, 0x90, 0xe2)
    c2 = edof.as_color("#4a90e2cc")
    assert c2 == (0x4a, 0x90, 0xe2, 0xcc)


def test_transform_has_width_height():
    """v4.1.0: Transform has width/height (not w/h). Documented in README."""
    doc = edof.new(width=100, height=100)
    page = doc.add_page()
    tb = page.add_textbox(0, 0, 50, 20, "")
    assert tb.transform.width == 50
    assert tb.transform.height == 20
    # Confirm w/h does NOT exist (would be silent for typo)
    assert not hasattr(tb.transform, 'w')
    assert not hasattr(tb.transform, 'h')


# ─────────────────────────────────────────────────────────────────────────────
# v4.1.1: Viewer + file association
# ─────────────────────────────────────────────────────────────────────────────

def test_viewer_module_imports():
    """v4.1.1: edof._apps.viewer module loads without error."""
    import edof._apps.viewer as vw
    assert hasattr(vw, 'EdofViewer')
    assert hasattr(vw, 'main')


def test_file_assoc_module():
    """v4.1.1: file association helpers exist."""
    import edof._apps.file_assoc as fa
    assert hasattr(fa, 'associate_edof_files')
    assert hasattr(fa, 'unassociate_edof_files')
    assert hasattr(fa, 'current_association_status')
    # Status should run on any platform without raising
    s = fa.current_association_status()
    assert isinstance(s, str)


def test_cli_has_associate_files():
    """v4.1.1: CLI has the associate-files subcommand."""
    from edof._apps.cli import build_parser
    p = build_parser()
    # Parse with --status flag — should not raise
    args = p.parse_args(["associate-files", "--status"])
    assert args.command == "associate-files"
    assert args.status is True
