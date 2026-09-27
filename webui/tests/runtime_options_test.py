import tempfile
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

from webui import server


class RuntimeOptionsTest(unittest.TestCase):
    def test_discovers_models_and_marks_missing_quantizations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            generated = root / "generated"
            models.mkdir()
            bundle = generated / "llm2vec-text-bundle"
            bundle.mkdir(parents=True)
            key, value = b"kimodo.skeleton", b"soma30"
            (models / "kimodo-soma-rp-v1.1-f32.gguf").write_bytes(
                struct.pack("<4sIQQQ", b"GGUF", 3, 0, 1, len(key)) + key
                + struct.pack("<IQ", 8, len(value)) + value)
            (bundle / "embedding.gguf").write_bytes(b"text")
            with patch.object(server, "KIMODO_MODELS_DIR", models), \
                 patch.object(server, "KIMODO_GENERATED_DIR", generated):
                result = server.list_runtime_options()

        self.assertEqual(1, len(result["models"]))
        self.assertIn("SOMA RP", result["models"][0]["label"])
        self.assertTrue(result["models"][0]["supported"])
        encoders = {item["quantization"]: item for item in result["encoders"]}
        self.assertTrue(encoders["bf16"]["available"])
        self.assertFalse(encoders["q8_0"]["available"])

    def test_packed_encoder_is_a_selectable_default(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            packed = generated / "Llama-3-Kimodo-BF16.gguf"
            packed.write_bytes(b"text")
            with patch.object(server, "KIMODO_GENERATED_DIR", generated):
                result = server.list_runtime_options()
            self.assertEqual(str(packed), result["default_encoder"])


if __name__ == "__main__":
    unittest.main()
