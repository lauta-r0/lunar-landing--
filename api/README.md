# LunaScout API

FastAPI wrapper around the terrain engine (CONTRACT section 4, schema 1.3).

```bash
pip install -r api/requirements.txt          # server
pip install -r requirements-dev.txt          # tests (pytest, httpx)
uvicorn api.main:app --port 8000             # from the repo root; startup takes ~5 s (loads DEM, grids, ephemeris)
python -m pytest api -q
```

Runtime data (git-ignored, must exist locally): `data/raw/*.tif`, `data/derived/` (horizon grids, hillshade),
`data/ephemeris/sun_earth_vectors.npz`. Memory about 600 MB: give the server 1-2 GB.

| Endpoint | Description |
|---|---|
| `GET /api/health` | `{"status","engine_ready","schema_version"}` |
| `GET /api/meta` | coverage, curated sites, defaults, input limits |
| `POST /api/analyze` | analysis (request body: CONTRACT 4.3). Headers `X-Cache: HIT\|MISS`, `X-Compute-Ms` |
| `GET /api/static/hillshade.png` | LOLA hillshade for the map |

Errors: 422 (invalid input, FastAPI), 400 `{"error","message",...}` (engine errors such as `out_of_coverage`),
500 `{"error":"internal"}`.

Environment variables: `ALLOWED_ORIGINS` (comma-separated, extra CORS origins; localhost is always allowed),
`LUNASCOUT_THREADS` (threads for on-the-fly horizons, e.g. 2), `LUNASCOUT_API_CACHE` (LRU size, default 256).
`min_sun_margin_deg` defaults to 0 (real data only); it is an optional user setting.
