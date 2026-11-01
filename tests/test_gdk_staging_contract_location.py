"""Location boundary tests for Signal Sprint reviewed GDK SDK handoff."""
from pathlib import Path
import os
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

from gdk_staging_handoff_verify import _load_external_contract, _require_external_contract
from package_identity_provisioner import ConflictError, HoldError


class ReviewedContractLocationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.staging = self.root / "staging"
        self.staging.mkdir()

    def test_independent_contract_outside_staging_allowed(self):
        contract = self.root / "reviewed-contract.json"
        contract.write_text("{}", encoding="utf-8")
        _require_external_contract(contract, self.staging)

    def test_contract_in_staging_rejected(self):
        contract = self.staging / "reviewed-contract.json"
        contract.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "outside mutable staging"):
            _require_external_contract(contract, self.staging)

    def test_nested_contract_and_parent_traversal_rejected(self):
        nested = self.staging / "reports"
        nested.mkdir()
        contract = nested / "reviewed-contract.json"
        contract.write_text("{}", encoding="utf-8")
        disguised = self.staging / ".." / "staging" / "reports" / "reviewed-contract.json"
        with self.assertRaisesRegex(ConflictError, "outside mutable staging"):
            _require_external_contract(disguised, self.staging)

    def test_symlinked_contract_rejected(self):
        actual = self.root / "reviewed-contract.json"
        actual.write_text("{}", encoding="utf-8")
        linked = self.root / "linked-contract.json"
        try:
            linked.symlink_to(actual)
        except (OSError, NotImplementedError):
            self.skipTest("Runner cannot create symlinks")
        with self.assertRaisesRegex(HoldError, "linked"):
            _require_external_contract(linked, self.staging)

    def test_external_contract_strict_read_accepts_reviewed_object(self):
        contract = self.root / "reviewed-contract.json"
        contract.write_text('{"schema_version":1}', encoding="utf-8")
        self.assertEqual(_load_external_contract(contract, self.staging),
                         {"schema_version": 1})

    def test_external_contract_duplicate_keys_rejected(self):
        contract = self.root / "reviewed-contract.json"
        contract.write_text('{"status":"GOOD","status":"FORGED"}', encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "duplicate JSON key"):
            _load_external_contract(contract, self.staging)

    def test_external_contract_changed_file_identity_rejected(self):
        # Simulate a file replacement between lstat and open. A plain
        # read_bytes() would accept the substituted JSON without detection.
        contract = self.root / "reviewed-contract.json"
        contract.write_text('{"status":"GOOD"}', encoding="utf-8")
        original_fstat = os.fstat

        def replaced_inode(fd):
            actual = original_fstat(fd)
            return SimpleNamespace(st_dev=actual.st_dev, st_ino=actual.st_ino + 1)

        with patch("gdk_sdk_result_intake.os.fstat", side_effect=replaced_inode):
            with self.assertRaisesRegex(ConflictError, "changed before open"):
                _load_external_contract(contract, self.staging)

    def test_external_contract_over_reader_limit_rejected(self):
        contract = self.root / "reviewed-contract.json"
        contract.write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaisesRegex(ConflictError, "size invalid"):
            _load_external_contract(contract, self.staging)


if __name__ == "__main__":
    unittest.main()
