# edof/engine/debug_log.py
"""Lightweight, opt-in debug logger.

Disabled by default. Enable it either by setting the environment variable
EDOF_DEBUG=1 before launching, or programmatically via enable() (e.g. from a
debug menu). When enabled the log is written to EDOF_DEBUG_PATH if set,
otherwise to 'edof_debug.log' in the user's home directory. Output is
ASCII-safe and UTF-8 encoded so it never fails on non-ASCII content.
"""
import os
import time
import threading


def _default_path() -> str:
    """A log location that is easy to find on every OS (user home directory)."""
    home = os.path.expanduser('~')
    return os.path.join(home, 'edof_debug.log')


def _env_enabled() -> bool:
    # Be forgiving: a launcher may accidentally append a trailing comment
    # (e.g. Windows Batch "set EDOF_DEBUG=1  REM ..." stores the whole rest of
    # the line). Only the FIRST whitespace-separated token decides truthiness,
    # so a stray comment can never silently disable logging again.
    raw = os.environ.get('EDOF_DEBUG', '').strip().lower()
    if not raw:
        return False
    token = raw.split()[0].strip(' \t",;')
    return token in ('1', 'true', 'yes', 'on')


ENABLED = _env_enabled()      # off unless explicitly opted in
LOG_PATH = os.environ.get('EDOF_DEBUG_PATH') or _default_path()

_lock = threading.Lock()
_file = None
_t0 = time.monotonic()


def _ensure_file():
    global _file
    if _file is not None: return _file
    try:
        # encoding='utf-8' so writes never blow up on a non-ASCII char.
        # buffering=1 -> line-buffered, so each line is flushed when written.
        _file = open(LOG_PATH, 'a', encoding='utf-8', buffering=1)
        _file.write(f"\n====== Session start {time.ctime()} ======\n")
        try:
            import sys, platform
            try: import edof; ver = edof.__version__
            except Exception: ver = "?"
            _file.write(f"edof_version={ver}\n")
            _file.write(f"python={sys.version.split()[0]}  platform={platform.platform()}\n")
        except Exception:
            pass
    except Exception as e:
        # If the home dir is not writable, fall back to the temp directory.
        try:
            import tempfile
            _file = open(os.path.join(tempfile.gettempdir(), 'edof_debug.log'),
                          'a', encoding='utf-8', buffering=1)
            _file.write(f"\n====== Session start {time.ctime()} ({e}) ======\n")
        except Exception:
            _file = None
    return _file


def log(tag: str, **fields) -> None:
    """Log one event. Cheap no-op when disabled."""
    if not ENABLED: return
    with _lock:
        f = _ensure_file()
        if f is None: return
        try:
            t_ms = (time.monotonic() - _t0) * 1000.0
            parts = []
            for k, v in fields.items():
                if isinstance(v, str):
                    if len(v) > 60:
                        v = v[:30] + "..." + v[-25:]
                    s = repr(v)   # makes newlines/tabs visible
                else:
                    s = str(v)
                parts.append(f"{k}={s}")
            line = f"[{t_ms:8.1f}] {tag:30s} {' '.join(parts)}\n"
            f.write(line)
        except Exception:
            pass


def enable(path: str = None):
    """Programmatic enable (e.g. from a debug menu)."""
    global ENABLED, LOG_PATH, _file
    ENABLED = True
    if path: LOG_PATH = path
    _file = None    # reopen
    log("LOG.ENABLED")


def disable():
    """Programmatic disable."""
    global ENABLED
    ENABLED = False


def is_enabled() -> bool:
    return ENABLED


def current_path() -> str:
    return LOG_PATH
