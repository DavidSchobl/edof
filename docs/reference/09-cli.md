# Reference: CLI

`edof-cli` is the command-line tool for working with `.edof` files without writing Python. Installed automatically when you `pip install edof`.

## Global options

```
edof-cli --version         # show version
edof-cli --help            # show all subcommands
edof-cli <subcommand> --help  # detailed help for a subcommand
```

---

## Subcommands

### `info` — show document metadata

```bash
edof-cli info template.edof
```

Output:
```
Title:    Certificate
Author:   Jan Novák
Pages:    1
Format:   4.0.1
Variables: recipient (text, required), score (number, default=0)
Encrypted: no
```

For encrypted files without a password, only the manifest-level info is shown:
```
Encrypted: yes (full)
Cannot read further details without a password.
Use --password or --recovery-key.
```

With password:
```bash
edof-cli info secret.edof --password "myPass"
```

### `objects` — list all objects

```bash
edof-cli objects template.edof
```

Output:
```
Page 1 (210x297mm @ 300dpi):
  TextBox  id=ab12cd34  pos=(15.0, 15.0)  size=180x12  text="FAKTURA"
  TextBox  id=ef56gh78  pos=(15.0, 30.0)  size=180x8   text="#{invoice_number}"
  Table    id=ij90kl12  pos=(15.0, 80.0)  size=180x60  rows=4 cols=4
  ...
```

Useful for inspecting templates and finding object IDs.

### `validate` — check document integrity

```bash
edof-cli validate template.edof
```

Returns exit code 0 if valid, non-zero with issue list if not.

```
✓ Document is valid.
```

or:

```
✗ Document has issues:
  - Required variable "recipient" has no value
  - Object 'ab12cd' references resource 'foo' which doesn't exist
  - Object 'ef56gh' is positioned entirely off-page
Exit: 1
```

### `export` — render document to a file

```bash
edof-cli export template.edof output.png
edof-cli export template.edof output.pdf
edof-cli export template.edof output.svg
```

Format is auto-detected from the output extension:
- `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp` → bitmap export
- `.pdf` → PDF (vector by default)
- `.svg` → SVG

Options:
- `--page N` — export specific page (0-based; default: 0)
- `--all-pages` — export all pages (use `{n}` in path: `out_{n}.png`)
- `--dpi N` — for bitmap exports (default: 300)
- `--vector / --raster` — for PDF (default: --vector)
- `--password "..."` — for encrypted files
- `--recovery-key "..."` — alternative to password
- `--set name=value` — fill variables before export (repeatable)

Examples:

```bash
# Export specific page
edof-cli export template.edof page2.png --page 1

# All pages with placeholder
edof-cli export template.edof "out_{n}.png" --all-pages

# Fill variables and export
edof-cli export cert.edof output.pdf \
  --set recipient="Jan Novák" \
  --set score=98

# Raster PDF (bigger file, but supports custom fonts)
edof-cli export template.edof output.pdf --raster

# Lower DPI for screen viewing
edof-cli export template.edof preview.png --dpi 96

# From an encrypted file
edof-cli export secret.edof output.pdf --password "myPass"
```

### `batch` — fill from CSV, export per row

Bulk template generation. Reads a CSV file, treats each row as a set of variable values, and exports one file per row.

```bash
edof-cli batch template.edof data.csv -o "out_{n}.png"
edof-cli batch template.edof data.csv -o "out_{name}.pdf"
```

Required:
- Template `.edof` file
- CSV file with header row matching variable names

Options:
- `-o PATH` / `--output PATH` — output path pattern. Use `{n}` for row number (1-based), or `{column}` for any CSV column value.
- `--password "..."` — for encrypted templates
- `--dpi N` — for bitmap output
- `--vector / --raster` — for PDF output
- `--start N` — skip first N rows (default: 0, no skip)
- `--limit N` — process at most N rows
- `--continue-on-error` — don't stop on per-row errors

Example:

`data.csv`:
```csv
name,score,date
Alice,98,2026-05-04
Bob,87,2026-05-04
Carol,92,2026-05-04
```

```bash
edof-cli batch certificate.edof data.csv -o "certs/{name}.pdf"
```

Produces:
```
certs/Alice.pdf
certs/Bob.pdf
certs/Carol.pdf
```

If a column doesn't match a defined variable, the column is ignored. If a `required` variable isn't in the CSV, the row produces an error.

### `import` — convert PDF to EDOF

```bash
edof-cli import input.pdf -o output.edof
```

Options:
- `-o PATH` — output `.edof` path (required)
- `--no-tables` — skip table detection (faster)
- `--no-images` — skip image extraction
- `--no-paths` — skip vector path extraction
- `--heading-threshold N` — heading detection multiplier (default: 1.4)

Requires `pip install edof[pdf]`.

```bash
edof-cli import old_template.pdf -o template.edof --no-paths
edof-cli info template.edof   # verify the import
```

### `convert` — migrate legacy formats

Convert an EDOF 2 archive to EDOF 4. Auto-detects the source format.

```bash
edof-cli convert legacy_v2.edof -o new.edof
```

Options:
- `-o PATH` — output (required)

This is equivalent to `edof.load(path)` followed by `doc.save(out)`. The migration is one-way; the output cannot be saved back as v2.

### `to-v3` — downgrade to EDOF 3 format

Save an EDOF 4 document as a v3-compatible archive (lossy).

```bash
edof-cli to-v3 v4_doc.edof -o v3_compatible.edof
```

What's flattened:
- Tables → groups of TextBoxes + line shapes
- Rich text runs → plain text
- Path shapes → polygon shapes
- Gradients → average color
- `visible_if` → evaluated and baked into `.visible`
- `blend_mode` → reset to "normal"

Useful when you need to share a v4 document with someone running an older library version.

### `set-password` — manage encryption from CLI

Add or change a password without opening the editor.

```bash
edof-cli set-password template.edof --level admin --password "newPass"
```

Options:
- `--level LEVEL` — `fill`, `edit`, `design`, or `admin`
- `--password "..."` — new password
- `--current-password "..."` — current password (required if doc already encrypted)

For the **first** password on a document, a recovery key is printed:
```
Recovery key (save this!): 7K3F-9XQM-2N8P-VR4A-HT6L-Z5BJ
Document re-saved as encrypted.
```

To **remove** a password:
```bash
edof-cli set-password template.edof --level fill --remove --current-password "admin_pwd"
```

Removing requires admin permission (i.e. supplying an admin password via `--current-password`).

To **clear all protection**:
```bash
edof-cli set-password template.edof --clear-all --current-password "admin_pwd"
```

### `unlock-render` — render encrypted file in one step

Combine unlock + render. Convenience for scripts.

```bash
edof-cli unlock-render secret.edof output.pdf --password "myPass"
edof-cli unlock-render secret.edof output.png --recovery-key "7K3F-9XQM-..."
```

Same options as `export`, plus `--password` and `--recovery-key`. The decrypted document is **never written back** to disk — just rendered.

---

## Exit codes

- `0` — success
- `1` — usage error (bad arguments)
- `2` — file not found
- `3` — encryption error (wrong password, missing crypto extra)
- `4` — validation error (`validate` finds issues)
- `5` — unknown internal error (with traceback if `--verbose`)

Useful for shell scripts:

```bash
if edof-cli validate template.edof; then
    echo "OK"
    edof-cli batch template.edof data.csv -o "out/{n}.pdf"
fi
```

---

## Examples

### Generate certificates from CSV

```bash
edof-cli batch certificate.edof recipients.csv -o "certs/{name}.pdf"
```

### Verify all `.edof` files in a directory

```bash
for f in *.edof; do
    edof-cli validate "$f" || echo "FAIL: $f"
done
```

### Inspect a file you don't trust

```bash
edof-cli info untrusted.edof    # safe — reads only manifest
edof-cli objects untrusted.edof # safe — lists structure
```

(Don't `export` an untrusted file unless you trust the rendering — though edof's renderer doesn't execute code from documents.)

### Re-encrypt with a new password

```bash
edof-cli set-password old.edof --clear-all --current-password "oldPass"
edof-cli set-password old.edof --level admin --password "newPass"
```

### Bulk PDF generation with progress reporting

```bash
edof-cli batch invoice.edof customers.csv \
  -o "invoices/{customer_id}.pdf" \
  --continue-on-error \
  2>&1 | tee batch.log
```
