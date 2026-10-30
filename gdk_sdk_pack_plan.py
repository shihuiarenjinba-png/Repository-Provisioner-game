"""Read-only Signal Sprint GDK MSIXVC2 SDK pack plan, never an SDK invocation.

The returned argv is only a handoff contract. On Windows, a separate authorized
builder must re-run the CAS/branch/staging gates immediately before execution,
verify the installed GDK and capture SDK validation + package SHA evidence.
MSIXVC2 is generally available with October 2026 GDK, but a check-only plan is NOT a Store certification approval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import sys

from gdk_build_intake import EXE_SHA256
from gdk_msixvc2_preflight import MAX_FILE_BYTES, _digest
from gdk_msixvc2_recheck import recheck
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB


def _reject_redirected_path(path: Path, description: str) -> None:
    """Reject linked ancestors, including Windows junctions, before SDK handoff.

    A safe-looking staging/output leaf may still be redirected by a linked
    parent. This is a fail-closed preflight, not a replacement for trusted
    storage or handle-level protections against concurrent filesystem races.
    """
    for component in (path, *path.parents):
        try:
            if (component.is_symlink()
                    or getattr(component, "is_junction", lambda: False)()):
                raise ConflictError(description + " linked path (symlink or junction)")
        except (OSError, RuntimeError) as exc:
            raise HoldError(description + " path cannot be inspected") from exc


def _directory(path: Path, description: str) -> Path:
    _reject_redirected_path(path, description)
    if not path.is_dir():
        raise HoldError(description + " directory missing or linked")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HoldError(description + " directory cannot be resolved") from exc
    _reject_redirected_path(path, description)
    return resolved


def _under(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def make_pack_plan(factory_checkout: Path, artifact_zip: Path, cas_sha: str,
                   build_sha: str, staging_dir: Path, package_version: str,
                   reviewed_display_name: str, receipt_path: Path,
                   output_dir: Path) -> dict:
    """Fail closed on changed staging, unsafe output, or non-GDK evidence."""
    # Guard all five input/output paths before any SDK-facing plan is made.
    # In particular, a symlinked *parent* of the ZIP or receipt must not
    # silently redirect the immutable evidence used by the build.
    for path, label in (
        (factory_checkout, "Factory checkout"),
        (artifact_zip, "Pinned artifact ZIP"),
        (staging_dir, "GDK staging"),
        (receipt_path, "Preflight receipt"),
        (output_dir, "GDK output"),
    ):
        _reject_redirected_path(path, label)
    verified = recheck(factory_checkout, artifact_zip, cas_sha, build_sha,
                       staging_dir, package_version, reviewed_display_name,
                       receipt_path)
    fixed = {
        "schema_version": 1,
        "status": "GDK_MSIXVC2_RECHECK_PASS",
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "cas_commit_sha": cas_sha,
        "factory_head_sha": build_sha,
        "product_history_gate": "NO_PRODUCT_PATH_CHANGES_SINCE_CAS",
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
    }
    if type(verified) is not dict:
        raise ConflictError("GDK SDK handoff recheck evidence invalid")
    for key, expected in fixed.items():
        if type(verified.get(key)) is not type(expected) or verified[key] != expected:
            raise ConflictError("GDK SDK handoff evidence mismatch: " + key)
    hashes = verified.get("staging_files_sha256")
    if type(hashes) is not dict or set(hashes) != set(MAX_FILE_BYTES):
        raise ConflictError("GDK SDK handoff staging manifest incomplete")
    if hashes["SignalSprint.exe"] != EXE_SHA256:
        raise ConflictError("GDK SDK handoff executable SHA mismatch")
    if not isinstance(verified.get("verified_receipt_sha256"), str) or len(verified["verified_receipt_sha256"]) != 64:
        raise ConflictError("GDK SDK handoff receipt SHA missing")

    factory = _directory(factory_checkout, "Factory checkout")
    staging = _directory(staging_dir, "GDK staging")
    output = _directory(output_dir, "GDK output")
    if _under(staging, factory) or _under(output, factory) or _under(output, staging) or _under(staging, output):
        raise ConflictError("GDK SDK staging/output must be isolated from checkout and each other")
    if _under(artifact_zip.resolve(strict=True), output) or _under(receipt_path.resolve(strict=True), output):
        raise ConflictError("GDK SDK output overlaps immutable input evidence")
    if any(output.iterdir()):
        raise ConflictError("GDK SDK output must be empty before packaging")

    # The earlier recheck verified exactly six files, but a new unreviewed
    # payload could appear after that snapshot. Re-enumerate at SDK handoff,
    # not only the six expected filenames, and repeat after hashing.
    expected_names = set(MAX_FILE_BYTES)
    def require_exact_staging_inventory() -> None:
        entries = list(staging.iterdir())
        if len(entries) != len(expected_names) or {p.name for p in entries} != expected_names:
            raise ConflictError("GDK SDK staging inventory changed after recheck")

    require_exact_staging_inventory()

    # A receipt is not enough: hash the actual six staging files again.
    for name, limit in MAX_FILE_BYTES.items():
        file = staging / name
        mode = file.lstat().st_mode
        if not stat.S_ISREG(mode) or file.is_symlink() or not 0 < file.stat().st_size <= limit:
            raise ConflictError("GDK SDK staging file invalid: " + name)
        expected = hashes[name]
        if not isinstance(expected, str) or len(expected) != 64 or _digest(file) != expected:
            raise ConflictError("GDK SDK staging changed after recheck: " + name)

    require_exact_staging_inventory()
    if any(output.iterdir()):
        raise ConflictError("GDK SDK output changed before packaging")
    for path, label in (
        (factory_checkout, "Factory checkout"),
        (artifact_zip, "Pinned artifact ZIP"),
        (staging_dir, "GDK staging"),
        (receipt_path, "Preflight receipt"),
        (output_dir, "GDK output"),
    ):
        _reject_redirected_path(path, label)

    # No /skipvalidation, /upload, /auth or browser/Partner Center operation.
    argv = ["makepkg.exe", "pack", "/msixvc2", "/d", str(staging),
            "/pc", "/pd", str(output), "/validationcritical"]
    return {
        "schema_version": 1,
        "status": "GDK_SDK_PACK_PLAN_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "request_id": verified["request_id"],
        "source_sha": verified["source_sha"],
        "cas_commit_sha": cas_sha,
        "factory_head_sha": build_sha,
        "package_version": package_version,
        "reviewed_display_name": reviewed_display_name,
        "verified_receipt_sha256": verified["verified_receipt_sha256"],
        "staging_files_sha256": dict(sorted(hashes.items())),
        "sdk_command_argv_not_executed": argv,
        "sdk_required": "October 2026 GDK or later with managed makepkg.exe",
        "msixvc2_preview_public_certification_blocked": False,
        "public_release_requires_certification": True,
        "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("factory-checkout", "pinned-artifact-zip", "staging-dir", "preflight-receipt", "output-dir"):
        parser.add_argument("--" + flag, required=True, type=Path)
    for flag in ("cas-commit-sha", "build-head-sha", "package-version", "reviewed-display-name"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args(argv)
    try:
        result = make_pack_plan(args.factory_checkout, args.pinned_artifact_zip,
                                args.cas_commit_sha, args.build_head_sha,
                                args.staging_dir, args.package_version,
                                args.reviewed_display_name, args.preflight_receipt,
                                args.output_dir)
    except (ConflictError, HoldError, OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msixvc_built": False}))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
