# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""
Sun / Earth directions in the Moon body-fixed ME frame and local az/el for any point.

The table in ``data/ephemeris/sun_earth_vectors.npz`` holds unit vectors (Moon ME frame)
pointing to the Sun and to the Earth, hourly. Because both bodies are very far away,
the same vector is valid (to ~0.02 deg within ~150 km) for every point of the south
polar region; the local azimuth/elevation of a point is obtained by projecting the
vector on that point's own East-North-Up (ENU) basis.

Conventions (CONTRACT.md section 2): latitude south-negative, longitude east-positive,
azimuth clockwise from local north, elevation above the local horizontal plane.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "ephemeris" / "sun_earth_vectors.npz"
SUN_ANGULAR_RADIUS_DEG = 0.2665


# --------------------------------------------------------------------------- geometry
def _enu_basis(lat_deg, lon_deg):
    """ENU unit vectors (each (P, 3)) expressed in the Moon ME frame."""
    lat = np.radians(np.atleast_1d(np.asarray(lat_deg, dtype=np.float64)))
    lon = np.radians(np.atleast_1d(np.asarray(lon_deg, dtype=np.float64)))
    sl, cl = np.sin(lon), np.cos(lon)
    sp, cp = np.sin(lat), np.cos(lat)
    zero = np.zeros_like(sl)
    east = np.stack([-sl, cl, zero], axis=-1)
    north = np.stack([-sp * cl, -sp * sl, cp], axis=-1)
    up = np.stack([cp * cl, cp * sl, sp], axis=-1)
    return east, north, up


def azel_to_vec(az_deg, el_deg, lat_deg: float, lon_deg: float) -> np.ndarray:
    """Topocentric az/el (arrays of shape (T,)) seen from one site -> unit vectors (T, 3) in ME frame."""
    az = np.radians(np.atleast_1d(np.asarray(az_deg, dtype=np.float64)))
    el = np.radians(np.atleast_1d(np.asarray(el_deg, dtype=np.float64)))
    east, north, up = (b[0] for b in _enu_basis(lat_deg, lon_deg))
    e = np.cos(el) * np.sin(az)
    n = np.cos(el) * np.cos(az)
    u = np.sin(el)
    vec = e[:, None] * east + n[:, None] * north + u[:, None] * up
    return vec / np.linalg.norm(vec, axis=1, keepdims=True)


def local_az_el(vecs: np.ndarray, lat_deg, lon_deg) -> tuple[np.ndarray, np.ndarray]:
    """vecs (T, 3); lat/lon (P,) -> (az, el) arrays of shape (P, T), degrees.

    Fully vectorized: three (P,3)@(3,T) products.
    """
    vecs = np.asarray(vecs, dtype=np.float64)
    if vecs.ndim == 1:
        vecs = vecs[None, :]
    east, north, up = _enu_basis(lat_deg, lon_deg)
    vt = vecs.T
    e, n, u = east @ vt, north @ vt, up @ vt
    el = np.degrees(np.arcsin(np.clip(u, -1.0, 1.0)))
    az = np.degrees(np.arctan2(e, n)) % 360.0
    return az, el


def sun_disk_visible_fraction(sun_el, horizon_el, radius_deg: float = SUN_ANGULAR_RADIUS_DEG):
    """Fraction of the solar disk above a flat horizon line at ``horizon_el`` (exact circular segment).

    Inputs broadcast; 0 when the whole disk is below the line, 1 when it is fully above.
    """
    d = np.clip((np.asarray(sun_el, dtype=np.float64) - np.asarray(horizon_el, dtype=np.float64)) / radius_deg, -1.0, 1.0)
    return 0.5 + (d * np.sqrt(1.0 - d * d) + np.arcsin(d)) / np.pi


# --------------------------------------------------------------------------- table
def _to_unix(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


@dataclass
class Ephemeris:
    t_unix: np.ndarray      # (N,) int64, hourly UTC
    sun_vec: np.ndarray     # (N, 3) float64 unit vectors, Moon ME frame
    earth_vec: np.ndarray   # (N, 3) float64 unit vectors, Moon ME frame
    meta: dict | None = None

    @property
    def range_utc(self) -> tuple[datetime, datetime]:
        return (datetime.fromtimestamp(int(self.t_unix[0]), timezone.utc),
                datetime.fromtimestamp(int(self.t_unix[-1]), timezone.utc))

    def window(self, start_utc: datetime, hours: int):
        """Hourly slice starting at the hour of ``start_utc`` (rounded down) -> (t, sun_vec, earth_vec).

        Naive datetimes are interpreted as UTC. Raises ValueError if the slice is outside the table.
        """
        hours = int(hours)
        if hours < 0:
            raise ValueError("hours must be >= 0")
        t0 = _to_unix(start_utc) // 3600 * 3600
        step = int(self.t_unix[1] - self.t_unix[0]) if len(self.t_unix) > 1 else 3600
        first, last = int(self.t_unix[0]), int(self.t_unix[-1])
        end = t0 + (hours - 1) * step if hours else t0
        if t0 < first or end > last:
            lo, hi = self.range_utc
            raise ValueError(f"Requested window [{start_utc}, +{hours} h] is outside the ephemeris range "
                             f"[{lo:%Y-%m-%dT%H:%M:%SZ}, {hi:%Y-%m-%dT%H:%M:%SZ}]")
        i = (t0 - first) // step
        sl = slice(i, i + hours)
        return self.t_unix[sl], self.sun_vec[sl], self.earth_vec[sl]


def load_ephemeris(path=DEFAULT_PATH) -> Ephemeris:
    """Load the precomputed table and sanity-check it (hourly, unit vectors)."""
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        alt = DEFAULT_PATH.parent.parent.parent / path          # allow paths relative to the repo root
        path = alt if alt.exists() else path
    with np.load(path, allow_pickle=False) as z:
        t = z["t_unix"].astype(np.int64)
        sun, earth = z["sun_vec"].astype(np.float64), z["earth_vec"].astype(np.float64)
        meta = {k: str(z[k]) for k in z.files if z[k].ndim == 0}
    if not (len(t) == len(sun) == len(earth)):
        raise ValueError("Inconsistent ephemeris table lengths")
    if len(t) > 1 and not np.all(np.diff(t) == 3600):
        raise ValueError("Ephemeris table is not strictly hourly")
    return Ephemeris(t, sun, earth, meta)
