"""Offline Signal Sprint GDK CAS-ref creation race tests.

No real GitHub writes, Partner Center access, or package generation.
"""
import base64
import json
from pathlib import Path
import unittest

from package_identity_provisioner import (
    ConflictError, RetryableError, GitHubReturnClient, Job, ProductConfig,
    PINNED_SIGNAL_SPRINT_GDK_IDENTITY, PINNED_SIGNAL_SPRINT_JOB,
)

SOURCE = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
CAS = "b" * 40
OTHER = "c" * 40
CAS_BRANCH = "codex/game-signal-sprint-gdk-cas-" + SOURCE[:12]
ROOT = Path(__file__).resolve().parents[1]


def encoded(obj):
    return {"encoding": "base64", "content": base64.b64encode(
        json.dumps(obj).encode("utf-8")).decode("ascii")}


class GdkCasCreateReconcileTests(unittest.TestCase):
    def setUp(self):
        self.config = ProductConfig.load(ROOT / "config.json")
        self.job = Job.validate({
            "schema_version": "1.0", **PINNED_SIGNAL_SPRINT_JOB,
            "display_name": "Signal Sprint - Offline Route Puzzle",
            "target_owner": self.config.target_owner,
            "dry_run": False,
            "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE",
                                  "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
        }, self.config)
        self.official = {
            **PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
            "request_id": self.job.request_id,
            "product_type": "GAME", "slug": "signal-sprint",
            "source_sha": SOURCE,
            "identity_source": "USER_PROVIDED_PARTNER_CENTER",
            "provided_at": "2026-10-28T10:49:00+09:00",
            "packaging_family": "GDK",
        }
        self.package = {"sha256": "d" * 64, "signature_status": "NOTSIGNED"}

    def attempt(self, mode):
        refs = {self.job.source_branch: SOURCE}
        calls = []
        writes = []
        approved_payload = None

        def api(endpoint, body=None, allow_missing=False):
            nonlocal approved_payload
            calls.append(endpoint)
            if endpoint == "graphql":
                writes.append("graphql")
                self.assertEqual(refs[CAS_BRANCH], SOURCE)
                approved_payload = body["variables"]["input"]["fileChanges"]["additions"][0]["contents"]
                refs[CAS_BRANCH] = OTHER if mode == "postwrite_ref_moved" else CAS
                return {"data": {"createCommitOnBranch": {"commit": {
                    "oid": CAS, "url": "https://github.com/example/commit/" + CAS}}}}
            if endpoint.endswith("git/refs") and body:
                writes.append("create_ref")
                self.assertEqual(body, {
                    "ref": "refs/heads/" + CAS_BRANCH, "sha": SOURCE})
                if mode == "lost_response":
                    refs[CAS_BRANCH] = SOURCE
                    raise RetryableError("GitHub API timed out")
                if mode == "concurrent_same":
                    refs[CAS_BRANCH] = SOURCE
                    raise ConflictError("HTTP 422")
                if mode == "concurrent_other":
                    refs[CAS_BRANCH] = OTHER
                    raise ConflictError("HTTP 422")
                if mode == "still_missing":
                    raise ConflictError("HTTP 422")
                raise AssertionError("unexpected mode")
            if "git/ref/heads/" in endpoint:
                name = endpoint.split("git/ref/heads/", 1)[1]
                if name not in refs and allow_missing:
                    return None
                return {"object": {"sha": refs[name]}}
            if "/manifest.json" in endpoint:
                return encoded({"slug": "signal-sprint", "kind": "game"})
            if "/proposals/" in endpoint:
                return encoded({"slug": "signal-sprint",
                                "title": "Signal Sprint - Offline Route Puzzle"})
            if "/approved-identity.json" in endpoint:
                if approved_payload is None:
                    self.assertTrue(allow_missing)
                    return None
                if mode == "postwrite_identity_tampered":
                    return encoded({"store_id": "TAMPERED"})
                return {"encoding": "base64", "content": approved_payload}
            if "/commits/" in endpoint:
                return {"sha": CAS, "parents": [{"sha": SOURCE}],
                        "files": [{"filename": "products/signal-sprint/store/approved-identity.json",
                                   "status": "added"}]}
            raise AssertionError("unexpected endpoint: " + endpoint)

        try:
            result = GitHubReturnClient(api).return_identity(
                self.job, self.config, self.official, self.package, apply=True)
        except (ConflictError, RetryableError):
            self.assertEqual(refs[self.job.source_branch], SOURCE)
            if mode.startswith("postwrite_"):
                self.assertIn("graphql", writes)
            else:
                self.assertNotIn("graphql", writes)
            raise
        self.assertEqual(refs[self.job.source_branch], SOURCE)
        return result, refs, writes, calls

    def test_lost_create_response_reconciles_without_second_create(self):
        result, refs, writes, _ = self.attempt("lost_response")
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["branch"], CAS_BRANCH)
        self.assertEqual(result["commit_sha"], CAS)
        self.assertEqual(refs[CAS_BRANCH], CAS)
        self.assertEqual(writes, ["create_ref", "graphql"])

    def test_concurrent_identical_create_reconciles_without_overwrite(self):
        result, refs, writes, _ = self.attempt("concurrent_same")
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(refs[CAS_BRANCH], CAS)
        self.assertEqual(writes, ["create_ref", "graphql"])

    def test_concurrent_different_ref_blocks_cas_write(self):
        with self.assertRaisesRegex(ConflictError, "HEAD changed"):
            self.attempt("concurrent_other")

    def test_failed_create_with_missing_ref_does_not_claim_success(self):
        with self.assertRaisesRegex(ConflictError, "422"):
            self.attempt("still_missing")

    def test_graphql_success_but_moved_cas_ref_never_claims_applied(self):
        with self.assertRaisesRegex(ConflictError, "moved during CAS resume"):
            self.attempt("postwrite_ref_moved")

    def test_graphql_success_but_tampered_committed_bytes_never_claims_applied(self):
        with self.assertRaisesRegex(ConflictError, "committed Identity differs"):
            self.attempt("postwrite_identity_tampered")


if __name__ == "__main__":
    unittest.main()
