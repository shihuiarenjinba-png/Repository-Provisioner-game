"""Signal Sprint: revalidate reviewed GDK staging bytes before SDK MakePkg.

Input is the preserved JSON output of gdk_microsoft_game_config.py, stored
outside the mutable staging directory. No CAS, SDK build, Store action, or
source-branch mutation is performed by this check-only verifier.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from gdk_sdk_result_intake import _read_json
from gdk_microsoft_game_config import _regular_file, verify_staging_inputs
from package_identity_provisioner import ConflictError, HoldError


def _require_external_contract(contract_path: Path, asset_root: Path) -> None:
    """Do not treat a manifest inside mutable SDK staging as independent review.

    Resolve lexical '..' and reject linked components before comparing paths.
    This is a location boundary, not an authenticity signature: callers must
    still protect and review the external contract independently.
    """
    _regular_file(contract_path, 2_000_000)
    if contract_path.resolve().is_relative_to(asset_root.resolve()):
        raise ConflictError("GDK reviewed contract must be outside mutable staging root")


def _load_external_contract(contract_path: Path, asset_root: Path) -> dict:
    """Read one independently reviewed JSON with bounded, stable-file checks.

    The SDK result intake's strict reader pins inode, size and modification
    time across a bounded read, rejecting concurrent rewrites and duplicate
    JSON keys. Repeat the staging location check after reading as well.
    """
    _require_external_contract(contract_path, asset_root)
    contract = _read_json(contract_path, "GDK reviewed contract")
    _require_external_contract(contract_path, asset_root)
    return contract


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-json", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        contract = _load_external_contract(args.contract_json, args.asset_root)
        result = verify_staging_inputs(args.asset_root, contract, require_config=True)
    except (ConflictError, HoldError, OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": getattr(exc, "status", "CONFLICT"),
                          "error": str(exc), "gdk_sdk_validated": False,
                          "real_msixvc_built": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
