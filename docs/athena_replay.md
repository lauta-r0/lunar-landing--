<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->
# IM-2 "Athena" replay

Generated 2026-11-15 12:42 UTC by `python scripts/athena_replay.py`; wording and sources revised 2026-11-15 after the independent validation (`docs/validation.md` §3).

> **What this is.** LunaScout is a general landing-site tool; this page is one real-world **test case**, not a prediction. It checks that LunaScout runs on a real touchdown site and shows the limits of terrain-scale lighting: Athena's site was sunlit at the scale of the available terrain data (LunaScout and LROC QuickMap agree), and the mission was lost to the lander's attitude in a crater smaller than that data can show.

## Inputs

- Intended site: lat -84.78, lon 29.13 E (LROC, primary source). Actual touchdown: lat -84.79059, lon 29.19567 E (Hancock et al. 2026, The Planetary Science Journal 7, https://doi.org/10.3847/PSJ/ae732f; it agrees with the LROC caption, 84.7906 S, 29.1957 E). Distance between the two coordinates: 369 m, bearing 150.6 deg. The intended site is published with two decimals (±0.005°, about ±150 m north-south), so the true distance is anywhere from 238 to 511 m; that range covers every reported value (Intuitive Machines 250 m, NASA more than 400 m, Hancock et al. about 500 m).
- Landing 2025-03-06T17:31:00Z as entered (Hancock et al. give 17:28 UTC; either way the 1 h step uses 17:00 UTC), mission 10 days, default limits (max darkness 50 h, max comms gap 72 h, Earth >= 50%, slope <= 8 deg).
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

- **LunaScout does not reproduce the loss, and is not expected to.** With the 20 m DEM it rates the actual touchdown **viable** (survival probability 0.93); Athena lost power and the mission ended about 12–13 h after touchdown (Hancock et al. 2026: about 12 h; SpacePolicyOnline: about 13 h).
- **Independent check:** LROC QuickMap's terrain-shadow model (20 m/px) also shows the actual and intended sites sunlit in all of the first 15 hours (`docs/validation.md` §3.3). Terrain-scale lighting was not the problem.
- **Cause, per the primary source:** the landed "orientation and location resulted in a power-negative state" (Hancock et al. 2026). The lander ended on its side in a "20-meter diameter crater" (LROC featured image 1408, NAC M1495922531LR, NASA/GSFC/Arizona State University), which Hancock et al. describe as shallow. That crater is about one pixel of the 20 m DEM, so no available terrain data can represent it.
- The real ephemeris and the 20/40 m terrain put the Sun **1.6 deg above the DEM horizon** during the first 13 h (Sun elevation 2.4-2.9 deg). To hide the whole solar disk, local relief only has to rise above the panels by about 0.3 m at 10 m, 0.7 m at 20 m, 1.6 m at 50 m; relief that small is below what a 20 m DEM resolves. This shows how little unresolved relief would matter; it does not show that the crater itself shadowed an upright lander (a shallow crater may not).
- The lander tipped over, so its panels were near the ground and misoriented. LunaScout assumes an upright lander with panels 2 m above the terrain and does not model attitude.
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

- Intended-site coordinates (-84.78, 29.13) come from the LROC featured image with two decimals, so the intended-to-actual distance is only known to be 238-511 m (369 m at the nominal values).
- The 20 m DEM cannot resolve the ~20 m crater Athena landed in, and the lander's attitude is not modeled.

## Warnings returned by the engine (run A, margin 0)

- Horizon is modeled out to 101 km from the target: LOLA 5 m/px tile nearby, LOLA 20 m and 40 m/px polar DEM beyond it. Terrain farther than 100 km is not modeled.
- 100% of the sample points (target outside the tile) lie outside the LOLA 5 m/px tile: their terrain and slope come from the 20 m/px LOLA polar DEM, which smooths features smaller than about 40 m, so slopes there underestimate the local steepness (points flagged with slope_coarse = true). Tip-over risk from boulders and small craters is not captured.
- Survival probability assumes the landing point is uniformly distributed inside the ellipse.

## Sources

- Intended site: LROC featured image "IM-2 Landing Region", https://lroc.im-ldi.com/images/1401 (two decimals)
- Actual touchdown (84.79059 S, 29.19567 E): Hancock et al. 2026, "The Polar Resources Ice Mining Experiment-1 (PRIME-1) Payload Operations Summary from the IM-2 Mission", The Planetary Science Journal 7, https://doi.org/10.3847/PSJ/ae732f, Sect. 1.2: touchdown 17:28 UTC, about 500 m from the intended site, power loss from "orientation and location", mission end about 12 h after touchdown
- Crater of about 20 m diameter, lander on its side: LROC "IM-2 Athena Seen Obliquely" caption, NAC M1495922531LR [NASA/GSFC/Arizona State University], https://lroc.im-ldi.com/images/1408 (primary)
- Touchdown time as entered in the replay: Space.com, "12:31 p.m. EST (1731 GMT)"; primary source above: 17:28 UTC
- Mission end about 13 h after landing (press): https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/
- JPL Horizons System (Solar System Dynamics Group, NASA JPL) — Sun and Earth topocentric positions
- LRO LOLA 5 m/px LDEM — Site20v2 (Mons Mouton / Leibnitz beta plateau) (Barker et al. 2021, NASA GSFC PGDA)
- LRO LOLA 20 m/px and 40 m/px south polar LDEM (LRO-L-LOLA-4-GDR-V1.0, product v2.0, NASA PDS Geosciences Node; Smith et al. 2017)
