"""Pure, platform-independent tests for Windows-safe GDK handoff basenames."""
import unittest

from gdk_windows_filename import validate_windows_basename, validate_unique_windows_names
from package_identity_provisioner import ConflictError


class WindowsGdkFilenameTests(unittest.TestCase):
    def test_legitimate_gdk_outputs(self):
        for name in ("SignalSprint.msixvc2", "SignalSprint.ekb",
                     "SubmissionValidator.xml", "symbols.zip", "validation.log"):
            validate_windows_basename(name, "test")

    def test_unsafe_device_names(self):
        for name in ("CON.ekb", "con.xml", "NUL.zip", "COM1.log",
                     "LPT9.json", "COM¹.ekb"):
            with self.subTest(name=name), self.assertRaisesRegex(ConflictError, "unsafe Windows filename"):
                validate_windows_basename(name, "test")

    def test_ads_and_win32_forbidden_characters(self):
        for name in ("report:secret.xml", "a?b.ekb", "a*b.zip",
                     "a<b.xml", "a>b.xml", 'a"b.xml', "a|b.log",
                     "a\\b.xml", "a/b.xml"):
            with self.subTest(name=name), self.assertRaisesRegex(ConflictError, "unsafe Windows filename"):
                validate_windows_basename(name, "test")

    def test_control_and_trailing_dot_or_space(self):
        for name in ("bad\x01.ekb", "bad.xml ", "bad.xml.", ".", "..", ""):
            with self.subTest(name=repr(name)), self.assertRaises(ConflictError):
                validate_windows_basename(name, "test")

    def test_windows_case_insensitive_collision(self):
        with self.assertRaisesRegex(ConflictError, "case-insensitive filename collision"):
            validate_unique_windows_names(["A.ekb", "a.ekb"], "test")

    def test_unicode_normalization_collision(self):
        with self.assertRaisesRegex(ConflictError, "case-insensitive filename collision"):
            validate_unique_windows_names(["caf\u00e9.xml", "cafe\u0301.xml"], "test")

    def test_distinct_names_accepted(self):
        validate_unique_windows_names(["SignalSprint.msixvc2", "SignalSprint.ekb",
                                       "SubmissionValidator.xml"], "test")


if __name__ == "__main__":
    unittest.main()
