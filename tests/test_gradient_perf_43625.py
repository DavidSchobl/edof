# -*- coding: utf-8 -*-
"""v4.3.6.25: gradient render vectorised (per-pixel Python loop -> numpy LUT).
Guards correctness (colours at stop positions) so the fast path can't silently
drift, plus a loose speed sanity check.
"""
import time
np = __import__("pytest").importorskip("numpy")  # numpy is an optional test dep
from edof.engine.renderer import _render_gradient
from edof.format.styles import Gradient


def test_linear_gradient_colours_at_stops():
    g = Gradient(type="linear", angle=0,
                 stops=[(0.0, (0, 0, 0, 255)), (1.0, (255, 255, 255, 255))])
    img = np.array(_render_gradient(200, 20, g))
    # angle 0 = left-to-right: left edge ~black, right edge ~white
    left = img[10, 2, :3].mean()
    right = img[10, 197, :3].mean()
    assert left < 20, left
    assert right > 235, right
    # midpoint ~grey
    mid = img[10, 100, :3].mean()
    assert 100 < mid < 155, mid


def test_gradient_three_stops():
    g = Gradient(type="linear", angle=0,
                 stops=[(0.0, (255, 0, 0, 255)), (0.5, (0, 255, 0, 255)),
                        (1.0, (0, 0, 255, 255))])
    img = np.array(_render_gradient(300, 10, g))
    assert img[5, 2, 0] > 235 and img[5, 2, 1] < 20      # left red
    assert img[5, 150, 1] > 235                           # mid green
    assert img[5, 297, 2] > 235 and img[5, 297, 0] < 20  # right blue


def test_radial_gradient_center_vs_edge():
    g = Gradient(type="radial", center=(0.5, 0.5), radius=0.5,
                 stops=[(0.0, (255, 255, 255, 255)), (1.0, (0, 0, 0, 255))])
    img = np.array(_render_gradient(100, 100, g))
    center = img[50, 50, :3].mean()
    corner = img[2, 2, :3].mean()
    assert center > 235, center           # bright centre
    assert corner < 60, corner            # dark edge


def test_gradient_alpha_interpolates():
    g = Gradient(type="linear", angle=0,
                 stops=[(0.0, (100, 100, 100, 255)), (1.0, (100, 100, 100, 0))])
    img = np.array(_render_gradient(200, 10, g))
    assert img[5, 2, 3] > 235      # opaque left
    assert img[5, 197, 3] < 20     # transparent right


def test_gradient_speed_sanity():
    """A4 @150dpi gradient must render well under a second (was ~7.6s)."""
    g = Gradient(type="linear", angle=30,
                 stops=[(0.0, (44, 138, 138, 255)), (1.0, (240, 240, 220, 255))])
    _render_gradient(1240, 1754, g)   # warm up
    t0 = time.time()
    _render_gradient(1240, 1754, g)
    dt = time.time() - t0
    assert dt < 1.5, dt               # generous ceiling for slow CI
