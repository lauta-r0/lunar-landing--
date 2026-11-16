# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Metrics and classification on synthetic hourly series (CONTRACT section 4.4)."""
import numpy as np

from engine import metrics
from engine.metrics import NOT_VIABLE, RISKY, VIABLE

LIMITS = {"max_dark_h": 50, "max_comm_gap_h": 72, "min_earth_pct": 50, "max_slope_deg": 8}


def b(*rows):
    return np.array(rows, dtype=bool)


def test_longest_run_and_first_false():
    mask = b([1, 1, 0, 1, 1, 1, 0, 1],
             [0, 0, 0, 0, 0, 0, 0, 0],
             [1, 1, 1, 1, 1, 1, 1, 1],
             [0, 1, 1, 0, 0, 1, 1, 1])
    assert metrics.longest_run(mask).tolist() == [3, 0, 8, 3]
    assert metrics.first_false(mask).tolist() == [2, 0, 8, 0]
    assert metrics.longest_run(np.zeros((2, 0), dtype=bool)).tolist() == [0, 0]


def test_point_metrics_basic():
    sun = b([1, 1, 0, 0, 0, 1, 0, 1],      # sunset after 2 h, longest dark 3 h
            [0, 0, 1, 1, 1, 1, 1, 1])      # dark at touchdown: the run starting at hour 0 counts
    earth = b([1, 1, 1, 1, 0, 0, 0, 0],
              [0, 1, 0, 0, 1, 1, 1, 1])
    m = metrics.point_metrics(sun, earth)
    assert m["sun_hours"].tolist() == [4, 6]
    assert m["longest_dark_h"].tolist() == [3, 2]
    assert m["hours_until_sunset"].tolist() == [2, 0]
    assert m["sun_at_touchdown"].tolist() == [True, False]
    assert m["earth_pct"].tolist() == [50.0, 62.5]
    assert m["longest_comm_gap_h"].tolist() == [4, 2]
    assert m["hours_until_earthset"].tolist() == [4, 0]


def test_no_sunset_gives_mission_length():
    m = metrics.point_metrics(np.ones((1, 168), dtype=bool), np.ones((1, 168), dtype=bool))
    assert m["hours_until_sunset"][0] == 168 and m["longest_dark_h"][0] == 0 and m["sun_hours"][0] == 168


def _metrics(dark=0.0, gap=0.0, earth=100.0, sunset=168.0, touchdown=True):
    return {"longest_dark_h": np.array([dark]), "longest_comm_gap_h": np.array([gap]),
            "earth_pct": np.array([earth]), "hours_until_sunset": np.array([sunset]),
            "sun_at_touchdown": np.array([touchdown]), "sun_hours": np.array([0.0]),
            "hours_until_earthset": np.array([0.0])}


def _classify(slope=2.0, margin=0.2, **kw):
    codes, fail, risk = metrics.classify(_metrics(**kw), np.array([slope]), LIMITS, margin, 168)
    return int(codes[0]), metrics.reasons_for(0, codes, fail, risk)


def test_classification_rules():
    assert _classify() == (VIABLE, [])
    # not viable: each criterion alone
    assert _classify(slope=8.01) == (NOT_VIABLE, ["slope"])
    assert _classify(dark=51) == (NOT_VIABLE, ["darkness"])
    assert _classify(gap=73) == (NOT_VIABLE, ["comms_gap"])
    assert _classify(earth=49.9) == (NOT_VIABLE, ["earth_time"])
    assert _classify(touchdown=False, sunset=0) == (NOT_VIABLE, ["no_sun_at_touchdown"])
    # exactly at the limit is not a failure, but it is inside the risk margin
    assert _classify(slope=8.0) == (RISKY, ["slope"])
    assert _classify(dark=50) == (RISKY, ["darkness"])
    # risky: within 20% of a limit
    assert _classify(slope=6.5) == (RISKY, ["slope"])           # > 0.8 * 8 = 6.4
    assert _classify(slope=6.4) == (VIABLE, [])
    assert _classify(dark=41) == (RISKY, ["darkness"])          # > 0.8 * 50 = 40
    assert _classify(gap=58) == (RISKY, ["comms_gap"])          # > 0.8 * 72 = 57.6
    assert _classify(earth=59.9) == (RISKY, ["earth_time"])     # < 50 * 1.2 = 60
    assert _classify(earth=60.0) == (VIABLE, [])
    # v1.4: a sunset during the mission is NOT a reason by itself (darkness is judged by longest_dark_h only)
    assert _classify(sunset=100) == (VIABLE, [])
    assert _classify(sunset=0, dark=10) == (VIABLE, [])
    # several reasons, contract order
    assert _classify(slope=9, dark=60, gap=80) == (NOT_VIABLE, ["slope", "darkness", "comms_gap"])
    assert _classify(slope=7, sunset=10) == (RISKY, ["slope"])
    # a not_viable point lists only what failed, not what is merely risky
    assert _classify(slope=9, dark=45) == (NOT_VIABLE, ["slope"])


def test_earth_risk_threshold_is_clipped_at_100():
    limits = dict(LIMITS, min_earth_pct=90)
    codes, _, _ = metrics.classify(_metrics(earth=100.0), np.array([1.0]), limits, 0.2, 168)
    assert codes[0] == VIABLE                       # 90 * 1.2 = 108 -> clipped to 100; 100 is not < 100
    codes, _, _ = metrics.classify(_metrics(earth=99.0), np.array([1.0]), limits, 0.2, 168)
    assert codes[0] == RISKY


def test_sun_visible_fraction():
    f = metrics.sun_visible_fraction(np.array([1.0, 0.0, -1.0, 0.2665, -0.2665]), 0.0)
    assert np.allclose(f, [1.0, 0.5, 0.0, 1.0, 0.0], atol=1e-9)
    mid = metrics.sun_visible_fraction(0.1, 0.0)
    assert 0.5 < float(mid) < 1.0


def test_low_sun_margin_is_risky_never_not_viable():
    """Sun clearance below the required margin during lit hours -> risky (low_sun_margin) only."""
    lit = np.ones((3, 24), dtype=bool)
    lit[2] = False                                   # never lit: no margin, darkness decides
    earth = np.ones((3, 24), dtype=bool)
    margin = np.full((3, 24), 5.0)
    margin[1, 7] = 1.0                               # one lit hour only 1 deg above the horizon
    margin[0, 3] = -2.0                              # an unlit hour does not count (lit[0,3] set False)
    lit[0, 3] = False
    m = metrics.point_metrics(lit, earth, sun_margin=margin)
    assert m["min_sun_margin"][0] == 5.0 and m["min_sun_margin"][1] == 1.0 and np.isnan(m["min_sun_margin"][2])
    limits = {"max_slope_deg": 8, "max_dark_h": 50, "max_comm_gap_h": 72, "min_earth_pct": 50}
    codes, fail, risk = metrics.classify(m, np.zeros(3), limits, 0.2, 24, sun_margin_req=np.array([2.86, 2.86, 2.86]))
    assert list(risk["low_sun_margin"]) == [False, True, False]
    assert codes[1] == metrics.RISKY and metrics.reasons_for(1, codes, fail, risk) == ["low_sun_margin"]
    assert not any(fail[r][1] for r in fail)         # never a failure reason
    # margin 0 disables the rule (a lit hour always has a positive margin)
    codes0, _f, risk0 = metrics.classify(m, np.zeros(3), limits, 0.2, 24, sun_margin_req=0.0)
    assert not risk0["low_sun_margin"].any()


def test_sunset_is_not_a_risk_reason():
    """v1.4: "sunset" is gone from the risk criteria; hours_until_sunset stays as a metric only."""
    assert "sunset" not in metrics.RISK_REASONS and "sunset" not in metrics.FAIL_REASONS
    codes, fail, risk = metrics.classify(_metrics(sunset=5.0, dark=10.0), np.array([1.0]), LIMITS, 0.2, 168)
    assert "sunset" not in risk and "sunset" not in fail
    assert codes[0] == VIABLE


def test_battery_size_moves_the_class_through_longest_dark_only():
    """One point with a 60 h night and a sunset during the mission: only max_dark_h decides its class."""
    for max_dark, expected in [(50, NOT_VIABLE), (60, RISKY), (70, RISKY), (74, RISKY), (76, VIABLE), (400, VIABLE)]:
        limits = dict(LIMITS, max_dark_h=max_dark)
        codes, fail, risk = metrics.classify(_metrics(dark=60.0, sunset=20.0), np.array([1.0]), limits, 0.2, 336)
        assert codes[0] == expected, (max_dark, codes[0])
        if expected == NOT_VIABLE:
            assert metrics.reasons_for(0, codes, fail, risk) == ["darkness"]


def test_survival_rises_with_max_dark_h_in_a_14_day_mission():
    """Four points over 336 h, each with a sunset and a different longest night (30, 60, 100, 200 h).

    Under the old rule every one of them was risky (sunset) at any battery size, so the viable count
    never moved. Now it grows as the battery allows each night: 0 -> 1 -> 2 -> 3 -> 4 of 4.
    """
    hours = 14 * 24
    lit = np.ones((4, hours), dtype=bool)
    for row, night in enumerate((30, 60, 100, 200)):
        lit[row, 40:40 + night] = False                    # first night starts after 40 h of light
    earth = np.ones((4, hours), dtype=bool)
    m = metrics.point_metrics(lit, earth)
    assert m["longest_dark_h"].tolist() == [30, 60, 100, 200]
    assert (m["hours_until_sunset"] < hours).all()          # every point sees a sunset

    viable = []
    for max_dark in (25, 50, 100, 150, 400):
        limits = dict(LIMITS, max_dark_h=max_dark)
        codes, _f, _r = metrics.classify(m, np.zeros(4), limits, 0.2, hours)
        viable.append(int((codes == VIABLE).sum()))
    # max_dark_h 25, 50, 100, 150, 400 -> 0, 1, 2, 3, 4 viable points
    assert viable == [0, 1, 2, 3, 4]
