import math
import unittest

from webui import pose_anatomy as pa
from webui import pose_ops as po

HORSE_STANCE = [
    {"joint": "left_foot", "mode": "add", "translate_m": {"left": 0.2}, "turn_out_deg": 20},
    {"joint": "right_foot", "mode": "add", "translate_m": {"right": 0.2}, "turn_out_deg": 20},
    {"joint": "pelvis", "mode": "add", "translate_m": {"down": 0.2, "back": 0.1}},
]


def errors(state):
    return [issue for issue in pa.validate(state)[0] if issue["severity"] == "error"]


def knee_and_toe_heading(state, side):
    _, p = pa.forward_kinematics(state)
    hip, knee, ankle, toe = p[f"{side}Leg"], p[f"{side}Shin"], p[f"{side}Foot"], p[f"{side}ToeBase"]
    axis = pa.unit(pa.sub(ankle, hip))
    bend = pa.sub(pa.sub(knee, hip), pa.scale(axis, pa.dot(pa.sub(knee, hip), axis)))
    return (math.degrees(math.atan2(bend[0], bend[2])),
            math.degrees(math.atan2(toe[0] - ankle[0], toe[2] - ankle[2])))


class ApplyOperationsTest(unittest.TestCase):
    def setUp(self):
        self.rest = pa.rest_state()

    def test_horse_stance_is_valid_planted_and_knees_track_toes(self):
        state, unreached = po.apply_operations(self.rest, HORSE_STANCE, ["left_foot", "right_foot"])
        self.assertEqual([], unreached)
        self.assertEqual([], errors(state))
        _, p = pa.forward_kinematics(state)
        self.assertAlmostEqual(0.788, p["Hips"][1], places=3)
        self.assertAlmostEqual(0.60, abs(p["LeftFoot"][0] - p["RightFoot"][0]), places=2)
        for side in ("Left", "Right"):
            self.assertLess(abs(p[f"{side}ToeBase"][1]), 0.01)  # toe stays on the ground
            knee, toe = knee_and_toe_heading(state, side)
            self.assertAlmostEqual(toe, knee, delta=5.0)
            self.assertAlmostEqual(20.0, abs(toe), delta=0.5)
        angles = pa.measure(state)
        self.assertGreater(angles["left_knee"]["flexion"], 50)
        self.assertGreater(angles["left_hip"]["external_rotation"], 5)

    def test_planted_feet_do_not_move_when_the_body_drops(self):
        _, before = pa.forward_kinematics(self.rest)
        state, _ = po.apply_operations(self.rest, [{"joint": "pelvis", "mode": "add", "translate_m": {"down": 0.15}}],
                                       ["left_foot", "right_foot"])
        _, after = pa.forward_kinematics(state)
        for joint in ("LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase"):
            self.assertLess(pa.norm(pa.sub(before[joint], after[joint])), 1e-3)

    def test_only_the_final_pose_is_validated_so_order_cannot_deadlock(self):
        # An intermediate step is outside the knee's range and the foot is moved
        # before the body; the finished pose is valid, so it must be accepted.
        operations = [
            {"joint": "left_knee", "mode": "set", "angles": {"flexion": 170}},
            {"joint": "left_foot", "mode": "add", "translate_m": {"forward": 0.15}},
            {"joint": "pelvis", "mode": "add", "translate_m": {"down": 0.1}},
            {"joint": "left_knee", "mode": "set", "angles": {"flexion": 30}},
        ]
        state, unreached = po.apply_operations(self.rest, operations, ["right_foot"])
        self.assertEqual([], unreached)
        self.assertEqual([], errors(state))

    def test_add_mode_is_relative_and_set_mode_is_absolute(self):
        bent = po.apply_operations(self.rest, [{"joint": "left_hip", "mode": "set", "angles": {"flexion": 30}}], [])[0]
        more = po.apply_operations(bent, [{"joint": "left_hip", "mode": "add", "angles": {"flexion": 20}}], [])[0]
        self.assertAlmostEqual(50.0, pa.measure(more)["left_hip"]["flexion"], delta=0.5)
        reset = po.apply_operations(more, [{"joint": "left_hip", "mode": "set", "angles": {"abduction": 10}}], [])[0]
        self.assertNotIn("flexion", pa.measure(reset)["left_hip"])

    def test_too_deep_squat_fails_on_ankle_or_reach_with_numbers(self):
        state, unreached = po.apply_operations(
            self.rest, [{"joint": "pelvis", "mode": "add", "translate_m": {"down": 0.6}}], ["left_foot", "right_foot"])
        found = {issue["code"] for issue in errors(state)}
        self.assertTrue(found & {"swing_limit", "flexion_limit"} or unreached, found)

    def test_bad_operations_are_rejected_with_a_reason(self):
        for op in ({"joint": "left_knee", "mode": "set", "angles": {"abduction": 10}},
                   {"joint": "left_hip", "mode": "set", "angles": {"twirl": 10}},
                   {"joint": "pelvis", "mode": "add", "translate_m": {"down": 3}}):
            with self.subTest(op=op), self.assertRaises(po.OperationError):
                po.apply_operations(self.rest, [op], [])


class ExportAndRunTest(unittest.TestCase):
    def test_controls_cover_touched_chains_with_the_editor_modes(self):
        state, _ = po.apply_operations(pa.rest_state(), HORSE_STANCE, ["left_foot", "right_foot"])
        controls = po.controls_from_state(state, po.touched_controls(HORSE_STANCE, ["left_foot", "right_foot"]))
        self.assertEqual({"pelvis", "left_hip", "left_knee", "left_foot", "left_toe",
                          "right_hip", "right_knee", "right_foot", "right_toe"}, set(controls))
        self.assertEqual({"space", "weight", "position"}, set(controls["left_knee"]))
        self.assertEqual({"space", "weight", "rotation_xyzw"}, set(controls["left_hip"]))
        self.assertEqual({"space", "weight", "position", "rotation_xyzw"}, set(controls["left_foot"]))
        self.assertAlmostEqual(0.788, controls["pelvis"]["position"][1], places=3)

    def test_run_retries_once_with_the_violations_then_succeeds(self):
        prompts = []
        replies = [
            {"name": "킥", "summary": "차기", "operations": [{"joint": "left_hip", "mode": "set",
                                                            "angles": {"extension": 60}}], "keep_planted": []},
            {"name": "킥", "summary": "차기", "operations": [{"joint": "left_hip", "mode": "set",
                                                            "angles": {"extension": 20}}], "keep_planted": []},
        ]

        def ask(prompt):
            prompts.append(prompt)
            return replies[len(prompts) - 1]

        result = po.run("왼다리를 뒤로 차", pa.bone_state_from_state(pa.rest_state()), {}, ask)
        self.assertEqual(2, result["rounds"])
        self.assertIn("swing_limit", prompts[1])
        self.assertIn("측정:", result["summary"])
        self.assertIn("left_hip", result["controls"])
        self.assertAlmostEqual(20.0, pa.measure(pa.state_from_bone_state(result["bone_state"]))["left_hip"]["extension"],
                               delta=0.5)

    def test_run_gives_up_after_two_invalid_rounds(self):
        reply = {"name": "x", "summary": "x", "keep_planted": [],
                 "operations": [{"joint": "left_knee", "mode": "set", "angles": {"flexion": 175}}]}
        with self.assertRaisesRegex(po.OperationError, "left_knee"):
            po.run("무릎을 끝까지", pa.bone_state_from_state(pa.rest_state()), {}, lambda prompt: reply)

    def test_prompt_is_small_and_carries_angles_not_quaternions(self):
        prompt = po.build_prompt("자세를 낮춰", pa.rest_state(), {})
        self.assertLess(len(prompt), 4500)
        self.assertIn("Current joint angles", prompt)
        self.assertNotIn("rotation_xyzw", prompt)


if __name__ == "__main__":
    unittest.main()
