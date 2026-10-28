"""User-provided GDK Store Identity contract for Signal Sprint."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from package_identity_provisioner import (
    GitHubReturnClient, Job, OfficialIdentityProvider, ProductConfig,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST_ID = "game-signal-sprint-" + SOURCE_SHA


def raw_job():
    cfg = ProductConfig.load(ROOT / "config.json")
    return {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "product_type": "GAME",
        "source_factory": "AI-Game-Factory",
        "source_repository": "shihuiarenjinba-png/AI-Game-Factory",
        "source_branch": "codex/game-signal-sprint-undo-20261027",
        "source_sha": SOURCE_SHA,
        "slug": "signal-sprint",
        "display_name": "Signal Sprint",
        "target_owner": cfg.target_owner,
        "dry_run": False,
        "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE",
                              "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
    }


def gdk_identity():
    return {
        "request_id": REQUEST_ID,
        "product_type": "GAME",
        "slug": "signal-sprint",
        "source_sha": SOURCE_SHA,
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

    def test_wrong_gdk_identifier_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "official-identity.json"
            bad = gdk_identity()
            bad["xbox_scid"] = "not-a-guid"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "Xbox SCID"):
                OfficialIdentityProvider(path).lookup(
                    Job.validate(raw_job(), ProductConfig.load(ROOT / "config.json")))


if __name__ == "__main__":
    unittest.main()
