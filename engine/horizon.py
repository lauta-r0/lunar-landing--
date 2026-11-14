# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Horizon mask: the elevation angle of the terrain skyline seen from a point, per azimuth.

For an observer standing h_obs above the terrain, and for each azimuth (1 degree bins, clockwise
from local north), we march along the great circle that leaves the observer in that direction,
read the DEM height at every sample, and convert it to an elevation angle above the observer's
local horizontal plane using exact spherical geometry:

    theta = atan2( (R+z)*cos(s/R) - (R+z0+h_obs),  (R+z)*sin(s/R) )

    R  = 1,737,400 m (reference sphere)     s  = ground distance along the great circle
    z  = terrain height at the sample       z0 = terrain height under the observer

The horizon elevation at that azimuth is the maximum theta over the samples inside the DEM.
The Sun (or Earth) is visible when its elevation is above this value at its azimuth.

With the regional LOLA levels loaded (engine.terrain.LayeredTerrain) the rays read the 5 m tile
first, then the 20 m and 40 m polar DEMs, out to MAX_RAY_M = 100 km (far-field horizon).

All azimuths x samples of one observer are computed as one numpy array operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from . import geo
from .geo import R_MOON

# Ray sampling: start at S0, step = max(DS_MIN, GROWTH * s). Dense near the observer (DEM
# resolution), geometric far away (constant ~1% relative spacing, comparable to the lateral
# spacing of 1-degree azimuth bins, which is 1.7% of the distance).
S0_M = 10.0
DS_MIN_M = 5.0
GROWTH = 0.01
MAX_RAY_M = 100000.0     # far-field horizon limit (curvature drop at 100 km: 2.9 km)

# Samples closer than this use bilinear interpolation of the DEM; farther samples use the nearest
# pixel of the finest level that covers them (5 m on the tile) (at >= 1 km a 2.5 m horizontal offset changes the angle by < 0.08 deg even on a
# 30 deg slope, and it is ~3x faster).
NEAR_BILINEAR_M = 1000.0

# A ray that leaves the DEM before this distance may be missing distant peaks.
MIN_TRUSTED_REACH_M = 10000.0


@dataclass
class Horizon:
    elevation_deg: np.ndarray      # (n_az,) horizon elevation, degrees
    reach_m: np.ndarray            # (n_az,) distance of the farthest DEM sample along the ray, m
    az_step_deg: float
    x_m: float
    y_m: float
    lat: float
    lon: float
    ground_height_m: float
    observer_height_m: float

    def at(self, azimuth_deg):
        """Horizon elevation at arbitrary azimuth(s): linear interpolation with wrap-around."""
        return interp_horizon(self.elevation_deg[None, :], np.atleast_1d(azimuth_deg)[None, :])[0]


@lru_cache(maxsize=8)
def _all_distances(s0: float, ds_min: float, growth: float, max_ray: float) -> np.ndarray:
    out = [s0]
    s = s0
    while s < max_ray:
        s += max(ds_min, growth * s)
        out.append(s)
    arr = np.asarray(out, dtype=np.float64)
    arr.setflags(write=False)
    return arr


def sample_distances(max_dist_m: float, s0: float = S0_M, ds_min: float = DS_MIN_M,
                     growth: float = GROWTH) -> np.ndarray:
    """Ground distances of the ray samples, from s0 up to (just past) max_dist_m."""
    allv = _all_distances(float(s0), float(ds_min), float(growth), MAX_RAY_M)
    n = int(np.searchsorted(allv, max_dist_m, side="right")) + 1
    return allv[: max(2, min(n, allv.size))]


def flat_horizon_deg(observer_height_m: float) -> float:
    """Horizon dip on a smooth sphere: -acos(R / (R + h)) in degrees."""
    return -float(np.degrees(np.arccos(R_MOON / (R_MOON + observer_height_m))))


def _heights_along_rays(terrain, xs: np.ndarray, ys: np.ndarray, n_near: int) -> np.ndarray:
    """Terrain height at ray samples (A, S): bilinear for the first n_near columns, nearest pixel beyond."""
    n_near = max(0, min(int(n_near), xs.shape[1]))
    z = np.empty(xs.shape, dtype=np.float64)
    if n_near > 0:
        z[:, :n_near] = terrain.height_at(xs[:, :n_near], ys[:, :n_near])
    if n_near < xs.shape[1]:
        z[:, n_near:] = terrain.height_nearest(xs[:, n_near:], ys[:, n_near:])
    return z


def compute_horizon_xy(x: float, y: float, observer_height_m: float = 2.0, terrain=None,
                       az_step_deg: float = 1.0, s0: float = S0_M, ds_min: float = DS_MIN_M,
                       growth: float = GROWTH, near_m: float = NEAR_BILINEAR_M) -> Horizon:
    """Horizon mask for an observer at map coordinates (x, y)."""
    if terrain is None:
        from .terrain import get_terrain
        terrain = get_terrain()
    x, y = float(x), float(y)
    lat, lon = geo.xy_to_latlon(x, y)
    lat, lon = float(lat), float(lon)
    z0 = float(terrain.height_at(x, y))
    if not np.isfinite(z0):
        raise ValueError("Observer is outside the DEM")

    n_az = int(round(360.0 / az_step_deg))
    az = np.arange(n_az) * az_step_deg
    s = sample_distances(min(terrain.max_distance_from(x, y), MAX_RAY_M), s0, ds_min, growth)

    xs, ys = geo.ray_xy(lat, lon, az, s)                    # (A, S)
    z = _heights_along_rays(terrain, xs, ys, int(np.searchsorted(s, near_m)))   # NaN outside the DEM
    valid = np.isfinite(z)
    reach = (valid * s[None, :]).max(axis=1)

    # tan(theta) = [(R+z) cos(sig) - (R+z0+h)] / [(R+z) sin(sig)] = cot(sig) - (R+z0+h) / ((R+z) sin(sig))
    sig = s / R_MOON
    np.copyto(z, -0.5 * R_MOON, where=~valid)               # outside the DEM: far below any real sample
    z += R_MOON
    z *= np.sin(sig)[None, :]
    np.divide(R_MOON + z0 + observer_height_m, z, out=z)
    np.subtract((1.0 / np.tan(sig))[None, :], z, out=z)
    best = z.max(axis=1)
    best = np.where(reach > 0.0, best, -np.inf)
    elev = np.degrees(np.arctan(best))

    # Azimuths with no DEM sample at all (observer on the very edge): smooth-sphere horizon.
    empty = ~np.isfinite(best)
    if empty.any():
        elev = np.where(empty, flat_horizon_deg(observer_height_m), elev)
    return Horizon(elevation_deg=elev, reach_m=reach, az_step_deg=float(az_step_deg), x_m=x, y_m=y,
                   lat=lat, lon=lon, ground_height_m=z0, observer_height_m=float(observer_height_m))


def compute_horizon(lat: float, lon: float, observer_height_m: float = 2.0, terrain=None,
                    **kwargs) -> Horizon:
    """Horizon mask for an observer at lat/lon (degrees)."""
    x, y = geo.latlon_to_xy(lat, lon)
    return compute_horizon_xy(float(x), float(y), observer_height_m, terrain, **kwargs)


def compute_horizons_xy(xs, ys, observer_height_m: float = 2.0, terrain=None, workers: int = 1, **kwargs):
    """Horizon masks for many observers.

    Returns (elevation_deg (P, A) float32, reach_m (P, A) float32, ground_height_m (P,) float32).
    One vectorized (azimuths x samples) operation per observer. With workers > 1 the observers are
    spread over threads (numpy releases the GIL in the heavy array operations; about 1.7x faster
    with 2 threads, 2.9x with 4). The precompute script uses processes instead and keeps workers = 1.
    """
    xs = np.asarray(xs, dtype=np.float64).ravel()
    ys = np.asarray(ys, dtype=np.float64).ravel()
    n_az = int(round(360.0 / kwargs.get("az_step_deg", 1.0)))
    elev = np.empty((xs.size, n_az), dtype=np.float32)
    reach = np.empty((xs.size, n_az), dtype=np.float32)
    z0 = np.empty(xs.size, dtype=np.float32)
    if terrain is None:
        from .terrain import get_terrain
        terrain = get_terrain()

    def one(i):
        h = compute_horizon_xy(xs[i], ys[i], observer_height_m, terrain, **kwargs)
        elev[i], reach[i], z0[i] = h.elevation_deg, h.reach_m, h.ground_height_m

    if workers > 1 and xs.size > 4:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=int(workers)) as ex:
            list(ex.map(one, range(xs.size)))
    else:
        for i in range(xs.size):
            one(i)
    return elev, reach, z0


def interp_horizon(horizon_deg: np.ndarray, azimuth_deg: np.ndarray) -> np.ndarray:
    """Horizon elevation at given azimuths, linear between bins, wrapping at 360.

    horizon_deg: (P, A) with bin k at azimuth k * 360 / A.   azimuth_deg: (P, T).
    Returns (P, T) float64.
    """
    hor = np.asarray(horizon_deg)
    n_az = hor.shape[1]
    pos = (np.asarray(azimuth_deg, dtype=np.float64) % 360.0) * (n_az / 360.0)
    i0 = np.floor(pos).astype(np.int64) % n_az
    frac = pos - np.floor(pos)
    i1 = (i0 + 1) % n_az
    h0 = np.take_along_axis(hor, i0, axis=1).astype(np.float64)
    h1 = np.take_along_axis(hor, i1, axis=1).astype(np.float64)
    return h0 + (h1 - h0) * frac
