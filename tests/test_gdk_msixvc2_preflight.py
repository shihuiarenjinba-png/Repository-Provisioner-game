"""Synthetic MSIXVC2 staging checks; never invoke the GDK SDK or Store."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_msixvc2_preflight as gate
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB


class GdkMsixvc2PreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.exe = b"MZ" + b"synthetic-pinned-exe" * 10
        self.xml = '<?xml version="1.0"?><Game configVersion="1" />\n'
        for name in gate.MAX_FILE_BYTES:
            data = (self.exe if name == "SignalSprint.exe"
                    else self.xml.encode() if name == "MicrosoftGame.config"
                    else b"synthetic-png-fixture")
            (self.root / name).write_bytes(data)
        self.config = {
            "status": "GDK_CONFIG_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "package_version": "1.0.1.0",
            "microsoft_game_config_xml": self.xml,
            "microsoft_game_config_sha256": hashlib.sha256(self.xml.encode()).hexdigest(),
            "gdk_sdk_validated": False, "real_msixvc_built": False,
            "store_submitted": False,
        }
        self.intake = {"pinned_exe": {"artifact_zip_sha256": "a" * 64}}
        for name, value in (
            ("EXE_SHA256", hashlib.sha256(self.exe).hexdigest()),
            ("create_intake", lambda *args: self.intake),
            ("prepare_config", lambda *args: self.config),
        ):
            p = patch.object(gate, name, value)
            p.start()
            self.addCleanup(p.stop)

    def run_gate(self):
        return gate.create_preflight(
            self.root, self.root / "original.zip", "b" * 40, "c" * 40,
            self.root, "1.0.1.0", "Signal Sprint")

    def test_exact_staging_is_check_only(self):
        result = self.run_gate()
        self.assertEqual(result["status"], "GDK_MSIXVC2_STAGING_CHECK_ONLY")
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertEqual(result["package_format"], "MSIXVC2")
        self.assertEqual(result["source_sha"], PINNED_SIGNAL_SPRINT_JOB["source_sha"])
        self.assertEqual(result["staging_files_sha256"]["SignalSprint.exe"], gate.EXE_SHA256)
        self.assertEqual(set(result["staging_files_sha256"]), set(gate.MAX_FILE_BYTES))
        self.assertFalse(result["gdk_sdk_validated"])
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["store_submitted"])

    def test_extra_payload_rejected(self):
        (self.root / "surprise.dll").write_bytes(b"extra")
        with self.assertRaisesRegex(ConflictError, "unreviewed"):
            self.run_gate()

    def test_missing_icon_rejected(self):
        (self.root / "SmallLogo.png").unlink()
        with self.assertRaisesRegex(ConflictError, "missing"):
            self.run_gate()

    def test_nested_directory_rejected(self):
        (self.root / "Logo.png").unlink()
        (self.root / "Logo.png").mkdir()
        with self.assertRaisesRegex(ConflictError, "non-file"):
            self.run_gate()

    def test_linked_payload_rejected(self):
        (self.root / "StoreLogo.png").unlink()
        (self.root / "StoreLogo.png").symlink_to(self.root / "Logo.png")
        with self.assertRaisesRegex(ConflictError, "linked"):
            self.run_gate()

    def test_modified_executable_rejected(self):
        (self.root / "SignalSprint.exe").write_bytes(b"MZnew-build")
        with self.assertRaisesRegex(ConflictError, "immutable EXE"):
            self.run_gate()

    def test_modified_config_rejected(self):
        (self.root / "MicrosoftGame.config").write_bytes(b"<Game />")
        with self.assertRaisesRegex(ConflictError, "reviewed XML"):
            self.run_gate()

    def test_unreviewed_success_claim_rejected(self):
        self.config["real_msixvc_built"] = True
        with self.assertRaisesRegex(ConflictError, "downstream success"):
            self.run_gate()

    def test_config_sha_mismatch_rejected(self):
        self.config["microsoft_game_config_sha256"] = "f" * 64
        with self.assertRaisesRegex(ConflictError, "config SHA"):
            self.run_gate()

    def test_linked_staging_directory_rejected(self):
        link = self.root.parent / (self.root.name + "-link")
        link.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(lambda: link.unlink(missing_ok=True))
        with self.assertRaisesRegex(HoldError, "linked"):
            gate.verify_staging(link, self.xml)

    def test_empty_payload_rejected(self):
        (self.root / "Logo.png").write_bytes(b"")
        with self.assertRaisesRegex(ConflictError, "size"):
            self.run_gate()


if __name__ == "__main__":
    unittest.main()
