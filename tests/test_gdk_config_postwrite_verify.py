"""Signal Sprint GDK config CLI must verify the bytes it just staged."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gdk_microsoft_game_config as cfg
from package_identity_provisioner import ConflictError


class GdkConfigPostWriteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.xml = '<?xml version="1.0" encoding="utf-8"?>\n<Game />\n'
        self.args = [
            "--factory-checkout", str(self.root),
            "--pinned-artifact-zip", str(self.root / "pinned.zip"),
            "--cas-commit-sha", "a" * 40,
            "--build-head-sha", "b" * 40,
            "--asset-root", str(self.root),
            "--package-version", "1.0.1.0",
            "--reviewed-display-name", "Signal Sprint",
        ]

    def invoke(self, *, write, verifier):
        with patch.object(cfg, "create_intake", return_value={}), patch.object(
                cfg, "prepare_config", return_value={
                    "status": "GDK_CONFIG_CHECK_ONLY",
                    "microsoft_game_config_xml": self.xml,
                }), patch.object(cfg, "verify_staging_inputs", side_effect=verifier) as check:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cfg.main(self.args + (["--write-staging-config"] if write else []))
        return code, json.loads(stdout.getvalue()), check

    def test_written_config_is_verified_before_reporting_path(self):
        def check(root, contract, *, require_config):
            self.assertTrue(require_config)
            self.assertEqual(root, self.root)
            self.assertEqual((root / "MicrosoftGame.config").read_bytes(), self.xml.encode("utf-8"))
        code, result, check = self.invoke(write=True, verifier=check)
        self.assertEqual(code, 0)
        self.assertEqual(check.call_count, 1)
        self.assertEqual(result["config_path"], str(self.root / "MicrosoftGame.config"))

    def test_postwrite_verification_failure_is_not_reported_as_success(self):
        def reject(root, contract, *, require_config):
            self.assertTrue(require_config)
            (root / "MicrosoftGame.config").write_text("changed", encoding="utf-8")
            raise ConflictError("GDK staged MicrosoftGame.config bytes changed")
        code, result, check = self.invoke(write=True, verifier=reject)
        self.assertEqual(code, 2)
        self.assertEqual(check.call_count, 1)
        self.assertNotIn("config_path", result)
        self.assertFalse(result["real_msixvc_built"])
        self.assertIn("bytes changed", result["error"])

    def test_identical_existing_config_is_restart_safe(self):
        target = self.root / "MicrosoftGame.config"
        def check(root, contract, *, require_config):
            self.assertTrue(require_config)
            self.assertEqual(target.read_bytes(), self.xml.encode("utf-8"))
        first_code, first_result, first_check = self.invoke(write=True, verifier=check)
        second_code, second_result, second_check = self.invoke(write=True, verifier=check)
        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(first_check.call_count, 1)
        self.assertEqual(second_check.call_count, 1)
        self.assertEqual(first_result["config_path"], second_result["config_path"])
        self.assertEqual(target.read_bytes(), self.xml.encode("utf-8"))

    def test_foreign_existing_config_is_never_overwritten(self):
        target = self.root / "MicrosoftGame.config"
        target.write_bytes(b"foreign config")
        def reject(root, contract, *, require_config):
            self.assertTrue(require_config)
            self.assertEqual(target.read_bytes(), b"foreign config")
            raise ConflictError("GDK staged MicrosoftGame.config bytes changed")
        code, result, check = self.invoke(write=True, verifier=reject)
        self.assertEqual(code, 2)
        self.assertEqual(check.call_count, 1)
        self.assertNotIn("config_path", result)
        self.assertFalse(result["real_msixvc_built"])
        self.assertEqual(target.read_bytes(), b"foreign config")

    def test_check_only_does_not_write_or_call_postwrite_verifier(self):
        code, result, check = self.invoke(write=False, verifier=AssertionError("unexpected"))
        self.assertEqual(code, 0)
        self.assertEqual(check.call_count, 0)
        self.assertNotIn("config_path", result)
        self.assertFalse((self.root / "MicrosoftGame.config").exists())


if __name__ == "__main__":
    unittest.main()
