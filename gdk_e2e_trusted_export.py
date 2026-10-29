"""Signal Sprint: independently anchored GDK prebuild -> E2E byte handoff.

This is a *check-only* trust-chain wrapper. The separate SHA-256 anchor MUST
come from a trusted channel outside the SDK output and transferred directory.
No SDK execution, CAS, install, Windows-all-auto queue or Store submission.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import sys

from gdk_e2e_handoff import export_handoff
from gdk_e2e_handoff_verify import verify_handoff
from gdk_sdk_result_intake import MAX_JSON, MAX_LOG, MAX_PACKAGE, MAX_SIDECAR, MAX_OUTPUT_FILES, SHA256, _hash_file
from gdk_sdk_trusted_intake import trusted_intake
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

BOUND = ("request_id", "source_sha", "cas_commit_sha", "factory_head_sha",
         "package_version", "package_sha256", "package_size_bytes",
         "validation_log_sha256", "sdk_version_claim", "sdk_exit_code_claim")
FALSE_FLAGS = ("real_msix_pass", "e2e_pass", "store_submitted",
               "gdk_sdk_validation_independently_verified")


def _require_equal(left: dict, right: dict, key: str) -> None:
    if key not in left or key not in right or type(left[key]) is not type(right[key]) or left[key] != right[key]:
        raise ConflictError("GDK trusted E2E mismatch: " + key)


def _require_inventory_continuity(trusted: dict, manifest: dict) -> None:
    """Bind SDK sidecars to the *first* independently anchored intake result.

    Rechecking only the package/log permits an SDK sidecar to change between
    trusted_intake and export_handoff while both independent checks pass.
    The original SDK inventory is authoritative, not the later exporter.
    """
    original = trusted.get("package_filename")
    inventory = trusted.get("output_files_sha256")
    transferred = manifest.get("sdk_sidecars_sha256")
    if (type(original) is not str or not original or type(inventory) is not dict
            or type(transferred) is not dict or not inventory):
        raise ConflictError("GDK trusted SDK output inventory missing")
    if manifest.get("original_sdk_filename") != original:
        raise ConflictError("GDK original SDK filename changed during export")
    if inventory.get(original) != trusted.get("package_sha256"):
        raise ConflictError("GDK trusted SDK package inventory mismatch")
    expected_sidecars = {
        "sdk-sidecar-" + name: digest
        for name, digest in inventory.items() if name != original
    }
    if transferred != expected_sidecars:
        raise ConflictError("GDK SDK sidecar inventory changed during export")



def _verify_source_inventory(trusted: dict, package_dir: Path) -> None:
    """Rehash the first trusted SDK inventory immediately before exporting.

    A sidecar may be modified after trusted_intake returns and before the
    exporter begins. Reject before creating an E2E handoff destination.
    The later exporter independently rehashes during the actual copy.
    """
    inventory = trusted.get("output_files_sha256")
    original = trusted.get("package_filename")
    if (type(inventory) is not dict or not inventory
            or len(inventory) > MAX_OUTPUT_FILES or type(original) is not str
            or original not in inventory):
        raise ConflictError("GDK original SDK inventory missing")
    if package_dir.is_symlink() or not package_dir.is_dir():
        raise ConflictError("GDK original SDK output directory missing or linked")
    files = list(package_dir.iterdir())
    if len(files) != len(inventory) or {p.name for p in files} != set(inventory):
        raise ConflictError("GDK original SDK output inventory changed before export")
    for path in files:
        if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
            raise ConflictError("GDK original SDK output contains linked or non-regular file")
        maximum = MAX_PACKAGE if path.name == original else MAX_SIDECAR
        expected = inventory[path.name]
        if type(expected) is not str or not SHA256.fullmatch(expected):
            raise ConflictError("GDK original SDK inventory digest invalid")
        if _hash_file(path, maximum, "GDK original SDK output")[0] != expected:
            raise ConflictError("GDK original SDK output bytes changed before export")
    if {p.name for p in package_dir.iterdir()} != set(inventory):
        raise ConflictError("GDK original SDK output inventory changed during precheck")


def export_trusted(handoff_path: Path, independent_handoff_sha256: str,
                   plan_path: Path, evidence_path: Path, package_dir: Path,
                   validation_log: Path, output_dir: Path) -> dict:
    """Fail closed unless both trusted prebuild and transferred bytes agree."""
    if type(independent_handoff_sha256) is not str or not SHA256.fullmatch(independent_handoff_sha256):
        raise HoldError("independent prebuild handoff SHA-256 required")
    anchor_before, _ = _hash_file(handoff_path, MAX_JSON, "trusted prebuild handoff")
    if anchor_before != independent_handoff_sha256:
        raise ConflictError("independent prebuild handoff SHA-256 mismatch")
    plan_sha, _ = _hash_file(plan_path, MAX_JSON, "GDK pack plan")
    evidence_sha, _ = _hash_file(evidence_path, MAX_JSON, "GDK SDK evidence")
    log_sha, _ = _hash_file(validation_log, MAX_LOG, "GDK SDK validation log")

    # This independently checks the pinned EXE, post-CAS identity, SDK pack
    # plan, actual package/log bytes and separately trusted prebuild anchor.
    trusted = trusted_intake(handoff_path, independent_handoff_sha256, plan_path,
                             evidence_path, package_dir, validation_log)
    if trusted.get("status") != "GDK_TRUSTED_PREBUILD_TO_PACKAGE_BYTES_CHECK_PASS":
        raise ConflictError("GDK trusted SDK intake has not passed")
    if trusted.get("prebuild_trust_chain_verified") is not True:
        raise ConflictError("GDK prebuild trust chain not verified")
    if trusted.get("partner_center_selection") != "GDK_GAME":
        raise ConflictError("GDK Partner Center route mismatch")
    if trusted.get("request_id") != PINNED_SIGNAL_SPRINT_JOB["request_id"]:
        raise ConflictError("GDK request mismatch")
    for key in FALSE_FLAGS:
        if trusted.get(key) is not False:
            raise ConflictError("unearned GDK SDK approval: " + key)

    _verify_source_inventory(trusted, package_dir)

    # The existing exporter rehashes every source and copies only verified
    # package/log/sidecar bytes to a new, never-overwritten directory.
    manifest = export_handoff(plan_path, evidence_path, package_dir,
                              validation_log, output_dir)
    for key in BOUND:
        _require_equal(trusted, manifest, key)
    _require_inventory_continuity(trusted, manifest)
    if manifest.get("sdk_pack_plan_sha256") != plan_sha or manifest.get("sdk_result_evidence_sha256") != evidence_sha:
        raise ConflictError("GDK exported evidence SHA mismatch")
    if manifest.get("partner_center_selection") != "GDK_GAME" or manifest.get("package_format") != "MSIXVC2":
        raise ConflictError("GDK exported routing mismatch")
    for key in FALSE_FLAGS:
        if manifest.get(key) is not False:
            raise ConflictError("unearned GDK transfer approval: " + key)

    manifest_sha, _ = _hash_file(output_dir / "handoff.json", MAX_JSON, "GDK E2E manifest")
    received = verify_handoff(output_dir, manifest_sha)
    for key in ("request_id", "source_sha", "cas_commit_sha", "factory_head_sha",
                "package_sha256", "validation_log_sha256"):
        _require_equal(trusted, received, key)
    if received.get("manifest_sha256") != manifest_sha or received.get("independent_manifest_anchor_matched") is not True:
        raise ConflictError("GDK local receiver digest mismatch")
    if received.get("sdk_sidecars_sha256") != manifest.get("sdk_sidecars_sha256"):
        raise ConflictError("GDK sidecar inventory mismatch")
    for key in FALSE_FLAGS:
        if received.get(key) is not False:
            raise ConflictError("unearned GDK receiver approval: " + key)

    # Fail closed on a changed trust anchor or evidence during export. The
    # directory, if already exported, must not be consumed on any failure.
    for path, maximum, expected, label in (
        (handoff_path, MAX_JSON, anchor_before, "trusted prebuild handoff"),
        (plan_path, MAX_JSON, plan_sha, "GDK pack plan"),
        (evidence_path, MAX_JSON, evidence_sha, "GDK SDK evidence"),
        (validation_log, MAX_LOG, log_sha, "GDK SDK validation log"),
    ):
        if _hash_file(path, maximum, label)[0] != expected:
            raise ConflictError(label + " changed during trusted E2E export")
    return {
        "status": "GDK_TRUSTED_E2E_HANDOFF_CHECK_ONLY_PASS",
        "partner_center_selection": "GDK_GAME",
        "request_id": trusted["request_id"],
        "source_sha": trusted["source_sha"],
        "cas_commit_sha": trusted["cas_commit_sha"],
        "factory_head_sha": trusted["factory_head_sha"],
        "package_sha256": trusted["package_sha256"],
        "validation_log_sha256": trusted["validation_log_sha256"],
        "trusted_prebuild_handoff_sha256": independent_handoff_sha256,
        "handoff_manifest_sha256": manifest_sha,
        "sdk_sidecars_sha256": received["sdk_sidecars_sha256"],
        "prebuild_trust_chain_verified": True,
        "local_transfer_bytes_verified": True,
        "gdk_sdk_validation_independently_verified": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
        "next_stage": "WINDOWS_E2E_INDEPENDENT_GDK_VALIDATION_INSTALL_GUI_QA",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk-handoff", "pack-plan", "sdk-result-evidence",
                 "package-dir", "validation-log", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--trusted-handoff-sha256", required=True,
                        help="Independent trusted prebuild SHA, NOT from transferred files")
    args = parser.parse_args(argv)
    try:
        result = export_trusted(args.sdk_handoff, args.trusted_handoff_sha256,
                                args.pack_plan, args.sdk_result_evidence,
                                args.package_dir, args.validation_log, args.output_dir)
    except (ConflictError, HoldError, OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msix_pass": False,
                          "e2e_pass": False}))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
