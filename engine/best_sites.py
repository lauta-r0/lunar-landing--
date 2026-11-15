# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Best landing areas across the whole analyzable region (CONTRACT 4.7, schema 1.6).

Public interface:
    best_sites(request: dict) -> dict     body of POST /api/best-sites (raises engine.errors.EngineError)

Method (ENGINE.md, "Best sites"):
    1. take the precomputed horizon grids on one coarse lattice (every STRIDE_M meters)
    2. classify every lattice node for the requested date and mission with the SAME rules as
       analyze() (CONTRACT 4.4). Two exact shortcuts skip most of the work: nodes steeper than the
       slope limit and nodes dark at the touchdown hour can never be viable.
    3. "survival probability if you aim here" = share of viable nodes inside the user's landing
       ellipse centered on each lattice cell (one FFT correlation per ellipse orientation bin)
    4. pick well separated maxima, then re-evaluate each one with the full analyze() sampling, so the
       probability of a listed site is the number the full analysis shows when it is selected

Data resolution: the region filter and the labels look at the whole ellipse, not at its center.
"5m" / "20m" keep an aim point only if at least 95% of its ellipse is on that data. Sites are
always ranked by their real survival probability (no adjustment for the data resolution); equal
probabilities go to the site with the larger share of its ellipse on 5 m data.

The heatmap is approximate (coarse sampling); the listed sites are not.
"""
from __future__ import annotations

import base64
import copy
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np

from . import analyze as az
from . import geo, metrics
from .errors import EngineError
from .grid import GridSet
from .metrics import RISKY, VIABLE

STRIDE_M = 200.0             # lattice spacing of the regional scan (heatmap cell size)
CHUNK_ELEMS = 250_000        # points x hours per visibility chunk (bounds the transient memory)
REGIONS = ("all", "5m", "20m")
DEFAULT_REGION = "5m"        # the most reliable data
REGION_MIN_SHARE = 0.95      # "5m" / "20m": at least this share of the ellipse on that data
MAX_SITES_DEFAULT = 5
MAX_SITES_LIMIT = 10
N_CANDIDATES = 24            # maxima re-evaluated with the full sampling before ranking
MIN_SEPARATION_M = 1500.0    # listed sites are at least this far apart (or 2 x semi-major, if larger)
ORIENT_BIN_DEG = 2.0         # local north turns ~16 deg across the region: one ellipse kernel per bin
MIN_KERNEL_NODES = 5         # ellipses smaller than this many lattice nodes are scanned on a wider disc
SMALL_ELLIPSE_M = 100.0      # same floor as the "Recommended nearby" sampling
HEAT_MAX = 254               # uint8 0..254 = probability 0..1; 255 = invalid cell
HEAT_INVALID = 255

_LOCK = threading.Lock()     # one scan at a time: bounds the peak memory and the CPU use


# =========================================================================== request
def normalize_request(request: dict) -> dict:
    """Validate a best-sites request and fill defaults. Same fields as analyze, without a target."""
    if not isinstance(request, dict):
        raise EngineError("invalid_request", "The request body must be a JSON object")
    base = az.normalize_request({
        "target": {"lat": -85.0, "lon": 0.0},            # placeholder: the scan has no target
        **{k: request[k] for k in ("landing_utc", "mission_days", "ellipse", "limits", "options") if k in request},
    })
    region = request.get("region", DEFAULT_REGION)
    if region is None:
        region = DEFAULT_REGION
    if region not in REGIONS:
        raise EngineError("invalid_request", f"'region' must be one of {', '.join(REGIONS)}")
    max_sites = az._num(request, "max_sites", 1, MAX_SITES_LIMIT, default=MAX_SITES_DEFAULT, integer=True)
    return {
        "landing_utc": base["landing_utc"],
        "mission_days": base["mission_days"],
        "ellipse": base["ellipse"],
        "limits": base["limits"],
        "options": {"risk_margin": base["options"]["risk_margin"],
                    "observer_height_m": base["options"]["observer_height_m"]},
        "region": region,
        "max_sites": max_sites,
    }


# =========================================================================== lattice
class _Lattice:
    """Grid nodes that fall on one regular lattice (spacing S), as rasters with row 0 at y_min."""

    def __init__(self, eng, stride: float):
        grids = eng.grid.grids
        coarsest = max(g.spacing for g in grids)
        self.S = S = float(max(1, round(stride / coarsest)) * coarsest)
        self.x0 = min(g.x0 for g in grids)
        self.y0 = min(g.y0 for g in grids)
        x1 = max(g.bounds[2] for g in grids)
        y1 = max(g.bounds[3] for g in grids)
        self.W = int(math.floor((x1 - self.x0) / S + 1e-9)) + 1
        self.H = int(math.floor((y1 - self.y0) / S + 1e-9)) + 1
        shape = (self.H, self.W)
        self.grid_idx = np.full(shape, -1, dtype=np.int8)
        self.jj = np.zeros(shape, dtype=np.int32)
        self.ii = np.zeros(shape, dtype=np.int32)
        self.lat = np.full(shape, np.nan)
        self.lon = np.full(shape, np.nan)
        self.slope = np.full(shape, np.nan)
        for k, g in enumerate(grids):
            cx = (g.x0 + np.arange(g.nx) * g.spacing - self.x0) / S
            cy = (g.y0 + np.arange(g.ny) * g.spacing - self.y0) / S
            i_ok = np.flatnonzero(np.abs(cx - np.round(cx)) < 1e-6)
            j_ok = np.flatnonzero(np.abs(cy - np.round(cy)) < 1e-6)
            if not i_ok.size or not j_ok.size:
                continue
            rr, cc = np.meshgrid(np.round(cy[j_ok]).astype(int), np.round(cx[i_ok]).astype(int), indexing="ij")
            gj, gi = np.meshgrid(j_ok, i_ok, indexing="ij")
            free = self.grid_idx[rr, cc] < 0             # grids are listed finest first: the finest wins
            rr, cc, gj, gi = rr[free], cc[free], gj[free], gi[free]
            self.grid_idx[rr, cc] = k
            self.jj[rr, cc], self.ii[rr, cc] = gj, gi
            self.lat[rr, cc], self.lon[rr, cc] = g.lat[gj, gi], g.lon[gj, gi]
            self.slope[rr, cc] = g.slope_deg[gj, gi]
        self.has = self.grid_idx >= 0
        self.x = self.x0 + np.arange(self.W)[None, :] * S + np.zeros((self.H, 1))
        self.y = self.y0 + np.arange(self.H)[:, None] * S + np.zeros((1, self.W))
        self.fine = self.has & eng.fine_layer(self.x, self.y)
        # clockwise angle from the map's +y axis to local north (south polar stereographic: north
        # points away from the pole, so it turns with longitude across the region)
        lat = np.where(self.has, self.lat, eng.center[0])
        lon = np.where(self.has, self.lon, eng.center[1])
        north, _east, scale = geo.map_frame(lat, lon)
        self.north_deg = np.degrees(np.arctan2(north[..., 0], north[..., 1]))
        self.scale = float(np.mean(scale[self.has])) if self.has.any() else 1.0

    @property
    def bounds(self) -> list[float]:
        """Outer edges of the cells (each node is the center of its S x S cell)."""
        h = 0.5 * self.S
        return [self.x0 - h, self.y0 - h, self.x0 + (self.W - 1) * self.S + h, self.y0 + (self.H - 1) * self.S + h]


def _lattice(eng) -> _Lattice:
    lat = getattr(eng, "_best_sites_lattice", None)
    if lat is None:
        lat = _Lattice(eng, STRIDE_M)
        eng._best_sites_lattice = lat
    return lat


# =========================================================================== ellipse footprint
def _corr_same(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Correlation of a raster with a (2r+1, 2r+1) kernel, zero padded, same shape as the raster."""
    h, w = values.shape
    kh, kw = kernel.shape
    fh, fw = h + kh - 1, w + kw - 1
    spec = np.fft.rfft2(values, (fh, fw)) * np.fft.rfft2(kernel[::-1, ::-1], (fh, fw))
    out = np.fft.irfft2(spec, (fh, fw))
    return out[kh // 2: kh // 2 + h, kw // 2: kw // 2 + w]


def _kernel(lattice: _Lattice, a: float, b: float, azimuth_deg: float, north_deg: float) -> np.ndarray:
    """Lattice offsets inside an a x b ellipse whose major axis is azimuth_deg clockwise from north."""
    S = lattice.S
    reach = int(math.ceil(max(a, b) * lattice.scale / S)) + 1
    d = np.arange(-reach, reach + 1) * S
    dx, dy = np.meshgrid(d, d)                           # rows = +y, like the lattice rasters
    ang = math.radians(north_deg + azimuth_deg)          # major axis, clockwise from the map's +y
    u = (dx * math.sin(ang) + dy * math.cos(ang)) / lattice.scale
    v = (dx * math.cos(ang) - dy * math.sin(ang)) / lattice.scale
    return ((u / a) ** 2 + (v / b) ** 2 <= 1.0 + 1e-12).astype(np.float64)


def _scan_axes(lattice: _Lattice, a: float, b: float) -> tuple[float, float, bool]:
    """Ellipse semi-axes used by the scan: ellipses smaller than the lattice are widened to a disc."""
    if math.pi * a * b / lattice.S ** 2 >= MIN_KERNEL_NODES:
        return a, b, False
    r = lattice.S * math.sqrt(MIN_KERNEL_NODES / math.pi) * 1.05
    return max(a, r), max(b, r), True


def _footprint_counts(lattice: _Lattice, rasters: list[np.ndarray], a: float, b: float, azimuth_deg: float):
    """Sum of each raster over the ellipse centered on every cell. Returns (sums, kernel_size, kernel)."""
    circle = abs(a - b) < 1e-9
    ang = lattice.north_deg[lattice.has]
    lo, hi = (float(ang.min()), float(ang.max())) if ang.size else (0.0, 0.0)
    n_bins = 1 if circle else max(1, int(math.ceil((hi - lo) / ORIENT_BIN_DEG)))
    width = (hi - lo) / n_bins if n_bins > 1 else 1.0
    bin_idx = np.clip(((lattice.north_deg - lo) / width).astype(int), 0, n_bins - 1) if n_bins > 1 else None
    sums = [np.zeros(r.shape) for r in rasters]
    ksize = np.zeros(rasters[0].shape)
    union = None
    for k in range(n_bins):
        kern = _kernel(lattice, a, b, azimuth_deg, lo + (k + 0.5) * width if n_bins > 1 else 0.5 * (lo + hi))
        union = kern if union is None else np.maximum(union, kern)
        where = slice(None) if bin_idx is None else (bin_idx == k)
        for out, r in zip(sums, rasters):
            out[where] = np.rint(_corr_same(r, kern))[where]
        ksize[where] = kern.sum()
    return sums, ksize, union


# =========================================================================== node classification
def _classify_nodes(eng, lattice: _Lattice, need: np.ndarray, sun_vec, earth_vec, limits: dict,
                    risk_margin: float, mission_h: int):
    """viable / risky flags (H, W) of the lattice nodes in `need`, with the rules of CONTRACT 4.4.

    Exact shortcuts: a node over the slope limit, or dark at the touchdown hour, is not viable
    whatever else happens, so the hourly simulation runs only for the remaining nodes.
    Returns (viable, risky, stats).
    """
    viable = np.zeros(lattice.has.shape, dtype=bool)
    risky = np.zeros(lattice.has.shape, dtype=bool)
    flat = np.flatnonzero(need & lattice.has)
    slope = lattice.slope.ravel()[flat]
    flat = flat[slope <= float(limits["max_slope_deg"])]          # NaN slopes drop out here too
    stats = {"n_nodes": int(np.count_nonzero(need & lattice.has)), "n_slope_ok": int(flat.size), "n_simulated": 0}
    if not flat.size:
        return viable, risky, stats
    margin_req = float(limits.get("min_sun_margin_deg") or 0.0)
    grids = eng.grid.grids
    gk = lattice.grid_idx.ravel()
    gj, gi = lattice.jj.ravel(), lattice.ii.ravel()
    lat, lon, slp = lattice.lat.ravel(), lattice.lon.ravel(), lattice.slope.ravel()

    def horizons(idx):
        hor = np.empty((idx.size, grids[0].n_az), dtype=np.float32)
        for k, g in enumerate(grids):
            m = gk[idx] == k
            if m.any():
                hor[m] = g.horizons(gj[idx[m]], gi[idx[m]])
        return hor

    def lit_at_touchdown(idx):
        vis = az._visibility(eng, lat[idx], lon[idx], horizons(idx), sun_vec[:1], earth_vec[:1])
        return idx[vis["sun_lit"][:, 0]]

    def simulate(idx):
        vis = az._visibility(eng, lat[idx], lon[idx], horizons(idx), sun_vec, earth_vec)
        m = metrics.point_metrics(vis["sun_lit"], vis["earth_visible"], sun_margin=vis["sun_margin"])
        codes, _fail, _risk = metrics.classify(m, slp[idx], limits, risk_margin, mission_h, margin_req)
        return idx, codes

    def chunks(idx, size):
        return [idx[a:a + size] for a in range(0, idx.size, size)]

    workers = max(1, int(az.FLY_THREADS))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        lit = list(pool.map(lit_at_touchdown, chunks(flat, max(256, CHUNK_ELEMS // 8))))
        flat = np.concatenate(lit) if lit else flat[:0]
        stats["n_simulated"] = int(flat.size)
        size = max(32, CHUNK_ELEMS // max(1, mission_h))
        for idx, codes in pool.map(simulate, chunks(flat, size)):
            viable.ravel()[idx] = codes == VIABLE
            risky.ravel()[idx] = codes == RISKY
    return viable, risky, stats


# =========================================================================== candidates
def _pick_candidates(lattice: _Lattice, prob: np.ndarray, smooth: np.ndarray, valid: np.ndarray,
                     min_sep_m: float, n_max: int) -> list[tuple[int, int]]:
    """Greedy non-maximum suppression: best cell first, then the best one at least min_sep_m away.

    Cells are ordered by the heatmap probability, then by robustness (mean probability around the
    cell). The data resolution plays no part here: it only breaks ties between equal real
    probabilities, after the candidates are re-evaluated.
    """
    ok = valid & (prob > 0)
    rows, cols = np.nonzero(ok)
    if not rows.size:
        return []
    order = np.lexsort((-smooth[rows, cols], -prob[rows, cols]))
    rows, cols = rows[order], cols[order]
    alive = np.ones(rows.size, dtype=bool)
    sep2 = (min_sep_m / lattice.S) ** 2
    out = []
    for n in range(rows.size):
        if not alive[n]:
            continue
        out.append((int(rows[n]), int(cols[n])))
        if len(out) >= n_max:
            break
        alive &= (rows - rows[n]) ** 2 + (cols - cols[n]) ** 2 >= sep2
    return out


def _evaluate_site(eng, lat: float, lon: float, req: dict, sun_vec, earth_vec) -> dict | None:
    """Survival probability of one aim point with the sampling of analyze().

    Returns None when analyze() would reject the target (out of coverage). `matches_full_analysis`
    is False for ellipses with too few grid nodes, where analyze() computes horizons on the fly.
    """
    ell, limits = req["ellipse"], req["limits"]
    grid = eng.grid
    frame = az._Frame(lat, lon, ell["semi_major_m"], ell["semi_minor_m"], ell["azimuth_deg"])
    if not bool(eng.in_area(frame.x0, frame.y0)):
        return None
    ax, ay = frame.area_points(600)
    if float(np.mean(eng.in_area(ax, ay))) < az.MIN_ELLIPSE_INSIDE:
        return None
    sel = az._grid_select(grid, frame)
    exact = GridSet.count(sel) >= az.MIN_GRID_NODES
    if exact:
        sel, _spacing = grid.thin(sel, az.MAX_POINTS)
    else:
        a_eff, b_eff = max(frame.a, SMALL_ELLIPSE_M), max(frame.b, SMALL_ELLIPSE_M)
        sel = grid.thin(az._grid_select(grid, frame, a_eff, b_eff), az.MAX_POINTS)[0]
    pts = grid.gather(sel)
    n = int(pts["x"].size)
    if n == 0:
        return None
    mission_h = req["mission_days"] * 24
    vis = az._visibility(eng, pts["lat"], pts["lon"], pts["horizon"], sun_vec, earth_vec)
    m = metrics.point_metrics(vis["sun_lit"], vis["earth_visible"], sun_margin=vis["sun_margin"])
    codes, _fail, _risk = metrics.classify(m, pts["slope"], limits, req["options"]["risk_margin"], mission_h,
                                           float(limits.get("min_sun_margin_deg") or 0.0))
    n_viable, n_risky = int(np.sum(codes == VIABLE)), int(np.sum(codes == RISKY))
    fine = eng.fine_layer(pts["x"], pts["y"])
    fine_px = float(eng.terrain.pixel_m)
    coarse_px = float(eng.terrain.layers[1].pixel_m) if eng.layered else fine_px
    res = ([fine_px] if fine.any() else []) + ([coarse_px] if not fine.all() else [])
    # composition of the whole ellipse (600 points spread evenly over its area), not of its center
    fine_fraction = az._r(float(np.mean(eng.fine_layer(ax, ay))), 3)
    coarse_fraction = az._r(1.0 - fine_fraction, 3)
    return {
        "lat": az._r(lat, 5), "lon": az._r(lon, 5), "x_m": az._r(frame.x0, 1), "y_m": az._r(frame.y0, 1),
        "survival_probability": az._r(n_viable / n, 3),
        "survival_probability_incl_risky": az._r((n_viable + n_risky) / n, 3),
        "n_points": n,
        "data_resolution_m": res,
        "fine_fraction": fine_fraction,
        "coarse_fraction": coarse_fraction,
        "matches_full_analysis": bool(exact),
    }


# =========================================================================== public entry point
def best_sites(request: dict) -> dict:
    """Body of POST /api/best-sites (CONTRACT 4.7). Identical requests are served from a small cache."""
    eng = az._engine()
    req = normalize_request(request)
    key = "best-sites:" + json.dumps(req, sort_keys=True)
    hit = eng.result_cache.get(key)
    if hit is not None:
        return copy.deepcopy(hit)
    with _LOCK:
        hit = eng.result_cache.get(key)                  # another thread may have just computed it
        if hit is None:
            hit = _best_sites(eng, req)
            eng.result_cache.put(key, hit)
    return copy.deepcopy(hit)


def _best_sites(eng, req: dict) -> dict:
    t_start = time.perf_counter()
    if eng.grid is None:
        raise EngineError("best_sites_unavailable",
                          "Best sites needs the precomputed horizon grid, which is not available on this server.")
    warnings: list[str] = []
    ell, limits, opts = req["ellipse"], req["limits"], req["options"]
    mission_h = req["mission_days"] * 24
    landing = datetime.fromisoformat(req["landing_utc"].replace("Z", "+00:00"))

    t_unix = np.asarray(eng.eph.t_unix)
    t0 = int(landing.timestamp())
    if t0 < int(t_unix[0]) or t0 + (mission_h - 1) * 3600 > int(t_unix[-1]):
        lo = az._iso(datetime.fromtimestamp(int(t_unix[0]), timezone.utc))
        hi = az._iso(datetime.fromtimestamp(int(t_unix[-1]), timezone.utc))
        raise EngineError("out_of_ephemeris_range",
                          f"The landing date plus the mission ({req['mission_days']} d) must be inside the "
                          f"precomputed ephemeris ({lo} to {hi}).")
    _t, sun_vec, earth_vec = eng.eph.window(landing, mission_h)
    sun_vec, earth_vec = np.asarray(sun_vec, dtype=np.float64), np.asarray(earth_vec, dtype=np.float64)

    lattice = _lattice(eng)
    grid_h = float(eng.grid.observer_height_m)
    height_ok = abs(grid_h - opts["observer_height_m"]) < 1e-6
    if not height_ok:
        warnings.append(f"The regional scan uses the precomputed horizons for an observer {grid_h:g} m above the "
                        f"ground; your observer height ({opts['observer_height_m']:g} m) applies only in the full "
                        "analysis of a site.")

    # ---- cells the user may aim at, by the data under the whole ellipse (not under its center) ----
    region = req["region"]
    a, b, widened = _scan_axes(lattice, ell["semi_major_m"], ell["semi_minor_m"])
    if widened:
        warnings.append(f"The landing ellipse is smaller than the {lattice.S:g} m sampling of the regional scan, so "
                        f"the heatmap evaluates a {2 * a:.0f} m wide neighborhood of each cell.")
    (n_in, n_fine), ksize, union = _footprint_counts(
        lattice, [lattice.has.astype(np.float64), lattice.fine.astype(np.float64)], a, b, ell["azimuth_deg"])
    # same coverage rule as analyze(): at least 80% of the ellipse inside the analyzable area
    valid = lattice.has & (n_in >= az.MIN_ELLIPSE_INSIDE * ksize) & (n_in > 0)
    frac_fine = n_fine / np.maximum(n_in, 1.0)           # share of the ellipse on the 5 m tile
    if region == "5m":
        valid &= frac_fine >= REGION_MIN_SHARE - 1e-9
    elif region == "20m":
        valid &= (1.0 - frac_fine) >= REGION_MIN_SHARE - 1e-9
    need = np.rint(_corr_same(valid.astype(np.float64), union)) > 0

    # ---- classify the nodes, then the share of viable nodes inside each ellipse ---------------
    viable, risky, stats = _classify_nodes(eng, lattice, need, sun_vec, earth_vec, limits,
                                           opts["risk_margin"], mission_h)
    (n_viable,), _k, _u = _footprint_counts(lattice, [viable.astype(np.float64)], a, b, ell["azimuth_deg"])
    prob = np.where(valid, n_viable / np.maximum(n_in, 1.0), 0.0)
    # robustness tie-break: the mean probability over the ellipse around each cell
    k0 = _kernel(lattice, a, b, ell["azimuth_deg"], float(np.mean(lattice.north_deg[lattice.has])))
    smooth = _corr_same(prob, k0) / np.maximum(_corr_same(valid.astype(np.float64), k0), 1.0)

    # ---- candidates: separated maxima, re-evaluated with the sampling of the full analysis ----
    min_sep = max(MIN_SEPARATION_M, 2.0 * ell["semi_major_m"])
    sites = []
    for r, c in _pick_candidates(lattice, prob, smooth, valid, min_sep, max(N_CANDIDATES, req["max_sites"])):
        site = _evaluate_site(eng, float(lattice.lat[r, c]), float(lattice.lon[r, c]), req, sun_vec, earth_vec)
        if site is None or site["survival_probability"] <= 0:
            continue
        # the region rule again, on the exact ellipse (the heatmap cell used the 200 m lattice)
        if region == "5m" and site["fine_fraction"] < REGION_MIN_SHARE:
            continue
        if region == "20m" and site["coarse_fraction"] < REGION_MIN_SHARE:
            continue
        site["matches_full_analysis"] = bool(site["matches_full_analysis"] and height_ok)
        site["heatmap_probability"] = az._r(prob[r, c], 3)
        site["_smooth"] = float(smooth[r, c])
        sites.append(site)
    # the real survival probability decides; ties go to the site with more of its ellipse on 5 m
    # data, then to the more robust neighborhood
    sites.sort(key=lambda s: (-s["survival_probability"], -s["fine_fraction"], -s["_smooth"],
                              -s["survival_probability_incl_risky"]))
    sites = sites[:req["max_sites"]]
    for rank, s in enumerate(sites, start=1):
        del s["_smooth"]
        s["rank"] = rank
        s["name"] = f"Site {rank}"

    # ---- heatmap: uint8, row 0 = north edge (image order), 255 = invalid ----------------------
    heat = np.where(valid, np.rint(prob * HEAT_MAX), HEAT_INVALID).astype(np.uint8)[::-1]
    n_valid = int(np.count_nonzero(valid))
    warnings.append(f"Approximate heatmap: the precomputed horizon grid is sampled every {lattice.S:g} m; each cell "
                    "is the share of viable samples inside your landing ellipse if you aim at that cell.")
    warnings.append("Best sites depend on the landing date and the mission settings; they assume the landing point "
                    "is uniformly distributed inside the ellipse.")
    share = f"{100 * REGION_MIN_SHARE:.0f}%"
    if region == "5m":
        warnings.append(f"5 m only: an aim point counts only if at least {share} of its landing ellipse is on the "
                        "LOLA 5 m/px tile.")
    elif region == "20m":
        warnings.append(f"20 m only: an aim point counts only if at least {share} of its landing ellipse is on the "
                        "LOLA 20 m/px DEM, which can hide small craters and slopes.")
    else:
        warnings.append("All data includes 20 m terrain, which can hide small craters and slopes.")
    if eng.eph_is_stub:
        warnings.insert(0, "SYNTHETIC EPHEMERIS (development stub): Sun and Earth positions are NOT real. "
                           "Do not use these results.")

    return {
        "schema_version": az.SCHEMA_VERSION,
        "is_sample": bool(eng.eph_is_stub),
        "computed_utc": az._iso(datetime.now(timezone.utc)),
        "compute_ms": int(round((time.perf_counter() - t_start) * 1000.0)),
        "inputs": req,
        "heatmap": {
            "encoding": "uint8-base64",
            "width": int(lattice.W), "height": int(lattice.H),
            "cell_m": az._r(lattice.S, 1),
            "bounds_xy_m": [az._r(v, 1) for v in lattice.bounds],
            "value_max": HEAT_MAX, "invalid_value": HEAT_INVALID,
            "approximate": True,
            "data_b64": base64.b64encode(heat.tobytes()).decode("ascii"),
        },
        "summary": {
            "n_cells": n_valid,
            "n_cells_above_zero": int(np.count_nonzero(valid & (prob > 0))),
            "best_heatmap_probability": az._r(prob[valid].max(), 3) if n_valid else 0.0,
            "n_nodes": stats["n_nodes"], "n_nodes_simulated": stats["n_simulated"],
            "n_nodes_viable": int(np.count_nonzero(viable)),
        },
        "sites": sites,
        "map": {"hillshade_url": az.HILLSHADE_URL, "hillshade_bounds_xy_m": eng.hillshade_bounds,
                **az._resolution_block(eng)},
        "warnings": warnings,
        "sources": [az.SOURCES_HORIZONS,
                    f"LRO {getattr(eng.terrain, 'short_name', eng.terrain.name)} (Barker et al. 2021, NASA GSFC PGDA)"]
                   + ([az.SOURCES_REGIONAL] if eng.layered else []),
    }
