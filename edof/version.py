# edof/version.py
"""Single source-of-truth for version information."""

from __future__ import annotations
__version__         = "3.0.0"
FORMAT_MAJOR        = 3
FORMAT_MINOR        = 0
FORMAT_PATCH        = 0
FORMAT_VERSION_STR  = f"{FORMAT_MAJOR}.{FORMAT_MINOR}.{FORMAT_PATCH}"

# Oldest format version this library can attempt to read
MIN_READABLE_MAJOR  = 1
# Below this we refuse entirely
HARD_MIN_MAJOR      = 1


def parse_version(s: str) -> tuple[int, int, int]:
    """Parse "X.Y.Z" → (X, Y, Z), filling missing parts with 0."""
    parts = (str(s).split(".") + ["0", "0"])[:3]
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def compatibility(file_version_str: str) -> str:
    """
    Returns one of:
      'ok'     – identical or fully compatible
      'older'  – file is older; we read it fine (possible migration)
      'newer'  – file is newer; we try, but emit a warning
      'refuse' – too old (major < HARD_MIN_MAJOR), cannot read
    """
    fmaj, fmin, fpat = parse_version(file_version_str)
    if fmaj < HARD_MIN_MAJOR:
        return "refuse"
    cur = (FORMAT_MAJOR, FORMAT_MINOR, FORMAT_PATCH)
    fil = (fmaj, fmin, fpat)
    if fil == cur:
        return "ok"
    return "older" if fil < cur else "newer"
