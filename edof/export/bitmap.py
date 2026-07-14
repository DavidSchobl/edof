# edof/export/bitmap.py
"""Export document pages to raster image files."""

from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from edof.format.document import Document


def export_page_bitmap(
    doc:          "Document",
    page_index:   int  = 0,
    path:         str  = "output.png",
    dpi:          Optional[int] = None,
    color_space:  Optional[str] = None,
    bit_depth:    Optional[int] = None,
    format:       str  = "PNG",
    jpeg_quality: int  = 95,
) -> None:
    """Render one page and save it to a file."""
    from edof.engine.renderer import render_page
    from edof.engine.text_engine import suppress_view_marks
    page = doc.pages[page_index]
    # v4.1.8: export with real transparency (no editor checker pattern)
    # v4.4.0: view-only marks (variable rainbow, focus) never export
    with suppress_view_marks():
        img = render_page(page, doc.resources, doc.variables,
                          dpi, color_space, bit_depth,
                          show_transparency_checker=False)
    _save_image(img, path, format, dpi or page.dpi, jpeg_quality)


def export_all_pages(
    doc:          "Document",
    path_pattern: str  = "page_{n}.png",
    dpi:          Optional[int] = None,
    color_space:  Optional[str] = None,
    bit_depth:    Optional[int] = None,
    format:       str  = "PNG",
    jpeg_quality: int  = 95,
) -> List[str]:
    """
    Render every page.
    ``path_pattern`` may contain ``{n}`` (0-based index) and ``{page}`` (1-based).
    Returns list of written paths.
    """
    from edof.engine.renderer import render_page
    from edof.engine.text_engine import suppress_view_marks
    paths = []
    for i, page in enumerate(doc.pages):
        path = path_pattern.format(n=i, page=i + 1)
        with suppress_view_marks():
            img = render_page(page, doc.resources, doc.variables,
                              dpi, color_space, bit_depth,
                              show_transparency_checker=False)
        try:
            _save_image(img, path, format, dpi or page.dpi, jpeg_quality)
        finally:
            # v4.4.0: release the decoded RGBA buffer NOW; a multi-page batch
            # export used to keep every page's buffer alive until GC.
            try: img.close()
            except Exception: pass
        paths.append(path)
    return paths


def export_to_bytes(
    doc:          "Document",
    page_index:   int  = 0,
    format:       str  = "PNG",
    dpi:          Optional[int] = None,
    color_space:  Optional[str] = None,
    bit_depth:    Optional[int] = None,
    jpeg_quality: int  = 95,
) -> bytes:
    """Render one page and return raw image bytes."""
    import io
    from edof.engine.renderer import render_page
    from edof.engine.text_engine import suppress_view_marks
    page = doc.pages[page_index]
    with suppress_view_marks():
        img = render_page(page, doc.resources, doc.variables,
                          dpi, color_space, bit_depth,
                          show_transparency_checker=False)
    buf  = io.BytesIO()
    _save_image(img, buf, format, dpi or page.dpi, jpeg_quality)
    return buf.getvalue()


def _save_image(img, dest, format: str, dpi: int, jpeg_quality: int) -> None:
    import io
    fmt = format.upper()
    save_kwargs: dict = {"dpi": (dpi, dpi)}

    if fmt in ("JPG", "JPEG"):
        fmt = "JPEG"
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        save_kwargs["quality"] = jpeg_quality
        save_kwargs["subsampling"] = 0

    elif fmt == "TIFF":
        save_kwargs["compression"] = "tiff_lzw"

    elif fmt == "PNG":
        # v4.3.6.25: optimize=True runs PIL's exhaustive filter search, which on
        # a many-colour image (a gradient page) took ~1s per page for a marginal
        # size win (155 vs 265 KB). compress_level=6 (zlib default) is ~6x faster
        # and is the right trade-off for batch rendering. Callers who want the
        # smallest file can re-compress the PNG afterwards.
        save_kwargs["compress_level"] = 6

    img.save(dest, format=fmt, **save_kwargs)
