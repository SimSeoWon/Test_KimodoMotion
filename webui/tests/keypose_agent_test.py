import tempfile
import sys
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

from keypose import KeyposeValidationError
from keypose_agent import KeyposeStore


class KeyposeAgentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = KeyposeStore(Path(self.temp.name) / "state.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_create_move_and_undo(self):
        self.store.command("create_keypose", {"frame": 12, "label": "reach"})
        result = self.store.command("move_control", {
            "frame": 12, "control": "right_hand", "position": [0.2, 1.1, 0.5],
        })
        self.assertEqual([0.2, 1.1, 0.5], result["document"]["keyposes"][0]["controls"]["right_hand"]["position"])
        undone = self.store.command("undo_pose_edit")
        self.assertEqual({}, undone["document"]["keyposes"][0]["controls"])

    def test_copy_and_reject_unknown_control(self):
        self.store.command("create_keypose", {"frame": 1})
        self.store.command("rotate_control", {"frame": 1, "control": "head", "rotation_xyzw": [0, 0, 0, 1]})
        result = self.store.command("copy_keypose", {"source_frame": 1, "frame": 20})
        self.assertEqual([1, 20], [item["frame"] for item in result["document"]["keyposes"]])
        with self.assertRaises(KeyposeValidationError):
            self.store.command("move_control", {"frame": 1, "control": "tail", "position": [0, 0, 0]})
