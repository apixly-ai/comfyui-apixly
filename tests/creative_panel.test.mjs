import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { attachCreativePanel } from "../web/creative.mjs";

const require = createRequire(import.meta.url);
globalThis.ApixlyCreativeControlsV1 = require("../web/creative-compiler.js");

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.style = {}; this.attributes = {}; this.listeners = {}; this._text = ""; }
  set textContent(value) { this._text = value; this.children = []; }
  set innerHTML(_) { throw new Error("User prompt text must never be HTML."); }
  get textContent() { return this._text + this.children.map(c => c.textContent || "").join(""); }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.append(item); return item; }
  replaceChildren(...items) { this.children = items; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  dispatch(name) { for (const f of this.listeners[name] || []) f({ preventDefault() {}, stopPropagation() {}, currentTarget: this }); }
}
function all(root) { return [root, ...root.children.flatMap(all)]; }
function fakeNode(comfyClass, values, id = 1) {
  return { comfyClass, id, size: [440, 400], inputs: [], widgets: Object.entries(values).map(([name, value]) => ({ name, value })),
    addDOMWidget(name, type, element, options) { this.panel = element; this.panelOptions = options; return {}; },
    computeSize() { return [440, 400]; }, setSize(size) { this.size = size; } };
}
function setup(nodes) {
  globalThis.document = { createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag) };
  globalThis.fetch = () => { throw new Error("Preview must not make a request."); };
  const graph = { _nodes: nodes, links: {}, getNodeById: id => nodes.find(n => n.id === id), setDirtyCanvas() {} };
  const app = { graph, queuePrompt() { throw new Error("Preview must not queue generation."); } };
  for (const node of nodes) { node.graph = graph; attachCreativePanel(node, app); }
  return app;
}

test("free panel toggles/reset keep native settings and never show paid receipt buttons", () => {
  const node = fakeNode("ApixlyPromptViewpoint", { enabled: false, preset: "custom", yaw: 0, pitch: 0, shot: "none" });
  setup([node]);
  assert.equal(node.panel.dataset.apixlyCreative, "angle");
  assert.equal(node.panelOptions.serialize, false);
  assert.doesNotMatch(node.panel.textContent, /Copy task ID|Copy result URL|Paid action/);
  const preset = all(node.panel).find(e => e.tagName === "button" && e.textContent === "High angle");
  preset.dispatch("click");
  assert.equal(node.widgets.find(w => w.name === "pitch").value, 45);
  assert.equal(node.widgets.find(w => w.name === "enabled").value, false);
  all(node.panel).find(e => e.getAttribute("role") === "switch").dispatch("click");
  assert.match(all(node.panel).find(e => e.tagName === "textarea").value, /looking down/);
  all(node.panel).find(e => e.tagName === "button" && e.textContent === "Reset").dispatch("click");
  assert.equal(node.widgets.find(w => w.name === "enabled").value, false);
  assert.equal(node.widgets.find(w => w.name === "pitch").value, 0);
});

test("Compose preview recomputes native inputs exactly and resets only connected tools", () => {
  const tool = fakeNode("ApixlyPromptCamera", { enabled: true, body: "none", lens: "none", use_focal: true, focal: 85, aperture: "f/1.8" }, 1);
  const compose = fakeNode("ApixlyPromptCompose", { prompt: "  Same vase\n", mode: "edit" }, 2);
  compose.inputs = [{ name: "camera", link: 1 }];
  const app = setup([tool, compose]);
  app.graph.links[1] = { origin_id: 1, origin_slot: 0 };
  compose.onConnectionsChange();
  const preview = all(compose.panel).find(e => e.tagName === "textarea");
  assert.match(preview.value, /85mm telephoto/);
  assert.match(preview.value, /Preserve all subject/);
  all(compose.panel).find(e => e.tagName === "button" && e.textContent === "Reset connected tools").dispatch("click");
  assert.equal(preview.value, "  Same vase\n");
  assert.equal(compose.widgets.find(w => w.name === "prompt").value, "  Same vase\n");
});

test("prompt and smart lighting text remain literal text, not HTML", () => {
  const attack = '</textarea><img src=x onerror="alert(1)">';
  const light = fakeNode("ApixlyPromptLighting", { enabled: true, smart_text: attack }, 1);
  const compose = fakeNode("ApixlyPromptCompose", { prompt: attack, mode: "edit" }, 2);
  compose.inputs = [{ name: "lighting", link: 1 }];
  const app = setup([light, compose]);
  app.graph.links[1] = { origin_id: 1, origin_slot: 0 };
  compose.onConnectionsChange();
  const preview = all(compose.panel).find(e => e.tagName === "textarea");
  assert.equal(preview.value.startsWith(attack), true);
  assert.equal(preview.value.includes(`lighting style: ${attack}`), true);
  assert.equal(all(compose.panel).some(e => e.tagName === "img"), false);
});

test("free panel allows narrow native nodes and retains touch-size controls", () => {
  const node = fakeNode("ApixlyPromptLighting", { enabled: false });
  node.size = [310, 600];
  setup([node]);
  assert.ok(node.size[0] <= 340, "The prompt panel must not force a desktop-width node.");
  for (const item of all(node.panel).filter(e => e.tagName === "button")) {
    assert.match(item.style.cssText, /min-height:44px/);
    assert.match(item.style.cssText, /min-width:44px/);
  }
});

test("camera has an accessible native lens diagram", () => {
  const node = fakeNode("ApixlyPromptCamera", { enabled: false });
  setup([node]);
  assert.ok(all(node.panel).some(e => e.getAttribute("aria-label") === "Lens style diagram"));
});

test("lighting uses the original eight Studixly gradient swatches", () => {
  const node = fakeNode("ApixlyPromptLighting", { enabled: false });
  setup([node]);
  const swatches = all(node.panel).filter(item => item.dataset.apixlySwatch);
  assert.equal(swatches.length, 8);
  const golden = swatches.find(item => item.dataset.apixlySwatch === "goldenHour");
  assert.match(golden.style.cssText, /#fbbf24.*#f59e0b.*#b45309/);
});

test("orbit markers reuse the original Studixly camera and light glyphs", () => {
  for (const [type, glyph] of [["ApixlyPromptViewpoint", "camera"], ["ApixlyPromptLighting", "light"]]) {
    const node = fakeNode(type, { enabled: false });
    setup([node]);
    assert.ok(all(node.panel).some(item => item.getAttribute("data-studixly-glyph") === glyph));
  }
});

test("Vue native widget setters can call callbacks without recursive writes or preset loss", () => {
  const node = fakeNode("ApixlyPromptViewpoint", { enabled: false, preset: "custom", yaw: 70, pitch: -20, shot: "none" });
  let writes = 0;
  const callbacks = {};
  for (const widget of node.widgets) {
    widget.callback = () => { callbacks[widget.name] = (callbacks[widget.name] || 0) + 1; };
    let current = widget.value;
    Object.defineProperty(widget, "value", {
      get() { return current; },
      set(value) {
        current = value;
        if (++writes > 50) throw new Error("Native widget callback recursion");
        this.callback?.(value);
      },
    });
  }
  setup([node]);
  all(node.panel).find(e => e.tagName === "button" && e.textContent === "High angle").dispatch("click");
  assert.equal(node.widgets.find(w => w.name === "preset").value, "front_high");
  assert.equal(node.widgets.find(w => w.name === "pitch").value, 45);
  assert.ok(writes <= 4);
  assert.deepEqual(callbacks, { preset: 1, yaw: 1, pitch: 1 });
});

test("native configure restores stored controls without treating them as new user edits", () => {
  const node = fakeNode("ApixlyPromptViewpoint", { enabled: false, preset: "custom", yaw: 0, pitch: 0, shot: "none" });
  node.configure = function (values) { for (const w of this.widgets) { w.value = values[w.name]; w.callback?.(w.value); } };
  setup([node]);
  node.configure({ enabled: true, preset: "front_high", yaw: 123, pitch: -20, shot: "none" });
  assert.equal(node.widgets.find(w => w.name === "preset").value, "front_high");
  assert.equal(node.widgets.find(w => w.name === "yaw").value, 123);
  assert.match(all(node.panel).find(e => e.tagName === "textarea").value, /front view, high-angle/);
});

test("named viewpoint preset draws its effective direction and nudges from it", () => {
  const node = fakeNode("ApixlyPromptViewpoint", { enabled: true, preset: "front_high", yaw: 123, pitch: -20, shot: "none" });
  setup([node]);
  assert.equal(node.widgets.find(w => w.name === "yaw").value, 123);
  assert.match(node.panel.textContent, /0° azimuth · \+45° elevation/);
  all(node.panel).find(e => e.getAttribute("aria-label") === "Viewpoint up 15 degrees").dispatch("click");
  assert.equal(node.widgets.find(w => w.name === "preset").value, "custom");
  assert.equal(node.widgets.find(w => w.name === "yaw").value, 0);
  assert.equal(node.widgets.find(w => w.name === "pitch").value, 60);
});
