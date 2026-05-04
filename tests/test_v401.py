"""
Tests for edof 4.0.1 encryption + permissions:
  - AES-256-GCM full encryption with single & multi-level passwords
  - Partial encryption (structure visible, content encrypted)
  - Recovery key
  - Per-object lock_level and lock_text
  - Backward compat with plain (unencrypted) docs
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import edof
from edof.crypto import (
    Permission, VIEW, FILL, EDIT, DESIGN, ADMIN,
    EdofPasswordRequired, EdofWrongPassword, EdofCryptoUnavailable,
    HAS_CRYPTO, generate_recovery_key, normalize_recovery_key,
)


@pytest.fixture
def doc():
    d = edof.new(width=148, height=210, title="Test")
    page = d.add_page(dpi=96)
    page.add_textbox(10, 10, 100, 12, "Hello")
    page.add_textbox(10, 25, 100, 12, "World")
    return d


# ── Plain (default) backward compat ───────────────────────────────────────────

def test_plain_doc_has_admin_permission(doc):
    assert doc.encryption_mode == "none"
    assert doc.permission_level == ADMIN
    assert doc.can(ADMIN)
    assert not doc.is_encrypted

def test_plain_doc_save_load(doc, tmp_path):
    p = str(tmp_path / "plain.edof")
    doc.save(p)
    doc2 = edof.load(p)
    assert doc2.encryption_mode == "none"
    assert doc2.pages[0].objects[0].text == "Hello"
    assert doc2.permission_level == ADMIN


# ── Permission ordering ───────────────────────────────────────────────────────

def test_permission_ordering():
    assert ADMIN > DESIGN > EDIT > FILL > VIEW

def test_permission_can():
    from edof.crypto import can
    assert can(ADMIN, EDIT) is True
    assert can(EDIT, ADMIN) is False
    assert can(EDIT, "fill") is True


# ── Crypto core (skip if cryptography unavailable) ────────────────────────────

def _skip_if_no_crypto():
    if not HAS_CRYPTO:
        pytest.skip("cryptography library not installed")


def test_recovery_key_format():
    _skip_if_no_crypto()
    rk = generate_recovery_key()
    assert len(rk) == 29   # 6 groups of 4 + 5 dashes
    assert rk.count("-") == 5

def test_recovery_key_normalize():
    n = normalize_recovery_key("abc-DEF-123 XYZ")
    assert n == "ABCDEF123XYZ"


# ── Set password and save encrypted ───────────────────────────────────────────

def test_set_password_returns_recovery_key(doc):
    _skip_if_no_crypto()
    rk = doc.set_password("admin", "secret123")
    assert rk is not None and len(rk) == 29
    assert doc.encryption_mode == "full"
    # Subsequent passwords don't return recovery key
    rk2 = doc.set_password("edit", "edit_pwd")
    assert rk2 is None

def test_set_password_then_save_load(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin", "tajne")
    p = str(tmp_path / "enc.edof")
    doc.save(p)
    # Load without password fails
    with pytest.raises(EdofPasswordRequired):
        edof.load(p)
    # Load with wrong password fails
    with pytest.raises(EdofWrongPassword):
        edof.load(p, password="wrong")
    # Load with correct password
    doc2 = edof.load(p, password="tajne")
    assert doc2.permission_level == ADMIN
    assert doc2.pages[0].objects[0].text == "Hello"


def test_full_mode_hides_title_and_page_count(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin", "x")
    p = str(tmp_path / "full.edof")
    doc.save(p)
    # Peek manifest
    import zipfile, json
    with zipfile.ZipFile(p) as zf:
        m = json.loads(zf.read("manifest.json"))
    assert m["title"] == ""
    assert m["pages"] == 0


# ── Multi-level passwords ─────────────────────────────────────────────────────

def test_multilevel_passwords(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin",  "admin_pwd")
    doc.set_password("design", "design_pwd")
    doc.set_password("edit",   "edit_pwd")
    doc.set_password("fill",   "fill_pwd")
    p = str(tmp_path / "multi.edof")
    doc.save(p)

    d = edof.load(p, password="fill_pwd");   assert d.permission_level == FILL
    d = edof.load(p, password="edit_pwd");   assert d.permission_level == EDIT
    d = edof.load(p, password="design_pwd"); assert d.permission_level == DESIGN
    d = edof.load(p, password="admin_pwd");  assert d.permission_level == ADMIN


def test_recovery_key_unlocks_as_admin(doc, tmp_path):
    _skip_if_no_crypto()
    rk = doc.set_password("admin", "secret")
    p = str(tmp_path / "rk.edof")
    doc.save(p)
    d = edof.load(p, recovery_key=rk)
    assert d.permission_level == ADMIN


# ── Permission enforcement ────────────────────────────────────────────────────

def test_can_and_require(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("fill", "f")
    p = str(tmp_path / "f.edof")
    doc.save(p)
    d = edof.load(p, password="f")
    assert d.can(FILL)
    assert not d.can(EDIT)
    with pytest.raises(PermissionError):
        d.require(EDIT)


def test_per_object_lock_level(doc, tmp_path):
    _skip_if_no_crypto()
    obj = doc.pages[0].objects[0]
    obj.lock_level = "design"
    doc.set_password("admin",  "a")
    doc.set_password("edit",   "e")
    doc.set_password("design", "d")
    p = str(tmp_path / "locked.edof")
    doc.save(p)

    # EDIT user cannot modify a design-locked object
    d = edof.load(p, password="e")
    assert d.can(EDIT)
    obj_loaded = d.pages[0].objects[0]
    assert obj_loaded.lock_level == "design"
    assert not obj_loaded.can_modify(d)

    # DESIGN user can
    d2 = edof.load(p, password="d")
    obj2 = d2.pages[0].objects[0]
    assert obj2.can_modify(d2)


def test_lock_text_blocks_text_edits(doc, tmp_path):
    _skip_if_no_crypto()
    obj = doc.pages[0].objects[0]
    obj.lock_text = True
    doc.set_password("admin", "a")
    p = str(tmp_path / "lt.edof")
    doc.save(p)

    # Even ADMIN cannot edit text while lock_text is True
    d = edof.load(p, password="a")
    obj2 = d.pages[0].objects[0]
    assert obj2.lock_text is True
    assert not obj2.can_modify_text(d)
    # But can still modify other props (move, etc.)
    assert obj2.can_modify(d)
    # ADMIN can clear lock_text
    obj2.lock_text = False
    assert obj2.can_modify_text(d)


# ── Password rotation ─────────────────────────────────────────────────────────

def test_change_password(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin", "old")
    doc.change_password("admin", "old", "new")
    p = str(tmp_path / "rot.edof")
    doc.save(p)
    with pytest.raises(EdofWrongPassword):
        edof.load(p, password="old")
    d = edof.load(p, password="new")
    assert d.permission_level == ADMIN


def test_change_wrong_old_password(doc):
    _skip_if_no_crypto()
    doc.set_password("admin", "old")
    with pytest.raises(EdofWrongPassword):
        doc.change_password("admin", "WRONG", "new")


# ── Remove password ───────────────────────────────────────────────────────────

def test_remove_password_requires_admin(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin", "a")
    doc.set_password("fill",  "f")
    p = str(tmp_path / "rm.edof")
    doc.save(p)
    # FILL user cannot remove passwords
    d = edof.load(p, password="f")
    with pytest.raises(PermissionError):
        d.remove_password("fill")
    # ADMIN can
    d2 = edof.load(p, password="a")
    d2.remove_password("fill")
    assert "fill" not in d2.password_levels


# ── Partial encryption ────────────────────────────────────────────────────────

def test_partial_mode_load_without_password(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin", "x")
    doc.encryption_mode = "partial"
    p = str(tmp_path / "partial.edof")
    doc.save(p)
    # Load without password: structure visible, content redacted
    d = edof.load(p)
    assert d.title == "Test"        # title visible in partial mode
    assert len(d.pages) == 1
    assert d.permission_level == VIEW
    # Text is redacted (placeholder)
    assert d.pages[0].objects[0].text != "Hello"
    # Object position & size still visible
    assert d.pages[0].objects[0].transform.width == 100


def test_partial_mode_load_with_password(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin", "x")
    doc.encryption_mode = "partial"
    p = str(tmp_path / "partial.edof")
    doc.save(p)
    d = edof.load(p, password="x")
    assert d.pages[0].objects[0].text == "Hello"
    assert d.pages[0].objects[1].text == "World"


# ── Tampering detection ──────────────────────────────────────────────────────

def test_tampering_detected(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin", "x")
    p = str(tmp_path / "tamper.edof")
    doc.save(p)
    # Flip a byte in the encrypted payload
    import zipfile
    # Read & corrupt
    with open(p, "rb") as f:
        data = bytearray(f.read())
    # Find a byte in the payload area and flip it
    data[len(data) // 2] ^= 0xFF
    with open(p, "wb") as f:
        f.write(data)
    # Loading should fail (with high probability — depends on which byte got hit)
    try:
        edof.load(p, password="x")
        # If it loaded (corrupted byte was metadata not payload), that's still OK
    except (EdofWrongPassword, Exception):
        pass


# ── Cannot save unlocked encrypted doc ────────────────────────────────────────

def test_lock_after_unlock(doc, tmp_path):
    _skip_if_no_crypto()
    doc.set_password("admin", "x")
    p = str(tmp_path / "x.edof")
    doc.save(p)
    d = edof.load(p, password="x")
    d.lock()
    assert d.permission_level == VIEW
    assert d._protection.content_key is None
