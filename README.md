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

## Use of AI

_Placeholder — to be completed by the team._ This project is developed with assistance from Claude (Anthropic). Code files carry an AI-use header; the team owns the concept and reviews all output.
