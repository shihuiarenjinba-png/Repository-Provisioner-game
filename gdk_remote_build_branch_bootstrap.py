"""Signal Sprint GDK: verify CAS and optionally create its remote build branch.

Read-only by default. --create creates only a new GitHub ref at the verified
CAS commit (no checkout, product edit, package build, merge, or Store action).
The original source ref is immutable and is never updated by this tool.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from urllib.parse import quote

from gdk_build_intake import APPROVED_FIELDS, APPROVED_PATH, EXE_SHA256
from package_identity_provisioner import (
    ConflictError, GitHubReturnClient, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB, SHA40, _unique_json_object,
)

PROVIDED_AT = re.compile(
    r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)\Z"
)


def _ref(api, base: str, branch: str, *, missing_ok: bool = False) -> str | None:
    item = api(base + "git/ref/heads/" + branch, allow_missing=missing_ok)
    if item is None and missing_ok:
        return None
    sha = item.get("object", {}).get("sha") if isinstance(item, dict) else None
    if type(sha) is not str or not SHA40.fullmatch(sha):
        raise ConflictError("GDK remote branch ref missing or invalid: " + branch)
    return sha


def _approved(api, base: str, cas_sha: str) -> None:
    item = api(base + "contents/" + APPROVED_PATH + "?ref=" + quote(cas_sha, safe=""))
    # GitHub's REST contents API inserts CR/LF in its base64 payload.
    # Strip only those documented line breaks, then strictly validate bytes.
    encoded = item.get("content") if isinstance(item, dict) and item.get("encoding") == "base64" else None
    if type(encoded) is not str or len(encoded) > 90_000:
        raise ConflictError("GDK remote CAS Identity content missing or oversized")
    try:
        raw = base64.b64decode(encoded.replace("\\r", "").replace("\\n", ""), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConflictError("GDK remote CAS Identity base64 invalid") from exc
    if not 0 < len(raw) <= 65_536:
        raise ConflictError("GDK remote CAS Identity decoded size invalid")
    try:
        approved = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ConflictError("GDK remote CAS approved Identity JSON invalid") from exc
    if type(approved) is not dict or set(approved) != APPROVED_FIELDS:
        raise ConflictError("GDK remote CAS approved Identity schema mismatch")
    expected = {
        **PINNED_SIGNAL_SPRINT_JOB, **PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
        "schema_version": "1.0", "reviewed": True,
        "verified_source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "package_sha256": EXE_SHA256,
        "source": "partner_center_user_provided",
        "identity_source": "USER_PROVIDED_PARTNER_CENTER",
        "packaging_family": "GDK", "signature_status": "QA_UNSIGNED",
    }
    for field, value in expected.items():
        if type(approved.get(field)) is not type(value) or approved[field] != value:
            raise ConflictError("GDK remote CAS reviewed Identity/provenance mismatch: " + field)
    if type(approved.get("provided_at")) is not str or not PROVIDED_AT.fullmatch(approved["provided_at"]):
        raise ConflictError("GDK remote CAS provided_at provenance invalid")


def bootstrap_remote_build_branch(cas_sha: str, *, create: bool = False, api=None) -> dict:
    """Fail closed on CAS ancestry, identity mismatch, or remote-ref movement.

    This function does not perform the CAS itself. It accepts an actual CAS
    SHA only, never a placeholder or inferred Identity timestamp.
    """
    source = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
    if type(cas_sha) is not str or not SHA40.fullmatch(cas_sha) or cas_sha == source:
        raise ConflictError("GDK remote bootstrap requires actual non-source CAS SHA")
    api = api or GitHubReturnClient().api
    base = "repos/" + PINNED_SIGNAL_SPRINT_JOB["source_repository"] + "/"
    source_branch = PINNED_SIGNAL_SPRINT_JOB["source_branch"]
    cas_branch = "codex/game-signal-sprint-gdk-cas-" + source[:12]
    build_branch = "codex/game-signal-sprint-gdk-build-" + cas_sha[:12]

    if _ref(api, base, source_branch, missing_ok=True) != source:
        raise ConflictError("GDK immutable remote source branch moved")
    if _ref(api, base, cas_branch, missing_ok=True) != cas_sha:
        raise ConflictError("GDK reviewed remote CAS branch missing or moved")
    commit = api(base + "commits/" + cas_sha)
    if (not isinstance(commit, dict) or commit.get("sha") != cas_sha
            or not isinstance(commit.get("parents"), list)
            or len(commit["parents"]) != 1
            or not isinstance(commit["parents"][0], dict)
            or commit["parents"][0].get("sha") != source):
        raise ConflictError("GDK remote CAS must have immutable source as its sole parent")
    files = commit.get("files")
    if (not isinstance(files, list) or len(files) != 1
            or not isinstance(files[0], dict)
            or files[0].get("filename") != APPROVED_PATH
            or files[0].get("status") != "added"):
        raise ConflictError("GDK remote CAS must add only approved Identity")
    _approved(api, base, cas_sha)

    # Recheck before even a check-only PASS, and immediately before any write.
    if (_ref(api, base, source_branch, missing_ok=True) != source
            or _ref(api, base, cas_branch, missing_ok=True) != cas_sha):
        raise ConflictError("GDK source/CAS remote refs moved during bootstrap verification")
    existing = _ref(api, base, build_branch, missing_ok=True)
    if existing is not None and existing != cas_sha:
        raise ConflictError("GDK remote build branch already points to another commit; no overwrite")
    if create and existing is None:
        if (_ref(api, base, source_branch, missing_ok=True) != source
                or _ref(api, base, cas_branch, missing_ok=True) != cas_sha):
            raise ConflictError("GDK source/CAS remote refs moved before build branch creation")
        # GitHub POST git/refs creates a new ref; no update-ref, no force.
        api(base + "git/refs", body={"ref": "refs/heads/" + build_branch, "sha": cas_sha})

    # Do not claim success on a stale or concurrently moved branch.
    if (_ref(api, base, source_branch, missing_ok=True) != source
            or _ref(api, base, cas_branch, missing_ok=True) != cas_sha):
        raise ConflictError("GDK source/CAS remote refs moved after bootstrap")
    actual = _ref(api, base, build_branch, missing_ok=True)
    if actual is not None and actual != cas_sha:
        raise ConflictError("GDK remote build branch moved during bootstrap")
    if create and actual != cas_sha:
        raise ConflictError("GDK remote build branch creation not confirmed")
    return {
        "schema_version": 1,
        "status": ("GDK_REMOTE_BUILD_BRANCH_CREATED_OR_EXISTING" if create
                   else "GDK_REMOTE_BUILD_BRANCH_CHECK_ONLY"),
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": source,
        "cas_commit_sha": cas_sha,
        "factory_head_sha": actual,
        "build_branch": build_branch,
        "remote_ref_exists_at_cas": actual == cas_sha,
        "remote_ref_created_or_verified": bool(create and actual == cas_sha),
        "real_msixvc_built": False,
        "store_submitted": False,
        "next_stage": "REVIEWED_POST_CAS_BUILD_ONLY_INTEGRATION_THEN_GDK_SDK_GATE",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cas-commit-sha", required=True)
    parser.add_argument("--create", action="store_true",
                        help="Explicitly create a new remote ref at CAS (never force/update)")
    args = parser.parse_args(argv)
    try:
        result = bootstrap_remote_build_branch(args.cas_commit_sha, create=args.create)
    except (ConflictError, HoldError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "real_msixvc_built": False,
                          "store_submitted": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
