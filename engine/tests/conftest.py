# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Shared test helpers: synthetic DEMs placed where the real Site20v2 DEM is."""
import numpy as np
import pytest

from engine import geo
from engine.terrain import Terrain, find_dem_files

CENTER_XY = (73000.0, 118000.0)     # center of the real Site20v2 DEM


def make_terrain(height_fn=None, size_m=12000.0, pixel_m=10.0, slope_deg=0.0):
    """Synthetic DEM centered on CENTER_XY.

    height_fn(dist_m, bearing_deg) -> height, where dist/bearing are the great-circle distance and
    initial bearing from the DEM center to each pixel center (independent of the horizon code).
    """
    n = int(round(size_m / pixel_m))
    x_min = CENTER_XY[0] - size_m / 2.0
    y_max = CENTER_XY[1] + size_m / 2.0
    cols = x_min + (np.arange(n) + 0.5) * pixel_m
    rows = y_max - (np.arange(n) + 0.5) * pixel_m
    xx, yy = np.meshgrid(cols, rows)
    if height_fn is None:
        surf = np.zeros((n, n), dtype=np.float32)
    else:
        lat0, lon0 = geo.xy_to_latlon(*CENTER_XY)
        lat, lon = geo.xy_to_latlon(xx, yy)
        dist = geo.great_circle_distance(lat0, lon0, lat, lon)
        bearing = geo.initial_bearing(lat0, lon0, lat, lon)
        surf = np.asarray(height_fn(dist, bearing), dtype=np.float32)
    slp = np.full((n, n), slope_deg, dtype=np.float32)
    return Terrain(surf, slp, x_min=x_min, y_max=y_max, pixel_m=pixel_m, name="synthetic test DEM")


@pytest.fixture(autouse=True)
def _default_projection():
    """Every test starts with the contract's fallback CRS (closed-form projection)."""
    geo.configure(None)
    yield


def real_dem_available() -> bool:
    try:
        find_dem_files()
        return True
    except FileNotFoundError:
        return False
