"""Shared key-pose contract for the Web UI, automation API, and future MCP server.

The browser and agents operate on named controls rather than Kimodo motion-vector
indices. Conversion into observed/observed_mask stays behind the runtime boundary.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Mapping


SCHEMA_VERSION = 1
COORDINATE_SYSTEM = {"handedness": "right", "up": "+Y", "forward": "+Z", "unit": "meter"}

# These are the deliberately small, always-visible posing controls. soma_joint is
# the stable SOMA30 joint name used by the native runtime and GLB preview skeleton.
CONTROLS = (
    {"id": "pelvis", "label": "골반 / Root", "soma_joint": "Hips", "joint_index": 0, "modes": ["move", "rotate"], "role": "root"},
    {"id": "chest", "label": "가슴", "soma_joint": "Chest", "joint_index": 3, "modes": ["rotate"]},
    {"id": "head", "label": "고개", "soma_joint": "Head", "joint_index": 6, "modes": ["rotate"]},
    {"id": "left_shoulder", "label": "왼쪽 어깨", "soma_joint": "LeftShoulder", "joint_index": 10, "modes": ["rotate"]},
    {"id": "left_elbow", "label": "왼쪽 팔꿈치", "soma_joint": "LeftForeArm", "joint_index": 12, "modes": ["move"]},
    {"id": "left_hand", "label": "왼손", "soma_joint": "LeftHand", "joint_index": 13, "modes": ["move", "rotate"]},
    {"id": "right_shoulder", "label": "오른쪽 어깨", "soma_joint": "RightShoulder", "joint_index": 16, "modes": ["rotate"]},
    {"id": "right_elbow", "label": "오른쪽 팔꿈치", "soma_joint": "RightForeArm", "joint_index": 18, "modes": ["move"]},
    {"id": "right_hand", "label": "오른손", "soma_joint": "RightHand", "joint_index": 19, "modes": ["move", "rotate"]},
    {"id": "left_hip", "label": "왼쪽 고관절", "soma_joint": "LeftLeg", "joint_index": 22, "modes": ["rotate"]},
    {"id": "left_knee", "label": "왼쪽 무릎", "soma_joint": "LeftShin", "joint_index": 23, "modes": ["move"]},
    {"id": "left_foot", "label": "왼발목", "soma_joint": "LeftFoot", "joint_index": 24, "modes": ["move", "rotate"]},
    {"id": "left_toe", "label": "왼발끝", "soma_joint": "LeftToeBase", "joint_index": 25, "modes": ["move", "rotate"]},
    {"id": "right_hip", "label": "오른쪽 고관절", "soma_joint": "RightLeg", "joint_index": 26, "modes": ["rotate"]},
    {"id": "right_knee", "label": "오른쪽 무릎", "soma_joint": "RightShin", "joint_index": 27, "modes": ["move"]},
    {"id": "right_foot", "label": "오른발목", "soma_joint": "RightFoot", "joint_index": 28, "modes": ["move", "rotate"]},
    {"id": "right_toe", "label": "오른발끝", "soma_joint": "RightToeBase", "joint_index": 29, "modes": ["move", "rotate"]},
)
CONTROL_BY_ID = {control["id"]: control for control in CONTROLS}


@dataclass(frozen=True, slots=True)
class PoseConstraint:
    """One named control's transform in a single-frame pose."""

    position: tuple[float, float, float] | None = None
    rotation_xyzw: tuple[float, float, float, float] | None = None
    space: str = "character"
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class PoseEdit:
    """Auditable change applied to a pose asset."""

    revision: int
    instruction: str
    summary: str
    changed_controls: tuple[str, ...]
    before: Mapping[str, PoseConstraint]
    after: Mapping[str, PoseConstraint]
    created_at: str
    actor: str = "llm"


@dataclass(frozen=True, slots=True)
class PoseAsset:
    """Reusable single-frame pose. It deliberately has no timeline frame."""

    id: str
    name: str
    controls: Mapping[str, PoseConstraint] = field(default_factory=dict)
    revision: int = 0
    edits: tuple[PoseEdit, ...] = ()
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class PosePlacement:
    """Immutable snapshot of a pose asset placed on an animation timeline."""

    frame: int
    pose_id: str
    pose_name: str
    controls: Mapping[str, PoseConstraint] = field(default_factory=dict)

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
        "structures": {
            "pose_asset": {
                "required": ["schema_version", "id", "name", "controls", "revision", "edits"],
                "timeline_fields": [],
                "description": "Reusable single-frame pose with no frame or duration.",
            },
            "pose_placement": {
                "required": ["frame", "pose_id", "pose_name", "controls"],
                "description": "Timeline placement containing an immutable pose snapshot.",
            },
        },
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


def _normalize_controls(controls: object, path: str = "controls") -> dict:
    if not isinstance(controls, dict):
        raise KeyposeValidationError(f"{path} must be an object")

    normalized_controls = {}
    for control_id, constraint in controls.items():
        control_path = f"{path}.{control_id}"
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
    return normalized_controls


def validate_pose_asset(pose: dict, *, require_id: bool = True) -> dict:
    """Validate the JSON representation of a reusable, frame-free pose asset."""
    if not isinstance(pose, dict):
        raise KeyposeValidationError("pose asset must be an object")
    if pose.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise KeyposeValidationError(f"schema_version must be {SCHEMA_VERSION}")
    pose_id = pose.get("id", "")
    if require_id and (not isinstance(pose_id, str) or not pose_id.strip() or len(pose_id) > 128):
        raise KeyposeValidationError("pose asset id must be a non-empty string of at most 128 characters")
    if not require_id and (not isinstance(pose_id, str) or len(pose_id) > 128):
        raise KeyposeValidationError("pose asset id must be a string of at most 128 characters")
    name = pose.get("name", "")
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise KeyposeValidationError("pose asset name must be a non-empty string of at most 80 characters")
    revision = pose.get("revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise KeyposeValidationError("pose asset revision must be a non-negative integer")
    edits = pose.get("edits", [])
    if not isinstance(edits, list) or len(edits) > 100:
        raise KeyposeValidationError("pose asset edits must be an array of at most 100 items")
    normalized_edits = []
    previous_revision = 0
    for index, edit in enumerate(edits):
        edit_path = f"pose.edits[{index}]"
        if not isinstance(edit, dict):
            raise KeyposeValidationError(f"{edit_path} must be an object")
        edit_revision = edit.get("revision")
        if isinstance(edit_revision, bool) or not isinstance(edit_revision, int) or edit_revision <= previous_revision:
            raise KeyposeValidationError(f"{edit_path}.revision must increase")
        instruction = edit.get("instruction", "")
        summary = edit.get("summary", "")
        created_at = edit.get("created_at", "")
        actor = edit.get("actor", "llm")
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 2000:
            raise KeyposeValidationError(f"{edit_path}.instruction is invalid")
        if not isinstance(summary, str) or len(summary) > 500:
            raise KeyposeValidationError(f"{edit_path}.summary is invalid")
        if not isinstance(created_at, str) or not created_at or len(created_at) > 64:
            raise KeyposeValidationError(f"{edit_path}.created_at is invalid")
        if actor not in ("llm", "manual"):
            raise KeyposeValidationError(f"{edit_path}.actor is invalid")
        before = _normalize_controls(edit.get("before", {}), f"{edit_path}.before")
        after = _normalize_controls(edit.get("after", {}), f"{edit_path}.after")
        changed_controls = edit.get("changed_controls")
        if not isinstance(changed_controls, list) or any(item not in CONTROL_BY_ID for item in changed_controls):
            raise KeyposeValidationError(f"{edit_path}.changed_controls is invalid")
        expected = sorted(set(before) | set(after))
        if sorted(set(changed_controls)) != expected:
            raise KeyposeValidationError(f"{edit_path}.changed_controls must match before/after controls")
        normalized_edits.append({
            "revision": edit_revision,
            "instruction": instruction.strip(),
            "summary": summary,
            "changed_controls": expected,
            "before": before,
            "after": after,
            "created_at": created_at,
            "actor": actor,
        })
        previous_revision = edit_revision
    if normalized_edits and revision != normalized_edits[-1]["revision"]:
        raise KeyposeValidationError("pose asset revision must match the latest edit")
    return {
        "schema_version": SCHEMA_VERSION,
        "id": pose_id.strip(),
        "name": name.strip(),
        "controls": _normalize_controls(pose.get("controls"), "pose.controls"),
        "revision": revision,
        "edits": normalized_edits,
    }


def validate_pose_placement(placement: dict, frame_count: int | None = None) -> dict:
    """Validate a pose snapshot placed at one animation frame."""
    if not isinstance(placement, dict):
        raise KeyposeValidationError("pose placement must be an object")
    frame = placement.get("frame")
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise KeyposeValidationError("pose placement frame must be a non-negative integer")
    if frame_count is not None and frame >= frame_count:
        raise KeyposeValidationError("pose placement frame must be less than frame_count")
    pose_id = placement.get("pose_id")
    if not isinstance(pose_id, str) or not pose_id.strip() or len(pose_id) > 128:
        raise KeyposeValidationError("pose placement pose_id must be a non-empty string")
    pose_name = placement.get("pose_name", "")
    if not isinstance(pose_name, str) or len(pose_name) > 80:
        raise KeyposeValidationError("pose placement pose_name must be a string of at most 80 characters")
    return {
        "frame": frame,
        "pose_id": pose_id.strip(),
        "pose_name": pose_name,
        "controls": _normalize_controls(placement.get("controls"), "placement.controls"),
    }


def placements_to_keypose_document(placements: list[dict], frame_count: int | None = None) -> dict:
    """Build the legacy runtime keypose document from explicit timeline placements."""
    if not isinstance(placements, list):
        raise KeyposeValidationError("pose placements must be an array")
    keyposes = []
    for placement in placements:
        normalized = validate_pose_placement(placement, frame_count=frame_count)
        keyposes.append({
            "frame": normalized["frame"],
            "label": normalized["pose_name"],
            "controls": normalized["controls"],
        })
    return validate_keypose_document({"schema_version": SCHEMA_VERSION, "keyposes": keyposes}, frame_count)


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
        normalized_controls = _normalize_controls(keypose.get("controls", {}), f"{path}.controls")

        normalized["keyposes"].append({"frame": frame, "label": label, "controls": normalized_controls})

    normalized["keyposes"].sort(key=lambda item: item["frame"])
    return normalized
