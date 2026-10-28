"""Read-only GDK post-CAS build-intake contract, without Store or CAS writes."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import gdk_build_intake as intake
from package_identity_provisioner import (
    ConflictError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY, PINNED_SIGNAL_SPRINT_JOB,
)

SOURCE = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
CAS = "a" * 40
BUILD = "b" * 40


class GdkBuildIntakeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.exe = b"MZ" + b"sample-only" * 100
        self.exe_sha = hashlib.sha256(self.exe).hexdigest()
        self.approved = {
            **PINNED_SIGNAL_SPRINT_JOB, **PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
            "schema_version": "1.0", "reviewed": True,
            "verified_source_sha": SOURCE, "package_sha256": self.exe_sha,
            "signature_status": "QA_UNSIGNED", "source": "partner_center_user_provided",
            "identity_source": "USER_PROVIDED_PARTNER_CENTER",
            "packaging_family": "GDK", "provided_at": "2026-10-28T10:49:00+09:00",
        }
        self.zip = self.root / "pinned.zip"
        self.make_zip()
        self.zip_sha = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        p1 = patch.object(intake, "EXE_SHA256", self.exe_sha)
        p2 = patch.object(intake, "ARTIFACT_SHA256", self.zip_sha)
        p1.start()
        p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)
        self.calls = []
        self.git_patch = patch.object(intake, "_git", side_effect=self.fake_git)
        self.git_patch.start()
        self.addCleanup(self.git_patch.stop)

    def make_zip(self, extra=None):
        provenance = {**PINNED_SIGNAL_SPRINT_JOB,
                      "executable": "SignalSprint.exe", "executable_sha256": self.exe_sha,
                      "artifact_kind": "EXE_QA_UNSIGNED"}
        request = {**PINNED_SIGNAL_SPRINT_JOB, "dry_run": True}
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("SignalSprint.exe", self.exe)
            z.writestr("provenance.json", json.dumps(provenance))
            z.writestr("provisioner-request.json", json.dumps(request))
            if extra:
                z.writestr("extra.exe", b"bad")

    def fake_git(self, repo, *args):
        self.calls.append(args)
        if args == ("rev-parse", "refs/heads/" + PINNED_SIGNAL_SPRINT_JOB["source_branch"]):
            return SOURCE.encode()
        if args == ("rev-list", "--parents", "-n", "1", CAS):
            return (CAS + " " + SOURCE).encode()
        if args == ("rev-parse", "HEAD"):
            return BUILD.encode()
        if args == ("symbolic-ref", "--short", "HEAD"):
            return b"codex/game-signal-sprint-gdk-build-fixture"
        if args == ("status", "--porcelain"):
            return b""
        if args == ("rev-list", "--reverse", CAS + ".." + BUILD):
            return b""
        if args == ("rev-parse", CAS + "^"):
            return SOURCE.encode()
        if args == ("merge-base", "--is-ancestor", CAS, BUILD):
            return b""
        if args == ("diff-tree", "--no-commit-id", "--name-only", "-r", CAS):
            return intake.APPROVED_PATH.encode()
        if args in (("show", CAS + ":" + intake.APPROVED_PATH),
                    ("show", BUILD + ":" + intake.APPROVED_PATH)):
            return json.dumps(self.approved).encode()
        raise AssertionError(args)

    def test_handoff_binds_actual_cas_and_pinned_exe_without_building(self):
        result = intake.create_intake(self.root, self.zip, CAS, BUILD)
        self.assertEqual(result["status"], "GDK_BUILD_INPUT_CHECK_ONLY")
        self.assertEqual(result["source_sha"], SOURCE)
        self.assertEqual(result["cas_commit_sha"], CAS)
        self.assertEqual(result["factory_head_sha"], BUILD)
        self.assertEqual(result["pinned_exe"]["executable_sha256"], self.exe_sha)
        self.assertEqual(result["identity"]["store_id"], "9N21MJM7S57P")
        self.assertIsNone(result["package_version"])
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["store_submitted"])
        self.assertIn(("merge-base", "--is-ancestor", CAS, BUILD), self.calls)

    def test_moved_immutable_source_ref_rejected(self):
        original = self.fake_git

        def moved_source(repo, *args):
            if args == ("rev-parse", "refs/heads/" + PINNED_SIGNAL_SPRINT_JOB["source_branch"]):
                return ("f" * 40).encode()
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=moved_source):
            with self.assertRaisesRegex(ConflictError, "source branch moved"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_merge_cas_rejected_even_with_correct_first_parent(self):
        original = self.fake_git

        def merged_cas(repo, *args):
            if args == ("rev-list", "--parents", "-n", "1", CAS):
                return (CAS + " " + SOURCE + " " + "f" * 40).encode()
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=merged_cas):
            with self.assertRaisesRegex(ConflictError, "single-parent"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_false_signed_claim_rejected(self):
        self.approved["signature_status"] = "SIGNED"
        with self.assertRaisesRegex(ConflictError, "QA_UNSIGNED"):
            intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_wrong_approved_identity_rejected(self):
        self.approved["store_id"] = "9N21MJM7S57Q"
        with self.assertRaisesRegex(ConflictError, "reviewed Identity"):
            intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_extra_approved_field_rejected(self):
        self.approved["version"] = "1.0.0.0"
        with self.assertRaisesRegex(ConflictError, "schema"):
            intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_wrong_source_rejected(self):
        self.approved["source_sha"] = "f" * 40
        with self.assertRaisesRegex(ConflictError, "immutable source"):
            intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_cas_cannot_be_immutable_source(self):
        with self.assertRaisesRegex(ConflictError, "CAS/build SHA"):
            intake.create_intake(self.root, self.zip, SOURCE, BUILD)

    def test_pinned_artifact_byte_tampering_rejected(self):
        self.zip.write_bytes(self.zip.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ConflictError, "ZIP bytes changed"):
            intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_extra_zip_member_rejected_even_with_new_digest(self):
        self.make_zip(extra=True)
        with patch.object(intake, "ARTIFACT_SHA256", hashlib.sha256(self.zip.read_bytes()).hexdigest()):
            with self.assertRaisesRegex(ConflictError, "member set changed"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_wrong_git_checkout_head_rejected(self):
        original = self.fake_git

        def wrong_head(repo, *args):
            if args == ("rev-parse", "HEAD"):
                return ("f" * 40).encode()
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=wrong_head):
            with self.assertRaisesRegex(ConflictError, "checkout HEAD"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_wrong_cas_parent_rejected(self):
        original = self.fake_git

        def wrong_parent(repo, *args):
            if args == ("rev-list", "--parents", "-n", "1", CAS):
                return (CAS + " " + "f" * 40).encode()
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=wrong_parent):
            with self.assertRaisesRegex(ConflictError, "single-parent"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_cas_must_change_only_identity(self):
        original = self.fake_git

        def wrong_files(repo, *args):
            if args == ("diff-tree", "--no-commit-id", "--name-only", "-r", CAS):
                return (intake.APPROVED_PATH + "\\nproducts/signal-sprint/main.py").encode()
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=wrong_files):
            with self.assertRaisesRegex(ConflictError, "outside approved Identity"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_build_branch_cannot_change_approved_identity(self):
        original = self.fake_git

        def changed_build_identity(repo, *args):
            if args == ("show", BUILD + ":" + intake.APPROVED_PATH):
                return json.dumps({**self.approved, "store_id": "9N21MJM7S57Q"}).encode()
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=changed_build_identity):
            with self.assertRaisesRegex(ConflictError, "build HEAD changed"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_cas_git_ancestry_failure_rejected(self):
        original = self.fake_git

        def no_ancestor(repo, *args):
            if args == ("merge-base", "--is-ancestor", CAS, BUILD):
                raise ConflictError("GDK build Git ancestry/content verification failed")
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=no_ancestor):
            with self.assertRaisesRegex(ConflictError, "ancestry"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_generic_msix_branch_rejected(self):
        original = self.fake_git

        def generic_branch(repo, *args):
            if args == ("symbolic-ref", "--short", "HEAD"):
                return b"codex/game-msix-build"
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=generic_branch):
            with self.assertRaisesRegex(ConflictError, "dedicated Factory contract"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_legacy_factory_branch_rejected(self):
        original = self.fake_git

        def legacy_branch(repo, *args):
            if args == ("symbolic-ref", "--short", "HEAD"):
                return b"codex/game-gdk-signal-sprint-build-old"
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=legacy_branch):
            with self.assertRaisesRegex(ConflictError, "dedicated Factory contract"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_dirty_build_checkout_rejected(self):
        original = self.fake_git

        def dirty(repo, *args):
            if args == ("status", "--porcelain"):
                return b"?? untracked-file"
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=dirty):
            with self.assertRaisesRegex(ConflictError, "checkout is dirty"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_detached_head_rejected(self):
        original = self.fake_git

        def detached(repo, *args):
            if args == ("symbolic-ref", "--short", "HEAD"):
                raise ConflictError("GDK build Git ancestry/content verification failed")
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=detached):
            with self.assertRaisesRegex(ConflictError, "verification failed"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_post_cas_edit_then_revert_product_rejected(self):
        original = self.fake_git
        changed, reverted = "c" * 40, "d" * 40

        def tamper_history(repo, *args):
            if args == ("rev-list", "--reverse", CAS + ".." + BUILD):
                return (changed + "\\n" + reverted).encode()
            if args == ("rev-list", "--parents", "-n", "1", changed):
                return (changed + " " + CAS).encode()
            if args == ("diff-tree", "--no-commit-id", "--name-only", "-r", changed):
                return b"products/signal-sprint/main.py"
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=tamper_history):
            with self.assertRaisesRegex(ConflictError, "product change in history"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_post_cas_merge_commit_rejected(self):
        original = self.fake_git
        merged = "c" * 40

        def merge_history(repo, *args):
            if args == ("rev-list", "--reverse", CAS + ".." + BUILD):
                return merged.encode()
            if args == ("rev-list", "--parents", "-n", "1", merged):
                return (merged + " " + CAS + " " + "d" * 40).encode()
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=merge_history):
            with self.assertRaisesRegex(ConflictError, "post-CAS merge"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)

    def test_post_cas_docs_only_change_allowed(self):
        original = self.fake_git
        doc_commit = "c" * 40

        def docs_history(repo, *args):
            if args == ("rev-list", "--reverse", CAS + ".." + BUILD):
                return doc_commit.encode()
            if args == ("rev-list", "--parents", "-n", "1", doc_commit):
                return (doc_commit + " " + CAS).encode()
            if args == ("diff-tree", "--no-commit-id", "--name-only", "-r", doc_commit):
                return b"docs/SIGNAL_SPRINT_GDK_BUILD.md"
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=docs_history):
            result = intake.create_intake(self.root, self.zip, CAS, BUILD)
        self.assertEqual(result["status"], "GDK_BUILD_INPUT_CHECK_ONLY")

    def test_post_cas_identity_edit_rejected(self):
        original = self.fake_git
        edit_commit = "c" * 40

        def identity_history(repo, *args):
            if args == ("rev-list", "--reverse", CAS + ".." + BUILD):
                return edit_commit.encode()
            if args == ("rev-list", "--parents", "-n", "1", edit_commit):
                return (edit_commit + " " + CAS).encode()
            if args == ("diff-tree", "--no-commit-id", "--name-only", "-r", edit_commit):
                return intake.APPROVED_PATH.encode()
            return original(repo, *args)

        with patch.object(intake, "_git", side_effect=identity_history):
            with self.assertRaisesRegex(ConflictError, "product change in history"):
                intake.create_intake(self.root, self.zip, CAS, BUILD)


if __name__ == "__main__":
    unittest.main()
