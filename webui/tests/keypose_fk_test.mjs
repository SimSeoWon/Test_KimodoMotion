import assert from "node:assert/strict";
import {
  computeWorldTransforms,
  quaternionFromAxisAngle,
} from "../static/keypose-fk.mjs";

const identity = [0, 0, 0, 1];
const almostEqual = (actual, expected, epsilon = 1e-6) => {
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < epsilon,
    `${actual} != ${expected} at ${index}`));
};

// A minimal shoulder -> elbow -> hand chain. Rotating the shoulder 90 degrees
// around +Z must carry both descendants; their local rotations remain identity.
{
  const parents = [-1, 0, 1];
  const local = [
    {position: [0, 0, 0], rotation_xyzw: quaternionFromAxisAngle([0, 0, 1], Math.PI / 2)},
    {position: [1, 0, 0], rotation_xyzw: identity},
    {position: [1, 0, 0], rotation_xyzw: identity},
  ];
  const world = computeWorldTransforms(parents, local);
  almostEqual(world[1].position, [0, 1, 0]);
  almostEqual(world[2].position, [0, 2, 0]);
}

// Parent and child rotations compose continuously down the hierarchy.
{
  const quarterTurn = quaternionFromAxisAngle([0, 0, 1], Math.PI / 2);
  const world = computeWorldTransforms(
    [-1, 0],
    [
      {position: [0, 0, 0], rotation_xyzw: quarterTurn},
      {position: [1, 0, 0], rotation_xyzw: quarterTurn},
    ],
  );
  almostEqual(world[1].position, [0, 1, 0]);
  // Two 90-degree rotations produce a 180-degree global rotation.
  almostEqual(world[1].rotation_xyzw.map((value) => Math.abs(value)), [0, 0, 1, 0]);
}

// Invalid non-topological parents are rejected instead of producing stale FK.
assert.throws(() => computeWorldTransforms(
  [1, -1],
  [
    {position: [0, 0, 0], rotation_xyzw: identity},
    {position: [0, 0, 0], rotation_xyzw: identity},
  ],
), /earlier joint/);

console.log("keypose FK tests passed");
