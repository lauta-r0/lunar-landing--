# Developed with assistance from Claude (Anthropic). Reviewed and integrated by the LunaScout team.
"""Write fixtures/sample_response.json from a real analyze() run of the default request.

    python -m engine.make_fixture

The fixture is what the frontend shows when the API is unreachable, so the copy always has
"is_sample": true (CONTRACT section 6). The target is the first curated site that is viable
or risky, so the sample shows all three classes on the map. It uses the default request, whose
landing date (2027-10-12T14:00Z, CONTRACT v1.2) shows all three classes at the summit plateau
(the earlier default, 2027-03-10, fell in a dark period there: every point was not viable).
"""
from __future__ import annotations

import json
from pathlib import Path

from .analyze import analyze, get_meta

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_response.json"


def main() -> int:
    meta = get_meta()
    sites = {s["id"]: s for s in meta["curated_sites"]}
    site = sites.get("summit_plateau", meta["curated_sites"][0])
    target = {"lat": site["lat"], "lon": site["lon"]}
    result = analyze({"target": target})
    landing = result["inputs"]["landing_utc"]
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
