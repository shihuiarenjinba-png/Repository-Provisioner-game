"""Fail-closed independent review of real Windows GUI smoke receipts.

Never treats synthetic tests, process launch alone, or a screenshot as consumer QA.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from gdk_signal_sprint_window_visibility import check as check_window_visibility

SOURCE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST = ("game-signal-sprint-" + SOURCE +
           "-reissue-sprint-41361263698-41361263698")
EXE_SHA = "beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0"
TRUE_CHECKS = ("process_launched", "window_observed", "input_attempted", "first_move_ui_observed",
               "loss_ui_observed", "retry_ui_observed")
FALSE_AUTHORITIES = ("human_qa_pass", "consumer_sale_ready", "cas_return_pass",
                     "gdk_sdk_executed", "real_msixvc_built", "store_submitted")


def validate(receipt: dict) -> dict:
    result = {"status": "WINDOWS_GUI_RECEIPT_REVIEW_HOLD",
              "ready_for_sale": False, "human_qa_pass": False}
    if not isinstance(receipt, dict):
        result["reason"] = "INVALID_RECEIPT_TYPE"
        return result
    expected = {
        "schema_version": 1, "product": "Signal Sprint",
        "registration": "GDK_GAME", "source_sha": SOURCE,
        "new_request_id": REQUEST, "github_run_id": 41361263698,
        "github_artifact_id": 13105352227, "exe_sha256": EXE_SHA,
        "exe_size_bytes": 11344389,
        "evidence_kind": "REAL_WINDOWS_EXE_UIAUTOMATION_CHECK_ONLY",
    }
    for key, value in expected.items():
        if type(receipt.get(key)) is not type(value) or receipt.get(key) != value:
            result["reason"] = "IDENTITY_OR_ARTIFACT_MISMATCH:" + key
            return result
    for key in FALSE_AUTHORITIES:
        if receipt.get(key) is not False:
            result["reason"] = "FORBIDDEN_AUTHORITY_CLAIM:" + key
            return result
    if receipt.get("status") != "WINDOWS_GUI_AUTOMATED_CHECK_ONLY":
        result["reason"] = "NO_REAL_GUI_OBSERVATION:" + str(receipt.get("reason"))
        return result
    for key in TRUE_CHECKS:
        if receipt.get(key) is not True:
            result["reason"] = "UNOBSERVED_GUI_STEP:" + key
            return result
    seconds = receipt.get("first_move_seconds")
    if type(seconds) not in (int, float) or not 0 < seconds <= 30:
        result["reason"] = "FIRST_MOVE_TIMING_NOT_PROVEN"
        return result
    if receipt.get("screenshot_captured") is True:
        dimensions = receipt.get("screenshot_dimensions")
        if (not isinstance(dimensions, list) or len(dimensions) != 2
                or any(type(v) is not int for v in dimensions)
                or dimensions[0] < 820 or dimensions[1] < 640):
            result["reason"] = "SCREENSHOT_DIMENSIONS_INVALID"
            return result
    # Real input evidence alone cannot prove a consumer can see the controls.
    # A screenshot without matching window/work-area bounds is not sufficient.
    visibility = check_window_visibility(receipt)
    result["visibility"] = visibility
    if visibility["status"] != "WINDOW_VISIBILITY_CHECK_ONLY":
        result["reason"] = "WINDOW_VISIBILITY_HOLD:" + visibility["reason"]
        return result
    result["status"] = "WINDOWS_GUI_RECEIPT_AUTOMATED_CHECK_ONLY"
    result["reason"] = "REAL_GUI_AUTOMATION_ONLY_HUMAN_QA_AND_REPLAY_VALUE_HOLD"
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", required=True, type=Path)
    args = p.parse_args()
    try:
        result = validate(json.loads(args.receipt.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, UnicodeError) as exc:
        result = {"status": "WINDOWS_GUI_RECEIPT_REVIEW_HOLD",
                  "reason": type(exc).__name__, "ready_for_sale": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "WINDOWS_GUI_RECEIPT_AUTOMATED_CHECK_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
