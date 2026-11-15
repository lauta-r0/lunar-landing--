# LunaScout

Evaluate the whole lunar landing ellipse, not just one point: how likely is your mission to survive where it will actually land?

> **Work in progress.** Built for the NASA Space Apps Challenge 2026 — *Lunar Landing Site Navigator*.

Repository: https://github.com/lauta-r0/lunar-landing--

## Structure

```
lunascout/
├── CONTRACT.md        Shared interface contract (binding)
├── CONTEXT.md         Project background and decisions
├── CLAUDE.md          Rules loaded by every Claude Code session
├── data/              raw DEMs (git-ignored), ephemeris, derived grids
├── engine/            Python engine: ephemeris, terrain, horizon, analysis
├── scripts/           Data preparation scripts
├── api/               FastAPI service
├── web/               Single-screen web interface
├── fixtures/          sample_response.json (labeled sample data)
└── docs/              Design reference, validation, submission material
```

## Data sources

- JPL Horizons System (NASA JPL) — Sun and Earth positions.
- LRO LOLA 5 m/px site DEMs (Barker et al. 2021, NASA GSFC PGDA).
- LRO LOLA 20 m/px and 40 m/px south polar gridded DEMs (LRO-L-LOLA-4-GDR-V1.0, NASA PDS Geosciences Node; Smith et al. 2017) — terrain outside the 5 m tile and far-field horizon.

## Validation

Independent checks against the live deployment; full report, figures and reproducible tests in [docs/validation.md](docs/validation.md) and `tests/validation/`.

- **Why the whole ellipse matters.** On the 5 m Mons Mouton terrain, sample points inside one 1 km-wide landing area range from **0 % to 100 %** of a 7-day mission in sunlight (several dates; `docs/validation/sunlight_spread_in_ellipse.json`).
- **Sunlight vs. LROC QuickMap.** LunaScout's lit/shadow result agrees with LROC QuickMap's independent terrain-shadow model ("Terrain Shadows @UTC", 20 m/px) on **95.5–98.0 %** of about 3,000 test points on each of three dates (Cohen's kappa **0.90–0.93**). QuickMap shadows are a model, not observations.
- **Ephemeris vs. JPL Horizons.** Sun and Earth azimuth and elevation returned by the API match direct JPL Horizons queries to **≤ 0.0013°** at our sites.
- **Test case.** The IM-2 "Athena" sites are included as quick picks; the replay and its limits (20 m terrain there, upright-lander assumption) are in [docs/athena_replay.md](docs/athena_replay.md).

## Use of AI

The team defined the problem, the requirements and the design decisions, and reviewed all results. Claude (Anthropic) assisted with the code, the documentation and the validation (tests and the comparisons with JPL Horizons and LROC QuickMap). Every AI-assisted code file starts with a header comment saying so.
