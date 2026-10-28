import json
from pathlib import Path
import tempfile
import unittest

import provisioner


class EntrypointTests(unittest.TestCase):
    def test_new_pipeline_is_the_public_entrypoint(self):
        self.assertTrue(callable(provisioner.main))
        self.assertTrue(hasattr(provisioner, "Provisioner"))

    def test_cli_startup_hold_has_complete_machine_readable_result(self):
        """A missing/invalid job must not produce a partial result JSON."""
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "result-v1.0.schema.json"
        required = set(json.loads(schema_path.read_text(encoding="utf-8"))["required"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in (("missing", None), ("invalid", '{"request_id":"a","request_id":"b"}')):
                with self.subTest(name=name):
                    input_path = root / (name + ".json")
                    output_path = root / (name + "-result.json")
                    if payload is not None:
                        input_path.write_text(payload, encoding="utf-8")
                    code = provisioner.main(["--input", str(input_path), "--output", str(output_path),
                                             "--state-dir", str(root / "state"),
                                             "--work-dir", str(root / "work")])
                    self.assertEqual(code, 2)
                    result = json.loads(output_path.read_text(encoding="utf-8"))
                    self.assertTrue(required.issubset(result), required - set(result))
                    self.assertEqual(result["status"], "HOLD")
                    self.assertEqual(result["package"]["status"], "NOT_BUILT")
                    self.assertEqual(result["official_identity"]["status"], "UNVERIFIED")
                    self.assertEqual(result["github_return"]["status"], "NOT_APPLIED")
                    self.assertIsNone(result["windows_all_auto_record"])
                    self.assertIsNone(result["source_sha"])
                    self.assertFalse(result["idempotent_replay"])
                    self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
