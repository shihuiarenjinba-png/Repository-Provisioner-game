"""Read-only dedicated build-branch gate for the pinned Signal Sprint GDK game.

Run after an explicitly authorized Identity CAS, on a dedicated post-CAS
build checkout. This is NOT a GDK SDK, MSIXVC2, install or Store validation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from gdk_build_intake import APPROVED_PATH, _git, verify_cas_checkout
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

BRANCH_PATTERN = re.compile(r"codex/game-signal-sprint-gdk-build-[a-z0-9][a-z0-9-]{0,79}\Z")


def verify_build_branch(factory_checkout: Path, cas_sha: str, build_sha: str) -> dict:
    # Independently revalidate actual CAS ancestry and committed Identity bytes.
    # Never trust a previous JSON receipt as authorization.
    verify_cas_checkout(factory_checkout, cas_sha, build_sha)

    branch = _git(factory_checkout, "symbolic-ref", "--quiet", "--short", "HEAD").decode("utf-8")
    if not BRANCH_PATTERN.fullmatch(branch):
        raise ConflictError("GDK build must use a named dedicated post-CAS branch")

    # The checkout itself must not contain uncommitted/untracked source changes.
    # Staging, artifacts and receipts belong OUTSIDE this Factory checkout.
    if _git(factory_checkout, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ConflictError("GDK build checkout has uncommitted or untracked files")

    # CAS may add approved Identity, but build integration must never mutate
    # the pinned product tree, including approved Identity or executable inputs.
    changed = _git(factory_checkout, "diff", "--name-only", "-z",
                   cas_sha, build_sha, "--", "products/signal-sprint")
    if changed:
        raise ConflictError("GDK build branch modified immutable Signal Sprint product tree")

    blob_sha = _git(factory_checkout, "rev-parse", cas_sha + ":" + APPROVED_PATH).decode("ascii")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", blob_sha):
        raise ConflictError("GDK approved Identity Git blob id is invalid")
    return {
        "schema_version": 1,
        "status": "GDK_BUILD_BRANCH_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME",
        "packaging_family": "GDK",
        "package_format": "MSIXVC2",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "cas_commit_sha": cas_sha,
        "factory_head_sha": build_sha,
        "build_branch": branch,
        "approved_identity_blob_sha": blob_sha,
        "next_stage": "GDK_MSIXVC2_STAGING_RECHECK_AND_SDK_VALIDATION",
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-checkout", type=Path, required=True)
    parser.add_argument("--cas-commit-sha", required=True)
    parser.add_argument("--build-head-sha", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_build_branch(args.factory_checkout, args.cas_commit_sha, args.build_head_sha)
    except (ConflictError, HoldError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msixvc_built": False}))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
