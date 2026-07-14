"""v4.4.0 beta-review fixes: safe_eval DoS, recovery key normalization,
PDF double save, docx tri-state, RTF unicode/ul0, QR recolor, table
variable substitution."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from edof import Document


# ── #1 safe_eval DoS ─────────────────────────────────────────────────────────

def test_safe_eval_rejects_huge_pow_and_repeat():
    import time
    from edof.utils.safe_eval import evaluate
    t0 = time.time()
    assert evaluate("9**9**9", {}) is None
    assert evaluate('"x"*10**9', {}) is None
    assert evaluate('"x"*999999', {}) is None
    assert time.time() - t0 < 1.0, "must reject instantly, not compute"
    # sane expressions still work
    assert evaluate("2**10 == 1024", {}) is True
    assert evaluate('"ab"*3 == "ababab"', {}) is True
    assert evaluate("a > 3", {"a": 5}) is True
    assert evaluate("price * 2 < 100", {"price": 20}) is True


# ── #3 recovery key normalization ────────────────────────────────────────────

def test_recovery_key_any_form_unlocks():
    crypto = pytest.importorskip("cryptography")  # noqa: F841
    import os as _os
    from edof.crypto.encryption import (generate_recovery_key,
                                        create_recovery_slot,
                                        unwrap_with_recovery_key)
    ck = _os.urandom(32)
    key = generate_recovery_key()
    slot = create_recovery_slot(key, ck)
    assert unwrap_with_recovery_key([slot], key) == ck
    assert unwrap_with_recovery_key([slot], key.replace("-", "")) == ck
    assert unwrap_with_recovery_key([slot], key.replace("-", "").lower()) == ck
    assert unwrap_with_recovery_key([slot], key.lower()) == ck
    assert unwrap_with_recovery_key([slot], "NOPE") is None


# ── #4 PDF double save ───────────────────────────────────────────────────────

def test_pdf_writer_save_is_idempotent(tmp_path):
    from edof.export.pdf_writer import PdfWriter
    w = PdfWriter()
    pg = w.add_page(210, 297)
    pg.text(20, 30, "Ahoj PDF")
    p1 = str(tmp_path / "a1.pdf"); p2 = str(tmp_path / "a2.pdf")
    w.save(p1)
    w.save(p2)
    d1 = open(p1, "rb").read(); d2 = open(p2, "rb").read()
    assert d1 == d2
    assert d2.count(b"/Type /Catalog") == 1
    assert d2.count(b"%%EOF") == 1


# ── #5 docx bold/italic/underline tri-state ─────────────────────────────────

def test_docx_roundtrip_keeps_explicit_false(tmp_path):
    pytest.importorskip("docx")
    from edof.interop.docx_io import export_docx, import_docx
    from edof.format.styles import TextRun
    from edof.format.document_body import DocumentBody, Paragraph
    doc = Document()
    doc.add_page(width=210, height=297)
    doc.mode = "document"
    doc.body = DocumentBody()
    doc.body.paragraphs = [Paragraph(runs=[
        TextRun(text="tucne ", bold=True),
        TextRun(text="vypnute", bold=False),      # explicitly NOT bold
        TextRun(text=" zdedene"),                 # inherit (None)
    ])]
    path = str(tmp_path / "t.docx")
    export_docx(doc, path)
    doc2, _report = import_docx(path)
    runs = [r for p in doc2.body.paragraphs for r in p.runs if (r.text or "").strip()]
    by_text = {r.text.strip(): r for r in runs}
    assert by_text["tucne"].bold is True
    assert by_text["vypnute"].bold is False, \
        "explicit False must survive the round-trip (used to collapse to None)"


# ── #6 RTF unicode + ul0 ─────────────────────────────────────────────────────

def test_rtf_ucn_skip_and_ul0(tmp_path):
    from edof.utils.rtf import _decode_rtf_unicode, import_rtf
    t = _decode_rtf_unicode(r"{\uc1 a \u269\'9e b \u268 ? c}")
    assert "č" in t and "ž" not in t     # č present, ž fallback eaten
    assert "Č" in t and "?" not in t
    assert _decode_rtf_unicode(r"caf\'e9") == "café"
    rtf = (r"{\rtf1\ansi\deff0\uc1 {\fonttbl{\f0 Arial;}}\pard "
           r"{\ul podtrzeno}\ul0 dal \u269\'9e konec\par tail\par"
           r"\page next page\par}")
    path = str(tmp_path / "t.rtf")
    open(path, "w").write(rtf)
    doc = import_rtf(path)
    runs = [r for pg in doc.pages for o in pg.objects
            for r in (getattr(o, "runs", None) or [])]
    txt = "".join(r.text for r in runs)
    assert "č" in txt and "ž" not in txt
    ul = {r.text.strip(): bool(r.underline) for r in runs if r.text.strip()}
    assert ul.get("podtrzeno") is True
    assert any(("dal" in k and not v) for k, v in ul.items()), \
        r"\ul0 must turn underline OFF"
    assert len(doc.pages) == 2                     # \page honoured


# ── QR recolor (perf rewrite must keep output correct) ──────────────────────

def test_qr_recolor_colors_correct():
    pytest.importorskip("qrcode")
    from edof.engine.renderer import render_document
    doc = Document()
    page = doc.add_page(width=60, height=60)
    qr = page.add_qrcode(5, 5, 50, 50, "https://example.com")
    qr.fg_color = (10, 20, 200, 255)
    qr.bg_color = (250, 240, 10, 255)
    img = render_document(doc, dpi=96)[0].convert("RGB")
    colors = {c for _n, c in img.getcolors(1 << 20)}
    assert (10, 20, 200) in colors
    assert (250, 240, 10) in colors
    # old black/white must be fully recoloured
    assert (0, 0, 0) not in colors


# ── table {variable} substitution still works after the precompute ───────────

def test_table_variable_substitution_renders(tmp_path):
    from edof.engine.renderer import render_document
    from edof.export.svg import export_svg
    from edof.format.objects import Table, TableCell
    doc = Document()
    page = doc.add_page(width=100, height=60)
    tb = Table()
    tb.transform.x = 5; tb.transform.y = 5
    tb.transform.width = 90; tb.transform.height = 40
    tb.cells = [[TableCell(text="Cena: {price} Kc")]]
    tb.row_heights = [0]; tb.col_widths = [0]
    page.objects.append(tb)
    doc.variables.set("price", "42")
    render_document(doc, dpi=96)          # smoke: renders without error
    path = str(tmp_path / "t.svg")
    export_svg(doc, path, page=0)
    svg = open(path, encoding="utf-8").read()
    assert "{price}" not in svg and "42" in svg


# ── round 2: link export + URL validation + PDF fixes ───────────────────────

def test_validate_link_whitelist():
    from edof.utils.links import validate_link
    for bad in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x",
                " ", "", None, "not a url", "data:text/html,x", "#"):
        assert validate_link(bad) is None, bad
    assert validate_link("https://example.com") == "https://example.com"
    assert validate_link("mailto:a@b.cz") == "mailto:a@b.cz"
    assert validate_link("#anch_1") == "#anch_1"
    assert validate_link("example.com/x") == "https://example.com/x"


def test_editor_refuses_unsafe_link():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    global _APP2
    _APP2 = QApplication.instance() or QApplication([])
    import edof._apps.editor as E
    doc = Document()
    page = doc.add_page(width=120, height=50)
    tb = page.add_textbox(10, 10, 100, 20, "klikni sem")
    cv = E.EdofCanvas(); cv.set_document(doc, 0)
    cv._start_inline(tb)
    ied = cv._inline_widget
    ied._anchor = 0; ied._cursor = 6
    assert ied.set_link_on_selection("javascript:alert(1)") is False
    assert ied.selection_link() is None
    assert ied.set_link_on_selection("example.com") is True
    assert ied.selection_link() == "https://example.com"


def test_pdf_export_emits_link_annotations(tmp_path):
    from edof.export.pdf import export_pdf
    from edof.format.styles import TextRun
    doc = Document()
    p1 = doc.add_page(width=120, height=60)
    p2 = doc.add_page(width=120, height=60)
    tb = p1.add_textbox(10, 10, 100, 20, "navstiv web a skoc zly")
    tb.runs = [TextRun(text="navstiv "),
               TextRun(text="web", link="https://example.com"),
               TextRun(text=" a "),
               TextRun(text="skoc", link="#anch_t1"),
               TextRun(text=" zly", link="javascript:alert(1)")]
    t2 = p2.add_textbox(10, 10, 100, 20, "cil")
    t2.runs = [TextRun(text="cil", anchor="anch_t1")]
    path = str(tmp_path / "links.pdf")
    export_pdf(doc, path)
    d = open(path, "rb").read()
    assert b"/Subtype /Link" in d
    assert b"/URI (https://example.com)" in d
    assert b"/Dest [" in d and b"/Annots [" in d
    assert b"javascript" not in d, "unsafe scheme must never reach the PDF"


def test_svg_export_wraps_links(tmp_path):
    from edof.export.svg import export_svg
    from edof.format.styles import TextRun
    doc = Document()
    p1 = doc.add_page(width=120, height=60)
    tb = p1.add_textbox(10, 10, 100, 20, "web zly")
    tb.runs = [TextRun(text="web", link="https://example.com"),
               TextRun(text=" zly", link="javascript:alert(1)")]
    path = str(tmp_path / "l.svg")
    export_svg(doc, path, page=0)
    svg = open(path, encoding="utf-8").read()
    assert '<a href="https://example.com"' in svg
    assert "xlink:href" in svg
    assert "javascript" not in svg


def test_pdf_quad_bezier_elevation(tmp_path):
    import re, zlib
    from edof.export.pdf_writer import PdfWriter
    w = PdfWriter(); pg = w.add_page(100, 100)
    pg.path([("M", 10, 50), ("Q", 50, 10, 90, 50)], fill=None, stroke=(0, 0, 0))
    path = str(tmp_path / "q.pdf")
    w.save(path)
    raw = open(path, "rb").read()
    m = re.search(rb"stream\n(.*?)\nendstream", raw, re.S)
    content = zlib.decompress(m.group(1)).decode()
    mmpt = 72 / 25.4
    P0x, Qx, P2x = 10 * mmpt, 50 * mmpt, 90 * mmpt
    c1x = P0x + 2 / 3 * (Qx - P0x)
    c2x = P2x + 2 / 3 * (Qx - P2x)
    line = [l for l in content.splitlines() if l.endswith(" c")][0]
    vals = [float(v) for v in line.split()[:6]]
    assert abs(vals[0] - c1x) < 0.01 and abs(vals[2] - c2x) < 0.01
    assert abs(vals[0] - vals[2]) > 1, "control points must differ"


def test_pdf_transparent_png_gets_smask(tmp_path):
    import io as _io
    from PIL import Image as _Image
    from edof.export.pdf import export_pdf
    img = _Image.new("RGBA", (40, 40), (255, 0, 0, 0))
    for x in range(20):
        for y in range(40):
            img.putpixel((x, y), (255, 0, 0, 255))
    buf = _io.BytesIO(); img.save(buf, "PNG")
    doc = Document()
    page = doc.add_page(width=100, height=60)
    rid = doc.add_resource(buf.getvalue(), "logo.png", "image/png")
    page.add_image(rid, 10, 10, 40, 40)
    path = str(tmp_path / "alpha.pdf")
    export_pdf(doc, path)
    d = open(path, "rb").read()
    assert b"/SMask" in d and b"/DeviceGray" in d


def test_add_page_explicit_zero_not_defaulted():
    doc = Document()
    pg = doc.add_page(width=0, height=0)
    assert pg.width == 0 and pg.height == 0, \
        "explicit 0 must not silently fall back to the default size"
