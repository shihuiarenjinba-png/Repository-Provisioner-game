"""No-SDK, synthetic regression tests for transferred Signal Sprint GDK bytes."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from gdk_e2e_handoff_verify import verify_handoff
from package_identity_provisioner import (
    ConflictError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB,
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GdkE2eHandoffVerifyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.package = self.root / "package.msixvc2"
        self.log = self.root / "validation.log"
        self.manifest_path = self.root / "handoff.json"
        self.package.write_bytes(b"synthetic GDK bytes: not a real package")
        self.log.write_bytes(b"synthetic SDK log: not SDK proof")
        self.manifest = {
            "schema_version": 1,
            "status": "GDK_E2E_QA_INTAKE_PENDING",
            "type": "game",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_repository": PINNED_SIGNAL_SPRINT_JOB["source_repository"],
            "source_branch": PINNED_SIGNAL_SPRINT_JOB["source_branch"],
            "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
            "cas_commit_sha": "b" * 40,
            "factory_head_sha": "c" * 40,
            "store_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"],
            "package_identity_name": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["name"],
            "package_version": "1.0.1.0",
            "package_filename": "package.msixvc2",
            "original_sdk_filename": "SignalSprint.msixvc2",
            "package_sha256": sha(self.package.read_bytes()),
            "package_size_bytes": self.package.stat().st_size,
            "validation_log_filename": "validation.log",
            "validation_log_sha256": sha(self.log.read_bytes()),
            "sdk_result_evidence_sha256": "d" * 64,
            "sdk_pack_plan_sha256": "e" * 64,
            "sdk_version_claim": "October 2026 GDK SDK",
            "sdk_exit_code_claim": 0,
            "gdk_sdk_validation_independently_verified": False,
            "real_msix_pass": False,
            "e2e_pass": False,
            "store_submitted": False,
            "next_stage": "WINDOWS_E2E_INDEPENDENT_GDK_VALIDATION_INSTALL_GUI_QA",
        }

    def check(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return verify_handoff(self.root)

    def test_valid_synthetic_transfer_is_not_sdk_or_e2e_approval(self):
        result = self.check()
        self.assertEqual(result["status"], "GDK_E2E_TRANSFER_BYTES_CHECK_PASS")
        self.assertEqual(result["package_sha256"], self.manifest["package_sha256"])
        self.assertEqual(result["source_sha"], PINNED_SIGNAL_SPRINT_JOB["source_sha"])
        self.assertFalse(result["real_msix_pass"])
        self.assertFalse(result["e2e_pass"])
        self.assertFalse(result["gdk_sdk_validation_independently_verified"])

    def test_package_tampering_rejected(self):
        self.package.write_bytes(b"modified synthetic package")
        with self.assertRaisesRegex(ConflictError, "package bytes"):
            self.check()

    def test_log_tampering_rejected(self):
        self.log.write_bytes(b"modified log")
        with self.assertRaisesRegex(ConflictError, "validation log bytes"):
            self.check()

    def test_wrong_source_rejected(self):
        self.manifest["source_sha"] = "a" * 40
        with self.assertRaisesRegex(ConflictError, "source_sha"):
            self.check()

    def test_wrong_store_id_rejected(self):
        self.manifest["store_id"] = "9INVALID"
        with self.assertRaisesRegex(ConflictError, "store_id"):
            self.check()

    def test_claimed_approval_rejected(self):
        self.manifest["real_msix_pass"] = True
        with self.assertRaisesRegex(ConflictError, "real_msix_pass"):
            self.check()

    def test_extra_file_rejected(self):
        (self.root / "unexpected.txt").write_text("unexpected")
        with self.assertRaisesRegex(ConflictError, "exactly three"):
            self.check()

    def test_duplicate_json_key_rejected(self):
        self.manifest_path.write_text(
            json.dumps(self.manifest)[:-1] + ', "source_sha": "' + "f" * 40 + '"}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConflictError, "duplicate JSON key"):
            verify_handoff(self.root)

    def test_original_sdk_filename_traversal_rejected(self):
        self.manifest["original_sdk_filename"] = "../other.msixvc2"
        with self.assertRaisesRegex(ConflictError, "original SDK filename"):
            self.check()

    def test_boolean_size_rejected(self):
        self.manifest["package_size_bytes"] = True
        with self.assertRaisesRegex(ConflictError, "package size"):
            self.check()

    def test_unknown_manifest_field_rejected(self):
        self.manifest["store_certified"] = True
        with self.assertRaisesRegex(ConflictError, "schema unexpected"):
            self.check()

    def test_bad_version_rejected(self):
        self.manifest["package_version"] = "1.0.99999.0"
        with self.assertRaisesRegex(ConflictError, "package version"):
            self.check()


if __name__ == "__main__":
    unittest.main()
