"""No SDK/CAS required: GDK MSIXVC2 result intake fail-closed tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from gdk_sdk_result_intake import intake
from package_identity_provisioner import ConflictError, PINNED_SIGNAL_SPRINT_JOB


def sha(data):
    return hashlib.sha256(data).hexdigest()


class GdkSdkResultIntakeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.plan_path = root / "plan.json"
        self.evidence_path = root / "result.json"
        self.log_path = root / "validation.log"
        self.log_path.write_bytes(b"synthetic validation output\n")
        self.output = root / "output"
        self.output.mkdir()
        self.package = self.output / "SignalSprint.msixvc2"
        self.package.write_bytes(b"synthetic package only")
        argv = ["makepkg.exe", "pack", "/msixvc2", "/d", str(root / "stage"),
                "/pc", "/pd", str(self.output), "/validationcritical"]
        self.plan = {
            "schema_version": 1, "status": "GDK_SDK_PACK_PLAN_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME", "package_format": "MSIXVC2",
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
            "cas_commit_sha": "b" * 40, "factory_head_sha": "c" * 40,
            "package_version": "1.0.1.0", "reviewed_display_name": "Signal Sprint",
            "verified_receipt_sha256": "d" * 64,
            "staging_files_sha256": {"SignalSprint.exe": "e" * 64,
                                      **{f"asset{i}.png": "f" * 64 for i in range(5)}},
            "sdk_command_argv_not_executed": argv,
            "sdk_required": "October 2026 GDK or later with managed makepkg.exe",
            "msixvc2_preview_public_certification_blocked": False,
            "public_release_requires_certification": True,
            "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
            "gdk_sdk_validated": False, "real_msixvc_built": False,
            "store_submitted": False,
        }
        self.evidence = {k: self.plan[k] for k in (
            "schema_version", "partner_center_selection", "package_format",
            "request_id", "source_sha", "cas_commit_sha", "factory_head_sha",
            "package_version", "reviewed_display_name",
            "verified_receipt_sha256", "staging_files_sha256", "store_submitted")}
        self.evidence.update({
            "status": "GDK_SDK_PACK_EXECUTED", "sdk_command_argv": argv,
            "sdk_executable": "makepkg.exe", "sdk_version": "October 2026 GDK SDK",
            "sdk_exit_code": 0,
            "validation_log_sha256": sha(self.log_path.read_bytes()),
            "package_filename": self.package.name,
            "package_sha256": sha(self.package.read_bytes()),
            "package_size_bytes": self.package.stat().st_size,
        })

    def check(self):
        self.plan_path.write_text(json.dumps(self.plan))
        self.evidence_path.write_text(json.dumps(self.evidence))
        return intake(self.plan_path, self.evidence_path, self.output, self.log_path)

    def test_byte_checks_never_claim_real_msix_pass(self):
        result = self.check()
        self.assertEqual(result["status"], "GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS")
        self.assertFalse(result["real_msix_pass"])
        self.assertFalse(result["e2e_pass"])
        self.assertFalse(result["gdk_sdk_validation_independently_verified"])

    def test_changed_package_rejected(self):
        self.package.write_bytes(b"tampered")
        with self.assertRaisesRegex(ConflictError, "package bytes"):
            self.check()

    def test_changed_validation_log_rejected(self):
        self.log_path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ConflictError, "validation log bytes"):
            self.check()

    def test_wrong_source_rejected(self):
        self.evidence["source_sha"] = "f" * 40
        with self.assertRaisesRegex(ConflictError, "source_sha"):
            self.check()

    def test_wrong_factory_head_rejected(self):
        self.evidence["factory_head_sha"] = "f" * 40
        with self.assertRaisesRegex(ConflictError, "factory_head_sha"):
            self.check()

    def test_failed_sdk_exit_rejected(self):
        self.evidence["sdk_exit_code"] = 1
        with self.assertRaisesRegex(ConflictError, "sdk_exit_code"):
            self.check()

    def test_makepkg2_command_rejected(self):
        self.evidence["sdk_command_argv"] = ["makepkg2.exe"]
        with self.assertRaisesRegex(ConflictError, "sdk_command_argv"):
            self.check()

    def test_claimed_store_submission_rejected(self):
        self.evidence["store_submitted"] = True
        with self.assertRaisesRegex(ConflictError, "store_submitted"):
            self.check()

    def test_package_path_traversal_rejected(self):
        self.evidence["package_filename"] = "../evil.msixvc2"
        with self.assertRaisesRegex(ConflictError, "filename"):
            self.check()

    def test_extra_output_rejected(self):
        (self.output / "extra.msixvc2").write_bytes(b"bad")
        with self.assertRaisesRegex(ConflictError, "exactly one"):
            self.check()

    def test_unexpected_schema_rejected(self):
        self.evidence["certified"] = True
        with self.assertRaisesRegex(ConflictError, "schema"):
            self.check()

    def test_duplicate_json_key_rejected(self):
        self.check()
        self.evidence_path.write_text(
            self.evidence_path.read_text().replace('"status":', '"status": "BAD", "status":', 1))
        with self.assertRaisesRegex(ConflictError, "duplicate JSON key"):
            intake(self.plan_path, self.evidence_path, self.output, self.log_path)

    def test_symlink_package_rejected(self):
        other = self.output.parent / "other.msixvc2"
        other.write_bytes(self.package.read_bytes())
        self.package.unlink()
        self.package.symlink_to(other)
        with self.assertRaisesRegex(ConflictError, "escapes|linked"):
            self.check()

    def test_plan_cannot_claim_sdk_success(self):
        self.plan["real_msixvc_built"] = True
        with self.assertRaisesRegex(ConflictError, "real_msixvc_built"):
            self.check()

    def test_preview_block_rejected(self):
        self.plan["msixvc2_preview_public_certification_blocked"] = True
        with self.assertRaisesRegex(ConflictError, "preview_public"):
            self.check()

    def test_wrong_output_path_rejected(self):
        changed = list(self.plan["sdk_command_argv_not_executed"])
        changed[7] = str(self.output.parent)
        self.plan["sdk_command_argv_not_executed"] = changed
        self.evidence["sdk_command_argv"] = changed
        with self.assertRaisesRegex(ConflictError, "output directory"):
            self.check()


if __name__ == "__main__":
    unittest.main()
