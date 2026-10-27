"""Regression: an existing GitHub contents blob SHA is not a commit SHA."""
import base64
import json
import unittest

from package_identity_provisioner import GitHubReturnClient, Job, ProductConfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40
BLOB = "b" * 40
RETURN_HEAD = "c" * 40


class ExistingIdentityCommitTests(unittest.TestCase):
    def test_existing_verified_reports_branch_commit_not_file_blob(self):
        config = ProductConfig.load(ROOT / "config.json")
        raw = {
            "schema_version": "1.0", "request_id": "req-existing-001",
            "product_type": config.product_type,
            "source_factory": config.source_factory,
            "source_repository": config.source_repository,
            "source_branch": config.source_branch,
            "source_sha": HEAD, "slug": "sample-product",
            "display_name": "Sample Product", "target_owner": config.target_owner,
            "dry_run": False,
            "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE", "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
        }
        official = {
            "store_id": "9N1234567890", "name": "Sample.Product",
            "publisher": "CN=Test Publisher", "version": "1.2.3.4",
            "authenticated_account": "operator@example.invalid",
            "official_evidence_url": "https://partner.microsoft.com/dashboard/products/123",
            "verified_at": "2026-10-26T00:00:00Z",
            "package_family_name": "Sample.Product_abcdefghijklm",
            "package_sid": "S-1-15-2-1-2-3-4-5-6-7",
        }
        package = {"sha256": "d" * 64, "signature_status": "NOTSIGNED",
                   "package_family_name": official["package_family_name"],
                   "package_sid": official["package_sid"]}
        approved = {
            "reviewed": True, "source": "partner_center",
            **{key: official[key] for key in ("store_id", "name", "publisher", "version",
                                              "package_family_name", "package_sid")},
            "request_id": raw["request_id"], "product_type": raw["product_type"],
            "slug": raw["slug"],
            "source_factory": raw["source_factory"], "source_repository": raw["source_repository"],
            "source_branch": raw["source_branch"], "source_sha": HEAD,
            "verified_source_sha": HEAD, "package_sha256": package["sha256"],
            "signature_status": package["signature_status"],
            "verified_by": official["authenticated_account"],
            "evidence_url": official["official_evidence_url"],
            "verified_at": official["verified_at"],
        }
        calls = []

        def fake_api(endpoint, body=None, allow_missing=False):
            calls.append(endpoint)
            if "git/ref/heads/" in endpoint:
                return {"object": {"sha": HEAD}}
            if "/manifest.json" in endpoint:
                manifest = {"slug": "sample-product", "kind": "game"}
                return {"encoding": "base64", "content": base64.b64encode(json.dumps(manifest).encode()).decode()}
            if "/proposals/" in endpoint:
                proposal = {"slug": "sample-product", "title": "Sample Product"}
                return {"encoding": "base64", "content": base64.b64encode(json.dumps(proposal).encode()).decode()}
            if "/approved-identity.json" in endpoint:
                return {"sha": BLOB, "encoding": "base64",
                        "content": base64.b64encode(json.dumps(approved).encode()).decode()}
            raise AssertionError("Unexpected GitHub write or endpoint: " + endpoint)

        result = GitHubReturnClient(fake_api).return_identity(
            Job.validate(raw, config), config, official, package, apply=True
        )
        self.assertEqual(result["status"], "EXISTING_VERIFIED")
        self.assertEqual(result["commit_sha"], HEAD)
        self.assertNotEqual(result["commit_sha"], BLOB)
        self.assertFalse(any(endpoint == "graphql" for endpoint in calls))

    def test_retry_after_success_reads_existing_before_original_head_check(self):
        """An ambiguous first response may leave the CAS commit already applied."""
        config = ProductConfig.load(ROOT / "config.json")
        raw = {
            "schema_version": "1.0", "request_id": "req-existing-001",
            "product_type": config.product_type,
            "source_factory": config.source_factory,
            "source_repository": config.source_repository,
            "source_branch": config.source_branch,
            "source_sha": HEAD, "slug": "sample-product",
            "display_name": "Sample Product", "target_owner": config.target_owner,
            "dry_run": False,
            "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE", "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
        }
        official = {
            "store_id": "9N1234567890", "name": "Sample.Product",
            "publisher": "CN=Test Publisher", "version": "1.2.3.4",
            "authenticated_account": "operator@example.invalid",
            "official_evidence_url": "https://partner.microsoft.com/dashboard/products/123",
            "verified_at": "2026-10-26T00:00:00Z",
            "package_family_name": "Sample.Product_abcdefghijklm",
            "package_sid": "S-1-15-2-1-2-3-4-5-6-7",
        }
        package = {"sha256": "d" * 64, "signature_status": "NOTSIGNED",
                   "package_family_name": official["package_family_name"],
                   "package_sid": official["package_sid"]}
        approved = {
            "schema_version": "1.0", "reviewed": True, "source": "partner_center",
            "request_id": raw["request_id"], "product_type": raw["product_type"],
            "slug": raw["slug"], "source_factory": raw["source_factory"],
            "source_repository": raw["source_repository"],
            "source_branch": raw["source_branch"], "source_sha": HEAD,
            "verified_source_sha": HEAD, "package_sha256": package["sha256"],
            "signature_status": package["signature_status"],
            "verified_by": official["authenticated_account"],
            "evidence_url": official["official_evidence_url"],
            "verified_at": official["verified_at"],
            **{key: official[key] for key in ("store_id", "name", "publisher", "version",
                                              "package_family_name", "package_sid")},
        }
        calls = []

        def fake_api(endpoint, body=None, allow_missing=False):
            calls.append(endpoint)
            if "git/ref/heads/" in endpoint:
                return {"object": {"sha": RETURN_HEAD}}
            if "/manifest.json" in endpoint:
                value = {"slug": "sample-product", "kind": "game"}
            elif "/proposals/" in endpoint:
                value = {"slug": "sample-product", "title": "Sample Product"}
            elif "/approved-identity.json" in endpoint:
                value = approved
            else:
                raise AssertionError("Unexpected API write or endpoint: " + endpoint)
            return {"encoding": "base64", "content": base64.b64encode(
                json.dumps(value).encode()).decode()}

        result = GitHubReturnClient(fake_api).return_identity(
            Job.validate(raw, config), config, official, package, apply=True)
        self.assertEqual(result["status"], "EXISTING_VERIFIED")
        self.assertEqual(result["commit_sha"], RETURN_HEAD)
        self.assertFalse(any(endpoint == "graphql" for endpoint in calls))


    def test_existing_identity_requires_review_and_matching_evidence(self):
        official = {
            "store_id": "9N1234567890", "name": "Sample.Product",
            "publisher": "CN=Test Publisher", "version": "1.2.3.4",
            "authenticated_account": "operator@example.invalid",
            "official_evidence_url": "https://partner.microsoft.com/dashboard/products/123",
            "verified_at": "2026-10-26T00:00:00Z",
            "package_family_name": "Sample.Product_abcdefghijklm",
            "package_sid": "S-1-15-2-1-2-3-4-5-6-7",
        }
        config = ProductConfig.load(ROOT / "config.json")
        checked_job = Job.validate({
            "schema_version": "1.0", "request_id": "req-existing-001",
            "product_type": config.product_type, "source_factory": config.source_factory,
            "source_repository": config.source_repository, "source_branch": config.source_branch,
            "source_sha": HEAD, "slug": "sample-product", "display_name": "Sample Product",
            "target_owner": config.target_owner, "dry_run": False,
            "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE", "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
        }, config)
        package = {"sha256": "d" * 64, "signature_status": "NOTSIGNED",
                   "package_family_name": official["package_family_name"],
                   "package_sid": official["package_sid"]}
        approved = {
            "reviewed": True, "source": "partner_center",
            **{key: official[key] for key in ("store_id", "name", "publisher", "version",
                                              "package_family_name", "package_sid")},
            "request_id": checked_job.request_id, "product_type": checked_job.product_type,
            "slug": checked_job.slug,
            "source_factory": checked_job.source_factory, "source_repository": checked_job.source_repository,
            "source_branch": checked_job.source_branch, "source_sha": HEAD,
            "verified_source_sha": HEAD, "package_sha256": package["sha256"],
            "signature_status": package["signature_status"],
            "verified_by": official["authenticated_account"],
            "evidence_url": official["official_evidence_url"],
            "verified_at": official["verified_at"],
        }

        def wrapped(value):
            return {"encoding": "base64", "content": base64.b64encode(
                json.dumps(value).encode("utf-8")).decode("ascii")}

        self.assertTrue(GitHubReturnClient._existing_matches(wrapped(approved), official, checked_job, package))
        for changes in (
            {"reviewed": False}, {"reviewed": 1}, {"source": "unknown"},
            {"verified_by": "different-operator"},
            {"evidence_url": "https://partner.microsoft.com/other-product"},
            {"verified_at": "2000-01-01T00:00:00Z"},
            {"store_id": "9N0000000000"}, {"slug": "another-game"},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(GitHubReturnClient._existing_matches(
                    wrapped({**approved, **changes}), official, checked_job, package))
        for missing in approved:
            with self.subTest(missing=missing):
                self.assertFalse(GitHubReturnClient._existing_matches(
                    wrapped({k: v for k, v in approved.items() if k != missing}), official, checked_job, package))
        self.assertFalse(GitHubReturnClient._existing_matches(wrapped([]), official, checked_job, package))
        self.assertFalse(GitHubReturnClient._existing_matches(
            {"encoding": "base64", "content": "not base64"}, official, checked_job, package))

if __name__ == "__main__":
    unittest.main()
