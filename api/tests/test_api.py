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
    assert r.json() == {"status": "ok", "engine_ready": True, "schema_version": "1.5"}


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["schema_version"] == "1.5"
    assert m["defaults"]["limits"]["min_sun_margin_deg"] == 0
    assert "min_sun_margin_auto_deg" not in m["defaults"]
    assert m["map"]["hillshade_url"] == "/api/static/hillshade.png"
    # schema 1.5: extent of the 5 m tile, inside the hillshade, same polar stereographic meters
    hx0, hy0, hx1, hy1 = m["map"]["hires_bounds_xy_m"]
    sx0, sy0, sx1, sy1 = m["map"]["hillshade_bounds_xy_m"]
    assert hx0 < hx1 and hy0 < hy1 and sx0 <= hx0 and sy0 <= hy0 and hx1 <= sx1 and hy1 <= sy1
    assert m["map"]["hires_label"] == "LOLA 5 m/px" and m["map"]["coarse_label"] == "LOLA 20 m/px"
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
    assert body["schema_version"] == "1.5" and body["is_sample"] is False
    assert body["inputs"]["limits"]["min_sun_margin_deg"] == 0
    meta_map = client.get("/api/meta").json()["map"]
    for k in ("hires_bounds_xy_m", "hires_label", "coarse_label"):
        assert body["map"][k] == meta_map[k], k
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


def test_no_mojibake_and_charset(client):
    """Responses declare utf-8 and carry no mojibake markers (text is escaped ASCII, decodes the same everywhere)."""
    responses = [client.get("/api/health"), client.get("/api/meta"),
                 client.post("/api/analyze", json={"target": SUMMIT}),
                 client.post("/api/analyze", json={"target": {"lat": -80.0, "lon": 10.0}})]
    for r in responses:
        assert "charset=utf-8" in r.headers["content-type"]
        for text in (r.content.decode("ascii"), r.content.decode("latin-1"), r.text):
            assert "Ã" not in text and "â€" not in text and "Â" not in text
    meta = responses[1].json()
    assert "—" in meta["coverage"]["dem_name"] and "—" in meta["coverage"]["dem_name"]
    assert "—" in " ".join(responses[2].json()["sources"])
    assert "—" in responses[3].json()["message"] or "DEM" in responses[3].json()["message"]


def test_recommendations_are_nearby(client):
    """Recommended targets (rings of 1-3 km and curated sites) are within 5 km of the target."""
    for target in (SUMMIT, {"lat": -85.23787, "lon": 33.95403}, {"lat": -84.79059, "lon": 29.19567}):
        r = client.post("/api/analyze", json={"target": target}).json()
        for rec in r["recommendations"]:
            assert rec["distance_km"] <= 5.0, rec


def test_analyze_is_gzip_compressed_and_lossless(client):
    """~140 KB JSON is compressed when the client accepts gzip (validation P2); the body decodes to the same data."""
    app.state.cache.clear()
    plain = client.post("/api/analyze", json={"target": SUMMIT}, headers={"Accept-Encoding": "identity"})
    assert plain.status_code == 200 and "content-encoding" not in plain.headers
    zipped = client.post("/api/analyze", json={"target": SUMMIT}, headers={"Accept-Encoding": "gzip"})
    assert zipped.status_code == 200 and zipped.headers["content-encoding"] == "gzip"
    assert zipped.headers["content-type"].startswith("application/json")
    assert zipped.json()["summary"] == plain.json()["summary"]      # TestClient (httpx) decodes the gzip body
    small = client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in small.headers                   # under 1 KB: not compressed
