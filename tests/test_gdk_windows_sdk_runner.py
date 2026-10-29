"""Synthetic tests for guarded Windows GDK runner. No real SDK or Store calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gdk_windows_sdk_runner import _make_evidence, _scan_sdk_output, run_windows_pack
from package_identity_provisioner import ConflictError, HoldError


def sha(value):
    return hashlib.sha256(value).hexdigest()


class GdkWindowsSdkRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.staging = self.root / "staging"
        self.output = self.root / "output"
        self.factory = self.root / "factory"
        for directory in (self.staging, self.output, self.factory):
            directory.mkdir()
        self.anchor = self.root / "handoff.json"
        self.plan_path = self.root / "plan.json"
        self.log = self.root / "sdk.log"
        self.evidence = self.root / "evidence.json"
        self.fake_makepkg = self.root / "makepkg.exe"
        self.fake_makepkg.write_bytes(b"synthetic fake makepkg, never executed")
        self.plan = {
            "request_id": "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e",
            "source_sha": "c058cbf7fe38e02d929c67d047d717ff74bd522e",
            "cas_commit_sha": "b" * 40, "factory_head_sha": "c" * 40,
            "package_version": "1.0.1.0", "reviewed_display_name": "Signal Sprint",
            "verified_receipt_sha256": "a" * 64,
            "staging_files_sha256": {"SignalSprint.exe": "f" * 64},
            "sdk_command_argv_not_executed": [
                "makepkg.exe", "pack", "/msixvc2", "/d", str(self.staging),
                "/pc", "/pd", str(self.output), "/validationcritical"],
        }
        canonical = json.dumps(self.plan, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode()
        self.handoff = {"sdk_pack_plan_sha256": sha(canonical)}
        self.anchor.write_text(json.dumps(self.handoff))
        self.plan_path.write_text(json.dumps(self.plan))
        self.args = dict(
            factory_checkout=self.factory, artifact_zip=self.root / "artifact.zip",
            cas_sha="b" * 40, build_sha="c" * 40,
            factory_gate_script=self.root / "gate.py",
            trusted_factory_gate_sha256="e" * 64,
            staging_dir=self.staging, package_version="1.0.1.0",
            reviewed_display_name="Signal Sprint",
            preflight_receipt=self.root / "preflight.json",
            output_dir=self.output, sdk_handoff=self.anchor,
            trusted_handoff_sha256=sha(self.anchor.read_bytes()),
            pack_plan=self.plan_path, sdk_version_claim="GDK October 2026",
            validation_log=self.log, result_evidence=self.evidence,
            trusted_makepkg_sha256=sha(self.fake_makepkg.read_bytes()),
        )

    def patches(self):
        return (mock.patch("gdk_windows_sdk_runner.create_sdk_handoff",
                           return_value=self.handoff),
                mock.patch("gdk_sdk_pack_plan.make_pack_plan", return_value=self.plan))

    def test_check_only_never_executes_sdk_or_writes_evidence(self):
        a, b = self.patches()
        with a, b, mock.patch("gdk_windows_sdk_runner.subprocess.run") as run:
            result = run_windows_pack(**self.args)
            self.assertEqual(result["status"], "GDK_WINDOWS_SDK_EXECUTION_CHECK_ONLY_READY")
            self.assertFalse(result["sdk_executed"])
            self.assertFalse(self.evidence.exists())
            run.assert_not_called()

    def test_wrong_independent_anchor_rejected(self):
        with self.assertRaisesRegex(ConflictError, "independent handoff SHA"):
            run_windows_pack(**{**self.args, "trusted_handoff_sha256": "0" * 64})
        self.assertFalse(self.evidence.exists())

    def test_changed_plan_rejected_before_execution(self):
        self.plan["package_version"] = "2.0.0.0"
        self.plan_path.write_text(json.dumps(self.plan))
        a, b = self.patches()
        with a, b, mock.patch("gdk_windows_sdk_runner.subprocess.run") as run:
            with self.assertRaisesRegex(ConflictError, "plan SHA"):
                run_windows_pack(**{**self.args, "execute": True})
            run.assert_not_called()

    def test_unapproved_makepkg_digest_rejected_without_running_sdk(self):
        a, b = self.patches()
        with a, b, mock.patch("gdk_windows_sdk_runner._sdk_executable",
                              return_value=self.fake_makepkg), \
             mock.patch("gdk_windows_sdk_runner.subprocess.run") as run:
            with self.assertRaisesRegex(ConflictError, "independently approved bytes"):
                run_windows_pack(**{**self.args, "execute": True,
                                    "trusted_makepkg_sha256": "0" * 64})
            run.assert_not_called()

    def test_successful_synthetic_sdk_output_remains_unapproved(self):
        def fake_sdk(command, stdout, **kwargs):
            stdout.write(b"synthetic SDK output, not validation\n")
            (self.output / "SignalSprint.msixvc").write_bytes(b"fake package")
            (self.output / "symbols.zip").write_bytes(b"fake symbols")
            return mock.Mock(returncode=0)
        a, b = self.patches()
        with a, b, mock.patch("gdk_windows_sdk_runner._sdk_executable",
                              return_value=self.fake_makepkg), \
             mock.patch("gdk_windows_sdk_runner.subprocess.run",
                        side_effect=fake_sdk) as run, \
             mock.patch("gdk_windows_sdk_runner.recheck", return_value={
                 "staging_files_sha256": self.plan["staging_files_sha256"],
                 "verified_receipt_sha256": self.plan["verified_receipt_sha256"]}), \
             mock.patch("gdk_windows_sdk_runner.intake", return_value={
                 "status": "GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS",
                 "package_sha256": sha(b"fake package"),
                 "validation_log_sha256": sha(b"synthetic SDK output, not validation\n"),
                 "output_files_sha256": {
                     "SignalSprint.msixvc": sha(b"fake package"),
                     "symbols.zip": sha(b"fake symbols")}}):
            result = run_windows_pack(**{**self.args, "execute": True})
        self.assertTrue(result["sdk_executed"])
        self.assertFalse(result["real_msix_pass"])
        self.assertFalse(result["e2e_pass"])
        self.assertFalse(result["gdk_sdk_validation_independently_verified"])
        self.assertTrue(self.evidence.exists())
        self.assertEqual(json.loads(self.evidence.read_text())["sdk_exit_code"], 0)
        self.assertEqual(run.call_args.kwargs["shell"], False)

    def _run_with_intake_mutation(self, mutate=None, changed_recheck=False):
        package_bytes = b"original synthetic package"
        log_bytes = b"synthetic SDK output, not validation\n"
        original_inventory = {"SignalSprint.msixvc": sha(package_bytes)}
        initial_post = {
            "staging_files_sha256": self.plan["staging_files_sha256"],
            "verified_receipt_sha256": self.plan["verified_receipt_sha256"],
        }

        def fake_sdk(command, stdout, **kwargs):
            stdout.write(log_bytes)
            (self.output / "SignalSprint.msixvc").write_bytes(package_bytes)
            return mock.Mock(returncode=0)

        def fake_intake(*args):
            if mutate == "package":
                (self.output / "SignalSprint.msixvc").write_bytes(b"changed after SDK scan")
            elif mutate == "log":
                self.log.write_bytes(b"changed log after SDK scan")
            return {
                "status": "GDK_PACKAGE_BYTES_AND_SDK_RECEIPT_CHECK_PASS",
                "package_sha256": original_inventory["SignalSprint.msixvc"],
                "validation_log_sha256": sha(log_bytes),
                "output_files_sha256": original_inventory,
            }

        changed_post = {**initial_post, "verified_receipt_sha256": "0" * 64}
        recheck_results = [initial_post, changed_post if changed_recheck else initial_post]
        a, b = self.patches()
        with a, b, mock.patch("gdk_windows_sdk_runner._sdk_executable",
                              return_value=self.fake_makepkg), \
             mock.patch("gdk_windows_sdk_runner.subprocess.run",
                        side_effect=fake_sdk), \
             mock.patch("gdk_windows_sdk_runner.recheck",
                        side_effect=recheck_results), \
             mock.patch("gdk_windows_sdk_runner.intake",
                        side_effect=fake_intake):
            with self.assertRaises(ConflictError):
                run_windows_pack(**{**self.args, "execute": True})
        self.assertFalse(self.evidence.exists(), "failed intake must not leave trusted evidence")

    def test_package_swap_during_intake_rejected(self):
        self._run_with_intake_mutation(mutate="package")

    def test_validation_log_swap_during_intake_rejected(self):
        self._run_with_intake_mutation(mutate="log")

    def test_cas_staging_change_during_intake_rejected(self):
        self._run_with_intake_mutation(changed_recheck=True)

    def test_reject_multiple_packages(self):
        (self.output / "first.msixvc").write_bytes(b"one")
        (self.output / "second.msixvc2").write_bytes(b"two")
        with self.assertRaisesRegex(ConflictError, "exactly one"):
            _scan_sdk_output(self.output)

    def test_reject_unreviewed_sdk_sidecar(self):
        (self.output / "SignalSprint.msixvc").write_bytes(b"one")
        (self.output / "rogue.exe").write_bytes(b"two")
        with self.assertRaisesRegex(ConflictError, "unreviewed sidecar"):
            _scan_sdk_output(self.output)

    def test_reject_invalid_sdk_version_claim(self):
        with self.assertRaises(HoldError):
            _make_evidence(self.plan, "", "SignalSprint.msixvc",
                           {"SignalSprint.msixvc": "a" * 64}, 1, "b" * 64)


if __name__ == "__main__":
    unittest.main()
