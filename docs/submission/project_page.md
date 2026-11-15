<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. (Delete this line when pasting into the form.) -->
# LunaScout — Space Apps project page (paste-ready)

Challenge: **Lunar Landing Site Navigator** · Team: **CD Band** · Members: Lautaro Montes, Agustin Guerequiz, Francisco Castelli, Sebastián Luciardi (Systems Engineering, ORT Uruguay)

Every field of the project form is below. Text inside a code block is what to paste. Items marked `[TO VERIFY]` must be confirmed by the team before the final submission.

---

## 1. Project Name

```
LunaScout
```

---

## 2. High-Level Project Summary  (≈190 words)

```
A lander never touches down exactly on its target. Near the lunar south pole the Sun stays only a few degrees above the horizon, so a few hundred metres can separate sunlight from shadow. LunaScout is a single-screen web app that evaluates the whole landing ellipse instead of one point.

The user enters a target, a landing date, a mission length, a landing ellipse and the lander's limits (battery, comms gap, slope). For every sample point in the ellipse, LunaScout computes the terrain horizon from real LRO LOLA topography and the Sun and Earth positions from JPL Horizons, simulates the mission hour by hour, and classifies the point as viable, risky or not viable. It returns a survival probability, the number of days a launch can slip before the target stops being viable, and better targets nearby.

This answers the challenge's call for a fast, intuitive way to compare sites and dates, so a schedule slip can be re-evaluated in seconds. Planners get a shared view for science and engineering; educators and the public see why the south pole is hard. LunaScout's sunlit/shadow results agree with LROC QuickMap's independent model on 95–98% of about 3,000 test points per date.
```

---

## 3. Link to Project Demo

```
[DEMO LINK — paste the public video (YouTube/Drive, no login) or slide-deck link here. Video ≤ 30 s, or ≤ 7 slides including the title slide.]
```

---

## 4. Link to Final Project

```
App (live, no login): https://lunascout.web.app
Source code (public):  https://github.com/lauta-r0/lunar-landing--
```

`[TO VERIFY]` — if the free custom domain is set up before submitting, add it as the first line (and request the FortiGuard classification, see `checklist.md`). Open all links in a private window first.

---

## 5. Detailed Project Description  (≈850 words)

```
THE PROBLEM
Missions to the lunar south pole depend on two things that the terrain controls: sunlight for power and a line of sight to Earth for communication. Near the pole the Sun circles the horizon, never rising more than a few degrees, so a hill or a crater rim decides whether a solar array is lit. Schedules also slip, and every slip changes the Sun and Earth geometry. Tools such as LROC Quickmap, Moon Trek and JPL Horizons are powerful, but comparing scenarios quickly with them is hard.

A lander also does not land exactly where it is aimed: it lands somewhere inside a landing ellipse. In March 2025 the IM-2 "Athena" lander touched down a few hundred metres from its target, tipped over in a crater about 20 m across and could not generate enough power; the mission ended about 12–13 hours later. Near the pole, where you land decides whether your panels see the Sun. Evaluating only the target point hides that.

WHAT LUNASCOUT DOES
LunaScout is a single-screen web app. You enter a target (latitude/longitude), a landing date and time (UTC), a mission length, a landing ellipse (semi-axes and orientation) and the lander's limits: longest darkness the battery survives, longest comms gap, minimum share of time with Earth in view, and maximum slope. LunaScout then answers one question: what is the probability that the mission survives where it will actually land?

The map shows the ellipse covered with sample points, green (viable), amber (risky) or red (not viable), also marked with different shapes so colour is not the only cue. The right panel shows the survival probability, a pass/fail check for each limit, the launch-delay tolerance and recommended nearby targets that re-run with one click. "Find best sites" ranks the best aim points region-wide on an approximate heatmap. A timeline shows the Sun's and Earth's elevation against the terrain horizon hour by hour.

HOW IT WORKS (5 STEPS)
1. Terrain. Real LRO LOLA topography around the target: 5 m/px near Mons Mouton (NASA GSFC PGDA), and 20 m and 40 m/px south-polar elevation models farther out.
2. Horizon mask. For every sample point in the ellipse, we compute how high the terrain rises in each direction (1° steps) by marching rays across the surface, including the curvature of the Moon, out to about 100 km.
3. Sun and Earth. Positions come from JPL Horizons (hourly, 2025–2028) and converted to azimuth and elevation at each point (no atmosphere, so no refraction).
4. Hourly simulation. For each hour of the mission we check whether the centre of the Sun and the centre of the Earth are above that point's terrain horizon.
5. Classification. A point is not viable if it breaks a limit (slope, darkness longer than the battery, comms gap, too little Earth time, or no Sun at touchdown), risky if it is within a risk margin of a limit, and viable otherwise. The survival probability is the share of viable points, assuming the lander is equally likely to land anywhere inside the ellipse. The analysis is repeated for each possible launch delay (delay tolerance) and for nearby sites (better targets).

BENEFITS
- Fast re-evaluation when schedules slip: a typical analysis takes well under a second of server time, so planners can test dates, limits and sites interactively.
- Planning for where the lander will land, not where it is aimed: results cover the whole ellipse, and the app flags better targets nearby and region-wide.
- A shared view for science and engineering teams: one screen shows terrain, Sun, Earth and limits in plain language.
- Educational value: the map and timeline show why a few degrees of Sun elevation and a few hundred metres matter at the pole.

EVIDENCE
Inside a single 1 km-wide landing area on the 5 m Mons Mouton terrain, sample points range from 0% to 100% of a 7-day mission in sunlight. We compared LunaScout's sunlit/shadow result with LROC QuickMap's independent terrain-shadow model on three dates (about 3,000 points each): agreement was 95.5–98.0% (Cohen's kappa 0.90–0.93). Sun and Earth directions match direct JPL Horizons queries to within 0.002° at our sites. The full validation report is in the repository (docs/validation.md).

LIMITS WE STATE OPENLY
Coverage today is one region around Mons Mouton (about 24 × 42 km). Terrain is 5 m/px only on the 5 m tile and 20 m/px elsewhere, so boulders and craters smaller than a pixel (such as Athena's ~20 m crater) are not resolved. The lander is assumed upright with panels 2 m above ground; its attitude is not modelled. No thermal model (darkness duration is the proxy for cold); relay satellites and descent constraints are out of scope. LunaScout is a planning aid, not an operational tool.

WHAT WE HOPE TO ACHIEVE
We want planners, students and the public to ask the right question: not "is my target sunlit?" but "how likely is my mission to survive where it will actually land, and is that robust to a delay?" Next: more south-pole regions, relay-satellite visibility and a thermal model.

TOOLS, LANGUAGES AND SOFTWARE
Python (NumPy, SciPy, rasterio, pyproj, Pillow) for the engine; FastAPI and Uvicorn for the API; plain HTML, CSS and JavaScript with Chart.js for the interface; pytest for tests. Hosted on Google Cloud Run (API) and Firebase Hosting (web app). Data: NASA JPL Horizons and LRO LOLA; LROC QuickMap for validation. Font: Barlow (Google Fonts).
```

`[TO VERIFY]` Final tool list (Claude confirmed from `engine/requirements.txt`, `api/requirements.txt`, `web/index.html`, `api/DEPLOY.md`). "Well under a second of server time": our own live check on 15 Nov 2026 gave 240–440 ms of server compute for six uncached default requests with recommendations; re-run before submitting.

---

## 6. Use of Super Intelligence (SI)

```
We used Claude (Anthropic) as a coding and writing assistant to accelerate implementation and documentation. The team came up with the idea and defined the problem, the requirements and the design decisions (evaluating the whole landing ellipse and the classification rules). Claude helped write the code, the tests, the validation scripts and the documentation, including this project page. Every AI-assisted code file starts with a header comment saying so, and the repository README has a "Use of AI" section. Team members reviewed and integrated all AI-assisted work, and the results were cross-checked against external references: direct JPL Horizons queries and LROC QuickMap's independent terrain-shadow model. No AI-generated images, video or voices are used in our materials. [TO VERIFY by the team]
```

> **Team: adjust this to what actually happened.** The guide says AI must not be used to come up with the idea, and judges can see AI-use indicators. Two points where this text deliberately differs from the draft in the brief:
> 1. The brief's draft says "validation … done by the team". `docs/validation.md` and the repo README say the validation scripts and comparisons were produced **with AI assistance** and reviewed by the team, so the text above follows the repo.
> 2. It says this page itself was AI-assisted. Delete that if it is not true.
> The last sentence ("No AI-generated images…") is true only if the demo and slides contain none; if you add any, they need a visible watermark (see `checklist.md`).

---

## 7. NASA Data

```
1) JPL Horizons System (NASA JPL Solar System Dynamics Group) — https://ssd.jpl.nasa.gov/horizons/
   Used for the positions of the Sun and the Earth. We queried the Horizons API once for hourly values from 2025-01-01 to 2028-12-31 (topocentric, lunar surface site, Moon Mean-Earth/polar-axis frame, no atmospheric refraction) and stored them as unit vectors. The app computes azimuth and elevation at each point from these vectors and never calls Horizons live. We checked the result against direct Horizons queries at several sites and dates: differences ≤ 0.0013° (Sun and Earth, DEM centre and IM-2 site).

2) LRO LOLA 5 m/px south-pole site DEMs — NASA GSFC Planetary Geodesy Data Archive (PGDA), https://pgda.gsfc.nasa.gov/products/78
   Barker, M. K., et al. (2021), Planetary and Space Science 203, 105119, doi:10.1016/j.pss.2020.105119.
   Site20v2 ("Leibnitz beta plateau", Mons Mouton), 26 × 26 km. Used for heights and slopes and for the high-resolution horizon around the target. Hillshade for the map is derived from it.

3) LRO LOLA 20 m/px and 40 m/px south-polar gridded DEMs (LRO-L-LOLA-4-GDR-V1.0, v2.0) — NASA PDS Geosciences Node (Smith et al. 2017)
   https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/
   Used for terrain outside the 5 m tile (including the IM-2 sites) and for the far-field horizon, out to about 100 km.

4) LROC Quickmap (LROC team, Arizona State University / NASA) — https://quickmap.lroc.asu.edu/ (now redirects to https://quickmap.lroc.im-ldi.com)
   Used only for validation. We compared our sunlit/shadow results with its "Terrain Shadows @UTC (80S, 20 mpp)" layer on three dates (agreement 95.5–98.0%, kappa 0.90–0.93) and compared the subsolar point with its SPICE-based value (≤ 0.001°). QuickMap is not a data input to the app.

5) LROC featured images (NASA/GSFC/Arizona State University) — https://lroc.im-ldi.com/images/1401 and /1408
   Used as sources for the IM-2 "Athena" intended site and the ~20 m crater in which it came to rest.

Moon Trek (NASA JPL): not used. [TO VERIFY]
```

---

## 8. Space Agency Partner Data and Other References

```
SPACE AGENCY PARTNER DATA
- CSA Moon Exploration (Canadian Space Agency) — context only: it informed our understanding of the challenge (south-pole exploration, lighting and communication constraints). No CSA data is used in the app. [TO VERIFY link used by the team]
- JAXA / ISRO: no data used.

SCIENTIFIC AND NEWS REFERENCES
- Barker, M. K., et al. (2021). Improved LOLA elevation maps for south pole landing sites: Error estimates and their impact on illumination conditions. Planetary and Space Science 203, 105119. doi:10.1016/j.pss.2020.105119 [TO VERIFY title against the DOI page]
- Smith, D. E., et al. (2017). Summary of the results from the Lunar Orbiter Laser Altimeter after seven years in lunar orbit. Icarus 283, 70–91. [TO VERIFY]
- Hancock et al. (2026). PRIME-1 payload operations summary from the IM-2 mission. The Planetary Science Journal 7. doi:10.3847/PSJ/ae732f — touchdown coordinates and time, "orientation and location" power loss.
- LROC "IM-2 Athena Seen Obliquely" (NAC M1495922531LR, NASA/GSFC/Arizona State University) — https://lroc.im-ldi.com/images/1408
- LROC "IM-2 Landing Region" — https://lroc.im-ldi.com/images/1401
- SpacePolicyOnline, "IM-2 mission ends one day after lunar landing" — https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/
- Space.com report on the IM-2 touchdown time (cited in docs/athena_replay.md). [TO VERIFY URL]

SOFTWARE LIBRARIES (versions pinned in the repository)
- NumPy 2.5.4 (BSD-3-Clause) · SciPy 1.18.1 (BSD-3-Clause) · rasterio 1.5.2 (BSD-3-Clause) · pyproj 3.8.0 (MIT) · Pillow 13.0.0 (MIT-CMU / HPND) · tqdm 4.70.1 (MPL-2.0 and MIT)
- FastAPI 0.163.0 (MIT) · Uvicorn 0.54.0 (BSD-3-Clause) · Pydantic ≥ 2 (MIT)
- pytest 9.2.0 (MIT) · httpx (BSD-3-Clause)
- Chart.js 4.4.1 (MIT), loaded from the jsDelivr CDN
[TO VERIFY] licences against each package's metadata before submitting (for example with pip-licenses).

FONTS
- Barlow and Barlow Semi Condensed (Jeremy Tribby), served by Google Fonts, SIL Open Font License 1.1.

PLATFORMS
- Google Cloud Run and Firebase Hosting (hosting). GitHub (source).

IMAGES
- All screenshots are of the LunaScout app itself. No NASA logos, insignia or mission patches are used. No AI-generated images.
  [TO VERIFY] If any LROC image is added to the video or slides, credit it as "NASA/GSFC/Arizona State University".
```
