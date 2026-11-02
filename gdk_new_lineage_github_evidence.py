"""Live GitHub evidence gate for a DISTINCT Signal Sprint reissue lineage.

Read-only. Does not approve a human, CAS, a package, or the old Artifact.
Never treats caller-supplied run/artifact JSON as authenticated evidence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from gdk_new_lineage_cas_precheck import precheck
from gdk_new_lineage_reissue_check import SOURCE, OLD_REQUEST

REPO = "shihuiarenjinba-png/AI-Game-Factory"
REPO_ID = 1434022838
API = f"https://api.github.com/repos/{REPO}"
SOURCE_BRANCH = "codex/game-signal-sprint-undo-20261027"
OLD_WORKFLOW = ".github/workflows/game-signal-sprint-windows.yml"
REISSUE_WORKFLOW = ".github/workflows/game-signal-sprint-reissue.yml"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceHold(ValueError):
    pass


def _strict_json(raw: bytes) -> dict:
    if len(raw) > 512_000:
        raise EvidenceHold("GITHUB_RESPONSE_TOO_LARGE")
    def pairs(items):
        data = {}
        for key, value in items:
            if key in data:
                raise EvidenceHold("GITHUB_JSON_DUPLICATE_KEY")
            data[key] = value
        return data
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_float=lambda _: (_ for _ in ()).throw(EvidenceHold("GITHUB_JSON_FLOAT")),
            parse_constant=lambda _: (_ for _ in ()).throw(EvidenceHold("GITHUB_JSON_CONSTANT")),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise EvidenceHold("GITHUB_RESPONSE_INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise EvidenceHold("GITHUB_RESPONSE_NOT_OBJECT")
    return value


def _get_json(url: str, token: str | None = None) -> dict:
    # No arbitrary URL supplied by a receipt or GitHub API response is followed.
    if not url.startswith(API + "/actions/") or not re.fullmatch(
        r"https://api\.github\.com/repos/shihuiarenjinba-png/AI-Game-Factory/actions/(?:runs|artifacts)/[1-9][0-9]*",
        url,
    ):
        raise EvidenceHold("GITHUB_URL_NOT_ALLOWLISTED")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "signal-sprint-gdk-readonly-gate",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(url, headers=headers, method="GET"), timeout=12) as response:
            if response.geturl() != url:
                raise EvidenceHold("GITHUB_REDIRECT_REJECTED")
            return _strict_json(response.read(512_001))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise EvidenceHold("GITHUB_API_UNAVAILABLE") from exc


def _same_int(actual: object, expected: int) -> bool:
    return type(actual) is int and actual == expected


def verify_api_evidence(receipt: dict, run: dict, artifact: dict) -> dict:
    """Verify LIVE GitHub REST results against a separately rehashed ZIP receipt."""
    run_id = receipt.get("workflow_run_id")
    artifact_id = receipt.get("artifact_id")
    evidence = receipt.get("new_artifact_evidence")
    if (type(run_id) is not int or run_id <= 0
            or type(artifact_id) is not int or artifact_id <= 0
            or not isinstance(evidence, dict)
            or not isinstance(evidence.get("zip_sha256"), str)
            or not HEX64.fullmatch(evidence["zip_sha256"])):
        raise EvidenceHold("REISSUE_RECEIPT_MISSING_EVIDENCE")
    if (receipt.get("source_sha") != SOURCE or receipt.get("original_request_id") != OLD_REQUEST
            or receipt.get("original_lineage_status") != "ARTIFACT_EXACT_BYTES_HOLD"
            or receipt.get("status") != "NEW_LINEAGE_CAS_PREFLIGHT_CHECK_ONLY"
            or receipt.get("ready_for_cas") is not False
            or receipt.get("cas_return_pass") is not False):
        raise EvidenceHold("REISSUE_PREFLIGHT_NOT_CHECK_ONLY")
    if not _same_int(run.get("id"), run_id):
        raise EvidenceHold("GITHUB_RUN_ID_MISMATCH")
    repo = run.get("repository")
    head_repo = run.get("head_repository")
    if (not isinstance(repo, dict) or repo.get("full_name") != REPO
            or not _same_int(repo.get("id"), REPO_ID)
            or not isinstance(head_repo, dict) or head_repo.get("full_name") != REPO):
        raise EvidenceHold("GITHUB_RUN_REPOSITORY_MISMATCH")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise EvidenceHold("GITHUB_RUN_NOT_SUCCESSFUL")
    if run.get("event") != "workflow_dispatch":
        raise EvidenceHold("GITHUB_REISSUE_EVENT_NOT_MANUAL")
    if type(run.get("run_attempt")) is not int or run["run_attempt"] != 1:
        raise EvidenceHold("GITHUB_RUN_ATTEMPT_UNPINNED")
    head = run.get("head_sha")
    branch = run.get("head_branch")
    workflow = run.get("path")
    if not isinstance(head, str) or not HEX40.fullmatch(head):
        raise EvidenceHold("GITHUB_BUILD_HEAD_INVALID")
    if (not isinstance(branch, str)
            or not branch.startswith("codex/game-signal-sprint-gdk-reissue-")
            or not re.fullmatch(r"codex/game-signal-sprint-gdk-reissue-[a-z0-9-]{1,64}", branch)
            or workflow != REISSUE_WORKFLOW):
        raise EvidenceHold("GITHUB_REISSUE_WORKFLOW_OR_BRANCH_MISMATCH")
    # The original immutable source and the reissue workflow HEAD are different identities.
    # This check is evidence only; separate authorization of build HEAD is mandatory.
    if head == SOURCE:
        raise EvidenceHold("GITHUB_BUILD_HEAD_NOT_SEPARATE")
    if not _same_int(artifact.get("id"), artifact_id):
        raise EvidenceHold("GITHUB_ARTIFACT_ID_MISMATCH")
    arun = artifact.get("workflow_run")
    if not isinstance(arun, dict) or not _same_int(arun.get("id"), run_id):
        raise EvidenceHold("GITHUB_ARTIFACT_RUN_MISMATCH")
    if artifact.get("expired") is not False:
        raise EvidenceHold("GITHUB_ARTIFACT_EXPIRED_OR_UNKNOWN")
    if (type(artifact.get("size_in_bytes")) is not int
            or artifact["size_in_bytes"] <= 0):
        raise EvidenceHold("GITHUB_ARTIFACT_SIZE_INVALID")
    if (not isinstance(artifact.get("name"), str)
            or not artifact["name"].startswith("game-signal-sprint-reissue-")
            or not re.fullmatch(r"game-signal-sprint-reissue-[a-z0-9-]{1,100}", artifact["name"])):
        raise EvidenceHold("GITHUB_ARTIFACT_PRODUCT_MISMATCH")
    if artifact.get("digest") != "sha256:" + evidence["zip_sha256"]:
        raise EvidenceHold("GITHUB_ARTIFACT_ZIP_DIGEST_MISMATCH")
    if artifact.get("archive_download_url") != f"{API}/actions/artifacts/{artifact_id}/zip":
        raise EvidenceHold("GITHUB_ARTIFACT_DOWNLOAD_URL_MISMATCH")
    return {
        "schema_version": 1, "product": "Signal Sprint",
        "status": "GITHUB_NEW_LINEAGE_EVIDENCE_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "source_sha": SOURCE, "original_request_id": OLD_REQUEST,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "new_request_id": receipt["new_request_id"],
        "workflow_run_id": run_id, "artifact_id": artifact_id,
        "github_build_head_sha": head, "github_build_branch": branch,
        "github_workflow_path": workflow, "github_artifact_digest": artifact["digest"],
        "approval_authenticity_verified": False, "build_head_authorized": False,
        "ready_for_cas": False, "cas_return_pass": False,
        "gdk_sdk_validated": False, "real_msixvc_built": False,
        "e2e_pass": False, "store_submitted": False,
        "next_gate": "INDEPENDENT_BUILD_HEAD_AND_APPROVER_AUTHORIZATION",
    }


def check_live(checkout: Path, proposal: Path, archive: Path, receipt_path: Path,
               token: str | None = None) -> dict:
    result = {
        "status": "GITHUB_NEW_LINEAGE_EVIDENCE_HOLD",
        "source_sha": SOURCE, "original_request_id": OLD_REQUEST,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "ready_for_cas": False, "cas_return_pass": False,
        "real_msixvc_built": False, "e2e_pass": False, "store_submitted": False,
    }
    try:
        checked = precheck(checkout, proposal, archive, receipt_path)
        if checked.get("status") != "NEW_LINEAGE_CAS_PREFLIGHT_CHECK_ONLY":
            raise EvidenceHold("NEW_LINEAGE_CAS_PREFLIGHT_NOT_VERIFIED")
        run_id, artifact_id = checked["workflow_run_id"], checked["artifact_id"]
        if (type(run_id) is not int or run_id <= 0 or
                type(artifact_id) is not int or artifact_id <= 0):
            raise EvidenceHold("INVALID_GITHUB_IDS")
        run = _get_json(f"{API}/actions/runs/{run_id}", token)
        artifact = _get_json(f"{API}/actions/artifacts/{artifact_id}", token)
        return verify_api_evidence(checked, run, artifact)
    except (EvidenceHold, ValueError, TypeError, KeyError, OSError) as exc:
        result["reason"] = str(exc)
        return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-source-checkout", type=Path, required=True)
    parser.add_argument("--reissue-proposal", type=Path, required=True)
    parser.add_argument("--new-artifact-zip", type=Path, required=True)
    parser.add_argument("--reissue-receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    output = check_live(args.factory_source_checkout, args.reissue_proposal,
                        args.new_artifact_zip, args.reissue_receipt,
                        os.environ.get("GITHUB_TOKEN"))
    print(json.dumps(output, sort_keys=True))
    # Check-only must not be interpreted as CAS authorization.
    return 2


if __name__ == "__main__":
    sys.exit(main())
