// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// LunaScout single-screen app: settings → /api/analyze → map, results, timeline.

import { getMeta, analyze, loadFixture, apiUrl, ApiError } from "./api.js";
import { MapView } from "./map.js";
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
  set("date", (req.landing_utc || "").slice(0, 16));
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

function readForm() {
  const v = (k) => $(FIELDS[k]).value.trim();
  const num = (k) => (v(k) === "" ? NaN : Number(v(k)));
  const date = v("date");
  const margin = v("margin") === "" ? 0 : Number(v("margin"));
  return {
    target: { lat: num("lat"), lon: num("lon") },
    landing_utc: date ? `${date.slice(0, 16)}:00Z` : "",
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

function clearErrors() {
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

function validate(req) {
  clearErrors();
  const lim = state.meta?.input_limits || {};
  const errs = [];
  const check = (key, errId, value, range, label, { integer = false } = {}) => {
    if (!isFinite(value)) { errs.push([key, errId, `Enter a number for ${label}.`]); return; }
    if (integer && !Number.isInteger(value)) { errs.push([key, errId, `${label} must be a whole number.`]); return; }
    if (range && (value < range[0] || value > range[1])) errs.push([key, errId, `${label} must be between ${range[0]} and ${range[1]}.`]);
  };
  check("lat", "e-lat", req.target.lat, [-90, 90], "Latitude");
  check("lon", "e-lon", req.target.lon, [-180, 180], "Longitude");
  if (!req.landing_utc || isNaN(Date.parse(req.landing_utc))) errs.push(["date", "e-date", "Enter a landing date and time (UTC)."]);
  else if (state.meta?.ephemeris_range_utc) {
    const [a, b] = state.meta.ephemeris_range_utc.map(Date.parse);
    const t = Date.parse(req.landing_utc);
    if (t < a || t > b) errs.push(["date", "e-date", `Ephemeris covers ${state.meta.ephemeris_range_utc[0].slice(0, 10)} to ${state.meta.ephemeris_range_utc[1].slice(0, 10)}.`]);
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
    $(FIELDS.date).min = state.meta.ephemeris_range_utc[0].slice(0, 16);
    $(FIELDS.date).max = state.meta.ephemeris_range_utc[1].slice(0, 16);
  }
}

function updateDirty() {
  const dirty = state.lastRunKey !== null && !state.running && runKey(readForm()) !== state.lastRunKey;
  $("dirty-note").hidden = !dirty;
  markActiveChip();
}

/* ================= curated sites ================= */

function shortName(name) { return name.replace(/\s*\(.*\)\s*$/, ""); }

function renderSites() {
  const list = $("sites-list");
  const sites = state.meta?.curated_sites || [];
  list.innerHTML = "";
  if (!sites.length) { list.parentElement.hidden = true; return; }
  // IM-2 Athena entries first: they are the demo case.
  const ordered = [...sites].sort((a, b) => (/athena/i.test(b.name) ? 1 : 0) - (/athena/i.test(a.name) ? 1 : 0));
  for (const s of ordered) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip" + (/athena/i.test(s.name) ? " chip--key" : "");
    b.textContent = shortName(s.name);
    b.dataset.lat = s.lat;
    b.dataset.lon = s.lon;
    b.setAttribute("aria-pressed", "false");
    b.dataset.tip = `${s.name} · ${fmtLat(s.lat)}, ${fmtLon(s.lon)}. Select to analyze it.`;
    b.addEventListener("click", () => {
      $(FIELDS.lat).value = s.lat;
      $(FIELDS.lon).value = s.lon;
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
  const s = (state.meta?.curated_sites || []).find((c) => Math.abs(c.lat - lat) < 1e-4 && Math.abs(c.lon - lon) < 1e-4);
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
}

async function run({ fromUser = false } = {}) {
  if (state.running) return;
  const req = readForm();
  if (!validate(req)) return;
  if (fromUser || !state.originTarget) state.originTarget = { ...req.target };
  setRunning(true);
  try {
    const resp = await analyze(req);
    state.live = true;
    state.lastRunKey = runKey(req);
    setNotices([]);
    render(resp);
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
    state.lastRunKey = null;
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
  const name = siteNameFor(inputs.target?.lat ?? t.lat, inputs.target?.lon ?? t.lon) || "Custom target";
  $("site-name").textContent = shortName(name);
  $("site-name").title = name;
  const e = inputs.ellipse || {};
  const n = (resp.points || []).length;
  $("map-eyebrow").textContent = `Step 02 · Landing ellipse · ${Math.round(e.semi_major_m * 2).toLocaleString("en-US")} × ${Math.round(e.semi_minor_m * 2).toLocaleString("en-US")} m · ${n} sample points`;
  $("coord-line").textContent = `${fmtLat(t.lat)} · ${fmtLon(t.lon)} · ${fmtUtc(inputs.landing_utc)}`;
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
  map.setData(resp);
  renderSky(resp);
  $("legend-coarse").hidden = !(resp.points || []).some((p) => p.slope_coarse);

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
}

function renderMetrics(resp) {
  const ul = $("metrics");
  ul.innerHTML = (resp.target_metrics || []).map((m) => {
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

async function boot() {
  initTooltips($("tooltip"));
  $("about-btn").addEventListener("click", () => $("about").showModal());
  $("about").addEventListener("click", (e) => { if (e.target === $("about")) $("about").close(); });
  $("zoom-in").addEventListener("click", () => map.zoom(1.25));
  $("zoom-out").addEventListener("click", () => map.zoom(1 / 1.25));
  $("zoom-reset").addEventListener("click", () => map.resetView());
  $("settings").addEventListener("submit", (e) => { e.preventDefault(); run({ fromUser: true }); });
  $("settings").addEventListener("input", updateDirty);
  $("settings").addEventListener("change", updateDirty);
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
  } catch (err) {
    console.warn("API unreachable, showing sample data", err);
    $("map-empty").textContent = "API offline";
    $("sites-list").parentElement.hidden = true;
    fillForm(FALLBACK_DEFAULTS);
    await showSample();
    return;
  }

  applyInputLimits();
  renderSites();
  const saved = loadInputs();
  const defaults = { target: { lat: state.meta.curated_sites?.find((s) => s.id === "summit_plateau")?.lat ?? FALLBACK_DEFAULTS.target.lat, lon: state.meta.curated_sites?.find((s) => s.id === "summit_plateau")?.lon ?? FALLBACK_DEFAULTS.target.lon }, ...state.meta.defaults };
  fillForm(saved || defaults);
  if (!validate(readForm())) fillForm(defaults);
  map.setHillshade(apiUrl(state.meta.map.hillshade_url), state.meta.map.hillshade_bounds_xy_m);
  run({ fromUser: true });
}

boot();
