"""Persistent per-execution JSONL diagnostics for pose and motion jobs."""

from __future__ import annotations

import json
import re
import sys
import threading
import uuid
import atexit
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_ROOT = REPO_ROOT / ".codex-local" / "logs" / "webui"
_allocation_lock = threading.Lock()
_legacy_sequence_pattern = re.compile(r"^(\d{4})_")
_named_sequence_pattern = re.compile(r"_run-(\d{4})_")


def _allocate_path(kind: str, suffix: str) -> tuple[datetime, int, Path]:
    now = datetime.now().astimezone()
    day_dir = LOG_ROOT / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    with _allocation_lock:
        existing = []
        for path in day_dir.iterdir():
            match = _named_sequence_pattern.search(path.name) or _legacy_sequence_pattern.match(path.name)
            if match:
                existing.append(int(match.group(1)))
        number = max(existing, default=0) + 1
        stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        path = day_dir / f"{stamp}_run-{number:04d}_{kind}_{uuid.uuid4().hex[:8]}.{suffix}"
        path.touch(exist_ok=False)
    return now, number, path


class _TimestampedTee:
    def __init__(self, original, path: Path, channel: str, lock: threading.Lock):
        self.original = original
        self.path = path
        self.channel = channel
        self.lock = lock
        self.pending = ""

    def write(self, text: str) -> int:
        self.original.write(text)
        self.original.flush()
        self.pending += text
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self._append(line)
        return len(text)

    def flush(self) -> None:
        self.original.flush()
        if self.pending:
            self._append(self.pending)
            self.pending = ""

    def _append(self, line: str) -> None:
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        with self.lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(f"[{timestamp}] [{self.channel}] {line}\n")

    def isatty(self) -> bool:
        return self.original.isatty()

    @property
    def encoding(self):
        return self.original.encoding


class ProcessRunLog:
    """Tee a complete process lifetime to a timestamped, numbered text log."""

    def __init__(self, kind: str):
        self.started_at, self.number, self.path = _allocate_path(kind, "log")
        self._lock = threading.Lock()
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._closed = False

    def install(self) -> None:
        sys.stdout = _TimestampedTee(self._stdout, self.path, "stdout", self._lock)
        sys.stderr = _TimestampedTee(self._stderr, self.path, "stderr", self._lock)
        atexit.register(self.close)
        print(f"실행 로그: {self.path}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        sys.stdout.flush()
        sys.stderr.flush()


class DiagnosticRun:
    def __init__(self, kind: str, request: dict):
        now, self.number, self.path = _allocate_path(kind, "jsonl")
        self.id = f"{now.strftime('%Y%m%d')}-{self.number:04d}-{self.path.stem[-8:]}"
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
