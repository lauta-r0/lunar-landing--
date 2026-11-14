# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Write fixtures/sample_response.json from a real analyze() run of the default request.

    python -m engine.make_fixture

The fixture is what the frontend shows when the API is unreachable, so the copy always has
"is_sample": true (CONTRACT section 6). The target is the first curated site that is viable
or risky, so the sample shows all three classes on the map. The landing date is chosen by scanning
2027 (every second day, 14:00 UTC): the date with the highest survival probability among those where
the target is not "not_viable" and all three classes appear. (The contract's default date,
2027-03-10, falls in a dark period at the summit plateau: every point is not viable.)
"""
from __future__ import annotations

import json
from pathlib import Path

from .analyze import analyze, get_meta

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_response.json"


def _pick_date(target: dict) -> str:
    from datetime import datetime, timedelta

    best, best_p = None, -1.0
    for k in range(0, 365, 2):
        utc = (datetime(2027, 1, 1, 14) + timedelta(days=k)).strftime("%Y-%m-%dT%H:00:00Z")
        try:
            r = analyze({"target": target, "landing_utc": utc,
                         "options": {"include_recommendations": False, "delay_days_max": 0}})
        except Exception:  # noqa: BLE001  (date outside the ephemeris, etc.)
            continue
        s = r["summary"]
        if s["verdict"] != "not_viable" and min(s["viable"], s["risky"], s["not_viable"]) > 0                 and s["survival_probability"] > best_p:
            best, best_p = utc, s["survival_probability"]
    return best or "2027-03-10T14:00:00Z"


def main() -> int:
    meta = get_meta()
    sites = {s["id"]: s for s in meta["curated_sites"]}
    site = sites.get("summit_plateau", meta["curated_sites"][0])
    target = {"lat": site["lat"], "lon": site["lon"]}
    landing = _pick_date(target)
    result = analyze({"target": target, "landing_utc": landing})
    real_ephemeris = not result["is_sample"]
    result["is_sample"] = True
    if real_ephemeris:
        note = "Sample data — saved example of a real analysis, shown because the API is offline."
    else:
        note = ("Sample data — saved example: real LOLA terrain, but SYNTHETIC Sun/Earth positions "
                "(development stub; the real JPL Horizons ephemeris is not integrated yet).")
    if note not in result["warnings"]:
        result["warnings"].insert(0, note)
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    s = result["summary"]
    print(f"wrote {OUT} ({OUT.stat().st_size / 1000:.0f} kB): target {site['name']}, {s['n_points']} points, "
          f"landing {landing}, P = {s['survival_probability']}, verdict {s['verdict']}, "
          f"real ephemeris: {real_ephemeris}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
