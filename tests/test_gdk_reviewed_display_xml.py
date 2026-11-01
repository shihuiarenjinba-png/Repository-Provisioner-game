"""GDK reviewed display names must be safe for MicrosoftGame.config XML 1.0.

Offline validation only: no CAS, GDK SDK, or Partner Center access.
"""
import unittest
import xml.etree.ElementTree as ET

from gdk_microsoft_game_config import _reviewed_display
from package_identity_provisioner import HoldError


class GdkReviewedDisplayXmlTests(unittest.TestCase):
    def test_invalid_xml_unicode_fails_as_classified_hold(self):
        for invalid in ("\uD800", "\uDFFF", "\uFFFE", "\uFFFF"):
            with self.subTest(codepoint=hex(ord(invalid))):
                with self.assertRaisesRegex(HoldError, "display name"):
                    _reviewed_display("Signal Sprint " + invalid)

    def test_existing_control_and_whitespace_rejections_remain(self):
        for invalid in ("", " ", " Signal Sprint", "Signal Sprint ", "Signal\nSprint"):
            with self.subTest(name=repr(invalid)):
                with self.assertRaises(HoldError):
                    _reviewed_display(invalid)

    def test_valid_japanese_and_supplementary_unicode_roundtrip(self):
        for name in ("Signal Sprint", "シグナル・スプリント", "Signal Sprint 🎮"):
            with self.subTest(name=name):
                self.assertEqual(_reviewed_display(name), name)
                xml = ET.tostring(ET.Element("ShellVisuals", {"DefaultDisplayName": name}),
                                  encoding="utf-8")
                self.assertEqual(ET.fromstring(xml).attrib["DefaultDisplayName"], name)


if __name__ == "__main__":
    unittest.main()
