"""Synthetic GitHub API contract tests: never create a real branch or CAS."""
import base64
import json
import unittest

import gdk_remote_build_branch_bootstrap as remote
from gdk_build_intake import APPROVED_FIELDS, APPROVED_PATH, EXE_SHA256
from package_identity_provisioner import (
    ConflictError, RetryableError, PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
    PINNED_SIGNAL_SPRINT_JOB,
)

SOURCE = PINNED_SIGNAL_SPRINT_JOB["source_sha"]
CAS = "b" * 40
OTHER = "d" * 40
CAS_BRANCH = "codex/game-signal-sprint-gdk-cas-" + SOURCE[:12]
BUILD_BRANCH = "codex/game-signal-sprint-gdk-build-" + CAS[:12]


class FakeAPI:
    def __init__(self):
        self.refs = {PINNED_SIGNAL_SPRINT_JOB["source_branch"]: SOURCE, CAS_BRANCH: CAS}
        self.calls = []
        self.parents = [{"sha": SOURCE}]
        self.files = [{"filename": APPROVED_PATH, "status": "added"}]
        self.approved = {
            **PINNED_SIGNAL_SPRINT_JOB, **PINNED_SIGNAL_SPRINT_GDK_IDENTITY,
            "schema_version": "1.0", "reviewed": True,
            "verified_source_sha": SOURCE, "package_sha256": EXE_SHA256,
            "source": "partner_center_user_provided",
            "identity_source": "USER_PROVIDED_PARTNER_CENTER",
            "packaging_family": "GDK", "signature_status": "QA_UNSIGNED",
            "provided_at": "2026-10-28T12:00:00Z",
        }
        assert set(self.approved) == APPROVED_FIELDS
        self.mutate_after = None
        self.linewrap = False
        self.bad_base64 = False

    def __call__(self, endpoint, body=None, allow_missing=False):
        self.calls.append((endpoint, body))
        if self.mutate_after and len(self.calls) == self.mutate_after:
            self.refs[CAS_BRANCH] = OTHER
        if endpoint.endswith("git/refs") and body:
            assert body == {"ref": "refs/heads/" + BUILD_BRANCH, "sha": CAS}
            if BUILD_BRANCH in self.refs:
                raise ConflictError("already exists")
            self.refs[BUILD_BRANCH] = CAS
            return {"ref": body["ref"]}
        if "git/ref/heads/" in endpoint:
            name = endpoint.split("git/ref/heads/", 1)[1]
            if name not in self.refs:
                if allow_missing:
                    return None
                raise ConflictError("missing ref")
            return {"object": {"sha": self.refs[name]}}
        if endpoint.endswith("commits/" + CAS):
            return {"sha": CAS, "parents": self.parents, "files": self.files}
        if "contents/" + APPROVED_PATH in endpoint:
            assert endpoint.endswith("?ref=" + CAS)
            encoded = base64.b64encode(json.dumps(self.approved).encode()).decode()
            if self.linewrap:
                encoded = "\n".join(encoded[i:i+60] for i in range(0, len(encoded), 60)) + "\n"
            if self.bad_base64:
                encoded = encoded[:10] + "!" + encoded[11:]
            return {"encoding": "base64", "content": encoded}
        raise AssertionError("Unexpected GitHub API call: " + endpoint)


class RemoteBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()

    def run_gate(self, create=False):
        return remote.bootstrap_remote_build_branch(CAS, create=create, api=self.api)

    def test_check_only_does_not_create_remote_ref(self):
        result = self.run_gate()
        self.assertEqual(result["status"], "GDK_REMOTE_BUILD_BRANCH_CHECK_ONLY")
        self.assertFalse(result["remote_ref_exists_at_cas"])
        self.assertNotIn(BUILD_BRANCH, self.api.refs)
        self.assertFalse(any(body for _, body in self.api.calls))

    def test_create_is_idempotent_and_source_stays_immutable(self):
        first = self.run_gate(create=True)
        second = self.run_gate(create=True)
        self.assertEqual(first, second)
        self.assertEqual(self.api.refs[BUILD_BRANCH], CAS)
        self.assertEqual(self.api.refs[PINNED_SIGNAL_SPRINT_JOB["source_branch"]], SOURCE)
        self.assertEqual(len([1 for endpoint, body in self.api.calls if body]), 1)
        self.assertFalse(first["real_msixvc_built"])

    def test_concurrent_identical_create_conflict_is_idempotent(self):
        original = self.api.__call__
        def racing(endpoint, body=None, allow_missing=False):
            if endpoint.endswith("git/refs") and body:
                self.api.refs[BUILD_BRANCH] = CAS
                raise ConflictError("GitHub target, validation, or conflict error (422)")
            return original(endpoint, body=body, allow_missing=allow_missing)
        result = remote.bootstrap_remote_build_branch(CAS, create=True, api=racing)
        self.assertTrue(result["remote_ref_created_or_verified"])
        self.assertEqual(self.api.refs[BUILD_BRANCH], CAS)
        self.assertEqual(self.api.refs[PINNED_SIGNAL_SPRINT_JOB["source_branch"]], SOURCE)

    def test_lost_create_response_reconciles_remote_ref(self):
        original = self.api.__call__
        def lost_response(endpoint, body=None, allow_missing=False):
            value = original(endpoint, body=body, allow_missing=allow_missing)
            if endpoint.endswith("git/refs") and body:
                raise RetryableError("GitHub API timed out; reconcile before retry")
            return value
        result = remote.bootstrap_remote_build_branch(CAS, create=True, api=lost_response)
        self.assertTrue(result["remote_ref_created_or_verified"])
        self.assertEqual(self.api.refs[BUILD_BRANCH], CAS)

    def test_concurrent_different_create_conflict_never_overwrites(self):
        original = self.api.__call__
        def racing(endpoint, body=None, allow_missing=False):
            if endpoint.endswith("git/refs") and body:
                self.api.refs[BUILD_BRANCH] = OTHER
                raise ConflictError("GitHub target, validation, or conflict error (422)")
            return original(endpoint, body=body, allow_missing=allow_missing)
        with self.assertRaises(ConflictError):
            remote.bootstrap_remote_build_branch(CAS, create=True, api=racing)
        self.assertEqual(self.api.refs[BUILD_BRANCH], OTHER)
        self.assertEqual(self.api.refs[PINNED_SIGNAL_SPRINT_JOB["source_branch"]], SOURCE)

    def test_existing_different_remote_head_is_conflict(self):
        self.api.refs[BUILD_BRANCH] = OTHER
        with self.assertRaisesRegex(ConflictError, "no overwrite"):
            self.run_gate(create=True)
        self.assertEqual(self.api.refs[BUILD_BRANCH], OTHER)

    def test_wrong_cas_parent_is_conflict(self):
        self.api.parents = [{"sha": OTHER}]
        with self.assertRaisesRegex(ConflictError, "sole parent"):
            self.run_gate(create=True)

    def test_extra_cas_file_is_conflict(self):
        self.api.files.append({"filename": "products/signal-sprint/main.py", "status": "modified"})
        with self.assertRaisesRegex(ConflictError, "only approved Identity"):
            self.run_gate(create=True)

    def test_wrong_reviewed_identity_is_conflict(self):
        self.api.approved["store_id"] = "9PFAKE"
        with self.assertRaisesRegex(ConflictError, "reviewed Identity"):
            self.run_gate(create=True)

    def test_source_ref_moved_is_conflict(self):
        self.api.refs[PINNED_SIGNAL_SPRINT_JOB["source_branch"]] = CAS
        with self.assertRaisesRegex(ConflictError, "source branch moved"):
            self.run_gate(create=True)

    def test_cas_ref_moved_during_verification_is_conflict(self):
        self.api.mutate_after = 4
        with self.assertRaisesRegex(ConflictError, "remote refs moved"):
            self.run_gate(create=True)
        self.assertNotIn(BUILD_BRANCH, self.api.refs)

    def test_missing_cas_ref_is_conflict(self):
        del self.api.refs[CAS_BRANCH]
        with self.assertRaisesRegex(ConflictError, "CAS branch missing"):
            self.run_gate(create=True)

    def test_invalid_provenance_timestamp_is_conflict(self):
        self.api.approved["provided_at"] = "tomorrow"
        with self.assertRaisesRegex(ConflictError, "provided_at"):
            self.run_gate(create=True)

    def test_impossible_calendar_provenance_rejected_without_write(self):
        self.api.approved["provided_at"] = "2026-02-30T12:00:00Z"
        with self.assertRaisesRegex(ConflictError, "calendar"):
            self.run_gate(create=True)
        self.assertNotIn(BUILD_BRANCH, self.api.refs)

    def test_remote_branch_move_after_creation_is_conflict(self):
        original = self.api.__call__
        def moving(endpoint, body=None, allow_missing=False):
            result = original(endpoint, body=body, allow_missing=allow_missing)
            if body and endpoint.endswith("git/refs"):
                self.api.refs[BUILD_BRANCH] = OTHER
            return result
        with self.assertRaisesRegex(ConflictError, "branch moved"):
            remote.bootstrap_remote_build_branch(CAS, create=True, api=moving)

    def test_github_line_wrapped_base64_accepted(self):
        self.api.linewrap = True
        self.assertEqual(self.run_gate()["status"], "GDK_REMOTE_BUILD_BRANCH_CHECK_ONLY")

    def test_invalid_base64_rejected_without_write(self):
        self.api.bad_base64 = True
        with self.assertRaisesRegex(ConflictError, "base64 invalid"):
            self.run_gate(create=True)
        self.assertNotIn(BUILD_BRANCH, self.api.refs)

    def test_placeholder_cas_rejected_without_api(self):
        with self.assertRaisesRegex(ConflictError, "actual non-source"):
            remote.bootstrap_remote_build_branch(SOURCE, api=self.api)
        self.assertFalse(self.api.calls)


if __name__ == "__main__":
    unittest.main()
