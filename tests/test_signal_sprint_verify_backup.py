"""Offline tests: verification cannot mutate or silently repair the backup."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import signal_sprint_preserve_artifact as preservation
import signal_sprint_verify_backup as verifier
from package_identity_provisioner import ConflictError, HoldError


class VerifyBackupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.original = self.root / "source.zip"
        self.original.write_bytes(b"pinned zip fixture")
        self.backup = self.root / "owner-backup"
        self.backup.mkdir()
        digest = hashlib.sha256(self.original.read_bytes()).hexdigest()
        mock_sha = patch.object(preservation, "ARTIFACT_SHA256", digest)
        mock_inspect = patch.object(preservation, "inspect_pinned_artifact")
        mock_sha.start()
        mock_inspect.start()
        self.addCleanup(mock_sha.stop)
        self.addCleanup(mock_inspect.stop)
        preservation.preserve(self.original, self.backup)
        self.archive = self.backup / preservation.ARCHIVE_NAME
        self.manifest = self.backup / preservation.MANIFEST_NAME

    def test_valid_backup_without_original_and_no_mutation(self):
        self.original.unlink()
        before = (self.archive.read_bytes(), self.manifest.read_bytes(),
                  self.archive.stat().st_mtime_ns, self.manifest.stat().st_mtime_ns)
        result = verifier.verify_backup(self.backup)
        self.assertEqual(result["status"], "SIGNAL_SPRINT_BACKUP_READ_ONLY_VERIFIED")
        self.assertFalse(result["real_msix_pass"])
        self.assertEqual(before, (self.archive.read_bytes(), self.manifest.read_bytes(),
                                  self.archive.stat().st_mtime_ns, self.manifest.stat().st_mtime_ns))

    def test_missing_manifest_fails_without_repair(self):
        self.manifest.unlink()
        with self.assertRaises(HoldError):
            verifier.verify_backup(self.backup)
        self.assertFalse(self.manifest.exists())

    def test_modified_manifest_fails_without_repair(self):
        self.manifest.write_bytes(self.manifest.read_bytes().replace(b"QA_UNSIGNED", b"SIGNED"))
        with self.assertRaisesRegex(ConflictError, "manifest differs"):
            verifier.verify_backup(self.backup)

    def test_modified_archive_fails_without_repair(self):
        self.archive.write_bytes(b"changed")
        with self.assertRaisesRegex(ConflictError, "differs from pinned"):
            verifier.verify_backup(self.backup)

    def test_linked_parent_rejected(self):
        linked = self.root / "redirect"
        try:
            linked.symlink_to(self.backup, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ConflictError, "symlink or junction"):
            verifier.verify_backup(linked)

    def test_linked_manifest_rejected(self):
        external = self.root / "external.json"
        external.write_bytes(self.manifest.read_bytes())
        self.manifest.unlink()
        try:
            self.manifest.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ConflictError, "symlink or junction"):
            verifier.verify_backup(self.backup)


if __name__ == "__main__":
    unittest.main()
