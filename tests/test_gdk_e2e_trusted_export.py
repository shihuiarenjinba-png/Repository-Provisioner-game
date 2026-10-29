"""Synthetic tests: independent trust-anchor continuity; no GDK SDK execution."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gdk_e2e_trusted_export import export_trusted, _verify_source_inventory
from package_identity_provisioner import ConflictError, HoldError, PINNED_SIGNAL_SPRINT_JOB


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GdkTrustedE2eExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.anchor = root / "trusted-handoff.json"
        self.plan = root / "plan.json"
        self.evidence = root / "sdk-result.json"
        self.log = root / "validation.log"
        self.package_dir = root / "sdk-output"
        self.output = root / "transfer"
        self.package_dir.mkdir()
        for path, data in ((self.anchor, b'{"trusted":true}'),
                           (self.plan, b'{"plan":true}'),
                           (self.evidence, b'{"sdk":true}'),
                           (self.log, b"synthetic SDK log, not a real build\n")):
            path.write_bytes(data)
        self.trusted_sha = digest(self.anchor)
        self.expected = {
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
            "cas_commit_sha": "b" * 40,
            "factory_head_sha": "c" * 40,
            "package_version": "1.0.1.0",
            "package_sha256": "d" * 64,
            "validation_log_sha256": digest(self.log),
            "package_size_bytes": 123,
            "sdk_version_claim": "GDK SDK 2026",
            "sdk_exit_code_claim": 0,
        }
        self.trusted = {
            **self.expected,
            "status": "GDK_TRUSTED_PREBUILD_TO_PACKAGE_BYTES_CHECK_PASS",
            "prebuild_trust_chain_verified": True,
            "package_filename": "SignalSprint.msixvc",
            "output_files_sha256": {"SignalSprint.msixvc": "d" * 64},
            "partner_center_selection": "GDK_GAME",
            "gdk_sdk_validation_independently_verified": False,
            "real_msix_pass": False, "e2e_pass": False, "store_submitted": False,
        }
        self.manifest = {
            **self.expected,
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "original_sdk_filename": "SignalSprint.msixvc",
            "sdk_pack_plan_sha256": digest(self.plan),
            "sdk_result_evidence_sha256": digest(self.evidence),
            "sdk_sidecars_sha256": {},
            "gdk_sdk_validation_independently_verified": False,
            "real_msix_pass": False, "e2e_pass": False, "store_submitted": False,
        }
        self.received = {
            **{key: self.expected[key] for key in (
                "request_id", "source_sha", "cas_commit_sha",
                "factory_head_sha", "package_sha256", "validation_log_sha256")},
            "sdk_sidecars_sha256": {},
            "independent_manifest_anchor_matched": True,
            "gdk_sdk_validation_independently_verified": False,
            "real_msix_pass": False, "e2e_pass": False, "store_submitted": False,
        }

    def run_gate(self):
        with mock.patch("gdk_e2e_trusted_export.trusted_intake",
                        return_value=self.trusted) as trusted, \
             mock.patch("gdk_e2e_trusted_export._verify_source_inventory"), \
             mock.patch("gdk_e2e_trusted_export.export_handoff",
                        side_effect=self.fake_export) as exported, \
             mock.patch("gdk_e2e_trusted_export.verify_handoff",
                        side_effect=self.fake_receive) as received:
            value = export_trusted(self.anchor, self.trusted_sha, self.plan,
                                   self.evidence, self.package_dir,
                                   self.log, self.output)
            return value, trusted, exported, received

    def fake_export(self, *args):
        self.output.mkdir()
        (self.output / "handoff.json").write_bytes(b'{"synthetic":"handoff"}')
        return self.manifest

    def fake_receive(self, output_dir, manifest_sha):
        return {**self.received, "manifest_sha256": manifest_sha}

    def test_success_does_not_promote_sdk_or_e2e(self):
        result, trusted, exported, received = self.run_gate()
        self.assertEqual(result["status"], "GDK_TRUSTED_E2E_HANDOFF_CHECK_ONLY_PASS")
        self.assertEqual(result["trusted_prebuild_handoff_sha256"], self.trusted_sha)
        self.assertEqual(result["handoff_manifest_sha256"],
                         digest(self.output / "handoff.json"))
        self.assertTrue(result["prebuild_trust_chain_verified"])
        self.assertTrue(result["local_transfer_bytes_verified"])
        self.assertFalse(result["real_msix_pass"])
        self.assertFalse(result["e2e_pass"])
        self.assertFalse(result["gdk_sdk_validation_independently_verified"])
        self.assertFalse(result["store_submitted"])
        self.assertEqual(trusted.call_args.args[1], self.trusted_sha)
        exported.assert_called_once()
        received.assert_called_once()

    def test_missing_independent_anchor_rejected_before_export(self):
        with self.assertRaises(HoldError):
            export_trusted(self.anchor, "", self.plan, self.evidence,
                           self.package_dir, self.log, self.output)
        self.assertFalse(self.output.exists())

    def test_forged_anchor_rejected_before_export(self):
        with self.assertRaisesRegex(ConflictError, "independent prebuild"):
            export_trusted(self.anchor, "0" * 64, self.plan, self.evidence,
                           self.package_dir, self.log, self.output)
        self.assertFalse(self.output.exists())

    def test_trusted_intake_failure_stops_export(self):
        self.trusted["status"] = "HOLD"
        with self.assertRaisesRegex(ConflictError, "has not passed"):
            self.run_gate()
        self.assertFalse(self.output.exists())

    def test_false_trust_claim_stops_export(self):
        self.trusted["prebuild_trust_chain_verified"] = False
        with self.assertRaisesRegex(ConflictError, "trust chain"):
            self.run_gate()
        self.assertFalse(self.output.exists())

    def test_forged_real_msix_claim_stops_export(self):
        self.trusted["real_msix_pass"] = True
        with self.assertRaisesRegex(ConflictError, "unearned"):
            self.run_gate()
        self.assertFalse(self.output.exists())

    def test_exported_plan_hash_mismatch_rejected(self):
        self.manifest["sdk_pack_plan_sha256"] = "0" * 64
        with self.assertRaisesRegex(ConflictError, "evidence SHA"):
            self.run_gate()

    def test_exported_package_sha_mismatch_rejected(self):
        self.manifest["package_sha256"] = "0" * 64
        with self.assertRaisesRegex(ConflictError, "package_sha256"):
            self.run_gate()

    def test_changed_trusted_anchor_during_export_rejected(self):
        def mutate(*args):
            value = self.fake_export(*args)
            self.anchor.write_bytes(b'{"tampered":true}')
            return value
        with mock.patch("gdk_e2e_trusted_export.trusted_intake",
                        return_value=self.trusted), \
             mock.patch("gdk_e2e_trusted_export.export_handoff",
                        side_effect=mutate), \
             mock.patch("gdk_e2e_trusted_export.verify_handoff",
                        side_effect=self.fake_receive):
            with self.assertRaisesRegex(ConflictError, "changed during"):
                export_trusted(self.anchor, self.trusted_sha, self.plan,
                               self.evidence, self.package_dir,
                               self.log, self.output)

    def test_sidecar_mutation_between_trusted_intake_and_export_rejected(self):
        # Both the later exporter and receiver agree, but the original SDK
        # inventory from the trusted intake has different sidecar bytes.
        self.trusted["output_files_sha256"]["symbols.zip"] = "a" * 64
        self.manifest["sdk_sidecars_sha256"] = {"sdk-sidecar-symbols.zip": "b" * 64}
        self.received["sdk_sidecars_sha256"] = dict(self.manifest["sdk_sidecars_sha256"])
        with self.assertRaisesRegex(ConflictError, "sidecar inventory changed"):
            self.run_gate()

    def test_matching_trusted_sidecar_inventory_passes(self):
        self.trusted["output_files_sha256"]["symbols.zip"] = "a" * 64
        self.manifest["sdk_sidecars_sha256"] = {"sdk-sidecar-symbols.zip": "a" * 64}
        self.received["sdk_sidecars_sha256"] = dict(self.manifest["sdk_sidecars_sha256"])
        result, *_ = self.run_gate()
        self.assertEqual(result["sdk_sidecars_sha256"], self.received["sdk_sidecars_sha256"])

    def test_original_sdk_filename_swap_rejected(self):
        self.manifest["original_sdk_filename"] = "Other.msixvc"
        with self.assertRaisesRegex(ConflictError, "original SDK filename"):
            self.run_gate()

    def test_sdk_package_size_swap_rejected(self):
        self.manifest["package_size_bytes"] = 124
        with self.assertRaisesRegex(ConflictError, "package_size_bytes"):
            self.run_gate()

    def test_sdk_version_claim_swap_rejected(self):
        self.manifest["sdk_version_claim"] = "Forged SDK"
        with self.assertRaisesRegex(ConflictError, "sdk_version_claim"):
            self.run_gate()

    def test_missing_trusted_sdk_inventory_rejected(self):
        self.trusted.pop("output_files_sha256")
        with self.assertRaisesRegex(ConflictError, "inventory missing"):
            self.run_gate()

    def seed_real_sdk_inventory(self):
        package = self.package_dir / "SignalSprint.msixvc"
        sidecar = self.package_dir / "symbols.zip"
        package.write_bytes(b"synthetic GDK package, not a real MSIXVC")
        sidecar.write_bytes(b"synthetic symbols")
        self.trusted["package_sha256"] = digest(package)
        self.trusted["output_files_sha256"] = {
            package.name: digest(package), sidecar.name: digest(sidecar),
        }
        return package, sidecar

    def test_original_sdk_inventory_unchanged_precheck_passes(self):
        self.seed_real_sdk_inventory()
        _verify_source_inventory(self.trusted, self.package_dir)

    def test_original_sdk_sidecar_changed_before_export_rejected(self):
        _, sidecar = self.seed_real_sdk_inventory()
        sidecar.write_bytes(b"tampered symbols")
        with self.assertRaisesRegex(ConflictError, "bytes changed before export"):
            _verify_source_inventory(self.trusted, self.package_dir)

    def test_original_sdk_package_changed_before_export_rejected(self):
        package, _ = self.seed_real_sdk_inventory()
        package.write_bytes(b"tampered package")
        with self.assertRaisesRegex(ConflictError, "bytes changed before export"):
            _verify_source_inventory(self.trusted, self.package_dir)

    def test_original_sdk_unregistered_file_before_export_rejected(self):
        self.seed_real_sdk_inventory()
        (self.package_dir / "extra.ekb").write_bytes(b"extra")
        with self.assertRaisesRegex(ConflictError, "inventory changed before export"):
            _verify_source_inventory(self.trusted, self.package_dir)

    def test_original_sdk_missing_file_before_export_rejected(self):
        _, sidecar = self.seed_real_sdk_inventory()
        sidecar.unlink()
        with self.assertRaisesRegex(ConflictError, "inventory changed before export"):
            _verify_source_inventory(self.trusted, self.package_dir)

    def test_original_sdk_inventory_digest_forgery_rejected(self):
        self.seed_real_sdk_inventory()
        self.trusted["output_files_sha256"]["symbols.zip"] = "not-a-sha"
        with self.assertRaisesRegex(ConflictError, "digest invalid"):
            _verify_source_inventory(self.trusted, self.package_dir)

    def test_receiver_sidecar_mismatch_rejected(self):
        self.received["sdk_sidecars_sha256"] = {"sdk-sidecar-forged.ekb": "0" * 64}
        with self.assertRaisesRegex(ConflictError, "sidecar inventory"):
            self.run_gate()


if __name__ == "__main__":
    unittest.main()
