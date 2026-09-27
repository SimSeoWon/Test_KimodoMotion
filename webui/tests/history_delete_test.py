import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webui import server


class HistoryDeleteTest(unittest.TestCase):
    def test_deletes_only_requested_generation_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "20260919-120000_test"
            other = root / "20260919-120001_other"
            target.mkdir()
            other.mkdir()
            (target / "meta.json").write_text(json.dumps({"id": target.name}), encoding="utf-8")
            (target / "animation.glb").write_bytes(b"glb")
            (other / "meta.json").write_text(json.dumps({"id": other.name}), encoding="utf-8")
            with patch.object(server, "GENERATIONS_DIR", root):
                self.assertTrue(server.delete_history_item(target.name))
            self.assertFalse(target.exists())
            self.assertTrue(other.exists())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(server, "GENERATIONS_DIR", Path(directory)):
            with self.assertRaises(ValueError):
                server.delete_history_item("../outside")

    def test_refuses_unrecognized_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "not-a-generation").mkdir()
            with patch.object(server, "GENERATIONS_DIR", root):
                with self.assertRaises(ValueError):
                    server.delete_history_item("not-a-generation")


if __name__ == "__main__":
    unittest.main()
