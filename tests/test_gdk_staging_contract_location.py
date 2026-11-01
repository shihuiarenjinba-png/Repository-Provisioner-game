"""Location boundary tests for Signal Sprint reviewed GDK SDK handoff."""
from pathlib import Path
import tempfile
import unittest

from gdk_staging_handoff_verify import _require_external_contract
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


if __name__ == "__main__":
    unittest.main()
