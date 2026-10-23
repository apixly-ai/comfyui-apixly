import { catalogEntries, createAccountBridge, setExactModel } from "./account-helpers.mjs";

const STYLE = "box-sizing:border-box;display:flex;flex-direction:column;gap:12px;min-width:0;max-width:100%;padding:16px;border:1px solid #2e8fff30;border-radius:14px;background:linear-gradient(145deg,#0f172ae6,#06070af2);color:#e2e8f0;font:13px/1.6 system-ui;overflow-wrap:anywhere";
const CONTROL = "box-sizing:border-box;min-height:44px;min-width:44px;max-width:100%;border:1px solid #2e8fff55;border-radius:9px;background:#1670f018;color:inherit;padding:9px 12px;font:inherit;cursor:pointer";
const instances = new WeakMap();
function el(tag, text, style) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (style) result.style.cssText = style;
  return result;
}
function button(text, action) {
  const result = el("button", text, CONTROL);
  result.type = "button";
  result.addEventListener("click", event => { event.preventDefault(); event.stopPropagation(); action(); });
  return result;
}
export function accountBridge(api) {
  if (!instances.has(api)) instances.set(api, createAccountBridge((path, options) => api.fetchApi(path, options)));
  return instances.get(api);
}
function identity(state) {
  const account = state.account || {};
  return JSON.stringify([account.mode, account.connected, account.connection_id, account.selected_key?.id, account.selection_revision]);
}
export function mountAccount(root, bridge) {
  let busy = false, error = "", timer, disposed = false;
  root.style.cssText = STYLE;
  root.dataset.apixlyAccount = "true";
  async function act(action, key) {
    if (busy || disposed) return;
    busy = true; error = ""; render(bridge.value());
    try { await bridge.action(action, key); }
    catch (failure) { error = failure.message; }
    finally { busy = false; if (!disposed) render(bridge.value()); }
  }
  function render(state = {}) {
    if (disposed) return;
    clearTimeout(timer);
    root.replaceChildren();
    const account = state.account || {};
    root.append(el("div", "APIXLY · CREATIVE CONNECTION", "font-size:11px;letter-spacing:.12em;color:#2e8fff;font-weight:650"), el("h2", "Your account. Your models.", "margin:0;font-size:22px;line-height:1.3"));
    root.append(el("p", "Connect your existing Apixly account. Use your Studixly Key by default, or choose an active Key you already own.", "margin:0;color:#94a3b8"));
    const current = el("div", undefined, "padding:12px;border:1px solid #ffffff12;border-radius:10px;background:#ffffff04");
    current.append(el("strong", account.mode === "account" ? account.connected ? "Apixly account connected" : "Reconnect your Apixly account" : "Server API Key mode"));
    if (account.account) current.append(el("div", account.account.name || account.account.email));
    if (account.selected_key) current.append(el("div", `${account.selected_key.name} · ${account.selected_key.masked}`, "color:#94a3b8;font-size:12px"));
    if (account.mode === "manual") current.append(el("div", state.manual_key_available ? "APIXLY_API_KEY configured on this server." : "Connect an account, or configure APIXLY_API_KEY on the server.", "color:#94a3b8;font-size:12px"));
    root.append(current);
    if (error) { const notice = el("p", error, "margin:0;color:#fbbf24"); notice.setAttribute("role", "alert"); root.append(notice); }
    const actions = el("div", undefined, "display:flex;flex-wrap:wrap;gap:8px");
    actions.append(button("Connect / reconnect ↗", () => act("begin")));
    if (account.connected) {
      actions.append(button("Refresh account", () => act("refresh")));
      if (account.mode !== "account") actions.append(button("Use connected account", () => act("use_account")));
      actions.append(button("Disconnect account", () => act("disconnect")));
    }
    root.append(actions);
    const pending = account.authorization;
    if (pending?.status === "pending") {
      const progress = el("div", undefined, "display:flex;flex-direction:column;gap:9px;padding:14px;border:1px solid #2e8fff55;border-radius:12px;background:#2e8fff0a");
      progress.append(el("strong", "Approve on apixly.ai"), el("code", pending.user_code, "font-size:22px;color:#7dd3fc;letter-spacing:.12em"));
      const uri = new URL(pending.verification_uri_complete);
      if (uri.origin === "https://apixly.ai" && uri.pathname.startsWith("/connect/")) {
        const link = el("a", "Open authorization page ↗", CONTROL + ";text-decoration:none;text-align:center");
        link.href = uri.href; link.target = "_blank"; link.rel = "noopener noreferrer"; progress.append(link);
      }
      progress.append(el("small", `Expires ${new Date(pending.expires_at * 1000).toLocaleTimeString()}. Waiting does not generate media.`, "color:#94a3b8"));
      progress.append(button("Cancel connection", () => act("cancel"))); root.append(progress);
      if (!busy) timer = setTimeout(() => act("poll"), Math.max(5, pending.interval || 5) * 1000);
    }
    if (account.mode === "account" && account.connected) {
      const label = el("label", "API Key", "display:flex;flex-direction:column;gap:7px");
      const picker = el("select", undefined, CONTROL + ";width:100%"); picker.setAttribute("aria-label", "Apixly account API Key");
      const rows = state.keys?.data || state.keys || [];
      const options = Array.isArray(rows) ? rows : [];
      if (!options.length) { const placeholder = el("option", "Refresh account to load your active Keys"); placeholder.value = ""; picker.append(placeholder); }
      for (const key of options) { const option = el("option", `${key.name} · ${key.masked}`); option.value = String(key.id); picker.append(option); }
      picker.value = account.selected_key?.id || "";
      picker.addEventListener("change", () => { if (picker.value) act("select_key", picker.value); }); label.append(picker); root.append(label);
      root.append(el("small", "Key changes keep your exact model ID. Open or refresh a model picker to load its available models.", "color:#94a3b8"));
    }
    if (account.mode !== "manual") root.append(button("Use server APIXLY_API_KEY", () => act("use_manual")));
    root.append(el("small", "Server-wide connection: people using this ComfyUI server share its selected account. Connection tokens stay outside workflows and browser-readable userdata.", "color:#94a3b8"));
    const links = el("div", undefined, "display:flex;flex-wrap:wrap;gap:8px");
    for (const [text, href] of [["apixly.ai", "https://apixly.ai"], ["Models & prices", "https://platform.apixly.ai/models"], ["Manage Keys", "https://platform.apixly.ai/keys"], ["Connected plugins", "https://apixly.ai/integrations"]]) { const link = el("a", text + " ↗", CONTROL + ";text-decoration:none"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; links.append(link); }
    root.append(links, el("small", "Free plugin · generation uses your Apixly balance. Account connection and catalog browsing do not generate media.", "color:#64748b"));
    for (const control of root.querySelectorAll("button,select")) control.disabled = busy;
  }
  const unsubscribe = bridge.subscribe(render);
  render(bridge.value());
  bridge.read(true).catch(failure => { error = failure.message; render(bridge.value()); });
  return () => { disposed = true; clearTimeout(timer); unsubscribe(); root.replaceChildren(); };
}

export function attachModelPicker(node, app, bridge) {
  const kind = node.comfyClass === "ApixlyVideoSubmit" ? "video" : "image";
  if (!["ApixlyVideoSubmit", "ApixlyImageSubmit", "ApixlyImageEdit"].includes(node.comfyClass)) return;
  let epoch = 0, disposed = false, currentIdentity = identity(bridge.value());
  const root = el("div", undefined, STYLE + ";padding:12px;gap:8px");
  const label = el("label", `Available ${kind} models`, "display:flex;flex-direction:column;gap:7px");
  const picker = el("select", undefined, CONTROL + ";width:100%"); picker.setAttribute("aria-label", `Apixly ${kind} model catalog`);
  label.append(picker); root.append(label);
  const status = el("small", "Open this picker to load all models for the selected Key.", "color:#94a3b8;white-space:normal"); status.setAttribute("role", "status");
  function placeholder() { const option = el("option", "Keep exact model ID below"); option.value = ""; picker.replaceChildren(option); }
  placeholder();
  async function load(force = false) {
    const started = ++epoch;
    status.textContent = "Reading model catalog… No generation is submitted.";
    try {
      const snapshot = await bridge.catalog(force);
      if (disposed || epoch !== started) return;
      const rows = catalogEntries(snapshot, kind);
      placeholder();
      for (const row of rows) { const option = el("option", row.name && row.name !== row.id ? `${row.name} · ${row.id}` : row.id); option.value = row.id; picker.append(option); }
      const exact = node.widgets?.find(item => item.name === "model")?.value;
      picker.value = rows.some(row => row.id === exact) ? exact : "";
      status.textContent = `${rows.length} ${kind} models${snapshot.stale ? " · saved catalog" : ""}. ${snapshot.error || snapshot.capabilitiesError || "Exact model ID is unchanged until you select one."}`;
    } catch (failure) { if (!disposed && started === epoch) status.textContent = failure.message; }
  }
  picker.addEventListener("focus", () => load());
  picker.addEventListener("change", () => {
    if (!picker.value) return;
    try { setExactModel(node, picker.value); app.graph?.setDirtyCanvas(true, true); }
    catch (failure) { status.textContent = failure.message; picker.value = ""; }
  });
  root.append(status, button("Refresh models", () => load(true)), el("small", "Connect or select an owned Key in the Apixly sidebar. You can still type any exact model ID in the native field.", "color:#64748b"));
  const widget = node.addDOMWidget("apixly_models", "div", root, { serialize: false, hideOnZoom: false });
  widget.computeSize = () => [300, 215];
  const unsubscribe = bridge.subscribe(state => { const next = identity(state); if (next !== currentIdentity) { currentIdentity = next; epoch++; placeholder(); status.textContent = "Key changed. Open or refresh this picker to read its available models."; } });
  const previous = node.onRemoved;
  node.onRemoved = function () { disposed = true; epoch++; unsubscribe(); previous?.apply(this, arguments); };
}
