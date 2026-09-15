const $ = (id) => document.getElementById(id);

const els = {
  prompt: $("prompt"),
  frameCount: $("frame-count"),
  frameCountRange: $("frame-count-range"),
  frameCountVal: $("frame-count-val"),
  steps: $("steps"),
  stepsRange: $("steps-range"),
  stepsVal: $("steps-val"),
  seed: $("seed"),
  seedRandom: $("seed-random"),
  backend: $("backend"),
  modelPath: $("model-path"),
  textBundlePath: $("text-bundle-path"),
  generateBtn: $("generate-btn"),
  progress: $("progress"),
  error: $("error"),
  viewer: $("viewer"),
  info: $("info"),
  downloadLink: $("download-link"),
  historyList: $("history-list"),
  statusBanner: $("status-banner"),
};

function syncRangeAndNumber(range, number, label) {
  range.addEventListener("input", () => { number.value = range.value; label.textContent = range.value; });
  number.addEventListener("input", () => { range.value = number.value; label.textContent = number.value; });
}
syncRangeAndNumber(els.frameCountRange, els.frameCount, els.frameCountVal);
syncRangeAndNumber(els.stepsRange, els.steps, els.stepsVal);

els.seedRandom.addEventListener("click", () => {
  els.seed.value = Math.floor(Math.random() * 2147483647);
});

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch { return iso; }
}

function showResult(meta) {
  els.viewer.src = meta.glb_url;
  els.viewer.removeAttribute("poster");
  els.downloadLink.href = meta.glb_url;
  els.downloadLink.hidden = false;
  els.info.innerHTML = `
    <span><b>Prompt:</b> ${escapeHtml(meta.prompt)}</span>
    <span><b>Frames:</b> ${meta.frame_count}</span>
    <span><b>Steps:</b> ${meta.steps}</span>
    <span><b>Seed:</b> ${meta.seed}</span>
    <span><b>Backend:</b> ${meta.backend}</span>
    <span><b>소요:</b> ${meta.elapsed_sec}s</span>
    <span><b>생성:</b> ${fmtTime(meta.created_at)}</span>
  `;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function loadIntoForm(meta) {
  els.prompt.value = meta.prompt;
  els.frameCount.value = meta.frame_count;
  els.frameCountRange.value = Math.min(Math.max(meta.frame_count, els.frameCountRange.min), els.frameCountRange.max);
  els.frameCountVal.textContent = meta.frame_count;
  els.steps.value = meta.steps;
  els.stepsRange.value = Math.min(Math.max(meta.steps, els.stepsRange.min), els.stepsRange.max);
  els.stepsVal.textContent = meta.steps;
  els.seed.value = meta.seed;
  els.backend.value = meta.backend;
  showResult(meta);
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

async function refreshHistory() {
  const res = await fetch("/api/history");
  const data = await res.json();
  els.historyList.innerHTML = "";
  for (const meta of data.items) {
    const card = document.createElement("div");
    card.className = "history-card";
    card.innerHTML = `
      <div class="prompt">${escapeHtml(meta.prompt)}</div>
      <div class="meta">${meta.frame_count}f · ${meta.steps} steps · seed ${meta.seed} · ${meta.backend} · ${fmtTime(meta.created_at)}</div>
    `;
    card.addEventListener("click", () => loadIntoForm(meta));
    els.historyList.appendChild(card);
  }
}

els.generateBtn.addEventListener("click", async () => {
  els.error.hidden = true;
  const body = {
    prompt: els.prompt.value,
    frame_count: parseInt(els.frameCount.value, 10),
    steps: parseInt(els.steps.value, 10),
    seed: els.seed.value === "" ? null : parseInt(els.seed.value, 10),
    backend: els.backend.value,
    model: els.modelPath.value || undefined,
    text_bundle: els.textBundlePath.value || undefined,
  };

  els.generateBtn.disabled = true;
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
    showResult(data);
    await refreshHistory();
  } catch (e) {
    els.error.textContent = e.message;
    els.error.hidden = false;
  } finally {
    els.generateBtn.disabled = false;
    els.progress.hidden = true;
    refreshStatus();
  }
});

els.backend.addEventListener("change", refreshStatus);

refreshStatus();
refreshHistory();
