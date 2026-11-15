# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Replay the IM-2 "Athena" landing (2025-03-06) with LunaScout and write docs/athena_replay.md.

    python scripts/athena_replay.py              # needs the real ephemeris (engine/ephemeris.py + npz)
    python scripts/athena_replay.py --stdout     # print the report instead of writing the file

Two targets:
    A. target = intended site, ellipse 500 x 300 m with its major axis pointing at the actual
       touchdown, so the actual site is inside the ellipse;
    B. target = actual touchdown (same ellipse size and orientation).
Main result = margin 0 (pure real data, the v1.3 default). An informational sensitivity table runs
Sun-clearance margins of 0, 1, 2, 2.86 and 4 deg; it is NOT part of the default model.
Landing 2025-03-06T17:31:00Z (floored to 17:00 by the 1 h time step), mission 10 days.

The report is written only with the real JPL Horizons ephemeris. With the synthetic stub
(LUNASCOUT_ALLOW_STUB=1) the script refuses to write docs/ and only prints, labeled as synthetic.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

INTENDED = {"lat": -84.78, "lon": 29.13}
ACTUAL = {"lat": -84.79059, "lon": 29.19567}
LANDING_UTC = "2025-03-06T17:31:00Z"
MISSION_DAYS = 10
SEMI_MAJOR_M, SEMI_MINOR_M = 500.0, 300.0
MARGINS = (0.0, 1.0, 2.0, 2.86, 4.0)
SOURCES = [
    "Intended site: LROC featured image \"IM-2 Landing Region\", https://www.lroc.asu.edu/images/1401",
    "Actual touchdown (84.79059 S, 29.19567 E): Hancock et al. 2026, \"The Polar Resources Ice Mining "
    "Experiment-1 (PRIME-1) Payload Operations Summary from the IM-2 Mission\", The Planetary Science "
    "Journal 7, https://doi.org/10.3847/PSJ/ae732f, Sect. 1.2 (about 500 m from the intended site)",
    "Crater of about 20 m diameter, lander on its side: LROC \"IM-2 Athena Seen Obliquely\" caption, "
    "NAC M1495922531LR [NASA/GSFC/Arizona State University], https://lroc.im-ldi.com/images/1408; "
    "reported by https://www.leonarddavid.com/?p=44873",
    "Touchdown time: Space.com, \"12:31 p.m. EST (1731 GMT)\"",
    "Mission end ~13 h after landing: https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/",
]


def run() -> dict:
    from engine import analyze as az
    from engine import geo

    dist = float(geo.great_circle_distance(INTENDED["lat"], INTENDED["lon"], ACTUAL["lat"], ACTUAL["lon"]))
    bearing = float(geo.initial_bearing(INTENDED["lat"], INTENDED["lon"], ACTUAL["lat"], ACTUAL["lon"])) % 360.0
    ellipse = {"semi_major_m": SEMI_MAJOR_M, "semi_minor_m": SEMI_MINOR_M, "azimuth_deg": round(bearing, 2)}
    base = {"landing_utc": LANDING_UTC, "mission_days": MISSION_DAYS, "ellipse": ellipse,
            "options": {"include_recommendations": True}}
    out = {"distance_m": dist, "bearing_deg": bearing, "ellipse": ellipse, "sens": []}
    ax, ay = geo.latlon_to_xy(ACTUAL["lat"], ACTUAL["lon"])
    for margin in MARGINS:
        lim = {"min_sun_margin_deg": margin}
        ra = az.analyze(dict(base, target=INTENDED, limits=lim))
        rb = az.analyze(dict(base, target=ACTUAL, limits=lim))
        out["sens"].append((margin, ra, rb))
        if margin == 0.0:
            d = [float(np.hypot(p["x_m"] - ax, p["y_m"] - ay)) for p in ra["points"]]
            out["A"], out["B"] = ra, rb
            out["nearest_point_A"] = ra["points"][int(np.argmin(d))]
            out["nearest_point_dist_m"] = float(min(d))
    out["is_sample"] = out["A"]["is_sample"]
    return out


def _metric(r, mid):
    return next(m for m in r["target_metrics"] if m["id"] == mid)


def _flagged(r) -> str:
    s = r["summary"]
    if s["verdict"] == "not_viable":
        return "yes (not viable)"
    if s["verdict"] == "risky":
        return "yes, as amber (risky)"
    if s["survival_probability"] < 0.5:
        return "partly (target viable, P < 0.5)"
    return "no"


def _honest(res: dict) -> list[str]:
    """Plain-language comparison with what happened, computed from run B (actual touchdown)."""
    b = res["B"]
    ts = b["timeseries"]
    el = np.array(ts["sun_el_deg"])
    margin13 = float(np.array(ts["sun_margin_deg"])[:13].min())      # Athena operated ~13 h
    disk = 0.2665                                                     # solar angular radius, deg
    rims = ", ".join(f"{np.tan(np.radians(margin13 + disk)) * d:.1f} m at {d} m" for d in (10, 20, 50))
    out = []
    if _flagged(b) == "no":
        out.append(
            "- **The main result (real data only, margin 0) does not match what happened.** With the 20 m DEM "
            f"LunaScout rates the actual touchdown **{b['summary']['verdict']}** (survival probability "
            f"{b['summary']['survival_probability']:.2f}), but Athena lost power about 13 h after landing.")
    else:
        out.append("- With real data only (margin 0) LunaScout already flags the actual touchdown "
                   f"({b['summary']['verdict']}).")
    out.append(
        "- **Why: the data cannot resolve the crater.** Athena ended on its side inside a crater of about 20 m "
        "diameter (LROC image caption, NASA/GSFC/Arizona State University, reported by leonarddavid.com), which is "
        "about one pixel of the 20 m DEM. The available terrain data cannot represent it.")
    out.append(
        f"- The real ephemeris and the 20/40 m terrain put the Sun **{margin13:.1f} deg above the DEM horizon** "
        f"during the first 13 h (Sun elevation {el[:13].min():.1f}-{el[:13].max():.1f} deg). To hide the whole solar "
        f"disk, local relief only has to rise above the panels by about {rims}; relief that small is below what "
        "a 20 m DEM resolves.")
    out.append(
        "- The lander tipped over: its panels were near the ground and misoriented. LunaScout assumes an upright "
        "lander with panels 2 m above the terrain.")
    return out


def _sens_table(res: dict) -> list[str]:
    rows = ["| Sun-clearance margin | Survival probability (A: intended site) | "
            "Survival probability (B: actual site) | Actual-site class (B target) |", "|---|---|---|---|"]
    for margin, ra, rb in res["sens"]:
        rows.append(f"| {margin:g}° | {ra['summary']['survival_probability']:.3f} | "
                    f"{rb['summary']['survival_probability']:.3f} | {rb['summary']['verdict']} |")
    return rows


def report(res: dict) -> str:
    a, b, n = res["A"], res["B"], res["nearest_point_A"]
    lines = [
        "<!-- Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team. -->",
        "# IM-2 \"Athena\" replay",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `python scripts/athena_replay.py`.",
        "",
    ]
    if res["is_sample"]:
        lines += ["> **SYNTHETIC EPHEMERIS — these numbers are NOT real.**", ""]
    lines += [
        "## Inputs",
        "",
        f"- Intended site: lat {INTENDED['lat']}, lon {INTENDED['lon']} E (LROC, primary source). Actual touchdown: "
        f"lat {ACTUAL['lat']}, lon {ACTUAL['lon']} E (Hancock et al. 2026, The Planetary Science Journal 7, "
        "https://doi.org/10.3847/PSJ/ae732f; it agrees with the LROC caption, 84.7906 S, 29.1957 E). Distance "
        f"between the two coordinates: {res['distance_m']:.0f} m, bearing {res['bearing_deg']:.1f} deg. The paper "
        "reports the lander about 500 m from the intended site, so the intended-site coordinates used here are "
        "approximate (limitation).",
        f"- Landing {LANDING_UTC} (the engine uses a 1 h step, so 17:00 UTC), mission {MISSION_DAYS} days, "
        "default limits (max darkness 50 h, max comms gap 72 h, Earth >= 50%, slope <= 8 deg).",
        f"- Ellipse {SEMI_MAJOR_M:.0f} x {SEMI_MINOR_M:.0f} m (semi-axes), major axis at azimuth "
        f"{res['ellipse']['azimuth_deg']:.1f} deg, i.e. pointing from the intended site at the actual one, so the "
        "actual site is inside the ellipse.",
        "- Terrain: both sites are outside the LOLA 5 m/px tile; heights and slopes come from the LOLA 20 m/px "
        "polar DEM, horizons from the 20 m and 40 m DEMs out to 100 km.",
        "",
        "## Main result (real data only, `min_sun_margin_deg` = 0)",
        "",
        "| | A: intended site | B: actual touchdown |",
        "|---|---|---|",
    ]
    for label, fn in [
        ("Survival probability (viable / points)", lambda r: f"{r['summary']['survival_probability']:.3f} "
                                                              f"({r['summary']['viable']}/{r['summary']['n_points']})"),
        ("Incl. risky", lambda r: f"{r['summary']['survival_probability_incl_risky']:.3f}"),
        ("Target verdict", lambda r: r["summary"]["verdict"]),
        ("Sun at touchdown (target)", lambda r: _metric(r, "sun_at_touchdown")["display"]),
        ("Time until sunset (target)", lambda r: _metric(r, "hours_until_sunset")["display"]),
        ("Longest darkness (target)", lambda r: _metric(r, "longest_dark")["display"]),
        ("Earth visible (target)", lambda r: _metric(r, "earth_pct")["display"]),
        ("Minimum Sun clearance (target, informative)", lambda r: _metric(r, "min_sun_margin")["display"]),
        ("Target slope", lambda r: f"{r['target']['slope_deg']:.1f} deg ({r['target']['slope_dem_m']:.0f} m DEM)"),
        ("Would LunaScout have flagged the risk?", _flagged),
    ]:
        lines.append(f"| {label} | {fn(a)} | {fn(b)} |")
    lines += [
        "",
        f"Sample point of run A nearest to the actual touchdown ({res['nearest_point_dist_m']:.0f} m from it): class "
        f"**{n['class']}** (reasons {n['reasons'] or 'none'}); lit at touchdown: {n['sun_at_touchdown']}, "
        f"hours until sunset {n['hours_until_sunset']:.0f}, slope {n['slope_deg']:.1f} deg "
        f"({'coarse 20 m' if n['slope_coarse'] else '5 m'}).",
        "",
        "## Honest reading",
        "",
    ] + _honest(res) + [
        "- Tip-over is captured only through the DEM slope, which a 20 m DEM smooths (boulders, crater rims, "
        "small craters), so the real local slope was likely steeper than shown.",
        "- The engine models sunlight, Earth visibility and slope; it does not model the descent, the landing "
        "dynamics or the lander's attitude after touchdown.",
        "",
        "## Sensitivity to unresolved terrain (informational, not part of the default model)",
        "",
        "Sensitivity to unresolved terrain, not part of the default model. The user-set `min_sun_margin_deg` "
        "marks points amber (`low_sun_margin`) when the Sun clears the computed horizon by less than the margin "
        "during lit hours. 2.86 deg = atan(1 m / 20 m).",
        "",
    ] + _sens_table(res) + [
        "",
        "## Limitations",
        "",
        "- Intended-site coordinates (-84.78, 29.13) come from the LROC featured image (primary source) and are "
        "approximate; the paper puts the touchdown about 500 m from the intended site, while these coordinates "
        f"are {res['distance_m']:.0f} m apart.",
        "- The 20 m DEM cannot resolve the ~20 m crater Athena landed in, and the lander's attitude is not modeled.",
        "",
        "## Warnings returned by the engine (run A, margin 0)",
        "",
    ] + [f"- {w}" for w in a["warnings"]] + [
        "",
        "## Sources",
        "",
    ] + [f"- {s}" for s in SOURCES + a["sources"]] + [""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--json", help="also dump the raw responses to this file")
    args = ap.parse_args()
    res = run()
    text = report(res)
    if args.json:
        Path(args.json).write_text(json.dumps({k: res[k] for k in ("A", "B")}, indent=1), encoding="utf-8")
    if args.stdout or res["is_sample"]:
        if res["is_sample"] and not args.stdout:
            print("Synthetic ephemeris loaded: NOT writing docs/athena_replay.md. Report below is NOT real.\n")
        print(text)
        return 0
    out = REPO_ROOT / "docs" / "athena_replay.md"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
