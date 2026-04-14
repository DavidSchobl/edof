# edof/utils/qr.py
"""
QR code utilities – generate Pillow images or PNG bytes.
Requires:  pip install edof[qr]
"""

from __future__ import annotations
import io
from typing import Optional, Tuple

Color = Tuple[int, int, int]


def generate_qr_image(
    data:             str,
    size_px:          int  = 256,
    error_correction: str  = "M",
    border:           int  = 4,
    fg:               Color = (0, 0, 0),
    bg:               Color = (255, 255, 255),
):
    """
    Generate a QR code and return a Pillow Image (RGBA).
    Raises ImportError if qrcode is not installed.
    """
    try:
        import qrcode as qrlib
    except ImportError:
        raise ImportError(
            "qrcode is required for QR generation. "
            "Install with:  pip install edof[qr]"
        )

    ec_map = {
        "L": qrlib.constants.ERROR_CORRECT_L,
        "M": qrlib.constants.ERROR_CORRECT_M,
        "Q": qrlib.constants.ERROR_CORRECT_Q,
        "H": qrlib.constants.ERROR_CORRECT_H,
    }

    qr = qrlib.QRCode(
        error_correction=ec_map.get(error_correction.upper(),
                                     qrlib.constants.ERROR_CORRECT_M),
        border=border,
        box_size=10,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fg, back_color=bg)
    from PIL import Image
    img = img.convert("RGBA").resize((size_px, size_px), Image.NEAREST)
    return img


def generate_qr_bytes(
    data:             str,
    size_px:          int  = 256,
    error_correction: str  = "M",
    border:           int  = 4,
    fg:               Color = (0, 0, 0),
    bg:               Color = (255, 255, 255),
    fmt:              str  = "PNG",
) -> bytes:
    """Return QR code as raw image bytes."""
    img = generate_qr_image(data, size_px, error_correction, border, fg, bg)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()
