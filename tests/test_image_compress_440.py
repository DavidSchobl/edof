"""v4.4.0 final addition: image recompression (PNG lossless / JPEG quality)
for edof saves, PDF export and batch generation."""
import io
import os
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from edof.format.document import Document


def _noise_png(w=256, h=256, alpha=False):
    """A photo-like image (random noise compresses badly as PNG, well as
    JPEG), returned as PNG bytes."""
    import random
    rnd = random.Random(42)
    mode = "RGBA" if alpha else "RGB"
    img = Image.new(mode, (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            c = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            px[x, y] = c + ((128,) if alpha else ())
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _doc_with_photo(alpha=False):
    doc = Document()
    pg = doc.add_page(width=100, height=100)
    rid = doc.resources.add(_noise_png(alpha=alpha), "photo.png", "image/png")
    pg.add_image(rid, 10, 10, 60, 60)
    return doc, rid


def test_recompress_jpeg_shrinks_and_updates_entry():
    doc, rid = _doc_with_photo()
    entry = doc.resources.get(rid)
    src = len(entry.data)
    n, before, after = doc.recompress_images("jpeg", 60)
    assert n == 1 and before == src and after < before / 2
    assert entry.mime_type == "image/jpeg"
    assert entry.filename.endswith(".jpg")
    assert Image.open(io.BytesIO(entry.data)).format == "JPEG"


def test_recompress_keeps_alpha_as_png():
    doc, rid = _doc_with_photo(alpha=True)
    n, before, after = doc.recompress_images("jpeg", 60)
    entry = doc.resources.get(rid)
    img = Image.open(io.BytesIO(entry.data))
    assert img.format == "PNG"                 # alpha never goes lossy
    assert entry.mime_type == "image/png"


def test_recompress_never_inflates_and_skips_fonts():
    doc = Document()
    pg = doc.add_page()
    tiny = io.BytesIO(); Image.new("RGB", (2, 2), (250, 0, 0)).save(tiny, "PNG")
    rid = doc.resources.add(tiny.getvalue(), "dot.png", "image/png")
    pg.add_image(rid, 5, 5, 10, 10)
    frid = doc.resources.add(b"\x00\x01\x00\x00fontdata", "f.ttf", "font/ttf")
    src_img = len(doc.resources.get(rid).data)
    n, before, after = doc.recompress_images("jpeg", 40)
    assert doc.resources.get(frid).data == b"\x00\x01\x00\x00fontdata"
    # 2x2 dot: jpeg is BIGGER than png, so the entry must stay untouched
    e = doc.resources.get(rid)
    assert len(e.data) == src_img or e.mime_type == "image/png"
    assert after <= before


def test_recompress_png_lossless_roundtrip():
    doc, rid = _doc_with_photo()
    raw0 = Image.open(io.BytesIO(doc.resources.get(rid).data)).tobytes()
    doc.recompress_images("png", 100)
    raw1 = Image.open(io.BytesIO(doc.resources.get(rid).data)).tobytes()
    assert raw0 == raw1                        # bit-identical pixels


def test_pdf_export_jpeg_smaller_with_dct(tmp_path):
    doc, rid = _doc_with_photo()
    p1 = str(tmp_path / "lossless.pdf")
    p2 = str(tmp_path / "jpeg.pdf")
    doc.export_pdf(p1, embed_source=False)
    doc.export_pdf(p2, embed_source=False, image_format="jpeg",
                   image_quality=60)
    assert os.path.getsize(p2) < os.path.getsize(p1) / 2
    data = open(p2, "rb").read()
    assert b"/DCTDecode" in data
    pypdf = pytest.importorskip("pypdf")
    from pypdf import PdfReader
    assert len(PdfReader(p2).pages) == 1


def test_pdf_export_jpeg_keeps_alpha_smask(tmp_path):
    doc, rid = _doc_with_photo(alpha=True)
    p = str(tmp_path / "a.pdf")
    doc.export_pdf(p, embed_source=False, image_format="jpeg",
                   image_quality=60)
    data = open(p, "rb").read()
    assert b"/DCTDecode" in data and b"/SMask" in data


def test_export_pdf_wrapper_accepts_embed_source(tmp_path):
    """Regression: the editor calls doc.export_pdf(embed_source=...) and the
    Document wrapper did not accept the kwarg (TypeError -> export failed)."""
    doc, _ = _doc_with_photo()
    p = str(tmp_path / "w.pdf")
    doc.export_pdf(p, vector=True, dpi=None, embed_source=True)
    assert os.path.getsize(p) > 0


def test_batch_export_image_compression(tmp_path):
    from edof.batch.generate import export_batch
    from edof.batch.model import BatchRow
    doc, rid = _doc_with_photo()
    cfg = doc.batch
    rows = [BatchRow(name="A")]
    out1 = tmp_path / "o1"; out1.mkdir()
    ok, w1, err = export_batch(doc, cfg, rows, str(out1), "x", "edof",
                               scope="all")
    assert not err
    out2 = tmp_path / "o2"; out2.mkdir()
    ok, w2, err = export_batch(doc, cfg, rows, str(out2), "x", "edof",
                               scope="all", image_format="jpeg",
                               image_quality=60)
    assert not err
    assert os.path.getsize(w2[0]) < os.path.getsize(w1[0]) / 2
    d2 = Document.load(w2[0])
    ents = [e for e in d2.resources.all_entries()
            if e.mime_type == "image/jpeg"]
    assert len(ents) == 1


def test_row_and_column_contexts_support_with():
    """v4.4.0 docs pass: page.row()/page.column() usable as context
    managers, as the helpers documentation shows."""
    doc = Document()
    pg = doc.add_page()
    with pg.row(y=20, gap=5, height=12) as r:
        t1 = r.add_textbox(60, "A")
        t2 = r.add_textbox(60, "B")
    assert t2.transform.x > t1.transform.x
    col = pg.column if hasattr(pg, "column") else None
    if col:
        with pg.column(x=20, gap=3, width=60) as c:
            c.add_textbox(10, "C")
