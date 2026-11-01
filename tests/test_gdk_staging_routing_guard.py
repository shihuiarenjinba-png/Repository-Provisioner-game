"""Fail-closed routing/schema tests for Signal Sprint GDK SDK staging."""
import copy
from pathlib import Path
import unittest

from gdk_build_intake import EXE_SHA256
from gdk_microsoft_game_config import verify_staging_inputs
from package_identity_provisioner import ConflictError, PINNED_SIGNAL_SPRINT_JOB


class GdkStagingRoutingTests(unittest.TestCase):
    def setUp(self):
        self.contract = {
            "schema_version": 1,
            "status": "GDK_CONFIG_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "packaging_family": "GDK",
            "package_format": "MSIXVC_OR_MSIXVC2",
            "next_stage": "GDK_SDK_VALIDATE_THEN_MAKEPKG_PC",
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
            "pinned_exe_sha256": EXE_SHA256,
            "cas_commit_sha": "a" * 40,
            "factory_head_sha": "b" * 40,
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
            "staging_sha256": {},  # Intentional: reach the later digest gate.
        }

    def test_expected_route_passes_routing_gate(self):
        with self.assertRaisesRegex(ConflictError, "digest manifest invalid"):
            verify_staging_inputs(Path("unused-staging"), self.contract)

    def test_route_and_schema_mutations_fail_before_staging(self):
        changes = (
            ("schema_version", 2),
            ("schema_version", True),
            ("packaging_family", "MSIX"),
            ("package_format", "MSIX"),
            ("next_stage", "STORE_SUBMIT"),
            ("next_stage", None),
        )
        for key, changed in changes:
            with self.subTest(key=key, changed=changed):
                contract = copy.deepcopy(self.contract)
                contract[key] = changed
                with self.assertRaisesRegex(ConflictError, "routing/schema mismatch"):
                    verify_staging_inputs(Path("unused-staging"), contract)

    def test_missing_routing_fields_fail_closed(self):
        for key in ("schema_version", "packaging_family", "package_format", "next_stage"):
            with self.subTest(key=key):
                contract = copy.deepcopy(self.contract)
                del contract[key]
                with self.assertRaisesRegex(ConflictError, "routing/schema mismatch"):
                    verify_staging_inputs(Path("unused-staging"), contract)


if __name__ == "__main__":
    unittest.main()
