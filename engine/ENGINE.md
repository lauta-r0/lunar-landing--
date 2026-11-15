<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->
# LunaScout terrain engine

The engine answers one question: **given where the lander is aimed, and that it will touch down
somewhere inside its landing ellipse, what fraction of the ellipse lets the mission survive?**
Survival needs sunlight (power, heat), direct-to-Earth visibility (comms) and a safe slope.

Interfaces are fixed by `CONTRACT.md`: `engine.analyze.analyze(request) -> dict` and
`engine.analyze.get_meta() -> dict`.

> **Ephemeris.** The engine uses the real JPL Horizons table of the ephemeris agent
> (`engine/ephemeris.py`, `data/ephemeris/sun_earth_vectors.npz`, hourly 2025-01-01 to 2028-12-31,
> see `engine/EPHEMERIS.md`). Check: the highest Sun elevation over 2025-2028 is 6.131 deg at the
> Site20v2 center (-85.43; expected (90 - |lat|) + 1.54 = 6.11) and 6.769 deg at the IM-2 touchdown
> (-84.79; expected 6.75). `engine/_ephemeris_stub.py` (synthetic positions) is still available for
> tests and only with `LUNASCOUT_ALLOW_STUB=1`; responses produced with it have `"is_sample": true`.

## 1. The idea in one picture

```
                          Sun, 0 to 6 deg above the horizontal
                              .
                         .          terrain skyline seen from the lander
                    .           /\        (horizon elevation, one value per azimuth)
               .               /  \____
          .   theta           /        \___      .
   [lander]------------------/-------------\----------- local horizontal plane
      |  2 m             ___/               \___
   ___|_________________/                       \________  DEM surface (LOLA, 5 m/px)

   Sun is "lit"        <=>  Sun elevation   > horizon elevation at the Sun's azimuth
   Earth is "visible"  <=>  Earth elevation > horizon elevation at Earth's azimuth
```

Near the south pole the Sun never rises more than `(90 - |lat|) + 1.54` degrees (6.1 degrees at
the DEM center), so a hill a few hundred meters away is enough to hide it, and a massif 50 km away
can still matter.

## 2. Data

Terrain is a stack of three LOLA height rasters, finest first (`engine/terrain.py`):

| Level | Product | Pixel | Coverage | Used for |
|---|---|---|---|---|
| fine | PGDA LOLA LDEM Site20v2 (Barker et al. 2021) | 5 m | x 60..86 km, y 105..131 km (26 x 26 km) | height, slope, horizon near the tile |
| near | PDS LOLA GDR `LDEM_80S_20M` v2.0, crop | 20 m | x 41..110 km, y 86..168 km | height and slope outside the tile (IM-2 sites), horizon to ~20-40 km |
| far | PDS LOLA GDR `LDEM_80S_40M` v2.0, crop | 40 m | x -39..190 km, y 6..248 km | far-field horizon out to 100 km |

| File | What | In git? |
|---|---|---|
| `data/raw/Site20v2_final_adj_5mpp_surf.tif`, `_slp.tif` | LOLA 5 m/px height and slope, PGDA "Site20v2: Leibnitz beta plateau, extended boundaries" (108 MB each) | no (ignored) |
| `data/raw/ldem_80s_20m_crop.tif`, `_slp.tif` | 20 m crop (int16, height = 0.5 x DN) and its slope (9 MB + 48 MB) | no (ignored) |
| `data/raw/ldem_80s_40m_crop.tif` | 40 m crop (int16, 27 MB) | no (ignored) |
| `data/derived/dem_meta.json` | 5 m tile coverage, CRS, center, source URLs, hillshade bounds | yes |
| `data/derived/regional_meta.json` | crop boxes, analyzable areas, sources, measured offsets vs. the 5 m tile | yes |
| `data/derived/hillshade.png` | 1700 x 2600 px shaded relief at 20 m/px, all levels composited (display only) | yes (2.5 MB) |
| `data/derived/horizon_grid/*.npy` + `meta.json` | 50 m horizon grid over the 5 m tile | only `meta.json` |
| `data/derived/horizon_grid_regional/*.npy` + `meta.json` | 100 m horizon grid north of the tile (IM-2 sites) | only `meta.json` |
| `data/derived/horizon_tiles*/` | per-row working files of the precompute (can be deleted) | no (ignored) |

5 m tile facts (read from the GeoTIFF, see `dem_meta.json`):

- 5200 x 5200 px at 5 m = 26 x 26 km, no empty pixels. Map bounds x 60,000..86,000 m, y 105,000..131,000 m.
- CRS: south polar stereographic on the 1,737,400 m sphere, `lat_0=-90`, `lon_0=0`, true scale at the
  pole. Same as the contract's fallback. The closed-form projection used in the hot loops matches
  pyproj to better than 1 mm (checked at load time and in `test_geo.py`).
- Center: **lat -85.42658, lon 31.74276 E**, height 6398.7 m. Latitude range -86.01 to -84.84,
  longitude range 24.6 to 39.3 E. Heights 1330 to 6788 m.
- Source: Barker, M. K., et al. (2021), *Planetary and Space Science* 203, 105119,
  doi:10.1016/j.pss.2020.105119. https://pgda.gsfc.nasa.gov/products/78

Regional levels (read from the PDS labels, see `regional_meta.json`):

- Files: https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/
  `ldem_80s_20m.img` (30400 x 30400 px, 1.85 GB) and `ldem_80s_40m.img` (15200 x 15200 px, 0.46 GB),
  data set `LRO-L-LOLA-4-GDR-V1.0`, product version 2.0 (2017), LOLA data through mission phase
  LRO_ES_54. 16-bit integers, height = 0.5 x DN meters above the 1,737,400 m sphere.
- Same projection (polar stereographic, 1737.4 km sphere, center lat -90, lon 0) and frame
  (MEAN EARTH/POLAR AXIS of DE421) as the 5 m tiles, and the same height reference.
- Orientation checked against the 5 m tile: row 0 is +y, column 0 is -x (correlation 1.000 along a
  26 km profile).
- Only the crop rows are downloaded (HTTP Range requests, about 250 + 180 MB); nothing is stored
  uncropped.
- NASA PDS data, no use restrictions. Citation: Smith, D. E., et al. (2017), *Icarus* 283, 70-91,
  doi:10.1016/j.icarus.2016.06.006.

Consistency with the 5 m tile (measured on the whole overlap, 5 m heights block-averaged to the
coarser pixel; `scripts/prepare_regional_dem.py`):

| Level | Median (level - 5 m) | Std | 5-95% | Best horizontal shift (+-1 px search, 1/4 px steps) |
|---|---|---|---|---|
| 20 m | -0.25 m | 1.57 m | -2.63..+2.30 m | 0 m |
| 40 m | -0.24 m | 1.47 m | -2.53..+2.14 m | 0 m |

So the levels agree to a quarter of a meter on average and are not misregistered; each regional
level is shifted by +0.25 m (`vertical_correction_m`) so its mean matches the tile. Across the edge
of a finer level the heights are blended linearly over 500 m, so there is no step at the seam.

### Coverage of the IM-2 (Athena) sites

Verified facts (sources):

- Intended site: **lat -84.78, lon 29.13 E** (LROC featured image "IM-2 Landing Region",
  https://www.lroc.asu.edu/images/1401).
- Actual touchdown: **lat -84.7906, lon 29.1957 E** (Wikipedia "Mons Mouton" / "IM-2", citing LROC).
  Intuitive Machines reported ~250 m from the target; NASA said more than 400 m. The great-circle
  distance between the two coordinates above is **369 m**.
- Touchdown time: **2025-03-06 17:31 UTC** (Space.com: "12:31 p.m. EST (1731 GMT)").
- The mission ended about 13 h after landing: Athena lay on its side inside a shadowed crater and its
  panels could not recharge.

Both sites are about **7 km north** of the 5 m tile (y = 138.0 and 138.4 km; tile edge at 131 km).
No PGDA 5 m/px product covers them (extents read from the GeoTIFF headers over HTTP, without
downloading the files):

| PGDA product | Lat range | Lon range | Covers IM-2? |
|---|---|---|---|
| Site20 (v1) | -85.79..-85.06 | 27.3..36.4 E | no |
| Site20v2 | -86.01..-84.84 | 24.6..39.3 E | no (7 km short) |
| Site06 (Nobile rim 1) | -85.90..-84.98 | 31.7..43.2 E | no |
| Site01, 04, 07, 11, 23, Haworth, Shoemaker, DM2 | elsewhere | | no |

They are covered by the 20 m level and by the regional horizon grid, so an IM-2 replay runs on real
LOLA data, with the coarser-slope caveat of section 7. Terrain at the two sites (20 m level):
height 5312 m / 5322 m, slope 1.0 / 2.4 degrees, highest point of the horizon 4.0 / 4.05 degrees.

**Replay** (`python scripts/athena_replay.py`, full report in `docs/athena_replay.md`): landing
2025-03-06 17:31 UTC (17:00 with the 1 h step), 10 days, 500 x 300 m ellipse from the intended site
toward the actual one, plus a run on the actual site (actual touchdown 84.79059 S, 29.19567 E from
Hancock et al. 2026, The Planetary Science Journal 7, doi 10.3847/PSJ/ae732f).

Main result, real data only (margin 0): intended site P = 1.00 (47/47 viable), actual site P = 0.93
(42/45), both verdict viable. **This does not match what happened** (Athena lost power about 13 h
after landing): it ended on its side in a crater of about 20 m diameter (LROC caption, NASA/GSFC/
Arizona State University), about one pixel of the 20 m DEM, so the data cannot resolve it, and the
lander tipped over (LunaScout assumes an upright lander with panels 2 m up). The report also has an
informational sensitivity table (margins 0, 1, 2, 2.86, 4 deg), not part of the default model.

### How to regenerate the large files

```
pip install -r engine/requirements.txt
python scripts/prepare_dem.py --skip-download   # (drop the flag the first time) 5 m tile from PGDA, dem_meta.json
python scripts/prepare_regional_dem.py          # 20 m / 40 m crops from PDS (about 5 min), regional_meta.json
python scripts/prepare_dem.py --skip-download   # re-run after the regional step: hillshade over all levels
python scripts/precompute_horizons.py           # 50 m grid over the tile
python scripts/precompute_horizons.py --area regional   # 100 m grid around the IM-2 sites
```

The precompute is resumable: it writes one file per grid row and skips the rows that already exist,
so it can be stopped and restarted (`--restart` if the parameters changed). For a server build,
either run the scripts in the image build or copy `data/raw/*.tif` and `data/derived/horizon_grid*/`
into the image (they are too large for git: GitHub rejects files over 100 MB). Without the regional
files the engine still runs on the 5 m tile alone (or force that with `LUNASCOUT_REGIONAL=0`).

## 3. Modules

| Module | Role |
|---|---|
| `geo.py` | lat/lon <-> map x/y, great-circle helpers, local north/east in the map plane |
| `terrain.py` | loads the terrain levels once (`Terrain`, `LayeredTerrain`); `height_at`, `slope_at` (bilinear, blended at seams), `height_nearest`, `make_hillshade` |
| `horizon.py` | horizon mask of one observer (the core algorithm) |
| `grid.py` | loads the precomputed horizon grids (`HorizonGrid`, `GridSet` = fine + regional) |
| `metrics.py` | per-point mission metrics and the classification rules of CONTRACT 4.4 |
| `analyze.py` | `analyze()` and `get_meta()` |
| `_ephemeris_stub.py` | synthetic Sun/Earth for development and tests only |
| `make_fixture.py` | `python -m engine.make_fixture` writes `fixtures/sample_response.json` |

## 4. Horizon mask (`horizon.py`)

For an observer standing `h_obs` (default 2 m) above the terrain, and for each of 360 azimuths
(1 degree bins, clockwise from local north):

1. Walk along the great circle that leaves the observer in that direction, out to **100 km**
   (or the edge of the coarsest level). Sample distances start at 10 m and grow as
   `step = max(5 m, 1% of the distance)`: 5 m steps near the lander, about 100 m steps at 10 km,
   1 km at 100 km. About 630 samples per ray; two thirds of them are within 13 km.
2. Read the terrain height `z` at every sample: bilinear inside 1 km, beyond that the nearest pixel of
   the finest level that covers the sample (5 m tile, then 20 m, then 40 m).
3. Convert it to an elevation angle with exact spherical geometry (no flat-Moon approximation):

   `theta = atan2( (R+z) cos(s/R) - (R + z0 + h_obs),  (R+z) sin(s/R) )`

   `R` = 1,737,400 m, `s` = ground distance, `z0` = terrain height under the observer. The term
   `cos(s/R)` is the curvature drop: 7 m at 5 km, 29 m at 10 km, 2.9 km at 100 km.
4. The horizon elevation at that azimuth is the largest `theta` over the samples inside the DEM.
   The distance of the last sample inside the DEM (`reach`) is stored too: if a ray leaves the DEM
   early, more distant peaks are missing and the horizon may be underestimated. With the regional
   levels every ray of the analyzable area reaches the full 100 km.

All 360 azimuths x 630 samples of one observer are one numpy array operation (no Python loop).
Measured: **24 to 31 ms per observer** with the three levels and 100 km rays (14 to 20 ms with the
5 m tile alone and rays stopping at its edge).

Effect of the far field (5 m tile + regional levels vs. 5 m tile alone, same observer): at the
summit plateau and the DEM center the horizon rises by up to 0.56 and 0.76 degrees in a few
directions (about 2% of azimuths change by more than 0.1 degree); on the crater floor nothing
changes because the local rim is higher than anything beyond it. With the Sun 0 to 6 degrees up,
0.5 degree is a real difference in lit hours.

Why 1% spacing: 1 degree azimuth bins are 1.7% of the distance apart sideways, so sampling the
ray much finer than that along its length would not add accuracy. Worst-case angular error from
the ray spacing on a 30 degree slope is about 0.17 degrees; from the nearest-pixel read beyond
1 km, less than 0.08 degrees. The Sun's disk is 0.53 degrees wide.

### Precomputed grids (`scripts/precompute_horizons.py`)

- **Fine**: regular grid, **50 m spacing**, over the 5 m tile with a 1 km margin (x 61..85 km,
  y 106..130 km): 481 x 481 = **231,361 nodes**.
- **Regional** (`--area regional`): **100 m spacing**, x 61..85 km, y 130.1..148 km, north of the
  fine grid and around the IM-2 sites: 241 x 180 = **43,380 nodes**. Its slope comes from the 5 m
  tile where it reaches (y < 131 km) and from the 20 m level elsewhere.
- Both use all terrain levels for the horizon (100 km rays).
- Per node: 360 horizon elevations (float16), 360 reach values (uint16, units of 10 m), height,
  slope, lat, lon. 339 MB (fine) + 64 MB (regional) on disk; the API keeps the horizon arrays
  (167 + 31 MB) in RAM and memory-maps the reach arrays.
- Time with 12 worker processes on the 16-core laptop: fine grid 17.2 min (53 ms per node per core
  under full load), regional grid about 3 min. The row files are working data and can be deleted
  after the merge.
- Observer height is fixed at 2 m in the grid. A request with a different `observer_height_m`
  is computed on the fly instead (about 65 points, with a warning).

## 5. Analysis (`analyze.py`)

1. **Normalize** the request (defaults of CONTRACT 4.2; the landing time is floored to the hour).
2. **Coverage**: the target must be inside the analyzable area (the union of the two grid areas:
   x 61..85 km, y 106..148 km, lat about -86.0 to -84.6) and at least 80% of the ellipse area must be
   inside it; otherwise `out_of_coverage` with the DEM center as `suggested_target`. The landing time plus mission plus delay range must be inside the
   ephemeris; otherwise `out_of_ephemeris_range`.
3. **Sample points**: the grid nodes inside the ellipse. The ellipse azimuth is measured from
   *local* north at the target, which in a polar stereographic map points away from the pole, not
   along the map's y axis. More than 400 nodes are thinned to a regular sub-lattice (71 m, 100 m,
   141 m, ...). When the ellipse touches the 100 m regional grid, both grids are sampled at the
   same spacing (100 m or coarser), so the point density stays uniform across the seam and the
   survival fraction is not biased toward one side. Fewer than 40 nodes (small ellipse) switches to
   about 70 points on a hexagonal grid whose horizons are computed on the fly, spread over threads
   (`LUNASCOUT_THREADS`, default min(4, CPUs)).
4. **Sun and Earth** azimuth/elevation at every point and hour (`local_az_el`), compared with the
   point's horizon at that azimuth (linear interpolation between the 1 degree bins, wrapping at
   360). The target itself always gets its own exact horizon, not the nearest grid node.
5. **Metrics per point** over the mission window: sunlit hours, longest darkness, % of time with
   Earth visible, longest comms gap, hours until sunset, Sun at touchdown, slope. Run lengths are
   computed with cumulative numpy operations.
6. **Classification** exactly as CONTRACT 4.4 (v1.4). `survival_probability = viable / n_points`.
   **Darkness is judged only by `longest_dark_h` against `max_dark_h`**: not_viable above the limit,
   risky within `risk_margin` of it. A sunset during the mission does not make a point risky by
   itself (before v1.4 it did, so the headline probability never changed with the battery size on
   missions with a sunset; validation finding P1). `hours_until_sunset` is still computed and shown,
   as an informative target metric (`pass` is `null`), so `checks_total` is 6 by default.
7. **Delay curve**: the same (points x hours) arrays are sliced 24 h later for each delay day and
   reclassified. `delay_tolerance_days` is the last day up to which the target stays viable or risky.
8. **Recommendations**: 24 candidates on rings at 1, 2 and 3 km (8 bearings) plus the curated
   sites, each evaluated on a coarser sample (up to 60 grid nodes); the best 3 that beat the current
   probability are returned.
   "Ellipse area over max slope" samples the finest slope raster on a 5 m lattice inside the ellipse.
9. Identical requests are served from a 32-entry cache. Recommendations are truly nearby: rings at 1, 2 and 3 km (8 bearings each) plus curated sites within 5 km of the target (`REC_MAX_CURATED_KM`).

### Sun clearance (`min_sun_margin`, `low_sun_margin`, CONTRACT v1.3)

LunaScout results come purely from the real DEM and JPL Horizons: **no default safety margin**.
`limits.min_sun_margin_deg` defaults to 0 everywhere (5 m tile and 20 m DEM); `null` or absent also
means 0. It stays as an optional user override: with a margin > 0, a point is **risky** with reason
`low_sun_margin` ("Sun clearance below the margin set by the user") when, during the **lit hours** of
the mission, the smallest clearance `sun_el - horizon_at_sun` is below it. It never makes a point
not_viable and is not a computed shadow. With margin 0 the reason never appears.

The target metric `min_sun_margin` ("Minimum Sun clearance") and `timeseries.sun_margin_deg` always
report the real clearance (informative); `pass` is `null` when the margin is 0, so `checks_total`
is 7 by default (8 with a margin > 0).

Points on the 20 m DEM keep `slope_coarse` / `slope_dem_m` and the warning that coarse terrain cannot
resolve small craters: that is about data resolution, not an adjustment.

Window: all lit hours of the mission. Unlit hours are excluded because darkness already penalizes them.

Fields added in CONTRACT v1.1:
- `timeseries.sun_visible_fraction`, the fraction of the solar disk above the horizon, for display.
  Classification uses the center-of-disk rule only.
- `points[].slope_dem_m` / `target.slope_dem_m` (5 or 20) and `points[].slope_coarse` /
  `target.slope_coarse` (true outside the 5 m tile, where the slope comes from the 20 m DEM and
  underestimates local steepness). A warning gives the share of such points.
- `coverage.message`: set when the target is outside the 5 m tile.

`coverage.bounds_xy_m` in `get_meta()` is the **analyzable area** (x 61,000..85,000, y
106,000..148,000), i.e. where a target is accepted; `map.hillshade_bounds_xy_m` is the full image
(x 56,000..90,000, y 101,000..153,000). `coverage.message` in an analysis says when the target is
outside the 5 m tile, and `sources` lists the PDS regional DEM when it is loaded.

### Curated sites

The terrain sites were chosen from the horizon grid with geometry only (no ephemeris): 350 m mean
slope, and the fraction of azimuths where an idealized Sun (`elevation = colatitude * cos(azimuth) +
season`, season = +1.54 / 0 / -1.54 degrees) clears the terrain horizon. Their labels are
descriptive, not official names. The two IM-2 entries are real landing sites (sources in section 2,
"Coverage of the IM-2 (Athena) sites") and are listed only when the regional DEM is loaded.

| id | Label | lat, lon | Why |
|---|---|---|---|
| `mons_mouton_center` | Mons Mouton (DEM center) | -85.42658, 31.74276 | center of the DEM; sits on a slope rising to the north (8 degree horizon there) |
| `summit_plateau` | Summit plateau (high, flat, long sunlight) | -85.47628, 31.39691 | 6311 m, slope 4 degrees, horizon below 3.8 degrees in every direction |
| `western_bench` | Western bench (flat, Earth in view) | -85.39890, 29.95361 | slope 2 degrees, low horizon toward Earth |
| `crater_floor` | Crater floor (shadowed) | -85.23787, 33.95403 | flat floor, horizon up to 16 degrees, never clears the idealized Sun |
| `sunlit_slope` | Sunlit slope (steep) | -85.48962, 30.66935 | well lit but 12 degree slope |
| `im2_athena_intended` | IM-2 Athena intended site | -84.78, 29.13 | LROC featured image "IM-2 Landing Region" |
| `im2_athena_actual` | IM-2 Athena actual touchdown | -84.7906, 29.1957 | Wikipedia "IM-2" / "Mons Mouton", citing LROC |

## 6. Assumptions

- Landing point **uniformly distributed** inside the ellipse (stated in every response).
- Observer (solar array / antenna) **2 m** above the terrain.
- **1 hour** time step; a sunset between two samples is located to the hour. A sunset is informative only; whether the lander survives the night is decided by `longest_dark_h` vs. `max_dark_h` (CONTRACT v1.4).
- **Center-of-disk** rule for sunlight; no penumbra in the classification.
- Horizon known out to **100 km** (5 m tile, then 20 m / 40 m LOLA polar DEM).
- No atmosphere, so no refraction (correct for the Moon).
- Slope is the PGDA 5 m slope product on the tile; boulders and craters smaller than about 5 m are
  not seen. Outside the tile it is the slope of the 20 m LOLA DEM.
- One Sun/Earth direction for the whole DEM at each hour: the parallax across the 26 x 42 km
  analyzable area is under 0.01 degrees for Earth and negligible for the Sun.

## 7. Known limitations

- **Terrain beyond 100 km is not modeled.** At 100 km the curvature drop is 2.9 km, so only very high
  massifs farther away could still reach above the local horizon. The warning states the range.
- **Coarser terrain outside the 5 m tile.** North of y = 131 km (including the IM-2 sites) heights
  and slopes come from the 20 m LOLA DEM: features smaller than about 40 m are smoothed and slopes
  are underestimated (the 5 m tile has only 23% of its area under 8 degrees; the 20 m slope looks
  gentler). Responses say how many sample points are outside the tile.
- **LOLA track artifact.** The 20 m polar DEM shows one straight, narrow ridge/groove from a single
  LOLA track, crossing the regional area about 8 km north of the IM-2 sites (visible in the
  hillshade). It is a few meters high and narrow, so its effect on horizons is small, but slopes on
  it are not real.
- **Coverage.** The analyzable area is x 61..85 km, y 106..148 km (lat about -86.0 to -84.4 around
  lon 22..39 E): the Site20v2 tile plus the IM-2 area.
- **Rough terrain.** Only 23% of the tile has a 5 m slope under 8 degrees, so slope is the most
  common reason for "not viable".
- No thermal model (darkness duration is the proxy), no relay satellites, no eclipses, no descent
  trajectory constraints.
- Recommendations use a coarser sample than the main analysis, so their probability is comparable
  to, not identical with, a full run on that target.
- DEM height error (0.3 to 0.5 m RMS on the tile) is not propagated. **Future work:** quantify the
  horizon uncertainty on the 5 m tile with the 100 PGDA DEM clones (recompute the horizon on each
  clone and use the spread as a per-point Sun-clearance margin instead of 0 deg).
- Unresolved terrain (e.g. the ~20 m crater where Athena ended) is not in the 20 m DEM; the optional
  `min_sun_margin_deg` lets a user explore that sensitivity (docs/athena_replay.md).

## 8. Tests

`python -m pytest engine/tests -q` : **57 passed** (about 1 min, including the 10 ephemeris tests of the
ephemeris agent; the tests that need the real DEM are skipped when it is not downloaded).

| Test | Expected | Result |
|---|---|---|
| Flat sphere, h = 2 m | horizon = -acos(R/(R+h)) = -0.0869 degrees | within 0.0002 degrees at all 360 azimuths |
| Ring wall, H = 200 m at D = 2 km | atan2(H - h - D^2/2R, D) = 5.62 degrees | within 0.1 degrees (default sampling), 0.03 degrees (fine sampling), never above the analytic value |
| Wall 60 m at 5 km | curvature term changes the answer by 0.08 degrees | matches the formula with curvature to 0.01 degrees |
| Wall only to the east | high at azimuth 90, flat at 0 / 180 / 270 | passes (azimuth is clockwise from north) |
| Symmetric bowl | horizon independent of azimuth | spread under 0.03 degrees (0.01 with bilinear sampling throughout) |
| Classification | every rule of CONTRACT 4.4, limits and margins; a sunset alone is not a reason (v1.4) | passes |
| Battery rule (v1.4) | one point with a 60 h night: not_viable at max_dark_h 50, risky at 60-74, viable from 76; four points with nights of 30/60/100/200 h in 14 days all see a sunset, and the viable count goes 0, 1, 2, 3, 4 as max_dark_h goes 25, 50, 100, 150, 400 | passes |
| Survival vs. battery, end to end (v1.4) | `analyze()` on a 14-day mission, other limits relaxed, every point with a sunset: P = 0.0 at max_dark_h 50 and above 0.5 at 250, never decreasing | passes |
| Contract shape | keys, types, lengths, consistency of `analyze()` output | passes in grid mode, on-the-fly mode and without a grid |
| Physical sanity (synthetic) | crater floor darker than the open plain; Sun never above (90 - lat) + 1.54 | passes |
| Ellipse orientation | azimuth 0 elongates the ellipse along local north | passes |
| Two-level terrain (synthetic) | finest level wins; linear 500 m ramp across the seam, no step; int16 scale and vertical correction | passes |
| Far-field wall: 3 km high at 40 km, only in the coarse DEM | invisible with the fine tile alone; atan2(H - h - D^2/2R, D) = 3.6 degrees with both levels | within 0.15 degrees at all azimuths |
| Ray length | rays stop at 100 km | passes |
| Grid seam | fine 50 m + coarse 100 m grids sampled at one common spacing | 220 + 180 points, exactly the 100 m lattice on both sides |
| Sun clearance | low margin in a lit hour -> risky `low_sun_margin` only; unlit hours ignored; margin 0 disables it; `min_sun_margin` = min of `sun_margin_deg` over lit hours | passes |
| Real data | composite = 5 m DEM inside the tile; IM-2 sites on the 20 m level; no step across the north seam | passes |

## 9. Timings

Laptop, 16 cores, Python 3.13, real JPL Horizons ephemeris, default request
(7 days, 1000 x 600 m ellipse, 30 delay days). The engine uses one core, except the on-the-fly
horizons (2 threads here, as on a 2 vCPU Cloud Run instance). Measured after a long full-CPU
precompute: this laptop was about 1.6x slower than when it was cool (one horizon: 24-31 ms cool,
45-50 ms in this state), so the numbers below are on the pessimistic side.

| Case | Time | Contract target |
|---|---|---|
| Summit plateau (5 m tile, 384 points), with recommendations | **551 ms** (max 599) | < 3 s |
| Summit plateau, without recommendations | **308 ms** (max 315) | < 1.5 s |
| IM-2 actual touchdown (20 m level, ~190 points), with recommendations | **338 ms** (max 433) | < 3 s |
| IM-2 actual touchdown, without recommendations | **170 ms** (max 189) | < 1.5 s |
| Identical request (cache) | 9 ms | |
| Cold: first `get_meta()` of a new process (loads 3 DEM levels + 2 grids + ephemeris) | 3.8 to 5.1 s | call `get_meta()` at API start-up |
| Small ellipse 100 x 100 m at the IM-2 site (73 points on the fly, 2 threads), first time | 2.5 s (3.9 s with 1 thread, 1.5 s with 4) | < 3 s |
| Same small ellipse, new date (horizons cached) | 73 ms | |
| Largest request: 30 days, 60 delay days, 5 x 5 km | 1.8 s | |
| Horizon of one observer (3 levels, 100 km rays) | 24 to 31 ms cool, 45 to 55 ms throttled | < 30 ms |

Most of the warm time is Sun/Earth geometry and horizon interpolation for every point and hour;
the terrain only matters for on-the-fly horizons.

Memory: about 600 MB (5 m height + slope 2 x 108 MB, 20 m height int16 28 MB + slope 57 MB,
40 m height int16 69 MB, horizon arrays 167 + 31 MB).

## 10. Environment variables

| Variable | Effect |
|---|---|
| `LUNASCOUT_ALLOW_STUB=1` | allow the synthetic ephemeris when the real one is missing (development only) |
| `LUNASCOUT_DEM_DIR` | folder with the GeoTIFFs (default `data/raw`) |
| `LUNASCOUT_GRID_DIR` | folder with the fine horizon grid (default `data/derived/horizon_grid`) |
| `LUNASCOUT_REGIONAL_GRID_DIR` | folder with the regional horizon grid (default `data/derived/horizon_grid_regional`) |
| `LUNASCOUT_REGIONAL=0` | ignore the regional DEM levels and grid (5 m tile only, horizon to its edge) |
| `LUNASCOUT_GRID_MMAP=1` | memory-map the horizon array instead of loading it into RAM |
| `LUNASCOUT_THREADS` | threads for on-the-fly horizons (default min(4, CPU count)) |
