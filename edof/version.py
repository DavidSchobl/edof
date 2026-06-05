# edof/version.py
"""Single source-of-truth for version information.

v4.1.17: Major format change — canonical unit switched from pt to mm
for all length values (font_size, letter_spacing, stroke widths, etc).
Bumped FORMAT_VERSION from 4.1.1 → 4.2.0 to signal this. Format version
≥ 4.2.0 stores values in mm; older files (4.0.3 — 4.1.16.x) stored
typography values in pt and are migrated on load.
"""

from __future__ import annotations
__version__ = "4.2.4"
FORMAT_MAJOR        = 4
FORMAT_MINOR        = 2
FORMAT_PATCH        = 0
FORMAT_VERSION_STR  = f"{FORMAT_MAJOR}.{FORMAT_MINOR}.{FORMAT_PATCH}"

# Oldest format version this library can read. Files with version
# below this are refused with EdofFormatError. The cutoff is 4.0.3
# because the file structure stabilised there.
MIN_READABLE_MAJOR  = 4
MIN_READABLE_MINOR  = 0
MIN_READABLE_PATCH  = 3
MIN_READABLE_STR    = f"{MIN_READABLE_MAJOR}.{MIN_READABLE_MINOR}.{MIN_READABLE_PATCH}"
# Below this we refuse entirely (legacy compatibility — kept at 1 so
# the test suite's older fixture files don't break)
HARD_MIN_MAJOR      = 1

# The version below which font_size & friends are stored in PT (legacy)
# and require migration to mm on load. ≥ this version → already mm.
METRIC_PIVOT_MAJOR  = 4
METRIC_PIVOT_MINOR  = 2
METRIC_PIVOT_PATCH  = 0


def parse_version(s: str) -> tuple[int, int, int]:
    """Parse "X.Y.Z" → (X, Y, Z), filling missing parts with 0."""
    parts = (str(s).split(".") + ["0", "0"])[:3]
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def is_legacy_pt_format(file_version_str: str) -> bool:
    """True if the file uses pt for font/typography units (pre-4.2.0)."""
    fv = parse_version(file_version_str)
    pivot = (METRIC_PIVOT_MAJOR, METRIC_PIVOT_MINOR, METRIC_PIVOT_PATCH)
    return fv < pivot


def is_too_old(file_version_str: str) -> bool:
    """True if the file is below the minimum readable version."""
    fv = parse_version(file_version_str)
    mn = (MIN_READABLE_MAJOR, MIN_READABLE_MINOR, MIN_READABLE_PATCH)
    return fv < mn


def compatibility(file_version_str: str) -> str:
    """
    Returns one of:
      'ok'     – identical or fully compatible
      'older'  – file is older; we read it fine (possible migration)
      'newer'  – file is newer; we try, but emit a warning
      'refuse' – too old, cannot read
    """
    if is_too_old(file_version_str):
        return "refuse"
    fmaj, fmin, fpat = parse_version(file_version_str)
    cur = (FORMAT_MAJOR, FORMAT_MINOR, FORMAT_PATCH)
    fil = (fmaj, fmin, fpat)
    if fil == cur:
        return "ok"
    return "older" if fil < cur else "newer"
