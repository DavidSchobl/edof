"""
Tests for edof 3.1.0 new features:
  - Item 1: configurable padding
  - Item 2: font fallback with warning
  - Item 3: cross-platform font aliases
  - Item 4: helper widgets (card, metric, table, kv_list)
  - Item 5: layout helpers (row, column)
  - Item 6: auto-height textbox
  - measure_text_height helper
"""
import sys, os, warnings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import edof
from edof.format.styles import TextStyle
from edof.engine.text_engine import (
    get_font_path, measure_text_height, find_fitting_size, list_system_fonts
)


@pytest.fixture
def page():
    doc  = edof.new(width=210, height=297)
    pg   = doc.add_page(dpi=96)
    return doc, pg


# ── Item 1: padding ────────────────────────────────────────────────────────────

def test_textstyle_has_padding():
    s = TextStyle()
    assert hasattr(s, 'padding'), "TextStyle must have a padding attribute"
    assert s.padding == 1.0, "Default padding should be 1.0 mm"


def test_textstyle_custom_padding():
    s = TextStyle(padding=3.5)
    assert s.padding == 3.5


def test_padding_smaller_than_2mm_default(page):
    """Padding=0.5 allows text in a tiny 5mm-tall box (was invisible with 2mm default)."""
    _, pg = page
    tb = pg.add_textbox(10, 10, 60, 5, "X")
    tb.style.font_size = 0.996
    tb.style.padding   = 0.5
    from edof.engine.renderer import render_page
    from edof.format.document import Document
    doc = edof.new(); doc.pages.append(pg)
    # Should render without error
    img = render_page(pg, doc.resources, doc.variables, dpi=96)
    assert img is not None


# ── Item 2: font fallback ──────────────────────────────────────────────────────

def test_missing_font_warns():
    """
    EdofMissingFontWarning is emitted when a font is not found via direct lookup
    OR via the alias table.  We patch _get_db to return an empty DB so the
    alias fallback also fails, ensuring the warning path is exercised.
    """
    from edof.engine import text_engine as _te
    from edof.exceptions import EdofMissingFontWarning

    original_get_db = _te._get_db
    _te._get_db = lambda: {}   # empty DB → nothing found
    _te._FONT_CACHE.clear()

    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            font = _te.load_font_safe("TotallyNonExistentFont999", False, False, 20)
            assert font is not None, "Should return fallback font, not None"
            missing = [x for x in w if issubclass(x.category, EdofMissingFontWarning)]
            assert missing, "Should emit EdofMissingFontWarning"
    finally:
        _te._get_db = original_get_db
        _te._FONT_CACHE.clear()


def test_missing_font_returns_usable_font():
    from edof.engine.text_engine import load_font_safe, _lw
    font = load_font_safe("TotallyFakeFontName", False, False, 20)
    # Should be usable for measurement
    w = _lw(font, "Hello")
    assert w >= 0


# ── Item 3: cross-platform font aliases ────────────────────────────────────────

@pytest.mark.parametrize("alias", [
    "Arial", "Helvetica", "Times New Roman", "Courier New",
    "Calibri", "Verdana", "Georgia",
])
def test_font_alias_resolves(alias):
    path = get_font_path(alias)
    assert path is not None, (
        f"Font alias '{alias}' should resolve to a system font path. "
        f"Install liberation-fonts or dejavu-fonts.")
    assert os.path.isfile(path), f"Resolved path does not exist: {path}"


def test_direct_font_still_works():
    fonts = list_system_fonts()
    if not fonts:
        pytest.skip("No system fonts found")
    path = get_font_path(fonts[0])
    assert path is not None


# ── Item 4: helper widgets ─────────────────────────────────────────────────────

def test_add_card(page):
    _, pg = page
    g = pg.add_card(10, 10, 80, 40, title="Card Title", body="Body text")
    assert g.OBJECT_TYPE == "group"
    assert len(g.children) >= 2   # at least bg + accent bar


def test_add_card_no_body(page):
    _, pg = page
    g = pg.add_card(10, 10, 80, 20, title="Only title")
    assert g.OBJECT_TYPE == "group"


def test_add_metric(page):
    _, pg = page
    g = pg.add_metric(10, 10, 40, 25, "Revenue", "€12k", "↑ 5%")
    assert g.OBJECT_TYPE == "group"
    assert len(g.children) == 3   # value + label + subtitle


def test_add_metric_no_subtitle(page):
    _, pg = page
    g = pg.add_metric(10, 10, 40, 25, "Count", "42")
    assert len(g.children) == 2


def test_add_table(page):
    _, pg = page
    rows = [["Name", "Score", "Grade"],
            ["Alice",  "98",    "A"],
            ["Bob",    "87",    "B"],
            ["Carol",  "72",    "C"]]
    g = pg.add_table(5, 5, 130, rows, header=True, row_height=8)
    assert g.OBJECT_TYPE == "group"
    # 4 rows × (1 bg + 3 cells) = 16 children
    assert len(g.children) == 4 * (1 + 3)


def test_add_table_no_header(page):
    _, pg = page
    g = pg.add_table(5, 5, 100, [["A","B"],["C","D"]], header=False)
    assert g.OBJECT_TYPE == "group"


def test_add_table_empty(page):
    _, pg = page
    g = pg.add_table(5, 5, 100, [])
    assert g.OBJECT_TYPE == "group"
    assert len(g.children) == 0


def test_add_kv_list(page):
    _, pg = page
    g = pg.add_kv_list(10, 10, 80, [
        ("Author", "Jan Novák"),
        ("Date", "2025-01-01"),
        ("Version", "3.1.0"),
    ])
    assert g.OBJECT_TYPE == "group"
    assert len(g.children) == 6   # 3 rows × 2 cells


# ── Item 5: layout helpers ─────────────────────────────────────────────────────

def test_row_positions(page):
    _, pg = page
    row = pg.row(y=20, gap=4, height=10)
    t1  = row.add_textbox(50, "A")
    t2  = row.add_textbox(40, "B")
    t3  = row.add_textbox(30, "C")
    assert t1.transform.x == 0
    assert t2.transform.x == pytest.approx(54, abs=0.1)   # 50 + 4
    assert t3.transform.x == pytest.approx(98, abs=0.1)   # 50+4+40+4
    # All at same y
    assert t1.transform.y == t2.transform.y == t3.transform.y == pytest.approx(20)


def test_row_height(page):
    _, pg = page
    row = pg.row(y=10, height=15)
    t   = row.add_textbox(60, "X")
    assert t.transform.height == pytest.approx(15)


def test_row_skip(page):
    _, pg = page
    row = pg.row(y=0, gap=2, height=8)
    t1  = row.add_textbox(20, "A")
    row.skip(10)
    t2  = row.add_textbox(20, "B")
    assert t2.transform.x == pytest.approx(20 + 2 + 10 + 2, abs=0.1)


def test_column_positions(page):
    _, pg = page
    col = pg.column(x=15, gap=3, width=50)
    c1  = col.add_textbox(10, "Row 1")
    c2  = col.add_textbox(12, "Row 2")
    c3  = col.add_textbox(8,  "Row 3")
    assert c1.transform.y == pytest.approx(0)
    assert c2.transform.y == pytest.approx(13, abs=0.1)   # 10 + 3
    assert c3.transform.y == pytest.approx(28, abs=0.1)   # 10+3+12+3
    # All at same x
    assert c1.transform.x == c2.transform.x == c3.transform.x == pytest.approx(15)


def test_column_auto_textbox(page):
    _, pg = page
    col = pg.column(x=10, gap=2, width=80)
    c1  = col.add_textbox_auto("Short text", font_size=4.233)
    c2  = col.add_textbox_auto("Longer text that might wrap over several lines " * 3,
                                font_size=4.233, wrap=True)
    assert c1.transform.height > 0
    assert c2.transform.height > c1.transform.height, \
        "Longer text should produce taller auto box"
    assert c2.transform.y > c1.transform.y + c1.transform.height, \
        "Second box should start below the first"


def test_column_skip(page):
    _, pg = page
    col = pg.column(x=10, gap=2, width=50)
    c1  = col.add_textbox(10, "A")
    col.skip(20)
    c2  = col.add_textbox(10, "B")
    assert c2.transform.y == pytest.approx(10 + 2 + 20 + 2, abs=0.1)


def test_row_next_x(page):
    _, pg = page
    row = pg.row(y=0, gap=5, height=10)
    row.add_textbox(30, "X")
    assert row.next_x == pytest.approx(35, abs=0.1)


def test_column_next_y(page):
    _, pg = page
    col = pg.column(x=0, gap=4, width=50)
    col.add_textbox(20, "Y")
    assert col.next_y == pytest.approx(24, abs=0.1)


# ── Item 6: auto-height textbox ────────────────────────────────────────────────

def test_add_textbox_auto_basic(page):
    _, pg = page
    tb = pg.add_textbox_auto(10, 10, 100, text="Hello World", font_size=4.939)
    assert tb.transform.height > 0
    assert tb.transform.height < 30   # should be small for one line


def test_add_textbox_auto_min_height(page):
    _, pg = page
    tb = pg.add_textbox_auto(10, 10, 100, text="Hi", font_size=2.822, min_height=15)
    assert tb.transform.height >= 15


def test_add_textbox_auto_multiline(page):
    _, pg = page
    short = pg.add_textbox_auto(10, 10, 80, text="Short", font_size=4.233)
    long  = pg.add_textbox_auto(10, 50, 80,
                                 text="This is a much longer text that should wrap " * 5,
                                 font_size=4.233, wrap=True)
    assert long.transform.height > short.transform.height


def test_add_textbox_auto_empty(page):
    _, pg = page
    tb = pg.add_textbox_auto(10, 10, 80, text="", font_size=4.233, min_height=8)
    assert tb.transform.height >= 8


def test_measure_text_height():
    s = TextStyle(font_size=4.233, wrap=True)
    h1 = measure_text_height("Short", s, width_mm=100)
    h2 = measure_text_height("Much longer text " * 20, s, width_mm=50)
    assert h1 > 0
    assert h2 > h1


def test_measure_text_height_empty():
    s = TextStyle(font_size=4.233)
    h = measure_text_height("", s, width_mm=100)
    assert h > 0   # empty returns single-line height


# ── Render integration ─────────────────────────────────────────────────────────

def test_render_with_all_new_helpers():
    """Full integration: build a page with all new widgets and render it."""
    doc  = edof.new(width=210, height=297)
    page = doc.add_page(dpi=72)

    # Auto-height textbox
    page.add_textbox_auto(10, 10, 190, text="Document Title", font_size=8.467, bold=True)

    # Row of metrics
    row = page.row(y=30, gap=5, height=25)
    page.add_metric(row.next_x, row.y, 55, 25, "Revenue", "€12k")
    row.skip(55)
    page.add_metric(row.next_x, row.y, 55, 25, "Users", "1,234")
    row.skip(55)
    page.add_metric(row.next_x, row.y, 55, 25, "Growth", "+15%")

    # Card
    page.add_card(10, 60, 90, 40, title="Summary", body="Q1 results exceeded expectations.")

    # Table
    page.add_table(10, 108, 190,
                   [["Product","Q1","Q2"],["Alpha","12k","15k"],["Beta","8k","11k"]],
                   row_height=8)

    # KV list
    page.add_kv_list(110, 60, 90, [
        ("Date", "2025-01-31"), ("Author", "Jan"), ("Version", "1.0"),
    ])

    from edof.engine.renderer import render_page
    img = render_page(page, doc.resources, doc.variables, dpi=72)
    assert img.size[0] > 0 and img.size[1] > 0
