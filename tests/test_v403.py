"""
Tests for edof 4.0.3 — editor catches up with the API + RTF support.

Coverage:
  - PDF import path bbox correctness
  - PDF import flags (extract_paths, extract_images)
  - ImageBox default fit_mode = stretch
  - Document.margins save/load
  - RTF roundtrip preserves text + formatting
  - Editor source has v4.0.3 modifier semantics (Ctrl bypass, Shift toggle)
  - Editor has Insert Table / Path tool / Help dialog
  - Editor has Advanced properties group (visible_if, lock_level, blend, shadow)
"""
import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import edof


# ── ImageBox stretch default ─────────────────────────────────────────────────

def test_imagebox_default_fit_mode_stretch():
    """v4.0.3: ImageBox now defaults to stretch (was contain)."""
    img = edof.ImageBox()
    assert img.fit_mode == "stretch"


def test_imagebox_load_default_stretch(tmp_path):
    """A saved ImageBox without fit_mode set defaults to stretch on load."""
    doc = edof.new()
    page = doc.add_page()
    img = edof.ImageBox()
    page.add_object(img)
    p = tmp_path / "i.edof"
    doc.save(str(p))
    doc2 = edof.load(str(p))
    img2 = doc2.pages[0].objects[0]
    assert img2.fit_mode == "stretch"


# ── Document margins ─────────────────────────────────────────────────────────

def test_document_margins_field_exists():
    doc = edof.new()
    assert hasattr(doc, "margins")
    assert doc.margins is None


def test_document_margins_save_load(tmp_path):
    doc = edof.new()
    doc.margins = (10.0, 12.0, 14.0, 16.0)
    doc.add_page().add_textbox(20, 20, 100, 10, "test")
    p = tmp_path / "m.edof"
    doc.save(str(p))

    doc2 = edof.load(str(p))
    assert doc2.margins == (10.0, 12.0, 14.0, 16.0)


def test_document_margins_optional():
    """Documents without margins still load."""
    doc = edof.new()
    assert doc.margins is None
    d = doc.to_dict()
    assert "margins" in d
    assert d["margins"] is None


# ── PDF import paths bbox (v4.0.3 fix) ──────────────────────────────────────

@pytest.fixture
def curves_pdf(tmp_path):
    """Build a small PDF with vector shapes for testing import."""
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas
    p = str(tmp_path / "curves.pdf")
    c = canvas.Canvas(p)
    c.rect(100, 600, 200, 100, fill=1)
    c.line(50, 500, 500, 500)
    pa = c.beginPath()
    pa.moveTo(50, 400); pa.curveTo(150, 500, 350, 300, 500, 400)
    c.drawPath(pa)
    c.circle(300, 200, 50)
    c.save()
    return p


def test_pdf_import_paths_have_proper_bbox(curves_pdf):
    pytest.importorskip("fitz")
    doc = edof.import_pdf(curves_pdf)
    paths = [o for o in doc.pages[0].objects if hasattr(o, "shape_type")]
    assert paths, "Should have extracted at least one path"
    # No path should span the full page (the bug we fixed)
    for path in paths:
        t = path.transform
        assert t.width < 200, f"Path bbox spans full page: w={t.width}"
        assert t.height < 290, f"Path bbox spans full page: h={t.height}"


def test_pdf_import_extract_flags(curves_pdf):
    """v4.0.3: extract_paths and extract_images flags work."""
    pytest.importorskip("fitz")
    doc_no_paths = edof.import_pdf(curves_pdf, extract_paths=False)
    paths = [o for o in doc_no_paths.pages[0].objects if hasattr(o, "shape_type")]
    assert len(paths) == 0, "extract_paths=False should skip paths"


def test_pdf_import_paths_render(curves_pdf, tmp_path):
    """Paths still render correctly after the bbox change."""
    pytest.importorskip("fitz")
    doc = edof.import_pdf(curves_pdf)
    out = tmp_path / "rendered.png"
    doc.export_bitmap(str(out), page=0, dpi=72)
    assert out.exists() and out.stat().st_size > 1000


# ── RTF import/export ────────────────────────────────────────────────────────

def test_rtf_export_basic(tmp_path):
    doc = edof.new(title="Test")
    page = doc.add_page()
    page.add_textbox(20, 20, 170, 10, "Hello, World!")
    page.add_textbox(20, 40, 170, 10, "Second paragraph.")

    p = tmp_path / "out.rtf"
    doc.export_rtf(str(p))
    assert p.exists() and p.stat().st_size > 50

    raw = p.read_bytes()
    assert raw.startswith(b"{\\rtf1")
    assert b"Hello, World" in raw


def test_rtf_export_unicode(tmp_path):
    """Czech text round-trips through unicode escapes."""
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(20, 20, 170, 10, "Příšerně český text — ěščřžýáí.")

    p = tmp_path / "uni.rtf"
    doc.export_rtf(str(p))

    doc2 = edof.import_rtf(str(p))
    found = False
    for pg in doc2.pages:
        for o in pg.objects:
            if isinstance(o, edof.TextBox) and "ěščřžýáí" in o.text:
                found = True
    assert found, "Czech unicode should round-trip through RTF"


def test_rtf_roundtrip_preserves_paragraphs(tmp_path):
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(20, 20, 170, 10, "First paragraph.")
    page.add_textbox(20, 40, 170, 10, "Second paragraph here.")
    page.add_textbox(20, 60, 170, 10, "Third paragraph with more words and stuff.")

    p = tmp_path / "rt.rtf"
    doc.export_rtf(str(p))
    doc2 = edof.import_rtf(str(p))

    # Should have 3 textboxes (one per non-empty paragraph)
    text_boxes = [o for pg in doc2.pages for o in pg.objects
                   if isinstance(o, edof.TextBox)]
    # Empty paragraphs may also be created; check that all 3 strings are present
    all_text = " ".join(tb.text for tb in text_boxes)
    assert "First paragraph" in all_text
    assert "Second paragraph" in all_text
    assert "Third paragraph" in all_text


def test_rtf_import_invalid_file_raises(tmp_path):
    p = tmp_path / "not_rtf.txt"
    p.write_text("This is not RTF")
    with pytest.raises(ValueError, match="not look like an RTF"):
        edof.import_rtf(str(p))


def test_import_rtf_in_namespace():
    """edof.import_rtf is exposed at top level."""
    assert hasattr(edof, "import_rtf")
    assert callable(edof.import_rtf)


def test_export_rtf_method_on_document():
    """Document.export_rtf exists."""
    doc = edof.new()
    assert hasattr(doc, "export_rtf")
    assert callable(doc.export_rtf)


# ── Editor source-level checks ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def editor_src():
    p = os.path.join(os.path.dirname(__file__), "..", "edof", "_apps", "editor.py")
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_editor_has_v403_modifier_semantics(editor_src):
    """v4.0.3: Ctrl bypass + reverse Shift logic for ImageBox."""
    assert "Ctrl is the new" in editor_src or "no_snap = alt or ctrl" in editor_src
    assert "is_image = isinstance(obj, ImageBox)" in editor_src


def test_editor_has_path_tool(editor_src):
    """Path drawing tool present."""
    assert "_ins_path" in editor_src
    assert "_path_drawing" in editor_src
    assert "_finish_path_drawing" in editor_src


def test_editor_has_insert_table(editor_src):
    """Insert Table dialog present."""
    assert "_ins_table" in editor_src
    assert "Insert Table" in editor_src


def test_editor_has_help_dialog(editor_src):
    """Keyboard shortcuts help dialog present."""
    assert "_show_shortcuts" in editor_src
    assert "Keyboard Shortcuts" in editor_src


def test_editor_has_advanced_properties(editor_src):
    """Properties panel has v4.0.3 advanced fields.

    v4.1.1: drop shadow moved exclusively to Layer Effects dialog;
    the legacy `_on_shadow_toggle` was removed.
    """
    assert "visible_if" in editor_src
    assert "lock_level" in editor_src
    assert "blend_mode" in editor_src
    assert "_open_layer_effects_dialog" in editor_src


def test_editor_object_panel_has_dragdrop_and_rename(editor_src):
    """Object panel: drag&drop, F2 rename, right-click menu."""
    assert "DragDropMode.InternalMove" in editor_src
    assert "_on_item_renamed" in editor_src
    assert "_on_context_menu" in editor_src


def test_editor_has_pdf_export_dialog(editor_src):
    """PDF export shows vector/raster choice dialog."""
    assert "Vector PDF" in editor_src
    assert "Raster PDF" in editor_src


def test_editor_has_margins(editor_src):
    """Margins toggle + dialog present."""
    assert "_margins_enabled" in editor_src
    assert "_set_margins_dlg" in editor_src
    assert "_snap_to_margins" in editor_src


def test_editor_has_panel_persistence(editor_src):
    """v4.0.3: Window state (dock layout) saved/restored."""
    assert "saveState" in editor_src
    assert "restoreState" in editor_src


def test_editor_has_subpixel_render_fix(editor_src):
    """v4.1.15.7: oversampling removed (caused text-position jumps at
    different zoom levels). Render is now at canvas DPI directly."""
    assert ("render at canvas DPI directly" in editor_src or
            "thin text strokes" in editor_src or
            "multiplier = min" in editor_src)


# ── Backward compat ─────────────────────────────────────────────────────────

def test_v401_features_still_work():
    """Encryption still works."""
    pytest.importorskip("cryptography")
    doc = edof.new()
    doc.add_page().add_textbox(10, 10, 100, 10, "test")
    rk = doc.set_password("admin", "x")
    assert rk is not None
    assert doc.is_encrypted


def test_v402_variable_substitution_still_works():
    """The {name} fix from 4.0.2 still works."""
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 180, 12, "Hello {name}!")
    doc.define_variable("name", default="World")
    doc.set_variable("name", "Alice")
    tb = page.objects[0]
    assert tb.get_resolved_text(doc.variables) == "Hello Alice!"
