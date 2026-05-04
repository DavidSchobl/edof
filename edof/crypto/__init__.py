# edof/crypto/__init__.py
"""
v4.0.1: Encryption and access control for EDOF documents.

This subpackage adds:
  - AES-256-GCM document encryption with PBKDF2 key derivation
  - Multi-password slots, each granting a different permission level
  - Recovery keys for owner self-recovery
  - Permission-aware editor (load/save check capability)
  - Per-object lock_level for fine-grained restrictions

This module is OPTIONAL. By default, EDOF documents remain plain
(no encryption, no permissions). Once `doc.set_password(...)` is called,
the document switches to encrypted mode on the next save.

Public API:

    from edof.crypto import (
        Permission, VIEW, FILL, EDIT, DESIGN, ADMIN,
        EdofPasswordRequired, EdofWrongPassword,
        describe_permission,
    )

The Document object exposes:

    doc.set_password(level: str, password: str) → recovery_key | None
    doc.remove_password(level: str) → None
    doc.change_password(level: str, old: str, new: str) → None
    doc.encryption_mode → "none" | "partial" | "full"
    doc.permission_level → Permission (current session)
    doc.can(perm) → bool
    doc.require(perm) → None (raises if denied)
    doc.recovery_key → str | None    (only available right after generation)

And `edof.load(path, password=..., recovery_key=...)` accepts decryption args.
"""
from edof.crypto.permissions import (    # noqa: F401
    Permission, VIEW, FILL, EDIT, DESIGN, ADMIN,
    SLOT_NAMES, PERMISSION_DESCRIPTIONS,
    describe as describe_permission,
    slot_to_permission, can,
)
from edof.crypto.encryption import (    # noqa: F401
    EdofCryptoError, EdofPasswordRequired, EdofWrongPassword,
    EdofCryptoUnavailable,
    HAS_CRYPTO,
    KDF_ITERATIONS, KEY_SIZE, FORMAT_TAG,
    generate_recovery_key, normalize_recovery_key,
)

__all__ = [
    "Permission", "VIEW", "FILL", "EDIT", "DESIGN", "ADMIN",
    "SLOT_NAMES", "PERMISSION_DESCRIPTIONS", "describe_permission",
    "slot_to_permission", "can",
    "EdofCryptoError", "EdofPasswordRequired", "EdofWrongPassword",
    "EdofCryptoUnavailable",
    "HAS_CRYPTO", "KDF_ITERATIONS", "KEY_SIZE", "FORMAT_TAG",
    "generate_recovery_key", "normalize_recovery_key",
]
