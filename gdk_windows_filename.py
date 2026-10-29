"""Conservative Windows filename contract for Signal Sprint GDK transfers.

Reject ambiguous names *before* any SDK output is copied across filesystems.
This does not prove that a GDK package is authentic or ready for submission.
"""
from __future__ import annotations

import unicodedata

from package_identity_provisioner import ConflictError

_FORBIDDEN = frozenset('<>:"/\\|?*')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    prefix + str(n) for prefix in ("COM", "LPT") for n in range(1, 10)
} | {
    prefix + digit for prefix in ("COM", "LPT") for digit in ("¹", "²", "³")
}


def validate_windows_basename(name: str, label: str) -> None:
    """Fail closed on Win32 devices, ADS, separators and ambiguous basenames."""
    if (type(name) is not str or not name or len(name) > 240
            or name in (".", "..") or name.endswith((" ", "."))
            or any(c in _FORBIDDEN or ord(c) < 32 for c in name)
            or unicodedata.normalize("NFC", name).split(".", 1)[0].upper() in _RESERVED):
        raise ConflictError(label + " unsafe Windows filename")


def validate_unique_windows_names(names, label: str) -> None:
    """Conservatively reject NFC/casefold aliases before Windows transport."""
    seen = set()
    for name in names:
        validate_windows_basename(name, label)
        key = unicodedata.normalize("NFC", name).casefold()
        if key in seen:
            raise ConflictError(label + " Windows case-insensitive filename collision")
        seen.add(key)
