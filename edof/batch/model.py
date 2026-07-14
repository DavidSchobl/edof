"""3D Batch data model + .edof persistence (phase 4.3.2.0).

Backend only. Builds on the attribute registry (`edof.batch` package root) and
adds the batch *configuration* that lives alongside a document: which object
attributes are batched (columns), the rows of values, a separate demo table
for template building/preview, and the generation mode. Nothing here renders or
touches Qt; the UI (4.3.3.0) and exports/import (4.3.5.0) consume this.

Core pieces:

  * ObjectRef  — a STABLE, hierarchical address of an object: a list of ids
                 from the page's top level down through groups (and, later,
                 sub-documents). Resolving a ref walks `.children`, so it
                 reaches objects nested in groups. A flat top-level object is
                 just a one-element path.

  * BatchColumn — one batched attribute: a stable column_id, the ObjectRef +
                 attribute path it targets, an optional human var_name (header
                 label; falls back to the descriptor label), and the value kind
                 (cached from the registry for UI/validation). Columns address
                 attributes via the registry, so every value kind is supported
                 from day one.

  * BatchRow   — one record: an optional page_target (only meaningful in
                 row_scope='page'), and a {column_id: raw_value} map. Empty /
                 missing value means "leave as-is" (registry semantics).

  * BatchConfig — the whole thing: row_scope ('page'|'document'), the column
                 list, the data rows, and the separate demo rows. Serializes to
                 a single 'batch' dict that Document.to_dict embeds and
                 Document.from_dict restores. Old readers ignore the unknown
                 key, so documents stay backward compatible.

Targeting rules (applied by `apply_row_to_document`):
  * A column applies only where its target object resolves AND its attribute
    descriptor exists. A column whose object is gone is dead (the UI drops it;
    here resolution simply returns None and the column is skipped).
  * In row_scope='page', a row fills only the page named by page_target: a
    column whose target object is not on that page is skipped for that row.
  * In row_scope='document', a row fills every page where the target resolves.
  * Conflicts between two columns hitting the same attribute are resolved by
    the registry's priority band (lower wins); this is descriptive of EDOF's
    own precedence, not a new behaviour.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from edof.batch import find_descriptor


# ── object addressing ────────────────────────────────────────────────────────
@dataclass
class ObjectRef:
    """Hierarchical id path: [top_id, child_id, ...]. One element = a
    top-level object; more = nested inside group(s)."""
    path: List[str] = field(default_factory=list)

    def to_list(self) -> List[str]:
        return list(self.path)

    @classmethod
    def from_list(cls, lst) -> "ObjectRef":
        return cls([str(x) for x in (lst or [])])

    def __bool__(self) -> bool:
        return bool(self.path)


def _children_of(obj) -> List[Any]:
    return list(getattr(obj, "children", None) or [])


def resolve_ref(page, ref: ObjectRef):
    """Walk a page's object tree following the id path. Returns the object or
    None if any hop is missing (object deleted / moved)."""
    if not ref or not ref.path:
        return None
    level = list(getattr(page, "objects", []) or [])
    obj = None
    for oid in ref.path:
        obj = next((o for o in level if getattr(o, "id", None) == oid), None)
        if obj is None:
            return None
        level = _children_of(obj)
    return obj


def find_ref_on_pages(pages, ref: ObjectRef) -> Optional[int]:
    """Return the index of the first page on which `ref` resolves, or None."""
    for i, pg in enumerate(pages):
        if resolve_ref(pg, ref) is not None:
            return i
    return None


def build_ref(page, target_obj) -> Optional[ObjectRef]:
    """Find the id path from a page's top level down to target_obj (searching
    into groups). Returns None if the object is not under this page."""
    target_id = getattr(target_obj, "id", None)
    if target_id is None:
        return None

    def _search(level, trail):
        for o in level:
            t2 = trail + [getattr(o, "id", None)]
            if getattr(o, "id", None) == target_id:
                return t2
            kids = _children_of(o)
            if kids:
                hit = _search(kids, t2)
                if hit:
                    return hit
        return None

    trail = _search(list(getattr(page, "objects", []) or []), [])
    return ObjectRef(trail) if trail else None


# ── columns / rows ───────────────────────────────────────────────────────────
def _new_col_id() -> str:
    return "col_" + uuid.uuid4().hex[:12]


@dataclass
class BatchColumn:
    column_id: str
    target: ObjectRef
    attr_path: str
    var_name: str = ""          # human header; empty -> fall back to label
    kind: str = "text"          # cached from registry (text/number/color/enum/file_path)
    # v4.3.5.13: a column may drive MORE than one object with the same attribute
    # (e.g. one variable that sets the same text on two text boxes, or toggles a
    # shadow on two shapes). The primary `target` plus these extra targets all
    # receive the row's value. Empty = single-target (backwards compatible).
    extra_targets: list = field(default_factory=list)
    # v4.3.5.21: for an effect attribute, bind to a SPECIFIC effect instance by
    # its stable id, so reordering effects on the layer doesn't re-point the
    # variable to a different instance. When set, it overrides the positional
    # ordinal in attr_path (effects.<type>#N.<field>). Empty -> positional.
    effect_id: str = ""
    # v4.3.6.0: for a text-run attribute (attr_path 'run.<field>'), bind to the
    # run with this stable rid inside the target TextBox, so editing surrounding
    # text doesn't re-point the variable. Empty -> not a run-targeted column.
    run_id: str = ""
    # v4.4.0: LINKED variables. Additional rids this column's value also fills.
    # Unlike the old fold (which reassigned the other variable's rid and made
    # its entity vanish), a linked variable keeps its own rid, name and panel
    # entry; only the VALUE comes from this column. Unlink = remove from here.
    extra_run_ids: list = field(default_factory=list)

    def all_targets(self):
        """The primary target followed by any extra targets."""
        return [self.target] + list(self.extra_targets or [])

    def to_dict(self) -> dict:
        return {
            "column_id": self.column_id,
            "target": self.target.to_list(),
            "attr_path": self.attr_path,
            "var_name": self.var_name,
            "kind": self.kind,
            "extra_targets": [t.to_list() for t in (self.extra_targets or [])],
            "effect_id": self.effect_id,
            "run_id": self.run_id,
            "extra_run_ids": list(self.extra_run_ids or []),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BatchColumn":
        return cls(
            column_id=d.get("column_id") or _new_col_id(),
            target=ObjectRef.from_list(d.get("target", [])),
            attr_path=d.get("attr_path", ""),
            var_name=d.get("var_name", ""),
            kind=d.get("kind", "text"),
            extra_targets=[ObjectRef.from_list(t)
                           for t in d.get("extra_targets", [])],
            effect_id=d.get("effect_id", ""),
            run_id=d.get("run_id", ""),
            extra_run_ids=list(d.get("extra_run_ids", []) or []),
        )

    def header(self) -> str:
        return self.var_name.strip() if self.var_name.strip() else self.attr_path


@dataclass
class BatchRow:
    page_target: Optional[int] = None     # page index; only used in row_scope='page'
    values: Dict[str, Any] = field(default_factory=dict)   # column_id -> raw value
    name: str = ""                        # optional row name (used in export filenames)
    locked: bool = False                  # when True the row's values can't be edited

    def to_dict(self) -> dict:
        return {"page_target": self.page_target,
                "values": dict(self.values),
                "name": self.name,
                "locked": self.locked}

    @classmethod
    def from_dict(cls, d: dict) -> "BatchRow":
        return cls(
            page_target=d.get("page_target", None),
            values=dict(d.get("values", {})),
            name=d.get("name", ""),
            locked=bool(d.get("locked", False)),
        )


# ── whole config ─────────────────────────────────────────────────────────────
@dataclass
class BatchConfig:
    row_scope: str = "page"               # 'page' | 'document'
    columns: List[BatchColumn] = field(default_factory=list)
    rows: List[BatchRow] = field(default_factory=list)
    demo_rows: List[BatchRow] = field(default_factory=list)
    export_demo: bool = False             # include demo rows in production export

    # -- column management --
    # ── v4.4.0: unique column names ──────────────────────────────────────
    # Two columns must never share a header: the header IS the variable's
    # identity in the UI, in CSV import matching and in the [{Header}]
    # filename tags. Names are auto-generated from the object + attribute
    # ("shape01.fill_color") unless the user supplies one, and every path
    # that stores a name goes through unique_header().

    _TYPE_SHORT = {"TextBox": "text", "ImageBox": "img", "Shape": "shape",
                   "QRCode": "qr", "Table": "table", "Group": "group",
                   "SubDocumentBox": "subdoc", "SvgBox": "svg"}

    def header_in_use(self, name: str, exclude_column_id: str = "") -> bool:
        key = (name or "").strip().lower()
        if not key:
            return False
        return any(c.header().strip().lower() == key
                   for c in self.columns if c.column_id != exclude_column_id)

    def unique_header(self, base: str, exclude_column_id: str = "") -> str:
        """Return base, or base_2 / base_3 ... so it collides with no other
        column's header."""
        base = (base or "").strip() or "col"
        cand = base
        n = 2
        while self.header_in_use(cand, exclude_column_id):
            cand = "%s_%d" % (base, n)
            n += 1
        return cand

    def system_header(self, obj, attr_path: str) -> str:
        """Systematic default name like "shape01.fill_color": short object
        type + per-type counter + the attribute tail. An object's own name
        (Objects panel) wins over the type prefix."""
        import re as _re
        tail = (attr_path or "attr").split(".")[-1] or "attr"
        oname = (getattr(obj, "name", "") or "").strip()
        if oname:
            return "%s.%s" % (oname, tail)
        t = type(obj).__name__ if obj is not None else ""
        short = (getattr(obj, "OBJECT_TYPE", None)
                 or self._TYPE_SHORT.get(t, (t.lower() or "obj")))
        seen = 0
        pat = _re.compile(_re.escape(short) + r"(\d+)\.", _re.I)
        for c in self.columns:
            m = pat.match(c.header().strip())
            if m:
                seen = max(seen, int(m.group(1)))
        return "%s%02d.%s" % (short, seen + 1, tail)

    def add_column(self, target: ObjectRef, attr_path: str,
                   var_name: str = "", kind: str = "text",
                   obj=None) -> BatchColumn:
        col = BatchColumn(_new_col_id(), target, attr_path, var_name, kind)
        # v4.4.0: never create two columns with the same header. A custom
        # name that is taken gets suffixed; an unnamed column only gets a
        # generated var_name when its fallback header (the attr path) would
        # collide, so the panels' pretty auto labels keep working.
        name = (var_name or "").strip()
        if name:
            if self.header_in_use(name):
                col.var_name = self.unique_header(name)
        elif self.header_in_use(col.header()):
            base = (self.system_header(obj, attr_path) if obj is not None
                    else ((attr_path or "col").split(".")[-1] or "col"))
            col.var_name = self.unique_header(base)
        self.columns.append(col)
        return col

    def remove_column(self, column_id: str) -> bool:
        before = len(self.columns)
        self.columns = [c for c in self.columns if c.column_id != column_id]
        for r in self.rows:
            r.values.pop(column_id, None)
        for r in self.demo_rows:
            r.values.pop(column_id, None)
        return len(self.columns) != before

    def column(self, column_id: str) -> Optional[BatchColumn]:
        return next((c for c in self.columns if c.column_id == column_id), None)

    def duplicate_name_counts(self) -> Dict[str, int]:
        """Map header-name -> count, for the 'same name used N times' highlight.
        Only names that genuinely repeat are returned."""
        counts: Dict[str, int] = {}
        for c in self.columns:
            h = c.header()
            counts[h] = counts.get(h, 0) + 1
        return {h: n for h, n in counts.items() if n > 1}

    # -- pruning when objects are deleted from the document --
    def prune_dead_columns(self, pages) -> List[str]:
        """Drop columns whose target no longer resolves on any page. Returns
        the removed column_ids (the editor calls this after a deletion)."""
        removed = []
        for c in list(self.columns):
            if find_ref_on_pages(pages, c.target) is None:
                removed.append(c.column_id)
                self.remove_column(c.column_id)
        return removed

    def orphan_columns(self, pages) -> List[str]:
        """Column ids whose target does not resolve anywhere (for red-header
        display on import; NOT removed)."""
        return [c.column_id for c in self.columns
                if find_ref_on_pages(pages, c.target) is None]

    # -- serialization --
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "row_scope": self.row_scope,
            "export_demo": bool(self.export_demo),
            "columns": [c.to_dict() for c in self.columns],
            "rows": [r.to_dict() for r in self.rows],
            "demo_rows": [r.to_dict() for r in self.demo_rows],
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "BatchConfig":
        if not d:
            return cls()
        cfg = cls(
            row_scope=d.get("row_scope", "page"),
            export_demo=bool(d.get("export_demo", False)),
            columns=[BatchColumn.from_dict(x) for x in d.get("columns", [])],
            rows=[BatchRow.from_dict(x) for x in d.get("rows", [])],
            demo_rows=[BatchRow.from_dict(x) for x in d.get("demo_rows", [])],
        )
        if cfg.row_scope not in ("page", "document"):
            cfg.row_scope = "page"
        return cfg

    def is_empty(self) -> bool:
        return not self.columns and not self.rows and not self.demo_rows

    # ── CSV export / import (v4.3.5.55) ──────────────────────────────────────
    # Two CSV files, by design:
    #   * the CLEAN csv: first column is the row name, then one column per
    #     batched attribute (its header), then the values. No meta, nothing extra
    #     -- opens cleanly in Excel/Sheets and is what a person edits by hand.
    #   * the META csv: a small side file (header, column_id, attr_path, kind)
    #     that lets an import re-bind each clean column to the exact batch column
    #     even if headers were renamed or duplicated. Optional on import: with it,
    #     mapping is lossless; without it, columns match by header.
    ROW_NAME_HEADER = "name"

    def to_csv(self, include_demo: bool = False) -> str:
        """The CLEAN csv (no meta line). Human-editable."""
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([self.ROW_NAME_HEADER] + [c.header() for c in self.columns])
        rows = list(self.rows) + (list(self.demo_rows) if include_demo else [])
        for r in rows:
            row = [r.name or ""]
            for c in self.columns:
                v = r.values.get(c.column_id, "")
                row.append("" if v is None else str(v))
            w.writerow(row)
        return buf.getvalue()

    def to_meta_csv(self) -> str:
        """The META side csv: maps each clean column (by position/header) back to
        its stable column_id, so an import is lossless even after renames."""
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["header", "column_id", "attr_path", "kind"])
        for c in self.columns:
            w.writerow([c.header(), c.column_id, c.attr_path, c.kind])
        return buf.getvalue()

    @staticmethod
    def _decode_bytes(data: bytes) -> str:
        """v4.3.5.55: best-effort encoding autodetect for an imported CSV. Tries
        a BOM, then utf-8, then cp1250 (common for Czech Windows exports), then
        latin-1 as a last resort (never fails)."""
        if data[:3] == b"\xef\xbb\xbf":
            return data[3:].decode("utf-8", errors="replace")
        for enc in ("utf-8", "cp1250", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("latin-1", errors="replace")

    @staticmethod
    def _parse_meta_csv(text_or_bytes) -> dict:
        """Parse the META side csv into {header -> column_id}."""
        import csv, io
        if isinstance(text_or_bytes, (bytes, bytearray)):
            text = BatchConfig._decode_bytes(bytes(text_or_bytes))
        else:
            text = text_or_bytes
        out = {}
        reader = csv.reader(io.StringIO(text))
        try:
            hdr = next(reader)
        except StopIteration:
            return out
        try:
            hi = hdr.index("header"); ci = hdr.index("column_id")
        except ValueError:
            return out
        for row in reader:
            if len(row) > max(hi, ci) and row[ci].strip():
                out[row[hi]] = row[ci].strip()
        return out

    def update_rows_from_csv(self, text_or_bytes, meta=None) -> int:
        """v4.3.5.55: replace the production rows from the CLEAN csv (text or raw
        bytes, with encoding autodetect). `meta` is the optional META side csv
        (text/bytes) for lossless re-binding; without it columns match by header
        against the batch's existing columns. Returns rows imported. Unknown
        headers are ignored, missing ones left blank. Does NOT create columns."""
        import csv, io
        if isinstance(text_or_bytes, (bytes, bytearray)):
            text = self._decode_bytes(bytes(text_or_bytes))
        else:
            text = text_or_bytes
        meta_map = self._parse_meta_csv(meta) if meta is not None else {}
        reader = csv.reader(io.StringIO(text))
        try:
            headers = next(reader)
        except StopIteration:
            return 0
        by_header = {c.header(): c.column_id for c in self.columns}
        valid_ids = {c.column_id for c in self.columns}
        idx_to_id = {}
        name_idx = None
        for i, h in enumerate(headers):
            if i == 0 and h.strip().lower() in (self.ROW_NAME_HEADER, "row", "row_name"):
                name_idx = i; continue
            cid = meta_map.get(h) or by_header.get(h)
            if cid and cid in valid_ids:
                idx_to_id[i] = cid
        new_rows = []
        for raw in reader:
            if not raw or all(not str(x).strip() for x in raw):
                continue
            vals = {}
            for i, cell in enumerate(raw):
                cid = idx_to_id.get(i)
                if cid:
                    vals[cid] = cell
            nm = raw[name_idx].strip() if (name_idx is not None
                                           and name_idx < len(raw)) else ""
            new_rows.append(BatchRow(values=vals, name=nm))
        self.rows = new_rows
        return len(new_rows)


# ── applying a row to a document (preview / generation) ──────────────────────
def _columns_in_priority_order(cfg: BatchConfig, page) -> List[Tuple[BatchColumn, Any]]:
    """Columns that resolve on `page`, paired with their descriptor, sorted so
    that LOWER priority (more important) is applied LAST and therefore wins on
    conflict. A column with extra targets yields one entry per target that
    resolves on this page, so one variable can drive several objects."""
    out = []
    for col in cfg.columns:
        for ref in col.all_targets():
            obj = resolve_ref(page, ref)
            if obj is None:
                continue
            eff_id = getattr(col, "effect_id", "")
            run_id = getattr(col, "run_id", "")
            desc = None
            if run_id and col.attr_path.startswith("run."):
                # v4.3.6.0: a run-targeted column binds to a specific run rid
                # inside this TextBox. v4.4.0: LINKED variables: the column also
                # fills every rid in extra_run_ids, each variable keeping its
                # own identity.
                from edof.batch import find_descriptor_with_run_id
                rid_set = {run_id} | set(getattr(col, "extra_run_ids", None) or [])
                has_rid = any(getattr(r, "rid", None) in rid_set
                              for r in (getattr(obj, "runs", None) or []))
                if has_rid:
                    desc = find_descriptor_with_run_id(
                        obj, col.attr_path, run_id,
                        extra_run_ids=getattr(col, "extra_run_ids", None))
                if desc is None and col.attr_path == "run.text":
                    # v4.3.6.16: a LINKED object that doesn't carry this rid
                    # (a multi-target run-text variable) gets the value in its
                    # whole text instead, so a run text variable can drive other
                    # text objects. The source span still resolves via its rid.
                    desc = find_descriptor(obj, "text")
                if desc is None:
                    continue
            elif eff_id:
                from edof.batch import find_descriptor_with_effect_id
                # the eid identifies an effect on the PRIMARY target. Other
                # linked objects (multi-target) have their own effects with
                # different eids, so the eid won't match there -- fall back to
                # the positional descriptor for those, otherwise the effect
                # would apply only to the primary object (the multi-object bug).
                has_eid = any(getattr(e, "eid", "") == eff_id
                              for e in (getattr(obj, "effects", None) or []))
                if has_eid:
                    desc = find_descriptor_with_effect_id(obj, col.attr_path, eff_id)
            if desc is None:
                desc = find_descriptor(obj, col.attr_path)
            if desc is None:
                continue
            out.append((col, obj, desc))
    # apply higher-priority-number first, lower last (lower wins)
    out.sort(key=lambda t: -t[2].priority)
    return out


def apply_row_to_document(cfg: BatchConfig, doc, row: BatchRow) -> int:
    """Apply a row's values to `doc` in place. Returns the number of cells
    actually applied. Respects row_scope and the registry's coercion / empty
    semantics. Never raises on a bad cell."""
    applied = 0
    pages = list(getattr(doc, "pages", []) or [])
    if not pages:
        return 0

    if cfg.row_scope == "page":
        # v4.3.5.22: page_target is now 1-based-in-UI / 0-based internally, and
        # None means CROSS-PAGE (the row applies to every page). A concrete
        # index targets just that page.
        if row.page_target is None:
            target_pages = pages          # cross-page
        else:
            idx = row.page_target
            if idx < 0 or idx >= len(pages):
                return 0
            target_pages = [pages[idx]]
    else:
        target_pages = pages

    # v4.4.0 (BUG #10): a file_path image column is materialised INTO the
    # resource store, so the document is self-contained after apply (save,
    # reload and every export path see the image, not just the raster
    # renderer's path fallback). One resource per distinct path per call.
    import os as _os
    _path_rids = {}

    def _materialise_file(obj_, col_, raw_):
        if (getattr(col_, "kind", "") != "file_path"
                or getattr(col_, "attr_path", "") != "resource_id"):
            return
        if not (isinstance(raw_, str) and raw_.strip()):
            return
        pth = raw_.strip()
        res = getattr(doc, "resources", None)
        if res is None or pth in res or not _os.path.isfile(pth):
            return
        rid_ = _path_rids.get(pth)
        if rid_ is None:
            try:
                rid_ = doc.add_resource_from_file(pth)
            except Exception:
                return
            _path_rids[pth] = rid_
        try:
            obj_.resource_id = rid_
        except Exception:
            pass

    for page in target_pages:
        for col, obj, desc in _columns_in_priority_order(cfg, page):
            if col.column_id not in row.values:
                continue
            raw = row.values.get(col.column_id)
            ok = desc.set(obj, raw)
            if ok:
                _materialise_file(obj, col, raw)
            try:
                from edof.engine.debug_log import log as _dlog
                _dlog("apply_row.cell", path=col.attr_path, raw=str(raw),
                      ok=ok, obj_id=str(getattr(obj, "id", "?"))[:8],
                      n_effects=len(getattr(obj, "effects", []) or []),
                      effects_enabled=getattr(obj, "effects_enabled", None))
            except Exception: pass
            if ok:
                # count only non-empty applications
                if not (raw is None or (isinstance(raw, str) and raw.strip() == "")):
                    applied += 1
    return applied


# ── export filename templates (v4.3.5.57) ────────────────────────────────────
def render_filename(template: str, row_number, row: "BatchRow",
                    cfg: "BatchConfig", default_ext: str = "png",
                    page_number=None) -> str:
    """Build an output filename for a batch row from a token template.

    Tokens (case-insensitive):
      [ROW_NUMBER]        the 1-based row number
      [ROW_NUMBER:04]     zero-padded to the given width (e.g. 0007)
      [ROW_NAME]          the row's name (blank -> "row")
      [PAGE]              the 1-based page number (v4.4.0, per-page outputs)
      [PAGE:02]           zero-padded page number
      [{Header}]          the value of the column whose header is Header
      [{Header:upper}]    that value upper/lower-cased ("upper"/"lower")

    Unknown tokens are left as-is minus the brackets. The result is sanitized
    for the filesystem (no / \\ : * ? " < > |, trimmed) and an extension is
    appended if the template didn't include one.
    """
    import re
    if not template:
        template = "[ROW_NUMBER:04]"
    # map header -> value for this row
    by_header = {}
    for c in cfg.columns:
        v = row.values.get(c.column_id, "")
        by_header[c.header().lower()] = "" if v is None else str(v)

    def _sub(m):
        tok = m.group(1).strip()
        low = tok.lower()
        # column value token: {Header} or {Header:mod}
        if tok.startswith("{") and tok.endswith("}"):
            inner = tok[1:-1]
            mod = ""
            if ":" in inner:
                inner, mod = inner.split(":", 1)
            val = by_header.get(inner.strip().lower(), "")
            if mod.strip().lower() == "upper":
                val = val.upper()
            elif mod.strip().lower() == "lower":
                val = val.lower()
            return val
        # row number, optional :NN padding
        if low == "row_number" or low.startswith("row_number:"):
            pad = 0
            if ":" in tok:
                try:
                    pad = int(tok.split(":", 1)[1])
                except ValueError:
                    pad = 0
            return str(row_number).zfill(pad) if pad else str(row_number)
        if low == "row_name":
            nm = (row.name or "").strip()
            return nm if nm else "row"
        # v4.4.0: page number for per-page outputs
        if low == "page" or low.startswith("page:"):
            if page_number is None:
                return ""
            pad = 0
            if ":" in tok:
                try:
                    pad = int(tok.split(":", 1)[1])
                except ValueError:
                    pad = 0
            return (str(page_number).zfill(pad) if pad
                    else str(page_number))
        return tok            # unknown -> drop brackets, keep text

    out = re.sub(r"\[([^\[\]]*)\]", _sub, template)
    # split extension if present in the template
    base, dot, ext = out.rpartition(".")
    if dot and 1 <= len(ext) <= 5 and ext.isalnum():
        name, file_ext = base, ext
    else:
        name, file_ext = out, default_ext
    # sanitize for the filesystem
    name = re.sub(r'[/\\:*?"<>|]+', "_", name).strip().strip(".")
    if not name:
        name = "row"
    return f"{name}.{file_ext}"


# ── migration: old document variables -> 3D Batch columns (v4.3.5.59) ────────
def migrate_variables_to_batch(doc) -> int:
    """Consolidate the legacy variable system into the 3D Batch.

    Old model: an object carried `obj.variable` = the name of a document-level
    variable, and at render time that variable's value replaced the object's
    text. That is just batching the object's `text` attribute, so this converts
    each such binding into a 3D Batch column (target = that object, attr = text,
    header = the variable name) and clears `obj.variable`. The variables' current
    values become a single batch row so nothing visually changes. Idempotent:
    objects already migrated (no `obj.variable`) are skipped, and a column for the
    same target+attr isn't duplicated.

    Returns the number of bindings migrated.
    """
    if doc is None:
        return 0
    pages = list(getattr(doc, "pages", []) or [])

    # First pass: is there anything bound at all? If not, return WITHOUT touching
    # doc.batch -- creating the lazy BatchConfig here would turn a genuinely
    # empty/absent batch into a non-None one (older files expect _batch is None).
    def _any_bound(level):
        for o in level:
            if getattr(o, "variable", None):
                return True
            kids = _children_of(o)
            if kids and _any_bound(kids):
                return True
        return False
    if not any(_any_bound(list(getattr(pg, "objects", []) or [])) for pg in pages):
        return 0

    store = getattr(doc, "variables", None)
    cfg = getattr(doc, "batch", None)
    if cfg is None:
        return 0

    # existing (target_id-tuple, attr) pairs so we don't double-add columns
    have = set()
    for c in cfg.columns:
        ids = tuple(getattr(c.target, "path", None) or [])
        have.add((ids, c.attr_path))

    migrated = 0
    row_values = {}            # column_id -> value for the single migration row
    for pi, page in enumerate(pages):
        def _walk(level):
            nonlocal migrated
            for o in level:
                var = getattr(o, "variable", None)
                if var:
                    ref = build_ref(page, o)
                    if ref is not None:
                        key = (tuple(ref.to_list()), "text")
                        if key not in have:
                            col = BatchColumn(
                                column_id=_new_col_id(),
                                target=ref,
                                attr_path="text",
                                var_name=str(var),
                                kind="text",
                            )
                            cfg.columns.append(col)
                            have.add(key)
                            # capture the variable's current value for the row
                            val = ""
                            if store is not None:
                                try:
                                    v = store.get(var)
                                    val = "" if v is None else str(v)
                                except Exception:
                                    val = ""
                            row_values[col.column_id] = val
                            migrated += 1
                    # clear the legacy binding regardless (it's gone now)
                    try:
                        o.variable = None
                    except Exception:
                        pass
                kids = _children_of(o)
                if kids:
                    _walk(kids)
        _walk(list(getattr(page, "objects", []) or []))

    # add a single row carrying the migrated values, if we made any columns and
    # there are no rows yet (don't clobber an existing batch the user built)
    if migrated and row_values and not cfg.rows:
        cfg.rows.append(BatchRow(values=row_values, name="migrated"))
    return migrated
