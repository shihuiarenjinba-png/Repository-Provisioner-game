"""No-SDK, no-CAS regression tests for the MSIXVC2 Windows handoff plan."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_sdk_pack_plan as plan
from package_identity_provisioner import ConflictError


class GdkSdkPackPlanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.factory = root / "factory"
        self.staging = root / "stage"
        self.output = root / "output"
        for d in (self.factory, self.staging, self.output):
            d.mkdir()
        self.zip = root / "pinned.zip"
        self.zip.write_bytes(b"immutable artifact")
        self.receipt = root / "receipt.json"
        self.receipt.write_text("{}")
        self.hashes = {}
        for name in plan.MAX_FILE_BYTES:
            data = b"exe" if name == "SignalSprint.exe" else name.encode()
            (self.staging / name).write_bytes(data)
            self.hashes[name] = hashlib.sha256(data).hexdigest()
        self.evidence = {
            "schema_version": 1,
            "status": "GDK_MSIXVC2_RECHECK_PASS",
            "partner_center_selection": "GDK_GAME",
            "request_id": plan.PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": plan.PINNED_SIGNAL_SPRINT_JOB["source_sha"],
            "cas_commit_sha": "b" * 40,
            "factory_head_sha": "c" * 40,
            "product_history_gate": "NO_PRODUCT_PATH_CHANGES_SINCE_CAS",
            "staging_files_sha256": self.hashes,
            "verified_receipt_sha256": "d" * 64,
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
        }
        p1 = patch.object(plan, "recheck", side_effect=lambda *args: self.evidence)
        p2 = patch.object(plan, "EXE_SHA256", self.hashes["SignalSprint.exe"])
        p1.start()
        p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def run_plan(self):
        return plan.make_pack_plan(self.factory, self.zip, "b" * 40, "c" * 40,
                                   self.staging, "1.0.1.0", "Signal Sprint",
                                   self.receipt, self.output)

    def test_safe_plan_is_not_an_sdk_execution(self):
        result = self.run_plan()
        self.assertEqual(result["status"], "GDK_SDK_PACK_PLAN_CHECK_ONLY")
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertEqual(result["sdk_command_argv_not_executed"][:3],
                         ["makepkg.exe", "pack", "/msixvc2"])
        self.assertIn("/validationcritical", result["sdk_command_argv_not_executed"])
        self.assertNotIn("upload", result["sdk_command_argv_not_executed"])
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["msixvc2_preview_public_certification_blocked"])
        self.assertTrue(result["public_release_requires_certification"])
        self.assertIn("October 2026 GDK", result["sdk_required"])
        self.assertNotIn("makepkg2.exe", result["sdk_command_argv_not_executed"])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_changed_exe_after_recheck_rejected(self):
        (self.staging / "SignalSprint.exe").write_bytes(b"tampered")
        with self.assertRaisesRegex(ConflictError, "changed after recheck"):
            self.run_plan()

    def test_changed_asset_after_recheck_rejected(self):
        (self.staging / "StoreLogo.png").write_bytes(b"tampered")
        with self.assertRaisesRegex(ConflictError, "changed after recheck"):
            self.run_plan()

    def test_missing_staging_file_rejected(self):
        (self.staging / "SmallLogo.png").unlink()
        with self.assertRaises(OSError):
            self.run_plan()

    def test_extra_manifest_entry_rejected(self):
        self.evidence["staging_files_sha256"] = dict(self.hashes, evil="a" * 64)
        with self.assertRaisesRegex(ConflictError, "manifest incomplete"):
            self.run_plan()

    def test_wrong_source_rejected(self):
        self.evidence["source_sha"] = "f" * 40
        with self.assertRaisesRegex(ConflictError, "source_sha"):
            self.run_plan()

    def test_false_sdk_success_rejected(self):
        self.evidence["gdk_sdk_validated"] = True
        with self.assertRaisesRegex(ConflictError, "gdk_sdk_validated"):
            self.run_plan()

    def test_output_must_be_empty(self):
        (self.output / "old.msixvc").write_bytes(b"old")
        with self.assertRaisesRegex(ConflictError, "empty"):
            self.run_plan()

    def test_output_cannot_overlap_staging(self):
        self.output = self.staging
        with self.assertRaisesRegex(ConflictError, "isolated"):
            self.run_plan()

    def test_output_cannot_overlap_factory(self):
        self.output = self.factory
        with self.assertRaisesRegex(ConflictError, "isolated"):
            self.run_plan()

    def test_output_symlink_rejected(self):
        link = self.output.parent / "output-link"
        link.symlink_to(self.output, target_is_directory=True)
        self.output = link
        with self.assertRaisesRegex(Exception, "linked"):
            self.run_plan()

    def test_receipt_claims_store_submission_rejected(self):
        self.evidence["store_submitted"] = True
        with self.assertRaisesRegex(ConflictError, "store_submitted"):
            self.run_plan()


if __name__ == "__main__":
    unittest.main()
