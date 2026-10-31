"""Read-only NuGet Microsoft.GDK.Windows *component* version observation.

A component version is NOT proof that a full GDK SDK, makepkg.exe, or an
approved retail MSIXVC2 builder is available. No install/CAS/Store actions.
"""
from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

API = "https://api.nuget.org/v3-flatcontainer/microsoft.gdk.windows/index.json"
MAX_RESPONSE = 1_000_000
VERSION = re.compile(r"2610(?:\.[0-9]+){1,3}\Z")
REQUEST_ID = "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e"
SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"


def _download() -> bytes:
    request = Request(API, headers={"Accept": "application/json",
                                    "User-Agent": "SignalSprint-GDK-Component-Probe"})
    with urlopen(request, timeout=20) as response:
        payload = response.read(MAX_RESPONSE + 1)
    if len(payload) > MAX_RESPONSE:
        raise ValueError("NuGet component catalog too large")
    return payload


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate NuGet JSON key")
        result[key] = value
    return result


def probe(fetcher=None) -> dict:
    result = {
        "schema_version": 1, "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "request_id": REQUEST_ID, "immutable_source_sha": SOURCE_SHA,
        "source": "NuGet Microsoft.GDK.Windows component index",
        "source_url": API, "component_catalog_status": "UNKNOWN",
        "observed_component_versions": 0,
        "observed_2610_component_versions_unapproved": [],
        "complete_gdk_sdk_available": False, "sdk_installed": False,
        "sdk_approved": False, "makepkg_sha256_approved": False,
        "cas_return_pass": False, "real_msix_pass": False,
        "e2e_pass": False, "store_submitted": False,
    }
    try:
        raw = (fetcher or _download)()
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE:
            raise ValueError("Invalid NuGet component response")
        catalog = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        if (type(catalog) is not dict or set(catalog) != {"versions"}
                or type(catalog["versions"]) is not list
                or not catalog["versions"]
                or any(type(v) is not str or len(v) > 80 for v in catalog["versions"])):
            raise ValueError("Unexpected NuGet component schema")
        versions = catalog["versions"]
        candidates = sorted({v for v in versions if VERSION.fullmatch(v)},
                            key=lambda v: tuple(int(n) for n in v.split(".")))
        result["observed_component_versions"] = len(versions)
        result["observed_2610_component_versions_unapproved"] = candidates[-50:]
        result["component_catalog_status"] = (
            "2610_COMPONENT_VERSION_CANDIDATE_UNAPPROVED" if candidates
            else "NO_2610_COMPONENT_VERSION_OBSERVED")
    except (OSError, TimeoutError, UnicodeError, ValueError, TypeError):
        result["component_catalog_status"] = "UNKNOWN_QUERY_FAILED_OR_UNTRUSTED"
    return result


def main() -> int:
    print(json.dumps(probe(), sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
