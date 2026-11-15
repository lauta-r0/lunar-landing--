// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// Mission timeline (Chart.js): Sun and Earth elevation vs. the terrain horizon at the target point.

const SUN = "#FFE066";
const EARTH = "#FFFFFF";
const HORIZON_FILL = "rgba(160,160,168,0.30)";
const HORIZON_LINE = "#8c8c94";
const GRID = "rgba(255,255,255,0.08)";
const MUTED = "#a0a0a8";

function hatch(ctx) {
  const c = document.createElement("canvas");
  c.width = 8; c.height = 8;
  const g = c.getContext("2d");
  g.strokeStyle = "rgba(255,255,255,0.16)";
  g.lineWidth = 1;
  g.beginPath(); g.moveTo(0, 8); g.lineTo(8, 0); g.moveTo(-2, 2); g.lineTo(2, -2); g.moveTo(6, 10); g.lineTo(10, 6); g.stroke();
  return ctx.createPattern(c, "repeat");
}

/** Contiguous runs of hours where test(i) is true → [[start, end), ...]. */
function runs(n, test) {
  const out = [];
  let s = null;
  for (let i = 0; i < n; i++) {
    if (test(i)) { if (s === null) s = i; }
    else if (s !== null) { out.push([s, i]); s = null; }
  }
  if (s !== null) out.push([s, n]);
  return out;
}

const bandsPlugin = {
  id: "lsBands",
  beforeDatasetsDraw(chart) {
    const meta = chart.$ls;
    if (!meta) return;
    const { ctx, chartArea: a, scales: { x } } = chart;
    ctx.save();
    // mission window
    ctx.fillStyle = "rgba(255,255,255,0.025)";
    ctx.fillRect(x.getPixelForValue(0), a.top, x.getPixelForValue(meta.n) - x.getPixelForValue(0), a.bottom - a.top);
    // Sun blocked → hatched bands
    if (!chart.$hatch) chart.$hatch = hatch(ctx);
    ctx.fillStyle = chart.$hatch;
    for (const [s, e] of meta.dark) {
      const x0 = x.getPixelForValue(s), x1 = x.getPixelForValue(e);
      ctx.fillRect(x0, a.top, x1 - x0, a.bottom - a.top);
    }
    // Earth hidden → strip along the top
    ctx.fillStyle = "rgba(255,255,255,0.55)";
    for (const [s, e] of meta.noEarth) {
      const x0 = x.getPixelForValue(s), x1 = x.getPixelForValue(e);
      for (let px = x0; px < x1; px += 6) ctx.fillRect(px, a.top, Math.min(3, x1 - px), 4);
    }
    ctx.restore();
  },
  afterDatasetsDraw(chart) {
    const meta = chart.$ls;
    if (!meta) return;
    const { ctx, chartArea: a, scales: { x } } = chart;
    ctx.save();
    ctx.font = "600 11px Barlow, Arial, sans-serif";
    ctx.textBaseline = "top";
    // touchdown marker
    const x0 = Math.round(x.getPixelForValue(0)) + 0.5;
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x0, a.top); ctx.lineTo(x0, a.bottom); ctx.stroke();
    label(ctx, "TOUCHDOWN", x0 + 6, a.top + 8);
    // first sunset
    if (meta.sunset != null) {
      const xs = Math.round(x.getPixelForValue(meta.sunset)) + 0.5;
      ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(xs, a.top); ctx.lineTo(xs, a.bottom); ctx.stroke();
      ctx.setLineDash([]);
      const txt = `SUNSET +${meta.sunset} H`;
      const w = ctx.measureText(txt).width;
      label(ctx, txt, xs + 6 + w > a.right ? xs - w - 6 : xs + 6, a.top + 24);
    }
    ctx.restore();
  },
};

function label(ctx, txt, x, y) {
  const w = ctx.measureText(txt).width;
  ctx.fillStyle = "rgba(0,0,0,0.85)";
  ctx.fillRect(x - 3, y - 2, w + 6, 16);
  ctx.fillStyle = "#fff";
  ctx.fillText(txt, x, y);
}

const LEGEND = [
  ['<svg width="22" height="10" aria-hidden="true"><path d="M1 5h20" stroke="#FFE066" stroke-width="2.5"/></svg>', "Sun elevation"],
  ['<svg width="22" height="10" aria-hidden="true"><path d="M1 5h20" stroke="#fff" stroke-width="1.6" stroke-dasharray="5 3"/></svg>', "Earth elevation"],
  ['<svg width="22" height="12" aria-hidden="true"><rect x="1" y="3" width="20" height="8" fill="rgba(160,160,168,0.4)"/><path d="M1 3h20" stroke="#8c8c94"/></svg>', "Terrain horizon toward Sun"],
  ['<svg width="22" height="10" aria-hidden="true"><path d="M1 5h20" stroke="#a0a0a8" stroke-width="1.2" stroke-dasharray="1.5 2.5"/></svg>', "Terrain horizon toward Earth"],
  ['<svg width="22" height="12" aria-hidden="true"><defs><pattern id="lgh" width="5" height="5" patternUnits="userSpaceOnUse"><path d="M0 5L5 0" stroke="rgba(255,255,255,0.5)"/></pattern></defs><rect x="1" y="1" width="20" height="10" fill="url(#lgh)" stroke="#3a3a3f"/></svg>', "Sun blocked"],
  ['<svg width="22" height="10" aria-hidden="true"><path d="M1 3h20" stroke="rgba(255,255,255,0.7)" stroke-width="4" stroke-dasharray="3 3"/></svg>', "Earth hidden"],
];

export function createTimeline(canvas, legendEl) {
  const Chart = window.Chart;
  if (!Chart) throw new Error("Chart.js not loaded");
  legendEl.innerHTML = LEGEND.map(([ico, t]) => `<span class="legend-item">${ico}<span>${t}</span></span>`).join("");

  Chart.defaults.font.family = "Barlow, Arial, sans-serif";
  Chart.defaults.color = MUTED;

  let chart = null;
  let t0 = null;

  const render = (resp) => {
    const ts = resp.timeseries;
    if (!ts || !ts.n) return;
    t0 = Date.parse(ts.t0_utc);
    const step = ts.step_h || 1;
    const pts = (arr) => arr.map((y, i) => ({ x: i * step, y }));
    const n = ts.n * step;
    const dark = runs(ts.n, (i) => !ts.sun_lit[i]).map(([s, e]) => [s * step, e * step]);
    const noEarth = runs(ts.n, (i) => !ts.earth_visible[i]).map(([s, e]) => [s * step, e * step]);
    const firstDark = ts.sun_lit[0] ? ts.sun_lit.findIndex((v) => !v) : -1;
    const sunset = firstDark > 0 ? firstDark * step : null;

    const all = [...ts.sun_el_deg, ...ts.earth_el_deg, ...ts.horizon_at_sun_deg, ...ts.horizon_at_earth_deg];
    const yMin = Math.floor(Math.min(...all) - 0.5);
    const yMax = Math.ceil(Math.max(...all) + 1.5);

    const datasets = [
      { label: "Terrain horizon toward Sun", data: pts(ts.horizon_at_sun_deg), borderColor: HORIZON_LINE, backgroundColor: HORIZON_FILL, borderWidth: 1, fill: "start", order: 4 },
      { label: "Terrain horizon toward Earth", data: pts(ts.horizon_at_earth_deg), borderColor: MUTED, borderDash: [1.5, 2.5], borderWidth: 1.2, fill: false, order: 3 },
      { label: "Earth elevation", data: pts(ts.earth_el_deg), borderColor: EARTH, borderDash: [6, 4], borderWidth: 1.6, fill: false, order: 2 },
      { label: "Sun elevation", data: pts(ts.sun_el_deg), borderColor: SUN, borderWidth: 2.5, fill: false, order: 1 },
    ];

    if (chart) {
      chart.data.datasets = datasets;
      chart.options.scales.x.max = n;
      chart.options.scales.y.min = yMin;
      chart.options.scales.y.max = yMax;
      chart.$ls = { n, dark, noEarth, sunset };
      chart.update("none");
    } else {
      chart = new Chart(canvas, {
        type: "line",
        data: { datasets },
        plugins: [bandsPlugin],
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          parsing: false,
          normalized: true,
          elements: { point: { radius: 0, hoverRadius: 3 }, line: { tension: 0 } },
          interaction: { mode: "index", intersect: false, axis: "x" },
          layout: { padding: { top: 4, right: 8 } },
          scales: {
            x: {
              type: "linear", min: 0, max: n,
              grid: { color: GRID }, border: { color: "#3a3a3f" },
              ticks: { stepSize: 24, color: MUTED, font: { size: 11 }, callback: (v) => (v % 24 === 0 ? `+${v / 24} d` : "") },
              title: { display: true, text: "DAYS SINCE TOUCHDOWN", color: MUTED, font: { size: 11, weight: 600 } },
            },
            y: {
              min: yMin, max: yMax,
              grid: { color: GRID }, border: { color: "#3a3a3f" },
              ticks: { color: MUTED, font: { size: 11 }, callback: (v) => `${v}°` },
              title: { display: true, text: "ELEVATION", color: MUTED, font: { size: 11, weight: 600 } },
            },
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: "#0a0a0a", borderColor: "#ffffff", borderWidth: 1, cornerRadius: 4,
              titleColor: "#fff", bodyColor: "#f0f0fa", padding: 10, boxPadding: 4,
              titleFont: { size: 12, weight: 700 }, bodyFont: { size: 12 },
              callbacks: {
                title: (items) => {
                  const h = items[0].parsed.x;
                  const d = new Date(t0 + h * 3600e3).toISOString().slice(0, 16).replace("T", " ");
                  return `+${h} h · ${d} UTC`;
                },
                label: (item) => ` ${item.dataset.label}: ${item.parsed.y.toFixed(2)}°`,
              },
            },
          },
        },
      });
      chart.$ls = { n, dark, noEarth, sunset };
      chart.update("none");
    }

    const darkH = dark.reduce((s, [a, b]) => s + (b - a), 0);
    const hiddenH = noEarth.reduce((s, [a, b]) => s + (b - a), 0);
    const cap = document.getElementById("timeline-caption");
    if (cap) {
      const base = "The Sun barely rises here: a small hill can block it. When the yellow line drops into the grey terrain area, the lander is in shadow.";
      const detail = darkH === 0
        ? " At this target the Sun clears the terrain for the whole mission."
        : ` At this target the Sun is blocked for ${darkH} h of ${n} h.`;
      const earth = hiddenH === 0 ? " Earth stays in view throughout." : ` Earth is hidden for ${hiddenH} h.`;
      cap.textContent = base + detail + earth;
    }
    canvas.setAttribute("aria-label", `Mission timeline over ${n} hours. Sun blocked ${darkH} h, Earth hidden ${hiddenH} h.`);
  };

  return { render };
}
