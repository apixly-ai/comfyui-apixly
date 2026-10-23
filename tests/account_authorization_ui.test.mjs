import assert from "node:assert/strict";
import test from "node:test";
import { mountAccount } from "../web/account.mjs";

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.style = {}; this.attributes = {}; this.listeners = {}; }
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return (this.text || "") + this.children.map(item => item.textContent || "").join(""); }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, handler) { this.listeners[key] = handler; }
  querySelectorAll(selector) { return elements(this).filter(item => selector.split(",").includes(item.tagName)); }
  focus() { this.focused = true; }
  select() { this.selected = true; }
}
const elements = root => [root, ...root.children.flatMap(elements)];
const tick = () => new Promise(resolve => setImmediate(resolve));
const trigger = element => { assert.ok(element, "Expected a visible action"); element.listeners.click({ preventDefault() {}, stopPropagation() {} }); };
const action = (root, text) => elements(root).find(item => ["button", "a"].includes(item.tagName) && item.textContent === text);
const URI = "https://apixly.ai/connect/abcdefghijklmnopqrstuv?user_code=ABCD-EF12";

function fixture(t, { pending = false, blocked = false, clipboardFails = false, copyText } = {}) {
  globalThis.document = { createElement: tag => new Element(tag) };
  let now = Date.now();
  const calls = [], timers = new Map();
  const page = { closed: false, opener: "old-opener", location: { replace(value) { calls.push(["navigate", value]); } }, focus() { calls.push(["focus"]); }, close() { this.closed = true; calls.push(["close"]); } };
  const authorization = () => ({ status: "pending", user_code: "ABCD-EF12", verification_uri_complete: URI, expires_at: (now + 60000) / 1000, interval: 5 });
  let value = { account: { mode: "account", connected: false, ...(pending ? { authorization: authorization() } : {}) } }, subscriber;
  const bridge = {
    value: () => value, subscribe(fn) { subscriber = fn; return () => {}; }, read: async () => value,
    async action(name) { calls.push(["action", name]); if (name === "begin") value = { account: { mode: "account", connected: false, authorization: authorization() } }; else if (name === "cancel") value = { account: { mode: "account", connected: false } }; subscriber?.(value); return value; },
  };
  const environment = {
    openWindow(url, target) { calls.push(["open", url, target]); return blocked ? null : page; },
    async copyText(text) { calls.push(["copy", text]); if (copyText) return copyText(text); if (clipboardFails) throw Error("Clipboard denied"); },
    now: () => now,
    schedule(fn, delay) { const id = Symbol(); timers.set(id, { fn, delay }); return id; },
    cancelTimer(id) { timers.delete(id); },
  };
  const root = new Element("div");
  const dispose = mountAccount(root, bridge, environment); t.after(dispose);
  return { root, calls, page, bridge, timers, dispose, emit(state) { value = state; subscriber?.(value); }, advance(ms) { now += ms; for (const { fn } of [...timers.values()]) fn(); } };
}

test("Connect prepares its tab in the original gesture before asynchronous authorization, without a noopener-null ambiguity", async t => {
  const f = fixture(t); await tick();
  trigger(action(f.root, "Connect / reconnect ↗"));
  assert.deepEqual(f.calls.slice(0, 2), [["open", "about:blank", "_blank"], ["action", "begin"]]);
  assert.equal(f.page.opener, null);
  await tick();
  assert.deepEqual(f.calls.find(row => row[0] === "navigate"), ["navigate", URI]);
  assert.match(f.root.textContent, /authorization tab.*opened/i);
});

test("Mounting a pending flow does not open tabs; Open and Copy reuse that flow without creating another authorization", async t => {
  const f = fixture(t, { pending: true }); await tick();
  assert.equal(f.calls.length, 0);
  assert.ok(action(f.root, "Copy authorization link"), "Copy authorization link is visible");
  trigger(action(f.root, "Open authorization page ↗")); await tick();
  trigger(action(f.root, "Copy authorization link")); await tick();
  assert.equal(f.calls.filter(row => row[0] === "action" && row[1] === "begin").length, 0);
  assert.deepEqual(f.calls.find(row => row[0] === "copy"), ["copy", URI]);
  assert.match(f.root.textContent, /Link copied/);
});

test("Blocked automatic opening keeps explicit Open and Copy actions and never claims success", async t => {
  const f = fixture(t, { blocked: true }); await tick();
  trigger(action(f.root, "Connect / reconnect ↗")); await tick();
  assert.match(f.root.textContent, /blocked|unavailable/i);
  assert.doesNotMatch(f.root.textContent, /authorization tab.*opened/i);
  assert.ok(action(f.root, "Open authorization page ↗"));
  assert.ok(action(f.root, "Copy authorization link"));
  assert.equal(f.calls.filter(row => row[0] === "navigate").length, 0);
});

test("Clipboard failure selects the public link for manual copy and shows the real fallback", async t => {
  const f = fixture(t, { pending: true, clipboardFails: true }); await tick();
  trigger(action(f.root, "Copy authorization link")); await tick();
  const field = elements(f.root).find(item => item.attributes["aria-label"] === "Authorization link");
  assert.ok(field);
  assert.equal(field.value, URI); assert.equal(field.readOnly, true);
  assert.equal(field.selected, true);
  assert.match(f.root.textContent, /copy.*manually/i);
  assert.doesNotMatch(f.root.textContent, /Link copied/);
});

test("Cancel removes the old link and opening/copy status instead of reopening or creating another flow", async t => {
  const f = fixture(t); await tick();
  trigger(action(f.root, "Connect / reconnect ↗")); await tick();
  trigger(action(f.root, "Copy authorization link")); await tick();
  trigger(action(f.root, "Cancel connection")); await tick();
  assert.equal(action(f.root, "Copy authorization link"), undefined);
  assert.equal(action(f.root, "Open authorization page ↗"), undefined);
  assert.doesNotMatch(f.root.textContent, /Link copied|authorization tab.*opened/i);
  assert.equal(f.calls.filter(row => row[0] === "action" && row[1] === "begin").length, 1);
});

test("Expiry removes public actions and tells the user to reconnect without polling or reopening an expired URL", async t => {
  const f = fixture(t, { pending: true }); await tick();
  f.advance(61000); await tick();
  assert.equal(action(f.root, "Open authorization page ↗"), undefined);
  assert.equal(action(f.root, "Copy authorization link"), undefined);
  assert.match(f.root.textContent, /expired.*Connect again/i);
  assert.equal(f.calls.filter(row => row[0] === "open").length, 0);
  assert.equal(f.calls.filter(row => row[0] === "action" && row[1] === "poll").length, 0);
});

test("Successful binding clears the old authorization link and its transient copy/open status", async t => {
  const f = fixture(t, { pending: true }); await tick();
  f.emit({ account: { mode: "account", connected: true, connection_id: "new-connection", selected_key: { id: "studixly", name: "Studixly", masked: "••••1234" } } });
  assert.equal(action(f.root, "Open authorization page ↗"), undefined);
  assert.equal(action(f.root, "Copy authorization link"), undefined);
  assert.match(f.root.textContent, /Apixly account connected/);
});

test("An authorization request failure closes only its prepared blank tab and does not claim it opened the site", async t => {
  const f = fixture(t); await tick();
  f.bridge.action = async () => { throw Error("Connection service unavailable"); };
  trigger(action(f.root, "Connect / reconnect ↗")); await tick();
  assert.equal(f.page.closed, true);
  assert.match(f.root.textContent, /Connection service unavailable/);
  assert.doesNotMatch(f.root.textContent, /authorization tab.*opened/i);
});

test("Closing the prepared tab before begin settles gives a visible manual fallback", async t => {
  const f = fixture(t); await tick();
  trigger(action(f.root, "Connect / reconnect ↗"));
  f.page.closed = true;
  await tick();
  assert.match(f.root.textContent, /tab.*closed/i);
  assert.equal(f.calls.filter(row => row[0] === "navigate").length, 0);
  assert.ok(action(f.root, "Copy authorization link"));
});

test("Unsafe or malformed authorization URLs are not rendered, copied or opened", async t => {
  const f = fixture(t); await tick();
  f.emit({ account: { mode: "account", connected: false, authorization: { status: "pending", user_code: "ABCD-EF12", verification_uri_complete: "javascript:alert(1)", expires_at: Date.now() / 1000 + 60 } } });
  assert.match(f.root.textContent, /invalid.*authorization|authorization.*invalid/i);
  assert.equal(action(f.root, "Copy authorization link"), undefined);
  assert.equal(action(f.root, "Open authorization page ↗"), undefined);
  assert.equal(f.calls.length, 0);
});

test("A late clipboard result cannot announce success on a different authorization flow", async t => {
  let finish;
  const f = fixture(t, { pending: true, copyText: () => new Promise(resolve => { finish = resolve; }) }); await tick();
  trigger(action(f.root, "Copy authorization link"));
  trigger(action(f.root, "Cancel connection")); await tick();
  const next = { account: { mode: "account", connected: false, authorization: { status: "pending", user_code: "ABCD-EF12", verification_uri_complete: URI.replace("abcdefghijklmnopqrstuv", "ABCDEFGHIJKLMNOPQRSTUV"), expires_at: Date.now() / 1000 + 60 } } };
  f.emit(next); finish(); await tick();
  f.emit(next);
  assert.doesNotMatch(f.root.textContent, /Link copied/);
});

test("Disposing a panel during begin closes its blank tab and ignores the later response", async t => {
  const f = fixture(t); await tick();
  let finish;
  f.bridge.action = () => new Promise(resolve => { finish = resolve; });
  trigger(action(f.root, "Connect / reconnect ↗")); f.dispose();
  finish(); await tick();
  assert.equal(f.page.closed, true);
  assert.equal(f.calls.filter(row => row[0] === "navigate").length, 0);
  assert.equal(f.root.children.length, 0);
});
