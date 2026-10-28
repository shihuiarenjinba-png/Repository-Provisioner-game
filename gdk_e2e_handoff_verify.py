"""Read-only, fail-closed receiver for the Signal Sprint GDK E2E handoff.

This validates transferred bytes and a strict transport manifest. It does NOT
attest SDK execution, package authenticity, installation, Store approval, or
Windows-all-auto central-queue ingestion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from gdk_sdk_result_intake import (
    MAX_LOG, MAX_PACKAGE, SHA256, SHA40, _hash_file, _read_json,
)
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB, VERSION,
)

FILES = frozenset({"package.msixvc2", "validation.log", "handoff.json"})
MANIFEST_FIELDS = frozenset({
    "schema_version", "status", "type", "partner_center_selection",
    "package_format", "request_id", "source_repository", "source_branch",
    "source_sha", "cas_commit_sha", "factory_head_sha", "store_id",
    "package_identity_name", "package_version", "package_filename",
    "original_sdk_filename", "package_sha256", "package_size_bytes",
    "validation_log_filename", "validation_log_sha256",
    "sdk_result_evidence_sha256", "sdk_pack_plan_sha256",
    "sdk_version_claim", "sdk_exit_code_claim",
    "gdk_sdk_validation_independently_verified", "real_msix_pass",
    "e2e_pass", "store_submitted", "next_stage",
})


def _exact(manifest: dict, key: str, expected) -> None:
    actual = manifest.get(key)
    if type(actual) is not type(expected) or actual != expected:
        raise ConflictError("GDK E2E handoff mismatch: " + key)


def verify_handoff(handoff_dir: Path) -> dict:
    """Verify an untrusted received folder without changing any of its bytes."""
    if handoff_dir.is_symlink() or not handoff_dir.is_dir():
        raise HoldError("GDK E2E handoff directory missing or linked")
    root = handoff_dir.resolve(strict=True)
    entries = list(root.iterdir())
    if {p.name for p in entries} != FILES or len(entries) != len(FILES):
        raise ConflictError("GDK E2E handoff must contain exactly three files")
    if any(p.is_symlink() or not p.is_file() for p in entries):
        raise ConflictError("GDK E2E handoff contains linked or non-regular files")

    manifest_path = root / "handoff.json"
    manifest_sha, _ = _hash_file(manifest_path, 1024 * 1024, "GDK handoff manifest")
    manifest = _read_json(manifest_path, "GDK handoff manifest")
    if set(manifest) != MANIFEST_FIELDS:
        raise ConflictError("GDK E2E handoff schema unexpected")
    expected = {
        "schema_version": 1,
        "status": "GDK_E2E_QA_INTAKE_PENDING",
        "type": "game",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_repository": PINNED_SIGNAL_SPRINT_JOB["source_repository"],
        "source_branch": PINNED_SIGNAL_SPRINT_JOB["source_branch"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "store_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"],
        "package_identity_name": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["name"],
        "package_filename": "package.msixvc2",
        "validation_log_filename": "validation.log",
        "sdk_exit_code_claim": 0,
        "gdk_sdk_validation_independently_verified": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
        "next_stage": "WINDOWS_E2E_INDEPENDENT_GDK_VALIDATION_INSTALL_GUI_QA",
    }
    for key, value in expected.items():
        _exact(manifest, key, value)
    for key in ("cas_commit_sha", "factory_head_sha"):
        value = manifest[key]
        if type(value) is not str or not SHA40.fullmatch(value):
            raise ConflictError("GDK E2E invalid " + key)
    version = manifest["package_version"]
    if type(version) is not str or not VERSION.fullmatch(version) or any(
        int(part) > 65535 for part in version.split(".")
    ):
        raise ConflictError("GDK E2E invalid package version")
    original_name = manifest["original_sdk_filename"]
    if (type(original_name) is not str or not original_name or
            original_name in (".", "..") or
            Path(original_name).name != original_name or
            "/" in original_name or "\\" in original_name or
            not original_name.lower().endswith((".msixvc", ".msixvc2"))):
        raise ConflictError("GDK E2E original SDK filename invalid")
    for key in ("package_sha256", "validation_log_sha256",
                "sdk_result_evidence_sha256", "sdk_pack_plan_sha256"):
        value = manifest[key]
        if type(value) is not str or not SHA256.fullmatch(value):
            raise ConflictError("GDK E2E invalid " + key)
    size = manifest["package_size_bytes"]
    if type(size) is not int or not 0 < size <= MAX_PACKAGE:
        raise ConflictError("GDK E2E invalid package size")
    sdk_version = manifest["sdk_version_claim"]
    if (type(sdk_version) is not str or not 5 <= len(sdk_version) <= 160 or
            any(char in sdk_version for char in "\r\n\x00")):
        raise ConflictError("GDK E2E invalid SDK version claim")

    package_sha, package_size = _hash_file(root / "package.msixvc2", MAX_PACKAGE, "GDK received package")
    log_sha, _ = _hash_file(root / "validation.log", MAX_LOG, "GDK received SDK log")
    if package_sha != manifest["package_sha256"] or package_size != size:
        raise ConflictError("GDK E2E received package bytes mismatch")
    if log_sha != manifest["validation_log_sha256"]:
        raise ConflictError("GDK E2E received validation log bytes mismatch")
    if _hash_file(manifest_path, 1024 * 1024, "GDK handoff manifest")[0] != manifest_sha:
        raise ConflictError("GDK E2E manifest changed during verification")
    if {p.name for p in root.iterdir()} != FILES:
        raise ConflictError("GDK E2E handoff files changed during verification")

    return {
        "status": "GDK_E2E_TRANSFER_BYTES_CHECK_PASS",
        "request_id": manifest["request_id"],
        "source_sha": manifest["source_sha"],
        "cas_commit_sha": manifest["cas_commit_sha"],
        "factory_head_sha": manifest["factory_head_sha"],
        "package_sha256": package_sha,
        "package_size_bytes": package_size,
        "validation_log_sha256": log_sha,
        "manifest_sha256": manifest_sha,
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "gdk_sdk_validation_independently_verified": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
        "next_stage": "WINDOWS_E2E_INDEPENDENT_GDK_VALIDATION_INSTALL_GUI_QA",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_handoff(args.handoff_dir)
    except (ConflictError, HoldError, OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msix_pass": False,
                          "e2e_pass": False}))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
