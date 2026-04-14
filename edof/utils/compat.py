# edof/utils/compat.py
"""
Backward-compatibility migration layer.

When loading older .edof files the serializer calls migrate(doc_dict, old_version)
which applies in-order transformations to bring the dict up to the current schema.
"""

from __future__ import annotations
import warnings
from typing import Callable

from edof.version import FORMAT_VERSION_STR, parse_version

# Registry: (from_major, from_minor) → migration function
_MIGRATIONS: dict[tuple[int, int], Callable[[dict], dict]] = {}


def _register(from_major: int, from_minor: int):
    """Decorator to register a migration from version (from_major, from_minor)."""
    def decorator(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        _MIGRATIONS[(from_major, from_minor)] = fn
        return fn
    return decorator


# ── Migration functions ────────────────────────────────────────────────────────
# Add a new @_register(X, Y) block for each future format version change.

@_register(1, 0)
def _migrate_1_0_to_2_0(d: dict) -> dict:
    """Example: v1.0 → v2.0 – rename 'canvas' key to 'defaults'."""
    if "canvas" in d and "defaults" not in d:
        d["defaults"] = d.pop("canvas")
    return d


@_register(2, 0)
def _migrate_2_0_to_3_0(d: dict) -> dict:
    """Example: v2.0 → v3.0 – add missing 'bit_depth' to pages."""
    for page in d.get("pages", []):
        page.setdefault("bit_depth", 8)
    # variables format changed from flat dict to {defs, values}
    if "variables" in d and isinstance(d["variables"], dict):
        if "defs" not in d["variables"]:
            flat = d["variables"]
            d["variables"] = {
                "defs": {
                    k: {"name": k, "type": "text", "default": v,
                        "description": "", "required": False, "choices": None}
                    for k, v in flat.items()
                },
                "values": dict(flat),
            }
    return d


# ── Public API ────────────────────────────────────────────────────────────────

def migrate(doc_dict: dict, file_version_str: str) -> dict:
    """
    Apply all necessary migrations to bring ``doc_dict`` from
    ``file_version_str`` up to the current format version.

    Called automatically by the serializer on load.
    """
    fmaj, fmin, _ = parse_version(file_version_str)
    cur_maj, cur_min, _ = parse_version(FORMAT_VERSION_STR)

    # Sort migrations in ascending order and apply those newer than the file version
    ordered = sorted(_MIGRATIONS.keys())
    for (mmaj, mmin) in ordered:
        if (mmaj, mmin) >= (fmaj, fmin) and (mmaj, mmin) < (cur_maj, cur_min):
            doc_dict = _MIGRATIONS[(mmaj, mmin)](doc_dict)

    return doc_dict


def needs_migration(file_version_str: str) -> bool:
    fmaj, fmin, fpat = parse_version(file_version_str)
    cur  = parse_version(FORMAT_VERSION_STR)
    return (fmaj, fmin, fpat) < cur
