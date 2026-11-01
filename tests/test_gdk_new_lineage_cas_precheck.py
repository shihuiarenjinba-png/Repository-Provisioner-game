"""Synthetic-only negative tests: no real CAS, SDK, or Store operations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_new_lineage_cas_precheck as gate
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_GDK_IDENTITY


class NewLineageCasPrecheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.checkout = self.root / "factory"
        self.checkout.mkdir()
        self.proposal = self.root / "proposal.json"
        self.archive = self.root / "new.zip"
        self.receipt = self.root / "receipt.json"
        self.proposal.write_text("{}", encoding="utf-8")
        self.archive.write_bytes(b"synthetic-not-real-zip")
        self.fresh = {
            "status": "NEW_LINEAGE_CHECK_ONLY",
            "new_lineage_check_only": True,
            "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
            "source_sha": gate.SOURCE,
            "original_request_id": gate.OLD_REQUEST,
            "identity_store_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"],
            "new_request_id": "game-signal-sprint-reissue-" + gate.SOURCE + "-500001",
            "build_id": "gdk-reissue-500001-600001",
            "workflow_run_id": 500001,
            "artifact_id": 600001,
            "proposal_sha256": "a" * 64,
            "new_artifact_evidence": {"zip_sha256": "b" * 64, "exe_sha256": "c" * 64},
            "ready_for_cas": False,
            "cas_return_pass": False,
            "approval_authenticity_verified": False,
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "e2e_pass": False,
            "store_submitted": False,
        }
        self.receipt.write_text(json.dumps(self.fresh), encoding="utf-8")
        self.checker = patch.object(gate, "check_reissue", return_value=self.fresh)
        self.checker.start()
        self.addCleanup(self.checker.stop)
        self.git = patch.object(gate, "_git", side_effect=self.fake_git)
        self.git.start()
        self.addCleanup(self.git.stop)
        self.head = gate.SOURCE
        self.dirty = ""

    def fake_git(self, checkout, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(self.checkout.resolve())
        if args == ("rev-parse", "HEAD"):
            return self.head
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return self.dirty
        raise AssertionError("unexpected Git invocation: " + repr(args))

    def run_gate(self):
        return gate.precheck(self.checkout, self.proposal, self.archive, self.receipt)

    def assert_hold(self, reason):
        result = self.run_gate()
        self.assertEqual(result["status"], "NEW_LINEAGE_CAS_PREFLIGHT_HOLD")
        self.assertEqual(result["reason"], reason)
        self.assertIs(result["ready_for_cas"], False)

    def test_check_only_never_authorizes_cas_or_real_package(self):
        result = self.run_gate()
        self.assertEqual(result["status"], "NEW_LINEAGE_CAS_PREFLIGHT_CHECK_ONLY")
        self.assertEqual(result["original_lineage_status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertNotEqual(result["new_request_id"], gate.OLD_REQUEST)
        self.assertEqual(result["source_sha"], gate.SOURCE)
        self.assertEqual(result["identity"]["xbox_title_id"], "68721417")
        self.assertIsNone(result["cas_commit_sha"])
        self.assertIsNone(result["build_head_sha"])
        for key in ("ready_for_cas", "cas_return_pass", "approval_authenticity_verified",
                    "package_version_approved", "gdk_sdk_validated",
                    "real_msixvc_built", "e2e_pass", "store_submitted"):
            self.assertIs(result[key], False)

    def test_source_head_must_remain_pinned(self):
        self.head = "f" * 40
        self.assert_hold("IMMUTABLE_SOURCE_HEAD_MISMATCH")

    def test_dirty_factory_checkout_rejected(self):
        self.dirty = "?? staging/MicrosoftGame.config"
        self.assert_hold("SOURCE_CHECKOUT_DIRTY")

    def test_receipt_tampering_rejected(self):
        changed = dict(self.fresh)
        changed["artifact_id"] = 777777
        self.receipt.write_text(json.dumps(changed), encoding="utf-8")
        self.assert_hold("REISSUE_RECEIPT_STALE_OR_TAMPERED")

    def test_missing_receipt_rejected(self):
        self.receipt.unlink()
        self.assert_hold("REISSUE_RECEIPT_MISSING_OR_INVALID")

    def test_duplicate_json_key_rejected(self):
        self.receipt.write_text('{"status":"NEW_LINEAGE_CHECK_ONLY","status":"NEW_LINEAGE_CHECK_ONLY"}')
        self.assert_hold("REISSUE_RECEIPT_MISSING_OR_INVALID")

    def test_unverified_new_lineage_rejected(self):
        self.fresh["status"] = "NEW_LINEAGE_REISSUE_HOLD"
        self.assert_hold("NEW_LINEAGE_NOT_VERIFIED")

    def test_original_lineage_must_stay_on_hold(self):
        self.fresh["original_lineage_status"] = "RECOVERED"
        self.assert_hold("NEW_LINEAGE_NOT_VERIFIED")

    def test_cas_success_claim_rejected(self):
        self.fresh["cas_return_pass"] = True
        self.receipt.write_text(json.dumps(self.fresh), encoding="utf-8")
        self.assert_hold("REISSUE_RECEIPT_CLAIMS_UNPROVEN_PROGRESS")

    def test_cross_product_identity_rejected(self):
        self.fresh["identity_store_id"] = "OTHER_STORE"
        self.receipt.write_text(json.dumps(self.fresh), encoding="utf-8")
        self.assert_hold("REISSUE_RECEIPT_PRODUCT_OR_SOURCE_CONFLICT")

    def test_old_request_reuse_rejected(self):
        self.fresh["new_request_id"] = gate.OLD_REQUEST
        self.receipt.write_text(json.dumps(self.fresh), encoding="utf-8")
        self.assert_hold("REISSUE_RECEIPT_PRODUCT_OR_SOURCE_CONFLICT")

    def test_proposal_inside_factory_rejected(self):
        inside = self.checkout / "proposal.json"
        inside.write_text("{}")
        result = gate.precheck(self.checkout, inside, self.archive, self.receipt)
        self.assertEqual(result["reason"], "EVIDENCE_INSIDE_FACTORY_CHECKOUT")

    def test_zip_inside_factory_rejected(self):
        inside = self.checkout / "new.zip"
        inside.write_bytes(b"fixture")
        result = gate.precheck(self.checkout, self.proposal, inside, self.receipt)
        self.assertEqual(result["reason"], "EVIDENCE_INSIDE_FACTORY_CHECKOUT")

    def test_receipt_inside_factory_rejected(self):
        inside = self.checkout / "receipt.json"
        inside.write_text(json.dumps(self.fresh))
        result = gate.precheck(self.checkout, self.proposal, self.archive, inside)
        self.assertEqual(result["reason"], "EVIDENCE_INSIDE_FACTORY_CHECKOUT")

    def test_symlink_receipt_rejected(self):
        link = self.root / "linked.json"
        try:
            link.symlink_to(self.receipt)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        result = gate.precheck(self.checkout, self.proposal, self.archive, link)
        self.assertEqual(result["reason"], "REISSUE_RECEIPT_MISSING_OR_INVALID")

    def test_read_only_inputs(self):
        before = (self.proposal.read_bytes(), self.archive.read_bytes(), self.receipt.read_bytes())
        self.run_gate()
        self.assertEqual(before, (self.proposal.read_bytes(), self.archive.read_bytes(), self.receipt.read_bytes()))

    def test_cli_never_returns_success_exit_code(self):
        with patch.object(gate, "precheck", return_value=self.fresh):
            self.assertEqual(gate.main([
                "--factory-source-checkout", str(self.checkout),
                "--reissue-proposal", str(self.proposal),
                "--new-artifact-zip", str(self.archive),
                "--reissue-receipt", str(self.receipt),
            ]), 2)


if __name__ == "__main__":
    unittest.main()
