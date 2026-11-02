"""Read-only, fail-closed CAS precheck for a *distinct* Signal Sprint GDK lineage.

This does not perform or authorize CAS. It independently rechecks the submitted
new-lineage ZIP and proposal, compares the exact check-only receipt, and verifies
the Factory source checkout still points at the immutable original commit.
The original request/Artifact remain on HOLD.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from gdk_build_intake import _json
from gdk_new_lineage_reissue_check import (
    MAX_PROPOSAL, MAX_ARCHIVE, ReissueHold, SOURCE, OLD_REQUEST,
    _safe_regular, check_reissue,
)
from package_identity_provisioner import ConflictError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY

MAX_RECEIPT = 65_536
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class CasPrecheckHold(ValueError):
    pass


def _outside_factory(checkout: Path, candidate: Path) -> None:
    """Do not let operator evidence or GDK staging pollute the source checkout."""
    try:
        root = checkout.resolve(strict=True)
        target = candidate.resolve(strict=False)
        if target == root or root in target.parents:
            raise CasPrecheckHold("EVIDENCE_INSIDE_FACTORY_CHECKOUT")
    except (OSError, RuntimeError) as exc:
        raise CasPrecheckHold("EVIDENCE_PATH_UNRESOLVABLE") from exc


def _git(checkout: Path, *args: str) -> str:
    try:
        p = subprocess.run(["git", "-C", str(checkout), *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CasPrecheckHold("SOURCE_GIT_UNAVAILABLE") from exc
    if p.returncode != 0:
        raise CasPrecheckHold("SOURCE_GIT_VERIFICATION_FAILED")
    try:
        return p.stdout.decode("utf-8").strip()
    except UnicodeError as exc:
        raise CasPrecheckHold("SOURCE_GIT_OUTPUT_INVALID") from exc


def _verify_source_checkout(checkout: Path) -> None:
    if checkout.is_symlink() or not checkout.is_dir():
        raise CasPrecheckHold("SOURCE_CHECKOUT_MISSING_OR_LINKED")
    try:
        root = checkout.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CasPrecheckHold("SOURCE_CHECKOUT_UNRESOLVABLE") from exc
    if Path(_git(checkout, "rev-parse", "--show-toplevel")).resolve() != root:
        raise CasPrecheckHold("SOURCE_CHECKOUT_NOT_REPOSITORY_ROOT")
    if _git(checkout, "rev-parse", "HEAD") != SOURCE:
        raise CasPrecheckHold("IMMUTABLE_SOURCE_HEAD_MISMATCH")
    if _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        raise CasPrecheckHold("SOURCE_CHECKOUT_DIRTY")


def _fresh_receipt(proposal: Path, archive: Path, saved: Path) -> dict:
    try:
        raw = _safe_regular(saved, MAX_RECEIPT)
        previous = _json(raw)
    except (ReissueHold, ConflictError, ValueError, TypeError, RecursionError) as exc:
        raise CasPrecheckHold("REISSUE_RECEIPT_MISSING_OR_INVALID") from exc
    current = check_reissue(proposal, archive)
    if (current.get("status") != "NEW_LINEAGE_CHECK_ONLY"
            or current.get("new_lineage_check_only") is not True
            or current.get("original_lineage_status") != "ARTIFACT_EXACT_BYTES_HOLD"):
        raise CasPrecheckHold("NEW_LINEAGE_NOT_VERIFIED")
    if previous != current:
        raise CasPrecheckHold("REISSUE_RECEIPT_STALE_OR_TAMPERED")
    for key in ("ready_for_cas", "cas_return_pass", "approval_authenticity_verified",
                "gdk_sdk_validated", "real_msixvc_built", "e2e_pass", "store_submitted"):
        if current.get(key) is not False:
            raise CasPrecheckHold("REISSUE_RECEIPT_CLAIMS_UNPROVEN_PROGRESS")
    if (current.get("source_sha") != SOURCE
            or current.get("original_request_id") != OLD_REQUEST
            or current.get("identity_store_id") != PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"]
            or current.get("new_request_id") == OLD_REQUEST):
        raise CasPrecheckHold("REISSUE_RECEIPT_PRODUCT_OR_SOURCE_CONFLICT")
    return current


def precheck(checkout: Path, proposal: Path, archive: Path, receipt: Path) -> dict:
    result = {
        "schema_version": 1, "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "source_sha": SOURCE, "original_request_id": OLD_REQUEST,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "status": "NEW_LINEAGE_CAS_PREFLIGHT_HOLD",
        "reason": "NEW_LINEAGE_CAS_EVIDENCE_MISSING",
        "ready_for_cas": False, "cas_return_pass": False,
        "approval_authenticity_verified": False, "package_version_approved": False,
        "gdk_sdk_validated": False, "real_msixvc_built": False,
        "e2e_pass": False, "store_submitted": False,
    }
    try:
        for path in (proposal, archive, receipt):
            _outside_factory(checkout, path)
        _verify_source_checkout(checkout)
        current = _fresh_receipt(proposal, archive, receipt)
    except (CasPrecheckHold, ReissueHold, OSError, ValueError, TypeError) as exc:
        result["reason"] = str(exc)
        return result
    result.update({
        "status": "NEW_LINEAGE_CAS_PREFLIGHT_CHECK_ONLY",
        "reason": "INDEPENDENT_AUTHORIZATION_AND_NEW_REQUEST_CAS_CONTRACT_REQUIRED",
        "new_request_id": current["new_request_id"],
        "build_id": current["build_id"],
        "workflow_run_id": current["workflow_run_id"],
        "artifact_id": current["artifact_id"],
        "proposal_sha256": current["proposal_sha256"],
        "new_artifact_evidence": current["new_artifact_evidence"],
        "identity": dict(PINNED_SIGNAL_SPRINT_GDK_IDENTITY),
        "identity_source": "USER_PROVIDED_PARTNER_CENTER",
        "build_head_sha": None,
        "cas_commit_sha": None,
    })
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--factory-source-checkout", type=Path, required=True)
    p.add_argument("--reissue-proposal", type=Path, required=True)
    p.add_argument("--new-artifact-zip", type=Path, required=True)
    p.add_argument("--reissue-receipt", type=Path, required=True)
    args = p.parse_args(argv)
    print(json.dumps(precheck(args.factory_source_checkout, args.reissue_proposal,
                              args.new_artifact_zip, args.reissue_receipt),
                     ensure_ascii=False, sort_keys=True))
    # Always nonzero: a check-only result is never permission to write CAS.
    return 2


if __name__ == "__main__":
    sys.exit(main())
