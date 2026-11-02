"""Signal Sprint MSIXVC2 SDK handoff contract; strictly check-only.

Never builds a package, performs CAS, touches Partner Center, or updates
Factory / Windows-all-auto. A separate human version review record is required,
but this script cannot authenticate its author; Windows owner must verify it.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

from gdk_build_intake import ARTIFACT_SHA256, EXE_SHA256
from gdk_microsoft_game_config import _reviewed_version, _reviewed_display
from gdk_msixvc2_preflight import _require_external_inputs
from gdk_msixvc2_recheck import read_receipt, recheck
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB, _unique_json_object,
)

APPROVAL_FIELDS = frozenset({
    "schema_version", "decision", "partner_center_selection",
    "package_format", "request_id", "source_sha", "package_version",
    "reviewed_display_name", "reviewed_by", "reviewed_at",
})
MAX_APPROVAL_BYTES = 16_384


def _external_file(checkout: Path, path: Path, label: str) -> None:
    """Reject any approval/receipt placed in Factory checkout, including aliases."""
    try:
        checkout_real = checkout.resolve(strict=True)
        candidate = path.resolve(strict=False)
        if candidate == checkout_real or checkout_real in candidate.parents:
            raise ConflictError("GDK " + label + " must be outside Factory checkout")
    except (OSError, RuntimeError) as exc:
        raise ConflictError("GDK " + label + " path cannot be resolved") from exc


def read_version_review(path: Path) -> tuple[dict, str]:
    """Validate an independent version review; do not treat as signed authority."""
    try:
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode) or path.is_symlink():
            raise ConflictError("GDK version review must be a regular unlinked file")
        size = path.stat().st_size
        if not 0 < size <= MAX_APPROVAL_BYTES:
            raise ConflictError("GDK version review size invalid")
        raw = path.read_bytes()
        if len(raw) != size:
            raise ConflictError("GDK version review changed while reading")
        data = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_json_object,
            parse_float=lambda _: (_ for _ in ()).throw(ValueError("floating-point JSON")),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ConflictError("GDK version review malformed or unreadable") from exc
    if not isinstance(data, dict) or set(data) != APPROVAL_FIELDS:
        raise ConflictError("GDK version review schema mismatch")
    expected = {
        "schema_version": 1,
        "decision": "APPROVED",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
    }
    for key, value in expected.items():
        if type(data.get(key)) is not type(value) or data[key] != value:
            raise ConflictError("GDK version review mismatch: " + key)
    _reviewed_version(data["package_version"])
    _reviewed_display(data["reviewed_display_name"])
    reviewer = data["reviewed_by"]
    if (not isinstance(reviewer, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@ -]{2,99}", reviewer)
            or reviewer.strip() != reviewer or reviewer.lower() in
            {"test", "tester", "unknown", "placeholder", "tbd", "reviewer"}):
        raise HoldError("GDK build version reviewer is missing or placeholder")
    reviewed_at = data["reviewed_at"]
    if not isinstance(reviewed_at, str) or not re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)", reviewed_at):
        raise HoldError("GDK build version review timestamp missing")
    try:
        timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError("naive datetime")
    except ValueError as exc:
        raise HoldError("GDK build version review timestamp invalid") from exc
    return data, hashlib.sha256(raw).hexdigest()


def create_handoff(
    factory_checkout: Path, artifact_zip: Path, cas_sha: str, build_sha: str,
    staging_dir: Path, review_path: Path, preflight_receipt: Path,
) -> dict:
    _require_external_inputs(factory_checkout, artifact_zip, staging_dir)
    _external_file(factory_checkout, review_path, "version review")
    _external_file(factory_checkout, preflight_receipt, "preflight receipt")
    review, review_digest = read_version_review(review_path)
    verified = recheck(
        factory_checkout, artifact_zip, cas_sha, build_sha, staging_dir,
        review["package_version"], review["reviewed_display_name"], preflight_receipt,
    )
    previous, raw = read_receipt(preflight_receipt)
    if (verified.get("status") != "GDK_MSIXVC2_RECHECK_PASS"
            or verified.get("partner_center_selection") != "GDK_GAME"
            or verified.get("source_sha") != PINNED_SIGNAL_SPRINT_JOB["source_sha"]
            or verified.get("cas_commit_sha") != cas_sha
            or verified.get("factory_head_sha") != build_sha
            or verified.get("verified_receipt_sha256") != hashlib.sha256(raw).hexdigest()
            or verified.get("staging_files_sha256") != previous.get("staging_files_sha256")
            or verified.get("gdk_sdk_validated") is not False
            or verified.get("real_msixvc_built") is not False
            or verified.get("store_submitted") is not False):
        raise ConflictError("GDK handoff second-pass verification mismatch")
    expected = {
        "status": "GDK_MSIXVC2_STAGING_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "cas_commit_sha": cas_sha,
        "factory_head_sha": build_sha,
        "package_version": review["package_version"],
        "pinned_artifact_zip_sha256": ARTIFACT_SHA256,
        "pinned_exe_sha256": EXE_SHA256,
    }
    for key, value in expected.items():
        if type(previous.get(key)) is not type(value) or previous[key] != value:
            raise ConflictError("GDK handoff preflight mismatch: " + key)
    hashes = previous.get("staging_files_sha256")
    if (not isinstance(hashes, dict) or
            hashes.get("SignalSprint.exe") != EXE_SHA256 or
            not isinstance(hashes.get("MicrosoftGame.config"), str) or
            not re.fullmatch(r"[0-9a-f]{64}", hashes["MicrosoftGame.config"])):
        raise ConflictError("GDK handoff staging hash contract invalid")
    if (not isinstance(previous.get("build_branch"), str)
            or not previous["build_branch"].startswith("codex/game-signal-sprint-gdk-build-")
            or not re.fullmatch(r"[0-9a-f]{40}", previous.get("approved_identity_blob_sha", ""))):
        raise ConflictError("GDK handoff build branch or Identity blob invalid")
    return {
        "schema_version": 1,
        "status": "GDK_MSIXVC2_HANDOFF_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "request_id": expected["request_id"],
        "source_sha": expected["source_sha"],
        "cas_commit_sha": cas_sha,
        "factory_head_sha": build_sha,
        "build_branch": previous["build_branch"],
        "approved_identity_blob_sha": previous["approved_identity_blob_sha"],
        "identity": dict(PINNED_SIGNAL_SPRINT_GDK_IDENTITY),
        "package_version": review["package_version"],
        "reviewed_display_name": review["reviewed_display_name"],
        "version_review_sha256": review_digest,
        "version_review_authenticity_verified": False,
        "preflight_receipt_sha256": verified["verified_receipt_sha256"],
        "pinned_artifact_zip_sha256": ARTIFACT_SHA256,
        "pinned_exe_sha256": EXE_SHA256,
        "microsoft_game_config_sha256": hashes["MicrosoftGame.config"],
        "staging_files_sha256": hashes,
        "next_stage": "WINDOWS_GDK_SDK_VALIDATE_THEN_MAKEPKG_MSIXVC2",
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "cas_return_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-checkout", type=Path, required=True)
    parser.add_argument("--pinned-artifact-zip", type=Path, required=True)
    parser.add_argument("--cas-commit-sha", required=True)
    parser.add_argument("--build-head-sha", required=True)
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--version-review", type=Path, required=True)
    parser.add_argument("--preflight-receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = create_handoff(
            args.factory_checkout, args.pinned_artifact_zip, args.cas_commit_sha,
            args.build_head_sha, args.staging_dir, args.version_review,
            args.preflight_receipt,
        )
    except (ConflictError, HoldError, OSError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msixvc_built": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
