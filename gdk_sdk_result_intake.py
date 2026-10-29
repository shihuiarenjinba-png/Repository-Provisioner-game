"""Read-only Signal Sprint GDK SDK result intake. Never claims Store certification.

This checks real package/log bytes against a claimed Windows makepkg execution.
A self-reported SDK exit code is not independent SDK validation. No CAS, SDK
invocation, package mutation, security-policy change or Store submission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_JSON = 1024 * 1024
MAX_LOG = 100 * 1024 * 1024
MAX_PACKAGE = 20 * 1024 * 1024 * 1024
MAX_SIDECAR = 2 * 1024 * 1024 * 1024
MAX_OUTPUT_FILES = 16
# makepkg may emit an EKB, Submission Validator XML/log and a symbol bundle
# beside the package. They are evidence, never a second package or approval.
SIDECAR_SUFFIXES = {".ekb", ".xml", ".zip", ".log", ".json"}
PLAN_FIELDS = {
    "schema_version", "status", "partner_center_selection", "package_format",
    "request_id", "source_sha", "cas_commit_sha", "factory_head_sha",
    "package_version", "reviewed_display_name", "verified_receipt_sha256",
    "staging_files_sha256", "sdk_command_argv_not_executed", "sdk_required",
    "msixvc2_preview_public_certification_blocked", "public_release_requires_certification",
    "next_stage", "gdk_sdk_validated", "real_msixvc_built", "store_submitted",
}
RESULT_FIELDS = {
    "schema_version", "status", "partner_center_selection", "package_format",
    "request_id", "source_sha", "cas_commit_sha", "factory_head_sha",
    "package_version", "reviewed_display_name", "verified_receipt_sha256",
    "staging_files_sha256", "sdk_command_argv", "sdk_executable",
    "sdk_version", "sdk_exit_code", "validation_log_sha256",
    "package_filename", "package_sha256", "package_size_bytes",
    "output_files_sha256", "store_submitted",
}


def _read_json(path: Path, label: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise HoldError(label + " missing or linked")
    if not 0 < path.stat().st_size <= MAX_JSON:
        raise ConflictError(label + " size invalid")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ConflictError(label + " duplicate JSON key: " + key)
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ConflictError(label + " invalid strict JSON") from exc
    if type(value) is not dict:
        raise ConflictError(label + " must be object")
    return value


def _expect(obj: dict, key: str, expected):
    actual = obj.get(key)
    if type(actual) is not type(expected) or actual != expected:
        raise ConflictError("GDK result evidence mismatch: " + key)


def _hash_file(path: Path, maximum: int, label: str) -> tuple[str, int]:
    if path.is_symlink():
        raise ConflictError(label + " linked")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
        raise ConflictError(label + " invalid regular file or size")
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ConflictError(label + " changed before open")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if total > maximum:
                raise ConflictError(label + " too large")
            h.update(chunk)
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ) or total != before.st_size:
        raise ConflictError(label + " changed during hashing")
    return h.hexdigest(), total


def intake(plan_path: Path, evidence_path: Path, package_dir: Path,
           validation_log: Path) -> dict:
    plan = _read_json(plan_path, "GDK plan")
    result = _read_json(evidence_path, "GDK SDK result")
    if set(plan) != PLAN_FIELDS or set(result) != RESULT_FIELDS:
        raise ConflictError("GDK plan/result schema unexpected")
    for obj in (plan, result):
        for key, expected in (
            ("schema_version", 1), ("partner_center_selection", "GDK_GAME"),
            ("package_format", "MSIXVC2"),
            ("request_id", PINNED_SIGNAL_SPRINT_JOB["request_id"]),
            ("source_sha", PINNED_SIGNAL_SPRINT_JOB["source_sha"]),
            ("store_submitted", False),
        ):
            _expect(obj, key, expected)
        for key in ("cas_commit_sha", "factory_head_sha"):
            if type(obj[key]) is not str or not SHA40.fullmatch(obj[key]):
                raise ConflictError("GDK invalid " + key)
    for key, expected in (
        ("status", "GDK_SDK_PACK_PLAN_CHECK_ONLY"),
        ("gdk_sdk_validated", False), ("real_msixvc_built", False),
        ("public_release_requires_certification", True),
        ("msixvc2_preview_public_certification_blocked", False),
        ("next_stage", "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK"),
    ):
        _expect(plan, key, expected)
    for key, expected in (
        ("status", "GDK_SDK_PACK_EXECUTED"),
        ("sdk_executable", "makepkg.exe"), ("sdk_exit_code", 0),
    ):
        _expect(result, key, expected)
    for key in ("cas_commit_sha", "factory_head_sha", "package_version",
                "reviewed_display_name", "verified_receipt_sha256",
                "staging_files_sha256"):
        _expect(result, key, plan[key])
    if type(plan["verified_receipt_sha256"]) is not str or not SHA256.fullmatch(plan["verified_receipt_sha256"]):
        raise ConflictError("GDK preflight receipt SHA invalid")
    hashes = plan["staging_files_sha256"]
    if type(hashes) is not dict or len(hashes) != 6 or "SignalSprint.exe" not in hashes or any(
        type(v) is not str or not SHA256.fullmatch(v) for v in hashes.values()
    ):
        raise ConflictError("GDK staging hashes invalid")
    argv = plan["sdk_command_argv_not_executed"]
    if type(argv) is not list or len(argv) != 9 or not all(type(x) is str for x in argv):
        raise ConflictError("GDK SDK argv shape invalid")
    if argv[:4] != ["makepkg.exe", "pack", "/msixvc2", "/d"] or argv[5:7] != ["/pc", "/pd"] or argv[-1] != "/validationcritical" or not argv[4] or not argv[7]:
        raise ConflictError("GDK SDK argv unsafe")
    _expect(result, "sdk_command_argv", argv)
    version = result["sdk_version"]
    if type(version) is not str or not 5 <= len(version) <= 160 or any(c in version for c in "\r\n\x00"):
        raise ConflictError("GDK SDK version missing")
    filename = result["package_filename"]
    if type(filename) is not str or filename in ("", ".", "..") or Path(filename).name != filename or "/" in filename or "\\" in filename or not filename.lower().endswith((".msixvc", ".msixvc2")):
        raise ConflictError("GDK package filename invalid")
    for key in ("package_sha256", "validation_log_sha256"):
        if type(result[key]) is not str or not SHA256.fullmatch(result[key]):
            raise ConflictError("GDK invalid " + key)
    size = result["package_size_bytes"]
    if type(size) is not int or not 0 < size <= MAX_PACKAGE:
        raise ConflictError("GDK package size invalid")
    if package_dir.is_symlink() or not package_dir.is_dir():
        raise HoldError("GDK output directory missing or linked")
    directory = package_dir.resolve(strict=True)
    if Path(argv[7]).resolve(strict=True) != directory:
        raise ConflictError("GDK SDK output directory differs from plan")
    package = directory / filename
    if package.resolve(strict=True).parent != directory:
        raise ConflictError("GDK package escapes output directory")
    files = list(directory.iterdir())
    inventory = result["output_files_sha256"]
    if (type(inventory) is not dict or not 1 <= len(inventory) <= MAX_OUTPUT_FILES
            or set(inventory) != {entry.name for entry in files}):
        raise ConflictError("GDK output inventory incomplete or unexpected")
    if inventory.get(filename) != result["package_sha256"]:
        raise ConflictError("GDK package missing from output inventory")
    for entry in files:
        name = entry.name
        if (not name or name in (".", "..") or len(name) > 240
                or "/" in name or "\\" in name or any(ord(c) < 32 for c in name)
                or name.endswith((" ", "."))):
            raise ConflictError("GDK output filename unsafe")
        if entry.is_symlink() or not entry.is_file():
            raise ConflictError("GDK output contains linked or non-file evidence")
        digest = inventory[name]
        if type(digest) is not str or not SHA256.fullmatch(digest):
            raise ConflictError("GDK output inventory digest invalid")
        if name != filename:
            if entry.suffix.lower() not in SIDECAR_SUFFIXES:
                raise ConflictError("GDK output contains unreviewed sidecar")
            sidecar_sha, _ = _hash_file(entry, MAX_SIDECAR, "GDK SDK sidecar")
            if sidecar_sha != digest:
                raise ConflictError("GDK SDK sidecar bytes mismatch")
    if validation_log.is_symlink() or not validation_log.is_file():
        raise HoldError("GDK validation log missing or linked")
    for p in (plan_path, evidence_path, validation_log):
        if p.resolve(strict=True).parent == directory:
            raise ConflictError("GDK evidence must remain outside package directory")
    actual_sha, actual_size = _hash_file(package, MAX_PACKAGE, "GDK package")
    log_sha, _ = _hash_file(validation_log, MAX_LOG, "GDK validation log")
    if actual_sha != result["package_sha256"] or actual_size != size:
        raise ConflictError("GDK package bytes mismatch")
    if log_sha != result["validation_log_sha256"]:
        raise ConflictError("GDK validation log bytes mismatch")
    if {entry.name for entry in directory.iterdir()} != set(inventory):
        raise ConflictError("GDK output inventory changed during intake")
    return {
        "schema_version": 1,
        "status": "GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS",
        "partner_center_selection": "GDK_GAME", "package_format": "MSIXVC2",
        "request_id": plan["request_id"], "source_sha": plan["source_sha"],
        "cas_commit_sha": plan["cas_commit_sha"],
        "factory_head_sha": plan["factory_head_sha"],
        "package_version": plan["package_version"],
        "package_filename": filename, "package_sha256": actual_sha,
        "package_size_bytes": actual_size, "validation_log_sha256": log_sha,
        "output_files_sha256": dict(sorted(inventory.items())),
        "sdk_output_sidecar_count": len(inventory) - 1,
        "sdk_version_claim": version, "sdk_exit_code_claim": 0,
        "gdk_sdk_validation_independently_verified": False,
        "real_msix_pass": False, "e2e_pass": False, "store_submitted": False,
        "next_stage": "WINDOWS_GDK_SDK_LOG_REVIEW_INSTALL_GUI_QA",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pack-plan", "sdk-result-evidence", "package-dir", "validation-log"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = intake(args.pack_plan, args.sdk_result_evidence,
                       args.package_dir, args.validation_log)
    except (ConflictError, HoldError, OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msix_pass": False}))
        return 2
    print(json.dumps(value, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
