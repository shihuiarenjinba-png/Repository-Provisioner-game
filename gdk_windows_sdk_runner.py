"""Signal Sprint only: guarded Windows GDK MSIXVC2 SDK execution.

Check-only by default. Explicit --execute runs a locally installed makepkg.exe
AFTER re-deriving the Factory/Provisioner dual gate and the six staged hashes.
This script does not perform CAS, identity retrieval, install, Store submission,
or independent SDK certification. Output is a *claim* requiring later intake.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys

from gdk_sdk_handoff_gate import create_sdk_handoff
from gdk_sdk_result_intake import (
    MAX_JSON, MAX_LOG, MAX_OUTPUT_FILES, MAX_PACKAGE, MAX_SIDECAR,
    RESULT_FIELDS, SHA256, SIDECAR_SUFFIXES, _hash_file, _read_json, intake,
)
from gdk_windows_filename import validate_unique_windows_names
from gdk_msixvc2_recheck import recheck
from package_identity_provisioner import ConflictError, HoldError


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _ensure_equal(actual: dict, expected: dict, label: str) -> None:
    if _canonical(actual) != _canonical(expected):
        raise ConflictError("GDK Windows runner: " + label + " changed")


def _sdk_executable() -> Path:
    if platform.system() != "Windows":
        raise HoldError("GDK SDK execution requires local Windows")
    found = shutil.which("makepkg.exe")
    if not found:
        raise HoldError("GDK makepkg.exe not found on PATH")
    path = Path(found)
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ConflictError("GDK makepkg executable is linked or not regular")
    return path.resolve(strict=True)


def _scan_sdk_output(output: Path) -> tuple[str, dict[str, str], int]:
    if output.is_symlink() or not output.is_dir():
        raise ConflictError("GDK SDK output directory missing or linked")
    files = list(output.iterdir())
    if not 1 <= len(files) <= MAX_OUTPUT_FILES:
        raise ConflictError("GDK SDK output file count invalid")
    validate_unique_windows_names((p.name for p in files), "GDK SDK output")
    packages = [p for p in files if p.suffix.lower() in (".msixvc", ".msixvc2")]
    if len(packages) != 1:
        raise ConflictError("GDK SDK must produce exactly one MSIXVC package")
    package = packages[0]
    inventory = {}
    package_size = 0
    for path in files:
        if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
            raise ConflictError("GDK SDK output contains linked or non-regular file")
        if path != package and path.suffix.lower() not in SIDECAR_SUFFIXES:
            raise ConflictError("GDK SDK output contains unreviewed sidecar")
        sha, size = _hash_file(path, MAX_PACKAGE if path == package else MAX_SIDECAR,
                               "GDK SDK output " + path.name)
        inventory[path.name] = sha
        if path == package:
            package_size = size
    if {p.name for p in output.iterdir()} != set(inventory):
        raise ConflictError("GDK SDK output inventory changed during scan")
    return package.name, dict(sorted(inventory.items())), package_size


def _make_evidence(plan: dict, sdk_version_claim: str, filename: str,
                   inventory: dict[str, str], size: int, log_sha: str) -> dict:
    if (type(sdk_version_claim) is not str or not 5 <= len(sdk_version_claim) <= 160
            or any(c in sdk_version_claim for c in "\r\n\x00")):
        raise HoldError("reviewed GDK SDK version claim required")
    evidence = {
        "schema_version": 1,
        "status": "GDK_SDK_PACK_EXECUTED",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "request_id": plan["request_id"],
        "source_sha": plan["source_sha"],
        "cas_commit_sha": plan["cas_commit_sha"],
        "factory_head_sha": plan["factory_head_sha"],
        "package_version": plan["package_version"],
        "reviewed_display_name": plan["reviewed_display_name"],
        "verified_receipt_sha256": plan["verified_receipt_sha256"],
        "staging_files_sha256": plan["staging_files_sha256"],
        "sdk_command_argv": plan["sdk_command_argv_not_executed"],
        "sdk_executable": "makepkg.exe",
        "sdk_version": sdk_version_claim,
        "sdk_exit_code": 0,
        "validation_log_sha256": log_sha,
        "package_filename": filename,
        "package_sha256": inventory[filename],
        "package_size_bytes": size,
        "output_files_sha256": inventory,
        "store_submitted": False,
    }
    if set(evidence) != RESULT_FIELDS:
        raise ConflictError("GDK SDK result evidence schema drift")
    return evidence


def run_windows_pack(*, factory_checkout: Path, artifact_zip: Path, cas_sha: str,
                     build_sha: str, factory_gate_script: Path,
                     trusted_factory_gate_sha256: str, staging_dir: Path,
                     package_version: str, reviewed_display_name: str,
                     preflight_receipt: Path, output_dir: Path,
                     sdk_handoff: Path, trusted_handoff_sha256: str,
                     pack_plan: Path, sdk_version_claim: str,
                     validation_log: Path, result_evidence: Path,
                     execute: bool = False, timeout_seconds: int = 3600,
                     trusted_makepkg_sha256: str | None = None) -> dict:
    """Recheck immutable inputs and optionally execute the SDK without shell."""
    if type(trusted_handoff_sha256) is not str or not SHA256.fullmatch(trusted_handoff_sha256):
        raise HoldError("independent GDK SDK handoff SHA-256 required")
    if not 1 <= timeout_seconds <= 7200:
        raise ConflictError("GDK SDK timeout outside reviewed bounds")
    if (type(sdk_version_claim) is not str or not 5 <= len(sdk_version_claim) <= 160
            or any(c in sdk_version_claim for c in "\r\n\x00")):
        raise HoldError("reviewed GDK SDK version claim required")
    if _hash_file(sdk_handoff, MAX_JSON, "GDK SDK trusted handoff")[0] != trusted_handoff_sha256:
        raise ConflictError("GDK SDK independent handoff SHA mismatch")
    handoff = _read_json(sdk_handoff, "GDK SDK trusted handoff")
    plan = _read_json(pack_plan, "GDK SDK pack plan")
    expected_handoff = create_sdk_handoff(
        factory_checkout, artifact_zip, cas_sha, build_sha,
        factory_gate_script, trusted_factory_gate_sha256, staging_dir,
        package_version, reviewed_display_name, preflight_receipt, output_dir,
    )
    _ensure_equal(handoff, expected_handoff, "trusted SDK handoff")
    if hashlib.sha256(_canonical(plan)).hexdigest() != handoff["sdk_pack_plan_sha256"]:
        raise ConflictError("GDK SDK pack plan SHA differs from trusted handoff")
    from gdk_sdk_pack_plan import make_pack_plan
    fresh_plan = make_pack_plan(factory_checkout, artifact_zip, cas_sha, build_sha,
                                staging_dir, package_version, reviewed_display_name,
                                preflight_receipt, output_dir)
    _ensure_equal(plan, fresh_plan, "SDK pack plan")
    if validation_log.exists() or validation_log.is_symlink() or result_evidence.exists() or result_evidence.is_symlink():
        raise ConflictError("GDK SDK output evidence destination must not exist")
    if validation_log.resolve() == result_evidence.resolve():
        raise ConflictError("GDK SDK log and result evidence paths must differ")
    for path in (validation_log, result_evidence):
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise HoldError("GDK SDK evidence parent missing or linked")
        resolved = path.resolve()
        for forbidden in (output_dir.resolve(), staging_dir.resolve(), factory_checkout.resolve()):
            if resolved == forbidden or forbidden in resolved.parents:
                raise ConflictError("GDK SDK evidence overlaps output, staging or Factory")
        if resolved in {artifact_zip.resolve(), sdk_handoff.resolve(), pack_plan.resolve(),
                        preflight_receipt.resolve(), factory_gate_script.resolve()}:
            raise ConflictError("GDK SDK evidence overlaps immutable input")
    if not execute:
        return {"status": "GDK_WINDOWS_SDK_EXECUTION_CHECK_ONLY_READY",
                "partner_center_selection": "GDK_GAME", "request_id": plan["request_id"],
                "source_sha": plan["source_sha"], "cas_commit_sha": cas_sha,
                "factory_head_sha": build_sha, "sdk_executed": False,
                "real_msix_pass": False, "e2e_pass": False, "store_submitted": False}

    if (type(trusted_makepkg_sha256) is not str
            or not SHA256.fullmatch(trusted_makepkg_sha256)):
        raise HoldError("independent approved makepkg.exe SHA-256 required for execution")
    executable = _sdk_executable()
    if _hash_file(executable, 512 * 1024 * 1024, "GDK makepkg.exe")[0] != trusted_makepkg_sha256:
        raise ConflictError("GDK makepkg.exe differs from independently approved bytes")
    command = [str(executable), *plan["sdk_command_argv_not_executed"][1:]]
    try:
        with validation_log.open("xb") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                       timeout=timeout_seconds, check=False, shell=False)
    except subprocess.TimeoutExpired as exc:
        raise HoldError("GDK SDK execution timed out; output untrusted") from exc
    if completed.returncode != 0:
        raise HoldError("GDK SDK makepkg failed; inspect validation log")
    if _hash_file(executable, 512 * 1024 * 1024, "GDK makepkg.exe")[0] != trusted_makepkg_sha256:
        raise ConflictError("GDK makepkg.exe changed during execution")
    log_sha, _ = _hash_file(validation_log, MAX_LOG, "GDK SDK validation log")
    filename, inventory, size = _scan_sdk_output(output_dir)
    post = recheck(factory_checkout, artifact_zip, cas_sha, build_sha,
                   staging_dir, package_version, reviewed_display_name,
                   preflight_receipt)
    if post["staging_files_sha256"] != plan["staging_files_sha256"] or post["verified_receipt_sha256"] != plan["verified_receipt_sha256"]:
        raise ConflictError("GDK SDK inputs changed during execution")
    if _hash_file(sdk_handoff, MAX_JSON, "GDK SDK trusted handoff")[0] != trusted_handoff_sha256:
        raise ConflictError("GDK SDK trusted handoff changed during execution")
    evidence = _make_evidence(plan, sdk_version_claim, filename, inventory, size, log_sha)
    with result_evidence.open("x", encoding="utf-8") as writer:
        json.dump(evidence, writer, sort_keys=True, ensure_ascii=False, indent=2)
        writer.write("\n")
    try:
        checked = intake(pack_plan, result_evidence, output_dir, validation_log)
        if checked["status"] != "GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS":
            raise ConflictError("GDK SDK strict intake did not pass")
        # The intake can take minutes for large MSIXVC2 packages. Do not trust a
        # receipt if the independent CAS/staging gate, package, or log changed
        # while that intake was hashing bytes. Any failure removes the receipt.
        final_post = recheck(factory_checkout, artifact_zip, cas_sha, build_sha,
                             staging_dir, package_version, reviewed_display_name,
                             preflight_receipt)
        _ensure_equal(final_post, post, "post-intake CAS/staging evidence")
        final_name, final_inventory, final_size = _scan_sdk_output(output_dir)
        if (final_name != filename or final_inventory != inventory
                or final_size != size
                or checked.get("output_files_sha256") != inventory
                or checked.get("package_sha256") != inventory[filename]
                or checked.get("validation_log_sha256") != log_sha):
            raise ConflictError("GDK SDK output changed during trusted intake")
        if _hash_file(validation_log, MAX_LOG, "GDK SDK validation log")[0] != log_sha:
            raise ConflictError("GDK SDK log changed during trusted intake")
        if _hash_file(sdk_handoff, MAX_JSON, "GDK SDK trusted handoff")[0] != trusted_handoff_sha256:
            raise ConflictError("GDK SDK handoff changed during trusted intake")
    except BaseException:
        result_evidence.unlink(missing_ok=True)
        raise
    return {"status": "GDK_WINDOWS_SDK_OUTPUT_INTAKE_CHECK_PASS",
            "partner_center_selection": "GDK_GAME", "request_id": plan["request_id"],
            "source_sha": plan["source_sha"], "cas_commit_sha": cas_sha,
            "factory_head_sha": build_sha, "sdk_executed": True,
            "sdk_exit_code_claim": 0, "package_sha256": checked["package_sha256"],
            "validation_log_sha256": checked["validation_log_sha256"],
            "output_files_sha256": checked["output_files_sha256"],
            "gdk_sdk_validation_independently_verified": False,
            "real_msix_pass": False, "e2e_pass": False, "store_submitted": False,
            "next_stage": "GDK_TRUSTED_INTAKE_AND_WINDOWS_E2E_QA"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    paths = ("factory-checkout", "pinned-artifact-zip", "factory-gate-script",
             "staging-dir", "preflight-receipt", "output-dir", "sdk-handoff",
             "pack-plan", "validation-log", "result-evidence")
    for name in paths:
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("cas-commit-sha", "build-head-sha", "trusted-factory-gate-sha256",
                 "package-version", "reviewed-display-name", "trusted-handoff-sha256",
                 "sdk-version-claim"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--execute", action="store_true", help="Explicitly authorize local GDK SDK packaging")
    parser.add_argument("--trusted-makepkg-sha256", help="Independently approved SDK executable digest; required with --execute")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args(argv)
    try:
        result = run_windows_pack(
            factory_checkout=args.factory_checkout, artifact_zip=args.pinned_artifact_zip,
            cas_sha=args.cas_commit_sha, build_sha=args.build_head_sha,
            factory_gate_script=args.factory_gate_script,
            trusted_factory_gate_sha256=args.trusted_factory_gate_sha256,
            staging_dir=args.staging_dir, package_version=args.package_version,
            reviewed_display_name=args.reviewed_display_name,
            preflight_receipt=args.preflight_receipt, output_dir=args.output_dir,
            sdk_handoff=args.sdk_handoff, trusted_handoff_sha256=args.trusted_handoff_sha256,
            pack_plan=args.pack_plan, sdk_version_claim=args.sdk_version_claim,
            validation_log=args.validation_log, result_evidence=args.result_evidence,
            execute=args.execute, timeout_seconds=args.timeout_seconds,
            trusted_makepkg_sha256=args.trusted_makepkg_sha256,
        )
    except (ConflictError, HoldError, OSError, ValueError, TypeError, KeyError,
            RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "HOLD"), "error": str(exc),
                          "real_msix_pass": False, "e2e_pass": False, "store_submitted": False}))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
