"""Synthetic contract tests: never run CAS, SDK, Store, or mutate source refs."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import gdk_dual_gate as dual

CAS = "a" * 40
BUILD = "b" * 40
TRUST = "c" * 64
PINNED = {"artifact_zip_sha256": dual.ZIP_SHA,
          "executable_sha256": dual.EXE_SHA,
          "executable_bytes": 12345, "executable": "SignalSprint.exe"}


def receipt(stage):
    base = {"schema_version": 1, "request_id": dual.REQUEST_ID,
            "source_sha": dual.SOURCE_SHA, "cas_commit_sha": CAS,
            "factory_head_sha": BUILD, "package_version": None,
            "real_msixvc_built": False, "store_submitted": False,
            "packaging_family": "GDK", "pinned_exe": dict(PINNED),
            "source_repository": "shihuiarenjinba-png/AI-Game-Factory"}
    if stage == "provisioner":
        base.update(status="GDK_BUILD_INPUT_CHECK_ONLY",
                    next_stage="BUILD_GDK_MSIXVC_FROM_PINNED_EXE",
                    package_format="MSIXVC_OR_MSIXVC2",
                    source_branch="codex/game-signal-sprint-undo-20261027")
    else:
        base.update(status="GDK_FACTORY_POST_CAS_CHECK_ONLY",
                    next_stage="GDK_SDK_BUILD_PENDING",
                    windows_e2e_pass=False)
    return base


class DualGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.checkout = root / "checkout"
        self.checkout.mkdir()
        self.zip = root / "pinned.zip"
        self.zip.write_bytes(b"fixture")
        self.gate = root / "reviewed-factory-gate.py"
        self.gate.write_text("pass\n")

    def run_gate(self, first=None, second=None, recheck=None):
        first = receipt("provisioner") if first is None else first
        second = receipt("factory") if second is None else second
        recheck = first if recheck is None else recheck
        with patch.object(dual, "digest", side_effect=lambda path:
                          TRUST if path == self.gate else dual.ZIP_SHA), \
             patch.object(dual, "invoke", side_effect=[first, second, recheck]):
            return dual.run_dual_gate(self.checkout, self.zip, CAS, BUILD,
                                      self.gate, TRUST)

    def test_success_is_check_only_not_real_package(self):
        result = self.run_gate()
        self.assertEqual(result["status"], "GDK_DUAL_GATE_CHECK_ONLY")
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["gdk_sdk_validated"])
        self.assertFalse(result["windows_e2e_pass"])
        self.assertIsNone(result["package_version"])

    def test_wrong_source_rejected(self):
        first = receipt("provisioner")
        first["source_sha"] = "d" * 40
        with self.assertRaisesRegex(dual.DualGateHold, "source_sha"):
            self.run_gate(first=first)

    def test_forged_provisioner_status_rejected(self):
        first = receipt("provisioner")
        first["status"] = "REAL_MSIX_PASS"
        with self.assertRaisesRegex(dual.DualGateHold, "status"):
            self.run_gate(first=first)

    def test_forged_factory_e2e_rejected(self):
        second = receipt("factory")
        second["windows_e2e_pass"] = True
        with self.assertRaisesRegex(dual.DualGateHold, "windows_e2e_pass"):
            self.run_gate(second=second)

    def test_mismatched_executable_rejected(self):
        second = receipt("factory")
        second["pinned_exe"]["executable_sha256"] = "f" * 64
        with self.assertRaisesRegex(dual.DualGateHold, "pinned EXE"):
            self.run_gate(second=second)

    def test_intermediate_mutation_detected(self):
        third = receipt("provisioner")
        third["factory_head_sha"] = "d" * 40
        with self.assertRaisesRegex(dual.DualGateHold, "changed during"):
            self.run_gate(recheck=third)

    def test_missing_trust_anchor_rejected(self):
        with self.assertRaisesRegex(dual.DualGateHold, "digest missing"):
            dual.run_dual_gate(self.checkout, self.zip, CAS, BUILD,
                               self.gate, "")

    def test_wrong_factory_gate_digest_rejected(self):
        with patch.object(dual, "digest", return_value="f" * 64):
            with self.assertRaisesRegex(dual.DualGateHold, "reviewed SHA-256"):
                dual.run_dual_gate(self.checkout, self.zip, CAS, BUILD,
                                   self.gate, TRUST)

    def test_duplicate_receipt_key_rejected(self):
        with self.assertRaisesRegex(dual.DualGateHold, "duplicate"):
            dual.parse_receipt(b'{"status":"PASS","status":"HOLD"}', "fixture")

    def test_nonzero_gate_exit_rejected(self):
        fake = subprocess.CompletedProcess([], 2, b'{"status":"HOLD"}', b'')
        with patch.object(dual.subprocess, "run", return_value=fake):
            with self.assertRaisesRegex(dual.DualGateHold, "rejected"):
                dual.invoke(self.gate, [], "factory")

    def test_symlinked_factory_gate_rejected(self):
        alias = Path(self.tmp.name) / "gate-link.py"
        try:
            alias.symlink_to(self.gate)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(dual.DualGateHold, "script unavailable"):
            dual.run_dual_gate(self.checkout, self.zip, CAS, BUILD,
                               alias, TRUST)


if __name__ == "__main__":
    unittest.main()
