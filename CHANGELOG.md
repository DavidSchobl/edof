## [4.4.0] - 2026-07-02

Two big pieces land here: the header/footer rework (containers of objects,
batch variables inside) and hyperlinks. File format bumped once, to 4.3.0
(all new keys additive; old files load unchanged, old readers ignore them).

### Added, header/footer rework
- **Header/footer as a container of objects.** DocumentBody gained
  header_objects / footer_objects: template objects of any type (TextBox,
  ImageBox, Shape, ...). Every page receives a literal clone of each template
  with the SAME id, so rendering, selection, batch refs and variable rids work
  per page while the single source of truth stays on the body. Editing any
  clone writes back to the template and re-syncs every page. Objects panel
  context menu: "Move to header", "Move to footer", "Detach from
  header/footer". {page_number} tokens stay a band-text feature; container
  clones are literal copies so writeback is lossless.
- **Batch variables in the header/footer.** The band boxes carry a canonical
  id on every page (hf_header / hf_footer, migrated automatically for older
  files at pagination), so one batch ObjectRef addresses the band everywhere
  and a document-scope row fills the header on every page. Making a variable
  in the header/footer inline editor persists the rid to the body template
  immediately (survives repagination). The 4.3.6.7 block dialog is gone;
  run-attribute toggles work in the band too.
- **Rid ops mirror into header/footer templates.** Remove, rename, merge and
  change-range of a text variable also update the band template runs and
  container object runs. The orphan-variable GC counts template rids as
  present, so toggling the band off does not drop its columns.

### Added, hyperlinks
- **Link as a run format, like bold/italic.** TextRun gained `link`: either an
  external target (http/https/mailto URL) or an in-document jump written as
  "#<anchor_id>". Toolbar button, Ctrl+K and the right-click menu share one
  dialog (external URL field, or a picker of marked targets). Removing a link
  is in the same dialog and the context menu.
- **In-document link targets (anchors).** "Mark as link target (anchor)" names
  the selected span; the id lives on the runs (like a rid) so it survives
  editing around it and page reflow. Following the link switches to the
  target's page, opens the editor there and selects the span.
- **Document link style with per-link overrides.** Default blue underlined;
  Document menu: "Link style..." edits colour, underline and hover colour for
  every link in the document. A link with explicit run formatting keeps it,
  which is how one link is re-styled individually. Stored as
  Document.link_style.
- **Hover + Ctrl+click in the editor.** Hovering a link tints it with the
  hover colour; holding Ctrl shows the pointing hand and Ctrl+click follows
  the link (a plain click keeps editing, Word style).
- **Ctrl+click works directly on the canvas too**, outside any inline editing
  session, in BASIC mode as well as document mode: clicking a link span on the
  page follows it (rotated text boxes: follow from the inline editor).
- **Viewer follows links on plain click.** External links open the browser;
  in-document links jump to the target page. Panning still works; rotated
  text boxes are skipped (editor feature).

### Fixed
- Pagination re-syncs header/footer container clones on every pass; stale
  clones (template removed, band disabled) are dropped from the pages.
- Run merge in the inline editor (_normalize_runs) ignored link/anchor
  attributes, so a freshly made link adjacent to same-formatted text merged
  back and silently lost the link.

### Fixed, beta review (security + data loss)
- **SECURITY: DoS in the visible_if evaluator.** safe_eval allowed an
  unbounded ** so an untrusted .edof with "9**9**9" froze the process. The
  exponent is capped (|exp| <= 64), integer results are capped at 4096 bits,
  and string/list repetition and concatenation are capped at 10k elements.
  Sane expressions are unaffected; anything over the caps evaluates to None
  (falsy) like any other invalid expression.
- **Recovery key now unlocks in any typed form.** The recovery slot used to be
  keyed by the dashed display form, so typing the key without dashes or in
  lowercase never matched (the normalizing branch was dead code). The slot is
  now keyed by the normalized form; the raw form is still tried for files
  written by older builds.
- **Second save() on one PdfWriter produced a corrupt PDF.** Finalisation
  objects (page contents, /Pages, /Info, /Catalog) were appended to the
  object list without a reset, so the second save wrote duplicate catalogs
  and a wrong /Size. save() now snapshots the object list and restores it,
  making it idempotent (byte-identical output).
- **.docx round-trip re-emboldened explicitly non-bold runs.** Import
  collapsed bold/italic/underline False (explicitly off) to None (inherit).
  The tri-state is preserved now, and enum underline values from python-docx
  are coerced sanely.
- **RTF import: Word files decoded with garbage and wrong underline.**
  The \uNNNN decoder ignored the \ucN skip count, so cp1252 fallback bytes
  leaked into the text as duplicates; \ul0 (underline OFF) switched underline
  ON. Both fixed (the skip count is honoured with group scoping); \par
  immediately followed by \page no longer creates a phantom empty paragraph.
  The RTF generator string also stopped claiming edof 4.0.3.
- **Docs: the permission model is spelled out.** Every password slot wraps the
  same content key, so levels are honor-system enforcement by the library,
  not cryptographic isolation; the encryption reference now says so
  explicitly and documents recovery-key normalization.

### Fixed, beta review round 2 (link export + PDF correctness)
- **Links now EXPORT.** PDF: every link run emits a /Link annotation (adjacent
  same-link words on a line merge into one /Rect); external targets via
  /A /URI, in-document anchors via /Dest [page /Fit] resolved to the target
  page. SVG: link runs are wrapped in <a href / xlink:href> (new-tab target
  for external). Before, exports showed blue underlined text that was not
  clickable.
- **SECURITY: link targets are validated everywhere.** New shared
  edof.utils.links.validate_link whitelists http/https/mailto and #anchors
  (bare domains normalize to https://). Applied when a link is CREATED
  (editor dialog + set_link_on_selection return False on refuse), when it is
  FOLLOWED (editor, canvas, viewer; a link stored in an untrusted file cannot
  smuggle javascript:/file:/data:) and when it is EXPORTED (PDF/SVG never
  emit an unsafe scheme).
- **PDF quadratic Bezier segments render correctly.** Q -> C conversion now
  uses the proper degree elevation (C1 = P0 + 2/3(Q-P0), C2 = P2 + 2/3(Q-P2))
  with the current point tracked across M/L/C/Q/Z. The old code used the
  quadratic control point as BOTH cubic control points, so exported curves
  visibly differed from the PNG renderer.
- **Transparent PNGs export transparent.** add_image emits a grayscale /SMask
  XObject built from the alpha channel (the has_alpha/alpha_mask parameters
  were accepted but ignored before); the imagebox export path feeds it
  whenever the source has real transparency.
- **Silent failures now speak.** A decrypted variable value that fails
  re-validation is logged to doc._error_state instead of vanishing; PDF
  import table-detection crashes are logged; batch bitmap export closes each
  page image instead of holding every RGBA buffer until GC.
- **Cleanup.** Dead engine/textbox_flow.py removed (~1280 lines, replaced by
  document_paginate since v4.1.23). add_page() defaults only on None, an
  explicit width=0/dpi=0 is no longer silently replaced. The 4362x render
  test files use pytest tmp_path instead of hardcoded /tmp paths.

### Fixed, document-mode round (variables, header/footer, exports)
- **Batch preview values can no longer leak into the document.** While a row
  is previewed the inline editor shows a MIRRORED, value-substituted copy of
  the runs; a commit fired in that state (typically by clicking into the
  batch panel) used to write the preview values into the live object, and for
  a header/footer into the SHARED TEMPLATE, which repaginated, refreshed the
  panels, re-mirrored and looped (the "cyclic refresh" with a header
  variable). Commits now always restore and write the LIVE runs; a cancelled
  session drops the mirror snapshot.
- **Folding one variable into another no longer looks like a vanish.** The
  Objects panel labels a variable whose rid lives on several separate spans
  with the span count ("name (x2)"); the fold keeps every span's text (that
  was already correct) and now the panel says so.
- **Multi-select of variables in the Objects panel works.** Ctrl+clicking a
  second variable used to collapse back to one item: the currentItemChanged
  signal re-focused a single variable and the panel refresh re-selected only
  the primary. The single-select signal is now suppressed during a
  multi-selection, the canvas remembers the full vid list, and refreshes and
  _on_sel re-select the WHOLE set.
- **"Mark as link target" is discoverable.** New anchor toolbar button next
  to the link button (the right-click menu entry stays), so in-document links
  can actually be authored without hunting.
- **Header/footer members are visible in the Objects panel.** Container
  clones (and their templates) carry a "header"/"footer" badge in the row.
- **View-only marks never export.** The variable rainbow and the focus
  highlight are suppressed for every export (bitmap single/all/bytes, raster
  PDF, print) and restored afterwards; Show Variables ON no longer leaks
  colours into output. Both modes.
- **Header/footer editing opens on a SINGLE click** (double-click still
  works), and the guide band is WHITE with a neutral dashed outline instead
  of the blue tint.
- **Bitmap export dialog can export ALL pages at once** (both modes): a
  checkbox turns the chosen file name into a numbered series
  (name_p1.png, name_p2.png, ...) at the selected DPI/format.

### Changed, variables round 2 (feedback on the first round)
- **Linking variables no longer merges identities.** New model: the Link
  dialog LINKS variables via the column's extra_run_ids: one value drives
  every linked span, but each variable KEEPS its own rid, name and Objects
  panel entry (nothing shows "(x2)", nothing vanishes). Unchecking in the
  dialog unlinks. Redundant same-attribute columns of newly linked variables
  are dropped so two columns never fight over one span. Serialized
  (additive key), the old fold path is retired from the dialog.
- **Variable multi-select via CHECKBOXES.** The vrun rows in the Objects
  panel now carry a checkbox; checking several forms the shared set (rainbow
  highlight + shared-attributes targets). The rows are excluded from the Qt
  selection model entirely, so ctrl+click can no longer repaint rows oddly or
  touch the canvas object selection; a plain click still focuses the
  variable's span.
- **Typing after a span no longer extends it.** New text typed at the END of
  a variable / anchor / link span is plain (character formatting continues,
  the identity does not); typing INSIDE a span still belongs to it. This
  stops the rainbow from swallowing everything typed after a variable.
- **Link targets (anchors) can be removed** from the anchor toolbar button
  (it toggles on an existing target) and from the right-click menu
  ("Remove link target").
- **Optional link-target highlight.** View menu: "Show Link Targets" marks
  anchor spans with a translucent red -> blue gradient. Default OFF, and the
  export suppression covers it like the variable rainbow.

### Fixed, follow-up (header/footer click + undo caret)
- **Single-click into the header/footer band no longer breaks the editor.**
  The first implementation consumed the mouse PRESS, bypassing the normal
  press bookkeeping; the release handler then ran against a broken state
  (body rendered hidden/yellow, no caret, canvas stuck). The press now goes
  through the normal handling (commit + selection), the switch happens on
  RELEASE when the click didn't turn into a drag, deferred one event-loop
  turn, and the body's sticky re-entry is suppressed for the switch. Entering
  the band, typing, committing back to the template and re-entering all work.
- **Undo places the caret at the site of the UNDONE change.** Ctrl+Z used to
  restore the caret stored with the OLDER snapshot, which could be an
  unrelated spot far from the change being undone (disorienting jump). The
  caret now follows the step being left; redo behavior is unchanged; offsets
  are clamped to the restored text.

### Changed, inline switching REFACTOR (document mode)
- **One code path for switching text editing between the body, header and
  footer.** _switch_inline_to is now the single choke point: it commits the
  open session (restoring live runs when a batch preview mirror is active),
  suppresses the body's sticky re-entry, neutralises drag/lasso/pan state,
  starts the target editor, places the caret AT THE CLICK POSITION and keeps
  the viewport still; re-entrant calls are ignored. A single click on the
  header/footer band OR on the body switches editing synchronously on the
  press, and the matching release is swallowed, so no downstream handler ever
  sees a half-handled click (the previous two attempts each left some state
  behind). The body remains unselectable as an object; its rect is tested
  directly for the switch. Covered by a press+release integration test:
  body -> header -> type -> body -> header.

### Fixed, switching focus (why typing into the header did "nothing")
- **The switch now takes the keyboard focus.** The synchronous switch consumes
  the mouse press, so Qt's default focus-on-click for the view never runs;
  when the keyboard focus sat in a side panel (batch panel field, spinbox...),
  the freshly opened header editor never received a single keystroke: click
  appeared to do nothing. _switch_inline_to now activates the window, focuses
  the VIEW first and re-asserts the proxy/editor focus after opening.
  Covered by a test that parks the focus in a foreign QLineEdit and verifies
  the click pulls it into the editor chain.
- Debug logging along the whole switch path (doc_click_switch.hit /
  switch_inline.ok / start_failed / exceptions) so any remaining machine
  -specific refusal shows up in the Help debug log immediately.

### Fixed, header typing round 3 (preview lock + GL viewport focus)
- **An active batch-row preview no longer silently blocks typing.** The
  preview locks the template read-only and the editor swallowed every
  keystroke without a word. Now: clicking into a text box / band drops the
  preview (editing intent wins), and typing into an already open read-only
  editor drops it too and processes the key. Recording is untouched.
- **GL viewport focus.** On the GPU canvas (QOpenGLWidget viewport) the
  keyboard focus is now set on the VIEWPORT as well as the view, plus a late
  (60 ms) re-assert after the switch, because the GL surface can finish its
  activation after the first focus pass.
- **Key-delivery diagnostics.** The text editor logs every received key
  (Help -> Debug log) with the read-only flag and the header/footer role, so
  a machine where typing "does nothing" shows immediately whether keys reach
  the editor at all.

### Fixed, header typing FOUND IT (band overlay painted over the editor)
- **The header/footer band decoration hid the editor.** The band is painted
  in drawForeground, i.e. OVER every scene item -- including the band's own
  rendered text and the open inline editor. The 4.4.0 "white band" change
  gave it an OPAQUE white fill, so from that build on the header editor,
  its caret and everything typed were painted over by a white rectangle:
  the debug log proved keys arrived, text was inserted and committed, yet
  nothing was visible. The band now has NO fill (the page is already white,
  which is the requested look), keeps the neutral dashed outline + hint, and
  the decoration is skipped entirely while that band is being edited.
  Pixel-level regression test: the band interior must stay untouched when
  painted over a red canvas, and nothing may paint while editing.

### Fixed, UI flicker with an enabled header/footer
- **Endless repagination loop through band-style padding.** Pagination step 1
  forces padding to 0 on every document box (a body-layout rule) and reports
  the document changed; step 4 then re-applied the STORED band template style,
  which could carry a non-zero padding, re-arming the zero -> restore -> zero
  cycle. Result: every idle repagination reported changed=True while a
  header/footer was enabled, cascading into cache invalidation, re-render and
  panel repaints -- the batch panel (and more) flickered at the idle rate.
  Fixed on both ends: _apply_hf_style zeroes padding after applying the
  template (heals old documents that already store a padded style), and the
  band commit never persists padding into the template again. Regression
  test: a second no-op paginate must report changed=False even with a
  poisoned stored style.

### Fixed, tester round (BUG #10-#13)
- **BUG #10, batch image regression closed for good.** The raster renderer
  kept the 4.3.6.27 path fallback, but the VECTOR exports (PDF, SVG) still
  required a resource-store key, so batch-filled maps/flags/photos silently
  vanished from exports ("in one output they were there, in another not").
  Both exports now load a file-path resource_id from disk, AND
  apply_row_to_document materialises file_path image columns into the
  resource store (one resource per distinct path), so the document is
  self-contained after apply: save, reload and every output see the image.
- **BUG #11, fonts.** (a) doc.save(embed_fonts=True) / doc.embed_used_fonts()
  embeds every family+weight the document's text actually uses (pages, runs,
  tables, header/footer templates and containers) from the system font
  registry; idempotent, skips families already embedded. (b) Embedded fonts
  now resolve through a weight-aware registry built from the REAL family
  name in each font file's name table: "Nunito Sans" matches
  "NunitoSans-Regular.ttf", bold/italic pick the right file, and rich-text
  RUNS get embedded fonts too (before, only plain textboxes did, via a
  brittle filename substring).
- **BUG #12, zoom drift (WYSIWYG).** Text layout geometry is now always
  computed at ONE reference DPI (300) and scaled to the render DPI; glyphs
  still rasterise at the target DPI. Line breaks and positions are identical
  at every zoom level and every export DPI (test pins 96/150/300/432).
  Side benefit: the measurement caches stop re-measuring per zoom level.
- **BUG #13, effect-heavy pages on CPU.** Large-radius Gaussian mattes
  (drop/inner shadow, glows, bevel soften) now blur on a downscaled matte
  and upscale back -- a Gaussian is scale-invariant, parity measured at
  mean |diff| < 0.1/255. Together with the object cache the WYSIWYG editing
  path on a recipe-profile page (page-wide translucent background, card
  with 3 drop shadows, mono halftone strip, text) measures: first render
  0.36 s @150 dpi / 0.84 s @300 dpi, unchanged-page re-render 20/108 ms,
  TEXT EDIT re-render 29/125 ms (unchanged effect objects come from cache).

### Hardened, PDF output validity
- Reported "PDFs would not open" could not be reproduced on the current
  build: every export flavour (links + /Dest anchors, SMask images, effects,
  source attachment, raster, double export, document mode with header/footer
  and batch apply, parentheses/diacritics in URLs) passes qpdf --check and a
  byte-exact xref offset verification. Two guards added anyway: the writer
  now FAILS LOUDLY if any reserved object placeholder is left unfilled
  (that class of bug would previously produce a silently corrupt file), and
  a PDF validity battery (pypdf + xref byte checks) is part of the suite, so
  any structural regression trips the gate immediately.

### Added, batch export completed
- **Batch Generate covers the full matrix now.** Scope: current page or ALL
  pages. Formats: png/jpg (file per page with the [PAGE] token, auto-added
  as _p[PAGE] when the pattern lacks it), svg, pdf (single-page or
  multipage), and NEW: edof (single-page document or the whole document per
  row). The engine lives in edof.batch.generate.export_batch (UI-independent,
  CLI-ready); the Generate dialog gained the page-scope radios, the edof
  format and a "+ Page" token button.
- **Two source modes for the edof format.** "Integrate external sources
  into the file": one self-contained .edof (file-path images are
  materialised into resources by apply, used fonts embedded via
  embed_used_fonts). "Keep sources as files next to the .edof and ZIP": the
  row's document is written with a sources/ folder holding the referenced
  files, objects point at the RELATIVE path and the pair ships as
  <name>.zip -- an editable bundle. Document.load resolves relative
  resource paths against the .edof location, so an unpacked bundle renders
  from any working directory.
- **Filename tag templates apply everywhere.** [ROW_NUMBER[:pad]],
  [ROW_NAME], [{Header}[:upper|lower]] and the new [PAGE[:pad]] drive every
  generated name, with collision de-duplication.

### Performance, cookbook profiling (real-world batch document)
- Profiled on the actual cookbook (15-page batch template, 261 rows x 77
  columns, photo-heavy pages, halftone + multi-shadow recipe pages, plus the
  261-page book). Findings and fixes:
- **Halftone DPI floor was the big one.** The WYSIWYG lattice pin (24 px per
  halftone cell) forced recipe pages to render at ~470-600 DPI; one CPU
  render took 4.6 s, paid on first paint and every page-cache invalidation.
  The lattice is visually converged at 12 px/cell: floor halved and capped
  at 450. Recipe-page first paint: 4.6 s -> 1.2 s (~4x), cached re-render
  38 ms; the lattice stays zoom-stable (the floor still fixes its DPI).
- **Decoded-image cache.** Image sources were PIL-decoded from resource
  bytes on EVERY render; photo pages paid ~0.5 s per paint in JPEG decodes.
  Decoded RGBA sources are now a bounded LRU keyed by resource id + size
  (file-path images keyed by path + mtime). Photo page: 0.21 s -> 0.09 s
  after first decode; batch generate reuses decodes across rows.
- Object tile cache capacity 512 -> 768 (a 30-object page x several DPI
  buckets was near the cap and evictions caused re-renders).
- File load itself was never the problem: 0.10 s for the batch template,
  0.50 s for the 261-page book; panel rebuild with 261x79 cells 0.23 s.

### Performance, beta review
- QR recolouring dropped the per-pixel Python loop (O(w*h) per QR) for a
  1-bit mask + two flat fills.
- {variable} substitution in table cells precomputes the replacement map once
  per table instead of walking every variable for every cell (renderer and
  SVG export both).

### Format
- FORMAT_VERSION 4.2.20 -> 4.3.0. New optional keys: DocumentBody's
  header_objects + footer_objects, TextRun.link + anchor + anchor_name,
  Document.link_style. compatibility(): older files report "older" and load
  with automatic band-id migration; nothing else changed shape.

### Added, batch generation (final addition)
- **Single multipage output.** The Generate dialog (pdf/edof) offers "File
  per row" vs "Single multipage file": one file with every row's page(s)
  appended in row order. The single .edof is baked, fixed pages with the
  values filled in, no document body and no batch config, so it reopens
  exactly as generated and never re-paginates the rows away. Page ids of
  appended rows are freshly assigned; resources are merged. The filename UI
  switches with the mode: tags per row vs one plain filename (tag helpers
  disabled, preview shows the one name).
- **Progress + cancel.** Generation runs with a progress dialog (row x of
  y) and a working Cancel; the UI no longer freezes. Engine side:
  export_batch(progress=callable) is called between rows, returning False
  stops cleanly (finished files stay, errors gets a "Cancelled" entry).
- **File menu entry.** "Generate batch..." sits in the File menu, so
  generation does not require opening the batch table dock.

### Added, image compression (small files)
- **Document.recompress_images(format, quality).** Re-encodes embedded image
  resources: "png" lossless, "jpeg" lossy at 1-100. Images with real
  transparency always stay lossless PNG (JPEG has no alpha), a resource is
  only replaced when the re-encoded bytes are SMALLER (never inflates), fonts
  and other non-image resources untouched. Returns (n, bytes_before,
  bytes_after). Batch: export_batch(image_format=, image_quality=) applies it
  to pdf/edof outputs, per row and single-file alike.
- **PDF export with JPEG images.** export_pdf(image_format="jpeg",
  image_quality=N) embeds images as DCT streams; alpha channels survive as a
  lossless /SMask over the JPEG base. Full-page rasterized pages (layer
  effects) use the same setting. Photo-heavy PDFs shrink by an order of
  magnitude.
- **Editor UI.** Export PDF dialog and the batch Generate dialog gained an
  "Images" choice (Lossless / JPEG 90 / 75 / 60 / 40 %). File menu: "Save
  optimized copy..." saves a re-encoded copy (deep copy, the open document
  keeps its originals) and reports MB before/after.

### Fixed
- **Editor PDF export TypeError.** The Export PDF dialog called
  doc.export_pdf(embed_source=...) but the Document wrapper did not accept
  the kwarg, so the export died with a TypeError into the generic error
  dialog. The wrapper now accepts and forwards embed_source.

### Changed, Python floor
- **Minimum Python is 3.10.** Python 3.9 reached end of life in October
  2025 and the PyQt6 editor tests segfault on it in CI (exit 139) while
  3.10+ passes cleanly. requires-python is >=3.10, classifiers and the CI
  matrix (3.10 / 3.11 / 3.13) updated, README and INSTALL adjusted.

### Fixed, CI workflow
- **GitHub Actions test job could not run the suite.** It installed only
  [dev,qr], but the suite includes the PyQt6 editor/panel tests, so the
  3.11 job died at collection and cancelled the matrix, which blocked the
  PyPI publish job. The workflow now installs [all,dev] + pypdf, installs
  the Qt system libraries (libegl1 and friends) on the runner and runs
  pytest with QT_QPA_PLATFORM=offscreen.

### Fixed, release deploy
- **numpy is now a declared core dependency.** The deploy test gate (fresh
  venv) exposed that numpy was a silent hard requirement all along: the
  render engine imports it at runtime for gradients (_render_gradient),
  16-bit export and the layer effects (bevel, halftone, long shadow,
  chromatic aberration, EDT, ...), so a clean "pip install edof" crashed on
  the first gradient render. numpy>=1.24 moved into
  [project.dependencies]; README and INSTALL updated (core = Pillow +
  numpy). Five older test modules also gained pytest.importorskip("numpy")
  as a defensive measure.

### Fixed, unique variable names (major)
- **Two columns could share a name.** Creating variables could produce
  identically named columns, which made the batch table ambiguous and broke
  [{Header}] filename tags and CSV header matching. Names are now unique by
  construction, case-insensitive, enforced at the model level:
  BatchConfig.add_column auto-suffixes a taken custom name (Name_2, ...) and
  gives colliding unnamed columns a generated name; new helpers
  header_in_use / unique_header / system_header.
- **Systematic default names are persisted.** An unnamed column now stores
  its systematic label ("textbox-1.text", "shape-1.fill-color", object's own
  name wins over the type prefix) as its real name instead of being an
  empty-name display-only label.
- **Every naming path checked.** Add text variable dialog auto-suffixes a
  typed name that is already used (status shows the final name); the table
  header rename rejects taken names with a warning (blank regenerates a
  unique name); Rename variable flows auto-suffix against foreign columns;
  the editor's fallback inlinetextNN counter now also counts run var_names,
  not only columns.

### Docs, README rework (beta tester feedback)
- The README (PyPI landing page) now leads with a plain-language pitch:
  what edof actually does, who it is for, and why to use it instead of
  Word + export, a PDF editor, or Photoshop (concrete pain points, not
  feature dumps). Real-world use cases up front: invoices, card decks,
  certificates, catalogs, posters.
- 3D Batches promoted to the headline feature with a short runnable
  example (multiple page templates sharing variables, any parameter as a
  column, per-row files or one multipage document) and a card-deck
  walkthrough in words.
- "What's new in 4.4.0" section: batch export engine, hyperlinks,
  header/footer containers, image compression, WYSIWYG zoom stability.
  Status section refreshed to include the 4.4.0 subsystems. The docs
  landing page opens with the same pitch.

### Docs, final verification pass
- Every python code block in docs/ (reference, advanced, cookbook,
  quickstart) is now executed as validation. Fixed the drift that had crept
  in: discovered_fonts -> list_system_fonts, CellBorder has no style kwarg,
  to_mm/from_mm are unit converters (not dpi), VariableStore uses get_def /
  all_values / reset_all / undefine (docs claimed exists/get_definition/
  values/unset), define_variable takes description= (docs claimed label= /
  help= / max_length=), export_to_bytes takes page_index= and has no pdf
  format, render_page takes (page, resources, variables), make_table has no
  style= presets (use header_bg/alt_bg), encryption signature listings moved
  to text blocks.
- page.row() and page.column() are now real context managers (the helpers
  page showed "with page.row(...)" that did not actually work; the
  metric-tiles example now uses the real page.add_metric API).
- New reference page 15-batch.md: the 3D Batch model (ObjectRef,
  BatchColumn incl. run_id/extra_run_ids, BatchRow, BatchConfig), the
  attribute registry (describe_object, find_descriptor, apply_value) and
  pointers to the export engine and filename tags.
- mkdocs nav completed (12-effects and the effects-poster cookbook were
  missing entirely; 15-batch added); mkdocs build --strict is clean.
  Repo-relative links out of docs/ replaced with GitHub URLs.

### Docs
- Complete documentation pass for 4.4.0. New reference pages: Hyperlinks
  (13-hyperlinks.md: model, editor and viewer behaviour, document link style,
  URL validation, PDF/SVG export) and Header & Footer (14-header-footer.md:
  band text and tokens, canonical band ids, object containers, batch
  variables in bands, storage keys). Updated: Styles (TextRun link/anchor
  fields), Variables (text run variables, panel checkboxes, linking via
  extra_run_ids, change range, boundary typing), Export (export_batch engine,
  scope and formats, sources modes, filename tags, font embedding), Desktop
  editor (document mode workflow, single click bands, link UI, undo caret,
  PNG all pages), file format internals (all 4.3.0 additive keys). API.md
  regenerated; mkdocs nav and docs index extended.

## [4.3.6.28] - 2026-07-02

### Added
- **Change range for an existing text variable.** Objects panel, context menu on
  a variable: "Change range (use editor selection)". The current selection in
  the inline editor becomes the variable's new span; the rid, every batch column
  bound to it and all record values are kept. Before, re-spanning meant deleting
  the variable (losing its columns) and creating it again.
- **Span highlight for the focused batch column.** Selecting a cell or column in
  the bottom batch table highlights, on the canvas, the exact text span that
  column's values drive (rainbow mark), in the normal render AND in the batch
  row preview, independent of the Show Variables toggle. Clears when the column
  focus leaves run-bound columns or the selection changes.

### Fixed
- **Removing or renaming a variable while the inline editor was open got
  reverted by the next reflow.** Remove/rename only touched the page objects'
  runs; the open inline editor holds a COPY of them, and the reflow refreshes
  the page box FROM that copy, resurrecting the old rid/var_name (same class of
  bug as the 4.3.6.23 merge fix). Both ops now mirror the edit into the open
  editor's runs and sync.
- **Dead batch columns after a variable's text was deleted.** The orphan cleanup
  dropped the columns from the config but never rebuilt the batch panels, so the
  bottom table (and the template panel) kept showing a column that no longer
  existed. The cleanup now rebuilds them.
- **Variable operations now land as exactly ONE labelled undo step.** Remove
  pushed two snapshots (before and after) plus the coalesced object-edit burst
  pushed a third, so undoing a remove cost dead Ctrl+Z presses; merge and rename
  pushed only the pre-state; add-variable and attribute toggles relied on the
  generic burst ("Edit"). All variable ops (add, merge, rename, remove,
  attributes, change range) now flush pending edit bursts first and commit one
  named step.
- **Gradient stop alpha was ignored on rect/ellipse shapes.** The fill branch
  replaced the gradient's alpha channel with the shape mask, so stops fading to
  alpha 0 rendered fully opaque. The mask now multiplies with the gradient's own
  alpha (matching the path branch) and fill_opacity is applied there too.
- Headless robustness: the module-level render signals object is recreated when
  Qt tore it down after a previous QApplication (offscreen test runs crashed
  every canvas constructed afterwards).

## [4.3.6.27] - 2026-06-16

### Fixed
- **BUG #7: object opacity distorted halftone (and other effects) instead of
  scaling them linearly.** Opacity was baked into the dispatch buffer BEFORE the
  effects ran, and halftone uses the layer alpha to size its dots -- so opacity
  fell off ~cubically (0.5 opacity gave ~0.1 coverage, 0.25 gave ~0.01) as it
  shrank the dots AND faded them. The object body + effects now render at full
  opacity into a separate layer whose alpha is scaled by opacity once, at the
  end, so opacity is linear (0.5 -> 0.5 coverage) and the dot raster keeps its
  geometry. Only engages when opacity < 1; the opacity == 1 path is unchanged.
- **BUG #8: batch could not fill an image from a file path.** The ImageBox batch
  descriptor set resource_id directly to the CSV value, but that value is a file
  PATH, not a resource key, so the renderer found nothing. The image render now
  resolves resource_id as a filesystem path when it is not a known resource key
  (the descriptor is labelled "Image (file/resource)"), so a batch column of
  image paths fills photos/backgrounds as expected.

### Validation
- Four tests: opacity linear with/without effects, image-from-path render, batch
  descriptor image path. Full suite 525 passed. FORMAT_PATCH 20.
## [4.3.6.26] - 2026-06-16

### Performance
- **Gradient fill vectorised (~100x faster).** _render_gradient ran a per-pixel
  Python loop calling color_at() for every pixel -- ~2.2M calls for an A4 page
  @150dpi, so a full-page gradient took ~7.6s (35x a solid fill) and scaled
  ~O(dpi^2). It now builds a 2048-entry colour LUT once (np.interp over the
  stops), computes the per-pixel parameter with numpy broadcasting, and maps it
  through the LUT with a single fancy-index. Output is identical to within 1/255
  per channel. A full-page linear gradient @150dpi drops from ~7.6s to ~40ms;
  polygon/path gradients (blobs) benefit the same way.
- **PNG export ~6x faster.** Saving used optimize=True, which runs PIL's
  exhaustive filter search -- ~1s per page on a many-colour gradient image for a
  marginal size win (155 vs 265 KB). Now uses compress_level=6 (zlib default).
- Net effect: an A4 gradient page export drops from ~7.6s to ~0.3s @150dpi
  (~19.5s to ~1.2s @300dpi); a page with several gradients renders in a fraction
  of a second, so a large batch runs in minutes rather than tens of minutes.

### Validation
- Five tests: gradient colours at stops (linear/radial/multi-stop), alpha
  interpolation, and a speed sanity check. Full suite 521 passed. FORMAT_PATCH 20.
## [4.3.6.25] - 2026-06-16

### Fixed
- **auto_shrink STILL overflowed the box width (the .24 fix was not enough).**
  The fit check (find_fitting_scale/_runs_fit) measured with a private
  _layout_runs, but the RENDER lays text out with layout_runs. The two tokenise
  text into segments differently, so their summed line widths disagreed by a few
  px: the fit said "fits", the render wrapped a hair wider and clipped the last
  word (laminovaciho -> laminovacih). _runs_fit now measures with the SAME
  layout_runs the renderer uses, so the chosen scale genuinely fits.
- **BorderStyle was documented but did not exist (ImportError).** Added the
  BorderStyle dataclass (enabled, color, width, style, radius) with save/load,
  exported from the top level, and the TextBox border render now honours enabled
  (skips when False), radius (rounded corners) and a dashed style. A plain
  StrokeStyle still works there too.
- **Shape.from_svg_path with absolute coords rendered nothing.** It left the
  default 50x30 transform, so an absolutely-placed path fell outside its box and
  was clipped away. from_svg_path now derives the transform from the path bbox
  and re-origins the path to local (0,0), so absolute or local coords both work.
- **edof.new() get_page(0) raised a bare IndexError on the empty document.** It
  now raises a clear message telling you to call add_page() first; the new()
  docstring states the document starts empty (0 pages) by design.

### Added
- **effects_enabled=False now warns instead of being a silent no-op.** When an
  object has effects but the master switch is off (the default on a brand-new
  object), the render emits a one-time RuntimeWarning per object.

### Validation
- Five regression tests (fit==render width, BorderStyle, from_svg_path bbox,
  empty-doc get_page message, effects-disabled warning). Full suite 516 passed.
  FORMAT_PATCH 20.
## [4.3.6.24] - 2026-06-16

### Fixed
- **auto_shrink overflowed the box width with some fonts.** Line width was
  measured as getbbox[2]-getbbox[0], which subtracts the first glyph's LEFT
  side bearing. Rendering starts at the pen, so the rightmost pixel lands at
  getbbox[2]; for fonts with a noticeable left bearing the line was under-
  measured and wrap let a line through that then clipped on the right edge.
  Width is now max(advance, visual-right-edge), so wrap stays inside the box.
- **long_shadow rendered nothing that extended past the object.** The shadow
  matte was cropped to the INPUT alpha's bbox, so a shadow thrown beyond the
  object's own box was clipped away entirely. The alpha is now padded by the
  throw length (+ blur) on every side and composited at the shifted origin.
- **halftone ht_color_mode="mono" produced cyan/magenta/black dots.** "mono"
  was not implemented and fell through to the CMYK branch. It now paints a
  single ink -- the layer's own colour, so a teal fill gives teal dots -- with
  dot size tracking darkness on a transparent background, and the dot capped to
  about one cell so the raster stays visible.

### Notes
- All three effects require the object's master switch effects_enabled=True
  (the default for a brand-new object is False). Setting an effect alone does
  not enable it.

### Validation
- Three regression tests (bearing width, shadow past bbox, mono ink colour).
  Full suite 511 passed. FORMAT_PATCH 20.
## [4.3.6.23] - 2026-06-16

### Fixed
- **Folding variables together did nothing while the body was being edited.**
  In document mode the body's runs live as a COPY on the inline editor, and the
  reflow refreshes the page box FROM that copy. So a merge applied to the page
  box was immediately overwritten by the stale copy -- the variables never
  actually folded. The merge is now also applied to the inline editor's runs
  (and synced) before the reflow, so it sticks. This is why "Link" appeared to
  do nothing.

### Added
- **Feedback after folding.** The status bar now confirms how many variables
  were folded in, since the column list can look unchanged (one column before
  and after).

### Validation
- New test reproducing the inline-editor case and asserting the merge sticks.
  Full suite 508 passed. FORMAT_PATCH 20.
## [4.3.6.22] - 2026-06-16

You can now make each string its own variable, then link them together in the
batch editor -- one column drives several strings, like linking normal objects.

### Added
- **Fold variables together from the Link dialog.** For a run variable the
  "Link objects to variable" dialog now also lists the OTHER run variables
  (strings) in the document. Checking one folds it into the current variable:
  its span takes the current variable's identity (rid + name) and its redundant
  column is dropped, so a single column drives every folded-in string. This is
  the in-document counterpart to linking whole objects -- the workflow you asked
  for: make each string a variable one at a time, then link them on the right.
  Undoable.

### Validation
- New tests for folding variables together and for the Link dialog listing other
  variables + collecting them on accept. Full suite 507 passed. FORMAT_PATCH 20.
## [4.3.6.21] - 2026-06-16

The same variable can now sit on several spans in ONE object (body, header,
anything) and one batch value fills every occurrence at once.

### Fixed
- **A run variable only updated its first occurrence.** When several spans in
  one object shared a rid, applying a batch value changed only the first run.
  It now writes to EVERY run carrying that rid, so the same variable on multiple
  spans all update together (e.g. a restaurant name repeated through the body).

### Added
- **Add a selection to an existing variable.** The add-variable dialog has a
  "Variable" dropdown: keep "New variable", or pick "Add to: <name>" to give the
  selected span an existing variable's rid (no new column). One column then
  drives all its spans. This is the in-document equivalent of linking -- it
  targets spans inside the same text object instead of whole other objects.

### Validation
- New tests for the all-occurrences write and for adding a selection to an
  existing variable. Full suite 505 passed. FORMAT_PATCH 20.
## [4.3.6.20] - 2026-06-16

Variable editing polish: fixes a phantom-selection bug near variables, makes
variable names unique and editable, warns before deleting a variable's last
character, and makes the Link dialog list real OTHER objects.

### Fixed
- **Phantom selection after deleting near a variable.** A click leaves the
  anchor sitting on the cursor; backspace/delete then moved the cursor without
  clearing the anchor, leaving a one-character phantom selection that the next
  keystroke would delete (so deleting a space after a span quietly armed the
  next character for deletion). Delete operations now clear the anchor.
- **Duplicate variable names.** The default-name counter only looked at batch
  columns, but a no-attribute variable has no column -- so two of them both got
  "inlinetext01". It now also counts var_names already on the runs.
- **Link dialog listed the source object.** For a run variable the dialog
  offered the very object the variable lives on (in document mode, the body --
  the only object), which is a no-op. It now excludes the source and lists real
  OTHER objects; the source stays the implicit primary target and chosen objects
  become extra targets. Shows a hint when there's nothing else to link.

### Added
- **Rename variable.** Right-click a variable in the Objects panel ->
  "Rename variable" updates its name on the runs and on every bound column
  (keeping the attribute suffix for non-text columns). Undoable.
- **Warning before deleting a variable's last character.** Backspace/forward-
  delete of the final character of a variable span now asks for confirmation,
  since it removes the variable and all its columns.

### Validation
- New tests for the phantom-selection fix, unique names, rename, the last-char
  warning helper, and source exclusion in the Link dialog. Updated the two older
  link-dialog tests for the new source-exclusion behaviour. Full suite 503
  passed. FORMAT_PATCH 20.
## [4.3.6.19] - 2026-06-16

Variables are now first-class entities: a named span can exist with no attribute,
and deleting its text removes the variable and all its columns (undoable).

### Added
- **Make a variable with no attribute.** The add-text-variable dialog no longer
  requires ticking an attribute -- you can just name a span as a targetable
  entity (rid + name) with zero batch columns. Columns can be added later.
- **Remove variable from the Objects panel.** Right-click a text variable ->
  "Remove variable" clears its rid from the runs AND drops every batch column
  bound to it. Undoable.

### Fixed
- **Deleting a variable's text left the entity (and its columns) behind.** When a
  variable's text is fully deleted its run -- and rid -- is gone, but the Objects
  panel still listed it and its batch columns stayed. The editor now detects when
  the set of variable rids changes and drops orphan columns + refreshes the
  panel, so the entity and its columns disappear. Verified undo restores both the
  text and the column.

### Validation
- New tests for no-attribute creation, entity removal, and the delete-then-undo
  round trip. Full suite 498 passed. FORMAT_PATCH 20.
## [4.3.6.18] - 2026-06-16

Fixed several run-variable issues: removing a variable, the link dialog in
document mode, the font / bold / italic editors, and current-value placeholders.

### Fixed
- **Removing a variable left its rainbow and its Objects-panel entry behind.**
  A run variable also lives as rid/var_name ON the runs, which is what drives the
  highlight and the panel. Removing the column now also strips the rid/var_name
  from every run that carries it (across all pages), then reflows and refreshes,
  so the highlight and the panel entry disappear too.
- **The link dialog was empty in document mode -- not even the variable's own
  object showed.** The document body has runs but no object-level 'text'
  descriptor, and the filter required that descriptor. The filter now lists any
  object that carries runs (including the body) or has a 'text' descriptor, so
  the source and other text objects appear and can be linked.
- **A run font variable had no font dropdown.** The font picker was only wired
  for object-level style.font_family; it now also applies to run.font_family.
- **A run bold / italic / underline / strikethrough variable couldn't be set.**
  Those dropdowns were empty because the choices came from an object descriptor
  that doesn't exist for run attributes. They now use the true/false choices.
- **Number and colour fields now show the run's current value as greyed
  placeholder text** when no override is set, so you can see what you'd change.

### Validation
- New tests for remove, document-mode link, and the run field editors. Full
  suite 496 passed. FORMAT_PATCH 20.
## [4.3.6.17] - 2026-06-16

Fixed the first text variable after opening a new document doing nothing.

### Fixed
- **Right after New / Open, the first text variable made via right-click or the
  toolbar did nothing: no column, no rainbow, nothing in the Objects panel.** The
  batch panels only rebound to the document when their tab was opened, so until
  then the make-variable flow saw a None document (cfg was None) and returned
  early. The canvas now emits a documentChanged signal on every document swap and
  the batch panels rebind to it, so the very first variable works -- it appears
  in the Objects panel, colours, and shows in the batch editor with its column.

### Validation
- New regression test (full editor, new doc, first variable). Full suite 493
  passed. FORMAT_PATCH 20.
## [4.3.6.16] - 2026-06-16

Made "Link to objects" work for run-text variables, so a text-span variable can
drive other text objects.

### Added
- **Run-text variables can be linked to other text objects.** Previously the
  link dialog for a run variable was empty (a run variable binds to a specific
  rid, which no whole object carries). Now the dialog lists every text object on
  the page, and linking one makes the variable fill that object's whole text
  with the value. The source span still resolves through its own rid, so the
  same value lands in the span and in each linked object at render / generate
  time. The link button is back for run variables.

### Validation
- New tests for the run-variable link dialog and multi-target apply. Full suite
  492 passed. FORMAT_PATCH 20.
## [4.3.6.15] - 2026-06-16

Fixed right-click / toolbar "make variable" not colouring the text and not
listing the variable in the Objects panel, and hid the link-to-objects button
for run variables (where it could never show anything).

### Fixed
- **Making a variable from a text selection via the right-click menu (or the
  toolbar/Ctrl+Shift+B) did nothing useful the first time: no rainbow, and
  nothing in the Objects panel.** The flow handed off to the wrapper batch panel,
  which has no _add_text_variable, so it fell through to a bare fallback that
  skipped the textbox sync, the show-variables toggle, and the Objects-panel
  refresh -- while the panel's own "Add variable" button (on the template panel)
  worked. The right-click/toolbar flow now hands off to the template panel like
  the button does, so the variable is synced to the textbox, the rainbow turns
  on, and it appears under its textbox in the Objects panel right away. The
  fallback (used only when no panel exists) also got the sync + refresh, as a
  safety net.

### Changed
- **The link-to-objects button is hidden for run variables.** A run variable
  (the text/colour/size of a specific text span) is bound to one run, not to
  whole objects, so "Link to objects" could never list anything (it needs a
  run_id the object level does not have) and the dialog came up empty. The
  button now shows only for object-level variables.

### Validation
- New regression test for the template-panel hand-off. Full suite 490 passed.
  FORMAT_PATCH 20.
## [4.3.6.14] - 2026-06-16

Fixed text variables vanishing in document mode, moved the shared-attribute
editing into a dialog, and added a toolbar toggle for the variable highlight.

### Fixed
- **Making a variable from text in the body did nothing visible: no rainbow, and
  nothing in the Objects panel.** In document mode the body is held in an inline
  editor whose runs are a COPY; make_variable_from_selection set the rid only on
  that copy, then the reflow reloaded the editor from the textbox (which still
  lacked the rid) and the variable was lost instantly. The rid is now pushed back
  to the textbox before the reflow, so the variable persists, highlights, and
  shows up under its textbox in the Objects panel.

### Changed
- **The shared run-attribute editor is now a dialog, not a fixed checklist in the
  batch panel.** Right-click selected variables in the Objects panel ->
  "Edit shared attributes…" opens a dialog with one tri-state checkbox per run
  attribute (checked = variable on all, mixed = left unchanged). This matches the
  object Add-variable flow. The fixed checklist that used to sit in the batch
  panel has been removed.

### Added
- **Toolbar button for the variable highlight.** A rainbow toggle on the main
  toolbar shows/hides the rainbow underlay on variables, kept in sync with the
  View > Show Variables menu item.

### Validation
- Tests updated for the dialog flow. Full suite 490 passed. FORMAT_PATCH 20.
## [4.3.6.13] - 2026-06-16

The shared run-attribute controls now also appear directly in the batch panel
when variables are multi-selected (variant 2 of the shared-attribute editing).

### Added
- **Batch panel shows a "Shared attributes" box when variables are selected in
  the Objects panel.** It lists every run attribute (Text, Font, Font size,
  Colour, Highlight, Bold, Italic, Underline, Strikethrough) as a tri-state
  checkbox: checked = a variable on all selected, partially checked = on some,
  unchecked = on none. Toggling adds or removes that attribute as a batch
  variable across every selected variable at once. The box hides when the
  selection isn't a pure set of variables.

### Validation
- New test: shared-attribute box shows on variable selection and its checkboxes
  toggle the attribute across all targets. Full suite 490 passed. FORMAT_PATCH 20.
## [4.3.6.12] - 2026-06-16

Text-variable objects now behave as real, selectable objects in the Objects
panel, and a multi-selected set of variables can have their common attributes
edited in one go.

### Fixed
- **Variables didn't appear in the Objects panel until something else forced a
  refresh.** Creating a variable only emitted the batch 'changed' signal, which
  doesn't rebuild the Objects panel. It now emits objectChanged too, so the new
  variable shows up under its textbox immediately.
- **Variables couldn't be selected by clicking them in the panel.** Clicking a
  variable focused its textbox (via set_sel_id), and the resulting panel refresh
  re-selected the parent textbox row, so the variable never stayed selected. The
  panel now keeps the virtual item selected while a variable is the active focus.

### Added
- **Right-click a selected variable (or several) in the Objects panel for a
  shared run-attribute menu.** Each attribute (Text, Font, Font size, Colour,
  Highlight, Bold, Italic, Underline, Strikethrough) is a checkable item;
  toggling it adds or removes that attribute as a batch variable for EVERY
  selected variable at once. Mixed states are shown as "(mixed)".

### Notes
- Surfacing the same shared-attribute controls inside the batch panel after a
  multi-select is the next step.

### Validation
- New tests: shared run-attribute toggle across multiple variables; virtual
  selection sticks across a refresh. Full suite 489 passed. FORMAT_PATCH 20.
## [4.3.6.11] - 2026-06-16

Multi-select of text-variable objects in the Objects panel now highlights them
all at once.

### Added
- **Selecting several variables in the Objects panel rainbow-highlights all of
  them** (and focuses the first), matching the multi-select principle used for
  regular objects. Variables in the same textbox light up together. The rainbow
  marker now takes a set of rids rather than a single one.

### Notes
- Editing the common run attributes of a multi-selected set of variables in one
  go is the next step.

### Validation
- Full suite 487 passed. FORMAT_PATCH still 20.
## [4.3.6.10] - 2026-06-16

Fixed text selection in the body being wiped instantly whenever a header or
footer is enabled.

### Fixed
- **Any selection in the body cleared immediately with a header/footer enabled.**
  When a header/footer shrinks the body box, the body text overflows, and an
  overflowing body restarts the idle balance timer with a 0 ms delay -- so the
  balance pass runs on every render. That pass calls refresh_from_tb to reload
  the runs, and it was dropping the selection anchor every time, so any selection
  (drag, Shift+arrow, Ctrl+Shift) vanished the instant it was made. refresh_from_tb
  now keeps the anchor (clamped to the new length), so selection survives the
  balance pass. (The 4.3.6.9 sticky-editor restore stays; this was the real
  cause of "selection doesn't work with a header".)

### Validation
- New test: refresh_from_tb keeps the selection anchor (and clamps it if the
  content shrank). Full suite 487 passed. FORMAT_PATCH still 20.
## [4.3.6.9] - 2026-06-16

Fixed body text selection breaking after a header/footer was edited or toggled.

### Fixed
- **Text selection (and typing) in the body stopped working once a header or
  footer was involved.** In document mode the body is held in a sticky inline
  editor; after editing a header/footer the commit path repaginated and returned
  early, skipping the re-entry that puts the editor back on the body -- so the
  body had no active editor and clicks/drags did nothing. The sticky editor is
  now restored on the body after a header/footer edit, and also after enabling or
  disabling a header/footer in Page setup.

### Validation
- Full suite 486 passed. FORMAT_PATCH still 20.
## [4.3.6.8] - 2026-06-16

First cut of virtual text-variable objects: text variables now appear in the
Objects panel and can be picked there instead of hunting for the exact run.

### Added
- **Text variables show in the Objects panel** as virtual children under the
  textbox that holds them (a rainbow chip + the variable name), one per variable.
  This is also how you see which variables an object already uses (so you don't
  duplicate them).
- **Clicking a variable in the panel focuses its span**: it selects the textbox,
  enters inline edit, selects the run, scrolls it into view, and rainbow-marks it
  -- even when Show Variables is off -- so the otherwise hard-to-click span is
  easy to find. The mark clears when you select something else.

### Changed
- **Rainbow marker opacity lowered to ~25%** (from 50%), still diagonal at 8mm.

### Notes
- Multi-selecting variables to edit their common run attributes together (the
  shared-attributes flow) is the next step; for now a multi-select of variables
  is ignored rather than clearing the real selection.

### Validation
- New test: _variable_runs lists variables de-duped by rid. Full suite 486
  passed. FORMAT_PATCH still 20.
## [4.3.6.7] - 2026-06-16

Fixed a crash when deleting text caused a repagination, and stopped header/footer
variables from corrupting the document.

### Fixed
- **IndexError after deleting text in document mode.** Deleting text can shrink
  the page count (repagination), but the current page index wasn't clamped, so
  the next overlay/ghost pass indexed a page that no longer existed and crashed
  (and selection stopped working afterwards). The page index is now clamped after
  a render and in the ghost pass.
- **Making a variable in the header/footer no longer wipes the text / crashes.**
  Header and footer text isn't a normal page object -- its runs live on
  doc.body.header_runs and aren't addressable by the batch ref system yet -- so a
  variable there lost the text. It's now blocked with a clear message in both the
  right-click / toolbar path and the panel's Add variable, until the header/footer
  rework lands.

### Validation
- Full suite 485 passed. FORMAT_PATCH still 20.
## [4.3.6.6] - 2026-06-16

Fixed an empty batch cell inheriting a previous row's value (a recorded run
value leaking onto the template), and tuned the rainbow marker.

### Fixed
- **An empty cell now resets the attribute to the template default**, not to
  whatever a previous row left. Root cause: stopping a recording restored the
  template's object attributes and effects but NOT its rich-text runs, so a value
  recorded into a run (e.g. text colour) stayed on the base template. A later row
  that left that cell empty then inherited the stale value instead of resetting.
  Recording restore now restores runs wholesale, so empties reset correctly.
  (Empty semantics are "set to template default", as intended.)

### Changed
- **Rainbow variable marker** is now diagonal, one hue cycle per 8mm, at 50%
  opacity (was 3.5mm horizontal).

### Validation
- New test: stopping a recording restores rich-text runs to the template (colour
  and text), so a later empty cell resets. Full suite 485 passed.
  FORMAT_PATCH still 20.
## [4.3.6.5] - 2026-06-16

Fixed the real reason inline (document-mode) text didn't change under a batch
preview, and tuned the rainbow marker.

### Fixed
- **Batch preview now changes the document-body text.** In document mode the
  body is shown by the always-on inline editor, which keeps its OWN copy of the
  runs -- so the batch preview rendered on the canvas underneath was hidden and
  the body kept showing the un-substituted text (looked like the variable did
  nothing). The preview now mirrors into the editor: previewing a row loads that
  row's substituted runs into the body editor, and leaving preview restores the
  live runs. This is the core "variables don't change inline text" bug.

### Changed
- **Rainbow marker** is now a diagonal sweep, one full hue cycle per 8mm, at 50%
  opacity (was 3.5mm horizontal at higher opacity).

### Validation
- New test: previewing a row mirrors the substituted runs into the inline editor
  and restores the live runs on exit. Full suite 485 passed / 3 skipped.
  FORMAT_PATCH still 20.
## [4.3.6.4] - 2026-06-16

Fixed the "stuck variable" (duplicate columns on one span) and made the marker a
rainbow gradient.

### Fixed
- **Duplicate run columns no longer fight each other.** Making a variable twice
  on the same span created two run.text columns on the same rid; the last one
  won, so the text was stuck on one value no matter which row was selected. Now
  the picker reuses the existing column instead of duplicating it, and loading a
  document drops any leftover duplicates (same run_id + attr_path), keeping the
  first. This repairs files that already have the duplicate.

### Changed
- **Variable marker is now a rainbow gradient** drawn under the span — one full
  hue sweep per 3.5mm, keyed to absolute x so it flows continuously across
  glyphs and runs — instead of the flat blue tint.

### Validation
- New test: a loaded doc with duplicate run.text columns on one rid keeps one,
  and the variable then differs per row. Full suite 484 passed / 3 skipped.
  FORMAT_PATCH still 20.
## [4.3.6.3] - 2026-06-16

Fixed the variable-text round trip: right-click now creates a record (so the
variable actually does something), every entry point uses the same attribute
picker, more run attributes are offered, the highlight turns on automatically,
and the editor's right-click menu gained cut/copy/paste.

### Fixed
- **Right-click / toolbar / shortcut now create the record too.** Previously the
  right-click path added a column but no record, so there was nothing to edit
  and changing the value did nothing. All three entry points now hand off to the
  same flow as the panel's "Add variable" (attribute picker + auto record +
  value seeding), so making a variable works end to end.
- **More run attributes** in the picker: added Font, Highlight/marker
  (background), Underline and Strikethrough alongside Text, Font size, Colour,
  Bold and Italic.
- **The variable highlight turns on automatically** when you make a variable, so
  you immediately see which span it is (and the View-menu "Show Variables" check
  stays in sync). It's still toggleable (View menu, Ctrl+Shift+H).
- **Cut / Copy / Paste** added to the text editor's right-click menu (disabled
  appropriately while the template is read-only under a preview).

### Notes
- Several variables in one text already work: select another span and make it a
  variable; each carries its own id. Changing the SPAN of an existing variable
  (re-ranging) and highlighting exactly which span a row affects during preview
  are not done yet.

### Validation
- New test: the extended run attributes (font/background/underline/
  strikethrough) resolve and write by rid. Full suite 483 passed / 3 skipped.
  FORMAT_PATCH still 20 (UI/behaviour only).
## [4.3.6.2] - 2026-06-16

Fixed three problems with making text variables: right-click in document mode,
the 3D Batch "Add variable" attributes for selected text, and a preview-mode
template-edit trap.

### Fixed
- **Right-click on selected text now offers "Make variable from selection"**
  (and "Remove variable" on an existing one), including in document mode. The
  canvas's context-menu policy was swallowing the right-click before the text
  editor saw it, so the option never appeared; the canvas menu now handles it
  when the click is over the active text editor with a selection.
- **3D Batch "Add variable" with a text selection now offers the run's
  attributes** — Text, Font size, Colour, Bold, Italic — instead of the body
  object's transform. Previously it showed the body's rotation/geometry, which
  is meaningless for variable text (you don't rotate the whole body per row).
  Choosing attributes assigns a stable rid to the span and adds one column per
  attribute, all bound to that rid.
- **Template is read-only while previewing a batch row (and not recording).**
  Editing the canvas under a row preview silently changed the BASE template
  (the preview hid it, so it looked like nothing happened until you left
  preview). Now text typing/formatting, object move and resize/rotate are
  blocked during preview; you record (edits captured into the row) or turn off
  the preview to edit the template. Selection, navigation and copy still work.

### Validation
- New tests: every run attribute resolves by rid (text/font_size/colour/bold/
  italic); a read-only editor blocks typing but still navigates. Full suite
  482 passed / 3 skipped. FORMAT_PATCH still 20 (UI/behaviour only).
## [4.3.6.1] - 2026-06-16

Made variable text discoverable: right-click menu, a keyboard shortcut, a
clearer toolbar button, and a Show-Variables highlight. (Follow-up to 4.3.6.0,
where the only way to make a variable was an obscure "{x}" toolbar button.)

### Added
- **Right-click "Make variable from selection"** in the text editor. With a
  selection it creates the variable (prompting for a name); on an existing
  variable it offers "Remove variable" (keeps the text). This is what the
  workflow expected; 4.3.6.0 only had the toolbar button.
- **Ctrl+Shift+B** makes the selection a variable (Ctrl+Shift+V is paste-plain,
  so B = batch variable).
- **Show Variables toggle** (View menu, Ctrl+Shift+H): variable spans render with
  a faint blue tint and a dotted underline so you can see which text is a
  variable, both on the canvas and while editing. View-only — off for export.
- The toolbar button is now a clearer bold "{ }" with the shortcut in its tooltip.

### Changed
- The make/remove-variable logic moved to a single canvas method shared by the
  toolbar button, the right-click menu and the shortcut, so all three behave
  identically.

### Validation
- New test (Show-Variables draws a marker on a variable run and nothing on a
  plain run); full suite 480 passed / 3 skipped. FORMAT_PATCH still 20 (no
  schema change — this is UI only).
## [4.3.6.0] - 2026-06-15

Added variable text: any span of text can become a batch variable. Verified
halftone pattern batching already works (no change made).

### Added
- **Variable text (inline batch variables).** A selected span of text in any
  TextBox (including document header/footer, which are TextBoxes) can be turned
  into a batch variable. The span becomes a run carrying a stable id (`rid`) and
  a human `var_name`; a batch column targets `run.text` on that rid, so each row
  sets that span's text. The run's STYLE fields are batchable too (`run.font_size`,
  `run.color`, `run.bold`, `run.italic`) -- properties were already per-run, this
  exposes them as variables. The renderer is unchanged: the value is baked into
  the run before rendering, like every other batched attribute.
  - The binding is by stable rid, never by position, so editing the surrounding
    text (which splits and merges runs) keeps the variable pointed at the same
    span. A variable run is never merged into an identically-formatted neighbour.
  - In the text editor toolbar, a "{x}" button turns the selection into a
    variable (prompting for a name, default `inlinetextNN`) and adds the batch
    column automatically; pressing it on an existing variable offers to remove it.
    Creating a variable from a text selection also works as a normal batch column,
    so it shows up in the 3D Batch table like any other.

### Verified (no change)
- Halftone pattern batching in the batch editor already works end to end: the
  pattern FILE PATH is offered in the Add-column dialog (v4.3.5.53) and the batch
  table cell uses a file picker for file_path attributes, so a custom pattern can
  be batched by browsing to a file. Nothing was changed here.

### Validation
- New tests: run rid/var_name serialization round-trip; a batch column replaces
  just the bound run and keeps TextBox.text in sync; the binding resolves by rid
  after surrounding text changes; run style fields are batchable; a variable run
  survives run normalization (not merged) while same-rid runs merge. Full suite
  479 passed / 3 skipped.

### Format
- FORMAT_PATCH 19 -> 20: TextRun gains optional `rid`/`var_name` (written only
  when set) and BatchColumn gains `run_id`. Purely additive and backward
  compatible -- older builds load newer files (the unknown fields are ignored,
  with the standard newer-version notice); files without variable text serialize
  exactly as before.
## [4.3.5.68] - 2026-06-15

Fixed a sheared child getting clipped (a cut-off corner) inside a rotated group,
from five uploaded repro files.

### Fixed
- **A rotated group clipped a child that carried shear.** The rotated-group
  renderer sizes its buffer to the bounding box of the children, but that box was
  computed from each child's rotated corners while IGNORING shear -- the same gap
  fixed in compute_bounds in 4.3.5.66, except _render_group has its own copy. So a
  child sheared by a previous resize overflowed the too-small buffer and lost a
  corner (the rect rendered with a flat cut edge instead of a parallelogram tip).
  Each corner is now sheared about the child center before its rotation when
  sizing the buffer, matching the renderer and compute_bounds, so the sheared
  child fits and renders whole.

### Validation
- New test (a rotated group with a strongly sheared child renders the child's
  full parallelogram area, no clipping); full suite 475 passed / 3 skipped.
  FORMAT_PATCH still 19. Verified against the uploaded u4 file: the rect now
  renders as a complete parallelogram with a sharp corner instead of a cut edge.
## [4.3.5.67] - 2026-06-15

Fixed a rotated child collapsing when a group's side was dragged back and forth,
from three uploaded repro files.

### Fixed
- **Dragging a group's side and back wrecked a rotated child.** The first
  non-uniform resize shears a rotated child (Photoshop skew); the second resize
  then ran _shear_decompose from the child's ROTATION ONLY and ignored the shear
  it already had, so it didn't compose. A back-and-forth drag collapsed the child
  (shear jumping to ~-1.06) instead of returning it to the start. The child's own
  map is now taken as R(theta) . Shear(shear_x), so a second resize composes
  M = diag(sx,sy) . R(theta) . Shear(shear_x) correctly. Resizing a side out and
  back now restores the child's rotation, size and shear exactly (a true inverse).
  The shear path also now triggers for a child that has shear but no rotation,
  which the rotation-only test skipped.

### Validation
- New test (resize a group's side then back restores a rotated child's rotation,
  size and shear); the decomposition reproduces M = diag(sx,sy).R(theta).Shear
  exactly (err 0), and is unchanged for shear=0 (backward compatible). Full suite
  474 passed / 3 skipped. FORMAT_PATCH still 19. Verified against the three
  uploaded files: the back-and-forth drag now returns the rect to its original
  rotation and zero shear.
## [4.3.5.66] - 2026-06-15

Fixed the group bounding box not fitting (and appearing to jump on) sheared
children, using two uploaded repro files.

### Fixed
- **A group box didn't fit its children once they were sheared, and the box
  jumped after a drag.** compute_bounds built the box from each child's rotated
  corners but ignored the child's shear. A non-uniform resize of a group with
  ROTATED children shears them (rotated rects become parallelograms), so the real
  extent differed from the computed box: the selection box overshot/undershot the
  shapes, and because the drag set a fitting box while the old compute_bounds
  recomputed a non-fitting one on release, the box "jumped". Each corner is now
  sheared about the child center before rotation, matching the renderer, so the
  box fits the sheared children and the drag/release boxes agree (no jump). An
  ellipse with no rotation has no shear, which is why it looked fine.
- **Old files showed a wrong group box until edited.** Group boxes are now
  recomputed on load, so files saved before the shear-aware compute_bounds get a
  fitting box immediately (idempotent for already-correct files).

### Validation
- New test (a group box fits a sheared rotated child and contains its sheared
  corners); full suite 473 passed / 3 skipped. FORMAT_PATCH still 19. Verified
  against both uploaded repro files: the box now fits the content within ~0.5 mm
  (was off by ~7.6 mm).
## [4.3.5.65] - 2026-06-15

Reworked the rotated-group renderer to drop the square intermediate buffer that
4.3.5.64 introduced, which showed as square padding / clipping while dragging a
group's side handles.

### Fixed
- **Resizing a rotated group's side clipped/padded the content to a square.**
  4.3.5.64 fixed the child "dancing" by rotating the group about its BOX center,
  but did so by embedding the children buffer in a 2*rad x 2*rad SQUARE and
  rotating that about its center. The square wasted memory on long groups and
  surfaced as square padding / edge clipping during a side-handle drag (most
  visible on rect and image children, which paint to the box edge; ellipse, path
  and text paint inside, so they hid it). The renderer now rotates the children
  buffer TIGHTLY (expand=True) about the box center and computes where the pivot
  lands, so there's no square intermediate, no padding, and no clipping. For an
  un-edited group this is pixel-identical to the pre-4.3.5.64 output; the child
  "dancing" fix (rotation about the box center) is preserved.

### Validation
- New test (a rotated group's child renders at full area, no clipping); the
  rotated-group child-edit test (others stay still) still passes; full suite
  472 passed / 3 skipped. FORMAT_PATCH still 19. Verified: an un-edited rotated
  group renders pixel-identical to the tight expand=True reference.
## [4.3.5.64] - 2026-06-15

Fixed four bugs from RTX batch testing: rotated-group child "dancing", negative
shear collapsing to a triangle, and nested-group children vanishing from the
Objects panel. (The rotated-group cursor report now works as a side effect of the
4.3.5.62 group overlay.)

### Fixed
- **Editing one child of a ROTATED group made the OTHERS dance.** The renderer
  rotated the group about the bbox center of its children, which shifts whenever a
  child is edited, so the other children swung about a moving center. The renderer
  now rotates about the group BOX center (obj.transform), which is stable during
  per-child edits (compute_bounds isn't called per child). The selection overlay
  rotates the box about the same center, so they stay aligned. A Group also gained
  an optional rotation_pivot (serialized only when set, no format bump) as an
  override for future use.
- **Enlarging a rotated object along its axis collapsed it into a TRIANGLE.** Pure
  sign error in the shear renderer: the PIL AFFINE offset for shear_x < 0 was
  +abs(shear_x)*h, but must be shear_x*h (negative). The wrong sign double-shifted
  the skew and crushed a strongly negative shear to a triangle. Now a +s and -s
  shear render mirror parallelograms of equal area. This affected every negative
  shear, including SVG/PDF export.
- **A group nested inside a group hid its own children in the Objects panel.** The
  panel listed only a group's DIRECT children; a child that was itself a group
  showed up, but its children vanished below depth 1. The panel now recurses, each
  nesting level indented one step further.

### Notes
- The rotated-group resize-cursor report could not be reproduced in the current
  build: object and group handle cursors are identical at every rotation. The
  4.3.5.62 rotated group overlay is what fixed it (before that a group had no
  rotated box for cursors to follow).

### Validation
- New tests (a -s shear renders equal area to +s, i.e. a parallelogram not a
  triangle; editing one child of a rotated group leaves the others' visual centers
  fixed; a doubly-nested group lists all its leaves in the panel); full suite
  471 passed / 3 skipped. FORMAT_PATCH still 19.
## [4.3.5.63] - 2026-06-15

Fixed rotated-group resize scattering children; clarified the "apply to all" button.

### Fixed
- **Resizing a rotated group threw its children out of the box.** Children scaled
  in the group's ROTATED world axes (4.3.5.52), but children actually live in the
  group's LOCAL, un-rotated space (the renderer rotates the whole group buffer
  about the box center). So a resize drifted child positions, sheared the
  perpendicular axis, and pushed everything off-center -- exactly the "stretches
  too much, shrinks the other way, slides off center" report. Children now scale
  AXIS-ALIGNED in local space, mapped from the baseline box to the new box by
  (sx, sy), so they stay aligned and fill the rotated box as a rigid unit. The
  group box itself (anchor fixed in world) was already correct; only the child
  placement changed. Pre-rotated children (shear decomposition) and the QR
  exception still apply.
- **The "apply layer effects to all selected" button showed for a single
  selection.** It copies the primary object's effects onto the OTHER selected
  objects, so it only makes sense with 2+ selected. It's now hidden unless a
  multi-selection is active (it was puzzling on a single object or a group), and
  its tooltip explains it.

### Validation
- New tests (a rotated group resized along its local axis keeps children aligned,
  heights unchanged, widths scaled; the apply-to-all button is hidden for a single
  selection and shown for a multi-selection); full suite 468 passed / 3 skipped.
  FORMAT_PATCH untouched.

### Notes
- This supersedes the 4.3.5.52 approach. Verified visually: a rotated group
  resized along its axis stretches its children along that axis, staying inside
  the rotated box.
## [4.3.5.62] - 2026-06-15

Group fixes: child selection box in a rotated group, and a Layer Effects panel
for groups.

### Fixed
- **A selected child of a rotated group had its selection box in the wrong place.**
  The overlay drew the box from the child's own transform only, ignoring the
  group's rotation, so for a rotated group the box sat off to the side, unrotated.
  The overlay now carries the box (and line endpoints) up through every parent
  group's rotation about that group's center, so it lands exactly where the child
  is rendered. Verified the box corners match the rendered child to < 1 mm.
- **Selecting a group showed the empty properties panel.** Groups had no panel in
  the type dispatch, so there was no way to reach Layer Effects (copy/paste/delete
  effect) for a group even though groups render effects on their combined
  silhouette. Groups now get their own panel with the Layer Effects entry point
  and the same effect actions as other object types.

### Not a bug (clarified)
- Resizing a rotated group projects the drag into the group's local (rotated)
  axes -- so dragging a corner "horizontally" on screen changes both width and
  height. This is the standard rotated-resize behavior (the dragged corner follows
  the mouse, the opposite corner stays fixed) and is identical for a single
  rotated object; it does not drift across a multi-step drag. Left as-is.

### Validation
- New tests (a rotated group's child overlay matches the rendered child; selecting
  a group shows the group panel, not the empty one); full suite 466 passed / 3
  skipped. FORMAT_PATCH untouched.
## [4.3.5.61] - 2026-06-15

Consolidation step 3 (final): the old CSV-batch and Variables dialogs are retired.

### Changed
- **The standalone Variables dialog is retired.** It defined document variables,
  which no longer exist as a separate concept; it now shows a short note and opens
  the 3D Batch (where each varied value is a column).
- **The old CSV-batch is retired.** It mapped CSV columns to document variables
  and exported per row. The 3D Batch does all of this natively (add columns,
  Import CSV with autodetected encoding + meta, Generate to files with a filename
  pattern), so the menu entry now redirects there.
- **The toolbar "CSV" button was removed.** CSV batch is reached through the 3D
  Batch panel; the File menu keeps a redirecting entry for discoverability.
- New helper `_open_batch_tab()` brings the 3D Batch panel forward.

### Validation
- New test (both retired dialogs redirect to the 3D Batch, define no document
  variables, and no longer contain their old dialog bodies); full suite 464 passed
  / 3 skipped. FORMAT_PATCH untouched.

### Notes
- This completes the variables -> 3D Batch consolidation (migrate on load ->
  remove the properties-panel binding UI -> retire the old dialogs). There is now
  a single batch system. The legacy variable data model still loads (for old
  files) but has no UI surface; it's migrated to batch columns on open.
## [4.3.5.60] - 2026-06-15

Consolidation step 2: the variable-binding UI is removed from the properties panel.

### Changed
- **The "Variable" field and Bind button are gone from the properties panel.**
  Variable bindings are consolidated into the 3D Batch (an object bound to a
  variable is now a batch column targeting its text), so a separate binding field
  in object properties no longer makes sense. The "[variable]" tag in the object
  header card was removed too.
- `_bind_var` is now a no-op, and the underlying le_var line edit is kept but
  hidden, so existing panel code that references it keeps working without showing
  a binding control.

### Validation
- New test (the properties panel no longer shows a variable field; _bind_var
  doesn't bind; loading an object that still has a legacy variable doesn't crash);
  full suite 463 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Last consolidation step remaining: retire/redirect the old CSV-batch dialog and
  the standalone Variables dialog (both predate the 3D Batch).
## [4.3.5.59] - 2026-06-15

Consolidation step 1: legacy variables migrate into the 3D Batch.

### Changed
- **The old document-variable system is being folded into the 3D Batch.** An
  object bound to a document variable (obj.variable) was really just batching that
  object's text, so on load each such binding is converted into a 3D Batch column
  (target = that object, attr = text, header = the variable name) and obj.variable
  is cleared. The variables' current values become a single "migrated" row, so
  nothing changes visually. This runs automatically in Document.from_dict, so old
  files migrate transparently on open; new files have nothing to migrate.

### Migration details
- Idempotent: an object already migrated (no obj.variable) is skipped, and a
  column for the same target+attribute isn't duplicated.
- Safe for batch-less files: if nothing is bound, migration returns early WITHOUT
  creating a BatchConfig (a pre-3D-batch file still loads with _batch is None).
- Backwards compatibility is preserved (old files load and migrate), though it
  isn't critical since the variable system wasn't widely used.

### Validation
- New tests (a binding migrates to a column + row; migration is idempotent;
  save+load migrates transparently; a file with no bindings doesn't get a batch
  created); full suite 462 passed / 3 skipped. Old CSV batch and FORMAT_PATCH
  untouched.

### Notes
- Next consolidation steps: remove the variable binding UI from the properties
  panel (it no longer makes sense next to the 3D Batch), and retire/redirect the
  old CSV-batch dialog and the Variables dialog.
## [4.3.5.58] - 2026-06-15

3D Batch: Generate to files, with a filename-pattern builder.

### Added
- **Generate… button in the 3D Batch toolbar.** Renders every row to a file
  (PNG/JPG/PDF/SVG), applying each row to a copy of the document first. Names come
  from a pattern you build; identical names are de-duplicated automatically.
- **Filename-pattern dialog** that does exactly what was asked:
  - Type any pattern; each column can go into the name.
  - **Live preview** of the resulting filename.
  - **Step through rows** at the preview (‹ / ›) to see how the name changes per
    row before generating.
  - **Click-to-insert** buttons: + Row number, + Row name, and a column picker
    (pick a column from the list, click + Add column, it inserts [{Column}]).
  - **Built-in help** explaining the tokens ([ROW_NUMBER], [ROW_NUMBER:04],
    [ROW_NAME], [{Column}], [{Column:upper}]) and that anything else is plain text
    and the extension is added automatically.
  - Output folder picker and format selector (the extension follows the format).

### Validation
- New tests (the Generate button exists; the dialog preview updates and steps
  through rows with wrap-around; the column picker inserts [{Column}] and the
  preview reflects it; changing the format changes the extension); full suite 458
  passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- This completes the batch export/import phase (CSV in/out + filename templates +
  generate to files). Remaining roadmap before 4.4.0: consolidate the old CSV
  batch into 3D Batch; document-mode header/footer batching.
## [4.3.5.57] - 2026-06-15

Export filename token templates for batch output (model layer).

### Added
- **render_filename()** builds a batch output filename from a token template:
  - `[ROW_NUMBER]` / `[ROW_NUMBER:04]` -- the 1-based row number, optionally
    zero-padded to a width.
  - `[ROW_NAME]` -- the row's name (blank falls back to "row").
  - `[{Header}]` -- the value of the column with that header.
  - `[{Header:upper}]` / `[{Header:lower}]` -- that value, case-folded.
  Unknown tokens keep their text (brackets dropped). The result is sanitized for
  the filesystem (no / \\ : * ? " < > |) and an extension is appended when the
  template didn't include one. Empty template -> a padded row number.

### Validation
- New tests (basic tokens; padding + extension; case modifiers; path-char
  sanitize; blank name and unknown token; default on empty template); full suite
  454 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Model layer. Next: a filename-pattern field in the batch export dialog using
  these tokens.
- Roadmap updated with the post-4.4.0 web plan: a JS render core running in the
  browser (the chosen path for a standalone WordPress plugin), built as a separate
  library testable against the Python renders, with a per-layer vector/raster
  output boundary. Second, independent dev track.
## [4.3.5.56] - 2026-06-15

3D Batch CSV export/import wired into the panel (clean csv + meta side file).

### Added
- **Export CSV / Import CSV buttons in the 3D Batch toolbar.**
  - Export writes the clean CSV (rows) plus a meta side file next to it
    (foo.csv -> foo.meta.csv), both UTF-8 with BOM so Excel on Windows shows
    Czech text correctly. Honours the "include demo rows" toggle.
  - Import replaces the rows from a chosen CSV, auto-loading the meta side file
    if it sits next to it (lossless re-bind); without meta, columns match by
    header. Encoding is autodetected. The status line reports how many rows came
    in and whether meta was used.
- Import fills rows only (it doesn't create columns); a guard tells the user to
  add columns first if the batch has none.

### Validation
- New tests (the panel exposes the two buttons and the meta path helper; a clean
  + meta file pair round-trips the rows through the panel); full suite 448 passed
  / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Next in this phase: export filename token templates
  ([ROW_NUMBER]_[ROW_NAME]-[{COLUMN}]) for the batch output files.
## [4.3.5.55] - 2026-06-15

3D Batch CSV export/import (model layer): a clean CSV plus a meta CSV.

### Added
- **BatchConfig.to_csv()** writes the CLEAN csv: first column the row name, then
  one column per batched attribute (its header), then the values. No meta line,
  nothing extra -- opens cleanly in Excel/Sheets and is what a person edits.
- **BatchConfig.to_meta_csv()** writes the META side csv (header, column_id,
  attr_path, kind) so an import can re-bind each clean column to the exact batch
  column even after headers are renamed or duplicated.
- **BatchConfig.update_rows_from_csv(clean, meta=None)** replaces the production
  rows from the clean csv. With the meta csv the mapping is lossless; without it,
  columns match by header. Encoding is autodetected (UTF-8 BOM, UTF-8, cp1250 for
  Czech Windows exports, latin-1 fallback). Unknown headers are ignored, missing
  ones left blank; it does not create columns (the batch's columns are the schema).

### Validation
- New tests (clean csv has no meta line; meta csv maps headers to column_ids;
  round-trip with meta; import-by-header without meta; cp1250 autodetect; BOM
  strip; unknown columns ignored); full suite 446 passed / 3 skipped. Old CSV
  batch and FORMAT_PATCH untouched.

### Notes
- This is the model layer. Next: wire Export CSV / Import CSV buttons into the 3D
  Batch panel (clean + meta file pair), then the export filename token templates
  ([ROW_NUMBER]_[ROW_NAME]-[{COLUMN}]).
## [4.3.5.54] - 2026-06-15

SVG/PDF export now applies rotation and shear (closing the 4.3.5.51 limitation).

### Fixed
- **SVG export ignored rotation entirely.** A rotated shape/text/image/QR was
  exported axis-aligned. Export now wraps each object in a `<g transform=...>`
  that rotates (and shears) about the object's center, so rotated objects export
  in the right orientation. Rotation parity with the on-canvas render verified.
- **SVG/PDF export now emits shear.** A sheared object exports as a parallelogram:
  SVG via a `matrix(1,0,shear_x,1,0,0)` transform, PDF via a new `shear_at` on the
  page writer (concatenated after the rotation, matching the renderer's
  local -> shear -> rotate order). A rotated group wraps its children in the
  group rotation on export too.

### Validation
- New tests (SVG emits a rotation transform; SVG emits the shear matrix; a plain
  object has no transform wrapper; the PDF page writer exposes shear_at); full
  suite 439 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- The shear pivot differs from the renderer by a small offset (the renderer
  re-centers the sheared buffer); the export is visually a correct parallelogram
  and rotation matches exactly. PDF native-primitive vs full-page-raster choice
  is unchanged; both now carry rotation + shear.
## [4.3.5.53] - 2026-06-15

Halftone pattern file path is now in the batch tree, so a custom pattern can be
batched by path.

### Fixed
- **The halftone pattern's file path was missing from the batch attribute tree.**
  The batchable `ht_pattern_path` descriptor existed and worked, but the
  add-column tree only listed the static halftone fields (dot, angle, shape, ...),
  not the pattern path -- so there was no way to add it as a column from the UI.
  The tree now shows "Pattern file" under a halftone effect (one slot in
  shape/single mode, per-channel slots otherwise), wired to the real descriptor.

### How it works
- The pattern's file path is the source of truth: setting it (per batch row)
  loads that image into the effect's pattern cache at apply time, so each row can
  use a different custom pattern. The batch cell uses a file picker (file_path
  kind), like other path attributes.

### Validation
- New tests (the pattern file path appears in the add-column tree and is wired to
  effects.halftone.ht_pattern_path; setting the path per value loads a different
  pattern); full suite 435 passed / 3 skipped. Old CSV batch and FORMAT_PATCH
  untouched.
## [4.3.5.52] - 2026-06-15

Fixed a rotated group scattering its children when resized.

### Fixed
- **Resizing a rotated group scattered its children.** Child positions were
  scaled in world (axis-aligned) axes while the group's size was measured in its
  rotated axes, so once a group had any rotation, resizing flung the children
  apart and broke their spacing (the "weird crop"). Positions now scale in the
  group's local rotated frame (project to local about the anchor, scale by the
  local factors, project back), so a rotated group resizes as a rigid unit:
  spacing scales proportionally and the layout stays compact. Pre-rotated-child
  shear (4.3.5.51) and the QR exception still apply on top of this.

### Validation
- New test (a rotated group resized uniformly keeps even, proportional child
  spacing); full suite 433 passed / 3 skipped. Old CSV batch and FORMAT_PATCH
  untouched.

### Notes
- This only fixes future edits. A file already saved with scattered children
  (from the old bug) stays as saved -- the scatter was destructive.
- Still pending: SVG/PDF export of shear; custom pattern picker in batch.
## [4.3.5.51] - 2026-06-14

Pre-rotated objects now deform in the group/selection axes when the group is
resized non-uniformly -- Photoshop-style shear. QR codes are kept square.

### Added
- **Shear (skew) in the transform model.** `Transform` gains `shear_x` (default
  0, only serialized when non-zero): a local point (x, y) maps to
  (x + shear_x*y, y) before rotation. The renderer applies it uniformly for every
  object type (render upright, then shear + rotate the buffer), so a skewed object
  draws as a parallelogram.
- **Pre-rotated children shear with the group/selection.** When a group or a
  multi-selection is resized non-uniformly, a rotated child now deforms in the
  group's axes instead of its own. The new rotation / width / height / shear are
  derived by RQ-decomposing diag(sx,sy)*R(theta), so the result matches the
  group's scale applied to the rotated box exactly (verified on the corners).
- The selection box follows the skew (handles sit on the parallelogram).

### Excepted
- **QR codes never shear.** A pre-rotated QR in a resized group scales uniformly
  (by the larger factor) and keeps its rotation, so it stays square and scannable.

### Validation
- New tests (shear serialization; the RQ decomposition matches the matrix on all
  four corners; a sheared rect renders wider; a group resize shears a rotated rect
  but keeps a rotated QR square); full suite 432 passed / 3 skipped. Old CSV batch
  and FORMAT_PATCH untouched.

### Known limitation
- SVG / PDF export does not yet emit the shear (the on-canvas render and editing
  are correct); export of skewed objects will be added next.
## [4.3.5.50] - 2026-06-14

Effects can now be applied to a group as a whole, finishing the group work.

### Added
- **Layer effects on a group apply to the whole group.** A drop shadow / glow /
  stroke on a group treats the combined silhouette of its children as one shape
  (Photoshop-style), riding the buffer render added in 4.3.5.49. Works with a
  rotated group and with nested groups.
- **A child's own effects still render inside a group.** Group children now draw
  through the effect-aware path, so a shadow on a single child shows even when
  the child sits inside a group.

### Validation
- New tests (effect on the whole group; a child's own effect inside a group;
  effects through nested groups); full suite 427 passed / 3 skipped. Old CSV
  batch and FORMAT_PATCH untouched.

### Notes
- Next: optional Photoshop-style shear for a pre-rotated child when a group /
  selection is resized non-uniformly (QR codes excepted -- they must stay
  square). This needs a shear/affine term in the transform model.
## [4.3.5.49] - 2026-06-14

A group now rotates as a single unit: its box is bound to the group and shows
rotated, and resizing a rotated group works in its own (rotated) space.

### Changed
- **A group rotates as one unit via its own transform rotation.** Before, the
  group rotated its children and kept its own box axis-aligned -- so after a 90-deg
  rotation, resizing deformed along the wrong (screen) axis. Now the group carries
  the rotation on its own transform and the renderer rotates the whole group
  (children render into a buffer that is rotated and pasted). The children stay in
  the group's local, un-rotated space.
- The selection box is now bound to the group like any other object: rotate the
  group and the box shows rotated, and resize happens in the group's local axes
  (so dragging a handle stretches the direction you expect).
- `compute_bounds` keeps the group's rotation (it only recomputes x/y/w/h from
  the local children) instead of resetting it.

### Notes
- The buffer render path added here is also the basis for the remaining piece:
  effects applied to a group as a whole.

### Validation
- Updated the group-rotate tests to the new model (rotation lives on the group,
  children stay unrotated) and added new ones (a rotated group renders as a unit
  with width/height swapped; rotation survives compute_bounds); full suite 424
  passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.
## [4.3.5.48] - 2026-06-14

Lines rebuilt on the same model as curves: their points are now LOCAL (relative
to the transform), so a line behaves like every other object across the whole
app -- box, move, resize, rotate, group, batch, save/load, export.

### Changed (systemic fix)
- **A line's points are now LOCAL (relative to transform.x/y), like a path's
  path_data.** Previously they were absolute, which made the line a hybrid that
  fought the transform and broke repeatedly. Now the transform IS the line's
  bounding box and the renderer adds the transform origin, so the same
  transform-based logic that works for every other object works for lines too.
- A new `normalize_line()` keeps the invariant (transform = points' bbox, points
  re-based to 0) after the endpoints change.

### Fixed (all flow from the model change)
- **Move** a line: only the transform changes (no more absolute-point juggling).
- **Resize** a line: scales the local points about the origin, like a curve.
- **Endpoint edit (P1/P2):** edits in world coords, then re-normalizes the box.
- **Group:** a line resizes/moves correctly as part of a group.
- **Batch:** x/y move only the transform; width/height scale the local points.
- **Properties panel:** endpoint fields show world coords and write back through
  the local model.
- **SVG / PDF / legacy export:** add the transform origin to local points.

### Migration
- Files saved before this stored absolute points (no "_local_points" flag). On
  load they're converted to local once (subtract the transform origin) so they
  render in the same place; saving adds the flag so it never double-migrates.

### Validation
- Updated the old line tests to the local-point model and added new ones
  (absolute->local migration, the flag prevents re-migration, normalize_line
  re-bases the box, the renderer adds the transform so a line moves with it);
  full suite 422 passed / 3 skipped. Verified end-to-end: real save/load keeps
  points local, and SVG export emits correct world coords. Old CSV batch and
  FORMAT_PATCH untouched.
## [4.3.5.47] - 2026-06-14

Lines now have a proper transform box and resize/rotate like other objects,
including inside a group.

### Fixed
- **A line had no bounding box and couldn't be transformed.** The selection
  overlay only drew the P1/P2 endpoints, so a line had no resize/rotate handles.
  A selected line now shows a full transform box (8 resize handles + rotate)
  alongside its P1/P2 endpoints. Clicking an endpoint still edits that endpoint
  (it takes priority over the box corners).
- **Resizing a line did nothing.** A line's points are absolute, so the resize
  left them unchanged while the box grew. Resizing now scales the endpoints about
  the anchor, so the line actually resizes.
- **A line transformed badly inside a group.** Group resize now scales a child
  line's endpoints (its baseline points are captured), so a line scales correctly
  as part of a group.

### Validation
- New tests (a line overlay has both the box handles and endpoints; an endpoint
  click wins over the box corner; resizing scales the endpoints about the anchor;
  a line inside a group scales with it); full suite 418 passed / 3 skipped. Old
  CSV batch and FORMAT_PATCH untouched.

### Notes
- Line rotation already worked in the renderer (it routes through a rotated
  buffer); now it's reachable via the box's rotate handle.
- Still to do: effects on a group as a whole, document-mode header/footer
  batching, halftone picker, and exports.
## [4.3.5.46] - 2026-06-14

Group phase 2a: a group resizes and rotates as a single unit.

### Added
- **Resize a group as a unit.** Dragging a selected group's resize handle scales
  every child about the opposite anchor (position and size together), like
  Photoshop. Child geometry follows -- absolute line points and local path data
  scale, and text glyph scale stretches with the group.
- **Rotate a group as a unit.** Dragging the rotate handle rotates every child
  about the group center and adds the same spin to each child's own rotation. The
  group's own box stays axis-aligned (the rotation lives on the children), and is
  recomputed from the children on release.

### Validation
- New tests (group resize scales children about the anchor; group rotate turns
  children about the center and moves their centers; compute_bounds resets the
  group's own rotation); full suite 414 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.

### Notes
- Phase 2b next: effects applied to the group as a whole (render the children
  together into a buffer, then apply the effect). Plus document-mode header/footer
  batching, halftone picker, and exports.
## [4.3.5.45] - 2026-06-14

UI polish: the whole multi-selection is highlighted in the Objects panel, and
menu items no longer clip their labels.

### Fixed
- **A multi-selection only highlighted one row in the Objects panel.** The list
  set just the primary as the current row, so a multi-selection looked like a
  single highlight. Every selected object's row is now highlighted, with the
  primary as the current item.
- **Some menu items were too narrow to read fully.** Menu items now have
  horizontal padding and a minimum width, plus styled separators, so labels and
  their shortcuts aren't clipped together.

### Validation
- New tests (select-many highlights all selected rows and not others; the menu
  style carries item padding + min width); full suite 411 passed / 3 skipped. Old
  CSV batch and FORMAT_PATCH untouched.

### Notes
- This clears the UI items from that report. Remaining: group phase 2 (resize/
  rotate a group, effects on the group as a whole), document-mode header/footer
  batching, halftone picker, and exports.
## [4.3.5.44] - 2026-06-14

Group naming dialog, and a batch variable on a group now targets only the group.

### Added
- **Name a group when creating it.** Grouping a selection now asks for a name;
  leaving it blank uses an auto "GroupNNN" (the next free number on the page,
  filling gaps). The name shows in the Objects panel.

### Fixed
- **A batch variable on a group wrongly expanded to all its children.** Selecting
  the group still counted leftover child ids from the multi-selection, so adding a
  variable linked every child. A single selection now clears any prior
  multi-selection, so a variable on a group targets just the group (which is
  clearly the whole group anyway) -- no confusing per-child expansion.

### Validation
- New tests (selecting one object clears a prior multi-selection; the auto group
  name fills gaps and starts at Group001); full suite 409 passed / 3 skipped. Old
  CSV batch and FORMAT_PATCH untouched.

### Notes
- Next (UI polish from the same report): some menu items are too narrow to read
  fully, and a multi-selection in the Objects panel only highlights one row.
- Then group phase 2 (resize/rotate a group, effects on the group), document-mode
  header/footer batching, halftone picker, and exports.
## [4.3.5.43] - 2026-06-14

Yes -- batch now works with groups: a batch column can target a group or any
object inside it.

### Added
- **Batch targets objects inside a group.** The object reference walks into
  groups, so a batch column can drive a child that lives inside a group (and the
  group itself, for its own transform). The batch panel's target lists now
  include group children, and a child inside a group can be selected on the canvas
  (so you can add a variable from it).

### Fixed
- **Selecting a group's child resolved to nothing.** Object lookup now searches
  inside groups, so a child can be selected / targeted / batched instead of
  silently failing.

### Validation
- New tests (a reference into a group is multi-level and resolves back; a batch
  row reaches a child inside a group; target lists include group children; object
  lookup resolves a group child); full suite 407 passed / 3 skipped. The batch
  resolve/build already walked the tree; this wires the UI and selection to it.
  Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Group phase 2 still to come: resize/rotate a group as a unit, and effects on the
  group as a whole. Plus document-mode header/footer batching, halftone picker,
  and exports.
## [4.3.5.42] - 2026-06-14

Grouping: a multi-selection can be grouped into a single unit, shown with its
children in the Objects panel, moved as a whole, and ungrouped.

### Added
- **Group / ungroup a selection.** Edit menu (Ctrl+Shift+G to group, Ctrl+Shift+U
  to ungroup) turns a multi-selection into a Group and back. Grouping keeps the
  page stacking order; ungrouping dissolves the group's children back to the top
  level and selects them.
- **Groups show their children in the Objects panel**, indented under the group
  with a connector glyph, so the grouping is visible (like Photoshop).
- **Moving a group moves its contents.** A group's children are absolute, so
  dragging the group (or nudging it) translates every child by the same delta.
- **Group bounding box.** A group computes its box from its children (accounting
  for child rotation), so it selects and reads correctly.

### Validation
- New tests (group/ungroup round-trips and needs 2+ objects, the group box spans
  the children, moving the group translates children, the panel lists children
  under the group); full suite 403 passed / 3 skipped. The Group data model and
  rendering already existed; this adds the UI and group transform. Old CSV batch
  and FORMAT_PATCH untouched.

### Notes
- Phase 2 (next): resize/rotate a group as a unit, and effects applied to the
  group as a whole (rendered together, then the effect). Plus document-mode
  header/footer batching, halftone picker, and exports.
## [4.3.5.41] - 2026-06-14

Non-uniform resize of a multi-selection now squashes/stretches text too, not
just its box.

### Fixed
- **Text didn't squash on a non-uniform multi-selection resize.** Scaling the
  selection changed a text box's dimensions but left the letters unchanged. The
  multi-transform now multiplies the text's glyph scale (glyph_scale_x/y) by the
  per-axis factors, so the renderer stretches/squashes the letters non-uniformly
  -- true letter deformation, matching the single-object Shift-resize behavior.
  Lines and paths already followed; this brings text in line.

### Validation
- New tests (a width-only multi-resize doubles a text box's glyph_scale_x and
  leaves glyph_scale_y at 1; glyph_scale_x actually widens the rendered text);
  full suite 399 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Last item from that report: grouping a selection (a group object shown and
  ungroupable in the Objects panel, with effects on the group). Plus document-mode
  header/footer batching, halftone picker, and exports.
## [4.3.5.40] - 2026-06-14

Multi-selection polish: only the union box shows now (no leftover handle box on
the first/last object), and rotating the selection repaints more smoothly.

### Fixed
- **A stray transform box lingered on the primary object during a
  multi-selection.** The union box and the primary object's single overlay were
  both drawn. With 2+ objects selected the single overlay is now hidden, so only
  the union box (the selection UI) shows.
- **Rotating a multi-selection looked jumpy.** Each mouse-move kicked off a
  separate async render, so objects appeared to rotate slightly out of sync. The
  drag now uses the interactive live-preview render path, so the whole selection
  repaints together and responsively.

### Validation
- New test (a multi-selection hides the single overlay while keeping the union
  box); full suite 397 passed / 3 skipped. Old CSV batch and FORMAT_PATCH
  untouched.

### Notes
- Still to do from the same report: non-uniform scaling should squash text
  non-uniformly, and grouping a selection (a group object shown/ungroupable in the
  Objects panel, with effects on the group). Plus document-mode header/footer
  batching, halftone picker, and exports.
## [4.3.5.39] - 2026-06-14

Hotfix: making a multi-selection by rubber-band raised a repeating error.

### Fixed
- **Multi-selection raised AttributeError ('EdofCanvas' has no '_view_zoom').**
  The 4.3.5.37 union-box handle code called self._view_zoom(), which only exists
  on the SelectionOverlay, not on EdofCanvas. Hovering or hit-testing the
  multi-selection box (in _update_cursor / mouseMove) raised repeatedly. It now
  uses the canvas's own zoom (the _zoom attribute). Affected 4.3.5.37 and
  4.3.5.38.

### Validation
- New regression test (hit-testing and cursor updates over the multi-selection
  box don't raise); full suite 396 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.
## [4.3.5.38] - 2026-06-14

Normal mode: editing a property in the panel now applies to the whole
multi-selection, and one button applies a layer effect to all selected objects.

### Added
- **Properties panel edits the whole multi-selection.** With several objects
  selected, changing width / height / rotation in the panel applies the same
  value to each; changing X / Y moves the whole selection by the same delta;
  changing opacity applies to all. Lines/paths follow via the same geometry rules
  as batch. A single selection behaves exactly as before.
- **Apply layer effects to all selected.** A new button in the Layer Effects
  action row copies the primary object's layer style (effects + blending + the
  master flag) onto every other selected object in one click, so a multi-selection
  gets the same effects at once.

### Fixed
- **Copy/paste layer effects now carries the master flag.** Pasting a layer style
  (here and via the existing copy/paste buttons) also copies the "All effects"
  master, so pasted effects actually render instead of sitting under an off
  master.

### Validation
- New tests (panel width/opacity apply to all, X/Y apply as a delta, effects-to-
  selection copies effects + master + opacity, single selection stays isolated);
  full suite 395 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- This completes the multi-selection request: transform the selection (4.3.5.37),
  effects to all, and edit shared properties from the panel.
- Still to do from before: document-mode header/footer batching, halftone
  pattern-file picker UI, and exports/import.
## [4.3.5.37] - 2026-06-14

Normal mode: the multi-selection box can now transform the whole selection --
resize (uniform and non-uniform) and rotate together, like Photoshop.

### Added
- **Transform the whole multi-selection.** The selection box now has resize
  handles (8) and a rotate handle. Dragging a corner/edge scales every selected
  object about the opposite anchor (Shift on a corner = uniform); dragging the
  rotate handle rotates them all about the selection center (Shift = 15-degree
  snaps). Each object's position and size scale together, and lines/paths follow
  their boxes (absolute line points translate + scale; local path data scale).
  Cursors reflect the handle under the pointer.

### Validation
- New tests (union bbox + handle set, corner resize scales every object about the
  anchor, rotate turns them about the center and moves their centers); full suite
  391 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still to come from the same request: a layer effect applied to all selected
  objects at once, and editing shared properties from the properties panel. Plus
  document-mode header/footer batching, halftone picker, and exports.
## [4.3.5.36] - 2026-06-14

Fixed curve vanishing on height change and line not moving, and added absolute
vs incremental X/Y to batch.

### Fixed
- **Changing a curve's height made it vanish.** 4.3.5.34 scaled path data about
  (transform.x, transform.y), but path data are LOCAL (the renderer adds the
  transform), so that pushed the curve far off-canvas. It now scales about the
  local origin (0,0), like the interactive resize -- the curve squashes/stretches
  in place.
- **Moving a line did nothing.** Line points are absolute (the renderer does NOT
  add the transform), so changing x/y left the line where it was -- both in batch
  and when dragging it in the editor. Setting x/y (and dragging) now translates
  the line's points by the same delta, so the line actually moves. Multi-drag
  moves lines too.
- **Scaling a line's width/height now moves its endpoints** about the box origin,
  so a batched size change reshapes the line instead of being ignored.

### Added
- **Absolute and incremental X/Y in batch.** transform.x / transform.y set the
  position absolutely (as before); new transform.x_offset / transform.y_offset
  ADD to the current position (negative values move the other way). So one
  variable can place objects exactly, another can nudge them relative to where
  they are.

### Validation
- New tests (height keeps a curve on-canvas, x/y translate a line's absolute
  points, incremental offsets add/subtract incl. negatives on line and rect, the
  offset descriptors are in the tree); updated the 4.3.5.34 path tests for local
  coords. Full suite 388 passed / 3 skipped. Old CSV batch and FORMAT_PATCH
  untouched.

### Notes
- This clears the rest of that report. Still open from before: document-mode
  header/footer batching, halftone pattern-file picker UI, and exports/import.
## [4.3.5.35] - 2026-06-14

3D Batch: a multi-selection now shows one bounding box around all selected
objects (like Photoshop), and during a batch preview the box uses the projected
geometry instead of the template.

### Changed
- **One bounding box around all multi-selected objects.** Instead of a separate
  frame per object, a multi-selection now draws a single dashed box spanning all
  of them with corner marks, like Photoshop. Rotated objects expand the box to
  their rotated extent.

### Fixed
- **Selection boxes showed the template during a batch preview.** The
  multi-selection box is now computed from the PROJECTED objects (the previewed
  row applied), so it matches what's rendered -- e.g. a batched size change moves
  the box, not the original template geometry.

### Validation
- New tests (the projected-selection helper returns all selected objects; during
  a preview the box reflects the projected width, not the template); full suite
  382 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still to do from the same report: absolute vs incremental X/Y (next). Plus
  document-mode header/footer batching, halftone pattern-file picker UI, exports.
## [4.3.5.34] - 2026-06-14

Objects panel: Ctrl/Shift multi-selection now works and rows are taller. Batch:
resizing a line/curve squashes it instead of cropping, and QR opacity is honored.

### Fixed
- **Ctrl/Shift multi-selection didn't work in the Objects panel.** The custom row
  widget ate the click, so Ctrl-click never reached the list's selection. The row
  now passes clicks through to the list (its toggle buttons stay clickable), so
  Ctrl-click toggles and Shift-click selects a range, mirrored to the canvas.
- **Resizing a curve cropped it; a line ignored height entirely.** Setting a
  shape's width/height (via batch or the panel) now scales its local geometry
  (path data / line endpoints) proportionally about the transform origin, like
  the interactive resize -- so the curve squashes/stretches and the line follows
  its box. Rects and other objects without local geometry are unchanged.
- **QR opacity was ignored.** The QR renderer never applied the object's opacity,
  so a batched opacity did nothing on a QR code; it now scales the QR alpha. The
  QR also centers in a non-square box instead of silently ignoring one side.

### Changed
- **Taller Objects-panel rows (40px).** The selection highlight no longer crowds
  the icon and name.

### Validation
- New tests (dimension setters scale line points and path data about the origin
  while leaving rects alone, QR opacity scales the alpha, rows are >=40px tall and
  pass mouse through while buttons stay clickable); full suite 380 passed / 3
  skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Opacity/width/height now apply correctly across textbox, rect, line, path/curve
  and QR (the data layer already did; this fixes the rendering and geometry).
- Still to do (reported together): a single bounding box around all multi-selected
  objects and projected-geometry outlines during batch preview, and absolute vs
  incremental X/Y. Plus document-mode header/footer batching, halftone picker,
  and exports.
## [4.3.5.33] - 2026-06-14

3D Batch: fixed number/text variables being uneditable in the right panel, and
the table filter now matches an object's name/type (e.g. "rectangle").

### Fixed
- **Number and plain-text variables had no editable field in the right panel.**
  The template panel's value editor lost its fallthrough case in 4.3.5.29 (the
  default QLineEdit was created but never wired up or returned), so variables
  like transform.height, width, x, y, rotation and plain text showed no editor --
  the bug David hit with a height variable. The default editor is restored and
  wired up; all 27 descriptor kinds now produce a usable widget.

### Added
- **Filter by object name/type.** The table filter now also matches the target
  object of a column by its name, object type, and a human word for its shape
  (e.g. typing "rectangle" matches columns targeting a rect shape, even though
  the table never prints the object name). A name/type match is column-level, so
  it shows all rows, like a variable-name match.

### Validation
- New tests (every descriptor yields an editor, a height variable is editable via
  keyboard, filter matches an object by "rectangle"); full suite 373 passed / 3
  skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still to do: document-mode header/footer batching, halftone pattern-file picker
  UI, and exports/import.
## [4.3.5.32] - 2026-06-14

3D Batch: multi-selection now works in the Objects list and on the canvas
(Ctrl/Shift + rubber-band rectangle), and the table has a text filter.

### Added
- **Multi-selection in the Objects list.** The list is now extended-selection:
  Ctrl-click toggles, Shift-click selects a range, and the selection mirrors to
  the canvas so the batch panel sees all selected objects.
- **Rubber-band (rectangle) selection on the canvas.** Drag from empty space to
  draw a selection box; objects whose bounding box falls inside are selected.
  Ctrl/Shift adds to the current selection instead of replacing it. Ctrl-click
  and Shift-click on objects continue to work as before.
- **Multi-selected objects are outlined on the canvas** (blue frames) so a
  multi-selection is visible, alongside the primary object's transform overlay.
- **Table text filter.** A filter box above the batch table hides rows that
  don't match: type a value (e.g. "Hello", "99") to show only rows containing it,
  or a variable name to match its whole column. Case-insensitive; clearing shows
  all. The page filter (all / active-page rows) is unchanged.

### Validation
- New tests (object list is extended-selection with the multi signal, canvas
  set_multi_selection, rectangle bbox intersection, table filter by value and by
  column name); full suite 370 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.

### Notes
- "edof tabs" (a nicer custom table component to replace the Qt table in the
  batch UI) is already tracked in the roadmap's TBD section.
- Still to do: document-mode header/footer batching, halftone pattern-file picker
  UI, and exports/import.
## [4.3.5.31] - 2026-06-14

3D Batch: selecting several objects and adding a variable now shows only the
attributes they all share, and each variable drives every selected object.

### Added
- **Multi-selection common-attribute tree.** With several objects selected
  (Ctrl/Shift-click on the canvas or object list), the Add-variable dialog now
  filters the tree to the attributes COMMON to all of them -- so you only batch
  what they share (e.g. geometry and shared style, but not text if one isn't a
  text box). The title shows "(N objects)", empty bands are dropped, and each
  variable you add is linked to every selected object (multi-target). Single
  selection is unchanged (full tree).

### Validation
- New tests (multi-select tree shows only shared attributes with the count in
  the title, empty bands dropped, single selection stays unfiltered); full suite
  366 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- This completes the multi-target flow: link/unlink an existing variable
  (4.3.5.23), apply to all linked objects incl. effects (4.3.5.27), and now
  create from a multi-selection with a shared-attribute tree.
- Still to do: document-mode header/footer batching, halftone pattern-file picker
  UI, and exports/import.
## [4.3.5.30] - 2026-06-14

3D Batch: the effects master is now truly explicit -- Path A no longer enables
it either, so an effect batched onto a second object stays hidden until a master
variable enables it (matching the warning).

### Fixed
- **An effect batched onto an object that had none secretly enabled the master.**
  When a column targeted an effect the object didn't have, Path A created the
  effect and (for the first effect) turned the object's master "All effects" flag
  on -- so the effect showed even with no master variable, contradicting the red
  warning. Path A no longer touches the master. The master is now explicit
  everywhere: an effects.all_enabled variable set true, or the master already on.
  So a shadow linked to a second object without a master variable stays hidden,
  consistent with the warning the panel shows.

### Validation
- New tests (Path A creates the effect but leaves the master off; with an
  all_enabled variable set true the effect renders); full suite 363 passed / 3
  skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- The rule is now uniform: effects render only when the master is explicitly on
  (a master variable, or turned on by hand). The panel's red warning flags any
  object with an effect variable but no master variable.
- Still to do: a multi-selection tree filtered to common attributes,
  document-mode header/footer batching, halftone pattern-file picker UI, exports.
## [4.3.5.29] - 2026-06-14

3D Batch: effects need an explicit master variable (with a red warning when it's
missing), plus a font-family dropdown and a justify-mode dropdown.

### Changed
- **Effects no longer work without an explicit master variable.** Adding an
  effect in the dialog no longer silently turns the object's master "All
  effects" flag on (that was a state change outside the batch's control). Per
  request, effects need an explicit "effects enabled" (all_enabled) variable, or
  the master already on.

### Added
- **Red warning when the master variable is missing.** The template panel shows a
  red banner when an object has an effect variable but no master variable (and
  the master isn't already on): effects won't render until an "All effects"
  variable is added and set true.
- **Font-family dropdown.** The value editor for a style.font_family variable is
  now a real font picker (QFontComboBox) instead of a free-text field.
- **Justify-mode in batch, as a dropdown.** style.justify_mode (space / full --
  how justified text spreads) was missing from batch; it's now available and, as
  an enum, edits via a dropdown. (Alignment justify was already there.)

### Validation
- New tests (add-instance leaves the master alone, the red warning shows without
  a master variable and hides once one is added, justify_mode is in the registry
  with the right choices) plus updated prior test; full suite 361 passed / 3
  skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still to do: a multi-selection tree filtered to common attributes,
  document-mode header/footer batching, halftone pattern-file picker UI, exports.
## [4.3.5.28] - 2026-06-14

3D Batch: the effects master flag is explicit again -- enabling an effect no
longer secretly forces it on, so removing a master variable hides the effect as
expected.

### Fixed
- **Removing a master variable didn't hide the effect.** Enabling an effect used
  to auto-turn-on the object's master "All effects" flag (added in 4.3.5.26 for a
  multi-object symptom that was really the effect-id bug, fixed properly in
  4.3.5.27). That auto-toggle surprised the user: after unlinking the master
  variable from an object, the shadow stayed visible because enabling it forced
  the master back on. The auto-toggle is removed -- the master is controlled
  explicitly only (an effects.all_enabled variable, or the master already on).

### Changed
- **Adding an effect in the dialog turns the master on.** So a freshly added
  effect can still render (the master gates all effects), matching the
  layer-effects dialog. The batch then drives the per-effect enabled, and the
  master stays explicit (no hidden toggling on apply).

### Validation
- New tests (enabling an effect leaves the master alone, adding an effect turns
  the master on, removing the master variable hides the effect) plus updated
  prior master tests; full suite 359 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.

### Notes
- Multi-object effects still work: link a master (all_enabled) variable to the
  objects alongside the per-effect variables, or have the master on. The
  per-effect enabled is applied to every linked object (4.3.5.27).
- Still to do: a multi-selection tree filtered to common attributes,
  document-mode header/footer batching, halftone pattern-file picker UI, exports.
## [4.3.5.27] - 2026-06-14

3D Batch: effects now apply to ALL linked objects (not just the first), text
justify works, and a multi-selection batches the shared attribute on every
selected object.

### Fixed
- **Effects applied only to the first of several linked objects.** A variable on
  an effect stored the primary object's effect id (eid), which is unique per
  object, so on other linked objects the eid didn't match and nothing applied.
  The apply now uses the eid only where it matches (the primary, keeping its
  reorder-safety) and falls back to the positional descriptor on the other
  objects -- so the effect applies to all of them.
- **Text justify did nothing.** Like plain text, run-level alignment wins in the
  layout engine, so setting only style.alignment was invisible. Alignment now
  pushes onto every run and clears the per-paragraph override, so justify (and
  the others) actually show. (justify was already in the choices.)

### Added
- **Multi-selection batches all selected objects.** Select several objects
  (Ctrl-click / Shift-click on the canvas or the object list), then Add variable:
  each new variable is linked to every selected object the attribute applies to
  (multi-target), so one row value drives them all. Incompatible objects are
  skipped per attribute.

### Validation
- New tests (eid-bound column falls back for other targets so all get the effect,
  justify applies to runs, multi-select returns primary-first, multi-select add
  links all and applies to all); full suite 357 passed / 3 skipped. Old CSV batch
  and FORMAT_PATCH untouched.

### Notes
- Per-span rich-text formatting in a batched text cell (bring in formatted text
  via richer tables) is deferred to after 4.4.0, per request.
- Still to do: a multi-selection tree filtered to the common attributes (header
  "Text (N objects)"), document-mode header/footer batching, halftone
  pattern-file picker UI, and exports/import.
## [4.3.5.26] - 2026-06-14

3D Batch: text variables now actually change the text, enabling an effect turns
on the master so it renders, added effects use sensible defaults, and the
Add-variable dialog gets a left-hand effect column with remove.

### Fixed
- **Batch text on a textbox did nothing.** A textbox stores plain `text` plus
  rich-text `runs`, and the renderer draws the runs -- so setting `text` alone
  was invisible. Setting text now rewrites the runs too, preserving the first
  run's formatting (font / size / bold / colour ...), and splits paragraphs into
  runs. So a batched text keeps the look it had; type plain text into the cell
  and the formatting is kept.
- **Enabling an effect on the second object showed nothing.** Turning an effect
  on (enabled=true) now also turns on the object's master "All effects" flag,
  which gates all effects -- otherwise the enabled effect still wouldn't render.
  An explicit effects.all_enabled in the same row still wins (it applies last).
- **Added effects didn't use sensible defaults.** "+ Add effect instance" now
  builds the effect with the same defaults the 'add effect' UI uses (e.g. drop
  shadow direction 315, not the bare dataclass 135), via make_default_effect.

### Added
- **Effect column moved left, with remove.** In the Add-variable dialog the
  effect reorder list is now a left-hand column (dialog widened to fit), and has
  a "Remove selected effect" button to drop an effect added by mistake (its
  eid-bound columns are dropped with it).

### Validation
- New tests (text set updates runs + preserves formatting + splits paragraphs,
  enabling an effect turns on the master, disabling leaves it, all_enabled still
  wins, add-instance uses sensible defaults, remove selected effect) plus updated
  prior tests; full suite 353 passed / 3 skipped. Old CSV batch and FORMAT_PATCH
  untouched.

### Notes
- For a textbox with several differently-formatted spans, a batched text
  collapses them to one run with the first span's look (a reasonable rule for a
  single cell); rich per-span editing stays in the inline editor.
- Still to do: creating a variable from a multi-selection with a common-attribute
  tree, document-mode header/footer batching, halftone pattern-file picker UI,
  and exports/import.
## [4.3.5.25] - 2026-06-14

3D Batch: Add-variable dialog now lists only the object's effects (add more
dynamically), the reorder list covers all effect types and refills live, and
linking objects refreshes the preview immediately.

### Fixed
- **Add-variable tree no longer floods with every effect type.** It used to
  pre-list a slot for all 13 effect types even when the object had none. Now it
  shows only the effects the object actually has; you add others dynamically with
  "+ Add effect instance".
- **"+ Add effect instance" now really adds the effect to the object** (disabled),
  like the layer-effects dialog. So it appears as an instance, can be reordered,
  and a variable on it binds by effect id.
- **Effect reorder list wasn't visible / didn't cover added effects.** The
  drag-to-reorder list now refills live whenever effects change (including ones
  just added), and lists all effect types (not only identical instances), exactly
  like the layer-effects dialog. It shows whenever the object has 2+ effects.
- **Linking a variable to more objects didn't update the canvas right away.** The
  link/unlink dialog (both template and table tabs) now re-projects the current
  row on accept, so newly linked objects reflect the row's value immediately.

### Validation
- New tests (tree starts with no effect slots, add-instance adds a real disabled
  effect, reorder lists all types, linking refreshes the preview) plus updated
  prior tests for the new dynamic behavior; full suite 347 passed / 3 skipped.
  Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still to do: creating a variable from a multi-selection with a tree filtered to
  the selection's common attributes, document-mode header/footer batching,
  halftone pattern-file picker UI, and exports/import.
## [4.3.5.24] - 2026-06-14

3D Batch: effects can be drag-reordered inside the Add-variable dialog, kept in
sync with the object (and so the layer-effects dialog).

### Added
- **Drag-reorder effects in the Add-variable dialog.** When the object has two
  or more effects, the dialog shows a small drag-to-reorder list of them above
  the attribute tree. Dragging rewrites the effect order ON THE OBJECT (the same
  order the layer-effects dialog uses, so the two stay in sync), and the
  attribute tree's instance ordinals (#1, #2, ...) update to match. This is the
  second of the two ways to reorder effects you asked for (the layer-effects
  dialog being the first).

### Robustness
- Reordering here is safe because of stable effect ids (v4.3.5.21): a variable
  bound to a specific effect by its id keeps driving THAT effect across the
  reorder, even though its positional ordinal changes. The reorder is applied
  live, so it's reflected on the canvas even if the dialog is cancelled.

### Validation
- New tests (reorder list shown only with 2+ effects, dragging writes the new
  order to the object, an eid-bound variable still drives the same effect after a
  dialog reorder); full suite 343 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.

### Notes
- Still to do: creating a variable from a multi-selection with a tree filtered
  to the selection's common attributes, document-mode header/footer batching,
  halftone pattern-file picker UI, and exports/import.
## [4.3.5.23] - 2026-06-14

3D Batch: a variable can now drive several objects via a link/unlink dialog
(one variable, many objects).

### Added
- **Link/unlink objects dialog.** A variable (column) can be linked to more than
  one object so a single row value drives them all (e.g. the same text on three
  text boxes, or one shadow toggle across several shapes). In the template tab,
  each variable has a link button (next to remove); in the table tab, right-click
  a column header -> "Link objects". The dialog lists every object across the
  document that the variable's attribute can apply to (incompatible objects are
  hidden), with the current targets pre-checked. The data layer for this
  (extra_targets) shipped earlier; this is the UI to manage it.
- **Object count shown.** When a variable drives more than one object, its data
  name shows "(N objects)".

### Validation
- New tests (dialog lists only compatible objects with current targets
  pre-checked, accept writes primary + extra targets, end-to-end multi-target
  apply sets the same value on all linked objects, empty selection is rejected);
  full suite 340 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Creating a variable from a multi-selection with a tree filtered to the
  selection's COMMON attributes (header "Text (2 objects)") is the related
  follow-up; this release covers linking objects to an existing variable.
- Still to do: drag-reorder of effects in the Add-variable tree (identity is in),
  the common-attribute multi-selection tree, document-mode header/footer
  batching, halftone pattern-file picker UI, and exports/import.
## [4.3.5.22] - 2026-06-14

3D Batch: page numbers are now 1-based in the UI, and page 0 means "cross-page".

### Changed
- **Page targeting is 1-based, with 0 = cross-page.** The per-row Page field
  used to show the internal 0-based index (page 1 displayed as "0"), which was
  confusing. It now shows the natural page number (page 1 is "1", page 2 is "2").
  Entering **0** (or "crosspage" / blank) makes the row CROSS-PAGE: it applies to
  every page instead of one. A cross-page row shows on every page in the table's
  page filter. Internally page_target stays 0-based for a concrete page and is
  None for cross-page; the UI layer does the 1-based translation.

### Validation
- New tests (page display/parse helpers map 0<->cross-page and N<->N-1, a
  cross-page row applies to all targeted pages, a concrete page row applies only
  to that page); full suite 336 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.

### Notes
- A cross-page row applies each column wherever its target object resolves; with
  multi-target columns that's several pages. (A single object lives on one page,
  so a cross-page row on it still only changes that page -- as expected.)
- Still to do: drag-reorder of effects in the Add-variable tree (identity is in),
  link/unlink-objects dialog, variable tree filtered to a multi-selection's
  common attributes, document-mode header/footer batching, halftone pattern-file
  picker UI, and exports/import.
## [4.3.5.21] - 2026-06-14

3D Batch: stable effect identity, so a variable stays bound to a specific effect
across reordering (foundation for robust multi-effect batching).

### Added
- **Effects have a stable id (`eid`).** Each layer effect now carries a stable
  per-effect id, generated on creation and serialized. This is the foundation
  for binding a batch variable to a SPECIFIC effect instead of its position.
- **Batch columns can bind to an effect by id.** A column gained an
  ``effect_id`` field. When set, it targets that exact effect instance,
  overriding the positional ordinal in the path -- so reordering effects on the
  layer doesn't re-point the variable to a different instance. Adding a variable
  for an effect that's already on the object now records its eid automatically,
  so it's reorder-safe from the start. Serialized; empty = positional (backwards
  compatible).

### Validation
- New tests (effects get unique eids, eid survives serialization,
  effect_id_for_path resolves the right instance, an eid-bound column survives a
  reorder while a positional one wouldn't, column effect_id serializes); full
  suite 333 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Drag-reorder of effects inside the Add-variable tree (kept in sync with the
  layer-effects dialog) is the next step; the identity it relies on is now in,
  so reordering can be made safe.
- Still to do: link/unlink-objects dialog, variable tree filtered to a
  multi-selection's common attributes, page numbering 1-based (0 = cross-page),
  document-mode header/footer batching, halftone pattern-file picker UI, and
  exports/import.
## [4.3.5.20] - 2026-06-14

3D Batch: selection-box now tracks batched/recorded geometry, and halftone
patterns are batched by file path instead of a raw base64 cache.

### Fixed
- **Selection box ignored batched size changes.** While a batch row is
  projected, the canvas renders the row applied to a deep copy, but the live
  object still had the old geometry, so the bounding box (and its handles) stayed
  at the old size. The overlay is now driven by the PROJECTED object, so it
  matches what's drawn (e.g. a batched width/height).
- **Recording didn't show live edits.** If a row was being projected when you
  started recording, the canvas kept rendering that projection on a deep copy,
  so live edits during recording (size changes, the selection box) didn't show.
  Starting a record now drops the active projection, so the canvas shows your
  live edits.

### Changed
- **Halftone patterns are batched by file path.** The old ``ht_patterns``
  (base64 image cache) was offered as a batchable text field, which was
  meaningless and tied a row to an internal backup. It's removed from batch;
  instead a halftone effect now exposes a pattern FILE PATH (``ht_pattern_path``,
  plus per-channel ``#2``..``#4`` when the colour mode uses channels). Setting it
  loads the PNG from the path at apply time (downscaled like the UI), so the path
  is the source of truth -- exactly what an imported file needs. The pattern mode
  remains batchable as ``ht_pattern_mode``. Paths are serialized
  (``ht_pattern_paths``).

### Validation
- New tests (overlay reflects projected geometry, start-recording clears the
  projection, halftone pattern path loads a file / rejects a bad one / is
  serialized, raw base64 patterns no longer batchable); full suite 328 passed /
  3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- A UI to pick halftone pattern files (open-file with preview) outside the
  effect dialog is a follow-up; the data layer (path = source of truth) is in.
- Ordinal effect paths are still positional (#1 = first on the layer). Making
  variables stick to a specific effect across a reorder (stable effect identity)
  and drag-reorder inside the Add-variable tree are the next big item, per the
  discussion.
- Still to do: link/unlink-objects dialog, variable tree filtered to a
  multi-selection's common attributes, page numbering 1-based (0 = cross-page),
  document-mode header/footer batching, exports/import.
## [4.3.5.19] - 2026-06-14

3D Batch: unique column-header validation and a tidier (collapsed) Add-variable
tree.

### Added
- **Column headers are kept unique.** Variable names must be unique (export/
  import identifies columns by header), so the UI now prevents duplicates: in
  the value editor a name that clashes with another column is rejected and the
  field flagged red with a tooltip; in the Add-variable dialog, accepting with a
  duplicate (or repeated) name flags the offending fields and shows a warning
  instead of accepting. Row names are left free (they're data, not headers).

### Changed
- **Add-variable tree starts collapsed where it's deep.** The Layer Effects
  group and its per-instance subgroups now start collapsed (they can get long,
  especially with several instances); Content / Geometry / Style stay expanded
  since they're short flat lists. Adding an instance expands Layer Effects and
  the new subgroup so it's visible.

### Validation
- New tests (header-uniqueness helper incl. case-insensitive and self-exclude,
  dialog rejects a duplicate name then accepts a fresh one, effects collapsed by
  default); full suite 322 passed / 3 skipped. Old CSV batch and FORMAT_PATCH
  untouched.

### Notes
- Reordering effects already exists in the layer-effects dialog (drag-and-drop),
  and the Add-variable tree already reflects the template's existing effects as
  "(on object)" instances in layer order; ordinal batch paths (#1, #2, ...)
  follow that order. If variables should "stick" to a specific effect across a
  reorder, that's a follow-up to discuss.
- Still to do: the link/unlink-objects dialog (one variable, several objects),
  the variable tree filtered to a multi-selection's common attributes, page
  numbering 1-based (0 = cross-page), document-mode header/footer batching, and
  exports/import.
## [4.3.5.18] - 2026-06-14

3D Batch: nicer Add-variable dialog -- inline name fields and manual
multi-instance effects.

### Changed
- **Variable names are now inline text fields.** The Add-variable tree had a
  double-click-to-edit cell for the variable name, which was awkward. Each
  checkable attribute now has a real text field next to it you can click and
  type into directly (with a "variable name (optional)" placeholder).

### Added
- **Add several instances of the same effect manually.** The dialog gained a
  "+ Add effect instance" button (pick the effect type from its menu). Each
  click adds another instance subgroup to the tree (drop_shadow #2, #3, ...),
  so you can batch multiple same-type effects (e.g. several drop shadows on one
  object) without recording them first. Checks and typed names are preserved
  when the tree rebuilds after adding an instance.

### Validation
- New tests (line-edit names returned on accept, add-effect-instance adds the
  ordinal subgroup and returns it with its name, checks/names survive an
  instance-add rebuild); existing tree-dialog test updated for the line-edit
  names; full suite 319 passed / 3 skipped. Old CSV batch and FORMAT_PATCH
  untouched.

### Notes
- Still to do: the link/unlink-objects dialog (one variable, several objects),
  the variable tree filtered to a multi-selection's common attributes, page
  numbering 1-based (0 = cross-page), document-mode header/footer batching, and
  exports/import.
## [4.3.5.17] - 2026-06-14

3D Batch: several effects of the same type now fully work (record, projection,
and the variable tree), plus a master-switch precedence fix.

### Fixed
- **Master "All effects" off now wins.** With ``all_enabled=false`` and an
  effect's ``enabled=true`` in the same row, the shadow used to appear: creating
  the effect via Path A turned the master on as a side effect, overriding the
  explicit master-off. Path A now only flips the master on when the object had
  NO effects at all (the genuine first-effect case); an explicit
  ``effects.all_enabled`` in the row applies last (lowest priority) and stays
  authoritative, so master-off reliably hides every effect.
- **The 2nd effect of a type could be turned off but not on.** After recording
  two drop shadows, projection rebuilt the object from a template with no
  shadows, and the ``#2`` path couldn't create the second instance (Path A was
  first-instance only), so it never appeared. Path A now pads instances up to
  the requested ordinal (you can't have a 2nd without a 1st), so a recorded or
  hand-made ``drop_shadow#2`` projects correctly and toggles both ways.

### Added
- **Add-variable tree handles duplicate effects.** For an effect already on the
  object, the tree shows one expandable subgroup per existing instance
  ("drop_shadow", "drop_shadow #2", ... marked "on object"), plus one extra
  "#N (new)" subgroup to batch the next instance even though the object doesn't
  have it yet. So you can add a variable for a second same-type effect directly,
  instead of being blocked because the first is already checked.
- **More batch logging** around the master switch and Path-A effect creation
  (``registry.all_enabled_set``, ``registry.pathA_create_effect`` with whether
  it set the master), to trace effect/master interactions from the debug log.

### Validation
- New tests (master-off overrides Path-A enable, Path A leaves the master alone
  when the object already has effects, plus the ordinal/seed/duplicate coverage
  from 4.3.5.16); full suite 317 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.

### Notes
- Effect dialog and Properties already read the live object, so in record mode
  they reflect the current state (incl. effects added while recording); moving a
  field there captures it into the record via the normal edit hook.
- Still to do: the link/unlink-objects dialog (one variable, several objects),
  the variable tree filtered to a multi-selection's common attributes, page
  numbering 1-based (0 = cross-page), document-mode header/footer batching, and
  exports/import.
## [4.3.5.16] - 2026-06-13

3D Batch: seed-value fix for effect toggles, and support for several effects of
the same type on one layer.

### Fixed
- **Seeded effect-toggle cells were misleading.** Adding a variable for an
  effect's ``enabled`` flag on an object that doesn't have the effect produced
  an empty cell that visually showed the first choice ("true") without actually
  storing it, so projection did nothing until you toggled it. The ``enabled``
  reader now returns a concrete value: "false" when the object has no such
  effect, or the real state when it does. So a seeded cell is "false" (per the
  template) and you flip it to "true" -- one extra click, but no phantom value.

### Added
- **Several effects of the same type per layer are now batchable
  independently.** Paths gained an ordinal index: ``effects.drop_shadow.enabled``
  targets the first drop shadow (unchanged, backwards compatible), while
  ``effects.drop_shadow#2.enabled``, ``#3`` and so on target the later instances
  in layer order. ``describe_object`` emits these for objects that have
  duplicates, ``find_descriptor`` resolves them, and recording captures a newly
  added 2nd/3rd instance under its ordinal path (the first, unchanged, instance
  is left alone). Path-A creation (an effect the template doesn't have) still
  applies to the first instance only -- you can't fabricate an arbitrary Nth
  instance out of nothing, but once the instances exist (e.g. by recording) each
  is independently addressable.

### Validation
- 7 new tests (enabled-reader false/true per template, ordinal paths emitted,
  ordinal descriptor targets the right instance, ordinal batch applies
  independently, Path-A only for the first instance, recording captures the 2nd
  same-type effect); full suite 315 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.

### Notes
- Still to do: the link/unlink-objects dialog (one variable, several objects),
  the variable tree filtered to a multi-selection's common attributes, page
  numbering 1-based (0 = cross-page), document-mode header/footer batching, edit/
  remove icons (pending PNGs), record-navigation niceties, and exports/import.
## [4.3.5.15] - 2026-06-12

3D Batch: five fixes found from the debug log, around record mode and effects.

### Fixed
- **Edits during recording leaked onto the template.** An effect added while
  recording stayed on the base object after stop. Restore now replaces the whole
  effects list and the master flag from the baseline snapshot, so a
  newly-added effect is removed from the template (it belongs to the record).
- **Recording captured every effect field.** Adding a default effect recorded
  all ~7 of its fields. New-effect fields are now compared against the effect's
  default, so only the fields that actually differ are captured (plus
  ``enabled``). Adding a default drop shadow records just ``enabled=true``.
- **Adding a variable did nothing.** There was no record yet, and the new
  column's cells were empty, so projection had nothing to apply. Adding a
  variable now ensures at least one record exists and pre-fills the new column
  in every record with the object's current value.
- **The Add-variable tree didn't show existing variables.** Attributes already
  used as variables for the object are now shown pre-checked, disabled, and
  marked "already a variable", so adding more variables for the same object
  doesn't hide or duplicate the existing ones.

### Changed
- **Effects are off by default.** A new object's master "All effects" switch
  (``effects_enabled``) now defaults to off -- an object with no effects has
  nothing to show. Adding an effect (via the dialog or via a batch column /
  Path A) turns it on automatically; the user can switch it off to hide effects.
  Backwards compatible: an older file with effects but no saved flag loads with
  the master on. (This also fixed the "shadow does nothing" case: a Path-A
  effect now turns the master on, so it actually renders.)

### Validation
- 6 new tests (record effect doesn't leak to template, record captures only
  changed effect fields, default effects_enabled is false, add-variable seeds a
  record and value, add dialog shows existing variables); 9 existing tests
  updated for the off-by-default master and the seeded record; full suite 308
  passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still to do: the link/unlink-objects dialog (one variable, several objects),
  the variable tree filtered to a multi-selection's common attributes, page
  numbering 1-based (0 = cross-page), document-mode header/footer batching, edit/
  remove icons (pending PNGs), record-navigation niceties, and exports/import.
## [4.3.5.14] - 2026-06-12

3D Batch: detailed logging so the "effect doesn't show" issue can be traced.

### Added
- **3D Batch logging.** The existing debug log (Help -> "Debug log (curves /
  keys / batch)") now also records the batch flow: toggling Batch edit, adding a
  variable, filling a value, projecting a record to the canvas, record
  start/stop/capture, Path-A effect creation, and every cell applied by a row
  (with the object id, how many effects it has, and its master effects_enabled
  after the apply). This makes it possible to see exactly what happens on each
  click and why an effect may or may not appear.

### How to use
- Help menu -> enable "Debug log (curves / keys / batch)"; it shows the log file
  path. Reproduce the issue (add the variable, toggle Batch edit, fill the
  value), close the editor, and send the file. The relevant lines are tagged
  ``editor.batch_edit_toggle``, ``tpl.add_variable``, ``tpl._set_val``,
  ``tpl._project_to_canvas`` (incl. a SKIP line when projection is off because
  recording), ``apply_row.cell``, ``registry.pathA_create_effect``, and
  ``render.batch_preview applied``.

### Validation
- Full suite 302 passed / 3 skipped (logging is a no-op when disabled). Old CSV
  batch and FORMAT_PATCH untouched.

### Notes
- The instrumented build is to pin down the "All effects + shadow enabled does
  nothing" report, which couldn't be reproduced in tests. Still to do: link/
  unlink-objects dialog, variable tree filtered to a multi-selection's common
  attributes, page numbering 1-based (0 = cross-page), icons, record-navigation
  niceties, exports/import.
## [4.3.5.13] - 2026-06-12

3D Batch: a column can now drive several objects (data layer), and the text-box
attribute set is much more complete.

### Added
- **One variable, multiple objects (data layer).** A batch column can now carry
  extra targets besides its primary one, and the row's value is applied to every
  target that resolves (with the same attribute). So one variable can set the
  same text on two text boxes, or toggle a shadow on two shapes. Serialized
  (``extra_targets``); backwards compatible (empty = single target). The UI to
  link/unlink objects to a variable is coming next.
- **Many missing text-box attributes are now batchable.** Added bold, italic,
  underline, strikethrough, line height, letter spacing, auto-shrink, auto-fill,
  min/max font size, wrap, and padding (previously only text, colour, font
  size/family, and alignment were exposed).

### Validation
- 5 new tests (text-box autofit/style attributes offered and applied, multi
  target applies to all objects, multi-target serialization); full suite 302
  passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still to do: the link/unlink-objects dialog for a variable, the variable tree
  filtered to attributes common to a multi-selection, page numbering shown
  1-based (with 0 = cross-page), edit/remove buttons as icons (pending PNGs),
  record-navigation niceties, and the exports/import phase.
## [4.3.5.12] - 2026-06-12

Layer effects: effects are no longer dropped when disabled (so they survive for
batching), and a master "All effects" switch is now a batchable variable.

### Fixed
- **Disabled effects were dropped from the object.** The effect dialog only
  stored effects whose own checkbox was on, so an effect you added but left off
  simply vanished -- and in batch/record mode there was nothing to capture or to
  toggle via ``effects.<type>.enabled``. The dialog now keeps ALL effects on the
  object (each with its own enabled flag); the renderer still skips disabled
  ones, so the picture is unchanged, but the effect persists and is batchable.
  This also fixes "I don't see my changes in record mode" (the effect wasn't
  being stored, so nothing rendered and nothing was captured).

### Added
- **Master "All effects" switch (``effects.all_enabled``).** The effect dialog's
  master checkbox (renamed "All effects") now drives a real per-object flag
  ``effects_enabled`` instead of a derived "any effect enabled". When off, no
  effect renders even if individual effects are on -- but the effects stay on the
  object, so nothing is lost. It is exposed as a batchable enum variable
  ``effects.all_enabled`` (offered in the Add-variable tree even when the object
  has no effects yet), so a record can switch every effect on/off at once.
- ``effects_enabled`` is serialized (round-trips; defaults to True on load and
  for new objects).

### Validation
- 11 new tests (master renders on/off while effects stay, serialization
  round-trip + default, effects.all_enabled batchable and offered without
  effects, disabled effect stays but doesn't render, master in the tree dialog,
  master batched through a row); 2 existing tree/registry tests updated for the
  added master entry; full suite 298 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.

### Notes
- Still to do: edit/remove buttons as icons (pending PNGs), record-navigation
  niceties (new-from-base / from-current / reset to defaults), row locking from
  the canvas, and the exports/import phase.
## [4.3.5.11] - 2026-06-12

3D Batch: batch-edit mode behaviour fixes, a Path-A effect-default fix, big
performance fix, standard colour picker, and undo for removing a variable.

### Changed
- **Batch edit = recording.** The toolbar "◆ Batch edit" toggle now starts and
  stops recording into the selected record. You can't edit in batch mode
  without recording (that would change the template), so the two are one action.
  The panel's "● Record edits" button and the toolbar toggle stay in sync.
- **Structural edits blocked in batch edit.** Inserting, deleting, or
  duplicating objects is refused while in batch edit (it would change the
  template for every record), with a short message. Previously you could e.g.
  draw an ellipse mid-record.
- **No lingering banner.** Switching to Properties when not recording leaves
  batch edit and clears the BATCH EDIT banner. While recording it stays, and
  Properties edits then feed the record (not the template).

### Fixed
- **Path-A effect defaults.** An effect created by a batch column (one the
  object didn't have) used the dataclass defaults, so e.g. a drop shadow pointed
  the opposite way (direction 135 vs the UI's 315). Effect creation now uses the
  same defaults as the "add effect" UI via a shared ``make_default_effect()``,
  so Path-A effects match hand-added ones. The UI uses the same helper, so they
  can't drift.
- **Performance: switching row sets / opening the table editor was very slow.**
  The table and template panels cross-refreshed each other and ping-ponged, so
  one rebuild fired hundreds of times. Guarded the cross-link; switching to the
  demo set dropped from ~390 ms to ~45 ms, binding from costly to ~1 ms. Rebuild
  also no longer triggers a canvas re-render (that happens only on row-selection
  / value edits).
- **Standard colour picker.** Colour cells and the template colour fields now
  open EDOF's own colour dialog (SV square + hue/alpha), not Qt's.

### Added
- **Undo for removing a variable.** Deleting a variable now records an undo
  step (the whole document, which includes the batch config, is snapshotted), so
  Ctrl+Z restores the column and its data. The confirmation says so. Undo/redo
  rebinds the batch panels to the restored config.
- **"Show selected on canvas" shows its state.** The button is green when
  projecting, plain when off, and is disabled (showing "Editing live") while
  recording, since recording edits live rather than projecting.

### Validation
- 11 new tests (batch-edit toggle records, insert blocked in batch edit,
  Properties edits record into the row, Path-A uses UI defaults, make_default
  for all types, undo restores a removed variable, show-on-canvas visual state
  and recording-disable, colour-picker helper); full suite 292 passed / 3
  skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still to do: edit/remove buttons as icons (pending PNGs), record-navigation
  niceties (new-from-base / from-current / reset to defaults), row locking from
  the canvas, and the exports/import phase.
## [4.3.5.10] - 2026-06-11

3D Batch: record mode -- a classic/batch edit toggle with an in-canvas banner,
and recording canvas edits into a record (columns created automatically).

### Added
- **Classic / batch edit toggle** in the toolbar ("◆ Batch edit"). Independent
  of the right-hand tab: the toggle controls WHAT canvas edits affect (the base
  document vs a batch record), the tab controls what you look at. Turning it on
  shows the 3D Batch tab.
- **In-canvas BATCH EDIT banner.** While in batch edit mode the canvas paints a
  screen-fixed banner so it's unmistakable; it turns red with "● REC" while a
  record is being recorded.
- **Record canvas edits into a record.** The template panel has a "● Record
  edits" button. While recording, every edit you make on the canvas is diffed
  against a baseline snapshot and the changed attributes are written into the
  selected record -- creating columns automatically from whatever you change
  (text, position, colour, size, effects, ...). Stopping recording restores the
  live document to the baseline (the edits belong to the record, not the base)
  and the record is shown via the non-destructive canvas projection.
- **Locked records can't be recorded into.** Starting a recording on a locked
  record is refused.

### Canvas API
- ``set_edit_mode('classic'|'batch')`` and ``set_batch_recording(bool)`` drive
  the banner; ``EdofEditor._on_chg`` feeds edits to the recorder (re-entry
  guarded).

### Validation
- 4 new tests (edit-mode banner state, recording creates columns from canvas
  edits, stop restores the base document while the record keeps its values,
  locked record can't record); full suite 283 passed / 3 skipped. Old CSV batch
  and FORMAT_PATCH untouched.

### Notes
- Next: record navigation niceties (new-from-base / from-current / reset to
  defaults), row locking from the canvas, and the exports/import phase.
## [4.3.5.9] - 2026-06-11

3D Batch: one shared preview on the main canvas (per-panel previews removed).
This is the start of record mode.

### Changed
- **Single preview on the main canvas.** Both batch editors used to carry their
  own small row preview, so opening both showed two previews. Those are gone.
  Selecting a record now projects it NON-DESTRUCTIVELY onto the main canvas
  instead: the canvas renders a deep copy of the document with that row applied,
  and the live document is never touched (selection and editing still act on the
  base). The table editor's grid now fills its dock; the template panel ends
  with a "Show selected on canvas" toggle.
- **Page follow.** Projecting a page-scope record switches the canvas to that
  record's target page.

### Added
- Canvas API: ``set_batch_preview_row(row, page_idx=None)`` and
  ``clear_batch_preview()``. Leaving the batch tab (or closing the table dock)
  clears the projection unless the other batch editor is still open and wants
  it.

### Validation
- Tests rewritten for projection (row projects to canvas without mutating the
  doc, page-scope projection switches page, document-scope projection, toggle
  clears, projection survives table changes, non-destructive canvas preview);
  full suite 279 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Next: the rest of record mode -- record/stop recording, the classic/batch
  edit toggle (toolbar + in-canvas "BATCH EDIT" indication), automatic column
  creation from what you change on the canvas, and row locking from the canvas.
## [4.3.5.8] - 2026-06-11

Renderer: fixed the ellipse stroke being clipped on the right/bottom edge.

### Fixed
- **Ellipse stroke clipped on the right (and bottom).** The shape buffer was
  exactly the object's size (w×h px), so the outer half of a wide stroke --
  which PIL centres on the path edge and extends ~half the stroke width beyond
  it -- was cut off at the buffer's right/bottom edge. The buffer is now padded
  by half the stroke width on every side and all shape drawing is offset into
  it (paste shifted back), so the stroke is symmetric on all four sides. This
  also covers rect outlines, lines, and polygons drawn through the same path.

### Validation
- 5 new tests (ellipse stroke symmetric at two widths, ellipse fill still
  drawn, rect stroke symmetric, rotated ellipse renders); full suite 278 passed
  / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.
## [4.3.5.7] - 2026-06-11

3D Batch: removing a variable now asks for confirmation.

### Changed
- **Deleting a variable is no longer one click.** The "✕" next to a variable in
  the Template panel now pops a confirmation that names the variable and how
  many records hold a value in it, so it can't be wiped by an accidental click.
  Answering No keeps it; Yes removes the column and its data.

### Validation
- 1 new test (No keeps the variable, Yes removes it); full suite 273 passed / 3
  skipped. Old CSV batch and FORMAT_PATCH untouched.
## [4.3.5.6] - 2026-06-11

3D Batch: a tree-based "add variables" dialog with in-dialog naming, and
Path-A effect creation (batch effects an object doesn't have yet).

### Added
- **Tree "Add variables" dialog.** Replaces the flat list. Attributes are
  grouped (Content / Geometry / Style / Layer Effects). Each leaf has a checkbox
  and an inline editable variable-name field, so you check several at once and
  name them right there. Layer Effects is collapsed by default and expands to
  all 13 effect types, each expanding to its fields; effects already on the
  object are marked "(on object)".
- **Path A: batch effects the object doesn't have.** The tree offers every
  effect type even when the object has none, and applying a value for such a
  field now creates the effect on demand -- disabled by default
  (``enabled=False``) with constructor defaults -- then sets the field. So a row
  can add a drop shadow the base template lacks: empty value means no effect,
  and the effect only shows once a row enables it. ``find_descriptor`` resolves
  effect paths even when the effect is absent.

### Registry helpers
- ``all_effect_descriptors()``, ``effect_types()``, ``effect_fields(type)`` for
  building the tree and (later) the generated reference manual.

### Validation
- New tests (tree returns checked leaves with names, tree offers effects not on
  the object, Path-A creates a disabled effect, descriptor synthesis, all
  effect types covered); the old multi-select test became a tree test; full
  suite 272 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Next: unify the preview into the main canvas (non-destructive row projection,
  removing the per-panel previews), then the rest of record mode (recording,
  classic/batch edit toggle with in-canvas indication, row locking from the
  canvas).
## [4.3.5.5] - 2026-06-11

3D Batch UI split, fixing the previous bad layout: the Table editor goes back
to the bottom dock; the Template editor is a vertical panel in the right tab.

### Changed
- **Two separate batch editors, each where it fits.**
  - **Table editor** -> bottom dock again (grid + side preview, where there is
    width). View ▸ "3D Batch (Table editor)" toggles it. This is the full table
    with scope, row filter, demo set, smart cells, duplicate/copy/paste/sort,
    and row index numbers.
  - **Template editor** -> a vertical panel in the right-side tab beside
    Properties (about the Properties width). No table here. View ▸ "3D Batch
    (Template panel)" switches to it.
- The previous build wrongly moved the whole table+preview into the narrow
  right tab, which broke the layout. Reverted that.

### Added (Template panel)
- **Vertical authoring layout**: Mode + Rows (production/demo) selectors, a
  record list, record navigation (‹ Prev / Next ›, Duplicate, New, Delete), a
  scrollable value list, and a preview at the bottom.
- **Per-variable value blocks**: each variable shows an editable variable name
  (what goes to CSV when set), a non-editable data name underneath
  (``<type>-<N>.<attr>``, the auto path), the type-aware value editor, and a
  "✕" to remove that variable. An "Add variable…" button at the bottom adds a
  column (same flow as the table's Add column).
- **Row lock groundwork**: ``BatchRow.locked`` (persisted). A locked record
  shows a 🔒 and its value editors are disabled, so its values can't be edited
  in the template panel. (The full canvas batch-edit mode that sets/locks rows
  is the next step.)
- Both editors read/write the same live ``doc.batch`` and are cross-linked, so
  an edit in one refreshes the other; both follow the active page.

### Validation
- Template tests rewritten for the standalone panel (record list, form fields
  match columns, edit writes to model, add/duplicate record, locked record not
  editable, demo rows); full suite 268 passed / 3 skipped. Old CSV batch and
  FORMAT_PATCH untouched.
## [4.3.5.4] - 2026-06-11

3D Batch: the batch editor moved into a tab beside Properties, with an
optimized preview resize.

### Changed
- **Batch editor is now a right-side tab, not a bottom dock.** The right panel
  is a tab group: "Properties" and "3D Batch". You switch between them in
  place; View ▸ "3D Batch panel" jumps to the batch tab. The old bottom dock is
  gone. Switching to the batch tab (or changing pages) rebinds it to the live
  document.

### Added
- **Optimized preview resize.** Resizing the panel rescales the cached preview
  image immediately (cheap) and then re-renders crisply at the new size after a
  short debounce, so dragging the panel edge stays smooth instead of
  re-rendering on every pixel. The preview now renders at a DPI scaled to the
  panel width (clamped), so a wider panel yields a sharper image.

### Validation
- 2 new tests (resize caches the pixmap and survives a resize, resize timer is
  debounced); the editor dock test became a tab test; full suite 268 passed / 3
  skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Next: the big batch-edit mode -- a classic/batch edit toggle (toolbar + an
  in-canvas "BATCH EDIT" indication), template-vs-row canvas editing, concurrent
  record + preview, row lock, record navigation, and the value list with
  rename/clear/add-variable. Then the larger tree-based "add columns" dialog
  (checkboxes, collapsible effect trees, in-dialog variable naming, and
  Path-A effect creation), and the exports/import phase.
## [4.3.5.3] - 2026-06-11

3D Batch table: row duplication, row index numbers, row copy/paste, and column
sorting.

### Added
- **Duplicate row.** A "Duplicate row" button (and Ctrl+D) clones the selected
  row -- a deep copy of its values inserted right after it, named "<name>
  copy".
- **Row index numbers.** The table's vertical header now shows each row's
  1-based model index, so rows are identifiable at a glance (the number follows
  the row even under the active-page filter).
- **Copy / paste rows.** Ctrl+C copies the selected rows into an internal
  clipboard (deep copies); Ctrl+V pastes them as new rows after the selection.
- **Sort by column.** Clicking a column header sorts the active row set by that
  column, toggling ascending/descending on repeat clicks. Number columns sort
  numerically; the Name and Page lead columns sort too. Sorting reorders the
  underlying rows.

### Implementation notes
- All of these act on the active row set (production or demo) via
  ``_rows_list()`` and translate through the visible-rows mapping, so they
  behave correctly under the active-page filter and in either row set.

### Validation
- 5 new tests (duplicate row, row index labels, copy/paste rows, sort by a
  number column ascending/descending, sort by name); full suite 266 passed / 3
  skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Next: move the batch editor into a tab next to Properties (off the bottom
  dock) with an optimized preview resize, then the big batch-edit mode (canvas
  template-vs-row editing, concurrent record + preview, row lock, record
  navigation).
## [4.3.5.2] - 2026-06-11

3D Batch: layer effects are now batchable; the "Layer Effects" button label is
unified; and chromatic aberration is fixed on black objects.

### Added
- **Layer effects in the attribute registry.** When an object carries a layer
  effect, that effect's fields become batchable, addressed as
  ``effects.<type>.<field>`` (e.g. ``effects.drop_shadow.distance``,
  ``effects.halftone.ht_dot``). Covered for all 13 effect types (drop/inner
  shadow, outer/inner glow, stroke, long shadow, chromatic aberration,
  halftone including its pattern list, colour/gradient overlay, bevel, light
  sweep, texture overlay) with the right editor per field -- colour pickers,
  enums with the real value sets, numbers, and the halftone pattern list.
  Each effect's ``enabled`` is batchable too, so one row can switch an effect
  on and another off. Batch tweaks an existing effect; it does not create one.
- **`visible` is batchable; `locked` is not.** A row can hide/show an object;
  ``locked`` is deliberately excluded (no per-row meaning), per the batch-edit
  rules.

### Fixed
- **Chromatic aberration on black objects.** The effect tinted each R/G/B
  channel by its own brightness, so a pure-black (or fully-saturated
  single-colour) object -- whose channels are near zero -- produced black on
  every layer and summed to a flat black blob with no colour split. Both the
  CPU and GPU paths now use ``max(channel, silhouette)`` as the per-channel
  source, so a solid object carries its tint and the offset layers separate
  into real colour fringes, while photographic content keeps its channel
  detail wherever the channel exceeds the silhouette.
- **Unified "Layer Effects" button label.** The one button reading "✨ Layer
  Effects… (blend mode, effects)" now matches the short "✨ Layer Effects…"
  used everywhere else.

### Validation
- 6 new tests (effects offered only when present, apply effect field, halftone
  pattern field, visible batchable / locked not, CA black-object fringes); full
  suite 261 passed / 3 skipped. Verified an effect's enabled toggle reaches the
  renderer (shadow appears/disappears). Old CSV batch and FORMAT_PATCH
  untouched.

### Notes
- Roadmap (not implemented): 4D batch -- targeting objects *inside* a
  sub-document (needs unpack/repack of the embedded doc); and growing the
  registry into a generated object/effect reference manual.
## [4.3.5.1] - 2026-06-11

3D Batch: the demo (template) row set now has a UI.

### Added
- **Demo rows + "Export demo".** A "Rows: Production / Demo (template)"
  selector switches the table (and the template view) between the production
  rows and a separate demo set used for building and previewing the template.
  The two sets are edited identically -- add/delete/edit, table or template,
  with the same preview -- but stay completely independent. An "Export demo"
  checkbox sets the config's flag so a later export/generate can include the
  demo rows when wanted (off by default). Demo rows and the flag persist with
  the document (model support was added in 4.3.2.0).

### Implementation notes
- All row operations now go through one ``_rows_list()`` accessor returning the
  active set, so the visible-rows mapping, the table handlers, the template
  view, the preview, and the status line all act on whichever set is selected.

### Validation
- 4 new tests (demo separate from production, export-demo checkbox sets the
  model, demo rows in the template view, demo + flag round-trip); full suite
  255 passed / 3 skipped. Old CSV batch and FORMAT_PATCH untouched.

### Notes
- Still ahead: the exports/import phase -- four+two batch-file exports,
  encoding/CSV-dialect auto-detection, the result-export matrix, and filename
  token templates. The "Export demo" flag and [ROW_NAME] are the hooks for it.
## [4.3.5.0] - 2026-06-11

3D Batch: the Template authoring view -- a second way to edit the same batch,
alongside the table.

### Added
- **Template edit view** (View ▸ Table edit / Template edit). The left side is
  a row list with Add/Delete; the right side is a value list for the selected
  row -- one labelled field per column, with the same type-aware editors as the
  table (enum dropdown, colour field with a swatch + picker button, file-path
  field with a "…" button, plain editors for number/text), plus Name and (when
  relevant) Page fields. It is a pure alternate view over the same live
  config: edits in either view show up in the other and in the preview, which
  updates live here too.

### Implementation notes
- Both views render from one model and go through the panel's single rebuild
  path, so the row list, the table, the value form, and the preview stay in
  sync. Row indices are translated through the same visible-rows mapping used
  by the table, so the active-page filter applies in the template view as well.

### Validation
- 5 new tests (view switch + row list, form fields match columns, template edit
  writes to the model without mutating the document, add row from template,
  table/template share the model); full suite 251 passed / 3 skipped. Old CSV
  batch and FORMAT_PATCH untouched.

### Notes
- Still ahead: the demo table UI (model support exists) and the exports/import
  phase (four+two batch-file exports, encoding/dialect auto-detection, the
  result-export matrix and filename token templates).
## [4.3.4.6] - 2026-06-11

3D Batch: the preview now refreshes on every table change, not just cell edits.

### Fixed
- **Any table change refreshes the preview.** Adding or deleting a row,
  adding or deleting a column, switching scope, or changing the row filter now
  re-renders the preview for the selected row. Previously only a direct cell
  edit (4.3.4.5) updated it, so structural changes left the preview stale. The
  refresh hangs off the single rebuild path, so every code path that touches
  the table is covered.

### Validation
- 1 new test (preview survives and refreshes across row add and column delete);
  full suite 246 passed / 3 skipped. Renders run on a deep copy; the live
  document is never mutated. Old CSV batch and FORMAT_PATCH untouched.
## [4.3.4.5] - 2026-06-11

3D Batch preview fixes: live updates on edit, correct page selection, working
page stepping.

### Fixed
- **Preview now updates live on edit.** Editing a cell (value, colour, name, or
  page target) re-renders the row preview immediately; previously the preview
  only refreshed when you changed rows, so edits weren't reflected.
- **Preview shows the right page.** In page scope the preview shows the row's
  target page. In document scope it shows the page currently active in the
  editor canvas (and follows it when you switch pages there), instead of being
  stuck on page 1.
- **Page stepping (‹ ›) works.** In document scope the buttons step through the
  pages and enable/disable correctly at the ends. In page scope a row owns a
  single page, so stepping is intentionally disabled (the buttons reflect
  that). The previous code changed the sticky page but the renderer discarded
  it, so the buttons appeared dead.

### Validation
- 3 new tests (live preview on edit, page-scope shows target page with no
  stepping, document-scope stepping enables/disables at the ends); full suite
  245 passed / 3 skipped. Renders run on a deep copy, so the live document is
  never mutated. Old CSV batch and FORMAT_PATCH untouched.
## [4.3.4.4] - 2026-06-11

3D Batch: a row filter for multi-page documents (show all rows vs only the
active page's rows). The single-page Page-column fix shipped in 4.3.4.3.

### Added
- **Row filter (page scope, 2+ pages): "Show all rows" / "Active page rows
  only".** With many pages you can now narrow the table to just the rows whose
  target is the page currently shown in the editor, and it follows the canvas:
  switching pages re-filters live. The filter is hidden when it cannot do
  anything (single page or document scope).
  - All row-index handling (cell edit, delete, preview) goes through one
    table-row -> model-row translation, so editing or deleting a filtered row
    hits the correct underlying record and leaves the hidden rows untouched.

### Validation
- 6 new tests (show-all lists every row, active-page subset, filter follows the
  active page, a filtered edit maps to the right model row, filter inert on a
  single page); full suite 242 passed / 3 skipped. Old CSV batch, rendering,
  and FORMAT_PATCH untouched.
## [4.3.4.3] - 2026-06-11

3D Batch fix: the Page column no longer shows for a single-page document.

### Fixed
- **Page column hidden until there are 2+ pages.** In page-per-row scope a
  single-page document has nowhere else for a row to go, so the leading "Page"
  column was redundant. It now appears only when the document has more than one
  page (matching the "extra page -> 3D" idea). The single source of truth
  (`_show_page_col`) drives the header, the cells, and cell-edit routing
  together, so column indices stay aligned in both cases.

### Validation
- 2 new tests (Page hidden for single page, Page appears with a second page);
  existing panel tests updated for the single-page layout; full suite 235
  passed / 3 skipped. Old CSV batch, rendering, and FORMAT_PATCH untouched.
## [4.3.4.2] - 2026-06-11

3D Batch fixes from feedback: colour swatches now actually appear, and rows
have a Name column.

### Fixed
- **Colour cells now paint on edit.** The swatch + contrasting hex was only
  applied during a full table rebuild, so entering a colour (by hand or via the
  colour dialog) left the cell un-tinted until the next refresh. Editing a
  colour cell now repaints it immediately; the rebuild path shares the same
  painter.

### Added
- **Row name column.** Every row has an optional "Name" (the first table
  column, before "Page"). It persists with the document and is the basis for
  the filename token templates in the upcoming export phase ([ROW_NAME]).
  Leading-column indexing was centralized so the Name + Page columns can't
  drift out of sync with the data columns.

### Validation
- 3 new tests (row name present/editable, row name round-trips, colour cell
  paints immediately on edit); existing panel tests updated for the new column
  layout; full suite 235 passed / 3 skipped. Old CSV batch, rendering, and
  FORMAT_PATCH untouched.

### Notes
- Per-row preview already updates on row change (4.3.4.0). Still ahead: the
  template (right-hand value list) authoring mode and the demo table UI (model
  support exists), then the exports/import phase. Confirmed open from feedback.
## [4.3.4.1] - 2026-06-11

3D Batch polish from feedback: multi-attribute add, renamable variables,
disambiguated auto-headers, and a readable colour swatch.

### Added
- **Multi-select in "Add column…"**: pick several attributes of one object at
  once and get one column per attribute in a single step. (A typed variable
  name applies only when exactly one attribute is selected; multi-selections
  take their auto headers, renamable afterwards.)
- **Rename a variable**: double-click a column header to set/clear its variable
  name. Object name and variable name are independent — the variable name is
  what shows in the header and travels to the exported batch file.
- **Disambiguated auto-headers**: a column with no variable name now shows
  ``<object>-<N>.<attr>`` (e.g. ``textbox-2.text``, ``shape-1.fill-color``) so
  two same-type objects never collide. ``<object>`` is the object's name when
  set, else its type; ``<N>`` is the 1-based index among same-type objects on
  the page; dotted attribute paths are flattened with dashes. Duplicate-name
  highlighting and the red orphan header now key off the shown label.

### Changed
- **Colour cells stay readable.** The fill/stroke/colour cell is painted with
  the colour and the hex text is drawn black or white by the background's
  luminance (so mid-grey, which cannot be inverted, still reads clearly)
  instead of a plain inverse.

### Validation
- 6 new tests (type-ordinal headers, dotted-path flattening, named override,
  multi-select dialog, contrasting colour text, header rename); full suite 232
  passed / 3 skipped. Old CSV batch, rendering, and FORMAT_PATCH untouched.

### Notes
- Roadmap additions (not implemented): custom named document presets
  (size + DPI) in settings; and the template (right-hand value list) editing
  mode as the second authoring approach alongside the table.
## [4.3.4.0] - 2026-06-11

3D Batch step 4: smart cells + row preview, all presentation over the existing
model. Plus a registry fix. Nothing that already works is touched.

### Added
- **Type-aware batch cells.** Each cell now edits according to its column's
  value kind: colour opens a colour dialog and the cell is painted with the
  chosen colour (with contrasting text); enum offers a dropdown of the
  attribute's allowed values; file_path opens an open-file dialog; numbers and
  text use a plain editor. This is pure UI over the 4.3.1.0/4.3.2.0 model --
  the value still flows through the same registry coercion.
- **Per-row preview.** Selecting a row renders the document with that row's
  values applied and shows it beside the table. The render runs on a deep copy,
  so the live document is never mutated. Multipage documents get ‹ › page
  buttons and the shown page is sticky across row changes (it does not snap
  back to page 1). In page scope the row's target page is shown.

### Fixed
- **Ellipse no longer offers "corner radius".** The renderer only honours
  corner_radius for rectangles, but the shape attribute table exposed it for
  every shape. The registry now includes corner_radius only for rect (live
  objects filter by shape_type; the type-only export still lists it).

### Validation
- 6 new tests (cell kind roles, colour swatch, enum choices, preview renders
  without mutating the document, colour parser; plus the ellipse/rect
  corner-radius split); full suite 226 passed / 3 skipped. Old CSV batch,
  rendering, and FORMAT_PATCH untouched.

### Notes
- Next (4.3.5.0): the four+two batch-file exports and the import with encoding
  / CSV-dialect auto-detection. The whole-document generation path and the
  result-export matrix (single files vs one multipage PDF/EDOF, filename token
  templates) follow per the roadmap.
## [4.3.3.0] - 2026-06-11

3D Batch step 3: the first visible piece -- a dockable batch panel in the
editor, built on the 4.3.2.0 model. Everything that already works is untouched;
the panel is hidden until you turn it on.

### Added
- **3D Batch dock** (View ▸ "3D Batch panel"). A bottom dock holding a table
  whose columns are batched object attributes and whose rows are value sets:
  - **Add column…**: select an object on the canvas, then pick one of its
    attributes from the registry (content first, then geometry, then style) and
    an optional human header name. The column targets the object through its
    stable hierarchical ref, so it survives renames and reaches objects nested
    in groups.
  - **Add row / Delete row**, and a **Mode** selector (Page per row / Whole
    document per row). Page scope shows a first "Page" column (per-row target);
    document scope hides it.
  - Editing a cell writes straight back to the model. Duplicate header names
    are tinted amber with a "×N" count; a column whose target no longer
    resolves gets a red header.
- **Deletion integrity**: deleting an object in the editor prunes any batch
  columns that targeted it (the surviving columns and their data are kept).
- **Persistence**: the panel edits the live `doc.batch`, so the batch saves and
  loads with the document (added in 4.3.2.0); reopening shows the same table.

### Implementation notes
- The panel (`edof._apps.batch_panel.EdofBatchPanel`) is a pure view over the
  model -- it owns no batch data and is headless-constructible, so its logic is
  unit-tested under the offscreen platform. Cells are plain text for now; the
  model already supports every value kind, so the smart cell editors (colour
  swatch, file dialog, enum dropdown) land in 4.3.4.0 as presentation only.
- Uses the available Qt table (QTableWidget). When the custom "edof tabs"
  component exists it replaces this table behind the same panel API (roadmap
  TBD).

### Validation
- 8 new panel tests (add column/row, scope switch, duplicate highlight, prune
  on delete, changed signal, editor dock toggle); full suite 220 passed / 3
  skipped. Old CSV batch, rendering, and FORMAT_PATCH untouched.

### Notes
- Next (4.3.4.0): smart cell editors (colour/number/enum/file path) over this
  same model, plus the per-row preview and the whole-document generation path.
## [4.3.2.0] - 2026-06-11

3D Batch step 2: the data model + .edof persistence. Still backend only, no UI,
fully additive -- documents without a batch are byte-for-byte unchanged and
older readers ignore the new section.

### Added
- **`edof.batch.model`: the batch configuration.** Sits alongside a document
  (lazy `Document.batch` property) and holds everything the 3D Batch needs:
  - **ObjectRef** -- a STABLE hierarchical id path (top level down through
    groups), so a column can target an object nested in a group, not just a
    top-level one. `build_ref` / `resolve_ref` / `find_ref_on_pages` create and
    walk these paths.
  - **BatchColumn** -- one batched attribute: stable column_id, ObjectRef +
    registry attribute path, optional human header name (falls back to the
    attribute path), and cached value kind. Columns address attributes through
    the 4.3.1.0 registry, so every value type works from the start.
  - **BatchRow** -- one record: optional page_target (used only in page scope)
    and a {column_id: raw_value} map.
  - **BatchConfig** -- row_scope ('page' | 'document'), the columns, the data
    rows, and a SEPARATE demo-row table (template building / preview, excluded
    from production export unless export_demo is set).
- **Row application** (`apply_row_to_document`): page scope fills only the
  page named by page_target (a column whose object lives on another page is
  skipped); document scope fills every page where the target resolves. Conflicts
  between two columns on the same attribute resolve by the registry's priority
  band (lower wins) -- descriptive of EDOF's existing precedence, renderer
  untouched. Empty cells never overwrite; a bad cell never raises.
- **Integrity helpers**: `prune_dead_columns` (drops columns whose target was
  deleted -- the editor calls this after a deletion) and `orphan_columns`
  (flags unresolved targets for red-header display without removing them);
  `duplicate_name_counts` backs the "same name ×N" highlight.
- **.edof persistence**: `Document.to_dict` emits a `batch` section only when
  non-empty; `Document.from_dict` restores it. Format bumped additively;
  pre-4.3.2.0 files load unchanged (no `batch` key -> empty config).

### Validation
- 18 new model tests; full suite 212 passed / 3 skipped. Verified: refs build
  into and resolve through groups; page-scope skips off-page targets while
  document-scope fills all; pruning removes dead columns and orphans are kept
  but flagged; full .edof save/load round-trip preserves columns/rows and refs
  still resolve on the loaded document; an empty batch is never serialized; a
  document stripped of its batch key loads cleanly. FORMAT_PATCH and GPU paths
  untouched; the old CSV batch is untouched.

### Notes
- Next (4.3.3.0): the batch mode in the UI -- a dockable table, the
  object→attribute→value column picker, and the page-per-row preview, all on
  top of this model with the available Qt table (custom "edof tabs" component
  is a later TBD).
## [4.3.1.0] - 2026-06-11

First step toward the 3D Batch mode (target 4.4.0): the attribute registry.
Pure backend, no UI, no behaviour change to anything that exists.

### Added
- **`edof.batch` attribute registry.** A single introspection layer that, for
  any object, returns its batchable attributes as uniform descriptors (dotted
  path, human label, value kind, allowed enum values, EDOF-matching priority,
  and bound get/set). `set()` owns value coercion, so a consumer always calls
  `descriptor.set(obj, cell)` regardless of whether the attribute is text, a
  number, a colour, an enum, or a file path -- the groundwork that lets the
  later UI add smart cell editors as a pure presentation layer over a complete
  model. Public API: `describe_object`, `describe_type`, `find_descriptor`,
  `apply_value`. Covered types: textbox, imagebox, shape, qrcode,
  subdocument, plus transform/opacity on everything.
  - Empty cell = "leave as-is" (never overwrites). Unknown path or failed
    coercion returns False and never raises (a bad batch cell must not crash a
    render). Numbers accept comma decimals; colours accept #rrggbb, #rrggbbaa,
    and r,g,b[,a]; enums match case-insensitively against the allowed set.
  - Priority bands mirror how EDOF already resolves precedence (content <
    geometry < style < effect); the renderer is untouched -- the batch layer
    will use the band only to pick which of two conflicting columns to apply.

### Validation
- 15 new registry tests; full suite 194 passed / 3 skipped. Verified set()
  reaches the renderer (shape fill change shows in pixels). Object ids confirmed
  stable across .edof save/load (UUID strings) and multipage PDF export
  confirmed working -- the two prerequisites for the batch model. FORMAT_PATCH
  19 and GPU paths untouched.

### Notes
- This release only describes and applies attributes on an object instance the
  caller resolved; object targeting by id / hierarchical path (groups,
  sub-documents) and .edof persistence come in 4.3.2.0.
## [4.3.0.4] - 2026-06-11

Dragging large objects: parts hanging off the page no longer vanish, and the
first drag frame of a huge image with a pattern halftone is bounded instead
of stalling the editor.

### Fixed
- **Overhanging part of a large object vanished during drag.** The drag
  cache rendered the active object into a PAGE-sized buffer, so anything
  hanging off the page (e.g. an image enlarged beyond the canvas) was
  cropped away the moment the drag started and stayed missing for the whole
  gesture. The active object now renders into an ISOLATED buffer sized to
  the object itself (rotation-aware bounds plus the same effects margin the
  effects pipeline uses), independent of the page -- the full object is in
  the cache and every overhang stays visible while dragging. Verified: an
  image spanning -20..120 mm on a 100 mm page keeps its exact edges through
  left/right drags (letterbox fit accounted for); groups shift recursively;
  the document object is never mutated (renders use shifted shallow copies).

### Changed
- **Bounded first-frame cost for heavy drag previews.** Two budgets in the
  interactive (pixelated) drag path: (1) a 600k-pixel cap on the isolated
  buffer -- huge objects render the preview at a reduced internal dpi; and
  (2) when that cap kicks in, the halftone CELL SIZE is scaled by the same
  factor for the preview render only -- the cell loop dominates pattern
  halftones and its count depends on the physical cell size, not pixels, so
  the pixel cap alone could not bound it. Measured on a 4000x3000 image
  scaled past the canvas with a pattern halftone: first drag frame 2.96 s ->
  1.56 s, subsequent moves ~32 ms (~30 fps), and the cost stays ~1.7 s even
  at dpi 400 where it previously grew without bound. The release render and
  the non-interactive active path are exact (24 MP safety cap only); the
  document's effect values are untouched.

### Validation
- Suite 179 passed / 3 skipped; the 4.3.0.3 negative-position matrix passes;
  drag-edge checks pass with letterbox-corrected expectations; preview
  coarsening leaves the document's ht_dot unchanged. FORMAT_PATCH 19 and GPU
  paths untouched.
## [4.3.0.3] - 2026-06-11

Objects can now go off-canvas in EVERY direction (up/left included), and the
halftone pattern click path no longer uses the native-crash-prone style hook.

### Fixed
- **Off-canvas up/left: the image snapped back inside.** Nine compositing
  sites across the renderer clamped paste positions with max(0, ...) because
  PIL's alpha_composite rejects negative destinations -- so an object dragged
  over the TOP or LEFT page edge had its bounding box outside but its IMAGE
  silently shifted back inside the page (right/down were unaffected since
  positive overflow clips naturally). Every site now routes through the
  crop-then-composite helper: images (rotated and plain), text boxes, shapes,
  ellipses, lines, QR codes, sub-documents, the rotated-buffer paths, the
  normal-blend branch of the blend dispatcher, and the active-object drag
  cache. Verified with an 8-case matrix (rect / ellipse / image / shape with
  effects x rotation 0 / 30, moved to negative coordinates): all clip exactly
  at the page edge with the correct visible area, including the
  render_page_active drag path.
- **Halftone pattern click crash (native).** The library submenu attached a
  Python QProxyStyle subclass to enlarge menu icons -- a known native crash
  on Windows (the style is invoked during menu paint after the Python wrapper
  side is torn down), which survived all Python-level guards because it
  segfaults below them. The proxy style is gone; icons are sized with a
  plain stylesheet (harmless where unsupported). The remaining pattern
  handlers (_on_pmode, _refresh_thumbs) are now also guarded, so no
  exception can escape a Qt slot anywhere in the pattern UI.

### Validation
- Suite 179 passed / 3 skipped; negative-position matrix passes for all
  object types and rotations; 120-combo long-shadow smoke passes; halftone
  dialog stress (real menu exec, library with a valid entry + 3 MB corrupted
  entry + junk, mode switching, repeated clicks) passes and the library
  self-heals to valid entries only. FORMAT_PATCH 19 and GPU paths untouched.
## [4.3.0.2] - 2026-06-11

Off-canvas editing now follows the Photoshop model, and the halftone pattern
button is crash-proof (with the root cause -- oversized registry values --
eliminated at the source).

### Changed
- **Photoshop canvas model for off-canvas objects.** The 4.3.0.1 apron
  (which painted overhanging object content on the workspace) is reverted:
  the page clips content at its boundary exactly like a Photoshop canvas.
  Instead, the SCENE now extends well beyond the page as navigable workspace
  (max(50% of the page, 200 px) on every side): objects can be dragged
  completely off-canvas, their selection outline and handles stay visible
  and grabbable out there, the view scrolls over them, and clicking an
  off-canvas object selects it. Verified with synthetic mouse-event tests:
  a drag from x = 40 mm ends at x = 165 mm on a 100 mm page, and a click on
  a fully off-canvas object selects it.

### Fixed
- **Halftone pattern button crash (root cause + defense in depth).**
  Pattern images were stored as FULL-RESOLUTION base64 PNG both in the
  effect and in the QSettings pattern library -- a photo pattern produced
  multi-megabyte strings, and the Windows registry corrupts values that
  large, which is what actually blew up the next click on the button.
  Fixes: (1) patterns are downscaled to max 512 px on load (halftone cells
  are mm-sized; this is far beyond what the stamp can use) and saved as
  optimized PNG; (2) the library reader and writer enforce a 400 KB per-entry
  cap, so an already-corrupted library SELF-HEALS on first read; (3) the
  library menu only builds actions for entries whose thumbnail actually
  decodes; (4) the whole pattern click path (menu, load, set) is wrapped in
  guarded handlers with logging -- in PyQt6 an exception escaping a slot
  aborts the application, so nothing is allowed to escape; (5) the menu is
  released after use instead of accumulating on the dialog. Stress-tested
  with a 3 MB corrupted registry value: two clicks, no crash, library heals
  to empty.
- **Pattern slot label.** The single-image slot is labelled "1" instead of
  the barely readable "all".

### Validation
- Suite 179 passed / 3 skipped; synthetic-event drag and off-canvas
  selection tests pass; halftone dialog stress test passes (real menu exec,
  corrupted settings). FORMAT_PATCH 19 and GPU paths untouched.
## [4.3.0.1] - 2026-06-11

Three bug fixes: objects dragged over the page edge stay visible, text
auto-fill actually fills large boxes, and the halftone pattern button no
longer crashes after a settings round-trip.

### Fixed
- **Dragging over the page edge.** Objects moved past the page boundary were
  clipped at the page pixmap edge, so they looked stuck at the canvas border.
  The editor canvas now renders an APRON strip around the page (15% of the
  larger page dimension, 8-30 mm): overhanging objects stay visible on the
  workspace, held by their full bounding box (rotation-aware). The page area
  itself is byte-identical to the plain render (in-page z-order, caching and
  effects untouched; only the apron frame is composited from a separate
  enlarged render of the overhanging objects); page (0,0) stays at scene
  (0,0), so hit-testing, snapping and overlays are unaffected.
- **Text auto-fill stopping short.** Auto-fill respected the silent legacy
  default cap of max_font_size = 70.555 mm (200 pt), so any box taller than
  ~95 mm stopped filling ("zastavi se a uz nevyplnuje"). The untouched
  default is now treated as "no limit" for auto_fill -- the text grows to
  fill the container -- while an explicitly set cap is still respected
  strictly. Fixed in both render paths (plain text and styled runs);
  verified: 120 mm box now fills to 89 mm, 200 mm to 148 mm, an explicit
  30 mm cap still yields 29.8 mm.
- **Halftone pattern button crash.** QSettings round-trips a ONE-element
  string list as a plain string (Windows registry and ini both do this).
  The pattern library reader then iterated the base64 string character by
  character and the library menu tried to build tens of thousands of
  actions from single characters -- hang / crash on the next click. This is
  why it only happened on a machine with exactly one pattern in the
  library. The reader re-wraps a bare string into a list and filters
  fragments; the writer guards the same way.

### Validation
- Suite 179 passed / 3 skipped; headless editor canvas cycle verified (the
  apron pixmap lands at the negative scene offset with page (0,0) fixed);
  apron render verified with overhanging text and shapes on both sides;
  auto-fill measured before/after; pattern-library reader exercised with a
  bare-string settings value. GPU paths and FORMAT_PATCH 19 untouched.
## [4.3.0] - 2026-06-11

PyPI release. Highlights of the 4.2.11.x series rolled into this version:
the long-shadow effect was rebuilt around a per-point ray model with three
independent mode selectors (blur: Solid / Constant / Linear / Custom; colour:
Solid / Custom; alpha: Solid / Fade / Custom), Photoshop-style multi-stop
gradient editors, fractional-radius variable blur, an exact GPU kernel for
the ray field, and a 2.5-5x faster CPU path. File format 4.2.19.

This release also ships a complete documentation refresh: a new layer-effects
reference (docs/reference/12-effects.md) covering all 13 effect types with the
full long-shadow mode and gradient-stop documentation, a new cookbook recipe
(effects-poster.md), a new runnable `examples/` directory (six end-to-end
scripts, all verified), layer-effects sections in README and QUICKSTART, the
effects serialization schema in the file-format guide, and updated doc
indexes. All new documentation code blocks are executed as part of validation.

The cleanup pass itself has no behaviour changes:

### Changed
- **Dead code removed:** four unreferenced internal functions
  (`_render_object_raw`, `_pdf_hex_string`, `_emit_rasterized`, `_from_qc`)
  and a shadowed duplicate definition of `_composite_with_blend` in the
  renderer (~6 KB; the later definition always won at import time, so
  behaviour is identical). One dead local in the GPU selftest.
- **28 unused imports removed** (conservative pass: top-level from-imports
  only; bare imports, package re-exports in `__init__.py` and local imports
  untouched). `List` added to the typing imports in `format/styles.py` (the
  gradient stop annotations referenced it lazily).
- **Library prints converted to `logging`:** the sub-document load failure in
  the renderer and the render-error path in the PyQt6 widget now go through
  `logging.getLogger(__name__).warning` instead of stdout.
- **Documentation paths neutralised:** installation examples no longer
  reference a machine-specific drive layout; internal first-person notes in
  comments and changelog entries reworded to neutral technical language.

### Validation
- Full suite 179 passed / 3 skipped; 120-combo long-shadow mode smoke clean;
  backward-halo, perpendicular-profile and CPU-vs-exact parity checks
  unchanged from .61. Headless import smoke of editor / viewer / CLI passes.
  `python -m build` produces a clean sdist + wheel (no caches, tests-only or
  launcher files inside the wheel); the wheel installs into a fresh venv and
  the core API works. FORMAT_PATCH 19 unchanged; GPU paths untouched, 3090
  selftest expectations unchanged.
## [4.2.11.61] - 2026-06-11

Long shadow: the side (perpendicular) blur is back at full width -- the .60
backward-halo fix had tightened it.

### Fixed
- **Side halo width.** The .60 radius driver composed the X and Y min passes
  into a 2D window minimum, so a perpendicular halo pixel inherited the
  SMALLEST t within the whole reach window -- typically from body pixels up
  to `reach` px upstream -- instead of the local body t right beside it. A
  smaller t means a smaller radius, so the side halo visibly tightened
  ("nebluruje do boku"). The propagation is now a SEQUENTIAL FILL that
  approximates "the t of the NEAREST shadow": the Y pass assigns the local
  body t to the perpendicular halo (exactly the .59 behaviour), and the X
  pass fills ONLY the cells the Y pass left empty -- the backward halo past
  the leading edge (kept from .60: constant / nonzero-start custom soften
  backward, linear stays root-sharp) and the corners, which read the
  already-filled perpendicular strips and therefore wrap roundly instead of
  notching.

### Validation
- Perpendicular profiles bit-match .59 again (x=200 max 66, x=350 max 102,
  x=500 max 111); the backward-halo block repro bit-matches .60 (constant
  ramps 18..153 across the leading edge, custom ramps, linear exactly sharp);
  circle: linear contact clean (crescent 0), constant smooth all around (max
  alpha step 8). Two-block outward halo 103; 30-config matrix OK (linear
  solid 2466 px); 120-combo smoke clean; CPU-vs-exact parity unchanged (mean
  0.3120, max 10/255, solid-alpha fast path bit-identical); suite 179 passed
  / 3 skipped. GPU paths untouched, 3090 selftest expectations unchanged
  incl. lsf_*. FORMAT_PATCH 19 unchanged.
## [4.2.11.60] - 2026-06-11

Long shadow: with a nonzero START blur (Constant mode, Custom stops with
blur(0) > 0) the shadow now softens BACKWARD over the silhouette's leading
boundary too -- the razor edge against the throw direction is gone.

### Fixed
- **Backward halo at the leading edge.** The local radius driver propagated
  the shadow's t only PERPENDICULAR to the throw, so pixels straight upstream
  of the leading edge always kept the no-shadow sentinel (radius 0) and the
  leading boundary stayed razor-sharp even in Constant mode, where the blur
  must spread in every direction. The propagation is now a separable 2D min
  over the blur reach (X then Y, symmetric doubling shifts): upstream pixels
  inherit the adjacent shadow's t ~ 0, which maps to radius = blur(0) --
  Constant / nonzero-start Custom soften backward, while Linear (blur(0) = 0)
  keeps the root razor-sharp by design. The rotated-frame crop box gets an
  upstream margin for the backward halo (it would have cut it into a hard
  diagonal otherwise).

### Validation
- Block repro: Constant 30 px now ramps smoothly across the leading edge
  (18..153, was a 0 -> 227 jump); Custom with start 20 px ramps; Linear stays
  exactly sharp. Circle: Constant grows a clean halo all around the leading
  rim (max alpha step 8 on the leading side), Linear keeps the .59 clean
  contact (crescent check still 0). Two-block outward halo, 30-config matrix,
  120-combo smoke, CPU-vs-exact parity (mean 0.31, max 10/255) and the suite
  (179 passed / 3 skipped) all pass. GPU paths untouched, 3090 selftest
  expectations unchanged incl. lsf_*.
## [4.2.11.59] - 2026-06-11

Long shadow: the hard edge / dark crescent at the start is gone.

### Fixed
- **Hard cut and dark crescent at the shadow start.** Two stacked causes,
  both rooted in the silhouette's faint leading AA fringe (alpha 2..40, just
  upstream of the source threshold):
  1. those pixels SELF-emit (their own ray at t = 0) but carried the
     no-upstream sentinel t = 1, so the leading rim got the MAXIMUM blur
     radius; the radius smooth spread it to the neighbourhood, whose gather
     then pulled the nearby body at near-full strength;
  2. pixels with no shadow in reach clipped the same sentinel to t = 1 as
     well, growing a spurious halo BACKWARD past the leading edge that the
     rotated-frame crop box cut into a hard straight diagonal (the visible
     razor edge in the reported screenshot).
  Fix: the leading AA fringe gets its true t = 0 at the source of everything
  (the youngest-distance field itself, so the blur driver, the colour lookup
  and the constant-alpha path are all consistent), and the no-shadow sentinel
  maps to radius 0 instead of max. Verified on the circle reproduction: the
  crescent (max alpha 243 outside the rim) and both tangent spikes are gone;
  the shadow emerges cleanly, sharp at the contact, softening along the throw.

### Validation
- Circle repro clean at the contact; two-block outward-halo repro and the
  single-block profiles bit-match .58; 30-config halo matrix OK; 120-combo
  mode smoke clean; CPU-vs-exact parity unchanged (mean 0.31, max 10/255);
  suite 179 passed / 3 skipped. GPU paths untouched (the fix is in the shared
  CPU-side t field), 3090 selftest expectations unchanged incl. lsf_*.
## [4.2.11.58] - 2026-06-11

Long shadow: the outward blur fixed. The blur ate the shadow inward but the
outer contour stayed razor-sharp for any shadow cast before the object's
global trailing edge -- which with text or any multi-part silhouette is most
of the shadow.

### Fixed
- **Outward halo everywhere.** The radius driver for pixels OUTSIDE the shadow
  (where the soft halo must grow) was anchored to the GLOBAL trailing object
  column: anything left of it got a zero outside radius. One glyph's shadow
  passing beside another therefore blurred inward only, with hard outer edges
  ("blur jen dovnitr, ven ostre okraje"). The driver is now LOCAL: each halo
  pixel takes the t of the nearby shadow it belongs to, propagated vertically
  out of the field over the blur reach (symmetric sliding min, doubling
  shifts), plus the row's own distance for the downstream end cap. The root
  flank stays sharp (propagated t ~ 0 near the contact); pixels with no shadow
  within reach gather empty windows at O(1) SAT cost, so nothing is wasted.
  Reproduced with a two-block silhouette (shadow of block 1 passing block 2:
  outward halo max was 0, now a smooth 0 -> 103 ramp) and verified the
  single-block profiles are bit-identical to .57.

### Validation
- 30-config halo matrix (5 directions x 3 blur modes x 2 alpha modes): outward
  halo present in every case; text-like multi-glyph silhouette blurs outward
  along the whole shadow with sharp glyph contacts. 120-combo mode smoke
  clean; suite 179 passed / 3 skipped. GPU paths untouched (the driver is
  CPU-side; the field kernel and the variable box blur are unchanged), 3090
  selftest expectations unchanged (incl. lsf_mean_diff / lsf_max_diff from
  .57).
## [4.2.11.57] - 2026-06-11

Long shadow: taper and cast removed; three clean mode selectors; the blur
fixed (no more radius rings, no value/distance mispairing); 2.5-5x faster on
CPU and a new exact GPU kernel for the ray field.

### Changed
- **Taper and cast are removed.** Legacy documents map: ls_mode
  'cast' renders as a linear-blur soft shadow, ls_taper is ignored (straight
  rays). With taper gone the per-point ray union is EXACTLY per-row in the
  rotated frame, which unlocked the speed and the GPU kernel below.
- **Three independent mode selectors** (UI + format):
  - BLUR mode: Solid (sharp, hides the rest) | Constant (amount in UI) |
    Linear (END amount in UI) | Custom (blur gradient stops);
  - COLOR mode: Solid (colour button) | Custom (colour gradient stops);
  - ALPHA mode: Solid | Fade | Custom (alpha gradient stops); the ls_fade
    flag is gone from the UI (still written for legacy readers).
  All gradient bars come PRE-FILLED with sensible defaults (never empty); the
  x button resets to the default stops. Only the controls relevant to the
  selected mode are visible. New serialized fields ls_alpha_mode /
  ls_color_mode (FORMAT_PATCH 18 -> 19); empty = derive from legacy fields, so
  old documents render unchanged.

### Fixed
- **Blur quality.** Two real defects fixed:
  - the variable blur radius map was quantised to integers, which drew faint
    RINGS (radius steps) across the soft skirt; the radius is now FRACTIONAL --
    two integer-radius variable box blurs lerped per pixel -- which is
    mathematically continuous across radius transitions, identically on the
    CPU and GPU paths;
  - the radius driver went through an 8-bit roundtrip (uint8 de-stair smooth),
    quantising t to 256 levels; it now uses a small float32 separable Gaussian.
- **Field correctness.** The CPU youngest-ray term paired the value of the
  STRONGEST upstream emitter with the distance of the NEAREST one, so the
  shadow behind a semi-transparent emitter jumped to the strength of a distant
  opaque one. It now carries the actual nearest emitter's value (a true
  single-ray contribution, never an overestimate). Measured against the exact
  max-convolution: max error dropped 84 -> 10 (of 255), mean 0.62 -> 0.31, and
  the dominant regime is exact.

### Performance / GPU
- CPU: constant-alpha fast path (the exact field is ONE doubling smear, no
  segment loop), allocation-free segment hot loop, monotone-aware segment
  count, tight crop before the heavy ops. 1600x1200 page, L = 500 px: 2.0-2.5 s
  -> 0.45-0.97 s depending on mode (2.5-5x).
- GPU: new `gpu_long_shadow_field` kernel computes the EXACT per-row
  max-convolution (every emitter, LINEAR-filtered alpha-gradient LUT, no
  segment quantisation) in a single pass; the variable box blur already runs
  on the GPU, so with GPU enabled the whole heavy pipeline is on the card and
  the CPU only rotates. CPU remains the fallback (approximate, documented).
  New selftest entries lsf_mean_diff / lsf_max_diff compare the kernel against
  a brute-force numpy reference (expected: mean well under 0.05, max under
  1.0 -- the LUT linear filtering).

### Validation
- 120-combo smoke (5 directions x 4 blur modes x 2 colour modes x 3 alpha
  modes) clean; suite 179 passed / 3 skipped; gradient round-trip serialization
  OK; solid blur renders with zero soft pixels beyond edge AA; the sharp
  contact and growing blur verified visually. GUI smoke-tested headless only.
## [4.2.11.56] - 2026-06-10

Long shadow: the PER-POINT RAY model + Photoshop-style
multi-stop COLOUR / ALPHA / BLUR gradients with a stops editor in the UI.

### Changed
- **Per-point rays.** Every silhouette point (any source: path, PNG with
  alpha, text) emits a ray of length `ls_length` along the throw; the shadow is
  the max-union of all rays. The source point's alpha scales its whole ray.
  Along each ray, everything is a multi-stop gradient over the ray's own
  progression t: colour c(t), alpha a(t), blur radius r(t); TAPER makes each
  ray straight, widening or narrowing -- so with taper the widening starts at
  each EMITTING point (the leading edge included), which is what the previous
  trailing-boundary model got wrong at the front. Narrowing erodes rays along
  their travel, so thin strokes naturally die off toward the tip.
  Implementation: rotated frame (throw = +X), a single trailing-window sliding
  max + N cheap shifts realise the max-convolution over distance segments,
  vertical morphological dilation / erosion per segment realises taper, and an
  exact continuous youngest-ray term keeps the dominant regime perfectly
  smooth (skipped when narrowing, where erosion must be able to remove
  coverage). All float until the final compose.
- **Multi-stop gradients (format + UI).** New serialized fields on the effect:
  `ls_grad_colors` [[t, r, g, b], ...], `ls_grad_alphas` [[t, a01], ...],
  `ls_grad_blurs` [[t, mm], ...]. Empty lists = legacy behaviour (fade flag,
  color -> color2, blur mode/gamma), so old documents render as before;
  non-empty stops override the legacy controls. FORMAT_PATCH 17 -> 18 (new
  serialized fields). The Long Shadow effect page gets three Photoshop-style
  gradient bars (drag a stop to move, double-click to add / edit -- colour
  dialog or numeric value, right-click to delete, x to clear back to legacy).
  Cast stays physical (light-driven) and ignores the stylistic gradients.

### Validation
- Front behaviour: with taper > 1 the widening cone starts at the leading
  corner and runs along the object's flank; taper < 1 narrows to the tip;
  taper 1 is a straight column. Multi-stop colour, non-monotone alpha (the
  union over a thick body correctly lets older interior rays dominate where
  they should) and mid-peaking blur stops all verified end-to-end through the
  dispatch. Effect serialization round-trips; legacy dicts load with empty
  stops. Cast bit-identity checks still hold. 180-combo smoke clean; suite
  179 passed / 3 skipped; 1600x1200 page with L = 500 px renders in ~2-2.5 s.
- GPU pipeline untouched (the model is CPU numpy; halftone / blur / CA GPU
  paths unchanged). 3090 selftest expectations unchanged.
## [4.2.11.55] - 2026-06-10

Long shadow: ONE model. The scaled-copy loft is deleted; everything (including
taper) renders through the rotated-frame column model where every property is a
function of the progression t along the throw.

### Changed
- **The loft path is gone.** Its design could never deliver a sharp start: the
  sweep merged its discrete scaled copies by pre-blurring the silhouette, so the
  coverage was soft from the contact by construction, and every patch on top of
  that (distance clamps, contact bands, protection gates) traded one artifact
  for another. The column model needs none of it.
- **The unified column model.** The silhouette is rotated so the throw is +X
  and extruded by a float max-smear of the ANTI-ALIASED alpha (the flank carries
  the silhouette's own AA). Every pixel has an exact progression t, and all
  properties are functions of it:
  - alpha a(t): fade is a 2-stop alpha gradient 1 -> 0; the colour-gradient
    alphas are a 2-stop a0 -> a1;
  - colour c(t): the 2-stop colour gradient, applied in page frame;
  - blur r(t): 0 at the contact, growing linearly (or by the gamma curve) --
    sharp at the root where the alpha originates, progressively blurring;
  - cross-section s(t): TAPER widens/narrows THE END. The scale driver is the
    per-column progression measured from the last object column, constant
    across the perpendicular: s = 1 over the whole object (the silhouette is
    never stretched, the contact never moves) and the cross-section changes
    only past the object, reaching `taper` at the tip. The height field t is
    resampled together with the coverage so the widened/narrowed flank keeps
    its true t for fade, colour and blur.
  The far end terminates in the (scaled) silhouette shape itself -- no stroke,
  no outline; with fade it dissolves.
- The whole pipeline stays in float until the final compose (no 8-bit
  quantisation stair-steps / checkerboarding), and the back-rotation bleed is
  trimmed by a validity mask.
- Cast remains standalone (light elevation + disk + height only) per .54.

### Validation
- Sharp contact verified at the corner for taper 0.5 / 1.0 / 1.6 (full-opacity
  step at the casting edge, blur growing downstream). Detailed text silhouettes
  render clean at all tapers with no tearing or detached patches. 180-combo
  smoke clean. Suite 179 passed / 3 skipped.
- The GPU loft-sweep primitive in gpu.py is now unused by the renderer but kept
  (the GL selftest still exercises it; 3090 selftest expectations unchanged).
  Document format unchanged (FORMAT_PATCH 17).

### Next (agreed direction)
- Photoshop-style gradient controls replacing fade: multi-stop COLOUR, ALPHA
  and BLUR gradients over t. The model already consumes c(t), a(t), r(t), so
  this is format fields (stop lists) + the effects-dialog gradient editor.
## [4.2.11.54] - 2026-06-10

Long shadow rework: tapered shadows no longer blur their whole start, and cast
is now a fully standalone physical mode that soft-mode settings cannot touch.

### Fixed
- **Tapered long shadows (taper != 1) no longer blur everything.** The loft
  sweep merges its discrete steps by pre-blurring the silhouette (~the step
  spacing, easily several px in soft mode), so the coverage itself was soft from
  the very contact; on top of that the blur-radius field was driven by a
  diffusion average that is nonzero right next to the object. Together the whole
  start (and with it effectively the whole shadow) read as blurred. Now:
  - the blur radius is clamped by the true geometric distance from the object
    silhouette (EDT), in the body and in the outside halo alike, so blur grows
    physically with distance and is exactly 0 at the contact;
  - a sharp CONTACT BAND (the unblurred silhouette extruded along the throw in
    page frame) replaces the pre-blurred coverage near the object, crossfaded
    out by distance, so the start emerges crisp at any taper;
  - tmap (nearest covering throw distance) is now honest: it is assigned at the
    50% contour of each swept copy instead of the >5% blur skirt, on both the
    CPU and GPU sweep (same threshold passed to both), so shadow passing close
    over the silhouette from far upstream is correctly recognised and protected
    from the band replace -- previously the skirt-contaminated tmap caused a
    light seam above the silhouette. Skirt pixels never sharply covered get a
    geometric distance estimate for fade / colour-gradient / blur instead of a
    bogus one.
- **Cast is standalone: soft settings no longer affect it.** Cast was
  implemented as a parameterisation of the soft path and leaked two soft inputs:
  the soft `size` acted as the penumbra whenever the light disk size was 0, and
  a non-1 `taper` silently rerouted cast through the tapered loft. Cast is now
  driven ONLY by the light elevation, the light disk size and the object height:
  a zero light disk is a point light (perfectly sharp shadow, only edge AA),
  taper is ignored, and fade / blur-curve / gamma do not apply.
- **Straight (taper 1) start polish.** The shadow column is now extruded from
  the anti-aliased silhouette itself instead of a binarised mask, so the flank
  carries the silhouette's own AA and meets the object without a light seam or
  dithered stubs; the sub-pixel bleed of the back-rotation is trimmed with a
  validity mask.

### Validation
- Verified per mode: cast with light size 0 renders with zero soft pixels beyond
  edge AA and is bit-identical for any soft `size`; cast with taper 1.6 is
  bit-identical to taper 1.0; penumbra area grows with the light disk. Tapered
  starts (0.5 / 1.4 / 1.5, solid and soft) emerge sharp with blur growing
  downstream; no seam above the silhouette; detailed text-like silhouettes keep
  sharp starts without tearing. 180-combo smoke (5 directions x 3 tapers x
  solid/soft/cast x fade x colour-gradient) all clean. Suite 179 passed /
  3 skipped.
- The GPU loft sweep primitive is unchanged (the honest-tmap threshold is a
  parameter passed identically to CPU and GPU); the GL selftest is
  self-contained and its 3090 expectations are unchanged. Document format
  unchanged (FORMAT_PATCH 17).
## [4.2.11.53] - 2026-06-10

Long shadow: the start (the casting contact with the object) is now sharp.

### Fixed
- **Soft long shadows no longer blur their start.** In soft / cast / tapered
  modes the shadow was already feathered right where it leaves the object, when
  the contact should be the sharpest part and the blur should grow with distance.
  Three causes, all fixed:
  - The silhouette got an unconditional 0.6 px pre-blur before the projection
    rotate. For an axis-aligned throw (0/90/180/270) the rotate is lossless, so
    that pre-blur is now skipped and the contact stays crisp; it is kept only for
    arbitrary angles, where it actually helps the rotate.
  - The straight (matte) path drove the side / leading halo blur from a
    per-column *average* throw distance, which was nonzero at the contact and
    bloomed the start. The blur radius is now the true per-pixel throw distance
    (in-shadow) anchored to the casting-edge column (halo), which is exactly 0 at
    the contact, and the exact casting line is re-zeroed after a gentle de-stair
    smooth, so the start is sharp and the blur ramps up with distance.
  - The tapered (loft) path pre-blurred the silhouette to merge its sweep steps,
    softening the contact. The swept body is now unioned with the original sharp
    silhouette so the emerging edge is crisp, and inside the covered shadow the
    blur radius is clamped to the true throw distance so the diffusion can't
    bloom the contact.

### Validation
- Measured: the soft side edge at the contact went from ~3 px of feather to 0 px
  (sharp), while the distance-growing blur is preserved (≈7 px at 1/8 length,
  ≈17 px at 1/2). 180-combo smoke (5 directions x 3 tapers x solid/soft/cast x
  fade x colour-gradient) all render cleanly; detailed silhouettes (text-like
  strokes) keep sharp starts with no tearing. Suite 179 passed / 3 skipped.
- The variable-blur core and the GPU loft sweep are unchanged, so GPU parity is
  untouched. Document format unchanged (FORMAT_PATCH 17).
## [4.2.11.52] - 2026-06-10

WYSIWYG halftone: the dot pattern no longer changes with canvas zoom. Plus a
one-click local-deploy-and-run launcher.

### Fixed
- **Halftone dots are now stable across zoom (WYSIWYG).** The dot lattice
  (which cells are on, their size bucket) is decided by sampling the source over
  a small per-cell window. The canvas renders at an adaptive DPI that drops when
  you zoom out, which shrank that window to a few pixels and made near-threshold
  dots flicker in and out from one zoom level to the next, so the dot count kept
  changing. The editor now pins a minimum render DPI whenever the page carries a
  halftone effect: the lattice is computed at a resolution where the cell
  spacing is at least 24 px (where the count has converged) and the resulting
  pixmap is simply scaled onto the scene. Measured: per-channel dot counts are
  now identical at every zoom from 72 to 576 DPI, where before they drifted by
  several percent. The densest dot on the page (smallest ht_dot) sets the floor,
  which is capped at 600 DPI and re-clamped to the page memory cap.

### Added
- **edof-deploy-run.bat** next to the other launchers: installs edof locally
  from the package files (no PyPI) and launches the editor in one step, for
  quickly testing a freshly unzipped build.

### Notes
- The halftone renderer itself is unchanged, so CPU/GPU parity is untouched
  (re-confirmed: real-pattern 18-case matrix all 0.00000/0.00). Suite 179 passed
  / 3 skipped. Document format unchanged (FORMAT_PATCH 17).
## [4.2.11.51] - 2026-06-10

Two real-world fixes surfaced while validating real-world halftone patterns:
the pattern library submenu crashed on open, and opaque (white-on-black)
pattern PNGs stamped as solid squares instead of their shape.

### Fixed
- **Pattern library submenu no longer crashes.** Opening a halftone thumbnail
  menu with a non-empty pattern library raised
  `'QMenu' object has no attribute 'setIconSize'` (QMenu has no such method in
  Qt6). The 28px library icon size is now set via a QProxyStyle overriding
  PM_SmallIconSize, parented to the submenu. The "Load image" and "Clear"
  paths were unaffected; only the populated "From library" submenu hit it.
- **Opaque white-on-black patterns now keep their shape.** A custom pattern
  PNG exported as a white silhouette on an opaque black background (the most
  natural export) has a flat, fully-opaque alpha channel. The stencil decoder
  only fell back to luminance when alpha was fully *transparent*, so a flat
  *opaque* alpha was taken as the stencil and every dot became a solid square,
  losing the heart / dragon / peace shape entirely. The decoder now falls back
  to luminance whenever the alpha carries no shape (negligible spread), which
  covers both the transparent and the opaque-flat cases. Genuine alpha-shaped
  patterns (transparent background, shape in alpha) are unchanged.

### Validation
- Emulated-stamp CPU-vs-GPU parity re-confirmed on three real-world patterns
  (heart, dragon, peace), 18-case matrix, all 0.00000 mean / 0.00 max: cmyk and
  rgb, single and per-channel, random rotation, decentralization 40 + hex, and
  transparency render mode. The stencil fix lives in the shared decode path, so
  both CPU and GPU consume the identical stencil and parity is preserved.
- Suite 179 passed / 3 skipped. Document format unchanged (FORMAT_PATCH 17).

### Notes
- 3090 GL selftest still expected halftone 0/0; the GL stamp shader is unchanged.
## [4.2.11.50] - 2026-06-10

GPU halftone now covers ALL cases: custom patterns, random rotation,
decentralization. This completes the GPU effects roadmap.

### Changed
- **The GPU halftone fast path no longer excludes anything.** Previously it
  handled only the common case (built-in shapes, no random dot rotation, no
  decentralization); the remaining cases ran the CPU loop. Now:
  - **Custom pattern images** flow through the same size-bucket atlas as the
    built-in shapes -- they were only excluded by the eligibility gate, the
    stamping path is identical.
  - **Random dot rotation** extends the atlas to K x 8 rotation-variant tiles;
    the per-cell variant is picked by the exact same _ht_rot_idx hash the CPU
    loop uses, so dot-for-dot identical output. Rotation variants are
    expand=True, so the tile pitch is the largest variant, not the base size.
  - **Decentralization** is a constant per-channel offset, applied to the
    vectorised grid exactly as in the CPU loop.
  - A 256MB atlas memory guard falls back to CPU for absurd dot sizes;
    the per-call CPU fallback stays for any GPU failure, as always.

### Validation
- Emulated-stamp parity matrix, all 0.00000 mean / 0.00 max vs the CPU loop:
  random rotation (circle; diamond+hex grid), decentralization 40,
  custom pattern, pattern+randrot, pattern+randrot+decentralization+hex,
  and randrot in transparency render mode. Suite 179 passed / 3 skipped.
- The GL stamp shader itself is unchanged (it just receives more tiles), and
  was previously confirmed exact on RTX 3090 (selftest halftone 0/0).

### Notes
- Document format unchanged (FORMAT_PATCH still 17).
## [4.2.11.49] - 2026-06-10

The text ribbon is present from startup (disabled until editing).

### Changed
- **The ribbon no longer pops in on the first text edit** -- in basic mode it
  used to appear only once a textbox edit started, shifting the page at that
  moment. A disabled skeleton ribbon is now shown as soon as a document opens
  (any mode), reserving the top band up front; starting a text edit merely
  enables the controls in place, so the page never moves. Opening another
  document rebuilds the skeleton.
- Internals: ribbon construction was extracted into _build_text_ribbon(); the
  skeleton binds to a hidden dummy editor whose controls can never fire
  (everything is disabled until a real session rebuilds the contents).

### Notes
- Document format unchanged (FORMAT_PATCH still 17).
## [4.2.11.48] - 2026-06-10

Copy/paste keeps source formatting; header/footer auto-shrink & auto-fill.

### Fixed
- **Ctrl+A / Ctrl+C in a header or footer, Ctrl+V elsewhere: the text now
  really keeps its attributes.** Rich copy/paste existed, but attributes the
  runs INHERIT from the box's base style (typical for bands, which carry their
  own font/size in the band style) round-tripped as "inherit" -- pasting into a
  box with a different base style visibly changed the text. The clipboard now
  resolves the identity attributes (font family, size, colour) from the source
  box style at copy time, Word-style "keep source formatting", so the pasted
  text looks like what was copied, in any target box.

### Added
- **Auto-shrink and auto-fill for headers and footers**, in the page-setup
  panel (one pair per band). The flags live in the persisted band style, so
  pagination applies them on every page; when "different odd & even pages" is
  on they apply to both template sets. Seeding preserves the band's existing
  style attributes (font size etc.) when the flags are first toggled.

### Notes
- Document format unchanged (FORMAT_PATCH still 17).
## [4.2.11.47] - 2026-06-10

The text ribbon is persistent -- no more page jumping, in any mode.

### Fixed
- **The page jumped because the text toolbar was destroyed and recreated on
  every editing cycle** -- every sticky commit in document mode, every switch
  between body and header/footer, every edit in basic mode. Each teardown
  released the reserved top band and each rebuild claimed it again, shifting
  the page. The ribbon is now a PERSISTENT widget: created once per document,
  its contents are rebuilt in place for each session (so buttons bind to the
  current editor), and ending a session merely disables the controls -- the
  ribbon stays visible and the reserved band never moves. It is hidden only
  when the document is replaced. Applies to document mode AND basic mode.
- The one-row/two-row decision now includes a fixed allowance for the optional
  per-session buttons (page-number menu, Apply/Cancel), so the ribbon height is
  identical for every session and cannot flip between edits.
- Verified across the full lifecycle (open body edit, commit, sticky re-enter,
  double-click switch to header, header commit; and basic-mode box-to-box):
  reserved band constant, ribbon always visible, scroll position unchanged.

### Notes
- Document format unchanged (FORMAT_PATCH still 17).
## [4.2.11.46] - 2026-06-10

Header/footer: persistent band style, first page number, odd/even pages.
FORMAT change: 1.0.17 (new DocumentBody fields; older files load fine).

### Added
- **Band style persists across pages.** Setting e.g. vertical align = middle
  while editing a header/footer now survives repagination and applies on every
  page: the band's box-level style is stored on the document
  (header_style/footer_style) and re-applied by pagination, the same way the
  text template is.
- **First page number.** Page setup gained "First page number"; {page_number}
  starts there and {page_count} shows the last page's number (start 5 over 8
  pages renders "Strana 5 z 12" ... "Strana 12 z 12").
- **Different odd & even pages (optional).** When enabled in page setup, pages
  with an EVEN page number use their own header/footer template + style.
  Double-clicking a band edits the template of that page's parity, so you edit
  even pages' chrome on an even page. Odd template stays untouched.

### Fixed
- **The page no longer jumps around while editing headers/footers.** Two causes:
  switching editors (body <-> band) flipped the reserved toolbar margin off and
  back on, shifting the whole page; and the post-commit repagination reset the
  scroll position. The margin now stays put during a direct switch and the
  scroll position is preserved across the commit.

### Format
- FORMAT_PATCH 16 -> 17: DocumentBody gains header_style, footer_style,
  page_number_start, hf_odd_even, header_runs_even, footer_runs_even,
  header_style_even, footer_style_even. All have backward-compatible defaults;
  files saved by older versions load unchanged. Verified save/load roundtrip.
## [4.2.11.45] - 2026-06-10

Double-click into a header/footer now works while the body is being edited.

### Fixed
- **The real reason header/footer editing "did not work": in document mode the
  body sits in near-permanent sticky inline edit, and the double-click handler
  ignored ALL double-clicks while any inline editor was open.** So with the
  body editor active (i.e. almost always), double-clicking a header/footer band
  did nothing -- which matched exactly what was reported, and is why the
  band-position fix alone (4.2.11.44, also real) was not enough. A double-click
  that lands on a header/footer while an inline session is active now commits
  that session (nothing typed is lost), suppresses the sticky body re-entry,
  and switches the editor into the band. Verified with real event dispatch in
  the sticky state: body editing -> double-click header -> editor switches
  (role header), typed template persists ("HLAVICKA {page_number}" -> page
  shows "HLAVICKA 1"), and the body keeps the text typed before the switch.
- The header/footer write-back path also resets the sticky-suppression flag it
  previously could leak on its early return.

### Notes
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.44] - 2026-06-10

Header/footer guide band now matches the real box (double-click works).

### Fixed
- **The header band drew at the page edge but the box lived inside the margin**,
  so the dashed band you saw at the very top did not line up with the box the
  double-click targets -- clicking the visible band hit nothing and editing
  seemed dead. The guide band is now drawn at the box's actual geometry from
  pagination (header sits just below the top margin, footer just above the
  bottom margin), so the band you see IS the click target. Verified: a real
  double-click on the band opens inline editing with the page-number menu.

### Notes
- When a header/footer is enabled the body text area shifts to make room (the
  body starts below the header band), so they do not overlap.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.43] - 2026-06-10

Header/footer are now visible and discoverable (editing works again).

### Fixed
- **You could not find where to edit a header/footer.** After 4.2.11.42 made
  them non-selectable as objects (correct), an enabled but empty band had no
  text, no fill and no outline -- nothing on screen to aim a double-click at, so
  it looked like editing was broken. Enabled header/footer bands now draw a
  faint tinted rectangle with a dashed outline, and while empty show a
  "Header / Footer (double-click to edit)" hint. The drawn band is exactly the
  region the double-click hit-test targets, so double-clicking it opens inline
  editing (where the #▾ page-number menu lives). The editing path itself was
  intact; this restores the visual affordance. Single-click / hover still ignore
  them (no handles), per 4.2.11.42.

### Notes
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.42] - 2026-06-10

Header/footer are no longer free objects; Fit page fixed properly.

### Fixed
- **Header and footer boxes no longer behave like draggable objects.** They are
  geometry-locked document furniture (size/position driven by page setup), so
  showing a selection box with resize handles on them was wrong and ugly.
  Single-click and hover now skip them entirely (no selection, no handles, no
  edge dragging); they are still editable by DOUBLE-CLICK, which is the only
  path that picks them. Even if one is selected via the Objects list, no
  transform overlay is drawn. The document body is treated the same way.
- **Fit Page now actually places the page below the inline toolbar.** The
  previous attempt reserved height in the zoom math, but the scene rect is
  exactly the page so centerOn had no scroll room and the page stayed centered
  under the ribbon. The toolbar band is now reserved with setViewportMargins
  (and the toolbar reparented to the view frame so it sits in that band), so the
  scrollable area genuinely starts below it. Verified: page top lands well below
  the toolbar bottom; the margin is released when the editor closes.

### Notes
- The page-number insert menu (#▾) appears in the inline toolbar while editing a
  header or footer; double-click the band to start. Verified all six variants
  present.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.41] - 2026-06-10

Document mode: page setup panel, editable header/footer, page numbering UI.

### Added
- **Page setup properties for the document body.** Selecting the body (which
  has no meaningful per-object properties) now shows a page-setup panel instead:
  page size (presets A4/A5/A3/Letter portrait+landscape, or custom W/H),
  margins (top/right/bottom/left), and header/footer enable + height. Changes
  apply to the whole document and repaginate live.
- **Editable header & footer, directly on the page.** Double-click the
  header/footer band to edit it like a normal text box. The text is shared
  across all pages: edits are written back to the document's header/footer
  template and every page updates. (The engine already placed and resolved
  these boxes; this wires up authoring.) When editing a header/footer the
  editor shows the raw template, so you see and edit the actual {page_number}
  token rather than a resolved value.
- **Page-number insert menu** in the inline toolbar (header/footer only): a #▾
  button offering Page number, "Page X of Y", Total pages, and left / center /
  right-aligned number variants. Inserts the matching template token at the
  caret; the paginator resolves it per page.

### Notes
- All built on existing engine support (DocumentBody header/footer runs,
  DocumentHeaderBox/FooterBox pagination, {page_number}/{page_count} template
  resolution) -- no format change (FORMAT_PATCH still 16). Verified headless:
  body shows page setup, enabling header/footer creates the boxes, multi-page
  numbering resolves ("Strana 3 z 8"), and on-page header edits persist to the
  template and re-resolve across pages. Suite 179/3.
## [4.2.11.40] - 2026-06-10

Fit-page accounts for the inline text toolbar (regression from 4.2.11.39).

### Fixed
- After the toolbar became a 2-row ribbon in 4.2.11.39, Fit Page (Ctrl+0)
  still measured the full viewport height, so the page was tucked partly under
  the toolbar in both modes. Fit now reserves the visible inline toolbar's
  height and centres the page in the area below it. The toolbar reposition on
  window resize also keeps its current height (1 or 2 rows) instead of forcing
  40px.

### Notes
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.39] - 2026-06-10

Inline text toolbar: spinboxes no longer fall off the edge in design mode.

### Fixed
- **The size / line-spacing / letter-spacing spinboxes were missing from the
  inline text toolbar in normal (design) mode.** The toolbar is a fixed-width
  single row pinned to the top of the viewport; its full content needs more
  width than was available, so trailing controls were silently pushed past the
  right edge. Document mode has two fewer buttons (no Apply/Cancel on the
  permanent body), which is why the spinboxes still squeezed in there but
  disappeared in design mode.
- The toolbar now measures its content against the viewport width and packs
  everything into ONE row when it fits, or wraps into TWO rows (format + font
  controls on top; alignment, lists, vertical align, Apply/Cancel below) when
  it does not. Verified in both modes at wide and narrow window widths: all
  three spinboxes visible and inside the toolbar bounds.

### Notes
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.38] - 2026-06-10

Glyph mask cache: ~7x faster text drawing, bit-identical, self-verifying.

### Performance
- **Text drawing now reuses cached FreeType glyph masks.** PIL's draw.text for
  our plain case boils down to: rasterise the glyph (getmask2 with the
  fractional position) and blend it (draw_bitmap). Only the rasterisation is
  expensive and it is a pure function of (font, char, fontmode, ink, fractional
  offset) -- so it is now cached, and the final blend still goes through PIL's
  own draw_bitmap. The output is therefore bit-identical BY CONSTRUCTION, not
  just visually similar.
- **Self-verifying:** on first use a probe string is rendered char by char both
  ways (integer + fractional positions; transparent, opaque and
  semi-transparent backgrounds) and the fast path enables itself ONLY if every
  byte matches. On a Pillow version with different text internals it silently
  falls back to plain draw.text -- the rendering can never change.
- Numbers: a full A4 text page 677 -> 396 ms cold (chars repeat within the
  page) and ~104 ms with a warm cache; a document-mode keystroke re-render
  drops from ~0.7 s to ~0.1 s. Verified bit-identical against 4.2.11.37 on
  plain text, auto-shrink + center, glyph-scale deform, and rich multi-run
  text (colours, bold/italic, underline, strikethrough). The glyph cache is
  cleared together with the font cache.

### Notes
- This closes the "editor speed vs pixel-perfect WYSIWYG" question from the
  ROADMAP: no trade-off needed, the middle path delivers both.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.37] - 2026-06-10

Ctrl+Enter (hard page break) crash in document mode fixed.

### Fixed
- **The whole app could crash on Ctrl+Enter in document mode.** Reproduced: in
  PyQt6 any exception escaping a slot or key handler aborts the entire process
  (qFatal), and the editor-rebuild dance around a hard page break (cancel old
  inline widget, repaginate, hop, start new inline widget) had several escape
  routes -- most notably a stale reference calling into the old editor widget
  after its C++ side was destroyed (RuntimeError on a deleted QTimer followed by
  a segfault in the reproduction).
  Fixes, layered: (1) the whole hard-page-break slot now runs inside a guard
  that logs the traceback (debug log + console) and leaves the editor alive
  instead of killing the app; (2) the text editor's keyPressEvent has the same
  top-level guard; (3) the editor's _invalidate / cursor-blink slots tolerate a
  destroyed underlying widget (no more RuntimeError -> abort); (4)
  _cancel_inline stops the widget's render-debounce and blink timers before the
  deferred deletion so a queued timeout cannot land on a half-destroyed widget.
  The previously-crashing scenario (type until overflow, Ctrl+Enter mid-text,
  hop, second Ctrl+Enter, plus deliberate stale-reference abuse) now completes
  cleanly: 4 pages, editor alive.

### Notes
- If a page break ever fails now, it logs instead of crashing -- check the
  debug log via Help if Ctrl+Enter seems to do nothing.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.36] - 2026-06-10

Text drawing: per-run context hoisted out of the per-character loop.

### Performance
- render_layout_onto resolved the run style, looked up the font and unpacked
  the colour for EVERY character (thousands of times on a document page). All
  of that only depends on the run, so it is now computed once per run and
  reused; the draw calls themselves are unchanged. Output verified
  bit-identical; a full A4 text page is ~7% faster (~725 -> ~677 ms). The
  remaining cost is FreeType glyph rasterisation itself.

### Notes
- An exact glyph-raster cache was investigated and PROVEN infeasible: PIL
  renders glyphs subpixel-positioned (float vs floored coordinates differ) and
  mask-paste compositing is bit-exact on opaque backgrounds but NOT on
  transparent ones. So a glyph cache can be visually identical but not
  bit-identical; it is NOT enabled anywhere. See ROADMAP for the open decision
  (editor-only glyph cache vs strict WYSIWYG parity).
- GPU parity fully confirmed on hardware (RTX 3090) as of 4.2.11.35: blur
  0.35/4 (expected), CA 0/0, loft 0.001/1.7 + tmap rim pixels, halftone 0/0,
  variable box blur 0/0.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.35] - 2026-06-10

Halftone GPU parity: the max-255 outliers are gone (exact bucket parity).

### Fixed
- **Halftone GPU self-test showed mean ~0.02 but max 255**: a few dots came out
  one size bucket different. Root cause was NOT the GPU: the instance builder
  sampled cell values via a cumsum (sequential float32 summation) while the CPU
  loop uses window .sum() (pairwise float32). The different rounding order
  shifted val by ~1e-6, which at an exact .5 boundary flipped
  round(val * 19) into the neighbouring size bucket - a whole dot one step
  bigger/smaller (hence max 255). The GPU instance builder now samples cell
  values with the CPU's exact expressions per cell (identical summation order),
  so buckets match bit for bit. Verified: all shape/mode/grid/render-mode
  combinations now diff 0.00000 / 0.00, including transparency mode.
- The stamping shader also lost its last numeric transforms: the stencil atlas
  uploads as float32 (no more u8 quantisation) and sampling is texelFetch with
  integer coordinates derived from gl_FragCoord (no interpolated UVs), so the
  fragment path is fetch * ad + MAX blend, nothing else.

### Notes
- Expected on-hardware self-test after this: halftone 0 / 0 (like the variable
  box blur). Loft tmap max ~0.2 on the 0..1 scale remains expected: a handful of
  rim pixels at the coverage threshold pick a neighbouring sweep step due to
  bilinear rounding; the radius smoothing absorbs it (mean 0).
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.34] - 2026-06-10

GPU self-test dialog now reports ALL parity sections.

### Fixed
- **The GPU self-test dialog only displayed the Gaussian blur and chromatic
  aberration results**, silently discarding the loft-sweep, halftone and
  variable-blur parity metrics added in 4.2.11.28-.32 (the engine computed
  them; the dialog hardcoded two sections). The report is now built from
  everything the engine returns: blur, CA, loft coverage, loft distance map
  (0..1 scale), halftone stamping, variable box blur, any per-section errors
  (e.g. loft section FAILED: ...), and any future *_diff metric is listed
  generically so the dialog cannot go stale again. Expected-noise notes are
  shown where a tiny diff is normal (weight-summation order; sequential cumsum
  vs parallel scan).

### Notes
- Engine self-test itself unchanged. Document format unchanged (FORMAT_PATCH 16).
## [4.2.11.33] - 2026-06-10

Shortcuts fixed (Ctrl+S et al.) + document mode / textboxes much faster.

### Fixed
- **Keyboard shortcuts work again.** Ctrl+S, Ctrl+N, Ctrl+O, Ctrl+Z, Ctrl+Y,
  Ctrl+D, Ctrl+=, Ctrl+-, Ctrl+0 were registered on BOTH the toolbar action and
  the menu action. Qt treats a key bound to two actions as ambiguous and fires
  NEITHER, so those shortcuts silently did nothing. There is now a single
  window-wide shortcut registry: menu actions register first (menus display the
  key natively), toolbar actions show the key in the tooltip and register only
  keys the menu did not claim. Verified: every shortcut registered exactly once.

### Performance
- **Text layout measurement cache.** Word width (getbbox) and font ascender
  measurements are pure functions of (font, text) but were recomputed for every
  word on every layout pass: every keystroke in the inline editor, every
  fitting-scale probe (auto-shrink runs a binary search of full layouts), every
  repagination in document mode, every canvas textbox render. They are now
  cached centrally (strong font refs pin ids; caches cleared with the font
  cache). A full A4 page of text renders ~1476ms -> ~830ms, and the layout part
  of a keystroke in document mode drops to near zero. Output verified
  bit-identical (plain text, auto-shrink + center, glyph-scale deform).

### Notes
- Vector rasterization profiled: ~1.8ms/shape, ~117ms for a full-page ellipse at
  300 DPI. PIL is fast enough; GPU rasterization is deprioritized (same verdict
  as image resize). Remaining typing cost in document mode is the PIL glyph
  DRAW of the full page (~0.8s); a draw-side cache is the next candidate but
  needs care to keep pixel-perfect parity, so it ships separately.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.32] - 2026-06-10

Long-shadow variable blur: big CPU speedup (bit-identical) + full GPU path.

### Performance
- **CPU: the variable box blur gather now uses flat take() indices** instead of
  2D fancy indexing. Bit-identical output (verified render-vs-render against
  4.2.11.31), about 1.9x faster on the gather; a large straight shadow went
  ~4.9s -> ~1.8s end to end on CPU. Both the straight and the loft path share one
  helper now.
- **GPU: the whole variable blur runs on the GPU when enabled.** Each of the 4
  box passes builds an inclusive 2D prefix sum by Hillis-Steele scans (log2 W
  horizontal + log2 H vertical ping-pong draws) and one gather pass mirrors the
  CPU clamped-window box average exactly (same y1/y2/x1/x2 clamping and area).
  This was the last big CPU stage of the long shadow; with the loft sweep
  (4.2.11.28) the heavy parts of the effect are now GPU-resident.
- Parity self-test added (vb_mean_diff / vb_max_diff): float32 addition order
  differs between a sequential cumsum and a parallel scan, so a tiny diff (mean
  well under 0.1 grey level) is expected and invisible; the structure was
  validated exactly (1e-9 in float64) against the CPU SAT.

### Notes
- Opt-in with per-call CPU fallback as always; CPU output is bit-identical to
  4.2.11.31. Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.31] - 2026-06-09

Drag preview no longer shifts the layout; only the dragged object pixelates.

### Fixed
- **During a drag/resize the static elements stay put.** The low-res interaction
  preview used to drop the WHOLE page (background included) to 0.6x DPI, so every
  element re-rounded to the coarse grid and the layout visibly shifted, then
  snapped back on release. Now the page and all static objects render at full DPI
  (identical positions, no jump) and only the dragged object renders at reduced
  resolution and is upscaled NEAREST, so just that one object pixelates for
  responsiveness while everything else is rock-steady.
  - render_page_active gained an active_scale parameter; the editor keeps full DPI
    during interaction and passes active_scale=0.6 for the active object. The old
    whole-page low-DPI preview remains only as a fallback when there is no single
    active object (e.g. dirty-region disabled).

### Notes
- The dragged object's position stays full-DPI exact (within ~1px of the final
  raster); it snaps to full quality on release as before.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.30] - 2026-06-09

Long shadow: ~2x faster by right-sizing the work buffer (no visual change).

### Performance
- **The straight (taper 100%) long shadow renders about twice as fast.** Its soft
  blur is a box that reaches ~size, but the work buffer was padded by the generic
  size*3 used for 3-sigma Gaussian effects (glow, drop shadow). Long shadow now
  pads by size*1.3 + length (+ taper widening), shrinking the buffer area a lot.
  Output is identical (verified across throw angles, no clipping). A 28mm-blur
  shadow on a large shape went ~4.5s -> ~2.4s; 14mm ~2.7s -> ~1.2s.

### Notes
- The remaining cost is the per-pixel variable box blur itself. Making that
  GPU-fast is the next step (either an exact summed-area-table scan shader, or a
  GPU Gaussian-pyramid variable blur).
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.29] - 2026-06-09

GPU acceleration for the halftone screen (common path), faithful to the CPU.

### Added
- **The halftone dot stamping now runs on the GPU when enabled**, for the common
  path (built-in shapes, RGB/CMYK, hex or square grid, screen rotation, size and
  transparency modes). The per-cell grid loop is vectorised into instance data
  (position, size bucket, value) computed exactly as the CPU does, then the dots
  are stamped by GPU instanced quads sampling a bucket-stencil atlas with MAX
  blend, at the same integer positions as the CPU _stamp_max. Channel compositing
  (RGB add / CMYK multiply / key over) stays on CPU, unchanged.
- Halftone parity self-test (CPU loop vs GPU): reports mean/max diff, alongside the
  blur, CA and loft checks.

### Notes
- Opt-in and safe: custom pattern dots, random dot rotation and decentralization
  still use the tested CPU loop, as does any case when the GPU is unavailable or a
  step fails. The CPU path is byte-identical to before.
- The full GPU pipeline except the GL shader itself was validated bit-exact here
  (instances, atlas, integer placement, MAX stamping == CPU, diff 0); the GL stamp
  is validated by the on-hardware self-test, same conventions as the loft sweep.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.28] - 2026-06-09

GPU acceleration for the long-shadow taper loft sweep (the slow part).

### Added
- **The tapered long-shadow loft sweep now runs on the GPU when enabled** (the
  per-step scale+translate sweep that dominated CPU cost, ~0.3s soft / ~1.5s solid
  for a large shape). It is one GPU job: N steps composite a uniformly scaled,
  throw-translated copy of the silhouette into a coverage target (MAX blend) and a
  nearest-distance tmap target (MIN blend), mirroring the CPU sweep step for step.
  The same uv->image convention as the chromatic-aberration pass keeps the throw
  direction correct. The post step (variable blur, fade, colour) stays on CPU.
- Parity self-test for the loft sweep (asymmetric silhouette + diagonal throw):
  reports cov/tmap mean and max diff vs the CPU sweep, alongside the blur and CA
  parity checks.

### Notes
- Opt-in and safe: if the GPU is unavailable or any step fails, the renderer falls
  back to the identical CPU sweep, so output is always produced. taper == 100% is
  unchanged. The GPU path is validated by the on-hardware self-test (no GL context
  in CI); the CPU path and the sweep math were validated here.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.27] - 2026-06-09

Long shadow taper rebuilt as a true LOFT (morph), per the per-point model.

### Changed
- **Taper (!= 100%) is now a loft / morph, not a perpendicular squash.** The
  cross-section goes gradually from the object silhouette at the contact (scale 1)
  to a UNIFORMLY scaled copy of the silhouette at the far end (scale = taper),
  swept along the throw. So the far end is a shrunk or enlarged *image* of the
  object, with the right aspect ratio, instead of a perpendicular squash.
  - At length 0 the taper is just the scaled copy in the object's shape (plus rays
    + blur), concentric; no more square clipping or splatting.
  - Widening fans out gradually; narrowing converges gradually; the contact stays
    glued to the object at any size.
- Taper == 100% is unchanged (the fast straight-extrusion path).

### Notes
- The loft is a forward sweep, so it costs more than the straight path: roughly
  0.3s soft / ~1.5s solid for a large shape on CPU (the editor drag preview uses
  reduced DPI). A later GPU pass can do the sweep in parallel.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.26] - 2026-06-09

Long shadow taper: the casting contact no longer shifts sideways (the real taper bug).

### Fixed
- **Taper shifted the start of the shadow perpendicular to the throw, worse on
  big objects.** The taper scale was per-column, but a column of a large object
  mixes object rows (distance 0) and shadow rows (distance > 0), so the column
  average was non-zero right at the contact: the scale came out != 1 there and
  pushed the contact sideways, proportionally to the distance from the object
  centre (hence very visible on big objects). The taper scale is now taken
  per-pixel from the real distance, so it is exactly 1 at the object (the contact
  stays glued to the edge at any object size) and only grows into the shadow.
  Per-pixel distance is also smooth, so detailed shapes / text still do not tear.

### Notes
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.25] - 2026-06-09

Long shadow taper: widening taper no longer clips, and the taper warp no longer
smears edge content.

### Fixed
- **Widening taper (>100%) was cut off by a straight edge.** The work buffer was
  cropped to the object extent plus the blur reach, but a widening taper makes the
  shadow wider than the object, so the fanned part was clipped. The perpendicular
  crop now also accounts for the taper widening.
- **Taper resample no longer smears edge rows.** Where the taper sampling fell
  outside the buffer it was clamped to the edge row (smearing whatever was there);
  it now reads as empty, which is correct.

### Notes
- A single text shadow tapers cleanly; the busy pattern in a dense grid of text is
  the expected overlap of many faded shadows, not a per-shadow artifact.
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.24] - 2026-06-09

Long shadow: taper no longer tears detailed shapes, and "cast" mode is now in the UI.

### Fixed
- **Taper no longer tears text / detailed silhouettes.** The per-column taper
  scale was read from a distance that jumped column-to-column wherever the set of
  covered rows changed (e.g. between glyphs), so neighbouring columns were scaled
  by different amounts and sheared the shadow into streaks. The per-column
  distance is now smoothed along the axis, so the taper scale varies gradually and
  the shadow tapers as one coherent shape (the convergence toward the centre line
  is kept; the tearing is gone). Solid shapes are unchanged.

### Added
- **"cast" mode and its light controls are now selectable in the effect panel**
  (Mode: solid / soft / cast; plus Light elevation and Light disk, enabled in
  cast mode). Previously the cast mode existed only in the engine.

### Notes
- Document format unchanged (FORMAT_PATCH still 16).
## [4.2.11.23] - 2026-06-09

Long shadow: sharp casting edge at any angle, plus a new physical "cast" mode.

### Fixed
- **The casting edge now stays sharp along its whole length, at any edge angle.**
  The blur radius was per-column (one value across the whole perpendicular), so
  on an edge slanted to the throw the column average was non-zero right at the
  edge and softened it more the further along / the more slanted it was. The
  radius is now taken per-pixel from the real distance to the casting edge, so it
  is zero exactly at the edge everywhere; the side bleed still uses the column
  value so there is no border ridge.

### Added
- **"cast" mode: a physically-modelled shadow** (ls_mode = 'cast'), as an
  alternative to the stylistic 'soft' long shadow. A light at elevation
  `ls_light_angle` (1..90 deg, lower = longer shadow, length = height * cot(angle)
  using ls_length as the object height) shines on the object; the light disk
  `ls_light_size` is the penumbra, so edges soften with distance while the umbra
  stays solid (no length fade) and the contact stays sharp. Switchable so the two
  looks can be compared.

### Notes
- New serialised fields `ls_light_angle`, `ls_light_size`; document format bumped
  to .16. Backward/forward compatible (defaults, unknown keys ignored).
## [4.2.11.22] - 2026-06-09

Long shadow soft mode: one coherent field instead of two effects fighting. Fixes
the halo and the chopped-off tip.

### Fixed
- **Halo / "two effects that don't cooperate" is gone.** The shadow was built by
  blurring the silhouette and then SEPARATELY multiplying a fade, with the fade
  extrapolated into the blur halo, the mismatch read as a faint offset echo. Now
  the fade (and the gradient alpha) are baked into a SINGLE sharp alpha first, and
  that one real, already-faded shadow is blurred once. No extrapolation, no
  post-multiply, no halo. The blur softens the actual shadow as one thing.
- **Chopped-off far end is gone.** The work buffer was cropped at the shadow
  length, so the blurred, rounded tip (which reaches ~`size` beyond the end) was
  clipped into a straight cut. The crop now extends past the end by the blur reach,
  so the tip dissolves smoothly.

### Notes
- Document format unchanged (FORMAT_PATCH still 15). CPU render of a full scene
  stays ~1s; the SAT blur keeps cost independent of the blur size.
## [4.2.11.21] - 2026-06-09

Long shadow: fixed the border around the shadow and made taper use the good blur.

### Fixed
- **Border / ridge around the soft shadow at taper = 1.** Two causes: the blur
  radius was taken per-pixel from the extended distance field, so it varied
  across the side edges and the box average left a faint ridge; and the 4-pass
  box reached well past the cropped work buffer, so its tail was clipped into a
  faint outline. The radius is now per-COLUMN (constant across the perpendicular,
  no ridge), the soft edge reaches exactly `size` (4 passes of size/4) and the
  crop margin contains it (no clipped tail).
- **Changing taper no longer smears the blur across the whole shadow.** Taper was
  still going through the old per-step path, which applied one uniform blur and
  lost the sharp start. Taper is now folded into the main pipeline as a
  per-column vertical resample of the column, so any taper keeps the sharp
  casting edge and the same isotropic distance-driven blur (sharp start, soft
  growing tail). The old taper path is gone.

### Notes
- Document format unchanged (FORMAT_PATCH still 15).
## [4.2.11.20] - 2026-06-09

Long shadow soft blur rebuilt for quality: a true isotropic variable Gaussian.

### Changed
- The blur is now a genuine isotropic, spatially-varying Gaussian: every pixel is
  blurred by a radius taken from its distance along the shadow, in all directions.
  This replaces the perpendicular-only, per-column blur, which produced a hard
  core against a softer edge and could band column-wise. The shadow now softens
  smoothly in every direction, the far tip rounds off naturally, and there is no
  core/halo seam, no banding, and no detached double-shadow.
- Implemented with a 2D Summed-Area Table and a per-pixel radius (4 box passes ~
  a high-quality Gaussian); SAT keeps each pass independent of the blur radius.

### Notes
- Quality favoured over speed here: a full multi-object scene renders in ~1.3s at
  150 dpi. The drag preview renders at reduced DPI and only the moved object, so
  it stays responsive; a faster preview path can come with the GPU port.
- Document format unchanged (FORMAT_PATCH still 15).
## [4.2.11.19] - 2026-06-09

Long shadow perpendicular blur rewritten as a Summed-Area-Table (prefix-sum) box,
so its cost no longer depends on the blur radius.

### Performance
- The per-column variable blur now builds a 1D prefix sum along the column once
  per pass, then reads each pixel's window as two lookups (SAT[y+r+1]-SAT[y-r]),
  dividing by the true clamped window count (edge-correct, no dark rim). Three
  passes approximate a Gaussian. Cost is independent of the blur size: a 4mm and
  an 80mm blur now cost about the same, so the drag preview stays smooth even
  with a very large soft shadow. Visual output is unchanged.

### Notes
- Document format unchanged (FORMAT_PATCH still 15).
- Next (GPU): the same pipeline as moderngl passes (log-step silhouette + SAT
  blur + gradient pass) with a parity self-test against this CPU path.
## [4.2.11.18] - 2026-06-09

Long shadow refactored to a 3D-column model and gained a colour + alpha gradient
along its length.

### Changed
- The soft long shadow is now built as an explicit pipeline that treats the
  silhouette as a prism extruded along the throw: (1) project (rotate the throw
  to one axis), (2) extrude into the column with a height field t (0 at the
  casting edge, 1 at the tip), (3) per-height perpendicular blur that grows with
  t, (4) per-height colour and alpha, (5) project back. This is the same maths as
  before, but the structure now matches how the effect actually behaves and makes
  per-length properties first-class.

### Added
- **Colour + alpha gradient along the shadow** (`ls_color_grad`). When enabled,
  the shadow runs from `color` at the object to `color2` at the tip, with the
  alpha interpolating between the two colours' alphas. Output is RGBA. When
  disabled, behaviour is unchanged (flat tint with the usual fade).

### Notes
- New serialised field `ls_color_grad`; document format bumped to .15. Old files
  load unchanged (gradient defaults off); files written now still load in older
  builds (the unknown field is ignored).
## [4.2.11.17] - 2026-06-09

(Numbering: resuming the 4.2.11.x build sequence after 4.2.11.16; the 4.2.12 and
4.2.13 tags were a mis-numbered detour. Their content is folded in here.)

Long shadow soft mode: removed the detached "double shadow" halo, the blur now
widens the shadow smoothly as it travels.

### Fixed
- **Detached halo / double-shadow look is gone.** It came from blending discrete
  pre-blurred levels (a sharp copy plus a wide copy superimposed). Each column is
  now blurred by its own continuous radius (a true variable blur), so the shadow
  goes from sharp at the object to a smooth widening soft tail with no seam.
- Carried over from the 4.2.12/4.2.13 work: anisotropic perpendicular blur (the
  shadow fans out with distance instead of only softening in place), the earlier
  edge outline removed, and the rotated work buffer cropped to the shadow region
  so a full-scene render is well under a second and the drag preview is smooth.

### Notes
- Document format unchanged (FORMAT_PATCH still 14).
## [4.2.13] - 2026-06-09

Long shadow soft mode: the blur now widens the shadow as it travels, the hard
outline around the shadow is gone, and it renders several times faster.

### Fixed
- **The shadow now fans out / widens with distance.** The blur is applied
  perpendicular to the throw with a radius that grows along it (anisotropic),
  instead of an isotropic blur that only softened the edge in place without ever
  making the shadow wider. Linear and curve modes now visibly spread.
- **Removed the outline / contour around the shadow.** It was edge ringing from
  blending isotropically pre-blurred copies of the hard silhouette. The
  perpendicular blur keeps a constant radius within each cross-section, so there
  is no ridge along the edges.

### Performance
- The rotated work buffer is cropped to the shadow region (it was mostly empty),
  cutting a full-scene render from a few seconds to well under one. At the reduced
  DPI used during a drag, and re-rendering only the dragged object, the live
  preview is now smooth.

### Notes
- Document format unchanged (FORMAT_PATCH still 14).
## [4.2.12] - 2026-06-09

Long shadow soft mode rewritten from the ground up (shear-to-axis architecture),
synthesising five independent design reviews. Sharp casting edge at every angle,
fade to nothing, and a progressive blur that is finally visible across the body,
all at once, plus a clean thin diagonal line for text.

### Changed
- The shadow is computed by rotating the object so the throw points +X, then
  doing everything as 1D operations along that axis:
  - **One unified distance = upstream distance** (how far a pixel is from the
    object's trailing/casting edge, against the throw), via np.maximum.accumulate.
    It is zero over the whole object (sharp casting edge at any orientation) yet
    spans the full range beyond it (blur and fade develop for any shape, even a
    line drawn along the throw). This resolves the old distance-vs-projection
    conflict with a single correct measure.
  - **Blur** = weighted blend of pre-blurred levels keyed to that distance
    (constant / linear / curve). **Fade** is a SEPARATE step applied AFTER the
    blur, so the blur shows across the dark body instead of only in the faded
    tail (that coupling was why the blur looked absent).
  - The smear is built from binary coverage, so the shadow body is fully opaque
    and fades cleanly, regardless of the source antialiasing.
- **Thin diagonal lines no longer need the morphological close** (which rounded
  text corners): the 1D extrusion is continuous, with a tiny pre-AA so a hard 1px
  line survives the rotation. No checker, no corner rounding.
- O(log length) instead of O(length): a long shadow now renders in about a second.

### Notes
- Taper (narrow / widen) keeps the previous per-step path for now.
- Document format unchanged (FORMAT_PATCH still 14).
## [4.2.11.16] - 2026-06-09

Long shadow soft mode: the blur is now actually visible (it was being applied
after the fade, so it only affected the already-faded far end).

### Fixed
- **Progressive blur was invisible.** The blur was applied AFTER the fade, so the
  dark, visible part of the shadow (near the object) stayed sharp and the blur
  only touched the far end that the fade had already dimmed to almost nothing.
  The order is now: apply the directional, distance-driven blur to the full solid
  silhouette FIRST, then fade. The whole shadow (not just its faint tail) shows
  the blur, the casting edge stays sharp at any angle, and it still fades to zero.
## [4.2.11.15] - 2026-06-09

Long shadow soft mode: sharp casting edge at every angle, fade to nothing, and
blur that grows with distance, now all at once for any object orientation.

### Changed
- The blur and the fade are now driven by two different distance measures, which
  removes the conflict between them:
  - **Blur** is keyed to the distance a shadow pixel has travelled FROM the object
    along the throw. That distance is zero over the whole object, so the casting
    edge stays sharp at any orientation, and the blur grows smoothly outward.
  - **Fade** is keyed to the pixel's projection along the throw across the shadow.
    That spans a full range even for a line drawn along the throw direction, so
    the shadow always fades to nothing at the far end (object slant adds only a
    mild darkness gradient, never blur at the source).
  Result: sharp-at-origin (all angles) + fade-to-zero + increasing blur together.
## [4.2.11.14] - 2026-06-09

Long shadow soft mode: blur and fade now scale correctly for a line perpendicular
to the throw (line2.edof), while keeping the whole casting edge sharp (line3.edof).

### Fixed
- **Sharp edges and almost no fade for a line perpendicular to the throw.** The
  distance field was built by a separate coarse shift loop; for a thin feature
  the coarse steps left uncovered slivers (a holey field), and smoothing then
  crushed the field toward zero, so the blur radius (size*g) and the fade (1-g)
  stayed tiny. The field is now computed inside the dense extrusion loop itself,
  so it is gap-free for any feature; only light smoothing is applied. Blur and
  fade scale smoothly with distance again, the casting edge stays sharp for any
  object orientation, and the shadow fades to nothing at the far end.
## [4.2.11.13] - 2026-06-09

Long shadow soft mode: fixed one side of a slanted object being blurred at the
source. Verified on line3.edof (wide near-horizontal line).

### Fixed
- **A slanted/wide object was sharp on one side of the casting edge but already
  blurred at maximum on the other, right at the source.** The previous field was
  the projection along the throw, so the object's own far-projection parts (one
  end of a near-horizontal line) got a non-zero distance and were blurred at the
  object. The field is back to the distance a shadow pixel has travelled FROM the
  object along the throw (nearest generating offset), which is zero over the whole
  object -> the entire casting edge is sharp. It is normalised by its own maximum
  so the fade still reaches zero and the blur still reaches full radius even for an
  object with extent along the throw (the 4.2.11.12 fix is preserved).
## [4.2.11.12] - 2026-06-09

Long shadow soft mode: fade now reaches zero and the blur is no longer hard-edged.
Verified on line2.edof (long throw, large blur).

### Fixed
- **Fade did not reach transparency at the far end, and the soft blur had a hard
  outer boundary.** Both came from the distance field. It used the "nearest
  generating shift" which, for an object with extent ALONG the throw (a line
  drawn in the shadow direction), stays near 0 across almost the whole shadow:
  fade = (1 - g) never approached 0, and the blur radius (size * g) stayed tiny,
  so edges were sharp. The field is now the pixel's projection onto the throw
  axis, normalised across the smear (0 at the object, 1 at the far tip). It spans
  a full 0..1 for any object orientation, so the shadow fades fully to nothing and
  the blur grows to the full radius (soft silhouette that softens with distance).
  It is also analytic and per-pixel, so it is faster than the previous loop.
## [4.2.11.11] - 2026-06-08

Long shadow finally smooth on the real test cases (thin diagonal line, circle,
text). Verified against the actual line.edof.

### Fixed
- **Perpendicular wavy bands (ripples) in soft mode.** They came from tiling the
  shadow into discrete distance bands. Soft blur is now CONTINUOUS: a weighted
  sum of pre-blurred copies, weighted by a triangular partition of unity over the
  distance, so the blur radius varies smoothly with no banding.
- **White halo + ghost second shadow in soft mode.** The distance field is now
  extended into the blur halo by normalized convolution and blended as a full
  weighted sum (not a 2-level pick), so the outward falloff is soft with no ring.
- **Checker / stripes on a thin diagonal line, in solid AND soft.** The solid
  extrusion is a dense per-step smear (every 1px offset covered -> uniform, no
  sparse-coverage stripes) followed by a morphological close that fills the 1px
  diagonal gaps a 45-deg thin feature leaves, so a 1px line extrudes to a SOLID
  plane. Residual quantisation in the distance field is smoothed proportionally
  to its contour spacing so the soft blur shows no faint stripes either.

### Known
- The dense smear is O(length): ~1s at screen DPI, ~6s for a very long shadow at
  300 dpi (idle full-quality / export render; interaction uses the low-res path).
  A faster smear (GPU / van-Herk line dilation) is a planned follow-up.
## [4.2.11.10] - 2026-06-08

Long shadow rewrite addressing the reported checker / hard start / halo issues.

### Fixed
- **Thin diagonal features checkered and solid edges were jagged** (visible even
  in solid mode, not just soft). The smear was an integer-step paste, so a 1px
  feature swept across the throw landed on a checkerboard of pixels. The smear is
  now built SUPERSAMPLED (2x) and downsampled with antialiasing, so a thin line
  extrudes to a solid plane and edges are smooth. Benefits solid and soft modes.
- **Soft mode showed a white ring and a ghost second shadow.** The previous
  distance-field extension + 2-level interpolation produced those artifacts.
  Soft progressive blur is now done by tiling the antialiased shadow into
  overlapping distance bands (triangular partition of unity) and blurring each by
  its distance's radius, max-composited. The blur spreads outward on its own, so
  no halo; bands overlap, so no gaps; blur grows from sharp at the object to soft
  at the far end.

### Known
- The supersampled smear costs ~1.5-2s on CPU for medium/large shadows (idle
  full-quality render; interaction uses the low-res path). Enabling GPU effects
  offloads the band blurs. A faster smear (log-step / GPU) is a planned follow-up.
## [4.2.11.9] - 2026-06-08

### Fixed
- **Soft + linear long shadow: gaps/steps (4.2.11.8 bands) and hard edges
  (earlier).** Rewritten so the gap-free solid extrusion is kept whole and per
  pixel interpolated between full pre-blurred copies, using a distance field that
  is EXTENDED into the blur halo outside the shadow (the missing piece: outside
  pixels previously took the unblurred level, which clipped the outward falloff
  and kept edges hard). Result: gap-free, real progressive blur (sharp at the
  object, soft at the far end), no checker. Far-edge softness and low
  high-frequency content verified numerically.

### Known / next
- Very thin diagonal features can still show slight rasterisation jaggedness in
  the smear (integer-step sweep). The clean fix is a supersampled smear (render
  at 2x, downsample); planned next if needed.
- Heavy cases (very long shadow + large blur) take ~2s on CPU for the soft path;
  enabling GPU effects offloads the blurs.

## [4.2.11.8] - 2026-06-08

### Fixed
- **Soft + linear long shadow was not actually blurring** (sharp edges, and a
  checker on thin lines). It blurred the whole shadow at a few levels and blended
  per pixel by distance, so a pixel near the object picked the unblurred level and
  its far-projected parts stayed sharp. Rewritten as a true spatially-varying
  blur: the shadow is tiled into contiguous distance bands by nearest distance
  from the object (the solid extrusion is gap-free) and each band is blurred by
  the radius for its distance, then composited. Blur now grows smoothly from sharp
  at the object to soft at the far end; thin features no longer checker. Fade still
  works (per-band alpha).

### Added
- **'curve' blur mode** (engine groundwork): variable blur intensity along the
  throw via an adjustable exponent (ls_blur_gamma). A full curve editor with
  save/load is planned as a follow-up UI step. Constant and linear modes unchanged
  in meaning, now both rendered through the clean path.

## [4.2.11.7] - 2026-06-08

### Fixed
- **GPU effect blur produced a sheared "woven grid" for images whose width was
  not a multiple of 4** (very visible on long shadows with GPU enabled). Single-
  channel GL texture rows can be padded to a 4-byte boundary; at non-multiple-of-4
  widths the read-back was misaligned row to row. The CPU path was always correct.
  The GPU blur now pads the buffer to a multiple of 4 (edge-replicated) and crops
  back, and sets texture/read alignment explicitly. The blur self-test used a
  256px image so it never hit this. Workaround on older builds: turn GPU effects
  off (the CPU blur is unaffected).

## [4.2.11.6] - 2026-06-08

Long shadow fixes (reported on text and on thin-lined artwork).

### Fixed
- **Soft-linear blur followed horizontal position, not the shadow.** The
  graduated blur gradient projected each pixel's absolute position onto the
  throw direction from a single object-centre anchor, so for a wide object (a
  line of text) the blur depended on left/right position (left sharp, right
  blurred) instead of on distance from each letter. The gradient is now a
  distance-along-throw map measured from the casting silhouette, so every part
  of the shadow ramps from its own base: sharp at the object, blurred at the
  far end, everywhere.
- **Long shadows were truncated at 600px and broke into a comb on thin
  features.** The per-step offset used the (capped) step index directly, so any
  shadow longer than 600px stopped at 600px, and long shadows took >1px steps
  that left gaps across thin features perpendicular to the throw. The offset now
  spans the full length and the step count gives <=1px increments (continuous
  smear) up to a sanity cap.

## [4.2.11.5] - 2026-06-08

GPU acceleration extended to chromatic aberration (the second effect on GPU).

### Added
- **GPU chromatic aberration**: per-channel tint + linear shift / radial scale in
  a single fragment shader (gpu_chromatic_aberration). Wired into the CA effect
  behind the "Use GPU for effect blur" toggle, with per-effect CPU fallback —
  verified identical to CPU (both linear and radial) when GPU is unavailable.
- **CA added to the parity self-test**: the GPU self-test now reports chromatic
  aberration mean/max difference (vs a numpy reference) alongside the blur, and
  saves ca_ref/ca_gpu/ca_diff images.

### Note
- Export and the idle full-quality render stay on CPU. Next GPU candidate:
  halftone.

## [4.2.11.4] - 2026-06-08

### Fixed
- **Text box was missing the Copy / Paste / Clear layer-effect buttons**. It
  added the Layer Effects button bare instead of via the shared FX helper; now
  it uses the same helper as every other object type.

### Changed
- **Layer-effects controls are now two separate rows for every object type**:
  the "Layer Effects" button on its own row, and Copy / Paste / Clear on a
  separate row below it (was a single combined row).

## [4.2.11.3] - 2026-06-08

### Changed
- **All effect blur now routes through the GPU path** when enabled. The long
  shadow soft-LINEAR branch (its graduated multi-level blur) was still on CPU;
  it now uses the same GPU-or-CPU helper as the soft-CONSTANT branch and every
  other effect. The only remaining direct CPU Gaussian call is the fallback
  inside the helper itself. Verified: both long-shadow soft modes render and are
  identical to CPU when GPU is unavailable.

## [4.2.11.2] - 2026-06-08

GPU blur wired into the live renderer (opt-in), after the parity self-test
passed on real hardware (mean diff 0.35 / max 4 of 255).

### Added
- **GPU-accelerated effect blur**: drop/inner shadow, outer/inner glow and the
  bevel soften now run their Gaussian blur on the GPU when "Use GPU for effect
  blur" is on (View -> Performance / optimizations). A single long-lived GPU
  worker thread owns the GL context and processes blur jobs from a queue, so the
  context is used safely from the render worker threads.
- **Per-effect CPU fallback**: any GPU miss (disabled, unavailable, radius over
  budget, or error) transparently uses the CPU, so output is always produced and
  matches the CPU path. Verified identical when GPU is unavailable.
- **Status badge**: the resolution status shows "· GPU" when GPU effects are on
  and available.
- **GPU effects toggle** in the Performance dialog (default OFF), persisted; the
  self-test button remains for validation.

### Note
- Export and the idle full-quality render are unaffected by the live wiring;
  this accelerates interactive/effect rendering. Other effects (chromatic
  aberration, halftone) remain CPU for now and will be moved over incrementally,
  each gated by its own parity check.

## [4.2.11.1] - 2026-06-08

### Fixed
- **GPU blur output was vertically mirrored** vs the CPU reference. The parity
  self-test made this obvious (the diff image was a clean vertical-mirror
  pattern). An extra np.flipud in gpu_gaussian_blur_L was the culprit: the
  texture upload and framebuffer read-back orientations already cancel, so no
  flip is needed. Removed it; GPU and CPU blur should now align.

## [4.2.11.0] - 2026-06-08

Build 5 groundwork: optional GPU acceleration scaffolding + a CPU-vs-GPU parity
self-test. No live-render behaviour changes yet.

### Added
- **edof/engine/gpu.py**: optional moderngl-based GPU module. A lazily-created
  standalone GL context gates everything via gpu_available(); when moderngl or a
  GPU is absent, every entry point falls back (returns None) and the CPU path is
  used. Includes a two-pass separable Gaussian blur shader (gpu_gaussian_blur_L)
  for the shadow/glow blur, capped to a fixed tap budget (large radii fall back).
- **Parity self-test**: View -> Performance / optimizations -> "Run GPU
  self-test…" (and the `edof-gpu-selftest` console script). Blurs a test mask on
  CPU (PIL) and GPU, saves cpu/gpu/diff images, and reports mean/max pixel
  difference so the shader can be validated on real hardware.
- **Optional `gpu` extra**: `pip install moderngl` (pyproject [gpu]).

### Note
- The GPU path is NOT wired into the live renderer or export yet — that comes
  after the parity self-test confirms acceptable CPU/GPU agreement on real
  hardware. Export and the idle full-quality render will always stay on CPU.

## [4.2.10.14] - 2026-06-08

Follow-up to the BASIC-mode undo fix.

### Verified
- Layer-effect changes (effects dialog OK, Copy / Paste / Clear effects) are
  undoable, along with every property-panel edit (fill, stroke, corners, font,
  blend, opacity, ...): they all route through the changed / objectChanged
  handler that now records a coalesced history step.

### Fixed
- **Cancelling the Layer Effects dialog left a dead no-op undo step**. The cancel
  path restores the pre-dialog state (identical to the current history top), so
  it now suppresses history recording instead of pushing a redundant snapshot.

## [4.2.10.13] - 2026-06-08

Undo/redo now works for object edits in BASIC (free-design) mode.

### Fixed
- **Move / resize / rotate and property-panel edits were not undoable** in BASIC
  mode. These all route through the objectChanged / panel-changed handler, which
  only set the modified flag and never recorded history; only explicit ops (add,
  delete, duplicate, ...) pushed snapshots. Object edits are now coalesced into
  one history step per burst (mirroring the body-text model) and pushed, so
  Ctrl+Z / Ctrl+Y step through moves, resizes, rotations and style changes.

### Details
- A short debounce (450 ms) groups a burst of edits (e.g. a slider drag or a
  move) into a single undo step. Explicit ops flush/cancel the pending burst so
  no duplicate snapshot is recorded; undo/redo flush it first so the latest edit
  is captured. Programmatic doc swaps (New / Open / Import / history restore)
  suppress recording so they never add spurious steps.

## [4.2.10.12] - 2026-06-08

Halftone fixes (reported on paths): dot sizing and the default screen angle.

### Fixed
- **Dot sizes were inconsistent / edge dots dropped or detached**. Each dot's
  channel value was sampled from a SINGLE pixel at the cell centre, so a centre
  landing on a partial-alpha edge made the dot jump in size or vanish. Now the
  value is AVERAGED over the cell (radius ~ cell/4), alpha-weighted, matching the
  reference mosaic generator. Solid fills now reach near-full coverage instead of
  looking washed out, and edge dots are sized consistently.
- **Default screen-angle step was 45 deg, not 72**. The halftone effect created
  from the dialog forced ht_angle = 45 (the model default was already 72); it now
  uses 72, so the per-channel screens are spaced as intended.

### Note
- For additive RGB, dark areas legitimately produce no ink (black = no light);
  enable the extra (black) key channel to render blacks in RGB mode.

## [4.2.10.11] - 2026-06-08

In-app control over the render optimizations, including the GPU viewport (which
was previously forced on with no way to disable it).

### Added
- **View -> Performance / optimizations…**: a dialog to toggle each render
  optimization on/off, applied live and persisted via QSettings:
  per-object raster cache, dirty-region (active object only), adaptive render
  DPI (zoom + HiDPI), supersample-when-zoomed-out, low-res preview while
  dragging, and the GPU (OpenGL) viewport. All default ON. Turning everything
  off gives the simplest, most predictable render path for comparison.

### Changed
- The QOpenGLWidget viewport (on by default since 4.1.0) is now behind the
  gl_viewport setting and can be swapped to the plain raster viewport at runtime
  (useful if a GPU/driver shows a black viewport or artifacts).

### Note
- These flags affect the interactive render path only; the idle full-quality
  render and all exports always use the exact path. GUI smoke-tested headless;
  the GPU viewport toggle needs verifying on real hardware.

## [4.2.10.10] - 2026-06-08

Dragging a heavy object is now cheap: the active object's raster is reused
across pure moves instead of being re-rendered every frame.

### Added
- **Active-object translation cache**: render_page_active() now keys the active
  object's raster on a signature that EXCLUDES translation, so a pure move (only
  transform.x/y changes) re-composites the cached crop at the new pixel offset
  instead of re-rendering the object and its expensive effects (blur / glow /
  bevel / halftone / drop shadow). Rotation, flip, size and content still force a
  re-render. Normal-blend only; non-normal blends render directly.

### Performance
- ~9.5x faster while dragging an object that carries a drop shadow + halftone on
  a cluttered page, vs the per-object cache. Output matches a full render within
  1 LSB (interactive preview only).

## [4.2.10.9] - 2026-06-08

Build 4 (render & performance) dirty-region pass: editing one object no longer
re-renders the whole page each frame.

### Added
- **render_page_active()**: while a single object is being edited, the static
  rest of the page is cached as two flattened layers (below / above the active
  object) keyed on a signature of every non-active object; only the active
  object is re-rendered and composited between them each frame. Falls back to a
  full render when the active object is not on the page or an above-object uses a
  non-normal blend. The editor uses this on the interactive (drag / resize /
  path-edit) render path; the idle full-quality render and export are unchanged.

### Performance
- ~2x faster interactive re-render on a 40-object page vs the existing
  per-object cache, scaling further with object count (one flatten instead of
  re-compositing every static object every frame). Pixel output matches a full
  render within 1 LSB (interactive preview only; full-quality / export use the
  exact path).

## [4.2.10.8] - 2026-06-08

Pen / path tool fixes found via the debug log: stroke rendering, draw-mode
handle sizing, and closed-path geometry.

### Fixed
- **Path stroke rendered as disjoint rectangles** with cracks at every vertex
  when widened. Stroke polylines are now drawn with rounded joints (and round
  end caps for wide strokes), so the stroke is continuous.
- **Wide path stroke clipped by the bounding box**. The path buffer is padded by
  half the stroke width on every side (the bbox only covers the centreline), so
  a thick stroke is no longer cut off at the object edge.
- **Draw-mode control points scaled with zoom**. Preview anchor/handle dots are
  now sized in screen pixels (divided by zoom, cosmetic pens), matching the
  constant on-screen size used in edit mode.
- **Closed path did not connect with a curve, and an extra phantom anchor
  appeared**. The wrap segment's endpoint was hardcoded to (0,0) instead of the
  start point M; whenever M was not at the bbox origin the closure was mistaken
  for an extra anchor and did not curve back. The wrap now ends exactly at M and
  is emitted whenever either end is curved, with the correct outgoing/incoming
  tangents.
- **Dragging a point on a closed path could make the last point vanish**. When M
  was dragged, the wrap-sync overwrote the last user anchor's endpoint on paths
  without a real wrap-cmd. The sync now runs only for a genuine wrap-cmd
  (endpoint matching M's previous position).

## [4.2.10.7] - 2026-06-08

The reliable way to turn on debug logging: do it from inside the editor. No more
dependence on how the app was launched (file association, shortcut, entry point,
or batch quoting).

### Added
- **Help -> Debug log (curves/keys)**: checkable menu toggle that enables/disables
  detailed pen-tool + keypress logging at runtime. On enable it creates the log
  file immediately and shows the exact path, with an "Open folder" button.
- **Help -> Open debug log location…**: opens the folder containing the log and
  shows the resolved path (works whether or not the file exists yet).

### Note
- Path: uses EDOF_DEBUG_PATH if set, otherwise edof_debug.log in the user home.
  Launching via edof-editor-debug.bat still works and pins the log next to the
  launcher; the menu is the launch-independent fallback.

## [4.2.10.6] - 2026-06-08

Make the debug log impossible to miss: it now appears the instant the editor
launches with EDOF_DEBUG enabled, instead of only after the first curve/key
event. Pairs with the 4.2.10.5 launcher fix.

### Added
- **Guaranteed startup log line**: on launch with EDOF_DEBUG enabled, the editor
  writes an `editor.startup` event (with version and the resolved log path)
  immediately, creating the log file up front. Instant confirmation that
  logging is on and where the file lives.

### Note
- The .bat launchers run the INSTALLED edof package, so the 4.2.10.5/4.2.10.6
  fixes only take effect after re-installing (deploy-edof.bat -> [1]) AND using
  the new edof-editor-debug.bat.

## [4.2.10.5] - 2026-06-08

Fix: the debug log was never written. The debug launcher set
EDOF_DEBUG with a trailing "REM ..." comment on the same line, so on Windows
the variable held "1  REM ..." instead of "1" and the truthy check failed,
silently disabling logging.

### Fixed
- **edof-editor-debug.bat**: EDOF_DEBUG and EDOF_DEBUG_PATH are now each on
  their own line with no inline comment. The log is written next to the
  launcher (%~dp0edof_debug.log) as intended.
- **debug_log._env_enabled()**: hardened so only the first whitespace token of
  EDOF_DEBUG decides truthiness (strips a stray trailing comment / quotes).
  A polluted launcher value can no longer silently disable logging.

# Changelog

All notable changes to **edof** are documented here.
Format: Keep a Changelog (https://keepachangelog.com/en/1.0.0/)
Versioning: SemVer (https://semver.org/)

================================================================================

## [4.2.10.4] - 2026-06-05

### Added
- **Detailed opt-in debug logging for curve creation and editing**, plus every
  key press/release. Each entry records the current mode and path state (point
  count, edit target, drag state) for context. Logged events include: placing
  pen points, drag-to-curve, closing a path, finishing/cancelling a drawing
  (with the created object id, command count and bbox), entering/exiting path
  edit, grabbing/dragging/releasing anchor and control-point handles (old→new
  positions + active modifiers), anchor selection, point insertion, and
  connect/disconnect. Use this to reproduce and pin down curve-tool bugs.
- **The debug launcher (edof-editor-debug.bat) now enables the debug log**
  (EDOF_DEBUG=1), writing edof_debug.log next to the launcher. Run that launcher,
  reproduce the issue, then read/send the log.

================================================================================

## [4.2.10.3] - 2026-06-05

### Fixed
- **The grid, page margins and alignment guides now keep a constant on-screen
  width at any zoom** (and stay crisp on HiDPI), matching the selection-handle
  fix. They were drawn with scene-unit pens, so lines and grid dots got thick
  when zoomed in and faint when zoomed out. They now use cosmetic pens (constant
  screen width and dash); the grid also hides when the dots would be too dense
  on screen rather than judging density in scene units.

================================================================================

## [4.2.10.2] - 2026-06-05

### Fixed
- **Selection handles, the transform bounding box and the rotate handle now stay
  a constant on-screen size at any zoom** (and are crisp on HiDPI displays).
  They were drawn in scene units, so they grew when zooming in and shrank when
  zooming out. Outlines now use cosmetic pens (constant screen width + dash) and
  the handle squares/circles, rotate-handle distance and hit-test radius are
  divided by the view zoom, so grabbing a handle feels the same at every zoom.

================================================================================

## [4.2.10.1] - 2026-06-05

### Changed
- **The draw preview now matches the shape you are drawing.** Dragging out an
  ellipse shows an ellipse preview, and a line/arrow shows a live segment from
  the start point to the cursor, instead of always a dashed rectangle.

### Fixed
- **Lines now keep the direction you draw them in.** Dragging from bottom-right
  to top-left previously snapped the committed line to a top-left → bottom-right
  diagonal. The two endpoints are now taken from the actual drag.
- **Horizontal and vertical lines can be drawn again.** The draw was cancelled
  unless the bounding box was at least 5 mm in *both* dimensions, so a perfectly
  axis-aligned line (zero height or width) was rejected. Lines now use a minimum
  *length* of 2 mm instead.

================================================================================

## [4.2.10.0] - 2026-06-05

### Changed
- **Maximum zoom is now 10x** (1 document pixel : 10 screen pixels, shown as
  1000% in the status bar), up from 5x, for fine pixel-level inspection. Pixel
  edges stay crisp (nearest-neighbour) in this range.
- **Live previews while tuning layer effects now render at reduced DPI** for
  responsiveness, then snap to full quality ~0.35s after you stop adjusting.
  This makes dragging sliders on heavy effects (halftone, blur) smooth instead
  of lagging on every tick. Reuses the same low-res-during-interaction path as
  object dragging.

================================================================================

## [4.2.9.9] - 2026-06-05

Build 4 (Render & performance) slice: anti-aliased minification.

### Changed
- **Zoomed-out pages are now supersampled for smooth minification.** Fine detail
  (halftone dots, thin strokes, small text) was aliasing / moiring when the page
  was shrunk, because it rendered at the bare on-screen resolution. The page now
  renders above that, up to the base DPI, and Qt minifies it (= anti-aliasing).
  Extreme zoom-out still scales below base so large pages stay cheap. On a
  halftone-filled ellipse this cut the error vs a high-DPI reference by ~55%.

================================================================================

## [4.2.9.8] - 2026-06-05

Build 4 (Render & performance) slice: low-resolution preview during interaction.

### Changed
- **Dragging or resizing an object now renders at a reduced DPI for
  responsiveness**, then snaps back to full quality the moment you release.
  Previously the whole page was re-rendered at full DPI on every mouse-move,
  which lagged for heavy objects (large images, halftone, blur). Geometry and
  hit-testing are unaffected (the low-res pixmap is scaled onto the base-DPI
  scene exactly like the adaptive-DPI zoom rendering).

================================================================================

## [4.2.9.7] - 2026-06-05

### Changed
- **Zoom limits are now content-relative instead of a fixed percentage.** Max
  zoom = 5 screen pixels per document pixel (shows as 500% in the status bar),
  and at that range the page is drawn with **crisp pixel edges** (nearest-
  neighbour once we're upscaling beyond the render-DPI cap) instead of a blur.
  Min zoom = half the fit-to-window zoom (the page fills about half the
  viewport), so you can't lose the page off-screen.
- **Holding Alt over the page shows a magnifier cursor** (a plain loupe, no
  +/- sign) to signal that the wheel will zoom. It clears on release / when the
  pointer leaves the page.

================================================================================

## [4.2.9.6] - 2026-06-05

### Fixed
- **The zoom % in the status bar now updates live and is meaningful.** It was
  stuck at 100% because wheel/pinch zoom changed the canvas without notifying
  the status bar; the canvas now emits a zoom-changed signal. The displayed
  percentage is also rescaled so **100% means 1 document pixel : 1 screen
  pixel** (previously it showed the internal canvas zoom, which is relative to
  the dynamic render DPI, so a 300-DPI page looked "zoomed in" at "100%").
- **New documents now fit the page to the window** (like Open in 4.2.9.5), so a
  new document is fully visible instead of opening zoomed in.

================================================================================

## [4.2.9.5] - 2026-06-05

### Added
- **Opening a document now fits the page to the window automatically** (the same
  as Fit / Ctrl+0), so you start at a sensible zoom instead of an arbitrary one.
  Deferred until the viewport is sized so the fit is correct. Only on open —
  editing, adding/removing pages and undo/redo no longer change your zoom.

================================================================================

## [4.2.9.4] - 2026-06-05

### Changed
- **Status bar now shows document info instead of the internal canvas DPI.** It
  reads e.g. ``300 DPI · 210×297 mm · 2480×3508 px`` (page export DPI, size in
  millimetres, and size in pixels at that DPI). The old "DPI 300 (canvas 150)"
  exposed the internal render DPI, which is now dynamic (zoom/display-aware) and
  not meaningful to the user. Updates on page switch; a tooltip notes on-screen
  sharpness is automatic and independent of this.

================================================================================

## [4.2.9.3] - 2026-06-05

Build 4 (Render & performance) slice 3: HiDPI-aware rendering.

### Changed
- **The canvas now renders at the display's device pixel ratio.** On HiDPI /
  retina screens and Windows display scaling (125-150%), the page was rendered
  at logical resolution and the OS upscaled it, looking soft. The render DPI now
  includes the device pixel ratio (clamped to 4x, with the same 24-DPI
  quantisation, 48-DPI floor and 3x / ~28 MP caps), so on-screen pixels are ~1:1
  with physical pixels: crisp text and edges on scaled displays. On a 1x display
  at ~100% behaviour is unchanged.

================================================================================

## [4.2.9.2] - 2026-06-05

### Changed
- **Adaptive render DPI now also applies when zooming out.** The page is
  rendered to match the effective on-screen resolution (base DPI x zoom): zoomed
  out it renders fewer pixels (faster, identical sharpness, since the screen
  can't show more than its pixels), zoomed in it renders more (crisp). DPI is
  quantised to 24-DPI steps to limit cache churn while zooming, with a 48-DPI
  floor and the 3x / ~28 MP cap; at ~100% the exact base DPI is used. As before,
  the pixmap is scaled onto the base-DPI scene, so positions never shift.
  (Rendering at the object's full DPI when the page is shown small would only
  waste pixels the display can't show, so we target the screen resolution.)

================================================================================

## [4.2.9.1] - 2026-06-05

Build 4 (Render & performance) slice 2: adaptive render DPI by zoom.

### Changed
- **Zooming in now renders crisp instead of upscaling a blurry base-DPI image.**
  When zoom > 1.25x the page is rendered at a proportionally higher DPI (capped
  at 3x and at ~28 MP) and the resulting pixmap is scaled back onto the base-DPI
  scene, so on-screen pixels are ~1:1 with rendered pixels (sharp text and
  edges). At zoom <= 1.25x behaviour is unchanged (base DPI, no oversampling).
  Crucially the scene coordinate system stays at base DPI, so object/overlay
  positions and hit-testing do not shift with zoom (the old oversampling bug
  that caused text-position jumps does not return).

================================================================================

## [4.2.9.0] - 2026-06-05

Build 4 (Render & performance, phase 1) start: per-object render cache.

### Added
- **Per-object raster cache** in the renderer. Each object's rendered result is
  cached and reused while it is unchanged, so editing one object on a busy page
  no longer re-renders every other object. Pixel-identical to the uncached path
  (verified): the cache key is a content signature of the object (geometry,
  content, effects, blend, opacity) plus DPI, page size, variables and a
  resource fingerprint; only normal-blend objects are cached (a non-normal
  blend blends against the layers beneath it, so it falls back to a direct
  render). Opt-in via ``render_page(..., use_cache=True)``; the editor canvas
  uses it, exports stay uncached for safety. New ``clear_object_cache()``.

### Performance
- Re-render of a 40-object page after changing one object: ~514 ms -> ~36 ms in
  testing; an all-unchanged re-render ~30x faster. (Editor canvas re-render.)

================================================================================

## [4.2.8.7] - 2026-06-05

### Changed
- **Live colour preview is now everywhere a colour dialog is used**, not just
  object fill/stroke/text. Dragging in the picker live-updates: all layer-effect
  colours (Colour Overlay, Gradient Overlay, outer/inner Glow, Satin, Stroke
  effect, Bevel highlight/shadow, Long Shadow, etc.) and the **page background**
  in Page Settings. Cancel restores the previous colour (page background is also
  restored if Page Settings itself is cancelled). The only colour control
  without live preview is the new-document custom-background swatch, which has
  no object to preview on.

================================================================================

## [4.2.8.6] - 2026-06-05

Build 3 (Colors) complete: live colour preview.

### Added
- **Live preview on the object while picking a colour.** Dragging in the SV
  square / hue / alpha strip (or editing the fields) updates the object on the
  canvas in real time, alpha included. Cancel restores the original colour; OK
  keeps the new one. Wired for text colour, fill, stroke, line stroke and QR
  colours.

================================================================================

## [4.2.8.5] - 2026-06-05

Halftone pattern UX + sensible background default.

### Fixed
- **Background no longer forces a solid fill by default.** The default is now
  *Transparent*, so the document background shows through the gaps between dots
  (previously the *Native* default painted a solid black base for RGB / white
  for CMYK, e.g. when applied to a square — not wanted as a default). *Native*
  and *Layer* remain selectable.
- **Per-channel patterns are settable again.** After loading one image you can
  now load the others.

### Changed
- **Explicit Pattern mode selector** is back: *Built-in shape* / *One image
  (all channels)* / *Per channel (individual)*. The thumbnail slots show one
  slot for "one image", or one per channel for "per channel".
- The **extra key channel is now optional (off by default)** as intended — turn
  it on for full-range black(RGB)/white(CMYK) dots in Transparent mode.

================================================================================

## [4.2.8.4] - 2026-06-05

### Added / Changed
- Eyedropper now uses the bundled **eyedropper cursor**, shows a live **loupe**
  (zoomed pixels) with a **colour swatch + hex** next to the cursor as you move,
  and **right-click (or Esc) cancels** the pick.

================================================================================

## [4.2.8.3] - 2026-06-05

### Fixed
- **Eyedropper now works.** The "Pick from screen" overlay is now a modal
  dialog, so it takes input precedence over the (modal) colour dialog — the
  cross cursor shows and clicking anywhere samples the pixel. It also grabs the
  screen under the cursor (multi-monitor) and maps the click through that
  screen's offset and device-pixel-ratio.

================================================================================

## [4.2.8.2] - 2026-06-05

Colour eyedropper + halftone pattern thumbnails & library.

### Added
- **Eyedropper in the colour picker.** A "Pick from screen" button grabs a
  full-screen snapshot; click anywhere (canvas, another window, anywhere) to
  sample that pixel's colour. Esc cancels.
- **Halftone pattern thumbnails.** Each channel has its own thumbnail slot
  showing its loaded pattern. Click a slot to: Load image…, pick one From the
  library, Use a library item / this item for ALL channels, or Clear. Empty
  slots fall back to the built-in shape.
- **Halftone pattern library.** Patterns you load are remembered across the app
  (persisted) and reusable from any slot's menu. Patterns load per channel
  separately.

================================================================================

## [4.2.8.1] - 2026-06-05

Halftone: full-range reproduction on any background.

### Added
- **Background mode** for the halftone screen: *Native* (default — the screen
  paints its own base, black for RGB / white for CMYK, so blacks and whites are
  reproduced faithfully regardless of the document background, self-contained),
  *Transparent* (dots only, gaps see-through), *Layer content* (dots over the
  original layer).
- **Extra key channel**: adds an achromatic screen — black dots for dark areas
  in RGB, white dots for bright areas in CMYK — so the Transparent mode can also
  cover the full tonal range. Ink is Auto / White / Black. Default on.
- **Per-channel enable**: turn individual screens (R/G/B(+key) or C/M/Y/K(+key))
  on or off.

### Fixed
- RGB omitted blacks and CMYK omitted whites unless the document background
  happened to be black / white (the original design baked them into the
  background). Native background and the extra channel now handle them.

### Changed
- File schema 4.2.13 -> 4.2.14.
- (Still to come: pattern thumbnails + a reusable pattern library, and an
  eyedropper inside the colour dialog.)

================================================================================

## [4.2.8.0] - 2026-06-05

Build 3 (Colors) start: Photoshop-style colour picker.

### Changed
- **The colour picker is now a Photoshop-style dialog.** A saturation/value
  square plus a hue strip (and an alpha strip when alpha is enabled), with
  HSB / RGB / hex (#RRGGBB or #RRGGBBAA) fields that all stay in sync, a live
  "new vs current" swatch, and click-drag on the square/strips. Replaces the
  previous RGBA-slider dialog. All existing colour buttons use it (same
  get_color API), so it applies everywhere colours are chosen.
- Picker number fields widened so 3-digit values (e.g. 255 / 360) and the
  8-digit hex are no longer clipped.

================================================================================

## [4.2.7.20] - 2026-06-05

Build 2 phase 2 (slice 20): halftone background + edge-clip modes.

### Fixed
- **The halftone no longer leaves the original image showing underneath** (it
  did even with fill_opacity 0). The dot coverage is now the layer alpha, so the
  gaps between dots are transparent and, in the default "just patterns" mode,
  the layer body is not composited at all.

### Added
- **"Keep background under dots" toggle.** Default OFF = only the screened dots
  are shown, gaps transparent (body dropped). ON = dots are drawn over the
  original layer content.
- **"Edge clip" mode** for the dots: Whole dots (no clip, default — dots stay
  whole and may extend past the source edge), Hard (clip to the source
  silhouette), Soft (feather to the source alpha).

### Changed
- File schema 4.2.12 -> 4.2.13 (new halftone fields). Older files load with
  defaults.

================================================================================

## [4.2.7.19] - 2026-06-05

Build 2 phase 2 (slice 19): halftone custom patterns, random rotation, opacity fix.

### Added
- **Custom halftone pattern images.** Pattern source can be the built-in shape,
  1 image used for every channel, or per-channel images (3 for RGB / 4 for
  CMYK). A channel with no supplied pattern falls back to the built-in shape.
  The pattern's own alpha (transparency) is used as the dot mask.
- **Random dot rotation** for halftone (each dot rotated by a stable
  pseudo-random angle).

### Changed
- Default halftone screen-angle step is now 72 degrees.
- **Halftone now respects the effect Opacity** (mixes the screen with the layer
  content); previously the opacity slider was ignored on this effect.

### Notes
- Blend: the halftone effect's Blend mode blends the screen against the layer
  content; the object-level blend (Blending Options) blends the whole layer
  against what is beneath it. Both work; note that "multiply" over a white page
  is identity by definition, so it can look like nothing changed.
- File schema 4.2.11 -> 4.2.12 (new halftone fields). Older files load with
  defaults.

================================================================================

## [4.2.7.18] - 2026-06-05

Build 2 phase 2 (slice 18): real halftone (per-channel mosaic screen) + more icons.

### Changed
- **Halftone effect fully reworked into a per-channel "mosaic" screen.** The old
  effect only did a single luminance dot/line screen ("dots and lines"). It now
  reconstructs the image from shaped dots, each colour channel screened on its
  own rotated grid: RGB channels composite additively on black, CMYK channels
  composite multiplicatively on white. New controls: colour mode (RGB/CMYK), dot
  driven by Size or Transparency, dot shape (circle / diamond / square / ring /
  cross / line / triangle / hex), cell size, per-channel screen-angle step, dot
  scale, max-dot-vs-cell overlap, decentralization, and hex vs square grid.
  Pure numpy + Pillow, no new dependencies.
- File schema 4.2.10 -> 4.2.11 (new halftone fields). Older files still load
  (missing fields default).

### Added
- More buttons attempt bundled icons with graceful glyph fallback: sub-document
  / SVG / PDF / CSV toolbar buttons, the layer-order buttons (up/down light up
  now), and polygon / arrow object types. Icons still to draw are listed in
  edof-icons-todo.json (drop the PNG in and it appears; otherwise the current
  default shows).

================================================================================

## [4.2.7.17] - 2026-06-05

Build 2 phase 2 (slice 17): Copy/Paste/Clear layer effects + more real icons.

### Added
- **Copy / Paste / Clear Layer Effects.** Small buttons sit next to the
  "Layer Effects…" button in the property panel, and a "Layer Effects" submenu
  is in the right-click menu both on the canvas and in the Objects panel. Copy
  grabs the whole layer style (effects + blend mode + opacity + fill opacity);
  Paste applies it to another object; Clear removes all effects. Paste is
  disabled until something is copied; Clear is disabled when the object has no
  effects.

### Changed
- **Objects panel uses real bundled icons.** Each row shows a per-type icon
  (text / image / rect / ellipse / line / pen for paths / qr / table / group),
  and the visibility and lock toggles now use proper eye / lock icons instead of
  emoji. A glyph fallback is kept where no matching asset exists.

================================================================================

## [4.2.7.16] - 2026-06-05

Build 2 phase 2 (slice 16): fix bevel ring/contour banding.

### Fixed
- **Bevel & Emboss no longer shows concentric-ring / contour banding** across
  the face. Previously the height map came from a blurred 8-bit alpha, which (a)
  domed over the whole shape for larger bevels and (b) quantized into contour
  rings. It is now built from a **distance transform** (ramps over the bevel
  width, then a flat plateau) computed in float, so the interior face has zero
  slope and receives no shading. The bevel stays confined to the edge band.
- scipy is used for the distance transform when available, with a pure-numpy
  fallback (downsampled for large objects to stay fast) so EDOF keeps no hard
  scipy dependency.

================================================================================

## [4.2.7.15] - 2026-06-05

Build 2 phase 2 (slice 15): proper Photoshop-style bevel shading + more sliders.

### Changed
- **Bevel & Emboss rewritten to normal-based shading.** Instead of the old
  "blur the alpha and subtract" edge trick, it now builds a height ramp from the
  edge, derives surface normals, and lights them with the light azimuth
  (angle) and elevation (altitude). The shading is confined to the sloped bevel
  band, giving the smooth rounded highlight/shadow gradient you get in
  Photoshop. Technique, Depth, Direction, Soften, Altitude and the separate
  Highlight/Shadow opacities all feed into it; inner/emboss/smooth and outer
  share the renderer.
- **More sliders:** in the Bevel panel, Depth, Light angle and Altitude are now
  sliders (with live value labels).

================================================================================

## [4.2.7.14] - 2026-06-05

Build 2 phase 2 (slice 14): richer Bevel & Emboss render.

### Added / Changed
- **Bevel & Emboss now uses its full set of controls** (previously the render
  ignored most of them): Technique (smooth / chisel hard / chisel soft), Depth
  (%), Direction (up / down), Soften (mm), Altitude (light height °), and
  separate Highlight opacity / Shadow opacity. The inner/emboss/smooth kinds
  share one richer renderer and the outer bevel honours the same controls.
- The Bevel dialog panel exposes all of these.

================================================================================

## [4.2.7.13] - 2026-06-05

Build 2 phase 2 (slice 13): blending / opacity correctness.

### Fixed
- **An object's Blending mode was ignored whenever the object had any layer
  effect.** The body was blended against an empty internal buffer instead of the
  real canvas, so multiply / screen / etc. did nothing on shapes, curves or text
  that also had effects. The object is now composited onto the actual background
  with its blend mode (and shadows/below-effects underneath it).

### Notes
- Verified the Photoshop semantics: **Opacity** fades the whole layer (object +
  effects); **Fill opacity** fades only the object pixels while effects (drop
  shadow, glow, ...) stay at full strength.

================================================================================

## [4.2.7.12] - 2026-06-05

Build 2 phase 2 (slice 12): rich Chromatic Aberration.

### Added
- **Chromatic Aberration is now fully per-channel.** Each of the R / G / B
  channels has its own **colour**, and either its own **offset + angle**
  (linear mode) or its own **radial distortion %** (radial / lens mode). A
  Mode switch chooses linear vs radial. Defaults reproduce the classic split.

### Changed
- File format schema -> 4.2.10 (added the per-channel CA fields; older files load).

================================================================================

## [4.2.7.11] - 2026-06-05

Build 2 phase 2 (slice 11): smooth Long Shadow soft-linear blur.

### Changed
- **Long Shadow soft "linear" ramp is now smooth.** It previously blurred in 6
  discrete distance bands, leaving visible steps; it now uses a continuous
  graduated blur (interpolating between a few pre-blurred copies by a distance
  gradient), so the blur grows seamlessly along the throw.

================================================================================

## [4.2.7.10] - 2026-06-05

Build 2 phase 2 (slice 10): mm fields become sliders, Long Shadow taper + soft mode.

### Added
- **mm fields in the effects dialog are now slider + number + adjustable max**
  (shadow distance/size, glow size, bevel size, stroke size, long-shadow length,
  halftone spacing). Drag the slider, type an exact value, or raise the "≤ max"
  box to go past the default cap.
- **Long Shadow — Taper (0-200%, 100% = uniform):** progressively narrows
  (towards 0%) or widens (towards 200%) the shadow along its throw.
- **Long Shadow — Soft mode:** the shadow blurs along the throw, with a ramp of
  `linear` (blur grows with distance) or `constant` (uniform soft blur), plus a
  "Soft blur size" control.

### Changed
- File format schema -> 4.2.9 (added ls_taper, ls_mode, ls_blur_mode; older files
  load fine).

================================================================================

## [4.2.7.9] - 2026-06-05

Build 2 phase 2 (slice 9): effects dialog reworked to an instance list
(multiple effects of one type, duplication, drag-to-reorder).

### Added
- **Multiple instances per effect type.** The Layer Style list is now a list of
  effect *instances* (e.g. two Drop Shadows), shown as "Drop Shadow 1",
  "Drop Shadow 2", ...
- **＋ Add** (menu of every effect type, can add the same type repeatedly),
  **⧉ Duplicate** (copies the selected effect right below it), and
  **－ Remove** buttons.
- **Drag to reorder** effects in the list — this is the render/stacking order.
  Blending Options stays pinned at the top and is not movable.

### Changed
- Effects are now collected and rendered in the list's order, allowing fine
  control over which effect sits on top.

================================================================================

## [4.2.7.8] - 2026-06-05

Build 2 phase 2 (slice 8): Photoshop-style Spread / Choke for shadows and glows.

### Added
- **Spread** (Drop Shadow, Outer Glow) / **Choke** (Inner Shadow, Inner Glow),
  exactly like Photoshop: it expands (or, for inner effects, chokes) the solid
  matte before the blur. At 0% you get the usual soft edge; at 100% the soft
  edge collapses into a hard, stroke-like outline. Controlled by a new `spread`
  field on layer effects.

### Changed
- File format schema -> 4.2.8 (added the `spread` field; older files load fine,
  new files carry it).

================================================================================

## [4.2.7.7] - 2026-06-05

Build 2 phase 2 (slice 7): the four newer effects are now in the Layer Style dialog.

### Added
- **Long Shadow**, **Chromatic Aberration**, **Halftone** and **Light Sweep**
  are now selectable in the Layer Style (effects) dialog with full parameter
  panels (they already rendered; now they can be added and tuned from the UI):
  - Long Shadow: blend, opacity, color, angle, length, fade-out toggle.
  - Chromatic Aberration: opacity, offset, angle.
  - Halftone: blend, opacity, color, dot/line spacing, angle, shape (dot/line).
  - Light Sweep: blend, opacity, light colour, position, width, angle.

================================================================================

## [4.2.7.6] - 2026-06-05

Build 2 phase 2 (slice 6): effects dialog modernization (visual pass).

### Changed
- **Layer Style (effects) dialog restyled** for a cleaner, more modern look:
  card-style panels and effect list with rounded corners, an accent-highlighted
  selection, hover states, restyled sliders, and more breathing room (larger
  default window). Structure and functionality unchanged. Deeper changes
  (per-effect descriptions, right-panel de-duplication, drag-to-reorder /
  duplicate / remove, and the blending/opacity logic) come next.

================================================================================

## [4.2.7.5] - 2026-06-05

Build 2 phase 2 (slice 5): more UI icons.

### Added
- UI icons on the text formatting toolbar: bold, italic, underline,
  strikethrough, and align left / center / right.

================================================================================

## [4.2.7.4] - 2026-06-05

Build 2 phase 2 (slice 4): coloured icons + text toolbar at the top.

### Changed
- **UI toolbar icons keep their original colours** (the previous build wrongly
  flattened them to a grey tint).
- **The text formatting toolbar is now always pinned to the top** of the canvas
  (Word-style ribbon, like document mode), instead of floating squished above
  the textbox.

================================================================================

## [4.2.7.3] - 2026-06-05

Build 2 phase 2 (slice 3): UI icons on the main toolbar + cursor refinements.

### Added
- **Custom UI icons on the main toolbar** (new, open, save, undo, redo, select,
  hand, text, image, rect, ellipse, line, qr, table, pen, zoom-in, zoom-out,
  fit, duplicate, delete, export), from the bundled icon set. Dark artwork is
  recoloured to a light tint so it is visible on the dark toolbar; buttons with
  no matching icon keep their text/emoji label.

### Changed
- Per-corner rectangle radii: the label is now English ("Corners (mm)") and the
  four fields are laid out in two rows (TL / TR on top, BL / BR below) so they
  no longer get squeezed.
- Cursor refinements: resize cursors now follow the object's rotation; path
  point-editing shows tangent / move / add-point / remove-point cursors; the
  pen tool shows a close cursor near the first point; custom cursors scaled down
  so they are not oversized.

================================================================================

## [4.2.7.2] - 2026-06-05

Build 2 phase 2 (slice 2): custom tool cursors. Also carries the 4.2.7.1 work
(per-corner rectangle radii + the rounded-rect stroke-clipping fix).

### Added
- **Custom tool cursors.** The canvas cursor now changes by tool and by what is
  under the pointer, using a bundled cursor set (move, pen, tangent, resize
  NWSE/NESW/NS/EW, rotate, hand / hand-grab, crosshair, not-allowed, ...) loaded
  from `cursors.json` with per-cursor hotspots. Falls back to the native Qt
  cursor if an asset is missing.
- Bundled the cursor and UI-icon asset sets into the package
  (`edof/_apps/assets/cursors`, `edof/_apps/assets/ui_icons`). Wiring the UI
  icons into the toolbars/panels comes next.

================================================================================

## [4.2.7.1] - 2026-06-05

Build 2 phase 2 (slice 1): effects coverage. More of phase 2 (effects dialog
modernization + right-panel cleanup, blending/opacity logic, drag-drop reorder,
custom cursors, live draw preview) follows in 4.2.7.2+.

### Added
- **Layer Effects are now available for QR codes and for lines** (and confirmed
  working for shapes / curves). Effects already rendered for any object; the
  entry point was simply missing from the QR and line property panels. Effects
  follow the object's real alpha, so a QR whose background colour is made
  transparent casts its shadow / glow / bevel from the modules only.

================================================================================

## [4.2.7.0] - 2026-06-05

Build 2 (phase 1) of the editor roadmap: layer-effect model + file versioning.
The new effects render and are fully controllable programmatically; the editor
UI to add / reorder / duplicate them (and the richer bevel controls) lands in
4.2.7.1.

### Added
- **Four new layer effects** (Photoshop does not have these as one-click,
  non-destructive effects):
  - **Long Shadow** — flat-design shadow thrown along a direction for a set
    length, optional fade.
  - **Chromatic Aberration** — RGB channel split for a glitch / retro look.
  - **Halftone** — luminance dot (or line) screen clipped to the object.
  - **Light Sweep** — glossy diagonal specular streak.
- **Extended bevel model** towards Photoshop parity: technique
  (smooth / chisel hard / chisel soft), depth, direction (up / down), soften,
  altitude, and separate highlight / shadow opacity. (These ship in the schema
  now; the richer bevel *rendering* and UI controls come in 4.2.7.1.)
- **File versioning**: every saved `.edof` now records `writer_version` (the
  exact library version that wrote it) alongside `edof_version` (the format /
  schema version). The schema version is bumped to **4.2.7** because the effect
  schema grew.

### Changed
- File format (schema) version: 4.2.0 -> 4.2.7. The change is additive
  (new optional effect fields), so older 4.2.x readers still open new files and
  new readers open old files.

================================================================================

## [4.2.6.0] - 2026-06-05

Build 1 of the editor roadmap: curve (path) editing.

### Fixed
- **Path handles keep a constant on-screen size at any zoom** and no longer
  grow or look pixelated when you zoom in; their outlines stay crisp (1–2 px).
- **Dragging multiple selected anchors now moves their tangent handles too**, so
  a group move keeps the curve shape instead of leaving tangents behind.

### Added
- **Grid snapping and Photoshop-style modifiers while dragging path points**
  (anchors and tangents):
  - no modifier: snap to the grid (when grid snap is on),
  - Ctrl: no snapping,
  - Shift: constrain to 0 / 45 / 90 degrees from the drag start (with snap),
  - Ctrl+Shift: constrain without snapping.

================================================================================

## [4.2.5] - 2026-06-05

### Fixed
- **New Document now respects the size and DPI you type.** The width / height /
  DPI fields are the single source of truth: picking a preset (A4, Full HD, ...)
  just fills those fields, and the document is always created from the fields.
  Previously, if a preset row stayed selected, the typed width / height / DPI
  were ignored and you got the preset size (usually A4).
- **Custom DPI is respected.** Once you set a DPI in New Document, picking a
  preset no longer overwrites it, and the DPI range is widened (1–9600).
- **Millimetre fields now keep 0.01 mm precision and no longer jump by 0.5 mm.**
  The geometry fields step by 0.1 mm on the arrows (was 0.5 mm) and accept two
  decimals; fields that rounded to 0.1 mm (corner radius, table border, layer
  effect sizes/distances) now keep hundredths too. Canvas snapping is unchanged.

### Changed
- The documentation version (docs landing page) is now generated from the
  package version automatically, so it never goes stale.

================================================================================

## [4.2.4] - 2026-06-05

### Fixed
- **The Editor and Viewer now show the EDOF icon in the Windows taskbar**
  (instead of the Python interpreter's icon). Each app sets its own
  AppUserModelID at startup and an application-level window icon.
- **File association now always records an absolute path to the real launcher**
  and never a `.bat`/`.cmd`. Previously the resolver could pick up a launcher
  `edof-viewer.bat` from the current directory and register it with a relative
  path (`.\edof-viewer.BAT`), which has no icon and fails on double-click. It
  now prefers `edof-viewer.exe` / `edof-editor.exe` next to the interpreter,
  rejects batch files, and falls back to `pythonw -m ...` with absolute paths.

### Changed
- `edof-editor` and `edof-viewer` are now GUI entry points (no console window
  flashes on launch); `edof-cli` stays a console command.

================================================================================

## [4.2.3] - 2026-06-05

### Changed
- **You now choose the default opener inside EDOF, not in the OS dialog.** The
  "File association (.edof)" dialog (in both the Editor and the Viewer) lets you
  pick whether double-clicking a `.edof` file opens the **Viewer** or the
  **Editor**, and registers that choice as the default. The other app stays
  available via right-click → Open With, and files keep the EDOF icon. The same
  choice is available on the command line: `edof-cli associate-files --app
  editor` (or `--app viewer`, the default). In 4.2.2 the OS prompted you to pick
  on first open; now the choice is made in the app.

================================================================================

## [4.2.2] - 2026-06-05

Bug-fix release with application/document icons.

### Fixed
- **Centre (and other) paragraph alignment is no longer lost on save or on
  Word export.** `TextRun` now serializes its `alignment`, and the body sync
  promotes run-carried alignment onto `Paragraph.alignment`, so the chosen
  alignment survives the `.edof` round-trip and is picked up by `export_docx`.
- **Ctrl+S / Ctrl+Shift+S now work while typing in the body editor.** They are
  routed to the window's Save / Save As; previously Ctrl+S did nothing inside
  the inline editor and Ctrl+Shift+S toggled strikethrough instead of Save As.
- **File association no longer errors with "cannot unpack NoneType".** The
  associate / unassociate functions now return `(ok, message)`.
- Removed an unsupported `outline` property from the stylesheet that caused
  repeated "Could not parse stylesheet of object ..." console warnings.

### Added
- **Icons.** The Editor and Viewer windows now use their own icons, `.edof`
  files show a document icon in Explorer, and the Viewer / Editor appear with
  their own icons under "Open with". Icons ship inside the package
  (`edof/_apps/assets/icons/`, `.ico` + `.png` + `.icns` for Windows / Linux /
  macOS).
- **File association** that registers the Viewer and the Editor as open-with
  choices and gives `.edof` files the EDOF icon. The Viewer gained a
  register / remove toggle and **File → Open in Editor (Ctrl+E)**.

================================================================================

## [4.2.1] - 2026-06-04

Follow-up to 4.2.0 (which was already published to PyPI, where versions are
immutable, so these ship in a new version).

### Fixed
- `edof._apps.viewer` now imports without PyQt6 installed (it falls back to a
  harmless base class and `main()` prints an install hint), so the CI test
  suite passes on the lean `[dev,qr]` install instead of erroring on import.

### Added
- Ko-fi funding links (`https://ko-fi.com/davidschobl`): `.github/FUNDING.yml`,
  the `Funding` project URL, the README, and the in-app "Support the
  developer" action and About dialogs (alongside GitHub Sponsors).

### Packaging
- `deploy-edof.bat` / `deploy-edof.sh` default the deploy clone to a directory
  next to the script (the unzipped package) instead of a hard-coded developer
  path.

================================================================================

## [4.2.0] - 2026-06-04

First public release since 4.0.3. It folds in a long line of editor and
format work developed in between, so the highlights below cover everything
new since 4.0.3.

### Added
- **Word (.docx) import and export** (optional, needs `python-docx`:
  `pip install edof[docx]`). New top-level API `edof.export_docx(doc, path)`
  and `edof.import_docx(path, return_report=False)`, plus **File → Import /
  Export Word (.docx)…** in the desktop editor.
  - Export writes the document body flow: runs with bold / italic / underline
    / strikethrough, font family and size, run colour, paragraph alignment,
    page size and margins, page-break-before, single-level lists, and a line
    height matched **exactly** to EDOF's so Word paginates the same way the
    editor does.
  - Import builds a document-mode file and produces a compatibility report.
    It never silently drops content: tables, images, drawings, text boxes,
    equations and embedded objects are detected and the user is advised
    against importing when such content is significant; headers/footers,
    footnotes and comments are reported as dropped. See
    `docs/reference/11-docx.md`.
- **Unified document-wide undo/redo.** A single timeline now covers both
  body-text editing and object operations (move / add / delete / style).
  Body edits coalesce into one step per typing burst and are flushed before
  any undo/redo or object change, so Ctrl+Z/Ctrl+Y behave consistently
  everywhere and never split between two histories.
- **Document mode** maturity: continuous multi-page text flow with automatic
  pagination, hard page breaks (Ctrl+Enter), per-paragraph keep/break
  controls, and per-run/paragraph line spacing.
- Complete generated **API reference** (`docs/reference/API.md`) and a
  MkDocs-Material documentation site published to GitHub Pages.
- **Read-only Viewer** (`edof-viewer`) and OS-level **file associations** for
  `.edof` (open by double-click; register from the editor, the viewer, or
  `edof-cli associate-files`).
- **Document mode**: a continuous, multi-page text flow you can edit like a
  word processor, alongside the free-form object canvas.
- **Layer effects** (Photoshop-style), **per-side padding** on text boxes, and
  a **bezier path tool**.
- **Table editor UI** (tables remain experimental / a work in progress).

### Changed
- **Debug logging is now opt-in.** It is disabled by default and only writes a
  log when `EDOF_DEBUG=1` is set or it is enabled programmatically;
  `EDOF_DEBUG_PATH` overrides the location. Releases no longer create
  `edof_debug.log` in the home directory during normal use.
- Line-height model on export uses an exact point value (not Word's "multiple"
  rule), eliminating the ~15 % taller spacing that pushed extra lines onto
  later pages.

### Fixed
- Pagination: hard page breaks and empty break-pages survive re-pagination;
  the caret no longer drops below the bottom margin while typing at the end of
  a full page; the empty-document caret respects paragraph alignment;
  continuing pages no longer render a spurious trailing cursor line.
- Close / New / Open now prompt to save unsaved body edits, including edits
  made on a single line that previously failed to mark the document modified.
- New documents no longer capture the editor's placeholder hint into undo
  history, so undoing to the very start leaves a clean empty document.

### Packaging
- Clean release tree (no build/debug helpers or caches); restored the
  `.github/workflows/publish.yml` Trusted-Publishing (OIDC) workflow; added a
  `Funding` project URL and a `.gitignore`.

================================================================================

## [4.0.3] - 2026-05-04

The "editor catches up with the API" release. Substantial editor improvements,
PDF import bug fixes, RTF import/export, and a long list of polish.
No format changes — files saved by 4.0.3 are wire-compatible with 4.0.2.

================================================================================
FIXED — PDF import: vector paths had wrong bounding box
================================================================================

Previously, vector paths (lines, curves, rectangles) imported from PDF were
created with a transform spanning the entire page, while the path coordinates
themselves were absolute. The renderer worked, but the editor couldn't select
or move them — the bounding box covered the whole page.

In 4.0.3:
- `_extract_paths()` now computes the actual bbox of each path
- Path coordinates are stored as local (relative to transform.x/y)
- The renderer auto-detects local vs absolute coords for backward compatibility
  with documents created before this fix

Also added new flags to `import_pdf()`:
- `extract_paths` (default True): convert PDF vector paths to Shape objects
- `extract_images` (default True): extract embedded raster images

These flags were promised in the 4.0.2 docs but were not actually wired up.

================================================================================
FIXED — Image scale X breaks position
================================================================================

When resizing an ImageBox by dragging an edge handle (only one axis), the
opposite anchor was not held fixed, causing the image to "jump" sideways. The
resize now correctly keeps the opposite corner / edge as the anchor regardless
of which handle you drag.

================================================================================
FIXED — Subpixel text rendering disappears at low zoom
================================================================================

When zoomed below 100%, thin text strokes on the canvas would render at
sub-pixel widths and disappear into anti-aliasing — the text became unreadable.

In 4.0.3, the editor canvas renders at higher DPI when zoomed out (up to 2×)
and downscales with LANCZOS, so thin strokes survive. This affects only the
canvas preview; export quality is unchanged.

================================================================================
CHANGED — Modifier semantics for resize/rotation/move
================================================================================

The editor's modifier behaviors were inconsistent and didn't match user
expectations. Revised in 4.0.3:

- **Ctrl** while dragging — bypass ALL snapping (grid, alignment guides, margins).
  This is the primary "give me precise control" modifier.
- **Alt** while dragging — bypass snapping (legacy alias for Ctrl, kept for
  compatibility).
- **Shift on resize** — toggles uniform/non-uniform scale:
  - For ImageBox: default is uniform (preserve aspect ratio); Shift toggles
    to non-uniform.
  - For other objects: default is non-uniform; Shift forces uniform.
- **Shift on rotation** — snap to 15° increments.

This means typical workflows do the right thing automatically:
- Drag image corner → preserves aspect ratio
- Drag image corner with Shift → free distortion if you really want it
- Drag rectangle corner → free resize
- Drag rectangle corner with Shift → preserve aspect ratio

================================================================================
ADDED — Page margins (per-document) with snap support
================================================================================

Documents now have an optional `doc.margins` field — a 4-tuple of
(top, right, bottom, left) in mm. Margins are saved/loaded with the document.

In the editor:
- View menu → "Use Page Margins (snap)" toggle
- View menu → "Set Margins…" dialog
- When enabled, dragged objects snap their edges to the margin lines

Margins are editor-only — they're not enforced at render or export.

================================================================================
ADDED — Editor: Insert Table dialog
================================================================================

Tables existed in the API since 4.0.0 but had no UI to create them. Insert
Table dialog now offers:
- Rows × columns
- Width × height in mm
- Optional header (first row in bold + accent color)
- Optional alternating row colors

================================================================================
ADDED — Editor: Path drawing tool
================================================================================

A new toolbar button (✎) puts the canvas in path-drawing mode:
- Click adds a point
- Double-click or Enter finishes the path
- Esc cancels
- Snap-to-grid is honored if enabled

The result is a `Shape(shape_type="path")` with proper local coordinates and
correct bounding box.

================================================================================
ADDED — Editor: Object panel rename, drag-and-drop, context menu
================================================================================

The left-side object list panel was bare-bones. Now:

- **F2** or **double-click** an item to rename the object inline
- **Drag** items up/down to reorder layers (front-to-back ordering)
- **Right-click** an item for: Rename, Bring to Front, Bring Forward,
  Send Backward, Send to Back, Show/Hide, Lock/Unlock, Duplicate, Delete

Also fixed a dark-theme rendering bug where alternating row colors were too
bright; the panel now uses a quieter selected-state highlight.

================================================================================
ADDED — Editor: Properties panel — Advanced section
================================================================================

A new "Advanced" group on the right-side properties panel exposes API-level
features that previously had no UI:

- **Show if** (`visible_if` expression) — conditional visibility
- **Lock level** dropdown (none / fill / edit / design / admin) — for
  permission-aware editing of encrypted templates
- **Lock text** checkbox — prevents changes to text content even when the
  object itself is editable
- **Blend mode** dropdown (normal / multiply / screen / darken / lighten / overlay)
- **Shape type** changer — convert rect ↔ ellipse ↔ polygon ↔ path on the fly
- **Drop shadow** — toggle + offset X/Y + blur

================================================================================
ADDED — Editor: Help → Keyboard Shortcuts dialog
================================================================================

F1 now opens a comprehensive reference dialog covering File, Edit, View,
Insert, Document, Selection, Modifier keys (with the new v4.0.3 semantics),
Object panel actions, and the Path tool.

Help → About also added.

================================================================================
ADDED — Editor: PDF Export dialog with Vector / Raster choice
================================================================================

The PDF export menu item now opens a dialog explaining the trade-off:
- **Vector PDF** (default): pure-Python writer, smaller files, selectable text,
  limited to Standard 14 PDF fonts
- **Raster PDF**: rendered as bitmap, larger files, no text selection,
  supports any TTF font, requires reportlab

Plus a DPI control for raster mode.

================================================================================
ADDED — Editor: Resizable docks + persistence
================================================================================

The left and right panels were previously fixed-width. Now:
- Both docks are user-resizable
- Both are dockable (movable, can detach to floating)
- Geometry, snap-to-grid state, alignment guides state, margin state, and
  full window/dock layout persist across sessions (via `QSettings`)
- View menu → "Reset Panel Layout" to restore defaults

================================================================================
ADDED — Editor: Toolbar tooltips
================================================================================

Every toolbar button now has a descriptive tooltip + status-bar message +
keyboard shortcut hint. Previously hovering "💾" gave no explanation; now it
shows "Save (Ctrl+S)".

================================================================================
ADDED — RTF import / export
================================================================================

A new utility module (`edof.utils.rtf`) provides best-effort interop with
Rich Text Format documents:

- `edof.import_rtf(path)` reads an RTF file into an EDOF Document. Each
  non-empty paragraph becomes a TextBox; runs preserve bold/italic/underline/
  size/color. Tables, images, lists, fields are not supported.
- `doc.export_rtf(path)` writes an EDOF document as flat RTF — paragraphs in
  vertical order, runs with formatting. Other object types (shapes, images,
  tables) are not exported.

In the editor:
- File → Import RTF…
- File → Export RTF…

================================================================================
DOCUMENTATION
================================================================================

- Documentation site at https://davidschobl.github.io/edof/ updated for 4.0.3
- Editor reference page (`docs/reference/08-editor.md`) updated with
  v4.0.3 modifier semantics, margins, panel persistence
- New "Path tool" section in editor docs

================================================================================
TESTS
================================================================================

138/138 tests passing (vs 112 in 4.0.2):
- 36 v3.1 (legacy)
- 36 v4.0
- 21 v4.0.1
- 19 v4.0.2
- 26 v4.0.3 (new)

================================================================================

## [4.0.2] - 2026-05-04

Polish, bug fixes, and CLI completeness release. No format changes — files saved by 4.0.2 are bit-identical to 4.0.1 when no 4.0.2-only behaviors are exercised.

================================================================================
FIXED — Variable `{name}` placeholder substitution at render time
================================================================================

Previously, `{name}` placeholders inside `obj.text` were only substituted by `repeat_objects()`. Direct rendering (`doc.export_pdf()`, `doc.export_bitmap()`, `doc.export_svg()`) left placeholders as literal text. Documentation and examples in 4.0.1 promised this worked — now it actually does.

Behaviour:
- `obj.text = "Hello {name}!"` with `doc.set_variable("name", "Alice")` now renders as "Hello Alice!".
- Multiple placeholders supported: `"{greeting} {name}"`.
- Undefined variable names stay as literal `{name}` (graceful fallback, no exception).
- Table cell substitution (which already worked) is unchanged.
- The previous mechanism of binding a textbox to a single variable via `obj.variable = "name"` continues to work and takes priority.

================================================================================
FIXED — Editor: snap-to-grid during resize and rotation
================================================================================

When **Snap to Grid** (Ctrl+G) was enabled in 4.0.1, snapping only applied while moving objects. Resize handles (non-uniform scale corner / edge dragging) and rotation handles ignored the setting.

In 4.0.2:
- **Resize**: when grid snap is active and the object is non-rotated, the mouse position is snapped to the 5mm grid before computing the new size, so resize ends on grid increments. Rotated objects skip this (snapping along rotated axes is unintuitive). Hold **Alt** to bypass.
- **Rotation**: when grid snap is active, rotation now snaps to 15° increments by default (the same behaviour you previously got only by holding Shift). Hold **Alt** to bypass.

================================================================================
ADDED — Editor settings persistence (Windows / Linux / macOS)
================================================================================

The editor now uses `QSettings` to remember preferences across sessions:

- Window geometry (size + position)
- Snap-to-grid on/off
- Show alignment guides on/off
- Recent files list (up to 10)

Settings live in standard system locations (registry on Windows, `~/.config/edof/editor.conf` on Linux, `~/Library/Preferences/edof.plist` on macOS). Delete to reset.

================================================================================
ADDED — Validate enhancements
================================================================================

`doc.validate()` now also reports:
- **Duplicate object IDs** anywhere in the document (recursing into groups). Useful when programmatically copying objects without resetting `obj.id`.
- **Objects positioned entirely off-page** (i.e. their bounding box has no overlap with the page). Partially-off objects (overlapping the edge) are NOT flagged — that's a deliberate design choice (e.g. bleed marks).

These join the existing checks for missing-resource references, undefined variable references, and unset required variables. The function still returns an empty list when the document is fully valid.

================================================================================
ADDED — CLI: 6 new subcommands + password support on existing ones
================================================================================

The CLI now exposes the rest of the public API. New subcommands:

- `edof-cli batch <template> <csv> -o <pattern>` — generate one output file per CSV row, auto-filling variables. Supports `{n}`, `{column}` in output pattern; `--start`, `--limit`, `--continue-on-error`. Accepts PDF/PNG/JPEG/SVG output formats.
- `edof-cli import <pdf> -o <edof>` — convert a PDF to an editable .edof (best-effort PDF reconstruction, requires `[pdf]` extra). `--no-tables`, `--no-images`, `--no-paths`, `--heading-threshold` flags.
- `edof-cli convert <input> -o <output>` — migrate any legacy archive to current v4 format.
- `edof-cli to-v3 <input> -o <output>` — save as v3-compatible (lossy: tables flatten, runs collapse, paths sample, gradients average).
- `edof-cli set-password <input> --level admin --password <pwd>` — manage encryption from the command line. Supports `--remove`, `--clear-all`, `--current-password`, `--recovery-key`. Recovery key is shown once on first password.
- `edof-cli unlock-render <encrypted> <out.pdf> --password <pwd>` — decrypt + render in one step. The decrypted document is never written to disk.

Existing commands (`info`, `objects`, `validate`, `export`) gained:
- `--password` / `--recovery-key` flags for working with encrypted templates.
- `--vector` / `--raster` flags on PDF export.
- SVG output support on `export` (auto-detected from `.svg` extension or via `--format svg`).

`info` on an encrypted file without a password now shows public manifest data (encryption mode, permission levels, KDF parameters) instead of failing.

Exit codes are now consistent with the documentation:
- `0` success
- `1` usage error
- `2` file not found
- `3` encryption error (wrong password / missing crypto extra)
- `4` validation failure
- `5` unknown internal error

================================================================================
DOCUMENTATION
================================================================================

Comprehensive documentation added under `docs/`. Covers every public symbol with signatures, examples, and conventions. Hosted on GitHub Pages at https://davidschobl.github.io/edof/ (after the deploy below). Includes:

- Installation, quick start, and conventions
- Full API reference (Document, Page, all object types, styles, variables, export, import, encryption, editor, CLI, helpers)
- Five cookbook recipes (certificate, invoice, batch PDF, encrypted template, PDF import)
- Advanced topics (file format internals, extending, troubleshooting)

`pyproject.toml` now declares `[project.urls]` (Documentation, Repository, Changelog, Issues), which appear on the PyPI project page.

The README badges and content link to the documentation site.

================================================================================

## [4.0.1] - 2026-05-04

Maintenance + protection release. Adds AES-256 encryption, multi-level password protection, real (not XOR) document security, plus editor enhancements.

================================================================================
ADDED — Encryption & multi-level password protection
================================================================================

This is the headline feature for 4.0.1.

By default, documents remain plain (no encryption, no friction — same as 4.0.0). When an admin password is set, the document switches to encrypted mode on the next save. Encryption requires the optional `cryptography` extra: `pip install edof[crypto]`.

**Cryptography**
- AES-256-GCM authenticated encryption for content
- PBKDF2-SHA256 key derivation with 600,000 iterations
- 16-byte random salt per slot, 12-byte random nonce per ciphertext
- GCM authentication tag detects tampering on load
- Real protection: no XOR, no obfuscation theatre

**Permission levels (hierarchical)**
- `view`   — render, print, export. No modifications.
- `fill`   — view + change variable values (template filling). No structural / textual edits.
- `edit`   — fill + change object .text content (and rich-text run text segments).
- `design` — edit + change styles, layout, add / remove objects and pages.
- `admin`  — design + manage passwords, recovery keys, lock_level overrides.

Higher levels imply all lower levels.

**Multi-slot key wrapping**
- Each password independently wraps the same 32-byte content key.
- Setting an `admin` password also generates a 24-character alphanumeric recovery key.
- The recovery key is shown exactly once at first password setup; it cannot be retrieved later.
- Recovery key always grants ADMIN; designed for owner self-recovery.
- Changing one password does not re-encrypt the bulk payload (just rewraps that one slot).

**Encryption modes**
- `full`    — entire document content (and resources) encrypted as a single AES blob inside the ZIP. Manifest leaks only KDF parameters and slot count. Title, page count, all metadata are hidden.
- `partial` — only sensitive content fields encrypted (text content, rich-text runs, image data, QR data, table cell text). Structure (positions, sizes, fonts, alignment, page count, title) remains visible. Useful for "design template" sharing where layout is public but content is private.
- `none`    — current 4.0 behaviour, plain ZIP, no encryption.

In partial mode without a password, the document loads with redacted content (a placeholder character `█` replaces text). The user can see the layout and structure but no content. With a password, the full content is decrypted and accessible.

**Per-object locks (independent of doc-level encryption)**
- `obj.lock_level = "design"` — modifying this object requires at least the named permission, regardless of the user's general permission level.
- `obj.lock_text = True` — hard text lock; even ADMIN cannot edit `.text` or `.runs` until clearing this flag (which itself requires ADMIN).
- `obj.can_modify(doc) -> bool` — programmatic check.
- `obj.can_modify_text(doc) -> bool` — also honors `lock_text`.

**Document API**
```python
rk = doc.set_password("admin", "mySecret123")
doc.set_password("design", "designerPwd")
doc.set_password("edit",   "editorPwd")
doc.set_password("fill",   "templateFiller")

doc.encryption_mode = "partial"   # or "full" (default after first password)
doc.save("template.edof")

doc = edof.load("template.edof", password="editorPwd")
print(doc.permission_level)   # Permission.EDIT
doc.can(edof.crypto.DESIGN)   # False
doc.require(edof.crypto.EDIT) # OK, no exception

doc.change_password("edit", "old", "new")   # rotate without re-encrypting payload
doc.remove_password("fill")                 # requires ADMIN
doc.clear_all_protection()                  # requires ADMIN

doc = edof.load("template.edof", recovery_key="ABCD-EFGH-...")  # recovers as ADMIN
```

**Editor UI**
- File → Open: detects encrypted files automatically and prompts for password / recovery key. Three-strikes-and-out; Cancel on any prompt aborts the open.
- Document → Unlock for editing… (Ctrl+Shift+L): shows password prompt when an encrypted document was opened with insufficient privileges, then displays a dialog listing exactly what the granted level can and cannot do.
- Document → Protection… : full management UI for setting / changing / removing passwords and switching between full and partial encryption modes. Confirmation dialog before plain → encrypted upgrade.
- Document → Re-lock: forgets the cached content key for the session.
- Status bar shows protection state at all times: 🔓 Plain / 🔒 Locked / 🔓 Unlocked: <level>.
- Permission-aware action gating: pressing a button (Add TextBox, Delete, Duplicate, etc.) without sufficient permission shows a clear dialog explaining what level is needed.
- Canvas drag respects `obj.can_modify()`; locked objects cannot be moved.
- Recovery key dialog uses fixed-width font, clipboard copy button, "I have saved this key" confirmation gate.

**EDOF 2 → 4 password upgrade flow**
- When opening a legacy EDOF 2 archive that had an XOR-obfuscated password, the editor offers to set up real AES-256 encryption with a clear explanation of why the old password was insecure.

================================================================================
ADDED — Editor improvements (carry-over completed in 4.0.1)
================================================================================

- Snap-to-grid: View → Snap to Grid (Ctrl+G), 5 mm grid, hold Alt to bypass.
- Alignment guides: View → Show Alignment Guides; magnetic snap to other objects' edges and centers during drag, threshold 1.5 mm.
- Multi-select: Ctrl+click adds / removes from selection; group drag moves all selected objects together; group delete removes them all.
- Cursor position in mm in the status bar (live during mouse move).
- Find & Replace dialog (Ctrl+F): searches all TextBoxes on all pages, with case-sensitive and regex options.
- Gradient Editor dialog: visual stop list, add/remove/recolor stops, switch between linear and radial.
- Template gallery (File → New from Template…): Blank A4 P/L, Business Card, Certificate, Invoice with Table.
- File → Save as v3 (downgrade)…: produces a v3-compatible .edof with all v4-only features flattened.
- File → Import PDF…
- File → Export SVG…

================================================================================
ADDED — `doc.export_3x(path)` API
================================================================================

Programmatic API for downgrading a v4 document to v3 format.

Best-effort lossy conversion:
- Tables flattened to a Group of TextBoxes plus line shapes for borders.
- Rich-text runs collapsed to plain `obj.text` (formatting lost).
- Path shapes rasterised to polygon shapes (Beziers sampled at 12 segments per curve).
- Gradients replaced with the average color of their stops.
- `visible_if` evaluated once at export time and baked into `.visible`.
- `blend_mode` reset to `"normal"`.

The original document is not mutated; a deep copy is made first. Manifest in the output explicitly says `format_version: 3.1.0` so v3 readers don't show a "newer version" warning.

```python
doc.export_3x("for_v3_users.edof")
```

================================================================================
ADDED — Real EDOF 2 import (`edof/utils/legacy_v2.py`)
================================================================================

Replaces the placeholder scaffolding from 4.0.0 with a complete migration path based on the actual EDOF 2 schema (versions ≤ 2.2):

- ZIP with `data.json` at root (no manifest).
- Float `version` field (e.g. `2.2`).
- ARGB hex colors `#AARRGGBB` correctly converted to v4 RGB tuples (alpha dropped, RGB preserved — alpha is not part of TextStyle.color in v4).
- `font_weight ≥ 600` → `bold = True`.
- `max_font_size_pt > font_point_size` → `auto_shrink = True`, `font_size = max`.
- `h_align` / `v_align` mapped to v4 `alignment` / `vertical_align`.
- Embedded images extracted from the `images/` directory and added as v4 resources with detected MIME type.
- `z_value` → `layer` (preserves stacking order).
- `allow_non_uniform_scale` → `fit_mode = "stretch"` or `"contain"`.
- `edit_mode` other than "all" → informational warning in `doc.errors`.
- `edit_password_xor` → ignored, with explicit warning that XOR provided no real security; editor offers to set up real AES encryption.

Auto-detection: `edof.load(path)` checks for v2 markers (`data.json` at root, version < 3.0, no `manifest.json`) and routes to the legacy loader transparently.

================================================================================
ADDED — Optional dependency
================================================================================

```toml
[project.optional-dependencies]
crypto = ["cryptography>=42.0"]
all    = [..., "cryptography>=42.0"]
```

Encryption is opt-in. Without `cryptography` installed, all plain-mode functionality continues to work; only `set_password()` and friends raise `EdofCryptoUnavailable` with installation instructions.

================================================================================
FILE FORMAT
================================================================================

- Format version bumped to 4.0.1.
- New optional `protection` block in the manifest:
```json
{
  "protection": {
    "mode": "full" | "partial",
    "format": "edof-aes-256-gcm-v1",
    "slots": [
      {"permission": "fill", "kdf": "pbkdf2-sha256", "iterations": 600000,
       "salt": "<base64>", "wrapped_key": "<base64>"},
      ...
    ]
  }
}
```
- New file inside encrypted archives: `encrypted_payload.bin` (AES-GCM ciphertext: 12 B nonce || 16 B GCM tag || ciphertext).
- 4.0.0 files load unchanged (mode defaults to "none").
- Plain 4.0.1 files are bit-identical to 4.0.0 format.

================================================================================
SECURITY MODEL
================================================================================

What encryption protects against:
- Reading content without a password
- Detection of any tampering with the ciphertext
- Brute-forcing weak passwords (PBKDF2 with 600k iterations is intentionally slow)

What it does NOT protect against:
- A user with sufficient access running their own decryption code (they have the password)
- Side-channel attacks on the host (memory dumps, keyloggers, etc.)
- Loss of all passwords AND the recovery key — the document is mathematically unrecoverable
- A malicious EDOF library — verify the source

Recovery key is treated as an additional ADMIN-level slot keyed by the recovery string. If you lose it, the only way to regenerate one is to remove all passwords and re-protect the document (which requires the admin password).

================================================================================
FIXED
================================================================================

- `EdofSerializer` now reads `FORMAT_VERSION_STR` dynamically through the version module, so `export_3x()` can override it for the duration of a single save without leaking into other operations.
- Editor `_gradient_editor` method properly registered (it was lost during 4.0.0 development).

================================================================================



Major release: rich text, vector graphics, custom PDF writer, PDF import, formatted tables, and legacy EDOF 2 read support.
This is a major version bump because the renderer, PDF subsystem, and Shape model received fundamental architectural changes. File-format compatibility is preserved - 3.x files load with automatic migration, and EDOF 2 files (legacy unreleased format) are now also readable in best-effort mode.

================================================================================
ADDED - Rich text & formatting
================================================================================

Rich text runs in TextBox
- New TextRun dataclass: text segment with its own font_family, font_size, bold, italic, underline, strikethrough, color, background
- TextBox.runs: list[TextRun] - when non-empty, replaces plain text + style rendering
- Run-based layout engine: per-run measurement, wrap across run boundaries, mixed font sizes on the same line
- Auto-shrink / auto-fill with runs: global scale factor s found by binary search and applied to all font_size values, preserving relative size ratios between runs
- Per-run underline, strikethrough, background highlight rendering with correct horizontal extents
- Backwards compatible: runs == [] keeps the original plain-text behaviour

Formatted tables
- New Table object type (separate from Group)
- TableCell with full styling: own TextStyle or runs[] for rich text, bg_color (RGBA), per-side border (top/right/bottom/left) with own color and width, padding, colspan, rowspan
- Per-row and per-column custom widths/heights; auto-distribution if not specified
- Cell content clipped at cell boundary
- Editor: click to select cell, double-click to edit, right-click for cell formatting menu

================================================================================
ADDED - Vector graphics
================================================================================

Bezier path Shape
- New shape type "path" - arbitrary vector path with line segments and Bezier curves
- Shape.path_data: list[PathCommand] - SVG-style commands: M (moveto), L (lineto), C (cubic Bezier), Q (quadratic Bezier), Z (close)
- Pixel-correct rendering via Pillow ImageDraw.line() for segments + de Casteljau subdivision for curves
- Direct SVG path string parsing: Shape.from_svg_path("M 10 10 L 50 50 C ...")

Linear and radial gradients
- FillStyle.gradient - replaces solid fill with multi-stop gradient
- Linear: gradient_type="linear" with gradient_angle (deg) and gradient_stops=[(offset, rgba), ...]
- Radial: gradient_type="radial" with gradient_center=(cx, cy) and gradient_radius
- Renderer creates per-object gradient mask; full RGBA interpolation between stops

Path-based stroke styling
- StrokeStyle.dash_pattern - list of mm values, e.g. [3, 2] for dashed line
- StrokeStyle.cap - "butt", "round", "square"
- StrokeStyle.join - "miter", "round", "bevel"

Blend modes
- obj.blend_mode - "normal", "multiply", "screen", "overlay", "darken", "lighten"
- Compositing via Pillow with custom pixel ops

================================================================================
ADDED - Custom vector PDF writer
================================================================================

Pure-Python PDF 1.7 writer (no reportlab dependency)
- Native implementation of cross-reference table, object catalog, page tree, content streams
- Standard 14 PDF fonts (Helvetica, Times, Courier with bold/italic) - zero embedding for these
- TTF embedding for custom fonts (Type0/CID font + ToUnicode CMap + cidset)
- System font name mapping (Arial -> Helvetica, Times New Roman -> Times-Roman, ...)
- WinAnsiEncoding for Latin-1 incl. Czech diacritics; UTF-16BE for CID fonts
- Vector text - searchable, copyable, selectable in PDF readers
- Vector shapes (rect, ellipse, line, polygon, Bezier path)
- Linear / radial gradient as PDF shading patterns
- Images as XObject with FlateDecode (PNG-style) or DCTDecode (JPEG passthrough)
- Multi-page support with shared resources
- PDF metadata (title, author, subject, keywords, creator) via Info dictionary
- Vector PDFs typically 5-15x smaller than rasterised PDFs
- Default mode is vector; raster fallback: doc.export_pdf(path, vector=False)

================================================================================
ADDED - PDF -> EDOF import
================================================================================

edof.import_pdf(path) -> Document

Bidirectional PDF support - open existing PDFs as editable EDOF documents.

Text reconstruction
- Per-page text spans extracted via pymupdf with bbox, font, size, color, bold/italic flags
- Block clustering algorithm detects formatted text blocks:
    * Same font + size (5% tolerance) -> grouped together
    * Vertical gap <= font_size x 1.5 -> same paragraph
    * Similar X-alignment (left, center, justified) -> same column
    * Line-spacing tolerance - variable line gaps within a paragraph are merged when consistent
    * Indented paragraphs detected by first-line offset relative to subsequent lines
    * Hanging indents for bulleted lists detected separately
- Heading detection: spans with significantly larger font size than median -> standalone TextBox marked as heading
- List detection: spans starting with bullet/dash/number prefixes -> list item TextBoxes with proper indent
- Mixed inline formatting within a block -> produces a rich-text TextBox with runs[]

Font handling
- Standard 14 PDF fonts -> mapped via the alias system, no embedding needed
- Fully embedded TrueType/OpenType -> font bytes extracted directly into .edof resources
- Subsetted fonts ("AAAAAA+Arial" prefix), most common case:
    * First tries to find the full font locally via the alias system -> uses local copy (full editing capability)
    * If not found, embeds the subset anyway -> existing text renders correctly, but adding new characters to that font will warn in doc.errors
    * Both cases logged in doc.errors with the substitution decision
- Type3 fonts (vector glyphs) -> individual glyphs converted to Shape path objects when extractable; otherwise replaced with the closest local font and logged
- CID fonts (Asian scripts) -> handled transparently by pymupdf, embedded as full TTFs

Image extraction
- Embedded raster images extracted with original encoding (PNG / JPEG)
- Pixel position and clip preserved
- One ImageBox per detected image

Vector graphics
- PDF stroked/filled paths converted to Shape objects with "path" type
- Color and stroke properties preserved
- Bezier curves preserved as C commands (no rasterization)

Tables (heuristic)
- Optional pdfplumber dependency: detects tabular grids from horizontal/vertical lines + clustered text spans
- Detected tables become Table objects with TableCells preserving cell content and basic styling
- When detection is uncertain, falls back to individual TextBoxes (logged in doc.errors)

API:
    doc = edof.import_pdf("template.pdf",
                          detect_tables=True,
                          merge_paragraphs=True,
                          heading_threshold=1.4)   # font_size > median * 1.4

CLI:
    edof-cli import template.pdf -o template.edof --detect-tables

Editor: File -> Import PDF...

================================================================================
ADDED - Legacy EDOF 2 read support
================================================================================

EDOF 2 was an internal pre-release format that was never publicly distributed. It had architectural problems that led to the redesign in EDOF 3. To support users who have legacy EDOF 2 archives, the loader now performs a best-effort migration.

- edof.load(path) auto-detects the file format (EDOF 4, EDOF 3, or EDOF 2)
- EDOF 2 files identified by manifest version field or legacy structure markers
- Best-effort migration:
    * Object types mapped to EDOF 4 equivalents where possible
    * Style properties translated (legacy enum values -> string constants)
    * Embedded resources preserved
    * Variable system mapped to new VariableStore (legacy unstructured names normalised)
- Migration warnings recorded in doc.errors (does not abort)
- One-way conversion only: EDOF 2 -> EDOF 4. The output cannot be saved back to EDOF 2.
- CLI: edof-cli convert legacy.edof -o new.edof
- After conversion, save as a current EDOF file: doc.save("new.edof")

================================================================================
ADDED - SVG export
================================================================================

- doc.export_svg(path, page=0) - one SVG file per page
- Text rendered as <text> elements (searchable in browsers, indexable, copyable)
- Shapes as native SVG: <rect>, <ellipse>, <line>, <polygon>, <path> (with full Bezier)
- Gradients rendered as <linearGradient> / <radialGradient> definitions
- Images embedded as base64 data URIs (PNG / JPEG)
- Custom fonts embedded via @font-face with data URI

================================================================================
ADDED - Templating
================================================================================

Conditional visibility
- obj.visible_if = "score > 90" - Python-style expression evaluated against document variables at render time
- Safe evaluator: literals, comparisons (<, <=, ==, !=, >=, >), arithmetic, and/or/not, in/not in; no function calls, no imports, no attribute access
- Syntax errors recorded in doc.errors without aborting render
- Editor displays a small (i) badge on objects with conditions

Repeating sections
- page.repeat_objects(template_objs, data_list, gap=2.0) - duplicates a group of objects for each row of data_list
- Variable substitution per row: {column_name} placeholders inside text, runs[].text, qrcode.data, imagebox.variable are replaced with row values
- Auto-pagination: when a row would overflow the page, a new page is created automatically with the same dimensions
- Page-level header/footer objects can be marked repeat_on_pages=True so they appear on every generated page

================================================================================
ADDED - High-level API helpers
================================================================================

Configurable text padding
- TextStyle.padding (mm) - default 1 mm (was hardcoded 2 mm); set to 0 for edge-to-edge text
- Small textboxes (< 6 mm tall) are now usable

Font fallback & cross-platform aliases
- load_font_safe() emits EdofMissingFontWarning instead of silently using a bitmap fallback
- Fallback chain: DejaVu Sans -> Liberation Sans -> FreeSans
- Cross-platform aliases for Arial, Helvetica, Times New Roman, Courier New, Calibri, Cambria, Verdana, Tahoma, Trebuchet MS, Georgia, Segoe UI, Comic Sans MS, Impact

High-level widgets
- page.add_card(x, y, w, h, title, body, accent_color) - accent header + title + body
- page.add_metric(x, y, w, h, label, value, subtitle, value_color) - large-value tile
- page.add_table(x, y, w, rows, header, alternating, row_height) - quick table (now uses new Table object internally)
- page.add_kv_list(x, y, w, items, key_width_frac) - key-value list

Layout helpers
- page.row(y, gap, height) -> _RowContext with add_textbox, add_image, add_shape, skip, next_x
- page.column(x, gap, width) -> _ColumnContext with add_textbox, add_textbox_auto, add_image, add_shape, skip, next_y

Auto-height textbox
- page.add_textbox_auto(x, y, w, text, min_height, **style) - height computed from content
- edof.measure_text_height(text, style, width_mm, dpi) - standalone helper

================================================================================
ADDED - Editor
================================================================================

Existing 3.x features retained
- edof-editor and edof-cli console scripts
- edof/editor_lang/en.json for translations (add XX.json for other languages)
- Async rendering, type-aware property panel, object list panel
- Inline text editor with WYSIWYG sizing across all zoom levels and Windows DPI scaling
- Double-click QR / Image actions
- 60-step undo/redo

New in 4.0
- Rich text inline editor: double-click a TextBox with runs opens a formatting toolbar (bold, italic, underline, color, font, size) for selected text
- Cell editor for Table objects: click cell to select, double-click to edit content, right-click for cell formatting
- Path drawing tool: draw arbitrary Bezier paths; convert any shape to path for editing
- Cursor position in mm in status bar (live update during mouse move)
- Find & Replace dialog (Ctrl+F): searches all TextBoxes on all pages, optional case-sensitive, regex, whole-word
- Snap-to-grid: toggleable grid snap during drag, configurable spacing
- Alignment guides: magnetic alignment to other objects' edges/centres while dragging
- Multi-select: Ctrl+click adds to selection, lasso drag-rectangle, group move + batch property edit
- Template gallery: File -> New from Template (invoice, certificate, business card, A4 label sheet)
- CSV batch export: File -> Batch Fill from CSV...
- Import PDF: File -> Import PDF...
- Convert legacy EDOF 2: File -> Open... auto-detects and converts on load
- Gradient editor: visual stop editor for fill gradients
- Layer panel: dedicated dock with drag-to-reorder, eye/lock toggles per object

Print preview fixes (carried from 3.x)
- Raw PIL bytes via QImage constructor -> bypasses Qt 256 MB image allocation limit
- painter.viewport() for correct page rect (was blank pages)
- QPageSize(QPageSize.PageSizeId.A4) (PyQt6-correct API)
- Preview renders at <= 150 dpi regardless of printer DPI

================================================================================
ADDED - CLI
================================================================================

- edof-cli info template.edof - metadata, variables, editable fields, fonts used
- edof-cli objects template.edof - all objects with layer, type, variable
- edof-cli validate template.edof - structural validation
- edof-cli export template.edof out.png --set name=Jan - fill and export
- edof-cli batch template.edof data.csv -o "out_{n}.png" - CSV batch export
- edof-cli import template.pdf -o template.edof - PDF -> EDOF
- edof-cli convert legacy.edof -o template.edof - EDOF 2 -> EDOF 4 conversion
- --vector / --raster flag for PDF export
- --svg for SVG export
- --all-pages, --dpi, --format, --color-space overrides

================================================================================
FIXED - carried from 3.x development
================================================================================

- Inline text editor keyboard input (replaced QGraphicsProxyWidget with QPlainTextEdit viewport child)
- Inline text editor font size = font_pt x RDPI x zoom / logical_dpi (correct WYSIWYG at all zoom + Windows DPI scaling)
- Auto-shrink / auto-fill DPI conversion (pt -> px = pt x dpi / 72)
- Rotation handle direction sign error
- Rotated object resize keeps anchor fixed
- Middle-mouse pan (scroll bar delta)
- Toolbar/menu items missing (semicolon bug if key: ...; addAction())
- Layer ordering proper swap
- QR codes with non-black colors (B&W render then colorise)
- get_resolved_text falls back to obj.text for empty variable values
- Hidden objects show as ghost outline, still selectable

================================================================================
CHANGED - breaking
================================================================================

- doc.export_pdf() defaults to vector mode (was raster); doc.export_pdf(path, vector=False) for raster fallback
- Internal add_table helper produces a Table object (was a Group of TextBoxes); existing .edof files with the old layout still load via auto-migration
- Shape.path_data field added - old Shape instances without this field load with path_data = [] (no behaviour change)
- TextStyle.padding default 1.0 mm (was hardcoded 2.0 mm in renderer)
- FillStyle.gradient field added - old FillStyle instances load with gradient = None (no behaviour change)

================================================================================
CHANGED - non-breaking
================================================================================

- reportlab is no longer a hard requirement - only used as fallback if vector=False is requested with reportlab installed
- pymupdf added to edof[pdf] extras for the new PDF writer and PDF importer
- pdfplumber added to edof[pdf] extras as optional table-detection helper

================================================================================
FILE FORMAT
================================================================================

- Format version bumped to 4.0.0
- Forward compat: 3.x files load and migrate automatically; new 4.x fields default to neutral values that preserve existing rendering
- Legacy EDOF 2 read support: best-effort migration on load (one-way; output is always 4.x)
- Backward compat for 3.x consumers: 4.x files using only 3.x features can be downgraded with doc.export_3x() (best-effort: rich-text runs collapsed to plain text, paths rasterised to bitmap shapes, tables flattened to groups)

================================================================================
REMOVED
================================================================================

- Old raster-only pdf.py writer (replaced by vector writer with raster fallback)

================================================================================
MIGRATION GUIDE (3.x -> 4.x)
================================================================================

- All 3.x scripts continue to work without changes
- doc.export_pdf("out.pdf") now produces vector PDF; if you specifically need raster (e.g., for compatibility with old PDF/A profiles), pass vector=False
- If you used add_table and relied on iterating its child TextBoxes, switch to Table.cells instead
- New rich-text features are opt-in; plain TextBox.text continues to work
- Legacy EDOF 2 files: loading works automatically. To convert in bulk:
      for f in glob("legacy/*.edof"):
          doc = edof.load(f)
          doc.save(f.replace("legacy/", "converted/"))

================================================================================
================================================================================

## [3.0.2] - 2025-04-15

### Fixed
- attestations: false in CI workflow to fix failed PyPI publish via GitHub Actions

================================================================================

## [3.0.1] - 2025-04-14

### Added
- edof-editor and edof-cli console scripts
- editor_lang/en.json for editor i18n

### Fixed
- Print preview blank pages, Qt 256 MB image limit, QPrinter.PageSize API
- Inline text editor keyboard input and WYSIWYG font sizing
- Auto-shrink / auto-fill DPI conversion
- Rotation handle direction, rotated resize anchor, middle-mouse pan
- Toolbar items missing (semicolon bug)
- Layer ordering swap logic
- QR codes with non-black colors
- Variable binding clearing text
- Hidden objects unselectable

================================================================================

## [3.0.0] - 2025-01-01

Initial public release.

- Document model: TextBox, ImageBox, Shape, Line, QRCode, Group
- Variable/template system with type validation and batch fill
- Pillow RGBA renderer; RGB/RGBA/L/1/CMYK; 8/16-bit
- .edof ZIP format with embedded assets
- Export: PNG/JPEG/TIFF/BMP/PDF; CLI tool; PyQt6 desktop editor
- Command API with undo/redo

================================================================================

Note: Versions 1.x were internal iterations not publicly released.
EDOF 2 was a separate pre-release format with architectural problems that led to the redesign in EDOF 3. EDOF 2 archives can be read by EDOF 4+ in best-effort mode but cannot be written back to.
