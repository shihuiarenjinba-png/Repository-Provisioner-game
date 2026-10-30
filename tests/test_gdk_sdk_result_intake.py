"""No SDK/CAS required: GDK MSIXVC2 result intake fail-closed tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_sdk_result_intake as sdk_intake

from gdk_sdk_result_intake import intake
from gdk_build_intake import EXE_SHA256
from gdk_msixvc2_preflight import MAX_FILE_BYTES
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
            "staging_files_sha256": {
                name: EXE_SHA256 if name == "SignalSprint.exe" else "f" * 64
                for name in MAX_FILE_BYTES
            },
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
            "sdk_executable": "makepkg.exe", "sdk_version": "2610.0.8000",
            "sdk_exit_code": 0,
            "validation_log_sha256": sha(self.log_path.read_bytes()),
            "package_filename": self.package.name,
            "package_sha256": sha(self.package.read_bytes()),
            "package_size_bytes": self.package.stat().st_size,
            "output_files_sha256": {self.package.name: sha(self.package.read_bytes())},
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

    def test_preview_sdk_claim_rejected_before_retail_handoff(self):
        self.evidence["sdk_version"] = "2604.5.7903"
        with self.assertRaisesRegex(ConflictError, "2610"):
            self.check()

    def test_unpinned_human_sdk_label_rejected(self):
        self.evidence["sdk_version"] = "October 2026 GDK SDK"
        with self.assertRaisesRegex(ConflictError, "2610"):
            self.check()

    def test_changed_package_rejected(self):
        self.package.write_bytes(b"tampered")
        with self.assertRaisesRegex(ConflictError, "package bytes"):
            self.check()

    def test_changed_validation_log_rejected(self):
        self.log_path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ConflictError, "validation log bytes"):
            self.check()

    def test_plan_rewritten_during_large_package_hash_rejected(self):
        self.plan_path.write_text(json.dumps(self.plan))
        self.evidence_path.write_text(json.dumps(self.evidence))
        original_hash = sdk_intake._hash_file

        def rewrite_after_package(path, *args):
            value = original_hash(path, *args)
            if Path(path) == self.package:
                # Still valid JSON, but not the bytes actually reviewed.
                self.plan_path.write_bytes(self.plan_path.read_bytes() + b" ")
            return value

        with patch.object(sdk_intake, "_hash_file", side_effect=rewrite_after_package):
            with self.assertRaisesRegex(ConflictError, "GDK plan changed during intake"):
                intake(self.plan_path, self.evidence_path, self.output, self.log_path)

    def test_sdk_result_rewritten_during_large_package_hash_rejected(self):
        self.plan_path.write_text(json.dumps(self.plan))
        self.evidence_path.write_text(json.dumps(self.evidence))
        original_hash = sdk_intake._hash_file

        def rewrite_after_package(path, *args):
            value = original_hash(path, *args)
            if Path(path) == self.package:
                self.evidence_path.write_bytes(self.evidence_path.read_bytes() + b" ")
            return value

        with patch.object(sdk_intake, "_hash_file", side_effect=rewrite_after_package):
            with self.assertRaisesRegex(ConflictError, "GDK SDK result changed during intake"):
                intake(self.plan_path, self.evidence_path, self.output, self.log_path)

    def test_sidecar_rewritten_during_large_package_hash_rejected(self):
        sidecar = self.output / "SubmissionValidator.xml"
        sidecar.write_bytes(b"<reviewed/>")
        self.evidence["output_files_sha256"][sidecar.name] = sha(sidecar.read_bytes())
        self.plan_path.write_text(json.dumps(self.plan))
        self.evidence_path.write_text(json.dumps(self.evidence))
        original_hash = sdk_intake._hash_file

        def rewrite_after_package(path, *args):
            value = original_hash(path, *args)
            if Path(path) == self.package:
                sidecar.write_bytes(b"<modified/>")
            return value

        with patch.object(sdk_intake, "_hash_file", side_effect=rewrite_after_package):
            with self.assertRaisesRegex(ConflictError, "GDK SDK sidecar changed during intake"):
                intake(self.plan_path, self.evidence_path, self.output, self.log_path)

    def test_unreviewed_staging_filename_rejected(self):
        # A plan and SDK result can agree on an unreviewed filename; intake
        # must still reject it independently of the earlier pack-plan gate.
        hashes = self.plan["staging_files_sha256"]
        hashes["unreviewed.dat"] = hashes.pop("MicrosoftGame.config")
        with self.assertRaisesRegex(ConflictError, "staging hashes"):
            self.check()

    def test_substituted_executable_digest_rejected(self):
        # Both receipts still agree, but the immutable Factory EXE pin differs.
        self.plan["staging_files_sha256"]["SignalSprint.exe"] = "0" * 64
        with self.assertRaisesRegex(ConflictError, "immutable executable"):
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

    def test_reserved_windows_package_name_rejected(self):
        self.evidence["package_filename"] = "CON.msixvc2"
        with self.assertRaisesRegex(ConflictError, "unsafe Windows filename"):
            self.check()

    def test_extra_output_rejected(self):
        (self.output / "extra.msixvc2").write_bytes(b"bad")
        with self.assertRaisesRegex(ConflictError, "inventory"):
            self.check()

    def test_sdk_sidecars_are_hashed_without_claiming_real_build(self):
        sidecars = {
            "SignalSprint.ekb": b"synthetic EKB",
            "SubmissionValidator.xml": b"<synthetic/>",
            "symbols.zip": b"synthetic symbols",
        }
        for name, payload in sidecars.items():
            (self.output / name).write_bytes(payload)
            self.evidence["output_files_sha256"][name] = sha(payload)
        receipt = self.check()
        self.assertEqual(receipt["sdk_output_sidecar_count"], 3)
        self.assertEqual(set(receipt["output_files_sha256"]), set(sidecars) | {self.package.name})
        self.assertIs(receipt["real_msix_pass"], False)

    def test_sidecar_tampering_rejected(self):
        extra = self.output / "SubmissionValidator.xml"
        extra.write_bytes(b"first")
        self.evidence["output_files_sha256"][extra.name] = sha(b"first")
        extra.write_bytes(b"changed")
        with self.assertRaisesRegex(ConflictError, "sidecar bytes"):
            self.check()

    def test_unreviewed_sidecar_extension_rejected(self):
        extra = self.output / "unexpected.exe"
        extra.write_bytes(b"not SDK evidence")
        self.evidence["output_files_sha256"][extra.name] = sha(extra.read_bytes())
        with self.assertRaisesRegex(ConflictError, "unreviewed sidecar"):
            self.check()

    def test_second_package_rejected(self):
        extra = self.output / "second.msixvc"
        extra.write_bytes(b"other package")
        self.evidence["output_files_sha256"][extra.name] = sha(extra.read_bytes())
        with self.assertRaisesRegex(ConflictError, "unreviewed sidecar"):
            self.check()

    def test_missing_sidecar_inventory_rejected(self):
        (self.output / "SubmissionValidator.xml").write_bytes(b"validator")
        with self.assertRaisesRegex(ConflictError, "inventory"):
            self.check()

    def test_legacy_extension_valid_for_msixvc2_output(self):
        # Microsoft documents the MSIXVC2 package as <package>.msixvc.
        legacy = self.output / "SignalSprint.msixvc"
        self.package.rename(legacy)
        self.evidence["package_filename"] = legacy.name
        self.evidence["output_files_sha256"] = {legacy.name: sha(legacy.read_bytes())}
        self.assertEqual(self.check()["package_filename"], legacy.name)

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
        try:
            self.package.symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable on this Windows runner")
        with self.assertRaisesRegex(ConflictError, "escapes|linked"):
            self.check()

    def test_symlinked_output_parent_rejected(self):
        alias = self.output.parent / "output-alias"
        try:
            alias.symlink_to(self.output.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink creation unavailable")
        self.output = alias / "output"
        with self.assertRaisesRegex(ConflictError, "GDK output contains symlink or junction"):
            self.check()

    def test_symlinked_validation_log_parent_rejected(self):
        alias = self.log_path.parent / "log-alias"
        try:
            alias.symlink_to(self.log_path.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink creation unavailable")
        self.log_path = alias / "validation.log"
        with self.assertRaisesRegex(ConflictError, "GDK validation log contains symlink or junction"):
            self.check()

    def test_symlinked_plan_parent_rejected(self):
        alias = self.plan_path.parent / "plan-alias"
        try:
            alias.symlink_to(self.plan_path.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink creation unavailable")
        self.plan_path = alias / "plan.json"
        with self.assertRaisesRegex(ConflictError, "GDK plan contains symlink or junction"):
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
