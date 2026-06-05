# .edof file format internals

The `.edof` file is a ZIP archive. This document describes its internal structure for anyone who wants to:
- Inspect a file with standard ZIP tools
- Build alternative readers / writers
- Understand the encryption layout
- Debug corruption issues

> Format version covered: **4.2.0**

---

## Plain (unencrypted) layout

```
template.edof  (ZIP archive)
├── manifest.json     — header: version, title, page count, etc.
├── document.json     — full document data (pages, objects, variables)
└── resources/        — embedded binary resources
    ├── <resource_id_1>
    ├── <resource_id_2>
    └── ...
```

Inspect with any ZIP tool:

```bash
unzip -l template.edof
# Archive:  template.edof
#   Length      Name
#   --------    ----
#       312    manifest.json
#     14385    document.json
#     45623    resources/img_a8d2c1
#     12440    resources/img_b9f4e7
#   --------
#     72760    4 files
```

### `manifest.json`

Top-level metadata. Always cleartext (even in encrypted archives).

```json
{
  "edof_version": "4.2.0",
  "title": "Certificate",
  "author": "Jan Novák",
  "description": "Internal certificate template",
  "pages": 1,
  "id": "abc123-def456-789...",
  "created_at": "2026-05-04T10:30:00Z",
  "protection": null
}
```

Fields:
- `edof_version: str` — semantic version of the format. Loaders use this to detect features.
- `title, author, description: str` — user-supplied metadata
- `pages: int` — page count
- `id: str` — UUID
- `created_at: str` — ISO-8601 timestamp
- `protection: object | null` — encryption metadata; `null` for plain documents

### `document.json`

The main payload. Schema (simplified):

```json
{
  "id": "abc123-...",
  "title": "Certificate",
  "author": "Jan Novák",
  "description": "...",
  "pages": [
    {
      "id": "page_001",
      "width_mm": 297,
      "height_mm": 210,
      "dpi": 300,
      "color_space": "RGB",
      "bit_depth": 8,
      "background": [255, 255, 255, 255],
      "objects": [
        {
          "type": "textbox",
          "id": "obj_001",
          "name": "",
          "tags": [],
          "transform": {
            "x": 15.0, "y": 15.0,
            "width": 180.0, "height": 12.0,
            "rotation": 0.0, "flip_h": false, "flip_v": false
          },
          "layer": 0,
          "opacity": 1.0,
          "visible": true,
          "visible_if": "",
          "blend_mode": "normal",
          "lock_level": "",
          "lock_text": false,
          "shadow": null,
          "text": "Hello world",
          "runs": [],
          "style": {
            "font_family": "Helvetica",
            "font_size": 14.0,
            "bold": false,
            "italic": false,
            "alignment": "left",
            "color": [0, 0, 0],
            "wrap": true,
            "auto_shrink": false,
            "auto_fill": false
          },
          "padding": [0, 0, 0, 0],
          "border": null,
          "fill": null,
          "variable": ""
        }
      ]
    }
  ],
  "variables": {
    "names": ["recipient", "score"],
    "definitions": {
      "recipient": {
        "name": "recipient",
        "type": "text",
        "default": null,
        "required": true,
        "label": "Recipient",
        "help": "",
        "choices": null,
        "max_length": null
      }
    },
    "values": {
      "recipient": "Jan Novák"
    }
  },
  "resources": {
    "img_a8d2c1": {
      "filename": "logo.png",
      "mime_type": "image/png",
      "size": 45623,
      "checksum": "sha256:..."
    }
  },
  "metadata": {
    "edof_version": "4.2.0",
    "created_at": "2026-05-04T10:30:00Z",
    "modified_at": "2026-05-04T11:45:00Z"
  }
}
```

### `resources/<id>`

Each binary resource is stored as a separate file in the `resources/` directory. The filename is the resource ID.

The resource's metadata (filename, mime_type) is in `document.json` under `resources`, not on the file itself.

For new resources, IDs are generated as short hashes. They're treated as opaque strings — don't parse them.

---

## Encrypted layout — `full` mode

When `encryption_mode = "full"`, the entire content is wrapped in a single AES-GCM ciphertext.

```
secret.edof  (ZIP archive)
├── manifest.json           — cleartext, advertises encryption
└── encrypted_payload.bin   — AES-GCM ciphertext of the entire payload
```

`manifest.json` in encrypted mode:

```json
{
  "edof_version": "4.2.0",
  "title": "<encrypted>",
  "author": "<encrypted>",
  "description": "<encrypted>",
  "pages": 0,
  "id": "abc123-...",
  "created_at": "2026-05-04T10:30:00Z",
  "protection": {
    "mode": "full",
    "kdf": "pbkdf2-sha256",
    "iterations": 600000,
    "slots": [
      {
        "permission": "admin",
        "salt": "<base64, 16 bytes>",
        "wrapped_key": "<base64, 60 bytes — AES-GCM-encrypted content key>"
      },
      {
        "permission": "design",
        "salt": "<base64, 16 bytes>",
        "wrapped_key": "<base64, 60 bytes>"
      },
      {
        "permission": "edit",
        "salt": "<base64, 16 bytes>",
        "wrapped_key": "<base64, 60 bytes>"
      },
      {
        "permission": "fill",
        "salt": "<base64, 16 bytes>",
        "wrapped_key": "<base64, 60 bytes>"
      },
      {
        "permission": "_recovery",
        "salt": "<base64, 16 bytes>",
        "wrapped_key": "<base64, 60 bytes>"
      }
    ]
  }
}
```

Fields:
- `protection.mode: "full" | "partial"`
- `protection.kdf: "pbkdf2-sha256"` (only this is currently supported)
- `protection.iterations: int` — PBKDF2 iteration count
- `protection.slots[]: object[]` — one per password
  - `permission: str` — `"fill"`, `"edit"`, `"design"`, `"admin"`, `"_recovery"`
  - `salt: str` (base64) — 16 random bytes per slot
  - `wrapped_key: str` (base64) — AES-GCM encryption of the 32-byte content key, using the slot's derived key. 60 bytes total = 12 nonce + 32 ciphertext + 16 GCM tag.

### `encrypted_payload.bin`

Format:
```
[12-byte nonce][N-byte ciphertext][16-byte GCM tag]
```

The plaintext (after decryption) is a JSON object containing:

```json
{
  "title": "Real Title",
  "author": "Real Author",
  "description": "...",
  "document": { ...full document.json... },
  "resources": {
    "img_a8d2c1": "<base64 of binary data>",
    ...
  }
}
```

Note that resources are inlined as base64 strings in the encrypted payload (not separate files), because each resource as a separate ZIP entry would leak their sizes.

---

## Encrypted layout — `partial` mode

When `encryption_mode = "partial"`, structure is preserved but content is encrypted.

```
template.edof  (ZIP archive)
├── manifest.json           — cleartext, with protection block
├── document.json           — cleartext, but with sensitive fields redacted
├── encrypted_payload.bin   — AES-GCM ciphertext of sensitive content
└── resources/
    ├── img_a8d2c1          — non-sensitive resources (e.g. logos)
    └── ...
```

`manifest.json` is similar to full mode, but `title`, `pages` count, etc. are real values:

```json
{
  "edof_version": "4.2.0",
  "title": "Confidential Template",
  "pages": 5,
  "id": "abc123-...",
  "protection": {
    "mode": "partial",
    "kdf": "pbkdf2-sha256",
    "iterations": 600000,
    "slots": [...]
  }
}
```

`document.json` in partial mode has sensitive fields replaced with placeholders:

```json
{
  "pages": [
    {
      "objects": [
        {
          "type": "textbox",
          "transform": {...},
          "style": {...},
          "text": "█",            // ← redacted
          "runs": []                // ← redacted
        }
      ]
    }
  ],
  "variables": {
    "names": ["recipient", "score"],
    "definitions": {...},
    "values": {
      "recipient": "█",            // ← redacted
      "score": 0
    }
  }
}
```

The `█` character (U+2588 FULL BLOCK) signals "encrypted, real value in `encrypted_payload.bin`".

`encrypted_payload.bin` plaintext (after decryption) contains a mapping:

```json
{
  "objects": {
    "obj_001": {
      "text": "Hello {recipient}",
      "runs": [...]
    },
    "obj_005": {
      "data": "real QR data here"
    }
  },
  "variables": {
    "values": {
      "recipient": "Jan Novák"
    }
  },
  "resources": {
    "img_b9f4e7": "<base64>"   // sensitive resources only
  }
}
```

When loading:
1. The placeholder `█` values from cleartext `document.json` are loaded
2. If decryption succeeds, the sensitive data is merged in, overriding the placeholders
3. If decryption fails or no password supplied, the placeholders remain (redacted view)

This lets the editor preview encrypted templates without a password (showing layout but not content).

### Which fields are sensitive?

Encrypted in partial mode:
- `TextBox.text`
- `TextBox.runs[].text`
- `ImageBox.resource_id` (if it points to a sensitive resource)
- `QRCode.data`
- `Table.cells[].text`
- `Table.cells[].runs[].text`
- `VariableStore.values` (all of them)

NOT encrypted in partial mode:
- Any structural data: positions, sizes, fonts, colors, alignment, layer, etc.
- Variable definitions (names and types) — only values are sensitive
- Page dimensions, DPI, color space
- Document title (left visible by design choice)

---

## Recovery key slot

The recovery key is stored as a special slot with `permission: "_recovery"`. It's wrapped with a key derived from the recovery key string (after stripping dashes and uppercasing).

When loading with a recovery key:
1. Strip dashes, uppercase
2. Derive slot key using PBKDF2 with the `_recovery` slot's salt
3. Decrypt the wrapped content key
4. If successful, grant ADMIN permission

The `permission: "_recovery"` slot is hidden from `doc.password_levels`. From the user's perspective, recovery is a separate concept.

---

## Cryptographic details

| Component | Specification |
|---|---|
| Symmetric cipher | AES-256-GCM |
| Key size | 256 bits |
| Nonce | 96 bits, random per ciphertext |
| Auth tag | 128 bits |
| KDF | PBKDF2-HMAC-SHA256 |
| Iterations | 600,000 (current default; future versions may increase) |
| Salt | 128 bits per slot |
| Random source | `secrets.token_bytes()` (CSPRNG) |
| Recovery key | 24 chars from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (~120 bits entropy) |

Future format versions may change `iterations` (the manifest field is honored, so old documents continue to work even after parameter changes).

---

## Compatibility matrix

| Reader version | Plain v4 | Encrypted v4 | v3 | v2 |
|---|---|---|---|---|
| 4.2.x | ✅ | ✅ | ✅ (auto-upgrade) | ✅ (auto-migrate) |
| 4.0.1 | ✅ | ✅ | ✅ (auto-upgrade) | ✅ (auto-migrate) |
| 4.0.0 | ✅ | ❌ (encryption added in 4.0.1) | ✅ | ✅ |
| 3.x | ⚠️ (newer-version warning, fields dropped) | ❌ | ✅ | ✅ |
| 2.x | ❌ | ❌ | ❌ | ✅ |

When a v3 reader opens a v4 file:
- `manifest.json` is read; `edof_version` is `"4.0.x"` which v3 doesn't recognize
- A `EdofNewerVersionWarning` is logged
- The reader proceeds best-effort, dropping unknown fields

For maximum compatibility with legacy environments, use `doc.export_3x()` to write a v3-compatible file.

---

## Inspecting an encrypted file

You can read the **manifest** of any encrypted document without a password:

```python
from edof.format.serializer import EdofSerializer

manifest = EdofSerializer.peek("secret.edof")
print(manifest)
# {
#   "edof_version": "4.2.0",
#   "pages": 5,
#   "title": "Confidential" (or "<encrypted>" for full mode),
#   "protection": {
#     "mode": "full",
#     "iterations": 600000,
#     "slots": [
#       {"permission": "admin",  ...},
#       {"permission": "fill", ...},
#       ...
#     ]
#   },
#   ...
# }
```

This is enough to:
- Know if a file is encrypted
- See which permission levels have passwords
- Verify KDF parameters
- Detect tampering (mismatched manifest)

It's NOT enough to:
- Read any document content
- Decrypt anything
- Identify the document's owner (no PII in manifest by design)

---

## Manual inspection example

```bash
# Peek at the structure of a plain .edof
unzip -l template.edof

# Read the manifest
unzip -p template.edof manifest.json | python3 -m json.tool

# For plain documents, read the document
unzip -p template.edof document.json | python3 -m json.tool | less

# Extract a resource
unzip -p template.edof resources/img_a8d2c1 > extracted.png
```

For encrypted documents, only the manifest is readable this way.
