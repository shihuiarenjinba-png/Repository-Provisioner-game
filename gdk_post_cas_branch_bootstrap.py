"""Signal Sprint: safely prepare a dedicated GDK build branch after Identity CAS.

Check-only by default. --create atomically creates a *local* branch ref from
an already verified CAS commit; it never modifies the immutable source branch,
commits product files, pushes, merges, packages, or accesses Partner Center.
"""
from __future__ import annotations

from gdk_provenance_timestamp import require_valid_provided_at

import argparse
import json
from pathlib import Path
import subprocess
import sys

from gdk_build_intake import APPROVED_FIELDS, APPROVED_PATH, EXE_SHA256, _changed_paths, _git, _json
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB, SHA40,
)

ZERO_SHA = "0" * 40


def _ref(repo: Path, name: str) -> str | None:
    """Return an existing local ref, or None; reject other Git failures."""
    try:
        probe = subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", name],
            capture_output=True, timeout=15, check=False,
        )
        if probe.returncode == 1:
            return None
        if probe.returncode:
            raise ConflictError("GDK branch ref cannot be inspected: " + name)
        result = subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", "--hash", name],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HoldError("GDK branch ref inspection unavailable") from exc
    if result.returncode or not SHA40.fullmatch(result.stdout.strip()):
        raise ConflictError("GDK branch ref invalid or moved: " + name)
    return result.stdout.strip()


def _verify_cas(repo: Path, cas_sha: str) -> tuple[str, str, str]:
    source = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
    if not isinstance(cas_sha, str) or not SHA40.fullmatch(cas_sha) or cas_sha == source:
        raise ConflictError("GDK CAS SHA must be an actual non-source commit")
    source_ref = "refs/heads/" + PINNED_SIGNAL_SPRINT_JOB["source_branch"]
    cas_ref = "refs/heads/codex/game-signal-sprint-gdk-cas-" + source[:12]
    if _ref(repo, source_ref) != source:
        raise ConflictError("GDK immutable source branch missing or moved")
    if _ref(repo, cas_ref) != cas_sha:
        raise ConflictError("GDK approved CAS branch missing or moved")
    if _git(repo, "rev-list", "--parents", "-n", "1", cas_sha).decode().split() != [cas_sha, source]:
        raise ConflictError("GDK CAS is not a single-parent child of immutable source")
    if _changed_paths(repo, cas_sha) != [APPROVED_PATH.encode("utf-8")]:
        raise ConflictError("GDK CAS must change only approved Identity")
    approved = _json(_git(repo, "show", cas_sha + ":" + APPROVED_PATH))
    if set(approved) != APPROVED_FIELDS:
        raise ConflictError("GDK CAS approved Identity schema mismatch")
    for key, expected in PINNED_SIGNAL_SPRINT_JOB.items():
        if type(approved.get(key)) is not type(expected) or approved[key] != expected:
            raise ConflictError("GDK CAS immutable source mismatch: " + key)
    for key, expected in PINNED_SIGNAL_SPRINT_GDK_IDENTITY.items():
        if type(approved.get(key)) is not str or approved[key] != expected:
            raise ConflictError("GDK CAS reviewed Identity mismatch: " + key)
    fixed = {"schema_version": "1.0", "reviewed": True,
             "verified_source_sha": source, "package_sha256": EXE_SHA256,
             "source": "partner_center_user_provided",
             "identity_source": "USER_PROVIDED_PARTNER_CENTER",
             "packaging_family": "GDK", "signature_status": "QA_UNSIGNED"}
    for key, expected in fixed.items():
        if type(approved.get(key)) is not type(expected) or approved[key] != expected:
            raise ConflictError("GDK CAS provenance mismatch: " + key)
    require_valid_provided_at(approved.get("provided_at"), label="GDK CAS provenance timestamp")
    if _ref(repo, source_ref) != source or _ref(repo, cas_ref) != cas_sha:
        raise ConflictError("GDK source/CAS branch moved during verification")
    return source, source_ref, cas_ref


def bootstrap_build_branch(repo: Path, cas_sha: str, *, create: bool = False) -> dict:
    """Verify CAS; optionally create the deterministic local build ref once."""
    source, source_ref, cas_ref = _verify_cas(repo, cas_sha)
    branch = "codex/game-signal-sprint-gdk-build-" + cas_sha[:12]
    build_ref = "refs/heads/" + branch
    existing = _ref(repo, build_ref)
    if existing is not None and existing != cas_sha:
        raise ConflictError("GDK build branch already exists at another commit")
    if create and existing is None:
        if _ref(repo, source_ref) != source or _ref(repo, cas_ref) != cas_sha:
            raise ConflictError("GDK source/CAS moved before build branch creation")
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "update-ref", build_ref, cas_sha, ZERO_SHA],
                capture_output=True, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HoldError("GDK build branch creation unavailable") from exc
        if result.returncode and _ref(repo, build_ref) != cas_sha:
            raise ConflictError("GDK build branch atomic creation failed")
    if _ref(repo, source_ref) != source or _ref(repo, cas_ref) != cas_sha:
        raise ConflictError("GDK source/CAS moved after build branch operation")
    actual = _ref(repo, build_ref)
    if actual is not None and actual != cas_sha:
        raise ConflictError("GDK build branch changed during verification")
    return {
        "schema_version": 1,
        "status": ("GDK_BUILD_BRANCH_LOCAL_CREATED_OR_EXISTING" if create
                   else "GDK_BUILD_BRANCH_BOOTSTRAP_CHECK_ONLY"),
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": source,
        "cas_commit_sha": cas_sha,
        "factory_head_sha": actual if create else None,
        "build_branch": branch,
        "build_ref_exists_at_cas": actual == cas_sha,
        "local_ref_created_or_verified": create,
        "remote_ref_pushed": False,
        "real_msixvc_built": False,
        "store_submitted": False,
        "next_stage": "REVIEWED_BUILD_BRANCH_INTEGRATION_THEN_GDK_BUILD_BRANCH_GATE",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-checkout", required=True, type=Path)
    parser.add_argument("--cas-commit-sha", required=True)
    parser.add_argument("--create", action="store_true", help="Explicitly create local ref only; never push")
    args = parser.parse_args(argv)
    try:
        result = bootstrap_build_branch(args.factory_checkout, args.cas_commit_sha, create=args.create)
    except (ConflictError, HoldError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"), "error": str(exc),
                          "real_msixvc_built": False}))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
