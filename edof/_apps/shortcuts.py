"""v4.1.23.37: user-configurable keyboard shortcuts for the text editor.

A small, dependency-light layer: a default action→combo map, JSON
persistence in the user config dir, and a helper to turn a Qt key event into
a normalized combo string ("ctrl+shift+v") so the editor can look up which
action to run. The Settings dialog (editor.py) edits this map.
"""
from __future__ import annotations
import json, os
from typing import Dict, Optional

try:
    from PyQt6.QtCore import Qt
except Exception:  # pragma: no cover
    Qt = None

# action_id → (human label, default combo)
DEFAULT_SHORTCUTS = {
    "bold":            ("Bold",                       "ctrl+b"),
    "italic":          ("Italic",                     "ctrl+i"),
    "underline":       ("Underline",                  "ctrl+u"),
    "strikethrough":   ("Strikethrough",              "ctrl+shift+s"),
    "copy":            ("Copy (with formatting)",     "ctrl+c"),
    "copy_plain":      ("Copy plain (no attributes)", "ctrl+shift+c"),
    "cut":             ("Cut",                        "ctrl+x"),
    "paste":           ("Paste (keep formatting)",    "ctrl+v"),
    "paste_spacing":   ("Paste line spacing only",    "ctrl+shift+v"),
    "paste_markdown":  ("Paste Markdown as formatted", "ctrl+alt+v"),
    "select_all":      ("Select all",                 "ctrl+a"),
    "undo":            ("Undo",                        "ctrl+z"),
    "redo":            ("Redo",                        "ctrl+shift+z"),
    "align_left":      ("Align left",                 "ctrl+l"),
    "align_center":    ("Align center",               "ctrl+e"),
    "align_right":     ("Align right",                "ctrl+r"),
    "justify":         ("Justify (spaces)",           "ctrl+j"),
    "justify_full":    ("Force justify (letter spacing)", "ctrl+shift+j"),
}


def _config_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    d = os.path.join(base, "edof")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, "shortcuts.json")


def load_shortcuts() -> Dict[str, str]:
    """Return action_id → combo, defaults overlaid with the user's overrides."""
    out = {k: v[1] for k, v in DEFAULT_SHORTCUTS.items()}
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            user = json.load(f)
        if isinstance(user, dict):
            for k, v in user.items():
                if k in out and isinstance(v, str) and v:
                    out[k] = v.lower()
    except Exception:
        pass
    return out


def save_shortcuts(mapping: Dict[str, str]) -> bool:
    try:
        clean = {k: str(v).lower() for k, v in mapping.items()
                 if k in DEFAULT_SHORTCUTS and v}
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2)
        return True
    except Exception:
        return False


_KEYNAMES = {}
def _key_name(key) -> Optional[str]:
    """Map a Qt.Key to a combo token (letters, digits, a few named keys)."""
    if Qt is None:
        return None
    # letters
    if Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value:
        return chr(key).lower()
    if Qt.Key.Key_0.value <= key <= Qt.Key.Key_9.value:
        return chr(key)
    named = {
        Qt.Key.Key_Space: "space", Qt.Key.Key_Return: "enter",
        Qt.Key.Key_Enter: "enter", Qt.Key.Key_Tab: "tab",
        Qt.Key.Key_Delete: "delete", Qt.Key.Key_Backspace: "backspace",
        Qt.Key.Key_Slash: "/", Qt.Key.Key_Backslash: "\\",
        Qt.Key.Key_Period: ".", Qt.Key.Key_Comma: ",",
        Qt.Key.Key_Minus: "-", Qt.Key.Key_Equal: "=",
        Qt.Key.Key_BracketLeft: "[", Qt.Key.Key_BracketRight: "]",
    }
    for k, name in named.items():
        if key == k.value:
            return name
    return None


def event_combo(ev) -> Optional[str]:
    """Build a normalized combo string from a QKeyEvent, e.g. 'ctrl+shift+v'.
    Returns None for bare modifier presses or unmapped keys."""
    if Qt is None:
        return None
    mods = ev.modifiers()
    name = _key_name(ev.key())
    if name is None:
        return None
    parts = []
    if mods & Qt.KeyboardModifier.ControlModifier: parts.append("ctrl")
    if mods & Qt.KeyboardModifier.AltModifier:     parts.append("alt")
    if mods & Qt.KeyboardModifier.ShiftModifier:   parts.append("shift")
    parts.append(name)
    return "+".join(parts)
