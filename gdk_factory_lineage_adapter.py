"""Read-only Signal Sprint Factory-v1 nested ZIP -> GDK evidence adapter.

The old reissue contract expects a different request schema and manual event.
This adapter verifies the actual PR #15 run, GitHub OUTER ZIP, Factory INNER
ZIP, EXE and provenance independently; it never grants CAS permission.
"""
from __future__ import annotations
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import stat
import sys
import zipfile
from gdk_new_lineage_github_evidence import _get_json, REPO, REPO_ID, API
from gdk_new_lineage_reissue_check import SOURCE, OLD_REQUEST
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_GDK_IDENTITY
from gdk_build_intake import _json

LEGACY_ARTIFACT = 12706862577
LEGACY_ZIP_SHA = "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412"
LEGACY_EXE_SHAS = {
    "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad",
    "e8517df8cd31a40e5ce72afdd4e6a4d63626fb99f7ff8a4fa3296ff8deef05f4",
}
BRANCH = "codex/game-signal-sprint-new-lineage-20261102"
WORKFLOW = ".github/workflows/game-signal-sprint-new-lineage.yml"
PR_NUMBER = 15
MAX_OUTER = 100_000_000
MAX_INNER = 80_000_000
MAX_EXE = 40_000_000
HEX40 = re.compile(r"[0-9a-f]{40}\Z")

class FactoryLineageHold(ValueError):
    pass

def require(ok: bool, reason: str) -> None:
    if not ok:
        raise FactoryLineageHold(reason)

def same(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def members(raw: bytes, names: set[str], maximum: int) -> dict[str, bytes]:
    require(0 < len(raw) <= maximum, "ARCHIVE_SIZE_INVALID")
    try:
        with zipfile.ZipFile(BytesIO(raw)) as z:
            entries = z.infolist()
            require(len(entries) == len(names) and {x.filename for x in entries} == names,
                    "ARCHIVE_MEMBERS_INVALID")
            out = {}
            for x in entries:
                require(not x.is_dir() and 0 < x.file_size <= maximum and
                        not (x.create_system == 3 and stat.S_IFMT(x.external_attr >> 16) == stat.S_IFLNK),
                        "ARCHIVE_MEMBER_UNSAFE")
                out[x.filename] = z.read(x)
            require(z.testzip() is None, "ARCHIVE_CRC_INVALID")
            return out
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, EOFError) as exc:
        raise FactoryLineageHold("ARCHIVE_INVALID") from exc

def checked_json(raw: bytes) -> dict:
    require(0 < len(raw) <= 65_536, "JSON_SIZE_INVALID")
    try:
        data = _json(raw)
    except (ValueError, TypeError, RecursionError) as exc:
        raise FactoryLineageHold("JSON_INVALID") from exc
    require(type(data) is dict, "JSON_NOT_OBJECT")
    return data

def verify_factory_artifact(outer: bytes, run: dict, artifact: dict) -> dict:
    """Pure verifier; run/artifact must be independently fetched from GitHub REST."""
    require(type(run) is dict and type(artifact) is dict, "GITHUB_RECORD_MISSING")
    run_id, artifact_id = run.get("id"), artifact.get("id")
    require(type(run_id) is int and run_id > 0 and type(artifact_id) is int and artifact_id > 0
            and artifact_id != LEGACY_ARTIFACT, "GITHUB_IDS_INVALID")
    require(run.get("status") == "completed" and run.get("conclusion") == "success"
            and same(run.get("run_attempt"), 1), "GITHUB_RUN_NOT_FIRST_SUCCESS")
    require(run.get("path") == WORKFLOW and run.get("head_branch") == BRANCH,
            "GITHUB_WORKFLOW_BRANCH_MISMATCH")
    head = run.get("head_sha")
    require(type(head) is str and HEX40.fullmatch(head) is not None and head != SOURCE,
            "GITHUB_BUILD_HEAD_INVALID")
    for key in ("repository", "head_repository"):
        repo = run.get(key)
        require(type(repo) is dict and repo.get("full_name") == REPO and same(repo.get("id"), REPO_ID),
                "GITHUB_REPOSITORY_MISMATCH")
    # This actual run is a PR-body one-shot, NOT workflow_dispatch.
    require(run.get("event") == "pull_request", "GITHUB_EVENT_NOT_FACTORY_PR")
    prs = run.get("pull_requests")
    require(type(prs) is list and len(prs) == 1 and type(prs[0]) is dict and
            same(prs[0].get("number"), PR_NUMBER), "GITHUB_PR_NOT_PINNED")
    pr_head = prs[0].get("head")
    require(type(pr_head) is dict and pr_head.get("ref") == BRANCH and
            pr_head.get("sha") == head and type(pr_head.get("repo")) is dict and
            same(pr_head["repo"].get("id"), REPO_ID), "GITHUB_PR_HEAD_MISMATCH")
    arun = artifact.get("workflow_run")
    require(type(arun) is dict and same(arun.get("id"), run_id) and
            same(arun.get("repository_id"), REPO_ID) and
            same(arun.get("head_repository_id"), REPO_ID) and
            arun.get("head_branch") == BRANCH and arun.get("head_sha") == head,
            "GITHUB_ARTIFACT_RUN_MISMATCH")
    require(artifact.get("expired") is False and
            artifact.get("name") == f"signal-sprint-new-lineage-{run_id}" and
            artifact.get("archive_download_url") == f"{API}/actions/artifacts/{artifact_id}/zip" and
            same(artifact.get("size_in_bytes"), len(outer)), "GITHUB_ARTIFACT_METADATA_MISMATCH")
    outer_sha = sha(outer)
    require(artifact.get("digest") == "sha256:" + outer_sha and outer_sha != LEGACY_ZIP_SHA,
            "GITHUB_OUTER_ZIP_DIGEST_MISMATCH")
    outer_files = members(outer, {"new-lineage.zip", "lineage-receipt.json"}, MAX_OUTER)
    inner = outer_files["new-lineage.zip"]
    receipt = checked_json(outer_files["lineage-receipt.json"])
    inner_sha = sha(inner)
    require(inner_sha != outer_sha and inner_sha != LEGACY_ZIP_SHA and
            receipt.get("artifact_sha256") == inner_sha and
            receipt.get("artifact_file") == "new-lineage.zip", "FACTORY_INNER_ZIP_DIGEST_MISMATCH")
    inner_files = members(inner, {"provenance.json", "provisioner-request.json", "SignalSprint.exe"}, MAX_INNER)
    exe = inner_files["SignalSprint.exe"]
    require(100_000 <= len(exe) <= MAX_EXE and exe.startswith(b"MZ"), "FACTORY_EXE_INVALID")
    exe_sha = sha(exe)
    require(exe_sha not in LEGACY_EXE_SHAS and receipt.get("executable_sha256") == exe_sha,
            "FACTORY_EXE_DIGEST_MISMATCH")
    provenance = checked_json(inner_files["provenance.json"])
    request = checked_json(inner_files["provisioner-request.json"])
    build_id = f"sprint-{run_id}"
    new_request = f"{OLD_REQUEST}-reissue-{build_id}-{run_id}"
    common = {"source_sha": SOURCE, "source_branch": "codex/game-signal-sprint-undo-20261027",
              "source_repository": REPO, "request_id": new_request}
    for obj in (receipt, provenance, request):
        require(all(same(obj.get(k), v) for k, v in common.items()), "FACTORY_SOURCE_REQUEST_MISMATCH")
    for obj in (receipt, provenance):
        require(all(same(obj.get(k), v) for k, v in {
            "build_id": build_id, "github_run_id": run_id, "build_head_sha": head,
            "legacy_artifact_id": LEGACY_ARTIFACT, "legacy_artifact_replaced": False,
        }.items()), "FACTORY_BUILD_LINEAGE_MISMATCH")
    require(all(same(receipt.get(k), v) for k, v in {
        "schema_version": 1, "status": "NEW_LINEAGE_ARTIFACT_CREATED_NOT_CAS",
        "legacy_request_id": OLD_REQUEST, "legacy_zip_sha256": LEGACY_ZIP_SHA,
        "legacy_artifact_recovered": False, "github_artifact_id": None,
        "github_evidence_verified": False, "cas_status": "NOT_EXECUTED",
        "msixvc2_status": "NOT_BUILT", "store_submission": "FORBIDDEN",
        "artifact_kind": "EXE_QA_UNSIGNED_NEW_LINEAGE",
    }.items()), "FACTORY_RECEIPT_UNPROVEN_PROGRESS_OR_LEGACY_MISMATCH")
    require(type(receipt.get("legacy_exe_sha256_authority_conflict")) is list and
            set(receipt["legacy_exe_sha256_authority_conflict"]) == LEGACY_EXE_SHAS and
            len(receipt["legacy_exe_sha256_authority_conflict"]) == 2,
            "FACTORY_LEGACY_SHA_AUTHORITY_CONFLICT_HIDDEN")
    require(all(same(provenance.get(k), v) for k, v in {
        "schema_version": 1, "lineage_type": "NEW_IMMUTABLE_BUILD_NOT_OLD_ARTIFACT_RECOVERY",
        "legacy_request_id": OLD_REQUEST, "executable": "SignalSprint.exe",
        "executable_sha256": exe_sha, "artifact_kind": "EXE_QA_UNSIGNED_NEW_LINEAGE",
        "product_type": "GAME", "slug": "signal-sprint", "cas_status": "NOT_EXECUTED",
        "msixvc2_status": "NOT_BUILT", "store_submission": "FORBIDDEN",
    }.items()), "FACTORY_PROVENANCE_INVALID")
    require(all(same(request.get(k), v) for k, v in {
        "schema_version": "1.0", "source_factory": "AI-Game-Factory",
        "product_type": "GAME", "slug": "signal-sprint", "dry_run": True,
        "target_owner": "shihuiarenjinba-png", "display_name": "Signal Sprint - Offline Route Puzzle",
        "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE", "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
    }.items()), "FACTORY_INTAKE_INVALID")
    require(not any(k in receipt or k in provenance or k in request for k in
                    ("approved_identity", "review_approved", "package_version_approved", "cas_return_pass")),
            "UNAUTHENTICATED_APPROVAL_CLAIM")
    return {
        "schema_version": 1, "product": "Signal Sprint", "partner_center_selection": "GDK_GAME",
        "status": "FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY", "source_sha": SOURCE,
        "build_head_sha": head, "original_request_id": OLD_REQUEST,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD", "new_request_id": new_request,
        "build_id": build_id, "github_run_id": run_id, "github_artifact_id": artifact_id,
        "outer_github_zip_sha256": outer_sha, "inner_factory_zip_sha256": inner_sha,
        "exe_sha256": exe_sha, "provenance_sha256": sha(inner_files["provenance.json"]),
        "request_sha256": sha(inner_files["provisioner-request.json"]),
        "factory_receipt_sha256": sha(outer_files["lineage-receipt.json"]),
        "identity_store_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"],
        "approval_authenticity_verified": False, "package_version_approved": False,
        "gdk_assets_approved": False, "ready_for_cas": False, "cas_return_pass": False,
        "gdk_sdk_validated": False, "real_msixvc_built": False, "e2e_pass": False,
        "store_submitted": False, "next_gate": "INDEPENDENT_APPROVER_AND_NEW_REQUEST_CAS_AUTHORIZATION",
    }

def check_live(outer_zip: Path, run_id: int, artifact_id: int, token: str | None = None) -> dict:
    result = {"status": "FACTORY_NEW_LINEAGE_GITHUB_HOLD", "ready_for_cas": False,
              "cas_return_pass": False, "real_msixvc_built": False, "e2e_pass": False,
              "store_submitted": False}
    try:
        require(type(run_id) is int and run_id > 0 and type(artifact_id) is int and artifact_id > 0,
                "GITHUB_IDS_INVALID")
        require(not outer_zip.is_symlink() and outer_zip.is_file() and
                0 < outer_zip.stat().st_size <= MAX_OUTER, "OUTER_ARTIFACT_MISSING")
        raw = outer_zip.read_bytes()
        run = _get_json(f"{API}/actions/runs/{run_id}", token)
        artifact = _get_json(f"{API}/actions/artifacts/{artifact_id}", token)
        require(same(run.get("id"), run_id) and same(artifact.get("id"), artifact_id),
                "GITHUB_IDS_MISMATCH")
        return verify_factory_artifact(raw, run, artifact)
    except (FactoryLineageHold, ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        result["reason"] = str(exc)
        return result

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outer-artifact-zip", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    args = parser.parse_args(argv)
    import os
    print(json.dumps(check_live(args.outer_artifact_zip, args.run_id, args.artifact_id,
                                os.environ.get("GITHUB_TOKEN")), sort_keys=True))
    return 2  # check-only is never CAS permission

if __name__ == "__main__":
    sys.exit(main())
