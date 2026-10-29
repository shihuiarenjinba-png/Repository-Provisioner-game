"""Synthetic trust-anchor tests; no real CAS, SDK, package or Store operation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_sdk_trusted_intake as gate
from gdk_dual_gate import EXE_SHA, ZIP_SHA


CAS = "a" * 40
BUILD = "b" * 40
VERSION = "1.0.1.0"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


class TrustedIntakeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.handoff_path = root / "handoff.json"
        self.plan_path = root / "plan.json"
        self.evidence_path = root / "sdk.json"
        self.package_dir = root / "package"
        self.package_dir.mkdir()
        self.log = root / "validation.log"
        self.plan = {
            "schema_version": 1,
            "status": "GDK_SDK_PACK_PLAN_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": gate.PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": gate.PINNED_SIGNAL_SPRINT_JOB["source_sha"],
            "cas_commit_sha": CAS,
            "factory_head_sha": BUILD,
            "package_version": VERSION,
            "reviewed_display_name": "Signal Sprint",
            "staging_files_sha256": {"SignalSprint.exe": EXE_SHA},
            "sdk_command_argv_not_executed": [
                "makepkg.exe", "pack", "/msixvc2", "/d", "stage",
                "/pc", "/pd", "out", "/validationcritical"],
            "verified_receipt_sha256": "c" * 64,
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
        }
        self.handoff = {
            "schema_version": 1,
            "status": "GDK_SDK_HANDOFF_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "request_id": self.plan["request_id"],
            "source_sha": self.plan["source_sha"],
            "cas_commit_sha": CAS,
            "factory_head_sha": BUILD,
            "pinned_artifact_zip_sha256": ZIP_SHA,
            "pinned_exe_sha256": EXE_SHA,
            "trusted_factory_gate_sha256": "d" * 64,
            "dual_gate_receipt_sha256": "e" * 64,
            "sdk_pack_plan_sha256": hashlib.sha256(canonical(self.plan)).hexdigest(),
            "verified_preflight_receipt_sha256": "c" * 64,
            "staging_files_sha256": self.plan["staging_files_sha256"],
            "package_version": VERSION,
            "reviewed_display_name": "Signal Sprint",
            "sdk_command_argv_not_executed": self.plan["sdk_command_argv_not_executed"],
            "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
            "windows_e2e_pass": False,
        }
        self.receipt = {
            "status": "GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS",
            "request_id": self.plan["request_id"],
            "source_sha": self.plan["source_sha"],
            "cas_commit_sha": CAS,
            "factory_head_sha": BUILD,
            "package_version": VERSION,
            "real_msix_pass": False,
            "e2e_pass": False,
            "store_submitted": False,
            "gdk_sdk_validation_independently_verified": False,
        }

    def run_gate(self, plan=None, handoff=None, receipt=None, trusted=None):
        self.plan_path.write_bytes(canonical(self.plan if plan is None else plan))
        self.handoff_path.write_bytes(canonical(self.handoff if handoff is None else handoff))
        expected = hashlib.sha256(self.handoff_path.read_bytes()).hexdigest()
        if trusted is not None:
            expected = trusted
        with patch.object(gate, "intake", return_value=self.receipt if receipt is None else receipt):
            return gate.trusted_intake(self.handoff_path, expected,
                                       self.plan_path, self.evidence_path,
                                       self.package_dir, self.log)

    def test_valid_anchor_remains_check_only(self):
        result = self.run_gate()
        self.assertTrue(result["prebuild_trust_chain_verified"])
        self.assertEqual(result["status"], "GDK_TRUSTED_PREBUILD_TO_PACKAGE_BYTES_CHECK_PASS")
        for key in ("gdk_sdk_validation_independently_verified",
                    "real_msix_pass", "e2e_pass", "store_submitted"):
            self.assertIs(result[key], False)

    def test_missing_external_anchor_rejected(self):
        with self.assertRaisesRegex(gate.HoldError, "independent trusted"):
            self.run_gate(trusted="")

    def test_changed_handoff_with_old_trusted_sha_rejected(self):
        old = hashlib.sha256(canonical(self.handoff)).hexdigest()
        altered = deepcopy(self.handoff)
        altered["package_version"] = "9.0.0.0"
        with self.assertRaisesRegex(gate.ConflictError, "digest mismatch"):
            self.run_gate(handoff=altered, trusted=old)

    def test_plan_replacement_rejected_even_if_receipt_claims_success(self):
        altered = deepcopy(self.plan)
        altered["package_version"] = "9.0.0.0"
        with self.assertRaisesRegex(gate.ConflictError, "not bound"):
            self.run_gate(plan=altered)

    def test_false_sdk_validation_rejected(self):
        altered = deepcopy(self.handoff)
        altered["gdk_sdk_validated"] = True
        with self.assertRaisesRegex(gate.ConflictError, "gdk_sdk_validated"):
            self.run_gate(handoff=altered)

    def test_fake_source_rejected(self):
        altered = deepcopy(self.handoff)
        altered["source_sha"] = "0" * 40
        with self.assertRaisesRegex(gate.ConflictError, "source_sha"):
            self.run_gate(handoff=altered)

    def test_wrong_original_exe_rejected(self):
        altered = deepcopy(self.handoff)
        altered["pinned_exe_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.ConflictError, "pinned_exe_sha256"):
            self.run_gate(handoff=altered)

    def test_fake_independent_sdk_pass_rejected(self):
        altered = deepcopy(self.receipt)
        altered["gdk_sdk_validation_independently_verified"] = True
        with self.assertRaisesRegex(gate.ConflictError, "independently_verified"):
            self.run_gate(receipt=altered)

    def test_extra_handoff_field_rejected(self):
        altered = deepcopy(self.handoff)
        altered["store_certified"] = True
        with self.assertRaisesRegex(gate.ConflictError, "schema unexpected"):
            self.run_gate(handoff=altered)

    def test_symlink_handoff_rejected(self):
        self.plan_path.write_bytes(canonical(self.plan))
        actual = self.handoff_path.parent / "actual.json"
        actual.write_bytes(canonical(self.handoff))
        self.handoff_path.symlink_to(actual)
        with patch.object(gate, "intake", return_value=self.receipt):
            with self.assertRaises(gate.ConflictError):
                gate.trusted_intake(self.handoff_path,
                                    hashlib.sha256(actual.read_bytes()).hexdigest(),
                                    self.plan_path, self.evidence_path,
                                    self.package_dir, self.log)

    def test_changed_plan_during_intake_rejected(self):
        def mutate(*args):
            self.plan_path.write_bytes(canonical({"modified": True}))
            return self.receipt
        self.plan_path.write_bytes(canonical(self.plan))
        self.handoff_path.write_bytes(canonical(self.handoff))
        with patch.object(gate, "intake", side_effect=mutate):
            with self.assertRaisesRegex(gate.ConflictError, "changed during intake"):
                gate.trusted_intake(self.handoff_path,
                                    hashlib.sha256(self.handoff_path.read_bytes()).hexdigest(),
                                    self.plan_path, self.evidence_path,
                                    self.package_dir, self.log)


if __name__ == "__main__":
    unittest.main()
