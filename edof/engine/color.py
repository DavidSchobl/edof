# edof/engine/color.py
"""
Colour-space helpers.
Conversion is delegated to Pillow; this module provides a clean interface
and validates the settings chosen in the document.
"""

from __future__ import annotations
from typing import Optional
from PIL import Image

# Mapping from edof CS constants → Pillow mode
PILLOW_MODE: dict[str, str] = {
    "RGB":  "RGB",
    "RGBA": "RGBA",
    "L":    "L",       # 8-bit grayscale
    "1":    "1",       # 1-bit B&W
    "CMYK": "CMYK",
}

VALID_COLOR_SPACES = set(PILLOW_MODE.keys())
VALID_BIT_DEPTHS   = {8, 16}


def validate(color_space: str, bit_depth: int) -> None:
    from edof.exceptions import EdofValidationError
    if color_space not in VALID_COLOR_SPACES:
        raise EdofValidationError(
            f"Unknown colour space {color_space!r}. "
            f"Valid: {sorted(VALID_COLOR_SPACES)}"
        )
    if bit_depth not in VALID_BIT_DEPTHS:
        raise EdofValidationError(
            f"Unsupported bit depth {bit_depth}. Valid: {VALID_BIT_DEPTHS}"
        )


def pillow_mode(color_space: str) -> str:
    return PILLOW_MODE.get(color_space, "RGB")


def convert_image(img: Image.Image,
                  color_space: str,
                  bit_depth: int = 8) -> Image.Image:
    """
    Convert a Pillow image to the target colour space and bit depth.
    Always works non-destructively (returns new image).
    """
    validate(color_space, bit_depth)
    mode = pillow_mode(color_space)

    # ── Colour-space conversion ────────────────────────────────────────────────
    if img.mode != mode:
        if mode == "1":
            # Convert to grayscale first for clean B&W threshold
            img = img.convert("L").convert("1")
        elif mode == "CMYK" and img.mode in ("RGBA", "LA"):
            img = img.convert("RGB").convert("CMYK")
        else:
            try:
                img = img.convert(mode)
            except Exception:
                img = img.convert("RGB").convert(mode)

    # ── Bit depth ─────────────────────────────────────────────────────────────
    if bit_depth == 16 and mode in ("RGB", "L", "RGBA"):
        import numpy as np
        arr = np.array(img, dtype=np.uint16) * 257   # 8-bit → 16-bit range
        # Pillow doesn't natively save 16-bit RGB; return as I;16 for TIFF
        if mode == "L":
            img = Image.fromarray(arr.astype(np.uint16), mode="I;16")
        # For RGB 16-bit export Pillow uses mode "I;16" only for grayscale;
        # callers should save as TIFF with bit_depth hint in metadata.

    return img


def background_image(width_px: int, height_px: int,
                     color_space: str,
                     background: tuple = (255, 255, 255)) -> Image.Image:
    """Create a blank canvas in the correct mode."""
    mode = pillow_mode(color_space)
    if mode == "1":
        return Image.new("1", (width_px, height_px), 1)
    if mode == "CMYK":
        return Image.new("CMYK", (width_px, height_px), (0, 0, 0, 0))
    # Clamp alpha for RGBA
    if mode == "RGBA" and len(background) == 3:
        background = (*background, 255)
    return Image.new(mode, (width_px, height_px), background[:len(background)])
