"""Synthetic-only recovery receipt tests: no Identity, CAS or GDK SDK actions."""
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import gdk_build_intake as intake
import gdk_exact_artifact_check as gate
import gdk_exact_bytes_recovery_receipt as recovery
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_JOB


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture(exe, provenance=None, request=None):
    provenance = provenance if provenance is not None else {
        **PINNED_SIGNAL_SPRINT_JOB, "executable": "SignalSprint.exe",
        "executable_sha256": sha(exe), "artifact_kind": "EXE_QA_UNSIGNED",
    }
    request = request if request is not None else {
        **PINNED_SIGNAL_SPRINT_JOB, "dry_run": True,
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("SignalSprint.exe", exe)
        z.writestr("provenance.json", json.dumps(provenance))
        z.writestr("provisioner-request.json", json.dumps(request))
    return out.getvalue()


class RecoveryReceiptTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.exe = b"MZ" + b"synthetic-original" * 30
        self.archive = fixture(self.exe)
        self.path = self.root / "original.zip"
        self.path.write_bytes(self.archive)

    def coherent_pins(self, archive=None, exe=None):
        archive = self.archive if archive is None else archive
        exe = self.exe if exe is None else exe
        stack = ExitStack()
        self.addCleanup(stack.close)
        for obj, name, value in [
            (recovery, "HANDOFF_ZIP_SHA256", sha(archive)),
            (recovery, "HANDOFF_EXE_SHA256", sha(exe)),
            (recovery, "ARTIFACT_SHA256", sha(archive)),
            (recovery, "EXE_SHA256", sha(exe)),
            (gate, "ARTIFACT_SHA256", sha(archive)),
            (gate, "EXE_SHA256", sha(exe)),
            (intake, "ARTIFACT_SHA256", sha(archive)),
            (intake, "EXE_SHA256", sha(exe)),
        ]:
            stack.enter_context(patch.object(obj, name, value))

    def test_real_handoff_and_repository_exe_pins_conflict_fail_closed(self):
        result = recovery.recovery_receipt([self.path], [])
        self.assertEqual(result["reason"], "EXPECTED_DIGEST_AUTHORITY_CONFLICT")
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertNotEqual(result["expected_exe_sha256_handoff"],
                            result["expected_exe_sha256_repository"])
        self.assertFalse(result["ready_for_cas"])

    def test_exact_synthetic_bytes_are_check_only_not_cas(self):
        self.coherent_pins()
        result = recovery.recovery_receipt([self.path], [])
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_RECOVERY_CHECK_ONLY")
        self.assertTrue(result["original_bytes_verified"])
        self.assertTrue(result["evidence"]["candidates"][0]["exe_matches_handoff"])
        self.assertFalse(result["ready_for_cas"])
        self.assertFalse(result["cas_return_pass"])
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["store_submitted"])
        self.assertFalse(result["receipt_authenticity_verified"])

    def test_missing_archive_hold(self):
        self.coherent_pins()
        result = recovery.recovery_receipt([self.root / "missing.zip"], [])
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertEqual(result["evidence"]["candidates"][0]["reason"],
                         "UNREADABLE_OR_INVALID_ARCHIVE")

    def test_no_candidates_hold(self):
        self.coherent_pins()
        result = recovery.recovery_receipt([], [])
        self.assertEqual(result["reason"], "ORIGINAL_ARTIFACT_NOT_FOUND")

    def test_repacked_zip_same_exe_hold(self):
        self.coherent_pins()
        with zipfile.ZipFile(self.path, "a") as z:
            z.comment = b"changed archive bytes"
        result = recovery.recovery_receipt([self.path], [])
        self.assertFalse(result["original_bytes_verified"])
        self.assertTrue(result["evidence"]["candidates"][0]["exe_matches_handoff"])
        self.assertFalse(result["evidence"]["candidates"][0]["zip_matches_handoff"])

    def test_changed_exe_hold_even_if_archive_rehashed(self):
        changed = b"MZ" + b"changed-exe"
        changed_zip = fixture(changed)
        self.path.write_bytes(changed_zip)
        self.coherent_pins(archive=changed_zip, exe=self.exe)
        result = recovery.recovery_receipt([self.path], [])
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertFalse(result["evidence"]["candidates"][0]["exe_matches_handoff"])

    def test_wrong_product_provenance_hold(self):
        wrong = {**PINNED_SIGNAL_SPRINT_JOB, "slug": "other-game",
                 "executable": "SignalSprint.exe",
                 "executable_sha256": sha(self.exe),
                 "artifact_kind": "EXE_QA_UNSIGNED"}
        altered = fixture(self.exe, provenance=wrong)
        self.path.write_bytes(altered)
        self.coherent_pins(archive=altered)
        result = recovery.recovery_receipt([self.path], [])
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertFalse(result["evidence"]["candidates"][0]["provenance_matches_repository"])

    def test_wrong_request_id_hold(self):
        wrong = {**PINNED_SIGNAL_SPRINT_JOB, "request_id": "game-other"}
        altered = fixture(self.exe, request={**wrong, "dry_run": True})
        self.path.write_bytes(altered)
        self.coherent_pins(archive=altered)
        self.assertFalse(recovery.recovery_receipt([self.path], [])["original_bytes_verified"])

    def test_symlink_hold(self):
        self.coherent_pins()
        link = self.root / "linked.zip"
        link.symlink_to(self.path)
        result = recovery.recovery_receipt([link], [])
        self.assertEqual(result["evidence"]["candidates"][0]["reason"], "SYMLINK_PATH")

    def test_incomplete_scan_hold(self):
        self.coherent_pins()
        with patch.object(gate, "MAX_CANDIDATES", 0):
            result = recovery.recovery_receipt([], [self.root])
        self.assertEqual(result["reason"], "INCOMPLETE_CANDIDATE_SEARCH")
        self.assertFalse(result["original_bytes_verified"])


if __name__ == "__main__":
    unittest.main()
