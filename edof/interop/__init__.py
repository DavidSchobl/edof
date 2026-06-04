"""Interop with foreign document formats.

v4.1.24.0: first-pass DOCX (Microsoft Word) import/export. See docx_io.

Kept in its own package (not in edof.format) because it depends on both
format and engine (pagination) and on the optional third-party python-docx
library, which the core format must never require.
"""
