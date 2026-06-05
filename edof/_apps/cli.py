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

try:
    import edof
except ImportError:
    print("ERROR: edof library not found. Install with:  pip install edof")
    sys.exit(1)


# ── Colour helpers ────────────────────────────────────────────────────────────

# v4.0.2: try to set UTF-8 on stdout/stderr so emoji-style markers render on
# Windows consoles (cp1250 / cp852). If reconfigure fails or yields a stream
# that still can't encode our markers, fall back to ASCII so the CLI never
# crashes on encoding alone.
def _setup_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is None: continue
            enc = (stream.encoding or "").lower()
            if enc not in ("utf-8", "utf8"):
                # Available since Python 3.7
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass

_setup_console_encoding()

def _can_emit(s: str) -> bool:
    try:
        s.encode(sys.stdout.encoding or "ascii", errors="strict")
        return True
    except (UnicodeEncodeError, LookupError, AttributeError):
        return False

if _can_emit("✓"):
    _MARK_OK, _MARK_ERR, _MARK_WARN = "✓", "✗", "⚠"
    _ARROW, _DASH = "→", "—"
else:
    _MARK_OK, _MARK_ERR, _MARK_WARN = "[OK]", "[X]", "[!]"
    _ARROW, _DASH = "->", "--"

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

def ok(msg):    print(_c(f"{_MARK_OK} ",   GREEN)  + msg)
def err(msg):   print(_c(f"{_MARK_ERR} ",  RED)    + msg, file=sys.stderr)
def warn(msg):  print(_c(f"{_MARK_WARN} ", YELLOW) + msg)
def info(msg):  print(_c("  ", DIM)   + msg)
def head(msg):  print(_c(msg, BOLD))


# ═══════════════════════════════════════════════════════════════════════════════
#  Commands
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_info(args):
    """Show template metadata and variables."""
    # v4.0.2: try peek-only mode first for encrypted files (works without password)
    pwd = getattr(args, 'password', None)
    rk = getattr(args, 'recovery_key', None)
    if pwd is None and rk is None:
        # Quick check — is this encrypted?
        try:
            from edof.format.serializer import EdofSerializer
            mf = EdofSerializer.peek(args.template)
            if mf.get("protection", {}).get("mode") in ("partial", "full"):
                head(f"\nTemplate: {os.path.abspath(args.template)}")
                print(f"  Title:       {mf.get('title') or '—'}")
                print(f"  Pages:       {mf.get('pages', '?')}")
                print(f"  Format:      edof {mf.get('edof_version', '?')}")
                prot = mf["protection"]
                slots = prot.get("slots", [])
                levels = sorted({s.get("permission") for s in slots if s.get("permission") and not s.get("permission", "").startswith("_")})
                print(f"  Encrypted:   yes ({prot.get('mode')})")
                print(f"  Levels:      {', '.join(levels) if levels else '(none)'}")
                print(f"  KDF:         {prot.get('kdf')} × {prot.get('iterations')}")
                print()
                info("Use --password or --recovery-key for full details.")
                return
        except Exception:
            pass

    doc = _load(args.template, password=pwd, recovery_key=rk)

    head(f"\nTemplate: {os.path.abspath(args.template)}")
    print(f"  Title:       {doc.title or '—'}")
    print(f"  Author:      {doc.author or '—'}")
    print(f"  Description: {doc.description or '—'}")
    print(f"  Pages:       {len(doc.pages)}")
    print(f"  Format:      edof {edof.FORMAT_VERSION_STR}")
    print(f"  Resources:   {len(doc.resources)} embedded file(s)")
    if doc.is_encrypted:
        print(f"  Encrypted:   yes ({doc.encryption_mode}, level={doc.permission_level.name.lower()})")
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
    doc = _load(args.template,
                password=getattr(args, 'password', None),
                recovery_key=getattr(args, 'recovery_key', None))
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
    doc = _load(args.template,
                password=getattr(args, 'password', None),
                recovery_key=getattr(args, 'recovery_key', None))
    issues = doc.validate()
    if issues:
        err(f"Validation failed – {len(issues)} issue(s):")
        for i in issues:
            print(f"  • {i}")
        sys.exit(4)   # v4.0.2: exit code 4 = validation error (per docs)
    else:
        ok(f"Template is valid: {args.template}")
    missing = doc.variables.missing_required()
    if missing:
        warn(f"Required variables not set: {missing}")


def cmd_export(args):
    """Fill variables and export."""
    # v4.0.2: support password / recovery key
    doc = _load(args.template,
                password=getattr(args, 'password', None),
                recovery_key=getattr(args, 'recovery_key', None))

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
    # v4.0.2: support --vector / --raster for PDF
    vector_pdf = getattr(args, 'vector', True)

    if fmt == 'pdf':
        _export_pdf(doc, out_path, dpi, vector=vector_pdf)
    elif fmt == 'svg':
        _export_svg(doc, out_path, pages[0])
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
        ok(f"Exported page {page_idx} {_ARROW} {path}  ({dpi} dpi, {fmt.upper()})")
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
            ok(f"  Page {idx} {_ARROW} {path}")
            results.append(path)
        except Exception as e:
            err(f"  Page {idx} failed: {e}")
    print(f"\nExported {len(results)}/{len(pages)} page(s).")


def _export_pdf(doc, path, dpi, vector=True):
    try:
        # v4.0.2: vector vs raster
        doc.export_pdf(path, vector=vector)
        kind = "vector" if vector else "raster"
        ok(f"Exported PDF ({kind}) {_ARROW} {path}")
    except ImportError:
        err("PDF export requires reportlab:  pip install edof[pdf]")
        sys.exit(1)
    except Exception as e:
        err(f"PDF export failed: {e}")
        sys.exit(1)


def _export_svg(doc, path, page_idx):
    """v4.0.2: SVG export."""
    try:
        doc.export_svg(path, page=page_idx)
        ok(f"Exported page {page_idx} {_ARROW} {path}  (SVG)")
    except Exception as e:
        err(f"SVG export failed: {e}")
        sys.exit(1)


# ── v4.0.2: New subcommands ───────────────────────────────────────────────────

def cmd_batch(args):
    """Batch generate per-row exports from a CSV file."""
    import csv
    pwd = getattr(args, 'password', None)
    rk = getattr(args, 'recovery_key', None)
    doc = _load(args.template, password=pwd, recovery_key=rk)

    # Determine output format from extension
    ext = os.path.splitext(args.output)[1].lower().lstrip('.')
    if ext not in ('png', 'jpg', 'jpeg', 'tiff', 'bmp', 'pdf', 'svg'):
        err(f"Unsupported output format: {ext!r}")
        sys.exit(1)
    fmt = ext

    if not os.path.isfile(args.csv):
        err(f"CSV file not found: {args.csv}")
        sys.exit(2)

    success = 0
    failed = []
    skipped = 0

    with open(args.csv, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for n, row in enumerate(reader, start=1):
            if args.start and n <= args.start:
                continue
            if args.limit and (n - (args.start or 0)) > args.limit:
                break
            try:
                # Set only variables that exist in the template
                for k, v in row.items():
                    if k in doc.variables.names():
                        doc.set_variable(k, v)
                # Substitute filename pattern
                try:
                    out_path = args.output.format(n=n, **row)
                except KeyError as ke:
                    err(f"Row {n}: filename pattern references missing column: {ke}")
                    if not args.continue_on_error:
                        sys.exit(1)
                    failed.append((n, str(ke)))
                    continue
                # Validate
                missing = doc.variables.missing_required()
                if missing:
                    if not args.continue_on_error:
                        err(f"Row {n}: required variables missing: {missing}")
                        sys.exit(4)
                    failed.append((n, f"missing required: {missing}"))
                    skipped += 1
                    continue
                # Export
                os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
                if fmt == 'pdf':
                    doc.export_pdf(out_path, vector=getattr(args, 'vector', True))
                elif fmt == 'svg':
                    doc.export_svg(out_path, page=0)
                else:
                    doc.export_bitmap(out_path, page=0, dpi=args.dpi or 300,
                                      format=fmt.upper())
                success += 1
                if n % 25 == 0:
                    info(f"  ... processed {n} rows")
            except Exception as e:
                failed.append((n, str(e)))
                if not args.continue_on_error:
                    err(f"Row {n} failed: {e}")
                    sys.exit(5)

    print()
    ok(f"Generated {success} file(s).")
    if skipped:
        warn(f"{skipped} row(s) skipped (validation).")
    if failed:
        warn(f"{len(failed)} row(s) failed:")
        for n, msg in failed[:10]:
            print(f"  row {n}: {msg}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")


def cmd_import(args):
    """Convert a PDF to an editable .edof file."""
    if not os.path.isfile(args.pdf):
        err(f"File not found: {args.pdf}")
        sys.exit(2)
    try:
        head(f"\nImporting {args.pdf}...")
        doc = edof.import_pdf(args.pdf,
                              detect_tables=not args.no_tables,
                              extract_images=not args.no_images,
                              extract_paths=not args.no_paths,
                              heading_threshold=args.heading_threshold)
    except ImportError as e:
        err(f"PDF import requires extras:  pip install edof[pdf]  ({e})")
        sys.exit(1)
    except Exception as e:
        err(f"Import failed: {e}")
        sys.exit(5)

    n_objects = sum(len(p.objects) for p in doc.pages)
    info(f"  {len(doc.pages)} page(s), {n_objects} object(s)")
    if doc.errors:
        for e in doc.errors[:5]:
            warn(f"  {e}")
        if len(doc.errors) > 5:
            info(f"  ... and {len(doc.errors) - 5} more warnings")

    try:
        doc.save(args.output)
        ok(f"Saved: {args.output}")
    except Exception as e:
        err(f"Save failed: {e}")
        sys.exit(5)


def cmd_convert(args):
    """Migrate a legacy .edof archive to v4 format."""
    pwd = getattr(args, 'password', None)
    rk = getattr(args, 'recovery_key', None)
    doc = _load(args.input, password=pwd, recovery_key=rk)
    if doc.errors:
        for e in doc.errors:
            info(f"  {e}")
    try:
        doc.save(args.output)
        ok(f"Converted: {args.input} {_ARROW} {args.output}  (edof {edof.FORMAT_VERSION_STR})")
    except Exception as e:
        err(f"Save failed: {e}")
        sys.exit(5)


def cmd_to_v3(args):
    """Save an EDOF 4 document as a v3-compatible archive (lossy)."""
    pwd = getattr(args, 'password', None)
    rk = getattr(args, 'recovery_key', None)
    doc = _load(args.input, password=pwd, recovery_key=rk)
    try:
        doc.export_3x(args.output)
        ok(f"Downgraded: {args.input} {_ARROW} {args.output}  (v3 format, lossy)")
        warn("Note: tables flattened, rich text collapsed, paths sampled,")
        warn("      gradients averaged, visible_if baked into .visible.")
    except Exception as e:
        err(f"Downgrade failed: {e}")
        sys.exit(5)


def cmd_set_password(args):
    """Manage encryption passwords on an .edof file."""
    pwd = getattr(args, 'current_password', None)
    rk = getattr(args, 'recovery_key', None)
    doc = _load(args.input, password=pwd, recovery_key=rk)

    output = args.output or args.input

    if args.clear_all:
        try:
            doc.clear_all_protection()
            ok("All protection cleared. Document is now plain.")
        except PermissionError as e:
            err(f"Permission denied: {e}")
            sys.exit(3)
    elif args.remove:
        if not args.level:
            err("--remove requires --level")
            sys.exit(1)
        try:
            doc.remove_password(args.level)
            ok(f"Removed password for level: {args.level}")
        except (PermissionError, KeyError, ValueError) as e:
            err(f"Cannot remove password: {e}")
            sys.exit(3)
    else:
        if not args.level or not args.password:
            err("--level and --password are both required (or --remove / --clear-all)")
            sys.exit(1)
        try:
            from edof.crypto import EdofCryptoUnavailable
        except ImportError:
            err("Encryption requires:  pip install edof[crypto]")
            sys.exit(3)
        try:
            recovery = doc.set_password(args.level, args.password)
            ok(f"Set password for level: {args.level}")
            if recovery:
                print()
                head(f"{_MARK_WARN} RECOVERY KEY {_DASH} save this NOW:")
                print(f"  {_c(recovery, GREEN)}")
                print()
                info("This is shown only once. Without it AND your passwords,")
                info("the document is unrecoverable.")
                # Make sure it's consumed (so it isn't saved twice)
                doc.consume_recovery_key()
        except PermissionError as e:
            err(f"Permission denied: {e}")
            sys.exit(3)
        except Exception as e:
            err(f"Cannot set password: {e}")
            sys.exit(5)

    try:
        doc.save(output)
        ok(f"Saved: {output}")
    except Exception as e:
        err(f"Save failed: {e}")
        sys.exit(5)


def cmd_unlock_render(args):
    """Decrypt + render in one step (decrypted file is never written to disk)."""
    pwd = getattr(args, 'password', None)
    rk = getattr(args, 'recovery_key', None)
    doc = _load(args.input, password=pwd, recovery_key=rk)

    out_path = args.output
    ext = os.path.splitext(out_path)[1].lower().lstrip('.')

    try:
        if ext == 'pdf':
            doc.export_pdf(out_path, vector=getattr(args, 'vector', True))
            ok(f"Rendered {_ARROW} {out_path}")
        elif ext == 'svg':
            doc.export_svg(out_path, page=getattr(args, 'page', 0))
            ok(f"Rendered {_ARROW} {out_path}")
        elif ext in ('png', 'jpg', 'jpeg', 'tiff', 'bmp'):
            doc.export_bitmap(out_path, page=getattr(args, 'page', 0),
                              dpi=getattr(args, 'dpi', 300) or 300,
                              format=ext.upper())
            ok(f"Rendered {_ARROW} {out_path}")
        else:
            err(f"Unsupported output format: {ext!r}")
            sys.exit(1)
    except Exception as e:
        err(f"Render failed: {e}")
        sys.exit(5)




def _load(path: str, password: str = None, recovery_key: str = None) -> edof.Document:
    if not os.path.isfile(path):
        err(f"File not found: {path}")
        sys.exit(1)
    try:
        import warnings
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            doc = edof.load(path, password=password, recovery_key=recovery_key)
        for w in ws:
            warn(str(w.message))
        return doc
    except edof.EdofVersionError as e:
        err(f"Incompatible format: {e}")
        sys.exit(1)
    except Exception as e:
        # v4.0.2: distinguish password issues for clearer exit
        try:
            from edof.crypto import EdofPasswordRequired, EdofWrongPassword, EdofCryptoUnavailable
            if isinstance(e, EdofPasswordRequired):
                err("This document is encrypted. Use --password or --recovery-key.")
                sys.exit(3)
            if isinstance(e, EdofWrongPassword):
                err("Wrong password or recovery key.")
                sys.exit(3)
            if isinstance(e, EdofCryptoUnavailable):
                err("Encrypted document — install with: pip install edof[crypto]")
                sys.exit(3)
        except ImportError:
            pass
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
    # Helper: standard --password / --recovery-key on commands that load files
    def add_unlock_args(p, prefix=''):
        p.add_argument(f"--{prefix}password", default=None,
                       help="Password for encrypted files")
        p.add_argument(f"--{prefix}recovery-key", default=None,
                       dest=f"{prefix.replace('-','_')}recovery_key" if prefix else "recovery_key",
                       help="Recovery key for encrypted files")

    pi = sub.add_parser("info", help="Show template metadata and variables")
    pi.add_argument("template", help=".edof file")
    add_unlock_args(pi)

    # ── objects ───────────────────────────────────────────────────────────────
    po = sub.add_parser("objects", help="List all objects in the template")
    po.add_argument("template", help=".edof file")
    add_unlock_args(po)

    # ── validate ──────────────────────────────────────────────────────────────
    pv = sub.add_parser("validate", help="Validate a template file")
    pv.add_argument("template", help=".edof file")
    add_unlock_args(pv)

    # ── export ────────────────────────────────────────────────────────────────
    pe = sub.add_parser("export", help="Fill variables and export to PNG/JPEG/TIFF/PDF/SVG")
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
                    choices=["png","jpg","jpeg","tiff","bmp","pdf","svg"],
                    default=None,
                    help="Output format (auto-detected from extension if omitted)")
    pe.add_argument("--dpi", "-d",
                    type=int, default=300, metavar="DPI",
                    help="Resolution in DPI (default: 300)")
    pe.add_argument("--color-space", "-c",
                    choices=["RGB","RGBA","L","1","CMYK"],
                    default=None, dest="color_space",
                    help="Color space override (default: page setting)")
    # v4.0.2: vector/raster PDF + password
    pe.add_argument("--vector", dest="vector", action="store_true", default=True,
                    help="(PDF) Use vector writer (default; pure Python, smaller files)")
    pe.add_argument("--raster", dest="vector", action="store_false",
                    help="(PDF) Use raster writer via reportlab (supports custom TTF fonts)")
    add_unlock_args(pe)

    # ── v4.0.2: batch ────────────────────────────────────────────────────────
    pb = sub.add_parser("batch",
        help="Generate one output per CSV row (auto-fill variables)")
    pb.add_argument("template", help=".edof template file")
    pb.add_argument("csv",      help="CSV file with header row matching variable names")
    pb.add_argument("-o", "--output", required=True,
                    help='Output path pattern (use {n}, {column}, e.g. "out/{customer_id}.pdf")')
    pb.add_argument("--dpi", "-d", type=int, default=300, metavar="DPI",
                    help="Resolution in DPI (for bitmap outputs)")
    pb.add_argument("--vector", dest="vector", action="store_true", default=True,
                    help="(PDF) Vector writer (default)")
    pb.add_argument("--raster", dest="vector", action="store_false",
                    help="(PDF) Raster writer")
    pb.add_argument("--start", type=int, default=0, metavar="N",
                    help="Skip first N rows")
    pb.add_argument("--limit", type=int, default=None, metavar="N",
                    help="Process at most N rows")
    pb.add_argument("--continue-on-error", action="store_true",
                    help="Continue processing if a row fails")
    add_unlock_args(pb)

    # ── v4.0.2: import ───────────────────────────────────────────────────────
    pim = sub.add_parser("import", help="Convert a PDF file to an editable .edof")
    pim.add_argument("pdf", help="Input PDF file")
    pim.add_argument("-o", "--output", required=True, help="Output .edof path")
    pim.add_argument("--no-tables", action="store_true",
                     help="Skip table detection (faster)")
    pim.add_argument("--no-images", action="store_true",
                     help="Skip image extraction")
    pim.add_argument("--no-paths", action="store_true",
                     help="Skip vector path extraction")
    pim.add_argument("--heading-threshold", type=float, default=1.4,
                     dest="heading_threshold",
                     help="Heading detection multiplier (default: 1.4)")

    # ── v4.0.2: convert (legacy → v4) ────────────────────────────────────────
    pc = sub.add_parser("convert",
        help="Migrate legacy EDOF 2/3 archive to current v4 format")
    pc.add_argument("input",  help="Source .edof (any version)")
    pc.add_argument("-o", "--output", required=True,
                    help="Output .edof path (will be v4)")
    add_unlock_args(pc)

    # ── v4.0.2: to-v3 (downgrade) ────────────────────────────────────────────
    pd = sub.add_parser("to-v3",
        help="Save an EDOF 4 document as v3-compatible (lossy)")
    pd.add_argument("input",  help="Source v4 .edof")
    pd.add_argument("-o", "--output", required=True, help="Output v3 .edof path")
    add_unlock_args(pd)

    # ── v4.0.2: set-password ─────────────────────────────────────────────────
    psp = sub.add_parser("set-password",
        help="Add, change, or remove encryption passwords")
    psp.add_argument("input", help=".edof file")
    psp.add_argument("-o", "--output", default=None,
                     help="Output path (default: overwrite input)")
    psp.add_argument("--level",
                     choices=["fill", "edit", "design", "admin"],
                     help="Permission level for the password")
    psp.add_argument("--password", default=None,
                     help="New password to set for --level")
    psp.add_argument("--current-password", default=None,
                     dest="current_password",
                     help="Current password (required if doc already encrypted)")
    psp.add_argument("--recovery-key", default=None,
                     dest="recovery_key",
                     help="Recovery key (alternative to --current-password)")
    psp.add_argument("--remove", action="store_true",
                     help="Remove the password for --level (admin required)")
    psp.add_argument("--clear-all", action="store_true",
                     help="Remove all encryption (admin required)")

    # ── v4.0.2: unlock-render ────────────────────────────────────────────────
    pur = sub.add_parser("unlock-render",
        help="Render an encrypted file in one step (no decrypted file is written)")
    pur.add_argument("input",  help="Encrypted .edof file")
    pur.add_argument("output", help="Output path (.pdf, .png, .svg, etc.)")
    pur.add_argument("--page", type=int, default=0, metavar="N",
                     help="Page index for SVG/bitmap (default: 0)")
    pur.add_argument("--dpi", type=int, default=300, metavar="DPI",
                     help="DPI for bitmap output (default: 300)")
    pur.add_argument("--vector", dest="vector", action="store_true", default=True,
                     help="(PDF) Vector writer (default)")
    pur.add_argument("--raster", dest="vector", action="store_false",
                     help="(PDF) Raster writer")
    add_unlock_args(pur)

    # ── v4.1.1: file association ─────────────────────────────────────────────
    pa = sub.add_parser("associate-files",
        help="Register .edof files with edof-viewer (so double-click opens viewer)")
    pa.add_argument("--remove", action="store_true",
                     help="Remove the .edof file association instead of adding it")
    pa.add_argument("--status", action="store_true",
                     help="Show current association status and exit")
    pa.add_argument("--app", choices=["viewer", "editor"], default="viewer",
                     help="Which app opens .edof on double-click (default: viewer)")

    return p


def cmd_associate_files(args):
    """v4.1.1: Register or unregister the .edof file association."""
    from edof._apps.file_assoc import (
        associate_edof_files, unassociate_edof_files, current_association_status,
    )
    if args.status:
        print(current_association_status())
        return
    if args.remove:
        try:
            unassociate_edof_files()
            print("OK: .edof file association removed.")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    else:
        try:
            ok, info = associate_edof_files(default_app=getattr(args, "app", "viewer"))
            print(("OK: " if ok else "WARN: ") + info)
            print("  On Windows, you may need to log out and back in for icons to refresh.")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)


def main():
    parser = build_parser()
    args   = parser.parse_args()

    cmd_map = {
        "info":          cmd_info,
        "objects":       cmd_objects,
        "validate":      cmd_validate,
        "export":        cmd_export,
        # v4.0.2:
        "batch":         cmd_batch,
        "import":        cmd_import,
        "convert":       cmd_convert,
        "to-v3":         cmd_to_v3,
        "set-password":  cmd_set_password,
        "unlock-render": cmd_unlock_render,
        # v4.1.1
        "associate-files": cmd_associate_files,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
