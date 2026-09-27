import unittest

from webui import pose_anatomy as pa


def codes(issues, severity="error"):
    return {(issue["joint"], issue["code"]) for issue in issues if issue["severity"] == severity}


class AxisConventionTest(unittest.TestCase):
    """Pin every anatomical axis to a physical outcome of forward kinematics."""

    def setUp(self):
        self.rest = pa.rest_state()

    def positions(self, state):
        return pa.forward_kinematics(state)[1]

    def test_rest_t_pose_is_valid_and_reads_as_neutral_legs_and_abducted_arms(self):
        issues, angles = pa.validate(self.rest)
        self.assertEqual(set(), codes(issues))
        self.assertEqual({}, angles["left_hip"])
        self.assertEqual({"flexion": 0.0}, angles["left_knee"])
        self.assertAlmostEqual(90.0, angles["left_shoulder"]["abduction"], delta=0.5)
        self.assertAlmostEqual(90.0, angles["right_shoulder"]["abduction"], delta=0.5)

    def test_knee_flexion_moves_the_ankle_behind_the_knee(self):
        for side, key in (("Left", "left_knee"), ("Right", "right_knee")):
            p = self.positions(pa.set_hinge(self.rest, key, 90))
            self.assertLess(p[f"{side}Foot"][2], p[f"{side}Shin"][2] - 0.3)
            self.assertAlmostEqual(p[f"{side}Foot"][1], p[f"{side}Shin"][1], delta=0.05)
            self.assertAlmostEqual(90.0, pa.measure_hinge(pa.set_hinge(self.rest, key, 90), key)["flexion"], places=6)

    def test_knee_bends_one_way_on_one_axis(self):
        issues, _ = pa.validate(pa.set_hinge(self.rest, "left_knee", -20))
        self.assertIn(("left_knee", "hyperextension"), codes(issues))
        self.assertNotIn(("left_knee", "hyperextension"), codes(pa.validate(pa.set_hinge(self.rest, "left_knee", -4))[0]))
        sideways = dict(self.rest["rot"])
        sideways["LeftShin"] = pa.qaxis_angle((0, 0, 1), 30)
        issues, _ = pa.validate({"root": self.rest["root"], "rot": sideways})
        self.assertIn(("left_knee", "hinge_off_axis"), codes(issues))
        self.assertIn(("left_knee", "flexion_limit"), codes(pa.validate(pa.set_hinge(self.rest, "left_knee", 160))[0]))

    def test_elbow_flexion_brings_the_hand_forward_in_t_pose(self):
        for side, key in (("Left", "left_elbow"), ("Right", "right_elbow")):
            p = self.positions(pa.set_hinge(self.rest, key, 90))
            self.assertGreater(p[f"{side}Hand"][2], p[f"{side}ForeArm"][2] + 0.2)

    def test_hip_flexion_lifts_the_knee_forward(self):
        for side, key in (("Left", "left_hip"), ("Right", "right_hip")):
            state = pa.set_ball(self.rest, key, {"flexion": 90})
            p = self.positions(state)
            self.assertGreater(p[f"{side}Shin"][2], p[f"{side}Leg"][2] + 0.35)
            self.assertAlmostEqual(p[f"{side}Shin"][1], p[f"{side}Leg"][1], delta=0.06)
            self.assertAlmostEqual(90.0, pa.measure(state)[key]["flexion"], delta=0.5)

    def test_hip_abduction_moves_the_leg_outward(self):
        left = self.positions(pa.set_ball(self.rest, "left_hip", {"abduction": 30}))
        right = self.positions(pa.set_ball(self.rest, "right_hip", {"abduction": 30}))
        self.assertGreater(left["LeftFoot"][0], self.positions(self.rest)["LeftFoot"][0] + 0.2)
        self.assertLess(right["RightFoot"][0], self.positions(self.rest)["RightFoot"][0] - 0.2)

    def test_hip_external_rotation_is_toe_out_turnout(self):
        # CLAUDE.md: 팔자 = toes out: left toe X > ankle X, right toe X < ankle X.
        left = self.positions(pa.set_ball(self.rest, "left_hip", {"external_rotation": 30}))
        right = self.positions(pa.set_ball(self.rest, "right_hip", {"external_rotation": 30}))
        self.assertGreater(left["LeftToeBase"][0], left["LeftFoot"][0] + 0.03)
        self.assertLess(right["RightToeBase"][0], right["RightFoot"][0] - 0.03)
        state = pa.set_ball(self.rest, "left_hip", {"external_rotation": 30})
        self.assertAlmostEqual(30.0, pa.measure(state)["left_hip"]["external_rotation"], delta=0.5)

    def test_ankle_dorsiflexion_lifts_the_toe_and_inversion_tilts_the_sole_inward(self):
        up = self.positions(pa.set_ball(self.rest, "left_ankle", {"dorsiflexion": 15}))
        self.assertGreater(up["LeftToeBase"][1], self.positions(self.rest)["LeftToeBase"][1] + 0.02)
        inverted = pa.set_ball(self.rest, "left_ankle", {"inversion": 20})
        world_rot = pa.forward_kinematics(inverted)[0]
        foot_up = pa.qrot(world_rot["LeftFoot"], (0, 1, 0))
        self.assertGreater(foot_up[0], 0.2)  # dorsum faces outward (+X) = sole faces inward

    def test_shoulder_measured_from_chest_and_arm_down_is_neutral(self):
        down = pa.set_ball(self.rest, "left_shoulder", {})
        p = self.positions(down)
        self.assertLess(p["LeftForeArm"][1], p["LeftArm"][1] - 0.25)
        self.assertEqual(set(), codes(pa.validate(down)[0]))
        forward = pa.set_ball(self.rest, "left_shoulder", {"flexion": 90})
        p = self.positions(forward)
        self.assertGreater(p["LeftForeArm"][2], p["LeftArm"][2] + 0.25)
        overhead = pa.set_ball(self.rest, "left_shoulder", {"flexion": 170})
        self.assertEqual(set(), codes(pa.validate(overhead)[0]))
        self.assertIn(("left_shoulder", "swing_limit"),
                      codes(pa.validate(pa.set_ball(self.rest, "left_shoulder", {"extension": 90}))[0]))

    def test_shoulder_external_rotation_turns_a_bent_forearm_outward(self):
        state = pa.set_ball(self.rest, "left_shoulder", {"external_rotation": 60})
        state = pa.set_hinge(state, "left_elbow", 90)
        p = self.positions(state)
        self.assertGreater(p["LeftHand"][0], p["LeftForeArm"][0] + 0.15)

    def test_neck_and_spine_directions(self):
        nod = self.positions(pa.set_ball(self.rest, "neck", {"flexion": 30}))
        rest_eye = self.positions(self.rest)["LeftEye"]
        self.assertGreater(nod["LeftEye"][2], rest_eye[2] + 0.01)  # chin down: eyes go forward
        self.assertLess(nod["LeftEye"][1], rest_eye[1] - 0.02)     # ... and down
        lean = self.positions(pa.set_ball(self.rest, "spine", {"lateral_flexion_left": 20}))
        self.assertGreater(lean["Head"][0], 0.1)
        turned = pa.set_ball(self.rest, "neck", {"rotation_left": 45})
        eye = self.positions(turned)["LeftEye"]
        self.assertGreater(eye[0], self.positions(self.rest)["LeftEye"][0] + 0.02)


class ValidationTest(unittest.TestCase):
    def test_limits_outside_aaos_are_errors_and_messages_carry_numbers(self):
        state = pa.set_ball(pa.rest_state(), "left_hip", {"extension": 45})
        issues, _ = pa.validate(state)
        issue = next(i for i in issues if i["joint"] == "left_hip")
        self.assertEqual(("error", "swing_limit", "extension"), (issue["severity"], issue["code"], issue["motion"]))
        self.assertAlmostEqual(45.0, issue["value"], delta=0.5)
        self.assertEqual(30.0, issue["limit"])
        self.assertEqual(set(), codes(pa.validate(state, flexibility=1.6)[0]))

    def test_lowering_the_pelvis_without_bending_sinks_the_feet(self):
        state = pa.move_root(pa.rest_state(), (0, -0.3, 0))
        self.assertIn(("left_heel", "ground_penetration"), codes(pa.validate(state)[0]))

    def test_straight_leg_high_kick_warns_but_bent_knee_does_not(self):
        kick = pa.set_ball(pa.rest_state(), "left_hip", {"flexion": 110})
        self.assertIn(("left_hip", "hamstring_coupling"), codes(pa.validate(kick)[0], "warning"))
        tucked = pa.set_hinge(kick, "left_knee", 90)
        self.assertNotIn(("left_hip", "hamstring_coupling"), codes(pa.validate(tucked)[0], "warning"))

    def test_bone_state_round_trip(self):
        state = pa.set_ball(pa.rest_state(), "left_hip", {"flexion": 40, "abduction": 10, "external_rotation": 15})
        again = pa.state_from_bone_state(pa.bone_state_from_state(state))
        self.assertEqual(pa.measure(state), pa.measure(again))


if __name__ == "__main__":
    unittest.main()
