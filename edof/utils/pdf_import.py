# edof/utils/pdf_import.py
"""
v4.0: Import PDF files as editable EDOF documents.

Uses pymupdf (fitz) for text/image/path extraction.
Optional pdfplumber for table detection.

Usage:
    doc = edof.import_pdf("template.pdf",
                          detect_tables=True,
                          merge_paragraphs=True,
                          heading_threshold=1.4)
"""
from __future__ import annotations
import io
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edof.format.document import Document


def import_pdf(path: str,
                detect_tables: bool = False,
                merge_paragraphs: bool = True,
                heading_threshold: float = 1.4,
                indent_threshold_mm: float = 3.0,
                extract_paths: bool = True,
                extract_images: bool = True) -> "Document":
    """Import a PDF as an editable EDOF Document.

    detect_tables       — enable heuristic table detection (requires pdfplumber)
    merge_paragraphs    — cluster spans into paragraphs based on font/size/spacing
    heading_threshold   — font_size > median × this ratio → heading TextBox
    indent_threshold_mm — first-line offset above this triggers paragraph indent
    extract_paths       — convert PDF vector paths to Shape objects (v4.0.3)
    extract_images      — extract embedded raster images as ImageBox objects (v4.0.3)
    """
    try:
        import fitz   # pymupdf
    except ImportError:
        from edof.exceptions import EdofError
        raise EdofError(
            "pymupdf is required for PDF import. Install with:\n"
            "  pip install pymupdf"
        )

    import edof
    from edof.format.objects import TextBox, ImageBox, Shape, SHAPE_PATH
    from edof.format.styles import TextRun

    pdf = fitz.open(path)
    doc = edof.new(width=210, height=297, title=os.path.basename(path))

    # PDF metadata → doc metadata
    meta = pdf.metadata or {}
    doc.title       = meta.get("title")    or doc.title
    doc.author      = meta.get("author")   or ""
    doc.description = meta.get("subject")  or ""

    # Process fonts (extract embedded TTFs to resources)
    font_mapping = _extract_fonts(pdf, doc)

    pdf_pages = []
    for pdf_page in pdf:
        rect = pdf_page.rect
        # PDF uses 72 dpi units (points); convert to mm
        w_mm = rect.width  / 72 * 25.4
        h_mm = rect.height / 72 * 25.4
        page = doc.add_page(dpi=300)
        page.width  = w_mm
        page.height = h_mm

        # 1. Extract text spans with full font/size info
        spans = _extract_text_spans(pdf_page, font_mapping)

        # 2. Cluster into paragraph blocks
        if merge_paragraphs:
            blocks = _cluster_blocks(spans, indent_threshold_mm)
        else:
            blocks = [[s] for s in spans]

        # 3. Compute median font size for heading detection
        sizes = [s["size"] for s in spans if s["text"].strip()]
        median_size = sorted(sizes)[len(sizes)//2] if sizes else 12.0

        # 4. Convert blocks to TextBoxes
        for block in blocks:
            tb = _block_to_textbox(block, h_mm, median_size, heading_threshold)
            if tb: page.add_object(tb)

        # 5. Extract images
        if extract_images:
            for img_info in _extract_images(pdf_page, doc):
                page.add_object(img_info)

        # 6. Extract vector paths (basic)
        if extract_paths:
            for path_obj in _extract_paths(pdf_page, h_mm):
                page.add_object(path_obj)

        # 7. Detect tables (optional)
        if detect_tables:
            for table_obj in _detect_tables(pdf_page, h_mm):
                page.add_object(table_obj)

        pdf_pages.append(pdf_page)

    pdf.close()
    return doc


# ──────────────────────────────────────────────────────────────────────────────
#  Font extraction & mapping
# ──────────────────────────────────────────────────────────────────────────────

def _extract_fonts(pdf, doc) -> dict:
    """Extract embedded fonts. Returns mapping pdf_font_name -> edof_family."""
    mapping = {}
    seen = set()
    standard_14 = {
        "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
        "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
        "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
        "Symbol", "ZapfDingbats",
    }
    standard_to_family = {
        "Helvetica":         "Arial",
        "Times-Roman":       "Times New Roman",
        "Courier":           "Courier New",
    }

    for page in pdf:
        for fontinfo in page.get_fonts():
            xref, ext, font_type, base_name, _ref = fontinfo[:5]
            if base_name in seen: continue
            seen.add(base_name)

            # Strip subset prefix "AAAAAA+"
            clean = base_name.split("+")[-1] if "+" in base_name else base_name
            is_subset = "+" in base_name

            # Standard 14 - no embedding
            for s in standard_14:
                if clean.startswith(s.split("-")[0]):
                    base = s.split("-")[0]
                    mapping[base_name] = standard_to_family.get(base, base)
                    break
            else:
                # Try local lookup first (for subsets, prefer full local font)
                from edof.engine.text_engine import get_font_path
                local = get_font_path(clean)
                if local and is_subset:
                    # Use local full font, skip embedding subset
                    try:
                        with open(local, "rb") as f: data = f.read()
                        rid = doc.resources.add(data, f"{clean}.ttf", "font/ttf")
                        mapping[base_name] = clean
                        doc._error_state.append(
                            f"Subset font '{base_name}' replaced with local "
                            f"full font '{clean}'")
                    except Exception:
                        mapping[base_name] = clean
                else:
                    # Try to extract from PDF
                    try:
                        info = pdf.extract_font(xref)
                        if isinstance(info, tuple) and len(info) >= 4:
                            font_data = info[3]
                            if font_data and isinstance(font_data, bytes):
                                ext_name = info[1] if info[1] else "ttf"
                                rid = doc.resources.add(
                                    font_data, f"{clean}.{ext_name}",
                                    f"font/{ext_name}")
                                mapping[base_name] = clean
                                if is_subset:
                                    doc._error_state.append(
                                        f"Subset font '{base_name}' embedded "
                                        f"(limited character set)")
                                continue
                    except Exception:
                        pass
                    # Final fallback: use alias system
                    mapping[base_name] = clean
                    doc._error_state.append(
                        f"Font '{base_name}' could not be extracted; "
                        f"will use system fallback for '{clean}'")
    return mapping


# ──────────────────────────────────────────────────────────────────────────────
#  Text span extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_text_spans(pdf_page, font_mapping):
    """Extract all text spans on a page with bbox, font, size, color, flags.

    Returns coordinates in mm (top-left origin).
    """
    page_h = pdf_page.rect.height
    spans  = []
    text_dict = pdf_page.get_text("dict")

    for block in text_dict.get("blocks", []):
        if block.get("type", 0) != 0: continue   # skip image blocks
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span["bbox"]   # (x0, y0, x1, y1) in points, top-left origin in PyMuPDF
                spans.append({
                    "text":  span["text"],
                    "bbox":  (bbox[0] / 72 * 25.4,  # x0 mm
                              bbox[1] / 72 * 25.4,  # y0 mm
                              bbox[2] / 72 * 25.4,  # x1 mm
                              bbox[3] / 72 * 25.4), # y1 mm
                    "font":  font_mapping.get(span["font"], span["font"]),
                    "size":  span["size"],         # in points
                    "color": _decode_color(span.get("color", 0)),
                    "flags": span.get("flags", 0),
                    "bold":  bool(span.get("flags", 0) & 16),
                    "italic":bool(span.get("flags", 0) & 2),
                })
    return spans


def _decode_color(c: int) -> tuple:
    """Decode PDF span color int to (r,g,b)."""
    if c is None or c == 0: return (0, 0, 0)
    r = (c >> 16) & 0xFF
    g = (c >> 8) & 0xFF
    b = c & 0xFF
    return (r, g, b)


# ──────────────────────────────────────────────────────────────────────────────
#  Block clustering — group spans into paragraphs
# ──────────────────────────────────────────────────────────────────────────────

def _cluster_blocks(spans, indent_threshold_mm: float = 3.0):
    """Cluster spans into paragraph blocks using:
      - same font + size (5% tolerance)
      - vertical gap <= line_height * 1.5
      - similar x-alignment
      - line-spacing tolerance for variable gaps within paragraph

    Returns a list of blocks; each block is a list of spans.
    """
    if not spans: return []

    # Sort by Y then X
    spans = sorted(spans, key=lambda s: (s["bbox"][1], s["bbox"][0]))

    blocks = []
    cur_block = []
    cur_line_y = None
    cur_line_h = None

    def _flush():
        nonlocal cur_block
        if cur_block: blocks.append(cur_block); cur_block = []

    for span in spans:
        if not span["text"].strip():
            continue

        if not cur_block:
            cur_block = [span]
            cur_line_y = span["bbox"][1]
            cur_line_h = span["size"] / 72 * 25.4
            continue

        prev = cur_block[-1]
        prev_y = prev["bbox"][1]
        cur_y  = span["bbox"][1]
        # Same line? (y values within ~30% of font height)
        same_line = abs(cur_y - prev_y) < cur_line_h * 0.3

        # Compatible style?
        same_style = (span["font"] == prev["font"] and
                      abs(span["size"] - prev["size"]) < 0.5 and
                      span["color"] == prev["color"] and
                      span["bold"]  == prev["bold"] and
                      span["italic"]== prev["italic"])

        # Next line within paragraph? (y gap <= 1.5 line heights, similar x or indented)
        line_gap = cur_y - (prev["bbox"][3])   # gap from prev line bottom to cur line top
        next_line_close = (line_gap >= -1.0 and line_gap <= cur_line_h * 1.0)

        # Similar X alignment? (within block X range, or within indent threshold)
        block_x = min(s["bbox"][0] for s in cur_block)
        cur_x   = span["bbox"][0]
        x_compatible = (abs(cur_x - block_x) < indent_threshold_mm * 2)

        if same_line:
            cur_block.append(span)
        elif same_style and next_line_close and x_compatible:
            cur_block.append(span)
            cur_line_h = span["size"] / 72 * 25.4
        else:
            _flush()
            cur_block = [span]
            cur_line_h = span["size"] / 72 * 25.4

    _flush()
    return blocks


# ──────────────────────────────────────────────────────────────────────────────
#  Block → TextBox
# ──────────────────────────────────────────────────────────────────────────────

def _block_to_textbox(block, page_h_mm, median_size, heading_threshold):
    """Convert a list of spans (one block) into a TextBox or rich-text TextBox."""
    from edof.format.objects import TextBox
    from edof.format.styles  import TextRun

    if not block: return None

    # Compute bounding box of block (mm)
    x0 = min(s["bbox"][0] for s in block)
    y0 = min(s["bbox"][1] for s in block)
    x1 = max(s["bbox"][2] for s in block)
    y1 = max(s["bbox"][3] for s in block)

    tb = TextBox()
    tb.transform.x      = x0
    tb.transform.y      = y0
    tb.transform.width  = max(x1 - x0, 1.0)
    tb.transform.height = max(y1 - y0, 1.0)

    # Use first span's primary style as parent
    first = block[0]
    tb.style.font_family = first["font"]
    tb.style.font_size   = first["size"]
    tb.style.color       = first["color"]
    tb.style.bold        = first["bold"]
    tb.style.italic      = first["italic"]
    tb.style.padding     = 0.5
    tb.style.wrap        = True

    # Mark heading if font significantly larger than median
    if first["size"] > median_size * heading_threshold:
        tb.tags.append("heading") if hasattr(tb, "tags") else None

    # Determine if all spans share the same style
    all_same = all(
        s["font"]   == first["font"]   and
        abs(s["size"] - first["size"]) < 0.5 and
        s["color"]  == first["color"]  and
        s["bold"]   == first["bold"]   and
        s["italic"] == first["italic"]
        for s in block
    )

    # Reconstruct text by joining spans, preserving line breaks
    if all_same:
        text_parts = []
        prev_y = block[0]["bbox"][1]
        for s in block:
            cur_y = s["bbox"][1]
            if abs(cur_y - prev_y) > s["size"] / 72 * 25.4 * 0.5:
                text_parts.append("\n")
            text_parts.append(s["text"])
            prev_y = cur_y
        tb.text = "".join(text_parts).strip()
    else:
        # Build runs preserving inline formatting differences
        runs = []
        prev_y = block[0]["bbox"][1]
        for s in block:
            cur_y = s["bbox"][1]
            txt = s["text"]
            if abs(cur_y - prev_y) > s["size"] / 72 * 25.4 * 0.5:
                txt = "\n" + txt
            run = TextRun(text=txt)
            if s["font"]   != first["font"]:   run.font_family = s["font"]
            if abs(s["size"] - first["size"]) >= 0.5: run.font_size   = s["size"]
            if s["bold"]   != first["bold"]:   run.bold        = s["bold"]
            if s["italic"] != first["italic"]: run.italic      = s["italic"]
            if s["color"]  != first["color"]:  run.color       = s["color"]
            runs.append(run)
            prev_y = cur_y
        tb.runs = runs

    return tb


# ──────────────────────────────────────────────────────────────────────────────
#  Image extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_images(pdf_page, doc):
    """Extract embedded images on the page."""
    from edof.format.objects import ImageBox
    out = []
    image_list = pdf_page.get_images(full=True)
    for img_info in image_list:
        xref = img_info[0]
        try:
            base_image = pdf_page.parent.extract_image(xref)
            img_data = base_image["image"]
            ext      = base_image["ext"]
            mime     = f"image/{ext}"
            name     = f"img_{xref}.{ext}"

            # Position: pymupdf doesn't directly tell us where the image is rendered;
            # we use page.get_image_rects() if available
            try:
                rects = pdf_page.get_image_rects(xref)
                if not rects: continue
                rect = rects[0]
                x_mm = rect.x0 / 72 * 25.4
                y_mm = rect.y0 / 72 * 25.4
                w_mm = (rect.x1 - rect.x0) / 72 * 25.4
                h_mm = (rect.y1 - rect.y0) / 72 * 25.4
            except Exception:
                continue

            rid = doc.resources.add(img_data, name, mime)
            ib  = ImageBox(resource_id=rid)
            ib.transform.x = x_mm; ib.transform.y = y_mm
            ib.transform.width = w_mm; ib.transform.height = h_mm
            out.append(ib)
        except Exception:
            continue
    return out


# ──────────────────────────────────────────────────────────────────────────────
#  Vector path extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_paths(pdf_page, page_h_mm):
    """Extract vector paths (lines, curves, fills) as Shape objects.

    v4.0.3 fix: previously paths used transform spanning the whole page with
    path_data in absolute coordinates. The renderer worked but the editor
    couldn't select / move them (bbox was the whole page). Now we compute
    the actual path bbox and store coordinates relative to it.
    """
    from edof.format.objects import Shape, SHAPE_PATH
    out = []
    try:
        drawings = pdf_page.get_drawings()
    except Exception:
        return out

    for d in drawings:
        # Collect absolute-coord path
        abs_path = []
        for item in d.get("items", []):
            op = item[0]
            if op == "l":
                p1, p2 = item[1], item[2]
                if not abs_path:
                    abs_path.append(["M", p1.x / 72 * 25.4, p1.y / 72 * 25.4])
                abs_path.append(["L", p2.x / 72 * 25.4, p2.y / 72 * 25.4])
            elif op == "c":
                p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                if not abs_path:
                    abs_path.append(["M", p1.x / 72 * 25.4, p1.y / 72 * 25.4])
                abs_path.append(["C",
                                  p2.x / 72 * 25.4, p2.y / 72 * 25.4,
                                  p3.x / 72 * 25.4, p3.y / 72 * 25.4,
                                  p4.x / 72 * 25.4, p4.y / 72 * 25.4])
            elif op == "re":
                rect = item[1]
                x0 = rect.x0 / 72 * 25.4; y0 = rect.y0 / 72 * 25.4
                x1 = rect.x1 / 72 * 25.4; y1 = rect.y1 / 72 * 25.4
                abs_path.extend([["M", x0, y0], ["L", x1, y0],
                                 ["L", x1, y1], ["L", x0, y1], ["Z"]])

        if not abs_path: continue

        # v4.0.3: compute bbox from path
        xs, ys = [], []
        for cmd in abs_path:
            op = cmd[0]
            if op in ("M", "L"):
                xs.append(cmd[1]); ys.append(cmd[2])
            elif op == "C":
                xs.extend([cmd[1], cmd[3], cmd[5]])
                ys.extend([cmd[2], cmd[4], cmd[6]])
        if not xs:
            continue
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w = max(0.5, max_x - min_x)
        h = max(0.5, max_y - min_y)

        # Translate to local
        path_data = []
        for cmd in abs_path:
            op = cmd[0]
            if op in ("M", "L"):
                path_data.append([op, cmd[1] - min_x, cmd[2] - min_y])
            elif op == "C":
                path_data.append([op,
                                  cmd[1] - min_x, cmd[2] - min_y,
                                  cmd[3] - min_x, cmd[4] - min_y,
                                  cmd[5] - min_x, cmd[6] - min_y])
            else:
                path_data.append(cmd)

        sh = Shape(shape_type=SHAPE_PATH)
        sh.path_data = path_data
        sh.transform.x = min_x
        sh.transform.y = min_y
        sh.transform.width = w
        sh.transform.height = h

        if d.get("fill"):
            c = d["fill"]
            if isinstance(c, (tuple, list)) and len(c) >= 3:
                sh.fill.color = (int(c[0]*255), int(c[1]*255), int(c[2]*255), 255)
        else:
            sh.fill.color = None
        if d.get("color"):
            c = d["color"]
            if isinstance(c, (tuple, list)) and len(c) >= 3:
                sh.stroke.color = (int(c[0]*255), int(c[1]*255), int(c[2]*255), 255)
        sh.stroke.width = d.get("width", 0.5) or 0.5
        out.append(sh)
    return out


# ──────────────────────────────────────────────────────────────────────────────
#  Table detection (heuristic, requires pdfplumber)
# ──────────────────────────────────────────────────────────────────────────────

def _detect_tables(pdf_page, page_h_mm):
    """Optional: detect tables using pdfplumber heuristics."""
    try:
        import pdfplumber
    except ImportError:
        return []

    out = []
    pdf_path = pdf_page.parent.name
    page_idx = pdf_page.number
    try:
        with pdfplumber.open(pdf_path) as pp:
            page = pp.pages[page_idx]
            tables = page.find_tables()
            for tbl in tables:
                bbox = tbl.bbox
                rows_data = tbl.extract()
                if not rows_data: continue
                from edof.format.objects import Table, TableCell
                t = Table()
                t.transform.x      = bbox[0] / 72 * 25.4
                t.transform.y      = bbox[1] / 72 * 25.4
                t.transform.width  = (bbox[2] - bbox[0]) / 72 * 25.4
                t.transform.height = (bbox[3] - bbox[1]) / 72 * 25.4
                t.cells = [[TableCell(text=str(c) if c else "")
                             for c in row] for row in rows_data]
                # Style first row as header
                if t.cells:
                    for c in t.cells[0]:
                        c.style.bold = True
                        c.bg_color = (245, 245, 250, 255)
                out.append(t)
    except Exception:
        pass
    return out
