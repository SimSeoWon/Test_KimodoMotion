import math
import sys
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

from keypose import (  # noqa: E402
    CONTROLS,
    KeyposeValidationError,
    PoseAsset,
    PoseConstraint,
    get_keypose_schema,
    placements_to_keypose_document,
    validate_keypose_document,
    validate_pose_asset,
    validate_pose_placement,
)


class KeyposeContractTest(unittest.TestCase):
    def test_pose_asset_is_frame_free(self):
        pose = validate_pose_asset({
            "schema_version": 1,
            "id": "horse-stance",
            "name": "낮은 마보 자세",
            "frame": 24,
            "controls": {"pelvis": {"position": [0, 0.8, 0]}},
        })
        self.assertNotIn("frame", pose)
        self.assertEqual("horse-stance", pose["id"])

    def test_pose_dataclasses_express_asset_and_constraints(self):
        constraint = PoseConstraint(position=(0.0, 1.0, 0.0))
        pose = PoseAsset(id="ready", name="준비", controls={"pelvis": constraint})
        self.assertEqual("ready", pose.id)
        self.assertFalse(hasattr(pose, "frame"))

    def test_placement_keeps_asset_identity_and_builds_runtime_document(self):
        placement = validate_pose_placement({
            "frame": 12,
            "pose_id": "ready",
            "pose_name": "준비",
            "controls": {"pelvis": {"position": [0, 1, 0]}},
        }, frame_count=30)
        self.assertEqual("ready", placement["pose_id"])
        document = placements_to_keypose_document([placement], frame_count=30)
        self.assertEqual(12, document["keyposes"][0]["frame"])
        self.assertEqual("준비", document["keyposes"][0]["label"])

    def test_basic_control_set_has_unique_ids_and_joint_indices(self):
        self.assertEqual(17, len(CONTROLS))
        self.assertEqual(17, len({item["id"] for item in CONTROLS}))
        self.assertEqual(17, len({item["joint_index"] for item in CONTROLS}))
        self.assertEqual("LeftShin", next(item for item in CONTROLS if item["id"] == "left_knee")["soma_joint"])
        self.assertEqual("RightShin", next(item for item in CONTROLS if item["id"] == "right_knee")["soma_joint"])
        self.assertEqual("LeftToeBase", next(item for item in CONTROLS if item["id"] == "left_toe")["soma_joint"])
        self.assertEqual("RightToeBase", next(item for item in CONTROLS if item["id"] == "right_toe")["soma_joint"])
        pelvis = next(item for item in CONTROLS if item["id"] == "pelvis")
        self.assertEqual("Hips", pelvis["soma_joint"])
        self.assertEqual("root", pelvis["role"])
        for control_id in ("chest", "head", "left_shoulder", "right_shoulder"):
            self.assertEqual(["rotate"], next(item for item in CONTROLS if item["id"] == control_id)["modes"])
        for control_id in ("left_hip", "right_hip"):
            self.assertEqual(["rotate"], next(item for item in CONTROLS if item["id"] == control_id)["modes"])
        for control_id in ("left_elbow", "right_elbow", "left_knee", "right_knee"):
            self.assertEqual(["move"], next(item for item in CONTROLS if item["id"] == control_id)["modes"])

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
