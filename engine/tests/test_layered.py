# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Two-level terrain (fine tile + coarse regional DEM) and the multi-grid sampler, on synthetic data."""
import numpy as np
import pytest

from engine import geo, horizon
from engine.geo import R_MOON
from engine.grid import GridSet, HorizonGrid
from engine.terrain import LayeredTerrain, Terrain, load_terrain
from engine.tests.conftest import CENTER_XY, make_terrain, real_dem_available

H_OBS = 2.0


def coarse_terrain(height_fn, size_m=80000.0, pixel_m=40.0, z_scale=1.0, z_offset=0.0, as_int16=False):
    t = make_terrain(height_fn, size_m=size_m, pixel_m=pixel_m)
    surf = t.surf
    if as_int16:
        surf = np.rint(surf / z_scale).astype(np.int16)
    return Terrain(surf, t.slp, x_min=t.x_min, y_max=t.y_max, pixel_m=pixel_m, z_scale=z_scale,
                   z_offset=z_offset, name="coarse", role="far")


def test_finest_level_wins_and_seam_is_blended():
    fine = make_terrain(lambda d, b: np.full_like(d, 100.0), size_m=10000.0, pixel_m=10.0)
    coarse = coarse_terrain(lambda d, b: np.zeros_like(d), size_m=40000.0, pixel_m=40.0)
    lt = LayeredTerrain([fine, coarse], blend_m=500.0)
    cx, cy = CENTER_XY
    assert lt.height_at(cx, cy) == pytest.approx(100.0)                 # deep inside the fine tile
    assert lt.height_at(cx + 8000.0, cy) == pytest.approx(0.0)          # only the coarse level
    # across the fine tile's east edge (cx + 5000) the height ramps from 100 to 0 over 500 m
    xs = cx + np.linspace(4000.0, 5200.0, 121)
    z = lt.height_at(xs, np.full(xs.size, cy))
    assert np.all(np.isfinite(z))
    assert np.all(np.diff(z) <= 1e-6)                                    # monotone, no step
    assert z[0] == pytest.approx(100.0) and z[-1] == pytest.approx(0.0)
    mid = lt.height_at(cx + 4750.0, cy)                                  # 250 m inside the edge
    assert 40.0 < mid < 60.0
    # nearest-pixel reads (far ray samples) use the finest level, no blending
    assert lt.height_nearest(np.array([cx + 4990.0]), np.array([cy]))[0] == pytest.approx(100.0)
    assert lt.height_nearest(np.array([cx + 5010.0]), np.array([cy]))[0] == pytest.approx(0.0)
    assert list(lt.layer_index_at(np.array([cx, cx + 8000.0, cx + 30000.0]), np.full(3, cy))) == [0, 1, -1]


def test_int16_level_with_scale_and_vertical_correction():
    coarse = coarse_terrain(lambda d, b: np.full_like(d, 1234.5), size_m=4000.0, pixel_m=40.0,
                            z_scale=0.5, z_offset=-2.0, as_int16=True)
    assert coarse.surf.dtype == np.int16
    assert coarse.height_at(*CENTER_XY) == pytest.approx(1232.5)
    assert coarse.height_nearest(np.array([CENTER_XY[0]]), np.array([CENTER_XY[1]]))[0] == pytest.approx(1232.5)


def test_far_field_wall_is_seen_only_with_the_regional_level():
    """A 3 km wall 40 km away, present only in the coarse DEM, must raise the horizon."""
    H, D = 3000.0, 40000.0
    fine = make_terrain(None, size_m=10000.0, pixel_m=10.0)
    coarse = coarse_terrain(lambda d, b: np.where(d >= D, H, 0.0), size_m=100000.0, pixel_m=40.0)
    alone = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, fine)
    both = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, LayeredTerrain([fine, coarse]))
    expected = np.degrees(np.arctan2(H - H_OBS - D ** 2 / (2.0 * R_MOON), D))     # ~3.6 deg
    assert alone.elevation_deg.max() < 0.0
    assert np.all(np.abs(both.elevation_deg - expected) < 0.15)
    assert both.reach_m.min() > 45000.0


def test_rays_stop_at_max_ray():
    fine = make_terrain(None, size_m=10000.0, pixel_m=10.0)
    coarse = coarse_terrain(lambda d, b: np.zeros_like(d), size_m=300000.0, pixel_m=200.0)
    h = horizon.compute_horizon_xy(*CENTER_XY, H_OBS, LayeredTerrain([fine, coarse]))
    assert h.reach_m.max() <= horizon.MAX_RAY_M * 1.011


def _grid(x0, y0, nx, ny, spacing):
    xs, ys = x0 + np.arange(nx) * spacing, y0 + np.arange(ny) * spacing
    xx, yy = np.meshgrid(xs, ys)
    lat, lon = geo.xy_to_latlon(xx, yy)
    meta = {"nx": nx, "ny": ny, "x0": x0, "y0": y0, "spacing_m": spacing, "observer_height_m": 2.0, "n_az": 4}
    return HorizonGrid(meta, np.zeros((ny, nx, 4), np.float16), None, np.zeros((ny, nx), np.float32),
                       np.full((ny, nx), spacing, np.float32), lat, lon)


def test_gridset_uses_one_spacing_across_the_seam():
    """Fine 50 m grid below y = 0, coarse 100 m grid above: a box straddling the seam is sampled at
    100 m on both sides, so the point density (and the survival fraction) is not biased."""
    fine = _grid(70000.0, 110000.0, 81, 41, 50.0)          # y 110000..112000
    coarse = _grid(70000.0, 112100.0, 41, 20, 100.0)       # y 112100..114000
    gs = GridSet([fine, coarse])
    sel = gs.select(lambda x, y: np.ones(np.shape(x), bool), 71000.0, 111000.0, 72990.0, 112990.0)
    thinned, spacing = gs.thin(sel, max_points=10000)
    assert spacing == pytest.approx(100.0)
    g = gs.gather(thinned)
    n_fine = int(np.sum(g["grid"] == 0))                   # y 111000..112000 -> 11 rows x 20 cols
    n_coarse = int(np.sum(g["grid"] == 1))                 # y 112100..112900 -> 9 rows x 20 cols
    assert (n_fine, n_coarse) == (220, 180)
    # a tighter budget grows the spacing by sqrt(2) steps on both grids
    thinned, spacing = gs.thin(sel, max_points=150)
    assert spacing > 100.0 and GridSet.count(thinned) <= 150
    assert gs.contains(71000.0, 113000.0) and not gs.contains(60000.0, 113000.0)


@pytest.mark.skipif(not real_dem_available(), reason="real Site20v2 DEM not downloaded")
def test_real_regional_levels_match_the_tile():
    t = load_terrain()
    if not isinstance(t, LayeredTerrain):
        pytest.skip("regional DEM not prepared (scripts/prepare_regional_dem.py)")
    # inside the tile, away from the seam, the composite is exactly the 5 m DEM
    assert t.height_at(73000.0, 118000.0) == pytest.approx(t.layers[0].height_at(73000.0, 118000.0))
    # the IM-2 sites are covered by the 20 m level
    x, y = geo.latlon_to_xy(np.array([-84.78, -84.7906]), np.array([29.13, 29.1957]))
    assert list(t.layer_index_at(x, y)) == [1, 1]
    # no step across the north seam of the tile (y = 131 km)
    ys = np.linspace(130000.0, 132000.0, 401)
    z = t.height_at(np.full(ys.size, 75000.0), ys)
    assert np.all(np.isfinite(z)) and np.max(np.abs(np.diff(z))) < 10.0
