// Restore a complete generation request. Missing optional fields clear old state.
export function restoreGenerationForm(els, meta, keyposes, {toggleStoryboard, addSegment, renderPoses}) {
  els.storyboardToggle.checked = !!meta.sequence_mode;
  els.prompt.value = meta.sequence_mode ? "" : (meta.prompt || "");
  els.negativePrompt.value = meta.negative_prompt || "";
  els.transitionFrames.value = meta.transition_frames ?? 15;
  els.segmentList.innerHTML = "";
  for (const segment of meta.segments || []) addSegment(segment.frame_count, segment.prompt);
  const frames = meta.sequence_mode ? 120 : (meta.frame_count ?? 120);
  for (const [field, value] of [["frameCount", frames], ["steps", meta.steps ?? 50], ["textCfg", meta.text_cfg ?? 2]]) {
    els[field].value = value;
    els[`${field}Range`].value = value;
    els[`${field}Val`].textContent = value;
  }
  els.seed.value = meta.seed;
  els.backend.value = meta.backend || "vulkan";
  els.batchCount.value = 1; // Reproduce this sample; start a new batch explicitly.
  els.modelPath.value = meta.model || "";
  els.textBundlePath.value = meta.text_bundle || "";
  els.motionModel.value = meta.model || "";
  els.textEncoder.value = meta.text_bundle || "";
  keyposes.clear();
  for (const pose of meta.keyposes?.keyposes || []) {
    keyposes.set(pose.frame, structuredClone(pose));
  }
  toggleStoryboard();
  renderPoses();
}

export function samplesInBatch(items, selected) {
  if (!selected.batch_id) return [selected];
  return items.filter((item) => item.batch_id === selected.batch_id)
    .sort((a, b) => a.batch_index - b.batch_index);
}
