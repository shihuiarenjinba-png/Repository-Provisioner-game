"""Signal Sprint opt-in legacy MSIXVC (v1) *development-only* pack plan.

The retail MSIXVC2 gate remains unchanged. This deliberately separate plan
reuses its full immutable-source/CAS/Identity/ZIP/staging recheck but removes
the MSIXVC2 format switch for a non-submittable development package.

No SDK invocation, installation, signing, encryption, Store upload or CAS.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

from gdk_sdk_pack_plan import make_pack_plan
from gdk_build_intake import EXE_SHA256
from gdk_msixvc2_preflight import MAX_FILE_BYTES
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

# Only these exact options are allowed in this development-only alternative.
MSIXVC2_PREFIX = ["makepkg.exe", "pack", "/msixvc2", "/d"]
MSIXVC1_PREFIX = ["makepkg.exe", "pack", "/d"]


def make_msixvc1_dev_plan(factory_checkout: Path, artifact_zip: Path,
                         cas_sha: str, build_sha: str, staging_dir: Path,
                         package_version: str, reviewed_display_name: str,
                         receipt_path: Path, output_dir: Path) -> dict:
    """Require the complete MSIXVC2 safety preflight before format selection.

    A plan is never an execution approval. MSIXVC1 retail submission needs a
    separately reviewed encryption choice (/l or /lk) and fresh SDK QA.
    """
    base = make_pack_plan(factory_checkout, artifact_zip, cas_sha, build_sha,
                          staging_dir, package_version, reviewed_display_name,
                          receipt_path, output_dir)
    if type(base) is not dict:
        raise ConflictError("GDK shared preflight returned invalid plan")
    expected = {
        "schema_version": 1,
        "status": "GDK_SDK_PACK_PLAN_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
    }
    for key, value in expected.items():
        if type(base.get(key)) is not type(value) or base[key] != value:
            raise ConflictError("GDK shared preflight mismatch: " + key)
    # The development-only format switch must not weaken the immutable
    # Signal Sprint correlation, receipt or exact six-file payload contract.
    # Recheck here as well as in the shared preflight so a future change to
    # that helper cannot silently create a different-byte development plan.
    bindings = {
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "cas_commit_sha": cas_sha,
        "factory_head_sha": build_sha,
        "package_version": package_version,
        "reviewed_display_name": reviewed_display_name,
    }
    for key, expected_value in bindings.items():
        if type(base.get(key)) is not type(expected_value) or base[key] != expected_value:
            raise ConflictError("GDK MSIXVC1 immutable binding mismatch: " + key)
    receipt_sha = base.get("verified_receipt_sha256")
    if type(receipt_sha) is not str or re.fullmatch(r"[0-9a-f]{64}", receipt_sha) is None:
        raise ConflictError("GDK MSIXVC1 preflight receipt digest invalid")
    hashes = base.get("staging_files_sha256")
    if (type(hashes) is not dict or set(hashes) != set(MAX_FILE_BYTES)
            or any(type(v) is not str or re.fullmatch(r"[0-9a-f]{64}", v) is None
                   for v in hashes.values())
            or hashes["SignalSprint.exe"] != EXE_SHA256):
        raise ConflictError("GDK MSIXVC1 immutable staging payload mismatch")
    argv = base.get("sdk_command_argv_not_executed")
    if (type(argv) is not list or len(argv) != 9
            or not all(type(part) is str for part in argv)
            or argv[:4] != MSIXVC2_PREFIX
            or argv[5:7] != ["/pc", "/pd"]
            or argv[8] != "/validationcritical"
            or not argv[4] or not argv[7]):
        raise ConflictError("GDK shared preflight SDK command unexpected")
    # The trusted base plan already validates the staging/output paths and
    # all six staged hashes. Preserve its arguments; do not add /l or /lk
    # because an encryption key is not yet independently approved.
    dev_argv = [*MSIXVC1_PREFIX, argv[4], *argv[5:]]
    if "/msixvc2" in dev_argv or any(
            option in dev_argv for option in ("/l", "/lk", "/upload", "/skipvalidation")):
        raise ConflictError("GDK MSIXVC1 development command unsafe")
    return {
        **base,
        "status": "GDK_MSIXVC1_DEV_PACK_PLAN_CHECK_ONLY",
        "package_format": "MSIXVC",
        "sdk_command_argv_not_executed": dev_argv,
        "sdk_required": "Independently reviewed official GDK makepkg.exe with MSIXVC support",
        "development_only": True,
        "retail_submission_ready": False,
        "retail_encryption_approved": False,
        "msixvc2_preview_public_certification_blocked": False,
        "next_stage": "INDEPENDENT_SDK_APPROVAL_AND_AUTHORIZED_MSIXVC1_DEV_PACK",
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("factory-checkout", "pinned-artifact-zip", "staging-dir",
                 "preflight-receipt", "output-dir"):
        parser.add_argument("--" + flag, required=True, type=Path)
    for flag in ("cas-commit-sha", "build-head-sha", "package-version",
                 "reviewed-display-name"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args(argv)
    try:
        result = make_msixvc1_dev_plan(
            args.factory_checkout, args.pinned_artifact_zip,
            args.cas_commit_sha, args.build_head_sha, args.staging_dir,
            args.package_version, args.reviewed_display_name,
            args.preflight_receipt, args.output_dir)
    except (ConflictError, HoldError, OSError, ValueError, TypeError,
            KeyError, RuntimeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msixvc_built": False}))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
