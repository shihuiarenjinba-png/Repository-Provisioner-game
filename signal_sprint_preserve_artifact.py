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

from gdk_build_intake import ARTIFACT_SHA256, inspect_pinned_artifact
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

ARCHIVE_NAME = "signal-sprint-original-github-artifact-12706862577.zip"
ARTIFACT_ID = 12706862577


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preserve(source: Path, destination_dir: Path) -> dict:
    """Create the verified original ZIP once; never overwrite a different file."""
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
