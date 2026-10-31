"""Restore Signal Sprint's exact pinned ZIP from a rescued Actions wrapper.

Offline fail-closed preservation; never runs CAS, rebuilds, invokes GDK or Store.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import zipfile

from gdk_build_intake import ARTIFACT_SHA256, inspect_pinned_artifact
from package_identity_provisioner import ConflictError, HoldError
from signal_sprint_preserve_artifact import (
    ARCHIVE_NAME, _reject_redirected_path, preserve,
)

NESTED = "signal-sprint-exact-archive/" + ARCHIVE_NAME
DIRECT = {
    "signal-sprint-original/SignalSprint.exe":
        "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad",
    "signal-sprint-original/provenance.json":
        "797f8d9f93846a55ab32143b3d957e041f2516547cd850babe75131cb2f0fe96",
    "signal-sprint-original/provisioner-request.json":
        "79375be526d4dbdb477d241cc0c168c6514d2d1ccc99e2f46bf2775524284a43",
}
ALLOWED_DIRS = {"signal-sprint-exact-archive/", "signal-sprint-original/"}
MAX_WRAPPER_BYTES = 120_000_000
MAX_MEMBER_BYTES = 45_000_000


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def restore(wrapper: Path, destination_dir: Path) -> dict:
    """Verify rescued wrapper, then preserve only the exact nested ZIP."""
    _reject_redirected_path(wrapper, "Rescued wrapper")
    _reject_redirected_path(destination_dir / ARCHIVE_NAME, "Preservation destination")
    if not wrapper.is_file() or not 0 < wrapper.stat().st_size <= MAX_WRAPPER_BYTES:
        raise HoldError("Rescued Actions wrapper missing or oversized")
    if not destination_dir.is_dir():
        raise HoldError("Owner-managed preservation directory must exist")
    outer = wrapper.read_bytes()
    try:
        with zipfile.ZipFile(io.BytesIO(outer)) as archive:
            entries = archive.infolist()
            files = {NESTED, *DIRECT}
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or set(names) - files - ALLOWED_DIRS or not files.issubset(names):
                raise ConflictError("Rescue wrapper contains missing, duplicate or unexpected entries")
            for entry in entries:
                if entry.filename in ALLOWED_DIRS:
                    if not entry.is_dir() or entry.file_size:
                        raise ConflictError("Rescue wrapper has malformed directory entry")
                    continue
                mode = entry.external_attr >> 16
                if (entry.is_dir() or (entry.create_system == 3 and
                    stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or
                    entry.file_size <= 0 or entry.file_size > MAX_MEMBER_BYTES):
                    raise ConflictError("Rescue wrapper has unsafe member")
            if archive.testzip() is not None:
                raise ConflictError("Rescue wrapper CRC mismatch")
            nested = archive.read(NESTED)
            if _sha(nested) != ARTIFACT_SHA256:
                raise ConflictError("Rescued nested original ZIP SHA-256 mismatch")
            with zipfile.ZipFile(io.BytesIO(nested)) as original:
                if set(original.namelist()) != {Path(name).name for name in DIRECT} or len(original.infolist()) != 3:
                    raise ConflictError("Rescued original ZIP inventory mismatch")
                for name, expected in DIRECT.items():
                    direct = archive.read(name)
                    inner = original.read(Path(name).name)
                    if _sha(direct) != expected or direct != inner:
                        raise ConflictError("Rescued member differs from pinned original: " + name)
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise ConflictError("Rescue wrapper ZIP is corrupt") from exc
    _reject_redirected_path(wrapper, "Rescued wrapper")
    if _sha(wrapper.read_bytes()) != _sha(outer):
        raise ConflictError("Rescue wrapper changed during verification")
    with tempfile.TemporaryDirectory(prefix=".signal-sprint-rescue-", dir=destination_dir) as tmp:
        original_path = Path(tmp) / ARCHIVE_NAME
        with original_path.open("xb") as output:
            output.write(nested)
        inspect_pinned_artifact(original_path)
        result = preserve(original_path, destination_dir)
    result["source"] = "RESCUED_ACTIONS_WRAPPER_EXACT_NESTED_ORIGINAL"
    result["wrapper_sha256"] = _sha(outer)
    result["wrapper_checked"] = True
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rescue-wrapper-zip", type=Path, required=True)
    parser.add_argument("--destination-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = restore(args.rescue_wrapper_zip, args.destination_dir)
    except (ConflictError, HoldError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "HOLD"), "error": str(exc),
                          "real_msix_pass": False, "store_submitted": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
