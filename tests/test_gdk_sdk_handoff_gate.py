"""Synthetic integration contract tests; never run real CAS, SDK or Store."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_sdk_handoff_gate as gate
from gdk_msixvc2_preflight import MAX_FILE_BYTES


CAS = "a" * 40
BUILD = "b" * 40
TRUST = "c" * 64
VERSION = "1.0.1.0"
DISPLAY = "Signal Sprint"


class SdkHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.factory = root / "factory"
        self.staging = root / "staging"
        self.output = root / "output"
        for directory in (self.factory, self.staging, self.output):
            directory.mkdir()
        self.zip = root / "original.zip"
        self.factory_gate = root / "factory-gate.py"
        self.preflight = root / "preflight.json"
        self.dual = {
            "schema_version": 1,
            "status": "GDK_DUAL_GATE_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "request_id": gate.REQUEST_ID,
            "source_sha": gate.SOURCE_SHA,
            "cas_commit_sha": CAS,
            "factory_head_sha": BUILD,
            "factory_gate_sha256": TRUST,
            "provisioner_receipt_sha256": "d" * 64,
            "factory_receipt_sha256": "e" * 64,
            "package_version": None,
            "real_msixvc_built": False,
            "gdk_sdk_validated": False,
            "store_submitted": False,
            "windows_e2e_pass": False,
            "next_stage": "GDK_SDK_PREFLIGHT_PENDING",
        }
        hashes = {name: "f" * 64 for name in MAX_FILE_BYTES}
        hashes["SignalSprint.exe"] = gate.EXE_SHA
        self.plan = {
            "schema_version": 1,
            "status": "GDK_SDK_PACK_PLAN_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": gate.REQUEST_ID,
            "source_sha": gate.SOURCE_SHA,
            "cas_commit_sha": CAS,
            "factory_head_sha": BUILD,
            "package_version": VERSION,
            "reviewed_display_name": DISPLAY,
            "verified_receipt_sha256": "a" * 64,
            "staging_files_sha256": hashes,
            "sdk_command_argv_not_executed": [
                "makepkg.exe", "pack", "/msixvc2", "/d",
                str(self.staging.resolve()), "/pc", "/pd",
                str(self.output.resolve()), "/validationcritical"],
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
            "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
        }

    def run_gate(self, duals=None, plans=None):
        duals = duals or [deepcopy(self.dual), deepcopy(self.dual)]
        plans = plans or [deepcopy(self.plan), deepcopy(self.plan)]
        with patch.object(gate, "run_dual_gate", side_effect=duals) as d, \
             patch.object(gate, "make_pack_plan", side_effect=plans) as p:
            result = gate.create_sdk_handoff(
                self.factory, self.zip, CAS, BUILD, self.factory_gate, TRUST,
                self.staging, VERSION, DISPLAY, self.preflight, self.output)
            self.assertEqual(d.call_count, 2)
            self.assertEqual(p.call_count, 2)
            return result

    def test_check_only_success_has_two_independent_passes(self):
        result = self.run_gate()
        self.assertEqual(result["status"], "GDK_SDK_HANDOFF_CHECK_ONLY")
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertEqual(result["pinned_artifact_zip_sha256"], gate.ZIP_SHA)
        self.assertEqual(result["pinned_exe_sha256"], gate.EXE_SHA)
        self.assertEqual(result["package_version"], VERSION)
        self.assertEqual(result["dual_gate_receipt_sha256"], gate._sha(self.dual))
        self.assertEqual(result["sdk_pack_plan_sha256"], gate._sha(self.plan))
        for flag in ("gdk_sdk_validated", "real_msixvc_built",
                     "store_submitted", "windows_e2e_pass"):
            self.assertIs(result[flag], False)

    def test_wrong_source_in_dual_rejected(self):
        bad = deepcopy(self.dual)
        bad["source_sha"] = "0" * 40
        with self.assertRaisesRegex(gate.DualGateHold, "source_sha"):
            self.run_gate(duals=[bad, self.dual])

    def test_wrong_cas_in_plan_rejected(self):
        bad = deepcopy(self.plan)
        bad["cas_commit_sha"] = "0" * 40
        with self.assertRaisesRegex(gate.DualGateHold, "cas_commit_sha"):
            self.run_gate(plans=[bad, self.plan])

    def test_changed_dual_receipt_second_pass_rejected(self):
        bad = deepcopy(self.dual)
        bad["factory_receipt_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.DualGateHold, "changed between passes"):
            self.run_gate(duals=[self.dual, bad])

    def test_changed_staging_hash_second_pass_rejected(self):
        bad = deepcopy(self.plan)
        bad["staging_files_sha256"]["Logo.png"] = "0" * 64
        with self.assertRaisesRegex(gate.DualGateHold, "changed between passes"):
            self.run_gate(plans=[self.plan, bad])

    def test_fake_sdk_success_rejected(self):
        bad = deepcopy(self.plan)
        bad["gdk_sdk_validated"] = True
        with self.assertRaisesRegex(gate.DualGateHold, "gdk_sdk_validated"):
            self.run_gate(plans=[bad, self.plan])

    def test_wrong_package_version_rejected(self):
        bad = deepcopy(self.plan)
        bad["package_version"] = "9.9.9.0"
        with self.assertRaisesRegex(gate.DualGateHold, "package_version"):
            self.run_gate(plans=[bad, self.plan])

    def test_command_with_skip_validation_rejected(self):
        bad = deepcopy(self.plan)
        bad["sdk_command_argv_not_executed"].append("/skipvalidation")
        with self.assertRaisesRegex(gate.DualGateHold, "SDK command differs"):
            self.run_gate(plans=[bad, self.plan])

    def test_command_with_wrong_output_rejected(self):
        bad = deepcopy(self.plan)
        bad["sdk_command_argv_not_executed"][7] = "/tmp/other"
        with self.assertRaisesRegex(gate.DualGateHold, "SDK command differs"):
            self.run_gate(plans=[bad, self.plan])

    def test_fake_store_submission_in_dual_rejected(self):
        bad = deepcopy(self.dual)
        bad["store_submitted"] = True
        with self.assertRaisesRegex(gate.DualGateHold, "store_submitted"):
            self.run_gate(duals=[bad, self.dual])

    def test_wrong_trusted_factory_digest_rejected(self):
        bad = deepcopy(self.dual)
        bad["factory_gate_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.DualGateHold, "factory_gate_sha256"):
            self.run_gate(duals=[bad, self.dual])

    def test_invalid_preflight_digest_rejected(self):
        bad = deepcopy(self.plan)
        bad["verified_receipt_sha256"] = "not-a-sha"
        with self.assertRaisesRegex(gate.DualGateHold, "preflight digest"):
            self.run_gate(plans=[bad, self.plan])


if __name__ == "__main__":
    unittest.main()
