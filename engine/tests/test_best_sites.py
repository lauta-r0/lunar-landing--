# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""best_sites(): response shape and consistency with analyze() (CONTRACT 4.7).

Synthetic DEM + the SYNTHETIC ephemeris stub (see test_analyze.py): results here are not real.
"""
import base64
import json

import numpy as np
import pytest

from engine import analyze as az
from engine import best_sites as bs
from engine import _ephemeris_stub as stub
from engine import geo
from engine.errors import EngineError
from engine.grid import HorizonGrid
from engine.terrain import LayeredTerrain, Terrain
from engine.tests.conftest import CENTER_XY, make_terrain
from engine.tests.test_analyze import center_request, engine_grid, engine_no_grid, synthetic_parts  # noqa: F401

BASE = {k: v for k, v in center_request().items() if k != "target"}


def decode(heat: dict) -> np.ndarray:
    raw = np.frombuffer(base64.b64decode(heat["data_b64"]), dtype=np.uint8)
    assert raw.size == heat["width"] * heat["height"]
    return raw.reshape(heat["height"], heat["width"])


def test_shape_and_payload(engine_grid):
    r = bs.best_sites(dict(BASE))
    body = json.dumps(r)                                             # JSON-serializable, no numpy types
    assert len(body) < 300_000                                       # payload limit, before gzip
    for key in ["schema_version", "is_sample", "computed_utc", "compute_ms", "inputs", "heatmap", "summary",
                "sites", "map", "warnings", "sources"]:
        assert key in r, key
    assert r["inputs"]["region"] == "5m" and r["inputs"]["max_sites"] == bs.MAX_SITES_DEFAULT   # most reliable data
    assert "target" not in r["inputs"]
    heat = r["heatmap"]
    assert heat["encoding"] == "uint8-base64" and heat["approximate"] is True
    assert heat["value_max"] == 254 and heat["invalid_value"] == 255
    x0, y0, x1, y1 = heat["bounds_xy_m"]
    assert abs((x1 - x0) / heat["cell_m"] - heat["width"]) < 1e-6
    assert abs((y1 - y0) / heat["cell_m"] - heat["height"]) < 1e-6
    img = decode(heat)
    assert (img == 255).any() and (img < 255).any()                  # the rim cannot hold 80% of an ellipse
    assert r["summary"]["n_cells"] == int((img < 255).sum())
    assert any("Approximate" in w for w in r["warnings"]) and any("date" in w for w in r["warnings"])

    sites = r["sites"]
    assert 0 < len(sites) <= bs.MAX_SITES_DEFAULT
    assert [s["rank"] for s in sites] == list(range(1, len(sites) + 1))
    probs = [s["survival_probability"] for s in sites]
    assert probs == sorted(probs, reverse=True) and min(probs) > 0          # ranked by the real probability
    sep = max(bs.MIN_SEPARATION_M, 2 * BASE["ellipse"]["semi_major_m"])
    for i, s in enumerate(sites):
        assert set(s) == {"rank", "name", "lat", "lon", "x_m", "y_m", "survival_probability",
                          "survival_probability_incl_risky", "n_points", "data_resolution_m", "fine_fraction",
                          "coarse_fraction", "matches_full_analysis", "heatmap_probability"}
        assert s["fine_fraction"] + s["coarse_fraction"] == pytest.approx(1.0, abs=1e-9)
        assert s["survival_probability"] <= s["survival_probability_incl_risky"] <= 1.0
        assert x0 <= s["x_m"] <= x1 and y0 <= s["y_m"] <= y1
        for other in sites[i + 1:]:
            assert np.hypot(s["x_m"] - other["x_m"], s["y_m"] - other["y_m"]) >= sep - 1.0


def test_listed_sites_equal_the_full_analysis(engine_grid):
    """A listed site shows the number the full analysis gives when the user selects it."""
    # large enough for >= 40 nodes of the 200 m synthetic grid, so analyze() samples the grid too
    req = {**BASE, "ellipse": {"semi_major_m": 1400, "semi_minor_m": 900, "azimuth_deg": 30}}
    r = bs.best_sites(req)
    assert r["sites"]
    for s in r["sites"]:
        assert s["matches_full_analysis"] is True
        full = az.analyze({**req, "target": {"lat": s["lat"], "lon": s["lon"]},
                           "options": {**BASE["options"], "delay_days_max": 0, "include_recommendations": False}})
        assert full["summary"]["survival_probability"] == s["survival_probability"]
        assert full["summary"]["survival_probability_incl_risky"] == s["survival_probability_incl_risky"]
        assert full["summary"]["n_points"] == s["n_points"]


def test_heatmap_cell_matches_analyze_at_the_same_aim_point(engine_grid):
    """With a circular ellipse the cell value is the survival probability of analyze() at that node."""
    req = {**BASE, "ellipse": {"semi_major_m": 900, "semi_minor_m": 900, "azimuth_deg": 0}}
    r = bs.best_sites(req)
    heat = r["heatmap"]
    img = decode(heat)
    x0, _y0, _x1, y1 = heat["bounds_xy_m"]
    checked = 0
    for row, col in [(img.shape[0] // 2, img.shape[1] // 2), (img.shape[0] // 2 - 4, img.shape[1] // 2 + 5),
                     (img.shape[0] // 2 + 6, img.shape[1] // 2 - 3)]:
        assert img[row, col] != 255
        x = x0 + (col + 0.5) * heat["cell_m"]
        y = y1 - (row + 0.5) * heat["cell_m"]                        # row 0 is the north edge
        lat, lon = geo.xy_to_latlon(x, y)
        full = az.analyze({**req, "target": {"lat": float(lat), "lon": float(lon)},
                           "options": {**BASE["options"], "delay_days_max": 0, "include_recommendations": False}})
        assert abs(img[row, col] / 254.0 - full["summary"]["survival_probability"]) <= 0.004
        checked += 1
    assert checked == 3


def test_empty_when_no_site_meets_the_limits(engine_grid):
    """Slope limit below the terrain slope everywhere: no site, every valid cell is 0."""
    r = bs.best_sites({**BASE, "limits": {**BASE["limits"], "max_slope_deg": 1}})
    assert r["sites"] == []
    img = decode(r["heatmap"])
    assert set(np.unique(img)) <= {0, 255} and r["summary"]["n_cells_above_zero"] == 0


def test_region_filter(engine_grid):
    """The synthetic DEM has one level: everything is 'fine', so 5m = all and 20m is empty."""
    all_r, fine, coarse = (bs.best_sites({**BASE, "region": reg}) for reg in ("all", "5m", "20m"))
    assert fine["heatmap"]["data_b64"] == all_r["heatmap"]["data_b64"] and fine["sites"] == all_r["sites"]
    assert coarse["sites"] == [] and set(np.unique(decode(coarse["heatmap"]))) == {255}
    assert coarse["inputs"]["region"] == "20m"


def test_small_ellipse_is_flagged_as_not_matching(engine_grid):
    r = bs.best_sites({**BASE, "ellipse": {"semi_major_m": 60, "semi_minor_m": 60, "azimuth_deg": 0}})
    assert any("smaller than" in w for w in r["warnings"])
    assert all(s["matches_full_analysis"] is False for s in r["sites"])


def test_cached_and_errors(engine_grid):
    a, b = bs.best_sites(dict(BASE)), bs.best_sites(dict(BASE))
    assert a == b and a["computed_utc"] == b["computed_utc"]
    with pytest.raises(EngineError) as e:
        bs.best_sites({**BASE, "region": "everywhere"})
    assert e.value.code == "invalid_request"
    with pytest.raises(EngineError) as e:
        bs.best_sites({**BASE, "max_sites": 99})
    assert e.value.code == "invalid_request"
    with pytest.raises(EngineError) as e:
        bs.best_sites({**BASE, "landing_utc": "2040-01-01T00:00:00Z"})
    assert e.value.code == "out_of_ephemeris_range"


def test_needs_the_precomputed_grid(engine_no_grid):
    with pytest.raises(EngineError) as e:
        bs.best_sites(dict(BASE))
    assert e.value.code == "best_sites_unavailable"


# --------------------------------------------------------------------------- two DEM levels
TILE_HALF_M = 3000.0          # the synthetic "5 m tile" is 6 x 6 km around CENTER_XY


@pytest.fixture()
def engine_two_levels():
    """Fine tile (6 km) inside a coarse DEM (40 km), both flat with a 3 deg slope raster, and a
    200 m grid with flat horizons that straddles the tile's east edge (x = CENTER + 3000)."""
    geo.configure(None)
    fine = make_terrain(None, size_m=2 * TILE_HALF_M, pixel_m=10.0, slope_deg=3.0)
    c = make_terrain(None, size_m=40000.0, pixel_m=40.0, slope_deg=3.0)
    coarse = Terrain(c.surf, c.slp, x_min=c.x_min, y_max=c.y_max, pixel_m=40.0, name="coarse", role="near")
    terrain = LayeredTerrain([fine, coarse])
    nx, ny, spacing = 51, 21, 200.0
    x0, y0 = CENTER_XY[0] - 2400.0, CENTER_XY[1] - 2000.0          # x: -2400 .. +7600 around the center
    xx, yy = np.meshgrid(x0 + np.arange(nx) * spacing, y0 + np.arange(ny) * spacing)
    lat, lon = geo.xy_to_latlon(xx, yy)
    meta = {"nx": nx, "ny": ny, "x0": x0, "y0": y0, "spacing_m": spacing, "observer_height_m": 2.0, "n_az": 360}
    grid = HorizonGrid(meta, np.full((ny, nx, 360), -1.0, np.float16), None, np.zeros((ny, nx), np.float32),
                       np.full((ny, nx), 3.0, np.float32), lat, lon)
    az.configure_engine(terrain=terrain, grid=grid, ephemeris=stub.load_ephemeris_stub(),
                        local_az_el=stub.local_az_el, is_stub=True)
    yield
    az.reset_engine()


def _valid_x(resp):
    """Map x of the valid heatmap cells."""
    heat = resp["heatmap"]
    img = decode(heat)
    cols = np.nonzero((img != 255).any(axis=0))[0]
    return heat["bounds_xy_m"][0] + (cols + 0.5) * heat["cell_m"]


def test_region_uses_the_ellipse_composition_not_its_center(engine_two_levels):
    """"5m" / "20m" keep an aim point only if >= 95% of its ellipse is on that data, so no site sits
    on the seam; "all" covers everything and ranks by the real probability (ties: more 5 m data)."""
    edge = CENTER_XY[0] + TILE_HALF_M
    relaxed = {"max_dark_h": 400, "max_comm_gap_h": 400, "min_earth_pct": 0, "max_slope_deg": 8}
    req = {**BASE, "limits": relaxed, "ellipse": {"semi_major_m": 800, "semi_minor_m": 800, "azimuth_deg": 0},
           "max_sites": 10}
    fine, coarse, both = (bs.best_sites({**req, "region": reg}) for reg in ("5m", "20m", "all"))

    # a center closer than about one ellipse radius to the seam is in neither filtered region
    xf, xc, xa = _valid_x(fine), _valid_x(coarse), _valid_x(both)
    assert xf.max() <= edge - 600.0 and xc.min() >= edge + 600.0
    assert xa.min() <= xf.min() and xa.max() >= xc.max()
    assert np.any((xa > xf.max()) & (xa < xc.min()))                 # the seam band exists only in "all"

    assert fine["sites"] and coarse["sites"] and both["sites"]
    for s in fine["sites"]:
        assert s["fine_fraction"] >= bs.REGION_MIN_SHARE and s["x_m"] <= edge - 600.0
        assert 10.0 in s["data_resolution_m"]                       # up to 5% of the ellipse may be coarse
    for s in coarse["sites"]:
        assert s["coarse_fraction"] >= bs.REGION_MIN_SHARE and s["x_m"] >= edge + 600.0
        assert 40.0 in s["data_resolution_m"]

    # "all": everything is equally viable on this flat terrain, so only the tie-break decides the
    # order: the larger share of the ellipse on 5 m data first. No probability is adjusted.
    probs = {s["survival_probability"] for s in both["sites"]}
    assert probs == {1.0}
    fracs = [s["fine_fraction"] for s in both["sites"]]
    assert fracs == sorted(fracs, reverse=True) and fracs[0] == 1.0 and fracs[-1] < 0.5
    assert all("rank_score" not in s for s in both["sites"])
    assert any("20 m terrain" in w for w in both["warnings"])
    assert not any("order of probability" in w or "minus" in w for w in both["warnings"])


def test_all_data_ranks_by_the_real_probability_only(engine_two_levels):
    """A 20 m site with a higher survival probability outranks a 5 m site: no resolution adjustment."""
    eng = az._engine()
    g = eng.grid.grids[0]
    x, _y = g.node_xy(*np.meshgrid(np.arange(g.ny), np.arange(g.nx), indexing="ij"))
    edge = CENTER_XY[0] + TILE_HALF_M
    # make most of the 5 m side too steep; the 20 m side stays fully viable
    g.slope_deg = np.where((x < edge) & ((np.arange(g.nx)[None, :] + np.arange(g.ny)[:, None]) % 3 > 0),
                           20.0, 3.0).astype(np.float32)
    eng._best_sites_lattice = None
    relaxed = {"max_dark_h": 400, "max_comm_gap_h": 400, "min_earth_pct": 0, "max_slope_deg": 8}
    r = bs.best_sites({**BASE, "limits": relaxed, "region": "all", "max_sites": 10,
                       "ellipse": {"semi_major_m": 800, "semi_minor_m": 800, "azimuth_deg": 0}})
    sites = r["sites"]
    probs = [s["survival_probability"] for s in sites]
    assert probs == sorted(probs, reverse=True)
    assert sites[0]["survival_probability"] == 1.0 and sites[0]["coarse_fraction"] > 0.9
    fine_sites = [s for s in sites if s["fine_fraction"] == 1.0]
    coarse_sites = [s for s in sites if s["coarse_fraction"] == 1.0]
    assert fine_sites and max(s["survival_probability"] for s in fine_sites) < 0.6
    assert coarse_sites and min(s["survival_probability"] for s in coarse_sites) == 1.0
    # every fully 20 m site (100%) is listed before every fully 5 m site (under 60%)
    assert max(sites.index(s) for s in coarse_sites) < min(sites.index(s) for s in fine_sites)
    # equal probabilities: the site with more of its ellipse on 5 m data comes first
    top = [s for s in sites if s["survival_probability"] == 1.0]
    assert [s["fine_fraction"] for s in top] == sorted((s["fine_fraction"] for s in top), reverse=True)
