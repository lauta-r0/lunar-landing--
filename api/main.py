# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""LunaScout API (CONTRACT section 4): FastAPI wrapper around the terrain engine.

    uvicorn api.main:app --port 8000

Endpoints: GET /api/health, GET /api/meta, POST /api/analyze, GET /api/static/hillshade.png.
Responses over 1 KB are gzip-compressed when the client accepts it (GZipMiddleware).
The engine is loaded once at startup (lifespan); analyses run in a threadpool; identical requests
are served from a thread-safe LRU cache (X-Cache: HIT|MISS, X-Compute-Ms).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse as StarletteJSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from engine import analyze as engine_analyze
from engine.analyze import INPUT_LIMITS as LIM
from engine.errors import EngineError

log = logging.getLogger("lunascout.api")

REPO_ROOT = Path(__file__).resolve().parents[1]
HILLSHADE_FILE = REPO_ROOT / "data" / "derived" / "hillshade.png"
SCHEMA_VERSION = engine_analyze.SCHEMA_VERSION
CACHE_SIZE = int(os.environ.get("LUNASCOUT_API_CACHE", "256"))


# =========================================================================== responses
class JSONResponse(StarletteJSONResponse):
    """JSON with an explicit charset and ASCII-only bytes (non-ASCII characters as unicode escapes).

    Starlette's default sends `application/json` with raw UTF-8 and no charset; clients that guess the
    encoding (Windows PowerShell 5.1 and some HTTP libraries use ISO-8859-1) then show "â€”" for "—".
    With the charset declared and the bytes pure ASCII, every client decodes the same text.
    """
    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=True, allow_nan=False, indent=None,
                          separators=(",", ":")).encode("ascii")


# =========================================================================== request model (CONTRACT 4.3)
def _rng(key: str) -> dict:
    lo, hi = LIM[key]
    return {"ge": lo, "le": hi}


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-360, le=360)


class Ellipse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semi_major_m: float | None = Field(None, **_rng("semi_major_m"))
    semi_minor_m: float | None = Field(None, **_rng("semi_minor_m"))
    azimuth_deg: float | None = Field(None, ge=-360, le=720)


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_dark_h: float | None = Field(None, **_rng("max_dark_h"))
    max_comm_gap_h: float | None = Field(None, **_rng("max_comm_gap_h"))
    min_earth_pct: float | None = Field(None, **_rng("min_earth_pct"))
    max_slope_deg: float | None = Field(None, **_rng("max_slope_deg"))
    # optional user setting; null / absent = 0 (real data only)
    min_sun_margin_deg: float | None = Field(None, **_rng("min_sun_margin_deg"))


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_margin: float | None = Field(None, ge=0, le=0.9)
    delay_days_max: int | None = Field(None, **_rng("delay_days_max"))
    include_recommendations: bool | None = None
    observer_height_m: float | None = Field(None, ge=0.1, le=100)


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Target
    landing_utc: str | None = None
    mission_days: int | None = Field(None, **_rng("mission_days"))
    ellipse: Ellipse | None = None
    limits: Limits | None = None
    options: Options | None = None


# =========================================================================== cache
class LRUCache:
    """Thread-safe LRU: one lock around every get / move_to_end / insert / popitem."""

    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                return self._d[key]
        return None

    def put(self, key, value):
        with self._lock:
            self._d[key] = value
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def clear(self):
        with self._lock:
            self._d.clear()

    def __len__(self):
        with self._lock:
            return len(self._d)


# =========================================================================== app
@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    app.state.engine_ready = False
    app.state.meta = None
    app.state.cache = LRUCache(CACHE_SIZE)
    # loads the DEM, horizon grids and ephemeris once (about 5 s)
    app.state.meta = await run_in_threadpool(engine_analyze.get_meta)
    app.state.engine_ready = True
    log.info("engine ready in %.1f s", time.perf_counter() - t0)
    yield


app = FastAPI(title="LunaScout API", version=SCHEMA_VERSION, lifespan=lifespan,
              default_response_class=JSONResponse)

# the analyze JSON is ~140 KB; compress anything over 1 KB (clients that send Accept-Encoding: gzip)
app.add_middleware(GZipMiddleware, minimum_size=1000)

_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Cache", "X-Compute-Ms"],
)


@app.exception_handler(EngineError)
async def _engine_error(_request: Request, exc: EngineError):
    return JSONResponse(exc.to_dict(), status_code=400)


@app.exception_handler(Exception)
async def _unexpected(_request: Request, exc: Exception):
    log.exception("unhandled error", exc_info=exc)
    return JSONResponse({"error": "internal", "message": "Unexpected server error"}, status_code=500)


@app.get("/api/health")
def health():
    return {"status": "ok", "engine_ready": bool(app.state.engine_ready), "schema_version": SCHEMA_VERSION}


@app.get("/api/meta")
def meta():
    return app.state.meta


@app.get("/api/static/hillshade.png")
def hillshade():
    if not HILLSHADE_FILE.exists():
        return JSONResponse({"error": "not_found", "message": "hillshade.png is not available"}, status_code=404)
    return FileResponse(HILLSHADE_FILE, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/analyze")
async def analyze(body: AnalyzeRequest):
    request = body.model_dump(exclude_none=True)
    # normalized request = cache key (defaults filled, floats rounded, time floored to the hour);
    # also raises the engine's own validation errors (400)
    key = json.dumps(engine_analyze.normalize_request(request), sort_keys=True)
    cache: LRUCache = app.state.cache
    t0 = time.perf_counter()
    hit = cache.get(key)
    if hit is not None:
        result, cache_state = hit, "HIT"
    else:
        result = await run_in_threadpool(engine_analyze.analyze, request)
        cache.put(key, result)
        cache_state = "MISS"
    ms = (time.perf_counter() - t0) * 1000.0
    return JSONResponse(result, headers={"X-Cache": cache_state, "X-Compute-Ms": f"{ms:.0f}"})
