"""Signal Sprint: bind the independent post-CAS dual gate to a GDK SDK pack plan.

CHECK-ONLY. Neither CAS nor SDK is invoked. A Windows builder MUST repeat the
actual gates immediately before SDK execution; this receipt cannot assert
package creation, certification, installation, or Store submission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from gdk_dual_gate import (
    DualGateHold, EXE_SHA, REQUEST_ID, SOURCE_SHA, ZIP_SHA, run_dual_gate,
)
from gdk_sdk_pack_plan import make_pack_plan
from package_identity_provisioner import ConflictError, HoldError

SHA64 = re.compile(r"[0-9a-f]{64}\Z")
FALSE_FLAGS = ("gdk_sdk_validated", "real_msixvc_built", "store_submitted")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DualGateHold("GDK SDK handoff: " + message)


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value: dict) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validate_dual(value: dict, cas: str, build: str, trusted_sha: str) -> None:
    required = {
        "schema_version": 1,
        "status": "GDK_DUAL_GATE_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "request_id": REQUEST_ID,
        "source_sha": SOURCE_SHA,
        "cas_commit_sha": cas,
        "factory_head_sha": build,
        "factory_gate_sha256": trusted_sha,
        "package_version": None,
        "real_msixvc_built": False,
        "gdk_sdk_validated": False,
        "store_submitted": False,
        "windows_e2e_pass": False,
        "next_stage": "GDK_SDK_PREFLIGHT_PENDING",
    }
    _require(type(value) is dict, "dual gate receipt missing")
    for key, expected in required.items():
        _require(type(value.get(key)) is type(expected) and value[key] == expected,
                 "dual gate mismatch: " + key)
    for key in ("provisioner_receipt_sha256", "factory_receipt_sha256"):
        _require(type(value.get(key)) is str and bool(SHA64.fullmatch(value[key])),
                 "dual gate missing digest: " + key)


def _validate_plan(value: dict, cas: str, build: str, version: str,
                   display: str, staging: Path, output: Path) -> None:
    required = {
        "schema_version": 1,
        "status": "GDK_SDK_PACK_PLAN_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "request_id": REQUEST_ID,
        "source_sha": SOURCE_SHA,
        "cas_commit_sha": cas,
        "factory_head_sha": build,
        "package_version": version,
        "reviewed_display_name": display,
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
        "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
    }
    _require(type(value) is dict, "SDK pack plan missing")
    for key, expected in required.items():
        _require(type(value.get(key)) is type(expected) and value[key] == expected,
                 "SDK pack plan mismatch: " + key)
    _require(type(value.get("verified_receipt_sha256")) is str
             and bool(SHA64.fullmatch(value["verified_receipt_sha256"])),
             "SDK pack plan preflight digest invalid")
    hashes = value.get("staging_files_sha256")
    _require(type(hashes) is dict and len(hashes) == 6
             and all(type(v) is str and bool(SHA64.fullmatch(v)) for v in hashes.values())
             and hashes.get("SignalSprint.exe") == EXE_SHA,
             "SDK staging hashes invalid")
    command = value.get("sdk_command_argv_not_executed")
    _require(type(command) is list and all(type(arg) is str for arg in command),
             "SDK command missing")
    _require(command == ["makepkg.exe", "pack", "/msixvc2", "/d",
                         str(staging.resolve(strict=True)), "/pc", "/pd",
                         str(output.resolve(strict=True)), "/validationcritical"],
             "SDK command differs from reviewed MSIXVC2-only contract")


def create_sdk_handoff(factory_checkout: Path, artifact_zip: Path, cas_sha: str,
                       build_sha: str, factory_gate_script: Path,
                       trusted_factory_gate_sha256: str, staging_dir: Path,
                       package_version: str, reviewed_display_name: str,
                       preflight_receipt: Path, output_dir: Path) -> dict:
    """Recheck both independent gates and the staging plan on one checkout."""
    dual_args = (factory_checkout, artifact_zip, cas_sha, build_sha,
                 factory_gate_script, trusted_factory_gate_sha256)
    pack_args = (factory_checkout, artifact_zip, cas_sha, build_sha,
                 staging_dir, package_version, reviewed_display_name,
                 preflight_receipt, output_dir)

    first_dual = run_dual_gate(*dual_args)
    _validate_dual(first_dual, cas_sha, build_sha, trusted_factory_gate_sha256)
    first_plan = make_pack_plan(*pack_args)
    _validate_plan(first_plan, cas_sha, build_sha, package_version,
                   reviewed_display_name, staging_dir, output_dir)

    # A second pass catches mutations between independent gate and SDK staging.
    second_dual = run_dual_gate(*dual_args)
    _validate_dual(second_dual, cas_sha, build_sha, trusted_factory_gate_sha256)
    _require(_canonical(first_dual) == _canonical(second_dual),
             "post-CAS evidence changed between passes")
    second_plan = make_pack_plan(*pack_args)
    _validate_plan(second_plan, cas_sha, build_sha, package_version,
                   reviewed_display_name, staging_dir, output_dir)
    _require(_canonical(first_plan) == _canonical(second_plan),
             "SDK staging or pack plan changed between passes")

    return {
        "schema_version": 1,
        "status": "GDK_SDK_HANDOFF_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "request_id": REQUEST_ID,
        "source_sha": SOURCE_SHA,
        "cas_commit_sha": cas_sha,
        "factory_head_sha": build_sha,
        "pinned_artifact_zip_sha256": ZIP_SHA,
        "pinned_exe_sha256": EXE_SHA,
        "trusted_factory_gate_sha256": trusted_factory_gate_sha256,
        "dual_gate_receipt_sha256": _sha(second_dual),
        "sdk_pack_plan_sha256": _sha(second_plan),
        "verified_preflight_receipt_sha256": second_plan["verified_receipt_sha256"],
        "staging_files_sha256": second_plan["staging_files_sha256"],
        "package_version": package_version,
        "reviewed_display_name": reviewed_display_name,
        "sdk_command_argv_not_executed": second_plan["sdk_command_argv_not_executed"],
        "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
        "windows_e2e_pass": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("factory-checkout", "pinned-artifact-zip", "factory-gate-script",
                 "staging-dir", "preflight-receipt", "output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    for name in ("cas-commit-sha", "build-head-sha", "trusted-factory-gate-sha256",
                 "package-version", "reviewed-display-name"):
        p.add_argument("--" + name, required=True)
    args = p.parse_args(argv)
    try:
        result = create_sdk_handoff(
            args.factory_checkout, args.pinned_artifact_zip,
            args.cas_commit_sha, args.build_head_sha,
            args.factory_gate_script, args.trusted_factory_gate_sha256,
            args.staging_dir, args.package_version, args.reviewed_display_name,
            args.preflight_receipt, args.output_dir,
        )
    except (DualGateHold, ConflictError, HoldError, OSError, ValueError,
            KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "real_msixvc_built": False, "store_submitted": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
