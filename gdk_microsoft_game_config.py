"""Fail-closed Signal Sprint GDK MicrosoftGame.config preflight and staging.

Only a reviewed post-CAS intake can be used. No Store, CAS, package build,
credential access, or source branch changes occur here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib

from gdk_build_intake import create_intake, EXE_SHA256
from package_identity_provisioner import (
    ConflictError, HoldError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB,
)

ASSETS = {
    "StoreLogo": ("StoreLogo.png", (100, 100)),
    "Square150x150Logo": ("Logo.png", (150, 150)),
    "Square44x44Logo": ("SmallLogo.png", (44, 44)),
    "SplashScreenImage": ("SplashScreen.png", (1920, 1080)),
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
VERSION = re.compile(r"^(0|[1-9][0-9]{0,4})(?:\.(0|[1-9][0-9]{0,4})){2}\.0$")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _reject_redirected_path(path: Path, label: str) -> None:
    """Reject linked ancestors as well as linked leaf files in GDK staging."""
    for component in (path, *path.parents):
        try:
            if (component.is_symlink()
                    or getattr(component, "is_junction", lambda: False)()):
                raise HoldError(label + " linked path (symlink or junction)")
        except (OSError, RuntimeError) as exc:
            raise HoldError(label + " path cannot be inspected") from exc


def _regular_file(path: Path, max_size: int) -> None:
    _reject_redirected_path(path, "GDK staging input")
    if not path.is_file() or not 0 < path.stat().st_size <= max_size:
        raise HoldError("GDK staging input missing, linked, empty or oversized: " + path.name)


def _png_dimensions(path: Path) -> tuple[int, int]:
    _regular_file(path, 20_000_000)
    # Validate PNG chunk order, CRC, compressed scanlines and filter bytes.
    # Checking only IHDR and CRC allows completely undecodable artwork to
    # pass the staging gate and fail later in the actual GDK packaging step.
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ConflictError("GDK icon is not PNG: " + path.name)
    cursor, dims, ended = len(PNG_SIGNATURE), None, False
    idat, seen_idat, idat_ended, palette, transparency = [], False, False, False, False
    bit_depth = color_type = interlace = None
    while cursor < len(data):
        if len(data) - cursor < 12:
            raise ConflictError("GDK icon truncated: " + path.name)
        size = struct.unpack(">I", data[cursor:cursor+4])[0]
        tag = data[cursor+4:cursor+8]
        end = cursor + 12 + size
        if end > len(data):
            raise ConflictError("GDK icon truncated chunk: " + path.name)
        chunk = data[cursor+8:cursor+8+size]
        crc = struct.unpack(">I", data[cursor+8+size:end])[0]
        if zlib.crc32(tag + chunk) != crc:
            raise ConflictError("GDK icon PNG CRC mismatch: " + path.name)
        # PNG chunk names are ASCII letters and the third (reserved) byte
        # must be uppercase. Unknown *critical* chunks cannot be ignored:
        # accepting one would claim artwork is decodable without interpreting
        # mandatory rendering instructions.
        if (any(not (65 <= letter <= 90 or 97 <= letter <= 122) for letter in tag)
                or not 65 <= tag[2] <= 90):
            raise ConflictError("GDK icon invalid PNG chunk type: " + path.name)
        if tag not in (b"IHDR", b"PLTE", b"IDAT", b"IEND") and not (tag[0] & 0x20):
            raise ConflictError("GDK icon unknown critical PNG chunk: " + path.name)
        if cursor == 8:
            if tag != b"IHDR" or size != 13:
                raise ConflictError("GDK icon missing PNG IHDR: " + path.name)
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", chunk))
            if (not 0 < width <= 1920 or not 0 < height <= 1080
                    or compression != 0 or filtering != 0 or interlace not in (0, 1)
                    or bit_depth not in {0: (1, 2, 4, 8, 16), 2: (8, 16),
                                         3: (1, 2, 4, 8), 4: (8, 16),
                                         6: (8, 16)}.get(color_type, ())):
                raise ConflictError("GDK icon invalid PNG IHDR: " + path.name)
            # Microsoft GDK SubmissionValidator accepts 24-bpp RGB or
            # 32-bpp RGBA/PARGB artwork. A valid grayscale, indexed, or
            # 16-bit PNG can pass structural/CRC checks but fail packaging.
            # Enforce the retail pixel-format contract before staging.
            if bit_depth != 8 or color_type not in (2, 6):
                raise ConflictError("GDK icon requires 8-bit RGB or RGBA PNG: " + path.name)
            dims = (width, height)
        elif tag == b"IHDR":
            raise ConflictError("GDK icon duplicate PNG IHDR: " + path.name)
        if tag == b"PLTE":
            if (seen_idat or palette or size == 0 or size % 3 or size > 768
                    or color_type in (0, 4)
                    or (color_type == 3 and size // 3 > (1 << bit_depth))):
                raise ConflictError("GDK icon invalid PNG palette: " + path.name)
            palette = True
        elif tag == b"tRNS":
            # PNG transparency keys are valid for RGB, but forbidden for RGBA.
            # For 8-bit RGB, tRNS contains three 16-bit samples whose high
            # bytes must be zero. CRC-correct malformed metadata must not
            # pass the GDK staging gate as validated artwork.
            if (transparency or seen_idat or color_type != 2 or size != 6
                    or any(chunk[index] != 0 for index in (0, 2, 4))):
                raise ConflictError("GDK icon invalid PNG transparency chunk: " + path.name)
            transparency = True
        elif tag == b"IDAT":
            if idat_ended:
                raise ConflictError("GDK icon noncontiguous PNG IDAT: " + path.name)
            seen_idat = True
            idat.append(chunk)
        elif seen_idat:
            idat_ended = True
        if tag == b"IEND":
            if size or end != len(data):
                raise ConflictError("GDK icon malformed PNG end: " + path.name)
            ended = True
            break
        cursor = end
    if not ended or dims is None or not seen_idat or (color_type == 3 and not palette):
        raise ConflictError("GDK icon PNG image data/end missing: " + path.name)

    # Check the actual zlib stream, not just the CRC of the compressed bytes.
    # Bound decompression to the exact PNG scanline budget (including Adam7).
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    passes = ((0, 0, 1, 1),) if interlace == 0 else (
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
    rows = []
    for x, y, dx, dy in passes:
        w = max(0, (dims[0] - x + dx - 1) // dx)
        h = max(0, (dims[1] - y + dy - 1) // dy)
        if w and h:
            rows.extend([1 + (w * channels * bit_depth + 7) // 8] * h)
    expected = sum(rows)
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(b"".join(idat), expected + 1)
        if len(raw) <= expected:
            raw += decoder.flush(expected + 1 - len(raw))
    except (zlib.error, ValueError) as exc:
        raise ConflictError("GDK icon invalid PNG compressed image: " + path.name) from exc
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ConflictError("GDK icon PNG decompressed scanlines invalid: " + path.name)
    pos = 0
    for row_bytes in rows:
        if raw[pos] > 4:
            raise ConflictError("GDK icon PNG invalid scanline filter: " + path.name)
        pos += row_bytes
    return dims


def _reviewed_version(value: str) -> str:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise HoldError("GDK package version must be explicit A.B.C.0 (Store reserves fourth component)")
    if any(int(v) > 65535 for v in value.split(".")) or int(value.split(".")[0]) == 0:
        raise HoldError("GDK package version components out of range")
    return value


def _reviewed_display(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 100 or value != value.strip() or any(ord(c) < 32 for c in value):
        raise HoldError("Reviewed Partner Center display name is required at build gate")
    return value


def _validate_intake(intake: dict) -> None:
    if not isinstance(intake, dict) or intake.get("status") != "GDK_BUILD_INPUT_CHECK_ONLY":
        raise ConflictError("GDK post-CAS intake must be verified first")
    fixed = {key: PINNED_SIGNAL_SPRINT_JOB[key] for key in ("request_id", "source_repository", "source_branch", "source_sha")}
    fixed.update({"packaging_family": "GDK",
                  "next_stage": "BUILD_GDK_MSIXVC_FROM_PINNED_EXE",
                  "package_format": "MSIXVC_OR_MSIXVC2"})
    for key, expected in fixed.items():
        if type(intake.get(key)) is not type(expected) or intake[key] != expected:
            raise ConflictError("GDK intake immutable field mismatch: " + key)
    if intake.get("identity") != PINNED_SIGNAL_SPRINT_GDK_IDENTITY:
        raise ConflictError("GDK intake Identity mismatch")
    if intake.get("pinned_exe", {}).get("executable_sha256") != EXE_SHA256:
        raise ConflictError("GDK intake pinned executable mismatch")
    if intake.get("package_version") is not None or intake.get("real_msixvc_built") is not False or intake.get("store_submitted") is not False:
        raise ConflictError("GDK intake incorrectly claims downstream progress")
    for key in ("cas_commit_sha", "factory_head_sha"):
        if not isinstance(intake.get(key), str) or not re.fullmatch(r"[0-9a-f]{40}", intake[key]):
            raise ConflictError("GDK intake missing actual CAS/build SHA")


def prepare_config(intake: dict, asset_root: Path, package_version: str, reviewed_display_name: str) -> dict:
    """Return validated XML and machine-readable build contract; no writes."""
    _validate_intake(intake)
    version = _reviewed_version(package_version)
    display = _reviewed_display(reviewed_display_name)
    _reject_redirected_path(asset_root, "GDK staging root")
    if not asset_root.is_dir():
        raise HoldError("GDK staging content directory is unavailable or linked")
    exe = asset_root / "SignalSprint.exe"
    _regular_file(exe, 40_000_000)
    if _sha(exe) != EXE_SHA256:
        raise ConflictError("GDK staged EXE differs from immutable artifact bytes")
    _reject_redirected_path(exe, "GDK staged EXE")
    for _, (name, dims) in ASSETS.items():
        icon = asset_root / name
        if _png_dimensions(icon) != dims:
            raise ConflictError("GDK icon dimensions mismatch: " + name)
        _reject_redirected_path(icon, "GDK staged icon")

    identity = PINNED_SIGNAL_SPRINT_GDK_IDENTITY
    game = ET.Element("Game", {"configVersion": "1"})
    ET.SubElement(game, "Identity", {"Name": identity["name"], "Publisher": identity["publisher"], "Version": version})
    ET.SubElement(game, "StoreId").text = identity["store_id"]
    # Signal Sprint is a standalone Win32 game; its pinned EXE has no Xbox
    # services imports or identifiable Xbox Live initialization strings.
    # Microsoft Game Publishing Guide explicitly requires GDK titles that do
    # NOT use Xbox services to OMIT MSAAppId and TitleId from the retail
    # MicrosoftGame.config, otherwise players can get Xbox sign-in errors.
    # Keep the user-provided values in the independently verified Identity
    # contract; do not silently turn on Xbox services just because IDs exist.
    ET.SubElement(ET.SubElement(game, "Resources"), "Resource", {"Language": "en-US"})
    ET.SubElement(ET.SubElement(game, "ExecutableList"), "Executable",
                  {"Name": "SignalSprint.exe", "Id": "Game", "TargetDeviceFamily": "PC", "Architecture": "x64"})
    ET.SubElement(game, "ShellVisuals", {"DefaultDisplayName": display,
        "PublisherDisplayName": identity["publisher_display_name"],
        "StoreLogo": ASSETS["StoreLogo"][0],
        "Square150x150Logo": ASSETS["Square150x150Logo"][0],
        "Square44x44Logo": ASSETS["Square44x44Logo"][0],
        "SplashScreenImage": ASSETS["SplashScreenImage"][0],
        "Description": display, "BackgroundColor": "#000040"})
    ET.SubElement(ET.SubElement(game, "DesktopRegistration"), "ProcessorArchitecture").text = "x64"
    xml_bytes = b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(game, encoding="utf-8") + b"\n"
    parsed = ET.fromstring(xml_bytes)
    if (parsed.tag != "Game" or parsed.attrib != {"configVersion": "1"}
            or parsed.find("Identity").attrib["Version"] != version
            or parsed.find("ExecutableList/Executable").attrib["Name"] != exe.name
            or parsed.findtext("StoreId") != identity["store_id"]
            or parsed.find("TitleId") is not None
            or parsed.find("MSAAppId") is not None):
        raise ConflictError("GDK generated config round-trip mismatch")
    return {"schema_version": 1, "status": "GDK_CONFIG_CHECK_ONLY",
        "partner_center_selection": "GDK_GAME", "packaging_family": "GDK",
        "package_format": "MSIXVC_OR_MSIXVC2", "package_version": version,
        "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
        "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
        "cas_commit_sha": intake["cas_commit_sha"],
        "factory_head_sha": intake["factory_head_sha"],
        "pinned_exe_sha256": EXE_SHA256,
        "microsoft_game_config_sha256": hashlib.sha256(xml_bytes).hexdigest(),
        "microsoft_game_config_xml": xml_bytes.decode("utf-8"),
        "next_stage": "GDK_SDK_VALIDATE_THEN_MAKEPKG_PC",
        "gdk_sdk_validated": False, "real_msixvc_built": False, "store_submitted": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-checkout", type=Path, required=True)
    parser.add_argument("--pinned-artifact-zip", type=Path, required=True)
    parser.add_argument("--cas-commit-sha", required=True)
    parser.add_argument("--build-head-sha", required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--reviewed-display-name", required=True)
    parser.add_argument("--write-staging-config", action="store_true")
    args = parser.parse_args(argv)
    try:
        intake = create_intake(args.factory_checkout, args.pinned_artifact_zip,
                               args.cas_commit_sha, args.build_head_sha)
        result = prepare_config(intake, args.asset_root, args.package_version,
                                args.reviewed_display_name)
        if args.write_staging_config:
            target = args.asset_root / "MicrosoftGame.config"
            # Exclusive creation only; never overwrite an existing config.
            _reject_redirected_path(target, "GDK config destination")
            with target.open("xb") as output:
                output.write(result["microsoft_game_config_xml"].encode("utf-8"))
            result["config_path"] = str(target)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ConflictError, HoldError, FileExistsError, OSError) as exc:
        status = getattr(exc, "status", "CONFLICT")
        print(json.dumps({"status": status, "error": str(exc), "real_msixvc_built": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
