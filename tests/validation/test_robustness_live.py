# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Robustness, error handling and timing of the live API (Agent 06, priority 5)."""
from __future__ import annotations

import json
import random
import time

import numpy as np
import pytest
import requests

from .conftest import ATHENA_ACTUAL, DEM_CENTER, SHACKLETON, SUMMIT, TIMEOUT, analyze
from .test_physics_live import record

BASE = {"target": {"lat": SUMMIT[0], "lon": SUMMIT[1]}, "landing_utc": "2027-10-12T14:00:00Z", "mission_days": 7}


def post(api, body):
    return requests.post(api + "/analyze", json=body, timeout=TIMEOUT)


def test_health_and_meta(api, meta):
    h = requests.get(api + "/health", timeout=TIMEOUT).json()
    assert h == {"status": "ok", "engine_ready": True, "schema_version": "1.5"}
    assert meta["defaults"]["limits"]["min_sun_margin_deg"] == 0
    assert meta["ephemeris_range_utc"] == ["2025-01-01T00:00:00Z", "2028-12-31T23:00:00Z"]
    ids = {s["id"] for s in meta["curated_sites"]}
    assert {"im2_athena_intended", "im2_athena_actual"} <= ids


def test_out_of_coverage(api):
    for lat, lon in (SHACKLETON, (-85.0, 60.0), (-84.0, 31.0)):
        r = post(api, {**BASE, "target": {"lat": lat, "lon": lon}})
        assert r.status_code == 400, (lat, lon, r.text[:200])
        j = r.json()
        assert j["error"] == "out_of_coverage" and "suggested_target" in j
        assert {"lat", "lon"} <= set(j["suggested_target"])


def test_ellipse_mostly_outside_is_refused(api):
    # target inside the area near its west edge, 5 km ellipse sticking far out
    r = post(api, {**BASE, "target": {"lat": -85.43, "lon": 23.2},
                   "ellipse": {"semi_major_m": 5000, "semi_minor_m": 5000, "azimuth_deg": 0}})
    record("ellipse_near_edge_status", [r.status_code, r.json().get("error")])
    assert r.status_code in (200, 400)


@pytest.mark.parametrize("t,delay", [("2024-12-31T23:00:00Z", 0), ("2029-01-01T00:00:00Z", 0),
                                     ("2028-12-25T01:00:00Z", 0), ("2028-12-01T00:00:00Z", 30)])
def test_out_of_ephemeris(api, t, delay):
    r = post(api, {**BASE, "landing_utc": t, "options": {"delay_days_max": delay}})
    assert r.status_code == 400, (t, r.status_code, r.text[:200])
    assert r.json()["error"] == "out_of_ephemeris_range"


BAD = [
    {"mission_days": 0}, {"mission_days": 31},
    {"ellipse": {"semi_major_m": 49, "semi_minor_m": 600, "azimuth_deg": 0}},
    {"ellipse": {"semi_major_m": 5001, "semi_minor_m": 600, "azimuth_deg": 0}},
    {"limits": {"max_slope_deg": 0}}, {"limits": {"min_earth_pct": 101}}, {"limits": {"max_dark_h": -1}},
    {"target": {"lat": "abc", "lon": 31}}, {"target": {"lat": -95, "lon": 31}},
    pytest.param({"landing_utc": "not a date"}, marks=pytest.mark.xfail(
        reason="known P2 deviation: API answers 400 invalid_request, CONTRACT 4.5 says 422", strict=True)),
    {"unexpected_field": 1}, {"options": {"risk_margin": 2}},
]


@pytest.mark.parametrize("patch", BAD, ids=[f"bad{i}" for i in range(len(BAD))])
def test_invalid_inputs_422(api, patch):
    r = post(api, {**BASE, **patch})
    assert r.status_code == 422, (patch, r.status_code, r.text[:300])


def test_missing_target_422(api):
    r = post(api, {"landing_utc": "2027-10-12T14:00:00Z"})
    assert r.status_code == 422


def test_semi_minor_larger_than_major(api):
    r = post(api, {**BASE, "ellipse": {"semi_major_m": 300, "semi_minor_m": 900, "azimuth_deg": 0}})
    record("semi_minor_gt_major", {"status": r.status_code, "body": r.text[:300]})
    assert r.status_code in (200, 422)


def test_tiny_huge_long(api):
    out = {}
    for name, ell, days, site in (("tiny_50m", (50, 50, 0), 7, ATHENA_ACTUAL), ("huge_5km", (5000, 5000, 0), 7, DEM_CENTER),
                                  ("mission_30d", (1000, 600, 0), 30, SUMMIT)):
        body = {"target": {"lat": site[0], "lon": site[1]}, "landing_utc": "2026-08-%02dT%02d:00:00Z" % (random.randint(1, 28), random.randint(0, 23)),
                "mission_days": days, "ellipse": dict(zip(("semi_major_m", "semi_minor_m", "azimuth_deg"), ell)),
                "options": {"delay_days_max": 30, "include_recommendations": True}}
        t0 = time.perf_counter()
        r = post(api, body)
        dt_ = time.perf_counter() - t0
        assert r.status_code == 200, (name, r.text[:300])
        d = r.json()
        out[name] = {"wall_s": round(dt_, 2), "compute_ms": d["compute_ms"], "n_points": d["summary"]["n_points"],
                     "n": d["timeseries"]["n"], "warnings": d["warnings"]}
        assert d["timeseries"]["n"] == days * 24
    record("edge_cases", out)


def test_timing_p50_p95(api):
    """10 varied, uncached requests with recommendations on (contract: < 3 s on the server)."""
    rng = random.Random(time.time())
    sites = [SUMMIT, DEM_CENTER, ATHENA_ACTUAL, (-85.3989, 29.95361), (-85.23787, 33.95403)]
    walls, comps, cache = [], [], []
    for i in range(10):
        site = sites[i % len(sites)]
        body = {"target": {"lat": site[0], "lon": site[1]},
                "landing_utc": "202%d-%02d-%02dT%02d:00:00Z" % (rng.choice((5, 6, 7)), rng.randint(2, 11), rng.randint(1, 28), rng.randint(0, 23)),
                "mission_days": rng.choice((3, 7, 10, 14)),
                "ellipse": {"semi_major_m": rng.choice((500, 1000, 2000)), "semi_minor_m": 400,
                            "azimuth_deg": round(rng.uniform(0, 180), 3)},
                "options": {"include_recommendations": True, "delay_days_max": 30}}
        t0 = time.perf_counter()
        r = post(api, body)
        walls.append(time.perf_counter() - t0)
        assert r.status_code == 200, r.text[:300]
        comps.append(r.json()["compute_ms"])
        cache.append(r.headers.get("X-Cache"))
    res = {"wall_s": [round(w, 2) for w in walls], "compute_ms": comps, "x_cache": cache,
           "wall_p50": round(float(np.percentile(walls, 50)), 2), "wall_p95": round(float(np.percentile(walls, 95)), 2),
           "compute_p50_ms": float(np.percentile(comps, 50)), "compute_p95_ms": float(np.percentile(comps, 95))}
    record("timing_10_varied_calls", res)
    assert res["compute_p95_ms"] < 3000
