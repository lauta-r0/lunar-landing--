# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Coordinates for LunaScout.

Conventions (CONTRACT section 2):
- latitude in degrees, south negative; longitude in degrees east-positive, [-180, 180]
- azimuth in degrees clockwise from local north
- map coordinates x_m, y_m: south polar stereographic meters on the R = 1,737,400 m sphere
- body-fixed frame: Moon Mean Earth / polar axis (ME); +z = north pole, +x = lon 0, +y = lon 90 E

The map CRS is read from the DEM GeoTIFF (``configure``). The PGDA site DEMs use the spherical
south polar stereographic projection with lon_0 = 0 and true scale at the pole; for that case the
projection has a simple closed form, which we use in the hot loops after checking it against pyproj.
"""
from __future__ import annotations

import numpy as np

R_MOON = 1737400.0

FALLBACK_PROJ4 = (
    "+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 "
    "+R=1737400 +units=m +no_defs"
)


class _State:
    crs_proj4: str = FALLBACK_PROJ4
    closed_form: bool = True      # True: use the analytic south polar stereographic formulas
    fwd = None                    # pyproj lon/lat -> x/y (only used when closed_form is False)
    inv = None                    # pyproj x/y -> lon/lat


_S = _State()


# --------------------------------------------------------------------------- projection
def _closed_latlon_to_xy(lat, lon):
    phi = np.radians(lat)
    lam = np.radians(lon)
    rho = 2.0 * R_MOON * np.tan(np.pi / 4.0 + phi / 2.0)
    return rho * np.sin(lam), rho * np.cos(lam)


def _closed_xy_to_latlon(x, y):
    rho = np.hypot(x, y)
    lat = -90.0 + np.degrees(2.0 * np.arctan(rho / (2.0 * R_MOON)))
    lon = np.degrees(np.arctan2(x, y))
    return lat, lon


def configure(crs=None) -> dict:
    """Set the map CRS (pass the rasterio/pyproj CRS of the DEM; None = contract fallback).

    Builds pyproj transformers and checks whether the closed-form projection reproduces them
    (to better than 1 mm). Returns a small report dict.
    """
    from pyproj import CRS, Transformer

    proj_crs = CRS.from_proj4(FALLBACK_PROJ4) if crs is None else CRS.from_user_input(
        crs.to_wkt() if hasattr(crs, "to_wkt") else crs
    )
    geo_crs = proj_crs.geodetic_crs
    fwd = Transformer.from_crs(geo_crs, proj_crs, always_xy=True)
    inv = Transformer.from_crs(proj_crs, geo_crs, always_xy=True)

    lat = np.array([-89.5, -86.0, -85.4, -84.0, -80.0])
    lon = np.array([-170.0, -45.0, 31.7, 90.0, 179.0])
    px, py = fwd.transform(lon, lat)
    cx, cy = _closed_latlon_to_xy(lat, lon)
    err = float(np.max(np.hypot(np.asarray(px) - cx, np.asarray(py) - cy)))

    _S.closed_form = bool(np.isfinite(err) and err < 1e-3)
    _S.fwd, _S.inv = fwd, inv
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _S.crs_proj4 = proj_crs.to_proj4()
    except Exception:  # pragma: no cover
        _S.crs_proj4 = FALLBACK_PROJ4
    return {"closed_form": _S.closed_form, "max_error_m": err, "crs_proj4": _S.crs_proj4}


def crs_proj4() -> str:
    return _S.crs_proj4


def uses_closed_form() -> bool:
    return _S.closed_form


def latlon_to_xy(lat, lon):
    """lat/lon in degrees -> map x_m, y_m (numpy arrays, broadcast)."""
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    if _S.closed_form:
        return _closed_latlon_to_xy(lat, lon)
    x, y = _S.fwd.transform(lon, lat)
    return np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)


def xy_to_latlon(x, y):
    """Map x_m, y_m -> lat, lon in degrees (lon in [-180, 180])."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if _S.closed_form:
        return _closed_xy_to_latlon(x, y)
    lon, lat = _S.inv.transform(x, y)
    lon = (np.asarray(lon, dtype=np.float64) + 180.0) % 360.0 - 180.0
    return np.asarray(lat, dtype=np.float64), lon


# --------------------------------------------------------------------------- sphere geometry
def unit_vector(lat, lon):
    """Unit vector(s) in the ME frame, shape (..., 3)."""
    phi = np.radians(np.asarray(lat, dtype=np.float64))
    lam = np.radians(np.asarray(lon, dtype=np.float64))
    c = np.cos(phi)
    return np.stack([c * np.cos(lam), c * np.sin(lam), np.sin(phi)], axis=-1)


def to_cartesian(lat, lon, height_m=0.0):
    """Cartesian ME coordinates in meters, shape (..., 3); heights relative to the R_MOON sphere."""
    r = R_MOON + np.asarray(height_m, dtype=np.float64)
    return unit_vector(lat, lon) * r[..., None]


def local_frame(lat, lon):
    """(up, east, north) unit vectors in the ME frame at lat/lon, each of shape (..., 3)."""
    phi = np.radians(np.asarray(lat, dtype=np.float64))
    lam = np.radians(np.asarray(lon, dtype=np.float64))
    sp, cp, sl, cl = np.sin(phi), np.cos(phi), np.sin(lam), np.cos(lam)
    up = np.stack([cp * cl, cp * sl, sp], axis=-1)
    east = np.stack([-sl, cl, np.zeros_like(sl)], axis=-1)
    north = np.stack([-sp * cl, -sp * sl, cp], axis=-1)
    return up, east, north


def destination(lat, lon, azimuth_deg, distance_m):
    """Great-circle destination on the R_MOON sphere (vectorized, broadcasts).

    Start at lat/lon, travel distance_m along the initial bearing azimuth_deg (clockwise from north).
    Returns (lat2, lon2) in degrees, lon2 in [-180, 180].
    """
    phi1 = np.radians(np.asarray(lat, dtype=np.float64))
    lam1 = np.radians(np.asarray(lon, dtype=np.float64))
    theta = np.radians(np.asarray(azimuth_deg, dtype=np.float64))
    delta = np.asarray(distance_m, dtype=np.float64) / R_MOON
    sin_phi2 = np.sin(phi1) * np.cos(delta) + np.cos(phi1) * np.sin(delta) * np.cos(theta)
    sin_phi2 = np.clip(sin_phi2, -1.0, 1.0)
    phi2 = np.arcsin(sin_phi2)
    lam2 = lam1 + np.arctan2(
        np.sin(theta) * np.sin(delta) * np.cos(phi1),
        np.cos(delta) - np.sin(phi1) * sin_phi2,
    )
    lon2 = (np.degrees(lam2) + 180.0) % 360.0 - 180.0
    return np.degrees(phi2), lon2


def great_circle_distance(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters on the R_MOON sphere (vectorized)."""
    u1 = unit_vector(lat1, lon1)
    u2 = unit_vector(lat2, lon2)
    cross = np.linalg.norm(np.cross(u1, u2), axis=-1)
    dot = np.sum(u1 * u2, axis=-1)
    return R_MOON * np.arctan2(cross, dot)


def initial_bearing(lat1, lon1, lat2, lon2):
    """Initial bearing (deg clockwise from north, [0, 360)) from point 1 to point 2."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dlam = np.radians(np.asarray(lon2, dtype=np.float64) - np.asarray(lon1, dtype=np.float64))
    y = np.sin(dlam) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlam)
    return np.degrees(np.arctan2(y, x)) % 360.0


def ray_xy(lat0: float, lon0: float, azimuth_deg, distance_m):
    """Map coordinates of the points along great-circle rays leaving (lat0, lon0).

    azimuth_deg: (A,) bearings; distance_m: (S,) ground distances.
    Returns x, y arrays of shape (A, S). Same result as destination() followed by latlon_to_xy(),
    but done with unit vectors so that all rays of one observer are a single array operation.
    """
    az = np.radians(np.asarray(azimuth_deg, dtype=np.float64)).reshape(-1)
    s = np.asarray(distance_m, dtype=np.float64).reshape(-1)
    if not _S.closed_form:
        lat2, lon2 = destination(lat0, lon0, np.degrees(az)[:, None], s[None, :])
        return latlon_to_xy(lat2, lon2)
    up, east, north = local_frame(float(lat0), float(lon0))
    d = north[None, :] * np.cos(az)[:, None] + east[None, :] * np.sin(az)[:, None]   # (A, 3)
    sig = s / R_MOON
    cs, sn = np.cos(sig), np.sin(sig)
    # p = up*cos(sig) + d*sin(sig) is the unit vector of each sample; then the south polar
    # stereographic projection of a unit vector is x = 2R*py/(1-pz), y = 2R*px/(1-pz).
    k = np.multiply.outer(d[:, 2], sn)
    k += up[2] * cs
    np.subtract(1.0, k, out=k)
    np.divide(2.0 * R_MOON, k, out=k)
    x = np.multiply.outer(d[:, 1], sn)
    x += up[1] * cs
    x *= k
    y = np.multiply.outer(d[:, 0], sn)
    y += up[0] * cs
    y *= k
    return x, y


def map_frame(lat, lon):
    """Local north/east directions and scale of the map projection at lat/lon.

    Returns (north_xy, east_xy, scale): unit 2-vectors (..., 2) in the map plane pointing to local
    north and local east, and the map scale factor (map meters per ground meter). In a south polar
    stereographic map, north points away from the pole, not along +y.
    """
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    step_m = 10.0
    dlat = np.degrees(step_m / R_MOON)
    x0, y0 = latlon_to_xy(lat, lon)
    x1, y1 = latlon_to_xy(lat + dlat, lon)
    dx, dy = x1 - x0, y1 - y0
    norm = np.hypot(dx, dy)
    north = np.stack([dx / norm, dy / norm], axis=-1)
    east = np.stack([north[..., 1], -north[..., 0]], axis=-1)   # conformal map: east = north rotated 90 deg clockwise
    return north, east, norm / step_m


def offset_to_xy(lat0: float, lon0: float, east_m, north_m):
    """Map coordinates of points given as small local offsets (meters east / north) from lat0/lon0.

    Uses the local conformal scale; accurate to well under a meter for offsets up to a few km.
    """
    north, east, scale = map_frame(lat0, lon0)
    x0, y0 = latlon_to_xy(lat0, lon0)
    e = np.asarray(east_m, dtype=np.float64) * scale
    n = np.asarray(north_m, dtype=np.float64) * scale
    return x0 + e * east[0] + n * north[0], y0 + e * east[1] + n * north[1]
