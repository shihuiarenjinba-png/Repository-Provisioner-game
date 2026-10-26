"""Strict, offline GAME Factory -> local package/Identity intake contract.

Validation is intentionally read-only: it does not call GitHub, build a game,
query Partner Center, register a product, or write approved-identity.json.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

SCHEMA_VERSION = "1.0"
OWNER = "shihuiarenjinba-png"
FACTORY = "AI-Game-Factory"
REPOSITORY = OWNER + "/" + FACTORY
BRANCH = "codex/factory-autoloop-20261026"
ACTIONS = (
    "BUILD_WINDOWS",
    "INSPECT_PACKAGE",
    "LOOKUP_OFFICIAL_IDENTITY",
    "PROPOSE_GITHUB_RETURN",
)
FIELDS = frozenset({
    "schema_version", "request_id", "product_type", "source_factory",
    "source_repository", "source_branch", "source_sha", "slug",
    "display_name", "target_owner", "dry_run", "requested_actions",
})
SLUG = re.compile(r"^[a-z][a-z0-9-]{3,39}$")
REQUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def validate_job(record: dict) -> dict:
    """Return a safe DRY_RUN receipt, never an authorization to build/write."""
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError("unexpected or missing job fields")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    if record["product_type"] != "GAME":
        raise ValueError("wrong product_type for GAME lane")
    if record["source_factory"] != FACTORY:
        raise ValueError("wrong source_factory for GAME lane")
    if record["source_repository"] != REPOSITORY:
        raise ValueError("untrusted source_repository")
    if record["source_branch"] != BRANCH:
        raise ValueError("unapproved source_branch")
    if record["target_owner"] != OWNER:
        raise ValueError("unapproved target_owner")
    if record["dry_run"] is not True:
        raise ValueError("live execution not implemented or authorized")
    rid = record["request_id"]
    if not isinstance(rid, str) or not REQUEST.fullmatch(rid):
        raise ValueError("unsafe request_id")
    slug = record["slug"]
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("unsafe product slug")
    sha = record["source_sha"]
    if not isinstance(sha, str) or not SHA40.fullmatch(sha) or sha == "0" * 40:
        raise ValueError("exact non-placeholder Git commit SHA required")
    display = record["display_name"]
    if (not isinstance(display, str) or not 1 <= len(display) <= 100
            or display.strip() != display
            or any(ord(c) < 32 or ord(c) == 127 for c in display)):
        raise ValueError("invalid display_name")
    actions = record["requested_actions"]
    if (not isinstance(actions, list) or len(actions) != len(ACTIONS)
            or set(map(str, actions)) != set(ACTIONS)
            or any(not isinstance(x, str) for x in actions)):
        raise ValueError("unsupported requested_actions")
    # Bind the key to the entire validated job, not just request_id/slug/SHA.
    # Otherwise a changed display_name or requested_actions could be treated
    # as the same request by a future durable idempotency ledger.
    canonical = dict(record)
    canonical["requested_actions"] = sorted(actions)  # order is not semantic
    key_material = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    key = sha256(b"GAME_PACKAGE_JOB_V1\x00" + key_material.encode("ascii")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": rid,
        "product_type": "GAME",
        "status": "DRY_RUN",
        "idempotency_key": key,
        "source_repository": REPOSITORY,
        "source_branch": BRANCH,
        "source_sha": sha,
        "expected_head_sha": None,
        "package": {
            "status": "NOT_BUILT", "sha256": None,
            "artifact_url": None, "package_identity": None,
        },
        "official_identity": {
            "status": "UNVERIFIED", "store_id": None, "name": None,
            "publisher": None, "version": None, "official_evidence_url": None,
        },
        "github_return": {
            "status": "NOT_GAMELIED",
            "repository": REPOSITORY, "branch": BRANCH,
            "path": "products/" + slug + "/store/approved-identity.json",
            "commit_sha": None,
        },
        "errors": [],
        "next_stage": "VERIFY_LIVE_GITHUB_HEAD_AND_LOCAL_BUILD",
        "note": (
            "Read-only contract check only. Authenticated HEAD verification, "
            "durable idempotency ledger, Windows build, Partner Center evidence, "
            "and atomic GitHub identity return are NOT performed."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > 32768:
            raise ValueError("job JSON too large")
        data = json.loads(args.input.read_text(encoding="utf-8"),
                          object_pairs_hook=_reject_duplicates)
        receipt = validate_job(data)
        encoded = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            if args.output.is_symlink():
                raise ValueError("symlink output forbidden")
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("PACKAGE_INTAKE_HOLD: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
