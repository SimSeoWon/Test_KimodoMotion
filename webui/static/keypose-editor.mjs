import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";
import { solveTwoBonePositions, solveTwoBoneWithJointHint } from "./keypose-fk.mjs";

const $ = (id) => document.getElementById(id);
const markerColor = 0x4fd18b;
const selectedColor = 0xffb84f;
const IK_DEPTH = {
  left_hand: 2, right_hand: 2,
  left_foot: 2, right_foot: 2,
  left_toe: 1, right_toe: 1,
  left_elbow: 1, right_elbow: 1,
  left_knee: 1, right_knee: 1,
};
const HINGE_CONTROLS = new Set(["left_elbow", "right_elbow", "left_knee", "right_knee"]);
const TWO_BONE_EFFECTORS = new Set(["left_foot", "right_foot"]);
const HUMAN_LIMITS = Object.freeze({
  hipFlexion: THREE.MathUtils.degToRad(120),
  hipExtension: THREE.MathUtils.degToRad(15),
  hipAbduction: THREE.MathUtils.degToRad(35),
  hipAdduction: THREE.MathUtils.degToRad(15),
  kneeFlexion: THREE.MathUtils.degToRad(135),
  ankleDorsiflexion: THREE.MathUtils.degToRad(20),
  anklePlantarflexion: THREE.MathUtils.degToRad(50),
  ankleSideTilt: THREE.MathUtils.degToRad(15),
});

function quaternionArray(quaternion) {
  return [quaternion.x, quaternion.y, quaternion.z, quaternion.w];
}

function vectorArray(vector) {
  return [vector.x, vector.y, vector.z];
}

function cloneBoneState(bones) {
  const state = {};
  for (const [name, bone] of bones) {
    state[name] = {
      position: vectorArray(bone.position),
      rotation_xyzw: quaternionArray(bone.quaternion),
    };
  }
  return state;
}

function restoreBoneState(bones, state) {
  for (const [name, value] of Object.entries(state || {})) {
    const bone = bones.get(name);
    if (!bone) continue;
    bone.position.fromArray(value.position);
    bone.quaternion.fromArray(value.rotation_xyzw).normalize();
  }
}

export async function createKeyposeEditor(options) {
  const container = $("pose-canvas");
  const status = $("pose-status");
  const selectionLabel = $("pose-selection");
  const labelInput = $("pose-label");
  const controlList = $("pose-controls");
  const presetSelect = $("pose-preset");
  const agentInstruction = $("pose-agent-instruction");
  const agentSubmit = $("pose-agent-submit");
  const agentStatus = $("pose-agent-status");
  const agentHistory = $("pose-agent-history");
  let posePresets = [];
  let agentRevision = -1;
  let currentPoseRecord = {id: crypto.randomUUID(), revision: 0, edits: []};

  function renderAgentHistory() {
    agentHistory.innerHTML = "";
    if (!(currentPoseRecord.edits || []).length) {
      const empty = document.createElement("div");
      empty.className = "pose-agent-edit";
      empty.textContent = "저장된 AI 요청이 없습니다.";
      agentHistory.appendChild(empty);
      return;
    }
    for (const edit of [...(currentPoseRecord.edits || [])].reverse().slice(0, 8)) {
      const row = document.createElement("div");
      row.className = "pose-agent-edit";
      const title = document.createElement("b");
      title.textContent = `r${edit.revision} · ${edit.instruction}`;
      const detail = document.createElement("div");
      detail.textContent = `${edit.summary || "수정됨"} · ${edit.changed_controls.length ? edit.changed_controls.join(", ") : "변경 없음"}`;
      row.append(title, detail);
      agentHistory.appendChild(row);
    }
  }

  const schemaResponse = await fetch("/api/keypose-schema");
  if (!schemaResponse.ok) throw new Error("키포즈 schema를 불러오지 못했습니다.");
  const schema = await schemaResponse.json();

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x11151c);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
  camera.position.set(2.4, 1.5, 3.2);
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  container.appendChild(renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 2.3));
  const directional = new THREE.DirectionalLight(0xffffff, 2.2);
  directional.position.set(2, 4, 3);
  scene.add(directional);
  scene.add(new THREE.GridHelper(5, 20, 0x3f4d5f, 0x27313e));

  const orbit = new OrbitControls(camera, renderer.domElement);
  orbit.target.set(0, 1, 0);
  orbit.enableDamping = true;
  const transform = new TransformControls(camera, renderer.domElement);
  scene.add(transform.getHelper());
  const ikTarget = new THREE.Object3D();
  scene.add(ikTarget);
  transform.addEventListener("dragging-changed", (event) => { orbit.enabled = !event.value; });

  const bones = new Map();
  const markers = new Map();
  const markerTargets = [];
  const constrained = new Map();
  let selected = null;
  let restState = null;
  let modelRoot = null;
  let mode = "select";
  let usingIkTarget = false;
  let activeTween = null;
  let tweenQueue = [];
  let tweenFinalMessage = "";

  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - ((-2 * t + 2) ** 3) / 2;
  }

  // Solves land straight on the final pose (bone-length-preserving math, no
  // animation of their own). Snapshot before/after, rewind, and let the render
  // loop tween local position/rotation per bone so a result is visible arriving
  // rather than snapping in — this never touches IK/FK math, only playback.
  function tweenToKeypose(applyInstant, label) {
    const before = cloneBoneState(bones);
    applyInstant();
    const after = cloneBoneState(bones);
    restoreBoneState(bones, before);
    tweenQueue = [{before, after, duration: 450, label}];
    advanceTweenQueue();
  }

  function advanceTweenQueue() {
    const next = tweenQueue.shift();
    if (!next) { activeTween = null; return; }
    activeTween = {...next, start: performance.now()};
    if (next.label) {
      agentStatus.textContent = `반영 중: ${next.label}`;
      const marker = markers.get(next.controlId);
      if (marker) marker.material.color.setHex(selectedColor);
    }
  }

  // Signal one changed control at a time instead of blending the whole pose at
  // once, so a multi-part AI edit is legible part by part. applyKeyposeInstant
  // always rebuilds from rest given a controls subset, so replaying it with an
  // increasing prefix of `changed_controls` (schema order, so limb parents are
  // applied before their IK children) yields well-defined intermediate poses —
  // this never re-derives IK math of its own, only sequences existing results.
  function playKeyposeEdit(poseAsset, finalMessage) {
    const edit = poseAsset.edits?.[poseAsset.edits.length - 1];
    tweenFinalMessage = finalMessage || "";
    if (!edit || !edit.changed_controls?.length) { applyKeypose(poseAsset); return; }
    const order = schema.controls.map((item) => item.id).filter((id) => edit.changed_controls.includes(id));
    let previous = cloneBoneState(bones);
    const initialBefore = previous;
    const queue = [];
    for (let index = 0; index < order.length; index += 1) {
      const partialControls = {...poseAsset.controls};
      for (let ahead = index + 1; ahead < order.length; ahead += 1) {
        const id = order[ahead];
        if (edit.before[id]) partialControls[id] = edit.before[id];
        else delete partialControls[id];
      }
      restoreBoneState(bones, restState);
      applyKeyposeInstant({controls: partialControls});
      const after = cloneBoneState(bones);
      const definition = schema.controls.find((item) => item.id === order[index]);
      queue.push({before: previous, after, duration: 260, label: definition?.label || order[index], controlId: order[index]});
      previous = after;
    }
    restoreBoneState(bones, initialBefore);
    tweenQueue = queue;
    advanceTweenQueue();
  }

  const gltf = await new GLTFLoader().loadAsync(options.modelUrl());
  modelRoot = gltf.scene;
  scene.add(modelRoot);
  modelRoot.traverse((object) => {
    if (object.isBone) bones.set(object.name, object);
  });
  restState = cloneBoneState(bones);
  modelRoot.updateMatrixWorld(true);
  const restTransforms = new Map();
  for (const definition of schema.controls) {
    const bone = bones.get(definition.soma_joint);
    if (!bone) continue;
    const position = new THREE.Vector3();
    const rotation = new THREE.Quaternion();
    bone.getWorldPosition(position);
    bone.getWorldQuaternion(rotation);
    restTransforms.set(definition.id, {
      position: vectorArray(position),
      rotation_xyzw: quaternionArray(rotation),
    });
  }

  for (const definition of schema.controls) {
    const bone = bones.get(definition.soma_joint);
    if (!bone) continue;
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(0.025, 14, 10),
      new THREE.MeshBasicMaterial({color: markerColor, depthTest: false}),
    );
    marker.renderOrder = 10;
    marker.userData.control = definition;
    scene.add(marker);
    markers.set(definition.id, marker);
    markerTargets.push(marker);

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = definition.label;
    button.dataset.control = definition.id;
    button.addEventListener("click", () => selectControl(definition.id));
    controlList.appendChild(button);
  }

  function selectControl(controlId) {
    selected = schema.controls.find((item) => item.id === controlId) || null;
    transform.detach();
    for (const [id, marker] of markers) marker.material.color.setHex(id === controlId ? selectedColor : markerColor);
    for (const button of controlList.querySelectorAll("button")) button.classList.toggle("active", button.dataset.control === controlId);
    if (!selected) {
      selectionLabel.textContent = "없음";
      return;
    }
    selectionLabel.textContent = selected.label;
    if (mode !== "select") attachGizmo();
  }

  function attachGizmo() {
    transform.detach();
    if (!selected || mode === "select") return;
    const bone = bones.get(selected.soma_joint);
    if (mode === "rotate" && HINGE_CONTROLS.has(selected.id)) {
      status.textContent = `${selected.label}은 힌지 관절입니다. 이동(W) 목표로 굽힘 방향을 조절하세요.`;
      return;
    }
    usingIkTarget = mode === "translate" && IK_DEPTH[selected.id] != null;
    if (mode === "translate" && selected.id !== "pelvis" && !usingIkTarget) {
      status.textContent = `${selected.label} 위치는 부모 본에서 계산됩니다. 회전(E)으로 조절하세요.`;
      return;
    }
    if (usingIkTarget) {
      bone.getWorldPosition(ikTarget.position);
      ikTarget.quaternion.identity();
      transform.attach(ikTarget);
    } else transform.attach(bone);
    transform.setMode(mode);
  }

  function solveIk(effector, target, depth) {
    const targetPosition = target.position;
    for (let iteration = 0; iteration < 8; iteration += 1) {
      let joint = effector.parent;
      for (let level = 0; level < depth && joint?.isBone; level += 1, joint = joint.parent) {
        modelRoot.updateMatrixWorld(true);
        const jointPosition = new THREE.Vector3();
        const effectorPosition = new THREE.Vector3();
        joint.getWorldPosition(jointPosition);
        effector.getWorldPosition(effectorPosition);
        const towardEffector = effectorPosition.sub(jointPosition).normalize();
        const towardTarget = targetPosition.clone().sub(jointPosition).normalize();
        if (towardEffector.lengthSq() < 1e-8 || towardTarget.lengthSq() < 1e-8) continue;
        const delta = new THREE.Quaternion().setFromUnitVectors(towardEffector, towardTarget);
        const jointWorld = new THREE.Quaternion();
        joint.getWorldQuaternion(jointWorld);
        const desiredWorld = delta.multiply(jointWorld).normalize();
        if (joint.parent) {
          const parentWorld = new THREE.Quaternion();
          joint.parent.getWorldQuaternion(parentWorld);
          joint.quaternion.copy(parentWorld.invert().multiply(desiredWorld)).normalize();
        } else joint.quaternion.copy(desiredWorld);
        joint.updateMatrixWorld(true);
      }
    }
  }

  function rotateBoneToward(bone, fromDirection, toDirection) {
    if (fromDirection.lengthSq() < 1e-10 || toDirection.lengthSq() < 1e-10) return;
    const delta = new THREE.Quaternion().setFromUnitVectors(
      fromDirection.clone().normalize(), toDirection.clone().normalize(),
    );
    const boneWorld = new THREE.Quaternion();
    bone.getWorldQuaternion(boneWorld);
    const desiredWorld = delta.multiply(boneWorld).normalize();
    if (bone.parent) {
      const parentWorld = new THREE.Quaternion();
      bone.parent.getWorldQuaternion(parentWorld);
      bone.quaternion.copy(parentWorld.invert().multiply(desiredWorld)).normalize();
    } else bone.quaternion.copy(desiredWorld);
    bone.updateMatrixWorld(true);
  }

  function clampHipDirection(hip, desiredKnee, isLeft, upperLength) {
    const up = new THREE.Vector3(0, 1, 0).transformDirection(modelRoot.matrixWorld);
    const forward = new THREE.Vector3(0, 0, 1).transformDirection(modelRoot.matrixWorld);
    const right = new THREE.Vector3(1, 0, 0).transformDirection(modelRoot.matrixWorld);
    const direction = desiredKnee.clone().sub(hip).normalize();
    const downAmount = -direction.dot(up);
    const flexion = THREE.MathUtils.clamp(
      Math.atan2(direction.dot(forward), downAmount),
      -HUMAN_LIMITS.hipExtension, HUMAN_LIMITS.hipFlexion,
    );
    const sideSign = isLeft ? 1 : -1;
    const abduction = THREE.MathUtils.clamp(
      Math.atan2(sideSign * direction.dot(right), downAmount),
      -HUMAN_LIMITS.hipAdduction, HUMAN_LIMITS.hipAbduction,
    );
    const limited = up.clone().negate();
    limited.applyAxisAngle(right, -flexion);
    limited.applyAxisAngle(forward, sideSign * abduction);
    return hip.clone().add(limited.normalize().multiplyScalar(upperLength));
  }

  function clampAnkleLocalRotation(definition, bone) {
    if (definition.id !== "left_foot" && definition.id !== "right_foot") return;
    const rest = restState[bone.name];
    if (!rest) return;
    const restRotation = new THREE.Quaternion().fromArray(rest.rotation_xyzw);
    const relative = restRotation.clone().invert().multiply(bone.quaternion);
    const angles = new THREE.Euler().setFromQuaternion(relative, "XYZ");
    angles.x = THREE.MathUtils.clamp(
      angles.x, -HUMAN_LIMITS.anklePlantarflexion, HUMAN_LIMITS.ankleDorsiflexion,
    );
    angles.y = THREE.MathUtils.clamp(angles.y, -HUMAN_LIMITS.ankleSideTilt, HUMAN_LIMITS.ankleSideTilt);
    angles.z = THREE.MathUtils.clamp(angles.z, -HUMAN_LIMITS.ankleSideTilt, HUMAN_LIMITS.ankleSideTilt);
    bone.quaternion.copy(restRotation.multiply(new THREE.Quaternion().setFromEuler(angles))).normalize();
  }

  function solveTwoBoneLeg(effector, target, poleTarget = null) {
    const lower = effector.parent;
    const upper = lower?.parent;
    if (!lower?.isBone || !upper?.isBone) return;
    modelRoot.updateMatrixWorld(true);
    const hip = new THREE.Vector3();
    const knee = new THREE.Vector3();
    const ankle = new THREE.Vector3();
    upper.getWorldPosition(hip);
    lower.getWorldPosition(knee);
    effector.getWorldPosition(ankle);
    const upperLength = hip.distanceTo(knee);
    const lowerLength = knee.distanceTo(ankle);
    if (upperLength < 1e-6 || lowerLength < 1e-6) return;

    const direction = target.position.clone().sub(hip).normalize();
    if (direction.lengthSq() < 1e-8) return;
    // The knee pole controls forward bending. The solver keeps the ankle from
    // passing forward of the knee while preserving a natural lateral leg line.
    const forward = new THREE.Vector3(0, 0, 1).transformDirection(modelRoot.matrixWorld);
    forward.addScaledVector(direction, -forward.dot(direction));
    let pole = forward;
    if (pole.lengthSq() < 1e-8) pole.set(1, 0, 0);
    pole.normalize();
    const jointHint = poleTarget || knee.clone();
    const solved = solveTwoBoneWithJointHint(
      vectorArray(hip), vectorArray(target.position), vectorArray(jointHint), vectorArray(pole),
      upperLength, lowerLength, HUMAN_LIMITS.kneeFlexion,
    );
    const desiredKnee = clampHipDirection(
      hip, new THREE.Vector3().fromArray(solved.joint), effector.name.toLowerCase().includes("left"), upperLength,
    );
    const reachableTarget = new THREE.Vector3().fromArray(solved.end);

    rotateBoneToward(upper, knee.clone().sub(hip), desiredKnee.clone().sub(hip));
    modelRoot.updateMatrixWorld(true);
    lower.getWorldPosition(knee);
    effector.getWorldPosition(ankle);
    rotateBoneToward(lower, ankle.clone().sub(knee), reachableTarget.clone().sub(knee));
    modelRoot.updateMatrixWorld(true);
  }

  transform.addEventListener("objectChange", () => {
    activeTween = null;
    tweenQueue = [];
    if (selected) {
      if (usingIkTarget) {
        const bone = bones.get(selected.soma_joint);
        if (TWO_BONE_EFFECTORS.has(selected.id)) solveTwoBoneLeg(bone, ikTarget);
        else solveIk(bone, ikTarget, IK_DEPTH[selected.id]);
      }
      const flags = constrained.get(selected.id) || {position: false, rotation: false};
      flags[mode === "translate" ? "position" : "rotation"] = true;
      constrained.set(selected.id, flags);
    }
  });

  function setMode(nextMode) {
    mode = nextMode;
    for (const button of document.querySelectorAll("[data-pose-mode]")) {
      button.classList.toggle("active", button.dataset.poseMode === nextMode);
    }
    if (nextMode === "select") transform.detach();
    else if (selected) attachGizmo();
  }

  for (const button of document.querySelectorAll("[data-pose-mode]")) {
    button.addEventListener("click", () => setMode(button.dataset.poseMode));
  }
  $("pose-space").addEventListener("click", (event) => {
    const next = transform.space === "local" ? "world" : "local";
    transform.setSpace(next);
    event.currentTarget.textContent = next === "local" ? "Local" : "World";
  });
  $("pose-reset").addEventListener("click", () => {
    const confirmed = window.confirm(
      "현재 편집 중인 포즈의 관절 수정, 이름, AI 요청 기록을 모두 삭제하고 새 포즈로 초기화할까요?\n\n저장된 다른 포즈는 삭제되지 않습니다.",
    );
    if (!confirmed) return;
    activeTween = null;
    tweenQueue = [];
    restoreBoneState(bones, restState);
    constrained.clear();
    currentPoseRecord = {id: crypto.randomUUID(), revision: 0, edits: []};
    labelInput.value = "";
    presetSelect.value = "";
    renderAgentHistory();
    status.textContent = "새 빈 포즈를 만들고 기본 자세로 초기화했습니다.";
  });
  function makePose() {
    const controls = {};
    for (const [controlId, flags] of constrained) {
      const definition = schema.controls.find((item) => item.id === controlId);
      const bone = bones.get(definition.soma_joint);
      bone.updateWorldMatrix(true, false);
      const position = new THREE.Vector3();
      const rotation = new THREE.Quaternion();
      bone.getWorldPosition(position);
      bone.getWorldQuaternion(rotation);
      controls[controlId] = {space: "world", weight: 1.0};
      if (flags.position) controls[controlId].position = vectorArray(position);
      if (flags.rotation) controls[controlId].rotation_xyzw = quaternionArray(rotation);
    }
    return {
      label: labelInput.value,
      controls,
      bone_state: cloneBoneState(bones),
    };
  }

  function makeFullSnapshot() {
    modelRoot.updateMatrixWorld(true);
    const controls = {};
    for (const definition of schema.controls) {
      const bone = bones.get(definition.soma_joint);
      if (!bone) continue;
      const position = new THREE.Vector3();
      const rotation = new THREE.Quaternion();
      bone.getWorldPosition(position);
      bone.getWorldQuaternion(rotation);
      controls[definition.id] = {
        position: vectorArray(position),
        rotation_xyzw: quaternionArray(rotation),
        rest_position: structuredClone(restTransforms.get(definition.id)?.position),
        rest_rotation_xyzw: structuredClone(restTransforms.get(definition.id)?.rotation_xyzw),
        space: "world",
        weight: 1.0,
      };
    }
    return controls;
  }

  function applyKeypose(keypose) {
    tweenToKeypose(() => applyKeyposeInstant(keypose));
  }

  function applyKeyposeInstant(keypose) {
    restoreBoneState(bones, restState);
    constrained.clear();

    // Translation belongs only to the skeleton root. Every descendant keeps its
    // bind-pose local offset so parent * local FK preserves bone connectivity.
    const pelvisValue = keypose.controls.pelvis;
    const pelvis = bones.get(schema.controls.find((item) => item.id === "pelvis")?.soma_joint);
    if (pelvisValue?.position && pelvis) {
      const world = new THREE.Vector3().fromArray(pelvisValue.position);
      pelvis.position.copy(pelvis.parent ? pelvis.parent.worldToLocal(world) : world);
      constrained.set("pelvis", {position: true, rotation: false});
    }

    function applyWorldRotation(definition, value) {
      const bone = bones.get(definition.soma_joint);
      if (!bone || !value?.rotation_xyzw || HINGE_CONTROLS.has(definition.id)) return;
      modelRoot.updateMatrixWorld(true);
      const worldRotation = new THREE.Quaternion().fromArray(value.rotation_xyzw).normalize();
      if (bone.parent) {
        const parentRotation = new THREE.Quaternion();
        bone.parent.getWorldQuaternion(parentRotation);
        bone.quaternion.copy(parentRotation.invert().multiply(worldRotation));
      } else bone.quaternion.copy(worldRotation);
      clampAnkleLocalRotation(definition, bone);
      const flags = constrained.get(definition.id) || {position: false, rotation: false};
      flags.rotation = true;
      constrained.set(definition.id, flags);
      bone.updateMatrixWorld(true);
    }

    // Apply non-effector rotations in schema (parent-first) order. World rotations are
    // converted to locals against the already-updated parent hierarchy.
    for (const definition of schema.controls) {
      const value = keypose.controls[definition.id];
      if (!value) continue;
      // IK rotates ancestors, so an end-effector orientation applied here would
      // be changed again. Defer it until after all positional IK is complete.
      if (value.position && IK_DEPTH[definition.id] != null) continue;
      applyWorldRotation(definition, value);
    }

    // Limb positions are IK targets, never direct writes to child local
    // translations. CCD rotates ancestors while every bone length stays fixed.
    for (const definition of schema.controls) {
      const value = keypose.controls[definition.id];
      const depth = IK_DEPTH[definition.id];
      if (!value?.position || depth == null) continue;
      const pairedFoot = definition.id === "left_knee" ? "left_foot"
        : definition.id === "right_knee" ? "right_foot" : null;
      // A knee target is the bend-plane pole when a foot target exists. Do not
      // solve it independently and then overwrite that result with leg IK.
      if (pairedFoot && keypose.controls[pairedFoot]?.position) continue;
      const bone = bones.get(definition.soma_joint);
      if (!bone) continue;
      const target = new THREE.Object3D();
      target.position.fromArray(value.position);
      if (TWO_BONE_EFFECTORS.has(definition.id)) {
        const kneeId = definition.id === "left_foot" ? "left_knee" : "right_knee";
        const kneePosition = keypose.controls[kneeId]?.position;
        const poleTarget = kneePosition ? new THREE.Vector3().fromArray(kneePosition) : null;
        solveTwoBoneLeg(bone, target, poleTarget);
      }
      else solveIk(bone, target, depth);
      const flags = constrained.get(definition.id) || {position: false, rotation: false};
      flags.position = true;
      constrained.set(definition.id, flags);
    }
    modelRoot.updateMatrixWorld(true);

    // Toe IK may rotate the foot after the ankle target has been solved. Clamp
    // that final local ankle rotation before restoring optional orientations.
    for (const definition of schema.controls) {
      if (definition.id !== "left_foot" && definition.id !== "right_foot") continue;
      const bone = bones.get(definition.soma_joint);
      if (bone) clampAnkleLocalRotation(definition, bone);
    }
    modelRoot.updateMatrixWorld(true);

    // Restore desired end-effector orientation after ancestor rotations. A toe
    // position owns the foot direction, so a stored ankle rotation must not
    // undo the sole contact that was just solved.
    for (const definition of schema.controls) {
      const value = keypose.controls[definition.id];
      if (!value?.position || IK_DEPTH[definition.id] == null) continue;
      const pairedToe = definition.id === "left_foot" ? "left_toe"
        : definition.id === "right_foot" ? "right_toe" : null;
      if (pairedToe && keypose.controls[pairedToe]?.position) continue;
      applyWorldRotation(definition, value);
    }
    modelRoot.updateMatrixWorld(true);
  }

  async function pullPoseAgentState() {
    if ($("pose-workspace").hidden) return;
    try {
      const response = await fetch("/api/pose-agent/state");
      const state = await response.json();
      if (!response.ok || state.revision === agentRevision) return;
      agentRevision = state.revision;
      agentSubmit.disabled = state.status === "queued" || state.status === "running";
      if (state.status === "queued") agentStatus.textContent = "포즈 명령이 대기 중입니다...";
      else if (state.status === "running") agentStatus.textContent = "LLM 서브 에이전트가 포즈를 조절하고 있습니다...";
      else if (state.status === "failed") agentStatus.textContent = `포즈 조절 실패: ${state.error || "알 수 없는 오류"}`;
      else if (state.status === "complete" && state.pose) {
        currentPoseRecord = structuredClone(state.pose);
        renderAgentHistory();
        playKeyposeEdit(state.pose, state.summary || "수정된 포즈를 화면에 반영했습니다.");
        labelInput.value = state.pose.name || labelInput.value;
        status.textContent = "AI가 수정한 포즈가 적용되었습니다. 기즈모로 이어서 보정할 수 있습니다.";
      }
    } catch (_) {
      agentStatus.textContent = "WebUI 데몬의 포즈 에이전트 상태를 기다리는 중입니다...";
    }
  }

  agentSubmit.addEventListener("click", async () => {
    const instruction = agentInstruction.value.trim();
    if (!instruction) {
      agentStatus.textContent = "포즈 명령을 입력하세요.";
      return;
    }
    const current = makePose();
    agentSubmit.disabled = true;
    agentStatus.textContent = "현재 포즈를 WebUI 데몬으로 전달하는 중입니다...";
    try {
      const response = await fetch("/api/pose-agent/command", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          instruction,
          pose: {
            schema_version: schema.schema_version,
            id: currentPoseRecord.id,
            name: current.label.trim() || "현재 포즈",
            controls: current.controls,
            revision: currentPoseRecord.revision || 0,
            edits: structuredClone(currentPoseRecord.edits || []),
          },
          snapshot: makeFullSnapshot(),
        }),
      });
      const state = await response.json();
      if (!response.ok) throw new Error(state.error || "포즈 명령 전송 실패");
      agentRevision = -1;
      await pullPoseAgentState();
    } catch (error) {
      agentSubmit.disabled = false;
      agentStatus.textContent = error.message;
    }
  });

  async function loadPosePresets() {
    const response = await fetch("/api/keypose-presets");
    const data = await response.json();
    posePresets = data.items || [];
    presetSelect.innerHTML = '<option value="">포즈 프리셋...</option>';
    for (const preset of posePresets) {
      const option = document.createElement("option");
      option.value = preset.name;
      option.textContent = preset.name;
      presetSelect.appendChild(option);
    }
    options.onPresetsChanged?.(posePresets);
  }

  $("pose-preset-save").addEventListener("click", async () => {
    const keypose = makePose();
    if (!Object.keys(keypose.controls).length) {
      status.textContent = "먼저 포즈를 조작해 제약을 하나 이상 만드세요.";
      return;
    }
    const name = keypose.label.trim() || window.prompt("포즈 이름:", "새 포즈");
    if (!name) return;
    const response = await fetch("/api/keypose-presets", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({pose: {
        schema_version: schema.schema_version,
        id: currentPoseRecord.id || "",
        name,
        controls: keypose.controls,
        revision: currentPoseRecord.revision || 0,
        edits: structuredClone(currentPoseRecord.edits || []),
      }}),
    });
    const data = await response.json();
    if (!response.ok) { status.textContent = data.error || "프리셋 저장 실패"; return; }
    await loadPosePresets();
    presetSelect.value = name;
    status.textContent = `포즈 프리셋 '${name}'을 저장했습니다.`;
  });

  $("pose-preset-load").addEventListener("click", () => {
    const preset = posePresets.find((item) => item.name === presetSelect.value);
    if (!preset) return;
    const keypose = {label: preset.name, controls: structuredClone(preset.controls)};
    currentPoseRecord = structuredClone(preset);
    renderAgentHistory();
    labelInput.value = preset.name;
    applyKeypose(keypose);
    status.textContent = `'${preset.name}' 포즈를 불러왔습니다.`;
  });

  $("pose-preset-delete").addEventListener("click", async () => {
    const name = presetSelect.value;
    if (!name) return;
    const deletingCurrent = posePresets.some((item) => item.name === name && item.id === currentPoseRecord.id);
    await fetch("/api/keypose-presets/delete", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name}),
    });
    await loadPosePresets();
    if (deletingCurrent) {
      restoreBoneState(bones, restState);
      constrained.clear();
      currentPoseRecord = {id: crypto.randomUUID(), revision: 0, edits: []};
      labelInput.value = "";
      renderAgentHistory();
      status.textContent = `포즈 '${name}'을 삭제하고 새 빈 포즈로 전환했습니다.`;
    } else status.textContent = `포즈 프리셋 '${name}'을 삭제했습니다.`;
  });

  await loadPosePresets();
  await pullPoseAgentState();
  setInterval(pullPoseAgentState, 750);

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  renderer.domElement.addEventListener("pointerdown", (event) => {
    if (transform.dragging) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(markerTargets, false)[0];
    if (hit) selectControl(hit.object.userData.control.id);
  });

  window.addEventListener("keydown", (event) => {
    if ($("pose-workspace").hidden || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    if (event.key.toLowerCase() === "q") setMode("select");
    if (event.key.toLowerCase() === "w") setMode("translate");
    if (event.key.toLowerCase() === "e") setMode("rotate");
  });

  function resize() {
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);
  resize();

  function applyTweenFrame() {
    if (!activeTween) return;
    const {before, after, start, duration} = activeTween;
    const t = easeInOutCubic(Math.min(1, (performance.now() - start) / duration));
    for (const [name, target] of Object.entries(after)) {
      const bone = bones.get(name);
      const from = before[name];
      if (!bone || !from) continue;
      bone.position.lerpVectors(
        new THREE.Vector3().fromArray(from.position), new THREE.Vector3().fromArray(target.position), t,
      );
      bone.quaternion.slerpQuaternions(
        new THREE.Quaternion().fromArray(from.rotation_xyzw),
        new THREE.Quaternion().fromArray(target.rotation_xyzw), t,
      );
    }
    if (t >= 1) {
      if (activeTween.controlId) {
        const marker = markers.get(activeTween.controlId);
        if (marker) marker.material.color.setHex(markerColor);
      }
      advanceTweenQueue();
      if (!tweenQueue.length && !activeTween && tweenFinalMessage) {
        agentStatus.textContent = tweenFinalMessage;
        tweenFinalMessage = "";
      }
    }
  }

  function animate() {
    requestAnimationFrame(animate);
    orbit.update();
    applyTweenFrame();
    modelRoot.updateMatrixWorld(true);
    for (const definition of schema.controls) {
      const marker = markers.get(definition.id);
      const bone = bones.get(definition.soma_joint);
      if (marker && bone) bone.getWorldPosition(marker.position);
    }
    renderer.render(scene, camera);
  }
  animate();
  status.textContent = "부위를 선택하고 이동(W) 또는 회전(E) 기즈모로 조작하세요.";

  return {
    getCurrentPose: () => {
      const {bone_state: ignored, ...pose} = makePose();
      return pose;
    },
    reloadPresets: loadPosePresets,
    selectControl,
    setMode,
  };
}
