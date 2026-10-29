"""Fail-closed Signal Sprint GDK byte handoff for the Windows/E2E owner.

Copies only the already-verified SDK package and validation log to an isolated
handoff folder. This is NOT a Store package approval, SDK attestation, install
QA result, or Windows-all-auto central queue write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from gdk_sdk_result_intake import (
    MAX_JSON, MAX_LOG, MAX_PACKAGE, MAX_SIDECAR, MAX_OUTPUT_FILES,
    _hash_file, _read_json, intake,
)
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB,
)

CHUNK = 1024 * 1024


def _copy_verified(source: Path, target: Path, expected_sha: str, expected_size: int,
                   maximum: int, label: str) -> None:
    """Copy once, reject source swaps/edits and verify destination bytes."""
    before = source.lstat()
    if source.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
        raise ConflictError(label + " source changed before copy")
    digest = hashlib.sha256()
    copied = 0
    with source.open("rb") as reader, target.open("xb") as writer:
        opened = os.fstat(reader.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ConflictError(label + " source replaced before open")
        while True:
            chunk = reader.read(CHUNK)
            if not chunk:
                break
            copied += len(chunk)
            if copied > maximum:
                raise ConflictError(label + " exceeds size limit")
            digest.update(chunk)
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    after = source.lstat()
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or copied != expected_size or digest.hexdigest() != expected_sha):
        raise ConflictError(label + " source changed during copy")
    target_sha, target_size = _hash_file(target, maximum, label + " handoff")
    if target_sha != expected_sha or target_size != expected_size:
        raise ConflictError(label + " handoff bytes mismatch")


def export_handoff(plan_path: Path, evidence_path: Path, package_dir: Path,
                   validation_log: Path, output_dir: Path) -> dict:
    """Recheck actual bytes and stage a separate, non-certified GDK handoff."""
    for path, label in ((plan_path, "plan"), (evidence_path, "SDK result")):
        if path.is_symlink():
            raise ConflictError("linked " + label + " evidence")
    plan_sha, _ = _hash_file(plan_path, MAX_JSON, "GDK plan")
    evidence_sha, _ = _hash_file(evidence_path, MAX_JSON, "GDK SDK result")
    verified = intake(plan_path, evidence_path, package_dir, validation_log)
    if verified.get("status") != "GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS":
        raise ConflictError("GDK SDK intake not passed")
    for key in ("real_msix_pass", "e2e_pass", "store_submitted",
                "gdk_sdk_validation_independently_verified"):
        if verified.get(key) is not False:
            raise ConflictError("unexpected GDK SDK approval claim")
    evidence = _read_json(evidence_path, "GDK SDK result")
    filename = evidence["package_filename"]
    original = package_dir.resolve(strict=True) / filename
    package_sha, package_size = verified["package_sha256"], verified["package_size_bytes"]
    log_sha = verified["validation_log_sha256"]
    log_size = validation_log.stat().st_size
    inventory = verified["output_files_sha256"]
    sidecar_names = sorted(set(inventory) - {filename})
    if len(sidecar_names) > MAX_OUTPUT_FILES - 1:
        raise ConflictError("GDK SDK sidecar count exceeds limit")
    # Preserve original names with a collision-free transfer prefix.
    sidecars = {}
    for name in sidecar_names:
        transferred = "sdk-sidecar-" + name
        if len(transferred) > 240:
            raise ConflictError("GDK SDK sidecar transfer name too long")
        sidecars[transferred] = inventory[name]
    if _hash_file(plan_path, MAX_JSON, "GDK plan")[0] != plan_sha or (
        _hash_file(evidence_path, MAX_JSON, "GDK SDK result")[0] != evidence_sha
    ):
        raise ConflictError("GDK plan or result changed during intake")
    if output_dir.exists() or output_dir.is_symlink():
        raise ConflictError("GDK handoff destination already exists")
    if output_dir.parent.is_symlink() or not output_dir.parent.is_dir():
        raise HoldError("GDK handoff parent missing or linked")
    parent = output_dir.parent.resolve(strict=True)
    package_root = package_dir.resolve(strict=True)
    target = parent / output_dir.name
    if target == package_root or package_root in target.parents or target in package_root.parents:
        raise ConflictError("GDK handoff must be isolated from SDK output")
    for source in (plan_path, evidence_path, validation_log):
        if target == source.resolve(strict=True) or target in source.resolve(strict=True).parents:
            raise ConflictError("GDK handoff overlaps evidence")
    target.mkdir(mode=0o700, exist_ok=False)
    try:
        _copy_verified(original, target / "package.msixvc2",
                       package_sha, package_size, MAX_PACKAGE, "GDK package")
        _copy_verified(validation_log, target / "validation.log",
                       log_sha, log_size, MAX_LOG, "GDK validation log")
        for name in sidecar_names:
            source = package_root / name
            transferred = "sdk-sidecar-" + name
            _copy_verified(source, target / transferred, inventory[name],
                           source.stat().st_size, MAX_SIDECAR, "GDK SDK sidecar")
        if {p.name for p in package_root.iterdir()} != set(inventory):
            raise ConflictError("GDK SDK output changed during handoff")
        if (_hash_file(plan_path, MAX_JSON, "GDK plan")[0] != plan_sha
                or _hash_file(evidence_path, MAX_JSON, "GDK SDK result")[0] != evidence_sha):
            raise ConflictError("GDK evidence changed during handoff")
        manifest = {
            "schema_version": 2,
            "status": "GDK_E2E_QA_INTAKE_PENDING",
            "type": "game",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_repository": PINNED_SIGNAL_SPRINT_JOB["source_repository"],
            "source_branch": PINNED_SIGNAL_SPRINT_JOB["source_branch"],
            "source_sha": verified["source_sha"],
            "cas_commit_sha": verified["cas_commit_sha"],
            "factory_head_sha": verified["factory_head_sha"],
            "store_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"],
            "package_identity_name": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["name"],
            "package_version": verified["package_version"],
            "package_filename": "package.msixvc2",
            "original_sdk_filename": filename,
            "package_sha256": package_sha,
            "package_size_bytes": package_size,
            "validation_log_filename": "validation.log",
            "validation_log_sha256": log_sha,
            "sdk_sidecars_sha256": dict(sorted(sidecars.items())),
            "sdk_result_evidence_sha256": evidence_sha,
            "sdk_pack_plan_sha256": plan_sha,
            "sdk_version_claim": verified["sdk_version_claim"],
            "sdk_exit_code_claim": verified["sdk_exit_code_claim"],
            "gdk_sdk_validation_independently_verified": False,
            "real_msix_pass": False,
            "e2e_pass": False,
            "store_submitted": False,
            "next_stage": "WINDOWS_E2E_INDEPENDENT_GDK_VALIDATION_INSTALL_GUI_QA",
        }
        with (target / "handoff.json").open("x", encoding="utf-8") as writer:
            json.dump(manifest, writer, ensure_ascii=False, sort_keys=True, indent=2)
            writer.write("\n")
        if set(p.name for p in target.iterdir()) != (
            {"package.msixvc2", "validation.log", "handoff.json"} | set(sidecars)
        ):
            raise ConflictError("GDK handoff contains unexpected files")
        return manifest
    except BaseException:
        # Only the freshly-created destination belongs to this operation.
        for path in target.iterdir():
            if path.is_file() or path.is_symlink():
                path.unlink()
        target.rmdir()
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pack-plan", "sdk-result-evidence", "package-dir",
                 "validation-log", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = export_handoff(args.pack_plan, args.sdk_result_evidence,
                                args.package_dir, args.validation_log, args.output_dir)
    except (ConflictError, HoldError, OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "e2e_pass": False}))
        return 2
    # The digest is emitted outside handoff.json to avoid self-reference.
    # The receiver must obtain this through an independently trusted channel.
    manifest_sha, _ = _hash_file(args.output_dir / "handoff.json", MAX_JSON,
                                 "GDK handoff manifest")
    print(json.dumps({**result, "handoff_manifest_sha256": manifest_sha},
                     sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
