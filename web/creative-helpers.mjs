/** Native widget adapters and orbit math. No requests or generation calls. */
export const CREATIVE_KINDS = Object.freeze({
  ApixlyPromptViewpoint: "angle",
  ApixlyPromptLighting: "lighting",
  ApixlyPromptCamera: "camera",
  ApixlyPromptCompose: "compose",
});

export const CONTROL_DEFAULTS = Object.freeze({
  angle: { enabled: false, preset: "custom", yaw: 0, pitch: 0, shot: "none" },
  lighting: { enabled: false, preset: "none", brightness: 50, use_color: false,
    color: "#2e8fff", view: "perspective", direction: "unspecified", key_light: "none", light_yaw: 0,
    light_pitch: 0, rim_light: false, smart_text: "" },
  camera: { enabled: false, body: "none", lens: "none", use_focal: false, focal: 50, aperture: "none" },
  compose: { prompt: "", mode: "generate" },
});

const DIRECTIONAL = {
  front_high: { yaw: 0, pitch: 45 }, front_low: { yaw: 0, pitch: -45 },
  aerial_top_down: { yaw: 0, pitch: 80 }, back: { yaw: 180, pitch: 0 },
};

export function isCreativeNode(node) { return Object.hasOwn(CREATIVE_KINDS, node?.comfyClass); }
export function kindForNode(node) { return CREATIVE_KINDS[node?.comfyClass] || null; }
export function widgetValues(node) {
  const kind = kindForNode(node);
  if (!kind) throw new Error("This is not a supported prompt control.");
  return { ...CONTROL_DEFAULTS[kind], ...Object.fromEntries((node.widgets || []).map(w => [w.name, w.value])) };
}
function unspecified(value) { return value === "none" ? "" : value; }
function flag(value, path) {
  if (typeof value !== "boolean") throw new Error(`${path}: expected a boolean.`);
  return value;
}

export function settingsForNode(node) {
  const kind = kindForNode(node), v = widgetValues(node);
  if (kind === "angle") return { enabled: v.enabled, preset: v.preset, yaw: v.yaw, pitch: v.pitch, shot: v.shot };
  if (kind === "lighting") {
    if (!["unspecified", "legacy", "orbit"].includes(v.direction)) throw new Error("lighting.direction: choose unspecified, legacy or orbit.");
    const result = { enabled: v.enabled, preset: unspecified(v.preset), brightness: v.brightness,
      color: flag(v.use_color, "lighting.use_color") ? v.color : "", view: v.view, rimLight: v.rim_light, smartText: v.smart_text };
    if (v.direction === "legacy") result.keyLight = unspecified(v.key_light);
    if (v.direction === "orbit") Object.assign(result, { lightYaw: v.light_yaw, lightPitch: v.light_pitch });
    return result;
  }
  if (kind === "camera") return { enabled: v.enabled, body: unspecified(v.body), lens: unspecified(v.lens),
    focal: flag(v.use_focal, "camera.use_focal") ? v.focal : null, aperture: unspecified(v.aperture) };
  throw new Error("Compose is not an individual control.");
}

export function payloadForCompose(node, graph) {
  const values = widgetValues(node), tools = {};
  for (const input of node.inputs || []) {
    if (input.link == null) continue;
    if (input.name === "prompt") throw new Error("An upstream prompt is available after this free Compose node executes. Live preview needs its local prompt field.");
    if (!["angle", "lighting", "camera"].includes(input.name)) continue;
    const link = graph?.links?.[input.link];
    const origin = link && graph.getNodeById(link.origin_id);
    if (!origin || kindForNode(origin) !== input.name || link.origin_slot !== 0) {
      throw new Error("Connected control settings are available after free execution. Use the matching Apixly prompt node for live preview.");
    }
    tools[input.name] = settingsForNode(origin);
  }
  return { prompt: values.prompt, mode: values.mode, tools };
}

export function wrapYaw(value) { return ((value % 360) + 360) % 360; }
export function clampPitch(value) { return Math.max(-90, Math.min(90, value)); }
export function applyDrag(angles, dx, dy, sensitivity = 0.6) {
  return { yaw: wrapYaw(angles.yaw + dx * sensitivity), pitch: clampPitch(angles.pitch - dy * sensitivity) };
}
export function nudgeAngles(angles, direction, step = 15) {
  return {
    yaw: wrapYaw(angles.yaw + (direction === "left" ? -step : direction === "right" ? step : 0)),
    pitch: clampPitch(angles.pitch + (direction === "up" ? step : direction === "down" ? -step : 0)),
  };
}
export function projectPoint(lon, lat, viewYaw = 24, viewPitch = -16, radius = 78) {
  const d = Math.PI / 180, lambda = (lon - viewYaw) * d, phi = lat * d, phi0 = viewPitch * d;
  return {
    x: 100 + radius * Math.cos(phi) * Math.sin(lambda),
    y: 100 - radius * (Math.cos(phi0) * Math.sin(phi) - Math.sin(phi0) * Math.cos(phi) * Math.cos(lambda)),
    front: Math.sin(phi0) * Math.sin(phi) + Math.cos(phi0) * Math.cos(phi) * Math.cos(lambda) >= 0,
  };
}

export function updateControl(node, name, value) {
  const kind = kindForNode(node);
  if (!Object.hasOwn(CONTROL_DEFAULTS[kind] || {}, name)) throw new Error("Unknown creative control.");
  const set = (key, next) => { const widget = node.widgets?.find(w => w.name === key); if (widget) widget.value = next; };
  set(name, value);
  if (kind === "angle") {
    if (name === "preset" && DIRECTIONAL[value]) for (const [key, next] of Object.entries(DIRECTIONAL[value])) set(key, next);
    if (name === "yaw" || name === "pitch") set("preset", "custom");
  }
  if (kind === "lighting") {
    if (name === "light_yaw" || name === "light_pitch") set("direction", "orbit");
    if (name === "key_light") set("direction", "legacy");
    if (name === "color") set("use_color", true);
  }
  if (kind === "camera" && name === "focal") set("use_focal", true);
}

export function resetControl(node) {
  for (const [name, value] of Object.entries(CONTROL_DEFAULTS[kindForNode(node)] || {})) {
    const widget = node.widgets?.find(w => w.name === name);
    if (widget) widget.value = value;
  }
}
