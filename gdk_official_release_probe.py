"""Read-only official Microsoft GDK release metadata probe for Signal Sprint.

This reports public release TAG candidates, never an approved SDK installer or
makepkg.exe digest. It does not install software, execute GDK, perform CAS,
create a game/package, or access Partner Center.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.request import Request, urlopen

API = "https://api.github.com/repos/microsoft/GDK/releases?per_page=100"
MAX_RESPONSE = 8_000_000
TAG = re.compile(r"October-2026(?:-Update-[0-9]+)?-v(2610\.(?:[0-9]+\.){1,2}[0-9]+)\Z", re.IGNORECASE)
REQUEST_ID = "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e"
SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"


def _download() -> bytes:
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "SignalSprint-GDK-ReadOnly-Release-Probe"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(API, headers=headers)
    with urlopen(request, timeout=20) as response:
        payload = response.read(MAX_RESPONSE + 1)
    if len(payload) > MAX_RESPONSE:
        raise ValueError("Official GDK release catalog response too large")
    return payload


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Ambiguous duplicate JSON key")
        result[key] = value
    return result


def probe(fetcher=None) -> dict:
    """Fail closed on API errors and pagination; do not infer release absence."""
    result = {
        "schema_version": 1,
        "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "request_id": REQUEST_ID,
        "immutable_source_sha": SOURCE_SHA,
        "official_source": "microsoft/GDK GitHub releases",
        "official_release_api": API,
        "catalog_status": "UNKNOWN",
        "observed_release_count": 0,
        "observed_2610_release_tags_unapproved": [],
        "catalog_exhaustive": False,
        "sdk_installed": False,
        "sdk_approved": False,
        "makepkg_executed": False,
        "makepkg_sha256_approved": False,
        "cas_return_pass": False,
        "real_msix_pass": False,
        "e2e_pass": False,
        "store_submitted": False,
    }
    try:
        payload = (fetcher or _download)()
        if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE:
            raise ValueError("Invalid release response")
        releases = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        if not isinstance(releases, list) or any(not isinstance(r, dict) for r in releases):
            raise ValueError("Official release catalog schema invalid")
        tags = set()
        for release in releases:
            # Draft/pre-release tags cannot qualify as a retail SDK candidate.
            if release.get("draft") is not False or release.get("prerelease") is not False:
                continue
            tag = release.get("tag_name")
            if isinstance(tag, str) and TAG.fullmatch(tag):
                tags.add(tag)
        result["observed_release_count"] = len(releases)
        result["observed_2610_release_tags_unapproved"] = sorted(tags)
        if tags:
            result["catalog_status"] = "OFFICIAL_2610_TAG_CANDIDATE_UNAPPROVED"
        elif len(releases) >= 100:
            result["catalog_status"] = "UNKNOWN_FIRST_PAGE_FULL"
        else:
            result["catalog_status"] = "NO_2610_TAG_ON_OBSERVED_PAGE"
        # The API response may be paginated or delayed. No response, even
        # a matching tag, proves installer availability, SDK approval, or
        # readiness for retail MSIXVC2 packaging.
    except (OSError, TimeoutError, UnicodeError, ValueError, TypeError):
        result["catalog_status"] = "UNKNOWN_QUERY_FAILED_OR_UNTRUSTED"
    return result


def main() -> int:
    print(json.dumps(probe(), sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
