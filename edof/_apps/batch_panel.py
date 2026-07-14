"""3D Batch panel — the editor-side UI for the batch model (phase 4.3.3.0).

A dockable panel that edits a document's BatchConfig: a table whose columns are
batched object attributes and whose rows are value sets, plus an "add column"
flow (pick object -> pick attribute -> demo value) built on the attribute
registry. Cells are plain text for now; the model underneath already supports
every value kind, so the smart cell editors (colour swatch, file dialog, enum
dropdown) land in 4.3.4.0 as pure presentation over this.

This uses the available Qt table (QTableWidget). Per the roadmap, when the
custom "edof tabs" component exists it replaces this table; the panel API stays
the same.

Design notes:
  * The panel never owns batch data — it reads/writes ``doc.batch`` (the live
    BatchConfig) and asks the canvas to re-render previews. It is a view.
  * "Add column" resolves the currently selected canvas object, lists its
    registry descriptors, and on confirm appends a BatchColumn. The header
    shows the human var name (or the attribute path).
  * Duplicate header names are tinted (the "same name xN" safety highlight);
    orphaned columns (target no longer resolves) get a red header.
  * Page-scope shows a first "Page" column (spin per row); document-scope hides
    it. Switching scope just re-reads the model.

Headless-friendly: constructing the panel and calling its public methods does
not require a visible window, so the logic is unit-testable under the offscreen
platform.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QListWidget,
    QLineEdit, QDialogButtonBox, QMessageBox, QAbstractItemView,
    QStyledItemDelegate, QColorDialog, QFileDialog,
)

from edof.batch import describe_object, find_descriptor
from edof.batch.model import build_ref, resolve_ref, BatchRow


# v4.3.5.33: human-readable names for shape subtypes, so the table filter can
# match an object by what the user sees ("rectangle") even though the table
# never prints it.
_SHAPE_TYPE_WORDS = {
    "rect": "rectangle rect", "ellipse": "ellipse circle oval",
    "line": "line", "path": "path", "polygon": "polygon", "arrow": "arrow",
}


def _flatten_targets(page):
    """v4.3.5.43: top-level page objects PLUS the children inside any group, so
    batch columns can target objects that live inside a group. The group itself
    is included too (you can batch the group's own transform)."""
    out = []

    def _walk(objs):
        for o in objs:
            out.append(o)
            kids = getattr(o, "children", None)
            if kids:
                _walk(kids)

    _walk(list(getattr(page, "objects", []) or []))
    return out


def _object_filter_text(obj):
    """Lower-case text describing an object for the table filter: its name, its
    object type, and a human word for its shape subtype (e.g. 'rectangle')."""
    parts = []
    nm = getattr(obj, "name", "") or ""
    if nm:
        parts.append(nm)
    ot = getattr(obj, "OBJECT_TYPE", "") or ""
    if ot:
        parts.append(ot)
    st = getattr(obj, "shape_type", "") or ""
    if st:
        parts.append(st)
        parts.append(_SHAPE_TYPE_WORDS.get(st, ""))
    return " ".join(parts).lower()


def _blog(tag, **fields):
    """Thin wrapper around the debug logger for batch-panel events."""
    try:
        from edof.engine.debug_log import log as _dlog
        _dlog(tag, **fields)
    except Exception:
        pass


def _gray_brush():
    from PyQt6.QtGui import QBrush, QColor
    return QBrush(QColor("#888"))


def _page_target_to_display(pt):
    """Convert an internal page_target to its UI string. None -> 'crosspage'
    (the row applies to every page); a 0-based index -> its 1-based number."""
    if pt is None:
        return "crosspage"
    try:
        return str(int(pt) + 1)
    except Exception:
        return "crosspage"


def _display_to_page_target(text):
    """Parse a UI page string back to an internal page_target. '0', 'crosspage',
    'cross', 'all', or blank -> None (cross-page). N>=1 -> 0-based index N-1."""
    t = (text or "").strip().lower()
    if t in ("", "0", "crosspage", "cross", "cross-page", "all", "*"):
        return None
    try:
        n = int(t)
        return max(0, n - 1)
    except ValueError:
        return None


def _iter_hf_template_runs(doc):
    """v4.4.0: yield the header/footer TEMPLATE runs: the band text templates
    (header_runs/footer_runs, plus the _even sets) and the runs of container
    objects (body.header_objects/footer_objects). A rid edit that only touched
    the per-page clones would be undone by the next repagination, so every
    rid-level op mirrors into these too."""
    body = getattr(doc, "body", None) if doc is not None else None
    if body is None:
        return
    for attr in ("header_runs", "footer_runs",
                 "header_runs_even", "footer_runs_even"):
        for r in (getattr(body, attr, None) or []):
            yield r
    for attr in ("header_objects", "footer_objects"):
        for o in (getattr(body, attr, None) or []):
            for r in (getattr(o, "runs", None) or []):
                yield r


def _merge_run_variables_in_doc(doc, cfg, primary_rid, primary_name, merge_rids):
    """v4.3.6.21: fold each variable in ``merge_rids`` into the primary one --
    reassign its runs to ``primary_rid``/``primary_name`` and drop its batch
    columns. After this a single column (on primary_rid) drives every folded-in
    span. Returns True if anything changed."""
    mset = {r for r in (merge_rids or []) if r and r != primary_rid}
    if not mset or doc is None:
        return False
    changed = False
    for pg in (getattr(doc, "pages", None) or []):
        for obj in _flatten_targets(pg):
            for r in (getattr(obj, "runs", None) or []):
                if getattr(r, "rid", None) in mset:
                    try:
                        r.rid = primary_rid
                        r.var_name = primary_name
                        changed = True
                    except Exception:
                        pass
    # v4.4.0: fold in the header/footer TEMPLATE runs too
    for r in _iter_hf_template_runs(doc):
        if getattr(r, "rid", None) in mset:
            try:
                r.rid = primary_rid
                r.var_name = primary_name
                changed = True
            except Exception:
                pass
    if cfg is not None:
        for cid in [c.column_id for c in list(cfg.columns)
                    if getattr(c, "run_id", "") in mset]:
            try: cfg.remove_column(cid); changed = True
            except Exception: pass
    return changed


def _header_in_use(cfg, header, exclude_col_id=None):
    """True if `header` (case-insensitive, trimmed) is already the variable name
    of another column. Used to keep column headers unique, which export/import
    requires. Empty header never conflicts (the auto data-name is used then and
    is unique per target+attr)."""
    h = (header or "").strip().lower()
    if not h or cfg is None:
        return False
    for c in cfg.columns:
        if exclude_col_id is not None and c.column_id == exclude_col_id:
            continue
        if (c.var_name or "").strip().lower() == h:
            return True
    return False


# kind cached on each cell item so the delegate knows how to edit it
_KIND_ROLE = Qt.ItemDataRole.UserRole + 1
_COLID_ROLE = Qt.ItemDataRole.UserRole + 2


_DUP_TINT = QColor(120, 110, 40)     # amber-ish: duplicate header name
_ORPHAN_TINT = QColor(120, 40, 40)   # red: target no longer resolves


def _parse_color(text):
    """Best-effort parse of a cell's text into a QColor for the swatch; None
    if it isn't a colour value."""
    if not text:
        return None
    s = str(text).strip()
    try:
        if s.startswith("#") and len(s) in (7, 9):
            c = QColor(s[:7])
            return c if c.isValid() else None
        parts = [p for p in s.replace(";", ",").split(",") if p.strip() != ""]
        if len(parts) in (3, 4):
            vals = [max(0, min(255, int(round(float(p))))) for p in parts[:3]]
            return QColor(*vals)
    except (ValueError, TypeError):
        return None
    return None


# ── recording helpers ────────────────────────────────────────────────────────
def _values_equal(a, b):
    """Compare two attribute values for recording. Numbers compare with a small
    tolerance; colours/tuples element-wise; everything else by string."""
    if a is None and b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-6
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        if len(a) != len(b):
            return False
        return all(_values_equal(x, y) for x, y in zip(a, b))
    return str(a) == str(b)


def _value_to_raw(value, kind):
    """Convert a live attribute value into the raw cell string the batch model
    stores (so it round-trips through the descriptor's setter)."""
    if kind == "color":
        if isinstance(value, (tuple, list)) and len(value) >= 3:
            r, g, b = int(value[0]), int(value[1]), int(value[2])
            return "#%02x%02x%02x" % (r, g, b)
        return str(value)
    if kind == "number":
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    if kind == "enum":
        return str(value)
    return str(value)


def _find_or_add_column(cfg, ref, desc, obj=None):
    """Return the existing column matching (ref target, attr path) or add one
    (v4.4.0: with a systematic unique name derived from the object)."""
    for c in cfg.columns:
        if c.attr_path == desc.path and c.target == ref:
            return c
    return cfg.add_column(ref, desc.path, "", desc.kind, obj=obj)


def _existing_paths_for_object(cfg, obj, pages):
    """Set of attr_paths already used as variables that target `obj` (so the
    Add-variable dialog can show them pre-checked / disabled)."""
    paths = set()
    if cfg is None or obj is None:
        return paths
    oid = getattr(obj, "id", None)
    for col in cfg.columns:
        for ref in col.all_targets():
            for pg in pages:
                ro = resolve_ref(pg, ref)
                if ro is not None and getattr(ro, "id", None) == oid:
                    paths.add(col.attr_path)
                    break
    return paths


def _pick_color_standard(parent, current_rgb):
    """Open EDOF's own colour picker (not Qt's), returning a '#rrggbb' string or
    None. `current_rgb` may be a hex string, an (r,g,b[,a]) tuple, or None."""
    # resolve the initial colour to an (r,g,b,a) tuple
    init = (0, 0, 0, 255)
    if isinstance(current_rgb, (tuple, list)) and len(current_rgb) >= 3:
        init = (int(current_rgb[0]), int(current_rgb[1]), int(current_rgb[2]),
                int(current_rgb[3]) if len(current_rgb) >= 4 else 255)
    else:
        qc = _parse_color(current_rgb) if current_rgb is not None else None
        if qc is not None:
            init = (qc.red(), qc.green(), qc.blue(), 255)
    try:
        from edof._apps.editor import EdofColorDialog
        res = EdofColorDialog.get_color(parent, init, alpha=False)
        if res is None:
            return None
        r, g, b = int(res[0]), int(res[1]), int(res[2])
        return "#%02x%02x%02x" % (r, g, b)
    except Exception:
        # fall back to Qt's dialog only if EDOF's picker can't be loaded
        c = QColorDialog.getColor(QColor(*init[:3]), parent, "Pick colour")
        if c.isValid():
            return "#%02x%02x%02x" % (c.red(), c.green(), c.blue())
        return None


class _CellDelegate(QStyledItemDelegate):
    """Type-aware editors driven by each cell's cached kind:
    colour -> colour dialog, enum -> dropdown, file_path -> open-file dialog,
    everything else -> a normal line edit. The colour swatch is painted by the
    panel (item background), not here."""

    def __init__(self, panel):
        super().__init__(panel)
        self._panel = panel

    def _kind(self, index):
        return index.data(_KIND_ROLE)

    def _choices(self, index):
        col = self._panel._column_for_visual(index.column())
        if col is None:
            return None
        # need a live object to read enum choices off the descriptor
        obj = self._panel._first_object_for_column(col)
        if obj is None:
            return None
        desc = find_descriptor(obj, col.attr_path)
        return desc.choices if desc else None

    def createEditor(self, parent, option, index):
        kind = self._kind(index)
        if kind == "enum":
            choices = self._choices(index) or []
            cb = QComboBox(parent)
            cb.addItems([str(c) for c in choices])
            return cb
        if kind == "color":
            # modal dialog now; return None so no inline editor lingers
            cur = index.data(Qt.ItemDataRole.DisplayRole)
            hexv = _pick_color_standard(parent, cur)
            if hexv is not None:
                self._panel._set_cell_text(index.row(), index.column(), hexv)
            return None
        if kind == "file_path":
            path, _f = QFileDialog.getOpenFileName(
                parent, "Choose file", "",
                "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All files (*)")
            if path:
                self._panel._set_cell_text(index.row(), index.column(), path)
            return None
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            cur = index.data(Qt.ItemDataRole.DisplayRole) or ""
            i = editor.findText(str(cur))
            if i >= 0:
                editor.setCurrentIndex(i)
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(),
                          Qt.ItemDataRole.DisplayRole)
            return
        super().setModelData(editor, model, index)


class _AddColumnDialog(QDialog):
    """Tree of checkable attributes to batch, grouped (Content / Geometry /
    Style / Layer Effects), with effects expandable to their fields -- including
    effects the object doesn't have yet (Path A) and several instances of the
    same effect type. Each leaf has a checkbox and an inline text field for the
    variable name. OK returns every checked leaf as a (descriptor, var_name)
    pair."""

    def __init__(self, obj, parent=None, existing_paths=None, existing_names=None,
                 extra_objs=None):
        super().__init__(parent)
        self._obj = obj
        # v4.3.5.31: other objects in a multi-selection. When present, the tree
        # is filtered to attributes COMMON to all selected objects, and the title
        # shows the count -- so a multi-select batches only what they share.
        self._extra_objs = [o for o in (extra_objs or []) if o is not obj]
        n_sel = 1 + len(self._extra_objs)
        if n_sel > 1:
            self.setWindowTitle("Add batch variables  (%d objects)" % n_sel)
        else:
            self.setWindowTitle("Add batch variables")
        self.resize(840, 600)
        self._result = []           # list of (descriptor, var_name)
        # paths already used as variables for this object -> shown pre-checked
        # and disabled so they can't be added twice
        self._existing_paths = set(existing_paths or [])
        # variable names already in use anywhere (for uniqueness validation)
        self._existing_names = {(n or "").strip().lower()
                                for n in (existing_names or []) if (n or "").strip()}
        self._desc_by_path = {}
        # name editors and checkable items, keyed by descriptor path, so we can
        # read names back on accept and survive tree rebuilds
        self._name_edits = {}
        self._items_by_path = {}
        # extra effect instances the user asked to add beyond those on the
        # object (per effect type): {eff_type: count_of_extra_new_slots}
        self._extra_instances = {}
        self._checked_paths = set()       # remembered across rebuilds
        self._reordered = False           # set if the user reordered effects

        from PyQt6.QtWidgets import QTreeWidget, QPushButton, QMenu
        lay = QVBoxLayout(self)
        intro = ("Check the attributes to batch and type a variable name next to "
                 "each (optional). Effects can be added even if the object "
                 "doesn't have them yet, and you can add several instances of the "
                 "same effect.")
        if self._extra_objs:
            intro = ("%d objects selected \u2014 showing only the attributes they "
                     "all share. Each variable you add will drive every selected "
                     "object." % (1 + len(self._extra_objs)))
        lay.addWidget(QLabel(intro))

        # v4.3.5.26: split the dialog into a left column (effect reorder + remove)
        # and the attribute tree on the right; the dialog is wider to fit both.
        from PyQt6.QtWidgets import QHBoxLayout as _QHB, QWidget as _QWdg, QVBoxLayout as _QVB
        split = _QHB()
        left_col = _QVB()
        left_col.setContentsMargins(0, 0, 0, 0)
        # v4.3.5.24/26: drag-to-reorder list of the object's effects, shown only
        # when there are 2+. Reordering rewrites the effect order ON THE OBJECT
        # (same as the layer-effects dialog), and variables bound by eid follow.
        self._fx_reorder = None
        self._build_effect_reorder(left_col)
        left_host = _QWdg()
        left_host.setLayout(left_col)
        left_host.setFixedWidth(220)
        split.addWidget(left_host)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Attribute", "Variable name"])
        self._tree.setColumnWidth(0, 340)
        self._tree.itemChanged.connect(self._on_item_changed)
        split.addWidget(self._tree, 1)
        lay.addLayout(split, 1)

        # role key for storing the descriptor path on a leaf item
        self._DESC_ROLE = Qt.ItemDataRole.UserRole + 10

        # "add another effect instance" control
        from edof.batch import effect_types
        add_row = QHBoxLayout()
        self._btn_add_fx = QPushButton("+ Add effect instance")
        fx_menu = QMenu(self._btn_add_fx)
        for et in effect_types():
            act = fx_menu.addAction(et)
            act.triggered.connect(lambda _checked=False, t=et: self._add_instance(t))
        self._btn_add_fx.setMenu(fx_menu)
        add_row.addWidget(self._btn_add_fx)
        add_row.addStretch(1)
        lay.addLayout(add_row)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._rebuild_tree()

    def _build_effect_reorder(self, parent_layout):
        """Create the (initially empty) drag-to-reorder effects widget. It's
        populated by _rebuild_effect_reorder and hidden when the object has < 2
        effects. Mirrors the layer-effects dialog so order stays in sync."""
        from PyQt6.QtWidgets import (QListWidget, QLabel, QAbstractItemView,
                                     QWidget, QVBoxLayout)
        cont = QWidget()
        cv = QVBoxLayout(cont)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(1)
        self._fx_reorder_label = QLabel("Effect order (drag to reorder):")
        cv.addWidget(self._fx_reorder_label)
        lw = QListWidget()
        lw.setMaximumHeight(110)
        lw.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        lw.setDefaultDropAction(Qt.DropAction.MoveAction)
        lw.model().rowsMoved.connect(lambda *a: self._on_fx_reordered())
        cv.addWidget(lw)
        # remove the selected effect from the object (mistake / no longer wanted)
        from PyQt6.QtWidgets import QPushButton
        btn_rm = QPushButton("Remove selected effect")
        btn_rm.clicked.connect(self._remove_selected_effect)
        cv.addWidget(btn_rm)
        self._fx_remove_btn = btn_rm
        self._fx_reorder = lw
        self._fx_reorder_cont = cont
        parent_layout.addWidget(cont)
        self._rebuild_effect_reorder()

    def _rebuild_effect_reorder(self):
        """Refill the reorder list from the object's current effects (all types,
        not just identical ones). Hidden when there are fewer than 2."""
        if getattr(self, "_fx_reorder", None) is None:
            return
        from PyQt6.QtWidgets import QListWidgetItem
        DISPLAY = {
            "drop_shadow": "Drop shadow", "inner_shadow": "Inner shadow",
            "outer_glow": "Outer glow", "inner_glow": "Inner glow",
            "bevel": "Bevel & emboss", "stroke": "Stroke",
            "color_overlay": "Color overlay", "gradient_overlay": "Gradient overlay",
            "satin": "Satin", "halftone": "Halftone",
            "texture_overlay": "Texture overlay", "pixelate": "Pixelate",
            "chromatic_aberration": "Chromatic aberration",
        }
        effects = [e for e in (getattr(self._obj, "effects", None) or [])]
        lw = self._fx_reorder
        lw.blockSignals(True)
        lw.clear()
        seen = {}
        for e in effects:
            t = getattr(e, "type", "?")
            base = DISPLAY.get(t, t)
            seen[t] = seen.get(t, 0) + 1
            same = [x for x in effects if getattr(x, "type", None) == t]
            label = "%s %d" % (base, seen[t]) if len(same) > 1 else base
            if not getattr(e, "enabled", True):
                label += "  (off)"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, getattr(e, "eid", ""))
            lw.addItem(it)
        lw.blockSignals(False)
        # show the block when there's at least one effect (so it can be removed);
        # the drag-reorder is only meaningful with 2+, but a single effect can
        # still be removed if it was a mistake
        vis = len(effects) >= 1
        if getattr(self, "_fx_reorder_label", None) is not None:
            self._fx_reorder_label.setText(
                "Effect order (drag to reorder):" if len(effects) >= 2
                else "Effect on object:")
        if getattr(self, "_fx_reorder_cont", None) is not None:
            self._fx_reorder_cont.setVisible(vis)

    def _on_fx_reordered(self):
        """The user dragged an effect in the reorder list -> apply the new order
        to the object's effects, remember tree state, and rebuild the tree so the
        instance ordinals (#1, #2, ...) match. Variables bound by eid follow."""
        if self._fx_reorder is None:
            return
        # new eid order from the list
        order = []
        for i in range(self._fx_reorder.count()):
            eid = self._fx_reorder.item(i).data(Qt.ItemDataRole.UserRole)
            if eid:
                order.append(eid)
        effects = list(getattr(self._obj, "effects", None) or [])
        by_eid = {getattr(e, "eid", ""): e for e in effects}
        new_list = [by_eid[e] for e in order if e in by_eid]
        # keep any effect without an eid (shouldn't happen) at the end
        for e in effects:
            if e not in new_list:
                new_list.append(e)
        try:
            self._obj.effects = new_list
        except Exception:
            return
        self._reordered = True        # signal the caller the object changed
        self._remember_state()
        self._rebuild_effect_reorder()
        self._rebuild_tree()

    def _remove_selected_effect(self):
        """Remove the effect selected in the reorder list from the object (e.g.
        the user added it by mistake). Any batch column bound to it by eid is
        dropped too, so no column is left pointing at a missing effect."""
        if getattr(self, "_fx_reorder", None) is None:
            return
        it = self._fx_reorder.currentItem()
        if it is None:
            return
        eid = it.data(Qt.ItemDataRole.UserRole)
        effects = list(getattr(self._obj, "effects", None) or [])
        new = [e for e in effects if getattr(e, "eid", "") != eid]
        if len(new) == len(effects):
            return        # nothing matched
        try:
            self._obj.effects = new
        except Exception:
            return
        self._reordered = True
        # drop any pending checks for that effect's paths so we don't re-add it
        self._remember_state()
        self._rebuild_effect_reorder()
        self._rebuild_tree()

    def _add_instance(self, eff_type):
        """User asked for another instance of an effect type. v4.3.5.25: really
        adds a (disabled) effect to the object -- like the layer-effects dialog
        -- so it appears in the tree, can be reordered, and a variable on it
        binds by eid. v4.3.5.26: uses make_default_effect so the new effect has
        the same sensible defaults the 'add effect' UI uses, not bare dataclass
        defaults. Then remember state and rebuild."""
        from edof.batch import make_default_effect
        self._remember_state()
        try:
            if getattr(self._obj, "effects", None) is None:
                self._obj.effects = []
            eff = make_default_effect(eff_type)
            if eff is None:
                from edof.format.styles import LayerEffect
                eff = LayerEffect(type=eff_type, enabled=False)
            eff.enabled = False        # added off; the batch turns it on
            self._obj.effects.append(eff)
            # v4.3.5.29: do NOT touch the object's master here. Per request,
            # effects shouldn't work without an explicit "effects enabled"
            # (all_enabled) variable; a red warning in the panel tells the user
            # when an effect variable exists without a master variable.
            self._reordered = True        # the object changed -> caller repaints
        except Exception:
            self._extra_instances[eff_type] = self._extra_instances.get(eff_type, 0) + 1
        self._rebuild_effect_reorder()
        self._rebuild_tree()
        # expand Layer Effects so the newly added instance is visible
        for i in range(self._tree.topLevelItemCount()):
            it = self._tree.topLevelItem(i)
            if it.text(0) == "Layer Effects":
                it.setExpanded(True)
                for j in range(it.childCount() - 1, -1, -1):
                    if it.child(j).text(0).startswith(eff_type):
                        it.child(j).setExpanded(True)
                        break
                break

    def _remember_state(self):
        """Snapshot which paths are checked and the names typed, so a rebuild
        doesn't lose them."""
        for path, item in self._items_by_path.items():
            try:
                if item.checkState(0) == Qt.CheckState.Checked:
                    self._checked_paths.add(path)
                else:
                    self._checked_paths.discard(path)
            except Exception:
                pass
        for path, edit in self._name_edits.items():
            try:
                t = edit.text().strip()
                if t:
                    self._name_cache = getattr(self, "_name_cache", {})
                    self._name_cache[path] = t
            except Exception:
                pass

    def _rebuild_tree(self):
        from PyQt6.QtWidgets import QTreeWidgetItem
        self._tree.blockSignals(True)
        self._tree.clear()
        self._name_edits = {}
        self._items_by_path = {}

        from edof.batch import (describe_object, PRIO_CONTENT, PRIO_GEOMETRY,
                                 PRIO_STYLE, _all_enabled_descriptor,
                                 effect_types, _effect_field_descriptor,
                                 _EFFECT_FIELDS)
        obj = self._obj
        descs = describe_object(obj)
        bands = [("Content", PRIO_CONTENT), ("Geometry", PRIO_GEOMETRY),
                 ("Style", PRIO_STYLE)]
        for title, prio in bands:
            in_band = [d for d in descs
                       if prio <= d.priority < prio + 10
                       and not d.path.startswith("effects.")]
            if not in_band:
                continue
            grp = QTreeWidgetItem(self._tree, [title, ""])
            grp.setFlags(grp.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            grp.setExpanded(True)
            for d in in_band:
                self._add_leaf(grp, d)

        type_counts = {}
        for e in (getattr(obj, "effects", None) or []):
            et = getattr(e, "type", None)
            if et:
                type_counts[et] = type_counts.get(et, 0) + 1
        fx_root = QTreeWidgetItem(self._tree, ["Layer Effects", ""])
        fx_root.setFlags(fx_root.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        fx_root.setExpanded(False)        # collapsed by default (can be deep)
        self._add_leaf(fx_root, _all_enabled_descriptor(), leaf_label="All effects")

        def _add_instance_group(et, ordinal, label):
            grp = QTreeWidgetItem(fx_root, [label, ""])
            grp.setFlags(grp.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            grp.setExpanded(False)        # collapsed by default
            for field, kind, flabel in _EFFECT_FIELDS.get(et, []):
                d = _effect_field_descriptor(et, field, kind, flabel, ordinal=ordinal)
                self._add_leaf(grp, d, leaf_label=field)
            # v4.3.5.53: halftone also exposes the pattern FILE PATH slot(s) so a
            # custom pattern can be batched by path (the path is the source of
            # truth; it's loaded into the base64 cache at apply time). Mirror the
            # slot logic in batch._effect_descriptors: one slot for shape/single
            # mode, per-channel slots otherwise. Only on the first instance.
            if et == "halftone" and ordinal == 0:
                from edof.batch import _ht_pattern_path_descriptor
                e0 = next((e for e in (getattr(obj, "effects", None) or [])
                           if getattr(e, "type", None) == "halftone"), None)
                n_slots = 4 if getattr(e0, "ht_color_mode", "cmyk") == "cmyk" else 3
                if getattr(e0, "ht_pattern_mode", "shape") in ("shape", "single"):
                    n_slots = 1
                for k in range(n_slots):
                    d = _ht_pattern_path_descriptor(ordinal=k)
                    leaf = ("Pattern file" if k == 0
                            else "Pattern file #%d" % (k + 1))
                    self._add_leaf(grp, d, leaf_label=leaf)

        # v4.3.5.25: show only the effect types the object actually HAS, plus
        # any the user explicitly added via "+ Add effect instance" (tracked in
        # _extra_instances). We no longer pad a "(new)" slot for every effect
        # type -- that flooded the tree. Effects are added dynamically instead.
        shown_types = []
        for et in effect_types():
            if type_counts.get(et, 0) > 0 or self._extra_instances.get(et, 0) > 0:
                shown_types.append(et)
        for et in shown_types:
            n = type_counts.get(et, 0)
            extra = self._extra_instances.get(et, 0)
            # instances on the object -> "(on object)"
            for k in range(n):
                lbl = et if k == 0 else "%s #%d" % (et, k + 1)
                _add_instance_group(et, k, lbl + "  (on object)")
            # then any extra "(new)" slots the user explicitly asked for
            for j in range(extra):
                ordn = n + j
                lbl = et if ordn == 0 else "%s #%d" % (et, ordn + 1)
                tag = "  (new)" if (n > 0 or j > 0) else ""
                _add_instance_group(et, ordn, lbl + tag)
        if not shown_types:
            hint = QTreeWidgetItem(fx_root,
                                   ["(use \u201c+ Add effect instance\u201d to batch an effect)", ""])
            hint.setFlags(hint.flags() & ~Qt.ItemFlag.ItemIsUserCheckable
                          & ~Qt.ItemFlag.ItemIsSelectable)
            hint.setForeground(0, _gray_brush())
        # multi-select: drop any band/group left empty by the common-attribute
        # filter, so the tree doesn't show headers with nothing under them
        if getattr(self, "_extra_objs", None):
            for i in range(self._tree.topLevelItemCount() - 1, -1, -1):
                top = self._tree.topLevelItem(i)
                if top.text(0) == "Layer Effects":
                    continue      # keep (has the master + add control context)
                if top.childCount() == 0:
                    self._tree.takeTopLevelItem(i)
        self._tree.blockSignals(False)

    def _common_to_all(self, path):
        """For a multi-selection, True only if every extra object also has this
        attribute (so the variable can apply to all). Always True for a single
        selection."""
        for eo in getattr(self, "_extra_objs", []):
            if find_descriptor(eo, path) is None:
                return False
        return True

    def _add_leaf(self, parent, desc, leaf_label=None):
        from PyQt6.QtWidgets import QTreeWidgetItem, QLineEdit
        # multi-select: skip attributes not shared by all selected objects
        if getattr(self, "_extra_objs", None) and not self._common_to_all(desc.path):
            return
        text = leaf_label if leaf_label is not None else desc.label
        already = desc.path in getattr(self, "_existing_paths", set())
        suffix = "  [%s]" % desc.kind + ("   ✓ already a variable" if already else "")
        item = QTreeWidgetItem(parent, [f"{text}{suffix}", ""])
        if already:
            item.setFlags((item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                          & ~Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(0, Qt.CheckState.Checked)
        else:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = desc.path in getattr(self, "_checked_paths", set())
            item.setCheckState(0, Qt.CheckState.Checked if checked
                               else Qt.CheckState.Unchecked)
        item.setData(0, self._DESC_ROLE, desc.path)
        self._desc_by_path[desc.path] = desc
        self._items_by_path[desc.path] = item
        # an inline text field for the variable name (much nicer than a
        # double-click-to-edit cell). Pre-fill from any remembered name.
        if not already:
            edit = QLineEdit()
            edit.setPlaceholderText("variable name (optional)")
            cached = getattr(self, "_name_cache", {}).get(desc.path, "")
            if cached:
                edit.setText(cached)
            self._tree.setItemWidget(item, 1, edit)
            self._name_edits[desc.path] = edit

    def _on_item_changed(self, item, col):
        # auto-expand a group when something inside gets checked (visual aid)
        if col == 0 and item.checkState(0) == Qt.CheckState.Checked:
            p = item.parent()
            while p is not None:
                p.setExpanded(True)
                p = p.parent()

    def _iter_leaves(self):
        from PyQt6.QtWidgets import QTreeWidgetItemIterator
        it = QTreeWidgetItemIterator(self._tree)
        while it.value():
            yield it.value()
            it += 1

    def _accept(self):
        out = []
        existing = getattr(self, "_existing_paths", set())
        seen_names = set(getattr(self, "_existing_names", set()))
        dupes = []
        for path, item in self._items_by_path.items():
            if path in existing:
                continue        # already a variable, don't add again
            try:
                checked = item.checkState(0) == Qt.CheckState.Checked
            except Exception:
                checked = False
            if not checked:
                continue
            desc = self._desc_by_path.get(path)
            if desc is None:
                continue
            edit = self._name_edits.get(path)
            var_name = edit.text().strip() if edit is not None else ""
            key = var_name.lower()
            if var_name and key in seen_names:
                # duplicate name -> flag and collect
                if edit is not None:
                    edit.setStyleSheet("QLineEdit{border:1px solid #c0392b;"
                                       "background:#3a2020}")
                dupes.append(var_name)
                continue
            if var_name:
                seen_names.add(key)
            elif edit is not None:
                edit.setStyleSheet("")
            out.append((desc, var_name))
        if dupes:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Duplicate variable names",
                "These names are already used or duplicated:\n  "
                + "\n  ".join(dupes)
                + "\n\nColumn names must be unique. Rename them and try again.")
            return       # don't accept; let the user fix the names
        self._result = out
        self.accept()

    def chosen_pairs(self):
        """Return a list of (descriptor, var_name) for every checked leaf."""
        return self._result

    # backward-compatible helper used by the simple callers
    def chosen(self):
        descs = [d for d, _ in self._result]
        name = self._result[0][1] if len(self._result) == 1 else ""
        return descs, name


class _LinkObjectsDialog(QDialog):
    """Pick which objects a variable (column) drives. Lists every object across
    the document that the column's attribute can apply to (same attr path), with
    a checkbox per object; the column's current target + extra_targets start
    checked. OK writes the selection back as the primary target + extra_targets.
    This is variant 3: one variable, several objects, linked/unlinked here."""

    def __init__(self, col, pages, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link objects to variable")
        self.resize(460, 520)
        self._col = col
        self._pages = list(pages or [])
        self._rows = []        # (checkbox, page_idx, ObjectRef)

        from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QCheckBox
        lay = QVBoxLayout(self)
        hdr = col.header()
        lay.addWidget(QLabel(
            "Choose which objects the variable \"%s\" drives. Only objects the "
            "attribute (%s) applies to are listed." % (hdr, col.attr_path)))

        self._tree = QTreeWidget()
        self._tree.setColumnCount(1)
        self._tree.setHeaderLabels(["Object"])
        lay.addWidget(self._tree, 1)

        # currently linked refs (as comparable lists)
        cur = {tuple(r.to_list()) for r in col.all_targets()}
        from edof.batch import find_descriptor
        for pi, pg in enumerate(self._pages):
            page_item = QTreeWidgetItem(self._tree, ["Page %d" % (pi + 1)])
            page_item.setFlags(page_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            page_item.setExpanded(True)
            any_here = False
            _is_run_col = str(getattr(self._col, "attr_path", "") or "").startswith("run.")
            for obj in _flatten_targets(pg):
                # only objects this attribute can apply to. v4.3.6.16/.18: a RUN
                # variable can't resolve run.<x> on an arbitrary object (needs a
                # matching rid), so list any TEXT object -- anything that carries
                # runs (INCLUDING the document body, which has runs but no
                # object-level 'text' descriptor) or has a 'text' descriptor.
                # Linking one makes the variable drive its text.
                if _is_run_col:
                    if (getattr(obj, "runs", None) is None
                            and find_descriptor(obj, "text") is None):
                        continue
                    # v4.3.6.20: don't list the object that already HOSTS this
                    # variable (its runs carry the rid). Linking a run variable
                    # onto its own object is a no-op, and in document mode the
                    # body is usually the only object -- so the list now shows
                    # real OTHER objects to target, not the source itself.
                    _rid = getattr(self._col, "run_id", "")
                    if _rid and any(getattr(r, "rid", None) == _rid
                                    for r in (getattr(obj, "runs", None) or [])):
                        continue
                elif find_descriptor(obj, col.attr_path) is None:
                    continue
                ref = build_ref(pg, obj)
                if ref is None:
                    continue
                any_here = True
                otype = getattr(obj, "OBJECT_TYPE", "obj")
                nm = (getattr(obj, "name", "") or "").strip() or otype
                txt = "%s" % nm
                if getattr(obj, "text", None):
                    t = str(obj.text).strip().replace("\n", " ")
                    if t:
                        txt += "  \u2014  %s" % (t[:24])
                it = QTreeWidgetItem(page_item, [txt])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                checked = tuple(ref.to_list()) in cur
                it.setCheckState(0, Qt.CheckState.Checked if checked
                                 else Qt.CheckState.Unchecked)
                self._rows.append((it, pi, ref))
            if not any_here:
                page_item.setHidden(True)

        # v4.3.6.21: for a RUN variable, also let OTHER run variables (strings)
        # be MERGED into this one. Checking a variable gives its span(s) this
        # variable's rid, so a single column drives every one of them -- this is
        # how you drive several strings inside the SAME object with one variable.
        self._var_rows = []   # (item, rid)
        self._merge_rids = []
        _is_run_top = str(getattr(self._col, "attr_path", "") or "").startswith("run.")
        if _is_run_top:
            from PyQt6.QtWidgets import QTreeWidget as _QTW, QTreeWidgetItem as _QTWI
            _prid = getattr(self._col, "run_id", "")
            seen = {}
            var_items = []
            for pi, pg in enumerate(self._pages):
                for obj in _flatten_targets(pg):
                    for r in (getattr(obj, "runs", None) or []):
                        rid = getattr(r, "rid", None)
                        if not rid or rid == _prid or rid in seen:
                            continue
                        seen[rid] = True
                        vn = getattr(r, "var_name", None) or rid
                        pv = (r.text or "").strip().replace("\n", " ")[:24]
                        var_items.append((rid, vn, pv))
            if var_items:
                lay.addWidget(QLabel(
                    "Or LINK other variables to \"%s\": one value then drives "
                    "them all, but every variable KEEPS its own name and panel "
                    "entry. Uncheck to unlink." % hdr))
                vtree = _QTW(); vtree.setColumnCount(1)
                vtree.setHeaderLabels(["Variable"])
                lay.addWidget(vtree, 1)
                _linked = set(getattr(self._col, "extra_run_ids", None) or [])
                for rid, vn, pv in var_items:
                    lbl = vn + ("  \u2014  %s" % pv if pv else "")
                    vit = _QTWI(vtree, [lbl])
                    vit.setFlags(vit.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    vit.setCheckState(0, Qt.CheckState.Checked if rid in _linked
                                      else Qt.CheckState.Unchecked)
                    self._var_rows.append((vit, rid))

        if not self._rows and not self._var_rows:
            empty = QLabel(
                "No other objects or variables to link to.\n\n"
                "The variable already drives its own text. To have it drive "
                "another span, make that span a variable too (or add a text "
                "object), then link it here.")
            empty.setWordWrap(True)
            lay.addWidget(empty)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _accept(self):
        _is_run = str(getattr(self._col, "attr_path", "") or "").startswith("run.")
        chosen = [ref for (it, pi, ref) in self._rows
                  if it.checkState(0) == Qt.CheckState.Checked]
        if _is_run:
            # v4.3.6.20: for a RUN variable the source object (where the variable
            # lives) is the primary target and is no longer listed, so the chosen
            # objects are EXTRA targets. Keep the primary target intact.
            self._col.extra_targets = chosen
            # v4.4.0: collect variables the user chose to LINK. The caller
            # stores them on the column (extra_run_ids); nobody's rid is
            # reassigned and no entity disappears.
            self._merge_rids = [rid for (it, rid) in self._var_rows
                                if it.checkState(0) == Qt.CheckState.Checked]
            self._link_selection_final = True
            self.accept()
            return
        # non-run column: the source IS listed; first chosen is the primary
        # target, the rest are extra targets.
        if not chosen:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Link objects",
                                "Select at least one object for the variable.")
            return
        self._col.target = chosen[0]
        self._col.extra_targets = chosen[1:]
        self.accept()


class EdofBatchTemplatePanel(QWidget):
    """Template (authoring) editor, laid out VERTICALLY for the narrow
    right-side tab (about the width of Properties). Top: a row list with record
    navigation (previous / next / duplicate / new / delete). Middle: the value
    list for the selected row -- one labelled field per column with type-aware
    editors. Bottom: a live preview.

    Standalone like EdofBatchPanel: it binds to the document and edits the same
    live ``doc.batch``, so it stays in sync with the table editor in the bottom
    dock. No table here -- that is the bottom dock's job."""

    changed = pyqtSignal()

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._editor = parent       # the EdofEditor (for toolbar sync)
        self._doc = None
        self._cur = 0
        self._building = False
        self._preview_page = 0
        self._last_preview_pixmap = None
        self._canvas_preview_on = True       # project selected record to canvas

        from PyQt6.QtWidgets import QListWidget, QFormLayout, QScrollArea
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── row set + scope (compact, stacked) ──
        top = QHBoxLayout()
        top.addWidget(QLabel("Mode:"))
        self._scope = QComboBox()
        self._scope.addItem("Page per row", "page")
        self._scope.addItem("Whole document per row", "document")
        self._scope.currentIndexChanged.connect(self._on_scope_changed)
        top.addWidget(self._scope, 1)
        root.addLayout(top)

        top2 = QHBoxLayout()
        top2.addWidget(QLabel("Rows:"))
        self._rowset = QComboBox()
        self._rowset.addItem("Production", "rows")
        self._rowset.addItem("Demo (template)", "demo")
        self._rowset.currentIndexChanged.connect(lambda *_: self.rebuild())
        top2.addWidget(self._rowset, 1)
        root.addLayout(top2)

        # ── record list ──
        root.addWidget(QLabel("Records:"))
        self._rows = QListWidget()
        self._rows.setMaximumHeight(130)
        self._rows.currentRowChanged.connect(self._on_row_selected)
        root.addWidget(self._rows)

        # ── record navigation: prev / next / duplicate / new / delete ──
        nav = QHBoxLayout()
        b_prev = QPushButton("‹ Prev")
        b_next = QPushButton("Next ›")
        b_prev.clicked.connect(lambda: self._step_record(-1))
        b_next.clicked.connect(lambda: self._step_record(1))
        nav.addWidget(b_prev)
        nav.addWidget(b_next)
        root.addLayout(nav)
        nav2 = QHBoxLayout()
        b_dup = QPushButton("Duplicate")
        b_new = QPushButton("New")
        b_del = QPushButton("Delete")
        b_dup.clicked.connect(self._dup_record)
        b_new.clicked.connect(self._new_record)
        b_del.clicked.connect(self._del_record)
        nav2.addWidget(b_dup)
        nav2.addWidget(b_new)
        nav2.addWidget(b_del)
        root.addLayout(nav2)

        # ── record controls (v4.3.5.10) ──
        # While recording, edits on the canvas are captured into the selected
        # record: changed attributes become columns automatically and their
        # values are written to this record, until you stop.
        recrow = QHBoxLayout()
        self._btn_record = QPushButton("● Record edits")
        self._btn_record.setCheckable(True)
        self._btn_record.toggled.connect(self._on_toggle_record)
        self._btn_record.setToolTip(
            "Record canvas edits into the selected record. Changed attributes "
            "become columns automatically.")
        recrow.addWidget(self._btn_record)
        root.addLayout(recrow)
        self._lbl_record = QLabel("")
        self._lbl_record.setStyleSheet("QLabel{color:#c44;font-size:10px}")
        root.addWidget(self._lbl_record)
        self._recording = False
        self._record_baseline = None     # deep copy of doc at record start
        self._record_row_idx = None

        # ── value list (scrollable) ──
        # v4.3.5.29: red warning shown when an effect variable exists without a
        # master 'effects enabled' variable -- effects won't render without it.
        self._fx_warn = QLabel("")
        self._fx_warn.setWordWrap(True)
        self._fx_warn.setStyleSheet(
            "QLabel{color:#c0392b;background:#3a2020;border:1px solid #c0392b;"
            "border-radius:3px;padding:4px;font-size:10px}")
        self._fx_warn.setVisible(False)
        root.addWidget(self._fx_warn)
        self._shared_targets = []   # v4.3.6.14: variables selected in the panel
        root.addWidget(QLabel("Values:"))
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._form_host = QWidget()
        self._form = QFormLayout(self._form_host)
        self._scroll.setWidget(self._form_host)
        root.addWidget(self._scroll, 1)

        # ── add variable (same as adding a column) ──
        self._btn_add_var = QPushButton("Add variable…")
        self._btn_add_var.clicked.connect(self._on_add_variable)
        root.addWidget(self._btn_add_var)

        # v4.3.5.9: the per-panel preview is gone. The selected record is now
        # projected non-destructively onto the MAIN canvas instead, so there is
        # a single preview (the canvas itself). A small live/base toggle lets
        # you flip the canvas between the selected record and the base document.
        self._btn_show_on_canvas = QPushButton("Show selected on canvas")
        self._btn_show_on_canvas.setCheckable(True)
        self._btn_show_on_canvas.setChecked(True)
        self._btn_show_on_canvas.toggled.connect(self._on_toggle_canvas_preview)
        self._btn_show_on_canvas.setToolTip(
            "Project the selected record onto the main canvas (non-destructive). "
            "Disabled while recording, since you're editing live.")
        root.addWidget(self._btn_show_on_canvas)
        self._update_show_on_canvas_style()
        root.addStretch(0)

    # ── binding / model ──
    def set_document(self, doc):
        self._doc = doc
        self.rebuild()

    def _cfg(self):
        return self._doc.batch if self._doc is not None else None

    def _pages(self):
        return list(getattr(self._doc, "pages", []) or []) if self._doc else []

    def _page_scope(self):
        cfg = self._cfg()
        return cfg is not None and cfg.row_scope == "page"

    def _show_page_col(self):
        return self._page_scope() and len(self._pages()) > 1

    def _rows_list(self):
        cfg = self._cfg()
        if cfg is None:
            return []
        if self._rowset.currentData() == "demo":
            return cfg.demo_rows
        return cfg.rows

    def _active_page(self):
        return int(getattr(self._canvas, "_page_idx", 0) or 0)

    # ── descriptor helpers (shared logic with the table panel) ──
    def _column_label(self, col):
        if col.var_name.strip():
            return col.var_name.strip()
        attr = col.attr_path.replace(".", "-")
        for pg in self._pages():
            obj = resolve_ref(pg, col.target)
            if obj is None:
                continue
            otype = getattr(obj, "OBJECT_TYPE", "obj")
            base = (getattr(obj, "name", "") or "").strip() or otype
            same = [o for o in getattr(pg, "objects", [])
                    if getattr(o, "OBJECT_TYPE", None) == otype]
            n = 1
            for i, o in enumerate(same, start=1):
                if getattr(o, "id", None) == getattr(obj, "id", None):
                    n = i
                    break
            if base == otype:
                return f"{base}-{n}.{attr}"
            return f"{base}.{attr}"
        return col.attr_path

    def _first_object_for_column(self, col):
        for pg in self._pages():
            obj = resolve_ref(pg, col.target)
            if obj is not None:
                return obj
        return None

    def _data_name(self, col):
        """The non-editable data name shown under the variable label; this is
        the auto <type>-<N>.<attr> path, regardless of any custom var name."""
        attr = col.attr_path.replace(".", "-")
        for pg in self._pages():
            obj = resolve_ref(pg, col.target)
            if obj is None:
                continue
            otype = getattr(obj, "OBJECT_TYPE", "obj")
            base = (getattr(obj, "name", "") or "").strip() or otype
            same = [o for o in getattr(pg, "objects", [])
                    if getattr(o, "OBJECT_TYPE", None) == otype]
            n = 1
            for i, o in enumerate(same, start=1):
                if getattr(o, "id", None) == getattr(obj, "id", None):
                    n = i
                    break
            if base == otype:
                return f"{base}-{n}.{attr}"
            return f"{base}.{attr}"
        return col.attr_path

    # ── rebuild ──
    def rebuild(self):
        cfg = self._cfg()
        self._building = True
        try:
            # reflect scope
            want = 0 if (cfg and cfg.row_scope == "page") else 1
            if self._scope.currentIndex() != want:
                self._scope.blockSignals(True)
                self._scope.setCurrentIndex(want)
                self._scope.blockSignals(False)

            self._rows.clear()
            rows = self._rows_list()
            for i, row in enumerate(rows):
                label = row.name.strip() if row.name.strip() else f"Record {i + 1}"
                if getattr(row, "locked", False):
                    label = "🔒 " + label
                self._rows.addItem(label)
            if rows:
                self._cur = max(0, min(self._cur, len(rows) - 1))
                self._rows.setCurrentRow(self._cur)
            self._build_form()
            self._update_fx_warning()
        finally:
            self._building = False
        # if a table peer is bound, keep it in sync (same model). Guard with a
        # dedicated flag so the peer's rebuild doesn't call back into ours and
        # ping-pong (which made every rebuild fire hundreds of times).
        if not getattr(self, "_syncing_peer", False):
            tp = getattr(self, "_table_peer", None)
            if tp is not None:
                self._syncing_peer = True
                try: tp.rebuild()
                except Exception: pass
                finally: self._syncing_peer = False
        # NOTE: rebuild intentionally does NOT project to the canvas. Projection
        # triggers a full page re-render, which is expensive; doing it on every
        # rebuild made switching row sets / binding feel frozen. Projection
        # happens only when the selected record actually changes (row selection
        # or a value edit).

    def _update_fx_warning(self):
        """Show a red warning when there's an effect variable but no master
        'effects enabled' (all_enabled) variable for the same object -- effects
        won't render without the master being turned on. Per request, the panel
        warns instead of silently flipping the master."""
        if getattr(self, "_fx_warn", None) is None:
            return
        cfg = self._cfg()
        if cfg is None:
            self._fx_warn.setVisible(False)
            return
        # objects that have an effect variable but no all_enabled variable
        eff_objs = {}     # obj-ref-key -> has effect var
        master_objs = set()
        for c in cfg.columns:
            path = c.attr_path or ""
            if not path.startswith("effects."):
                continue
            for ref in c.all_targets():
                key = tuple(ref.to_list())
                if path == "effects.all_enabled":
                    master_objs.add(key)
                else:
                    eff_objs[key] = True
        missing = [k for k in eff_objs if k not in master_objs]
        # of those, only warn for objects whose master isn't already on
        really_missing = []
        for key in missing:
            obj = None
            for pg in self._pages():
                for o in _flatten_targets(pg):
                    r = build_ref(pg, o)
                    if r is not None and tuple(r.to_list()) == key:
                        obj = o
                        break
                if obj is not None:
                    break
            if obj is not None and not getattr(obj, "effects_enabled", False):
                really_missing.append(key)
        if really_missing:
            n = len(really_missing)
            self._fx_warn.setText(
                "\u26a0  %d object%s ha%s an effect variable but no \u201ceffects "
                "enabled\u201d (master) variable. Effects won't show until the "
                "master is on \u2014 add an \u201cAll effects\u201d variable and set it "
                "true." % (n, "s" if n != 1 else "", "ve" if n != 1 else "s"))
            self._fx_warn.setVisible(True)
        else:
            self._fx_warn.setVisible(False)

    def _build_form(self):
        from PyQt6.QtWidgets import QLineEdit, QWidget as _QW, QVBoxLayout as _QV
        while self._form.rowCount():
            self._form.removeRow(0)
        cfg = self._cfg()
        rows = self._rows_list()
        if cfg is None or not rows:
            return
        if not (0 <= self._cur < len(rows)):
            return
        row = rows[self._cur]

        # row name
        name_edit = QLineEdit(row.name or "")
        name_edit.textEdited.connect(lambda t: self._set_name(t))
        self._form.addRow("Name", name_edit)

        # page target (only when meaningful)
        if self._show_page_col():
            page_edit = QLineEdit(_page_target_to_display(row.page_target))
            page_edit.setPlaceholderText("page # or 'crosspage'")
            page_edit.textEdited.connect(lambda t: self._set_page(t))
            self._form.addRow("Page", page_edit)

        # one block per column: editable variable name, non-editable data name,
        # the value editor, and a "remove variable" button
        for col in cfg.columns:
            block = _QW()
            bl = _QV(block)
            bl.setContentsMargins(0, 0, 0, 6)
            bl.setSpacing(1)
            # editable variable name (what goes to CSV when set)
            var_edit = QLineEdit(col.var_name)
            var_edit.setPlaceholderText("variable name (optional)")
            var_edit.textEdited.connect(
                lambda t, c=col, e=var_edit: self._set_var_name(c, t, e))
            bl.addWidget(var_edit)
            # non-editable data name (not written to CSV when a name is set);
            # show the object count when the variable drives more than one
            n_tg = len(col.all_targets())
            dn_txt = self._data_name(col)
            if n_tg > 1:
                dn_txt += "   (%d objects)" % n_tg
            dn = QLabel(dn_txt)
            dn.setStyleSheet("QLabel{color:#888;font-size:10px}")
            bl.addWidget(dn)
            # the value editor + link-objects + remove-variable buttons
            valrow = QHBoxLayout()
            valrow.setContentsMargins(0, 0, 0, 0)
            field = self._make_field(col, row)
            valrow.addWidget(field, 1)
            b_link = QPushButton("\U0001F517")      # link symbol
            b_link.setFixedWidth(26)
            b_link.setToolTip("Link this variable to one or more objects")
            b_link.clicked.connect(lambda _=False, c=col: self._link_objects(c))
            valrow.addWidget(b_link)
            b_rm = QPushButton("\u2715")
            b_rm.setFixedWidth(26)
            b_rm.setToolTip("Remove this variable (column)")
            b_rm.clicked.connect(lambda _=False, c=col: self._remove_variable(c))
            valrow.addWidget(b_rm)
            bl.addLayout(valrow)
            self._form.addRow(block)

    def _make_field(self, col, row):
        from PyQt6.QtWidgets import QLineEdit, QComboBox, QPushButton, QWidget
        val = row.values.get(col.column_id, "")
        val = "" if val is None else str(val)
        locked = getattr(row, "locked", False)

        if col.kind == "enum":
            cb = QComboBox()
            obj = self._first_object_for_column(col)
            choices = []
            # v4.3.6.18: a run bool attr (bold/italic/underline/strikethrough)
            # has no object-level descriptor (it needs a run_id), so
            # find_descriptor returned None and the dropdown came up empty --
            # nothing could be set. Use the known true/false choices for run
            # enums.
            _ap = str(getattr(col, "attr_path", "") or "")
            if _ap.startswith("run."):
                try:
                    from edof.batch import _RUN_ENUM_CHOICES
                    choices = _RUN_ENUM_CHOICES.get(_ap.split(".", 1)[1], [])
                except Exception:
                    choices = []
            if not choices and obj is not None:
                desc = find_descriptor(obj, col.attr_path)
                choices = desc.choices if desc else []
            cb.addItems([str(c) for c in choices])
            i = cb.findText(val)
            if i >= 0:
                cb.setCurrentIndex(i)
            cb.setEnabled(not locked)
            cb.currentTextChanged.connect(
                lambda t, ci=col.column_id: self._set_val(ci, t))
            return cb

        if col.kind in ("color", "file_path"):
            host = QWidget()
            h = QHBoxLayout(host)
            h.setContentsMargins(0, 0, 0, 0)
            le = QLineEdit(val)
            le.setEnabled(not locked)
            # v4.3.6.18: current value as greyed placeholder when no override set
            _cur = self._current_run_value(col)
            if _cur and not val:
                le.setPlaceholderText(_cur)
            le.textEdited.connect(lambda t, ci=col.column_id: self._set_val(ci, t))
            if col.kind == "color":
                self._tint_lineedit(le, val)
                le.textChanged.connect(lambda t, w=le: self._tint_lineedit(w, t))
            btn = QPushButton("…")
            btn.setFixedWidth(28)
            btn.setEnabled(not locked)
            btn.clicked.connect(
                lambda _=False, ci=col.column_id, k=col.kind, w=le:
                self._pick(ci, k, w))
            h.addWidget(le, 1)
            h.addWidget(btn)
            return host

        if col.attr_path in ("style.font_family", "run.font_family"):
            # v4.3.5.29: a real font picker instead of a free-text field.
            # v4.3.6.18: also for run.font_family (a run-level font variable),
            # which used to fall through to the plain text field (no dropdown).
            from PyQt6.QtWidgets import QFontComboBox
            fc = QFontComboBox()
            fc.setEnabled(not locked)
            if val:
                from PyQt6.QtGui import QFont
                fc.setCurrentFont(QFont(val))
            fc.currentFontChanged.connect(
                lambda f, ci=col.column_id: self._set_val(ci, f.family()))
            return fc

        # v4.3.5.33: default editor for number / text / anything else. This
        # fallthrough lost its body in 4.3.5.29 (the QLineEdit was created but
        # never wired up or returned), so number and plain-text variables had no
        # editable field in the right panel -- the bug David hit with height.
        le = QLineEdit(val)
        le.setEnabled(not locked)
        # v4.3.6.18: show the run's CURRENT value as greyed placeholder text when
        # no override is set, so the user sees what they'd be changing.
        _cur = self._current_run_value(col)
        if _cur and not val:
            le.setPlaceholderText(_cur)
        le.textEdited.connect(lambda t, ci=col.column_id: self._set_val(ci, t))
        return le

    def _current_run_value(self, col):
        """v4.3.6.18: the run's current value for this column's attribute as a
        string, used as placeholder text. Empty when not a run column or the run
        isn't found."""
        rid = getattr(col, "run_id", "")
        ap = str(getattr(col, "attr_path", "") or "")
        if not rid or not ap.startswith("run."):
            return ""
        field = ap.split(".", 1)[1]
        obj = self._first_object_for_column(col)
        if obj is None:
            return ""
        for r in (getattr(obj, "runs", None) or []):
            if getattr(r, "rid", None) == rid:
                v = getattr(r, field, None)
                if v not in (None, ""):
                    return str(v)
                break
        return ""

    def _tint_lineedit(self, le, text):
        qc = _parse_color(text)
        if qc is not None:
            lum = 0.299 * qc.red() + 0.587 * qc.green() + 0.114 * qc.blue()
            fg = "#000000" if lum > 140 else "#ffffff"
            le.setStyleSheet("QLineEdit{background:%s;color:%s}" % (qc.name(), fg))
        else:
            le.setStyleSheet("")

    # ── editing callbacks ──
    def _row(self):
        rows = self._rows_list()
        if 0 <= self._cur < len(rows):
            return rows[self._cur]
        return None

    def _locked(self):
        r = self._row()
        return bool(getattr(r, "locked", False)) if r else False

    def _set_name(self, text):
        r = self._row()
        if r is None or getattr(r, "locked", False):
            return
        r.name = text.strip()
        it = self._rows.item(self._cur)
        if it is not None:
            it.setText(text.strip() or f"Record {self._cur + 1}")
        self._refresh_preview_current()
        self.changed.emit()

    def _set_page(self, text):
        r = self._row()
        if r is None or getattr(r, "locked", False):
            return
        r.page_target = _display_to_page_target(text)
        self._refresh_preview_current()
        self.changed.emit()

    def _set_val(self, col_id, text):
        r = self._row()
        if r is None or getattr(r, "locked", False):
            _blog("tpl._set_val SKIP", reason="no row or locked", col_id=col_id)
            return
        r.values[col_id] = text
        _blog("tpl._set_val", col_id=col_id, text=text, cur=self._cur,
              preview_on=getattr(self, "_canvas_preview_on", None),
              recording=getattr(self, "_recording", False))
        self._refresh_preview_current()
        self.changed.emit()

    def _set_var_name(self, col, text, editor=None):
        cfg = self._cfg()
        new = text.strip()
        if _header_in_use(cfg, new, exclude_col_id=col.column_id):
            # duplicate header: reject (don't store), flag the field red
            if editor is not None:
                editor.setStyleSheet("QLineEdit{border:1px solid #c0392b;"
                                     "background:#3a2020}")
                editor.setToolTip("A variable with this name already exists. "
                                  "Column names must be unique.")
            return
        if editor is not None:
            editor.setStyleSheet("")
            editor.setToolTip("")
        col.var_name = new
        self.changed.emit()

    def _link_objects(self, col):
        """Open the link-objects dialog for a variable, then rebuild so the
        object count and previews reflect the new target set."""
        pages = list(self._pages())
        if not pages:
            return
        dlg = _LinkObjectsDialog(col, pages, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cfg = self._cfg()
            # v4.3.6.21: fold in any variables the user chose to merge into this
            # one (their spans take this variable's rid; their columns are
            # dropped) so a single column drives them all. Undoable.
            merge_rids = getattr(dlg, "_merge_rids", None) or []
            if merge_rids or (getattr(col, "extra_run_ids", None) or []):
                # v4.4.0: LINK, not fold. Every variable keeps its rid, name
                # and panel entry; the column simply fills the linked rids too.
                # Unchecking removes the link. Columns of the SAME attribute
                # bound to a newly linked rid are dropped (they would fight
                # over the same span).
                self._history_begin()
                col.extra_run_ids = list(merge_rids)
                if cfg is not None and merge_rids:
                    for cid in [c.column_id for c in list(cfg.columns)
                                if c.column_id != col.column_id
                                and getattr(c, "run_id", "") in set(merge_rids)
                                and c.attr_path == col.attr_path]:
                        try: cfg.remove_column(cid)
                        except Exception: pass
                cv = self._canvas
                if cv is not None:
                    try:
                        if hasattr(cv, "_reflow_current_body"):
                            cv._reflow_current_body()
                    except Exception: pass
                    try: cv.objectChanged.emit()
                    except Exception: pass
                    try: cv.schedule_render(0)
                    except Exception: pass
                ed2 = getattr(self, "_editor", None)
                st = getattr(ed2, "_status", None)
                if st is not None:
                    try:
                        st.showMessage(
                            "Linked %d variable(s) to \"%s\" (each keeps its "
                            "identity)" % (len(merge_rids), col.var_name), 4000)
                    except Exception:
                        pass
            # any record cells that don't yet have a value for this column
            if cfg is not None:
                obj = self._first_object_for_column(col)
                if obj is not None:
                    desc = find_descriptor(obj, col.attr_path)
                    if desc is not None:
                        self._seed_new_column(cfg, col, desc, obj)
            self.rebuild()
            # re-project the current row so the newly linked objects update on
            # the canvas immediately (not just after the next row change)
            self._refresh_preview_current()
            self.changed.emit()
            if merge_rids:
                self._history_end("Merge variables")

    def _existing_text_variables(self):
        """v4.3.6.21: existing variables as (rid, var_name), unique by rid. A new
        selection can be added to one of them -- the same rid on several spans
        means one batch value fills every occurrence in the object."""
        seen = {}
        doc = self._doc
        if doc is not None:
            for pg in (getattr(doc, "pages", None) or []):
                for obj in _flatten_targets(pg):
                    for r in (getattr(obj, "runs", None) or []):
                        rid = getattr(r, "rid", None)
                        if rid and rid not in seen:
                            seen[rid] = (getattr(r, "var_name", None) or rid)
        return list(seen.items())

    def _all_used_var_names(self):
        """v4.3.6.20: every variable name in use -- both batch column names AND
        var_names sitting on runs. A no-attribute variable has no column, so
        counting columns alone produced duplicate default names ('inlinetext01'
        twice). Returns a set of lowercased names."""
        names = set()
        cfg = self._cfg()
        for c in (cfg.columns if cfg else []):
            vn = (getattr(c, "var_name", "") or "").strip().lower()
            if vn:
                names.add(vn)
        doc = self._doc
        if doc is not None:
            for pg in (getattr(doc, "pages", None) or []):
                for obj in _flatten_targets(pg):
                    for r in (getattr(obj, "runs", None) or []):
                        vn = (getattr(r, "var_name", "") or "").strip().lower()
                        if vn:
                            names.add(vn)
        return names

    # ── v4.3.6.28: history + inline-copy helpers ─────────────────────────────

    def _history_begin(self):
        """v4.3.6.28: flush pending edit bursts so the committed pre-state sits
        on top of the undo stack before a batch-variable op mutates anything
        (no duplicate snapshot, no lost step)."""
        ed = getattr(self, "_editor", None)
        if ed is None:
            return
        for m in ("_commit_pending_body", "_commit_pending_obj"):
            fn = getattr(ed, m, None)
            if fn is not None:
                try: fn()
                except Exception: pass

    def _history_end(self, desc):
        """v4.3.6.28: commit the op as ONE undo step. Cancels the burst our own
        objectChanged emit scheduled (it would duplicate the snapshot and cost a
        dead Ctrl+Z press) and pushes the post-state with a proper label."""
        ed = getattr(self, "_editor", None)
        if ed is None or not hasattr(ed, "push_history"):
            return
        try:
            ed._obj_pending = False
            t = getattr(ed, "_obj_commit_timer", None)
            if t is not None:
                t.stop()
        except Exception:
            pass
        try: ed.push_history(desc)
        except Exception: pass

    def _mirror_rid_edit_to_inline(self, rids, fn):
        """v4.3.6.28: apply a rid-level edit (clear, rename) to the OPEN inline
        editor's run copy too. Without this the next reflow refreshes the page
        box FROM the stale copy and resurrects the old rid/var_name (same class
        of bug as the 4.3.6.23 merge fix)."""
        cv = self._canvas
        ied = getattr(cv, "_inline_widget", None) if cv is not None else None
        if ied is None:
            return
        changed = False
        for r in (getattr(ied, "_runs", None) or []):
            if getattr(r, "rid", None) in rids:
                try:
                    fn(r)
                    changed = True
                except Exception:
                    pass
        if changed:
            try: ied.sync_to_tb_silent()
            except Exception: pass
            try: ied._invalidate()
            except Exception: pass

    def _clear_run_var_in_document(self, run_id):
        """v4.3.6.18: strip rid + var_name from every run that carries this
        run_id, across all pages (a run variable can be linked to several
        objects). Used when removing a run variable so its rainbow highlight and
        its Objects-panel entry disappear too."""
        if not run_id:
            return
        doc = self._doc
        if doc is None:
            return
        for pg in (getattr(doc, "pages", None) or []):
            for obj in _flatten_targets(pg):
                for r in (getattr(obj, "runs", None) or []):
                    if getattr(r, "rid", None) == run_id:
                        try:
                            r.rid = None
                            r.var_name = None
                        except Exception:
                            pass
        # v4.4.0: clear the rid on the header/footer TEMPLATE runs too, or the
        # next repagination re-creates the per-page clones WITH the rid.
        for r in _iter_hf_template_runs(doc):
            if getattr(r, "rid", None) == run_id:
                try:
                    r.rid = None
                    r.var_name = None
                except Exception:
                    pass
        # v4.3.6.28: the open inline editor holds a COPY of the runs; clear the
        # rid there too or the reflow resurrects the variable from the copy.
        def _clr(r):
            r.rid = None
            r.var_name = None
        self._mirror_rid_edit_to_inline({run_id}, _clr)

    def rename_run_variable(self, targets, new_name):
        """v4.3.6.20: rename a run-variable entity -- update var_name on its runs
        and on its batch columns (keeping the attribute suffix for non-text
        columns). Undoable."""
        new_name = (new_name or "").strip()
        if not new_name:
            return
        rids = {rid for (_o, rid) in (targets or []) if rid}
        if not rids:
            return
        # v4.4.0: column names must be unique. If the wanted name collides
        # with a column that is NOT part of this variable, auto-suffix it
        # (new_name_2, ...) instead of silently creating a duplicate.
        cfg0 = self._cfg()
        if cfg0 is not None:
            own_ids = {c.column_id for c in cfg0.columns
                       if getattr(c, "run_id", "") in rids}
            def _taken(nm):
                return any(c.header().strip().lower() == nm.strip().lower()
                           for c in cfg0.columns
                           if c.column_id not in own_ids)
            if _taken(new_name):
                base = new_name
                n = 2
                while _taken(new_name):
                    new_name = "%s_%d" % (base, n)
                    n += 1
        self._history_begin()
        doc = self._doc
        if doc is not None:
            for pg in (getattr(doc, "pages", None) or []):
                for obj in _flatten_targets(pg):
                    for r in (getattr(obj, "runs", None) or []):
                        if getattr(r, "rid", None) in rids:
                            try: r.var_name = new_name
                            except Exception: pass
        # v4.4.0: rename on the header/footer TEMPLATE runs too
        for r in _iter_hf_template_runs(doc):
            if getattr(r, "rid", None) in rids:
                try: r.var_name = new_name
                except Exception: pass
        # v4.3.6.28: rename in the inline editor's copy too (see mirror helper)
        def _ren(r):
            r.var_name = new_name
        self._mirror_rid_edit_to_inline(rids, _ren)
        cfg = self._cfg()
        if cfg is not None:
            for c in cfg.columns:
                if getattr(c, "run_id", "") in rids:
                    if getattr(c, "attr_path", "") == "run.text":
                        c.var_name = new_name
                    else:
                        field = str(getattr(c, "attr_path", "") or "").split(".")[-1]
                        cand = "%s_%s" % (new_name, field) if field else new_name
                        c.var_name = cfg.unique_header(
                            cand, exclude_column_id=c.column_id)
        cv = self._canvas
        if cv is not None:
            try:
                if hasattr(cv, "_reflow_current_body"):
                    cv._reflow_current_body()
            except Exception:
                pass
            try: cv.objectChanged.emit()
            except Exception: pass
            try: cv.schedule_render(0)
            except Exception: pass
        self.rebuild()
        self.changed.emit()
        self._history_end("Rename variable")

    def change_run_variable_range(self, _obj, rid):
        """v4.3.6.28: re-span an existing variable: the CURRENT selection in
        the inline editor becomes the variable's new range. The rid (and with
        it every batch column and record value) is kept; runs outside the new
        selection lose it. Entry: Objects panel context menu on a variable."""
        cv = self._canvas
        ied = getattr(cv, "_inline_widget", None) if cv is not None else None
        if ied is None or not ied._has_selection():
            QMessageBox.information(
                self, "Change range",
                "Select the new text range in the editor first (double click "
                "the text box, select the text), then run Change range again.")
            return
        if not rid:
            return
        # keep the current name: look on the page objects, then the inline copy
        vname = None
        doc = self._doc
        for pg in (getattr(doc, "pages", None) or []) if doc is not None else []:
            for o in _flatten_targets(pg):
                for r in (getattr(o, "runs", None) or []):
                    if getattr(r, "rid", None) == rid:
                        vname = getattr(r, "var_name", None) or vname
        for r in (getattr(ied, "_runs", None) or []):
            if getattr(r, "rid", None) == rid:
                vname = getattr(r, "var_name", None) or vname
        self._history_begin()
        # strip the old span(s) everywhere (page objects AND the inline copy,
        # via the mirror in _clear_run_var_in_document), then re-apply the SAME
        # rid to the selection. Columns stay bound, values survive.
        self._clear_run_var_in_document(rid)
        new_rid = ied.make_variable_from_selection(vname or "", rid=rid)
        if not new_rid:
            return
        try: ied.sync_to_tb_silent()
        except Exception: pass
        try: cv._commit_hf_runs_from_inline()
        except Exception: pass
        if cv is not None:
            try:
                if hasattr(cv, "_reflow_current_body"):
                    cv._reflow_current_body()
            except Exception:
                pass
            try:
                if hasattr(cv, "clear_object_cache"):
                    cv.clear_object_cache()
            except Exception:
                pass
            try: cv.objectChanged.emit()
            except Exception: pass
            try: cv.schedule_render(0)
            except Exception: pass
        self.rebuild()
        self.changed.emit()
        self._history_end("Change variable range")

    def remove_run_variable(self, targets):
        """v4.3.6.19: delete run-variable ENTITIES. For each (obj, rid) target,
        strip the rid/var_name from the runs AND drop every batch column bound to
        that rid. Undoable. Used by the Objects-panel 'Remove variable' action
        and by the auto-cleanup when a variable's text is fully deleted."""
        rids = {rid for (_o, rid) in (targets or []) if rid}
        if not rids:
            return
        cfg = self._cfg()
        self._history_begin()
        if cfg is not None:
            for cid in [c.column_id for c in list(cfg.columns)
                        if getattr(c, "run_id", "") in rids]:
                cfg.remove_column(cid)
        for rid in rids:
            self._clear_run_var_in_document(rid)
        cv = self._canvas
        if cv is not None:
            try:
                if hasattr(cv, "_reflow_current_body"):
                    cv._reflow_current_body()
            except Exception:
                pass
            try: cv.objectChanged.emit()
            except Exception: pass
            try: cv.schedule_render(0)
            except Exception: pass
        self.rebuild()
        self.changed.emit()
        self._history_end("Remove variable")

    def _remove_variable(self, col):
        cfg = self._cfg()
        if cfg is None:
            return
        # confirm: deleting a variable drops the column and its data in every
        # record, so it must not be a one-click action
        label = self._column_label(col)
        n_with_data = sum(1 for r in (cfg.rows + cfg.demo_rows)
                          if r.values.get(col.column_id) not in (None, ""))
        msg = "Remove variable \"%s\"?" % label
        if n_with_data:
            msg += "\n\nThis also clears its value in %d record(s)." % n_with_data
        msg += "\n\nYou can undo this (Ctrl+Z)."
        reply = QMessageBox.question(
            self, "Remove variable", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        # flush pending bursts so undo restores the column + its data cleanly
        self._history_begin()
        cfg.remove_column(col.column_id)
        # v4.3.6.18: a run variable also lives as rid/var_name ON the runs. The
        # rainbow and the Objects-panel entry come from those, not from the
        # column, so removing the column alone left the variable highlighted and
        # still listed. Strip the rid/var_name from every run that carries it
        # (across all pages, since a run variable can be linked to several
        # objects), then reflow + refresh so the highlight and the panel update.
        _rid = getattr(col, "run_id", "")
        if _rid and str(getattr(col, "attr_path", "") or "").startswith("run."):
            self._clear_run_var_in_document(_rid)
            cv = self._canvas
            if cv is not None:
                try:
                    if hasattr(cv, "_reflow_current_body"):
                        cv._reflow_current_body()
                except Exception:
                    pass
                try: cv.objectChanged.emit()
                except Exception: pass
                try: cv.schedule_render(0)
                except Exception: pass
        # record the new state as ONE labelled step (no burst duplicate)
        self.rebuild()
        self.changed.emit()
        self._history_end("Remove variable")

    def _pick(self, col_id, kind, line_edit):
        if self._locked():
            return
        if kind == "color":
            hexv = _pick_color_standard(self, line_edit.text())
            if hexv is not None:
                line_edit.setText(hexv)
                self._set_val(col_id, hexv)
        else:
            path, _f = QFileDialog.getOpenFileName(
                self, "Choose file", "",
                "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;All files (*)")
            if path:
                line_edit.setText(path)
                self._set_val(col_id, path)

    # ── record navigation ──
    def _on_row_selected(self, idx):
        if self._building or idx < 0:
            return
        self._cur = idx
        self._build_form()
        self._refresh_preview_current()

    def _step_record(self, delta):
        rows = self._rows_list()
        if not rows:
            return
        self._cur = max(0, min(self._cur + delta, len(rows) - 1))
        self._rows.setCurrentRow(self._cur)

    def _new_record(self):
        cfg = self._cfg()
        if cfg is None:
            return
        pt = 0 if cfg.row_scope == "page" else None
        self._rows_list().append(BatchRow(page_target=pt, values={}))
        self._cur = len(self._rows_list()) - 1
        self.rebuild()
        self.changed.emit()

    def _dup_record(self):
        import copy as _c
        rows = self._rows_list()
        if not (0 <= self._cur < len(rows)):
            return
        src = rows[self._cur]
        clone = BatchRow(page_target=src.page_target,
                         values=_c.deepcopy(src.values),
                         name=(src.name + " copy") if src.name else "")
        rows.insert(self._cur + 1, clone)
        self._cur += 1
        self.rebuild()
        self.changed.emit()

    def _del_record(self):
        rows = self._rows_list()
        if 0 <= self._cur < len(rows):
            rows.pop(self._cur)
            self._cur = max(0, self._cur - 1)
            self.rebuild()
            self.changed.emit()

    def _on_scope_changed(self, *_):
        cfg = self._cfg()
        if cfg is None:
            return
        cfg.row_scope = self._scope.currentData()
        self.rebuild()
        self.changed.emit()

    def _on_add_variable(self):
        """Add a column/variable -- same flow as the table's 'Add column'."""
        # v4.3.6.2: if a span of text is selected in the inline editor, the user
        # means "make THIS text a variable" -- offer the run's attributes (text,
        # font size, colour, bold, italic), not the body object's transform
        # (rotating the whole body via a variable is nonsense). Falls through to
        # the object flow when there's no text selection.
        ed = getattr(self._canvas, "_inline_widget", None)
        if ed is not None and hasattr(ed, "_has_selection") and ed._has_selection():
            self._add_text_variable(ed)
            return
        obj = self._selected_object()
        if obj is None:
            QMessageBox.information(
                self, "Add variable",
                "Select an object on the canvas first.")
            return
        _existing = _existing_paths_for_object(self._cfg(), obj, list(self._pages()))
        _names = list(self._all_used_var_names())   # v4.3.6.20: include run var_names
        _extra = [o for o in self._selected_objects() if o is not obj]
        dlg = _AddColumnDialog(obj, self, existing_paths=_existing,
                               existing_names=_names, extra_objs=_extra)
        dlg_code = dlg.exec()
        # the effect-reorder list writes order to the object live, so reflect it
        # even if the dialog was cancelled
        if getattr(dlg, "_reordered", False):
            try: self._canvas.schedule_render(0)
            except Exception: pass
            self.changed.emit()
        if dlg_code == QDialog.DialogCode.Accepted:
            pairs = dlg.chosen_pairs()
            cfg = self._cfg()
            page = self._canvas._cur_page() if hasattr(self._canvas, "_cur_page") else None
            if page is None:
                for pg in self._pages():
                    if build_ref(pg, obj) is not None:
                        page = pg
                        break
            if cfg is None or page is None:
                return
            ref = build_ref(page, obj)
            if ref is None:
                return
            # v4.3.5.27: if several objects are selected, link each new variable
            # to all of them that the attribute applies to (multi-target), so a
            # multi-selection batches the shared attribute on every object.
            extra_objs = [o for o in self._selected_objects() if o is not obj]
            for d, var_name in pairs:
                col = cfg.add_column(ref, d.path, var_name, d.kind)
                try:
                    from edof.batch import effect_id_for_path
                    col.effect_id = effect_id_for_path(obj, d.path)
                except Exception:
                    pass
                # link compatible extra-selected objects
                extra_refs = []
                for eo in extra_objs:
                    if find_descriptor(eo, d.path) is None:
                        continue
                    er = build_ref(page, eo)
                    if er is not None:
                        extra_refs.append(er)
                if extra_refs:
                    col.extra_targets = extra_refs
                _blog("tpl.add_variable", path=d.path, kind=d.kind,
                      var_name=var_name, col_id=col.column_id,
                      n_targets=1 + len(extra_refs))
                self._seed_new_column(cfg, col, d, obj)
            self.rebuild()
            self.changed.emit()

    _RUN_ATTR_FIELDS = [("text", "Text (the words)", "text"),
                        ("font_family", "Font", "text"),
                        ("font_size", "Font size", "number"),
                        ("color", "Colour", "color"),
                        ("background", "Highlight / marker", "color"),
                        ("bold", "Bold", "enum"),
                        ("italic", "Italic", "enum"),
                        ("underline", "Underline", "enum"),
                        ("strikethrough", "Strikethrough", "enum")]

    def _run_var_name(self, obj, rid):
        try:
            for r in (getattr(obj, "runs", None) or []):
                if getattr(r, "rid", None) == rid:
                    return getattr(r, "var_name", None) or rid[:6]
        except Exception:
            pass
        return rid[:6]

    def run_attr_state(self, targets):
        """v4.3.6.13: targets = list of (obj, rid). Return {field: 'all'|'some'
        |'none'} -- which run attributes are currently variables across ALL the
        targets. Used to drive the tri-state checkmarks in the shared-attribute
        menu."""
        cfg = self._cfg()
        state = {}
        n = len(targets)
        for field, _lbl, _k in self._RUN_ATTR_FIELDS:
            path = "run.%s" % field
            have = 0
            for obj, rid in targets:
                if cfg is not None and any(
                        getattr(c, "run_id", "") == rid and c.attr_path == path
                        for c in cfg.columns):
                    have += 1
            state[field] = ("all" if have == n and n else
                            "none" if have == 0 else "some")
        return state

    def set_run_attr(self, targets, field, kind, enable):
        """v4.3.6.13: add (enable) or remove (not enable) the run.<field>
        variable column for every (obj, rid) in targets -- the common-attribute
        edit for a multi-selected set of variables."""
        cfg = self._cfg()
        if cfg is None:
            return
        self._history_begin()
        from edof.batch import find_descriptor_with_run_id
        page = (self._canvas._cur_page()
                if hasattr(self._canvas, "_cur_page") else None)
        path = "run.%s" % field
        changed = False
        for obj, rid in targets:
            existing = None
            for c in cfg.columns:
                if getattr(c, "run_id", "") == rid and c.attr_path == path:
                    existing = c
                    break
            if enable and existing is None:
                ref = build_ref(page, obj) if page is not None else None
                if ref is None:
                    continue
                vn = self._run_var_name(obj, rid)
                col_name = vn if field == "text" else "%s_%s" % (vn, field)
                col = cfg.add_column(ref, path, col_name, kind)
                col.run_id = rid
                try:
                    desc = find_descriptor_with_run_id(obj, path, rid)
                    cur = desc.get(obj) if desc else None
                    raw = _value_to_raw(cur, kind) if cur is not None else ""
                except Exception:
                    raw = ""
                if not cfg.rows:
                    self._new_record()
                for r in cfg.rows:
                    if col.column_id not in r.values:
                        r.values[col.column_id] = raw
                changed = True
            elif (not enable) and existing is not None:
                cfg.remove_column(existing.column_id)
                changed = True
        if changed:
            try: self._canvas._reflow_current_body()
            except Exception: pass
            self.rebuild()
            self.changed.emit()
            try: self._canvas.objectChanged.emit()
            except Exception: pass
            self._history_end("Variable attributes")

    def set_shared_targets(self, targets):
        """v4.3.6.14: remember which variables are selected in the Objects panel
        (used by the shared-attribute dialog). No fixed UI -- editing happens in
        a dialog, like the object 'Add variable' flow."""
        self._shared_targets = list(targets or [])

    def edit_shared_attrs_dialog(self, targets=None):
        """v4.3.6.14: dialog (like the object Add-variable flow) to choose which
        run attributes are batch variables across the selected (obj, rid)
        targets. Checked = variable on all; unchecked = on none; a box left
        partially-checked (mixed) is unchanged."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QCheckBox,
                                     QDialogButtonBox)
        from PyQt6.QtCore import Qt as _Qt
        targets = list(targets if targets is not None else self._shared_targets)
        if not targets:
            return
        state = self.run_attr_state(targets)
        dlg = QDialog(self)
        dlg.setWindowTitle("Variable attributes")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(
            "Which attributes vary, across the %d selected variable%s.\n"
            "A greyed (mixed) box is left unchanged." % (
                len(targets), "" if len(targets) == 1 else "s")))
        checks = {}
        for field, lbl, kind in self._RUN_ATTR_FIELDS:
            cb = QCheckBox(lbl)
            cb.setTristate(True)
            st = state.get(field, "none")
            cb.setCheckState(_Qt.CheckState.Checked if st == "all"
                             else _Qt.CheckState.PartiallyChecked if st == "some"
                             else _Qt.CheckState.Unchecked)
            checks[field] = (cb, kind)
            v.addWidget(cb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        for field, (cb, kind) in checks.items():
            cs = cb.checkState()
            st = state.get(field, "none")
            if cs == _Qt.CheckState.Checked and st != "all":
                self.set_run_attr(targets, field, kind, True)
            elif cs == _Qt.CheckState.Unchecked and st != "none":
                self.set_run_attr(targets, field, kind, False)

    def _add_text_variable(self, ed):
        """v4.3.6.2: make the inline editor's current text selection a batch
        variable. Offers the run's attributes (text + style fields) instead of
        the body object's attributes, assigns a stable rid to the span, and adds
        a batch column per chosen attribute (all sharing that rid)."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
                                     QLineEdit, QLabel, QDialogButtonBox, QComboBox)
        # v4.4.0: header/footer variables are supported now. The band boxes
        # carry a canonical id on every page (hf_header/hf_footer) so build_ref
        # addresses them, and the rid is persisted to the body template right
        # after the span is made (see _commit_hf_runs_from_inline calls below)
        # so it survives repagination.
        rid_cur, vname_cur = ed.selection_variable()
        # default name: first free inlinetextNN. v4.3.6.20: count names on the
        # runs too, not just columns, so a no-attribute variable doesn't collide.
        names = self._all_used_var_names()
        n = 1
        while ("inlinetext%02d" % n) in names:
            n += 1
        default_name = vname_cur or ("inlinetext%02d" % n)

        dlg = QDialog(self)
        dlg.setWindowTitle("Add text variable")
        dlg.resize(360, 320)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Make the selected text a batch variable (a named\n"
                           "span you can target). Optionally choose what should\n"
                           "vary per row -- you can also leave them all off and\n"
                           "just name the span:"))
        # v4.3.6.21: let the selection be added to an EXISTING variable instead
        # of making a new one. Picking an existing variable gives the span the
        # same rid, so one batch value fills every occurrence in the object.
        existing = self._existing_text_variables()
        # don't offer the variable the selection already IS as a merge target
        existing = [(r, nm) for (r, nm) in existing if r != rid_cur]
        combo = QComboBox()
        combo.addItem("New variable", None)
        for _rid, _nm in existing:
            combo.addItem("Add to: %s" % _nm, _rid)
        if existing:
            crow = QHBoxLayout()
            crow.addWidget(QLabel("Variable:"))
            crow.addWidget(combo, 1)
            v.addLayout(crow)
        fields = [("text", "Text (the words)", "text"),
                  ("font_family", "Font", "text"),
                  ("font_size", "Font size", "number"),
                  ("color", "Colour", "color"),
                  ("background", "Highlight / marker", "color"),
                  ("bold", "Bold", "enum"),
                  ("italic", "Italic", "enum"),
                  ("underline", "Underline", "enum"),
                  ("strikethrough", "Strikethrough", "enum")]
        checks = {}
        for f, lbl, _kind in fields:
            cb = QCheckBox(lbl)
            cb.setChecked(f == "text")
            checks[f] = cb
            v.addWidget(cb)
        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("Name:"))
        name_edit = QLineEdit(default_name)
        nrow.addWidget(name_edit)
        v.addLayout(nrow)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # v4.3.6.21: "Add to: <existing>" merges the selection into an existing
        # variable -- give the span that variable's rid, no new column. One batch
        # value then fills this occurrence along with the others.
        merge_rid = combo.currentData()
        if merge_rid:
            merge_name = next((nm for (r, nm) in existing if r == merge_rid), None)
            self._history_begin()
            new_rid = ed.make_variable_from_selection(merge_name or "", rid=merge_rid)
            if not new_rid:
                return
            try: ed.sync_to_tb_silent()
            except Exception: pass
            try: self._canvas._commit_hf_runs_from_inline()
            except Exception: pass
            try: self._canvas._reflow_current_body()
            except Exception: pass
            try:
                from edof.engine.text_engine import set_show_variables
                set_show_variables(True)
                mw0 = self._canvas.parent() if self._canvas else None
                act0 = getattr(mw0, "_act_show_vars", None)
                if act0 is not None: act0.setChecked(True)
                if hasattr(self._canvas, "clear_object_cache"):
                    self._canvas.clear_object_cache()
                self._canvas.schedule_render(0)
            except Exception: pass
            self.rebuild(); self.changed.emit()
            try: self._canvas.objectChanged.emit()
            except Exception: pass
            self._history_end("Merge variables")
            return
        chosen = [(f, k) for f, _l, k in fields if checks[f].isChecked()]
        # v4.3.6.19: an empty selection is allowed now -- you can name a span as a
        # variable WITHOUT any attribute (a targetable entity). Columns can be
        # added later. So don't bail when nothing is checked.
        name = name_edit.text().strip() or default_name
        # v4.4.0: variable names must be unique. A typed name that is already
        # used by ANOTHER variable/column gets auto-suffixed (name_2, ...),
        # so two variables can never share a name. Renaming a span to its
        # own current name is fine.
        used = self._all_used_var_names()
        if (vname_cur or "").strip().lower() == name.strip().lower():
            pass                                  # keeping its own name
        elif name.strip().lower() in used:
            base = name
            k = 2
            while name.strip().lower() in used:
                name = "%s_%d" % (base, k)
                k += 1
            try:
                self._status.setText(
                    'Name already used, created as "%s"' % name)
            except Exception:
                pass

        # assign the rid to the span (reuse if it's already a variable)
        self._history_begin()
        rid = rid_cur or ed.make_variable_from_selection(name)
        if not rid:
            return
        # v4.3.6.14: in document mode the body lives in an inline editor whose
        # _runs are a COPY -- make_variable_from_selection set the rid only on
        # that copy. Push it back to the textbox now; otherwise the reflow below
        # reloads the editor from tb.runs (which still lacks the rid) and the
        # variable vanishes (no rainbow, nothing in the Objects panel).
        try:
            ed.sync_to_tb_silent()
        except Exception:
            pass
        # v4.4.0: in the header/footer the template is the source of truth
        try: self._canvas._commit_hf_runs_from_inline()
        except Exception: pass
        cfg = self._cfg()
        obj = getattr(self._canvas, "_inline_obj", None)
        page = self._canvas._cur_page() if hasattr(self._canvas, "_cur_page") else None
        if cfg is None or obj is None or page is None:
            return
        ref = build_ref(page, obj)
        if ref is None:
            return
        from edof.batch import find_descriptor_with_run_id
        made = False
        for field, kind in chosen:
            path = "run.%s" % field
            col_name = name if field == "text" else "%s_%s" % (name, field)
            # v4.3.6.4: never create a second column for the same run attribute
            # on the same rid -- two run.text columns on one span fight each other
            # (the last one wins, so the variable looks stuck). Reuse the
            # existing column instead of duplicating it.
            existing_col = None
            for c in cfg.columns:
                if getattr(c, "run_id", "") == rid and c.attr_path == path:
                    existing_col = c
                    break
            col = existing_col or cfg.add_column(ref, path, col_name, kind)
            col.run_id = rid
            # seed every row with the run's current value so it does something
            try:
                desc = find_descriptor_with_run_id(obj, path, rid)
                cur = desc.get(obj) if desc else None
                raw = _value_to_raw(cur, kind) if cur is not None else ""
            except Exception:
                raw = ""
            if not cfg.rows:
                self._new_record()
            for r in cfg.rows:
                if col.column_id not in r.values:
                    r.values[col.column_id] = raw
            made = True
        # v4.3.6.19: refresh whenever a variable exists (rid), even with no
        # columns, so a no-attribute entity still highlights and lists.
        if rid:
            try: self._canvas._reflow_current_body()
            except Exception: pass
            # v4.3.6.3: turn on the variable highlight so the user immediately
            # sees which span became the variable (and keep the View-menu check
            # in sync if the main window exposes it).
            try:
                from edof.engine.text_engine import set_show_variables
                set_show_variables(True)
                mw = self._canvas.parent() if self._canvas else None
                act = getattr(mw, "_act_show_vars", None)
                if act is not None:
                    act.setChecked(True)
                ed2 = getattr(self._canvas, "_inline_widget", None)
                if ed2 is not None:
                    ed2._invalidate()
                if hasattr(self._canvas, "clear_object_cache"):
                    self._canvas.clear_object_cache()
                self._canvas.schedule_render(0)
            except Exception:
                pass
            self.rebuild()
            self.changed.emit()
            # v4.3.6.12: the new variable is a virtual object in the Objects
            # panel; emit objectChanged so the panel rebuilds and shows it right
            # away (the batch 'changed' signal alone doesn't refresh that panel).
            try:
                self._canvas.objectChanged.emit()
            except Exception:
                pass
            # v4.3.6.15: also refresh the Objects panel directly (belt-and-
            # suspenders) so the variable is listed even if the objectChanged
            # connection is somehow not wired in this configuration.
            try:
                mw = self._canvas.parent() if self._canvas else None
                op = getattr(mw, "_obj_panel", None)
                if op is not None:
                    op.refresh()
            except Exception:
                pass
            self._history_end("Add variable")

    def _seed_new_column(self, cfg, col, desc, obj):
        """When a new variable is added, make sure there's at least one record,
        and pre-fill the new column in every record with the object's CURRENT
        value -- so the variable does something immediately (an empty cell would
        project nothing). The user then just edits the value."""
        try:
            cur = desc.get(obj)
        except Exception:
            cur = None
        raw = _value_to_raw(cur, desc.kind) if cur is not None else ""
        if not cfg.rows:
            self._new_record()
        for r in cfg.rows:
            if col.column_id not in r.values:
                r.values[col.column_id] = raw

    def _selected_object(self):
        oid = getattr(self._canvas, "_sel_id", None)
        if not oid:
            return None
        finder = getattr(self._canvas, "_find_obj", None)
        return finder(oid) if finder else None

    def _selected_objects(self):
        """All selected objects (primary + multi-select), in a stable order with
        the primary first. v4.3.5.27: lets 'Add variable' target a multi-select."""
        cv = self._canvas
        finder = getattr(cv, "_find_obj", None)
        if finder is None:
            return []
        out = []
        prim = getattr(cv, "_sel_id", None)
        if prim:
            o = finder(prim)
            if o is not None:
                out.append(o)
        for oid in (getattr(cv, "_multi_sel_ids", None) or set()):
            if oid == prim:
                continue
            o = finder(oid)
            if o is not None and o not in out:
                out.append(o)
        return out

    # ── recording (v4.3.5.10) ──────────────────────────────────────────────
    def _on_toggle_record(self, on):
        if on:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        """Begin recording canvas edits into the selected record. Snapshots the
        document so each later edit can be diffed against the baseline."""
        import copy as _c
        cfg = self._cfg()
        rows = self._rows_list()
        if cfg is None or self._doc is None:
            self._btn_record.setChecked(False)
            return
        # need a record to record into; create one if none selected
        if not rows:
            self._new_record()
            rows = self._rows_list()
        if not (0 <= self._cur < len(rows)):
            self._cur = 0
        if getattr(rows[self._cur], "locked", False):
            QMessageBox.information(self, "Record",
                                    "This record is locked. Unlock it first.")
            self._btn_record.setChecked(False)
            return
        self._recording = True
        self._record_row_idx = self._cur
        self._record_baseline = _c.deepcopy(self._doc)
        _blog("tpl.start_recording", row=self._cur,
              n_baseline_pages=len(self._record_baseline.pages))
        self._lbl_record.setText("Recording into: %s"
                                 % (rows[self._cur].name or "Record %d" % (self._cur + 1)))
        if not self._btn_record.isChecked():
            self._btn_record.blockSignals(True)
            self._btn_record.setChecked(True)
            self._btn_record.blockSignals(False)
        # tell the canvas (banner -> REC) and switch it to batch edit
        cv = self._canvas
        if hasattr(cv, "set_edit_mode"):
            cv.set_edit_mode("batch")
        if hasattr(cv, "set_batch_recording"):
            cv.set_batch_recording(True)
        # turn off the read-only projection while recording (we want live edits)
        self._canvas_preview_on = False
        # v4.3.5.20: also drop any active projection on the canvas, otherwise the
        # canvas keeps rendering the projected row on a deep copy and your live
        # edits (incl. size changes / the selection box) wouldn't show.
        if hasattr(cv, "clear_batch_preview"):
            try: cv.clear_batch_preview()
            except Exception: pass
        self._update_show_on_canvas_style()
        # keep the toolbar Batch edit toggle in sync
        self._sync_editor_toggle(True)

    def _sync_editor_toggle(self, on):
        """Reflect recording state in the editor's toolbar Batch edit toggle
        without re-triggering it."""
        ed = getattr(self, "_editor", None)
        act = getattr(ed, "_act_batch_edit", None) if ed is not None else None
        if act is not None and act.isChecked() != bool(on):
            act.blockSignals(True)
            act.setChecked(bool(on))
            act.blockSignals(False)

    def stop_recording(self):
        _blog("tpl.stop_recording", was_recording=getattr(self, "_recording", False))
        if not getattr(self, "_recording", False):
            # still make sure the button reflects the state
            if self._btn_record.isChecked():
                self._btn_record.blockSignals(True)
                self._btn_record.setChecked(False)
                self._btn_record.blockSignals(False)
            return
        self._recording = False
        # restore the live document to the baseline: the edits made while
        # recording belong to the record, not the base template. The record now
        # holds those values and is shown via the non-destructive projection.
        base = self._record_baseline
        restored_idx = self._record_row_idx
        self._record_baseline = None
        self._record_row_idx = None
        self._lbl_record.setText("")
        if self._btn_record.isChecked():
            self._btn_record.blockSignals(True)
            self._btn_record.setChecked(False)
            self._btn_record.blockSignals(False)
        cv = self._canvas
        if base is not None and self._doc is not None:
            try:
                self._restore_document_from(base)
            except Exception:
                pass
        if hasattr(cv, "set_batch_recording"):
            cv.set_batch_recording(False)
        if hasattr(cv, "set_edit_mode"):
            cv.set_edit_mode("classic")
        # keep the toolbar Batch edit toggle in sync
        self._sync_editor_toggle(False)
        # show the just-recorded record via projection again
        self._canvas_preview_on = True
        self._update_show_on_canvas_style()
        if restored_idx is not None:
            self._cur = restored_idx
        self.rebuild()
        self._project_to_canvas(self._cur)

    def _restore_document_from(self, base):
        """Restore the live document's objects to the baseline snapshot exactly,
        so edits made while recording (which belong to the record) don't leak
        into the template. This must also UNDO structural effect changes: if you
        added an effect during recording, the baseline object didn't have it, so
        we replace the whole effects list (and the master flag) from the
        baseline -- not just copy descriptor values, which would leave a newly
        added effect stuck on the template."""
        import copy as _cp
        from edof.batch import describe_object
        for pi, page in enumerate(self._doc.pages):
            if pi >= len(base.pages):
                break
            base_by_id = {getattr(o, "id", None): o
                          for o in getattr(base.pages[pi], "objects", [])}
            for obj in getattr(page, "objects", []):
                bobj = base_by_id.get(getattr(obj, "id", None))
                if bobj is None:
                    continue
                # 1) restore plain attributes via descriptors
                for desc in describe_object(bobj):
                    try:
                        desc.set(obj, desc.get(bobj))
                    except Exception:
                        pass
                # 2) restore the effects list and master flag wholesale, so an
                #    effect added during recording is removed from the template
                try:
                    obj.effects = [_cp.deepcopy(e)
                                   for e in (getattr(bobj, "effects", None) or [])]
                except Exception:
                    pass
                try:
                    obj.effects_enabled = getattr(bobj, "effects_enabled", True)
                except Exception:
                    pass
                # 3) v4.3.6.6: restore rich-text runs wholesale. Run attributes
                #    (run.text / run.color / ...) are NOT in describe_object, so a
                #    value recorded into a run would otherwise stay on the
                #    template -- and then an empty cell in another row would
                #    inherit it instead of resetting to the template default.
                try:
                    if hasattr(bobj, "runs") and getattr(bobj, "runs", None) is not None:
                        obj.runs = [_cp.deepcopy(r) for r in bobj.runs]
                        if getattr(obj, "runs", None):
                            obj.text = "".join(rr.text for rr in obj.runs)
                except Exception:
                    pass
        cv = self._canvas
        if hasattr(cv, "_invalidate_page_cache"):
            try: cv._invalidate_page_cache(cv._page_idx)
            except Exception: pass
        if hasattr(cv, "_start_render"):
            try: cv._start_render()
            except Exception: pass

    def capture_canvas_edit(self):
        """Called when the canvas reports an object edit while recording. Diff
        every object against the baseline snapshot and write changed attributes
        into the recording record, creating columns as needed."""
        if not getattr(self, "_recording", False):
            return
        cfg = self._cfg()
        rows = self._rows_list()
        base = self._record_baseline
        if cfg is None or self._doc is None or base is None:
            return
        if not (0 <= self._record_row_idx < len(rows)):
            return
        row = rows[self._record_row_idx]
        from edof.batch import describe_object, make_default_effect
        from edof.batch.model import build_ref
        changed_any = False
        # walk pages/objects in parallel with the baseline
        for pi, page in enumerate(self._doc.pages):
            if pi >= len(base.pages):
                break
            base_page = base.pages[pi]
            base_by_id = {getattr(o, "id", None): o
                          for o in getattr(base_page, "objects", [])}
            for obj in getattr(page, "objects", []):
                bid = getattr(obj, "id", None)
                bobj = base_by_id.get(bid)
                if bobj is None:
                    continue
                # which effect types are NEW on the object (not on the baseline)?
                # how many effects of each type did the baseline have? An effect
                # field is "new" when its instance index >= the baseline count
                # for that type (covers adding a 2nd/3rd effect of the same type
                # during recording).
                base_type_counts = {}
                for e in (getattr(bobj, "effects", None) or []):
                    t = getattr(e, "type", None)
                    base_type_counts[t] = base_type_counts.get(t, 0) + 1
                # cache a default instance per new effect type, so we capture
                # only the fields that DIFFER from the freshly-added default
                # (plus 'enabled'), not all ~7 fields of the effect.
                _def_cache = {}
                for desc in describe_object(obj):
                    try:
                        cur = desc.get(obj)
                    except Exception:
                        continue
                    if cur is None:
                        continue
                    # figure out the comparison baseline value for this attr
                    path = desc.path
                    old = None
                    is_new_effect_field = False
                    if path.startswith("effects.") and path != "effects.all_enabled":
                        # effects.<type>[#N].<field> -> base type + ordinal
                        seg = path.split(".")[1]
                        field = path.split(".")[-1]
                        if "#" in seg:
                            base_t, _, num = seg.partition("#")
                            try:
                                ordinal = max(0, int(num) - 1)
                            except ValueError:
                                ordinal = 0
                        else:
                            base_t, ordinal = seg, 0
                        if ordinal >= base_type_counts.get(base_t, 0):
                            is_new_effect_field = True
                            if field == "enabled":
                                # always record that a newly-added effect is on
                                old = "false"
                            else:
                                de = _def_cache.get(base_t)
                                if de is None:
                                    de = make_default_effect(base_t)
                                    _def_cache[base_t] = de
                                old = getattr(de, field, None)
                                # _value_to_raw form for comparison
                                old = _value_to_raw(old, desc.kind) if old is not None else None
                                cur_cmp = _value_to_raw(cur, desc.kind)
                                if _values_equal(cur_cmp, old):
                                    continue        # field still at default -> skip
                    if not is_new_effect_field:
                        try:
                            old = desc.get(bobj)
                        except Exception:
                            old = None
                        if _values_equal(cur, old):
                            continue
                    # changed (or a meaningful new-effect field): ensure a column
                    ref = build_ref(page, obj)
                    if ref is None:
                        continue
                    col = _find_or_add_column(cfg, ref, desc, obj=obj)
                    row.values[col.column_id] = _value_to_raw(cur, desc.kind)
                    changed_any = True
        if changed_any:
            _blog("tpl.capture_canvas_edit changed",
                  n_columns=len(cfg.columns), row=self._record_row_idx)
            self.rebuild()
            self.changed.emit()

    # ── preview ──
    def _refresh_preview_current(self):
        rows = self._rows_list()
        if 0 <= self._cur < len(rows):
            self._project_to_canvas(self._cur)

    def _project_to_canvas(self, row_idx):
        """Project the given record onto the main canvas non-destructively, if
        the canvas preview toggle is on."""
        if not getattr(self, "_canvas_preview_on", True):
            _blog("tpl._project_to_canvas SKIP",
                  reason="canvas_preview_on=False (recording? live edit)",
                  row_idx=row_idx, recording=getattr(self, "_recording", False))
            return
        cv = self._canvas
        if cv is None or not hasattr(cv, "set_batch_preview_row"):
            _blog("tpl._project_to_canvas SKIP", reason="no canvas")
            return
        cfg = self._cfg()
        rows = self._rows_list()
        if cfg is None or not (0 <= row_idx < len(rows)):
            _blog("tpl._project_to_canvas SKIP", reason="bad row/cfg",
                  row_idx=row_idx, n_rows=len(rows))
            try: cv.clear_batch_preview()
            except Exception: pass
            return
        _blog("tpl._project_to_canvas", row_idx=row_idx,
              n_values=len(rows[row_idx].values),
              n_columns=len(cfg.columns))
        row = rows[row_idx]
        page_idx = None
        if cfg.row_scope == "page":
            # a concrete page targets that page; cross-page (None) previews on
            # the page currently in view
            if row.page_target is not None:
                page_idx = row.page_target
            else:
                page_idx = getattr(self._canvas, "_page_idx", 0)
        try:
            cv.set_batch_preview_row(row, page_idx=page_idx)
        except Exception:
            pass

    def _on_toggle_canvas_preview(self, on):
        self._canvas_preview_on = bool(on)
        self._update_show_on_canvas_style()
        if on:
            self._project_to_canvas(self._cur)
        else:
            cv = self._canvas
            if cv is not None and hasattr(cv, "clear_batch_preview"):
                try: cv.clear_batch_preview()
                except Exception: pass

    def _update_show_on_canvas_style(self):
        """Colour the 'Show selected on canvas' button by state (green = on,
        grey = off) and disable it while recording (live editing, projection
        doesn't apply)."""
        btn = getattr(self, "_btn_show_on_canvas", None)
        if btn is None:
            return
        recording = bool(getattr(self, "_recording", False))
        btn.setEnabled(not recording)
        if recording:
            btn.setText("Editing live (recording)")
            btn.setStyleSheet("QPushButton{background:#7a3030;color:#fff}")
        elif btn.isChecked():
            btn.setText("Showing selected on canvas")
            btn.setStyleSheet("QPushButton{background:#2e7d32;color:#fff}")
        else:
            btn.setText("Show selected on canvas")
            btn.setStyleSheet("")

    def resizeEvent(self, event):
        super().resizeEvent(event)


class EdofBatchPanel(QWidget):
    """Dockable batch editor. Bind to a canvas; call set_document on load."""

    # emitted whenever the batch config changed (host may mark doc modified)
    changed = pyqtSignal()

    # v4.3.6.28: same one-step undo helpers as the template panel (see there)
    _history_begin = EdofBatchTemplatePanel._history_begin
    _history_end = EdofBatchTemplatePanel._history_end

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._doc = None
        self._building = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── toolbar row ──
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Mode:"))
        self._scope = QComboBox()
        self._scope.addItem("Page per row", "page")
        self._scope.addItem("Whole document per row", "document")
        self._scope.currentIndexChanged.connect(self._on_scope_changed)
        bar.addWidget(self._scope)

        # view switch removed: this panel is the Table editor (bottom dock);
        # the Template editor is a separate vertical panel in the right-side tab

        # which row set: production rows vs the demo (template) rows
        bar.addWidget(QLabel("Rows:"))
        self._rowset = QComboBox()
        self._rowset.addItem("Production", "rows")
        self._rowset.addItem("Demo (template)", "demo")
        self._rowset.currentIndexChanged.connect(self._on_rowset_changed)
        bar.addWidget(self._rowset)

        from PyQt6.QtWidgets import QCheckBox
        self._chk_export_demo = QCheckBox("Export demo")
        self._chk_export_demo.setToolTip(
            "Include demo/template rows when exporting/generating")
        self._chk_export_demo.toggled.connect(self._on_export_demo_toggled)
        bar.addWidget(self._chk_export_demo)

        self._btn_add_col = QPushButton("Add column…")
        self._btn_add_col.clicked.connect(self._on_add_column)
        bar.addWidget(self._btn_add_col)

        self._btn_add_row = QPushButton("Add row")
        self._btn_add_row.clicked.connect(self._on_add_row)
        bar.addWidget(self._btn_add_row)

        self._btn_dup_row = QPushButton("Duplicate row")
        self._btn_dup_row.clicked.connect(self._on_dup_row)
        bar.addWidget(self._btn_dup_row)

        self._btn_del_row = QPushButton("Delete row")
        self._btn_del_row.clicked.connect(self._on_del_row)
        bar.addWidget(self._btn_del_row)

        # v4.3.5.56: CSV export/import (clean csv + meta side csv)
        self._btn_export_csv = QPushButton("Export CSV…")
        self._btn_export_csv.setToolTip(
            "Export rows to a clean CSV (plus a small meta CSV for lossless "
            "re-import)")
        self._btn_export_csv.clicked.connect(self._on_export_csv)
        bar.addWidget(self._btn_export_csv)

        self._btn_import_csv = QPushButton("Import CSV…")
        self._btn_import_csv.setToolTip(
            "Replace rows from a CSV (encoding autodetected; uses the meta CSV "
            "if found next to it)")
        self._btn_import_csv.clicked.connect(self._on_import_csv)
        bar.addWidget(self._btn_import_csv)

        # v4.3.5.58: generate the batch to image/pdf/svg files with a
        # filename-pattern builder (live preview, click-to-insert tokens)
        self._btn_generate = QPushButton("Generate…")
        self._btn_generate.setToolTip(
            "Render every row to a file, naming them from a pattern you build")
        self._btn_generate.clicked.connect(self._on_generate)
        bar.addWidget(self._btn_generate)

        # row filter: all rows, or only rows whose target is the active page
        # (only meaningful with >1 page; hidden otherwise via _update_filter_vis)
        self._filter = QComboBox()
        self._filter.addItem("Show all rows", "all")
        self._filter.addItem("Active page rows only", "active")
        self._filter.currentIndexChanged.connect(lambda *_: self.rebuild())
        bar.addWidget(self._filter)

        bar.addStretch(1)
        self._status = QLabel("")
        bar.addWidget(self._status)
        root.addLayout(bar)

        # ── text filter box (v4.3.5.32) ──
        from PyQt6.QtWidgets import QLineEdit as _QLE
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Filter:"))
        self._text_filter = _QLE()
        self._text_filter.setPlaceholderText(
            "show rows matching a name or value (column name or cell text)")
        self._text_filter.setClearButtonEnabled(True)
        self._text_filter.textChanged.connect(lambda _t: self._apply_filter())
        frow.addWidget(self._text_filter, 1)
        root.addLayout(frow)

        # ── the table ──
        self._table = QTableWidget(0, 0)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setItemDelegate(_CellDelegate(self))
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.currentCellChanged.connect(self._on_row_changed)
        # double-click a header to rename the variable
        self._table.horizontalHeader().sectionDoubleClicked.connect(
            self._on_header_double_clicked)
        # click a header to sort by that column
        self._table.horizontalHeader().setSectionsClickable(True)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        # right-click a header for rename / link-objects
        from PyQt6.QtCore import Qt as _Qt
        _hh = self._table.horizontalHeader()
        _hh.setContextMenuPolicy(_Qt.ContextMenuPolicy.CustomContextMenu)
        _hh.customContextMenuRequested.connect(self._on_header_context_menu)

        # copy / paste whole rows via keyboard
        from PyQt6.QtGui import QShortcut, QKeySequence
        self._row_clipboard = []     # list of (page_target, values, name)
        QShortcut(QKeySequence.StandardKey.Copy, self._table,
                  activated=self._copy_rows)
        QShortcut(QKeySequence.StandardKey.Paste, self._table,
                  activated=self._paste_rows)
        QShortcut(QKeySequence("Ctrl+D"), self._table,
                  activated=self._on_dup_row)

        # ── table fills the dock; the preview is now the MAIN canvas ──
        # v4.3.5.9: the per-panel row preview is gone. Selecting a row projects
        # it non-destructively onto the main canvas instead (single preview).
        body = QHBoxLayout()
        body.addWidget(self._table, 1)
        root.addLayout(body)

        # canvas-projection state
        self._canvas_preview_on = True
        self._preview_page = 0

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def _on_header_double_clicked(self, section):
        """Rename the variable behind a column header (double-click)."""
        from PyQt6.QtWidgets import QInputDialog
        col = self._column_for_visual(section)
        if col is None:                       # the Page column has no variable
            return
        current = col.var_name
        text, ok = QInputDialog.getText(
            self, "Rename variable",
            "Variable name (blank = auto from object/attribute):",
            text=current)
        if ok:
            cfg = self._cfg()
            name = text.strip()
            if not name and cfg is not None:
                # v4.4.0: blank regenerates a systematic unique name
                tail = (col.attr_path or "attr").split(".")[-1] or "attr"
                name = cfg.unique_header(tail, exclude_column_id=col.column_id)
            elif (cfg is not None
                  and cfg.header_in_use(name,
                                        exclude_column_id=col.column_id)):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Rename variable",
                    "A variable named \"%s\" already exists.\n"
                    "Column names must be unique." % name)
                return
            col.var_name = name
            self.rebuild()
            self.changed.emit()

    def _on_header_context_menu(self, pos):
        """Right-click a column header -> rename or link the variable to more
        objects (multi-target)."""
        from PyQt6.QtWidgets import QMenu
        section = self._table.horizontalHeader().logicalIndexAt(pos)
        col = self._column_for_visual(section)
        if col is None:                       # Name / Page columns have no variable
            return
        menu = QMenu(self)
        act_rename = menu.addAction("Rename variable\u2026")
        act_link = menu.addAction("Link objects\u2026")
        gpos = self._table.horizontalHeader().mapToGlobal(pos)
        chosen = menu.exec(gpos)
        if chosen == act_rename:
            self._on_header_double_clicked(section)
        elif chosen == act_link:
            self._link_objects(col)

    def _link_objects(self, col):
        """Open the link-objects dialog for a column, then rebuild so the table
        reflects the new target set."""
        pages = list(self._pages())
        if not pages:
            return
        dlg = _LinkObjectsDialog(col, pages, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # v4.4.0: LINK variables (identity preserved), no fold/merge.
            merge_rids = getattr(dlg, "_merge_rids", None) or []
            if merge_rids or (getattr(col, "extra_run_ids", None) or []):
                doc = getattr(self, "_doc", None)
                cfg = self._cfg() if hasattr(self, "_cfg") else getattr(doc, "batch", None)
                self._history_begin()
                col.extra_run_ids = list(merge_rids)
                if cfg is not None and merge_rids:
                    for cid in [c.column_id for c in list(cfg.columns)
                                if c.column_id != col.column_id
                                and getattr(c, "run_id", "") in set(merge_rids)
                                and c.attr_path == col.attr_path]:
                        try: cfg.remove_column(cid)
                        except Exception: pass
                cv = getattr(self, "_canvas", None)
                if cv is not None:
                    try:
                        if hasattr(cv, "_reflow_current_body"):
                            cv._reflow_current_body()
                    except Exception: pass
                    try: cv.objectChanged.emit()
                    except Exception: pass
                    try: cv.schedule_render(0)
                    except Exception: pass
            self.rebuild()
            # re-project the current row so newly linked objects update now
            self._refresh_preview_current()
            self.changed.emit()
            if merge_rids:
                self._history_end("Merge variables")

    def _refresh_preview_current(self):
        """Project the row selected in the table onto the main canvas."""
        r = self._table.currentRow()
        if r < 0:
            return
        mi = self._model_index_for_table_row(r)
        if mi >= 0:
            self._project_to_canvas(mi)

    def _on_row_changed(self, cur_row, cur_col, prev_row, prev_col):
        if self._building:
            return
        if cur_row != prev_row:
            self._project_to_canvas(self._model_index_for_table_row(cur_row))
        # v4.3.6.28: highlight on the canvas the span the selected cell's
        # column changes, so you can see WHICH piece of text a value drives.
        if cur_col != prev_col or cur_row != prev_row:
            self._focus_column_span(cur_col)

    def _focus_column_span(self, c):
        """v4.3.6.28: canvas-highlight the run span(s) bound to the table
        column under the cursor (its run rid). Lead columns and non-run
        columns clear the highlight."""
        cfg = self._cfg()
        cv = self._canvas
        if cfg is None or cv is None or not hasattr(cv, "set_var_focus_rids"):
            return
        rid = None
        ci = c - self._n_lead()
        if 0 <= ci < len(cfg.columns):
            rid = getattr(cfg.columns[ci], "run_id", "") or None
        try:
            cv.set_var_focus_rids({rid} if rid else None)
        except Exception:
            pass

    def _project_to_canvas(self, row_idx):
        """Project the given model row onto the main canvas non-destructively."""
        if not getattr(self, "_canvas_preview_on", True):
            return
        cv = self._canvas
        if cv is None or not hasattr(cv, "set_batch_preview_row"):
            return
        cfg = self._cfg()
        rows = self._rows_list()
        if cfg is None or not (0 <= row_idx < len(rows)):
            try: cv.clear_batch_preview()
            except Exception: pass
            return
        row = rows[row_idx]
        page_idx = None
        if cfg.row_scope == "page":
            # a concrete page targets that page; cross-page (None) previews on
            # the page currently in view
            if row.page_target is not None:
                page_idx = row.page_target
            else:
                page_idx = getattr(self._canvas, "_page_idx", 0)
        try:
            cv.set_batch_preview_row(row, page_idx=page_idx)
        except Exception:
            pass

    # ── helpers for the cell delegate ────────────────────────────────────────
    def _page_scope(self):
        cfg = self._cfg()
        return cfg is not None and cfg.row_scope == "page"

    def _show_page_col(self):
        """The Page column is shown only in page scope AND when the document
        has more than one page -- with a single page there is nowhere else for
        a row to go, so the column would be redundant."""
        return self._page_scope() and len(self._pages()) > 1

    def _n_lead(self):
        """Number of leading non-data columns: Name (always) + Page (page scope
        with >1 page)."""
        return 1 + (1 if self._show_page_col() else 0)

    def _column_for_visual(self, visual_col):
        """Map a table column index to a BatchColumn (None for lead columns)."""
        cfg = self._cfg()
        if cfg is None:
            return None
        idx = visual_col - self._n_lead()
        if 0 <= idx < len(cfg.columns):
            return cfg.columns[idx]
        return None

    def _first_object_for_column(self, col):
        """Resolve the column's target on the first page where it exists, so
        the delegate can read enum choices off the live descriptor."""
        for pg in self._pages():
            obj = resolve_ref(pg, col.target)
            if obj is not None:
                return obj
        return None

    def _column_label(self, col):
        """Header text for a column. If the user named the variable, use that.
        Otherwise build "<obj>-<N>.<attr>" so two textboxes never collide:
        <obj> is the object's name when set else its type, <N> is the 1-based
        index of that object among same-type objects on its page, and <attr>
        is the attribute path with dots flattened to dashes
        (e.g. "fill.color" -> "fill-color")."""
        if col.var_name.strip():
            return col.var_name.strip()
        attr = col.attr_path.replace(".", "-")
        for pg in self._pages():
            obj = resolve_ref(pg, col.target)
            if obj is None:
                continue
            otype = getattr(obj, "OBJECT_TYPE", "obj")
            base = (getattr(obj, "name", "") or "").strip() or otype
            same = [o for o in getattr(pg, "objects", [])
                    if getattr(o, "OBJECT_TYPE", None) == otype]
            n = 1
            for i, o in enumerate(same, start=1):
                if getattr(o, "id", None) == getattr(obj, "id", None):
                    n = i
                    break
            if base == otype:
                return f"{base}-{n}.{attr}"
            return f"{base}.{attr}"
        return col.attr_path

    def _set_cell_text(self, row, vcol, text):
        """Used by the delegate's modal editors (colour / file) to write a
        value back; goes through the normal item path so the model updates."""
        item = self._table.item(row, vcol)
        if item is None:
            item = QTableWidgetItem("")
            self._table.setItem(row, vcol, item)
        item.setText(text)

    def notify_page_changed(self):
        """Called by the host editor when the canvas page changes. Refreshes
        the active-page row filter, and in document scope follows the active
        page in the preview too."""
        cfg = self._cfg()
        if self._row_filter_active():
            self.rebuild()
        if cfg is not None and cfg.row_scope == "document":
            # follow the editor's page in the preview
            self._preview_page = self._active_page()
            self._refresh_preview_current()

    def _active_page(self):
        """Index of the page currently shown in the editor canvas (0 if
        unknown)."""
        return int(getattr(self._canvas, "_page_idx", 0) or 0)

    def _row_filter_active(self):
        """True when only active-page rows should be shown. Only applies in
        page scope with more than one page."""
        return (self._show_page_col()
                and self._filter.currentData() == "active")

    def _visible_rows(self):
        """List of (model_index, BatchRow) for the rows the table should show,
        honouring the active-page filter. The table renders these in order; a
        table row r maps back to model index via this list."""
        cfg = self._cfg()
        if cfg is None:
            return []
        rows = self._rows_list()
        if not self._row_filter_active():
            return list(enumerate(rows))
        ap = self._active_page()
        out = []
        for i, row in enumerate(rows):
            # cross-page rows (None) show on every page; otherwise match the page
            if row.page_target is None or row.page_target == ap:
                out.append((i, row))
        return out

    def _model_index_for_table_row(self, table_row):
        """Translate a visible table row back to its index in cfg.rows."""
        vis = self._visible_rows()
        if 0 <= table_row < len(vis):
            return vis[table_row][0]
        return -1

    def _update_filter_vis(self):
        """Show the row filter only when it can do something (page scope, >1
        page)."""
        self._filter.setVisible(self._show_page_col())

    # ── document binding ─────────────────────────────────────────────────────
    def set_document(self, doc):
        self._doc = doc
        self.rebuild()

    def _cfg(self):
        return self._doc.batch if self._doc is not None else None

    def _pages(self):
        return list(getattr(self._doc, "pages", []) or []) if self._doc else []

    def _apply_filter(self):
        """Hide table rows that don't match the filter text. A row matches if the
        filter (case-insensitive substring) appears in any column header
        (variable name), the target object's name/type of any column (even
        though it isn't written in the table -- e.g. "rectangle"), or any cell
        value in that row. Empty filter shows all."""
        if getattr(self, "_table", None) is None:
            return
        q = (self._text_filter.text()
             if getattr(self, "_text_filter", None) else "").strip().lower()
        tbl = self._table
        ncols = tbl.columnCount()
        cfg = self._cfg()
        cols = list(cfg.columns) if cfg is not None else []
        nlead = ncols - len(cols)        # leading (name/page) columns
        # a header/object hit shows every row (the match is column-level)
        header_hit = False
        if q:
            # variable-name headers
            for c in range(ncols):
                it = tbl.horizontalHeaderItem(c)
                if it is not None and q in it.text().lower():
                    header_hit = True
                    break
            # target object's name/type per column (not shown in the table)
            if not header_hit:
                for col in cols:
                    obj = self._first_object_for_column(col)
                    if obj is None:
                        continue
                    if q in _object_filter_text(obj):
                        header_hit = True
                        break
        for r in range(tbl.rowCount()):
            if not q or header_hit:
                tbl.setRowHidden(r, False)
                continue
            match = False
            for c in range(ncols):
                cell = tbl.item(r, c)
                if cell is not None and q in cell.text().lower():
                    match = True
                    break
            tbl.setRowHidden(r, not match)

    # ── rebuild table from model ─────────────────────────────────────────────
    def rebuild(self):
        cfg = self._cfg()
        self._building = True
        try:
            self._table.clear()
            if cfg is None:
                self._table.setRowCount(0)
                self._table.setColumnCount(0)
                return

            # reflect scope in the combo without re-triggering
            want = 0 if cfg.row_scope == "page" else 1
            if self._scope.currentIndex() != want:
                self._scope.blockSignals(True)
                self._scope.setCurrentIndex(want)
                self._scope.blockSignals(False)

            # reflect export_demo without re-triggering
            if self._chk_export_demo.isChecked() != bool(cfg.export_demo):
                self._chk_export_demo.blockSignals(True)
                self._chk_export_demo.setChecked(bool(cfg.export_demo))
                self._chk_export_demo.blockSignals(False)

            page_scope = (cfg.row_scope == "page")
            show_page = self._show_page_col()
            self._update_filter_vis()
            # leading columns: always "Name", then "Page" only when it matters
            lead = ["Name"] + (["Page"] if show_page else [])
            n_lead = len(lead)
            n_data_cols = len(cfg.columns)
            visible = self._visible_rows()
            self._table.setColumnCount(n_lead + n_data_cols)
            self._table.setRowCount(len(visible))

            # headers
            headers = list(lead)
            # labels: user var name, else "<type>-<N>.<attr>"
            labels = {c.column_id: self._column_label(c) for c in cfg.columns}
            # duplicates are computed on the SHOWN label, not the raw header
            lab_counts = {}
            for lab in labels.values():
                lab_counts[lab] = lab_counts.get(lab, 0) + 1
            dup = {lab: n for lab, n in lab_counts.items() if n > 1}
            orphans = set(cfg.orphan_columns(self._pages()))
            for c in cfg.columns:
                h = labels[c.column_id]
                if h in dup:
                    h = f"{h}  ×{dup[h]}"
                headers.append(h)
            self._table.setHorizontalHeaderLabels(headers)

            # header tints
            for i, c in enumerate(cfg.columns):
                item = self._table.horizontalHeaderItem(n_lead + i)
                if item is None:
                    continue
                if c.column_id in orphans:
                    item.setForeground(_ORPHAN_TINT)
                elif labels[c.column_id] in dup:
                    item.setForeground(_DUP_TINT)

            # cells (iterate the visible subset; table row r != model index)
            row_index_labels = []
            for r, (_mi, row) in enumerate(visible):
                # 1-based row index label (the model index of the visible row)
                row_index_labels.append(str(_mi + 1))
                # row name (col 0)
                self._table.setItem(r, 0, QTableWidgetItem(row.name or ""))
                if show_page:
                    pitem = QTableWidgetItem(_page_target_to_display(row.page_target))
                    self._table.setItem(r, 1, pitem)
                for i, c in enumerate(cfg.columns):
                    raw = row.values.get(c.column_id, "")
                    cell = QTableWidgetItem("" if raw is None else str(raw))
                    cell.setData(_KIND_ROLE, c.kind)
                    cell.setData(_COLID_ROLE, c.column_id)
                    self._table.setItem(r, n_lead + i, cell)
                    if c.kind == "color":
                        self._paint_color_item(cell)

            self._table.setVerticalHeaderLabels(row_index_labels)
            self._update_status()
        finally:
            self._building = False
        # v4.3.5.32: re-apply the text filter so it survives a rebuild
        self._apply_filter()
        # if a separate template panel is bound, refresh it from the same model.
        # Guard with a dedicated flag so the peer doesn't call back and ping-pong
        # (which made every rebuild fire hundreds of times -> the freeze).
        if not getattr(self, "_syncing_peer", False):
            tp = getattr(self, "_template_peer", None)
            if tp is not None:
                self._syncing_peer = True
                try: tp.rebuild()
                except Exception: pass
                finally: self._syncing_peer = False
        # NOTE: rebuild does NOT project to the canvas (a full re-render); that
        # happens only on actual row-selection / value edits.

    def _update_status(self):
        cfg = self._cfg()
        if cfg is None:
            self._status.setText("")
            return
        which = "demo" if (getattr(self, "_rowset", None) is not None
                           and self._rowset.currentData() == "demo") else "rows"
        self._status.setText(
            f"{len(cfg.columns)} columns · {len(self._rows_list())} {which}")

    def _rows_list(self):
        """The active row set: production rows or the demo (template) rows,
        per the Rows selector. All row operations go through this so the two
        sets are edited identically."""
        cfg = self._cfg()
        if cfg is None:
            return []
        if getattr(self, "_rowset", None) is not None and \
                self._rowset.currentData() == "demo":
            return cfg.demo_rows
        return cfg.rows

    def _on_rowset_changed(self, *_):
        self.rebuild()

    def _on_export_demo_toggled(self, on):
        cfg = self._cfg()
        if cfg is None:
            return
        cfg.export_demo = bool(on)
        self.changed.emit()

    # ── scope ────────────────────────────────────────────────────────────────
    def _on_scope_changed(self, *_):
        cfg = self._cfg()
        if cfg is None:
            return
        cfg.row_scope = self._scope.currentData()
        self.rebuild()
        self.changed.emit()

    # ── add column ───────────────────────────────────────────────────────────
    def _selected_object(self):
        """Resolve the canvas's currently selected object, or None."""
        cv = self._canvas
        oid = getattr(cv, "_sel_id", None)
        if not oid:
            return None
        finder = getattr(cv, "_find_obj", None)
        return finder(oid) if finder else None

    def _selected_objects(self):
        """All selected objects (primary + multi-select), primary first."""
        cv = self._canvas
        finder = getattr(cv, "_find_obj", None)
        if finder is None:
            return []
        out = []
        prim = getattr(cv, "_sel_id", None)
        if prim:
            o = finder(prim)
            if o is not None:
                out.append(o)
        for oid in (getattr(cv, "_multi_sel_ids", None) or set()):
            if oid == prim:
                continue
            o = finder(oid)
            if o is not None and o not in out:
                out.append(o)
        return out

    def add_column_for_object(self, obj, descriptor, var_name="", extra_objs=None):
        """Programmatic column add (also used by tests). Returns the column.
        extra_objs links the variable to more objects (multi-target)."""
        cfg = self._cfg()
        if cfg is None or obj is None:
            return None
        page = self._canvas._cur_page() if hasattr(self._canvas, "_cur_page") else None
        if page is None:
            # fall back to the first page that contains the object
            for pg in self._pages():
                if build_ref(pg, obj) is not None:
                    page = pg
                    break
        if page is None:
            return None
        ref = build_ref(page, obj)
        if ref is None:
            return None
        col = cfg.add_column(ref, descriptor.path, var_name, descriptor.kind,
                             obj=obj)
        # v4.4.0: unnamed columns get the systematic label ("textbox-1.text")
        # PERSISTED as their name, made unique. Custom names were already
        # uniquified by add_column. Two columns can never share a name.
        if not (var_name or "").strip():
            try:
                lab = self._column_label(col)
                col.var_name = cfg.unique_header(
                    lab, exclude_column_id=col.column_id)
            except Exception:
                pass
        # v4.3.5.27: link compatible extra-selected objects (multi-target)
        if extra_objs:
            extra_refs = []
            for eo in extra_objs:
                if eo is obj or find_descriptor(eo, descriptor.path) is None:
                    continue
                er = build_ref(page, eo)
                if er is not None:
                    extra_refs.append(er)
            if extra_refs:
                col.extra_targets = extra_refs
        # v4.3.5.21: bind to the specific effect instance (by stable id) if the
        # object already has it, so reordering effects won't re-point this var
        try:
            from edof.batch import effect_id_for_path
            col.effect_id = effect_id_for_path(obj, descriptor.path)
        except Exception:
            pass
        # seed: ensure a record exists and pre-fill the new column with the
        # object's current value so the variable does something immediately
        try:
            cur = descriptor.get(obj)
        except Exception:
            cur = None
        raw = _value_to_raw(cur, descriptor.kind) if cur is not None else ""
        if not cfg.rows:
            cfg.rows.append(BatchRow(page_target=0, values={}))
        for r in cfg.rows:
            if col.column_id not in r.values:
                r.values[col.column_id] = raw
        self.rebuild()
        self.changed.emit()
        return col

    def _on_add_column(self):
        obj = self._selected_object()
        if obj is None:
            QMessageBox.information(
                self, "Add column",
                "Select an object on the canvas first, then add a column.")
            return
        _existing = _existing_paths_for_object(self._cfg(), obj, list(self._pages()))
        _names = list(self._all_used_var_names())   # v4.3.6.20: include run var_names
        _extra = [o for o in self._selected_objects() if o is not obj]
        dlg = _AddColumnDialog(obj, self, existing_paths=_existing,
                               existing_names=_names, extra_objs=_extra)
        dlg_code = dlg.exec()
        # the effect-reorder list writes order to the object live, so reflect it
        # even if the dialog was cancelled
        if getattr(dlg, "_reordered", False):
            try: self._canvas.schedule_render(0)
            except Exception: pass
            self.changed.emit()
        if dlg_code == QDialog.DialogCode.Accepted:
            extra_objs = [o for o in self._selected_objects() if o is not obj]
            for desc, var_name in dlg.chosen_pairs():
                self.add_column_for_object(obj, desc, var_name,
                                           extra_objs=extra_objs)

    # ── rows ─────────────────────────────────────────────────────────────────
    def _on_add_row(self):
        cfg = self._cfg()
        if cfg is None:
            return
        pt = 0 if cfg.row_scope == "page" else None
        self._rows_list().append(BatchRow(page_target=pt, values={}))
        self.rebuild()
        self.changed.emit()

    def _on_del_row(self):
        cfg = self._cfg()
        if cfg is None:
            return
        rows = self._rows_list()
        mi = self._model_index_for_table_row(self._table.currentRow())
        if 0 <= mi < len(rows):
            rows.pop(mi)
            self.rebuild()
            self.changed.emit()

    # ── CSV export / import (v4.3.5.56) ──────────────────────────────────────
    def _meta_path_for(self, csv_path):
        """The meta side file sits next to the clean csv: foo.csv -> foo.meta.csv"""
        import os
        base, ext = os.path.splitext(csv_path)
        return base + ".meta" + (ext or ".csv")

    def _on_export_csv(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        cfg = self._cfg()
        if cfg is None or not cfg.columns:
            QMessageBox.information(self, "Export CSV",
                                    "Add at least one column first.")
            return
        path, _f = QFileDialog.getSaveFileName(
            self, "Export batch CSV", "batch.csv", "CSV (*.csv);;All files (*)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        meta_path = self._meta_path_for(path)
        try:
            inc = bool(getattr(cfg, "export_demo", False))
            # UTF-8 with BOM so Excel on Windows opens Czech text correctly
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(cfg.to_csv(include_demo=inc))
            with open(meta_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(cfg.to_meta_csv())
        except OSError as e:
            QMessageBox.warning(self, "Export CSV", "Could not write file:\n%s" % e)
            return
        import os
        self._status.setText("Exported %d rows to %s (+ %s)" % (
            len(cfg.rows), os.path.basename(path), os.path.basename(meta_path)))

    def _on_import_csv(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import os
        cfg = self._cfg()
        if cfg is None or not cfg.columns:
            QMessageBox.information(self, "Import CSV",
                                    "Add the columns first; import fills rows, "
                                    "it doesn't create columns.")
            return
        path, _f = QFileDialog.getOpenFileName(
            self, "Import batch CSV", "", "CSV (*.csv);;All files (*)")
        if not path:
            return
        try:
            with open(path, "rb") as f:
                clean = f.read()
        except OSError as e:
            QMessageBox.warning(self, "Import CSV", "Could not read file:\n%s" % e)
            return
        # auto-pick the meta side file if it's there
        meta = None
        meta_path = self._meta_path_for(path)
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "rb") as f:
                    meta = f.read()
            except OSError:
                meta = None
        try:
            n = cfg.update_rows_from_csv(clean, meta=meta)
        except Exception as e:
            QMessageBox.warning(self, "Import CSV", "Could not parse CSV:\n%s" % e)
            return
        self.rebuild()
        self.changed.emit()
        suffix = " (with meta)" if meta is not None else " (matched by header)"
        self._status.setText("Imported %d rows from %s%s" % (
            n, os.path.basename(path), suffix))

    def _on_generate(self):
        """v4.3.5.58: render every row to a file using the filename-pattern
        dialog (the pattern's tokens are resolved per row)."""
        from PyQt6.QtWidgets import QMessageBox
        import os, copy as _cp
        from edof.batch.model import apply_row_to_document, render_filename
        cfg = self._cfg()
        if cfg is None or not cfg.rows:
            QMessageBox.information(self, "Generate batch",
                                    "There are no rows to generate.")
            return
        rows = list(cfg.rows) + (list(cfg.demo_rows)
                                 if getattr(cfg, "export_demo", False) else [])
        dlg = _FilenamePatternDialog(cfg, rows, self)
        from PyQt6.QtWidgets import QDialog
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        out_dir = dlg.out_dir; pattern = dlg.pattern; fmt = dlg.fmt
        page_idx = self._active_page_index()
        # v4.4.0: the export engine handles scope (page/all), every format
        # incl. edof, per-page files with the [PAGE] token and the external
        # -sources ZIP bundles
        from edof.batch.generate import export_batch
        # v4.4.0: progress dialog with Cancel; the callback pumps the event
        # loop between rows so the UI stays alive and Cancel works.
        from PyQt6.QtWidgets import QProgressDialog, QApplication
        from PyQt6.QtCore import Qt
        prog = QProgressDialog("Generating batch…", "Cancel",
                               0, len(rows), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(300)   # only pops up for real work
        prog.setAutoClose(False); prog.setAutoReset(False)

        def _tick(done, total):
            prog.setValue(done)
            prog.setLabelText("Generating row %d of %d…"
                              % (min(done + 1, total), total))
            QApplication.processEvents()
            return not prog.wasCanceled()

        try:
            ok, written, errors = export_batch(
                self._doc, cfg, rows, out_dir, pattern, fmt,
                scope=dlg.scope, page_idx=page_idx, sources=dlg.sources,
                output=dlg.output, progress=_tick,
                image_format=dlg.image_format,
                image_quality=dlg.image_quality)
        finally:
            prog.close()
        cancelled = any(e.startswith("Cancelled") for e in errors)
        what = ("1 multipage file" if dlg.output == "single"
                else "%d file(s)" % len(written))
        msg = "Generated %d/%d rows (%s) to:\n%s" % (
            ok, len(rows), what, out_dir)
        if cancelled:
            msg = "Cancelled.\n" + msg
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors[:5])
        QMessageBox.information(self, "Generate batch", msg)
        self._status.setText(("Cancelled at %d/%d rows" if cancelled
                              else "Generated %d/%d rows") % (ok, len(rows)))

    def _active_page_index(self):
        return int(getattr(self._canvas, "_page_idx", 0) or 0)

    def _on_dup_row(self):
        """Duplicate the selected row (a deep copy of its values), inserting the
        clone right after it."""
        import copy as _c
        cfg = self._cfg()
        if cfg is None:
            return
        rows = self._rows_list()
        mi = self._model_index_for_table_row(self._table.currentRow())
        if not (0 <= mi < len(rows)):
            return
        src = rows[mi]
        clone = BatchRow(page_target=src.page_target,
                         values=_c.deepcopy(src.values),
                         name=(src.name + " copy") if src.name else "")
        rows.insert(mi + 1, clone)
        self.rebuild()
        self.changed.emit()

    def _selected_model_rows(self):
        """Model indices of the table's selected rows, in visible order."""
        sel = self._table.selectionModel()
        if sel is None:
            return []
        table_rows = sorted({ix.row() for ix in sel.selectedRows()})
        if not table_rows:
            r = self._table.currentRow()
            table_rows = [r] if r >= 0 else []
        out = []
        for tr in table_rows:
            mi = self._model_index_for_table_row(tr)
            if mi >= 0:
                out.append(mi)
        return out

    def _copy_rows(self):
        """Copy selected rows into the internal clipboard (deep copies)."""
        import copy as _c
        rows = self._rows_list()
        mis = self._selected_model_rows()
        self._row_clipboard = [
            (rows[mi].page_target, _c.deepcopy(rows[mi].values), rows[mi].name)
            for mi in mis if 0 <= mi < len(rows)]

    def _paste_rows(self):
        """Append clipboard rows as new rows after the current selection."""
        import copy as _c
        if not self._row_clipboard:
            return
        rows = self._rows_list()
        mis = self._selected_model_rows()
        at = (max(mis) + 1) if mis else len(rows)
        for i, (pt, vals, name) in enumerate(self._row_clipboard):
            rows.insert(at + i, BatchRow(page_target=pt,
                                         values=_c.deepcopy(vals),
                                         name=name))
        self.rebuild()
        self.changed.emit()

    def _on_header_clicked(self, section):
        """Sort the active row set by the clicked column (toggles asc/desc).
        Sorting reorders the model rows. Lead columns sort by Name / Page."""
        rows = self._rows_list()
        if len(rows) < 2:
            return
        col = self._column_for_visual(section)
        # decide the key
        if col is None:
            if section == 0:                       # Name column
                key = lambda r: (r.name or "").lower()
            elif self._show_page_col() and section == 1:
                key = lambda r: (r.page_target if r.page_target is not None else 0)
            else:
                return
        else:
            cid = col.column_id
            kind = col.kind

            def key(r, cid=cid, kind=kind):
                v = r.values.get(cid, "")
                if kind == "number":
                    try:
                        return (0, float(str(v).replace(",", ".")))
                    except (ValueError, TypeError):
                        return (1, 0.0)
                return (0, str(v).lower())

        # toggle direction per section
        prev = getattr(self, "_sort_state", (None, False))
        descending = (prev[0] == section) and (not prev[1])
        self._sort_state = (section, descending)
        try:
            rows.sort(key=key, reverse=descending)
        except TypeError:
            # mixed types: fall back to string compare
            rows.sort(key=lambda r: str(key(r)), reverse=descending)
        self.rebuild()
        self.changed.emit()

    # ── editing cells writes back to the model ───────────────────────────────
    def _on_item_changed(self, item):
        if self._building:
            return
        cfg = self._cfg()
        if cfg is None:
            return
        rows = self._rows_list()
        r = self._model_index_for_table_row(item.row())
        c = item.column()
        if not (0 <= r < len(rows)):
            return
        # lead columns: 0 = Name, 1 = Page (only when the Page column is shown)
        if c == 0:
            rows[r].name = item.text().strip()
            self.changed.emit()
            return
        if self._show_page_col() and c == 1:
            rows[r].page_target = _display_to_page_target(item.text())
            # the target page changed -> the preview's page may change too
            self._refresh_preview_current()
            self.changed.emit()
            return
        col_idx = c - self._n_lead()
        if 0 <= col_idx < len(cfg.columns):
            col = cfg.columns[col_idx]
            rows[r].values[col.column_id] = item.text()
            if col.kind == "color":
                self._paint_color_item(item)
            # live: reflect the edited value in the preview immediately
            self._refresh_preview_current()
            self.changed.emit()

    def _paint_color_item(self, item):
        """Apply the colour swatch + contrasting hex text to a single cell."""
        qc = _parse_color(item.text())
        if qc is not None:
            item.setBackground(QBrush(qc))
            lum = 0.299 * qc.red() + 0.587 * qc.green() + 0.114 * qc.blue()
            item.setForeground(QBrush(
                QColor(0, 0, 0) if lum > 140 else QColor(255, 255, 255)))
        else:
            # invalid/empty: clear any previous swatch
            item.setBackground(QBrush())
            item.setForeground(QBrush())

    # ── deletion integrity (host calls after an object is removed) ───────────
    def prune_after_object_change(self):
        cfg = self._cfg()
        if cfg is None:
            return
        removed = cfg.prune_dead_columns(self._pages())
        if removed:
            self.rebuild()
            self.changed.emit()


# ── v4.3.5.58: batch generate dialog with a filename-pattern builder ─────────
class _FilenamePatternDialog(QDialog):
    """Pick an output folder and a filename pattern for batch generation, with a
    live preview of the resulting name that can be stepped through the rows, and
    click-to-insert buttons for the row number / row name / each column."""

    def __init__(self, cfg, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate batch")
        try:
            from edof._apps.editor import QSS
            self.setStyleSheet(QSS)
        except Exception:
            pass
        self.resize(560, 480)
        self._cfg = cfg
        self._rows = rows
        self._preview_idx = 0
        self.out_dir = ""
        self.pattern = "[ROW_NUMBER:04]_[ROW_NAME]"
        self.fmt = "png"
        self.scope = "page"          # v4.4.0: "page" | "all"
        self.sources = "integrate"   # v4.4.0: "integrate" | "external"
        self.output = "per_row"      # v4.4.0: "per_row" | "single"
        self.image_format = None     # v4.4.0: None | "jpeg" (+quality)
        self.image_quality = 80

        from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                                     QPushButton, QComboBox, QDialogButtonBox,
                                     QGridLayout, QFrame)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14); v.setSpacing(8)

        # output folder
        of = QHBoxLayout()
        of.addWidget(QLabel("Output folder:"))
        self._le_dir = QLineEdit(); self._le_dir.setReadOnly(True)
        of.addWidget(self._le_dir, 1)
        b_browse = QPushButton("Browse…"); b_browse.clicked.connect(self._pick_dir)
        of.addWidget(b_browse)
        v.addLayout(of)

        # format
        ff = QHBoxLayout()
        ff.addWidget(QLabel("Format:"))
        self._cb_fmt = QComboBox()
        self._cb_fmt.addItems(["png", "jpg", "pdf", "svg", "edof"])
        self._cb_fmt.currentTextChanged.connect(self._on_fmt_changed)
        ff.addWidget(self._cb_fmt)
        # v4.4.0: page scope -- one chosen page, or every page. For png/jpg/
        # svg "all pages" writes one file per page ([PAGE] token); for pdf it
        # switches single-page vs multipage; for edof a one-page document vs
        # the whole document.
        from PyQt6.QtWidgets import QRadioButton
        self._rb_page = QRadioButton("Current page")
        self._rb_all = QRadioButton("All pages")
        self._rb_page.setChecked(True)
        ff.addSpacing(14)
        ff.addWidget(self._rb_page); ff.addWidget(self._rb_all)
        ff.addStretch(1)
        v.addLayout(ff)
        # v4.4.0: output shape for pdf/edof -- one file per row (tag-based
        # names) or ONE multipage file with every row's page(s) appended.
        outf = QHBoxLayout()
        self._lbl_output = QLabel("Output:")
        self._rb_per_row = QRadioButton("File per row (tags in name)")
        self._rb_single = QRadioButton("Single multipage file (all rows)")
        self._rb_per_row.setChecked(True)
        # keep the two radio groups apart
        from PyQt6.QtWidgets import QButtonGroup
        self._grp_output = QButtonGroup(self)
        self._grp_output.addButton(self._rb_per_row)
        self._grp_output.addButton(self._rb_single)
        self._grp_scope = QButtonGroup(self)
        self._grp_scope.addButton(self._rb_page)
        self._grp_scope.addButton(self._rb_all)
        self._rb_single.setToolTip(
            "One file: every row's page(s) appended in row order.\n"
            "edof: the result is baked to fixed pages (values filled in,\n"
            "no live batch), so it reopens exactly as generated.")
        self._rb_per_row.toggled.connect(self._on_output_changed)
        outf.addWidget(self._lbl_output)
        outf.addWidget(self._rb_per_row); outf.addWidget(self._rb_single)
        outf.addStretch(1)
        v.addLayout(outf)
        self._lbl_output.setVisible(False)
        self._rb_per_row.setVisible(False); self._rb_single.setVisible(False)
        # v4.4.0: external-source handling for the edof format
        sf = QHBoxLayout()
        self._lbl_sources = QLabel("Sources:")
        self._cb_sources = QComboBox()
        self._cb_sources.addItem(
            "Integrate external sources into the file", "integrate")
        self._cb_sources.addItem(
            "Keep sources as files next to the .edof and ZIP", "external")
        self._cb_sources.setToolTip(
            "Integrate: one self-contained .edof (images materialised, used "
            "fonts embedded).\nZIP: the .edof plus a sources/ folder with the "
            "referenced files, zipped together -- editable bundle.")
        sf.addWidget(self._lbl_sources); sf.addWidget(self._cb_sources, 1)
        v.addLayout(sf)
        self._lbl_sources.setVisible(False); self._cb_sources.setVisible(False)
        # v4.4.0: image compression for pdf/edof outputs (photo-heavy
        # documents shrink dramatically with JPEG)
        imf = QHBoxLayout()
        self._lbl_img = QLabel("Images:")
        self._cb_img = QComboBox()
        from edof._apps.editor import _IMAGE_COMPRESS_CHOICES
        for label, data in _IMAGE_COMPRESS_CHOICES:
            self._cb_img.addItem(label, data)
        self._cb_img.setToolTip(
            "Lossless keeps images exactly as they are.\nJPEG re-encodes "
            "photos at the chosen quality (transparency preserved), so the "
            "generated files are much smaller.")
        imf.addWidget(self._lbl_img); imf.addWidget(self._cb_img, 1)
        v.addLayout(imf)
        self._lbl_img.setVisible(False); self._cb_img.setVisible(False)

        # pattern field
        self._lbl_pattern = QLabel("Filename pattern:")
        v.addWidget(self._lbl_pattern)
        self._le_pat = QLineEdit(self.pattern)
        self._le_pat.textChanged.connect(self._refresh_preview)
        v.addWidget(self._le_pat)

        # insert buttons: row number / name + a column picker
        ins = QGridLayout(); ins.setHorizontalSpacing(6); ins.setVerticalSpacing(4)
        b_num = QPushButton("+ Row number"); b_num.setToolTip("[ROW_NUMBER:04]")
        b_num.clicked.connect(lambda: self._insert("[ROW_NUMBER:04]"))
        b_name = QPushButton("+ Row name"); b_name.setToolTip("[ROW_NAME]")
        b_name.clicked.connect(lambda: self._insert("[ROW_NAME]"))
        b_page = QPushButton("+ Page"); b_page.setToolTip(
            "[PAGE:02] -- page number, used when exporting every page")
        b_page.clicked.connect(lambda: self._insert("[PAGE:02]"))
        ins.addWidget(b_num, 0, 0); ins.addWidget(b_name, 0, 1)
        ins.addWidget(b_page, 0, 2)
        self._tag_buttons = [b_num, b_name, b_page]
        # column picker
        self._cb_col = QComboBox()
        for c in cfg.columns:
            self._cb_col.addItem(c.header())
        b_col = QPushButton("+ Add column")
        b_col.clicked.connect(self._insert_column)
        self._tag_buttons += [b_col, self._cb_col]
        ins.addWidget(self._cb_col, 1, 0); ins.addWidget(b_col, 1, 1)
        v.addLayout(ins)

        # help text (how to write it)
        help_line = QFrame(); help_line.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(help_line)
        help_txt = QLabel(
            "How the pattern works:\n"
            "  [ROW_NUMBER]      the row number (1, 2, 3 …)\n"
            "  [ROW_NUMBER:04]   zero-padded width, e.g. 0007\n"
            "  [ROW_NAME]        the row's name\n"
            "  [{Column}]        a column's value (pick above and Add)\n"
            "  [{Column:upper}]  upper/lower-cased value\n"
            "Anything else is kept as plain text. The extension is added "
            "automatically.")
        help_txt.setWordWrap(True)
        help_txt.setStyleSheet("color:#9aa;font-size:11px;")
        v.addWidget(help_txt)

        # live preview with row stepper
        pv = QHBoxLayout()
        self._b_prev = QPushButton("‹"); self._b_prev.setFixedWidth(34)
        self._b_prev.clicked.connect(lambda: self._step(-1))
        self._b_next = QPushButton("›"); self._b_next.setFixedWidth(34)
        self._b_next.clicked.connect(lambda: self._step(1))
        pv.addWidget(self._b_prev)
        self._lbl_preview = QLabel("")
        self._lbl_preview.setStyleSheet(
            "background:#1c1f26;border:1px solid #333;border-radius:4px;"
            "padding:6px 10px;font-family:monospace;")
        pv.addWidget(self._lbl_preview, 1)
        pv.addWidget(self._b_next)
        v.addLayout(pv)
        self._lbl_rowinfo = QLabel("")
        self._lbl_rowinfo.setStyleSheet("color:#888;font-size:11px;")
        v.addWidget(self._lbl_rowinfo)

        v.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Generate")
        bb.accepted.connect(self._accept); bb.rejected.connect(self.reject)
        v.addWidget(bb)

        self._refresh_preview()

    # -- token insertion --
    def _insert(self, token):
        le = self._le_pat
        le.insert(token)
        le.setFocus()

    def _insert_column(self):
        h = self._cb_col.currentText()
        if h:
            self._insert("[{%s}]" % h)

    # -- preview stepping --
    def _step(self, d):
        if not self._rows:
            return
        self._preview_idx = (self._preview_idx + d) % len(self._rows)
        self._refresh_preview()

    def _refresh_preview(self):
        from edof.batch.model import render_filename
        self.fmt = self._cb_fmt.currentText()
        pat = self._le_pat.text()
        if not self._rows:
            self._lbl_preview.setText("(no rows)")
            self._lbl_rowinfo.setText("")
            return
        single = (getattr(self, "_rb_single", None) is not None
                  and self._rb_single.isVisible()
                  and self._rb_single.isChecked())
        idx = 0 if single else min(self._preview_idx, len(self._rows) - 1)
        row = self._rows[idx]
        try:
            name = render_filename(pat, idx + 1, row, self._cfg,
                                   default_ext=self.fmt)
        except Exception as e:
            name = "(error: %s)" % e
        self._lbl_preview.setText(name)
        if single:
            self._lbl_rowinfo.setText(
                "One multipage file with all %d rows" % len(self._rows))
        else:
            label = row.name.strip() if row.name.strip() else "(unnamed)"
            self._lbl_rowinfo.setText("Preview: row %d of %d  —  %s" % (
                idx + 1, len(self._rows), label))

    def _pick_dir(self):
        from PyQt6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if d:
            self.out_dir = d
            self._le_dir.setText(d)

    def _accept(self):
        from PyQt6.QtWidgets import QMessageBox
        if not self.out_dir:
            QMessageBox.information(self, "Generate batch",
                                    "Choose an output folder first.")
            return
        self.pattern = self._le_pat.text().strip() or "[ROW_NUMBER:04]"
        self.fmt = self._cb_fmt.currentText()
        self.scope = "all" if self._rb_all.isChecked() else "page"
        self.sources = self._cb_sources.currentData() or "integrate"
        self.output = ("single" if (self._rb_single.isVisible()
                                    and self._rb_single.isChecked())
                       else "per_row")
        data = self._cb_img.currentData() if self._cb_img.isVisible() else None
        self.image_format, self.image_quality = (data or (None, 80))
        self.accept()

    def _on_fmt_changed(self, _txt=None):
        """v4.4.0: the sources choice only applies to the edof format; the
        per-row / single-file choice only to pdf and edof."""
        fmt = self._cb_fmt.currentText()
        is_edof = fmt == "edof"
        self._lbl_sources.setVisible(is_edof)
        self._cb_sources.setVisible(is_edof)
        multi_ok = fmt in ("pdf", "edof")
        self._lbl_output.setVisible(multi_ok)
        self._rb_per_row.setVisible(multi_ok)
        self._rb_single.setVisible(multi_ok)
        self._lbl_img.setVisible(multi_ok)
        self._cb_img.setVisible(multi_ok)
        if not multi_ok:
            self._rb_per_row.setChecked(True)
        self._on_output_changed()

    def _on_output_changed(self, _checked=None):
        """Single-file mode uses the pattern ONCE as a plain filename, so the
        per-row tag helpers make no sense there."""
        single = (self._rb_single.isVisible()
                  and self._rb_single.isChecked())
        for w in getattr(self, "_tag_buttons", []):
            w.setEnabled(not single)
        self._lbl_pattern.setText(
            "Filename (one file):" if single else "Filename pattern:")
        self._refresh_preview()
