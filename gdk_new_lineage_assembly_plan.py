"""Deterministic Signal Sprint NEW-lineage GDK staging assembly PLAN, read-only.

Produces a manifest of intended files and hashes, never stages files. The
authenticated CAS/reviewer/SDK authorities are separate gates. This tool
cannot authorize CAS, package construction, E2E, or Store submission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import xml.etree.ElementTree as ET

from gdk_factory_lineage_adapter import check_live, members, MAX_OUTER, MAX_INNER
from gdk_microsoft_game_config import ASSETS, _png_dimensions, _reviewed_version, _reviewed_display
from gdk_new_lineage_post_cas_gate import (
    ARTIFACT_ID, BUILD_HEAD, EXE_SHA, INNER_SHA, NEW_REQUEST, OLD_REQUEST,
    OUTER_SHA, RUN_ID, SOURCE, ASSET_KEYS, REVIEW_KEYS, read_review,
    verify_cas_git, require,
)
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY as ID,
)

MAX_ASSET = 20_000_000
ASSET_NAMES = frozenset(name for name, _ in ASSETS.values())


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_file(path: Path, limit: int) -> bytes:
    try:
        mode = path.lstat().st_mode
        require(stat.S_ISREG(mode) and not path.is_symlink(), "INPUT_NOT_REGULAR")
        size = path.stat().st_size
        require(0 < size <= limit, "INPUT_SIZE_INVALID")
        data = path.read_bytes()
        require(len(data) == size, "INPUT_CHANGED_WHILE_READING")
        return data
    except FileNotFoundError as exc:
        raise HoldError("REQUIRED_INPUT_MISSING") from exc


def external(checkout: Path, path: Path) -> None:
    root = checkout.resolve(strict=True)
    target = path.resolve(strict=False)
    require(target != root and root not in target.parents,
            "INPUT_OR_TARGET_INSIDE_FACTORY_CHECKOUT")


def pinned_exe_from_outer(outer_zip: Path) -> tuple[int, str]:
    """Rehash the actual inner EXE independently; never write/extract to disk."""
    raw = safe_file(outer_zip, MAX_OUTER)
    require(sha(raw) == OUTER_SHA, "OUTER_ARTIFACT_DIGEST_MISMATCH")
    outer = members(raw, {"new-lineage.zip", "lineage-receipt.json"}, MAX_OUTER)
    inner = outer["new-lineage.zip"]
    require(sha(inner) == INNER_SHA, "INNER_ARTIFACT_DIGEST_MISMATCH")
    files = members(inner, {"SignalSprint.exe", "provenance.json",
                            "provisioner-request.json"}, MAX_INNER)
    exe = files["SignalSprint.exe"]
    require(len(exe) >= 100_000 and exe.startswith(b"MZ") and
            sha(exe) == EXE_SHA, "NEW_LINEAGE_EXE_DIGEST_MISMATCH")
    return len(exe), sha(exe)


def config_xml(version: str, display: str) -> bytes:
    """Stable XML rendering consistent with the existing GDK config layout."""
    game = ET.Element("Game", {"configVersion": "1"})
    ET.SubElement(game, "Identity", {"Name": ID["name"],
                                    "Publisher": ID["publisher"], "Version": version})
    ET.SubElement(game, "StoreId").text = ID["store_id"]
    ET.SubElement(game, "MSAAppId").text = ID["msa_app_id"]
    ET.SubElement(game, "TitleId").text = ID["xbox_title_id"]
    ET.SubElement(ET.SubElement(game, "Resources"), "Resource", {"Language": "en-US"})
    ET.SubElement(ET.SubElement(game, "ExecutableList"), "Executable",
                  {"Name": "SignalSprint.exe", "Id": "Game",
                   "TargetDeviceFamily": "PC", "Architecture": "x64"})
    ET.SubElement(game, "ShellVisuals", {
        "DefaultDisplayName": display, "PublisherDisplayName": ID["publisher_display_name"],
        "StoreLogo": ASSETS["StoreLogo"][0],
        "Square150x150Logo": ASSETS["Square150x150Logo"][0],
        "Square44x44Logo": ASSETS["Square44x44Logo"][0],
        "SplashScreenImage": ASSETS["SplashScreenImage"][0],
        "Description": display, "BackgroundColor": "#000040",
    })
    ET.SubElement(ET.SubElement(game, "DesktopRegistration"),
                  "ProcessorArchitecture").text = "x64"
    raw = b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(
        game, encoding="utf-8") + b"\n"
    parsed = ET.fromstring(raw)
    require(parsed.findtext("TitleId") == ID["xbox_title_id"] and
            parsed.findtext("MSAAppId") == ID["msa_app_id"] and
            parsed.findtext("StoreId") == ID["store_id"] and
            parsed.find("Identity").get("Version") == version,
            "CONFIG_IDENTITY_OR_VERSION_MISMATCH")
    return raw


def assemble_plan(checkout: Path, outer_zip: Path, cas_sha: str, build_sha: str,
                  asset_dir: Path, version_review: Path, asset_review: Path,
                  staging_target: Path) -> dict:
    base = {
        "schema_version": 1, "status": "NEW_LINEAGE_GDK_ASSEMBLY_HOLD",
        "partner_center_selection": "GDK_GAME", "package_format": "MSIXVC2",
        "source_sha": SOURCE, "original_request_id": OLD_REQUEST,
        "new_request_id": NEW_REQUEST,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "cas_return_pass": False, "review_authenticity_verified": False,
        "ready_for_sdk": False, "gdk_sdk_validated": False,
        "real_msixvc_built": False, "e2e_pass": False, "store_submitted": False,
        "staging_created": False,
    }
    try:
        require(checkout.is_dir() and not checkout.is_symlink(),
                "FACTORY_CHECKOUT_MISSING")
        for path in (outer_zip, asset_dir, version_review, asset_review,
                     staging_target):
            external(checkout, path)
        require(not staging_target.exists() and not staging_target.is_symlink(),
                "STAGING_TARGET_ALREADY_EXISTS")
        require(staging_target.parent.is_dir() and
                not staging_target.parent.is_symlink(),
                "STAGING_PARENT_MISSING_OR_LINKED")
        require(asset_dir.is_dir() and not asset_dir.is_symlink(),
                "ASSET_DIRECTORY_MISSING_OR_LINKED")
        require(asset_dir.resolve() != staging_target.resolve(strict=False),
                "ASSET_SOURCE_TARGET_COLLISION")
        require({p.name for p in asset_dir.iterdir()} == ASSET_NAMES,
                "ASSET_DIRECTORY_CONTENTS_MISMATCH")
        live = check_live(outer_zip, RUN_ID, ARTIFACT_ID)
        require(live.get("status") == "FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY",
                "GITHUB_ARTIFACT_NOT_VERIFIED")
        fixed = {
            "new_request_id": NEW_REQUEST, "source_sha": SOURCE,
            "build_head_sha": BUILD_HEAD, "github_run_id": RUN_ID,
            "github_artifact_id": ARTIFACT_ID,
            "outer_github_zip_sha256": OUTER_SHA,
            "inner_factory_zip_sha256": INNER_SHA, "exe_sha256": EXE_SHA,
            "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        }
        require(all(type(live.get(k)) is type(v) and live[k] == v
                    for k, v in fixed.items()), "FACTORY_LINEAGE_MISMATCH")
        require(all(live.get(k) is False for k in
                    ("ready_for_cas", "cas_return_pass", "real_msixvc_built",
                     "store_submitted")), "FACTORY_UNPROVEN_PROGRESS")
        blob = verify_cas_git(checkout, cas_sha, build_sha)
        version, version_sha = read_review(version_review, REVIEW_KEYS)
        assets, assets_sha = read_review(asset_review, ASSET_KEYS)
        require(version.get("partner_center_selection") == "GDK_GAME" and
                version.get("package_format") == "MSIXVC2",
                "VERSION_ROUTE_MISMATCH")
        package_version = _reviewed_version(version.get("package_version"))
        display = _reviewed_display(version.get("reviewed_display_name"))
        reviewed_hashes = assets.get("assets_sha256")
        require(type(reviewed_hashes) is dict and
                set(reviewed_hashes) == ASSET_NAMES,
                "ASSET_APPROVAL_INCOMPLETE")
        file_plan = []
        for name in sorted(ASSET_NAMES):
            path = asset_dir / name
            data = safe_file(path, MAX_ASSET)
            dimensions = next(dim for asset_name, dim in ASSETS.values()
                              if asset_name == name)
            require(_png_dimensions(path) == dimensions,
                    "ASSET_DIMENSIONS_INVALID:" + name)
            actual = sha(data)
            require(type(reviewed_hashes[name]) is str and
                    reviewed_hashes[name] == actual,
                    "ASSET_DIGEST_MISMATCH:" + name)
            file_plan.append({"destination": name, "source_kind": "reviewed_asset",
                              "sha256": actual, "size_bytes": len(data)})
        exe_size, exe_hash = pinned_exe_from_outer(outer_zip)
        file_plan.append({"destination": "SignalSprint.exe",
                          "source_kind": "factory_new_lineage_inner_zip",
                          "sha256": exe_hash, "size_bytes": exe_size})
        xml = config_xml(package_version, display)
        file_plan.append({"destination": "MicrosoftGame.config",
                          "source_kind": "deterministic_generated_config",
                          "sha256": sha(xml), "size_bytes": len(xml)})
        file_plan.sort(key=lambda item: item["destination"])
        require(len(file_plan) == 6 and len({f["destination"] for f in file_plan}) == 6,
                "ASSEMBLY_FILE_SET_INVALID")
        base.update({
            "status": "NEW_LINEAGE_GDK_ASSEMBLY_PLAN_CHECK_ONLY",
            "reason": "INDEPENDENT_CAS_AND_REVIEW_AUTHENTICATION_SDK_VALIDATION_REQUIRED",
            "cas_commit_sha": cas_sha, "factory_head_sha": build_sha,
            "approved_identity_blob_sha": blob, "package_version": package_version,
            "reviewed_display_name": display,
            "xbox_title_id": ID["xbox_title_id"], "xbox_scid": ID["xbox_scid"],
            "msa_app_id": ID["msa_app_id"], "exe_sha256": EXE_SHA,
            "github_run_id": RUN_ID, "github_artifact_id": ARTIFACT_ID,
            "version_review_sha256": version_sha,
            "asset_review_sha256": assets_sha, "files": file_plan,
            "config_xml_utf8": xml.decode("utf-8"),
        })
    except (ConflictError, HoldError, OSError, ValueError, KeyError, TypeError,
            RuntimeError, UnicodeError) as exc:
        base["reason"] = str(exc)
    return base


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--factory-checkout", type=Path, required=True)
    p.add_argument("--outer-artifact-zip", type=Path, required=True)
    p.add_argument("--cas-commit-sha", required=True)
    p.add_argument("--build-head-sha", required=True)
    p.add_argument("--asset-dir", type=Path, required=True)
    p.add_argument("--version-review", type=Path, required=True)
    p.add_argument("--asset-review", type=Path, required=True)
    p.add_argument("--staging-target", type=Path, required=True)
    a = p.parse_args(argv)
    result = assemble_plan(a.factory_checkout, a.outer_artifact_zip,
                           a.cas_commit_sha, a.build_head_sha, a.asset_dir,
                           a.version_review, a.asset_review, a.staging_target)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 2  # Never an authorization or staging operation.


if __name__ == "__main__":
    sys.exit(main())
