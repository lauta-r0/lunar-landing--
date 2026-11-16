# LunaScout — Shared Contract (v1.6)

> **Changes in v1.6 (2026-11-15, team decision: best sites)** — `schema_version` is now `"1.6"`. Additive only; no existing endpoint or field changes.
> - New endpoint `POST /api/best-sites` (section 4.7): scans the whole analyzable area for the requested date and mission and returns an approximate heatmap of "survival probability if you aim here" plus the best aim points. Its request is the analyze request without `target`, plus `region` (`"all" | "5m" | "20m"`) and `max_sites`.
> - Data resolution is judged on the whole ellipse, not on its center: `region` `"5m"` (the default) / `"20m"` keep an aim point only if at least 95% of its ellipse is on that data; `"all"` keeps every aim point. Sites are always ranked by their real survival probability, with no adjustment for the data resolution (ties: the larger share of the ellipse on 5 m data). Sites carry `fine_fraction` and `coarse_fraction`.
> - Slopes are no longer blended across the 5 m / 20 m seam: every point takes the slope raster of one DEM, and `slope_dem_m` / `slope_coarse` name that DEM. This changes the slope of points within 500 m inside the tile edge (they were a 5 m / 20 m mix labelled 5 m); heights are still blended for the horizon. No field changes.
> - New engine function `engine.best_sites.best_sites(request)` (section 5).
> - `GET /api/health` and every response report `"1.6"`.
>

> **Changes in v1.5 (2026-11-15, owner decision: map UX)** — `schema_version` is now `"1.5"`. Additive only; no existing field changes.
> - `GET /api/meta` → `map` and `POST /api/analyze` → `map` gain `hires_bounds_xy_m` (`[x_min, y_min, x_max, y_max]`, extent of the 5 m/px Site20v2 tile, same polar stereographic meters as the other bounds), `hires_label` (`"LOLA 5 m/px"`) and `coarse_label` (`"LOLA 20 m/px"`; `null` only when no coarser level is loaded). The frontend draws this footprint on the map and shows a data-resolution badge.
> - `GET /api/health` and every response report `"1.5"`.
>

> **Changes in v1.4 (2026-11-15, team decision: classification rule, validation finding P1)** — `schema_version` is now `"1.4"`.
> - A sunset during the mission no longer makes a point risky by itself. Darkness is judged only by `longest_dark_h` against `limits.max_dark_h`: not_viable above the limit, risky within `risk_margin` of it. The risky reason `sunset` is removed (it is never emitted); `hours_until_sunset` stays as a metric, now informative.
> - Consequence: `survival_probability` now responds to `limits.max_dark_h` on missions that include a sunset (before, any sunset made the point risky at every battery size).
> - Target metric `hours_until_sunset` has `pass: null` and `limit_display: "Reference"`, so `checks_total` is **6** by default (7 when a Sun margin > 0 is set).
> - `GET /api/health` and every response report `"1.4"`. The API compresses responses over 1 KB with gzip when the client accepts it (no schema change).
>

> **Changes in v1.3 (2026-11-14, team decision: real data only)** — `schema_version` is now `"1.3"`.
> - `min_sun_margin_deg` default is 0 (real data only); the margin is an optional user setting. `null` or absent = 0. `get_meta().defaults.limits.min_sun_margin_deg` is `0` and `min_sun_margin_auto_deg` is removed.
> - `low_sun_margin` now means "Sun clearance below the margin set by the user" and appears only when the user sets a margin > 0.
> - Target metric `min_sun_margin` stays as an informative metric (real clearance); with margin 0 its `pass` is `null`, so `checks_total` is 7 by default (8 when a margin > 0 is set). `timeseries.sun_margin_deg` is unchanged.
>
> **Changes in v1.2 (2026-11-14, terrain engine / Agent 03)** — `schema_version` was `"1.2"`.
> - New limit `limits.min_sun_margin_deg` ("Required Sun clearance", degrees, optional, `null` by default). `null` = automatic per point: **0° on the 5 m/px tile**, **2.86° = atan(1 m / 20 m) on the coarse 20 m/px DEM** (heuristic for unresolved sub-pixel relief). A number overrides it everywhere. `get_meta().defaults.min_sun_margin_auto_deg` gives the automatic values (`{"5": 0.0, "20": 2.862}`).
> - New risky reason `low_sun_margin`: "Sun clearance below the terrain-data uncertainty margin (coarse DEM)". It means the data are too coarse to guarantee sunlight, not a computed shadow. It never makes a point not_viable.
> - New target metric `min_sun_margin` ("Minimum Sun clearance", unit `°`, pass if ≥ the required clearance); `checks_total` is now 8.
> - New field `timeseries.sun_margin_deg` (length `n`): Sun elevation minus the terrain horizon at the Sun's azimuth, degrees (negative = Sun hidden).
> - Default `landing_utc` is now **`2027-10-12T14:00:00Z`** (2027-03-10 is a dark period at Mons Mouton: every point was not viable).
>

> **Changes in v1.1 (2026-11-14, terrain engine / Agent 03)** — `schema_version` was `"1.1"`.
> - New field `timeseries.sun_visible_fraction`: array of length `n`, values 0–1 (fraction of the solar disk above the terrain horizon, for display; classification still uses the center-of-disk rule).
> - New optional fields: `points[].slope_dem_m` and `target.slope_dem_m` (pixel size of the DEM the slope comes from: 5 or 20), `points[].slope_coarse` and `target.slope_coarse` (true when the slope comes from the coarser 20 m/px DEM, which underestimates local steepness). `coverage.message` is a string when the target is outside the 5 m/px tile.
> - Terrain: the 5 m/px Site20v2 tile plus the LOLA 20/40 m/px south polar DEM (PDS) outside it and for the far-field horizon (out to 100 km). Analyzable area: x 61–85 km, y 106–148 km (lat ≈ −86.0 to −84.6), which includes the IM-2 Athena sites.
> - The example target (−84.6, 31.2) was outside coverage; the examples now use the summit plateau (−85.47628, 31.39691).
> - `get_meta().curated_sites` can include the IM-2 Athena intended site and actual touchdown.

This file is the single source of truth that connects all parts of LunaScout. Every agent must follow it exactly. If a change is unavoidable, bump `schema_version`, update this file, and tell the whole team.

## 1. Product in one paragraph
LunaScout is a single-screen web app for the lunar south pole. A lander never touches down exactly on its target, so the user enters a target, a landing date, a mission duration, a landing ellipse and mission limits. The backend evaluates every sample point inside the ellipse using **real LOLA topography** (horizon mask + slope) and **real JPL Horizons ephemerides** (Sun and Earth positions). It returns each point as viable / risky / not viable, a survival probability, target-point metrics, a time series of Sun/Earth elevation vs. the local horizon, a launch-delay tolerance curve, and better nearby targets.

## 2. Conventions (non-negotiable)
| Topic | Convention |
|---|---|
| Latitude | Degrees, south negative (`-85.47`) |
| Longitude | Degrees **east-positive**, range [-180, 180] |
| Time | UTC, ISO 8601 with `Z` (`2027-10-12T14:00:00Z`). Internal sampling step: **1 hour** |
| Azimuth | Degrees, **clockwise from local north**, [0, 360) |
| Elevation | Degrees above the local horizontal plane (plane perpendicular to the local radius of the reference sphere) |
| Distances / heights | Meters. Heights are relative to the **1,737,400 m reference sphere** (LOLA convention) |
| Map coordinates | South polar stereographic, meters, read from the DEM GeoTIFF's own CRS (spherical Moon, R = 1,737,400 m). Named `x_m`, `y_m` |
| Body-fixed frame | Moon **Mean Earth / polar axis (ME)** frame, which both Horizons topocentric output and the PGDA DEMs use |
| Moon radius | `R_MOON = 1737400.0` m |
| "Sun lit" | Sun center elevation > local terrain horizon elevation at the Sun's azimuth. Also compute `sun_visible_fraction` of the solar disk (angular radius 0.2665°) for display, but classification uses the center rule |
| "Earth visible" | Earth center elevation > local terrain horizon elevation at Earth's azimuth |
| Observer height | Default 2.0 m above the terrain (solar array / antenna height) |
| Rounding in JSON | Angles 3 decimals, hours 1 decimal, probabilities 3 decimals (0–1), coordinates 5 decimals |

## 3. Data sources
- **JPL Horizons API** — `https://ssd.jpl.nasa.gov/api/horizons.api`. Topocentric az/el from a lunar site works with: `CENTER='coord@301'`, `COORD_TYPE='GEODETIC'`, `SITE_COORD='<lon_east>,<lat>,<alt_km>'` (**longitude first**), `QUANTITIES='4'`, `EPHEM_TYPE='OBSERVER'`, targets `'10'` (Sun) and `'399'` (Earth). The output header states `Atmos refraction: NO (AIRLESS)` and `Center pole/equ: MEAN_ME`.
  - Verified example: Shackleton (lat -89.67, lon 129.78), `2027-01-01 00:00 UT` → Sun az 133.339447°, el 0.787435°.
- **LOLA 5 m/px south pole site DEMs** (Barker et al. 2021, NASA GSFC PGDA): `https://pgda.gsfc.nasa.gov/products/78`, data in `https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/`. Per site: `*_surf.tif` (height, m), `*_slp.tif` (slope, °), `*_toterr.tif` (height RMS error, m), `Clones/` (100 DEM realizations). GeoTIFFs in south polar stereographic meters. **Primary site: Site20 "Leibnitz beta plateau" = Mons Mouton** (use `Site20v2` if available). Citation: Barker, M. K., et al. (2021), *Planetary and Space Science* 203, 105119, doi:10.1016/j.pss.2020.105119.
- **LOLA 20 m/px and 40 m/px south polar gridded DEMs** (since v1.1): `LDEM_80S_20M`, `LDEM_80S_40M`, data set `LRO-L-LOLA-4-GDR-V1.0` v2.0, NASA PDS Geosciences Node, `https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/`. Same projection, frame and height reference as the 5 m tiles. Used outside the 5 m tile and for the far-field horizon. Citation: Smith, D. E., et al. (2017), *Icarus* 283, 70–91, doi:10.1016/j.icarus.2016.06.006.

## 4. API

Base path: `/api`. JSON only. CORS enabled for the frontend origin(s) and `http://localhost:*`.

### 4.1 `GET /api/health`
`200 {"status":"ok","engine_ready":true,"schema_version":"1.6"}`

### 4.2 `GET /api/meta`
Lets the frontend set defaults, limits and the map.
```json
{
  "schema_version": "1.6",
  "coverage": {
    "dem_name": "LOLA 5 m/px LDEM — Site20v2 (Mons Mouton / Leibnitz beta plateau) + LOLA 20 m/px polar LDEM (...) + LOLA 40 m/px polar LDEM (...)",
    "bounds_xy_m": [-0.0, -0.0, 0.0, 0.0],
    "center_lat": 0.0,
    "center_lon": 0.0,
    "approx_bounds_latlon": {"lat_min": 0.0, "lat_max": 0.0, "lon_min": 0.0, "lon_max": 0.0}
  },
  "ephemeris_range_utc": ["2025-01-01T00:00:00Z", "2028-12-31T23:00:00Z"],
  "map": {
    "hillshade_url": "/api/static/hillshade.png",
    "hillshade_bounds_xy_m": [0.0, 0.0, 0.0, 0.0],
    "crs_proj4": "+proj=stere +lat_0=-90 ... +R=1737400 +units=m",
    "hires_bounds_xy_m": [0.0, 0.0, 0.0, 0.0],
    "hires_label": "LOLA 5 m/px",
    "coarse_label": "LOLA 20 m/px"
  },
  "curated_sites": [
    {"id": "mons_mouton_center", "name": "Mons Mouton (DEM center)", "lat": 0.0, "lon": 0.0},
    {"id": "im2_athena_intended", "name": "IM-2 Athena intended site", "lat": -84.78, "lon": 29.13},
    {"id": "im2_athena_actual", "name": "IM-2 Athena actual touchdown", "lat": -84.7906, "lon": 29.1957}
  ],
  "defaults": {
    "landing_utc": "2027-10-12T14:00:00Z",
    "mission_days": 7,
    "ellipse": {"semi_major_m": 1000, "semi_minor_m": 600, "azimuth_deg": 0},
    "limits": {"max_dark_h": 50, "max_comm_gap_h": 72, "min_earth_pct": 50, "max_slope_deg": 8, "min_sun_margin_deg": 0},
    "options": {"risk_margin": 0.2, "delay_days_max": 30, "include_recommendations": true, "observer_height_m": 2.0}
  },
  "input_limits": {
    "mission_days": [1, 30], "semi_major_m": [50, 5000], "semi_minor_m": [50, 5000],
    "max_dark_h": [1, 400], "max_comm_gap_h": [1, 400], "min_earth_pct": [0, 100], "max_slope_deg": [1, 30],
    "delay_days_max": [0, 60], "min_sun_margin_deg": [0, 15]
  }
}
```
(Values shown as `0.0` are filled from the real DEM.)

### 4.3 `POST /api/analyze`
**Request**
```json
{
  "target": {"lat": -85.47628, "lon": 31.39691},
  "landing_utc": "2027-10-12T14:00:00Z",
  "mission_days": 7,
  "ellipse": {"semi_major_m": 1000, "semi_minor_m": 600, "azimuth_deg": 0},
  "limits": {"max_dark_h": 50, "max_comm_gap_h": 72, "min_earth_pct": 50, "max_slope_deg": 8, "min_sun_margin_deg": 0},
  "options": {"risk_margin": 0.2, "delay_days_max": 30, "include_recommendations": true, "observer_height_m": 2.0}
}
```
- `ellipse.azimuth_deg`: direction of the semi-major axis, clockwise from local north at the target.
- `limits.max_dark_h`: longest continuous period without sunlight the lander survives (battery).
- `limits.max_comm_gap_h`: longest continuous period without direct-to-Earth visibility tolerated.
- `limits.min_earth_pct`: minimum % of mission hours with Earth visible.
- `limits.min_sun_margin_deg` (optional, v1.3): required Sun clearance above the terrain horizon during the lit hours of the mission. `null`, omitted or `0` = no margin (real data only, the default); a number > 0 applies to every point and can make points risky (`low_sun_margin`).
- `options.risk_margin`: fraction of a limit that counts as "close to failing" (0.2 = within 20% of a limit → risky).
- `options` may be omitted (defaults apply).

**Response 200**
```json
{
  "schema_version": "1.6",
  "is_sample": false,
  "computed_utc": "2026-11-15T14:03:22Z",
  "compute_ms": 1840,
  "inputs": { "...": "echo of the normalized request" },
  "coverage": {"in_coverage": true, "dem_name": "LOLA 5 m/px LDEM — Site20v2 (...) + LOLA 20/40 m/px polar LDEM", "message": null},

  "target": {"lat": -85.47628, "lon": 31.39691, "x_m": 0.0, "y_m": 0.0, "elevation_m": 0.0, "slope_deg": 3.1,
             "slope_dem_m": 5.0, "slope_coarse": false},

  "summary": {
    "n_points": 118,
    "viable": 64, "risky": 34, "not_viable": 20,
    "survival_probability": 0.542,
    "survival_probability_incl_risky": 0.831,
    "checks_passed": 5, "checks_total": 6,
    "verdict": "risky"
  },

  "target_metrics": [
    {"id": "sun_at_touchdown",   "label": "Sun at touchdown",          "value": 1,     "unit": "bool", "display": "Yes · el 1.4°", "limit_display": "Required",                 "pass": true},
    {"id": "sun_hours",          "label": "Hours of sunlight",         "value": 121.0, "unit": "h",    "display": "121 h / 168 h", "limit_display": "≥ 60% of mission",         "pass": true},
    {"id": "longest_dark",       "label": "Longest darkness period",   "value": 41.0,  "unit": "h",    "display": "41 h",          "limit_display": "≤ 50 h (battery)",         "pass": true},
    {"id": "min_sun_margin",     "label": "Minimum Sun clearance",     "value": 2.9,   "unit": "°",    "display": "2.9°",          "limit_display": "Reference", "pass": null},
    {"id": "earth_pct",          "label": "Mission time with Earth visible", "value": 58.0, "unit": "%", "display": "58%",        "limit_display": "≥ 50%",                    "pass": true},
    {"id": "longest_comm_gap",   "label": "Longest comms gap",         "value": 96.0,  "unit": "h",    "display": "4 d 0 h",       "limit_display": "≤ 72 h",                   "pass": false},
    {"id": "hours_until_sunset", "label": "Time until sunset",         "value": 78.0,  "unit": "h",    "display": "3 d 6 h",       "limit_display": "Reference",                "pass": null},
    {"id": "hours_until_earthset","label": "Time until Earthset",      "value": 30.0,  "unit": "h",    "display": "1 d 6 h",       "limit_display": "Reference",                "pass": null},
    {"id": "area_over_slope",    "label": "Ellipse area over max slope","value": 6.0,  "unit": "%",    "display": "6% > 8°",       "limit_display": "≤ 20% of ellipse",         "pass": true},
    {"id": "delay_tolerance",    "label": "Launch-delay tolerance",    "value": 9,     "unit": "days", "display": "9 days",        "limit_display": "Days the target stays viable", "pass": null}
  ],

  "points": [
    {
      "id": 0, "x_m": 0.0, "y_m": 0.0, "lat": -85.47628, "lon": 31.39691,
      "class": "viable",
      "reasons": [],
      "slope_deg": 3.2, "slope_dem_m": 5.0, "slope_coarse": false,
      "sun_hours": 130.0, "longest_dark_h": 12.0,
      "earth_pct": 60.0, "longest_comm_gap_h": 40.0,
      "hours_until_sunset": 168.0, "sun_at_touchdown": true
    }
  ],

  "timeseries": {
    "t0_utc": "2027-10-12T14:00:00Z",
    "step_h": 1,
    "n": 168,
    "sun_az_deg": [], "sun_el_deg": [], "horizon_at_sun_deg": [], "sun_lit": [],
    "earth_az_deg": [], "earth_el_deg": [], "horizon_at_earth_deg": [], "earth_visible": [],
    "sun_visible_fraction": [], "sun_margin_deg": []
  },

  "horizon_profile": {"az_step_deg": 1.0, "elevation_deg": []},

  "delay_curve": [{"delay_days": 0, "survival_probability": 0.542, "target_viable": true}],
  "delay_tolerance_days": 9,

  "recommendations": [
    {"name": "1.0 km N of target", "lat": -85.4433, "lon": 31.39691, "distance_km": 1.0, "survival_probability": 0.84, "delta_pts": 30}
  ],

  "map": {
    "hillshade_url": "/api/static/hillshade.png",
    "hillshade_bounds_xy_m": [0.0, 0.0, 0.0, 0.0],
    "view_bounds_xy_m": [0.0, 0.0, 0.0, 0.0],
    "ellipse_polygon_xy_m": [[0.0, 0.0]],
    "hires_bounds_xy_m": [0.0, 0.0, 0.0, 0.0],
    "hires_label": "LOLA 5 m/px",
    "coarse_label": "LOLA 20 m/px"
  },

  "warnings": ["Horizon is modeled out to 100–101 km from the target: LOLA 5 m/px tile nearby, LOLA 20 m and 40 m/px polar DEM beyond it. Terrain farther than 100 km is not modeled."],
  "sources": [
    "JPL Horizons System (Solar System Dynamics Group, NASA JPL) — Sun and Earth topocentric positions",
    "LRO LOLA 5 m/px LDEM, Site20 (Barker et al. 2021, NASA GSFC PGDA)",
    "LRO LOLA 20 m/px and 40 m/px south polar LDEM (LRO-L-LOLA-4-GDR-V1.0, product v2.0, NASA PDS Geosciences Node; Smith et al. 2017)"
  ]
}
```

Field rules:
- `points[].class` ∈ `"viable" | "risky" | "not_viable"`.
- `points[].reasons` ⊆ `["slope", "darkness", "comms_gap", "earth_time", "no_sun_at_touchdown", "low_sun_margin"]` (v1.4: `sunset` removed). It lists the criteria that failed (not_viable) or are within the risk margin (risky).
- `summary.verdict` ∈ `"viable" | "risky" | "not_viable"`. It is the target point's class.
- `target_metrics[].pass` is `true`, `false` or `null` (informational). `checks_passed` and `checks_total` count only non-null metrics.
- `timeseries` arrays all have length `n` = `mission_days * 24`, for the **target point**. `sun_lit` and `earth_visible` are 0/1 integers. `sun_visible_fraction` (v1.1) is a float 0–1 per hour (display only). `sun_margin_deg` (v1.2) is the Sun elevation minus the horizon at the Sun's azimuth, degrees.
- `low_sun_margin` (v1.3) appears only when the user sets `limits.min_sun_margin_deg` > 0; explain it in the UI as "Sun clearance below the margin set by the user" (not a computed shadow).
- `points[].slope_coarse` / `target.slope_coarse` (v1.1): `true` when the slope comes from the 20 m/px DEM (outside the 5 m tile); the UI should mark such slopes as "coarse, may underestimate steepness". `slope_dem_m` is the source pixel size (5 or 20).
- `coverage.message` (v1.1): `null`, or a note such as "Target is outside the LOLA 5 m/px tile; terrain from the 20 m/px LOLA polar DEM."
- `horizon_profile.elevation_deg` has `360 / az_step_deg` values for the target point, starting at az 0.
- `delay_curve` has one entry per day from 0 to `delay_days_max`. The landing time shifts by that many days and everything is recomputed. `delay_tolerance_days` = the largest d such that the target stays viable (class viable or risky) for every delay 0..d. If the target is already not viable at 0 days, it is -1.
- `recommendations`: up to 3, only those with `survival_probability` greater than the current one, sorted descending. Empty list if none.
- `map.view_bounds_xy_m`: suggested view window (target-centered, ≥ 5 km wide, aspect 3:2).
- `map.hires_bounds_xy_m` (v1.5, also in `GET /api/meta` → `map`): extent of the 5 m/px tile. Points inside it have `slope_dem_m` 5; outside it the terrain comes from the 20 m/px DEM. `hires_label` / `coarse_label` name the two levels for the map legend.

### 4.4 Classification rules (engine must implement exactly)
For each point, with mission window `[landing, landing + mission_days)` sampled hourly:
- **not_viable** if any of:
  - `slope_deg > max_slope_deg` → `slope`
  - `longest_dark_h > max_dark_h` → `darkness` (a dark run that starts at touchdown counts)
  - `longest_comm_gap_h > max_comm_gap_h` → `comms_gap`
  - `earth_pct < min_earth_pct` → `earth_time`
  - Sun not lit at the touchdown hour → `no_sun_at_touchdown`
- **risky** if it is not not_viable and any of:
  - `slope_deg > (1 - risk_margin) * max_slope_deg`
  - `longest_dark_h > (1 - risk_margin) * max_dark_h`
  - `longest_comm_gap_h > (1 - risk_margin) * max_comm_gap_h`
  - `earth_pct < min_earth_pct * (1 + risk_margin)` (clipped at 100)
  - (v1.2) during the lit hours of the mission, min(`sun_el − horizon_at_sun`) < required Sun clearance (`limits.min_sun_margin_deg`; only when > 0) → `low_sun_margin`
- **viable** otherwise.
- (v1.4) A sunset during the mission does **not** make a point risky by itself. A point that sees a sunset but whose longest dark run fits the battery (`longest_dark_h` ≤ `(1 - risk_margin) * max_dark_h`) is viable. `hours_until_sunset` is reported for information only.
- `survival_probability = viable / n_points`. `survival_probability_incl_risky = (viable + risky) / n_points`. **Assumption to state in the UI: landing is uniformly distributed inside the ellipse.**

### 4.5 Errors
| Status | Body | When |
|---|---|---|
| 400 | `{"error":"out_of_coverage","message":"Target is outside the analyzable area of the DEM. The loaded DEM is … Try a point near lat …, lon …","suggested_target":{"lat":…,"lon":…}}` | Target or most of the ellipse outside the DEM |
| 400 | `{"error":"out_of_ephemeris_range","message":"…"}` | Landing date (plus delay range) outside the precomputed ephemeris |
| 422 | FastAPI validation error | Bad or out-of-range inputs |
| 500 | `{"error":"internal","message":"…"}` | Bug |

### 4.6 Performance
`POST /api/analyze` must answer in **< 3 s** for the default request on the deployed server (2 vCPU) with recommendations on, and in **< 1.5 s** without recommendations. Identical requests are cached.

### 4.7 `POST /api/best-sites` (v1.6)
Region-wide scan: where should the mission aim on this date with these settings? It runs in the threadpool like analyze; the engine runs one scan at a time. Identical requests are cached. Target: < 3 s on the deployed server for the default request.

**Request** — the analyze request (4.3) without `target`; every field is optional (defaults of 4.2):
```json
{
  "landing_utc": "2027-10-12T14:00:00Z",
  "mission_days": 7,
  "ellipse": {"semi_major_m": 1000, "semi_minor_m": 600, "azimuth_deg": 0},
  "limits": {"max_dark_h": 50, "max_comm_gap_h": 72, "min_earth_pct": 50, "max_slope_deg": 8, "min_sun_margin_deg": 0},
  "options": {"risk_margin": 0.2, "observer_height_m": 2.0},
  "region": "5m",
  "max_sites": 5
}
```
- `region`: which aim points are considered, judged on the **whole ellipse** (not on its center). `"5m"` (default, the most reliable data): at least 95% of the ellipse on the LOLA 5 m/px tile. `"20m"`: at least 95% of the ellipse on the 20 m/px DEM outside the tile. `"all"`: every aim point in the analyzable area; it includes 20 m terrain, which can hide small craters and slopes (the UI must say so). The ranking is the same for every `region`: real survival probability only.
- `max_sites`: 1–10, default 5.
- `options.delay_days_max` and `options.include_recommendations` are accepted and ignored. A `target` is rejected (422).

**Response 200**
```json
{
  "schema_version": "1.6",
  "is_sample": false,
  "computed_utc": "2026-11-15T18:03:22Z",
  "compute_ms": 440,
  "inputs": { "...": "echo of the normalized request, including region and max_sites" },
  "heatmap": {
    "encoding": "uint8-base64",
    "width": 121, "height": 211,
    "cell_m": 200.0,
    "bounds_xy_m": [60900.0, 105900.0, 85100.0, 148100.0],
    "value_max": 254, "invalid_value": 255,
    "approximate": true,
    "data_b64": "…"
  },
  "summary": {"n_cells": 13921, "n_cells_above_zero": 6239, "best_heatmap_probability": 0.787,
              "n_nodes": 15121, "n_nodes_simulated": 2987, "n_nodes_viable": 1522},
  "sites": [
    {"rank": 1, "name": "Site 1", "lat": -85.1436, "lon": 32.69785, "x_m": 0.0, "y_m": 0.0,
     "survival_probability": 0.795, "survival_probability_incl_risky": 0.93, "n_points": 371,
     "data_resolution_m": [5.0], "fine_fraction": 1.0, "coarse_fraction": 0.0,
     "matches_full_analysis": true, "heatmap_probability": 0.787}
  ],
  "map": {"hillshade_url": "/api/static/hillshade.png", "hillshade_bounds_xy_m": [0.0, 0.0, 0.0, 0.0],
          "hires_bounds_xy_m": [0.0, 0.0, 0.0, 0.0], "hires_label": "LOLA 5 m/px", "coarse_label": "LOLA 20 m/px"},
  "warnings": ["Approximate heatmap: the precomputed horizon grid is sampled every 200 m; …"],
  "sources": ["…"]
}
```
Field rules:
- `heatmap.data_b64`: base64 of `width * height` bytes, row-major, **row 0 = north edge** (`y_max`), column 0 = `x_min`. Byte `v` in 0–254 is the probability `v / 254`; `255` = invalid cell (outside the analyzable area, excluded by `region`, or less than 80% of the ellipse inside the area). `bounds_xy_m` are the outer edges of the cells, in the map coordinates of section 2. The whole response stays under 300 KB before gzip.
- A cell's probability is the share of viable horizon-grid nodes (classified exactly as in 4.4, sampled every `cell_m`) inside the request's ellipse centered on that cell. **It is approximate** (`approximate` is always `true`): the UI must label it "Approximate (coarse sampling); click a site for the full analysis".
- `sites`: up to `max_sites` aim points, at least 1.5 km (or 2 × semi-major, if larger) apart, sorted by `survival_probability` descending, `rank` from 1. Equal probabilities are ordered by the larger `fine_fraction`. The probability is real data only: nothing is added or subtracted for the data resolution. Only sites with `survival_probability` > 0.
- `sites[].fine_fraction` / `coarse_fraction`: share of the ellipse area on the 5 m/px tile / on the 20 m/px DEM (they add up to 1). The UI labels a site by this composition ("5 M · 100%", "20 M · 100%", "MIXED · 40% 5 M"), not by its center. With `region` `"5m"` every site has `fine_fraction` ≥ 0.95; with `"20m"`, `coarse_fraction` ≥ 0.95.
- **An empty list means no site meets the limits for this date**; the UI must say so and never show an empty list without an explanation.
- `sites[].survival_probability`, `survival_probability_incl_risky` and `n_points` come from the same sampling as `POST /api/analyze` for that target, so with `matches_full_analysis: true` they equal the `summary` of the full analysis. `matches_full_analysis` is `false` for ellipses too small for the precomputed grid (analyze then computes horizons on the fly) or when `options.observer_height_m` differs from the grid's (2 m).
- `sites[].data_resolution_m`: DEM pixel sizes behind the site's sample points (`[5.0]`, `[20.0]` or `[5.0, 20.0]`).
- `sites[].heatmap_probability`: the coarse heatmap value at the site (it may differ slightly from `survival_probability`).
- Results depend on the landing date and the mission settings; the UI must say so.
- Errors: as 4.5 (`out_of_ephemeris_range`, `invalid_request`, 422), plus `400 {"error":"best_sites_unavailable","message":"…"}` when the precomputed horizon grid is not loaded.

## 5. Python engine interface (shared by 02, 03, 04)
```python
# engine/ephemeris.py   (owner: 02)
def load_ephemeris(path="data/ephemeris/sun_earth_vectors.npz") -> "Ephemeris": ...
class Ephemeris:
    t_unix: "np.ndarray[int64]"        # hourly UTC timestamps
    sun_vec: "np.ndarray[float64]"      # (N, 3) unit vectors, Moon ME frame
    earth_vec: "np.ndarray[float64]"    # (N, 3) unit vectors, Moon ME frame
    def window(self, start_utc: "datetime", hours: int) -> tuple["np.ndarray", "np.ndarray", "np.ndarray"]: ...  # (t, sun_vec, earth_vec)
def local_az_el(vecs: "np.ndarray", lat_deg: "np.ndarray", lon_deg: "np.ndarray") -> tuple["np.ndarray", "np.ndarray"]:
    """vecs (T,3); lat/lon (P,) → az, el arrays of shape (P, T) in degrees."""

# engine/analyze.py     (owner: 03)
def get_meta() -> dict: ...                   # body of GET /api/meta
def analyze(request: dict) -> dict: ...       # body of POST /api/analyze (raises engine.errors.EngineError(code, message, extra))

# engine/best_sites.py  (owner: 03, v1.6)
def best_sites(request: dict) -> dict: ...    # body of POST /api/best-sites (raises engine.errors.EngineError)
```

## 6. Fixture
`fixtures/sample_response.json` must always be a valid example of section 4.3 with `"is_sample": true`. The frontend uses it when the API is unreachable and shows a visible "Sample data — API offline" banner. There is no best-sites fixture (v1.6): when the API is unreachable the best-sites button shows "Unavailable offline" and results are never faked.

## 7. AI-use header (every code file)
```
# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
```
(Use `//` or `<!-- -->` as the language requires.)
