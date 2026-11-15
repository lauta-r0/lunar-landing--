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
| `js/map.js` | Canvas map: hillshade by its bounds, km grid, ellipse, points, target, pan/zoom |
| `js/timeline.js` | Mission timeline chart (Sun / Earth elevation vs. terrain horizon) |
| `js/format.js` | Formatting and plain-language reason / metric text |
| `js/tooltip.js` | Hover + keyboard-focus tooltips |
| `js/about.js` | About & method modal |
| `fixtures/` | Offline sample response and a copy of the hillshade |

Map keys (canvas focused): arrows pan, `+` / `-` zoom, `0` reset, `Esc` closes a pinned point. Mouse wheel zooms, drag pans.
