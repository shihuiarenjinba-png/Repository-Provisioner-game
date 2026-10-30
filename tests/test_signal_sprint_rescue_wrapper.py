"""Offline tests: rescued wrapper cannot substitute different EXE/ZIP bytes."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

import signal_sprint_rescue_wrapper as rescue
from package_identity_provisioner import ConflictError


def archive(files):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as output:
        for name, value in files.items():
            output.writestr(name, value)
    return buffer.getvalue()


class RescueWrapperTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.dest = root / "backup"
        self.dest.mkdir()
        self.wrapper = root / "rescue.zip"
        self.members = {name: name.encode() for name in rescue.DIRECT}
        inner = {Path(name).name: value for name, value in self.members.items()}
        self.original = archive(inner)
        self.digest = hashlib.sha256(self.original).hexdigest()
        patches = (
            patch.object(rescue, "ARTIFACT_SHA256", self.digest),
            patch("signal_sprint_preserve_artifact.ARTIFACT_SHA256", self.digest),
            patch("signal_sprint_preserve_artifact.inspect_pinned_artifact"),
            patch.object(rescue, "inspect_pinned_artifact"),
            patch.object(rescue, "DIRECT", {
                k: hashlib.sha256(v).hexdigest() for k, v in self.members.items()}),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.write_wrapper()

    def write_wrapper(self, extra=None, original=None, direct=None):
        files = {rescue.NESTED: self.original if original is None else original}
        files.update(self.members if direct is None else direct)
        if extra:
            files.update(extra)
        self.wrapper.write_bytes(archive(files))

    def test_exact_nested_archive_preserved_and_idempotent(self):
        first = rescue.restore(self.wrapper, self.dest)
        self.assertEqual(first["status"], "PRESERVED_VERIFIED")
        self.assertEqual(first["archive_sha256"], self.digest)
        self.assertEqual((self.dest / rescue.ARCHIVE_NAME).read_bytes(), self.original)
        self.assertEqual(rescue.restore(self.wrapper, self.dest)["status"], "EXISTING_VERIFIED")

    def test_repacked_inner_zip_is_rejected_even_if_members_match(self):
        alternative = archive({Path(k).name: v for k, v in reversed(list(self.members.items()))})
        self.assertNotEqual(alternative, self.original)
        self.write_wrapper(original=alternative)
        with self.assertRaisesRegex(ConflictError, "nested original ZIP"):
            rescue.restore(self.wrapper, self.dest)

    def test_changed_direct_member_is_rejected(self):
        changed = dict(self.members)
        changed[next(iter(changed))] = b"replacement"
        self.write_wrapper(direct=changed)
        with self.assertRaisesRegex(ConflictError, "Rescued member differs"):
            rescue.restore(self.wrapper, self.dest)

    def test_extra_entry_and_path_traversal_are_rejected(self):
        for name in ("other.bin", "../escape", "signal-sprint-original/other.exe"):
            with self.subTest(name=name):
                self.write_wrapper(extra={name: b"unexpected"})
                with self.assertRaisesRegex(ConflictError, "unexpected entries"):
                    rescue.restore(self.wrapper, self.dest)

    def test_conflicting_existing_target_not_overwritten(self):
        target = self.dest / rescue.ARCHIVE_NAME
        target.write_bytes(b"different")
        with self.assertRaises(ConflictError):
            rescue.restore(self.wrapper, self.dest)
        self.assertEqual(target.read_bytes(), b"different")

    def test_linked_wrapper_ancestor_is_rejected(self):
        alias = self.wrapper.parent / "alias"
        try:
            alias.symlink_to(self.wrapper.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ConflictError, "symlink or junction"):
            rescue.restore(alias / self.wrapper.name, self.dest)

    def test_duplicate_entry_rejected(self):
        buf = io.BytesIO()
        with ZipFile(buf, "w", ZIP_DEFLATED) as out:
            for name, value in {rescue.NESTED: self.original, **self.members}.items():
                out.writestr(name, value)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                out.writestr(rescue.NESTED, self.original)
        self.wrapper.write_bytes(buf.getvalue())
        with self.assertRaisesRegex(ConflictError, "duplicate"):
            rescue.restore(self.wrapper, self.dest)


if __name__ == "__main__":
    unittest.main()
