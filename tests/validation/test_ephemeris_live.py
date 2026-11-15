# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Ephemeris cross-check: the live LunaScout API vs. direct JPL Horizons topocentric queries.

For each site and hour, Horizons is queried directly (CENTER='coord@301', COORD_TYPE='GEODETIC',
SITE_COORD='lon,lat,0', QUANTITIES='4', airless apparent az/el) and compared with the API's
`timeseries` at hour 0 (sun_az/el, earth_az/el) for a 1-day mission landing at that hour.
Shackleton is outside the analyzable area, so the API must refuse it (400 out_of_coverage); there
the check uses LunaScout's own table + `engine.ephemeris.local_az_el` (pure geometry, no terrain).

Tolerances (Agent 06 brief): Sun <= 0.02 deg, Earth <= 0.05 deg (azimuth error scaled by cos(el)
is NOT applied: raw azimuth differences are compared, which is stricter).
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest
import requests

from .conftest import ATHENA_ACTUAL, DEM_CENTER, SHACKLETON, analyze

HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "validation" / "ephemeris_crosscheck.json"

SUN_TOL, EARTH_TOL = 0.02, 0.05


def _random_hours(n=3, seed=2026):
    rng = random.Random(seed)
    t0 = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    hours = int((dt.datetime(2028, 12, 30, tzinfo=dt.timezone.utc) - t0).total_seconds() // 3600)
    return sorted((t0 + dt.timedelta(hours=rng.randrange(hours))) for _ in range(n))


HOURS = _random_hours()
KNOWN = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)


def _jd(t: dt.datetime) -> float:
    return t.timestamp() / 86400.0 + 2440587.5


@lru_cache(maxsize=None)
def horizons(body: str, lat: float, lon: float, times: tuple) -> list[tuple[float, float]]:
    params = {"format": "json", "COMMAND": f"'{body}'", "MAKE_EPHEM": "YES", "EPHEM_TYPE": "OBSERVER",
              "CENTER": "'coord@301'", "COORD_TYPE": "'GEODETIC'", "SITE_COORD": f"'{lon},{lat},0'",
              "TLIST": " ".join(f"{_jd(t):.9f}" for t in times), "TLIST_TYPE": "JD", "TIME_TYPE": "UT",
              "QUANTITIES": "'4'", "ANG_FORMAT": "DEG", "EXTRA_PREC": "YES", "CSV_FORMAT": "YES"}
    try:
        r = requests.get(HORIZONS, params=params, timeout=120)
        r.raise_for_status()
    except requests.RequestException as e:
        pytest.skip(f"JPL Horizons not reachable: {e}")
    txt = r.json()["result"]
    assert "AIRLESS" in txt and "MEAN_ME" in txt, "unexpected Horizons header (frame / refraction)"
    rows = txt.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()
    out = []
    for line in rows:
        f = [c.strip() for c in line.split(",")]
        nums = [c for c in f[1:] if c not in ("",) and c.replace(".", "", 1).replace("-", "", 1).isdigit()]
        out.append((float(nums[-2]), float(nums[-1])))
    assert len(out) == len(times)
    return out


def _daz(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


RESULTS: list[dict] = []


def _record(site, t, body, ref, got):
    rec = {"site": site, "utc": t.strftime("%Y-%m-%dT%H:%MZ"), "body": body,
           "horizons_az": ref[0], "horizons_el": ref[1], "lunascout_az": got[0], "lunascout_el": got[1],
           "d_az": round(_daz(ref[0], got[0]), 5), "d_el": round(abs(ref[1] - got[1]), 5)}
    RESULTS.append(rec)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"hours": [h.isoformat() for h in HOURS], "results": RESULTS}, indent=1))
    return rec


def test_known_shackleton_value_from_horizons():
    """Horizons itself still gives the value recorded in CONTEXT.md / CONTRACT.md."""
    (az, el), = horizons("10", SHACKLETON[0], SHACKLETON[1], (KNOWN,))
    assert abs(az - 133.339447) < 1e-5 and abs(el - 0.787435) < 1e-5


@pytest.mark.parametrize("site_name,site", [("dem_center", DEM_CENTER), ("athena_actual", ATHENA_ACTUAL)])
def test_api_matches_horizons(api, site_name, site):
    sun = horizons("10", site[0], site[1], tuple(HOURS))
    earth = horizons("399", site[0], site[1], tuple(HOURS))
    for t, s_ref, e_ref in zip(HOURS, sun, earth):
        ts = analyze(api, site[0], site[1], landing_utc=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     mission_days=1, ellipse=(300, 300, 0))["timeseries"]
        rs = _record(site_name, t, "sun", s_ref, (ts["sun_az_deg"][0], ts["sun_el_deg"][0]))
        re_ = _record(site_name, t, "earth", e_ref, (ts["earth_az_deg"][0], ts["earth_el_deg"][0]))
        assert rs["d_az"] <= SUN_TOL and rs["d_el"] <= SUN_TOL, rs
        assert re_["d_az"] <= EARTH_TOL and re_["d_el"] <= EARTH_TOL, re_


def test_shackleton_is_refused_by_api(api):
    r = analyze(api, *SHACKLETON, raw=True)
    assert r.status_code == 400 and r.json()["error"] == "out_of_coverage"


def test_shackleton_table_matches_horizons():
    """Outside the API coverage: LunaScout's table + local_az_el (pure geometry) vs Horizons."""
    sys.path.insert(0, str(REPO))
    try:
        from engine.ephemeris import load_ephemeris, local_az_el
    except Exception as e:  # pragma: no cover
        pytest.skip(f"engine.ephemeris not importable: {e}")
    E = load_ephemeris(str(REPO / "data/ephemeris/sun_earth_vectors.npz"))
    times = tuple(sorted(HOURS + [KNOWN]))   # Horizons returns TLIST epochs in time order
    sun = horizons("10", SHACKLETON[0], SHACKLETON[1], times)
    earth = horizons("399", SHACKLETON[0], SHACKLETON[1], times)
    for t, s_ref, e_ref in zip(times, sun, earth):
        i = int(np.searchsorted(E.t_unix, int(t.timestamp())))
        lat, lon = np.array([SHACKLETON[0]]), np.array([SHACKLETON[1]])
        saz, sel = local_az_el(E.sun_vec[i:i + 1], lat, lon)
        eaz, eel = local_az_el(E.earth_vec[i:i + 1], lat, lon)
        rs = _record("shackleton(table)", t, "sun", s_ref, (float(saz[0, 0]), float(sel[0, 0])))
        re_ = _record("shackleton(table)", t, "earth", e_ref, (float(eaz[0, 0]), float(eel[0, 0])))
        assert rs["d_az"] <= SUN_TOL and rs["d_el"] <= SUN_TOL, rs
        assert re_["d_az"] <= EARTH_TOL and re_["d_el"] <= EARTH_TOL, re_
