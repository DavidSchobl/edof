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
    page = doc.pages[page_index]
    img  = render_page(page, doc.resources, doc.variables,
                       dpi, color_space, bit_depth)
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
    paths = []
    for i, page in enumerate(doc.pages):
        path = path_pattern.format(n=i, page=i + 1)
        img  = render_page(page, doc.resources, doc.variables,
                           dpi, color_space, bit_depth)
        _save_image(img, path, format, dpi or page.dpi, jpeg_quality)
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
    page = doc.pages[page_index]
    img  = render_page(page, doc.resources, doc.variables,
                       dpi, color_space, bit_depth)
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
        save_kwargs["optimize"] = True

    img.save(dest, format=fmt, **save_kwargs)
