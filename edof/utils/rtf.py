"""
RTF (Rich Text Format) import / export for edof.
v4.0.3 — best-effort conversion between RTF documents and edof documents.

Mapping:
  RTF document        ↔  edof.Document with one or more A4 pages
  RTF paragraph       ↔  TextBox (one per paragraph, vertically stacked)
  RTF inline runs     ↔  TextRun (bold, italic, underline, font size, color)
  RTF \\page          ↔  new edof Page

Limitations:
  - This implementation handles paragraph-level layout (each paragraph becomes
    a TextBox). It does NOT preserve every tiny bit of RTF formatting.
  - Tables, images, fields, comments, and footnotes are NOT supported.
  - Colour table is parsed but only foreground colour is mapped per run.
  - Font table is parsed; a single fallback font name is used for the document.
  - Word-style indentation, lists, and tabs are dropped (paragraph text only).

Usage:
    import edof
    doc = edof.import_rtf("input.rtf")
    doc.save("output.edof")

    doc = edof.load("template.edof")
    doc.export_rtf("output.rtf")
"""
from __future__ import annotations

import re
from typing import List, Tuple

# ──────────────────────────────────────────────────────────────────────────────
#  RTF → edof
# ──────────────────────────────────────────────────────────────────────────────

def _parse_rtf_color_table(text: str) -> List[Tuple[int, int, int]]:
    """Extract colour table: \\colortbl;\\red0\\green0\\blue0;…"""
    m = re.search(r"\\colortbl\s*;((?:[^}]|\\[^;])*)\s*\}", text)
    if not m:
        return [(0, 0, 0)]
    body = m.group(1)
    out = [(0, 0, 0)]
    for entry in body.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        r = re.search(r"\\red(\d+)", entry)
        g = re.search(r"\\green(\d+)", entry)
        b = re.search(r"\\blue(\d+)", entry)
        out.append((
            int(r.group(1)) if r else 0,
            int(g.group(1)) if g else 0,
            int(b.group(1)) if b else 0,
        ))
    return out


def _decode_rtf_unicode(s: str) -> str:
    """Decode \\uNNNN? sequences and \\'XX hex sequences."""
    # \uNNNN? form — RTF unicode (signed 16-bit)
    def _u(m):
        n = int(m.group(1))
        if n < 0:
            n += 65536
        try:
            return chr(n)
        except ValueError:
            return ""
    s = re.sub(r"\\u(-?\d+)\??", _u, s)
    # \'XX hex (cp1252 by default)
    def _h(m):
        try:
            return bytes([int(m.group(1), 16)]).decode("cp1252", errors="replace")
        except Exception:
            return ""
    s = re.sub(r"\\'([0-9a-fA-F]{2})", _h, s)
    return s


def _strip_rtf_groups(text: str, group_names) -> str:
    """Remove RTF groups by destination name (e.g. fonttbl, stylesheet, info)."""
    # Also handle \*\groupname (ignored destination groups)
    for name in group_names:
        # Optional \* prefix and \groupname
        pat = re.compile(r"\{(?:\\\*)?\\" + name + r"\b[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")
        prev = None
        while text != prev:
            prev = text
            text = pat.sub("", text)
    return text


def import_rtf(path: str):
    """Read an RTF file and return an edof.Document.

    Each non-empty paragraph becomes a TextBox stacked vertically. Inline runs
    preserve bold/italic/underline/size/color.
    """
    import edof
    from edof.format.objects import TextBox
    from edof.format.styles import TextRun

    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("cp1252", errors="replace")

    # Quick sanity check
    if not text.lstrip().startswith("{\\rtf"):
        raise ValueError(f"{path} does not look like an RTF file (missing \\rtf header)")

    # Parse colour table BEFORE stripping groups
    colors = _parse_rtf_color_table(text)

    # Strip non-content groups
    text = _strip_rtf_groups(text, [
        "fonttbl", "colortbl", "stylesheet", "info", "generator",
        "header", "footer",
    ])
    # Decode unicode sequences
    text = _decode_rtf_unicode(text)

    # Now we tokenise the cleaned RTF body. We simulate a simple state machine:
    # - track current run formatting (bold, italic, underline, font size, color index)
    # - on \par, finish current paragraph
    # - on plain text, append to current run
    state = {
        "bold": False, "italic": False, "underline": False,
        "size_half": 24,    # half-points; default = 12pt
        "color_idx": 0,
    }
    state_stack: List[dict] = []

    paragraphs: List[List[TextRun]] = [[]]
    page_break_indices: List[int] = []  # indices in paragraphs where \page occurred

    # Token regex: control word, control symbol, group brace, or plain text
    token_re = re.compile(
        r"\\([a-zA-Z]+)(-?\d+)?\s?"           # 1: name, 2: param, optional space
        r"|\\([^a-zA-Z*])"                     # 3: control symbol
        r"|(\{)"
        r"|(\})"
        r"|([^\\{}]+)"
    )

    cur_run_text = []

    def flush_run():
        nonlocal cur_run_text
        if not cur_run_text:
            return
        s = "".join(cur_run_text)
        cur_run_text = []
        if not s:
            return
        color = (0, 0, 0)
        if 0 <= state["color_idx"] < len(colors):
            color = colors[state["color_idx"]]
        run = TextRun(
            text=s,
            font_size=float(state["size_half"]) / 2.0,
            bold=state["bold"],
            italic=state["italic"],
            underline=state["underline"],
            color=color,
        )
        paragraphs[-1].append(run)

    def end_para():
        flush_run()
        paragraphs.append([])

    for m in token_re.finditer(text):
        cw, param, sym, ob, cb, plain = m.groups()
        if cw:
            flush_run()
            n = cw.lower()
            if n == "par":
                end_para()
            elif n == "page":
                # Flush current paragraph and mark page break
                end_para()
                page_break_indices.append(len(paragraphs) - 1)
            elif n == "b":
                state["bold"] = (param != "0")
            elif n == "i":
                state["italic"] = (param != "0")
            elif n == "ul":
                state["underline"] = True
            elif n == "ulnone":
                state["underline"] = False
            elif n == "fs":
                if param:
                    try: state["size_half"] = int(param)
                    except: pass
            elif n == "cf":
                if param:
                    try: state["color_idx"] = int(param)
                    except: pass
            elif n == "plain":
                state.update(bold=False, italic=False, underline=False,
                             size_half=24, color_idx=0)
            elif n == "tab":
                cur_run_text.append("\t")
            elif n == "line":
                cur_run_text.append("\n")
            # Many other control words ignored silently
        elif sym:
            # \\ \{ \} are literal characters
            if sym in ("\\", "{", "}"):
                cur_run_text.append(sym)
            # Other symbols ignored
        elif ob:
            flush_run()
            state_stack.append(state.copy())
        elif cb:
            flush_run()
            if state_stack:
                state = state_stack.pop()
        elif plain:
            cur_run_text.append(plain)

    flush_run()

    # Build the Document — stack textboxes vertically across A4 pages
    doc = edof.Document(width=210, height=297, title="Imported from RTF")
    page = doc.add_page()

    # Layout config (mm)
    margin_top = 20
    margin_left = 20
    text_width = 170
    line_height_factor = 1.4
    cur_y = margin_top
    page_h_avail = 297 - 20  # bottom margin

    for i, runs in enumerate(paragraphs):
        if i in page_break_indices:
            page = doc.add_page()
            cur_y = margin_top

        if not runs:
            cur_y += 4   # blank paragraph spacing
            continue

        # Estimate height needed
        max_size = max((r.font_size or 12) for r in runs) if runs else 12
        approx_lines = max(1, sum(len(r.text) for r in runs) // 80 + 1)
        h_mm = max(6, max_size / 2.835 * line_height_factor * approx_lines)

        if cur_y + h_mm > page_h_avail:
            page = doc.add_page()
            cur_y = margin_top

        tb = TextBox()
        tb.transform.x = margin_left
        tb.transform.y = cur_y
        tb.transform.width = text_width
        tb.transform.height = h_mm
        # Use plain text from concatenation; runs preserved for fidelity
        tb.text = "".join(r.text for r in runs)
        tb.runs = list(runs)
        # Inherit base style from largest run
        biggest = max(runs, key=lambda r: r.font_size or 0)
        tb.style.font_size = biggest.font_size or 12
        tb.style.bold = biggest.bold or False
        tb.style.italic = biggest.italic or False
        tb.style.color = biggest.color or (0, 0, 0)
        tb.style.wrap = True
        page.add_object(tb)

        cur_y += h_mm + 1.5

    doc._push_error("Imported from RTF (best-effort: paragraph-level layout, "
                    "tables/images/lists not supported).")
    return doc


# ──────────────────────────────────────────────────────────────────────────────
#  edof → RTF
# ──────────────────────────────────────────────────────────────────────────────

def _rtf_escape(s: str) -> str:
    """Escape special chars and encode non-ASCII as RTF unicode."""
    out = []
    for ch in s:
        cp = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        elif ch == "\n":
            out.append("\\par\n")
        elif ch == "\t":
            out.append("\\tab ")
        elif cp < 128:
            out.append(ch)
        else:
            # Encode as RTF unicode escape
            n = cp if cp < 32768 else cp - 65536
            out.append(f"\\u{n}?")
    return "".join(out)


def _build_color_table(doc) -> List[Tuple[int, int, int]]:
    """Walk all runs/styles and collect unique RGB colors."""
    seen = set()
    out = [(0, 0, 0)]   # color index 0 = default

    def add(c):
        if not c:
            return
        rgb = tuple(c[:3])
        if rgb in seen:
            return
        seen.add(rgb)
        out.append(rgb)

    add((0, 0, 0))
    for page in doc.pages:
        for obj in page.objects:
            if hasattr(obj, "style"):
                add(getattr(obj.style, "color", None))
            if hasattr(obj, "runs"):
                for r in (obj.runs or []):
                    add(getattr(r, "color", None))
    return out


def export_rtf(doc, path: str) -> None:
    """Write the document as an RTF file. Best-effort, paragraph-by-paragraph."""
    from edof.format.objects import TextBox

    color_table = _build_color_table(doc)
    color_idx = {c: i for i, c in enumerate(color_table)}

    def color_index_for(rgb):
        if not rgb:
            return 0
        return color_idx.get(tuple(rgb[:3]), 0)

    parts = []
    parts.append(r"{\rtf1\ansi\deff0\uc1")
    # Font table (one font, Helvetica/Arial)
    parts.append(r"{\fonttbl{\f0\fswiss\fcharset0 Arial;}}")
    # Color table
    ct = "{\\colortbl;"
    for r, g, b in color_table:
        ct += f"\\red{r}\\green{g}\\blue{b};"
    ct += "}"
    parts.append(ct)
    parts.append(r"{\*\generator edof " + "4.0.3}")
    parts.append(r"\viewkind4\uc1\pard\f0")

    first_page = True
    for page in doc.pages:
        if not first_page:
            parts.append(r"\page")
        first_page = False
        # Sort textboxes by Y, then X — flow layout
        textboxes = [o for o in page.sorted_objects() if isinstance(o, TextBox)]
        textboxes.sort(key=lambda t: (t.transform.y, t.transform.x))
        for tb in textboxes:
            # If runs present, emit each run with formatting
            runs = tb.runs
            if not runs:
                runs = [None]   # marker: use plain text + style
            for r in runs:
                if r is None:
                    s = tb.style
                    txt = tb.text
                    fmt = []
                    fmt.append(f"\\fs{int(s.font_size * 2)}")
                    fmt.append(f"\\cf{color_index_for(s.color)}")
                    if s.bold: fmt.append(r"\b")
                    if s.italic: fmt.append(r"\i")
                    if s.underline: fmt.append(r"\ul")
                    parts.append("{" + "".join(fmt) + " " + _rtf_escape(txt) + "}")
                else:
                    fmt = []
                    fs = r.font_size or tb.style.font_size or 12
                    fmt.append(f"\\fs{int(fs * 2)}")
                    fmt.append(f"\\cf{color_index_for(r.color)}")
                    if r.bold: fmt.append(r"\b")
                    if r.italic: fmt.append(r"\i")
                    if r.underline: fmt.append(r"\ul")
                    parts.append("{" + "".join(fmt) + " " + _rtf_escape(r.text) + "}")
            # End of paragraph for this textbox
            parts.append(r"\par")

    parts.append("}")

    with open(path, "wb") as f:
        f.write("\n".join(parts).encode("cp1252", errors="replace"))
