# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""
Verification of engine/ephemeris.py and data/ephemeris/sun_earth_vectors.npz against JPL Horizons.

Ground truth = real Horizons queries made directly at each test site (topocentric az/el). They are stored in
engine/tests/data/horizons_reference_points.json (created from Horizons on first run if missing) so the test
suite is offline-safe afterwards.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from engine.ephemeris import azel_to_vec, load_ephemeris, local_az_el, sun_disk_visible_fraction

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data" / "horizons_reference_points.json"
R_MOON_KM = 1737.4
START = datetime(2027, 1, 1, tzinfo=timezone.utc)
HOURS = 31 * 24
SITES = {  # name -> (lat, lon)
    "shackleton": (-89.67, 129.78),
    "ref_plus_15km": (-85.5, 31.0),        # ~15 km from the default reference (-85.0, 31.0)
    "ref_plus_24km": (-85.0, 40.0),        # ~24 km, different longitude
    "ref_plus_78km": (-85.0, 61.0),        # ~78 km
}


def _angdiff(a, b):
    return np.abs((np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0)


def _dist_km(p, q):
    la1, lo1, la2, lo2 = np.radians([*p, *q])
    v1 = np.array([np.cos(la1) * np.cos(lo1), np.cos(la1) * np.sin(lo1), np.sin(la1)])
    v2 = np.array([np.cos(la2) * np.cos(lo2), np.cos(la2) * np.sin(lo2), np.sin(la2)])
    return float(R_MOON_KM * np.arccos(np.clip(v1 @ v2, -1, 1)))


@pytest.fixture(scope="module")
def eph():
    return load_ephemeris()


@pytest.fixture(scope="module")
def ref(eph):
    return float(eph.meta["ref_lat"]), float(eph.meta["ref_lon"])


@pytest.fixture(scope="module")
def horizons_truth():
    if not DATA.exists():
        sys.path.insert(0, str(ROOT / "scripts"))
        from fetch_ephemeris import fetch_site_series
        stop = START + timedelta(hours=HOURS - 1)
        out = {}
        for name, (lat, lon) in SITES.items():
            out[name] = {"lat": lat, "lon": lon}
            for body in ("sun", "earth"):
                t, az, el = fetch_site_series(body, lat, lon, START, stop, chunk_months=1)
                out[name][body] = {"az": az.tolist(), "el": el.tolist()}
                out[name]["t0_unix"] = int(t[0])
                time.sleep(0.5)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps({"source": "JPL Horizons API (direct topocentric query per site)", "sites": out}))
    return json.loads(DATA.read_text())["sites"]


# --------------------------------------------------------------------------- known value
def test_shackleton_known_value(eph):
    """Contract value: Shackleton 2027-01-01 00:00 UT -> Sun az 133.339447, el 0.787435 (Horizons)."""
    t, sun, _ = eph.window(START, 1)
    az, el = local_az_el(sun, np.array([-89.67]), np.array([129.78]))
    print(f"\nShackleton via table: az={az[0, 0]:.6f} el={el[0, 0]:.6f} (Horizons: 133.339447, 0.787435)")
    assert _angdiff(az[0, 0], 133.339447) <= 0.01
    assert abs(el[0, 0] - 0.787435) <= 0.01


def test_table_vs_direct_horizons_by_distance(eph, ref, horizons_truth):
    print(f"\nreference site = {ref}")
    print(f"{'site':16s} {'dist km':>8s} | {'Sun max az err':>14s} {'Sun max el err':>14s} | {'Earth max az':>12s} {'Earth max el':>12s}")
    t, sun, earth = eph.window(START, HOURS)
    assert t[0] == horizons_truth["shackleton"]["t0_unix"]
    for name, site in horizons_truth.items():
        res = {}
        for body, vec in (("sun", sun), ("earth", earth)):
            az, el = local_az_el(vec, np.array([site["lat"]]), np.array([site["lon"]]))
            truth_az, truth_el = np.array(site[body]["az"]), np.array(site[body]["el"])
            # azimuth is ill-conditioned right at the pole; weight by cos(el) is unnecessary here (el << 90)
            res[body] = (_angdiff(az[0], truth_az).max(), np.abs(el[0] - truth_el).max())
        d = _dist_km(ref, (site["lat"], site["lon"]))
        print(f"{name:16s} {d:8.1f} | {res['sun'][0]:14.5f} {res['sun'][1]:14.5f} | {res['earth'][0]:12.5f} {res['earth'][1]:12.5f}")
        assert res["sun"][0] <= 0.01 and res["sun"][1] <= 0.01, f"Sun error at {name}"
        assert res["earth"][0] <= 0.05 and res["earth"][1] <= 0.05, f"Earth error at {name}"


# --------------------------------------------------------------------------- math
def test_round_trip():
    rng = np.random.default_rng(0)
    az = rng.uniform(0, 360, 500)
    el = rng.uniform(-30, 30, 500)
    for lat, lon in [(-85.0, 31.0), (-89.67, 129.78), (-80.0, -120.0)]:
        vec = azel_to_vec(az, el, lat, lon)
        az2, el2 = local_az_el(vec, np.array([lat]), np.array([lon]))
        assert _angdiff(az2[0], az).max() < 1e-9
        assert np.abs(el2[0] - el).max() < 1e-9


def test_vectors_are_unit(eph):
    assert np.allclose(np.linalg.norm(eph.sun_vec, axis=1), 1.0, atol=1e-12)
    assert np.allclose(np.linalg.norm(eph.earth_vec, axis=1), 1.0, atol=1e-12)


def test_table_shape_and_range(eph):
    assert len(eph.t_unix) == 35064
    assert eph.range_utc == (datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2028, 12, 31, 23, tzinfo=timezone.utc))
    assert np.all(np.diff(eph.t_unix) == 3600)


def test_window_semantics(eph):
    t, s, e = eph.window(datetime(2027, 3, 10, 14, 37, 12, tzinfo=timezone.utc), 168)   # rounds down to 14:00
    assert len(t) == len(s) == len(e) == 168
    assert datetime.fromtimestamp(int(t[0]), timezone.utc) == datetime(2027, 3, 10, 14, tzinfo=timezone.utc)
    eph.window(datetime(2028, 12, 31, 0, tzinfo=timezone.utc), 24)                       # last valid window
    with pytest.raises(ValueError):
        eph.window(datetime(2028, 12, 31, 0, tzinfo=timezone.utc), 25)
    with pytest.raises(ValueError):
        eph.window(datetime(2024, 12, 31, 23, tzinfo=timezone.utc), 1)


def test_performance_1000x1000(eph):
    rng = np.random.default_rng(1)
    lat, lon = rng.uniform(-86, -84, 1000), rng.uniform(28, 34, 1000)
    vec = eph.sun_vec[:1000]
    t0 = time.perf_counter()
    az, el = local_az_el(vec, lat, lon)
    dt = time.perf_counter() - t0
    print(f"\nlocal_az_el 1000x1000: {dt * 1000:.0f} ms")
    assert az.shape == el.shape == (1000, 1000)
    assert dt < 1.0


def test_sun_disk_fraction():
    assert sun_disk_visible_fraction(1.0, 0.0) == 1.0
    assert sun_disk_visible_fraction(-1.0, 0.0) == 0.0
    assert sun_disk_visible_fraction(0.0, 0.0) == pytest.approx(0.5)
    f = sun_disk_visible_fraction(np.array([0.1, 0.2]), 0.0)
    assert 0.5 < f[0] < f[1] < 1.0


# --------------------------------------------------------------------------- physics
def test_sun_max_elevation_matches_axial_tilt(eph, ref):
    """Max Sun elevation over a year ~ (90 - |lat|) + 1.54 deg."""
    lat, lon = ref
    _, el = local_az_el(eph.sun_vec, np.array([lat]), np.array([lon]))
    year = (eph.t_unix >= START.timestamp()) & (eph.t_unix < datetime(2028, 1, 1, tzinfo=timezone.utc).timestamp())
    expected = (90 - abs(lat)) + 1.54
    got = el[0][year].max()
    print(f"\nSun max elevation in 2027 at ref {ref}: {got:.3f} deg (expected ~{expected:.2f})")
    assert abs(got - expected) < 0.15


def test_earth_libration_period(eph, ref):
    """Earth elevation oscillates with the ~27.2-day libration-in-latitude period, azimuth never circles."""
    lat, lon = ref
    sl = slice(0, 24 * 365 * 2)                                              # 2025-2026
    az, el = local_az_el(eph.earth_vec[sl], np.array([lat]), np.array([lon]))
    az, el = az[0], el[0]
    x = el - el.mean()
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), d=1.0 / 24.0)                            # cycles per day
    k = spec[1:].argmax() + 1
    # parabolic interpolation of the spectral peak
    a, b, c = np.log(spec[k - 1:k + 2] + 1e-30)
    k_f = k + 0.5 * (a - c) / (a - 2 * b + c)
    period = 1.0 / (k_f * (freqs[1] - freqs[0]))
    amp = (el.max() - el.min()) / 2
    az_span = np.ptp(np.unwrap(np.radians(az)) * 180 / np.pi)
    print(f"\nEarth libration at ref: period={period:.2f} d, el range [{el.min():.2f}, {el.max():.2f}], "
          f"half-amplitude={amp:.2f}, unwrapped az span={az_span:.1f} deg")
    assert 26.5 < period < 28.0
    assert 5.0 < amp < 8.0
    assert az_span < 360.0, "Earth azimuth must not circle the sky"
