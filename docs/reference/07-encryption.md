# Reference: Encryption & Permissions

> Requires `pip install edof[crypto]`

EDOF 4.0.1 supports AES-256-GCM document encryption with multi-level password protection and recovery keys. By default, documents are plain (no encryption) — encryption is opt-in and adds zero friction when you don't use it.

## Quick example

```python
import edof
from edof.crypto import EDIT, ADMIN

# Build a document
doc = edof.new(title="Confidential")
page = doc.add_page()
page.add_textbox(10, 10, 100, 12, "TOP SECRET")

# Set up multi-level passwords (writes recovery key to your safe!)
recovery_key = doc.set_password("admin",  "ownerSecret")
doc.set_password("design", "designerPwd")
doc.set_password("edit",   "editorPwd")
doc.set_password("fill",   "templateUser")

print("RECOVERY KEY:", recovery_key)   # 24-character key, shown ONLY ONCE

doc.save("secret.edof")

# Loading
doc = edof.load("secret.edof", password="editorPwd")
print(doc.permission_level)            # Permission.EDIT
doc.can(ADMIN)                         # False
```

---

## Permission levels

There are five hierarchical permission levels. Higher levels imply all lower levels.

| Level | Constant | Allows |
|---|---|---|
| `view`   | `VIEW`   | Render, print, export. No modifications. |
| `fill`   | `FILL`   | view + change variable values (template filling). |
| `edit`   | `EDIT`   | fill + change object `.text` and rich-text run text. |
| `design` | `DESIGN` | edit + change styles, fonts, colors, layout, structure (add/remove objects and pages). |
| `admin`  | `ADMIN`  | design + manage passwords, recovery key, override per-object locks. |

Import them:

```python
from edof.crypto import VIEW, FILL, EDIT, DESIGN, ADMIN, Permission
```

`Permission` is an `IntEnum`, so you can compare them directly:

```python
if doc.permission_level >= EDIT:
    print("Can edit text")
```

---

## Encryption modes

| Mode | What's encrypted | What's visible without password |
|---|---|---|
| `none` (default) | Nothing | Everything (plain ZIP) |
| `partial` | Object text, rich-text runs, image data, QR data, table cell text, variable values | Page count, page sizes, fonts, colors, layout, structure, document title |
| `full` | Everything | Only "encrypted=true" + KDF parameters + slot count |

Set the mode after enabling encryption:

```python
doc.set_password("admin", "x")
doc.encryption_mode = "partial"          # default after first password is "full"
doc.save("template.edof")
```

### When to use partial vs full

**Use `partial`** when you want to share a layout / template publicly, but the actual content is private. Example: an invoice template — anyone can see how it's structured (placement of fields, fonts, branding), but the actual invoice numbers, prices, and customer data are encrypted.

**Use `full`** for private documents where even the existence of pages, layout, and the title should be hidden. Example: a confidential contract that's stored on a shared drive.

### Loading partial documents without a password

If you load a `partial` document without supplying a password, it loads in a **redacted view**:

```python
doc = edof.load("partial.edof")    # no password
print(doc.title)                   # visible
print(doc.pages[0].objects[0].text)
# '█' — placeholder, real text is encrypted
```

The placeholder is a single `█` character, replacing all sensitive text content. The user can see the layout and structure but no actual content.

This mode lets the editor render a "preview" of an encrypted template even without a password — useful in file managers, thumbnails, etc.

---

## Setting up encryption

### Adding the first password

```python
doc = edof.new()
recovery_key = doc.set_password("admin", "myMasterPassword")
```

When you set the **first** password on a document:
1. A 32-byte random content key is generated. This key encrypts all sensitive data.
2. A 24-character recovery key is generated, shown to you exactly once. **Save it.**
3. The document switches to `encryption_mode = "full"`.
4. Your password and the recovery key both wrap the same content key (independent slots).
5. Your session is granted ADMIN permission (you're the one who set the password).

```python
print(recovery_key)
# "7K3F-9XQM-2N8P-VR4A-HT6L-Z5BJ"
```

### Adding more passwords

Subsequent `set_password` calls add slots without generating new recovery keys:

```python
doc.set_password("design", "designerPwd")    # returns None
doc.set_password("edit",   "editorPwd")      # returns None
doc.set_password("fill",   "userPwd")        # returns None
```

You can have any subset of the four levels — you don't need all four. A common pattern:
- `admin` only — the simplest case, single password gives full access
- `admin` + `fill` — owner can do everything, users can fill the template
- `admin` + `edit` + `fill` — adds an editor role for proofreaders
- All four — large team with a designer role separate from editors

### Permissions for password operations

- **Adding the first password:** anyone (the act of locking the document)
- **Adding/replacing additional passwords:** requires `admin`
- **Changing a password:** requires the **old password** (not necessarily admin)
- **Removing a password:** requires `admin`
- **Clearing all protection:** requires `admin`

The reasoning: knowing the old password proves you were trusted at that level, so you can rotate it (e.g. the editor leaves, the owner gives the editor role to someone else by changing `edit` password).

---

## Loading encrypted documents

### With a password

```python
doc = edof.load("secret.edof", password="editorPwd")
```

The library tries the password against every slot. The first match determines the granted permission.

If no slot matches → raises `EdofWrongPassword`.

If the file is encrypted but no password supplied → raises `EdofPasswordRequired`.

### With the recovery key

```python
doc = edof.load("secret.edof", recovery_key="7K3F-9XQM-2N8P-VR4A-HT6L-Z5BJ")
```

The recovery key always grants ADMIN access. Useful when the admin password is lost.

---

## Permission checking

After loading, check what's allowed:

```python
doc.permission_level                # Permission.EDIT
doc.can(EDIT)                       # True
doc.can(DESIGN)                     # False

# Raises PermissionError if level is insufficient
doc.require(EDIT)
doc.require(DESIGN)                 # raises
```

`can()` is for branching logic; `require()` is for guarding operations that need a level.

### Per-object permissions

Each object can override doc-level permissions for its modification:

```python
heading = page.add_textbox(15, 15, 180, 18, "MUST NEVER CHANGE")
heading.lock_level = "design"       # only design+ can modify
heading.lock_text = True            # text NEVER editable, even by admin
```

`lock_level` raises the bar above the document's general permission. A user with `edit` permission can change other text but not this heading.

`lock_text = True` is a hard text lock. Even ADMIN cannot change `obj.text` or `obj.runs` until they explicitly clear the flag (which requires ADMIN). Useful for "this header must never change accidentally".

Helper methods on each object:

```python
obj.can_modify(doc)         # respects doc permission AND lock_level
obj.can_modify_text(doc)    # also respects lock_text
```

The editor uses these to disable UI buttons and show "needs *level* password" dialogs.

---

## Password rotation

To rotate a password (someone leaves, password compromised, periodic rotation policy):

```python
doc = edof.load("secret.edof", password="oldEditor")
doc.change_password("edit", "oldEditor", "newEditor")
doc.save("secret.edof")
```

Note: `change_password` does **not** re-encrypt the bulk content. It just rewraps the slot key — fast even for huge documents.

---

## Removing protection

```python
doc = edof.load("secret.edof", password="adminPwd")
doc.remove_password("fill")          # remove one slot
doc.clear_all_protection()            # remove all encryption (becomes plain)
doc.save("plain.edof")
```

After `clear_all_protection`, the document is back to `encryption_mode = "none"` and saves as a plain ZIP. Of course, anyone who had a copy of the encrypted file can still decrypt their copy with their old password — clearing protection only affects future saves.

---

## Recovery key

The recovery key is shown **once** when you set the first password. After that:
- It's stored in `doc.recovery_key` until you call `consume_recovery_key()` to clear it
- It's saved into the document file as a special slot
- It cannot be retrieved later from the document — there's no API to "show me the recovery key again"

If you lose all your passwords AND the recovery key, the document is **mathematically unrecoverable**. There is no backdoor.

```python
recovery_key = doc.set_password("admin", "x")
print(recovery_key)
# Save it somewhere safe!

# Optional: clear from memory after copying
doc.consume_recovery_key()
```

The editor automatically shows a recovery key dialog with a "I have saved this key" confirmation gate.

### Generating a new recovery key

You cannot generate a new recovery key for an existing protected document — it's tied to the content key. If you want a fresh recovery key:

```python
doc = edof.load("secret.edof", password="admin_pwd")
doc.clear_all_protection()                 # back to plain
new_recovery = doc.set_password("admin", "admin_pwd")  # re-protect, new RK
doc.save("secret.edof")
```

This rotates everything — content key, all slots, recovery key.

---

## Cryptographic details

For curious readers / security reviewers:

| Component | Specification |
|---|---|
| Symmetric cipher | AES-256-GCM |
| Key size | 256 bits |
| Nonce size | 96 bits (12 bytes), random per ciphertext |
| Auth tag size | 128 bits (16 bytes) |
| KDF | PBKDF2-HMAC-SHA256 |
| KDF iterations | 600,000 |
| Salt size | 128 bits (16 bytes), random per slot |
| Random source | Python's `secrets.token_bytes()` (CSPRNG) |
| Recovery key alphabet | 32 chars: `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (excludes I, O, 0, 1) |
| Recovery key length | 24 alphanumeric (~120 bits entropy) |

### Slot structure

Each password slot in the manifest is a JSON object:

```json
{
  "permission": "edit",
  "kdf": "pbkdf2-sha256",
  "iterations": 600000,
  "salt": "<base64, 16 bytes>",
  "wrapped_key": "<base64 — AES-GCM encryption of content key with derived slot key>"
}
```

When unlocking, edof iterates over slots, derives the slot key from the password using the slot's salt, attempts to decrypt the wrapped content key, and uses the GCM auth tag to verify the password is correct (no false positives).

### Content key wrapping

A single 32-byte content key encrypts the actual document. Each password slot wraps a **copy** of the same content key — so the bulk content is encrypted only once. Changing one password rewraps just that slot, not the entire payload.

### Authenticated encryption

GCM provides authenticated encryption: any tampering with the ciphertext (even a single bit flip) makes decryption fail. So:
- Modifying the encrypted document outside the library → unrecoverable
- Truncating the file → fails to decrypt
- Replacing one slot with another → that slot's password no longer works

---

## What encryption protects against

- **Reading content without a password.** Without a matching password (or the recovery key), the encrypted payload is just random bytes.
- **Tampering.** GCM auth tag detects any modification of the ciphertext.
- **Brute-forcing weak passwords.** PBKDF2 with 600,000 iterations is intentionally slow (~0.5s per password attempt on modern hardware), which makes offline brute-force expensive for short passwords. For longer passwords (12+ characters with mixed types), brute force is infeasible.

## What encryption does NOT protect against

- **A user with the password running their own decryption code.** They have the password — they can do whatever they want with the content.
- **Side-channel attacks on the host.** Memory dumps, keyloggers, screen recording while you have the document open — outside the library's threat model.
- **Loss of all passwords AND the recovery key.** No backdoor. The document is unrecoverable.
- **A malicious build of edof.** Verify the source if security is critical.

---

## Editor integration

The PyQt6 editor (`edof-editor`) provides a UI for all encryption operations:

- **File → Open**: detects encrypted files, prompts for password / recovery key, three-strikes-and-out
- **Document → Unlock for editing… (Ctrl+Shift+L)**: prompts for password, shows what the granted level can / cannot do
- **Document → Protection…**: full management dialog — set/change/remove passwords, switch full ↔ partial mode, clear all protection
- **Document → Re-lock**: forgets the cached content key (paranoid mode)
- **Status bar**: shows current state — 🔓 Plain / 🔒 Locked / 🔓 Unlocked: \<level\>
- **Permission-aware action gating**: actions you can't take are disabled or show clear "needs *level* password" dialogs
- **Recovery key dialog**: monospace font, "Copy to clipboard" button, "I have saved this key" gate before close

When opening a legacy EDOF 2 archive that had an XOR password, the editor offers to set up real AES-256 encryption.

---

## API summary

### On the document

```python
# Setup
doc.set_password(level, password) → str | None    # returns recovery key on first call
doc.change_password(level, old_pwd, new_pwd)
doc.remove_password(level)
doc.clear_all_protection()

# State
doc.encryption_mode                                # "none" | "partial" | "full"
doc.is_encrypted                                   # bool
doc.is_locked                                      # bool — encrypted but not unlocked
doc.permission_level                               # Permission enum
doc.password_levels                                # list of level names with passwords set
doc.recovery_key                                   # str | None (pending, returned once)
doc.consume_recovery_key()                         # str | None — clear pending RK

# Unlock / lock
doc.unlock(password=..., recovery_key=...)         # → Permission
doc.lock()                                         # forget content key

# Permission checks
doc.can(level) → bool
doc.require(level)                                 # raises if denied
```

### On objects

```python
obj.lock_level = "design"      # str: "" | "fill" | "edit" | "design" | "admin"
obj.lock_text = True           # bool

obj.can_modify(doc) → bool
obj.can_modify_text(doc) → bool
```

### Loading

```python
edof.load(path, password="...", recovery_key="...")
```

### Module imports

```python
from edof.crypto import (
    Permission, VIEW, FILL, EDIT, DESIGN, ADMIN,
    EdofPasswordRequired, EdofWrongPassword, EdofCryptoError, EdofCryptoUnavailable,
    HAS_CRYPTO,                          # bool — whether cryptography lib is available
    generate_recovery_key,                # generate a key without using it
    normalize_recovery_key,               # strip dashes / case
    describe_permission,                  # → dict with "label", "allowed", "denied"
)
```
