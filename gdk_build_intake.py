"""Read-only Signal Sprint GDK post-CAS build intake; never builds or submits.

Run against a checkout of a dedicated post-CAS build branch. A CAS receipt
alone is not proof: verify its actual Git parent, committed Identity bytes and
ancestry before trusting the immutable EXE artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB, SHA40, _unique_json_object,
)

ARTIFACT_SHA256 = "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412"
EXE_SHA256 = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
APPROVED_PATH = "products/signal-sprint/store/approved-identity.json"
APPROVED_FIELDS = frozenset({
    "schema_version", "reviewed", "request_id", "product_type", "slug",
    "source_factory", "source_repository", "source_branch", "source_sha",
    "verified_source_sha", "package_sha256", "package_family_name",
    "package_sid", "signature_status", "store_id", "name", "publisher",
    "source", "identity_source", "provided_at", "packaging_family",
    "publisher_display_name", "xbox_title_id", "xbox_scid", "msa_app_id",
})


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes) -> dict:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeError, ValueError) as exc:
        raise ConflictError("GDK intake JSON is invalid or ambiguous") from exc
    if not isinstance(value, dict):
        raise ConflictError("GDK intake JSON must be an object")
    return value


def _git(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HoldError("GDK build Git verification unavailable") from exc
    if result.returncode:
        raise ConflictError("GDK build Git ancestry/content verification failed")
    return result.stdout.strip()


def verify_cas_checkout(repo: Path, cas_sha: str, build_sha: str) -> dict:
    source = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
    if (not isinstance(cas_sha, str) or not SHA40.fullmatch(cas_sha)
            or not isinstance(build_sha, str) or not SHA40.fullmatch(build_sha)
            or cas_sha == source or build_sha == source):
        raise ConflictError("GDK CAS/build SHA is missing or equals immutable source")
    if _git(repo, "rev-parse", "HEAD").decode() != build_sha:
        raise ConflictError("GDK checkout HEAD differs from declared build HEAD")
    if _git(repo, "rev-parse", cas_sha + "^").decode() != source:
        raise ConflictError("GDK CAS commit is not directly based on immutable source")
    _git(repo, "merge-base", "--is-ancestor", cas_sha, build_sha)
    approved_bytes = _git(repo, "show", cas_sha + ":" + APPROVED_PATH)
    approved = _json(approved_bytes)
    if set(approved) != APPROVED_FIELDS:
        raise ConflictError("GDK approved Identity schema has missing/extra fields")
    for field, expected in PINNED_SIGNAL_SPRINT_JOB.items():
        if type(approved.get(field)) is not type(expected) or approved[field] != expected:
            raise ConflictError("GDK approved immutable source mismatch: " + field)
    for field, expected in PINNED_SIGNAL_SPRINT_GDK_IDENTITY.items():
        if type(approved.get(field)) is not str or approved[field] != expected:
            raise ConflictError("GDK approved reviewed Identity mismatch: " + field)
    fixed = {"schema_version": "1.0", "reviewed": True,
             "verified_source_sha": source, "package_sha256": EXE_SHA256,
             "source": "partner_center_user_provided",
             "identity_source": "USER_PROVIDED_PARTNER_CENTER",
             "packaging_family": "GDK"}
    for field, expected in fixed.items():
        if type(approved.get(field)) is not type(expected) or approved[field] != expected:
            raise ConflictError("GDK approved CAS payload mismatch: " + field)
    if not isinstance(approved["provided_at"], str) or not re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)",
            approved["provided_at"]):
        raise ConflictError("GDK approved Identity provenance timestamp invalid")
    if not isinstance(approved["signature_status"], str) or not approved["signature_status"]:
        raise ConflictError("GDK pinned EXE signature provenance missing")
    return approved


def inspect_pinned_artifact(path: Path) -> dict:
    if (path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < 100_000_000):
        raise HoldError("Pinned GDK EXE artifact missing, linked or oversized")
    if _sha256(path.read_bytes()) != ARTIFACT_SHA256:
        raise ConflictError("Pinned GDK artifact ZIP bytes changed")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if {m.filename for m in members} != {
                    "SignalSprint.exe", "provenance.json", "provisioner-request.json"} or len(members) != 3:
                raise ConflictError("Pinned GDK artifact member set changed")
            if any(m.is_dir() or m.file_size > 40_000_000 or
                   (m.create_system == 3 and (m.external_attr >> 16) & 0o170000 == 0o120000)
                   for m in members):
                raise ConflictError("Pinned GDK artifact contains unsafe members")
            if archive.testzip() is not None:
                raise ConflictError("Pinned GDK artifact CRC failed")
            exe = archive.read("SignalSprint.exe")
            provenance = _json(archive.read("provenance.json"))
            request = _json(archive.read("provisioner-request.json"))
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as exc:
        raise ConflictError("Pinned GDK artifact is invalid") from exc
    if _sha256(exe) != EXE_SHA256:
        raise ConflictError("Pinned GDK EXE SHA changed")
    for record in (provenance, request):
        for field, expected in PINNED_SIGNAL_SPRINT_JOB.items():
            if record.get(field) != expected:
                raise ConflictError("Pinned GDK artifact provenance mismatch: " + field)
    if (provenance.get("executable") != "SignalSprint.exe"
            or provenance.get("executable_sha256") != EXE_SHA256
            or provenance.get("artifact_kind") != "EXE_QA_UNSIGNED"
            or request.get("dry_run") is not True):
        raise ConflictError("Pinned GDK EXE provenance or original dry-run request mismatch")
    return {"artifact_zip_sha256": ARTIFACT_SHA256, "executable_sha256": EXE_SHA256,
            "executable_bytes": len(exe), "executable": "SignalSprint.exe"}


def create_intake(repo: Path, artifact: Path, cas_sha: str, build_sha: str) -> dict:
    approved = verify_cas_checkout(repo, cas_sha, build_sha)
    pinned = inspect_pinned_artifact(artifact)
    return {
        "schema_version": 1, "status": "GDK_BUILD_INPUT_CHECK_ONLY",
        "next_stage": "BUILD_GDK_MSIXVC_FROM_PINNED_EXE",
        "packaging_family": "GDK", "package_format": "MSIXVC_OR_MSIXVC2",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_repository": PINNED_SIGNAL_SPRINT_JOB["source_repository"],
        "source_branch": PINNED_SIGNAL_SPRINT_JOB["source_branch"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "cas_commit_sha": cas_sha, "factory_head_sha": build_sha,
        "identity": {key: approved[key] for key in PINNED_SIGNAL_SPRINT_GDK_IDENTITY},
        "pinned_exe": pinned, "package_version": None,
        "real_msixvc_built": False, "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-checkout", type=Path, required=True)
    parser.add_argument("--pinned-artifact-zip", type=Path, required=True)
    parser.add_argument("--cas-commit-sha", required=True)
    parser.add_argument("--build-head-sha", required=True)
    args = parser.parse_args(argv)
    try:
        result = create_intake(args.factory_checkout, args.pinned_artifact_zip,
                               args.cas_commit_sha, args.build_head_sha)
    except (ConflictError, HoldError) as exc:
        print(json.dumps({"status": exc.status, "next_stage": exc.next_stage,
                          "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
