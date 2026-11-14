# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
import numpy as np
from pyproj import CRS, Transformer

from engine import geo
from engine.geo import R_MOON


def test_closed_form_matches_pyproj():
    crs = CRS.from_proj4(geo.FALLBACK_PROJ4)
    fwd = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    rng = np.random.default_rng(1)
    lat = rng.uniform(-90.0, -80.0, 200)
    lon = rng.uniform(-180.0, 180.0, 200)
    px, py = fwd.transform(lon, lat)
    x, y = geo.latlon_to_xy(lat, lon)
    assert np.max(np.hypot(x - px, y - py)) < 1e-4
    assert geo.uses_closed_form()


def test_roundtrip_and_known_point():
    x, y = geo.latlon_to_xy(-85.42657728, 31.74276115)     # Site20v2 DEM center
    assert abs(float(x) - 73000.0) < 0.01 and abs(float(y) - 118000.0) < 0.01
    lat, lon = geo.xy_to_latlon(73000.0, 118000.0)
    assert abs(float(lat) + 85.42657728) < 1e-7 and abs(float(lon) - 31.74276115) < 1e-7
    # longitude convention: +x is 90 E, +y is 0 E
    assert abs(float(geo.xy_to_latlon(1000.0, 0.0)[1]) - 90.0) < 1e-9
    assert abs(float(geo.xy_to_latlon(0.0, 1000.0)[1])) < 1e-9


def test_destination_basic():
    # going north by a quarter of the circumference from the equator reaches the pole
    lat, _ = geo.destination(0.0, 10.0, 0.0, np.pi / 2 * R_MOON)
    assert abs(float(lat) - 90.0) < 1e-6
    # going east along the equator
    lat, lon = geo.destination(0.0, 10.0, 90.0, np.radians(5.0) * R_MOON)
    assert abs(float(lat)) < 1e-9 and abs(float(lon) - 15.0) < 1e-9
    # distance and bearing are consistent with destination
    lat2, lon2 = geo.destination(-85.4, 31.7, 123.0, 7500.0)
    assert abs(float(geo.great_circle_distance(-85.4, 31.7, lat2, lon2)) - 7500.0) < 1e-4
    assert abs(float(geo.initial_bearing(-85.4, 31.7, lat2, lon2)) - 123.0) < 1e-6


def test_ray_xy_matches_destination():
    az = np.arange(0.0, 360.0, 7.0)
    s = np.array([10.0, 500.0, 5000.0, 30000.0])
    x, y = geo.ray_xy(-85.4266, 31.7428, az, s)
    lat2, lon2 = geo.destination(-85.4266, 31.7428, az[:, None], s[None, :])
    x2, y2 = geo.latlon_to_xy(lat2, lon2)
    assert np.max(np.hypot(x - x2, y - y2)) < 1e-4


def test_map_frame_north_points_away_from_pole():
    north, east, scale = geo.map_frame(-85.4266, 31.7428)
    x, y = geo.latlon_to_xy(-85.4266, 31.7428)
    radial = np.array([float(x), float(y)]) / np.hypot(x, y)
    assert np.allclose(north, radial, atol=1e-6)
    assert np.allclose(east, [radial[1], -radial[0]], atol=1e-6)
    assert abs(float(scale) - 2.0 / (1.0 + np.sin(np.radians(85.4266)))) < 1e-5
    # a point 1 km to the local east really is 1 km away at bearing 90
    ex, ey = geo.offset_to_xy(-85.4266, 31.7428, 1000.0, 0.0)
    lat2, lon2 = geo.xy_to_latlon(ex, ey)
    assert abs(float(geo.great_circle_distance(-85.4266, 31.7428, lat2, lon2)) - 1000.0) < 0.5
    assert abs(float(geo.initial_bearing(-85.4266, 31.7428, lat2, lon2)) - 90.0) < 0.5


def test_to_cartesian():
    p = geo.to_cartesian(-90.0, 0.0, 100.0)
    assert np.allclose(p, [0.0, 0.0, -(R_MOON + 100.0)], atol=1e-6)
    p = geo.to_cartesian(0.0, 90.0, 0.0)
    assert np.allclose(p, [0.0, R_MOON, 0.0], atol=1e-6)
