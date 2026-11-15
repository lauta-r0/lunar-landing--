# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Quantitative comparison of LunaScout sunlit/shadow points with LROC QuickMap terrain shadows.

Independent reference: the QuickMap layer "Terrain Shadows @UTC (80S,20mpp)" (ACT, layer id 4072,
source `pqmi_cloud`). QuickMap describes it as a binary 20 m/px shadow map (1 = sunlit, 0 = shadow)
computed with the center of the solar disc, accurate to 0.5 deg in subsolar longitude and 0.1 deg
in subsolar latitude, for 2025-2043. Its tiles are float32 rasters served per subsolar position:

    https://qts2d.actgate.com/tiles/pqmi_cloud/lunar-steresp/{z}/{col}/{row}.flt?d_pos=<lon>,<lat>&size=256

Tile grid (read from https://quickmap.lroc.im-ldi.com/maps/lroc, projection 27 "lunar-steresp"):
south polar stereographic on the 1,737,400 m sphere (same CRS as LunaScout), extent +-931,070 m,
quadtree with 2^z tiles per side, origin at the top-left corner, 256 x 256 px, 9-byte header, then
little-endian float32.

LunaScout side: the live API. For each date we run /api/analyze with landing_utc = that hour, a
5 x 5 km circle on a grid of targets covering the analyzable area, mission 1 day, no delays, no
recommendations, and read points[].sun_at_touchdown (Sun center above the terrain horizon at the
landing hour, observer 2 m above the ground).

The subsolar point passed to QuickMap is computed from LunaScout's own ephemeris table
(data/ephemeris/sun_earth_vectors.npz, JPL Horizons). That table is checked against Horizons
separately (test_ephemeris_live.py) and agrees with QuickMap's own subsolar value to ~0.001 deg,
so this comparison tests the terrain/horizon model, not the ephemeris.

Usage:  python tests/validation/quickmap_compare.py [--api URL] [--out docs/validation]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
import time
from pathlib import Path

import numpy as np
import requests

R_MOON = 1737400.0
QM_EXTENT = 931070.0
QM_URL = "https://qts2d.actgate.com/tiles/pqmi_cloud/lunar-steresp/{z}/{c}/{r}.flt?d_pos={lon},{lat}&size=256"
DEFAULT_API = "https://lunascout.web.app/api"
REPO = Path(__file__).resolve().parents[2]

DATES = [
    ("2025-03-06T17:00:00Z", "IM-2 Athena touchdown hour (Sun ~2.4 deg, az ~63 deg)"),
    ("2026-04-04T12:00:00Z", "Low Sun from the west-northwest (~1.5 deg, az ~303 deg)"),
    ("2027-10-12T14:00:00Z", "App default date (Sun ~6.1 deg, az ~0 deg, near maximum)"),
]
# Target grid (map metres) covering the analyzable area x 61-85 km, y 106-148 km with 5 km circles.
TARGETS_XY = [(x, y) for x in (66000.0, 73000.0, 80000.0)
              for y in (111000.0, 118000.0, 125000.0, 132000.0, 139000.0, 143000.0)]
ZOOM = 8   # 7274 m tiles, 28.4 m/px (QuickMap native product is 20 m/px)


def xy_to_latlon(x, y):
    rho = np.hypot(x, y)
    colat = 2.0 * np.degrees(np.arctan(rho / (2.0 * R_MOON)))
    return -(90.0 - colat), np.degrees(np.arctan2(x, y))


def latlon_to_xy(lat, lon):
    colat = np.radians(90.0 + np.asarray(lat, float))
    rho = 2.0 * R_MOON * np.tan(colat / 2.0)
    return rho * np.sin(np.radians(lon)), rho * np.cos(np.radians(lon))


def subsolar(t_iso: str) -> tuple[float, float]:
    z = np.load(REPO / "data/ephemeris/sun_earth_vectors.npz")
    t = int(dt.datetime.fromisoformat(t_iso.replace("Z", "+00:00")).timestamp())
    i = int(np.searchsorted(z["t_unix"], t))
    assert z["t_unix"][i] == t, "hour not in the ephemeris table"
    v = z["sun_vec"][i]
    return float(np.degrees(np.arctan2(v[1], v[0]))), float(np.degrees(np.arcsin(v[2])))


def fetch_qm_mosaic(lon: float, lat: float, x0, x1, y0, y1, cache: Path):
    size = 2 * QM_EXTENT / 2 ** ZOOM
    c0, c1 = int((x0 + QM_EXTENT) // size), int((x1 + QM_EXTENT) // size)
    r0, r1 = int((QM_EXTENT - y1) // size), int((QM_EXTENT - y0) // size)
    mos = np.zeros(((r1 - r0 + 1) * 256, (c1 - c0 + 1) * 256), dtype=np.float32)
    cache.mkdir(parents=True, exist_ok=True)
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            f = cache / f"{ZOOM}_{c}_{r}_{lon:.6f}_{lat:.6f}.flt"
            if not f.exists():
                url = QM_URL.format(z=ZOOM, c=c, r=r, lon=repr(lon), lat=repr(lat))
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                f.write_bytes(resp.content)
                time.sleep(0.2)   # be polite to the tile server
            b = f.read_bytes()
            a = np.frombuffer(b[9:9 + 256 * 256 * 4], dtype="<f4").reshape(256, 256)
            mos[(r - r0) * 256:(r - r0 + 1) * 256, (c - c0) * 256:(c - c0 + 1) * 256] = a
    # geotransform: pixel (i, j) centre
    gx0 = -QM_EXTENT + c0 * size
    gy0 = QM_EXTENT - r0 * size
    return mos, gx0, gy0, size / 256.0


def sample(mos, gx0, gy0, px, x, y, radius_px=0):
    j = np.floor((np.asarray(x) - gx0) / px).astype(int)
    i = np.floor((gy0 - np.asarray(y)) / px).astype(int)
    if radius_px == 0:
        return mos[i, j]
    lo = np.full(len(i), np.inf)
    hi = np.full(len(i), -np.inf)
    for di in range(-radius_px, radius_px + 1):
        for dj in range(-radius_px, radius_px + 1):
            v = mos[i + di, j + dj]
            lo, hi = np.minimum(lo, v), np.maximum(hi, v)
    return lo, hi


def lunascout_points(api: str, t_iso: str, cache: Path):
    f = cache / f"lunascout_{t_iso[:13]}.json"
    if f.exists():
        return json.loads(f.read_text())
    pts, warnings, timings = {}, set(), []
    for x, y in TARGETS_XY:
        lat, lon = xy_to_latlon(x, y)
        body = {"target": {"lat": round(float(lat), 5), "lon": round(float(lon), 5)},
                "landing_utc": t_iso, "mission_days": 1,
                "ellipse": {"semi_major_m": 5000, "semi_minor_m": 5000, "azimuth_deg": 0},
                "options": {"delay_days_max": 0, "include_recommendations": False}}
        t0 = time.perf_counter()
        r = requests.post(api + "/analyze", json=body, timeout=120)
        timings.append(time.perf_counter() - t0)
        if r.status_code != 200:
            print("  target", body["target"], "->", r.status_code, r.text[:200])
            continue
        d = r.json()
        warnings.update(d.get("warnings", []))
        for p in d["points"]:
            key = (round(p["x_m"]), round(p["y_m"]))
            pts[key] = {"x": p["x_m"], "y": p["y_m"], "lat": p["lat"], "lon": p["lon"],
                        "lit": bool(p["sun_at_touchdown"]), "coarse": bool(p.get("slope_coarse"))}
    out = {"points": list(pts.values()), "warnings": sorted(warnings), "timings_s": timings}
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def kappa(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    po = np.mean(a == b)
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--out", default=str(REPO / "docs/validation"))
    ap.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "lunascout_validation_cache"))
    args = ap.parse_args()
    out, cache = Path(args.out), Path(args.cache)
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    x0, x1, y0, y1 = 60000.0, 86000.0, 105000.0, 149000.0
    results = []
    for t_iso, label in DATES:
        lon, lat = subsolar(t_iso)
        print(f"{t_iso}  subsolar lon {lon:.4f} lat {lat:.4f}  ({label})")
        mos, gx0, gy0, px = fetch_qm_mosaic(lon, lat, x0, x1, y0, y1, cache / "qm")
        ls = lunascout_points(args.api, t_iso, cache)
        P = ls["points"]
        x = np.array([p["x"] for p in P]); y = np.array([p["y"] for p in P])
        ours = np.array([p["lit"] for p in P])
        coarse = np.array([p["coarse"] for p in P])
        qm = sample(mos, gx0, gy0, px, x, y) > 0.5
        lo, hi = sample(mos, gx0, gy0, px, x, y, radius_px=1)
        edge = lo != hi                                   # QuickMap shadow edge within ~30-40 m
        agree = ours == qm
        agree_tol = agree | edge
        res = {"utc": t_iso, "label": label, "subsolar_lon": round(lon, 4), "subsolar_lat": round(lat, 4),
               "n": int(len(P)), "lit_ours": round(float(ours.mean()), 3), "lit_qm": round(float(qm.mean()), 3),
               "agreement": round(float(agree.mean()), 3), "kappa": round(float(kappa(ours, qm)), 3),
               "agreement_edge_tolerant": round(float(agree_tol.mean()), 3),
               "ours_lit_qm_dark": int((ours & ~qm).sum()), "ours_dark_qm_lit": int((~ours & qm).sum()),
               "agreement_5m_tile": round(float(agree[~coarse].mean()), 3) if (~coarse).any() else None,
               "agreement_20m_area": round(float(agree[coarse].mean()), 3) if coarse.any() else None,
               "n_5m_tile": int((~coarse).sum()), "n_20m_area": int(coarse.sum()),
               "qm_lit_fraction_whole_area": round(float((mos > 0.5).mean()), 3),
               "api_call_s_median": round(float(np.median(ls["timings_s"])), 2) if ls["timings_s"] else None}
        results.append(res)
        print("  ", json.dumps(res))

        # Figure: QuickMap shadows | LunaScout points | disagreement
        ext = [gx0 / 1000, (gx0 + mos.shape[1] * px) / 1000, (gy0 - mos.shape[0] * px) / 1000, gy0 / 1000]
        fig, axs = plt.subplots(1, 3, figsize=(15, 8.6), sharex=True, sharey=True)
        cm = ListedColormap(["#3b1f5c", "#fde725"])
        axs[0].imshow(mos > 0.5, extent=ext, cmap=cm, interpolation="nearest")
        axs[0].set_title("LROC QuickMap 'Terrain Shadows @UTC'\n(ACT, 20 m/px; yellow = sunlit)")
        axs[1].imshow(mos > 0.5, extent=ext, cmap=cm, interpolation="nearest", alpha=0.25)
        axs[1].scatter(x[ours] / 1000, y[ours] / 1000, s=7, c="#FFE066", edgecolors="k", linewidths=0.2, label="LunaScout: lit")
        axs[1].scatter(x[~ours] / 1000, y[~ours] / 1000, s=7, c="#5b2a86", edgecolors="w", linewidths=0.2, label="LunaScout: shadow")
        axs[1].set_title("LunaScout live API, sun_at_touchdown\n(points of 5 km circles; QuickMap faint behind)")
        axs[1].legend(loc="lower left", fontsize=8)
        axs[2].imshow(mos > 0.5, extent=ext, cmap="gray", interpolation="nearest", alpha=0.35)
        axs[2].scatter(x[agree] / 1000, y[agree] / 1000, s=6, c="#3DDC84", label=f"agree ({agree.mean():.1%})")
        m1 = ours & ~qm; m2 = ~ours & qm
        axs[2].scatter(x[m1] / 1000, y[m1] / 1000, s=14, c="#FF9F43", marker="^", label=f"LunaScout lit, QM shadow ({m1.sum()})")
        axs[2].scatter(x[m2] / 1000, y[m2] / 1000, s=14, c="#FF6B6B", marker="x", label=f"LunaScout shadow, QM lit ({m2.sum()})")
        axs[2].set_title(f"Agreement {agree.mean():.1%}, Cohen's kappa {res['kappa']:.2f}\n(edge-tolerant {agree_tol.mean():.1%})")
        axs[2].legend(loc="lower left", fontsize=8)
        for a in axs:
            a.axhline(131, color="c", lw=0.8, ls="--")
            a.set_xlim(x0 / 1000, x1 / 1000); a.set_ylim(y0 / 1000, y1 / 1000)
            a.set_xlabel("x (km, south polar stereographic)")
        axs[0].set_ylabel("y (km)")
        axs[0].text(60.5, 131.4, "north edge of 5 m tile", color="c", fontsize=7)
        fig.suptitle(f"{t_iso} - {label}; subsolar lon {lon:.3f}, lat {lat:.3f} (from LunaScout's Horizons table)", fontsize=11)
        ax_, ay_ = latlon_to_xy(np.array([-84.79059, -84.78]), np.array([29.19567, 29.13]))
        for a in axs:
            a.scatter(ax_[:1] / 1000, ay_[:1] / 1000, s=90, marker="*", c="cyan", edgecolors="k", zorder=5)
            a.scatter(ax_[1:] / 1000, ay_[1:] / 1000, s=60, marker="P", c="white", edgecolors="k", zorder=5)
        axs[0].text(ax_[0] / 1000 + 0.6, ay_[0] / 1000 - 1.2, "IM-2 actual (*) / intended (+)", color="cyan", fontsize=7)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        fig.savefig(out / f"quickmap_vs_lunascout_{t_iso[:10]}.png", dpi=110)
        plt.close(fig)
    athena = athena_series(args.api, cache)
    (out / "quickmap_comparison.json").write_text(json.dumps({"dates": results, "athena_site_hourly": athena}, indent=1))


def athena_series(api: str, cache: Path):
    """QuickMap shadow value at the IM-2 sites, hourly for the first 14 h, vs LunaScout's target timeseries."""
    sites = {"actual": (-84.79059, 29.19567), "intended": (-84.78, 29.13)}
    t0 = dt.datetime(2025, 3, 6, 17, tzinfo=dt.timezone.utc)
    out = {}
    for name, (lat, lon) in sites.items():
        body = {"target": {"lat": lat, "lon": lon}, "landing_utc": "2025-03-06T17:00:00Z", "mission_days": 1,
                "ellipse": {"semi_major_m": 300, "semi_minor_m": 300, "azimuth_deg": 0},
                "options": {"delay_days_max": 0, "include_recommendations": False}}
        ts = requests.post(api + "/analyze", json=body, timeout=120).json()["timeseries"]
        x, y = latlon_to_xy(np.array([lat]), np.array([lon]))
        rows = []
        for h in range(15):
            t_iso = (t0 + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
            slon, slat = subsolar(t_iso)
            mos, gx0, gy0, px = fetch_qm_mosaic(slon, slat, float(x[0]) - 50, float(x[0]) + 50,
                                                float(y[0]) - 50, float(y[0]) + 50, cache / "qm")
            v = float(sample(mos, gx0, gy0, px, x, y)[0])
            lo, hi = sample(mos, gx0, gy0, px, x, y, radius_px=1)
            rows.append({"utc": t_iso, "qm_lit": v > 0.5, "qm_3x3_min": float(lo[0]), "qm_3x3_max": float(hi[0]),
                         "ls_lit": bool(ts["sun_lit"][h]), "ls_sun_el": ts["sun_el_deg"][h],
                         "ls_horizon_at_sun": ts["horizon_at_sun_deg"][h], "ls_margin": ts["sun_margin_deg"][h]})
        out[name] = rows
        print(name, "QM lit hours", sum(r["qm_lit"] for r in rows), "/ 15; LunaScout lit hours",
              sum(r["ls_lit"] for r in rows), "/ 15; min LS margin", min(r["ls_margin"] for r in rows))
    return out


if __name__ == "__main__":
    main()
