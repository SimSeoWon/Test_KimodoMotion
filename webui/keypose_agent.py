"""Persistent, transactional key-pose commands shared by HTTP and MCP."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path

try:
    from keypose import CONTROL_BY_ID, SCHEMA_VERSION, KeyposeValidationError, validate_keypose_document
except ModuleNotFoundError:
    from webui.keypose import CONTROL_BY_ID, SCHEMA_VERSION, KeyposeValidationError, validate_keypose_document


STATE_FILE = Path(__file__).resolve().parent / "keypose_agent_state.json"


class KeyposeStore:
    def __init__(self, path: Path = STATE_FILE):
        self.path = path
        self.lock = threading.Lock()
        self.undo_stack = []
        self.redo_stack = []
        self.revision = 0
        self.document = {"schema_version": SCHEMA_VERSION, "keyposes": []}
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.document = validate_keypose_document(payload.get("document", payload))
                self.revision = int(payload.get("revision", 0)) if isinstance(payload, dict) else 0
            except Exception:
                pass

    def _save(self):
        self.path.write_text(json.dumps({"revision": self.revision, "document": self.document}, ensure_ascii=False, indent=2), encoding="utf-8")

    def state(self):
        with self.lock:
            return {"revision": self.revision, "document": deepcopy(self.document)}

    def replace(self, document: dict, frame_count: int | None = None):
        with self.lock:
            normalized = validate_keypose_document(document, frame_count=frame_count)
            before = deepcopy(self.document)
            self.document = normalized
            self._commit(before)
            return {"changed": self.document != before, "revision": self.revision, "document": deepcopy(self.document)}

    def _find(self, frame: int):
        return next((item for item in self.document["keyposes"] if item["frame"] == frame), None)

    def _commit(self, before):
        self.document = validate_keypose_document(self.document)
        self.undo_stack.append(before)
        self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()
        self.revision += 1
        self._save()

    def command(self, name: str, arguments: dict | None = None):
        arguments = arguments or {}
        with self.lock:
            if name in ("get_pose_state", "list_keyposes"):
                return {"revision": self.revision, "document": deepcopy(self.document)}
            if name == "undo_pose_edit":
                if not self.undo_stack:
                    return {"changed": False, "revision": self.revision, "document": deepcopy(self.document)}
                self.redo_stack.append(deepcopy(self.document))
                self.document = self.undo_stack.pop()
                self.revision += 1
                self._save()
                return {"changed": True, "revision": self.revision, "document": deepcopy(self.document)}
            if name == "redo_pose_edit":
                if not self.redo_stack:
                    return {"changed": False, "revision": self.revision, "document": deepcopy(self.document)}
                self.undo_stack.append(deepcopy(self.document))
                self.document = self.redo_stack.pop()
                self.revision += 1
                self._save()
                return {"changed": True, "revision": self.revision, "document": deepcopy(self.document)}

            before = deepcopy(self.document)
            frame = arguments.get("frame")
            if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
                raise KeyposeValidationError("frame must be a non-negative integer")
            keypose = self._find(frame)

            if name == "create_keypose":
                if keypose is None:
                    self.document["keyposes"].append({"frame": frame, "label": arguments.get("label", ""), "controls": {}})
                elif "label" in arguments:
                    keypose["label"] = arguments["label"]
            elif name == "delete_keypose":
                if keypose is not None:
                    self.document["keyposes"].remove(keypose)
            elif name == "copy_keypose":
                source_frame = arguments.get("source_frame")
                source = self._find(source_frame)
                if source is None:
                    raise KeyposeValidationError("source keypose does not exist")
                if keypose is not None:
                    self.document["keyposes"].remove(keypose)
                copy = deepcopy(source)
                copy["frame"] = frame
                copy["label"] = arguments.get("label", copy.get("label", ""))
                self.document["keyposes"].append(copy)
            elif name in ("set_constraint", "move_control", "rotate_control"):
                control = arguments.get("control")
                if control not in CONTROL_BY_ID:
                    raise KeyposeValidationError(f"unknown control: {control}")
                if keypose is None:
                    keypose = {"frame": frame, "label": arguments.get("label", ""), "controls": {}}
                    self.document["keyposes"].append(keypose)
                current = keypose["controls"].setdefault(control, {"space": arguments.get("space", "world"), "weight": float(arguments.get("weight", 1.0))})
                if name in ("set_constraint", "move_control") and "position" in arguments:
                    position = [float(value) for value in arguments["position"]]
                    if arguments.get("relative") and "position" in current:
                        position = [a + b for a, b in zip(current["position"], position)]
                    current["position"] = position
                if name in ("set_constraint", "rotate_control") and "rotation_xyzw" in arguments:
                    current["rotation_xyzw"] = [float(value) for value in arguments["rotation_xyzw"]]
                current["space"] = arguments.get("space", current.get("space", "world"))
                current["weight"] = float(arguments.get("weight", current.get("weight", 1.0)))
            else:
                raise KeyposeValidationError(f"unsupported pose command: {name}")
            self._commit(before)
            return {"changed": self.document != before, "revision": self.revision, "document": deepcopy(self.document)}


STORE = KeyposeStore()
