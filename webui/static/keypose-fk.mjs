// Minimal, dependency-free FK used by the key-pose editor and Node tests.
// Quaternions are [x, y, z, w]. Parents must precede children.

const EPSILON = 1e-8;

export function normalizeQuaternion(value) {
  if (!Array.isArray(value) || value.length !== 4 || value.some((item) => !Number.isFinite(item))) {
    throw new TypeError("quaternion must contain four finite numbers");
  }
  const length = Math.hypot(...value);
  if (length < EPSILON) throw new RangeError("quaternion must not be zero");
  return value.map((item) => item / length);
}

export function multiplyQuaternions(a, b) {
  const [ax, ay, az, aw] = a;
  const [bx, by, bz, bw] = b;
  return normalizeQuaternion([
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
    aw * bw - ax * bx - ay * by - az * bz,
  ]);
}

export function rotateVector(rotation, vector) {
  const [x, y, z, w] = rotation;
  const [vx, vy, vz] = vector;
  // q * [v, 0] * conjugate(q), expanded to avoid temporary quaternions.
  const tx = 2 * (y * vz - z * vy);
  const ty = 2 * (z * vx - x * vz);
  const tz = 2 * (x * vy - y * vx);
  return [
    vx + w * tx + (y * tz - z * ty),
    vy + w * ty + (z * tx - x * tz),
    vz + w * tz + (x * ty - y * tx),
  ];
}

function addVectors(a, b) {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

export function computeWorldTransforms(parents, localTransforms) {
  if (!Array.isArray(parents) || !Array.isArray(localTransforms) || parents.length !== localTransforms.length) {
    throw new TypeError("parents and localTransforms must be arrays of equal length");
  }

  const world = [];
  for (let index = 0; index < parents.length; index += 1) {
    const parent = parents[index];
    const local = localTransforms[index];
    if (!local || !Array.isArray(local.position) || local.position.length !== 3) {
      throw new TypeError(`localTransforms[${index}].position must contain three numbers`);
    }
    if (local.position.some((item) => !Number.isFinite(item))) {
      throw new TypeError(`localTransforms[${index}].position must contain finite numbers`);
    }
    const localRotation = normalizeQuaternion(local.rotation_xyzw);

    if (parent === -1) {
      world.push({position: [...local.position], rotation_xyzw: localRotation});
      continue;
    }
    if (!Number.isInteger(parent) || parent < 0 || parent >= index) {
      throw new RangeError(`parents[${index}] must refer to an earlier joint or -1`);
    }
    const parentWorld = world[parent];
    world.push({
      position: addVectors(parentWorld.position, rotateVector(parentWorld.rotation_xyzw, local.position)),
      rotation_xyzw: multiplyQuaternions(parentWorld.rotation_xyzw, localRotation),
    });
  }
  return world;
}

export function quaternionFromAxisAngle(axis, radians) {
  if (!Array.isArray(axis) || axis.length !== 3 || axis.some((item) => !Number.isFinite(item))) {
    throw new TypeError("axis must contain three finite numbers");
  }
  if (!Number.isFinite(radians)) throw new TypeError("radians must be finite");
  const axisLength = Math.hypot(...axis);
  if (axisLength < EPSILON) throw new RangeError("axis must not be zero");
  const scale = Math.sin(radians / 2) / axisLength;
  return normalizeQuaternion([axis[0] * scale, axis[1] * scale, axis[2] * scale, Math.cos(radians / 2)]);
}

export function solveTwoBonePositions(root, target, pole, upperLength, lowerLength, maxFlexRadians) {
  for (const [name, value] of Object.entries({root, target, pole})) {
    if (!Array.isArray(value) || value.length !== 3 || value.some((item) => !Number.isFinite(item))) {
      throw new TypeError(`${name} must contain three finite numbers`);
    }
  }
  if (!(upperLength > 0) || !(lowerLength > 0)) throw new RangeError("bone lengths must be positive");
  const delta = target.map((value, index) => value - root[index]);
  const rawDistance = Math.hypot(...delta);
  if (rawDistance < EPSILON) throw new RangeError("target must differ from root");
  const direction = delta.map((value) => value / rawDistance);
  const minDistance = Math.sqrt(
    upperLength ** 2 + lowerLength ** 2 + 2 * upperLength * lowerLength * Math.cos(maxFlexRadians),
  );
  const distance = Math.min(Math.max(rawDistance, minDistance), upperLength + lowerLength - EPSILON);
  let perpendicular = pole.map((value, index) => value - direction[index]
    * pole.reduce((sum, item, poleIndex) => sum + item * direction[poleIndex], 0));
  let perpendicularLength = Math.hypot(...perpendicular);
  if (perpendicularLength < EPSILON) throw new RangeError("pole must not be parallel to target direction");
  perpendicular = perpendicular.map((value) => value / perpendicularLength);
  const along = (upperLength ** 2 + distance ** 2 - lowerLength ** 2) / (2 * distance);
  const height = Math.sqrt(Math.max(0, upperLength ** 2 - along ** 2));
  const joint = root.map((value, index) => value + direction[index] * along + perpendicular[index] * height);
  const end = root.map((value, index) => value + direction[index] * distance);
  return {joint, end};
}

export function solveTwoBoneWithJointHint(
  root, target, jointHint, forwardPole, upperLength, lowerLength, maxFlexRadians,
) {
  let best = null;
  let bestDistance = Infinity;
  for (let step = 0; step <= 20; step += 1) {
    const amount = step / 20;
    const pole = forwardPole.map((value, index) => value * (1 - amount)
      + (jointHint[index] - root[index]) * amount);
    let solved;
    try {
      solved = solveTwoBonePositions(root, target, pole, upperLength, lowerLength, maxFlexRadians);
    } catch (_) {
      continue;
    }
    // Keep the knee laterally between hip and ankle. This prevents the hip
    // from being forced open by an over-wide knee pole.
    const lateralMin = Math.min(root[0], solved.end[0]) - 1e-6;
    const lateralMax = Math.max(root[0], solved.end[0]) + 1e-6;
    if (solved.joint[0] < lateralMin || solved.joint[0] > lateralMax) continue;
    const distance = Math.hypot(...solved.joint.map((value, index) => value - jointHint[index]));
    if (distance < bestDistance) {
      best = solved;
      bestDistance = distance;
    }
  }
  if (best) return best;
  return solveTwoBonePositions(root, target, forwardPole, upperLength, lowerLength, maxFlexRadians);
}
