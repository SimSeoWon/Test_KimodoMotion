import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

import pose_agent  # noqa: E402


class PoseAgentConfigTest(unittest.TestCase):
    def test_reads_timeout_settings_without_import_time_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            config_file = Path(directory) / "config.json"
            with patch.object(pose_agent, "CONFIG_FILE", config_file):
                config_file.write_text(json.dumps({"pose_agent": {
                    "total_timeout_seconds": 480,
                    "idle_timeout_seconds": 60,
                    "max_attempts": 1,
                }}), encoding="utf-8")
                first = pose_agent.load_pose_agent_config()
                config_file.write_text(json.dumps({"pose_agent": {
                    "total_timeout_seconds": 600,
                    "idle_timeout_seconds": 90,
                    "max_attempts": 2,
                }}), encoding="utf-8")
                second = pose_agent.load_pose_agent_config()

        self.assertEqual(480, first["total_timeout_seconds"])
        self.assertEqual(600, second["total_timeout_seconds"])
        self.assertEqual(90, second["idle_timeout_seconds"])
        self.assertEqual(2, second["max_attempts"])

    def test_invalid_values_fall_back_or_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            config_file = Path(directory) / "config.json"
            config_file.write_text(json.dumps({"pose_agent": {
                "total_timeout_seconds": 99999,
                "idle_timeout_seconds": "bad",
                "max_attempts": 0,
            }}), encoding="utf-8")
            with patch.object(pose_agent, "CONFIG_FILE", config_file):
                config = pose_agent.load_pose_agent_config()

        self.assertEqual(1800, config["total_timeout_seconds"])
        self.assertEqual(45, config["idle_timeout_seconds"])
        self.assertEqual(1, config["max_attempts"])


if __name__ == "__main__":
    unittest.main()
