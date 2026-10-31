"""Offline checks for opt-in, non-submittable MSIXVC1 development path."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import gdk_msixvc1_dev_pack_plan as legacy
from gdk_build_intake import EXE_SHA256
from gdk_msixvc2_preflight import MAX_FILE_BYTES
from package_identity_provisioner import ConflictError


def approved_shared_plan():
    return {
        "schema_version": 1,
        "status": "GDK_SDK_PACK_PLAN_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2",
        "request_id": "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e",
        "source_sha": "c058cbf7fe38e02d929c67d047d717ff74bd522e",
        "cas_commit_sha": "b" * 40,
        "factory_head_sha": "c" * 40,
        "staging_files_sha256": {name: EXE_SHA256 if name == "SignalSprint.exe" else "d" * 64 for name in MAX_FILE_BYTES},
        "package_version": "1.0.1.0",
        "reviewed_display_name": "Signal Sprint",
        "verified_receipt_sha256": "e" * 64,
        "sdk_command_argv_not_executed": [
            "makepkg.exe", "pack", "/msixvc2", "/d", "/stage",
            "/pc", "/pd", "/output", "/validationcritical",
        ],
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
        "public_release_requires_certification": True,
        "msixvc2_preview_public_certification_blocked": False,
        "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
    }


class Msixvc1DevPlanTests(unittest.TestCase):
    def setUp(self):
        self.base = approved_shared_plan()
        self.patcher = patch.object(legacy, "make_pack_plan",
                                    side_effect=lambda *args: copy.deepcopy(self.base))
        self.mock = self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def plan(self):
        return legacy.make_msixvc1_dev_plan(
            Path("/factory"), Path("/original.zip"), "b" * 40,
            "c" * 40, Path("/stage"), "1.0.1.0",
            "Signal Sprint", Path("/receipt.json"), Path("/output"))

    def test_development_plan_reuses_full_existing_gate_and_does_not_execute(self):
        result = self.plan()
        self.mock.assert_called_once()
        self.assertEqual(result["status"], "GDK_MSIXVC1_DEV_PACK_PLAN_CHECK_ONLY")
        self.assertEqual(result["package_format"], "MSIXVC")
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertEqual(result["source_sha"], self.base["source_sha"])
        self.assertEqual(result["staging_files_sha256"], self.base["staging_files_sha256"])
        self.assertEqual(result["sdk_command_argv_not_executed"], [
            "makepkg.exe", "pack", "/d", "/stage", "/pc", "/pd",
            "/output", "/validationcritical",
        ])
        self.assertTrue(result["development_only"])
        for key in ("retail_submission_ready", "retail_encryption_approved",
                    "gdk_sdk_validated", "real_msixvc_built", "store_submitted"):
            self.assertIs(result[key], False, key)
        self.assertNotIn("/msixvc2", result["sdk_command_argv_not_executed"])
        self.assertNotIn("/l", result["sdk_command_argv_not_executed"])
        self.assertNotIn("/lk", result["sdk_command_argv_not_executed"])
        self.assertNotIn("/skipvalidation", result["sdk_command_argv_not_executed"])

    def test_wrong_route_or_false_sdk_success_is_rejected(self):
        for key, value in (
            ("partner_center_selection", "MSIX_OR_PWA_GAME"),
            ("package_format", "MSIXVC"),
            ("status", "GDK_SDK_PACK_EXECUTED"),
            ("gdk_sdk_validated", True),
            ("real_msixvc_built", True),
            ("store_submitted", True),
            ("schema_version", True),
        ):
            with self.subTest(key=key):
                original = self.base[key]
                self.base[key] = value
                try:
                    with self.assertRaisesRegex(ConflictError, "shared preflight mismatch"):
                        self.plan()
                finally:
                    self.base[key] = original

    def test_sdk_argv_injection_or_missing_validation_rejected(self):
        for injected in (
            ["makepkg.exe", "upload", "/msixvc2", "/d", "/stage",
             "/pc", "/pd", "/output", "/validationcritical"],
            ["makepkg.exe", "pack", "/msixvc2", "/d", "/stage",
             "/pc", "/pd", "/output", "/skipvalidation"],
            ["makepkg.exe", "pack", "/msixvc2", "/d", "",
             "/pc", "/pd", "/output", "/validationcritical"],
            ["makepkg.exe", "pack", "/msixvc2", "/d", "/stage",
             "/pc", "/pd", "/output", "/validationcritical", "/l"],
        ):
            with self.subTest(argv=injected):
                self.base["sdk_command_argv_not_executed"] = injected
                with self.assertRaisesRegex(ConflictError, "command unexpected"):
                    self.plan()

    def test_immutable_correlation_cannot_drift_even_if_shared_helper_regresses(self):
        for key, bad in (
            ("request_id", "game-other"),
            ("source_sha", "f" * 40),
            ("cas_commit_sha", "f" * 40),
            ("factory_head_sha", "f" * 40),
            ("package_version", "9.9.9.9"),
            ("reviewed_display_name", "Unreviewed Name"),
        ):
            with self.subTest(key=key):
                original = self.base[key]
                self.base[key] = bad
                try:
                    with self.assertRaisesRegex(ConflictError, "immutable binding mismatch"):
                        self.plan()
                finally:
                    self.base[key] = original

    def test_missing_or_unreviewed_payload_cannot_enter_dev_plan(self):
        for bad in (
            {"SignalSprint.exe": EXE_SHA256},
            {**self.base["staging_files_sha256"], "SignalSprint.exe": "f" * 64},
            {**self.base["staging_files_sha256"], "extra.exe": "f" * 64},
            {**self.base["staging_files_sha256"], "MicrosoftGame.config": "NOT_A_SHA"},
        ):
            with self.subTest(bad=bad):
                original = self.base["staging_files_sha256"]
                self.base["staging_files_sha256"] = bad
                try:
                    with self.assertRaisesRegex(ConflictError, "immutable staging payload mismatch"):
                        self.plan()
                finally:
                    self.base["staging_files_sha256"] = original

    def test_receipt_digest_cannot_be_omitted_or_malformed(self):
        for bad in ("", "G" * 64, None, "0" * 63):
            with self.subTest(bad=bad):
                original = self.base["verified_receipt_sha256"]
                self.base["verified_receipt_sha256"] = bad
                try:
                    with self.assertRaisesRegex(ConflictError, "receipt digest invalid"):
                        self.plan()
                finally:
                    self.base["verified_receipt_sha256"] = original

    def test_certification_or_shared_next_stage_regression_is_rejected(self):
        for key, bad in (
            ("public_release_requires_certification", False),
            ("msixvc2_preview_public_certification_blocked", True),
            ("next_stage", "STORE_SUBMIT"),
        ):
            with self.subTest(key=key):
                original = self.base[key]
                self.base[key] = bad
                try:
                    with self.assertRaisesRegex(ConflictError, "shared preflight mismatch"):
                        self.plan()
                finally:
                    self.base[key] = original

    def test_sdk_staging_and_output_paths_cannot_be_redirected(self):
        for index, bad in ((4, "/other-staging"), (7, "/other-output")):
            with self.subTest(index=index):
                original = self.base["sdk_command_argv_not_executed"][index]
                self.base["sdk_command_argv_not_executed"][index] = bad
                try:
                    with self.assertRaisesRegex(ConflictError, "command unexpected"):
                        self.plan()
                finally:
                    self.base["sdk_command_argv_not_executed"][index] = original

    def test_shared_gate_failure_is_not_bypassed(self):
        with patch.object(legacy, "make_pack_plan",
                          side_effect=ConflictError("immutable source mismatch")):
            with self.assertRaisesRegex(ConflictError, "immutable source"):
                self.plan()

    def test_no_automatic_fallback_when_msixvc2_gate_fails(self):
        self.base["package_format"] = "UNKNOWN"
        with self.assertRaises(ConflictError):
            self.plan()


if __name__ == "__main__":
    unittest.main()
