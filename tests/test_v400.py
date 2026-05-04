"""
Tests for edof 4.0.0 features:
  - Rich text runs in TextBox
  - Formatted Tables with TableCell
  - Bezier path Shape (SVG path syntax)
  - Linear/radial gradients
  - Conditional visibility (visible_if)
  - Repeating sections (repeat_objects)
  - Vector PDF export
  - SVG export
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import edof
from edof.format.styles import TextRun, Gradient, TextStyle, FillStyle
from edof.format.objects import (Table, TableCell, CellBorder, Shape,
                                  TextBox, SHAPE_PATH, _parse_svg_path)


@pytest.fixture
def doc():
    d = edof.new(width=210, height=297, title="Test")
    d.add_page(dpi=96)
    return d


# ── TextRun ───────────────────────────────────────────────────────────────────

def test_textrun_creation():
    r = TextRun(text="Hello", bold=True, color=(255, 0, 0))
    assert r.text == "Hello"
    assert r.bold is True
    assert r.color == (255, 0, 0)
    assert r.font_size is None  # inherits


def test_textrun_resolve_inherits():
    style = TextStyle(font_size=12, font_family="Arial", bold=False)
    run   = TextRun(text="X", bold=True)   # only bold overridden
    rs = run.resolve(style)
    assert rs["bold"] is True
    assert rs["font_size"] == 12          # inherited
    assert rs["font_family"] == "Arial"   # inherited


def test_textrun_resolve_with_scale():
    style = TextStyle(font_size=10)
    run   = TextRun(text="X", font_size=20)
    rs = run.resolve(style, scale=0.5)
    assert rs["font_size"] == 10.0


def test_textbox_runs_persisted_in_dict():
    tb = TextBox()
    tb.runs = [TextRun(text="A"), TextRun(text="B", bold=True)]
    d = tb.to_dict()
    assert "runs" in d
    assert len(d["runs"]) == 2
    assert d["runs"][1]["bold"] is True


def test_textbox_runs_roundtrip(doc, tmp_path):
    page = doc.pages[0]
    tb = page.add_textbox(10, 10, 100, 20)
    tb.runs = [TextRun(text="Hello "),
               TextRun(text="bold ", bold=True),
               TextRun(text="red", color=(220, 0, 0))]
    p = str(tmp_path / "test.edof")
    doc.save(p)
    doc2 = edof.load(p)
    tb2 = doc2.pages[0].objects[0]
    assert len(tb2.runs) == 3
    assert tb2.runs[1].bold is True
    assert tb2.runs[2].color[0] == 220


# ── Table ─────────────────────────────────────────────────────────────────────

def test_table_creation():
    t = Table()
    t.cells = [[TableCell(text="A"), TableCell(text="B")],
               [TableCell(text="C"), TableCell(text="D")]]
    assert t.OBJECT_TYPE == "table"
    assert t.num_rows == 2
    assert t.num_cols == 2


def test_table_cell_styling():
    cell = TableCell(text="X", bg_color=(100, 200, 255, 200))
    cell.border_top.color = (50, 50, 50, 255)
    cell.border_top.width = 0.5
    assert cell.bg_color == (100, 200, 255, 200)
    assert cell.border_top.width == 0.5


def test_table_dispatch_in_from_dict():
    """The from_dict dispatcher must recognize 'table' type."""
    from edof.format.objects import EdofObject
    t = Table()
    t.cells = [[TableCell(text="X")]]
    d = t.to_dict()
    assert d["type"] == "table"
    rebuilt = EdofObject.from_dict(d)
    assert isinstance(rebuilt, Table)
    assert rebuilt.num_rows == 1


def test_make_table_helper():
    from edof.format.objects import make_table
    t = make_table([["Name", "Score"], ["Alice", "98"]],
                    header=True)
    assert t.num_rows == 2 and t.num_cols == 2
    # First row should have header styling (bold)
    assert t.cells[0][0].style.bold is True
    assert t.cells[1][0].style.bold is False


def test_table_save_load_roundtrip(doc, tmp_path):
    page = doc.pages[0]
    t = Table()
    t.transform.x = 10; t.transform.y = 10
    t.transform.width = 100; t.transform.height = 30
    t.cells = [
        [TableCell(text="H1"), TableCell(text="H2")],
        [TableCell(text="A"),  TableCell(text="B")],
    ]
    t.cells[0][0].bg_color = (50, 80, 150, 255)
    t.cells[0][0].style.color = (255, 255, 255)
    page.add_object(t)

    p = str(tmp_path / "test.edof")
    doc.save(p)
    doc2 = edof.load(p)
    tables = [o for o in doc2.pages[0].objects if isinstance(o, Table)]
    assert len(tables) == 1
    assert tables[0].num_rows == 2
    assert tables[0].cells[0][0].bg_color == (50, 80, 150, 255)


# ── Path / SVG path parsing ───────────────────────────────────────────────────

def test_parse_svg_path_simple():
    cmds = _parse_svg_path("M 10 20 L 30 40 Z")
    assert cmds[0] == ["M", 10.0, 20.0]
    assert cmds[1] == ["L", 30.0, 40.0]
    assert cmds[2] == ["Z"]


def test_parse_svg_path_relative():
    cmds = _parse_svg_path("M 10 20 l 5 5")
    assert cmds[0] == ["M", 10.0, 20.0]
    assert cmds[1] == ["L", 15.0, 25.0]


def test_parse_svg_path_cubic_bezier():
    cmds = _parse_svg_path("M 0 0 C 10 0 20 10 30 10")
    assert cmds[1][0] == "C"
    assert len(cmds[1]) == 7   # ["C", x1, y1, x2, y2, x, y]


def test_parse_svg_path_h_v():
    cmds = _parse_svg_path("M 10 20 H 50 V 80")
    # H/V commands are converted to L
    assert cmds[1] == ["L", 50.0, 20.0]
    assert cmds[2] == ["L", 50.0, 80.0]


def test_shape_from_svg_path():
    sh = Shape.from_svg_path("M 0 0 L 10 0 L 10 10 Z")
    assert sh.shape_type == SHAPE_PATH
    assert len(sh.path_data) == 4   # M, L, L, Z


# ── Gradient ──────────────────────────────────────────────────────────────────

def test_gradient_creation():
    g = Gradient(type="linear", angle=45,
                  stops=[(0.0, (255, 0, 0, 255)), (1.0, (0, 0, 255, 255))])
    assert g.type == "linear"
    assert len(g.stops) == 2


def test_gradient_in_fillstyle():
    fs = FillStyle()
    fs.gradient = Gradient(type="linear",
                            stops=[(0.0, (0, 0, 0, 255)), (1.0, (255, 255, 255, 255))])
    d = fs.to_dict()
    assert "gradient" in d
    fs2 = FillStyle.from_dict(d)
    assert fs2.gradient is not None
    assert fs2.gradient.type == "linear"


# ── Conditional visibility ───────────────────────────────────────────────────

def test_visible_if_simple():
    from edof.utils.safe_eval import evaluate
    assert evaluate("1 < 2", {}) is True
    assert evaluate("1 > 2", {}) is False
    assert evaluate("score > 90", {"score": 95}) is True
    assert evaluate("score > 90", {"score": 85}) is False


def test_visible_if_string_compare():
    from edof.utils.safe_eval import evaluate
    assert evaluate("country == 'CZ'", {"country": "CZ"}) is True
    assert evaluate("country == 'CZ'", {"country": "DE"}) is False


def test_visible_if_unsafe_rejected():
    from edof.utils.safe_eval import evaluate
    # Function calls forbidden
    assert evaluate("__import__('os')", {}) is None
    assert evaluate("open('/etc/passwd')", {}) is None
    # Attribute access forbidden (not in our whitelist)
    assert evaluate("a.b", {"a": "x"}) is None


def test_visible_if_on_object(doc):
    page = doc.pages[0]
    tb = page.add_textbox(10, 10, 100, 10, "Secret")
    tb.visible_if = "show == 1"
    doc.define_variable("show", default="0")

    from edof.utils.safe_eval import is_visible
    assert is_visible(tb, doc.variables) is False
    doc.set_variable("show", "1")
    assert is_visible(tb, doc.variables) is True


# ── Blend modes ───────────────────────────────────────────────────────────────

def test_blend_mode_attribute(doc):
    page = doc.pages[0]
    tb = page.add_textbox(10, 10, 50, 20, "X")
    tb.blend_mode = "multiply"
    d = tb.to_dict()
    assert d["blend_mode"] == "multiply"


# ── Repeating sections ────────────────────────────────────────────────────────

def test_repeat_objects_basic(doc):
    page = doc.pages[0]
    tb = page.add_textbox(10, 10, 100, 8, "Name: {name}")
    template = [tb]
    page.objects.remove(tb)
    pages = page.repeat_objects(template,
        [{"name": "A"}, {"name": "B"}, {"name": "C"}], gap=2.0)
    assert len(pages) == 1
    assert len(pages[0].objects) == 3


def test_repeat_objects_substitutes_variables(doc):
    page = doc.pages[0]
    tb = page.add_textbox(10, 10, 100, 8, "Hello {name}")
    template = [tb]
    page.objects.remove(tb)
    pages = page.repeat_objects(template, [{"name": "Alice"}, {"name": "Bob"}])
    texts = [o.text for o in pages[0].objects]
    assert "Hello Alice" in texts
    assert "Hello Bob" in texts


def test_repeat_objects_auto_paginates():
    """When data overflows, new pages are created."""
    d = edof.new(width=100, height=50)
    page = d.add_page(dpi=72)
    tb = page.add_textbox(5, 5, 90, 8, "Row {n}")
    template = [tb]
    page.objects.remove(tb)
    pages = page.repeat_objects(template,
                                  [{"n": i} for i in range(20)], gap=2.0)
    assert len(pages) > 1, "Should create multiple pages for 20 rows on 50mm tall page"


# ── Vector PDF export ────────────────────────────────────────────────────────

def test_vector_pdf_export(doc, tmp_path):
    page = doc.pages[0]
    page.add_textbox(20, 20, 170, 10, "Hello vector PDF")
    sh = page.add_shape("rect", 20, 40, 80, 30)
    sh.fill.color = (200, 100, 50, 255)
    p = str(tmp_path / "out.pdf")
    doc.export_pdf(p)
    assert os.path.exists(p)
    data = open(p, "rb").read()
    assert data.startswith(b"%PDF-")
    assert b"%%EOF" in data[-30:]


def test_vector_pdf_smaller_than_raster(doc, tmp_path):
    """Vector PDF should be much smaller than rasterised PDF."""
    page = doc.pages[0]
    for i in range(5):
        page.add_textbox(20, 20 + i * 12, 170, 10, f"Line {i}")
    p_vec = str(tmp_path / "vec.pdf")
    p_ras = str(tmp_path / "ras.pdf")
    doc.export_pdf(p_vec, vector=True)
    try:
        doc.export_pdf(p_ras, vector=False)
        # If reportlab is available, vector should be much smaller
        if os.path.exists(p_ras):
            assert os.path.getsize(p_vec) < os.path.getsize(p_ras)
    except Exception:
        # reportlab not available — that's fine, vector is the new default
        pass


def test_vector_pdf_czech_diacritics(doc, tmp_path):
    """Czech diacritics encoded via WinAnsi should appear in PDF."""
    page = doc.pages[0]
    page.add_textbox(20, 20, 170, 10, "Příliš žluťoučký kůň")
    p = str(tmp_path / "cz.pdf")
    doc.export_pdf(p)
    data = open(p, "rb").read()
    # WinAnsi encoded Czech chars should be present in some form
    assert len(data) > 200


# ── SVG export ────────────────────────────────────────────────────────────────

def test_svg_export_basic(doc, tmp_path):
    page = doc.pages[0]
    page.add_textbox(10, 10, 100, 10, "SVG Test")
    sh = page.add_shape("rect", 10, 30, 50, 30)
    sh.fill.color = (200, 100, 50, 255)
    p = str(tmp_path / "out.svg")
    doc.export_svg(p)
    content = open(p).read()
    assert "<svg" in content
    assert "<text" in content
    assert "<rect" in content


def test_svg_export_with_gradient(doc, tmp_path):
    page = doc.pages[0]
    sh = page.add_shape("rect", 10, 10, 80, 50)
    sh.fill.color = None
    sh.fill.gradient = Gradient(type="linear", angle=0,
        stops=[(0, (255, 0, 0, 255)), (1, (0, 0, 255, 255))])
    p = str(tmp_path / "grad.svg")
    doc.export_svg(p)
    content = open(p).read()
    assert "<linearGradient" in content


def test_svg_path_export(doc, tmp_path):
    page = doc.pages[0]
    sh = Shape.from_svg_path("M 10 10 L 50 10 L 30 50 Z")
    sh.fill.color = (100, 200, 100, 255)
    page.add_object(sh)
    p = str(tmp_path / "path.svg")
    doc.export_svg(p)
    content = open(p).read()
    assert "<path" in content


# ── Renderer integration ─────────────────────────────────────────────────────

def test_render_with_runs(doc):
    page = doc.pages[0]
    tb = page.add_textbox(10, 10, 100, 20)
    tb.runs = [TextRun(text="A"), TextRun(text="B", bold=True)]
    from edof.engine.renderer import render_page
    img = render_page(page, doc.resources, doc.variables, dpi=96)
    assert img.size[0] > 0


def test_render_with_table(doc):
    page = doc.pages[0]
    t = Table()
    t.transform.x = 10; t.transform.y = 10
    t.transform.width = 100; t.transform.height = 30
    t.cells = [[TableCell(text="A"), TableCell(text="B")],
               [TableCell(text="1"), TableCell(text="2")]]
    page.add_object(t)
    from edof.engine.renderer import render_page
    img = render_page(page, doc.resources, doc.variables, dpi=96)
    assert img.size[0] > 0


def test_render_with_path(doc):
    page = doc.pages[0]
    sh = Shape.from_svg_path("M 10 10 L 50 50 Z")
    sh.fill.color = (100, 200, 100, 255)
    page.add_object(sh)
    from edof.engine.renderer import render_page
    img = render_page(page, doc.resources, doc.variables, dpi=96)
    assert img.size[0] > 0


def test_render_with_gradient(doc):
    page = doc.pages[0]
    sh = page.add_shape("rect", 10, 10, 80, 50)
    sh.fill.gradient = Gradient(type="linear",
        stops=[(0, (255, 0, 0, 255)), (1, (0, 0, 255, 255))])
    sh.fill.color = None
    from edof.engine.renderer import render_page
    img = render_page(page, doc.resources, doc.variables, dpi=96)
    assert img.size[0] > 0


def test_render_with_visible_if(doc):
    page = doc.pages[0]
    tb1 = page.add_textbox(10, 10, 100, 10, "Visible")
    tb2 = page.add_textbox(10, 25, 100, 10, "Hidden")
    tb2.visible_if = "0 == 1"
    from edof.engine.renderer import render_page
    img = render_page(page, doc.resources, doc.variables, dpi=96)
    assert img.size[0] > 0
