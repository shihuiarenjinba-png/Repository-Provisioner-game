"""Read-only original GitHub Actions run-log + exact-byte provenance audit.

The original run log is a primary *claim* of upload bytes, not the bytes.
Neither a copied log nor a SHA match authenticates the source or authorizes CAS.
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

from gdk_build_intake import ARTIFACT_SHA256, EXE_SHA256
from gdk_exact_bytes_recovery_receipt import (
    HANDOFF_EXE_SHA256, HANDOFF_ZIP_SHA256, ORIGINAL_ARTIFACT_ID,
    recovery_receipt,
)
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_JOB

ORIGINAL_RUN_ID = 40443340158
ORIGINAL_JOB_ID = 121988766700
RUN_URL = ("https://github.com/shihuiarenjinba-png/AI-Game-Factory/"
           "actions/runs/40443340158/job/121988766700")
PIN_URL = ("https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/"
           "blob/a12ae8d540645462708d6c6894744b6f10677cea/gdk_build_intake.py")
HANDOFF_URL = ("https://github.com/shihuiarenjinba-png/Repository-Provisioner-game/"
               "pull/10#issuecomment-6561652071")
MAX_LOG_BYTES = 2_000_000


class EvidenceError(ValueError):
    pass


def _unique(log: str, regex: str, label: str) -> str:
    matches = re.findall(regex, log, flags=re.MULTILINE | re.IGNORECASE)
    if not matches or len(set(matches)) != 1:
        raise EvidenceError("missing or contradictory original run log: " + label)
    return matches[0].lower()


def parse_original_job_log(raw: bytes) -> dict:
    """Require two independent EXE outputs and the uploaded ZIP/artifact record."""
    if not 0 < len(raw) <= MAX_LOG_BYTES:
        raise EvidenceError("original job log missing or oversized")
    try:
        log = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError("original job log not UTF-8") from exc
    prefix = r"^20\d{2}-[^\r\n]*?Z[ \t]+"
    exe_build = _unique(log, prefix + r"GAME_UNSIGNED_EXE_SHA256=([0-9a-f]{64})[ \t]*\r?$", "build EXE")
    exe_verify = _unique(log, prefix + r"GAME EXE SHA256:[ \t]*([0-9a-f]{64})[ \t]*\r?$", "verification EXE")
    zip_digest = _unique(log, prefix + r"SHA256 digest of uploaded artifact zip is[ \t]+([0-9a-f]{64})[ \t]*\r?$", "uploaded ZIP")
    artifact_id = _unique(log, prefix + r"Artifact ID(?: is)?[ \t]+([0-9]+)\b[^\r\n]*\r?$", "artifact ID")
    source = _unique(log, prefix + r"[ \t]*name:[ \t]*game-signal-sprint-exe-([0-9a-f]{40})[ \t]*\r?$", "artifact source")
    git_source = _unique(log, r"\+([0-9a-f]{40}):refs/remotes/origin/codex/game-signal-sprint-undo-20261027", "checked-out source")
    if exe_build != exe_verify:
        raise EvidenceError("build and verification EXE digests disagree")
    if source != PINNED_SIGNAL_SPRINT_JOB["source_sha"] or git_source != source:
        raise EvidenceError("original run source does not match immutable source")
    if artifact_id != str(ORIGINAL_ARTIFACT_ID):
        raise EvidenceError("original run artifact ID differs from pinned artifact")
    return {
        "run_id": ORIGINAL_RUN_ID, "job_id": ORIGINAL_JOB_ID,
        "artifact_id": ORIGINAL_ARTIFACT_ID,
        "source_sha": source, "exe_sha256": exe_build,
        "zip_sha256": zip_digest,
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "origin_url": RUN_URL,
        "log_authenticity_verified": False,
    }


def read_original_job_log(path: Path) -> bytes:
    """Read only a regular unlinked file; reject symlinked ancestors too."""
    absolute = Path(os.path.abspath(path))
    try:
        for part in (absolute, *absolute.parents):
            if stat.S_ISLNK(part.lstat().st_mode):
                raise EvidenceError("original job log path contains symlink")
        info = absolute.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_LOG_BYTES:
            raise EvidenceError("original job log must be a bounded regular file")
        with absolute.open("rb") as stream:
            raw = stream.read(MAX_LOG_BYTES + 1)
        if len(raw) != info.st_size:
            raise EvidenceError("original job log changed while reading")
        return raw
    except OSError as exc:
        raise EvidenceError("original job log missing or unreadable") from exc


def audit(candidates: list[Path], search_dirs: list[Path], log_path: Path | None) -> dict:
    recovered = recovery_receipt(candidates, search_dirs)
    log_evidence = {"status": "PRIMARY_LOG_NOT_PROVIDED", "origin_url": RUN_URL,
                    "log_authenticity_verified": False}
    if log_path is not None:
        try:
            log_evidence = {"status": "PRIMARY_LOG_PARSED_CHECK_ONLY",
                            **parse_original_job_log(read_original_job_log(log_path))}
        except EvidenceError as exc:
            log_evidence = {"status": "PRIMARY_LOG_UNVERIFIED",
                            "origin_url": RUN_URL, "error": str(exc),
                            "log_authenticity_verified": False}
    parsed = log_evidence["status"] == "PRIMARY_LOG_PARSED_CHECK_ONLY"
    repo_agrees = parsed and log_evidence["exe_sha256"] == EXE_SHA256
    handoff_agrees = parsed and log_evidence["exe_sha256"] == HANDOFF_EXE_SHA256
    zip_agrees = parsed and log_evidence["zip_sha256"] == ARTIFACT_SHA256 == HANDOFF_ZIP_SHA256
    exact = (parsed and repo_agrees and handoff_agrees and zip_agrees
             and recovered["original_bytes_verified"])
    reason = ("EXPECTED_DIGEST_AUTHORITY_CONFLICT"
              if EXE_SHA256 != HANDOFF_EXE_SHA256 or ARTIFACT_SHA256 != HANDOFF_ZIP_SHA256
              else "PRIMARY_LOG_UNVERIFIED" if not parsed
              else "PRIMARY_LOG_DIGEST_MISMATCH" if not (repo_agrees and handoff_agrees and zip_agrees)
              else recovered["reason"])
    return {
        "schema_version": 1,
        "status": "ARTIFACT_EVIDENCE_AUDIT_CHECK_ONLY" if exact else "ARTIFACT_EXACT_BYTES_HOLD",
        "reason": reason,
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "artifact_id": ORIGINAL_ARTIFACT_ID,
        "digest_authorities": {
            "github_actions_original_job_log": log_evidence,
            "repository_pin": {"source_url": PIN_URL, "zip_sha256": ARTIFACT_SHA256,
                               "exe_sha256": EXE_SHA256},
            "supervisor_handoff": {"source_url": HANDOFF_URL,
                                   "zip_sha256": HANDOFF_ZIP_SHA256,
                                   "exe_sha256": HANDOFF_EXE_SHA256},
            "log_matches_repository_exe": repo_agrees,
            "log_matches_handoff_exe": handoff_agrees,
            "log_matches_both_zip_pins": zip_agrees,
            "all_authorities_agree": bool(repo_agrees and handoff_agrees and zip_agrees),
        },
        "original_archive_evidence": recovered["evidence"],
        "original_bytes_verified": exact,
        "receipt_authenticity_verified": False,
        "ready_for_cas": False,
        "cas_return_pass": False,
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "e2e_pass": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-job-log", type=Path)
    parser.add_argument("--candidate", type=Path, action="append", default=[])
    parser.add_argument("--search-dir", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    result = audit(args.candidate, args.search_dir, args.original_job_log)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["original_bytes_verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
