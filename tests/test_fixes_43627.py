# -*- coding: utf-8 -*-
"""v4.3.6.27: BUG #7 (opacity vs halftone) + BUG #8 (batch image from path)."""
np = __import__("pytest").importorskip("numpy")  # numpy is an optional test dep
from PIL import Image
import edof
from edof import FillStyle, LayerEffect


def _darkness_over_white(opacity, halftone, tmp_path):
    doc = edof.new(100, 100); p = doc.add_page(dpi=100); p.background = (255, 255, 255, 255)
    a = p.add_shape("rect", 10, 10, 80, 80); a.fill = FillStyle(color=(0, 0, 0, 255))
    a.opacity = opacity
    if halftone:
        a.effects.append(LayerEffect(type="halftone", ht_dot=2.5, ht_shape="circle",
                                     ht_color_mode="mono"))
        a.effects_enabled = True
    doc.export_bitmap(str(tmp_path / "_op.png"), dpi=100)
    img = np.array(Image.open(str(tmp_path / "_op.png")).convert("RGB")).astype(float)
    return 1.0 - img[100:300, 100:300].mean() / 255.0


def test_opacity_linear_without_effects(tmp_path):
    for op in (1.0, 0.5, 0.25):
        d = _darkness_over_white(op, False, tmp_path)
        assert abs(d - op) < 0.03, (op, d)


def test_opacity_linear_with_halftone(tmp_path):
    """Opacity must scale a halftone object ~linearly, not cubically."""
    base = _darkness_over_white(1.0, True, tmp_path)
    assert base > 0.2, base
    for op in (0.75, 0.5, 0.25):
        d = _darkness_over_white(op, True, tmp_path)
        ratio = d / base
        # was ~cubic (0.5 -> ~0.16 ratio); must now track opacity within tolerance
        assert abs(ratio - op) < 0.12, (op, ratio)


def test_batch_image_from_path(tmp_path):
    """An ImageBox whose resource_id is a FILE PATH must render (batch fills
    image columns by path)."""
    photo = str(tmp_path / "photo.png")
    Image.new("RGB", (100, 100), (30, 180, 60)).save(photo)
    doc = edof.new(210, 297); p = doc.add_page(dpi=100); p.background = (255, 255, 255, 255)
    ib = p.add_image(photo, 20, 20, 60, 60)          # resource_id = path
    doc.export_bitmap(str(tmp_path / "_ib.png"), dpi=100)
    img = np.array(Image.open(str(tmp_path / "_ib.png")).convert("RGB"))
    green = (np.abs(img.astype(int) - np.array([30, 180, 60])).sum(2) < 80).sum()
    assert green > 1000, green


def test_batch_descriptor_sets_image_path(tmp_path):
    """The batch resource_id descriptor, given a path, must produce a visible image."""
    from edof.batch import find_descriptor
    photo = str(tmp_path / "p2.png")
    Image.new("RGB", (80, 80), (200, 30, 30)).save(photo)
    doc = edof.new(210, 297); p = doc.add_page(dpi=100); p.background = (255, 255, 255, 255)
    ib = p.add_image("placeholder", 20, 20, 60, 60)
    d = find_descriptor(ib, "resource_id")
    assert d is not None
    d.set(ib, photo)                                  # like a batch row
    doc.export_bitmap(str(tmp_path / "_ib2.png"), dpi=100)
    img = np.array(Image.open(str(tmp_path / "_ib2.png")).convert("RGB"))
    red = (np.abs(img.astype(int) - np.array([200, 30, 30])).sum(2) < 80).sum()
    assert red > 1000, red
