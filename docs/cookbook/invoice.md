# Cookbook: Build an invoice template

Build an invoice with a header, two-column "from/to" block, line-item table, totals, and footer. Then fill it from a Python dictionary or database row.

## Result

The template renders as something like:

```
┌────────────────────────────────────────────────────┐
│ FAKTURA                                #2026-0042  │
│                                       Date: 2026-05-04 │
│                                                    │
│ From:                  To:                         │
│ Vaše firma s.r.o.      ACME Customers              │
│ Street 123             Customer St 456             │
│ 100 00 Praha           200 00 Brno                 │
│                                                    │
│ ┌─────────────┬────┬─────────┬──────────┐         │
│ │ Description │Qty │Unit Price│ Total    │         │
│ ├─────────────┼────┼─────────┼──────────┤         │
│ │ Consulting  │ 5  │ 1500    │ 7500     │         │
│ │ Software    │ 1  │ 25000   │ 25000    │         │
│ │ Support     │12  │ 800     │ 9600     │         │
│ └─────────────┴────┴─────────┴──────────┘         │
│                                                    │
│                                  TOTAL: 42100 CZK  │
│                                                    │
│ Thank you for your business.                       │
└────────────────────────────────────────────────────┘
```

## Step 1: Define the template

```python
import edof
from edof import Table, TableCell

def make_invoice_template():
    doc = edof.new(width=210, height=297, title="Invoice")
    page = doc.add_page(dpi=300)

    # Big heading
    hdr = page.add_textbox(15, 15, 100, 14, "FAKTURA")
    hdr.style.font_size = 28
    hdr.style.bold = True
    hdr.style.color = (50, 80, 160)

    # Invoice number, top-right
    num = page.add_textbox(115, 15, 80, 7, "#{invoice_number}")
    num.style.font_size = 14
    num.style.alignment = "right"

    # Date, below number
    dt = page.add_textbox(115, 23, 80, 6, "Date: {date}")
    dt.style.font_size = 10
    dt.style.alignment = "right"

    # From section
    fr_label = page.add_textbox(15, 40, 90, 6, "From:")
    fr_label.style.bold = True
    fr_label.style.font_size = 10
    fr_addr = page.add_textbox(15, 47, 90, 25,
        "Vaše firma s.r.o.\nStreet 123\n100 00 Praha\nIČO: 12345678\nDIČ: CZ12345678")
    fr_addr.style.font_size = 9

    # To section
    to_label = page.add_textbox(110, 40, 85, 6, "Bill to:")
    to_label.style.bold = True
    to_label.style.font_size = 10
    to_addr = page.add_textbox(110, 47, 85, 25,
        "{client_name}\n{client_address}\nIČO: {client_ico}")
    to_addr.style.font_size = 9

    # Line-items table
    t = Table()
    t.transform.x = 15
    t.transform.y = 85
    t.transform.width  = 180
    t.transform.height = 80
    t.col_widths = [80, 25, 30, 45]
    t.cells = [
        # Header row
        [TableCell(text="Description"), TableCell(text="Qty"),
         TableCell(text="Unit Price"), TableCell(text="Total")],
        # Three line items as templates
        [TableCell(text="{item1_desc}"), TableCell(text="{item1_qty}"),
         TableCell(text="{item1_price}"), TableCell(text="{item1_total}")],
        [TableCell(text="{item2_desc}"), TableCell(text="{item2_qty}"),
         TableCell(text="{item2_price}"), TableCell(text="{item2_total}")],
        [TableCell(text="{item3_desc}"), TableCell(text="{item3_qty}"),
         TableCell(text="{item3_price}"), TableCell(text="{item3_total}")],
    ]
    # Style header row
    for c in t.cells[0]:
        c.bg_color = (50, 80, 160, 255)
        c.style.color = (255, 255, 255)
        c.style.bold = True
        c.style.alignment = "center"
    # Right-align numeric columns
    for row in t.cells[1:]:
        for col_idx in (1, 2, 3):  # Qty, Price, Total
            row[col_idx].style.alignment = "right"

    page.add_object(t)

    # Total
    total = page.add_textbox(110, 175, 85, 8, "TOTAL: {total} CZK")
    total.style.font_size = 14
    total.style.bold = True
    total.style.alignment = "right"

    # Footer
    foot = page.add_textbox(15, 270, 180, 8,
        "Thank you for your business. Payment due in 14 days.")
    foot.style.font_size = 9
    foot.style.italic = True
    foot.style.alignment = "center"
    foot.style.color = (120, 120, 120)

    # Hide line items 2 and 3 if not needed (visible_if)
    # (Actually each item is in a single table cell here; for true conditional rows
    # see "Variations" below.)

    # Variables — tagged so we can update them in bulk
    doc.define_variable("invoice_number", default="2026-0001", label="Invoice number")
    doc.define_variable("date", type="date", required=True)
    doc.define_variable("client_name",    required=True, label="Client name")
    doc.define_variable("client_address", default="", label="Client address")
    doc.define_variable("client_ico",     default="", label="Client IČO")
    for n in (1, 2, 3):
        doc.define_variable(f"item{n}_desc",  default="-")
        doc.define_variable(f"item{n}_qty",   default="")
        doc.define_variable(f"item{n}_price", default="")
        doc.define_variable(f"item{n}_total", default="")
    doc.define_variable("total", default="0")

    return doc

doc = make_invoice_template()
doc.save("invoice_template.edof")
print("Template saved.")
```

## Step 2: Fill from data

```python
import edof
import datetime

def issue_invoice(invoice_data, output_path):
    doc = edof.load("invoice_template.edof")

    # Compute totals
    items = invoice_data["items"][:3]  # template supports up to 3
    total = sum(i["qty"] * i["price"] for i in items)

    values = {
        "invoice_number": invoice_data["number"],
        "date":           invoice_data.get("date") or datetime.date.today().isoformat(),
        "client_name":    invoice_data["client"]["name"],
        "client_address": invoice_data["client"]["address"],
        "client_ico":     invoice_data["client"].get("ico", ""),
        "total":          f"{total:,.2f}",
    }

    # Fill items
    for n, item in enumerate(items, start=1):
        line_total = item["qty"] * item["price"]
        values[f"item{n}_desc"]  = item["desc"]
        values[f"item{n}_qty"]   = str(item["qty"])
        values[f"item{n}_price"] = f"{item['price']:,.2f}"
        values[f"item{n}_total"] = f"{line_total:,.2f}"
    # Empty unused slots
    for n in range(len(items) + 1, 4):
        for k in ("desc", "qty", "price", "total"):
            values[f"item{n}_{k}"] = ""

    doc.fill_variables(values)
    doc.export_pdf(output_path)


# Use it
issue_invoice({
    "number": "2026-0042",
    "client": {
        "name":    "ACME s.r.o.",
        "address": "Customer Street 456\n200 00 Brno",
        "ico":     "87654321",
    },
    "items": [
        {"desc": "Consulting (May 2026)", "qty": 5,  "price": 1500},
        {"desc": "Software License",       "qty": 1, "price": 25000},
        {"desc": "Premium Support",        "qty": 12,"price": 800},
    ],
}, "invoices/2026-0042.pdf")
```

## Variations

### Variable number of line items

The fixed-3-row template above is simple but limited. For arbitrary line counts, use `repeat_objects`:

```python
def make_dynamic_invoice_template():
    doc = edof.new(width=210, height=297, title="Invoice")
    page = doc.add_page(dpi=300)

    # Header (same as before)
    page.add_textbox(15, 15, 100, 14, "FAKTURA").style.font_size = 28

    # Build a "row template" — a one-line set of textboxes
    # We'll repeat this block for each item

    # First, place the header row directly
    hdr_row = []
    hdr_row.append(page.add_textbox(15,  85, 80,  8, "Description"))
    hdr_row.append(page.add_textbox(95,  85, 25,  8, "Qty"))
    hdr_row.append(page.add_textbox(120, 85, 30,  8, "Price"))
    hdr_row.append(page.add_textbox(150, 85, 45,  8, "Total"))
    for tb in hdr_row:
        tb.style.bold = True
        tb.fill = edof.FillStyle(color=(50, 80, 160, 255))
        tb.style.color = (255, 255, 255)

    # Now build a template row (will be repeated)
    desc = page.add_textbox(15,  93, 80, 6, "{desc}")
    qty  = page.add_textbox(95,  93, 25, 6, "{qty}")
    qty.style.alignment = "right"
    price= page.add_textbox(120, 93, 30, 6, "{price}")
    price.style.alignment = "right"
    total= page.add_textbox(150, 93, 45, 6, "{total}")
    total.style.alignment = "right"
    for tb in (desc, qty, price, total):
        tb.style.font_size = 9

    # Remove the template objects from the page (they'll be added back via repeat)
    template_objs = [desc, qty, price, total]
    for o in template_objs:
        page.objects.remove(o)

    # Save without items — they'll be added at fill time
    doc.template_row = template_objs   # stash for later use
    return doc
```

Then at fill time:

```python
doc = make_dynamic_invoice_template()
template_row = doc.template_row

items = [
    {"desc": "Consulting", "qty": 5,  "price": "1,500.00", "total": "7,500.00"},
    {"desc": "Software",   "qty": 1,  "price": "25,000",   "total": "25,000"},
    # ... any number
]

# Repeat: this auto-paginates if items overflow the page
new_pages = doc.pages[0].repeat_objects(template_row, items, gap=1.0)
```

For the totals (which appear after the last row), you need to either:
- Place them at a fixed position relative to the page (might overlap items if many)
- Compute manually based on number of rows

For full dynamism, consider building the document from scratch each time rather than using a template.

### Logo

```python
logo_id = doc.add_resource_from_file("logo.png")
logo = page.add_image(logo_id, x=160, y=15, w=35, h=20)
```

Or as a variable for per-customer branding:

```python
doc.define_variable("logo", type="image")
logo = page.add_image(default_id, 160, 15, 35, 20)
logo.variable = "logo"
```

### QR code with payment link

```python
qr = page.add_qrcode(160, 200, 30, 30, data="")
qr.variable = "payment_qr"
qr.error_correction = "M"

doc.define_variable("payment_qr", type="qr")
doc.set_variable("payment_qr", "SPD*1.0*ACC:CZ123...*AM:42100*CC:CZK")  # SPAYD
```

### Conditional discount line

```python
discount = page.add_textbox(110, 167, 85, 6, "Discount: -{discount} CZK")
discount.style.alignment = "right"
discount.style.color = (200, 50, 50)
discount.visible_if = "discount > 0"

doc.define_variable("discount", type="number", default=0)
```

When `discount` is 0, the line doesn't render.

### Different language

Just translate the static text:

```python
hdr.text = "INVOICE"
fr_label.text = "From:"
to_label.text = "Bill to:"
# etc.
```

For multilingual templates, use variables:

```python
doc.define_variable("lang_invoice",  default="FAKTURA")
doc.define_variable("lang_from",     default="From:")
doc.define_variable("lang_to",       default="Bill to:")

hdr.text = "{lang_invoice}"
fr_label.text = "{lang_from}"
to_label.text = "{lang_to}"

# Then for English:
doc.fill_variables({"lang_invoice": "INVOICE", "lang_from": "From:", "lang_to": "Bill to:"})
```

### Save as encrypted

If invoices contain sensitive data:

```python
recovery = doc.set_password("admin", "company_secret_2026")
doc.save("invoice.edof")
print(f"Save this recovery key: {recovery}")
```

Then loading requires the password. Issue the PDF normally — the PDF itself is not encrypted (encryption is the .edof file format).
