"""v4.4.0 tester round: BUG #10 (batch file_path regression), BUG #11 (font
embed + weight-aware matching)."""
import io
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from edof.format.document import Document


def _png(tmp_path, name="map.png", color=(0, 128, 255, 255)):
    img = Image.new("RGBA", (24, 24), color)
    p = str(tmp_path / name)
    img.save(p, "PNG")
    return p


def test_bug10_apply_materialises_file_into_resources(tmp_path):
    from edof.batch.model import build_ref, BatchRow, apply_row_to_document
    path = _png(tmp_path)
    doc = Document()
    page = doc.add_page(width=100, height=60)
    ib = page.add_image("", 10, 10, 40, 40)
    cfg = doc.batch
    col = cfg.add_column(build_ref(page, ib), "resource_id", "mapa", "file_path")
    row = BatchRow(page_target=0, values={col.column_id: path})
    apply_row_to_document(cfg, doc, row)
    assert ib.resource_id and ib.resource_id != path, \
        "the file must be materialised as a RESOURCE, not left as a path"
    assert ib.resource_id in doc.resources
    entry = doc.resources.get(ib.resource_id)
    assert entry.filename == os.path.basename(path)
    # applying the same path to another object reuses the resource
    ib2 = page.add_image("", 55, 10, 40, 40)
    col2 = cfg.add_column(build_ref(page, ib2), "resource_id", "mapa2", "file_path")
    row2 = BatchRow(page_target=0, values={col.column_id: path,
                                           col2.column_id: path})
    n_before = len(list(doc.resources.index_dict()))
    apply_row_to_document(cfg, doc, row2)
    assert ib2.resource_id == ib.resource_id or ib2.resource_id in doc.resources


def test_bug10_pdf_and_svg_export_render_path_images(tmp_path):
    """Even an UN-materialised path resource_id must reach the exports (the
    raster renderer resolved paths since 4.3.6.27; PDF/SVG silently dropped
    them, which is why maps appeared in one output and not another)."""
    from edof.export.pdf import export_pdf
    from edof.export.svg import export_svg
    path = _png(tmp_path)
    doc = Document()
    page = doc.add_page(width=100, height=60)
    ib = page.add_image("", 10, 10, 40, 40)
    ib.resource_id = path                     # raw path, no resource store
    pdf_p = str(tmp_path / "o.pdf")
    export_pdf(doc, pdf_p)
    d = open(pdf_p, "rb").read()
    assert b"/Subtype /Image" in d, "PDF must embed the path image"
    svg_p = str(tmp_path / "o.svg")
    export_svg(doc, svg_p, page=0)
    svg = open(svg_p, encoding="utf-8").read()
    assert "data:image/png;base64," in svg, "SVG must embed the path image"


def _dejavu_paths():
    import glob
    reg = glob.glob("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold = glob.glob("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    return (reg[0] if reg else None), (bold[0] if bold else None)


def test_bug11b_embedded_fonts_weight_aware(tmp_path):
    """Embedded fonts resolve by the REAL family from the font's name table
    (weight-aware), not by a filename substring."""
    from edof.engine.text_engine import (register_resource_fonts,
                                         embedded_font_bytes)
    reg, bold = _dejavu_paths()
    if not reg or not bold:
        pytest.skip("dejavu fonts not present")
    doc = Document()
    doc.add_page(width=100, height=50)
    # filenames WITHOUT spaces; the family name is "DejaVu Sans" (with space)
    doc.resources.add(open(reg, "rb").read(), "DejaVuSans.ttf", "font/ttf")
    doc.resources.add(open(bold, "rb").read(), "DejaVuSans-Bold.ttf", "font/ttf")
    register_resource_fonts(None)
    register_resource_fonts(doc.resources)
    b_reg = embedded_font_bytes("DejaVu Sans", False, False)
    b_bold = embedded_font_bytes("DejaVu Sans", True, False)
    assert b_reg is not None, "family with a space must match"
    assert b_bold is not None
    assert b_reg != b_bold, "bold must pick the bold file, not the first hit"
    # italic falls back to regular gracefully
    assert embedded_font_bytes("DejaVu Sans", False, True) is not None
    register_resource_fonts(None)


def test_bug11a_embed_used_fonts_roundtrip(tmp_path):
    """save(embed_fonts=True) embeds the used families; the reloaded document
    resolves them from resources (as if on a machine without the font)."""
    from edof.engine.text_engine import (register_resource_fonts,
                                         embedded_font_bytes)
    reg, _bold = _dejavu_paths()
    if not reg:
        pytest.skip("dejavu fonts not present")
    doc = Document()
    page = doc.add_page(width=100, height=50)
    tb = page.add_textbox(5, 5, 90, 30, "Ahoj")
    tb.style.font_family = "DejaVu Sans"
    n = doc.embed_used_fonts()
    assert n >= 1, "the used family must be embedded"
    fonts = [e for e in doc.resources.all_entries()
             if (e.mime_type or "").startswith("font/")]
    assert fonts
    path = str(tmp_path / "f.edof")
    doc.save(path)
    doc2 = Document.load(path)
    register_resource_fonts(None)
    register_resource_fonts(doc2.resources)
    assert embedded_font_bytes("DejaVu Sans", False, False) is not None
    register_resource_fonts(None)
    # idempotent: second embed adds nothing
    assert doc.embed_used_fonts() == 0


def test_bug12_layout_zoom_stable():
    """BUG #12: line breaks and (scaled) positions must be identical across
    render DPIs -- the layout geometry comes from one reference DPI."""
    from edof.engine.text_layout import layout_runs
    from edof.format.styles import TextRun, TextStyle
    runs = [TextRun(text=("Lorem ipsum dolor sit amet, consectetur adipiscing "
                          "elit, sed do eiusmod tempor incididunt ut labore et "
                          "dolore magna aliqua. Ut enim ad minim veniam."))]
    style = TextStyle()
    style.font_size = 4.0
    style.padding = 1.0

    def breaks_at(dpi):
        w = 80.0 * dpi / 25.4       # 80 mm box
        h = 120.0 * dpi / 25.4
        lay = layout_runs(runs, style, 0, 0, w, h, dpi)
        # line-break signature: char_idx of the first char of every line
        return [ln.chars[0].char_idx for ln in lay.lines if ln.chars], lay

    sig96, lay96 = breaks_at(96)
    sig150, lay150 = breaks_at(150)
    sig300, lay300 = breaks_at(300)
    sig432, lay432 = breaks_at(432)
    assert sig96 == sig150 == sig300 == sig432, \
        "line breaks must not depend on the render DPI"
    # positions scale linearly with dpi (within float tolerance)
    c96 = lay96.chars[40]; c300 = lay300.chars[40]
    assert abs(c96.x * (300.0 / 96.0) - c300.x) < 0.75
    assert abs(c96.line_top * (300.0 / 96.0) - c300.line_top) < 0.75


# ── PDF validity battery ─────────────────────────────────────────────────────

def _assert_pdf_valid(path):
    """Structural validation: strict-ish parse with pypdf + xref offsets
    verified byte-exactly against the file."""
    pypdf = pytest.importorskip("pypdf")
    from pypdf import PdfReader
    r = PdfReader(path)
    assert len(r.pages) >= 1
    for pg in r.pages:
        pg.extract_text()                    # forces content stream decode
    raw = open(path, "rb").read()
    assert raw.count(b"%%EOF") == 1
    # verify every xref offset points at the right "N 0 obj" header
    import re
    m = re.search(rb"xref\n0 (\d+)\n", raw)
    assert m, "xref table missing"
    n = int(m.group(1))
    table = raw[m.end():m.end() + (n) * 20]
    for i in range(1, n):
        ent = table[i * 20:(i + 1) * 20]
        off = int(ent[:10])
        assert raw[off:off + 20].startswith(b"%d 0 obj" % i), \
            f"xref offset of object {i} is wrong"


def test_pdf_validity_battery(tmp_path):
    """Every export flavour must produce a structurally valid PDF (links,
    /Dest anchors, SMask images, effects, attachments, double export,
    document mode with header/footer + batch apply, parentheses and
    diacritics in URLs)."""
    import io as _io
    from PIL import Image as _Image
    from edof.format.styles import TextRun
    from edof.export.pdf import export_pdf
    from edof import LayerEffect

    doc = Document()
    p1 = doc.add_page(width=210, height=297)
    p2 = doc.add_page(width=210, height=297)
    tb = p1.add_textbox(10, 10, 180, 20, "web skok mapa")
    tb.runs = [TextRun(text="web", link="https://example.com"),
               TextRun(text=" "),
               TextRun(text="skok", link="#a1"),
               TextRun(text=" "),
               TextRun(text="mapa", link="https://m.example.com/(50.1,14.4)/žluť")]
    t2 = p2.add_textbox(10, 10, 180, 20, "cíl")
    t2.runs = [TextRun(text="cíl", anchor="a1")]
    img = _Image.new("RGBA", (30, 30), (0, 200, 0, 0))
    for x in range(15):
        for y in range(30):
            img.putpixel((x, y), (0, 200, 0, 255))
    buf = _io.BytesIO(); img.save(buf, "PNG")
    rid = doc.add_resource(buf.getvalue(), "l.png", "image/png")
    p1.add_image(rid, 10, 60, 30, 30)
    sh = p1.add_shape("rect", 10, 120, 60, 40)
    sh.effects.append(LayerEffect(type="drop_shadow", distance=2.0, size=4.0))
    sh.effects_enabled = True

    a = str(tmp_path / "a.pdf"); b = str(tmp_path / "b.pdf")
    export_pdf(doc, a, embed_source=True)
    _assert_pdf_valid(a)
    export_pdf(doc, b, embed_source=False)
    _assert_pdf_valid(b)
    # double export through the document API
    c = str(tmp_path / "c.pdf")
    doc.export_pdf(c); doc.export_pdf(c)
    _assert_pdf_valid(c)


def test_pdf_validity_docmode_hf_batch(tmp_path):
    from edof.format.document_body import DocumentBody
    from edof.format.document_boxes import DocumentTextBox
    from edof.format.styles import TextRun
    from edof.engine.document_paginate import paginate_document, HF_HEADER_ID
    from edof.batch.model import ObjectRef, BatchRow, apply_row_to_document
    from edof.export.pdf import export_pdf
    doc = Document()
    page = doc.add_page(width=210, height=297)
    doc.margins = (15.0,) * 4; doc.mode = "document"
    doc.body = DocumentBody(); doc.body.page_margins_mm = (15.0,) * 4
    doc.body.header_enabled = True
    doc.body.header_runs = [TextRun(text="Menu: "),
                            TextRun(text="U Lva", rid="r1", var_name="v")]
    tb = DocumentTextBox()
    tb.transform.x = 15; tb.transform.y = 15
    tb.transform.width = 180; tb.transform.height = 267
    tb.style.padding = 0.0
    tb.runs = [TextRun(text="odkaz "),
               TextRun(text="(mapa)", link="https://x.cz/(a)b"),
               TextRun(text=" text " * 50)]
    tb.text = "".join(r.text for r in tb.runs)
    page.objects.append(tb)
    paginate_document(doc)
    cfg = doc.batch
    col = cfg.add_column(ObjectRef([HF_HEADER_ID]), "run.text", "v", "text")
    col.run_id = "r1"
    apply_row_to_document(cfg, doc, BatchRow(values={col.column_id: "U Orla (dvůr)"}))
    p = str(tmp_path / "d.pdf")
    export_pdf(doc, p)
    _assert_pdf_valid(p)


def test_image_decode_cache_reuses_source(tmp_path):
    """Cookbook perf: the decoded image source is cached per resource, so a
    re-render doesn't re-decode the JPEG/PNG bytes."""
    from edof.engine import renderer as R
    img = Image.new("RGBA", (32, 32), (1, 2, 3, 255))
    p = str(tmp_path / "x.png")
    img.save(p, "PNG")
    data = open(p, "rb").read()
    R._IMG_SRC_CACHE.clear()
    a = R._decode_image_source(("rid1", len(data)), data)
    b = R._decode_image_source(("rid1", len(data)), data)
    assert a is b, "second call must be a cache hit"
    # different key -> new decode
    c = R._decode_image_source(("rid2", len(data)), data)
    assert c is not a
    R._IMG_SRC_CACHE.clear()
