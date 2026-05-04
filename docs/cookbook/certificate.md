# Cookbook: Generate certificates from CSV

End-to-end recipe: build a certificate template, fill it from a CSV file, and produce one PDF per recipient.

## Step 1: Build the template

```python
import edof
from edof import TextRun

doc = edof.new(width=297, height=210, title="Certificate")   # A4 landscape
page = doc.add_page(dpi=300)

# Heavy decorative border
border = page.add_shape("rect", 10, 10, 277, 190)
border.fill.color   = None
border.stroke.color = (50, 50, 100, 255)
border.stroke.width = 2.0

# Inner thin border for elegance
inner = page.add_shape("rect", 14, 14, 269, 182)
inner.fill.color   = None
inner.stroke.color = (50, 50, 100, 255)
inner.stroke.width = 0.3

# Heading
hdr = page.add_textbox(20, 30, 257, 25, "CERTIFICATE OF ACHIEVEMENT")
hdr.style.font_family = "Helvetica"
hdr.style.font_size   = 32
hdr.style.bold        = True
hdr.style.color       = (50, 50, 100)
hdr.style.alignment   = "center"

# Subtitle
sub = page.add_textbox(20, 65, 257, 12, "is hereby presented to")
sub.style.font_size = 14
sub.style.italic    = True
sub.style.color     = (120, 120, 120)
sub.style.alignment = "center"

# Recipient name (the variable)
name = page.add_textbox(20, 85, 257, 30, "{recipient}")
name.style.font_size = 36
name.style.bold      = True
name.style.alignment = "center"
name.style.color     = (40, 40, 40)

# Description
desc = page.add_textbox(20, 130, 257, 20,
    "for outstanding achievement in {course} during {term}.")
desc.style.font_size = 14
desc.style.alignment = "center"
desc.style.wrap      = True

# Date and signature lines
page.add_textbox(40, 165, 80, 8, "{date}").style.alignment = "center"
page.add_textbox(40, 173, 80, 8, "Date").style.font_size = 9

page.add_textbox(177, 165, 80, 8, "Director").style.alignment = "center"
page.add_textbox(177, 173, 80, 8, "Signature").style.font_size = 9

# Variables
doc.define_variable("recipient", required=True, label="Recipient name")
doc.define_variable("course",    default="the program")
doc.define_variable("term",      default="2026")
doc.define_variable("date",      type="date", required=True)

doc.save("certificate_template.edof")
print("Template saved.")
```

## Step 2: Prepare the CSV

`recipients.csv`:

```csv
recipient,course,term,date
Jan Novák,Advanced Python,Spring 2026,2026-05-15
Anna Dvořáková,Data Engineering,Spring 2026,2026-05-15
Petr Svoboda,Machine Learning,Spring 2026,2026-05-15
Marie Procházková,Web Development,Spring 2026,2026-05-15
```

## Step 3: Generate certificates

### Option A: Using the CLI

```bash
edof-cli batch certificate_template.edof recipients.csv \
  -o "certs/{recipient}.pdf"
```

This generates:
```
certs/Jan Novák.pdf
certs/Anna Dvořáková.pdf
certs/Petr Svoboda.pdf
certs/Marie Procházková.pdf
```

### Option B: From Python

```python
import csv
import os
import edof

doc = edof.load("certificate_template.edof")
os.makedirs("certs", exist_ok=True)

with open("recipients.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        doc.fill_variables(row)
        # Validate before exporting
        issues = doc.validate()
        if issues:
            print(f"SKIP {row['recipient']}: {issues}")
            continue

        # Build a safe filename
        safe_name = row['recipient'].replace(" ", "_").replace("/", "_")
        out_path = f"certs/{safe_name}.pdf"
        doc.export_pdf(out_path)
        print(f"Generated: {out_path}")
```

The Python version gives you more control over filename sanitization, error handling, progress reporting, and any custom logic between rows.

## Step 4: Output

You'll have a directory full of personalized PDF certificates. Each is small (~5-10 KB in vector mode), with selectable text.

## Variations

### Multiple courses per certificate

If a recipient has multiple courses, you might want one certificate listing all of them. Use rich text:

```python
doc.define_variable("courses_text")  # pre-formatted

# Build the courses string in your code
courses = ["Advanced Python", "Data Engineering", "Machine Learning"]
courses_text = ", ".join(courses[:-1]) + f", and {courses[-1]}"
# → "Advanced Python, Data Engineering, and Machine Learning"

doc.set_variable("courses_text", courses_text)
```

### Accent color per recipient

Add an "accent_color" variable as a hex string, then use it programmatically:

```python
doc.define_variable("accent")
doc.set_variable("accent", "#3050A0")

# In your generation code:
def hex_to_rgb(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))

accent = hex_to_rgb(doc.variables.get("accent"))
border.stroke.color = (*accent, 255)
hdr.style.color = accent
```

### Logos per recipient

Use an image variable:

```python
doc.define_variable("school_logo", type="image")

logo = page.add_image(default_logo_id, x=15, y=15, w=30, h=30)
logo.variable = "school_logo"
```

In CSV:

```csv
recipient,school_logo,date
Jan Novák,logos/charles_uni.png,2026-05-15
Anna Dvořáková,logos/cvut.png,2026-05-15
```

When `school_logo` is set to a path, edof loads that file as a fresh resource for that render.

### Combining all into a single multipage PDF

```python
import edof
import csv

template = edof.load("certificate_template.edof")
combined = edof.new(width=297, height=210, title="All Certificates")
combined.pages.clear()

with open("recipients.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        # Render this template into a temporary doc
        template.fill_variables(row)
        # ...trick: render to image then re-add as a new page in combined
        # (The straightforward way is to export individual PDFs and merge with pypdf.)
```

For a real multi-page PDF combining many filled templates, the cleaner approach is to export each as PDF and merge them with `pypdf`:

```python
from pypdf import PdfWriter

merger = PdfWriter()
for path in pdf_paths:
    merger.append(path)
merger.write("all_certs.pdf")
```

`pypdf` is not a dependency of edof — install separately if you need this.
