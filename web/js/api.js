// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// Thin client for the LunaScout API (CONTRACT.md §4).

export const API_BASE = (window.LUNASCOUT_API ?? "/api").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(status, body, message) {
    super(message || (body && body.message) || `HTTP ${status}`);
    this.status = status;
    this.body = body || null;
    this.code = (body && body.error) || (status === 0 ? "network" : "http");
  }
}

/** A request cancelled by the caller's AbortSignal rejects with ApiError code "aborted". */
function abortedError() {
  const err = new ApiError(0, null, "Request cancelled.");
  err.code = "aborted";
  return err;
}

async function request(path, options = {}, timeoutMs = 30000, signal = null) {
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, timeoutMs);
  const onAbort = () => ctrl.abort();
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  let res;
  let body = null;
  try {
    res = await fetch(API_BASE + path, { ...options, signal: ctrl.signal });
    try { body = await res.json(); } catch (err) { if (err.name === "AbortError") throw err; /* non-JSON body */ }
  } catch (err) {
    if (signal && signal.aborted && !timedOut) throw abortedError();
    throw new ApiError(0, null, err.name === "AbortError" ? "The API took too long to answer." : "Could not reach the API.");
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}

export const getMeta = () => request("/meta", {}, 12000);

export const analyze = (payload) =>
  request("/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

/** Region-wide scan (POST /api/best-sites). `signal` cancels an in-flight request. */
export const bestSites = (payload, signal) =>
  request("/best-sites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, 60000, signal);

/** Absolute URL for a path the API returns (e.g. "/api/static/hillshade.png"). */
export function apiUrl(path) {
  if (!path) return null;
  if (/^https?:\/\//.test(path)) return path;
  const base = new URL(API_BASE + "/", window.location.href);
  return new URL(path, base).href;
}

/** Saved example response, used only when the API is unreachable (always labelled SAMPLE DATA). */
export async function loadFixture() {
  const res = await fetch("fixtures/sample_response.json");
  if (!res.ok) throw new Error("Sample data not found");
  const data = await res.json();
  data.is_sample = true;
  return data;
}
