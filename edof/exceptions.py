# edof/exceptions.py
"""All custom exceptions and warnings used by the edof library."""

from __future__ import annotations
import warnings


# ── Exceptions ────────────────────────────────────────────────────────────────

class EdofError(Exception):
    """Base exception – catch this to handle any edof error."""


class EdofVersionError(EdofError):
    """File format version is completely incompatible with this library."""


class EdofResourceError(EdofError):
    """A resource (font, image, …) cannot be found or loaded."""


class EdofRenderError(EdofError):
    """Error during rendering or export."""


class EdofVariableError(EdofError):
    """Variable undefined, wrong type, or invalid value."""


class EdofAPIError(EdofError):
    """Invalid API command name or parameters."""


class EdofValidationError(EdofError):
    """Document or object fails structural validation."""


class EdofPrintError(EdofError):
    """Printing failed or no printer available."""


# ── Warnings (non-fatal – stored in error-state, never block execution) ───────

class EdofNewerVersionWarning(UserWarning):
    """
    File was saved by a newer version of edof.
    The document may render incorrectly; update the library.
    """


class EdofMissingOptionalWarning(UserWarning):
    """An optional feature (PDF export, QR, PyQt6) is unavailable."""


class EdofResourceWarning(UserWarning):
    """A resource is missing but a fallback was used."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def warn_newer_version(file_version: str) -> None:
    """Issue EdofNewerVersionWarning.  Called from serializer on load."""
    warnings.warn(
        f"[edof] This file was created with format version {file_version}. "
        f"The installed library may not support all features. "
        f"Run  pip install --upgrade edof  to get the latest version.",
        EdofNewerVersionWarning,
        stacklevel=3,
    )


def warn_missing(feature: str, install_extra: str = "") -> None:
    hint = f"  Run: pip install edof[{install_extra}]" if install_extra else ""
    warnings.warn(
        f"[edof] Optional feature '{feature}' is not available.{hint}",
        EdofMissingOptionalWarning,
        stacklevel=3,
    )
