# Ephemeris (Sun and Earth directions on the Moon)

Owner: Agent 02. Files: `scripts/fetch_ephemeris.py`, `data/ephemeris/sun_earth_vectors.npz`, `engine/ephemeris.py`, `engine/tests/test_ephemeris.py`, `docs/ephemeris_check.png`.

## Method
1. Query JPL Horizons (`CENTER='coord@301'`, `COORD_TYPE='GEODETIC'`, `SITE_COORD='lon,lat,0'`, `QUANTITIES='4'`, targets `10` Sun and `399` Earth, step 1 h, DE441) for **one reference site**: lat **-85.0**, lon **31.0** (placeholder near Mons Mouton; the real Site20 DEM centre was not available yet — re-run with `--ref-lat --ref-lon` if you want it at the DEM centre; any point within ~150 km is fine, see errors below).
2. Convert each az/el to a unit vector in the Moon **ME** frame with the reference site's East-North-Up basis (`azel_to_vec`).
3. For any point (lat, lon) project that vector on the point's own ENU basis (`local_az_el`) to get its az/el. Sun and Earth are so far away that the vector is the same everywhere in the region; the change of local elevation with latitude comes from the ENU basis.

Frame: Horizons header says `Center pole/equ: MEAN_ME (high precision)`, `Atmos refraction: NO (AIRLESS)` — same ME frame as the LOLA DEMs. Light-time and aberration are included by Horizons (columns `Azi_(a-app)`, `Elev_(a-app)`).

Table: 35,064 hourly samples, 2025-01-01T00:00Z … 2028-12-31T23:00Z, 1.67 MB. Arrays `t_unix`, `sun_vec`, `earth_vec` plus metadata (`ref_lat`, `ref_lon`, `frame`, `source`, `created_utc`, `step`). Regenerate (cached in `data/ephemeris/raw/`, git-ignored):

```bash
uv venv && uv pip install numpy requests pytest matplotlib
.venv/Scripts/python scripts/fetch_ephemeris.py --start 2025-01-01 --end 2028-12-31 --ref-lat -85.0 --ref-lon 31.0
```

## API (`engine/ephemeris.py`)
- `load_ephemeris(path)` → `Ephemeris(t_unix, sun_vec, earth_vec, meta)`; checks the table is strictly hourly.
- `Ephemeris.window(start_utc, hours)` → `(t, sun_vec, earth_vec)`; rounds the start down to the hour; naive datetimes are treated as UTC; `ValueError` if outside the table. Last valid hour is 2028-12-31T23:00Z.
- `local_az_el(vecs (T,3), lat (P,), lon (P,))` → `az, el` of shape `(P, T)`; no Python loops. 1000 × 1000 takes ~45 ms.
- `sun_disk_visible_fraction(sun_el, horizon_el, radius=0.2665)` → exact circular-segment fraction of the disk above a flat horizon line.
- `azel_to_vec(az, el, lat, lon)` → helper used by the fetch script.

## Verification (all 10 tests pass: `python -m pytest engine/tests/test_ephemeris.py`)
Ground truth: direct Horizons topocentric queries at each test site, 2027-01-01 … 2027-01-31 hourly (stored in `engine/tests/data/horizons_reference_points.json`). Maximum absolute error of table + `local_az_el` vs. direct Horizons over 744 hours:

| Test site | Distance to ref | Sun az / el (°) | Earth az / el (°) |
|---|---|---|---|
| (-85.5, 31.0) | 15.2 km | 0.00001 / 0.00000 | 0.00147 / 0.00034 |
| (-85.0, 40.0) | 23.8 km | 0.00001 / 0.00000 | 0.00323 / 0.00045 |
| (-85.0, 61.0) | 78.4 km | 0.00003 / 0.00000 | 0.00936 / 0.00169 |
| Shackleton (-89.67, 129.78) | 153.5 km | 0.00006 / 0.00000 | 0.01339 / 0.00320 |

Tolerances required: Sun ≤ 0.01°, Earth ≤ 0.05° — met everywhere. Earth error grows ~linearly with distance (parallax, ≈0.0001° per km worst case).
- Known value: Shackleton 2027-01-01 00:00 → table gives az 133.339398°, el 0.787436° (Horizons: 133.339447°, 0.787435°).
- Round trip az/el → vector → az/el: error < 1e-9°.
- Sun maximum elevation in 2027 at the reference site: 6.539° (expected (90−85)+1.54 = 6.54°).
- Earth libration at the reference site (2025–2026 FFT): period 27.23 d, elevation range −3.14° … +11.08° (half-amplitude 7.1°; the offset from 0 is expected away from the pole), unwrapped azimuth span 16° — Earth never circles the sky.
- `docs/ephemeris_check.png`: Shackleton Jan 2027 — Sun 0–1.2°, Earth −7° … +6°, Earth above the flat horizon ≈ Jan 11–23, as in the earlier plot.

## Limitations
- Parallax: the single-vector approximation error for Earth is ≤ ~0.013° within 150 km (Sun negligible). Beyond ~300 km re-fetch with a closer reference.
- Horizons EOP predictions end 2027-Feb-08; they affect Earth-orientation terms only, not the Moon's libration-based ME frame (DE441), and the Moon-fixed direction errors observed are far below the tolerances. Not independently verified beyond that date.
- Elevation is relative to the local plane of the 1737.4 km reference sphere (geodetic lat on a sphere), as in the contract; terrain horizon is handled by the terrain engine, not here.
- The reference site is a placeholder near Mons Mouton, not the verified DEM centre.
