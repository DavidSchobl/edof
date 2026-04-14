# edof/format/variables.py
"""
Variable system – named placeholders for batch fill and template rendering.
Objects reference a variable by name; at render-time the store provides values.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

VAR_TEXT   = "text"
VAR_IMAGE  = "image"   # resource_id or file path
VAR_NUMBER = "number"
VAR_DATE   = "date"
VAR_BOOL   = "bool"
VAR_QR     = "qr"      # data string for a QR code object
VAR_URL    = "url"
ALL_TYPES  = {VAR_TEXT, VAR_IMAGE, VAR_NUMBER, VAR_DATE, VAR_BOOL, VAR_QR, VAR_URL}


@dataclass
class VariableDef:
    name:        str
    type:        str            = VAR_TEXT
    default:     Any            = ""
    description: str            = ""
    required:    bool           = False
    choices:     Optional[List] = None   # allowed values; None = any

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self, value: Any) -> bool:
        if self.choices and value not in self.choices:
            return False
        if self.type == VAR_NUMBER:
            try:
                float(value)
            except (TypeError, ValueError):
                return False
        return True

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "type":        self.type,
            "default":     self.default,
            "description": self.description,
            "required":    self.required,
            "choices":     self.choices,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VariableDef":
        return cls(
            name        = d["name"],
            type        = d.get("type",        VAR_TEXT),
            default     = d.get("default",     ""),
            description = d.get("description", ""),
            required    = d.get("required",    False),
            choices     = d.get("choices"),
        )


class VariableStore:
    """Holds all VariableDefs and their current values for one Document."""

    def __init__(self) -> None:
        self._defs:   Dict[str, VariableDef] = {}
        self._values: Dict[str, Any]         = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def define(
        self,
        name:        str,
        type:        str  = VAR_TEXT,
        default:     Any  = "",
        description: str  = "",
        required:    bool = False,
        choices           = None,
    ) -> VariableDef:
        vdef = VariableDef(
            name=name, type=type, default=default,
            description=description, required=required, choices=choices,
        )
        self._defs[name]   = vdef
        self._values[name] = default
        return vdef

    def undefine(self, name: str) -> None:
        self._defs.pop(name, None)
        self._values.pop(name, None)

    def names(self) -> List[str]:
        return list(self._defs.keys())

    def get_def(self, name: str) -> Optional[VariableDef]:
        return self._defs.get(name)

    # ── Values ────────────────────────────────────────────────────────────────

    def set(self, name: str, value: Any) -> None:
        from edof.exceptions import EdofVariableError
        if name not in self._defs:
            self.define(name)                       # auto-define as text
        vdef = self._defs[name]
        if not vdef.validate(value):
            raise EdofVariableError(
                f"Value {value!r} invalid for variable {name!r} "
                f"(type={vdef.type}, choices={vdef.choices})"
            )
        self._values[name] = value

    def get(self, name: str, fallback: Any = None) -> Any:
        if name in self._values:
            return self._values[name]
        if name in self._defs:
            return self._defs[name].default
        return fallback

    def fill(self, mapping: Dict[str, Any]) -> None:
        """Batch fill – set multiple variables at once."""
        for k, v in mapping.items():
            self.set(k, v)

    def reset_all(self) -> None:
        for name, vdef in self._defs.items():
            self._values[name] = vdef.default

    def all_values(self) -> Dict[str, Any]:
        return dict(self._values)

    def missing_required(self) -> List[str]:
        return [
            name for name, vdef in self._defs.items()
            if vdef.required and not self._values.get(name)
        ]

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "defs":   {n: d.to_dict() for n, d in self._defs.items()},
            "values": dict(self._values),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VariableStore":
        store = cls()
        for name, dd in d.get("defs", {}).items():
            store._defs[name] = VariableDef.from_dict(dd)
        store._values = dict(d.get("values", {}))
        return store
