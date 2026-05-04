# Cookbook: Batch generate PDFs from data

Generate hundreds or thousands of personalized PDFs from a single template and a data source (CSV, JSON, database). Two approaches: CLI for simple cases, Python for full control.

## Approach 1: CLI (simplest)

If your data is in a CSV file and your variable names match column headers, the CLI handles everything:

```bash
edof-cli batch template.edof data.csv -o "out/{n}.pdf"
```

Options:
- `-o "out/{n}.pdf"` — `{n}` is row number (1-based)
- `-o "out/{customer_id}.pdf"` — any column name in `{}` is substituted
- `--start N` — skip first N rows
- `--limit N` — process at most N rows
- `--continue-on-error` — don't stop on per-row failures

Example:

`customers.csv`:
```csv
customer_id,name,email,balance
C001,Alice,alice@example.com,1500
C002,Bob,bob@example.com,2300
C003,Carol,carol@example.com,890
```

```bash
edof-cli batch monthly_statement.edof customers.csv \
  -o "statements/{customer_id}.pdf" \
  --continue-on-error
```

Generates `statements/C001.pdf`, `statements/C002.pdf`, `statements/C003.pdf`.

## Approach 2: Python (more control)

For larger jobs, custom logic, or non-CSV data sources:

```python
import edof
import csv
import os
from pathlib import Path

def batch_generate(template_path, data_iter, out_dir, name_func, fmt="pdf"):
    """
    template_path: path to .edof template
    data_iter:     iterable of dicts (each dict = one document)
    out_dir:       output directory
    name_func:     function(record) → output filename (without extension)
    fmt:           "pdf" | "png" | "svg"
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    doc = edof.load(template_path)

    success = 0
    failed = []

    for i, record in enumerate(data_iter, start=1):
        try:
            doc.fill_variables(record)
            issues = doc.validate()
            if issues:
                failed.append((i, record, "validation", issues))
                continue

            filename = name_func(record)
            out_path = Path(out_dir) / f"{filename}.{fmt}"

            if fmt == "pdf":
                doc.export_pdf(str(out_path))
            elif fmt == "png":
                doc.export_bitmap(str(out_path), dpi=300)
            elif fmt == "svg":
                doc.export_svg(str(out_path))

            success += 1
            if i % 100 == 0:
                print(f"  Generated {i} files...")

        except Exception as e:
            failed.append((i, record, "exception", str(e)))

    print(f"\nDone: {success} success, {len(failed)} failed")
    return success, failed
```

### Usage with CSV

```python
with open("customers.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    success, failed = batch_generate(
        template_path="statement_template.edof",
        data_iter=reader,
        out_dir="output/statements",
        name_func=lambda r: r["customer_id"],
        fmt="pdf",
    )

if failed:
    with open("output/failed.log", "w") as f:
        for i, record, kind, err in failed:
            f.write(f"Row {i} ({kind}): {err}\n")
```

### Usage with JSON

```python
import json

with open("customers.json", encoding="utf-8") as f:
    customers = json.load(f)

batch_generate(
    template_path="statement_template.edof",
    data_iter=customers,
    out_dir="output",
    name_func=lambda r: f"{r['id']}_{r['name'].replace(' ', '_')}",
)
```

### Usage with a database

```python
import sqlite3

conn = sqlite3.connect("customers.db")
conn.row_factory = sqlite3.Row   # so rows are dict-like

cursor = conn.execute("""
    SELECT customer_id, name, email, balance, due_date
    FROM customers
    WHERE active = 1
""")

# row_factory makes each row indexable by column name; convert to plain dict for fill_variables
data_iter = (dict(row) for row in cursor)

batch_generate(
    template_path="statement.edof",
    data_iter=data_iter,
    out_dir="output",
    name_func=lambda r: r["customer_id"],
)

conn.close()
```

## Performance tips

### Reuse the loaded document

Loading a template takes time. Load once, fill many times:

```python
# DON'T do this — loads 1000 times
for record in records:
    doc = edof.load("template.edof")    # slow
    doc.fill_variables(record)
    doc.export_pdf(...)

# DO this — loads once
doc = edof.load("template.edof")
for record in records:
    doc.fill_variables(record)
    doc.export_pdf(...)
```

The `fill_variables()` call mutates `doc` in place; subsequent fills overwrite previous values. No need to "reset" between iterations.

### Parallelize if I/O-bound

Use `concurrent.futures.ProcessPoolExecutor` if you have many CPU cores and the export is the bottleneck:

```python
from concurrent.futures import ProcessPoolExecutor

def render_one(record_and_path):
    record, out_path = record_and_path
    doc = edof.load("template.edof")    # each worker loads its own copy
    doc.fill_variables(record)
    doc.export_pdf(out_path)
    return out_path

tasks = [(r, f"out/{r['id']}.pdf") for r in records]

with ProcessPoolExecutor(max_workers=4) as exe:
    for path in exe.map(render_one, tasks):
        print(f"  Done: {path}")
```

Note: each worker process loads its own copy of the template. For very fast inner work, this overhead can outweigh the parallelism — measure first.

### Use bitmap export for previews

PDFs have large fixed overhead. For preview thumbnails, use PNG at low DPI:

```python
doc.export_bitmap("preview.png", dpi=72)   # very fast, screen-readable
```

### Cache resources

If your template uses many images, ensure `add_resource()` is called once during template construction, not per-render. Resources stored in the doc are reused.

If a variable substitutes images at render time (`ib.variable = "logo"`), each unique value loads the file fresh — this is slow if the same logo appears in many records. To cache:

```python
class CachedImageVariable:
    def __init__(self, doc):
        self.doc = doc
        self.cache = {}   # path → resource_id

    def set(self, var_name, image_path):
        if image_path in self.cache:
            self.doc.set_variable(var_name, self.cache[image_path])
        else:
            rid = self.doc.add_resource_from_file(image_path)
            self.cache[image_path] = rid
            self.doc.set_variable(var_name, rid)

helper = CachedImageVariable(doc)
for record in records:
    helper.set("logo", record["logo_path"])
    doc.fill_variables({k: v for k, v in record.items() if k != "logo_path"})
    doc.export_pdf(f"out/{record['id']}.pdf")
```

## Combining outputs into one PDF

If you want all generated PDFs concatenated into a single file (e.g. for printing), use `pypdf`:

```python
from pypdf import PdfWriter

merger = PdfWriter()
for record in records:
    doc.fill_variables(record)
    tmp_path = f"/tmp/temp_{record['id']}.pdf"
    doc.export_pdf(tmp_path)
    merger.append(tmp_path)
    os.remove(tmp_path)

merger.write("all_statements.pdf")
```

`pypdf` is not bundled with edof; install with `pip install pypdf`.

## Logging and progress

For long-running batches:

```python
import logging
logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)

for i, record in enumerate(records, 1):
    if i % 50 == 0:
        logging.info(f"Processing {i}/{total}")
    doc.fill_variables(record)
    doc.export_pdf(f"out/{record['id']}.pdf")

logging.info(f"Done: {len(records)} files")
```

For a progress bar, install `tqdm`:

```python
from tqdm import tqdm

for record in tqdm(records, desc="Generating"):
    doc.fill_variables(record)
    doc.export_pdf(f"out/{record['id']}.pdf")
```

## Error recovery

For robust batch processing, catch errors per-record and continue:

```python
errors = []
for i, record in enumerate(records, 1):
    try:
        doc.fill_variables(record)
        doc.export_pdf(f"out/{record['id']}.pdf")
    except Exception as e:
        errors.append((i, record.get("id"), str(e)))

if errors:
    print(f"\n{len(errors)} errors:")
    for i, rid, err in errors[:10]:    # show first 10
        print(f"  row {i} (id={rid}): {err}")
```

Common per-record failures:
- Required variable missing → validation error
- Image path doesn't exist → resource error
- Filename contains characters invalid for the OS → IOError

Sanitize filenames before use:

```python
import re

def safe_filename(name):
    # Remove/replace characters problematic on Windows/Linux/macOS
    return re.sub(r'[<>:"/\\|?*]', '_', str(name))[:200]

doc.export_pdf(f"out/{safe_filename(record['name'])}.pdf")
```
