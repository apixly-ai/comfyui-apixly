export function safeResultURL(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

export function nativeDownloadURL(saved) {
  if (!saved || !["temp", "output"].includes(saved.type)) return null;
  const filename = saved.filename;
  const subfolder = saved.subfolder || "";
  if (typeof filename !== "string" || !filename || /[\\/]/.test(filename) || filename.includes("..")) return null;
  if (typeof subfolder !== "string" || subfolder.split(/[\\/]/).includes("..")) return null;
  return `/view?${new URLSearchParams({ filename, subfolder, type: saved.type })}`;
}
