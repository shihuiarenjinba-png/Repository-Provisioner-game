"""Negative fixtures: GUI evidence cannot be inferred from process start."""
from pathlib import Path
import unittest
from unittest.mock import patch
import gdk_signal_sprint_gui_receipt as checker


def observed():
    receipt = {
        "schema_version": 1, "product": "Signal Sprint",
        "registration": "GDK_GAME", "source_sha": checker.SOURCE,
        "new_request_id": checker.REQUEST, "github_run_id": 41361263698,
        "github_artifact_id": 13105352227, "exe_sha256": checker.EXE_SHA,
        "exe_size_bytes": 11344389,
        "evidence_kind": "REAL_WINDOWS_EXE_UIAUTOMATION_CHECK_ONLY",
        "status": "WINDOWS_GUI_AUTOMATED_CHECK_ONLY",
        "reason": "REAL_WINDOW_FIRST_MOVE_LOSS_RETRY_OBSERVED_NOT_HUMAN_QA",
        "first_move_seconds": 3.5, "screenshot_captured": False,
    }
    receipt.update({key: True for key in checker.TRUE_CHECKS})
    receipt.update({key: False for key in checker.FALSE_AUTHORITIES})
    return receipt


class ReceiptTests(unittest.TestCase):
    def test_observed_input_without_screen_geometry_is_held(self):
        result = checker.validate(observed())
        self.assertEqual(result["status"], "WINDOWS_GUI_RECEIPT_REVIEW_HOLD")
        self.assertIn("WINDOW_VISIBILITY_HOLD:SCREENSHOT_NOT_OBSERVED", result["reason"])
        self.assertFalse(result["ready_for_sale"])
        self.assertFalse(result["human_qa_pass"])

    def test_held_runner_never_passes(self):
        receipt = observed()
        receipt["status"] = "WINDOWS_GUI_CHECK_ONLY_HOLD"
        receipt["reason"] = "NO_INTERACTIVE_GUI_WINDOW_OR_SESSION"
        self.assertIn("NO_REAL_GUI_OBSERVATION", checker.validate(receipt)["reason"])

    def test_missing_any_real_observation_holds(self):
        for key in checker.TRUE_CHECKS:
            with self.subTest(key=key):
                receipt = observed()
                receipt[key] = False
                self.assertIn("UNOBSERVED_GUI_STEP", checker.validate(receipt)["reason"])

    def test_fake_authority_claims_hold(self):
        for key in checker.FALSE_AUTHORITIES:
            with self.subTest(key=key):
                receipt = observed()
                receipt[key] = True
                self.assertIn("FORBIDDEN_AUTHORITY_CLAIM", checker.validate(receipt)["reason"])

    def test_wrong_identity_request_artifact_and_exe_hold(self):
        for key in ("source_sha", "new_request_id", "github_artifact_id",
                    "exe_sha256", "exe_size_bytes", "registration", "github_run_id"):
            with self.subTest(key=key):
                receipt = observed()
                receipt[key] = "old-artifact"
                self.assertIn("MISMATCH", checker.validate(receipt)["reason"])

    def test_timing_not_observed_under_30_seconds_holds(self):
        for value in (None, 0, 31, "2", True, -1):
            with self.subTest(value=value):
                receipt = observed()
                receipt["first_move_seconds"] = value
                self.assertIn("TIMING_NOT_PROVEN", checker.validate(receipt)["reason"])

    def test_screenshot_not_substitute_for_interaction(self):
        receipt = observed()
        receipt["first_move_ui_observed"] = False
        receipt["screenshot_captured"] = True
        receipt["screenshot_dimensions"] = [1024, 768]
        self.assertIn("UNOBSERVED", checker.validate(receipt)["reason"])

    def test_bad_screenshot_dimensions_hold(self):
        receipt = observed()
        receipt["screenshot_captured"] = True
        receipt["screenshot_dimensions"] = [300, 200]
        self.assertIn("SCREENSHOT_DIMENSIONS_INVALID", checker.validate(receipt)["reason"])

    def test_powershell_uses_real_exe_and_ui_not_synthetic_pass(self):
        script = (Path(__file__).resolve().parents[1] / "qa" /
                  "signal_sprint_windows_gui_smoke.ps1").read_text(encoding="utf-8")
        for needle in ("Start-Process", "Get-FileHash", "UIAutomationClient",
                       "SendKeys", "WINDOWS_GUI_CHECK_ONLY_HOLD",
                       "Stop-Process", "EXE_SHA256_MISMATCH",
                       "FIRST_REAL_INPUT_NO_OBSERVABLE_UI_CHANGE"):
            self.assertIn(needle, script)
        self.assertNotIn("gdk_sdk.exe", script.lower())


if __name__ == "__main__":
    unittest.main()
