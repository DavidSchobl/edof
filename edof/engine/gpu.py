"""Optional GPU acceleration (moderngl), Build 5.

DESIGN INVARIANTS (do not break):
  * GPU is an OPT-IN accelerator. When enabled AND available it does the work;
    on ANY failure or when unavailable, the caller falls back to the CPU path so
    output is always produced. moderngl is an OPTIONAL dependency.
  * A GL context is bound to the thread that created it, and the live renderer
    runs in short-lived worker threads. So ALL GPU work goes through a single
    long-lived worker thread that owns the one context and processes jobs from a
    queue; callers submit a job and block briefly for the result. This makes the
    GPU usable safely from any thread.
  * Export and the idle full-quality render stay on CPU (deterministic).

Headless/CI has no GL context, so the worker reports unavailable and everything
falls back. The parity self-test validates correctness on real hardware.
"""

from __future__ import annotations

import os
import math
import queue
import threading

_MAX_TAPS = 127

# Enable flag (set from the app's Performance settings) + live counters for the
# status indicator. Counters are plain ints touched from the render thread; an
# occasional torn read is harmless for a status badge.
_enabled = False
blur_gpu_count = 0
blur_cpu_count = 0


def set_enabled(v: bool):
    global _enabled
    _enabled = bool(v)


def is_enabled() -> bool:
    return _enabled or _env_gpu_enabled()


def _env_gpu_enabled() -> bool:
    raw = os.environ.get("EDOF_GPU", "").strip().lower()
    if not raw:
        return False
    return raw.split()[0].strip(" \t\",;") in ("1", "true", "yes", "on")


def reset_counters():
    global blur_gpu_count, blur_cpu_count
    blur_gpu_count = 0
    blur_cpu_count = 0


# ── GPU worker thread ────────────────────────────────────────────────────────

_VERT = """
#version 330
in vec2 in_pos;
out vec2 uv;
void main() { uv = in_pos * 0.5 + 0.5; gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

_FRAG = """
#version 330
uniform sampler2D tex;
uniform vec2 direction;
uniform int taps;
uniform float weights[%d];
in vec2 uv;
out float frag;
void main() {
    float wc = weights[0];
    float sum = texture(tex, uv).r * wc;
    float wsum = wc;
    for (int i = 1; i <= taps; i++) {
        float w = weights[i];
        vec2 off = direction * float(i);
        sum += w * (texture(tex, uv + off).r + texture(tex, uv - off).r);
        wsum += 2.0 * w;
    }
    frag = sum / max(wsum, 1e-6);
}
""" % (_MAX_TAPS + 1)


class _GpuWorker(threading.Thread):
    """Owns the single GL context and runs all GPU jobs serially in-thread."""

    def __init__(self):
        super().__init__(daemon=True, name="edof-gpu")
        self._q = queue.Queue()
        self._ready = threading.Event()
        self.ctx = None
        self.reason = None
        self._prog = None
        self._vao = None
        self._quad = None
        self._ca_prog = None
        self._ca_vao = None
        self._loft_prog = None
        self._loft_vao = None
        self._ht_prog = None
        self._ht_quad = None

    def _ca_quad(self):
        """Shared fullscreen-quad buffer (built once, reused by blur + CA)."""
        if self._quad is None:
            import numpy as np
            quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4")
            self._quad = self.ctx.buffer(quad.tobytes())
        return self._quad

    def run(self):
        try:
            import moderngl
            self.ctx = moderngl.create_standalone_context()
        except Exception as e:
            self.ctx = None
            self.reason = f"{type(e).__name__}: {e}"
        self._ready.set()
        if self.ctx is None:
            return
        while True:
            job = self._q.get()
            if job is None:
                break
            func, args, holder, ev = job
            try:
                holder["result"] = func(self, *args)
            except Exception as e:
                holder["result"] = None
                holder["error"] = f"{type(e).__name__}: {e}"
            ev.set()

    def wait_ready(self, timeout=10.0):
        return self._ready.wait(timeout)

    def submit(self, func, args=(), timeout=10.0):
        if self.ctx is None:
            return None
        ev = threading.Event()
        holder = {}
        self._q.put((func, args, holder, ev))
        if ev.wait(timeout):
            return holder.get("result")
        return None

    # programs are built lazily IN the worker thread (context-bound)
    def _ensure_blur(self):
        if self._prog is not None:
            return
        self._prog = self.ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)
        self._vao = self.ctx.simple_vertex_array(self._prog, self._ca_quad(), "in_pos")


_worker = None
_worker_lock = threading.Lock()


def _ensure_worker():
    """Start the worker (once) and return it if its GL context is usable, else
    None."""
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = _GpuWorker()
            _worker.start()
        w = _worker
    w.wait_ready()
    return w if w.ctx is not None else None


def gpu_available() -> bool:
    return _ensure_worker() is not None


def gpu_status() -> str:
    w = _ensure_worker()
    if w is None:
        reason = (_worker.reason if _worker is not None else None) or \
                 "no moderngl / no GL context"
        return f"GPU unavailable ({reason})"
    try:
        info = w.ctx.info
        return (f"GPU available: {info.get('GL_RENDERER', '?')} | "
                f"GL {info.get('GL_VERSION', '?')}")
    except Exception:
        return "GPU available"


def reset():
    """Tear down the worker/context (tests / driver change)."""
    global _worker
    with _worker_lock:
        w = _worker
        _worker = None
    if w is not None and w.ctx is not None:
        try:
            w._q.put(None)
        except Exception:
            pass


def _gaussian_weights(sigma, taps):
    return [math.exp(-(i * i) / (2.0 * sigma * sigma)) for i in range(taps + 1)]


def _blur_job(worker, src_bytes, w, h, sigma, taps):
    """Runs IN the worker thread; has the context. Two-pass separable blur."""
    import moderngl
    import numpy as np
    from PIL import Image

    ctx = worker.ctx
    worker._ensure_blur()
    prog, vao = worker._prog, worker._vao

    wbuf = np.zeros(_MAX_TAPS + 1, dtype="f4")
    wts = _gaussian_weights(sigma, taps)
    wbuf[: taps + 1] = wts

    def _tex(data=None):
        t = ctx.texture((w, h), 1, data=data, dtype="f1", alignment=1)
        t.repeat_x = False
        t.repeat_y = False
        t.filter = (moderngl.NEAREST, moderngl.NEAREST)
        return t

    tex_in = _tex(src_bytes)
    tex_mid = _tex()
    tex_out = _tex()
    fbo_mid = ctx.framebuffer(color_attachments=[tex_mid])
    fbo_out = ctx.framebuffer(color_attachments=[tex_out])
    try:
        prog["taps"].value = taps
        prog["weights"].write(wbuf.tobytes())

        fbo_mid.use()
        ctx.viewport = (0, 0, w, h)
        prog["tex"].value = 0
        tex_in.use(0)
        prog["direction"].value = (1.0 / w, 0.0)
        vao.render(moderngl.TRIANGLE_STRIP)

        fbo_out.use()
        tex_mid.use(0)
        prog["direction"].value = (0.0, 1.0 / h)
        vao.render(moderngl.TRIANGLE_STRIP)

        raw = fbo_out.read(components=1, dtype="f1", alignment=1)
        out = np.frombuffer(raw, dtype="u1").reshape((h, w)).copy()
        # No flip: upload + framebuffer-read orientations cancel (verified by the
        # parity self-test, which initially showed a vertical-mirror diff).
        return Image.fromarray(out, "L")
    finally:
        for obj in (tex_in, tex_mid, tex_out, fbo_mid, fbo_out):
            try:
                obj.release()
            except Exception:
                pass


_CA_FRAG = """
#version 330
uniform sampler2D src;
uniform int mode;            // 0 = linear shift, 1 = radial scale
uniform vec3 tint0; uniform vec2 shift0; uniform float scale0;
uniform vec3 tint1; uniform vec2 shift1; uniform float scale1;
uniform vec3 tint2; uniform vec2 shift2; uniform float scale2;
in vec2 uv;
out vec4 frag;
vec4 samp(vec2 c) {
    if (c.x < 0.0 || c.x > 1.0 || c.y < 0.0 || c.y > 1.0) return vec4(0.0);
    return texture(src, c);
}
vec2 srcuv(vec2 sh, float sc) {
    return (mode == 0) ? (uv - sh) : (vec2(0.5) + (uv - vec2(0.5)) / sc);
}
void main() {
    vec3 rgb = vec3(0.0);
    float aA = 0.0;
    vec4 s0 = samp(srcuv(shift0, scale0)); rgb += tint0 * s0.r; aA = max(aA, s0.a);
    vec4 s1 = samp(srcuv(shift1, scale1)); rgb += tint1 * s1.g; aA = max(aA, s1.a);
    vec4 s2 = samp(srcuv(shift2, scale2)); rgb += tint2 * s2.b; aA = max(aA, s2.a);
    frag = vec4(min(rgb, vec3(1.0)), aA);
}
"""


def _ca_job(worker, rgba_bytes, w, h, mode, specs):
    """Runs IN the worker thread. Per-channel chromatic aberration in one pass.
    specs = [(tint_rgb01, (shx,shy_uv), scale), ...] for R,G,B (channel via .r/.g/.b)."""
    import moderngl
    import numpy as np
    from PIL import Image

    ctx = worker.ctx
    if worker._ca_prog is None:
        worker._ca_prog = ctx.program(vertex_shader=_VERT, fragment_shader=_CA_FRAG)
        worker._ca_vao = ctx.simple_vertex_array(worker._ca_prog, worker._ca_quad(), "in_pos")
    prog, vao = worker._ca_prog, worker._ca_vao

    tex_in = ctx.texture((w, h), 4, data=rgba_bytes, dtype="f1")
    tex_in.repeat_x = False; tex_in.repeat_y = False
    tex_in.filter = (moderngl.LINEAR, moderngl.LINEAR)
    tex_out = ctx.texture((w, h), 4, dtype="f1")
    fbo = ctx.framebuffer(color_attachments=[tex_out])
    try:
        prog["mode"].value = int(mode)
        for i, (tint, sh, sc) in enumerate(specs):
            prog[f"tint{i}"].value = (float(tint[0]), float(tint[1]), float(tint[2]))
            prog[f"shift{i}"].value = (float(sh[0]), float(sh[1]))
            prog[f"scale{i}"].value = float(sc) if sc and abs(sc) > 1e-3 else 1.0
        fbo.use()
        ctx.viewport = (0, 0, w, h)
        prog["src"].value = 0
        tex_in.use(0)
        vao.render(moderngl.TRIANGLE_STRIP)
        raw = fbo.read(components=4, dtype="f1")
        out = np.frombuffer(raw, dtype="u1").reshape((h, w, 4)).copy()
        return Image.fromarray(out, "RGBA")
    finally:
        for obj in (tex_in, tex_out, fbo):
            try:
                obj.release()
            except Exception:
                pass


def gpu_chromatic_aberration(rgba_pil, mode, specs):
    """Per-channel chromatic aberration on the GPU. mode: 'linear' or 'radial'.
    specs: list of 3 (tint_rgb_0_255, (dx_px, dy_px), scale) for R/G/B. Returns a
    new RGBA image, or None (caller falls back to CPU)."""
    w = _ensure_worker()
    if w is None:
        return None
    import numpy as np
    src = np.asarray(rgba_pil.convert("RGBA"), dtype="u1")
    h, ww = src.shape[0], src.shape[1]
    m = 1 if mode == "radial" else 0
    gspecs = []
    for tint, (dx, dy), sc in specs:
        gspecs.append(((tint[0] / 255.0, tint[1] / 255.0, tint[2] / 255.0),
                       (dx / float(ww), dy / float(h)), sc))
    return w.submit(_ca_job, (src.tobytes(), ww, h, m, gspecs))


def gpu_gaussian_blur_L(pil_L, radius_px):
    """Two-pass separable Gaussian blur of an 'L' image on the GPU worker. Returns
    a new 'L' image, or None if the GPU is unavailable or the radius exceeds the
    fixed tap budget (caller falls back to CPU). radius_px == sigma (matches the
    way PIL's GaussianBlur(radius) is used elsewhere)."""
    if radius_px is None or radius_px <= 0:
        return pil_L
    w = _ensure_worker()
    if w is None:
        return None
    sigma = float(radius_px)
    taps = int(math.ceil(3.0 * sigma))
    if taps < 1:
        return pil_L
    if taps > _MAX_TAPS:
        return None
    import numpy as np
    src = np.asarray(pil_L.convert("L"), dtype="u1")
    h, ww = src.shape
    # v4.2.11.7: pad width/height to a multiple of 4 before upload, then crop back.
    # Single-channel GL texture rows can be padded to a 4-byte boundary by the
    # driver; for widths that are not a multiple of 4 that produced a sheared
    # "woven grid" in the result (visible as the long-shadow comb). Padding with
    # edge replication keeps the blur at the real edges unchanged.
    w4 = (ww + 3) & ~3
    h4 = (h + 3) & ~3
    if w4 != ww or h4 != h:
        src = np.pad(src, ((0, h4 - h), (0, w4 - ww)), mode="edge")
    from PIL import Image as _Img
    res = w.submit(_blur_job, (src.tobytes(), w4, h4, sigma, taps))
    if res is None:
        return None
    if w4 != ww or h4 != h:
        res = res.crop((0, 0, ww, h))
    return res


_LOFT_FRAG = """
#version 330
uniform sampler2D sil;     // pre-blurred silhouette (single channel, [0,1])
uniform vec2 wh;           // (W, H) in pixels
uniform float aff_a;       // 1/s  (inverse uniform scale)
uniform vec2 aff_cf;       // (c, f) translation terms, pixels
uniform float t_val;       // normalised distance of this step
uniform float thresh;      // coverage threshold (e.g. 12/255)
uniform int target;        // 0 = coverage (MAX), 1 = tmap (MIN, discard if empty)
in vec2 uv;
out float frag;
void main() {
    // uv maps directly to image pixels (same convention as the CA pass), so the
    // affine matches PIL's transform and the throw direction is correct.
    vec2 outpx = uv * wh;
    vec2 inpx = vec2(aff_a * outpx.x + aff_cf.x, aff_a * outpx.y + aff_cf.y);
    vec2 inuv = inpx / wh;
    float a = 0.0;
    if (inuv.x >= 0.0 && inuv.x <= 1.0 && inuv.y >= 0.0 && inuv.y <= 1.0)
        a = texture(sil, inuv).r;
    if (target == 0) {
        frag = a;                       // MAX-blended -> union coverage
    } else {
        if (a < thresh) discard;        // only covering steps update tmap
        frag = t_val;                   // MIN-blended -> first (nearest) t
    }
}
"""


def _loft_sweep_job(worker, sil_bytes, w, h, cx, cy, dxu, dyu, L, taper, N, thresh):
    """Runs IN the worker thread. Forward loft sweep: composite N uniformly scaled
    + throw-translated copies of the silhouette, returning coverage (MAX) and the
    nearest covering distance tmap (MIN). Mirrors the CPU sweep step-for-step."""
    import moderngl
    import numpy as np

    ctx = worker.ctx
    if worker._loft_prog is None:
        worker._loft_prog = ctx.program(vertex_shader=_VERT, fragment_shader=_LOFT_FRAG)
        worker._loft_vao = ctx.simple_vertex_array(worker._loft_prog, worker._ca_quad(), "in_pos")
    prog, vao = worker._loft_prog, worker._loft_vao

    sil = ctx.texture((w, h), 1, data=sil_bytes, dtype="f1", alignment=1)
    sil.repeat_x = False; sil.repeat_y = False
    sil.filter = (moderngl.LINEAR, moderngl.LINEAR)
    cov_t = ctx.texture((w, h), 1, dtype="f4")
    tmap_t = ctx.texture((w, h), 1, dtype="f4")
    cov_f = ctx.framebuffer(color_attachments=[cov_t])
    tmap_f = ctx.framebuffer(color_attachments=[tmap_t])
    try:
        cov_f.use(); ctx.clear(0.0, 0.0, 0.0, 0.0)
        tmap_f.use(); ctx.clear(1.0, 1.0, 1.0, 1.0)
        ctx.viewport = (0, 0, w, h)
        prog["sil"].value = 0; sil.use(0)
        prog["wh"].value = (float(w), float(h))
        prog["thresh"].value = float(thresh)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = (moderngl.ONE, moderngl.ONE)
        for i in range(int(N) + 1):
            t = i / float(N)
            s = 1.0 + (taper - 1.0) * t
            if s <= 0.02:
                continue
            a = 1.0 / s
            c = cx * (1.0 - a) - dxu * L * t * a
            f = cy * (1.0 - a) - dyu * L * t * a
            prog["aff_a"].value = float(a)
            prog["aff_cf"].value = (float(c), float(f))
            prog["t_val"].value = float(t)
            cov_f.use(); ctx.blend_equation = moderngl.MAX
            prog["target"].value = 0
            vao.render(moderngl.TRIANGLE_STRIP)
            tmap_f.use(); ctx.blend_equation = moderngl.MIN
            prog["target"].value = 1
            vao.render(moderngl.TRIANGLE_STRIP)
        ctx.blend_equation = moderngl.FUNC_ADD
        ctx.disable(moderngl.BLEND)
        cov = np.frombuffer(cov_f.read(components=1, dtype="f4"),
                            dtype="f4").reshape((h, w)).copy()
        tmap = np.frombuffer(tmap_f.read(components=1, dtype="f4"),
                             dtype="f4").reshape((h, w)).copy()
        return cov, tmap
    finally:
        for obj in (sil, cov_t, tmap_t, cov_f, tmap_f):
            try:
                obj.release()
            except Exception:
                pass


def gpu_long_shadow_sweep(alpha_pil, dxu, dyu, length_px, taper, N,
                          thresh=12.0 / 255.0, cx=None, cy=None):
    """Loft sweep on the GPU. `alpha_pil` must already be the pre-blurred
    silhouette (so it matches the CPU path exactly). Returns (cov, tmap) as float
    arrays the size of the input (cov in 0..255, tmap in 0..1), or None so the
    caller falls back to the CPU sweep."""
    w = _ensure_worker()
    if w is None:
        return None
    import numpy as np
    src = np.asarray(alpha_pil.convert("L"), dtype="u1")
    h, ww = src.shape
    if cx is None or cy is None:
        ys, xs = np.where(src > 40)
        if len(xs) == 0:
            return None
        cx = float((int(xs.min()) + int(xs.max())) / 2.0)
        cy = float((int(ys.min()) + int(ys.max())) / 2.0)
    # pad to a multiple of 4 (single-channel upload alignment) then crop back
    w4 = (ww + 3) & ~3
    h4 = (h + 3) & ~3
    if w4 != ww or h4 != h:
        src = np.pad(src, ((0, h4 - h), (0, w4 - ww)), mode="constant")
    res = w.submit(_loft_sweep_job,
                   (src.tobytes(), w4, h4, cx, cy, float(dxu), float(dyu),
                    float(length_px), float(taper), int(N), float(thresh)))
    if res is None:
        return None
    cov, tmap = res
    return (cov[:h, :ww] * 255.0).astype("float32"), tmap[:h, :ww].astype("float32")


_HT_VERT = """
#version 330
in vec2 in_corner;        // base quad [0,1]^2
in vec4 inst_a;           // x0, y0, sz, bk  (x0/y0/sz/bk are integers in float)
in float inst_ad;         // value multiplier (transparency mode)
uniform vec2 wh;          // layer (W, H)
flat out ivec3 v_meta;    // (x0, y0, bk)
flat out float v_ad;
void main() {
    float x0 = inst_a.x, y0 = inst_a.y, sz = inst_a.z;
    vec2 px = vec2(x0 + in_corner.x * sz, y0 + in_corner.y * sz);
    gl_Position = vec4(px.x / wh.x * 2.0 - 1.0, px.y / wh.y * 2.0 - 1.0, 0.0, 1.0);
    v_meta = ivec3(int(inst_a.x + 0.5), int(inst_a.y + 0.5), int(inst_a.w + 0.5));
    v_ad = inst_ad;
}
"""

_HT_FRAG = """
#version 330
uniform sampler2D atlas;   // f32 stencil atlas, K tiles of maxd x maxd
uniform int maxdi;
flat in ivec3 v_meta;
flat in float v_ad;
out float frag;
void main() {
    // v4.2.11.35: EXACT integer sampling. The dot's quad starts at the
    // integer (x0, y0), so the fragment at pixel p maps to stencil texel
    // (p - x0, p - y0) with no interpolation and no rounding anywhere --
    // the only math left is fetch * ad and the MAX blend, mirroring the
    // CPU _stamp_max bit for bit (the atlas is float32, not quantised).
    ivec2 p = ivec2(gl_FragCoord.xy);
    int i = p.x - v_meta.x;
    int j = p.y - v_meta.y;
    frag = texelFetch(atlas, ivec2(v_meta.z * maxdi + i, j), 0).r * v_ad;
}
"""


def _ht_stamp_job(worker, atlas_bytes, atlas_w, atlas_h, maxd, K,
                  lw, lh, inst_bytes, n_inst):
    """Runs IN the worker thread. Instanced dot stamping into one channel layer:
    each instance draws its bucket stencil (from the atlas) at an integer position
    with MAX blend, mirroring the CPU _stamp_max."""
    import moderngl
    import numpy as np

    ctx = worker.ctx
    if getattr(worker, "_ht_prog", None) is None:
        worker._ht_prog = ctx.program(vertex_shader=_HT_VERT, fragment_shader=_HT_FRAG)
        quad = np.array([0, 0, 1, 0, 0, 1, 1, 1], dtype="f4")
        worker._ht_quad = ctx.buffer(quad.tobytes())
    prog = worker._ht_prog

    atlas = ctx.texture((atlas_w, atlas_h), 1, data=atlas_bytes, dtype="f4")
    atlas.repeat_x = False; atlas.repeat_y = False
    layer_t = ctx.texture((lw, lh), 1, dtype="f4")
    fbo = ctx.framebuffer(color_attachments=[layer_t])
    inst_buf = ctx.buffer(inst_bytes)
    vao = ctx.vertex_array(prog, [
        (worker._ht_quad, "2f", "in_corner"),
        (inst_buf, "4f 1f/i", "inst_a", "inst_ad"),
    ])
    try:
        fbo.use(); ctx.clear(0.0, 0.0, 0.0, 0.0)
        ctx.viewport = (0, 0, lw, lh)
        prog["atlas"].value = 0; atlas.use(0)
        prog["wh"].value = (float(lw), float(lh))
        prog["maxdi"].value = int(maxd)
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = (moderngl.ONE, moderngl.ONE)
        ctx.blend_equation = moderngl.MAX
        vao.render(moderngl.TRIANGLE_STRIP, instances=int(n_inst))
        ctx.blend_equation = moderngl.FUNC_ADD
        ctx.disable(moderngl.BLEND)
        raw = fbo.read(components=1, dtype="f4")
        return np.frombuffer(raw, dtype="f4").reshape((lh, lw)).copy()
    finally:
        for obj in (atlas, layer_t, fbo, inst_buf, vao):
            try:
                obj.release()
            except Exception:
                pass


def gpu_halftone_stamp(atlas, maxd, K, lw, lh, instances):
    """Stamp one channel's halftone dots on the GPU. `atlas` is a float (maxd,
    K*maxd) array of bucket stencils (0..1); `instances` is an (M,5) float array of
    [x0, y0, sz, bk, ad]. Returns the (lh, lw) float layer, or None to fall back."""
    w = _ensure_worker()
    if w is None:
        return None
    import numpy as np
    if instances is None or len(instances) == 0:
        return np.zeros((lh, lw), dtype="f4")
    atlas_f = np.ascontiguousarray(atlas, dtype="f4")
    ah, aw = atlas_f.shape
    inst = np.ascontiguousarray(instances, dtype="f4")
    return w.submit(_ht_stamp_job,
                    (atlas_f.tobytes(), aw, ah, float(maxd), int(K),
                     int(lw), int(lh), inst.tobytes(), int(inst.shape[0])))


_VB_PREFIX_FRAG = """
#version 330
uniform sampler2D src;
uniform int offset;
uniform int axis;          // 0 = x (rows), 1 = y (columns)
out float frag;
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    float v = texelFetch(src, p, 0).r;
    ivec2 q = p;
    if (axis == 0) q.x -= offset; else q.y -= offset;
    if ((axis == 0 && q.x >= 0) || (axis == 1 && q.y >= 0))
        v += texelFetch(src, q, 0).r;
    frag = v;
}
"""

_VB_GATHER_FRAG = """
#version 330
uniform sampler2D satP;    // INCLUSIVE 2D prefix sum of the working image
uniform sampler2D rtex;    // per-pixel radius (float)
uniform ivec2 whi;         // (W, H)
out float frag;

float S(int a, int b) {    // exclusive SAT lookup: sum over [0,a) x [0,b)
    if (a < 1 || b < 1) return 0.0;
    return texelFetch(satP, ivec2(b - 1, a - 1), 0).r;
}

void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);   // x = col, y = row (image convention)
    int r = int(texelFetch(rtex, p, 0).r + 0.5);
    int y1 = clamp(p.y - r, 0, whi.y);
    int y2 = clamp(p.y + r + 1, 0, whi.y);
    int x1 = clamp(p.x - r, 0, whi.x);
    int x2 = clamp(p.x + r + 1, 0, whi.x);
    float area = float((y2 - y1) * (x2 - x1));
    frag = (S(y2, x2) - S(y1, x2) - S(y2, x1) + S(y1, x1)) / area;
}
"""


def _vb_blur_job(worker, a_bytes, r_bytes, w, h, passes):
    """Runs IN the worker thread. 4-pass per-pixel-radius box blur:
    each pass builds an inclusive 2D prefix sum by Hillis-Steele scans
    (log2 W horizontal + log2 H vertical ping-pong draws), then one gather
    pass mirrors the CPU clamped-window box average exactly."""
    import moderngl
    import numpy as np

    ctx = worker.ctx
    if getattr(worker, "_vb_prefix", None) is None:
        worker._vb_prefix = ctx.program(vertex_shader=_VERT, fragment_shader=_VB_PREFIX_FRAG)
        worker._vb_gather = ctx.program(vertex_shader=_VERT, fragment_shader=_VB_GATHER_FRAG)
        worker._vb_vao_p = ctx.simple_vertex_array(worker._vb_prefix, worker._ca_quad(), "in_pos")
        worker._vb_vao_g = ctx.simple_vertex_array(worker._vb_gather, worker._ca_quad(), "in_pos")
    pre, gat = worker._vb_prefix, worker._vb_gather
    vao_p, vao_g = worker._vb_vao_p, worker._vb_vao_g

    a0 = ctx.texture((w, h), 1, data=a_bytes, dtype="f4")
    a1 = ctx.texture((w, h), 1, dtype="f4")
    s0 = ctx.texture((w, h), 1, dtype="f4")
    s1 = ctx.texture((w, h), 1, dtype="f4")
    rt = ctx.texture((w, h), 1, data=r_bytes, dtype="f4")
    f_a1 = ctx.framebuffer(color_attachments=[a1])
    f_a0 = ctx.framebuffer(color_attachments=[a0])
    f_s0 = ctx.framebuffer(color_attachments=[s0])
    f_s1 = ctx.framebuffer(color_attachments=[s1])
    try:
        ctx.disable(moderngl.BLEND)
        ctx.viewport = (0, 0, w, h)
        cur_a, cur_fa = a0, f_a0
        nxt_a, nxt_fa = a1, f_a1
        for _ in range(int(passes)):
            # ── inclusive 2D prefix sum of cur_a into s0/s1 ping-pong ──
            src, dst, fdst = cur_a, s0, f_s0
            other, fother = s1, f_s1
            for axis, n in ((0, w), (1, h)):
                pre["axis"].value = axis
                off = 1
                while off < n:
                    pre["offset"].value = off
                    fdst.use(); pre["src"].value = 0; src.use(0)
                    vao_p.render(moderngl.TRIANGLE_STRIP)
                    src = dst
                    dst, fdst, other, fother = other, fother, dst, fdst
                    off *= 2
            sat = src        # final prefix result
            # ── gather: per-pixel clamped box average into the other A ──
            fnxt = nxt_fa
            fnxt.use()
            gat["satP"].value = 0; sat.use(0)
            gat["rtex"].value = 1; rt.use(1)
            gat["whi"].value = (w, h)
            vao_g.render(moderngl.TRIANGLE_STRIP)
            cur_a, cur_fa, nxt_a, nxt_fa = nxt_a, nxt_fa, cur_a, cur_fa
        raw = cur_fa.read(components=1, dtype="f4")
        return np.frombuffer(raw, dtype="f4").reshape((h, w)).copy()
    finally:
        for obj in (a0, a1, s0, s1, rt, f_a0, f_a1, f_s0, f_s1):
            try:
                obj.release()
            except Exception:
                pass


_LSF_FRAG = """
#version 330
uniform sampler2D rtex;    // source alpha, float32, 0..255
uniform sampler2D lut;     // a(t) over t in [0,1], 1D as a 1024x1 texture
uniform int L;             // ray length in px
uniform int Wi;            // image width
out float frag;
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    float best = 0.0;
    int dmax = min(L, p.x);
    // exact per-row max-convolution: every upstream source pixel emits a ray
    // scaled by the alpha gradient a(d / L) sampled from the LUT (LINEAR
    // filtered, so the gradient is continuous, no segment quantisation).
    for (int d = 0; d <= dmax; ++d) {
        float r = texelFetch(rtex, ivec2(p.x - d, p.y), 0).r;
        if (r <= 0.0) continue;
        float a = texture(lut, vec2((float(d) / float(L)) * 0.999023 + 0.000488, 0.5)).r;
        float v = r * a;
        if (v > best) best = v;
    }
    frag = best;
}
"""


def _ls_field_job(worker, r_bytes, w, h, L, lut_bytes, lutn):
    """Runs IN the worker thread: exact long-shadow per-row max-convolution."""
    import moderngl
    import numpy as np
    ctx = worker.ctx
    if getattr(worker, "_lsf_prog", None) is None:
        worker._lsf_prog = ctx.program(vertex_shader=_VERT, fragment_shader=_LSF_FRAG)
        worker._lsf_vao = ctx.simple_vertex_array(worker._lsf_prog, worker._ca_quad(), "in_pos")
    prog, vao = worker._lsf_prog, worker._lsf_vao
    rt = ctx.texture((w, h), 1, data=r_bytes, dtype="f4")
    rt.filter = (moderngl.NEAREST, moderngl.NEAREST)
    lt = ctx.texture((lutn, 1), 1, data=lut_bytes, dtype="f4")
    lt.filter = (moderngl.LINEAR, moderngl.LINEAR)
    lt.repeat_x = False
    dst = ctx.texture((w, h), 1, dtype="f4")
    fb = ctx.framebuffer(color_attachments=[dst])
    try:
        ctx.disable(moderngl.BLEND)
        ctx.viewport = (0, 0, w, h)
        fb.use()
        prog["rtex"].value = 0; rt.use(0)
        prog["lut"].value = 1; lt.use(1)
        prog["L"].value = int(L)
        prog["Wi"].value = int(w)
        vao.render(moderngl.TRIANGLE_STRIP)
        out = np.frombuffer(dst.read(), dtype="f4").reshape(h, w)
        return out.copy()
    finally:
        rt.release(); lt.release(); dst.release(); fb.release()


def gpu_long_shadow_field(R, L, lut):
    """Exact long-shadow ray field on the GPU:
    field(y, x) = max over d in [0, L] of R(y, x - d) * lut(d / L).
    `R` float32 (H, W) source alpha 0..255; `lut` float32 1D samples of the
    alpha gradient over t in [0, 1]. Returns float32 (H, W) or None so the
    caller falls back to the CPU path."""
    w = _ensure_worker()
    if w is None:
        return None
    import numpy as np
    a = np.ascontiguousarray(R, dtype="f4")
    h, ww = a.shape
    lt = np.ascontiguousarray(np.asarray(lut, dtype="f4").ravel())
    if lt.size < 2:
        lt = np.array([float(lt[0]) if lt.size else 1.0] * 2, dtype="f4")
    if lt.size != 1024:
        xs = np.linspace(0.0, 1.0, 1024).astype("f4")
        lt = np.interp(xs, np.linspace(0.0, 1.0, lt.size), lt).astype("f4")
    return w.submit(_ls_field_job, (a.tobytes(), ww, h, int(L), lt.tobytes(), 1024))


def gpu_variable_box_blur(A, rmap, passes=4):
    """Per-pixel-radius 4-pass box blur on the GPU (the long-shadow variable
    blur). `A` float32 (H, W), `rmap` integer radii. Returns the blurred float32
    array, or None so the caller falls back to the CPU SAT path."""
    w = _ensure_worker()
    if w is None:
        return None
    import numpy as np
    a = np.ascontiguousarray(A, dtype="f4")
    h, ww = a.shape
    r = np.ascontiguousarray(rmap, dtype="f4")
    return w.submit(_vb_blur_job, (a.tobytes(), r.tobytes(), ww, h, int(passes)))


def selftest(size: int = 256, radius: float = 8.0, out_dir=None) -> dict:
    """Blur a test mask on CPU (PIL) and GPU, save cpu/gpu/diff images, and
    report mean/max pixel difference. Validates GPU parity on real hardware."""
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np

    status = gpu_status()
    if not gpu_available():
        return {"available": False, "status": status}

    base = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(base)
    d.ellipse([size * 0.18, size * 0.18, size * 0.62, size * 0.62], fill=255)
    d.rectangle([size * 0.55, size * 0.55, size * 0.85, size * 0.85], fill=200)
    for i in range(6):
        x = int(size * (0.1 + i * 0.13))
        d.line([(x, int(size * 0.05)), (x, int(size * 0.95))], fill=160, width=2)

    cpu = base.filter(ImageFilter.GaussianBlur(radius))
    gpu = gpu_gaussian_blur_L(base, radius)
    if gpu is None:
        return {"available": True, "status": status,
                "error": "gpu_gaussian_blur_L returned None (radius too large?)"}

    a = np.asarray(cpu, dtype=np.float32)
    b = np.asarray(gpu, dtype=np.float32)
    diff = np.abs(a - b)

    import tempfile
    out_dir = out_dir or tempfile.mkdtemp(prefix="edof_gpu_selftest_")
    os.makedirs(out_dir, exist_ok=True)
    cpu_path = os.path.join(out_dir, "blur_cpu.png")
    gpu_path = os.path.join(out_dir, "blur_gpu.png")
    diff_path = os.path.join(out_dir, "blur_diff.png")
    cpu.save(cpu_path)
    gpu.save(gpu_path)
    Image.fromarray(np.clip(diff * 8.0, 0, 255).astype("u1"), "L").save(diff_path)

    result = {
        "available": True, "status": status, "radius": radius,
        "mean_diff": float(diff.mean()), "max_diff": float(diff.max()),
        "cpu_path": cpu_path, "gpu_path": gpu_path, "diff_path": diff_path,
        "out_dir": out_dir,
    }

    # ── Chromatic aberration parity (linear shift) ───────────────────────────
    # Asymmetric RGBA test so a wrong direction / flip / channel shows up big.
    rgba = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dd = ImageDraw.Draw(rgba)
    dd.ellipse([size * 0.25, size * 0.2, size * 0.7, size * 0.65], fill=(255, 255, 255, 255))
    dd.rectangle([size * 0.1, size * 0.7, size * 0.4, size * 0.9], fill=(255, 255, 255, 255))
    specs = [((255, 0, 0), (6.0, 2.0), 1.0),
             ((0, 255, 0), (0.0, 0.0), 1.0),
             ((0, 0, 255), (-6.0, -2.0), 1.0)]
    gpu_ca = gpu_chromatic_aberration(rgba, "linear", specs)
    if gpu_ca is not None:
        src = np.asarray(rgba, dtype=np.float32)
        H, W = size, size
        ref = np.zeros((H, W, 4), np.float32)
        aA = np.zeros((H, W), np.float32)
        ch_idx = [0, 1, 2]
        for (tint, (dx, dy), _sc), ci in zip(specs, ch_idx):
            ys, xs = np.mgrid[0:H, 0:W]
            sx = xs - int(round(dx)); sy = ys - int(round(dy))
            valid = (sx >= 0) & (sx < W) & (sy >= 0) & (sy < H)
            sxc = np.clip(sx, 0, W - 1); syc = np.clip(sy, 0, H - 1)
            samp = src[syc, sxc] * valid[..., None]
            chan = samp[..., ci] / 255.0
            ref[..., 0] += (tint[0] / 255.0) * chan
            ref[..., 1] += (tint[1] / 255.0) * chan
            ref[..., 2] += (tint[2] / 255.0) * chan
            aA = np.maximum(aA, samp[..., 3] / 255.0)
        ref[..., 3] = aA
        ref = np.clip(ref * 255.0, 0, 255)
        g = np.asarray(gpu_ca, dtype=np.float32)
        cad = np.abs(ref - g)
        ca_cpu = os.path.join(out_dir, "ca_ref.png")
        ca_gpu = os.path.join(out_dir, "ca_gpu.png")
        ca_diff = os.path.join(out_dir, "ca_diff.png")
        Image.fromarray(ref.astype("u1"), "RGBA").save(ca_cpu)
        gpu_ca.save(ca_gpu)
        Image.fromarray(np.clip(cad[..., :3].max(2) * 8.0, 0, 255).astype("u1"), "L").save(ca_diff)
        result["ca_mean_diff"] = float(cad.mean())
        result["ca_max_diff"] = float(cad.max())

    # ── Long-shadow loft sweep parity ────────────────────────────────────────
    # Asymmetric silhouette + a diagonal throw so a wrong direction / flip shows
    # up big. Compare GPU (cov, tmap) against the CPU sweep step-for-step.
    try:
        sil = Image.new("L", (size, size), 0)
        ds = ImageDraw.Draw(sil)
        ds.rectangle([size * 0.22, size * 0.22, size * 0.42, size * 0.6], fill=255)
        ds.rectangle([size * 0.22, size * 0.22, size * 0.6, size * 0.32], fill=255)
        ds.ellipse([size * 0.5, size * 0.5, size * 0.62, size * 0.62], fill=255)
        dxu, dyu = math.cos(math.radians(315)), -math.sin(math.radians(315))
        L = size * 0.45; taper = 0.5; N = 80
        gpu_sw = gpu_long_shadow_sweep(sil, dxu, dyu, L, taper, N, 12.0 / 255.0)
        if gpu_sw is not None:
            gcov, gtmap = gpu_sw
            A0 = np.asarray(sil, np.float32)
            yy, xx = np.where(A0 > 40)
            cx = float((xx.min() + xx.max()) / 2.0); cy = float((yy.min() + yy.max()) / 2.0)
            ccov = np.zeros((size, size), np.float32); ctmap = np.ones((size, size), np.float32)
            for i in range(N + 1):
                t = i / float(N); s = 1.0 + (taper - 1.0) * t
                if s <= 0.02:
                    continue
                a = 1.0 / s
                c = cx * (1.0 - a) - dxu * L * t * a
                f = cy * (1.0 - a) - dyu * L * t * a
                la = np.asarray(sil.transform((size, size), Image.AFFINE, (a, 0.0, c, 0.0, a, f),
                                              resample=Image.BILINEAR), np.float32)
                nc = la > 12.0; ctmap = np.where(nc & (t < ctmap), t, ctmap); ccov = np.maximum(ccov, la)
            covd = np.abs(ccov - gcov); tmd = np.abs(ctmap - gtmap)
            Image.fromarray(np.clip(ccov, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "loft_cov_cpu.png"))
            Image.fromarray(np.clip(gcov, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "loft_cov_gpu.png"))
            Image.fromarray(np.clip(covd * 4.0, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "loft_cov_diff.png"))
            result["loft_cov_mean_diff"] = float(covd.mean())
            result["loft_cov_max_diff"] = float(covd.max())
            result["loft_tmap_mean_diff"] = float(tmd.mean())
            result["loft_tmap_max_diff"] = float(tmd.max())
    except Exception as _e:
        result["loft_error"] = f"{type(_e).__name__}: {_e}"

    # ── Halftone parity (CPU loop vs GPU instanced stamping) ─────────────────
    try:
        from edof.engine.renderer import _render_halftone_mosaic
        from edof.format.styles import LayerEffect
        bw = bh = size
        yy, xx = np.mgrid[0:bh, 0:bw].astype(np.float32)
        rr = np.sqrt((xx - bw / 2) ** 2 + (yy - bh / 2) ** 2)
        disk = (rr < size * 0.42).astype(np.float32)
        rgb = np.zeros((bh, bw, 3), np.float32)
        rgb[..., 0] = 120 + 100 * (xx / bw); rgb[..., 1] = 80 + 120 * (yy / bh)
        rgb[..., 2] = 200 - 120 * (xx / bw)
        aim = (disk * 255).astype("u1")
        obj = Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype("u1"), aim]), "RGBA")
        al = Image.fromarray(aim, "L")
        e = LayerEffect(type="halftone", enabled=True)
        e.ht_dot = 1.6; e.ht_color_mode = "cmyk"; e.ht_shape = "circle"
        sv = is_enabled()
        set_enabled(False)
        cpu_h = np.asarray(_render_halftone_mosaic(obj, al, e, 200, bw, bh), np.float32)
        set_enabled(True)
        gpu_h = np.asarray(_render_halftone_mosaic(obj, al, e, 200, bw, bh), np.float32)
        set_enabled(sv)
        hd = np.abs(cpu_h - gpu_h)
        Image.fromarray(cpu_h.astype("u1"), "RGBA").save(os.path.join(out_dir, "ht_cpu.png"))
        Image.fromarray(gpu_h.astype("u1"), "RGBA").save(os.path.join(out_dir, "ht_gpu.png"))
        Image.fromarray(np.clip(hd[..., :3].max(2) * 4.0, 0, 255).astype("u1"), "L").save(
            os.path.join(out_dir, "ht_diff.png"))
        result["ht_mean_diff"] = float(hd.mean())
        result["ht_max_diff"] = float(hd.max())
    except Exception as _e:
        result["ht_error"] = f"{type(_e).__name__}: {_e}"

    # ── Variable box blur parity (CPU SAT vs GPU SAT-scan) ───────────────────
    # Shadow-like data: a soft slab + linearly growing radius. float32 addition
    # order differs (sequential cumsum vs Hillis-Steele tree), so a tiny diff
    # (mean well under 0.1) is expected and invisible; structure must match.
    try:
        H = W = size
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        Aa = np.zeros((H, W), np.float32)
        Aa[int(H * 0.15):int(H * 0.7), int(W * 0.12):int(W * 0.8)] = 255.0
        Aa *= np.clip(1.0 - (xx - W * 0.12) / (W * 0.7), 0.2, 1.0)
        rmap = np.clip(np.round((xx / W) * (size * 0.12)), 0,
                       min(H, W) // 2).astype(np.int64)
        gpu_vb = gpu_variable_box_blur(Aa, rmap)
        if gpu_vb is not None:
            y1 = np.clip(np.mgrid[0:H, 0:W][0] - rmap, 0, H)
            y2 = np.clip(np.mgrid[0:H, 0:W][0] + rmap + 1, 0, H)
            x1 = np.clip(np.mgrid[0:H, 0:W][1] - rmap, 0, W)
            x2 = np.clip(np.mgrid[0:H, 0:W][1] + rmap + 1, 0, W)
            area = ((y2 - y1) * (x2 - x1)).astype(np.float32)
            cpu_vb = Aa.copy()
            for _ in range(4):
                sat = np.zeros((H + 1, W + 1), np.float32)
                np.cumsum(np.cumsum(cpu_vb, 0), 1, out=sat[1:, 1:])
                cpu_vb = (sat[y2, x2] - sat[y1, x2] - sat[y2, x1] + sat[y1, x1]) / area
            vbd = np.abs(cpu_vb - gpu_vb)
            Image.fromarray(np.clip(cpu_vb, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "vb_cpu.png"))
            Image.fromarray(np.clip(gpu_vb, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "vb_gpu.png"))
            Image.fromarray(np.clip(vbd * 16.0, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "vb_diff.png"))
            result["vb_mean_diff"] = float(vbd.mean())
            result["vb_max_diff"] = float(vbd.max())
    except Exception as _e:
        result["vb_error"] = f"{type(_e).__name__}: {_e}"

    # ── Long-shadow ray field parity (GPU kernel vs exact numpy reference) ───
    # The GPU computes the EXACT per-row max-convolution; the reference here is
    # the brute-force numpy evaluation on a small case. The LUT is LINEAR
    # filtered, so a sub-1/255 interpolation difference is expected; structure
    # must match (mean well under 0.05, max under 1.0).
    try:
        Hs = Ws = 128
        Lf = 48
        rng = np.random.default_rng(7)
        Rf = np.zeros((Hs, Ws), np.float32)
        Rf[30:90, 12:40] = 255.0
        Rf[50:70, 50:58] = 120.0           # semi-transparent emitter
        Rf[20:24, 70:74] = 60.0            # faint isolated emitter
        Rf[30:90, 12:14] = rng.uniform(40, 255, (60, 2)).astype(np.float32)
        ts_ = np.linspace(0.0, 1.0, 1024).astype(np.float32)
        lutf = (0.25 + 0.75 * np.abs(np.cos(ts_ * 3.0))).astype(np.float32)  # non-monotone
        gpu_f = gpu_long_shadow_field(Rf, Lf, lutf)
        if gpu_f is not None:
            ref = np.zeros_like(Rf)
            for d in range(Lf + 1):
                a = float(np.interp((d / Lf) * 0.999023 + 0.000488, ts_, lutf))
                if d == 0:
                    np.maximum(ref, Rf * a, out=ref)
                else:
                    np.maximum(ref[:, d:], Rf[:, :-d] * a, out=ref[:, d:])
            lsd = np.abs(ref - gpu_f)
            Image.fromarray(np.clip(ref, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "lsf_cpu.png"))
            Image.fromarray(np.clip(gpu_f, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "lsf_gpu.png"))
            Image.fromarray(np.clip(lsd * 16.0, 0, 255).astype("u1"), "L").save(os.path.join(out_dir, "lsf_diff.png"))
            result["lsf_mean_diff"] = float(lsd.mean())
            result["lsf_max_diff"] = float(lsd.max())
    except Exception as _e:
        result["lsf_error"] = f"{type(_e).__name__}: {_e}"

    return result


def _cli():
    res = selftest(size=512, radius=8.0)
    print(gpu_status())
    if not res.get("available"):
        print("GPU unavailable -> CPU-only. Install: pip install moderngl")
        return
    if res.get("error"):
        print("error:", res["error"]); return
    print(f"Gaussian blur radius {res['radius']:g}px: "
          f"mean diff {res['mean_diff']:.3f}, max diff {res['max_diff']:.1f}")
    if "ca_mean_diff" in res:
        print(f"Chromatic aberration: "
              f"mean diff {res['ca_mean_diff']:.3f}, max diff {res['ca_max_diff']:.1f}")
    print("images:", res["out_dir"])


if __name__ == "__main__":
    _cli()
