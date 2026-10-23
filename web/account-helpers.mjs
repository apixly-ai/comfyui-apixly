/** Browser metadata and exact-model adapters. No credentials or inference. */
const ACTIONS = new Set(["begin", "poll", "cancel", "refresh", "select_key", "disconnect", "use_manual", "use_account"]);
export function catalogEntries(snapshot, kind) {
  if (!["image", "video"].includes(kind)) throw Error("Unsupported media kind.");
  const rows = snapshot?.[kind === "image" ? "image_models" : "video_models"];
  return Array.isArray(rows) ? rows.filter(row => typeof row?.id === "string" && row.id) : [];
}
export function setExactModel(node, id) {
  if (typeof id !== "string" || !id || id.length > 500 || /[\u0000-\u001f]/.test(id)) throw Error("Choose an exact model ID.");
  const widget = node.widgets?.find(item => item.name === "model");
  if (!widget) throw Error("This node has no model field.");
  widget.value = id;
  widget.callback?.(id);
}
export function createAccountBridge(fetchApi) {
  let current = {}, epoch = 0;
  const listeners = new Set();
  function accept(value) {
    epoch++;
    current = value;
    for (const listener of listeners) listener(value);
    return value;
  }
  async function request(path, options) {
    const response = await fetchApi(path, { cache: "no-store", ...options });
    let result;
    try { result = await response.json(); } catch { throw Error("The Apixly connection service returned an unreadable response."); }
    if (!response.ok) {
      if (result.account) accept({ ...current, account: result.account });
      const message = typeof result.message === "string" ? result.message : result.error;
      throw Error(typeof message === "string" ? message.slice(0, 400) : "Connection needs attention. Refresh your account before trying again.");
    }
    return result;
  }
  async function read(keys = false) {
    const started = epoch;
    const result = await request(`/apixly/state${keys ? "?keys=1" : ""}`);
    return started === epoch ? accept(result) : current;
  }
  function action(action, key_id) {
    if (!ACTIONS.has(action)) throw Error("Unsupported account action.");
    return (async () => {
      if (!current.csrf_token) await read();
      const result = await request("/apixly/account", { method: "POST", headers: { "Content-Type": "application/json", "X-Apixly-CSRF": current.csrf_token }, body: JSON.stringify({ action, ...(key_id === undefined ? {} : { key_id }) }) });
      return accept(result);
    })();
  }
  return { accept, read, action, value: () => current, subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); }, catalog: (force = false) => request(`/apixly/catalog${force ? "?refresh=1" : ""}`) };
}
