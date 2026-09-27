"""Anatomical measurement, validation and joint-angle editing on the SOMA30 rig.

The LLM should reason in anatomical terms ("knee flexion 90°") and never in
quaternions. This module owns the math: forward kinematics, measuring every
joint as clinical angles, checking them against joint_limits, and building
local rotations from requested angles. Standard library only (see CLAUDE.md).

Frames: SOMA30 rest is a T-pose with identity local rotations, +X = character
left, +Y up, +Z forward, quaternions x,y,z,w. A joint's rotation orients its
children, so the hip angle lives on "LeftLeg", the knee on "LeftShin".

Ball joints use swing-twist: the bone direction's elevation away from the
anatomical neutral direction (limited by an elliptical cone built from the four
planar limits) plus twist about the bone. Twist is measured against the minimal
swing from neutral, which avoids Euler-order dependence (Codman's paradox).
"""

from __future__ import annotations

import importlib.util
import math
from functools import lru_cache
from pathlib import Path

try:
    import joint_limits as limits
except ModuleNotFoundError:
    from webui import joint_limits as limits

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORT_GLB_PY = REPO_ROOT / "vendor" / "kimodo.cpp" / "scripts" / "export_glb.py"

# --------------------------------------------------------------------- vectors

def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def scale(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a): return math.sqrt(dot(a, a))


def unit(a):
    length = norm(a)
    if length < 1e-12:
        raise ValueError("zero-length vector")
    return scale(a, 1.0 / length)


def angle_between(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


def orthogonal_part(v, n):
    return unit(sub(v, scale(n, dot(v, n))))


# ----------------------------------------------------------------- quaternions
IDENTITY = (0.0, 0.0, 0.0, 1.0)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qconj(q): return (-q[0], -q[1], -q[2], q[3])


def qnormalize(q):
    length = math.sqrt(sum(c * c for c in q))
    if length < 1e-12:
        raise ValueError("zero quaternion")
    return tuple(c / length for c in q)


def qrot(q, v):
    return qmul(qmul(q, (v[0], v[1], v[2], 0.0)), qconj(q))[:3]


def qaxis_angle(axis, degrees):
    axis = unit(axis)
    half = math.radians(degrees) / 2.0
    s = math.sin(half)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half))


def qbetween(u, v):
    """Minimal rotation taking direction u onto direction v."""
    u, v = unit(u), unit(v)
    d = dot(u, v)
    if d > 1.0 - 1e-12:
        return IDENTITY
    if d < -1.0 + 1e-12:
        helper = (1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 1.0, 0.0)
        return qaxis_angle(cross(u, helper), 180.0)
    c = cross(u, v)
    return qnormalize((c[0], c[1], c[2], 1.0 + d))


def twist_angle(q, axis):
    """Signed rotation (degrees) of q about axis, from its swing-twist split."""
    axis = unit(axis)
    projection = dot(q[:3], axis)
    angle = math.degrees(2.0 * math.atan2(projection, q[3]))
    return (angle + 180.0) % 360.0 - 180.0


def swing_angle(q, axis):
    """Magnitude (degrees) of the part of q that moves the axis itself."""
    return angle_between(axis, qrot(q, axis))


# -------------------------------------------------------------------- skeleton
@lru_cache(maxsize=1)
def skeleton():
    spec = importlib.util.spec_from_file_location("kimodo_export_glb", EXPORT_GLB_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module.SKELETONS["soma30"]
    names = list(data["names"])
    parents = list(data["parents"])
    offsets = [tuple(float(c) for c in o) for o in data["offsets"]]
    return {"names": names, "parents": parents, "offsets": offsets,
            "index": {name: i for i, name in enumerate(names)}}


def rest_state():
    s = skeleton()
    return {"root": s["offsets"][0], "rot": {name: IDENTITY for name in s["names"]}}


def state_from_bone_state(bone_state):
    """Editor bone_state {name: {position, rotation_xyzw}} (canonical rig)."""
    s = skeleton()
    rot = {}
    for name in s["names"]:
        value = (bone_state or {}).get(name)
        rot[name] = qnormalize(tuple(value["rotation_xyzw"])) if value else IDENTITY
    root = tuple((bone_state or {}).get("Hips", {}).get("position", s["offsets"][0]))
    return {"root": root, "rot": rot}


def bone_state_from_state(state):
    s = skeleton()
    result = {}
    for i, name in enumerate(s["names"]):
        position = state["root"] if i == 0 else s["offsets"][i]
        result[name] = {"position": list(position), "rotation_xyzw": list(state["rot"][name])}
    return result


def forward_kinematics(state):
    s = skeleton()
    world_rot, world_pos = {}, {}
    for i, name in enumerate(s["names"]):
        parent = s["parents"][i]
        if parent < 0:
            world_rot[name] = state["rot"][name]
            world_pos[name] = tuple(state["root"])
        else:
            pname = s["names"][parent]
            world_rot[name] = qmul(world_rot[pname], state["rot"][name])
            world_pos[name] = add(world_pos[pname], qrot(world_rot[pname], s["offsets"][i]))
    return world_rot, world_pos


@lru_cache(maxsize=1)
def heel_offsets():
    """Heel point per foot in the ankle's local frame, as the editor derives it."""
    _, pos = forward_kinematics(rest_state())
    result = {}
    for side, foot, toe in (("left", "LeftFoot", "LeftToeBase"), ("right", "RightFoot", "RightToeBase")):
        ankle, tip = pos[foot], pos[toe]
        heel = (ankle[0], tip[1], ankle[2] - (tip[2] - ankle[2]))
        result[side] = sub(heel, ankle)
    return result


# ---------------------------------------------------------------- joint table
FORWARD = (0.0, 0.0, 1.0)
UP = (0.0, 1.0, 0.0)
DOWN = (0.0, -1.0, 0.0)


def _offset_dir(child):
    s = skeleton()
    return unit(s["offsets"][s["index"][child]])


@lru_cache(maxsize=1)
def ball_joints():
    """Each entry: which bone, measured in which frame, and the anatomical axes.

    axes: (vector, positive name, negative name) x 2 for swing, then the twist
    probe/toward pair: positive twist rotates `probe` toward `toward`.
    """
    joints = {}
    for side, sign in (("left", 1.0), ("right", -1.0)):
        cap = side.capitalize()
        out = (sign, 0.0, 0.0)
        arm_rest = (sign, 0.0, 0.0)
        joints[f"{side}_shoulder"] = dict(
            limits="shoulder", bone=f"{cap}Arm", frame="Chest", rest=arm_rest, neutral=DOWN,
            axes=((FORWARD, "flexion", "extension"), (out, "abduction", "adduction")),
            twist=(FORWARD, out, "external_rotation", "internal_rotation"))
        thigh = _offset_dir(f"{cap}Shin")
        joints[f"{side}_hip"] = dict(
            limits="hip", bone=f"{cap}Leg", frame="Hips", rest=thigh, neutral=thigh,
            axes=((FORWARD, "flexion", "extension"), (out, "abduction", "adduction")),
            twist=(FORWARD, out, "external_rotation", "internal_rotation"))
        foot = _offset_dir(f"{cap}ToeBase")
        foot_up = orthogonal_part(UP, foot)
        joints[f"{side}_ankle"] = dict(
            limits="ankle", bone=f"{cap}Foot", frame=f"{cap}Shin", rest=foot, neutral=foot,
            axes=((foot_up, "dorsiflexion", "plantarflexion"), (out, "abduction", "adduction")),
            twist=(foot_up, out, "inversion", "eversion"))
        palm = (0.0, -1.0, 0.0)
        joints[f"{side}_wrist"] = dict(
            limits="wrist", bone=f"{cap}Hand", frame=f"{cap}ForeArm", rest=arm_rest, neutral=arm_rest,
            axes=((palm, "flexion", "extension"), (FORWARD, "radial_deviation", "ulnar_deviation")),
            twist=(palm, FORWARD, "supination", "pronation"))
        clavicle = _offset_dir(f"{cap}Arm")
        joints[f"{side}_clavicle"] = dict(
            limits="clavicle", bone=f"{cap}Shoulder", frame="Chest", rest=clavicle, neutral=clavicle,
            axes=((orthogonal_part(FORWARD, clavicle), "protraction", "retraction"),
                  (orthogonal_part(UP, clavicle), "elevation", "depression")),
            twist=(orthogonal_part(UP, clavicle), orthogonal_part(FORWARD, clavicle),
                   "rotation_forward", "rotation_backward"))
    left = (1.0, 0.0, 0.0)
    joints["neck"] = dict(
        limits="neck", bone="Head", frame="Chest", rest=UP, neutral=UP,
        axes=((FORWARD, "flexion", "extension"), (left, "lateral_flexion_left", "lateral_flexion_right")),
        twist=(FORWARD, left, "rotation_left", "rotation_right"))
    joints["spine"] = dict(
        limits="spine", bone="Chest", frame="Hips", rest=UP, neutral=UP,
        axes=((FORWARD, "flexion", "extension"), (left, "lateral_flexion_left", "lateral_flexion_right")),
        twist=(FORWARD, left, "rotation_left", "rotation_right"))
    return joints


HINGE_JOINTS = {
    "left_knee": dict(limits="knee", bone="LeftShin", axis=(1.0, 0.0, 0.0)),
    "right_knee": dict(limits="knee", bone="RightShin", axis=(1.0, 0.0, 0.0)),
    "left_elbow": dict(limits="elbow", bone="LeftForeArm", axis=(0.0, -1.0, 0.0)),
    "right_elbow": dict(limits="elbow", bone="RightForeArm", axis=(0.0, 1.0, 0.0)),
}


# ------------------------------------------------------------------ measuring
def _relative(world_rot, frame, bone):
    return qmul(qconj(world_rot[frame]), world_rot[bone])


def _twist_sign(spec):
    probe, toward = spec["twist"][0], spec["twist"][1]
    return 1.0 if dot(cross(probe, toward), spec["neutral"]) >= 0 else -1.0


def measure_ball(world_rot, key):
    spec = ball_joints()[key]
    orientation = _relative(world_rot, spec["frame"], spec["bone"])
    direction = qrot(orientation, spec["rest"])
    neutral = spec["neutral"]
    elevation = angle_between(neutral, direction)
    (axis1, pos1, neg1), (axis2, pos2, neg2) = spec["axes"]
    c1, c2 = dot(direction, axis1), dot(direction, axis2)
    azimuth = math.atan2(c2, c1) if elevation > 1e-6 else 0.0
    planar = {pos1: max(0.0, elevation * math.cos(azimuth)), neg1: max(0.0, -elevation * math.cos(azimuth)),
              pos2: max(0.0, elevation * math.sin(azimuth)), neg2: max(0.0, -elevation * math.sin(azimuth))}
    twist = None
    if elevation < 170.0:
        reference = qmul(qbetween(neutral, direction), qbetween(spec["rest"], neutral))
        raw = twist_angle(qmul(qconj(reference), orientation), spec["rest"])
        twist = raw * _twist_sign(spec)
    return {"elevation": elevation, "azimuth": math.degrees(azimuth), "planar": planar,
            "twist": twist, "twist_names": spec["twist"][2:], "cos": math.cos(azimuth), "sin": math.sin(azimuth)}


def measure_hinge(state, key):
    spec = HINGE_JOINTS[key]
    local = state["rot"][spec["bone"]]
    return {"flexion": twist_angle(local, spec["axis"]), "off_axis": swing_angle(local, spec["axis"])}


def measure(state):
    """Every joint as clinical angles (degrees), rounded for an LLM prompt."""
    world_rot, _ = forward_kinematics(state)
    result = {}
    for key in ball_joints():
        m = measure_ball(world_rot, key)
        entry = {name: round(value, 1) for name, value in m["planar"].items() if value >= 0.5}
        if m["twist"] is not None:
            positive, negative = m["twist_names"]
            if abs(m["twist"]) >= 0.5:
                entry[positive if m["twist"] > 0 else negative] = round(abs(m["twist"]), 1)
        result[key] = entry
    for key in HINGE_JOINTS:
        m = measure_hinge(state, key)
        result[key] = {"flexion": round(m["flexion"], 1)}
    return result


# ------------------------------------------------------------------ validating
def _ellipse_limit(cos_a, sin_a, axis1_limits, axis2_limits):
    limit1 = axis1_limits[0] if cos_a >= 0 else axis1_limits[1]
    limit2 = axis2_limits[0] if sin_a >= 0 else axis2_limits[1]
    denominator = math.sqrt((cos_a / max(limit1, 1e-6)) ** 2 + (sin_a / max(limit2, 1e-6)) ** 2)
    return 1.0 / denominator if denominator > 1e-12 else max(limit1, limit2)


def validate(state, *, flexibility=1.0):
    """Return (issues, measurements). Issues carry numbers the LLM can act on."""
    world_rot, world_pos = forward_kinematics(state)
    contacts = contact_points(world_rot, world_pos)
    issues = []
    for key, spec in ball_joints().items():
        table = limits.BALL_LIMITS[spec["limits"]]
        m = measure_ball(world_rot, key)
        (_, pos1, neg1), (_, pos2, neg2) = spec["axes"]
        swing = dict(table["swing"])
        if spec["limits"] == "ankle":
            side = key.split("_")[0]
            if min(contacts[f"{side}_heel"][1], contacts[f"{side}_toe"][1]) < limits.WEIGHT_BEARING_CONTACT_M:
                swing["dorsiflexion"] = limits.ANKLE_WEIGHT_BEARING_DORSIFLEXION_DEG
        limit = flexibility * _ellipse_limit(m["cos"], m["sin"], (swing[pos1], swing[neg1]), (swing[pos2], swing[neg2]))
        if m["elevation"] > limit + 0.5:
            dominant = max(m["planar"], key=m["planar"].get)
            issues.append({"joint": key, "severity": "error" if table["severity"] == "hard" else "warning",
                           "code": "swing_limit", "motion": dominant, "value": round(m["elevation"], 1),
                           "limit": round(limit, 1),
                           "message": f"{key} {dominant} {m['elevation']:.0f}° exceeds {limit:.0f}°"})
        if m["twist"] is not None:
            positive, negative = m["twist_names"]
            name = positive if m["twist"] >= 0 else negative
            twist_limit = flexibility * table["twist"][name]
            if abs(m["twist"]) > twist_limit + 0.5:
                issues.append({"joint": key, "severity": "error" if table["severity"] == "hard" else "warning",
                               "code": "twist_limit", "motion": name, "value": round(abs(m["twist"]), 1),
                               "limit": round(twist_limit, 1),
                               "message": f"{key} {name} {abs(m['twist']):.0f}° exceeds {twist_limit:.0f}°"})
    for key, spec in HINGE_JOINTS.items():
        table = limits.HINGE_LIMITS[spec["limits"]]
        m = measure_hinge(state, key)
        if m["off_axis"] > limits.HINGE_OFF_AXIS_DEG:
            issues.append({"joint": key, "severity": "error", "code": "hinge_off_axis",
                           "value": round(m["off_axis"], 1), "limit": limits.HINGE_OFF_AXIS_DEG,
                           "message": f"{key} bends {m['off_axis']:.0f}° off its single hinge axis"})
        if m["flexion"] < -limits.HYPEREXTENSION_DEG - 0.5:
            issues.append({"joint": key, "severity": "error", "code": "hyperextension",
                           "value": round(m["flexion"], 1), "limit": -limits.HYPEREXTENSION_DEG,
                           "message": f"{key} is bent backwards ({m['flexion']:.0f}°); it only flexes one way"})
        elif m["flexion"] > flexibility * table["flexion"] + 0.5:
            issues.append({"joint": key, "severity": "error", "code": "flexion_limit",
                           "value": round(m["flexion"], 1), "limit": round(flexibility * table["flexion"], 1),
                           "message": f"{key} flexion {m['flexion']:.0f}° exceeds {table['flexion']:.0f}°"})
    for side in ("left", "right"):
        hip = measure_ball(world_rot, f"{side}_hip")["planar"]["flexion"]
        knee = measure_hinge(state, f"{side}_knee")["flexion"]
        if hip > limits.STRAIGHT_LEG_HIP_FLEXION_WARN_DEG and knee < limits.STRAIGHT_LEG_KNEE_MAX_DEG:
            issues.append({"joint": f"{side}_hip", "severity": "warning", "code": "hamstring_coupling",
                           "value": round(hip, 1), "limit": limits.STRAIGHT_LEG_HIP_FLEXION_WARN_DEG,
                           "message": f"{side} hip flexed {hip:.0f}° with a straight knee (hamstrings usually stop ~90°)"})
    for name, point in contacts.items():
        if point[1] < -limits.GROUND_TOLERANCE_M:
            issues.append({"joint": name, "severity": "error", "code": "ground_penetration",
                           "value": round(point[1], 3), "limit": 0.0,
                           "message": f"{name} is {-point[1] * 100:.0f} cm below the ground"})
    return issues, measure(state)


def contact_points(world_rot, world_pos):
    points = {}
    for side, foot, toe, hand in (("left", "LeftFoot", "LeftToeBase", "LeftHand"),
                                  ("right", "RightFoot", "RightToeBase", "RightHand")):
        points[f"{side}_ankle"] = world_pos[foot]
        points[f"{side}_toe"] = world_pos[toe]
        points[f"{side}_heel"] = add(world_pos[foot], qrot(world_rot[foot], heel_offsets()[side]))
        points[f"{side}_hand"] = world_pos[hand]
    return points


# --------------------------------------------------------------------- editing
def _signed(angles, positive, negative):
    return float(angles.get(positive, 0.0)) - float(angles.get(negative, 0.0))


def set_ball(state, key, angles):
    """Set a ball joint from clinical angles, e.g. {"flexion": 90, "external_rotation": 20}.

    Unmentioned angles are zero: this sets the joint's absolute orientation
    relative to its measuring frame, keeping every other joint's local rotation.
    """
    spec = ball_joints()[key]
    (axis1, pos1, neg1), (axis2, pos2, neg2) = spec["axes"]
    known = {pos1, neg1, pos2, neg2, *spec["twist"][2:]}
    unknown = set(angles) - known
    if unknown:
        raise ValueError(f"{key}: unknown motions {sorted(unknown)}; use {sorted(known)}")
    neutral = spec["neutral"]
    first = _signed(angles, pos1, neg1)
    second = _signed(angles, pos2, neg2)
    # Exact inverse of measure_ball: elevation = |(first, second)| in the plane
    # whose azimuth is atan2(second, first), so measured planar angles read back.
    elevation = math.hypot(first, second)
    direction = neutral
    if elevation > 1e-9:
        plane = unit(add(scale(axis1, first / elevation), scale(axis2, second / elevation)))
        direction = qrot(qaxis_angle(cross(neutral, plane), elevation), neutral)
    twist = _signed(angles, *spec["twist"][2:]) * _twist_sign(spec)
    orientation = qmul(qbetween(neutral, direction), qbetween(spec["rest"], neutral))
    orientation = qmul(orientation, qaxis_angle(spec["rest"], twist))
    world_rot, _ = forward_kinematics(state)
    s = skeleton()
    parent = s["names"][s["parents"][s["index"][spec["bone"]]]]
    desired_world = qmul(world_rot[spec["frame"]], orientation)
    rot = dict(state["rot"])
    rot[spec["bone"]] = qnormalize(qmul(qconj(world_rot[parent]), desired_world))
    return {"root": state["root"], "rot": rot}


def set_hinge(state, key, flexion):
    spec = HINGE_JOINTS[key]
    rot = dict(state["rot"])
    rot[spec["bone"]] = qaxis_angle(spec["axis"], float(flexion))
    return {"root": state["root"], "rot": rot}


def move_root(state, delta):
    return {"root": add(tuple(state["root"]), tuple(delta)), "rot": dict(state["rot"])}
