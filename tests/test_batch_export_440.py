"""v4.4.0: batch export engine — scope page/all, PNG/PDF/EDOF, [PAGE] token,
integrate vs external+ZIP sources."""
import io
import os
import zipfile
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from edof.format.document import Document
from edof.format.styles import TextRun
from edof.batch.model import build_ref, BatchRow, render_filename
from edof.batch.generate import export_batch


def _doc_with_batch(tmp_path, pages=2):
    img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
    ipath = str(tmp_path / "flag.png")
    img.save(ipath, "PNG")
    doc = Document()
    pgs = [doc.add_page(width=100, height=60) for _ in range(pages)]
    tb = pgs[0].add_textbox(10, 10, 80, 20, "Nazev")
    tb.runs = [TextRun(text="Nazev", rid="r1", var_name="nazev")]
    ib = pgs[0].add_image("", 10, 35, 16, 16)
    cfg = doc.batch
    cfg.row_scope = "document"
    c1 = cfg.add_column(build_ref(pgs[0], tb), "run.text", "nazev", "text")
    c1.run_id = "r1"
    c2 = cfg.add_column(build_ref(pgs[0], ib), "resource_id", "vlajka", "file_path")
    rows = [BatchRow(name="Praha", values={c1.column_id: "Praha",
                                           c2.column_id: ipath}),
            BatchRow(name="Brno", values={c1.column_id: "Brno",
                                          c2.column_id: ipath})]
    cfg.rows.extend(rows)
    return doc, cfg, rows


def test_render_filename_page_token():
    doc, cfg, rows = None, None, None
    from edof.batch.model import BatchConfig
    cfg = BatchConfig()
    row = BatchRow(name="Praha")
    assert render_filename("[ROW_NAME]_p[PAGE:02]", 1, row, cfg,
                           default_ext="png", page_number=3) == "Praha_p03.png"


def test_export_png_all_pages(tmp_path):
    doc, cfg, rows = _doc_with_batch(tmp_path)
    out = tmp_path / "out"; out.mkdir()
    ok, written, errors = export_batch(doc, cfg, rows, str(out),
                                       "[ROW_NAME]", "png", scope="all")
    assert not errors and ok == 2
    names = sorted(os.path.basename(w) for w in written)
    assert names == ["Brno_p1.png", "Brno_p2.png",
                     "Praha_p1.png", "Praha_p2.png"], names


def test_export_pdf_page_vs_all(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    from pypdf import PdfReader
    doc, cfg, rows = _doc_with_batch(tmp_path)
    out1 = tmp_path / "o1"; out1.mkdir()
    ok, w1, err = export_batch(doc, cfg, rows[:1], str(out1),
                               "[ROW_NAME]", "pdf", scope="page", page_idx=0)
    assert not err and len(w1) == 1
    assert len(PdfReader(w1[0]).pages) == 1
    out2 = tmp_path / "o2"; out2.mkdir()
    ok, w2, err = export_batch(doc, cfg, rows[:1], str(out2),
                               "[ROW_NAME]", "pdf", scope="all")
    assert not err and len(PdfReader(w2[0]).pages) == 2


def test_export_edof_integrate(tmp_path):
    doc, cfg, rows = _doc_with_batch(tmp_path)
    out = tmp_path / "oi"; out.mkdir()
    ok, written, errors = export_batch(doc, cfg, rows[:1], str(out),
                                       "[ROW_NAME]", "edof", scope="all",
                                       sources="integrate")
    assert not errors and written[0].endswith("Praha.edof")
    d2 = Document.load(written[0])
    # the image is a RESOURCE inside the file (self-contained)
    ib2 = [o for pg in d2.pages for o in pg.objects
           if getattr(o, "resource_id", None)][0]
    assert ib2.resource_id in d2.resources
    # row value applied
    assert any("Praha" in (getattr(o, "text", "") or "")
               for pg in d2.pages for o in pg.objects)


def test_export_edof_external_zip(tmp_path):
    doc, cfg, rows = _doc_with_batch(tmp_path)
    out = tmp_path / "oz"; out.mkdir()
    ok, written, errors = export_batch(doc, cfg, rows[:1], str(out),
                                       "[ROW_NAME]", "edof", scope="all",
                                       sources="external")
    assert not errors and written[0].endswith("Praha.zip")
    with zipfile.ZipFile(written[0]) as zf:
        names = sorted(zf.namelist())
        assert "Praha.edof" in names
        assert any(n.replace("\\\\", "/").startswith("sources/")
                   for n in names), names
        # the edof inside references the RELATIVE sources path
        data = zf.read("Praha.edof")
    p = tmp_path / "unpack"; p.mkdir()
    with zipfile.ZipFile(written[0]) as zf:
        zf.extractall(str(p))
    d2 = Document.load(str(p / "Praha.edof"))
    rids = [getattr(o, "resource_id", None)
            for pg in d2.pages for o in pg.objects
            if getattr(o, "resource_id", None)]
    # load resolves the relative bundle path against the .edof folder, so it
    # comes back ABSOLUTE, existing, and pointing into sources/
    assert any("sources" in str(r).replace("\\\\", "/")
               and os.path.isfile(str(r)) for r in rids), rids


def test_external_bundle_renders_from_any_cwd(tmp_path):
    """The unpacked ZIP bundle must render its sources no matter what the
    process CWD is (relative paths resolve against the .edof location)."""
    doc, cfg, rows = _doc_with_batch(tmp_path)
    out = tmp_path / "ob"; out.mkdir()
    ok, written, errors = export_batch(doc, cfg, rows[:1], str(out),
                                       "[ROW_NAME]", "edof", scope="all",
                                       sources="external")
    p = tmp_path / "un"; p.mkdir()
    with zipfile.ZipFile(written[0]) as zf:
        zf.extractall(str(p))
    cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))            # NOT the bundle folder
        d2 = Document.load(str(p / "Praha.edof"))
        from edof.engine.renderer import render_document
        img = render_document(d2, dpi=72)[0].convert("RGB")
        colors = {c for _n, c in img.getcolors(1 << 20)}
        assert (255, 0, 0) in colors, "the external image must render"
    finally:
        os.chdir(cwd)


# ── v4.4.0: single multipage output + progress/cancel ────────────────────────

def test_single_pdf_all_rows(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    from pypdf import PdfReader
    doc, cfg, rows = _doc_with_batch(tmp_path)          # 2 rows x 2 pages
    out = tmp_path / "sp"; out.mkdir()
    ok, written, errors = export_batch(doc, cfg, rows, str(out),
                                       "katalog", "pdf", scope="all",
                                       output="single")
    assert not errors and ok == 2
    assert len(written) == 1 and written[0].endswith("katalog.pdf")
    assert len(PdfReader(written[0]).pages) == 4        # 2 rows x 2 pages

    out2 = tmp_path / "sp1"; out2.mkdir()
    ok, w2, err = export_batch(doc, cfg, rows, str(out2),
                               "prehled", "pdf", scope="page", page_idx=0,
                               output="single")
    assert not err and len(PdfReader(w2[0]).pages) == 2  # 1 page per row


def test_single_edof_baked(tmp_path):
    doc, cfg, rows = _doc_with_batch(tmp_path)
    out = tmp_path / "se"; out.mkdir()
    ok, written, errors = export_batch(doc, cfg, rows, str(out),
                                       "kniha", "edof", scope="all",
                                       output="single", sources="integrate")
    assert not errors and len(written) == 1
    assert written[0].endswith("kniha.edof")
    d2 = Document.load(written[0])
    assert len(d2.pages) == 4
    assert d2.body is None                       # baked: no re-pagination
    assert not d2.batch.columns and not d2.batch.rows   # no live batch
    # page ids are unique (appended rows get fresh ids)
    ids = [p.id for p in d2.pages]
    assert len(ids) == len(set(ids))
    # both rows' values are baked into their own pages
    texts = []
    for pg in d2.pages:
        for o in pg.objects:
            for r in (getattr(o, "runs", None) or []):
                texts.append(r.text)
    assert any("Praha" in t for t in texts)
    assert any("Brno" in t for t in texts)
    # and it renders
    from edof.engine.renderer import render_page
    img = render_page(d2.pages[0], d2.resources, {}, dpi=72)
    assert img.size[0] > 0


def test_single_rejects_image_formats(tmp_path):
    doc, cfg, rows = _doc_with_batch(tmp_path)
    with pytest.raises(ValueError):
        export_batch(doc, cfg, rows, str(tmp_path), "x", "png",
                     output="single")


def test_progress_ticks_and_cancel(tmp_path):
    doc, cfg, rows = _doc_with_batch(tmp_path)
    out = tmp_path / "pr"; out.mkdir()
    ticks = []
    ok, written, errors = export_batch(
        doc, cfg, rows, str(out), "[ROW_NAME]", "png", scope="page",
        progress=lambda d, t: ticks.append((d, t)) or True)
    assert not errors and ticks[0] == (0, 2) and ticks[-1] == (2, 2)

    # cancel after the first row: one file written, "Cancelled" reported
    out2 = tmp_path / "pc"; out2.mkdir()
    ok, written, errors = export_batch(
        doc, cfg, rows, str(out2), "[ROW_NAME]", "png", scope="page",
        progress=lambda d, t: d < 1)
    assert ok == 1 and len(written) == 1
    assert any(e.startswith("Cancelled") for e in errors)

    # cancel works for the single-file combine too
    out3 = tmp_path / "pc2"; out3.mkdir()
    ok, written, errors = export_batch(
        doc, cfg, rows, str(out3), "x", "pdf", scope="all",
        output="single", progress=lambda d, t: d < 1)
    assert not written
    assert any(e.startswith("Cancelled") for e in errors)
