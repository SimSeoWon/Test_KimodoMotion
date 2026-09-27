import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

import server  # noqa: E402


class PreviewVariantTest(unittest.TestCase):
    def test_builds_and_caches_character_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generation = root / "generation-1"
            generation.mkdir()
            (generation / "meta.json").write_text(json.dumps({"id": "generation-1"}), encoding="utf-8")

            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                output = Path(command[command.index("--output") + 1])
                output.write_bytes(b"glb")
                return subprocess.CompletedProcess(command, 0, "ok", "")

            models = [{"id": "capsule", "label": "Capsule", "bind": None}]
            with patch.object(server, "GENERATIONS_DIR", root), \
                    patch.object(server, "list_mixamo_models", return_value=models), \
                    patch.object(server.subprocess, "run", side_effect=fake_run):
                first = server.ensure_preview_variant("generation-1", "capsule")
                second = server.ensure_preview_variant("generation-1", "capsule")

            self.assertEqual(first, second)
            self.assertEqual(b"glb", first.read_bytes())
            self.assertEqual(1, len(calls))
            self.assertEqual("none", calls[0][calls[0].index("--mixamo-bind") + 1])

    def test_rejects_unknown_generation_or_character(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = [{"id": "capsule", "label": "Capsule", "bind": None}]
            with patch.object(server, "GENERATIONS_DIR", root), \
                    patch.object(server, "list_mixamo_models", return_value=models):
                with self.assertRaises(ValueError):
                    server.ensure_preview_variant("../outside", "capsule")
                with self.assertRaises(ValueError):
                    server.ensure_preview_variant("missing", "unknown")


if __name__ == "__main__":
    unittest.main()
