"""Signal Sprint new-lineage GDK post-CAS/MSIXVC2 CHECK-ONLY gate.

Distinct from the expired original lineage. This gate reuses the live GitHub
Factory adapter, reads actual Git CAS ancestry, and hashes staged files. Human
review JSON is NOT authenticated by its contents; no result authorizes CAS,
SDK execution, MSIXVC2 packaging, E2E, or Store submission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

from gdk_factory_lineage_adapter import check_live, SOURCE, OLD_REQUEST
from gdk_build_intake import APPROVED_PATH, APPROVED_FIELDS, _git, _json
from gdk_microsoft_game_config import ASSETS, _png_dimensions, _reviewed_version
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB,
)

RUN_ID = 41361263698
ARTIFACT_ID = 13105352227
NEW_REQUEST = OLD_REQUEST + "-reissue-sprint-41361263698-41361263698"
BUILD_HEAD = "a1af3448cd2edeae5bd54cbaca486a53fd991944"
OUTER_SHA = "843496682662e871fc6e1b5df83ace2c6b01ef314cfc466b5072290890b70a8f"
INNER_SHA = "46aff1ee7570459235c9e7ca7fb1faf6f494dc8100e62b6e132c6d07a6291b71"
EXE_SHA = "beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
REVIEW_KEYS = frozenset({
    "schema_version", "decision", "partner_center_selection", "package_format",
    "request_id", "source_sha", "exe_sha256", "package_version",
    "reviewed_display_name", "reviewed_by", "reviewed_at",
})
ASSET_KEYS = frozenset({
    "schema_version", "decision", "request_id", "source_sha", "exe_sha256",
    "assets_sha256", "reviewed_by", "reviewed_at",
})


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ConflictError(code)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def regular(path: Path, limit: int) -> None:
    try:
        mode = path.lstat().st_mode
        require(stat.S_ISREG(mode) and not path.is_symlink()
                and 0 < path.stat().st_size <= limit, "UNSAFE_OR_MISSING_FILE")
    except FileNotFoundError as exc:
        raise HoldError("REQUIRED_FILE_MISSING") from exc


def read_review(path: Path, keys: frozenset[str]) -> tuple[dict, str]:
    regular(path, 65536)
    raw = path.read_bytes()
    require(len(raw) <= 65536, "REVIEW_CHANGED_WHILE_READING")
    record = _json(raw)
    require(set(record) == keys and type(record.get("schema_version")) is int
            and record["schema_version"] == 1 and record.get("decision") == "APPROVED",
            "REVIEW_SCHEMA_OR_DECISION_INVALID")
    require(record.get("request_id") == NEW_REQUEST and
            record.get("source_sha") == SOURCE and
            record.get("exe_sha256") == EXE_SHA, "REVIEW_LINEAGE_MISMATCH")
    # No self-declared 'authenticated' flag can establish review authority.
    require(type(record.get("reviewed_by")) is str and
            len(record["reviewed_by"].strip()) >= 3 and
            type(record.get("reviewed_at")) is str and
            len(record["reviewed_at"]) >= 20, "REVIEW_PROVENANCE_MISSING")
    return record, hashlib.sha256(raw).hexdigest()


def verify_cas_git(checkout: Path, cas_sha: str, build_sha: str) -> str:
    require(checkout.is_dir() and not checkout.is_symlink(), "CAS_CHECKOUT_INVALID")
    require(type(cas_sha) is str and HEX40.fullmatch(cas_sha) is not None and
            type(build_sha) is str and HEX40.fullmatch(build_sha) is not None and
            cas_sha != SOURCE and build_sha != SOURCE, "CAS_SHA_INVALID")
    require(_git(checkout, "rev-parse", "HEAD").decode() == build_sha,
            "BUILD_HEAD_MISMATCH")
    require(_git(checkout, "rev-parse", cas_sha + "^").decode() == SOURCE,
            "CAS_NOT_DIRECTLY_BASED_ON_SOURCE")
    _git(checkout, "merge-base", "--is-ancestor", cas_sha, build_sha)
    require(_git(checkout, "diff-tree", "--no-commit-id", "--name-only", "-r",
                 cas_sha).decode() == APPROVED_PATH, "CAS_CHANGED_UNAPPROVED_FILES")
    require(not _git(checkout, "status", "--porcelain=v1", "--untracked-files=all"),
            "BUILD_CHECKOUT_DIRTY")
    branch = _git(checkout, "symbolic-ref", "--quiet", "--short", "HEAD").decode()
    require(re.fullmatch(r"codex/game-signal-sprint-gdk-build-[a-z0-9-]+", branch)
            is not None, "DEDICATED_BUILD_BRANCH_REQUIRED")
    require(not _git(checkout, "diff", "--name-only", cas_sha, build_sha,
                     "--", "products/signal-sprint"), "BUILD_MUTATED_PRODUCT_TREE")
    approved = _json(_git(checkout, "show", cas_sha + ":" + APPROVED_PATH))
    require(set(approved) == APPROVED_FIELDS, "CAS_IDENTITY_SCHEMA_MISMATCH")
    require(_json(_git(checkout, "show", build_sha + ":" + APPROVED_PATH)) == approved,
            "BUILD_CHANGED_APPROVED_IDENTITY")
    expected = {
        "request_id": NEW_REQUEST, "source_sha": SOURCE,
        "verified_source_sha": SOURCE, "package_sha256": EXE_SHA,
        "reviewed": True, "packaging_family": "GDK",
        "source": "partner_center_user_provided",
        "identity_source": "USER_PROVIDED_PARTNER_CENTER",
    }
    expected.update(PINNED_SIGNAL_SPRINT_GDK_IDENTITY)
    for key in ("source_repository", "source_branch", "source_factory", "slug", "product_type"):
        expected[key] = PINNED_SIGNAL_SPRINT_JOB[key]
    for key, value in expected.items():
        require(type(approved.get(key)) is type(value) and approved[key] == value,
                "CAS_IDENTITY_OR_LINEAGE_MISMATCH:" + key)
    blob = _git(checkout, "rev-parse", cas_sha + ":" + APPROVED_PATH).decode()
    require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", blob) is not None,
            "CAS_IDENTITY_BLOB_INVALID")
    return blob


def verify_staging(root: Path, exe_sha: str, version: str, display: str,
                   assets: dict) -> dict[str, str]:
    require(root.is_dir() and not root.is_symlink(), "STAGING_DIRECTORY_INVALID")
    expected_files = {"SignalSprint.exe", "MicrosoftGame.config"} | {
        name for name, _ in ASSETS.values()
    }
    entries = list(root.iterdir())
    require(len(entries) == len(expected_files) and
            {entry.name for entry in entries} == expected_files,
            "STAGING_UNREVIEWED_OR_MISSING_FILE")
    hashes = {}
    for path in entries:
        regular(path, 40_000_000 if path.name == "SignalSprint.exe" else 20_000_000)
        hashes[path.name] = digest(path)
    require(hashes["SignalSprint.exe"] == exe_sha, "STAGED_EXE_SHA_MISMATCH")
    for _, (name, dimensions) in ASSETS.items():
        require(_png_dimensions(root / name) == dimensions,
                "STAGED_PNG_DIMENSIONS_INVALID:" + name)
    require(type(assets) is dict and set(assets) == expected_files - {
        "SignalSprint.exe", "MicrosoftGame.config"
    } and all(assets[k] == hashes[k] for k in assets),
            "ASSET_REVIEW_DIGEST_MISMATCH")
    try:
        xml = ET.fromstring((root / "MicrosoftGame.config").read_bytes())
        identity = xml.find("Identity")
        executable = xml.find("ExecutableList/Executable")
        visuals = xml.find("ShellVisuals")
    except (ET.ParseError, OSError) as exc:
        raise ConflictError("MICROSOFTGAME_CONFIG_INVALID") from exc
    expected = PINNED_SIGNAL_SPRINT_GDK_IDENTITY
    require(xml.tag == "Game" and identity is not None and executable is not None
            and visuals is not None, "MICROSOFTGAME_CONFIG_STRUCTURE_INVALID")
    require(identity.get("Name") == expected["name"] and
            identity.get("Publisher") == expected["publisher"] and
            identity.get("Version") == version and
            xml.findtext("StoreId") == expected["store_id"] and
            xml.findtext("TitleId") == expected["xbox_title_id"] and
            xml.findtext("MSAAppId") == expected["msa_app_id"] and
            executable.get("Name") == "SignalSprint.exe" and
            visuals.get("DefaultDisplayName") == display and
            visuals.get("PublisherDisplayName") == expected["publisher_display_name"],
            "MICROSOFTGAME_CONFIG_IDENTITY_VERSION_MISMATCH")
    for key, (name, _) in ASSETS.items():
        require(visuals.get(key) == name, "MICROSOFTGAME_CONFIG_ASSET_MISMATCH")
    return dict(sorted(hashes.items()))


def check_only(checkout: Path, outer_zip: Path, cas_sha: str, build_sha: str,
               staging: Path, version_review: Path, asset_review: Path) -> dict:
    base = {
        "schema_version": 1, "partner_center_selection": "GDK_GAME",
        "package_format": "MSIXVC2", "source_sha": SOURCE,
        "original_request_id": OLD_REQUEST, "new_request_id": NEW_REQUEST,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "cas_return_pass": False, "approval_authenticity_verified": False,
        "version_review_authenticity_verified": False,
        "asset_review_authenticity_verified": False,
        "gdk_sdk_validated": False, "real_msixvc_built": False,
        "e2e_pass": False, "store_submitted": False,
        "ready_for_sdk": False, "status": "NEW_LINEAGE_GDK_POST_CAS_HOLD",
    }
    try:
        root = checkout.resolve(strict=True)
        for path in (outer_zip, staging, version_review, asset_review):
            resolved = path.resolve(strict=False)
            require(resolved != root and root not in resolved.parents,
                    "EVIDENCE_OR_STAGING_INSIDE_FACTORY_CHECKOUT")
        live = check_live(outer_zip, RUN_ID, ARTIFACT_ID)
        require(live.get("status") == "FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY",
                "LIVE_GITHUB_EVIDENCE_NOT_VERIFIED")
        fixed = {
            "new_request_id": NEW_REQUEST, "source_sha": SOURCE,
            "build_head_sha": BUILD_HEAD, "github_run_id": RUN_ID,
            "github_artifact_id": ARTIFACT_ID,
            "outer_github_zip_sha256": OUTER_SHA,
            "inner_factory_zip_sha256": INNER_SHA, "exe_sha256": EXE_SHA,
            "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        }
        require(all(type(live.get(k)) is type(v) and live[k] == v
                    for k, v in fixed.items()), "LIVE_LINEAGE_MISMATCH")
        require(all(live.get(k) is False for k in
                    ("ready_for_cas", "cas_return_pass", "real_msixvc_built",
                     "store_submitted")), "LIVE_RECEIPT_UNPROVEN_PROGRESS")
        blob = verify_cas_git(checkout, cas_sha, build_sha)
        version, version_sha = read_review(version_review, REVIEW_KEYS)
        assets, assets_sha = read_review(asset_review, ASSET_KEYS)
        require(version.get("partner_center_selection") == "GDK_GAME" and
                version.get("package_format") == "MSIXVC2",
                "VERSION_REVIEW_ROUTE_MISMATCH")
        package_version = _reviewed_version(version.get("package_version"))
        display = version.get("reviewed_display_name")
        require(type(display) is str and display.strip() == display
                and 0 < len(display) <= 100, "REVIEWED_DISPLAY_NAME_INVALID")
        hashes = verify_staging(staging, EXE_SHA, package_version, display,
                                assets.get("assets_sha256"))
        base.update({
            "status": "NEW_LINEAGE_GDK_POST_CAS_CHECK_ONLY",
            "reason": "INDEPENDENT_REVIEW_AUTHENTICATION_AND_GDK_SDK_VALIDATION_REQUIRED",
            "cas_commit_sha": cas_sha, "factory_head_sha": build_sha,
            "approved_identity_blob_sha": blob,
            "new_lineage_exe_sha256": EXE_SHA,
            "package_version": package_version,
            "staging_files_sha256": hashes,
            "version_review_sha256": version_sha,
            "asset_review_sha256": assets_sha,
        })
    except (ConflictError, HoldError, OSError, UnicodeError, ValueError, TypeError,
            KeyError, RuntimeError) as exc:
        base["reason"] = str(exc)
    return base


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--factory-checkout", type=Path, required=True)
    p.add_argument("--outer-artifact-zip", type=Path, required=True)
    p.add_argument("--cas-commit-sha", required=True)
    p.add_argument("--build-head-sha", required=True)
    p.add_argument("--staging-dir", type=Path, required=True)
    p.add_argument("--version-review", type=Path, required=True)
    p.add_argument("--asset-review", type=Path, required=True)
    a = p.parse_args(argv)
    result = check_only(a.factory_checkout, a.outer_artifact_zip,
                        a.cas_commit_sha, a.build_head_sha, a.staging_dir,
                        a.version_review, a.asset_review)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2  # check-only is never authorization to build


if __name__ == "__main__":
    sys.exit(main())
