# LunaScout — web frontend

Single-screen static UI (plain HTML + CSS + ES modules, Chart.js from a pinned CDN URL). No build step.

## Run locally

```bash
cd web
python -m http.server 5500
```

Open http://localhost:5500 (never via `file://`: the browser blocks the API calls). If port 5500 is taken, use any other port (e.g. 5501); the API allows CORS from `http://localhost:*`.

## API

`web/config.js` sets `window.LUNASCOUT_API`:

- Live (default): `https://lunascout-api-855190992553.southamerica-east1.run.app/api`
- Local API: run `uvicorn api.main:app --port 8000` from the repo root and set `http://localhost:8000/api`
- Production behind Firebase Hosting `/api/**` rewrites: `/api`

If `/api/meta` is unreachable, the app shows `fixtures/sample_response.json` (a saved real analysis) with the **SAMPLE DATA — API OFFLINE** badge. Sample data is never shown without that badge.

## Files

| File | Purpose |
|---|---|
| `index.html` | Layout: header, settings, map + timeline, results, footer, About modal |
| `styles.css` | Design tokens and components (palette, type, pills, responsive stacking) |
| `config.js` | API base URL |
| `js/app.js` | State, form ↔ request, run states, rendering of results |
| `js/api.js` | `GET /api/meta`, `POST /api/analyze`, fixture loader |
| `js/map.js` | Canvas map: hillshade by its bounds, km grid, 5 m data footprint, ellipse, points, target, pin, pan/zoom, click-to-pick |
| `js/proj.js` | South polar stereographic projection (inverse for click-to-pick), parameters from `/api/meta` `map.crs_proj4` |
| `js/timeline.js` | Mission timeline chart (Sun / Earth elevation vs. terrain horizon) |
| `js/format.js` | Formatting and plain-language reason / metric text |
| `js/tooltip.js` | Hover + keyboard-focus tooltips |
| `js/about.js` | About & method modal |
| `fixtures/` | Offline sample response and a copy of the hillshade |

Map keys (canvas focused): arrows pan, `+` / `-` zoom, `0` reset, `Enter` picks the map center as the target, `Esc` closes a pinned point. Mouse wheel zooms, drag pans.

Click-to-pick: a click on empty terrain (pointer moved less than 5 px) converts the position to lat/lon, fills the target fields (5 decimals), drops a pin and runs the analysis. Clicks outside `/api/meta` `coverage.bounds_xy_m` show the out-of-area message without calling the API. A click on a sample point pins its details instead; the pinned card has **Set as target**. Clicks are ignored while an analysis is running.

The dashed outline is `map.hires_bounds_xy_m` (schema 1.5), the extent of the LOLA 5 m/px tile. The **Data resolution** badge next to the survival probability summarizes `points[].slope_dem_m` / `slope_coarse`: `5 M · HIGH`, `20 M · LOWER` or `MIXED · 5/20 M`.
