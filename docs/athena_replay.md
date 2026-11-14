<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->
# IM-2 "Athena" replay

Generated 2026-11-14 23:50 UTC by `python scripts/athena_replay.py`.

## Inputs

- Intended site: lat -84.78, lon 29.13 E (LROC, primary source). Actual touchdown: lat -84.79059, lon 29.19567 E (Hancock et al. 2026, The Planetary Science Journal 7, https://doi.org/10.3847/PSJ/ae732f; it agrees with the LROC caption, 84.7906 S, 29.1957 E). Distance between the two coordinates: 369 m, bearing 150.6 deg. The paper reports the lander about 500 m from the intended site, so the intended-site coordinates used here are approximate (limitation).
- Landing 2025-03-06T17:31:00Z (the engine uses a 1 h step, so 17:00 UTC), mission 10 days, default limits (max darkness 50 h, max comms gap 72 h, Earth >= 50%, slope <= 8 deg).
- Ellipse 500 x 300 m (semi-axes), major axis at azimuth 150.6 deg, i.e. pointing from the intended site at the actual one, so the actual site is inside the ellipse.
- Terrain: both sites are outside the LOLA 5 m/px tile; heights and slopes come from the LOLA 20 m/px polar DEM, horizons from the 20 m and 40 m DEMs out to 100 km.

## Main result (real data only, `min_sun_margin_deg` = 0)

| | A: intended site | B: actual touchdown |
|---|---|---|
| Survival probability (viable / points) | 1.000 (47/47) | 0.933 (42/45) |
| Incl. risky | 1.000 | 1.000 |
| Target verdict | viable | viable |
| Sun at touchdown (target) | Yes · el 2.4° | Yes · el 2.4° |
| Time until sunset (target) | > 10 d 0 h | > 10 d 0 h |
| Longest darkness (target) | 0 h | 0 h |
| Earth visible (target) | 100% | 100% |
| Minimum Sun clearance (target, informative) | 1.6° | 1.6° |
| Target slope | 1.0 deg (20 m DEM) | 2.4 deg (20 m DEM) |
| Would LunaScout have flagged the risk? | no | no |

Sample point of run A nearest to the actual touchdown (11 m from it): class **viable** (reasons none); lit at touchdown: True, hours until sunset 240, slope 2.7 deg (coarse 20 m).

## Honest reading

- **The main result (real data only, margin 0) does not match what happened.** With the 20 m DEM LunaScout rates the actual touchdown **viable** (survival probability 0.93), but Athena lost power about 13 h after landing.
- **Why: the data cannot resolve the crater.** Athena ended on its side inside a crater of about 20 m diameter (LROC image caption, NASA/GSFC/Arizona State University, reported by leonarddavid.com), which is about one pixel of the 20 m DEM. The available terrain data cannot represent it.
- The real ephemeris and the 20/40 m terrain put the Sun **1.6 deg above the DEM horizon** during the first 13 h (Sun elevation 2.4-2.9 deg). To hide the whole solar disk, local relief only has to rise above the panels by about 0.3 m at 10 m, 0.7 m at 20 m, 1.6 m at 50 m; relief that small is below what a 20 m DEM resolves.
- The lander tipped over: its panels were near the ground and misoriented. LunaScout assumes an upright lander with panels 2 m above the terrain.
- Tip-over is captured only through the DEM slope, which a 20 m DEM smooths (boulders, crater rims, small craters), so the real local slope was likely steeper than shown.
- The engine models sunlight, Earth visibility and slope; it does not model the descent, the landing dynamics or the lander's attitude after touchdown.

## Sensitivity to unresolved terrain (informational, not part of the default model)

Sensitivity to unresolved terrain, not part of the default model. The user-set `min_sun_margin_deg` marks points amber (`low_sun_margin`) when the Sun clears the computed horizon by less than the margin during lit hours. 2.86 deg = atan(1 m / 20 m).

| Sun-clearance margin | Survival probability (A: intended site) | Survival probability (B: actual site) | Actual-site class (B target) |
|---|---|---|---|
| 0° | 1.000 | 0.933 | viable |
| 1° | 1.000 | 0.911 | viable |
| 2° | 0.000 | 0.000 | risky |
| 2.86° | 0.000 | 0.000 | risky |
| 4° | 0.000 | 0.000 | risky |

## Limitations

- Intended-site coordinates (-84.78, 29.13) come from the LROC featured image (primary source) and are approximate; the paper puts the touchdown about 500 m from the intended site, while these coordinates are 369 m apart.
- The 20 m DEM cannot resolve the ~20 m crater Athena landed in, and the lander's attitude is not modeled.

## Warnings returned by the engine (run A, margin 0)

- Horizon is modeled out to 101 km from the target: LOLA 5 m/px tile nearby, LOLA 20 m and 40 m/px polar DEM beyond it. Terrain farther than 100 km is not modeled.
- 100% of the sample points (target outside the tile) lie outside the LOLA 5 m/px tile: their terrain and slope come from the 20 m/px LOLA polar DEM, which smooths features smaller than about 40 m, so slopes there underestimate the local steepness (points flagged with slope_coarse = true). Tip-over risk from boulders and small craters is not captured.
- Survival probability assumes the landing point is uniformly distributed inside the ellipse.

## Sources

- Intended site: LROC featured image "IM-2 Landing Region", https://www.lroc.asu.edu/images/1401
- Actual touchdown (84.79059 S, 29.19567 E): Hancock et al. 2026, "The Polar Resources Ice Mining Experiment-1 (PRIME-1) Payload Operations Summary from the IM-2 Mission", The Planetary Science Journal 7, https://doi.org/10.3847/PSJ/ae732f, Sect. 1.2 (about 500 m from the intended site)
- Crater of about 20 m diameter, lander on its side: LROC "IM-2 Athena Seen Obliquely" caption, NAC M1495922531LR [NASA/GSFC/Arizona State University], https://lroc.im-ldi.com/images/1408; reported by https://www.leonarddavid.com/?p=44873
- Touchdown time: Space.com, "12:31 p.m. EST (1731 GMT)"
- Mission end ~13 h after landing: https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/
- JPL Horizons System (Solar System Dynamics Group, NASA JPL) — Sun and Earth topocentric positions
- LRO LOLA 5 m/px LDEM — Site20v2 (Mons Mouton / Leibnitz beta plateau) (Barker et al. 2021, NASA GSFC PGDA)
- LRO LOLA 20 m/px and 40 m/px south polar LDEM (LRO-L-LOLA-4-GDR-V1.0, product v2.0, NASA PDS Geosciences Node; Smith et al. 2017)
