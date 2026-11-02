"""Synthetic-only negative tests; no GitHub network, CAS, SDK or Store calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_new_lineage_github_evidence as gate


class GitHubEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt = {
            "status": "NEW_LINEAGE_CAS_PREFLIGHT_CHECK_ONLY",
            "source_sha": gate.SOURCE,
            "original_request_id": gate.OLD_REQUEST,
            "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
            "ready_for_cas": False, "cas_return_pass": False,
            "new_request_id": "game-signal-sprint-reissue-" + gate.SOURCE + "-500001",
            "workflow_run_id": 500001, "artifact_id": 600001,
            "new_artifact_evidence": {"zip_sha256": "a" * 64, "exe_sha256": "b" * 64},
        }
        self.run = {
            "id": 500001,
            "repository": {"id": gate.REPO_ID, "full_name": gate.REPO},
            "head_repository": {"full_name": gate.REPO},
            "status": "completed", "conclusion": "success",
            "event": "workflow_dispatch", "run_attempt": 1,
            "head_sha": "c" * 40,
            "head_branch": "codex/game-signal-sprint-gdk-reissue-500001",
            "path": gate.REISSUE_WORKFLOW,
        }
        self.artifact = {
            "id": 600001, "workflow_run": {"id": 500001},
            "expired": False, "size_in_bytes": 120000,
            "name": "game-signal-sprint-reissue-500001",
            "digest": "sha256:" + "a" * 64,
            "archive_download_url": gate.API + "/actions/artifacts/600001/zip",
        }

    def verify(self):
        return gate.verify_api_evidence(self.receipt, self.run, self.artifact)

    def assert_hold(self, reason):
        with self.assertRaises(gate.EvidenceHold) as caught:
            self.verify()
        self.assertEqual(str(caught.exception), reason)

    def test_valid_synthetic_evidence_still_check_only(self):
        result = self.verify()
        self.assertEqual(result["status"], "GITHUB_NEW_LINEAGE_EVIDENCE_CHECK_ONLY")
        self.assertEqual(result["github_build_head_sha"], "c" * 40)
        self.assertEqual(result["source_sha"], gate.SOURCE)
        self.assertEqual(result["original_lineage_status"], "ARTIFACT_EXACT_BYTES_HOLD")
        for key in ("approval_authenticity_verified", "build_head_authorized",
                    "ready_for_cas", "cas_return_pass", "real_msixvc_built",
                    "e2e_pass", "store_submitted"):
            self.assertIs(result[key], False)

    def test_other_repository_rejected(self):
        self.run["repository"]["full_name"] = "other/AI-Game-Factory"
        self.assert_hold("GITHUB_RUN_REPOSITORY_MISMATCH")

    def test_fork_head_rejected(self):
        self.run["head_repository"]["full_name"] = "other/AI-Game-Factory"
        self.assert_hold("GITHUB_RUN_REPOSITORY_MISMATCH")

    def test_wrong_run_rejected(self):
        self.run["id"] = 500002
        self.assert_hold("GITHUB_RUN_ID_MISMATCH")

    def test_boolean_run_id_rejected(self):
        self.run["id"] = True
        self.assert_hold("GITHUB_RUN_ID_MISMATCH")

    def test_failed_run_rejected(self):
        self.run["conclusion"] = "failure"
        self.assert_hold("GITHUB_RUN_NOT_SUCCESSFUL")

    def test_unreviewed_push_event_rejected(self):
        self.run["event"] = "push"
        self.assert_hold("GITHUB_REISSUE_EVENT_NOT_MANUAL")

    def test_rerun_attempt_rejected(self):
        self.run["run_attempt"] = 2
        self.assert_hold("GITHUB_RUN_ATTEMPT_UNPINNED")

    def test_original_source_head_not_misrepresented_as_new_build(self):
        self.run["head_sha"] = gate.SOURCE
        self.assert_hold("GITHUB_BUILD_HEAD_NOT_SEPARATE")

    def test_unapproved_workflow_rejected(self):
        self.run["path"] = gate.OLD_WORKFLOW
        self.assert_hold("GITHUB_REISSUE_WORKFLOW_OR_BRANCH_MISMATCH")

    def test_wrong_branch_rejected(self):
        self.run["head_branch"] = gate.SOURCE_BRANCH
        self.assert_hold("GITHUB_REISSUE_WORKFLOW_OR_BRANCH_MISMATCH")

    def test_cross_product_artifact_rejected(self):
        self.artifact["name"] = "game-prism-route-reissue-500001"
        self.assert_hold("GITHUB_ARTIFACT_PRODUCT_MISMATCH")

    def test_wrong_artifact_id_rejected(self):
        self.artifact["id"] = 600002
        self.assert_hold("GITHUB_ARTIFACT_ID_MISMATCH")

    def test_artifact_from_different_run_rejected(self):
        self.artifact["workflow_run"]["id"] = 500002
        self.assert_hold("GITHUB_ARTIFACT_RUN_MISMATCH")

    def test_expired_artifact_rejected(self):
        self.artifact["expired"] = True
        self.assert_hold("GITHUB_ARTIFACT_EXPIRED_OR_UNKNOWN")

    def test_missing_digest_rejected(self):
        del self.artifact["digest"]
        self.assert_hold("GITHUB_ARTIFACT_ZIP_DIGEST_MISMATCH")

    def test_digest_conflict_rejected(self):
        self.artifact["digest"] = "sha256:" + "d" * 64
        self.assert_hold("GITHUB_ARTIFACT_ZIP_DIGEST_MISMATCH")

    def test_untrusted_download_url_rejected(self):
        self.artifact["archive_download_url"] = "https://example.com/zip"
        self.assert_hold("GITHUB_ARTIFACT_DOWNLOAD_URL_MISMATCH")

    def test_tampered_receipt_rejected(self):
        self.receipt["ready_for_cas"] = True
        self.assert_hold("REISSUE_PREFLIGHT_NOT_CHECK_ONLY")

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(gate.EvidenceHold):
            gate._strict_json(b'{"id":1,"id":2}')

    def test_float_json_rejected(self):
        with self.assertRaises(gate.EvidenceHold):
            gate._strict_json(b'{"id":1.1}')

    def test_invalid_url_rejected_before_network(self):
        with self.assertRaises(gate.EvidenceHold):
            gate._get_json("https://example.com/actions/runs/500001")

    def test_live_gate_fails_closed_without_local_evidence(self):
        with patch.object(gate, "precheck", return_value={"status": "NEW_LINEAGE_CAS_PREFLIGHT_HOLD"}):
            with patch.object(gate, "_get_json") as remote:
                result = gate.check_live(self.root, self.root / "a", self.root / "b", self.root / "c")
        self.assertEqual(result["status"], "GITHUB_NEW_LINEAGE_EVIDENCE_HOLD")
        self.assertIs(result["ready_for_cas"], False)
        remote.assert_not_called()

    def test_live_gate_uses_only_allowlisted_github_urls(self):
        with patch.object(gate, "precheck", return_value=self.receipt):
            with patch.object(gate, "_get_json", side_effect=[self.run, self.artifact]) as remote:
                result = gate.check_live(self.root, self.root / "a", self.root / "b", self.root / "c")
        self.assertEqual(result["status"], "GITHUB_NEW_LINEAGE_EVIDENCE_CHECK_ONLY")
        self.assertEqual([c.args[0] for c in remote.call_args_list], [
            gate.API + "/actions/runs/500001",
            gate.API + "/actions/artifacts/600001",
        ])

    def test_cli_always_nonzero(self):
        with patch.object(gate, "check_live", return_value=self.verify()):
            self.assertEqual(gate.main([
                "--factory-source-checkout", str(self.root),
                "--reissue-proposal", str(self.root / "proposal"),
                "--new-artifact-zip", str(self.root / "artifact"),
                "--reissue-receipt", str(self.root / "receipt"),
            ]), 2)


if __name__ == "__main__":
    unittest.main()
