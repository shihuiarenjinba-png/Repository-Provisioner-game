"""Fail-closed, read-only recovery receipt for the *original* Signal Sprint ZIP.

This does not perform CAS, package GDK/MSIXVC2, or authorize a release.
A conflicting independently supplied EXE SHA is a hard HOLD, not a reason
to silently overwrite the repository's existing pin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from gdk_build_intake import ARTIFACT_SHA256, EXE_SHA256
from gdk_exact_artifact_check import check
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_JOB

# 2026-11-02 supervisor handoff. Intentionally separate from the repository
# EXE pin: they disagree; an operator must reconcile using primary evidence.
HANDOFF_ZIP_SHA256 = "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412"
HANDOFF_EXE_SHA256 = "e8517df8cd31a40e5ce72afdd4e6a4d63626fb99f7ff8a4fa3296ff8deef05f4"
ORIGINAL_ARTIFACT_ID = 12706862577


def recovery_receipt(candidates: list[Path], search_dirs: list[Path]) -> dict:
    """Return machine-readable evidence; never claim CAS or real package PASS."""
    scan = check(candidates, search_dirs)
    pin_conflict = (
        ARTIFACT_SHA256 != HANDOFF_ZIP_SHA256
        or EXE_SHA256 != HANDOFF_EXE_SHA256
    )
    exact = (
        not pin_conflict
        and scan.get("status") == "ARTIFACT_EXACT_BYTES_CHECK_ONLY"
        and scan.get("exact_copy_count", 0) > 0
    )
    if pin_conflict:
        reason = "EXPECTED_DIGEST_AUTHORITY_CONFLICT"
    elif scan.get("reason") == "INCOMPLETE_CANDIDATE_SEARCH":
        reason = "INCOMPLETE_CANDIDATE_SEARCH"
    elif exact:
        reason = "ORIGINAL_ZIP_EXE_PROVENANCE_VERIFIED_CHECK_ONLY"
    elif not scan.get("candidates_checked"):
        reason = "ORIGINAL_ARTIFACT_NOT_FOUND"
    else:
        reason = "ORIGINAL_BYTES_OR_PROVENANCE_MISMATCH"

    inspected = []
    for entry in scan.get("candidates", []):
        inspected.append({
            "path": entry.get("path"),
            "zip_sha256": entry.get("zip_sha256"),
            "exe_sha256": entry.get("exe_sha256"),
            "zip_matches_handoff": entry.get("zip_sha256") == HANDOFF_ZIP_SHA256,
            "exe_matches_handoff": entry.get("exe_sha256") == HANDOFF_EXE_SHA256,
            "zip_matches_repository": entry.get("zip_sha256") == ARTIFACT_SHA256,
            "exe_matches_repository": entry.get("exe_sha256") == EXE_SHA256,
            "provenance_matches_repository": entry.get("provenance_match") is True,
            "provenance_sha256": entry.get("provenance_sha256"),
            "request_sha256": entry.get("request_sha256"),
            "provenance_exe_sha256": entry.get("provenance_exe_sha256"),
            "provenance_matches_exe_bytes": entry.get("provenance_matches_exe_bytes") is True,
            "provenance_matches_source": entry.get("provenance_matches_source") is True,
            "request_matches_source": entry.get("request_matches_source") is True,
            "reason": entry.get("reason"),
        })
    evidence = {
        "candidates_checked": scan.get("candidates_checked", 0),
        "exact_copy_count_repository": scan.get("exact_copy_count", 0),
        "candidates": inspected,
        "scan_reason": scan.get("reason"),
    }
    evidence_digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "original_artifact_id": ORIGINAL_ARTIFACT_ID,
        "original_artifact_expired": True,
        "expected_zip_sha256_handoff": HANDOFF_ZIP_SHA256,
        "expected_exe_sha256_handoff": HANDOFF_EXE_SHA256,
        "expected_zip_sha256_repository": ARTIFACT_SHA256,
        "expected_exe_sha256_repository": EXE_SHA256,
        "digest_authorities_agree": not pin_conflict,
        "status": "ARTIFACT_EXACT_BYTES_RECOVERY_CHECK_ONLY" if exact else "ARTIFACT_EXACT_BYTES_HOLD",
        "reason": reason,
        "original_bytes_verified": exact,
        "evidence": evidence,
        "evidence_sha256": evidence_digest,
        "receipt_authenticity_verified": False,
        "ready_for_cas": False,
        "cas_return_pass": False,
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "e2e_pass": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, action="append", default=[])
    parser.add_argument("--search-dir", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    result = recovery_receipt(args.candidate, args.search_dir)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["original_bytes_verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
