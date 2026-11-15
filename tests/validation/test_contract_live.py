# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Contract shape (CONTRACT v1.4 section 4) and internal consistency of live /api/analyze responses.

Beyond key presence, this re-derives values the response itself implies: the center-of-disk lit rule,
target metrics from the timeseries, summary counts, and every point's class from CONTRACT 4.4.
"""
from __future__ import annotations

import numpy as np
import pytest

from .conftest import ATHENA_ACTUAL, DEM_CENTER, SUMMIT, analyze

TOP = {"schema_version", "is_sample", "computed_utc", "compute_ms", "inputs", "coverage", "target", "summary",
       "target_metrics", "points", "timeseries", "horizon_profile", "delay_curve", "delay_tolerance_days",
       "recommendations", "map", "warnings", "sources"}
SUMMARY = {"n_points", "viable", "risky", "not_viable", "survival_probability", "survival_probability_incl_risky",
           "checks_passed", "checks_total", "verdict"}
POINT = {"id", "x_m", "y_m", "lat", "lon", "class", "reasons", "slope_deg", "sun_hours", "longest_dark_h",
         "earth_pct", "longest_comm_gap_h", "hours_until_sunset", "sun_at_touchdown"}
TS = {"t0_utc", "step_h", "n", "sun_az_deg", "sun_el_deg", "horizon_at_sun_deg", "sun_lit", "earth_az_deg",
      "earth_el_deg", "horizon_at_earth_deg", "earth_visible", "sun_visible_fraction", "sun_margin_deg"}
METRIC_IDS = ["sun_at_touchdown", "sun_hours", "longest_dark", "min_sun_margin", "earth_pct", "longest_comm_gap",
              "hours_until_sunset", "hours_until_earthset", "area_over_slope", "delay_tolerance"]
REASONS = {"slope", "darkness", "comms_gap", "earth_time", "no_sun_at_touchdown", "low_sun_margin"}

SCENARIOS = [
    dict(site=SUMMIT, t="2027-10-12T14:00:00Z", days=7, opts={"delay_days_max": 30, "include_recommendations": True}),
    dict(site=DEM_CENTER, t="2026-04-04T12:00:00Z", days=7, opts={"delay_days_max": 5}),
    dict(site=ATHENA_ACTUAL, t="2025-03-06T17:00:00Z", days=10, opts={"delay_days_max": 3}),
    dict(site=DEM_CENTER, t="2026-06-23T02:00:00Z", days=14, opts={"delay_days_max": 0}),
]


@pytest.fixture(scope="module", params=range(len(SCENARIOS)), ids=lambda i: f"scenario{i}")
def resp(api, request):
    s = SCENARIOS[request.param]
    return analyze(api, *s["site"], landing_utc=s["t"], mission_days=s["days"], options=s["opts"]), s


def _runs(a, value):
    best = cur = 0
    for v in a:
        cur = cur + 1 if v == value else 0
        best = max(best, cur)
    return best


def test_shape(resp):
    d, s = resp
    assert TOP <= set(d), TOP - set(d)
    assert d["schema_version"] == "1.4" and d["is_sample"] is False
    assert SUMMARY <= set(d["summary"])
    assert [m["id"] for m in d["target_metrics"]] == METRIC_IDS
    for p in d["points"]:
        assert POINT <= set(p), POINT - set(p)
        assert p["class"] in ("viable", "risky", "not_viable") and set(p["reasons"]) <= REASONS
    ts = d["timeseries"]
    assert TS <= set(ts)
    n = s["days"] * 24
    assert ts["n"] == n and ts["step_h"] == 1
    for k in TS - {"t0_utc", "step_h", "n"}:
        assert len(ts[k]) == n, k
    hp = d["horizon_profile"]
    assert len(hp["elevation_deg"]) == round(360 / hp["az_step_deg"])
    assert len(d["delay_curve"]) == s["opts"].get("delay_days_max", 30) + 1
    assert d["summary"]["verdict"] in ("viable", "risky", "not_viable")


def test_summary_counts(resp):
    d, _ = resp
    sm, pts = d["summary"], d["points"]
    assert sm["n_points"] == len(pts) == sm["viable"] + sm["risky"] + sm["not_viable"]
    for c in ("viable", "risky", "not_viable"):
        assert sm[c] == sum(p["class"] == c for p in pts)
    assert sm["survival_probability"] == round(sm["viable"] / sm["n_points"], 3)
    assert sm["survival_probability_incl_risky"] == round((sm["viable"] + sm["risky"]) / sm["n_points"], 3)
    nn = [m for m in d["target_metrics"] if m["pass"] is not None]
    assert sm["checks_total"] == len(nn) and sm["checks_passed"] == sum(m["pass"] for m in nn)
    assert sm["checks_total"] == 6       # margin 0 by default; sunset is informative (CONTRACT v1.4)


def test_center_of_disk_rule_and_target_metrics(resp):
    d, s = resp
    ts = d["timeseries"]
    el, hz, lit = map(np.array, (ts["sun_el_deg"], ts["horizon_at_sun_deg"], ts["sun_lit"]))
    marg = np.array(ts["sun_margin_deg"])
    clear = np.abs(el - hz) > 0.002                         # skip hours within JSON rounding of the horizon
    assert np.all((el > hz)[clear] == (lit == 1)[clear])
    assert np.allclose(marg, el - hz, atol=0.002)
    eel, ehz, vis = map(np.array, (ts["earth_el_deg"], ts["horizon_at_earth_deg"], ts["earth_visible"]))
    clear = np.abs(eel - ehz) > 0.002
    assert np.all((eel > ehz)[clear] == (vis == 1)[clear])
    f = np.array(ts["sun_visible_fraction"])
    assert np.all((f >= 0) & (f <= 1))
    assert np.all(f[marg > 0.27] == 1) and np.all(f[marg < -0.27] == 0)
    m = {x["id"]: x for x in d["target_metrics"]}
    assert m["sun_hours"]["value"] == pytest.approx(lit.sum(), abs=0.05)
    assert m["longest_dark"]["value"] == pytest.approx(_runs(lit, 0), abs=0.05)
    assert m["earth_pct"]["value"] == pytest.approx(100 * vis.mean(), abs=0.6)
    assert m["longest_comm_gap"]["value"] == pytest.approx(_runs(vis, 0), abs=0.05)
    assert m["sun_at_touchdown"]["value"] == int(lit[0])


def test_point_classes_follow_contract_rules(resp):
    d, _ = resp
    L = d["inputs"]["limits"]
    rm = d["inputs"]["options"]["risk_margin"]
    bad = []
    for p in d["points"]:
        nv = (p["slope_deg"] > L["max_slope_deg"] or p["longest_dark_h"] > L["max_dark_h"]
              or p["longest_comm_gap_h"] > L["max_comm_gap_h"] or p["earth_pct"] < L["min_earth_pct"]
              or not p["sun_at_touchdown"])
        risky = (p["slope_deg"] > (1 - rm) * L["max_slope_deg"] or p["longest_dark_h"] > (1 - rm) * L["max_dark_h"]
                 or p["longest_comm_gap_h"] > (1 - rm) * L["max_comm_gap_h"]
                 or p["earth_pct"] < min(100, L["min_earth_pct"] * (1 + rm)))   # v1.4: sunset is not a risk reason
        cls = "not_viable" if nv else ("risky" if risky else "viable")
        if cls != p["class"]:
            bad.append((p["id"], p["class"], cls, p))
    # values in JSON are rounded (slope 1 decimal etc.), so allow a handful of boundary cases
    assert len(bad) <= max(1, len(d["points"]) // 100), bad[:3]


def test_recommendations_rules(resp):
    d, _ = resp
    rec = d["recommendations"]
    P = d["summary"]["survival_probability"]
    assert len(rec) <= 3
    assert all(r["survival_probability"] > P for r in rec)
    assert [r["survival_probability"] for r in rec] == sorted((r["survival_probability"] for r in rec), reverse=True)
