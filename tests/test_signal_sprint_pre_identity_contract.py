"""Pinned Signal Sprint contract tests; synthetic PE is never a release artifact."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from package_identity_provisioner import ProductConfig, Provisioner

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST_ID = "game-signal-sprint-" + SOURCE_SHA
BRANCH = "codex/game-signal-sprint-undo-20261027"


def job(dry_run):
    cfg = ProductConfig.load(ROOT / "config.json")
    return dict(schema_version="1.0", request_id=REQUEST_ID, product_type="GAME",
                source_factory="AI-Game-Factory",
                source_repository="shihuiarenjinba-png/AI-Game-Factory",
                source_branch=BRANCH, source_sha=SOURCE_SHA, slug="signal-sprint",
                display_name="Signal Sprint", target_owner=cfg.target_owner,
                dry_run=dry_run, requested_actions=["BUILD_WINDOWS", "INSPECT_PACKAGE",
                    "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN"])


class FakeSource:
    calls = 0
    def acquire(self, _job, path):
        self.calls += 1
        path.mkdir(parents=True, exist_ok=True)
        return path


class FakeBuilder:
    calls = 0
    path = None
    def build(self, _job, _source, output, _config):
        self.calls += 1
        output.mkdir(parents=True, exist_ok=True)
        self.path = output / "synthetic-test-only.exe"
        pe = bytearray(100_100)
        pe[:2] = b"MZ"
        pe[0x3c:0x40] = (0x80).to_bytes(4, "little")
        pe[0x80:0x84] = b"PE" + bytes(2)
        self.path.write_bytes(pe)
        return self.path


class NoGithub:
    calls = 0
    def return_identity(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("No official Identity: CAS must never run")


class SignalSprintContractTests(unittest.TestCase):
    def test_dry_run_replay_and_source_sha_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, build, gh = FakeSource(), FakeBuilder(), NoGithub()
            p = Provisioner(ProductConfig.load(ROOT / "config.json"),
                            Path(tmp) / "state", Path(tmp) / "work",
                            source=src, builder=build, github=gh)
            first = p.run(job(True))
            self.assertEqual(first["status"], "DRY_RUN")
            self.assertEqual((first["request_id"], first["source_sha"], first["source_branch"]),
                             (REQUEST_ID, SOURCE_SHA, BRANCH))
            self.assertEqual(first["github_return"]["status"], "NOT_APPLIED")
            self.assertIsNone(first["windows_all_auto_record"])
            self.assertTrue(p.run(job(True))["idempotent_replay"])
            changed = job(True)
            changed["source_sha"] = "a" * 40
            conflict = p.run(changed)
            self.assertEqual((conflict["status"], conflict["next_stage"]),
                             ("CONFLICT", "RECONCILE_CONFLICT"))
            self.assertEqual((src.calls, build.calls, gh.calls), (0, 0, 0))

    def test_identity_retry_requires_resume_and_preserves_pinned_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, build, gh = FakeSource(), FakeBuilder(), NoGithub()
            p = Provisioner(ProductConfig.load(ROOT / "config.json"),
                            root / "state", root / "work",
                            source=src, builder=build, github=gh)
            held = p.run(job(False))
            self.assertEqual(held["status"], "HOLD")
            rejected = p.run(job(False), apply=True)
            self.assertEqual((rejected["status"], rejected["next_stage"]),
                             ("CONFLICT", "RECONCILE_CONFLICT"))
            self.assertIn("--resume-result", rejected["errors"][0])
            self.assertEqual(p.ledger.read(REQUEST_ID)["response"]["package"]["sha256"],
                             held["package"]["sha256"])
            self.assertEqual((src.calls, build.calls, gh.calls), (1, 1, 0))

    def test_tampered_resume_hash_cannot_replace_original_exe_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, build, gh = FakeSource(), FakeBuilder(), NoGithub()
            p = Provisioner(ProductConfig.load(ROOT / "config.json"),
                            root / "state", root / "work",
                            source=src, builder=build, github=gh)
            held = p.run(job(False))
            self.assertEqual(held["status"], "HOLD")
            with build.path.open("r+b") as handle:
                handle.seek(4096)
                handle.write(b"changed but valid PE")
            tampered = json.loads(json.dumps(held))
            tampered["package"]["sha256"] = hashlib.sha256(build.path.read_bytes()).hexdigest()
            resume_path = root / "tampered-resume-result.json"
            resume_path.write_text(json.dumps(tampered), encoding="utf-8")
            p.resume_result = resume_path
            rejected = p.run(job(False), apply=True)
            self.assertEqual((rejected["status"], rejected["next_stage"]),
                             ("CONFLICT", "RECONCILE_CONFLICT"))
            self.assertIn("previously pinned ledger", rejected["errors"][0])
            self.assertEqual(p.ledger.read(REQUEST_ID)["response"]["package"]["sha256"],
                             held["package"]["sha256"])
            self.assertEqual((src.calls, build.calls, gh.calls), (1, 1, 0))

    def test_live_hold_resume_pins_bytes_without_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, build, gh = FakeSource(), FakeBuilder(), NoGithub()
            cfg = ProductConfig.load(ROOT / "config.json")
            p = Provisioner(cfg, root / "state", root / "work",
                            source=src, builder=build, github=gh)
            held = p.run(job(False))
            self.assertEqual((held["status"], held["next_stage"]),
                             ("HOLD", "OBTAIN_AUTHENTICATED_OFFICIAL_IDENTITY"))
            self.assertEqual(held["package"]["kind"], "exe")
            self.assertEqual(held["package"]["sha256"],
                             hashlib.sha256(build.path.read_bytes()).hexdigest())
            self.assertEqual(held["github_return"]["status"], "NOT_APPLIED")
            self.assertIsNone(held["windows_all_auto_record"])
            result = root / "prior-result.json"
            result.write_text(json.dumps(held), encoding="utf-8")
            resume = Provisioner(cfg, root / "state", root / "work",
                                 source=src, builder=build, github=gh,
                                 resume_result=result)
            again = resume.run(job(False))
            self.assertEqual(again["package"]["sha256"], held["package"]["sha256"])
            self.assertEqual(again["status"], "HOLD")
            self.assertEqual((src.calls, build.calls, gh.calls), (1, 1, 0))
            with build.path.open("r+b") as f:
                f.seek(4096)
                f.write(b"changed")
            conflict = resume.run(job(False))
            self.assertEqual((conflict["status"], conflict["next_stage"]),
                             ("CONFLICT", "RECONCILE_CONFLICT"))
            self.assertEqual((src.calls, build.calls, gh.calls), (1, 1, 0))


    def test_missing_or_invalid_resume_exe_preserves_pinned_ledger(self):
        # A filesystem failure is a conflict with previously pinned evidence,
        # not a fresh HOLD that may overwrite the immutable EXE checkpoint.
        for corruption in ("missing", "truncated"):
            with self.subTest(corruption=corruption):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    src, build, gh = FakeSource(), FakeBuilder(), NoGithub()
                    p = Provisioner(ProductConfig.load(ROOT / "config.json"),
                                    root / "state", root / "work",
                                    source=src, builder=build, github=gh)
                    held = p.run(job(False))
                    self.assertEqual(held["status"], "HOLD")
                    prior = root / "resume-result.json"
                    prior.write_text(json.dumps(held), encoding="utf-8")
                    if corruption == "missing":
                        build.path.unlink()
                    else:
                        build.path.write_bytes(b"truncated PE")
                    p.resume_result = prior
                    rejected = p.run(job(False), apply=True)
                    self.assertEqual((rejected["status"], rejected["next_stage"]),
                                     ("CONFLICT", "RECONCILE_CONFLICT"))
                    self.assertEqual(
                        p.ledger.read(REQUEST_ID)["response"]["package"]["sha256"],
                        held["package"]["sha256"])
                    self.assertEqual((src.calls, build.calls, gh.calls), (1, 1, 0))


if __name__ == "__main__":
    unittest.main()
