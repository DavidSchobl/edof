# -*- coding: utf-8 -*-
"""Renderer fixes in the 4.3.5.x line."""
np = __import__("pytest").importorskip("numpy")  # numpy is an optional test dep

import edof
from edof.engine.renderer import render_page


def _ellipse_stroke_gaps(stroke_w_mm, dpi=100):
    """Render a centred ellipse outline and return the gap (px) between the
    object's nominal bounds and the stroke on each side (L, R, T, B)."""
    doc = edof.Document()
    p = doc.add_page(width=60, height=60)
    e = p.add_shape("ellipse", 10, 10, 40, 40)
    e.fill.color = (255, 255, 255, 0)          # no fill, stroke only
    e.stroke.color = (255, 0, 0, 255)
    e.stroke.width = stroke_w_mm
    a = np.asarray(render_page(p, doc.resources, doc.variables, dpi=dpi).convert("RGBA"))
    red = (a[..., 0] > 150) & (a[..., 1] < 100) & (a[..., 3] > 100)
    ys, xs = np.where(red)
    left = xs.min() - round(10 / 25.4 * dpi)
    right = round(50 / 25.4 * dpi) - xs.max()
    top = ys.min() - round(10 / 25.4 * dpi)
    bot = round(50 / 25.4 * dpi) - ys.max()
    return left, right, top, bot


def test_ellipse_stroke_not_clipped_right_bottom():
    # the bug: the right/bottom half of the stroke was clipped, so the right
    # gap was much larger than the left. After the fix all four gaps match
    # within rounding.
    left, right, top, bot = _ellipse_stroke_gaps(2.0)
    assert abs(left - right) <= 2
    assert abs(top - bot) <= 2


def test_ellipse_stroke_thick_symmetric():
    left, right, top, bot = _ellipse_stroke_gaps(4.0)
    assert abs(left - right) <= 2
    assert abs(top - bot) <= 2


def test_ellipse_fill_still_drawn():
    doc = edof.Document()
    p = doc.add_page(width=60, height=60)
    e = p.add_shape("ellipse", 10, 10, 40, 40)
    e.fill.color = (0, 0, 255, 255)
    e.stroke.color = (255, 0, 0, 255)
    e.stroke.width = 2.0
    a = np.asarray(render_page(p, doc.resources, doc.variables, dpi=100).convert("RGBA"))
    blue = (a[..., 2] > 150) & (a[..., 0] < 100)
    assert int(blue.sum()) > 1000              # interior filled


def test_rect_stroke_symmetric_no_regression():
    doc = edof.Document()
    p = doc.add_page(width=60, height=60)
    r = p.add_shape("rect", 10, 10, 40, 40)
    r.fill.color = (255, 255, 255, 0)
    r.stroke.color = (0, 255, 0, 255)
    r.stroke.width = 3.0
    a = np.asarray(render_page(p, doc.resources, doc.variables, dpi=100).convert("RGBA"))
    g = (a[..., 1] > 150) & (a[..., 0] < 100) & (a[..., 3] > 100)
    ys, xs = np.where(g)
    left = xs.min() - round(10 / 25.4 * 100)
    right = round(50 / 25.4 * 100) - xs.max()
    assert abs(left - right) <= 2


def test_rotated_ellipse_renders():
    doc = edof.Document()
    p = doc.add_page(width=60, height=60)
    e = p.add_shape("ellipse", 10, 10, 40, 30)
    e.fill.color = (0, 0, 0, 255)
    e.stroke.color = (255, 0, 0, 255)
    e.stroke.width = 2.0
    e.transform.rotation = 30
    img = render_page(p, doc.resources, doc.variables, dpi=100)
    assert img is not None


# ── master 'All effects' switch (v4.3.5.12) ──────────────────────────────────
def test_effects_master_switch_renders():
    import edof
    from edof.engine.renderer import render_page
    import numpy as np

    def redpx(d):
        a = np.asarray(render_page(d.pages[0], d.resources, d.variables,
                                   dpi=100).convert("RGB"))
        return int(((a[..., 0].astype(int) - a[..., 1]) > 80).sum())

    d = edof.Document()
    p = d.add_page(width=80, height=50)
    sh = p.add_shape("rect", 25, 18, 30, 14)
    sh.fill.color = (0, 0, 0)
    sh.effects.append(edof.LayerEffect(type="drop_shadow", enabled=True,
                                       distance=4, color=(255, 0, 0, 255)))
    sh.effects_enabled = True           # master on (default is now off)
    assert redpx(d) > 0
    sh.effects_enabled = False
    assert redpx(d) == 0                # master off -> nothing renders
    assert len(sh.effects) == 1         # but the effect stays on the object
    sh.effects_enabled = True
    assert redpx(d) > 0


def test_effects_master_serialization_roundtrip():
    import edof
    from edof.format.serializer import EdofSerializer
    d = edof.Document()
    p = d.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    sh.effects.append(edof.LayerEffect(type="drop_shadow"))
    sh.effects_enabled = False
    d2 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(d))
    assert d2.pages[0].objects[0].effects_enabled is False
    assert len(d2.pages[0].objects[0].effects) == 1
    # default false for a fresh object (no effects -> nothing to show)
    sh2 = p.add_shape("rect", 0, 0, 10, 10)
    assert sh2.effects_enabled is False


def test_effects_all_enabled_is_batchable():
    import edof
    from edof.batch import describe_object, find_descriptor, apply_value
    d = edof.Document()
    p = d.add_page(width=80, height=50)
    sh = p.add_shape("rect", 10, 10, 40, 30)
    paths = {x.path for x in describe_object(sh)}
    assert "effects.all_enabled" in paths        # offered even with no effects
    desc = find_descriptor(sh, "effects.all_enabled")
    assert desc is not None and desc.kind == "enum"
    assert apply_value(sh, "effects.all_enabled", "false") is True
    assert sh.effects_enabled is False
    assert apply_value(sh, "effects.all_enabled", "true") is True
    assert sh.effects_enabled is True


def test_disabled_effect_stays_on_object_but_not_rendered():
    import edof
    from edof.engine.renderer import render_page
    import numpy as np

    def redpx(d):
        a = np.asarray(render_page(d.pages[0], d.resources, d.variables,
                                   dpi=100).convert("RGB"))
        return int(((a[..., 0].astype(int) - a[..., 1]) > 80).sum())

    d = edof.Document()
    p = d.add_page(width=80, height=50)
    sh = p.add_shape("rect", 25, 18, 30, 14)
    sh.fill.color = (0, 0, 0)
    # a DISABLED effect must remain on the object (so it can be batched) but
    # must not render
    sh.effects_enabled = True            # master on; test the per-effect flag
    sh.effects.append(edof.LayerEffect(type="drop_shadow", enabled=False,
                                       distance=4, color=(255, 0, 0, 255)))
    assert len(sh.effects) == 1
    assert redpx(d) == 0
    sh.effects[0].enabled = True
    assert redpx(d) > 0
