"""Cross-repo Signal Sprint manifest/assembly binding: deterministic + fail closed.

Fixtures are synthetic. A real Factory artifact is separately rehashed by
the no-write CLI and never treated as a CAS or package approval.
"""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import gdk_new_lineage_cross_repo as cross
import gdk_new_lineage_assembly_plan as assembly
from gdk_new_lineage_post_cas_gate import (
    ARTIFACT_ID, BUILD_HEAD, NEW_REQUEST, OLD_REQUEST, RUN_ID, SOURCE
)
from gdk_microsoft_game_config import ASSETS
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_GDK_IDENTITY as ID


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def archive(files):
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    return out.getvalue()


def encode(data):
    return json.dumps(data, sort_keys=True).encode()


class CrossRepoTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.zip_path = self.root / "github.zip"
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.exe = b"MZ" + b"Q" * 100000
        self.exe_sha = digest(self.exe)
        self.provenance = {
            "request_id": NEW_REQUEST, "source_sha": SOURCE,
            "build_head_sha": BUILD_HEAD, "github_run_id": RUN_ID,
            "legacy_artifact_id": 12706862577, "legacy_artifact_replaced": False,
            "executable_sha256": self.exe_sha, "cas_status": "NOT_EXECUTED",
            "lineage_type": "NEW_IMMUTABLE_BUILD_NOT_OLD_ARTIFACT_RECOVERY",
        }
        self.request = {
            "request_id": NEW_REQUEST, "source_sha": SOURCE,
            "product_type": "GAME", "slug": "signal-sprint", "dry_run": True,
        }
        self.factory = {
            "request_id": NEW_REQUEST, "source_sha": SOURCE,
            "build_head_sha": BUILD_HEAD, "github_run_id": RUN_ID,
            "legacy_artifact_id": 12706862577, "legacy_artifact_replaced": False,
            "executable_sha256": self.exe_sha, "cas_status": "NOT_EXECUTED",
            "github_artifact_id": None, "legacy_artifact_recovered": False,
        }
        for name, _ in ASSETS.values():
            (self.assets / name).write_bytes(("approved-" + name).encode())
        self.rebuild()
        self.version = "1.0.0.0"
        self.display = "Signal Sprint"
        self.plan = self.make_plan()

    def rebuild(self):
        self.provenance_raw = encode(self.provenance)
        self.request_raw = encode(self.request)
        self.inner = archive({
            "SignalSprint.exe": self.exe,
            "provenance.json": self.provenance_raw,
            "provisioner-request.json": self.request_raw,
        })
        self.inner_sha = digest(self.inner)
        self.factory["artifact_sha256"] = self.inner_sha
        self.factory_raw = encode(self.factory)
        self.outer = archive({
            "new-lineage.zip": self.inner,
            "lineage-receipt.json": self.factory_raw,
        })
        self.outer_sha = digest(self.outer)
        self.zip_path.write_bytes(self.outer)
        self.live = {
            "evidence_kind": "GITHUB_ACTIONS_NETWORK_LIVE_CHECK_ONLY",
            "validation_status": "FACTORY_NEW_LINEAGE_GITHUB_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME",
            "source_sha": SOURCE, "build_head_sha": BUILD_HEAD,
            "new_request_id": NEW_REQUEST, "original_request_id": OLD_REQUEST,
            "github_run_id": RUN_ID, "github_artifact_id": ARTIFACT_ID,
            "outer_github_zip_sha256": self.outer_sha,
            "inner_factory_zip_sha256": self.inner_sha,
            "exe_sha256": self.exe_sha,
            "provenance_sha256": digest(self.provenance_raw),
            "request_sha256": digest(self.request_raw),
            "factory_receipt_sha256": digest(self.factory_raw),
            "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
            "original_exe_sha_authority_conflict_unresolved": True,
            "ready_for_cas": False, "cas_return_pass": False,
            "real_msixvc_built": False, "store_submitted": False,
        }

    def make_plan(self):
        xml = assembly.config_xml(self.version, self.display)
        files = []
        for name in sorted(cross.EXPECTED_FILES):
            if name == "SignalSprint.exe":
                data, kind = self.exe, "factory_new_lineage_inner_zip"
            elif name == "MicrosoftGame.config":
                data, kind = xml, "deterministic_generated_config"
            else:
                data = (self.assets / name).read_bytes()
                kind = "reviewed_asset"
            files.append({"destination": name, "sha256": digest(data),
                          "size_bytes": len(data), "source_kind": kind})
        return {
            "status": "NEW_LINEAGE_GDK_ASSEMBLY_PLAN_CHECK_ONLY",
            "partner_center_selection": "GDK_GAME", "package_format": "MSIXVC2",
            "source_sha": SOURCE, "new_request_id": NEW_REQUEST,
            "original_request_id": OLD_REQUEST,
            "original_lineage_status": "ARTIFACT_EXACT_BYTES_HOLD",
            "github_run_id": RUN_ID, "github_artifact_id": ARTIFACT_ID,
            "exe_sha256": self.exe_sha, "xbox_title_id": ID["xbox_title_id"],
            "xbox_scid": ID["xbox_scid"], "msa_app_id": ID["msa_app_id"],
            "package_version": self.version, "reviewed_display_name": self.display,
            "config_xml_utf8": xml.decode("utf-8"), "files": files,
            "cas_return_pass": False, "review_authenticity_verified": False,
            "ready_for_sdk": False, "gdk_sdk_validated": False,
            "real_msixvc_built": False, "e2e_pass": False,
            "store_submitted": False, "staging_created": False,
        }

    def run_check(self, plan=True):
        with patch.object(cross, "OUTER_SHA", self.outer_sha), \
             patch.object(cross, "INNER_SHA", self.inner_sha), \
             patch.object(cross, "EXE_SHA", self.exe_sha), \
             patch.object(assembly, "OUTER_SHA", self.outer_sha), \
             patch.object(assembly, "INNER_SHA", self.inner_sha), \
             patch.object(assembly, "EXE_SHA", self.exe_sha):
            return cross.reconcile(self.zip_path, self.live,
                                   self.plan if plan else None,
                                   self.assets if plan else None)

    def assert_hold(self, code, plan=True):
        r = self.run_check(plan)
        self.assertEqual(r["status"], "CROSS_REPO_INTEGRATION_HOLD")
        self.assertIn(code, r["reason"])
        self.assertFalse(r["staging_created"])
        self.assertFalse(r["ready_for_sdk"])
        self.assertFalse(r["real_msixvc_built"])

    def test_synthetic_six_file_contract_is_reproducible(self):
        a, b = self.run_check(), self.run_check()
        self.assertEqual(a, b)
        self.assertEqual(a["status"], "CROSS_REPO_ASSEMBLY_CONTRACT_CHECK_ONLY")
        self.assertEqual([f["destination"] for f in a["files"]],
                         sorted(cross.EXPECTED_FILES))
        self.assertEqual(a["exe_sha256"], self.exe_sha)
        self.assertEqual(a["partner_center_selection"], "GDK_GAME")
        self.assertFalse(a["cas_return_pass"])
        self.assertFalse(a["ready_for_sdk"])
        self.assertFalse(a["store_submitted"])

    def test_real_approvals_absent_is_hold_without_file_plan(self):
        r = self.run_check(plan=False)
        self.assertEqual(r["status"], "CROSS_REPO_INTEGRATION_HOLD")
        self.assertTrue(r["artifact_manifest_bound"])
        self.assertNotIn("files", r)
        self.assertIn("CAS_VERSION_AND_ASSET_APPROVALS_NOT_AVAILABLE", r["reason"])

    def test_old_request_in_factory_manifest_rejected(self):
        self.provenance["request_id"] = OLD_REQUEST
        self.rebuild()
        self.assert_hold("FACTORY_MANIFEST_LINEAGE_MISMATCH")

    def test_old_artifact_id_rejected(self):
        self.factory["legacy_artifact_id"] = ARTIFACT_ID
        self.rebuild()
        self.assert_hold("LEGACY_ARTIFACT_SUBSTITUTION")

    def test_wrong_live_artifact_id_rejected(self):
        self.live["github_artifact_id"] = 12706862577
        self.assert_hold("LIVE_RECEIPT_LINEAGE_MISMATCH")

    def test_foreign_identity_title_id_rejected(self):
        self.plan["xbox_title_id"] = "00000000"
        self.assert_hold("ASSEMBLY_LINEAGE_IDENTITY_MISMATCH")

    def test_wrong_registration_rejected(self):
        self.plan["partner_center_selection"] = "MSIX_OR_PWA_GAME"
        self.assert_hold("ASSEMBLY_LINEAGE_IDENTITY_MISMATCH")

    def test_tampered_asset_rejected(self):
        (self.assets / "Logo.png").write_bytes(b"tampered")
        self.assert_hold("ASSEMBLY_FILE_SHA_OR_SOURCE_MISMATCH:Logo.png")

    def test_extra_staging_file_rejected(self):
        (self.assets / "unexpected.png").write_bytes(b"unexpected")
        self.assert_hold("ASSET_FILE_SET_MISMATCH")

    def test_wrong_exe_hash_in_plan_rejected(self):
        self.plan["files"][0]["sha256"] = "0" * 64
        self.assert_hold("ASSEMBLY_FILE_SHA_OR_SOURCE_MISMATCH")

    def test_outer_zip_mutation_rejected(self):
        self.zip_path.write_bytes(self.outer + b"tamper")
        self.assert_hold("OUTER_ZIP_SHA_MISMATCH")

    def test_wrong_source_rejected(self):
        self.live["source_sha"] = "0" * 40
        self.assert_hold("LIVE_RECEIPT_LINEAGE_MISMATCH")

    def test_false_sdk_success_rejected(self):
        self.plan["gdk_sdk_validated"] = True
        self.assert_hold("ASSEMBLY_FALSE_AUTHORIZATION")


if __name__ == "__main__":
    unittest.main()
