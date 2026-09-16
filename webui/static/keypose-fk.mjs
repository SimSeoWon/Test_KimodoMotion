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
