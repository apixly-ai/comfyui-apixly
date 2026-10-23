/** Public authorization navigation only. Never handles device proofs or tokens. */
export function authorizationInfo(pending, now) {
  if (pending?.status !== "pending") return { state: "none" };
  const expires = pending.expires_at;
  if (typeof expires !== "number" || !Number.isFinite(expires)) return { state: "invalid" };
  if (expires * 1000 <= now) return { state: "expired" };
  try {
    const uri = new URL(pending.verification_uri_complete);
    if (uri.origin !== "https://apixly.ai" || !/^\/connect\/[A-Za-z0-9_-]{22}$/.test(uri.pathname)
      || uri.username || uri.password || uri.hash || !/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(pending.user_code)
      || [...uri.searchParams.keys()].length !== 1 || uri.searchParams.get("user_code") !== pending.user_code) return { state: "invalid" };
    return { state: "pending", uri: uri.href, expires, userCode: pending.user_code };
  } catch { return { state: "invalid" }; }
}

export function authorizationEnvironment(overrides = {}) {
  return {
    openWindow: (url, target) => globalThis.open?.(url, target),
    copyText: text => {
      if (!globalThis.navigator?.clipboard?.writeText) return Promise.reject(Error("Clipboard unavailable"));
      return globalThis.navigator.clipboard.writeText(text);
    },
    now: () => Date.now(),
    schedule: (fn, delay) => setTimeout(fn, delay),
    cancelTimer: timer => clearTimeout(timer),
    ...overrides,
  };
}

export function createAuthorizationLauncher(environment) {
  let page, blank = false, destination = "", notice = "";
  const fallback = "Automatic opening was blocked or unavailable. Use Open or Copy below.";
  function alive() { try { return Boolean(page && !page.closed); } catch { return false; } }
  function release() {
    if (blank && alive()) { try { page.close(); } catch { /* Only this prepared blank tab is owned. */ } }
    page = undefined; blank = false; destination = ""; notice = "";
  }
  function prepare() {
    release();
    try {
      // Keep a real handle. A noopener feature can itself return null even if
      // the browser opened a tab, which would make outcome reporting ambiguous.
      page = environment.openWindow("about:blank", "_blank");
      if (!alive()) { page = undefined; notice = fallback; return; }
      blank = true;
      page.opener = null;
    } catch { release(); notice = fallback; }
  }
  function navigate(uri) {
    if (!alive()) {
      notice = page ? "The authorization tab was closed. Use Open or Copy below." : notice || fallback;
      page = undefined; blank = false;
      return notice;
    }
    try {
      page.location.replace(uri);
      blank = false; destination = uri;
      return "Authorization tab opened. Complete approval there, or use Open or Copy below.";
    } catch {
      release();
      return "Could not navigate to the authorization page. Use Open or Copy below.";
    }
  }
  function open(uri) {
    if (alive() && !blank && destination === uri) {
      try { page.focus(); return "Authorization tab is already open. Complete approval there."; }
      catch { /* The browser may have separated the tab's browsing context. */ }
    }
    prepare();
    return navigate(uri);
  }
  return { prepare, navigate, open, release };
}
