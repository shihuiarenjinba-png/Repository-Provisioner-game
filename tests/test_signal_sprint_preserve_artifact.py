"""Offline, no-GitHub tests of exact-byte original artifact preservation."""
import errno
import hashlib
import json
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

    def test_manifest_is_portable_strict_json_and_idempotent(self):
        first = preservation.preserve(self.source, self.destination)
        path = self.destination / preservation.MANIFEST_NAME
        raw = path.read_bytes()
        evidence = json.loads(raw)
        self.assertEqual(evidence["archive_sha256"], self.digest)
        self.assertEqual(evidence["archive_size_bytes"], len(self.source.read_bytes()))
        self.assertEqual(evidence["immutable_source_sha"],
                         preservation.PINNED_SIGNAL_SPRINT_JOB["source_sha"])
        self.assertEqual(evidence["signature_status"], "QA_UNSIGNED")
        self.assertFalse(evidence["cas_return_pass"])
        self.assertFalse(evidence["real_msix_pass"])
        self.assertFalse(evidence["e2e_pass"])
        self.assertFalse(evidence["store_submitted"])
        self.assertEqual(first["integrity_manifest"], str(path))
        self.assertEqual(first["integrity_manifest_sha256"], hashlib.sha256(raw).hexdigest())
        second = preservation.preserve(self.source, self.destination)
        self.assertEqual(second["status"], "EXISTING_VERIFIED")
        self.assertEqual(path.read_bytes(), raw)

    def test_missing_manifest_can_be_restored_without_rewriting_zip(self):
        preservation.preserve(self.source, self.destination)
        archive = self.destination / preservation.ARCHIVE_NAME
        before = archive.stat()
        (self.destination / preservation.MANIFEST_NAME).unlink()
        result = preservation.preserve(self.source, self.destination)
        self.assertEqual(result["status"], "EXISTING_VERIFIED")
        self.assertTrue((self.destination / preservation.MANIFEST_NAME).is_file())
        self.assertEqual(archive.stat().st_mtime_ns, before.st_mtime_ns)

    def test_conflicting_manifest_rejected_without_touching_zip(self):
        preservation.preserve(self.source, self.destination)
        archive = self.destination / preservation.ARCHIVE_NAME
        original = archive.read_bytes()
        manifest = self.destination / preservation.MANIFEST_NAME
        manifest.write_text('{"archive_sha256":"different"}', encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "manifest conflicts"):
            preservation.preserve(self.source, self.destination)
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(manifest.read_text(encoding="utf-8"),
                         '{"archive_sha256":"different"}')

    def test_linked_manifest_is_rejected(self):
        preservation.preserve(self.source, self.destination)
        manifest = self.destination / preservation.MANIFEST_NAME
        manifest.unlink()
        external = self.destination.parent / "other-manifest.json"
        external.write_text("not trusted", encoding="utf-8")
        try:
            manifest.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("Windows runner cannot create symlinks")
        with self.assertRaisesRegex(ConflictError, "symlink or junction"):
            preservation.preserve(self.source, self.destination)
        self.assertEqual(external.read_text(encoding="utf-8"), "not trusted")

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
        with self.assertRaisesRegex(ConflictError, "symlink or junction"):
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
