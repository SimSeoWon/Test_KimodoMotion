import tempfile
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
            (models / "kimodo-soma-rp-v1.1-f32.gguf").write_bytes(b"model")
            (bundle / "embedding.gguf").write_bytes(b"text")
            with patch.object(server, "KIMODO_MODELS_DIR", models), \
                 patch.object(server, "KIMODO_GENERATED_DIR", generated):
                result = server.list_runtime_options()

        self.assertEqual(1, len(result["models"]))
        self.assertIn("SOMA RP", result["models"][0]["label"])
        encoders = {item["quantization"]: item for item in result["encoders"]}
        self.assertTrue(encoders["bf16"]["available"])
        self.assertFalse(encoders["q8_0"]["available"])


if __name__ == "__main__":
    unittest.main()
