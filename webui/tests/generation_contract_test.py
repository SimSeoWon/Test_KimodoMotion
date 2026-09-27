import copy
import struct
import tempfile
import unittest
from pathlib import Path

from webui.generation_contract import compile_keypose_constraints, motion_skeleton, normalize_generation_request
from webui.keypose import validate_keypose_document


class GenerationContractTest(unittest.TestCase):
    def document(self, **changes):
        doc = {"schema_version": 1, "skeleton": "soma30", "keyposes": [{
            "frame": 0, "controls": {
                "pelvis": {"position": [1, 0.9, 2]},
                "left_hand": {"position": [1.4, 1.2, 2.6], "rotation_xyzw": [0, 0, 0, 2]},
            },
        }]}
        doc["keyposes"][0]["controls"]["left_hand"].update(changes)
        return doc

    def test_canonical_world_targets_reach_native_rows_without_axis_changes(self):
        params = normalize_generation_request({"prompt": "walk", "keyposes": self.document()})
        rows = compile_keypose_constraints(params["keyposes"])
        self.assertEqual("0 0 1 1.0 0.9 2.0 0 0 0 0 1", rows[0])
        self.assertEqual("0 13 1 1.4 1.2 2.6 1 0.0 0.0 0.0 1.0", rows[1])

    def test_disabled_control_is_omitted_and_unsupported_semantics_are_rejected(self):
        rows = compile_keypose_constraints(validate_keypose_document(self.document(weight=0)))
        self.assertEqual(1, len(rows))
        for changes in ({"weight": 0.5}, {"space": "local"}, {"space": "character"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize_generation_request({"prompt": "walk", "keyposes": self.document(**changes)})

    def test_legacy_pose_is_not_silently_reinterpreted(self):
        doc = self.document()
        del doc["skeleton"]
        with self.assertRaisesRegex(ValueError, "다시 저장"):
            normalize_generation_request({"prompt": "walk", "keyposes": doc})

    def test_hand_position_without_pelvis_leaves_root_free(self):
        # Native positions are root-relative in XZ; adding a pelvis row would pin the
        # global root to the editor origin and drag locomotion back mid-motion.
        doc = self.document()
        del doc["keyposes"][0]["controls"]["pelvis"]
        rows = compile_keypose_constraints(normalize_generation_request({"prompt": "walk", "keyposes": doc})["keyposes"])
        self.assertEqual([13], [int(row.split()[1]) for row in rows])

    def test_invalid_inputs_fail_before_inference(self):
        cases = [
            {"frame_count": 600}, {"frame_count": 1}, {"frame_count": 4.5},
            {"steps": 0}, {"steps": True}, {"text_cfg": float("nan")},
            {"text_cfg": "Infinity"}, {"batch_count": 9}, {"batch_count": 0},
            {"seed": -2}, {"seed": 2_147_483_647, "batch_count": 2},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                normalize_generation_request({"prompt": "walk", **case})

    def test_sequence_transition_and_constrained_sequence_are_checked(self):
        segments = [{"prompt": "walk", "frame_count": 10}, {"prompt": "stop", "frame_count": 20}]
        with self.assertRaisesRegex(ValueError, "전환"):
            normalize_generation_request({"segments": segments, "transition_frames": 15})
        with self.assertRaisesRegex(ValueError, "단일 구간"):
            normalize_generation_request({"segments": segments, "transition_frames": 2, "keyposes": self.document()})
        result = normalize_generation_request({"segments": segments, "transition_frames": 2})
        self.assertEqual(30, result["frame_count"])

    def test_normalization_is_detached_and_batch_seeds_fit_range(self):
        params = {"prompt": " walk ", "batch_count": 8, "seed": -1, "keyposes": self.document()}
        before = copy.deepcopy(params)
        result = normalize_generation_request(params)
        self.assertEqual(before, params)
        self.assertLessEqual(result["seed"] + 7, 2_147_483_647)
        self.assertEqual(2.0, result["text_cfg"])

    def test_reads_actual_skeleton_instead_of_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kimodo-soma-rp.gguf"
            key, value = b"kimodo.skeleton", b"g1"
            path.write_bytes(struct.pack("<4sIQQQ", b"GGUF", 3, 0, 1, len(key)) + key
                             + struct.pack("<IQ", 8, len(value)) + value)
            self.assertEqual("g1", motion_skeleton(path))
            path.write_bytes(b"GGUF")
            with self.assertRaises(ValueError):
                motion_skeleton(path)
