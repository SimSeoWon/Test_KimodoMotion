import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from webui import server


class PreviewCacheTest(unittest.TestCase):
    """A re-extracted binding or a changed exporter must rebuild display GLBs."""

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.bindings = self.root / "bindings"
        self.bindings.mkdir()
        self.bind = self.bindings / "quinn_soma30_bind.json"
        self.bind.write_text(json.dumps({"label": "Quinn", "offsets": [1]}), encoding="utf-8")
        self.exporter = self.root / "pretty_export_glb.py"
        self.exporter.write_text("# v1", encoding="utf-8")
        self.generations = self.root / "results"
        self.motion = self.generations / "gen1"
        self.motion.mkdir(parents=True)
        (self.motion / "meta.json").write_text("{}", encoding="utf-8")
        self.static = self.root / "static"
        self.static.mkdir()
        for name, value in (("MIXAMO_PROCESSED_DIR", self.bindings), ("EXPORT_GLB_PY", self.exporter),
                            ("VENDOR_EXPORT_GLB_PY", self.root / "export_glb.py"),
                            ("GENERATIONS_DIR", self.generations), ("STATIC_DIR", self.static),
                            ("TPOSE_SRC_DIR", self.root / "tpose_src")):
            self.stack.enter_context(patch.object(server, name, value))
        self.builds = []

        def export(command, **kwargs):
            output = Path(command[command.index("--output") + 1])
            output.write_bytes(self.bind.read_bytes())
            self.builds.append(command[command.index("--mixamo-bind") + 1])
            return subprocess.CompletedProcess(command, 0, "", "")

        self.stack.enter_context(patch.object(server.subprocess, "run", side_effect=export))

    def touch_later(self, path, text):
        stat = path.stat()
        path.write_text(text, encoding="utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    def test_generation_preview_rebuilds_after_binding_or_exporter_change(self):
        legacy = self.motion / "preview_v2_quinn.glb"
        legacy.write_bytes(b"stale")
        first = server.ensure_preview_variant("gen1", "quinn")
        self.assertEqual(first, server.ensure_preview_variant("gen1", "quinn"))
        self.assertEqual(1, len(self.builds))
        self.assertFalse(legacy.exists())

        self.touch_later(self.bind, json.dumps({"label": "Quinn", "offsets": [2]}))
        second = server.ensure_preview_variant("gen1", "quinn")
        self.assertNotEqual(first, second)
        self.assertIn(b"[2]", second.read_bytes())
        self.assertFalse(first.exists())

        self.touch_later(self.exporter, "# v2")
        third = server.ensure_preview_variant("gen1", "quinn")
        self.assertNotEqual(second, third)
        self.assertEqual(3, len(self.builds))
        self.assertEqual([third.name], [path.name for path in self.motion.glob("preview_*.glb")])

    def test_other_characters_previews_are_kept(self):
        other = self.motion / "preview_v2_quinn_simple_0123456789ab.glb"
        other.write_bytes(b"other character")
        server.ensure_preview_variant("gen1", "quinn")
        self.assertTrue(other.exists())

    def test_tpose_rebuilds_after_binding_change_and_status_tracks_it(self):
        first = server.ensure_tpose_variant("quinn", str(self.bind))
        self.assertEqual(first, server.ensure_tpose_variant("quinn", str(self.bind)))
        self.assertEqual(1, len(self.builds))
        self.touch_later(self.bind, json.dumps({"label": "Quinn", "offsets": [3]}))
        self.assertFalse(server.tpose_path("quinn", str(self.bind)).exists())
        second = server.ensure_tpose_variant("quinn", str(self.bind))
        self.assertNotEqual(first, second)
        self.assertEqual([second.name], [path.name for path in self.static.glob("tpose_quinn*.glb")])


if __name__ == "__main__":
    unittest.main()
