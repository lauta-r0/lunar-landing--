# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Access to the precomputed horizon grids (written by scripts/precompute_horizons.py).

Two grids can be loaded:
    data/derived/horizon_grid/            50 m nodes over the 5 m tile (Mons Mouton), "fine"
    data/derived/horizon_grid_regional/   100 m nodes north of the tile (IM-2 sites), "regional"
Their node areas do not overlap. ``GridSet`` puts them behind one interface and samples both at
the same spacing, so a landing ellipse that straddles the seam keeps a uniform point density.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRID_DIR = REPO_ROOT / "data" / "derived" / "horizon_grid"
DEFAULT_REGIONAL_GRID_DIR = REPO_ROOT / "data" / "derived" / "horizon_grid_regional"


class HorizonGrid:
    """Regular grid of horizon masks. Node (j, i) is at x = x0 + i*spacing, y = y0 + j*spacing."""

    def __init__(self, meta: dict, horizon_deg, reach_10m, height_m, slope_deg, lat, lon):
        self.meta = meta
        self.nx, self.ny = int(meta["nx"]), int(meta["ny"])
        self.x0, self.y0 = float(meta["x0"]), float(meta["y0"])
        self.spacing = float(meta["spacing_m"])
        self.observer_height_m = float(meta["observer_height_m"])
        self.n_az = int(meta.get("n_az", 360))
        self.reach_unit_m = float(meta.get("reach_unit_m", 10.0))
        self.horizon_deg = horizon_deg       # (ny, nx, n_az) float16
        self.reach_10m = reach_10m           # (ny, nx, n_az) uint16 or None
        self.height_m = height_m             # (ny, nx)
        self.slope_deg = slope_deg
        self.lat = lat
        self.lon = lon

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(x_min, y_min, x_max, y_max) of the node area."""
        return (self.x0, self.y0, self.x0 + (self.nx - 1) * self.spacing, self.y0 + (self.ny - 1) * self.spacing)

    def contains(self, x, y):
        x0, y0, x1, y1 = self.bounds
        x, y = np.asarray(x), np.asarray(y)
        return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)

    def node_xy(self, jj, ii):
        return self.x0 + np.asarray(ii) * self.spacing, self.y0 + np.asarray(jj) * self.spacing

    def nodes_in_bbox(self, x_min, y_min, x_max, y_max):
        """Index arrays (jj, ii) of all nodes inside the box (flattened meshgrid)."""
        i0 = max(0, int(np.ceil((x_min - self.x0) / self.spacing - 1e-9)))
        i1 = min(self.nx - 1, int(np.floor((x_max - self.x0) / self.spacing + 1e-9)))
        j0 = max(0, int(np.ceil((y_min - self.y0) / self.spacing - 1e-9)))
        j1 = min(self.ny - 1, int(np.floor((y_max - self.y0) / self.spacing + 1e-9)))
        if i1 < i0 or j1 < j0:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        jj, ii = np.meshgrid(np.arange(j0, j1 + 1), np.arange(i0, i1 + 1), indexing="ij")
        return jj.ravel(), ii.ravel()

    def horizons(self, jj, ii) -> np.ndarray:
        """(P, n_az) float32 horizon elevations of the given nodes."""
        return np.asarray(self.horizon_deg[np.asarray(jj), np.asarray(ii)], dtype=np.float32)


def _lattice_mask(jj, ii, level: int):
    """Regular sub-lattices of a grid: level 0 = all nodes, each level halves the density."""
    stride = 2 ** (level // 2)
    m = (jj % stride == 0) & (ii % stride == 0)
    if level % 2 == 1:
        m &= ((jj // stride + ii // stride) % 2 == 0)
    return m


def lattice_spacing(spacing: float, level: int) -> float:
    return spacing * (2 ** (level // 2)) * (np.sqrt(2.0) if level % 2 else 1.0)


class GridSet:
    """One or more HorizonGrid with disjoint node areas, finest first.

    Selections are lists of (grid_index, jj, ii). Sampling uses one common spacing for all grids:
    grid spacings must differ by powers of 2 (50 m and 100 m), so every lattice level of the coarse
    grid has a matching level on the fine one.
    """

    def __init__(self, grids: list[HorizonGrid]):
        if not grids:
            raise ValueError("GridSet needs at least one grid")
        self.grids = list(grids)
        h = {round(g.observer_height_m, 6) for g in self.grids}
        if len(h) != 1:
            raise ValueError(f"grids were computed for different observer heights: {sorted(h)}")
        self.observer_height_m = self.grids[0].observer_height_m
        self.spacing = min(g.spacing for g in self.grids)
        for g in self.grids:
            ratio = g.spacing / self.spacing
            if abs(np.log2(ratio) - round(np.log2(ratio))) > 1e-9:
                raise ValueError("grid spacings must differ by powers of 2")
        self.meta = self.grids[0].meta

    @property
    def areas(self) -> list[tuple[float, float, float, float]]:
        return [g.bounds for g in self.grids]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        b = np.array(self.areas)
        return (float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 2].max()), float(b[:, 3].max()))

    def contains(self, x, y):
        out = self.grids[0].contains(x, y)
        for g in self.grids[1:]:
            out = out | g.contains(x, y)
        return out

    def select(self, inside_fn, x_min, y_min, x_max, y_max) -> list[tuple[int, np.ndarray, np.ndarray]]:
        """Nodes in the bbox for which inside_fn(x, y) is True, per grid."""
        sel = []
        for k, g in enumerate(self.grids):
            jj, ii = g.nodes_in_bbox(x_min, y_min, x_max, y_max)
            if jj.size:
                x, y = g.node_xy(jj, ii)
                keep = inside_fn(x, y)
                jj, ii = jj[keep], ii[keep]
            if jj.size:
                sel.append((k, jj, ii))
        return sel

    @staticmethod
    def count(sel) -> int:
        return int(sum(jj.size for _k, jj, _ii in sel))

    def _level_for(self, k: int, spacing: float) -> int:
        return int(round(2.0 * np.log2(spacing / self.grids[k].spacing)))

    def thin(self, sel, max_points: int, min_spacing: float | None = None):
        """Sub-sample every grid at one common spacing so the total is <= max_points.

        The spacing starts at the coarsest grid touched (or min_spacing) and grows by sqrt(2).
        Returns (selection, spacing_m).
        """
        if not sel:
            return sel, self.spacing
        spacing = max([self.grids[k].spacing for k, _j, _i in sel] + [min_spacing or 0.0])
        for _ in range(40):
            out = []
            for k, jj, ii in sel:
                m = _lattice_mask(jj, ii, self._level_for(k, spacing))
                if m.any():
                    out.append((k, jj[m], ii[m]))
            if self.count(out) <= max_points:
                return out, spacing
            spacing *= np.sqrt(2.0)
        return out, spacing

    def gather(self, sel) -> dict:
        """x, y, lat, lon, slope (float64) and horizon (P, n_az float32) of the selected nodes."""
        parts = {"x": [], "y": [], "lat": [], "lon": [], "slope": [], "horizon": [], "grid": []}
        for k, jj, ii in sel:
            g = self.grids[k]
            x, y = g.node_xy(jj, ii)
            parts["x"].append(np.asarray(x, dtype=np.float64))
            parts["y"].append(np.asarray(y, dtype=np.float64))
            parts["lat"].append(g.lat[jj, ii])
            parts["lon"].append(g.lon[jj, ii])
            parts["slope"].append(g.slope_deg[jj, ii].astype(np.float64))
            parts["horizon"].append(g.horizons(jj, ii))
            parts["grid"].append(np.full(jj.size, k, dtype=np.int64))
        if not sel:
            n_az = self.grids[0].n_az
            return {"x": np.zeros(0), "y": np.zeros(0), "lat": np.zeros(0), "lon": np.zeros(0),
                    "slope": np.zeros(0), "horizon": np.zeros((0, n_az), np.float32), "grid": np.zeros(0, np.int64)}
        return {key: np.concatenate(v) for key, v in parts.items()}


def load_grids(grid_dir=None, regional_dir=None) -> GridSet | None:
    """The fine grid plus, if present, the regional one. None if no grid has been computed."""
    grids = []
    fine = load_grid(grid_dir)
    if fine is not None:
        grids.append(fine)
    if os.environ.get("LUNASCOUT_REGIONAL") != "0":
        reg = load_grid(regional_dir or os.environ.get("LUNASCOUT_REGIONAL_GRID_DIR") or DEFAULT_REGIONAL_GRID_DIR)
        if reg is not None:
            grids.append(reg)
    return GridSet(grids) if grids else None


def load_grid(grid_dir=None) -> HorizonGrid | None:
    """Load the grid, or return None if it has not been computed yet."""
    grid_dir = Path(grid_dir or os.environ.get("LUNASCOUT_GRID_DIR") or DEFAULT_GRID_DIR)
    meta_file = grid_dir / "meta.json"
    if not meta_file.exists() or not (grid_dir / "horizon_deg.npy").exists():
        return None
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    mmap = "r" if os.environ.get("LUNASCOUT_GRID_MMAP") == "1" else None
    horizon_deg = np.load(grid_dir / "horizon_deg.npy", mmap_mode=mmap)     # ~166 MB in RAM by default
    reach_file = grid_dir / "reach_10m.npy"
    reach = np.load(reach_file, mmap_mode="r") if reach_file.exists() else None   # rarely read: keep on disk
    return HorizonGrid(
        meta, horizon_deg, reach,
        np.load(grid_dir / "height_m.npy"), np.load(grid_dir / "slope_deg.npy"),
        np.load(grid_dir / "lat.npy"), np.load(grid_dir / "lon.npy"),
    )
