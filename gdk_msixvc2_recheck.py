"""Re-derive Signal Sprint GDK staging evidence immediately before makepkg.

This is a read-only, fail-closed second check. A saved preflight receipt alone
cannot authorize packaging: re-run actual Git CAS, pinned ZIP, XML and staging
checks using the current checkout and compare every field to the saved receipt.
No GDK SDK invocation, build, CAS, Store operation or source modification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys

from gdk_msixvc2_preflight import create_preflight
from package_identity_provisioner import ConflictError, HoldError, _unique_json_object

MAX_RECEIPT_BYTES = 1_000_000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def read_receipt(path: Path) -> tuple[dict, bytes]:
    try:
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode) or path.is_symlink():
            raise ConflictError("GDK receipt is not a regular unlinked file")
        size = path.stat().st_size
        if not 0 < size <= MAX_RECEIPT_BYTES:
            raise ConflictError("GDK receipt size invalid")
        raw = path.read_bytes()
        if len(raw) != size:
            raise ConflictError("GDK receipt changed while reading")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ConflictError("GDK receipt unreadable, malformed or ambiguous") from exc
    if not isinstance(data, dict):
        raise ConflictError("GDK receipt must be a JSON object")
    return data, raw


def recheck(
    factory_checkout: Path, artifact_zip: Path, cas_sha: str, build_sha: str,
    staging_dir: Path, package_version: str, reviewed_display_name: str,
    receipt_path: Path,
) -> dict:
    # Receipt never supplies trusted paths, refs, versions or display names.
    # These are independently provided by the caller and re-verified below.
    previous, raw = read_receipt(receipt_path)
    current = create_preflight(factory_checkout, artifact_zip, cas_sha, build_sha,
                               staging_dir, package_version, reviewed_display_name)
    if _canonical(previous) != _canonical(current):
        raise ConflictError("GDK preflight receipt differs from freshly verified CAS/artifact/staging")
    if (current.get("status") != "GDK_MSIXVC2_STAGING_CHECK_ONLY"
            or current.get("partner_center_selection") != "GDK_GAME"
            or current.get("package_format") != "MSIXVC2"
            or current.get("gdk_sdk_validated") is not False
            or current.get("real_msixvc_built") is not False
            or current.get("store_submitted") is not False):
        raise ConflictError("GDK receipt makes invalid downstream claims")
    return {
        "schema_version": 1,
        "status": "GDK_MSIXVC2_RECHECK_PASS",
        "partner_center_selection": "GDK_GAME",
        "request_id": current["request_id"],
        "source_sha": current["source_sha"],
        "cas_commit_sha": current["cas_commit_sha"],
        "factory_head_sha": current["factory_head_sha"],
        "verified_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "staging_files_sha256": current["staging_files_sha256"],
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
    parser.add_argument("--preflight-receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = recheck(
            args.factory_checkout, args.pinned_artifact_zip,
            args.cas_commit_sha, args.build_head_sha, args.staging_dir,
            args.package_version, args.reviewed_display_name, args.preflight_receipt,
        )
    except (ConflictError, HoldError, OSError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msixvc_built": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
