# edof/batch/generate.py
"""v4.4.0: batch export engine (UI-independent).

One entry point, export_batch(), renders every batch row to files:

  * scope   "page" (one chosen page) or "all" (every page)
  * fmt     "png" | "jpg" | "svg" | "pdf" | "edof"
            - png/jpg/svg + all pages -> one file per page ([PAGE] token,
              auto-appended as _p[PAGE] when the pattern lacks it)
            - pdf + page  -> single-page PDF;  pdf + all -> multipage PDF
            - edof + page -> single-page document; edof + all -> whole doc
  * output  "per_row" (one file per row, tag-based filenames) or "single"
            (pdf/edof only: ONE multipage file, every row's page(s) appended
            in row order; the pattern is used once, as a plain filename).
            The single edof bakes the rows in: the combined document is
            converted to fixed pages (no document body, no batch config), so
            reopening it never re-paginates the rows away.
  * progress optional callable progress(done, total) -> bool, called before
            each row and once at the end; return False to cancel. On cancel
            the files written so far stay and errors gets a "Cancelled"
            entry.
  * sources (edof only)
            "integrate": external file-path images are materialised into the
              resource store (apply does this since BUG #10) and the fonts the
              document uses are embedded, so ONE self-contained file.
            "external":  referenced external files stay files: they are copied
              into a sources/ folder next to the .edof, objects point at the
              RELATIVE path, and the pair is zipped (<name>.zip) -- the bundle
              stays editable with the sources as plain files.

Filenames come from render_filename() token templates ([ROW_NUMBER],
[ROW_NAME], [PAGE], [{Header}], ...).
"""
from __future__ import annotations

import copy as _copy
import os
import zipfile

from edof.batch.model import apply_row_to_document, render_filename


def _uniq(name: str, used: set) -> str:
    base, dot, ext = name.rpartition(".")
    cand = name
    k = 2
    while cand.lower() in used:
        cand = "%s_%d.%s" % (base, k, ext) if dot else "%s_%d" % (name, k)
        k += 1
    used.add(cand.lower())
    return cand


def _trim_to_page(doc, page_idx: int) -> None:
    """Keep only the chosen page (clamped)."""
    if not doc.pages:
        return
    pi = max(0, min(int(page_idx), len(doc.pages) - 1))
    doc.pages[:] = [doc.pages[pi]]


def _externalise_sources(doc, out_dir: str, bundle_name: str):
    """v4.4.0 'external' mode: move file-backed resources OUT of the document
    into <out_dir>/sources/, point objects at the relative path and return
    the list of written files. Resources that never came from a file (no
    filename) stay embedded."""
    written = []
    src_dir = os.path.join(out_dir, "sources")
    res = getattr(doc, "resources", None)
    if res is None:
        return written
    # resource_id -> relative path for every file-backed resource in use
    used_ids = set()

    def _collect(o):
        rid = getattr(o, "resource_id", None)
        if rid and rid in res:
            used_ids.add(rid)
        for ch in (getattr(o, "children", None) or []):
            _collect(ch)

    for pg in (doc.pages or []):
        for o in (getattr(pg, "objects", None) or []):
            _collect(o)
    body = getattr(doc, "body", None)
    if body is not None:
        for attr in ("header_objects", "footer_objects"):
            for o in (getattr(body, attr, None) or []):
                _collect(o)
    if not used_ids:
        return written
    os.makedirs(src_dir, exist_ok=True)
    mapping = {}
    used_names = set()
    for rid in sorted(used_ids):
        entry = res.get(rid)
        if entry is None or not (entry.filename or "").strip():
            continue                      # not file-backed: keep embedded
        fname = _uniq(os.path.basename(entry.filename), used_names)
        fpath = os.path.join(src_dir, fname)
        with open(fpath, "wb") as fh:
            fh.write(entry.data)
        written.append(fpath)
        mapping[rid] = os.path.join("sources", fname)
    if not mapping:
        return written

    def _repoint(o):
        rid = getattr(o, "resource_id", None)
        if rid in mapping:
            o.resource_id = mapping[rid]
        for ch in (getattr(o, "children", None) or []):
            _repoint(ch)

    for pg in (doc.pages or []):
        for o in (getattr(pg, "objects", None) or []):
            _repoint(o)
    if body is not None:
        for attr in ("header_objects", "footer_objects"):
            for o in (getattr(body, attr, None) or []):
                _repoint(o)
    for rid in mapping:
        try:
            res.remove(rid)
        except Exception:
            try: res._store.pop(rid, None)
            except Exception: pass
    return written


def _row_doc(doc, row, scope: str, page_idx: int):
    """Deepcopy of doc with the row applied, trimmed to one page for the
    "page" scope."""
    dcopy = _copy.deepcopy(doc)
    apply_row_to_document(dcopy.batch, dcopy, row)
    if scope == "page":
        _trim_to_page(dcopy, page_idx)
    return dcopy


def _build_combined_doc(doc, rows, scope: str, page_idx: int,
                        progress=None):
    """v4.4.0 "single" output: ONE document whose pages are every row's
    page(s) in row order. Returns (combined_doc_or_None, errors, cancelled).

    The result is baked: body (document mode flow) and batch config are
    dropped, because the rows' values only make sense as fixed pages -- a
    reopened document-mode body would re-paginate from ONE row's text and
    the other rows' pages would be wrong or gone.
    """
    from edof.format.objects import _new_id
    combined = None
    errors = []
    total = len(rows)
    for i, row in enumerate(rows, 1):
        if progress is not None and not progress(i - 1, total):
            return combined, errors, True
        try:
            dcopy = _row_doc(doc, row, scope, page_idx)
            if combined is None:
                combined = dcopy
            else:
                for pg in dcopy.pages:
                    pg.id = _new_id()
                    combined.pages.append(pg)
                res = getattr(dcopy, "resources", None)
                cres = getattr(combined, "resources", None)
                if res is not None and cres is not None:
                    for entry in res.all_entries():
                        if entry.resource_id not in cres:
                            cres._store[entry.resource_id] = entry
        except Exception as e:
            errors.append("Row %d: %s" % (i, e))
    if combined is not None:
        combined.body = None       # bake: fixed pages, no re-pagination
        combined._batch = None     # values are baked in, no live batch
        for k, pg in enumerate(combined.pages):
            pg.index = k
    return combined, errors, False


def export_batch(doc, cfg, rows, out_dir: str, pattern: str, fmt: str,
                 scope: str = "page", page_idx: int = 0,
                 sources: str = "integrate", dpi: int = 300,
                 output: str = "per_row", progress=None,
                 image_format=None, image_quality: int = 80):
    """Render every row. Returns (ok_count, [written paths], [errors])."""
    fmt = (fmt or "png").lower()
    scope = "all" if scope == "all" else "page"

    def _shrink(d):
        # v4.4.0: optional image recompression (png lossless / jpeg quality)
        # for the pdf and edof outputs
        if image_format:
            try:
                d.recompress_images(image_format, image_quality)
            except Exception:
                pass
    written = []
    errors = []
    used = set()
    ok = 0
    total = len(rows)
    if output == "single":
        if fmt not in ("pdf", "edof"):
            raise ValueError("single-file output needs pdf or edof, not %r"
                             % fmt)
        combined, errors, cancelled = _build_combined_doc(
            doc, rows, scope, page_idx, progress=progress)
        ok = total - len(errors)
        if cancelled:
            errors.append("Cancelled after %d row(s)" % ok)
            return ok, written, errors
        if combined is None or not combined.pages:
            errors.append("Nothing to export")
            return 0, written, errors
        if fmt == "edof":
            _shrink(combined)
        name = render_filename(pattern, 1, rows[0], cfg, default_ext=fmt)
        try:
            if fmt == "pdf":
                path = os.path.join(out_dir, name)
                combined.export_pdf(path, image_format=image_format,
                                    image_quality=image_quality)
                written.append(path)
            elif sources == "external":
                stem = name[:-5] if name.lower().endswith(".edof") else name
                bdir = os.path.join(out_dir, stem)
                os.makedirs(bdir, exist_ok=True)
                files = _externalise_sources(combined, bdir, stem)
                epath = os.path.join(bdir, stem + ".edof")
                combined.save(epath)
                zpath = os.path.join(out_dir, stem + ".zip")
                with zipfile.ZipFile(zpath, "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    zf.write(epath, arcname=stem + ".edof")
                    for f in files:
                        zf.write(f, arcname=os.path.join(
                            "sources", os.path.basename(f)))
                written.append(zpath)
            else:
                try:
                    combined.embed_used_fonts()
                except Exception:
                    pass
                path = os.path.join(out_dir, name)
                combined.save(path)
                written.append(path)
        except Exception as e:
            errors.append("Write failed: %s" % e)
            return 0, written, errors
        if progress is not None:
            progress(total, total)
        return ok, written, errors
    per_page_files = fmt in ("png", "jpg", "svg") and scope == "all"
    if per_page_files and "[page" not in (pattern or "").lower():
        base, dot, ext = (pattern or "[ROW_NUMBER:04]").rpartition(".")
        pattern = ((base if dot else pattern) + "_p[PAGE]"
                   + (dot + ext if dot else ""))

    for i, row in enumerate(rows, 1):
        if progress is not None and not progress(i - 1, total):
            errors.append("Cancelled after %d row(s)" % ok)
            return ok, written, errors
        try:
            dcopy = _copy.deepcopy(doc)
            apply_row_to_document(dcopy.batch, dcopy, row)
            n_pages = len(dcopy.pages)
            if fmt in ("png", "jpg", "svg"):
                pages = (range(n_pages) if scope == "all"
                         else [max(0, min(page_idx, n_pages - 1))])
                for pi in pages:
                    name = _uniq(render_filename(
                        pattern, i, row, cfg, default_ext=fmt,
                        page_number=pi + 1), used)
                    path = os.path.join(out_dir, name)
                    if fmt == "svg":
                        dcopy.export_svg(path, page=pi)
                    else:
                        dcopy.export_bitmap(path, page=pi, dpi=dpi,
                                            format=fmt.upper())
                    written.append(path)
            elif fmt == "pdf":
                if scope == "page":
                    _trim_to_page(dcopy, page_idx)
                name = _uniq(render_filename(pattern, i, row, cfg,
                                             default_ext="pdf"), used)
                path = os.path.join(out_dir, name)
                dcopy.export_pdf(path, image_format=image_format,
                                 image_quality=image_quality)
                written.append(path)
            elif fmt == "edof":
                if scope == "page":
                    _trim_to_page(dcopy, page_idx)
                name = _uniq(render_filename(pattern, i, row, cfg,
                                             default_ext="edof"), used)
                _shrink(dcopy)
                if sources == "external":
                    # bundle: <name>/ folder with the .edof + sources/, zipped
                    stem = name[:-5] if name.lower().endswith(".edof") else name
                    bdir = os.path.join(out_dir, stem)
                    os.makedirs(bdir, exist_ok=True)
                    files = _externalise_sources(dcopy, bdir, stem)
                    epath = os.path.join(bdir, stem + ".edof")
                    dcopy.save(epath)
                    zpath = os.path.join(out_dir, stem + ".zip")
                    with zipfile.ZipFile(zpath, "w",
                                         zipfile.ZIP_DEFLATED) as zf:
                        zf.write(epath, arcname=stem + ".edof")
                        for f in files:
                            zf.write(f, arcname=os.path.join(
                                "sources", os.path.basename(f)))
                    written.append(zpath)
                else:
                    # integrate: one self-contained file (images are already
                    # materialised by apply; fonts embedded here)
                    try:
                        dcopy.embed_used_fonts()
                    except Exception:
                        pass
                    path = os.path.join(out_dir, name)
                    dcopy.save(path)
                    written.append(path)
            else:
                raise ValueError("unknown format %r" % fmt)
            ok += 1
        except Exception as e:
            errors.append("Row %d: %s" % (i, e))
    if progress is not None:
        progress(total, total)
    return ok, written, errors
