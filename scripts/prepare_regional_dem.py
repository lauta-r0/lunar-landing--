# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Crop the LOLA south polar gridded DEMs (20 m and 40 m/px) around Mons Mouton and the IM-2 sites.

    python scripts/prepare_regional_dem.py                # download crops (if missing) + offset check
    python scripts/prepare_regional_dem.py --skip-download

Why
    The 5 m/px Site20v2 tile (26 x 26 km) does not reach the IM-2 "Athena" sites (lat ~ -84.79,
    about 7 km north of the tile edge) and its horizon stops at the tile edge. The LOLA GDR polar
    products cover the whole south pole (80S to the pole) at 20 and 40 m/px, in the same south polar
    stereographic projection (1,737,400 m sphere, MEAN EARTH/POLAR AXIS of DE421) and with heights
    relative to the same 1,737,400 m reference sphere as the PGDA 5 m DEMs.

What it writes (all git-ignored, reproducible with this script)
    data/raw/ldem_80s_20m_crop.tif      near layer: analyzable area + 20 km, int16 DN (height = 0.5 * DN)
    data/raw/ldem_80s_20m_crop_slp.tif  slope of the near layer (degrees, 20 m baseline)
    data/raw/ldem_80s_40m_crop.tif      far layer: analyzable area + 100 km (far-field horizon), int16 DN
    data/derived/regional_meta.json     boxes, sources, and the vertical offset of each layer
                                        against the 5 m DEM measured on the overlap

The source files are 1.85 GB (20 m) and 0.46 GB (40 m) raw PDS IMG rasters. Only the rows of the
crop boxes are fetched with HTTP Range requests (about 250 MB and 180 MB), and only the needed
columns are kept.

Source: LRO LOLA Gridded Data Records, LRO-L-LOLA-4-GDR-V1.0, product version 2.0 (2017),
NASA PDS Geosciences Node. Smith, D. E., et al. (2017), Icarus 283, 70-91,
doi:10.1016/j.icarus.2016.06.006. NASA data, no use restrictions.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

PDS_DIR = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img"
PDS_PAGE = "https://pds-geosciences.wustl.edu/missions/lro/lola.htm"
CITATION = ("Smith, D. E., et al. (2017), Summary of the results from the Lunar Orbiter Laser Altimeter after "
            "seven years in lunar orbit, Icarus 283, 70-91, doi:10.1016/j.icarus.2016.06.006. "
            "Data: LRO-L-LOLA-4-GDR-V1.0 (product version 2.0), NASA PDS Geosciences Node.")
CRS_PROJ4 = "+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"

# Analyzable areas (map meters, x_min, y_min, x_max, y_max). Must match the horizon grids.
#   fine:     the Site20v2 5 m tile minus a 1 km margin (50 m horizon grid)
#   regional: north of the tile, around the IM-2 intended / actual sites (100 m horizon grid)
AREA_FINE = (61000.0, 106000.0, 85000.0, 130000.0)
AREA_REGIONAL = (61000.0, 130100.0, 85000.0, 148000.0)
NEAR_MARGIN_M = 20000.0      # 20 m layer: analyzable area + 20 km
FAR_MARGIN_M = 100000.0      # 40 m layer: analyzable area + 100 km (far-field horizon)

LAYERS = {
    "near": {"product": "ldem_80s_20m", "margin_m": NEAR_MARGIN_M, "file": "ldem_80s_20m_crop.tif"},
    "far": {"product": "ldem_80s_40m", "margin_m": FAR_MARGIN_M, "file": "ldem_80s_40m_crop.tif"},
}


def union_area():
    return (min(AREA_FINE[0], AREA_REGIONAL[0]), min(AREA_FINE[1], AREA_REGIONAL[1]),
            max(AREA_FINE[2], AREA_REGIONAL[2]), max(AREA_FINE[3], AREA_REGIONAL[3]))


def read_label(product: str) -> dict:
    """Parse the fields we need from the PDS3 label (and check the ones we assume)."""
    txt = urllib.request.urlopen(f"{PDS_DIR}/{product}.lbl", timeout=60).read().decode("ascii", "replace")

    def field(name):
        m = re.search(rf"^\s*{name}\s*=\s*\"?([^\"\r\n<]+)", txt, re.M)
        if not m:
            raise RuntimeError(f"{product}.lbl has no {name}")
        return m.group(1).strip()

    lab = {
        "lines": int(field("LINES")), "samples": int(field("LINE_SAMPLES")),
        "sample_type": field("SAMPLE_TYPE"), "sample_bits": int(field("SAMPLE_BITS")),
        "scale": float(field("SCALING_FACTOR")), "map_scale_m": float(field("MAP_SCALE")),
        "line_offset": float(field("LINE_PROJECTION_OFFSET")), "sample_offset": float(field("SAMPLE_PROJECTION_OFFSET")),
        "radius_km": float(field("A_AXIS_RADIUS")), "center_lat": float(field("CENTER_LATITUDE")),
        "center_lon": float(field("CENTER_LONGITUDE")), "frame": field("COORDINATE_SYSTEM_NAME"),
        "version": field("PRODUCT_VERSION_ID"), "dataset": field("DATA_SET_ID"),
    }
    assert lab["sample_type"] == "LSB_INTEGER" and lab["sample_bits"] == 16, lab
    assert abs(lab["radius_km"] - 1737.4) < 1e-6 and lab["center_lat"] == -90.0 and lab["center_lon"] == 0.0, lab
    assert "DE421" in lab["frame"], lab
    return lab


def crop_box(margin_m: float, pixel_m: float):
    """Crop box snapped to the product's pixel edges (edges at multiples of pixel_m from the pole)."""
    x0, y0, x1, y1 = union_area()
    snap = lambda v, f: f((v) / pixel_m) * pixel_m   # noqa: E731
    return (snap(x0 - margin_m, np.floor), snap(y0 - margin_m, np.floor),
            snap(x1 + margin_m, np.ceil), snap(y1 + margin_m, np.ceil))


def fetch_crop(product: str, lab: dict, box, block_rows: int = 256) -> np.ndarray:
    """Read the rows of box with HTTP Range requests and keep its columns. Returns int16 DN (rows, cols).

    Orientation (checked against the 5 m DEM, correlation 1.000): row 0 is the top (+y), column 0 is
    the left (-x); the pole is at (line_offset, sample_offset) in 0-based pixel-center indices.
    """
    px = lab["map_scale_m"]
    x0, y0, x1, y1 = box
    # pixel center of (row r, col c): x = (c - sample_offset) * px, y = (line_offset - r) * px
    c0 = int(round(x0 / px + lab["sample_offset"] + 0.5))
    c1 = int(round(x1 / px + lab["sample_offset"] + 0.5))
    r0 = int(round(lab["line_offset"] - y1 / px + 0.5))
    r1 = int(round(lab["line_offset"] - y0 / px + 0.5))
    assert 0 <= c0 < c1 <= lab["samples"] and 0 <= r0 < r1 <= lab["lines"], (c0, c1, r0, r1)
    row_bytes = lab["samples"] * 2
    url = f"{PDS_DIR}/{product}.img"
    out = np.empty((r1 - r0, c1 - c0), dtype=np.int16)
    t0 = time.perf_counter()
    for r in range(r0, r1, block_rows):
        n = min(block_rows, r1 - r)
        rng = f"bytes={r * row_bytes}-{(r + n) * row_bytes - 1}"
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"Range": rng})
                with urllib.request.urlopen(req, timeout=180) as resp:
                    if resp.status != 206:
                        raise RuntimeError(f"server ignored the Range header (HTTP {resp.status})")
                    buf = resp.read()
                if len(buf) != n * row_bytes:
                    raise RuntimeError(f"short read {len(buf)} of {n * row_bytes}")
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 4:
                    raise
                print(f"  retry {attempt + 1} ({exc})")
                time.sleep(3 * (attempt + 1))
        rows = np.frombuffer(buf, dtype="<i2").reshape(n, lab["samples"])
        out[r - r0:r - r0 + n] = rows[:, c0:c1]
        done = r + n - r0
        mb = done * row_bytes / 1e6
        print(f"\r  {product}: {done}/{r1 - r0} rows, {mb:.0f} MB, {time.perf_counter() - t0:.0f} s",
              end="", flush=True)
    print()
    return out


def write_geotiff(path: Path, arr: np.ndarray, x_min: float, y_max: float, pixel_m: float, *,
                  scale: float = 1.0, nodata=None, tags=None) -> None:
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part.tif")
    profile = {"driver": "GTiff", "width": arr.shape[1], "height": arr.shape[0], "count": 1,
               "dtype": arr.dtype.name, "crs": CRS_PROJ4, "transform": from_origin(x_min, y_max, pixel_m, pixel_m),
               "compress": "deflate", "predictor": 2, "tiled": True, "blockxsize": 512, "blockysize": 512}
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(tmp, "w", **profile) as ds:
        ds.write(arr, 1)
        ds.scales = (scale,)
        ds.offsets = (0.0,)
        if tags:
            ds.update_tags(**tags)
    tmp.replace(path)


def slope_deg(z: np.ndarray, pixel_m: float, x_min: float, y_max: float) -> np.ndarray:
    """Slope (degrees) by central differences. Map distances are converted to ground distances with
    the polar stereographic scale factor k = 1 + r^2 / (4 R^2) (0.2% here)."""
    R = 1737400.0
    zf = z.astype(np.float64)
    d_row, d_col = np.gradient(zf, pixel_m)
    ny, nx = z.shape
    xs = x_min + (np.arange(nx) + 0.5) * pixel_m
    ys = y_max - (np.arange(ny) + 0.5) * pixel_m
    k = 1.0 + (xs[None, :] ** 2 + ys[:, None] ** 2) / (4.0 * R * R)
    return np.degrees(np.arctan(np.hypot(d_row, d_col) * k)).astype(np.float32)


def offset_vs_fine(layer_path: Path, scale: float):
    """Height difference (layer - 5 m DEM) on the overlap, 5 m DEM block-averaged to the layer's pixels.

    Also searches a +-1 pixel horizontal shift (in 1/4-pixel steps) to report any misregistration.
    """
    import rasterio
    from scipy import ndimage

    from engine.terrain import find_dem_files

    _sid, _name, surf5, _slp = find_dem_files()
    with rasterio.open(surf5) as f5, rasterio.open(layer_path) as fr:
        z5 = f5.read(1).astype(np.float64)
        b5, px5 = f5.bounds, f5.transform.a
        pxr = fr.transform.a
        f = int(round(pxr / px5))
        # layer pixels fully inside the 5 m tile
        c0 = int(np.ceil((b5.left - fr.bounds.left) / pxr))
        c1 = int(np.floor((b5.right - fr.bounds.left) / pxr))
        r0 = int(np.ceil((fr.bounds.top - b5.top) / pxr))
        r1 = int(np.floor((fr.bounds.top - b5.bottom) / pxr))
        zr = fr.read(1, window=((r0, r1), (c0, c1))).astype(np.float64) * scale
        # matching 5 m block means
        x_left = fr.bounds.left + c0 * pxr
        y_top = fr.bounds.top - r0 * pxr
        i0 = int(round((x_left - b5.left) / px5))
        j0 = int(round((b5.top - y_top) / px5))
        blk = z5[j0:j0 + (r1 - r0) * f, i0:i0 + (c1 - c0) * f]
        zb = blk.reshape(r1 - r0, f, c1 - c0, f).mean(axis=(1, 3))
    d = zr - zb
    inner = d[2:-2, 2:-2]
    best = (np.inf, 0.0, 0.0)
    for dy in np.arange(-1.0, 1.01, 0.25):
        for dx in np.arange(-1.0, 1.01, 0.25):
            sh = ndimage.shift(zr, (dy, dx), order=1, mode="nearest")[2:-2, 2:-2] - zb[2:-2, 2:-2]
            rms = float(np.sqrt(np.mean((sh - np.median(sh)) ** 2)))
            if rms < best[0]:
                best = (rms, dx * pxr, -dy * pxr)
    return {
        "n_pixels": int(inner.size),
        "median_m": round(float(np.median(inner)), 3),
        "mean_m": round(float(np.mean(inner)), 3),
        "std_m": round(float(np.std(inner)), 3),
        "p05_p95_m": [round(float(np.percentile(inner, 5)), 2), round(float(np.percentile(inner, 95)), 2)],
        "best_shift_xy_m": [round(best[1], 1), round(best[2], 1)],
        "rms_at_best_shift_m": round(best[0], 3),
        "rms_at_zero_shift_m": round(float(np.sqrt(np.mean((inner - np.median(inner)) ** 2))), 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dem-dir", default=str(REPO_ROOT / "data" / "raw"))
    ap.add_argument("--derived-dir", default=str(REPO_ROOT / "data" / "derived"))
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    dem_dir, derived = Path(args.dem_dir), Path(args.derived_dir)

    meta = {"crs_proj4": CRS_PROJ4, "area_fine_xy_m": list(AREA_FINE), "area_regional_xy_m": list(AREA_REGIONAL),
            "source_dir": PDS_DIR, "product_page": PDS_PAGE, "citation": CITATION, "layers": {}}
    for key, spec in LAYERS.items():
        lab = read_label(spec["product"])
        px = lab["map_scale_m"]
        box = crop_box(spec["margin_m"], px)
        path = dem_dir / spec["file"]
        if not path.exists():
            if args.skip_download:
                print(f"missing {path}")
                return 1
            print(f"{spec['product']}: crop x [{box[0]:.0f}, {box[2]:.0f}] y [{box[1]:.0f}, {box[3]:.0f}] m "
                  f"({(box[2] - box[0]) / px:.0f} x {(box[3] - box[1]) / px:.0f} px)")
            dn = fetch_crop(spec["product"], lab, box)
            write_geotiff(path, dn, box[0], box[3], px, scale=lab["scale"],
                          tags={"SOURCE": f"{PDS_DIR}/{spec['product']}.img", "HEIGHT": "0.5 * DN, m above 1737400 m"})
        if key == "near":
            slp_path = dem_dir / spec["file"].replace(".tif", "_slp.tif")
            if not slp_path.exists():
                import rasterio
                with rasterio.open(path) as ds:
                    z = ds.read(1).astype(np.float32) * lab["scale"]
                write_geotiff(slp_path, slope_deg(z, px, box[0], box[3]), box[0], box[3], px,
                              tags={"SOURCE": f"slope of {spec['file']} (central differences, 20 m)"})
        import rasterio
        with rasterio.open(path) as ds:          # record what is on disk (may be a superset of box)
            box = tuple(float(v) for v in ds.bounds)
        off = offset_vs_fine(path, lab["scale"])
        print(f"{spec['product']} - 5 m DEM on the overlap: median {off['median_m']} m, std {off['std_m']} m, "
              f"best shift {off['best_shift_xy_m']} m (rms {off['rms_at_zero_shift_m']} -> {off['rms_at_best_shift_m']})")
        meta["layers"][key] = {
            "file": spec["file"], "product": spec["product"], "url": f"{PDS_DIR}/{spec['product']}.img",
            "label_url": f"{PDS_DIR}/{spec['product']}.lbl", "dataset": lab["dataset"], "version": lab["version"],
            "pixel_m": px, "dn_scale": lab["scale"], "bounds_xy_m": list(box), "margin_m": spec["margin_m"],
            "vs_fine_dem": off,
            # added to the layer's heights so that it matches the 5 m DEM on average
            "vertical_correction_m": -off["median_m"],
        }
    meta["created_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    derived.mkdir(parents=True, exist_ok=True)
    (derived / "regional_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {derived / 'regional_meta.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
