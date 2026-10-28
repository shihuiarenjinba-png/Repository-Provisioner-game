"""No-SDK tests for second-pass Signal Sprint GDK MSIXVC2 staging checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_msixvc2_recheck as gate
from package_identity_provisioner import ConflictError


class GdkMsixvc2RecheckTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.receipt = self.root / "receipt.json"
        self.snapshot = {
            "schema_version": 1,
            "status": "GDK_MSIXVC2_STAGING_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": "game-signal-sprint-test",
            "source_sha": "a" * 40,
            "cas_commit_sha": "b" * 40,
            "factory_head_sha": "c" * 40,
            "staging_files_sha256": {"SignalSprint.exe": "d" * 64},
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
        }
        self.write_receipt()
        self.fresh = dict(self.snapshot)
        self.branch_evidence = {
            "status": "GDK_BUILD_BRANCH_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": self.snapshot["request_id"],
            "source_sha": self.snapshot["source_sha"],
            "cas_commit_sha": self.snapshot["cas_commit_sha"],
            "factory_head_sha": self.snapshot["factory_head_sha"],
            "product_history_gate": "NO_PRODUCT_PATH_CHANGES_SINCE_CAS",
            "build_branch": "codex/game-signal-sprint-gdk-build-test",
            "approved_identity_blob_sha": "f" * 40,
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
        }
        branch_patch = patch.object(gate, "verify_build_branch",
                                    side_effect=lambda *args: self.branch_evidence)
        branch_patch.start()
        self.addCleanup(branch_patch.stop)
        self.patch = patch.object(gate, "create_preflight", side_effect=lambda *args: self.fresh)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write_receipt(self):
        self.receipt.write_text(json.dumps(self.snapshot), encoding="utf-8")

    def run_check(self):
        return gate.recheck(self.root, self.root / "artifact.zip", "b" * 40,
                            "c" * 40, self.root, "1.0.1.0",
                            "Signal Sprint", self.receipt)

    def test_exact_receipt_passes_without_claiming_package(self):
        result = self.run_check()
        self.assertEqual(result["status"], "GDK_MSIXVC2_RECHECK_PASS")
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertEqual(result["staging_files_sha256"], self.snapshot["staging_files_sha256"])
        self.assertEqual(result["verified_receipt_sha256"], hashlib.sha256(self.receipt.read_bytes()).hexdigest())
        self.assertEqual(result["build_branch"], self.branch_evidence["build_branch"])
        self.assertEqual(result["product_history_gate"], "NO_PRODUCT_PATH_CHANGES_SINCE_CAS")
        self.assertEqual(result["approved_identity_blob_sha"], "f" * 40)
        self.assertFalse(result["gdk_sdk_validated"])
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["store_submitted"])

    def test_changed_executable_hash_rejected(self):
        self.fresh["staging_files_sha256"] = {"SignalSprint.exe": "e" * 64}
        with self.assertRaisesRegex(ConflictError, "differs"):
            self.run_check()

    def test_changed_source_sha_rejected(self):
        self.fresh["source_sha"] = "f" * 40
        with self.assertRaisesRegex(ConflictError, "differs"):
            self.run_check()

    def test_changed_cas_sha_rejected(self):
        self.fresh["cas_commit_sha"] = "f" * 40
        with self.assertRaisesRegex(ConflictError, "differs"):
            self.run_check()

    def test_extra_receipt_field_rejected(self):
        self.snapshot["unexpected"] = "ignore me"
        self.write_receipt()
        with self.assertRaisesRegex(ConflictError, "differs"):
            self.run_check()

    def test_success_claim_rejected(self):
        self.snapshot["real_msixvc_built"] = True
        self.write_receipt()
        with self.assertRaisesRegex(ConflictError, "differs"):
            self.run_check()

    def test_wrong_json_type_rejected(self):
        self.snapshot["schema_version"] = True
        self.write_receipt()
        with self.assertRaisesRegex(ConflictError, "differs"):
            self.run_check()

    def test_duplicate_keys_rejected(self):
        self.receipt.write_text('{"status":"ok","status":"changed"}', encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.run_check()

    def test_invalid_json_rejected(self):
        self.receipt.write_text("{", encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.run_check()

    def test_symlink_receipt_rejected(self):
        link = self.root / "linked.json"
        link.symlink_to(self.receipt)
        with self.assertRaisesRegex(ConflictError, "regular"):
            gate.recheck(self.root, self.root / "artifact.zip", "b" * 40,
                         "c" * 40, self.root, "1.0.1.0", "Signal Sprint", link)

    def test_oversize_receipt_rejected(self):
        self.receipt.write_bytes(b"x" * (gate.MAX_RECEIPT_BYTES + 1))
        with self.assertRaisesRegex(ConflictError, "size"):
            self.run_check()

    def test_missing_receipt_rejected(self):
        self.receipt.unlink()
        with self.assertRaises(ConflictError):
            self.run_check()

    def test_fresh_result_claiming_sdk_success_rejected(self):
        self.fresh["gdk_sdk_validated"] = True
        self.snapshot["gdk_sdk_validated"] = True
        self.write_receipt()
        with self.assertRaisesRegex(ConflictError, "downstream"):
            self.run_check()

    def test_receipt_recheck_does_not_mutate_file(self):
        before = self.receipt.read_bytes()
        self.run_check()
        self.assertEqual(before, self.receipt.read_bytes())


    def test_unsafe_branch_history_rejected_even_with_matching_receipt(self):
        self.branch_evidence["product_history_gate"] = "UNVERIFIED"
        with self.assertRaisesRegex(ConflictError, "branch evidence mismatch"):
            self.run_check()

    def test_wrong_build_sha_from_branch_gate_rejected(self):
        self.branch_evidence["factory_head_sha"] = "e" * 40
        with self.assertRaisesRegex(ConflictError, "branch evidence mismatch"):
            self.run_check()

    def test_wrong_identity_blob_format_rejected(self):
        self.branch_evidence["approved_identity_blob_sha"] = "invalid"
        with self.assertRaisesRegex(ConflictError, "Identity blob invalid"):
            self.run_check()

    def test_wrong_branch_name_rejected(self):
        self.branch_evidence["build_branch"] = "codex/game-signal-sprint-undo-20261027"
        with self.assertRaisesRegex(ConflictError, "branch name"):
            self.run_check()

    def test_fake_sdk_success_in_branch_gate_rejected(self):
        self.branch_evidence["gdk_sdk_validated"] = True
        with self.assertRaisesRegex(ConflictError, "branch evidence mismatch"):
            self.run_check()

    def test_branch_gate_failure_is_not_bypassed(self):
        with patch.object(gate, "verify_build_branch", side_effect=ConflictError("dirty checkout")):
            with self.assertRaisesRegex(ConflictError, "dirty checkout"):
                self.run_check()


if __name__ == "__main__":
    unittest.main()
