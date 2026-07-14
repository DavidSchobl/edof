# -*- coding: utf-8 -*-
"""v4.3.6.25: second round of cookbook fixes.
  #3 auto_shrink STILL overflowed (fit used a different layout than render)
  #6 BorderStyle class was documented but missing
  #5 from_svg_path with absolute coords rendered nothing (no transform)
  #4 edof.new() empty-doc get_page gave a bare IndexError
  effects_enabled=False silent no-op now warns
"""
import warnings
np = __import__("pytest").importorskip("numpy")  # numpy is an optional test dep
from PIL import Image
import edof
from edof import FillStyle, BorderStyle, LayerEffect, Shape


def test_autoshrink_fit_matches_render():
    """find_fitting_scale must pick a scale where the ACTUAL render fits the
    box width -- fit and render must use the same layout."""
    from edof.engine.text_engine import find_fitting_scale, mm_to_px
    from edof.engine.text_layout import layout_runs
    from edof.format.styles import TextRun, TextStyle
    st = TextStyle(); st.font_size = 3.6; st.auto_shrink = True
    txt = ("Vyhnet hladke leskle testo ze vsech surovin krome laminovaciho "
           "masla, hnet 10-12 minut do plneho vyvinuti lepku. " * 4)
    runs = [TextRun(text=txt)]
    dpi = 200
    pad = mm_to_px(getattr(st, 'padding', 1.0), dpi)
    iw = int(mm_to_px(90, dpi) - 2 * pad); ih = int(mm_to_px(118, dpi) - 2 * pad)
    scale = find_fitting_scale(runs, st, iw, ih, dpi=dpi, wrap=st.wrap, shrink_only=True)
    lay = layout_runs(runs, st, 0.0, 0.0, float(iw + 2 * pad), float(ih + 2 * pad),
                      dpi, scale=scale)
    assert lay.total_w <= iw + 1, (lay.total_w, iw)     # render does NOT overflow
    assert lay.total_h <= ih + 1, (lay.total_h, ih)


def test_borderstyle_imports_and_renders(tmp_path):
    """BorderStyle must import, render, honour enabled, and survive save/load."""
    doc = edof.new(); p = doc.add_page(dpi=150); p.background = (255, 255, 255, 255)
    tb = p.add_textbox(20, 20, 60, 30, "Ahoj")
    tb.border = BorderStyle(enabled=True, color=(200, 50, 50, 255), width=0.5, radius=3.0)
    doc.export_bitmap(str(tmp_path / "_bs.png"), dpi=150)
    img = np.array(Image.open(str(tmp_path / "_bs.png")).convert("RGB"))
    red = (np.abs(img.astype(int) - np.array([200, 50, 50])).sum(2) < 80).sum()
    assert red > 100, red
    doc.save(str(tmp_path / "_bs.edof"))
    tb2 = edof.load(str(tmp_path / "_bs.edof")).pages[0].objects[0]
    assert isinstance(tb2.border, BorderStyle)
    assert abs(tb2.border.radius - 3.0) < 1e-6
    # enabled=False -> nothing
    tb.border = BorderStyle(enabled=False, color=(200, 50, 50, 255), width=0.5)
    doc.export_bitmap(str(tmp_path / "_bs2.png"), dpi=150)
    img2 = np.array(Image.open(str(tmp_path / "_bs2.png")).convert("RGB"))
    red2 = (np.abs(img2.astype(int) - np.array([200, 50, 50])).sum(2) < 80).sum()
    assert red2 == 0, red2


def test_from_svg_path_absolute_renders(tmp_path):
    """from_svg_path with absolute coords must set the transform from the bbox
    and render (not clip to a default box)."""
    heart = ("M100 100 C100 90 85 80 70 90 C55 100 55 115 100 140 "
             "C145 115 145 100 130 90 C115 80 100 90 100 100 Z")
    sh = Shape.from_svg_path(heart)
    assert abs(sh.transform.x - 55.0) < 1.0
    assert abs(sh.transform.y - 80.0) < 1.0
    assert sh.transform.width > 10 and sh.transform.height > 10
    sh.fill = FillStyle(color=(220, 40, 60, 255))
    doc = edof.new(); p = doc.add_page(dpi=150); p.background = (255, 255, 255, 255)
    p.objects.append(sh)
    doc.export_bitmap(str(tmp_path / "_heart.png"), dpi=150)
    img = np.array(Image.open(str(tmp_path / "_heart.png")).convert("RGB"))
    red = (np.abs(img.astype(int) - np.array([220, 40, 60])).sum(2) < 80).sum()
    assert red > 1000, red


def test_new_empty_doc_get_page_message():
    """get_page on an empty document must raise a clear, actionable error."""
    doc = edof.new()
    assert len(doc.pages) == 0
    try:
        doc.get_page(0)
        assert False, "expected IndexError"
    except IndexError as e:
        assert "add_page" in str(e)


def test_effects_disabled_warns(tmp_path):
    """An object with effects but effects_enabled=False must warn on render."""
    doc = edof.new(); p = doc.add_page(dpi=80); p.background = (255, 255, 255, 255)
    sq = p.add_shape("rect", 10, 10, 20, 20); sq.fill = FillStyle(color=(44, 138, 138, 255))
    sq.effects.append(LayerEffect(type="drop_shadow", size=2, distance=2))
    assert sq.effects_enabled is False
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        doc.export_bitmap(str(tmp_path / "_fx.png"), dpi=80)
        assert any("effects_enabled" in str(x.message) for x in w)
