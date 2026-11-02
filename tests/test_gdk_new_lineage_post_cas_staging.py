"""Staging-level negative fixtures: no GDK SDK, CAS or Store calls."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from gdk_new_lineage_post_cas_gate import verify_staging, EXE_SHA
from gdk_microsoft_game_config import ASSETS
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_GDK_IDENTITY as ID, ConflictError

class StagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "SignalSprint.exe").write_bytes(b"MZnew-lineage-synthetic")
        for _, (name, _) in ASSETS.items():
            (self.root / name).write_bytes(b"fake-PNG-test-only")
        self.make_config()
        self.hashes = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                       for name, _ in ASSETS.values()}

    def make_config(self, **changes):
        values = {
            "name": ID["name"], "publisher": ID["publisher"],
            "version": "1.0.0.0", "store_id": ID["store_id"],
            "title": ID["xbox_title_id"], "msa": ID["msa_app_id"],
            "exe": "SignalSprint.exe", "display": "Signal Sprint",
            "publisher_display": ID["publisher_display_name"],
        }
        values.update(changes)
        root = ET.Element("Game")
        ET.SubElement(root, "Identity", {
            "Name": values["name"], "Publisher": values["publisher"],
            "Version": values["version"]})
        for tag, value in (("StoreId", values["store_id"]), ("TitleId", values["title"]),
                           ("MSAAppId", values["msa"])):
            ET.SubElement(root, tag).text = value
        ET.SubElement(ET.SubElement(root, "ExecutableList"), "Executable",
                      {"Name": values["exe"]})
        visuals = {"DefaultDisplayName": values["display"],
                   "PublisherDisplayName": values["publisher_display"]}
        visuals.update({key: name for key, (name, _) in ASSETS.items()})
        if "visual_override" in changes:
            visuals["StoreLogo"] = changes["visual_override"]
        ET.SubElement(root, "ShellVisuals", visuals)
        (self.root / "MicrosoftGame.config").write_bytes(ET.tostring(root))

    def check(self, *, exe_digest=EXE_SHA, png_ok=True):
        def hashed(path):
            if path.name == "SignalSprint.exe":
                return exe_digest
            return hashlib.sha256(path.read_bytes()).hexdigest()
        def dims(path):
            for _, (name, size) in ASSETS.items():
                if name == path.name:
                    return size if png_ok else (1, 1)
            raise AssertionError("unexpected image")
        with patch("gdk_new_lineage_post_cas_gate.digest", side_effect=hashed), \
             patch("gdk_new_lineage_post_cas_gate._png_dimensions", side_effect=dims):
            return verify_staging(self.root, EXE_SHA, "1.0.0.0",
                                  "Signal Sprint", self.hashes)

    def assert_conflict(self, expected):
        with self.assertRaisesRegex(ConflictError, expected):
            self.check()

    def test_positive_is_staging_snapshot_only(self):
        result = self.check()
        self.assertEqual(result["SignalSprint.exe"], EXE_SHA)
        self.assertEqual(set(result), {"SignalSprint.exe", "MicrosoftGame.config",
                                      *self.hashes})

    def test_title_id_mixing(self):
        self.make_config(title="12345678")
        self.assert_conflict("IDENTITY_VERSION_MISMATCH")

    def test_msa_app_id_mixing(self):
        self.make_config(msa="00000000-0000-0000-0000-000000000000")
        self.assert_conflict("IDENTITY_VERSION_MISMATCH")

    def test_store_id_mixing(self):
        self.make_config(store_id="FOREIGN_STORE")
        self.assert_conflict("IDENTITY_VERSION_MISMATCH")

    def test_identity_name_mixing(self):
        self.make_config(name="Foreign.Game")
        self.assert_conflict("IDENTITY_VERSION_MISMATCH")

    def test_version_mismatch(self):
        self.make_config(version="2.0.0.0")
        self.assert_conflict("IDENTITY_VERSION_MISMATCH")

    def test_display_mismatch(self):
        self.make_config(display="Unreviewed Game")
        self.assert_conflict("IDENTITY_VERSION_MISMATCH")

    def test_config_asset_path_mismatch(self):
        self.make_config(visual_override="other.png")
        self.assert_conflict("CONFIG_ASSET_MISMATCH")

    def test_rehashed_exe_rejected(self):
        with self.assertRaisesRegex(ConflictError, "STAGED_EXE_SHA_MISMATCH"):
            self.check(exe_digest="0" * 64)

    def test_foreign_asset_digest_rejected(self):
        self.hashes["Logo.png"] = "0" * 64
        self.assert_conflict("ASSET_REVIEW_DIGEST_MISMATCH")

    def test_missing_asset_rejected(self):
        (self.root / "Logo.png").unlink()
        self.assert_conflict("STAGING_UNREVIEWED_OR_MISSING_FILE")

    def test_unreviewed_extra_file_rejected(self):
        (self.root / "secret.dll").write_bytes(b"x")
        self.assert_conflict("STAGING_UNREVIEWED_OR_MISSING_FILE")

    def test_symlink_asset_rejected(self):
        logo = self.root / "Logo.png"
        logo.unlink()
        try:
            logo.symlink_to(self.root / "StoreLogo.png")
        except (OSError, NotImplementedError):
            self.skipTest("symlink not permitted on this host")
        self.assert_conflict("UNSAFE_OR_MISSING_FILE")

    def test_wrong_png_dimensions_rejected(self):
        with self.assertRaisesRegex(ConflictError, "STAGED_PNG_DIMENSIONS_INVALID"):
            self.check(png_ok=False)

if __name__ == "__main__":
    unittest.main()
