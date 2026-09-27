import assert from 'node:assert/strict';
import {test} from 'node:test';
import {restoreGenerationForm, samplesInBatch} from '../static/generation-form.mjs';

test('history replaces prior keyposes and resets missing optional generation settings', () => {
  const els = new Proxy({}, {get(target, key) { return target[key] ||= {value: 'old', textContent: '', innerHTML: ''}; }});
  const poses = new Map([[99, {frame: 99}]]);
  let rendered = false;
  const stored = {frame: 0, skeleton: 'soma30', controls: {pelvis: {position: [0, 1, 0]}}};
  const meta = {prompt: 'walk', seed: 42, frame_count: 120, steps: 50, text_cfg: null,
    keyposes: {keyposes: [stored]}, model: 'model.gguf', text_bundle: 'encoder.gguf'};
  const callbacks = {toggleStoryboard() {}, addSegment() {}, renderPoses() { rendered = true; }};
  restoreGenerationForm(els, meta, poses, callbacks);
  assert.deepEqual([...poses.keys()], [0]);
  assert.equal(els.textCfg.value, 2);
  assert.equal(els.negativePrompt.value, '');
  assert.equal(els.batchCount.value, 1);
  assert.equal(els.modelPath.value, 'model.gguf');
  assert.ok(rendered);
  poses.get(0).controls.pelvis.position[1] = 9;
  assert.equal(stored.controls.pelvis.position[1], 1);
  restoreGenerationForm(els, {prompt: 'jump', seed: 7}, poses, callbacks);
  assert.equal(poses.size, 0);
  assert.equal(els.modelPath.value, '');
  assert.equal(els.textBundlePath.value, '');
});

test('batch selection groups by identity and preserves seed order', () => {
  const items = [{id: 'b2', batch_id: 'b', batch_index: 2, seed: 43},
    {id: 'a', batch_id: 'a', batch_index: 1}, {id: 'b1', batch_id: 'b', batch_index: 1, seed: 42}];
  assert.deepEqual(samplesInBatch(items, items[0]).map((item) => item.seed), [42, 43]);
  assert.deepEqual(samplesInBatch(items, {id: 'legacy'}), [{id: 'legacy'}]);
});
