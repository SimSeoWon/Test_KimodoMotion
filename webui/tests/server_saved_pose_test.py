import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

import server  # noqa: E402


class SavedPoseStorageTest(unittest.TestCase):
    def test_saved_pose_keeps_revision_and_edit_history(self):
        edit = {
            "revision": 1,
            "instruction": "오른손만 들어",
            "summary": "오른손을 올렸습니다.",
            "changed_controls": ["right_hand"],
            "before": {},
            "after": {"right_hand": {"position": [0.2, 1.4, 0.0]}},
            "created_at": "2026-09-18T00:00:00+00:00",
            "actor": "llm",
        }
        pose = {
            "schema_version": 1,
            "id": "working-pose",
            "name": "작업 중 포즈",
            "controls": {"right_hand": {"position": [0.2, 1.4, 0.0]}},
            "revision": 1,
            "edits": [edit],
        }
        with tempfile.TemporaryDirectory() as directory:
            pose_file = Path(directory) / "poses.json"
            pose_file.write_text(json.dumps([pose], ensure_ascii=False), encoding="utf-8")
            with patch.object(server, "KEYPOSE_PRESETS_FILE", pose_file):
                loaded = server.load_saved_poses()

        self.assertEqual("working-pose", loaded[0]["id"])
        self.assertEqual(1, loaded[0]["revision"])
        self.assertEqual("오른손만 들어", loaded[0]["edits"][0]["instruction"])

    def test_legacy_pose_without_history_still_loads(self):
        legacy = {"name": "준비", "controls": {"pelvis": {"position": [0, 1, 0]}}}
        with tempfile.TemporaryDirectory() as directory:
            pose_file = Path(directory) / "poses.json"
            pose_file.write_text(json.dumps([legacy], ensure_ascii=False), encoding="utf-8")
            with patch.object(server, "KEYPOSE_PRESETS_FILE", pose_file):
                loaded = server.load_saved_poses()

        self.assertEqual(0, loaded[0]["revision"])
        self.assertEqual([], loaded[0]["edits"])


if __name__ == "__main__":
    unittest.main()
