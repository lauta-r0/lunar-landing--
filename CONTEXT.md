# LunaScout — Project Context (read before doing anything)

Background for every agent working on LunaScout. `CONTRACT.md` defines the interfaces; this file explains the **why**, the decisions already made and the facts already verified, so nobody re-litigates them.

## 1. Event & team
- **NASA Space Apps Challenge 2026**, Nov 14–15, 2026. **Submission deadline: Sunday Nov 15, 23:59 local time** (Uruguay, UTC−3). Resubmitting is allowed; only the last submission counts.
- Team: 4 Systems Engineering students from ORT Uruguay (Montevideo). We build with AI assistance (Claude); each person supervises one agent and must understand its output.
- Challenge: **"Lunar Landing Site Navigator"** (Advanced): https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/
- Judging criteria: **Impact, Creativity, Validity, Relevance, Presentation**. Most of the score comes from the project page; the demo (≤30 s video or ≤7 slides) mainly affects Presentation.

## 2. What the challenge asks (summary)
Build an intuitive tool so mission planners, educators and the public can quickly compare lunar landing sites and dates, visualizing **Sun and Earth positions relative to the horizon** to assess **solar power** and **direct-to-Earth communication**. Focus: the **lunar south pole**. The brief stresses:
- Missions slip (hardware, launch delays), so alternatives must be re-evaluated **fast**.
- Existing tools (Quickmap, Moon Trek, JPL Horizons) are powerful but hard to use for quick scenario comparison.
- Time remaining until sunset/Earthset.
- Real topography (LOLA); no atmosphere (no refraction); libration.
- Steep slopes and deep craters at the south pole; coordinating science and engineering teams; educational value.
- Resources given: JPL Horizons, LROC Quickmap, Moon Trek, CSA Moon Exploration.

## 3. Problems → our idea
Problems the team identified: **sunlight** (power), **temperature** (no sun means about −170 °C; electronics die without heater power), **communication** (direct-to-Earth, or relay), **terrain** (safe touchdown, and it blocks the Sun and Earth), **delays** (any engineering issue shifts the landing date).

**Key insight (the team's choice):** a lander never touches down exactly on its target. Near the south pole the Sun stays only a few degrees above the horizon, so **a few hundred meters can separate sunlight from deadly shadow**. Existing tools and most competitors evaluate a single exact point. LunaScout evaluates the **whole landing ellipse** and answers: *"What is the probability my mission survives where it will actually land?"*

**Our evidence (measured, see `docs/validation.md`):** on the 5 m Mons Mouton terrain, points inside one 1 km-wide landing area range from 0% to 100% of a 7-day mission in sunlight; LunaScout's lit/shadow results agree with LROC QuickMap's independent terrain-shadow model on 95.5–98.0% of ~3,000 points per date (3 dates, kappa 0.90–0.93).

**Real-world motivation and test case (one line, not the centerpiece):** IM-2 "Athena" (March 2025) landed a few hundred meters off target near Mons Mouton, tipped over in a ~20 m crater and lost power (§6). Never present LunaScout as predicting Athena's failure.

## 4. Product scope (MVP, decided)
**One single screen.** No multi-page app, no modes or tabs, nothing Athena-specific hard-coded: users enter any scenario manually (we'll reproduce Athena by typing its data).
- **Left:** settings: target lat/lon, landing date-time (UTC), mission duration, landing ellipse (semi-major, semi-minor, orientation), max darkness (battery h), max comms gap (h), min % time with Earth visible, max slope; Run analysis.
- **Center:** real Moon map (LOLA hillshade) centered on the target; ellipse with points colored **green viable / amber risky / red not viable** (with shapes ● ▲ ✕); target marker; legend. Below it, a **mission timeline chart**: Sun and Earth elevation vs. the terrain horizon over time.
- **Right:** survival probability, metric checks with PASS/FAIL, launch-delay tolerance, recommended nearby targets (click to re-run).
- **About & method** modal: problem, method, data, assumptions, AI-use statement.
- **Live computation:** changing coordinates, date or limits recomputes on the server (FastAPI). Target response < 3 s.

Requirements are tracked in a team spreadsheet (Problems → 26 needs N1–N26 → 46 functional requirements RF01–RF46, with MVP flags). The MVP covers: settings (RF01, RF03–RF08), sunlight (RF10–RF15), comms (RF20–RF23, RF25), terrain + ellipse probability (RF26–RF33), delays (RF36–RF38), viability classification (RF41), reproducing a real mission (RF43).

## 5. Technical decisions (already made, don't change without the team)
| Topic | Decision |
|---|---|
| Stack | Python engine (numpy, scipy, rasterio, pyproj) + FastAPI; frontend in plain HTML/CSS/JS + Chart.js; Canvas map |
| Hosting | Google Cloud Run (min 1 instance, no cold start), Firebase Hosting for the frontend with `/api/**` rewrites to Cloud Run; free custom domain (GoDaddy Registry offer via Porkbun); FortiGuard classification request |
| Region / DEM | **Mons Mouton**: PGDA LOLA 5 m/px **Site20v2** ("Leibnitz beta plateau", 26 x 26 km tile) + LOLA 20 m/px and 40 m/px south polar DEMs (PDS) outside the tile. Analyzable area x 61–85 km, y 106–148 km (lat about −85.97 to −84.37, lon 22.4–38.8 E) |
| Ephemeris | Horizons queried once (2025–2028, hourly) at a reference site, stored as Moon-fixed (ME) unit vectors; per-point az/el computed geometrically. The app never calls Horizons live |
| Horizon | Great-circle ray marching with exact spherical curvature, 1° azimuth bins, rays out to **100 km** (5 m tile, then 20 m / 40 m DEMs); **precomputed grids** every 50 m (5 m tile) and 100 m (area north of it) + on-the-fly for small ellipses and for the target |
| Sun margin | **Real data only** (CONTRACT v1.3): `min_sun_margin_deg` defaults to 0; a margin > 0 is an optional user setting (`low_sun_margin` = risky), never a default adjustment |
| Time step | 1 hour |
| Lit rule | Sun center above the local terrain horizon at the Sun's azimuth; observer 2 m above the ground |
| Probability | Fraction of viable points, assuming a uniform landing distribution inside the ellipse (stated in the UI) |
| Classification | Exact rules in CONTRACT §4.4 (slope, darkness vs. battery, comms gap, Earth %, Sun at touchdown; risky = within the risk margin of a limit; a sunset alone is not a reason since CONTRACT v1.4) |
| Earth metric | **% of mission time with Earth visible** + **longest comms gap**. NOT "hours per day": at the pole, Earth is visible for ~2 weeks, then hidden for ~2 weeks (libration) |
| Colors | Sun yellow `#FFE066`, Earth blue `#8CC4FF`, viable `#3DDC84` ●, risky `#FF9F43` ▲, not viable `#FF6B6B` ✕ |
| Design | Reference mockup in `docs/design/Main.dc.html` (visual reference only; its data and logic are fake) |

## 6. Verified facts (use these; cite the sources)
- **Horizons works for lunar sites** with `CENTER='coord@301'`, `COORD_TYPE='GEODETIC'`, `SITE_COORD='lon,lat,alt_km'` (longitude first), `QUANTITIES='4'`. Header shows `Atmos refraction: NO (AIRLESS)` and `Center pole/equ: MEAN_ME`.
- **Shackleton** (lat −89.67, lon 129.78), 2027-01-01 00:00 UT: Sun az **133.339447°**, el **0.787435°**. In January 2027 at Shackleton (flat horizon): Sun between ~0° and ~1.2°; Earth oscillates between about −7° and +6° (~27-day cycle) and is visible only ~Jan 11–23.
- **Max Sun elevation** at latitude φ ≈ (90 − |φ|) + 1.54° (lunar axial tilt ~1.54°).
- **Athena (IM-2), test case only (details in `docs/validation.md` §3):** touchdown 2025-03-06 17:28 UTC at 84.79059° S, 29.19567° E, on its side in a ~20 m crater; power loss attributed to "orientation and location", mission ended ~12 h later (Hancock et al. 2026, PSJ, doi:10.3847/PSJ/ae732f; crater size: LROC featured image 1408, NASA/GSFC/Arizona State University). The site is outside the 5 m tile; the 20 m DEM there cannot resolve the crater, so LunaScout (like LROC QuickMap) shows it sunlit.
- **JAXA SLIM** (Jan 2024) landed upside down and regained power ~9 days later when the Sun angle changed (Scientific American, Jan 29, 2024). Possible extra replay case.
- **PGDA LOLA DEMs:** 5 m/px GeoTIFFs, south polar stereographic meters, MOON_ME (DE421); per site: `_surf.tif`, `_slp.tif`, `_toterr.tif`, 100 clones. Sites include Connecting Ridge (Site01), Shackleton Rim (Site04), Nobile Rim 1 (Site06), Peak near Shackleton (Site07), de Gerlache Rim (Site11), **Leibnitz beta plateau (Site20)**, Malapert Massif (Site23). Height RMS error ~0.3–0.5 m. https://pgda.gsfc.nasa.gov/products/78

## 7. Known limitations (be honest about them everywhere)
- Horizon modeled out to ~100 km (5 m tile, then 20 m / 40 m LOLA DEMs); terrain farther away is not modeled (a warning says so).
- Terrain is 5 m/px on the Site20v2 tile and 20 m/px outside it (including the IM-2 sites): boulders and craters smaller than the pixel are missed and 20 m slopes underestimate steepness, so tip-over risk is captured only through slope.
- The lander is assumed upright with panels/antenna 2 m above the ground; attitude after touchdown is not modeled.
- Since CONTRACT v1.4 a sunset during the mission no longer makes a point "risky": darkness is judged only by the longest dark run vs. the battery limit (`max_dark_h`), so the survival probability responds to battery size.
- No thermal model (darkness duration is the proxy for cold).
- Uniform landing distribution; 1 h time step; center-of-disk sunlight rule.
- Relay satellites, descent lighting for navigation, launch-window orbital constraints and eclipses are **out of MVP scope** (mention them as future work).

## 8. Space Apps rules that affect everyone
- **All submitted content in English** (the video may be Spanish with English subtitles).
- **Disclose AI use:** header comment in every AI-assisted code file (CONTRACT §7), a "Use of AI" README section, watermarks on AI-generated images/video. AI must not be what came up with the idea; the team owns the concept and must be able to explain everything.
- No NASA logos, insignia or mission patches; no images, video or voice of anyone under 18.
- Use and declare NASA data (Horizons, LOLA/PGDA). List all libraries and sources.
- Public links with no login. Demo ≤ 30 s video or ≤ 7 slides, or the project is not eligible for global judging.
- **Never present sample or made-up data as real.** Sample data is always labeled.

## 9. Where things live
- `CONTRACT.md`: interfaces (binding)
- `CONTEXT.md`: this file
- `docs/design/`: UI mockup (reference)
- `docs/validation.md`, `tests/validation/`: independent validation (QuickMap, Horizons, live API tests)
- `scripts/horizons_test.py`: first working Horizons query + plot (Shackleton, Jan 2027)
- Team prompts for each agent: `../prompts/` (outside the repo)
