"""Actual local Git fixture tests for the Signal Sprint dedicated GDK build gate.

All commits are temporary synthetic fixtures. No Factory or Partner Center writes.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import gdk_build_branch_gate as gate
from package_identity_provisioner import ConflictError


class GdkBuildBranchGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic CI")
        self.git("config", "user.email", "synthetic@example.invalid")
        product = self.repo / "products" / "signal-sprint"
        (product / "store").mkdir(parents=True)
        (product / "game.txt").write_text("immutable game", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic source")
        self.source_sha = self.git("rev-parse", "HEAD")
        (product / "store" / "approved-identity.json").write_text('{"synthetic":true}\n', encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic CAS")
        self.cas_sha = self.git("rev-parse", "HEAD")
        self.git("switch", "-qc", "codex/game-signal-sprint-gdk-build-20261028")
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "gdk-integration.txt").write_text("build-only", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic build integration")
        self.build_sha = self.git("rev-parse", "HEAD")
        # Actual Identity payload is checked by gdk_build_intake, which already
        # has independent tests; isolate the branch policy in these Git fixtures.
        p = patch.object(gate, "verify_cas_checkout", return_value={})
        p.start()
        self.addCleanup(p.stop)

    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.repo), *args],
                           capture_output=True, text=True, check=True)
        return p.stdout.strip()

    def check(self):
        return gate.verify_build_branch(self.repo, self.cas_sha, self.git("rev-parse", "HEAD"))

    def test_clean_dedicated_build_branch_passes_without_claiming_build(self):
        result = self.check()
        self.assertEqual(result["status"], "GDK_BUILD_BRANCH_CHECK_ONLY")
        self.assertEqual(result["partner_center_selection"], "GDK_GAME")
        self.assertEqual(result["source_sha"], gate.PINNED_SIGNAL_SPRINT_JOB["source_sha"])
        self.assertEqual(result["factory_head_sha"], self.build_sha)
        self.assertEqual(result["build_branch"], "codex/game-signal-sprint-gdk-build-20261028")
        self.assertEqual(result["approved_identity_blob_sha"],
                         self.git("rev-parse", self.cas_sha + ":" + gate.APPROVED_PATH))
        self.assertFalse(result["gdk_sdk_validated"])
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["store_submitted"])

    def test_source_branch_name_rejected(self):
        self.git("switch", "-qc", "codex/game-signal-sprint-undo-20261027")
        with self.assertRaisesRegex(ConflictError, "dedicated"):
            self.check()

    def test_detached_head_rejected(self):
        self.git("checkout", "--detach", "-q")
        with self.assertRaises((ConflictError, gate.HoldError)):
            self.check()

    def test_untracked_file_rejected(self):
        (self.repo / "unreviewed.txt").write_text("untracked", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "uncommitted"):
            self.check()

    def test_dirty_tracked_file_rejected(self):
        (self.repo / "tools" / "gdk-integration.txt").write_text("dirty", encoding="utf-8")
        with self.assertRaisesRegex(ConflictError, "uncommitted"):
            self.check()

    def test_product_source_change_after_cas_rejected(self):
        (self.repo / "products" / "signal-sprint" / "game.txt").write_text("changed", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "illicit product change")
        with self.assertRaisesRegex(ConflictError, "product tree"):
            self.check()

    def test_approved_identity_change_after_cas_rejected(self):
        path = self.repo / gate.APPROVED_PATH
        path.write_text('{"synthetic":false}\n', encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "illicit identity change")
        with self.assertRaisesRegex(ConflictError, "product tree"):
            self.check()

    def test_branch_prefix_lookalike_rejected(self):
        self.git("switch", "-qc", "codex/game-signal-sprint-gdk-build-")
        with self.assertRaisesRegex(ConflictError, "dedicated"):
            self.check()


if __name__ == "__main__":
    unittest.main()
