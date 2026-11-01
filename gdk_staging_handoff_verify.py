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

from gdk_build_intake import _json
from gdk_microsoft_game_config import _regular_file, verify_staging_inputs
from package_identity_provisioner import ConflictError, HoldError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-json", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _regular_file(args.contract_json, 2_000_000)
        contract = _json(args.contract_json.read_bytes())
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
