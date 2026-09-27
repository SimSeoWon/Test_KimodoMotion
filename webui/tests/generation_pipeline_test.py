import copy
import json
import struct
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from webui import server
from webui.generation_batch import GenerationBatchState


class GenerationPipelineTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.model = self.root / "motion.gguf"
        key, value = b"kimodo.skeleton", b"soma30"
        self.model.write_bytes(struct.pack("<4sIQQQ", b"GGUF", 3, 0, 1, len(key)) + key
                              + struct.pack("<IQ", 8, len(value)) + value)
        self.exe = self.root / "generator.exe"
        self.exe.touch()
        self.stack.enter_context(patch.object(server, "KMD_GENERATE", self.exe))
        self.stack.enter_context(patch.object(server, "GENERATIONS_DIR", self.root / "results"))
        self.stack.enter_context(patch.object(server, "BATCH_STATE", GenerationBatchState()))
        self.stack.enter_context(patch.object(server, "DiagnosticRun", return_value=Mock()))
        self.base = {"prompt": "walk", "model": str(self.model), "text_bundle": str(self.root), "seed": 42}

    def test_worker_is_reaped_before_one_shot_and_each_sample_has_unique_output(self):
        order = []
        resident = Mock()
        resident.close.side_effect = lambda: order.append("closed")

        def run(command, **kwargs):
            if command[0] == str(self.exe):
                self.assertEqual("closed", order[-1])
                order.append("inference")
                return subprocess.CompletedProcess(command, 0, "generated 120 frames", "")
            output = Path(command[command.index("--output") + 1])
            output.write_bytes(b"glb")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(server, "PERSISTENT_GENERATOR", resident), patch.object(server, "run_cancelable", side_effect=run):
            result = server.run_generation_batch({**self.base, "negative_prompt": "running", "batch_count": 3})
        self.assertEqual("complete", result["status"])
        self.assertEqual([42, 43, 44], [m["seed"] for m in result["items"]])
        self.assertEqual(3, len({m["id"] for m in result["items"]}))
        self.assertEqual(1, len({m["batch_id"] for m in result["items"]}))
        self.assertEqual([1, 2, 3], [m["batch_index"] for m in result["items"]])
        self.assertEqual(3, len(server.load_history()))

    def test_cancelled_or_failed_sample_leaves_no_output_folder(self):
        inferences = []

        def run(command, **kwargs):
            if command[0] == str(self.exe):
                inferences.append(Path(kwargs["env"].get("KIMODO_CONSTRAINTS_FILE", "")))
                if len(inferences) == 2:
                    server.BATCH_STATE.request_cancel()
                    raise server.GenerationCancelled("cancelled")
                return subprocess.CompletedProcess(command, 0, "generated 120 frames", "")
            Path(command[command.index("--output") + 1]).write_bytes(b"glb")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(server, "PERSISTENT_GENERATOR", Mock()), patch.object(server, "run_cancelable", side_effect=run):
            result = server.run_generation_batch({**self.base, "negative_prompt": "running", "batch_count": 3})
        self.assertEqual("cancelled", result["status"])
        folders = sorted(path.name for path in (self.root / "results").iterdir())
        self.assertEqual([result["items"][0]["id"]], folders)

        failing = subprocess.CompletedProcess([str(self.exe)], 1, "", "boom")
        with patch.object(server, "PERSISTENT_GENERATOR", Mock()), patch.object(server, "run_cancelable", return_value=failing):
            self.assertEqual("failed", server.run_generation_batch({**self.base, "negative_prompt": "running"})["status"])
        self.assertEqual(folders, sorted(path.name for path in (self.root / "results").iterdir()))

    def test_batch_only_changes_seed_and_stops_after_cancellation(self):
        calls = []

        def generate(params):
            calls.append(copy.deepcopy(params))
            if len(calls) == 2:
                server.BATCH_STATE.request_cancel()
            return {"id": str(len(calls)), "seed": params["seed"]}

        with patch.object(server, "run_generation", side_effect=generate):
            result = server.run_generation_batch({**self.base, "batch_count": 4})
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(2, result["completed"])
        first = {k: v for k, v in calls[0].items() if k not in ("seed", "_batch")}
        second = {k: v for k, v in calls[1].items() if k not in ("seed", "_batch")}
        self.assertEqual(first, second)
        self.assertEqual([42, 43], [item["seed"] for item in result["items"]])
        with patch.object(server, "run_generation", return_value={"id": "retry"}):
            self.assertEqual("complete", server.run_generation_batch(self.base)["status"])

    def test_later_failure_preserves_completed_results(self):
        with patch.object(server, "run_generation", side_effect=[{"id": "first"}, RuntimeError("failed")]):
            result = server.run_generation_batch({**self.base, "batch_count": 3})
        self.assertEqual("failed", result["status"])
        self.assertEqual([{"id": "first"}], result["items"])
        self.assertEqual("failed", result["error"])

    def test_cancel_during_active_inference_does_not_start_next_sample(self):
        with patch.object(server, "run_generation", side_effect=server.GenerationCancelled("cancelled")) as run:
            result = server.run_generation_batch({**self.base, "batch_count": 3})
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(1, run.call_count)

    def test_invalid_request_never_starts_a_batch_or_worker(self):
        with patch.object(server, "run_generation") as run:
            with self.assertRaises(ValueError):
                server.run_generation_batch({**self.base, "frame_count": 600})
            run.assert_not_called()
        self.assertEqual("idle", server.BATCH_STATE.snapshot()["status"])

    def test_close_waits_for_forced_exit_before_forgetting_the_worker(self):
        runtime = server.PersistentGenerator()
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("worker", 5),
                                    subprocess.TimeoutExpired("worker", 5), 0]
        runtime.proc = process
        runtime.close()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(3, process.wait.call_count)
        self.assertIsNone(runtime.proc)

    def test_pose_targets_written_to_file_match_saved_metadata(self):
        keyposes = {"schema_version": 1, "skeleton": "soma30", "keyposes": [{"frame": 0, "controls": {
            "pelvis": {"position": [1, 0.9, 2]}, "left_hand": {"position": [1.4, 1.2, 2.6]},
        }}]}
        native_rows = []

        def run(command, **kwargs):
            if command[0] == str(self.exe):
                native_rows.append(Path(kwargs["env"]["KIMODO_CONSTRAINTS_FILE"]).read_text())
                return subprocess.CompletedProcess(command, 0, "generated 120 frames", "")
            Path(command[command.index("--output") + 1]).write_bytes(b"glb")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(server, "PERSISTENT_GENERATOR"), patch.object(server, "run_cancelable", side_effect=run):
            result = server.run_generation_batch({**self.base, "keyposes": keyposes})
        self.assertEqual("complete", result["status"])
        meta = result["items"][0]
        saved = json.loads((self.root / "results" / meta["id"] / "meta.json").read_text())
        self.assertEqual(meta["keyposes"], saved["keyposes"])
        self.assertEqual("soma30", saved["keyposes"]["keyposes"][0]["skeleton"])
        self.assertIn("0 13 1 1.4 1.2 2.6", native_rows[0])
        self.assertFalse(meta["persistent_worker"])
