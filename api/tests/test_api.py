# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""API tests (real engine, real data; needs data/ on disk). Run: python -m pytest api -q"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from engine import analyze as engine_analyze

TOP_KEYS = ["schema_version", "is_sample", "computed_utc", "compute_ms", "inputs", "coverage", "target",
            "summary", "target_metrics", "points", "timeseries", "horizon_profile", "delay_curve",
            "delay_tolerance_days", "recommendations", "map", "warnings", "sources"]
SUMMIT = {"lat": -85.47628, "lon": 31.39691}


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "engine_ready": True, "schema_version": "1.3"}


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["schema_version"] == "1.3"
    assert m["defaults"]["limits"]["min_sun_margin_deg"] == 0
    assert "min_sun_margin_auto_deg" not in m["defaults"]
    assert m["map"]["hillshade_url"] == "/api/static/hillshade.png"
    assert any(s["id"] == "mons_mouton_center" for s in m["curated_sites"])


def test_hillshade(client):
    r = client.get("/api/static/hillshade.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_analyze_default_and_cache(client):
    app.state.cache.clear()
    r = client.post("/api/analyze", json={"target": SUMMIT})
    assert r.status_code == 200
    assert r.headers["X-Cache"] == "MISS" and float(r.headers["X-Compute-Ms"]) >= 0
    body = r.json()
    for k in TOP_KEYS:
        assert k in body, k
    assert body["schema_version"] == "1.3" and body["is_sample"] is False
    assert body["inputs"]["limits"]["min_sun_margin_deg"] == 0
    assert "low_sun_margin" not in {x for p in body["points"] for x in p["reasons"]}
    r2 = client.post("/api/analyze", json={"target": SUMMIT, "mission_days": 7})   # same normalized request
    assert r2.headers["X-Cache"] == "HIT" and r2.json()["summary"] == body["summary"]


def test_user_margin_is_optional_override(client):
    r = client.post("/api/analyze", json={"target": SUMMIT, "limits": {"min_sun_margin_deg": None}})
    assert r.status_code == 200 and r.json()["inputs"]["limits"]["min_sun_margin_deg"] == 0
    r = client.post("/api/analyze", json={"target": SUMMIT, "limits": {"min_sun_margin_deg": 4}})
    assert r.status_code == 200 and r.json()["inputs"]["limits"]["min_sun_margin_deg"] == 4


@pytest.mark.parametrize("bad", [
    {},
    {"target": {"lat": 120, "lon": 0}},
    {"target": SUMMIT, "mission_days": 0},
    {"target": SUMMIT, "limits": {"max_slope_deg": 90}},
    {"target": SUMMIT, "limits": {"min_sun_margin_deg": 30}},
    {"target": SUMMIT, "bogus": 1},
])
def test_422_on_bad_input(client, bad):
    assert client.post("/api/analyze", json=bad).status_code == 422


def test_400_out_of_coverage(client):
    r = client.post("/api/analyze", json={"target": {"lat": -80.0, "lon": 10.0}})
    assert r.status_code == 400
    b = r.json()
    assert b["error"] == "out_of_coverage" and "suggested_target" in b and set(b) == {"error", "message", "suggested_target"}


def test_400_bad_date(client):
    r = client.post("/api/analyze", json={"target": SUMMIT, "landing_utc": "yesterday"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_request"


def test_500_internal(client, monkeypatch):
    def boom(_req):
        raise RuntimeError("secret detail")
    monkeypatch.setattr(engine_analyze, "analyze", boom)
    r = client.post("/api/analyze", json={"target": SUMMIT, "mission_days": 3})
    assert r.status_code == 500 and r.json()["error"] == "internal" and "secret" not in r.text


def test_cors_localhost(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
