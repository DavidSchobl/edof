# edof/crypto/document_protection.py
"""
v4.0.1: Document-level protection state.

Mixed in via composition rather than inheritance to keep Document's
public API surface stable. Documents always carry a `_protection`
attribute (DocumentProtection instance) holding the encryption mode,
slot list, current session permission, and the recovery key.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from edof.crypto.permissions import Permission, VIEW, FILL, EDIT, DESIGN, ADMIN, can
from edof.crypto.encryption import (
    HAS_CRYPTO, EdofCryptoUnavailable, EdofWrongPassword,
    generate_content_key, generate_recovery_key,
    create_slot, create_recovery_slot, try_unwrap_slot,
    unwrap_with_any_password, unwrap_with_recovery_key,
    rewrap_slot, _require_crypto,
)

if TYPE_CHECKING:
    from edof.format.document import Document


class DocumentProtection:
    """Holds encryption-related state for a Document.

    Attributes:
        mode             — "none" | "partial" | "full"
        slots            — list of password slot dicts (serialized in manifest)
        content_key      — bytes, present only when document is unlocked
        permission       — current session Permission (default VIEW for encrypted)
        recovery_key     — only set transiently after first password is added,
                           returned to caller for safekeeping. Cleared after save.
    """

    def __init__(self):
        self.mode: str                    = "none"
        self.slots: List[Dict[str, Any]]  = []
        self.content_key: Optional[bytes] = None
        self.permission: Permission       = ADMIN     # plain doc = full access
        self._pending_recovery_key: Optional[str] = None

    # ── Mode and state ────────────────────────────────────────────────────────

    @property
    def is_encrypted(self) -> bool:
        return self.mode in ("partial", "full")

    @property
    def is_unlocked(self) -> bool:
        return (not self.is_encrypted) or (self.content_key is not None)

    def has_password(self, level: str) -> bool:
        """Return True if a slot for this level exists."""
        return any(s.get("permission") == level and not s.get("recovery")
                   for s in self.slots)

    @property
    def password_levels(self) -> List[str]:
        """List of slot permission names that have passwords set."""
        return [s["permission"] for s in self.slots
                if not s.get("recovery")]

    # ── Manage passwords ──────────────────────────────────────────────────────

    def set_password(self, level: str, password: str) -> Optional[str]:
        """Add or replace a password slot.

        Requires either:
          - The document has no passwords yet (becomes encrypted).
          - The current session has ADMIN permission.

        Returns a recovery key if this is the first password being set;
        otherwise None.
        """
        _require_crypto()
        if level not in ("fill", "edit", "design", "admin"):
            raise ValueError(f"Unknown level {level!r}; "
                             f"expected one of: fill, edit, design, admin")
        if password is None or password == "":
            raise ValueError("password cannot be empty")

        first_password = (self.mode == "none")
        recovery_key = None

        if first_password:
            # Initialize encryption: generate content key + recovery key
            self.mode = "full"
            self.content_key = generate_content_key()
            self.permission = ADMIN     # owner who is setting up gets ADMIN
            recovery_key = generate_recovery_key()
            self._pending_recovery_key = recovery_key
            # Add the recovery slot
            self.slots.append(create_recovery_slot(recovery_key, self.content_key))
        else:
            # Modifying an existing encrypted doc — must have ADMIN
            if self.permission != ADMIN:
                raise PermissionError(
                    "Setting or changing passwords requires ADMIN permission. "
                    f"Current session is {self.permission.to_string()!r}.")
            if self.content_key is None:
                raise RuntimeError("Document is encrypted but not unlocked")

        # Remove any existing slot at this level (replace)
        self.slots = [s for s in self.slots
                       if s.get("permission") != level or s.get("recovery")]
        # Add new slot
        self.slots.append(create_slot(password, self.content_key, level))
        return recovery_key

    def remove_password(self, level: str) -> None:
        """Remove a password slot. Requires ADMIN permission.

        Cannot remove the last non-recovery slot — would leave only the
        recovery key, which is unusual but not catastrophic; we allow it
        but warn (caller responsibility).
        """
        if self.permission != ADMIN:
            raise PermissionError(
                "Removing passwords requires ADMIN permission. "
                f"Current session is {self.permission.to_string()!r}.")
        before = len(self.slots)
        self.slots = [s for s in self.slots
                       if s.get("permission") != level or s.get("recovery")]
        if len(self.slots) == before:
            raise ValueError(f"No password set for level {level!r}")

    def change_password(self, level: str, old_password: str,
                         new_password: str) -> None:
        """Rotate a password without re-encrypting the payload.

        The caller doesn't need ADMIN if they can prove the old password
        for this level — proving the old password is sufficient to rotate
        that one slot.
        """
        _require_crypto()
        if not new_password:
            raise ValueError("new_password cannot be empty")
        for i, slot in enumerate(self.slots):
            if slot.get("permission") == level and not slot.get("recovery"):
                self.slots[i] = rewrap_slot(slot, old_password, new_password)
                return
        raise ValueError(f"No password set for level {level!r}")

    def clear_all_passwords(self) -> None:
        """Remove all encryption. Requires ADMIN permission."""
        if self.permission != ADMIN:
            raise PermissionError(
                "Clearing all passwords requires ADMIN permission.")
        self.mode = "none"
        self.slots = []
        self.content_key = None
        self.permission = ADMIN

    # ── Unlock ────────────────────────────────────────────────────────────────

    def unlock_with_password(self, password: str) -> Permission:
        """Try every slot with this password. Updates state on success.

        Returns the Permission level granted by the matching slot.
        Raises EdofWrongPassword if no slot matched.
        """
        ck, perm_name = unwrap_with_any_password(self.slots, password)
        if ck is None:
            raise EdofWrongPassword("No matching password slot")
        self.content_key = ck
        self.permission  = Permission.from_string(perm_name or "view")
        return self.permission

    def unlock_with_recovery_key(self, recovery_key: str) -> Permission:
        """Use the recovery key to unlock as ADMIN."""
        ck = unwrap_with_recovery_key(self.slots, recovery_key)
        if ck is None:
            raise EdofWrongPassword("Recovery key did not match")
        self.content_key = ck
        self.permission  = ADMIN
        return ADMIN

    def lock(self) -> None:
        """Forget the unlocked content key (paranoid cleanup)."""
        self.content_key = None
        self.permission  = VIEW

    # ── Permission checks ─────────────────────────────────────────────────────

    def can(self, required) -> bool:
        return can(self.permission, required)

    def require(self, required) -> None:
        if not self.can(required):
            from edof.crypto import PERMISSION_DESCRIPTIONS
            target = required if isinstance(required, Permission) \
                     else Permission.from_string(required)
            raise PermissionError(
                f"This action requires {target.to_string()!r} permission. "
                f"Current session has {self.permission.to_string()!r}. "
                f"Use Document → Unlock with a higher-privilege password.")

    # ── Manifest serialization ────────────────────────────────────────────────

    def to_manifest_section(self) -> Optional[Dict[str, Any]]:
        """Return the encryption-related section of the manifest, or None."""
        if self.mode == "none":
            return None
        return {
            "mode":   self.mode,
            "format": "edof-aes-256-gcm-v1",
            "slots":  [dict(s) for s in self.slots],
        }

    @classmethod
    def from_manifest_section(cls, data: Dict[str, Any]) -> "DocumentProtection":
        prot = cls()
        prot.mode  = data.get("mode", "none")
        prot.slots = list(data.get("slots", []))
        # Default: fully locked until the loader unlocks it
        prot.permission  = VIEW
        prot.content_key = None
        return prot

    # ── Pending recovery key handling ────────────────────────────────────────

    def take_pending_recovery_key(self) -> Optional[str]:
        """Get and clear any pending recovery key (returned exactly once)."""
        rk = self._pending_recovery_key
        self._pending_recovery_key = None
        return rk
