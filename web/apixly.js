import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { nativeDownloadURL, safeResultURL } from "./helpers.mjs";

const LINKS = [
  ["Apixly website", "https://apixly.ai"],
  ["Console", "https://platform.apixly.ai"],
  ["API keys", "https://platform.apixly.ai/keys"],
  ["Models & prices", "https://platform.apixly.ai/models"],
  ["Usage details", "https://platform.apixly.ai/usage/logs"],
  ["API documentation", "https://apixly.ai/docs"],
  ["Support", "mailto:support@apixly.ai"],
];

function accountSettings() {
  const panel = document.createElement("div");
  panel.style.cssText = "display:flex;flex-direction:column;gap:12px;padding:12px;max-width:560px;color:var(--fg-color,#e2e8f0)";
  const text = document.createElement("p");
  text.textContent = "Apixly Media uses your server's APIXLY_API_KEY. Generation is paid separately from Comfy credits. Use a limited key; never paste it into a workflow.";
  panel.append(text);
  const links = document.createElement("div");
  links.style.cssText = "display:flex;gap:8px;flex-wrap:wrap";
  for (const [label, href] of LINKS) {
    const link = document.createElement("a");
    link.textContent = label;
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.style.cssText = "display:inline-flex;align-items:center;min-height:44px;padding:0 12px;border:1px solid #2e8fff55;border-radius:9px;color:#76b6ff;text-decoration:none;background:#2e8fff10";
    links.append(link);
  }
  panel.append(links);
  return panel;
}

app.registerExtension({
  name: "Apixly.Media",
  setup() {
    app.ui.settings.addSetting({
      id: "Apixly.Media.AccountAndHelp",
      name: "Account, keys & help",
      category: ["Apixly", "Media", "AccountAndHelp"],
      type: accountSettings,
    });
  },
  nodeCreated(node) {
    if (!node.comfyClass?.startsWith("Apixly")) return;
    node.color = "#152b49";
    node.bgcolor = "#0f172a";
    node.boxcolor = "#2e8fff";
    const panel = document.createElement("div");
    panel.dataset.apixlyResult = "true";
    panel.style.cssText = "box-sizing:border-box;display:flex;flex-direction:column;gap:9px;padding:12px;border:1px solid #2e8fff44;border-radius:10px;background:linear-gradient(145deg,#2e8fff10,#06070a99);color:#e2e8f0;font:12px/1.4 system-ui;overflow:auto;pointer-events:auto";
    const status = document.createElement("div");
    status.textContent = node.comfyClass.endsWith("Submit") || node.comfyClass.endsWith("Edit")
      ? "Paid action · A new nonce creates a new job."
      : "Recovery · Read an existing task without generating again.";
    status.style.cssText = "white-space:normal;overflow-wrap:anywhere";
    panel.append(status);
    const buttons = document.createElement("div");
    buttons.style.cssText = "display:flex;gap:6px;flex-wrap:wrap";
    let detail = {};
    function button(label, action) {
      const element = document.createElement("button");
      element.type = "button";
      element.textContent = label;
      element.disabled = true;
      element.style.cssText = "min-height:44px;padding:0 10px;border:1px solid #2e8fff55;border-radius:8px;background:#1670f020;color:inherit;cursor:pointer;font:inherit";
      element.addEventListener("pointerdown", (event) => event.stopPropagation());
      element.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        try {
          await action();
        } catch {
          status.textContent = "Action unavailable in this browser. Use the task ID or output socket.";
        }
      });
      buttons.append(element);
      return element;
    }
    const copyTask = button("Copy task ID", () => navigator.clipboard.writeText(detail.task_id));
    const copyURL = button("Copy result URL", () => navigator.clipboard.writeText(safeResultURL(detail.url)));
    const download = button("Download", () => {
      const href = nativeDownloadURL(detail.saved);
      if (!href) return;
      const link = document.createElement("a");
      link.href = api.apiURL(href);
      link.download = detail.saved.filename;
      link.click();
    });
    panel.append(buttons);
    const widget = node.addDOMWidget("apixly_result", "div", panel, { serialize: false, hideOnZoom: false });
    widget.computeSize = () => [320, 128];
    const previous = node.onExecuted;
    node.onExecuted = function (message) {
      previous?.apply(this, arguments);
      const receipt = message?.apixly?.[0] || {};
      detail = { ...receipt, task_id: receipt.task_id || receipt.id || "" };
      status.textContent = detail.task_id ? `${detail.kind === "video" ? "Video" : "Image"} task ${detail.task_id} · ${detail.status}` : "No completed task receipt received.";
      copyTask.disabled = !detail.task_id;
      copyURL.disabled = !safeResultURL(detail.url);
      download.disabled = !nativeDownloadURL(detail.saved);
      app.graph.setDirtyCanvas(true, true);
    };
    node.setSize([Math.max(380, node.size[0]), Math.max(node.computeSize()[1], node.size[1])]);
  },
});
