"""Regression coverage for independent GAME codex/* product source branches."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from package_identity_provisioner import (
    ConflictError, GitHubReturnClient, HoldError, Job, ProductConfig, Provisioner,
)

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
PRODUCT_BRANCH = "codex/game-signal-sprint-playable-20261027"


def request(**changes):
    raw = {
        "schema_version": "1.0", "request_id": "signal-sprint-a123",
        "product_type": "GAME", "source_factory": "AI-Game-Factory",
        "source_repository": "shihuiarenjinba-png/AI-Game-Factory",
        "source_branch": PRODUCT_BRANCH, "source_sha": SHA,
        "slug": "signal-sprint", "display_name": "Signal Sprint - Offline Route Puzzle",
        "target_owner": "shihuiarenjinba-png", "dry_run": True,
        "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE",
                              "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
    }
    raw.update(changes)
    return raw


class IndependentGameBranchTests(unittest.TestCase):
    def setUp(self):
        self.config = ProductConfig.load(ROOT / "config.json")

    def test_real_product_work_branch_is_accepted(self):
        validated = Job.validate(request(), self.config)
        self.assertEqual(validated.source_branch, PRODUCT_BRANCH)
        self.assertEqual(validated.product_type, "GAME")

    def test_unsafe_and_cross_lane_sources_are_held(self):
        for branch in ("main", "release", "codex/../main", "codex//bad",
                       "codex/bad.lock", "codex/.hidden", "codex/other\\bad",
                       "codex/a.", "codex/a/", "codex/a@{1}", "codex/"):
            with self.subTest(branch=branch), self.assertRaises(HoldError):
                Job.validate(request(source_branch=branch), self.config)
        for product_type, factory in (("APP", "AI-Game-Factory"),
                                      ("GAME_3D", "AI-Game-Factory"),
                                      ("GAME", "3d-game-factory")):
            with self.subTest(product_type=product_type, factory=factory), self.assertRaises(HoldError):
                Job.validate(request(product_type=product_type, source_factory=factory), self.config)

    def test_atomic_return_targets_actual_product_branch(self):
        calls = []
        def fake_api(endpoint, body=None, allow_missing=False):
            calls.append((endpoint, body))
            if "git/ref/heads/" in endpoint:
                self.assertTrue(endpoint.endswith(PRODUCT_BRANCH))
                return {"object": {"sha": SHA}}
            if "/manifest.json" in endpoint:
                self.assertIn("ref=codex%2Fgame-signal-sprint-playable-20261027", endpoint)
                raw = json.dumps({"slug": "signal-sprint", "kind": "game"}).encode()
                return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
            if "/proposals/" in endpoint:
                self.assertIn("ref=codex%2Fgame-signal-sprint-playable-20261027", endpoint)
                raw = json.dumps({"slug": "signal-sprint",
                                  "title": "Signal Sprint - Offline Route Puzzle"}).encode()
                return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
            if "/approved-identity.json" in endpoint:
                self.assertIn("ref=codex%2Fgame-signal-sprint-playable-20261027", endpoint)
                return None
            if endpoint == "graphql":
                branch = body["variables"]["input"]["branch"]
                self.assertEqual(branch["branchName"], PRODUCT_BRANCH)
                self.assertEqual(body["variables"]["input"]["expectedHeadOid"], SHA)
                return {"data": {"createCommitOnBranch": {"commit": {
                    "oid": "b" * 40, "url": "https://github.invalid/commit"}}}}
            raise AssertionError(endpoint)

        official = {"store_id": "9NTESTONLY123", "name": "Test.Game",
                    "publisher": "CN=Test Only", "version": "1.0.0.0",
                    "package_family_name": "Test.Game_abcdefghijklm",
                    "package_sid": "S-1-15-2-1-2-3-4-5-6-7",
                    "authenticated_account": "test-only",
                    "official_evidence_url": "https://partner.microsoft.com/test",
                    "verified_at": "2026-10-26T00:00:00Z"}
        package = {"sha256": "d" * 64, "signature_status": "NOTSIGNED",
                   "package_family_name": official["package_family_name"],
                   "package_sid": official["package_sid"]}
        result = GitHubReturnClient(fake_api).return_identity(
            Job.validate(request(), self.config), self.config, official, package, apply=True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["branch"], PRODUCT_BRANCH)
        self.assertEqual(result["path"], "products/signal-sprint/store/approved-identity.json")
        self.assertEqual(result["commit_sha"], "b" * 40)
        self.assertEqual(len(calls), 5)

    def test_mismatched_factory_product_name_is_conflict(self):
        def fake_api(endpoint, body=None, allow_missing=False):
            if "git/ref/heads/" in endpoint:
                return {"object": {"sha": SHA}}
            if "/manifest.json" in endpoint:
                raw = json.dumps({"slug": "signal-sprint", "kind": "game"}).encode()
                return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
            if "/proposals/" in endpoint:
                raw = json.dumps({"slug": "signal-sprint", "title": "Other Game"}).encode()
                return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
            raise AssertionError(endpoint)
        with self.assertRaises(ConflictError):
            GitHubReturnClient(fake_api).return_identity(
                Job.validate(request(), self.config), self.config, {}, {}, apply=True)

    def test_same_request_id_different_branch_sha_or_slug_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Provisioner(self.config, Path(directory) / "state", Path(directory) / "work")
            self.assertEqual(runner.run(request())["status"], "DRY_RUN")
            for change in ({"source_branch": "codex/other-game"},
                           {"source_sha": "b" * 40}, {"slug": "other-game"}):
                self.assertEqual(runner.run(request(**change))["status"], "CONFLICT")
            self.assertEqual(runner.run(request())["status"], "DRY_RUN")
            self.assertEqual(runner.ledger.read("signal-sprint-a123")["response"]["status"], "DRY_RUN")


if __name__ == "__main__":
    unittest.main()
