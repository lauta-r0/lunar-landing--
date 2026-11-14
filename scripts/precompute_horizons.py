# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Precompute the horizon mask on a regular grid over the DEM (resumable, multi-process).

    python scripts/precompute_horizons.py                     # 50 m grid over the 5 m tile, 1 km margin
    python scripts/precompute_horizons.py --area regional     # 100 m grid north of the tile (IM-2 sites)
    python scripts/precompute_horizons.py --spacing 100       # coarser fallback
    python scripts/precompute_horizons.py --workers 8
    python scripts/precompute_horizons.py --merge-only        # only build the final files

How it works
    The horizons use every terrain level that is present (5 m tile, then the 20 m / 40 m LOLA
    polar DEM crops from scripts/prepare_regional_dem.py, rays out to 100 km).

    The grid is processed one row (constant y) at a time. Each finished row is written to
    data/derived/horizon_tiles[_regional]/row_XXXX.npz. Re-running the script skips the rows that are
    already there, so it can be stopped (Ctrl+C) and restarted at any time. When every row
    exists, they are merged into data/derived/horizon_grid[_regional]/:

        horizon_deg.npy   (ny, nx, 360) float16   horizon elevation per 1-degree azimuth bin
        reach_10m.npy     (ny, nx, 360) uint16    distance to the last DEM sample, units of 10 m
        height_m.npy      (ny, nx)      float32   terrain height at the node
        slope_deg.npy     (ny, nx)      float32   slope at the node (5 m tile, else 20 m DEM)
        lat.npy, lon.npy  (ny, nx)      float64
        meta.json         grid geometry and the parameters used

    Node (j, i) is at x = x0 + i * spacing, y = y0 + j * spacing.
"""
from __future__ import annotations

import os

# one math thread per worker process; set before numpy is imported anywhere
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

N_AZ = 360
REACH_UNIT_M = 10.0

_W = {}   # per-worker state


def grid_axes(bounds, spacing: float, margin: float):
    x_min, y_min, x_max, y_max = bounds
    xs = np.arange(x_min + margin, x_max - margin + 1e-6, spacing)
    ys = np.arange(y_min + margin, y_max - margin + 1e-6, spacing)
    return xs, ys


def _init_worker(layer_specs: list, crs_wkt, xs, ys, observer_height_m: float, tiles_dir: str) -> None:
    from engine import geo
    from engine.terrain import LayeredTerrain, Terrain

    geo.configure(crs_wkt)
    layers = []
    for sp in layer_specs:
        surf = np.load(sp["npy"], mmap_mode="r")      # shared between workers through the OS page cache
        layers.append(Terrain(surf, None, x_min=sp["x_min"], y_max=sp["y_max"], pixel_m=sp["pixel_m"],
                              z_scale=sp["z_scale"], z_offset=sp["z_offset"], role=sp["role"]))
    _W["terrain"] = layers[0] if len(layers) == 1 else LayeredTerrain(layers)
    _W["xs"], _W["ys"] = xs, ys
    _W["h_obs"] = observer_height_m
    _W["tiles_dir"] = Path(tiles_dir)


def _row_path(tiles_dir: Path, j: int) -> Path:
    return tiles_dir / f"row_{j:04d}.npz"


def _do_row(j: int):
    from engine import horizon

    t0 = time.perf_counter()
    xs = _W["xs"]
    y = float(_W["ys"][j])
    elev, reach, z0 = horizon.compute_horizons_xy(xs, np.full(xs.size, y), _W["h_obs"], _W["terrain"])
    out = _row_path(_W["tiles_dir"], j)
    tmp = out.with_name(out.stem + f".tmp{os.getpid()}.npz")
    np.savez(tmp,
             horizon_deg=elev.astype(np.float16),
             reach_10m=np.clip(np.rint(reach / REACH_UNIT_M), 0, 65535).astype(np.uint16),
             height_m=z0.astype(np.float32))
    os.replace(tmp, out)
    return j, time.perf_counter() - t0


def merge(tiles_dir: Path, out_dir: Path, terrain, xs, ys, params: dict) -> None:
    from engine import geo

    ny, nx = ys.size, xs.size
    out_dir.mkdir(parents=True, exist_ok=True)
    hor = np.lib.format.open_memmap(out_dir / "horizon_deg.npy", mode="w+", dtype=np.float16, shape=(ny, nx, N_AZ))
    rch = np.lib.format.open_memmap(out_dir / "reach_10m.npy", mode="w+", dtype=np.uint16, shape=(ny, nx, N_AZ))
    hgt = np.empty((ny, nx), dtype=np.float32)
    for j in range(ny):
        with np.load(_row_path(tiles_dir, j)) as d:
            hor[j], rch[j], hgt[j] = d["horizon_deg"], d["reach_10m"], d["height_m"]
    hor.flush()
    rch.flush()
    xx, yy = np.meshgrid(xs, ys)
    lat, lon = geo.xy_to_latlon(xx, yy)
    np.save(out_dir / "height_m.npy", hgt)
    np.save(out_dir / "slope_deg.npy", terrain.slope_at(xx, yy).astype(np.float32))
    np.save(out_dir / "lat.npy", lat)
    np.save(out_dir / "lon.npy", lon)
    meta = dict(params)
    meta.update({
        "nx": int(nx), "ny": int(ny), "x0": float(xs[0]), "y0": float(ys[0]),
        "n_az": N_AZ, "az_step_deg": 360.0 / N_AZ, "reach_unit_m": REACH_UNIT_M,
        "dem_name": terrain.name, "site_id": terrain.site_id,
        "dem_bounds_xy_m": list(terrain.bounds), "crs_proj4": geo.crs_proj4(),
        "terrain_levels": [{"role": lay.role, "name": lay.name, "pixel_m": lay.pixel_m, "bounds_xy_m": list(lay.bounds),
                            "z_offset_m": lay.z_offset} for lay in getattr(terrain, "layers", [terrain])],
        "horizon_min_deg": float(np.min(hor)), "horizon_max_deg": float(np.max(hor)),
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "arrays": {"horizon_deg.npy": "float16 (ny, nx, 360) deg", "reach_10m.npy": "uint16 (ny, nx, 360) x10 m",
                   "height_m.npy": "float32 (ny, nx)", "slope_deg.npy": "float32 (ny, nx)",
                   "lat.npy": "float64 (ny, nx)", "lon.npy": "float64 (ny, nx)"},
    })
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    size_mb = sum(f.stat().st_size for f in out_dir.iterdir()) / 1e6
    print(f"merged {ny} x {nx} = {ny * nx} nodes into {out_dir} ({size_mb:.0f} MB)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", choices=["fine", "regional"], default="fine",
                    help="fine: the 5 m tile minus --margin (default); regional: the IM-2 area of regional_meta.json")
    ap.add_argument("--spacing", type=float, default=None, help="grid spacing in meters (default 50 fine, 100 regional)")
    ap.add_argument("--margin", type=float, default=1000.0, help="margin excluded at the 5 m DEM edge (fine area), m")
    ap.add_argument("--observer-height", type=float, default=2.0)
    ap.add_argument("--workers", type=int, default=max(1, min((os.cpu_count() or 2) - 2, 12)))
    ap.add_argument("--derived-dir", default=str(REPO_ROOT / "data" / "derived"))
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--limit-rows", type=int, default=0, help="only process this many missing rows (benchmark)")
    ap.add_argument("--restart", action="store_true",
                    help="delete existing row tiles computed with different parameters and start over")
    args = ap.parse_args()

    from engine import horizon
    from engine.terrain import find_dem_files, load_terrain

    derived = Path(args.derived_dir)
    suffix = "" if args.area == "fine" else "_regional"
    spacing = args.spacing or (50.0 if args.area == "fine" else 100.0)
    tiles_dir = derived / f"horizon_tiles{suffix}"
    out_dir = derived / f"horizon_grid{suffix}"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    terrain = load_terrain()
    import rasterio
    with rasterio.open(find_dem_files()[2]) as ds:
        crs_wkt = ds.crs.to_wkt() if ds.crs else None
    levels = list(getattr(terrain, "layers", [terrain]))

    if args.area == "fine":
        xs, ys = grid_axes(levels[0].bounds, spacing, args.margin)
        margin = args.margin
    else:
        reg_meta = derived / "regional_meta.json"
        if len(levels) < 2 or not reg_meta.exists():
            print("The regional grid needs the regional DEM: run python scripts/prepare_regional_dem.py")
            return 1
        x0, y0, x1, y1 = json.loads(reg_meta.read_text(encoding="utf-8"))["area_regional_xy_m"]
        xs = np.arange(x0, x1 + 1e-6, spacing)
        ys = np.arange(y0, y1 + 1e-6, spacing)
        margin = None
    params = {
        "area": args.area, "spacing_m": spacing, "margin_m": margin, "observer_height_m": args.observer_height,
        "site_id": terrain.site_id, "nx": int(xs.size), "ny": int(ys.size),
        "x0": float(xs[0]), "y0": float(ys[0]),
        "ray_sampling": {"s0_m": horizon.S0_M, "ds_min_m": horizon.DS_MIN_M, "growth": horizon.GROWTH,
                         "near_bilinear_m": horizon.NEAR_BILINEAR_M, "max_ray_m": horizon.MAX_RAY_M},
        "levels": [{"role": lay.role, "pixel_m": lay.pixel_m, "bounds_xy_m": [float(v) for v in lay.bounds],
                    "z_offset_m": lay.z_offset} for lay in levels],
    }
    params_file = tiles_dir / "params.json"
    if params_file.exists():
        old = json.loads(params_file.read_text(encoding="utf-8"))
        if old != params:
            if not args.restart:
                print("Existing row tiles were computed with different parameters:\n"
                      f"  old: {old}\n  new: {params}\n"
                      "Re-run with --restart to delete them and start over.")
                return 2
            shutil.rmtree(tiles_dir)
            tiles_dir.mkdir(parents=True)
    params_file.write_text(json.dumps(params, indent=2) + "\n", encoding="utf-8")

    todo = [j for j in range(ys.size) if not _row_path(tiles_dir, j).exists()]
    n_nodes = xs.size * ys.size
    print(f"{args.area} grid {ys.size} x {xs.size} = {n_nodes} nodes, spacing {spacing:.0f} m, "
          f"x [{xs[0]:.0f}, {xs[-1]:.0f}] y [{ys[0]:.0f}, {ys[-1]:.0f}]; rows done {ys.size - len(todo)}/{ys.size}; "
          f"terrain levels: {', '.join(f'{lay.role} {lay.pixel_m:g} m' for lay in levels)}")

    if todo and not args.merge_only:
        if args.limit_rows:
            todo = todo[: args.limit_rows]
        layer_specs = []
        for lay in levels:
            npy = tiles_dir / f"_surf_{lay.role}.npy"
            if not npy.exists():
                np.save(npy, lay.surf)
            layer_specs.append({"npy": str(npy), "x_min": lay.x_min, "y_max": lay.y_max, "pixel_m": lay.pixel_m,
                                "z_scale": lay.z_scale, "z_offset": lay.z_offset, "role": lay.role})
        init_args = (layer_specs, crs_wkt, xs, ys, args.observer_height, str(tiles_dir))
        try:
            from tqdm import tqdm
        except ImportError:  # pragma: no cover
            tqdm = None
        t_start = time.perf_counter()
        print(f"computing {len(todo)} rows with {args.workers} workers "
              f"(started {datetime.now().strftime('%H:%M:%S')})", flush=True)
        with mp.Pool(args.workers, initializer=_init_worker, initargs=init_args) as pool:
            it = pool.imap_unordered(_do_row, todo)
            bar = tqdm(total=len(todo), unit="row", smoothing=0.05) if tqdm else None
            cpu_s = 0.0
            for k, (j, dt) in enumerate(it, 1):
                cpu_s += dt
                if bar:
                    bar.update(1)
                if k % 20 == 0 or k == len(todo):
                    el = time.perf_counter() - t_start
                    eta = el / k * (len(todo) - k)
                    print(f"[progress] {k}/{len(todo)} rows, elapsed {el / 60:.1f} min, ETA {eta / 60:.1f} min, "
                          f"{1000 * cpu_s / (k * xs.size):.1f} ms/node/core", flush=True)
            if bar:
                bar.close()

    missing = [j for j in range(ys.size) if not _row_path(tiles_dir, j).exists()]
    if missing:
        print(f"{len(missing)} rows still missing; run again to continue. Not merging yet.")
        return 0
    merge(tiles_dir, out_dir, terrain, xs, ys, params)
    print(f"done. The row tiles in {tiles_dir} can be deleted to save disk space.")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
