"""Signal Sprint isolated real-byte staging DRY RUN (never a package authority).

Only the independently hashed Factory EXE may be materialized in a temporary
folder. No unapproved GDK assets, Version or MicrosoftGame.config are invented.
The folder is destroyed before returning; no SDK, CAS, Store or ledger writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from gdk_factory_lineage_adapter import members, MAX_OUTER, MAX_INNER
from gdk_new_lineage_assembly_plan import safe_file
from gdk_new_lineage_cross_repo import reconcile, EXPECTED_FILES
from package_identity_provisioner import HoldError, ConflictError
from gdk_new_lineage_post_cas_gate import (
    ARTIFACT_ID, BUILD_HEAD, EXE_SHA, INNER_SHA, NEW_REQUEST, OLD_REQUEST,
    OUTER_SHA, RUN_ID, SOURCE,
)

MISSING_AUTHORITIES = [
    "authenticated new-request CAS authorization",
    "independently approved package Version",
    "independently approved four GDK image assets",
    "authenticated independent reviewer",
]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def dry_run(outer_zip: Path, live_receipt: dict, *, temp_parent: Path | None = None,
            assembly_plan: dict | None = None, asset_dir: Path | None = None) -> dict:
    """Check real nested ZIP bytes, stage only EXE transiently, fail closed.

    A prior live receipt is a historical snapshot, not fresh GitHub auth.
    An assembly CHECK-ONLY plan is never proof of CAS/reviewer approval.
    """
    result = {
        "schema_version": 1,
        "status": "NEW_LINEAGE_STAGING_DRY_RUN_HOLD",
        "registration": "GDK_GAME",
        "package_format": "MSIXVC2",
        "source_sha": SOURCE,
        "build_head_sha": BUILD_HEAD,
        "new_request_id": NEW_REQUEST,
        "original_request_id": OLD_REQUEST,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "github_run_id": RUN_ID,
        "github_artifact_id": ARTIFACT_ID,
        "outer_zip_sha256": OUTER_SHA,
        "inner_zip_sha256": INNER_SHA,
        "exe_sha256": EXE_SHA,
        "expected_staging_paths": sorted(EXPECTED_FILES),
        "verified_transient_files": [],
        "missing_files": sorted(EXPECTED_FILES),
        "missing_authorities": MISSING_AUTHORITIES,
        "staging_persisted": False,
        "cas_return_pass": False,
        "review_authenticity_verified": False,
        "ready_for_sdk": False,
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "e2e_pass": False,
        "store_submitted": False,
    }
    try:
        if temp_parent is not None:
            if not temp_parent.is_dir() or temp_parent.is_symlink():
                raise ValueError("TEMP_PARENT_MISSING_OR_SYMLINK")
        check = reconcile(outer_zip, live_receipt, assembly_plan, asset_dir)
        if check.get("artifact_manifest_bound") is not True:
            raise ValueError("ARTIFACT_MANIFEST_NOT_VERIFIED:" + str(check.get("reason")))
        if assembly_plan is not None and check.get("status") != "CROSS_REPO_ASSEMBLY_CONTRACT_CHECK_ONLY":
            raise ValueError("ASSEMBLY_PLAN_NOT_VERIFIED:" + str(check.get("reason")))
        if assembly_plan is None and check.get("reason") != "CAS_VERSION_AND_ASSET_APPROVALS_NOT_AVAILABLE":
            raise ValueError("UNEXPECTED_RECONCILIATION_STATUS")
        raw = safe_file(outer_zip, MAX_OUTER)
        if sha(raw) != OUTER_SHA:
            raise ValueError("OUTER_ZIP_DIGEST_MISMATCH")
        outer = members(raw, {"new-lineage.zip", "lineage-receipt.json"}, MAX_OUTER)
        inner_raw = outer["new-lineage.zip"]
        if sha(inner_raw) != INNER_SHA:
            raise ValueError("INNER_ZIP_DIGEST_MISMATCH")
        inner = members(inner_raw, {"SignalSprint.exe", "provenance.json",
                                    "provisioner-request.json"}, MAX_INNER)
        exe = inner["SignalSprint.exe"]
        if len(exe) < 100_000 or not exe.startswith(b"MZ") or sha(exe) != EXE_SHA:
            raise ValueError("EXE_DIGEST_OR_FORMAT_MISMATCH")
        with tempfile.TemporaryDirectory(prefix="signal-sprint-check-only-",
                                         dir=temp_parent) as directory:
            destination = Path(directory) / "SignalSprint.exe"
            with destination.open("xb") as out:
                out.write(exe)
            staged = safe_file(destination, MAX_INNER)
            if sha(staged) != EXE_SHA or len(staged) != len(exe):
                raise ValueError("TRANSIENT_STAGE_BYTES_MISMATCH")
            result["verified_transient_files"] = [{
                "destination": "SignalSprint.exe", "sha256": sha(staged),
                "size_bytes": len(staged), "source_kind": "factory_new_lineage_inner_zip",
            }]
        result["missing_files"] = sorted(EXPECTED_FILES - {"SignalSprint.exe"})
        result["reason"] = "REAL_EXE_VERIFIED_BUT_CAS_VERSION_ASSETS_NOT_AUTHORIZED"
        result["artifact_manifest_bound"] = True
        result["evidence_mode"] = "PERSISTED_LIVE_RECEIPT_PLUS_REAL_LOCAL_BYTES"
    except (HoldError, ConflictError, ValueError, OSError, TypeError, KeyError, RuntimeError) as exc:
        result["reason"] = str(exc)
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outer-artifact-zip", required=True, type=Path)
    p.add_argument("--live-receipt-json", required=True, type=Path)
    p.add_argument("--temp-parent", type=Path)
    p.add_argument("--assembly-plan-json", type=Path)
    p.add_argument("--asset-dir", type=Path)
    a = p.parse_args(argv)
    try:
        receipt = json.loads(a.live_receipt_json.read_text(encoding="utf-8"))
        plan = (json.loads(a.assembly_plan_json.read_text(encoding="utf-8"))
                if a.assembly_plan_json else None)
        outcome = dry_run(a.outer_artifact_zip, receipt, temp_parent=a.temp_parent,
                          assembly_plan=plan, asset_dir=a.asset_dir)
    except (OSError, ValueError, TypeError) as exc:
        outcome = {"status": "NEW_LINEAGE_STAGING_DRY_RUN_HOLD", "reason": str(exc),
                   "staging_persisted": False, "ready_for_sdk": False}
    print(json.dumps(outcome, sort_keys=True, ensure_ascii=False))
    return 2  # HOLD even if one real EXE was temporarily materialized.


if __name__ == "__main__":
    raise SystemExit(main())
