"""Cross-repo Signal Sprint Factory-v1 Artifact <-> GDK assembly CHECK ONLY.

No CAS, staging writes, SDK, package build or Store action. A persisted live
GitHub evidence receipt is a snapshot, not a fresh GitHub authentication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from gdk_factory_lineage_adapter import members, checked_json, MAX_OUTER, MAX_INNER
from gdk_new_lineage_assembly_plan import pinned_exe_from_outer, config_xml, safe_file
from gdk_new_lineage_post_cas_gate import (
    ARTIFACT_ID, BUILD_HEAD, EXE_SHA, INNER_SHA, NEW_REQUEST, OLD_REQUEST,
    OUTER_SHA, RUN_ID, SOURCE,
)
from gdk_microsoft_game_config import ASSETS
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_GDK_IDENTITY as ID

EXPECTED_ASSETS = {name for name, _ in ASSETS.values()}
EXPECTED_FILES = EXPECTED_ASSETS | {"SignalSprint.exe", "MicrosoftGame.config"}
LEGACY_ARTIFACT = 12706862577


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def demand(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def strict_fields(record: dict, fields: dict, code: str) -> None:
    demand(type(record) is dict and all(
        type(record.get(k)) is type(v) and record[k] == v
        for k, v in fields.items()
    ), code)


def reconcile(outer_zip: Path, live_receipt: dict, plan: dict | None = None,
              asset_dir: Path | None = None) -> dict:
    """Read-only, reproducible comparison. Never treats a plan as authorization."""
    result = {
        "schema_version": 1, "status": "CROSS_REPO_INTEGRATION_HOLD",
        "partner_center_selection": "GDK_GAME", "package_format": "MSIXVC2",
        "source_sha": SOURCE, "new_request_id": NEW_REQUEST,
        "original_request_id": OLD_REQUEST,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "cas_return_pass": False, "review_authenticity_verified": False,
        "version_approved": False, "assets_approved": False,
        "staging_created": False, "ready_for_sdk": False,
        "gdk_sdk_validated": False, "real_msixvc_built": False,
        "e2e_pass": False, "store_submitted": False,
    }
    try:
        strict_fields(live_receipt, {
            "evidence_kind": "GITHUB_ACTIONS_NETWORK_LIVE_CHECK_ONLY",
            "validation_status": "FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "source_sha": SOURCE, "build_head_sha": BUILD_HEAD,
            "new_request_id": NEW_REQUEST, "original_request_id": OLD_REQUEST,
            "github_run_id": RUN_ID, "github_artifact_id": ARTIFACT_ID,
            "outer_github_zip_sha256": OUTER_SHA,
            "inner_factory_zip_sha256": INNER_SHA, "exe_sha256": EXE_SHA,
            "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
            "original_exe_sha_authority_conflict_unresolved": True,
        }, "LIVE_RECEIPT_LINEAGE_MISMATCH")
        demand(all(live_receipt.get(k) is False for k in (
            "ready_for_cas", "cas_return_pass", "real_msixvc_built",
            "store_submitted")), "LIVE_RECEIPT_FALSE_PROGRESS")
        raw = safe_file(outer_zip, MAX_OUTER)
        demand(sha(raw) == OUTER_SHA, "OUTER_ZIP_SHA_MISMATCH")
        outer = members(raw, {"new-lineage.zip", "lineage-receipt.json"}, MAX_OUTER)
        inner_raw = outer["new-lineage.zip"]
        demand(sha(inner_raw) == INNER_SHA, "INNER_ZIP_SHA_MISMATCH")
        inner = members(inner_raw, {
            "SignalSprint.exe", "provenance.json", "provisioner-request.json"
        }, MAX_INNER)
        factory_receipt = checked_json(outer["lineage-receipt.json"])
        provenance = checked_json(inner["provenance.json"])
        request = checked_json(inner["provisioner-request.json"])
        common = {"request_id": NEW_REQUEST, "source_sha": SOURCE,
                  "build_head_sha": BUILD_HEAD, "github_run_id": RUN_ID}
        for obj in (factory_receipt, provenance):
            strict_fields(obj, common, "FACTORY_MANIFEST_LINEAGE_MISMATCH")
            strict_fields(obj, {"legacy_artifact_id": LEGACY_ARTIFACT,
                                "legacy_artifact_replaced": False},
                          "LEGACY_ARTIFACT_SUBSTITUTION")
        strict_fields(request, {"request_id": NEW_REQUEST, "source_sha": SOURCE,
                                "product_type": "GAME", "slug": "signal-sprint",
                                "dry_run": True}, "FACTORY_REQUEST_MISMATCH")
        strict_fields(factory_receipt, {
            "artifact_sha256": INNER_SHA, "executable_sha256": EXE_SHA,
            "cas_status": "NOT_EXECUTED", "github_artifact_id": None,
            "legacy_artifact_recovered": False,
        }, "FACTORY_RECEIPT_MISMATCH")
        strict_fields(provenance, {
            "executable_sha256": EXE_SHA, "cas_status": "NOT_EXECUTED",
            "lineage_type": "NEW_IMMUTABLE_BUILD_NOT_OLD_ARTIFACT_RECOVERY",
        }, "FACTORY_PROVENANCE_MISMATCH")
        exe_size, exe_sha = pinned_exe_from_outer(outer_zip)
        demand(sha(inner["SignalSprint.exe"]) == exe_sha == EXE_SHA and
               exe_size == len(inner["SignalSprint.exe"]),
               "FACTORY_EXE_SHA_MISMATCH")
        strict_fields(live_receipt, {
            "provenance_sha256": sha(inner["provenance.json"]),
            "request_sha256": sha(inner["provisioner-request.json"]),
            "factory_receipt_sha256": sha(outer["lineage-receipt.json"]),
        }, "LIVE_MANIFEST_SHA_MISMATCH")
        result.update({
            "github_run_id": RUN_ID, "github_artifact_id": ARTIFACT_ID,
            "build_head_sha": BUILD_HEAD, "outer_zip_sha256": OUTER_SHA,
            "inner_zip_sha256": INNER_SHA, "exe_sha256": EXE_SHA,
            "expected_staging_paths": sorted(EXPECTED_FILES),
            "artifact_manifest_bound": True,
            "evidence_mode": "PERSISTED_PRIOR_LIVE_RECEIPT_NOT_FRESH_AUTH",
        })
        if plan is None:
            result["reason"] = "CAS_VERSION_AND_ASSET_APPROVALS_NOT_AVAILABLE"
            return result
        demand(asset_dir is not None and asset_dir.is_dir() and
               not asset_dir.is_symlink(), "ASSET_DIRECTORY_REQUIRED")
        strict_fields(plan, {
            "status": "NEW_LINEAGE_GDK_ASSEMBLY_PLAN_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2", "source_sha": SOURCE,
            "new_request_id": NEW_REQUEST, "original_request_id": OLD_REQUEST,
            "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
            "github_run_id": RUN_ID, "github_artifact_id": ARTIFACT_ID,
            "exe_sha256": EXE_SHA, "xbox_title_id": ID["xbox_title_id"],
            "xbox_scid": ID["xbox_scid"], "msa_app_id": ID["msa_app_id"],
        }, "ASSEMBLY_LINEAGE_IDENTITY_MISMATCH")
        demand(all(plan.get(k) is False for k in (
            "cas_return_pass", "review_authenticity_verified",
            "ready_for_sdk", "gdk_sdk_validated", "real_msixvc_built",
            "e2e_pass", "store_submitted", "staging_created")),
            "ASSEMBLY_FALSE_AUTHORIZATION")
        files = plan.get("files")
        demand(type(files) is list and len(files) == 6 and
               all(type(f) is dict for f in files) and
               [f.get("destination") for f in files] == sorted(EXPECTED_FILES),
               "ASSEMBLY_FILE_SET_MISMATCH")
        demand({p.name for p in asset_dir.iterdir()} == EXPECTED_ASSETS,
               "ASSET_FILE_SET_MISMATCH")
        expected_xml = config_xml(plan.get("package_version"),
                                  plan.get("reviewed_display_name"))
        demand(plan.get("config_xml_utf8") == expected_xml.decode("utf-8"),
               "ASSEMBLY_CONFIG_MISMATCH")
        for f in files:
            name = f["destination"]
            if name == "SignalSprint.exe":
                expected_sha, size, kind = EXE_SHA, exe_size, "factory_new_lineage_inner_zip"
            elif name == "MicrosoftGame.config":
                expected_sha, size, kind = sha(expected_xml), len(expected_xml), "deterministic_generated_config"
            else:
                asset = asset_dir / name
                data = safe_file(asset, 20_000_000)
                expected_sha, size, kind = sha(data), len(data), "reviewed_asset"
            strict_fields(f, {"sha256": expected_sha, "size_bytes": size,
                              "source_kind": kind}, "ASSEMBLY_FILE_SHA_OR_SOURCE_MISMATCH:" + name)
        result["status"] = "CROSS_REPO_ASSEMBLY_CONTRACT_CHECK_ONLY"
        result["reason"] = "NOT_AUTHORIZED_FOR_CAS_SDK_OR_STORE"
        result["files"] = files
        result["plan_sha256"] = sha(json.dumps(plan, sort_keys=True,
                                      ensure_ascii=False, separators=(",", ":")).encode())
    except (ValueError, OSError, TypeError, KeyError, RuntimeError,
            UnicodeError, AttributeError) as exc:
        result["reason"] = str(exc)
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outer-artifact-zip", type=Path, required=True)
    p.add_argument("--live-receipt-json", type=Path, required=True)
    p.add_argument("--assembly-plan-json", type=Path)
    p.add_argument("--asset-dir", type=Path)
    args = p.parse_args(argv)
    try:
        live = json.loads(args.live_receipt_json.read_text(encoding="utf-8"))
        plan = (json.loads(args.assembly_plan_json.read_text(encoding="utf-8"))
                if args.assembly_plan_json else None)
        result = reconcile(args.outer_artifact_zip, live, plan, args.asset_dir)
    except (OSError, ValueError, TypeError) as exc:
        result = {"status": "CROSS_REPO_INTEGRATION_HOLD", "reason": str(exc)}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 2  # check-only is never a release authorization


if __name__ == "__main__":
    sys.exit(main())
