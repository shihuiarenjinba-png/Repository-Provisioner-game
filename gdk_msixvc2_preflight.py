"""Fail-closed Signal Sprint GDK MSIXVC2 staging preflight (no package build).

Re-derive the CAS and pinned artifact evidence instead of trusting a JSON
receipt. Refuse unreviewed files in the makepkg input directory. The returned
manifest is a check-only snapshot; the Windows GDK builder must rehash files
immediately before invoking the SDK, then independently validate the package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys

from gdk_build_intake import create_intake, EXE_SHA256
from gdk_microsoft_game_config import ASSETS, prepare_config
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

MAX_FILE_BYTES = {
    "SignalSprint.exe": 40_000_000,
    "MicrosoftGame.config": 1_000_000,
    **{name: 20_000_000 for name, _ in ASSETS.values()},
}


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_staging(root: Path, expected_xml: str) -> dict[str, str]:
    """Require exactly the reviewed executable, artwork and generated config."""
    if root.is_symlink() or not root.is_dir():
        raise HoldError("GDK MSIXVC2 staging directory missing or linked")
    try:
        entries = list(root.iterdir())
        actual = {entry.name for entry in entries}
        if len(entries) != len(MAX_FILE_BYTES) or actual != set(MAX_FILE_BYTES):
            raise ConflictError("GDK MSIXVC2 staging has missing or unreviewed payload")
        hashes = {}
        for entry in entries:
            mode = entry.lstat().st_mode
            if not stat.S_ISREG(mode) or entry.is_symlink():
                raise ConflictError("GDK MSIXVC2 staging contains linked or non-file payload")
            size = entry.stat().st_size
            if size <= 0 or size > MAX_FILE_BYTES[entry.name]:
                raise ConflictError("GDK MSIXVC2 staging payload size invalid")
            hashes[entry.name] = _digest(entry)
        config = root / "MicrosoftGame.config"
        if config.read_bytes() != expected_xml.encode("utf-8"):
            raise ConflictError("GDK MSIXVC2 staged MicrosoftGame.config differs from reviewed XML")
        if hashes["SignalSprint.exe"] != EXE_SHA256:
            raise ConflictError("GDK MSIXVC2 staged executable differs from immutable EXE")
        return dict(sorted(hashes.items()))
    except (OSError, UnicodeError) as exc:
        raise HoldError("GDK MSIXVC2 staging cannot be read safely") from exc


def create_preflight(
    factory_checkout: Path, artifact_zip: Path, cas_sha: str, build_sha: str,
    staging_dir: Path, package_version: str, reviewed_display_name: str,
) -> dict:
    intake = create_intake(factory_checkout, artifact_zip, cas_sha, build_sha)
    config = prepare_config(intake, staging_dir, package_version, reviewed_display_name)
    if (config.get("status") != "GDK_CONFIG_CHECK_ONLY"
            or config.get("partner_center_selection") != "GDK_GAME"
            or config.get("real_msixvc_built") is not False
            or config.get("gdk_sdk_validated") is not False
            or config.get("store_submitted") is not False):
        raise ConflictError("GDK config receipt incorrectly claims downstream success")
    hashes = verify_staging(staging_dir, config["microsoft_game_config_xml"])
    if hashes["MicrosoftGame.config"] != config["microsoft_game_config_sha256"]:
        raise ConflictError("GDK MSIXVC2 config SHA mismatch")
    return {
        "schema_version": 1,
        "status": "GDK_MSIXVC2_STAGING_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "packaging_family": "GDK",
        "package_format": "MSIXVC2",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "cas_commit_sha": cas_sha,
        "factory_head_sha": build_sha,
        "package_version": config["package_version"],
        "pinned_artifact_zip_sha256": intake["pinned_exe"]["artifact_zip_sha256"],
        "pinned_exe_sha256": EXE_SHA256,
        "staging_files_sha256": hashes,
        "next_stage": "WINDOWS_GDK_SDK_VALIDATE_THEN_MAKEPKG_MSIXVC2",
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-checkout", type=Path, required=True)
    parser.add_argument("--pinned-artifact-zip", type=Path, required=True)
    parser.add_argument("--cas-commit-sha", required=True)
    parser.add_argument("--build-head-sha", required=True)
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--reviewed-display-name", required=True)
    args = parser.parse_args(argv)
    try:
        result = create_preflight(
            args.factory_checkout, args.pinned_artifact_zip,
            args.cas_commit_sha, args.build_head_sha, args.staging_dir,
            args.package_version, args.reviewed_display_name,
        )
    except (ConflictError, HoldError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msixvc_built": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
