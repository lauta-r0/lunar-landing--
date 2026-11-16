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
- Local API: run `uvicorn api.main:app --port 8000` from the repo root and open the page with `?api=local` (honoured only on localhost), or set `window.LUNASCOUT_API = "http://localhost:8000/api"`
- Production behind Firebase Hosting `/api/**` rewrites: `/api`

If `/api/meta` is unreachable, the app shows `fixtures/sample_response.json` (a saved real analysis) with the **SAMPLE DATA — API OFFLINE** badge. Sample data is never shown without that badge.

## Files

| File | Purpose |
|---|---|
| `index.html` | Layout: header, settings, map + timeline, results, footer, About modal |
| `styles.css` | Design tokens and components (palette, type, pills, responsive stacking) |
| `config.js` | API base URL |
| `js/app.js` | State, form ↔ request, run states, rendering of results |
| `js/api.js` | `GET /api/meta`, `POST /api/analyze`, `POST /api/best-sites` (cancellable), fixture loader |
| `js/map.js` | Canvas map: hillshade by its bounds, best-sites heatmap and ranked pins, km grid, 5 m data footprint, ellipse, points, target, pin, pan/zoom, click-to-pick |
| `js/proj.js` | South polar stereographic projection (inverse for click-to-pick), parameters from `/api/meta` `map.crs_proj4` |
| `js/timeline.js` | Mission timeline chart (Sun / Earth elevation vs. terrain horizon) |
| `js/format.js` | Formatting and plain-language reason / metric text |
| `js/tooltip.js` | Hover + keyboard-focus tooltips |
| `js/about.js` | About & method modal |
| `fixtures/` | Offline sample response and a copy of the hillshade |

Map keys (canvas focused): arrows pan, `+` / `-` zoom, `0` reset, `Enter` picks the map center as the target, `Esc` closes a pinned point. Mouse wheel zooms, drag pans.

Click-to-pick: a click on empty terrain (pointer moved less than 5 px) converts the position to lat/lon, fills the target fields (5 decimals), drops a pin and runs the analysis. Clicks outside `/api/meta` `coverage.bounds_xy_m` show the out-of-area message without calling the API. A click on a sample point pins its details instead; the pinned card has **Set as target**. Clicks are ignored while an analysis is running.

## Best sites (CONTRACT 4.7)

**Find best sites** (under Run analysis) sends the mission settings without the target to `POST /api/best-sites`; the segmented control **All data · 5 m only · 20 m only** is its `region` parameter. **5 m only** is the default (the most reliable data); "All data" carries an ⓘ: "Includes 20 m terrain, which can hide small craters and slopes." The region is judged on the whole ellipse (at least 95% on that data), not on its center.

- **Heatmap**: `heatmap.data_b64` (uint8, 255 = invalid) is drawn between the hillshade and the grid as one hue, transparent to the viable green `#3DDC84` at 50% opacity; invalid cells are transparent. The **Heatmap** toggle and the scale "Survival probability if you aim here: 0% → 100%" sit directly under the map, with the note "Approximate (coarse sampling); click a site for the full analysis". A new result fits the map to the whole region; the reset button returns to the ellipse.
- **Pins**: white outlined circles with the rank number; the site that is the analysed target is a filled white circle beside the crosshair. A pin or a list row runs the full analysis there.
- **List** ("Best sites in region", under the results): `<button>` rows in the "Recommended nearby" style, in an `aria-live` region. The badge is the composition of the site's ellipse (`sites[].fine_fraction`): `5 M · 100%`, `20 M · 100%` or `MIXED · 40% 5 M`. The list is always in order of the real survival probability (ties: more of the ellipse on 5 m data); nothing is adjusted for the data resolution. No site above 0%: "No site meets your limits for this date. Try relaxing the limits or another date."
- **Requests**: a new best-sites request aborts the one in flight (`AbortController`). Analyze and best-sites never run together: each button is disabled while the other request runs, and map clicks are ignored.
- **Stale / offline**: when the settings differ from the ones the list answers, it is dimmed with "Settings changed — find best sites again to update". If the API is unreachable the button reads **Unavailable offline**; best sites are never taken from the fixture and are cleared when sample data is shown.

The dashed outline is `map.hires_bounds_xy_m` (schema 1.5), the extent of the LOLA 5 m/px tile. The **Data resolution** badge next to the survival probability summarizes `points[].slope_dem_m` / `slope_coarse`: `5 M · HIGH`, `20 M · LOWER` or `MIXED · 5/20 M`.
