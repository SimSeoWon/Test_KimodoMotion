import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";

const $ = (id) => document.getElementById(id);
const markerColor = 0x4fd18b;
const selectedColor = 0xffb84f;
const IK_DEPTH = {
  left_hand: 2, right_hand: 2,
  left_foot: 2, right_foot: 2,
  left_elbow: 1, right_elbow: 1,
  left_knee: 1, right_knee: 1,
};

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
  const frameInput = $("pose-frame");
  const labelInput = $("pose-label");
  const keyposeList = $("pose-keyposes");
  const controlList = $("pose-controls");
  const presetSelect = $("pose-preset");
  let posePresets = [];

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
  const keyposes = new Map();
  let selected = null;
  let restState = null;
  let modelRoot = null;
  let mode = "select";
  let stateRevision = -1;
  let usingIkTarget = false;

  const gltf = await new GLTFLoader().loadAsync(options.modelUrl());
  modelRoot = gltf.scene;
  scene.add(modelRoot);
  modelRoot.traverse((object) => {
    if (object.isBone) bones.set(object.name, object);
  });
  restState = cloneBoneState(bones);

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
    usingIkTarget = mode === "translate" && IK_DEPTH[selected.id] != null;
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

  transform.addEventListener("objectChange", () => {
    if (selected) {
      if (usingIkTarget) solveIk(bones.get(selected.soma_joint), ikTarget, IK_DEPTH[selected.id]);
      const flags = constrained.get(selected.id) || {position: false, rotation: false};
      flags[mode === "translate" ? "position" : "rotation"] = true;
      constrained.set(selected.id, flags);
      if (!usingIkTarget) {
        const selectedBone = bones.get(selected.soma_joint);
        for (const definition of schema.controls) {
          if (definition.id === selected.id) continue;
          let ancestor = bones.get(definition.soma_joint)?.parent;
          while (ancestor?.isBone && ancestor !== selectedBone) ancestor = ancestor.parent;
          if (ancestor !== selectedBone) continue;
          const childFlags = constrained.get(definition.id) || {position: false, rotation: false};
          childFlags.position = true;
          childFlags.rotation = true;
          constrained.set(definition.id, childFlags);
        }
      }
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
    restoreBoneState(bones, restState);
    constrained.clear();
    status.textContent = "기본 포즈로 되돌렸습니다.";
  });
  async function runHistoryCommand(name) {
    const response = await fetch("/api/keyposes/command", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name, arguments: {}}),
    });
    if (!response.ok) throw new Error("포즈 이력 명령에 실패했습니다.");
    stateRevision = -1;
    await pullAgentState();
  }
  $("pose-undo").addEventListener("click", () => runHistoryCommand("undo_pose_edit"));
  $("pose-redo").addEventListener("click", () => runHistoryCommand("redo_pose_edit"));

  function makeDocument() {
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
      frame: Number.parseInt(frameInput.value, 10),
      label: labelInput.value,
      controls,
      bone_state: cloneBoneState(bones),
    };
  }

  async function validateDocument() {
    const document = {
      schema_version: schema.schema_version,
      keyposes: [...keyposes.values()].map(({bone_state: ignored, ...keypose}) => keypose),
    };
    const response = await fetch("/api/keyposes/validate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({document, frame_count: options.frameCount()}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "키포즈 검증 실패");
    return result.document;
  }

  async function publishDocument() {
    const document = await validateDocument();
    const response = await fetch("/api/keyposes/document", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({document, frame_count: options.frameCount()}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "키포즈 저장 실패");
    stateRevision = result.revision;
  }

  function applyKeypose(keypose) {
    restoreBoneState(bones, restState);
    constrained.clear();
    for (const definition of schema.controls) {
      const value = keypose.controls[definition.id];
      if (!value) continue;
      const bone = bones.get(definition.soma_joint);
      if (!bone) continue;
      modelRoot.updateMatrixWorld(true);
      if (value.position) {
        const world = new THREE.Vector3().fromArray(value.position);
        bone.position.copy(bone.parent ? bone.parent.worldToLocal(world) : world);
        const flags = constrained.get(definition.id) || {position: false, rotation: false};
        flags.position = true;
        constrained.set(definition.id, flags);
      }
      if (value.rotation_xyzw) {
        const worldRotation = new THREE.Quaternion().fromArray(value.rotation_xyzw).normalize();
        if (bone.parent) {
          const parentRotation = new THREE.Quaternion();
          bone.parent.getWorldQuaternion(parentRotation);
          bone.quaternion.copy(parentRotation.invert().multiply(worldRotation));
        } else bone.quaternion.copy(worldRotation);
        const flags = constrained.get(definition.id) || {position: false, rotation: false};
        flags.rotation = true;
        constrained.set(definition.id, flags);
      }
      bone.updateMatrixWorld(true);
    }
  }

  function renderKeyposes() {
    keyposeList.innerHTML = "";
    for (const keypose of [...keyposes.values()].sort((a, b) => a.frame - b.frame)) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${keypose.frame}f ${keypose.label || "키포즈"}`;
      button.classList.toggle("active", Number.parseInt(frameInput.value, 10) === keypose.frame);
      button.addEventListener("click", () => {
        frameInput.value = keypose.frame;
        labelInput.value = keypose.label;
        if (keypose.bone_state) restoreBoneState(bones, keypose.bone_state);
        else applyKeypose(keypose);
        renderKeyposes();
      });
      keyposeList.appendChild(button);
    }
  }

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
  }

  $("pose-preset-save").addEventListener("click", async () => {
    const keypose = makeDocument();
    if (!Object.keys(keypose.controls).length) {
      status.textContent = "먼저 포즈를 조작해 제약을 하나 이상 만드세요.";
      return;
    }
    const name = window.prompt("포즈 프리셋 이름:", keypose.label || "새 포즈");
    if (!name) return;
    const response = await fetch("/api/keypose-presets", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name, controls: keypose.controls}),
    });
    const data = await response.json();
    if (!response.ok) { status.textContent = data.error || "프리셋 저장 실패"; return; }
    await loadPosePresets();
    presetSelect.value = name;
    status.textContent = `포즈 프리셋 '${name}'을 저장했습니다.`;
  });

  $("pose-preset-apply").addEventListener("click", async () => {
    const preset = posePresets.find((item) => item.name === presetSelect.value);
    if (!preset) return;
    const frame = Number.parseInt(frameInput.value, 10);
    const keypose = {frame, label: preset.name, controls: structuredClone(preset.controls)};
    keyposes.set(frame, keypose);
    labelInput.value = preset.name;
    applyKeypose(keypose);
    await publishDocument();
    renderKeyposes();
    status.textContent = `'${preset.name}' 포즈를 ${frame}프레임에 배치했습니다.`;
  });

  $("pose-preset-delete").addEventListener("click", async () => {
    const name = presetSelect.value;
    if (!name) return;
    await fetch("/api/keypose-presets/delete", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name}),
    });
    await loadPosePresets();
    status.textContent = `포즈 프리셋 '${name}'을 삭제했습니다.`;
  });

  $("pose-save").addEventListener("click", async () => {
    try {
      const keypose = makeDocument();
      keyposes.set(keypose.frame, keypose);
      await publishDocument();
      renderKeyposes();
      status.textContent = `${keypose.frame}프레임 키포즈를 저장했습니다.`;
    } catch (error) {
      keyposes.delete(Number.parseInt(frameInput.value, 10));
      status.textContent = error.message;
    }
  });
  $("pose-delete").addEventListener("click", () => {
    keyposes.delete(Number.parseInt(frameInput.value, 10));
    renderKeyposes();
    status.textContent = "키포즈를 삭제했습니다.";
    publishDocument().catch((error) => { status.textContent = error.message; });
  });

  async function pullAgentState() {
    try {
      const response = await fetch("/api/keyposes/state");
      const state = await response.json();
      if (!response.ok || state.revision === stateRevision) return;
      stateRevision = state.revision;
      keyposes.clear();
      for (const keypose of state.document.keyposes || []) keyposes.set(keypose.frame, keypose);
      renderKeyposes();
      status.textContent = "Claude/Codex 또는 API의 키포즈 변경을 반영했습니다.";
    } catch (error) {
      // Local server may be restarting; the next poll will retry.
    }
  }
  await pullAgentState();
  await loadPosePresets();
  setInterval(() => { if (!$("posing-panel").hidden) pullAgentState(); }, 1000);

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
    if ($("posing-panel").hidden || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    if (event.key.toLowerCase() === "q") setMode("select");
    if (event.key.toLowerCase() === "w") setMode("translate");
    if (event.key.toLowerCase() === "e") setMode("rotate");
    if (event.ctrlKey && event.key.toLowerCase() === "z") { event.preventDefault(); runHistoryCommand("undo_pose_edit"); }
    if (event.ctrlKey && event.key.toLowerCase() === "y") { event.preventDefault(); runHistoryCommand("redo_pose_edit"); }
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

  function animate() {
    requestAnimationFrame(animate);
    orbit.update();
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
    getDocument: () => ({
      schema_version: schema.schema_version,
      keyposes: [...keyposes.values()].map(({bone_state: ignored, ...keypose}) => keypose),
    }),
    selectControl,
    setMode,
  };
}
