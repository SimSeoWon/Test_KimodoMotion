#!/usr/bin/env python3
"""Dependency-free stdio MCP bridge for the local Kimodo key-pose store."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "webui"))

from keypose import KeyposeValidationError, get_keypose_schema  # noqa: E402
from keypose_agent import STORE  # noqa: E402


TOOLS = [
    {"name": "get_control_schema", "description": "List Kimodo posing controls, joints, coordinates, and gizmo modes.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_pose_state", "description": "Read the current key-pose document and revision.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_keyposes", "description": "List all current key poses.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "create_keypose", "description": "Create or label a key pose at a frame.", "inputSchema": {"type": "object", "properties": {"frame": {"type": "integer", "minimum": 0}, "label": {"type": "string"}}, "required": ["frame"]}},
    {"name": "delete_keypose", "description": "Delete a key pose.", "inputSchema": {"type": "object", "properties": {"frame": {"type": "integer", "minimum": 0}}, "required": ["frame"]}},
    {"name": "move_control", "description": "Set or offset a control world position in meters.", "inputSchema": {"type": "object", "properties": {"frame": {"type": "integer", "minimum": 0}, "control": {"type": "string"}, "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}, "relative": {"type": "boolean"}, "weight": {"type": "number", "minimum": 0, "maximum": 4}}, "required": ["frame", "control", "position"]}},
    {"name": "rotate_control", "description": "Set a control world rotation as an xyzw quaternion.", "inputSchema": {"type": "object", "properties": {"frame": {"type": "integer", "minimum": 0}, "control": {"type": "string"}, "rotation_xyzw": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}, "weight": {"type": "number", "minimum": 0, "maximum": 4}}, "required": ["frame", "control", "rotation_xyzw"]}},
    {"name": "set_constraint", "description": "Set position and/or rotation for one control.", "inputSchema": {"type": "object", "properties": {"frame": {"type": "integer", "minimum": 0}, "control": {"type": "string"}, "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}, "rotation_xyzw": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}, "weight": {"type": "number", "minimum": 0, "maximum": 4}}, "required": ["frame", "control"]}},
    {"name": "copy_keypose", "description": "Copy a key pose to another frame.", "inputSchema": {"type": "object", "properties": {"source_frame": {"type": "integer", "minimum": 0}, "frame": {"type": "integer", "minimum": 0}, "label": {"type": "string"}}, "required": ["source_frame", "frame"]}},
    {"name": "undo_pose_edit", "description": "Undo the most recent AI/API pose edit.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "redo_pose_edit", "description": "Redo the most recently undone pose edit.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_pose_presets", "description": "List reusable pose presets.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "save_pose_preset", "description": "Save one existing key pose as a reusable preset.", "inputSchema": {"type": "object", "properties": {"frame": {"type": "integer", "minimum": 0}, "name": {"type": "string"}}, "required": ["frame", "name"]}},
    {"name": "apply_pose_preset", "description": "Place a reusable pose preset at a timeline frame.", "inputSchema": {"type": "object", "properties": {"frame": {"type": "integer", "minimum": 0}, "name": {"type": "string"}}, "required": ["frame", "name"]}},
]

PRESET_FILE = REPO_ROOT / "webui" / "keypose_presets.json"


def load_presets():
    try:
        value = json.loads(PRESET_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def save_presets(items):
    PRESET_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def result(payload, is_error=False):
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": is_error}


def dispatch(message):
    method = message.get("method")
    if method == "initialize":
        return {"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "kimodo-keypose", "version": "0.1.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = message.get("params", {})
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            if name == "get_control_schema":
                return result(get_keypose_schema())
            if name == "list_pose_presets":
                return result({"items": load_presets()})
            if name == "save_pose_preset":
                state = STORE.state()
                keypose = next((item for item in state["document"]["keyposes"] if item["frame"] == arguments.get("frame")), None)
                preset_name = (arguments.get("name") or "").strip()
                if keypose is None or not preset_name:
                    raise KeyposeValidationError("existing frame and preset name are required")
                items = [item for item in load_presets() if item.get("name") != preset_name]
                items.append({"name": preset_name, "controls": keypose["controls"]})
                items.sort(key=lambda item: item["name"])
                save_presets(items)
                return result({"items": items})
            if name == "apply_pose_preset":
                preset_name = (arguments.get("name") or "").strip()
                preset = next((item for item in load_presets() if item.get("name") == preset_name), None)
                if preset is None:
                    raise KeyposeValidationError("pose preset does not exist")
                state = STORE.state()["document"]
                frame = arguments.get("frame")
                state["keyposes"] = [item for item in state["keyposes"] if item["frame"] != frame]
                state["keyposes"].append({"frame": frame, "label": preset_name, "controls": preset["controls"]})
                return result(STORE.replace(state))
            return result(STORE.command(name, arguments))
        except (KeyposeValidationError, ValueError, TypeError) as exc:
            return result({"error": str(exc)}, True)
    raise ValueError(f"unsupported MCP method: {method}")


def main():
    for line in sys.stdin:
        try:
            message = json.loads(line.lstrip("\ufeff"))
            if "id" not in message:  # Notification.
                continue
            response = {"jsonrpc": "2.0", "id": message["id"], "result": dispatch(message)}
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": message.get("id") if "message" in locals() else None, "error": {"code": -32603, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
