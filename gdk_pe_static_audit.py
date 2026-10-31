"""Read-only static PE inspection of Signal Sprint's immutable original EXE.

This is an additional pre-build check, not Windows execution, SDK validation,
Authenticode verification, or proof that dynamic DLL loads are absent.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

from gdk_build_intake import ARTIFACT_SHA256, inspect_pinned_artifact
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ConflictError("Signal Sprint PE header truncated")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ConflictError("Signal Sprint PE header truncated")
    return struct.unpack_from("<I", data, offset)[0]


def inspect_pe(exe: bytes) -> dict:
    """Check architecture, GUI subsystem, certificate directory and direct DLL imports."""
    if not isinstance(exe, bytes) or len(exe) < 512 or exe[:2] != b"MZ":
        raise ConflictError("Signal Sprint executable is not a valid DOS/PE candidate")
    pe = _u32(exe, 0x3C)
    if not 0x40 <= pe <= len(exe) - 24 or exe[pe:pe + 4] != b"PE\x00\x00":
        raise ConflictError("Signal Sprint PE signature invalid")
    machine, sections, opt_size = _u16(exe, pe + 4), _u16(exe, pe + 6), _u16(exe, pe + 20)
    opt = pe + 24
    if machine != 0x8664 or not 1 <= sections <= 96 or opt_size < 240 or opt + opt_size + sections * 40 > len(exe):
        raise ConflictError("Signal Sprint PE must be well-formed x64")
    if _u16(exe, opt) != 0x20B or _u16(exe, opt + 68) != 2:
        raise ConflictError("Signal Sprint PE must be PE32+ Windows GUI")
    if _u32(exe, opt + 108) < 5:
        raise ConflictError("Signal Sprint PE data directories missing")
    cert_offset, cert_size = _u32(exe, opt + 112 + 8 * 4), _u32(exe, opt + 116 + 8 * 4)
    if cert_offset or cert_size:
        raise ConflictError("Signal Sprint original EXE unexpectedly contains a certificate table")
    section_table = opt + opt_size
    ranges = []
    for i in range(sections):
        s = section_table + 40 * i
        virtual_size, rva, raw_size, raw_ptr = (_u32(exe, s + 8), _u32(exe, s + 12),
                                                _u32(exe, s + 16), _u32(exe, s + 20))
        if raw_size and (raw_ptr > len(exe) or raw_size > len(exe) - raw_ptr):
            raise ConflictError("Signal Sprint PE section extends beyond executable")
        ranges.append((rva, max(virtual_size, raw_size), raw_ptr, raw_size))

    def rva_offset(rva: int, size: int) -> int:
        for base, extent, ptr, raw_size in ranges:
            if base <= rva and size <= extent and rva - base <= raw_size - size:
                return ptr + rva - base
        raise ConflictError("Signal Sprint PE import RVA outside raw sections")

    import_rva, import_size = _u32(exe, opt + 112 + 8), _u32(exe, opt + 116 + 8)
    if not import_rva or import_size < 20:
        raise ConflictError("Signal Sprint PE direct import directory missing")
    imports = []
    for i in range(min(128, import_size // 20)):
        desc = rva_offset(import_rva + 20 * i, 20)
        fields = struct.unpack_from("<IIIII", exe, desc)
        if fields == (0, 0, 0, 0, 0):
            break
        name_off = rva_offset(fields[3], 1)
        end = exe.find(b"\x00", name_off, min(name_off + 129, len(exe)))
        if end < 0:
            raise ConflictError("Signal Sprint PE import DLL name unterminated")
        try:
            name = exe[name_off:end].decode("ascii")
        except UnicodeError as exc:
            raise ConflictError("Signal Sprint PE import DLL name non-ASCII") from exc
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}\.dll", name, re.IGNORECASE):
            raise ConflictError("Signal Sprint PE import DLL name malformed")
        imports.append(name.upper())
    else:
        raise ConflictError("Signal Sprint PE import descriptor terminator missing")
    if not imports or len(imports) != len(set(imports)):
        raise ConflictError("Signal Sprint PE import descriptor set invalid")
    vc_runtime = sorted(name for name in imports if re.match(
        r"(?:VCRUNTIME|MSVCP|UCRTBASE|API-MS-WIN-CRT)", name))
    return {
        "machine": "AMD64", "pe_format": "PE32+", "subsystem": "WINDOWS_GUI",
        "certificate_table_present": False,
        "direct_import_dlls": sorted(imports),
        "vc_runtime_direct_imports": vc_runtime,
        "dynamic_loads_and_runtime_compatibility_not_proven": True,
    }


def audit_pinned_zip(original_zip: Path) -> dict:
    pinned = inspect_pinned_artifact(original_zip)
    # Inspect the exact pinned ZIP bytes, not a second path-opened archive.
    # Otherwise a file replaced only between the two surrounding checks
    # could yield a PASS for an EXE that was never part of the pinned ZIP.
    snapshot = original_zip.read_bytes()
    if hashlib.sha256(snapshot).hexdigest() != ARTIFACT_SHA256:
        raise ConflictError("Signal Sprint pinned ZIP changed before PE audit")
    with zipfile.ZipFile(io.BytesIO(snapshot)) as z:
        exe = z.read("SignalSprint.exe")
    report = inspect_pe(exe)
    # The ZIP path can change after the first inspection; fail closed.
    if inspect_pinned_artifact(original_zip) != pinned:
        raise ConflictError("Signal Sprint pinned artifact changed during PE audit")
    return {
        "schema_version": 1, "status": "GDK_PINNED_PE_STATIC_AUDIT_PASS",
        "partner_center_selection": "GDK_GAME",
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "artifact_zip_sha256": pinned["artifact_zip_sha256"],
        "executable_sha256": pinned["executable_sha256"],
        **report, "real_msixvc_built": False, "e2e_pass": False,
        "store_submitted": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(audit_pinned_zip(args.original_zip), sort_keys=True))
        return 0
    except (ConflictError, HoldError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": getattr(exc, "status", "HOLD"), "error": str(exc),
                          "real_msixvc_built": False, "store_submitted": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
