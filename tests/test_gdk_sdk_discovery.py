"""Offline GDK executable discovery tests. Never execute an SDK."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gdk_sdk_discovery import discover_makepkg
from package_identity_provisioner import ConflictError, HoldError


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.env = mock.patch.dict(os.environ, {}, clear=True)
        self.env.start()
        # Do not discover a real SDK installed on the CI host during unit tests.
        os.environ["ProgramFiles(x86)"] = str(self.root / "empty-program-files")
        self.addCleanup(self.env.stop)
        self.os_patch = mock.patch("gdk_sdk_discovery.platform.system", return_value="Windows")
        self.os_patch.start()
        self.addCleanup(self.os_patch.stop)

    def tool(self, root, bin_subdir=True):
        path = root / "bin" / "makepkg.exe" if bin_subdir else root / "makepkg.exe"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake GDK executable: do not run")
        return path

    def test_gamedk_environment_root(self):
        path = self.tool(self.root / "GDK")
        os.environ["GameDK"] = str(path.parent.parent)
        self.assertEqual(discover_makepkg(), path.resolve())

    def test_gamedk_core_latest_environment_root(self):
        path = self.tool(self.root / "Core")
        os.environ["GameDKCoreLatest"] = str(path.parent.parent)
        self.assertEqual(discover_makepkg(), path.resolve())

    def test_gdk_bin_environment_root(self):
        path = self.tool(self.root / "tools", bin_subdir=False)
        os.environ["GDK_BIN"] = str(path.parent)
        self.assertEqual(discover_makepkg(), path.resolve())

    def test_default_program_files_install(self):
        path = self.tool(self.root / "Program Files (x86)" / "Microsoft GDK")
        os.environ["ProgramFiles(x86)"] = str(self.root / "Program Files (x86)")
        self.assertEqual(discover_makepkg(), path.resolve())

    def test_multiple_distinct_candidates_fail_closed(self):
        first = self.tool(self.root / "one")
        second = self.tool(self.root / "two")
        os.environ["GameDK"] = str(first.parent.parent)
        os.environ["GameDKCoreLatest"] = str(second.parent.parent)
        with self.assertRaisesRegex(HoldError, "multiple"):
            discover_makepkg()
        self.assertEqual(discover_makepkg(second), second.resolve())

    def test_duplicate_candidate_is_not_ambiguous(self):
        path = self.tool(self.root / "one")
        os.environ["GameDK"] = str(path.parent.parent)
        os.environ["GDK_BIN"] = str(path.parent)
        self.assertEqual(discover_makepkg(), path.resolve())

    def test_symlink_candidate_rejected(self):
        path = self.tool(self.root / "one")
        linked = self.root / "link.exe"
        try:
            linked.symlink_to(path)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(ConflictError, "linked"):
            discover_makepkg(linked)

    def test_two_distinct_path_versions_hold(self):
        first = self.tool(self.root / "path-a", bin_subdir=False)
        second = self.tool(self.root / "path-b", bin_subdir=False)
        os.environ["PATH"] = str(first.parent) + ";" + str(second.parent)
        with self.assertRaisesRegex(HoldError, "multiple"):
            discover_makepkg()
        self.assertEqual(discover_makepkg(first), first.resolve())

    def test_path_and_gdk_bin_same_file_not_ambiguous(self):
        path = self.tool(self.root / "path-only", bin_subdir=False)
        os.environ["PATH"] = str(path.parent)
        os.environ["GDK_BIN"] = str(path.parent)
        self.assertEqual(discover_makepkg(), path.resolve())

    def test_empty_and_relative_path_entries_not_searched(self):
        os.environ["PATH"] = ";.;relative;\"\""
        with self.assertRaisesRegex(HoldError, "not discovered"):
            discover_makepkg()

    def test_current_directory_executable_is_not_discovered(self):
        # Windows command lookup can search cwd even with a relative PATH.
        # Discovery must never accept it without an explicit absolute path.
        fake = self.tool(self.root, bin_subdir=False)
        old_cwd = os.getcwd()
        try:
            os.chdir(self.root)
            os.environ["PATH"] = ".;relative;"
            with self.assertRaisesRegex(HoldError, "not discovered"):
                discover_makepkg()
        finally:
            os.chdir(old_cwd)
        self.assertEqual(discover_makepkg(fake), fake.resolve())

    def test_relative_explicit_path_rejected(self):
        fake = self.tool(self.root, bin_subdir=False)
        old_cwd = os.getcwd()
        try:
            os.chdir(self.root)
            with self.assertRaisesRegex(ConflictError, "absolute"):
                discover_makepkg(Path("makepkg.exe"))
        finally:
            os.chdir(old_cwd)

    def test_relative_environment_sdk_roots_rejected(self):
        for name in ("GameDK", "GameDKCoreLatest", "GDK_BIN"):
            with self.subTest(name=name):
                os.environ[name] = "relative-sdk-root"
                with self.assertRaisesRegex(ConflictError, "absolute"):
                    discover_makepkg()
                os.environ.pop(name)

    def test_symlink_parent_rejected(self):
        path = self.tool(self.root / "actual", bin_subdir=False)
        linked = self.root / "linked-dir"
        try:
            linked.symlink_to(path.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlink creation unavailable")
        os.environ["GDK_BIN"] = str(linked)
        with self.assertRaisesRegex(ConflictError, "linked"):
            discover_makepkg()

    def test_missing_candidate_holds(self):
        with self.assertRaisesRegex(HoldError, "not discovered"):
            discover_makepkg()

    def test_explicit_missing_candidate_holds(self):
        with self.assertRaisesRegex(HoldError, "does not exist"):
            discover_makepkg(self.root / "missing.exe")

    def test_non_windows_holds(self):
        with mock.patch("gdk_sdk_discovery.platform.system", return_value="Linux"):
            with self.assertRaisesRegex(HoldError, "requires Windows"):
                discover_makepkg()


if __name__ == "__main__":
    unittest.main()
