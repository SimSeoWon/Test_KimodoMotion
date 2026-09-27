"""Anatomical pose operations: what the LLM asks for, applied and checked in Python.

The LLM returns a short list of clinical-angle / metre operations (schema
below). Python applies them with forward kinematics and two-bone IK, validates
the result against joint_limits, and exports both the exact bone state (for the
editor) and the world-space controls the engine consumes. The LLM never writes
a quaternion, which is what made the previous agent slow (minutes of thinking
spent on rotation arithmetic).
"""

from __future__ import annotations

import json
import math

try:
    import pose_anatomy as pa
    import joint_limits as limits
except ModuleNotFoundError:
    from webui import pose_anatomy as pa
    from webui import joint_limits as limits

TRANSLATE_AXES = {"left": (1, 0, 0), "right": (-1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0),
                  "forward": (0, 0, 1), "back": (0, 0, -1)}
LIMB_TARGETS = {"left_foot": "left_leg", "right_foot": "right_leg", "left_hand": "left_arm", "right_hand": "right_arm"}
LIMBS = {
    "left_leg": dict(upper="LeftLeg", lower="LeftShin", end="LeftFoot", toe="LeftToeBase",
                     ball="left_hip", hinge="left_knee"),
    "right_leg": dict(upper="RightLeg", lower="RightShin", end="RightFoot", toe="RightToeBase",
                      ball="right_hip", hinge="right_knee"),
    "left_arm": dict(upper="LeftArm", lower="LeftForeArm", end="LeftHand", ball="left_shoulder", hinge="left_elbow"),
    "right_arm": dict(upper="RightArm", lower="RightForeArm", end="RightHand", ball="right_shoulder", hinge="right_elbow"),
}
# Which editor controls an operation on a joint touches (whole chain, so the
# editor's IK reproduces the limb and the engine gets a coherent constraint set).
CHAIN_CONTROLS = {
    "left_leg": ("left_hip", "left_knee", "left_foot", "left_toe"),
    "right_leg": ("right_hip", "right_knee", "right_foot", "right_toe"),
    "left_arm": ("left_shoulder", "left_elbow", "left_hand"),
    "right_arm": ("right_shoulder", "right_elbow", "right_hand"),
}
JOINT_CHAIN = {
    "left_hip": "left_leg", "left_knee": "left_leg", "left_ankle": "left_leg", "left_foot": "left_leg",
    "right_hip": "right_leg", "right_knee": "right_leg", "right_ankle": "right_leg", "right_foot": "right_leg",
    "left_shoulder": "left_arm", "left_elbow": "left_arm", "left_wrist": "left_arm", "left_clavicle": "left_arm",
    "left_hand": "left_arm",
    "right_shoulder": "right_arm", "right_elbow": "right_arm", "right_wrist": "right_arm", "right_clavicle": "right_arm",
    "right_hand": "right_arm",
}
SINGLE_CONTROLS = {"spine": ("chest",), "neck": ("head",), "pelvis": ("pelvis",)}
CONTROL_JOINTS = {
    "pelvis": "Hips", "chest": "Chest", "head": "Head", "left_shoulder": "LeftShoulder",
    "left_elbow": "LeftForeArm", "left_hand": "LeftHand", "right_shoulder": "RightShoulder",
    "right_elbow": "RightForeArm", "right_hand": "RightHand", "left_hip": "LeftLeg", "left_knee": "LeftShin",
    "left_foot": "LeftFoot", "left_toe": "LeftToeBase", "right_hip": "RightLeg", "right_knee": "RightShin",
    "right_foot": "RightFoot", "right_toe": "RightToeBase",
}
ROTATION_CONTROLS = {"pelvis", "chest", "head", "left_shoulder", "right_shoulder", "left_hip", "right_hip",
                     "left_hand", "right_hand", "left_foot", "right_foot"}
POSITION_CONTROLS = {"pelvis", "left_elbow", "right_elbow", "left_hand", "right_hand", "left_knee", "right_knee",
                     "left_foot", "right_foot", "left_toe", "right_toe"}


def joint_names():
    return sorted([*pa.ball_joints(), *pa.HINGE_JOINTS, "pelvis", *LIMB_TARGETS])


OPS_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "maxLength": 80},
        "summary": {"type": "string", "maxLength": 400},
        "operations": {
            "type": "array", "maxItems": 24,
            "items": {
                "type": "object",
                "properties": {
                    "joint": {"type": "string", "enum": joint_names()},
                    "mode": {"type": "string", "enum": ["set", "add"]},
                    "angles": {"type": "object", "additionalProperties": {"type": "number"}},
                    "translate_m": {
                        "type": "object",
                        "properties": {axis: {"type": "number"} for axis in TRANSLATE_AXES},
                        "additionalProperties": False,
                    },
                    "turn_out_deg": {"type": "number"},
                },
                "required": ["joint", "mode"],
                "additionalProperties": False,
            },
        },
        "keep_planted": {"type": "array", "items": {"type": "string", "enum": ["left_foot", "right_foot"]}},
    },
    "required": ["name", "summary", "operations", "keep_planted"],
    "additionalProperties": False,
}


class OperationError(ValueError):
    pass


# ------------------------------------------------------------------ applying
def _translation(values):
    delta = (0.0, 0.0, 0.0)
    for axis, amount in (values or {}).items():
        if axis not in TRANSLATE_AXES:
            raise OperationError(f"unknown direction {axis}")
        if abs(amount) > 1.5:
            raise OperationError(f"{axis} move {amount} m is not a pose edit")
        delta = pa.add(delta, pa.scale(TRANSLATE_AXES[axis], float(amount)))
    return delta


def _ball_angles_now(state, key):
    world_rot, _ = pa.forward_kinematics(state)
    m = pa.measure_ball(world_rot, key)
    angles = dict(m["planar"])
    if m["twist"] is not None:
        positive, negative = m["twist_names"]
        angles[positive] = max(0.0, m["twist"])
        angles[negative] = max(0.0, -m["twist"])
    return angles


def _merged_angles(current, delta, spec):
    """Add delta motions onto current ones, cancelling opposite motions."""
    pairs = [(a[1], a[2]) for a in spec["axes"]] + [tuple(spec["twist"][2:])]
    result = {}
    for positive, negative in pairs:
        value = (current.get(positive, 0.0) - current.get(negative, 0.0)
                 + delta.get(positive, 0.0) - delta.get(negative, 0.0))
        result[positive if value >= 0 else negative] = abs(value)
    return result


def _limb_positions(state, limb):
    _, pos = pa.forward_kinematics(state)
    return pos[limb["upper"]], pos[limb["lower"]], pos[limb["end"]]


def _solve_two_bone(state, limb_key, target, pole):
    """Reach `target` with the limb end: hinge flexion by bisection, then aim, then
    swing the bend plane toward `pole`. Returns (state, reached)."""
    limb = LIMBS[limb_key]
    hinge = limb["hinge"]

    def reach(flexion):
        trial = pa.set_hinge(state, hinge, flexion)
        root, _, end = _limb_positions(trial, limb)
        return pa.norm(pa.sub(end, root))

    root = _limb_positions(state, limb)[0]
    distance = pa.norm(pa.sub(target, root))
    low, high = 0.0, limits.HINGE_LIMITS[pa.HINGE_JOINTS[hinge]["limits"]]["flexion"]
    reached = reach(low) + 1e-3 >= distance >= reach(high) - 1e-3
    if distance >= reach(low):
        flexion = low
    elif distance <= reach(high):
        flexion = high
    else:
        for _ in range(40):
            middle = (low + high) / 2
            low, high = (middle, high) if reach(middle) > distance else (low, middle)
        flexion = (low + high) / 2
    state = pa.set_hinge(state, hinge, flexion)

    world_rot, pos = pa.forward_kinematics(state)
    current = pa.sub(pos[limb["end"]], root)
    wanted = pa.sub(target, root)
    parent = _parent(limb["upper"])
    aim = pa.qbetween(current, wanted)
    new_world = pa.qmul(aim, world_rot[limb["upper"]])
    state = _set_world(state, limb["upper"], new_world, world_rot[parent])

    if pole is not None and pa.norm(wanted) > 1e-6:
        axis = pa.unit(wanted)
        world_rot, pos = pa.forward_kinematics(state)
        mid = pa.sub(pos[limb["lower"]], root)
        mid_perp = pa.sub(mid, pa.scale(axis, pa.dot(mid, axis)))
        pole_perp = pa.sub(pa.sub(pole, root), pa.scale(axis, pa.dot(pa.sub(pole, root), axis)))
        if pa.norm(mid_perp) > 1e-6 and pa.norm(pole_perp) > 1e-6:
            angle = math.degrees(math.atan2(pa.dot(pa.cross(mid_perp, pole_perp), axis), pa.dot(mid_perp, pole_perp)))
            spin = pa.qaxis_angle(axis, angle)
            state = _set_world(state, limb["upper"], pa.qmul(spin, world_rot[limb["upper"]]), world_rot[parent])
    return state, reached


def _parent(name):
    s = pa.skeleton()
    return s["names"][s["parents"][s["index"][name]]]


def _set_world(state, bone, world, parent_world):
    rot = dict(state["rot"])
    rot[bone] = pa.qnormalize(pa.qmul(pa.qconj(parent_world), world))
    return {"root": state["root"], "rot": rot}


def _yaw(degrees):
    return pa.qaxis_angle((0, 1, 0), degrees)


def apply_operations(state, operations, keep_planted):
    """Apply ops in order; planted feet keep their start position and orientation."""
    start_rot, start_pos = pa.forward_kinematics(state)
    foot_targets = {}
    unreached = []
    for index, op in enumerate(operations):
        joint, mode = op["joint"], op["mode"]
        where = f"operations[{index}] {joint}"
        if joint == "pelvis":
            if op.get("angles"):
                raise OperationError(f"{where}: rotate the pelvis through spine/hip angles, not pelvis angles")
            delta = _translation(op.get("translate_m"))
            state = pa.move_root(state, delta) if mode == "add" else {
                "root": pa.add(pa.rest_state()["root"], delta), "rot": dict(state["rot"])}
        elif joint in LIMB_TARGETS:
            limb_key = LIMB_TARGETS[joint]
            limb = LIMBS[limb_key]
            # End-point moves are relative to where the hand/foot was when the
            # edit began, never to a transient mid-sequence state: otherwise an
            # earlier op (say a knee bent to 170° then relaxed) drags the target
            # along and op order decides the result -- the deadlock seen before.
            previous = foot_targets.get(joint)
            base = previous[0] if previous else start_pos[limb["end"]]
            target = pa.add(base, _translation(op.get("translate_m")))
            end_world = previous[1] if previous else start_rot[limb["end"]]
            turn = float(op.get("turn_out_deg", 0.0))
            if turn:
                if limb_key.endswith("arm"):
                    raise OperationError(f"{where}: turn_out_deg applies to feet only")
                outward = 1.0 if limb_key.startswith("left") else -1.0
                end_world = pa.qmul(_yaw(turn * outward), end_world)
            foot_targets[joint] = (target, end_world)
        elif joint in pa.HINGE_JOINTS:
            angles = op.get("angles") or {}
            if set(angles) - {"flexion", "extension"}:
                raise OperationError(f"{where}: a hinge only takes flexion (negative = extension)")
            value = float(angles.get("flexion", 0.0)) - float(angles.get("extension", 0.0))
            if mode == "add":
                value += pa.measure_hinge(state, joint)["flexion"]
            state = pa.set_hinge(state, joint, value)
        elif joint in pa.ball_joints():
            angles = {k: float(v) for k, v in (op.get("angles") or {}).items()}
            spec = pa.ball_joints()[joint]
            if mode == "add":
                known = {a[1] for a in spec["axes"]} | {a[2] for a in spec["axes"]} | set(spec["twist"][2:])
                if set(angles) - known:
                    raise OperationError(f"{where}: unknown motions {sorted(set(angles) - known)}")
                angles = _merged_angles(_ball_angles_now(state, joint), angles, spec)
            try:
                state = pa.set_ball(state, joint, angles)
            except ValueError as exc:
                raise OperationError(f"{where}: {exc}") from None
        else:
            raise OperationError(f"{where}: unknown joint")

    for foot in keep_planted:
        if foot not in foot_targets:
            end = LIMBS[LIMB_TARGETS[foot]]["end"]
            foot_targets[foot] = (start_pos[end], start_rot[end])
    for joint, (target, end_world) in foot_targets.items():
        limb_key = LIMB_TARGETS[joint]
        limb = LIMBS[limb_key]
        _, pos = pa.forward_kinematics(state)
        # The pole sits in front of the limb's own root-to-target line, not at the
        # pre-solve knee: that knee can be anywhere after a pelvis move and made
        # knees cave inward (measured -16° against straight toes).
        middle = pa.scale(pa.add(pos[limb["upper"]], target), 0.5)
        if limb_key.endswith("leg"):
            # Knees track the toes: bend toward where the foot points.
            toe_dir = pa.qrot(end_world, pa.skeleton()["offsets"][pa.skeleton()["index"][limb["toe"]]])
            flat = (toe_dir[0], 0.0, toe_dir[2])
            pole = pa.add(middle, pa.scale(pa.unit(flat) if pa.norm(flat) > 1e-6 else (0, 0, 1), 0.5))
        else:
            pole = pa.add(middle, (0.0, -0.3, -0.3))
        state, reached = _solve_two_bone(state, limb_key, target, pole)
        if not reached:
            unreached.append(joint)
        world_rot, _ = pa.forward_kinematics(state)
        state = _set_world(state, limb["end"], end_world, world_rot[limb["lower"]])
    return state, unreached


# ------------------------------------------------------------------ exporting
def touched_controls(operations, keep_planted):
    touched = set()
    for op in operations:
        joint = op["joint"]
        if joint in JOINT_CHAIN:
            touched.update(CHAIN_CONTROLS[JOINT_CHAIN[joint]])
        elif joint in SINGLE_CONTROLS:
            touched.update(SINGLE_CONTROLS[joint])
    for foot in keep_planted:
        touched.update(CHAIN_CONTROLS[JOINT_CHAIN[foot]])
    if any(op["joint"] == "pelvis" for op in operations):
        touched.add("pelvis")
    return touched


def controls_from_state(state, control_ids):
    world_rot, world_pos = pa.forward_kinematics(state)
    controls = {}
    for control_id in sorted(control_ids):
        bone = CONTROL_JOINTS[control_id]
        value = {"space": "world", "weight": 1.0}
        if control_id in POSITION_CONTROLS:
            value["position"] = [round(c, 6) for c in world_pos[bone]]
        if control_id in ROTATION_CONTROLS and control_id != "pelvis":
            value["rotation_xyzw"] = [round(c, 7) for c in world_rot[bone]]
        controls[control_id] = value
    return controls


def facts(before, after):
    """Numbers Python measured, appended to the summary so it never over-claims."""
    def summary(state):
        world_rot, pos = pa.forward_kinematics(state)
        angles = pa.measure(state)
        width = abs(pos["LeftFoot"][0] - pos["RightFoot"][0])
        return pos["Hips"][1], width, angles["left_knee"]["flexion"], angles["right_knee"]["flexion"]
    b, a = summary(before), summary(after)
    return (f"측정: 골반 높이 {b[0]:.2f}→{a[0]:.2f}m, 발목 좌우 간격 {b[1]:.2f}→{a[1]:.2f}m, "
            f"무릎 굴곡 L {a[2]:.0f}° R {a[3]:.0f}°")


# -------------------------------------------------------------------- prompt
def build_prompt(instruction, state, pose_controls, feedback=None):
    world_rot, pos = pa.forward_kinematics(state)
    contacts = {name: round(p[1], 3) for name, p in pa.contact_points(world_rot, pos).items() if "hand" not in name}
    motions = {}
    for key, spec in pa.ball_joints().items():
        table = limits.BALL_LIMITS[spec["limits"]]
        motions[key] = {**table["swing"], **table["twist"]}
    for key, spec in pa.HINGE_JOINTS.items():
        motions[key] = {"flexion": limits.HINGE_LIMITS[spec["limits"]]["flexion"],
                        "extension(hyper)": limits.HYPEREXTENSION_DEG}
    text = f"""You edit a single-frame character pose by returning anatomical operations only.
Python applies them with forward kinematics and IK and checks joint limits; never compute
quaternions or coordinates yourself. Axes: +X character left, +Y up, +Z forward; metres; degrees.

Operations (applied in order):
- Ball/hinge joint: {{"joint": J, "mode": "set"|"add", "angles": {{motion: degrees}}}}.
  "set" makes the listed motions absolute and every unlisted motion of that joint 0.
  "add" changes only the listed motions relative to now (use for "more", "a bit", "조금").
- "pelvis": {{"joint":"pelvis","mode":"add","translate_m":{{"down":0.15,"back":0.1}}}} moves the whole body.
- "left_foot"/"right_foot"/"left_hand"/"right_hand": translate_m moves that end point from where it is
  now (IK solves the limb; mode is ignored, repeated moves add up). Feet may add "turn_out_deg"
  (toes outward = 팔자; knees follow the toes). Moved feet keep their orientation on the ground.
Only the finished pose is checked, so operation order never blocks a valid result.
- keep_planted: feet that must stay where they are now. Lowering or shifting the body with feet on
  the ground = pelvis translate + keep_planted both feet (knees/hips/ankles are solved for you).
  Widening the stance = translate each foot outward (left_foot "left", right_foot "right") and keep the
  other foot planted if it should not move.
Keep changes to what the instruction asks. Summaries must describe intent, not invent measurements.

Allowed motions and limits (degrees): {json.dumps(motions, separators=(',', ':'))}

Current joint angles: {json.dumps(pa.measure(state), ensure_ascii=False, separators=(',', ':'))}
Pelvis height {pos['Hips'][1]:.3f} m; ankle separation {abs(pos['LeftFoot'][0] - pos['RightFoot'][0]):.3f} m;
contact heights: {json.dumps(contacts, separators=(',', ':'))}
Constraints already authored by the user: {sorted(pose_controls)}

Instruction: {instruction}
"""
    if feedback:
        text += f"\nYour previous operations: {json.dumps(feedback['operations'], ensure_ascii=False)}\n"
        text += f"They violated: {json.dumps(feedback['issues'], ensure_ascii=False)}\nReturn corrected operations.\n"
    return text


def run(instruction, bone_state, pose_controls, ask, *, max_rounds=2):
    """ask(prompt) -> dict matching OPS_SCHEMA. Returns the agent result."""
    start = pa.state_from_bone_state(bone_state)
    feedback = None
    for round_index in range(max_rounds):
        reply = ask(build_prompt(instruction, start, pose_controls, feedback))
        operations = reply.get("operations") or []
        planted = list(dict.fromkeys(reply.get("keep_planted") or []))
        try:
            state, unreached = apply_operations(start, operations, planted)
        except OperationError as exc:
            issues = [{"severity": "error", "code": "invalid_operation", "message": str(exc)}]
        else:
            issues, _ = pa.validate(state)
            issues += [{"joint": foot, "severity": "error", "code": "unreachable",
                        "message": f"{foot} target is out of the leg's reach"} for foot in unreached]
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if not errors:
            warnings = [issue["message"] for issue in issues if issue["severity"] == "warning"]
            controls = controls_from_state(state, set(pose_controls) | touched_controls(operations, planted))
            summary = str(reply.get("summary", "")).strip()
            summary = f"{summary} {facts(start, state)}" + (f" 주의: {'; '.join(warnings)}" if warnings else "")
            return {"name": reply.get("name") or "", "summary": summary[:500], "controls": controls,
                    "bone_state": pa.bone_state_from_state(state), "operations": operations,
                    "keep_planted": planted, "rounds": round_index + 1, "warnings": warnings}
        feedback = {"operations": operations, "issues": errors}
    raise OperationError("요청한 자세가 관절 가동 범위를 벗어납니다: "
                         + "; ".join(issue["message"] for issue in feedback["issues"]))
