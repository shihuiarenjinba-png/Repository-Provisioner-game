"""Discover an installed Windows GDK makepkg without installing or running it.

Discovery is not approval. Callers MUST compare the selected executable's bytes
with an independently approved SHA-256 immediately before execution.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import stat

from package_identity_provisioner import ConflictError, HoldError


def _candidates() -> list[Path]:
    paths: list[Path] = []
    on_path = shutil.which("makepkg.exe")
    if on_path:
        paths.append(Path(on_path))
    # shutil.which returns only the FIRST PATH hit. A second installed SDK
    # must not be silently ignored: enumerate bounded, explicit PATH entries.
    # Empty/relative entries are deliberately ignored (no current-dir lookup).
    for entry in os.environ.get("PATH", "").split(";"):
        directory = Path(entry.strip().strip('"'))
        if entry.strip() and directory.is_absolute():
            paths.append(directory / "makepkg.exe")
    for name in ("GameDK", "GameDKCoreLatest"):
        root = os.environ.get(name)
        if root:
            paths.append(Path(root) / "bin" / "makepkg.exe")
    gdk_bin = os.environ.get("GDK_BIN")
    if gdk_bin:
        paths.append(Path(gdk_bin) / "makepkg.exe")
    program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    paths.append(Path(program_files) / "Microsoft GDK" / "bin" / "makepkg.exe")
    return paths


def _regular_executable(path: Path) -> Path | None:
    # Missing candidates are normal; linked or special files are not.
    if not path.exists() and not path.is_symlink():
        return None
    # Windows junctions/reparse-point parents are not an approved SDK root.
    # Check the whole path, not only makepkg.exe itself, before resolving it.
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
            raise ConflictError("GDK makepkg candidate linked parent or executable")
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ConflictError("GDK makepkg candidate is not a regular file")
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ConflictError("GDK makepkg candidate cannot be resolved") from exc


def discover_makepkg(explicit_path: Path | None = None) -> Path:
    """Fail closed if zero/multiple distinct tools; explicit path resolves ambiguity.

    Neither environment variables nor PATH prove SDK provenance. This helper
    never executes a candidate and never supplies a trusted digest.
    """
    if platform.system() != "Windows":
        raise HoldError("GDK SDK execution requires Windows")
    if explicit_path is not None:
        selected = _regular_executable(Path(explicit_path))
        if selected is None:
            raise HoldError("explicit GDK makepkg.exe path does not exist")
        return selected
    found: dict[str, Path] = {}
    for candidate in _candidates():
        selected = _regular_executable(candidate)
        if selected is not None:
            found.setdefault(str(selected).casefold(), selected)
    if not found:
        raise HoldError("GDK makepkg.exe not discovered on PATH or known GDK install locations")
    if len(found) != 1:
        raise HoldError("multiple GDK makepkg.exe candidates; use --makepkg-path with an independently approved SHA-256")
    return next(iter(found.values()))
