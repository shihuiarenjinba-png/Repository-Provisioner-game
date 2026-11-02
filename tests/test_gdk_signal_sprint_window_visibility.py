"""Positive/negative geometry fixtures; none is a real GUI or human QA PASS."""
import hashlib
import tempfile
import unittest
from pathlib import Path

import gdk_signal_sprint_window_visibility as gate


def evidence():
    return {
        "source_sha": gate.SOURCE, "new_request_id": gate.REQUEST,
        "exe_sha256": gate.EXE, "github_artifact_id": 13105352227,
        "github_run_id": 41361263698, "registration": "GDK_GAME",
        "screenshot_captured": True, "screenshot_sha256": "a" * 64,
        "screenshot_dimensions": [1024, 768],
        "coordinate_space": "SCREEN_PHYSICAL_PIXELS_CONFIRMED",
        "monitor_bounds": [0, 0, 1024, 768],
        "work_area_bounds": [0, 0, 1024, 768],
        "window_bounds": [0, 0, 1024, 768],
        "critical_control_bounds": [{"name": "Restart", "bounds": [630, 392, 1014, 448]}],
        "dpi_percent": 100,
    }


class VisibilityTests(unittest.TestCase):
    def test_geometry_clear_is_still_dpi_hold(self):
        r = gate.check(evidence())
        self.assertEqual(r["status"], "WINDOW_VISIBILITY_HOLD")
        self.assertEqual(r["reason"], "DPI_125_150_INDEPENDENT_QA_UNVERIFIED")
        self.assertTrue(r["geometry_check_only"])
        self.assertFalse(r["ready_for_sale"])

    def test_realistic_taskbar_overlap_fails_closed(self):
        e = evidence()
        e["work_area_bounds"] = [0, 0, 1024, 720]
        r = gate.check(e)
        self.assertEqual(r["reason"], "WINDOW_OVERLAPS_TASKBAR_OR_RESERVED_WORKAREA")
        self.assertEqual(r["outside_workarea_area_px2"], 1024 * 48)

    def test_left_or_top_docked_taskbar_detected(self):
        for work in ([60, 0, 1024, 768], [0, 40, 1024, 768]):
            with self.subTest(work=work):
                e = evidence()
                e["work_area_bounds"] = work
                self.assertIn("WINDOW_OVERLAPS", gate.check(e)["reason"])

    def test_critical_control_occlusion_rejected(self):
        e = evidence()
        e["work_area_bounds"] = [0, 0, 1024, 720]
        e["window_bounds"] = [0, 0, 1024, 720]
        e["screenshot_dimensions"] = [1024, 720]
        e["critical_control_bounds"] = [{"name": "Restart", "bounds": [630, 700, 1014, 735]}]
        self.assertEqual(gate.check(e)["reason"], "CONTROL_OUTSIDE_WINDOW_OR_UNOBSERVED")

    def test_missing_tk_uia_control_bounds_holds(self):
        e = evidence()
        e["critical_control_bounds"] = []
        self.assertEqual(gate.check(e)["reason"], "CRITICAL_CONTROL_BOUNDS_UNOBSERVED")

    def test_dpi_125_and_150_cannot_use_unverified_coordinate_space(self):
        for dpi in (125, 150):
            e = evidence()
            e["dpi_percent"] = dpi
            e["coordinate_space"] = "SCREEN_COORDINATES_UNVERIFIED"
            self.assertEqual(gate.check(e)["reason"], "COORDINATE_SPACE_UNVERIFIED")

    def test_wrong_artifact_request_or_exe_rejected(self):
        for key in ("source_sha", "new_request_id", "exe_sha256",
                    "github_artifact_id", "github_run_id", "registration"):
            with self.subTest(key=key):
                e = evidence()
                e[key] = "old-artifact"
                self.assertIn("ARTIFACT_BINDING_MISMATCH", gate.check(e)["reason"])

    def test_screenshot_file_digest_must_match(self):
        e = evidence()
        with tempfile.TemporaryDirectory() as td:
            screenshot = Path(td) / "actual.png"
            screenshot.write_bytes(b"real screenshot bytes")
            self.assertEqual(gate.check(e, screenshot)["reason"], "SCREENSHOT_BYTES_MISMATCH")
            e["screenshot_sha256"] = hashlib.sha256(screenshot.read_bytes()).hexdigest()
            self.assertEqual(gate.check(e, screenshot)["reason"],
                             "DPI_125_150_INDEPENDENT_QA_UNVERIFIED")

    def test_missing_screenshot_or_geometry_holds(self):
        e = evidence()
        e["screenshot_captured"] = False
        self.assertEqual(gate.check(e)["reason"], "SCREENSHOT_NOT_OBSERVED")
        e = evidence()
        e["work_area_bounds"] = None
        self.assertEqual(gate.check(e)["reason"], "SCREEN_GEOMETRY_MISSING_OR_INVALID")

    def test_screenshot_window_mismatch_holds(self):
        e = evidence()
        e["screenshot_dimensions"] = [1024, 720]
        self.assertEqual(gate.check(e)["reason"], "SCREENSHOT_WINDOW_SIZE_MISMATCH")

    def test_no_success_claims_in_any_result(self):
        for e in (evidence(), {**evidence(), "work_area_bounds": [0, 0, 1024, 720]}):
            r = gate.check(e)
            for key in ("ready_for_sale", "human_qa_pass", "cas_return_pass",
                        "real_msixvc_built", "dpi_125_150_verified"):
                self.assertFalse(r[key])


if __name__ == "__main__":
    unittest.main()
