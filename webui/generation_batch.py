"""Observable state for the single active generation batch."""

import threading
from copy import deepcopy


class GenerationBatchState:
    def __init__(self):
        self.lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.data = {"status": "idle", "items": [], "count": 0, "completed": 0}

    def start(self, batch_id, count, base_seed):
        with self.lock:
            self.cancel_event.clear()
            self.data = {"batch_id": batch_id, "status": "running", "stage": "preparing",
                         "count": count, "completed": 0, "current_index": 1,
                         "base_seed": base_seed, "current_seed": base_seed, "items": []}

    def update(self, **values):
        with self.lock:
            self.data.update(values)

    def completed(self, meta):
        with self.lock:
            self.data["items"].append(deepcopy(meta))
            self.data["completed"] = len(self.data["items"])

    def request_cancel(self):
        with self.lock:
            if self.data["status"] != "running":
                return False
            self.cancel_event.set()
            self.data["stage"] = "cancelling"
            return True

    def finish(self, status, error=None):
        self.update(status=status, stage=status, error=error)
        return self.snapshot()

    def snapshot(self):
        with self.lock:
            return deepcopy(self.data)
