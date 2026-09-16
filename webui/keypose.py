"""Shared key-pose contract for the Web UI, automation API, and future MCP server.

The browser and agents operate on named controls rather than Kimodo motion-vector
indices. Conversion into observed/observed_mask stays behind the runtime boundary.
"""

from __future__ import annotations

import math
from copy import deepcopy


SCHEMA_VERSION = 1
COORDINATE_SYSTEM = {"handedness": "right", "up": "+Y", "forward": "+Z", "unit": "meter"}

# These are the deliberately small, always-visible posing controls. soma_joint is
# the stable SOMA30 joint name used by the native runtime and GLB preview skeleton.
CONTROLS = (
    {"id": "pelvis", "label": "골반", "soma_joint": "Hips", "joint_index": 0, "modes": ["move", "rotate"]},
    {"id": "chest", "label": "가슴", "soma_joint": "Chest", "joint_index": 3, "modes": ["move", "rotate"]},
    {"id": "head", "label": "고개", "soma_joint": "Head", "joint_index": 6, "modes": ["move", "rotate"]},
    {"id": "left_shoulder", "label": "왼쪽 어깨", "soma_joint": "LeftShoulder", "joint_index": 10, "modes": ["move", "rotate"]},
    {"id": "left_elbow", "label": "왼쪽 팔꿈치", "soma_joint": "LeftForeArm", "joint_index": 12, "modes": ["move", "rotate"]},
    {"id": "left_hand", "label": "왼손", "soma_joint": "LeftHand", "joint_index": 13, "modes": ["move", "rotate"]},
    {"id": "right_shoulder", "label": "오른쪽 어깨", "soma_joint": "RightShoulder", "joint_index": 16, "modes": ["move", "rotate"]},
    {"id": "right_elbow", "label": "오른쪽 팔꿈치", "soma_joint": "RightForeArm", "joint_index": 18, "modes": ["move", "rotate"]},
    {"id": "right_hand", "label": "오른손", "soma_joint": "RightHand", "joint_index": 19, "modes": ["move", "rotate"]},
    {"id": "left_knee", "label": "왼쪽 무릎", "soma_joint": "LeftShin", "joint_index": 23, "modes": ["move", "rotate"]},
    {"id": "left_foot", "label": "왼발", "soma_joint": "LeftFoot", "joint_index": 24, "modes": ["move", "rotate"]},
    {"id": "right_knee", "label": "오른쪽 무릎", "soma_joint": "RightShin", "joint_index": 27, "modes": ["move", "rotate"]},
    {"id": "right_foot", "label": "오른발", "soma_joint": "RightFoot", "joint_index": 28, "modes": ["move", "rotate"]},
)
CONTROL_BY_ID = {control["id"]: control for control in CONTROLS}

AI_COMMANDS = (
    "get_pose_state", "list_keyposes", "create_keypose", "move_control",
    "rotate_control", "set_constraint", "plant_foot", "place_hands",
    "look_at", "mirror_pose", "copy_keypose", "preview_pose",
    "undo_pose_edit", "redo_pose_edit", "generate_motion",
)


class KeyposeValidationError(ValueError):
    pass


def get_keypose_schema() -> dict:
    """Return a JSON-safe copy so callers cannot mutate the shared definitions."""
    return {
        "schema_version": SCHEMA_VERSION,
        "coordinate_system": dict(COORDINATE_SYSTEM),
        "spaces": ["world", "character", "local"],
        "gizmo_modes": ["select", "move", "rotate"],
        "controls": deepcopy(CONTROLS),
        "ai_commands": list(AI_COMMANDS),
    }


def _finite_vector(value, size: int, path: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise KeyposeValidationError(f"{path} must contain exactly {size} numbers")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise KeyposeValidationError(f"{path} must contain only finite numbers")
        result.append(float(item))
    return result


def validate_keypose_document(document: dict, frame_count: int | None = None) -> dict:
    """Validate and normalize an external key-pose document.

    The returned object is detached from the caller. Quaternions are normalized;
    malformed or unknown controls are rejected instead of silently ignored.
    """
    if not isinstance(document, dict):
        raise KeyposeValidationError("keypose document must be an object")
    if frame_count is not None and (
        isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count <= 0
    ):
        raise KeyposeValidationError("frame_count must be a positive integer")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise KeyposeValidationError(f"schema_version must be {SCHEMA_VERSION}")
    keyposes = document.get("keyposes")
    if not isinstance(keyposes, list):
        raise KeyposeValidationError("keyposes must be an array")
    if len(keyposes) > 64:
        raise KeyposeValidationError("at most 64 keyposes are allowed")

    normalized = {"schema_version": SCHEMA_VERSION, "keyposes": []}
    used_frames = set()
    for keypose_index, keypose in enumerate(keyposes):
        path = f"keyposes[{keypose_index}]"
        if not isinstance(keypose, dict):
            raise KeyposeValidationError(f"{path} must be an object")
        frame = keypose.get("frame")
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise KeyposeValidationError(f"{path}.frame must be a non-negative integer")
        if frame_count is not None and frame >= frame_count:
            raise KeyposeValidationError(f"{path}.frame must be less than frame_count")
        if frame in used_frames:
            raise KeyposeValidationError(f"duplicate keypose frame: {frame}")
        used_frames.add(frame)

        label = keypose.get("label", "")
        if not isinstance(label, str) or len(label) > 80:
            raise KeyposeValidationError(f"{path}.label must be a string of at most 80 characters")
        controls = keypose.get("controls", {})
        if not isinstance(controls, dict):
            raise KeyposeValidationError(f"{path}.controls must be an object")

        normalized_controls = {}
        for control_id, constraint in controls.items():
            control_path = f"{path}.controls.{control_id}"
            if control_id not in CONTROL_BY_ID:
                raise KeyposeValidationError(f"unknown control: {control_id}")
            if not isinstance(constraint, dict):
                raise KeyposeValidationError(f"{control_path} must be an object")
            result = {}
            if "position" in constraint:
                result["position"] = _finite_vector(constraint["position"], 3, f"{control_path}.position")
            if "rotation_xyzw" in constraint:
                quat = _finite_vector(constraint["rotation_xyzw"], 4, f"{control_path}.rotation_xyzw")
                norm = math.sqrt(sum(component * component for component in quat))
                if norm < 1e-8:
                    raise KeyposeValidationError(f"{control_path}.rotation_xyzw must not be zero")
                result["rotation_xyzw"] = [component / norm for component in quat]
            if not result:
                raise KeyposeValidationError(f"{control_path} needs position or rotation_xyzw")
            space = constraint.get("space", "character")
            if space not in ("world", "character", "local"):
                raise KeyposeValidationError(f"{control_path}.space is invalid")
            weight = constraint.get("weight", 1.0)
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight):
                raise KeyposeValidationError(f"{control_path}.weight must be finite")
            if not 0.0 <= float(weight) <= 4.0:
                raise KeyposeValidationError(f"{control_path}.weight must be in 0..4")
            result["space"] = space
            result["weight"] = float(weight)
            normalized_controls[control_id] = result

        normalized["keyposes"].append({"frame": frame, "label": label, "controls": normalized_controls})

    normalized["keyposes"].sort(key=lambda item: item["frame"])
    return normalized
