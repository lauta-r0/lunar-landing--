# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""
Download hourly Sun and Earth az/el from JPL Horizons for ONE lunar reference site and store
them as unit vectors in the Moon ME body-fixed frame.

    python scripts/fetch_ephemeris.py --start 2025-01-01 --end 2028-12-31 \
        --ref-lat -85.0 --ref-lon 31.0 --out data/ephemeris/sun_earth_vectors.npz

Raw Horizons responses are cached in data/ephemeris/raw/ so re-runs do not hit the API.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.ephemeris import azel_to_vec  # noqa: E402

API = "https://ssd.jpl.nasa.gov/api/horizons.api"
RAW_DIR = ROOT / "data" / "ephemeris" / "raw"
BODIES = {"sun": "10", "earth": "399"}
MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


# --------------------------------------------------------------------------- Horizons client
def _query(command: str, lat: float, lon: float, start: str, stop: str, retries: int = 5) -> str:
    params = {
        "format": "text", "COMMAND": f"'{command}'", "CENTER": "'coord@301'",
        "COORD_TYPE": "'GEODETIC'", "SITE_COORD": f"'{lon},{lat},0'",      # longitude first
        "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'OBSERVER'", "QUANTITIES": "'4'",
        "START_TIME": f"'{start}'", "STOP_TIME": f"'{stop}'", "STEP_SIZE": "'1h'",
        "CSV_FORMAT": "'YES'", "ANG_FORMAT": "'DEG'",
    }
    for attempt in range(retries):
        try:
            r = requests.get(API, params=params, timeout=120)
            if r.status_code == 200 and "$$SOE" in r.text:
                return r.text
            err = f"HTTP {r.status_code}: {r.text[:200]!r}"
        except requests.RequestException as exc:
            err = repr(exc)
        wait = 2 ** (attempt + 1)
        print(f"  Horizons error ({err}); retry in {wait}s", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"Horizons query failed after {retries} attempts: {command} {lat},{lon} {start}..{stop}")


def parse_horizons(text: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parse a CSV OBSERVER response -> (t_unix int64, az_deg, el_deg). Column positions come from the header."""
    lines = text.splitlines()
    header = next((ln for ln in lines if "Date" in ln and "Azi" in ln), None)
    if header is None:
        raise ValueError("Header with Azi/Elev columns not found")
    cols = [c.strip() for c in header.split(",")]
    i_az = next(i for i, c in enumerate(cols) if c.startswith("Azi"))
    i_el = next(i for i, c in enumerate(cols) if c.startswith("Elev"))
    body = text.split("$$SOE")[1].split("$$EOE")[0]
    t, az, el = [], [], []
    for ln in body.strip().splitlines():
        f = [x.strip() for x in ln.split(",")]
        m = re.match(r"(\d{4})-(\w{3})-(\d{2}) (\d{2}):(\d{2})", f[0])
        if not m:
            raise ValueError(f"Unparseable time: {ln!r}")
        when = datetime(int(m[1]), MONTHS[m[2]], int(m[3]), int(m[4]), int(m[5]), tzinfo=timezone.utc)
        t.append(int(when.timestamp()))
        az.append(float(f[i_az]))
        el.append(float(f[i_el]))
    return np.array(t, np.int64), np.array(az), np.array(el)


def fetch_site_series(body: str, lat: float, lon: float, start: datetime, stop: datetime, chunk_months: int = 3,
                      sleep_s: float = 1.0, cache_dir: Path = RAW_DIR):
    """Hourly az/el of ``body`` ('sun'|'earth') from a site, [start, stop] inclusive, chunked and cached."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_t, out_az, out_el = [], [], []
    cur = start
    while cur <= stop:
        m = cur.month - 1 + chunk_months
        nxt = cur.replace(year=cur.year + m // 12, month=m % 12 + 1, day=1, hour=0)
        last = min(nxt - timedelta(hours=1), stop)
        s, e = f"{cur:%Y-%m-%d %H:%M}", f"{last:%Y-%m-%d %H:%M}"
        cache = cache_dir / f"{body}_lat{lat}_lon{lon}_{cur:%Y%m%d%H}_{last:%Y%m%d%H}.txt"
        if cache.exists():
            text = cache.read_text(encoding="utf-8")
        else:
            print(f"Horizons {body} {s} .. {e}")
            text = _query(BODIES[body], lat, lon, s, e)
            cache.write_text(text, encoding="utf-8")
            time.sleep(sleep_s)
        t, az, el = parse_horizons(text)
        n_exp = int((last - cur).total_seconds() // 3600) + 1
        assert len(t) == n_exp, f"{body} {s}: expected {n_exp} rows, got {len(t)}"
        assert t[0] == int(cur.timestamp()) and t[-1] == int(last.timestamp()), "chunk bounds mismatch"
        out_t.append(t); out_az.append(az); out_el.append(el)
        cur = last + timedelta(hours=1)
    t, az, el = np.concatenate(out_t), np.concatenate(out_az), np.concatenate(out_el)
    assert np.all(np.diff(t) == 3600), "missing or non-increasing hours"
    return t, az, el


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2028-12-31", help="last day, inclusive (hours through 23:00)")
    ap.add_argument("--ref-lat", type=float, default=-85.0, help="reference site latitude (deg, south negative)")
    ap.add_argument("--ref-lon", type=float, default=31.0, help="reference site longitude (deg east)")
    ap.add_argument("--out", default=str(ROOT / "data" / "ephemeris" / "sun_earth_vectors.npz"))
    a = ap.parse_args()

    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    stop = datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc) + timedelta(hours=23)

    vecs, t_ref = {}, None
    for body in BODIES:
        t, az, el = fetch_site_series(body, a.ref_lat, a.ref_lon, start, stop)
        if t_ref is None:
            t_ref = t
        assert np.array_equal(t, t_ref), "Sun and Earth time grids differ"
        vecs[body] = azel_to_vec(az, el, a.ref_lat, a.ref_lon)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out, t_unix=t_ref, sun_vec=vecs["sun"], earth_vec=vecs["earth"],
        ref_lat=np.array(str(a.ref_lat)), ref_lon=np.array(str(a.ref_lon)),
        frame=np.array("MOON_ME (Horizons MEAN_ME)"), source=np.array("JPL Horizons API, DE441"),
        created_utc=np.array(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")), step=np.array("1h"),
    )
    print(f"Wrote {out} ({len(t_ref)} hourly samples, {out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
