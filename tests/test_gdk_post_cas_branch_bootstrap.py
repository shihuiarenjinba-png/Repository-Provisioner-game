"""Synthetic local Git fixtures; never mutate real Factory or Partner Center."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import gdk_post_cas_branch_bootstrap as bootstrap
from package_identity_provisioner import ConflictError


class PostCasBranchBootstrapTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic CI")
        self.git("config", "user.email", "ci@example.invalid")
        product = self.repo / "products" / "signal-sprint"
        (product / "store").mkdir(parents=True)
        (product / "main.py").write_text("immutable game\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic source")
        self.source = self.git("rev-parse", "HEAD")
        self.job = dict(bootstrap.PINNED_SIGNAL_SPRINT_JOB, source_sha=self.source)
        pin = patch.object(bootstrap, "PINNED_SIGNAL_SPRINT_JOB", self.job)
        pin.start()
        self.addCleanup(pin.stop)
        self.git("branch", self.job["source_branch"], self.source)
        self.cas_branch = "codex/game-signal-sprint-gdk-cas-" + self.source[:12]
        self.git("switch", "-qc", self.cas_branch)
        self.approved = {
            **self.job,
            **bootstrap.PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
            "schema_version": "1.0", "reviewed": True,
            "verified_source_sha": self.source,
            "package_sha256": bootstrap.EXE_SHA256,
            "source": "partner_center_user_provided",
            "identity_source": "USER_PROVIDED_PARTNER_CENTER",
            "packaging_family": "GDK",
            "signature_status": "QA_UNSIGNED",
            "provided_at": "2026-10-28T12:00:00Z",
        }
        self.assertEqual(set(self.approved), bootstrap.APPROVED_FIELDS)
        (self.repo / bootstrap.APPROVED_PATH).write_text(
            json.dumps(self.approved, sort_keys=True) + "\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic approved Identity CAS")
        self.cas = self.git("rev-parse", "HEAD")
        self.build_branch = "codex/game-signal-sprint-gdk-build-" + self.cas[:12]
        self.build_ref = "refs/heads/" + self.build_branch

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_check_only_does_not_create_branch(self):
        result = bootstrap.bootstrap_build_branch(self.repo, self.cas)
        self.assertEqual(result["status"], "GDK_BUILD_BRANCH_BOOTSTRAP_CHECK_ONLY")
        self.assertFalse(result["build_ref_exists_at_cas"])
        self.assertIsNone(result["factory_head_sha"])
        self.assertFalse(result["remote_ref_pushed"])
        self.assertNotIn(self.build_branch, self.git("branch", "--list"))

    def test_explicit_create_is_idempotent_and_source_immutable(self):
        first = bootstrap.bootstrap_build_branch(self.repo, self.cas, create=True)
        second = bootstrap.bootstrap_build_branch(self.repo, self.cas, create=True)
        self.assertEqual(first, second)
        self.assertEqual(first["factory_head_sha"], self.cas)
        self.assertEqual(self.git("rev-parse", self.build_ref), self.cas)
        self.assertEqual(self.git("rev-parse", self.job["source_branch"]), self.source)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.cas)

    def test_existing_build_branch_at_other_sha_rejected_without_force(self):
        self.git("branch", self.build_branch, self.source)
        with self.assertRaisesRegex(ConflictError, "another commit"):
            bootstrap.bootstrap_build_branch(self.repo, self.cas, create=True)
        self.assertEqual(self.git("rev-parse", self.build_ref), self.source)

    def test_missing_cas_branch_rejected(self):
        self.git("switch", "-q", self.job["source_branch"])
        self.git("branch", "-D", self.cas_branch)
        with self.assertRaisesRegex(ConflictError, "CAS branch"):
            bootstrap.bootstrap_build_branch(self.repo, self.cas, create=True)

    def test_source_moved_rejected(self):
        self.git("branch", "-f", self.job["source_branch"], self.cas)
        with self.assertRaisesRegex(ConflictError, "source branch"):
            bootstrap.bootstrap_build_branch(self.repo, self.cas, create=True)

    def test_unreviewed_identity_bytes_rejected(self):
        self.git("switch", "-qc", "synthetic-bad-identity", self.source)
        self.approved["store_id"] = "UNREVIEWED"
        path = self.repo / bootstrap.APPROVED_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.approved), encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "wrong identity")
        bad = self.git("rev-parse", "HEAD")
        self.git("branch", "-f", self.cas_branch, bad)
        with self.assertRaisesRegex(ConflictError, "reviewed Identity"):
            bootstrap.bootstrap_build_branch(self.repo, bad, create=True)

    def test_extra_file_in_cas_commit_rejected(self):
        self.git("switch", "-qc", "synthetic-bad-cas", self.source)
        path = self.repo / bootstrap.APPROVED_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.approved), encoding="utf-8")
        (self.repo / "unreviewed.txt").write_text("unexpected", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "CAS with extra file")
        bad = self.git("rev-parse", "HEAD")
        self.git("branch", "-f", self.cas_branch, bad)
        with self.assertRaisesRegex(ConflictError, "only approved Identity"):
            bootstrap.bootstrap_build_branch(self.repo, bad, create=True)


if __name__ == "__main__":
    unittest.main()
