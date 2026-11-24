"""User-provided GDK Store Identity contract for Signal Sprint."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from package_identity_provisioner import (
    GitHubReturnClient, Job, OfficialIdentityProvider, ProductConfig,
    build_gdk_identity_return_preview_receipt,
    canonical_hash,
    signal_sprint_gdk_lineage,
    validate_gdk_identity_return_preview_receipt,
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


def preview_fixture():
    config = ProductConfig.load(ROOT / "config.json")
    raw = raw_job(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID, CURRENT_SOURCE_BRANCH, dry_run=True)
    raw["display_name"] = "Signal Sprint - Offline Route Puzzle"
    job = Job.validate(raw, config)
    official = gdk_identity(CURRENT_SOURCE_SHA, CURRENT_REQUEST_ID)
    workflow_head = "3" * 40
    exe_sha = "4" * 64
    run_id = 1234567
    exe_artifact_id = 2345678
    build = {
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "product_source": CURRENT_SOURCE_SHA,
        "pr30_source_commit": "a377043d3c9ab0c71d9a100cdb841dd7000313b9",
        "pr30_ancestry_verified": True,
        "build_job_name": "windows-frozen-source-exe",
        "run_status_at_verification": "completed",
        "run_conclusion": "success",
        "completed_run_required": True,
        "build_provenance_verified": True,
        "independent_build_verified": True,
        "physical_gui_verified": False,
        "artifact_kind": "EXE_QA_UNSIGNED",
        "msix_status": "NOT_BUILT",
        "gdk_package_verified": False,
        "product_acceptance": False,
        "build_proof_artifact_verified": True,
        "run_id": run_id,
        "artifact_id": exe_artifact_id,
        "workflow_head_sha": workflow_head,
        "exe_sha256": exe_sha,
        "exe_size_bytes": 11453717,
        "artifact_exe_size_bytes": 11453717,
        "artifact_zip_size_bytes": 11203534,
        "artifact_zip_sha256": "9" * 64,
        "build_run_url": f"https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/{run_id}",
        "build_proof_artifact_id": 3456789,
        "build_proof_artifact_digest": "sha256:" + "2" * 64,
        "build_proof_artifact_run_id": run_id,
        "build_proof_artifact_workflow_head_sha": workflow_head,
        "build_proof_artifact_zip_sha256": "2" * 64,
        "build_proof_artifact_zip_size_bytes": 5432,
    }
    payload = dict(raw)
    readiness = {
        "schema": "signal-sprint-gdk-current-source-readiness-v1",
        "status": "HOLD_GDK_PACKAGE_PREREQUISITES",
        "read_only": True,
        "workflow_head_sha": workflow_head,
        "source_checkout": {
            "head_sha": CURRENT_SOURCE_SHA,
            "exact_frozen_source_verified": True,
        },
        "request": {
            "request_id": CURRENT_REQUEST_ID,
            "source_branch": CURRENT_SOURCE_BRANCH,
            "status": "CHECK_ONLY_REQUEST_DERIVED_NOT_SUBMITTED",
            "request_generated": True,
            "request_submitted": False,
            "dry_run_only": True,
            "request_payload": payload,
        },
        "route": {
            "packaging_family": "GDK",
            "partner_center_selection": "GDK_GAME",
            "ordinary_msix_allowed": False,
        },
        "authorization": {
            "cas_write_performed": False,
            "request_submitted": False,
            "central_ledger_modified": False,
            "makepkg_executed": False,
            "msixvc2_built": False,
            "store_submitted": False,
        },
        "source_lineage": {"legacy_identity_reusable": False},
        "legacy_identity": {"reusable": False},
        "identity": {"legacy_identity_reused": False},
        "completed_build_attestation": {
            "status": "PASS_INDEPENDENT_BUILD_ONLY",
            "product_source_sha": CURRENT_SOURCE_SHA,
            "pr30_source_sha": "a377043d3c9ab0c71d9a100cdb841dd7000313b9",
            "run_id": run_id,
            "artifact_id": exe_artifact_id,
            "workflow_head_sha": workflow_head,
            "exe_sha256": exe_sha,
            "exe_size_bytes": 11453717,
            "physical_gui_verified": False,
            "gdk_package_verified": False,
            "msix_status": "NOT_BUILT",
            "product_acceptance": False,
        },
    }
    build_artifact = {
        "artifact_id": 400,
        "name": "signal-sprint-completed-build-attestation",
        "digest": "sha256:" + "5" * 64,
        "size_in_bytes": 2048,
        "downloaded_zip_sha256": "5" * 64,
        "downloaded_zip_size_bytes": 2048,
    }
    readiness_artifact = {
        "artifact_id": 401,
        "name": "signal-sprint-gdk-package-readiness",
        "digest": "sha256:" + "6" * 64,
        "size_in_bytes": 1024,
        "downloaded_zip_sha256": "6" * 64,
        "downloaded_zip_size_bytes": 1024,
    }
    args = (
        job, config, official, build, readiness, build_artifact,
        readiness_artifact, "7" * 64, "8" * 64,
    )
    return args




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
        self.assertEqual(result["request_id"], CURRENT_REQUEST_ID)
        self.assertEqual(result["source_sha"], CURRENT_SOURCE_SHA)
        self.assertEqual(result["registration_family"], "GDK")
        self.assertEqual(result["identity_source"], "USER_PROVIDED_PARTNER_CENTER")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["request_submitted"])
        self.assertEqual(result["cas_status"], "NOT_APPLIED")
        self.assertFalse(result["cas_write_performed"])
        self.assertEqual(result["github_api_calls"], 0)
        self.assertEqual(result["github_write_calls"], 0)
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


    def test_current_lineage_builds_consumable_gdk_identity_only_preview_receipt(self):
        args = preview_fixture()
        receipt = build_gdk_identity_return_preview_receipt(*args)
        self.assertTrue(validate_gdk_identity_return_preview_receipt(receipt))
        self.assertEqual(receipt["status"], "CHECK_ONLY_SOURCE_BOUND_IDENTITY_RETURN_PREVIEW")
        self.assertEqual(receipt["scope"], "IDENTITY_ONLY")
        self.assertEqual(receipt["request_id"], CURRENT_REQUEST_ID)
        self.assertEqual(receipt["source_sha"], CURRENT_SOURCE_SHA)
        self.assertEqual(receipt["registration_family"], "GDK")
        self.assertEqual(receipt["return_target"]["repository"],
                         "shihuiarenjinba-png/AI-Game-Factory")
        self.assertEqual(receipt["return_target"]["branch"], CURRENT_SOURCE_BRANCH)
        self.assertEqual(receipt["return_target"]["path"],
                         "products/signal-sprint/store/approved-identity.json")
        self.assertEqual(receipt["authorization"]["cas_status"], "NOT_APPLIED")
        self.assertEqual(receipt["authorization"]["github_api_calls"], 0)
        self.assertEqual(receipt["authorization"]["github_write_calls"], 0)
        self.assertFalse(receipt["authorization"]["request_submitted"])
        self.assertFalse(receipt["authorization"]["central_ledger_modified"])
        self.assertFalse(receipt["gates"]["physical_gui_verified"])
        self.assertFalse(receipt["gates"]["gdk_package_verified"])
        self.assertNotIn("version", receipt)

    def test_preview_rejects_legacy_cross_lineage_and_modified_identity(self):
        args = list(preview_fixture())
        old_job = Job.validate(
            raw_job(SOURCE_SHA, REQUEST_ID, LEGACY_SOURCE_BRANCH, dry_run=True),
            args[1],
        )
        args[0] = old_job
        with self.assertRaisesRegex(Exception, "CURRENT_1A349"):
            build_gdk_identity_return_preview_receipt(*args)

        args = list(preview_fixture())
        bad_identity = dict(args[2])
        bad_identity["store_id"] = "9N21MJM7S57R"
        args[2] = bad_identity
        with self.assertRaisesRegex(Exception, "IDENTITY_IDENTIFIERS_MISMATCH"):
            build_gdk_identity_return_preview_receipt(*args)

    def test_preview_rejects_build_or_readiness_claims_that_cross_gates(self):
        args = list(preview_fixture())
        bad_build = dict(args[3])
        bad_build["physical_gui_verified"] = True
        args[3] = bad_build
        with self.assertRaisesRegex(Exception, "BUILD_ATTESTATION_NOT_ACCEPTABLE"):
            build_gdk_identity_return_preview_receipt(*args)

        args = list(preview_fixture())
        bad_readiness = dict(args[4])
        bad_request = dict(bad_readiness["request"])
        bad_request["request_submitted"] = True
        bad_readiness["request"] = bad_request
        args[4] = bad_readiness
        with self.assertRaisesRegex(Exception, "REQUEST_NOT_CHECK_ONLY"):
            build_gdk_identity_return_preview_receipt(*args)

    def test_preview_receipt_validator_rejects_tampered_return_target(self):
        receipt = build_gdk_identity_return_preview_receipt(*preview_fixture())
        receipt["return_target"]["path"] = "products/signal-sprint/store/other.json"
        with self.assertRaisesRegex(Exception, "RECEIPT_SHA_MISMATCH"):
            validate_gdk_identity_return_preview_receipt(receipt)


    def test_preview_receipt_validator_recomputes_identity_fingerprint(self):
        receipt = build_gdk_identity_return_preview_receipt(*preview_fixture())
        receipt["identity_reference"]["identifiers"]["store_id"] = "9N21MJM7S57R"
        receipt["receipt_sha256"] = canonical_hash({
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        })
        with self.assertRaisesRegex(Exception, "IDENTITY_FINGERPRINT_MISMATCH"):
            validate_gdk_identity_return_preview_receipt(receipt)


    def test_committed_current_lineage_preview_evidence_validates(self):
        path = ROOT / "evidence" / "signal-sprint-gdk-identity-return-preview.json"
        if not path.is_file():
            self.skipTest("current-lineage handoff receipt is not committed yet")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(validate_gdk_identity_return_preview_receipt(receipt))



if __name__ == "__main__":
    unittest.main()
