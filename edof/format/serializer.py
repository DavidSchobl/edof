# edof/format/serializer.py
"""
Saves and loads .edof files.

File format: ZIP archive containing
  manifest.json     – version header, quick metadata
  document.json     – full document data (without binary blobs)
  resources/<id>    – one file per embedded resource (binary)
"""

from __future__ import annotations
import io
import json
import zipfile
from typing import TYPE_CHECKING

from edof.version    import FORMAT_VERSION_STR, compatibility
from edof.exceptions import EdofVersionError, warn_newer_version

if TYPE_CHECKING:
    from edof.format.document import Document

MANIFEST_FILE  = "manifest.json"
DOCUMENT_FILE  = "document.json"
RESOURCE_DIR   = "resources/"
MIME_EDOF      = "application/vnd.edof+zip"


class EdofSerializer:

    # ── Save ──────────────────────────────────────────────────────────────────

    @staticmethod
    def save(doc: "Document", path: str) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:

            # 1) Manifest
            manifest = {
                "mime":         MIME_EDOF,
                "edof_version": FORMAT_VERSION_STR,
                "id":           doc.id,
                "title":        doc.title,
                "pages":        len(doc.pages),
            }
            zf.writestr(MANIFEST_FILE,
                        json.dumps(manifest, ensure_ascii=False, indent=2))

            # 2) Document JSON (no binary blobs)
            zf.writestr(DOCUMENT_FILE,
                        json.dumps(doc.to_dict(), ensure_ascii=False, indent=2))

            # 3) Resource blobs
            for entry in doc.resources.all_entries():
                arc_path = RESOURCE_DIR + entry.resource_id
                zf.writestr(arc_path, entry.data)

        with open(path, "wb") as fh:
            fh.write(buf.getvalue())

    # ── Save to bytes ─────────────────────────────────────────────────────────

    @staticmethod
    def to_bytes(doc: "Document") -> bytes:
        tmp = io.BytesIO()
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest = {
                "mime":         MIME_EDOF,
                "edof_version": FORMAT_VERSION_STR,
                "id":           doc.id,
                "title":        doc.title,
                "pages":        len(doc.pages),
            }
            zf.writestr(MANIFEST_FILE,
                        json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr(DOCUMENT_FILE,
                        json.dumps(doc.to_dict(), ensure_ascii=False, indent=2))
            for entry in doc.resources.all_entries():
                zf.writestr(RESOURCE_DIR + entry.resource_id, entry.data)
        return tmp.getvalue()

    # ── Load ──────────────────────────────────────────────────────────────────

    @staticmethod
    def load(path: str) -> "Document":
        with open(path, "rb") as fh:
            data = fh.read()
        return EdofSerializer.from_bytes(data)

    @staticmethod
    def from_bytes(data: bytes) -> "Document":
        from edof.format.document import Document

        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf, "r") as zf:
            names = set(zf.namelist())

            # ── Version check ─────────────────────────────────────────────────
            if MANIFEST_FILE not in names:
                raise EdofVersionError(
                    "Not a valid .edof file (manifest.json missing)."
                )
            manifest     = json.loads(zf.read(MANIFEST_FILE))
            file_version = manifest.get("edof_version", "0.0.0")
            compat       = compatibility(file_version)

            if compat == "refuse":
                raise EdofVersionError(
                    f"Cannot read format version {file_version}. "
                    f"This library supports version {FORMAT_VERSION_STR}."
                )
            if compat == "newer":
                warn_newer_version(file_version)

            # ── Document JSON ─────────────────────────────────────────────────
            if DOCUMENT_FILE not in names:
                raise EdofVersionError(
                    "Corrupt .edof file (document.json missing)."
                )
            doc_dict = json.loads(zf.read(DOCUMENT_FILE))

            # ── Resource blobs ────────────────────────────────────────────────
            resource_data: dict[str, bytes] = {}
            for name in names:
                if name.startswith(RESOURCE_DIR) and name != RESOURCE_DIR:
                    rid = name[len(RESOURCE_DIR):]
                    resource_data[rid] = zf.read(name)

        # ── Reconstruct document ──────────────────────────────────────────────
        doc = Document.from_dict(doc_dict, resource_data)

        # If the file was older, note it (non-fatal)
        if compat == "older":
            doc._push_error(
                f"File was created with format version {file_version}; "
                f"migrated to {FORMAT_VERSION_STR}."
            )

        return doc

    # ── Introspect without full load ──────────────────────────────────────────

    @staticmethod
    def peek(path: str) -> dict:
        """Return the manifest dict without loading the full document."""
        with open(path, "rb") as fh:
            buf = io.BytesIO(fh.read())
        with zipfile.ZipFile(buf, "r") as zf:
            return json.loads(zf.read(MANIFEST_FILE))
