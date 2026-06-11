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
