#!/usr/bin/env python3
"""
edof-cli  –  Command-line tool for EDOF template filling and export
====================================================================
Usage examples:

  # List variables in a template
  python edof_cli.py info template.edof

  # Export with variables set
  python edof_cli.py export template.edof output.png --set name="Jan Novák" --set date="2025-01-01"

  # Export all pages
  python edof_cli.py export template.edof page_{page}.png --all-pages --dpi 300

  # Export to PDF
  python edof_cli.py export template.edof output.pdf --format pdf

  # Validate template
  python edof_cli.py validate template.edof

  # List objects in template
  python edof_cli.py objects template.edof
"""

import sys, os, argparse, json

# Make sure edof is importable from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import edof
except ImportError:
    print("ERROR: edof library not found. Install with:  pip install edof")
    sys.exit(1)


# ── Colour helpers ────────────────────────────────────────────────────────────

BOLD  = "\033[1m"
DIM   = "\033[2m"
GREEN = "\033[32m"
CYAN  = "\033[36m"
YELLOW= "\033[33m"
RED   = "\033[31m"
RESET = "\033[0m"

def _c(text, code):
    if sys.stdout.isatty():
        return f"{code}{text}{RESET}"
    return text

def ok(msg):    print(_c("✓ ", GREEN) + msg)
def err(msg):   print(_c("✗ ", RED)   + msg, file=sys.stderr)
def warn(msg):  print(_c("⚠ ", YELLOW) + msg)
def info(msg):  print(_c("  ", DIM)   + msg)
def head(msg):  print(_c(msg, BOLD))


# ═══════════════════════════════════════════════════════════════════════════════
#  Commands
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_info(args):
    """Show template metadata and variables."""
    doc = _load(args.template)

    head(f"\nTemplate: {os.path.abspath(args.template)}")
    print(f"  Title:       {doc.title or '—'}")
    print(f"  Author:      {doc.author or '—'}")
    print(f"  Description: {doc.description or '—'}")
    print(f"  Pages:       {len(doc.pages)}")
    print(f"  Format:      edof {edof.FORMAT_VERSION_STR}")
    print(f"  Resources:   {len(doc.resources)} embedded file(s)")
    if doc.errors:
        for e in doc.errors: warn(e)

    # Pages summary
    print()
    head("Pages:")
    for i, page in enumerate(doc.pages):
        print(f"  [{i}]  {page.width:.0f}×{page.height:.0f} mm  "
              f"{page.dpi} dpi  {page.color_space}/{page.bit_depth}bit  "
              f"({len(page.objects)} objects)")

    # Variables
    names = doc.variables.names()
    print()
    if not names:
        head("Variables:  (none)")
    else:
        head(f"Variables ({len(names)}):")
        max_name = max(len(n) for n in names)
        for name in names:
            vdef  = doc.variables.get_def(name)
            val   = doc.variables.get(name)
            req   = _c(" [required]", RED) if vdef.required else ""
            desc  = f"  # {vdef.description}" if vdef.description else ""
            ch    = f"  choices: {vdef.choices}" if vdef.choices else ""
            print(f"  {_c(name.ljust(max_name), CYAN)}"
                  f"  type={vdef.type:<8}"
                  f"  default={str(val)!r:<20}{req}{desc}{ch}")

    # Editable objects
    editable = []
    for page in doc.pages:
        for obj in page.objects:
            if getattr(obj, 'editable', True) and obj.variable:
                editable.append((obj, page.index))
    if editable:
        print()
        head(f"Editable template fields ({len(editable)}):")
        for obj, pg_idx in editable:
            print(f"  page {pg_idx}  {_c(obj.OBJECT_TYPE, CYAN):<12}"
                  f"  variable={_c(obj.variable, YELLOW)}"
                  f"  name={obj.name or '—'}")


def cmd_objects(args):
    """List all objects in the template."""
    doc = _load(args.template)
    print()
    head(f"Objects in: {os.path.basename(args.template)}")
    for pg_idx, page in enumerate(doc.pages):
        head(f"\n  Page {pg_idx} ({page.width:.0f}×{page.height:.0f} mm):")
        if not page.objects:
            info("    (empty)")
            continue
        for obj in page.sorted_objects():
            lock = " 🔒" if obj.locked else ""
            vis  = "" if obj.visible else " [hidden]"
            var  = f"  var={_c(obj.variable, YELLOW)}" if obj.variable else ""
            name = f"  name={obj.name!r}" if obj.name else ""
            tags = f"  tags={obj.tags}" if obj.tags else ""
            print(f"    [{obj.layer:2d}] {_c(obj.OBJECT_TYPE, CYAN):<12}"
                  f"  id={obj.id[:12]}…{name}{var}{tags}{lock}{vis}")


def cmd_validate(args):
    """Validate a template file."""
    doc = _load(args.template)
    issues = doc.validate()
    if issues:
        err(f"Validation failed – {len(issues)} issue(s):")
        for i in issues:
            print(f"  • {i}")
        sys.exit(1)
    else:
        ok(f"Template is valid: {args.template}")
    missing = doc.variables.missing_required()
    if missing:
        warn(f"Required variables not set: {missing}")


def cmd_export(args):
    """Fill variables and export."""
    doc = _load(args.template)

    # ── Apply --set key=value pairs ───────────────────────────────────────────
    for kv in (args.set or []):
        if '=' not in kv:
            err(f"Invalid --set value (expected key=value): {kv!r}")
            sys.exit(1)
        key, _, val = kv.partition('=')
        key = key.strip(); val = val.strip()
        try:
            doc.set_variable(key, val)
            info(f"Set variable  {_c(key, CYAN)} = {val!r}")
        except Exception as e:
            err(f"Cannot set variable {key!r}: {e}")
            sys.exit(1)

    # ── Apply --json-vars ─────────────────────────────────────────────────────
    if args.json_vars:
        try:
            mapping = json.loads(args.json_vars)
            doc.fill_variables(mapping)
            info(f"Applied JSON vars: {list(mapping.keys())}")
        except Exception as e:
            err(f"Invalid --json-vars JSON: {e}")
            sys.exit(1)

    # ── Check required variables ───────────────────────────────────────────────
    missing = doc.variables.missing_required()
    if missing:
        err(f"Required variables not set: {missing}")
        err("Use --set name=value to supply them.")
        sys.exit(1)

    # ── Determine output format ────────────────────────────────────────────────
    out_path  = args.output
    ext       = os.path.splitext(out_path)[1].lower()
    fmt       = (args.format or ext.lstrip('.') or 'png').lower()

    # ── Pages to export ────────────────────────────────────────────────────────
    if args.page is not None:
        pages = [args.page]
    elif args.all_pages or fmt == 'pdf':
        pages = list(range(len(doc.pages)))
    else:
        pages = [0]

    dpi   = args.dpi or 300
    cs    = args.color_space  # may be None → use page default

    # ── Export ─────────────────────────────────────────────────────────────────
    if fmt == 'pdf':
        _export_pdf(doc, out_path, dpi)
    elif args.all_pages and len(pages) > 1:
        _export_all(doc, out_path, pages, dpi, fmt, cs)
    else:
        _export_bitmap(doc, out_path, pages[0], dpi, fmt, cs)


# ── Export helpers ─────────────────────────────────────────────────────────────

def _export_bitmap(doc, path, page_idx, dpi, fmt, color_space):
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            doc.export_bitmap(path, page=page_idx, dpi=dpi,
                              format=fmt.upper(),
                              color_space=color_space or None)
        ok(f"Exported page {page_idx} → {path}  ({dpi} dpi, {fmt.upper()})")
    except Exception as e:
        err(f"Export failed: {e}")
        sys.exit(1)


def _export_all(doc, pattern, pages, dpi, fmt, color_space):
    from edof.export.bitmap import export_page_bitmap
    import warnings
    results = []
    for idx in pages:
        # Substitute {page} and {n} in filename pattern
        path = pattern.format(page=idx+1, n=idx,
                               name=doc.title or "page")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                doc.export_bitmap(path, page=idx, dpi=dpi,
                                  format=fmt.upper(),
                                  color_space=color_space or None)
            ok(f"  Page {idx} → {path}")
            results.append(path)
        except Exception as e:
            err(f"  Page {idx} failed: {e}")
    print(f"\nExported {len(results)}/{len(pages)} page(s).")


def _export_pdf(doc, path, dpi):
    try:
        doc.export_pdf(path)
        ok(f"Exported PDF → {path}")
    except ImportError:
        err("PDF export requires reportlab:  pip install edof[pdf]")
        sys.exit(1)
    except Exception as e:
        err(f"PDF export failed: {e}")
        sys.exit(1)


# ── Load helper ────────────────────────────────────────────────────────────────

def _load(path: str) -> edof.Document:
    if not os.path.isfile(path):
        err(f"File not found: {path}")
        sys.exit(1)
    try:
        import warnings
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            doc = edof.load(path)
        for w in ws:
            warn(str(w.message))
        return doc
    except edof.EdofVersionError as e:
        err(f"Incompatible format: {e}")
        sys.exit(1)
    except Exception as e:
        err(f"Cannot open {path!r}: {e}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  Argument parser
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser():
    p = argparse.ArgumentParser(
        prog="edof-cli",
        description="EDOF template CLI – fill variables and export documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python edof_cli.py info          template.edof
  python edof_cli.py objects       template.edof
  python edof_cli.py validate      template.edof

  python edof_cli.py export template.edof output.png
  python edof_cli.py export template.edof output.png --set name="Jan" --set date="2025-01-01"
  python edof_cli.py export template.edof output.png --dpi 300 --color-space L
  python edof_cli.py export template.edof page_{page}.png --all-pages
  python edof_cli.py export template.edof output.pdf --format pdf

  python edof_cli.py export template.edof out.png \\
      --json-vars '{"name":"Jan","city":"Praha"}'
""")

    sub = p.add_subparsers(dest="command", required=True)

    # ── info ──────────────────────────────────────────────────────────────────
    pi = sub.add_parser("info", help="Show template metadata and variables")
    pi.add_argument("template", help=".edof file")

    # ── objects ───────────────────────────────────────────────────────────────
    po = sub.add_parser("objects", help="List all objects in the template")
    po.add_argument("template", help=".edof file")

    # ── validate ──────────────────────────────────────────────────────────────
    pv = sub.add_parser("validate", help="Validate a template file")
    pv.add_argument("template", help=".edof file")

    # ── export ────────────────────────────────────────────────────────────────
    pe = sub.add_parser("export", help="Fill variables and export to PNG/JPEG/TIFF/PDF")
    pe.add_argument("template",  help=".edof template file")
    pe.add_argument("output",    help="Output path (use {page} or {n} for multi-page)")
    pe.add_argument("--set", "-s",
                    metavar="KEY=VALUE", action="append", default=[],
                    help="Set a variable (repeatable):  --set name=Jan --set date=2025")
    pe.add_argument("--json-vars", "-j",
                    metavar="JSON", default=None,
                    help='Set multiple variables as JSON: \'{"name":"Jan","city":"Praha"}\'')
    pe.add_argument("--page", "-p",
                    type=int, default=None, metavar="N",
                    help="Page index to export (0-based, default: 0)")
    pe.add_argument("--all-pages", "-A",
                    action="store_true",
                    help="Export all pages (use {page} in output filename)")
    pe.add_argument("--format", "-f",
                    choices=["png","jpg","jpeg","tiff","bmp","pdf"],
                    default=None,
                    help="Output format (auto-detected from extension if omitted)")
    pe.add_argument("--dpi", "-d",
                    type=int, default=300, metavar="DPI",
                    help="Resolution in DPI (default: 300)")
    pe.add_argument("--color-space", "-c",
                    choices=["RGB","RGBA","L","1","CMYK"],
                    default=None, dest="color_space",
                    help="Color space override (default: page setting)")

    return p


def main():
    parser = build_parser()
    args   = parser.parse_args()

    cmd_map = {
        "info":     cmd_info,
        "objects":  cmd_objects,
        "validate": cmd_validate,
        "export":   cmd_export,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
