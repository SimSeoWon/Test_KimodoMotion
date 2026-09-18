import sys
import tempfile
import time
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import patch

WEBUI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBUI_DIR))

from pose_agent import (  # noqa: E402
    POSE_RESULT_SCHEMA, PoseAgentDaemon, _run_pose_cli,
)
import diagnostic_log  # noqa: E402
import pose_agent  # noqa: E402


class PoseAgentDaemonTest(unittest.TestCase):
    def setUp(self):
        self._log_directory = tempfile.TemporaryDirectory()
        self._log_patch = patch.object(diagnostic_log, "LOG_ROOT", Path(self._log_directory.name))
        self._log_patch.start()

    def tearDown(self):
        self._log_patch.stop()
        self._log_directory.cleanup()

    def test_cli_retries_once_after_a_stalled_request(self):
        success = CompletedProcess(["claude"], 0, stdout="ok", stderr="")
        with patch("pose_agent.subprocess.run", side_effect=[TimeoutExpired("claude", 1), success]) as run:
            result = _run_pose_cli(["claude"], WEBUI_DIR.parent, attempt_timeout=1)
        self.assertIs(success, result)
        self.assertEqual(2, run.call_count)

    def test_cli_reports_two_stalled_requests(self):
        with patch("pose_agent.subprocess.run", side_effect=TimeoutExpired("claude", 1)) as run:
            with self.assertRaisesRegex(RuntimeError, "1초씩 두 번"):
                _run_pose_cli(["claude"], WEBUI_DIR.parent, attempt_timeout=1)
        self.assertEqual(2, run.call_count)

    def test_runtime_uses_at_least_sonnet(self):
        process = unittest.mock.MagicMock()
        process.poll.return_value = None
        process.stdout = []
        process.stderr = []
        process.pid = 123
        runtime = pose_agent.PoseCliRuntime()
        with patch("pose_agent.shutil.which", return_value="claude.exe"), \
             patch("pose_agent.subprocess.Popen", return_value=process) as popen, \
             patch.dict("pose_agent.os.environ", {"KIMODO_POSE_AGENT_MODEL": "haiku"}):
            runtime.start()
        command = popen.call_args.args[0]
        self.assertEqual("sonnet", command[command.index("--model") + 1])

    def test_knee_output_is_position_only(self):
        knee = POSE_RESULT_SCHEMA["properties"]["controls"]["properties"]["left_knee"]
        self.assertEqual("#/$defs/position_only", knee["$ref"])
        definition = POSE_RESULT_SCHEMA["$defs"]["position_only"]
        self.assertIn("position", definition["properties"])
        self.assertNotIn("rotation_xyzw", definition["properties"])

    def test_job_completes_with_validated_pose_and_revision(self):
        daemon = PoseAgentDaemon(lambda instruction, pose, snapshot: {
            "name": "손 들기",
            "summary": instruction,
            "controls": {"right_hand": {"position": [0.4, 1.8, 0.1], "space": "world", "weight": 1}},
        })
        submitted = daemon.submit("오른손을 들어", {
            "schema_version": 1, "id": "live", "name": "현재 포즈", "controls": {},
        }, {"right_hand": {"position": [0.4, 1.0, 0.1]}})
        self.assertIn(submitted["status"], ("queued", "running", "complete"))
        for _ in range(100):
            state = daemon.state()
            if state["status"] == "complete":
                break
            time.sleep(0.005)
        self.assertEqual("complete", state["status"])
        self.assertEqual([0.4, 1.8, 0.1], state["pose"]["controls"]["right_hand"]["position"])
        self.assertEqual(1, state["pose"]["revision"])
        self.assertEqual("오른손을 들어", state["pose"]["edits"][0]["instruction"])
        self.assertEqual(["right_hand"], state["pose"]["edits"][0]["changed_controls"])
        self.assertGreaterEqual(state["revision"], 3)

    def test_job_keeps_rotation_when_same_leg_has_foot_target(self):
        daemon = PoseAgentDaemon(lambda instruction, pose, snapshot: {
            "name": "외회전 서기",
            "summary": instruction,
            "controls": {
                "left_hip": {"rotation_xyzw": [0, 0.1736, 0, 0.9848], "space": "world", "weight": 1},
                "left_foot": {"position": [0.3, 0.1, 0], "space": "world", "weight": 1},
            },
        })
        daemon.submit("왼발을 바깥으로 돌려", {
            "schema_version": 1, "id": "live", "name": "현재 포즈", "controls": {},
        }, {"left_foot": {"position": [0.1, 0.1, 0]}})
        for _ in range(100):
            state = daemon.state()
            if state["status"] == "complete":
                break
            time.sleep(0.005)
        self.assertIn("left_hip", state["pose"]["controls"])
        self.assertIn("left_foot", state["pose"]["controls"])
        self.assertEqual(["left_foot", "left_hip"], state["pose"]["edits"][0]["changed_controls"])

    def test_runner_failure_is_reported(self):
        def fail(*_):
            raise RuntimeError("agent unavailable")

        daemon = PoseAgentDaemon(fail)
        daemon.submit("명령", {
            "schema_version": 1, "id": "live", "name": "현재 포즈", "controls": {},
        }, {"pelvis": {"position": [0, 1, 0]}})
        for _ in range(100):
            state = daemon.state()
            if state["status"] == "failed":
                break
            time.sleep(0.005)
        self.assertEqual("failed", state["status"])
        self.assertIn("agent unavailable", state["error"])


if __name__ == "__main__":
    unittest.main()
