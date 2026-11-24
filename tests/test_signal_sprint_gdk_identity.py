"""User-provided GDK Store Identity contract for Signal Sprint."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from package_identity_provisioner import (
    GitHubReturnClient, Job, OfficialIdentityProvider, ProductConfig,
    signal_sprint_gdk_lineage,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST_ID = "game-signal-sprint-" + SOURCE_SHA
CURRENT_SOURCE_SHA = "1a349faa41663c417c40710140a4d50c79b62b78"
CURRENT_REQUEST_ID = "game-signal-sprint-" + CURRENT_SOURCE_SHA
CURRENT_SOURCE_BRANCH = "codex/signal-sprint-frozen-source-ref-20261124"
LEGACY_SOURCE_BRANCH = "codex/game-signal-sprint-undo-20261027"


def raw_job(source_sha=SOURCE_SHA, request_id=None, source_branch=LEGACY_SOURCE_BRANCH, dry_run=False):
    cfg = ProductConfig.load(ROOT / "config.json")
    return {
        "schema_version": "1.0",
        "request_id": request_id or ("game-signal-sprint-" + source_sha),
        "product_type": "GAME",
        "source_factory": "AI-Game-Factory",
        "source_repository": "shihuiarenjinba-png/AI-Game-Factory",
        "source_branch": source_branch,
        "source_sha": source_sha,
        "slug": "signal-sprint",
        "display_name": "Signal Sprint",
        "target_owner": cfg.target_owner,
        "dry_run": dry_run,
        "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE",
                              "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
    }


def gdk_identity(source_sha=SOURCE_SHA, request_id=None):
    return {
        "request_id": request_id or ("game-signal-sprint-" + source_sha),
        "product_type": "GAME",
        "slug": "signal-sprint",
        "source_sha": source_sha,
        "identity_source": "USER_PROVIDED_PARTNER_CENTER",
        "provided_at": "2026-10-28T10:49:00+09:00",
        "store_id": "9N21MJM7S57P",
        "name": "OkinawaDesktopTools.SignalSprint",
        "publisher": "CN=46263F21-A700-41DB-8C9B-114C22FB82FC",
        "publisher_display_name": "Okinawa Desktop Tools",
        "package_family_name": "OkinawaDesktopTools.SignalSprint_j8yefg9jgfh58",
        "package_sid": "S-1-15-2-1437967488-3265478925-1925977903-994526844-2895000717-1943620661-378024715",
        "packaging_family": "GDK",
        "xbox_title_id": "68721417",
        "xbox_scid": "00000000-0000-0000-0000-000068721417",
        "msa_app_id": "39852fc3-fa46-4bda-88aa-b35385488ced",
    }


class GdkIdentityContractTests(unittest.TestCase):
    def test_user_provided_gdk_identity_is_accepted_without_package_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            path.write_text(json.dumps(gdk_identity()), encoding="utf-8")
            official = OfficialIdentityProvider(path).lookup(
                Job.validate(raw_job(), ProductConfig.load(ROOT / "config.json")))
        self.assertEqual(official["store_id"], "9N21MJM7S57P")
        self.assertEqual(official["packaging_family"], "GDK")
        self.assertNotIn("version", official)
        self.assertNotIn("authenticated_account", official)
        self.assertNotIn("official_evidence_url", official)

    def test_cas_payload_records_gdk_ids_and_keeps_version_separate(self):
        config = ProductConfig.load(ROOT / "config.json")
        job = Job.validate(raw_job(), config)
        official = gdk_identity()
        package = {"sha256": "d" * 64, "signature_status": "NOTSIGNED"}
        writes = []

        def api(endpoint, body=None, allow_missing=False):
            if "git/ref/heads/" in endpoint:
                return {"object": {"sha": SOURCE_SHA}}
            if "/manifest.json" in endpoint:
                value = {"slug": "signal-sprint", "kind": "game"}
                return {"encoding": "base64",
                        "content": base64.b64encode(json.dumps(value).encode()).decode()}
            if "/proposals/" in endpoint:
                value = {"slug": "signal-sprint", "title": "Signal Sprint"}
                return {"encoding": "base64",
                        "content": base64.b64encode(json.dumps(value).encode()).decode()}
            if "/approved-identity.json" in endpoint:
                return None
            if endpoint == "graphql":
                writes.append(body)
                return {"data": {"createCommitOnBranch": {
                    "commit": {"oid": "b" * 40, "url": "https://github.invalid/commit"}}}}
            raise AssertionError(endpoint)

        result = GitHubReturnClient(api).return_identity(
            job, config, official, package, apply=True)
        self.assertEqual(result["status"], "APPLIED")
        encoded = writes[0]["variables"]["input"]["fileChanges"]["additions"][0]["contents"]
        approved = json.loads(base64.b64decode(encoded))
        self.assertEqual(approved["source"], "partner_center_user_provided")
        self.assertEqual(approved["packaging_family"], "GDK")
        self.assertEqual(approved["xbox_title_id"], "68721417")
        self.assertEqual(approved["xbox_scid"],
                         "00000000-0000-0000-0000-000068721417")
        self.assertEqual(approved["msa_app_id"],
                         "39852fc3-fa46-4bda-88aa-b35385488ced")
        self.assertNotIn("version", approved)
        self.assertNotIn("verified_by", approved)
        self.assertNotIn("evidence_url", approved)

    def test_self_consistent_alternate_source_cannot_consume_gdk_identity(self):
        # Even when both the job and supplied evidence agree with each other,
        # they must match the original immutable Signal Sprint source SHA.
        with tempfile.TemporaryDirectory() as tmp:
            bad_job = raw_job()
            bad_identity = gdk_identity()
            alternate_sha = "a" * 40
            bad_job["source_sha"] = alternate_sha
            bad_job["request_id"] = "game-signal-sprint-" + alternate_sha
            bad_identity["source_sha"] = alternate_sha
            bad_identity["request_id"] = bad_job["request_id"]
            path = Path(tmp) / "official-identity.json"
            path.write_text(json.dumps(bad_identity), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "allowlisted Signal Sprint source/request lineage"):
                OfficialIdentityProvider(path).lookup(
                    Job.validate(bad_job, ProductConfig.load(ROOT / "config.json")))

    def test_alternate_branch_or_request_id_is_rejected_before_cas(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            for field, value in (
                ("source_branch", "codex/other-signal-sprint-source"),
                ("request_id", "game-signal-sprint-another-valid-request"),
            ):
                with self.subTest(field=field):
                    bad_job = raw_job()
                    bad_identity = gdk_identity()
                    bad_job[field] = value
                    if field == "request_id":
                        bad_identity[field] = value
                    path.write_text(json.dumps(bad_identity), encoding="utf-8")
                    with self.assertRaisesRegex(Exception, "allowlisted Signal Sprint source/request lineage"):
                        OfficialIdentityProvider(path).lookup(
                            Job.validate(bad_job, ProductConfig.load(ROOT / "config.json")))

    def test_all_reviewed_gdk_identity_values_are_exact_not_just_well_formed(self):
        replacements = {
            "store_id": "9N21MJM7S57Q",
            "name": "OkinawaDesktopTools.SignalSprint2",
            "publisher": "CN=56263F21-A700-41DB-8C9B-114C22FB82FC",
            "publisher_display_name": "Other Desktop Tools",
            "package_family_name": "OkinawaDesktopTools.SignalSprint_aaaaaaaaaaaaa",
            "package_sid": "S-1-15-2-1437967488-3265478925-1925977903-994526844-2895000717-1943620661-378024716",
            "xbox_title_id": "68721418",
            "xbox_scid": "00000000-0000-0000-0000-000068721418",
            "msa_app_id": "39852fc3-fa46-4bda-88aa-b35385488cee",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            job = Job.validate(raw_job(), ProductConfig.load(ROOT / "config.json"))
            for field, value in replacements.items():
                with self.subTest(field=field):
                    bad_identity = gdk_identity()
                    bad_identity[field] = value
                    path.write_text(json.dumps(bad_identity), encoding="utf-8")
                    with self.assertRaisesRegex(Exception, "user-reviewed Signal Sprint"):
                        OfficialIdentityProvider(path).lookup(job)

    def test_wrong_gdk_identifier_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            bad = gdk_identity()
            bad["xbox_scid"] = "not-a-guid"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "Xbox SCID"):
                OfficialIdentityProvider(path).lookup(
                    Job.validate(raw_job(), ProductConfig.load(ROOT / "config.json")))

    def test_current_frozen_source_identity_is_accepted_as_exact_dry_run_lineage(self):
        config = ProductConfig.load(ROOT / "config.json")
        job = Job.validate(
            raw_job(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID, CURRENT_SOURCE_BRANCH, dry_run=True),
            config,
        )
        identity = gdk_identity(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            path.write_text(json.dumps(identity), encoding="utf-8")
            official = OfficialIdentityProvider(path).lookup(job)

        self.assertEqual(signal_sprint_gdk_lineage(job), "CURRENT_1A349")
        self.assertEqual(official["source_sha"], CURRENT_SOURCE_SHA)
        self.assertEqual(official["request_id"], CURRENT_REQUEST_ID)
        self.assertTrue(job.dry_run)
        self.assertEqual(official["packaging_family"], "GDK")
        self.assertNotIn("version", official)

    def test_current_frozen_source_dry_run_never_calls_github_or_applies_cas(self):
        config = ProductConfig.load(ROOT / "config.json")
        job = Job.validate(
            raw_job(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID, CURRENT_SOURCE_BRANCH, dry_run=True),
            config,
        )
        identity = gdk_identity(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            path.write_text(json.dumps(identity), encoding="utf-8")
            official = OfficialIdentityProvider(path).lookup(job)

        calls = []
        def api(endpoint, body=None, allow_missing=False):
            calls.append((endpoint, body))
            raise AssertionError("dry-run must not call GitHub")

        result = GitHubReturnClient(api).return_identity(
            job, config, official,
            {"sha256": "d" * 64, "signature_status": "NOTSIGNED"},
            apply=False,
        )
        self.assertEqual(result["status"], "NOT_APPLIED")
        self.assertEqual(calls, [])

    def test_current_request_rejects_legacy_identity_and_legacy_request_rejects_current_identity(self):
        config = ProductConfig.load(ROOT / "config.json")
        pairs = (
            (
                raw_job(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID, CURRENT_SOURCE_BRANCH, dry_run=True),
                gdk_identity(SOURCE_SHA, REQUEST_ID),
            ),
            (
                raw_job(SOURCE_SHA, REQUEST_ID, LEGACY_SOURCE_BRANCH, dry_run=True),
                gdk_identity(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            for raw, identity in pairs:
                with self.subTest(job_source=raw["source_sha"], identity_source=identity["source_sha"]):
                    path.write_text(json.dumps(identity), encoding="utf-8")
                    job = Job.validate(raw, config)
                    with self.assertRaisesRegex(Exception, "another product/request/SHA"):
                        OfficialIdentityProvider(path).lookup(job)

    def test_current_source_rejects_self_consistent_unallowlisted_request_and_branch(self):
        config = ProductConfig.load(ROOT / "config.json")
        bad_cases = (
            (
                raw_job(CURRENT_SOURCE_SHA, "game-signal-sprint-unreviewed-current-request",
                        CURRENT_SOURCE_BRANCH, dry_run=True),
                "game-signal-sprint-unreviewed-current-request",
            ),
            (
                raw_job(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID,
                        "codex/unreviewed-signal-sprint-branch", dry_run=True),
                CURRENT_REQUEST_ID,
            ),
            (
                raw_job("a" * 40, "game-signal-sprint-" + "a" * 40,
                        CURRENT_SOURCE_BRANCH, dry_run=True),
                "game-signal-sprint-" + "a" * 40,
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            for raw, identity_request in bad_cases:
                with self.subTest(request_id=raw["request_id"], source_sha=raw["source_sha"]):
                    identity = gdk_identity(raw["source_sha"], identity_request)
                    path.write_text(json.dumps(identity), encoding="utf-8")
                    job = Job.validate(raw, config)
                    with self.assertRaisesRegex(Exception, "allowlisted Signal Sprint source/request lineage"):
                        OfficialIdentityProvider(path).lookup(job)


if __name__ == "__main__":
    unittest.main()
