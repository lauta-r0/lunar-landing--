# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""analyze() / get_meta(): contract shape (CONTRACT 4.2-4.5) and physical sanity checks.

These tests use a synthetic DEM and the SYNTHETIC ephemeris stub (engine/_ephemeris_stub.py),
so they do not need the real data. Results produced here are not real.
"""
import json
import time

import numpy as np
import pytest

from engine import _ephemeris_stub as stub
from engine import analyze as az
from engine import geo, horizon
from engine.errors import EngineError
from engine.grid import HorizonGrid
from engine.tests.conftest import CENTER_XY, make_terrain, real_dem_available

CLASSES = {"viable", "risky", "not_viable"}
REASONS = {"slope", "darkness", "comms_gap", "earth_time", "sunset", "no_sun_at_touchdown", "low_sun_margin"}
METRIC_IDS = ["sun_at_touchdown", "sun_hours", "longest_dark", "min_sun_margin", "earth_pct", "longest_comm_gap",
              "hours_until_sunset", "hours_until_earthset", "area_over_slope", "delay_tolerance"]


def crater_terrain():
    """Flat plain with one bowl crater (300 m deep, 1.5 km radius) centered 2 km east of the center."""
    def fn(dist, brg):
        east = dist * np.sin(np.radians(brg))
        north = dist * np.cos(np.radians(brg))
        r = np.hypot(east - 2000.0, north)
        return np.where(r < 1500.0, -300.0 * (1.0 - (r / 1500.0) ** 2), 0.0)
    return make_terrain(fn, size_m=12000.0, pixel_m=10.0, slope_deg=3.0)


def build_grid(terrain, half_m=3000.0, spacing=200.0, h_obs=2.0) -> HorizonGrid:
    n = int(round(2 * half_m / spacing)) + 1
    x0, y0 = CENTER_XY[0] - half_m, CENTER_XY[1] - half_m
    xs = x0 + np.arange(n) * spacing
    ys = y0 + np.arange(n) * spacing
    xx, yy = np.meshgrid(xs, ys)
    elev, reach, z0 = horizon.compute_horizons_xy(xx.ravel(), yy.ravel(), h_obs, terrain)
    lat, lon = geo.xy_to_latlon(xx, yy)
    meta = {"nx": n, "ny": n, "x0": x0, "y0": y0, "spacing_m": spacing, "observer_height_m": h_obs, "n_az": 360}
    return HorizonGrid(meta, elev.reshape(n, n, 360).astype(np.float16), None, z0.reshape(n, n),
                       terrain.slope_at(xx, yy).astype(np.float32), lat, lon)


@pytest.fixture(scope="module")
def synthetic_parts():
    geo.configure(None)
    terrain = crater_terrain()
    return terrain, build_grid(terrain), stub.load_ephemeris_stub()


@pytest.fixture()
def engine_grid(synthetic_parts):
    terrain, grid, eph = synthetic_parts
    az.configure_engine(terrain=terrain, grid=grid, ephemeris=eph, local_az_el=stub.local_az_el, is_stub=True)
    yield
    az.reset_engine()


@pytest.fixture()
def engine_no_grid(synthetic_parts):
    terrain, _grid, eph = synthetic_parts
    az.configure_engine(terrain=terrain, grid=None, ephemeris=eph, local_az_el=stub.local_az_el, is_stub=True)
    yield
    az.reset_engine()


def center_request(**over):
    lat, lon = geo.xy_to_latlon(*CENTER_XY)
    req = {"target": {"lat": float(lat), "lon": float(lon)}, "landing_utc": "2027-03-10T14:00:00Z",
           "mission_days": 7, "ellipse": {"semi_major_m": 1000, "semi_minor_m": 600, "azimuth_deg": 0},
           "limits": {"max_dark_h": 50, "max_comm_gap_h": 72, "min_earth_pct": 50, "max_slope_deg": 8},
           "options": {"risk_margin": 0.2, "delay_days_max": 10, "include_recommendations": True,
                       "observer_height_m": 2.0}}
    req.update(over)
    return req


def check_contract_shape(r: dict, req: dict):
    """Keys, types and internal consistency required by CONTRACT 4.3."""
    json.dumps(r)                                              # JSON-serializable, no numpy types
    for key in ["schema_version", "is_sample", "computed_utc", "compute_ms", "inputs", "coverage", "target",
                "summary", "target_metrics", "points", "timeseries", "horizon_profile", "delay_curve",
                "delay_tolerance_days", "recommendations", "map", "warnings", "sources"]:
        assert key in r, key
    assert r["schema_version"] == "1.3" and isinstance(r["is_sample"], bool)
    assert r["computed_utc"].endswith("Z") and isinstance(r["compute_ms"], int)
    assert r["coverage"]["in_coverage"] is True and isinstance(r["coverage"]["dem_name"], str)
    for key in ["lat", "lon", "x_m", "y_m", "elevation_m", "slope_deg"]:
        assert isinstance(r["target"][key], float), key

    mission_h = r["inputs"]["mission_days"] * 24
    s = r["summary"]
    assert s["n_points"] == len(r["points"]) == s["viable"] + s["risky"] + s["not_viable"] > 0
    assert s["survival_probability"] == round(s["viable"] / s["n_points"], 3)
    assert s["survival_probability_incl_risky"] == round((s["viable"] + s["risky"]) / s["n_points"], 3)
    assert s["verdict"] in CLASSES
    assert s["checks_total"] == 7 and 0 <= s["checks_passed"] <= 7

    assert [m["id"] for m in r["target_metrics"]] == METRIC_IDS
    for m in r["target_metrics"]:
        assert set(m) == {"id", "label", "value", "unit", "display", "limit_display", "pass"}
        assert m["pass"] in (True, False, None) and isinstance(m["display"], str)
    assert sum(m["pass"] is not None for m in r["target_metrics"]) == s["checks_total"]
    assert sum(m["pass"] is True for m in r["target_metrics"]) == s["checks_passed"]
    by_id = {m["id"]: m for m in r["target_metrics"]}
    assert by_id["hours_until_earthset"]["pass"] is None and by_id["delay_tolerance"]["pass"] is None

    counts = {c: 0 for c in CLASSES}
    for i, p in enumerate(r["points"]):
        assert p["id"] == i
        assert p["class"] in CLASSES and set(p["reasons"]) <= REASONS
        assert (p["class"] == "viable") == (p["reasons"] == [])
        assert isinstance(p["sun_at_touchdown"], bool)
        assert isinstance(p["slope_coarse"], bool) and p["slope_dem_m"] > 0     # extra fields (CONTRACT 1.1)
        assert 0 <= p["sun_hours"] <= mission_h and 0 <= p["longest_dark_h"] <= mission_h
        assert 0 <= p["earth_pct"] <= 100 and 0 <= p["hours_until_sunset"] <= mission_h
        assert -90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180
        counts[p["class"]] += 1
    assert (counts["viable"], counts["risky"], counts["not_viable"]) == (s["viable"], s["risky"], s["not_viable"])

    ts = r["timeseries"]
    assert ts["n"] == mission_h and ts["step_h"] == 1 and ts["t0_utc"] == r["inputs"]["landing_utc"]
    for key in ["sun_az_deg", "sun_el_deg", "horizon_at_sun_deg", "sun_lit",
                "earth_az_deg", "earth_el_deg", "horizon_at_earth_deg", "earth_visible",
                "sun_visible_fraction", "sun_margin_deg"]:
        assert len(ts[key]) == mission_h, key
    # v1.2: margin = Sun elevation - horizon at the Sun; the target metric is its minimum over lit hours
    for e, h, mg in zip(ts["sun_el_deg"], ts["horizon_at_sun_deg"], ts["sun_margin_deg"]):
        assert abs((e - h) - mg) < 0.002
    lit_margins = [mg for mg, lt in zip(ts["sun_margin_deg"], ts["sun_lit"]) if lt]
    if lit_margins:
        assert abs(by_id["min_sun_margin"]["value"] - min(lit_margins)) < 0.002
    else:
        assert by_id["min_sun_margin"]["value"] is None
    assert by_id["min_sun_margin"]["pass"] is None               # v1.3: margin 0 -> informative only
    assert set(ts["sun_lit"]) <= {0, 1} and set(ts["earth_visible"]) <= {0, 1}
    assert all(0 <= a < 360.0001 for a in ts["sun_az_deg"])
    lit = [int(e > h) for e, h in zip(ts["sun_el_deg"], ts["horizon_at_sun_deg"])]
    assert sum(a != c for a, c in zip(lit, ts["sun_lit"])) <= 2          # equal up to rounding at the limb
    assert by_id["sun_hours"]["value"] == float(sum(ts["sun_lit"]))

    hp = r["horizon_profile"]
    assert hp["az_step_deg"] == 1.0 and len(hp["elevation_deg"]) == 360

    n_delay = r["inputs"]["options"]["delay_days_max"]
    assert [d["delay_days"] for d in r["delay_curve"]] == list(range(n_delay + 1))
    assert r["delay_curve"][0]["survival_probability"] == s["survival_probability"]
    assert r["delay_curve"][0]["target_viable"] == (s["verdict"] != "not_viable")
    tol = -1
    for d in r["delay_curve"]:
        if not d["target_viable"]:
            break
        tol = d["delay_days"]
    assert r["delay_tolerance_days"] == tol == by_id["delay_tolerance"]["value"]

    assert len(r["recommendations"]) <= 3
    probs = [rec["survival_probability"] for rec in r["recommendations"]]
    assert probs == sorted(probs, reverse=True)
    for rec in r["recommendations"]:
        assert rec["distance_km"] <= az.REC_MAX_CURATED_KM
        assert set(rec) == {"name", "lat", "lon", "distance_km", "survival_probability", "delta_pts"}
        assert rec["survival_probability"] > s["survival_probability"]

    mp = r["map"]
    assert len(mp["ellipse_polygon_xy_m"]) == 72 and len(mp["hillshade_bounds_xy_m"]) == 4
    x0, y0, x1, y1 = mp["view_bounds_xy_m"]
    assert x1 - x0 >= 5000.0 - 1e-6 and abs((x1 - x0) / (y1 - y0) - 1.5) < 1e-3
    assert abs((x0 + x1) / 2 - r["target"]["x_m"]) < 0.2 and abs((y0 + y1) / 2 - r["target"]["y_m"]) < 0.2
    for px, py in mp["ellipse_polygon_xy_m"]:
        assert x0 <= px <= x1 and y0 <= py <= y1
    assert isinstance(r["warnings"], list) and len(r["sources"]) in (2, 3)     # 3 with the regional DEM


def test_contract_shape_grid_mode(engine_grid):
    req = center_request()
    r = az.analyze(req)
    check_contract_shape(r, req)
    assert r["is_sample"] is True                              # stub ephemeris -> never presented as real
    assert any("SYNTHETIC EPHEMERIS" in w for w in r["warnings"])
    assert not any("on the fly" in w for w in r["warnings"])
    assert r["summary"]["n_points"] >= 40


def test_contract_shape_on_the_fly_small_ellipse(engine_grid):
    req = center_request(ellipse={"semi_major_m": 120, "semi_minor_m": 80, "azimuth_deg": 30})
    r = az.analyze(req)
    check_contract_shape(r, req)
    assert any("Small ellipse" in w for w in r["warnings"])
    assert 40 <= r["summary"]["n_points"] <= 120


def test_runs_without_grid(engine_no_grid):
    req = center_request(options={"delay_days_max": 3, "include_recommendations": True})
    r = az.analyze(req)
    check_contract_shape(r, req)
    assert r["recommendations"] == []
    assert any("grid" in w for w in r["warnings"])


def test_options_are_optional_and_defaults_apply(engine_grid):
    lat, lon = geo.xy_to_latlon(*CENTER_XY)
    r = az.analyze({"target": {"lat": float(lat), "lon": float(lon)}})
    assert r["inputs"]["mission_days"] == 7 and r["inputs"]["options"]["delay_days_max"] == 30
    assert r["inputs"]["landing_utc"] == "2027-10-12T14:00:00Z"
    assert len(r["delay_curve"]) == 31


def test_meta_shape(engine_grid):
    meta = az.get_meta()
    json.dumps(meta)
    assert set(meta) == {"schema_version", "coverage", "ephemeris_range_utc", "map", "curated_sites",
                         "defaults", "input_limits"}
    cov = meta["coverage"]
    assert len(cov["bounds_xy_m"]) == 4 and cov["approx_bounds_latlon"]["lat_min"] < cov["approx_bounds_latlon"]["lat_max"]
    assert abs(cov["center_lat"] + 85.42658) < 1e-4 and abs(cov["center_lon"] - 31.74276) < 1e-4
    assert meta["ephemeris_range_utc"] == ["2025-01-01T00:00:00Z", "2028-12-31T23:00:00Z"]
    assert meta["curated_sites"][0]["id"] == "mons_mouton_center"
    assert meta["defaults"]["limits"] == {"max_dark_h": 50, "max_comm_gap_h": 72, "min_earth_pct": 50, "max_slope_deg": 8,
                                          "min_sun_margin_deg": 0}
    assert "min_sun_margin_auto_deg" not in meta["defaults"]     # v1.3: real data only, no automatic margin
    assert meta["map"]["hillshade_url"] == "/api/static/hillshade.png" and "+proj=stere" in meta["map"]["crs_proj4"]


def test_errors(engine_grid):
    with pytest.raises(EngineError) as e:
        az.analyze(center_request(target={"lat": -80.0, "lon": 10.0}))
    assert e.value.code == "out_of_coverage" and "suggested_target" in e.value.extra
    assert set(e.value.to_dict()) == {"error", "message", "suggested_target"}

    # target inside, but most of a huge ellipse outside the grid area
    with pytest.raises(EngineError) as e:
        az.analyze(center_request(ellipse={"semi_major_m": 5000, "semi_minor_m": 5000, "azimuth_deg": 0}))
    assert e.value.code == "out_of_coverage"

    with pytest.raises(EngineError) as e:
        az.analyze(center_request(landing_utc="2029-06-01T00:00:00Z"))
    assert e.value.code == "out_of_ephemeris_range"
    with pytest.raises(EngineError) as e:           # the delay range must fit too
        az.analyze(center_request(landing_utc="2028-12-20T00:00:00Z"))
    assert e.value.code == "out_of_ephemeris_range"

    for bad in [{"mission_days": 0}, {"mission_days": 2.5}, {"landing_utc": "yesterday"},
                {"limits": {"max_slope_deg": 90}}, {"target": {"lat": "x", "lon": 3}}]:
        with pytest.raises(EngineError) as e:
            az.analyze(center_request(**bad))
        assert e.value.code == "invalid_request"


def test_crater_floor_is_darker_than_the_plain(engine_grid):
    """Physical sanity: inside the bowl the rim hides the low Sun; the open plain sees it."""
    small = {"semi_major_m": 150, "semi_minor_m": 150, "azimuth_deg": 0}
    lat0, lon0 = (float(v) for v in geo.xy_to_latlon(*CENTER_XY))
    floor_lat, floor_lon = (float(v) for v in geo.destination(lat0, lon0, 90.0, 2000.0))
    plain_lat, plain_lon = (float(v) for v in geo.destination(lat0, lon0, 270.0, 2000.0))
    opts = {"delay_days_max": 0, "include_recommendations": False}
    floor = az.analyze(center_request(target={"lat": floor_lat, "lon": floor_lon}, ellipse=small, options=opts))
    plain = az.analyze(center_request(target={"lat": plain_lat, "lon": plain_lon}, ellipse=small, options=opts))
    sun = lambda r: {m["id"]: m for m in r["target_metrics"]}["sun_hours"]["value"]   # noqa: E731
    assert floor["target"]["elevation_m"] < -290.0 and abs(plain["target"]["elevation_m"]) < 1.0
    assert sun(plain) > sun(floor)
    assert min(floor["horizon_profile"]["elevation_deg"]) > 5.0      # rim all around
    assert max(plain["horizon_profile"]["elevation_deg"]) < 0.5


def test_sun_elevation_bound_and_date_dependence(engine_grid):
    r1 = az.analyze(center_request(mission_days=30, options={"delay_days_max": 0, "include_recommendations": False}))
    lat = r1["target"]["lat"]
    assert max(r1["timeseries"]["sun_el_deg"]) <= (90.0 - abs(lat)) + 1.54 + 0.01
    r2 = az.analyze(center_request(landing_utc="2027-06-20T03:00:00Z"))
    r3 = az.analyze(center_request())
    assert r2["timeseries"]["sun_az_deg"] != r3["timeseries"]["sun_az_deg"]


def test_ellipse_azimuth_is_relative_to_local_north(engine_grid):
    """A long thin ellipse with azimuth 0 must be elongated along local north (lat changes, lon does not)."""
    req = center_request(ellipse={"semi_major_m": 2000, "semi_minor_m": 300, "azimuth_deg": 0},
                         options={"delay_days_max": 0, "include_recommendations": False})
    r = az.analyze(req)
    lats = np.array([p["lat"] for p in r["points"]])
    lons = np.array([p["lon"] for p in r["points"]])
    north_span_m = np.ptp(lats) * np.pi / 180.0 * geo.R_MOON
    east_span_m = np.ptp(lons) * np.pi / 180.0 * geo.R_MOON * np.cos(np.radians(lats.mean()))
    assert north_span_m > 3000.0 and east_span_m < 700.0
    r90 = az.analyze(dict(req, ellipse={"semi_major_m": 2000, "semi_minor_m": 300, "azimuth_deg": 90}))
    lats = np.array([p["lat"] for p in r90["points"]])
    assert np.ptp(lats) * np.pi / 180.0 * geo.R_MOON < 700.0


def test_identical_requests_are_cached(engine_grid):
    req = center_request()
    a = az.analyze(req)
    t0 = time.perf_counter()
    b = az.analyze(req)
    assert (time.perf_counter() - t0) < 0.2 and a == b
    b["points"].clear()                                         # callers cannot corrupt the cache
    assert az.analyze(req)["points"]


@pytest.mark.skipif(not real_dem_available(), reason="real DEM not downloaded")
def test_real_dem_default_request_shape_and_speed():
    """Real DEM + (if present) real grid. Ephemeris: the real one if available, else the labeled stub."""
    import os
    from engine.grid import load_grid
    from engine.terrain import load_terrain, set_terrain
    os.environ.setdefault("LUNASCOUT_ALLOW_STUB", "1")
    set_terrain(load_terrain())
    az.reset_engine()
    try:
        meta = az.get_meta()
        req = {"target": {"lat": meta["curated_sites"][0]["lat"], "lon": meta["curated_sites"][0]["lon"]}}
        az.analyze(dict(req, mission_days=6))                   # warm-up (page cache, imports)
        t0 = time.perf_counter()
        r = az.analyze(req)
        dt = time.perf_counter() - t0
        check_contract_shape(r, req)
        print(f"\nreal DEM default request: {dt * 1000:.0f} ms, grid={'yes' if load_grid() else 'no'}, "
              f"points={r['summary']['n_points']}, P={r['summary']['survival_probability']}")
        if load_grid() is not None:
            assert dt < 3.0
    finally:
        az.reset_engine()
        set_terrain(None)
        geo.configure(None)


def test_concurrent_analyze(engine_grid):
    """analyze() is safe to call from several threads (thread-safe LRU caches)."""
    from concurrent.futures import ThreadPoolExecutor
    reqs = [center_request(mission_days=2 + (i % 3)) for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(az.analyze, reqs))
    for req, res in zip(reqs, results):
        assert res["inputs"]["mission_days"] == req["mission_days"]
        assert az.analyze(req)["summary"] == res["summary"]
