"""Synthetic-only checks for distinct Signal Sprint reissue lineage (no CAS)."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from gdk_build_intake import ARTIFACT_SHA256, EXE_SHA256
from gdk_new_lineage_reissue_check import check_reissue, SOURCE, OLD_REQUEST
from gdk_exact_bytes_recovery_receipt import ORIGINAL_ARTIFACT_ID
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_JOB, PINNED_SIGNAL_SPRINT_GDK_IDENTITY

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

class NewLineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive_path = self.root / "new.zip"
        self.proposal_path = self.root / "proposal.json"
        self.exe = b"MZ" + b"new-synthetic-executable" * 50
        self.run_id = 500001
        self.artifact_id = 600001
        self.new_request = f"game-signal-sprint-reissue-{SOURCE}-{self.run_id}"
        self.build_id = f"gdk-reissue-{self.run_id}-{self.artifact_id}"
        self.provenance = {
            **PINNED_SIGNAL_SPRINT_JOB, "request_id": self.new_request,
            "build_id": self.build_id, "workflow_run_id": self.run_id,
            "artifact_id": self.artifact_id, "executable": "SignalSprint.exe",
            "executable_sha256": sha(self.exe), "artifact_kind": "EXE_QA_UNSIGNED",
        }
        self.request = {
            **PINNED_SIGNAL_SPRINT_JOB, "request_id": self.new_request,
            "build_id": self.build_id, "workflow_run_id": self.run_id,
            "artifact_id": self.artifact_id, "dry_run": True,
        }
        self.proposal = {
            "schema_version": 1, "decision": "REQUEST_NEW_IMMUTABLE_BUILD_LINEAGE",
            "product": "Signal Sprint", "partner_center_selection": "GDK_GAME",
            "source_sha": SOURCE, "source_branch": PINNED_SIGNAL_SPRINT_JOB["source_branch"],
            "original_request_id": OLD_REQUEST, "original_artifact_id": ORIGINAL_ARTIFACT_ID,
            "new_request_id": self.new_request, "build_id": self.build_id,
            "workflow_run_id": self.run_id, "artifact_id": self.artifact_id,
            "zip_sha256": "", "exe_sha256": sha(self.exe),
            "reviewed_by": "Windows Release Owner", "reviewed_at": "2026-11-02T04:15:00+09:00",
            "store_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["store_id"],
            "xbox_title_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["xbox_title_id"],
            "xbox_scid": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["xbox_scid"],
            "msa_app_id": PINNED_SIGNAL_SPRINT_GDK_IDENTITY["msa_app_id"],
        }
        self.write()

    def write(self, *, refresh_zip=True):
        if refresh_zip:
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w") as z:
                z.writestr("SignalSprint.exe", self.exe)
                z.writestr("provenance.json", json.dumps(self.provenance))
                z.writestr("provisioner-request.json", json.dumps(self.request))
            self.archive_path.write_bytes(out.getvalue())
            self.proposal["zip_sha256"] = sha(out.getvalue())
        self.proposal_path.write_text(json.dumps(self.proposal), encoding="utf-8")

    def check(self):
        return check_reissue(self.proposal_path, self.archive_path)

    def assert_hold(self, reason=None):
        result = self.check()
        self.assertEqual(result["status"], "NEW_LINEAGE_REISSUE_HOLD")
        self.assertFalse(result["ready_for_cas"])
        if reason:
            self.assertEqual(result["reason"], reason)

    def test_new_lineage_check_only_never_releases_old_artifact(self):
        result = self.check()
        self.assertEqual(result["status"], "NEW_LINEAGE_CHECK_ONLY")
        self.assertTrue(result["new_lineage_check_only"])
        self.assertEqual(result["original_lineage_status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertEqual(result["original_request_id"], OLD_REQUEST)
        self.assertNotEqual(result["new_request_id"], OLD_REQUEST)
        self.assertEqual(result["source_sha"], SOURCE)
        for key in ("ready_for_cas", "cas_return_pass", "gdk_sdk_validated",
                    "real_msixvc_built", "e2e_pass", "store_submitted",
                    "approval_authenticity_verified"):
            self.assertFalse(result[key])

    def test_missing_evidence_hold(self):
        self.assertEqual(check_reissue(None, None)["reason"], "NEW_LINEAGE_EVIDENCE_MISSING")
        self.archive_path.unlink()
        self.assert_hold("MISSING_OR_UNREADABLE_FILE")

    def test_reused_original_request_rejected(self):
        self.proposal["new_request_id"] = OLD_REQUEST
        self.write(refresh_zip=False)
        self.assert_hold("NEW_LINEAGE_ID_NOT_DISTINCT")

    def test_reused_original_artifact_id_rejected(self):
        self.proposal["artifact_id"] = ORIGINAL_ARTIFACT_ID
        self.write(refresh_zip=False)
        self.assert_hold("RUN_OR_ARTIFACT_ID_INVALID")

    def test_changed_source_rejected(self):
        self.proposal["source_sha"] = "f" * 40
        self.write(refresh_zip=False)
        self.assert_hold("ORIGINAL_SOURCE_OR_PRODUCT_MISMATCH")

    def test_cross_product_identity_rejected(self):
        for key in ("store_id", "xbox_title_id", "xbox_scid", "msa_app_id"):
            with self.subTest(key=key):
                self.proposal[key] = "OTHER"
                self.write(refresh_zip=False)
                self.assert_hold("ORIGINAL_SOURCE_OR_PRODUCT_MISMATCH")
                self.proposal[key] = PINNED_SIGNAL_SPRINT_GDK_IDENTITY[key]

    def test_version_is_not_implicitly_approved(self):
        self.proposal["package_version"] = "1.0.0.0"
        self.write(refresh_zip=False)
        self.assert_hold("PROPOSAL_SCHEMA_MISMATCH")

    def test_repacked_zip_rejected(self):
        with zipfile.ZipFile(self.archive_path, "a") as z:
            z.comment = b"repacked"
        self.assert_hold("NEW_ZIP_DIGEST_MISMATCH")

    def test_exe_digest_mismatch_rejected(self):
        self.proposal["exe_sha256"] = "a" * 64
        self.write(refresh_zip=False)
        self.assert_hold("NEW_EXE_DIGEST_MISMATCH")

    def test_reused_original_exe_digest_rejected(self):
        self.proposal["exe_sha256"] = EXE_SHA256
        self.write(refresh_zip=False)
        self.assert_hold("NEW_LINEAGE_DIGEST_MISSING_OR_REUSED")

    def test_wrong_provenance_product_rejected(self):
        self.provenance["slug"] = "other-game"
        self.write()
        self.assert_hold("NEW_ARCHIVE_PROVENANCE_OR_REQUEST_MISMATCH")

    def test_old_request_in_new_zip_rejected(self):
        self.request["request_id"] = OLD_REQUEST
        self.write()
        self.assert_hold("NEW_ARCHIVE_PROVENANCE_OR_REQUEST_MISMATCH")

    def test_provenance_build_id_conflict_rejected(self):
        self.provenance["build_id"] = "gdk-reissue-other"
        self.write()
        self.assert_hold("NEW_ARCHIVE_PROVENANCE_OR_REQUEST_MISMATCH")

    def test_duplicate_json_key_rejected(self):
        raw = self.proposal_path.read_text()
        self.proposal_path.write_text(raw.replace('"schema_version": 1',
             '"schema_version": 1, "schema_version": 1'), encoding="utf-8")
        self.assert_hold("INVALID_PROPOSAL_JSON")

    def test_symlink_archive_rejected(self):
        link = self.root / "link.zip"
        try:
            link.symlink_to(self.archive_path)
        except (OSError, NotImplementedError):
            self.skipTest("symlink not available")
        self.assertEqual(check_reissue(self.proposal_path, link)["reason"], "SYMLINK_PATH")

    def test_read_only_evidence(self):
        before = (self.proposal_path.read_bytes(), self.archive_path.read_bytes())
        self.check()
        self.assertEqual(before, (self.proposal_path.read_bytes(), self.archive_path.read_bytes()))

if __name__ == "__main__":
    unittest.main()
