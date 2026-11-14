# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Synthetic tests of the horizon algorithm (analytic answers known in advance)."""
import time

import numpy as np
import pytest

from engine import geo, horizon
from engine.geo import R_MOON
from engine.tests.conftest import CENTER_XY, make_terrain, real_dem_available

H_OBS = 2.0


def test_flat_sphere_dip():
    """All heights 0: the horizon is the smooth-sphere dip, -acos(R/(R+h)) = -0.0869 deg for 2 m."""
    t = make_terrain()
    h = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, t)
    expected = -np.degrees(np.arccos(R_MOON / (R_MOON + H_OBS)))
    assert abs(expected + 0.0869) < 1e-3
    assert h.elevation_deg.shape == (360,)
    assert np.max(np.abs(h.elevation_deg - expected)) < 2e-4


def test_flat_sphere_other_heights():
    t = make_terrain()
    for h_obs in (0.5, 10.0):
        h = horizon.compute_horizon_xy(*CENTER_XY, h_obs, t)
        expected = -np.degrees(np.arccos(R_MOON / (R_MOON + h_obs)))
        assert np.max(np.abs(h.elevation_deg - expected)) < 5e-4


def wall_angle_deg(H, D, h_obs=H_OBS):
    return np.degrees(np.arctan2(H - h_obs - D ** 2 / (2.0 * R_MOON), D))


def test_ring_wall():
    """A cliff of height H at distance D all around: horizon = atan2(H - h - D^2/2R, D)."""
    H, D = 200.0, 2000.0
    t = make_terrain(lambda dist, brg: np.where(dist >= D, H, 0.0), size_m=8000.0, pixel_m=5.0)
    expected = wall_angle_deg(H, D)                 # about 5.62 deg
    # default sampling: within ~1.5% of the angle, never above the analytic value
    h = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, t)
    assert np.all(h.elevation_deg <= expected + 1e-6)
    assert np.max(np.abs(h.elevation_deg - expected)) < 0.1
    # finer sampling converges to the analytic value
    hf = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, t, ds_min=1.0, growth=0.001)
    assert np.max(np.abs(hf.elevation_deg - expected)) < 0.03


def test_far_wall_curvature_term():
    """At 5 km the curvature drop D^2/2R is 7.2 m; the result must include it."""
    H, D = 60.0, 5000.0
    t = make_terrain(lambda dist, brg: np.where(dist >= D, H, 0.0), size_m=11000.0, pixel_m=5.0)
    hf = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, t, ds_min=1.0, growth=0.001)
    with_curv = wall_angle_deg(H, D)
    without_curv = np.degrees(np.arctan2(H - H_OBS, D))
    assert without_curv - with_curv > 0.08
    assert np.max(np.abs(hf.elevation_deg - with_curv)) < 0.01


def test_wall_to_the_east_checks_azimuth_convention():
    """A wall only toward local east (bearing 60..120): azimuth is clockwise from north."""
    H, D = 300.0, 1500.0

    def fn(dist, brg):
        return np.where((dist >= D) & (brg >= 60.0) & (brg <= 120.0), H, 0.0)

    t = make_terrain(fn, size_m=8000.0, pixel_m=5.0)
    h = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, t)
    flat = horizon.flat_horizon_deg(H_OBS)
    assert abs(h.elevation_deg[90] - wall_angle_deg(H, D)) < 0.2
    assert abs(h.elevation_deg[270] - flat) < 1e-3
    assert abs(h.elevation_deg[0] - flat) < 1e-3
    assert abs(h.elevation_deg[180] - flat) < 1e-3
    assert np.all(h.elevation_deg[65:116] > 5.0)
    assert np.all(h.elevation_deg[125:360] < 0.0) and np.all(h.elevation_deg[0:55] < 0.0)


def test_symmetric_crater_is_azimuth_independent():
    """At the center of a radially symmetric bowl the horizon does not depend on azimuth."""
    depth, radius = 300.0, 3000.0
    t = make_terrain(lambda dist, brg: depth * np.minimum(dist / radius, 1.0) ** 2,
                     size_m=10000.0, pixel_m=5.0)
    h = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, t)
    # beyond 1 km the DEM is read at the nearest 5 m pixel, which adds up to ~0.01 deg of noise here
    assert np.ptp(h.elevation_deg) < 0.03
    # with bilinear sampling all the way, the result is azimuth-independent to 0.01 deg
    hb = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, t, near_m=1e9)
    assert np.ptp(hb.elevation_deg) < 0.01
    # the rim (300 m high at 3 km) is the skyline
    assert abs(np.mean(h.elevation_deg) - wall_angle_deg(depth, radius)) < 0.05


def test_reach_is_distance_to_dem_edge():
    t = make_terrain(size_m=12000.0, pixel_m=10.0)
    h = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, t)
    # from the center of a 12 km square: 6 km to the sides, 8.5 km to the corners (within one step)
    assert 5800.0 < h.reach_m.min() < 6100.0
    assert 8200.0 < h.reach_m.max() < 8600.0
    # off-center observer: the reach toward the near edge is short
    h2 = horizon.compute_horizon_xy(CENTER_XY[0] + 5000.0, CENTER_XY[1], H_OBS, t)
    assert h2.reach_m.min() < 1100.0


def test_observer_outside_dem_raises():
    t = make_terrain(size_m=4000.0)
    with pytest.raises(ValueError):
        horizon.compute_horizon_xy(CENTER_XY[0] + 5000.0, CENTER_XY[1], H_OBS, t)


def test_interp_horizon_wraps():
    hor = np.zeros((1, 360))
    hor[0, 359] = 2.0
    hor[0, 0] = 4.0
    out = horizon.interp_horizon(hor, np.array([[359.5, 0.0, 359.0, 0.25, 720.0, -0.5]]))
    assert np.allclose(out, [[3.0, 4.0, 2.0, 3.0, 4.0, 3.0]])


def test_sample_distances_spacing():
    s = horizon.sample_distances(37000.0)
    assert s[0] == horizon.S0_M and s[-1] >= 37000.0
    assert 300 <= s.size <= 700
    steps = np.diff(s)
    assert np.all(steps >= horizon.DS_MIN_M - 1e-9)
    assert np.all(steps <= np.maximum(horizon.DS_MIN_M, horizon.GROWTH * s[1:]) + 1e-6)


def test_many_observers_and_speed():
    t = make_terrain(lambda dist, brg: 50.0 * np.sin(dist / 400.0), size_m=12000.0, pixel_m=10.0)
    xs = CENTER_XY[0] + np.array([0.0, 100.0, -250.0])
    ys = CENTER_XY[1] + np.array([0.0, 50.0, 300.0])
    elev, reach, z0 = horizon.compute_horizons_xy(xs, ys, H_OBS, t)
    assert elev.shape == (3, 360) and reach.shape == (3, 360) and z0.shape == (3,)
    single = horizon.compute_horizon_xy(xs[1], ys[1], H_OBS, t)
    assert np.allclose(elev[1], single.elevation_deg, atol=1e-5)


@pytest.mark.skipif(not real_dem_available(), reason="real DEM not downloaded (scripts/prepare_dem.py)")
def test_real_dem_speed_and_sanity():
    from engine.terrain import load_terrain
    t = load_terrain(with_slope=False)
    cx, cy = t.center_xy
    horizon.compute_horizon_xy(cx, cy, H_OBS, t)          # warm-up
    t0 = time.perf_counter()
    n = 10
    for i in range(n):
        h = horizon.compute_horizon_xy(cx + 37.0 * i, cy - 53.0 * i, H_OBS, t)
    ms = (time.perf_counter() - t0) * 1000.0 / n
    print(f"\nreal DEM: {ms:.1f} ms per observer")
    assert ms < 150.0                                      # target is < 30 ms; generous for slow CI
    assert np.all(np.isfinite(h.elevation_deg))
    assert -30.0 < h.elevation_deg.min() and h.elevation_deg.max() < 60.0   # plateau top looks down
    assert h.reach_m.min() > 12000.0                       # center of a 26 km DEM
    geo.configure(None)
