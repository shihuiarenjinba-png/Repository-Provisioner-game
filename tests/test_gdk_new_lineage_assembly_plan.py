"""Signal Sprint deterministic new-lineage staging PLAN negative fixtures.

No actual CAS, SDK, staging writes, or Store calls. The positive fixture is
structural check-only and deliberately does not authenticate the reviewer.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gdk_new_lineage_assembly_plan import assemble_plan, config_xml
from gdk_new_lineage_post_cas_gate import (
    NEW_REQUEST, OLD_REQUEST, SOURCE, EXE_SHA, RUN_ID, ARTIFACT_ID,
    BUILD_HEAD, OUTER_SHA, INNER_SHA,
)
from gdk_microsoft_game_config import ASSETS
from package_identity_provisioner import ConflictError

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


class AssemblyPlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.checkout = self.root / "factory"
        self.checkout.mkdir()
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.target = self.root / "staging-new"
        self.outer = self.root / "artifact.zip"
        self.version_path = self.root / "version.json"
        self.asset_path = self.root / "asset-review.json"
        for name, _ in ASSETS.values():
            (self.assets / name).write_bytes(("synthetic-" + name).encode())
        self.version = {
            "schema_version": 1, "decision": "APPROVED",
            "partner_center_selection": "GDK_GAME", "package_format": "MSIXVC2",
            "request_id": NEW_REQUEST, "source_sha": SOURCE,
            "exe_sha256": EXE_SHA, "package_version": "1.0.0.0",
            "reviewed_display_name": "Signal Sprint",
            "reviewed_by": "Independent Reviewer",
            "reviewed_at": "2026-11-02T00:00:00Z",
        }
        self.asset_review = {
            "schema_version": 1, "decision": "APPROVED",
            "request_id": NEW_REQUEST, "source_sha": SOURCE,
            "exe_sha256": EXE_SHA,
            "assets_sha256": {
                name: hashlib.sha256((self.assets / name).read_bytes()).hexdigest()
                for name, _ in ASSETS.values()
            },
            "reviewed_by": "Independent Reviewer",
            "reviewed_at": "2026-11-02T00:00:00Z",
        }
        self.save()

    def save(self):
        self.version_path.write_text(json.dumps(self.version))
        self.asset_path.write_text(json.dumps(self.asset_review))

    def evaluate(self, evidence=None, cas_error=None):
        def dimensions(path):
            for name, dims in ASSETS.values():
                if path.name == name:
                    return dims
            raise AssertionError("unexpected asset")
        def git(*args):
            if cas_error:
                raise ConflictError(cas_error)
            return "f" * 40
        with patch("gdk_new_lineage_assembly_plan.check_live",
                   return_value=live() if evidence is None else evidence), \
             patch("gdk_new_lineage_assembly_plan.verify_cas_git",
                   side_effect=git), \
             patch("gdk_new_lineage_assembly_plan.pinned_exe_from_outer",
                   return_value=(300000, EXE_SHA)), \
             patch("gdk_new_lineage_assembly_plan._png_dimensions",
                   side_effect=dimensions):
            return assemble_plan(self.checkout, self.outer, CAS, BUILD,
                                 self.assets, self.version_path,
                                 self.asset_path, self.target)

    def assert_hold(self, code):
        result = self.evaluate()
        self.assertEqual(result["status"], "NEW_LINEAGE_GDK_ASSEMBLY_HOLD")
        self.assertIn(code, result["reason"])
        self.assertFalse(result["staging_created"])
        self.assertFalse(self.target.exists())
        self.assertNotIn("files", result)

    def test_positive_deterministic_plan_without_staging(self):
        first, second = self.evaluate(), self.evaluate()
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "NEW_LINEAGE_GDK_ASSEMBLY_PLAN_CHECK_ONLY")
        self.assertEqual([f["destination"] for f in first["files"]],
                         sorted(["SignalSprint.exe", "MicrosoftGame.config",
                                 *(name for name, _ in ASSETS.values())]))
        self.assertEqual(next(f for f in first["files"]
                              if f["destination"] == "SignalSprint.exe")["sha256"],
                         EXE_SHA)
        self.assertFalse(self.target.exists())
        self.assertEqual(first["original_lineage_status"], "ARTIFACT_EXACT_BYTES_HOLD")
        for field in ("cas_return_pass", "review_authenticity_verified",
                      "ready_for_sdk", "gdk_sdk_validated", "real_msixvc_built",
                      "e2e_pass", "store_submitted", "staging_created"):
            self.assertIs(first[field], False)

    def test_missing_cas_proof(self):
        result = self.evaluate(cas_error="CAS_NOT_DIRECTLY_BASED_ON_SOURCE")
        self.assertIn("CAS_NOT_DIRECTLY_BASED_ON_SOURCE", result["reason"])
        self.assertNotIn("files", result)

    def test_foreign_title_id_cas_rejected(self):
        result = self.evaluate(cas_error="CAS_IDENTITY_OR_LINEAGE_MISMATCH:xbox_title_id")
        self.assertIn("xbox_title_id", result["reason"])

    def test_foreign_scid_cas_rejected(self):
        result = self.evaluate(cas_error="CAS_IDENTITY_OR_LINEAGE_MISMATCH:xbox_scid")
        self.assertIn("xbox_scid", result["reason"])

    def test_foreign_msa_id_cas_rejected(self):
        result = self.evaluate(cas_error="CAS_IDENTITY_OR_LINEAGE_MISMATCH:msa_app_id")
        self.assertIn("msa_app_id", result["reason"])

    def test_old_request_version_rejected(self):
        self.version["request_id"] = OLD_REQUEST
        self.save()
        self.assert_hold("REVIEW_LINEAGE_MISMATCH")

    def test_old_request_asset_rejected(self):
        self.asset_review["request_id"] = OLD_REQUEST
        self.save()
        self.assert_hold("REVIEW_LINEAGE_MISMATCH")

    def test_unapproved_version_rejected(self):
        self.version["decision"] = "PENDING"
        self.save()
        self.assert_hold("REVIEW_SCHEMA_OR_DECISION_INVALID")

    def test_missing_version_review(self):
        self.version_path.unlink()
        self.assert_hold("REQUIRED_FILE_MISSING")

    def test_missing_asset_review(self):
        self.asset_path.unlink()
        self.assert_hold("REQUIRED_FILE_MISSING")

    def test_wrong_exe_review(self):
        self.version["exe_sha256"] = "0" * 64
        self.save()
        self.assert_hold("REVIEW_LINEAGE_MISMATCH")

    def test_tampered_asset(self):
        (self.assets / "Logo.png").write_bytes(b"tampered")
        self.assert_hold("ASSET_DIGEST_MISMATCH:Logo.png")

    def test_unreviewed_asset(self):
        (self.assets / "extra.png").write_bytes(b"unreviewed")
        self.assert_hold("ASSET_DIRECTORY_CONTENTS_MISMATCH")

    def test_missing_asset(self):
        (self.assets / "Logo.png").unlink()
        self.assert_hold("ASSET_DIRECTORY_CONTENTS_MISMATCH")

    def test_staging_existing_directory_collision(self):
        self.target.mkdir()
        self.assert_hold("STAGING_TARGET_ALREADY_EXISTS")

    def test_staging_existing_file_collision(self):
        self.target.write_text("existing")
        self.assert_hold("STAGING_TARGET_ALREADY_EXISTS")

    def test_staging_inside_factory_rejected(self):
        self.target = self.checkout / "staging"
        self.assert_hold("INPUT_OR_TARGET_INSIDE_FACTORY_CHECKOUT")

    def test_old_artifact_evidence_rejected(self):
        evidence = live()
        evidence["github_artifact_id"] = 12706862577
        result = self.evaluate(evidence)
        self.assertIn("FACTORY_LINEAGE_MISMATCH", result["reason"])

    def test_foreign_product_evidence_rejected(self):
        evidence = live()
        evidence["new_request_id"] = "game-foreign"
        result = self.evaluate(evidence)
        self.assertIn("FACTORY_LINEAGE_MISMATCH", result["reason"])

    def test_unauthenticated_review_claim_rejected(self):
        self.version["authenticity_verified"] = True
        self.save()
        self.assert_hold("REVIEW_SCHEMA_OR_DECISION_INVALID")

    def test_config_contains_official_title_msa_and_version(self):
        xml = config_xml("1.0.0.0", "Signal Sprint").decode()
        self.assertIn("<TitleId>68721417</TitleId>", xml)
        self.assertIn("<MSAAppId>39852fc3-fa46-4bda-88aa-b35385488ced</MSAAppId>", xml)
        self.assertIn('Version="1.0.0.0"', xml)


if __name__ == "__main__":
    unittest.main()
