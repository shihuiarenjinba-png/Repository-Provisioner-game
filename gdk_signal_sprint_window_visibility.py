"""Fail-closed Windows taskbar / gameplay visibility check for the pinned Signal Sprint EXE.

All geometry is screen-coordinate evidence, never a substitute for human QA.
A single 100% DPI screenshot cannot certify 125% or 150% DPI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

SOURCE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST = "game-signal-sprint-" + SOURCE + "-reissue-sprint-41361263698-41361263698"
EXE = "beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0"
SHA = re.compile(r"^[0-9a-f]{64}$")


def _rect(value):
    if not isinstance(value, list) or len(value) != 4:
        return None
    if any(type(v) is not int for v in value):
        return None
    left, top, right, bottom = value
    if left >= right or top >= bottom:
        return None
    return (left, top, right, bottom)


def _contained(inner, outer):
    return all((inner[0] >= outer[0], inner[1] >= outer[1],
                inner[2] <= outer[2], inner[3] <= outer[3]))


def _intersection(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1]))


def check(receipt: dict, screenshot: Path | None = None) -> dict:
    result = {
        "status": "WINDOW_VISIBILITY_HOLD", "ready_for_sale": False,
        "human_qa_pass": False, "dpi_125_150_verified": False,
        "cas_return_pass": False, "real_msixvc_built": False,
    }
    if not isinstance(receipt, dict):
        result["reason"] = "RECEIPT_NOT_OBJECT"
        return result
    expected = {
        "source_sha": SOURCE, "new_request_id": REQUEST,
        "exe_sha256": EXE, "github_artifact_id": 13105352227,
        "github_run_id": 41361263698, "registration": "GDK_GAME",
    }
    for field, value in expected.items():
        if type(receipt.get(field)) is not type(value) or receipt[field] != value:
            result["reason"] = "ARTIFACT_BINDING_MISMATCH:" + field
            return result
    if receipt.get("screenshot_captured") is not True:
        result["reason"] = "SCREENSHOT_NOT_OBSERVED"
        return result
    digest = receipt.get("screenshot_sha256")
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        result["reason"] = "SCREENSHOT_SHA_MISSING"
        return result
    dimensions = receipt.get("screenshot_dimensions")
    if (not isinstance(dimensions, list) or len(dimensions) != 2
            or any(type(n) is not int or n <= 0 for n in dimensions)):
        result["reason"] = "SCREENSHOT_DIMENSIONS_INVALID"
        return result
    if screenshot is not None:
        try:
            data = screenshot.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                result["reason"] = "SCREENSHOT_BYTES_MISMATCH"
                return result
            if (len(data) < 24 or data[:8] != b"\\x89PNG\\r\\n\\x1a\\n"
                    or data[12:16] != b"IHDR"):
                result["reason"] = "SCREENSHOT_NOT_PNG"
                return result
            width, height = struct.unpack(">II", data[16:24])
            if [width, height] != dimensions:
                result["reason"] = "SCREENSHOT_PNG_DIMENSIONS_MISMATCH"
                return result
        except OSError:
            result["reason"] = "SCREENSHOT_UNAVAILABLE"
            return result
    # UIAutomation uses physical screen coordinates on the target runner.
    # If the runner cannot demonstrate a consistent coordinate space, HOLD.
    if receipt.get("coordinate_space") != "SCREEN_PHYSICAL_PIXELS_CONFIRMED":
        result["reason"] = "COORDINATE_SPACE_UNVERIFIED"
        return result
    monitor = _rect(receipt.get("monitor_bounds"))
    work = _rect(receipt.get("work_area_bounds"))
    window = _rect(receipt.get("window_bounds"))
    if not all((monitor, work, window)):
        result["reason"] = "SCREEN_GEOMETRY_MISSING_OR_INVALID"
        return result
    if not _contained(work, monitor) or not _contained(window, monitor):
        result["reason"] = "SCREEN_GEOMETRY_INCONSISTENT"
        return result
    if dimensions != [window[2] - window[0], window[3] - window[1]]:
        result["reason"] = "SCREENSHOT_WINDOW_SIZE_MISMATCH"
        return result
    result["window_bounds"] = list(window)
    result["work_area_bounds"] = list(work)
    result["outside_workarea_area_px2"] = (
        (window[2] - window[0]) * (window[3] - window[1])
        - _intersection(window, work))
    # Even if UIAutomation cannot see Tk controls, the entire game window
    # must be inside the Windows work area. Never infer that hidden buttons
    # are safe from a cropped screenshot.
    if not _contained(window, work):
        result["reason"] = "WINDOW_OVERLAPS_TASKBAR_OR_RESERVED_WORKAREA"
        return result
    controls = receipt.get("critical_control_bounds")
    if not isinstance(controls, list) or not controls:
        result["reason"] = "CRITICAL_CONTROL_BOUNDS_UNOBSERVED"
        return result
    for item in controls:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            result["reason"] = "CONTROL_EVIDENCE_INVALID"
            return result
        bounds = _rect(item.get("bounds"))
        if bounds is None or not _contained(bounds, window):
            result["reason"] = "CONTROL_OUTSIDE_WINDOW_OR_UNOBSERVED"
            return result
        if not _contained(bounds, work):
            result["reason"] = "CRITICAL_CONTROL_OVERLAPS_TASKBAR"
            return result
    if receipt.get("dpi_percent") not in (100, 125, 150) or type(receipt.get("dpi_percent")) is not int:
        result["reason"] = "DPI_NOT_MEASURED"
        return result
    # A single receipt is never proof of all required DPI modes.
    result["reason"] = "DPI_125_150_INDEPENDENT_QA_UNVERIFIED"
    result["geometry_check_only"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
        result = check(receipt, args.screenshot)
    except (OSError, ValueError, UnicodeError):
        result = {"status": "WINDOW_VISIBILITY_HOLD", "reason": "RECEIPT_UNREADABLE",
                  "ready_for_sale": False}
    print(json.dumps(result, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
