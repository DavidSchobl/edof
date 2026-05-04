# edof/crypto/encryption.py
"""
v4.0.1: Cryptographic primitives for EDOF document encryption.

Algorithm: AES-256-GCM with PBKDF2-SHA256 (600,000 iterations) for key derivation.

Layout of an encrypted document at rest:

    template.edof (ZIP)
    ├── manifest.json           (cleartext, advertises encryption)
    ├── encrypted_payload.bin   (AES-256-GCM ciphertext of inner data)
    └── (optionally for partial mode) document.json + resources/

Key hierarchy:

    User passwords ──► slot keys (via PBKDF2 with per-slot salt)
    Slot keys ──► (encrypts) wrapped content key
    Content key (32 random bytes) ──► (AES-GCM) encrypts payload

Each password slot independently wraps the same content key, so changing
any password only re-wraps that slot — the bulk payload is never re-encrypted.

A recovery key (24 random alphanumeric chars) is treated as a special
admin-level slot, allowing the owner to recover an admin-locked document
if they lose the admin password.
"""
from __future__ import annotations
import os
import json
import secrets
import hmac
import hashlib
from base64 import b64encode, b64decode
from typing import Tuple, Optional, Dict, Any

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ── Parameters (do not change between releases without migration) ─────────────

KDF_ALGORITHM    = "pbkdf2-sha256"
KDF_ITERATIONS   = 600_000
KEY_SIZE         = 32          # bytes — 256-bit
SALT_SIZE        = 16          # bytes
NONCE_SIZE       = 12          # bytes — recommended for GCM
TAG_SIZE         = 16          # bytes — GCM authentication tag
RECOVERY_KEY_LEN = 24          # alphanumeric chars
FORMAT_TAG       = "edof-aes-256-gcm-v1"


# ── Errors ────────────────────────────────────────────────────────────────────

class EdofCryptoError(Exception):
    """Base class for crypto-related EDOF errors."""

class EdofPasswordRequired(EdofCryptoError):
    """The file is encrypted but no password was supplied."""

class EdofWrongPassword(EdofCryptoError):
    """The supplied password did not match any slot."""

class EdofCryptoUnavailable(EdofCryptoError):
    """The 'cryptography' library is not installed."""


def _require_crypto() -> None:
    if not HAS_CRYPTO:
        raise EdofCryptoUnavailable(
            "Encryption requires the 'cryptography' package. Install with:\n"
            "    pip install edof[crypto]"
        )


# ── Key derivation ────────────────────────────────────────────────────────────

def derive_slot_key(password: str, salt: bytes,
                    iterations: int = KDF_ITERATIONS) -> bytes:
    """Derive a 32-byte AES key from a password using PBKDF2-SHA256."""
    _require_crypto()
    if password is None:
        raise ValueError("password must not be None")
    pwd_bytes = password.encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(pwd_bytes)


def generate_content_key() -> bytes:
    """Generate a fresh random 32-byte content key."""
    return secrets.token_bytes(KEY_SIZE)


def generate_recovery_key() -> str:
    """Generate a human-friendly 24-char alphanumeric recovery key.

    Format: 6 groups of 4 chars separated by '-', for example:
        '7K3F-9XQM-2N8P-VR4A-HT6L-Z5BJ'
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # exclude I, O, 0, 1
    parts = []
    for _ in range(6):
        parts.append("".join(secrets.choice(alphabet) for _ in range(4)))
    return "-".join(parts)


def normalize_recovery_key(key: str) -> str:
    """Normalize a user-typed recovery key for comparison."""
    return key.replace("-", "").replace(" ", "").upper()


# ── AES-GCM payload encryption ────────────────────────────────────────────────

def encrypt_payload(plaintext: bytes, content_key: bytes,
                    associated_data: Optional[bytes] = None) -> bytes:
    """Encrypt arbitrary bytes with the content key. Returns nonce || ciphertext.

    The output is self-contained: the first 12 bytes are the nonce, and the
    remainder is the GCM ciphertext (which already includes the auth tag).
    """
    _require_crypto()
    nonce = secrets.token_bytes(NONCE_SIZE)
    aes = AESGCM(content_key)
    ct = aes.encrypt(nonce, plaintext, associated_data)
    return nonce + ct


def decrypt_payload(blob: bytes, content_key: bytes,
                    associated_data: Optional[bytes] = None) -> bytes:
    """Decrypt nonce || ciphertext produced by encrypt_payload."""
    _require_crypto()
    if len(blob) < NONCE_SIZE + TAG_SIZE:
        raise EdofCryptoError("Encrypted blob is too short")
    nonce = blob[:NONCE_SIZE]
    ct    = blob[NONCE_SIZE:]
    aes = AESGCM(content_key)
    try:
        return aes.decrypt(nonce, ct, associated_data)
    except Exception as e:
        raise EdofWrongPassword("Could not decrypt — wrong key or tampered data") from e


# ── Slot management ───────────────────────────────────────────────────────────

def create_slot(password: str, content_key: bytes,
                permission_level: str) -> Dict[str, Any]:
    """Create a new password slot wrapping the content key.

    Returns a dict serializable to JSON with all the data needed to later
    unwrap the content key given the same password.
    """
    _require_crypto()
    salt = secrets.token_bytes(SALT_SIZE)
    slot_key = derive_slot_key(password, salt)
    wrapped = encrypt_payload(content_key, slot_key)
    return {
        "permission":  permission_level,
        "kdf":         KDF_ALGORITHM,
        "iterations":  KDF_ITERATIONS,
        "salt":        b64encode(salt).decode("ascii"),
        "wrapped_key": b64encode(wrapped).decode("ascii"),
    }


def create_recovery_slot(recovery_key: str, content_key: bytes) -> Dict[str, Any]:
    """A recovery slot is just an ADMIN slot keyed by the recovery key string."""
    return create_slot(recovery_key, content_key, permission_level="admin") | {"recovery": True}


def try_unwrap_slot(slot: Dict[str, Any], password: str) -> Optional[bytes]:
    """Try to unwrap the content key from a slot using the password.

    Returns the content key on success, or None if this slot doesn't match.
    """
    _require_crypto()
    try:
        salt = b64decode(slot["salt"])
        wrapped = b64decode(slot["wrapped_key"])
        slot_key = derive_slot_key(password, salt,
                                    iterations=int(slot.get("iterations", KDF_ITERATIONS)))
        return decrypt_payload(wrapped, slot_key)
    except EdofWrongPassword:
        return None
    except Exception:
        return None


def unwrap_with_any_password(slots: list, password: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Try the password against every slot. Returns (content_key, slot_permission)."""
    for slot in slots:
        ck = try_unwrap_slot(slot, password)
        if ck is not None:
            return ck, slot.get("permission", "view")
    return None, None


def unwrap_with_recovery_key(slots: list, recovery_key: str) -> Optional[bytes]:
    """Try the recovery key against any slot marked recovery."""
    normalized = normalize_recovery_key(recovery_key)
    # Recovery slots need to handle both the formatted and normalized form
    for slot in slots:
        if not slot.get("recovery"): continue
        for candidate in (recovery_key, normalized):
            ck = try_unwrap_slot(slot, candidate)
            if ck is not None:
                return ck
    return None


def rewrap_slot(slot: Dict[str, Any], old_password: str,
                new_password: str) -> Dict[str, Any]:
    """Re-wrap the same content key in this slot with a new password.

    Used by Document.change_password to rotate a single slot without
    re-encrypting the bulk payload.
    """
    ck = try_unwrap_slot(slot, old_password)
    if ck is None:
        raise EdofWrongPassword("Old password did not unwrap this slot")
    new_slot = create_slot(new_password, ck, slot["permission"])
    if slot.get("recovery"):
        new_slot["recovery"] = True
    return new_slot
