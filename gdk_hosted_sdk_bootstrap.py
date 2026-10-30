"""Opt-in, hosted-only Microsoft GDK installation gate for Signal Sprint.

Read-only by default. The installer may run ONLY on an ephemeral GitHub-hosted
Windows runner with explicit invocation and pinned version. Observation mode records an
UNAPPROVED makepkg.exe digest for later independent review; approved-install
mode still requires a separately approved digest. It never executes makepkg,
CAS, or Store operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from gdk_sdk_discovery import discover_makepkg, _regular_executable
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
OCTOBER_GDK = re.compile(r"2610(?:\.\d+){1,3}\Z")
MAX_EXE = 512 * 1024 * 1024
VERSION_TOKEN = re.compile(r"(?<![A-Za-z0-9.])(?:2604|2610)(?:\.\d+){1,3}(?![A-Za-z0-9.])")


def _winget() -> Path | None:
    """Find WinGet only in explicit absolute PATH directories.

    Never use shutil.which on Windows: it may select an executable from the
    working directory before PATH. Reject ambiguous tools rather than silently
    choosing one, and never execute a binary from the repository checkout.
    """
    workspace = os.environ.get("GITHUB_WORKSPACE")
    root = Path(workspace).resolve() if workspace else None
    found: dict[str, Path] = {}
    for entry in os.environ.get("PATH", "").split(";"):
        raw = entry.strip().strip('"')
        if not raw:
            continue
        directory = Path(raw)
        if not directory.is_absolute():
            continue
        candidate = directory / "winget.exe"
        # Match the GDK tool's fail-closed discovery: neither the executable
        # nor any parent may be a symlink or Windows junction. Resolving a
        # linked PATH entry could otherwise execute an unreviewed installer.
        resolved = _regular_executable(candidate)
        if resolved is None:
            continue
        if root is not None and (resolved == root or root in resolved.parents):
            raise ConflictError("WinGet executable inside checkout is untrusted")
        found.setdefault(str(resolved).casefold(), resolved)
    if len(found) > 1:
        raise ConflictError("multiple WinGet executables found on PATH; refusing ambiguous installer")
    return next(iter(found.values())) if found else None


def _sha256(path: Path) -> str:
    before = path.stat()
    if not path.is_file() or not 0 < before.st_size <= MAX_EXE:
        raise ConflictError("installed GDK makepkg.exe size/type invalid")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ConflictError("installed GDK makepkg.exe changed during hashing")
    return h.hexdigest()


def _catalog_assessment(status: str, candidates: list[str]) -> dict:
    """Separate preview tooling from retail MSIXVC2 readiness.

    2604 is a preview (makepkg2.exe); 2610 is the first retail-capable
    MSIXVC2 GDK (managed makepkg.exe). Catalog presence is NOT approval.
    """
    # Classify the full catalog BEFORE bounding JSON output. A global first-50
    # cutoff can silently discard every 2610 version when 2604 has >50 updates,
    # falsely reporting a retail SDK as NOT_LISTED.
    ordered = sorted(set(candidates), key=lambda v: tuple(int(p) for p in v.split(".")))
    preview = [v for v in ordered if v.startswith("2604.")][-50:]
    retail = [v for v in ordered if v.startswith("2610.")][-50:]
    versions = sorted(preview + retail, key=lambda v: tuple(int(p) for p in v.split(".")))
    # A successful WinGet command with no recognizable 2604/2610 tokens may
    # be a localized, truncated, or otherwise unparseable response. It is
    # UNKNOWN, not proof that the retail SDK is absent from the catalog.
    known = status == "CANDIDATES_FOUND"
    return {
        "catalog_query_status": status,
        "unapproved_version_candidates": versions,
        "unapproved_2604_candidates": preview,
        "unapproved_2610_candidates": retail,
        "preview_2604_catalog_status": (
            "CANDIDATE_UNAPPROVED" if preview else "NOT_LISTED" if known else "UNKNOWN"),
        "retail_2610_catalog_status": (
            "CANDIDATE_UNAPPROVED" if retail else "NOT_LISTED" if known else "UNKNOWN"),
        "retail_msixvc2_sdk_approved": False,
    }


def _probe_versions(winget: Path) -> dict:
    """Read-only catalog query; candidates are NEVER approved SDK versions.

    Failure to reach the catalog must not be reported as an available version.
    No package is installed, and the query never executes makepkg.exe.
    """
    command = [str(winget), "show", "--id", "Microsoft.Gaming.GDK",
               "--exact", "--versions", "--source", "winget",
               "--accept-source-agreements", "--disable-interactivity"]
    try:
        completed = subprocess.run(command, timeout=90, check=False,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return _catalog_assessment("UNAVAILABLE", [])
    if completed.returncode != 0:
        return _catalog_assessment("FAILED", [])
    candidates = sorted(set(VERSION_TOKEN.findall(completed.stdout or "")))
    return _catalog_assessment(
        "CANDIDATES_FOUND" if candidates else "NO_RECOGNIZED_VERSION_TOKENS",
        candidates)


def bootstrap(*, install: bool = False, probe_versions: bool = False, sdk_version: str = "",
              approved_makepkg_sha256: str = "", observe_only: bool = False) -> dict:
    base = {
        "schema_version": 1,
        "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "sdk_installed_by_this_run": False,
        "makepkg_executed": False,
        "cas_return_pass": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
    }
    if install and probe_versions:
        raise HoldError("GDK probe and install modes cannot be combined")
    if observe_only and not install:
        raise HoldError("GDK SDK observation requires explicit install")
    if sys.platform != "win32":
        if install:
            raise HoldError("GDK bootstrap installation requires Windows")
        return {**base, "status": "GDK_HOSTED_WINDOWS_REQUIRED", "winget_available": False}
    try:
        winget = _winget()
    except (ConflictError, HoldError) as exc:
        # Hosted images may expose an unresolvable App Installer alias on PATH.
        # A read-only catalog probe should report UNKNOWN instead of failing
        # the whole workflow or claiming that retail SDK versions are absent.
        # Installation must still fail closed on any untrusted WinGet path.
        if install:
            raise
        return {**base, "status": "GDK_HOSTED_WINGET_UNTRUSTED_PROBE_ONLY",
                "winget_available": False,
                "winget_discovery_error": str(exc),
                **_catalog_assessment("WINGET_UNTRUSTED", [])}
    if not install:
        catalog = (_probe_versions(winget) if probe_versions and winget is not None
                   else _catalog_assessment("NOT_QUERIED" if not probe_versions
                                            else "WINGET_UNAVAILABLE", []))
        return {**base, "status": "GDK_HOSTED_WINGET_PROBE_ONLY",
                "winget_available": winget is not None, **catalog}
    # This is never a local-PC installer. Do not install anything on a
    # developer workstation, even if --install is passed accidentally.
    if (os.environ.get("CI", "").lower() != "true"
            or os.environ.get("GITHUB_ACTIONS", "").lower() != "true"
            or os.environ.get("RUNNER_OS") != "Windows"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise HoldError("GDK installation allowed only on GitHub-hosted Windows")
    # GitHub-hosted Windows alone is not authorization: push/PR jobs have
    # the same runner environment. Require an explicit manual dispatch with
    # the workflow's install_sdk input set to true before any WinGet install.
    if (os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("INSTALL_REQUESTED", "").lower() != "true"):
        raise HoldError("GDK installation requires manual workflow_dispatch with install_sdk=true")
    if type(sdk_version) is not str or not OCTOBER_GDK.fullmatch(sdk_version):
        raise HoldError("explicit October 2026 GDK 2610.x version pin required")
    if observe_only:
        if approved_makepkg_sha256:
            raise HoldError("observation mode must not accept an approved digest")
    elif (type(approved_makepkg_sha256) is not str
            or not SHA256.fullmatch(approved_makepkg_sha256)):
        raise HoldError("independently approved makepkg.exe SHA-256 required")
    if winget is None:
        raise HoldError("WinGet unavailable on hosted Windows; no SDK installed")
    command = [str(winget), "install", "--id", "Microsoft.Gaming.GDK",
               "--exact", "--version", sdk_version, "--source", "winget",
               "--silent", "--accept-package-agreements",
               "--accept-source-agreements", "--disable-interactivity"]
    try:
        completed = subprocess.run(command, timeout=1200, check=False,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HoldError("GDK WinGet installation unavailable or timed out") from exc
    if completed.returncode:
        raise HoldError("GDK WinGet installation failed; no SDK approved")
    # A successful installer is not approval. Discovery must be unambiguous
    # and the installed tool must match the independently supplied digest.
    executable = discover_makepkg()
    observed = _sha256(executable)
    if observe_only:
        return {**base, "status": "GDK_HOSTED_SDK_HASH_OBSERVED_UNAPPROVED_NO_BUILD",
                "winget_available": True, "sdk_installed_by_this_run": True,
                "sdk_version_candidate_unapproved": sdk_version,
                "makepkg_sha256_observed_unapproved": observed,
                "sdk_version_verified": False, "sdk_approved": False,
                "next_stage": "INDEPENDENT_SDK_VERSION_AND_HASH_REVIEW"}
    if observed != approved_makepkg_sha256:
        raise ConflictError("installed makepkg.exe differs from approved SHA-256")
    return {**base, "status": "GDK_HOSTED_SDK_BYTES_APPROVED_NO_BUILD",
            "winget_available": True, "sdk_installed_by_this_run": True,
            "sdk_version_pin": sdk_version,
            "makepkg_sha256": observed,
            "next_stage": "AUTHORIZED_POST_CAS_GDK_SDK_PACK_RECHECK"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--observe-only", action="store_true",
                        help="manual hosted install for UNAPPROVED digest observation only")
    parser.add_argument("--probe-versions", action="store_true",
                        help="read-only WinGet catalog query; never approves versions")
    parser.add_argument("--sdk-version", default="")
    parser.add_argument("--approved-makepkg-sha256", default="")
    args = parser.parse_args(argv)
    try:
        result = bootstrap(install=args.install, probe_versions=args.probe_versions,
                           sdk_version=args.sdk_version,
                           approved_makepkg_sha256=args.approved_makepkg_sha256,
                           observe_only=args.observe_only)
    except (ConflictError, HoldError, OSError, ValueError, TypeError) as exc:
        result = {"status": getattr(exc, "status", "HOLD"), "error": str(exc),
                  "partner_center_selection": "GDK_GAME",
                  "real_msix_pass": False, "e2e_pass": False, "store_submitted": False}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
