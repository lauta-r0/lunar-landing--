# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Per-point mission metrics and the viability classification (CONTRACT section 4.4).

Inputs are boolean arrays of shape (P, M): P points, M hourly samples of the mission window.
Everything is vectorized over points and hours (no Python loops over either).
"""
from __future__ import annotations

import numpy as np

VIABLE, RISKY, NOT_VIABLE = 0, 1, 2
CLASS_NAMES = ("viable", "risky", "not_viable")

FAIL_REASONS = ("slope", "darkness", "comms_gap", "earth_time", "no_sun_at_touchdown")
# v1.4: "sunset" is no longer a risk reason. A sunset is judged only through longest_dark_h vs max_dark_h;
# hours_until_sunset stays as an informational metric.
RISK_REASONS = ("slope", "darkness", "comms_gap", "earth_time", "low_sun_margin")


def longest_run(mask: np.ndarray) -> np.ndarray:
    """Length of the longest run of True along axis 1. mask (P, M) -> (P,) int."""
    mask = np.asarray(mask, dtype=bool)
    m = mask.shape[1]
    if m == 0:
        return np.zeros(mask.shape[0], dtype=np.int64)
    idx = np.arange(1, m + 1)
    last_false = np.maximum.accumulate(np.where(mask, 0, idx), axis=1)   # 1-based index of the last False so far
    return (idx - last_false).max(axis=1)


def first_false(mask: np.ndarray) -> np.ndarray:
    """Index of the first False along axis 1, or M if the row is all True. (P, M) -> (P,) int."""
    mask = np.asarray(mask, dtype=bool)
    m = mask.shape[1]
    idx = np.argmin(mask, axis=1)
    return np.where(mask.all(axis=1), m, idx)


def point_metrics(sun_lit: np.ndarray, earth_visible: np.ndarray, step_h: float = 1.0,
                  sun_margin: np.ndarray | None = None) -> dict:
    """Mission metrics for each point.

    sun_hours            hours with the Sun above the terrain horizon
    longest_dark_h       longest continuous run without Sun (a run starting at touchdown counts)
    earth_pct            % of mission time with Earth visible
    longest_comm_gap_h   longest continuous run without Earth
    hours_until_sunset   hours from touchdown to the first unlit hour (mission length if none; 0 if dark at touchdown)
    hours_until_earthset same for Earth
    sun_at_touchdown     Sun lit at the touchdown hour
    min_sun_margin       smallest (Sun elevation - horizon at the Sun's azimuth) over the LIT hours of
                         the window, degrees; NaN if the Sun is never lit (only when sun_margin given)
    """
    sun_lit = np.asarray(sun_lit, dtype=bool)
    earth_visible = np.asarray(earth_visible, dtype=bool)
    m = sun_lit.shape[1]
    out = {
        "sun_hours": sun_lit.sum(axis=1) * step_h,
        "longest_dark_h": longest_run(~sun_lit) * step_h,
        "earth_pct": 100.0 * earth_visible.sum(axis=1) / max(m, 1),
        "longest_comm_gap_h": longest_run(~earth_visible) * step_h,
        "hours_until_sunset": first_false(sun_lit) * step_h,
        "hours_until_earthset": first_false(earth_visible) * step_h,
        "sun_at_touchdown": sun_lit[:, 0].copy() if m else np.zeros(sun_lit.shape[0], dtype=bool),
    }
    if sun_margin is not None:
        mg = np.where(sun_lit, np.asarray(sun_margin, dtype=np.float64), np.inf)
        low = mg.min(axis=1) if m else np.full(sun_lit.shape[0], np.inf)
        out["min_sun_margin"] = np.where(np.isfinite(low), low, np.nan)
    return out


def classify(metrics: dict, slope_deg: np.ndarray, limits: dict, risk_margin: float,
             mission_hours: float, sun_margin_req=None):
    """Apply CONTRACT 4.4 (v1.4). Returns (codes (P,), fail_flags, risk_flags).

    A sunset during the mission does not by itself make a point risky: darkness is judged only by
    longest_dark_h against max_dark_h (not_viable above it, risky within risk_margin of it).
    mission_hours is kept in the signature for callers and for the informational sunset metric.

    sun_margin_req: required Sun clearance (degrees, scalar or (P,)). A lit point whose
    min_sun_margin is below it is "risky" with reason low_sun_margin (never not_viable).

    codes: 0 viable, 1 risky, 2 not_viable. fail_flags / risk_flags: dict reason -> bool (P,).
    """
    slope = np.asarray(slope_deg, dtype=np.float64)
    max_slope = float(limits["max_slope_deg"])
    max_dark = float(limits["max_dark_h"])
    max_gap = float(limits["max_comm_gap_h"])
    min_earth = float(limits["min_earth_pct"])
    k = 1.0 - float(risk_margin)

    fail = {
        "slope": slope > max_slope,
        "darkness": metrics["longest_dark_h"] > max_dark,
        "comms_gap": metrics["longest_comm_gap_h"] > max_gap,
        "earth_time": metrics["earth_pct"] < min_earth,
        "no_sun_at_touchdown": ~metrics["sun_at_touchdown"],
    }
    risk = {
        "slope": slope > k * max_slope,
        "darkness": metrics["longest_dark_h"] > k * max_dark,
        "comms_gap": metrics["longest_comm_gap_h"] > k * max_gap,
        "earth_time": metrics["earth_pct"] < min(100.0, min_earth * (1.0 + float(risk_margin))),
    }
    if sun_margin_req is not None and "min_sun_margin" in metrics:
        low = metrics["min_sun_margin"]
        risk["low_sun_margin"] = np.isfinite(low) & (low < np.asarray(sun_margin_req, dtype=np.float64))
    else:
        risk["low_sun_margin"] = np.zeros(slope.shape, dtype=bool)
    not_viable = np.zeros(slope.shape, dtype=bool)
    for flag in fail.values():
        not_viable |= flag
    risky = np.zeros(slope.shape, dtype=bool)
    for flag in risk.values():
        risky |= flag
    codes = np.where(not_viable, NOT_VIABLE, np.where(risky, RISKY, VIABLE)).astype(np.int8)
    return codes, fail, risk


def reasons_for(i: int, codes: np.ndarray, fail: dict, risk: dict) -> list[str]:
    """Reason list of point i: failed criteria if not viable, criteria within the margin if risky."""
    if codes[i] == NOT_VIABLE:
        return [r for r in FAIL_REASONS if fail[r][i]]
    if codes[i] == RISKY:
        return [r for r in RISK_REASONS if risk[r][i]]
    return []


def sun_visible_fraction(sun_el_deg, horizon_deg, sun_radius_deg: float = 0.2665):
    """Fraction of the solar disk above a locally flat horizon line (display only)."""
    d = np.clip((np.asarray(sun_el_deg) - np.asarray(horizon_deg)) / sun_radius_deg, -1.0, 1.0)
    return (np.arccos(-d) + d * np.sqrt(1.0 - d * d)) / np.pi
