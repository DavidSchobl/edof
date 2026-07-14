"""v4.4.1: hyperlinks (external + in-document anchors), document link style,
hover tint, editor + viewer behaviour. Headless (offscreen)."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from edof.format.styles import (TextRun, TextStyle, DEFAULT_LINK_STYLE,
                                set_active_link_style, active_link_style)
from edof import Document

_APP = None


def _ensure_app():
    global _APP
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])


def teardown_function(_fn):
    set_active_link_style(None)          # don't leak style between tests


def test_run_link_anchor_roundtrip():
    r = TextRun(text="klikni", link="https://example.com",
                anchor="anch_abc123", anchor_name="target A")
    r2 = TextRun.from_dict(r.to_dict())
    assert r2.link == "https://example.com"
    assert r2.anchor == "anch_abc123"
    assert r2.anchor_name == "target A"
    # plain run stays clean
    assert "link" not in TextRun(text="x").to_dict()


def test_document_link_style_roundtrip():
    from edof.format.serializer import EdofSerializer
    doc = Document()
    doc.add_page(width=100, height=50)
    doc.link_style = {"color": (200, 0, 0, 255), "underline": False,
                      "hover_color": (250, 100, 100, 255)}
    doc2 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(doc))
    assert tuple(doc2.link_style["color"]) == (200, 0, 0, 255)
    assert doc2.link_style["underline"] is False
    assert tuple(doc2.link_style["hover_color"]) == (250, 100, 100, 255)
    # no link style -> key stays None and default applies
    doc3 = EdofSerializer.from_bytes(EdofSerializer.to_bytes(Document()))
    assert getattr(doc3, "link_style", None) is None


def test_resolve_link_defaults_and_overrides():
    st = TextStyle()
    plain = TextRun(text="a").resolve(st)
    link = TextRun(text="a", link="https://x.cz").resolve(st)
    assert link["color"] == DEFAULT_LINK_STYLE["color"]
    assert link["underline"] is True
    assert plain["color"] != DEFAULT_LINK_STYLE["color"]
    # explicit run formatting wins over the link style
    styled = TextRun(text="a", link="https://x.cz",
                     color=(0, 128, 0, 255), underline=False).resolve(st)
    assert styled["color"] == (0, 128, 0, 255)
    assert styled["underline"] is False
    # document style change re-colours links without overrides
    set_active_link_style({"color": (200, 0, 0, 255), "underline": False})
    link2 = TextRun(text="a", link="https://x.cz").resolve(st)
    assert link2["color"] == (200, 0, 0, 255)
    assert link2["underline"] is False


def test_editor_link_api_and_anchor():
    _ensure_app()
    import edof._apps.editor as E
    doc = Document()
    page = doc.add_page(width=140, height=60)
    tb = page.add_textbox(10, 10, 120, 20, "navstiv web dneska")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv._start_inline(tb)
    ied = cv._inline_widget
    ied._anchor = 8; ied._cursor = 11          # "web"
    assert ied.set_link_on_selection("https://example.com")
    assert ied.selection_link() == "https://example.com"
    ied.sync_to_tb_silent()
    assert any(getattr(r, "link", None) == "https://example.com"
               for r in tb.runs)
    # anchor on another span
    ied._anchor = 12; ied._cursor = 18         # "dneska"
    aid = ied.make_anchor_from_selection("cil")
    assert aid and aid.startswith("anch_")
    ied.sync_to_tb_silent()
    spans = [r for r in tb.runs if getattr(r, "anchor", None) == aid]
    assert spans and spans[0].anchor_name == "cil"
    # remove link
    ied._anchor = 8; ied._cursor = 11
    ied.set_link_on_selection(None)
    assert ied.selection_link() is None


def test_follow_anchor_navigates_pages():
    _ensure_app()
    import edof._apps.editor as E
    doc = Document()
    p1 = doc.add_page(width=140, height=60)
    p2 = doc.add_page(width=140, height=60)
    p1.add_textbox(10, 10, 120, 20, "start")
    tb2 = p2.add_textbox(10, 10, 120, 20, "kapitola dve")
    tb2.runs = [TextRun(text="kapitola "),
                TextRun(text="dve", anchor="anch_kap2", anchor_name="Kap 2")]
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    anchors = cv.collect_anchors()
    assert "anch_kap2" in anchors
    assert anchors["anch_kap2"][1] == 1
    assert cv.follow_anchor("anch_kap2")
    assert cv._page_idx == 1
    ied = cv._inline_widget
    assert ied is not None
    a, b = sorted((ied._anchor, ied._cursor))
    assert "".join(r.text for r in ied._runs)[a:b] == "dve"
    assert not cv.follow_anchor("anch_missing")


def test_hover_tint_changes_render():
    _ensure_app()
    import edof._apps.editor as E
    doc = Document()
    page = doc.add_page(width=140, height=60)
    tb = page.add_textbox(10, 10, 120, 20, "navstiv web dneska")
    tb.runs = [TextRun(text="navstiv "),
               TextRun(text="web", link="https://example.com"),
               TextRun(text=" dneska")]
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv._start_inline(tb)
    ied = cv._inline_widget
    ied._ensure_render()
    base = ied._img.copy() if getattr(ied, "_img", None) else None
    ied._hover_link = "https://example.com"
    ied._layout = None
    ied._ensure_render()
    hovered = ied._img.copy() if getattr(ied, "_img", None) else None
    if base is not None and hovered is not None:
        import PIL.ImageChops as IC
        assert IC.difference(base.convert("RGB"),
                             hovered.convert("RGB")).getbbox() is not None


def test_link_render_is_blue_and_batch_survives():
    """Link runs render with the link colour in the page render, and the link
    attribute survives a batch text apply (descriptor sets run.text only)."""
    from edof.engine.renderer import render_document
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    doc = Document()
    page = doc.add_page(width=100, height=30)
    tb = page.add_textbox(5, 5, 90, 20, "WWWW")
    tb.runs = [TextRun(text="WWWW", link="https://example.com",
                       rid="ridlnk000001", var_name="lnk", font_size=8.0)]
    img = render_document(doc, dpi=96)[0].convert("RGB")
    colors = img.getcolors(1 << 20)
    lr, lg, lb = DEFAULT_LINK_STYLE["color"][:3]
    assert any(abs(c[0] - lr) < 30 and abs(c[1] - lg) < 30
               and abs(c[2] - lb) < 30
               for _n, c in colors), "link text should render blue-ish"
    cfg = doc.batch
    col = cfg.add_column(build_ref(page, tb), "run.text", "lnk", "text")
    col.run_id = "ridlnk000001"
    row = BatchRow(page_target=0, values={col.column_id: "MMMM"})
    assert apply_row_to_document(cfg, doc, row) == 1
    assert tb.runs[0].text == "MMMM"
    assert tb.runs[0].link == "https://example.com"


def test_viewer_link_hit_and_page_jump():
    _ensure_app()
    from edof._apps.viewer import EdofViewer
    from edof.engine.text_layout import layout_textbox
    doc = Document()
    p1 = doc.add_page(width=100, height=40)
    p2 = doc.add_page(width=100, height=40)
    tb = p1.add_textbox(5, 5, 90, 20, "skok")
    tb.runs = [TextRun(text="skok", link="#anch_x", font_size=8.0)]
    t2 = p2.add_textbox(5, 5, 90, 20, "cil")
    t2.runs = [TextRun(text="cil", anchor="anch_x")]
    vw = EdofViewer()
    vw._doc = doc
    vw._zoom_mode = "custom"; vw._zoom_factor = 1.0
    vw._do_render()
    dpi = float(getattr(vw, "_last_render_dpi", 96))
    lay = layout_textbox(tb, dpi)
    ch = next(c for line in lay.lines for c in line.chars
              if not getattr(c, "is_newline", False))
    from PyQt6.QtCore import QPointF
    pos = QPointF(ch.x + ch.w / 2.0, ch.line_top + ch.line_h / 2.0)
    assert vw._link_at_view_pos(pos) == "#anch_x"
    assert vw._handle_link_click(pos) is True
    assert vw._page_idx == 1


def test_canvas_link_hit_and_follow_in_basic_mode():
    """v4.4.0: Ctrl+click follows links directly on the canvas (no inline
    editing session needed), which is the basic-mode workflow."""
    _ensure_app()
    import edof._apps.editor as E
    from edof.engine.text_layout import layout_textbox
    doc = Document()                       # mode == "empty": basic mode
    p1 = doc.add_page(width=120, height=50)
    p2 = doc.add_page(width=120, height=50)
    tb = p1.add_textbox(10, 10, 100, 20, "skok jinam")
    tb.runs = [TextRun(text="skok", link="#anch_b1", font_size=8.0),
               TextRun(text=" jinam", font_size=8.0)]
    t2 = p2.add_textbox(10, 10, 100, 20, "cilova stranka")
    t2.runs = [TextRun(text="cilova stranka", anchor="anch_b1")]
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    lay = layout_textbox(tb, cv._dpi)
    ch = next(c for line in lay.lines for c in line.chars
              if not getattr(c, "is_newline", False))
    x = ch.x + ch.w / 2.0
    y = ch.line_top + ch.line_h / 2.0
    assert cv._link_at_scene_pos(x, y) == "#anch_b1"
    # a point in the non-link tail gives None
    last = [c for line in lay.lines for c in line.chars
            if not getattr(c, "is_newline", False)][-1]
    assert cv._link_at_scene_pos(last.x + last.w / 2.0,
                                 last.line_top + last.line_h / 2.0) is None
    # following the in-document link switches pages
    assert cv._follow_link_str("#anch_b1") is True
    assert cv._page_idx == 1
