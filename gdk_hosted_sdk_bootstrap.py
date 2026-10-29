"""Opt-in, hosted-only Microsoft GDK installation gate for Signal Sprint.

Read-only by default. The installer may run ONLY on an ephemeral GitHub-hosted
Windows runner with explicit invocation, pinned version, and an independently
approved makepkg.exe SHA-256. It never executes makepkg, CAS, or Store operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from gdk_sdk_discovery import discover_makepkg
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
OCTOBER_GDK = re.compile(r"2610(?:\.\d+){1,3}\Z")
MAX_EXE = 512 * 1024 * 1024


def _winget() -> Path | None:
    candidate = shutil.which("winget.exe")
    if not candidate:
        return None
    path = Path(candidate)
    if not path.is_absolute() or path.name.lower() != "winget.exe":
        raise ConflictError("WinGet must resolve to an absolute winget.exe")
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        root = Path(workspace).resolve()
        resolved = path.resolve()
        if resolved == root or root in resolved.parents:
            raise ConflictError("WinGet executable inside checkout is untrusted")
    return path


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


def bootstrap(*, install: bool = False, sdk_version: str = "",
              approved_makepkg_sha256: str = "") -> dict:
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
    if sys.platform != "win32":
        if install:
            raise HoldError("GDK bootstrap installation requires Windows")
        return {**base, "status": "GDK_HOSTED_WINDOWS_REQUIRED", "winget_available": False}
    winget = _winget()
    if not install:
        return {**base, "status": "GDK_HOSTED_WINGET_PROBE_ONLY",
                "winget_available": winget is not None}
    # This is never a local-PC installer. Do not install anything on a
    # developer workstation, even if --install is passed accidentally.
    if (os.environ.get("CI", "").lower() != "true"
            or os.environ.get("GITHUB_ACTIONS", "").lower() != "true"
            or os.environ.get("RUNNER_OS") != "Windows"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise HoldError("GDK installation allowed only on GitHub-hosted Windows")
    if type(sdk_version) is not str or not OCTOBER_GDK.fullmatch(sdk_version):
        raise HoldError("explicit October 2026 GDK 2610.x version pin required")
    if (type(approved_makepkg_sha256) is not str
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
    parser.add_argument("--sdk-version", default="")
    parser.add_argument("--approved-makepkg-sha256", default="")
    args = parser.parse_args(argv)
    try:
        result = bootstrap(install=args.install, sdk_version=args.sdk_version,
                           approved_makepkg_sha256=args.approved_makepkg_sha256)
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
