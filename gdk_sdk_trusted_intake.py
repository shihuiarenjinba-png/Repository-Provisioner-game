"""Anchor Signal Sprint GDK SDK result intake to a separately trusted prebuild handoff.

Read-only, fail-closed. The --trusted-handoff-sha256 MUST arrive through an
independent trusted channel, not from the same transferred folder/JSON.
This proves continuity of reviewed inputs, NOT that SDK validation succeeded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from gdk_sdk_result_intake import MAX_JSON, _hash_file, _read_json, intake
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB,
)

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
HANDOFF_FIELDS = {
    "schema_version", "status", "partner_center_selection", "request_id",
    "source_sha", "cas_commit_sha", "factory_head_sha",
    "pinned_artifact_zip_sha256", "pinned_exe_sha256",
    "trusted_factory_gate_sha256", "dual_gate_receipt_sha256",
    "sdk_pack_plan_sha256", "verified_preflight_receipt_sha256",
    "staging_files_sha256", "package_version", "reviewed_display_name",
    "sdk_command_argv_not_executed", "next_stage", "gdk_sdk_validated",
    "real_msixvc_built", "store_submitted", "windows_e2e_pass",
}
REQUIRED_FALSE = (
    "gdk_sdk_validated", "real_msixvc_built", "store_submitted", "windows_e2e_pass",
)
BOUND_FIELDS = (
    "request_id", "source_sha", "cas_commit_sha", "factory_head_sha",
    "package_version", "reviewed_display_name", "staging_files_sha256",
    "sdk_command_argv_not_executed",
)


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _expect(value: dict, key: str, expected: object) -> None:
    if type(value.get(key)) is not type(expected) or value[key] != expected:
        raise ConflictError("GDK trusted SDK intake mismatch: " + key)


def trusted_intake(handoff_path: Path, trusted_handoff_sha256: str,
                   plan_path: Path, evidence_path: Path, package_dir: Path,
                   validation_log: Path) -> dict:
    """Bind the actual package/log intake to an independently pinned receipt."""
    if type(trusted_handoff_sha256) is not str or not SHA256.fullmatch(trusted_handoff_sha256):
        raise HoldError("independent trusted GDK handoff SHA-256 required")
    raw_sha, _ = _hash_file(handoff_path, MAX_JSON, "GDK trusted handoff")
    if raw_sha != trusted_handoff_sha256:
        raise ConflictError("GDK trusted handoff digest mismatch")
    handoff = _read_json(handoff_path, "GDK trusted handoff")
    if set(handoff) != HANDOFF_FIELDS:
        raise ConflictError("GDK trusted handoff schema unexpected")
    fixed = {
        "schema_version": 1,
        "status": "GDK_SDK_HANDOFF_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
    }
    for key, expected in fixed.items():
        _expect(handoff, key, expected)
    for key in REQUIRED_FALSE:
        _expect(handoff, key, False)
    for key in ("cas_commit_sha", "factory_head_sha"):
        if type(handoff[key]) is not str or not SHA40.fullmatch(handoff[key]):
            raise ConflictError("GDK trusted handoff invalid " + key)
    for key in ("pinned_artifact_zip_sha256", "pinned_exe_sha256",
                "trusted_factory_gate_sha256", "dual_gate_receipt_sha256",
                "sdk_pack_plan_sha256", "verified_preflight_receipt_sha256"):
        if type(handoff[key]) is not str or not SHA256.fullmatch(handoff[key]):
            raise ConflictError("GDK trusted handoff invalid digest: " + key)

    # The pinned ZIP and EXE cannot be replaced with another build's bytes.
    from gdk_dual_gate import ZIP_SHA, EXE_SHA
    _expect(handoff, "pinned_artifact_zip_sha256", ZIP_SHA)
    _expect(handoff, "pinned_exe_sha256", EXE_SHA)

    plan_raw_sha, _ = _hash_file(plan_path, MAX_JSON, "GDK SDK pack plan")
    plan = _read_json(plan_path, "GDK SDK pack plan")
    if hashlib.sha256(_canonical(plan)).hexdigest() != handoff["sdk_pack_plan_sha256"]:
        raise ConflictError("GDK SDK pack plan not bound to trusted handoff")
    for key in BOUND_FIELDS:
        _expect(plan, key, handoff[key])
    _expect(plan, "verified_receipt_sha256", handoff["verified_preflight_receipt_sha256"])
    for key in ("gdk_sdk_validated", "real_msixvc_built", "store_submitted"):
        _expect(plan, key, False)
    _expect(plan, "status", "GDK_SDK_PACK_PLAN_CHECK_ONLY")
    _expect(plan, "partner_center_selection", "GDK_GAME")
    _expect(plan, "package_format", "MSIXVC2")

    # The existing intake independently hashes the real package and SDK log,
    # checks the complete pack-plan/result schemas, and rejects unsafe paths.
    result = intake(plan_path, evidence_path, package_dir, validation_log)
    _expect(result, "status", "GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS")
    for key in ("request_id", "source_sha", "cas_commit_sha",
                "factory_head_sha", "package_version"):
        _expect(result, key, handoff[key])
    for key in ("real_msix_pass", "e2e_pass", "store_submitted",
                "gdk_sdk_validation_independently_verified"):
        _expect(result, key, False)

    # Detect concurrent edits to the trust anchor or plan during SDK intake.
    if _hash_file(handoff_path, MAX_JSON, "GDK trusted handoff")[0] != trusted_handoff_sha256:
        raise ConflictError("GDK trusted handoff changed during intake")
    if _hash_file(plan_path, MAX_JSON, "GDK SDK pack plan")[0] != plan_raw_sha:
        raise ConflictError("GDK SDK pack plan changed during intake")
    return {
        **result,
        "status": "GDK_TRUSTED_PREBUILD_TO_PACKAGE_BYTES_CHECK_PASS",
        "trusted_handoff_sha256": trusted_handoff_sha256,
        "sdk_pack_plan_sha256": handoff["sdk_pack_plan_sha256"],
        "prebuild_trust_chain_verified": True,
        "gdk_sdk_validation_independently_verified": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
        "next_stage": "WINDOWS_E2E_INDEPENDENT_GDK_VALIDATION_INSTALL_GUI_QA",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk-handoff", "pack-plan", "sdk-result-evidence",
                 "package-dir", "validation-log"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--trusted-handoff-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        value = trusted_intake(args.sdk_handoff, args.trusted_handoff_sha256,
                               args.pack_plan, args.sdk_result_evidence,
                               args.package_dir, args.validation_log)
    except (ConflictError, HoldError, OSError, ValueError, TypeError,
            KeyError, RuntimeError, OverflowError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "HOLD"),
                          "error": str(exc), "real_msix_pass": False,
                          "e2e_pass": False, "store_submitted": False}))
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
