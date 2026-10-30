"""Signal Sprint: existing GDK Identity bytes are not sufficient CAS provenance.

All tests are offline and synthetic. No GitHub write, Partner Center, SDK, or
real CAS is performed.
"""
import base64
import json
from pathlib import Path
import unittest

from package_identity_provisioner import (
    ConflictError, GitHubReturnClient, Job, ProductConfig,
    PINNED_SIGNAL_SPRINT_GDK_IDENTITY, PINNED_SIGNAL_SPRINT_JOB,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
CAS = "b" * 40
OTHER = "c" * 40
TARGET = "products/signal-sprint/store/approved-identity.json"
CAS_BRANCH = "codex/game-signal-sprint-gdk-cas-" + SOURCE[:12]


def encoded(value):
    return {"encoding": "base64", "content": base64.b64encode(
        json.dumps(value).encode("utf-8")).decode("ascii")}


class GdkCasResumeProvenanceTests(unittest.TestCase):
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
            "request_id": self.job.request_id, "product_type": "GAME",
            "slug": "signal-sprint", "source_sha": SOURCE,
            "identity_source": "USER_PROVIDED_PARTNER_CENTER",
            "provided_at": "2026-10-28T10:49:00+09:00",
            "packaging_family": "GDK",
        }
        self.package = {"sha256": "d" * 64, "signature_status": "NOTSIGNED"}
        self.approved = {
            "schema_version": "1.0", "reviewed": True,
            "request_id": self.job.request_id,
            "product_type": "GAME", "slug": "signal-sprint",
            "source_factory": "AI-Game-Factory",
            "source_repository": self.job.source_repository,
            "source_branch": self.job.source_branch,
            "source_sha": SOURCE, "verified_source_sha": SOURCE,
            "package_sha256": self.package["sha256"],
            "package_family_name": self.official["package_family_name"],
            "package_sid": self.official["package_sid"],
            "signature_status": self.package["signature_status"],
            "store_id": self.official["store_id"],
            "name": self.official["name"], "publisher": self.official["publisher"],
            "source": "partner_center_user_provided",
            "identity_source": "USER_PROVIDED_PARTNER_CENTER",
            "provided_at": self.official["provided_at"],
            "packaging_family": "GDK",
            "publisher_display_name": self.official["publisher_display_name"],
            "xbox_title_id": self.official["xbox_title_id"],
            "xbox_scid": self.official["xbox_scid"],
            "msa_app_id": self.official["msa_app_id"],
        }

    def resume(self, *, parent=SOURCE, extra_file=False,
               changed_ref=False, missing_commit=False, current_head=CAS,
               source_moved=False):
        calls = []
        refs = 0

        def api(endpoint, body=None, allow_missing=False):
            nonlocal refs
            calls.append(endpoint)
            if endpoint == "graphql":
                raise AssertionError("resume must never write")
            if endpoint.endswith("git/ref/heads/" + self.job.source_branch):
                return {"object": {"sha": OTHER if source_moved else SOURCE}}
            if endpoint.endswith("git/ref/heads/" + CAS_BRANCH):
                refs += 1
                return {"object": {"sha": OTHER if changed_ref and refs > 1 else current_head}}
            if "/manifest.json" in endpoint:
                return encoded({"slug": "signal-sprint", "kind": "game"})
            if "/proposals/" in endpoint:
                return encoded({"slug": "signal-sprint", "title": "Signal Sprint - Offline Route Puzzle"})
            if "/approved-identity.json" in endpoint:
                self.assertIn("?ref=" + current_head, endpoint,
                              "GDK contents read must pin observed commit")
                return encoded(self.approved)
            if "/commits/" in endpoint:
                if missing_commit:
                    return {}
                files = [{"filename": TARGET, "status": "added"}]
                if extra_file:
                    files.append({"filename": "products/signal-sprint/main.py",
                                  "status": "modified"})
                return {"sha": current_head, "parents": [{"sha": parent}],
                        "files": files}
            raise AssertionError("unexpected endpoint: " + endpoint)

        result = GitHubReturnClient(api).return_identity(
            self.job, self.config, self.official, self.package, apply=True)
        return result, calls, refs

    def test_exact_single_file_cas_resume_is_idempotent(self):
        result, calls, refs = self.resume()
        self.assertEqual(result["status"], "EXISTING_VERIFIED")
        self.assertEqual(result["commit_sha"], CAS)
        self.assertEqual(result["branch"], CAS_BRANCH)
        self.assertEqual(refs, 2, "CAS branch must be rechecked after commit inspection")
        self.assertFalse(any(endpoint == "graphql" for endpoint in calls))

    def test_matching_identity_with_changed_source_history_is_conflict(self):
        with self.assertRaisesRegex(ConflictError, "directly descend"):
            self.resume(parent=OTHER)

    def test_matching_identity_with_extra_cas_file_is_conflict(self):
        with self.assertRaisesRegex(ConflictError, "add only approved Identity"):
            self.resume(extra_file=True)

    def test_matching_identity_with_unavailable_commit_is_conflict(self):
        with self.assertRaisesRegex(ConflictError, "provenance unavailable"):
            self.resume(missing_commit=True)

    def test_branch_movement_during_resume_is_conflict(self):
        with self.assertRaisesRegex(ConflictError, "moved during CAS resume"):
            self.resume(changed_ref=True)

    def test_immutable_source_movement_blocks_cas_resume(self):
        with self.assertRaisesRegex(ConflictError, "Immutable Signal Sprint source branch moved"):
            self.resume(source_moved=True)

    def test_identity_existing_at_original_source_is_not_cas(self):
        with self.assertRaisesRegex(ConflictError, "cannot predate CAS"):
            self.resume(current_head=SOURCE)


if __name__ == "__main__":
    unittest.main()
