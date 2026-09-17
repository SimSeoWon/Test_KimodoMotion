import sys
import time
import unittest
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

from pose_agent import POSE_RESULT_SCHEMA, PoseAgentDaemon, apply_pose_recipe  # noqa: E402


class PoseAgentDaemonTest(unittest.TestCase):
    def test_horse_stance_recipe_spreads_feet_and_limits_pelvis_drop(self):
        identity = [0, 0, 0, 1]
        snapshot = {
            "pelvis": {"position": [0, 0.75, 0], "rest_position": [0, 1, 0], "rotation_xyzw": identity},
            "left_knee": {"position": [0.2, 0.4, 0], "rest_position": [0.05, 0.55, 0]},
            "right_knee": {"position": [-0.2, 0.4, 0], "rest_position": [-0.05, 0.55, 0]},
            "left_foot": {"position": [0.1, 0.1, 0], "rest_position": [0.1, 0.1, 0], "rotation_xyzw": identity, "rest_rotation_xyzw": identity},
            "right_foot": {"position": [-0.1, 0.1, 0], "rest_position": [-0.1, 0.1, 0], "rotation_xyzw": identity, "rest_rotation_xyzw": identity},
            "left_toe": {"position": [0.1, 0, 0.2], "rest_position": [0.1, 0, 0.2], "rotation_xyzw": identity},
            "right_toe": {"position": [-0.1, 0, 0.2], "rest_position": [-0.1, 0, 0.2], "rotation_xyzw": identity},
        }
        result = apply_pose_recipe("마보 자세를 취해", {"name": "", "summary": "", "controls": {
            "pelvis": {"position": [0, 0.2, 0]},
            "left_knee": {"position": [1, 0.2, 0]},
        }}, snapshot)
        controls = result["controls"]
        self.assertGreater(controls["pelvis"]["position"][1], 0.81)
        self.assertLess(controls["pelvis"]["position"][1], 0.83)
        self.assertGreater(controls["left_foot"]["position"][0], 0.3)
        self.assertLess(controls["right_foot"]["position"][0], -0.3)
        self.assertEqual(0, controls["left_toe"]["position"][1])
        self.assertAlmostEqual(controls["left_foot"]["position"][0], controls["left_toe"]["position"][0])
        self.assertNotIn("left_knee", controls)
        self.assertNotIn("right_knee", controls)

    def test_knee_output_is_position_only(self):
        knee = POSE_RESULT_SCHEMA["properties"]["controls"]["properties"]["left_knee"]
        self.assertEqual("#/$defs/position_only", knee["$ref"])
        definition = POSE_RESULT_SCHEMA["$defs"]["position_only"]
        self.assertIn("position", definition["properties"])
        self.assertNotIn("rotation_xyzw", definition["properties"])

    def test_job_completes_with_validated_pose_and_revision(self):
        daemon = PoseAgentDaemon(lambda instruction, pose, snapshot: {
            "name": "손 들기",
            "summary": instruction,
            "controls": {"right_hand": {"position": [0.4, 1.8, 0.1], "space": "world", "weight": 1}},
        })
        submitted = daemon.submit("오른손을 들어", {
            "schema_version": 1, "id": "live", "name": "현재 포즈", "controls": {},
        }, {"right_hand": {"position": [0.4, 1.0, 0.1]}})
        self.assertIn(submitted["status"], ("queued", "running", "complete"))
        for _ in range(100):
            state = daemon.state()
            if state["status"] == "complete":
                break
            time.sleep(0.005)
        self.assertEqual("complete", state["status"])
        self.assertEqual([0.4, 1.8, 0.1], state["pose"]["controls"]["right_hand"]["position"])
        self.assertEqual(1, state["pose"]["revision"])
        self.assertEqual("오른손을 들어", state["pose"]["edits"][0]["instruction"])
        self.assertEqual(["right_hand"], state["pose"]["edits"][0]["changed_controls"])
        self.assertGreaterEqual(state["revision"], 3)

    def test_runner_failure_is_reported(self):
        def fail(*_):
            raise RuntimeError("agent unavailable")

        daemon = PoseAgentDaemon(fail)
        daemon.submit("명령", {
            "schema_version": 1, "id": "live", "name": "현재 포즈", "controls": {},
        }, {"pelvis": {"position": [0, 1, 0]}})
        for _ in range(100):
            state = daemon.state()
            if state["status"] == "failed":
                break
            time.sleep(0.005)
        self.assertEqual("failed", state["status"])
        self.assertIn("agent unavailable", state["error"])


if __name__ == "__main__":
    unittest.main()
