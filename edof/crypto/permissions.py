# edof/crypto/permissions.py
"""
v4.0.1: Permission levels for encrypted EDOF documents.

Levels (from least to most privileged):
    VIEW    — can render, print, export. Cannot modify anything.
    FILL    — VIEW + can change doc.variables values (template filling).
              Object .text, structure, layout, styles all stay frozen.
    EDIT    — FILL + can change object .text (and runs text segments).
    DESIGN  — EDIT + can change styles, layout, add/remove objects/pages.
    ADMIN   — DESIGN + can manage passwords, recovery keys, lock_level overrides.

Higher levels imply all lower levels.

Per-object overrides (object.lock_level):
    Each object can require a minimum permission for its modification.
    For example, a textbox with lock_level="design" cannot be edited even
    by someone with EDIT permission — they need DESIGN or higher.
"""
from __future__ import annotations
from enum import IntEnum


class Permission(IntEnum):
    """Ordered permission levels. Higher value = more privileges."""
    VIEW   = 0
    FILL   = 1
    EDIT   = 2
    DESIGN = 3
    ADMIN  = 4

    @classmethod
    def from_string(cls, name) -> "Permission":
        """Parse a string ('view', 'fill', etc.) or Permission to a Permission."""
        if isinstance(name, Permission):
            return name
        n = (name or "").strip().lower()
        for p in cls:
            if p.name.lower() == n:
                return p
        raise ValueError(f"Unknown permission level: {name!r}")

    def to_string(self) -> str:
        return self.name.lower()


# Convenience constants exposed at module level for users
VIEW   = Permission.VIEW
FILL   = Permission.FILL
EDIT   = Permission.EDIT
DESIGN = Permission.DESIGN
ADMIN  = Permission.ADMIN


# Slot names map 1:1 to permission levels (admin slot grants ADMIN, etc.)
SLOT_NAMES = ("fill", "edit", "design", "admin")


# Human-readable descriptions of what each permission allows / forbids
PERMISSION_DESCRIPTIONS = {
    VIEW: {
        "label":   "View only",
        "allowed": ["Open and render", "Print", "Export to PNG / PDF / SVG"],
        "denied":  ["Edit text", "Fill variables", "Move objects", "Change anything"],
    },
    FILL: {
        "label":   "Fill template",
        "allowed": ["Everything in View only", "Set variable values"],
        "denied":  ["Edit object text", "Change styles, fonts, colors",
                    "Move, resize, rotate objects", "Add or remove objects",
                    "Manage passwords"],
    },
    EDIT: {
        "label":   "Edit text",
        "allowed": ["Everything in Fill", "Change text content of objects",
                    "Change rich-text run contents"],
        "denied":  ["Change fonts, colors, sizes, alignment",
                    "Move, resize, rotate objects",
                    "Add or remove objects", "Manage passwords"],
    },
    DESIGN: {
        "label":   "Design",
        "allowed": ["Everything in Edit", "Change fonts, colors, sizes",
                    "Move, resize, rotate", "Add and remove objects",
                    "Add and remove pages"],
        "denied":  ["Manage passwords", "Change recovery key",
                    "Override per-object lock_level"],
    },
    ADMIN: {
        "label":   "Administrator",
        "allowed": ["Everything", "Set, change, remove passwords",
                    "Generate or replace recovery key",
                    "Override or remove per-object locks"],
        "denied":  [],
    },
}


def describe(level) -> dict:
    """Return a dict describing what a given permission level allows."""
    if isinstance(level, str):
        level = Permission.from_string(level)
    return PERMISSION_DESCRIPTIONS.get(level, PERMISSION_DESCRIPTIONS[VIEW])


def slot_to_permission(slot_name: str) -> Permission:
    """Map a password slot name to the permission it grants."""
    n = (slot_name or "").strip().lower()
    if n == "fill":   return FILL
    if n == "edit":   return EDIT
    if n == "design": return DESIGN
    if n == "admin":  return ADMIN
    raise ValueError(f"Unknown slot name: {slot_name!r}")


def can(current: Permission, required) -> bool:
    """Return True if `current` permission level is >= `required`."""
    if isinstance(required, str):
        required = Permission.from_string(required)
    return int(current) >= int(required)
