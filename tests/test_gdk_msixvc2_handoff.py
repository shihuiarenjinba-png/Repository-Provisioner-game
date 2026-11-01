"""Synthetic, no-GDK-SDK tests for Signal Sprint's version-reviewed handoff."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_msixvc2_handoff as handoff
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB


SOURCE = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
CAS = "a" * 40
BUILD = "b" * 40


class GdkMsixvc2HandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.checkout = self.root / "factory"
        self.checkout.mkdir()
        self.staging = self.root / "staging"
        self.staging.mkdir()
        self.artifact = self.root / "original.zip"
        self.review_file = self.root / "review.json"
        self.receipt = self.root / "preflight.json"
        self.review = {
            "schema_version": 1,
            "decision": "APPROVED",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": SOURCE,
            "package_version": "1.0.1.0",
            "reviewed_display_name": "Signal Sprint",
            "reviewed_by": "Fixture Operator",
            "reviewed_at": "2026-11-01T23:00:00+09:00",
        }
        self.preflight = {
            "status": "GDK_MSIXVC2_STAGING_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": SOURCE,
            "cas_commit_sha": CAS,
            "factory_head_sha": BUILD,
            "package_version": "1.0.1.0",
            "pinned_artifact_zip_sha256": handoff.ARTIFACT_SHA256,
            "pinned_exe_sha256": handoff.EXE_SHA256,
            "build_branch": "codex/game-signal-sprint-gdk-build-fixture",
            "approved_identity_blob_sha": "c" * 40,
            "staging_files_sha256": {
                "SignalSprint.exe": handoff.EXE_SHA256,
                "MicrosoftGame.config": "d" * 64,
                "Logo.png": "e" * 64,
            },
        }
        self.write_review()
        self.write_receipt()
        self.patch_recheck = patch.object(handoff, "recheck", side_effect=self.fake_recheck)
        self.patch_recheck.start()
        self.addCleanup(self.patch_recheck.stop)

    def write_review(self):
        self.review_file.write_text(json.dumps(self.review), encoding="utf-8")

    def write_receipt(self):
        self.receipt.write_text(json.dumps(self.preflight), encoding="utf-8")

    def fake_recheck(self, checkout, artifact, cas, build, staging, version, display, receipt):
        self.assertEqual(version, self.review["package_version"])
        self.assertEqual(display, self.review["reviewed_display_name"])
        self.assertEqual(cas, CAS)
        self.assertEqual(build, BUILD)
        return {
            "status": "GDK_MSIXVC2_RECHECK_PASS",
            "partner_center_selection": "GDK_GAME",
            "source_sha": SOURCE,
            "cas_commit_sha": CAS,
            "factory_head_sha": BUILD,
            "verified_receipt_sha256": hashlib.sha256(self.receipt.read_bytes()).hexdigest(),
            "staging_files_sha256": self.preflight["staging_files_sha256"],
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
        }

    def run_gate(self):
        return handoff.create_handoff(
            self.checkout, self.artifact, CAS, BUILD, self.staging,
            self.review_file, self.receipt,
        )

    def test_valid_synthetic_contract_is_check_only(self):
        result = self.run_gate()
        self.assertEqual(result["status"], "GDK_MSIXVC2_HANDOFF_CHECK_ONLY")
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertEqual(result["package_format"], "MSIXVC2")
        self.assertEqual(result["source_sha"], SOURCE)
        self.assertEqual(result["factory_head_sha"], BUILD)
        self.assertEqual(result["identity"]["store_id"], "9N21MJM7S57P")
        self.assertEqual(result["identity"]["xbox_title_id"], "68721417")
        self.assertEqual(result["identity"]["xbox_scid"], "00000000-0000-0000-0000-000068721417")
        self.assertEqual(result["identity"]["msa_app_id"], "39852fc3-fa46-4bda-88aa-b35385488ced")
        self.assertEqual(result["microsoft_game_config_sha256"], "d" * 64)
        self.assertFalse(result["version_review_authenticity_verified"])
        for key in ("gdk_sdk_validated", "real_msixvc_built", "cas_return_pass", "e2e_pass", "store_submitted"):
            self.assertIs(result[key], False)

    def test_review_version_is_independent_of_identity(self):
        self.review["package_version"] = "2.0.0.0"
        self.write_review()
        self.preflight["package_version"] = "2.0.0.0"
        self.write_receipt()
        self.assertEqual(self.run_gate()["package_version"], "2.0.0.0")

    def test_wrong_version_rejected(self):
        self.review["package_version"] = "1.0.1.9"
        self.write_review()
        with self.assertRaises(HoldError):
            self.run_gate()

    def test_wrong_source_rejected(self):
        self.review["source_sha"] = "f" * 40
        self.write_review()
        with self.assertRaisesRegex(ConflictError, "source_sha"):
            self.run_gate()

    def test_wrong_routing_rejected(self):
        self.review["partner_center_selection"] = "MSIX_OR_PWA_GAME"
        self.write_review()
        with self.assertRaisesRegex(ConflictError, "partner_center_selection"):
            self.run_gate()

    def test_extra_approval_field_rejected(self):
        self.review["real_msixvc_built"] = True
        self.write_review()
        with self.assertRaisesRegex(ConflictError, "schema"):
            self.run_gate()

    def test_duplicate_json_key_rejected(self):
        self.review_file.write_text('{"decision":"APPROVED","decision":"APPROVED"}', encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.run_gate()

    def test_float_json_rejected(self):
        self.review_file.write_text('{"schema_version":1e999}', encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.run_gate()

    def test_review_without_reviewer_rejected(self):
        self.review["reviewed_by"] = "placeholder"
        self.write_review()
        with self.assertRaises(HoldError):
            self.run_gate()

    def test_invalid_review_date_rejected(self):
        self.review["reviewed_at"] = "2026-11-31T23:00:00+09:00"
        self.write_review()
        with self.assertRaises(HoldError):
            self.run_gate()

    def test_wrong_exe_digest_rejected(self):
        self.preflight["pinned_exe_sha256"] = "f" * 64
        self.write_receipt()
        with self.assertRaisesRegex(ConflictError, "pinned_exe_sha256"):
            self.run_gate()

    def test_wrong_config_digest_rejected(self):
        self.preflight["staging_files_sha256"]["MicrosoftGame.config"] = "broken"
        self.write_receipt()
        with self.assertRaisesRegex(ConflictError, "staging hash"):
            self.run_gate()

    def test_review_inside_factory_checkout_rejected(self):
        inside = self.checkout / "review.json"
        inside.write_text(self.review_file.read_text())
        with self.assertRaisesRegex(ConflictError, "outside Factory"):
            handoff.create_handoff(
                self.checkout, self.artifact, CAS, BUILD, self.staging,
                inside, self.receipt,
            )

    def test_receipt_inside_factory_checkout_rejected(self):
        inside = self.checkout / "receipt.json"
        inside.write_text(self.receipt.read_text())
        with self.assertRaisesRegex(ConflictError, "outside Factory"):
            handoff.create_handoff(
                self.checkout, self.artifact, CAS, BUILD, self.staging,
                self.review_file, inside,
            )

    def test_symlink_review_rejected(self):
        linked = self.root / "linked-review.json"
        linked.symlink_to(self.review_file)
        with self.assertRaisesRegex(ConflictError, "regular unlinked"):
            handoff.read_version_review(linked)

    def test_stale_second_pass_rejected(self):
        with patch.object(handoff, "recheck", return_value={"status": "UNVERIFIED"}):
            with self.assertRaisesRegex(ConflictError, "second-pass"):
                self.run_gate()

    def test_receipt_staging_mismatch_rejected(self):
        def changed(*args):
            result = self.fake_recheck(*args)
            result["staging_files_sha256"] = {"SignalSprint.exe": "f" * 64}
            return result
        with patch.object(handoff, "recheck", side_effect=changed):
            with self.assertRaisesRegex(ConflictError, "second-pass"):
                self.run_gate()


if __name__ == "__main__":
    unittest.main()
