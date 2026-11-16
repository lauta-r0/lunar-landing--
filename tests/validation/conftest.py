# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Shared fixtures for the live validation tests (Agent 06).

These tests call the deployed LunaScout API (and, for the ephemeris check, JPL Horizons) over the
network. They are skipped automatically when the API is unreachable.

    python -m pytest tests/validation -v
    LUNASCOUT_API=http://localhost:8000/api python -m pytest tests/validation -v
"""
from __future__ import annotations

import os
from functools import lru_cache

import pytest
import requests

API = os.environ.get("LUNASCOUT_API", "https://lunascout.web.app/api").rstrip("/")
TIMEOUT = 120

DEM_CENTER = (-85.42658, 31.74276)
SUMMIT = (-85.47628, 31.39691)
ATHENA_ACTUAL = (-84.79059, 29.19567)
SHACKLETON = (-89.67, 129.78)


@lru_cache(maxsize=1)
def _api_up() -> bool:
    try:
        r = requests.get(API + "/health", timeout=20)
        return r.status_code == 200 and r.json().get("engine_ready") is True
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def api():
    if not _api_up():
        pytest.skip(f"LunaScout API not reachable at {API}")
    return API


@pytest.fixture(scope="session")
def meta(api):
    return requests.get(api + "/meta", timeout=TIMEOUT).json()


_CACHE: dict = {}


def analyze(api: str, lat: float, lon: float, landing_utc: str = "2027-10-12T14:00:00Z",
            mission_days: int = 7, ellipse=(1000, 600, 0), limits: dict | None = None,
            options: dict | None = None, raw: bool = False):
    body = {"target": {"lat": lat, "lon": lon}, "landing_utc": landing_utc,
            "mission_days": mission_days,
            "ellipse": {"semi_major_m": ellipse[0], "semi_minor_m": ellipse[1], "azimuth_deg": ellipse[2]}}
    if limits:
        body["limits"] = limits
    body["options"] = {"include_recommendations": False, "delay_days_max": 0, **(options or {})}
    key = repr(body)
    if key not in _CACHE:
        r = requests.post(api + "/analyze", json=body, timeout=TIMEOUT)
        if raw:
            return r
        assert r.status_code == 200, r.text[:500]
        _CACHE[key] = r.json()
    return _CACHE[key]
