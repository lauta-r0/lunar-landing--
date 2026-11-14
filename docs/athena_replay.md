<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->
# IM-2 "Athena" replay

Generated 2026-11-14 22:54 UTC by `python scripts/athena_replay.py`.

## Inputs

- Intended site: lat -84.78, lon 29.13 E. Actual touchdown: lat -84.7906, lon 29.1957 E. Distance between them: 369 m, bearing 150.6 deg.
- Landing 2025-03-06T17:31:00Z (the engine uses a 1 h step, so 17:00 UTC), mission 10 days, default limits (max darkness 50 h, max comms gap 72 h, Earth >= 50%, slope <= 8 deg).
- Ellipse 500 x 300 m (semi-axes), major axis at azimuth 150.6 deg, i.e. pointing from the intended site at the actual one. Why: the actual site (369 m away) must be inside, and the reported miss distances (~250 m per Intuitive Machines, >400 m per NASA) suggest a dispersion of a few hundred meters, larger along track than across.
- Terrain: both sites are outside the LOLA 5 m/px tile; heights and slopes come from the LOLA 20 m/px polar DEM, horizons from the 20 m and 40 m DEMs out to 100 km.

## Results

| | Run A: target = intended site | Run B: target = actual touchdown |
|---|---|---|
| Survival probability (viable / points) | 1.000 (47/47) | 0.933 (42/45) |
| Incl. risky | 1.000 | 1.000 |
| Target verdict | viable | viable |
| Sun at touchdown (target) | Yes · el 2.4° | Yes · el 2.4° |
| Time until sunset (target) | > 10 d 0 h | > 10 d 0 h |
| Longest darkness (target) | 0 h | 0 h |
| Earth visible (target) | 100% | 100% |
| Target slope | 1.0 deg (20 m DEM) | 2.4 deg (20 m DEM) |
| Would LunaScout have flagged the risk? | no | no |

Sample point of run A nearest to the actual touchdown (11 m from it): class **viable**, reasons none, lit at touchdown: True, hours until sunset 240, slope 2.7 deg (coarse 20 m).

## Honest reading

- **This does not match reality.** LunaScout rates the actual touchdown as **viable** (survival probability 0.93), but Athena lost power about 13 h after landing.
- The real ephemeris and the 20/40 m terrain put the Sun only **1.6 deg above the DEM horizon** during the first 13 h (Sun elevation 2.4-2.9 deg). To hide the whole solar disk, local relief only has to rise above the panels by about 0.3 m at 10 m, 0.7 m at 20 m, 1.6 m at 50 m. Athena came to rest inside a shadowed crater; relief that small (a crater rim a few tens of meters away, less than a meter or two high) is below what a 20 m DEM resolves, so that shadow is not in our data. (The size of Athena's crater is not verified here; the numbers only show how little relief is needed.)
- Athena also ended up on its side, so its solar panels were close to the ground and not facing the Sun. LunaScout assumes an upright lander with panels 2 m above the terrain.
- What LunaScout does show: a very low Sun (a margin of 1-2 deg) at a site evaluated on 20 m terrain. A low-Sun margin is itself a warning sign at the pole. A possible improvement is a "risky" flag when the Sun-horizon margin is under ~2-3 deg, or wherever the slope and terrain come from the coarse DEM.
- Tip-over is captured only through the DEM slope. Here the slope comes from a 20 m DEM, which smooths boulders, crater rims and small craters, so the real local slope was likely steeper than shown.
- The engine models sunlight, Earth visibility and slope; it does not model the descent, the landing dynamics or the lander's attitude after touchdown (Athena lay on its side, so its panels could not face the Sun even where the ground was lit).

## Warnings returned by the engine (run A)

- Horizon is modeled out to 101 km from the target: LOLA 5 m/px tile nearby, LOLA 20 m and 40 m/px polar DEM beyond it. Terrain farther than 100 km is not modeled.
- 100% of the sample points (target outside the tile) lie outside the LOLA 5 m/px tile: their terrain and slope come from the 20 m/px LOLA polar DEM, which smooths features smaller than about 40 m, so slopes there underestimate the local steepness (points flagged with slope_coarse = true). Tip-over risk from boulders and small craters is not captured.
- Survival probability assumes the landing point is uniformly distributed inside the ellipse.

## Sources

- Intended site: LROC featured image "IM-2 Landing Region", https://www.lroc.asu.edu/images/1401
- Actual touchdown: Wikipedia "IM-2" / "Mons Mouton" (citing LROC); ~250 m from target per Intuitive Machines, NASA said more than 400 m
- Touchdown time: Space.com, "12:31 p.m. EST (1731 GMT)"
- Mission end ~13 h after landing, lander on its side in a shadowed crater: https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/
- JPL Horizons System (Solar System Dynamics Group, NASA JPL) — Sun and Earth topocentric positions
- LRO LOLA 5 m/px LDEM — Site20v2 (Mons Mouton / Leibnitz beta plateau) (Barker et al. 2021, NASA GSFC PGDA)
- LRO LOLA 20 m/px and 40 m/px south polar LDEM (LRO-L-LOLA-4-GDR-V1.0, product v2.0, NASA PDS Geosciences Node; Smith et al. 2017)
