"""No-authorization dry-run tests: synthetic archive, no SDK or real CAS."""
import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import gdk_new_lineage_staging_dry_run as stage


def archive(items):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in items.items():
            z.writestr(name, data)
    return output.getvalue()


class IsolatedStageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.exe = b"MZ" + b"\0" * 120_000
        inner = archive({"SignalSprint.exe": self.exe,
                         "provenance.json": b"{}", "provisioner-request.json": b"{}"})
        outer = archive({"new-lineage.zip": inner, "lineage-receipt.json": b"{}"})
        self.path = self.root / "artifact.zip"
        self.path.write_bytes(outer)
        self.patches = [
            patch.object(stage, "OUTER_SHA", hashlib.sha256(outer).hexdigest()),
            patch.object(stage, "INNER_SHA", hashlib.sha256(inner).hexdigest()),
            patch.object(stage, "EXE_SHA", hashlib.sha256(self.exe).hexdigest()),
            patch.object(stage, "reconcile", return_value={
                "status": "CROSS_REPO_INTEGRATION_HOLD",
                "reason": "CAS_VERSION_AND_ASSET_APPROVALS_NOT_AVAILABLE",
                "artifact_manifest_bound": True,
            }),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.receipt = {"new_request_id": stage.NEW_REQUEST}

    def execute(self, **kwargs):
        return stage.dry_run(self.path, self.receipt, temp_parent=self.root, **kwargs)

    def test_real_exe_only_transient_and_cleaned(self):
        before = set(self.root.iterdir())
        result = self.execute()
        self.assertEqual(result["status"], "NEW_LINEAGE_STAGING_DRY_RUN_HOLD")
        self.assertEqual(result["verified_transient_files"][0]["sha256"], stage.EXE_SHA)
        self.assertEqual(result["verified_transient_files"][0]["size_bytes"], len(self.exe))
        self.assertEqual(len(result["missing_files"]), 5)
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertFalse(result["staging_persisted"])
        self.assertFalse(result["ready_for_sdk"])

    def test_deterministic_rerun(self):
        self.assertEqual(self.execute(), self.execute())

    def test_tampered_outer_bytes_hold(self):
        self.path.write_bytes(self.path.read_bytes() + b"tampered")
        result = self.execute()
        self.assertIn("OUTER_ZIP_DIGEST_MISMATCH", result["reason"])
        self.assertEqual(result["verified_transient_files"], [])

    def test_foreign_or_old_request_rejected_by_existing_reconciler(self):
        for error in ("LIVE_RECEIPT_LINEAGE_MISMATCH", "LEGACY_ARTIFACT_SUBSTITUTION",
                      "ASSEMBLY_LINEAGE_IDENTITY_MISMATCH"):
            with self.subTest(error=error), patch.object(stage, "reconcile", return_value={
                "status": "CROSS_REPO_INTEGRATION_HOLD", "reason": error,
                "artifact_manifest_bound": False,
            }):
                self.assertIn(error, self.execute()["reason"])

    def test_unapproved_plan_cannot_be_used_to_stage_assets(self):
        with patch.object(stage, "reconcile", return_value={
            "status": "CROSS_REPO_INTEGRATION_HOLD",
            "reason": "ASSEMBLY_FALSE_AUTHORIZATION", "artifact_manifest_bound": True,
        }):
            result = self.execute(assembly_plan={"files": []}, asset_dir=self.root)
        self.assertIn("ASSEMBLY_PLAN_NOT_VERIFIED", result["reason"])
        self.assertEqual(result["verified_transient_files"], [])

    def test_structural_plan_is_still_not_reviewer_authority(self):
        with patch.object(stage, "reconcile", return_value={
            "status": "CROSS_REPO_ASSEMBLY_CONTRACT_CHECK_ONLY",
            "reason": "NOT_AUTHORIZED_FOR_CAS_SDK_OR_STORE",
            "artifact_manifest_bound": True,
        }):
            result = self.execute(assembly_plan={"status": "NEW_LINEAGE_GDK_ASSEMBLY_PLAN_CHECK_ONLY"},
                                  asset_dir=self.root)
        self.assertEqual(len(result["verified_transient_files"]), 1)
        self.assertEqual(len(result["missing_files"]), 5)
        self.assertFalse(result["review_authenticity_verified"])

    def test_symlink_temp_root_rejected(self):
        linked = self.root / "linked"
        try:
            linked.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Windows runner cannot create symlinks")
        result = stage.dry_run(self.path, self.receipt, temp_parent=linked)
        self.assertIn("TEMP_PARENT_MISSING_OR_SYMLINK", result["reason"])

    def test_missing_artifact_rejected(self):
        self.path.unlink()
        result = self.execute()
        self.assertIn("REQUIRED_INPUT_MISSING", result["reason"])

    def test_wrong_exe_digest_rejected(self):
        with patch.object(stage, "EXE_SHA", "0" * 64):
            result = self.execute()
        self.assertIn("EXE_DIGEST_OR_FORMAT_MISMATCH", result["reason"])


if __name__ == "__main__":
    unittest.main()
