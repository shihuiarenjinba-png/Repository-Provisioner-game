"""Fail-closed check-only contract for a NEW Signal Sprint build lineage.

A new lineage is never a recovery of expired Artifact 12706862577. It must
retain the immutable source, use a distinct request/build/run/artifact ID, and
receive separate human approval. This checker never authorizes CAS or Store.
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
import zipfile

from gdk_build_intake import ARTIFACT_SHA256, EXE_SHA256, _json
from gdk_exact_bytes_recovery_receipt import ORIGINAL_ARTIFACT_ID, HANDOFF_EXE_SHA256
from package_identity_provisioner import (PINNED_SIGNAL_SPRINT_JOB, PINNED_SIGNAL_SPRINT_GDK_IDENTITY, ConflictError)

SOURCE = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
OLD_REQUEST = PINNED_SIGNAL_SPRINT_JOB["request_id"]
MAX_PROPOSAL = 16_384
MAX_ARCHIVE = 100_000_000
MAX_EXE = 40_000_000
MEMBERS = {"SignalSprint.exe", "provenance.json", "provisioner-request.json"}
FIELDS = {"schema_version", "decision", "product", "partner_center_selection",
          "source_sha", "source_branch", "original_request_id", "original_artifact_id",
          "new_request_id", "build_id", "workflow_run_id", "artifact_id",
          "zip_sha256", "exe_sha256", "reviewed_by", "reviewed_at",
          "store_id", "xbox_title_id", "xbox_scid", "msa_app_id"}
HEX64 = re.compile(r"[0-9a-f]{64}")
REVIEWED_AT = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)")


class ReissueHold(ValueError):
    pass


def _safe_regular(path: Path, maximum: int) -> bytes:
    absolute = Path(os.path.abspath(path))
    try:
        for part in (absolute, *absolute.parents):
            if stat.S_ISLNK(part.lstat().st_mode):
                raise ReissueHold("SYMLINK_PATH")
        before = absolute.stat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
            raise ReissueHold("MISSING_OR_INVALID_FILE")
        with absolute.open("rb") as stream:
            raw = stream.read(maximum + 1)
        after = absolute.stat()
        if (len(raw) != before.st_size or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ino != after.st_ino):
            raise ReissueHold("FILE_CHANGED_DURING_READ")
        return raw
    except OSError as exc:
        raise ReissueHold("MISSING_OR_UNREADABLE_FILE") from exc


def _proposal(raw: bytes) -> dict:
    try:
        data = _json(raw)
    except (ValueError, TypeError, ConflictError) as exc:
        raise ReissueHold("INVALID_PROPOSAL_JSON") from exc
    if set(data) != FIELDS:
        raise ReissueHold("PROPOSAL_SCHEMA_MISMATCH")
    expected = {
        "schema_version": 1,
        "decision": "REQUEST_NEW_IMMUTABLE_BUILD_LINEAGE",
        "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "source_sha": SOURCE,
        "source_branch": PINNED_SIGNAL_SPRINT_JOB["source_branch"],
        "original_request_id": OLD_REQUEST,
        "original_artifact_id": ORIGINAL_ARTIFACT_ID,
        "store_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"],
        "xbox_title_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["xbox_title_id"],
        "xbox_scid": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["xbox_scid"],
        "msa_app_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["msa_app_id"],
    }
    if any(type(data[k]) is not type(v) or data[k] != v for k, v in expected.items()):
        raise ReissueHold("ORIGINAL_SOURCE_OR_PRODUCT_MISMATCH")
    run, artifact = data["workflow_run_id"], data["artifact_id"]
    if (type(run) is not int or type(artifact) is not int
            or run <= 0 or artifact <= 0 or artifact == ORIGINAL_ARTIFACT_ID):
        raise ReissueHold("RUN_OR_ARTIFACT_ID_INVALID")
    new_request = f"game-signal-sprint-reissue-{SOURCE}-{run}"
    build_id = f"gdk-reissue-{run}-{artifact}"
    if (type(data["new_request_id"]) is not str or data["new_request_id"] != new_request
            or type(data["build_id"]) is not str or data["build_id"] != build_id):
        raise ReissueHold("NEW_LINEAGE_ID_NOT_DISTINCT")
    for field, old in (("zip_sha256", ARTIFACT_SHA256), ("exe_sha256", EXE_SHA256)):
        value = data[field]
        if (not isinstance(value, str) or not HEX64.fullmatch(value) or value == old
                or (field == "exe_sha256" and value == HANDOFF_EXE_SHA256)):
            raise ReissueHold("NEW_LINEAGE_DIGEST_MISSING_OR_REUSED")
    if (not isinstance(data["reviewed_by"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@ -]{2,99}", data["reviewed_by"])
            or data["reviewed_by"].lower() in {"test", "unknown", "tbd", "placeholder"}):
        raise ReissueHold("REVIEWER_NOT_IDENTIFIED")
    if (not isinstance(data["reviewed_at"], str)
            or not REVIEWED_AT.fullmatch(data["reviewed_at"])):
        raise ReissueHold("REVIEW_TIMESTAMP_INVALID")
    return data


def _inspect_archive(raw: bytes, proposal: dict) -> dict:
    from io import BytesIO
    zip_digest = hashlib.sha256(raw).hexdigest()
    if zip_digest != proposal["zip_sha256"]:
        raise ReissueHold("NEW_ZIP_DIGEST_MISMATCH")
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) != 3 or {m.filename for m in members} != MEMBERS:
                raise ReissueHold("NEW_ARCHIVE_MEMBER_SET_INVALID")
            for m in members:
                limit = MAX_EXE if m.filename.endswith(".exe") else 65_536
                if (m.is_dir() or not 0 < m.file_size <= limit
                        or (m.create_system == 3 and stat.S_IFMT(m.external_attr >> 16) == stat.S_IFLNK)):
                    raise ReissueHold("NEW_ARCHIVE_MEMBER_UNSAFE")
            if archive.testzip() is not None:
                raise ReissueHold("NEW_ARCHIVE_CRC_MISMATCH")
            exe = archive.read("SignalSprint.exe")
            exe_digest = hashlib.sha256(exe).hexdigest()
            if exe_digest != proposal["exe_sha256"]:
                raise ReissueHold("NEW_EXE_DIGEST_MISMATCH")
            provenance = _json(archive.read("provenance.json"))
            request = _json(archive.read("provisioner-request.json"))
    except ReissueHold:
        raise
    except (OSError, ValueError, RuntimeError, EOFError, zipfile.BadZipFile,
            zipfile.LargeZipFile, ConflictError) as exc:
        raise ReissueHold("NEW_ARCHIVE_INVALID") from exc
    required = {**PINNED_SIGNAL_SPRINT_JOB, "request_id": proposal["new_request_id"]}
    lineage = {"build_id": proposal["build_id"], "workflow_run_id": proposal["workflow_run_id"],
               "artifact_id": proposal["artifact_id"]}
    for record in (provenance, request):
        if any(type(record.get(k)) is not type(v) or record[k] != v
               for k, v in {**required, **lineage}.items()):
            raise ReissueHold("NEW_ARCHIVE_PROVENANCE_OR_REQUEST_MISMATCH")
    if (provenance.get("executable") != "SignalSprint.exe"
            or provenance.get("executable_sha256") != exe_digest
            or provenance.get("artifact_kind") != "EXE_QA_UNSIGNED"
            or request.get("dry_run") is not True):
        raise ReissueHold("NEW_ARCHIVE_EXE_OR_REQUEST_INVALID")
    return {"zip_sha256": zip_digest, "exe_sha256": exe_digest,
            "provenance_sha256": hashlib.sha256(
                json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "request_sha256": hashlib.sha256(
                json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def check_reissue(proposal_path: Path | None, archive_path: Path | None) -> dict:
    receipt = {
        "schema_version": 1, "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME", "source_sha": SOURCE,
        "original_request_id": OLD_REQUEST, "original_artifact_id": ORIGINAL_ARTIFACT_ID,
        "original_zip_sha256": ARTIFACT_SHA256, "original_exe_sha256": EXE_SHA256,
        "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
        "status": "NEW_LINEAGE_REISSUE_HOLD", "reason": "NEW_LINEAGE_EVIDENCE_MISSING",
        "new_lineage_check_only": False, "approval_authenticity_verified": False,
        "ready_for_cas": False, "cas_return_pass": False,
        "gdk_sdk_validated": False, "real_msixvc_built": False,
        "e2e_pass": False, "store_submitted": False,
    }
    if proposal_path is None or archive_path is None:
        return receipt
    try:
        proposal_raw = _safe_regular(proposal_path, MAX_PROPOSAL)
        proposal = _proposal(proposal_raw)
        archive_raw = _safe_regular(archive_path, MAX_ARCHIVE)
        evidence = _inspect_archive(archive_raw, proposal)
    except ReissueHold as exc:
        receipt["reason"] = str(exc)
        return receipt
    receipt.update({
        "status": "NEW_LINEAGE_CHECK_ONLY",
        "reason": "INDEPENDENT_AUTHORIZATION_AND_NEW_CAS_CONTRACT_REQUIRED",
        "new_lineage_check_only": True,
        "new_request_id": proposal["new_request_id"],
        "build_id": proposal["build_id"],
        "workflow_run_id": proposal["workflow_run_id"],
        "artifact_id": proposal["artifact_id"],
        "proposal_sha256": hashlib.sha256(proposal_raw).hexdigest(),
        "new_artifact_evidence": evidence,
        "identity_store_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"],
        "package_version": None,
    })
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reissue-proposal", type=Path)
    parser.add_argument("--new-artifact-zip", type=Path)
    args = parser.parse_args(argv)
    result = check_reissue(args.reissue_proposal, args.new_artifact_zip)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    # A check-only receipt must never be interpreted as release/CAS authorization.
    return 2


if __name__ == "__main__":
    sys.exit(main())
