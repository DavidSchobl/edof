# edof/export/pdf.py
"""
v4.0: Vector PDF export using the built-in pure-Python pdf_writer.

Falls back to the legacy reportlab raster export if vector=False.
"""
from __future__ import annotations
import io
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from edof.format.document import Document


def export_pdf(doc: "Document", path: str,
               vector: bool = True,
               dpi: Optional[int] = None) -> None:
    """Export the document to PDF.

    vector=True (default): pure-Python vector PDF — searchable, copyable, small.
    vector=False: legacy raster mode via reportlab.
    """
    if vector:
        _export_pdf_vector(doc, path)
    else:
        _export_pdf_raster(doc, path, dpi)


# ──────────────────────────────────────────────────────────────────────────────
#  v4.0  Vector export
# ──────────────────────────────────────────────────────────────────────────────

def _export_pdf_vector(doc, path: str) -> None:
    from edof.export.pdf_writer import PdfWriter
    from edof.utils.safe_eval import is_visible

    writer = PdfWriter(
        title   = doc.title       or "EDOF Document",
        author  = doc.author      or "",
        subject = doc.description or "",
        creator = "edof v4.0.1",
    )

    for page in doc.pages:
        pp = writer.add_page(page.width, page.height)

        # Page background
        bg = page.background
        if bg and len(bg) >= 3 and tuple(bg[:3]) != (255, 255, 255):
            pp.rect(0, 0, page.width, page.height, fill=bg[:3], stroke=None)

        for obj in page.sorted_objects():
            if not is_visible(obj, doc.variables):
                continue
            _emit_object(pp, obj, doc, writer)

    writer.save(path)


def _emit_object(pp, obj, doc, writer):
    from edof.format.objects import (TextBox, ImageBox, Shape, QRCode, Group, Table)
    from edof.utils.safe_eval import is_visible

    if isinstance(obj, TextBox):
        _emit_textbox(pp, obj, doc)
    elif isinstance(obj, ImageBox):
        _emit_imagebox(pp, obj, doc, writer)
    elif isinstance(obj, Shape):
        _emit_shape(pp, obj)
    elif isinstance(obj, QRCode):
        _emit_qrcode(pp, obj, doc, writer)
    elif isinstance(obj, Table):
        _emit_table(pp, obj, doc)
    elif isinstance(obj, Group):
        for child in obj.flatten():
            if is_visible(child, doc.variables):
                _emit_object(pp, child, doc, writer)


def _emit_textbox(pp, obj, doc):
    from edof.export.pdf_writer import measure_text_width, map_to_standard

    t = obj.transform
    pad = getattr(obj.style, "padding", 1.0)

    # Background
    if obj.fill and obj.fill.color:
        c = obj.fill.color
        if len(c) < 4 or c[3] > 0:
            pp.rect(t.x, t.y, t.width, t.height, fill=c[:3], stroke=None)

    if obj.border:
        pp.rect(t.x, t.y, t.width, t.height,
                fill=None, stroke=obj.border.color[:3],
                width_pt=obj.border.width)

    # Text content
    if obj.runs:
        _emit_runs(pp, obj, t.x + pad, t.y + pad,
                   t.width - 2 * pad, t.height - 2 * pad)
    else:
        text = obj.get_resolved_text(doc.variables)
        if not text: return
        font_name = map_to_standard(obj.style.font_family,
                                     obj.style.bold, obj.style.italic)
        size_pt  = obj.style.font_size
        max_w_pt = (t.width - 2 * pad) / 25.4 * 72

        # Auto-shrink: simple width-based downscale
        if obj.style.auto_shrink or obj.style.auto_fill:
            w = measure_text_width(text.split("\n")[0], font_name, size_pt)
            if w > max_w_pt:
                size_pt = size_pt * max_w_pt / w if w > 0 else size_pt

        lines = _wrap_text_for_pdf(text, font_name, size_pt, max_w_pt,
                                    wrap=obj.style.wrap)
        line_h = size_pt * obj.style.line_height / 72 * 25.4
        total_h = line_h * len(lines)

        if   obj.style.vertical_align == "middle": y_off = (t.height - 2*pad - total_h) / 2
        elif obj.style.vertical_align == "bottom": y_off = t.height - 2*pad - total_h
        else:                                       y_off = 0

        for i, line in enumerate(lines):
            line_w_mm = measure_text_width(line, font_name, size_pt) / 72 * 25.4
            inner_w   = t.width - 2 * pad
            if   obj.style.alignment == "center": x_off = (inner_w - line_w_mm) / 2
            elif obj.style.alignment == "right":  x_off = inner_w - line_w_mm
            else:                                  x_off = 0

            line_y = t.y + pad + y_off + i * line_h
            pp.text(t.x + pad + x_off, line_y, line,
                    font_family=obj.style.font_family,
                    font_size_pt=size_pt,
                    color=obj.style.color[:3],
                    bold=obj.style.bold, italic=obj.style.italic)
            if obj.style.underline:
                pp.text_underline(t.x + pad + x_off, line_y, line,
                                   font_family=obj.style.font_family,
                                   font_size_pt=size_pt,
                                   color=obj.style.color[:3])


def _emit_runs(pp, obj, x_mm, y_mm, w_mm, h_mm):
    """Emit rich-text runs as vector PDF text."""
    from edof.export.pdf_writer import measure_text_width, map_to_standard

    parent   = obj.style
    max_w_pt = w_mm / 25.4 * 72

    # Tokenize into words
    word_seq = []
    for run in obj.runs:
        text = run.text; i = 0
        while i < len(text):
            if text[i] == "\n":
                word_seq.append((run, "\n", True)); i += 1
            else:
                j = i
                while j < len(text) and text[j] != "\n": j += 1
                seg = text[i:j]; k = 0
                while k < len(seg):
                    if seg[k] == " ":
                        m = k
                        while m < len(seg) and seg[m] == " ": m += 1
                        word_seq.append((run, seg[k:m], False)); k = m
                    else:
                        m = k
                        while m < len(seg) and seg[m] != " ": m += 1
                        word_seq.append((run, seg[k:m], False)); k = m
                i = j

    # Pack into lines
    lines, cur_line, cur_w = [], [], 0
    for run, word, is_nl in word_seq:
        if is_nl:
            lines.append(cur_line); cur_line = []; cur_w = 0; continue
        rs = run.resolve(parent, scale=1.0)
        font_name = map_to_standard(rs["font_family"], rs["bold"], rs["italic"])
        w_pt = measure_text_width(word, font_name, rs["font_size"])
        if parent.wrap and cur_w + w_pt > max_w_pt and cur_line:
            lines.append(cur_line); cur_line = []; cur_w = 0
            if word.strip() == "": continue
        cur_line.append((run, word, w_pt, rs))
        cur_w += w_pt
    if cur_line: lines.append(cur_line)

    # Compute line heights
    line_heights = []
    for line in lines:
        max_size = max((seg[3]["font_size"] for seg in line), default=parent.font_size)
        line_heights.append(max_size * parent.line_height / 72 * 25.4)

    total_h = sum(line_heights)
    if   parent.vertical_align == "middle": y_off = (h_mm - total_h) / 2
    elif parent.vertical_align == "bottom": y_off = h_mm - total_h
    else:                                    y_off = 0

    cur_y_mm = y_mm + y_off
    for line, lh_mm in zip(lines, line_heights):
        line_w_mm = sum(seg[2] for seg in line) / 72 * 25.4
        if   parent.alignment == "center": cur_x_mm = x_mm + (w_mm - line_w_mm) / 2
        elif parent.alignment == "right":  cur_x_mm = x_mm + w_mm - line_w_mm
        else:                               cur_x_mm = x_mm

        for run, word, w_pt, rs in line:
            bg = rs.get("background")
            if bg and len(bg) >= 4 and bg[3] > 0:
                pp.rect(cur_x_mm, cur_y_mm, w_pt / 72 * 25.4, lh_mm,
                        fill=bg[:3], stroke=None)
            color = rs["color"] if rs["color"] else (0, 0, 0)
            pp.text(cur_x_mm, cur_y_mm, word,
                    font_family=rs["font_family"],
                    font_size_pt=rs["font_size"],
                    color=color[:3],
                    bold=rs["bold"], italic=rs["italic"])
            if rs.get("underline"):
                pp.text_underline(cur_x_mm, cur_y_mm, word,
                                   font_family=rs["font_family"],
                                   font_size_pt=rs["font_size"],
                                   color=color[:3])
            cur_x_mm += w_pt / 72 * 25.4
        cur_y_mm += lh_mm


def _wrap_text_for_pdf(text, font_name, font_size_pt, max_w_pt, wrap=True):
    from edof.export.pdf_writer import measure_text_width
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not wrap: return raw
    out = []
    for line in raw:
        if not line: out.append(""); continue
        words, cur = line.split(" "), ""
        for word in words:
            test = (cur + " " + word).strip() if cur else word
            if measure_text_width(test, font_name, font_size_pt) <= max_w_pt:
                cur = test
            else:
                if cur: out.append(cur)
                cur = word
        if cur: out.append(cur)
    return out


def _emit_shape(pp, obj):
    from edof.format.objects import (
        SHAPE_RECT, SHAPE_ELLIPSE, SHAPE_LINE, SHAPE_POLYGON, SHAPE_PATH,
    )
    t = obj.transform
    fill   = obj.fill.color[:3]   if obj.fill.color   else None
    stroke = obj.stroke.color[:3] if obj.stroke.color else (0, 0, 0)
    width_pt = obj.stroke.width

    if obj.shape_type == SHAPE_RECT:
        pp.rect(t.x, t.y, t.width, t.height,
                fill=fill, stroke=stroke, width_pt=width_pt,
                corner_radius_mm=obj.corner_radius)
    elif obj.shape_type == SHAPE_ELLIPSE:
        pp.ellipse(t.x + t.width/2, t.y + t.height/2,
                   t.width/2, t.height/2,
                   fill=fill, stroke=stroke, width_pt=width_pt)
    elif obj.shape_type == SHAPE_LINE:
        if obj.points and len(obj.points) >= 2:
            p1, p2 = obj.points[0], obj.points[1]
            pp.line(p1[0], p1[1], p2[0], p2[1], color=stroke, width_pt=width_pt)
        else:
            pp.line(t.x, t.y, t.x + t.width, t.y + t.height,
                    color=stroke, width_pt=width_pt)
    elif obj.shape_type == SHAPE_POLYGON:
        if obj.points:
            pp.polygon(obj.points, fill=fill, stroke=stroke, width_pt=width_pt)
    elif obj.shape_type == SHAPE_PATH:
        if obj.path_data:
            pp.path(obj.path_data, fill=fill, stroke=stroke, width_pt=width_pt)


def _emit_imagebox(pp, obj, doc, writer):
    if not obj.resource_id or obj.resource_id not in doc.resources: return
    entry = doc.resources.get(obj.resource_id)
    if not entry: return
    image_id = obj.resource_id
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(entry.data))
        if img.format == "JPEG":
            writer.add_image(image_id, img.width, img.height, b"",
                              jpeg_data=entry.data)
        else:
            img = img.convert("RGB")
            writer.add_image(image_id, img.width, img.height, img.tobytes())
    except Exception:
        return
    t = obj.transform
    pp.image(image_id, t.x, t.y, t.width, t.height)


def _emit_qrcode(pp, obj, doc, writer):
    try: import qrcode as qrlib
    except ImportError: return
    from PIL import Image

    data = obj.get_resolved_data(doc.variables)
    if not data: return

    ec = {"L": qrlib.constants.ERROR_CORRECT_L, "M": qrlib.constants.ERROR_CORRECT_M,
          "Q": qrlib.constants.ERROR_CORRECT_Q, "H": qrlib.constants.ERROR_CORRECT_H}
    qr = qrlib.QRCode(error_correction=ec.get(obj.error_correction, ec["M"]),
                       border=obj.border_modules)
    qr.add_data(data); qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    if obj.fg_color[:3] != (0,0,0) or obj.bg_color[:3] != (255,255,255):
        pixels = qr_img.load()
        fg = obj.fg_color[:3]; bg = obj.bg_color[:3]
        for x in range(qr_img.width):
            for y in range(qr_img.height):
                r, _, _ = pixels[x, y]
                pixels[x, y] = fg if r < 128 else bg

    image_id = "qr_" + obj.id[:8]
    writer.add_image(image_id, qr_img.width, qr_img.height, qr_img.tobytes())
    t = obj.transform
    size = min(t.width, t.height)
    pp.image(image_id, t.x, t.y, size, size)


def _emit_table(pp, obj, doc):
    from edof.export.pdf_writer import measure_text_width, map_to_standard
    t = obj.transform
    n_rows = obj.num_rows; n_cols = obj.num_cols
    if n_rows == 0 or n_cols == 0: return

    col_w = list(obj.col_widths) + [0] * max(0, n_cols - len(obj.col_widths))
    explicit_w = sum(w for w in col_w if w > 0)
    auto_cols = sum(1 for w in col_w if w == 0)
    auto_w = (t.width - explicit_w) / auto_cols if auto_cols > 0 else 0
    col_w_mm = [w if w > 0 else auto_w for w in col_w]

    row_h = list(obj.row_heights) + [0] * max(0, n_rows - len(obj.row_heights))
    explicit_h = sum(h for h in row_h if h > 0)
    auto_rows = sum(1 for h in row_h if h == 0)
    auto_h = (t.height - explicit_h) / auto_rows if auto_rows > 0 else 0
    row_h_mm = [h if h > 0 else auto_h for h in row_h]

    x_off = [0]
    for w in col_w_mm[:-1]: x_off.append(x_off[-1] + w)
    y_off = [0]
    for h in row_h_mm[:-1]: y_off.append(y_off[-1] + h)

    # Cell backgrounds + content
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = obj.cells[ri][ci]
            cx = t.x + x_off[ci]; cy = t.y + y_off[ri]
            cw = sum(col_w_mm[ci:ci + cell.colspan])
            ch = sum(row_h_mm[ri:ri + cell.rowspan])

            bg = cell.bg_color
            if bg and len(bg) >= 4 and bg[3] > 0:
                pp.rect(cx, cy, cw, ch, fill=bg[:3], stroke=None)

            cell_text = cell.text
            if doc.variables and "{" in cell_text:
                for name in doc.variables.names():
                    v = doc.variables.get(name)
                    if v is not None:
                        cell_text = cell_text.replace("{" + name + "}", str(v))

            if cell.runs:
                class _Tmp:
                    def __init__(s, runs, style): s.runs=runs; s.style=style
                _emit_runs(pp, _Tmp(cell.runs, cell.style),
                           cx + cell.padding, cy + cell.padding,
                           cw - 2*cell.padding, ch - 2*cell.padding)
            elif cell_text:
                font_name = map_to_standard(cell.style.font_family,
                                             cell.style.bold, cell.style.italic)
                size_pt = cell.style.font_size
                max_w_pt = (cw - 2*cell.padding) / 25.4 * 72
                if cell.style.auto_shrink:
                    w = measure_text_width(cell_text, font_name, size_pt)
                    if w > max_w_pt: size_pt = size_pt * max_w_pt / w

                line_h_mm = size_pt * cell.style.line_height / 72 * 25.4
                if cell.style.vertical_align == "middle":
                    ty = cy + cell.padding + (ch - 2*cell.padding - line_h_mm) / 2
                elif cell.style.vertical_align == "bottom":
                    ty = cy + ch - cell.padding - line_h_mm
                else:
                    ty = cy + cell.padding

                line_w_mm = measure_text_width(cell_text, font_name, size_pt) / 72 * 25.4
                inner_w = cw - 2*cell.padding
                if   cell.style.alignment == "center": tx = cx + cell.padding + (inner_w - line_w_mm) / 2
                elif cell.style.alignment == "right":  tx = cx + cw - cell.padding - line_w_mm
                else:                                   tx = cx + cell.padding

                pp.text(tx, ty, cell_text,
                        font_family=cell.style.font_family,
                        font_size_pt=size_pt,
                        color=cell.style.color[:3],
                        bold=cell.style.bold, italic=cell.style.italic)

    # Borders
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = obj.cells[ri][ci]
            cx = t.x + x_off[ci]; cy = t.y + y_off[ri]
            cw = sum(col_w_mm[ci:ci + cell.colspan])
            ch = sum(row_h_mm[ri:ri + cell.rowspan])
            for side, x1, y1, x2, y2 in [
                (cell.border_top,    cx,      cy,      cx + cw, cy),
                (cell.border_right,  cx + cw, cy,      cx + cw, cy + ch),
                (cell.border_bottom, cx,      cy + ch, cx + cw, cy + ch),
                (cell.border_left,   cx,      cy,      cx,      cy + ch),
            ]:
                if side.enabled:
                    pp.line(x1, y1, x2, y2, color=side.color[:3],
                            width_pt=side.width / 25.4 * 72)

    if obj.table_border:
        pp.rect(t.x, t.y, t.width, t.height,
                fill=None, stroke=obj.table_border.color[:3],
                width_pt=obj.table_border.width)


# ──────────────────────────────────────────────────────────────────────────────
#  Legacy raster (reportlab)
# ──────────────────────────────────────────────────────────────────────────────

def _export_pdf_raster(doc, path: str, dpi: Optional[int] = None) -> None:
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.units import mm
    except ImportError:
        from edof.exceptions import warn_missing, EdofError
        warn_missing("PDF export (raster)", "pdf")
        raise EdofError(
            "reportlab is required for raster PDF export.\n"
            "Install with: pip install reportlab\n"
            "Or use vector mode (default, no extra dependencies)."
        )
    from edof.engine.renderer import render_page

    first = doc.pages[0]
    pdf = rl_canvas.Canvas(path, pagesize=(first.width * mm, first.height * mm))
    pdf.setTitle(doc.title or "EDOF Document")
    pdf.setAuthor(doc.author or "")
    pdf.setSubject(doc.description or "")
    for page in doc.pages:
        img = render_page(page, doc.resources, doc.variables, dpi or page.dpi)
        buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        pdf.setPageSize((page.width * mm, page.height * mm))
        pdf.drawImage(ImageReader(buf), 0, 0,
                      width=page.width * mm, height=page.height * mm,
                      preserveAspectRatio=False)
        pdf.showPage()
    pdf.save()
