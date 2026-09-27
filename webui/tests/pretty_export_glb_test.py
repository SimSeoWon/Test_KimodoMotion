import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import pretty_export_glb  # noqa: E402


class CapsuleSkinningTest(unittest.TestCase):
    def test_each_bone_segment_is_bound_to_its_parent_joint(self):
        positions = [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]
        parents = [-1, 0, 1]
        vertices, joints, _weights, _indices = pretty_export_glb.create_capsule_doll_mesh(
            positions, parents
        )

        vertices_per_capsule = len(vertices) // 3
        root_joints = joints[:vertices_per_capsule]
        first_segment_joints = joints[vertices_per_capsule:vertices_per_capsule * 2]
        second_segment_joints = joints[vertices_per_capsule * 2:]

        self.assertTrue(all(item[0] == 0 for item in root_joints))
        self.assertTrue(all(item[0] == 0 for item in first_segment_joints))
        self.assertTrue(all(item[0] == 1 for item in second_segment_joints))


if __name__ == "__main__":
    unittest.main()
