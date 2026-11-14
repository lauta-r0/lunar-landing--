# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""SYNTHETIC ephemeris stub. NOT REAL DATA. For tests and for development only.

It follows the interface of engine/ephemeris.py (CONTRACT section 5, owned by Agent 02) so the
analysis can be written and tested before the real JPL Horizons vectors exist. The motions are
simple sinusoids with roughly the right periods and amplitudes:

- Sun: sub-solar longitude drifts westward once per synodic month (29.53 d); sub-solar latitude
  oscillates +/-1.54 deg over a draconic year (346.62 d).
- Earth: sub-Earth point librates +/-7.9 deg in longitude (27.55 d) and +/-6.7 deg in latitude (27.21 d).

Any analysis produced with this stub is flagged "is_sample": true and carries a warning.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

IS_STUB = True
T0_UNIX = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
T1_UNIX = int(datetime(2028, 12, 31, 23, tzinfo=timezone.utc).timestamp())


def _unit(lat_deg, lon_deg):
    phi, lam = np.radians(lat_deg), np.radians(lon_deg)
    return np.stack([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)], axis=-1)


class StubEphemeris:
    """Hourly synthetic Sun/Earth unit vectors in the Moon ME frame (same fields as Ephemeris)."""

    is_stub = True

    def __init__(self):
        self.t_unix = np.arange(T0_UNIX, T1_UNIX + 1, 3600, dtype=np.int64)
        days = (self.t_unix - T0_UNIX) / 86400.0
        sun_lon = (-360.0 * days / 29.530589 + 40.0 + 180.0) % 360.0 - 180.0
        sun_lat = 1.54 * np.sin(2.0 * np.pi * days / 346.62 + 2.4)
        earth_lon = 7.9 * np.sin(2.0 * np.pi * days / 27.555 + 0.7)
        earth_lat = 6.7 * np.sin(2.0 * np.pi * days / 27.212 + 1.9)
        self.sun_vec = _unit(sun_lat, sun_lon)
        self.earth_vec = _unit(earth_lat, earth_lon)

    def window(self, start_utc: datetime, hours: int):
        """(t_unix, sun_vec, earth_vec) for `hours` hourly samples starting at start_utc."""
        if start_utc.tzinfo is None:
            start_utc = start_utc.replace(tzinfo=timezone.utc)
        i0 = int((int(start_utc.timestamp()) - T0_UNIX) // 3600)
        if i0 < 0 or i0 + hours > self.t_unix.size:
            raise ValueError("requested window is outside the ephemeris range")
        sl = slice(i0, i0 + hours)
        return self.t_unix[sl], self.sun_vec[sl], self.earth_vec[sl]


def load_ephemeris_stub() -> StubEphemeris:
    return StubEphemeris()


def local_az_el(vecs: np.ndarray, lat_deg: np.ndarray, lon_deg: np.ndarray):
    """vecs (T, 3) unit vectors in ME; lat/lon (P,) degrees -> az, el of shape (P, T), degrees.

    Azimuth clockwise from local north, [0, 360). Elevation above the local horizontal plane.
    """
    vecs = np.asarray(vecs, dtype=np.float64)
    phi = np.radians(np.atleast_1d(np.asarray(lat_deg, dtype=np.float64)))
    lam = np.radians(np.atleast_1d(np.asarray(lon_deg, dtype=np.float64)))
    sp, cp, sl, cl = np.sin(phi), np.cos(phi), np.sin(lam), np.cos(lam)
    up = np.stack([cp * cl, cp * sl, sp], axis=1)                  # (P, 3)
    east = np.stack([-sl, cl, np.zeros_like(sl)], axis=1)
    north = np.stack([-sp * cl, -sp * sl, cp], axis=1)
    el = np.degrees(np.arcsin(np.clip(up @ vecs.T, -1.0, 1.0)))
    az = np.degrees(np.arctan2(east @ vecs.T, north @ vecs.T)) % 360.0
    return az, el
