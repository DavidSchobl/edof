# edof/units.py
"""
v4.1.17: Single source of truth for all unit conversions.

EDOF uses millimetres as the canonical unit for ALL length values both
in-memory and on-disk. This module provides explicit conversions for
boundaries with other systems (typography in pt, raster output in px,
imperial in inches).

CANONICAL UNIT = MILLIMETRES (mm)
─────────────────────────────────
  • Geometry (x, y, width, height)
  • Padding, margins
  • Font size (font_size, min_font_size, max_font_size)
  • Letter spacing
  • Stroke / border widths
  • Line position offsets

Conversions live here. Anything in the codebase that does
`x * dpi / 72.0` or similar inline magic is a bug; route it through
mm_to_px / pt_to_mm.
"""
from __future__ import annotations

# Conversion constants
MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
MM_PER_PT   = MM_PER_INCH / PT_PER_INCH      # ≈ 0.3528 mm
PT_PER_MM   = PT_PER_INCH / MM_PER_INCH      # ≈ 2.8346 pt


# ── Length conversions ────────────────────────────────────────────────────────

def mm_to_pt(mm: float) -> float:
    """Millimetres to typographic points."""
    return float(mm) * PT_PER_MM


def pt_to_mm(pt: float) -> float:
    """Typographic points to millimetres."""
    return float(pt) * MM_PER_PT


def mm_to_in(mm: float) -> float:
    return float(mm) / MM_PER_INCH


def in_to_mm(inch: float) -> float:
    return float(inch) * MM_PER_INCH


def mm_to_px(mm: float, dpi: float) -> float:
    """Millimetres to pixels at the given DPI."""
    return float(mm) * float(dpi) / MM_PER_INCH


def px_to_mm(px: float, dpi: float) -> float:
    """Pixels at the given DPI back to millimetres."""
    return float(px) * MM_PER_INCH / float(dpi)


def pt_to_px(pt: float, dpi: float) -> float:
    """Typographic points to pixels at the given DPI."""
    return float(pt) * float(dpi) / PT_PER_INCH


def px_to_pt(px: float, dpi: float) -> float:
    """Pixels at the given DPI back to typographic points."""
    return float(px) * PT_PER_INCH / float(dpi)
