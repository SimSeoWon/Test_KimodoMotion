import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

import diagnostic_log  # noqa: E402


class DiagnosticLogTest(unittest.TestCase):
    def test_daily_files_have_increasing_execution_numbers_and_jsonl_events(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(diagnostic_log, "LOG_ROOT", Path(directory)):
                first = diagnostic_log.DiagnosticRun("pose", {"instruction": "손을 들어"})
                first.event("completed", elapsed_seconds=1.25)
                second = diagnostic_log.DiagnosticRun("motion", {"params": {"steps": 10}})

                self.assertEqual(1, first.number)
                self.assertEqual(2, second.number)
                records = [json.loads(line) for line in first.path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(["started", "completed"], [item["event"] for item in records])
                self.assertEqual("손을 들어", records[0]["request"]["instruction"])
                self.assertEqual(1.25, records[1]["elapsed_seconds"])


if __name__ == "__main__":
    unittest.main()
