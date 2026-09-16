import math
import sys
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

from keypose import (  # noqa: E402
    CONTROLS,
    KeyposeValidationError,
    get_keypose_schema,
    validate_keypose_document,
)


class KeyposeContractTest(unittest.TestCase):
    def test_basic_control_set_has_unique_ids_and_joint_indices(self):
        self.assertEqual(13, len(CONTROLS))
        self.assertEqual(13, len({item["id"] for item in CONTROLS}))
        self.assertEqual(13, len({item["joint_index"] for item in CONTROLS}))
        self.assertEqual("LeftShin", next(item for item in CONTROLS if item["id"] == "left_knee")["soma_joint"])
        self.assertEqual("RightShin", next(item for item in CONTROLS if item["id"] == "right_knee")["soma_joint"])

    def test_schema_is_detached_from_shared_definition(self):
        schema = get_keypose_schema()
        schema["controls"][0]["label"] = "changed"
        self.assertNotEqual("changed", CONTROLS[0]["label"])

    def test_document_is_sorted_and_quaternion_is_normalized(self):
        result = validate_keypose_document({
            "schema_version": 1,
            "keyposes": [
                {"frame": 20, "controls": {"right_hand": {"rotation_xyzw": [0, 0, 0, 2]}}},
                {"frame": 5, "label": "start", "controls": {"pelvis": {"position": [0, 1, 0]}}},
            ],
        }, frame_count=30)
        self.assertEqual([5, 20], [item["frame"] for item in result["keyposes"]])
        quat = result["keyposes"][1]["controls"]["right_hand"]["rotation_xyzw"]
        self.assertTrue(math.isclose(1.0, math.sqrt(sum(value * value for value in quat))))

    def test_unknown_control_is_rejected(self):
        with self.assertRaisesRegex(KeyposeValidationError, "unknown control"):
            validate_keypose_document({
                "schema_version": 1,
                "keyposes": [{"frame": 0, "controls": {"tail": {"position": [0, 0, 0]}}}],
            })

    def test_duplicate_and_out_of_range_frames_are_rejected(self):
        with self.assertRaisesRegex(KeyposeValidationError, "duplicate"):
            validate_keypose_document({
                "schema_version": 1,
                "keyposes": [{"frame": 2, "controls": {}}, {"frame": 2, "controls": {}}],
            })
        with self.assertRaisesRegex(KeyposeValidationError, "frame_count"):
            validate_keypose_document({
                "schema_version": 1,
                "keyposes": [{"frame": 10, "controls": {}}],
            }, frame_count=10)

    def test_invalid_frame_count_is_rejected(self):
        with self.assertRaisesRegex(KeyposeValidationError, "positive integer"):
            validate_keypose_document({"schema_version": 1, "keyposes": []}, frame_count="60")


if __name__ == "__main__":
    unittest.main()
