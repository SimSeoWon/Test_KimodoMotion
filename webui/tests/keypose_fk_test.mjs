import assert from "node:assert/strict";
import {
  computeWorldTransforms,
  quaternionFromAxisAngle,
  solveTwoBonePositions,
  solveTwoBoneWithJointHint,
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
  almostEqual([Math.hypot(...world[1].position)], [1]);
  almostEqual([Math.hypot(
    world[2].position[0] - world[1].position[0],
    world[2].position[1] - world[1].position[1],
    world[2].position[2] - world[1].position[2],
  )], [1]);
}

// A knee hint is honored without allowing the knee outside the hip-ankle line.
{
  const solved = solveTwoBoneWithJointHint(
    [0.1, 1, 0], [0.5, 0.2, 0], [0.5, 0.5, 0.15], [0, 0, 1],
    0.5, 0.5, 5 * Math.PI / 6,
  );
  assert.ok(solved.joint[0] > 0.1, "knee hint must spread the knee outward");
  assert.ok(solved.joint[0] >= 0.1 && solved.joint[0] <= solved.end[0], "knee must stay between hip and ankle");
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

// End-effector world orientation is applied after IK parent rotation by
// converting it back to local space; the foot remains level in world space.
{
  const parentRotation = quaternionFromAxisAngle([1, 0, 0], Math.PI / 4);
  const inverseParent = [-parentRotation[0], -parentRotation[1], -parentRotation[2], parentRotation[3]];
  const world = computeWorldTransforms(
    [-1, 0],
    [
      {position: [0, 0, 0], rotation_xyzw: parentRotation},
      {position: [0, -1, 0], rotation_xyzw: inverseParent},
    ],
  );
  almostEqual(world[1].rotation_xyzw, identity);
}

// Translating Hips/root carries every descendant by exactly the same delta.
{
  const world = computeWorldTransforms(
    [-1, 0, 1],
    [
      {position: [3, 2, -1], rotation_xyzw: identity},
      {position: [0, -1, 0], rotation_xyzw: identity},
      {position: [0, -1, 0], rotation_xyzw: identity},
    ],
  );
  almostEqual(world[0].position, [3, 2, -1]);
  almostEqual(world[1].position, [3, 1, -1]);
  almostEqual(world[2].position, [3, 0, -1]);
}

// Invalid non-topological parents are rejected instead of producing stale FK.
assert.throws(() => computeWorldTransforms(
  [1, -1],
  [
    {position: [0, 0, 0], rotation_xyzw: identity},
    {position: [0, 0, 0], rotation_xyzw: identity},
  ],
), /earlier joint/);

// A two-bone leg keeps both segment lengths and bends toward the forward pole.
{
  const solved = solveTwoBonePositions([0, 1, 0], [0, 0.2, 0.2], [0, 0, 1], 0.5, 0.5, 5 * Math.PI / 6);
  const upperLength = Math.hypot(solved.joint[0], solved.joint[1] - 1, solved.joint[2]);
  const lowerLength = Math.hypot(
    solved.end[0] - solved.joint[0], solved.end[1] - solved.joint[1], solved.end[2] - solved.joint[2],
  );
  almostEqual([upperLength, lowerLength], [0.5, 0.5]);
  assert.ok(solved.joint[2] > 0, "knee must bend toward the +Z pole");
}

// The same constraints are mirrored on the right leg.
{
  const solved = solveTwoBoneWithJointHint(
    [-0.1, 1, 0], [-0.5, 0.2, 0], [-0.55, 0.5, 0.15], [0, 0, 1],
    0.5, 0.5, 5 * Math.PI / 6,
  );
  assert.ok(solved.joint[0] <= -0.1 && solved.joint[0] >= solved.end[0], "knee must stay between hip and ankle");
}

// Regression: a wide stance (ankle spread far past the hip-ankle straight-line
// reach) must bend the knee outward, not jut it forward. The fixed bone lengths
// force a bend ("height") wider than the hip-ankle gap, so a knee hint with no
// lateral signal of its own (almost collinear with hip->ankle) used to fall back
// to a near-straight leg with the entire bend pushed toward the forward pole.
{
  const hip = [0.09124451130628586, 0.7508071545160437, -0.0005533625953830779];
  const target = [0.34304174397025344, 0.10492202639579773, -0.026301046833395958];
  const jointHint = [0.2963324000346724, 0.4004591235442252, -0.005709519609808922];
  const forwardPole = [0.013481357496357238, -0.03458103260963905, 0.9993109652073805];
  const solved = solveTwoBoneWithJointHint(
    hip, target, jointHint, forwardPole, 0.40599429905363793, 0.4209902753729924, 5 * Math.PI / 6,
  );
  const kneeOffsetForward = solved.joint[2] - hip[2];
  const kneeOffsetOutward = solved.joint[0] - hip[0];
  assert.ok(kneeOffsetForward < 0.1, `knee must not jut forward in a wide stance (got ${kneeOffsetForward})`);
  assert.ok(kneeOffsetOutward > 0.15, `knee must bend outward toward the wide ankle (got ${kneeOffsetOutward})`);
}

console.log("keypose FK tests passed");
