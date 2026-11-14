# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""DEM access: a stack of LOLA height rasters, finest first.

Levels (all south polar stereographic on the 1,737,400 m sphere, MOON_ME / DE421, heights in meters
relative to the 1,737,400 m reference sphere, values at pixel centers):

    1. fine      LOLA 5 m/px Site20v2 (PGDA, Barker et al. 2021): height + slope
    2. near      LOLA 20 m/px polar DEM crop (PDS LOLA GDR v2.0, LDEM_80S_20M): height + slope,
                 used outside the 5 m tile (e.g. the IM-2 sites) and for the horizon out to ~20 km
    3. far       LOLA 40 m/px polar DEM crop (LDEM_80S_40M): far-field horizon out to 100 km

Levels 2 and 3 are optional (``scripts/prepare_regional_dem.py``). Without them the engine works
on the 5 m tile alone, as before. The regional layers are shifted vertically so that they match
the 5 m DEM on the overlap (the offset is measured by the prep script, see regional_meta.json).

Queries take the finest level that covers the point. Bilinear heights and slopes are blended
linearly over BLEND_M inside the edge of a finer level, so there is no step at the seam.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from scipy import ndimage

from . import geo

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEM_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_REGIONAL_META = REPO_ROOT / "data" / "derived" / "regional_meta.json"

# Preferred first. Site20v2 = "Leibnitz beta plateau, extended boundaries" (26 x 26 km).
DEM_CANDIDATES = [
    ("Site20v2", "LOLA 5 m/px LDEM — Site20v2 (Mons Mouton / Leibnitz beta plateau)"),
    ("Site20", "LOLA 5 m/px LDEM — Site20 (Mons Mouton)"),
]
REGIONAL_NAMES = {
    "near": "LOLA 20 m/px polar LDEM (LDEM_80S_20M, PDS LOLA GDR v2.0)",
    "far": "LOLA 40 m/px polar LDEM (LDEM_80S_40M, PDS LOLA GDR v2.0)",
}
BLEND_M = 500.0
HILLSHADE_PIXEL_M = 20.0
HILLSHADE_MARGIN_M = 5000.0


class Terrain:
    """A height raster (and optional slope raster) on a regular north-up map grid.

    ``surf`` may be stored as int16 (LOLA DN); heights are ``surf * z_scale + z_offset``.
    """

    def __init__(self, surf, slp=None, *, x_min: float, y_max: float, pixel_m: float,
                 name: str = "synthetic", site_id: str = "synthetic", z_scale: float = 1.0,
                 z_offset: float = 0.0, role: str = "fine"):
        surf = np.asarray(surf)
        self.surf = surf if surf.dtype in (np.float32, np.int16) else surf.astype(np.float32)
        self.slp = None if slp is None else np.asarray(slp, dtype=np.float32)
        self.ny, self.nx = self.surf.shape
        self.pixel_m = float(pixel_m)
        self.x_min = float(x_min)
        self.y_max = float(y_max)
        self.x_max = self.x_min + self.nx * self.pixel_m
        self.y_min = self.y_max - self.ny * self.pixel_m
        self.name = name
        self.site_id = site_id
        self.z_scale = float(z_scale)
        self.z_offset = float(z_offset)
        self.role = role
        self.layers = [self]

    # ------------------------------------------------------------------ basic info
    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(x_min, y_min, x_max, y_max) of the raster outer edges, meters."""
        return (self.x_min, self.y_min, self.x_max, self.y_max)

    @property
    def center_xy(self) -> tuple[float, float]:
        return (0.5 * (self.x_min + self.x_max), 0.5 * (self.y_min + self.y_max))

    @property
    def primary(self) -> "Terrain":
        return self

    def _rowcol(self, x, y):
        col = (np.asarray(x, dtype=np.float64) - self.x_min) / self.pixel_m - 0.5
        row = (self.y_max - np.asarray(y, dtype=np.float64)) / self.pixel_m - 0.5
        return row, col

    def _sample(self, arr, x, y):
        row, col = self._rowcol(x, y)
        shape = np.broadcast(row, col).shape
        coords = np.stack([np.broadcast_to(row, shape).ravel(), np.broadcast_to(col, shape).ravel()])
        out = ndimage.map_coordinates(arr, coords, order=1, mode="constant", cval=np.nan,
                                      output=np.float64, prefilter=False)
        return out.reshape(shape)

    def edge_distance(self, x, y):
        """Distance (map m) from the point to the nearest raster edge; negative outside."""
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        return np.minimum(np.minimum(x - self.x_min, self.x_max - x), np.minimum(y - self.y_min, self.y_max - y))

    # ------------------------------------------------------------------ queries
    def height_at(self, x, y):
        """Bilinear terrain height (m) at map coordinates; NaN outside the grid."""
        z = self._sample(self.surf, x, y)
        if self.z_scale != 1.0 or self.z_offset != 0.0:
            z = z * self.z_scale + self.z_offset
        return z

    def height_nearest(self, x, y, out=None, where=None):
        """Height of the pixel containing each point (m); NaN outside the grid. Fast path for far ray samples.

        With ``out`` (float64 array, same shape) the heights are written into it, only where the point
        is inside this raster (and ``where`` is True, if given); returns the mask of written points.
        """
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        ok = (x >= self.x_min) & (x < self.x_max) & (y > self.y_min) & (y <= self.y_max)
        if where is not None:
            ok &= where
        inv = 1.0 / self.pixel_m
        if out is None:
            col = ((x - self.x_min) * inv).astype(np.intp)       # truncation == floor where ok
            row = ((self.y_max - y) * inv).astype(np.intp)
            np.clip(col, 0, self.nx - 1, out=col)
            np.clip(row, 0, self.ny - 1, out=row)
            z = self.surf[row, col].astype(np.float64)
            if self.z_scale != 1.0 or self.z_offset != 0.0:
                z *= self.z_scale
                z += self.z_offset
            z[~ok] = np.nan
            return z
        xs, ys = x[ok], y[ok]
        col = ((xs - self.x_min) * inv).astype(np.intp)
        row = ((self.y_max - ys) * inv).astype(np.intp)
        np.clip(col, 0, self.nx - 1, out=col)
        np.clip(row, 0, self.ny - 1, out=row)
        z = self.surf[row, col].astype(np.float64)
        if self.z_scale != 1.0 or self.z_offset != 0.0:
            z *= self.z_scale
            z += self.z_offset
        out[ok] = z
        return ok

    def slope_at(self, x, y):
        """Bilinear slope (degrees) at map coordinates; NaN outside the grid."""
        if self.slp is None:
            raise RuntimeError("No slope raster loaded")
        return self._sample(self.slp, x, y)

    def layer_index_at(self, x, y):
        """Index (in self.layers) of the finest level covering each point; -1 outside."""
        return np.where(self.in_coverage(x, y), 0, -1)

    def in_coverage(self, x, y, margin_m: float = 0.0):
        """True where the point is inside the DEM and at least margin_m away from its edge."""
        return self.edge_distance(x, y) >= margin_m

    def max_distance_from(self, x: float, y: float) -> float:
        """Largest map distance from (x, y) to a DEM corner (upper bound for ray length)."""
        dx = max(abs(x - self.x_min), abs(x - self.x_max))
        dy = max(abs(y - self.y_min), abs(y - self.y_max))
        return float(np.hypot(dx, dy))

    # ------------------------------------------------------------------ hillshade
    def hillshade_bounds(self, max_px: int = 2048) -> list[float]:
        """[x_min, y_min, x_max, y_max] of the hillshade image written by make_hillshade()."""
        f = max(1, int(np.ceil(max(self.ny, self.nx) / float(max_px))))
        ny, nx = (self.ny // f) * f, (self.nx // f) * f
        return [self.x_min, self.y_max - ny * self.pixel_m, self.x_min + nx * self.pixel_m, self.y_max]

    def make_hillshade(self, out_png, max_px: int = 2048, azimuth_deg: float = 315.0,
                       altitude_deg: float = 45.0, z_factor: float = 1.0):
        """Write a grayscale hillshade PNG and return its bounds [x_min, y_min, x_max, y_max].

        The light comes from azimuth_deg measured clockwise from map-up (+y), i.e. 315 = upper left.
        This is a display product only (it is not the real Sun direction).
        """
        f = int(np.ceil(max(self.ny, self.nx) / float(max_px)))
        f = max(f, 1)
        ny, nx = (self.ny // f) * f, (self.nx // f) * f
        z = (self.surf[:ny, :nx].astype(np.float32) * self.z_scale + self.z_offset)
        if f > 1:
            z = z.reshape(ny // f, f, nx // f, f).mean(axis=(1, 3))
        _write_hillshade(z, self.pixel_m * f, out_png, azimuth_deg, altitude_deg, z_factor)
        return self.hillshade_bounds(max_px)


class LayeredTerrain:
    """Several Terrain levels, finest first. Same query interface as Terrain."""

    def __init__(self, layers: list[Terrain], blend_m: float = BLEND_M, hillshade_box=None):
        if not layers:
            raise ValueError("LayeredTerrain needs at least one layer")
        self.layers = list(layers)
        self.blend_m = float(blend_m)
        p = self.layers[0]
        # the finest level describes the dataset (name, center, pixel size, legacy attributes)
        self.name = p.name if len(self.layers) == 1 else (
            p.name + " + " + " + ".join(lay.name for lay in self.layers[1:]))
        self.short_name = p.name
        self.site_id = p.site_id
        self.pixel_m = p.pixel_m
        self.x_min, self.y_min, self.x_max, self.y_max = p.bounds
        self.nx, self.ny = p.nx, p.ny
        self.surf, self.slp = p.surf, p.slp
        self._hillshade_box = hillshade_box

    @property
    def primary(self) -> Terrain:
        return self.layers[0]

    @property
    def bounds(self):
        return self.layers[0].bounds

    @property
    def center_xy(self):
        return self.layers[0].center_xy

    @property
    def outer_bounds(self):
        b = np.array([lay.bounds for lay in self.layers])
        return (float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 2].max()), float(b[:, 3].max()))

    def _blend(self, fn, x, y):
        """Finest-first composite of a bilinear per-layer query, feathered over blend_m at inner edges.

        Each level gets weight w = clip(distance to its edge / blend_m, 0, 1) of what the finer levels
        left; the coarsest level takes the rest. Where no coarser level exists, the weights are
        renormalized (the finer level is used alone). Coarser levels are not read at all when the
        finer ones already cover every point with full weight.
        """
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        shape = np.broadcast(x, y).shape
        acc = np.zeros(shape, dtype=np.float64)
        used = np.zeros(shape, dtype=np.float64)          # total weight assigned so far
        rem = np.ones(shape, dtype=np.float64)            # weight still available for coarser levels
        last = len(self.layers) - 1
        for k, lay in enumerate(self.layers):
            v = fn(lay, x, y)
            ok = np.isfinite(v)
            if k < last and self.blend_m > 0:
                w = np.clip(lay.edge_distance(x, y) / self.blend_m, 0.0, 1.0)
            else:
                w = np.ones(shape, dtype=np.float64)
            w = np.where(ok, w, 0.0) * rem
            acc += w * np.where(ok, v, 0.0)
            used += w
            rem -= w
            if not np.any(rem > 1e-12):
                break
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(used > 1e-12, acc / used, np.nan)

    def height_at(self, x, y):
        return self._blend(lambda lay, a, b: lay.height_at(a, b), x, y)

    def slope_at(self, x, y):
        return self._blend(lambda lay, a, b: (lay.slope_at(a, b) if lay.slp is not None
                                              else np.full(np.broadcast(a, b).shape, np.nan)), x, y)

    def height_nearest(self, x, y):
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        z = np.full(np.broadcast(x, y).shape, np.nan)
        todo = None
        for lay in self.layers:
            done = lay.height_nearest(x, y, out=z, where=todo)
            todo = ~done if todo is None else (todo & ~done)
            if not todo.any():
                break
        return z

    def layer_index_at(self, x, y):
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        idx = np.full(np.broadcast(x, y).shape, -1, dtype=np.int64)
        for k in range(len(self.layers) - 1, -1, -1):
            idx = np.where(self.layers[k].in_coverage(x, y), k, idx)
        return idx

    def in_coverage(self, x, y, margin_m: float = 0.0):
        out = self.layers[0].in_coverage(x, y, margin_m)
        for lay in self.layers[1:]:
            out = out | lay.in_coverage(x, y, margin_m)
        return out

    def edge_distance(self, x, y):
        return np.max([lay.edge_distance(x, y) for lay in self.layers], axis=0)

    def max_distance_from(self, x: float, y: float) -> float:
        return max(lay.max_distance_from(x, y) for lay in self.layers)

    # ------------------------------------------------------------------ hillshade
    def hillshade_bounds(self, max_px: int = 2048) -> list[float]:
        if self._hillshade_box is None or len(self.layers) == 1:
            return self.layers[0].hillshade_bounds(max_px)
        return [float(v) for v in self._hillshade_box]

    def make_hillshade(self, out_png, max_px: int = 2048, azimuth_deg: float = 315.0,
                       altitude_deg: float = 45.0, z_factor: float = 1.0):
        """Hillshade over the display box (all levels composited, HILLSHADE_PIXEL_M per pixel)."""
        if self._hillshade_box is None or len(self.layers) == 1:
            return self.layers[0].make_hillshade(out_png, max_px, azimuth_deg, altitude_deg, z_factor)
        x0, y0, x1, y1 = self._hillshade_box
        px = HILLSHADE_PIXEL_M
        nx, ny = int(round((x1 - x0) / px)), int(round((y1 - y0) / px))
        xs = x0 + (np.arange(nx) + 0.5) * px
        z = np.empty((ny, nx), dtype=np.float32)
        for r in range(0, ny, 256):                      # in strips to bound memory
            ys = y1 - (np.arange(r, min(ny, r + 256)) + 0.5) * px
            xx, yy = np.meshgrid(xs, ys)
            z[r:r + ys.size] = self._area_mean_height(xx, yy, px)
        _write_hillshade(z, px, out_png, azimuth_deg, altitude_deg, z_factor)
        return self.hillshade_bounds()

    def _area_mean_height(self, xx, yy, px):
        """Mean of a 4 x 4 bilinear sub-sample inside each display pixel (anti-aliasing on the 5 m tile)."""
        acc = np.zeros(xx.shape, dtype=np.float64)
        offs = (np.arange(4) + 0.5) / 4.0 - 0.5
        for dy in offs:
            for dx in offs:
                acc += self.height_at(xx + dx * px, yy + dy * px)
        return (acc / 16.0).astype(np.float32)


def _write_hillshade(z, cell, out_png, azimuth_deg, altitude_deg, z_factor):
    from PIL import Image

    zf = np.where(np.isfinite(z), z, np.nanmean(z))
    d_row, d_col = np.gradient(zf * z_factor, cell)
    dzdx, dzdy = d_col, -d_row                      # rows grow toward -y
    az, alt = np.radians(azimuth_deg), np.radians(altitude_deg)
    lx, ly, lz = np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)
    norm = np.sqrt(dzdx ** 2 + dzdy ** 2 + 1.0)
    shade = (-dzdx * lx - dzdy * ly + lz) / norm
    lo, hi = np.percentile(shade, [1.0, 99.0])          # contrast stretch for display
    shade = np.clip((shade - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    img = (255.0 * shade + 0.5).astype(np.uint8)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img, mode="L").save(out_png, optimize=True)


# --------------------------------------------------------------------------- loading
def find_dem_files(dem_dir=None):
    """Return (site_id, name, surf_path, slp_path) for the best 5 m DEM present in dem_dir."""
    dem_dir = Path(dem_dir or os.environ.get("LUNASCOUT_DEM_DIR") or DEFAULT_DEM_DIR)
    for site_id, name in DEM_CANDIDATES:
        surf = dem_dir / f"{site_id}_final_adj_5mpp_surf.tif"
        slp = dem_dir / f"{site_id}_final_adj_5mpp_slp.tif"
        if surf.exists():
            return site_id, name, surf, (slp if slp.exists() else None)
    raise FileNotFoundError(
        f"No Site20 DEM found in {dem_dir}. Run: python scripts/prepare_dem.py"
    )


def _read_raster(path, keep_int16: bool = False):
    import rasterio

    with rasterio.open(path) as ds:
        arr = ds.read(1)
        if not (keep_int16 and arr.dtype == np.int16):
            arr = arr.astype(np.float32)
            if ds.nodata is not None and not np.isnan(ds.nodata):
                arr[arr == ds.nodata] = np.nan
        tr = ds.transform
        if abs(tr.b) > 1e-9 or abs(tr.d) > 1e-9 or abs(tr.a + tr.e) > 1e-6:
            raise ValueError(f"Unexpected DEM geotransform (rotated or non-square pixels) in {path}: {tuple(tr)}")
        return arr, tr, ds.crs, (ds.scales[0] if ds.scales else 1.0)


def _same_projection(crs_a, crs_b) -> float:
    """Max distance (m) between the two CRSs' projections of a few south-pole points."""
    from pyproj import CRS, Transformer

    a, b = CRS.from_user_input(crs_a.to_wkt()), CRS.from_user_input(crs_b.to_wkt())
    lat = np.array([-89.0, -86.0, -85.4, -84.5, -83.0])
    lon = np.array([-120.0, 10.0, 31.7, 29.2, 150.0])
    ta = Transformer.from_crs(a.geodetic_crs, a, always_xy=True).transform(lon, lat)
    tb = Transformer.from_crs(b.geodetic_crs, b, always_xy=True).transform(lon, lat)
    return float(np.max(np.hypot(np.asarray(ta[0]) - tb[0], np.asarray(ta[1]) - tb[1])))


def load_regional_layers(fine_crs, dem_dir=None, meta_path=None) -> tuple[list[Terrain], dict | None]:
    """The optional 20 m / 40 m levels (empty list if not prepared or disabled with LUNASCOUT_REGIONAL=0)."""
    if os.environ.get("LUNASCOUT_REGIONAL") == "0":
        return [], None
    dem_dir = Path(dem_dir or os.environ.get("LUNASCOUT_DEM_DIR") or DEFAULT_DEM_DIR)
    meta_path = Path(meta_path or DEFAULT_REGIONAL_META)
    if not meta_path.exists():
        return [], None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    layers = []
    for role in ("near", "far"):
        spec = meta.get("layers", {}).get(role)
        if not spec or not (dem_dir / spec["file"]).exists():
            continue
        surf, tr, crs, scale = _read_raster(dem_dir / spec["file"], keep_int16=True)
        if crs is not None and fine_crs is not None:
            err = _same_projection(fine_crs, crs)
            if err > 1e-3:
                raise ValueError(f"{spec['file']} projection differs from the 5 m DEM by {err:.3f} m")
        slp = None
        slp_file = dem_dir / spec["file"].replace(".tif", "_slp.tif")
        if role == "near" and slp_file.exists():
            slp, tr_s, _c, _s = _read_raster(slp_file)
            if tuple(tr_s) != tuple(tr) or slp.shape != surf.shape:
                raise ValueError(f"{slp_file.name} grid does not match {spec['file']}")
        layers.append(Terrain(surf, slp, x_min=tr.c, y_max=tr.f, pixel_m=tr.a, name=REGIONAL_NAMES[role],
                              site_id=spec["product"], z_scale=float(spec.get("dn_scale", scale)),
                              z_offset=float(spec.get("vertical_correction_m", 0.0)), role=role))
    return layers, meta


def _hillshade_box(meta: dict) -> list[float]:
    a = np.array([meta["area_fine_xy_m"], meta["area_regional_xy_m"]])
    m, px = HILLSHADE_MARGIN_M, HILLSHADE_PIXEL_M
    box = [a[:, 0].min() - m, a[:, 1].min() - m, a[:, 2].max() + m, a[:, 3].max() + m]
    return [float(np.floor(box[0] / px) * px), float(np.floor(box[1] / px) * px),
            float(np.ceil(box[2] / px) * px), float(np.ceil(box[3] / px) * px)]


def load_terrain(dem_dir=None, with_slope: bool = True, with_regional: bool = True):
    """Read the GeoTIFFs, set the map CRS in engine.geo, return a Terrain or LayeredTerrain."""
    site_id, name, surf_path, slp_path = find_dem_files(dem_dir)
    surf, tr, crs, _scale = _read_raster(surf_path)
    slp = None
    if with_slope and slp_path is not None:
        slp, tr_s, _c, _s = _read_raster(slp_path)
        if slp.shape != surf.shape or tuple(tr_s) != tuple(tr):
            raise ValueError("Slope raster grid does not match the surface raster")
    geo.configure(crs)
    fine = Terrain(surf, slp, x_min=tr.c, y_max=tr.f, pixel_m=tr.a, name=name, site_id=site_id, role="fine")
    if not with_regional:
        return fine
    regional, meta = load_regional_layers(crs, dem_dir)
    if not regional:
        return fine
    return LayeredTerrain([fine] + regional, hillshade_box=_hillshade_box(meta))


_TERRAIN = None


def get_terrain():
    """The process-wide DEM (loaded on first use)."""
    global _TERRAIN
    if _TERRAIN is None:
        _TERRAIN = load_terrain()
    return _TERRAIN


def set_terrain(terrain) -> None:
    """Replace the process-wide DEM (used by tests with synthetic terrain)."""
    global _TERRAIN
    _TERRAIN = terrain


def height_at(x, y):
    return get_terrain().height_at(x, y)


def slope_at(x, y):
    return get_terrain().slope_at(x, y)


def in_coverage(x, y, margin_m: float = 0.0):
    return get_terrain().in_coverage(x, y, margin_m)


def make_hillshade(out_png, max_px: int = 2048):
    return get_terrain().make_hillshade(out_png, max_px=max_px)
