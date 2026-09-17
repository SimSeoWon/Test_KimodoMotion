"""Background LLM pose agent hosted by the kimodo-motion WebUI daemon."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:
    from keypose import CONTROLS, SCHEMA_VERSION, KeyposeValidationError, validate_pose_asset
except ModuleNotFoundError:
    from webui.keypose import CONTROLS, SCHEMA_VERSION, KeyposeValidationError, validate_pose_asset


CONTROL_IDS = tuple(item["id"] for item in CONTROLS)
POSITION_CONTROL_IDS = {"pelvis", "left_hand", "right_hand", "left_elbow", "right_elbow", "left_knee", "right_knee", "left_foot", "right_foot", "left_toe", "right_toe"}
POSITION_ONLY_CONTROL_IDS = {"left_elbow", "right_elbow", "left_knee", "right_knee"}
ROTATION_PROPERTIES = {
        "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "rotation_xyzw": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
        "space": {"type": "string", "enum": ["world", "character", "local"]},
        "weight": {"type": "number", "minimum": 0, "maximum": 4},
}


def _transform_schema(control_id: str) -> dict:
    properties = dict(ROTATION_PROPERTIES)
    if control_id not in POSITION_CONTROL_IDS:
        properties.pop("position")
    if control_id in POSITION_ONLY_CONTROL_IDS:
        properties.pop("rotation_xyzw")
    required_options = [{"required": ["rotation_xyzw"]}]
    if control_id in POSITION_CONTROL_IDS:
        required_options.insert(0, {"required": ["position"]})
    if control_id in POSITION_ONLY_CONTROL_IDS:
        required_options = [{"required": ["position"]}]
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        "anyOf": required_options,
    }
POSE_RESULT_SCHEMA = {
    "$defs": {
        "position_only": _transform_schema("left_knee"),
        "rotation_only": _transform_schema("left_hip"),
        "position_rotation": _transform_schema("left_foot"),
    },
    "type": "object",
    "properties": {
        "name": {"type": "string", "maxLength": 80},
        "summary": {"type": "string", "maxLength": 500},
        "controls": {
            "type": "object",
            "properties": {
                control_id: {"$ref": (
                    "#/$defs/position_only" if control_id in POSITION_ONLY_CONTROL_IDS
                    else "#/$defs/position_rotation" if control_id in POSITION_CONTROL_IDS
                    else "#/$defs/rotation_only"
                )}
                for control_id in CONTROL_IDS
            },
            "additionalProperties": False,
        },
    },
    "required": ["name", "summary", "controls"],
    "additionalProperties": False,
}


def apply_pose_recipe(instruction: str, result: dict, snapshot: dict) -> dict:
    """Apply deterministic anatomical constraints for named poses."""
    lowered = instruction.casefold()
    if "마보" not in lowered and "horse stance" not in lowered:
        return result
    try:
        pelvis = snapshot["pelvis"]["position"]
        rest_pelvis = snapshot["pelvis"].get("rest_position", pelvis)
        left_foot_state = snapshot["left_foot"]
        right_foot_state = snapshot["right_foot"]
        left_foot = left_foot_state["position"]
        right_foot = right_foot_state["position"]
        rest_left_foot = left_foot_state.get("rest_position", left_foot)
        rest_right_foot = right_foot_state.get("rest_position", right_foot)
        left_toe_state = snapshot["left_toe"]
        right_toe_state = snapshot["right_toe"]
        rest_left_toe = left_toe_state.get("rest_position", left_toe_state["position"])
        rest_right_toe = right_toe_state.get("rest_position", right_toe_state["position"])
        rest_left_knee = snapshot["left_knee"].get("rest_position", snapshot["left_knee"]["position"])
        rest_right_knee = snapshot["right_knee"].get("rest_position", snapshot["right_knee"]["position"])
        def distance(a, b):
            return sum((a[index] - b[index]) ** 2 for index in range(3)) ** 0.5
        leg_length = max(
            distance(rest_pelvis, rest_left_knee) + distance(rest_left_knee, rest_left_foot),
            distance(rest_pelvis, rest_right_knee) + distance(rest_right_knee, rest_right_foot),
        )
        if leg_length < 1e-4:
            return result
        ground_y = (rest_left_foot[1] + rest_right_foot[1]) * 0.5
        pelvis_x = rest_pelvis[0]
        current_half_width = abs(rest_left_foot[0] - rest_right_foot[0]) * 0.5
        half_width = max(current_half_width, leg_length * 0.38)
        target_pelvis_y = max(
            ground_y + leg_length * 0.68,
            rest_pelvis[1] - leg_length * 0.20,
        )
        left_sign = 1.0 if rest_left_foot[0] >= rest_right_foot[0] else -1.0
        controls = dict(result.get("controls") or {})
        controls["pelvis"] = {
            "position": [pelvis_x, target_pelvis_y, rest_pelvis[2]],
            "space": "world", "weight": 1.0,
        }
        left_foot_target = [pelvis_x + left_sign * half_width, rest_left_foot[1], rest_left_foot[2]]
        right_foot_target = [pelvis_x - left_sign * half_width, rest_right_foot[1], rest_right_foot[2]]
        controls["left_foot"] = {
            "position": left_foot_target,
            "space": "world", "weight": 1.0,
        }
        controls["right_foot"] = {
            "position": right_foot_target,
            "space": "world", "weight": 1.0,
        }
        controls["left_toe"] = {
            "position": [rest_left_toe[0] + left_foot_target[0] - rest_left_foot[0], rest_left_toe[1], rest_left_toe[2]],
            "space": "world", "weight": 1.0,
        }
        controls["right_toe"] = {
            "position": [rest_right_toe[0] + right_foot_target[0] - rest_right_foot[0], rest_right_toe[1], rest_right_toe[2]],
            "space": "world", "weight": 1.0,
        }
        controls.pop("left_knee", None)
        controls.pop("right_knee", None)
        return {
            **result,
            "name": result.get("name") or "마보 자세",
            "summary": f"{result.get('summary', '').strip()} · rest 기준 마보 보정(발 간격 {half_width * 2:.2f}m, 골반 하강 {rest_pelvis[1] - target_pelvis_y:.2f}m)".strip(" ·"),
            "controls": controls,
        }
    except (KeyError, TypeError, ValueError):
        return result


def _extract_structured_output(raw: str) -> dict:
    payload = json.loads(raw)
    if isinstance(payload, dict) and isinstance(payload.get("structured_output"), dict):
        return payload["structured_output"]
    if isinstance(payload, dict) and isinstance(payload.get("result"), str):
        return json.loads(payload["result"])
    if isinstance(payload, dict) and {"name", "controls"}.issubset(payload):
        return payload
    raise ValueError("LLM response did not contain structured pose output")


def run_claude_pose_agent(instruction: str, pose: dict, snapshot: dict) -> dict:
    executable = shutil.which("claude") or shutil.which("claude.exe")
    if not executable:
        raise RuntimeError("claude CLI를 찾을 수 없습니다.")
    llm_pose = {"name": pose.get("name", ""), "controls": pose.get("controls", {})}
    llm_snapshot = {
        control_id: {
            key: value for key, value in state.items()
            if key in ("position", "rotation_xyzw", "rest_position", "rest_rotation_xyzw")
        }
        for control_id, state in snapshot.items()
    }
    prompt = f"""You are a character pose sub-agent. Modify a single-frame pose from the Korean or English instruction.
Return only data matching the supplied JSON schema. Never add unknown control names.
The full snapshot contains current world-space transforms for reference. The current pose controls are the
constraints already authored by the user. Preserve those constraints unless the instruction changes them,
and return the complete desired constraint set. Prefer modest, anatomically plausible changes. Quaternion
order is x,y,z,w. Do not change bone lengths. Keep feet near their current ground height unless asked.
The skeleton is a rooted FK tree: descendant world transforms are parent_world * local_transform.
Never translate chest, head, shoulders, or hips. Use rotations for articulated joints. Positions on hands,
elbows, knees, ankles, and toes are IK targets; the runtime will reach them by rotating ancestors.
The pelvis/Hips control is the skeleton root. Translating it moves the entire character and every
descendant together. Do not counteract a pelvis translation with limb targets unless the instruction
explicitly asks to plant or pin that hand or foot in world space.
LeftLeg/rightLeg are separate hip rotation controls. LeftFoot/rightFoot are ankle targets, while
LeftToeBase/rightToeBase are separate ground-contact targets. Keep the matching toe at ground height and
in front of the ankle. Do not impose a hard knee-versus-ankle position rule: solve joint angles instead.
Use conservative human ranges: hip flexion 120°, extension 15°, abduction 35°, adduction 15°; knee
flexion 0–135° with no hyperextension; ankle dorsiflexion 20°, plantarflexion 50°, side tilt ±15°.
For a horse stance, spread the legs with the ankle positions. Knee positions are bend hints: keep each
knee laterally near the hip-to-ankle line and bend forward without valgus collapse. The runtime solves
each whole leg once and enforces joint-angle limits.

Instruction:
{instruction}

Current pose asset:
{json.dumps(llm_pose, ensure_ascii=False, separators=(',', ':'))}

Full control snapshot:
{json.dumps(llm_snapshot, ensure_ascii=False, separators=(',', ':'))}
"""
    command = [
        executable,
        "--print",
        "--output-format", "json",
        "--json-schema", json.dumps(POSE_RESULT_SCHEMA, separators=(",", ":")),
        "--tools", "",
        "--permission-mode", "dontAsk",
        "--no-session-persistence",
    ]
    model = os.environ.get("KIMODO_POSE_AGENT_MODEL", "haiku").strip()
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("포즈 LLM이 90초 안에 응답하지 않았습니다. 잠시 후 다시 시도하세요.") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"포즈 LLM 실행 실패: {detail[-1000:]}")
    return _extract_structured_output(completed.stdout)


class PoseAgentDaemon:
    def __init__(
        self,
        runner: Callable[[str, dict, dict], dict] = run_claude_pose_agent,
    ):
        self._runner = runner
        self._lock = threading.Lock()
        self._revision = 0
        self._state = {
            "job_id": None,
            "status": "idle",
            "instruction": "",
            "summary": "",
            "pose": None,
            "error": None,
        }

    def state(self) -> dict:
        with self._lock:
            return {"revision": self._revision, **deepcopy(self._state)}

    def submit(self, instruction: str, pose: dict, snapshot: dict) -> dict:
        instruction = instruction.strip() if isinstance(instruction, str) else ""
        if not instruction:
            raise KeyposeValidationError("포즈 명령을 입력하세요.")
        if not isinstance(snapshot, dict) or not snapshot:
            raise KeyposeValidationError("현재 전신 포즈 스냅샷이 필요합니다.")
        normalized_pose = validate_pose_asset(pose)
        with self._lock:
            if self._state["status"] in ("queued", "running"):
                raise KeyposeValidationError("이미 포즈 에이전트가 작업 중입니다.")
            job_id = str(uuid.uuid4())
            self._revision += 1
            self._state = {
                "job_id": job_id,
                "status": "queued",
                "instruction": instruction,
                "summary": "",
                "pose": None,
                "error": None,
            }
        threading.Thread(
            target=self._run_job,
            args=(job_id, instruction, normalized_pose, deepcopy(snapshot)),
            name=f"pose-agent-{job_id[:8]}",
            daemon=True,
        ).start()
        return self.state()

    def _run_job(self, job_id: str, instruction: str, pose: dict, snapshot: dict) -> None:
        with self._lock:
            if self._state["job_id"] != job_id:
                return
            self._state["status"] = "running"
            self._revision += 1
        try:
            result = apply_pose_recipe(instruction, self._runner(instruction, pose, snapshot), snapshot)
            normalized = validate_pose_asset({
                "schema_version": SCHEMA_VERSION,
                "id": pose["id"],
                "name": result.get("name") or pose["name"],
                "controls": result.get("controls"),
                "revision": pose.get("revision", 0),
                "edits": pose.get("edits", []),
            })
            changed = sorted(
                control_id for control_id in set(pose["controls"]) | set(normalized["controls"])
                if pose["controls"].get(control_id) != normalized["controls"].get(control_id)
            )
            next_revision = pose.get("revision", 0) + 1
            edit = {
                "revision": next_revision,
                "instruction": instruction,
                "summary": str(result.get("summary", ""))[:500],
                "changed_controls": changed,
                "before": {control_id: pose["controls"][control_id] for control_id in changed if control_id in pose["controls"]},
                "after": {control_id: normalized["controls"][control_id] for control_id in changed if control_id in normalized["controls"]},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "actor": "llm",
            }
            normalized = validate_pose_asset({
                **normalized,
                "revision": next_revision,
                "edits": [*pose.get("edits", []), edit][-100:],
            })
            with self._lock:
                self._state.update({
                    "status": "complete",
                    "summary": str(result.get("summary", ""))[:500],
                    "pose": normalized,
                    "error": None,
                })
                self._revision += 1
        except Exception as exc:
            with self._lock:
                self._state.update({"status": "failed", "error": str(exc), "pose": None})
                self._revision += 1


POSE_AGENT = PoseAgentDaemon()
