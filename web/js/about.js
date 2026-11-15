// Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.

// "About & method" modal content. Warnings and sources come from the API response.

import { esc, fixText } from "./format.js";

const LINKS = [
  ["JPL Horizons System", "https://ssd.jpl.nasa.gov/horizons/"],
  ["LOLA 5 m/px south pole site DEMs (NASA GSFC PGDA)", "https://pgda.gsfc.nasa.gov/products/78"],
  ["LOLA 20/40 m/px south polar DEMs (NASA PDS Geosciences Node)", "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/"],
];

export function renderAbout(el, resp, meta) {
  const warnings = (resp?.warnings || []).map(fixText);
  const sources = (resp?.sources || []).map(fixText);
  const dem = fixText(resp?.coverage?.dem_name || meta?.coverage?.dem_name || "");
  el.innerHTML = `
    <div class="modal-head">
      <div class="section-head">
        <div class="eyebrow">LunaScout</div>
        <h2 class="h2" id="about-title">About &amp; method</h2>
      </div>
      <button type="button" class="btn btn--sm" id="about-close">Close</button>
    </div>

    <section>
      <h3>The problem</h3>
      <p>A lander never touches down exactly on its target. Near the lunar south pole the Sun stays only a few degrees above the horizon, so a few hundred metres can separate sunlight from deadly shadow. On the 5 m Mons Mouton terrain, points inside a single 1 km-wide landing area can range from 0% to 100% of a 7-day mission in sunlight.</p>
      <p style="margin-top:8px">LunaScout evaluates the <strong>whole landing ellipse</strong>, not a single point, and answers: what is the probability my mission survives where it will actually land? Its sunlit/shadow results agree with LROC QuickMap’s independent terrain-shadow model on 95.5–98.0% of about 3,000 test points on each of three dates.</p>
      <p style="margin-top:8px">A real-world reminder: in 2025 IM-2 “Athena” landed a few hundred metres off target near Mons Mouton, tipped over in a crater about 20 m across and lost power (Hancock et al. 2026). Its site is a quick pick here as a test case; it comes out viable because the 20 m terrain data there cannot show that crater and LunaScout assumes an upright lander.</p>
    </section>

    <section>
      <h3>How it works</h3>
      <ol>
        <li><strong>Terrain.</strong> Real LOLA topography around the target (5 m/px near Mons Mouton, 20 and 40 m/px polar DEM beyond it).</li>
        <li><strong>Horizon mask.</strong> For every sample point in the ellipse, the elevation of the terrain horizon in each direction (1° bins), using great-circle ray marching with the Moon’s curvature.</li>
        <li><strong>Sun and Earth.</strong> Positions from JPL Horizons, converted to azimuth and elevation at each point.</li>
        <li><strong>Hourly simulation.</strong> Over the mission, each hour checks whether the Sun’s center and Earth’s center are above the local terrain horizon.</li>
        <li><strong>Classification.</strong> Each point is viable, risky (within the risk margin of a limit: darkness vs. battery, comms gap, slope or Earth time) or not viable (slope, darkness vs. battery, comms gap, Earth time, no Sun at touchdown). Survival probability = viable points ÷ all points.</li>
        <li><strong>Best sites.</strong> Find the best landing areas for your mission across the whole region: the same rules are applied to the precomputed terrain grid every 200 m, giving an approximate map of the survival probability if you aim at each spot. The listed sites are then re-evaluated with the full analysis. They depend on the landing date and your mission settings.</li>
      </ol>
    </section>

    <section>
      <h3>Data</h3>
      <ul>
        ${LINKS.map(([t, u]) => `<li><a href="${u}" target="_blank" rel="noopener">${esc(t)}</a></li>`).join("")}
      </ul>
      ${sources.length ? `<p class="caption" style="margin-top:8px">Sources used in this analysis: ${sources.map(esc).join(" · ")}</p>` : ""}
      ${dem ? `<p class="caption" style="margin-top:4px">Terrain model: ${esc(dem)}</p>` : ""}
    </section>

    <section>
      <h3>Assumptions &amp; limitations</h3>
      <ul>
        <li>The lander is equally likely to land anywhere inside the ellipse.</li>
        <li>Sunlit means the center of the solar disk is above the terrain horizon; 1-hour time step; observer 2 m above the ground by default; no atmosphere, so no refraction.</li>
        <li>Boulders and craters smaller than the DEM pixel are not resolved: tip-over risk is captured only through slope. Slopes from 20 m data can underestimate local steepness.</li>
        <li>The lander is assumed upright after touchdown, with panels and antenna 2 m above the ground; its attitude (for example after tipping over) and panel orientation are not modeled.</li>
        <li>No thermal model: the longest darkness period is the proxy for cold.</li>
        <li>Relay satellites, descent lighting and launch-window orbital constraints are out of scope.</li>
        ${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}
      </ul>
    </section>

    <section>
      <h3>Use of AI</h3>
      <p>The team defined the problem, the requirements and the design decisions, and reviewed all results. Claude (Anthropic) assisted with the code, the documentation and the validation (tests and the comparisons with JPL Horizons and LROC QuickMap). Every AI-assisted code file says so in a header comment.</p>
    </section>

    <section>
      <p class="caption">LunaScout — NASA Space Apps Challenge 2026 · Lunar Landing Site Navigator challenge. Not for operational mission use.</p>
    </section>
  `;
  const close = el.querySelector("#about-close");
  close.addEventListener("click", () => el.closest("dialog").close());
}
