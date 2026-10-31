"""Read-only, restart-safe verification of a preserved Signal Sprint GDK artifact.

Unlike the preservation command, this requires no original Actions download.
It never creates or repairs files, runs CAS/SDK, or claims Store readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from package_identity_provisioner import ConflictError, HoldError
import signal_sprint_preserve_artifact as preservation

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024


def _read_stable(path: Path, label: str, limit: int) -> bytes:
    preservation._reject_redirected_path(path, label)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ConflictError(label + " missing, non-regular or invalid size")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ConflictError(label + " changed before opening")
            raw = stream.read(limit + 1)
        after = path.lstat()
    except FileNotFoundError as exc:
        raise HoldError(label + " missing") from exc
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ) or len(raw) != before.st_size:
        raise ConflictError(label + " changed while reading")
    preservation._reject_redirected_path(path, label)
    return raw


def verify_backup(destination_dir: Path) -> dict:
    archive = destination_dir / preservation.ARCHIVE_NAME
    manifest = destination_dir / preservation.MANIFEST_NAME
    preservation._reject_redirected_path(archive, "Backup ZIP")
    preservation._reject_redirected_path(manifest, "Backup manifest")
    if not destination_dir.is_dir():
        raise HoldError("Backup directory missing")

    snapshot = _read_stable(archive, "Backup ZIP", MAX_ARCHIVE_BYTES)
    if hashlib.sha256(snapshot).hexdigest() != preservation.ARTIFACT_SHA256:
        raise ConflictError("Backup ZIP differs from pinned original")
    # Reuse the existing authoritative ZIP member, CRC and provenance checks.
    preservation.inspect_pinned_artifact(archive)
    if _read_stable(archive, "Backup ZIP", MAX_ARCHIVE_BYTES) != snapshot:
        raise ConflictError("Backup ZIP changed during provenance verification")

    expected = {
        "schema_version": 1,
        "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "request_id": preservation.PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "immutable_source_sha": preservation.PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "original_github_artifact_id": preservation.ARTIFACT_ID,
        "archive_name": preservation.ARCHIVE_NAME,
        "archive_size_bytes": len(snapshot),
        "archive_sha256": preservation.ARTIFACT_SHA256,
        "executable_name": "SignalSprint.exe",
        "executable_sha256": preservation.EXE_SHA256,
        "signature_status": "QA_UNSIGNED",
        "cas_return_pass": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
    }
    canonical = (json.dumps(expected, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":")) + "\n").encode("utf-8")
    raw_manifest = _read_stable(manifest, "Backup manifest", MAX_MANIFEST_BYTES)
    if raw_manifest != canonical:
        raise ConflictError("Backup manifest differs from pinned provenance; no repair attempted")
    return {
        "schema_version": 1,
        "status": "SIGNAL_SPRINT_BACKUP_READ_ONLY_VERIFIED",
        "partner_center_selection": "GDK_GAME",
        "request_id": expected["request_id"],
        "source_sha": expected["immutable_source_sha"],
        "archive_sha256": expected["archive_sha256"],
        "archive_size_bytes": len(snapshot),
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "rebuild_performed": False,
        "cas_return_pass": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_backup(args.destination_dir)
    except (ConflictError, HoldError, OSError, ValueError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "HOLD"),
                          "error": str(exc), "real_msix_pass": False,
                          "store_submitted": False}, ensure_ascii=False))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
