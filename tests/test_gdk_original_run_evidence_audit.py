"""Synthetic read-only original run log provenance tests; never perform CAS."""
import json
from pathlib import Path
import tempfile
import unittest

from gdk_build_intake import ARTIFACT_SHA256, EXE_SHA256
from gdk_exact_bytes_recovery_receipt import HANDOFF_EXE_SHA256, ORIGINAL_ARTIFACT_ID
from gdk_original_run_evidence_audit import (
    EvidenceError, audit, parse_original_job_log, read_original_job_log,
)
from package_identity_provisioner import PINNED_SIGNAL_SPRINT_JOB

SOURCE = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
STAMP = "2026-10-27T03:18:52.4943181Z "


def original_log(*, exe=EXE_SHA256, verified_exe=None, zip_digest=ARTIFACT_SHA256,
                 artifact_id=ORIGINAL_ARTIFACT_ID, source=SOURCE):
    if verified_exe is None:
        verified_exe = exe
    lines = [
        STAMP + "GAME_UNSIGNED_EXE_SHA256=" + exe,
        STAMP + "GAME EXE SHA256: " + verified_exe,
        STAMP + "SHA256 digest of uploaded artifact zip is " + zip_digest,
        STAMP + "Artifact ID " + str(artifact_id),
        STAMP + "Artifact ID is " + str(artifact_id),
        STAMP + "  name: game-signal-sprint-exe-" + source,
        STAMP + "[command]git fetch origin +" + source
        + ":refs/remotes/origin/codex/game-signal-sprint-undo-20261027",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


class OriginalRunEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "original-job.log"
        self.log.write_bytes(original_log())

    def test_primary_log_supports_repository_exe_but_not_handoff(self):
        parsed = parse_original_job_log(self.log.read_bytes())
        self.assertEqual(parsed["exe_sha256"], EXE_SHA256)
        self.assertEqual(parsed["zip_sha256"], ARTIFACT_SHA256)
        self.assertEqual(parsed["source_sha"], SOURCE)
        self.assertNotEqual(parsed["exe_sha256"], HANDOFF_EXE_SHA256)
        self.assertFalse(parsed["log_authenticity_verified"])

    def test_discrepancy_receipt_is_fail_closed_and_machine_readable(self):
        result = audit([], [], self.log)
        self.assertEqual(result["status"], "ARTIFACT_EXACT_BYTES_HOLD")
        self.assertEqual(result["reason"], "EXPECTED_DIGEST_AUTHORITY_CONFLICT")
        self.assertTrue(result["digest_authorities"]["log_matches_repository_exe"])
        self.assertFalse(result["digest_authorities"]["log_matches_handoff_exe"])
        self.assertTrue(result["digest_authorities"]["log_matches_both_zip_pins"])
        self.assertFalse(result["ready_for_cas"])
        self.assertFalse(result["cas_return_pass"])
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["receipt_authenticity_verified"])
        self.assertEqual(json.loads(json.dumps(result))["artifact_id"], ORIGINAL_ARTIFACT_ID)

    def test_missing_job_log_is_hold(self):
        result = audit([], [], None)
        self.assertEqual(result["digest_authorities"]["github_actions_original_job_log"]["status"],
                         "PRIMARY_LOG_NOT_PROVIDED")
        self.assertFalse(result["original_bytes_verified"])

    def test_missing_original_zip_is_independent_hold(self):
        result = audit([self.root / "missing.zip"], [], self.log)
        self.assertEqual(result["original_archive_evidence"]["candidates_checked"], 1)
        self.assertEqual(result["original_archive_evidence"]["candidates"][0]["reason"],
                         "UNREADABLE_OR_INVALID_ARCHIVE")
        self.assertFalse(result["original_bytes_verified"])

    def test_mismatched_build_and_verify_exe_rejected(self):
        with self.assertRaises(EvidenceError):
            parse_original_job_log(original_log(verified_exe=HANDOFF_EXE_SHA256))

    def test_wrong_product_source_rejected(self):
        with self.assertRaises(EvidenceError):
            parse_original_job_log(original_log(source="f" * 40))

    def test_wrong_artifact_id_rejected(self):
        with self.assertRaises(EvidenceError):
            parse_original_job_log(original_log(artifact_id=12345))

    def test_conflicting_duplicate_log_record_rejected(self):
        forged = original_log() + STAMP.encode() + b"GAME EXE SHA256: " + HANDOFF_EXE_SHA256.encode() + b"\n"
        with self.assertRaises(EvidenceError):
            parse_original_job_log(forged)

    def test_truncated_log_rejected(self):
        with self.assertRaises(EvidenceError):
            parse_original_job_log(original_log().split(b"Artifact ID")[0])

    def test_symlinked_log_is_rejected(self):
        link = self.root / "linked.log"
        try:
            link.symlink_to(self.log)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable on this runner")
        with self.assertRaises(EvidenceError):
            read_original_job_log(link)

    def test_log_file_does_not_change(self):
        before = self.log.read_bytes()
        audit([], [], self.log)
        self.assertEqual(self.log.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
