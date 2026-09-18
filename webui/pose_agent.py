"""Background LLM pose agent hosted by the kimodo-motion WebUI daemon."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:
    from keypose import CONTROLS, SCHEMA_VERSION, KeyposeValidationError, validate_pose_asset
    from diagnostic_log import DiagnosticRun
except ModuleNotFoundError:
    from webui.keypose import CONTROLS, SCHEMA_VERSION, KeyposeValidationError, validate_pose_asset
    from webui.diagnostic_log import DiagnosticRun


CONTROL_IDS = tuple(item["id"] for item in CONTROLS)
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
DEFAULT_POSE_AGENT_CONFIG = {
    "total_timeout_seconds": 300,
    "idle_timeout_seconds": 45,
    "max_attempts": 1,
}
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


def load_pose_agent_config() -> dict:
    """Read bounded timeout settings for every request, without a server restart."""
    config = dict(DEFAULT_POSE_AGENT_CONFIG)
    try:
        payload = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        requested = payload.get("pose_agent", {}) if isinstance(payload, dict) else {}
        if isinstance(requested, dict):
            config.update({key: requested[key] for key in config if key in requested})
    except (OSError, json.JSONDecodeError):
        pass
    bounds = {
        "total_timeout_seconds": (30, 1800),
        "idle_timeout_seconds": (5, 300),
        "max_attempts": (1, 3),
    }
    for key, (minimum, maximum) in bounds.items():
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            config[key] = DEFAULT_POSE_AGENT_CONFIG[key]
        else:
            config[key] = int(max(minimum, min(maximum, value)))
    return config


def _extract_structured_output(raw: str) -> dict:
    payload = json.loads(raw)
    if isinstance(payload, dict) and isinstance(payload.get("structured_output"), dict):
        return payload["structured_output"]
    if isinstance(payload, dict) and isinstance(payload.get("result"), str):
        return json.loads(payload["result"])
    if isinstance(payload, dict) and {"name", "controls"}.issubset(payload):
        return payload
    raise ValueError("LLM response did not contain structured pose output")


def _run_pose_cli(command: list[str], cwd: Path, *, attempt_timeout: int = 50) -> subprocess.CompletedProcess:
    """Run the authenticated CLI with one retry for a stalled API turn.

    Claude CLI occasionally remains alive without producing a response even though
    the next request succeeds immediately. A single 90-second wait made that
    transient stall indistinguishable from a genuinely slow response. Two bounded
    attempts recover from the common stall while keeping a finite total wait.
    """
    last_timeout = None
    for _attempt in range(2):
        try:
            return subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=attempt_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            last_timeout = exc
    raise RuntimeError(
        f"포즈 LLM이 {attempt_timeout}초씩 두 번 응답하지 않았습니다. "
        "Claude CLI 연결 상태를 확인한 뒤 다시 시도하세요."
    ) from last_timeout


class PoseCliRuntime:
    """One long-lived Claude CLI process fed with stream-json user turns."""

    def __init__(self):
        self._process = None
        self._events = queue.Queue()
        self._lifecycle_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._event_log = deque(maxlen=30)
        self._active_diagnostic = None

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._process is not None and self._process.poll() is None:
                return
            executable = shutil.which("claude") or shutil.which("claude.exe")
            if not executable:
                raise RuntimeError("claude CLI를 찾을 수 없습니다.")
            command = [
                executable, "--print",
                "--input-format", "stream-json",
                "--output-format", "stream-json",
                "--verbose",
                "--json-schema", json.dumps(POSE_RESULT_SCHEMA, separators=(",", ":")),
                "--tools", "",
                "--permission-mode", "dontAsk",
                "--no-session-persistence",
            ]
            model = os.environ.get("KIMODO_POSE_AGENT_MODEL", "sonnet").strip()
            if not model or "haiku" in model.casefold():
                model = "sonnet"
            if model:
                command.extend(["--model", model])
            self._events = queue.Queue()
            self._process = subprocess.Popen(
                command,
                cwd=Path(__file__).resolve().parent.parent,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            threading.Thread(target=self._read_events, args=(self._process,), daemon=True).start()
            threading.Thread(target=self._read_stderr, args=(self._process,), daemon=True).start()

    def _read_events(self, process) -> None:
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                    summary = {
                        "time": datetime.now(timezone.utc).isoformat(),
                        "type": event.get("type", "unknown"),
                        "subtype": event.get("subtype"),
                        "attempt": event.get("attempt"),
                        "max_retries": event.get("max_retries"),
                    }
                    self._event_log.append(summary)
                    if self._active_diagnostic is not None:
                        self._active_diagnostic.event("claude_event", payload=event)
                except json.JSONDecodeError:
                    self._event_log.append({
                        "time": datetime.now(timezone.utc).isoformat(),
                        "type": "invalid_json",
                    })
                self._events.put(line)
        finally:
            self._events.put(None)

    def _read_stderr(self, process) -> None:
        for line in process.stderr:
            if self._active_diagnostic is not None:
                self._active_diagnostic.event("claude_stderr", text=line.rstrip())

    def stop(self) -> None:
        with self._lifecycle_lock:
            process = self._process
            self._process = None
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()

    def status(self) -> dict:
        process = self._process
        return {
            "pid": process.pid if process is not None and process.poll() is None else None,
            "running": process is not None and process.poll() is None,
            "events": list(self._event_log),
        }

    def request(self, prompt: str, *, diagnostic: DiagnosticRun | None = None) -> dict:
        with self._request_lock:
            config = load_pose_agent_config()
            self._active_diagnostic = diagnostic
            started = time.monotonic()
            if diagnostic is not None:
                diagnostic.event("claude_timeout_config", **config)
            for attempt in range(config["max_attempts"]):
                self.start()
                if diagnostic is not None:
                    diagnostic.event("claude_attempt", attempt=attempt + 1, pid=self._process.pid)
                message = {
                    "type": "user",
                    "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
                }
                try:
                    self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                    self._process.stdin.flush()
                except (BrokenPipeError, OSError, AttributeError):
                    self.stop()
                    if attempt + 1 < config["max_attempts"]:
                        continue
                    self._active_diagnostic = None
                    raise RuntimeError("대기 중인 포즈 LLM 프로세스에 명령을 전달하지 못했습니다.")
                total_deadline = time.monotonic() + config["total_timeout_seconds"]
                idle_deadline = time.monotonic() + config["idle_timeout_seconds"]
                timeout_reason = "total"
                while True:
                    now = time.monotonic()
                    deadline = min(total_deadline, idle_deadline)
                    remaining = deadline - now
                    if remaining <= 0:
                        timeout_reason = "total" if total_deadline <= idle_deadline else "idle"
                        break
                    try:
                        line = self._events.get(timeout=remaining)
                    except queue.Empty:
                        timeout_reason = "total" if total_deadline <= idle_deadline else "idle"
                        break
                    if line is None:
                        break
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    idle_deadline = time.monotonic() + config["idle_timeout_seconds"]
                    if event.get("type") != "result":
                        continue
                    if event.get("is_error"):
                        self._active_diagnostic = None
                        raise RuntimeError(f"포즈 LLM 실행 실패: {event.get('result') or event.get('subtype') or 'unknown error'}")
                    result = _extract_structured_output(json.dumps(event, ensure_ascii=False))
                    if diagnostic is not None:
                        diagnostic.event("claude_result", elapsed_seconds=round(time.monotonic() - started, 3), result=result)
                    self._active_diagnostic = None
                    return result
                self.stop()
                if diagnostic is not None:
                    diagnostic.event(
                        "claude_attempt_timeout",
                        attempt=attempt + 1,
                        reason=timeout_reason,
                        total_timeout_seconds=config["total_timeout_seconds"],
                        idle_timeout_seconds=config["idle_timeout_seconds"],
                    )
            self._active_diagnostic = None
            raise RuntimeError(
                f"포즈 LLM이 최대 {config['total_timeout_seconds']}초 안에 완료되지 않았거나 "
                f"{config['idle_timeout_seconds']}초 동안 이벤트를 보내지 않았습니다."
            )


POSE_CLI_RUNTIME = PoseCliRuntime()


def run_claude_pose_agent(instruction: str, pose: dict, snapshot: dict, *, diagnostic: DiagnosticRun | None = None) -> dict:
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
and return the complete desired constraint set. Apply the requested change at its stated magnitude instead
of weakening it toward the current pose. Quaternion order is x,y,z,w. Do not change bone lengths.
Never claim a distance, width multiplier, or angle in the summary unless the returned controls actually
produce it. Before returning, calculate the requested measurement from the output numbers and compare it
with the full snapshot. Preserve enough decimal precision for the requested change to be visible; merely
rounding an unchanged snapshot coordinate is not a pose edit.
The skeleton is a rooted FK tree: descendant world transforms are parent_world * local_transform.
Never translate chest, head, shoulders, or hips. Use rotations for articulated joints. Positions on hands,
elbows, knees, ankles, and toes are IK targets; the runtime will reach them by rotating ancestors.
The pelvis/Hips control is the skeleton root. Translating it moves the entire character and every
descendant together. Do not counteract a pelvis translation with limb targets unless the instruction
explicitly asks to plant or pin that hand or foot in world space.
LeftLeg/rightLeg are separate hip rotation controls. LeftFoot/rightFoot are ankle targets, while
LeftToeBase/rightToeBase are separate ground-contact targets. Keep the matching toe at ground height and
in front of the ankle. Do not impose a hard knee-versus-ankle position rule: solve joint angles instead.
When the instruction turns a leg or foot inward/outward, keep the required hip/ankle rotation controls
even when position targets are also present. Position and rotation express different requested properties.
For a toe direction target, calculate its horizontal direction from toe minus ankle, preserve the current
ankle-to-toe length, and verify that this vector has the requested yaw angle.
There is no separate heel or sole joint — LeftFoot/RightFoot is the whole rear/mid-foot plate from ankle
through heel, as one rigid unit; heel and sole are expressed through the ankle's own position and rotation,
never through the toe. A heel lift / tiptoe / releve ("뒤꿈치를 들어", "까치발") means: raise the ankle's Y
position while keeping the matching toe's position near its current ground height (the toe stays the
pivot), and rotate the ankle toward plantarflexion so the foot line follows. Flattening the sole against
the ground ("발바닥을 지면에 붙여", "평평하게") means: return the ankle's rotation toward its rest
orientation and its Y position to the toe's ground height, so the whole plate lies flat — not a toe change.
For a horse stance, spread the legs with the ankle positions. Knee positions are bend hints: keep each
knee laterally near the hip-to-ankle line and bend forward without valgus collapse. The runtime solves
each whole leg once.

Instruction:
{instruction}

Current pose asset:
{json.dumps(llm_pose, ensure_ascii=False, separators=(',', ':'))}

Full control snapshot:
{json.dumps(llm_snapshot, ensure_ascii=False, separators=(',', ':'))}
"""
    return POSE_CLI_RUNTIME.request(prompt, diagnostic=diagnostic)


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
            return {"revision": self._revision, **deepcopy(self._state), "runtime": POSE_CLI_RUNTIME.status()}

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
        diagnostic = DiagnosticRun("pose", {
            "job_id": job_id,
            "instruction": instruction,
            "pose": pose,
            "snapshot": snapshot,
        })
        started = time.monotonic()
        with self._lock:
            if self._state["job_id"] != job_id:
                return
            self._state["status"] = "running"
            self._revision += 1
        try:
            if self._runner is run_claude_pose_agent:
                runner_result = self._runner(instruction, pose, snapshot, diagnostic=diagnostic)
            else:
                runner_result = self._runner(instruction, pose, snapshot)
            diagnostic.event("runner_result", result=runner_result)
            # Position carries stance/contact while rotation carries orientation.
            # Keep both when the model returns both; deleting hip rotation here
            # previously erased requested turnout while leaving only a tiny move.
            result = runner_result
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
            diagnostic.event(
                "completed",
                elapsed_seconds=round(time.monotonic() - started, 3),
                changed_controls=changed,
                pose=normalized,
            )
            with self._lock:
                self._state.update({
                    "status": "complete",
                    "summary": str(result.get("summary", ""))[:500],
                    "pose": normalized,
                    "error": None,
                })
                self._revision += 1
        except Exception as exc:
            diagnostic.event(
                "failed",
                elapsed_seconds=round(time.monotonic() - started, 3),
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            with self._lock:
                self._state.update({"status": "failed", "error": str(exc), "pose": None})
                self._revision += 1


POSE_AGENT = PoseAgentDaemon()
