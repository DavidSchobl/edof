# edof/utils/links.py
"""Shared hyperlink validation (v4.4.0).

One place that decides what a TextRun.link may contain, used by the editor
(creating links), the viewers (following links) and the exporters (emitting
them into PDF/SVG). The whitelist is deliberately small: http, https, mailto
and in-document anchors ("#<anchor_id>"). Everything else (javascript:,
file:, ftp:, data:, vbscript:, empty strings, free text with spaces) is
rejected, because an exported or followed link is an XSS / phishing /
local-file disclosure vector.
"""
from __future__ import annotations

from typing import Optional

ALLOWED_SCHEMES = ("http", "https", "mailto")


def validate_link(link) -> Optional[str]:
    """Return the cleaned link string, or None when the value must not be
    used as a link.

    Accepted forms:
      - "#<anchor_id>"           in-document jump (non-empty id)
      - "http://…", "https://…"  external URL
      - "mailto:…"               e-mail
      - "example.com/page"       bare domain, normalized to https://
    """
    if link is None:
        return None
    link = str(link).strip()
    if not link:
        return None
    if link.startswith("#"):
        return link if len(link) > 1 else None
    low = link.lower()
    for sch in ALLOWED_SCHEMES:
        if low.startswith(sch + ":"):
            return link
    # A bare domain (no scheme anywhere before the first slash, at least one
    # dot, no whitespace) is a common paste; normalize it to https://.
    head = link.split("/", 1)[0]
    if ":" not in head and "." in head and not any(c.isspace() for c in link):
        return "https://" + link
    return None


def is_internal_link(link) -> bool:
    """True for an in-document anchor jump ('#<anchor_id>')."""
    return bool(link) and str(link).startswith("#") and len(str(link)) > 1
