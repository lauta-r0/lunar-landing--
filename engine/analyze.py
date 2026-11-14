# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""LunaScout analysis: survival probability of a mission over its whole landing ellipse.

Public interface (CONTRACT section 5):
    get_meta() -> dict                 body of GET /api/meta
    analyze(request: dict) -> dict     body of POST /api/analyze (raises engine.errors.EngineError)

Pipeline of analyze():
    1. normalize the request and check DEM / ephemeris coverage
    2. sample points inside the landing ellipse (precomputed 50 m horizon grid, or a hex grid
       computed on the fly for small ellipses)
    3. Sun / Earth azimuth and elevation at every point and hour, compared with the terrain
       horizon at that azimuth -> sun_lit, earth_visible (points x hours)
    4. per-point mission metrics and the viable / risky / not_viable classification
    5. the same for every launch delay (shift the window by 24 h per day)
    6. recommendations: nearby targets with a higher survival probability
"""
from __future__ import annotations

import copy
import json
import math
import os
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import geo, horizon, metrics
from .errors import EngineError
from .grid import GridSet, HorizonGrid, load_grids
from .metrics import CLASS_NAMES, NOT_VIABLE, RISKY, VIABLE

SCHEMA_VERSION = "1.1"
REPO_ROOT = Path(__file__).resolve().parents[1]
EPHEMERIS_FILE = REPO_ROOT / "data" / "ephemeris" / "sun_earth_vectors.npz"

MARGIN_M = 1000.0            # analyzable area = DEM minus this margin (same as the horizon grid)
MIN_ELLIPSE_INSIDE = 0.8     # at least 80% of the ellipse must be inside the analyzable area
MAX_POINTS = 400
MIN_GRID_NODES = 40          # fewer grid nodes than this inside the ellipse -> on-the-fly hex grid
FLY_POINTS = 70              # target number of on-the-fly points
# threads for on-the-fly horizons (LUNASCOUT_THREADS overrides; Cloud Run with 2 vCPU -> 2)
FLY_THREADS = int(os.environ.get("LUNASCOUT_THREADS") or min(4, os.cpu_count() or 1))
REC_MAX_POINTS = 60          # points per recommendation candidate
SUN_HOURS_MIN_FRACTION = 0.6
AREA_OVER_SLOPE_MAX_PCT = 20.0
HILLSHADE_URL = "/api/static/hillshade.png"

DEFAULTS = {
    "landing_utc": "2027-03-10T14:00:00Z",
    "mission_days": 7,
    "ellipse": {"semi_major_m": 1000, "semi_minor_m": 600, "azimuth_deg": 0},
    "limits": {"max_dark_h": 50, "max_comm_gap_h": 72, "min_earth_pct": 50, "max_slope_deg": 8},
    "options": {"risk_margin": 0.2, "delay_days_max": 30, "include_recommendations": True,
                "observer_height_m": 2.0},
}
INPUT_LIMITS = {
    "mission_days": [1, 30], "semi_major_m": [50, 5000], "semi_minor_m": [50, 5000],
    "max_dark_h": [1, 400], "max_comm_gap_h": [1, 400], "min_earth_pct": [0, 100],
    "max_slope_deg": [1, 30], "delay_days_max": [0, 60],
}
SOURCES_HORIZONS = ("JPL Horizons System (Solar System Dynamics Group, NASA JPL) — "
                    "Sun and Earth topocentric positions")
SOURCES_REGIONAL = ("LRO LOLA 20 m/px and 40 m/px south polar LDEM (LRO-L-LOLA-4-GDR-V1.0, product v2.0, "
                    "NASA PDS Geosciences Node; Smith et al. 2017)")
MAX_SLOPE_SAMPLES = 250000   # slope samples for "ellipse area over max slope"
BEARING_NAMES = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

# Distinctive spots picked from the terrain itself (descriptive labels, NOT official names).
# They were chosen from the 50 m horizon grid using only geometry: 350 m mean slope, and the
# fraction of azimuths where an idealized Sun (elevation = colatitude * cos(azimuth) + season)
# clears the terrain horizon. See ENGINE.md, "Curated sites".
CURATED_BY_SITE: dict[str, list[dict]] = {
    "Site20v2": [
        {"id": "summit_plateau", "name": "Summit plateau (high, flat, long sunlight)", "lat": -85.47628, "lon": 31.39691},
        {"id": "western_bench", "name": "Western bench (flat, Earth in view)", "lat": -85.39890, "lon": 29.95361},
        {"id": "crater_floor", "name": "Crater floor (shadowed)", "lat": -85.23787, "lon": 33.95403},
        {"id": "sunlit_slope", "name": "Sunlit slope (steep)", "lat": -85.48962, "lon": 30.66935},
    ],
}
# Real landing sites, listed whenever they are inside the analyzable area (needs the regional DEM).
# Sources in ENGINE.md: LROC featured image "IM-2 Landing Region" (intended site) and LROC via
# Wikipedia "IM-2" / "Mons Mouton" (actual touchdown).
CURATED_REAL_SITES: list[dict] = [
    {"id": "im2_athena_intended", "name": "IM-2 Athena intended site", "lat": -84.78, "lon": 29.13},
    {"id": "im2_athena_actual", "name": "IM-2 Athena actual touchdown", "lat": -84.7906, "lon": 29.1957},
]


# =========================================================================== engine state
class _Engine:
    def __init__(self, terrain, grid, ephemeris, local_az_el, eph_is_stub: bool):
        self.terrain = terrain
        if isinstance(grid, HorizonGrid):
            grid = GridSet([grid])
        self.grid: GridSet | None = grid
        self.eph = ephemeris
        self.local_az_el = local_az_el
        self.eph_is_stub = eph_is_stub
        if grid is not None:
            # each node stands for the cell around it: pad by half the coarsest spacing so the fine
            # (y <= 130.0 km) and regional (y >= 130.1 km) areas touch without a gap
            pad = 0.5 * max(g.spacing for g in grid.grids)
            self.areas = [(a[0] - pad, a[1] - pad, a[2] + pad, a[3] + pad) for a in grid.areas]
        else:
            x0, y0, x1, y1 = terrain.bounds
            self.areas = [(x0 + MARGIN_M, y0 + MARGIN_M, x1 - MARGIN_M, y1 - MARGIN_M)]
        b = np.array(self.areas)
        self.area = (float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 2].max()), float(b[:, 3].max()))
        self.layered = len(getattr(terrain, "layers", [terrain])) > 1
        cx, cy = terrain.center_xy
        clat, clon = geo.xy_to_latlon(cx, cy)
        self.center = (float(clat), float(clon))
        self.hillshade_bounds = [float(v) for v in terrain.hillshade_bounds(2048)]
        self.fly_cache: OrderedDict = OrderedDict()
        self.target_cache: OrderedDict = OrderedDict()
        self.result_cache: OrderedDict = OrderedDict()

    def in_area(self, x, y):
        """True where a point is inside one of the analyzable rectangles."""
        x, y = np.asarray(x), np.asarray(y)
        out = np.zeros(np.broadcast(x, y).shape, dtype=bool)
        for x0, y0, x1, y1 in self.areas:
            out |= (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
        return out

    def fine_layer(self, x, y):
        """True where the 5 m tile (finest level) covers the point."""
        return np.asarray(self.terrain.layer_index_at(x, y)) == 0


_ENGINE: _Engine | None = None


def _load_ephemeris():
    """Real ephemeris (Agent 02) if present; the synthetic stub only if explicitly allowed."""
    try:
        from . import ephemeris as real          # noqa: PLC0415  (owned by Agent 02)
        eph = real.load_ephemeris(str(EPHEMERIS_FILE))
        return eph, real.local_az_el, False
    except (ImportError, FileNotFoundError, OSError) as exc:
        if os.environ.get("LUNASCOUT_ALLOW_STUB") == "1":
            from . import _ephemeris_stub as stub
            return stub.load_ephemeris_stub(), stub.local_az_el, True
        raise EngineError(
            "ephemeris_unavailable",
            "The Sun/Earth ephemeris (engine/ephemeris.py + data/ephemeris/sun_earth_vectors.npz) is not "
            f"available: {exc}. For development only, set LUNASCOUT_ALLOW_STUB=1 to use synthetic positions.",
        ) from exc


def _engine() -> _Engine:
    global _ENGINE
    if _ENGINE is None:
        from .terrain import get_terrain
        terrain = get_terrain()
        eph, az_el, is_stub = _load_ephemeris()
        _ENGINE = _Engine(terrain, load_grids(), eph, az_el, is_stub)
    return _ENGINE


def configure_engine(terrain=None, grid=None, ephemeris=None, local_az_el=None, is_stub=None):
    """Build the engine from explicit parts (tests, or custom data locations)."""
    global _ENGINE
    if terrain is None:
        from .terrain import get_terrain
        terrain = get_terrain()
    if ephemeris is None:
        ephemeris, az_el, stub = _load_ephemeris()
        local_az_el = local_az_el or az_el
        is_stub = stub if is_stub is None else is_stub
    _ENGINE = _Engine(terrain, grid, ephemeris, local_az_el, bool(is_stub))
    return _ENGINE


def reset_engine() -> None:
    global _ENGINE
    _ENGINE = None


# =========================================================================== small helpers
def _r(v, nd):
    return round(float(v), nd)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_dh(hours: float) -> str:
    h = int(round(float(hours)))
    return f"{h // 24} d {h % 24} h"


def _num(d: dict, key: str, lo: float, hi: float, default=None, integer: bool = False):
    v = d.get(key, default)
    if v is None or isinstance(v, bool):
        raise EngineError("invalid_request", f"'{key}' is required and must be a number")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise EngineError("invalid_request", f"'{key}' must be a number") from None
    if not math.isfinite(v) or v < lo or v > hi:
        raise EngineError("invalid_request", f"'{key}' must be between {lo:g} and {hi:g}")
    if integer:
        if abs(v - round(v)) > 1e-9:
            raise EngineError("invalid_request", f"'{key}' must be a whole number")
        return int(round(v))
    return v


def normalize_request(request: dict) -> dict:
    """Validate the request and fill defaults (CONTRACT 4.3). Returns a JSON-ready dict."""
    if not isinstance(request, dict):
        raise EngineError("invalid_request", "The request body must be a JSON object")
    target = request.get("target") or {}
    lat = _num(target, "lat", -90.0, 90.0)
    lon = _num(target, "lon", -360.0, 360.0)
    lon = (lon + 180.0) % 360.0 - 180.0

    raw_t = request.get("landing_utc", DEFAULTS["landing_utc"])
    try:
        dt = datetime.fromisoformat(str(raw_t).strip().replace("Z", "+00:00"))
    except ValueError:
        raise EngineError("invalid_request", "'landing_utc' must be ISO 8601, e.g. 2027-03-10T14:00:00Z") from None
    dt = (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc))
    dt = dt.replace(minute=0, second=0, microsecond=0)          # internal step: 1 hour

    lim = INPUT_LIMITS
    ell = {**DEFAULTS["ellipse"], **(request.get("ellipse") or {})}
    limits = {**DEFAULTS["limits"], **(request.get("limits") or {})}
    opts = {**DEFAULTS["options"], **(request.get("options") or {})}
    return {
        "target": {"lat": _r(lat, 5), "lon": _r(lon, 5)},
        "landing_utc": _iso(dt),
        "mission_days": _num(request, "mission_days", *lim["mission_days"], default=DEFAULTS["mission_days"], integer=True),
        "ellipse": {
            "semi_major_m": _num(ell, "semi_major_m", *lim["semi_major_m"]),
            "semi_minor_m": _num(ell, "semi_minor_m", *lim["semi_minor_m"]),
            "azimuth_deg": _num(ell, "azimuth_deg", -360.0, 720.0) % 360.0,
        },
        "limits": {
            "max_dark_h": _num(limits, "max_dark_h", *lim["max_dark_h"]),
            "max_comm_gap_h": _num(limits, "max_comm_gap_h", *lim["max_comm_gap_h"]),
            "min_earth_pct": _num(limits, "min_earth_pct", *lim["min_earth_pct"]),
            "max_slope_deg": _num(limits, "max_slope_deg", *lim["max_slope_deg"]),
        },
        "options": {
            "risk_margin": _num(opts, "risk_margin", 0.0, 0.9),
            "delay_days_max": _num(opts, "delay_days_max", *lim["delay_days_max"], integer=True),
            "include_recommendations": bool(opts.get("include_recommendations", True)),
            "observer_height_m": _num(opts, "observer_height_m", 0.1, 100.0),
        },
    }


# =========================================================================== ellipse geometry
class _Frame:
    """Landing ellipse in the map plane: center, axis directions (map unit vectors), map scale."""

    def __init__(self, lat: float, lon: float, semi_major: float, semi_minor: float, azimuth_deg: float):
        north, east, scale = geo.map_frame(lat, lon)
        x0, y0 = geo.latlon_to_xy(lat, lon)
        self.lat, self.lon = float(lat), float(lon)
        self.x0, self.y0 = float(x0), float(y0)
        self.scale = float(scale)
        a = math.radians(azimuth_deg)
        # azimuth is clockwise from LOCAL north (which is not the map's +y axis near the pole)
        self.major = north * math.cos(a) + east * math.sin(a)
        self.minor = -north * math.sin(a) + east * math.cos(a)
        self.a, self.b = float(semi_major), float(semi_minor)

    def uv(self, x, y):
        """Ground meters along the major / minor axis for map points."""
        dx, dy = np.asarray(x) - self.x0, np.asarray(y) - self.y0
        return ((dx * self.major[0] + dy * self.major[1]) / self.scale,
                (dx * self.minor[0] + dy * self.minor[1]) / self.scale)

    def inside(self, x, y, a=None, b=None):
        u, v = self.uv(x, y)
        return (u / (a or self.a)) ** 2 + (v / (b or self.b)) ** 2 <= 1.0 + 1e-12

    def xy(self, u, v):
        u, v = np.asarray(u) * self.scale, np.asarray(v) * self.scale
        return self.x0 + u * self.major[0] + v * self.minor[0], self.y0 + u * self.major[1] + v * self.minor[1]

    def half_extent_xy(self, a=None, b=None):
        a, b = (a or self.a) * self.scale, (b or self.b) * self.scale
        return (math.hypot(a * self.major[0], b * self.minor[0]), math.hypot(a * self.major[1], b * self.minor[1]))

    def polygon(self, n: int = 72):
        th = np.arange(n) * (2.0 * np.pi / n)
        return self.xy(self.a * np.cos(th), self.b * np.sin(th))

    def area_points(self, n: int = 600):
        """n points spread evenly over the ellipse area (sunflower pattern)."""
        k = np.arange(n) + 0.5
        r = np.sqrt(k / n)
        th = k * 2.399963229728653
        return self.xy(self.a * r * np.cos(th), self.b * r * np.sin(th))

    def hex_points(self, n_target: int):
        pitch = math.sqrt(math.pi * self.a * self.b / (n_target * 0.8660254))
        row_h = pitch * 0.8660254
        nv = int(math.ceil(self.b / row_h))
        nu = int(math.ceil(self.a / pitch)) + 1
        us, vs = [], []
        for jv in range(-nv, nv + 1):
            off = 0.5 * pitch if jv % 2 else 0.0
            u = np.arange(-nu, nu + 1) * pitch + off
            us.append(u)
            vs.append(np.full(u.size, jv * row_h))
        u, v = np.concatenate(us), np.concatenate(vs)
        keep = (u / self.a) ** 2 + (v / self.b) ** 2 <= 1.0
        x, y = self.xy(u[keep], v[keep])
        return x, y, pitch


def _grid_select(grid: GridSet, frame: _Frame, a=None, b=None):
    ex, ey = frame.half_extent_xy(a, b)
    return grid.select(lambda x, y: frame.inside(x, y, a, b),
                       frame.x0 - ex, frame.y0 - ey, frame.x0 + ex, frame.y0 + ey)


def _sample_points(eng: _Engine, frame: _Frame, h_obs: float):
    """Sample points inside the ellipse. Returns a dict with x, y, lat, lon, slope, horizon, info."""
    grid = eng.grid
    grid_ok = grid is not None and abs(grid.observer_height_m - h_obs) < 1e-6
    if grid_ok:
        sel = _grid_select(grid, frame)
        n_all = GridSet.count(sel)
        if n_all >= MIN_GRID_NODES:
            sel, spacing = grid.thin(sel, MAX_POINTS)
            out = grid.gather(sel)
            out.update({"mode": "grid", "n_candidates": n_all, "spacing_m": float(spacing)})
            return out

    key = (round(frame.x0, 1), round(frame.y0, 1), frame.a, frame.b,
           round(float(np.degrees(np.arctan2(frame.major[0], frame.major[1]))), 4), h_obs)
    if key in eng.fly_cache:
        eng.fly_cache.move_to_end(key)
        return eng.fly_cache[key]
    x, y, pitch = frame.hex_points(FLY_POINTS)
    keep = eng.in_area(x, y)
    x, y = x[keep], y[keep]
    elev, _reach, _z0 = horizon.compute_horizons_xy(x, y, h_obs, eng.terrain, workers=FLY_THREADS)
    lat, lon = geo.xy_to_latlon(x, y)
    if grid is None:
        reason = "no_grid"
    elif not grid_ok:
        reason = "observer_height"
    else:
        reason = "small_ellipse"
    out = {"mode": "on_the_fly", "x": x, "y": y, "lat": lat, "lon": lon,
           "slope": eng.terrain.slope_at(x, y), "horizon": elev,
           "n_candidates": int(x.size), "spacing_m": pitch, "reason": reason}
    eng.fly_cache[key] = out
    while len(eng.fly_cache) > 8:
        eng.fly_cache.popitem(last=False)
    return out


def _target_horizon(eng: _Engine, x: float, y: float, h_obs: float) -> horizon.Horizon:
    key = (round(x, 2), round(y, 2), h_obs)
    if key in eng.target_cache:
        eng.target_cache.move_to_end(key)
        return eng.target_cache[key]
    hz = horizon.compute_horizon_xy(x, y, h_obs, eng.terrain)
    eng.target_cache[key] = hz
    while len(eng.target_cache) > 64:
        eng.target_cache.popitem(last=False)
    return hz


def _area_over_slope_pct(eng: _Engine, frame: _Frame, max_slope: float) -> float:
    """% of the ellipse area steeper than max_slope, from a regular lattice of slope samples.

    The lattice spacing is the 5 m pixel size (coarser only for huge ellipses), and each sample reads
    the finest slope raster available there (5 m on the tile, 20 m outside it).
    """
    t = eng.terrain
    ex, ey = frame.half_extent_xy()
    step = max(float(t.pixel_m), math.sqrt(4.0 * ex * ey / MAX_SLOPE_SAMPLES))
    xs = np.arange(frame.x0 - ex + 0.5 * step, frame.x0 + ex, step)
    ys = np.arange(frame.y0 - ey + 0.5 * step, frame.y0 + ey, step)
    xx, yy = np.meshgrid(xs, ys)
    inside = frame.inside(xx, yy)
    if not inside.any():
        return float("nan")
    slp = t.slope_at(xx[inside], yy[inside])
    slp = slp[np.isfinite(slp)]
    return float(100.0 * np.mean(slp > max_slope)) if slp.size else float("nan")


def _visibility(eng: _Engine, lat, lon, hor, sun_vec, earth_vec) -> dict:
    """Sun / Earth az, el, horizon at their azimuth, and visibility flags, all (P, T)."""
    sun_az, sun_el = eng.local_az_el(sun_vec, np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64))
    earth_az, earth_el = eng.local_az_el(earth_vec, np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64))
    h_sun = horizon.interp_horizon(hor, sun_az)
    h_earth = horizon.interp_horizon(hor, earth_az)
    return {"sun_az": sun_az, "sun_el": sun_el, "h_sun": h_sun, "sun_lit": sun_el > h_sun,
            "earth_az": earth_az, "earth_el": earth_el, "h_earth": h_earth, "earth_visible": earth_el > h_earth}


def _out_of_coverage(eng: _Engine, why: str):
    clat, clon = eng.center
    raise EngineError(
        "out_of_coverage",
        f"{why} The loaded DEM is {eng.terrain.name}. Try a point near lat {clat:.3f}, lon {clon:.3f}.",
        {"suggested_target": {"lat": _r(clat, 5), "lon": _r(clon, 5)}},
    )


# =========================================================================== meta
def _curated_sites(eng: _Engine) -> list[dict]:
    clat, clon = eng.center
    sites = [{"id": "mons_mouton_center", "name": "Mons Mouton (DEM center)", "lat": _r(clat, 5), "lon": _r(clon, 5)}]
    for s in CURATED_BY_SITE.get(eng.terrain.site_id, []) + CURATED_REAL_SITES:
        x, y = geo.latlon_to_xy(s["lat"], s["lon"])
        if bool(eng.in_area(x, y)):
            sites.append(dict(s))
    return sites


def get_meta() -> dict:
    """Body of GET /api/meta (CONTRACT 4.2), filled from the real DEM and ephemeris."""
    eng = _engine()
    x0, y0, x1, y1 = eng.area
    ex = np.concatenate([np.linspace(x0, x1, 101), np.linspace(x0, x1, 101), np.full(101, x0), np.full(101, x1)])
    ey = np.concatenate([np.full(101, y0), np.full(101, y1), np.linspace(y0, y1, 101), np.linspace(y0, y1, 101)])
    elat, elon = geo.xy_to_latlon(ex, ey)
    t_unix = np.asarray(eng.eph.t_unix)
    return {
        "schema_version": SCHEMA_VERSION,
        "coverage": {
            "dem_name": eng.terrain.name,
            "bounds_xy_m": [_r(x0, 1), _r(y0, 1), _r(x1, 1), _r(y1, 1)],
            "center_lat": _r(eng.center[0], 5),
            "center_lon": _r(eng.center[1], 5),
            "approx_bounds_latlon": {"lat_min": _r(elat.min(), 5), "lat_max": _r(elat.max(), 5),
                                     "lon_min": _r(elon.min(), 5), "lon_max": _r(elon.max(), 5)},
        },
        "ephemeris_range_utc": [_iso(datetime.fromtimestamp(int(t_unix[0]), timezone.utc)),
                                _iso(datetime.fromtimestamp(int(t_unix[-1]), timezone.utc))],
        "map": {"hillshade_url": HILLSHADE_URL, "hillshade_bounds_xy_m": eng.hillshade_bounds,
                "crs_proj4": geo.crs_proj4()},
        "curated_sites": _curated_sites(eng),
        "defaults": copy.deepcopy(DEFAULTS),
        "input_limits": copy.deepcopy(INPUT_LIMITS),
    }


# =========================================================================== analysis
def analyze(request: dict) -> dict:
    """Body of POST /api/analyze (CONTRACT 4.3). Identical requests are served from a small cache."""
    eng = _engine()
    req = normalize_request(request)
    key = json.dumps(req, sort_keys=True)
    if key in eng.result_cache:
        eng.result_cache.move_to_end(key)
        return copy.deepcopy(eng.result_cache[key])
    result = _analyze(eng, req)
    eng.result_cache[key] = result
    while len(eng.result_cache) > 32:
        eng.result_cache.popitem(last=False)
    return copy.deepcopy(result)


def _analyze(eng: _Engine, req: dict) -> dict:
    t_start = time.perf_counter()
    warnings: list[str] = []
    lat, lon = req["target"]["lat"], req["target"]["lon"]
    ell, limits, opts = req["ellipse"], req["limits"], req["options"]
    h_obs = opts["observer_height_m"]
    mission_h = req["mission_days"] * 24
    n_delay = opts["delay_days_max"]
    landing = datetime.fromisoformat(req["landing_utc"].replace("Z", "+00:00"))

    # ---- 1. coverage ------------------------------------------------------------------
    frame = _Frame(lat, lon, ell["semi_major_m"], ell["semi_minor_m"], ell["azimuth_deg"])
    tx, ty = frame.x0, frame.y0
    if not bool(eng.in_area(tx, ty)):
        _out_of_coverage(eng, "Target is outside the analyzable area of the DEM.")
    ax, ay = frame.area_points(600)
    inside_frac = float(np.mean(eng.in_area(ax, ay)))
    if inside_frac < MIN_ELLIPSE_INSIDE:
        _out_of_coverage(eng, f"Only {100 * inside_frac:.0f}% of the landing ellipse is inside the DEM "
                              f"(at least {100 * MIN_ELLIPSE_INSIDE:.0f}% is required).")
    if inside_frac < 0.999:
        warnings.append(f"{100 * (1 - inside_frac):.0f}% of the landing ellipse is outside the DEM and was ignored.")

    # ---- 2. ephemeris window ----------------------------------------------------------
    total_h = mission_h + 24 * n_delay
    t_unix = np.asarray(eng.eph.t_unix)
    t0 = int(landing.timestamp())
    if t0 < int(t_unix[0]) or t0 + (total_h - 1) * 3600 > int(t_unix[-1]):
        lo = _iso(datetime.fromtimestamp(int(t_unix[0]), timezone.utc))
        hi = _iso(datetime.fromtimestamp(int(t_unix[-1]), timezone.utc))
        raise EngineError(
            "out_of_ephemeris_range",
            f"The landing date plus the mission ({req['mission_days']} d) and the delay range ({n_delay} d) must "
            f"be inside the precomputed ephemeris ({lo} to {hi}).",
        )
    _t, sun_vec, earth_vec = eng.eph.window(landing, total_h)
    sun_vec, earth_vec = np.asarray(sun_vec, dtype=np.float64), np.asarray(earth_vec, dtype=np.float64)

    # ---- 3. sample points and visibility ----------------------------------------------
    pts = _sample_points(eng, frame, h_obs)
    n_pts = int(pts["x"].size)
    if n_pts == 0:
        _out_of_coverage(eng, "No sample point of the landing ellipse is inside the DEM.")
    vis = _visibility(eng, pts["lat"], pts["lon"], pts["horizon"], sun_vec, earth_vec)

    thz = _target_horizon(eng, tx, ty, h_obs)
    tvis = _visibility(eng, [lat], [lon], thz.elevation_deg[None, :], sun_vec, earth_vec)
    t_slope = float(eng.terrain.slope_at(tx, ty))
    t_slope_arr = np.array([t_slope])

    # ---- 4. delay loop: metrics + classification for every delay ---------------------
    risk_margin = opts["risk_margin"]
    delay_curve = []
    first = None
    for d in range(n_delay + 1):
        sl = slice(24 * d, 24 * d + mission_h)
        m = metrics.point_metrics(vis["sun_lit"][:, sl], vis["earth_visible"][:, sl])
        codes, fail, risk = metrics.classify(m, pts["slope"], limits, risk_margin, mission_h)
        tm = metrics.point_metrics(tvis["sun_lit"][:, sl], tvis["earth_visible"][:, sl])
        tcodes, tfail, trisk = metrics.classify(tm, t_slope_arr, limits, risk_margin, mission_h)
        n_viable = int(np.sum(codes == VIABLE))
        delay_curve.append({"delay_days": d, "survival_probability": _r(n_viable / n_pts, 3),
                            "target_viable": bool(tcodes[0] != NOT_VIABLE)})
        if d == 0:
            first = (m, codes, fail, risk, tm, tcodes, tfail, trisk)
    m, codes, fail, risk, tm, tcodes, _tfail, _trisk = first
    tolerance = -1
    for entry in delay_curve:
        if not entry["target_viable"]:
            break
        tolerance = entry["delay_days"]

    n_viable, n_risky = int(np.sum(codes == VIABLE)), int(np.sum(codes == RISKY))
    n_bad = n_pts - n_viable - n_risky
    p_survive = n_viable / n_pts

    # ---- 5. target metrics ------------------------------------------------------------
    area_pct = _area_over_slope_pct(eng, frame, limits["max_slope_deg"])
    if not math.isfinite(area_pct):
        area_pct = float(100.0 * np.mean(pts["slope"] > limits["max_slope_deg"]))
    sun_el0 = float(tvis["sun_el"][0, 0])
    lit0 = bool(tm["sun_at_touchdown"][0])
    sun_h, dark_h = float(tm["sun_hours"][0]), float(tm["longest_dark_h"][0])
    e_pct, gap_h = float(tm["earth_pct"][0]), float(tm["longest_comm_gap_h"][0])
    sunset_h, earthset_h = float(tm["hours_until_sunset"][0]), float(tm["hours_until_earthset"][0])
    if tolerance < 0:
        tol_display = "Not viable at 0 days"
    elif tolerance >= n_delay:
        tol_display = f"≥ {tolerance} days"
    else:
        tol_display = f"{tolerance} day" + ("" if tolerance == 1 else "s")

    def _until(h):
        return f"> {_fmt_dh(mission_h)}" if h >= mission_h else _fmt_dh(h)

    target_metrics = [
        {"id": "sun_at_touchdown", "label": "Sun at touchdown", "value": int(lit0), "unit": "bool",
         "display": f"{'Yes' if lit0 else 'No'} · el {sun_el0:.1f}°", "limit_display": "Required", "pass": lit0},
        {"id": "sun_hours", "label": "Hours of sunlight", "value": _r(sun_h, 1), "unit": "h",
         "display": f"{sun_h:.0f} h / {mission_h} h",
         "limit_display": f"≥ {100 * SUN_HOURS_MIN_FRACTION:.0f}% of mission",
         "pass": bool(sun_h >= SUN_HOURS_MIN_FRACTION * mission_h)},
        {"id": "longest_dark", "label": "Longest darkness period", "value": _r(dark_h, 1), "unit": "h",
         "display": f"{dark_h:.0f} h", "limit_display": f"≤ {limits['max_dark_h']:g} h (battery)",
         "pass": bool(dark_h <= limits["max_dark_h"])},
        {"id": "earth_pct", "label": "Mission time with Earth visible", "value": _r(e_pct, 1), "unit": "%",
         "display": f"{e_pct:.0f}%", "limit_display": f"≥ {limits['min_earth_pct']:g}%",
         "pass": bool(e_pct >= limits["min_earth_pct"])},
        {"id": "longest_comm_gap", "label": "Longest comms gap", "value": _r(gap_h, 1), "unit": "h",
         "display": _fmt_dh(gap_h), "limit_display": f"≤ {limits['max_comm_gap_h']:g} h",
         "pass": bool(gap_h <= limits["max_comm_gap_h"])},
        {"id": "hours_until_sunset", "label": "Time until sunset", "value": _r(sunset_h, 1), "unit": "h",
         "display": _until(sunset_h), "limit_display": f"≥ mission ({_fmt_dh(mission_h)})",
         "pass": bool(sunset_h >= mission_h)},
        {"id": "hours_until_earthset", "label": "Time until Earthset", "value": _r(earthset_h, 1), "unit": "h",
         "display": _until(earthset_h), "limit_display": "Reference", "pass": None},
        {"id": "area_over_slope", "label": "Ellipse area over max slope", "value": _r(area_pct, 1), "unit": "%",
         "display": f"{area_pct:.0f}% > {limits['max_slope_deg']:g}°",
         "limit_display": f"≤ {AREA_OVER_SLOPE_MAX_PCT:.0f}% of ellipse",
         "pass": bool(area_pct <= AREA_OVER_SLOPE_MAX_PCT)},
        {"id": "delay_tolerance", "label": "Launch-delay tolerance", "value": int(tolerance), "unit": "days",
         "display": tol_display, "limit_display": "Days the target stays viable", "pass": None},
    ]
    checks = [tmx["pass"] for tmx in target_metrics if tmx["pass"] is not None]

    # ---- 6. points --------------------------------------------------------------------
    # slope source per point: 5 m tile, or the coarser 20 m polar DEM outside it (underestimates
    # local steepness; flagged per point and in the warnings)
    fine_pts = eng.fine_layer(pts["x"], pts["y"])
    target_fine = bool(eng.fine_layer(tx, ty))
    coarse_px = float(eng.terrain.layers[1].pixel_m) if eng.layered else float(eng.terrain.pixel_m)
    fine_px = float(eng.terrain.pixel_m)
    points = []
    for i in range(n_pts):
        points.append({
            "id": i, "x_m": _r(pts["x"][i], 1), "y_m": _r(pts["y"][i], 1),
            "lat": _r(pts["lat"][i], 5), "lon": _r(pts["lon"][i], 5),
            "class": CLASS_NAMES[int(codes[i])],
            "reasons": metrics.reasons_for(i, codes, fail, risk),
            "slope_deg": _r(pts["slope"][i], 3),
            "slope_dem_m": fine_px if fine_pts[i] else coarse_px,
            "slope_coarse": bool(not fine_pts[i]),
            "sun_hours": _r(m["sun_hours"][i], 1), "longest_dark_h": _r(m["longest_dark_h"][i], 1),
            "earth_pct": _r(m["earth_pct"][i], 1), "longest_comm_gap_h": _r(m["longest_comm_gap_h"][i], 1),
            "hours_until_sunset": _r(m["hours_until_sunset"][i], 1),
            "sun_at_touchdown": bool(m["sun_at_touchdown"][i]),
        })

    # ---- 7. time series and horizon profile of the target ------------------------------
    ms = slice(0, mission_h)
    r3 = lambda a: [round(float(v), 3) for v in a]      # noqa: E731
    timeseries = {
        "t0_utc": req["landing_utc"], "step_h": 1, "n": mission_h,
        "sun_az_deg": r3(tvis["sun_az"][0, ms]), "sun_el_deg": r3(tvis["sun_el"][0, ms]),
        "horizon_at_sun_deg": r3(tvis["h_sun"][0, ms]),
        "sun_lit": [int(v) for v in tvis["sun_lit"][0, ms]],
        "earth_az_deg": r3(tvis["earth_az"][0, ms]), "earth_el_deg": r3(tvis["earth_el"][0, ms]),
        "horizon_at_earth_deg": r3(tvis["h_earth"][0, ms]),
        "earth_visible": [int(v) for v in tvis["earth_visible"][0, ms]],
        # display only (CONTRACT section 2): fraction of the solar disk above the horizon
        "sun_visible_fraction": r3(metrics.sun_visible_fraction(tvis["sun_el"][0, ms], tvis["h_sun"][0, ms])),
    }
    horizon_profile = {"az_step_deg": thz.az_step_deg, "elevation_deg": r3(thz.elevation_deg)}

    # ---- 8. warnings ------------------------------------------------------------------
    reach_km = thz.reach_m / 1000.0
    short = float(np.mean(thz.reach_m < horizon.MIN_TRUSTED_REACH_M))
    if eng.layered:
        rng = (f"{reach_km.max():.0f}" if reach_km.max() - reach_km.min() < 1.0
               else f"{reach_km.min():.0f}–{reach_km.max():.0f}")
        msg = (f"Horizon is modeled out to {rng} km from the target: LOLA 5 m/px "
               "tile nearby, LOLA 20 m and 40 m/px polar DEM beyond it. Terrain farther than "
               f"{horizon.MAX_RAY_M / 1000:.0f} km is not modeled.")
    else:
        msg = (f"Horizon is modeled only out to the DEM edge ({reach_km.min():.1f}–{reach_km.max():.1f} km from the "
               "target, depending on direction); more distant peaks may block additional sunlight or Earth "
               "visibility.")
    if short > 0:
        msg += f" {100 * short:.0f}% of directions reach less than {horizon.MIN_TRUSTED_REACH_M / 1000:.0f} km."
    warnings.append(msg)
    if eng.layered and not bool(np.all(fine_pts)):
        share = 100.0 * float(np.mean(~fine_pts))
        warnings.append(
            f"{share:.0f}% of the sample points (target {'inside' if target_fine else 'outside'} the tile) lie "
            "outside the LOLA 5 m/px tile: their terrain and slope come from the 20 m/px LOLA polar DEM, which "
            "smooths features smaller than about 40 m, so slopes there underestimate the local steepness "
            "(points flagged with slope_coarse = true). Tip-over risk from boulders and small craters is not "
            "captured.")
    if pts["mode"] == "on_the_fly":
        why = {"small_ellipse": "Small ellipse", "no_grid": "Precomputed horizon grid not available",
               "observer_height": "Observer height differs from the precomputed grid"}[pts["reason"]]
        warnings.append(f"{why}: {n_pts} sample points computed on the fly (hexagonal grid, "
                        f"{pts['spacing_m']:.0f} m spacing).")
    elif pts["n_candidates"] > n_pts:
        warnings.append(f"Large ellipse: sampled every {pts['spacing_m']:.0f} m ({n_pts} of "
                        f"{pts['n_candidates']} grid nodes).")
    warnings.append("Survival probability assumes the landing point is uniformly distributed inside the ellipse.")
    if eng.eph_is_stub:
        warnings.insert(0, "SYNTHETIC EPHEMERIS (development stub): Sun and Earth positions are NOT real. "
                           "Do not use these results.")

    # ---- 9. recommendations -----------------------------------------------------------
    recommendations = []
    if opts["include_recommendations"]:
        if eng.grid is None:
            warnings.append("Recommendations need the precomputed horizon grid, which is not available.")
        else:
            recommendations = _recommend(eng, req, frame, p_survive, sun_vec[:mission_h], earth_vec[:mission_h])

    # ---- 10. map block ----------------------------------------------------------------
    ex, ey = frame.half_extent_xy()
    half_w = max(2500.0, 1.25 * ex, 1.5 * 1.25 * ey)
    half_h = half_w / 1.5
    px, py = frame.polygon(72)
    map_block = {
        "hillshade_url": HILLSHADE_URL,
        "hillshade_bounds_xy_m": eng.hillshade_bounds,
        "view_bounds_xy_m": [_r(tx - half_w, 1), _r(ty - half_h, 1), _r(tx + half_w, 1), _r(ty + half_h, 1)],
        "ellipse_polygon_xy_m": [[_r(a, 1), _r(b, 1)] for a, b in zip(px, py)],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "is_sample": bool(eng.eph_is_stub),
        "computed_utc": _iso(datetime.now(timezone.utc)),
        "compute_ms": int(round((time.perf_counter() - t_start) * 1000.0)),
        "inputs": req,
        "coverage": {"in_coverage": True, "dem_name": eng.terrain.name,
                     "message": (None if target_fine else
                                 "Target is outside the LOLA 5 m/px tile; terrain from the 20 m/px LOLA polar DEM.")},
        "target": {"lat": _r(lat, 5), "lon": _r(lon, 5), "x_m": _r(tx, 1), "y_m": _r(ty, 1),
                   "elevation_m": _r(thz.ground_height_m, 1), "slope_deg": _r(t_slope, 3),
                   "slope_dem_m": fine_px if target_fine else coarse_px, "slope_coarse": not target_fine},
        "summary": {
            "n_points": n_pts, "viable": n_viable, "risky": n_risky, "not_viable": n_bad,
            "survival_probability": _r(p_survive, 3),
            "survival_probability_incl_risky": _r((n_viable + n_risky) / n_pts, 3),
            "checks_passed": int(sum(bool(c) for c in checks)), "checks_total": len(checks),
            "verdict": CLASS_NAMES[int(tcodes[0])],
        },
        "target_metrics": target_metrics,
        "points": points,
        "timeseries": timeseries,
        "horizon_profile": horizon_profile,
        "delay_curve": delay_curve,
        "delay_tolerance_days": int(tolerance),
        "recommendations": recommendations,
        "map": map_block,
        "warnings": warnings,
        "sources": [SOURCES_HORIZONS,
                    f"LRO {getattr(eng.terrain, 'short_name', eng.terrain.name)} (Barker et al. 2021, NASA GSFC PGDA)"]
                   + ([SOURCES_REGIONAL] if eng.layered else []),
    }


# =========================================================================== recommendations
def _recommend(eng: _Engine, req: dict, frame: _Frame, p_current: float, sun_vec, earth_vec) -> list[dict]:
    """Nearby targets with a higher survival probability (coarser sampling, no delay curve)."""
    grid = eng.grid
    ell, limits, opts = req["ellipse"], req["limits"], req["options"]
    mission_h = req["mission_days"] * 24
    lat0, lon0 = frame.lat, frame.lon

    cands = []
    for dist_km in (1.0, 2.0, 3.0):
        for k, name in enumerate(BEARING_NAMES):
            clat, clon = geo.destination(lat0, lon0, 45.0 * k, dist_km * 1000.0)
            cands.append((f"{dist_km:.1f} km {name} of target", float(clat), float(clon), dist_km))
    for s in _curated_sites(eng):
        d_km = float(geo.great_circle_distance(lat0, lon0, s["lat"], s["lon"])) / 1000.0
        if d_km > 0.2:
            cands.append((s["name"], s["lat"], s["lon"], d_km))

    # small ellipses: sample at least a 100 m neighborhood so every candidate has grid nodes
    a_eff, b_eff = max(frame.a, 100.0), max(frame.b, 100.0)
    blocks, meta = [], []
    for name, clat, clon, d_km in cands:
        f = _Frame(clat, clon, frame.a, frame.b, ell["azimuth_deg"])
        if not bool(eng.in_area(f.x0, f.y0)):
            continue
        ax, ay = f.area_points(200)
        if float(np.mean(eng.in_area(ax, ay))) < MIN_ELLIPSE_INSIDE:
            continue
        sel = _grid_select(grid, f, a_eff, b_eff)
        if not sel:
            continue
        coarse, _sp = grid.thin(sel, REC_MAX_POINTS, min_spacing=2.0 * grid.spacing)
        sel = coarse if GridSet.count(coarse) >= 12 else grid.thin(sel, REC_MAX_POINTS)[0]
        g = grid.gather(sel)
        blocks.append(g)
        meta.append((name, clat, clon, d_km, int(g["x"].size)))
    if not blocks:
        return []

    lat_all = np.concatenate([b["lat"] for b in blocks])
    lon_all = np.concatenate([b["lon"] for b in blocks])
    hor_all = np.concatenate([b["horizon"] for b in blocks])
    slope_all = np.concatenate([b["slope"] for b in blocks])
    vis = _visibility(eng, lat_all, lon_all, hor_all, sun_vec, earth_vec)
    m = metrics.point_metrics(vis["sun_lit"], vis["earth_visible"])
    codes, _fail, _risk = metrics.classify(m, slope_all, limits, opts["risk_margin"], mission_h)
    out, pos = [], 0
    for name, clat, clon, d_km, n in meta:
        p = float(np.mean(codes[pos:pos + n] == VIABLE))
        pos += n
        if p > p_current + 1e-9:
            out.append({"name": name, "lat": _r(clat, 5), "lon": _r(clon, 5), "distance_km": _r(d_km, 1),
                        "survival_probability": _r(p, 3), "delta_pts": int(round(100.0 * (p - p_current)))})
    out.sort(key=lambda r: (-r["survival_probability"], r["distance_km"]))
    return out[:3]
