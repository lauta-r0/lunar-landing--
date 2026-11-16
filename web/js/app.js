// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// LunaScout single-screen app: settings → /api/analyze → map, results, timeline;
// "Find best sites" → /api/best-sites → heatmap, ranked pins and list (never from the fixture).

import { getMeta, analyze, bestSites, loadFixture, apiUrl, ApiError } from "./api.js";
import { MapView } from "./map.js";
import { SouthPolarStereo } from "./proj.js";
import {
  CLASS_LABEL, METRIC_TIPS, esc, fixText, fmtLat, fmtLon, fmtHours, fmtUtc, hhmmUtc, reasonText,
} from "./format.js";
import { initTooltips } from "./tooltip.js";
import { renderAbout } from "./about.js";

const $ = (id) => document.getElementById(id);
const STORE_KEY = "lunascout.inputs.v1";

// Used only if /api/meta is unreachable; the result shown is then the labelled sample.
const FALLBACK_DEFAULTS = {
  target: { lat: -85.47628, lon: 31.39691 },
  landing_utc: "2027-10-12T14:00:00Z",
  mission_days: 7,
  ellipse: { semi_major_m: 1000, semi_minor_m: 600, azimuth_deg: 0 },
  limits: { max_dark_h: 50, max_comm_gap_h: 72, min_earth_pct: 50, max_slope_deg: 8, min_sun_margin_deg: 0 },
  options: { risk_margin: 0.2, delay_days_max: 30, include_recommendations: true, observer_height_m: 2.0 },
};

// Quick picks: named lunar locations (lat, east-positive lon). Each one uses the default date and duration.
const QUICK_PICKS = [
  { id: "mons_mouton", name: "Mons Mouton", lat: -84.6, lon: 31.0,
    note: "IAU reference center" },
  { id: "viper_area", name: "VIPER Mission Area", lat: -85.42088, lon: 31.6218,
    note: "published center of the VIPER rover study area" },
  { id: "nobile_rim_1", name: "Nobile Rim 1", lat: -85.431, lon: 37.241,
    note: "published reference point in a region NASA evaluated for Artemis" },
];

const FIELDS = {
  lat: "f-lat", lon: "f-lon", date: "f-date", days: "f-days",
  smaj: "f-smaj", smin: "f-smin", az: "f-az",
  dark: "f-dark", gap: "f-gap", earth: "f-earth", slope: "f-slope",
  margin: "f-margin", risk: "f-risk", delay: "f-delay", height: "f-height",
};

const state = {
  meta: null,
  live: false,
  running: false,
  resp: null,
  lastRunKey: null,
  originTarget: null,
  timeline: null,
  proj: new SouthPolarStereo(null), // replaced by the CRS from /api/meta
  // best sites: last response, the request it answers (key), and the request in flight
  best: { resp: null, key: null, loading: false, pendingKey: null, ctrl: null, offline: false },
};

/* ================= markers (inline SVG, same shapes as the map) ================= */

const ICON = {
  viable: '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="5" fill="#3ddc84" stroke="#000"/></svg>',
  risky: '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1 L11.2 10.6 H0.8 Z" fill="#ff9f43" stroke="#000" stroke-linejoin="round"/></svg>',
  not_viable: '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2 L10 10 M10 2 L2 10" stroke="#000" stroke-width="4.4" stroke-linecap="round"/><path d="M2 2 L10 10 M10 2 L2 10" stroke="#ff6b6b" stroke-width="2.4" stroke-linecap="round"/></svg>',
  check: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M2 6.5 5 9.2 10 3"/></svg>',
  cross: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6"/></svg>',
  info: '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M6 5.2v4M6 2.8v.4"/></svg>',
  arrow: '<svg width="16" height="16" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true" style="flex:none"><path d="M2 7h10M8 3l4 4-4 4"/></svg>',
};

/* ================= form ================= */

function fillForm(req) {
  const set = (k, v) => { $(FIELDS[k]).value = v ?? ""; };
  set("lat", req.target.lat);
  set("lon", req.target.lon);
  set("date", isoToField(req.landing_utc));
  set("days", req.mission_days);
  set("smaj", req.ellipse.semi_major_m);
  set("smin", req.ellipse.semi_minor_m);
  set("az", req.ellipse.azimuth_deg);
  set("dark", req.limits.max_dark_h);
  set("gap", req.limits.max_comm_gap_h);
  set("earth", req.limits.min_earth_pct);
  set("slope", req.limits.max_slope_deg);
  const m = req.limits.min_sun_margin_deg;
  set("margin", m ? m : "");
  set("risk", Math.round((req.options?.risk_margin ?? 0.2) * 100));
  set("delay", req.options?.delay_days_max ?? 30);
  set("height", req.options?.observer_height_m ?? 2);
}

/** "2027-10-12T14:00:00Z" → "2027-10-12 14:00" (the date field always shows ISO, never a locale format). */
function isoToField(iso) {
  return (iso || "").slice(0, 16).replace("T", " ");
}

/** "2027-10-12 14:00" (or with "T") → "2027-10-12T14:00:00Z"; "" if malformed. */
function fieldToIso(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})$/.exec(text.trim());
  if (!m) return "";
  const iso = `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00Z`;
  const d = new Date(iso);
  // reject impossible dates such as 2027-02-31 or 25:00
  return !isNaN(d) && d.toISOString().slice(0, 16) === iso.slice(0, 16) ? iso : "";
}

function readForm() {
  const v = (k) => $(FIELDS[k]).value.trim();
  const num = (k) => (v(k) === "" ? NaN : Number(v(k)));
  const margin = v("margin") === "" ? 0 : Number(v("margin"));
  return {
    target: { lat: num("lat"), lon: num("lon") },
    landing_utc: fieldToIso(v("date")),
    mission_days: num("days"),
    ellipse: { semi_major_m: num("smaj"), semi_minor_m: num("smin"), azimuth_deg: num("az") },
    limits: {
      max_dark_h: num("dark"), max_comm_gap_h: num("gap"), min_earth_pct: num("earth"),
      max_slope_deg: num("slope"), min_sun_margin_deg: margin,
    },
    options: {
      risk_margin: num("risk") / 100,
      delay_days_max: num("delay"),
      include_recommendations: true,
      observer_height_m: num("height"),
    },
  };
}

const runKey = (req) => JSON.stringify(req);

/* ================= analyzable area ================= */

const AREA_NAME = "Mons Mouton region";

function areaBounds() {
  return state.meta?.coverage?.approx_bounds_latlon || null;
}

function renderAreaHint() {
  const b = areaBounds();
  const el = $("area-hint");
  if (!b) { el.hidden = true; return; }
  el.hidden = false;
  el.textContent = `Analyzable area: lat ${b.lat_min.toFixed(2)}° to ${b.lat_max.toFixed(2)}°, lon ${b.lon_min.toFixed(2)}–${b.lon_max.toFixed(2)}° E (${AREA_NAME})`;
}

/** Which coordinates fall outside the approximate lat/lon box of the terrain data. */
function outsideArea(lat, lon) {
  const b = areaBounds();
  if (!b || !isFinite(lat) || !isFinite(lon)) return null;
  const badLat = lat < b.lat_min || lat > b.lat_max;
  const badLon = lon < b.lon_min || lon > b.lon_max;
  return badLat || badLon ? { badLat, badLon } : null;
}

function showAreaError(on) {
  $("area-error").hidden = !on;
  if (on) {
    $("area-error-text").textContent = `This target is outside the terrain data. Pick a point inside the ${AREA_NAME}, or start from its center.`;
  }
}

function goToRegionCenter() {
  const c = state.meta?.coverage;
  if (!c) return;
  $(FIELDS.lat).value = c.center_lat;
  $(FIELDS.lon).value = c.center_lon;
  run({ fromUser: true });
}

/** True when map x/y metres fall inside the analyzable area box of /api/meta (unknown → true). */
function insideCoverageXY(x, y) {
  const b = state.meta?.coverage?.bounds_xy_m;
  if (!b) return true;
  return x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3];
}

/* ================= pick a target on the map ================= */

function pickTarget(x, y) {
  if (state.running || state.best.loading) return; // respect the "Analyzing…" / "Scanning…" lock
  const [lat, lon] = state.proj.toLatLon(x, y);
  $(FIELDS.lat).value = lat.toFixed(5);
  $(FIELDS.lon).value = lon.toFixed(5);
  map.setPin([x, y]);
  map.centerOn(x, y);
  if (!insideCoverageXY(x, y)) {
    // outside the terrain data: no API call, show the out-of-area message
    clearErrors();
    showAreaError(true);
    fieldError("lat", "e-lat", "Outside the analyzable area.");
    fieldError("lon", "e-lon", "Outside the analyzable area.");
    setNotices([{
      kind: "error", title: "Outside the terrain data",
      text: `The picked point (${fmtLat(lat)}, ${fmtLon(lon)}) is outside the analyzable area. Pick a point inside the ${AREA_NAME}, or start from its center.`,
      actions: state.meta?.coverage ? [{ label: "Go to region center", onClick: goToRegionCenter }] : [],
    }]);
    updateDirty();
    return;
  }
  run({ fromUser: true });
}

function clearErrors() {
  showAreaError(false);
  document.querySelectorAll(".field-error").forEach((e) => { e.textContent = ""; });
  document.querySelectorAll(".input[aria-invalid]").forEach((e) => e.removeAttribute("aria-invalid"));
}

function fieldError(fieldKey, errId, msg) {
  const input = $(FIELDS[fieldKey]);
  if (input) {
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-describedby", errId);
  }
  const el = $(errId);
  if (el && !el.textContent) el.textContent = msg;
}

/** needTarget = false skips the target checks (the best-sites scan has no target). */
function validate(req, { needTarget = true } = {}) {
  clearErrors();
  const lim = state.meta?.input_limits || {};
  const errs = [];
  const check = (key, errId, value, range, label, { integer = false } = {}) => {
    if (!isFinite(value)) { errs.push([key, errId, `Enter a number for ${label}.`]); return; }
    if (integer && !Number.isInteger(value)) { errs.push([key, errId, `${label} must be a whole number.`]); return; }
    if (range && (value < range[0] || value > range[1])) errs.push([key, errId, `${label} must be between ${range[0]} and ${range[1]}.`]);
  };
  if (needTarget) {
    check("lat", "e-lat", req.target.lat, [-90, 90], "Latitude");
    check("lon", "e-lon", req.target.lon, [-180, 180], "Longitude");
  }
  const out = errs.length || !needTarget ? null : outsideArea(req.target.lat, req.target.lon);
  if (out) {
    const b = areaBounds();
    if (out.badLat) errs.push(["lat", "e-lat", `Must be between ${b.lat_min.toFixed(2)}° and ${b.lat_max.toFixed(2)}°.`]);
    if (out.badLon) errs.push(["lon", "e-lon", `Must be between ${b.lon_min.toFixed(2)}° and ${b.lon_max.toFixed(2)}° E.`]);
  }
  if (!req.landing_utc) errs.push(["date", "e-date", "Use YYYY-MM-DD HH:MM (UTC), e.g. 2027-10-12 14:00."]);
  else if (state.meta?.ephemeris_range_utc) {
    const [a, b] = state.meta.ephemeris_range_utc.map(Date.parse);
    const t = Date.parse(req.landing_utc);
    if (t < a || t > b) errs.push(["date", "e-date", `Ephemeris covers ${fmtUtc(state.meta.ephemeris_range_utc[0])} to ${fmtUtc(state.meta.ephemeris_range_utc[1])}.`]);
  }
  check("days", "e-days", req.mission_days, lim.mission_days || [1, 30], "Mission duration", { integer: true });
  check("smaj", "e-ellipse", req.ellipse.semi_major_m, lim.semi_major_m || [50, 5000], "Semi-major");
  check("smin", "e-ellipse", req.ellipse.semi_minor_m, lim.semi_minor_m || [50, 5000], "Semi-minor");
  check("az", "e-ellipse", req.ellipse.azimuth_deg, [0, 360], "Azimuth");
  if (isFinite(req.ellipse.semi_major_m) && isFinite(req.ellipse.semi_minor_m) && req.ellipse.semi_minor_m > req.ellipse.semi_major_m) {
    errs.push(["smin", "e-ellipse", "Semi-minor can't be larger than semi-major."]);
  }
  check("dark", "e-dark", req.limits.max_dark_h, lim.max_dark_h || [1, 400], "Max darkness");
  check("gap", "e-gap", req.limits.max_comm_gap_h, lim.max_comm_gap_h || [1, 400], "Max comms gap");
  check("earth", "e-earth", req.limits.min_earth_pct, lim.min_earth_pct || [0, 100], "Min Earth time");
  check("slope", "e-slope", req.limits.max_slope_deg, lim.max_slope_deg || [1, 30], "Max slope");
  check("margin", "e-margin", req.limits.min_sun_margin_deg, lim.min_sun_margin_deg || [0, 15], "Sun clearance");
  check("risk", "e-risk", req.options.risk_margin * 100, [0, 90], "Risk margin");
  check("delay", "e-delay", req.options.delay_days_max, lim.delay_days_max || [0, 60], "Delay range", { integer: true });
  check("height", "e-height", req.options.observer_height_m, [0, 20], "Observer height");

  for (const [key, errId, msg] of errs) fieldError(key, errId, msg);
  showAreaError(!!out);
  if (errs.length) {
    const first = $(FIELDS[errs[0][0]]);
    if (["margin", "risk", "delay", "height"].includes(errs[0][0])) $("advanced").open = true;
    first?.focus();
  }
  return errs.length === 0;
}

function applyInputLimits() {
  const lim = state.meta?.input_limits;
  if (!lim) return;
  const map = { days: "mission_days", smaj: "semi_major_m", smin: "semi_minor_m", dark: "max_dark_h", gap: "max_comm_gap_h", earth: "min_earth_pct", slope: "max_slope_deg", delay: "delay_days_max", margin: "min_sun_margin_deg" };
  for (const [k, key] of Object.entries(map)) {
    if (lim[key]) { $(FIELDS[k]).min = lim[key][0]; $(FIELDS[k]).max = lim[key][1]; }
  }
  if (state.meta.ephemeris_range_utc) {
    const [a, b] = state.meta.ephemeris_range_utc;
    $("h-date").innerHTML = `ISO format, UTC · YYYY-MM-DD HH:MM<br>Ephemeris: <span style="white-space:nowrap">${esc(a.slice(0, 10))}</span> to <span style="white-space:nowrap">${esc(b.slice(0, 10))}</span>`;
  }
}

function updateDirty() {
  const dirty = state.lastRunKey !== null && !state.running && runKey(readForm()) !== state.lastRunKey;
  $("dirty-note").hidden = !dirty;
  markActiveChip();
  updateBestStale();
}

/* ================= quick picks ================= */

function shortName(name) { return name.replace(/\s*\(.*\)\s*$/, ""); }

function renderSites() {
  const list = $("sites-list");
  list.innerHTML = "";
  for (const s of QUICK_PICKS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = s.name;
    b.dataset.lat = s.lat;
    b.dataset.lon = s.lon;
    b.setAttribute("aria-pressed", "false");
    const timing = { landing_utc: state.meta.defaults.landing_utc, mission_days: state.meta.defaults.mission_days };
    b.dataset.tip = `${s.name} (${s.note}) · ${fmtLat(s.lat)}, ${fmtLon(s.lon)} · landing ${fmtUtc(timing.landing_utc)}, ${timing.mission_days} days. Select to analyze it.`;
    b.addEventListener("click", () => {
      $(FIELDS.lat).value = s.lat;
      $(FIELDS.lon).value = s.lon;
      $(FIELDS.date).value = isoToField(timing.landing_utc);
      $(FIELDS.days).value = timing.mission_days;
      run({ fromUser: true });
    });
    list.appendChild(b);
  }
  markActiveChip();
}

function markActiveChip() {
  const lat = Number($(FIELDS.lat).value), lon = Number($(FIELDS.lon).value);
  document.querySelectorAll("#sites-list .chip").forEach((b) => {
    const on = Math.abs(Number(b.dataset.lat) - lat) < 1e-5 && Math.abs(Number(b.dataset.lon) - lon) < 1e-5;
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function siteNameFor(lat, lon) {
  const s = [...QUICK_PICKS, ...(state.meta?.curated_sites || [])].find((c) => Math.abs(c.lat - lat) < 1e-4 && Math.abs(c.lon - lon) < 1e-4);
  return s ? s.name : null;
}

/* ================= notices ================= */

function setNotices(items) {
  const box = $("notices");
  box.innerHTML = "";
  for (const n of items) {
    const div = document.createElement("div");
    div.className = `notice notice--${n.kind || "info"}`;
    div.setAttribute("role", n.kind === "error" ? "alert" : "status");
    div.innerHTML = `<div class="notice-body">${n.title ? `<strong>${esc(n.title)}</strong> · ` : ""}${esc(fixText(n.text))}</div>`;
    if (n.actions?.length) {
      const act = document.createElement("div");
      act.className = "notice-actions";
      for (const a of n.actions) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn btn--sm";
        b.textContent = a.label;
        b.addEventListener("click", a.onClick);
        act.appendChild(b);
      }
      div.appendChild(act);
    }
    box.appendChild(div);
  }
}

/* ================= run ================= */

function setRunning(on) {
  state.running = on;
  const btn = $("run-btn");
  btn.setAttribute("aria-busy", on ? "true" : "false");
  $("run-label").textContent = on ? "Analyzing…" : "Run analysis";
  $("map-frame").classList.toggle("is-loading", on);
  updateDirty();
  updateBestUi();
}

async function run({ fromUser = false } = {}) {
  if (state.running || state.best.loading) return; // analyze and best-sites never run together
  const req = readForm();
  if (!validate(req)) return;
  if (fromUser || !state.originTarget) state.originTarget = { ...req.target };
  setRunning(true);
  try {
    const resp = await analyze(req);
    state.live = true;
    state.best.offline = false;
    state.lastRunKey = runKey(req);
    state.lastReq = req;
    setNotices([]);
    render(resp);
    map.setPin(null);
    saveInputs(req);
  } catch (err) {
    handleRunError(err, req);
  } finally {
    setRunning(false);
  }
}

function setStale(on) {
  document.body.classList.toggle("is-stale", on && !!state.resp);
}

function handleRunError(err, req) {
  console.error("Analysis failed", err);
  setStale(true);
  if (!(err instanceof ApiError)) {
    setNotices([{ kind: "error", title: "Error", text: String(err.message || err) }]);
    return;
  }
  const body = err.body || {};
  if (err.status === 0) state.best.offline = true; // API unreachable: best sites are unavailable too
  if (err.status === 400 && body.error === "out_of_coverage") {
    const st = body.suggested_target;
    setNotices([{
      kind: "error", title: "Outside the terrain data", text: body.message || "The target is outside the analyzable area.",
      actions: st ? [{ label: "Go to suggested target", onClick: () => { $(FIELDS.lat).value = st.lat; $(FIELDS.lon).value = st.lon; run({ fromUser: true }); } }] : [],
    }]);
    fieldError("lat", "e-lat", "Outside the analyzable area.");
    fieldError("lon", "e-lon", "Outside the analyzable area.");
    return;
  }
  if (err.status === 400 && body.error === "out_of_ephemeris_range") {
    setNotices([{ kind: "error", title: "Date out of range", text: body.message || "The landing date is outside the precomputed ephemeris." }]);
    fieldError("date", "e-date", "Outside the ephemeris range (including the delay range).");
    return;
  }
  if (err.status === 422) {
    const detail = Array.isArray(body.detail) ? body.detail : [];
    const locMap = {
      lat: ["lat", "e-lat"], lon: ["lon", "e-lon"], landing_utc: ["date", "e-date"], mission_days: ["days", "e-days"],
      semi_major_m: ["smaj", "e-ellipse"], semi_minor_m: ["smin", "e-ellipse"], azimuth_deg: ["az", "e-ellipse"],
      max_dark_h: ["dark", "e-dark"], max_comm_gap_h: ["gap", "e-gap"], min_earth_pct: ["earth", "e-earth"],
      max_slope_deg: ["slope", "e-slope"], min_sun_margin_deg: ["margin", "e-margin"], risk_margin: ["risk", "e-risk"],
      delay_days_max: ["delay", "e-delay"], observer_height_m: ["height", "e-height"],
    };
    for (const d of detail) {
      const last = (d.loc || []).slice(-1)[0];
      const m = locMap[last];
      if (m) fieldError(m[0], m[1], d.msg || "Invalid value.");
    }
    setNotices([{ kind: "error", title: "Check the settings", text: detail.map((d) => d.msg).filter(Boolean).slice(0, 2).join(" · ") || "Some values were rejected by the API." }]);
    return;
  }
  const text = err.status === 0
    ? `${err.message} Check your connection and try again.`
    : `The API returned an error (${err.status}${body.message ? `: ${body.message}` : ""}).`;
  setNotices([{
    kind: "error", title: "Analysis failed", text,
    actions: [
      { label: "Try again", onClick: () => run() },
      { label: "Load sample result", onClick: () => showSample() },
    ],
  }]);
}

async function showSample(extraNotice) {
  try {
    const data = await loadFixture();
    clearBest(); // best sites are never shown next to sample data
    state.lastRunKey = null;
    state.lastReq = null;
    fillForm(data.inputs);
    render(data);
    if (extraNotice) setNotices([extraNotice]);
  } catch (e) {
    setNotices([{ kind: "error", title: "Offline", text: "The API is unreachable and the sample data could not be loaded." }]);
  }
}

/* ================= render ================= */

function render(resp) {
  state.resp = resp;
  setStale(false);
  const isSample = !!resp.is_sample;
  const inputs = resp.inputs || {};
  const t = resp.target;
  const s = resp.summary;

  // ---- header status ----
  $("sample-badge").hidden = !isSample;
  $("run-status").innerHTML = isSample
    ? '<span class="status-dot status-dot--off" aria-hidden="true"></span>Saved example · not a live run'
    : `<span class="status-dot" aria-hidden="true"></span>Live · last run ${hhmmUtc()}`;

  // ---- map header ----
  const bestRank = isSample ? null : selectedSiteRank();
  const name = siteNameFor(inputs.target?.lat ?? t.lat, inputs.target?.lon ?? t.lon)
    || (bestRank ? `Best site ${bestRank}` : "Custom target");
  $("site-name").textContent = shortName(name);
  $("site-name").title = name;
  const e = inputs.ellipse || {};
  const n = (resp.points || []).length;
  $("map-eyebrow").textContent = `Step 02 · Landing ellipse · ${Math.round(e.semi_major_m * 2).toLocaleString("en-US")} × ${Math.round(e.semi_minor_m * 2).toLocaleString("en-US")} m · ${n} sample points`;
  // The engine samples hourly and echoes the landing time it actually used.
  const asked = state.lastReq?.landing_utc;
  const rounded = !isSample && asked && inputs.landing_utc && Date.parse(asked) !== Date.parse(inputs.landing_utc);
  $("coord-line").textContent = `${fmtLat(t.lat)} · ${fmtLon(t.lon)} · ${fmtUtc(inputs.landing_utc)}${rounded ? ` (entered ${fmtUtc(asked).replace(" UTC", "")}; analysis uses 1 h steps)` : ""}`;
  const vb = resp.map?.view_bounds_xy_m;
  const slopeSrc = t.slope_coarse ? `${t.slope_dem_m ?? 20} m data, may underestimate` : `${t.slope_dem_m ?? 5} m data`;
  $("view-meta").innerHTML = [
    "Polar stereographic view",
    vb ? `${((vb[2] - vb[0]) / 1000).toFixed(1)} × ${((vb[3] - vb[1]) / 1000).toFixed(1)} km window` : "",
    `Target elev ${Math.round(t.elevation_m).toLocaleString("en-US")} m · slope ${t.slope_deg.toFixed(1)}° (${esc(slopeSrc)})`,
  ].filter(Boolean).join("<br>");

  // ---- notices ----
  const notices = [];
  if (isSample) notices.push({ kind: "warn", title: "Sample data", text: "The API is offline, so this is a saved example of a real analysis. It does not reflect your current settings." });
  if (resp.coverage?.message) notices.push({ kind: "warn", title: "Terrain data", text: fixText(resp.coverage.message) });
  setNotices(notices);

  // ---- map ----
  const mapInfo = resp.map || state.meta?.map || {};
  const hsUrl = isSample ? "fixtures/hillshade.png" : apiUrl(mapInfo.hillshade_url || state.meta?.map?.hillshade_url);
  map.setHillshade(hsUrl, mapInfo.hillshade_bounds_xy_m || state.meta?.map?.hillshade_bounds_xy_m);
  ["ov-sky", "ov-north", "ov-scale", "ov-zoom"].forEach((id) => { $(id).hidden = false; });
  $("map-empty").hidden = true;
  const hires = resp.map?.hires_bounds_xy_m ? resp.map : state.meta?.map || {};
  map.setHires(hires.hires_bounds_xy_m, hires.hires_label, hires.coarse_label);
  $("legend-hires").hidden = !hires.hires_bounds_xy_m;
  map.setData(resp);
  renderSky(resp);
  checkRoundTrip(t);

  // ---- survival ----
  renderSurvival(resp);

  // ---- metrics ----
  renderMetrics(resp);

  // ---- delay ----
  renderDelay(resp);

  // ---- recommendations ----
  renderRecs(resp);

  // ---- timeline ----
  if (state.timeline) state.timeline.render(resp);
  $("timeline").hidden = !state.timeline;

  // ---- notes & sources ----
  const warns = (resp.warnings || []).map(fixText);
  $("notes").hidden = !warns.length;
  $("notes-summary").textContent = `Model notes (${warns.length})`;
  $("notes-list").innerHTML = warns.map((w) => `<li>${esc(w)}</li>`).join("");
  const sources = (resp.sources || []).map(fixText);
  $("sources-text").textContent = sources.length ? sources.join(" · ") : "—";

  renderAbout($("about-body"), resp, state.meta);
  markActiveChip();
  if (isSample) clearBest();
  else syncBestSelection();
}

/**
 * The inverse projection used by click-to-pick must map the target's x/y back to its lat/lon within
 * 1e-5°. The API rounds x_m/y_m to 0.1 m, which near the pole is up to ~2e-5° of longitude
 * (0.05 m / 140 km), so that rounding is added to the longitude tolerance.
 */
function checkRoundTrip(t) {
  if (!t || !isFinite(t.x_m) || !isFinite(t.y_m)) return;
  const [lat, lon] = state.proj.toLatLon(t.x_m, t.y_m);
  const rho = Math.hypot(t.x_m - state.proj.x0, t.y_m - state.proj.y0) || 1;
  const xyRoundingDeg = ((0.05 * Math.SQRT2) / rho) * (180 / Math.PI);
  const okLat = Math.abs(lat - t.lat) <= 1e-5;
  const okLon = Math.abs(lon - t.lon) <= 1e-5 + xyRoundingDeg;
  if (!okLat || !okLon) console.warn("LunaScout: map projection round trip off", { lat, lon, target: t });
}

function renderSky(resp) {
  const ts = resp.timeseries;
  if (!ts || !ts.n) { $("ov-sky").hidden = true; return; }
  const north = map.northAngleDeg();
  const sAz = ts.sun_az_deg[0], sEl = ts.sun_el_deg[0];
  const eAz = ts.earth_az_deg[0], eEl = ts.earth_el_deg[0];
  $("sun-arrow").style.transform = `rotate(${sAz + north}deg)`;
  $("earth-arrow").style.transform = `rotate(${eAz + north}deg)`;
  $("north-arrow").style.transform = `rotate(${north}deg)`;
  $("sun-text").textContent = `Sun az ${sAz.toFixed(1)}° · el ${sEl.toFixed(1)}°`;
  $("earth-text").textContent = `Earth az ${eAz.toFixed(1)}° · el ${eEl.toFixed(1)}°`;
}

function renderSurvival(resp) {
  const pts = resp.points || [];
  const c = { viable: 0, risky: 0, not_viable: 0 };
  for (const p of pts) c[p.class] = (c[p.class] || 0) + 1;
  const total = pts.length || 1;
  const prob = c.viable / total;
  // The big number must equal viable ÷ total of the points drawn on the map.
  console.assert(Math.abs(prob - resp.summary.survival_probability) < 0.0015,
    `Survival mismatch: points give ${prob.toFixed(3)}, API summary says ${resp.summary.survival_probability}`);
  if (Math.abs(prob - resp.summary.survival_probability) >= 0.0015) {
    console.warn("LunaScout: survival probability from the drawn points differs from summary.survival_probability", { fromPoints: prob, summary: resp.summary.survival_probability });
  }
  const shown = Math.round(prob * 1000) / 10;
  $("survival-num").innerHTML = `${shown % 1 === 0 ? shown.toFixed(0) : shown.toFixed(1)}<small>%</small>`;

  const v = resp.summary.verdict;
  const vEl = $("verdict");
  vEl.hidden = false;
  vEl.className = `verdict verdict--${v}`;
  vEl.innerHTML = `${ICON[v === "viable" ? "check" : v === "risky" ? "info" : "cross"]}Target ${esc(CLASS_LABEL[v] || v)}`;
  vEl.dataset.tip = "Classification of the exact target point. The survival probability covers the whole ellipse.";
  vEl.tabIndex = 0;

  const w = (k) => `${(c[k] / total) * 100}%`;
  $("dist-bar").innerHTML = ["viable", "risky", "not_viable"]
    .map((k, i) => (c[k] ? `<span class="${["seg-v", "seg-r", "seg-n"][i]}" style="width:${w(k)}"></span>` : "")).join("");
  $("counts").innerHTML = `
    <span class="key">${ICON.viable}${c.viable} viable</span>
    <span class="key">${ICON.risky}${c.risky} risky</span>
    <span class="key">${ICON.not_viable}${c.not_viable} not viable</span>
    <span style="color:var(--muted)">of ${pts.length} sample points</span>`;
  const incl = Math.round(((c.viable + c.risky) / total) * 1000) / 10;
  $("incl-risky").textContent = `Including risky points: ${incl % 1 === 0 ? incl.toFixed(0) : incl.toFixed(1)}%`;
  renderDataRes(pts);
}

/** Badge: which terrain resolution the sample points use (points[].slope_dem_m / slope_coarse). */
function renderDataRes(pts) {
  const el = $("data-res");
  if (!pts.length) { el.hidden = true; return; }
  const px = (p) => p.slope_dem_m ?? (p.slope_coarse ? 20 : 5);
  const coarse = pts.filter((p) => p.slope_coarse ?? px(p) > 5).length;
  const sizes = [...new Set(pts.map(px))].sort((a, b) => a - b).map((v) => `${+v.toFixed(1)}`);
  let text, spoken;
  if (coarse === 0) { text = `${sizes[0]} M · HIGH`; spoken = `${sizes[0]} metre, high`; }
  else if (coarse === pts.length) { text = `${sizes[sizes.length - 1]} M · LOWER`; spoken = `${sizes[sizes.length - 1]} metre, lower`; }
  else { text = `MIXED · ${sizes.join("/")} M`; spoken = `mixed, ${sizes.join(" and ")} metre`; }
  el.hidden = false;
  const badge = $("data-res-text");
  badge.textContent = `DATA RESOLUTION · ${text}`;
  badge.setAttribute("aria-label", `Data resolution: ${spoken}`);
}

function renderMetrics(resp) {
  const ul = $("metrics");
  // delay_tolerance is shown in its own section with the sparkline, so it is not repeated here.
  ul.innerHTML = (resp.target_metrics || []).filter((m) => m.id !== "delay_tolerance").map((m) => {
    const tip = METRIC_TIPS[m.id];
    const badge = m.pass === true
      ? `<span class="badge badge--pass">${ICON.check}PASS</span>`
      : m.pass === false
        ? `<span class="badge badge--fail">${ICON.cross}FAIL</span>`
        : `<span class="badge badge--info">${ICON.info}INFO</span>`;
    const ref = m.limit_display ? fixText(m.limit_display) : "";
    return `<li class="metric">
      <div class="metric-main">
        <span class="metric-label">${esc(fixText(m.label))}${tip ? ` <button type="button" class="info-btn" data-tip="${esc(tip)}" aria-label="About ${esc(m.label)}">i</button>` : ""}</span>
        <span class="metric-value">${esc(fixText(m.display))}</span>
        ${ref ? `<span class="metric-ref">${m.pass !== null && /^[≤≥<>=\d]/.test(ref) ? "Limit " : ""}${esc(ref)}</span>` : ""}
      </div>
      ${badge}
    </li>`;
  }).join("");
  const s = resp.summary;
  $("checks-summary").textContent = `${s.checks_passed} of ${s.checks_total} checks pass against your settings.`;
}

function renderDelay(resp) {
  const curve = resp.delay_curve || [];
  const sec = $("delay");
  if (!curve.length) { sec.hidden = true; return; }
  sec.hidden = false;
  const d = resp.delay_tolerance_days;
  const max = curve[curve.length - 1].delay_days;
  $("delay-val").textContent = d < 0 ? "None" : d >= max ? `≥ ${max} days` : `${d} day${d === 1 ? "" : "s"}`;
  $("delay-val").title = d < 0 ? "The target is not viable even without delay." : "";
  renderSpark($("spark"), curve, d);
}

function renderSpark(svg, curve, tol) {
  const W = 320, H = 72, padL = 30, padR = 6, padT = 6, padB = 18;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const max = curve[curve.length - 1].delay_days || 1;
  const X = (d) => padL + (d / max) * (W - padL - padR);
  const Y = (p) => padT + (1 - p) * (H - padT - padB);
  const line = curve.map((c, i) => `${i ? "L" : "M"}${X(c.delay_days).toFixed(1)} ${Y(c.survival_probability).toFixed(1)}`).join(" ");
  const bad = curve.filter((c) => !c.target_viable);
  const tolX = tol >= 0 ? X(Math.min(tol, max)) : null;
  svg.innerHTML = `
    <line x1="${padL}" y1="${Y(0)}" x2="${W - padR}" y2="${Y(0)}" stroke="#3a3a3f"/>
    <line x1="${padL}" y1="${Y(1)}" x2="${W - padR}" y2="${Y(1)}" stroke="#3a3a3f" stroke-dasharray="2 3"/>
    <text x="${padL - 4}" y="${Y(1) + 4}" fill="#a0a0a8" font-size="11" text-anchor="end">100%</text>
    <text x="${padL - 4}" y="${Y(0) + 4}" fill="#a0a0a8" font-size="11" text-anchor="end">0%</text>
    <text x="${padL}" y="${H - 3}" fill="#a0a0a8" font-size="11">+0 d</text>
    <text x="${W - padR}" y="${H - 3}" fill="#a0a0a8" font-size="11" text-anchor="end">+${max} d delay</text>
    ${tolX !== null ? `<line x1="${tolX}" y1="${padT}" x2="${tolX}" y2="${Y(0)}" stroke="#fff" stroke-dasharray="3 3"/>` : ""}
    <path d="${line}" fill="none" stroke="#fff" stroke-width="1.6" vector-effect="non-scaling-stroke"/>
    ${bad.map((c) => `<path d="M${X(c.delay_days) - 2.5} ${Y(0) - 7.5} l5 5 m0 -5 l-5 5" stroke="#ff6b6b" stroke-width="1.4"/>`).join("")}
  `;
  const tolTxt = tol < 0 ? "not viable at launch" : `viable through day ${tol}`;
  svg.setAttribute("aria-label", `Survival probability over ${max} days of delay; target ${tolTxt}. Red marks are days when the target point is not viable.`);
}

function renderRecs(resp) {
  const sec = $("recs-section");
  sec.hidden = false;
  const box = $("recs");
  const recs = resp.recommendations || [];
  box.innerHTML = "";
  if (!recs.length) {
    const t = resp.inputs?.target || resp.target;
    const o = state.originTarget;
    const away = o && (Math.abs(o.lat - t.lat) > 1e-6 || Math.abs(o.lon - t.lon) > 1e-6);
    const div = document.createElement("div");
    div.className = "rec-empty";
    div.innerHTML = `<div class="label-strong">Best site in range</div><div class="caption">No nearby target with a higher survival probability was found.</div>`;
    if (away) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn btn--sm";
      b.textContent = "Back to original target";
      b.addEventListener("click", () => { $(FIELDS.lat).value = o.lat; $(FIELDS.lon).value = o.lon; run({ fromUser: true }); });
      div.appendChild(b);
    }
    box.appendChild(div);
    return;
  }
  for (const r of recs) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "rec";
    const prob = Math.round(r.survival_probability * 100);
    b.setAttribute("aria-label", `Re-run at ${r.name}, ${prob}% survival probability, ${r.distance_km} km away`);
    b.innerHTML = `
      <span class="rec-prob">${prob}%</span>
      <span class="rec-body">
        <span class="rec-name">${esc(fixText(r.name))}</span>
        <span class="rec-meta">${fmtLat(r.lat)} · ${fmtLon(r.lon)} · ${r.distance_km.toFixed(1)} km away · +${r.delta_pts} pts</span>
      </span>${ICON.arrow}`;
    b.addEventListener("click", () => {
      $(FIELDS.lat).value = r.lat;
      $(FIELDS.lon).value = r.lon;
      run();
    });
    box.appendChild(b);
  }
}

/* ================= best sites ================= */

const NO_SITE_TEXT = "No site meets your limits for this date. Try relaxing the limits or another date.";

const bestRegion = () => document.querySelector("#best-region input:checked")?.value || "all";

/** Request of POST /api/best-sites: the mission settings without the target, plus the region filter. */
function bestPayload(req) {
  return {
    landing_utc: req.landing_utc,
    mission_days: req.mission_days,
    ellipse: req.ellipse,
    limits: req.limits,
    options: { risk_margin: req.options.risk_margin, observer_height_m: req.options.observer_height_m },
    region: bestRegion(),
    max_sites: 5,
  };
}

function updateBestUi() {
  const b = state.best;
  const offline = !state.live || b.offline;
  const btn = $("best-btn");
  btn.disabled = offline || state.running; // never while an analysis runs
  btn.setAttribute("aria-busy", b.loading ? "true" : "false");
  $("best-label").textContent = offline ? "Unavailable offline" : b.loading ? "Scanning region…" : "Find best sites";
  document.querySelectorAll("#best-region input").forEach((i) => { i.disabled = offline; });
  $("run-btn").disabled = b.loading; // and no analysis while a scan runs
  $("best-list").setAttribute("aria-busy", b.loading ? "true" : "false");
  document.querySelectorAll("#best-list .rec").forEach((r) => { r.disabled = b.loading || state.running; });
}

/** The list is stale when the settings (or the region) differ from the request it answers. */
function updateBestStale() {
  const b = state.best;
  const stale = !!b.resp && !b.loading && JSON.stringify(bestPayload(readForm())) !== b.key;
  $("best-stale").hidden = !stale;
  $("best-list").classList.toggle("is-stale", stale);
}

function clearBest() {
  const b = state.best;
  if (b.ctrl) b.ctrl.abort();
  b.ctrl = null; b.loading = false; b.pendingKey = null; b.resp = null; b.key = null;
  map.setHeatmap(null);
  map.setSites([]);
  $("heat-legend").hidden = true;
  $("best-section").hidden = true;
  $("best-list").innerHTML = "";
  $("best-notes").innerHTML = "";
  updateBestUi();
  updateBestStale();
}

function bestMessage(title, text, role = "status") {
  const box = $("best-list");
  box.innerHTML = "";
  const div = document.createElement("div");
  div.className = "rec-empty";
  div.setAttribute("role", role);
  div.innerHTML = `<div class="label-strong">${esc(title)}</div><div class="caption">${esc(text)}</div>`;
  box.appendChild(div);
  $("best-section").hidden = false;
}

async function findBestSites() {
  const b = state.best;
  if (state.running || !state.live || b.offline) return;
  const req = readForm();
  if (!validate(req, { needTarget: false })) return;
  const payload = bestPayload(req);
  const key = JSON.stringify(payload);
  if (b.loading && b.pendingKey === key) return; // this exact request is already in flight
  if (b.ctrl) b.ctrl.abort(); // a new request cancels the one in flight
  const ctrl = new AbortController();
  b.ctrl = ctrl; b.loading = true; b.pendingKey = key;
  if (!b.resp) bestMessage("Scanning the region…", "Evaluating every part of the region for your date and mission settings.");
  $("best-notes").innerHTML = b.resp ? $("best-notes").innerHTML : "";
  updateBestUi();
  updateBestStale();
  try {
    const resp = await bestSites(payload, ctrl.signal);
    if (b.ctrl !== ctrl) return; // superseded while the response was being read
    b.resp = resp; b.key = key; b.offline = false;
    showBest(resp);
  } catch (err) {
    if (err.code === "aborted" || b.ctrl !== ctrl) return;
    handleBestError(err);
  } finally {
    if (b.ctrl === ctrl) {
      b.ctrl = null; b.loading = false; b.pendingKey = null;
      updateBestUi();
      updateBestStale();
    }
  }
}

function handleBestError(err) {
  console.error("Best sites failed", err);
  const b = state.best;
  const body = (err instanceof ApiError && err.body) || {};
  b.resp = null; b.key = null;
  map.setHeatmap(null);
  map.setSites([]);
  $("heat-legend").hidden = true;
  $("best-notes").innerHTML = "";
  if (!(err instanceof ApiError)) {
    bestMessage("Best sites failed", String(err.message || err), "alert");
  } else if (err.status === 0) {
    // API down: say so on the button. Best sites are never faked from the sample fixture.
    b.offline = true;
    bestMessage("Unavailable offline", "The API is unreachable, so best sites cannot be computed. Sample data is never used for this.", "alert");
  } else if (err.status === 404 || err.status === 405) {
    bestMessage("Not available", "This API version does not include the best-sites search yet.", "alert");
  } else if (err.status === 400 && body.error === "out_of_ephemeris_range") {
    fieldError("date", "e-date", "Outside the ephemeris range.");
    bestMessage("Date out of range", fixText(body.message) || "The landing date is outside the precomputed ephemeris.", "alert");
  } else if (err.status === 422) {
    bestMessage("Check the settings", "Some values were rejected by the API.", "alert");
  } else {
    bestMessage("Best sites failed", `The API returned an error (${err.status}${body.message ? `: ${fixText(body.message)}` : ""}).`, "alert");
  }
}

function siteProbText(s) {
  const pct = s.survival_probability * 100;
  if (pct > 0 && pct < 1) return "<1%";
  const r = Math.round(pct);
  return `${r === 100 && s.survival_probability < 1 ? 99 : r}%`;
}

/** Pixel size (m) in a level label such as "LOLA 5 m/px". */
function labelPx(label, fallback) {
  const m = /([\d.]+)\s*m\/px/i.exec(label || "");
  return m ? `${+m[1]}` : fallback;
}

/**
 * Data resolution of a best site by the composition of its whole ellipse (sites[].fine_fraction),
 * not by its center: "5 M · 100%", "20 M · 100%" or "MIXED · 40% 5 M".
 */
function siteRes(s) {
  const mapInfo = state.best.resp?.map || state.meta?.map || {};
  const fine = labelPx(mapInfo.hires_label, "5"), coarse = labelPx(mapInfo.coarse_label, "20");
  const f = s.fine_fraction ?? (s.coarse_fraction != null ? 1 - s.coarse_fraction : null);
  if (f == null) return null;
  const pct = Math.round(f * 100);
  if (pct >= 100) return { text: `${fine} M · 100%`, spoken: `whole ellipse on ${fine} metre data` };
  if (pct <= 0) return { text: `${coarse} M · 100%`, spoken: `whole ellipse on ${coarse} metre data` };
  return { text: `MIXED · ${pct}% ${fine} M`, spoken: `mixed data, ${pct} percent of the ellipse on ${fine} metre data` };
}

/** Great-circle distance on the Moon (R = 1737.4 km), km. */
function distanceKm(lat1, lon1, lat2, lon2) {
  const rad = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * rad) / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
  return 2 * 1737.4 * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Rank of the best site that is the analysed target, or null. */
function selectedSiteRank() {
  const t = state.resp && !state.resp.is_sample ? state.resp.inputs?.target || state.resp.target : null;
  const sites = state.best.resp?.sites || [];
  if (!t) return null;
  const s = sites.find((q) => Math.abs(q.lat - t.lat) < 2e-5 && Math.abs(q.lon - t.lon) < 2e-5);
  return s ? s.rank : null;
}

function syncBestSelection() {
  const resp = state.best.resp;
  if (!resp) return;
  map.setSites(resp.sites || [], selectedSiteRank());
  renderBestList(resp);
}

function showBest(resp) {
  $("best-section").hidden = false;
  $("heat-legend").hidden = false;
  $("heat-toggle").setAttribute("aria-pressed", "true");
  map.setHeatmapVisible(true);
  map.setHeatmap(resp.heatmap);
  syncBestSelection();
  map.fitBounds(resp.heatmap?.bounds_xy_m); // show the whole region; the reset button returns to the ellipse
  if (window.matchMedia("(max-width: 820px)").matches) {
    $("map-frame").scrollIntoView({ behavior: "smooth", block: "start" }); // map + heatmap toggle in view
  }
}

function renderBestList(resp) {
  const box = $("best-list");
  const sites = resp.sites || [];
  const notes = (resp.warnings || []).map(fixText);
  $("best-notes").innerHTML = notes.map((w) => `<li>${esc(w)}</li>`).join("");
  if (!sites.length) {
    // never an empty list without an explanation
    bestMessage("No site found", NO_SITE_TEXT);
    return;
  }
  box.innerHTML = "";
  const selected = selectedSiteRank();
  const t = state.resp && !state.resp.is_sample ? state.resp.target : null;
  const locked = state.best.loading || state.running;
  for (const s of sites) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "rec";
    b.disabled = locked;
    if (s.rank === selected) b.setAttribute("aria-current", "true");
    const prob = siteProbText(s);
    const res = siteRes(s);
    const dist = t ? distanceKm(t.lat, t.lon, s.lat, s.lon) : null;
    const meta = [
      `${fmtLat(s.lat)} · ${fmtLon(s.lon)}`,
      s.rank === selected ? "current target" : dist != null ? `${dist.toFixed(1)} km from target` : "",
      s.matches_full_analysis ? "" : "approximate",
    ].filter(Boolean).join(" · ");
    b.setAttribute("aria-label", `${s.rank === selected ? "Current target, site" : "Analyze site"} ${s.rank}: ${prob.replace("<", "under ")} survival probability${res ? `, ${res.spoken}` : ""}${dist != null && s.rank !== selected ? `, ${dist.toFixed(1)} km from the target` : ""}`);
    b.innerHTML = `
      <span class="rec-prob">${esc(prob)}</span>
      <span class="rec-body">
        <span class="rec-name best-name"><span class="rank-dot" aria-hidden="true">${s.rank}</span><span>${esc(fixText(s.name || `Site ${s.rank}`))}</span>${res ? `<span class="res-badge num">${esc(res.text)}</span>` : ""}</span>
        <span class="rec-meta">${esc(meta)}</span>
      </span>${ICON.arrow}`;
    b.addEventListener("click", () => selectSite(s));
    box.appendChild(b);
  }
}

/** A site (list row or map pin) runs the full analysis there with the current settings. */
function selectSite(s) {
  if (state.running || state.best.loading) return;
  $(FIELDS.lat).value = s.lat;
  $(FIELDS.lon).value = s.lon;
  run({ fromUser: true });
}

function siteTip(s) {
  const res = siteRes(s);
  return `
    <div class="tip-head"><span class="rank-dot" aria-hidden="true">${s.rank}</span>${esc(fixText(s.name || `Site ${s.rank}`))} · ${esc(siteProbText(s))}</div>
    <div class="tip-grid">
      <span>Survival probability</span><span>${esc(siteProbText(s))}</span>
      <span>Including risky points</span><span>${Math.round(s.survival_probability_incl_risky * 100)}%</span>
      ${res ? `<span>Data under the ellipse</span><span>${esc(res.text)}</span>` : ""}
    </div>
    <div class="tip-note">${fmtLat(s.lat)} · ${fmtLon(s.lon)}</div>
    <div class="tip-note">Click for the full analysis. Best sites depend on the date and mission settings.</div>`;
}

/* ================= point tooltip ================= */

function pointTip(p) {
  const resp = state.resp;
  const limits = resp?.inputs?.limits || {};
  const missionH = (resp?.inputs?.mission_days || 0) * 24;
  const failed = p.class === "not_viable";
  const reasons = (p.reasons || []).map((r) => reasonText(r, p, limits, missionH, failed));
  const row = (k, v) => `<span>${k}</span><span>${v}</span>`;
  return `
    <div class="tip-head">${ICON[p.class]}${esc(CLASS_LABEL[p.class] || p.class)}</div>
    ${reasons.length ? `<ul class="tip-reasons">${reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : `<div class="tip-note" style="margin:0 0 8px;color:var(--text-2)">Meets every limit.</div>`}
    <div class="tip-grid">
      ${row("Slope", `${p.slope_deg.toFixed(1)}°${p.slope_coarse ? " *" : ""}`)}
      ${row("Sun at touchdown", p.sun_at_touchdown ? "Yes" : "No")}
      ${row("Sunlight", `${Math.round(p.sun_hours)} h / ${missionH} h`)}
      ${row("Longest dark", fmtHours(p.longest_dark_h))}
      ${row("Earth visible", `${Math.round(p.earth_pct)}%`)}
      ${row("Longest comms gap", fmtHours(p.longest_comm_gap_h))}
      ${row("Until sunset", p.hours_until_sunset >= missionH ? `> ${fmtHours(missionH)}` : fmtHours(p.hours_until_sunset))}
    </div>
    ${p.slope_coarse ? `<div class="tip-note">* Slope from ${p.slope_dem_m ?? 20} m data, may underestimate steepness.</div>` : ""}
    <div class="tip-note">${fmtLat(p.lat)} · ${fmtLon(p.lon)}</div>`;
}

/* ================= map overlays sync ================= */

function syncScale(m) {
  const sb = m.scaleBar();
  if (!sb) return;
  $("scale-bar").style.width = `${sb.px.toFixed(1)}px`;
  $("scale-label").textContent = sb.m >= 1000 ? `${sb.m / 1000} km` : `${sb.m} m`;
}

/* ================= storage ================= */

function saveInputs(req) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(req)); } catch { /* storage blocked */ }
}
function loadInputs() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return null;
    const r = JSON.parse(raw);
    return r && r.target && r.ellipse && r.limits ? r : null;
  } catch { return null; }
}

/* ================= boot ================= */

const map = new MapView({
  frame: $("map-frame"),
  canvas: $("map-canvas"),
  tip: $("map-tip"),
  overlays: [$("ov-sky"), $("ov-north"), $("ov-scale"), $("ov-zoom")],
  onTip: pointTip,
});
map.onViewChange = syncScale;
map.onPickTarget = pickTarget;
map.onPickSite = selectSite;
map.onSiteTip = siteTip;

async function boot() {
  initTooltips($("tooltip"));
  $("about-btn").addEventListener("click", () => $("about").showModal());
  $("about").addEventListener("click", (e) => { if (e.target === $("about")) $("about").close(); });
  $("area-center-btn").addEventListener("click", goToRegionCenter);
  $("zoom-in").addEventListener("click", () => map.zoom(1.25));
  $("zoom-out").addEventListener("click", () => map.zoom(1 / 1.25));
  $("zoom-reset").addEventListener("click", () => map.resetView());
  $("settings").addEventListener("submit", (e) => { e.preventDefault(); run({ fromUser: true }); });
  $("settings").addEventListener("input", updateDirty);
  $("settings").addEventListener("change", updateDirty);
  $("best-btn").addEventListener("click", findBestSites);
  // a new region re-runs the search (cancelling the one in flight) once there is something to update
  $("best-region").addEventListener("change", () => { if (state.best.resp || state.best.loading) findBestSites(); });
  $("heat-toggle").addEventListener("click", () => {
    const on = $("heat-toggle").getAttribute("aria-pressed") !== "true";
    $("heat-toggle").setAttribute("aria-pressed", on ? "true" : "false");
    map.setHeatmapVisible(on);
  });
  updateBestUi(); // "Unavailable offline" until /api/meta answers
  renderAbout($("about-body"), null, null);

  try {
    const { createTimeline } = await import("./timeline.js");
    state.timeline = createTimeline($("timeline-canvas"), $("chart-legend"));
  } catch (e) {
    console.warn("Timeline chart unavailable", e);
  }

  try {
    state.meta = await getMeta();
    state.live = true;
    state.proj = new SouthPolarStereo(state.meta.map?.crs_proj4);
    updateBestUi();
  } catch (err) {
    console.warn("API unreachable, showing sample data", err);
    $("map-empty").textContent = "API offline";
    $("sites-list").parentElement.hidden = true;
    fillForm(FALLBACK_DEFAULTS);
    await showSample();
    return;
  }

  applyInputLimits();
  renderAreaHint();
  renderSites();
  const saved = loadInputs();
  const defaults = { target: { lat: state.meta.curated_sites?.find((s) => s.id === "summit_plateau")?.lat ?? FALLBACK_DEFAULTS.target.lat, lon: state.meta.curated_sites?.find((s) => s.id === "summit_plateau")?.lon ?? FALLBACK_DEFAULTS.target.lon }, ...state.meta.defaults };
  fillForm(saved || defaults);
  if (!validate(readForm())) fillForm(defaults);
  map.setHillshade(apiUrl(state.meta.map.hillshade_url), state.meta.map.hillshade_bounds_xy_m);
  run({ fromUser: true });
}

boot();
