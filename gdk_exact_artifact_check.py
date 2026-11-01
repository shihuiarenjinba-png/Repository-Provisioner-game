"""Read-only pre-CAS check for preserved Signal Sprint GDK artifact bytes.

Only an exact byte-for-byte preserved ZIP can pass. A matching executable in a
repacked ZIP is NOT an acceptable replacement. No Git, CAS, GDK or Store writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

from gdk_build_intake import ARTIFACT_SHA256, EXE_SHA256, inspect_pinned_artifact, _json
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_JOB, ConflictError, HoldError

MAX_ZIP_BYTES = 100_000_000
MAX_CANDIDATES = 1000
MAX_DEPTH = 4


def sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def inspect_candidate(path: Path) -> dict:
    """Hash ZIP and contained EXE separately, then validate full provenance."""
    result = {"path": str(path), "zip_sha256": None, "exe_sha256": None,
              "zip_match": False, "exe_match": False, "provenance_match": False,
              "status": "ARTIFACT_EXACT_BYTES_HOLD",
              "provenance_sha256": None, "request_sha256": None,
              "provenance_exe_sha256": None, "provenance_matches_exe_bytes": False,
              "provenance_matches_source": False, "request_matches_source": False}
    try:
        # Reject symlinks in the entire path (including ancestor directories).
        absolute = Path(os.path.abspath(path))
        for component in (absolute, *absolute.parents):
            if stat.S_ISLNK(component.lstat().st_mode):
                result["reason"] = "SYMLINK_PATH"
                return result
        st = absolute.stat()
        if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size < MAX_ZIP_BYTES:
            result["reason"] = "NOT_REGULAR_OR_INVALID_SIZE"
            return result
        with absolute.open("rb") as source:
            result["zip_sha256"] = sha256_stream(source)
        result["zip_match"] = result["zip_sha256"] == ARTIFACT_SHA256
        # Independently report EXE digest, even for a repacked/altered ZIP.
        with zipfile.ZipFile(absolute) as archive:
            members = archive.infolist()
            if len(members) != 3 or {m.filename for m in members} != {
                    "SignalSprint.exe", "provenance.json", "provisioner-request.json"}:
                result["reason"] = "UNEXPECTED_ZIP_MEMBERS"
                return result
            info = archive.getinfo("SignalSprint.exe")
            if info.is_dir() or not 0 < info.file_size <= 40_000_000:
                result["reason"] = "EXE_SIZE_INVALID"
                return result
            with archive.open(info) as exe:
                result["exe_sha256"] = sha256_stream(exe)
            # Independently inspect the two small provenance records even if
            # the ZIP or EXE hash differs. Never treat these as authenticated.
            records = {}
            for member, label in (("provenance.json", "provenance"),
                                  ("provisioner-request.json", "request")):
                meta = archive.getinfo(member)
                if meta.is_dir() or not 0 < meta.file_size <= 65_536:
                    result["reason"] = "PROVENANCE_SIZE_INVALID"
                    return result
                with archive.open(meta) as source:
                    raw = source.read(65_537)
                if len(raw) != meta.file_size:
                    result["reason"] = "PROVENANCE_SIZE_INVALID"
                    return result
                result[label + "_sha256"] = hashlib.sha256(raw).hexdigest()
                records[label] = _json(raw)
            provenance, request = records["provenance"], records["request"]
            result["provenance_exe_sha256"] = provenance.get("executable_sha256")
            result["provenance_matches_exe_bytes"] = (
                provenance.get("executable_sha256") == result["exe_sha256"])
            result["provenance_matches_source"] = all(
                provenance.get(k) == v for k, v in PINNED_SIGNAL_SPRINT_JOB.items())
            result["request_matches_source"] = (
                all(request.get(k) == v for k, v in PINNED_SIGNAL_SPRINT_JOB.items())
                and request.get("dry_run") is True)
        result["exe_match"] = result["exe_sha256"] == EXE_SHA256
        if not result["zip_match"] or not result["exe_match"]:
            result["reason"] = "ZIP_OR_EXE_DIGEST_MISMATCH"
            return result
        # Full CRC, exact member set, JSON provenance and request pinning.
        evidence = inspect_pinned_artifact(absolute)
        result["provenance_match"] = (evidence["artifact_zip_sha256"] == ARTIFACT_SHA256
                                      and evidence["executable_sha256"] == EXE_SHA256)
        if result["provenance_match"]:
            result["status"] = "ARTIFACT_EXACT_BYTES_CHECK_ONLY"
            result["reason"] = "EXACT_ZIP_EXE_AND_PROVENANCE"
        return result
    except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile,
            RuntimeError, EOFError, ConflictError, HoldError):
        result["reason"] = "UNREADABLE_OR_INVALID_ARCHIVE"
        return result


def find_candidates(paths: list[Path], roots: list[Path]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path):
        key = os.path.abspath(path)
        if key not in seen:
            if len(candidates) >= MAX_CANDIDATES:
                raise HoldError("candidate scan limit reached; search is incomplete")
            seen.add(key)
            candidates.append(path)

    for path in paths:
        add(path)
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            raise HoldError("candidate search root unavailable or symlinked")
        root = root.absolute()
        for current, dirs, files in os.walk(root, followlinks=False):
            depth = len(Path(current).relative_to(root).parts)
            dirs[:] = sorted(d for d in dirs if depth < MAX_DEPTH and not (Path(current) / d).is_symlink())
            for name in sorted(files):
                if name.lower().endswith(".zip"):
                    add(Path(current) / name)
    return candidates


def check(paths: list[Path], roots: list[Path]) -> dict:
    try:
        candidates = find_candidates(paths, roots)
        results = [inspect_candidate(p) for p in candidates]
    except (OSError, HoldError):
        return {"status": "ARTIFACT_EXACT_BYTES_HOLD", "reason": "INCOMPLETE_CANDIDATE_SEARCH",
                "candidates": [], "ready_for_cas": False, "real_msixvc_built": False}
    exact = [r for r in results if r["status"] == "ARTIFACT_EXACT_BYTES_CHECK_ONLY"]
    return {"schema_version": 1,
            "status": "ARTIFACT_EXACT_BYTES_CHECK_ONLY" if exact else "ARTIFACT_EXACT_BYTES_HOLD",
            "partner_center_selection": "GDK_GAME",
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
            "expected_zip_sha256": ARTIFACT_SHA256, "expected_exe_sha256": EXE_SHA256,
            "candidates_checked": len(results), "exact_copy_count": len(exact),
            "candidates": results, "ready_for_cas": False,
            "real_msixvc_built": False, "store_submitted": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, action="append", default=[])
    parser.add_argument("--search-dir", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    result = check(args.candidate, args.search_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "ARTIFACT_EXACT_BYTES_CHECK_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())
