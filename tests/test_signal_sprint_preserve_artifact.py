"""Offline, no-GitHub tests of exact-byte original artifact preservation."""
import errno
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import signal_sprint_preserve_artifact as preservation
from package_identity_provisioner import ConflictError, HoldError


class PreservationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.source = root / "original.zip"
        self.source.write_bytes(b"exact original zip fixture")
        self.destination = root / "durable"
        self.destination.mkdir()
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        digest = patch.object(preservation, "ARTIFACT_SHA256", self.digest)
        inspect = patch.object(preservation, "inspect_pinned_artifact")
        digest.start()
        inspect.start()
        self.addCleanup(digest.stop)
        self.addCleanup(inspect.stop)

    def test_preserves_once_then_idempotent(self):
        first = preservation.preserve(self.source, self.destination)
        self.assertEqual(first["status"], "PRESERVED_VERIFIED")
        self.assertEqual(first["archive_sha256"], self.digest)
        self.assertFalse(first["real_msix_pass"])
        second = preservation.preserve(self.source, self.destination)
        self.assertEqual(second["status"], "EXISTING_VERIFIED")
        self.assertEqual((self.destination / preservation.ARCHIVE_NAME).read_bytes(),
                         self.source.read_bytes())

    def test_filesystem_without_hardlinks_uses_exclusive_copy(self):
        with patch.object(preservation.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "no hardlinks")):
            result = preservation.preserve(self.source, self.destination)
        self.assertEqual(result["status"], "PRESERVED_VERIFIED")
        self.assertEqual((self.destination / preservation.ARCHIVE_NAME).read_bytes(),
                         self.source.read_bytes())

    def test_different_existing_file_is_never_overwritten(self):
        target = self.destination / preservation.ARCHIVE_NAME
        target.write_bytes(b"other artifact")
        with self.assertRaisesRegex(ConflictError, "refusing overwrite"):
            preservation.preserve(self.source, self.destination)
        self.assertEqual(target.read_bytes(), b"other artifact")

    def test_changed_source_is_rejected(self):
        self.source.write_bytes(b"modified")
        with self.assertRaisesRegex(ConflictError, "changed after provenance"):
            preservation.preserve(self.source, self.destination)

    def test_linked_destination_rejected(self):
        linked = self.destination.parent / "linked"
        try:
            linked.symlink_to(self.destination, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Windows runner cannot create symlinks")
        with self.assertRaisesRegex(HoldError, "not be linked"):
            preservation.preserve(self.source, linked)

    def test_symlinked_destination_ancestor_is_rejected(self):
        linked_parent = self.destination.parent / "linked-parent"
        try:
            linked_parent.symlink_to(self.destination.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Windows runner cannot create symlinks")
        redirected_destination = linked_parent / self.destination.name
        self.assertFalse(redirected_destination.is_symlink())
        with self.assertRaisesRegex(ConflictError, "symlink or junction"):
            preservation.preserve(self.source, redirected_destination)
        self.assertFalse((self.destination / preservation.ARCHIVE_NAME).exists())

    def test_symlinked_source_ancestor_is_rejected(self):
        linked_parent = self.destination.parent / "linked-source"
        try:
            linked_parent.symlink_to(self.source.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Windows runner cannot create symlinks")
        redirected_source = linked_parent / self.source.name
        self.assertFalse(redirected_source.is_symlink())
        with self.assertRaisesRegex(ConflictError, "symlink or junction"):
            preservation.preserve(redirected_source, self.destination)
        self.assertFalse((self.destination / preservation.ARCHIVE_NAME).exists())

    def test_target_cannot_be_original(self):
        self.source = self.destination / preservation.ARCHIVE_NAME
        self.source.write_bytes(b"exact original zip fixture")
        with self.assertRaisesRegex(ConflictError, "must be distinct"):
            preservation.preserve(self.source, self.destination)


if __name__ == "__main__":
    unittest.main()
