# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
# LunaScout API (FastAPI + terrain engine). The runtime data (DEM tiles, horizon grids, ephemeris) is
# copied into the image: it is git-ignored and exists only on the build machine (see .gcloudignore).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LUNASCOUT_THREADS=2

# rasterio's bundled GDAL needs libexpat, which python:3.12-slim does not ship
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt api/requirements.txt
RUN pip install -r api/requirements.txt

# large, rarely changing data first (better layer caching)
COPY data/ephemeris/sun_earth_vectors.npz data/ephemeris/sun_earth_vectors.npz
COPY data/raw/ data/raw/
COPY data/derived/ data/derived/

COPY engine/ engine/
COPY api/ api/
COPY fixtures/ fixtures/

EXPOSE 8080
# one worker: the engine holds ~600 MB of terrain data. Loading takes ~14 s before the port answers.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
