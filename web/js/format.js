// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// Formatting helpers and plain-language text.

export const COLORS = {
  viable: "#3DDC84",
  risky: "#FF9F43",
  not_viable: "#FF6B6B",
  sun: "#FFE066",
  earth: "#FFFFFF",
};

export const CLASS_LABEL = { viable: "Viable", risky: "Risky", not_viable: "Not viable" };

// Some API strings arrive double-encoded (UTF-8 read as Windows-1252). Repair the common cases.
const MOJIBAKE = [
  ["â€”", "—"], ["â€“", "–"], ["â€™", "’"], ["â€œ", "“"], ["â€\u009d", "”"],
  ["Â°", "°"], ["Â·", "·"], ["â‰¤", "≤"], ["â‰¥", "≥"], ["Ã—", "×"], ["Â ", " "],
];
export function fixText(s) {
  if (typeof s !== "string") return s;
  if (!/[âÂÃ]/.test(s)) return s;
  let out = s;
  for (const [bad, good] of MOJIBAKE) out = out.split(bad).join(good);
  return out;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const fmtLat = (v) => `${Math.abs(v).toFixed(3)}° ${v < 0 ? "S" : "N"}`;
export const fmtLon = (v) => `${Math.abs(v).toFixed(3)}° ${v < 0 ? "W" : "E"}`;

export function fmtHours(h) {
  if (h == null || !isFinite(h)) return "—";
  const d = Math.floor(h / 24);
  const r = Math.round(h - d * 24);
  return d > 0 ? `${d} d ${r} h` : `${Math.round(h)} h`;
}

export const pct = (p, digits = 0) => (p == null ? "—" : (p * 100).toFixed(digits));

/** "2027-10-12T14:00:00Z" → "2027-10-12 14:00 UTC" */
export function fmtUtc(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

export function hhmmUtc(date = new Date()) {
  return date.toISOString().slice(11, 16) + " UTC";
}

const n1 = (v) => (v == null ? "—" : (Math.round(v * 10) / 10).toString());

/**
 * Plain-language explanation of each reason code for one point.
 * `failed` = true for not_viable points (limit broken), false for risky (close to the limit).
 */
export function reasonText(code, p, limits, missionH, failed) {
  const L = limits || {};
  switch (code) {
    case "slope":
      return failed
        ? `Too steep (${n1(p.slope_deg)}° > ${n1(L.max_slope_deg)}°)`
        : `Steep, close to the limit (${n1(p.slope_deg)}° of ${n1(L.max_slope_deg)}°)`;
    case "darkness":
      return failed
        ? `Dark for ${n1(p.longest_dark_h)} h, battery lasts ${n1(L.max_dark_h)} h`
        : `Dark for ${n1(p.longest_dark_h)} h, close to the ${n1(L.max_dark_h)} h battery`;
    case "comms_gap":
      return failed
        ? `No Earth contact for ${n1(p.longest_comm_gap_h)} h (limit ${n1(L.max_comm_gap_h)} h)`
        : `Comms gap of ${n1(p.longest_comm_gap_h)} h, close to the ${n1(L.max_comm_gap_h)} h limit`;
    case "earth_time":
      return failed
        ? `Earth visible ${n1(p.earth_pct)}% of the mission (min ${n1(L.min_earth_pct)}%)`
        : `Earth visible ${n1(p.earth_pct)}% of the mission, close to the ${n1(L.min_earth_pct)}% minimum`;
    case "sunset":
      return `Sunset during the mission (after ${fmtHours(p.hours_until_sunset)})`;
    case "no_sun_at_touchdown":
      return "No sunlight at touchdown";
    case "low_sun_margin":
      return `Sun clearance below the ${n1(L.min_sun_margin_deg)}° margin you set (not a computed shadow)`;
    default:
      return code;
  }
}

/** Plain-language tooltips for the metric ids in CONTRACT §4.3. */
export const METRIC_TIPS = {
  sun_at_touchdown: "Whether the Sun is above the local terrain horizon at the moment of landing. A solar-powered lander needs light right away.",
  sun_hours: "Total hours with the Sun above the terrain horizon during the mission.",
  longest_dark: "The longest stretch without sunlight. Solar-powered landers must survive it on batteries, and without sunlight it gets extremely cold.",
  min_sun_margin: "How far the Sun's center stays above the terrain horizon during the lit hours. Small values mean a tiny hill could block it.",
  earth_pct: "Share of the mission with Earth above the terrain horizon, so the lander can talk to Earth directly. At the pole Earth is visible for about two weeks, then hidden for about two weeks.",
  longest_comm_gap: "The longest stretch without a direct line of sight to Earth.",
  hours_until_sunset: "Time from touchdown until the Sun first drops behind the terrain.",
  hours_until_earthset: "Time from touchdown until Earth first drops behind the terrain.",
  area_over_slope: "Share of the landing ellipse steeper than your maximum safe slope. Steep ground can tip a lander over.",
  delay_tolerance: "How many days the landing can slip while the target point stays viable.",
};
