import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  applyDrag, clampPitch, isCreativeNode, nudgeAngles, payloadForCompose,
  settingsForNode, updateControl, wrapYaw,
} from "../web/creative-helpers.mjs";

const require = createRequire(import.meta.url);
const { composeCreativePrompt } = require("../web/creative-compiler.js");
const fixtures = JSON.parse(await readFile(new URL("./fixtures/creative-golden-v1.json", import.meta.url)));

for (const item of fixtures.valid) {
  test(`shared creative valid: ${item.id}`, () => {
    assert.deepEqual(composeCreativePrompt(item.input), item.expected);
  });
}
for (const item of fixtures.invalid) {
  test(`shared creative invalid: ${item.id}`, () => {
    assert.throws(() => composeCreativePrompt(item.input));
  });
}

function node(comfyClass, values, id = 1) {
  return { comfyClass, id, widgets: Object.entries(values).map(([name, value]) => ({ name, value })), inputs: [] };
}
function value(item, name) { return item.widgets.find(widget => widget.name === name).value; }

test("only the four free utility classes use creative panels", () => {
  assert.equal(isCreativeNode({ comfyClass: "ApixlyPromptCompose" }), true);
  assert.equal(isCreativeNode({ comfyClass: "ApixlyPromptLighting" }), true);
  for (const comfyClass of ["ApixlyImageSubmit", "ApixlyImageEdit", "ApixlyVideoResult", "OtherPrompt"]) {
    assert.equal(isCreativeNode({ comfyClass }), false);
  }
});

test("orbit drag/nudges wrap yaw and keep positive elevation above", () => {
  assert.equal(wrapYaw(-15), 345);
  assert.equal(clampPitch(100), 90);
  assert.deepEqual(nudgeAngles({ yaw: 355, pitch: 85 }, "right"), { yaw: 10, pitch: 85 });
  assert.deepEqual(nudgeAngles({ yaw: 0, pitch: 85 }, "up"), { yaw: 0, pitch: 90 });
  assert.deepEqual(applyDrag({ yaw: 0, pitch: 0 }, 10, -20, 1), { yaw: 10, pitch: 20 });
});

test("preset and direct-angle changes update native serialized widgets without enabling", () => {
  const item = node("ApixlyPromptViewpoint", { enabled: false, preset: "custom", yaw: 80, pitch: -20, shot: "none" });
  updateControl(item, "preset", "front_high");
  assert.equal(value(item, "yaw"), 0);
  assert.equal(value(item, "pitch"), 45);
  assert.equal(value(item, "enabled"), false);
  updateControl(item, "yaw", 90);
  assert.equal(value(item, "preset"), "custom");
  const restored = node(item.comfyClass, Object.fromEntries(item.widgets.map(w => [w.name, w.value])));
  assert.deepEqual(settingsForNode(restored), settingsForNode(item));
});

test("lighting omits unused orbit coordinates and never injects its picker default", () => {
  const item = node("ApixlyPromptLighting", { enabled: true, preset: "none", brightness: 50, use_color: false, color: "#2e8fff", direction: "legacy", key_light: "left", light_yaw: 0, light_pitch: 0, rim_light: false, smart_text: "" });
  const setting = settingsForNode(item);
  assert.equal(setting.color, "");
  assert.equal(setting.keyLight, "left");
  assert.equal("lightYaw" in setting, false);
  updateControl(item, "light_pitch", 30);
  assert.equal(value(item, "direction"), "orbit");
  assert.equal(settingsForNode(item).lightPitch, 30);
});

test("Compose preview follows only typed utility connections and matches the host payload", () => {
  const angle = node("ApixlyPromptViewpoint", { enabled: true, preset: "custom", yaw: 90, pitch: 30, shot: "none" }, 2);
  const compose = node("ApixlyPromptCompose", { prompt: "  Same vase\n", mode: "edit" }, 3);
  compose.inputs = [{ name: "angle", link: 10 }];
  const graph = { links: { 10: { origin_id: 2, origin_slot: 0 } }, getNodeById: id => id === 2 ? angle : null };
  const payload = payloadForCompose(compose, graph);
  assert.deepEqual(payload.tools.angle, settingsForNode(angle));
  assert.equal(payload.prompt, "  Same vase\n");
  assert.match(composeCreativePrompt(payload).final_prompt, /re-photograph the exact same subject/);
  compose.inputs.push({ name: "prompt", link: 11 });
  assert.throws(() => payloadForCompose(compose, graph), /upstream prompt/i);
});
