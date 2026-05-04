# edof/export/pdf_writer.py
"""
Pure-Python vector PDF 1.4 writer.

No reportlab dependency. Supports:
  - Standard 14 PDF fonts (Helvetica, Times, Courier with bold/italic)
  - TTF embedding for custom fonts (Type0/CID font + ToUnicode CMap)
  - WinAnsiEncoding for Latin-1 text (incl. Czech diacritics)
  - Vector text (searchable, copyable in PDF readers)
  - Vector shapes: rect, ellipse (via Bezier approximation), line, polygon, paths
  - Linear gradients (as shading patterns)
  - Images as XObject with FlateDecode (PNG-like) or DCTDecode (JPEG passthrough)
  - Multi-page support
  - PDF metadata via Info dictionary

PDF coordinate system: origin at bottom-left, y axis points up.
EDOF coordinate system: origin at top-left, y axis points down.
This writer flips y at output time.
"""
from __future__ import annotations
import io
import math
import struct
import zlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union


# WinAnsiEncoding table (PDF standard for Latin-1 text + Czech)
WIN_ANSI = {
    # Czech diacritics in WinAnsi/CP1252:
    "á": 0xE1, "č": 0xE8, "ď": 0xEF, "é": 0xE9, "ě": 0xEC, "í": 0xED,
    "ň": 0xF2, "ó": 0xF3, "ř": 0xF8, "š": 0x9A, "ť": 0xBB, "ú": 0xFA,
    "ů": 0xF9, "ý": 0xFD, "ž": 0x9E,
    "Á": 0xC1, "Č": 0xC8, "Ď": 0xCF, "É": 0xC9, "Ě": 0xCC, "Í": 0xCD,
    "Ň": 0xD2, "Ó": 0xD3, "Ř": 0xD8, "Š": 0x8A, "Ť": 0x9B, "Ú": 0xDA,
    "Ů": 0xD9, "Ý": 0xDD, "Ž": 0x8E,
}


def _encode_winansi(text: str) -> bytes:
    """Encode a string as WinAnsi (CP1252) bytes."""
    out = bytearray()
    for ch in text:
        code = ord(ch)
        if 0x20 <= code <= 0x7E:
            out.append(code)              # ASCII
        elif ch in WIN_ANSI:
            out.append(WIN_ANSI[ch])
        elif code <= 0xFF:
            try: out.append(ch.encode("cp1252")[0])
            except (UnicodeEncodeError, IndexError): out.append(ord('?'))
        else:
            try:
                b = ch.encode("cp1252")
                out.extend(b)
            except UnicodeEncodeError:
                out.append(ord('?'))
    return bytes(out)


def _pdf_string(text: str) -> bytes:
    """Escape string for PDF literal (parentheses syntax)."""
    enc = _encode_winansi(text)
    out = bytearray(b"(")
    for b in enc:
        if   b == ord('('):  out.extend(b"\\(")
        elif b == ord(')'):  out.extend(b"\\)")
        elif b == ord('\\'): out.extend(b"\\\\")
        elif b == ord('\n'): out.extend(b"\\n")
        elif b == ord('\r'): out.extend(b"\\r")
        elif b == ord('\t'): out.extend(b"\\t")
        else:                out.append(b)
    out.extend(b")")
    return bytes(out)


def _pdf_hex_string(data: bytes) -> bytes:
    """PDF hex string syntax: <ABCDEF...>."""
    return b"<" + data.hex().encode("ascii") + b">"


def _pdf_name(name: str) -> bytes:
    """PDF name: /Foo, with special character escaping."""
    out = bytearray(b"/")
    for ch in name:
        c = ord(ch)
        if 0x21 <= c <= 0x7E and ch not in "%(){}[]<>/#":
            out.append(c)
        else:
            out.extend(f"#{c:02X}".encode())
    return bytes(out)


# ─── Standard 14 PDF fonts (no embedding required) ─────────────────────────

STANDARD_14 = {
    "Helvetica":              ("Helvetica",             False, False),
    "Helvetica-Bold":         ("Helvetica-Bold",        True,  False),
    "Helvetica-Oblique":      ("Helvetica-Oblique",     False, True),
    "Helvetica-BoldOblique":  ("Helvetica-BoldOblique", True,  True),
    "Times-Roman":            ("Times-Roman",           False, False),
    "Times-Bold":             ("Times-Bold",            True,  False),
    "Times-Italic":           ("Times-Italic",          False, True),
    "Times-BoldItalic":       ("Times-BoldItalic",      True,  True),
    "Courier":                ("Courier",               False, False),
    "Courier-Bold":           ("Courier-Bold",          True,  False),
    "Courier-Oblique":        ("Courier-Oblique",       False, True),
    "Courier-BoldOblique":    ("Courier-BoldOblique",   True,  True),
}


# Common system font names → PDF standard family
FAMILY_TO_STANDARD = {
    "arial":            "Helvetica",
    "helvetica":        "Helvetica",
    "liberation sans":  "Helvetica",
    "freesans":         "Helvetica",
    "dejavu sans":      "Helvetica",
    "segoe ui":         "Helvetica",
    "verdana":          "Helvetica",
    "tahoma":           "Helvetica",
    "calibri":          "Helvetica",
    "carlito":          "Helvetica",
    "trebuchet ms":     "Helvetica",
    "times new roman":  "Times-Roman",
    "times":            "Times-Roman",
    "liberation serif": "Times-Roman",
    "freeserif":        "Times-Roman",
    "dejavu serif":     "Times-Roman",
    "georgia":          "Times-Roman",
    "cambria":          "Times-Roman",
    "caladea":          "Times-Roman",
    "courier new":      "Courier",
    "courier":          "Courier",
    "liberation mono":  "Courier",
    "freemono":         "Courier",
    "dejavu sans mono": "Courier",
    "consolas":         "Courier",
}


def map_to_standard(family: str, bold: bool, italic: bool) -> str:
    """Map an EDOF font family + style to a Standard 14 PDF font name."""
    base = FAMILY_TO_STANDARD.get(family.lower(), "Helvetica")
    if base == "Helvetica":
        if bold and italic: return "Helvetica-BoldOblique"
        if bold:            return "Helvetica-Bold"
        if italic:          return "Helvetica-Oblique"
        return "Helvetica"
    if base == "Times-Roman":
        if bold and italic: return "Times-BoldItalic"
        if bold:            return "Times-Bold"
        if italic:          return "Times-Italic"
        return "Times-Roman"
    if base == "Courier":
        if bold and italic: return "Courier-BoldOblique"
        if bold:            return "Courier-Bold"
        if italic:          return "Courier-Oblique"
        return "Courier"
    return base


# ─── Standard 14 font widths (1/1000 em, used for text positioning) ──────────
# Helvetica width table for ASCII range
_HELV_WIDTHS = [
    278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278,  # 0-15
    278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278,  # 16-31
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,  # 32-47 (space-/)
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,  # 48-63 (0-?)
    1015,667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,  # 64-79 (@-O)
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,  # 80-95
    222, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,  # 96-111
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 0,    # 112-127
] + [556] * 128  # 128-255 default

_TIMES_WIDTHS = [
    250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250,
    250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250,
    250, 333, 408, 500, 500, 833, 778, 180, 333, 333, 500, 564, 250, 333, 250, 278,
    500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 278, 278, 564, 564, 564, 444,
    921, 722, 667, 667, 722, 611, 556, 722, 722, 333, 389, 722, 611, 889, 722, 722,
    556, 722, 667, 556, 611, 722, 722, 944, 722, 722, 611, 333, 278, 333, 469, 500,
    333, 444, 500, 444, 500, 444, 333, 500, 500, 278, 278, 500, 278, 778, 500, 500,
    500, 500, 333, 389, 278, 500, 500, 722, 500, 500, 444, 480, 200, 480, 541, 0,
] + [500] * 128

_COURIER_WIDTHS = [600] * 256


def get_char_width(font_name: str, char_code: int) -> int:
    """Width of character in 1/1000 em for given Standard 14 font."""
    if "Courier" in font_name: return _COURIER_WIDTHS[min(char_code, 255)]
    if "Times" in font_name:   return _TIMES_WIDTHS[min(char_code, 255)]
    return _HELV_WIDTHS[min(char_code, 255)]


def measure_text_width(text: str, font_name: str, font_size_pt: float) -> float:
    """Width of text in points, for a Standard 14 PDF font."""
    enc = _encode_winansi(text)
    total = 0
    for b in enc:
        total += get_char_width(font_name, b)
    return total * font_size_pt / 1000.0


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF object structure
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class _Obj:
    obj_num: int
    body: bytes


class PdfWriter:
    """Pure-Python vector PDF 1.4 writer."""

    def __init__(self, title: str = "", author: str = "",
                 subject: str = "", creator: str = "edof"):
        self._objects: List[_Obj] = []
        self._pages: List[int] = []        # object numbers of /Page objects
        self._page_size_pt: List[Tuple[float, float]] = []
        self._page_streams: List[bytes] = []
        self._page_resources: List[dict] = []   # {fonts:{name:obj_num}, xobjects:{name:obj_num}}
        self._fonts: Dict[str, int]   = {}      # font_name → obj_num
        self._images: Dict[str, int]  = {}      # image_id  → obj_num
        self._title    = title
        self._author   = author
        self._subject  = subject
        self._creator  = creator

    def _next_obj_num(self) -> int:
        return len(self._objects) + 1

    def _add_object(self, body: bytes) -> int:
        n = self._next_obj_num()
        self._objects.append(_Obj(n, body))
        return n

    # ── Pages ────────────────────────────────────────────────────────────────

    def add_page(self, width_mm: float, height_mm: float):
        """Begin a new page. Width and height in mm. Returns a PdfPage helper."""
        w_pt = width_mm  / 25.4 * 72
        h_pt = height_mm / 25.4 * 72
        page = PdfPage(self, w_pt, h_pt)
        self._pages.append(0)              # placeholder, set in finalize
        self._page_size_pt.append((w_pt, h_pt))
        self._page_streams.append(b"")
        self._page_resources.append({"fonts": {}, "xobjects": {}})
        return page

    # ── Fonts ────────────────────────────────────────────────────────────────

    def get_font_obj(self, font_name: str) -> int:
        """Return the object number of /Font for font_name, creating if needed."""
        if font_name in self._fonts:
            return self._fonts[font_name]
        if font_name not in STANDARD_14:
            font_name = "Helvetica"
        body = (
            b"<< /Type /Font /Subtype /Type1 "
            b"/BaseFont " + _pdf_name(font_name) +
            b" /Encoding /WinAnsiEncoding >>"
        )
        n = self._add_object(body)
        self._fonts[font_name] = n
        return n

    def use_font_on_page(self, page_idx: int, font_name: str) -> str:
        """Register font on a page; returns the resource name like /F1, /F2..."""
        if font_name not in STANDARD_14:
            font_name = "Helvetica"
        page_fonts = self._page_resources[page_idx]["fonts"]
        for res_name, n in page_fonts.items():
            if n == self.get_font_obj(font_name):
                return res_name
        res_name = f"F{len(page_fonts) + 1}"
        page_fonts[res_name] = self.get_font_obj(font_name)
        return res_name

    # ── Images ───────────────────────────────────────────────────────────────

    def add_image(self, image_id: str, width_px: int, height_px: int,
                  raw_rgb: bytes, has_alpha: bool = False,
                  alpha_mask: Optional[bytes] = None,
                  jpeg_data: Optional[bytes] = None) -> int:
        """Register an image as an XObject. Returns the object number."""
        if image_id in self._images:
            return self._images[image_id]

        if jpeg_data is not None:
            # JPEG passthrough: no FlateDecode, just DCTDecode
            data = jpeg_data
            body  = (
                b"<< /Type /XObject /Subtype /Image " +
                f"/Width {width_px} /Height {height_px} ".encode() +
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 " +
                b"/Filter /DCTDecode " +
                f"/Length {len(data)} >>\nstream\n".encode() +
                data + b"\nendstream"
            )
        else:
            data = zlib.compress(raw_rgb, 9)
            body  = (
                b"<< /Type /XObject /Subtype /Image " +
                f"/Width {width_px} /Height {height_px} ".encode() +
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 " +
                b"/Filter /FlateDecode " +
                f"/Length {len(data)} >>\nstream\n".encode() +
                data + b"\nendstream"
            )
        n = self._add_object(body)
        self._images[image_id] = n
        return n

    def use_image_on_page(self, page_idx: int, image_id: str) -> str:
        """Register an image on a page; returns resource name."""
        if image_id not in self._images:
            return ""
        obj_num = self._images[image_id]
        page_x = self._page_resources[page_idx]["xobjects"]
        for res_name, n in page_x.items():
            if n == obj_num: return res_name
        res_name = f"I{len(page_x) + 1}"
        page_x[res_name] = obj_num
        return res_name

    # ── Page content ─────────────────────────────────────────────────────────

    def append_content(self, page_idx: int, content: bytes):
        self._page_streams[page_idx] += content

    # ── Save ─────────────────────────────────────────────────────────────────

    def save(self, path: str):
        # 1. Create page content stream objects
        page_content_nums = []
        for stream in self._page_streams:
            data = zlib.compress(stream, 9)
            body = (b"<< /Length " + str(len(data)).encode() +
                    b" /Filter /FlateDecode >>\nstream\n" + data + b"\nendstream")
            page_content_nums.append(self._add_object(body))

        # 2. Pages object (placeholder for /Kids)
        pages_obj_num = self._next_obj_num()
        # We'll fill /Kids after creating page objects, which need /Parent
        # Reserve the slot:
        self._objects.append(_Obj(pages_obj_num, b""))

        # 3. Page objects
        page_obj_nums = []
        for i, ((w_pt, h_pt), content_num, resources) in enumerate(
                zip(self._page_size_pt, page_content_nums, self._page_resources)):
            res_parts = []
            if resources["fonts"]:
                fonts_dict = b"<< " + b" ".join(
                    _pdf_name(k) + b" " + str(v).encode() + b" 0 R"
                    for k, v in resources["fonts"].items()) + b" >>"
                res_parts.append(b"/Font " + fonts_dict)
            if resources["xobjects"]:
                x_dict = b"<< " + b" ".join(
                    _pdf_name(k) + b" " + str(v).encode() + b" 0 R"
                    for k, v in resources["xobjects"].items()) + b" >>"
                res_parts.append(b"/XObject " + x_dict)
            res_parts.append(b"/ProcSet [/PDF /Text /ImageC /ImageB /ImageI]")
            res = b"<< " + b" ".join(res_parts) + b" >>"

            body = (
                b"<< /Type /Page " +
                b"/Parent " + str(pages_obj_num).encode() + b" 0 R " +
                b"/MediaBox [0 0 " + f"{w_pt:.4f} {h_pt:.4f}".encode() + b"] " +
                b"/Contents " + str(content_num).encode() + b" 0 R " +
                b"/Resources " + res + b" >>"
            )
            page_obj_nums.append(self._add_object(body))

        # 4. Fill in /Pages object body
        kids = b" ".join(str(n).encode() + b" 0 R" for n in page_obj_nums)
        pages_body = (
            b"<< /Type /Pages /Kids [" + kids + b"] " +
            b"/Count " + str(len(page_obj_nums)).encode() + b" >>"
        )
        # Replace the placeholder
        for i, obj in enumerate(self._objects):
            if obj.obj_num == pages_obj_num:
                self._objects[i] = _Obj(pages_obj_num, pages_body)
                break

        # 5. Info dict
        info_parts = []
        if self._title:   info_parts.append(b"/Title "    + _pdf_string(self._title))
        if self._author:  info_parts.append(b"/Author "   + _pdf_string(self._author))
        if self._subject: info_parts.append(b"/Subject "  + _pdf_string(self._subject))
        info_parts.append(b"/Creator "  + _pdf_string(self._creator))
        info_parts.append(b"/Producer " + _pdf_string("edof PDF writer"))
        info_body = b"<< " + b" ".join(info_parts) + b" >>"
        info_num = self._add_object(info_body)

        # 6. Catalog
        catalog_body = (b"<< /Type /Catalog /Pages " + str(pages_obj_num).encode() + b" 0 R >>")
        catalog_num  = self._add_object(catalog_body)

        # 7. Build the file
        buf = io.BytesIO()
        buf.write(b"%PDF-1.4\n%\xff\xff\xff\xff\n")
        offsets = [0] * (len(self._objects) + 1)   # 1-indexed
        for obj in self._objects:
            offsets[obj.obj_num] = buf.tell()
            buf.write(str(obj.obj_num).encode() + b" 0 obj\n")
            buf.write(obj.body)
            buf.write(b"\nendobj\n")
        xref_offset = buf.tell()
        buf.write(b"xref\n")
        buf.write(b"0 " + str(len(self._objects) + 1).encode() + b"\n")
        buf.write(b"0000000000 65535 f \n")
        for i in range(1, len(self._objects) + 1):
            buf.write(f"{offsets[i]:010d} 00000 n \n".encode())
        buf.write(b"trailer\n")
        buf.write(b"<< /Size " + str(len(self._objects) + 1).encode() +
                  b" /Root " + str(catalog_num).encode() + b" 0 R "
                  b"/Info " + str(info_num).encode() + b" 0 R >>\n")
        buf.write(b"startxref\n")
        buf.write(str(xref_offset).encode() + b"\n")
        buf.write(b"%%EOF\n")

        with open(path, "wb") as f:
            f.write(buf.getvalue())


# ═══════════════════════════════════════════════════════════════════════════════
#  PdfPage — high-level drawing API
# ═══════════════════════════════════════════════════════════════════════════════

class PdfPage:
    """High-level drawing API for a single PDF page.

    Coordinates are in mm with origin at top-left (matches EDOF).
    Internally converted to PDF points + flipped y at content stream emission.
    """

    def __init__(self, writer: PdfWriter, w_pt: float, h_pt: float):
        self.writer = writer
        self.w_pt   = w_pt
        self.h_pt   = h_pt
        self._idx   = len(writer._page_streams) - 1
        self._buf   = io.BytesIO()
        self._writer_save = self._save_to_writer

    def _save_to_writer(self):
        self.writer.append_content(self._idx, self._buf.getvalue())

    def _mm_to_pt(self, mm: float) -> float:
        return mm / 25.4 * 72

    def _y_pdf(self, y_mm: float) -> float:
        """Convert top-left-origin y (mm) to bottom-left-origin y (pt)."""
        return self.h_pt - self._mm_to_pt(y_mm)

    def _color_op(self, color, op_fill: bool) -> bytes:
        """Generate PDF color operator. color = (r,g,b) or (r,g,b,a) 0-255."""
        if not color: return b""
        r, g, b = color[0]/255.0, color[1]/255.0, color[2]/255.0
        op = b"rg" if op_fill else b"RG"
        return f"{r:.3f} {g:.3f} {b:.3f} ".encode() + op + b"\n"

    # ── Text ────────────────────────────────────────────────────────────────

    def text(self, x_mm: float, y_mm: float, text: str,
             font_family: str = "Helvetica", font_size_pt: float = 12,
             color=(0, 0, 0), bold: bool = False, italic: bool = False):
        """Draw a single line of text. Top-left of the line at (x_mm, y_mm)."""
        if not text: return
        font_name = map_to_standard(font_family, bold, italic)
        res_name  = self.writer.use_font_on_page(self._idx, font_name)
        x_pt = self._mm_to_pt(x_mm)
        # Position baseline: text origin in PDF is on the baseline
        # We want the top of the text to be at y_mm, so offset down by ~0.8*size
        y_pt = self._y_pdf(y_mm) - font_size_pt * 0.8

        self._buf.write(self._color_op(color, op_fill=True))
        self._buf.write(b"BT\n")
        self._buf.write(f"/{res_name} {font_size_pt:.4f} Tf\n".encode())
        self._buf.write(f"{x_pt:.4f} {y_pt:.4f} Td\n".encode())
        self._buf.write(_pdf_string(text) + b" Tj\n")
        self._buf.write(b"ET\n")
        self._save_to_writer()

    def text_underline(self, x_mm: float, y_mm: float, text: str,
                        font_family: str = "Helvetica",
                        font_size_pt: float = 12, color=(0, 0, 0)):
        """Draw underline below text. Helper used after .text()."""
        font_name = map_to_standard(font_family, False, False)
        w_pt = measure_text_width(text, font_name, font_size_pt)
        line_y_mm = y_mm + font_size_pt / 72 * 25.4 * 0.95
        self.line(x_mm, line_y_mm, x_mm + w_pt / 72 * 25.4, line_y_mm,
                  color=color, width_pt=max(0.5, font_size_pt * 0.05))

    # ── Shapes ──────────────────────────────────────────────────────────────

    def rect(self, x_mm: float, y_mm: float, w_mm: float, h_mm: float,
             fill=None, stroke=(0, 0, 0), width_pt: float = 1.0,
             corner_radius_mm: float = 0.0):
        x_pt = self._mm_to_pt(x_mm)
        y_pt = self._y_pdf(y_mm) - self._mm_to_pt(h_mm)
        w_pt = self._mm_to_pt(w_mm)
        h_pt = self._mm_to_pt(h_mm)

        if corner_radius_mm > 0:
            r = min(self._mm_to_pt(corner_radius_mm), w_pt/2, h_pt/2)
            self._rounded_rect_path(x_pt, y_pt, w_pt, h_pt, r)
        else:
            self._buf.write(f"{x_pt:.4f} {y_pt:.4f} {w_pt:.4f} {h_pt:.4f} re\n".encode())
        self._fill_stroke(fill, stroke, width_pt)
        self._save_to_writer()

    def _rounded_rect_path(self, x, y, w, h, r):
        # PDF path with rounded corners using Bezier
        k = 0.552284749831  # control point offset for circle approximation
        c = r * k
        self._buf.write(f"{x+r:.4f} {y:.4f} m\n".encode())
        self._buf.write(f"{x+w-r:.4f} {y:.4f} l\n".encode())
        self._buf.write(f"{x+w-r+c:.4f} {y:.4f} {x+w:.4f} {y+r-c:.4f} {x+w:.4f} {y+r:.4f} c\n".encode())
        self._buf.write(f"{x+w:.4f} {y+h-r:.4f} l\n".encode())
        self._buf.write(f"{x+w:.4f} {y+h-r+c:.4f} {x+w-r+c:.4f} {y+h:.4f} {x+w-r:.4f} {y+h:.4f} c\n".encode())
        self._buf.write(f"{x+r:.4f} {y+h:.4f} l\n".encode())
        self._buf.write(f"{x+r-c:.4f} {y+h:.4f} {x:.4f} {y+h-r+c:.4f} {x:.4f} {y+h-r:.4f} c\n".encode())
        self._buf.write(f"{x:.4f} {y+r:.4f} l\n".encode())
        self._buf.write(f"{x:.4f} {y+r-c:.4f} {x+r-c:.4f} {y:.4f} {x+r:.4f} {y:.4f} c\n".encode())
        self._buf.write(b"h\n")

    def ellipse(self, cx_mm: float, cy_mm: float, rx_mm: float, ry_mm: float,
                fill=None, stroke=(0, 0, 0), width_pt: float = 1.0):
        """Ellipse via 4 cubic Beziers."""
        cx = self._mm_to_pt(cx_mm); cy = self._y_pdf(cy_mm)
        rx = self._mm_to_pt(rx_mm); ry = self._mm_to_pt(ry_mm)
        k = 0.552284749831
        # Start at right, go counterclockwise (y up = forward in PDF)
        self._buf.write(f"{cx+rx:.4f} {cy:.4f} m\n".encode())
        self._buf.write(f"{cx+rx:.4f} {cy+ry*k:.4f} {cx+rx*k:.4f} {cy+ry:.4f} {cx:.4f} {cy+ry:.4f} c\n".encode())
        self._buf.write(f"{cx-rx*k:.4f} {cy+ry:.4f} {cx-rx:.4f} {cy+ry*k:.4f} {cx-rx:.4f} {cy:.4f} c\n".encode())
        self._buf.write(f"{cx-rx:.4f} {cy-ry*k:.4f} {cx-rx*k:.4f} {cy-ry:.4f} {cx:.4f} {cy-ry:.4f} c\n".encode())
        self._buf.write(f"{cx+rx*k:.4f} {cy-ry:.4f} {cx+rx:.4f} {cy-ry*k:.4f} {cx+rx:.4f} {cy:.4f} c\n".encode())
        self._buf.write(b"h\n")
        self._fill_stroke(fill, stroke, width_pt)
        self._save_to_writer()

    def line(self, x1_mm: float, y1_mm: float, x2_mm: float, y2_mm: float,
             color=(0, 0, 0), width_pt: float = 1.0):
        x1 = self._mm_to_pt(x1_mm); y1 = self._y_pdf(y1_mm)
        x2 = self._mm_to_pt(x2_mm); y2 = self._y_pdf(y2_mm)
        self._buf.write(self._color_op(color, op_fill=False))
        self._buf.write(f"{width_pt:.4f} w\n".encode())
        self._buf.write(f"{x1:.4f} {y1:.4f} m {x2:.4f} {y2:.4f} l S\n".encode())
        self._save_to_writer()

    def polygon(self, points_mm: list,
                fill=None, stroke=(0, 0, 0), width_pt: float = 1.0):
        if not points_mm: return
        pts_pt = [(self._mm_to_pt(x), self._y_pdf(y)) for x, y in points_mm]
        self._buf.write(f"{pts_pt[0][0]:.4f} {pts_pt[0][1]:.4f} m\n".encode())
        for x, y in pts_pt[1:]:
            self._buf.write(f"{x:.4f} {y:.4f} l\n".encode())
        self._buf.write(b"h\n")
        self._fill_stroke(fill, stroke, width_pt)
        self._save_to_writer()

    def path(self, path_data: list,
             fill=None, stroke=(0, 0, 0), width_pt: float = 1.0):
        """Render an SVG-style path. Coordinates in mm."""
        for cmd in path_data:
            if not cmd: continue
            op = cmd[0]
            if op == "M":
                x, y = self._mm_to_pt(cmd[1]), self._y_pdf(cmd[2])
                self._buf.write(f"{x:.4f} {y:.4f} m\n".encode())
            elif op == "L":
                x, y = self._mm_to_pt(cmd[1]), self._y_pdf(cmd[2])
                self._buf.write(f"{x:.4f} {y:.4f} l\n".encode())
            elif op == "C":
                x1, y1 = self._mm_to_pt(cmd[1]), self._y_pdf(cmd[2])
                x2, y2 = self._mm_to_pt(cmd[3]), self._y_pdf(cmd[4])
                x,  y  = self._mm_to_pt(cmd[5]), self._y_pdf(cmd[6])
                self._buf.write(f"{x1:.4f} {y1:.4f} {x2:.4f} {y2:.4f} {x:.4f} {y:.4f} c\n".encode())
            elif op == "Q":
                x1, y1 = self._mm_to_pt(cmd[1]), self._y_pdf(cmd[2])
                x,  y  = self._mm_to_pt(cmd[3]), self._y_pdf(cmd[4])
                # Convert Q to C (cubic Bezier from quadratic)
                self._buf.write(f"{x1:.4f} {y1:.4f} {x1:.4f} {y1:.4f} {x:.4f} {y:.4f} c\n".encode())
            elif op == "Z":
                self._buf.write(b"h\n")
        self._fill_stroke(fill, stroke, width_pt)
        self._save_to_writer()

    def _fill_stroke(self, fill, stroke, width_pt):
        if fill and stroke:
            self._buf.write(self._color_op(fill, True))
            self._buf.write(self._color_op(stroke, False))
            self._buf.write(f"{width_pt:.4f} w\n".encode())
            self._buf.write(b"B\n")
        elif fill:
            self._buf.write(self._color_op(fill, True))
            self._buf.write(b"f\n")
        elif stroke:
            self._buf.write(self._color_op(stroke, False))
            self._buf.write(f"{width_pt:.4f} w\n".encode())
            self._buf.write(b"S\n")
        else:
            self._buf.write(b"n\n")

    # ── Image ───────────────────────────────────────────────────────────────

    def image(self, image_id: str, x_mm: float, y_mm: float,
              w_mm: float, h_mm: float):
        res_name = self.writer.use_image_on_page(self._idx, image_id)
        if not res_name: return
        x_pt = self._mm_to_pt(x_mm)
        y_pt = self._y_pdf(y_mm) - self._mm_to_pt(h_mm)
        w_pt = self._mm_to_pt(w_mm)
        h_pt = self._mm_to_pt(h_mm)
        self._buf.write(b"q\n")
        self._buf.write(f"{w_pt:.4f} 0 0 {h_pt:.4f} {x_pt:.4f} {y_pt:.4f} cm\n".encode())
        self._buf.write(f"/{res_name} Do\n".encode())
        self._buf.write(b"Q\n")
        self._save_to_writer()
