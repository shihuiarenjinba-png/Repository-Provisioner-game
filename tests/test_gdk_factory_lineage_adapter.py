"""Synthetic positive and fail-closed negative tests for the REAL Factory-v1 contract."""
import copy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from gdk_factory_lineage_adapter import (
    verify_factory_artifact, check_live, FactoryLineageHold, sha, REPO, REPO_ID,
    API, SOURCE, OLD_REQUEST, LEGACY_ARTIFACT, LEGACY_ZIP_SHA,
    LEGACY_EXE_SHAS, BRANCH, WORKFLOW,
)

RUN = 41361263698
ARTIFACT = 13105352227
HEAD = "a1af3448cd2edeae5bd54cbaca486a53fd991944"
BUILD = f"sprint-{RUN}"
REQUEST = f"{OLD_REQUEST}-reissue-{BUILD}-{RUN}"

def zipped(items):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as z:
        for name, value in items.items():
            z.writestr(name, value)
    return output.getvalue()

def fixture():
    exe = b"MZ" + b"TEST" * 25_000
    common = {"source_sha": SOURCE, "source_branch": "codex/game-signal-sprint-undo-20261027",
              "source_repository": REPO, "request_id": REQUEST}
    lineage = {"build_id": BUILD, "github_run_id": RUN, "build_head_sha": HEAD,
               "legacy_artifact_id": LEGACY_ARTIFACT, "legacy_artifact_replaced": False}
    provenance = {**common, **lineage, "schema_version": 1,
        "lineage_type": "NEW_IMMUTABLE_BUILD_NOT_OLD_ARTIFACT_RECOVERY",
        "legacy_request_id": OLD_REQUEST, "executable": "SignalSprint.exe",
        "executable_sha256": sha(exe), "artifact_kind": "EXE_QA_UNSIGNED_NEW_LINEAGE",
        "product_type": "GAME", "slug": "signal-sprint", "cas_status": "NOT_EXECUTED",
        "msixvc2_status": "NOT_BUILT", "store_submission": "FORBIDDEN"}
    request = {**common, "schema_version": "1.0", "source_factory": "AI-Game-Factory",
        "product_type": "GAME", "slug": "signal-sprint", "dry_run": True,
        "target_owner": "shihuiarenjinba-png", "display_name": "Signal Sprint - Offline Route Puzzle",
        "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE",
                              "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"]}
    inner = zipped({"provenance.json": json.dumps(provenance).encode(),
                    "provisioner-request.json": json.dumps(request).encode(),
                    "SignalSprint.exe": exe})
    receipt = {**common, **lineage, "schema_version": 1,
        "status": "NEW_LINEAGE_ARTIFACT_CREATED_NOT_CAS",
        "legacy_request_id": OLD_REQUEST, "legacy_zip_sha256": LEGACY_ZIP_SHA,
        "legacy_exe_sha256_authority_conflict": sorted(LEGACY_EXE_SHAS),
        "legacy_artifact_recovered": False, "github_artifact_id": None,
        "github_evidence_verified": False, "cas_status": "NOT_EXECUTED",
        "msixvc2_status": "NOT_BUILT", "store_submission": "FORBIDDEN",
        "artifact_kind": "EXE_QA_UNSIGNED_NEW_LINEAGE",
        "artifact_file": "new-lineage.zip", "artifact_sha256": sha(inner),
        "executable_sha256": sha(exe)}
    outer = zipped({"new-lineage.zip": inner,
                    "lineage-receipt.json": json.dumps(receipt).encode()})
    repo = {"id": REPO_ID, "full_name": REPO}
    run = {"id": RUN, "status": "completed", "conclusion": "success", "run_attempt": 1,
           "path": WORKFLOW, "head_branch": BRANCH, "head_sha": HEAD,
           "repository": repo, "head_repository": repo, "event": "pull_request",
           "pull_requests": [{"number": 15, "head": {"ref": BRANCH, "sha": HEAD,
                                                      "repo": {"id": REPO_ID}}}]}
    artifact = {"id": ARTIFACT, "workflow_run": {"id": RUN, "repository_id": REPO_ID,
            "head_repository_id": REPO_ID, "head_branch": BRANCH, "head_sha": HEAD},
        "expired": False, "name": f"signal-sprint-new-lineage-{RUN}",
        "archive_download_url": f"{API}/actions/artifacts/{ARTIFACT}/zip",
        "size_in_bytes": len(outer), "digest": "sha256:" + sha(outer)}
    return outer, run, artifact

def change_json(outer, archive_name, json_name, key, value):
    with zipfile.ZipFile(BytesIO(outer)) as z:
        top = {x.filename: z.read(x) for x in z.infolist()}
    if archive_name:
        with zipfile.ZipFile(BytesIO(top[archive_name])) as z:
            nested = {x.filename: z.read(x) for x in z.infolist()}
        data = json.loads(nested[json_name])
        data[key] = value
        nested[json_name] = json.dumps(data).encode()
        top[archive_name] = zipped(nested)
        if archive_name == "new-lineage.zip":
            receipt = json.loads(top["lineage-receipt.json"])
            receipt["artifact_sha256"] = sha(top[archive_name])
            top["lineage-receipt.json"] = json.dumps(receipt).encode()
    else:
        data = json.loads(top[json_name])
        data[key] = value
        top[json_name] = json.dumps(data).encode()
    return zipped(top)

def resign_artifact(outer, artifact):
    artifact["size_in_bytes"] = len(outer)
    artifact["digest"] = "sha256:" + sha(outer)

class FactoryLineageAdapterTests(unittest.TestCase):
    def setUp(self):
        self.outer, self.run, self.artifact = fixture()

    def check_hold(self, expected):
        with self.assertRaisesRegex(FactoryLineageHold, expected):
            verify_factory_artifact(self.outer, self.run, self.artifact)

    def test_synthetic_check_only(self):
        result = verify_factory_artifact(self.outer, self.run, self.artifact)
        self.assertEqual(result["status"], "FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY")
        for key in ("ready_for_cas", "cas_return_pass", "approval_authenticity_verified",
                    "package_version_approved", "gdk_assets_approved",
                    "real_msixvc_built", "e2e_pass", "store_submitted"):
            self.assertIs(result[key], False)
        self.assertEqual(result["original_lineage_status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertNotEqual(result["outer_github_zip_sha256"], result["inner_factory_zip_sha256"])

    def test_wrong_product(self):
        self.outer = change_json(self.outer, "new-lineage.zip", "provenance.json", "slug", "other-game")
        resign_artifact(self.outer, self.artifact)
        self.check_hold("PROVENANCE_INVALID")

    def test_old_request_reuse(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json", "request_id", OLD_REQUEST)
        resign_artifact(self.outer, self.artifact)
        self.check_hold("SOURCE_REQUEST_MISMATCH")

    def test_rehashed_outer_zip_not_github(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json", "status", "TAMPERED")
        self.check_hold("GITHUB_ARTIFACT_METADATA_MISMATCH|GITHUB_OUTER_ZIP")

    def test_foreign_identity_claim(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json", "approved_identity", {"store_id": "FOREIGN"})
        resign_artifact(self.outer, self.artifact)
        self.check_hold("UNAUTHENTICATED_APPROVAL_CLAIM")

    def test_unauthenticated_review(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json", "review_approved", True)
        resign_artifact(self.outer, self.artifact)
        self.check_hold("UNAUTHENTICATED_APPROVAL_CLAIM")

    def test_version_claim_not_approved(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json", "package_version_approved", True)
        resign_artifact(self.outer, self.artifact)
        self.check_hold("UNAUTHENTICATED_APPROVAL_CLAIM")

    def test_foreign_xbox_title_claim_rejected(self):
        self.outer = change_json(self.outer, "new-lineage.zip", "provenance.json",
                                 "xbox_title_id", "99999999")
        resign_artifact(self.outer, self.artifact)
        self.check_hold("UNAUTHENTICATED_APPROVAL_CLAIM")

    def test_foreign_scid_and_msa_claims_rejected(self):
        for key, value in (
            ("xbox_scid", "00000000-0000-0000-0000-000000000001"),
            ("msa_app_id", "00000000-0000-0000-0000-000000000001"),
        ):
            with self.subTest(key=key):
                outer = change_json(self.outer, None, "lineage-receipt.json", key, value)
                artifact = copy.deepcopy(self.artifact)
                resign_artifact(outer, artifact)
                with self.assertRaisesRegex(FactoryLineageHold, "UNAUTHENTICATED_APPROVAL_CLAIM"):
                    verify_factory_artifact(outer, self.run, artifact)

    def test_untrusted_version_review_claim_rejected(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json",
                                 "version_review_authenticity_verified", True)
        resign_artifact(self.outer, self.artifact)
        self.check_hold("UNAUTHENTICATED_APPROVAL_CLAIM")

    def test_unapproved_asset_claim_rejected(self):
        self.outer = change_json(self.outer, "new-lineage.zip", "provisioner-request.json",
                                 "gdk_assets_approved", True)
        resign_artifact(self.outer, self.artifact)
        self.check_hold("UNAUTHENTICATED_APPROVAL_CLAIM")

    def test_fake_gdk_sdk_success_rejected(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json",
                                 "gdk_sdk_validated", True)
        resign_artifact(self.outer, self.artifact)
        self.check_hold("UNAUTHENTICATED_APPROVAL_CLAIM")

    def test_foreign_identity_in_request_rejected(self):
        self.outer = change_json(self.outer, "new-lineage.zip", "provisioner-request.json",
                                 "identity", {"store_id": "FOREIGN"})
        resign_artifact(self.outer, self.artifact)
        self.check_hold("UNAUTHENTICATED_APPROVAL_CLAIM")

    def test_wrong_event(self):
        self.run["event"] = "workflow_dispatch"
        self.check_hold("GITHUB_EVENT_NOT_FACTORY_PR")

    def test_wrong_pr(self):
        self.run["pull_requests"][0]["number"] = 16
        self.check_hold("GITHUB_PR_NOT_PINNED")

    def test_foreign_artifact(self):
        self.artifact["workflow_run"]["id"] = 999
        self.check_hold("GITHUB_ARTIFACT_RUN_MISMATCH")

    def test_old_artifact_id(self):
        self.artifact["id"] = LEGACY_ARTIFACT
        self.check_hold("GITHUB_IDS_INVALID")

    def test_wrong_build_head(self):
        self.run["head_sha"] = SOURCE
        self.check_hold("GITHUB_BUILD_HEAD_INVALID")

    def test_inner_zip_tampered(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json",
                                 "artifact_sha256", "0" * 64)
        resign_artifact(self.outer, self.artifact)
        self.check_hold("FACTORY_INNER_ZIP_DIGEST_MISMATCH")

    def test_exe_digest_tampered(self):
        self.outer = change_json(self.outer, None, "lineage-receipt.json",
                                 "executable_sha256", "0" * 64)
        resign_artifact(self.outer, self.artifact)
        self.check_hold("FACTORY_EXE_DIGEST_MISMATCH")

    def test_live_check_is_read_only_and_non_authorizing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "github-outer.zip"
            path.write_bytes(self.outer)
            with patch("gdk_factory_lineage_adapter._get_json",
                       side_effect=[self.run, self.artifact]) as get:
                result = check_live(path, RUN, ARTIFACT)
            self.assertEqual(get.call_count, 2)
            self.assertEqual(result["status"], "FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY")
            self.assertIs(result["ready_for_cas"], False)

if __name__ == "__main__":
    unittest.main()
