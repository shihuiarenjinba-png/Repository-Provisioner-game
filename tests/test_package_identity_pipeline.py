import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from package_identity_provisioner import (
    ConflictError, GitHubReturnClient, HoldError, Job, Ledger, OfficialIdentityProvider,
    PackageBuilder, ProductConfig, Provisioner, RequestLock, RetryableError,
    SourceManager, compare_package_identity, inspect_package, redact,
    windows_all_auto_record, _package_family_name, _windows_package_sid,
)

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
TEST_TEMP = ROOT / ".test-tmp"
TEST_TEMP.mkdir(exist_ok=True)
tempfile.tempdir = str(TEST_TEMP)


def config():
    return ProductConfig.load(ROOT / "config.json")


def job(**updates):
    cfg = config()
    value = {
        "schema_version": "1.0", "request_id": "req-0001", "product_type": cfg.product_type,
        "source_factory": cfg.source_factory, "source_repository": cfg.source_repository,
        "source_branch": cfg.source_branch, "source_sha": SHA, "slug": "sample-product",
        "display_name": "Sample Product", "target_owner": cfg.target_owner, "dry_run": False,
        "requested_actions": ["BUILD_WINDOWS", "INSPECT_PACKAGE", "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"],
    }
    value.update(updates)
    return value


def evidence(**updates):
    cfg = config()
    family = _package_family_name("Sample.Product", "CN=Test Publisher") or "Sample.Product_abcdefghijklm"
    sid = _windows_package_sid(family) or "S-1-15-2-1-2-3-4-5-6-7"
    value = {
        "request_id": "req-0001", "product_type": cfg.product_type, "slug": "sample-product",
        "source_sha": SHA, "authenticated_account": "partner-operator@example.invalid",
        "verified_at": "2026-10-26T00:00:00Z",
        "official_evidence_url": "https://partner.microsoft.com/dashboard/products/123",
        "store_id": "9N1234567890", "name": "Sample.Product", "publisher": "CN=Test Publisher",
        "version": "1.2.3.4", "package_family_name": family, "package_sid": sid,
    }
    value.update(updates)
    return value


def package_result(**updates):
    official = evidence()
    value = {"sha256": "d" * 64, "package_family_name": official["package_family_name"],
             "package_sid": official["package_sid"], "signature_status": "NOTSIGNED"}
    value.update(updates)
    return value


def make_msix(path: Path, name="Sample.Product", publisher="CN=Test Publisher", version="1.2.3.4",
              include_exe=True):
    manifest = f'''<?xml version="1.0" encoding="utf-8"?>
    <Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">
      <Identity Name="{name}" Publisher="{publisher}" Version="{version}" />
      <Applications><Application Id="Game" Executable="bin/Sample.exe" EntryPoint="Windows.FullTrustApplication" /></Applications>
    </Package>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AppxManifest.xml", manifest)
        archive.writestr("AppxBlockMap.xml", '<BlockMap xmlns="http://schemas.microsoft.com/appx/2010/blockmap"/>')
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr("payload.txt", "payload")
        if include_exe:
            archive.writestr("bin/Sample.exe", b"MZ" + b"test executable")
    return path


class FakeSource:
    def __init__(self):
        self.calls = 0
    def acquire(self, _job, destination):
        self.calls += 1
        destination.mkdir(parents=True, exist_ok=True)
        return destination


class FakeBuilder:
    def __init__(self, artifact_kind="msix", name="Sample.Product"):
        self.calls, self.artifact_kind, self.name = 0, artifact_kind, name
    def build(self, _job, _source, output_dir, _config):
        self.calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / ("candidate.msix" if self.artifact_kind == "msix" else "candidate.exe")
        if self.artifact_kind == "msix":
            return make_msix(path, name=self.name)
        pe = bytearray(100_100)
        pe[:2] = b"MZ"
        pe[0x3c:0x40] = (0x80).to_bytes(4, "little")
        pe[0x80:0x84] = b"PE\x00\x00"
        path.write_bytes(pe)
        return path


class FakeIdentity:
    def __init__(self, value=None, error=None):
        self.value, self.error, self.calls = value or evidence(), error, 0
    def lookup(self, _job):
        self.calls += 1
        if self.error:
            raise self.error
        return dict(self.value)


class FakeGitHub:
    def __init__(self, result=None, error=None):
        self.result = result or {"status": "APPLIED", "repository": config().source_repository,
                                 "branch": config().source_branch, "path": "products/sample-product/store/approved-identity.json",
                                 "commit_sha": "b" * 40, "commit_url": "https://github.com/example/commit"}
        self.error, self.calls = error, 0
    def return_identity(self, *_args, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        if not kwargs.get("apply", False):
            return {**self.result, "status": "NOT_APPLIED", "commit_sha": None, "commit_url": None}
        return dict(self.result)


class ContractValidationTests(unittest.TestCase):
    def test_valid_job(self):
        self.assertEqual(Job.validate(job(), config()).source_sha, SHA)
    def test_wrong_product_type_is_hold(self):
        with self.assertRaises(HoldError):
            Job.validate(job(product_type="WRONG"), config())
    def test_wrong_factory_is_hold(self):
        with self.assertRaises(HoldError):
            Job.validate(job(source_factory="other"), config())
    def test_wrong_repository_is_hold(self):
        with self.assertRaises(HoldError):
            Job.validate(job(source_repository="owner/other"), config())
    def test_wrong_return_branch_is_hold(self):
        with self.assertRaises(HoldError):
            Job.validate(job(source_branch="main"), config())
    def test_other_safe_codex_work_branch_is_allowed(self):
        self.assertEqual(Job.validate(job(source_branch="codex/product/sample-product"), config()).source_branch,
                         "codex/product/sample-product")
    def test_unsafe_codex_work_branch_is_hold(self):
        with self.assertRaises(HoldError):
            Job.validate(job(source_branch="codex/../main"), config())
    def test_placeholder_sha_is_hold(self):
        with self.assertRaises(HoldError):
            Job.validate(job(source_sha="0" * 40), config())
    def test_unknown_input_field_is_hold(self):
        with self.assertRaises(HoldError):
            Job.validate(job(command="arbitrary"), config())
    def test_unknown_action_is_hold(self):
        with self.assertRaises(HoldError):
            Job.validate(job(requested_actions=["DELETE_REPOSITORY"]), config())


class PackageInspectionTests(unittest.TestCase):
    def test_msix_identity_hash_and_family_are_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_package(make_msix(Path(tmp) / "candidate.msix"))
        self.assertEqual(result["package_identity"], "Sample.Product")
        self.assertEqual(result["publisher"], "CN=Test Publisher")
        self.assertEqual(result["version"], "1.2.3.4")
        self.assertRegex(result["sha256"], r"^[0-9a-f]{64}$")
        if os.name == "nt":
            self.assertTrue(result["package_family_name"].startswith("Sample.Product_"))
        else:
            self.assertIsNone(result["package_family_name"])
    @unittest.skipUnless(os.name == "nt", "Windows AppModel API required")
    def test_publisher_id_uses_windows_appmodel_api(self):
        publisher = "CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, S=Washington, C=US"
        self.assertEqual(_package_family_name("Microsoft.Windows.Photos", publisher),
                         "Microsoft.Windows.Photos_8wekyb3d8bbwe")
    def test_exe_has_hash_but_no_package_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.exe"
            path.write_bytes(b"MZ")
            result = inspect_package(path)
        self.assertIsNone(result["package_identity"])
        self.assertEqual(result["kind"], "exe")
    def test_invalid_msix_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.msix"
            path.write_bytes(b"not zip")
            with self.assertRaises(HoldError):
                inspect_package(path)
    def test_msix_requires_package_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing-blockmap.msix"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("AppxManifest.xml", '<Package><Identity Name="X" Publisher="CN=X" Version="1.0.0.0"/></Package>')
                archive.writestr("Sample.exe", b"MZ")
            with self.assertRaisesRegex(HoldError, "required package metadata"):
                inspect_package(path)

    def test_msix_rejects_traversal_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_msix(Path(tmp) / "traversal.msix")
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("../outside.exe", b"MZ")
            with self.assertRaisesRegex(HoldError, "unsafe ZIP member"):
                inspect_package(path)

    def test_msix_rejects_duplicate_case_insensitive_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_msix(Path(tmp) / "duplicate.msix")
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("APPXMANIFEST.XML", b"<Package/>")
            with self.assertRaisesRegex(HoldError, "duplicate case-insensitive"):
                inspect_package(path)

    def test_msix_rejects_zip_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_msix(Path(tmp) / "linked.msix")
            entry = zipfile.ZipInfo("linked.exe")
            entry.create_system = 3
            entry.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr(entry, b"target.exe")
            with self.assertRaisesRegex(HoldError, "ZIP symlink"):
                inspect_package(path)

    def test_msix_reports_executable_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            present = inspect_package(make_msix(Path(tmp) / "present.msix"))
            absent = inspect_package(make_msix(Path(tmp) / "absent.msix", include_exe=False))
        self.assertTrue(present["has_executable"])
        self.assertTrue(present["manifest_executable_present"])
        self.assertFalse(absent["has_executable"])
        self.assertFalse(absent["manifest_executable_present"])

    def test_msix_rejects_unbound_helper_executable(self):
        # A ZIP may contain a helper EXE while the launch target is missing.
        with tempfile.TemporaryDirectory() as tmp:
            path = make_msix(Path(tmp) / "orphan.msix")
            with zipfile.ZipFile(path, "a") as archive:
                manifest = archive.read("AppxManifest.xml").decode()
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("AppxManifest.xml", manifest.replace(
                    'Executable="bin/Sample.exe"', 'Executable="bin/Missing.exe"'))
                archive.writestr("AppxBlockMap.xml", "<BlockMap/>")
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("bin/Sample.exe", b"MZhelper")
            result = inspect_package(path)
        self.assertTrue(result["has_executable"])
        self.assertFalse(result["manifest_executable_present"])

    def test_msix_rejects_manifest_executable_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_msix(Path(tmp) / "unsafe.msix")
            with zipfile.ZipFile(path, "r") as archive:
                manifest = archive.read("AppxManifest.xml").decode()
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("AppxManifest.xml", manifest.replace(
                    'Executable="bin/Sample.exe"', 'Executable="../outside.exe"'))
                archive.writestr("AppxBlockMap.xml", "<BlockMap/>")
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("bin/Sample.exe", b"MZhelper")
            with self.assertRaisesRegex(HoldError, "unsafe executable path"):
                inspect_package(path)

    def test_msix_rejects_wrong_blockmap_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-blockmap.msix"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("AppxManifest.xml", '<Package><Identity Name="X" Publisher="CN=X" Version="1.0.0.0"/></Package>')
                archive.writestr("AppxBlockMap.xml", "<Package/>")
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("Sample.exe", b"MZ")
            with self.assertRaisesRegex(HoldError, "invalid XML root"):
                inspect_package(path)

    def test_msix_with_corrupt_non_manifest_payload_is_hold(self):
        # The manifest is still valid: CRC checking must cover every payload.
        with tempfile.TemporaryDirectory() as tmp:
            path = make_msix(Path(tmp) / "corrupt.msix")
            contents = bytearray(path.read_bytes())
            offset = contents.find(b"payload")
            self.assertGreaterEqual(offset, 0)
            contents[offset] ^= 1
            path.write_bytes(contents)
            with self.assertRaises(HoldError):
                inspect_package(path)



class IdentityEvidenceTests(unittest.TestCase):
    def test_matching_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.json"
            path.write_text(json.dumps(evidence()), encoding="utf-8")
            result = OfficialIdentityProvider(path).lookup(Job.validate(job(), config()))
        self.assertEqual(result["store_id"], "9N1234567890")
    def test_official_identity_verification_timestamp_must_be_real_and_not_future(self):
        for timestamp in (None, "", "not-a-timestamp", "2026-10-26T00:00:00",
                          "2026-02-30T00:00:00Z", "3026-10-26T00:00:00Z"):
            with self.subTest(verified_at=timestamp), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "identity.json"
                path.write_text(json.dumps(evidence(verified_at=timestamp)), encoding="utf-8")
                with self.assertRaisesRegex(HoldError, "verification timestamp"):
                    OfficialIdentityProvider(path).lookup(Job.validate(job(), config()))

    def test_duplicate_official_identity_source_sha_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.json"
            # The first SHA conflicts; the second would win under json.loads.
            duplicate = '{"source_sha":"' + "b" * 40 + '",' + json.dumps(evidence())[1:]
            path.write_text(duplicate, encoding="utf-8")
            with self.assertRaisesRegex(HoldError, "Duplicate JSON key"):
                OfficialIdentityProvider(path).lookup(Job.validate(job(), config()))

    def test_untrusted_evidence_url_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.json"
            path.write_text(json.dumps(evidence(official_evidence_url="https://evil.invalid/x")), encoding="utf-8")
            with self.assertRaises(HoldError):
                OfficialIdentityProvider(path).lookup(Job.validate(job(), config()))
    def test_evidence_for_other_sha_is_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.json"
            path.write_text(json.dumps(evidence(source_sha="b" * 40)), encoding="utf-8")
            with self.assertRaises(ConflictError):
                OfficialIdentityProvider(path).lookup(Job.validate(job(), config()))
    def test_package_identity_mismatch_is_conflict(self):
        with self.assertRaises(ConflictError):
            compare_package_identity({**package_result(), "kind": "msix", "package_identity": "Other",
                                      "publisher": "CN=Test Publisher", "version": "1.2.3.4"}, evidence())
    def test_exe_cannot_approve_official_identity(self):
        with self.assertRaises(HoldError):
            compare_package_identity({"kind": "exe"}, evidence())
    def test_windows_all_auto_adapter(self):
        contract = windows_all_auto_record(Job.validate(job(), config()), evidence(), package_result())
        self.assertEqual(contract["expected_head_sha"], SHA)
        self.assertEqual(contract["source_branch"], config().source_branch)
        self.assertEqual(contract["package_sha256"], "d" * 64)
        self.assertTrue(contract["operator_verified"])
        self.assertEqual(contract["request_id"], "req-0001")
        self.assertEqual(contract["product_type"], "GAME")
        self.assertEqual(contract["source_factory"], "AI-Game-Factory")
        self.assertEqual(contract["source_repository"], config().source_repository)
        self.assertEqual(contract["source_branch"], config().source_branch)
        self.assertEqual(contract["source_sha"], SHA)


class GitHubReturnTests(unittest.TestCase):
    def api(self, endpoint, body=None, allow_missing=False):
        if "git/ref/heads/" in endpoint:
            return {"object": {"sha": SHA}}
        if "/manifest.json" in endpoint:
            raw = json.dumps({"slug": "sample-product", "kind": "app" if config().product_type == "APP" else "game"}).encode()
            return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
        if "/proposals/" in endpoint:
            raw = json.dumps({"slug": "sample-product", "title": "Sample Product"}).encode()
            return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
        if "/project.godot" in endpoint:
            return {"encoding": "base64", "content": base64.b64encode(b"run/main_scene=x").decode()}
        if "/approved-identity.json" in endpoint:
            return None
        if endpoint == "graphql":
            return {"data": {"createCommitOnBranch": {"commit": {"oid": "b" * 40, "url": "https://github.invalid/c"}}}}
        raise AssertionError(endpoint)

    def test_atomic_apply_returns_real_commit_sha(self):
        result = GitHubReturnClient(self.api).return_identity(
            Job.validate(job(), config()), config(), evidence(), package_result(), True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["commit_sha"], "b" * 40)
    def test_atomic_identity_return_preserves_slug_in_approved_payload(self):
        submitted = []
        def capture(endpoint, body=None, allow_missing=False):
            if endpoint == "graphql":
                submitted.append(body)
            return self.api(endpoint, body, allow_missing)
        selected_job = Job.validate(job(), config())
        result = GitHubReturnClient(capture).return_identity(
            selected_job, config(), evidence(), package_result(), True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(len(submitted), 1)
        encoded = submitted[0]["variables"]["input"]["fileChanges"]["additions"][0]["contents"]
        approved = json.loads(base64.b64decode(encoded, validate=True))
        self.assertEqual(approved["slug"], selected_job.slug)
        self.assertEqual(approved["request_id"], selected_job.request_id)
        self.assertEqual(approved["source_sha"], selected_job.source_sha)
        self.assertEqual(approved["verified_at"], evidence()["verified_at"])

    def test_existing_identity_reuse_requires_verified_provenance(self):
        official = evidence()
        selected_job = Job.validate(job(), config())
        package = package_result()
        approved = {
            "schema_version": "1.0", "reviewed": True, "source": "partner_center",
            **{k: official[k] for k in ("store_id", "name", "publisher", "version",
                                        "package_family_name", "package_sid")},
            "request_id": selected_job.request_id, "product_type": selected_job.product_type,
            "slug": selected_job.slug,
            "source_factory": selected_job.source_factory, "source_repository": selected_job.source_repository,
            "source_branch": selected_job.source_branch, "source_sha": selected_job.source_sha,
            "verified_source_sha": selected_job.source_sha, "package_sha256": package["sha256"],
            "signature_status": package["signature_status"],
            "verified_by": official["authenticated_account"],
            "evidence_url": official["official_evidence_url"],
            "verified_at": official["verified_at"],
        }
        def wrapped(obj):
            return {"encoding": "base64", "content": base64.b64encode(
                json.dumps(obj).encode("utf-8")).decode("ascii")}
        self.assertTrue(GitHubReturnClient._existing_matches(wrapped(approved), official, selected_job, package))
        for changes in ({"reviewed": 1}, {"reviewed": False}, {"source": "unverified"},
                        {"verified_by": "wrong-user"}, {"evidence_url": "https://evil.invalid"},
                        {"verified_at": "2000-01-01T00:00:00Z"},
                        {"store_id": "9N0000000000"}, {"slug": "another-game"},
                        {"schema_version": "0.9"}):
            with self.subTest(changes=changes):
                self.assertFalse(GitHubReturnClient._existing_matches(
                    wrapped({**approved, **changes}), official, selected_job, package))
        for missing in approved:
            with self.subTest(missing=missing):
                self.assertFalse(GitHubReturnClient._existing_matches(
                    wrapped({k: v for k, v in approved.items() if k != missing}), official, selected_job, package))
        self.assertFalse(GitHubReturnClient._existing_matches(
            wrapped({**approved, "unreviewed_extra": "value"}), official, selected_job, package))
        self.assertFalse(GitHubReturnClient._existing_matches(wrapped([]), official, selected_job, package))
        duplicate = '{"source_sha":"' + "b" * 40 + '",' + json.dumps(approved)[1:]
        duplicate_item = {"encoding": "base64", "content": base64.b64encode(
            duplicate.encode("utf-8")).decode("ascii")}
        self.assertFalse(GitHubReturnClient._existing_matches(
            duplicate_item, official, selected_job, package))

    def test_existing_identity_reports_branch_commit_not_blob_sha(self):
        official = evidence()
        selected_job = Job.validate(job(), config())
        package = package_result()
        approved = {
            "schema_version": "1.0", "reviewed": True, "source": "partner_center",
            **{k: official[k] for k in ("store_id", "name", "publisher", "version",
                                        "package_family_name", "package_sid")},
            "request_id": selected_job.request_id, "product_type": selected_job.product_type,
            "slug": selected_job.slug,
            "source_factory": selected_job.source_factory, "source_repository": selected_job.source_repository,
            "source_branch": selected_job.source_branch, "source_sha": selected_job.source_sha,
            "verified_source_sha": selected_job.source_sha, "package_sha256": package["sha256"],
            "signature_status": package["signature_status"],
            "verified_by": official["authenticated_account"],
            "evidence_url": official["official_evidence_url"],
            "verified_at": official["verified_at"],
        }
        def fake_api(endpoint, body=None, allow_missing=False):
            if "git/ref/heads/" in endpoint:
                return {"object": {"sha": SHA}}
            if "/manifest.json" in endpoint:
                raw = json.dumps({"slug": "sample-product", "kind": "game"}).encode()
                return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
            if "/proposals/" in endpoint:
                raw = json.dumps({"slug": "sample-product", "title": "Sample Product"}).encode()
                return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
            if "/approved-identity.json" in endpoint:
                return {"sha": "b" * 40, **{"encoding": "base64",
                        "content": base64.b64encode(json.dumps(approved).encode()).decode()}}
            raise AssertionError("unexpected API write or read: " + endpoint)
        result = GitHubReturnClient(fake_api).return_identity(
            selected_job, config(), official, package, True)
        self.assertEqual(result["status"], "EXISTING_VERIFIED")
        self.assertEqual(result["commit_sha"], SHA)
        self.assertNotEqual(result["commit_sha"], "b" * 40)

    def test_no_apply_is_side_effect_free(self):
        def forbidden(*_a, **_k):
            raise AssertionError("API must not be called")
        result = GitHubReturnClient(forbidden).return_identity(
            Job.validate(job(), config()), config(), evidence(), package_result(), False)
        self.assertEqual(result["status"], "NOT_APPLIED")
    def test_head_mismatch_is_conflict(self):
        def wrong_head(*_a, **_k):
            return {"object": {"sha": "c" * 40}}
        with self.assertRaises(ConflictError):
            GitHubReturnClient(wrong_head).return_identity(
                Job.validate(job(), config()), config(), evidence(), package_result(), True)
    def test_existing_different_identity_is_conflict(self):
        def existing(endpoint, body=None, allow_missing=False):
            if "git/ref" in endpoint:
                return {"object": {"sha": SHA}}
            if "/manifest.json" in endpoint:
                raw = json.dumps({"slug": "sample-product", "kind": "app" if config().product_type == "APP" else "game"}).encode()
                return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
            if "/proposals/" in endpoint:
                raw = json.dumps({"slug": "sample-product", "title": "Sample Product"}).encode()
                return {"encoding": "base64", "content": base64.b64encode(raw).decode()}
            return {"encoding": "base64", "content": base64.b64encode(b'{"store_id":"OTHER000"}').decode()}
        with self.assertRaises(ConflictError):
            GitHubReturnClient(existing).return_identity(
                Job.validate(job(), config()), config(), evidence(), package_result(), True)

    def test_job_work_branch_drives_ref_read_and_atomic_write(self):
        selected = "codex/product/sample-product"
        seen = []

        def api(endpoint, body=None, allow_missing=False):
            seen.append((endpoint, body))
            return self.api(endpoint, body, allow_missing)

        result = GitHubReturnClient(api).return_identity(
            Job.validate(job(source_branch=selected), config()), config(), evidence(), package_result(), True)
        self.assertEqual(result["branch"], selected)
        self.assertIn("git/ref/heads/" + selected, seen[0][0])
        graphql = next(body for endpoint, body in seen if endpoint == "graphql")
        self.assertEqual(graphql["variables"]["input"]["branch"]["branchName"], selected)


class OrchestratorTests(unittest.TestCase):
    def runner(self, root, source=None, builder=None, identity=None, github=None):
        return Provisioner(config(), Path(root) / "state", Path(root) / "work",
                           source=source or FakeSource(), builder=builder or FakeBuilder(),
                           identity=identity or FakeIdentity(), github=github or FakeGitHub())

    def resume_fixture(self, root):
        builder = FakeBuilder(artifact_kind="exe")
        package_path = builder.build(Job.validate(job(), config()), Path(root), Path(root) / "prior", config())
        package = inspect_package(package_path)
        result = {
            "schema_version": "1.0", "request_id": "req-0001",
            "product_type": config().product_type, "source_factory": config().source_factory,
            "source_repository": config().source_repository,
            "source_branch": config().source_branch, "source_sha": SHA,
            "slug": "sample-product", "status": "HOLD",
            "package": package,
            "official_identity": {"status": "UNVERIFIED", "store_id": None},
            "github_return": {"status": "NOT_APPLIED", "commit_sha": None},
            "next_stage": "OBTAIN_AUTHENTICATED_OFFICIAL_IDENTITY",
        }
        path = Path(root) / "prior-result.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        return path, package

    def test_resume_result_reinspects_exact_exe_without_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            resume, package = self.resume_fixture(tmp)
            source, builder = FakeSource(), FakeBuilder(artifact_kind="exe")
            runner = Provisioner(config(), Path(tmp) / "state", Path(tmp) / "work",
                                 source=source, builder=builder,
                                 identity=FakeIdentity(error=HoldError("no identity")),
                                 github=FakeGitHub(), resume_result=resume)
            result = runner.run(job(), apply=False)
            self.assertEqual(result["next_stage"], "OBTAIN_AUTHENTICATED_OFFICIAL_IDENTITY")
            self.assertEqual(result["package"]["sha256"], package["sha256"])
            self.assertEqual(source.calls, 0)
            self.assertEqual(builder.calls, 0)

    def test_resume_result_rejects_malformed_status_objects_without_rebuild(self):
        for field, invalid in (("github_return", ["NOT_APPLIED"]),
                               ("official_identity", "UNVERIFIED")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                resume, _ = self.resume_fixture(tmp)
                previous = json.loads(resume.read_text(encoding="utf-8"))
                previous[field] = invalid
                resume.write_text(json.dumps(previous), encoding="utf-8")
                source, builder = FakeSource(), FakeBuilder(artifact_kind="exe")
                runner = Provisioner(config(), Path(tmp) / "state", Path(tmp) / "work",
                                     source=source, builder=builder,
                                     identity=FakeIdentity(), github=FakeGitHub(),
                                     resume_result=resume)
                result = runner.run(job(), apply=False)
                self.assertEqual(result["status"], "CONFLICT")
                self.assertEqual(result["next_stage"], "RECONCILE_CONFLICT")
                self.assertEqual(source.calls, 0)
                self.assertEqual(builder.calls, 0)

    def test_resume_result_rejects_nonabsolute_or_nonstr_path_before_build(self):
        # A scheduler must not reinterpret a relative path in its own cwd,
        # or coerce a malformed path to a string, when resuming pinned bytes.
        for bad_path in ("SignalSprint.exe", 42, [], None, "bad\x00path.exe"):
            with self.subTest(path=repr(bad_path)), tempfile.TemporaryDirectory() as tmp:
                resume, _ = self.resume_fixture(tmp)
                previous = json.loads(resume.read_text(encoding="utf-8"))
                previous["package"]["path"] = bad_path
                resume.write_text(json.dumps(previous), encoding="utf-8")
                source, builder, github = FakeSource(), FakeBuilder(artifact_kind="exe"), FakeGitHub()
                runner = Provisioner(config(), Path(tmp) / "state", Path(tmp) / "work",
                                     source=source, builder=builder, identity=FakeIdentity(),
                                     github=github, resume_result=resume)
                result = runner.run(job(), apply=True)
                self.assertEqual(result["status"], "CONFLICT")
                self.assertEqual(result["next_stage"], "RECONCILE_CONFLICT")
                self.assertEqual((source.calls, builder.calls, github.calls), (0, 0, 0))

    def test_resume_result_can_reach_existing_github_cas_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            resume, package = self.resume_fixture(tmp)
            source, builder, github = FakeSource(), FakeBuilder(artifact_kind="exe"), FakeGitHub()
            runner = Provisioner(config(), Path(tmp) / "state", Path(tmp) / "work",
                                 source=source, builder=builder, identity=FakeIdentity(),
                                 github=github, resume_result=resume)
            result = runner.run(job(), apply=False)
            self.assertEqual(result["next_stage"], "APPLY_VERIFIED_GITHUB_RETURN")
            self.assertEqual(result["package"]["sha256"], package["sha256"])
            self.assertEqual(github.calls, 1)
            self.assertEqual(source.calls, 0)
            self.assertEqual(builder.calls, 0)

    def test_dry_run_has_no_external_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, builder, identity, github = FakeSource(), FakeBuilder(), FakeIdentity(), FakeGitHub()
            result = self.runner(tmp, source, builder, identity, github).run(job(dry_run=True), apply=True)
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertEqual((source.calls, builder.calls, identity.calls, github.calls), (0, 0, 0, 0))
    def test_successful_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.runner(tmp).run(job(), apply=True)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["github_return"]["commit_sha"], "b" * 40)
    def test_without_apply_holds_after_local_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.runner(tmp).run(job(), apply=False)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["next_stage"], "APPLY_VERIFIED_GITHUB_RETURN")
    def test_duplicate_request_replays_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = FakeBuilder()
            runner = self.runner(tmp, builder=builder)
            first = runner.run(job(), apply=True)
            second = runner.run(job(), apply=True)
        self.assertEqual(first["status"], "COMPLETED")
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(builder.calls, 1)
    def test_dry_run_can_promote_to_live_after_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, builder, identity, github = FakeSource(), FakeBuilder(), FakeIdentity(), FakeGitHub()
            runner = self.runner(tmp, source, builder, identity, github)
            preview = runner.run(job(dry_run=True), apply=False)
            self.assertEqual(preview["status"], "DRY_RUN")
            self.assertEqual((source.calls, builder.calls, identity.calls, github.calls), (0, 0, 0, 0))
            live = runner.run(job(dry_run=False), apply=True)
            replay = runner.run(job(dry_run=False), apply=True)
            self.assertEqual(live["status"], "COMPLETED")
            self.assertFalse(live["idempotent_replay"])
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual((source.calls, builder.calls, identity.calls, github.calls), (1, 1, 1, 1))

    def test_conflicting_promotion_cannot_replace_original_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = FakeBuilder()
            runner = self.runner(tmp, builder=builder)
            preview = runner.run(job(dry_run=True), apply=False)
            wrong = runner.run(job(dry_run=False, source_sha="b" * 40), apply=True)
            stored = runner.ledger.read("req-0001")
            correct = runner.run(job(dry_run=False), apply=True)
            self.assertEqual(preview["status"], "DRY_RUN")
            self.assertEqual(wrong["status"], "CONFLICT")
            self.assertEqual(stored["response"]["status"], "DRY_RUN")
            self.assertEqual(correct["status"], "COMPLETED")
            self.assertEqual(builder.calls, 1)

    def test_same_request_different_sha_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.runner(tmp)
            runner.run(job(dry_run=True), apply=False)
            result = runner.run(job(dry_run=True, source_sha="b" * 40), apply=False)
        self.assertEqual(result["status"], "CONFLICT")
    def test_missing_identity_is_hold_and_can_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.runner(tmp, identity=FakeIdentity(error=HoldError("identity missing")))
            first = runner.run(job(), apply=True)
            runner.identity = FakeIdentity()
            second = runner.run(job(), apply=True)
        self.assertEqual(first["status"], "HOLD")
        self.assertEqual(second["status"], "COMPLETED")
    def test_retryable_github_failure_is_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.runner(tmp, github=FakeGitHub(error=RetryableError("rate limit"))).run(job(), apply=True)
        self.assertEqual(result["status"], "RETRYABLE_FAILURE")
    def test_package_mismatch_is_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.runner(tmp, builder=FakeBuilder(name="Other.Product")).run(job(), apply=True)
        self.assertEqual(result["status"], "CONFLICT")
    def test_game_msix_without_executable_is_hold_before_identity_return(self):
        class MissingExeBuilder(FakeBuilder):
            def build(self, _job, _source, output_dir, _config):
                output_dir.mkdir(parents=True, exist_ok=True)
                return make_msix(output_dir / "no-executable.msix", include_exe=False)
        with tempfile.TemporaryDirectory() as tmp:
            identity, github = FakeIdentity(), FakeGitHub()
            result = self.runner(tmp, builder=MissingExeBuilder(), identity=identity, github=github).run(
                job(), apply=True)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("manifest-bound executable payload", result["errors"][0])
        self.assertEqual((identity.calls, github.calls), (0, 0))

    def test_exe_only_build_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.runner(tmp, builder=FakeBuilder(artifact_kind="exe")).run(job(), apply=True)
        self.assertEqual(result["status"], "HOLD")

    def test_exe_identity_return_rejects_invalid_pe_before_partner_lookup(self):
        class InvalidExeBuilder(FakeBuilder):
            def build(self, *args):
                path = super().build(*args)
                path.write_bytes(b"not a Windows executable")
                return path
        with tempfile.TemporaryDirectory() as tmp:
            identity, github = FakeIdentity(), FakeGitHub()
            result = self.runner(
                tmp, builder=InvalidExeBuilder(artifact_kind="exe"),
                identity=identity, github=github).run(job(), apply=True)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual((identity.calls, github.calls), (0, 0))
        self.assertEqual(result["next_stage"], "RESOLVE_HOLD")

    def test_exe_stage_returns_official_identity_without_claiming_msix(self):
        with tempfile.TemporaryDirectory() as tmp:
            github = FakeGitHub()
            result = self.runner(
                tmp, builder=FakeBuilder(artifact_kind="exe"), github=github
            ).run(job(), apply=True)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["package"]["kind"], "exe")
        self.assertRegex(result["package"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["official_identity"]["status"], "VERIFIED_OPERATOR_EXPORT")
        self.assertEqual(result["github_return"]["status"], "APPLIED")
        self.assertEqual(result["next_stage"], "GITHUB_REBUILD_MSIX")
        self.assertIsNone(result["windows_all_auto_record"])
        self.assertEqual(github.calls, 1)

    def test_exe_missing_official_evidence_preserves_real_build_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            github = FakeGitHub()
            result = self.runner(
                tmp, builder=FakeBuilder(artifact_kind="exe"),
                identity=FakeIdentity(error=HoldError("Partner Center unavailable")),
                github=github,
            ).run(job(), apply=True)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["package"]["kind"], "exe")
        self.assertRegex(result["package"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["next_stage"], "OBTAIN_AUTHENTICATED_OFFICIAL_IDENTITY")
        self.assertEqual(github.calls, 0)

    def test_exe_identity_return_replay_never_rebuilds_or_reapplies(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder, github = FakeBuilder(artifact_kind="exe"), FakeGitHub()
            runner = self.runner(tmp, builder=builder, github=github)
            first = runner.run(job(), apply=True)
            replay = runner.run(job(), apply=True)
            collision = runner.run(job(source_sha="b" * 40), apply=True)
        self.assertEqual(first["status"], "HOLD")
        self.assertEqual(first["github_return"]["status"], "APPLIED")
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["next_stage"], "GITHUB_REBUILD_MSIX")
        self.assertEqual(collision["status"], "CONFLICT")
        self.assertEqual((builder.calls, github.calls), (1, 1))

    def test_game_msix_with_orphan_executable_is_hold_before_identity_return(self):
        class OrphanBuilder(FakeBuilder):
            def build(self, _job, _source, output_dir, _config):
                path = super().build(_job, _source, output_dir, _config)
                with zipfile.ZipFile(path, "r") as archive:
                    manifest = archive.read("AppxManifest.xml").decode()
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("AppxManifest.xml", manifest.replace(
                        'Executable="bin/Sample.exe"', 'Executable="bin/Missing.exe"'))
                    archive.writestr("AppxBlockMap.xml", "<BlockMap/>")
                    archive.writestr("[Content_Types].xml", "<Types/>")
                    archive.writestr("bin/Sample.exe", b"MZhelper")
                return path
        with tempfile.TemporaryDirectory() as tmp:
            identity, github = FakeIdentity(), FakeGitHub()
            result = self.runner(tmp, builder=OrphanBuilder(), identity=identity, github=github).run(
                job(), apply=True)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("manifest-bound executable", result["errors"][0])
        self.assertEqual((identity.calls, github.calls), (0, 0))

    def test_type_state_is_namespaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.runner(tmp)
            runner.run(job(dry_run=True), apply=False)
            self.assertIn(config().product_type.lower(), str(runner.ledger.records))


class MachineReadableErrorContractTests(unittest.TestCase):
    def test_invalid_field_types_still_produce_schema_compatible_hold(self):
        # The scheduler must parse a failed job without arbitrary JSON types
        # in the result-v1.0 string-or-null correlation fields.
        malformed = job(source_factory=17, source_repository=[],
                        source_branch=42, source_sha={}, slug=False)
        with tempfile.TemporaryDirectory() as tmp:
            result = Provisioner(config(), Path(tmp) / "state",
                                 Path(tmp) / "work").run(malformed)
        self.assertEqual(result["status"], "HOLD")
        for field in ("source_factory", "source_repository", "source_branch",
                      "source_sha", "slug"):
            self.assertIsNone(result[field], field)
        self.assertEqual(result["github_return"]["status"], "NOT_APPLIED")
        self.assertEqual(result["package"]["status"], "NOT_BUILT")


class FailureClassificationTests(unittest.TestCase):
    def test_git_timeout_is_retryable(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["git"], 1)):
            with self.assertRaises(RetryableError):
                SourceManager._run(["git", "fetch"], 1)
    def test_github_timeout_is_retryable(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["gh"], 1)):
            with self.assertRaises(RetryableError):
                GitHubReturnClient._gh_api("graphql")
    def test_github_401_is_hold(self):
        completed = subprocess.CompletedProcess(["gh"], 1, "", "HTTP 401: Bad credentials")
        with patch("subprocess.run", return_value=completed), self.assertRaises(HoldError):
            GitHubReturnClient._gh_api("graphql")
    def test_github_403_is_hold(self):
        completed = subprocess.CompletedProcess(["gh"], 1, "", "HTTP 403: Resource not accessible")
        with patch("subprocess.run", return_value=completed), self.assertRaises(HoldError):
            GitHubReturnClient._gh_api("graphql")
    def test_github_404_is_conflict(self):
        completed = subprocess.CompletedProcess(["gh"], 1, "", "HTTP 404: Not Found")
        with patch("subprocess.run", return_value=completed), self.assertRaises(ConflictError):
            GitHubReturnClient._gh_api("graphql")
    def test_github_422_is_conflict(self):
        completed = subprocess.CompletedProcess(["gh"], 1, "", "HTTP 422: Validation Failed")
        with patch("subprocess.run", return_value=completed), self.assertRaises(ConflictError):
            GitHubReturnClient._gh_api("graphql")
    def test_github_429_is_retryable(self):
        completed = subprocess.CompletedProcess(["gh"], 1, "", "HTTP 429: rate limit")
        with patch("subprocess.run", return_value=completed), self.assertRaises(RetryableError):
            GitHubReturnClient._gh_api("graphql")
    def test_secret_redaction(self):
        self.assertNotIn("supersecret", redact("Authorization: bearer supersecret"))
    def test_build_failure_keeps_redacted_root_cause_from_output_tail(self):
        completed = subprocess.CompletedProcess(
            ["builder"], 17, "stdout detail", "Authorization: bearer supersecret\n" + "noise" * 500 + "\nROOT_CAUSE")
        with patch("subprocess.run", return_value=completed), self.assertRaises(HoldError) as raised:
            PackageBuilder._run(["builder"], ROOT, 10)
        message = str(raised.exception)
        self.assertIn("exit 17", message)
        self.assertIn("ROOT_CAUSE", message)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn("supersecret", message)
    def test_signal_sprint_builder_selects_real_game_not_newer_decoy(self):
        class StubBuilder(PackageBuilder):
            def _build_windows(self, source):
                output = source / "dist" / "game"
                output.mkdir(parents=True)
                (output / "SignalSprint.exe").write_bytes(b"MZ" + b"game" * 100)
                (output / "Helper.exe").write_bytes(b"MZ" + b"decoy" * 100)
                os.utime(output / "Helper.exe", (2_000_000_000, 2_000_000_000))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            built = StubBuilder().build(
                Job.validate(job(slug="signal-sprint"), config()),
                root, root / "out", config())
            self.assertEqual(built.name, "SignalSprint.exe")

    def test_signal_sprint_builder_rejects_missing_expected_executable(self):
        class WrongBuilder(PackageBuilder):
            def _build_windows(self, source):
                output = source / "dist" / "game"
                output.mkdir(parents=True)
                (output / "Helper.exe").write_bytes(b"MZ" + b"decoy" * 100)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(HoldError, "fresh pinned executable"):
                WrongBuilder().build(
                    Job.validate(job(slug="signal-sprint"), config()),
                    root, root / "out", config())

    def test_live_builder_rejects_unknown_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HoldError):
                PackageBuilder()._build_windows(Path(tmp))
    def test_windows_builder_prefers_pwsh_for_factory_script(self):
        calls = []
        class RecordingBuilder(PackageBuilder):
            @staticmethod
            def _run(command, cwd, timeout):
                calls.append((command, cwd, timeout))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "scripts" / "build-windows.ps1"
            script.parent.mkdir()
            script.write_text("Write-Output ok", encoding="utf-8")
            with patch("shutil.which", side_effect=lambda name: "C:/tools/pwsh.exe" if name == "pwsh" else None):
                RecordingBuilder()._build_windows(root)
        self.assertEqual(calls[0][0][0], "C:/tools/pwsh.exe")
    def test_godot_missing_project_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(HoldError):
                PackageBuilder()._build_godot(root, root / "out")
    def test_godot_invalid_project_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project.godot").write_text("[application]", encoding="utf-8")
            (root / "export_presets.cfg").write_text("[preset.0]", encoding="utf-8")
            with self.assertRaises(HoldError):
                PackageBuilder()._build_godot(root, root / "out")
    def test_parallel_lock_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "same.lock"
            with RequestLock(path):
                with self.assertRaises(ConflictError):
                    RequestLock(path).__enter__()
    def test_ledger_is_atomic_and_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp))
            ledger.write("req", {"value": 1})
            self.assertEqual(ledger.read("req"), {"value": 1})

    def test_ledger_retries_transient_windows_replace_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp))
            real_replace = os.replace
            attempts = 0

            def transient_lock(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("transient file lock")
                return real_replace(source, destination)

            with patch("package_identity_provisioner.os.replace", side_effect=transient_lock), \
                    patch("package_identity_provisioner.time.sleep") as sleep:
                ledger.write("req", {"value": 1})

            self.assertEqual(attempts, 2)
            sleep.assert_called_once_with(0.025)
            self.assertEqual(ledger.read("req"), {"value": 1})


if __name__ == "__main__":
    unittest.main()
