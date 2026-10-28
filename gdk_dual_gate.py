"""Signal Sprint: run independent Provisioner and Factory post-CAS gates on one checkout.

CHECK-ONLY. No CAS, GDK SDK invocation, package creation, or Store operation.
The Factory gate is external tooling from a separately reviewed Factory PR;
its SHA-256 MUST be obtained from a trusted channel, not the supplied checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST_ID = "game-signal-sprint-" + SOURCE_SHA
ZIP_SHA = "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412"
EXE_SHA = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
PROVISIONER_SCRIPT = Path(__file__).with_name("gdk_build_intake.py")


class DualGateHold(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise DualGateHold(message)


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate gate JSON key")
        obj[key] = value
    return obj


def parse_receipt(raw: bytes, stage: str) -> dict:
    require(len(raw) <= 65536, stage + " output too large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    except DualGateHold:
        raise
    except (UnicodeError, ValueError) as exc:
        raise DualGateHold(stage + " invalid JSON") from exc
    require(type(value) is dict, stage + " output not an object")
    return value


def invoke(script: Path, args: list[str], stage: str) -> dict:
    try:
        proc = subprocess.run([sys.executable, str(script), *args],
                              capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DualGateHold(stage + " execution unavailable") from exc
    require(proc.returncode == 0, stage + " rejected inputs (HOLD)")
    return parse_receipt(proc.stdout, stage)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def expected(receipt: dict, stage: str, cas: str, build: str) -> None:
    shared = {"schema_version": 1, "request_id": REQUEST_ID,
              "source_sha": SOURCE_SHA, "cas_commit_sha": cas,
              "factory_head_sha": build, "package_version": None,
              "real_msixvc_built": False, "store_submitted": False}
    if stage == "provisioner":
        shared.update(status="GDK_BUILD_INPUT_CHECK_ONLY",
                      next_stage="BUILD_GDK_MSIXVC_FROM_PINNED_EXE",
                      packaging_family="GDK", package_format="MSIXVC_OR_MSIXVC2",
                      source_repository="shihuiarenjinba-png/AI-Game-Factory",
                      source_branch="codex/game-signal-sprint-undo-20261027")
    else:
        shared.update(status="GDK_FACTORY_POST_CAS_CHECK_ONLY",
                      next_stage="GDK_SDK_BUILD_PENDING",
                      packaging_family="GDK", windows_e2e_pass=False,
                      source_repository="shihuiarenjinba-png/AI-Game-Factory")
    for key, value in shared.items():
        require(type(receipt.get(key)) is type(value) and receipt[key] == value,
                stage + " receipt mismatch: " + key)
    pinned = receipt.get("pinned_exe")
    require(type(pinned) is dict and pinned.get("artifact_zip_sha256") == ZIP_SHA
            and pinned.get("executable_sha256") == EXE_SHA
            and type(pinned.get("executable_bytes")) is int
            and pinned["executable_bytes"] > 0
            and pinned.get("executable") == "SignalSprint.exe",
            stage + " pinned EXE receipt mismatch")


def run_dual_gate(checkout: Path, artifact: Path, cas: str, build: str,
                  factory_gate: Path, trusted_factory_gate_sha256: str) -> dict:
    require(bool(SHA40.fullmatch(cas)) and bool(SHA40.fullmatch(build))
            and cas != SOURCE_SHA and build != SOURCE_SHA,
            "invalid CAS/build SHA")
    require(bool(SHA64.fullmatch(trusted_factory_gate_sha256)),
            "trusted Factory gate digest missing")
    require(checkout.is_dir() and not checkout.is_symlink(),
            "Factory checkout unavailable")
    require(artifact.is_file() and not artifact.is_symlink(),
            "pinned artifact unavailable")
    require(factory_gate.is_file() and not factory_gate.is_symlink(),
            "Factory gate script unavailable")
    require(PROVISIONER_SCRIPT.is_file() and not PROVISIONER_SCRIPT.is_symlink(),
            "Provisioner gate script unavailable")
    require(digest(factory_gate) == trusted_factory_gate_sha256,
            "Factory gate differs from independently reviewed SHA-256")
    require(digest(artifact) == ZIP_SHA, "pinned ZIP bytes differ")
    # Neither receipt file nor any temporary output may dirty the build checkout.
    with tempfile.TemporaryDirectory(prefix="signal-sprint-gdk-dual-") as temp:
        receipt_file = Path(temp) / "provisioner-intake.json"
        provisioner_args = ["--factory-checkout", str(checkout),
                            "--pinned-artifact-zip", str(artifact),
                            "--cas-commit-sha", cas, "--build-head-sha", build]
        first = invoke(PROVISIONER_SCRIPT, provisioner_args, "provisioner")
        expected(first, "provisioner", cas, build)
        receipt_file.write_text(json.dumps(first, sort_keys=True, separators=(",", ":")),
                                encoding="utf-8")
        factory_args = ["--factory-checkout", str(checkout),
                        "--provisioner-intake", str(receipt_file),
                        "--pinned-artifact-zip", str(artifact)]
        second = invoke(factory_gate, factory_args, "factory")
        expected(second, "factory", cas, build)
        require(first["pinned_exe"] == second["pinned_exe"],
                "independent gates disagree on pinned EXE")
        # Catch mutations between the two independent checks; fail closed.
        require(invoke(PROVISIONER_SCRIPT, provisioner_args, "provisioner-recheck") == first,
                "Provisioner result changed during Factory gate")
        require(digest(factory_gate) == trusted_factory_gate_sha256
                and digest(artifact) == ZIP_SHA,
                "tool or artifact changed during verification")
    return {"schema_version": 1, "status": "GDK_DUAL_GATE_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME", "request_id": REQUEST_ID,
            "source_sha": SOURCE_SHA, "cas_commit_sha": cas,
            "factory_head_sha": build,
            "factory_gate_sha256": trusted_factory_gate_sha256,
            "provisioner_receipt_sha256": hashlib.sha256(json.dumps(
                first, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "factory_receipt_sha256": hashlib.sha256(json.dumps(
                second, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "next_stage": "GDK_SDK_PREFLIGHT_PENDING",
            "package_version": None, "real_msixvc_built": False,
            "gdk_sdk_validated": False, "store_submitted": False,
            "windows_e2e_pass": False}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--factory-checkout", required=True, type=Path)
    p.add_argument("--pinned-artifact-zip", required=True, type=Path)
    p.add_argument("--cas-commit-sha", required=True)
    p.add_argument("--build-head-sha", required=True)
    p.add_argument("--factory-gate-script", required=True, type=Path)
    p.add_argument("--trusted-factory-gate-sha256", required=True)
    a = p.parse_args(argv)
    try:
        result = run_dual_gate(a.factory_checkout, a.pinned_artifact_zip,
                               a.cas_commit_sha, a.build_head_sha,
                               a.factory_gate_script, a.trusted_factory_gate_sha256)
    except (DualGateHold, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "next_stage": "REVIEW_GDK_DUAL_GATE_INPUT"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
