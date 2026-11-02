"""Offline read-only exact-archive provenance tests; synthetic bytes only."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import gdk_exact_artifact_check as gate


def make_zip(exe: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("SignalSprint.exe", exe)
        archive.writestr("provenance.json", "{}")
        archive.writestr("provisioner-request.json", "{}")
    return output.getvalue()


class ExactArtifactTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.exe = b"MZ" + b"pinned-synthetic" * 20
        self.zip = make_zip(self.exe)
        self.file = self.root / "preserved.zip"
        self.file.write_bytes(self.zip)
        self.patches = [
            patch.object(gate, "ARTIFACT_SHA256", hashlib.sha256(self.zip).hexdigest()),
            patch.object(gate, "EXE_SHA256", hashlib.sha256(self.exe).hexdigest()),
            patch.object(gate, "inspect_pinned_artifact", lambda path: {
                "artifact_zip_sha256": hashlib.sha256(self.zip).hexdigest(),
                "executable_sha256": hashlib.sha256(self.exe).hexdigest()}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_exact_bytes_pass_check_only_not_cas(self):
        result = gate.check([self.file], [])
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_CHECK_ONLY")
        self.assertEqual(result["exact_copy_count"], 1)
        self.assertFalse(result["ready_for_cas"])
        self.assertTrue(result["candidates"][0]["exe_match"])

    def test_missing_copy_hold(self):
        result = gate.check([self.root / "missing.zip"], [])
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_HOLD")

    def test_repacked_same_exe_is_not_exact(self):
        with zipfile.ZipFile(self.file, "a") as archive:
            archive.comment = b"repacked"
        result = gate.check([self.file], [])
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertTrue(result["candidates"][0]["exe_match"])
        self.assertFalse(result["candidates"][0]["zip_match"])

    def test_modified_exe_has_independent_digest(self):
        self.file.write_bytes(make_zip(b"MZchanged"))
        result = gate.check([self.file], [])
        self.assertFalse(result["candidates"][0]["exe_match"])
        self.assertFalse(result["candidates"][0]["zip_match"])

    def test_symlink_candidate_rejected(self):
        alias = self.root / "alias.zip"
        alias.symlink_to(self.file)
        result = gate.check([alias], [])
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertEqual(result["candidates"][0]["reason"], "SYMLINK_PATH")

    def test_scan_nested_zip(self):
        nested = self.root / "one" / "two"
        nested.mkdir(parents=True)
        (nested / "copy.zip").write_bytes(self.zip)
        result = gate.check([], [self.root])
        self.assertEqual(result["exact_copy_count"], 2)

    def test_invalid_member_set_rejected(self):
        with zipfile.ZipFile(self.file, "a") as archive:
            archive.writestr("extra.dll", b"x")
        result = gate.check([self.file], [])
        self.assertEqual(result["candidates"][0]["reason"], "UNEXPECTED_ZIP_MEMBERS")

    def test_no_candidates_is_hold(self):
        self.assertEqual(gate.check([], [])["status"], "ARTIFACT_EXACT_BYTES_HOLD")


if __name__ == "__main__":
    unittest.main()
