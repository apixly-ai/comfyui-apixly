import "./creative-compiler.js";
import {
  applyDrag, controlTransaction, effectiveAngles, isControlUpdate, kindForNode, nudgeAngles, payloadForCompose, projectPoint,
  resetControl, settingsForNode, updateControl, widgetValues,
} from "./creative-helpers.mjs";

const PANELS = new WeakMap();
const CALLBACKS = new WeakSet();
const TITLES = { angle: "Viewpoint", lighting: "Lighting", camera: "Camera & Lens", compose: "Final prompt" };
const PRESETS = {
  angle: [["custom", "Custom"], ["front_high", "High angle"], ["front_low", "Low angle"],
    ["aerial_top_down", "Overhead"], ["back", "Rear view"], ["fisheye", "Fisheye"], ["dutch", "Dutch angle"]],
  lighting: [["goldenHour", "Golden hour"], ["blueBacklight", "Blue backlight"], ["rembrandt", "Rembrandt"],
    ["cyberpunk", "Neon"], ["psychedelicSunset", "Sunset glow"], ["mysteriousDark", "Low key"],
    ["overexposedFilm", "Film glow"], ["nolanGray", "Cool gray"]],
};
const BUTTON = "min-height:44px;min-width:44px;border:1px solid #2e8fff55;border-radius:9px;background:#1670f018;color:inherit;cursor:pointer;padding:7px 10px;font:inherit;white-space:normal";
function el(tag, text, style) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (style) item.style.cssText = style;
  return item;
}
function svg(tag, attrs = {}) {
  const item = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, value);
  return item;
}
function button(label, action) {
  const item = el("button", label, BUTTON); item.type = "button";
  item.addEventListener("click", event => { event.preventDefault(); event.stopPropagation(); action(); });
  return item;
}
function refreshAll(app) {
  for (const node of app.graph?._nodes || []) PANELS.get(node)?.();
  app.graph?.setDirtyCanvas(true, true);
}
function change(node, app, name, value) { updateControl(node, name, value); refreshAll(app); }

function orbit(node, kind, app) {
  const wrapper = el("div", undefined, "display:flex;flex-direction:column;gap:6px;min-width:0");
  const surface = el("div", undefined, "position:relative;aspect-ratio:1;width:min(200px,100%);align-self:center;touch-action:none;border:1px solid #2e8fff35;border-radius:13px;background:radial-gradient(circle at 35% 25%,#2e8fff1b,#06070a88);overflow:hidden;cursor:grab");
  surface.setAttribute("aria-label", `${TITLES[kind]} direction diagram`);
  surface.tabIndex = 0;
  const drawing = svg("svg", { viewBox: "0 0 200 200", width: "100%", height: "100%", "aria-hidden": "true" });
  surface.append(drawing);
  const readout = el("div", "", "text-align:center;color:#94a3b8;font-size:11px;overflow-wrap:anywhere");
  const arrows = el("div", undefined, "display:grid;grid-template-columns:repeat(4,minmax(44px,1fr));gap:3px");
  const names = kind === "angle" ? ["yaw", "pitch"] : ["light_yaw", "light_pitch"];
  let view = { yaw: 24, pitch: -16 }, drag = null;
  function values() {
    return effectiveAngles(node);
  }
  function set(next) {
    updateControl(node, names[0], Math.round(next.yaw * 10) / 10);
    updateControl(node, names[1], Math.round(next.pitch * 10) / 10);
    refreshAll(app);
  }
  for (const [direction, label] of [["left", "←"], ["up", "↑"], ["down", "↓"], ["right", "→"]]) {
    const item = button(label, () => set(nudgeAngles(values(), direction)));
    item.setAttribute("aria-label", `${TITLES[kind]} ${direction} 15 degrees`); arrows.append(item);
  }
  surface.addEventListener("pointerdown", event => {
    event.stopPropagation();
    drag = { x: event.clientX, y: event.clientY, marker: Boolean(event.target.closest?.("[data-orbit-marker]")) };
    surface.setPointerCapture(event.pointerId);
  });
  surface.addEventListener("pointermove", event => {
    if (!drag) return; event.stopPropagation();
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    drag.x = event.clientX; drag.y = event.clientY;
    if (drag.marker) set(applyDrag(values(), dx, dy));
    else {
      if (kind === "lighting" && widgetValues(node).view === "front") {
        updateControl(node, "view", "perspective"); view = { yaw: 0, pitch: 0 };
      }
      view = applyDrag(view, dx, dy); render();
    }
  });
  function end(event) {
    drag = null;
    if (surface.hasPointerCapture(event.pointerId)) surface.releasePointerCapture(event.pointerId);
  }
  surface.addEventListener("pointerup", end); surface.addEventListener("pointercancel", end);
  surface.addEventListener("keydown", event => {
    const key = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" }[event.key];
    if (key) { event.preventDefault(); event.stopPropagation(); set(nudgeAngles(values(), key)); }
  });
  function path(points, front) {
    let pen = false, d = "";
    for (const point of points) {
      if (point.front === front) { d += `${pen ? "L" : "M"}${point.x.toFixed(1)} ${point.y.toFixed(1)} `; pen = true; }
      else pen = false;
    }
    return d;
  }
  function render() {
    const v = values(); drawing.replaceChildren();
    if (![v.yaw, v.pitch].every(Number.isFinite)) return;
    const observation = kind === "lighting" && widgetValues(node).view === "front" ? { yaw: 0, pitch: 0 } : view;
    drawing.append(svg("circle", { cx: 100, cy: 100, r: 78, fill: "#2e8fff0a", stroke: "#94a3b855" }));
    const lines = [];
    for (let lat = -60; lat <= 60; lat += 30) {
      const pts = []; for (let lon = 0; lon <= 360; lon += 8) pts.push(projectPoint(lon, lat, observation.yaw, observation.pitch)); lines.push(pts);
    }
    for (let lon = 0; lon < 360; lon += 45) {
      const pts = []; for (let lat = -90; lat <= 90; lat += 8) pts.push(projectPoint(lon, lat, observation.yaw, observation.pitch)); lines.push(pts);
    }
    for (const front of [false, true]) {
      for (const pts of lines) drawing.append(svg("path", { d: path(pts, front), fill: "none", stroke: front ? "#94a3b899" : "#94a3b82b", "stroke-width": 0.8 }));
      if (!front) {
        drawing.append(svg("ellipse", { cx: 100, cy: 143, rx: 23, ry: 6, fill: "#00000066" }));
        drawing.append(svg("rect", { x: 80, y: 64, width: 40, height: 74, rx: 14, fill: "#0f172a", stroke: "#2e8fff88" }));
        const subject = svg("text", { x: 100, y: 106, fill: "#94a3b8", "font-size": 9, "text-anchor": "middle" }); subject.textContent = "Subject"; drawing.append(subject);
      }
    }
    const point = projectPoint(v.yaw, v.pitch, observation.yaw, observation.pitch, 79.5);
    drawing.append(svg("line", { x1: point.x, y1: point.y, x2: 100, y2: 100, stroke: "#2e8fff", "stroke-dasharray": "3 3", opacity: point.front ? 0.8 : 0.3 }));
    const marker = svg("g", { "data-orbit-marker": "true", cursor: "grab", opacity: point.front ? 1 : 0.55 });
    marker.append(svg("circle", { cx: point.x, cy: point.y, r: 24, fill: "transparent" }));
    marker.append(svg("circle", { cx: point.x, cy: point.y, r: 11, fill: kind === "lighting" ? "#d9edff" : "#1670f0", stroke: "#8ec9ff", "stroke-width": 2 }));
    marker.append(svg(kind === "lighting" ? "circle" : "rect", kind === "lighting" ? { cx: point.x, cy: point.y, r: 4, fill: "#2e8fff" } : { x: point.x - 5, y: point.y - 3, width: 10, height: 6, rx: 1, fill: "#d9edff" }));
    drawing.append(marker);
    readout.textContent = `${Math.round(v.yaw)}° azimuth · ${v.pitch > 0 ? "+" : ""}${Math.round(v.pitch)}° elevation`;
  }
  wrapper.append(surface, readout, arrows);
  return { element: wrapper, render };
}

export function attachCreativePanel(node, app) {
  const kind = kindForNode(node);
  if (!kind || PANELS.has(node)) return;
  const root = el("div", undefined, "box-sizing:border-box;display:flex;flex-direction:column;gap:9px;width:100%;height:100%;padding:12px;border:1px solid #2e8fff44;border-radius:13px;background:linear-gradient(145deg,#2e8fff0d,#06070ae8);color:#e2e8f0;font:12px/1.45 system-ui;pointer-events:auto;overflow:auto;container-type:inline-size;container-name:apixly-prompt");
  root.dataset.apixlyCreative = kind;
  const responsive = el("style", ".apixly-creative-layout{display:grid;grid-template-columns:minmax(140px,1fr) minmax(130px,1fr);gap:9px;align-items:start}@container apixly-prompt (max-width:380px){.apixly-creative-layout{grid-template-columns:minmax(0,1fr)}}");
  root.append(responsive);
  root.addEventListener("pointerdown", event => event.stopPropagation());
  const header = el("div", undefined, "display:flex;align-items:center;justify-content:space-between;gap:8px");
  header.append(el("strong", TITLES[kind], "font-size:14px;color:#d9edff"));
  let toggle;
  if (kind !== "compose") {
    toggle = button("Off", () => change(node, app, "enabled", !widgetValues(node).enabled));
    toggle.setAttribute("role", "switch"); toggle.setAttribute("aria-label", `Enable ${TITLES[kind]}`); header.append(toggle);
  } else header.append(el("span", "FREE · PROMPT ONLY", "color:#8ec9ff;font-size:10px;letter-spacing:.08em"));
  const status = el("div", "", "min-height:18px;color:#94a3b8;overflow-wrap:anywhere");
  status.setAttribute("aria-live", "polite");
  root.append(header, status);
  let orbitControl;
  const presetButtons = [];
  if (kind === "angle" || kind === "lighting") {
    const row = el("div"); row.className = "apixly-creative-layout";
    orbitControl = orbit(node, kind, app); row.append(orbitControl.element);
    const presets = el("div", undefined, "display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px");
    for (const [id, label] of PRESETS[kind]) {
      const item = button(label, () => change(node, app, "preset", id)); item.style.cssText += ";font-size:11px;padding:5px";
      presetButtons.push([id, item]); presets.append(item);
    }
    row.append(presets); root.append(row);
    root.append(el("div", "Drag the marker to set direction; drag the grid to inspect. Positive elevation is above. Diagram only." + (kind === "angle" ? " Named presets override raw sliders; the first move switches to Custom." : ""), "color:#64748b;font-size:10px"));
  }
  if (kind === "camera") {
    const diagram = svg("svg", { viewBox: "0 0 300 90", width: "100%", height: 90, role: "img", "aria-label": "Lens style diagram" });
    diagram.append(svg("path", { d: "M48 16L225 32M48 74L225 58", fill: "none", stroke: "#2e8fff66", "stroke-width": 1.5 }));
    for (const [radius, color] of [[34, "#2e8fff44"], [25, "#1670f088"], [14, "#8ec9ff"]]) diagram.append(svg("circle", { cx: 230, cy: 45, r: radius, fill: "#0f172a", stroke: color, "stroke-width": 2 }));
    const label = svg("text", { x: 26, y: 49, fill: "#94a3b8", "font-size": 12 }); label.textContent = "Style guidance"; diagram.append(label); root.append(diagram);
    const strip = el("div", undefined, "display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px");
    for (const focal of [16, 24, 35, 50, 85, 135]) strip.append(button(`${focal} mm`, () => change(node, app, "focal", focal)));
    root.append(strip, el("div", "Body, lens and aperture choices above describe photographic style. They do not set real optics or EXIF.", "color:#94a3b8;font-size:11px"));
  }
  const preview = el("textarea", undefined, "box-sizing:border-box;resize:vertical;width:100%;min-height:90px;border:1px solid #334155;border-radius:9px;padding:10px;color:#cbd5e1;background:#06070a99;font:11px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere");
  preview.readOnly = true; preview.spellcheck = false;
  preview.setAttribute("aria-label", kind === "compose" ? "Final prompt preview" : `${TITLES[kind]} instruction preview`);
  if (kind === "compose") preview.style.cssText += ";min-height:180px";
  const actions = el("div", undefined, "display:flex;gap:6px;flex-wrap:wrap");
  const copy = button("Copy prompt", async () => {
    try { await navigator.clipboard.writeText(preview.value); status.textContent = "Prompt copied. No generation submitted."; }
    catch { status.textContent = "Select the prompt below and copy it manually."; preview.focus?.(); preview.select?.(); }
  });
  const reset = button(kind === "compose" ? "Reset connected tools" : "Reset", () => {
    if (kind === "compose") {
      for (const input of node.inputs || []) {
        const link = app.graph?.links?.[input.link], origin = link && app.graph.getNodeById(link.origin_id);
        if (["angle", "lighting", "camera"].includes(kindForNode(origin))) resetControl(origin);
      }
    } else resetControl(node);
    refreshAll(app);
  });
  actions.append(copy, reset); root.append(preview, actions);
  if (kind === "compose") root.append(el("div", "Connect final_prompt explicitly to a generation node. Previewing, copying or resetting never starts a paid task.", "color:#64748b;font-size:11px"));
  const widget = node.addDOMWidget("apixly_creative", "div", root, { serialize: false, hideOnZoom: false });
  widget.computeSize = () => [280, kind === "compose" ? 380 : kind === "camera" ? 500 : 650];
  function refresh() {
    try {
      const values = widgetValues(node);
      if (toggle) { toggle.textContent = values.enabled ? "On" : "Off"; toggle.setAttribute("aria-checked", String(values.enabled)); }
      for (const [id, item] of presetButtons) item.style.cssText = BUTTON + `;font-size:11px;padding:5px;border-color:${values.preset === id ? "#2e8fff" : "#2e8fff44"}`;
      orbitControl?.render();
      const payload = kind === "compose" ? payloadForCompose(node, app.graph) : { prompt: "", mode: "generate", tools: { [kind]: settingsForNode(node) } };
      const result = globalThis.ApixlyCreativeControlsV1.composeCreativePrompt(payload);
      preview.value = result.final_prompt; copy.disabled = !preview.value;
      status.textContent = kind === "compose" ? (result.changed ? `Free preview · ${result.applied_tools.length} tools applied` : "Free preview · Base prompt unchanged") : !values.enabled ? "Off · Settings retained, no prompt added" : result.changed ? "On · Prompt guidance only" : "On · Neutral settings, no prompt added";
    } catch (error) {
      preview.value = ""; copy.disabled = true; status.textContent = error.message;
    }
  }
  PANELS.set(node, refresh);
  for (const native of node.widgets || []) {
    if (native.name === "apixly_creative") continue;
    const previous = native.callback;
    native.callback = function (value, ...args) {
      if (CALLBACKS.has(native)) return;
      CALLBACKS.add(native);
      try {
        previous?.call(this, value, ...args);
        if (!isControlUpdate(node)) { updateControl(node, native.name, value); refreshAll(app); }
      } finally { CALLBACKS.delete(native); }
    };
  }
  const configure = node.configure;
  if (configure) node.configure = function (...args) {
    try { return controlTransaction(node, () => configure.apply(this, args)); }
    finally { refreshAll(app); }
  };
  for (const hook of ["onConnectionsChange", "onConfigure", "onAdded"]) {
    const previous = node[hook];
    node[hook] = function (...args) { previous?.apply(this, args); if (!isControlUpdate(node)) refreshAll(app); };
  }
  const previous = node.onExecuted;
  node.onExecuted = function (message) {
    previous?.apply(this, arguments);
    const actual = message?.apixly_prompt?.[0];
    if (actual && kind === "compose") { preview.value = actual.final_prompt; copy.disabled = !preview.value; status.textContent = "Executed prompt · Recomputed by the host, no generation submitted"; }
  };
  refresh();
  node.setSize([Math.max(300, node.size[0]), Math.max(node.computeSize()[1], node.size[1])]);
}
