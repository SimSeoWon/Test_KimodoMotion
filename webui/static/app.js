const $ = (id) => document.getElementById(id);

const els = {
  prompt: $("prompt"),
  negativePrompt: $("negative-prompt"),
  captionImageInput: $("caption-image-input"),
  captionStatus: $("caption-status"),
  frameCount: $("frame-count"),
  frameCountRange: $("frame-count-range"),
  frameCountVal: $("frame-count-val"),
  steps: $("steps"),
  stepsRange: $("steps-range"),
  stepsVal: $("steps-val"),
  textCfg: $("text-cfg"),
  textCfgRange: $("text-cfg-range"),
  textCfgVal: $("text-cfg-val"),
  seed: $("seed"),
  seedRandom: $("seed-random"),
  backend: $("backend"),
  mixamoModel: $("mixamo-model"),
  modelPath: $("model-path"),
  textBundlePath: $("text-bundle-path"),
  batchCount: $("batch-count"),
  generateBtn: $("generate-btn"),
  cancelBtn: $("cancel-btn"),
  progress: $("progress"),
  error: $("error"),
  viewer: $("viewer"),
  info: $("info"),
  downloadLink: $("download-link"),
  historyList: $("history-list"),
  statusBanner: $("status-banner"),
  viewerCaption: $("viewer-caption"),
  presetSelect: $("preset-select"),
  presetSave: $("preset-save"),
  presetDelete: $("preset-delete"),
  storyboardToggle: $("storyboard-toggle"),
  singlePromptPanel: $("single-prompt-panel"),
  storyboardPanel: $("storyboard-panel"),
  transitionFrames: $("transition-frames"),
  segmentList: $("segment-list"),
  addSegmentBtn: $("add-segment-btn"),
  timelineBar: $("timeline-bar"),
  posingToggle: $("posing-toggle"),
  posingPanel: $("posing-panel"),
};

function syncRangeAndNumber(range, number, label) {
  range.addEventListener("input", () => { number.value = range.value; label.textContent = range.value; });
  number.addEventListener("input", () => { range.value = number.value; label.textContent = number.value; });
}
syncRangeAndNumber(els.frameCountRange, els.frameCount, els.frameCountVal);
syncRangeAndNumber(els.stepsRange, els.steps, els.stepsVal);
syncRangeAndNumber(els.textCfgRange, els.textCfg, els.textCfgVal);

els.seedRandom.addEventListener("click", () => {
  els.seed.value = Math.floor(Math.random() * 2147483647);
});

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch { return iso; }
}

let showingRealResult = false;

function showResult(meta, extraNote) {
  showingRealResult = true;
  els.viewer.src = meta.glb_url;
  els.viewer.removeAttribute("poster");
  els.viewerCaption.hidden = true;
  els.downloadLink.href = meta.glb_url;
  els.downloadLink.hidden = false;
  els.info.innerHTML = `
    <span><b>Prompt:</b> ${escapeHtml(meta.prompt)}${meta.sequence_mode ? " (스토리보드)" : ""}</span>
    ${meta.negative_prompt ? `<span><b>Negative:</b> ${escapeHtml(meta.negative_prompt)}</span>` : ""}
    <span><b>Frames:</b> ${meta.frame_count}</span>
    <span><b>Steps:</b> ${meta.steps}</span>
    <span><b>Seed:</b> ${meta.seed}</span>
    <span><b>Backend:</b> ${meta.backend}</span>
    ${meta.text_cfg != null ? `<span><b>CFG:</b> ${meta.text_cfg}</span>` : ""}
    <span><b>소요:</b> ${meta.elapsed_sec}s</span>
    <span><b>생성:</b> ${fmtTime(meta.created_at)}</span>
    ${extraNote ? `<span>${escapeHtml(extraNote)}</span>` : ""}
  `;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

const TIMELINE_COLORS = ["#5b9dff", "#4fd18b", "#ffb84f", "#ff6b9d", "#a78bfa", "#4fd1c5"];

function addSegmentRow(frameCount, promptText) {
  const row = document.createElement("div");
  row.className = "segment-row";
  row.innerHTML = `
    <input type="number" class="segment-frames" min="2" max="300" value="${frameCount}" title="프레임 수">
    <div class="segment-prompt-col">
      <textarea class="segment-prompt" rows="2" placeholder="이 구간의 프롬프트"></textarea>
      <label class="segment-caption-label">
        사진으로 이 구간 채우기
        <input type="file" class="segment-caption-input" accept="image/*" title="사진에서 캡션 뽑기">
      </label>
      <span class="segment-caption-status" role="status" hidden></span>
    </div>
    <button type="button" class="segment-remove" title="구간 삭제">✕</button>
  `;
  const promptEl = row.querySelector(".segment-prompt");
  promptEl.value = promptText || "";
  row.querySelector(".segment-remove").addEventListener("click", () => {
    row.remove();
    renderTimeline();
  });
  row.querySelector(".segment-frames").addEventListener("input", renderTimeline);
  promptEl.addEventListener("input", renderTimeline);

  const captionInput = row.querySelector(".segment-caption-input");
  const captionStatus = row.querySelector(".segment-caption-status");
  captionInput.addEventListener("change", async () => {
    const file = captionInput.files[0];
    if (!file) return;
    captionStatus.hidden = false;
    captionStatus.textContent = "캡션 추출 중...";
    captionInput.disabled = true;
    try {
      const caption = await captionImageFile(file);
      promptEl.value = caption;
      captionStatus.textContent = `캡션: "${caption}" — 필요하면 동작 위주로 다듬으세요.`;
      renderTimeline();
    } catch (e) {
      captionStatus.textContent = "캡션 추출 실패: " + e.message;
    } finally {
      captionInput.disabled = false;
      captionInput.value = "";
    }
  });

  els.segmentList.appendChild(row);
  renderTimeline();
}

function collectSegments() {
  return Array.from(els.segmentList.querySelectorAll(".segment-row")).map((row) => ({
    frame_count: parseInt(row.querySelector(".segment-frames").value, 10),
    prompt: row.querySelector(".segment-prompt").value,
  }));
}

// Deforum류 "prompt schedule" 타임라인 바 — 구간별 프레임 수에 비례해 폭을 나누고, 클릭하면
// 아래 해당 입력행으로 스크롤+포커스한다. 편집은 여전히 리스트(segment-row)에서 하고, 이건
// 그 상태를 그대로 반영하는 읽기 전용 미리보기라 드래그 리사이즈 등 입력 로직 중복이 없다.
function renderTimeline() {
  const segments = collectSegments();
  els.timelineBar.innerHTML = "";
  if (segments.length === 0) {
    const empty = document.createElement("div");
    empty.className = "timeline-segment empty";
    empty.textContent = "구간을 추가하면 여기에 타임라인이 표시됩니다";
    els.timelineBar.appendChild(empty);
    return;
  }
  const total = segments.reduce((sum, s) => sum + Math.max(s.frame_count || 0, 1), 0);
  const rows = els.segmentList.querySelectorAll(".segment-row");
  segments.forEach((seg, i) => {
    const block = document.createElement("div");
    block.className = "timeline-segment";
    block.style.flexBasis = `${(Math.max(seg.frame_count || 0, 1) / total) * 100}%`;
    block.style.background = TIMELINE_COLORS[i % TIMELINE_COLORS.length];
    const label = seg.prompt.trim() || `구간 ${i + 1}`;
    block.title = `${label} — ${seg.frame_count}프레임`;
    block.textContent = label.length > 14 ? label.slice(0, 14) + "…" : label;
    block.addEventListener("click", () => {
      const row = rows[i];
      if (!row) return;
      row.scrollIntoView({ behavior: "smooth", block: "center" });
      row.querySelector(".segment-prompt").focus();
    });
    els.timelineBar.appendChild(block);
  });
}

function toggleStoryboardPanels() {
  const on = els.storyboardToggle.checked;
  els.singlePromptPanel.hidden = on;
  els.storyboardPanel.hidden = !on;
  if (on && els.segmentList.children.length === 0) {
    addSegmentRow(60, "");
    addSegmentRow(60, "");
  }
  renderTimeline();
}

function loadIntoForm(meta) {
  els.storyboardToggle.checked = !!meta.sequence_mode;
  toggleStoryboardPanels();
  if (meta.sequence_mode && meta.segments) {
    els.transitionFrames.value = meta.transition_frames || 15;
    els.segmentList.innerHTML = "";
    for (const seg of meta.segments) addSegmentRow(seg.frame_count, seg.prompt);
  } else {
    els.prompt.value = meta.prompt;
    els.negativePrompt.value = meta.negative_prompt || "";
    els.frameCount.value = meta.frame_count;
    els.frameCountRange.value = Math.min(Math.max(meta.frame_count, els.frameCountRange.min), els.frameCountRange.max);
    els.frameCountVal.textContent = meta.frame_count;
  }
  els.steps.value = meta.steps;
  els.stepsRange.value = Math.min(Math.max(meta.steps, els.stepsRange.min), els.stepsRange.max);
  els.stepsVal.textContent = meta.steps;
  if (meta.text_cfg != null) {
    els.textCfg.value = meta.text_cfg;
    els.textCfgRange.value = Math.min(Math.max(meta.text_cfg, els.textCfgRange.min), els.textCfgRange.max);
    els.textCfgVal.textContent = meta.text_cfg;
  }
  els.seed.value = meta.seed;
  els.backend.value = meta.backend;
  if (meta.mixamo_model) els.mixamoModel.value = meta.mixamo_model;
  showResult(meta);
}

let presetItems = [];

async function loadPresets() {
  try {
    const res = await fetch("/api/presets");
    const data = await res.json();
    presetItems = data.items || [];
    els.presetSelect.innerHTML = '<option value="">프리셋 불러오기...</option>';
    for (const p of presetItems) {
      const opt = document.createElement("option");
      opt.value = p.name;
      opt.textContent = p.name;
      els.presetSelect.appendChild(opt);
    }
  } catch (e) {
    // 서버가 아직 안 떠있는 경우 등 — 조용히 무시
  }
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const s = await res.json();
    if (!s.kmd_generate_exists) {
      els.statusBanner.textContent = "kmd-generate.exe가 없습니다 — README의 빌드 단계를 먼저 실행하세요.";
      els.statusBanner.hidden = false;
    } else if (!s.model_exists) {
      els.statusBanner.textContent = "모델 가중치가 없습니다 — download_gguf_weights.py로 먼저 받으세요.";
      els.statusBanner.hidden = false;
    } else if (!s.vulkan_available && els.backend.value === "vulkan") {
      els.statusBanner.textContent = "Vulkan 런타임을 찾지 못했습니다 — 백엔드를 CPU로 바꾸거나 GPU 드라이버를 확인하세요.";
      els.statusBanner.hidden = false;
    } else if (s.editor_running && els.backend.value === "vulkan") {
      els.statusBanner.textContent = "UnrealEditor가 실행 중입니다 — Vulkan 백엔드는 VRAM을 에디터와 나눠 씁니다. 필요하면 백엔드를 CPU로 바꾸세요.";
      els.statusBanner.hidden = false;
    } else {
      els.statusBanner.hidden = true;
    }
  } catch (e) {
    // 서버가 아직 안 떠있는 경우 등 — 조용히 무시
  }
}

function showTposePreview() {
  if (showingRealResult) return; // 실제 생성 결과를 보고 있으면 콤보박스를 바꿔도 안 건드림
  const modelId = els.mixamoModel.value || "capsule";
  els.viewer.removeAttribute("poster");
  els.viewer.src = "/api/tpose?model=" + encodeURIComponent(modelId);
  els.viewerCaption.textContent = "T포즈 미리보기 — 프롬프트를 입력하고 Generate를 눌러보세요";
  els.viewerCaption.hidden = false;
}

async function loadMixamoModels() {
  try {
    const res = await fetch("/api/mixamo-models");
    const data = await res.json();
    els.mixamoModel.innerHTML = "";
    for (const m of data.items || []) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.label;
      els.mixamoModel.appendChild(opt);
    }
    els.mixamoModel.value = data.default || "capsule";
    showTposePreview();
  } catch (e) {
    // 서버가 아직 안 떠있는 경우 등 — 조용히 무시
  }
}

async function refreshHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  els.historyList.innerHTML = "";
  for (const meta of data.items) {
    const card = document.createElement("div");
    card.className = "history-card";
    card.innerHTML = `
      <div class="prompt">${meta.sequence_mode ? "🎬 " : ""}${escapeHtml(meta.prompt)}</div>
      <div class="meta">${meta.frame_count}f · ${meta.steps} steps · seed ${meta.seed} · ${meta.backend} · ${fmtTime(meta.created_at)}</div>
    `;
    card.addEventListener("click", () => loadIntoForm(meta));
    els.historyList.appendChild(card);
  }
}

els.generateBtn.addEventListener("click", async () => {
  els.error.hidden = true;
  const body = {
    steps: parseInt(els.steps.value, 10),
    seed: els.seed.value === "" ? null : parseInt(els.seed.value, 10),
    backend: els.backend.value,
    mixamo_model: els.mixamoModel.value || undefined,
    model: els.modelPath.value || undefined,
    text_bundle: els.textBundlePath.value || undefined,
    batch_count: parseInt(els.batchCount.value, 10) || 1,
    text_cfg: els.textCfg.value === "" ? undefined : parseFloat(els.textCfg.value),
  };
  if (els.storyboardToggle.checked) {
    body.segments = collectSegments();
    body.transition_frames = parseInt(els.transitionFrames.value, 10);
  } else {
    body.prompt = els.prompt.value;
    body.frame_count = parseInt(els.frameCount.value, 10);
    body.negative_prompt = els.negativePrompt.value || undefined;
  }
  if (poseEditor) body.keyposes = poseEditor.getDocument();

  els.generateBtn.disabled = true;
  els.cancelBtn.hidden = false;
  els.progress.hidden = false;

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `요청 실패 (${res.status})`);
    }
    const metas = data.items || [data];
    showResult(metas[0], metas.length > 1 ? `배치 ${metas.length}개 생성됨 — 히스토리에서 나머지 확인` : null);
    await refreshHistory();
  } catch (e) {
    els.error.textContent = e.message;
    els.error.hidden = false;
  } finally {
    els.generateBtn.disabled = false;
    els.cancelBtn.hidden = true;
    els.progress.hidden = true;
    refreshStatus();
  }
});

els.cancelBtn.addEventListener("click", async () => {
  els.cancelBtn.disabled = true;
  try {
    await fetch("/api/cancel", { method: "POST" });
  } catch (e) {
    // 무시 — finally 블록의 상태 갱신이 곧 이어짐
  } finally {
    els.cancelBtn.disabled = false;
  }
});

els.storyboardToggle.addEventListener("change", toggleStoryboardPanels);
els.addSegmentBtn.addEventListener("click", () => addSegmentRow(60, ""));

els.presetSelect.addEventListener("change", () => {
  const p = presetItems.find((item) => item.name === els.presetSelect.value);
  if (p) els.prompt.value = p.prompt;
});
els.presetSave.addEventListener("click", async () => {
  const promptText = els.prompt.value.trim();
  if (!promptText) {
    alert("저장할 프롬프트를 먼저 입력하세요.");
    return;
  }
  const name = window.prompt("프리셋 이름:", promptText.slice(0, 20));
  if (!name) return;
  await fetch("/api/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, prompt: promptText }),
  });
  await loadPresets();
  els.presetSelect.value = name;
});
els.presetDelete.addEventListener("click", async () => {
  const name = els.presetSelect.value;
  if (!name) return;
  await fetch("/api/presets/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await loadPresets();
});

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function captionImageFile(file) {
  const base64 = await fileToBase64(file);
  const ext = "." + (file.name.split(".").pop() || "jpg");
  const res = await fetch("/api/caption", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_base64: base64, ext }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
  return data.caption;
}

els.captionImageInput.addEventListener("change", async () => {
  const file = els.captionImageInput.files[0];
  if (!file) return;
  els.captionStatus.hidden = false;
  els.captionStatus.textContent = "캡션 추출 중... (처음 한 번은 모델을 CPU로 로드하느라 몇 초 더 걸릴 수 있음)";
  try {
    const caption = await captionImageFile(file);
    els.prompt.value = caption;
    els.captionStatus.textContent = `캡션: "${caption}" — 필요하면 직접 다듬어서 Generate 하세요.`;
  } catch (e) {
    els.captionStatus.textContent = "캡션 추출 실패: " + e.message;
  } finally {
    els.captionImageInput.value = "";
  }
});

els.backend.addEventListener("change", refreshStatus);
els.mixamoModel.addEventListener("change", showTposePreview);

let poseEditor = null;
els.posingToggle.addEventListener("click", async () => {
  const opening = els.posingPanel.hidden;
  els.posingPanel.hidden = !opening;
  els.viewer.hidden = opening;
  els.viewerCaption.hidden = opening || els.viewerCaption.textContent === "";
  els.posingToggle.textContent = opening ? "포징 모드 닫기" : "포징 모드";
  if (!opening) return;
  if (!poseEditor) {
    const poseStatus = $("pose-status");
    try {
      poseStatus.textContent = "포징 편집기 모듈을 불러오는 중...";
      const { createKeyposeEditor } = await import("/static/keypose-editor.mjs");
      poseEditor = await createKeyposeEditor({
        modelUrl: () => "/api/tpose?model=" + encodeURIComponent(els.mixamoModel.value || "capsule"),
        frameCount: () => els.storyboardToggle.checked
          ? collectSegments().reduce((sum, segment) => sum + (segment.frame_count || 0), 0)
          : parseInt(els.frameCount.value, 10),
      });
    } catch (error) {
      console.error("포징 편집기 초기화 실패", error);
      poseStatus.textContent = "포징 편집기 초기화 실패: " + error.message;
      poseEditor = null;
    }
  }
});

// 서버가 T포즈 미리보기를 못 만들었을 수 있음(Blender/Mixamo 리소스 없음 등) — 그때는
// 조용히 빈 화면 대신 안내 문구로 대체한다.
els.viewer.addEventListener("error", () => {
  if (showingRealResult) return;
  els.viewer.removeAttribute("src");
  els.viewerCaption.textContent = "이 캐릭터의 미리보기를 만들지 못했습니다 (콘솔 로그 확인)";
  els.viewerCaption.hidden = false;
});

refreshStatus();
refreshHistory();
loadMixamoModels();
loadPresets();
