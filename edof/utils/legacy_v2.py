# edof/utils/legacy_v2.py
"""
v4.0.1: One-way import of legacy EDOF 2 archives.

EDOF 2 was an internal pre-release format (max version 2.2 in the wild).
It had several architectural issues that motivated the v3 redesign:

  - Single `data.json` at archive root (no separate manifest)
  - Float version field (`2.2` instead of semver)
  - Color stored as ARGB hex (`"#AARRGGBB"`) — alpha first
  - Only two object types: text and image
  - No variables, no QR codes, no shapes, no groups, no styles
  - XOR-obfuscated password for "edit lock" (security theatre)
  - z_value field stored on items, sorted at load time
  - Edit modes (none/text_only/text_font/all) baked into the document

Schema (data.json):
    {
      "version": 2.2,
      "metadata": {...},
      "pages": [{
        "page_id": "abc12345",
        "page_width_mm": 210.0,
        "page_height_mm": 297.0,
        "page_dpi": 300,
        "items": [...],
        "max_z_value": 3
      }],
      "last_viewed_page": 0,
      "edit_mode": "all" | "text_only" | "text_font" | "none",
      "edit_password_xor": ""
    }

Item common fields:
    type ("text" | "image" | "base")
    id, x, y, width, height, rotation, z_value, locked

EdofTextItem:
    text, font_family, font_point_size, font_weight (400=normal, 700=bold),
    font_italic, font_underline, font_strikeout, max_font_size_pt,
    text_color_hex (ARGB!), h_align, v_align

EdofImageItem:
    original_path, internal_zip_path (e.g. "images/img_abc.png"),
    allow_non_uniform_scale

The conversion is one-way; the resulting v4 document cannot be saved back
to v2. All migration warnings are appended to doc.errors.
"""
from __future__ import annotations
import json
import zipfile
from typing import TYPE_CHECKING, Optional, Dict, Any

if TYPE_CHECKING:
    from edof.format.document import Document


# ──────────────────────────────────────────────────────────────────────────────
#  Detection
# ──────────────────────────────────────────────────────────────────────────────

def is_v2_archive(path: str) -> bool:
    """Return True if the .edof file at `path` looks like EDOF 2."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            # EDOF 2 has a single data.json at root; v3+ has manifest.json + document.json
            if "data.json" not in names:
                return False
            if "manifest.json" in names:
                return False
            try:
                data = json.loads(zf.read("data.json"))
            except Exception:
                return False
            if not isinstance(data, dict):
                return False
            v = data.get("version")
            if isinstance(v, (int, float)) and v < 3.0:
                return True
            pages = data.get("pages", [])
            if pages and isinstance(pages, list):
                first = pages[0]
                if isinstance(first, dict) and "page_width_mm" in first:
                    return True
                items = first.get("items", []) if isinstance(first, dict) else []
                if items and isinstance(items[0], dict):
                    if items[0].get("type") in ("text", "image"):
                        return True
    except (zipfile.BadZipFile, KeyError, OSError):
        return False
    return False


# ──────────────────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────────────────

def load_v2(path: str) -> "Document":
    """Load a legacy EDOF 2 archive and return a fresh EDOF 4 Document."""
    if not is_v2_archive(path):
        from edof.exceptions import EdofError
        raise EdofError(f"File {path!r} does not look like a legacy EDOF 2 archive")

    import edof
    doc = edof.new()
    doc.pages.clear()    # drop default initial page

    with zipfile.ZipFile(path, "r") as zf:
        try:
            data = json.loads(zf.read("data.json"))
        except Exception as e:
            from edof.exceptions import EdofError
            raise EdofError(f"Could not parse v2 data.json: {e}")

        # Cache embedded image bytes for later use
        image_blobs: Dict[str, bytes] = {}
        for n in zf.namelist():
            if n.startswith("images/") and not n.endswith("/"):
                try:
                    image_blobs[n] = zf.read(n)
                except KeyError:
                    pass

    # ── Document-level metadata ───────────────────────────────────────────────
    version_str = str(data.get("version", "2.0"))
    doc._error_state.append(
        f"Loaded legacy EDOF {version_str} archive — best-effort migration "
        f"to v4. This is a one-way conversion; the result cannot be saved "
        f"back to v2."
    )

    meta = data.get("metadata") or {}
    if isinstance(meta, dict):
        doc.title       = str(meta.get("title")       or meta.get("name") or doc.title or "")
        doc.author      = str(meta.get("author")      or "")
        doc.description = str(meta.get("description") or meta.get("subject") or "")
        for k, v in meta.items():
            if k not in ("title", "name", "author", "description", "subject"):
                doc._error_state.append(
                    f"v2 metadata key {k!r}={v!r} dropped (no v4 equivalent)")

    edit_mode = data.get("edit_mode")
    if edit_mode and edit_mode != "all":
        doc._error_state.append(
            f"v2 edit_mode={edit_mode!r} is informational only in v4. "
            f"Use object.locked or document-level access control instead.")

    if data.get("edit_password_xor"):
        doc._error_state.append(
            "v2 XOR password ignored. (XOR obfuscation provided no real "
            "security; v4 does not include a built-in password mechanism.)")

    # ── Pages ─────────────────────────────────────────────────────────────────
    pages_data = data.get("pages") or []
    if not pages_data:
        doc.add_page()
        return doc

    for page_data in pages_data:
        if not isinstance(page_data, dict):
            doc._error_state.append(
                f"Skipped non-dict page entry: {type(page_data).__name__}")
            continue

        w   = float(page_data.get("page_width_mm",  210.0))
        h   = float(page_data.get("page_height_mm", 297.0))
        dpi = int(page_data.get("page_dpi", 150))

        page = doc.add_page(dpi=dpi)
        page.width  = w
        page.height = h

        items = page_data.get("items") or []
        items_sorted = sorted(
            (it for it in items if isinstance(it, dict)),
            key=lambda it: int(it.get("z_value", 0))
        )

        for layer_idx, item_data in enumerate(items_sorted):
            obj = _migrate_v2_item(item_data, doc, image_blobs)
            if obj is None: continue
            obj.layer = layer_idx
            page.add_object(obj)

    return doc


# ──────────────────────────────────────────────────────────────────────────────
#  Per-item migration
# ──────────────────────────────────────────────────────────────────────────────

def _migrate_v2_item(item_data: dict, doc, image_blobs: Dict[str, bytes]):
    """Translate one EDOF 2 item dict into a v4 EdofObject."""
    item_type = item_data.get("type")
    if item_type == "text":
        return _migrate_text_item(item_data, doc)
    if item_type == "image":
        return _migrate_image_item(item_data, doc, image_blobs)
    if item_type == "base":
        doc._error_state.append(
            f"Skipped legacy 'base' item (id={item_data.get('id','?')!r}); "
            f"no v4 equivalent.")
        return None
    doc._error_state.append(
        f"Unknown v2 item type {item_type!r} "
        f"(id={item_data.get('id','?')!r}) skipped.")
    return None


def _migrate_text_item(item_data: dict, doc):
    """EdofTextItem → TextBox."""
    from edof.format.objects import TextBox

    tb = TextBox(text=str(item_data.get("text", "")))
    _apply_common_transform(tb, item_data)
    if item_data.get("locked"): tb.locked = True

    fp = float(item_data.get("font_point_size",
               item_data.get("max_font_size", 10.0)))            # legacy key
    max_fp = float(item_data.get("max_font_size_pt",
                   item_data.get("max_font_size", fp)))
    weight = int(item_data.get("font_weight", 400))

    tb.style.font_family   = str(item_data.get("font_family", "Arial"))
    tb.style.font_size     = fp
    tb.style.bold          = (weight >= 600)
    tb.style.italic        = bool(item_data.get("font_italic", False))
    tb.style.underline     = bool(item_data.get("font_underline", False))
    tb.style.strikethrough = bool(item_data.get("font_strikeout", False))

    # v2 always shrinks to fit if max_font_size_pt > font_point_size.
    # In v4 we set the reference size to the maximum and enable auto_shrink.
    if max_fp > fp + 0.01:
        tb.style.auto_shrink = True
        tb.style.font_size   = max_fp

    tb.style.color = _argb_to_rgb(
        item_data.get("text_color_hex",
                      item_data.get("text_color", "#FF000000"))   # legacy key
    )

    h = str(item_data.get("h_align", item_data.get("text_align", "center")))
    v = str(item_data.get("v_align", "center"))
    tb.style.alignment      = _v2_h_align_to_v4(h)
    tb.style.vertical_align = _v2_v_align_to_v4(v)
    tb.style.wrap = True
    return tb


def _migrate_image_item(item_data: dict, doc, image_blobs: Dict[str, bytes]):
    """EdofImageItem → ImageBox with embedded resource."""
    from edof.format.objects import ImageBox

    ib = ImageBox()
    _apply_common_transform(ib, item_data)
    if item_data.get("locked"): ib.locked = True

    if item_data.get("allow_non_uniform_scale"):
        ib.fit_mode = "stretch"
    else:
        ib.fit_mode = "contain"

    img_bytes: Optional[bytes] = None
    arc_path = item_data.get("internal_zip_path")
    if arc_path and arc_path in image_blobs:
        img_bytes = image_blobs[arc_path]
    elif arc_path:
        normalized = arc_path.replace("\\", "/").lstrip("/")
        for k, v in image_blobs.items():
            if k == normalized or k.endswith("/" + normalized.split("/")[-1]):
                img_bytes = v; break

    if img_bytes:
        mime = "image/png"
        if   img_bytes[:3] == b"\xff\xd8\xff":              mime = "image/jpeg"
        elif img_bytes[:6] in (b"GIF87a", b"GIF89a"):       mime = "image/gif"
        elif img_bytes[:4] == b"RIFF" and b"WEBP" in img_bytes[:16]: mime = "image/webp"
        elif img_bytes[:8] == b"\x89PNG\r\n\x1a\n":         mime = "image/png"

        filename = (arc_path or "image.png").rsplit("/", 1)[-1]
        rid = doc.resources.add(img_bytes, filename, mime)
        ib.resource_id = rid
    else:
        if arc_path:
            doc._error_state.append(
                f"Image item id={item_data.get('id','?')!r}: archive path "
                f"{arc_path!r} not found; image is missing.")
        elif item_data.get("original_path"):
            doc._error_state.append(
                f"Image item id={item_data.get('id','?')!r}: only "
                f"original_path={item_data['original_path']!r} known. The image "
                f"file was not embedded; you'll need to re-add it manually.")
        else:
            doc._error_state.append(
                f"Image item id={item_data.get('id','?')!r}: no image data "
                f"available (neither embedded nor on disk).")

    return ib


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _apply_common_transform(obj, item_data: dict) -> None:
    obj.transform.x        = float(item_data.get("x", 0.0))
    obj.transform.y        = float(item_data.get("y", 0.0))
    obj.transform.width    = float(item_data.get("width",  50.0))
    obj.transform.height   = float(item_data.get("height", 30.0))
    obj.transform.rotation = float(item_data.get("rotation", 0.0))


def _argb_to_rgb(value) -> tuple:
    """Convert v2's ARGB hex string '#AARRGGBB' to v4's RGB tuple.

    v2 stored alpha-first; v4 uses RGB tuples for TextStyle.color (alpha is
    implicit at 255 via the .opacity field on the object). Falls back to
    black if the input is malformed.
    """
    if not value: return (0, 0, 0)
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return tuple(int(v) for v in value[:3])
    s = str(value).strip().lstrip("#")
    try:
        if len(s) == 8:
            return (int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        if len(s) == 3:
            return (int(s[0]*2, 16), int(s[1]*2, 16), int(s[2]*2, 16))
    except ValueError:
        pass
    return (0, 0, 0)


def _v2_h_align_to_v4(h: str) -> str:
    h = (h or "").strip().lower()
    if h in ("left", "right", "center", "justify"): return h
    if h == "centre": return "center"
    return "center"


def _v2_v_align_to_v4(v: str) -> str:
    v = (v or "").strip().lower()
    if v == "top":    return "top"
    if v == "bottom": return "bottom"
    if v in ("center", "centre", "middle"): return "middle"
    return "middle"
