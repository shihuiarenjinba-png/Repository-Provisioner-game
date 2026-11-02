"""Negative fixtures for Signal Sprint's distinct post-CAS GDK lineage.

All positive cases are CHECK_ONLY, never CAS, SDK, MSIXVC2 or Store PASS.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gdk_new_lineage_post_cas_gate import (
    check_only, verify_cas_git, verify_staging, NEW_REQUEST, SOURCE, EXE_SHA,
    RUN_ID, ARTIFACT_ID, BUILD_HEAD, OUTER_SHA, INNER_SHA,
    REVIEW_KEYS, ASSET_KEYS,
)
from gdk_build_intake import APPROVED_PATH, APPROVED_FIELDS
from package_identity_provisioner import (
    ConflictError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY, PINNED_SIGNAL_SPRINT_JOB,
)

CAS = "a" * 40
BUILD = "b" * 40


def live():
    return {
        "status": "FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY",
        "new_request_id": NEW_REQUEST, "source_sha": SOURCE,
        "build_head_sha": BUILD_HEAD, "github_run_id": RUN_ID,
        "github_artifact_id": ARTIFACT_ID,
        "outer_github_zip_sha256": OUTER_SHA,
        "inner_factory_zip_sha256": INNER_SHA, "exe_sha256": EXE_SHA,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "ready_for_cas": False, "cas_return_pass": False,
        "real_msixvc_built": False, "store_submitted": False,
    }


def approved():
    value = dict(PINNED_SIGNAL_SPRINT_JOB)
    value["request_id"] = NEW_REQUEST
    value.update(PINNED_SIGNAL_SPRINT_GDK_IDENTITY)
    value.update({
        "schema_version": "1.0", "reviewed": True,
        "verified_source_sha": SOURCE, "package_sha256": EXE_SHA,
        "signature_status": "UNSIGNED_QA",
        "source": "partner_center_user_provided",
        "identity_source": "USER_PROVIDED_PARTNER_CENTER",
        "packaging_family": "GDK", "provided_at": "2026-11-02T00:00:00Z",
    })
    assert set(value) == APPROVED_FIELDS
    return value


class PostCasGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.staging = self.root / "staging"
        self.staging.mkdir()
        self.outer = self.root / "artifact.zip"
        self.version = self.root / "version.json"
        self.assets = self.root / "assets.json"
        self.version_data = {
            "schema_version": 1, "decision": "APPROVED",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": NEW_REQUEST, "source_sha": SOURCE,
            "exe_sha256": EXE_SHA, "package_version": "1.0.0.0",
            "reviewed_display_name": "Signal Sprint",
            "reviewed_by": "Independent Reviewer",
            "reviewed_at": "2026-11-02T00:00:00Z",
        }
        self.asset_data = {
            "schema_version": 1, "decision": "APPROVED",
            "request_id": NEW_REQUEST, "source_sha": SOURCE,
            "exe_sha256": EXE_SHA, "assets_sha256": {
                "StoreLogo.png": "1" * 64, "Logo.png": "2" * 64,
                "SmallLogo.png": "3" * 64, "SplashScreen.png": "4" * 64,
            }, "reviewed_by": "Independent Reviewer",
            "reviewed_at": "2026-11-02T00:00:00Z",
        }
        self.save()

    def save(self):
        self.version.write_text(json.dumps(self.version_data))
        self.assets.write_text(json.dumps(self.asset_data))

    def evaluate(self, evidence=None):
        with patch("gdk_new_lineage_post_cas_gate.check_live",
                   return_value=live() if evidence is None else evidence), \
             patch("gdk_new_lineage_post_cas_gate.verify_cas_git",
                   return_value="f" * 40), \
             patch("gdk_new_lineage_post_cas_gate.verify_staging",
                   return_value={"SignalSprint.exe": EXE_SHA}):
            return check_only(self.checkout, self.outer, CAS, BUILD,
                              self.staging, self.version, self.assets)

    def assert_hold(self, expected):
        result = self.evaluate()
        self.assertEqual(result["status"], "NEW_LINEAGE_GDK_POST_CAS_HOLD")
        self.assertIn(expected, result["reason"])
        self.assertIs(result["ready_for_sdk"], False)

    def test_check_only_does_not_authorize_sdk_or_cas(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "NEW_LINEAGE_GDK_POST_CAS_CHECK_ONLY")
        for field in ("cas_return_pass", "approval_authenticity_verified",
                      "version_review_authenticity_verified",
                      "asset_review_authenticity_verified", "gdk_sdk_validated",
                      "real_msixvc_built", "ready_for_sdk", "e2e_pass",
                      "store_submitted"):
            self.assertIs(result[field], False)
        self.assertEqual(result["original_lineage_status"], "ARTIFACT_EXACT_BYTES_HOLD")

    def test_old_request_rejected(self):
        self.version_data["request_id"] = PINNED_SIGNAL_SPRINT_JOB["request_id"]
        self.save()
        self.assert_hold("REVIEW_LINEAGE_MISMATCH")

    def test_foreign_exe_rejected(self):
        self.version_data["exe_sha256"] = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
        self.save()
        self.assert_hold("REVIEW_LINEAGE_MISMATCH")

    def test_wrong_route_rejected(self):
        self.version_data["partner_center_selection"] = "MSIX_OR_PWA_GAME"
        self.save()
        self.assert_hold("VERSION_REVIEW_ROUTE_MISMATCH")

    def test_version_unapproved_rejected(self):
        self.version_data["decision"] = "PENDING"
        self.save()
        self.assert_hold("REVIEW_SCHEMA_OR_DECISION_INVALID")

    def test_assets_unapproved_rejected(self):
        self.asset_data["decision"] = "PENDING"
        self.save()
        self.assert_hold("REVIEW_SCHEMA_OR_DECISION_INVALID")

    def test_missing_asset_review_rejected(self):
        self.assets.unlink()
        self.assert_hold("REQUIRED_FILE_MISSING")

    def test_review_claiming_authentication_rejected(self):
        self.version_data["authenticity_verified"] = True
        self.save()
        self.assert_hold("REVIEW_SCHEMA_OR_DECISION_INVALID")

    def test_missing_version_rejected(self):
        self.version_data["package_version"] = ""
        self.save()
        self.assert_hold("version")

    def test_invalid_review_timestamp_rejected(self):
        self.version_data["reviewed_at"] = "tomorrow"
        self.save()
        self.assert_hold("REVIEW_TIMESTAMP_INVALID")

    def test_placeholder_reviewer_rejected(self):
        self.asset_data["reviewed_by"] = "tester"
        self.save()
        self.assert_hold("REVIEWER_INVALID")

    def test_wrong_build_head_rejected(self):
        evidence = live()
        evidence["build_head_sha"] = "f" * 40
        result = self.evaluate(evidence)
        self.assertIn("LIVE_LINEAGE_MISMATCH", result["reason"])

    def test_wrong_github_artifact_rejected(self):
        evidence = live()
        evidence["github_artifact_id"] = 12706862577
        result = self.evaluate(evidence)
        self.assertIn("LIVE_LINEAGE_MISMATCH", result["reason"])

    def test_unverified_github_record_rejected(self):
        result = self.evaluate({"status": "FACTORY_NEW_LINEAGE_GITHUB_HOLD"})
        self.assertIn("LIVE_GITHUB_EVIDENCE_NOT_VERIFIED", result["reason"])

    def test_staging_inside_checkout_rejected(self):
        result = check_only(self.checkout, self.outer, CAS, BUILD,
                            self.checkout / "staging", self.version, self.assets)
        self.assertIn("EVIDENCE_OR_STAGING_INSIDE_FACTORY_CHECKOUT", result["reason"])

    def test_cas_identity_title_id_mixing_rejected(self):
        self.check_git_identity("xbox_title_id", "BAD_TITLE")

    def test_cas_identity_scid_mixing_rejected(self):
        self.check_git_identity("xbox_scid", "00000000-0000-0000-0000-000000000000")

    def test_cas_identity_msa_mixing_rejected(self):
        self.check_git_identity("msa_app_id", "00000000-0000-0000-0000-000000000000")

    def test_cas_identity_old_request_rejected(self):
        self.check_git_identity("request_id", PINNED_SIGNAL_SPRINT_JOB["request_id"])

    def test_cas_identity_old_exe_rejected(self):
        self.check_git_identity("package_sha256", "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad")

    def check_git_identity(self, field, replacement):
        value = approved()
        value[field] = replacement
        def fake_git(repo, *args):
            command = " ".join(args)
            if command == "rev-parse HEAD":
                return BUILD.encode()
            if command == "rev-parse " + CAS + "^":
                return SOURCE.encode()
            if command.startswith("diff-tree"):
                return APPROVED_PATH.encode()
            if command.startswith("symbolic-ref"):
                return b"codex/game-signal-sprint-gdk-build-test"
            if command.startswith("show "):
                return json.dumps(value).encode()
            if command.startswith("rev-parse " + CAS + ":"):
                return b"f" * 40
            return b""
        with patch("gdk_new_lineage_post_cas_gate._git", side_effect=fake_git):
            with self.assertRaisesRegex(ConflictError, "CAS_IDENTITY_OR_LINEAGE_MISMATCH"):
                verify_cas_git(self.checkout, CAS, BUILD)


if __name__ == "__main__":
    unittest.main()
