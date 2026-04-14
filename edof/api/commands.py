# edof/api/commands.py
"""
Command API – a string-based command system usable from:
  • editor undo/redo stacks
  • external scripts / automation
  • network / IPC APIs

Every command is a plain dict:
  {"cmd": "set_text", "object_id": "...", "text": "Hello"}

The CommandRegistry maps command names → handler functions.
The CommandHistory manages undo/redo.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from edof.format.document import Document

Handler = Callable[["Document", dict], Any]


# ── Registry ──────────────────────────────────────────────────────────────────

class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, Handler] = {}
        self._register_builtins()

    def register(self, name: str, handler: Handler) -> None:
        self._handlers[name] = handler

    def execute(self, doc: "Document", command: dict) -> Any:
        from edof.exceptions import EdofAPIError
        name = command.get("cmd")
        if not name:
            raise EdofAPIError("Command dict must have a 'cmd' key.")
        handler = self._handlers.get(name)
        if handler is None:
            raise EdofAPIError(f"Unknown command: {name!r}")
        return handler(doc, command)

    # ── Built-in commands ──────────────────────────────────────────────────────

    def _register_builtins(self) -> None:
        self.register("set_text",         _cmd_set_text)
        self.register("set_variable",     _cmd_set_variable)
        self.register("fill_variables",   _cmd_fill_variables)
        self.register("add_page",         _cmd_add_page)
        self.register("remove_page",      _cmd_remove_page)
        self.register("add_textbox",      _cmd_add_textbox)
        self.register("add_image",        _cmd_add_image)
        self.register("add_shape",        _cmd_add_shape)
        self.register("add_qrcode",       _cmd_add_qrcode)
        self.register("remove_object",    _cmd_remove_object)
        self.register("move_object",      _cmd_move_object)
        self.register("resize_object",    _cmd_resize_object)
        self.register("rotate_object",    _cmd_rotate_object)
        self.register("set_style",        _cmd_set_style)
        self.register("set_visibility",   _cmd_set_visibility)
        self.register("set_layer",        _cmd_set_layer)
        self.register("export_bitmap",    _cmd_export_bitmap)
        self.register("export_pdf",       _cmd_export_pdf)
        self.register("save",             _cmd_save)
        self.register("validate",         _cmd_validate)


# ── Command handlers ──────────────────────────────────────────────────────────

def _get_obj(doc: "Document", command: dict):
    from edof.exceptions import EdofAPIError
    oid = command.get("object_id")
    if not oid:
        raise EdofAPIError("'object_id' required.")
    page_idx = int(command.get("page", 0))
    page = doc.pages[page_idx]
    obj = page.get_object(oid)
    if obj is None:
        raise EdofAPIError(f"Object {oid!r} not found on page {page_idx}.")
    return obj


def _cmd_set_text(doc, cmd):
    obj = _get_obj(doc, cmd)
    from edof.format.objects import TextBox
    if not isinstance(obj, TextBox):
        from edof.exceptions import EdofAPIError
        raise EdofAPIError("Object is not a TextBox.")
    obj.text = str(cmd.get("text", ""))
    return obj.id


def _cmd_set_variable(doc, cmd):
    name  = cmd.get("name")
    value = cmd.get("value", "")
    doc.set_variable(name, value)
    return name


def _cmd_fill_variables(doc, cmd):
    mapping = cmd.get("mapping", {})
    doc.fill_variables(mapping)
    return list(mapping.keys())


def _cmd_add_page(doc, cmd):
    page = doc.add_page(
        width=cmd.get("width"), height=cmd.get("height"),
        dpi=cmd.get("dpi"), color_space=cmd.get("color_space"),
    )
    return page.id


def _cmd_remove_page(doc, cmd):
    doc.remove_page(int(cmd.get("index", 0)))


def _cmd_add_textbox(doc, cmd):
    page = doc.pages[int(cmd.get("page", 0))]
    tb = page.add_textbox(
        x=float(cmd.get("x", 0)),
        y=float(cmd.get("y", 0)),
        width=float(cmd.get("width", 80)),
        height=float(cmd.get("height", 20)),
        text=str(cmd.get("text", "")),
        unit=cmd.get("unit", "mm"),
    )
    if "variable" in cmd:
        tb.variable = cmd["variable"]
    return tb.id


def _cmd_add_image(doc, cmd):
    page = doc.pages[int(cmd.get("page", 0))]
    rid = cmd.get("resource_id") or doc.add_resource_from_file(cmd["path"])
    ib = page.add_image(resource_id=rid,
                         x=float(cmd.get("x", 0)),
                         y=float(cmd.get("y", 0)),
                         width=float(cmd.get("width", 50)),
                         height=float(cmd.get("height", 50)),
                         unit=cmd.get("unit", "mm"))
    return ib.id


def _cmd_add_shape(doc, cmd):
    page = doc.pages[int(cmd.get("page", 0))]
    sh = page.add_shape(
        shape_type=cmd.get("shape_type", "rect"),
        x=float(cmd.get("x", 0)), y=float(cmd.get("y", 0)),
        width=float(cmd.get("width", 50)), height=float(cmd.get("height", 30)),
        unit=cmd.get("unit", "mm"),
    )
    return sh.id


def _cmd_add_qrcode(doc, cmd):
    page = doc.pages[int(cmd.get("page", 0))]
    qr = page.add_qrcode(
        data=cmd.get("data", ""),
        x=float(cmd.get("x", 0)), y=float(cmd.get("y", 0)),
        size=float(cmd.get("size", 30)),
        unit=cmd.get("unit", "mm"),
        error_correction=cmd.get("error_correction", "M"),
    )
    return qr.id


def _cmd_remove_object(doc, cmd):
    page = doc.pages[int(cmd.get("page", 0))]
    return page.remove_object(cmd.get("object_id", ""))


def _cmd_move_object(doc, cmd):
    obj = _get_obj(doc, cmd)
    obj.transform.translate(
        float(cmd.get("dx", 0)),
        float(cmd.get("dy", 0)),
        cmd.get("unit", "mm"),
    )


def _cmd_resize_object(doc, cmd):
    obj = _get_obj(doc, cmd)
    if "factor" in cmd:
        obj.transform.resize_uniform(float(cmd["factor"]))
    else:
        obj.transform.resize_free(
            float(cmd.get("width",  obj.transform.width)),
            float(cmd.get("height", obj.transform.height)),
            cmd.get("unit", "mm"),
            cmd.get("anchor", "top-left"),
        )


def _cmd_rotate_object(doc, cmd):
    obj = _get_obj(doc, cmd)
    if "angle_absolute" in cmd:
        obj.transform.rotate_to(float(cmd["angle_absolute"]))
    else:
        obj.transform.rotate(float(cmd.get("angle", 0)))


def _cmd_set_style(doc, cmd):
    obj = _get_obj(doc, cmd)
    from edof.format.objects import TextBox
    if isinstance(obj, TextBox):
        for k, v in cmd.get("style", {}).items():
            if hasattr(obj.style, k):
                setattr(obj.style, k, v)


def _cmd_set_visibility(doc, cmd):
    obj = _get_obj(doc, cmd)
    obj.visible = bool(cmd.get("visible", True))


def _cmd_set_layer(doc, cmd):
    obj = _get_obj(doc, cmd)
    obj.layer = int(cmd.get("layer", 0))


def _cmd_export_bitmap(doc, cmd):
    from edof.export.bitmap import export_page_bitmap
    export_page_bitmap(
        doc,
        page_index=int(cmd.get("page", 0)),
        path=cmd["path"],
        dpi=cmd.get("dpi"),
        color_space=cmd.get("color_space"),
        format=cmd.get("format", "PNG"),
    )


def _cmd_export_pdf(doc, cmd):
    from edof.export.pdf import export_pdf
    export_pdf(doc, cmd["path"])


def _cmd_save(doc, cmd):
    doc.save(cmd["path"])


def _cmd_validate(doc, cmd):
    return doc.validate()


# ── History (undo/redo) ────────────────────────────────────────────────────────

@dataclass
class HistoryEntry:
    description: str
    snapshot:    bytes         # serialised document state


class CommandHistory:
    """
    Undo/redo stack based on document snapshots.
    Each snapshot is a full .edof file in memory (~fast for small documents).
    """

    def __init__(self, max_undo: int = 50) -> None:
        self._stack:   List[HistoryEntry] = []
        self._pointer: int                = -1
        self._max:     int                = max_undo

    def _snapshot(self, doc: "Document") -> bytes:
        from edof.format.serializer import EdofSerializer
        return EdofSerializer.to_bytes(doc)

    def _restore(self, data: bytes) -> "Document":
        from edof.format.serializer import EdofSerializer
        return EdofSerializer.from_bytes(data)

    def push(self, doc: "Document", description: str = "") -> None:
        # Drop any redo states ahead of current pointer
        self._stack = self._stack[:self._pointer + 1]
        entry = HistoryEntry(description=description,
                             snapshot=self._snapshot(doc))
        self._stack.append(entry)
        if len(self._stack) > self._max:
            self._stack.pop(0)
        self._pointer = len(self._stack) - 1

    def undo(self, doc: "Document") -> Optional["Document"]:
        if self._pointer <= 0:
            return None
        self._pointer -= 1
        return self._restore(self._stack[self._pointer].snapshot)

    def redo(self, doc: "Document") -> Optional["Document"]:
        if self._pointer >= len(self._stack) - 1:
            return None
        self._pointer += 1
        return self._restore(self._stack[self._pointer].snapshot)

    def can_undo(self) -> bool:
        return self._pointer > 0

    def can_redo(self) -> bool:
        return self._pointer < len(self._stack) - 1

    def description_undo(self) -> str:
        if self._pointer > 0:
            return self._stack[self._pointer].description
        return ""

    def description_redo(self) -> str:
        if self._pointer < len(self._stack) - 1:
            return self._stack[self._pointer + 1].description
        return ""

    def clear(self) -> None:
        self._stack.clear()
        self._pointer = -1


# ── Module-level singleton registry ───────────────────────────────────────────

registry = CommandRegistry()


def execute(doc: "Document", command: dict) -> Any:
    """Execute a command dict against a document using the global registry."""
    return registry.execute(doc, command)
