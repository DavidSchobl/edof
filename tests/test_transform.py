# tests/test_transform.py
import math, pytest
from edof.engine.transform import Transform, to_mm, from_mm, mm_to_px, rotate_point


def test_unit_conversion():
    assert to_mm(1.0, "cm")   == pytest.approx(10.0)
    assert to_mm(1.0, "inch") == pytest.approx(25.4)
    assert to_mm(72.0, "pt")  == pytest.approx(25.4, rel=1e-4)
    assert from_mm(10.0, "cm") == pytest.approx(1.0)


def test_mm_to_px():
    assert mm_to_px(25.4, 96)  == pytest.approx(96.0,  rel=1e-4)
    assert mm_to_px(25.4, 300) == pytest.approx(300.0, rel=1e-4)


def test_translate():
    t = Transform(x=10, y=20)
    t.translate(5, -3)
    assert t.x == pytest.approx(15.0)
    assert t.y == pytest.approx(17.0)


def test_move_to():
    t = Transform()
    t.move_to(100, 200)
    assert t.x == pytest.approx(100.0)
    assert t.y == pytest.approx(200.0)


def test_resize_uniform():
    t = Transform(x=0, y=0, width=100, height=50)
    t.resize_uniform(2.0, anchor="top-left")
    assert t.width  == pytest.approx(200.0)
    assert t.height == pytest.approx(100.0)


def test_resize_uniform_center():
    t = Transform(x=0, y=0, width=100, height=100)
    cx0, cy0 = t.center
    t.resize_uniform(2.0, anchor="center")
    assert t.center[0] == pytest.approx(cx0)
    assert t.center[1] == pytest.approx(cy0)


def test_resize_free():
    t = Transform(width=50, height=30)
    t.resize_free(80, 40)
    assert t.width  == pytest.approx(80.0)
    assert t.height == pytest.approx(40.0)


def test_rotate():
    t = Transform()
    t.rotate(90)
    assert t.rotation == pytest.approx(90.0)
    t.rotate(280)
    assert t.rotation == pytest.approx(10.0)   # wraps at 360


def test_rotate_to():
    t = Transform()
    t.rotate_to(45)
    assert t.rotation == pytest.approx(45.0)


def test_rotate_point_90():
    # Rotating (1, 0) by 90° clockwise around origin → (0, 1)
    x, y = rotate_point(1, 0, 0, 0, 90)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0, abs=1e-9)


def test_flip_horizontal():
    t = Transform()
    assert t.flip_h is False
    t.flip_horizontal()
    assert t.flip_h is True
    t.flip_horizontal()
    assert t.flip_h is False


def test_center():
    t = Transform(x=10, y=20, width=40, height=20)
    assert t.center == pytest.approx((30.0, 30.0))


def test_bounding_box_no_rotation():
    t = Transform(x=10, y=20, width=40, height=20, rotation=0)
    bb = t.bounding_box
    assert bb[0] == pytest.approx(10.0)
    assert bb[1] == pytest.approx(20.0)
    assert bb[2] == pytest.approx(40.0)
    assert bb[3] == pytest.approx(20.0)


def test_serialization_roundtrip():
    t = Transform(x=5, y=7, width=33, height=22, rotation=45, flip_h=True)
    t2 = Transform.from_dict(t.to_dict())
    assert t2.x        == pytest.approx(t.x)
    assert t2.width    == pytest.approx(t.width)
    assert t2.rotation == pytest.approx(t.rotation)
    assert t2.flip_h   == t.flip_h


def test_copy_independence():
    t  = Transform(x=1, y=2)
    t2 = t.copy()
    t2.x = 99
    assert t.x == pytest.approx(1.0)
