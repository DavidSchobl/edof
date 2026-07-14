# -*- coding: utf-8 -*-
"""v4.3.6.24: three rendering fixes from the Michelin cookbook build.
  #3 auto_shrink width overflow (line-width measured incl. left bearing)
  #1 long_shadow clipped to the object bbox (never extended past it)
  #2 halftone ht_color_mode="mono" fell through to CMYK (cyan/black dots)
"""
np = __import__("pytest").importorskip("numpy")  # numpy is an optional test dep
from PIL import Image
import edof
from edof import FillStyle, LayerEffect


def test_lw_measures_full_advance():
    """_lw must not subtract the first glyph's left side bearing (that
    under-measured the line and let it overflow the box on render)."""
    from edof.engine.text_engine import _lw, load_font_safe
    font = load_font_safe("DejaVu Sans", False, False, 40, None)
    for t in ["Ahoj svete", "William", "goodbye"]:
        adv = int(round(font.getlength(t)))
        assert _lw(font, t) >= adv - 1, (t, _lw(font, t), adv)


def test_long_shadow_extends_past_object(tmp_path):
    """The long shadow must paint pixels OUTSIDE the object's own box."""
    doc = edof.new(); p = doc.add_page(dpi=150); p.background = (250, 246, 239, 255)
    sq = p.add_shape("rect", 40, 20, 20, 20)
    sq.fill = FillStyle(color=(44, 138, 138, 255))
    sq.effects.append(LayerEffect(type="long_shadow", ls_length=14, direction=40,
                                  color=(20, 70, 70, 230), ls_alpha_mode="solid"))
    sq.effects_enabled = True
    doc.export_bitmap(str(tmp_path / "_ls_test.png"), dpi=150)
    img = np.array(Image.open(str(tmp_path / "_ls_test.png")).convert("RGB"))
    shadow = np.array([20, 70, 70])
    shadowpx = (np.abs(img.astype(int) - shadow).sum(2) < 70).sum()
    assert shadowpx > 500, shadowpx


def test_halftone_mono_uses_ink_colour(tmp_path):
    """mono halftone must paint the fill colour, not CMYK cyan/magenta/black."""
    doc = edof.new(); p = doc.add_page(dpi=150); p.background = (250, 246, 239, 255)
    a = p.add_shape("rect", 10, 20, 100, 10)
    a.fill = FillStyle(color=(44, 138, 138, 255))
    a.effects.append(LayerEffect(type="halftone", ht_dot=1.8, ht_shape="circle",
                                 ht_color_mode="mono"))
    a.effects_enabled = True
    doc.export_bitmap(str(tmp_path / "_ht_test.png"), dpi=150)
    img = np.array(Image.open(str(tmp_path / "_ht_test.png")).convert("RGB"))
    region = img[int(20 * 150 / 25.4):int(30 * 150 / 25.4),
                 int(10 * 150 / 25.4):int(110 * 150 / 25.4)]
    teal = np.array([44, 138, 138])
    cyan = np.array([0, 255, 255])
    teal_px = (np.abs(region.astype(int) - teal).sum(2) < 90).sum()
    cyan_px = (np.abs(region.astype(int) - cyan).sum(2) < 90).sum()
    bg = np.array([250, 246, 239])
    bg_px = (np.abs(region.astype(int) - bg).sum(2) < 40).sum()
    total = region.shape[0] * region.shape[1]
    assert teal_px > total * 0.10, ("teal", teal_px, total)     # ink dots present
    assert cyan_px < total * 0.02, ("cyan leaked", cyan_px)     # NOT cmyk
    assert bg_px > total * 0.15, ("no raster gaps", bg_px)      # dots, not solid
