"""Synthetic, no-GDK-SDK regression tests for Windows E2E byte handoff."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gdk_e2e_handoff import export_handoff
from package_identity_provisioner import ConflictError, PINNED_SIGNAL_SPRINT_JOB


def sha(value):
    return hashlib.sha256(value).hexdigest()


class GdkE2eHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.plan_path = self.root / "plan.json"
        self.evidence_path = self.root / "result.json"
        self.log = self.root / "validation.log"
        self.log.write_bytes(b"synthetic log: NOT real SDK validation\n")
        self.package_dir = self.root / "sdk-output"
        self.package_dir.mkdir()
        self.package = self.package_dir / "SignalSprint.msixvc2"
        self.package.write_bytes(b"synthetic package: NOT real GDK package")
        self.target = self.root / "handoff"
        argv = ["makepkg.exe", "pack", "/msixvc2", "/d",
                str(self.root / "stage"), "/pc", "/pd",
                str(self.package_dir), "/validationcritical"]
        self.plan = {
            "schema_version": 1,
            "status": "GDK_SDK_PACK_PLAN_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "package_format": "MSIXVC2",
            "request_id": PINNED_SIGNAL_SPRINT_JOB["request_id"],
            "source_sha": PINNED_SIGNAL_SPRINT_JOB["source_sha"],
            "cas_commit_sha": "b" * 40,
            "factory_head_sha": "c" * 40,
            "package_version": "1.0.1.0",
            "reviewed_display_name": "Signal Sprint",
            "verified_receipt_sha256": "d" * 64,
            "staging_files_sha256": {
                "SignalSprint.exe": "e" * 64,
                **{f"asset{i}.png": "f" * 64 for i in range(5)},
            },
            "sdk_command_argv_not_executed": argv,
            "sdk_required": "October 2026 GDK or later with managed makepkg.exe",
            "msixvc2_preview_public_certification_blocked": False,
            "public_release_requires_certification": True,
            "next_stage": "WINDOWS_GDK_SDK_VALIDATE_AND_PACK_WITH_FRESH_RECHECK",
            "gdk_sdk_validated": False,
            "real_msixvc_built": False,
            "store_submitted": False,
        }
        self.evidence = {k: self.plan[k] for k in (
            "schema_version", "partner_center_selection", "package_format",
            "request_id", "source_sha", "cas_commit_sha", "factory_head_sha",
            "package_version", "reviewed_display_name",
            "verified_receipt_sha256", "staging_files_sha256", "store_submitted",
        )}
        self.evidence.update({
            "status": "GDK_SDK_PACK_EXECUTED",
            "sdk_command_argv": argv,
            "sdk_executable": "makepkg.exe",
            "sdk_version": "October 2026 GDK SDK",
            "sdk_exit_code": 0,
            "validation_log_sha256": sha(self.log.read_bytes()),
            "package_filename": self.package.name,
            "package_sha256": sha(self.package.read_bytes()),
            "package_size_bytes": self.package.stat().st_size,
            "output_files_sha256": {self.package.name: sha(self.package.read_bytes())},
        })

    def export(self, target=None):
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        return export_handoff(self.plan_path, self.evidence_path,
                              self.package_dir, self.log, target or self.target)

    def test_export_preserves_package_and_log_bytes_without_approval(self):
        manifest = self.export()
        self.assertEqual(manifest["source_sha"], PINNED_SIGNAL_SPRINT_JOB["source_sha"])
        self.assertEqual(manifest["type"], "game")
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["sdk_sidecars_sha256"], {})
        self.assertEqual(manifest["partner_center_selection"], "GDK_GAME")
        self.assertEqual(manifest["package_format"], "MSIXVC2")
        self.assertFalse(manifest["real_msix_pass"])
        self.assertFalse(manifest["e2e_pass"])
        self.assertFalse(manifest["gdk_sdk_validation_independently_verified"])
        self.assertEqual((self.target / "package.msixvc2").read_bytes(),
                         self.package.read_bytes())
        self.assertEqual((self.target / "validation.log").read_bytes(),
                         self.log.read_bytes())
        self.assertEqual(json.loads((self.target / "handoff.json").read_text()), manifest)
        self.assertEqual({p.name for p in self.target.iterdir()},
                         {"package.msixvc2", "validation.log", "handoff.json"})

    def test_sdk_sidecars_preserved_with_hashes(self):
        for name, data in (("SignalSprint.ekb", b"synthetic EKB"),
                           ("SubmissionValidator.xml", b"<synthetic/>"),
                           ("symbols.zip", b"synthetic symbols")):
            (self.package_dir / name).write_bytes(data)
            self.evidence["output_files_sha256"][name] = sha(data)
        manifest = self.export()
        self.assertEqual(len(manifest["sdk_sidecars_sha256"]), 3)
        for original in ("SignalSprint.ekb", "SubmissionValidator.xml", "symbols.zip"):
            transfer = "sdk-sidecar-" + original
            self.assertEqual((self.target / transfer).read_bytes(),
                             (self.package_dir / original).read_bytes())
            self.assertEqual(manifest["sdk_sidecars_sha256"][transfer],
                             sha((self.package_dir / original).read_bytes()))
        self.assertFalse(manifest["real_msix_pass"])

    def test_sidecar_tamper_rejected_without_partial_handoff(self):
        extra = self.package_dir / "SignalSprint.ekb"
        extra.write_bytes(b"original")
        self.evidence["output_files_sha256"][extra.name] = sha(b"original")
        extra.write_bytes(b"tampered")
        with self.assertRaisesRegex(ConflictError, "sidecar bytes"):
            self.export()
        self.assertFalse(self.target.exists())

    def test_sidecar_mutation_during_copy_cleans_destination(self):
        extra = self.package_dir / "SignalSprint.ekb"
        extra.write_bytes(b"original")
        self.evidence["output_files_sha256"][extra.name] = sha(extra.read_bytes())
        original = export_handoff.__globals__["_copy_verified"]
        def fail_sidecar(source, target, *args):
            if source.name == "SignalSprint.ekb":
                raise ConflictError("simulated sidecar copy failure")
            return original(source, target, *args)
        with mock.patch("gdk_e2e_handoff._copy_verified", side_effect=fail_sidecar):
            with self.assertRaisesRegex(ConflictError, "sidecar copy failure"):
                self.export()
        self.assertFalse(self.target.exists())

    def test_existing_handoff_never_overwritten(self):
        self.target.mkdir()
        (self.target / "keep.txt").write_text("untouched")
        with self.assertRaisesRegex(ConflictError, "already exists"):
            self.export()
        self.assertEqual((self.target / "keep.txt").read_text(), "untouched")

    def test_wrong_package_bytes_rejected_without_output(self):
        self.package.write_bytes(b"modified after evidence")
        with self.assertRaisesRegex(ConflictError, "package bytes"):
            self.export()
        self.assertFalse(self.target.exists())

    def test_wrong_validation_log_rejected_without_output(self):
        self.log.write_bytes(b"modified log")
        with self.assertRaisesRegex(ConflictError, "validation log bytes"):
            self.export()
        self.assertFalse(self.target.exists())

    def test_wrong_source_rejected_without_output(self):
        self.evidence["source_sha"] = "a" * 40
        with self.assertRaisesRegex(ConflictError, "source_sha"):
            self.export()
        self.assertFalse(self.target.exists())

    def test_handoff_inside_sdk_output_rejected(self):
        with self.assertRaisesRegex(ConflictError, "isolated"):
            self.export(self.package_dir / "handoff")
        self.assertEqual([p.name for p in self.package_dir.iterdir()],
                         ["SignalSprint.msixvc2"])

    def test_failed_copy_removes_only_fresh_output(self):
        with mock.patch("gdk_e2e_handoff._copy_verified",
                        side_effect=ConflictError("simulated copy error")):
            with self.assertRaisesRegex(ConflictError, "simulated"):
                self.export()
        self.assertFalse(self.target.exists())
        self.assertTrue(self.package.exists())

    def test_claimed_store_submission_rejected(self):
        self.evidence["store_submitted"] = True
        with self.assertRaisesRegex(ConflictError, "store_submitted"):
            self.export()
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
