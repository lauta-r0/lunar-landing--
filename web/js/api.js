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

async function request(path, options = {}, timeoutMs = 30000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(API_BASE + path, { ...options, signal: ctrl.signal });
  } catch (err) {
    throw new ApiError(0, null, err.name === "AbortError" ? "The API took too long to answer." : "Could not reach the API.");
  } finally {
    clearTimeout(timer);
  }
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON body */ }
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
