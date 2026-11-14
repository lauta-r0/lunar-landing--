# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Download the LOLA 5 m/px Site20v2 DEM from NASA GSFC PGDA and prepare the derived files.

    python scripts/prepare_dem.py                 # download (if missing) + report + hillshade
    python scripts/prepare_dem.py --skip-download # only report + derived files

Outputs
    data/raw/<site>_final_adj_5mpp_surf.tif, _slp.tif   (git-ignored, ~108 MB each)
    data/derived/dem_meta.json                           coverage, CRS, center, sources
    data/derived/hillshade.png                           grayscale shaded relief for the map

Source: Barker, M. K., et al. (2021), Planetary and Space Science 203, 105119,
doi:10.1016/j.pss.2020.105119. https://pgda.gsfc.nasa.gov/products/78
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

BASE_URL = "https://pgda.gsfc.nasa.gov/data/LOLA_5mpp"
PRODUCT_URL = "https://pgda.gsfc.nasa.gov/products/78"
CITATION = ("Barker, M. K., et al. (2021), Improved LOLA elevation maps for south pole landing sites: "
            "Error estimates and their impact on illumination conditions, Planetary and Space Science "
            "203, 105119, doi:10.1016/j.pss.2020.105119")


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        ctype = resp.headers.get("Content-Type", "")
        total = int(resp.headers.get("Content-Length", 0))
        if "tiff" not in ctype.lower():
            raise RuntimeError(f"{url} did not return a TIFF (Content-Type: {ctype}); check the file name")
        done = 0
        with open(part, "wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:7.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        print()
    if total and done != total:
        raise RuntimeError(f"incomplete download of {url}: {done} of {total} bytes")
    part.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="Site20v2", help="PGDA site id (default Site20v2; fallback Site20)")
    ap.add_argument("--dem-dir", default=str(REPO_ROOT / "data" / "raw"))
    ap.add_argument("--derived-dir", default=str(REPO_ROOT / "data" / "derived"))
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--with-toterr", action="store_true", help="also download the height RMS error map")
    ap.add_argument("--hillshade-px", type=int, default=2048)
    args = ap.parse_args()

    dem_dir, derived = Path(args.dem_dir), Path(args.derived_dir)
    kinds = ["surf", "slp"] + (["toterr"] if args.with_toterr else [])
    urls = {}
    for kind in kinds:
        name = f"{args.site}_final_adj_5mpp_{kind}.tif"
        urls[kind] = f"{BASE_URL}/{args.site}/{name}"
        if not (dem_dir / name).exists():
            if args.skip_download:
                print(f"missing {dem_dir / name}")
                return 1
            download(urls[kind], dem_dir / name)

    import rasterio
    from engine import geo
    from engine.terrain import load_terrain

    surf_path = dem_dir / f"{args.site}_final_adj_5mpp_surf.tif"
    with rasterio.open(surf_path) as ds:
        crs_wkt = ds.crs.to_wkt() if ds.crs else None
        tags = ds.tags()
    terrain = load_terrain(dem_dir)
    if crs_wkt is None:
        print("WARNING: the GeoTIFF has no CRS; using the contract fallback projection")
    x0, y0, x1, y1 = terrain.bounds
    cx, cy = terrain.center_xy
    clat, clon = (float(v) for v in geo.xy_to_latlon(cx, cy))
    corners = [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]
    edge_x = np.concatenate([np.linspace(x0, x1, 201), np.linspace(x0, x1, 201), np.full(201, x0), np.full(201, x1)])
    edge_y = np.concatenate([np.full(201, y0), np.full(201, y1), np.linspace(y0, y1, 201), np.linspace(y0, y1, 201)])
    elat, elon = geo.xy_to_latlon(edge_x, edge_y)

    hillshade_png = derived / "hillshade.png"
    hs_bounds = terrain.make_hillshade(hillshade_png, max_px=args.hillshade_px)

    meta = {
        "site_id": terrain.site_id,
        "dem_name": terrain.name,
        "pixel_m": terrain.pixel_m,
        "shape_rows_cols": [terrain.ny, terrain.nx],
        "bounds_xy_m": [x0, y0, x1, y1],
        "crs_proj4": geo.crs_proj4(),
        "crs_wkt": crs_wkt,
        "closed_form_projection": geo.uses_closed_form(),
        "center": {"x_m": cx, "y_m": cy, "lat": round(clat, 5), "lon": round(clon, 5),
                   "height_m": round(float(terrain.height_at(cx, cy)), 1)},
        "corners_latlon": [{"x_m": x, "y_m": y,
                            "lat": round(float(geo.xy_to_latlon(x, y)[0]), 5),
                            "lon": round(float(geo.xy_to_latlon(x, y)[1]), 5)} for x, y in corners],
        "approx_bounds_latlon": {"lat_min": round(float(elat.min()), 5), "lat_max": round(float(elat.max()), 5),
                                 "lon_min": round(float(elon.min()), 5), "lon_max": round(float(elon.max()), 5)},
        "height_range_m": [round(float(np.nanmin(terrain.surf)), 1), round(float(np.nanmax(terrain.surf)), 1)],
        "slope_range_deg": [round(float(np.nanmin(terrain.slp)), 2), round(float(np.nanmax(terrain.slp)), 2)],
        "nodata_fraction": float(np.mean(~np.isfinite(terrain.surf))),
        "hillshade": {"file": "hillshade.png", "bounds_xy_m": hs_bounds,
                      "note": "display only; light from the upper left, not the real Sun"},
        "gmt_history": tags.get("NC_GLOBAL#history"),
        "source_urls": urls,
        "product_page": PRODUCT_URL,
        "citation": CITATION,
    }
    derived.mkdir(parents=True, exist_ok=True)
    (derived / "dem_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"DEM            : {terrain.name}")
    print(f"size           : {terrain.nx} x {terrain.ny} px at {terrain.pixel_m} m "
          f"= {(x1 - x0) / 1000:.1f} x {(y1 - y0) / 1000:.1f} km")
    print(f"bounds xy (m)  : x [{x0:.0f}, {x1:.0f}]  y [{y0:.0f}, {y1:.0f}]")
    print(f"CRS            : {geo.crs_proj4()}  (closed form ok: {geo.uses_closed_form()})")
    print(f"center         : lat {clat:.5f}, lon {clon:.5f} E, height {meta['center']['height_m']} m")
    print(f"lat/lon extent : {meta['approx_bounds_latlon']}")
    print(f"heights (m)    : {meta['height_range_m']}   nodata fraction: {meta['nodata_fraction']:.4f}")
    print(f"wrote {derived / 'dem_meta.json'} and {hillshade_png} (bounds {hs_bounds})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
