# edof/export/legacy_v3.py
"""
v4.0.1: Best-effort downgrade of an EDOF 4.x document to EDOF 3.x format.

Lossy conversions:
  - TextBox.runs[]      → flattened to plain text (formatting lost)
  - Table objects       → flattened to a Group of TextBoxes + line shapes
  - Shape (path)        → rasterized to a polygon shape
  - FillStyle.gradient  → replaced with average color of gradient stops
  - visible_if          → evaluated once at conversion time and baked into .visible
  - blend_mode          → reset to "normal"

The output is always a fresh Document with FORMAT_MAJOR=3 and is fully
loadable by edof 3.x. The original v4 document is not modified.
"""
from __future__ import annotations
import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edof.format.document import Document


def export_3x(doc, path: str) -> None:
    """Save a v3-compatible copy of the document to `path` (.edof file).

    The output uses only v3 features and can be opened by edof 3.x.
    """
    legacy = downgrade_to_v3(doc)
    # Force the format version in the saved file to 3.x
    from edof import version as _v
    saved_major = _v.FORMAT_MAJOR
    saved_minor = _v.FORMAT_MINOR
    saved_patch = _v.FORMAT_PATCH
    saved_str   = _v.FORMAT_VERSION_STR
    try:
        _v.FORMAT_MAJOR       = 3
        _v.FORMAT_MINOR       = 1
        _v.FORMAT_PATCH       = 0
        _v.FORMAT_VERSION_STR = "3.1.0"
        legacy.save(path)
    finally:
        _v.FORMAT_MAJOR       = saved_major
        _v.FORMAT_MINOR       = saved_minor
        _v.FORMAT_PATCH       = saved_patch
        _v.FORMAT_VERSION_STR = saved_str


def downgrade_to_v3(doc) -> "Document":
    """Return a deep-copied Document where v4-only features are flattened."""
    new_doc = copy.deepcopy(doc)
    for page in new_doc.pages:
        new_objs = []
        for obj in page.objects:
            new_objs.extend(_downgrade_object(obj, new_doc))
        page.objects = new_objs
    new_doc._error_state.append(
        "Document downgraded from v4 to v3 — Tables, rich text runs, "
        "gradients, paths, blend modes and visible_if expressions have "
        "been flattened or evaluated."
    )
    return new_doc


# ──────────────────────────────────────────────────────────────────────────────
#  Per-object downgrade
# ──────────────────────────────────────────────────────────────────────────────

def _downgrade_object(obj, doc) -> list:
    """Return a list of v3-compatible objects replacing this one."""
    from edof.format.objects import (TextBox, Table, Shape, Group,
                                       SHAPE_PATH, SHAPE_POLYGON)
    from edof.utils.safe_eval import evaluate

    # 1. Bake visible_if into .visible
    if getattr(obj, "visible_if", "") and obj.visible_if.strip():
        ctx = {n: doc.variables.get(n) for n in doc.variables.names()}
        result = evaluate(obj.visible_if, ctx)
        if result is False:
            obj.visible = False
        obj.visible_if = ""

    # 2. Reset blend_mode (v3 doesn't know about it; default value is harmless)
    if hasattr(obj, "blend_mode"):
        obj.blend_mode = "normal"

    # 3. Flatten v4-specific subtypes
    if isinstance(obj, Table):
        return _table_to_group(obj)

    if isinstance(obj, TextBox):
        if obj.runs:
            obj.text = "".join(r.text for r in obj.runs)
            obj.runs = []
        # Flatten gradient on TextBox fill
        _flatten_fill_gradient(obj.fill)
        return [obj]

    if isinstance(obj, Shape):
        # Path → polygon (sample path_data into polygon points)
        if obj.shape_type == SHAPE_PATH and obj.path_data:
            obj.points = _path_to_polygon_points(obj.path_data)
            obj.shape_type = SHAPE_POLYGON
            obj.path_data = []
        _flatten_fill_gradient(obj.fill)
        return [obj]

    if isinstance(obj, Group):
        new_children = []
        for child in obj.children:
            new_children.extend(_downgrade_object(child, doc))
        obj.children = new_children
        return [obj]

    return [obj]


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _flatten_fill_gradient(fill) -> None:
    """Replace FillStyle.gradient with the average color of its stops."""
    if not fill or not getattr(fill, "gradient", None):
        return
    g = fill.gradient
    if g.stops:
        n = len(g.stops)
        r = sum(c[1][0] for c in g.stops) // n
        gr = sum(c[1][1] for c in g.stops) // n
        b = sum(c[1][2] for c in g.stops) // n
        a = sum(c[1][3] if len(c[1]) >= 4 else 255 for c in g.stops) // n
        fill.color = (r, gr, b, a)
    else:
        fill.color = (200, 200, 200, 255)
    fill.gradient = None


def _path_to_polygon_points(path_data, samples_per_curve: int = 12) -> list:
    """Sample SVG-style path commands down to a flat polygon point list.

    Bezier curves are subdivided. Subpaths are joined; if there are multiple
    M commands the polygon will have a "stitch" line between subpaths
    (acceptable trade-off for a downgrade).
    """
    pts = []
    cur_x = cur_y = 0.0
    start_x = start_y = 0.0
    for cmd in path_data:
        if not cmd: continue
        op = cmd[0]
        if op == "M":
            cur_x, cur_y = cmd[1], cmd[2]
            start_x, start_y = cur_x, cur_y
            pts.append([cur_x, cur_y])
        elif op == "L":
            cur_x, cur_y = cmd[1], cmd[2]
            pts.append([cur_x, cur_y])
        elif op == "C":
            x1, y1, x2, y2, x, y = cmd[1:]
            for i in range(1, samples_per_curve + 1):
                t = i / samples_per_curve
                u = 1 - t
                px = (u**3 * cur_x + 3*u*u*t * x1 + 3*u*t*t * x2 + t**3 * x)
                py = (u**3 * cur_y + 3*u*u*t * y1 + 3*u*t*t * y2 + t**3 * y)
                pts.append([px, py])
            cur_x, cur_y = x, y
        elif op == "Q":
            x1, y1, x, y = cmd[1:]
            for i in range(1, samples_per_curve + 1):
                t = i / samples_per_curve
                u = 1 - t
                px = u*u*cur_x + 2*u*t*x1 + t*t*x
                py = u*u*cur_y + 2*u*t*y1 + t*t*y
                pts.append([px, py])
            cur_x, cur_y = x, y
        elif op == "Z":
            pts.append([start_x, start_y])
            cur_x, cur_y = start_x, start_y
    return pts


def _table_to_group(table) -> list:
    """Convert a Table into a Group containing one TextBox per cell + border lines."""
    from edof.format.objects import (Group, TextBox, Shape, SHAPE_RECT, SHAPE_LINE)
    from edof.format.styles  import StrokeStyle, FillStyle

    n_rows = table.num_rows; n_cols = table.num_cols
    if n_rows == 0 or n_cols == 0: return []

    t = table.transform

    # Compute column widths and row heights
    col_w = list(table.col_widths) + [0] * max(0, n_cols - len(table.col_widths))
    explicit_w = sum(w for w in col_w if w > 0)
    auto_cols = sum(1 for w in col_w if w == 0)
    auto_w = (t.width - explicit_w) / auto_cols if auto_cols > 0 else 0
    col_w_mm = [w if w > 0 else auto_w for w in col_w]

    row_h = list(table.row_heights) + [0] * max(0, n_rows - len(table.row_heights))
    explicit_h = sum(h for h in row_h if h > 0)
    auto_rows = sum(1 for h in row_h if h == 0)
    auto_h = (t.height - explicit_h) / auto_rows if auto_rows > 0 else 0
    row_h_mm = [h if h > 0 else auto_h for h in row_h]

    x_off = [0]
    for w in col_w_mm[:-1]: x_off.append(x_off[-1] + w)
    y_off = [0]
    for h in row_h_mm[:-1]: y_off.append(y_off[-1] + h)

    grp = Group()
    grp.transform = copy.deepcopy(table.transform)
    grp.transform.x = 0; grp.transform.y = 0   # children use absolute coords from page origin
    grp.transform.width = t.width; grp.transform.height = t.height
    grp.id = table.id
    grp.name = table.name or "table_group"

    children = []

    # Cell backgrounds + text
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = table.cells[ri][ci]
            cx = t.x + x_off[ci]; cy = t.y + y_off[ri]
            cw = sum(col_w_mm[ci:ci + cell.colspan])
            ch = sum(row_h_mm[ri:ri + cell.rowspan])

            # Background rect (only if visible alpha)
            if cell.bg_color and len(cell.bg_color) >= 4 and cell.bg_color[3] > 0:
                bg = Shape(shape_type=SHAPE_RECT)
                bg.transform.x = cx; bg.transform.y = cy
                bg.transform.width = cw; bg.transform.height = ch
                bg.fill = FillStyle(color=cell.bg_color)
                bg.stroke = StrokeStyle(color=(0,0,0,0), width=0)
                children.append(bg)

            # Cell text
            text = cell.text
            if cell.runs:
                text = "".join(r.text for r in cell.runs)
            if text:
                tb = TextBox(text=text)
                tb.transform.x = cx; tb.transform.y = cy
                tb.transform.width = cw; tb.transform.height = ch
                tb.style = copy.deepcopy(cell.style)
                tb.padding = cell.padding
                children.append(tb)

    # Borders as line shapes
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = table.cells[ri][ci]
            cx = t.x + x_off[ci]; cy = t.y + y_off[ri]
            cw = sum(col_w_mm[ci:ci + cell.colspan])
            ch = sum(row_h_mm[ri:ri + cell.rowspan])
            for side, x1, y1, x2, y2 in [
                (cell.border_top,    cx,      cy,      cx + cw, cy),
                (cell.border_right,  cx + cw, cy,      cx + cw, cy + ch),
                (cell.border_bottom, cx,      cy + ch, cx + cw, cy + ch),
                (cell.border_left,   cx,      cy,      cx,      cy + ch),
            ]:
                if not side.enabled: continue
                ln = Shape(shape_type=SHAPE_LINE)
                ln.points = [[x1, y1], [x2, y2]]
                ln.stroke.color = side.color
                ln.stroke.width = side.width / 25.4 * 72   # mm → pt
                children.append(ln)

    grp.children = children
    return [grp]
