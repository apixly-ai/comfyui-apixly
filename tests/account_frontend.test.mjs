import assert from "node:assert/strict";
import test from "node:test";
import { catalogEntries, createAccountBridge, setExactModel } from "../web/account-helpers.mjs";
import { attachModelPicker, mountAccount } from "../web/account.mjs";

test("catalog uses complete server-typed options and never silently substitutes the exact model", () => {
  const snapshot = { image_models: [{ id: "seedream-5-0", name: "Seedream" }, { id: "future-id", name: "New model" }], video_models: [{ id: "video-without-config", videoCapability: null }] };
  assert.deepEqual(catalogEntries(snapshot, "image").map(x => x.id), ["seedream-5-0", "future-id"]);
  assert.equal(catalogEntries(snapshot, "video")[0].videoCapability, null);
  const node = { widgets: [{ name: "model", value: "my-existing-exact-model" }] };
  catalogEntries(snapshot, "image");
  assert.equal(node.widgets[0].value, "my-existing-exact-model");
  setExactModel(node, "seedream-5-0");
  assert.equal(node.widgets[0].value, "seedream-5-0");
  assert.throws(() => setExactModel(node, ""));
});

test("account bridge reads only local metadata and protects actions with server CSRF", async () => {
  const calls = [];
  const fetchApi = async (path, options = {}) => {
    calls.push({ path, options });
    return { ok: true, json: async () => ({ csrf_token: "private-local-nonce", account: { mode: "account", connected: false } }) };
  };
  const bridge = createAccountBridge(fetchApi);
  await bridge.action("begin");
  assert.equal(calls[0].path, "/apixly/state");
  assert.equal(calls[1].path, "/apixly/account");
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[1].options.headers["X-Apixly-CSRF"], "private-local-nonce");
  assert.deepEqual(JSON.parse(calls[1].options.body), { action: "begin" });
  assert.equal(calls.some(c => /v1|generations|videos/.test(c.path)), false);
  assert.throws(() => bridge.action("generate"), /Unsupported/);
});

test("late account state from before a credential mutation cannot overwrite new selection", async () => {
  let finish;
  const bridge = createAccountBridge(async (path) => ({ ok: true, json: () => path.startsWith("/apixly/state") ? new Promise(resolve => { finish = resolve; }) : Promise.resolve({ account: { selected_key: { id: "new" } }, csrf_token: "csrf" }) }));
  const old = bridge.read();
  await new Promise(resolve => setImmediate(resolve));
  bridge.accept({ account: { selected_key: { id: "new" } }, csrf_token: "csrf" });
  finish({ account: { selected_key: { id: "old" } }, csrf_token: "old-csrf" });
  await old;
  assert.equal(bridge.value().account.selected_key.id, "new");
});

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.style = {}; this.attributes = {}; this.listeners = {}; }
  set textContent(text) { this.text = text; this.children = []; }
  get textContent() { return (this.text || "") + this.children.map(child => child.textContent || "").join(""); }
  set innerHTML(_) { throw Error("Account metadata must remain literal text."); }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, fn) { this.listeners[key] = fn; }
  querySelectorAll(selector) { return all(this).filter(item => selector.split(",").includes(item.tagName)); }
}
function all(root) { return [root, ...root.children.flatMap(all)]; }
const tick = () => new Promise(resolve => setImmediate(resolve));
function setupDocument() { globalThis.document = { createElement: tag => new Element(tag) }; }

test("model widget is lazy, retains exact ID and writes only explicit picker changes", async () => {
  setupDocument();
  let calls = 0, invalidate;
  const bridge = { value: () => ({}), subscribe(fn) { invalidate = fn; return () => {}; }, async catalog() { calls++; return { image_models: [{ id: "seedream-5-0", name: "<img onerror=bad>" }], stale: false }; } };
  const node = { comfyClass: "ApixlyImageSubmit", widgets: [{ name: "model", value: "manual-id" }], addDOMWidget(name, type, root, options) { this.root = root; assert.equal(options.serialize, false); return {}; } };
  attachModelPicker(node, { graph: { setDirtyCanvas() {} } }, bridge);
  assert.equal(calls, 0);
  const picker = all(node.root).find(item => item.tagName === "select");
  picker.listeners.focus(); await tick();
  assert.equal(calls, 1);
  assert.equal(node.widgets[0].value, "manual-id");
  assert.equal(picker.children[1].textContent, "<img onerror=bad> · seedream-5-0");
  picker.value = "seedream-5-0"; picker.listeners.change();
  assert.equal(node.widgets[0].value, "seedream-5-0");
  invalidate({ account: { mode: "account", selected_key: { id: "new" } } });
  assert.equal(picker.children.length, 1);
  assert.equal(node.widgets[0].value, "seedream-5-0");
});

test("account panel renders safe metadata, shared-server scope and owned Key selection", async () => {
  setupDocument();
  const state = { account: { mode: "account", connected: true, account: { name: "<img onerror=bad>" }, selected_key: { id: "studixly", name: "Studixly", masked: "••••1234" } }, keys: { data: [{ id: "studixly", name: "Studixly", masked: "••••1234" }, { id: "42", name: "Existing Key", masked: "••••5678" }] } };
  const actions = [];
  const bridge = { value: () => state, subscribe: () => () => {}, read: async () => state, action: async (...args) => { actions.push(args); return state; } };
  const root = new Element("div");
  const dispose = mountAccount(root, bridge); await tick();
  assert.match(root.textContent, /<img onerror=bad>/);
  assert.match(root.textContent, /Server-wide connection/);
  const picker = all(root).find(item => item.tagName === "select");
  assert.equal(picker.children.length, 2);
  picker.value = "42"; picker.listeners.change(); await tick();
  assert.deepEqual(actions, [["select_key", "42"]]);
  dispose(); assert.equal(root.children.length, 0);
});
