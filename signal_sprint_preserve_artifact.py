"""Copy Signal Sprint's original GitHub Actions ZIP without rebuilding or repacking.

The caller chooses an existing, durable destination directory. The original
archive is validated against hard-coded Factory provenance before copying.
No GitHub, Partner Center, CAS, SDK, or Store operations occur.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile

from gdk_build_intake import ARTIFACT_SHA256, EXE_SHA256, inspect_pinned_artifact
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

ARCHIVE_NAME = "signal-sprint-original-github-artifact-12706862577.zip"
ARTIFACT_ID = 12706862577
MANIFEST_NAME = ARCHIVE_NAME + ".integrity.json"


def _reject_redirected_path(path: Path, label: str) -> None:
    """Reject ancestor symlinks and Windows junctions before copying evidence.

    Checking only destination_dir.is_symlink() misses a linked *parent*
    directory, allowing an apparently owner-managed backup to be redirected.
    Recheck again after the copy; this is not a substitute for trusted storage.
    """
    for component in (path, *path.parents):
        try:
            linked = component.is_symlink()
            junction = getattr(component, "is_junction", lambda: False)()
        except (OSError, RuntimeError) as exc:
            raise HoldError(label + " path cannot be inspected") from exc
        if linked or junction:
            raise ConflictError(label + " contains a symlink or junction")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _preserve_integrity_manifest(destination_dir: Path, snapshot: bytes) -> tuple[Path, str]:
    """Store portable, byte-stable backup evidence beside the original ZIP.

    Exclusive creation never overwrites an existing manifest. A retry verifies
    exact canonical bytes, including all fail-closed gate states, before PASS.
    """
    manifest_path = destination_dir / MANIFEST_NAME
    _reject_redirected_path(manifest_path, "Preservation manifest")
    payload = {
        "schema_version": 1,
        "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "immutable_source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "original_github_artifact_id": ARTIFACT_ID,
        "archive_name": ARCHIVE_NAME,
        "archive_size_bytes": len(snapshot),
        "archive_sha256": ARTIFACT_SHA256,
        "executable_name": "SignalSprint.exe",
        "executable_sha256": EXE_SHA256,
        "signature_status": "QA_UNSIGNED",
        "cas_return_pass": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
    }
    raw = (json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")) + "\n").encode("utf-8")

    def verify() -> None:
        _reject_redirected_path(manifest_path, "Preservation manifest")
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ConflictError("Preservation manifest missing, linked or not a regular file")
        if manifest_path.read_bytes() != raw:
            raise ConflictError("Preservation manifest conflicts with pinned original; refusing overwrite")
        _reject_redirected_path(manifest_path, "Preservation manifest")

    if manifest_path.exists() or manifest_path.is_symlink():
        verify()
    else:
        created = False
        try:
            with manifest_path.open("xb") as writer:
                created = True
                writer.write(raw)
                writer.flush()
                os.fsync(writer.fileno())
        except FileExistsError:
            verify()
        except BaseException:
            # Keep a verified ZIP even if manifest creation fails. A later
            # idempotent retry may finish the evidence without replacing ZIP.
            if created:
                manifest_path.unlink(missing_ok=True)
            raise
        verify()
    return manifest_path, _hash(raw)


def preserve(source: Path, destination_dir: Path) -> dict:
    """Create the verified original ZIP once; never overwrite a different file."""
    _reject_redirected_path(source, "Original artifact")
    _reject_redirected_path(destination_dir / ARCHIVE_NAME, "Preservation destination")
    inspect_pinned_artifact(source)
    snapshot = source.read_bytes()
    if _hash(snapshot) != ARTIFACT_SHA256:
        raise ConflictError("Original artifact changed after provenance validation")
    if destination_dir.is_symlink() or not destination_dir.is_dir():
        raise HoldError("Owner-managed destination directory must exist and not be linked")
    target = destination_dir / ARCHIVE_NAME
    if target.resolve() == source.resolve():
        raise ConflictError("Original artifact and preservation target must be distinct")

    def verify_existing() -> str:
        _reject_redirected_path(target, "Preservation target")
        if target.is_symlink() or not target.is_file():
            raise ConflictError("Preservation target is linked or not a regular file")
        if _hash(target.read_bytes()) != ARTIFACT_SHA256:
            raise ConflictError("Preservation target contains different bytes; refusing overwrite")
        inspect_pinned_artifact(target)
        return "EXISTING_VERIFIED"

    if target.exists() or target.is_symlink():
        status = verify_existing()
    else:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".signal-sprint-", suffix=".tmp",
                                             dir=destination_dir, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(snapshot)
                handle.flush()
                os.fsync(handle.fileno())
            if _hash(temporary.read_bytes()) != ARTIFACT_SHA256:
                raise ConflictError("Temporary preservation copy differs from original")
            try:
                # Exclusive hard-link creation is atomic and never overwrites an
                # existing target, including one created by a competing run.
                os.link(temporary, target)
                status = "PRESERVED_VERIFIED"
            except FileExistsError:
                status = verify_existing()
            except OSError as exc:
                # exFAT/FAT and some synced folders cannot create hard links.
                # Fall back to exclusive creation, never replacing a target.
                unsupported = {errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP, errno.ENOTSUP}
                if exc.errno not in unsupported:
                    raise
                created = False
                try:
                    with target.open("xb") as output:
                        created = True
                        output.write(snapshot)
                        output.flush()
                        os.fsync(output.fileno())
                    status = "PRESERVED_VERIFIED"
                except FileExistsError:
                    status = verify_existing()
                except BaseException:
                    if created:
                        target.unlink(missing_ok=True)
                    raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        _reject_redirected_path(source, "Original artifact")
        _reject_redirected_path(target, "Preservation target")
        verify_existing()
    # A successful backup is two verified files, not a ZIP plus ephemeral
    # stdout. Preserve the manifest on first copy and idempotent reruns.
    manifest_path, manifest_sha = _preserve_integrity_manifest(destination_dir, snapshot)
    _reject_redirected_path(target, "Preservation target")
    verify_existing()
    return {
        "schema_version": 1,
        "status": status,
        "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "original_github_artifact_id": ARTIFACT_ID,
        "archive_name": ARCHIVE_NAME,
        "archive_sha256": ARTIFACT_SHA256,
        "archive_size_bytes": len(snapshot),
        "destination": str(target),
        "integrity_manifest": str(manifest_path),
        "integrity_manifest_sha256": manifest_sha,
        "rebuild_performed": False,
        "cas_return_pass": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", type=Path, required=True)
    parser.add_argument("--destination-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = preserve(args.original_zip, args.destination_dir)
    except (ConflictError, HoldError, OSError, ValueError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "HOLD"),
                          "error": str(exc), "real_msix_pass": False,
                          "store_submitted": False}, ensure_ascii=False))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
