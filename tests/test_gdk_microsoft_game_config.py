"""Synthetic GDK config fixtures: no real CAS, GDK SDK, or Store calls."""
import copy
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zlib

import gdk_microsoft_game_config as cfg
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB,
)


def chunk(name, payload):
    return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))


def png(width, height):
    pixels = b"".join(b"\x00" + b"\0" * (width * 4) for _ in range(height))
    return (cfg.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b""))


class MicrosoftGameConfigTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.exe = b"MZ" + b"fixture-executable" * 20
        (self.root / "SignalSprint.exe").write_bytes(self.exe)
        for name, dims in cfg.ASSETS.values():
            (self.root / name).write_bytes(png(*dims))
        self.exe_patch = patch.object(cfg, "EXE_SHA256", hashlib.sha256(self.exe).hexdigest())
        self.exe_patch.start()
        self.addCleanup(self.exe_patch.stop)
        self.intake = {
            "status": "GDK_BUILD_INPUT_CHECK_ONLY", "packaging_family": "GDK",
            "next_stage": "BUILD_GDK_MSIXVC_FROM_PINNED_EXE",
            "package_format": "MSIXVC_OR_MSIXVC2",
            "identity": copy.deepcopy(PINNED_SIGNAL_SPRINT_GDK_IDENTITY),
            "pinned_exe": {"executable_sha256": cfg.EXE_SHA256},
            "package_version": None, "real_msixvc_built": False, "store_submitted": False,
            "cas_commit_sha": "a" * 40, "factory_head_sha": "b" * 40,
            **{k: PINNED_SIGNAL_SPRINT_JOB[k] for k in ("request_id", "source_repository", "source_branch", "source_sha")},
        }

    def build(self):
        return cfg.prepare_config(self.intake, self.root, "1.0.1.0", "Signal Sprint (reviewed fixture)")

    def test_exact_identity_executable_source_and_no_false_pass(self):
        result = self.build()
        xml = ET.fromstring(result["microsoft_game_config_xml"])
        self.assertEqual(xml.find("Identity").attrib["Name"], "OkinawaDesktopTools.SignalSprint")
        self.assertEqual(xml.find("Identity").attrib["Publisher"], PINNED_SIGNAL_SPRINT_GDK_IDENTITY["publisher"])
        self.assertEqual(xml.find("Identity").attrib["Version"], "1.0.1.0")
        self.assertEqual(xml.findtext("StoreId"), "9N21MJM7S57P")
        # Microsoft requires no TitleId/MSAAppId in retail config when Xbox
        # services are not used; their receipt remains pinned in the intake.
        self.assertIsNone(xml.find("TitleId"))
        self.assertIsNone(xml.find("MSAAppId"))
        self.assertEqual(self.intake["identity"]["xbox_title_id"], "68721417")
        self.assertEqual(self.intake["identity"]["msa_app_id"],
                         PINNED_SIGNAL_SPRINT_GDK_IDENTITY["msa_app_id"])
        self.assertEqual(xml.find("ExecutableList/Executable").attrib["Name"], "SignalSprint.exe")
        self.assertEqual(xml.find("ExecutableList/Executable").attrib["TargetDeviceFamily"], "PC")
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["gdk_sdk_validated"])
        self.assertEqual(result["source_sha"], PINNED_SIGNAL_SPRINT_JOB["source_sha"])
        self.assertEqual(result["microsoft_game_config_sha256"], hashlib.sha256(result["microsoft_game_config_xml"].encode()).hexdigest())

    def test_unreviewed_xbox_service_identity_still_rejected(self):
        # Omitting unused XML elements must not relax the received Identity
        # contract or permit an attacker to substitute another Xbox title.
        self.intake["identity"]["xbox_title_id"] = "FFFFFFFF"
        with self.assertRaisesRegex(ConflictError, "Identity mismatch"):
            self.build()

    def test_wrong_store_id_rejected(self):
        self.intake["identity"]["store_id"] = "9N21MJM7S57Q"
        with self.assertRaisesRegex(ConflictError, "Identity mismatch"): self.build()

    def test_wrong_source_rejected(self):
        self.intake["source_sha"] = "f" * 40
        with self.assertRaisesRegex(ConflictError, "immutable"): self.build()

    def test_unverified_intake_rejected(self):
        self.intake["status"] = "CAS_RETURN_PASS"
        with self.assertRaisesRegex(ConflictError, "verified"): self.build()

    def test_version_missing_rejected(self):
        with self.assertRaisesRegex(HoldError, "explicit"):
            cfg.prepare_config(self.intake, self.root, "", "Signal Sprint")

    def test_store_reserved_fourth_component_rejected(self):
        with self.assertRaisesRegex(HoldError, "fourth"):
            cfg.prepare_config(self.intake, self.root, "1.0.1.1", "Signal Sprint")

    def test_version_component_overflow_rejected(self):
        with self.assertRaisesRegex(HoldError, "range"):
            cfg.prepare_config(self.intake, self.root, "65536.0.0.0", "Signal Sprint")

    def test_reviewed_display_required(self):
        with self.assertRaisesRegex(HoldError, "display name"):
            cfg.prepare_config(self.intake, self.root, "1.0.1.0", " ")

    def test_rebuilt_exe_rejected(self):
        (self.root / "SignalSprint.exe").write_bytes(b"MZchanged")
        with self.assertRaisesRegex(ConflictError, "immutable artifact"): self.build()

    def test_missing_icon_rejected(self):
        (self.root / "Logo.png").unlink()
        with self.assertRaisesRegex(HoldError, "missing"): self.build()

    def test_wrong_icon_dimensions_rejected(self):
        (self.root / "Logo.png").write_bytes(png(100, 100))
        with self.assertRaisesRegex(ConflictError, "dimensions"): self.build()

    def test_corrupt_png_crc_rejected(self):
        p = self.root / "SmallLogo.png"
        b = bytearray(p.read_bytes()); b[25] ^= 1; p.write_bytes(b)
        with self.assertRaisesRegex(ConflictError, "CRC"): self.build()

    def test_png_unknown_critical_chunk_rejected_even_with_valid_crc(self):
        p = self.root / "SmallLogo.png"
        original = p.read_bytes()
        ihdr_end = len(cfg.PNG_SIGNATURE) + 12 + 13
        p.write_bytes(original[:ihdr_end] + chunk(b"ABCD", b"unsupported")
                      + original[ihdr_end:])
        with self.assertRaisesRegex(ConflictError, "unknown critical PNG chunk"):
            self.build()

    def test_png_unknown_ancillary_chunk_is_ignorable(self):
        p = self.root / "SmallLogo.png"
        original = p.read_bytes()
        ihdr_end = len(cfg.PNG_SIGNATURE) + 12 + 13
        p.write_bytes(original[:ihdr_end] + chunk(b"tEXt", b"Note\\x00ok")
                      + original[ihdr_end:])
        self.assertEqual(self.build()["status"], "GDK_CONFIG_CHECK_ONLY")

    def test_png_invalid_reserved_chunk_name_rejected(self):
        p = self.root / "SmallLogo.png"
        original = p.read_bytes()
        ihdr_end = len(cfg.PNG_SIGNATURE) + 12 + 13
        p.write_bytes(original[:ihdr_end] + chunk(b"abcz", b"test")
                      + original[ihdr_end:])
        with self.assertRaisesRegex(ConflictError, "invalid PNG chunk type"):
            self.build()

    def test_png_grayscale_palette_rejected(self):
        p = self.root / "SmallLogo.png"
        raw = b"".join(b"\\x00" + b"\\x00" * 44 for _ in range(44))
        p.write_bytes(cfg.PNG_SIGNATURE + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 44, 44, 8, 0, 0, 0, 0)
        ) + chunk(b"PLTE", b"\\x00\\x00\\x00")
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        with self.assertRaisesRegex(ConflictError, "invalid PNG palette"):
            self.build()

    def test_png_indexed_palette_over_bit_depth_rejected(self):
        p = self.root / "SmallLogo.png"
        raw = b"".join(b"\\x00" + b"\\x00" * 6 for _ in range(44))
        p.write_bytes(cfg.PNG_SIGNATURE + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 44, 44, 1, 3, 0, 0, 0)
        ) + chunk(b"PLTE", b"\\x00\\x00\\x00" * 3)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        with self.assertRaisesRegex(ConflictError, "invalid PNG palette"):
            self.build()

    def test_png_missing_idat_rejected_even_with_valid_crc(self):
        p = self.root / "Logo.png"
        p.write_bytes(cfg.PNG_SIGNATURE + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 150, 150, 8, 6, 0, 0, 0)
        ) + chunk(b"IEND", b""))
        with self.assertRaisesRegex(ConflictError, "image data"):
            self.build()

    def test_png_corrupt_deflate_rejected_even_with_valid_crc(self):
        p = self.root / "SmallLogo.png"
        p.write_bytes(cfg.PNG_SIGNATURE + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 44, 44, 8, 6, 0, 0, 0)
        ) + chunk(b"IDAT", b"not a zlib stream") + chunk(b"IEND", b""))
        with self.assertRaisesRegex(ConflictError, "compressed image"):
            self.build()

    def test_png_invalid_filter_rejected_even_with_valid_crc(self):
        p = self.root / "SmallLogo.png"
        raw = b"".join(b"\x05" + b"\0" * (44 * 4) for _ in range(44))
        p.write_bytes(cfg.PNG_SIGNATURE + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 44, 44, 8, 6, 0, 0, 0)
        ) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        with self.assertRaisesRegex(ConflictError, "scanline filter"):
            self.build()

    def test_png_short_decompressed_image_rejected(self):
        p = self.root / "SmallLogo.png"
        raw = b"\0" * 100
        p.write_bytes(cfg.PNG_SIGNATURE + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 44, 44, 8, 6, 0, 0, 0)
        ) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        with self.assertRaisesRegex(ConflictError, "decompressed scanlines"):
            self.build()

    def test_symlink_exe_rejected(self):
        (self.root / "SignalSprint.exe").unlink()
        (self.root / "real.exe").write_bytes(self.exe)
        (self.root / "SignalSprint.exe").symlink_to(self.root / "real.exe")
        with self.assertRaisesRegex(HoldError, "linked"): self.build()

    def test_false_downstream_success_rejected(self):
        self.intake["real_msixvc_built"] = True
        with self.assertRaisesRegex(ConflictError, "downstream"): self.build()

    def test_check_only_never_writes_config(self):
        self.build()
        self.assertFalse((self.root / "MicrosoftGame.config").exists())


if __name__ == "__main__":
    unittest.main()
