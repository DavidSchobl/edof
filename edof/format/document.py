# edof/format/document.py
"""
Document and Page – the top-level EDOF 3.0 data model.
"""

from __future__ import annotations
import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from edof.format.objects    import (EdofObject, TextBox, ImageBox,
                                     Shape, QRCode, Group, _new_id)
from edof.format.styles     import FillStyle, TextStyle, StrokeStyle
from edof.format.variables  import VariableStore
from edof.engine.transform  import Transform, to_mm

# ── Color-space / bit-depth constants ─────────────────────────────────────────

CS_RGB  = "RGB"
CS_RGBA = "RGBA"
CS_GRAY = "L"
CS_BW   = "1"
CS_CMYK = "CMYK"

BD_8  = 8
BD_16 = 16


# ── Resource store ─────────────────────────────────────────────────────────────

@dataclass
class ResourceEntry:
    resource_id: str
    filename:    str
    mime_type:   str
    data:        bytes
    metadata:    Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "resource_id": self.resource_id,
            "filename":    self.filename,
            "mime_type":   self.mime_type,
            "metadata":    self.metadata,
            # raw data is stored separately in the .edof zip archive
        }


class ResourceStore:
    """Holds all embedded resources (fonts, images, …) for a Document."""

    def __init__(self) -> None:
        self._store: Dict[str, ResourceEntry] = {}

    # ── Adding ────────────────────────────────────────────────────────────────

    def add(self, data: bytes, filename: str,
            mime_type: str = "application/octet-stream",
            metadata: Optional[Dict] = None) -> str:
        """Add raw bytes, return the new resource_id."""
        rid = _new_id()
        self._store[rid] = ResourceEntry(
            resource_id=rid, filename=filename,
            mime_type=mime_type, data=data,
            metadata=metadata or {},
        )
        return rid

    def add_from_file(self, path: str,
                      mime_type: Optional[str] = None) -> str:
        """Add a file from disk, return the new resource_id."""
        import mimetypes, os
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(path)
            mime_type = mime_type or "application/octet-stream"
        with open(path, "rb") as fh:
            data = fh.read()
        import os
        return self.add(data, os.path.basename(path), mime_type)

    # ── Access ────────────────────────────────────────────────────────────────

    def get(self, resource_id: str) -> Optional[ResourceEntry]:
        return self._store.get(resource_id)

    def remove(self, resource_id: str) -> bool:
        return bool(self._store.pop(resource_id, None))

    def all_entries(self) -> Iterator[ResourceEntry]:
        yield from self._store.values()

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, resource_id: str) -> bool:
        return resource_id in self._store

    # ── Serialization ─────────────────────────────────────────────────────────

    def index_dict(self) -> dict:
        """Serialise metadata index (not the raw bytes)."""
        return {rid: entry.to_dict() for rid, entry in self._store.items()}

    @classmethod
    def from_index(cls, index: dict,
                   data_lookup: Dict[str, bytes]) -> "ResourceStore":
        store = cls()
        for rid, meta in index.items():
            store._store[rid] = ResourceEntry(
                resource_id = rid,
                filename    = meta.get("filename", ""),
                mime_type   = meta.get("mime_type", "application/octet-stream"),
                data        = data_lookup.get(rid, b""),
                metadata    = meta.get("metadata", {}),
            )
        return store


# ── Page ──────────────────────────────────────────────────────────────────────

@dataclass
class Page:
    """A single page in an EDOF document."""

    id:          str     = field(default_factory=_new_id)
    index:       int     = 0
    width:       float   = 210.0    # mm  (A4 default)
    height:      float   = 297.0    # mm
    dpi:         int     = 300
    color_space: str     = CS_RGB
    bit_depth:   int     = BD_8
    background:  tuple   = (255, 255, 255)
    objects:     List[EdofObject] = field(default_factory=list)

    # ── Object management ─────────────────────────────────────────────────────

    def add_object(self, obj: EdofObject) -> EdofObject:
        obj.layer = len(self.objects)
        self.objects.append(obj)
        return obj

    def add_textbox(
        self,
        x: float = 0, y: float = 0,
        width: float = 80, height: float = 20,
        text: str = "",
        unit: str = "mm",
        **style_kwargs,
    ) -> TextBox:
        tb = TextBox(text=text)
        tb.transform = Transform(
            x=to_mm(x, unit), y=to_mm(y, unit),
            width=to_mm(width, unit), height=to_mm(height, unit),
        )
        for k, v in style_kwargs.items():
            if hasattr(tb.style, k):
                setattr(tb.style, k, v)
        return self.add_object(tb)  # type: ignore[return-value]

    def add_image(
        self,
        resource_id: str,
        x: float = 0, y: float = 0,
        width: float = 50, height: float = 50,
        unit: str = "mm",
        fit_mode: str = "contain",
    ) -> ImageBox:
        ib = ImageBox(resource_id=resource_id, fit_mode=fit_mode)
        ib.transform = Transform(
            x=to_mm(x, unit), y=to_mm(y, unit),
            width=to_mm(width, unit), height=to_mm(height, unit),
        )
        return self.add_object(ib)  # type: ignore[return-value]

    def add_shape(
        self,
        shape_type: str = "rect",
        x: float = 0, y: float = 0,
        width: float = 50, height: float = 30,
        unit: str = "mm",
    ) -> Shape:
        sh = Shape(shape_type=shape_type)
        sh.transform = Transform(
            x=to_mm(x, unit), y=to_mm(y, unit),
            width=to_mm(width, unit), height=to_mm(height, unit),
        )
        return self.add_object(sh)  # type: ignore[return-value]

    def add_qrcode(
        self,
        data: str,
        x: float = 0, y: float = 0,
        size: float = 30,
        unit: str = "mm",
        error_correction: str = "M",
    ) -> QRCode:
        qr = QRCode(data=data, error_correction=error_correction)
        s  = to_mm(size, unit)
        qr.transform = Transform(
            x=to_mm(x, unit), y=to_mm(y, unit),
            width=s, height=s,
        )
        return self.add_object(qr)  # type: ignore[return-value]

    def add_group(self) -> Group:
        g = Group()
        return self.add_object(g)  # type: ignore[return-value]

    def remove_object(self, obj_id: str) -> bool:
        before = len(self.objects)
        self.objects = [o for o in self.objects if o.id != obj_id]
        return len(self.objects) < before

    def get_object(self, obj_id: str) -> Optional[EdofObject]:
        return next((o for o in self.objects if o.id == obj_id), None)

    def get_by_name(self, name: str) -> List[EdofObject]:
        return [o for o in self.objects if o.name == name]

    def get_by_tag(self, tag: str) -> List[EdofObject]:
        return [o for o in self.objects if tag in o.tags]

    def sorted_objects(self) -> List[EdofObject]:
        """Return objects sorted by layer (ascending = bottom to top)."""
        return sorted(self.objects, key=lambda o: o.layer)

    def duplicate(self) -> "Page":
        p       = copy.deepcopy(self)
        p.id    = _new_id()
        p.index = self.index + 1
        # Give each object a fresh id
        for obj in p.objects:
            obj.id = _new_id()
        return p

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        from edof.format.styles import _rgba_to_hex
        return {
            "id":          self.id,
            "index":       self.index,
            "width":       self.width,
            "height":      self.height,
            "dpi":         self.dpi,
            "color_space": self.color_space,
            "bit_depth":   self.bit_depth,
            "background":  _rgba_to_hex(self.background),
            "objects":     [o.to_dict() for o in self.objects],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Page":
        from edof.format.styles import _hex_to_rgba
        bg_raw = d.get("background", "#ffffff")
        bg     = _hex_to_rgba(bg_raw) if isinstance(bg_raw, str) else tuple(bg_raw)
        p = cls(
            id          = d.get("id",          _new_id()),
            index       = int(d.get("index",       0)),
            width       = float(d.get("width",   210.0)),
            height      = float(d.get("height",  297.0)),
            dpi         = int(d.get("dpi",         300)),
            color_space = d.get("color_space",  CS_RGB),
            bit_depth   = int(d.get("bit_depth",     8)),
            background  = bg,
        )
        p.objects = [EdofObject.from_dict(o) for o in d.get("objects", [])]
        return p


# ── Document ──────────────────────────────────────────────────────────────────

class Document:
    """
    Root object for an EDOF document.

    Usage::

        doc = edof.Document(width=210, height=297)
        page = doc.add_page()
        tb = page.add_textbox(10, 10, 100, 20, "Hello!")
        doc.save("hello.edof")
    """

    def __init__(
        self,
        width:        float = 210.0,   # mm
        height:       float = 297.0,   # mm
        dpi:          int   = 300,
        color_space:  str   = CS_RGB,
        bit_depth:    int   = BD_8,
        title:        str   = "",
        author:       str   = "",
        description:  str   = "",
    ) -> None:
        self.id           = _new_id()
        self.title        = title
        self.author       = author
        self.description  = description
        self.created      = datetime.now(timezone.utc).isoformat()
        self.modified     = self.created
        self.default_width       = width
        self.default_height      = height
        self.default_dpi         = dpi
        self.default_color_space = color_space
        self.default_bit_depth   = bit_depth
        self.pages:     List[Page]     = []
        self.variables: VariableStore  = VariableStore()
        self.resources: ResourceStore  = ResourceStore()
        self._error_state: List[str]   = []   # non-fatal warnings / errors

    # ── Error state ───────────────────────────────────────────────────────────

    def _push_error(self, msg: str) -> None:
        self._error_state.append(msg)

    @property
    def errors(self) -> List[str]:
        return list(self._error_state)

    def clear_errors(self) -> None:
        self._error_state.clear()

    # ── Pages ─────────────────────────────────────────────────────────────────

    def add_page(
        self,
        width:        Optional[float] = None,
        height:       Optional[float] = None,
        dpi:          Optional[int]   = None,
        color_space:  Optional[str]   = None,
        bit_depth:    Optional[int]   = None,
        background:   tuple           = (255, 255, 255),
    ) -> Page:
        page = Page(
            index       = len(self.pages),
            width       = width       or self.default_width,
            height      = height      or self.default_height,
            dpi         = dpi         or self.default_dpi,
            color_space = color_space or self.default_color_space,
            bit_depth   = bit_depth   or self.default_bit_depth,
            background  = background,
        )
        self.pages.append(page)
        return page

    def get_page(self, index: int) -> Page:
        return self.pages[index]

    def remove_page(self, index: int) -> None:
        self.pages.pop(index)
        for i, p in enumerate(self.pages):
            p.index = i

    def move_page(self, from_index: int, to_index: int) -> None:
        page = self.pages.pop(from_index)
        self.pages.insert(to_index, page)
        for i, p in enumerate(self.pages):
            p.index = i

    def duplicate_page(self, index: int) -> Page:
        new_page = self.pages[index].duplicate()
        self.pages.insert(index + 1, new_page)
        for i, p in enumerate(self.pages):
            p.index = i
        return new_page

    # ── Variables ─────────────────────────────────────────────────────────────

    def define_variable(self, name: str, **kwargs) -> None:
        self.variables.define(name, **kwargs)

    def set_variable(self, name: str, value: Any) -> None:
        self.variables.set(name, value)

    def fill_variables(self, mapping: Dict[str, Any]) -> None:
        """Batch fill – ``doc.fill_variables({"name": "Jan", "date": "2025"})``"""
        self.variables.fill(mapping)

    # ── Resources ─────────────────────────────────────────────────────────────

    def add_resource(self, data: bytes, filename: str,
                     mime_type: str = "application/octet-stream") -> str:
        return self.resources.add(data, filename, mime_type)

    def add_resource_from_file(self, path: str) -> str:
        return self.resources.add_from_file(path)

    # ── Save / Load ───────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        from edof.format.serializer import EdofSerializer
        EdofSerializer.save(self, path)
        self.modified = datetime.now(timezone.utc).isoformat()

    @classmethod
    def load(cls, path: str) -> "Document":
        from edof.format.serializer import EdofSerializer
        return EdofSerializer.load(path)

    # ── Export helpers ─────────────────────────────────────────────────────────

    def export_bitmap(
        self,
        path:         str,
        page:         int  = 0,
        dpi:          Optional[int] = None,
        color_space:  Optional[str] = None,
        bit_depth:    Optional[int] = None,
        format:       str  = "PNG",
    ) -> None:
        from edof.export.bitmap import export_page_bitmap
        export_page_bitmap(
            self, page_index=page, path=path,
            dpi=dpi, color_space=color_space,
            bit_depth=bit_depth, format=format,
        )

    def export_pdf(self, path: str) -> None:
        from edof.export.pdf import export_pdf
        export_pdf(self, path)

    def print_document(self, printer: Optional[str] = None,
                       pages: Optional[List[int]] = None) -> None:
        from edof.export.printer import print_document
        print_document(self, printer=printer, pages=pages)

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> List[str]:
        """Return list of validation issues (empty = valid)."""
        issues: List[str] = []
        if not self.pages:
            issues.append("Document has no pages.")
        for i, page in enumerate(self.pages):
            for obj in page.objects:
                if obj.variable and obj.variable not in self.variables.names():
                    issues.append(
                        f"Page {i}: object '{obj.id}' references "
                        f"undefined variable '{obj.variable}'."
                    )
                if hasattr(obj, "resource_id") and obj.resource_id:
                    if obj.resource_id not in self.resources:
                        issues.append(
                            f"Page {i}: object '{obj.id}' references "
                            f"missing resource '{obj.resource_id}'."
                        )
        missing = self.variables.missing_required()
        if missing:
            issues.append(f"Required variables not set: {missing}")
        return issues

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        from edof.version import FORMAT_VERSION_STR
        return {
            "edof_version":   FORMAT_VERSION_STR,
            "id":             self.id,
            "title":          self.title,
            "author":         self.author,
            "description":    self.description,
            "created":        self.created,
            "modified":       self.modified,
            "defaults": {
                "width":       self.default_width,
                "height":      self.default_height,
                "dpi":         self.default_dpi,
                "color_space": self.default_color_space,
                "bit_depth":   self.default_bit_depth,
            },
            "pages":     [p.to_dict() for p in self.pages],
            "variables": self.variables.to_dict(),
            "resources": self.resources.index_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict,
                  resource_data: Dict[str, bytes] = None) -> "Document":
        defs = d.get("defaults", {})
        doc  = cls(
            width       = float(defs.get("width",        210.0)),
            height      = float(defs.get("height",       297.0)),
            dpi         = int(  defs.get("dpi",            300)),
            color_space =       defs.get("color_space",  CS_RGB),
            bit_depth   = int(  defs.get("bit_depth",        8)),
            title       =       d.get("title",              ""),
            author      =       d.get("author",             ""),
            description =       d.get("description",        ""),
        )
        doc.id       = d.get("id",       _new_id())
        doc.created  = d.get("created",  doc.created)
        doc.modified = d.get("modified", doc.modified)
        doc.pages    = [Page.from_dict(pd) for pd in d.get("pages", [])]
        doc.variables = VariableStore.from_dict(d.get("variables", {}))
        doc.resources = ResourceStore.from_index(
            d.get("resources", {}),
            resource_data or {},
        )
        return doc

    def __repr__(self) -> str:
        return (
            f"<Document title={self.title!r} pages={len(self.pages)} "
            f"vars={len(self.variables.names())} "
            f"resources={len(self.resources)}>"
        )
