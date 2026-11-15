# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Physics and sanity checks against the live API (Agent 06, priority 4).

Measured values are appended to docs/validation/live_checks.json for the validation report.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pytest

from .conftest import ATHENA_ACTUAL, DEM_CENTER, SUMMIT, analyze

OUT = Path(__file__).resolve().parents[2] / "docs" / "validation" / "live_checks.json"
TILT = 1.54


def record(key, value):
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data[key] = value
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, default=float))


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.parametrize("name,site", [("dem_center", DEM_CENTER), ("athena_actual", ATHENA_ACTUAL)])
def test_max_sun_elevation_over_a_year(api, name, site):
    """Max geometric Sun elevation over 2027 ~= (90 - |lat|) + 1.54 deg (13 x 30-day windows)."""
    t0 = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    mx = -99.0
    for k in range(13):
        ts = analyze(api, *site, landing_utc=_iso(t0 + dt.timedelta(days=30 * k)), mission_days=30,
                     ellipse=(300, 300, 0))["timeseries"]
        assert ts["n"] == 720 and len(ts["sun_el_deg"]) == 720
        mx = max(mx, max(ts["sun_el_deg"]))
    expected = (90 - abs(site[0])) + TILT
    record(f"max_sun_el_2027_{name}", {"measured": mx, "expected": expected})
    assert abs(mx - expected) < 0.1, (mx, expected)


def _lit_points(d):
    return {(round(p["x_m"]), round(p["y_m"])): p["sun_at_touchdown"] for p in d["points"]}


def test_half_and_full_synodic_month(api):
    """+14.77 d changes illumination a lot; +29.53 d broadly repeats it (same ellipse, same hour of day)."""
    t0 = dt.datetime(2027, 10, 12, 14, tzinfo=dt.timezone.utc)
    kw = dict(mission_days=7, ellipse=(2500, 2500, 0))
    runs = {lab: analyze(api, *SUMMIT, landing_utc=_iso(t0 + dt.timedelta(hours=h)), **kw)
            for lab, h in (("t0", 0), ("half", 354), ("full", 709))}
    p0 = _lit_points(runs["t0"])
    res = {}
    for lab in ("half", "full"):
        p = _lit_points(runs[lab])
        keys = sorted(set(p0) & set(p))
        agree = float(np.mean([p0[k] == p[k] for k in keys]))
        daz = abs((runs[lab]["timeseries"]["sun_az_deg"][0] - runs["t0"]["timeseries"]["sun_az_deg"][0] + 180) % 360 - 180)
        lit = [runs[lab]["timeseries"]["sun_lit"], runs["t0"]["timeseries"]["sun_lit"]]
        res[lab] = {"touchdown_lit_agreement": round(agree, 3), "sun_az_shift_deg": round(daz, 2),
                    "target_lit_hours_agreement_7d": round(float(np.mean(np.array(lit[0]) == np.array(lit[1]))), 3),
                    "lit_fraction": round(float(np.mean(list(p.values()))), 3)}
    res["t0"] = {"lit_fraction": round(float(np.mean(list(p0.values()))), 3)}
    record("synodic_shift_summit_2027-10-12", res)
    assert res["half"]["sun_az_shift_deg"] > 150 and res["full"]["sun_az_shift_deg"] < 15
    assert res["full"]["touchdown_lit_agreement"] > res["half"]["touchdown_lit_agreement"] + 0.2
    assert res["full"]["touchdown_lit_agreement"] >= 0.75


# Chosen so that the limits actually bind (a case with P = 0 everywhere would make the test vacuous).
CASES = [(SUMMIT, "2027-10-12T14:00:00Z", 7), (SUMMIT, "2026-01-20T00:00:00Z", 14),
         (ATHENA_ACTUAL, "2025-03-06T17:00:00Z", 10), (DEM_CENTER, "2026-01-20T00:00:00Z", 14)]


@pytest.mark.parametrize("site,t,days", CASES)
def test_monotonicity(api, site, t, days):
    def P(**limits):
        s = analyze(api, *site, landing_utc=t, mission_days=days, ellipse=(1500, 1000, 30), limits=limits)["summary"]
        return s["survival_probability"], s["survival_probability_incl_risky"]

    slope = [P(max_slope_deg=v) for v in (15, 12, 8, 6, 4, 2)]
    dark = [P(max_dark_h=v) for v in (5, 20, 50, 100, 200)]
    gap = [P(max_comm_gap_h=v) for v in (5, 24, 72, 150, 300)]
    earth = [P(min_earth_pct=v) for v in (90, 70, 50, 20, 0)]
    flat = all(len({x for x, _ in seq}) == 1 and len({y for _, y in seq}) == 1 for seq in (slope, dark, gap, earth))
    assert not flat, "vacuous case: no limit changes the result"
    record(f"monotonicity_{site[0]}_{t[:10]}", {"slope_15_to_2": slope, "dark_5_to_200": dark,
                                                "gap_5_to_300": gap, "earth_90_to_0": earth})
    for seq, name in ((slope, "stricter slope"),):
        assert all(a[0] >= b[0] for a, b in zip(seq, seq[1:])), (name, seq)
        assert all(a[1] >= b[1] for a, b in zip(seq, seq[1:])), (name, seq)
    for seq, name in ((dark, "larger max_dark_h"), (gap, "larger gap"), (earth, "lower min_earth_pct")):
        assert all(a[0] <= b[0] for a, b in zip(seq, seq[1:])), (name, seq)
        assert all(a[1] <= b[1] for a, b in zip(seq, seq[1:])), (name, seq)


def test_delay_curve_day0_equals_summary(api):
    for site, t, days in CASES:
        d = analyze(api, *site, landing_utc=t, mission_days=days, options={"delay_days_max": 10})
        assert len(d["delay_curve"]) == 11
        assert d["delay_curve"][0]["survival_probability"] == d["summary"]["survival_probability"]
        # delay_tolerance_days = largest d with target viable/risky for every delay 0..d (-1 if none)
        tol = -1
        for e in d["delay_curve"]:
            if not e["target_viable"]:
                break
            tol = e["delay_days"]
        assert d["delay_tolerance_days"] == tol, (d["delay_tolerance_days"], d["delay_curve"])


def test_delay_shift_equals_fresh_run(api):
    """delay_curve[k] must equal a fresh analysis landing k days later (CONTRACT 4.3: 'everything is recomputed')."""
    site, t, days = SUMMIT, "2027-10-12T14:00:00Z", 7
    d = analyze(api, *site, landing_utc=t, mission_days=days, options={"delay_days_max": 5})
    t0 = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    got = []
    for k in (1, 3, 5):
        f = analyze(api, *site, landing_utc=_iso(t0 + dt.timedelta(days=k)), mission_days=days)
        got.append((k, d["delay_curve"][k]["survival_probability"], f["summary"]["survival_probability"]))
    record("delay_curve_vs_fresh_runs_summit", got)
    for k, a, b in got:
        assert abs(a - b) <= 0.005, got
