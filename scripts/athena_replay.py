# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Replay the IM-2 "Athena" landing (2025-03-06) with LunaScout and write docs/athena_replay.md.

    python scripts/athena_replay.py              # needs the real ephemeris (engine/ephemeris.py + npz)
    python scripts/athena_replay.py --stdout     # print the report instead of writing the file

Two targets, each run twice:
    A. target = intended site, ellipse 500 x 300 m with its major axis pointing at the actual
       touchdown (369 m away), so the actual site is inside the ellipse;
    B. target = actual touchdown (same ellipse size and orientation);
    each without the Sun-clearance margin (min_sun_margin_deg = 0, the v1.1 behavior) and with the
    default margin (v1.2: 0 deg on the 5 m tile, 2.86 deg on the coarse 20 m DEM).
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
ACTUAL = {"lat": -84.7906, "lon": 29.1957}
LANDING_UTC = "2025-03-06T17:31:00Z"
MISSION_DAYS = 10
SEMI_MAJOR_M, SEMI_MINOR_M = 500.0, 300.0
SOURCES = [
    "Intended site: LROC featured image \"IM-2 Landing Region\", https://www.lroc.asu.edu/images/1401",
    "Actual touchdown: Wikipedia \"IM-2\" / \"Mons Mouton\" (citing LROC); ~250 m from target per Intuitive "
    "Machines, NASA said more than 400 m",
    "Touchdown time: Space.com, \"12:31 p.m. EST (1731 GMT)\"",
    "Mission end ~13 h after landing, lander on its side in a shadowed crater: "
    "https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/",
]


def run() -> dict:
    from engine import analyze as az
    from engine import geo

    dist = float(geo.great_circle_distance(INTENDED["lat"], INTENDED["lon"], ACTUAL["lat"], ACTUAL["lon"]))
    bearing = float(geo.initial_bearing(INTENDED["lat"], INTENDED["lon"], ACTUAL["lat"], ACTUAL["lon"])) % 360.0
    ellipse = {"semi_major_m": SEMI_MAJOR_M, "semi_minor_m": SEMI_MINOR_M, "azimuth_deg": round(bearing, 2)}
    base = {"landing_utc": LANDING_UTC, "mission_days": MISSION_DAYS, "ellipse": ellipse,
            "options": {"include_recommendations": True}}
    out = {"distance_m": dist, "bearing_deg": bearing, "ellipse": ellipse}
    ax, ay = geo.latlon_to_xy(ACTUAL["lat"], ACTUAL["lon"])
    for suffix, margin in (("0", 0.0), ("", None)):          # "0": no margin; "": default margin
        lim = {"min_sun_margin_deg": margin}
        ra = az.analyze(dict(base, target=INTENDED, limits=lim))
        rb = az.analyze(dict(base, target=ACTUAL, limits=lim))
        d = [float(np.hypot(p["x_m"] - ax, p["y_m"] - ay)) for p in ra["points"]]
        out["A" + suffix], out["B" + suffix] = ra, rb
        out["nearest_point_A" + suffix] = ra["points"][int(np.argmin(d))]
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
    b0, b = res["B0"], res["B"]
    ts = b["timeseries"]
    el = np.array(ts["sun_el_deg"])
    margin = np.array(ts["sun_margin_deg"])
    margin13 = float(margin[:13].min())                     # Athena operated ~13 h
    disk = 0.2665                                           # solar angular radius, deg
    rims = ", ".join(f"{np.tan(np.radians(margin13 + disk)) * d:.1f} m at {d} m" for d in (10, 20, 50))
    req = _metric(b, "min_sun_margin")
    out = []
    if _flagged(b0) == "no":
        out.append(
            "- **Without the margin (v1.1) the result does not match reality.** LunaScout rates the actual "
            f"touchdown **{b0['summary']['verdict']}** (survival probability {b0['summary']['survival_probability']:.2f}), "
            "but Athena lost power about 13 h after landing.")
    else:
        out.append("- Without the margin (v1.1) LunaScout already flags the actual touchdown "
                   f"({b0['summary']['verdict']}).")
    if _flagged(b) != "no":
        out.append(
            f"- **With the default margin (v1.2) the actual touchdown is {b['summary']['verdict']}** "
            f"(survival probability {b['summary']['survival_probability']:.2f}, "
            f"{b['summary']['survival_probability_incl_risky']:.2f} including risky): minimum Sun clearance "
            f"{req['display']} against {req['limit_display'].replace('≥ ', '')}. The amber points mean *Sun clearance "
            "below the terrain-data uncertainty margin (coarse DEM)*: the data are too coarse to guarantee sunlight. "
            "It is not a computed shadow, and LunaScout still does not say the mission would end.")
    else:
        out.append(f"- With the default margin (v1.2) the result does not change ({b['summary']['verdict']}).")
    n_amber = sum(p["class"] == "risky" for p in b["points"])
    out.append(
        f"- The flag is not specific to the touchdown spot: {n_amber} of {len(b['points'])} points of ellipse B "
        "are amber, because the whole area sees a Sun only a few degrees up and is evaluated on the coarse DEM. "
        "LunaScout says \"the data cannot guarantee sunlight anywhere here\", which is the right caution, not a "
        "prediction that Athena's exact spot was in shadow.")
    out.append(
        "- The margin comes from the DEM resolution, not from Athena: 2.86 deg = atan(1 m / 20 m), the angle of "
        "1 m of unresolved relief one 20 m pixel away (ENGINE.md, \"Sun clearance\"). In fairness, the 1.6 deg "
        "clearance of the earlier replay was already known when the rule was chosen; the formula itself was "
        "fixed before re-running.")
    out.append(
        f"- The real ephemeris and the 20/40 m terrain put the Sun only **{margin13:.1f} deg above the DEM horizon** "
        f"during the first 13 h (Sun elevation {el[:13].min():.1f}-{el[:13].max():.1f} deg). To hide the whole solar "
        f"disk, local relief only has to rise above the panels by about {rims}. Athena came to rest inside a "
        "shadowed crater; relief that small (a crater rim a few tens of meters away, less than a meter or two "
        "high) is below what a 20 m DEM resolves, so that shadow is not in our data. (The size of Athena's "
        "crater is not verified here; the numbers only show how little relief is needed.)")
    out.append(
        "- Athena also ended up on its side, so its solar panels were close to the ground and not facing the Sun. "
        "LunaScout assumes an upright lander with panels 2 m above the terrain.")
    return out


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
        f"- Intended site: lat {INTENDED['lat']}, lon {INTENDED['lon']} E. Actual touchdown: lat {ACTUAL['lat']}, "
        f"lon {ACTUAL['lon']} E. Distance between them: {res['distance_m']:.0f} m, bearing {res['bearing_deg']:.1f} deg.",
        f"- Landing {LANDING_UTC} (the engine uses a 1 h step, so 17:00 UTC), mission {MISSION_DAYS} days, "
        "default limits (max darkness 50 h, max comms gap 72 h, Earth >= 50%, slope <= 8 deg).",
        f"- Ellipse {SEMI_MAJOR_M:.0f} x {SEMI_MINOR_M:.0f} m (semi-axes), major axis at azimuth "
        f"{res['ellipse']['azimuth_deg']:.1f} deg, i.e. pointing from the intended site at the actual one. Why: the "
        f"actual site ({res['distance_m']:.0f} m away) must be inside, and the reported miss distances "
        "(~250 m per Intuitive Machines, >400 m per NASA) suggest a dispersion of a few hundred meters, larger "
        "along track than across.",
        "- Terrain: both sites are outside the LOLA 5 m/px tile; heights and slopes come from the LOLA 20 m/px "
        "polar DEM, horizons from the 20 m and 40 m DEMs out to 100 km.",
        "",
        "## Results",
        "",
        "Without margin = `min_sun_margin_deg: 0` (v1.1 behavior). With margin = default of v1.2 (2.86 deg here, "
        "because both sites are on the coarse 20 m DEM).",
        "",
        "| | A: intended, no margin | A: intended, with margin | B: actual, no margin | B: actual, with margin |",
        "|---|---|---|---|---|",
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
        ("Minimum Sun clearance (target)", lambda r: f"{_metric(r, 'min_sun_margin')['display']} "
                                                      f"({_metric(r, 'min_sun_margin')['limit_display']})"),
        ("Target slope", lambda r: f"{r['target']['slope_deg']:.1f} deg ({r['target']['slope_dem_m']:.0f} m DEM)"),
        ("Would LunaScout have flagged the risk?", _flagged),
    ]:
        lines.append(f"| {label} | {fn(res['A0'])} | {fn(a)} | {fn(res['B0'])} | {fn(b)} |")
    lines += [
        "",
        f"Sample point of run A nearest to the actual touchdown ({res['nearest_point_dist_m']:.0f} m from it): class "
        f"**{res['nearest_point_A0']['class']}** without margin, **{n['class']}** with margin "
        f"(reasons {n['reasons'] or 'none'}); lit at touchdown: {n['sun_at_touchdown']}, "
        f"hours until sunset {n['hours_until_sunset']:.0f}, slope {n['slope_deg']:.1f} deg "
        f"({'coarse 20 m' if n['slope_coarse'] else '5 m'}).",
        "",
        "## Honest reading",
        "",
    ] + _honest(res) + [
        "- Tip-over is captured only through the DEM slope. Here the slope comes from a 20 m DEM, which smooths "
        "boulders, crater rims and small craters, so the real local slope was likely steeper than shown.",
        "- The engine models sunlight, Earth visibility and slope; it does not model the descent, the landing "
        "dynamics or the lander's attitude after touchdown (Athena lay on its side, so its panels could not "
        "face the Sun even where the ground was lit).",
        "",
        "## Warnings returned by the engine (run A, with margin)",
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
        Path(args.json).write_text(json.dumps({k: res[k] for k in ("A0", "B0", "A", "B")}, indent=1),
                                   encoding="utf-8")
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
