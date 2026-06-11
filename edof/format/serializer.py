# edof/format/serializer.py
"""
Saves and loads .edof files. v4.0.1 adds encrypted save/load.

File formats:

  Plain (encryption_mode='none'):
    manifest.json     – version header, quick metadata
    document.json     – full document data
    resources/<id>    – one file per embedded resource

  Partial (encryption_mode='partial'):
    manifest.json     – version header + protection block (slots, mode='partial')
    document.json     – structural data only; sensitive fields are placeholders
    resources/<id>    – non-sensitive resources (fonts)
    encrypted_payload.bin   – AES-GCM blob containing the sensitive fields
                              JSON: {"texts": {...}, "image_data": {...}, ...}

  Full (encryption_mode='full'):
    manifest.json     – version header + protection block (slots, mode='full')
    encrypted_payload.bin   – AES-GCM blob containing a ZIP with everything else
"""
from __future__ import annotations
import io
import json
import zipfile
from typing import TYPE_CHECKING, Optional, Dict, Any

from edof.version    import compatibility
from edof import version as _version_mod
from edof.exceptions import EdofVersionError, warn_newer_version

if TYPE_CHECKING:
    from edof.format.document import Document

MANIFEST_FILE      = "manifest.json"
DOCUMENT_FILE      = "document.json"
RESOURCE_DIR       = "resources/"
ENCRYPTED_PAYLOAD  = "encrypted_payload.bin"
MIME_EDOF          = "application/vnd.edof+zip"


class EdofSerializer:

    # ══════════════════════════════════════════════════════════════════════════
    # Save
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def save(doc: "Document", path: str) -> None:
        data = EdofSerializer.to_bytes(doc)
        with open(path, "wb") as fh:
            fh.write(data)

    @staticmethod
    def to_bytes(doc: "Document") -> bytes:
        prot = getattr(doc, "_protection", None)
        mode = prot.mode if prot else "none"

        if mode == "none":
            return _save_plain(doc)
        if mode == "partial":
            return _save_partial(doc, prot)
        if mode == "full":
            return _save_full(doc, prot)
        raise ValueError(f"Unknown encryption mode {mode!r}")

    # ══════════════════════════════════════════════════════════════════════════
    # Load
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def load(path: str, password: Optional[str] = None,
             recovery_key: Optional[str] = None) -> "Document":
        with open(path, "rb") as fh:
            return EdofSerializer.from_bytes(fh.read(),
                                              password=password,
                                              recovery_key=recovery_key)

    @staticmethod
    def from_bytes(data: bytes, password: Optional[str] = None,
                   recovery_key: Optional[str] = None) -> "Document":
        from edof.format.document import Document

        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf, "r") as zf:
            names = set(zf.namelist())
            if MANIFEST_FILE not in names:
                raise EdofVersionError(
                    "Not a valid .edof file (manifest.json missing).")

            manifest = json.loads(zf.read(MANIFEST_FILE))
            file_version = manifest.get("edof_version", "0.0.0")
            compat = compatibility(file_version)

            if compat == "refuse":
                raise EdofVersionError(
                    f"Cannot read format version {file_version}. "
                    f"This library supports {_version_mod.FORMAT_VERSION_STR}.")
            if compat == "newer":
                warn_newer_version(file_version)

            protection_block = manifest.get("protection")
            mode = (protection_block or {}).get("mode", "none")

            if mode == "none":
                doc = _load_plain(zf, names, file_version=file_version)
            elif mode == "partial":
                doc = _load_partial(zf, names, protection_block,
                                     password, recovery_key,
                                     file_version=file_version)
            elif mode == "full":
                doc = _load_full(zf, names, protection_block,
                                  password, recovery_key,
                                  file_version=file_version)
            else:
                raise EdofVersionError(f"Unknown encryption mode {mode!r}")

        if compat == "older":
            doc._push_error(
                f"File was created with format version {file_version}; "
                f"migrated to {_version_mod.FORMAT_VERSION_STR}.")
        return doc

    @staticmethod
    def peek(path: str) -> dict:
        """Return the manifest without loading or decrypting the document."""
        with open(path, "rb") as fh:
            buf = io.BytesIO(fh.read())
        with zipfile.ZipFile(buf, "r") as zf:
            return json.loads(zf.read(MANIFEST_FILE))

    @staticmethod
    def read_preview(path: str) -> Optional[bytes]:
        """v4.1.5: Return PNG thumbnail bytes embedded in an .edof file, or
        None if no preview is present (older files / encrypted full mode)."""
        try:
            with open(path, "rb") as fh:
                buf = io.BytesIO(fh.read())
            with zipfile.ZipFile(buf, "r") as zf:
                if "preview.png" in zf.namelist():
                    return zf.read("preview.png")
        except Exception:
            return None
        return None


# ──────────────────────────────────────────────────────────────────────────────
#  Plain mode
# ──────────────────────────────────────────────────────────────────────────────

def _save_plain(doc) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_FILE, _build_manifest_json(doc, encryption=None))
        zf.writestr(DOCUMENT_FILE,
                    json.dumps(doc.to_dict(), ensure_ascii=False, indent=2))
        for entry in doc.resources.all_entries():
            zf.writestr(RESOURCE_DIR + entry.resource_id, entry.data)
        # v4.1.5: embed a compressed preview thumbnail (preview.png) of the
        # first page. Keeps file size small while enabling thumbnails in
        # file explorers / viewers.
        try:
            preview = _build_preview_thumbnail(doc)
            if preview:
                zf.writestr("preview.png", preview)
        except Exception:
            pass  # never fail the save because of a thumbnail problem
    return buf.getvalue()


def _build_preview_thumbnail(doc, max_dim_px: int = 256) -> Optional[bytes]:
    """v4.1.5: Render the first page of the document at a small size and
    return PNG bytes, or None on any failure.

    The thumbnail is sized so the longer side is at most ``max_dim_px``
    pixels, keeping the .edof file overhead minimal (typically <30 KB).
    """
    try:
        if not doc.pages:
            return None
        page = doc.pages[0]
        from edof.engine.renderer import render_page
        # Use a low target DPI so the thumbnail render is fast and small
        target_dpi = max(36, int(max_dim_px / max(page.width, page.height) * 25.4))
        img = render_page(page, doc.resources, doc.variables, dpi=target_dpi)
        # Cap final size
        img.thumbnail((max_dim_px, max_dim_px))
        out = io.BytesIO()
        img.save(out, "PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _load_plain(zf, names, *, file_version: str = "0.0.0") -> "Document":
    from edof.format.document import Document
    if DOCUMENT_FILE not in names:
        raise EdofVersionError("Corrupt .edof (document.json missing).")
    doc_dict = json.loads(zf.read(DOCUMENT_FILE))
    # v4.1.17: migrate pre-4.2.0 documents from pt → mm
    from edof.version import is_legacy_pt_format
    if is_legacy_pt_format(file_version):
        doc_dict = _migrate_pt_to_mm(doc_dict)
    resource_data: Dict[str, bytes] = {}
    for n in names:
        if n.startswith(RESOURCE_DIR) and n != RESOURCE_DIR:
            resource_data[n[len(RESOURCE_DIR):]] = zf.read(n)
    return Document.from_dict(doc_dict, resource_data)


# ─── v4.1.17: pt → mm migration for legacy .edof files (4.0.3 — 4.1.16.x) ──
_PT_TO_MM = 25.4 / 72.0

def _migrate_pt_to_mm(doc_dict: dict) -> dict:
    """In-place convert font_size, letter_spacing, min/max_font_size,
    and stroke widths from pt → mm. Called for documents with format
    version < 4.2.0.

    The migration is exhaustive: walks pages → objects → style/runs/border
    /stroke and any nested structures (groups, tables) so no pt value
    escapes."""
    def _conv_style_dict(style: dict) -> None:
        if not isinstance(style, dict): return
        for key in ("font_size", "letter_spacing",
                    "min_font_size", "max_font_size"):
            if key in style and isinstance(style[key], (int, float)):
                style[key] = float(style[key]) * _PT_TO_MM

    def _conv_stroke_dict(s: dict) -> None:
        if not isinstance(s, dict): return
        if "width" in s and isinstance(s["width"], (int, float)):
            s["width"] = float(s["width"]) * _PT_TO_MM

    def _conv_runs(runs) -> None:
        if not isinstance(runs, list): return
        for r in runs:
            if isinstance(r, dict) and "font_size" in r and isinstance(r["font_size"], (int, float)):
                r["font_size"] = float(r["font_size"]) * _PT_TO_MM

    def _walk_object(obj: dict) -> None:
        if not isinstance(obj, dict): return
        # style
        if "style" in obj: _conv_style_dict(obj["style"])
        # runs (textbox)
        if "runs" in obj:  _conv_runs(obj["runs"])
        # border / stroke / table_border
        for k in ("border", "stroke", "table_border"):
            if k in obj: _conv_stroke_dict(obj[k])
        # Tables
        if "cells" in obj and isinstance(obj["cells"], list):
            for row in obj["cells"]:
                if not isinstance(row, list): continue
                for cell in row:
                    if isinstance(cell, dict):
                        if "style" in cell: _conv_style_dict(cell["style"])
                        if "runs"  in cell: _conv_runs(cell["runs"])
        # Groups / nested objects
        if "objects" in obj and isinstance(obj["objects"], list):
            for child in obj["objects"]: _walk_object(child)

    # Top-level walk
    for page in doc_dict.get("pages", []):
        for obj in page.get("objects", []):
            _walk_object(obj)
    # Master pages (if any)
    for mp in doc_dict.get("master_pages", []) or []:
        for obj in mp.get("objects", []):
            _walk_object(obj)
    return doc_dict


# ──────────────────────────────────────────────────────────────────────────────
#  Full mode — entire content encrypted
# ──────────────────────────────────────────────────────────────────────────────

def _save_full(doc, prot) -> bytes:
    """Encrypted ZIP-in-AES blob."""
    from edof.crypto.encryption import encrypt_payload, _require_crypto
    _require_crypto()
    if prot.content_key is None:
        raise RuntimeError("Cannot save: document is locked")

    # Build inner ZIP with document.json and resources
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w", compression=zipfile.ZIP_DEFLATED) as iz:
        iz.writestr(DOCUMENT_FILE,
                    json.dumps(doc.to_dict(), ensure_ascii=False, indent=2))
        for entry in doc.resources.all_entries():
            iz.writestr(RESOURCE_DIR + entry.resource_id, entry.data)
    encrypted = encrypt_payload(inner_buf.getvalue(), prot.content_key)

    # Build outer ZIP
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_STORED) as oz:
        oz.writestr(MANIFEST_FILE, _build_manifest_json(doc, encryption=prot))
        oz.writestr(ENCRYPTED_PAYLOAD, encrypted)
    return outer.getvalue()


def _load_full(zf, names, protection_block, password, recovery_key,
               *, file_version: str = "0.0.0"):
    from edof.format.document import Document
    from edof.crypto.encryption import (decrypt_payload, EdofPasswordRequired,
                                          EdofWrongPassword,
                                          unwrap_with_any_password,
                                          unwrap_with_recovery_key)
    if ENCRYPTED_PAYLOAD not in names:
        raise EdofVersionError("Corrupt encrypted .edof (payload missing).")

    slots = protection_block.get("slots", [])
    content_key, perm_name = None, None
    if recovery_key:
        content_key = unwrap_with_recovery_key(slots, recovery_key)
        if content_key is None:
            raise EdofWrongPassword("Recovery key did not match")
        perm_name = "admin"
    elif password is not None:
        content_key, perm_name = unwrap_with_any_password(slots, password)
        if content_key is None:
            raise EdofWrongPassword("Password did not match any slot")
    else:
        raise EdofPasswordRequired(
            "This document is encrypted. Pass password=... or recovery_key=... "
            "to edof.load()")

    blob = zf.read(ENCRYPTED_PAYLOAD)
    inner_zip_bytes = decrypt_payload(blob, content_key)

    inner = io.BytesIO(inner_zip_bytes)
    with zipfile.ZipFile(inner, "r") as iz:
        inner_names = set(iz.namelist())
        if DOCUMENT_FILE not in inner_names:
            raise EdofVersionError("Corrupt encrypted payload.")
        doc_dict = json.loads(iz.read(DOCUMENT_FILE))
        # v4.1.17: pt → mm migration for legacy encrypted documents
        from edof.version import is_legacy_pt_format
        if is_legacy_pt_format(file_version):
            doc_dict = _migrate_pt_to_mm(doc_dict)
        resource_data: Dict[str, bytes] = {}
        for n in inner_names:
            if n.startswith(RESOURCE_DIR) and n != RESOURCE_DIR:
                resource_data[n[len(RESOURCE_DIR):]] = iz.read(n)

    doc = Document.from_dict(doc_dict, resource_data)
    # Restore protection state
    from edof.crypto.document_protection import DocumentProtection
    from edof.crypto.permissions import Permission
    doc._protection = DocumentProtection.from_manifest_section(protection_block)
    doc._protection.content_key = content_key
    doc._protection.permission  = Permission.from_string(perm_name or "view")
    return doc


# ──────────────────────────────────────────────────────────────────────────────
#  Partial mode — only sensitive fields encrypted
# ──────────────────────────────────────────────────────────────────────────────

def _save_partial(doc, prot) -> bytes:
    """Save with structure visible but text/image content encrypted."""
    from edof.crypto.encryption import encrypt_payload, _require_crypto
    _require_crypto()
    if prot.content_key is None:
        raise RuntimeError("Cannot save: document is locked")

    # Walk the doc dict, extract sensitive payloads, replace in-place with refs
    full_dict = doc.to_dict()
    secrets_payload: Dict[str, Any] = {
        "variables": _extract_variable_values(full_dict),
        "objects":   {},        # id → {text, runs, qrcode_data, cells_text, ...}
        "resources": {},        # resource_id → bytes (b64 in JSON not allowed; use sep)
    }

    # Walk and redact pages
    redacted_dict = _redact_sensitive(full_dict, secrets_payload)

    # Resources: save image/qr resources encrypted, fonts plain
    plain_resources: Dict[str, bytes]    = {}
    encrypted_resources: Dict[str, bytes] = {}
    for entry in doc.resources.all_entries():
        if (entry.mime_type or "").startswith("image/"):
            encrypted_resources[entry.resource_id] = entry.data
        else:
            plain_resources[entry.resource_id] = entry.data

    # Build the encrypted payload (JSON for sensitive fields + binary for images)
    payload_inner = io.BytesIO()
    with zipfile.ZipFile(payload_inner, "w", compression=zipfile.ZIP_DEFLATED) as iz:
        iz.writestr("secrets.json",
                    json.dumps(secrets_payload, ensure_ascii=False, indent=2))
        for rid, data in encrypted_resources.items():
            iz.writestr(f"resources/{rid}", data)
    encrypted_blob = encrypt_payload(payload_inner.getvalue(), prot.content_key)

    # Build the outer ZIP
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", compression=zipfile.ZIP_DEFLATED) as oz:
        oz.writestr(MANIFEST_FILE, _build_manifest_json(doc, encryption=prot))
        oz.writestr(DOCUMENT_FILE,
                    json.dumps(redacted_dict, ensure_ascii=False, indent=2))
        for rid, data in plain_resources.items():
            oz.writestr(RESOURCE_DIR + rid, data)
        oz.writestr(ENCRYPTED_PAYLOAD, encrypted_blob)
    return outer.getvalue()


def _load_partial(zf, names, protection_block, password, recovery_key,
                  *, file_version: str = "0.0.0"):
    from edof.format.document import Document
    from edof.crypto.encryption import (decrypt_payload, EdofPasswordRequired,
                                          EdofWrongPassword,
                                          unwrap_with_any_password,
                                          unwrap_with_recovery_key)
    if DOCUMENT_FILE not in names:
        raise EdofVersionError("Corrupt partial .edof (document.json missing).")
    redacted_dict = json.loads(zf.read(DOCUMENT_FILE))
    # v4.1.17: pt → mm migration for legacy partial-encrypted documents
    from edof.version import is_legacy_pt_format
    if is_legacy_pt_format(file_version):
        redacted_dict = _migrate_pt_to_mm(redacted_dict)

    plain_resources: Dict[str, bytes] = {}
    for n in names:
        if n.startswith(RESOURCE_DIR) and n != RESOURCE_DIR:
            plain_resources[n[len(RESOURCE_DIR):]] = zf.read(n)

    slots = protection_block.get("slots", [])
    content_key, perm_name = None, None
    if recovery_key:
        content_key = unwrap_with_recovery_key(slots, recovery_key)
        perm_name   = "admin" if content_key else None
    elif password is not None:
        content_key, perm_name = unwrap_with_any_password(slots, password)

    # If no key supplied or wrong key: load redacted view (just structure)
    if content_key is None:
        if password is not None or recovery_key:
            raise EdofWrongPassword("Password did not match any slot")
        # No password supplied — return locked redacted view
        doc = Document.from_dict(redacted_dict, plain_resources)
        from edof.crypto.document_protection import DocumentProtection
        from edof.crypto.permissions import VIEW
        doc._protection = DocumentProtection.from_manifest_section(protection_block)
        doc._protection.permission = VIEW
        doc._push_error(
            "Document is partially encrypted; loaded structure only. "
            "Pass password=... to edof.load() to decrypt content.")
        return doc

    # Decrypt the secrets payload
    if ENCRYPTED_PAYLOAD not in names:
        raise EdofVersionError("Corrupt partial .edof (encrypted payload missing).")
    blob = zf.read(ENCRYPTED_PAYLOAD)
    payload_bytes = decrypt_payload(blob, content_key)
    inner = io.BytesIO(payload_bytes)
    with zipfile.ZipFile(inner, "r") as iz:
        secrets_payload = json.loads(iz.read("secrets.json"))
        all_resources = dict(plain_resources)
        for n in iz.namelist():
            if n.startswith("resources/") and n != "resources/":
                all_resources[n[len("resources/"):]] = iz.read(n)

    # Re-hydrate the dict with secrets
    full_dict = _rehydrate_sensitive(redacted_dict, secrets_payload)

    doc = Document.from_dict(full_dict, all_resources)

    # Restore variables values from secrets
    for name, value in secrets_payload.get("variables", {}).items():
        try:
            doc.variables.set(name, value)
        except Exception:
            pass

    # Restore protection
    from edof.crypto.document_protection import DocumentProtection
    from edof.crypto.permissions import Permission
    doc._protection = DocumentProtection.from_manifest_section(protection_block)
    doc._protection.content_key = content_key
    doc._protection.permission  = Permission.from_string(perm_name or "view")
    return doc


# ──────────────────────────────────────────────────────────────────────────────
#  Sensitive field redaction (partial mode)
# ──────────────────────────────────────────────────────────────────────────────

REDACT_PLACEHOLDER = "█"   # ASCII-safe redaction marker not used in text otherwise

def _extract_variable_values(doc_dict: dict) -> dict:
    """Pull out variable values; structure (definitions) stays in plaintext."""
    out = {}
    var_section = doc_dict.get("variables", {})
    if isinstance(var_section, dict):
        for name, def_dict in var_section.items():
            if isinstance(def_dict, dict) and "value" in def_dict:
                out[name] = def_dict["value"]
                def_dict["value"] = None       # mutate in place — clear value
    return out

def _redact_sensitive(doc_dict: dict, secrets: dict) -> dict:
    """Walk pages → objects, move sensitive fields into secrets dict, replace with placeholders."""
    import copy
    out = copy.deepcopy(doc_dict)

    for page in out.get("pages", []):
        for obj in page.get("objects", []):
            _redact_object(obj, secrets)
    return out


def _redact_object(obj: dict, secrets: dict) -> None:
    """Redact one object dict in-place; sensitive content goes to secrets['objects'][id]."""
    oid = obj.get("id")
    if not oid: return
    saved = {}
    otype = obj.get("type")

    if otype == "textbox":
        if obj.get("text"):
            saved["text"] = obj["text"]; obj["text"] = REDACT_PLACEHOLDER
        if obj.get("runs"):
            saved["runs_texts"] = [r.get("text", "") for r in obj["runs"]]
            for r in obj["runs"]:
                r["text"] = REDACT_PLACEHOLDER

    elif otype == "imagebox":
        if obj.get("resource_id"):
            saved["resource_id"] = obj["resource_id"]
            obj["resource_id"] = None    # blank in redacted view

    elif otype == "qrcode":
        if obj.get("data"):
            saved["qr_data"] = obj["data"]
            obj["data"] = REDACT_PLACEHOLDER

    elif otype == "table":
        cells = obj.get("cells", [])
        cell_secrets = []
        for row_idx, row in enumerate(cells):
            row_data = []
            for col_idx, cell in enumerate(row):
                cell_data = {}
                if cell.get("text"):
                    cell_data["text"] = cell["text"]
                    cell["text"] = REDACT_PLACEHOLDER
                if cell.get("runs"):
                    cell_data["runs_texts"] = [r.get("text", "") for r in cell["runs"]]
                    for r in cell["runs"]:
                        r["text"] = REDACT_PLACEHOLDER
                row_data.append(cell_data)
            cell_secrets.append(row_data)
        if any(any(c for c in row) for row in cell_secrets):
            saved["cells"] = cell_secrets

    elif otype == "group":
        for child in obj.get("children", []):
            _redact_object(child, secrets)

    if saved:
        secrets["objects"][oid] = saved


def _rehydrate_sensitive(redacted_dict: dict, secrets: dict) -> dict:
    """Inverse of _redact_sensitive. Mutates a copy of redacted_dict."""
    import copy
    out = copy.deepcopy(redacted_dict)
    for page in out.get("pages", []):
        for obj in page.get("objects", []):
            _rehydrate_object(obj, secrets)
    # Variables
    var_section = out.get("variables", {})
    for name, value in secrets.get("variables", {}).items():
        if isinstance(var_section, dict) and name in var_section:
            if isinstance(var_section[name], dict):
                var_section[name]["value"] = value
    return out


def _rehydrate_object(obj: dict, secrets: dict) -> None:
    oid = obj.get("id")
    if not oid: return
    saved = secrets.get("objects", {}).get(oid)
    if not saved:
        # Group children?
        if obj.get("type") == "group":
            for child in obj.get("children", []):
                _rehydrate_object(child, secrets)
        return

    otype = obj.get("type")
    if otype == "textbox":
        if "text" in saved:
            obj["text"] = saved["text"]
        if "runs_texts" in saved and obj.get("runs"):
            for r, text in zip(obj["runs"], saved["runs_texts"]):
                r["text"] = text
    elif otype == "imagebox":
        if "resource_id" in saved:
            obj["resource_id"] = saved["resource_id"]
    elif otype == "qrcode":
        if "qr_data" in saved:
            obj["data"] = saved["qr_data"]
    elif otype == "table":
        if "cells" in saved:
            for row_idx, row in enumerate(obj.get("cells", [])):
                if row_idx >= len(saved["cells"]): break
                for col_idx, cell in enumerate(row):
                    if col_idx >= len(saved["cells"][row_idx]): continue
                    cell_data = saved["cells"][row_idx][col_idx]
                    if "text" in cell_data:
                        cell["text"] = cell_data["text"]
                    if "runs_texts" in cell_data and cell.get("runs"):
                        for r, text in zip(cell["runs"], cell_data["runs_texts"]):
                            r["text"] = text
    elif otype == "group":
        for child in obj.get("children", []):
            _rehydrate_object(child, secrets)


# ──────────────────────────────────────────────────────────────────────────────
#  Manifest building
# ──────────────────────────────────────────────────────────────────────────────

def _build_manifest_json(doc, encryption=None) -> str:
    manifest: Dict[str, Any] = {
        "mime":         MIME_EDOF,
        "edof_version": _version_mod.FORMAT_VERSION_STR,
        "writer_version": _version_mod.__version__,
        "id":           doc.id,
    }
    # In full encryption mode, hide title and page count from the manifest.
    # In partial mode, the user explicitly chose to keep structure visible
    # (which includes the title — they wanted it that way).
    mode = encryption.mode if encryption is not None else "none"
    if mode == "full":
        # Manifest reveals only that the doc is encrypted, plus KDF params
        manifest["title"] = ""
        manifest["pages"] = 0
    else:
        manifest["title"] = doc.title
        manifest["pages"] = len(doc.pages)
    if encryption is not None:
        manifest["protection"] = encryption.to_manifest_section()
    return json.dumps(manifest, ensure_ascii=False, indent=2)
