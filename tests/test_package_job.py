"""Fail-closed GAME package-intake regression tests (no network/Store access)."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from package_job import validate_job

def sample():
    return {
        "schema_version": "1.0",
        "request_id": "game-20261026-001",
        "product_type": "GAME",
        "source_factory": "AI-Game-Factory",
        "source_repository": "shihuiarenjinba-png/AI-Game-Factory",
        "source_branch": "codex/factory-autoloop-20261026",
        "source_sha": "a" * 40,
        "slug": "arcade-puzzle-game",
        "display_name": "Arcade Puzzle Game",
        "target_owner": "shihuiarenjinba-png",
        "dry_run": True,
        "requested_actions": [
            "BUILD_WINDOWS", "INSPECT_PACKAGE",
            "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN",
        ],
    }

class PackageJobTests(unittest.TestCase):
    def test_receipt_is_read_only_and_routed_to_game(self):
        result = validate_job(sample())
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertEqual(result["product_type"], "GAME")
        self.assertEqual(result["package"]["status"], "NOT_BUILT")
        self.assertIsNone(result["official_identity"]["store_id"])
        self.assertIsNone(result["github_return"]["commit_sha"])
        self.assertEqual(result["github_return"]["repository"], "shihuiarenjinba-png/AI-Game-Factory")
        self.assertEqual(result["github_return"]["path"], "products/arcade-puzzle-game/store/approved-identity.json")

    def test_determinism_and_source_sha_key(self):
        a = validate_job(sample())
        self.assertEqual(a, validate_job(sample()))
        b = sample()
        b["source_sha"] = "b" * 40
        self.assertNotEqual(a["idempotency_key"], validate_job(b)["idempotency_key"])

    def test_idempotency_key_binds_every_validated_job_field(self):
        original = sample()
        baseline = validate_job(original)["idempotency_key"]
        # Same request_id/source SHA/slug is NOT enough to identify a job.
        for field, replacement in (
            ("display_name", "Another Game Title"),
            ("request_id", "game-20261026-002"),
            ("slug", "another-puzzle-game"),
            ("source_sha", "b" * 40),
        ):
            with self.subTest(field=field):
                changed = sample()
                changed[field] = replacement
                self.assertNotEqual(
                    baseline, validate_job(changed)["idempotency_key"])
        # Action ordering does not change the requested operation set.
        reordered = sample()
        reordered["requested_actions"] = list(reversed(reordered["requested_actions"]))
        self.assertEqual(
            baseline, validate_job(reordered)["idempotency_key"])

    def test_cross_lane_and_invalid_input_fail_closed(self):
        changes = [
            ("schema_version", 1),
            ("product_type", "APP"), ("product_type", "GAME_3D"),
            ("source_factory", "AI-App-Factory"),
            ("source_repository", "shihuiarenjinba-png/AI-App-Factory"),
            ("source_branch", "main"), ("source_branch", "codex/other"),
            ("target_owner", "some-other-owner"),
            ("dry_run", False),
            ("request_id", "../secret"),
            ("slug", "../../escape"), ("slug", "UPPER"),
            ("source_sha", "0" * 40), ("source_sha", "a" * 39),
            ("source_sha", "A" * 40),
            ("display_name", ""), ("display_name", "bad\ncommand"),
            ("requested_actions", ["BUILD_WINDOWS"]),
        ]
        for field, invalid in changes:
            with self.subTest(field=field, invalid=invalid):
                record = sample()
                record[field] = invalid
                with self.assertRaises(ValueError):
                    validate_job(record)

    def test_display_name_rejects_invisible_bidi_and_blank_titles(self):
        # The Factory rejects Unicode Cc/Cf characters; local intake must
        # enforce the same policy even for hand-crafted or stale JSON jobs.
        for title in (" ", "   ", "Puzzle\u202eexe", "Puzzle\u200bGame", "Puzzle\u2066Game", "Puzzle\u007fGame"):
            with self.subTest(title=repr(title)):
                job = sample()
                job["display_name"] = title
                with self.assertRaisesRegex(ValueError, "display_name"):
                    validate_job(job)
        for title in ("Arcade Puzzle Game", "パズルゲーム", "Puzzle: 2D"):
            with self.subTest(title=title):
                job = sample()
                job["display_name"] = title
                self.assertEqual(validate_job(job)["status"], "DRY_RUN")

    def test_unknown_missing_and_nonobject(self):
        record = sample()
        record["execute"] = True
        with self.assertRaises(ValueError):
            validate_job(record)
        record = sample()
        del record["slug"]
        with self.assertRaises(ValueError):
            validate_job(record)
        with self.assertRaises(ValueError):
            validate_job([])

    def test_cli_no_external_side_effects(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "job.json"
            target = Path(td) / "receipt.json"
            source.write_text(json.dumps(sample()), encoding="utf-8")
            run = subprocess.run(
                [sys.executable, "package_job.py", "--input", str(source), "--output", str(target)],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(target.read_text())["status"], "DRY_RUN")
            self.assertEqual({p.name for p in Path(td).iterdir()}, {"job.json", "receipt.json"})

    def test_cli_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "job.json"
            data = json.dumps(sample())
            source.write_text(data[:-1] + ', "dry_run": false}', encoding="utf-8")
            run = subprocess.run(
                [sys.executable, "package_job.py", "--input", str(source)],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 2)
            self.assertIn("PACKAGE_INTAKE_HOLD", run.stderr)

    def test_cli_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "job.json"
            target = Path(td) / "protected.json"
            link = Path(td) / "receipt.json"
            source.write_text(json.dumps(sample()), encoding="utf-8")
            target.write_text("protected", encoding="utf-8")
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unsupported")
            run = subprocess.run(
                [sys.executable, "package_job.py", "--input", str(source), "--output", str(link)],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(target.read_text(), "protected")

if __name__ == "__main__":
    unittest.main()
