"""Persistent per-execution JSONL diagnostics for pose and motion jobs."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path


LOG_ROOT = Path(__file__).resolve().parent / "logs"
_allocation_lock = threading.Lock()
_sequence_pattern = re.compile(r"^(\d{4})_")


class DiagnosticRun:
    def __init__(self, kind: str, request: dict):
        now = datetime.now().astimezone()
        day_dir = LOG_ROOT / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        with _allocation_lock:
            existing = []
            for path in day_dir.glob("*.jsonl"):
                match = _sequence_pattern.match(path.name)
                if match:
                    existing.append(int(match.group(1)))
            self.number = max(existing, default=0) + 1
            self.id = f"{now.strftime('%Y%m%d')}-{self.number:04d}-{uuid.uuid4().hex[:8]}"
            self.path = day_dir / f"{self.number:04d}_{kind}_{self.id[-8:]}.jsonl"
            self.path.touch(exist_ok=False)
        self.kind = kind
        self._lock = threading.Lock()
        self.event("started", request=request)

    def event(self, event: str, **data) -> None:
        record = {
            "time": datetime.now().astimezone().isoformat(),
            "execution_number": self.number,
            "execution_id": self.id,
            "kind": self.kind,
            "event": event,
            **data,
        }
        encoded = json.dumps(record, ensure_ascii=False, default=str, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
