# Cookbook: Encrypted templates with multi-level passwords

> Requires `pip install edof[crypto]`

Walkthrough: build a template that template fillers can use without seeing the design, designers can edit the layout, and only an admin can manage passwords or remove protection.

## Scenario

A company uses an invoice template. Three roles:

| Role | Should be able to | Should NOT be able to |
|---|---|---|
| **Sales staff** (template fillers) | Fill in customer name, items, totals; export PDF | Change layout, fonts, colors; see template internals |
| **Designer** | Adjust the visual design, fonts, colors | Manage passwords or remove encryption |
| **Manager / IT admin** | Everything, including password management | (no restrictions) |

## Step 1: Build the template

```python
import edof
from edof import TableCell, Table

doc = edof.new(width=210, height=297, title="Invoice Template")
page = doc.add_page(dpi=300)

# Heading
hdr = page.add_textbox(15, 15, 100, 14, "INVOICE")
hdr.style.font_size = 28
hdr.style.bold = True
hdr.style.color = (50, 80, 160)

# Lock the heading hard — should never change accidentally
hdr.lock_text = True   # text NEVER editable, even by admin

# Invoice number
num = page.add_textbox(115, 15, 80, 7, "#{invoice_number}")
num.style.font_size = 14
num.style.alignment = "right"

# Date
dt = page.add_textbox(115, 23, 80, 6, "Date: {date}")
dt.style.alignment = "right"

# Client info (fillable)
page.add_textbox(15, 50, 90, 6, "Bill To:").style.bold = True
client = page.add_textbox(15, 57, 90, 25, "{client_name}\n{client_address}")
client.style.font_size = 10

# Line items table
t = Table()
t.transform.x = 15
t.transform.y = 90
t.transform.width = 180
t.transform.height = 80
t.col_widths = [80, 25, 30, 45]
t.cells = [
    [TableCell(text="Description"), TableCell(text="Qty"),
     TableCell(text="Unit Price"), TableCell(text="Total")],
    [TableCell(text="{item1_desc}"), TableCell(text="{item1_qty}"),
     TableCell(text="{item1_price}"), TableCell(text="{item1_total}")],
    # ... more rows
]
for c in t.cells[0]:
    c.bg_color = (50, 80, 160, 255)
    c.style.color = (255, 255, 255)
    c.style.bold = True
page.add_object(t)

# The TABLE STRUCTURE (which columns exist, header) should never be changed by fillers
t.lock_level = "design"   # only design or admin can move/resize/restructure

# Total
total = page.add_textbox(110, 180, 85, 8, "TOTAL: {total} CZK")
total.style.font_size = 14
total.style.bold = True
total.style.alignment = "right"

# Footer
foot = page.add_textbox(15, 270, 180, 8,
    "Thank you for your business. Payment due in 14 days.")
foot.style.font_size = 9
foot.style.italic = True
foot.style.alignment = "center"

# Variables — these are what fillers will set
doc.define_variable("invoice_number", required=True, label="Invoice number")
doc.define_variable("date", type="date", required=True)
doc.define_variable("client_name", required=True, label="Client name")
doc.define_variable("client_address", default="", label="Client address")
doc.define_variable("item1_desc", default="-")
doc.define_variable("item1_qty", default="")
doc.define_variable("item1_price", default="")
doc.define_variable("item1_total", default="")
doc.define_variable("total", default="0.00")

# Save plain version first (for testing)
doc.save("invoice_template_plain.edof")
```

## Step 2: Set up encryption

```python
# Set passwords for three levels
recovery_key = doc.set_password("admin",  "admin_$ecret_2026")  # IT/manager
doc.set_password("design", "design3r_p455")                      # designer
doc.set_password("fill",   "salesUser2026")                       # sales staff

# IMPORTANT: save the recovery key NOW
print("RECOVERY KEY (save in password manager!):", recovery_key)

# Use partial mode — fillers can see structure but not template internals
doc.encryption_mode = "partial"

doc.save("invoice_template_encrypted.edof")
print("Encrypted template saved.")
```

After this, anyone opening `invoice_template_encrypted.edof` without a password sees redacted content (`█` placeholders) but the layout and structure are visible.

## Step 3: Sales staff workflow (FILL level)

Sales staff have just the `salesUser2026` password.

```python
import edof

# Open with fill password
doc = edof.load("invoice_template_encrypted.edof", password="salesUser2026")
print(f"Permission level: {doc.permission_level}")   # Permission.FILL

# Fill in customer data — allowed
doc.fill_variables({
    "invoice_number": "2026-0042",
    "date":           "2026-05-04",
    "client_name":    "ACME s.r.o.",
    "client_address": "Customer Street 456\n200 00 Brno",
    "item1_desc":     "Consulting",
    "item1_qty":      "5",
    "item1_price":    "1500",
    "item1_total":    "7500",
    "total":          "7500",
})

# Try to change a textbox text — DENIED
try:
    page = doc.pages[0]
    tb = page.objects[0]   # the heading
    tb.text = "FAKTURA"    # change to Czech
except PermissionError as e:
    print(f"Cannot edit: {e}")

# Export PDF — ALLOWED (fill is enough for export)
doc.export_pdf("invoice_2026-0042.pdf")
print("Invoice exported.")
```

The sales staff can:
- Fill in any variable
- Export to PDF, PNG, SVG
- Print

They cannot:
- Change the design (fonts, colors, sizes, positions)
- Add or remove objects
- Change the heading text (`lock_text=True` — even admin can't without unlocking that flag first)
- Manage passwords

## Step 4: Designer workflow (DESIGN level)

```python
doc = edof.load("invoice_template_encrypted.edof", password="design3r_p455")
print(f"Permission level: {doc.permission_level}")   # Permission.DESIGN

# Designer can change the layout
hdr = doc.pages[0].objects[0]
hdr.style.color = (200, 50, 50)   # change accent color
hdr.style.font_family = "Times New Roman"

# Designer can add new objects
doc.pages[0].add_textbox(15, 30, 100, 6, "Tax ID: 12345678").style.font_size = 9

# Designer CAN'T change the locked heading text, however:
try:
    hdr.text = "RECHNUNG"   # German
except PermissionError as e:
    print(f"Heading is text-locked: {e}")

# Designer CAN'T manage passwords
try:
    doc.set_password("fill", "newSalesPwd")
except PermissionError as e:
    print(f"Password change denied: {e}")

# Save the design changes
doc.save("invoice_template_encrypted.edof")
```

## Step 5: Admin workflow

```python
doc = edof.load("invoice_template_encrypted.edof", password="admin_$ecret_2026")
print(f"Permission level: {doc.permission_level}")   # Permission.ADMIN

# Admin can do everything design can do, PLUS:

# Manage passwords
doc.change_password("fill", "salesUser2026", "newSalesPwd_2026Q3")
print("Sales password rotated.")

# Add a new role
doc.set_password("edit", "editor_password")
print("New 'edit' password added.")

# Remove a level
doc.remove_password("edit")
print("'edit' password removed.")

# Change encryption mode
doc.encryption_mode = "full"   # was "partial"

# Override hard text lock
hdr = doc.pages[0].objects[0]
hdr.lock_text = False   # admin can clear this
hdr.text = "FAKTURA"    # now editable
hdr.lock_text = True    # re-lock

# Or remove all encryption
# doc.clear_all_protection()
# doc.encryption_mode == "none"  # back to plain

doc.save("invoice_template_encrypted.edof")
```

## Recovery scenarios

### Lost admin password

If the admin forgets their password but has the recovery key:

```python
doc = edof.load("invoice_template_encrypted.edof",
                recovery_key="7K3F-9XQM-2N8P-VR4A-HT6L-Z5BJ")
print(doc.permission_level)   # Permission.ADMIN

# Set a new admin password
doc.change_password("admin", None, "new_admin_password")
# Wait — change_password needs the OLD password. Use this instead:

doc.remove_password("admin")
doc.set_password("admin", "new_admin_password")
doc.save("invoice_template_encrypted.edof")
```

### Lost everything (all passwords AND recovery key)

The document is **mathematically unrecoverable**. There is no backdoor. This is a feature — store passwords and recovery key safely.

If you have an unencrypted backup somewhere (good practice for templates), use that. Always keep an unencrypted master copy of templates in a separate secure location.

## CLI shortcuts

The CLI can do most of these operations without writing Python:

```bash
# Add password
edof-cli set-password template.edof --level admin --password "newSecret"

# Remove all encryption (need admin password)
edof-cli set-password template.edof --clear-all --current-password "admin_pwd"

# Render encrypted file in one step
edof-cli unlock-render template.edof out.pdf --password "salesUser2026"
```

## Best practices

**Use partial mode for templates** that team members will fill, full mode for completed documents that go in storage.

**Set strong passwords**, especially admin (≥12 characters with mixed types). PBKDF2 with 600k iterations protects against brute force, but a password like "abc123" is still cracked instantly — the cost increase only matters for non-trivial passwords.

**Save the recovery key in a password manager** with the same security as bank credentials. If you also lose the password manager, no recovery is possible.

**Keep an unencrypted backup of every template in a secure location.** Encryption protects against unauthorized access; backups protect against data loss. They're separate concerns.

**Rotate passwords when team members leave.** `change_password` is fast even on large documents (it doesn't re-encrypt the payload).

**Test the workflow end-to-end** before deploying to users. Make sure the role you're targeting really can do their job and really can't do things you want to prevent.

**For shared environments**, store credentials in a secret manager (HashiCorp Vault, AWS Secrets Manager) rather than in scripts.
